# AGENTS.md — Parameter Golf Autonomous Workflow

## Mission

You are operating inside the `pgolf-agent` project to compete in OpenAI's Parameter Golf challenge.
Your three goals, in priority order:

1. **Push the frontier** — Run experiments to achieve the lowest BPB on FineWeb validation
2. **Learn and document** — Build a knowledge base linking techniques to papers, code, and results
3. **Write blog posts** — Generate daily blog posts documenting experiments and learnings

## Operating principles

Four principles govern everything you do here:

**1. Truth lives in one place.** The current SOTA comes from `state/leaderboard.json` via `pgolf leaderboard current` — never hardcoded. Total spend comes from `state/spending.jsonl`. Experiment state comes from `pgolf.db`. Never duplicate these facts into other files.

**2. Every claim in markdown is enforceable by code.** If AGENTS.md says "stop if budget exceeded," there is a hook that stops it. If it says "require 3 seeds," there is a `submit-check` script that counts them. If you find yourself making a claim that no code enforces, either remove the claim or add the code.

**3. Friction is graduated.** Smoke tests are free and instant. 1×H100 screens require no confirmation but consume budget. 8×H100 validations require explicit `PGOLF_CONFIRM_8XH100=1`. This boundary is where $500 becomes 13 days of work instead of 3 days.

**4. No autonomous overnight runs.** You (Claude Code) operate this pipeline *with Abi*, not instead of Abi. Every 8×H100 run has a human-in-loop. Every GREEN decision has a pre-registered rule applied mechanically.

## Current competition state

Always read the live state, never these static values:

```bash
python scripts/pgolf.py leaderboard current    # current SOTA
python scripts/pgolf.py spend status           # current budget position
python scripts/pgolf.py status                 # your experiments
```

Reference values (as of repo creation — may be stale by the time you read this):
- **Baseline**: 1.2244 BPB
- **Deadline**: April 30, 2026
- **Constraint**: 16MB artifact (code + compressed model), 10 min on 8×H100_SXM
- **Metric**: Bits per byte (BPB) on FineWeb validation, tokenizer-agnostic
- **Record threshold**: beat SOTA by ≥0.005 at p<0.01 (competition rule)

## Project structure

```
pgolf-agent/
├── AGENTS.md              ← YOU ARE HERE — operating instructions
├── CLAUDE.md              ← Command cheat sheet
├── ARCHITECTURE.md        ← Design rationale
├── TEMPLATE.md            ← Experiment analysis template
├── VALIDATION.md          ← Local checks to run before touching GPUs
│
├── .claude/
│   ├── settings.json      ← Hook registration
│   ├── skills/            ← Slash-command prompts (what you read when invoked)
│   │   ├── morning.md
│   │   ├── plan-experiment.md
│   │   ├── run-experiment.md
│   │   ├── analyze-results.md
│   │   ├── blog.md
│   │   ├── checkpoint.md
│   │   └── submit-check.md
│   └── hooks/             ← Enforcement (bash wrappers around your bash tool)
│       ├── pre-bash.sh    ← Budget gate for torchrun commands
│       └── post-bash.sh   ← Auto-log actual spend after torchrun
│
├── scripts/
│   ├── pgolf.py           ← Main CLI: track / parse / spend / leaderboard / submit-check / ...
│   ├── fetch_leaderboard.py
│   ├── dashboard.py
│   ├── runpod_setup.py
│   └── validate_workflow.py  ← Run this BEFORE going to GPU
│
├── knowledge/
│   ├── techniques/        ← One .md per technique; updated as experiments complete
│   ├── papers/            ← Paper summaries (optional)
│   ├── sota_timeline.md   ← Leaderboard progression — auto-appended
│   ├── lessons_learned.md ← Technique conflicts; gated by `check_technique_conflicts`
│   └── learning_path.md   ← Syllabus across technique tiers
│
├── experiments/           ← One folder per experiment
│   └── exp_NNN/
│       ├── config.json
│       ├── train_gpt.py
│       ├── train_seed*.log
│       └── analysis.md
│
├── blog/
│   ├── drafts/
│   └── published/
│
├── state/                 ← Mutable persistent state
│   ├── spending.jsonl     ← Append-only ledger, one line per GPU event
│   └── leaderboard.json   ← Cached from GitHub, refreshed on `leaderboard fetch`
│
├── journal/               ← One .md per day with checkpoint summary
│
├── tests/                 ← Pytest suite — run `pytest` to validate the pipeline
│
└── pgolf.db               ← SQLite: experiments, seeds, pre-registration, id_sequence
```

