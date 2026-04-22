# pgolf-agent

Disciplined experiment pipeline for [OpenAI's Parameter Golf](https://github.com/openai/parameter-golf) competition. Operated by Claude Code via skills and hooks.

## What this is

A project structure that makes Claude Code a reliable Parameter Golf researcher:

- **AGENTS.md** — Operating instructions (the "system prompt")
- **WORKFLOW.md** — Operator's guide with the exact 7-day workflow
- **.claude/commands/** — Eight slash-commands: `/morning`, `/plan-experiment`, `/run-experiment`, `/analyze-results`, `/synthesize`, `/blog`, `/checkpoint`, `/submit-check`
- **.claude/hooks/** — Bash hooks that enforce budget and require confirmation for expensive runs
- **scripts/pgolf.py** — CLI toolkit: tracking, parsing, spending, leaderboard, submission validation, reports, doctor
- **knowledge/** — Technique catalog, SOTA timeline, lessons learned, research framing guide
- **state/** — Mutable truth: spending ledger, cached leaderboard

**New: read `WORKFLOW.md` first.** It contains the exact 7-day workflow and how to operate the scaffold day-by-day.

## Quick start

```bash
# 1. Unpack the tarball into a new repo
tar -xzf pgolf-agent.tar.gz
cd pgolf-agent

# 2. Make hooks executable (may be needed depending on how you unpacked)
chmod +x .claude/hooks/*.sh

# 3. Initialize git
git init && git add -A && git commit -m "initial pgolf-agent setup"

# 4. Run local validation — does NOT touch GPUs, does NOT cost money
python scripts/validate_workflow.py

# 5. Install optional dependencies
pip install scipy   # for Welch's t-test p-values (the script works without, but only prints means/stds)

# 6. Fetch current leaderboard
python scripts/pgolf.py leaderboard fetch

# 7. Clone the competition repo alongside
git clone https://github.com/openai/parameter-golf.git

# 8. Check state
python scripts/pgolf.py status
```

If validation passes, you can start using the skills in Claude Code:

```
> Read AGENTS.md. Then run /morning.
```

## What's enforced vs. what's guidance

**Enforced by code** (the pipeline refuses to proceed if violated):
- Budget exceeded → pre-bash hook blocks torchrun
- 8×H100 without `PGOLF_CONFIRM_8XH100=1` → pre-bash hook blocks
- Missing `MAX_WALLCLOCK_SECONDS` → pre-bash hook blocks
- Known technique conflict per `lessons_learned.md` → `track create` refuses without `--force`
- Missing reproducibility fields, artifact > 16MB, GPU type wrong, seeds < 3 → `submit-check` fails

**Guidance** (documented but not enforced):
- When to use 1×A100 vs 1×H100 vs 8×H100
- When to write a non-record PR vs a full blog post
- How to phrase a hypothesis

## Validation before touching GPUs

Run `python scripts/validate_workflow.py` locally. It exercises the full pipeline with fake experiments and fake logs so you can verify everything works before spending a dollar on GPUs. See **VALIDATION.md** for what it checks and manual steps that complement it.

## Directory structure

```
pgolf-agent/
├── AGENTS.md              ← Operating instructions
├── CLAUDE.md              ← Command cheat sheet
├── ARCHITECTURE.md        ← Design decisions
├── TEMPLATE.md            ← Experiment analysis template
├── VALIDATION.md          ← Local checks before GPU use
├── README.md              ← You are here
│
├── .claude/
│   ├── settings.json
│   ├── skills/            (morning, plan-experiment, run-experiment,
│   │                       analyze-results, blog, checkpoint, submit-check)
│   └── hooks/             (pre-bash.sh, post-bash.sh)
│
├── scripts/
│   ├── pgolf.py           ← Main CLI
│   ├── fetch_leaderboard.py
│   ├── dashboard.py       (streamlit, optional)
│   ├── runpod_setup.py
│   └── validate_workflow.py
│
├── knowledge/
│   ├── techniques/        (depth_recurrence, qat, ttt, sentencepiece, ...)
│   ├── papers/
│   ├── sota_timeline.md
│   ├── lessons_learned.md
│   └── learning_path.md
│
├── experiments/           ← One folder per experiment
├── blog/drafts|published/
├── state/                 ← spending.jsonl, leaderboard.json
├── journal/               ← Daily checkpoint entries
│
├── tests/                 ← pytest suite
│   ├── test_parser.py
│   ├── test_hooks.py
│   ├── test_cli.py
│   ├── test_spending.py
│   └── fixtures/
│
└── pgolf.db               ← SQLite
```

## Dependencies

**Required**: Python 3.11+ (stdlib only for core CLI)

**Optional**:
- `scipy` — for p-value calculation in statistical comparisons
- `streamlit`, `pandas` — for the dashboard
- `pytest` — for the test suite

## Integrating with existing work

If you already have 19 experiments in a separate repo, you can migrate the state:

1. Copy your existing `experiments/` folder into this structure
2. Re-enter experiments into the new schema via `pgolf track create` (or import by hand)
3. Record seeds via `pgolf track result ... --seed N`
4. Run `python scripts/pgolf.py leaderboard fetch` to populate `state/leaderboard.json`

The new pre-registration requirement is forward-looking — you can't retroactively pre-register thresholds on existing experiments. Just use it for new experiments going forward.

## License

MIT
