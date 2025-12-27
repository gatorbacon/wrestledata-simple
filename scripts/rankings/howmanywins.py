#!/usr/bin/env python3
"""
howmanywins.py

For an entire season, analyze how often a wrestler wins or loses given that
they have exactly X wins.

For every wrestler across all weight classes:
  - Count their total wins
  - Count their total losses
  - Group by win count

At the end, we print a breakdown:

    Wins    Wrestlers    Total Wins    Total Losses    Win%

for X = 0..N, where N is the maximum win count observed.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Breakdown of win/loss record by number of wins, across all "
            "wrestlers for a season."
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
            "Defaults to mt/graphics/{season}/howmanywins.html"
        ),
    )

    args = parser.parse_args()
    base_dir = Path(args.data_dir) / str(args.season)
    if not base_dir.exists() or not base_dir.is_dir():
        raise SystemExit(f"Data directory not found for season {args.season}: {base_dir}")

    # wins_count -> {'wrestlers': int, 'total_wins': int, 'total_losses': int}
    stats: Dict[int, Dict[str, int]] = defaultdict(lambda: {"wrestlers": 0, "total_wins": 0, "total_losses": 0})
    max_wins = 0

    # Iterate all weight classes for this season
    for wc_file in sorted(base_dir.glob("weight_class_*.json")):
        try:
            with wc_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Warning: could not read {wc_file}: {e}")
            continue

        wrestlers = data.get("wrestlers", [])
        if not wrestlers:
            continue

        for wrestler in wrestlers:
            # Count wins and losses from matches
            wins = 0
            losses = 0
            
            matches = wrestler.get("matches", [])
            for m in matches:
                result = m.get("result", "")
                winner_id = m.get("winner_id")
                wrestler_id = wrestler.get("wrestler_id")
                
                if not winner_id or not wrestler_id:
                    continue
                
                # Skip forfeits
                if "MFF" in result.upper() or "FORFEIT" in result.upper():
                    continue
                
                if winner_id == wrestler_id:
                    wins += 1
                else:
                    losses += 1
            
            # Only count wrestlers who have wrestled at least one match
            if wins + losses == 0:
                continue
            
            # Update stats for this win count
            stats[wins]["wrestlers"] += 1
            stats[wins]["total_wins"] += wins
            stats[wins]["total_losses"] += losses
            
            if wins > max_wins:
                max_wins = wins

    if not stats:
        print("No wrestlers with matches were found.")
        return

    # Build a sorted list of win values that were actually used
    # Show every single number individually (no grouping)
    used_wins: List[int] = sorted(stats.keys())
    win_pct_by_wins: Dict[int, float] = {}
    
    for wins in used_wins:
        rec = stats[wins]
        total_wins = rec["total_wins"]
        total_losses = rec["total_losses"]
        total_matches = total_wins + total_losses
        if total_matches == 0:
            continue
        win_pct = total_wins / total_matches * 100.0
        win_pct_by_wins[wins] = win_pct

    if not used_wins:
        print("No wrestlers with non-zero matches were found.")
        return

    # Build list of report rows - show every single number individually
    # Each row is (label, wrestlers, total_wins, total_losses, win_pct)
    rows: List[tuple] = []

    for wins in used_wins:
        rec = stats[wins]
        wrestlers = rec["wrestlers"]
        total_wins = rec["total_wins"]
        total_losses = rec["total_losses"]
        total_matches = total_wins + total_losses
        if total_matches == 0:
            continue
        win_pct = win_pct_by_wins[wins]
        rows.append((str(wins), wrestlers, total_wins, total_losses, win_pct))

    # Print to console
    print("Wins\tWrestlers\tTotal Wins\tTotal Losses\tWin%")
    for label, wrestlers, total_wins, total_losses, win_pct in rows:
        print(f"{label}\t{wrestlers}\t{total_wins}\t{total_losses}\t{win_pct:.1f}%")

    # Also render as HTML table.
    if args.output:
        out_path = Path(args.output)
    else:
        out_dir = Path("mt/graphics") / str(args.season)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "howmanywins.html"

    out_path.parent.mkdir(parents=True, exist_ok=True)

    html_rows = "\n".join(
        f"            <tr><td>{label}</td><td>{wrestlers}</td><td>{total_wins}</td><td>{total_losses}</td><td>{win_pct:.1f}%</td></tr>"
        for label, wrestlers, total_wins, total_losses, win_pct in rows
    )

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Wins vs Win% Report - Season {args.season}</title>
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
        <h1>Wins vs Win% Report &mdash; Season {args.season}</h1>
        <table>
            <thead>
                <tr>
                    <th>Wins</th>
                    <th>Wrestlers</th>
                    <th>Total Wins</th>
                    <th>Total Losses</th>
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

