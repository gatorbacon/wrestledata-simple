#!/usr/bin/env python3
"""
Build relationship matrix from loaded wrestling data.

This script calculates direct head-to-head results and common opponent
relationships between wrestlers for ranking purposes.
"""

import json
from pathlib import Path
from typing import Dict, List, Set, Tuple
from collections import defaultdict


def build_direct_relationships(matches: List[Dict], wrestlers: Dict[str, Dict]) -> Dict[Tuple[str, str], Dict]:
    """
    Build direct head-to-head relationships from matches.
    
    Args:
        matches: List of match dictionaries
        wrestlers: Dictionary of wrestler_id -> wrestler_info
        
    Returns:
        Dictionary mapping (wrestler1_id, wrestler2_id) -> relationship_info
    """
    relationships = {}
    
    for match in matches:
        w1_id = match['wrestler1_id']
        w2_id = match['wrestler2_id']
        winner_id = match['winner_id']
        
        # Skip if either wrestler doesn't exist
        if w1_id not in wrestlers or w2_id not in wrestlers:
            continue
        
        # Create normalized pair key (always use smaller ID first for consistency)
        pair_key = tuple(sorted([w1_id, w2_id]))
        
        if pair_key not in relationships:
            relationships[pair_key] = {
                'wrestler1_id': pair_key[0],
                'wrestler2_id': pair_key[1],
                'direct_wins_1': 0,  # wins by wrestler1
                'direct_losses_1': 0,  # losses by wrestler1
                'direct_wins_2': 0,  # wins by wrestler2
                'direct_losses_2': 0,  # losses by wrestler2
                'matches': []
            }
        
        rel = relationships[pair_key]
        
        # Determine which wrestler won
        if winner_id == w1_id:
            if w1_id == pair_key[0]:
                rel['direct_wins_1'] += 1
                rel['direct_losses_2'] += 1
            else:
                rel['direct_wins_2'] += 1
                rel['direct_losses_1'] += 1
        else:  # winner_id == w2_id
            if w2_id == pair_key[0]:
                rel['direct_wins_1'] += 1
                rel['direct_losses_2'] += 1
            else:
                rel['direct_wins_2'] += 1
                rel['direct_losses_1'] += 1
        
        # Store match info
        rel['matches'].append({
            'date': match.get('date', ''),
            'winner_id': winner_id,
            'result': match.get('result', ''),
            'event': match.get('event', '')
        })
    
    return relationships


