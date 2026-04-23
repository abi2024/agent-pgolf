# Methodology — Canonical BPB Byte-Count Audit

This document is the standalone reference for what `canonical BPB` means in
this audit, how the inflation ratio is derived, and what the sliding-window
scored-token subset is. It is the source you cite in disputes; the
implementation in `scripts/canonical_rescore.py` is its operational
realization.

---

## 1. Canonical BPB definition

```
canonical_bpb = (mean_cross_entropy_loss_in_nats / ln(2)) / canonical_bytes_per_token
```

where `canonical_bytes_per_token` is computed over the same scored-token
subset that the eval loop uses (see §3), and the per-token byte count
follows the rule:

```
bytes_for_token(y, prev_x) =
    base_bytes(y)
    + (has_leading_space(y) AND NOT is_boundary_token(prev_x))
```

with:

* `base_bytes(t) = len(sp.id_to_piece(t).strip("▁").encode("utf-8"))` for
  non-boundary, non-byte tokens.
* `base_bytes(t) = 1` for SentencePiece byte tokens
  (`sp.is_byte(t)` true).
* `base_bytes(t) = 0` for boundary tokens (`sp.is_control(t)`,
  `sp.is_unknown(t)`, `sp.is_unused(t)`).
* `has_leading_space(t) = sp.id_to_piece(t).startswith("▁")`.
* `is_boundary_token(t) = sp.is_control(t) or sp.is_unknown(t) or sp.is_unused(t)`.

This rule is what the **upstream** `eval_val_sliding` in PR #1727
(`train_gpt.py` lines 2117-2150) actually computes. The audit anchors
"canonical" to the upstream eval logic — not to a separate reference
implementation — so the corrected number is what *anyone running the
upstream eval with the corrected LUT would measure*.

---

## 2. The bug, in code

