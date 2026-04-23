# Measurement Integrity Note: BPB Byte-Count Audit of the #1698 Lineage

**Type**: Non-record PR — tooling + methodology contribution.
**Track**: `track_non_record_16mb`
**Authors of this PR**: (filer)
**Acknowledgement**: This work systematizes the byte-count discrepancy that
**yahya010** discovered and self-reported in PR #1734 closure on 2026-04-19.

---

## TL;DR

* yahya010 self-reported in PR #1734 closure that
  `build_sentencepiece_luts` in the #1698 lineage bakes a `+1` into the byte
  LUT for leading-space tokens, while `eval_val_sliding` then adds the same
  `+1` again, double-counting.
* That double-count inflates the byte denominator of BPB by **+16.71%** on the
  full SP8192 fineweb val shard (151,080,891 canonical vs 176,332,748 buggy
  bytes — exact tool output, scored over 633,420 sliding windows of
  `seq_len=2048, stride=64`). Reported buggy BPBs translate to canonical BPBs
  via `canonical = reported × 1.1671`.
* We publish `scripts/canonical_rescore.py`: a static LUT inspection +
  byte-count tool that requires no GPU, no checkpoint, and no reproduction
  run. Drop in any `train_gpt.py` and it returns the LUT classification, the
  exact inflation ratio over the actual scored-token subset, and the
  inferred canonical BPB.
* Applying the tool to the **top 10 open PRs by reported BPB** as of
  2026-04-23: 6 are CORRECT (canonical), 4 are OBFUSCATED
  (`lzma.decompress(base64.b85decode(...))` — LUT cannot be verified
  statically). The verified correct-LUT frontier is **PR #1735** (AjAnubolu,
  1.04290), followed by the cluster of 1.064-1.071 PRs anchored by the
  reproducible PR #1727 stack.

This is a **tooling and methodology contribution**, not a disqualification
petition. The intent is to give future submitters a one-command self-check
("did I inherit the #1698 LUT bug?") and to help reviewers separate
verified-canonical results from unverified ones.

---

## The bug, in one paragraph

