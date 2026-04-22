"""Tests for the pgolf CLI — track, spend, leaderboard, submit-check."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
PGOLF = [sys.executable, str(REPO / "scripts" / "pgolf.py")]


@pytest.fixture
def temp_project(tmp_path, monkeypatch):
    """Create a temporary pgolf project with its own DB and state/."""
    # Copy the whole project layout we need
    (tmp_path / "scripts").mkdir()
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "experiments").mkdir()
    (tmp_path / "blog" / "drafts").mkdir(parents=True)
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "spending.jsonl").touch()

    # Copy pgolf.py so paths resolve correctly relative to PROJECT_ROOT
    (tmp_path / "scripts" / "pgolf.py").write_text(
        (REPO / "scripts" / "pgolf.py").read_text()
    )
    # Copy lessons_learned so conflict check works
    (tmp_path / "knowledge" / "lessons_learned.md").write_text(
        (REPO / "knowledge" / "lessons_learned.md").read_text()
    )

    return tmp_path


def run_pgolf(project, *args, input_text=None, env_extra=None):
    """Run pgolf.py with the given project as cwd."""
    import os
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(
        [sys.executable, str(project / "scripts" / "pgolf.py"), *args],
        capture_output=True,
        text=True,
        cwd=project,
        input=input_text,
        env=env,
    )
    return result


def test_track_create_assigns_sequential_ids(temp_project):
    r = run_pgolf(temp_project, "track", "create",
                  "--hypothesis", "test one",
                  "--techniques", "baseline")
    assert r.returncode == 0
    assert "exp_001" in r.stdout

    r = run_pgolf(temp_project, "track", "create",
                  "--hypothesis", "test two",
                  "--techniques", "baseline")
    assert r.returncode == 0
    assert "exp_002" in r.stdout


def test_track_create_refuses_known_conflict(temp_project):
    """EMA + depth_recurrence is a known bad combination."""
    r = run_pgolf(temp_project, "track", "create",
                  "--hypothesis", "stack EMA on recurrent model",
                  "--techniques", "ema,depth_recurrence")
    assert r.returncode != 0, "Should refuse a known conflict"
    assert "CONFLICT" in r.stdout.upper() or "CONFLICT" in r.stderr.upper()


def test_track_create_allows_conflict_with_force(temp_project):
    r = run_pgolf(temp_project, "track", "create",
                  "--hypothesis", "forced override",
                  "--techniques", "ema,depth_recurrence",
                  "--force")
    assert r.returncode == 0


def test_track_result_records_seed(temp_project):
    run_pgolf(temp_project, "track", "create",
              "--hypothesis", "test", "--techniques", "baseline")

    r = run_pgolf(temp_project, "track", "result", "exp_001",
                  "--bpb", "1.0850",
                  "--size", "15800000",
                  "--time", "598",
                  "--seed", "1337",
                  "--gpu", "8xH100_SXM")
    assert r.returncode == 0
    assert "completed" in r.stdout.lower()


def test_track_result_fails_for_nonexistent_experiment(temp_project):
    r = run_pgolf(temp_project, "track", "result", "exp_999",
                  "--bpb", "1.0", "--seed", "1337")
    assert r.returncode != 0


def test_spend_total_starts_at_zero(temp_project):
    r = run_pgolf(temp_project, "spend", "total", "--quiet")
    assert r.returncode == 0
    assert float(r.stdout.strip()) == 0.0


def test_spend_log_from_bash_appends_to_jsonl(temp_project):
    r = run_pgolf(temp_project, "spend", "log-from-bash",
                  "--exp-id", "exp_001",
                  "--nproc", "1",
                  "--exit-code", "0")
    assert r.returncode == 0

    log = temp_project / "state" / "spending.jsonl"
    content = log.read_text().strip()
    assert content, "Spending log should have an entry"
    entry = json.loads(content.splitlines()[-1])
    assert entry["gpu"] == "1xH100_SXM"
    assert entry["cost_usd"] > 0
    assert entry["exit_code"] == 0


def test_spend_total_accumulates(temp_project):
    run_pgolf(temp_project, "spend", "log-from-bash",
              "--exp-id", "exp_001", "--nproc", "1", "--exit-code", "0")
    run_pgolf(temp_project, "spend", "log-from-bash",
              "--exp-id", "exp_002", "--nproc", "8", "--exit-code", "0")

    r = run_pgolf(temp_project, "spend", "total", "--quiet")
    total = float(r.stdout.strip())
    assert total > 3.0, f"Two runs should total >$3, got ${total}"
    assert total < 10.0, f"Two runs should total <$10, got ${total}"


def test_register_thresholds_persists(temp_project):
    run_pgolf(temp_project, "track", "create",
              "--hypothesis", "t", "--techniques", "baseline")
    r = run_pgolf(temp_project, "register-thresholds", "exp_001",
                  "--seed1-continue", "1.10",
                  "--publish", "0.005",
                  "--internal", "0.003")
    assert r.returncode == 0
    assert "1.1" in r.stdout


def test_submit_check_fails_with_insufficient_seeds(temp_project):
    """Experiment with only 1 seed must fail submit-check."""
    run_pgolf(temp_project, "track", "create",
              "--hypothesis", "t", "--techniques", "baseline")
    run_pgolf(temp_project, "track", "result", "exp_001",
              "--bpb", "1.05", "--size", "15800000", "--time", "598",
              "--seed", "1337", "--gpu", "8xH100_SXM",
              "--torch-version", "2.8.0+cu128", "--pg-commit", "abc123",
              "--gpu-model", "H100 80GB HBM3")

    r = run_pgolf(temp_project, "submit-check", "exp_001")
    assert r.returncode != 0, "Should fail with only 1 seed"
    assert "seed" in r.stdout.lower() or "seed" in r.stderr.lower()


def test_submit_check_fails_on_oversized_artifact(temp_project):
    """An artifact over 16MB must fail submit-check."""
    run_pgolf(temp_project, "track", "create",
              "--hypothesis", "t", "--techniques", "baseline")

    # Create 3 seeds, but one is oversized
    for seed, size in [(1337, 15800000), (1338, 15900000), (1339, 16500000)]:
        run_pgolf(temp_project, "track", "result", "exp_001",
                  "--bpb", "1.05", "--size", str(size), "--time", "598",
                  "--seed", str(seed), "--gpu", "8xH100_SXM",
                  "--torch-version", "2.8.0+cu128", "--pg-commit", "abc",
                  "--gpu-model", "H100")

    r = run_pgolf(temp_project, "submit-check", "exp_001")
    assert r.returncode != 0
    assert "16MB" in r.stdout or "size" in r.stdout.lower()


def test_parse_log_success_fixture(temp_project):
    """Parse the success fixture and verify the output JSON."""
    fixture = REPO / "tests" / "fixtures" / "sample_train_log_success.txt"
    target = temp_project / "experiments" / "sample.log"
    target.parent.mkdir(exist_ok=True)
    target.write_text(fixture.read_text())

    r = run_pgolf(temp_project, "parse", str(target))
    assert r.returncode == 0
    output = json.loads(r.stdout)
    assert output["val_bpb"] == 1.08120543
    assert output["has_final_bpb"] is True
