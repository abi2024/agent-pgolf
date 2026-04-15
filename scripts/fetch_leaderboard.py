#!/usr/bin/env python3
"""Fetch latest PRs from the parameter-golf repo and update knowledge base.

Usage:
    python scripts/fetch_leaderboard.py          # Fetch latest 20 PRs
    python scripts/fetch_leaderboard.py --limit 50  # Fetch more
    python scripts/fetch_leaderboard.py --update  # Also update sota_timeline.md

Requires: pip install httpx (or use with Claude Code which can curl directly)
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"


def fetch_prs(limit: int = 20) -> list[dict]:
    """Fetch recent PRs from the parameter-golf repo."""
    try:
        import httpx
    except ImportError:
        print("httpx not installed. Install with: pip install httpx")
        print("Or use curl directly:")
        print('  curl -s "https://api.github.com/repos/openai/parameter-golf/pulls?state=all&sort=created&direction=desc&per_page=20"')
        sys.exit(1)

    url = "https://api.github.com/repos/openai/parameter-golf/pulls"
    params = {"state": "all", "sort": "created", "direction": "desc", "per_page": limit}

    resp = httpx.get(url, params=params, headers={"Accept": "application/vnd.github.v3+json"}, timeout=30)

    if resp.status_code != 200:
        print(f"GitHub API error: {resp.status_code}")
        print(resp.text[:500])
        sys.exit(1)

    prs = resp.json()
    results = []
    for pr in prs:
        results.append({
            "number": pr["number"],
            "title": pr["title"],
            "author": pr["user"]["login"],
            "state": pr["state"],
            "merged": pr.get("merged_at") is not None,
            "created_at": pr["created_at"][:10],
            "url": pr["html_url"],
            "labels": [l["name"] for l in pr.get("labels", [])],
        })

    return results


def display_prs(prs: list[dict]):
    """Print PR list in a readable format."""
    print(f"\n{'#':<6} {'State':<8} {'Author':<18} {'Title'}")
    print("─" * 90)
    for pr in prs:
        state = "merged" if pr["merged"] else pr["state"]
        title = pr["title"][:55]
        print(f"#{pr['number']:<5} {state:<8} {pr['author']:<18} {title}")
    print(f"\nTotal: {len(prs)} PRs")


def extract_bpb_from_title(title: str) -> float | None:
    """Try to extract BPB score from PR title."""
    import re
    match = re.search(r'(\d+\.\d{3,})', title)
    if match:
        val = float(match.group(1))
        if 0.9 < val < 1.5:  # Plausible BPB range
            return val
    return None


def update_timeline(prs: list[dict]):
    """Append new PRs to sota_timeline.md."""
    timeline_path = KNOWLEDGE_DIR / "sota_timeline.md"

    if not timeline_path.exists():
        print("sota_timeline.md not found, skipping update")
        return

    existing = timeline_path.read_text()

    new_entries = []
    for pr in prs:
        # Check if PR is already in the timeline
        if f"#{pr['number']}" in existing:
            continue
        if not pr["merged"]:
            continue

        bpb = extract_bpb_from_title(pr["title"])
        if bpb:
            new_entries.append(
                f"| {pr['created_at']} | {bpb:.4f} | {pr['title'][:40]} | #{pr['number']} |"
            )

    if new_entries:
        print(f"\nNew entries to add to sota_timeline.md:")
        for entry in new_entries:
            print(f"  {entry}")
        print("\n(Add these manually to the timeline table in the correct position)")
    else:
        print("\nNo new entries to add to timeline.")


def main():
    parser = argparse.ArgumentParser(description="Fetch Parameter Golf PRs")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--update", action="store_true", help="Update sota_timeline.md")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    prs = fetch_prs(args.limit)

    if args.json:
        print(json.dumps(prs, indent=2))
    else:
        display_prs(prs)

    if args.update:
        update_timeline(prs)


if __name__ == "__main__":
    main()
