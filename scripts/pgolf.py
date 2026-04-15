#!/usr/bin/env python3
"""pgolf — CLI toolkit for Parameter Golf experiments.

Called by Claude Code via bash. NOT an agent — just structured tools.

Usage:
    python scripts/pgolf.py track create --hypothesis "..." --techniques "a,b,c"
    python scripts/pgolf.py track result exp_001 --bpb 1.12 --size 15000000
    python scripts/pgolf.py track list
    python scripts/pgolf.py parse path/to/train.log
    python scripts/pgolf.py parse --compare exp_001 exp_002
    python scripts/pgolf.py blog --day 3 --experiment exp_001
    python scripts/pgolf.py status
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# ─── Paths ───────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "pgolf.db"
EXPERIMENTS_DIR = PROJECT_ROOT / "experiments"
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
BLOG_DIR = PROJECT_ROOT / "blog"


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
            training_seconds REAL,
            training_steps INTEGER,
            gpu_type TEXT,
            gpu_count INTEGER,
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
            PRIMARY KEY (experiment_id, seed)
        );
    """)
    return conn


# ─── Track commands ──────────────────────────────────────────────────────────

def track_create(args):
    db = get_db()
    # Auto-generate ID
    row = db.execute("SELECT COUNT(*) as n FROM experiments").fetchone()
    exp_id = f"exp_{row['n'] + 1:03d}"

    techniques = [t.strip() for t in args.techniques.split(",") if t.strip()]

    db.execute(
        "INSERT INTO experiments (id, hypothesis, technique_stack, parent_id) VALUES (?, ?, ?, ?)",
        (exp_id, args.hypothesis, json.dumps(techniques), args.parent or None),
    )
    db.commit()

    # Create experiment directory
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
    db.close()


def track_result(args):
    db = get_db()
    exp_id = args.experiment_id

    updates = ["status = 'completed'"]
    params = []

    if args.bpb is not None:
        updates.append("val_bpb = ?")
        params.append(args.bpb)
    if args.loss is not None:
        updates.append("val_loss = ?")
        params.append(args.loss)
    if args.size is not None:
        updates.append("artifact_size_bytes = ?")
        params.append(args.size)
    if args.time is not None:
        updates.append("training_seconds = ?")
        params.append(args.time)
    if args.steps is not None:
        updates.append("training_steps = ?")
        params.append(args.steps)
    if args.gpu:
        updates.append("gpu_type = ?")
        params.append(args.gpu)
    if args.cost is not None:
        updates.append("cost_usd = ?")
        params.append(args.cost)
    if args.notes:
        updates.append("notes = ?")
        params.append(args.notes)

    params.append(exp_id)
    db.execute(f"UPDATE experiments SET {', '.join(updates)} WHERE id = ?", params)

    # Record seed if provided
    if args.seed is not None and args.bpb is not None:
        db.execute(
            "INSERT OR REPLACE INTO seeds (experiment_id, seed, val_bpb, val_loss) VALUES (?, ?, ?, ?)",
            (exp_id, args.seed, args.bpb, args.loss),
        )

    db.commit()
    print(f"Updated {exp_id}: BPB={args.bpb}, size={args.size}, status=completed")
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

    print(f"\n{'ID':<10} {'Status':<11} {'BPB':>8} {'Size (MB)':>10} {'Hypothesis'}")
    print("─" * 80)
    for r in rows:
        bpb = f"{r['val_bpb']:.4f}" if r['val_bpb'] else "   —"
        size = f"{r['artifact_size_bytes']/1e6:.2f}" if r['artifact_size_bytes'] else "  —"
        hyp = (r['hypothesis'] or '')[:40]
        print(f"{r['id']:<10} {r['status']:<11} {bpb:>8} {size:>10} {hyp}")

    print(f"\nBest BPB: {best['best']:.4f}" if best['best'] else "\nNo completed experiments yet.")
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

    # Save as results.json next to the log
    results_path = log_path.parent / "results.json"
    results_path.write_text(json.dumps(results, indent=2))
    print(f"\nSaved to {results_path}")


