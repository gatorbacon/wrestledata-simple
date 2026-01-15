#!/usr/bin/env python3
"""
Generate Season Accomplishment JSON files.

This script creates a clean, authoritative summary of what each wrestler
accomplished in a given season. This is the foundation for historical seasons
and future career linking.

Output: data/season_accomplishments/{gender}/{season}/season_accomplishments.json
"""

import json
import argparse
import re
from pathlib import Path
from typing import Dict, List, Optional, Set
from collections import defaultdict
from datetime import datetime


def parse_grade(grade_str: Optional[str]) -> Optional[int]:
    """
    Parse grade string to integer.
    
    Handles all grade formats found in scraped data:
    - "6th", "7th", "8th" → 6, 7, 8
    - "Fr." → 9 (Freshman)
    - "So." → 10 (Sophomore)
    - "Jr." → 11 (Junior)
    - "Sr." → 12 (Senior)
    - Empty/null → None
    """
    if not grade_str:
        return None
    
    grade_str = grade_str.strip()
    
    # Handle numeric grades (6th, 7th, 8th)
    if grade_str.endswith('th'):
        try:
            return int(grade_str[:-2])
        except ValueError:
            pass
    
    # Handle high school grades
    grade_map = {
        'Fr.': 9,
        'So.': 10,
        'Jr.': 11,
        'Sr.': 12,
        'Freshman': 9,
        'Sophomore': 10,
        'Junior': 11,
        'Senior': 12,
    }
    
    return grade_map.get(grade_str, None)


def parse_date(date_str: str) -> Optional[datetime]:
    """
    Parse date string to datetime object.
    
    Handles formats like "11/30/2024", "12/07/2024", etc.
    """
    if not date_str:
        return None
    
    try:
        # Try MM/DD/YYYY format
        return datetime.strptime(date_str, "%m/%d/%Y")
    except ValueError:
        try:
            # Try YYYY-MM-DD format
            return datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return None


def is_valid_match(match: Dict, wrestler_name: str, team_name: str) -> bool:
    """
    Check if a match is valid (not BYE, not NoResult).
    
    Args:
        match: Match dictionary
        wrestler_name: Wrestler's name
        team_name: Wrestler's team name
        
    Returns:
        True if match is valid, False otherwise
    """
    result = match.get('result', '')
    summary = match.get('summary', '').lower()
    
    # Skip BYE matches
    if result == 'BYE' or 'received a bye' in summary:
        return False
    
    # Skip NoResult matches
    if result == 'NoResult':
        return False
    
    return True


def calculate_record(matches: List[Dict], wrestler_name: str, team_name: str) -> Dict[str, int]:
    """
    Calculate wins and losses from matches.
    
    Args:
        matches: List of match dictionaries
        wrestler_name: Wrestler's name
        team_name: Wrestler's team name
        
    Returns:
        Dictionary with 'wins' and 'losses' counts
    """
    wins = 0
    losses = 0
    
    for match in matches:
        if not is_valid_match(match, wrestler_name, team_name):
            continue
        
        winner_name = match.get('winner_name', '')
        loser_name = match.get('loser_name', '')
        winner_team = match.get('winner_team', '')
        loser_team = match.get('loser_team', '')
        
        # Check if this wrestler won
        if winner_name == wrestler_name and winner_team == team_name:
            wins += 1
        # Check if this wrestler lost
        elif loser_name == wrestler_name and loser_team == team_name:
            losses += 1
    
    return {'wins': wins, 'losses': losses}


def get_final_weight(matches: List[Dict], wrestler_name: str, team_name: str) -> Optional[int]:
    """
    Get the weight class of the wrestler's last match of the season.
    
    Args:
        matches: List of match dictionaries
        wrestler_name: Wrestler's name
        team_name: Wrestler's team name
        
    Returns:
        Weight class as integer, or None if no valid matches
    """
    valid_matches = []
    
    for match in matches:
        if not is_valid_match(match, wrestler_name, team_name):
            continue
        
        date_str = match.get('date', '')
        weight_str = match.get('weight', '')
        
        if not date_str or not weight_str:
            continue
        
        date_obj = parse_date(date_str)
        if not date_obj:
            continue
        
        try:
            weight = int(weight_str)
            valid_matches.append((date_obj, weight))
        except (ValueError, TypeError):
            continue
    
    if not valid_matches:
        return None
    
    # Sort by date and get the last one
    valid_matches.sort(key=lambda x: x[0])
    return valid_matches[-1][1]


