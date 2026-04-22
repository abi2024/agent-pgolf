# WORKFLOW.md — How to operate this scaffold

Your scaffold is already built. This document is how to use it effectively across the remaining 7 days.

## The mental model in one picture

```
┌────────────────────────────────────────────────────────────────────┐
│                                                                    │
│   YOU (Abi)                                                        │
│      │                                                             │
│      │ 1. opens Claude Code in pgolf-agent/                        │
│      │ 2. types /morning                                           │
│      ▼                                                             │
│   ┌────────────────┐                                               │
│   │  /morning      │  reads: state/leaderboard.json,               │
│   │                │         spending.jsonl, experiments/,         │
│   │                │         knowledge/observations.md             │
│   │                │  writes: nothing (proposes options)           │
│   └────────┬───────┘                                               │
│            │                                                       │
│            │ picks track A or B                                    │
│            ▼                                                       │
│   ┌────────────────┐                                               │
│   │ /plan-experim. │  reads: ALL analyses, ALL lessons,            │
│   │                │         observations.md, technique docs       │
│   │                │  writes: experiment config + pre-registration │
│   │                │  HUMAN APPROVES before any code runs          │
│   └────────┬───────┘                                               │
│            │                                                       │
│            ▼                                                       │
│   ┌────────────────┐                                               │
│   │ /run-experim.  │  stages: smoke → 1×H100 screen →              │
│   │                │          3× 8×H100 validate                   │
│   │                │  hooks:  pre-bash.sh gates budget             │
│   │                │          post-bash.sh logs actual spend       │
│   │                │  HUMAN APPROVES before 8×H100 stage           │
│   └────────┬───────┘                                               │
│            │                                                       │
│            ▼                                                       │
│   ┌────────────────┐                                               │
│   │ /analyze-res.  │  applies pre-registered rule MECHANICALLY     │
│   │                │  writes: analysis.md, updates technique doc   │
│   │                │  proposes next step based on GREEN/YELLOW/RED │
│   └────────┬───────┘                                               │
│            │                                                       │
│            │ after 3-4 experiments:                                │
│            ▼                                                       │
│   ┌────────────────┐                                               │
│   │ /synthesize    │  reads ALL analyses, writes patterns to       │
│   │                │  knowledge/observations.md                    │
│   │                │  (feeds next /plan-experiment)                │
│   └────────┬───────┘                                               │
│            │                                                       │
│            ▼                                                       │
│   ┌────────────────┐                                               │
│   │ /checkpoint    │  end-of-day commit + runway check             │
│   └────────┬───────┘                                               │
│            │                                                       │
│            │ for GREEN candidates only:                            │
│            ▼                                                       │
│   ┌────────────────┐                                               │
│   │ /submit-check  │  paranoid pre-PR validation                   │
│   │                │  produces PR-ready summary                    │
│   │                │  HUMAN files PR manually                      │
│   └────────────────┘                                               │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

## The outer loop — one cycle per experiment

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ 1. PROPOSE  │────▶│  2. RUN     │────▶│  3. DECIDE  │
│ plan-exp    │     │ run-exp     │     │ analyze-res │
└─────────────┘     └─────────────┘     └──────┬──────┘
       ▲                                       │
       │                                       │
       │         ┌─────────────────────┐       │
       └─────────┤ 4. (periodically)   │◀──────┘
                 │ /synthesize writes  │
                 │ observations.md     │
                 └─────────────────────┘
```

Every proposal reads *all* prior analyses and observations. Every analysis updates the knowledge base. Observations are mined every 3-4 cycles. This is what makes it an auto-research loop rather than a task runner.

## Commands you'll use every day

**Seeing what's going on:**
```bash
python scripts/pgolf.py status         # one-screen overview with lineage tree
python scripts/pgolf.py report         # full REPORT.md written to project root
python scripts/pgolf.py spend status   # money breakdown by day / GPU
python scripts/pgolf.py leaderboard current  # cached SOTA
python scripts/pgolf.py doctor         # diagnostic — run when things feel off
```

