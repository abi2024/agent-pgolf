# CLAUDE.md

## Project Overview

This is an autonomous experiment toolkit for the OpenAI Parameter Golf competition.
Read `AGENTS.md` for the full operating protocol before doing anything.

## Key Commands

```bash
# Check current state
python scripts/pgolf.py status

# Create experiment
python scripts/pgolf.py track create --hypothesis "..." --techniques "a,b,c"

# Record results
python scripts/pgolf.py track result exp_NNN --bpb X.XXXX --size NNNNNN

# Parse a training log
python scripts/pgolf.py parse path/to/train.log

# Compare two experiments (needs ≥2 seeds each)
python scripts/pgolf.py parse --compare exp_001 exp_002

# Mark experiment as failed
python scripts/pgolf.py track fail exp_NNN --reason "OOM on forward pass"

# Generate blog post
python scripts/pgolf.py blog --day N --experiment exp_NNN

# List experiments
python scripts/pgolf.py track list
```

## Code Style

- Python 3.11+, type hints everywhere
- Scripts use only stdlib (no pip install needed for toolkit)
- Competition code (train_gpt.py) uses PyTorch + whatever the competition requires
- Experiment analysis in markdown, not notebooks

## File Conventions

- Technique docs: `knowledge/techniques/snake_case_name.md`
- Experiment folders: `experiments/exp_NNN/` with config.json, train_gpt.py, train.log, results.json, analysis.md
- Blog drafts: `blog/drafts/day_NN_short_title.md`

## When Running Experiments

1. Always create the experiment in the tracker FIRST
2. Copy the best train_gpt.py as starting point
3. Make targeted, minimal changes (one technique per experiment ideally)
4. Run smoke test (200 iters) before full run
5. Always record results, even failures
6. Git commit after each experiment

## When on RunPod

- Working directory: `/workspace/parameter-golf`
- Data already downloaded at: `./data/datasets/fineweb10B_sp1024/`
- Use tmux for long-running training
- 1xH100 for iteration, 8xH100 only for final submissions
