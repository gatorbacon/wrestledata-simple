#!/usr/bin/env python3
"""
Load wrestling data from processed JSON files.

This script reads all team data from mt/processed_data/{season}/ and organizes
wrestlers and matches by weight class for ranking purposes.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Set, Tuple
from collections import defaultdict


def load_team_data(season: int) -> List[Dict]:
    """
    Load all team data files for a season.
    
    Args:
        season: Season year (e.g., 2026)
        
    Returns:
        List of team data dictionaries
    """
    data_dir = Path(f"mt/processed_data/{season}")
    
    if not data_dir.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")
    
    teams = []
    for json_file in sorted(data_dir.glob("*.json")):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                team_data = json.load(f)
                teams.append(team_data)
        except Exception as e:
            print(f"Warning: Error loading {json_file}: {e}")
            continue
    
    print(f"Loaded {len(teams)} team files from {data_dir}")
    return teams


def extract_wrestlers_and_matches(teams: List[Dict]) -> Dict[str, Dict]:
    """
    Extract all wrestlers and their matches, organized by weight class.
    
    Only includes wrestlers with valid IDs from D1 teams.
    Only processes matches where both wrestlers have valid IDs.
    
    Args:
        teams: List of team data dictionaries
        
    Returns:
        Dictionary mapping weight_class -> {
            'wrestlers': {wrestler_id: wrestler_info},
            'matches': [match_info]
        }
    """
    weight_classes = defaultdict(lambda: {
        'wrestlers': {},
        'matches': []
    })
    
    # First pass: collect all D1 wrestlers with valid IDs
    # Track by ID only - use ID as the primary identifier
    all_wrestlers = {}
    
    for team in teams:
        team_name = team.get('team_name', 'Unknown')
        
        for wrestler in team.get('roster', []):
            wrestler_id = wrestler.get('season_wrestler_id')
            wrestler_name = wrestler.get('name', 'Unknown')
            
            # CRITICAL: Only include wrestlers with valid, non-null IDs
            if not wrestler_id or wrestler_id == 'null' or wrestler_id == '':
                continue
            
            # Get or create wrestler info (use ID as key)
            if wrestler_id not in all_wrestlers:
                all_wrestlers[wrestler_id] = {
                    'id': wrestler_id,
                    'name': wrestler_name,
                    'team': team_name,
                    'weight_class': wrestler.get('weight_class', ''),
                    'grade': wrestler.get('grade', ''),
                    'wins': 0,
                    'losses': 0,
                    'matches_count': 0
                }
    
    # Second pass: process matches and determine weight class assignments
    # Track all matches per wrestler to determine their weight class
    wrestler_matches = defaultdict(list)  # wrestler_id -> list of (match, match_weight, date)
    
    # Track which matches we've already processed for stats (to avoid double-counting)
    processed_matches_for_stats = set()  # match_key -> already processed
    
    for team in teams:
        team_name = team.get('team_name', 'Unknown')
        
        for wrestler in team.get('roster', []):
            wrestler_id = wrestler.get('season_wrestler_id')
            
            # Skip if wrestler doesn't have valid ID or isn't in our list
            if not wrestler_id or wrestler_id not in all_wrestlers:
                continue
            
            wrestler_info = all_wrestlers[wrestler_id]
            wrestler_name = wrestler_info['name']
            primary_weight_class = wrestler_info['weight_class']
            
            # Process matches for this wrestler
            for match in wrestler.get('matches', []):
                # Skip matches that don't have parsed winner/loser info
                if 'winner_name' not in match or 'loser_name' not in match:
                    continue
                
                # Skip byes and no-result matches
                result = match.get('result', '')
                if result in ('BYE', 'NoResult') or 'received a bye' in match.get('summary', '').lower():
                    continue
                
                # Get opponent ID - CRITICAL: must have valid ID
                opponent_id = match.get('opponent_id')
                
                # Skip if opponent doesn't have a valid ID
                if not opponent_id or opponent_id == 'null' or opponent_id == '':
                    continue
                
                # Skip if opponent is not in our D1 wrestler list
                if opponent_id not in all_wrestlers:
                    continue
                
                # Get the weight class for this match
                match_weight = match.get('weight', '') or primary_weight_class
                if not match_weight:
                    continue
                
                # Determine if this wrestler won or lost (using ID-based matching)
                winner_name = match.get('winner_name', '')
                loser_name = match.get('loser_name', '')
                winner_team = match.get('winner_team', '')
                loser_team = match.get('loser_team', '')
                
                # Match using ID, not name
                opponent_info = all_wrestlers[opponent_id]
                opponent_name = opponent_info['name']
                opponent_team = opponent_info['team']
                
                # Determine winner using ID
                is_winner = (wrestler_id == match.get('winner_id', '') or 
                            (wrestler_name == winner_name and team_name == winner_team))
                is_loser = (wrestler_id == match.get('loser_id', '') or
                           (wrestler_name == loser_name and team_name == loser_team))
                
                if not (is_winner or is_loser):
                    # Can't determine result, skip
                    continue
                
                # Store match info for weight class determination
                match_date = match.get('date', '')
                wrestler_matches[wrestler_id].append((match, match_weight, match_date))
                
                # Create match record (using IDs only)
                # Normalize wrestler IDs (always use smaller ID first for consistency)
                w1_id_normalized = min(wrestler_id, opponent_id)
                w2_id_normalized = max(wrestler_id, opponent_id)
                winner_id_normalized = wrestler_id if is_winner else opponent_id
                
                match_record = {
                    'date': match_date,
                    'weight_class': match_weight,
                    'wrestler1_id': w1_id_normalized,
                    'wrestler2_id': w2_id_normalized,
                    'winner_id': winner_id_normalized,
                    'result': result,
                    'event': match.get('event', '')
                }
                
                # Create unique match key for deduplication
                match_key = (w1_id_normalized, w2_id_normalized, match_date, winner_id_normalized)
                
                # Store match by key to avoid duplicates
                if match_weight not in weight_classes:
                    weight_classes[match_weight] = {'wrestlers': {}, 'matches': [], 'match_keys': set()}
                elif 'match_keys' not in weight_classes[match_weight]:
                    weight_classes[match_weight]['match_keys'] = set()
                
                # Only add if we haven't seen this match before
                if match_key not in weight_classes[match_weight]['match_keys']:
                    weight_classes[match_weight]['matches'].append(match_record)
                    weight_classes[match_weight]['match_keys'].add(match_key)
                
                # Update wrestler stats (only once per unique match)
                if match_key not in processed_matches_for_stats:
                    if is_winner:
                        wrestler_info['wins'] += 1
                        opponent_info['losses'] += 1
                    else:
                        wrestler_info['losses'] += 1
                        opponent_info['wins'] += 1
                    
                    wrestler_info['matches_count'] += 1
                    opponent_info['matches_count'] += 1
                    
                    processed_matches_for_stats.add(match_key)
    
    # Third pass: determine weight class assignment for each wrestler
    wrestler_weight_class = {}  # wrestler_id -> assigned weight_class

    # Load manual weight overrides (virtual match hints) if present.
    # File format (mt/rankings_data/{season}/weight_overrides.json):
    # {
    #   "overrides": [
    #     {
    #       "wrestler_id": "<id>",
    #       "date": "MM/DD/YYYY",
    #       "weight": "141",
    #       "matches_equivalent": 5
    #     },
    #     ...
    #   ]
    # }
    #
    # These overrides do NOT create real matches; they only influence the
    # weight-assignment algorithm by adding virtual entries to wrestler_matches.
    overrides_by_wrestler: Dict[str, List[Tuple[str, str, int]]] = defaultdict(list)
    overrides_path = Path("mt/rankings_data") / "weight_overrides.json"
    if overrides_path.exists():
        try:
            with open(overrides_path, "r", encoding="utf-8") as f:
                overrides_data = json.load(f)
            for o in overrides_data.get("overrides", []):
                wid = o.get("wrestler_id")
                date = o.get("date")
                weight = o.get("weight")
                count = int(o.get("matches_equivalent", 5))
                if not (wid and date and weight):
                    continue
                overrides_by_wrestler[wid].append((weight, date, count))
        except Exception as e:
            print(f"Warning: Failed to load weight_overrides.json: {e}")
    
    def parse_date(date_str):
        """Parse MM/DD/YYYY date string to tuple for sorting."""
        if not date_str:
            return (0, 0, 0)
        try:
            parts = date_str.split('/')
            if len(parts) == 3:
                return (int(parts[2]), int(parts[0]), int(parts[1]))  # (year, month, day)
        except:
            pass
        return (0, 0, 0)
    
    for wrestler_id, wrestler_info in all_wrestlers.items():
        matches = list(wrestler_matches[wrestler_id])

        # Apply any weight overrides as virtual matches (no effect on stats).
        # Each override adds N synthetic matches at the given weight/date.
        for weight, date, count in overrides_by_wrestler.get(wrestler_id, []):
            for _ in range(max(0, count)):
                matches.append((None, weight, date))
        primary_weight = wrestler_info['weight_class']
        
        if len(matches) == 0:
            # No matches: use primary weight
            assigned_weight = primary_weight
        elif len(matches) < 5:
            # Less than 5 matches: use most recent weight
            # Sort by date (most recent first)
            sorted_matches = sorted(matches, key=lambda x: parse_date(x[2]), reverse=True)
            assigned_weight = sorted_matches[0][1] if sorted_matches else primary_weight
        else:
            # 5 or more matches: use most common weight in last 5 matches
            # Sort by date (most recent first) and take last 5
            sorted_matches = sorted(matches, key=lambda x: parse_date(x[2]), reverse=True)
            last_5 = sorted_matches[:5]
            
            # Count weights in last 5 matches
            weight_counts = defaultdict(int)
            for _, match_weight, _ in last_5:
                weight_counts[match_weight] += 1
            
            # Get most common weight
            if weight_counts:
                assigned_weight = max(weight_counts.items(), key=lambda x: x[1])[0]
            else:
                assigned_weight = primary_weight
        
        wrestler_weight_class[wrestler_id] = assigned_weight
    
    # Add wrestlers to their assigned weight classes
    for wrestler_id, assigned_weight in wrestler_weight_class.items():
        if assigned_weight:
            if assigned_weight not in weight_classes:
                weight_classes[assigned_weight] = {'wrestlers': {}, 'matches': []}
            weight_classes[assigned_weight]['wrestlers'][wrestler_id] = all_wrestlers[wrestler_id]
    
    # Collect all matches across all weight classes (for relationship building)
    # Matches can span weight classes - we want all matches for common opponent analysis
    # Use a set to track unique matches across all weight classes
    all_matches_unique = {}  # match_key -> match_record
    all_matches_by_weight = defaultdict(list)
    
    # Group matches by the weight class they were wrestled at
    for wc, wc_data in weight_classes.items():
        for match in wc_data['matches']:
            match_wc = match['weight_class']  # The weight class the match was at
            # Create unique key for deduplication across weight classes
            match_key = (match['wrestler1_id'], match['wrestler2_id'], match['date'], match['winner_id'])
            
            # Only add if we haven't seen this match before
            if match_key not in all_matches_unique:
                all_matches_unique[match_key] = match
                all_matches_by_weight[match_wc].append(match)
    
    # Now, for each assigned weight class, include:
    # 1. Wrestlers assigned to that weight class
    # 2. ALL matches involving those wrestlers (regardless of what weight class the match was at)
    # This allows cross-weight-class matches to be considered for common opponent relationships
    filtered_weight_classes = defaultdict(lambda: {'wrestlers': {}, 'matches': []})
    
    for assigned_wc, assigned_wrestlers in weight_classes.items():
        # Add wrestlers assigned to this weight class
        filtered_weight_classes[assigned_wc]['wrestlers'] = assigned_wrestlers['wrestlers']
        
        # Include ALL matches where at least one wrestler is assigned to this weight class
        # This allows cross-weight-class matches to be considered
        wrestler_ids_in_wc = set(assigned_wrestlers['wrestlers'].keys())
        seen_match_ids = set()  # Track matches we've already added to avoid duplicates
        
        for match_wc, matches in all_matches_by_weight.items():
            for match in matches:
                w1_id = match['wrestler1_id']
                w2_id = match['wrestler2_id']
                
                # Include match if at least one wrestler is assigned to this weight class
                if w1_id in wrestler_ids_in_wc or w2_id in wrestler_ids_in_wc:
                    # Create a unique match ID to avoid duplicates
                    match_id = f"{w1_id}_{w2_id}_{match.get('date', '')}_{match.get('result', '')}"
                    
                    if match_id not in seen_match_ids:
                        filtered_weight_classes[assigned_wc]['matches'].append(match)
                        seen_match_ids.add(match_id)
    
    weight_classes = filtered_weight_classes
    
    # Convert defaultdict to regular dict and filter out empty weight classes
    result = {}
    for wc, data in weight_classes.items():
        if data['wrestlers']:  # Only include weight classes with wrestlers
            result[wc] = {
                'wrestlers': data['wrestlers'],
                'matches': data['matches']
            }
    
    # Print summary
    print(f"\nData Summary:")
    print(f"Total wrestlers: {len(all_wrestlers)}")
    for wc in sorted(result.keys()):
        wrestler_count = len(result[wc]['wrestlers'])
        match_count = len(result[wc]['matches'])
        print(f"  {wc}: {wrestler_count} wrestlers, {match_count} matches")
    
    return result


def load_season_data(season: int) -> Dict[str, Dict]:
    """
    Main function to load all data for a season.
    
    Args:
        season: Season year (e.g., 2026)
        
    Returns:
        Dictionary mapping weight_class -> {
            'wrestlers': {wrestler_id: wrestler_info},
            'matches': [match_info]
        }
    """
    print(f"Loading data for season {season}...")
    
    # Load team data
    teams = load_team_data(season)
    
    if not teams:
        raise ValueError(f"No team data found for season {season}")
    
    # Extract wrestlers and matches
    data_by_weight = extract_wrestlers_and_matches(teams)
    
    return data_by_weight


def save_loaded_data(data: Dict[str, Dict], season: int, output_dir: str = "mt/rankings_data"):
    """
    Save the loaded data to JSON files for inspection.
    
    Args:
        data: Data dictionary from load_season_data
        season: Season year
        output_dir: Directory to save files
    """
    output_path = Path(output_dir) / str(season)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Save summary file
    summary = {
        'season': season,
        'weight_classes': {},
        'total_wrestlers': 0,
        'total_matches': 0
    }
    
    for wc, wc_data in data.items():
        wrestler_count = len(wc_data['wrestlers'])
        match_count = len(wc_data['matches'])
        summary['weight_classes'][wc] = {
            'wrestlers': wrestler_count,
            'matches': match_count
        }
        summary['total_wrestlers'] += wrestler_count
        summary['total_matches'] += match_count
    
    summary_file = output_path / "summary.json"
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)
    print(f"\nSaved summary to {summary_file}")
    
    # Save data for each weight class
    for wc, wc_data in data.items():
        wc_file = output_path / f"weight_class_{wc}.json"
        with open(wc_file, 'w', encoding='utf-8') as f:
            json.dump(wc_data, f, indent=2)
        print(f"Saved {wc} data to {wc_file}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Load wrestling data from processed JSON files')
    parser.add_argument('-season', type=int, required=True, help='Season year (e.g., 2026)')
    parser.add_argument('-save', action='store_true', help='Save loaded data to JSON files for inspection')
    args = parser.parse_args()
    
    data = load_season_data(args.season)
    
    # Print a sample of the data structure
    if data:
        sample_wc = list(data.keys())[0]
        sample_data = data[sample_wc]
        print(f"\nSample data for weight class {sample_wc}:")
        print(f"  Wrestlers: {len(sample_data['wrestlers'])}")
        print(f"  Matches: {len(sample_data['matches'])}")
        
        # Show top wrestlers by record
        wrestlers_list = list(sample_data['wrestlers'].values())
        wrestlers_with_matches = [w for w in wrestlers_list if w['matches_count'] > 0]
        if wrestlers_with_matches:
            # Sort by win percentage
            wrestlers_with_matches.sort(key=lambda w: (w['wins'] / w['matches_count'] if w['matches_count'] > 0 else 0), reverse=True)
            print(f"\n  Top 5 wrestlers by win %:")
            for w in wrestlers_with_matches[:5]:
                win_pct = (w['wins'] / w['matches_count'] * 100) if w['matches_count'] > 0 else 0
                print(f"    {w['name']} ({w['team']}): {w['wins']}-{w['losses']} ({win_pct:.1f}%)")
        
        if sample_data['matches']:
            sample_match = sample_data['matches'][0]
            print(f"\n  Sample match:")
            w1_id = sample_match['wrestler1_id']
            w2_id = sample_match['wrestler2_id']
            w1 = sample_data['wrestlers'].get(w1_id, {'name': w1_id})
            w2 = sample_data['wrestlers'].get(w2_id, {'name': w2_id})
            print(f"    {w1.get('name', w1_id)} vs {w2.get('name', w2_id)}")
            print(f"    Winner: {sample_match['winner_id']}")
    
    # Save data if requested
    if args.save:
        save_loaded_data(data, args.season)