**In Claude Code (slash commands):**
```
/morning                    # start-of-day: leaderboard, budget, proposal
/plan-experiment <focus>    # propose one experiment
/run-experiment exp_NNN     # execute with gates
/analyze-results exp_NNN    # GREEN/YELLOW/RED decision
/synthesize                 # cross-experiment pattern mining
/blog <day> <exp>           # 800-1200 word post, not a form
/checkpoint                 # end-of-day commit + runway
/submit-check exp_NNN       # paranoid PR validation
```

## Your exact 7-day workflow

### Day 1 — Setup, baseline, first real experiment

**Morning (30 min):**
```bash
# In the pod terminal
cd /workspace/pgolf-agent
python scripts/validate_workflow.py   # confirms scaffold works
python scripts/pgolf.py doctor        # will fail on "no leaderboard" — fix next
python scripts/pgolf.py leaderboard fetch
python scripts/pgolf.py doctor        # should now pass
```

**Then start Claude Code in the pod:**
```
> Read AGENTS.md and run /morning
```

`/morning` will produce 1-2 experiment proposals. Pick one. Probably: "reproduce the current SOTA stack" as exp_001 so you know your pipeline produces a trustable number.

**Afternoon:**
```
> /plan-experiment reproduce current SOTA to verify pipeline
```

Approve the plan. Then:
```
> /run-experiment exp_001
```

This will run smoke → 1×H100 screen. Cost: ~$0.55. At end of screen, Claude Code asks if you want to proceed to 3×8×H100. For Day 1 reproduction, the answer is usually "skip the 3-seed validate — we just want to confirm the pipeline works."

**Evening:**
```
> /analyze-results exp_001
> /checkpoint
```

First day done. You've confirmed the pipeline and have one clean data point.

### Days 2-3 — Track A (record chase)

Each day is 1-2 experiments. The loop:

```
/morning                    # quick check
/plan-experiment <idea>     # proposal with wide context read
<approve>
/run-experiment exp_NNN     # smoke + 1×H100 screen
<if promising, approve 8×H100>
/analyze-results exp_NNN    # decision
/checkpoint                 # end of day
```

Expected: by end of Day 3, you have 3-4 experiments. Probably 0-1 GREEN, rest YELLOW/RED. That's normal.

**At the end of Day 3, run `/synthesize`.** This is the first time the observation-mining skill is worth running. It'll write `knowledge/observations.md` with cross-experiment patterns. This feeds all subsequent `/plan-experiment` calls.

### Days 4-5 — Track B (non-record research)

Start from the `knowledge/research_framing.md` doc. Pick the direction you chose (LaCT, tokenizer ablation, or TTT variant). Plan carefully — non-record PRs are read for *writing quality* as much as for numbers.

```
/plan-experiment track B: LaCT port to Parameter Golf harness
```

Day 4 morning should also include a mid-sprint reassessment — look at `python scripts/pgolf.py report`, honestly assess what's realistic, and possibly pivot.

### Day 6 — Validation and PR prep

For your GREEN candidate (if any):
```
/submit-check exp_NNN
```

If passes: prepare the PR branch based on `upstream/main` (see below).

For your Track B submission:
- Draft the non-record README following `knowledge/research_framing.md`
- Run `/blog` for the retrospective

### Day 7 — Submit

Morning: file PRs. Post blog. Done.

## How to see everything at once

Four progressively-deeper views:

**Quick glance (10 seconds):**
```bash
python scripts/pgolf.py status
```
One screen: SOTA gap, top 5 results, lineage tree.

**Full picture (30 seconds):**
```bash
python scripts/pgolf.py report
code REPORT.md
```
Writes REPORT.md at project root. Open in VSCode — renders markdown beautifully with the lineage tree, every experiment's seeds, every analysis.md embedded in collapsible sections, spending breakdown, knowledge base status.

