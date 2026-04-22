# ARCHITECTURE — Parameter Golf Agent

## Core design principle

**Claude Code is the agent. The hooks are the guardrails. The CLI is the toolkit. The skills are the thinking.**

Four layers, stacked:

```
┌─────────────────────────────────────────────────────────────┐
│  SKILL LAYER        .claude/skills/*.md                      │  Thinking
│                     /morning, /plan-experiment, /run-         │  (prompts)
│                     experiment, /analyze-results, /blog,      │
│                     /checkpoint, /submit-check                │
├─────────────────────────────────────────────────────────────┤
│  HOOK LAYER         .claude/hooks/pre-bash.sh                │  Enforcement
│                     .claude/hooks/post-bash.sh               │  (bash)
├─────────────────────────────────────────────────────────────┤
│  CLI LAYER          scripts/pgolf.py                         │  Actions
│                     (track, parse, spend, leaderboard,       │  (python)
│                     submit-check, register-thresholds, ...)  │
├─────────────────────────────────────────────────────────────┤
│  STATE LAYER        pgolf.db (SQLite)                        │  Memory
│                     state/spending.jsonl                     │  (files)
│                     state/leaderboard.json                   │
│                     knowledge/*.md, experiments/exp_NNN/*    │
└─────────────────────────────────────────────────────────────┘
```

## Why this shape

### Why not an API-based agent
- Claude Code already implements ReACT natively (read, act, observe)
- File editing, bash, git are built in — no SSH library, no tool schemas
- Zero orchestration code to maintain
- Debugging = reading the conversation, not parsing API logs

### Why hooks
- A markdown instruction "stop if budget exceeded" is a prayer
- A bash script that refuses to execute `torchrun` when spend exceeds threshold is a lock
- Every critical rule in AGENTS.md should have a corresponding enforcement mechanism
- Hooks are registered in `.claude/settings.json` and run automatically around every bash command

### Why skills
- Skills are prompt files that Claude Code reads when invoked (via slash commands)
- They encode the *method* of each task — so the workflow is identical every time
- Without skills, each new session re-improvises the workflow, producing drift
- Skills are the canonical answer to "how do I do X" — AGENTS.md is the overview

### Why a CLI script
- Structured tools that are consistent across sessions
- Bug fixes to the parser apply everywhere
- Schema migrations are centralized
- Testable — see `tests/`

### Why SQLite + JSONL + markdown
- SQLite: structured queries (experiments, seeds, pre-registrations)
- JSONL: append-only ledgers (spending events — never mutate, always add)
- Markdown: human-editable context (lessons, techniques, timelines)

The mix is intentional. Use the right storage for the data shape.

## The staged execution model

Every experiment passes through stages, with explicit gates between them:

```
Stage 0: Pre-flight
    ↓ (check config, pre-registration, git clean)
Stage 1: Smoke (free, local GPU)
    ↓ (no crash, no NaN, loss decreasing)
Stage 2: Screen (1×H100, ~$0.55)
    ↓ (gate: seed-1 BPB ≤ pre-registered threshold)
    ↓ (gate: Abi's explicit confirmation)
Stage 3: Validate (3× 8×H100, ~$24 incl eval)
    ↓ (apply pre-registered GREEN/YELLOW/RED rule)
Stage 4: Analyze
    ↓ (update knowledge base, commit)
[if GREEN]
Stage 5: Submit-check (all competition rules)
    ↓ (Abi reviews and pushes PR manually)
```

Each gate has both a code check AND a human check. Code alone is never trusted for expensive actions.

## Preventing optional stopping

Optional stopping is a common bias: you run experiments until one looks good, then stop. This inflates false positives.

The pre-registration table in SQLite records:
- `seed1_continue_threshold` — below which continue to Stage 3, above which stop
- `publish_delta` — threshold vs SOTA for GREEN
- `internal_delta` — threshold vs parent for YELLOW

These are set BEFORE any seeds run. The `/analyze-results` skill applies them mechanically — no rationalizing "seed 1 looks great but is technically over threshold, I'll keep going."

## State as truth

- **Current SOTA**: `state/leaderboard.json`, populated by `pgolf leaderboard fetch`. Never hardcoded in AGENTS.md or pgolf.py.
- **Total spend**: sum of `state/spending.jsonl` entries. No single counter that can drift.
- **Experiment results**: `pgolf.db` + `experiments/exp_NNN/*`. SQLite for queries, files for human review.

If truth lives in multiple places, they will diverge. So it lives in one.

## Why no autonomous overnight mode

Originally the plan had an "autonomous overnight" mode. This was removed because:

1. The safety rails were not actually enforceable (signs on unlocked doors)
2. $500 is too tight to absorb a $40 overnight mistake
3. Claude Code operating without human-in-loop would still need to make judgment calls that benefit from Abi's context
4. 13 days is a sprint — more focused hours produce more signal than more elapsed hours

The current design is "Claude Code is a disciplined pipeline operator, not an autonomous worker." Every 8×H100 run requires explicit confirmation. Every GREEN result is reviewed before a PR is filed.

## Syllabus mapping

What the plan originally claimed to draw on, and what actually ended up in use:

| Topic | How it's used |
|-------|---------------|
| Markdown-as-program (Karpathy) | AGENTS.md and skill .md files ARE the prompts |
| ReACT | Claude Code native loop |
| Task decomposition | Staged skills (morning → plan → run → analyze → checkpoint) |
| Self-validation | Welch's t-test, pre-registration, submit-check |
| Episodic memory | SQLite + experiments/ folder |
| Cost management | pre-bash hook + spending.jsonl ledger |
| Strategy profiles | Budget tiers (iteration/screen/validate/reserve) |
| Reproducibility | Pre-registration, torch_version + commit tracking |

What was removed:
- MCP, A2A, browser automation, Computer Use, voice, GAIA, etc. — not relevant to training a 16MB LM
- The streamlit dashboard is present but optional
- "Autonomous overnight" mode — incompatible with the budget

## Local vs RunPod

| Task | Local (GTX 3060) | RunPod |
|------|-------------------|--------|
| Smoke test (200 iters) | ✅ Fast | Overkill |
| Full 1×H100 screening | ❌ Too slow | ✅ (1×H100_SXM, ~$0.55) |
| 3-seed 8×H100 validation | ❌ | ✅ (only for GREEN candidates) |
| Knowledge base editing | ✅ | ✅ |
| Blog writing | ✅ | ✅ |
| `validate_workflow.py` | ✅ | (not needed) |
| Claude Code operation | ✅ | ✅ (via tmux) |

The workflow is designed to run mostly locally, with RunPod used surgically for paid compute. `validate_workflow.py` lets you confirm the pipeline works end-to-end without touching GPUs.

## Extension points

If you want to extend this:

- **New technique doc**: add `knowledge/techniques/<name>.md` following the format of existing ones. `check_technique_conflicts` will automatically detect "### X + Y = BAD" headers in lessons_learned.md.
- **New safety rule**: add enforcement in `pre-bash.sh`, document in `AGENTS.md`. If you add the rule to AGENTS.md without the enforcement, you're back to signs on unlocked doors.
- **New CLI command**: add to `scripts/pgolf.py` main()'s argparse tree. Keep stdlib-only; add to `tests/test_cli.py`.
- **New skill**: add `.claude/skills/<name>.md` with the frontmatter. Skills can call the CLI and each other.
