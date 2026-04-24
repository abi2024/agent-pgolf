# `canonical_rescore.py` — Parameter Golf BPB byte-count audit tool

A static, GPU-free audit tool for the ``build_sentencepiece_luts`` byte-count
bug in Parameter Golf submissions descended from the #1698 lineage.

## Purpose

For a candidate ``train_gpt.py``:

1. **Classify** the ``build_sentencepiece_luts`` function as
   CORRECT / BUGGY / OBFUSCATED / UNKNOWN by static regex on the source.
2. **Compute** the canonical and buggy byte totals on the exact scored-token
   subset the upstream ``eval_val_sliding`` would use (``seq_len=2048``,
   ``stride=64`` by default), using only the tokenizer and val shards.
3. **Infer** the canonical BPB for a BUGGY script as
   ``reported_bpb × (buggy_bytes / canonical_bytes)``.
4. **Check** whether the inferred canonical BPB passes a user-supplied
   merged-SOTA threshold.

## When to use

* You are reviewing a newly opened PR and want to know whether it inherited
  the #1698 +1 bug before spending GPU time on a reproduction.
* You are maintaining a record-class leaderboard and want to distinguish
  verified-canonical results from reported-but-unverified results.
* You are a submitter filing a PR and want a one-command self-check before
  you hit "Open PR".
* You want to run the exact same arithmetic yahya010 used in the PR #1734
  closure, against any val shard and any train script.

## When NOT to use

The tool answers one specific question — "does this PR have the #1698 LUT
bug, and if so, what is the canonical-BPB correction?". It does not:

* **Verify** that ``eval_val_sliding`` itself is canonical. The eval-loop
  logic is treated as upstream-faithful; a PR that modified the eval loop
  to compute BPB differently would not be caught.
* **Verify** that the submitter's reported BPB came from the submitted
  ``train_gpt.py``, or from an unmodified val shard. The numerator of the
  correction (cross-entropy loss in nats) is assumed correctly measured.
* **Validate** the trained model artifact, the hyperparameters, the
  submission-pipeline reproducibility, or anything else about a PR beyond
  the LUT.
* **De-obfuscate** ``exec(lzma.decompress(base64.b85decode(...)))``
  wrappers. For OBFUSCATED submissions the tool returns ``lut_status =
  "OBFUSCATED"`` and ``inflation_ratio = null``; verifying those requires
  executing the wrapped code in a sandbox, which is out of scope.
* **Run** the training pipeline, load model weights, or touch the GPU.
* **Rule out** other measurement irregularities. "CORRECT LUT" is a
  necessary-but-not-sufficient signal for a trustworthy BPB.

## Installation

```bash
pip install sentencepiece numpy
```

Val shards are the standard fineweb10B_spNNNN binary format: a 256-int32
header (magic ``20240520``, version ``1``, token count, 253 zero-padded)
followed by ``n`` little-endian uint16 tokens.

## CLI reference

```text
python scripts/canonical_rescore.py \
    --train-script PATH \
    --tokenizer    PATH \
    --val-data     STR \
    [--seq-len 2048] \
    [--stride 64] \
    [--reported-bpb FLOAT] \
    [--pr-number INT] \
    [--threshold 1.0738] \
    [--max-val-tokens INT] \
    [--skip-byte-count] \
    [--scoring-mode {sliding-window-boundary-masked,all-tokens-boundary-masked,all-tokens-no-mask}] \
    [--output PATH]
```

Pass ``--help`` to see the full per-flag documentation.

## Example invocations

