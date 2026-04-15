# Quantization-Aware Training (QAT)

## Summary

Simulate quantization noise during training so the model learns to be robust to low-precision weights. Essential for Parameter Golf where every byte counts.

## How It Works

During the forward pass, weights are quantized (e.g., to int6) then dequantized back to float. The backward pass uses the Straight-Through Estimator (STE) to pass gradients through the non-differentiable quantization step as if it were the identity function.

```python
# Simplified QAT forward pass
def quantize_dequantize(w, bits=6):
    scale = w.abs().max() / (2**(bits-1) - 1)
    w_q = torch.round(w / scale).clamp(-2**(bits-1), 2**(bits-1)-1)
    return w_q * scale  # Back to float but with quantization error
```

## Variants Used in Parameter Golf

| Variant | Description | Used In |
|---------|-------------|---------|
| Int6 QAT (STE) | 6-bit weights, standard | All top submissions |
| Int5 MLP | 5-bit for MLP only, int6 for attention | PR #162+ |
| GPTQ post-training | Optimize quantization per-row after training | PR #1019+ |
| GPTQ-lite clip search | Try 5 percentiles per row, pick lowest MSE | PR #374 |
| Hessian-aware SDClip | Use Hessian info for smarter clipping | PR #1412 |
| Ternary (1-bit) | Quantize to {-1, 0, 1} | PR experimental (1.157) |

## Papers

- **Quantization and Training of Neural Networks for Efficient Integer-Arithmetic-Only Inference** — Jacob et al. 2018 (https://arxiv.org/abs/1712.05877)

- **GPTQ: Accurate Post-Training Quantization for Generative Pre-trained Transformers** — Frantar et al. 2023 (https://arxiv.org/abs/2210.17323)

- **BitNet: Scaling 1-bit Transformers for Large Language Models** — Wang et al. 2023 (https://arxiv.org/abs/2310.11453)

- **SqueezeLLM: Dense-and-Sparse Quantization** — Kim et al. 2024 (https://arxiv.org/abs/2306.07629)

## Implementation Notes

- **When to start QAT**: Some submissions start QAT at 15% of training (QAT@0.15). Earlier start = more adaptation time but slower early convergence.
- **Per-row scaling**: Each row of the weight matrix gets its own scale factor. Much better than per-tensor.
- **GPTQ calibration data**: PR #1019 uses self-generated calibration data (model's own outputs) instead of training data. Legal during training.
- **Compression**: After quantization, zstd-22 compression further reduces artifact size.

## Key Insight

Int6 is the sweet spot for Parameter Golf. Int5 saves bytes but hurts quality more than the extra capacity is worth — unless you pair it with techniques that compensate (BigramHash, SmearGate).

## My Experiments

*No experiments yet.*
