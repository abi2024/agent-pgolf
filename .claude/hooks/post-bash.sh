#!/bin/bash
# post-bash.sh — runs after every bash command.
# For torchrun commands, parses the log and records spend.
#
# Registered in .claude/settings.json as hooks.bash.post
#
# Args:
#   $1 = the command that was executed
#   $2 = exit code of that command

set -u

CMD="${1:-}"
EXIT_CODE="${2:-0}"

# Only act on torchrun
if [[ ! "$CMD" =~ torchrun ]]; then
    exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Extract NPROC
NPROC=$(echo "$CMD" | grep -oE 'nproc_per_node=[0-9]+' | head -1 | cut -d= -f2)
NPROC="${NPROC:-1}"

# Find the most recently modified train.log in experiments/
LATEST_LOG=""
if [[ -d "$REPO_ROOT/experiments" ]]; then
    LATEST_LOG=$(find "$REPO_ROOT/experiments" -name "train*.log" -mmin -60 2>/dev/null \
                 | xargs -I{} stat -c '%Y {}' 2>/dev/null \
                 | sort -rn | head -1 | awk '{print $2}')
fi

# Try to extract the experiment ID from the log path
EXP_ID=""
if [[ -n "$LATEST_LOG" ]]; then
    EXP_ID=$(echo "$LATEST_LOG" | grep -oE 'exp_[0-9]+' | head -1)
fi

# Log the spend event
python3 "$REPO_ROOT/scripts/pgolf.py" spend log-from-bash \
    --exp-id "${EXP_ID:-unknown}" \
    --nproc "$NPROC" \
    ${LATEST_LOG:+--log-path "$LATEST_LOG"} \
    --exit-code "$EXIT_CODE" 2>&1 | tail -3 >&2

exit 0