def parse_placement_from_match(match: Dict, wrestler_name: str, team_name: str) -> Optional[int]:
    """
    Parse placement from a placement match.
    
    Placement matches:
    - "1st Place Match": winner = 1st, loser = 2nd
    - "3rd Place Match": winner = 3rd, loser = 4th
    - "5th Place Match": winner = 5th, loser = 6th (state only)
    - "7th Place Match": winner = 7th, loser = 8th (state only)
    
    Args:
        match: Match dictionary
        wrestler_name: Wrestler's name
        team_name: Wrestler's team name
        
    Returns:
        Placement (1-8) or None if not a placement match or wrestler not involved
    """
    summary = match.get('summary', '')
    winner_name = match.get('winner_name', '')
    loser_name = match.get('loser_name', '')
    winner_team = match.get('winner_team', '')
    loser_team = match.get('loser_team', '')
    
    # Check if this is a placement match
    if '1st Place Match' in summary:
        if winner_name == wrestler_name and winner_team == team_name:
            return 1
        elif loser_name == wrestler_name and loser_team == team_name:
            return 2
    elif '3rd Place Match' in summary:
        if winner_name == wrestler_name and winner_team == team_name:
            return 3
        elif loser_name == wrestler_name and loser_team == team_name:
            return 4
    elif '5th Place Match' in summary:
        if winner_name == wrestler_name and winner_team == team_name:
            return 5
        elif loser_name == wrestler_name and loser_team == team_name:
            return 6
    elif '7th Place Match' in summary:
        if winner_name == wrestler_name and winner_team == team_name:
            return 7
        elif loser_name == wrestler_name and loser_team == team_name:
            return 8
    
    return None


def check_postseason_qualification_and_placement(matches: List[Dict], wrestler_name: str, team_name: str) -> Dict:
    """
    Check if wrestler qualified for regional/state tournaments and determine placement.
    
    For 2025 season, event names are:
    - Regional tournaments: "KHSAA Region <1-8>" (e.g., "KHSAA Region 1")
    - State tournament: "KHSAA State Championship"
    
    Args:
        matches: List of match dictionaries
        wrestler_name: Wrestler's name
        team_name: Wrestler's team name
        
    Returns:
        Dictionary with qualification flags and placements
    """
    regional_qualifier = False
    state_qualifier = False
    regional_place = None
    state_place = None
    
    for match in matches:
        event = match.get('event', '')
        
        # Check for regional qualification and placement
        if 'KHSAA Region' in event:
            if re.search(r'KHSAA Region\s+[1-8]', event, re.IGNORECASE):
                regional_qualifier = True
                # Check for placement match
                placement = parse_placement_from_match(match, wrestler_name, team_name)
                if placement is not None and placement <= 4:  # Regionals only place top 4
                    if regional_place is None or placement < regional_place:
                        regional_place = placement
        
        # Check for state championship and placement
        if 'KHSAA State Championship' in event:
            state_qualifier = True
            # Check for placement match
            placement = parse_placement_from_match(match, wrestler_name, team_name)
            if placement is not None:
                if state_place is None or placement < state_place:
                    state_place = placement
    
    return {
        'regional_qualifier': regional_qualifier,
        'regional_place': regional_place,
        'state_qualifier': state_qualifier,
        'state_place': state_place,
        'state_champion': state_place == 1
    }


def process_season(season: int, gender: str, state: str = 'ky') -> Dict:
    """
    Process a season and generate accomplishment records.
    
    Args:
        season: Season year (e.g., 2025)
        gender: Gender ('boys' or 'girls')
        state: State code (default 'ky')
        
    Returns:
        Dictionary with season, gender, and wrestlers list
    """
    # Setup paths - use processed data as single source of truth
    state_lower = state.lower()
    data_dir = Path(f"mt/processed_data/hs_{state_lower}_{gender}/{season}")
    
    if not data_dir.exists():
        raise FileNotFoundError(f"Processed data directory not found: {data_dir}")
    
    # Track wrestlers by ID (in case they appear on multiple teams)
    wrestlers_by_id: Dict[str, Dict] = {}
    wrestler_match_counts: Dict[str, int] = defaultdict(int)
    
    # Process all team files from processed data
    team_files = sorted(data_dir.glob("*.json"))
    print(f"Processing {len(team_files)} team files...")
    
    for team_file in team_files:
        try:
            with open(team_file, 'r', encoding='utf-8') as f:
                team_data = json.load(f)
        except Exception as e:
            print(f"⚠️  Warning: Could not load {team_file}: {e}")
            continue
        
        team_name = team_data.get('team_name', 'Unknown')
        
        for wrestler in team_data.get('roster', []):
            wrestler_id = wrestler.get('season_wrestler_id')
            wrestler_name = wrestler.get('name', 'Unknown')
            grade_str = wrestler.get('grade', '')
            matches = wrestler.get('matches', [])
            
            # Skip wrestlers without IDs
            if not wrestler_id:
                continue
            
            # Count valid matches
            valid_match_count = sum(
                1 for m in matches
                if is_valid_match(m, wrestler_name, team_name)
            )
            
            # Skip wrestlers with zero valid matches
            if valid_match_count == 0:
                continue
            
            # If wrestler already exists, use the team with more matches
            if wrestler_id in wrestlers_by_id:
                existing_count = wrestler_match_counts[wrestler_id]
                if valid_match_count <= existing_count:
                    continue  # Keep existing record
            
            # Calculate record
            record = calculate_record(matches, wrestler_name, team_name)
            
            # Get final weight
            final_weight = get_final_weight(matches, wrestler_name, team_name)
            
            # Check postseason qualification and placement
            postseason = check_postseason_qualification_and_placement(matches, wrestler_name, team_name)
            
            # Parse grade
            grade = parse_grade(grade_str)
            
            # Create accomplishment record
            accomplishment = {
                'season_wrestler_id': wrestler_id,
                'name': wrestler_name,
                'team': team_name,
                'gender': gender,
                'season': season,
                'grade': grade,
                'final_weight': final_weight,
                'record': record,
                'regional_qualifier': postseason['regional_qualifier'],
                'regional_place': postseason['regional_place'],
                'state_qualifier': postseason['state_qualifier'],
                'state_place': postseason['state_place'],
                'state_champion': postseason['state_champion'],
            }
            
            wrestlers_by_id[wrestler_id] = accomplishment
            wrestler_match_counts[wrestler_id] = valid_match_count
    
    print(f"Found {len(wrestlers_by_id)} wrestlers with at least one match")
    
    return {
        'season': season,
        'gender': gender,
        'wrestlers': list(wrestlers_by_id.values())
    }