def build_common_opponent_relationships(
    direct_relationships: Dict[Tuple[str, str], Dict],
    matches: List[Dict],
    wrestlers: Dict[str, Dict]
) -> Dict[Tuple[str, str], Dict]:
    """
    Build common opponent relationships.
    
    If A beat B, and B beat C, then A has a common opponent win over C.
    
    Args:
        direct_relationships: Direct head-to-head relationships
        matches: List of all matches
        wrestlers: Dictionary of wrestler_id -> wrestler_info
        
    Returns:
        Dictionary mapping (wrestler1_id, wrestler2_id) -> common_opponent_info
    """
    # Build opponent sets and win/loss records from ALL matches
    # opponents[wrestler_id] = set of all opponent IDs this wrestler has faced
    opponents = defaultdict(set)
    # match_results[(w1_id, w2_id)] = (wins_by_w1, losses_by_w1)
    match_results = {}
    # match_details[(w1_id, w2_id)] = list of match records for this pair
    match_details = defaultdict(list)
    
    for match in matches:
        w1_id = match['wrestler1_id']
        w2_id = match['wrestler2_id']
        winner_id = match['winner_id']
        
        # Skip if either wrestler doesn't exist
        if w1_id not in wrestlers or w2_id not in wrestlers:
            continue
        
        # Skip "no contest" and injury/medical forfeit matches for CO logic
        # (NC, MFF/MFFL/M. For./medical forfeit, INJ)
        result_str = str(match.get('result', '')).lower().strip()
        if (
            result_str == 'nc'
            or 'no contest' in result_str
            or 'mffl' in result_str
            or 'm. for.' in result_str
            or 'medical forfeit' in result_str
            or 'inj' in result_str
            or 'injury' in result_str
        ):
            continue
        
        # Track opponents
        opponents[w1_id].add(w2_id)
        opponents[w2_id].add(w1_id)
        
        # Track match results
        # Normalize: always use smaller ID first for consistency
        pair_key = tuple(sorted([w1_id, w2_id]))
        first_id = pair_key[0]
        second_id = pair_key[1]
        
        if pair_key not in match_results:
            match_results[pair_key] = [0, 0]  # [wins_by_first, losses_by_first]
        
        # Store match details
        match_details[pair_key].append({
            'date': match.get('date', ''),
            'result': match.get('result', ''),
            'event': match.get('event', ''),
            'winner_id': winner_id
        })
        
        # Determine who won from the first wrestler's perspective
        if winner_id == first_id:
            # First wrestler won
            match_results[pair_key][0] += 1  # wins_by_first += 1
        elif winner_id == second_id:
            # Second wrestler won, so first lost
            match_results[pair_key][1] += 1  # losses_by_first += 1 (first's losses)
        # Note: match_results[pair_key] = [wins_by_first, losses_by_first]
    
    # Now find common opponent relationships
    common_opp_relationships = {}
    
    # For each wrestler pair that doesn't have a direct relationship
    wrestler_ids = list(wrestlers.keys())
    for i, w1_id in enumerate(wrestler_ids):
        for w2_id in wrestler_ids[i+1:]:
            pair_key = tuple(sorted([w1_id, w2_id]))
            
            # Skip if they have a direct relationship
            if pair_key in direct_relationships:
                continue
            
            # Find common opponents (all opponents both have faced)
            w1_opponents = opponents[w1_id]
            w2_opponents = opponents[w2_id]
            common_opponents = w1_opponents & w2_opponents
            
            if not common_opponents:
                continue
            
            # Calculate common opponent wins/losses
            co_wins_1 = 0  # wins by w1 via common opponents
            co_losses_1 = 0  # losses by w1 via common opponents
            co_wins_2 = 0  # wins by w2 via common opponents
            co_losses_2 = 0  # losses by w2 via common opponents
            
            # Track details for each common opponent relationship
            co_details_1 = []  # Details for w1's wins (opponent, match info)
            co_details_2 = []  # Details for w2's wins (opponent, match info)
            
            for opp_id in common_opponents:
                # How did w1 do against this opponent?
                w1_opp_pair = tuple(sorted([w1_id, opp_id]))
                if w1_opp_pair in match_results:
                    wins_by_first, losses_by_first = match_results[w1_opp_pair]
                    if w1_id == w1_opp_pair[0]:
                        w1_wins = wins_by_first
                        w1_losses = losses_by_first
                    else:
                        # w1 is second in sorted pair
                        # match_results stores [wins_by_first, losses_by_first]
                        # So wins_by_first = opponent's wins, losses_by_first = opponent's losses
                        # w1's wins = opponent's losses, w1's losses = opponent's wins
                        w1_wins = losses_by_first  # opponent's losses = w1's wins
                        w1_losses = wins_by_first  # opponent's wins = w1's losses
                else:
                    # No matches found (shouldn't happen if opponent is in set)
                    continue
                
                # How did w2 do against this opponent?
                w2_opp_pair = tuple(sorted([w2_id, opp_id]))
                if w2_opp_pair in match_results:
                    wins_by_first, losses_by_first = match_results[w2_opp_pair]
                    if w2_id == w2_opp_pair[0]:
                        w2_wins = wins_by_first
                        w2_losses = losses_by_first
                    else:
                        # w2 is second in sorted pair
                        # match_results stores [wins_by_first, losses_by_first]
                        # So wins_by_first = opponent's wins, losses_by_first = opponent's losses
                        # w2's wins = opponent's losses, w2's losses = opponent's wins
                        w2_wins = losses_by_first  # opponent's losses = w2's wins
                        w2_losses = wins_by_first  # opponent's wins = w2's losses
                else:
                    # No matches found (shouldn't happen if opponent is in set)
                    continue

                # If either wrestler is exactly split (e.g. 1-1, 2-2) against this common
                # opponent, treat that opponent as neutral and do not use it for CO.
                if (w1_wins == w1_losses and w1_wins > 0) or (w2_wins == w2_losses and w2_wins > 0):
                    continue
                
                # Compare results - only count when one has an advantage
                # w1_wins means w1 beat the opponent, w1_losses means w1 lost to the opponent
                # IMPORTANT: Only count if both wrestlers actually have matches with the opponent
                # (w1_wins + w1_losses > 0 and w2_wins + w2_losses > 0)
                if w1_wins > 0 and w2_losses > 0:
                    # w1 beat the opponent, w2 lost to the opponent
                    co_wins_1 += 1
                    co_losses_2 += 1
                    
                    # Store details: get match info for both wrestlers vs opponent
                    opp_name = wrestlers.get(opp_id, {}).get('name', f'ID:{opp_id}')
                    w1_match_details = match_details.get(w1_opp_pair, [])
                    w2_match_details = match_details.get(w2_opp_pair, [])
                    
                    # Find the relevant matches (where w1 won and w2 lost)
                    for w1_match in w1_match_details:
                        if w1_match['winner_id'] == w1_id:
                            for w2_match in w2_match_details:
                                if w2_match['winner_id'] == opp_id:  # w2 lost
                                    co_details_1.append({
                                        'opponent_id': opp_id,
                                        'opponent_name': opp_name,
                                        'winner_id': w1_id,  # wrestler who has the advantage
                                        'loser_id': w2_id,   # wrestler at disadvantage
                                        'winner_match': {
                                            'date': w1_match['date'],
                                            'result': w1_match['result'],
                                            'event': w1_match.get('event', '')
                                        },
                                        'loser_match': {
                                            'date': w2_match['date'],
                                            'result': w2_match['result'],
                                            'event': w2_match.get('event', '')
                                        }
                                    })
                                    break
                            break
                    
                elif w1_losses > 0 and w2_wins > 0:
                    # w1 lost to the opponent, w2 beat the opponent
                    co_losses_1 += 1
                    co_wins_2 += 1
                    
                    # Store details: get match info for both wrestlers vs opponent
                    opp_name = wrestlers.get(opp_id, {}).get('name', f'ID:{opp_id}')
                    w1_match_details = match_details.get(w1_opp_pair, [])
                    w2_match_details = match_details.get(w2_opp_pair, [])
                    
                    # Find the relevant matches (where w1 lost and w2 won)
                    for w1_match in w1_match_details:
                        if w1_match['winner_id'] == opp_id:  # w1 lost
                            for w2_match in w2_match_details:
                                if w2_match['winner_id'] == w2_id:  # w2 won
                                    co_details_2.append({
                                        'opponent_id': opp_id,
                                        'opponent_name': opp_name,
                                        'winner_id': w2_id,  # wrestler who has the advantage
                                        'loser_id': w1_id,   # wrestler at disadvantage
                                        'winner_match': {
                                            'date': w2_match['date'],
                                            'result': w2_match['result'],
                                            'event': w2_match.get('event', '')
                                        },
                                        'loser_match': {
                                            'date': w1_match['date'],
                                            'result': w1_match['result'],
                                            'event': w1_match.get('event', '')
                                        }
                                    })
                                    break
                            break
                # If both won, both lost, or no clear advantage, don't count
            
            # Only create relationship if there are actual common opponent results
            if co_wins_1 > 0 or co_losses_1 > 0 or co_wins_2 > 0 or co_losses_2 > 0:
                # Normalize counts/details so that *_1 always corresponds to wrestler1_id
                first_id, second_id = pair_key
                if w1_id == first_id:
                    # Loop's w1 is wrestler1, w2 is wrestler2 – keep as-is
                    wins_1, losses_1, details_1 = co_wins_1, co_losses_1, co_details_1
                    wins_2, losses_2, details_2 = co_wins_2, co_losses_2, co_details_2
                else:
                    # Loop's w1 is wrestler2, w2 is wrestler1 – swap when storing
                    wins_1, losses_1, details_1 = co_wins_2, co_losses_2, co_details_2
                    wins_2, losses_2, details_2 = co_wins_1, co_losses_1, co_details_1

                common_opp_relationships[pair_key] = {
                    'wrestler1_id': first_id,
                    'wrestler2_id': second_id,
                    'common_opp_wins_1': wins_1,
                    'common_opp_losses_1': losses_1,
                    'common_opp_wins_2': wins_2,
                    'common_opp_losses_2': losses_2,
                    'common_opponents': list(common_opponents),
                    'co_details_1': details_1,  # Details for wrestler1's wins
                    'co_details_2': details_2   # Details for wrestler2's wins
                }
    
    return common_opp_relationships


