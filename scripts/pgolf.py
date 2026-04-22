#!/usr/bin/env python3
"""pgolf — CLI toolkit for Parameter Golf experiments.

Called by Claude Code via bash. NOT an agent — just structured tools.

Usage:
    # Experiment tracking
    python scripts/pgolf.py track create --hypothesis "..." --techniques "a,b,c"
    python scripts/pgolf.py track result exp_001 --bpb 1.12 --size 15000000 --seed 1337
    python scripts/pgolf.py track fail exp_001 --reason "OOM"
    python scripts/pgolf.py track list

    # Parsing
    python scripts/pgolf.py parse path/to/train.log
    python scripts/pgolf.py parse --compare exp_001 exp_002

    # Spending (new)
    python scripts/pgolf.py spend log-from-bash --exp-id exp_001 --nproc 1 --log-path x --exit-code 0
    python scripts/pgolf.py spend total [--quiet]
    python scripts/pgolf.py spend status

    # Leaderboard (new)
    python scripts/pgolf.py leaderboard fetch
    python scripts/pgolf.py leaderboard current

    # Pre-registration (new)
    python scripts/pgolf.py register-thresholds exp_001 --seed1-continue 1.10 --publish 0.005 --internal 0.003

    # Submission gate (new)
    python scripts/pgolf.py submit-check exp_001

    # Blog & status
    python scripts/pgolf.py blog --day 3 --experiment exp_001
    python scripts/pgolf.py status
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# ─── Paths ───────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "pgolf.db"
EXPERIMENTS_DIR = PROJECT_ROOT / "experiments"
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
BLOG_DIR = PROJECT_ROOT / "blog"
STATE_DIR = PROJECT_ROOT / "state"
SPENDING_LOG = STATE_DIR / "spending.jsonl"
LEADERBOARD_STATE = STATE_DIR / "leaderboard.json"

# Budget defaults (override with PGOLF_BUDGET env var)
DEFAULT_BUDGET = float(os.environ.get("PGOLF_BUDGET", "500"))
DEFAULT_RESERVE = float(os.environ.get("PGOLF_RESERVE", "60"))

# GPU rates ($/hour). Edit these when RunPod rates change.
# Source: RunPod public pricing; verify before funding pod.
GPU_HOURLY_RATES = {
    "1xA100_80GB": 1.64,
    "1xH100_PCIe": 2.49,
    "1xH100_SXM":  3.30,
    "8xH100_SXM": 24.72,
}


# ─── Database ────────────────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS experiments (
            id TEXT PRIMARY KEY,
            created_at TEXT DEFAULT (datetime('now')),
            hypothesis TEXT NOT NULL,
            technique_stack TEXT NOT NULL,
            status TEXT DEFAULT 'planned',
            val_bpb REAL,
            val_loss REAL,
            artifact_size_bytes INTEGER,
            code_size_bytes INTEGER,
            model_size_bytes INTEGER,
            training_seconds REAL,
            training_steps INTEGER,
            gpu_type TEXT,
            gpu_count INTEGER,
            gpu_model TEXT,
            torch_version TEXT,
            pg_commit TEXT,
            cost_usd REAL DEFAULT 0,
            parent_id TEXT,
            notes TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS technique_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT DEFAULT (datetime('now')),
            technique TEXT NOT NULL,
            experiment_id TEXT NOT NULL,
            delta_bpb REAL,
            worked INTEGER,
            notes TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS seeds (
            experiment_id TEXT NOT NULL,
            seed INTEGER NOT NULL,
            val_bpb REAL NOT NULL,
            val_loss REAL,
            gpu_type TEXT,
            wall_time_seconds REAL,
            artifact_size_bytes INTEGER,
            PRIMARY KEY (experiment_id, seed)
        );
        CREATE TABLE IF NOT EXISTS id_sequence (
            key TEXT PRIMARY KEY,
            next_id INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS pre_registration (
            experiment_id TEXT PRIMARY KEY,
            seed1_continue_threshold REAL,
            publish_delta REAL DEFAULT 0.005,
            internal_delta REAL DEFAULT 0.003,
            parent_id TEXT,
            parent_best_bpb REAL,
            sota_bpb_at_registration REAL,
            decision_rule TEXT,
            registered_at TEXT DEFAULT (datetime('now'))
        );
    """)
    return conn


def next_experiment_id(db) -> str:
    """Generate the next experiment ID using a monotonic counter (not COUNT(*))."""
    row = db.execute("SELECT next_id FROM id_sequence WHERE key = 'experiment'").fetchone()
    if row is None:
        # First time. Initialize based on whatever IS in the experiments table.
        row = db.execute("SELECT COALESCE(MAX(CAST(SUBSTR(id, 5) AS INTEGER)), 0) AS max_id FROM experiments").fetchone()
        start = row["max_id"] + 1
        db.execute("INSERT INTO id_sequence (key, next_id) VALUES ('experiment', ?)", (start,))
        next_id = start
    else:
        next_id = row["next_id"]
    db.execute("UPDATE id_sequence SET next_id = next_id + 1 WHERE key = 'experiment'")
    return f"exp_{next_id:03d}"


# ─── Track commands ──────────────────────────────────────────────────────────

def track_create(args):
    db = get_db()
    exp_id = next_experiment_id(db)

    techniques = [t.strip() for t in args.techniques.split(",") if t.strip()]

    # Conflict check against lessons_learned.md
    conflicts = check_technique_conflicts(techniques)
    if conflicts and not args.force:
        print(f"⚠️  POTENTIAL CONFLICTS for {', '.join(techniques)}:")
        for c in conflicts:
            print(f"   - {c}")
        print("\nPass --force to proceed anyway, or choose different techniques.")
        db.close()
        sys.exit(1)

    db.execute(
        "INSERT INTO experiments (id, hypothesis, technique_stack, parent_id) VALUES (?, ?, ?, ?)",
        (exp_id, args.hypothesis, json.dumps(techniques), args.parent or None),
    )
    db.commit()

    exp_dir = EXPERIMENTS_DIR / exp_id
    exp_dir.mkdir(parents=True, exist_ok=True)
    (exp_dir / "config.json").write_text(json.dumps({
        "id": exp_id,
        "hypothesis": args.hypothesis,
        "technique_stack": techniques,
        "parent_id": args.parent,
        "created_at": datetime.now().isoformat(),
    }, indent=2))

    print(f"Created {exp_id}: {args.hypothesis[:60]}")
    print(f"  Directory: {exp_dir}")
    print(f"  Techniques: {', '.join(techniques)}")
    if conflicts:
        print(f"  ⚠️  Proceeding despite {len(conflicts)} conflict(s) — --force was set")
    db.close()


def check_technique_conflicts(techniques: list[str]) -> list[str]:
    """Grep lessons_learned.md for known technique conflicts.

    Normalizes spaces/underscores/hyphens so `depth_recurrence` matches
    "depth recurrence" in the doc.
    """
    lessons = KNOWLEDGE_DIR / "lessons_learned.md"
    if not lessons.exists():
        return []
    text = lessons.read_text().lower()
    conflicts = []

    def normalize(s: str) -> str:
        return re.sub(r"[\s_\-]+", "", s.lower())

    t_norm = [normalize(t) for t in techniques]

    # Parse "### X + Y = BAD" style headers
    for match in re.finditer(r"###\s+([^=\n]+?)\s*=\s*bad", text, re.IGNORECASE):
        header_norm = normalize(match.group(1))
        mentioned = [t for t in t_norm if t and t in header_norm]
        if len(mentioned) >= 2:
            conflicts.append(f"Known conflict in lessons_learned.md: {match.group(0).strip()}")
    return conflicts


