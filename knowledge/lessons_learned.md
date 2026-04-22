# Lessons Learned — What Failed and Why

---

## ⚠ MEASUREMENT INTEGRITY — READ THIS FIRST

### BPB Double-Counting Bug: PR #1698 Inheritance Line (~17.46% inflation)

**Source**: yahya010 self-closure comment on PR #1734 (2026-04-19). The author explicitly described the bug before any external audit. This section systematizes that finding.

**The bug — two independent +1 errors that compound:**
1. `build_sentencepiece_luts`: for every token with a leading space (`▁`), the LUT stores `len(piece.encode('utf-8')) + 1` instead of `len(piece.encode('utf-8'))` — baking in +1 byte per leading-space token at LUT construction time.
2. `eval_val_sliding`: when accumulating byte counts during sliding-window evaluation, adds another +1 for the same leading-space tokens — double-counting them.

Result: reported byte count is inflated by approximately the fraction of tokens that have leading spaces (roughly 35–50% of SentencePiece tokens in English text), yielding **~17.46% fewer reported bytes** than canonical. Since BPB = bits / bytes, fewer bytes → lower (better-looking) BPB.

**Canonical correction**: `canonical_bpb ≈ reported_bpb × 1.1746`. PR #1734's reported 1.0108 → canonical ~1.187, which is **worse than the merged-SOTA threshold of 1.0738**.

**Affected submissions** (all descend from PR #1698's buggy `build_sentencepiece_luts`):
- PR #1734 — GatedDeltaNet + Legal TTT + Brotli-11 (closed by author)
- PR #1758 — PreQuant TTT LR=1e-3 + Unfrozen (open, inflated)
- All other open PRs in the #1698 family (treat any BPB < 1.06 with suspicion until lineage is verified)

**Verified correct lineage** (use only these as parents or comparisons):
- PR #1700 — correct-LUT base implementation
- PR #1727 — SP8192 + MP-SGD TTT 4 phases + QK-Gain 5.25, val_bpb 1.07217 (yahya010, confirmed correct)
- PR #1493 — Legal score-first TTT, val_bpb 1.0810 (older anchor, pre-SP8192)

**Action rule**: Before parenting any experiment on an open PR, verify that its `build_sentencepiece_luts` does NOT add +1 for leading-space tokens. One-line check:
```python
# In build_sentencepiece_luts — the correct line is:
base_bytes_np[token_id] = len(piece.encode('utf-8'))  # correct
# NOT:
base_bytes_np[token_id] = len(piece.encode('utf-8')) + 1  # BUG
```

**Active work**: `knowledge/measurement_integrity_audit.md` documents the systematic re-scoring project (exp_001–003).

---

## Technique Conflicts

### EMA + Aggressive Depth Recurrence = BAD
- **What happened**: EMA (decay=0.997) produced BPB of 1.42 on recurrent models — worse than random
- **Why**: EMA averages weights over the entire training run, including early poorly-converged states. With recurrent models the early weights are especially bad because the same weights process multiple loop iterations
- **Source**: namspdr.substack.com Parameter Golf blog post

### TTT + Weight-Tied Recurrence = BAD
- **What happened**: Per-document LoRA TTT produced BPB of 1.34 on recurrent architecture (vs 1.0865 on standard)
- **Why**: With weight tying, updating block weights via SGD also changes their behavior in other loop iterations. Same weights used twice = every update has 2x the effect. Gradients compound through recurrence in ways they don't in standard architectures
- **Key insight**: TTT assumes each layer is independent, but recurrence makes them coupled
- **Exception**: The legal "score-first" TTT works because it only trains on already-evaluated tokens, limiting gradient accumulation

### Width Increase Can Hurt
- **What happened**: Increasing model width to d=544 made things worse despite more parameters
- **Why**: Bigger model = slower per-step = fewer total training steps in the 10-minute window
- **Lesson**: Step count matters as much as model capacity

## Architecture Insights

### Unique Capacity > Loop Depth
- 5 unique blocks × 2 loops (10 effective layers) beat 4 blocks × 3 loops (12 effective layers)
- The model benefits more from diverse representations than repeated processing
- At 8+ unique blocks, adding more barely helps

### Layer Position Matters for Recurrence
- Looping layers 4-5 (middle of network) works best
- Looping layers 2-3 (too early) → worse results
- Current SOTA uses 3-layer recurrence (layers 3-5) — the sweet spot

### GPTQ-lite Sometimes Doesn't Help
- Percentile-based clipping (trying 5 percentiles per row) was slightly worse on some weight distributions
- Standard max-based clipping works fine when weight distributions are already well-behaved
- Worth trying but not guaranteed improvement

## Training Dynamics

### Warmdown Schedule Matters
- warmdown3500 (starting weight averaging at step 3500) worked well
- Too early = averaging poorly-converged weights
- Too late = not enough averaging time

### Weight Decay Sweet Spot
- WD=0.04 was early standard
- WD=0.085-0.09 works better with current deeper architectures
- Higher WD with more parameters seems to be the trend

## Quantization

### Int5 vs Int6
- Int5 MLP saves ~0.8MB per layer but training is harder
- Mixed precision (int5 MLP + int6 attention) works better than uniform int5
- BigramHash(10240) helped compensate for int5 quality loss

### Embedding Quantization
- FP16 embeddings → significant early improvement
- GPTQ embeddings → further improvement in later submissions
- Embeddings are the most sensitive to quantization quality
