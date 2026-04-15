# Parameter Golf SSM Hybrid — PRD & Milestone Map

## $450 Compute Plan · 16 Days Remaining · Deadline: April 30, 2026

---

## 1. Product Requirements

### 1.1 Objective

Implement and evaluate a hybrid SSM-Transformer architecture for OpenAI's Parameter Golf competition, replacing attention in layers 0-2 with Mamba-style state-space model blocks while preserving the full SOTA training stack.

### 1.2 Success Criteria

| Tier | BPB Target | Outcome |
|------|-----------|---------|
| A (Best case) | < 1.081 | New SOTA, record submission |
| B (Good) | 1.081 - 1.095 | Competitive non-record submission with novel architecture |
| C (Acceptable) | 1.095 - 1.12 | Documented non-record submission, organizer-requested experiment |
| D (Minimum) | Any | Documented negative result with ablations explaining why SSM fails |

All tiers produce a PR submission. All tiers produce blog posts. No outcome is wasted.

### 1.3 Hard Constraints

- Artifact ≤ 16,000,000 bytes (code + compressed model)
- Training ≤ 10 minutes on 8xH100 SXM
- Evaluation ≤ 10 minutes on 8xH100 SXM (separate from training)
- No network calls during evaluation
- No access to validation data during training
- Must beat comparison by ≥ 0.005 nats at p < 0.01 for record submission
- MIT license, public GitHub

### 1.4 Deliverables

1. PR to `openai/parameter-golf` with: README, submission.json, train_gpt.py, train logs
2. Blog series (Days 3-10+) documenting the full experiment
3. Technique doc: `knowledge/techniques/ssm_hybrid.md`
4. Ablation table with ≥ 3 seeds per key configuration

---

## 2. Tech Stack

### 2.1 Infrastructure

| Component | Choice | Notes |
|-----------|--------|-------|
| Compute | RunPod 1xH100 SXM ($3.09/hr) | Iteration and development |
| Compute (final) | RunPod 8xH100 SXM ($24.72/hr) | Submission validation only |
| Template | Parameter Golf RunPod template `y5cejece4j` | Pre-installed PyTorch, CUDA |
| Orchestrator | Claude Code via SSH into RunPod | NOT API calls, NOT local |
| Experiment tracking | pgolf.py CLI + SQLite | Already built |
| Version control | Git on RunPod + push to GitHub | Commit after every experiment |
| Blog | Markdown in blog/drafts/ | Generate with pgolf.py |

### 2.2 Software Dependencies (on RunPod)

```bash
# Pre-installed in template:
# PyTorch 2.x, CUDA, numpy, flash-attn

# Must install:
pip install mamba-ssm              # Mamba SSM blocks (requires CUDA)
pip install brotli                 # Compression for artifact
pip install sentencepiece          # Tokenizer
pip install causal-conv1d          # Mamba dependency
pip install scipy                  # Statistical significance testing
```

### 2.3 Key Files

| File | Purpose |
|------|---------|
| `experiments/exp_002/train_gpt_runpod.py` | SOTA baseline (1.0810 code, untouched) |
| `experiments/exp_003/train_gpt.py` | SSM hybrid (your modification) |
| `experiments/exp_003/config.json` | Hypothesis, technique stack, hyperparams |
| `scripts/pgolf.py` | Experiment tracking CLI |
| `knowledge/techniques/ssm_hybrid.md` | Technique documentation |
| `AGENTS.md` | Claude Code operating instructions |

### 2.4 Data

| Variant | Status | Action Required |
|---------|--------|----------------|
| SP1024 | Downloaded locally (1 shard) | Download full (80 shards) on RunPod |
| SP8192 | NOT in official cache | Must build tokenizer OR find in SOTA PR files |

**SP8192 resolution strategy** (in priority order):
1. Check if SOTA PR folder has the tokenizer model file
2. Check `parameter-golf/data/` for tokenizer training scripts
3. Train SP8192 from scratch using SentencePiece on FineWeb docs
4. Fallback: use SP4096 or SP1024 and accept different BPB baseline

---

## 3. Milestone Map

### Overview

```
M0: Pre-flight (local, $0)          ← YOU ARE HERE
M1: Environment + baseline ($15)     ← Day 1 on RunPod
M2: SSM implementation ($10)         ← Day 1-2
M3: SSM first training ($15)         ← Day 2
M4: Ablation grid ($60)              ← Day 2-4
M5: Optimization ($80)               ← Day 4-6
M6: 8xH100 validation ($80)          ← Day 7-8
M7: Submission ($15)                 ← Day 8-9
Buffer: $175 for pivots/extras
```

---

