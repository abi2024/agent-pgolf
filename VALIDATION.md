# VALIDATION.md — Local Checks Before Touching GPUs

Run through this entire checklist before funding your RunPod account or running any training. **Everything here is free.** The goal is to have zero surprises when you're spending real money.

## Automated checks (5 minutes)

### 1. Run the validation script

```bash
python scripts/validate_workflow.py --no-network
```

This exercises the full pipeline end-to-end in a temp directory with mock data. It validates:
- File structure (all files present, hooks executable)
- Python version + optional deps
- `pgolf.py` CLI: status, track, spend, parse, register-thresholds, submit-check
- Log parser: extracts the right values from fixtures, flags oversize, detects truncated logs
- Pre-bash hook: allows legit commands, blocks over-budget, blocks 8xH100 without confirm, blocks without MAX_WALLCLOCK
- Submit-check: refuses invalid mock submissions with actionable feedback

Expected output ends with:
```
✓ All validation checks passed.
  You're ready to start using the pipeline with Claude Code.
```

### 2. Test leaderboard fetch (needs internet)

```bash
python scripts/pgolf.py leaderboard fetch
```

Should print something like:
```
Fetched 42 scored PRs (28 merged)
Current SOTA: 1.0639 (PR #1577 by someuser)
```

If you hit GitHub API rate limits, wait an hour or run from a different IP.

### 3. Run the pytest suite

```bash
pip install pytest scipy  # if not installed
python -m pytest tests/ -v
```

Expected: all 33 tests pass. These are isolated unit tests for the parser, CLI, and hooks.

## Manual checks (10 minutes)

These require a human eye — the script can't catch everything.

### 4. Skim the seven skill files

```bash
ls -la .claude/commands/
cat .claude/commands/morning.md
```

Read each skill file. Check that:
- The workflow described matches how YOU want to work
- The commands referenced actually exist (`pgolf status`, `pgolf track create`, etc.)
- The statistical thresholds match your preference (0.005 publish, 0.003 internal)

If you want to change the workflow, edit the skill files — they're the Claude Code prompts, not commentary.

### 5. Review AGENTS.md once

```bash
less AGENTS.md
```

Check in particular:
- The "Critical constraints" section matches the competition rules you want to follow
- The "Budget discipline" numbers match your actual $500 / reserve split
- The override env vars (`PGOLF_FORCE`, `PGOLF_CONFIRM_8XH100`) match the hook

### 6. Sanity check the GPU rates

Open `scripts/pgolf.py` and search for `GPU_HOURLY_RATES`. Verify the dollar rates match what RunPod is currently charging you — rates change, and the hooks' budget math depends on these being right.

```python
GPU_HOURLY_RATES = {
    "1xA100_80GB": 1.64,
    "1xH100_PCIe": 2.49,
    "1xH100_SXM":  3.30,
    "8xH100_SXM": 24.72,
}
```

Go to https://www.runpod.io/pricing, compare against the SXM variants specifically, and update these rates if they've drifted.

### 7. Test hook integration with Claude Code

```bash
# Start Claude Code in the project
cd /path/to/pgolf-agent
claude

# In Claude Code, ask it to read the project
> read AGENTS.md and tell me what /morning does
```

Check that Claude Code:
- Finds and reads AGENTS.md
- Recognizes the skills in `.claude/commands/`
- Respects the hooks in `.claude/hooks/`

If Claude Code reports "I don't see any skills" or similar, check that `.claude/settings.json` is pointed at by the version of Claude Code you're using.

### 8. Dry-run a fake experiment

```bash
# Create a fake experiment
python scripts/pgolf.py track create \
    --hypothesis "validation run — do not actually train" \
    --techniques "baseline"

# Pre-register thresholds
python scripts/pgolf.py register-thresholds exp_001 \
    --seed1-continue 1.10 \
    --publish 0.005 \
    --internal 0.003

# Simulate recording 3 seeds
for SEED in 1337 1338 1339; do
    python scripts/pgolf.py track result exp_001 \
        --bpb 1.085 --size 15800000 --time 598 \
        --seed $SEED --gpu 8xH100_SXM \
        --gpu-model "NVIDIA H100 80GB HBM3" \
        --torch-version 2.8.0+cu128 \
        --pg-commit abc1234
done

# See what it looks like
python scripts/pgolf.py status
python scripts/pgolf.py track list

# Try submit-check (will fail because mock data isn't better than SOTA)
python scripts/pgolf.py submit-check exp_001

# Clean up the fake experiment when done
rm -rf experiments/exp_001
rm pgolf.db
touch state/spending.jsonl
```

The point: you've exercised every critical command with your own hands, so nothing surprises you in production.

### 9. Test the hook from a real shell

```bash
# This should succeed
./.claude/hooks/pre-bash.sh "ls"
echo "exit: $?"  # 0

# This should succeed (assuming fresh spending)
./.claude/hooks/pre-bash.sh \
    "MAX_WALLCLOCK_SECONDS=600 torchrun --standalone --nproc_per_node=1 train.py"
echo "exit: $?"  # 0

# This should fail (no confirmation for 8xH100)
./.claude/hooks/pre-bash.sh \
    "MAX_WALLCLOCK_SECONDS=600 torchrun --standalone --nproc_per_node=8 train.py"
echo "exit: $?"  # 1

# This should succeed
PGOLF_CONFIRM_8XH100=1 ./.claude/hooks/pre-bash.sh \
    "MAX_WALLCLOCK_SECONDS=600 torchrun --standalone --nproc_per_node=8 train.py"
echo "exit: $?"  # 0
```

### 10. Check your actual budget state

```bash
# What rates does the hook think apply?
grep -A 6 "case" .claude/hooks/pre-bash.sh

# What does the hook think the budget is?
grep "BUDGET\|RESERVE" .claude/hooks/pre-bash.sh
```

If these don't match your actual credit balance and desired reserve, either:
- Edit the hook defaults, or
- Set `PGOLF_BUDGET=X PGOLF_RESERVE=Y` in your shell environment

## Post-validation checklist

When all of the above pass, you're ready to:

- [ ] Fund your RunPod account (if not already done)
- [ ] Clone `parameter-golf` alongside this repo (`git clone https://github.com/openai/parameter-golf.git`)
- [ ] Download the SP8192 dataset on your first RunPod instance
- [ ] Initialize git in this repo and make your first commit
- [ ] Fetch the live leaderboard one more time: `python scripts/pgolf.py leaderboard fetch`
- [ ] Start Claude Code in this directory
- [ ] Tell it: "Read AGENTS.md and run /morning"

## If validation fails

- **Missing file**: Re-unpack the tarball cleanly into an empty directory
- **Hook not executable**: `chmod +x .claude/hooks/*.sh scripts/*.py`
- **Python version too old**: Upgrade to Python 3.11+
- **Import errors in pgolf.py**: Check stdlib only — no pip packages required for core CLI
- **Conflict check not firing**: Check that `knowledge/lessons_learned.md` uses the `### X + Y = BAD` format
- **Log parser test failing**: The regex patterns may need tweaking for your actual competition log format. Look at a real training log from the competition repo's `records/` folder and diff it against our fixtures.

## When the competition ends

Run `python scripts/pgolf.py status` and `python scripts/pgolf.py spend status` one last time. Copy your final numbers into `journal/final.md`. Archive the repo — future you will want to remember this.