def extract_metrics(text: str) -> dict:
    """Extract key metrics from Parameter Golf training log text."""
    results = {
        "val_bpb": None,
        "val_loss": None,
        "artifact_size_bytes": None,
        "artifact_size_mb": None,
        "training_steps": None,
        "wall_time_seconds": None,
        "under_16mb": None,
        "loss_curve": [],
    }

    # val_bpb — look for the final reported value
    for pattern in [r"val_bpb[:\s=]+([0-9.]+)", r"bpb[:\s=]+([0-9.]+)"]:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            results["val_bpb"] = float(matches[-1])
            break

    # val_loss
    matches = re.findall(r"val_loss[:\s=]+([0-9.]+)", text)
    if matches:
        results["val_loss"] = float(matches[-1])

    # Artifact size
    for pattern in [
        r"(\d[\d,]*)\s*bytes.*?(?:artifact|model|compressed)",
        r"(?:artifact|model|compressed).*?(\d[\d,]*)\s*bytes",
        r"final.*?size[:\s=]+(\d[\d,]*)",
    ]:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            size = int(matches[-1].replace(",", ""))
            results["artifact_size_bytes"] = size
            results["artifact_size_mb"] = round(size / 1_000_000, 3)
            results["under_16mb"] = size <= 16_000_000
            break

    # Training steps
    step_matches = re.findall(r"step[:\s=]*(\d+)", text)
    if step_matches:
        results["training_steps"] = max(int(s) for s in step_matches)

    # Wall time
    time_matches = re.findall(r"(\d+\.?\d*)\s*(?:s|sec)", text)
    if time_matches:
        results["wall_time_seconds"] = float(time_matches[-1])

    # Loss curve (step, loss pairs)
    for match in re.finditer(r"step[:\s=]*(\d+).*?loss[:\s=]*([0-9.]+)", text):
        results["loss_curve"].append({
            "step": int(match.group(1)),
            "loss": float(match.group(2)),
        })

    return results


def compare_experiments(args):
    """Compare two experiments for statistical significance."""
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
        print("Record more seeds with: pgolf track result EXP --bpb X --seed N")
        db.close()
        return

    bpb_a = [r["val_bpb"] for r in seeds_a]
    bpb_b = [r["val_bpb"] for r in seeds_b]

    try:
        from scipy import stats
        t_stat, p_value = stats.ttest_ind(bpb_a, bpb_b)
    except ImportError:
        # Fallback: simple comparison
        import statistics
        mean_a = statistics.mean(bpb_a)
        mean_b = statistics.mean(bpb_b)
        print(f"\n{args.exp_a}: mean={mean_a:.4f} std={statistics.stdev(bpb_a):.4f} (n={len(bpb_a)})")
        print(f"{args.exp_b}: mean={mean_b:.4f} std={statistics.stdev(bpb_b):.4f} (n={len(bpb_b)})")
        print(f"Delta: {mean_a - mean_b:+.4f}")
        print("(Install scipy for p-value calculation)")
        db.close()
        return

    import statistics
    mean_a = statistics.mean(bpb_a)
    mean_b = statistics.mean(bpb_b)
    delta = mean_a - mean_b

    print(f"\n{'Metric':<20} {args.exp_a:<15} {args.exp_b:<15}")
    print("─" * 50)
    print(f"{'Mean BPB':<20} {mean_a:<15.4f} {mean_b:<15.4f}")
    print(f"{'Std BPB':<20} {statistics.stdev(bpb_a):<15.4f} {statistics.stdev(bpb_b):<15.4f}")
    print(f"{'Seeds':<20} {len(bpb_a):<15} {len(bpb_b):<15}")
    print(f"\nDelta (A-B): {delta:+.4f}")
    print(f"t-statistic: {t_stat:.3f}")
    print(f"p-value: {p_value:.4f}")

    if p_value < 0.01 and abs(delta) >= 0.005:
        winner = args.exp_a if delta < 0 else args.exp_b
        print(f"\n✅ Statistically significant improvement (p<0.01, |Δ|≥0.005)")
        print(f"   Winner: {winner}")
    elif p_value < 0.05:
        print(f"\n⚠️  Marginally significant (p<0.05) — run more seeds")
    else:
        print(f"\n❌ Not significant (p={p_value:.3f}) — difference may be noise")

    db.close()


# ─── Blog commands ───────────────────────────────────────────────────────────

BLOG_TEMPLATE = """# Day {day}: {title}

*{date} · Parameter Golf Daily Blog*

## What I tried

{description}

## The hypothesis

{hypothesis}

## Results

| Metric | Value |
|--------|-------|
| val_bpb | {bpb} |
| Artifact size | {size} |
| Training time | {time} |
| GPU | {gpu} |

## What I learned

{learnings}

## Key concept: {technique}

{technique_explanation}

### Resources

{resources}

## What's next

{next_steps}

---

*Part of my [Parameter Golf](https://github.com/openai/parameter-golf) daily blog series.*
"""


