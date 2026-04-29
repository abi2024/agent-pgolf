# Reviewer readiness — BPB byte-count audit

**The audit is ready for external review.**

Three cleanup commits on 2026-04-24 brought the tool, tests, and writeup
to a state where a skeptical reviewer can validate the substantive claims
in ~10 minutes without running training or touching a GPU. A follow-up
2026-04-24 block extended the classifier from single-bug to three-variant
detection and re-ran the audit — results unchanged (same 6 CORRECT, 4
OBFUSCATED, 0 BUGGY split), which strengthens the top-10 assessment.

---

## What a reviewer can verify in 10 minutes

1. **Tool matches the claim.** Run
   `python -m pytest tests/test_canonical_rescore.py -q` — 20 tests green,
   covering LUT classification (CORRECT/BUGGY/OBFUSCATED/UNKNOWN), the
   three-variant deviation detectors (per-bug single-deviation fixtures
   and the triple-bug fixture), regressions against PR #1727,
   synthetic byte-count math, real-data inflation ratio, all three
   `--scoring-mode` variants, and end-to-end rescore for both a CORRECT
   script (PR #1727) and a BUGGY fixture (synthetic +1 insert).
2. **Reproduce the 1.1671 inflation ratio.** Run
   `python scripts/canonical_rescore.py --train-script <any CORRECT train_gpt.py> --tokenizer <SP8192.model> --val-data <fineweb_val>` —
   `canonical_byte_count` = 151,080,891 and `buggy_byte_count` = 176,332,748
   are the numbers quoted in `audit/methodology.md` §3.
3. **Reproduce the three-way scoring-mode convergence.** Same command
   with `--scoring-mode all-tokens-boundary-masked` and then
   `--scoring-mode all-tokens-no-mask` — all three yield ratio 1.16714.
   The residual-gap analysis to yahya's 1.1746 is in
   `audit/methodology.md` §4 (executive summary: yahya's #1734 LUT has
   additional byte-token and is_unused handling differences from the
   #1727-style LUT, not a scoring-strategy difference).
4. **Reproduce the three-bug classifier on yahya's PR #1734.** Point the
   tool at `records/.../train_gdn_7k.py` on the pr-1734 branch — output
   should have `lut_status: BUGGY` with
   `lut_bug_detections: ["leading_space_plus_one", "missing_is_unused"]`.
   The byte-token bug is implicit in yahya's code (no sp.is_byte branch
   at all) and the P2 detector correctly returns INDETERMINATE rather
   than DEVIATES per design — the classification is still BUGGY via the
   other two deviations. See `audit/methodology.md` §5.
5. **Audit the top-10 PRs — v1 vs v2.** `audit/run_audit.sh` (v1 driver)
   and `audit/run_audit_v2.sh` (v2 driver) document the static
   classification of each PR. Both produce 6 CORRECT, 4 OBFUSCATED, 0
   BUGGY; per-PR JSON is in `audit/per_pr/<pr>.json` (v1) and
   `audit/per_pr_v2/<pr>.json` (v2). Side-by-side diff:
   `audit/changelog_v2.md`.
6. **Cross-read the writeup.** `audit/writeup.md` has TL;DR → bug
   anatomy → methodology → scope/limitations → tool usage → results
   table → attribution → framing. Every claim that is LUT-verified is
   flagged as such; every OBFUSCATED entry is neutrally labeled
   "unverified" with conditional arithmetic clearly marked.
7. **Inspect the tool's self-documentation.**
   `scripts/README_canonical_rescore.md` carries a CLI reference, JSON
   output schema (including the new `lut_bug_detections`,
   `detected_bugs_description`, and `inflation_ratio_includes` fields),
   the three-variant classifier section, and explicit "what NOT to
   conclude" list. The module docstring and function docstrings mirror
   this.
8. **Confirm the hardware-parity anchor.** `experiments/exp_001/analysis.md`
   documents a PR #1727 reproduction on 8×H100 SXM, seed 1337, val_bpb
   1.07431 (within tolerance of the reported 3-seed mean 1.07217).
9. **Verify git hygiene.** All commits signed by the author, commit
   messages explain the why, no secrets, no force-pushes.

## What still requires deeper investigation

1. **Frontier is now PR #1795 (1.01252) since 2026-04-24, supersedes the closed #1785.** Independent reproduction of either PR #1795 or PR #1735 (the previous frontier at 1.04290) would strengthen the audit but is out of scope for the static analysis. Note also that PR #1795's mixture BPB is built on top of a canonical NN base measured at 1.09764 (matches @clarkkev's #1334 record within seed noise), so a reproduction would only need to verify the −0.07435 BPB mixture delta, not the entire pipeline. **Independent reproduction of PR #1735.** Its 0.021 BPB lead over the
   next-best LUT-verified entry is large enough to warrant a multi-seed
   reproduction before treating it as the authoritative record. The tool
   verifies the LUT only, not the full training pipeline. Flagged as
   "LUT-verified, reproduction-pending" throughout the writeup.
2. **OBFUSCATED PRs (#1785, #1758, #1738, #1771).** Verifying whether
   these inherit any of the three LUT bugs requires executing their
   `lzma.decompress(base64.b85decode(...))` blobs in a sandbox, which is
   out of scope for this audit. We state this neutrally; we do not
   accuse any obfuscated PR of being buggy.
3. **The 0.77% gap between our reproduction (1.1655) of yahya's exact
   LUT on our val and yahya's quoted 1.1746.** A previous draft of this
   audit claimed 1.1770 (see `audit/empirical_validation/run3_summary.md`);
   that has been retracted in favor of the corrected 1.1655. Runs 4 and 5
   have since bounded the gap. Run 4: ratio is invariant to eval pipeline
   windowing parameters. Run 5: of yahya's three LUT bugs, only Bug B
   (byte_token_wrong_size) produces a measurable ratio shift on SP8192,
   and that shift is *downward* (canonical 1.1671 → yahya 1.1655). No
   combination of his bugs can produce a ratio above canonical on this
   val. The gap to 1.1746 therefore cannot live in his LUT structure on
   this val; it lives in tokenizer/val state the audit cannot access
   (most likely the SP1024 tokenizer his code defaults to). Does not
   affect the audit's headline numbers (canonical 1.1671, top-10
   classifications): the structural classifier verdicts are independent
   of empirical inflation magnitudes.
4. **Broader cross-entropy correctness.** The audit assumes the
   cross-entropy numerator of BPB is correctly measured by each
   submitter. A PR that modified `eval_val_sliding` in other ways (e.g.
   changed the loss-accumulation logic, or swapped val shards) would
   appear CORRECT on this tool but could still be non-canonical. No such
   PR has been identified; we simply note the scope.
5. **Submission to upstream.** `audit/writeup.md` is structured as a PR
   body for `track_non_record_16mb`, but the actual
   `records/track_non_record_16mb/` placement + `submission.json` +
   `gh pr create` remain pending user review.

## Current state

**Recent commits (v2 classifier + re-audit block):**

```
(latest)  docs: update writeup, methodology, results, README for three-bug classifier
12c340f   audit: re-audit v2 with extended classifier — no top-10 PR changed classification
0287642   tool: extend LUT classifier to detect three bug variants
d639b45   session: 2026-04-24 polish pass summary
4ed570f   audit: writeup polish - both ratios documented, scope caveats added, tone neutralized
c4de2f9   docs: canonical_rescore README + docstrings + CLI help polish
b2dcc16   tool: add --scoring-mode flag with three variants; document ratio sensitivity
5991571   session: 2026-04-23 autonomous block summary
2af49bb   audit: Phase 3 draft writeup + methodology + results
b784d49   audit: Phase 2 results — leaderboard inspection across top-10 PRs
ffa66e5   tool: canonical_rescore.py for BPB byte-count audit
21455f1   exp_001: analysis.md — hardware parity confirmed
```

**Key files for a reviewer:**

| File | Role |
|---|---|
| `scripts/canonical_rescore.py` | The tool (static three-variant LUT audit + byte-count). |
| `scripts/README_canonical_rescore.md` | Tool user guide and output interpretation. |
| `tests/test_canonical_rescore.py` | 20 tests as proof of correctness. |
| `tests/fixtures/buggy_*.py` | Synthetic fixtures: +1 (original), byte-token, missing-is_unused, triple-bug. |
| `audit/writeup.md` | Top-level writeup for reviewer consumption. |
| `audit/methodology.md` | Canonical BPB definition, ratio math, §4 ratio sensitivity, §5 three-variant classifier. |
| `audit/results.md` | Per-PR inspection notes. |
| `audit/corrected_leaderboard.md` | Summary table with LUT-verified column. |
| `audit/changelog_v2.md` | v1 → v2 classifier diff: zero top-10 PR changed classification. |
| `audit/per_pr/*.json` | Raw v1 tool output for each audited PR. |
| `audit/per_pr_v2/*.json` | Raw v2 tool output (three-bug classifier). |
| `audit/run_audit.sh` / `audit/run_audit_v2.sh` | Reproducer drivers. |
| `experiments/exp_001/analysis.md` | Hardware-parity anchor. |
| `session_summary.md` | Session-level narrative. |

**Test suite:** 62 tests total (`python -m pytest tests/ -q`). 20 in
`test_canonical_rescore.py` — up from 14 after the three-variant
extension.

**Working tree:** `.claude/settings.json`, `.claude/settings.json.backup`,
`autonomous_run.log`, `polish_run.log`, `option_b_run.log` are
untracked/modified from harness activity and are unrelated to the audit
content.
