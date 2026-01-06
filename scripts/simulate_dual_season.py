#!/usr/bin/env python3
"""
Simulate all possible dual meet matchups for a season.
Uses the same logic as the dual predictor to determine winners and scores.
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import sys

# HS weight classes
HS_WEIGHTS = {
    'boys': [106, 113, 120, 126, 132, 138, 144, 150, 157, 165, 175, 190, 215, 285],
    'girls': [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235]
}

def get_weights_for_gender(gender: str) -> List[int]:
    """Get weight classes for a gender."""
    return HS_WEIGHTS.get(gender, HS_WEIGHTS['boys'])

def load_rankings_data(season: int, gender: str, data_dir: Path) -> Dict[int, List[Dict]]:
    """Load full rankings data for all weight classes."""
    rankings_by_weight = {}
    weights = get_weights_for_gender(gender)
    
    # Try loading from full rankings first (public location)
    rankings_full_dir = data_dir / 'rankings_full' / gender / str(season)
    
    # Fallback: try source location (mt/rankings_data)
    source_dir = Path('mt/rankings_data') / f'hs_ky_{gender}' / str(season)
    
    for weight in weights:
        rankings_file = None
        
        # Try public location first
        if (rankings_full_dir / f'{weight}.json').exists():
            rankings_file = rankings_full_dir / f'{weight}.json'
        # Fallback to source location
        elif (source_dir / f'rankings_{weight}.json').exists():
            rankings_file = source_dir / f'rankings_{weight}.json'
        
        if rankings_file and rankings_file.exists():
            try:
                with open(rankings_file, 'r') as f:
                    data = json.load(f)
                    if 'rankings' in data:
                        rankings_by_weight[weight] = data['rankings']
                    elif isinstance(data, list):
                        rankings_by_weight[weight] = data
                    else:
                        rankings_by_weight[weight] = []
            except Exception as e:
                print(f"Warning: Could not load rankings for {weight}: {e}", file=sys.stderr)
                rankings_by_weight[weight] = []
        else:
            rankings_by_weight[weight] = []
    
    # Fallback: Load from wrestler profiles if rankings files don't exist
    if not any(rankings_by_weight.values()):
        print("No full rankings found, loading from wrestler profiles...", file=sys.stderr)
        wrestlers_dir = data_dir / 'wrestlers' / gender / str(season) / 'by_id'
        
        if wrestlers_dir.exists():
            for profile_file in wrestlers_dir.glob('*.json'):
                try:
                    with open(profile_file, 'r') as f:
                        profile = json.load(f)
                        weight = profile.get('weight_class')
                        rank = profile.get('current_rank')
                        wrestler_id = profile.get('wrestler_id')
                        name = profile.get('name')
                        team = profile.get('team')
                        
                        if weight and wrestler_id and rank:
                            weight_int = int(weight)
                            if weight_int in weights:
                                if weight_int not in rankings_by_weight:
                                    rankings_by_weight[weight_int] = []
                                rankings_by_weight[weight_int].append({
                                    'wrestler_id': str(wrestler_id),
                                    'name': name,
                                    'team': team,
                                    'rank': rank,
                                    'is_highest_ranked': profile.get('is_highest_ranked', False)
                                })
                except Exception as e:
                    continue
    
    # Sort each weight class by rank
    for weight in rankings_by_weight:
        rankings_by_weight[weight].sort(key=lambda x: (x.get('rank') or 9999, x.get('name', '')))
    
    return rankings_by_weight

def load_team_rosters(season: int, gender: str, data_dir: Path, rankings_by_weight: Dict[int, List[Dict]]) -> Dict[str, Dict]:
    """Load team rosters organized by weight class."""
    team_rosters = {}
    weights = get_weights_for_gender(gender)
    
    # Build roster from rankings data
    for weight, wrestlers in rankings_by_weight.items():
        for wrestler in wrestlers:
            team_name = wrestler.get('team')
            if not team_name:
                continue
            
            if team_name not in team_rosters:
                team_rosters[team_name] = {'weights': {}}
            
            if weight not in team_rosters[team_name]['weights']:
                team_rosters[team_name]['weights'][weight] = []
            
            team_rosters[team_name]['weights'][weight].append({
                'wrestler_id': wrestler['wrestler_id'],
                'name': wrestler.get('name', ''),
                'rank': wrestler.get('rank'),
                'is_highest_ranked': wrestler.get('is_highest_ranked', False)
            })
    
    # Load ALL wrestlers from index_teams.json (includes unranked wrestlers)
    index_teams_file = data_dir / 'wrestlers' / gender / str(season) / 'index_teams.json'
    
    if index_teams_file.exists():
        try:
            with open(index_teams_file, 'r') as f:
                index_data = json.load(f)
            
            def normalize_team_name(name: str) -> str:
                if not name:
                    return ''
                return name.lower().replace(' ', '_').replace('-', '_')
            
            for team_entry in index_data:
                if not team_entry.get('roster') or not team_entry.get('team_slug'):
                    continue
                
                team_slug = team_entry['team_slug']
                normalized_slug = normalize_team_name(team_slug)
                
                # Find team name by matching slug
                team_name = None
                for existing_team_name in team_rosters.keys():
                    if normalize_team_name(existing_team_name) == normalized_slug:
                        team_name = existing_team_name
                        break
                
                # If not found, try loading team profile
                if not team_name:
                    team_profile_file = data_dir / 'teams' / gender / str(season) / f'{team_slug}.json'
                    if team_profile_file.exists():
                        try:
                            with open(team_profile_file, 'r') as f:
                                team_data = json.load(f)
                                team_name = team_data.get('team_name') or team_data.get('name')
                        except Exception:
                            continue
                
                if not team_name:
                    continue
                
                if team_name not in team_rosters:
                    team_rosters[team_name] = {'weights': {}}
                
                # Load wrestler profiles to get weight classes
                for wrestler_id in team_entry['roster']:
                    if not wrestler_id or str(wrestler_id).startswith('OUTSTATE_'):
                        continue
                    
                    try:
                        profile_file = data_dir / 'wrestlers' / gender / str(season) / 'by_id' / f'{wrestler_id}.json'
                        if profile_file.exists():
                            with open(profile_file, 'r') as f:
                                profile = json.load(f)
                                weight = profile.get('weight_class')
                                if weight:
                                    weight_int = int(weight)
                                    if weight_int in weights:
                                        if weight_int not in team_rosters[team_name]['weights']:
                                            team_rosters[team_name]['weights'][weight_int] = []
                                        
                                        # Check if wrestler already added
                                        wrestler_exists = any(
                                            w['wrestler_id'] == str(wrestler_id)
                                            for w in team_rosters[team_name]['weights'][weight_int]
                                        )
                                        
                                        if not wrestler_exists:
                                            team_rosters[team_name]['weights'][weight_int].append({
                                                'wrestler_id': str(wrestler_id),
                                                'name': profile.get('name', ''),
                                                'rank': profile.get('current_rank'),
                                                'is_highest_ranked': profile.get('is_highest_ranked', False)
                                            })
                    except Exception:
                        continue
        except Exception as e:
            print(f"Warning: Could not load index_teams.json: {e}", file=sys.stderr)
    
    return team_rosters

def get_starter(wrestlers: List[Dict]) -> Optional[Dict]:
    """Get the starter (highest-ranked wrestler) from a list."""
    if not wrestlers:
        return None
    
    # Find highest-ranked wrestler (lowest rank number)
    starter = None
    for w in wrestlers:
        if w.get('is_highest_ranked'):
            return w
    
    # If no is_highest_ranked flag, use highest ranked
    sorted_wrestlers = sorted(
        [w for w in wrestlers if w.get('rank') is not None],
        key=lambda x: x.get('rank', 9999)
    )
    
    return sorted_wrestlers[0] if sorted_wrestlers else wrestlers[0]

def get_highest_ranked_non_starter_from_weight_below(
    roster: Dict,
    weight: int,
    all_weights: List[int],
    weight_index: int
) -> Optional[Dict]:
    """Get highest-ranked non-starter from the weight class below."""
    if weight_index >= len(all_weights) - 1:
        return None
    
    weight_below = all_weights[weight_index + 1]
    wrestlers_below = roster['weights'].get(weight_below, [])
    
    if not wrestlers_below:
        return None
    
    # Filter out starters
    non_starters = [w for w in wrestlers_below if not w.get('is_highest_ranked', False)]
    
    if not non_starters:
        return None
    
    # Find highest-ranked non-starter (lowest rank number)
    sorted_non_starters = sorted(
        [w for w in non_starters if w.get('rank') is not None],
        key=lambda x: x.get('rank', 9999)
    )
    
    if sorted_non_starters:
        result = sorted_non_starters[0].copy()
        result['source_weight'] = weight_below
        return result
    
    return None

def get_default_wrestler(
    roster: Dict,
    weight: int,
    all_weights: List[int],
    weight_index: int
) -> Optional[Dict]:
    """Get default wrestler for a weight class using dual predictor logic."""
    # Priority: 1) Starter at current weight, 2) Highest non-starter from below, 3) None (forfeit)
    wrestlers_at_weight = roster['weights'].get(weight, [])
    starter = get_starter(wrestlers_at_weight)
    
    if starter:
        return starter
    
    # Try to get non-starter from weight below
    non_starter_below = get_highest_ranked_non_starter_from_weight_below(
        roster, weight, all_weights, weight_index
    )
    
    if non_starter_below:
        return non_starter_below
    
    return None

def adjust_rank_for_weight_class(rank: Optional[int], actual_weight: int, matchup_weight: int) -> Optional[float]:
    """Adjust rank based on weight class difference."""
    if rank is None:
        return None
    
    actual_weight_num = int(actual_weight)
    matchup_weight_num = int(matchup_weight)
    
    # If wrestler is from weight class below, add 2.5 to rank
    if actual_weight_num < matchup_weight_num:
        return rank + 2.5
    
    # If wrestler is from weight class above or same, use rank as-is
    return float(rank)

def calculate_points_for_rank_difference(rank_diff: float, gender: str) -> int:
    """Calculate match points based on rank difference."""
    rank_diff_int = int(rank_diff)
    
    if gender == 'boys':
        if 1 <= rank_diff_int <= 7:
            return 3  # Regular decision
        elif 8 <= rank_diff_int <= 14:
            return 4  # Major decision
        elif rank_diff_int >= 15:
            return 6  # Fall
    elif gender == 'girls':
        if 1 <= rank_diff_int <= 4:
            return 3  # Regular decision
        elif 5 <= rank_diff_int <= 8:
            return 4  # Major decision
        elif rank_diff_int >= 9:
            return 6  # Fall
    
    # Default to regular decision
    return 3

def simulate_dual_meet(
    team_a: str,
    team_b: str,
    team_rosters: Dict[str, Dict],
    rankings_by_weight: Dict[int, List[Dict]],
    gender: str
) -> Tuple[int, int]:
    """Simulate a dual meet between two teams. Returns (score_a, score_b)."""
    weights = get_weights_for_gender(gender)
    roster_a = team_rosters.get(team_a, {'weights': {}})
    roster_b = team_rosters.get(team_b, {'weights': {}})
    
    score_a = 0
    score_b = 0
    
    for weight_index, weight in enumerate(weights):
        # Get default wrestlers
        wrestler_a = get_default_wrestler(roster_a, weight, weights, weight_index)
        wrestler_b = get_default_wrestler(roster_b, weight, weights, weight_index)
        
        # Handle forfeits
        if not wrestler_a and not wrestler_b:
            # Both forfeit - skip
            continue
        elif not wrestler_a:
            # Team A forfeits
            score_b += 6
            continue
        elif not wrestler_b:
            # Team B forfeits
            score_a += 6
            continue
        
        # Get wrestler info
        rank_a = wrestler_a.get('rank')
        rank_b = wrestler_b.get('rank')
        actual_weight_a = wrestler_a.get('source_weight', weight)
        actual_weight_b = wrestler_b.get('source_weight', weight)
        
        # Adjust ranks
        adjusted_rank_a = adjust_rank_for_weight_class(rank_a, actual_weight_a, weight)
        adjusted_rank_b = adjust_rank_for_weight_class(rank_b, actual_weight_b, weight)
        
        # Determine winner and points
        if adjusted_rank_a is None and adjusted_rank_b is None:
            # Both unranked - default to Team A, regular decision
            score_a += 3
        elif adjusted_rank_a is None:
            # Team A unranked
            score_b += 3
        elif adjusted_rank_b is None:
            # Team B unranked
            score_a += 3
        else:
            # Both ranked - determine winner
            rank_diff = abs(adjusted_rank_a - adjusted_rank_b)
            
            if adjusted_rank_a < adjusted_rank_b:
                # Team A wins
                points = calculate_points_for_rank_difference(rank_diff, gender)
                score_a += points
            elif adjusted_rank_b < adjusted_rank_a:
                # Team B wins
                points = calculate_points_for_rank_difference(rank_diff, gender)
                score_b += points
            else:
                # Tie - default to Team A, regular decision
                score_a += 3
    
    return score_a, score_b

def main():
    parser = argparse.ArgumentParser(description='Simulate all dual meet matchups for a season')
    parser.add_argument('-season', type=int, required=True, help='Season year (e.g., 2026)')
    parser.add_argument('-league', type=str, default='hs', help='League (default: hs)')
    parser.add_argument('-state', type=str, default='KY', help='State (default: KY)')
    parser.add_argument('-gender', type=str, required=True, choices=['boys', 'girls'], help='Gender')
    parser.add_argument('--data-dir', type=str, default='frontend/hs-ky-ui/public/data', help='Data directory')
    
    args = parser.parse_args()
    
    if args.league != 'hs':
        print("Error: This script only supports HS league", file=sys.stderr)
        sys.exit(1)
    
    data_dir = Path(args.data_dir)
    
    print(f"Loading rankings data for {args.gender} {args.season}...")
    rankings_by_weight = load_rankings_data(args.season, args.gender, data_dir)
    
    print(f"Loading team rosters...")
    team_rosters = load_team_rosters(args.season, args.gender, data_dir, rankings_by_weight)
    
    team_names = sorted(team_rosters.keys())
    print(f"Found {len(team_names)} teams")
    
    # Track records
    records = defaultdict(lambda: {'wins': 0, 'losses': 0, 'ties': 0, 'points_for': 0, 'points_against': 0})
    
    print(f"\nSimulating {len(team_names) * (len(team_names) - 1) // 2} dual meets...")
    
    # Simulate all pairwise matchups
    for i, team_a in enumerate(team_names):
        for team_b in team_names[i+1:]:
            score_a, score_b = simulate_dual_meet(
                team_a, team_b, team_rosters, rankings_by_weight, args.gender
            )
            
            records[team_a]['points_for'] += score_a
            records[team_a]['points_against'] += score_b
            records[team_b]['points_for'] += score_b
            records[team_b]['points_against'] += score_a
            
            if score_a > score_b:
                records[team_a]['wins'] += 1
                records[team_b]['losses'] += 1
            elif score_b > score_a:
                records[team_b]['wins'] += 1
                records[team_a]['losses'] += 1
            else:
                records[team_a]['ties'] += 1
                records[team_b]['ties'] += 1
    
    # Sort by record (wins, then win percentage, then point differential)
    def sort_key(team):
        rec = records[team]
        total_games = rec['wins'] + rec['losses'] + rec['ties']
        win_pct = rec['wins'] / total_games if total_games > 0 else 0
        point_diff = rec['points_for'] - rec['points_against']
        return (-rec['wins'], -win_pct, -point_diff)
    
    sorted_teams = sorted(team_names, key=sort_key)
    
    # Print results
    print(f"\n{'='*80}")
    print(f"SEASON SIMULATION RESULTS - {args.gender.upper()} {args.season}")
    print(f"{'='*80}")
    print(f"{'Rank':<6} {'Team':<30} {'W':<4} {'L':<4} {'T':<4} {'PF':<6} {'PA':<6} {'PD':<6} {'Win%':<6}")
    print(f"{'-'*80}")
    
    for rank, team in enumerate(sorted_teams, 1):
        rec = records[team]
        total_games = rec['wins'] + rec['losses'] + rec['ties']
        win_pct = rec['wins'] / total_games if total_games > 0 else 0
        point_diff = rec['points_for'] - rec['points_against']
        
        print(f"{rank:<6} {team:<30} {rec['wins']:<4} {rec['losses']:<4} {rec['ties']:<4} "
              f"{rec['points_for']:<6} {rec['points_against']:<6} {point_diff:<6} {win_pct:.3f}")

if __name__ == '__main__':
    main()