def generate_blog(args):
    db = get_db()

    exp = None
    if args.experiment:
        row = db.execute("SELECT * FROM experiments WHERE id = ?", (args.experiment,)).fetchone()
        if row:
            exp = dict(row)

    title = args.title or (exp['hypothesis'][:50] if exp else "Untitled")
    bpb = f"{exp['val_bpb']:.4f}" if exp and exp['val_bpb'] else "TBD"
    size = f"{exp['artifact_size_bytes']/1e6:.2f} MB" if exp and exp['artifact_size_bytes'] else "TBD"
    time_s = f"{exp['training_seconds']:.0f}s" if exp and exp['training_seconds'] else "TBD"
    gpu = exp['gpu_type'] or "TBD" if exp else "TBD"
    techniques = json.loads(exp['technique_stack']) if exp else []

    post = BLOG_TEMPLATE.format(
        day=args.day,
        title=title,
        date=datetime.now().strftime("%B %d, %Y"),
        description=exp['hypothesis'] if exp else "*Fill in experiment description*",
        hypothesis="*Fill in your hypothesis*",
        bpb=bpb,
        size=size,
        time=time_s,
        gpu=gpu,
        learnings="*Fill in key learnings*",
        technique=techniques[0] if techniques else "TBD",
        technique_explanation="*Fill in technique explanation for readers*",
        resources="*Add relevant papers and links*",
        next_steps="*What will you try tomorrow?*",
    )

    filename = f"day_{args.day:02d}_{title.lower().replace(' ', '_')[:30]}.md"
    draft_path = BLOG_DIR / "drafts" / filename
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(post)

    print(f"Blog draft created: {draft_path}")
    print(f"Edit it, then move to blog/published/ when ready.")
    db.close()


# ─── Status command ──────────────────────────────────────────────────────────

def show_status(args):
    db = get_db()

    total = db.execute("SELECT COUNT(*) as n FROM experiments").fetchone()["n"]
    completed = db.execute("SELECT COUNT(*) as n FROM experiments WHERE status='completed'").fetchone()["n"]
    failed = db.execute("SELECT COUNT(*) as n FROM experiments WHERE status='failed'").fetchone()["n"]
    best = db.execute("SELECT MIN(val_bpb) as best FROM experiments WHERE status='completed'").fetchone()["best"]
    total_cost = db.execute("SELECT COALESCE(SUM(cost_usd), 0) as c FROM experiments").fetchone()["c"]

    # Technique summary
    techs = db.execute("""
        SELECT technique_stack, val_bpb FROM experiments
        WHERE status = 'completed' AND val_bpb IS NOT NULL
        ORDER BY val_bpb ASC LIMIT 5
    """).fetchall()

    print("\n╔══════════════════════════════════════════╗")
    print("║     🏌️  Parameter Golf Agent Status      ║")
    print("╠══════════════════════════════════════════╣")
    print(f"║  Competition SOTA:  1.0810 BPB           ║")
    print(f"║  Your best:         {f'{best:.4f} BPB' if best else 'No results yet':>20} ║")
    print(f"║  Gap to SOTA:       {f'{best - 1.0810:+.4f}' if best else 'N/A':>20} ║")
    print(f"║  Experiments:       {f'{completed}/{total} done, {failed} failed':>20} ║")
    print(f"║  Total cost:        {f'${total_cost:.2f}':>20} ║")
    print("╚══════════════════════════════════════════╝")

    if techs:
        print("\nTop 5 results:")
        for t in techs:
            stack = json.loads(t["technique_stack"])
            print(f"  {t['val_bpb']:.4f} BPB — {', '.join(stack[:3])}")

    # Count knowledge docs
    tech_dir = KNOWLEDGE_DIR / "techniques"
    if tech_dir.exists():
        tech_count = len(list(tech_dir.glob("*.md")))
        print(f"\nKnowledge base: {tech_count} technique docs")

    # Count blog posts
    drafts = BLOG_DIR / "drafts"
    published = BLOG_DIR / "published"
    d_count = len(list(drafts.glob("*.md"))) if drafts.exists() else 0
    p_count = len(list(published.glob("*.md"))) if published.exists() else 0
    print(f"Blog posts: {p_count} published, {d_count} drafts")

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

    result = track_sub.add_parser("result", help="Record experiment results")
    result.add_argument("experiment_id")
    result.add_argument("--bpb", type=float)
    result.add_argument("--loss", type=float)
    result.add_argument("--size", type=int, help="Artifact size in bytes")
    result.add_argument("--time", type=float, help="Training time in seconds")
    result.add_argument("--steps", type=int)
    result.add_argument("--gpu", help="GPU type e.g. '1xH100'")
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

    # blog
    blog = sub.add_parser("blog", help="Generate blog post")
    blog.add_argument("--day", "-d", type=int, required=True)
    blog.add_argument("--experiment", "-e", help="Experiment ID to reference")
    blog.add_argument("--title", "-t", help="Blog post title")

    # status
    sub.add_parser("status", help="Show agent status")

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
    elif args.command == "blog":
        generate_blog(args)
    elif args.command == "status":
        show_status(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