**Claude Code's view (what it sees before proposing):**
Claude Code reads all `experiments/*/analysis.md`, `knowledge/lessons_learned.md`, `knowledge/observations.md`, `state/leaderboard.json`. You can verify by running:
```bash
ls experiments/*/analysis.md
cat knowledge/observations.md
```

**The audit trail (for the PR):**
```bash
git log --all --oneline
```
Every experiment is committed. Every analysis is committed. The timeline is reconstructable.

## Visibility within Claude Code

When inside Claude Code, ask directly:

```
> show me the top 5 experiments
> what went wrong with exp_004?
> what techniques haven't I tried yet vs current SOTA?
> summarize knowledge/observations.md
> is the budget on track?
```

The agent has full filesystem access and can grep, cat, and read anything. The `/morning` and `/plan-experiment` skills already do this reading automatically. You can also ask freeform questions between commands.

## The one skill you'll forget to use

`/synthesize`. Run it after every 3-4 completed experiments. It's the single biggest quality lever on future proposals. Takes 1-2 minutes of Claude Code time, no GPU cost.

If you haven't run it by Day 4 morning, run it before `/plan-experiment`.

## When things go wrong

**Claude Code seems confused about state:**
```
> /morning
```
Forces a full re-read. Usually fixes drift.

**Numbers don't match the DB:**
```bash
python scripts/pgolf.py doctor
```
Catches schema drift, missing state files, stale leaderboard, budget issues.

**A training run mysteriously failed:**
```bash
cat experiments/exp_NNN/train_seed*.log | tail -50
python scripts/pgolf.py parse experiments/exp_NNN/train_seed1337.log
```
The parser output shows `warnings` array — check there first.

**Spend doesn't match RunPod dashboard:**
```bash
cat state/spending.jsonl | python -m json.tool
```
Each line is a timestamped event. Check the post-bash hook logged all your torchruns.

**You want a clean slate:**
Don't. It's almost never the right move. Fix the specific thing that's broken. The DB is append-only; deleting it loses research history.

## Anti-patterns (don't do these)

1. **Running experiments in parallel overnight unsupervised.** The budget can't absorb a runaway loop. Always human-in-loop on 8×H100 stages.

2. **Skipping `/plan-experiment`.** The pre-registration is what prevents optional stopping. No plan = no pre-registration = statistics are suspect.

3. **Rationalizing past the pre-registered rule.** If seed-1 is over the threshold, the experiment is screened out. Don't "just try one more seed to see."

4. **Editing `train_gpt.py` directly in `parameter-golf/`.** Always work in `experiments/exp_NNN/train_gpt.py`. The competition repo is a reference, not your workspace.

5. **Adding techniques you haven't read the paper for.** The wide-context reading in `/plan-experiment` assumes the knowledge base is real. Fake technique docs poison future proposals.

6. **Filing PRs before `/submit-check` passes.** There's a reason the checks are paranoid.

## How the Meta-Harness insight shows up

The scaffold was upgraded based on the Meta-Harness paper (Lee et al., 2026). Concretely:

- `/plan-experiment` reads ALL prior `analysis.md` files and `knowledge/observations.md` before proposing. This is the "full-trace filesystem context" pattern from the paper.
- `/synthesize` periodically mines patterns across experiments and writes structured observations. This is the "cross-run diagnostic" pattern.
- `knowledge/research_framing.md` helps you position test-time harness modifications (LaCT, LoRA-TTT) as the paper-cited research direction they actually are.

You are NOT running an unsupervised outer loop à la Meta-Harness. Your budget is too tight and evaluations too expensive. What you ARE doing is applying the paper's core insight (full traces beat summaries) within a human-in-loop workflow.

## Final checklist before starting

- [ ] On the RunPod pod, not OneDrive/Windows
- [ ] `validate_workflow.py` passes
- [ ] `doctor` passes (except first-run "no leaderboard cache")
- [ ] `leaderboard fetch` ran successfully
- [ ] You've read this doc once
- [ ] You've picked which of Track A and Track B you care more about
- [ ] You have 7 days and ~$300-450 left

Start with `/morning`.