### M0: Pre-Flight Checklist (Local, $0, Before Spinning Up Any Pod)

**Goal**: Have ALL code written and reviewed before spending a single dollar.

#### M0.1 — SSM Hybrid Code (Claude Code on laptop)

Tell Claude Code:

```
Read experiments/exp_002/train_gpt_runpod.py and experiments/exp_002/analysis.md.
Create experiments/exp_003/train_gpt.py based on the RunPod version.

Changes:
1. Add at the top: from mamba_ssm import Mamba
2. Add a MambaBlock class:

class MambaBlock(nn.Module):
    def __init__(self, dim, d_state=16, d_conv=4, expand=2, layer_idx=0):
        super().__init__()
        self.norm = RMSNorm()
        self.mamba = Mamba(d_model=dim, d_state=d_state, d_conv=d_conv, expand=expand)
        self.scale = nn.Parameter(torch.ones(dim, dtype=torch.float32))
    
    def forward(self, x, x0):
        return x + self.scale.to(dtype=x.dtype)[None, None, :] * self.mamba(self.norm(x))

3. In GPT.__init__, replace blocks 0-2 with MambaBlock:

self.blocks = nn.ModuleList()
for i in range(h.num_layers):
    if i < h.ssm_layers:
        self.blocks.append(MambaBlock(h.model_dim, d_state=h.ssm_d_state,
                                       d_conv=h.ssm_d_conv, expand=h.ssm_expand, layer_idx=i))
    else:
        self.blocks.append(Block(h.model_dim, ...existing args...))

4. Add hyperparameters:
   ssm_layers = int(os.environ.get('SSM_LAYERS', 3))
   ssm_d_state = int(os.environ.get('SSM_D_STATE', 16))
   ssm_d_conv = int(os.environ.get('SSM_D_CONV', 4))
   ssm_expand = int(os.environ.get('SSM_EXPAND', 2))

5. Fix XSA: Only apply use_xsa to transformer blocks, not MambaBlock:
   Change the XSA loop to skip blocks that are MambaBlock instances.

6. Fix GPTQ: The collect_hessians function hooks CastedLinear layers.
   Mamba uses regular nn.Linear internally. Either:
   - Add hooks for nn.Linear inside MambaBlock, OR
   - Wrap Mamba's internal projections with CastedLinear
   The simpler approach: add a separate hook pattern for modules inside
   blocks that are MambaBlock instances.

7. Keep everything else IDENTICAL. Same optimizer, same EMA, same
   recurrence on layers 3-5, same skip gates, same compression.

Create config.json with:
{
    "id": "exp_003",
    "hypothesis": "Replace layers 0-2 with Mamba SSM blocks. SSM handles local
                   pattern extraction faster than attention (O(n) vs O(n²)),
                   enabling more training steps in 10 min. Layers 0-2 are never
                   looped, making this the safest replacement point.",
    "technique_stack": ["ssm_mamba", "depth_recurrence", "parallel_residuals",
                        "qk_gain", "xsa", "skip_gates", "ema", "muon_eq_r",
                        "gptq", "brotli", "ttt"],
    "parent_id": "exp_002",
    "base_bpb": "1.0810 (SOTA on 8xH100)"
}
```

**Validation**: Read the generated code line by line. Check:
- [ ] MambaBlock.forward has same signature as Block.forward: `(self, x, x0)`
- [ ] MambaBlock is only used for layers < `ssm_layers`
- [ ] XSA skips MambaBlock instances
- [ ] Recurrence indices (layers 3-5) are unchanged
- [ ] Parallel residuals (layers 7+) are unchanged
- [ ] Skip gates still connect encoder to decoder
- [ ] GPTQ hooks handle both CastedLinear and Mamba internal linears
- [ ] All new hyperparameters have env var overrides
- [ ] `classify_param` handles mamba weight names correctly

#### M0.2 — Ablation Variants (Claude Code on laptop)

Tell Claude Code:

```
Create a shell script experiments/exp_003/run_ablations.sh that runs:

# Baseline (no SSM, original SOTA)
QK_GAIN_INIT=5.25 SEED=42 SSM_LAYERS=0 \
  torchrun --standalone --nproc_per_node=1 train_gpt.py

# 1 SSM layer (layer 0 only)
QK_GAIN_INIT=5.25 SEED=42 SSM_LAYERS=1 \
  torchrun --standalone --nproc_per_node=1 train_gpt.py

# 2 SSM layers (layers 0-1)
QK_GAIN_INIT=5.25 SEED=42 SSM_LAYERS=2 \
  torchrun --standalone --nproc_per_node=1 train_gpt.py

# 3 SSM layers (layers 0-2) — main hypothesis
QK_GAIN_INIT=5.25 SEED=42 SSM_LAYERS=3 \
  torchrun --standalone --nproc_per_node=1 train_gpt.py

Each run should log to a separate file via RUN_ID.
```

