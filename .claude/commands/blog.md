---
description: Generate a complete blog post draft (800-1200 words) for a given day and experiment.
argument-hint: [day_number] [exp_id]
allowed-tools: Read, Write, Glob
model: sonnet
---


Generate a publication-quality blog post. Arguments: $ARGUMENTS should contain a day number and an experiment ID (e.g., "3 exp_007").

**Do NOT use `pgolf blog` (it produces a scaffold with `*Fill in*` blanks).** Write the post yourself, drawing from these sources:

- `experiments/<exp_id>/config.json` — hypothesis, technique stack, parent
- `experiments/<exp_id>/analysis.md` — what happened, decision, rationale
- `experiments/<exp_id>/train*.log` — actual data you can reference concretely
- `knowledge/techniques/<relevant>.md` — technical background, papers
- `knowledge/sota_timeline.md` — where this result sits in the leaderboard narrative
- `knowledge/lessons_learned.md` — connections to prior findings
- `state/leaderboard.json` — current SOTA for framing

## Required structure — follow EXACTLY

```markdown
# Day N: <punchy title reflecting what actually happened>

*April DD, 2026 · Parameter Golf series*

## What I tried

<2-3 paragraphs, prose. Name the specific technique, the specific config change, and the parent experiment. No bullet points here — this is narrative. Readers should understand both WHAT you did and WHY this was the right next experiment given the last one.>

## Why I expected it to work

<1-2 paragraphs explaining the mechanistic reason. Cite the relevant paper with a link. This is the "learning" part — write like you're teaching a curious reader who knows ML but doesn't know Parameter Golf.>

## Results

<A real table with all seeds, the parent's result, the statistical test, and the pre-registered thresholds. Include artifact size. Include std. Include the decision (GREEN/YELLOW/RED) and which threshold was hit or missed.>

Parent (exp_XXX): X.XXXX BPB
This experiment: X.XXXX ± Y.YYYY (3-seed mean)
Delta: ±Z.ZZZZ at p=P.PPPP

Pre-registered thresholds:
- Publish: ≤ SOTA - 0.005 → <hit/miss>
- Internal: ≤ parent - 0.003 → <hit/miss>

Decision: GREEN/YELLOW/RED because <explicit rationale>

## What I learned

<This is the most important section. 2-3 paragraphs. What does this tell us about the technique? Did the hypothesis hold? What would you do differently? Did it update your model of the problem? If RED, be honest about why — negative results are signal.>

## The broader concept: <Technique name>

<2-3 paragraphs teaching the technique to someone who doesn't know it. Analogies encouraged. Cite the primary paper with a link. Explain WHY this technique exists — what problem was it invented to solve? How does it show up in Parameter Golf specifically?>

## Resources

<Links to papers (arxiv URLs), the parameter-golf PR if one is being filed, the experiment's commit hash. Keep this tight — 3-5 links, not a dump.>

## What's next

<One concrete paragraph. What specific experiment follows from this result? Name the technique, the hypothesis, the expected signal. NO "I'll figure it out tomorrow" — commit to a direction.>

---

*Part of my [Parameter Golf](https://github.com/openai/parameter-golf) daily blog series.*
```

## Writing constraints

- **Length**: 800-1200 words. Under 800 feels thin; over 1200 loses readers.
- **Voice**: First-person. Direct. Curious. Abi is a solo founder building in public — the voice should feel like a smart friend walking through their work, not a research paper.
- **Concrete numbers**: Every claim should have a number or a link. "This worked well" is weak; "this improved BPB by 0.004 at p=0.006" is strong.
- **Honesty about negative results**: If RED, say so clearly. A blog series about an ML competition that only posts wins is less credible than one that documents failures. The audience is founders and researchers — they respect honesty.
- **No lists in prose sections**: Use prose for "What I tried", "Why", "What I learned", "Broader concept". Use a table for Results. Only use a short list in Resources.

## Output

Write to `blog/drafts/day_NN_<slug>.md` where NN is zero-padded. Slug is lowercase, underscores, ~30 chars max.

After writing, print a SHORT editor's note to Abi:

```
Draft saved: blog/drafts/day_03_xxx.md

Voice check on:
- [specific line or framing you're least sure about]
- [another]

Suggested X thread summary (3 tweets):
1. <hook>
2. <key finding>
3. <link to post>
```

Do not write more than 5 lines of chat output. The real work is in the file.

## Gotchas

- Don't use the `pgolf blog` scaffold command's output directly — it produces a template with blanks. Write the post yourself.
- Voice: first-person, direct, honest about failures. "This didn't work because X" beats "results were mixed."
- Always include the statistical test numbers, not just the decision. Readers care about p-values.
