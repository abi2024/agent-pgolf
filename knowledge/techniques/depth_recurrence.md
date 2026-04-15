# Depth Recurrence (Weight-Tied Layer Loops)

## Summary

Reuse transformer layers by looping through a subset of them multiple times during the forward pass. This increases effective depth without adding parameters — critical when you're capped at 16MB.

## How It Works

Instead of `x = layer_4(x); x = layer_5(x)`, you do:
```python
for _ in range(num_loops):
    x = layer_4(x)
    x = layer_5(x)
```

The same weight matrices process the input multiple times, creating a deeper effective network.

## Key Results in Parameter Golf

| PR | Config | BPB | Date |
|----|--------|-----|------|
| #1493 | 3-layer recurrence (layers 3-5), 2 loops | 1.0810 | Apr 9 |
| #1394 | Loop layers 4-5, 2 iterations | 1.0856 | Apr 5 |
| #1334 | SP4096 + depth recurrence + parallel res | 1.0897 | Apr 4 |
| #1204 | Mini recurrence layers 4-5 | 1.1063 | Mar 31 |

## Papers

- **Universal Transformers** — Dehghani et al. 2019 (https://arxiv.org/abs/1807.03819)
  First proposal of applying transformer blocks repeatedly. Showed improved performance on algorithmic tasks.

- **Scaling Laws for Neural Language Models** — Kaplan et al. 2020 (https://arxiv.org/abs/2001.08361)
  Context for why parameter efficiency matters: L(N) optimization.

## Implementation Notes

- **Best layer range**: Middle layers (4-5 or 3-5). Early layers need unique representations for input processing.
- **Loop count**: 2 iterations is the sweet spot. 3 loops with fewer unique blocks is worse than 2 loops with more unique blocks.
- **Progressive recurrence**: Start with 1 loop during early training, increase to 2 during warmdown. Used in PR #1412.

## Known Conflicts

- **EMA**: Weight averaging fails because early weights are especially bad for recurrent models
- **Standard TTT**: Gradients compound through shared weights (2x effect per update)
- **Legal score-first TTT**: Works because it limits gradient accumulation to already-evaluated tokens

## My Experiments

*No experiments yet. Will be updated as experiments are run.*
