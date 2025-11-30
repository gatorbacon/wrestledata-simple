#!/usr/bin/env python3
"""
Save rankings from downloaded JSON files to the rankings directory.

After editing rankings in the HTML matrix and downloading the JSON file,
use this script to save it to the proper location.
"""

import json
import shutil
from pathlib import Path
from typing import Dict, List


def save_rankings_file(json_file: Path, season: int, output_dir: str = "mt/rankings_data") -> Path:
    """
    Save a rankings JSON file to the proper location.
    
    Args:
        json_file: Path to downloaded JSON file
        season: Season year
        output_dir: Directory to save rankings
        
    Returns:
        Path to saved file
    """
    # Load the JSON file
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Validate structure
    if 'weight_class' not in data or 'rankings' not in data:
        raise ValueError("Invalid rankings JSON structure. Expected 'weight_class' and 'rankings' keys.")

    weight_class = data['weight_class']

    # Annotate starters: for each team at this weight, the best-ranked
    # wrestler is marked is_starter=True; all other teammates are False.
    rankings: List[Dict] = data.get("rankings", [])
    team_best: Dict[str, int] = {}  # team -> best rank
    team_best_index: Dict[str, int] = {}  # team -> index into rankings

    for idx, entry in enumerate(rankings):
        team = entry.get("team")
        if not team:
            continue
        raw_rank = entry.get("rank")
        try:
            r_int = int(raw_rank)
        except (TypeError, ValueError):
            # Treat missing/invalid rank as very low priority
            r_int = 10**9
        prev_best = team_best.get(team)
        if prev_best is None or r_int < prev_best:
            team_best[team] = r_int
            team_best_index[team] = idx

    # Default everyone to non-starter
    for entry in rankings:
        entry["is_starter"] = False

    # Mark the single best-ranked wrestler per team as the starter
    for team, idx in team_best_index.items():
        if 0 <= idx < len(rankings):
            rankings[idx]["is_starter"] = True

    # Create output directory
    output_path = Path(output_dir) / str(season)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Save to proper location
    rankings_file = output_path / f"rankings_{weight_class}.json"
    
    with open(rankings_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    
    return rankings_file


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Save rankings from downloaded JSON file to rankings directory'
    )
    parser.add_argument('json_file', type=Path, help='Path to downloaded rankings JSON file')
    parser.add_argument('-season', type=int, help='Season year (if not in JSON file)')
    parser.add_argument('-output-dir', default='mt/rankings_data', help='Directory to save rankings')
    args = parser.parse_args()
    
    # Load JSON to get season if not provided
    with open(args.json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    season = args.season or data.get('season')
    if not season:
        raise ValueError("Season not found in JSON file and not provided via -season argument")
    
    saved_file = save_rankings_file(args.json_file, season, args.output_dir)
    print(f"Saved rankings to: {saved_file}")
    print(f"  Weight class: {data['weight_class']}")
    print(f"  Season: {season}")
    print(f"  Wrestlers ranked: {len(data['rankings'])}")

