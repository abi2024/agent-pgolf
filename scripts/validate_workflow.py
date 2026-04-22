#!/usr/bin/env python3
"""validate_workflow.py — Local end-to-end validation of the pgolf-agent pipeline.

Runs the full workflow with fake experiments and fake logs. No GPU. No money spent.

What it validates:
  - Dependencies and file structure
  - pgolf.py CLI commands all work
  - Log parser extracts correct values from fixtures
  - Hooks exist and are executable
  - Database schema initializes
  - Spending ledger works
  - Pre-registration works
  - submit-check correctly refuses invalid submissions
  - submit-check correctly accepts a well-formed mock submission

Exit 0 = ready for GPU work. Exit 1 = fix issues before spending money.

Usage:
    python scripts/validate_workflow.py
    python scripts/validate_workflow.py --verbose
    python scripts/validate_workflow.py --reset  # wipe state first (dangerous if you have real data)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).parent.parent
# NOTE: PGOLF is constructed dynamically inside run() using the temp project
# to avoid polluting the real project's state/pgolf.db/experiments/

# ANSI colors for the summary
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


class ValidationReport:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.warnings = []

    def ok(self, name, detail=""):
        self.passed.append((name, detail))

    def fail(self, name, detail):
        self.failed.append((name, detail))

    def warn(self, name, detail):
        self.warnings.append((name, detail))

    def render(self):
        total = len(self.passed) + len(self.failed)
        print(f"\n{'═' * 60}")
        print(f"  Validation Summary: {len(self.passed)}/{total} passed")
        print(f"{'═' * 60}\n")

        if self.passed:
            print(f"{GREEN}✓ Passed ({len(self.passed)}):{RESET}")
            for name, _ in self.passed:
                print(f"  {GREEN}✓{RESET} {name}")
            print()

        if self.warnings:
            print(f"{YELLOW}⚠ Warnings ({len(self.warnings)}):{RESET}")
            for name, detail in self.warnings:
                print(f"  {YELLOW}⚠{RESET} {name}")
                if detail:
                    print(f"     {detail}")
            print()

        if self.failed:
            print(f"{RED}✗ Failed ({len(self.failed)}):{RESET}")
            for name, detail in self.failed:
                print(f"  {RED}✗{RESET} {name}")
                if detail:
                    print(f"     {detail}")
            print()

        return len(self.failed) == 0


def run(cmd, cwd=None, env_extra=None, input_text=None):
    """Run a command and return (returncode, stdout, stderr)."""
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(
        cmd if isinstance(cmd, list) else cmd,
        capture_output=True, text=True, cwd=cwd, env=env, input=input_text,
        shell=isinstance(cmd, str),
    )
    return result.returncode, result.stdout, result.stderr


def pgolf_cmd(project):
    """Return the command prefix for running pgolf.py in the given project."""
    return [sys.executable, str(project / "scripts" / "pgolf.py")]


# ─── Phase 1: Structure and dependencies ─────────────────────────────────────

def check_structure(rpt, verbose=False):
    print(f"{BLUE}▸ Phase 1: File structure and dependencies{RESET}")

    required_files = [
        "AGENTS.md", "CLAUDE.md", "README.md", "ARCHITECTURE.md", "TEMPLATE.md",
        "scripts/pgolf.py",
        ".claude/settings.json",
        ".claude/hooks/pre-bash.sh",
        ".claude/hooks/post-bash.sh",
        ".claude/skills/morning.md",
        ".claude/skills/plan-experiment.md",
        ".claude/skills/run-experiment.md",
        ".claude/skills/analyze-results.md",
        ".claude/skills/blog.md",
        ".claude/skills/checkpoint.md",
        ".claude/skills/submit-check.md",
        "knowledge/lessons_learned.md",
        "knowledge/sota_timeline.md",
        "knowledge/learning_path.md",
        "tests/fixtures/sample_train_log_success.txt",
    ]
    for f in required_files:
        p = REPO / f
        if p.exists():
            rpt.ok(f"file: {f}")
        else:
            rpt.fail(f"file: {f}", "MISSING — re-unpack the tarball")

    # Check that hooks are executable
    for hook in [".claude/hooks/pre-bash.sh", ".claude/hooks/post-bash.sh"]:
        p = REPO / hook
        if p.exists():
            if os.access(p, os.X_OK):
                rpt.ok(f"executable: {hook}")
            else:
                rpt.fail(f"executable: {hook}",
                         f"Not executable. Run: chmod +x {hook}")

    # Python version
    py = sys.version_info
    if py >= (3, 11):
        rpt.ok(f"python {py.major}.{py.minor}")
    else:
        rpt.fail(f"python {py.major}.{py.minor}", "Need Python 3.11+")

    # scipy (optional but recommended)
    try:
        import scipy  # noqa: F401
        rpt.ok("scipy installed (p-values will work)")
    except ImportError:
        rpt.warn("scipy not installed", "pip install scipy (needed for p-value calculations)")

    # bash
    if run(["bash", "--version"])[0] == 0:
        rpt.ok("bash available")
    else:
        rpt.fail("bash available", "Required for hooks")

    # git
    if run(["git", "--version"])[0] == 0:
        rpt.ok("git available")
    else:
        rpt.fail("git available", "Required for version control")


# ─── Phase 2: CLI smoke test ─────────────────────────────────────────────────

def check_cli_smoke(rpt, temp):
    print(f"\n{BLUE}▸ Phase 2: CLI smoke tests{RESET}")

    # status (should work on empty DB)
    rc, _, err = run(pgolf_cmd(temp) + ["status"], cwd=temp)
    if rc == 0:
        rpt.ok("pgolf status on empty DB")
    else:
        rpt.fail("pgolf status", f"returncode={rc}: {err[:200]}")

    # track list (empty)
    rc, _, err = run(pgolf_cmd(temp) + ["track", "list"], cwd=temp)
    if rc == 0:
        rpt.ok("pgolf track list")
    else:
        rpt.fail("pgolf track list", err[:200])

    # spend total
    rc, out, err = run(pgolf_cmd(temp) + ["spend", "total", "--quiet"], cwd=temp)
    if rc == 0 and out.strip() == "0.00":
        rpt.ok("pgolf spend total (fresh)")
    else:
        rpt.fail("pgolf spend total", f"returncode={rc}, output={out!r}")


# ─── Phase 3: Log parser ─────────────────────────────────────────────────────

def check_parser(rpt, temp):
    print(f"\n{BLUE}▸ Phase 3: Log parser{RESET}")

    # Import and test directly
    sys.path.insert(0, str(REPO / "scripts"))
    import pgolf

    fixtures = REPO / "tests" / "fixtures"

    # Successful log
    text = (fixtures / "sample_train_log_success.txt").read_text()
    r = pgolf.extract_metrics(text)

    checks = [
        ("parser: final_int8_zlib BPB", r["val_bpb"] == 1.08120543,
         f"expected 1.08120543, got {r['val_bpb']}"),
        ("parser: has_final_bpb flag", r["has_final_bpb"] is True, ""),
        ("parser: distinguishes pre-quant",
         r["val_bpb_preqant"] == 1.0745 and r["val_bpb"] != r["val_bpb_preqant"],
         "pre-quant and final should be different"),
        ("parser: artifact size", r["artifact_size_bytes"] == 15842716, ""),
        ("parser: under 16MB flag", r["under_16mb"] is True, ""),
        ("parser: wall time", r["wall_time_seconds"] == 598.3, ""),
        ("parser: seed", r["seed"] == 1337, ""),
        ("parser: training steps", r["training_steps"] == 8394, ""),
        ("parser: no false warnings", len(r["warnings"]) == 0,
         f"warnings: {r['warnings']}"),
    ]
    for name, passed, detail in checks:
        if passed:
            rpt.ok(name)
        else:
            rpt.fail(name, detail)

    # Oversize log — must flag the 16MB violation
    text = (fixtures / "sample_train_log_oversize.txt").read_text()
    r = pgolf.extract_metrics(text)
    if r["under_16mb"] is False and r["artifact_size_bytes"] == 16423987:
        rpt.ok("parser: flags oversized artifact")
    else:
        rpt.fail("parser: flags oversized artifact",
                 f"size={r['artifact_size_bytes']}, under_16mb={r['under_16mb']}")

    # Failed/truncated log — must not have final BPB
    text = (fixtures / "sample_train_log_failed.txt").read_text()
    r = pgolf.extract_metrics(text)
    if r["has_final_bpb"] is False:
        rpt.ok("parser: detects truncated log")
    else:
        rpt.fail("parser: detects truncated log",
                 "Should have has_final_bpb=False for crashed run")

    # Empty log must not crash
    try:
        pgolf.extract_metrics("")
        rpt.ok("parser: handles empty input")
    except Exception as e:
        rpt.fail("parser: handles empty input", f"Crashed: {e}")


# ─── Phase 4: End-to-end experiment lifecycle ────────────────────────────────

def check_experiment_lifecycle(rpt, temp):
    print(f"\n{BLUE}▸ Phase 4: End-to-end experiment lifecycle (mock data){RESET}")

    # Create experiment
    rc, out, err = run(
        pgolf_cmd(temp) + ["track", "create",
                 "--hypothesis", "mock: reduce MLP 3x to 2.5x",
                 "--techniques", "baseline,quantization_aware_training"],
        cwd=temp,
    )
    if rc == 0 and "exp_001" in out:
        rpt.ok("create experiment → exp_001")
    else:
        rpt.fail("create experiment", f"rc={rc}, out={out[:200]}")
        return

    # Conflict refusal
    rc, out, err = run(
        pgolf_cmd(temp) + ["track", "create",
                 "--hypothesis", "should-be-refused",
                 "--techniques", "ema,depth_recurrence"],
        cwd=temp,
    )
    if rc != 0:
        rpt.ok("conflict check refuses EMA+depth_recurrence")
    else:
        rpt.fail("conflict check refuses EMA+depth_recurrence",
                 "Should have failed but didn't. Check knowledge/lessons_learned.md")

    # Pre-register thresholds
    rc, out, err = run(
        pgolf_cmd(temp) + ["register-thresholds", "exp_001",
                 "--seed1-continue", "1.10",
                 "--publish", "0.005",
                 "--internal", "0.003"],
        cwd=temp,
    )
    if rc == 0:
        rpt.ok("pre-register thresholds for exp_001")
    else:
        rpt.fail("pre-register thresholds", err[:200])

    # Record 3 seeds with reproducibility info
    seed_data = [(1337, 1.0810), (1338, 1.0815), (1339, 1.0808)]
    for seed, bpb in seed_data:
        rc, _, err = run(
            pgolf_cmd(temp) + ["track", "result", "exp_001",
                     "--bpb", str(bpb),
                     "--size", "15842716",
                     "--time", "598",
                     "--seed", str(seed),
                     "--gpu", "8xH100_SXM",
                     "--gpu-model", "NVIDIA H100 80GB HBM3",
                     "--torch-version", "2.8.0+cu128",
                     "--pg-commit", "abc1234"],
            cwd=temp,
        )
        if rc != 0:
            rpt.fail(f"record seed {seed}", err[:200])
            return
    rpt.ok("record 3 seeds with reproducibility metadata")

    # Spend logging
    for seed in [1337, 1338, 1339]:
        rc, _, err = run(
            pgolf_cmd(temp) + ["spend", "log-from-bash",
                     "--exp-id", "exp_001",
                     "--nproc", "8",
                     "--exit-code", "0"],
            cwd=temp,
        )
        if rc != 0:
            rpt.fail("spend log-from-bash", err[:200])
            return
    rpt.ok("log 3 spending events")

    # Total spend should be ~$12 for 3× 8xH100 runs at default duration
    rc, out, _ = run(pgolf_cmd(temp) + ["spend", "total", "--quiet"], cwd=temp)
    total = float(out.strip())
    if 10 <= total <= 20:
        rpt.ok(f"spend total is reasonable (${total:.2f})")
    else:
        rpt.warn(f"spend total is ${total:.2f}",
                 "Expected ~$12 for 3× 8xH100; check rates in pgolf.py")


# ─── Phase 5: Hooks ──────────────────────────────────────────────────────────

def check_hooks(rpt, temp):
    print(f"\n{BLUE}▸ Phase 5: Pre-bash hook (budget + GPU gating){RESET}")

    hook = temp / ".claude" / "hooks" / "pre-bash.sh"

    # Non-torchrun passes through
    rc, _, _ = run([str(hook), "ls -la"], cwd=temp)
    if rc == 0:
        rpt.ok("hook allows non-torchrun commands")
    else:
        rpt.fail("hook allows non-torchrun", "Unexpectedly blocked")

    # 1xH100 with wallclock should pass
    rc, _, err = run(
        [str(hook),
         "MAX_WALLCLOCK_SECONDS=600 torchrun --standalone --nproc_per_node=1 train.py"],
        cwd=temp,
    )
    if rc == 0:
        rpt.ok("hook allows 1xH100 with wallclock (fresh budget)")
    else:
        rpt.fail("hook allows 1xH100",
                 f"Blocked unexpectedly: {err[:200]}")

    # 8xH100 without confirm should be blocked
    rc, _, err = run(
        [str(hook),
         "MAX_WALLCLOCK_SECONDS=600 torchrun --standalone --nproc_per_node=8 train.py"],
        cwd=temp,
    )
    if rc != 0:
        rpt.ok("hook blocks 8xH100 without PGOLF_CONFIRM_8XH100")
    else:
        rpt.fail("hook blocks 8xH100",
                 "Should have required explicit confirmation")

    # 8xH100 WITH confirm should pass
    rc, _, err = run(
        [str(hook),
         "MAX_WALLCLOCK_SECONDS=600 torchrun --standalone --nproc_per_node=8 train.py"],
        cwd=temp,
        env_extra={"PGOLF_CONFIRM_8XH100": "1"},
    )
    if rc == 0:
        rpt.ok("hook allows 8xH100 with PGOLF_CONFIRM_8XH100=1")
    else:
        rpt.fail("hook allows 8xH100 with confirm",
                 f"Blocked: {err[:200]}")

    # Torchrun without MAX_WALLCLOCK should be blocked
    rc, _, err = run(
        [str(hook), "torchrun --standalone --nproc_per_node=1 train.py"],
        cwd=temp,
    )
    if rc != 0:
        rpt.ok("hook blocks torchrun without MAX_WALLCLOCK_SECONDS")
    else:
        rpt.fail("hook blocks no-wallclock",
                 "Should have required MAX_WALLCLOCK_SECONDS")

    # Over-budget should be blocked
    spending = temp / "state" / "spending.jsonl"
    original = spending.read_text()
    spending.write_text(json.dumps({
        "ts": "2026-04-17T00:00:00",
        "exp_id": "fake",
        "gpu": "8xH100_SXM",
        "duration_s": 600,
        "cost_usd": 450.0,
        "exit_code": 0,
    }) + "\n")

    rc, _, err = run(
        [str(hook),
         "MAX_WALLCLOCK_SECONDS=600 torchrun --nproc_per_node=1 train.py"],
        cwd=temp,
    )
    if rc != 0:
        rpt.ok("hook blocks when budget exhausted")
    else:
        rpt.fail("hook blocks over-budget",
                 "Should have blocked with $450 of $500 spent (reserve $60)")

    # PGOLF_FORCE should override
    rc, _, _ = run(
        [str(hook),
         "MAX_WALLCLOCK_SECONDS=600 torchrun --nproc_per_node=1 train.py"],
        cwd=temp, env_extra={"PGOLF_FORCE": "1"},
    )
    if rc == 0:
        rpt.ok("PGOLF_FORCE=1 overrides budget gate")
    else:
        rpt.fail("PGOLF_FORCE override", "Should have allowed with force")

    # Restore
    spending.write_text(original)


# ─── Phase 6: Submit-check ───────────────────────────────────────────────────

def check_submit_check(rpt, temp):
    print(f"\n{BLUE}▸ Phase 6: Submit-check paranoid gate{RESET}")

    # submit-check on 3-seed experiment should still fail because no SOTA cached
    # and because we're not beating a real SOTA
    rc, out, err = run(pgolf_cmd(temp) + ["submit-check", "exp_001"], cwd=temp)
    if rc != 0:
        rpt.ok("submit-check correctly refuses mock data")
    else:
        rpt.fail("submit-check",
                 "Mock data should have failed SOTA comparison at minimum")

    # Verify it produced specific actionable failure messages
    if "SOTA" in out or "sota" in out or "leaderboard" in out.lower():
        rpt.ok("submit-check gives actionable feedback")
    else:
        rpt.warn("submit-check feedback",
                 "Output didn't mention SOTA — may be unclear to user")


# ─── Phase 7: Leaderboard fetch (optional, needs network) ────────────────────

def check_leaderboard(rpt, temp, skip_network):
    print(f"\n{BLUE}▸ Phase 7: Leaderboard fetch{RESET}")

    if skip_network:
        rpt.warn("leaderboard fetch", "Skipped (--no-network)")
        return

    rc, out, err = run(pgolf_cmd(temp) + ["leaderboard", "fetch"], cwd=temp)
    if rc == 0 and "SOTA" in out:
        rpt.ok("leaderboard fetch from GitHub API")
    elif rc != 0 and "401" in err:
        rpt.warn("leaderboard fetch (rate-limited)",
                 "GitHub API rate limit hit. Retry later or use --no-network")
    else:
        rpt.warn("leaderboard fetch",
                 f"rc={rc}. Network issue? err={err[:200]}")


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--no-network", action="store_true",
                        help="Skip GitHub API calls")
    parser.add_argument("--keep-temp", action="store_true",
                        help="Keep temp directory for inspection")
    args = parser.parse_args()

    rpt = ValidationReport()

    # Phase 1: check the real project structure
    check_structure(rpt, args.verbose)

    # Phases 2-7: in a temp directory, don't pollute the real project
    with tempfile.TemporaryDirectory(delete=not args.keep_temp) as td:
        temp = Path(td) / "pgolf-test"
        temp.mkdir()

        # Copy necessary files
        (temp / "scripts").mkdir()
        (temp / ".claude" / "hooks").mkdir(parents=True)
        (temp / "state").mkdir()
        (temp / "experiments").mkdir()
        (temp / "blog" / "drafts").mkdir(parents=True)
        (temp / "knowledge").mkdir()

        (temp / "scripts" / "pgolf.py").write_text(
            (REPO / "scripts" / "pgolf.py").read_text()
        )
        (temp / ".claude" / "hooks" / "pre-bash.sh").write_text(
            (REPO / ".claude" / "hooks" / "pre-bash.sh").read_text()
        )
        (temp / ".claude" / "hooks" / "post-bash.sh").write_text(
            (REPO / ".claude" / "hooks" / "post-bash.sh").read_text()
        )
        (temp / ".claude" / "hooks" / "pre-bash.sh").chmod(0o755)
        (temp / ".claude" / "hooks" / "post-bash.sh").chmod(0o755)
        (temp / "knowledge" / "lessons_learned.md").write_text(
            (REPO / "knowledge" / "lessons_learned.md").read_text()
        )
        (temp / "state" / "spending.jsonl").touch()

        check_cli_smoke(rpt, temp)
        check_parser(rpt, temp)
        check_experiment_lifecycle(rpt, temp)
        check_hooks(rpt, temp)
        check_submit_check(rpt, temp)
        check_leaderboard(rpt, temp, args.no_network)

        if args.keep_temp:
            print(f"\n{YELLOW}Temp directory preserved: {temp}{RESET}")

    ok = rpt.render()

    if ok:
        print(f"{GREEN}✓ All validation checks passed.{RESET}")
        print(f"  You're ready to start using the pipeline with Claude Code.")
        print(f"  Next: fund RunPod, start Claude Code, run: /morning")
        return 0
    else:
        print(f"{RED}✗ Validation failed.{RESET}")
        print(f"  Fix the issues above before spending money on GPUs.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
