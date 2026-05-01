# agent-pgolf

This repo contains two related artifacts from a seven-day sprint inside [OpenAI's Parameter Golf](https://github.com/openai/parameter-golf) competition (April 2026):

1. **A measurement-integrity audit tool** for the competition's BPB byte-count look-up table. Static-analysis classifier that verifies whether a candidate `train_gpt.py` matches the canonical PR #1727 reference implementation, plus five empirical validation runs that bound the audit's reproduction of a disclosed bug. Documented under `audit/`.

2. **A disciplined-experimentation scaffold** for competing in Parameter Golf, built around Claude Code skills, slash-commands, and budget hooks. Documented in `AGENTS.md`, `WORKFLOW.md`, `scripts/pgolf.py`. The audit was built using this scaffold.

The audit was submitted to `openai/parameter-golf` as [PR #1804](https://github.com/openai/parameter-golf/pull/1804).

## Audit quickstart

```bash
git clone https://github.com/abi2024/agent-pgolf.git
cd agent-pgolf

# Install dependencies (the audit tool only needs sentencepiece + numpy)
pip install sentencepiece numpy

# Run the audit tool against a candidate train_gpt.py
python3 scripts/canonical_rescore.py \
    --train-script /path/to/train_gpt.py \
    --tokenizer    /path/to/sentencepiece.model \
    --val-data     '/path/to/fineweb_val_*.bin' \
    --reported-bpb 1.07217 \
    --pr-number    1727
```

The tool returns a JSON report classifying the candidate's `build_sentencepiece_luts` function as `CORRECT`, `BUGGY` (with detected bug names), `OBFUSCATED`, or `UNKNOWN`, plus the buggy/canonical inflation ratio on the supplied val.

For full CLI reference see `scripts/README_canonical_rescore.md`. For the methodology see `audit/methodology.md`.

## Worked example

Running the audit on PR #1727 (the canonical reference) against SP8192 fineweb val returns (verified output, `audit/empirical_validation/expected_outputs/pr_1727.json`):

```json
{
  "pr_number": 1727,
  "lut_status": "CORRECT",
  "lut_bug_detections": [],
  "reported_bpb": 1.07217,
  "inflation_ratio": 1.0,
  "computed_inflation_ratio": 1.1671413031314464,
  "inferred_canonical_bpb": 1.07217,
  "passes_merged_sota_threshold": true,
  "canonical_byte_count": 151080891,
  "buggy_byte_count": 176332748,
  "scored_token_count": 40540802
}
```

Running it on yahya010's PR #1734 (the disclosed-bug PR), `audit/empirical_validation/expected_outputs/pr_1734.json`:

```json
{
  "pr_number": 1734,
  "lut_status": "BUGGY",
  "lut_bug_detections": [
    "leading_space_plus_one",
    "missing_is_unused"
  ],
  "inflation_ratio_includes": ["leading_space_plus_one"],
  "reported_bpb": 1.0108,
  "inflation_ratio": 1.1671413031314464,
  "inferred_canonical_bpb": 1.179746429205266,
  "passes_merged_sota_threshold": false
}
```

Notes on the second output:

- `inferred_canonical_bpb` is the corrected BPB assuming only the `leading_space_plus_one` bug is applied. The tool's `notes` field flags this as conservative (an underestimate) when other deviations are also present.
- The static classifier detects two of yahya's three deviations. The third (`byte_token_wrong_size`) requires runtime verification because yahya's function has no `sp.is_byte` branch, so the default branch's behavior cannot be statically proven. The byte-token bug is real and was independently confirmed by `audit/empirical_validation/run2_yahya_byte_token.py`.
- The `computed_inflation_ratio` of 1.1671413 is the canonical buggy/canonical ratio on SP8192 fineweb val. yahya's PR #1734 disclosure quotes 1.1746; the gap is bounded to tokenizer/val state and not closable from yahya's code alone (see `audit/empirical_validation/run4_summary.md` and `run5_summary.md`).

## Audit artifacts

- `scripts/canonical_rescore.py` — the audit tool
- `scripts/README_canonical_rescore.md` — full CLI reference and JSON schema
- `audit/methodology.md` — what the tool checks, why, and the structural-vs-empirical distinction
- `audit/writeup.md` — top-10 PR classifications (snapshot, 2026-04-23)
- `audit/changelog_v2.md` — version history (v2.1: PR #1795 verified-CORRECT, frontier moved; addenda from runs 4 and 5)
- `audit/empirical_validation/` — five validation runs with summaries
- `audit/empirical_validation/expected_outputs/` — verified tool outputs for the worked examples above
- `audit/per_pr_v2/` — per-PR classifications including obfuscation re-checks

## Limitations of the audit tool

The audit verifies the byte-count LUT structure. It does not verify:

- The eval-loop logic itself (`eval_val_sliding`)
- Whether the reported BPB came from the submitted `train_gpt.py`
- Whether the cross-entropy numerator was correctly measured
- Whether the trained model artifact, hyperparameters, or other submission attributes are valid
- LUTs hidden inside `lzma.decompress(b85decode(...))` wrappers (returns `OBFUSCATED`; manual sandbox execution is out of scope)
- Some structural deviations require runtime verification (the `byte_token_wrong_size` false-negative noted above)

A `CORRECT` verdict is necessary but not sufficient for a trustworthy submission.

## Tests

```bash
python -m pytest tests/test_canonical_rescore.py -q
```

20 tests covering LUT classification across CORRECT / BUGGY / OBFUSCATED / UNKNOWN, three-variant deviation detection, byte-counting math on synthetic data, all three `--scoring-mode` variants, and end-to-end rescores.

---

## Experimentation scaffold (original purpose of this repo)

The rest of this repo is a project structure that makes Claude Code a reliable Parameter Golf researcher:

- **AGENTS.md** — Operating instructions (the "system prompt")
- **WORKFLOW.md** — Operator's guide with the exact 7-day workflow
- **.claude/commands/** — Eight slash-commands: `/morning`, `/plan-experiment`, `/run-experiment`, `/analyze-results`, `/synthesize`, `/blog`, `/checkpoint`, `/submit-check`
- **.claude/hooks/** — Bash hooks that enforce budget and require confirmation for expensive runs
- **scripts/pgolf.py** — CLI toolkit: tracking, parsing, spending, leaderboard, submission validation, reports, doctor
- **knowledge/** — Technique catalog, SOTA timeline, lessons learned, research framing guide
- **state/** — Mutable truth: spending ledger, cached leaderboard

See `WORKFLOW.md` for the full operator's guide.

### Quick start (scaffold, not audit)

```bash
# Make hooks executable (may be needed depending on how you unpacked)
chmod +x .claude/hooks/*.sh

# Run local validation — does NOT touch GPUs, does NOT cost money
python scripts/validate_workflow.py

# Install optional dependencies
pip install scipy   # for Welch's t-test p-values

# Fetch current leaderboard
python scripts/pgolf.py leaderboard fetch

# Clone the competition repo alongside
git clone https://github.com/openai/parameter-golf.git

# Check state
python scripts/pgolf.py status
```

If validation passes, you can start using the skills in Claude Code:

Read AGENTS.md. Then run /morning.


### What's enforced vs. what's guidance

**Enforced by code** (the pipeline refuses to proceed if violated):
- Budget exceeded → pre-bash hook blocks torchrun
- 8×H100 without `PGOLF_CONFIRM_8XH100=1` → pre-bash hook blocks
- Missing `MAX_WALLCLOCK_SECONDS` → pre-bash hook blocks
- Known technique conflict per `lessons_learned.md` → `track create` refuses without `--force`

For the rest of the scaffold's documentation, see `WORKFLOW.md`, `AGENTS.md`, `MILESTONE_MAP.md`, and `ARCHITECTURE.md`.
