# Measurement Integrity Audit — Parameter Golf BPB Accounting

## Objective

Produce a non-record PR that:
1. Audits BPB accounting across the #1698-family (buggy) and #1700-family (correct) lineage split
2. Publishes a standalone byte-count inspection tool anyone can run on any PR's train_gpt.py
3. Documents the reported-vs-canonical BPB delta and corrects the top-10 open-PR leaderboard
4. Frames the work as a rigorous methodology note — citing yahya010's own self-closure of PR #1734 as precedent

This is Track B work. The deliverable is scientific credibility and tooling, not a BPB record.

---

## Framing: Rigorous Methodology, Not Accusation

yahya010 discovered and self-reported the double-counting bug before any external audit. We are systematizing what he started: applying the same scrutiny to the full set of affected PRs, publishing reusable tooling, and establishing a clear lineage split. The tone is:

> "We replicate yahya010's finding, extend the audit to the full #1698 family, and publish a tool so future submitters can self-verify before filing a PR. The correct-LUT line (PR #1700 / #1727) is the legitimate frontier."

Citation: PR #1734 closure comment, yahya010, 2026-04-19:
> "build_sentencepiece_luts bakes +1 into LUT for leading-space tokens, then eval_val_sliding adds +1 again at eval. Buggy code overcounts bytes by 17.46% vs canonical sp.decode_ids().encode('utf-8'). Reported val_bpb=1.0108 corresponds to canonical val_bpb≈1.1873..."

---

## Definition of Canonical BPB

```
canonical_bpb = (mean_cross_entropy_loss_nats / ln(2)) / (canonical_bytes_per_token)
```

where:

```
canonical_bytes_per_token = (
    sum over scored val tokens t of:
        len(sp.decode_ids([t]).encode('utf-8'))
) / total_scored_tokens
```

**Rules**:
- Decode each token individually via `sp.decode_ids([tok_id])`, then `.encode('utf-8')`, then `len()`
- No +1 adjustments anywhere — not in the LUT, not in the eval loop
- Leading spaces (the `▁` prefix in SentencePiece pieces) are decoded to a space character and counted as 1 byte naturally by `encode('utf-8')`
- Boundary tokens (UNK, control, unused) contribute 0 bytes — consistent with competition starter code intent
- "Scored tokens" = tokens evaluated under the sliding-window protocol (seq_len=2048, stride=64); context tokens are not counted

This is identical to what a naive reference implementation would compute by decoding and re-encoding each token without any LUT.

---

## The Bug: Anatomy of the Double-Count

The #1698 family has two independent +1 additions for leading-space tokens:

```python
# In build_sentencepiece_luts (BUGGY version):
if piece.startswith('▁'):
    has_leading_space_np[token_id] = True
    piece = piece[1:]
base_bytes_np[token_id] = len(piece.encode('utf-8')) + 1  # BUG: +1 baked into LUT
#                                                    ^^^

# In eval_val_sliding:
token_bytes = base_bytes_lut[tgt_ids]  # already has +1 from LUT
token_bytes += has_leading_space_lut[tgt_ids]  # adds another +1 for same tokens
#              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ BUG: double-counts the space
```

