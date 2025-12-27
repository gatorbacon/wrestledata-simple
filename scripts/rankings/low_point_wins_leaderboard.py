#!/usr/bin/env python3
"""
low_point_wins_leaderboard.py

Creates a leaderboard of wrestlers with the most wins where they scored
X or fewer points. Useful for finding wrestlers who win efficiently with
low-scoring matches.

For every match across all weight classes:
  - Parse the score to determine points scored by winner
  - If winner scored <= X points, count it as a "low-point win"
  - Aggregate by wrestler and sort by most low-point wins

Output format:
    Rank    Name    Team    Weight    Low-Point Wins    Total Wins
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


def load_wrestler_info(season: int, data_dir: Path) -> Dict[str, Dict]:
    """
    Load wrestler information (name, team, weight) from all weight class files.
    Returns dict mapping wrestler_id -> {name, team, weight_class}
    """
    wrestler_info: Dict[str, Dict] = {}
    
    for wc_file in sorted(data_dir.glob("weight_class_*.json")):
        try:
            with wc_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Warning: could not read {wc_file}: {e}")
            continue
        
        # Extract weight class from filename
        weight_class_str = wc_file.stem.replace("weight_class_", "")
        try:
            weight_class = int(weight_class_str)
        except ValueError:
            continue
        
        # Wrestlers is a dict mapping wrestler_id -> wrestler_info
        wrestlers = data.get("wrestlers", {})
        for wrestler_id, winfo in wrestlers.items():
            if wrestler_id and wrestler_id not in wrestler_info:
                wrestler_info[wrestler_id] = {
                    "name": winfo.get("name", "Unknown"),
                    "team": winfo.get("team", "Unknown"),
                    "weight_class": weight_class,
                }
    
    return wrestler_info


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Leaderboard of wrestlers with the most wins where they scored "
            "X or fewer points."
        )
    )
    parser.add_argument(
        "-season",
        type=int,
        required=True,
        help="Season year (e.g., 2026).",
    )
    parser.add_argument(
        "-points",
        type=int,
        required=True,
        help="Maximum points scored to count as a 'low-point win'.",
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
            "Defaults to mt/graphics/{season}/low_point_wins_{points}.html"
        ),
    )
    parser.add_argument(
        "-top",
        type=int,
        default=50,
        help="Number of top wrestlers to show (default: 50).",
    )

    args = parser.parse_args()
    base_dir = Path(args.data_dir) / str(args.season)
    if not base_dir.exists() or not base_dir.is_dir():
        raise SystemExit(f"Data directory not found for season {args.season}: {base_dir}")

    max_points = args.points
    
    # Load wrestler info for display
    wrestler_info = load_wrestler_info(args.season, base_dir)
    
    # wrestler_id -> {'low_point_wins': int, 'total_wins': int}
    stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"low_point_wins": 0, "total_wins": 0})

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
            winner_id = m.get("winner_id")
            
            if not winner_id:
                continue
            
            # Skip forfeits
            if "MFF" in result.upper() or "FORFEIT" in result.upper():
                continue
            
            score = parse_score(result)
            if not score:
                # No score parsed, but it's still a win
                stats[winner_id]["total_wins"] += 1
                continue

            winner_pts, loser_pts = score
            
            # Count total wins
            stats[winner_id]["total_wins"] += 1
            
            # Count low-point wins (winner scored <= max_points)
            if winner_pts <= max_points:
                stats[winner_id]["low_point_wins"] += 1

    if not stats:
        print("No matches with winners were found.")
        return

    # Build leaderboard entries
    leaderboard: List[Tuple[str, int, int]] = []
    for wrestler_id, rec in stats.items():
        low_point_wins = rec["low_point_wins"]
        total_wins = rec["total_wins"]
        
        # Only include wrestlers with at least one low-point win
        if low_point_wins > 0:
            leaderboard.append((wrestler_id, low_point_wins, total_wins))

    if not leaderboard:
        print(f"No wrestlers found with wins scoring {max_points} or fewer points.")
        return

    # Sort by low_point_wins (descending), then by total_wins (descending)
    leaderboard.sort(key=lambda x: (x[1], x[2]), reverse=True)
    
    # Take top N
    leaderboard = leaderboard[:args.top]

    # Print to console (simplified: name, team, low-point wins only)
    print(f"Low-Point Wins Leaderboard (≤{max_points} points) — Season {args.season}")
    print("=" * 80)
    
    rows: List[Tuple[int, str, str, int, int, int]] = []
    for rank, (wrestler_id, low_point_wins, total_wins) in enumerate(leaderboard, 1):
        info = wrestler_info.get(wrestler_id, {})
        name = info.get("name", "Unknown")
        team = info.get("team", "Unknown")
        weight = info.get("weight_class", 0)
        
        rows.append((rank, name, team, weight, low_point_wins, total_wins))
        # Console output: just name, team, low-point wins
        print(f"{name:<30} {team:<20} {low_point_wins}")

    # Also render as HTML table.
    if args.output:
        out_path = Path(args.output)
    else:
        out_dir = Path("mt/graphics") / str(args.season)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"low_point_wins_{max_points}.html"

    out_path.parent.mkdir(parents=True, exist_ok=True)

    html_rows = "\n".join(
        f"            <tr><td>{rank}</td><td>{name}</td><td>{team}</td><td>{weight}</td><td>{low_point_wins}</td><td>{total_wins}</td></tr>"
        for rank, name, team, weight, low_point_wins, total_wins in rows
    )

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Low-Point Wins Leaderboard (≤{max_points} points) - Season {args.season}</title>
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
            padding: 8px 12px;
            text-align: left;
        }}
        th {{
            background-color: #f0f0f0;
            font-weight: 600;
        }}
        td:nth-child(4), td:nth-child(5), td:nth-child(6) {{
            text-align: right;
        }}
        tbody tr:nth-child(even) {{
            background-color: #fafafa;
        }}
        tbody tr:hover {{
            background-color: #f0f0f0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Low-Point Wins Leaderboard (≤{max_points} points) &mdash; Season {args.season}</h1>
        <table>
            <thead>
                <tr>
                    <th>Rank</th>
                    <th>Name</th>
                    <th>Team</th>
                    <th>Weight</th>
                    <th>Low-Pt Wins</th>
                    <th>Total Wins</th>
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