**Validation**: 
- [ ] Script uses different RUN_ID for each run
- [ ] SSM_LAYERS=0 should produce identical results to exp_002 baseline
- [ ] All runs use same SEED for fair comparison

#### M0.3 — Push to GitHub

```bash
git add -A
git commit -m "exp_003: SSM hybrid implementation ready for RunPod"
git push
```

**Validation**: 
- [ ] experiments/exp_003/train_gpt.py exists in repo
- [ ] experiments/exp_003/config.json exists
- [ ] experiments/exp_003/run_ablations.sh exists
- [ ] No local-only files (no train_gpt_local.py in exp_003 — not needed)

#### M0 Exit Criteria

- [ ] SSM hybrid code reviewed and pushed to GitHub
- [ ] Ablation script ready
- [ ] Blog Day 3 (SSM pivot) drafted and published
- [ ] Credit application submitted (already done)
- [ ] You understand every line of the SSM modification

---

### M1: Environment + Baseline ($15, ~3 hours)

**Goal**: Working RunPod environment with confirmed SOTA baseline number.

#### M1.1 — Pod Setup

Spin up 1xH100 SXM from Parameter Golf template.

```bash
# SSH in, then:
cd /workspace
git clone https://github.com/openai/parameter-golf.git
git clone <YOUR_REPO_URL> pgolf-agent
cd pgolf-agent

# Install dependencies
pip install mamba-ssm brotli sentencepiece scipy causal-conv1d
```

**Validation**:

```bash
python -c "from mamba_ssm import Mamba; print('mamba OK')"
python -c "import brotli; print('brotli OK')"
python -c "from flash_attn_interface import flash_attn_func; print('flash3 OK')"
python -c "import torch; print(f'GPUs: {torch.cuda.device_count()}, {torch.cuda.get_device_name(0)}')"
```

All four must print OK / H100. If mamba-ssm fails, try:
```bash
pip install mamba-ssm --no-build-isolation
```

If flash_attn_3 fails, check the SOTA PR README for the correct install URL.

#### M1.2 — SP8192 Tokenizer Resolution

```bash
# Check if tokenizer exists in SOTA PR
ls parameter-golf/records/track_10min_16mb/2026-04-09_SP8192_3LayerRecur_ParResid_QK525_LegalTTT/
find parameter-golf/ -name "*8192*" -o -name "*sp8192*" 2>/dev/null

# Check data download scripts
grep -r "8192" parameter-golf/data/*.py
```

Tell Claude Code:

```
I need the SP8192 tokenizer and dataset. Search the parameter-golf repo
for how other submissions built the SP8192 tokenizer. Check:
1. Records folders for any included tokenizer files
2. data/ directory for tokenizer training scripts
3. README files mentioning SP8192 setup
4. If none found, train a SentencePiece BPE tokenizer with vocab_size=8192
   on the FineWeb docs (use --with-docs flag on the download script to get
   the raw documents).
```

**Fallback**: If SP8192 is truly blocked, use SP1024. Your SSM hybrid vs. transformer baseline comparison is valid at any tokenizer size — the variable under test is the architecture, not the tokenizer.

#### M1.3 — Baseline Run (3 seeds)

```bash
cd /workspace/pgolf-agent/experiments/exp_002

# Seed 42
RUN_ID=baseline_s42 QK_GAIN_INIT=5.25 SEED=42 \
  DATA_DIR=/workspace/parameter-golf/data/ \
  torchrun --standalone --nproc_per_node=1 train_gpt_runpod.py

# Seed 43
RUN_ID=baseline_s43 QK_GAIN_INIT=5.25 SEED=43 \
  DATA_DIR=/workspace/parameter-golf/data/ \
  torchrun --standalone --nproc_per_node=1 train_gpt_runpod.py

# Seed 44
RUN_ID=baseline_s44 QK_GAIN_INIT=5.25 SEED=44 \
  DATA_DIR=/workspace/parameter-golf/data/ \
  torchrun --standalone --nproc_per_node=1 train_gpt_runpod.py
```

**Validation**:

```bash
# After each run, record:
cd /workspace/pgolf-agent
python scripts/pgolf.py track result exp_002 --bpb <VAL_BPB> --seed <SEED> --gpu "1xH100"

# After all 3, compare:
python scripts/pgolf.py parse --compare exp_002 exp_002  # Shows seed variance
```