The correct code (PR #1727, line 196) uses `len(piece.encode('utf-8'))` without `+1`.

**Measured inflation on SP8192 fineweb val shard** (all-token approximation, for reference only):
- Leading-space token fraction: **62.3%** of all val tokens
- Canonical byte total (all tokens): 151,080,891
- Buggy byte total (all tokens, +1 per leading-space token): 176,332,748
- All-token inflation ratio: **×1.1671** (+16.71%)
- yahya010's claimed ratio: ×1.1746 (+17.46%)

The ~0.75% gap is because sliding-window scoring (seq_len=2048, stride=64) selects a specific subset of tokens, not all val tokens. Scored tokens are the last `seq_len - context_size` tokens of each window, where context tokens overlap with the previous window and are excluded. The fraction of leading-space tokens among scored tokens differs slightly from the full val set, producing a ratio closer to 1.175.

**The tool computes the exact ratio using the actual scored-token subset**, not the all-token approximation:

```python
def compute_inflation_ratio(val_tokens, seq_len, stride, canonical_lut, buggy_lut):
    """Compute exact ratio using same token selection as sliding-window eval."""
    context_size = seq_len - stride
    total = val_tokens.numel() - 1
    window_starts = range(0, total - seq_len + 1, stride)
    
    canonical_bytes = 0
    buggy_bytes = 0
    for ws in window_starts:
        # Scored tokens: skip context (tokens already evaluated in prior window)
        scored_start = ws if ws == 0 else ws + context_size
        scored_tokens = val_tokens[scored_start : ws + seq_len]
        canonical_bytes += canonical_lut[scored_tokens].sum().item()
        buggy_bytes    += buggy_lut[scored_tokens].sum().item()
    
    return buggy_bytes / canonical_bytes  # exact inflation ratio
```

The reported inflation ratio in the audit writeup will be the tool's exact sliding-window output, with the scored-token basis explicitly documented (e.g., "ratio = 1.1746, computed over 18,432,000 scored tokens from 287,500 windows of seq_len=2048, stride=64").

---

## Tool Architecture: Byte-Count Inspection Only (No GPU Required)

**Key insight**: The LUT bug affects only the byte-count denominator of BPB. The model's cross-entropy (numerator) is computed independently of the LUT. Therefore:

```
canonical_bpb = reported_bpb × (buggy_byte_count / canonical_byte_count)
```

where `buggy_byte_count` and `canonical_byte_count` are determined by the tokenizer and the val tokens — **no model forward pass, no checkpoint, no GPU**.

**Architecture consequence**: exp_002 and exp_003 (GPU reproductions of buggy PRs) are **not required** for the core audit claim. The arithmetic is sound:
- exp_001 validates the correct-LUT side on our hardware (GPU, ~$7)
- All buggy-PR canonical BPBs are derived analytically from their reported BPBs × the inflation ratio
- The tool inspects each PR's `train_gpt.py` for the buggy `+1` pattern statically

This reduces audit cost from **$21** (three GPU reproductions) to **$7** (exp_001 only) + tool development time.

**Caveat**: we cannot verify the reported cross-entropy of buggy PRs without running them. The analytical correction assumes their model forward pass is correct and only the byte counting is wrong. For the audit's purpose (correcting reported BPBs, not disputing model quality), this is the appropriate scope.

### Tool Interface

```bash
python scripts/rescore.py \
    --train-script path/to/train_gpt.py \
    --tokenizer    path/to/fineweb_8192_bpe.model \
    --val-data     path/to/fineweb_val_*.bin \
    --seq-len 2048 --stride 64 \
    --report       results/pr1734_rescore.json
```

The tool does NOT load a model checkpoint. It:
1. Statically inspects `train_gpt.py` for the buggy `+1` pattern in `build_sentencepiece_luts`
2. Loads val tokens and computes `canonical_byte_count` and (if buggy) `buggy_byte_count` over the scoring-token subset
3. Reports the inflation ratio and infers canonical BPB from the reported BPB
4. Flags obfuscated scripts (lzma/base64 blobs) as unverifiable by static inspection

**LUT detection logic**:
```python
with open(train_script_path) as f:
    src = f.read()

if 'lzma' in src and 'b85decode' in src:
    lut_status = 'OBFUSCATED — cannot verify statically'
elif re.search(r'len\(piece\.encode\(["\']utf-8["\']\)\)\s*\+\s*1', src):
    lut_status = 'BUGGY — +1 found in LUT construction'
elif re.search(r'base_bytes_np\[token_id\]\s*=\s*len\(piece\.encode', src):
    lut_status = 'CORRECT — no +1 in LUT construction'
else:
    lut_status = 'UNKNOWN — pattern not recognized'
```

### Output JSON

```json
{
  "pr": 1758,
  "script_path": "records/.../train_gpt.py",
  "lut_status": "BUGGY",
  "reported_bpb": 1.02840,
  "inflation_ratio": 1.1746,
  "inferred_canonical_bpb": 1.2080,
  "passes_merged_sota_threshold": false,
  "merged_sota_threshold": 1.0738,
  "canonical_byte_count": 119847213,
  "buggy_byte_count": 140813891,
  "notes": "Descends from PR #1698 buggy lineage. Canonical BPB inferred arithmetically; model not run."
}
```

---

## Audit PR Selection: Three Deep-Dive Submissions

### Candidate Evaluation

**a) PR #1700 (jorge-asenjo, reported 1.07219)**
- Not in local repo — requires `git fetch upstream`
- Parent of PR #1727; reports BPB 0.00002 higher — nearly duplicate measurement
- Research signal: minimal. Two points on the same correct-LUT line at essentially identical BPB adds no information about the lineage split
- **Verdict: skip.** The research value is too low to justify fetching. PR #1727 already covers the correct-LUT side.

