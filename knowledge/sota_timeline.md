# SOTA Timeline — Parameter Golf Leaderboard

Last updated by hand: April 17, 2026. This file is auto-appended by `pgolf leaderboard fetch` when new merged records are detected. The `/morning` skill keeps it current.

For the authoritative live state, read `state/leaderboard.json`.

## Progression

| Date | BPB | Key Technique Added | PR |
|------|-----|--------------------|----|
| Mar 18 | 1.2244 | Naive baseline (9L, 512dim, 1024vocab) | Baseline |
| Mar 18 | 1.2197 | FP16 tied embeddings | #70 |
| Mar 18 | 1.2147 | Mixed int8/int6 precision | — |
| Mar 18 | 1.206  | 2048 sequence length | — |
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
| Apr ~14 | 1.0639 | Casefold tokenizer + parallel residuals + systems opt | (check PR list) |

## Key inflection points

1. **SP4096/8192 tokenizer** (Apr 1-5): 1.10 → 1.08 region. Larger vocab = better compression.
2. **Depth recurrence** (Mar 31): Looping layers gave free effective depth. Now 3-layer.
3. **Test-time training** (Mar 23): Legal score-first TTT. Conflicts with weight tying.
4. **GPTQ post-training** (Mar 25): Better than naive int8 rounding. Self-generated calibration data.
5. **Casefold tokenizer + systems opt** (~Apr 14): Current frontier. Systems optimization = more training steps in the 10-min budget.

## Current frontier (as of Apr 17)

The most recent recorded SOTA is ~1.0639 ("Casefold Tokenizer + Parallel Residuals + Systems Optimization"). Run `pgolf leaderboard fetch` to get the current value — the frontier moves every few days.

Run `pgolf leaderboard current` to see the cached state.

## How to keep this file current

The `/morning` skill automatically checks for new SOTA entries. If the leaderboard fetch returns a new record not in this table, append a row. Use the PR title to identify the technique additions.
