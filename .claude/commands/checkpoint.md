---
description: End-of-day routine. Writes journal entry, commits, reports progress vs plan and budget runway.
allowed-tools: Read, Write, Bash(git:*), Bash(python:*)
model: haiku
---


End-of-day checkpoint. Execute briefly and produce a one-screen summary for Abi.

## 1. Snapshot current state

```bash
python scripts/pgolf.py status
python scripts/pgolf.py spend status
```

Capture:
- Best BPB overall and how it moved today
- Experiments completed today vs. planned
- Total spend today and cumulative
- Runway at current pace

## 2. Write journal entry

Path: `journal/day_NN.md` (NN = day number of the competition, not date). Create the folder if it doesn't exist.

Template:
```markdown
# Day NN — April DD, 2026

## What happened
<One paragraph. What was tried, what worked, what didn't. Under 150 words.>

## Numbers
- Experiments created: X
- Experiments completed: X (Y GREEN, Z YELLOW, W RED)
- Best BPB today: X.XXXX (exp_NNN)
- Delta vs yesterday: +/- X.XXXX
- Spend today: $X.XX
- Cumulative spend: $X.XX of $500 (Y remaining)

## Tomorrow's plan
<One paragraph committing to tomorrow's focus. Specific enough that tomorrow's /morning can verify whether it happened.>

## Flags / open questions
<Anything that needs Abi's attention. Skip this section if none.>
```

## 3. Commit everything

```bash
git add -A
git status  # Review before committing

# Commit with a descriptive message
git commit -m "day NN: <top-level outcome>

- <key experiment results>
- <any knowledge base updates>
- spend: \$X.XX cumulative"
```

If the working tree is clean (nothing to commit), skip this step silently.

## 4. Runway check

Compute:
```
days_to_deadline = April 30 - today
spendable = (500 - total_spent - 60_reserve)
avg_daily_spend = total_spent / days_elapsed
runway_days = spendable / avg_daily_spend  (if avg_daily_spend > 0)
```

If `runway_days < days_to_deadline`: flag as **BUDGET RISK** in the summary. Suggest switching to 1×A100 for exploration (~50% cheaper) and holding 8×H100 runs for validated candidates only.

## 5. Chat summary for Abi

Print ONE screen, no more:

```
━━━ Day NN checkpoint ━━━

Best BPB:   X.XXXX  (↓ Y.YYYY vs yesterday)
SOTA gap:   +Z.ZZZZ
Experiments: X completed today (G/Y/R: X/X/X)
Spend:      $X.XX today, $X.XX cumulative
Runway:     X days spendable vs Y days to deadline

Tomorrow: <one-line plan>

<BUDGET RISK or other flags, if any>
```

That's it. Don't elaborate unless Abi asks. The journal entry is the long-form artifact.

## 6. Git push (optional, if configured)

If `git config --get remote.origin.url` returns a remote, suggest (but do not execute without confirmation):
```
git push origin main
```

## Gotchas

- If `git status` is clean, skip the commit step. Don't create empty commits.
- Journal entry before commit — the commit message references the journal.
- Don't push if tests fail. The scaffold is on GitHub; broken state should not go there.
