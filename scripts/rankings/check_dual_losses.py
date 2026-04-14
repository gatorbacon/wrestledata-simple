#!/usr/bin/env python3
"""
Diagnostic script to check which teams a specific team loses to in dual rankings.

This helps verify that dual rankings match the dual simulation logic.
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple

# Import the same functions used in generate_dual_predictor_data.py
# Add parent directory to path so we can import from scripts.rankings
import sys
from pathlib import Path
script_dir = Path(__file__).parent
project_root = script_dir.parent.parent
sys.path.insert(0, str(project_root))

from scripts.rankings.generate_dual_predictor_data import (
    load_team_rosters,
    load_rankings_by_weight,
    load_elo_data,
    simulate_dual_meet,
    get_weights_for_gender,
    load_boys_inactive_mask
)


def find_team_losses(
    team_name: str,
    season: int,
    gender: str,
    teams_dir: Path,
    data_dir: str = "mt/rankings_data"
) -> Tuple[List[str], List[str], List[str]]:
    """
    Find which teams the specified team loses to, beats, and ties.
    
    Returns:
        Tuple of (losses, wins, ties) - each is a list of team names
    """
    print(f"\nAnalyzing dual matchups for: {team_name}")
    print(f"Season: {season}, Gender: {gender}")
    print("=" * 70)
    
    # Load data (same as generate_dual_predictor_data.py)
    masked_wrestler_ids = set()
    if gender == 'boys':
        masked_wrestler_ids = load_boys_inactive_mask(season, data_dir)
    
    rankings_by_weight = load_rankings_by_weight(season, gender, data_dir)
    elo_by_id = load_elo_data(season, gender)
    all_rosters = load_team_rosters(season, gender, teams_dir, rankings_by_weight, elo_by_id, masked_wrestler_ids)
    
    # Find target team - check both team name and team_slug
    target_team = None
    team_name_lower = team_name.lower()
    
    for team_slug, roster in all_rosters.items():
        roster_team_name = roster.get("team", "")
        if team_name_lower in roster_team_name.lower() or team_name_lower in team_slug.lower():
            target_team = team_slug
            break
    
    if not target_team:
        print(f"ERROR: Team '{team_name}' not found!")
        # Show some example team names
        example_teams = sorted([(r.get("team", ""), slug) for slug, r in list(all_rosters.items())[:20]])
        print(f"Example teams (first 20):")
        for name, slug in example_teams:
            if name:
                print(f"  - {name} (slug: {slug})")
        return [], [], []
    
    target_roster = all_rosters[target_team]
    print(f"Found team: {target_roster.get('team', target_team)}")
    
    # Simulate matchups against all other teams
    wins = []
    losses = []
    ties = []
    
    team_names = sorted(all_rosters.keys())
    weights = get_weights_for_gender(gender)
    
    print(f"\nSimulating {len(team_names) - 1} matchups...")
    
    for opponent_slug in team_names:
        if opponent_slug == target_team:
            continue
        
        opponent_roster = all_rosters[opponent_slug]
        opponent_name = opponent_roster.get("team", opponent_slug)
        
        # Simulate dual meet
        score_a, score_b = simulate_dual_meet(
            target_team,
            opponent_slug,
            all_rosters,
            gender
        )
        
        if score_a > score_b:
            wins.append(opponent_name)
        elif score_b > score_a:
            losses.append(opponent_name)
        else:
            ties.append(opponent_name)
    
    return losses, wins, ties


def main():
    parser = argparse.ArgumentParser(description="Check which teams a team loses to in dual rankings")
    parser.add_argument("--team", required=True, help="Team name (partial match OK)")
    parser.add_argument("--season", type=int, required=True, help="Season year")
    parser.add_argument("--gender", choices=["boys", "girls"], default="boys", help="Gender")
    parser.add_argument("--teams-dir", type=Path, default=Path("frontend/hs-ky-ui/public/data/teams"), help="Teams data directory")
    parser.add_argument("--data-dir", default="mt/rankings_data", help="Rankings data directory")
    
    args = parser.parse_args()
    
    losses, wins, ties = find_team_losses(
        args.team,
        args.season,
        args.gender,
        args.teams_dir,
        args.data_dir
    )
    
    print("\n" + "=" * 70)
    print(f"RESULTS for {args.team.upper()}")
    print("=" * 70)
    print(f"\nWins: {len(wins)}")
    print(f"Losses: {len(losses)}")
    print(f"Ties: {len(ties)}")
    
    if losses:
        print(f"\n❌ LOSES TO ({len(losses)} teams):")
        for i, team in enumerate(losses, 1):
            print(f"  {i:2d}. {team}")
    
    if ties:
        print(f"\n🤝 TIES ({len(ties)} teams):")
        for i, team in enumerate(ties, 1):
            print(f"  {i:2d}. {team}")
    
    if wins:
        print(f"\n✅ WINS ({len(wins)} teams):")
        # Only show first 10 wins to avoid clutter
        for i, team in enumerate(wins[:10], 1):
            print(f"  {i:2d}. {team}")
        if len(wins) > 10:
            print(f"  ... and {len(wins) - 10} more")
    
    print("\n" + "=" * 70)
    print("To verify:")
    print("  1. Go to /dual_predictor.html")
    print("  2. Select this team vs each team listed above")
    print("  3. Use default lineup (don't change wrestlers)")
    print("  4. Verify the result matches (loss/win/tie)")
    print("=" * 70)


if __name__ == "__main__":
    main()

