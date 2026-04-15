# Day 0: Starting Parameter Golf — Training a 16MB Language Model

*April 14, 2026 · Parameter Golf Daily Blog*

## The Challenge

OpenAI launched [Parameter Golf](https://github.com/openai/parameter-golf) — a competition to train the best language model that fits in 16MB and trains in under 10 minutes on 8xH100 GPUs. The metric is bits per byte (BPB) on the FineWeb validation set. Lower is better.

The current SOTA sits at 1.0810 BPB, down from a 1.2244 baseline in just three weeks. That's a massive 12% improvement driven by a stack of clever techniques: aggressive quantization, depth recurrence, larger tokenizers, test-time training, and more.

## My Approach

I'm building an autonomous experiment workflow powered by Claude Code. Instead of manually tweaking hyperparameters and reading papers, I've structured my project so Claude Code can:

- Track experiments in a SQLite database
- Parse training logs automatically
- Maintain a knowledge base of techniques with linked papers
- Generate blog posts from experiment data
- Run the full experiment loop: hypothesize → implement → train → analyze → learn

The philosophy: Claude Code IS the agent. No API wrapper, no framework overhead. Just clean scripts it calls via bash and structured markdown it reads and updates.

## What I'm Starting With

The competition's naive baseline gets 1.2244 BPB with:
- 9 transformer layers, 512 hidden dim
- 1024-token SentencePiece vocabulary
- Tied embeddings, 4 KV heads
- Int8 quantization + zlib compression

The current SOTA at 1.0810 adds:
- SP8192 tokenizer (8x larger vocabulary)
- 3-layer depth recurrence (loop layers 3-5)
- Parallel residuals
- QK-Gain scaling at 5.25
- Legal score-first test-time training
- GPTQ post-training quantization
- MuonEq-R optimizer
- Int6 QAT during training

## My First Goal

Reproduce the baseline, then work through the technique stack one piece at a time. Each technique gets its own experiment, its own knowledge doc, and its own blog post.

## What's Next

Tomorrow: reproducing the baseline on a 1xH100 RunPod instance and setting up the full experiment tracking pipeline.

---

*Part of my [Parameter Golf](https://github.com/openai/parameter-golf) daily blog series.
Building in public, one experiment at a time.*
