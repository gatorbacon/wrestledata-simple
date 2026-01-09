#!/usr/bin/env python3
"""
Initialize Wrestler Match Tracking File

This script reviews existing scraped team data and populates the initial
wrestler match tracking JSON file, indicating which wrestlers have ever had
at least one valid match this season.

Usage:
    python scripts/initialize_wrestler_match_tracking.py --season 2026 --league hs --state KY --gender boys
"""

import argparse
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Set


def is_valid_match(match: Dict) -> bool:
    """
    Determine if a match is valid (should be counted).
    
    Excludes:
    - BYE matches
    - NoResult matches
    - Matches with "received a bye" in summary
    """
    result = match.get("result", "").strip()
    summary = match.get("summary", "").strip().lower()
    
    # Skip BYE and NoResult
    if result in ("BYE", "NoResult"):
        return False
    
    # Skip matches with "received a bye" in summary
    if "received a bye" in summary:
        return False
    
    return True


def load_existing_scraped_data(season: int, league: str, state: str = None, gender: str = None) -> Dict[str, bool]:
    """
    Load all existing scraped team data and determine which wrestlers have had matches.
    
    Returns:
        Dict mapping wrestler_id -> has_ever_had_matches (bool)
    """
    wrestler_match_history: Dict[str, bool] = {}
    
    # Determine data directory based on league
    if league == 'hs':
        if not state or not gender:
            raise ValueError("--state and --gender are required when --league=hs")
        state_lower = state.lower()
        data_dir = Path(f"mt/data/hs_{state_lower}_{gender}")
    else:  # ncaa
        data_dir = Path(f"mt/data/{season}")
    
    if not data_dir.exists():
        print(f"Warning: Data directory not found: {data_dir}")
        return wrestler_match_history
    
    print(f"Scanning scraped data in: {data_dir}")
    
    team_files = sorted(data_dir.glob("*.json"))
    print(f"Found {len(team_files)} team files")
    
    for team_file in team_files:
        try:
            with open(team_file, 'r', encoding='utf-8') as f:
                team_data = json.load(f)
            
            team_name = team_data.get("team_name", "Unknown")
            roster = team_data.get("roster", [])
            
            for wrestler in roster:
                wrestler_id = wrestler.get("season_wrestler_id")
                if not wrestler_id:
                    continue
                
                matches = wrestler.get("matches", [])
                
                # Count valid matches
                valid_match_count = sum(1 for m in matches if is_valid_match(m))
                
                # Update tracking: if wrestler has any valid matches, mark as having had matches
                if wrestler_id not in wrestler_match_history:
                    wrestler_match_history[wrestler_id] = (valid_match_count > 0)
                else:
                    # If we've seen this wrestler before and they have matches now, upgrade to True
                    if valid_match_count > 0:
                        wrestler_match_history[wrestler_id] = True
                    # If False, keep it False (don't downgrade if they had matches before)
                    # This handles the case where a wrestler appears in multiple team files
            
        except Exception as e:
            print(f"Error processing {team_file}: {e}")
            continue
    
    return wrestler_match_history


def create_tracking_file(
    season: int,
    league: str,
    state: str = None,
    gender: str = None,
    wrestler_match_history: Dict[str, bool] = None
) -> Path:
    """
    Create the wrestler match tracking file.
    
    Returns:
        Path to the created tracking file
    """
    # Create tracking directory
    tracking_dir = Path("mt/tracking")
    tracking_dir.mkdir(parents=True, exist_ok=True)
    
    # Build filename
    if league == 'hs':
        if not state or not gender:
            raise ValueError("state and gender are required for HS")
        filename = f"wrestler_match_history_{season}_hs_{state.lower()}_{gender}.json"
    else:  # ncaa
        filename = f"wrestler_match_history_{season}_ncaa.json"
    
    tracking_file = tracking_dir / filename
    
    # Build tracking structure
    tracking_data = {
        "season": season,
        "league": league,
        "state": state,
        "gender": gender,
        "initialized_at": datetime.now().isoformat(),
        "wrestlers": {}
    }
    
    # Populate wrestler data
    if wrestler_match_history:
        for wrestler_id, has_ever_had_matches in wrestler_match_history.items():
            if has_ever_had_matches:
                tracking_data["wrestlers"][wrestler_id] = {
                    "has_ever_had_matches": True,
                    "first_seen_with_matches": datetime.now().isoformat(),
                    "last_verified_with_matches": datetime.now().isoformat()
                }
            else:
                tracking_data["wrestlers"][wrestler_id] = {
                    "has_ever_had_matches": False,
                    "first_seen_zero_matches": datetime.now().isoformat()
                }
    
    # Write tracking file
    with open(tracking_file, 'w', encoding='utf-8') as f:
        json.dump(tracking_data, f, indent=2, ensure_ascii=False)
    
    return tracking_file


def main():
    parser = argparse.ArgumentParser(
        description="Initialize wrestler match tracking file from existing scraped data"
    )
    parser.add_argument("--season", type=int, required=True, help="Season year (e.g., 2026)")
    parser.add_argument("--league", type=str, default='ncaa', choices=['ncaa', 'hs'],
                        help='League type: ncaa (default) or hs')
    parser.add_argument("--state", type=str, help='State code (required when league=hs)')
    parser.add_argument("--gender", type=str, choices=['boys', 'girls'],
                        help='Gender: boys or girls (required when league=hs)')
    
    args = parser.parse_args()
    
    # Validate HS parameters
    if args.league == 'hs':
        if not args.state:
            raise ValueError("--state is required when --league=hs")
        if not args.gender:
            raise ValueError("--gender is required when --league=hs")
    
    print(f"\n{'='*60}")
    print(f"Initializing Wrestler Match Tracking")
    print(f"{'='*60}")
    print(f"Season: {args.season}")
    print(f"League: {args.league}")
    if args.league == 'hs':
        print(f"State: {args.state}")
        print(f"Gender: {args.gender}")
    print()
    
    # Load existing scraped data
    print("Loading existing scraped data...")
    wrestler_match_history = load_existing_scraped_data(
        args.season,
        args.league,
        args.state,
        args.gender
    )
    
    print(f"\nFound {len(wrestler_match_history)} unique wrestlers")
    wrestlers_with_matches = sum(1 for v in wrestler_match_history.values() if v)
    wrestlers_without_matches = len(wrestler_match_history) - wrestlers_with_matches
    print(f"  - {wrestlers_with_matches} wrestlers with at least one valid match")
    print(f"  - {wrestlers_without_matches} wrestlers with zero valid matches")
    
    # Create tracking file
    print("\nCreating tracking file...")
    tracking_file = create_tracking_file(
        args.season,
        args.league,
        args.state,
        args.gender,
        wrestler_match_history
    )
    
    print(f"\n✅ Tracking file created: {tracking_file}")
    print(f"   Contains {len(wrestler_match_history)} wrestler entries")


if __name__ == "__main__":
    main()

