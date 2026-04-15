#!/usr/bin/env python3
"""RunPod setup helper — commands Claude Code can run on a fresh pod.

This isn't meant to be run as a script. It's a reference for Claude Code
to copy-paste commands when setting up a RunPod instance.

Usage: Read this file, then run the commands manually or via Claude Code bash.
"""

SETUP_COMMANDS = """
# ═══════════════════════════════════════════════════════════════
# RunPod Setup for Parameter Golf
# Run these commands after SSHing into a new pod
# ═══════════════════════════════════════════════════════════════

# 1. Clone repos
cd /workspace
git clone https://github.com/openai/parameter-golf.git
git clone <YOUR_PGOLF_AGENT_REPO> pgolf-agent

# 2. Download data (SP8192 for current SOTA stack)
cd parameter-golf
python3 data/cached_challenge_fineweb.py --variant sp8192

# For SP1024 baseline experiments:
# python3 data/cached_challenge_fineweb.py --variant sp1024

# 3. Verify GPU setup
nvidia-smi
python3 -c "import torch; print(f'CUDA: {torch.cuda.is_available()}, GPUs: {torch.cuda.device_count()}')"

# 4. Quick baseline test (1xGPU, should take ~10 min)
cd /workspace/parameter-golf
RUN_ID=baseline_test \\
DATA_PATH=./data/datasets/fineweb10B_sp1024/ \\
TOKENIZER_PATH=./data/tokenizers/fineweb_1024_bpe.model \\
VOCAB_SIZE=1024 \\
torchrun --standalone --nproc_per_node=1 train_gpt.py

# 5. For 8xH100 final submission:
# torchrun --standalone --nproc_per_node=8 train_gpt.py

# ═══════════════════════════════════════════════════════════════
# tmux cheat sheet (for long-running training)
# ═══════════════════════════════════════════════════════════════

# Start a named session:
#   tmux new -s training

# Detach from session:
#   Ctrl+B, then D

# Reattach to session:
#   tmux attach -t training

# List sessions:
#   tmux ls

# Kill session:
#   tmux kill-session -t training
"""

# Cost estimates for budgeting
COST_ESTIMATES = {
    "1xH100_SXM": {"per_hour": 3.09, "10min_run": 0.52},
    "1xH100_PCIe": {"per_hour": 2.49, "10min_run": 0.42},
    "1xA100_80GB": {"per_hour": 1.64, "10min_run": 0.27},
    "8xH100_SXM": {"per_hour": 24.72, "10min_run": 4.12},
}

if __name__ == "__main__":
    print(SETUP_COMMANDS)
    print("\n# Cost estimates per 10-minute training run:")
    for gpu, costs in COST_ESTIMATES.items():
        print(f"#   {gpu}: ${costs['10min_run']:.2f} per run (${costs['per_hour']:.2f}/hr)")