**b) PR #1758 (kilojoules, reported 1.02840)**
- Not in local repo — requires `git fetch upstream` for LUT inspection
- Explicitly listed in lessons_learned.md as a confirmed #1698-family descendant
- Different author from PR #1734 (kilojoules, not yahya010) — critical for the "systematic, not per-PR" claim
- With byte-count-only tool: no GPU experiment needed; just inspect the LUT statically
- Inferred canonical BPB: ~1.208 (well below the merged-SOTA threshold of 1.0738)
- **Research signal: high.** A second author, same bug, same magnitude — the strongest possible evidence that this is lineage contamination rather than an individual error.
- **Verdict: select as Audit-3.** Cost: $0 (no GPU run; LUT inspection only after `git fetch upstream`).

**c) PR #1493 (bigbag, reported 1.08100)**
- IS in local repo, hardware-compatible (8×H100 SXM, torch 2.9.1+cu128)
- **Code is obfuscated** — single-line lzma+base64 blob. LUT cannot be verified by static inspection without executing the blob.
- Research signal: would be good anchor, but obfuscation makes it auditable only by running it (GPU required, ~$7 extra)
- **Verdict: skip as a deep-dive target.** Include in the leaderboard impact section as "LUT: OBFUSCATED — not statically verifiable" with a note.

### Selected Three PRs

| Slot | PR | Author | Reported BPB | LUT Status | GPU run needed? |
|------|----|--------|-------------|-----------|-----------------|
| **Audit-1 (buggy, confirmed)** | #1734 | yahya010 | 1.01080 | BUGGY (author-confirmed) | No — closed PR, arithmetic only |
| **Audit-2 (correct, anchor)** | #1727 | yahya010 | 1.07217 | CORRECT (verified line 196) | Yes — exp_001 validates our hardware |
| **Audit-3 (buggy, second author)** | #1758 | kilojoules | 1.02840 | Likely BUGGY (#1698 family) | No — LUT inspection + arithmetic |

**Strategic value of this selection**: Audit-1 and Audit-3 have different authors but the same bug, proving systematic contamination. Audit-2 is the same author as Audit-1 but correct, showing the same author knows how to write the correct LUT when not inheriting from #1698. This is the cleanest possible design for the methodology note.

---

## Output Table (to be populated after exp_001 + tool run)

| PR# | Author | Reported BPB | LUT | Inferred Canonical BPB | Inflation | Passes ≤1.0738? |
|-----|--------|-------------|-----|------------------------|-----------|----------------|
| #1734 | yahya010 | 1.01080 | BUGGY | ~1.180 | +16.7% | **No** |
| #1758 | kilojoules | 1.02840 | Likely BUGGY | ~1.208 | +16.7% | **No** |
| #1727 | yahya010 | 1.07217 | CORRECT | 1.07217 | — | **Yes** |

---

## Impact on the Current Leaderboard

**This is the key deliverable.** Once the tool runs, we re-rank all open PRs by inferred canonical BPB and show what the competition state actually is. This section is what gets shared.

### Methodology for full leaderboard correction

