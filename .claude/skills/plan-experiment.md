---
name: plan-experiment
description: Propose one specific experiment with hypothesis, config diff, pre-registered decision rule, and conflict check. Reads broadly across prior experiments and knowledge before proposing. Does NOT run anything.
---

Abi has given you a focus. The argument is: $ARGUMENTS

Produce a precise experiment plan. **DO NOT create the experiment or run anything yet.** Output in this exact structure.

## 0. Read broadly before proposing

Before writing the plan, read these (this is non-optional):

```bash
# All prior analyses — look for patterns across ALL experiments, not just the parent
ls experiments/
cat experiments/*/analysis.md 2>/dev/null | head -500

# All known-bad combinations
cat knowledge/lessons_learned.md

# Cross-experiment observations (if /synthesize has been run)
cat knowledge/observations.md 2>/dev/null

# Current SOTA context
cat state/leaderboard.json | head -40

# Recent technique docs that touch what you're planning
ls knowledge/techniques/
```

You are looking for:
- **Failed directions that look like what you're about to propose** — don't repeat
- **Unexpected confounders** from prior runs (e.g., a specific seed behaves anomalously)
- **Signal in YELLOW results** that could stack with your planned technique
- **Gaps** — techniques in the current SOTA stack that have no corresponding experiment

This reading step takes 30 seconds and is the single biggest lever on plan quality. The full-trace scan is the insight validated in Meta-Harness (Lee et al., 2026): proposers that see raw traces outperform ones given summarized scores.

## 1. Parent experiment

State the exp_NNN this builds on, and its val_bpb (best seed). If no parent, state the baseline explicitly.

## 2. Hypothesis

One sentence, specific and falsifiable.

- BAD: "Try a smaller MLP"
- GOOD: "Reducing MLP expansion from 3× to 2.5× saves ~0.4MB, which can fund one more unique layer, and should improve BPB by ≥0.003 vs parent exp_NNN."

## 3. Prior-evidence check

Cite at least ONE piece of evidence from your step 0 read. Examples:

- "exp_003 tried a similar change and got YELLOW — my hypothesis refines it by [specifics]"
- "lessons_learned.md notes X conflicts with Y; my proposal avoids this by Z"
- "observations.md noted seed variance increases when N_layers > 11 — I'm staying at 11"
- "No prior experiment has touched this technique — expect high variance"

If you can't cite any prior evidence, that's a signal the scaffold has a blind spot here. Flag it.

## 4. Conflict check

```bash
grep -i "TECHNIQUE_NAME" knowledge/lessons_learned.md
```

Report any hits. If a KNOWN CONFLICT is found, REFUSE to propose this experiment. `pgolf track create` also runs this check.

## 5. Config diff

Show exactly which lines of the parent's `train_gpt.py` will change. Use diff format.

```diff
- OLD_LINE
+ NEW_LINE
```

If more than ~15 lines change, flag it — experiment is probably not "one variable at a time."

## 6. Pre-registered decision rule

- **Seed-1 continue threshold**: parent's best seed + 0.005 (generous for 7-day sprint)
- **Publication delta** (vs SOTA): 0.005 (competition rule)
- **Internal delta** (vs parent): 0.003

## 7. Cost estimate

- Smoke: free
- Screen (1×H100): ~$0.55
- Validate (3× 8×H100 incl. eval): ~$24

If current spendable budget doesn't cover Stage 3, flag it now.

## 8. Register and await approval

**Only on Abi's explicit approval**, run:

```bash
python scripts/pgolf.py track create \
    --hypothesis "<your hypothesis>" \
    --techniques "<comma,separated,techniques>" \
    --parent exp_NNN

python scripts/pgolf.py register-thresholds exp_NNN \
    --seed1-continue <value> \
    --publish 0.005 \
    --internal 0.003
```

Then hand off to `/run-experiment exp_NNN`.

## Output constraints

- Total output: one screen
- Step 0 (reading) happens before you write anything else
- If plan uses a technique with no `knowledge/techniques/*.md` doc, flag it as a risk
