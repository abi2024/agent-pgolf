# Parallel Residuals

## Summary

Instead of the standard sequential residual connection (x → attention → add → MLP → add), parallel residuals run attention and MLP on the same input and add both results simultaneously. This creates two separate residual "lanes" that the model can use independently.

## Standard vs Parallel

```python
# Standard (sequential):
x = x + attention(norm(x))
x = x + mlp(norm(x))

# Parallel residuals:
x = x + attention(norm(x)) + mlp(norm(x))
```

## Key Results

| PR | BPB | Notes |
|----|-----|-------|
| #1493 | 1.0810 | Current SOTA, parallel residuals included |
| #1477 | 1.0822 | Parallel residuals on SP8192 + TTT stack |
| #1204 | 1.1063 | First use of parallel residual lanes |

## Papers

- **GPT-J and GPT-NeoX** — EleutherAI used parallel attention + MLP in their open models, showing it trains ~15% faster with negligible quality difference at scale.

- **PaLM: Scaling Language Modeling with Pathways** — Chowdhery et al. 2022. Google's PaLM used parallel formulation at 540B scale.

## Why It Helps

1. **Faster training**: One normalization call instead of two per layer → faster step time → more steps in 10 minutes
2. **Better gradient flow**: Both attention and MLP get gradients from the same clean residual stream
3. **Marginal quality improvement**: ~0.005 BPB in Parameter Golf context

## Implementation Notes

- Simple code change: compute attention and MLP on same normalized input, add both
- Works well with depth recurrence (no known conflicts)
- Works with TTT (no known conflicts)
- Essentially free improvement — should always be included

## My Experiments

*No experiments yet.*
