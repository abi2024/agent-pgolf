# Experiment Template

## Config (config.json)

```json
{
    "id": "exp_NNN",
    "hypothesis": "SPECIFIC hypothesis here",
    "technique_stack": ["technique_1", "technique_2"],
    "parent_id": "exp_MMM or null",
    "baseline_bpb": "BPB of parent experiment",
    "config": {
        "vocab_size": 8192,
        "n_layers": 11,
        "hidden_dim": 512,
        "n_heads": 8,
        "n_kv_heads": 4,
        "mlp_mult": 3,
        "quantization": "int6",
        "optimizer": "muoneq_r",
        "learning_rate": "auto",
        "weight_decay": 0.085,
        "warmdown_start": 3500,
        "max_steps": "auto (10 min budget)",
        "sequence_length": 2048,
        "batch_tokens": 524288,
        "recurrence_layers": [3, 4, 5],
        "recurrence_loops": 2,
        "CHANGE_DESCRIPTION": "What specifically changed from parent"
    },
    "created_at": "ISO datetime"
}
```

## Analysis Template (analysis.md)

```markdown
# Experiment exp_NNN: [Short Title]

## Hypothesis
[What I expected to happen and why]

## What Changed
[Specific diff from parent experiment — which lines of train_gpt.py changed]

## Results

| Metric | This Experiment | Parent (exp_MMM) | Delta |
|--------|----------------|-------------------|-------|
| val_bpb | X.XXXX | Y.YYYY | ±Z.ZZZZ |
| artifact_size | NN MB | NN MB | ±N MB |
| training_time | NNNs | NNNs | ±NNs |
| training_steps | NNNN | NNNN | ±NNN |

Seeds: [seed_1=X.XXXX, seed_2=X.XXXX, seed_3=X.XXXX]
Mean: X.XXXX ± X.XXXX std

## Analysis
[Why did this work or not work? What does it tell us about the technique?]

## Lessons for Knowledge Base
[What should be added to the technique doc? Any new conflicts discovered?]

## Next Steps
[What experiment to try next based on these results]
```

## Checklist

Before running:
- [ ] Created experiment in tracker: `pgolf track create --hypothesis "..." --techniques "..."`
- [ ] Copied and modified train_gpt.py
- [ ] Changes are minimal and targeted (one variable at a time)
- [ ] Checked knowledge/lessons_learned.md for known conflicts

After running:
- [ ] Parsed log: `pgolf parse experiments/exp_NNN/train.log`
- [ ] Recorded result: `pgolf track result exp_NNN --bpb X.XXXX --size NNNNNN`
- [ ] Wrote analysis.md
- [ ] Updated technique doc in knowledge/techniques/
- [ ] Updated lessons_learned.md if applicable
- [ ] Generated blog draft: `pgolf blog --day N --experiment exp_NNN`
- [ ] Git committed everything
