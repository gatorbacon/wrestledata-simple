#!/usr/bin/env python3
"""
howmanypoints.py

For an entire season, analyze how often a wrestler wins or loses given that
they score exactly X points in a match.

For every match across all weight classes:
  - If we can parse a numeric score like "12-3" from the result string,
    we treat that as (winner_points, loser_points).
  - We record:
      * a "win" for the side that scored winner_points
      * a "loss" for the side that scored loser_points

At the end, we print a breakdown:

    Points    Wins    Losses    Win%

for X = 1..N, where N is the maximum points value observed.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def parse_score(result: str) -> Optional[Tuple[int, int]]:
    """
    Extract (winner_points, loser_points) from a result string like:
      'Dec 4-2', 'MD 12-3', 'TF 18-0 2:33'
    If no score can be parsed, return None.
    """
    if not result:
        return None
    m = re.search(r"(\d+)-(\d+)", result)
    if not m:
        return None
    a = int(m.group(1))
    b = int(m.group(2))
    # We don't trust ordering in the string; treat the larger as winner's score.
    winner_pts = max(a, b)
    loser_pts = min(a, b)
    return winner_pts, loser_pts


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Breakdown of win/loss record by points scored, across all "
            "matches for a season."
        )
    )
    parser.add_argument(
        "-season",
        type=int,
        required=True,
        help="Season year (e.g., 2026).",
    )
    parser.add_argument(
        "-data-dir",
        default="mt/rankings_data",
        help="Base data directory containing weight_class_*.json files.",
    )
    parser.add_argument(
        "-output",
        default=None,
        help=(
            "Optional HTML output path for the report. "
            "Defaults to mt/graphics/{season}/howmanypoints.html"
        ),
    )

    args = parser.parse_args()
    base_dir = Path(args.data_dir) / str(args.season)
    if not base_dir.exists() or not base_dir.is_dir():
        raise SystemExit(f"Data directory not found for season {args.season}: {base_dir}")

    # points -> {'wins': int, 'losses': int}
    stats: Dict[int, Dict[str, int]] = defaultdict(lambda: {"wins": 0, "losses": 0})
    max_points = 0

    # Iterate all weight classes for this season
    for wc_file in sorted(base_dir.glob("weight_class_*.json")):
        try:
            with wc_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Warning: could not read {wc_file}: {e}")
            continue

        matches = data.get("matches", [])
        if not matches:
            continue

        for m in matches:
            result = m.get("result", "")
            score = parse_score(result)
            if not score:
                continue

            winner_pts, loser_pts = score
            if winner_pts <= 0 and loser_pts <= 0:
                continue

            stats[winner_pts]["wins"] += 1
            stats[loser_pts]["losses"] += 1

            if winner_pts > max_points:
                max_points = winner_pts
            if loser_pts > max_points:
                max_points = loser_pts

    if not stats:
        print("No scored matches with parsable points were found.")
        return

    # Build a sorted list of point values that were actually used
    # (skip any values with zero total usage).
    used_points: List[int] = []
    win_pct_by_pts: Dict[int, float] = {}
    for pts in sorted(stats.keys()):
        rec = stats[pts]
        wins = rec["wins"]
        losses = rec["losses"]
        total = wins + losses
        if total == 0:
            continue
        win_pct = wins / total * 100.0
        used_points.append(pts)
        win_pct_by_pts[pts] = win_pct

    if not used_points:
        print("No scored matches with non-zero wins/losses were found.")
        return

    # Build list of report rows - show every single number individually
    # Each row is (label, wins, losses, win_pct)
    rows: List[Tuple[str, int, int, float]] = []

    # Add each used point separately - no grouping
    for pts in used_points:
        rec = stats[pts]
        wins = rec["wins"]
        losses = rec["losses"]
        total = wins + losses
        if total == 0:
            continue
        win_pct = win_pct_by_pts[pts]
        rows.append((str(pts), wins, losses, win_pct))

    # Print to console
    print("Points\tWins\tLosses\tWin%")
    for label, wins, losses, win_pct in rows:
        print(f"{label}\t{wins}\t{losses}\t{win_pct:.1f}%")

    # Also render as HTML table.
    if args.output:
        out_path = Path(args.output)
    else:
        out_dir = Path("mt/graphics") / str(args.season)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "howmanypoints.html"

    out_path.parent.mkdir(parents=True, exist_ok=True)

    html_rows = "\n".join(
        f"            <tr><td>{label}</td><td>{wins}</td><td>{losses}</td><td>{win_pct:.1f}%</td></tr>"
        for label, wins, losses, win_pct in rows
    )

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Points vs Win% Report - Season {args.season}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background-color: #ffffff;
            padding: 20px;
            border-radius: 6px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            margin-top: 0;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            background-color: #fff;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 6px 8px;
            text-align: right;
        }}
        th:first-child, td:first-child {{
            text-align: left;
        }}
        th {{
            background-color: #f0f0f0;
        }}
        tbody tr:nth-child(even) {{
            background-color: #fafafa;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Points vs Win% Report &mdash; Season {args.season}</h1>
        <table>
            <thead>
                <tr>
                    <th>Points</th>
                    <th>Wins</th>
                    <th>Losses</th>
                    <th>Win%</th>
                </tr>
            </thead>
            <tbody>
{html_rows}
            </tbody>
        </table>
    </div>
</body>
</html>
"""

    with out_path.open("w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"\nHTML report written to {out_path}")


if __name__ == "__main__":
    main()


