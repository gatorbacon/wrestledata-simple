#!/usr/bin/env python3
"""
Compute and display team xTP leaderboard by aggregating per-weight xTP results.

This script:
1. Loads per-weight xTP JSON files (or generates them if needed)
2. Aggregates individual wrestler xTP to team totals
3. Writes team leaderboard JSON
4. Displays formatted team leaderboard
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


# D1 weight classes
WEIGHTS = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]


def load_weight_xtp(season: int, weight: int, data_dir: str) -> List[Dict]:
    """
    Load xTP data for a specific weight class.
    
    Args:
        season: Season year
        weight: Weight class
        data_dir: Directory containing xTP JSON files
    
    Returns:
        List of xTP entries for that weight
    """
    xtp_path = Path(data_dir) / str(season) / f"xtp_weight_{season}_{weight}.json"
    
    if not xtp_path.exists():
        return []
    
    try:
        with xtp_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  Warning: Failed to load {xtp_path}: {e}")
        return []


def rebuild_weight_xtp(season: int, weight: int, rankings_dir: str, wrestlers_dir: str, data_dir: str) -> bool:
    """
    Rebuild xTP for a specific weight class by calling the weight runner.
    
    Args:
        season: Season year
        weight: Weight class
        rankings_dir: Directory containing rankings files
        wrestlers_dir: Directory containing wrestler JSON files
        data_dir: Directory for output files
    
    Returns:
        True if successful, False otherwise
    """
    script_path = project_root / "scripts" / "xtp" / "run_weight_xtp.py"
    
    cmd = [
        sys.executable,
        str(script_path),
        "--season", str(season),
        "--weight", str(weight),
        "--rankings-dir", rankings_dir,
        "--wrestlers-dir", wrestlers_dir,
        "--output-dir", data_dir,
        "--export-json"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"  Error rebuilding weight {weight}: {e}")
        print(f"  stderr: {e.stderr}")
        return False


def aggregate_team_xtp(season: int, data_dir: str) -> Dict[str, Dict]:
    """
    Aggregate per-weight xTP data to team totals.
    
    Args:
        season: Season year
        data_dir: Directory containing xTP JSON files
    
    Returns:
        Dict mapping team name to team data with totals and per-weight breakdown
    """
    teams: Dict[str, Dict] = {}
    
    print(f"Loading per-weight xTP data...")
    
    for weight in WEIGHTS:
        weight_data = load_weight_xtp(season, weight, data_dir)
        
        if not weight_data:
            print(f"  Weight {weight}: No data found")
            continue
        
        print(f"  Weight {weight}: {len(weight_data)} entries")
        
        for entry in weight_data:
            team = entry.get("team")
            if not team:
                continue
            
            # Initialize team if not seen before
            if team not in teams:
                teams[team] = {
                    "team": team,
                    "team_xTP_A": 0.0,
                    "team_xTP_P": 0.0,
                    "team_xTP_B": 0.0,
                    "team_xTP": 0.0,
                    "weights": {}
                }
            
            # Add to team totals
            teams[team]["team_xTP_A"] += entry.get("xTP_A", 0.0)
            teams[team]["team_xTP_P"] += entry.get("xTP_P", 0.0)
            teams[team]["team_xTP_B"] += entry.get("xTP_B", 0.0)
            teams[team]["team_xTP"] += entry.get("xTP", 0.0)
            
            # Store per-weight breakdown
            teams[team]["weights"][str(weight)] = {
                "wrestler_id": entry.get("wrestler_id"),
                "name": entry.get("name"),
                "rank": entry.get("rank"),
                "xTP_A": entry.get("xTP_A", 0.0),
                "xTP_P": entry.get("xTP_P", 0.0),
                "xTP_B": entry.get("xTP_B", 0.0),
                "xTP": entry.get("xTP", 0.0),
                # Include placement probabilities if available
                "aa_prob": entry.get("aa_prob", None),
                "champ_prob": entry.get("champ_prob", None),
                "final_prob": entry.get("final_prob", None),
            }
    
    return teams


def validate_team_data(teams: Dict[str, Dict]) -> bool:
    """
    Validate team aggregation data.
    
    Args:
        teams: Dict mapping team name to team data
    
    Returns:
        True if all validations pass, False otherwise
    """
    valid = True
    
    for team_name, team_data in teams.items():
        xTP_A = team_data.get("team_xTP_A", 0.0)
        xTP_P = team_data.get("team_xTP_P", 0.0)
        xTP_B = team_data.get("team_xTP_B", 0.0)
        xTP = team_data.get("team_xTP", 0.0)
        
        # Check for NaN
        if xTP_A != xTP_A or xTP_P != xTP_P or xTP_B != xTP_B or xTP != xTP:
            print(f"Warning: NaN detected for {team_name}")
            valid = False
        
        # Check sum (allow small floating point differences)
        expected_sum = xTP_A + xTP_P + xTP_B
        if abs(xTP - expected_sum) > 0.02:  # Allow 0.02 tolerance for rounding
            print(f"Warning: xTP sum mismatch for {team_name}: {xTP} != {expected_sum}")
            valid = False
        
        # Check non-negative
        if xTP_A < 0 or xTP_P < 0 or xTP_B < 0 or xTP < 0:
            print(f"Warning: Negative xTP for {team_name}")
            valid = False
    
    return valid


def write_team_xtp_json(teams: Dict[str, Dict], season: int, data_dir: str) -> Path:
    """
    Write team xTP leaderboard to JSON file.
    
    Args:
        teams: Dict mapping team name to team data
        season: Season year
        data_dir: Directory for output file
    
    Returns:
        Path to written file
    """
    output_path = Path(data_dir) / str(season)
    output_path.mkdir(parents=True, exist_ok=True)
    
    output_file = output_path / f"xtp_teams_{season}.json"
    
    # Convert teams dict to sorted list
    teams_list = list(teams.values())
    teams_list.sort(key=lambda t: (-t["team_xTP"], -t["team_xTP_P"], -t["team_xTP_A"], t["team"]))
    
    output_data = {
        "season": season,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "weights": WEIGHTS,
        "teams": teams_list
    }
    
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)
    
    print(f"\nExported team xTP JSON: {output_file}")
    print(f"  {len(teams_list)} teams")
    
    return output_file


def print_team_leaderboard(teams: Dict[str, Dict], limit: Optional[int] = None) -> None:
    """
    Print formatted team xTP leaderboard table.
    
    Args:
        teams: Dict mapping team name to team data
        limit: Optional limit on number of entries to print
    """
    # Convert to sorted list
    teams_list = list(teams.values())
    teams_list.sort(key=lambda t: (-t["team_xTP"], -t["team_xTP_P"], -t["team_xTP_A"], t["team"]))
    
    if limit:
        teams_list = teams_list[:limit]
    
    if not teams_list:
        print("No team data found.")
        return
    
    # Calculate column widths
    max_team_len = max(len(team.get("team", "")) for team in teams_list)
    team_width = max(20, min(max_team_len + 2, 30))
    
    # Print header
    header = (
        f"{'Rank':<6} "
        f"{'Team':<{team_width}} "
        f"{'team_xTP':<10} "
        f"{'team_xTP_P':<11} "
        f"{'team_xTP_A':<11} "
        f"{'team_xTP_B':<11}"
    )
    print(header)
    print("-" * len(header))
    
    # Print entries
    for rank, team in enumerate(teams_list, 1):
        team_name = team.get("team", "Unknown")
        xTP = team.get("team_xTP", 0.0)
        xTP_P = team.get("team_xTP_P", 0.0)
        xTP_A = team.get("team_xTP_A", 0.0)
        xTP_B = team.get("team_xTP_B", 0.0)
        
        # Truncate team name if too long
        if len(team_name) > team_width - 2:
            team_name = team_name[:team_width - 5] + "..."
        
        row = (
            f"{rank:<6} "
            f"{team_name:<{team_width}} "
            f"{xTP:>9.2f} "
            f"{xTP_P:>10.2f} "
            f"{xTP_A:>10.2f} "
            f"{xTP_B:>10.2f}"
        )
        print(row)
    
    print(f"\nTotal teams: {len(teams_list)}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Compute and display team xTP leaderboard"
    )
    parser.add_argument(
        "--season",
        type=int,
        required=True,
        help="Season year"
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="data/xtp",
        help="Directory containing xTP JSON files"
    )
    parser.add_argument(
        "--rankings-dir",
        type=str,
        default="mt/rankings_data",
        help="Directory containing rankings files (for rebuild)"
    )
    parser.add_argument(
        "--wrestlers-dir",
        type=str,
        default="frontend/wrestledata-ui/public/wrestlers",
        help="Directory containing wrestler JSON files (for rebuild)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of teams to print (optional)"
    )
    parser.add_argument(
        "--rebuild-weights",
        action="store_true",
        help="Rebuild per-weight xTP files before aggregation"
    )
    
    args = parser.parse_args()
    
    print(f"{'=' * 80}")
    print(f"Team xTP Leaderboard: Season {args.season}")
    print(f"{'=' * 80}\n")
    
    # Rebuild weights if requested
    if args.rebuild_weights:
        print(f"Rebuilding per-weight xTP files...")
        for weight in WEIGHTS:
            print(f"  Rebuilding weight {weight}...")
            rebuild_weight_xtp(
                args.season,
                weight,
                args.rankings_dir,
                args.wrestlers_dir,
                args.data_dir
            )
        print()
    
    # Aggregate team xTP
    teams = aggregate_team_xtp(args.season, args.data_dir)
    
    if not teams:
        print("No team data found. Run with --rebuild-weights to generate per-weight xTP files.")
        return
    
    # Validate
    print(f"\nValidating team data...")
    if not validate_team_data(teams):
        print("Warning: Some validation checks failed")
    
    # Write JSON
    write_team_xtp_json(teams, args.season, args.data_dir)
    
    # Print leaderboard
    print(f"\n{'=' * 80}")
    print_team_leaderboard(teams, limit=args.limit)


if __name__ == "__main__":
    main()

