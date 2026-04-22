#!/bin/bash
# pre-bash.sh — intercepts bash commands before execution.
# Gates torchrun commands based on budget and GPU count.
#
# Registered in .claude/settings.json as hooks.bash.pre
#
# Args:
#   $1 = the command string about to be executed
# Exit codes:
#   0 = allow
#   1 = block (with reason written to stderr)

set -u

CMD="${1:-}"

# Only gate torchrun commands
if [[ ! "$CMD" =~ torchrun ]]; then
    exit 0
fi

# Locate the repo root (this script lives at <repo>/.claude/hooks/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Budget config (can be overridden via env)
TOTAL_BUDGET="${PGOLF_BUDGET:-500}"
RESERVE="${PGOLF_RESERVE:-60}"

# Extract --nproc_per_node (default 1)
NPROC=$(echo "$CMD" | grep -oE 'nproc_per_node=[0-9]+' | head -1 | cut -d= -f2)
NPROC="${NPROC:-1}"

# Per-run cost estimates (assume full 10-min budget, 8xH100_SXM pricing from pgolf.py)
case "$NPROC" in
    1)  EST_COST="0.55"  ;;  # 1xH100_SXM @ $3.30/hr × 10min
    2)  EST_COST="1.10"  ;;
    4)  EST_COST="2.20"  ;;
    8)  EST_COST="4.12"  ;;  # 8xH100_SXM @ $24.72/hr × 10min
    *)  EST_COST="0.55"  ;;
esac

# Read current spend
SPENT=$(python3 "$REPO_ROOT/scripts/pgolf.py" spend total --quiet 2>/dev/null || echo "0")

# Arithmetic in python (bash can't do floats)
REMAINING=$(python3 -c "print(round($TOTAL_BUDGET - $SPENT - $RESERVE, 2))")
BUDGET_AFTER=$(python3 -c "print(round($REMAINING - $EST_COST, 2))")

# Hard gate: would exceed budget
if python3 -c "import sys; sys.exit(0 if float('$BUDGET_AFTER') < 0 else 1)"; then
    if [[ "${PGOLF_FORCE:-0}" != "1" ]]; then
        cat >&2 <<EOF
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🛑 BLOCKED: would exceed budget reserve.
   Spent so far:  \$${SPENT}
   Reserve:       \$${RESERVE}
   Est. cost:     \$${EST_COST}  (${NPROC}×H100)
   After run:     \$${BUDGET_AFTER}  (negative means over reserve)

   Override:      PGOLF_FORCE=1 <your command>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EOF
        exit 1
    fi
    echo "[pre-bash] PGOLF_FORCE=1 set; allowing over-budget run" >&2
fi

# Soft gate: 8-GPU runs require explicit confirmation
if [[ "$NPROC" == "8" && "${PGOLF_CONFIRM_8XH100:-0}" != "1" ]]; then
    cat >&2 <<EOF
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠  8xH100 run requires explicit confirmation.
   Est. cost:       \$${EST_COST} per run
   Remaining:       \$${REMAINING}  (after reserving \$${RESERVE})
   After this run:  \$${BUDGET_AFTER}

   To confirm:  PGOLF_CONFIRM_8XH100=1 <your command>

   Typical validation = 3 seeds = 3× this cost.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EOF
    exit 1
fi

# Also verify MAX_WALLCLOCK_SECONDS is set (competition requires the 600s cap)
if [[ ! "$CMD" =~ MAX_WALLCLOCK_SECONDS ]]; then
    if [[ "${PGOLF_NO_WALLCLOCK:-0}" != "1" ]]; then
        cat >&2 <<EOF
⚠  MAX_WALLCLOCK_SECONDS not set. Competition requires the 600s cap.
   Add:  MAX_WALLCLOCK_SECONDS=600 ${CMD}
   Or override with: PGOLF_NO_WALLCLOCK=1
EOF
        exit 1
    fi
fi

echo "[pre-bash] Allowing ${NPROC}-GPU run, est. \$${EST_COST}, \$${REMAINING} spendable" >&2
exit 0