def track_result(args):
    db = get_db()
    exp_id = args.experiment_id

    # Verify experiment exists first
    if not db.execute("SELECT 1 FROM experiments WHERE id = ?", (exp_id,)).fetchone():
        print(f"Error: experiment {exp_id} not found. Create it first with `track create`.", file=sys.stderr)
        db.close()
        sys.exit(1)

    updates = ["status = 'completed'"]
    params = []

    for field, value in [
        ("val_bpb", args.bpb),
        ("val_loss", args.loss),
        ("artifact_size_bytes", args.size),
        ("code_size_bytes", args.code_size),
        ("model_size_bytes", args.model_size),
        ("training_seconds", args.time),
        ("training_steps", args.steps),
        ("gpu_type", args.gpu),
        ("gpu_model", args.gpu_model),
        ("torch_version", args.torch_version),
        ("pg_commit", args.pg_commit),
        ("cost_usd", args.cost),
        ("notes", args.notes),
    ]:
        if value is not None:
            updates.append(f"{field} = ?")
            params.append(value)

    params.append(exp_id)
    db.execute(f"UPDATE experiments SET {', '.join(updates)} WHERE id = ?", params)

    # Record per-seed result if provided
    if args.seed is not None and args.bpb is not None:
        db.execute(
            """INSERT OR REPLACE INTO seeds
               (experiment_id, seed, val_bpb, val_loss, gpu_type, wall_time_seconds, artifact_size_bytes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (exp_id, args.seed, args.bpb, args.loss, args.gpu, args.time, args.size),
        )

    db.commit()
    print(f"Updated {exp_id}: BPB={args.bpb}, size={args.size}, seed={args.seed}, status=completed")
    db.close()


def track_fail(args):
    db = get_db()
    db.execute(
        "UPDATE experiments SET status = 'failed', notes = ? WHERE id = ?",
        (args.reason or "Unknown failure", args.experiment_id),
    )
    db.commit()
    print(f"Marked {args.experiment_id} as failed: {args.reason}")
    db.close()


def track_list(args):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM experiments ORDER BY created_at DESC LIMIT ?",
        (args.limit,),
    ).fetchall()

    best = db.execute(
        "SELECT MIN(val_bpb) as best FROM experiments WHERE status = 'completed'"
    ).fetchone()

    print(f"\n{'ID':<10} {'Status':<11} {'BPB':>8} {'Size MB':>8} {'Hypothesis'}")
    print("─" * 80)
    for r in rows:
        bpb = f"{r['val_bpb']:.4f}" if r['val_bpb'] else "   —"
        size = f"{r['artifact_size_bytes']/1e6:.2f}" if r['artifact_size_bytes'] else "  —"
        hyp = (r['hypothesis'] or '')[:40]
        print(f"{r['id']:<10} {r['status']:<11} {bpb:>8} {size:>8} {hyp}")

    if best and best['best']:
        print(f"\nBest BPB: {best['best']:.4f}")
    else:
        print("\nNo completed experiments yet.")
    print(f"Total experiments: {len(rows)}")
    db.close()


# ─── Parse commands ──────────────────────────────────────────────────────────

def parse_log(args):
    """Parse a training log file and print structured results."""
    log_path = Path(args.log_path)
    if not log_path.exists():
        print(f"Error: {log_path} not found", file=sys.stderr)
        sys.exit(1)

    text = log_path.read_text()
    results = extract_metrics(text)

    print(json.dumps(results, indent=2))

    results_path = log_path.parent / (log_path.stem + "_results.json")
    results_path.write_text(json.dumps(results, indent=2))
    print(f"\nSaved to {results_path}", file=sys.stderr)


def extract_metrics(text: str) -> dict:
    """Extract key metrics from a Parameter Golf training log.

    Uses the competition's canonical output patterns. The authoritative metric
    is `final_int8_zlib_roundtrip_exact val_bpb:` — this is the post-quantization,
    post-compression value that's actually scored.
    """
    results = {
        "val_bpb": None,
        "val_bpb_preqant": None,
        "val_loss": None,
        "artifact_size_bytes": None,
        "artifact_size_mb": None,
        "training_steps": None,
        "wall_time_seconds": None,
        "under_16mb": None,
        "has_final_bpb": False,
        "seed": None,
        "loss_curve": [],
        "warnings": [],
    }

    # 1. AUTHORITATIVE: final post-quant BPB
    m = re.search(r"final_int8_zlib_roundtrip_exact\s+val_bpb\s*:?\s*([0-9]+\.[0-9]+)", text)
    if m:
        results["val_bpb"] = float(m.group(1))
        results["has_final_bpb"] = True
    else:
        # Fallback: last "val_bpb:" in log, but flag as non-authoritative
        matches = re.findall(r"val_bpb\s*:?\s*([0-9]+\.[0-9]+)", text)
        if matches:
            results["val_bpb"] = float(matches[-1])
            results["warnings"].append("final_int8_zlib_roundtrip_exact not found; used last val_bpb")

    # 2. Pre-quant BPB for comparison (useful to see quantization cost)
    m = re.search(r"pre[-_\s]?quant.*?val_bpb\s*:?\s*([0-9]+\.[0-9]+)", text, re.IGNORECASE | re.DOTALL)
    if m:
        results["val_bpb_preqant"] = float(m.group(1))

    # 3. val_loss — last reported value (final eval)
    matches = re.findall(r"val_loss\s*:?\s*([0-9]+\.[0-9]+)", text)
    if matches:
        results["val_loss"] = float(matches[-1])

    # 4. Artifact size — look for explicit "compressed" or "artifact" byte counts
    for pattern in [
        r"artifact[_\s]+size[:\s=]+(\d[\d,_]*)\s*bytes?",
        r"compressed[_\s]+size[:\s=]+(\d[\d,_]*)\s*bytes?",
        r"total[_\s]+size[:\s=]+(\d[\d,_]*)\s*bytes?",
        r"(\d[\d,_]*)\s*bytes?\s*\(?(?:compressed|total|artifact)",
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            size = int(m.group(1).replace(",", "").replace("_", ""))
            results["artifact_size_bytes"] = size
            results["artifact_size_mb"] = round(size / 1_000_000, 3)
            results["under_16mb"] = size <= 16_000_000
            break

    # 5. Training steps — last "step N" mentioned
    step_matches = re.findall(r"step\s+(\d+)", text)
    if step_matches:
        results["training_steps"] = max(int(s) for s in step_matches)

    # 6. Wall time — explicit total-time patterns (NOT just "N s")
    for pattern in [
        r"total[_\s]+time[:\s=]+([0-9]+\.?[0-9]*)\s*s",
        r"wall[_\s]?clock[:\s=]+([0-9]+\.?[0-9]*)\s*s",
        r"training\s+(?:completed|finished).*?in\s+([0-9]+\.?[0-9]*)\s*s",
        r"elapsed[:\s=]+([0-9]+\.?[0-9]*)\s*s",
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            results["wall_time_seconds"] = float(m.group(1))
            break
    if results["wall_time_seconds"] is None:
        results["warnings"].append("wall_time_seconds not found in log")

    # 7. Seed
    m = re.search(r"SEED\s*[:=]\s*(\d+)", text)
    if m:
        results["seed"] = int(m.group(1))

    # 8. Loss curve (periodic step-loss pairs)
    for match in re.finditer(r"step\s+(\d+)[^\n]*?(?:train_)?loss\s*:?\s*([0-9]+\.[0-9]+)", text):
        results["loss_curve"].append({
            "step": int(match.group(1)),
            "loss": float(match.group(2)),
        })

    # 9. Sanity: artifact must be <= 16MB for a valid record submission
    if results["artifact_size_bytes"] is not None and results["artifact_size_bytes"] > 16_000_000:
        results["warnings"].append(f"ARTIFACT EXCEEDS 16MB: {results['artifact_size_mb']} MB")

    return results


def compare_experiments(args):
    """Compare two experiments for statistical significance using Welch's t-test."""
    db = get_db()

    seeds_a = db.execute(
        "SELECT val_bpb FROM seeds WHERE experiment_id = ? ORDER BY seed",
        (args.exp_a,),
    ).fetchall()
    seeds_b = db.execute(
        "SELECT val_bpb FROM seeds WHERE experiment_id = ? ORDER BY seed",
        (args.exp_b,),
    ).fetchall()

    if len(seeds_a) < 2 or len(seeds_b) < 2:
        print(f"Need ≥2 seeds per experiment for comparison.")
        print(f"  {args.exp_a}: {len(seeds_a)} seeds")
        print(f"  {args.exp_b}: {len(seeds_b)} seeds")
        db.close()
        sys.exit(1)

    bpb_a = [r["val_bpb"] for r in seeds_a]
    bpb_b = [r["val_bpb"] for r in seeds_b]

    import statistics
    mean_a = statistics.mean(bpb_a)
    mean_b = statistics.mean(bpb_b)
    std_a = statistics.stdev(bpb_a) if len(bpb_a) > 1 else 0.0
    std_b = statistics.stdev(bpb_b) if len(bpb_b) > 1 else 0.0
    delta = mean_a - mean_b

    try:
        from scipy import stats
        t_stat, p_value = stats.ttest_ind(bpb_a, bpb_b, equal_var=False)  # Welch's
        has_pvalue = True
    except ImportError:
        t_stat = p_value = None
        has_pvalue = False

    print(f"\n{'Metric':<20} {args.exp_a:<15} {args.exp_b:<15}")
    print("─" * 50)
    print(f"{'Mean BPB':<20} {mean_a:<15.4f} {mean_b:<15.4f}")
    print(f"{'Std BPB':<20} {std_a:<15.4f} {std_b:<15.4f}")
    print(f"{'Seeds':<20} {len(bpb_a):<15} {len(bpb_b):<15}")
    print(f"\nDelta (A-B): {delta:+.4f}  (negative means A is better)")

    if not has_pvalue:
        print("\n(Install scipy for p-value calculation: pip install scipy)")
        db.close()
        return

    print(f"t-statistic: {t_stat:.3f} (Welch's, unequal variance)")
    print(f"p-value:     {p_value:.4f}")

    # Decision using competition-style thresholds
    threshold = args.threshold
    if p_value < 0.01 and abs(delta) >= threshold:
        winner = args.exp_a if delta < 0 else args.exp_b
        print(f"\n✅ Statistically significant improvement (p<0.01, |Δ|≥{threshold})")
        print(f"   Winner: {winner}")
    elif p_value < 0.05 and abs(delta) >= threshold:
        print(f"\n⚠️  Marginally significant (p<0.05) — consider more seeds")
    else:
        print(f"\n❌ Not significant at the |Δ|≥{threshold}, p<0.01 bar")

    db.close()


# ─── Spending ────────────────────────────────────────────────────────────────

def spend_log_from_bash(args):
    """Called by post-bash.sh after a torchrun. Computes actual cost from log.

    Falls back gracefully if the log can't be parsed — better to log an estimated
    cost than nothing.
    """
    STATE_DIR.mkdir(exist_ok=True)
    duration_s = None

    if args.log_path:
        log_path = Path(args.log_path)
        if log_path.exists():
            text = log_path.read_text()
            m = extract_metrics(text)
            duration_s = m.get("wall_time_seconds")

    # Fall back to the competition cap if we can't find a real duration
    if duration_s is None:
        duration_s = 600.0  # MAX_WALLCLOCK_SECONDS default

    gpu_key = f"{args.nproc}xH100_SXM"
    rate_per_hour = GPU_HOURLY_RATES.get(gpu_key, GPU_HOURLY_RATES["1xH100_SXM"])
    cost = duration_s * (rate_per_hour / 3600.0)

    entry = {
        "ts": datetime.now().isoformat(),
        "exp_id": args.exp_id or "unknown",
        "gpu": gpu_key,
        "duration_s": round(duration_s, 1),
        "cost_usd": round(cost, 3),
        "exit_code": args.exit_code,
        "log_path": str(args.log_path) if args.log_path else None,
    }

    with open(SPENDING_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")

    # Also update the experiment's cost column if we know the exp_id
    if args.exp_id and args.exp_id != "unknown":
        db = get_db()
        db.execute(
            "UPDATE experiments SET cost_usd = COALESCE(cost_usd, 0) + ? WHERE id = ?",
            (round(cost, 3), args.exp_id),
        )
        db.commit()
        db.close()

    print(f"[spend] {args.exp_id}: ${cost:.3f} ({args.nproc}xH100, {duration_s:.0f}s, exit={args.exit_code})")


def spend_total(args):
    """Print total spend. With --quiet, just the number (for shell use)."""
    if not SPENDING_LOG.exists():
        total = 0.0
    else:
        total = 0.0
        for line in SPENDING_LOG.read_text().splitlines():
            if line.strip():
                try:
                    total += json.loads(line)["cost_usd"]
                except (json.JSONDecodeError, KeyError):
                    continue
    if args.quiet:
        print(f"{total:.2f}")
    else:
        remaining = DEFAULT_BUDGET - total
        print(f"Total spent: ${total:.2f} of ${DEFAULT_BUDGET:.0f} budget (${remaining:.2f} remaining, ${DEFAULT_RESERVE:.0f} reserved)")


def spend_status(args):
    """Full spend breakdown: by day, by GPU type, implied runway."""
    if not SPENDING_LOG.exists():
        print("No spending events logged yet.")
        return

    entries = []
    for line in SPENDING_LOG.read_text().splitlines():
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if not entries:
        print("No valid spending entries.")
        return

    total = sum(e["cost_usd"] for e in entries)

    # By GPU
    by_gpu = {}
    for e in entries:
        gpu = e.get("gpu", "unknown")
        by_gpu.setdefault(gpu, {"count": 0, "cost": 0.0})
        by_gpu[gpu]["count"] += 1
        by_gpu[gpu]["cost"] += e["cost_usd"]

    # By day
    by_day = {}
    for e in entries:
        try:
            day = e["ts"][:10]
        except (KeyError, TypeError):
            continue
        by_day.setdefault(day, 0.0)
        by_day[day] += e["cost_usd"]

    remaining = DEFAULT_BUDGET - total
    spendable = max(0.0, remaining - DEFAULT_RESERVE)

    print(f"\n╔══════════════════════════════════════════╗")
    print(f"║           💰 Spending Status             ║")
    print(f"╠══════════════════════════════════════════╣")
    print(f"║  Total spent:    ${total:>7.2f} / ${DEFAULT_BUDGET:>5.0f}      ║")
    print(f"║  Remaining:      ${remaining:>7.2f}               ║")
    print(f"║  Reserve:        ${DEFAULT_RESERVE:>7.2f}               ║")
    print(f"║  Spendable now:  ${spendable:>7.2f}               ║")
    print(f"╚══════════════════════════════════════════╝")

    print("\nBy GPU type:")
    for gpu, v in sorted(by_gpu.items()):
        print(f"  {gpu:<20} {v['count']:>3} runs  ${v['cost']:>6.2f}")

    print("\nBy day (last 7):")
    for day in sorted(by_day.keys())[-7:]:
        print(f"  {day}  ${by_day[day]:>6.2f}")

    if len(by_day) >= 2:
        avg_daily = total / len(by_day)
        if avg_daily > 0:
            days_of_runway = spendable / avg_daily
            print(f"\n  Avg daily spend: ${avg_daily:.2f}")
            print(f"  Runway at current pace: {days_of_runway:.1f} days of spendable budget")


# ─── Leaderboard ─────────────────────────────────────────────────────────────

def leaderboard_fetch(args):
    """Pull recent PRs, extract BPBs, update state/leaderboard.json."""
    url = "https://api.github.com/repos/openai/parameter-golf/pulls?state=all&sort=created&direction=desc&per_page=50"

    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "pgolf-agent/1.0",
    })

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            prs = json.loads(resp.read())
    except urllib.error.URLError as e:
        print(f"Failed to fetch leaderboard: {e}", file=sys.stderr)
        sys.exit(1)

    # Extract BPB. Competition titles look like:
    #   "Record: <desc> — val_bpb 1.0639 (3-seed mean)"
    #   "Record: <desc> - 1.0810 BPB"
    extracted = []
    for pr in prs:
        title = pr.get("title", "")
        bpb = None
        m = re.search(r"val_bpb\s+([0-9]+\.[0-9]{3,})", title)
        if m:
            bpb = float(m.group(1))
        else:
            m = re.search(r"([0-9]+\.[0-9]{3,})\s*BPB", title, re.IGNORECASE)
            if m:
                bpb = float(m.group(1))

        if bpb and 0.9 < bpb < 1.5:
            extracted.append({
                "pr": pr["number"],
                "bpb": bpb,
                "title": title[:120],
                "author": pr["user"]["login"],
                "state": pr["state"],
                "merged": pr.get("merged_at") is not None,
                "created_at": pr["created_at"][:10],
                "url": pr["html_url"],
            })

    merged = [e for e in extracted if e["merged"]]
    best = min(merged, key=lambda x: x["bpb"]) if merged else None

    STATE_DIR.mkdir(exist_ok=True)
    state = {
        "fetched_at": datetime.now().isoformat(),
        "current_sota_bpb": best["bpb"] if best else None,
        "current_sota_pr": best["pr"] if best else None,
        "current_sota_title": best["title"] if best else None,
        "top_10_merged": sorted(merged, key=lambda x: x["bpb"])[:10],
        "recent_all": sorted(extracted, key=lambda x: x["created_at"], reverse=True)[:20],
    }
    LEADERBOARD_STATE.write_text(json.dumps(state, indent=2))

    print(f"Fetched {len(extracted)} scored PRs ({len(merged)} merged)")
    if best:
        print(f"Current SOTA: {best['bpb']:.4f} (PR #{best['pr']} by {best['author']})")
        print(f"  Title: {best['title'][:80]}")
    else:
        print("No merged scored PRs found.")


