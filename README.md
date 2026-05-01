# agent-pgolf

This repo contains two related artifacts from a seven-day sprint inside [OpenAI's Parameter Golf](https://github.com/openai/parameter-golf) competition (April 2026):

1. **A measurement-integrity audit tool** for the competition's BPB byte-count look-up table. Static-analysis classifier that verifies whether a candidate `train_gpt.py` matches the canonical PR #1727 reference implementation, plus five empirical validation runs that bound the audit's reproduction of the disclosed bug. Documented under `audit/`.

2. **A disciplined-experimentation scaffold** for competing in Parameter Golf, built around Claude Code skills, slash-commands, and budget hooks. Documented in `AGENTS.md`, `WORKFLOW.md`, `scripts/pgolf.py`. The audit was built using this scaffold.

For the methodology essay describing what was learned: [link to synthesis when published].

## Audit quickstart

```bash
git clone https://github.com/abi2024/agent-pgolf.git
cd agent-pgolf

# Install dependencies
pip install -e .
# or if pyproject.toml doesn't include the audit deps:
pip install sentencepiece numpy

# Run the audit tool against any train_gpt.py
python3 scripts/canonical_rescore.py \
    --train-script /path/to/train_gpt.py \
    --tokenizer /path/to/sentencepiece.model \
    --val /path/to/val.bin
```

The tool returns a JSON report classifying the LUT as `CORRECT`, `BUGGY` (with detected bug names), or `OBFUSCATED`, plus the buggy/canonical inflation ratio on the supplied val.

See `scripts/README_canonical_rescore.md` for full usage and `audit/methodology.md` for what the tool checks and why.

## Audit artifacts

- `scripts/canonical_rescore.py` — the audit tool
- `audit/methodology.md` — what the tool checks; structural-vs-empirical distinction
- `audit/writeup.md` — top-10 PR classifications (snapshot)
- `audit/changelog_v2.md` — version history including v2.1 frontier update
- `audit/empirical_validation/` — five validation runs with summaries
- `audit/per_pr_v2/` — per-PR classifications

The audit was submitted to `openai/parameter-golf` as [PR #1804](https://github.com/openai/parameter-golf/pull/1804).

## Worked example

Running the audit on the canonical reference (PR #1727) returns:

```json
{
  "lut_status": "CORRECT",
  "lut_bug_detections": [],
  "leading_space_noplus": true,
  "byte_token_one": true,
  "boundary_predicate_full": true,
  "canonical_ratio": 1.1671413
}
```

Running it on yahya010's PR #1734 (the disclosed-bug PR) returns:

```json
{
  "lut_status": "BUGGY",
  "lut_bug_detections": [
    "leading_space_plus_one",
    "byte_token_wrong_size",
    "missing_is_unused"
  ],
  "leading_space_noplus": false,
  "byte_token_one": false,
  "boundary_predicate_full": false,
  "yahya_ratio_on_sp8192": 1.1655009
}
```

(Note: only `byte_token_wrong_size` produces measurable inflation on SP8192 — the other two are structural deviations that happen to be empirically zero on this val. See `audit/methodology.md` and `audit/empirical_validation/run5_summary.md`.)

---

## Experimentation scaffold (original purpose of this repo)

[The original README content lives below this divider, lightly edited]
