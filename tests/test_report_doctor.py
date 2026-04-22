"""Tests for the new report and doctor commands."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent


@pytest.fixture
def temp_project(tmp_path):
    """Full temp project with scripts, hooks, commands, knowledge."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / ".claude" / "hooks").mkdir(parents=True)
    (tmp_path / ".claude" / "commands").mkdir(parents=True)
    (tmp_path / "knowledge" / "techniques").mkdir(parents=True)
    (tmp_path / "experiments").mkdir()
    (tmp_path / "blog" / "drafts").mkdir(parents=True)
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "spending.jsonl").touch()

    (tmp_path / "scripts" / "pgolf.py").write_text(
        (REPO / "scripts" / "pgolf.py").read_text()
    )
    for hook in ["pre-bash.sh", "post-bash.sh"]:
        src = REPO / ".claude" / "hooks" / hook
        dst = tmp_path / ".claude" / "hooks" / hook
        dst.write_text(src.read_text())
        dst.chmod(0o755)

    # Copy the eight commands
    for skill in ["morning", "plan-experiment", "run-experiment", "analyze-results",
                  "blog", "checkpoint", "submit-check", "synthesize"]:
        src = REPO / ".claude" / "commands" / f"{skill}.md"
        if src.exists():
            (tmp_path / ".claude" / "commands" / f"{skill}.md").write_text(src.read_text())

    # Copy required knowledge files
    for kb in ["lessons_learned.md", "sota_timeline.md", "learning_path.md"]:
        src = REPO / "knowledge" / kb
        if src.exists():
            (tmp_path / "knowledge" / kb).write_text(src.read_text())

    return tmp_path


def run_pgolf(project, *args, env_extra=None):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(project / "scripts" / "pgolf.py"), *args],
        capture_output=True, text=True, cwd=project, env=env,
    )


def _create_experiments(project):
    """Create two linked experiments with seeds for testing."""
    run_pgolf(project, "track", "create",
              "--hypothesis", "baseline test", "--techniques", "baseline")
    run_pgolf(project, "track", "create",
              "--hypothesis", "child experiment", "--techniques", "baseline",
              "--parent", "exp_001")
    for seed, bpb in [(1337, 1.120), (1338, 1.119)]:
        run_pgolf(project, "track", "result", "exp_001",
                  "--bpb", str(bpb), "--size", "15800000", "--time", "598",
                  "--seed", str(seed), "--gpu", "8xH100_SXM")
    run_pgolf(project, "track", "result", "exp_002",
              "--bpb", "1.090", "--size", "15800000", "--time", "595",
              "--seed", "1337", "--gpu", "8xH100_SXM")


def test_report_creates_file(temp_project):
    _create_experiments(temp_project)
    r = run_pgolf(temp_project, "report")
    assert r.returncode == 0
    report = temp_project / "REPORT.md"
    assert report.exists()
    content = report.read_text()
    assert "# Parameter Golf" in content
    assert "exp_001" in content
    assert "exp_002" in content


def test_report_includes_lineage(temp_project):
    _create_experiments(temp_project)
    run_pgolf(temp_project, "report")
    content = (temp_project / "REPORT.md").read_text()
    # Parent-child relationship should be visible in the tree
    assert "Experiment lineage" in content
    assert "exp_001" in content
    assert "exp_002" in content


def test_report_includes_top5(temp_project):
    _create_experiments(temp_project)
    run_pgolf(temp_project, "report")
    content = (temp_project / "REPORT.md").read_text()
    assert "Top 5 results" in content
    # exp_002 has the lower (better) BPB — should be rank 1
    idx_002 = content.find("exp_002")
    idx_001 = content.find("exp_001", content.find("Top 5 results"))
    assert 0 < idx_002 < idx_001, "exp_002 should be ranked above exp_001 (lower BPB)"


def test_report_on_empty_project(temp_project):
    """Report should work even with no experiments."""
    r = run_pgolf(temp_project, "report")
    assert r.returncode == 0
    content = (temp_project / "REPORT.md").read_text()
    assert "no experiments yet" in content.lower() or "0/0" in content


def test_doctor_healthy_on_fresh_project(temp_project):
    """Doctor should fail only on 'no leaderboard cache' for a fresh project."""
    r = run_pgolf(temp_project, "doctor")
    # Expect failure because no leaderboard has been fetched
    assert r.returncode != 0
    assert "leaderboard" in r.stdout.lower()


def test_doctor_all_green_with_leaderboard(temp_project):
    """Seed a fake fresh leaderboard and doctor should pass."""
    from datetime import datetime
    (temp_project / "state" / "leaderboard.json").write_text(json.dumps({
        "fetched_at": datetime.now().isoformat(),
        "current_sota_bpb": 1.0639,
        "current_sota_pr": 1577,
        "current_sota_title": "test SOTA",
        "top_10_merged": [],
        "recent_all": [],
    }))
    r = run_pgolf(temp_project, "doctor")
    assert r.returncode == 0, f"doctor should pass: {r.stdout}"
    assert "All" in r.stdout and "checks passed" in r.stdout


def test_doctor_detects_stale_leaderboard(temp_project):
    """Doctor should flag a leaderboard cache older than 24 hours."""
    (temp_project / "state" / "leaderboard.json").write_text(json.dumps({
        "fetched_at": "2024-01-01T00:00:00",
        "current_sota_bpb": 1.0,
    }))
    r = run_pgolf(temp_project, "doctor")
    assert r.returncode != 0
    assert "h old" in r.stdout or "stale" in r.stdout.lower() or "leaderboard" in r.stdout.lower()


def test_doctor_detects_missing_skill(temp_project):
    """Remove a skill and doctor should flag it."""
    (temp_project / ".claude" / "commands" / "synthesize.md").unlink()
    r = run_pgolf(temp_project, "doctor")
    assert r.returncode != 0
    assert "command" in r.stdout.lower() and "synthesize" in r.stdout.lower()


def test_status_shows_lineage_tree(temp_project):
    _create_experiments(temp_project)
    r = run_pgolf(temp_project, "status")
    assert r.returncode == 0
    assert "exp_001" in r.stdout
    assert "exp_002" in r.stdout
    assert "Experiment lineage" in r.stdout
