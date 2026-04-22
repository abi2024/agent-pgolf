# How to frame non-record submissions

Non-record PRs are the main recruiter-signal opportunity in this challenge. OpenAI explicitly welcomes them and the README says <quote>"We'd love to see weird & creative ideas in the challenge."</quote> This doc is the guide for framing non-record submissions to maximize both research value and reviewer attention.

## The three framings that work

Reviewers at OpenAI read dozens of PRs. What they remember is framing, not raw numbers. These three framings consistently get attention:

### 1. "Harness modification, not weight modification"

Strong for anything test-time (LaCT, LoRA-TTT, output-head adaptation, retrieval-at-eval).

**Why it works:** Meta-Harness (Lee, Nair, Zhang, Lee, Khattab, Finn, 2026) established that the scaffolding around a frozen LLM matters as much as the model. Parameter Golf usually optimizes the weights; a submission that shows "we kept weights fixed and improved BPB by X through a harness change" is on the right side of current research trends. Two concurrent citations (Meta-Harness + the specific TTT paper) gives the PR a strong reading list.

**Sample opening sentence for the PR README:**
> This submission demonstrates that a test-time harness modification — without any change to the training script or model weights — yields a measurable BPB improvement. The approach is inspired by recent findings on harness-level optimization in LLM systems (Meta-Harness, Lee et al. 2026; LaCT, <authors> 2026).

### 2. "Negative result with a clean ablation"

Strong when you try something that seemed promising and it didn't work. This is undervalued — the competition lore explicitly rewards documented failures (Issue #140's "dead zones" list is essentially a community negative-results doc).

**Why it works:** A rigorous negative result with a clear failure mechanism is harder to produce than a positive one, and saves other participants time. Reviewers specifically call out experiments that rule out a whole class of approaches.

**Sample opening:**
> We report that technique X, despite showing promise in setting Y, fails under the Parameter Golf constraints because of mechanism Z. This negative result rules out a family of approaches that have been proposed several times in Issue #140 comments.

The key is a clear failure mechanism, not just "we tried it and it was worse." Your analysis must identify *why* it failed — usually seed variance, compute budget interaction, or quantization interaction.

### 3. "Ablation sweep on an underexplored axis"

Strong for tokenizer variants, width/depth tradeoffs, quantization schedules, or precision mixing.

**Why it works:** Parameter Golf has explored some axes deeply (recurrence, XSA, QAT) but left others shallow. A 4-5 point sweep on an underexplored axis gives the community a reference they can build on. This is the highest-acceptance-rate framing.

**Sample opening:**
> We sweep <parameter X> across values {A, B, C, D} on a fixed SOTA-stack backbone and report the BPB / artifact-size tradeoff. Our best configuration matches SOTA within noise; the value of this submission is the curve, not the peak.

## What NOT to do in non-record framings

- **Don't claim novelty when there's none.** If a technique is in Issue #140's tried list, don't pretend you invented it. Cite the earlier attempt and explain your variation.
- **Don't inflate your statistics.** If std > 0.002 across 3 seeds, say so. Competition reviewers will notice and it damages credibility.
- **Don't skip the reproduction command.** Every non-record PR needs a copy-pasteable command that reproduces the result. Without it, reviewers can't evaluate.
- **Don't bury the punchline.** The headline finding goes in the first two sentences of the README. Reviewers skim.

## Required PR structure for non-record

```markdown
# Non-record: <short descriptive title>

**TL;DR:** <One sentence: what you did and what the effect was. Include the number.>

## Motivation
<Why this direction? What gap in the current landscape does this fill? 1 paragraph.>

## Approach
<What you actually did. Specific enough to reproduce without reading the code. 2-3 paragraphs.>

## Results
<Seed table. Parent comparison. Statistical test. Artifact size. Wall time.>

## Why it worked / didn't work
<Mechanism. This is the research value — speculate carefully, cite evidence from traces.>

## Limitations
<What you didn't test. What might break the result. Be explicit — reviewers respect this.>

## Related work
<The 2-4 papers and 2-4 prior PRs that frame this. Include links.>

## Reproduction
```bash
<exact command that reproduces>
```

## Credits / acknowledgments
<If you used scaffolding, autoresearch tools, or prior PR code — credit them.>
```

## The recruiter-signal hedge

Even if your submission is mid, framing it this way does three things that matter for recruiting:

1. Shows you read the research literature (the citation list is visible)
2. Shows you practice statistical discipline (seed tables, stated limitations)
3. Shows you can write for an audience (the structure signals research maturity)

Your autoresearch scaffold is itself a credible artifact. Link it from the PR (with repo URL in the README credits section). A clean pipeline shared publicly is a stronger hiring signal than raw leaderboard rank.

## Fallback — if the research doesn't work at all

If Day 6 arrives and nothing is publishable, your fallback is a **methodology submission**: a non-record describing your experiment pipeline, with 2-3 concrete negative results from your experiments. Frame as:

> This non-record documents our experiment pipeline and three null findings across N experiments. The pipeline is publicly available at <URL> and designed to replicate under similar compute constraints.

This is still a valid non-record, demonstrates rigor, and most importantly: it always works. You can write it even if every training run failed.
