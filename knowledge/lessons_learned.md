# Lessons Learned — What Failed and Why

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
