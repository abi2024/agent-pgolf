---
name: submit-check
description: Full pre-submission validation. Verifies all competition requirements before filing a leaderboard PR. Paranoid by design.
---

Validate experiment $ARGUMENTS for submission as a leaderboard PR. **Be paranoid.** This is where mistakes become permanent public record.

## 1. Ensure leaderboard state is fresh

```bash
python scripts/pgolf.py leaderboard fetch
```

The SOTA comparison uses the cached leaderboard. If the fetch is more than 4 hours old, get a fresh one first.

## 2. Run the CLI gate

```bash
python scripts/pgolf.py submit-check $ARGUMENTS
```

This script enforces:

1. **Seeds** — at least 3 recorded
2. **Artifact size** — all seeds under 16,000,000 bytes (from DB; you should also verify against the actual file size on disk)
3. **Wall time** — all seeds under 600s on 8×H100_SXM specifically
4. **GPU type** — all seeds on 8×H100_SXM (no 1×H100 seeds mixed in for a record submission)
5. **Statistical significance** — 3-seed mean beats current SOTA by ≥0.005
6. **Reproducibility metadata** — torch_version, pg_commit, gpu_model all populated
7. **Log integrity** — each log contains `final_int8_zlib_roundtrip_exact` line
8. **Static cheat scan** — train_gpt.py doesn't reference validation data paths or make network calls

If any check FAILS, the script exits non-zero and prints all failures. Do not proceed.

## 3. Additional manual checks (the script can't do these)

### 3a. Actual artifact file on disk
The DB has a recorded size, but verify the artifact file itself:
```bash
for f in experiments/$ARGUMENTS/*.bin experiments/$ARGUMENTS/model*.pt; do
    [ -f "$f" ] && echo "$(wc -c < $f) $f"
done
```
Hand-check: no file is > 16,000,000 bytes.

### 3b. Train script is the one used
```bash
diff experiments/$ARGUMENTS/train_gpt.py parameter-golf/train_gpt.py | head -50
```
Confirm the diff is exactly the minimal change the experiment was supposed to test, not some accumulation of dev changes. Only the intended changes, nothing else.

### 3c. Seeds are truly independent
```bash
grep -l "SEED=" experiments/$ARGUMENTS/train_seed*.log | xargs grep "SEED="
```
Each log should show a different seed value. Same seed twice = same run twice = not independent.

### 3d. Pre-registration alignment
```bash
sqlite3 pgolf.db "SELECT decision_rule FROM pre_registration WHERE experiment_id='$ARGUMENTS'"
```
Confirm the rule was set BEFORE any seeds ran. If no pre-registration exists, submission is questionable (optional stopping risk). Mention this to Abi.

## 4. Generate the PR body

If all checks pass, the `pgolf submit-check` script will have printed a PR-ready summary block. Copy that as the starting point. Augment with:

### Title
```
Record: <concise technique description> — val_bpb X.XXXX (3-seed mean)
```

Use the exact phrasing "val_bpb X.XXXX" in the title — the leaderboard tooling parses this.

### Body structure
```markdown
## Summary
<1-2 sentences: what changed from parent, what's the headline result>

## Result
| Seed | val_bpb | Wall time | Artifact size |
|------|---------|-----------|---------------|
| 1337 | X.XXXX  | NNNs      | NN.NN MB      |
| 1338 | X.XXXX  | NNNs      | NN.NN MB      |
| 1339 | X.XXXX  | NNNs      | NN.NN MB      |
| **mean** | **X.XXXX** | — | — |
| **std**  | **X.XXXX** | — | — |

Beats current SOTA (X.XXXX, PR #NNN) by X.XXXX.
Statistical test: Welch's t-test vs SOTA-reported seeds, p = P.PPP.

## Change from parent (PR #XXXX)
<Specific technique or config change. Diff if short.>

## Reproduction
```bash
cd records/track_10min_16mb/2026-04-DD_<slug>_<bpb>/
RUN_ID=record \
MAX_WALLCLOCK_SECONDS=600 \
torchrun --standalone --nproc_per_node=8 train_gpt.py
```

## Hardware
- 8× NVIDIA H100 80GB HBM3 (SXM)
- PyTorch 2.8.0+cu128
- parameter-golf commit: <hash>
```

## 5. Stage the PR branch (don't push yet)

```bash
cd parameter-golf
git checkout -b record-YYYY-MM-DD-<slug>

# Create the record folder
RECORD_DIR="records/track_10min_16mb/$(date +%Y-%m-%d)_<slug>_<bpb_no_dots>"
mkdir -p "$RECORD_DIR"

# Copy canonical run files
cp ../experiments/$ARGUMENTS/train_gpt.py "$RECORD_DIR/"
cp ../experiments/$ARGUMENTS/train_seed*.log "$RECORD_DIR/"
cat > "$RECORD_DIR/README.md" << 'EOF'
<the PR body from step 4>
EOF

git add "$RECORD_DIR/"
git commit -m "Record: <title>"
```

## 6. Final confirmation

Print to Abi:

```
═══ SUBMIT-CHECK PASSED for $ARGUMENTS ═══

Your best seed:  X.XXXX
3-seed mean:     X.XXXX ± Y.YYYY
Current SOTA:    X.XXXX (PR #NNN)
Delta:           -Z.ZZZZ (beats by Z.ZZZZ, threshold 0.005 ✓)
p-value:         P.PPPP  (threshold 0.01 ✓)

Branch prepared: record-YYYY-MM-DD-<slug>
PR body ready to paste (see above).

⚠  I will NOT push the PR. Review the branch, then push manually:
   cd parameter-golf && git push origin record-YYYY-MM-DD-<slug>

   Then open a PR on GitHub using the body above.
```

**Never auto-push a PR.** Abi files it manually after review.

## If checks fail

List ALL failures (not just the first). For each, propose a specific fix:

- "Seeds: have 2, need 3" → "Run one more seed: `SEED=1339 PGOLF_CONFIRM_8XH100=1 torchrun ...`"
- "Log missing final line" → "Re-run seed NNNN — log appears truncated"
- "std > 0.003" → "Seed XXXX looks like an outlier; re-run it to check"

Then stop. Do not try to continue toward submission with fixable failures.
