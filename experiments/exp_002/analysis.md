# exp_002: SOTA Stack Deep Analysis

**Source**: `parameter-golf/records/track_10min_16mb/2026-04-09_SP8192_3LayerRecur_ParResid_QK525_LegalTTT/`
**Result**: 1.0810 BPB (3-seed mean, std 0.0002), ~15.99 MB artifact, 588s on 8xH100

This document explains every technique in the SOTA stack, why it's there, and how it works in the code.

---

## 1. Architecture Overview

**11 layers, 512 dim, 8 heads (4 KV heads), MLP 4x, tied embeddings, vocab 8192**

The model is a GPT-style transformer with several non-standard modifications stacked together.
The forward pass (`GPT.forward_logits`, line 144-159) is:

```
embed -> RMSNorm -> encoder blocks -> decoder blocks (with skip connections) -> final_norm -> tied_lm_head -> softcap
```

The encoder/decoder split is a U-Net-like structure: the first half of blocks are "encoder", the second half are "decoder", with sigmoid-gated skip connections from encoder to decoder (like a U-Net).

---

## 2. SP8192 SentencePiece Tokenizer

**What**: A SentencePiece BPE tokenizer with 8192 vocab size (vs baseline's 1024).
**Why**: Larger vocab = each token covers more bytes on average = better compression = lower BPB.
**Where in code**: `Hyperparameters.vocab_size = 8192`, `tokenizer_path` points to `fineweb_8192_bpe.model`.
**Impact**: The jump from SP1024 to SP4096 to SP8192 was one of the biggest single improvements (~1.10 -> ~1.08 region). The tradeoff is that the embedding table is bigger (8192 x 512 = 4M params), but with int8 quantization and GPTQ it fits in the budget.
**BPB accounting**: The eval code (lines 22-30, `build_sentencepiece_luts`) carefully counts actual UTF-8 bytes per token including leading-space handling. BPB = bits/byte, so a tokenizer that represents more bytes per token directly reduces the numerator.

---

## 3. Depth Recurrence (3-Layer, Layers 3-5)

**What**: Layers 3, 4, and 5 are physically defined once but executed multiple times during the forward pass, creating "virtual" depth without extra parameters.
**Why**: Free effective depth. 11 physical layers become 17 virtual layers. The model gets more compute per parameter.
**Where in code**: Lines 132-136 in `GPT.__init__`:

```python
loop_seg = [3, 4, 5]  # loop_start=3, loop_end=5
all_indices = [0, 1, 2] + [3, 4, 5] * 3 + [6, 7, 8, 9, 10]
# = [0,1,2, 3,4,5, 3,4,5, 3,4,5, 6,7,8,9,10]  (17 indices total)
encoder_indices = [0,1,2,3,4,5,3,4]  (first 8)
decoder_indices = [5,3,4,5,6,7,8,9,10]  (last 9)
```

**Activation schedule**: Looping is NOT active from the start. It activates at `enable_looping_at = 0.35` (35% through training, line 429). This is critical: if you loop from step 0, the shared weights get conflicting gradients before they've converged. The model first learns good individual-layer representations, then learns to reuse them.

**Warmup trick** (lines 405-418): Before real training begins, the code does 20 warmup steps without looping, then 20 more WITH looping, then throws away all the weights and optimizer state. This "primes" `torch.compile` to generate kernels for both code paths, avoiding a JIT compilation stall mid-training.

**Known conflicts**: EMA + aggressive recurrence is bad (weights from early training are terrible for recurrence). Score-first TTT works despite recurrence because it doesn't backprop through loop iterations during eval.

---

## 4. Parallel Residuals (Layers 7+)

**What**: GPT-J style parallel attention and MLP. Instead of sequential `x = x + attn(norm(x)); x = x + mlp(norm(x))`, both operate on the same input: `x = x + attn(norm(x)) + mlp(norm(x))`.
**Why**: Saves one sequential dependency. Faster wall-clock time = more training steps in 10 minutes. Slight quality tradeoff but net positive because of extra steps.
**Where in code**: `Block.forward` (lines 109-113):

```python
if self.parallel:
    mlp_out = self.mlp(self.mlp_norm(x_in) * self.ln_scale_factor)
    x_out = x_in + attn_scale * attn_out + mlp_scale * mlp_out
else:
    x_out = x_in + attn_scale * attn_out
    x_out = x_out + mlp_scale * self.mlp(self.mlp_norm(x_out) * self.ln_scale_factor)
```

Only applied to layers 7+ (`parallel_residual_start = 7`). Earlier layers use sequential residuals — they benefit more from the sequential information flow because they build base representations.

---

## 5. QK-Gain 5.25

**What**: A learnable per-head scaling factor applied to query vectors after QK-normalization.
**Why**: Standard attention divides by sqrt(d_k) to prevent softmax saturation. QK-Gain goes the opposite direction — it AMPLIFIES the dot products by 5.25x, making attention distributions sharper. This helps the model attend more precisely to relevant tokens.
**Where in code**: `CausalSelfAttention.forward` (line 101):

```python
q = q * self.q_gain.to(dtype=q.dtype)[None, None, :, None]
```

`q_gain` is initialized to 5.0 (env `QK_GAIN_INIT=5.25` overrides for submissions) and is a learnable `nn.Parameter` of shape `(num_heads,)`. Each head learns its own sharpness.

**Why it works**: With RMSNorm on Q and K (line 101), the dot products are normalized to unit scale. Multiplying by 5.25 means the softmax temperature is effectively 1/5.25 — very peaked attention. The model learns to use this for precise token lookups. Monotonic improvement observed from 4.0 to 5.25.

---

## 6. LeakyReLU(0.5)^2 Activation

**What**: `MLP.forward` (line 106): `F.leaky_relu(x, negative_slope=0.5).square()`
**Why**: Squaring the activation creates a smoother nonlinearity than plain ReLU^2. The 0.5 negative slope means negative inputs still contribute (half-magnitude), squared. This gives the network more expressiveness than ReLU^2 (which zeroes negatives) while keeping the quadratic shape that helps with learning dynamics.
**History**: Replaced standard GELU/SwiGLU. Contributed in PR #549. The squared activation is important — it provides a natural gradient scaling that interacts well with the Muon optimizer.

---

## 7. Partial RoPE (16/64 dims)

**What**: Rotary Position Embeddings applied to only the first 16 out of 64 head dimensions.
**Why**: Full RoPE constrains all dimensions to encode position. Partial RoPE lets the remaining 48 dims freely encode content/semantic information. Especially useful for depth recurrence — the same layer sees the same positions multiple times, so less positional encoding in the content channels reduces interference.
**Where in code**: `Hyperparameters.rope_dims = 16`, applied in `apply_rotary_emb` (lines 88-90):

```python
if rope_dims > 0 and rope_dims < x.size(-1):
    x_rope, x_pass = x[..., :rope_dims], x[..., rope_dims:]
    # only x_rope gets cos/sin rotation, x_pass is unchanged
```

---

## 8. MuonEq-R Optimizer

**What**: A modified Muon optimizer with row normalization. Muon uses Newton-Schulz iteration to compute the matrix sign function of gradients (line 167-171), effectively decorrelating gradient directions.
**Why**: Standard Adam/AdamW under-performs on small models with limited training time. Muon gives much better per-step optimization, and with only ~4500 steps in 10 minutes, every step counts.
**Where in code**: `Muon` class (lines 172-198), `zeropower_via_newtonschulz5` (lines 167-171).

Key components:
- **Newton-Schulz 5 iteration** (5 steps of `X = a*X + b*(X@X.T)@X + c*(X@X.T@X@X.T)@X`): Approximates the polar decomposition `W = U * S * V^T -> U * V^T`. This whitens the gradient.
- **Row normalization** (`muon_row_normalize = True`, line 190): After Newton-Schulz, normalize each row of the gradient. This makes updates scale-invariant per output neuron.
- **Momentum warmup** (lines 399-400): Momentum starts at 0.92 and ramps to 0.99 over 1500 steps.
- **Separate optimizer groups**: Muon for weight matrices, AdamW for embeddings and scalars (lines 200-208). Muon only works on 2D weight matrices.

---

## 9. EMA (Exponential Moving Average, decay=0.9965)

**What**: Maintains an exponential moving average of all model weights during training. At the end, the EMA weights replace the training weights.
**Why**: Smooths out SGD noise. The final weights are an average heavily biased toward late training (when the model is best).
**Where in code**: Lines 421, 432, 438:

```python
ema_state = {name: t.detach().float().clone() for name, t in base_model.state_dict().items()}
# each step:
ema_state[name].mul_(0.9965).add_(t.detach().float(), alpha=0.0035)
# at end:
base_model.load_state_dict(avg_state, strict=True)
```

**Note**: Decay 0.9965 is quite aggressive (effective window ~286 steps). Works well here because the warmdown schedule already smooths the learning rate. EMA + aggressive depth recurrence was previously found to be BAD, but it works here because the looping activates at 35% (after ~1600 steps), and by that point EMA has mostly forgotten the non-looping weights.

---

## 10. GPTQ Post-Training Quantization with SDClip

**What**: Full Hessian-aware GPTQ quantization with Standard-Deviation-based Clipping.
**Why**: Need to compress the model to fit in 16MB. Naive round-to-nearest is suboptimal. GPTQ uses second-order (Hessian) information to decide quantization order and compensate for rounding errors.
**Where in code**: Lines 221-267 (`collect_hessians`, `gptq_quantize_weight`, `gptq_mixed_quantize`).

**How it works**:
1. **Collect Hessians** (lines 221-249): Run 64 calibration batches through the model. For each linear layer, collect `H = X^T @ X` (the Gram matrix of inputs). This tells you which weight dimensions are "important" — dimensions with large input activations matter more.
2. **GPTQ quantization** (lines 250-256): Process weights column-by-column in order of importance (descending diagonal of H). For each column:
   - Quantize: `q = clamp(round(w / scale), -range, range)`
   - Compute error: `err = (w - q * scale) / H_diag[j]`
   - Compensate: Spread the error to remaining unquantized columns using `H_inv`
   - Block processing (block_size=128) for efficiency
3. **SDClip** (`clip = k * std(row)`): Instead of using min/max of each row to set scale, use `scale = 12.85 * std(row) / 63`. This is principled: it comes from rate-distortion theory. A few outlier weights get clipped, but the overall MSE is lower because the scale isn't dominated by outliers.

**Precision allocation**:
- Weight matrices (attention + MLP): int6, k=12.85 — 6 bits per weight, clip at 12.85 standard deviations
- Embeddings: int8, k=20.0 — 8 bits, clip at 20 stds. Embeddings are more sensitive to quantization because they're used for both input and output (tied).

---

## 11. Byte-Shuffle + Brotli Compression

**What**: After quantization, weights are byte-shuffled then Brotli-11 compressed.
**Why**: Squeezing every byte to fit under 16MB.
**Where in code**: Lines 283-304 (`_byte_shuffle`, `_compress`).

**Byte-shuffle** (stride=2): Rearranges bytes so that the MSBs of all values are grouped together, followed by all LSBs. This dramatically improves compression ratio because the MSB patterns are much more regular than interleaved byte streams.

**Brotli-11**: Maximum compression level. Slow to compress (seconds) but fast to decompress (milliseconds). Better ratio than zlib/zstd for this data pattern.

---

## 12. Legal Score-First TTT (Test-Time Training)

**What**: At evaluation time, adapt the model to the validation data using SGD — but only train on tokens that have ALREADY been scored.
**Why**: The model sees the validation data for the first time at eval. TTT lets it adapt to the distribution of this specific data, improving predictions on later chunks.
**Where in code**: `eval_val_ttt` (lines 340-377).

**Algorithm**:
1. Split validation tokens into 32K-token chunks
2. For each chunk:
   a. **Score phase** (lines 350-356): Under `torch.no_grad()`, run sliding-window eval to score all tokens in this chunk. These scores count toward the final BPB.
   b. **Train phase** (lines 358-374): Using SGD (lr=0.005, momentum=0.9), train the model on the chunk for 3 epochs. This updates ALL model parameters.
3. Cosine LR decay across chunks (line 361): `lr = base_lr * 0.5 * (1 + cos(pi * chunk_idx / num_chunks))`

**Why it's legal** (per Issue #1017):
- **Causality**: Sliding window eval is strictly causal — each position scored from prefix tokens only
- **Score before update**: Each chunk is FULLY scored under `no_grad()` BEFORE any SGD update
- **Single pass**: Each token scored exactly once, no rescoring
- **No logit biasing**: Standard softmax, no n-gram tricks

**TTT + recurrence compatibility**: Score-first TTT works with recurrence because scoring is done under `no_grad()` (no gradient compounding through shared weights). The training phase does update shared weights, but only on already-scored tokens — the "damage" from gradient compounding doesn't affect the final BPB.

**Timing**: ~370s of the 600s eval budget. Training + TTT eval must fit in 600s total.

---

## 13. Skip Gates (Sigmoid-Gated U-Net Connections)

**What**: U-Net-style skip connections from encoder to decoder, with learnable sigmoid gates.
**Why**: Lets the decoder access early representations directly, helping gradient flow through the deep (17 virtual layers) network.
**Where in code**: Lines 137, 148-153:

```python
# Encoder: save skip activations
for i in enc_iter:
    x = self.blocks[i](x, x0)
    skips.append(x)

# Decoder: merge skip activations
if skip_idx < self.num_skip_weights and skips:
    scaled_skip = self.skip_weights[skip_idx] * skips.pop()
    g = sigmoid(self.skip_gates[skip_idx])
    x = lerp(scaled_skip, x, g)  # = g*x + (1-g)*scaled_skip
```

`skip_gates` initialized to 0 -> sigmoid(0) = 0.5 -> starts as 50/50 mix. The model learns to adjust the gate per-dimension. `skip_weights` are initialized to 1.0 (identity scaling).

---

## 14. Residual Mix (x0 Connection)

**What**: Each block receives both `x` (running hidden state) and `x0` (post-embedding representation). The input to each block is a learned weighted combination.
**Where in code**: `Block.forward` (line 110):

```python
mix = self.resid_mix  # shape (2, dim)
x_in = mix[0] * x + mix[1] * x0
```

**Why**: Initialized as `mix[0] = ones, mix[1] = zeros` (pure residual stream). The model can learn to inject raw token information at any layer. This is especially useful with depth recurrence — layers 3-5 see the same position embeddings but at different depths, and `x0` provides a stable reference signal.

---

## 15. Logit Softcap (30.0)

**What**: `logits = 30.0 * tanh(logits / 30.0)` — clamps logits to [-30, 30].
**Why**: Prevents logit explosion during training, especially important with tied embeddings and aggressive learning rates. Also stabilizes TTT.
**Where in code**: Line 159: `self.logit_softcap * torch.tanh(logits_proj / self.logit_softcap)`

---

## 16. Layerwise LN Scale

**What**: Each layer's norm output is scaled by `1/sqrt(layer_idx + 1)`.
**Why**: Deeper layers naturally accumulate larger activations. This scaling counteracts that, keeping all layers on similar scales. Important for the Muon optimizer which assumes roughly unit-scale gradients.
**Where in code**: `Block.__init__` line 108: `self.ln_scale_factor = 1./math.sqrt(layer_idx+1)`, applied in forward (lines 110-112).

---

## 17. XSA (Cross-Subspace Attention)

**What**: After standard attention, project out the component along V. This forces the attention output to be orthogonal to the value vectors.
**Why**: Prevents the attention from simply copying values — forces it to learn more complex transformations.
**Where in code**: Lines 99, 102:

```python
def _xsa_efficient(self, y, v):
    vn = F.normalize(v, dim=-1)
    proj = (y * vn).sum(dim=-1, keepdim=True) * vn
    return (y - proj)  # remove V component
```

Applied to all 11 layers (`xsa_last_n = 11`).

---

## 18. Training Schedule

**Wallclock-based training** (NOT step-based):
- `max_wallclock_seconds = 600` minus 12s for GPTQ = 588s of training
- ~4550 steps achieved on 8xH100
- Learning rate schedule: flat until warmdown, then linear decay to 0 over the final 72% (`warmdown_frac = 0.72`)
- This means LR is at full value for only the first 28% of training, then continuously decaying

**Warmdown is aggressive**: Starting LR decay at 28% might seem early, but with Muon's momentum and EMA smoothing, the model continues to improve during warmdown. The key insight is that in a time-limited competition, you want the model to be well-converged (low LR, averaged weights) when time runs out.

---

## 19. Weight Decay

- Muon (weight matrices): WD = 0.095
- AdamW (embeddings): WD = 0.085
- AdamW (scalars): WD = 0.02

Higher WD than typical (0.01-0.04) because:
1. Deeper/recurrent models overfit more
2. Helps quantization — smaller weight magnitudes = less quantization error
3. Works with aggressive LR schedule

---

## 20. Flash Attention 3

**Where**: Line 6 imports `flash_attn_3_func`, used in line 101.
**Why**: Hardware-optimized attention kernel. Not just faster — enables longer sequences and larger batches that wouldn't fit in memory with standard attention. Essential for getting 4500+ steps in 10 minutes.

**Note for local**: Flash Attention 3 requires CUDA SM90+ (H100). On GTX 3060 (SM86), you need either Flash Attention 2 or the math SDP backend, plus `TORCHDYNAMO_DISABLE=1` since there's no Triton on Windows.

---

## Summary: Why This Stack Wins

| Technique | BPB Impact | Why It's Here |
|-----------|-----------|---------------|
| SP8192 | ~0.03 | More bytes per token = better compression ratio |
| 3-layer recurrence | ~0.01 | Free depth: 11 params -> 17 virtual layers |
| Parallel residuals | ~0.005 | Faster steps -> more training in 10 min |
| QK-Gain 5.25 | ~0.003 | Sharper attention = more precise predictions |
| Legal TTT | ~0.002 | Adapt to val distribution at test time |
| GPTQ + SDClip | ~0.005 | Less quantization error = preserves training quality |
| MuonEq-R | ~0.01 | Better per-step optimization = more from limited steps |
| EMA 0.9965 | ~0.003 | Smoothed weights generalize better |
| XSA | ~0.002 | Forces attention to learn richer transformations |
| Skip gates | ~0.002 | Better gradient flow through deep recurrent network |
| Partial RoPE | ~0.001 | Frees head dims for content vs position |

Total stack improvement from baseline: **~0.14 BPB** (1.2244 -> 1.0810)

---

## Reproduction Notes

The submission file is LZMA-compressed (2 lines). The readable source is 469 lines.

```bash
# On RunPod with 8xH100:
pip install brotli sentencepiece
pip install flash_attn_3 --no-deps --find-links https://windreamer.github.io/flash-attention3-wheels/cu128_torch291/
SEED=42 QK_GAIN_INIT=5.25 TTT_ENABLED=1 TTT_LR=0.005 TTT_EPOCHS=3 \
  torchrun --standalone --nproc_per_node=8 train_gpt.py

# Local smoke test (GTX 3060):
TORCHDYNAMO_DISABLE=1 RUN_ID=smoke ITERATIONS=200 TRAIN_BATCH_TOKENS=8192 \
  VAL_LOSS_EVERY=0 TTT_ENABLED=0 python train_gpt.py
# Note: flash_attn_3 won't work on 3060. Need to swap to flash_attn_2 or math SDP.
```
