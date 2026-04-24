#!/usr/bin/env bash
# Pass B driver: re-audit each top-10 PR with the extended three-variant LUT
# classifier. Writes audit/per_pr_v2/<pr>.json — does NOT overwrite v1 outputs
# under audit/per_pr/.
#
# Usage:
#   ./run_audit_v2.sh
set -euo pipefail

REPO=/workspace/parameter-golf
TOOL=/workspace/agent-pgolf/scripts/canonical_rescore.py
TOKENIZER=/workspace/parameter-golf/data/tokenizers/fineweb_8192_bpe.model
VAL_GLOB='/workspace/parameter-golf/data/datasets/fineweb10B_sp8192/fineweb_val_*.bin'
OUT=/workspace/agent-pgolf/audit/per_pr_v2

mkdir -p "$OUT"

# pr,reported_bpb,author — same list as v1
PRS=(
  "1785,1.01925,OE-GOD"
  "1758,1.0284,kilojoules"
  "1738,1.0354,alertcat"
  "1735,1.0429,AjAnubolu"
  "1779,1.06421,leon2k2k2k"
  "1769,1.06453,dexhunter"
  "1756,1.06505,romeerp"
  "1771,1.06513,bigbag"
  "1736,1.06549,dexhunter"
  "1784,1.07081,renqianluo"
)

cd "$REPO"

for entry in "${PRS[@]}"; do
  IFS=',' read -r PR BPB AUTHOR <<<"$entry"
  echo "===== PR #$PR ($AUTHOR, reported $BPB) ====="
  branch="pr-$PR"
  result_file="$OUT/$PR.json"

  if ! git rev-parse --verify "$branch" >/dev/null 2>&1; then
    if ! git fetch upstream "pull/$PR/head:$branch" 2>&1 | tail -3; then
      echo '{"pr_number": '"$PR"', "lut_status": "NEEDS_MANUAL_REVIEW", "notes": "fetch failed"}' >"$result_file"
      continue
    fi
  fi
  if ! git checkout -q "$branch" 2>&1; then
    echo '{"pr_number": '"$PR"', "lut_status": "NEEDS_MANUAL_REVIEW", "notes": "checkout failed"}' >"$result_file"
    continue
  fi

  if ! script=$(ls -d records/track_10min_16mb/*/ 2>/dev/null | sort | tail -1); then
    echo '{"pr_number": '"$PR"', "lut_status": "NEEDS_MANUAL_REVIEW", "notes": "no track_10min_16mb dir"}' >"$result_file"
    continue
  fi
  script_path="${script}train_gpt.py"
  if [[ ! -f "$script_path" ]]; then
    echo '{"pr_number": '"$PR"', "lut_status": "NEEDS_MANUAL_REVIEW", "notes": "no train_gpt.py at '"$script_path"'"}' >"$result_file"
    continue
  fi
  echo "  using script: $script_path"

  if ! python "$TOOL" \
      --train-script "$script_path" \
      --tokenizer "$TOKENIZER" \
      --val-data "$VAL_GLOB" \
      --reported-bpb "$BPB" \
      --pr-number "$PR" \
      --output "$result_file" >/dev/null 2>&1; then
    echo '{"pr_number": '"$PR"', "script_path": "'"$script_path"'", "lut_status": "NEEDS_MANUAL_REVIEW", "notes": "rescore tool error"}' >"$result_file"
    continue
  fi

  python - <<EOF
import json
p = "$result_file"
d = json.load(open(p))
d["author"] = "$AUTHOR"
d["pr_dir"] = "$script"
open(p, "w").write(json.dumps(d, indent=2) + "\n")
print("  ", d["lut_status"], "deviations=", d.get("lut_bug_detections"), "inferred=", d.get("inferred_canonical_bpb"))
EOF

done

git checkout -q pr-1727
echo "===== restored to pr-1727 ====="
