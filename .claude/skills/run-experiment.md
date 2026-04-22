---
name: run-experiment
description: Execute a planned experiment through smoke → screen → validate stages, respecting cost gates and pre-registered thresholds.
---

Execute experiment $ARGUMENTS through the staged run protocol. **DO NOT skip stages.** Each stage produces a go/no-go decision.

## Stage 0: Pre-flight checks

Run these BEFORE any training:

```bash
# 1. Experiment exists and has config
cat experiments/$ARGUMENTS/config.json

# 2. Pre-registration exists
sqlite3 pgolf.db "SELECT * FROM pre_registration WHERE experiment_id='$ARGUMENTS'"

# 3. Thresholds are set (output must not be empty)
# If pre-registration is missing, STOP. Run /plan-experiment first.

# 4. Repo is clean
git status

# 5. Commit the config/script BEFORE running
git add experiments/$ARGUMENTS/
git commit -m "$ARGUMENTS: config for <hypothesis summary>"
```

If any pre-flight check fails, abort with a clear reason.

## Stage 1: Local smoke test (free)

Only run if Abi is on a machine with a local GPU. Otherwise skip to Stage 2.

```bash
cd experiments/$ARGUMENTS
RUN_ID=${ARGUMENTS}_smoke \
ITERATIONS=200 \
TRAIN_BATCH_TOKENS=8192 \
VAL_LOSS_EVERY=0 \
python train_gpt.py 2>&1 | tee smoke.log
```

**Pass conditions:**
- No crash, no OOM, no NaN in loss curve
- Artifact builds successfully
- Loss is decreasing (compare first 50 steps to last 50)

If smoke fails: `pgolf track fail $ARGUMENTS --reason "smoke: <reason>"` and stop.

## Stage 2: 1×H100 single-seed screen (~$0.55)

This is a budgeted action. The pre-bash hook will refuse if budget is tight.

```bash
cd experiments/$ARGUMENTS

RUN_ID=${ARGUMENTS}_seed1337 \
SEED=1337 \
MAX_WALLCLOCK_SECONDS=600 \
torchrun --standalone --nproc_per_node=1 train_gpt.py 2>&1 | tee train_seed1337.log
```

After completion:

```bash
python scripts/pgolf.py parse experiments/$ARGUMENTS/train_seed1337.log

# Extract val_bpb and size from the parse output, then:
python scripts/pgolf.py track result $ARGUMENTS \
    --bpb <val_bpb> \
    --size <bytes> \
    --time <wall_time_seconds> \
    --seed 1337 \
    --gpu 1xH100_SXM
```

**Decision gate — read the pre-registered seed-1 threshold:**
```bash
sqlite3 pgolf.db "SELECT seed1_continue_threshold FROM pre_registration WHERE experiment_id='$ARGUMENTS'"
```

- If seed-1 val_bpb **>** threshold: STOP. This experiment is screened out.
  - Write `experiments/$ARGUMENTS/analysis.md` explaining the screen-out.
  - Hand off to `/analyze-results $ARGUMENTS`.
  - DO NOT proceed to Stage 3.

- If seed-1 val_bpb **≤** threshold: proceed to Stage 3 (with Abi's confirmation).

## Stage 3: 3-seed 8×H100 validation (~$12 + ~$12 eval = ~$24)

**STOP. Ask Abi to explicitly confirm.** Do not proceed without a "go" message.

Once confirmed, note: the seed-1 result from Stage 2 was on 1×H100. For apples-to-apples comparison to SOTA (which is 8×H100), you typically need to re-run seed 1337 on 8×H100 too. Abi's judgment call on whether 1×H100 seed is valid to include.

```bash
cd experiments/$ARGUMENTS

for SEED in 1337 1338 1339; do
    RUN_ID=${ARGUMENTS}_8x_seed${SEED} \
    SEED=${SEED} \
    PGOLF_CONFIRM_8XH100=1 \
    MAX_WALLCLOCK_SECONDS=600 \
    torchrun --standalone --nproc_per_node=8 train_gpt.py 2>&1 | tee train_seed${SEED}.log

    python scripts/pgolf.py parse experiments/$ARGUMENTS/train_seed${SEED}.log

    python scripts/pgolf.py track result $ARGUMENTS \
        --bpb <val_bpb> \
        --size <bytes> \
        --time <wall_time_seconds> \
        --seed ${SEED} \
        --gpu 8xH100_SXM \
        --gpu-model "NVIDIA H100 80GB HBM3" \
        --torch-version "$(python -c 'import torch; print(torch.__version__)')" \
        --pg-commit "$(cd parameter-golf && git rev-parse HEAD)"
done
```

## Stage 4: Hand off

Once all seeds are recorded:

```
/analyze-results $ARGUMENTS
```

## Safety rails

- Never proceed Stage 2 → Stage 3 without explicit Abi confirmation
- Never skip Stage 1 when a local GPU is available
- If any stage crashes non-deterministically (pod preemption, network blip), retry ONCE. Second failure → investigate, don't retry blindly
- If cumulative spend for this experiment exceeds $40, stop and ask Abi
