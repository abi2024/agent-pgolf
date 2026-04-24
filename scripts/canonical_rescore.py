"""Canonical BPB byte-count audit tool for Parameter Golf.

Statically inspects a candidate ``train_gpt.py`` for the buggy ``+1`` pattern in
``build_sentencepiece_luts`` (or for lzma/base85 obfuscation), then computes the
canonical and buggy byte totals on the exact sliding-window scored-token subset
(``seq_len=2048, stride=64`` by default). The inflation ratio is
``buggy / canonical`` and the inferred canonical BPB for a buggy PR is
``reported_bpb * inflation_ratio``.

No GPU, no model checkpoint required. The arithmetic relies only on the
tokenizer and validation tokens — the cross-entropy numerator is independent of
the LUT bug, so the correction factor applies to the byte denominator only.

See ``knowledge/measurement_integrity_audit.md`` for the full methodology.
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import numpy as np


# ---------------------------------------------------------------------------
# Static LUT classification
# ---------------------------------------------------------------------------

# Obfuscated submissions wrap the entire module body in either
# ``exec(lzma.decompress(base64.b85decode(...)))`` or assign the decoded blob
# to a local and execute it via ``runpy``/``exec`` later. Both share a single
# expression chaining ``decompress(...b85decode(...))`` — match that, not bare
# imports (PR #1727 imports lzma for an artifact compressor without being
# obfuscated).
_OBFUSCATED_RE = re.compile(
    r"[A-Za-z_][\w.]*\.decompress\s*\(\s*[A-Za-z_][\w.]*\.b85decode\s*\(",
    re.DOTALL,
)
_BUGGY_LUT_RE = re.compile(r"len\(\s*piece\s*\.\s*encode\(\s*['\"]utf-8['\"]\s*\)\s*\)\s*\+\s*1")
_CORRECT_LUT_RE = re.compile(
    r"base_bytes_np\[\s*token_id\s*\]\s*=\s*len\(\s*piece\s*\.\s*encode\(\s*['\"]utf-8['\"]\s*\)\s*\)(?!\s*\+\s*1)"
)


def classify_lut(src: str) -> str:
    """Return one of CORRECT, BUGGY, OBFUSCATED, UNKNOWN.

    LUT pattern detection takes priority: a script can mention lzma/b85decode
    for legitimate compression purposes (e.g. PR #1727 wraps a JS minifier
    output) without being obfuscated. We only flag OBFUSCATED when the LUT
    cannot be inspected because the module body is wrapped in an
    ``exec(lzma.decompress(b85decode(...)))`` call AND no readable LUT pattern
    is present.
    """
    if _BUGGY_LUT_RE.search(src):
        return "BUGGY"
    if _CORRECT_LUT_RE.search(src):
        return "CORRECT"
    if _OBFUSCATED_RE.search(src):
        return "OBFUSCATED"
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Tokenizer LUT construction (canonical, no +1)
# ---------------------------------------------------------------------------


def build_canonical_luts(tokenizer_path: Path, vocab_size: Optional[int] = None):
    """Build the canonical LUTs from a SentencePiece model.

    Returns (base_bytes, has_leading_space, is_boundary) as numpy arrays.
    The canonical LUT contains ``len(piece_stripped.encode('utf-8'))`` only
    — no +1 for leading-space tokens (that addition lives in the eval loop,
    gated by the previous token being non-boundary).
    """
    import sentencepiece as spm

    sp = spm.SentencePieceProcessor()
    sp.Load(str(tokenizer_path))
    sp_vocab = int(sp.vocab_size())
    table_size = max(sp_vocab, vocab_size or sp_vocab)

    base_bytes = np.zeros(table_size, dtype=np.int32)
    has_leading_space = np.zeros(table_size, dtype=bool)
    is_boundary = np.ones(table_size, dtype=bool)

    for tid in range(sp_vocab):
        if sp.is_control(tid) or sp.is_unknown(tid) or sp.is_unused(tid):
            continue
        is_boundary[tid] = False
        if sp.is_byte(tid):
            base_bytes[tid] = 1
            continue
        piece = sp.id_to_piece(tid)
        if piece.startswith("▁"):  # SentencePiece ▁
            has_leading_space[tid] = True
            piece = piece[1:]
        base_bytes[tid] = len(piece.encode("utf-8"))

    return base_bytes, has_leading_space, is_boundary


# ---------------------------------------------------------------------------
# Validation token loading
# ---------------------------------------------------------------------------


def load_val_tokens(pattern: str) -> np.ndarray:
    """Read fineweb val .bin shards. Mirrors ``load_data_shard`` in train_gpt.py.

    Header: 256 int32 (1024 bytes). Tokens follow as little-endian uint16.
    """
    paths = sorted(glob.glob(pattern))
    if not paths:
        p = Path(pattern)
        if p.exists():
            paths = [str(p)]
        elif p.is_dir():
            paths = sorted(str(x) for x in p.glob("fineweb_val_*.bin"))
    if not paths:
        raise FileNotFoundError(f"No val files matched: {pattern}")
    chunks = []
    for path in paths:
        header = np.fromfile(path, dtype="<i4", count=256)
        if header.size != 256 or int(header[0]) != 20240520 or int(header[1]) != 1:
            raise ValueError(f"Unexpected shard header for {path}")
        n = int(header[2])
        toks = np.fromfile(path, dtype="<u2", count=n, offset=256 * 4)
        if toks.size != n:
            raise ValueError(f"Short read for {path}: expected {n} got {toks.size}")
        chunks.append(toks)
    return np.concatenate(chunks) if len(chunks) > 1 else chunks[0]


# ---------------------------------------------------------------------------
# Sliding-window byte computation
# ---------------------------------------------------------------------------


SCORING_MODES = (
    "sliding-window-boundary-masked",
    "all-tokens-boundary-masked",
    "all-tokens-no-mask",
)


@dataclass
class ByteCountResult:
    canonical_byte_count: int
    buggy_byte_count: int
    leading_space_token_count: int
    scored_token_count: int
    num_windows: int
    scoring_mode: str = "sliding-window-boundary-masked"


def compute_byte_counts(
    val_tokens: np.ndarray,
    base_bytes: np.ndarray,
    has_leading_space: np.ndarray,
    is_boundary: np.ndarray,
    seq_len: int,
    stride: int,
    scoring_mode: str = "sliding-window-boundary-masked",
) -> ByteCountResult:
    """Compute canonical and buggy byte totals under the chosen scoring mode.

    Three modes are supported:

    * ``sliding-window-boundary-masked`` (default): scored y-tokens = the exact
      subset the upstream ``eval_val_sliding`` in PR #1727 actually scores
      (``seq_len=2048, stride=64`` windows, last window trimmed to end of val).
      Leading-space bytes are gated by ``~is_boundary[x_prev]`` — the same gate
      the eval loop applies. This is what PR #1727's eval pipeline reports.
    * ``all-tokens-boundary-masked``: scored y-tokens = every position in the
      flat slice ``val_tokens[1:N]``. Same boundary-mask gate. On val data
      where the sliding windows already tile the full stream (the SP8192 case),
      this is numerically identical to sliding-window-boundary-masked.
    * ``all-tokens-no-mask``: scored y-tokens = flat ``val_tokens[1:N]`` slice,
      with boundary_mask = 1 everywhere (every leading-space byte is counted).
      This corresponds to the "decode the whole stream and count UTF-8 bytes"
      naive ground-truth that yahya010 used in the PR #1734 closure note.

    The buggy byte total always equals canonical + ``sum(has_leading_space[y])``
    regardless of the mask — the LUT adds +1 per leading-space token, and the
    eval still adds the gated +1 on top, so the per-token delta is exactly one.
    The inflation *ratio* varies because the canonical denominator varies.
    """
    if val_tokens.ndim != 1:
        raise ValueError("val_tokens must be 1-D")
    if scoring_mode not in SCORING_MODES:
        raise ValueError(f"unknown scoring_mode {scoring_mode!r}; valid: {SCORING_MODES}")
    total_tokens = int(val_tokens.shape[0]) - 1
    context_size = seq_len - stride
    if context_size < 0:
        raise ValueError(f"seq_len ({seq_len}) must be >= stride ({stride})")

    if scoring_mode.startswith("sliding-window"):
        # Replicate upstream window selection for the window count + tile end.
        window_starts = [
            ws for ws in range(0, total_tokens, stride) if ws + context_size < total_tokens
        ]
        num_windows = len(window_starts)
        if num_windows == 0:
            return ByteCountResult(0, 0, 0, 0, 0, scoring_mode=scoring_mode)
        last_ws = window_starts[-1]
        last_end = min(last_ws + seq_len, total_tokens)
        expected_scored = last_end
    else:
        # "all-tokens-*" variants score every position in val_tokens[1:N].
        num_windows = 0
        expected_scored = total_tokens

    y = val_tokens[1 : expected_scored + 1].astype(np.int64, copy=False)
    x = val_tokens[0 : expected_scored].astype(np.int64, copy=False)

    bb = base_bytes[y].astype(np.int64)
    ls = has_leading_space[y]
    if scoring_mode.endswith("no-mask"):
        mask = np.ones_like(ls)
    else:
        pb = is_boundary[x]
        mask = ~pb
    canonical_total = int(bb.sum()) + int((ls & mask).sum())
    leading_space_total = int(ls.sum())
    buggy_total = canonical_total + leading_space_total

    return ByteCountResult(
        canonical_byte_count=canonical_total,
        buggy_byte_count=buggy_total,
        leading_space_token_count=leading_space_total,
        scored_token_count=int(expected_scored),
        num_windows=num_windows,
        scoring_mode=scoring_mode,
    )


# ---------------------------------------------------------------------------
# Top-level rescore entrypoint
# ---------------------------------------------------------------------------


def rescore(
    train_script: Path,
    tokenizer: Path,
    val_data: str,
    seq_len: int = 2048,
    stride: int = 64,
    reported_bpb: Optional[float] = None,
    pr_number: Optional[int] = None,
    threshold: float = 1.0738,
    max_val_tokens: Optional[int] = None,
    skip_byte_count: bool = False,
    scoring_mode: str = "sliding-window-boundary-masked",
) -> dict:
    src = train_script.read_text(errors="replace")
    lut_status = classify_lut(src)

    counts: Optional[ByteCountResult] = None
    inflation_ratio: Optional[float] = None
    notes: list[str] = []

    if lut_status == "OBFUSCATED":
        notes.append("Code is lzma/b85-obfuscated; LUT cannot be verified statically.")
    elif lut_status == "UNKNOWN":
        notes.append(
            "build_sentencepiece_luts pattern not recognized; manual review required."
        )

    if not skip_byte_count and lut_status != "OBFUSCATED":
        base_bytes, has_leading_space, is_boundary = build_canonical_luts(tokenizer)
        val_tokens = load_val_tokens(val_data)
        if max_val_tokens is not None and val_tokens.shape[0] > max_val_tokens:
            val_tokens = val_tokens[:max_val_tokens]
            notes.append(f"Truncated val tokens to {max_val_tokens} for fast inspection.")
        counts = compute_byte_counts(
            val_tokens, base_bytes, has_leading_space, is_boundary, seq_len, stride,
            scoring_mode=scoring_mode,
        )
        if counts.canonical_byte_count > 0:
            inflation_ratio = counts.buggy_byte_count / counts.canonical_byte_count

    # Apply the inflation only when the LUT is actually buggy. CORRECT scripts
    # already report canonical BPB; OBFUSCATED scripts cannot be classified.
    applied_ratio: Optional[float]
    if lut_status == "CORRECT":
        applied_ratio = 1.0
    elif lut_status == "BUGGY":
        applied_ratio = inflation_ratio
    else:
        applied_ratio = None

    inferred_canonical_bpb: Optional[float] = None
    if reported_bpb is not None and applied_ratio is not None:
        inferred_canonical_bpb = reported_bpb * applied_ratio

    passes_threshold: Optional[bool] = None
    if inferred_canonical_bpb is not None:
        passes_threshold = inferred_canonical_bpb <= threshold

    result = {
        "pr_number": pr_number,
        "script_path": str(train_script),
        "lut_status": lut_status,
        "reported_bpb": reported_bpb,
        "inflation_ratio": applied_ratio,
        "computed_inflation_ratio": inflation_ratio,
        "inferred_canonical_bpb": inferred_canonical_bpb,
        "passes_merged_sota_threshold": passes_threshold,
        "merged_sota_threshold": threshold,
        "seq_len": seq_len,
        "stride": stride,
        "scoring_mode": scoring_mode,
    }
    if counts is not None:
        result["canonical_byte_count"] = counts.canonical_byte_count
        result["buggy_byte_count"] = counts.buggy_byte_count
        result["leading_space_token_count"] = counts.leading_space_token_count
        result["scored_token_count"] = counts.scored_token_count
        result["num_windows"] = counts.num_windows
    if notes:
        result["notes"] = "; ".join(notes)
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--train-script", type=Path, required=True)
    p.add_argument("--tokenizer", type=Path, required=True)
    p.add_argument("--val-data", type=str, required=True,
                   help="Path or glob for fineweb val .bin files")
    p.add_argument("--seq-len", type=int, default=2048)
    p.add_argument("--stride", type=int, default=64)
    p.add_argument("--reported-bpb", type=float, default=None)
    p.add_argument("--pr-number", type=int, default=None)
    p.add_argument("--threshold", type=float, default=1.0738)
    p.add_argument("--max-val-tokens", type=int, default=None,
                   help="Truncate val data (for fast smoke tests; do not use for audit)")
    p.add_argument("--skip-byte-count", action="store_true",
                   help="Only run static LUT classification; skip the byte computation")
    p.add_argument("--scoring-mode", type=str, default="sliding-window-boundary-masked",
                   choices=list(SCORING_MODES),
                   help=(
                       "Which y-token subset + boundary-mask policy to use for the "
                       "byte totals. 'sliding-window-boundary-masked' (default) "
                       "mirrors PR #1727's eval_val_sliding exactly and yields the "
                       "ratio the eval pipeline would report. 'all-tokens-no-mask' "
                       "mirrors yahya010's 'decode the full stream' ground-truth "
                       "used in the PR #1734 closure. See audit/methodology.md §4."
                   ))
    p.add_argument("--output", type=Path, default=None,
                   help="Write JSON to this path (in addition to stdout)")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    result = rescore(
        train_script=args.train_script,
        tokenizer=args.tokenizer,
        val_data=args.val_data,
        seq_len=args.seq_len,
        stride=args.stride,
        reported_bpb=args.reported_bpb,
        pr_number=args.pr_number,
        threshold=args.threshold,
        max_val_tokens=args.max_val_tokens,
        skip_byte_count=args.skip_byte_count,
        scoring_mode=args.scoring_mode,
    )
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
