---
description: Start-of-day routine. Refreshes leaderboard, reviews last 24h, proposes today's focus, confirms budget.
allowed-tools: Read, Bash(python:*), Bash(cat:*), Bash(ls:*)
model: sonnet
---


You are starting a new day of Parameter Golf work for Abi. Execute these steps in order, briefly. Keep the whole thing under 400 words. Abi reads this over coffee.

## Step 1 — Refresh leaderboard
Run:
```
python scripts/pgolf.py leaderboard fetch
```
Compare the returned SOTA to `knowledge/sota_timeline.md`. If the SOTA moved since your last run, flag:
- What technique caused the movement (read the PR title)
- Whether any `knowledge/lessons_learned.md` entries are now stale (e.g., "EMA bad" may need qualification if a new SOTA used EMA variants)
- Whether this SOTA uses techniques on Abi's planned list (priority shift?)

## Step 2 — Spend check
Run:
```
python scripts/pgolf.py spend status
```
Report: spent / remaining / implied runs left at current pace. If remaining < $100 with >5 days to deadline, flag as YELLOW. If remaining < $50, flag as RED and skip to Step 5 with an emergency-mode proposal.

## Step 3 — Experiment review
Run:
```
python scripts/pgolf.py track list --limit 10
```
Identify:
- Best BPB result in the last 24h (and how it compares to parent)
- Any experiments still in `planned` or `running` status >6h old (possible crashes — investigate logs)
- Any `failed` experiments without a diagnosis note — add one now if trivially diagnosable from the log

## Step 4 — Technique gap analysis
Scan `knowledge/techniques/*.md` briefly. For each technique in the current SOTA stack (from `state/leaderboard.json`):
- Does Abi have a corresponding technique doc?
- Does that doc have "My Experiments" entries, or is it still empty?

The highest-leverage gap is: a technique in the current SOTA stack that Abi has NOT yet tried.

## Step 5 — Propose today's focus
Propose 1-2 experiment directions. For EACH, give:
- **Hypothesis** (one sentence, specific and falsifiable)
- **Parent experiment** (exp_NNN that this builds on)
- **Expected cost** (smoke+screen=$0.55, full validation=$24)
- **Risk** (low / medium / high — based on how novel vs. how reproductive)
- **Evidence** (1 sentence pointing at knowledge/ supporting this direction)

## Step 6 — Ask for approval
End with: "Pick one (A/B) or redirect. No experiments run until you confirm."

Do NOT proceed to `/plan-experiment` without an explicit choice from Abi.

## Gotchas

- Don't skip the leaderboard fetch even if you ran it yesterday. SOTA moves fast.
- If remaining budget < $50, skip the "propose two directions" step. One direction only, or recommend pause.
- `pgolf status` uses the cached leaderboard. If it says "unknown" the cache is missing — fetch first.
