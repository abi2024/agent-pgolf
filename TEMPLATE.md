# Experiment Template

## config.json

```json
{
    "id": "exp_NNN",
    "hypothesis": "SPECIFIC, falsifiable hypothesis",
    "technique_stack": ["technique_1", "technique_2"],
    "parent_id": "exp_MMM",
    "baseline_bpb": null,
    "config": {
        "vocab_size": 8192,
        "n_layers": 11,
        "hidden_dim": 512,
        "n_heads": 8,
        "n_kv_heads": 4,
        "mlp_mult": 3,
        "quantization": "int6",
        "optimizer": "muoneq_r",
        "learning_rate": null,
        "weight_decay": 0.085,
        "warmdown_start": 3500,
        "max_steps": null,
        "sequence_length": 2048,
        "batch_tokens": 524288,
        "recurrence_layers": [3, 4, 5],
        "recurrence_loops": 2,
        "CHANGE_DESCRIPTION": "What specifically changed from parent"
    },
    "created_at": "2026-04-17T14:30:00"
}
```

Note: use `null` for unset values, not strings like `"auto"` — the downstream tooling assumes these are numeric.

## analysis.md template

```markdown
# Experiment exp_NNN: [Short Title]

## Hypothesis
[What I expected to happen and why, pulled from config.json]

## Pre-registered decision rule
[From pgolf.db pre_registration table — verbatim. If missing, flag it.]

- Seed-1 continue threshold: X.XXXX
- Publish delta vs SOTA: 0.005
- Internal delta vs parent: 0.003

## What changed
[Specific diff from parent experiment — which lines of train_gpt.py changed. Short, literal.]

```diff
- OLD_LINE
+ NEW_LINE
```

## Results

| Seed | val_bpb | Artifact size | Wall time | GPU |
|------|---------|---------------|-----------|-----|
| 1337 | X.XXXX  | NN.NN MB      | NNNs      | 8xH100_SXM |
| 1338 | X.XXXX  | NN.NN MB      | NNNs      | 8xH100_SXM |
| 1339 | X.XXXX  | NN.NN MB      | NNNs      | 8xH100_SXM |
| **mean** | **X.XXXX** | — | — | — |
| **std**  | **X.XXXX** | — | — | — |

### Comparison

| Metric | This experiment | Parent (exp_MMM) | SOTA | Delta vs parent | Delta vs SOTA |
|--------|----------------|-------------------|------|-----------------|---------------|
| Mean BPB | X.XXXX | Y.YYYY | Z.ZZZZ | ±Δ.ΔΔΔΔ | ±Δ.ΔΔΔΔ |

Statistical test vs parent: Welch's t, t=T.TTT, p=P.PPPP

## Decision
**GREEN / YELLOW / RED** because [explicit rationale referencing the pre-registered rule, not gut feeling].

## Analysis
[Why did this work or not work? What does it tell us about the technique? Was the hypothesis right, partially right, or wrong? If partially right, what's the refined version?]

## Confounders considered
[Were all seeds on the same GPU model? Same torch version? Same parameter-golf commit? Any infrastructure differences between seeds?]

## Lessons for knowledge base
[What should be added to the technique doc in knowledge/techniques/? Any new conflict to add to lessons_learned.md?]

## Next steps
[Specific next experiment — technique + hypothesis + why it follows from this result]
```

## Pre-experiment checklist

Before running:
- [ ] `/plan-experiment` produced and Abi approved
- [ ] `pgolf track create` ran successfully (no unaddressed conflicts)
- [ ] `pgolf register-thresholds` ran with concrete numbers
- [ ] Parent's train_gpt.py copied and modified (minimal changes, one variable)
- [ ] git committed the config + script before training

## Post-experiment checklist

After running:
- [ ] `pgolf parse` run on each seed's log
- [ ] `pgolf track result` recorded each seed with --torch-version, --pg-commit, --gpu-model
- [ ] analysis.md written following the template above
- [ ] knowledge/techniques/<primary>.md updated with "My Experiments" row
- [ ] lessons_learned.md updated if a new conflict was discovered
- [ ] git commit with descriptive message
- [ ] If GREEN: `/submit-check` run (paranoid validation before PR)
- [ ] `/blog` run to draft the day's post
