# CLAUDE.md

## Project overview

This is a structured toolkit for OpenAI's Parameter Golf challenge. Read `AGENTS.md` for the full operating protocol before doing anything.

**Skills are the canonical workflow.** Use `/morning`, `/plan-experiment`, `/run-experiment`, `/analyze-results`, `/blog`, `/checkpoint`, `/submit-check` instead of ad-hoc commands.

## Command reference

### Status & state
```bash
python scripts/pgolf.py status                 # experiments + SOTA gap + spend + lineage tree
python scripts/pgolf.py report                 # full REPORT.md at project root (open in VSCode)
python scripts/pgolf.py doctor                 # diagnostic health check
python scripts/pgolf.py spend total            # total $ spent
python scripts/pgolf.py spend status           # full spending breakdown
python scripts/pgolf.py leaderboard fetch      # update state/leaderboard.json
python scripts/pgolf.py leaderboard current    # print cached SOTA
```

### Experiment tracking
```bash
# Create — fails if techniques conflict per lessons_learned.md
python scripts/pgolf.py track create \
    --hypothesis "..." \
    --techniques "a,b,c" \
    --parent exp_NNN              # optional

# Pre-register decision rule — DO THIS BEFORE ANY SEEDS RUN
python scripts/pgolf.py register-thresholds exp_NNN \
    --seed1-continue 1.10 \
    --publish 0.005 \
    --internal 0.003

# Record a seed result
python scripts/pgolf.py track result exp_NNN \
    --bpb 1.0850 \
    --size 15800000 \
    --time 598 \
    --seed 1337 \
    --gpu 8xH100_SXM \
    --torch-version 2.8.0+cu128 \
    --pg-commit <hash>

# Mark failure
python scripts/pgolf.py track fail exp_NNN --reason "OOM on forward"

# List recent
python scripts/pgolf.py track list --limit 15
```

### Parsing
```bash
# Parse one log — extracts final_int8_zlib_roundtrip_exact val_bpb specifically
python scripts/pgolf.py parse experiments/exp_NNN/train_seed1337.log

# Compare two experiments — Welch's t-test, internal threshold 0.003
python scripts/pgolf.py parse --compare exp_NNN exp_MMM --threshold 0.003
```

### Pre-submission
```bash
# Paranoid pre-PR validation — exits non-zero if any check fails
python scripts/pgolf.py submit-check exp_NNN
```

### Blog
```bash
# Creates a scaffold — the /blog skill does the real writing
python scripts/pgolf.py blog --day 3 --experiment exp_NNN
```

## Override environment variables

The pre-bash hook gates expensive commands. Overrides:

- `PGOLF_FORCE=1` — bypass budget gate (don't casually use)
- `PGOLF_CONFIRM_8XH100=1` — required for every 8×H100 run
- `PGOLF_NO_WALLCLOCK=1` — run without MAX_WALLCLOCK_SECONDS (breaks competition constraint)

Budget configuration:
- `PGOLF_BUDGET=500` — total budget (default)
- `PGOLF_RESERVE=60` — untouchable reserve (default)

## Code style

- Python 3.11+, type hints for public functions
- `scripts/pgolf.py` uses stdlib only (scipy optional for p-values)
- Experiment code (`train_gpt.py`) uses PyTorch + whatever the competition requires
- Analyses in markdown, not notebooks

## File conventions

- Technique docs: `knowledge/techniques/snake_case_name.md`
- Experiment folders: `experiments/exp_NNN/` with `config.json`, `train_gpt.py`, `train_seed*.log`, `analysis.md`
- Blog drafts: `blog/drafts/day_NN_short_title.md`
- Journal entries: `journal/day_NN.md`
- Training logs: `train_seed<SEED>.log` (the hook uses this naming to find recent logs)

## Rules for running experiments

1. Always `/plan-experiment` first — creates exp, registers thresholds
2. Copy the best train_gpt.py as starting point
3. Make minimal, targeted changes (one variable at a time)
4. Run smoke test (200 iters) before any H100 run when a local GPU is available
5. Seed 1 on 1×H100 screens; seeds 1-3 on 8×H100 validate
6. Always record seed results via `track result`, even failures
7. `/analyze-results` applies the pre-registered rule mechanically — don't rationalize around it
8. Git commit after each experiment — use `/checkpoint` at end of day

## When on RunPod

- Working directory: `/workspace/parameter-golf` for competition code, `/workspace/pgolf-agent` for this toolkit
- Data at: `./data/datasets/fineweb10B_sp<N>/`
- Use tmux for long-running training
- 1×H100 for iteration, 8×H100 only for 3-seed validation of promising candidates
- Always set `MAX_WALLCLOCK_SECONDS=600` — enforces competition constraint, and the pre-bash hook refuses without it
