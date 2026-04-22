#!/bin/bash
# pre-bash.sh — intercepts Bash tool calls before execution.
# Reads JSON payload on stdin per Claude Code hook API.
# Exit codes:
#   0 = allow
#   2 = block (stderr is shown to Claude)

set -u

# Read the hook payload from stdin
PAYLOAD=$(cat)
CMD=$(echo "$PAYLOAD" | jq -r '.tool_input.command // empty')

# Only gate torchrun commands
if [[ ! "$CMD" =~ torchrun ]]; then
    exit 0
fi

# Locate the repo root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Budget config
TOTAL_BUDGET="${PGOLF_BUDGET:-500}"
RESERVE="${PGOLF_RESERVE:-60}"

# Extract --nproc_per_node (default 1)
NPROC=$(echo "$CMD" | grep -oE 'nproc_per_node=[0-9]+' | head -1 | cut -d= -f2)
NPROC="${NPROC:-1}"

# Per-run cost estimates (10-min wallclock)
case "$NPROC" in
    1)  EST_COST="0.55"  ;;  # 1xH100_SXM
    2)  EST_COST="1.10"  ;;
    4)  EST_COST="2.20"  ;;
    8)  EST_COST="4.12"  ;;  # 8xH100_SXM
    *)  EST_COST="0.55"  ;;
esac

# 8xH100 requires explicit confirmation
if [[ "$NPROC" == "8" && "${PGOLF_CONFIRM_8XH100:-0}" != "1" ]]; then
    echo "BLOCKED: 8xH100 run requires PGOLF_CONFIRM_8XH100=1" >&2
    echo "This is a ~\$${EST_COST} run. Confirm by prefixing with PGOLF_CONFIRM_8XH100=1" >&2
    exit 2
fi

# MAX_WALLCLOCK_SECONDS is required
if [[ ! "$CMD" =~ MAX_WALLCLOCK_SECONDS ]]; then
    echo "BLOCKED: torchrun requires MAX_WALLCLOCK_SECONDS in env" >&2
    echo "Add MAX_WALLCLOCK_SECONDS=600 (or 120 for smoke) before torchrun" >&2
    exit 2
fi

# Budget check
if [[ -f "$REPO_ROOT/state/spending.jsonl" && "${PGOLF_FORCE:-0}" != "1" ]]; then
    SPENT=$(awk -F'"cost_usd":' '{if(NF>1){split($2,a,","); sum+=a[1]}} END{printf "%.2f", sum+0}' \
            "$REPO_ROOT/state/spending.jsonl" 2>/dev/null || echo "0")
    REMAINING=$(awk -v b="$TOTAL_BUDGET" -v s="$SPENT" 'BEGIN{printf "%.2f", b-s}')
    SPENDABLE=$(awk -v r="$REMAINING" -v res="$RESERVE" 'BEGIN{printf "%.2f", r-res}')
    WOULD_REMAIN=$(awk -v s="$SPENDABLE" -v c="$EST_COST" 'BEGIN{printf "%.2f", s-c}')

    if (( $(awk -v w="$WOULD_REMAIN" 'BEGIN{print (w<0)?1:0}') )); then
        echo "BLOCKED: run would exceed spendable budget" >&2
        echo "  Spent: \$${SPENT} / \$${TOTAL_BUDGET} (reserve: \$${RESERVE})" >&2
        echo "  Spendable: \$${SPENDABLE}, est run cost: \$${EST_COST}" >&2
        echo "Override with PGOLF_FORCE=1 if you know what you're doing" >&2
        exit 2
    fi
fi

exit 0
