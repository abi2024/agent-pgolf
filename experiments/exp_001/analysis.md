# exp_001 — PR #1727 Reproduction (Hardware Parity Anchor)

## Result

| Metric | Value |
|---|---|
| Seed | 1337 |
| val_bpb (final, post-TTT) | **1.07431** |
| val_bpb (pre-quant, post-EMA) | 1.07380 |
| val_bpb (post-quant, pre-TTT) | 1.08636 |
| Iterations completed | 4982 / 20000 (wall-clock cap) |
| Train wall-time | 596.1 s |
| Total eval wall-time (TTT phase) | 417.1 s |
| Final artifact | 15,935,812 bytes (under 16 MB) |
| Hardware | 8×H100 SXM, torch 2.8.0+cu128 |

## Comparison to PR #1727 reported result

PR #1727 (yahya010) reports a **3-seed mean of val_bpb = 1.07217** with the same code, on the same 8×H100 SXM hardware.

| Source | val_bpb |
|---|---|
| PR #1727 reported (3-seed mean) | 1.07217 |
| exp_001 seed 1337 (this run) | 1.07431 |
| Δ (ours − reported mean) | **+0.00214** |

Our pre-registered tolerance interval was [1.062, 1.082]. **1.07431 lands well within tolerance**, and the +0.00214 delta is consistent with single-seed variance around a 3-seed mean (yahya010's seeds are 0, 42, 1234; ours is 1337). The sign and magnitude of the gap give no reason to suspect hardware drift, kernel non-determinism beyond seed noise, or a meaningful methodology difference.

**Hardware parity is confirmed.** Subsequent audit work can treat reported BPBs from runs on this same hardware (8×H100 SXM, torch 2.8/2.9 + cu128) as directly comparable to our own measurements without a hardware correction term.

## TTT recovery arc

The phased test-time-training stage (4 phases, prefix_docs=2000) is responsible for a **−0.01205 BPB recovery** after quantization:

```
post-EMA (pre-quant)  : 1.07380   ← model after EMA but before int6 cast
post-quant (pre-TTT)  : 1.08636   ← naive int6 GPTQ + brotli baseline
post-TTT (final)      : 1.07431   ← legal score-first TTT recovery
```

The quantization gap is +0.01256 BPB (1.07380 → 1.08636), and TTT recovers all but +0.00051 of it. This is the canonical "quantization-then-TTT" pattern that defines the correct-LUT frontier line. The final number we publish (1.07431) is the post-TTT score, identical in protocol to what PR #1727 reports.

## What this enables

1. **Measurement Integrity Audit can proceed with confidence.** The plan in `knowledge/measurement_integrity_audit.md` rests on the analytic claim that

       canonical_bpb_PR_X = reported_bpb_PR_X × (buggy_byte_count / canonical_byte_count)

   This claim is independent of model quality. exp_001 establishes that *when we run the same code on the same hardware we land within seed noise of the reported number* — so when we later assert that PR #1758 etc. have inflated BPBs, no one can rebut us with "your hardware just runs differently."

2. **Audit cost is bounded.** With hardware parity confirmed, exp_002 and exp_003 (originally GPU reproductions of buggy PRs) are eliminated per the audit plan. Total audit GPU spend is ~$7 (this experiment) instead of the original ~$21 estimate.

3. **PR #1727 is the legitimate frontier anchor.** With the buggy-LUT line discounted, the true SOTA on the correct-LUT line sits at 1.07217 (PR #1727, yahya010). All subsequent claims of "beats SOTA" must clear that bar in canonical BPB, not reported BPB.

## Caveats

- We ran one seed (1337); the reported number is a 3-seed mean. Our +0.00214 delta is one sample, not a distribution. We do not need additional seeds for the audit purpose, but if anyone challenged the parity claim we would re-run two more seeds before responding.
- 4982/20000 iterations completed before the 600 s wall-clock cut. This matches the upstream behavior — PR #1727 itself does not converge to a steady-state in 600 s and relies on the warmdown schedule (warmdown_frac=0.75) to land cleanly at the wall-clock boundary.
- The post-quant val_bpb of 1.08636 (not 1.08089 etc.) is from the diagnostic run inside `train_gpt.py`; the post-TTT 1.07431 is the score that would be reported under competition rules.

## Files

- `train_seed1337.log` — full training log
- `final_model.pt` — pre-quantization checkpoint (135 MB, gitignored)
- `final_model.int6.ptz` — quantized brotli artifact (~16 MB, gitignored)
- `config.json` — experiment metadata