**Expected**: BPB around 1.12-1.16 on 1xH100 (lower than 8xH100 SOTA due to 1/8 the batch).

Record: mean BPB, std, tok/s, peak memory, artifact size.

**CRITICAL**: Note the tok/s number. This is your speed benchmark. If SSM doesn't improve tok/s, the "more steps in 10 min" hypothesis fails.

#### M1 Exit Criteria

- [ ] mamba-ssm installed and importable
- [ ] SP8192 tokenizer resolved (or decision to use SP1024)
- [ ] 3-seed baseline recorded with mean/std
- [ ] tok/s baseline recorded
- [ ] Pod stopped

**Budget spent**: ~$15 (3 hours × $3/hr + margin)

---

### M2: SSM Implementation Verification ($10, ~2 hours)

**Goal**: SSM hybrid code runs without crashing. Not training quality — just mechanical correctness.

#### M2.1 — First Run (crash test)

```bash
cd /workspace/pgolf-agent
git pull  # Get the exp_003 code you wrote in M0

cd experiments/exp_003

# Quick crash test: 20 iterations, small batch
RUN_ID=ssm_crash_test ITERATIONS=20 TRAIN_BATCH_TOKENS=32768 \
  QK_GAIN_INIT=5.25 SEED=42 DATA_DIR=/workspace/parameter-golf/data/ \
  torchrun --standalone --nproc_per_node=1 train_gpt.py
```

**If it crashes**: Read the error. Common failures:

| Error | Fix |
|-------|-----|
| `ImportError: mamba_ssm` | `pip install mamba-ssm` |
| Shape mismatch in MambaBlock.forward | Check x0 is not used when it shouldn't be |
| GPTQ hook error on Mamba layers | Fix `collect_hessians` to handle Mamba internals |
| XSA error on MambaBlock | Ensure `use_xsa` is only set on transformer blocks |
| Skip connection shape mismatch | MambaBlock output dim must match Block output dim |
| OOM | Reduce TRAIN_BATCH_TOKENS to 16384 |

Tell Claude Code (on RunPod via SSH) to fix the error and retry. Budget 3-4 crash-fix cycles.

#### M2.2 — Architecture Verification

After it runs without crashing:

```bash
# Verify model structure
RUN_ID=ssm_verify ITERATIONS=1 TRAIN_BATCH_TOKENS=32768 \
  QK_GAIN_INIT=5.25 SSM_LAYERS=3 DATA_DIR=/workspace/parameter-golf/data/ \
  torchrun --standalone --nproc_per_node=1 train_gpt.py 2>&1 | head -50
```

**Validation checklist** (from the output):

- [ ] `model_params` printed — note the number. Compare to baseline (exp_002 had 32M on SP1024). SSM should be similar or slightly fewer params.
- [ ] Warmup steps complete without NaN
- [ ] Loop warmup completes (recurrence on layers 3-5 should be unchanged)
- [ ] Training step 1 produces a finite loss (not NaN, not inf)
- [ ] `peak memory` is not drastically higher than baseline

#### M2.3 — SSM_LAYERS=0 Sanity Check

```bash
# This MUST produce identical results to exp_002 baseline
RUN_ID=ssm0_sanity ITERATIONS=50 TRAIN_BATCH_TOKENS=32768 \
  QK_GAIN_INIT=5.25 SSM_LAYERS=0 SEED=42 DATA_DIR=/workspace/parameter-golf/data/ \
  torchrun --standalone --nproc_per_node=1 train_gpt.py
```

Compare final train_loss at step 50 with baseline at step 50. They should be identical (same seed, same architecture when SSM_LAYERS=0).

**If they differ**: Something in the code change broke the transformer path. Debug before proceeding.

#### M2 Exit Criteria

- [ ] SSM hybrid trains without crashing for 20+ steps
- [ ] SSM_LAYERS=0 matches baseline exactly
- [ ] Model param count noted
- [ ] Peak memory noted
- [ ] Pod stopped

**Budget spent**: ~$10 (2 hours)
**Cumulative**: ~$25

---

### M3: SSM First Real Training ($15, ~2 hours)

**Goal**: First full-length SSM training run. Get a real BPB number.

#### M3.1 — Full 10-Minute Run

```bash
cd /workspace/pgolf-agent/experiments/exp_003

RUN_ID=ssm3_full_s42 QK_GAIN_INIT=5.25 SSM_LAYERS=3 SEED=42 \
  DATA_DIR=/workspace/parameter-golf/data/ \
  torchrun --standalone --nproc_per_node=1 train_gpt.py
```