## The daily loop

**Prefer skills over ad-hoc workflows.** Skills in `.claude/skills/` are the canonical way to do each task.

```
/morning                           → refresh leaderboard, check budget, propose focus
/plan-experiment <focus>           → propose one experiment (reads ALL prior analyses)
/run-experiment exp_NNN            → execute smoke → screen → (validate) with gates
/analyze-results exp_NNN           → apply pre-reg rule, update knowledge base
/synthesize                        → cross-experiment pattern mining (run every 3-4 exps)
/blog N exp_NNN                    → write 800-1200 word post (not a form)
/checkpoint                        → end-of-day journal, commit, runway check
/submit-check exp_NNN              → paranoid pre-PR validation (only for GREEN results)
```

Each skill's full prompt is in `.claude/skills/<skill>.md`. Read it before invoking.

## Visibility commands

```bash
python scripts/pgolf.py status    # one-screen overview with lineage tree
python scripts/pgolf.py report    # generate full REPORT.md at project root
python scripts/pgolf.py doctor    # health check — run when things feel off
```

`WORKFLOW.md` documents the full 7-day workflow and how these pieces fit together.

## Key techniques — quick reference

For full docs, see `knowledge/techniques/`. At repo creation time, the SOTA stack included:

| Technique | Status | Notes |
|-----------|--------|-------|
| SP8192 tokenizer | Standard | Larger vocab = better compression |
| Depth recurrence (loop layers 3-5) | Standard | Free effective depth |
| Parallel residuals | Standard | Separate attn/MLP residual paths |
| GPTQ post-training quant | Standard | Better than naive rounding |
| QAT int6 (STE) | Standard | All top runs use this |
| Test-time training (score-first) | Standard | Legal variant only |
| EMA | ⚠️ Conflicts with recurrence | See lessons_learned.md |
| MuonEq-R optimizer | Standard | Modified Muon |
| QK-Gain scaling | Recent | Scale QK by ~5.0-5.25 |
| Hessian-aware SDClip | Recent | Smarter quant clipping |
| State-space models (Mamba) | Untried | Requested by organizers |
| Megakernels | Untried | Could enable more steps |

Always read `state/leaderboard.json` for the current SOTA stack — the table above ages fast.

## Critical constraints

- **DO NOT** train on validation data — disqualification
- **DO NOT** make network calls during evaluation
- **DO NOT** exceed 16,000,000 bytes total (code + compressed model)
- **DO NOT** exceed 600s wall time on 8×H100_SXM
- **DO NOT** skip the pre-registration step — it prevents optional stopping
- **Artifact** = code bytes + zlib-compressed int8 model bytes
- **TTT conflicts with weight-tied recurrence** (see lessons_learned.md)
- **EMA conflicts with aggressive depth recurrence** (see lessons_learned.md)

## Budget discipline

Total: $500. Reserve: $60 untouchable. Spendable: $440.

```
Tier 1: Iteration        ~$80   (1×A100/1×H100, 1-seed smoke-plus-screen)
Tier 2: 1×H100 validate  ~$120  (1×H100 single seed for screening)
Tier 3: 8×H100 record    ~$240  (3-seed validation for candidates)
Tier 4: Reserve          $60    (Day 14 panic, retries, overrides)
```

The pre-bash hook enforces this. Override mechanisms exist but require explicit env vars:

- `PGOLF_FORCE=1` — bypass the budget gate (don't use casually)
- `PGOLF_CONFIRM_8XH100=1` — proceed with 8×H100 run (required every time)
- `PGOLF_NO_WALLCLOCK=1` — run without MAX_WALLCLOCK_SECONDS (don't, ever, for real runs)

## Statistical rigor

- **Pre-registration before any seeds**: use `pgolf register-thresholds` BEFORE running seed 1
- **Welch's t-test, not Student's** (different-variance assumption is more realistic)
- **p < 0.01 for submission**, p < 0.01 + |Δ| ≥ 0.003 for internal claims
- **3 seeds minimum** for any result you record; re-run outliers if std > 0.003
- **Same hardware, same torch version** across seeds — apples to apples

## When in doubt

Read the skill's full prompt in `.claude/skills/<skill>.md`. Skill prompts are the authoritative source for "how do I do X" — AGENTS.md is the overview.

If you're about to do something expensive (`torchrun --nproc_per_node=8`, `git push`, submit a PR), STOP and confirm with Abi.
