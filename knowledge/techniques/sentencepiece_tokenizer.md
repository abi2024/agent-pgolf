# SentencePiece Tokenization (SP1024 → SP8192)

## Summary

The tokenizer determines how text is split into tokens before the model sees it. Larger vocabularies (more token types) mean each token carries more information, improving bits-per-byte compression at the cost of a larger embedding table.

## Why It Matters for Parameter Golf

BPB (bits per byte) is tokenizer-agnostic — it measures how well the model compresses raw bytes. But the tokenizer still matters enormously because it determines how efficiently the model can represent text patterns.

With SP1024 (1024 token vocab), the model needs many tokens to represent common words. With SP8192, common words and subwords get their own tokens, making prediction easier.

## Key Results

| Vocab Size | Best BPB | When Adopted | Impact |
|------------|---------|--------------|--------|
| SP1024 | 1.1063 | Baseline → Mar 31 | Original standard |
| SP4096 | 1.0979 | Apr 1 (PR #1218) | ~0.008 improvement |
| SP8192 | 1.0856 | Apr 5 (PR #1394) | ~0.012 further improvement |

The jump from SP1024 to SP8192 contributed roughly 0.02 BPB improvement — one of the single biggest gains in the competition.

## Trade-offs

**Larger vocab = bigger embedding table:**
- SP1024: 1024 × dim embedding matrix
- SP8192: 8192 × dim embedding matrix
- With tied embeddings and int6 quantization, SP8192 costs ~8192 × 512 × 0.75 bytes ≈ 3MB more

**Larger vocab = fewer tokens per document:**
- Fewer tokens = shorter sequences = faster training per document
- But also fewer "learning opportunities" per document

**The sweet spot**: SP8192 is now standard in all top submissions. The embedding cost is worth it.

## Papers

- **SentencePiece: A simple and language independent subword tokenizer and detokenizer** — Kudo & Richardson 2018 (https://arxiv.org/abs/1808.06226)

- **Neural Machine Translation of Rare Words with Subword Units** — Sennrich et al. 2016 (BPE original, https://arxiv.org/abs/1508.07909)

- **BPE-dropout: Simple and Effective Subword Regularization** — Provilkov et al. 2020 (https://arxiv.org/abs/1910.13267)

## Implementation Notes

- Competition provides pre-built tokenizers: `data/tokenizers/fineweb_1024_bpe.model`, etc.
- Download data variant: `python3 data/cached_challenge_fineweb.py --variant sp8192`
- Must update `VOCAB_SIZE` env var and `TOKENIZER_PATH` when switching
- GPTQ for embeddings (PR #1394) is critical — naive quantization of the larger embedding table hurts quality

## Blog Angle

"Why your tokenizer matters more than your architecture — how switching from 1024 to 8192 tokens gave us 0.02 BPB for free"

## My Experiments

*No experiments yet.*