**While it runs (~10 min), monitor**:
- Is loss decreasing? (Check periodic logs)
- What's tok/s? Higher than baseline = hypothesis confirmed on speed
- Does loop activation at 35% cause instability?

#### M3.2 — Record and Analyze

```bash
cd /workspace/pgolf-agent
python scripts/pgolf.py parse experiments/exp_003/logs/ssm3_full_s42.txt
python scripts/pgolf.py track create --hypothesis "SSM hybrid: 3 Mamba layers (0-2), full SOTA stack" --techniques "ssm_mamba,depth_recurrence,parallel_residuals,qk_gain,xsa,skip_gates,ema,muon_eq_r,gptq"
python scripts/pgolf.py track result exp_003 --bpb <BPB> --size <SIZE> --gpu "1xH100" --seed 42
```

#### M3.3 — Decision Point

| Result | tok/s vs baseline | BPB vs baseline | Action |
|--------|------------------|-----------------|--------|
| Faster + better BPB | Higher | Lower | PROCEED to M4 ablations |
| Faster + similar BPB | Higher | ±0.01 | PROCEED — speed advantage may compound at 8xH100 |
| Faster + worse BPB | Higher | +0.02 to +0.05 | PROCEED — try fewer SSM layers in M4 |
| Same speed + worse BPB | Same | Higher | INVESTIGATE — SSM overhead cancels speed gain |
| Slower + worse BPB | Lower | Higher | PIVOT — SSM doesn't help, try different approach |

**If PIVOT**: Skip to M4 alt plan below.

#### M3 Exit Criteria

- [ ] One full training run completed
- [ ] BPB, tok/s, memory, artifact size all recorded
- [ ] Compared to M1 baseline numbers
- [ ] Decision: proceed, investigate, or pivot
- [ ] Pod stopped
- [ ] Blog notes written

**Budget spent**: ~$15 (2 hours)
**Cumulative**: ~$40

---

### M4: Ablation Grid ($60, ~4 sessions over 2 days)

**Goal**: Systematic understanding of SSM's contribution. Which config works best?

#### M4.1 — Layer Count Ablation (4 runs)

```bash
# Already have SSM_LAYERS=3 from M3. Run the others:
for layers in 0 1 2; do
  RUN_ID=ssm${layers}_s42 QK_GAIN_INIT=5.25 SSM_LAYERS=$layers SEED=42 \
    DATA_DIR=/workspace/parameter-golf/data/ \
    torchrun --standalone --nproc_per_node=1 train_gpt.py
done
```

Record all four:

```bash
python scripts/pgolf.py track create --hypothesis "SSM ablation: $layers SSM layers" --techniques "ssm_mamba,..."
python scripts/pgolf.py track result exp_003_${layers}layer --bpb <BPB> --gpu "1xH100" --seed 42
```

**Expected output**: Table showing BPB and tok/s for 0, 1, 2, 3 SSM layers.

#### M4.2 — SSM Hyperparameter Sweep (6 runs, on best layer count from M4.1)

```bash
BEST_LAYERS=<from M4.1>

# d_state sweep
for dstate in 8 16 32 64; do
  RUN_ID=ssm_ds${dstate} SSM_LAYERS=$BEST_LAYERS SSM_D_STATE=$dstate \
    QK_GAIN_INIT=5.25 SEED=42 DATA_DIR=/workspace/parameter-golf/data/ \
    torchrun --standalone --nproc_per_node=1 train_gpt.py
done

# expand sweep
for expand in 1 2 4; do
  RUN_ID=ssm_ex${expand} SSM_LAYERS=$BEST_LAYERS SSM_EXPAND=$expand \
    QK_GAIN_INIT=5.25 SEED=42 DATA_DIR=/workspace/parameter-golf/data/ \
    torchrun --standalone --nproc_per_node=1 train_gpt.py
done
```

#### M4.3 — Speed Measurement (critical)

From every run's log, extract:
- Total training steps completed
- tok/s
- Wall time

Create table:

```
| Config          | Steps | tok/s  | BPB    | vs baseline |
|-----------------|-------|--------|--------|-------------|
| Baseline (0 SSM)| xxxx | xxxxxx | x.xxxx | —           |
| 1 SSM layer     | xxxx | xxxxxx | x.xxxx | +/-x.xxxx   |
| 2 SSM layers    | xxxx | xxxxxx | x.xxxx | +/-x.xxxx   |
| 3 SSM layers    | xxxx | xxxxxx | x.xxxx | +/-x.xxxx   |
```

**The key question**: Does more tok/s actually translate to more steps and thus lower BPB? Or does the per-step quality loss from SSM outweigh the extra steps?

#### M4 Alt Plan (if SSM pivot needed)