def main():
    parser = argparse.ArgumentParser(
        description='Generate Season Accomplishment JSON files'
    )
    parser.add_argument(
        '--season',
        type=int,
        required=True,
        help='Season year (e.g., 2025)'
    )
    parser.add_argument(
        '--gender',
        type=str,
        required=True,
        choices=['boys', 'girls'],
        help='Gender (boys or girls)'
    )
    parser.add_argument(
        '--state',
        type=str,
        default='ky',
        help='State code (default: ky)'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='data/season_accomplishments',
        help='Output directory (default: data/season_accomplishments)'
    )
    
    args = parser.parse_args()
    
    print(f"\n{'='*60}")
    print(f"Generating Season Accomplishments")
    print(f"Season: {args.season}")
    print(f"Gender: {args.gender}")
    print(f"State: {args.state}")
    print(f"{'='*60}\n")
    
    # Process season
    try:
        accomplishments = process_season(args.season, args.gender, args.state)
    except Exception as e:
        print(f"❌ Error processing season: {e}")
        return 1
    
    # Write output
    output_dir = Path(args.output_dir) / args.gender / str(args.season)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = output_dir / "season_accomplishments.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(accomplishments, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Successfully generated: {output_file}")
    print(f"   Total wrestlers: {len(accomplishments['wrestlers'])}")
    
    # Print summary statistics
    total_wins = sum(w['record']['wins'] for w in accomplishments['wrestlers'])
    total_losses = sum(w['record']['losses'] for w in accomplishments['wrestlers'])
    regional_qualifiers = sum(1 for w in accomplishments['wrestlers'] if w['regional_qualifier'])
    state_qualifiers = sum(1 for w in accomplishments['wrestlers'] if w['state_qualifier'])
    
    print(f"\nSummary:")
    print(f"  Total matches: {total_wins + total_losses}")
    print(f"  Regional qualifiers: {regional_qualifiers}")
    print(f"  State qualifiers: {state_qualifiers}")
    
    # Generate placement report
    print(f"\n{'='*60}")
    print("PLACEMENT REPORT")
    print(f"{'='*60}")
    
    # Regional placements (top 4)
    regional_placements = {}
    for place in [1, 2, 3, 4]:
        count = sum(1 for w in accomplishments['wrestlers'] if w.get('regional_place') == place)
        regional_placements[place] = count
    
    print("\nRegional Tournament Placements:")
    print(f"  1st Place: {regional_placements[1]}")
    print(f"  2nd Place: {regional_placements[2]}")
    print(f"  3rd Place: {regional_placements[3]}")
    print(f"  4th Place: {regional_placements[4]}")
    print(f"  Total Placers: {sum(regional_placements.values())}")
    print(f"  Expected: {8} regions × 14 weight classes × 4 placers = {8 * 14 * 4}")
    
    # State placements (top 8)
    state_placements = {}
    for place in [1, 2, 3, 4, 5, 6, 7, 8]:
        count = sum(1 for w in accomplishments['wrestlers'] if w.get('state_place') == place)
        state_placements[place] = count
    
    print("\nState Tournament Placements:")
    print(f"  1st Place: {state_placements[1]}")
    print(f"  2nd Place: {state_placements[2]}")
    print(f"  3rd Place: {state_placements[3]}")
    print(f"  4th Place: {state_placements[4]}")
    print(f"  5th Place: {state_placements[5]}")
    print(f"  6th Place: {state_placements[6]}")
    print(f"  7th Place: {state_placements[7]}")
    print(f"  8th Place: {state_placements[8]}")
    print(f"  Total Placers: {sum(state_placements.values())}")
    print(f"  Expected: 14 weight classes × 8 placers = {14 * 8}")
    
    state_champions = sum(1 for w in accomplishments['wrestlers'] if w.get('state_champion'))
    print(f"\nState Champions: {state_champions} (Expected: 14)")
    
    return 0


if __name__ == '__main__':
    exit(main())

