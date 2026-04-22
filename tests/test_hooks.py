"""Tests for the pre-bash and post-bash hooks."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent


@pytest.fixture
def temp_project(tmp_path):
    """Mini project with just the scripts/pgolf.py and hooks we need."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / ".claude" / "hooks").mkdir(parents=True)
    (tmp_path / "state").mkdir()
    (tmp_path / "experiments").mkdir()
    (tmp_path / "knowledge").mkdir()

    (tmp_path / "scripts" / "pgolf.py").write_text(
        (REPO / "scripts" / "pgolf.py").read_text()
    )
    for hook in ["pre-bash.sh", "post-bash.sh"]:
        src = REPO / ".claude" / "hooks" / hook
        dst = tmp_path / ".claude" / "hooks" / hook
        dst.write_text(src.read_text())
        dst.chmod(0o755)

    (tmp_path / "knowledge" / "lessons_learned.md").write_text("")
    (tmp_path / "state" / "spending.jsonl").touch()

    return tmp_path


def run_pre_bash(project, command, env_extra=None):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    payload = json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": command},
    })
    return subprocess.run(
        [str(project / ".claude" / "hooks" / "pre-bash.sh")],
        input=payload,
        capture_output=True, text=True, cwd=project, env=env,
    )


def test_pre_bash_allows_non_torchrun_commands(temp_project):
    """Hook should not gate arbitrary bash commands."""
    r = run_pre_bash(temp_project, "ls -la")
    assert r.returncode == 0


def test_pre_bash_allows_torchrun_when_budget_available(temp_project):
    """1xH100 run should pass when no spend has occurred."""
    r = run_pre_bash(
        temp_project,
        "MAX_WALLCLOCK_SECONDS=600 torchrun --standalone --nproc_per_node=1 train.py"
    )
    assert r.returncode == 0, f"Expected allow, got: {r.stderr}"


def test_pre_bash_blocks_8xh100_without_confirmation(temp_project):
    """8xH100 without PGOLF_CONFIRM_8XH100 should be blocked."""
    r = run_pre_bash(
        temp_project,
        "MAX_WALLCLOCK_SECONDS=600 torchrun --standalone --nproc_per_node=8 train.py"
    )
    assert r.returncode != 0
    assert "8xH100" in r.stderr or "confirm" in r.stderr.lower()


def test_pre_bash_allows_8xh100_with_confirmation(temp_project):
    """With PGOLF_CONFIRM_8XH100=1, 8xH100 should be allowed."""
    r = run_pre_bash(
        temp_project,
        "MAX_WALLCLOCK_SECONDS=600 torchrun --standalone --nproc_per_node=8 train.py",
        env_extra={"PGOLF_CONFIRM_8XH100": "1"},
    )
    assert r.returncode == 0, f"Expected allow with confirm, got: {r.stderr}"


def test_pre_bash_blocks_without_wallclock(temp_project):
    """Torchrun without MAX_WALLCLOCK_SECONDS should be blocked."""
    r = run_pre_bash(
        temp_project,
        "torchrun --standalone --nproc_per_node=1 train.py"
    )
    assert r.returncode != 0
    assert "WALLCLOCK" in r.stderr or "wallclock" in r.stderr.lower()


def test_pre_bash_blocks_over_budget(temp_project):
    """When near budget limit, torchrun should be blocked."""
    # Fake 99% spend: write enough entries to exceed remaining after reserve
    spending = temp_project / "state" / "spending.jsonl"
    with open(spending, "w") as f:
        # Put $450 spent; budget is 500, reserve is 60, so remaining spendable = -$10
        f.write(json.dumps({
            "ts": "2026-04-17T12:00:00",
            "exp_id": "exp_001",
            "gpu": "8xH100_SXM",
            "duration_s": 600,
            "cost_usd": 450.0,
            "exit_code": 0,
        }) + "\n")

    r = run_pre_bash(
        temp_project,
        "MAX_WALLCLOCK_SECONDS=600 torchrun --standalone --nproc_per_node=1 train.py"
    )
    assert r.returncode != 0
    assert "BLOCKED" in r.stderr or "budget" in r.stderr.lower()


def test_pre_bash_allows_over_budget_with_force(temp_project):
    """PGOLF_FORCE=1 should allow over-budget runs."""
    spending = temp_project / "state" / "spending.jsonl"
    with open(spending, "w") as f:
        f.write(json.dumps({
            "ts": "2026-04-17T12:00:00",
            "exp_id": "exp_001",
            "gpu": "8xH100_SXM",
            "duration_s": 600,
            "cost_usd": 450.0,
            "exit_code": 0,
        }) + "\n")

    r = run_pre_bash(
        temp_project,
        "MAX_WALLCLOCK_SECONDS=600 torchrun --standalone --nproc_per_node=1 train.py",
        env_extra={"PGOLF_FORCE": "1"},
    )
    assert r.returncode == 0


def test_pre_bash_custom_budget_via_env(temp_project):
    """PGOLF_BUDGET env var should change the effective budget."""
    spending = temp_project / "state" / "spending.jsonl"
    with open(spending, "w") as f:
        f.write(json.dumps({
            "ts": "2026-04-17T12:00:00",
            "exp_id": "exp_001",
            "gpu": "1xH100_SXM",
            "duration_s": 600,
            "cost_usd": 50.0,  # $50 spent
            "exit_code": 0,
        }) + "\n")

    # With budget=$100 reserve=$10, spendable=$40, 1xH100=$0.55 → allowed
    r = run_pre_bash(
        temp_project,
        "MAX_WALLCLOCK_SECONDS=600 torchrun --nproc_per_node=1 train.py",
        env_extra={"PGOLF_BUDGET": "100", "PGOLF_RESERVE": "10"},
    )
    assert r.returncode == 0

    # With budget=$55 reserve=$10, spendable=-$5 → blocked
    r = run_pre_bash(
        temp_project,
        "MAX_WALLCLOCK_SECONDS=600 torchrun --nproc_per_node=1 train.py",
        env_extra={"PGOLF_BUDGET": "55", "PGOLF_RESERVE": "10"},
    )
    assert r.returncode != 0
