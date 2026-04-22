---
name: analyze-results
description: Parse experiment results, apply pre-registered decision rule, update knowledge base, propose next step.
---

Produce a complete analysis of experiment $ARGUMENTS. This updates the knowledge base — it must be careful and thorough.

## 1. Parse all logs

```bash
for log in experiments/$ARGUMENTS/train*.log; do
    python scripts/pgolf.py parse "$log"
done
```

For each seed, verify:
- `has_final_bpb: true` (authoritative metric present)
- No `warnings` array entries (or understand them if present)
- val_bpb is consistent with what was recorded via `track result`

If any log is missing the `final_int8_zlib_roundtrip_exact` line, the run was truncated — mark that seed as invalid and flag it.

## 2. Sanity checks — RED flags

Any of these makes the experiment automatically RED regardless of BPB:

- Artifact size > 16MB on any seed
- Wall time > 600s on any seed (invalid per competition rules)
- `val_bpb` disagrees across different sections of the log (parser confusion — investigate)
- `std` across seeds > 0.003 (unusually high variance — one seed is probably an outlier and should be re-run before publishing)

## 3. Statistical test vs parent

If 3+ seeds exist, run:

```bash
python scripts/pgolf.py parse --compare $ARGUMENTS <parent_id> --threshold 0.003
```

This uses Welch's t-test (unequal variance) with the internal threshold 0.003.

## 4. Apply pre-registered rule

Fetch the rule:
```bash
sqlite3 pgolf.db "SELECT decision_rule, publish_delta, internal_delta, parent_best_bpb, sota_bpb_at_registration FROM pre_registration WHERE experiment_id='$ARGUMENTS'"
```

Apply the rule mechanically, NOT based on how you feel about the result:

- **GREEN (publishable)**: 3-seed mean ≤ SOTA - publish_delta (typically 0.005) at p<0.01 vs SOTA. Candidate for a leaderboard PR.
- **YELLOW (stack internally)**: 3-seed mean ≤ parent - internal_delta (typically 0.003) at p<0.01 vs parent. Not publishable alone but useful to stack with future techniques.
- **RED (document and move on)**: Neither threshold met. Still useful — write a negative result into `knowledge/lessons_learned.md` if there's a general lesson.

## 5. Write experiments/$ARGUMENTS/analysis.md

Follow `TEMPLATE.md`. Required sections:

- **Hypothesis** (pulled from config.json)
- **Pre-registered rule** (pulled from DB)
- **Results table**: row per seed, then mean/std row, with artifact size and wall time
- **Decision**: GREEN / YELLOW / RED with explicit rationale
- **What this tells us** about the technique (for knowledge base)
- **Confounders** considered (e.g., different PyTorch version between seeds? different GPU model?)

## 6. Update knowledge base

### 6a. Technique doc
For each technique in the stack, append a row to `knowledge/techniques/<technique>.md` under "My Experiments":

```markdown
| exp_NNN | parent_id | 3-seed mean X.XXXX ± Y.YYYY | GREEN/YELLOW/RED | One-line takeaway |
```

If the technique doc doesn't exist, create it using the skeleton structure seen in existing docs.

### 6b. Lessons learned
If a new conflict was discovered (technique A + technique B = unexpected bad result), append a section to `knowledge/lessons_learned.md`:

```markdown
### Technique A + Technique B = BAD
- **What happened**: ...
- **Why**: ...
- **Evidence**: exp_NNN showed <specific numbers>
```

The `= BAD` string is load-bearing — the conflict check in `track create` looks for it.

### 6c. SOTA timeline
If this was a GREEN result, append a row to `knowledge/sota_timeline.md` (but do NOT claim it's SOTA until the PR is merged — mark as "candidate").

## 7. Commit

```bash
git add experiments/$ARGUMENTS/analysis.md knowledge/
git commit -m "$ARGUMENTS: <GREEN|YELLOW|RED> <one-line summary>"
```

## 8. Propose next step

Based on decision:

- **GREEN** → recommend `/submit-check $ARGUMENTS` to validate for PR filing
- **YELLOW** → recommend `/plan-experiment` with a hypothesis that stacks this result with a next promising technique
- **RED** → recommend `/plan-experiment` with a different direction entirely. Don't throw good money after bad.

## Output discipline

- analysis.md is the long-form artifact. Your chat output should be brief: the GREEN/YELLOW/RED, the numbers, and the proposed next step.
- Apply the pre-registered rule mechanically. If seed-1 looks great but the rule says screened-out, it's screened-out — don't rationalize continuing.
