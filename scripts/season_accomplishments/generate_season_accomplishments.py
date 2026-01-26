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


def parse_placement_file(placement_file_path: Path) -> Dict[str, List[Dict]]:
    """
    Parse placement file to extract state tournament placements.
    
    File format:
    - Weight class on its own line (e.g., "106")
    - Placement matches:
      - "1st Place Match - Winner Name (Winner Team) X-Y won by ... over Loser Name (Loser Team) X-Y (...)"
      - "3rd Place Match - ..." (winner = 3rd, loser = 4th)
      - "5th Place Match - ..." (winner = 5th, loser = 6th)
      - "7th Place Match - ..." (winner = 7th, loser = 8th)
    
    Args:
        placement_file_path: Path to placement.txt or placement.md file
        
    Returns:
        Dictionary mapping weight_class -> list of placement dicts with:
            - weight: weight class (str)
            - place: placement (1-8)
            - name: wrestler name
            - team: team name
    """
    placements_by_weight = {}
    
    if not placement_file_path.exists():
        return placements_by_weight
    
    current_weight = None
    
    with open(placement_file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            # Check if line is a weight class (numeric only)
            if line.isdigit():
                current_weight = line
                placements_by_weight[current_weight] = []
                continue
            
            if not current_weight:
                continue
            
            # Parse placement match line
            # Format: "1st Place Match - Winner Name (Winner Team) X-Y won by ... over Loser Name (Loser Team) X-Y (...)"
            placement_match = re.match(r'(\d+)(st|nd|rd|th)\s+Place\s+Match', line)
            if not placement_match:
                continue
            
            placement_num = int(placement_match.group(1))
            
            # Extract winner and loser
            # Format: "Xth Place Match - Winner Name (Team) X-Y won by/in ... over Loser Name (Team) X-Y (Result)"
            # Note: Team names may contain parentheses like "Trinity (Louisville)"
            # Strategy: Match the pattern " (Team) X-Y" where Team is in parentheses before the record
            
            # For winner: Find "Place Match - ... (Team) X-Y won"
            # We need to find the last " (Team) X-Y" before "won"
            # Use a pattern that matches everything up to the last parentheses before the record
            winner_pattern = r'Place\s+Match\s+-\s+(.+?)\s+\(([^)]+(?:\([^)]+\))*[^)]*)\)\s+\d+-\d+\s+won\s+(?:by|in)'
            winner_match = re.search(winner_pattern, line)
            
            # For loser: Find "over ... (Team) X-Y ("
            # Match backwards from the final result parentheses
            # Pattern: "over ... (Team) X-Y (" where Team may have nested parens
            # We'll match the last set of parentheses before " X-Y ("
            loser_pattern = r'over\s+(.+?)\s+\(([^)]+(?:\([^)]+\))*[^)]*)\)\s+\d+-\d+\s*\('
            loser_match = re.search(loser_pattern, line)
            
            # If that fails, try without requiring final parens (for end of line cases)
            if not loser_match:
                loser_pattern = r'over\s+(.+?)\s+\(([^)]+(?:\([^)]+\))*[^)]*)\)\s+\d+-\d+$'
                loser_match = re.search(loser_pattern, line)
            
            if winner_match and loser_match:
                winner_name = winner_match.group(1).strip()
                winner_team = winner_match.group(2).strip()
                loser_name = loser_match.group(1).strip()
                loser_team = loser_match.group(2).strip()
                
                # Determine placements based on match type
                if placement_num == 1:
                    # 1st Place Match: winner = 1st, loser = 2nd
                    placements_by_weight[current_weight].append({
                        'weight': current_weight,
                        'place': 1,
                        'name': winner_name,
                        'team': winner_team
                    })
                    placements_by_weight[current_weight].append({
                        'weight': current_weight,
                        'place': 2,
                        'name': loser_name,
                        'team': loser_team
                    })
                elif placement_num == 3:
                    # 3rd Place Match: winner = 3rd, loser = 4th
                    placements_by_weight[current_weight].append({
                        'weight': current_weight,
                        'place': 3,
                        'name': winner_name,
                        'team': winner_team
                    })
                    placements_by_weight[current_weight].append({
                        'weight': current_weight,
                        'place': 4,
                        'name': loser_name,
                        'team': loser_team
                    })
                elif placement_num == 5:
                    # 5th Place Match: winner = 5th, loser = 6th
                    placements_by_weight[current_weight].append({
                        'weight': current_weight,
                        'place': 5,
                        'name': winner_name,
                        'team': winner_team
                    })
                    placements_by_weight[current_weight].append({
                        'weight': current_weight,
                        'place': 6,
                        'name': loser_name,
                        'team': loser_team
                    })
                elif placement_num == 7:
                    # 7th Place Match: winner = 7th, loser = 8th
                    placements_by_weight[current_weight].append({
                        'weight': current_weight,
                        'place': 7,
                        'name': winner_name,
                        'team': winner_team
                    })
                    placements_by_weight[current_weight].append({
                        'weight': current_weight,
                        'place': 8,
                        'name': loser_name,
                        'team': loser_team
                    })
    
    return placements_by_weight


def name_similarity(name1: str, name2: str) -> float:
    """
    Calculate similarity score between two names.
    
    Returns:
        Score from 0.0 to 1.0, where 1.0 is exact match
    """
    name1_lower = name1.lower().strip()
    name2_lower = name2.lower().strip()
    
    if name1_lower == name2_lower:
        return 1.0
    
    # Check if one name contains the other (partial match)
    if name1_lower in name2_lower or name2_lower in name1_lower:
        # Calculate ratio of shorter to longer
        shorter = min(len(name1_lower), len(name2_lower))
        longer = max(len(name1_lower), len(name2_lower))
        return shorter / longer if longer > 0 else 0.0
    
    # Check character similarity (simple Levenshtein-like)
    # Count matching characters in order
    matches = 0
    min_len = min(len(name1_lower), len(name2_lower))
    for i in range(min_len):
        if name1_lower[i] == name2_lower[i]:
            matches += 1
    
    if min_len == 0:
        return 0.0
    
    return matches / max(len(name1_lower), len(name2_lower))


def find_wrestler_by_name_team(
    name: str,
    team: str,
    weight: str,
    wrestlers: List[Dict],
    wrestlers_by_id: Dict[str, Dict]
) -> Optional[str]:
    """
    Find wrestler ID by name, team, and weight.
    
    Args:
        name: Wrestler name from placement file
        team: Team name from placement file
        weight: Weight class
        wrestlers: List of all wrestler accomplishment dicts
        wrestlers_by_id: Dict mapping wrestler_id -> accomplishment dict
        
    Returns:
        Wrestler ID if found, None otherwise
    """
    # Normalize names and teams for comparison
    name_lower = name.lower().strip()
    team_lower = team.lower().strip()
    weight_int = int(weight) if weight.isdigit() else None
    
    # Try exact match first
    for wrestler in wrestlers:
        wrestler_name = wrestler.get('name', '').lower().strip()
        wrestler_team = wrestler.get('team', '').lower().strip()
        wrestler_weight = wrestler.get('final_weight')
        
        if (wrestler_name == name_lower and 
            wrestler_team == team_lower and
            wrestler_weight == weight_int):
            return wrestler.get('season_wrestler_id')
    
    # Try fuzzy match (name and team, weight optional)
    candidates = []
    for wrestler in wrestlers:
        wrestler_name = wrestler.get('name', '').lower().strip()
        wrestler_team = wrestler.get('team', '').lower().strip()
        wrestler_weight = wrestler.get('final_weight')
        
        # Check team match (must be good)
        team_match = (team_lower == wrestler_team or 
                     team_lower in wrestler_team or 
                     wrestler_team in team_lower)
        
        if not team_match:
            continue
        
        # Check name similarity
        name_sim = name_similarity(name, wrestler.get('name', ''))
        
        # Only consider if name similarity is reasonable (>= 0.7 or substring match)
        if name_sim >= 0.7 or name_lower in wrestler_name or wrestler_name in name_lower:
            weight_match = (wrestler_weight == weight_int) if weight_int else False
            candidates.append({
                'wrestler_id': wrestler.get('season_wrestler_id'),
                'name': wrestler.get('name'),
                'team': wrestler.get('team'),
                'weight': wrestler_weight,
                'weight_match': weight_match,
                'name_similarity': name_sim
            })
    
    # If we have candidates, return the best one
    # Sort by: weight match, then name similarity, then exact team match
    if candidates:
        candidates.sort(key=lambda x: (
            not x['weight_match'],  # Weight match first
            -x['name_similarity'],  # Higher similarity better
            x['name']  # Then alphabetically for consistency
        ))
        
        best = candidates[0]
        # Only auto-match if we have high confidence (weight match + good name similarity)
        if best['weight_match'] and best['name_similarity'] >= 0.8:
            return best['wrestler_id']
        # Or if exact team match and very high name similarity
        elif team_lower == best['team'].lower() and best['name_similarity'] >= 0.9:
            return best['wrestler_id']
    
    return None


def interactive_match_wrestler(
    placement_name: str,
    placement_team: str,
    placement_weight: str,
    placement_place: int,
    wrestlers: List[Dict]
) -> Optional[str]:
    """
    Interactively match a placement file wrestler to a season wrestler.
    
    Args:
        placement_name: Name from placement file
        placement_team: Team from placement file
        placement_weight: Weight class from placement file
        placement_place: Placement (1-8)
        wrestlers: List of all wrestler accomplishment dicts
        
    Returns:
        Wrestler ID if matched, None if skipped
    """
    print(f"\n{'='*80}")
    print(f"⚠️  UNMATCHED WRESTLER FROM PLACEMENT FILE")
    print(f"{'='*80}")
    print(f"Placement: {placement_place} at {placement_weight} lbs")
    print(f"Name: {placement_name}")
    print(f"Team: {placement_team}")
    print(f"\nSearching for similar wrestlers in season data...")
    
    # Find candidates
    name_lower = placement_name.lower().strip()
    team_lower = placement_team.lower().strip()
    weight_int = int(placement_weight) if placement_weight.isdigit() else None
    
    candidates = []
    for wrestler in wrestlers:
        wrestler_name = wrestler.get('name', '').lower().strip()
        wrestler_team = wrestler.get('team', '').lower().strip()
        wrestler_weight = wrestler.get('final_weight')
        
        # Score candidates
        name_score = 0
        if name_lower == wrestler_name:
            name_score = 100
        elif name_lower in wrestler_name or wrestler_name in name_lower:
            name_score = 50
        
        team_score = 0
        if team_lower == wrestler_team:
            team_score = 100
        elif team_lower in wrestler_team or wrestler_team in team_lower:
            team_score = 50
        
        weight_score = 100 if wrestler_weight == weight_int else 0
        
        total_score = name_score + team_score + weight_score
        
        if total_score > 0:
            candidates.append({
                'wrestler_id': wrestler.get('season_wrestler_id'),
                'name': wrestler.get('name'),
                'team': wrestler.get('team'),
                'weight': wrestler_weight,
                'score': total_score
            })
    
    # Sort by score
    candidates.sort(key=lambda x: -x['score'])
    
    if candidates:
        print(f"\nFound {len(candidates)} potential matches:")
        for idx, cand in enumerate(candidates[:10], 1):  # Show top 10
            print(f"  {idx:2d}. {cand['name']:<30} {cand['team']:<30} Weight: {cand['weight']} (score: {cand['score']})")
        
        while True:
            try:
                choice = input(f"\nSelect wrestler number (1-{min(len(candidates), 10)}), or 's' to skip, or 'm' to enter ID manually: ").strip().lower()
                
                if choice == 's':
                    print("  Skipped.")
                    return None
                elif choice == 'm':
                    manual_id = input("  Enter wrestler ID manually: ").strip()
                    # Verify ID exists
                    if any(w.get('season_wrestler_id') == manual_id for w in wrestlers):
                        print(f"  Matched to ID: {manual_id}")
                        return manual_id
                    else:
                        print("  Invalid ID. Try again.")
                        continue
                else:
                    idx = int(choice)
                    if 1 <= idx <= min(len(candidates), 10):
                        selected = candidates[idx - 1]
                        print(f"  Matched: {selected['name']} ({selected['team']})")
                        return selected['wrestler_id']
                    else:
                        print("  Invalid number. Try again.")
                        continue
            except ValueError:
                print("  Invalid input. Try again.")
                continue
    else:
        print("\nNo similar wrestlers found.")
        manual_id = input("Enter wrestler ID manually (or press Enter to skip): ").strip()
        if manual_id:
            # Verify ID exists
            if any(w.get('season_wrestler_id') == manual_id for w in wrestlers):
                print(f"  Matched to ID: {manual_id}")
                return manual_id
            else:
                print("  Invalid ID. Skipping.")
                return None
        else:
            print("  Skipped.")
            return None


def apply_state_placements_from_file(
    accomplishments: Dict,
    placement_file_path: Path
) -> Dict[str, int]:
    """
    Apply state tournament placements from placement file.
    
    Args:
        accomplishments: Season accomplishments dict with wrestlers list
        placement_file_path: Path to placement.txt or placement.md file
        
    Returns:
        Dictionary with statistics: {'matched': count, 'unmatched': count, 'updated': count}
    """
    if not placement_file_path.exists():
        print(f"\n⚠️  Warning: Placement file not found: {placement_file_path}")
        print("   State placements will not be updated from file.")
        return {'matched': 0, 'unmatched': 0, 'updated': 0}
    
    print(f"\nLoading state placements from: {placement_file_path}")
    
    # Parse placement file
    placements_by_weight = parse_placement_file(placement_file_path)
    
    if not placements_by_weight:
        print("  No placements found in file.")
        return {'matched': 0, 'unmatched': 0, 'updated': 0}
    
    # Count total expected placements
    total_expected = 0
    for weight, placements in placements_by_weight.items():
        total_expected += len(placements)
    
    print(f"  Found placements for {len(placements_by_weight)} weight classes")
    print(f"  Total placements: {total_expected} (expected: {len(placements_by_weight)} × 8 = {len(placements_by_weight) * 8})")
    
    # Build wrestler lookup
    wrestlers = accomplishments.get('wrestlers', [])
    wrestlers_by_id = {w.get('season_wrestler_id'): w for w in wrestlers}
    
    stats = {'matched': 0, 'unmatched': 0, 'updated': 0}
    unmatched_placements = []
    
    # Match placements to wrestlers
    for weight, placements in placements_by_weight.items():
        for placement in placements:
            placement_name = placement['name']
            placement_team = placement['team']
            placement_weight = placement['weight']
            placement_place = placement['place']
            
            # Try to find wrestler
            wrestler_id = find_wrestler_by_name_team(
                placement_name,
                placement_team,
                placement_weight,
                wrestlers,
                wrestlers_by_id
            )
            
            if wrestler_id and wrestler_id in wrestlers_by_id:
                # Match found - update placement
                wrestler = wrestlers_by_id[wrestler_id]
                wrestler['state_place'] = placement_place
                wrestler['state_champion'] = (placement_place == 1)
                wrestler['state_qualifier'] = True  # If they placed, they qualified
                stats['matched'] += 1
                stats['updated'] += 1
            else:
                # No match - need interactive help
                stats['unmatched'] += 1
                unmatched_placements.append(placement)
                
                wrestler_id = interactive_match_wrestler(
                    placement_name,
                    placement_team,
                    placement_weight,
                    placement_place,
                    wrestlers
                )
                
                if wrestler_id and wrestler_id in wrestlers_by_id:
                    wrestler = wrestlers_by_id[wrestler_id]
                    wrestler['state_place'] = placement_place
                    wrestler['state_champion'] = (placement_place == 1)
                    wrestler['state_qualifier'] = True
                    stats['matched'] += 1
                    stats['updated'] += 1
    
    # Summary
    print(f"\n{'='*80}")
    print("STATE PLACEMENT IMPORT SUMMARY")
    print(f"{'='*80}")
    print(f"  Matched: {stats['matched']}")
    print(f"  Unmatched: {stats['unmatched']}")
    print(f"  Updated: {stats['updated']}")
    
    if stats['unmatched'] > 0:
        print(f"\n⚠️  Warning: {stats['unmatched']} placements could not be matched.")
    
    return stats


def check_postseason_qualification_and_placement(matches: List[Dict], wrestler_name: str, team_name: str) -> Dict:
    """
    Check if wrestler qualified for regional/state tournaments and determine placement.
    
    For 2025 season, event names are:
    - Regional tournaments: "KHSAA Region <1-8>" (e.g., "KHSAA Region 1")
    - State tournament: "KHSAA Final Round State Championship"
    
    Note: State placements are now primarily determined from placement file,
    but we still check matches for state qualification.
    
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
        
        # Check for state championship qualification
        # Look for "KHSAA Final Round State Championship" (placement matches happen in final round)
        if 'KHSAA Final Round State Championship' in event:
            state_qualifier = True
            # Note: State placement is determined from placement file, not from matches
    
    return {
        'regional_qualifier': regional_qualifier,
        'regional_place': regional_place,
        'state_qualifier': state_qualifier,
        'state_place': state_place,  # Will be updated from placement file
        'state_champion': state_place == 1 if state_place else False
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
    
    accomplishments = {
        'season': season,
        'gender': gender,
        'wrestlers': list(wrestlers_by_id.values())
    }
    
    # Apply state placements from placement file
    state_lower = state.lower()
    placement_file_path = Path(f"data/hs_{state_lower}_{gender}/{season}/placement.txt")
    # Also check for .md extension if .txt doesn't exist
    if not placement_file_path.exists():
        placement_file_path = Path(f"data/hs_{state_lower}_{gender}/{season}/placement.md")
    
    # Apply state placements from file (this will update state_place and state_champion)
    apply_state_placements_from_file(accomplishments, placement_file_path)
    
    return accomplishments


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

