# Exponential Moving Average (EMA) / Stochastic Weight Averaging (SWA)

## Summary

Weight averaging smooths the training trajectory by maintaining a running average of model weights. EMA keeps a decayed average updated every step. SWA averages discrete checkpoints during the warmdown phase.

## How It Works

```python
# EMA: update every step
ema_weights = decay * ema_weights + (1 - decay) * current_weights

# SWA: average checkpoints during warmdown
if step > warmdown_start:
    swa_weights = (swa_count * swa_weights + current_weights) / (swa_count + 1)
```

## Key Results

| PR | Variant | BPB | Notes |
|----|---------|-----|-------|
| #374 | EMA (decay=0.997) + SWA during warmdown | 1.1228 | EMA + SWA stacked |
| #287 | EMA | 1.1248 | With partial RoPE |
| #198 | EMA replacing SWA | 1.1271 | First EMA entry |

## Critical Warning: Conflicts with Depth Recurrence

**EMA (decay=0.997) produced BPB of 1.42 on recurrent models** — worse than random.

**Why**: EMA averages weights over the *entire* training run, including early poorly-converged states. With recurrent models, early weights are especially bad because the same weights process multiple loop iterations, amplifying errors.

**SWA is safer**: It only averages during the warmdown phase (e.g., last 500 steps), when weights are already well-converged.

## Papers

- **Averaging Weights Leads to Wider Optima and Better Generalization** — Izmailov et al. 2018 (https://arxiv.org/abs/1803.05407)

- **Exponential Moving Average in Deep Learning** — Polyak & Juditsky 1992 (original work)

## When to Use

- **Use SWA** (during warmdown only) with depth recurrence — safe
- **Use EMA** only with NON-recurrent architectures
- **Never use EMA** with aggressive weight tying / depth recurrence
- Consider warmdown schedule: 3500 steps worked well in PR #374

## My Experiments

*No experiments yet.*