If M3 showed SSM is definitively worse, use M4 budget for an alternative:

**Option A — Megakernels**: Fuse the attention + MLP into a single kernel for layers 0-2. Same hypothesis (faster steps) but without changing the architecture. Lower risk, lower reward.

**Option B — 4-loop recurrence**: Instead of `num_loops=2` (3 iterations), try `num_loops=3` (4 iterations). More virtual depth. The SOTA went from 2-layer to 3-layer recurrence and got 0.005 BPB. Maybe 4-layer helps.

**Option C — Quantization-aware SSM**: Even if pure SSM is worse, hybrid quantization might help. SSM weights might compress differently than attention weights. Worth exploring if SSM BPB is within 0.02 of baseline.

#### M4 Exit Criteria

- [ ] Layer count ablation complete (4 runs)
- [ ] Best layer count identified
- [ ] SSM hyperparameter sweep complete (6 runs)
- [ ] Speed table compiled
- [ ] Clear answer to: "Does SSM help?" with supporting data
- [ ] All results in pgolf.py tracker
- [ ] Knowledge base updated
- [ ] Blog post drafted

**Budget spent**: ~$60 (20 runs × 10 min × $3/hr)
**Cumulative**: ~$100

---

### M5: Optimization ($80, ~4 sessions over 2 days)

**Goal**: Take the best configuration and squeeze maximum performance from it.

#### M5.1 — Quantization Compatibility

```bash
BEST_CONFIG="SSM_LAYERS=X SSM_D_STATE=Y SSM_EXPAND=Z"

# Test: Does GPTQ work properly on SSM weights?
# Compare int6 vs int8 for SSM parameters specifically
RUN_ID=ssm_quant_test $BEST_CONFIG QK_GAIN_INIT=5.25 SEED=42 \
  DATA_DIR=/workspace/parameter-golf/data/ \
  torchrun --standalone --nproc_per_node=1 train_gpt.py

# Check artifact size
grep "Total submission size" logs/ssm_quant_test.txt
```

**If artifact > 16MB**: SSM weights might not compress as well. Options:
- Reduce SSM expand factor
- Use int5 for SSM, int6 for attention
- Reduce d_state

#### M5.2 — EMA Interaction

Your Day 2 blog showed EMA is problematic on 1-GPU. Test:

```bash
# SSM with EMA (default)
RUN_ID=ssm_ema_on $BEST_CONFIG QK_GAIN_INIT=5.25 SEED=42 \
  DATA_DIR=/workspace/parameter-golf/data/ \
  torchrun --standalone --nproc_per_node=1 train_gpt.py

# SSM without EMA (comment out EMA application lines — 
# Claude Code can make a variant)
RUN_ID=ssm_ema_off $BEST_CONFIG QK_GAIN_INIT=5.25 SEED=42 \
  EMA_DECAY=1.0 DATA_DIR=/workspace/parameter-golf/data/ \
  torchrun --standalone --nproc_per_node=1 train_gpt.py
```

Note: Setting EMA_DECAY=1.0 means ema = 1.0 * ema + 0.0 * current = pure EMA (never updates). This effectively disables EMA. Check if the code handles this edge case — if not, tell Claude Code to add an `EMA_ENABLED` flag.

#### M5.3 — Learning Rate for SSM Layers

SSM and attention have different optimal learning rates. Tell Claude Code:

```
Add SSM_LR hyperparameter (env var). In Optimizers.__init__, create a 
separate param group for Mamba parameters with its own learning rate.
Default SSM_LR to matrix_lr (0.022) but allow override.
```

Then sweep:

```bash
for lr in 0.01 0.02 0.03 0.05; do
  RUN_ID=ssm_lr${lr} $BEST_CONFIG SSM_LR=$lr QK_GAIN_INIT=5.25 SEED=42 \
    DATA_DIR=/workspace/parameter-golf/data/ \
    torchrun --standalone --nproc_per_node=1 train_gpt.py
done
```

#### M5.4 — 3-Seed Validation of Best Config

```bash
for seed in 42 43 44; do
  RUN_ID=ssm_best_s${seed} $BEST_CONFIG QK_GAIN_INIT=5.25 SEED=$seed \
    DATA_DIR=/workspace/parameter-golf/data/ \
    torchrun --standalone --nproc_per_node=1 train_gpt.py

  python scripts/pgolf.py track result exp_003_best --bpb <BPB> --seed $seed --gpu "1xH100"
done

python scripts/pgolf.py parse --compare exp_002 exp_003_best
```

**Validation**: p < 0.05 to justify 8xH100 spend. p < 0.01 needed for submission.

