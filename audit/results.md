# Audit Results — Top-10 Open PRs (snapshot 2026-04-23)

This is the per-PR write-up backing `audit/corrected_leaderboard.md`. For
each PR we record what the static tool found, what the inferred canonical
BPB is (or why we could not compute one), and any inspection notes. The
tool's raw JSON for each PR is in `audit/per_pr/<pr>.json`.

## Inputs

* **Snapshot date**: 2026-04-23 (leaderboard refreshed via
  `python scripts/pgolf.py leaderboard fetch`).
* **PR set**: top-10 open PRs sorted by reported `val_bpb` ascending.
* **Tool**: `scripts/canonical_rescore.py` (commit visible in
  `git log -- scripts/canonical_rescore.py`).
* **Hardware-parity anchor**: `exp_001/analysis.md` (PR #1727
  reproduction, seed 1337, val_bpb=1.07431, within +0.00214 of the
  reported 3-seed mean of 1.07217).
* **Inflation ratio on SP8192 fineweb val**: 1.1671413 (canonical
  151,080,891 bytes vs buggy 176,332,748 bytes; 25,251,857 leading-space
  tokens; 633,420 scored windows of `seq_len=2048, stride=64`).
* **"Pass merged-SOTA" threshold**: inferred canonical BPB ≤ 1.0738.

## Verified correct-LUT — True Top 5

