# Session Summary — 2026-04-23 Autonomous Block + 2026-04-24 Polish + 2026-04-24 Three-Variant Classifier Extension

3-phase autonomous block: write exp_001 analysis, build canonical_rescore tool,
run audit on top-10 PRs, draft three audit docs, push to origin.
Follow-up polish pass on 2026-04-24: three-commit cleanup addressing the
ratio discrepancy, tool documentation, and writeup tone.
Follow-up extension block on 2026-04-24: extend the LUT classifier from
single-bug to three-variant detection (leading_space_plus_one,
byte_token_wrong_size, missing_is_unused), re-audit the top 10 PRs with
the extended classifier, update all docs. **Key finding: zero top-10 PRs
changed classification under v2.** This strengthens the top-10
assessment.

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

## Polish pass (2026-04-24)

Three commits addressing the 2026-04-23 blockers:

### Pass 1: empirical resolution of the ratio discrepancy
* Added `--scoring-mode` flag to `scripts/canonical_rescore.py` with three
  variants: `sliding-window-boundary-masked` (default, what PR #1727's
  `eval_val_sliding` computes), `all-tokens-boundary-masked` (flat 1:N
  slice, same mask), `all-tokens-no-mask` (flat 1:N slice, boundary mask
  replaced with all-ones).
* **Finding: all three variants give 1.1671 on SP8192 fineweb val.**
  The sliding-window tile covers the full 1:N span, and
  `is_boundary[x_prev]` is identically zero over this stream (no
  control/unknown/unused tokens appear as predecessors). So scoring
  strategy is **not** the source of the 0.75% gap to yahya's 1.1746.
* **Root cause identified:** yahya's PR #1734 `train_gdn_7k.py` has a
  structurally different LUT — byte tokens (`sp.is_byte`) are sized by
  `len(piece.encode("utf-8"))` (6 bytes for `"<0x00>"`) instead of 1, and
  `sp.is_unused` tokens are not treated as boundary. Running yahya's
  exact LUT on the same val stream gives ratio 1.1770 (within 0.2% of
  the quoted 1.1746; the remaining residual is plausibly val-shard or
  rounding).
* 4 new tests (total 14 in `test_canonical_rescore.py`, 56 overall).
* Methodology doc has a new §4 "Inflation ratio is sensitive to scoring
  strategy" documenting the three variants, the three-way convergence,
  and the yahya010 residual-gap explanation.
* Commit: `b2dcc16 tool: add --scoring-mode flag with three variants; document ratio sensitivity`

### Pass 2: tool documentation
* Module docstring in `scripts/canonical_rescore.py` expanded with
  what-it-does / does-NOT-do / algorithm / example blocks.
* Docstrings added to `classify_lut`, `build_canonical_luts`,
  `load_val_tokens`, `rescore` (Args/Returns/Gotchas format).
* All CLI flags now carry explanatory `--help` strings.
* New `scripts/README_canonical_rescore.md`: purpose, when-to-use,
  when-NOT-to-use, installation, CLI reference, interpretation guide for
  JSON output (what to conclude / what NOT to conclude), limitations,
  test pointer.
* Commit: `c4de2f9 docs: canonical_rescore README + docstrings + CLI help polish`

### Pass 3: writeup polish
* `audit/writeup.md` TL;DR surfaces both 1.1671 (tool default) and
  yahya's 1.1746 and attributes the gap to LUT-construction differences.
* New "Scope and limitations" section spells out what LUT-verified
  CORRECT does and does not imply, and flags PR #1735's 0.021 BPB lead
  as reproduction-pending.
* Results table now has an explicit "LUT-verified" yes/no column with
  footnote. Emoji/checkmark decorations stripped for neutral tone.
* `audit/corrected_leaderboard.md` methodology paragraph mentions both
  ratios up-front; scope-caveat callout added; Caveats section explicitly
  rejects asserting obfuscated PRs are buggy.
* `audit/results.md` OBFUSCATED per-PR entries labeled "Conditional
  arithmetic (not a claim)" to make if-buggy-then-X hypothetical;
  #1735 entry carries the reproduction-pending caveat inline.
* Commit: `4ed570f audit: writeup polish - both ratios documented, scope caveats added, tone neutralized`

## Open items (still unblocked)

1. **Submission readiness.** This work is *not* yet packaged as a PR to
   `openai/parameter-golf`. The `audit/writeup.md` is structured as a PR
   body, but the actual `records/track_non_record_16mb/` placement,
   submission.json, and PR creation are pending user review.

## Git state

* `agent-pgolf` HEAD: `4ed570f` (after polish pass; pending push to origin).
* `parameter-golf` HEAD: `6927947` on branch `pr-1727` (restored).
* Local branches in `parameter-golf` for each fetched PR:
  `pr-1735, pr-1736, pr-1738, pr-1756, pr-1758, pr-1769, pr-1771, pr-1779,
  pr-1784, pr-1785` (kept for reproducibility; no rebase needed).
