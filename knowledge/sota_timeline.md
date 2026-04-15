# SOTA Timeline — Parameter Golf Leaderboard

Last updated: April 14, 2026

## Progression

| Date | BPB | Key Technique Added | PR |
|------|-----|--------------------|----|
| Mar 18 | 1.2244 | Naive baseline (9L, 512dim, 1024vocab) | Baseline |
| Mar 18 | 1.2197 | FP16 tied embeddings | #70 |
| Mar 18 | 1.2147 | Mixed int8/int6 precision | — |
| Mar 18 | 1.206 | 2048 sequence length | — |
| Mar 19 | 1.2014 | 4096 sequence length | — |
| Mar 19 | 1.1925 | Sliding window evaluation | — |
| Mar 19 | 1.1748 | 10 layers + Muon WD | — |
| Mar 19 | 1.1630 | Mixed quant + sliding eval | — |
| Mar 19 | 1.1586 | Int6 QAT + zstd MLP 2.6x | — |
| Mar 19 | 1.1570 | Ternary quantization (experimental) | — |
| Mar 19 | 1.1556 | SmearGate + OrthoInit | — |
| Mar 19 | 1.1502 | 11L MLP3x + Int6 QAT | — |
| Mar 20 | 1.1458 | Int6 MLP3x + SmearGate + BigramHash | — |
| Mar 20 | 1.1428 | 10L Int5-MLP + BigramHash(10240) | — |
| Mar 20 | 1.1307 | 11L Efficient Partial XSA | #198 |
| Mar 20 | 1.1271 | XSA4 + EMA + Int6 MLP3x | #198 |
| Mar 21 | 1.1248 | Partial RoPE + LN Scale + EMA | #287 |
| Mar 22 | 1.1228 | EMA + GPTQ-lite + warmdown | #374 |
| Mar 23 | 1.1194 | LeakyReLU² + Legal TTT + Parallel Muon | #549 |
| Mar 25 | 1.1147 | 11L AR Self-Gen GPTQ + XSA | #1019 |
| Mar 31 | 1.1063 | Parallel residuals + mini depth recurrence | #1204 |
| Apr 01 | 1.0979 | SP4096 + larger model + high WD | #1218 |
| Apr 03 | 1.0912 | MuonEq-R + depth recurrence + all-int6 | #1285 |
| Apr 04 | 1.0897 | SP4096 + depth recurrence + parallel res | #1334 |
| Apr 05 | 1.0856 | SP8192 + GPTQ embeddings + loop 4-5 | #1394 |
| Apr 06 | 1.0835 | Hessian-aware SDClip + progressive recurrence | #1412 |
| Apr 06 | 1.0828 | QK-Gain 5.0 + legal score-first TTT | #1413 |
| Apr 08 | 1.0822 | Parallel residuals on SP8192 + TTT stack | #1477 |
| Apr 09 | 1.0810 | 3-layer recurrence + QK-Gain 5.25 | #1493 |

## Key Inflection Points

1. **SP4096/8192 tokenizer** (Apr 1-5): Jumped from ~1.10 to ~1.08 region. Larger vocab = better compression. SP8192 is now standard.

2. **Depth recurrence** (Mar 31): Looping layers 4-5 gave "free" effective depth. Now extended to 3-layer (layers 3-5).

3. **Test-time training** (Mar 23): Legal score-first TTT evaluates tokens first, then trains on them. Significant but conflicts with weight tying.

4. **GPTQ post-training** (Mar 25): Better than naive int8 rounding. Self-generated calibration data.

## Current SOTA Stack (1.0810)

- SP8192 SentencePiece tokenizer
- 3-layer recurrence (layers 3-5)
- Parallel residuals (separate attn/MLP paths)
- QK-Gain 5.25
- Legal score-first TTT
- GPTQ embeddings
- MuonEq-R optimizer
- Std-based GPTQ clipping (SDClip)
- Int6 QAT with STE
- zstd compression