def leaderboard_current(args):
    """Print the cached current SOTA."""
    if not LEADERBOARD_STATE.exists():
        print("No leaderboard state cached. Run `pgolf leaderboard fetch` first.")
        sys.exit(1)
    state = json.loads(LEADERBOARD_STATE.read_text())
    print(f"Current SOTA: {state.get('current_sota_bpb')} BPB")
    print(f"  PR: #{state.get('current_sota_pr')}")
    print(f"  Title: {state.get('current_sota_title')}")
    print(f"  Fetched: {state.get('fetched_at')}")

    print("\nTop 10:")
    for entry in state.get("top_10_merged", [])[:10]:
        print(f"  {entry['bpb']:.4f}  PR #{entry['pr']:<5} {entry['title'][:60]}")


def get_current_sota() -> Optional[float]:
    """Helper: returns the current SOTA BPB from cached leaderboard state, or None."""
    if not LEADERBOARD_STATE.exists():
        return None
    try:
        return json.loads(LEADERBOARD_STATE.read_text()).get("current_sota_bpb")
    except (json.JSONDecodeError, OSError):
        return None


# ─── Pre-registration ────────────────────────────────────────────────────────

def register_thresholds(args):
    """Register decision thresholds BEFORE running any seeds. Prevents optional stopping."""
    db = get_db()

    # Verify experiment exists
    if not db.execute("SELECT 1 FROM experiments WHERE id = ?", (args.experiment_id,)).fetchone():
        print(f"Error: experiment {args.experiment_id} not found", file=sys.stderr)
        db.close()
        sys.exit(1)

    # Look up parent's best BPB if available
    parent_bpb = None
    exp = db.execute("SELECT parent_id FROM experiments WHERE id = ?", (args.experiment_id,)).fetchone()
    parent_id = exp["parent_id"] if exp else None
    if parent_id:
        best = db.execute(
            "SELECT MIN(val_bpb) as b FROM seeds WHERE experiment_id = ?",
            (parent_id,)
        ).fetchone()
        if best:
            parent_bpb = best["b"]

    sota = get_current_sota()

    rule = (
        f"GREEN (publishable): 3-seed mean ≤ {sota - args.publish if sota else 'SOTA - publish_delta'} "
        f"at p<0.01 (vs SOTA {sota}, delta={args.publish}); "
        f"YELLOW (internal stack): 3-seed mean ≤ parent - {args.internal} at p<0.01; "
        f"RED: otherwise. "
        f"Seed-1 screen: abandon if seed-1 val_bpb > {args.seed1_continue}."
    )

    db.execute(
        """INSERT OR REPLACE INTO pre_registration
           (experiment_id, seed1_continue_threshold, publish_delta, internal_delta,
            parent_id, parent_best_bpb, sota_bpb_at_registration, decision_rule)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (args.experiment_id, args.seed1_continue, args.publish, args.internal,
         parent_id, parent_bpb, sota, rule),
    )
    db.commit()

    print(f"Registered thresholds for {args.experiment_id}:")
    print(f"  Seed-1 continue: ≤ {args.seed1_continue}")
    print(f"  Publish delta:   {args.publish} (vs SOTA {sota})")
    print(f"  Internal delta:  {args.internal} (vs parent {parent_bpb})")
    print(f"  Rule: {rule}")
    db.close()


# ─── Submit check ────────────────────────────────────────────────────────────

def submit_check(args):
    """Run ALL pre-submission gates. Exit 0 if all pass, 1 if any fail."""
    exp_id = args.experiment_id
    failures = []
    warnings = []

    db = get_db()
    exp = db.execute("SELECT * FROM experiments WHERE id = ?", (exp_id,)).fetchone()
    if not exp:
        print(f"Error: experiment {exp_id} not found", file=sys.stderr)
        sys.exit(1)
    exp = dict(exp)

    seeds = db.execute("SELECT * FROM seeds WHERE experiment_id = ? ORDER BY seed", (exp_id,)).fetchall()
    seeds = [dict(s) for s in seeds]

    # --- Check 1: Seeds ---
    if len(seeds) < 3:
        failures.append(f"seeds: have {len(seeds)}, need ≥3 for competition submission")

    # --- Check 2: Artifact size ---
    for s in seeds:
        size = s.get("artifact_size_bytes")
        if size is None:
            warnings.append(f"seed {s['seed']}: artifact_size_bytes not recorded")
        elif size > 16_000_000:
            failures.append(f"size: seed {s['seed']} is {size:,} bytes (> 16MB = 16,000,000)")

    # --- Check 3: Wall time ---
    for s in seeds:
        wt = s.get("wall_time_seconds")
        if wt is None:
            warnings.append(f"seed {s['seed']}: wall_time_seconds not recorded")
        elif wt > 600:
            failures.append(f"wall_time: seed {s['seed']} took {wt}s (> 600s limit)")

    # --- Check 4: GPU type must be 8xH100_SXM ---
    for s in seeds:
        gpu = (s.get("gpu_type") or "").replace(" ", "").lower()
        if "8xh100" not in gpu or "sxm" not in gpu:
            failures.append(
                f"gpu_type: seed {s['seed']} was '{s.get('gpu_type')}', "
                f"competition requires 8xH100_SXM"
            )

    # --- Check 5: Statistical significance vs SOTA ---
    sota = get_current_sota()
    if sota is None:
        warnings.append("No cached SOTA — run `pgolf leaderboard fetch` first")
    elif len(seeds) >= 2:
        bpbs = [s["val_bpb"] for s in seeds]
        import statistics
        mean_bpb = statistics.mean(bpbs)
        std_bpb = statistics.stdev(bpbs) if len(bpbs) > 1 else 0

        delta_from_sota = mean_bpb - sota
        if delta_from_sota > -0.005:
            failures.append(
                f"bpb: 3-seed mean {mean_bpb:.4f} does not beat SOTA {sota:.4f} by ≥0.005 "
                f"(delta = {delta_from_sota:+.4f})"
            )

        # Check variance
        if std_bpb > 0.003:
            warnings.append(
                f"std across seeds is {std_bpb:.4f} (> 0.003) — consider re-running the outlier"
            )

    # --- Check 6: Reproducibility metadata ---
    for field in ["torch_version", "pg_commit", "gpu_model"]:
        if not exp.get(field):
            failures.append(f"reproducibility: experiment.{field} not recorded")

    # --- Check 7: Log integrity — final BPB line present in each log ---
    exp_dir = EXPERIMENTS_DIR / exp_id
    for s in seeds:
        seed = s["seed"]
        candidates = list(exp_dir.glob(f"train*seed*{seed}*.log")) + list(exp_dir.glob(f"*seed{seed}*.log"))
        if not candidates:
            candidates = list(exp_dir.glob("train*.log"))  # Fallback
        if not candidates:
            warnings.append(f"seed {seed}: no train log file found in {exp_dir}")
            continue
        log = candidates[0]
        text = log.read_text()
        if "final_int8_zlib_roundtrip_exact" not in text:
            failures.append(
                f"seed {seed}: log {log.name} missing `final_int8_zlib_roundtrip_exact` line "
                f"— run may have been truncated"
            )

    # --- Check 8: Static analysis for cheating signals ---
    for s in seeds:
        train_script = exp_dir / "train_gpt.py"
        if train_script.exists():
            text = train_script.read_text()
            suspicious = []
            if re.search(r"fineweb_val", text, re.IGNORECASE):
                suspicious.append("references fineweb_val (validation data) in training script")
            if re.search(r"urllib|requests\.|httpx|urlopen", text):
                suspicious.append("appears to make network calls")
            if suspicious:
                warnings.extend([f"cheating-check: {s}" for s in suspicious])
            break  # Only check once, not per-seed

    # --- Report ---
    print(f"\n═══ Submit check for {exp_id} ═══\n")

    if warnings:
        print(f"⚠️  {len(warnings)} warning(s):")
        for w in warnings:
            print(f"   - {w}")
        print()

    if failures:
        print(f"❌ {len(failures)} check(s) FAILED:")
        for f in failures:
            print(f"   - {f}")
        print(f"\nDo NOT submit until all failures are resolved.")
        db.close()
        sys.exit(1)

    # All good. Print PR-ready summary.
    print(f"✅ All pre-submission checks passed for {exp_id}.\n")
    print("═══ PR-ready summary ═══\n")
    print(f"**Title:** Record: {exp['hypothesis'][:60]} — val_bpb {mean_bpb:.4f} (3-seed mean)\n")
    print(f"**Results:**")
    print(f"| Seed | val_bpb | wall_time | artifact_size |")
    print(f"|------|---------|-----------|---------------|")
    for s in seeds:
        size_mb = s['artifact_size_bytes'] / 1_000_000 if s['artifact_size_bytes'] else 0
        print(f"| {s['seed']} | {s['val_bpb']:.4f} | {s.get('wall_time_seconds', '?')}s | {size_mb:.2f} MB |")
    print(f"| **mean** | **{mean_bpb:.4f}** | — | — |")
    print(f"| **std**  | **{std_bpb:.4f}** | — | — |")
    print(f"\n**SOTA comparison:** {mean_bpb:.4f} vs {sota:.4f} = {mean_bpb - sota:+.4f}")
    print(f"**Hardware:** {exp.get('gpu_model')}, torch={exp.get('torch_version')}")
    print(f"**Parameter-golf commit:** {exp.get('pg_commit')}")
    print(f"**Hypothesis:** {exp['hypothesis']}")

    db.close()


# ─── Blog command (stub — real writing happens in /blog skill) ───────────────

BLOG_TEMPLATE = """# Day {day}: {title}

*{date} · Parameter Golf series*

> **Note to Claude:** This is a scaffold. The `/blog` skill should REPLACE
> this template with a real 800-1200 word post drawing from:
>   - experiments/{exp_id}/config.json (hypothesis)
>   - experiments/{exp_id}/analysis.md (what happened)
>   - experiments/{exp_id}/train*.log (data to cite)
>   - knowledge/techniques/*.md (technical background)

## What I tried
{description}

## Why I expected it to work
*[Agent fills in: mechanistic reason with paper citation]*

## Results

| Seed | val_bpb | Artifact | Wall time |
|------|---------|----------|-----------|
{results_rows}

Parent ({parent_id}): {parent_bpb}
Pre-registered thresholds: {thresholds}

## What I learned
*[Agent fills in: 2-3 paragraphs on what the result teaches about the technique]*

## The broader concept: {technique}
*[Agent fills in: 2-3 paragraphs teaching the technique with analogies and citations]*

## Resources
*[Agent fills in: paper links, PR references]*

## What's next
*[Agent fills in: commit to a specific next experiment direction]*

---

*Part of my [Parameter Golf](https://github.com/openai/parameter-golf) daily blog series.*
"""


def generate_blog(args):
    """Scaffold a blog post. The /blog skill does the real writing."""
    db = get_db()

    exp = None
    if args.experiment:
        row = db.execute("SELECT * FROM experiments WHERE id = ?", (args.experiment,)).fetchone()
        if row:
            exp = dict(row)

    seeds = []
    if exp:
        seeds = [dict(s) for s in db.execute(
            "SELECT * FROM seeds WHERE experiment_id = ? ORDER BY seed",
            (args.experiment,)
        ).fetchall()]

    title = args.title or (exp['hypothesis'][:50] if exp else "Untitled")
    techniques = json.loads(exp['technique_stack']) if exp else []

    results_rows = []
    for s in seeds:
        size_mb = s['artifact_size_bytes'] / 1e6 if s.get('artifact_size_bytes') else '?'
        wt = f"{s['wall_time_seconds']:.0f}s" if s.get('wall_time_seconds') else '?'
        size_str = f"{size_mb:.2f} MB" if isinstance(size_mb, float) else size_mb
        results_rows.append(f"| {s['seed']} | {s['val_bpb']:.4f} | {size_str} | {wt} |")
    results_table = "\n".join(results_rows) if results_rows else "| — | — | — | — |"

    parent_bpb_str = "N/A"
    if exp and exp.get("parent_id"):
        parent_best = db.execute(
            "SELECT MIN(val_bpb) as b FROM seeds WHERE experiment_id = ?",
            (exp["parent_id"],)
        ).fetchone()
        if parent_best and parent_best["b"]:
            parent_bpb_str = f"{parent_best['b']:.4f}"

    prereg = None
    if args.experiment:
        p = db.execute("SELECT decision_rule FROM pre_registration WHERE experiment_id = ?", (args.experiment,)).fetchone()
        if p:
            prereg = p["decision_rule"]

    post = BLOG_TEMPLATE.format(
        day=args.day,
        title=title,
        date=datetime.now().strftime("%B %d, %Y"),
        exp_id=args.experiment or "UNKNOWN",
        description=exp['hypothesis'] if exp else "*Fill in experiment description*",
        results_rows=results_table,
        parent_id=exp.get('parent_id', 'none') if exp else 'none',
        parent_bpb=parent_bpb_str,
        thresholds=prereg or "not registered",
        technique=techniques[0] if techniques else "TBD",
    )

    filename = f"day_{args.day:02d}_{title.lower().replace(' ', '_').replace('/', '_')[:30]}.md"
    draft_path = BLOG_DIR / "drafts" / filename
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(post)

    print(f"Blog scaffold created: {draft_path}")
    print(f"The /blog skill should now fill in the sections with real writing.")
    db.close()


# ─── Status command ──────────────────────────────────────────────────────────

# ─── Report command — generate a comprehensive REPORT.md ────────────────────

def generate_report(args):
    """Generate REPORT.md at the project root — a single-file human-readable
    snapshot of everything. Run before a strategic pivot, when sharing with
    someone, or when you want a clean picture before opening Claude Code."""
    db = get_db()

    # Gather everything
    experiments = [dict(r) for r in db.execute(
        "SELECT * FROM experiments ORDER BY created_at DESC"
    ).fetchall()]

    seeds_by_exp = {}
    for s in db.execute("SELECT * FROM seeds ORDER BY experiment_id, seed").fetchall():
        seeds_by_exp.setdefault(s["experiment_id"], []).append(dict(s))

    prereg_by_exp = {}
    for r in db.execute("SELECT * FROM pre_registration").fetchall():
        prereg_by_exp[r["experiment_id"]] = dict(r)

    # Totals
    total = len(experiments)
    completed = sum(1 for e in experiments if e["status"] == "completed")
    failed = sum(1 for e in experiments if e["status"] == "failed")
    best_bpb = min((e["val_bpb"] for e in experiments if e["val_bpb"]), default=None)

    # Spend
    total_cost = 0.0
    spending_by_day = {}
    if SPENDING_LOG.exists():
        for line in SPENDING_LOG.read_text().splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                total_cost += entry.get("cost_usd", 0)
                day = entry.get("ts", "")[:10]
                spending_by_day[day] = spending_by_day.get(day, 0) + entry.get("cost_usd", 0)
            except json.JSONDecodeError:
                continue

    sota = get_current_sota()
    gap = (best_bpb - sota) if (best_bpb and sota) else None

    # Build report
    lines = []
    lines.append("# Parameter Golf — Experiment Report")
    lines.append(f"\n*Generated: {datetime.now().isoformat(timespec='seconds')}*")
    lines.append(f"*This file is auto-generated. Regenerate with `python scripts/pgolf.py report`.*\n")

    # Top-line
    lines.append("## Current state\n")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Current SOTA | {f'{sota:.4f}' if sota else '(no fetch yet)'} |")
    lines.append(f"| Your best BPB | {f'{best_bpb:.4f}' if best_bpb else '—'} |")
    lines.append(f"| Gap to SOTA | {f'{gap:+.4f}' if gap is not None else '—'} |")
    lines.append(f"| Experiments | {completed}/{total} completed, {failed} failed |")
    lines.append(f"| Spend | ${total_cost:.2f} / ${DEFAULT_BUDGET:.0f} (${DEFAULT_BUDGET-total_cost:.2f} remaining) |")
    lines.append("")

    # Top 5 results (ranked by BPB)
    ranked = sorted(
        [e for e in experiments if e.get("val_bpb")],
        key=lambda e: e["val_bpb"]
    )[:5]

    if ranked:
        lines.append("## Top 5 results\n")
        lines.append("| Rank | Exp | BPB | Size MB | Status | Hypothesis |")
        lines.append("|------|-----|-----|---------|--------|------------|")
        for i, e in enumerate(ranked, 1):
            size_mb = e["artifact_size_bytes"] / 1e6 if e["artifact_size_bytes"] else "—"
            size_str = f"{size_mb:.2f}" if isinstance(size_mb, float) else size_mb
            hyp = (e["hypothesis"] or "")[:50].replace("|", "\\|")
            lines.append(f"| {i} | {e['id']} | {e['val_bpb']:.4f} | {size_str} | {e['status']} | {hyp} |")
        lines.append("")

    # Experiment lineage tree
    lines.append("## Experiment lineage\n")
    lines.append("```")
    lines.extend(_render_lineage(experiments))
    lines.append("```")
    lines.append("")

    # Detailed per-experiment section
    lines.append("## All experiments\n")
    for e in experiments:
        eid = e["id"]
        lines.append(f"### {eid} — {e['status']}")
        lines.append(f"\n**Hypothesis:** {e['hypothesis']}\n")
        techs = json.loads(e["technique_stack"]) if e.get("technique_stack") else []
        lines.append(f"**Techniques:** {', '.join(techs)}")
        if e.get("parent_id"):
            lines.append(f"**Parent:** {e['parent_id']}")
        if e.get("val_bpb"):
            lines.append(f"**Best BPB:** {e['val_bpb']:.4f}")

        seeds = seeds_by_exp.get(eid, [])
        if seeds:
            lines.append(f"\n**Seeds ({len(seeds)}):**\n")
            lines.append("| Seed | val_bpb | Wall time | Artifact | GPU |")
            lines.append("|------|---------|-----------|----------|-----|")
            for s in seeds:
                size_mb = s["artifact_size_bytes"] / 1e6 if s.get("artifact_size_bytes") else "—"
                size_str = f"{size_mb:.2f} MB" if isinstance(size_mb, float) else size_mb
                wt = f"{s['wall_time_seconds']:.0f}s" if s.get("wall_time_seconds") else "—"
                gpu = s.get("gpu_type") or "—"
                lines.append(f"| {s['seed']} | {s['val_bpb']:.4f} | {wt} | {size_str} | {gpu} |")

        pr = prereg_by_exp.get(eid)
        if pr:
            lines.append(f"\n**Pre-registered rule:** {pr.get('decision_rule', '—')}")

        # Include analysis.md if it exists
        analysis_path = EXPERIMENTS_DIR / eid / "analysis.md"
        if analysis_path.exists():
            lines.append("\n<details><summary>analysis.md</summary>\n")
            lines.append(analysis_path.read_text())
            lines.append("\n</details>")

        if e.get("notes"):
            lines.append(f"\n**Notes:** {e['notes']}")

        lines.append("")

    # Spend breakdown
    lines.append("## Spending breakdown\n")
    if spending_by_day:
        lines.append("| Day | Spent |")
        lines.append("|-----|-------|")
        for day in sorted(spending_by_day.keys()):
            lines.append(f"| {day} | ${spending_by_day[day]:.2f} |")
        lines.append(f"| **Total** | **${total_cost:.2f}** |")
    else:
        lines.append("*No spending events logged yet.*")
    lines.append("")

    # Knowledge base status
    lines.append("## Knowledge base\n")
    tech_dir = KNOWLEDGE_DIR / "techniques"
    if tech_dir.exists():
        lines.append(f"- {len(list(tech_dir.glob('*.md')))} technique docs in `knowledge/techniques/`")
    lessons = KNOWLEDGE_DIR / "lessons_learned.md"
    if lessons.exists():
        conflict_count = lessons.read_text().lower().count("= bad")
        lines.append(f"- {conflict_count} documented technique conflicts in `knowledge/lessons_learned.md`")
    obs = KNOWLEDGE_DIR / "observations.md"
    if obs.exists():
        lines.append(f"- Cross-experiment observations present in `knowledge/observations.md` (last updated: {datetime.fromtimestamp(obs.stat().st_mtime).isoformat(timespec='seconds')})")
    else:
        lines.append(f"- No `knowledge/observations.md` yet — run `/synthesize` skill to generate one")
    lines.append("")

    # Write
    report_path = PROJECT_ROOT / "REPORT.md"
    report_path.write_text("\n".join(lines))
    print(f"Report written: {report_path}")
    print(f"Open in VSCode or preview with: grip REPORT.md")

    db.close()


def _render_lineage(experiments):
    """Build an ASCII tree of experiment parent-child relationships."""
    # Map parent -> children
    children = {}
    roots = []
    exps_by_id = {e["id"]: e for e in experiments}
    for e in experiments:
        parent = e.get("parent_id")
        if parent and parent in exps_by_id:
            children.setdefault(parent, []).append(e["id"])
        else:
            roots.append(e["id"])

    lines = []

    def render_node(eid, prefix, is_last):
        e = exps_by_id[eid]
        bpb_str = f"{e['val_bpb']:.4f}" if e.get("val_bpb") else "—"
        status_marker = {"completed": "✓", "failed": "✗", "planned": "?"}.get(e["status"], "·")
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{status_marker} {eid} [{bpb_str}] {(e['hypothesis'] or '')[:50]}")
        kids = children.get(eid, [])
        new_prefix = prefix + ("    " if is_last else "│   ")
        for i, kid in enumerate(kids):
            render_node(kid, new_prefix, i == len(kids) - 1)

    for i, root in enumerate(roots):
        render_node(root, "", i == len(roots) - 1)

    if not lines:
        lines.append("(no experiments yet)")
    return lines


# ─── Doctor — health check ──────────────────────────────────────────────────

def doctor(args):
    """Diagnostic health check of the scaffold. Run when things feel off."""
    issues = []
    ok = []

    # 1. DB reachable and has schema
    try:
        db = get_db()
        tables = set(r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall())
        required = {"experiments", "seeds", "pre_registration", "id_sequence"}
        if required.issubset(tables):
            ok.append("Database schema is complete")
        else:
            issues.append(f"Database missing tables: {required - tables}")
        db.close()
    except Exception as e:
        issues.append(f"Database error: {e}")

    # 2. State files exist and are writable
    STATE_DIR.mkdir(exist_ok=True)
    if SPENDING_LOG.exists() or SPENDING_LOG.parent.exists():
        ok.append(f"Spending log accessible at {SPENDING_LOG}")
    else:
        issues.append(f"Cannot access spending log directory: {SPENDING_LOG.parent}")

    # 3. Leaderboard state freshness
    if LEADERBOARD_STATE.exists():
        try:
            state = json.loads(LEADERBOARD_STATE.read_text())
            fetched = datetime.fromisoformat(state.get("fetched_at", ""))
            age_hours = (datetime.now() - fetched).total_seconds() / 3600
            if age_hours < 24:
                ok.append(f"Leaderboard cache is {age_hours:.1f}h old (fresh)")
            else:
                issues.append(f"Leaderboard cache is {age_hours:.1f}h old — run `pgolf leaderboard fetch`")
        except Exception as e:
            issues.append(f"Leaderboard state unreadable: {e}")
    else:
        issues.append("No leaderboard cache — run `pgolf leaderboard fetch`")

    # 4. Hooks exist and are executable
    pre_hook = PROJECT_ROOT / ".claude" / "hooks" / "pre-bash.sh"
    post_hook = PROJECT_ROOT / ".claude" / "hooks" / "post-bash.sh"
    for h in [pre_hook, post_hook]:
        if not h.exists():
            issues.append(f"Hook missing: {h.relative_to(PROJECT_ROOT)}")
        elif not os.access(h, os.X_OK):
            issues.append(f"Hook not executable: {h.relative_to(PROJECT_ROOT)} (fix: chmod +x {h.relative_to(PROJECT_ROOT)})")
        else:
            ok.append(f"Hook ready: {h.relative_to(PROJECT_ROOT)}")

    # 5. Skills present
    skills_dir = PROJECT_ROOT / ".claude" / "skills"
    expected = {"morning", "plan-experiment", "run-experiment", "analyze-results",
                "blog", "checkpoint", "submit-check", "synthesize"}
    if skills_dir.exists():
        present = {p.stem for p in skills_dir.glob("*.md")}
        missing = expected - present
        if missing:
            issues.append(f"Skills missing: {missing}")
        else:
            ok.append(f"All {len(expected)} skills present")
    else:
        issues.append(f"Skills directory missing: {skills_dir}")

    # 6. Knowledge base basics
    for required_kb in ["lessons_learned.md", "sota_timeline.md", "learning_path.md"]:
        p = KNOWLEDGE_DIR / required_kb
        if not p.exists():
            issues.append(f"Knowledge file missing: knowledge/{required_kb}")
        else:
            ok.append(f"Knowledge file present: knowledge/{required_kb}")

    # 7. Sanity-check pending runs
    try:
        db = get_db()
        stale = db.execute(
            """SELECT id, created_at FROM experiments
               WHERE status = 'planned'
                 AND datetime(created_at) < datetime('now', '-6 hours')"""
        ).fetchall()
        if stale:
            ids = [r["id"] for r in stale]
            issues.append(f"Stale 'planned' experiments (>6h old, may have crashed): {ids}")
        else:
            ok.append("No stale experiments")
        db.close()
    except Exception:
        pass

    # 8. Budget sanity
    total_cost = 0.0
    if SPENDING_LOG.exists():
        for line in SPENDING_LOG.read_text().splitlines():
            if line.strip():
                try:
                    total_cost += json.loads(line)["cost_usd"]
                except (json.JSONDecodeError, KeyError):
                    continue
    remaining = DEFAULT_BUDGET - total_cost
    spendable = remaining - DEFAULT_RESERVE
    if spendable < 30:
        issues.append(f"Budget critical: ${spendable:.2f} spendable (after reserve). "
                      f"Only 1-2 more 8×H100 runs affordable.")
    elif spendable < 100:
        ok.append(f"Budget: ${spendable:.2f} spendable (warning zone, ~4 runs left)")
    else:
        ok.append(f"Budget healthy: ${spendable:.2f} spendable")

    # Render
    print("\n═══ pgolf doctor ═══\n")
    for msg in ok:
        print(f"  \033[92m✓\033[0m {msg}")
    if issues:
        print()
        for msg in issues:
            print(f"  \033[91m✗\033[0m {msg}")
        print(f"\n{len(issues)} issue(s). Address before next experiment.")
        sys.exit(1)
    else:
        print(f"\nAll {len(ok)} checks passed.")


def show_status(args):
    db = get_db()

    total = db.execute("SELECT COUNT(*) as n FROM experiments").fetchone()["n"]
    completed = db.execute("SELECT COUNT(*) as n FROM experiments WHERE status='completed'").fetchone()["n"]
    failed = db.execute("SELECT COUNT(*) as n FROM experiments WHERE status='failed'").fetchone()["n"]
    best = db.execute("SELECT MIN(val_bpb) as best FROM experiments WHERE status='completed'").fetchone()["best"]

    # Read SOTA from cached leaderboard
    sota = get_current_sota()
    sota_str = f"{sota:.4f}" if sota else "unknown (run: pgolf leaderboard fetch)"
    gap_str = f"{best - sota:+.4f}" if (best and sota) else "—"

    # Read total spend
    total_cost = 0.0
    if SPENDING_LOG.exists():
        for line in SPENDING_LOG.read_text().splitlines():
            if line.strip():
                try:
                    total_cost += json.loads(line)["cost_usd"]
                except (json.JSONDecodeError, KeyError):
                    continue

    techs = db.execute("""
        SELECT technique_stack, val_bpb FROM experiments
        WHERE status = 'completed' AND val_bpb IS NOT NULL
        ORDER BY val_bpb ASC LIMIT 5
    """).fetchall()

    print("\n╔══════════════════════════════════════════╗")
    print("║     🏌️  Parameter Golf Agent Status      ║")
    print("╠══════════════════════════════════════════╣")
    print(f"║  Current SOTA:    {sota_str:>22} ║")
    print(f"║  Your best:       {f'{best:.4f}' if best else 'no results':>22} ║")
    print(f"║  Gap to SOTA:     {gap_str:>22} ║")
    print(f"║  Experiments:     {f'{completed}/{total} done, {failed} failed':>22} ║")
    print(f"║  Total spent:     {f'${total_cost:.2f} of ${DEFAULT_BUDGET:.0f}':>22} ║")
    print("╚══════════════════════════════════════════╝")

    if techs:
        print("\nTop 5 results:")
        for t in techs:
            stack = json.loads(t["technique_stack"])
            print(f"  {t['val_bpb']:.4f} BPB — {', '.join(stack[:3])}")

    tech_dir = KNOWLEDGE_DIR / "techniques"
    if tech_dir.exists():
        print(f"\nKnowledge base: {len(list(tech_dir.glob('*.md')))} technique docs")

    drafts = BLOG_DIR / "drafts"
    published = BLOG_DIR / "published"
    d_count = len(list(drafts.glob("*.md"))) if drafts.exists() else 0
    p_count = len(list(published.glob("*.md"))) if published.exists() else 0
    print(f"Blog posts: {p_count} published, {d_count} drafts")

    # Experiment lineage tree (if >0 experiments)
    experiments = [dict(r) for r in db.execute(
        "SELECT id, parent_id, status, val_bpb, hypothesis FROM experiments ORDER BY created_at"
    ).fetchall()]
    if experiments:
        print("\nExperiment lineage:")
        for line in _render_lineage(experiments):
            print(f"  {line}")

    print()  # trailing blank for readability
    db.close()


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="pgolf — Parameter Golf experiment toolkit")
    sub = parser.add_subparsers(dest="command")

    # track
    track = sub.add_parser("track", help="Experiment tracking")
    track_sub = track.add_subparsers(dest="track_action")

    create = track_sub.add_parser("create", help="Create new experiment")
    create.add_argument("--hypothesis", "-H", required=True)
    create.add_argument("--techniques", "-t", required=True, help="Comma-separated techniques")
    create.add_argument("--parent", "-p", help="Parent experiment ID")
    create.add_argument("--force", action="store_true", help="Override known conflicts from lessons_learned.md")

    result = track_sub.add_parser("result", help="Record experiment results")
    result.add_argument("experiment_id")
    result.add_argument("--bpb", type=float)
    result.add_argument("--loss", type=float)
    result.add_argument("--size", type=int, help="Artifact size in bytes")
    result.add_argument("--code-size", type=int, help="Code bytes")
    result.add_argument("--model-size", type=int, help="Model bytes")
    result.add_argument("--time", type=float, help="Training time in seconds")
    result.add_argument("--steps", type=int)
    result.add_argument("--gpu", help="GPU type e.g. '8xH100_SXM'")
    result.add_argument("--gpu-model", help="Specific GPU model e.g. 'NVIDIA H100 80GB HBM3'")
    result.add_argument("--torch-version", help="e.g. '2.8.0+cu128'")
    result.add_argument("--pg-commit", help="parameter-golf repo commit hash")
    result.add_argument("--cost", type=float, help="Cost in USD")
    result.add_argument("--seed", type=int, help="Random seed for this run")
    result.add_argument("--notes", help="Additional notes")

    fail = track_sub.add_parser("fail", help="Mark experiment as failed")
    fail.add_argument("experiment_id")
    fail.add_argument("--reason", "-r", help="Why it failed")

    lst = track_sub.add_parser("list", help="List experiments")
    lst.add_argument("--limit", "-n", type=int, default=15)

    # parse
    parse = sub.add_parser("parse", help="Parse training logs")
    parse.add_argument("log_path", nargs="?", help="Path to train.log")
    parse.add_argument("--compare", nargs=2, metavar=("EXP_A", "EXP_B"), help="Compare two experiments")
    parse.add_argument("--threshold", type=float, default=0.003, help="Min delta for significance (default 0.003 internal, 0.005 competition)")

    # spend
    spend = sub.add_parser("spend", help="Spending tracking")
    spend_sub = spend.add_subparsers(dest="spend_action")

    spend_log = spend_sub.add_parser("log-from-bash", help="[internal] Called by post-bash hook")
    spend_log.add_argument("--exp-id")
    spend_log.add_argument("--nproc", required=True)
    spend_log.add_argument("--log-path", help="Path to train.log")
    spend_log.add_argument("--exit-code", type=int, default=0)

    spend_t = spend_sub.add_parser("total", help="Print total spend")
    spend_t.add_argument("--quiet", action="store_true", help="Just the number, for shell use")

    spend_sub.add_parser("status", help="Full spending breakdown")

    # leaderboard
    lb = sub.add_parser("leaderboard", help="Leaderboard tracking")
    lb_sub = lb.add_subparsers(dest="lb_action")
    lb_sub.add_parser("fetch", help="Fetch latest PRs and update cached state")
    lb_sub.add_parser("current", help="Print cached current SOTA")

    # register-thresholds
    reg = sub.add_parser("register-thresholds", help="Pre-register decision thresholds for an experiment")
    reg.add_argument("experiment_id")
    reg.add_argument("--seed1-continue", type=float, required=True, help="Seed-1 screen: abandon if val_bpb exceeds this")
    reg.add_argument("--publish", type=float, default=0.005, help="Publication delta vs SOTA (default 0.005)")
    reg.add_argument("--internal", type=float, default=0.003, help="Internal delta vs parent (default 0.003)")

    # submit-check
    sc = sub.add_parser("submit-check", help="Run all pre-submission gates")
    sc.add_argument("experiment_id")

    # blog
    blog = sub.add_parser("blog", help="Create blog post scaffold (real writing is done by /blog skill)")
    blog.add_argument("--day", "-d", type=int, required=True)
    blog.add_argument("--experiment", "-e", help="Experiment ID to reference")
    blog.add_argument("--title", "-t", help="Blog post title")

    # status
    sub.add_parser("status", help="Show agent status")

    # report — comprehensive single-file snapshot
    sub.add_parser("report", help="Generate REPORT.md with full state snapshot")

    # doctor — health check
    sub.add_parser("doctor", help="Diagnostic health check — run when things feel off")

    args = parser.parse_args()

    if args.command == "track":
        if args.track_action == "create":
            track_create(args)
        elif args.track_action == "result":
            track_result(args)
        elif args.track_action == "fail":
            track_fail(args)
        elif args.track_action == "list":
            track_list(args)
        else:
            track.print_help()
    elif args.command == "parse":
        if args.compare:
            args.exp_a, args.exp_b = args.compare
            compare_experiments(args)
        elif args.log_path:
            parse_log(args)
        else:
            parse.print_help()
    elif args.command == "spend":
        if args.spend_action == "log-from-bash":
            spend_log_from_bash(args)
        elif args.spend_action == "total":
            spend_total(args)
        elif args.spend_action == "status":
            spend_status(args)
        else:
            spend.print_help()
    elif args.command == "leaderboard":
        if args.lb_action == "fetch":
            leaderboard_fetch(args)
        elif args.lb_action == "current":
            leaderboard_current(args)
        else:
            lb.print_help()
    elif args.command == "register-thresholds":
        register_thresholds(args)
    elif args.command == "submit-check":
        submit_check(args)
    elif args.command == "blog":
        generate_blog(args)
    elif args.command == "status":
        show_status(args)
    elif args.command == "report":
        generate_report(args)
    elif args.command == "doctor":
        doctor(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
