# pgolf-agent

Autonomous experiment toolkit for [OpenAI's Parameter Golf](https://github.com/openai/parameter-golf) competition. Designed to be operated by Claude Code — no API wrapper, no framework, just clean scripts and structured knowledge.

## What This Is

A project structure that turns Claude Code into a Parameter Golf research agent:

- **AGENTS.md** — Operating instructions (the "system prompt")
- **scripts/pgolf.py** — Experiment tracking, log parsing, blog generation
- **knowledge/** — Technique catalog, SOTA timeline, lessons learned
- **experiments/** — Structured experiment folders with configs and results
- **blog/** — Daily blog post drafts and published posts

## Quick Start

```bash
# Clone this repo
git clone <your-repo-url> pgolf-agent
cd pgolf-agent

# Clone the competition repo
git clone https://github.com/openai/parameter-golf.git

# Check status
python scripts/pgolf.py status

# Create your first experiment
python scripts/pgolf.py track create \
  --hypothesis "Reproduce baseline: 9L 512dim 1024vocab" \
  --techniques "baseline"

# After training, record results
python scripts/pgolf.py parse experiments/exp_001/train.log
python scripts/pgolf.py track result exp_001 --bpb 1.2244 --size 15500000

# Generate a blog post
python scripts/pgolf.py blog --day 1 --experiment exp_001
```

## Using with Claude Code

```bash
# Start Claude Code in the project
cd pgolf-agent
claude

# Tell it your goal
> Read AGENTS.md and then run an experiment exploring depth recurrence
```

Claude Code will read AGENTS.md, check the knowledge base, plan an experiment, modify train_gpt.py, run it, and analyze the results — all using the tools in this repo.

## Project Structure

```
pgolf-agent/
├── AGENTS.md              ← Claude Code's operating instructions
├── ARCHITECTURE.md        ← Design decisions and rationale
├── scripts/pgolf.py       ← CLI toolkit
├── knowledge/
│   ├── techniques/        ← Technique docs with papers + results
│   ├── sota_timeline.md   ← Leaderboard progression
│   └── lessons_learned.md ← Failed experiments and why
├── experiments/           ← One folder per experiment
├── blog/                  ← Blog post drafts and published
└── pgolf.db              ← SQLite experiment database
```

## Goals

1. **Push the frontier** — Achieve competitive BPB scores
2. **Learn deeply** — Build a knowledge base linking techniques → papers → code → results
3. **Build in public** — Daily blog posts documenting the journey

## Competition Info

- **SOTA**: 1.0810 BPB (April 9, 2026)
- **Baseline**: 1.2244 BPB
- **Deadline**: April 30, 2026
- **Constraint**: 16MB artifact, 10 min on 8xH100s

## License

MIT
