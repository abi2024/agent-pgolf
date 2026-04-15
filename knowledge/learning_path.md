# Learning Path — Parameter Golf Core Concepts

Each topic below links to papers, implementations, and blog angles. Claude Code should create technique docs in `knowledge/techniques/` as it explores each topic.

## Tier 1: Must-Know (In Every SOTA Submission)

### Quantization-Aware Training (QAT)
- **Doc**: `knowledge/techniques/quantization_aware_training.md`
- **Papers**: Jacob et al. 2018, Frantar et al. 2023 (GPTQ), Wang et al. 2023 (BitNet)
- **Implementation**: STE in train_gpt.py forward pass
- **Blog angle**: "From 32 bits to 6: how aggressive quantization enables tiny LMs"

### Depth Recurrence
- **Doc**: `knowledge/techniques/depth_recurrence.md`
- **Papers**: Dehghani et al. 2019 (Universal Transformers)
- **Implementation**: Layer loop in forward pass
- **Blog angle**: "Getting 2x depth for free with weight tying"

### SentencePiece Tokenization
- **Papers**: Kudo & Richardson 2018 (https://arxiv.org/abs/1808.06226)
- **Key insight**: SP8192 beats SP1024 for BPB because better compression
- **Blog angle**: "Why your tokenizer matters more than your architecture"

### Optimizer: Muon and Variants
- **Papers**: Original Muon paper, MuonEq-R modifications
- **Key insight**: Modified momentum with equalized learning rates per layer
- **Blog angle**: "Beyond Adam: optimizers for extreme parameter efficiency"

## Tier 2: Important (Used in Top 5 Submissions)

### Test-Time Training
- **Doc**: `knowledge/techniques/test_time_training.md`
- **Papers**: Sun et al. 2020, Hardt & Sun 2024
- **Key insight**: Legal score-first TTT is the only variant that works with depth recurrence
- **Blog angle**: "Can your model learn at test time? The legal way to cheat"

### Parallel Residuals
- **Papers**: Original residual learning (He et al. 2016), parallel formulation
- **Key insight**: Separate attention and MLP residual paths
- **Blog angle**: "Why your residual connections might be bottlenecking you"

### GPTQ Post-Training Quantization
- **Papers**: Frantar et al. 2023 (https://arxiv.org/abs/2210.17323)
- **Key insight**: Per-row optimization of quantization scales using calibration data
- **Blog angle**: "Squeezing the last 0.01 BPB with smarter quantization"

### Weight Averaging (EMA / SWA)
- **Papers**: Izmailov et al. 2018 (SWA), Polyak & Juditsky 1992 (EMA)
- **Key insight**: EMA conflicts with depth recurrence; SWA during warmdown is safer
- **Blog angle**: "The subtle art of weight averaging (and when it backfires)"

## Tier 3: Advanced (Recent Innovations)

### QK-Gain Scaling
- **What**: Scale query-key dot products by a learned or fixed factor (5.0-5.25)
- **Blog angle**: "A one-line change that improves attention quality"

### Hessian-Aware Quantization Clipping
- **What**: Use second-order information to decide per-row clip thresholds
- **Papers**: Related to OBQ (Frantar & Alistarh 2022)
- **Blog angle**: "When standard deviation beats percentiles for quantization"

### Progressive Recurrence
- **What**: Gradually increase loop depth during training
- **Blog angle**: "Teaching a model to think in loops, one iteration at a time"

## Tier 4: Frontier / Unexplored

### State-Space Models (Mamba)
- **Papers**: Gu & Dao 2024 (https://arxiv.org/abs/2312.00752)
- **Status**: Untried in Parameter Golf. Requested by organizers.
- **Potential**: Different inductive bias, linear-time inference, might compress differently

### Megakernels
- **What**: Fused CUDA kernels that do more computation per memory access
- **Potential**: More training steps in 10 min = better model = lower BPB
- **Challenge**: Requires CUDA kernel development expertise

### Mixture of Experts (Tiny)
- **Papers**: Fedus et al. 2022 (Switch Transformer)
- **Potential**: Route different tokens to different weight subsets
- **Challenge**: Router parameters + expert parameters must fit in 16MB

### Knowledge Distillation
- **Papers**: Hinton et al. 2015, Sanh et al. 2020 (DistilBERT)
- **Potential**: Train a large model, distill into 16MB student
- **Challenge**: Would need unlimited compute track, extra training budget

## How to Use This Document

1. When starting a new technique, read the relevant section here
2. Check if a `knowledge/techniques/` doc exists — if not, create one
3. After running experiments, update the technique doc with your results
4. Use the "blog angle" to generate your daily blog post