For each open PR in `state/leaderboard.json`:
1. Run the static LUT inspection tool against the PR's `train_gpt.py` (requires fetching unsynced PRs from upstream)
2. If BUGGY: `inferred_canonical_bpb = reported_bpb × inflation_ratio` (ratio computed from actual val tokens)
3. If CORRECT: `inferred_canonical_bpb = reported_bpb`
4. If OBFUSCATED: flag as unverifiable, report both bounds (reported BPB as lower bound, reported × ratio as upper bound)

### Pre-tool preliminary classification — to be replaced by tool-verified data

**⚠ The table below is a placeholder only. No classification is published until the tool runs against each PR's actual `train_gpt.py`.** Classifying PRs by BPB range alone is the sloppy methodology this audit pushes back against — a PR at 1.04 could be correct on a different tokenizer or different val split; a PR at 1.07 could be buggy with a smaller leading-space fraction. Only static LUT inspection produces a valid classification.

Current verified classifications (tool-confirmed or author-confirmed):

| PR# | Author | Reported BPB | LUT Status | Source |
|-----|--------|-------------|-----------|--------|
| #1734 | yahya010 | 1.01080 | **BUGGY** | Author self-confirmed in PR closure comment |
| #1758 | kilojoules | 1.02840 | **BUGGY** | Listed in lessons_learned.md as #1698 descendant |
| #1727 | yahya010 | 1.07217 | **CORRECT** | Static inspection of line 196 (this repo) |

All remaining open PRs require `git fetch upstream` + tool run before classification. The full corrected table will replace this placeholder after the tool runs.

This section will be finalized once the tool inspects each PR's code. Expected to produce the publication's lead table.

### Format for publication

```
## Corrected Leaderboard (Canonical BPB, SP8192 fineweb val, April 2026)

| Rank | PR# | Author | Reported BPB | Canonical BPB | LUT Status |
|------|-----|--------|-------------|--------------|------------|
| 1 | #1727 | yahya010 | 1.07217 | 1.07217 | ✅ Correct |
| 2 | (TBD) | ... | ... | ... | ✅ Correct |
| ... | ... | ... | ... | ... | ... |
| — | #1758 | kilojoules | 1.02840 | ~1.208 | ❌ Buggy (+16.7%) |
| — | #1734 | yahya010 | 1.01080 | ~1.180 | ❌ Buggy, closed |
```

---

## Experiment Sequence (Revised)

| Exp | PR | Purpose | Cost | Status |
|-----|----|---------|------|--------|
| **exp_001** | #1727 | Reproduce correct baseline; validate hardware | ~$7 | Planned |
| ~~exp_002~~ | ~~#1734~~ | ~~Reproduce buggy PR~~ | ~~$7~~ | **Eliminated** — arithmetic replaces GPU run |
| ~~exp_003~~ | ~~#1493~~ | ~~Reproduce anchor~~ | ~~$7~~ | **Eliminated** — obfuscated code; low signal |

Total cost: **~$7** (exp_001 only) vs. original **~$21** estimate.

Post-exp_001 work: `git fetch upstream` to obtain recent PR scripts, then run the static LUT inspection tool against each unsynced PR.

---

## Publication Plan

- **Venue**: Non-record PR to `openai/parameter-golf` under `records/track_non_record_16mb/`
- **Content**:
  - `scripts/rescore.py` — standalone static LUT inspection + byte-count tool (no GPU, no checkpoint)
  - `audit/corrected_leaderboard.md` — the populated corrected leaderboard table (the screenshot-worthy deliverable)
  - `audit/methodology.md` — bug anatomy, canonical BPB definition, inflation ratio derivation
  - `audit/lineage_diagram.md` — text diagram of #1698 (buggy) vs #1700 (correct) lineage split
- **Title**: "Measurement Integrity Note: BPB Byte-Count Audit of the #1698 Lineage"
- **Framing**: Cite PR #1734 closure comment. Acknowledge yahya010 for the self-report. Tool is for future submitters to self-verify — not a disqualification petition.