**1. Audit a CORRECT PR (PR #1727 reference):**

```bash
python scripts/canonical_rescore.py \
    --train-script /workspace/parameter-golf/records/track_10min_16mb/2026-04-18_SP8192_MPSGD_QKGain525/train_gpt.py \
    --tokenizer    /workspace/parameter-golf/data/tokenizers/fineweb_8192_bpe.model \
    --val-data     '/workspace/parameter-golf/data/datasets/fineweb10B_sp8192/fineweb_val_*.bin' \
    --reported-bpb 1.07217 \
    --pr-number    1727
```

Expected output: ``lut_status = "CORRECT"``, ``inflation_ratio = 1.0``,
``inferred_canonical_bpb = 1.07217``.

**2. Audit a BUGGY script (synthetic fixture):**

```bash
python scripts/canonical_rescore.py \
    --train-script tests/fixtures/buggy_train_gpt.py \
    --tokenizer    /workspace/parameter-golf/data/tokenizers/fineweb_8192_bpe.model \
    --val-data     '/workspace/parameter-golf/data/datasets/fineweb10B_sp8192/fineweb_val_*.bin' \
    --reported-bpb 1.02840 \
    --pr-number    1758
```

Expected output: ``lut_status = "BUGGY"``, ``inflation_ratio ≈ 1.1671``,
``inferred_canonical_bpb ≈ 1.2003``.

**3. Reproduce yahya010's all-tokens-no-mask characterization:**

```bash
python scripts/canonical_rescore.py \
    --train-script <path> \
    --tokenizer    /workspace/parameter-golf/data/tokenizers/fineweb_8192_bpe.model \
    --val-data     '/workspace/parameter-golf/data/datasets/fineweb10B_sp8192/fineweb_val_*.bin' \
    --scoring-mode all-tokens-no-mask
```

On SP8192 fineweb val this gives ratio = 1.1671 (same as the default — see
``audit/methodology.md`` §4 for why the three modes converge on this data
and why the residual gap to yahya's 1.1746 comes from LUT construction, not
scoring strategy).

## Interpreting the JSON output

The tool prints a single JSON object to stdout (and optionally to
``--output``). Field reference:

| Field | Type | Meaning |
|---|---|---|
| `pr_number` | int or null | Value passed via ``--pr-number``. |
| `script_path` | str | Absolute path of the inspected script. |
| `lut_status` | str | ``CORRECT`` / ``BUGGY`` / ``OBFUSCATED`` / ``UNKNOWN``. |
| `reported_bpb` | float or null | Echoed from ``--reported-bpb``. |
| `inflation_ratio` | float or null | ``1.0`` for CORRECT, ``buggy/canonical`` for BUGGY, ``null`` for OBFUSCATED / UNKNOWN. |
| `computed_inflation_ratio` | float or null | The raw ``buggy/canonical`` computed from val data, regardless of LUT classification. Use this if you want the number divorced from the applied-ratio logic. |
| `inferred_canonical_bpb` | float or null | ``reported_bpb × inflation_ratio`` when both are known. |
| `passes_merged_sota_threshold` | bool or null | ``inferred_canonical_bpb ≤ threshold``. |
| `merged_sota_threshold` | float | Echoed from ``--threshold`` (default 1.0738). |
| `seq_len`, `stride`, `scoring_mode` | | Echoed knob values. |
| `canonical_byte_count` | int | Sum of canonical bytes over the scored y-tokens. |
| `buggy_byte_count` | int | Same, but with the +1 bug baked into the LUT. |
| `leading_space_token_count` | int | ``sum(has_leading_space[y])`` — sanity counter. |
| `scored_token_count` | int | Number of y-positions actually scored. |
| `num_windows` | int | Number of sliding windows (0 for ``all-tokens-*`` modes). |
| `notes` | str (optional) | Human-readable caveats. |

### What to conclude from the output

* ``lut_status == "CORRECT"`` ⟹ the reported BPB is **LUT-verified**. This
  is necessary but not sufficient for a trustworthy submission; other
  measurement paths still need human review.
* ``lut_status == "BUGGY"`` ⟹ the PR inherits the #1698 +1 bug. The
  canonical BPB is ``inferred_canonical_bpb`` (assuming the cross-entropy
  numerator was correctly measured).
* ``lut_status == "OBFUSCATED"`` ⟹ the LUT cannot be verified statically.
  This is **not** a claim that the PR is buggy — only that the tool cannot
  tell. Manual sandbox execution of the decoded blob would be required.
* ``lut_status == "UNKNOWN"`` ⟹ the script's ``build_sentencepiece_luts``
  does not match either expected regex. Likely a structural refactor; human
  review needed.

### What NOT to conclude

* A ``CORRECT`` verdict does **not** mean the PR's model actually achieves
  the reported BPB. It means the LUT is canonical. Independent reproduction
  is still the gold standard when a gap between a PR and the rest of the
  leaderboard is large enough to matter (see the PR #1735 caveats in
  ``audit/writeup.md``).
* An ``OBFUSCATED`` verdict is **not** an accusation. yahya010's own PR
  #1734 was obfuscated and turned out to be buggy on self-disclosure, but
  that is one data point; other obfuscated PRs may use canonical LUTs.
* The tool does not catch structural eval-loop modifications. A PR that
  rewrote ``eval_val_sliding`` to compute BPB differently would appear
  CORRECT on this tool but could still be non-canonical.

## Limitations

* **LUT-only.** See "What NOT to conclude" above.
* **SP8192-calibrated examples.** The examples and expected-ratio ranges
  in the tests (``tests/test_canonical_rescore.py``) are for the SP8192
  fineweb tokenizer. Other vocab sizes will have different leading-space
  fractions and therefore different ratios; the tool handles them, but the
  numeric assertions in tests do not.
* **One seed of hardware parity.** The correctness of the inferred BPB
  rests on the assumption that the submitter's cross-entropy loss was
  correctly measured. Our hardware-parity anchor is a single 1×H100
  reproduction of PR #1727 (``experiments/exp_001/analysis.md``) — within
  tolerance but not a rigorous N≥3 check.

## Tests

See ``tests/test_canonical_rescore.py`` for 14 tests covering:

* LUT classification (CORRECT, BUGGY, OBFUSCATED inline-exec, OBFUSCATED
  runpy, UNKNOWN, whitespace-tolerant BUGGY detection, false-positive
  rejection for lzma imports alone).
* Byte-counting math on synthetic data with hand-verified expected values.
* Inflation ratio on real fineweb val subset.
* Each of the three ``--scoring-mode`` variants independently.
* Rejection of unknown ``scoring_mode`` values.
* End-to-end rescore against the PR #1727 canonical script and the buggy
  fixture.

Run:

```bash
python -m pytest tests/test_canonical_rescore.py -q
```

## See also

* ``audit/methodology.md`` — the source-of-truth mathematical derivation,
  including §4 on why the inflation ratio depends on scoring strategy and
  why yahya010's 1.1746 differs from the tool's 1.1671.
* ``audit/writeup.md`` — top-level audit write-up suitable for reviewer
  consumption.
* ``audit/results.md`` and ``audit/corrected_leaderboard.md`` — applied
  results on the top-10 open PRs as of 2026-04-23.
