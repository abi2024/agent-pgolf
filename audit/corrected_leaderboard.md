# Corrected Leaderboard — Top-10 Open PRs (April 2026)

**Methodology.** For each of the 10 open PRs with the lowest reported `val_bpb`,
we fetched the PR branch from `openai/parameter-golf` and ran
`scripts/canonical_rescore.py` against the `train_gpt.py` under the PR's
`records/track_10min_16mb/<dated-dir>/`. The tool statically inspects
`build_sentencepiece_luts` for the buggy `+1` pattern from the #1698 lineage
(yahya010, PR #1734 self-closure 2026-04-19) and computes the canonical and
buggy byte totals over the exact sliding-window scored-token subset
(`seq_len=2048`, `stride=64`) of the SP8192 fineweb val shard. No model is
loaded; the correction factor is `inferred_canonical_bpb = reported_bpb ×
(buggy_bytes / canonical_bytes)` for BUGGY scripts. The hardware-parity anchor
is exp_001 (PR #1727 reproduction, seed 1337, val_bpb=1.07431, within
tolerance of the reported 3-seed mean of 1.07217). Threshold for "True Top"
inclusion is `inferred_canonical_bpb ≤ 1.0738` (one record-class margin under
the merged-SOTA reference).

## Full audited table

Sorted by reported BPB (best first). "Inferred canonical BPB" is the buggy
value × `1.1671` for BUGGY scripts; for CORRECT scripts the reported value
already is canonical; for OBFUSCATED scripts the LUT cannot be verified
without executing the encoded blob.

| Rank | PR | Author | Reported BPB | LUT Status | Inferred Canonical BPB | Passes ≤1.0738? |
|------|----|--------|-------------|-----------|------------------------|-----------------|
| 1 | #1785 | OE-GOD | 1.01925 | ⚠ OBFUSCATED | unverified | ? |
| 2 | #1758 | kilojoules | 1.02840 | ⚠ OBFUSCATED | unverified | ? |
| 3 | #1738 | alertcat | 1.03540 | ⚠ OBFUSCATED | unverified | ? |
| 4 | #1735 | AjAnubolu | 1.04290 | ✅ CORRECT | 1.04290 | **Yes** |
| 5 | #1779 | leon2k2k2k | 1.06421 | ✅ CORRECT | 1.06421 | **Yes** |
| 6 | #1769 | dexhunter | 1.06453 | ✅ CORRECT | 1.06453 | **Yes** |
| 7 | #1756 | romeerp | 1.06505 | ✅ CORRECT | 1.06505 | **Yes** |
| 8 | #1771 | bigbag | 1.06513 | ⚠ OBFUSCATED | unverified | ? |
| 9 | #1736 | dexhunter | 1.06549 | ✅ CORRECT | 1.06549 | **Yes** |
| 10 | #1784 | renqianluo | 1.07081 | ✅ CORRECT | 1.07081 | **Yes** |
| anchor | #1727 | yahya010 | 1.07217 | ✅ CORRECT (verified) | 1.07217 | **Yes** |

## True Top 5 (verified correct-LUT only)

After excluding PRs whose `train_gpt.py` is wrapped in
`lzma.decompress(base64.b85decode(...))` and therefore cannot be statically
audited, the verified frontier is:

| Rank | PR | Author | Canonical BPB |
|------|----|--------|---------------|
| 1 | #1735 | AjAnubolu | **1.04290** |
| 2 | #1779 | leon2k2k2k | 1.06421 |
| 3 | #1769 | dexhunter | 1.06453 |
| 4 | #1756 | romeerp | 1.06505 |
| 5 | #1736 | dexhunter | 1.06549 |

PR #1735 (AjAnubolu, "SP8192 + Parallel Pre-Quant TTT") leads the verified
correct-LUT line by ~0.022 BPB over the next-best PR (#1779) — a substantial
margin that would clear the merged-SOTA bar by ~0.031 BPB. PRs #1727 and
#1784 (verified correct-LUT, mid-1.07 range) are within seed-noise of each
other and represent the previous-frontier QK-Gain stack.

## Caveats

The four OBFUSCATED PRs (#1785, #1758, #1738, #1771) report BPB values
spanning the three-best (#1785, #1758, #1738) and one mid-pack
(#1771). For them we have no way to verify whether the LUT is canonical or
inflated without running the encoded blob in a sandbox; the static tool
returns `NEEDS_MANUAL_REVIEW`-equivalent ("OBFUSCATED — cannot verify
statically"). yahya010's self-closure of PR #1734 establishes that at least
one obfuscated, sub-1.05 submission (his own #1734 at 1.0108) was actually a
buggy-LUT canonical ~1.18; this is the strongest reason to treat the three
sub-1.05 obfuscated entries here as unverified rather than as the true top.

## Per-PR JSON

Raw tool output for each PR is in `audit/per_pr/<pr>.json`. The driver
script is `audit/run_audit.sh`.
