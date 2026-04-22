"""Tests for the log parser. This is the foundation of every downstream decision."""

import sys
from pathlib import Path

# Add scripts to path so we can import pgolf
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pgolf  # noqa: E402


FIXTURES = Path(__file__).parent / "fixtures"


def test_success_log_extracts_final_bpb():
    """The authoritative metric is final_int8_zlib_roundtrip_exact, not any other val_bpb line."""
    text = (FIXTURES / "sample_train_log_success.txt").read_text()
    result = pgolf.extract_metrics(text)

    assert result["has_final_bpb"] is True
    assert result["val_bpb"] == 1.08120543
    assert not result["warnings"], f"Unexpected warnings: {result['warnings']}"


def test_success_log_distinguishes_prequant_from_final():
    """Pre-quant BPB is 1.0745, final is 1.0812. Must not confuse them."""
    text = (FIXTURES / "sample_train_log_success.txt").read_text()
    result = pgolf.extract_metrics(text)

    assert result["val_bpb"] == 1.08120543, "Must use the final post-quant value"
    assert result["val_bpb_preqant"] == 1.0745, "Must separately capture pre-quant"
    # The final number is higher (worse) than pre-quant — that's normal
    assert result["val_bpb"] > result["val_bpb_preqant"]


def test_success_log_extracts_artifact_size():
    text = (FIXTURES / "sample_train_log_success.txt").read_text()
    result = pgolf.extract_metrics(text)

    assert result["artifact_size_bytes"] == 15842716
    assert result["artifact_size_mb"] == 15.843
    assert result["under_16mb"] is True


def test_success_log_extracts_wall_time():
    text = (FIXTURES / "sample_train_log_success.txt").read_text()
    result = pgolf.extract_metrics(text)

    assert result["wall_time_seconds"] == 598.3


def test_success_log_extracts_seed():
    text = (FIXTURES / "sample_train_log_success.txt").read_text()
    result = pgolf.extract_metrics(text)

    assert result["seed"] == 1337


def test_success_log_extracts_training_steps():
    text = (FIXTURES / "sample_train_log_success.txt").read_text()
    result = pgolf.extract_metrics(text)

    assert result["training_steps"] == 8394


def test_success_log_loss_curve_monotonic_decreasing():
    """Smoke test: loss should go down over training."""
    text = (FIXTURES / "sample_train_log_success.txt").read_text()
    result = pgolf.extract_metrics(text)

    losses = [p["loss"] for p in result["loss_curve"]]
    assert len(losses) > 5
    assert losses[0] > losses[-1], "Loss should decrease over training"


def test_failed_log_missing_final_bpb():
    """Truncated/crashed logs do NOT contain the final metric. Must flag this."""
    text = (FIXTURES / "sample_train_log_failed.txt").read_text()
    result = pgolf.extract_metrics(text)

    assert result["has_final_bpb"] is False
    # Either val_bpb is None or a warning is raised
    if result["val_bpb"] is not None:
        assert any("final" in w.lower() for w in result["warnings"])


def test_oversize_log_flags_16mb_violation():
    """An artifact over 16MB must be explicitly flagged."""
    text = (FIXTURES / "sample_train_log_oversize.txt").read_text()
    result = pgolf.extract_metrics(text)

    assert result["artifact_size_bytes"] == 16423987
    assert result["under_16mb"] is False
    assert any("16" in w or "EXCEEDS" in w for w in result["warnings"])


def test_parser_does_not_crash_on_empty_log():
    result = pgolf.extract_metrics("")
    assert result["val_bpb"] is None
    assert result["artifact_size_bytes"] is None


def test_parser_does_not_crash_on_garbage():
    result = pgolf.extract_metrics("this is not a log file at all")
    assert result["val_bpb"] is None


def test_parser_regex_does_not_false_positive_on_random_numbers():
    """The old parser would match ANY float followed by 's'. Verify this is fixed."""
    text = """
    Some random text with 5.3s and 1.2s mentioned.
    Also mentioning val_loss:2.0 somewhere.
    And a step 100 loss: 4.5 line.
    No actual training happened here.
    """
    result = pgolf.extract_metrics(text)
    # Must not pick up arbitrary numbers as wall time
    assert result["wall_time_seconds"] is None
    # val_loss may be picked up, that's fine, it's explicit
    assert result["val_bpb"] is None  # No val_bpb anywhere


def test_parser_ignores_periodic_vs_final_val_bpb():
    """If a log has multiple val_bpb entries, use the final_int8_zlib_roundtrip_exact one specifically."""
    text = """
    step 1000 val_bpb: 2.5000
    step 2000 val_bpb: 2.0000
    step 3000 val_bpb: 1.5000
    final_int8_zlib_roundtrip_exact val_bpb: 1.2000
    """
    result = pgolf.extract_metrics(text)
    assert result["val_bpb"] == 1.2000
    assert result["has_final_bpb"] is True
