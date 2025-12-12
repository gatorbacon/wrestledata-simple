#!/usr/bin/env python3
"""
Calculate estimated team scores based on highest ranked wrestler at each weight.

Uses the ranking-to-points mapping:
- Rank 1: 24 points
- Rank 2: 18.5 points
- Rank 3: 17.5 points
- Rank 4: 15 points
- Rank 5: 12 points
- Rank 6: 10.5 points
- Rank 7: 7.5 points
- Rank 8: 5 points
- Rank 9-12: 3 points
- Rank 13-16: 2 points
- Rank 17-24: 1 point
- Rank 25+: 0 points
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# Weight classes in order
WEIGHT_CLASSES = ["125", "133", "141", "149", "157", "165", "174", "184", "197", "285"]


def rank_to_points(rank: int) -> float:
    """Convert a rank to estimated points based on the provided table."""
    if rank >= 25:
        return 0.0
    elif rank >= 17:
        return 1.0
    elif rank >= 13:
        return 2.0
    elif rank >= 9:
        return 3.0
    elif rank == 8:
        return 5.0
    elif rank == 7:
        return 7.5
    elif rank == 6:
        return 10.5
    elif rank == 5:
        return 12.0
    elif rank == 4:
        return 15.0
    elif rank == 3:
        return 17.5
    elif rank == 2:
        return 18.5
    elif rank == 1:
        return 24.0
    else:
        return 0.0


def load_rankings_for_weight(
    season: int, weight: str, data_dir: str
) -> Optional[List[Dict]]:
    """Load rankings_{weight}.json for a weight class, if present."""
    rankings_path = Path(data_dir) / str(season) / f"rankings_{weight}.json"
    if not rankings_path.exists():
        return None
    with rankings_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("rankings", [])


def find_best_wrestler_per_team(rankings: List[Dict]) -> Dict[str, Dict]:
    """
    For each team, find the highest ranked (lowest rank number) starter wrestler.
    Only considers wrestlers marked as starters (is_starter == True).
    Returns dict mapping team -> wrestler entry.
    """
    team_best: Dict[str, Dict] = {}
    
    for entry in rankings:
        # Only consider starters
        if not entry.get("is_starter", False):
            continue
        
        team = entry.get("team")
        if not team:
            continue
        
        rank = entry.get("rank")
        if rank is None:
            continue
        
        try:
            rank_int = int(rank)
        except (TypeError, ValueError):
            continue
        
        # If we haven't seen this team, or this wrestler is ranked better
        if team not in team_best:
            team_best[team] = entry
        else:
            current_best_rank = team_best[team].get("rank")
            try:
                current_rank_int = int(current_best_rank) if current_best_rank else 999
            except (TypeError, ValueError):
                current_rank_int = 999
            
            if rank_int < current_rank_int:
                team_best[team] = entry
    
    return team_best


def calculate_team_scores(season: int, data_dir: str) -> Tuple[Dict[str, float], Dict[str, Dict[str, Dict]]]:
    """
    Calculate team scores and detailed breakdown.
    
    Returns:
        - team_scores: dict mapping team -> total points
        - team_breakdown: dict mapping team -> dict mapping weight -> wrestler entry
    """
    team_scores: Dict[str, float] = defaultdict(float)
    team_breakdown: Dict[str, Dict[str, Dict]] = defaultdict(dict)
    
    for weight in WEIGHT_CLASSES:
        rankings = load_rankings_for_weight(season, weight, data_dir)
        if not rankings:
            continue
        
        # Find best wrestler per team at this weight
        best_per_team = find_best_wrestler_per_team(rankings)
        
        for team, wrestler_entry in best_per_team.items():
            rank = wrestler_entry.get("rank")
            if rank is None:
                continue
            
            try:
                rank_int = int(rank)
            except (TypeError, ValueError):
                continue
            
            points = rank_to_points(rank_int)
            team_scores[team] += points
            team_breakdown[team][weight] = {
                **wrestler_entry,
                "points": points
            }
    
    return dict(team_scores), dict(team_breakdown)


def display_top_teams(team_scores: Dict[str, float], top_n: int = 10) -> List[Tuple[str, float]]:
    """Display top N teams and return them as a list."""
    sorted_teams = sorted(team_scores.items(), key=lambda x: (-x[1], x[0]))
    top_teams = sorted_teams[:top_n]
    
    print(f"\n{'Rank':<6} {'Team':<30} {'Total Points':>12}")
    print("-" * 50)
    
    for idx, (team, score) in enumerate(top_teams, start=1):
        print(f"{idx:<6} {team:<30} {score:>12.1f}")
    
    return top_teams


def display_team_breakdown(team: str, breakdown: Dict[str, Dict], team_score: float):
    """Display detailed breakdown for a specific team."""
    print(f"\n{'='*70}")
    print(f"Team Breakdown: {team}")
    print(f"Total Estimated Points: {team_score:.1f}")
    print(f"{'='*70}")
    print(f"\n{'Weight':<8} {'Wrestler':<30} {'Rank':>6} {'Points':>8}")
    print("-" * 70)
    
    total_points = 0.0
    for weight in WEIGHT_CLASSES:
        if weight in breakdown:
            wrestler = breakdown[weight]
            name = wrestler.get("name", "Unknown")
            rank = wrestler.get("rank", "N/A")
            points = wrestler.get("points", 0.0)
            total_points += points
            print(f"{weight:<8} {name:<30} {rank:>6} {points:>8.1f}")
        else:
            print(f"{weight:<8} {'No ranked wrestler':<30} {'N/A':>6} {0.0:>8.1f}")
    
    print("-" * 70)
    print(f"{'TOTAL':<8} {'':<30} {'':>6} {total_points:>8.1f}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calculate estimated team scores based on highest ranked wrestler at each weight."
    )
    parser.add_argument(
        "-season",
        type=int,
        required=True,
        help="Season year (e.g., 2026)"
    )
    parser.add_argument(
        "-data-dir",
        default="mt/rankings_data",
        help="Directory containing rankings JSON files"
    )
    parser.add_argument(
        "-top-n",
        type=int,
        default=10,
        help="Number of top teams to display initially (default: 10)"
    )
    args = parser.parse_args()
    
    season = args.season
    data_dir = args.data_dir
    
    print(f"Calculating team scores for season {season}...")
    
    # Calculate team scores
    team_scores, team_breakdown = calculate_team_scores(season, data_dir)
    
    if not team_scores:
        print("No team scores found. Check that rankings files exist.")
        return
    
    # Display top teams
    top_teams = display_top_teams(team_scores, args.top_n)
    
    # Create a mapping of team names for easy lookup
    all_teams_sorted = sorted(team_scores.items(), key=lambda x: (-x[1], x[0]))
    team_list = [team for team, _ in all_teams_sorted]
    
    # Interactive breakdown
    while True:
        print(f"\nEnter a number (1-{len(team_list)}) to see a team breakdown, or 'q' to quit: ", end="")
        try:
            user_input = input().strip().lower()
            
            if user_input == 'q' or user_input == 'quit':
                break
            
            team_num = int(user_input)
            if 1 <= team_num <= len(team_list):
                selected_team = team_list[team_num - 1]
                display_team_breakdown(
                    selected_team,
                    team_breakdown.get(selected_team, {}),
                    team_scores.get(selected_team, 0.0)
                )
            else:
                print(f"Please enter a number between 1 and {len(team_list)}")
        except ValueError:
            print("Please enter a valid number or 'q' to quit")
        except KeyboardInterrupt:
            print("\nExiting...")
            break


if __name__ == "__main__":
    main()

