---
name: synthesize
description: Read all prior experiments and write knowledge/observations.md with cross-experiment patterns. Run after every 3-4 experiments, or when something feels off. Feeds future /plan-experiment calls.
---

You are doing post-hoc pattern mining across experiments. The output is `knowledge/observations.md`, which later `/plan-experiment` invocations will read.

This skill is inspired by the Meta-Harness finding that proposers improve when they see patterns across *many* runs, not just the most recent one. But Claude Code's context is limited, so we stage this: periodically synthesize patterns into a structured doc, which future proposals can grep.

## 1. Read the landscape

```bash
# List all experiments
sqlite3 pgolf.db "SELECT id, status, val_bpb, hypothesis FROM experiments ORDER BY id"

# Read every analysis.md
for f in experiments/*/analysis.md; do
    echo "=== $f ==="
    cat "$f"
done

# Read seed variance for each
sqlite3 pgolf.db "SELECT experiment_id, COUNT(*) as n, AVG(val_bpb), MIN(val_bpb), MAX(val_bpb), ROUND(MAX(val_bpb) - MIN(val_bpb), 4) as range FROM seeds GROUP BY experiment_id ORDER BY experiment_id"

# Read technique doc current state
ls knowledge/techniques/
cat knowledge/lessons_learned.md
```

## 2. Look for these specific patterns

For each, write a finding only if there is evidence. Do NOT speculate:

### A. Monotonic trends
Plot (in your head) val_bpb as you added each technique. Is there a clear descent? A plateau? An inflection where nothing more helps?

### B. Seed-variance signal
Which experiments had std > 0.002 across seeds? Which had std < 0.0005? Seed variance patterns indicate architectural instability or underconverged training.

### C. Consistent conflicts
If two experiments both tried technique X with different parents and both came out YELLOW, that's a conflict worth elevating.

### D. Compound effects
If exp_A gave +0.003 and exp_B gave +0.004, but exp_C (A+B) gave +0.005, they're non-additive. Note it — the stacking assumption is weaker than we thought.

### E. Dead zones
What techniques did you TRY and find RED? Document them explicitly so future `/plan-experiment` doesn't re-propose.

### F. Gaps
What techniques in current SOTA stack (see `state/leaderboard.json`) have you NOT yet tried? Flag them as next-experiment candidates.

## 3. Write knowledge/observations.md

Follow this structure exactly. If a section has no evidence, write "No evidence yet." — do not invent findings.

```markdown
# Cross-experiment observations

*Generated: <ISO datetime> by /synthesize. Based on experiments exp_NNN through exp_MMM.*

## Monotonic trends
<Bullet points with specific BPB numbers and experiment IDs. E.g., "BPB dropped monotonically from exp_001 (1.12) → exp_003 (1.10) → exp_005 (1.09). No plateau yet.">

## Seed variance by experiment
| Experiment | n_seeds | Mean | Std | Range | Notes |
|------------|---------|------|-----|-------|-------|
| exp_001 | 3 | ... | ... | ... | ... |

Flag any experiment where std > 0.002.

## Confirmed conflicts
<Beyond what's in lessons_learned.md — new pairs discovered across these experiments.>

## Non-additive stacks
<Pairs where combining didn't give the sum of individual gains.>

## Dead zones (do not retry without strong reason)
<RED experiments with clear mechanism — "technique X under condition Y produces result Z in exp_NNN.">

## Gaps vs current SOTA
<Techniques in state/leaderboard.json's current_sota_title that we haven't tested.>

## Recommendations for next /plan-experiment
<Three concrete candidate directions, each with a one-line rationale.>

## Blind spots
<What you wanted to check but couldn't — e.g., "only 2 seeds run on exp_004; can't statistically confirm." Flag for future work.>
```

## 4. Commit the output

```bash
git add knowledge/observations.md
git commit -m "synthesize: observations across exp_NNN-MMM"
```

## 5. Tell Abi what changed

Print a SHORT chat summary:

```
Synthesized across N experiments.

Key new observations:
- <one line>
- <one line>
- <one line>

Recommendations feed next /plan-experiment.
```

## When to run

- After every 3-4 completed experiments
- Before any major strategic pivot (e.g., switching tracks)
- Always before the Day 4 mid-sprint checkpoint

## When NOT to run

- Before any experiments have completed (there's nothing to synthesize)
- Mid-experiment (wait until analysis.md is written)
- As a substitute for actually running experiments (synthesis without new data is just re-reading)