Canonical SentencePiece BPB attributes one byte to the leading space of a
piece beginning with the `▁` marker, but only when the previous token is
*not* a boundary token (UNK / control / unused). The #1700-line
implementation (PR #1727 line 196) writes `base_bytes_np[token_id] =
len(piece.encode("utf-8"))` after stripping the `▁`, then in
`eval_val_sliding` adds `(has_leading_space[y] & ~is_boundary[x_prev])`. The
#1698 line writes `base_bytes_np[token_id] = len(piece.encode("utf-8")) + 1`
inside the leading-space branch — so the `+1` is *already* baked into the
LUT — and then *also* adds the boundary-gated `+1` at eval time. Each
leading-space scored token is therefore credited with one extra byte beyond
canonical. On SP8192 fineweb val, leading-space tokens account for 62.3% of
all val tokens, so the byte denominator is inflated by ~16.71% and the
reported BPB is correspondingly deflated.

Why we can correct without re-running the model: the cross-entropy
numerator is independent of the LUT. `bpb = (loss × N_tokens) / (ln(2) ×
byte_count)`. Multiply both sides by the `buggy_bytes / canonical_bytes`
ratio and you recover the canonical BPB from the buggy reported value.

---

## Methodology (full version: `audit/methodology.md`)

For each PR:

1. `git fetch upstream pull/<N>/head:pr-<N>` and check it out.
2. Find the `train_gpt.py` under `records/track_10min_16mb/<latest-dated-dir>/`.
3. Run `scripts/canonical_rescore.py` against that script + the SP8192
   tokenizer + the fineweb_val shard.
4. Tool returns:
   * `lut_status`: `CORRECT` / `BUGGY` / `OBFUSCATED` / `UNKNOWN`
   * `inflation_ratio`: `1.0` for CORRECT, computed buggy/canonical for
     BUGGY (~`1.1671` on SP8192), `null` otherwise.
   * `inferred_canonical_bpb`: `reported_bpb × inflation_ratio` if both are
     known; `null` otherwise.
   * `passes_merged_sota_threshold`: boolean, threshold default 1.0738 (one
     record-class margin under the merged-SOTA reference).

Hardware parity is anchored by exp_001: a verbatim PR #1727 reproduction on
8×H100 SXM, seed 1337, val_bpb = 1.07431, within 0.00214 of the reported
3-seed mean of 1.07217 — confirming our toolchain (torch 2.8.0+cu128) sees
the same numbers as upstream and that the audit's analytic correction can
be trusted. See `experiments/exp_001/analysis.md`.

---

## Tool usage

```bash
python scripts/canonical_rescore.py \
    --train-script <path-to-PR-train_gpt.py> \
    --tokenizer    data/tokenizers/fineweb_8192_bpe.model \
    --val-data     'data/datasets/fineweb10B_sp8192/fineweb_val_*.bin' \
    --reported-bpb 1.02840 \
    --pr-number    1758
```

Output (JSON to stdout / `--output`):

```json
{
  "pr_number": 1758,
  "script_path": "...",
  "lut_status": "OBFUSCATED",
  "inflation_ratio": null,
  "inferred_canonical_bpb": null,
  "passes_merged_sota_threshold": null,
  "notes": "Code is lzma/b85-obfuscated; LUT cannot be verified statically."
}
```

For a CORRECT script the output looks like:

```json
{
  "pr_number": 1735,
  "lut_status": "CORRECT",
  "inflation_ratio": 1.0,
  "inferred_canonical_bpb": 1.0429,
  "passes_merged_sota_threshold": true
}
```

For a BUGGY script the output reports the exact byte counts, the inflation
ratio, and the corrected BPB.

Tests covering CORRECT (PR #1727), BUGGY (synthetic fixture), OBFUSCATED
(both inline-`exec` and `runpy`-style wrappers), UNKNOWN, and the full
end-to-end rescore are in `tests/test_canonical_rescore.py` (10 tests, all
green).

---

## Results (full version: `audit/results.md` and `audit/corrected_leaderboard.md`)

| Rank | PR | Author | Reported | LUT | Canonical |
|------|----|--------|---------|-----|-----------|
| 1 | #1785 | OE-GOD | 1.01925 | OBFUSCATED | unverified |
| 2 | #1758 | kilojoules | 1.02840 | OBFUSCATED | unverified |
| 3 | #1738 | alertcat | 1.03540 | OBFUSCATED | unverified |
| 4 | #1735 | AjAnubolu | 1.04290 | ✅ CORRECT | **1.04290** |
| 5 | #1779 | leon2k2k2k | 1.06421 | ✅ CORRECT | 1.06421 |
| 6 | #1769 | dexhunter | 1.06453 | ✅ CORRECT | 1.06453 |
| 7 | #1756 | romeerp | 1.06505 | ✅ CORRECT | 1.06505 |
| 8 | #1771 | bigbag | 1.06513 | OBFUSCATED | unverified |
| 9 | #1736 | dexhunter | 1.06549 | ✅ CORRECT | 1.06549 |
| 10 | #1784 | renqianluo | 1.07081 | ✅ CORRECT | 1.07081 |

**Verified correct-LUT frontier: PR #1735 (AjAnubolu) at 1.04290 BPB**, with
PR #1779 the runner-up at 1.06421.

The four OBFUSCATED PRs occupy the top three reported slots (#1785, #1758,
#1738) and one mid-pack slot (#1771). yahya010's own PR #1734 closure
established that at least one obfuscated submission with a sub-1.05
reported BPB was actually a buggy-LUT canonical of ~1.18; the same correction
applied to #1785 (1.01925 → ~1.190), #1758 (1.02840 → ~1.200), and #1738
(1.03540 → ~1.208) **if** they share the bug. We do not assert they do —
only that the static tool cannot tell us until they are de-obfuscated.

---

## Attribution

Verbatim from the PR #1734 closure comment by **yahya010**, 2026-04-19:

> "build_sentencepiece_luts bakes +1 into LUT for leading-space tokens,
> then eval_val_sliding adds +1 again at eval. Buggy code overcounts bytes
> by 17.46% vs canonical sp.decode_ids().encode('utf-8'). Reported
> val_bpb=1.0108 corresponds to canonical val_bpb≈1.1873..."

This audit replicates yahya010's finding using a static, GPU-free
inspection method, extends it to the full set of currently-open top PRs,
and publishes the tool so future submitters can self-verify before filing.

---

## Framing

We do not request any PR be re-classified or closed. The competition
maintainers and authors are best positioned to decide whether obfuscated
submissions are eligible for record consideration. Our contribution is:

1. **A reusable tool** (`scripts/canonical_rescore.py`) that any submitter
   can run before filing — including a regex check that catches the buggy
   `+1` pattern in seconds.
2. **A clean methodology document** (`audit/methodology.md`) defining
   canonical BPB rigorously enough that disagreements about "what is
   canonical" can be resolved by code rather than discussion.
3. **A snapshot leaderboard** (`audit/corrected_leaderboard.md`,
   `audit/results.md`) that distinguishes *verified* canonical BPB from
   *reported* BPB, so reviewers do not have to re-derive that distinction
   per-PR.

The verified frontier (PR #1735 at canonical 1.04290, leading the cluster
around 1.064-1.071) tells a coherent story about where parameter golf
actually stands today on the correct-LUT measurement.