def build_relationships_for_weight_class(weight_class_data: Dict) -> Dict:
    """
    Build all relationships for a single weight class.
    
    Args:
        weight_class_data: Dictionary with 'wrestlers' and 'matches' keys
        
    Returns:
        Dictionary with direct and common opponent relationships
    """
    wrestlers = weight_class_data['wrestlers']
    matches = weight_class_data['matches']
    
    print(f"  Building relationships for {len(wrestlers)} wrestlers, {len(matches)} matches...")
    
    # Build direct relationships
    direct_rels = build_direct_relationships(matches, wrestlers)
    print(f"    Direct relationships: {len(direct_rels)}")
    
    # Build common opponent relationships
    common_opp_rels = build_common_opponent_relationships(direct_rels, matches, wrestlers)
    print(f"    Common opponent relationships: {len(common_opp_rels)}")
    
    return {
        'wrestlers': wrestlers,
        'direct_relationships': direct_rels,
        'common_opponent_relationships': common_opp_rels
    }


def load_data_from_files(season: int, data_dir: str = "mt/rankings_data") -> Dict[str, Dict]:
    """
    Load previously saved data from JSON files.
    
    Args:
        season: Season year
        data_dir: Directory containing saved data
        
    Returns:
        Dictionary mapping weight_class -> weight_class_data
    """
    data_path = Path(data_dir) / str(season)
    
    if not data_path.exists():
        raise FileNotFoundError(f"Data directory not found: {data_path}")
    
    data_by_weight = {}
    
    for wc_file in sorted(data_path.glob("weight_class_*.json")):
        weight_class = wc_file.stem.replace("weight_class_", "")
        with open(wc_file, 'r', encoding='utf-8') as f:
            data_by_weight[weight_class] = json.load(f)
    
    return data_by_weight


