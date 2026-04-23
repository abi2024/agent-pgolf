# Session Summary — 2026-04-23 Autonomous Block

3-phase autonomous block: write exp_001 analysis, build canonical_rescore tool,
run audit on top-10 PRs, draft three audit docs, push to origin.

## What was done

### Pre-Phase: exp_001 analysis.md
* Wrote `experiments/exp_001/analysis.md` documenting the PR #1727 reproduction:
  seed 1337, val_bpb 1.07431 (post-TTT), 4982/20000 iters, 15,935,812-byte
  artifact, +0.00214 vs reported 3-seed mean (within tolerance [1.062, 1.082]).
* Hardware parity confirmed; pre/post-quant/post-TTT arc documented.
* Commit: `21455f1 exp_001: analysis.md — hardware parity confirmed`.

### Phase 1: canonical_rescore tool + tests
* Built `scripts/canonical_rescore.py` — static LUT inspection +
  byte-count computation. No GPU, no model checkpoint required.
* Detection logic:
  * `BUGGY` — regex `len(piece.encode("utf-8")) + 1`
  * `CORRECT` — regex `base_bytes_np[token_id] = len(piece.encode...)` without +1
  * `OBFUSCATED` — `*.decompress(*.b85decode(...))` (handles both inline-`exec`
    and assign-then-runpy patterns)
  * `UNKNOWN` — fallthrough
* Vectorized byte-count: scored y-positions tile `val_tokens[1:N]`, so total
  reduces to two array sums; `buggy_total = canonical_total + sum(has_leading_space[y])`.
* Wrote `tests/test_canonical_rescore.py` with 10 tests — all pass:
  * CORRECT classification on PR #1727 actual file
  * BUGGY classification on `tests/fixtures/buggy_train_gpt.py` (PR #1727
    + `+1` inserted at line 196)
  * OBFUSCATED detection (both wrapper variants)
  * Synthetic byte-counting math (hand-verified against eval_val_sliding logic)
  * Real-data inflation ratio in [1.10, 1.25] range
  * End-to-end rescore for both CORRECT and BUGGY scripts
* Verified tool reproduces the audit doc's exact numbers on full SP8192 val:
  canonical=151,080,891 / buggy=176,332,748 / ratio=1.1671.
* Commit: `ffa66e5 tool: canonical_rescore.py for BPB byte-count audit`.

### Phase 2: top-10 PR audit
* `audit/run_audit.sh` driver fetches each PR via
  `git fetch upstream pull/<N>/head:pr-<N>`, locates train_gpt.py under
  `records/track_10min_16mb/`, runs the rescore tool, captures JSON.
* Results (sorted by reported BPB, lowest-best):
  1. #1785 OE-GOD     1.01925 → **OBFUSCATED**
  2. #1758 kilojoules 1.02840 → **OBFUSCATED**
  3. #1738 alertcat   1.03540 → **OBFUSCATED**
  4. #1735 AjAnubolu  1.04290 → ✅ CORRECT (verified frontier)
  5. #1779 leon2k2k2k 1.06421 → ✅ CORRECT
  6. #1769 dexhunter  1.06453 → ✅ CORRECT
  7. #1756 romeerp    1.06505 → ✅ CORRECT
  8. #1771 bigbag     1.06513 → **OBFUSCATED**
  9. #1736 dexhunter  1.06549 → ✅ CORRECT
  10. #1784 renqianluo 1.07081 → ✅ CORRECT
* Per-PR JSON in `audit/per_pr/<pr>.json`. Driver log in `audit/run_audit.log`.
* `audit/corrected_leaderboard.md` written with full table + True Top 5.
* Tool detector was extended once during Phase 2: PR #1771 used a `runpy`
  wrapper instead of inline `exec`; the regex was widened to match both. All
  10 tests still pass.
* Restored `/workspace/parameter-golf` to `pr-1727` branch.
* Commit: `b784d49 audit: Phase 2 results — leaderboard inspection across top-10 PRs`.

