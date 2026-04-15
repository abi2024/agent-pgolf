# AGENTS.md — Parameter Golf Autonomous Workflow

## Mission

You are operating inside the `pgolf-agent` project to compete in OpenAI's Parameter Golf challenge.
Your three goals, in priority order:

1. **Push the frontier** — Run experiments to achieve the lowest BPB on FineWeb validation
2. **Learn and document** — Build a knowledge base of techniques with papers and resources
3. **Write blog posts** — Generate daily blog posts documenting experiments and learnings

## Current Competition State

- **SOTA**: 1.0810 BPB (April 9, 2026) by bigbag
- **Baseline**: 1.2244 BPB
- **Deadline**: April 30, 2026
- **Constraint**: 16MB artifact (code + compressed model), 10 min on 8xH100s
- **Metric**: Bits per byte (BPB) on FineWeb validation set, tokenizer-agnostic

## Project Structure

```
pgolf-agent/
├── AGENTS.md              ← YOU ARE HERE — your operating instructions
├── scripts/               ← CLI tools you call via bash
│   ├── pgolf.py           ← Main CLI: track, parse, blog, status
│   └── analyze_log.py     ← Standalone log parser
├── knowledge/
│   ├── techniques/        ← One .md per technique (read and update these)
│   ├── papers/            ← Paper summaries
│   ├── sota_timeline.md   ← SOTA progression with technique stacks
│   └── lessons_learned.md ← Failed experiments and why
├── experiments/           ← One folder per experiment
│   └── exp_NNN/
│       ├── config.json    ← Hypothesis, technique stack, hyperparams
│       ├── train_gpt.py   ← Modified training script
│       ├── train.log      ← Raw training output
│       ├── results.json   ← Parsed results
│       └── analysis.md    ← Your analysis
├── blog/
│   ├── drafts/            ← Generated blog post drafts
│   └── published/         ← Reviewed and finalized posts
├── parameter-golf/        ← Cloned competition repo (git submodule or separate)
└── pgolf.db               ← SQLite experiment database
```

## Workflow Protocol

### Before Each Experiment

1. **Check state**: `python scripts/pgolf.py status` — see your best BPB, recent experiments, budget
2. **Read knowledge**: Check `knowledge/techniques/` for what's been tried
3. **Check leaderboard**: Read `knowledge/sota_timeline.md` or fetch latest from GitHub
4. **Form hypothesis**: Be SPECIFIC. Bad: "try quantization". Good: "Replace int6 MLP weights with int5 using STE, keeping embeddings at int8, targeting 0.8MB size savings to fit 1 more layer"
5. **Check for conflicts**: Some techniques conflict. Read `knowledge/lessons_learned.md`

### Running an Experiment

1. **Create experiment folder**: `python scripts/pgolf.py track create --hypothesis "..." --techniques "depth_recurrence,qat_int5"`
2. **Copy and modify train_gpt.py**: Copy the current best script, make targeted changes
3. **Local smoke test** (if on local machine with GPU):
   ```bash
   cd experiments/exp_NNN
   RUN_ID=smoke ITERATIONS=200 TRAIN_BATCH_TOKENS=8192 VAL_LOSS_EVERY=0 python train_gpt.py
   ```
4. **Full RunPod run** (if on RunPod):
   ```bash
   cd experiments/exp_NNN
   RUN_ID=exp_NNN torchrun --standalone --nproc_per_node=1 train_gpt.py
   ```
   For 8xH100: `--nproc_per_node=8`
5. **Parse results**: `python scripts/pgolf.py parse experiments/exp_NNN/train.log`
6. **Record results**: `python scripts/pgolf.py track result exp_NNN --bpb 1.0850 --size 15800000`

### After Each Experiment

1. **Analyze**: Write `experiments/exp_NNN/analysis.md` explaining what happened and why
2. **Update knowledge**: Add results to the relevant technique doc in `knowledge/techniques/`
3. **Update lessons**: If something failed unexpectedly, add to `knowledge/lessons_learned.md`
4. **Blog post**: `python scripts/pgolf.py blog --day N --experiment exp_NNN`
5. **Plan next**: Based on results, decide what to try next

### Statistical Rigor

- Run 3 seeds minimum for any result you want to publish
- Use `python scripts/pgolf.py parse --compare exp_A exp_B` for significance testing
- A technique "works" if it improves BPB by ≥0.005 at p < 0.01
- Track variance: std ≤ 0.001 BPB across seeds is good

## Key Techniques Reference (Quick Look)

See `knowledge/techniques/` for full docs. Here's the cheat sheet:

| Technique | Status in SOTA | Notes |
|-----------|---------------|-------|
| SP8192 tokenizer | ✅ Standard | Larger vocab = better compression |
| Depth recurrence (loop layers 4-5) | ✅ Standard | Free effective depth |
| 3-layer recurrence | ✅ Current best | Layers 3-5, newest improvement |
| Parallel residuals | ✅ Standard | Separate attn/MLP residual paths |
| GPTQ post-training quant | ✅ Standard | Better than naive rounding |
| QAT int6 (STE) | ✅ Baseline | All top runs use this |
| Test-time training (score-first) | ✅ Standard | Legal: only on already-evaluated tokens |
| EMA (weight averaging) | ⚠️ Conflicts | Fails with aggressive depth recurrence |
| MuonEq-R optimizer | ✅ Standard | Modified Muon |
| QK-Gain scaling | ✅ Recent | Scale QK dot products by 5.0-5.25 |
| Hessian-aware SDClip | ✅ Recent | Smarter quantization clipping |
| Ternary quantization | 🔬 Experimental | 1.157 BPB, needs more work |
| State-space models | ❌ Untried | Requested by organizers |
| Megakernels | ❌ Untried | Could enable more training steps |

## Critical Constraints

- **DO NOT** train on validation data (cheating, will be disqualified)
- **DO NOT** make network calls during evaluation
- **DO NOT** exceed 16,000,000 bytes total (code + compressed model)
- **Artifact = code bytes + zlib-compressed int8 model bytes**
- **TTT conflicts with weight-tied recurrence** — gradients compound through shared weights
- **Width increases can hurt** — slower training = fewer steps in 10 min

## Budget Tracking

Check budget: `python scripts/pgolf.py status`

Estimated costs:
- 1xH100: ~$3/hr (for iteration)
- 8xH100: ~$20/hr (for final submissions only)
- Local GTX 3060: Free (smoke tests only, ~200 iters)

**Rule**: Use 1xH100 for exploration. Only use 8xH100 when you have a promising result to validate.

## Blog Post Protocol

Each blog post follows this structure:
1. What I tried (experiment description)
2. The hypothesis (what I expected)
3. Results (table with BPB, size, timing)
4. What I learned (key takeaway)
5. Key concept (technique explanation for readers)
6. Resources (papers, links)
7. What's next (plan for tomorrow)

Generate with: `python scripts/pgolf.py blog --day N --experiment exp_NNN`
Then edit the draft in `blog/drafts/` before moving to `blog/published/`.

## Autonomous Mode

When running autonomously (e.g., overnight batch):
1. Read this file and `knowledge/lessons_learned.md`
2. Check `python scripts/pgolf.py status` for current state
3. Pick the highest-priority untried technique or variation
4. Run the experiment
5. Record results and update knowledge base
6. Generate blog draft
7. Repeat until budget limit or max experiments reached

**Safety rails**:
- Stop if cost exceeds per-experiment limit ($10 default)
- Stop if 3 consecutive experiments fail
- Stop if artifact exceeds 16MB
- Always git commit experiment results before starting next one