def build_all_relationships(season: int, data_dir: str = "mt/rankings_data") -> Dict[str, Dict]:
    """
    Build relationships for all weight classes.
    
    Args:
        season: Season year
        data_dir: Directory containing saved data
        
    Returns:
        Dictionary mapping weight_class -> relationships_data
    """
    print(f"Building relationships for season {season}...")
    
    # Load data
    data_by_weight = load_data_from_files(season, data_dir)
    
    if not data_by_weight:
        raise ValueError(f"No data found for season {season}")
    
    # Build relationships for each weight class
    relationships_by_weight = {}
    
    for weight_class in sorted(data_by_weight.keys()):
        print(f"\nWeight class {weight_class}:")
        relationships_by_weight[weight_class] = build_relationships_for_weight_class(
            data_by_weight[weight_class]
        )
    
    return relationships_by_weight


def save_relationships(relationships_by_weight: Dict[str, Dict], season: int, output_dir: str = "mt/rankings_data"):
    """
    Save relationships to JSON files.
    
    Args:
        relationships_by_weight: Dictionary from build_all_relationships
        season: Season year
        output_dir: Directory to save files
    """
    output_path = Path(output_dir) / str(season)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Convert tuple keys to strings for JSON serialization
    def convert_relationships(rels):
        converted = {}
        for key, value in rels.items():
            if isinstance(key, tuple):
                key_str = f"{key[0]}_{key[1]}"
            else:
                key_str = str(key)
            converted[key_str] = value
        return converted
    
    for weight_class, rel_data in relationships_by_weight.items():
        # Create a serializable version
        serializable = {
            'wrestlers': rel_data['wrestlers'],
            'direct_relationships': convert_relationships(rel_data['direct_relationships']),
            'common_opponent_relationships': convert_relationships(rel_data['common_opponent_relationships'])
        }
        
        rel_file = output_path / f"relationships_{weight_class}.json"
        with open(rel_file, 'w', encoding='utf-8') as f:
            json.dump(serializable, f, indent=2)
        print(f"Saved relationships for {weight_class} to {rel_file}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Build relationship matrix from loaded wrestling data')
    parser.add_argument('-season', type=int, required=True, help='Season year (e.g., 2026)')
    parser.add_argument('-data-dir', default='mt/rankings_data', help='Directory containing loaded data')
    parser.add_argument('-save', action='store_true', help='Save relationships to JSON files')
    args = parser.parse_args()
    
    relationships = build_all_relationships(args.season, args.data_dir)
    
    if args.save:
        save_relationships(relationships, args.season, args.data_dir)
    
    # Print summary
    print(f"\n=== Summary ===")
    for wc in sorted(relationships.keys()):
        rel_data = relationships[wc]
        direct_count = len(rel_data['direct_relationships'])
        co_count = len(rel_data['common_opponent_relationships'])
        wrestler_count = len(rel_data['wrestlers'])
        print(f"{wc}: {wrestler_count} wrestlers, {direct_count} direct relationships, {co_count} common opponent relationships")

