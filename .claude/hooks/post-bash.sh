#!/bin/bash
# post-bash.sh — runs after Bash tool calls.
# Reads JSON payload on stdin per Claude Code hook API.
# For torchrun commands, logs spend to state/spending.jsonl.

set -u

PAYLOAD=$(cat)
CMD=$(echo "$PAYLOAD" | jq -r '.tool_input.command // empty')

# Only log torchrun
if [[ ! "$CMD" =~ torchrun ]]; then
    exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Extract NPROC
NPROC=$(echo "$CMD" | grep -oE 'nproc_per_node=[0-9]+' | head -1 | cut -d= -f2)
NPROC="${NPROC:-1}"

# Find the most recently modified train log
LATEST_LOG=""
if [[ -d "$REPO_ROOT/experiments" ]]; then
    LATEST_LOG=$(find "$REPO_ROOT/experiments" -name "train*.log" -mmin -60 2>/dev/null \
                 | xargs -I{} stat -c '%Y {}' 2>/dev/null \
                 | sort -rn | head -1 | awk '{print $2}')
fi

# Extract the experiment ID from the log path
EXP_ID=""
if [[ -n "$LATEST_LOG" ]]; then
    EXP_ID=$(echo "$LATEST_LOG" | grep -oE 'exp_[0-9]+' | head -1)
fi

# Delegate spend logging to pgolf.py
if command -v python3 >/dev/null 2>&1; then
    python3 "$REPO_ROOT/scripts/pgolf.py" spend log-from-bash \
        --command "$CMD" \
        --nproc "$NPROC" \
        --log-path "${LATEST_LOG:-none}" \
        --exp-id "${EXP_ID:-none}" \
        2>/dev/null || true
fi

exit 0
