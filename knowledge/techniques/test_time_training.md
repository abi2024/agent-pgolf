# Test-Time Training (TTT)

## Summary

Adapt the model's weights at evaluation time by training on the test input *after* scoring it. The "legal" variant in Parameter Golf: evaluate tokens first (score them), then use those already-graded tokens to update the model via a few SGD steps before processing subsequent tokens.

## How It Works (Score-First / Legal TTT)

1. Model sees a document for evaluation
2. Process first chunk of tokens → compute loss (these are already "graded")
3. Use that loss to do a few gradient steps (e.g., LoRA updates)
4. Process next chunk with updated weights → better predictions
5. Repeat for the rest of the document

The key constraint: you can ONLY train on tokens you've already evaluated. You cannot look ahead.

## Key Results in Parameter Golf

| PR | Variant | BPB | Notes |
|----|---------|-----|-------|
| #1493 | Legal score-first TTT | 1.0810 | Current SOTA |
| #1413 | Legal score-first TTT | 1.0828 | With QK-Gain 5.0 |
| #549 | Legal score-first TTT + Parallel Muon | 1.1194 | First TTT entry |
| Mar 19 | LoRA TTT | 1.1928 | Early LoRA-based approach |

## Papers

- **Test-Time Training with Self-Supervision for Generalization under Distribution Shifts** — Sun et al. 2020 (https://arxiv.org/abs/1909.13231)

- **Test-Time Training on Nearest Neighbors for Large Language Models** — Hardt & Sun 2024 (https://arxiv.org/abs/2305.18466)

- **TTT: Tokenized Test-Time Training for Language Models** — Sun et al. 2024

## Critical Warning: Conflicts with Depth Recurrence

Standard TTT (updating all weights via SGD) **fundamentally conflicts** with weight-tied recurrence:
- With weight tying, updating block weights via SGD also changes their behavior in the other loop iteration
- Same weights used twice → every update has 2× the effect
- Gradients compound through recurrence
- Result: catastrophic regression (1.34 BPB vs 1.09 baseline)

**The legal score-first variant works** because it limits gradient accumulation to already-evaluated tokens, reducing the compounding effect.

## Implementation Notes

- Score-first approach: process tokens, compute loss, update weights, continue
- LoRA updates are cheaper than full weight updates
- Must NOT access tokens you haven't evaluated yet
- Must NOT access training data during evaluation
- Evaluation time limit: 10 min on 8xH100s (separate from training time)

## My Experiments

*No experiments yet.*