* Untracked in `agent-pgolf`: `.claude/settings.json.backup`,
  `autonomous_run.log` (both pre-existing from earlier session).
* Modified in `agent-pgolf`: `.claude/settings.json` (pre-existing).

## Commit hashes

```
4ed570f  audit: writeup polish - both ratios documented, scope caveats added, tone neutralized
c4de2f9  docs: canonical_rescore README + docstrings + CLI help polish
b2dcc16  tool: add --scoring-mode flag with three variants; document ratio sensitivity
2af49bb  audit: Phase 3 draft writeup + methodology + results
b784d49  audit: Phase 2 results — leaderboard inspection across top-10 PRs
ffa66e5  tool: canonical_rescore.py for BPB byte-count audit
21455f1  exp_001: analysis.md — hardware parity confirmed
```

Commits `21455f1..2af49bb` (4) are on `origin/main` from the autonomous
block. Commits `b2dcc16..4ed570f` (3) from the polish pass are local and
pending push.

## Files added this session

Autonomous block (2026-04-23):
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

Polish pass (2026-04-24):
```
scripts/README_canonical_rescore.md   ← new
scripts/canonical_rescore.py          ← +docstrings, +--scoring-mode, +CLI help
tests/test_canonical_rescore.py       ← +4 scoring-mode tests (14 total)
audit/methodology.md                  ← +§4 ratio sensitivity section
audit/writeup.md                      ← TL;DR + scope + attribution revised
audit/corrected_leaderboard.md        ← LUT-verified column + neutral caveats
audit/results.md                      ← conditional arithmetic language
```

## Three-variant classifier extension (2026-04-24)

### Pass A — extend classifier
* `scripts/canonical_rescore.py` gains `classify_lut_detailed(src)`
  which returns `(status, deviations)`. Three new property detectors:
  * P1 `leading_space_plus_one` — widened regex to accept
    `piece[1:].encode("utf-8")` in addition to `piece.encode("utf-8")`.
  * P2 `byte_token_wrong_size` — locates `if sp.is_byte(t):` branch and
    checks the assignment is literal `1`.
  * P3 `missing_is_unused` — scans `is_control(` call sites and verifies
    the surrounding window contains both `is_unknown(` and `is_unused(`.
* New JSON fields: `lut_bug_detections`, `detected_bugs_description`,
  `inflation_ratio_includes`. Multi-bug PRs get a conservative-ratio
  warning in `notes`.
* Three new fixtures under `tests/fixtures/`: `buggy_byte_token.py`,
  `buggy_missing_is_unused.py`, `buggy_triple.py`.
* Six new tests in `test_canonical_rescore.py` (14 → 20).
* Commit: `0287642 tool: extend LUT classifier to detect three bug variants`.

### Pass B — re-audit top 10 PRs
* New driver `audit/run_audit_v2.sh` writes to `audit/per_pr_v2/` (v1
  outputs preserved in `audit/per_pr/`).
* Result: **0 of 10 PRs changed classification**. Same 6 CORRECT + 4
  OBFUSCATED split as v1.
* Spot-check control: yahya010's PR #1734 train_gdn_7k.py correctly
  flagged as BUGGY with `["leading_space_plus_one", "missing_is_unused"]`
  (P2 returns INDETERMINATE because yahya's code has no sp.is_byte
  branch — byte tokens fall through the default path; this is the
  designed DEVIATES-vs-INDETERMINATE behavior).
* Changelog: `audit/changelog_v2.md`.
* Commit: `12c340f audit: re-audit v2 with extended classifier — no top-10 PR changed classification`.

### Pass C — docs
* `audit/methodology.md` new §5 documenting the three properties,
  detector design, and DEVIATES-vs-INDETERMINATE rule; old §5/§6/§7 → §6/§7/§8.
* `audit/writeup.md` TL;DR + tool section + attribution updated.
* `audit/results.md` and `audit/corrected_leaderboard.md` annotated
  with v1/v2 agreement footnote.
* `audit/reviewer_readiness.md` (new, committed copy of /tmp version).
* `scripts/README_canonical_rescore.md` new "Three-variant classifier"
  section + JSON schema additions + multi-bug invocation example.
* Commit: `9411b87 docs: update writeup, methodology, results, README for three-bug classifier`.

## Test count

62 tests pass (42 pre-existing + 20 in `test_canonical_rescore.py`
after the three-variant extension). Run with `python -m pytest tests/ -q`.

## Did NOT do (per prompt directive)

* No torchrun / training experiments.
* No pod spin-up.
* No edits to `knowledge/lessons_learned.md` or
  `knowledge/measurement_integrity_audit.md`.
* No PR submission to upstream (writeup is drafted in `audit/writeup.md` but
  not packaged for `track_non_record_16mb/`).
