# Architecture — Parameter Golf Agent

## Core Design Principle

**Claude Code IS the agent. Everything else is its toolkit.**

There is no separate agent loop, no API wrapper, no orchestration layer.
Claude Code already implements ReACT (reason → act → observe) natively.
This project gives it:

- **AGENTS.md** → System prompt (mission, protocols, constraints)
- **scripts/pgolf.py** → Tools (experiment tracking, log parsing, blog generation)
- **knowledge/** → Memory (technique docs, SOTA timeline, lessons learned)
- **experiments/** → State (configs, logs, results per experiment)

## Why Not API Calls

| API-based agent | Claude Code as agent |
|----------------|---------------------|
| Build ReACT loop from scratch | Already built in |
| Pay per API call for orchestration | Included in Claude Code |
| Can't edit files directly | Native file editing |
| Need SSH library for RunPod | Already has bash |
| Need tool schema definitions | Just runs scripts |
| Debugging = reading API logs | Debugging = reading conversation |
| Extra code to maintain | Zero orchestration code |

## What Claude Code Does Natively

- Reads AGENTS.md on startup → knows the mission
- Edits train_gpt.py → implements experiments
- Runs `python scripts/pgolf.py track create ...` → tracks experiments
- Runs `torchrun train_gpt.py` → executes training
- Reads training logs → analyzes results
- Updates knowledge/ markdown files → maintains memory
- Generates blog posts → documents learnings
- Git commit/push → version controls everything

## Project Structure

```
pgolf-agent/
├── AGENTS.md                    ← Claude Code reads this first
├── scripts/
│   └── pgolf.py                 ← CLI toolkit (track, parse, blog, status)
├── knowledge/
│   ├── techniques/              ← One .md per technique
│   │   ├── depth_recurrence.md
│   │   ├── quantization_aware_training.md
│   │   ├── test_time_training.md
│   │   └── ...                  ← Claude Code creates these as it learns
│   ├── papers/                  ← Paper summaries
│   ├── sota_timeline.md         ← Leaderboard history
│   └── lessons_learned.md       ← What failed and why
├── experiments/                 ← One folder per experiment
│   └── exp_NNN/
│       ├── config.json
│       ├── train_gpt.py
│       ├── train.log
│       ├── results.json
│       └── analysis.md
├── blog/
│   ├── drafts/
│   └── published/
├── parameter-golf/              ← Competition repo (clone)
└── pgolf.db                     ← SQLite (managed by scripts/pgolf.py)
```

## Workflow (What Claude Code Actually Does)

### Experiment cycle

```
1. Read AGENTS.md + knowledge/lessons_learned.md
2. Run: python scripts/pgolf.py status
3. Read: knowledge/sota_timeline.md
4. Think: What technique to try next?
5. Run: python scripts/pgolf.py track create --hypothesis "..." --techniques "..."
6. Copy best train_gpt.py to experiments/exp_NNN/
7. Edit train_gpt.py with the modification
8. Run: cd experiments/exp_NNN && torchrun --standalone --nproc_per_node=1 train_gpt.py
9. Run: python scripts/pgolf.py parse experiments/exp_NNN/train.log
10. Run: python scripts/pgolf.py track result exp_NNN --bpb X.XXXX --size NNNNN
11. Write experiments/exp_NNN/analysis.md
12. Update knowledge/techniques/relevant_technique.md
13. Run: python scripts/pgolf.py blog --day N --experiment exp_NNN
14. Git commit
15. Repeat
```

### Autonomous overnight mode

Claude Code can run this loop autonomously. Safety rails in AGENTS.md:
- Stop after budget limit
- Stop after 3 consecutive failures
- Always git commit between experiments
- Never exceed 16MB artifact size

## Syllabus Mapping

### Used (mapped to this project)

| Syllabus Topic | How It's Used |
|---------------|--------------|
| Python dataclasses, type hints | scripts/pgolf.py data models |
| ReACT pattern | Claude Code's native loop |
| Task decomposition | AGENTS.md workflow protocol |
| Chain-of-thought | Claude Code's reasoning |
| Self-validation | Statistical significance checking |
| Episodic memory | experiments/ folder + SQLite |
| Coding agent patterns | Claude Code editing train_gpt.py |
| Evaluation & benchmarking | BPB measurement, seed comparison |
| Strategy profiles | AGENTS.md: explore vs exploit |
| Cost management | scripts/pgolf.py status + budget limits |
| Markdown-as-Code (Karpathy) | AGENTS.md IS the program |

### Skipped (not relevant)

MCP, A2A, AG-UI, browser automation, Computer Use, channel adapters, voice, anti-detection, GAIA benchmarks, Node.js, React, container isolation, daemon installation — none of these help train a 16MB language model.

## Dependencies

Zero Python package dependencies for the core toolkit. `scripts/pgolf.py` uses only stdlib (sqlite3, json, re, argparse, pathlib). Optional: `scipy` for statistical significance testing.

The competition repo (parameter-golf) has its own dependencies (PyTorch, etc.) managed separately.

## Local vs RunPod

| Task | Local (GTX 3060) | RunPod (H100) |
|------|-----------------|---------------|
| Smoke test (200 iters) | ✅ 2-3 min | Overkill |
| Full training run | ❌ Too slow | ✅ 1xH100 for iteration |
| Leaderboard submission | ❌ | ✅ 8xH100 for final |
| Knowledge base editing | ✅ | ✅ |
| Blog generation | ✅ | ✅ |
| Claude Code operation | ✅ | ✅ (tmux) |