These six PRs (5 + the #1727 anchor) are statically confirmed to use the
canonical `len(piece.encode("utf-8"))` LUT. Their reported BPBs are
canonical and require no correction.

| Rank | PR | Author | Canonical BPB | Notes |
|------|----|--------|---------------|-------|
| 1 | #1735 | AjAnubolu | **1.04290** | "SP8192 + Parallel Pre-Quant TTT" — clean lead |
| 2 | #1779 | leon2k2k2k | 1.06421 | "SP8192 + CaseOps + GatedAttn + QuantGate + Loop4-5 + PhasedTTT + RecurAlpha" |
| 3 | #1769 | dexhunter | 1.06453 | Same family, MLPClip12 variant (5-seed mean) |
| 4 | #1756 | romeerp | 1.06505 | "CaseOps + Recurrence Depth Curriculum" |
| 5 | #1736 | dexhunter | 1.06549 | Same family, earlier variant |

PR #1727 (yahya010, 1.07217) and PR #1784 (renqianluo, 1.07081) are
verified correct but rank below the True Top 5 by reported BPB.

## Per-PR inspection notes

### #1785 — OE-GOD — reported 1.01925 — OBFUSCATED
* Script dir: `records/track_10min_16mb/2026-04-23_SP4096_PPM_AdaptiveMix/`
* Two-line `train_gpt.py`: `import lzma as L,base64 as B` followed by
  `exec(L.decompress(B.b85decode("..."))`.
* LUT cannot be verified statically. `inferred_canonical_bpb` = unverified.
* If it shares the #1698 bug, the correction would produce a canonical
  BPB of approximately `1.01925 × 1.1671 ≈ 1.1896` — close to yahya010's
  self-disclosed corrected value of 1.1873 for PR #1734. We do not assert
  the bug is present.

### #1758 — kilojoules — reported 1.02840 — OBFUSCATED
* Script dir: `records/track_10min_16mb/2026-04-20_SP8192_PreQuantTTT_Unfrozen_LR1e3/`
* Same `lzma.decompress(b85decode(...))` pattern as #1785.
* The PR title declares this is "PR #1738 + PreQuant TTT LR=1e-3". PR
  #1738 is itself OBFUSCATED (below).
* `inferred_canonical_bpb` = unverified. If buggy, the correction would
  give `1.02840 × 1.1671 ≈ 1.2003`.

### #1738 — alertcat — reported 1.03540 — OBFUSCATED
* Script dir: `records/track_10min_16mb/2026-04-19_SP8192_PreQuantTTT_CaseOps_V15/`
* Same obfuscation pattern.
* The PR title declares this is "PR #1735 + CaseOps Tokenizer V15". PR
  #1735 is itself CORRECT (below); the obfuscation here therefore changed
  more than just the tokenizer, and we cannot tell what.
* `inferred_canonical_bpb` = unverified. If buggy: `≈1.2084`.

### #1735 — AjAnubolu — reported 1.04290 — CORRECT ✅
* Script dir: `records/track_10min_16mb/2026-04-18_SP8192_ParallelPreQuantTTT/`
* `build_sentencepiece_luts` is the canonical version (no `+1`).
* This is the **verified correct-LUT frontier** at canonical BPB 1.04290.
* Threshold check: 1.04290 ≤ 1.0738 ✅ — would clear the merged-SOTA
  reference by 0.031 if held against the same 1.0738 threshold yahya's
  closure note implied.

### #1779 — leon2k2k2k — reported 1.06421 — CORRECT ✅
* Script dir: `records/track_10min_16mb/2026-04-23_SP8192_CaseOps_GatedAttn_QuantGate_Loop45_PhasedTTT_RecurAlpha/`
* CaseOps + GatedAttn + Loop4-5 + Phased TTT + Recurrent Alpha stack.
* Canonical BPB 1.06421.

### #1769 — dexhunter — reported 1.06453 — CORRECT ✅
* Script dir: `records/track_10min_16mb/2026-04-22_SP8192_CaseOps_GatedAttn_QuantGate_Loop45_PhasedTTT_MLPClip12/`
* 5-seed mean reported. Canonical BPB 1.06453.

### #1756 — romeerp — reported 1.06505 — CORRECT ✅
* Script dir: `records/track_10min_16mb/2026-04-20_SP8192_CaseOps_GatedAttn_QuantGate_Loop134_Curriculum_PhasedTTT/`
* CaseOps Tokenizer + Recurrence Depth Curriculum. Canonical BPB 1.06505.

### #1771 — bigbag — reported 1.06513 — OBFUSCATED
* Script dir: `records/track_10min_16mb/2026-04-22_SP8192_CaseOps_V13_L2_LoRA_TTT/`
* Wrapper variant: `_c=lzma.decompress(base64.b85decode("..."))` followed by
  `tempfile`/`runpy` execution. Detector handles both inline-`exec` and
  this `runpy` form.
* `inferred_canonical_bpb` = unverified. If buggy: `≈1.2434`. Given the
  reported BPB is at the top of the 1.064-1.066 cluster of correct-LUT
  PRs, the bug-free explanation is plausible but unverifiable here.

### #1736 — dexhunter — reported 1.06549 — CORRECT ✅
* Script dir: `records/track_10min_16mb/2026-04-19_SP8192_CaseOps_GatedAttn_QuantGate_Loop45_PhasedTTT/`
* Same family as #1769 / #1779. Canonical BPB 1.06549.

### #1784 — renqianluo — reported 1.07081 — CORRECT ✅
* Script dir: `records/track_10min_16mb/2026-04-23_GatedAttn_AlphaLoRA144_WarmStart_1.07081/`
* "GatedAttn + Alpha-Scaled LoRA + Warm-start A + WD 1.0" — 3-seed mean.
* Canonical BPB 1.07081.

## Summary table (verified correct-LUT only)

Reproduced from `audit/corrected_leaderboard.md` for convenience. Sorted
by canonical BPB ascending. Only includes PRs whose `train_gpt.py` was
statically classified as CORRECT.

| Rank | PR | Author | Canonical BPB | Δ to next |
|------|----|--------|---------------|-----------|
| 1 | #1735 | AjAnubolu | 1.04290 | +0.02131 |
| 2 | #1779 | leon2k2k2k | 1.06421 | +0.00032 |
| 3 | #1769 | dexhunter | 1.06453 | +0.00052 |
| 4 | #1756 | romeerp | 1.06505 | +0.00008 |
| 5 | #1736 | dexhunter | 1.06549 | +0.00532 |
| (anchor) | #1727 | yahya010 | 1.07217 | +0.00136 (above #1784) |
| 6 | #1784 | renqianluo | 1.07081 | — |

PR #1735's canonical BPB lead of 0.02131 over the next-best verified
result is a substantial gap. Two reads are consistent with the data:
either AjAnubolu's pre-quant TTT variant is genuinely a step-change over
the 1.064-1.071 cluster, or the 3-seed mean has unusually low variance
relative to the rest. Without re-running other PRs we cannot
disambiguate, but the static check is unambiguous: PR #1735 is the
verified correct-LUT lead as of 2026-04-23.

## What the obfuscated entries imply

The four OBFUSCATED entries (#1785, #1758, #1738, #1771) include the
three lowest reported BPBs in the leaderboard. yahya010's self-closure
of PR #1734 (also obfuscated, reported 1.0108, self-confirmed canonical
~1.1873) is the only data point we have on what's behind a sub-1.05
obfuscated submission. We do not extrapolate from one self-confirmed
case, but we do flag the pattern: **every sub-1.05 entry on the current
leaderboard is in obfuscated code**, and the only sub-1.05 entry with a
known LUT classification was buggy.

The verified correct-LUT frontier sits at 1.04290 (PR #1735) — well below
the 1.0738 threshold but well above the obfuscated entries.