#### M5 Exit Criteria

- [ ] Artifact fits in 16MB
- [ ] EMA behavior understood for SSM
- [ ] Best learning rate identified
- [ ] 3-seed results with mean/std
- [ ] Statistical comparison vs baseline
- [ ] Decision: proceed to 8xH100 or not

**Budget spent**: ~$80 (25+ runs)
**Cumulative**: ~$180

---

### M6: 8xH100 Validation ($80, ~2 sessions)

**Goal**: Validate at competition scale. This is where you find out if 1xH100 results transfer.

#### M6.1 — Pod Setup

Spin up 8xH100 SXM pod. This costs ~$24/hr — do NOT leave it idle.

Have everything ready before starting:
- [ ] Best config values written down
- [ ] Script tested on 1xH100
- [ ] Git pushed with latest code

```bash
cd /workspace/pgolf-agent
git pull
cd experiments/exp_003

# Baseline first — confirm SOTA reproduced at 8xH100 scale
RUN_ID=8gpu_baseline QK_GAIN_INIT=5.25 TTT_ENABLED=1 SEED=42 \
  DATA_DIR=/workspace/parameter-golf/data/ SSM_LAYERS=0 \
  torchrun --standalone --nproc_per_node=8 train_gpt.py
```

**Expected**: BPB close to 1.0810. If not, something is wrong — debug before running SSM.

#### M6.2 — SSM at 8xH100 Scale (3 seeds)

```bash
for seed in 42 43 44; do
  RUN_ID=8gpu_ssm_s${seed} $BEST_CONFIG QK_GAIN_INIT=5.25 TTT_ENABLED=1 SEED=$seed \
    DATA_DIR=/workspace/parameter-golf/data/ \
    torchrun --standalone --nproc_per_node=8 train_gpt.py

  python scripts/pgolf.py track result exp_003_8gpu --bpb <BPB> --seed $seed --gpu "8xH100"
done
```

#### M6.3 — Statistical Validation

```bash
python scripts/pgolf.py parse --compare exp_003_8gpu_baseline exp_003_8gpu
```

**Decision matrix**:

| p-value | Delta BPB | Action |
|---------|-----------|--------|
| p < 0.01, Δ > 0.005 improvement | SSM wins | Submit as record |
| p < 0.01, Δ < 0.005 improvement | Marginal | Submit as non-record |
| p < 0.05 | Suggestive | Run 2 more seeds, retest |
| p > 0.05 | No difference | Submit as non-record with analysis |
| SSM worse | — | Submit as documented negative result |

#### M6 Exit Criteria

- [ ] 8xH100 baseline confirmed (~1.081)
- [ ] 3-seed SSM results at 8xH100
- [ ] Statistical comparison complete
- [ ] Submission decision made
- [ ] Pod stopped immediately after last run

**Budget spent**: ~$80 (3-4 hours on 8xH100)
**Cumulative**: ~$260

---

### M7: Submission ($15, ~2 hours on laptop)

**Goal**: Package everything into a PR.

#### M7.1 — Prepare Submission Folder

```
parameter-golf/records/track_10min_16mb/2026-04-XX_SSM_Hybrid_MambaLayers012/
├── README.md          ← Detailed writeup
├── submission.json    ← Metadata
├── train_gpt.py       ← Your code (minified if needed for byte budget)
├── requirements.txt   ← mamba-ssm, brotli, etc.
└── logs/
    ├── seed42.txt
    ├── seed43.txt
    └── seed44.txt
```

Tell Claude Code:

```
Read parameter-golf/records/track_10min_16mb/2026-04-09_SP8192_3LayerRecur_ParResid_QK525_LegalTTT/
for the submission format. Create the same structure for our SSM hybrid
in parameter-golf/records/track_10min_16mb/2026-04-XX_SSM_Hybrid_MambaLayers012/

README.md should include:
- Hypothesis
- Architecture diagram (text)
- Full ablation table from M4
- 3-seed results from M6
- Speed comparison (tok/s SSM vs baseline)
- Discussion of what worked and what didn't
- If negative: detailed analysis of WHY SSM didn't help

submission.json should follow the format of existing submissions.
```

#### M7.2 — Minify for Byte Budget

Check total artifact size. If code + compressed model > 16MB:

```bash
# Check size
wc -c train_gpt.py
ls -la final_model.int6.ptz
```

If needed, minify the Python (remove comments, shorten variable names). The SOTA submission does this — that's why it's 2 lines of LZMA-compressed code.

#### M7.3 — Submit PR