**Correct LUT** (PR #1727, `build_sentencepiece_luts`, line ~196):

```python
for token_id in range(sp_vocab_size):
    if sp.is_control(token_id) or sp.is_unknown(token_id) or sp.is_unused(token_id):
        continue
    is_boundary_token_np[token_id] = False
    if sp.is_byte(token_id):
        base_bytes_np[token_id] = 1
        continue
    piece = sp.id_to_piece(token_id)
    if piece.startswith("▁"):
        has_leading_space_np[token_id] = True
        piece = piece[1:]
    base_bytes_np[token_id] = len(piece.encode("utf-8"))   # <-- no +1
```

**Buggy LUT** (#1698 lineage; reproduced in the audit fixture
`tests/fixtures/buggy_train_gpt.py` and self-confirmed by yahya010 in PR
#1734 closure):

```python
    base_bytes_np[token_id] = len(piece.encode("utf-8")) + 1   # <-- +1 baked in
```

Both versions then run an *identical* `eval_val_sliding`, which adds
`(has_leading_space[y] & ~is_boundary_token[x_prev])`. Hence each
leading-space scored token receives one extra byte of credit beyond the
canonical eval-bytes count.

---

## 3. Sliding-window scored-token subset

`eval_val_sliding` slides a window of `seq_len=2048` tokens with a stride
of `64` over the validation tokens. Each window's "scored" range is the
last `seq_len - context_size = stride = 64` tokens, except the first window
(`ws=0`) which scores all `seq_len` tokens. The window at position `ws` is
included iff `ws + context_size < total_tokens`.

Across all included windows, the scored y-positions form a contiguous
tile of `val_tokens[1 : total_tokens + 1]`, with the corresponding x-prev
positions forming `val_tokens[0 : total_tokens]`. This means the byte sum
collapses to two array reductions:

```python
y = val_tokens[1 : total_tokens + 1]
x = val_tokens[0 : total_tokens]
canonical_bytes = base_bytes[y].sum() + (has_leading_space[y] & ~is_boundary[x]).sum()
buggy_bytes     = canonical_bytes + has_leading_space[y].sum()
inflation_ratio = buggy_bytes / canonical_bytes
```

The `+ has_leading_space[y].sum()` is exact: the buggy LUT adds `+1` for
every leading-space token regardless of whether the prev token is a
boundary. The eval still adds the gated `+1`, so the difference per
leading-space token is exactly one — accumulated across the scored y subset
gives the byte-total delta.

On SP8192 fineweb val (40,540,803 raw val tokens, 633,420 windows of
`seq_len=2048, stride=64`):

* `canonical_byte_count` = 151,080,891
* `buggy_byte_count`     = 176,332,748
* `leading_space_token_count` = 25,251,857
* `inflation_ratio` = 1.16713

These numbers are exact and reproducible by running
`scripts/canonical_rescore.py` against any `train_gpt.py` plus the SP8192
tokenizer + val data.

---

## 4. Scope and what this audit does **not** claim

* **Cross-entropy is treated as given.** We do not re-run any model. The
  arithmetic correction `canonical_bpb = reported_bpb × inflation_ratio`
  applies only when (a) the buggy LUT is the source of byte mismatch and
  (b) the model's loss-in-nats was correctly measured by the submitter. If
  a PR has a separate cross-entropy bug, this audit does not catch it.
* **OBFUSCATED scripts are not classified.** Single-line
  `lzma.decompress(base64.b85decode(...))` wrappers — whether executed
  inline via `exec` or via `runpy` after assigning to a local — are flagged
  as `OBFUSCATED`. The static tool cannot determine the LUT status without
  decoding and executing the wrapped code, which is out of scope for a
  no-code-execution audit.
* **No claim is made that any specific obfuscated PR is buggy.** The
  closest precedent is yahya010's own PR #1734 (obfuscated, reported
  1.0108, self-disclosed as canonical ~1.1873). Other obfuscated PRs may
  use the correct LUT internally; we simply cannot verify until the
  authors publish the de-obfuscated source.
* **Per-PR variance is one seed.** Hardware parity is anchored by exp_001
  (one seed within tolerance of the upstream 3-seed mean). For a sharper
  check we would need at least two more seeds; the current evidence is
  sufficient for the analytic correction but not for a record-class
  comparative claim.

---

## 5. Why the static-only design is correct here

The byte-count denominator of BPB depends only on the tokenizer and the
val-token sequence. It does *not* depend on the model checkpoint, the
training data, the optimizer, or the random seed. So the canonical /
buggy ratio is the **same number** for every submission that uses the
SP8192 tokenizer + the standard fineweb val shard, regardless of model
architecture. We compute it once (`1.1671`) and apply it as a multiplier
to any reported BPB whose source `train_gpt.py` is statically classified
as BUGGY. This is a faster, cheaper, and more reliable audit than
reproducing each PR on a GPU — and it eliminates any "your hardware is
different" objection because no hardware is involved beyond the static
inspection.

---

## 6. Tool reference

```bash
python scripts/canonical_rescore.py \
    --train-script <path> \
    --tokenizer    <sp.model> \
    --val-data     '<glob-of-val-shards>' \
    [--seq-len 2048] [--stride 64] \
    [--reported-bpb FLOAT] \
    [--pr-number INT] \
    [--threshold 1.0738] \
    [--output JSON_PATH]
```

JSON output schema:

| Field | Meaning |
|---|---|
| `lut_status` | `CORRECT` / `BUGGY` / `OBFUSCATED` / `UNKNOWN` |
| `inflation_ratio` | `1.0` for CORRECT, computed for BUGGY, `null` otherwise |
| `computed_inflation_ratio` | always the raw `buggy/canonical` from the val data |
| `inferred_canonical_bpb` | `reported_bpb × inflation_ratio` if both known |
| `passes_merged_sota_threshold` | inferred_canonical_bpb ≤ threshold |
| `canonical_byte_count`, `buggy_byte_count` | totals on the scored y-subset |
| `leading_space_token_count`, `scored_token_count`, `num_windows` | sanity counters |
| `notes` | human-readable caveats (e.g. "OBFUSCATED — cannot verify statically") |

Tests in `tests/test_canonical_rescore.py` exercise CORRECT, BUGGY,
OBFUSCATED (both `exec(...)` and runpy patterns), UNKNOWN, the synthetic
byte-counting math, and the end-to-end rescore against PR #1727 and the
buggy fixture.
