# exp_002: SOTA Baseline Replication

Replicating the Apr 9 SOTA (1.0810 BPB) as our baseline to build on.

## Files

- `train_gpt.py` — Decompressed readable source (469 lines, reference copy)
- `train_gpt_local.py` — Modified for GTX 3060 on Windows (no flash_attn_3, no Triton, no NCCL)
- `train_gpt_runpod.py` — Original SOTA code, unchanged, ready for RunPod H100
- `analysis.md` — Deep analysis of every technique in the stack

## Key Env Vars

| Variable | Value | Notes |
|----------|-------|-------|
| `QK_GAIN_INIT` | `5.25` | Per-head query scaling (default in code is 5.0, SOTA uses 5.25) |
| `TTT_ENABLED` | `1` | Enable test-time training at eval (adds ~370s to eval) |
| `TTT_LR` | `0.005` | TTT learning rate |
| `TTT_EPOCHS` | `3` | TTT epochs per chunk |
| `SEED` | `1337` | Default seed (SOTA used 42, 314, 999 for 3-seed eval) |

## Local Smoke Test (GTX 3060, Windows)

```bash
TORCHDYNAMO_DISABLE=1 RUN_ID=smoke ITERATIONS=200 TRAIN_BATCH_TOKENS=8192 \
  VAL_LOSS_EVERY=0 TTT_ENABLED=0 python train_gpt_local.py
```

**Important**: Local BPB numbers are meaningless for comparison to leaderboard.
The batch size is 96x smaller (8192 vs 786432), you'll run ~200 steps instead of
~4550, and the 3060 has no Flash Attention 3 (uses PyTorch native SDPA instead).
Local is ONLY for crash-testing code changes before burning H100 time.

### Prerequisites (local)
```bash
pip install brotli sentencepiece
```

## RunPod Full Run (8xH100)

```bash
pip install brotli sentencepiece
pip install flash_attn_3 --no-deps --find-links https://windreamer.github.io/flash-attention3-wheels/cu128_torch291/

# Single seed
SEED=42 QK_GAIN_INIT=5.25 TTT_ENABLED=1 TTT_LR=0.005 TTT_EPOCHS=3 \
  torchrun --standalone --nproc_per_node=8 train_gpt_runpod.py

# 3-seed validation (for publishable results)
for SEED in 42 314 999; do
  SEED=$SEED QK_GAIN_INIT=5.25 TTT_ENABLED=1 TTT_LR=0.005 TTT_EPOCHS=3 \
    torchrun --standalone --nproc_per_node=8 train_gpt_runpod.py
done
```

### 1xH100 iteration (cheaper, for exploration)
```bash
SEED=42 QK_GAIN_INIT=5.25 TTT_ENABLED=0 \
  torchrun --standalone --nproc_per_node=1 train_gpt_runpod.py
```

## Differences: local vs runpod

| | `train_gpt_local.py` | `train_gpt_runpod.py` |
|---|---|---|
| Attention | PyTorch `F.scaled_dot_product_attention` with GQA expansion | Flash Attention 3 (native GQA) |
| torch.compile | Disabled when `TORCHDYNAMO_DISABLE=1` | Always on |
| Math SDP | Enabled | Disabled (uses flash SDP) |
| Distributed | Removed (single-GPU only) | NCCL init for multi-GPU |
| Everything else | Identical | Identical |