### Phase 3: writeup / methodology / results docs
* `audit/writeup.md` — PR-body-style document. TL;DR, bug anatomy, methodology,
  results table, tool usage, attribution (verbatim PR #1734 closure comment),
  framing as tooling contribution not disqualification.
* `audit/methodology.md` — Standalone methodology: canonical BPB definition,
  bug-in-code (correct vs buggy), sliding-window scored-token tiling
  derivation, scope/non-claims section, tool reference.
* `audit/results.md` — Full per-PR inspection notes + summary table (verified
  correct-LUT only) + analysis of what the obfuscated entries imply.
* Commit: `2af49bb audit: Phase 3 draft writeup + methodology + results`.

### Push
* `git push origin main` succeeded; remote at `2af49bb`.

## Key results

* **Verified correct-LUT frontier: PR #1735 (AjAnubolu, "SP8192 + Parallel
  Pre-Quant TTT") at canonical BPB 1.04290.** Lead of 0.02131 over PR #1779.
* **All 3 lowest-reported BPBs are obfuscated** (#1785, #1758, #1738) —
  cannot be statically verified. Only sub-1.05 obfuscated submission with a
  known LUT classification (yahya010's PR #1734) was buggy (corrected to
  ~1.1873).
* **6 of top 10 are CORRECT** (canonical reported BPBs); 4 are OBFUSCATED.
  No PRs in the top 10 were classified BUGGY (de-obfuscated) — the bug is
  hidden behind code obfuscation in the modern leaderboard.
* SP8192 fineweb val inflation ratio is exactly **1.16713**
  (canonical=151,080,891 bytes / buggy=176,332,748 bytes), reproducible by
  the published tool.

## Blockers needing your review

1. **Inflation ratio 1.1671 vs yahya's 1.1746.** The audit doc's "all-token
   approximation" of 1.1671 matches my tool's output exactly. yahya's
   reported 1.1746 is 0.75% higher. The audit doc attributes this to
   "sliding-window subset selection," but my tool *does* use the
   sliding-window subset (boundary-masked, scored-token-only). I documented
   the discrepancy in `audit/methodology.md` §3 by reporting the exact tool
   numbers; the audit conclusions don't change either way (every BUGGY-line
   PR still inflates by ~17%). Worth a sanity check before publishing.
2. **OBFUSCATED entries in the top 3.** `audit/results.md` is careful not
   to assert these are buggy — only that they cannot be statically verified.
   Your call whether to push harder on the framing ("the only sub-1.05
   submission with a known LUT was buggy" pattern) or stay maximally
   neutral.
3. **PR #1735 lead is large (0.021 BPB).** The "True Top 5" table has #1735
   at 1.04290 with the next-best at 1.06421. This is a substantial gap. We
   have no independent reproduction; the canonical claim rests on the
   author's reported number being correct. The methodology doc notes this
   explicitly; you may want to consider whether to caveat #1735 more
   strongly given how much it stands out.
4. **Submission readiness.** This work is *not* yet packaged as a PR to
   `openai/parameter-golf`. The `audit/writeup.md` is structured as a PR
   body, but the actual `records/track_non_record_16mb/` placement,
   submission.json, and PR creation are pending your review.

## Git state

* `agent-pgolf` HEAD: `2af49bb` (pushed to origin/main).
* `parameter-golf` HEAD: `6927947` on branch `pr-1727` (restored).
* Local branches in `parameter-golf` for each fetched PR:
  `pr-1735, pr-1736, pr-1738, pr-1756, pr-1758, pr-1769, pr-1771, pr-1779,
  pr-1784, pr-1785` (kept for reproducibility; no rebase needed).
* Untracked in `agent-pgolf`: `.claude/settings.json.backup`,
  `autonomous_run.log` (both pre-existing from earlier session).
* Modified in `agent-pgolf`: `.claude/settings.json` (pre-existing).

## Commit hashes

```
2af49bb  audit: Phase 3 draft writeup + methodology + results
b784d49  audit: Phase 2 results — leaderboard inspection across top-10 PRs
ffa66e5  tool: canonical_rescore.py for BPB byte-count audit
21455f1  exp_001: analysis.md — hardware parity confirmed
```

All four commits are on `origin/main`.

## Files added this session

```
experiments/exp_001/analysis.md
scripts/canonical_rescore.py
tests/test_canonical_rescore.py
tests/fixtures/buggy_train_gpt.py
audit/run_audit.sh
audit/run_audit.log
audit/per_pr/{1735,1736,1738,1756,1758,1769,1771,1779,1784,1785}.json
audit/corrected_leaderboard.md
audit/writeup.md
audit/methodology.md
audit/results.md
session_summary.md            ← this file
```

## Did NOT do (per prompt directive)

* No torchrun / training experiments.
* No pod spin-up.
* No edits to `knowledge/lessons_learned.md` or
  `knowledge/measurement_integrity_audit.md`.
* No PR submission to upstream (writeup is drafted in `audit/writeup.md` but
  not packaged for `track_non_record_16mb/`).