```bash
cd parameter-golf
git checkout -b ssm-hybrid-submission
git add records/track_10min_16mb/2026-04-XX_SSM_Hybrid_MambaLayers012/
git commit -m "SSM-Transformer Hybrid: Mamba blocks in layers 0-2"
git push origin ssm-hybrid-submission
# Open PR on GitHub
```

#### M7 Exit Criteria

- [ ] PR submitted to openai/parameter-golf
- [ ] README includes full results and analysis
- [ ] submission.json valid
- [ ] Code runs in the competition environment
- [ ] Blog post published

**Budget spent**: ~$15 (minor RunPod time for final checks)
**Cumulative**: ~$275

---

### Buffer: $175

Allocated for:

| Use | Estimated Cost |
|-----|---------------|
| Unexpected crashes and debugging | $20 |
| SP8192 tokenizer training (if needed) | $10 |
| Extra ablation runs (if M4 results are ambiguous) | $30 |
| Alternative idea if SSM pivot needed | $60 |
| Additional 8xH100 seeds | $40 |
| Pod idle time (inevitable) | $15 |

---

## 4. Risk Register

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| mamba-ssm won't install on RunPod | 15% | Blocks M2 | Try pip install --no-build-isolation; build from source |
| SP8192 tokenizer unavailable | 30% | Degrades comparisons | Use SP1024; results still valid for SSM vs transformer |
| SSM is slower than attention at seq_len=2048 | 25% | Kills speed hypothesis | Pivot to SSM at longer seq_len or try M4 alt plans |
| SSM BPB is much worse (>1.2) | 20% | No competitive submission | Document why; submit as negative result |
| GPTQ fails on Mamba weights | 20% | Blocks M5 | Skip GPTQ for SSM layers; use naive int8 |
| Artifact exceeds 16MB | 15% | Blocks submission | Reduce SSM expand, use lower bit width |
| Pod idle time burns budget | 40% | Wastes $20-50 | Script runs in advance; stop pod immediately after |

---

## 5. Daily Schedule Template

```
MORNING (laptop):
  - Read AGENTS.md + yesterday's results
  - Plan today's runs (exact commands, written down)
  - Have Claude Code prepare any code changes
  - Push to GitHub

MIDDAY (RunPod session 1, ~2 hours):
  - Spin up pod
  - git pull
  - Run planned experiments (batch them — don't wait between runs)
  - Download all logs
  - Stop pod

AFTERNOON (laptop):
  - python scripts/pgolf.py parse + track result for each run
  - Analyze results
  - Update knowledge base
  - Plan next runs
  - Draft blog notes

EVENING (RunPod session 2 if needed, ~1 hour):
  - Run follow-up experiments based on afternoon analysis
  - Download logs
  - Stop pod

NIGHT (laptop):
  - Write blog post
  - Push everything to GitHub
  - Commit experiment results
```

**The 80/20 rule**: 80% of your time is on your laptop (planning, analyzing, writing). 20% is on RunPod (executing). Pods are expensive clocks. Don't think on a running pod.

---

## 6. Claude Code Instructions Per Milestone

### For Every RunPod Session

Start by telling Claude Code (via SSH):

```
Read /workspace/pgolf-agent/AGENTS.md.
Check: python /workspace/pgolf-agent/scripts/pgolf.py status
I'm at milestone M[X]. Here are today's runs: [list exact commands].
After each run, parse the log and record the result.
```

### After Every Experiment

Tell Claude Code:

```
Parse the log at logs/<RUN_ID>.txt.
Record in the tracker: python scripts/pgolf.py track result <EXP_ID> --bpb <BPB> --seed <SEED> --gpu "<GPU>"
If the result changes our understanding of any technique, update the
relevant doc in knowledge/techniques/.
Write a brief analysis in experiments/<EXP_ID>/analysis.md.
Git commit everything.
```

### At Each Decision Point

Tell Claude Code:

```
Here are the results from milestone M[X]:
[paste the table of results]

Based on AGENTS.md protocols and knowledge/lessons_learned.md, what
should we do next? Consider: statistical significance, speed data,
budget remaining ($X), and the decision matrix in the milestone map.
```

---

## 7. Validation Summary

Before each milestone transition, check ALL exit criteria. Do not proceed if any are unchecked.

```
M0 → M1: Code reviewed, pushed, blog published
M1 → M2: Baseline established, dependencies installed
M2 → M3: SSM code runs, SSM_LAYERS=0 matches baseline
M3 → M4: First real BPB number, proceed/pivot decision made
M4 → M5: Best config identified, speed data collected
M5 → M6: Optimized config with 3-seed validation on 1xH100
M6 → M7: 8xH100 results, submission decision made
M7 → Done: PR submitted, blog published
```
