#!/usr/bin/env python3
"""
Load wrestling data from processed JSON files.

This script reads all team data from mt/processed_data/{season}/ and organizes
wrestlers and matches by weight class for ranking purposes.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict
import re
import hashlib
from datetime import datetime


# Standard weight classes for KY HS Boys
KY_HS_BOYS_WEIGHTS = [106, 113, 120, 126, 132, 138, 144, 150, 157, 165, 175, 190, 215, 285]

# Standard weight classes for KY HS Girls
KY_HS_GIRLS_WEIGHTS = [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235]


def normalize_weight_class_hs_boys(weight_str: str) -> Optional[str]:
    """
    Normalize weight class for KY HS Boys to one of the 14 standard weights.
    
    Rules:
    1. Strip prefixes (F, JV, M, etc.) and extract numeric weight
    2. Map to nearest standard weight class
    3. Standard weights: 106, 113, 120, 126, 132, 138, 144, 150, 157, 165, 175, 190, 215, 285
    
    Args:
        weight_str: Weight class string (e.g., "F145", "215 JV", "f100", "M190")
        
    Returns:
        Normalized weight class string (e.g., "144", "215", "106", "190") or None if invalid
    """
    if not weight_str:
        return None
    
    # Strip whitespace and convert to string
    weight_str = str(weight_str).strip()
    
    # Remove common prefixes (F, JV, M, etc.) - case insensitive
    # Pattern: optional letter(s) at start, then numbers, then optional " JV" or other suffix
    weight_str = re.sub(r'^[A-Za-z]+', '', weight_str)  # Remove leading letters
    weight_str = re.sub(r'\s+JV.*$', '', weight_str, flags=re.IGNORECASE)  # Remove " JV" suffix
    weight_str = re.sub(r'\s+.*$', '', weight_str)  # Remove any remaining suffix
    
    # Extract numeric weight
    try:
        weight_num = int(weight_str)
    except ValueError:
        return None
    
    # Map to nearest standard weight
    # Find the closest standard weight
    closest_weight = min(KY_HS_BOYS_WEIGHTS, key=lambda x: abs(x - weight_num))
    
    return str(closest_weight)


def create_synthetic_opponent_id(opponent_name: str, opponent_team: str) -> str:
    """
    Create a synthetic ID for an out-of-state opponent based on name and team.
    This allows us to track out-of-state wrestlers for common opponent analysis.
    
    Args:
        opponent_name: Opponent's name
        opponent_team: Opponent's team/school
        
    Returns:
        Synthetic ID string (e.g., "OUTSTATE_abc123...")
    """
    # Create a hash from name+team to ensure consistency
    key = f"{opponent_name}|{opponent_team}".lower().strip()
    hash_obj = hashlib.md5(key.encode('utf-8'))
    hash_hex = hash_obj.hexdigest()[:12]  # Use first 12 chars of hash
    return f"OUTSTATE_{hash_hex}"


def normalize_weight_class_hs_girls(weight_str: str) -> Optional[str]:
    """
    Normalize weight class for KY HS Girls to one of the 12 standard weights.
    
    Rules:
    1. Strip prefixes (F, JV, M, etc.) and extract numeric weight
    2. Map to nearest standard weight class
    3. Standard weights: 100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235
    
    Args:
        weight_str: Weight class string (e.g., "F145", "185 JV", "f100", "M152")
        
    Returns:
        Normalized weight class string (e.g., "145", "185", "100", "152") or None if invalid
    """
    if not weight_str:
        return None
    
    # Strip whitespace and convert to string
    weight_str = str(weight_str).strip()
    
    # Remove common prefixes (F, JV, M, etc.) - case insensitive
    # Pattern: optional letter(s) at start, then numbers, then optional " JV" or other suffix
    weight_str = re.sub(r'^[A-Za-z]+', '', weight_str)  # Remove leading letters
    weight_str = re.sub(r'\s+JV.*$', '', weight_str, flags=re.IGNORECASE)  # Remove " JV" suffix
    weight_str = re.sub(r'\s+.*$', '', weight_str)  # Remove any remaining suffix
    
    # Extract numeric weight
    try:
        weight_num = int(weight_str)
    except ValueError:
        return None
    
    # Map to nearest standard weight
    # Find the closest standard weight
    closest_weight = min(KY_HS_GIRLS_WEIGHTS, key=lambda x: abs(x - weight_num))
    
    return str(closest_weight)


def normalize_weight_class(weight_str: str, league: str = 'ncaa', state: str = None, gender: str = None) -> Optional[str]:
    """
    Normalize weight class based on league type.
    
    For KY HS Boys, applies special normalization to map to 14 standard weights.
    For KY HS Girls, applies special normalization to map to 12 standard weights.
    For other leagues, returns weight as-is (or with minimal normalization).
    
    Args:
        weight_str: Weight class string
        league: League type ('ncaa' or 'hs')
        state: State code (for HS)
        gender: Gender ('boys' or 'girls', for HS)
        
    Returns:
        Normalized weight class string or None if invalid
    """
    if league == 'hs' and state and state.upper() == 'KY' and gender == 'boys':
        return normalize_weight_class_hs_boys(weight_str)
    elif league == 'hs' and state and state.upper() == 'KY' and gender == 'girls':
        return normalize_weight_class_hs_girls(weight_str)
    else:
        # For NCAA and other leagues, return as-is (or with basic normalization)
        return str(weight_str).strip() if weight_str else None


def load_team_data(season: int, league: str = 'ncaa', state: str = None, gender: str = None) -> List[Dict]:
    """
    Load all team data files for a season.
    
    Args:
        season: Season year (e.g., 2026)
        league: League type ('ncaa' or 'hs')
        state: State code (required for HS)
        gender: Gender ('boys' or 'girls', required for HS)
        
    Returns:
        List of team data dictionaries
    """
    # Setup directory based on league type
    if league == 'hs':
        state_lower = state.lower() if state else 'ky'
        data_dir = Path(f"mt/processed_data/hs_{state_lower}_{gender}")
    else:  # ncaa
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


def load_match_overrides(season: int, data_dir: str = "mt/rankings_data", league: str = 'ncaa', state: str = None, gender: str = None) -> Dict[Tuple[str, str, str], Dict]:
    """
    Load match overrides for a season.
    
    Returns a dictionary mapping (w1_id, w2_id, date) -> override_dict
    where IDs are normalized (smaller ID first).
    """
    # Setup override path based on league type
    if league == 'hs':
        state_lower = state.lower() if state else 'ky'
        overrides_path = Path(data_dir) / f"hs_{state_lower}_{gender}" / str(season) / "match_overrides.json"
    else:  # ncaa
        overrides_path = Path(data_dir) / str(season) / "match_overrides.json"
    override_map = {}
    
    if overrides_path.exists():
        try:
            with overrides_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            for ov in data.get("overrides", []):
                w1 = ov.get("wrestler1_id")
                w2 = ov.get("wrestler2_id")
                date = ov.get("date")
                if w1 and w2 and date:
                    # Normalize IDs (smaller first)
                    w1_norm, w2_norm = tuple(sorted([w1, w2]))
                    key = (w1_norm, w2_norm, date)
                    override_map[key] = ov
        except Exception as e:
            print(f"Warning: Could not load match overrides: {e}")
    
    return override_map


def apply_match_overrides(data: Dict[str, Dict], season: int, data_dir: str = "mt/rankings_data", league: str = 'ncaa', state: str = None, gender: str = None) -> None:
    """
    Apply match overrides to deduplicated match data.
    
    This should be called AFTER deduplication, so that overrides are applied
    to the final deduplicated matches. Overrides are matched by (w1_id, w2_id, date)
    where IDs are normalized (smaller ID first).
    
    Args:
        data: Dictionary mapping weight_class -> {wrestlers: {}, matches: []}
        season: Season year
        data_dir: Directory containing match_overrides.json
        league: League type ('ncaa' or 'hs')
        state: State code (required for HS)
        gender: Gender ('boys' or 'girls', required for HS)
    """
    match_overrides = load_match_overrides(season, data_dir, league=league, state=state, gender=gender)
    
    if not match_overrides:
        return
    
    override_count = 0
    
    for wc, wc_data in data.items():
        matches = wc_data.get("matches", [])
        for match in matches:
            w1 = match.get("wrestler1_id")
            w2 = match.get("wrestler2_id")
            date = match.get("date")
            
            if not w1 or not w2 or not date:
                continue
            
            # Normalize IDs (smaller first) to match override key format
            w1_norm, w2_norm = tuple(sorted([w1, w2]))
            override_key = (w1_norm, w2_norm, date)
            override = match_overrides.get(override_key)
            
            if override:
                # Apply override: replace winner_id and result
                match["winner_id"] = override.get("winner_id", match.get("winner_id"))
                match["result"] = override.get("result", match.get("result"))
                
                # Override weight class if specified
                if override.get("weight_class"):
                    match["weight_class"] = override.get("weight_class")
                
                # Override event if specified
                if override.get("event"):
                    match["event"] = override.get("event")
                
                override_count += 1
    
    if override_count > 0:
        print(f"Applied {override_count} match override(s)")


def extract_wrestlers_and_matches(teams: List[Dict], season: int = None, data_dir: str = "mt/rankings_data", league: str = 'ncaa', state: str = None, gender: str = None) -> Dict[str, Dict]:
    """
    Extract all wrestlers and their matches, organized by weight class.
    
    Only includes wrestlers with valid IDs from D1 teams.
    Only processes matches where both wrestlers have valid IDs.
    
    Args:
        teams: List of team data dictionaries
        season: Season year (optional, used for loading match overrides)
        data_dir: Directory containing rankings data (for overrides)
        
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
                # Normalize primary weight class
                primary_wc = wrestler.get('weight_class', '')
                normalized_primary_wc = normalize_weight_class(primary_wc, league, state, gender) if primary_wc else ''
                
                all_wrestlers[wrestler_id] = {
                    'id': wrestler_id,
                    'name': wrestler_name,
                    'team': team_name,
                    'weight_class': normalized_primary_wc or primary_wc,  # Use normalized if available, fallback to original
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
                
                # Get opponent ID and identify opponent from match
                opponent_id = match.get('opponent_id')
                winner_name = match.get('winner_name', '')
                loser_name = match.get('loser_name', '')
                winner_team = match.get('winner_team', '')
                loser_team = match.get('loser_team', '')
                
                # Determine opponent name and team
                if winner_name == wrestler_name and winner_team == team_name:
                    # This wrestler won, opponent is the loser
                    opponent_name = loser_name
                    opponent_team = loser_team
                elif loser_name == wrestler_name and loser_team == team_name:
                    # This wrestler lost, opponent is the winner
                    opponent_name = winner_name
                    opponent_team = winner_team
                else:
                    # Can't determine opponent reliably, skip
                    continue
                
                # For HS: Handle matches with null opponent_id by creating synthetic opponents
                # For NCAA: Skip matches with null opponent_id (unchanged behavior)
                if not opponent_id or opponent_id == 'null' or opponent_id == '':
                    if league == 'hs':
                        # Create synthetic opponent ID for out-of-state wrestlers
                        if not opponent_name or not opponent_team:
                            # Can't create synthetic opponent without name/team
                            continue
                        opponent_id = create_synthetic_opponent_id(opponent_name, opponent_team)
                        
                        # Add synthetic opponent to all_wrestlers if not already present
                        if opponent_id not in all_wrestlers:
                            all_wrestlers[opponent_id] = {
                                'id': opponent_id,
                                'name': opponent_name,
                                'team': opponent_team,
                                'weight_class': '',  # Will be determined from matches
                                'grade': '',
                                'wins': 0,
                                'losses': 0,
                                'matches_count': 0,
                                'is_synthetic': True  # Mark as synthetic for reference
                            }
                    else:
                        # NCAA: Skip matches with null opponent_id (unchanged behavior)
                        continue
                
                # Get the weight class for this match (before checking if opponent is in all_wrestlers)
                # This ensures we can use match weight for weight assignment even for out-of-state opponents
                match_weight_raw = match.get('weight', '') or primary_weight_class
                if not match_weight_raw:
                    continue
                
                # Normalize weight class for HS Boys
                match_weight = normalize_weight_class(match_weight_raw, league, state, gender) or match_weight_raw
                match_date = match.get('date', '')
                
                # If opponent is not in our wrestler list (for NCAA with valid ID but not in dataset)
                # For HS, synthetic opponents are already added to all_wrestlers above (for null opponent_id)
                # But out-of-state opponents with valid IDs may not be in all_wrestlers
                if opponent_id not in all_wrestlers:
                    # This happens for:
                    # - NCAA: opponent has valid ID but isn't in dataset
                    # - HS: out-of-state opponent with valid ID (not null, so no synthetic ID created)
                    
                    # Build a key so we don't double-count if this match appears
                    # multiple times in the source data.
                    local_key = ('nonD1', wrestler_id, opponent_id, match_date, result)
                    if local_key not in processed_matches_for_stats:
                        if (winner_name == wrestler_name and winner_team == team_name):
                            wrestler_info['wins'] += 1
                        elif (loser_name == wrestler_name and loser_team == team_name):
                            wrestler_info['losses'] += 1
                        wrestler_info['matches_count'] += 1
                        processed_matches_for_stats.add(local_key)
                    
                    # For HS: Still add match to wrestler_matches for weight assignment
                    # For NCAA: Do not include this match in wrestler_matches (unchanged behavior)
                    if league == 'hs':
                        wrestler_matches[wrestler_id].append((match, match_weight, match_date))
                        # Note: opponent_id not in all_wrestlers, so we don't add to opponent's matches
                        # But the match weight is still recorded for the KY wrestler's weight assignment
                    
                    # Do not include this match in global match lists used for relationships
                    # (NCAA behavior unchanged, HS: already handled via synthetic opponents for null IDs)
                    continue
                
                # Store match info for weight-class determination for BOTH wrestlers.
                # Even if we cannot later determine the winner/loser reliably, these
                # entries still help with weight assignment based on where they wrestled.
                wrestler_matches[wrestler_id].append((match, match_weight, match_date))
                wrestler_matches[opponent_id].append((match, match_weight, match_date))
                
                # Get opponent info (may be synthetic for HS out-of-state opponents)
                opponent_info = all_wrestlers[opponent_id]
                
                # Determine winner using ID and, as a fallback, name+team.
                is_winner = (wrestler_id == match.get('winner_id', '') or 
                             (wrestler_name == winner_name and team_name == winner_team))
                is_loser = (wrestler_id == match.get('loser_id', '') or
                           (wrestler_name == loser_name and team_name == loser_team))
                
                if not (is_winner or is_loser):
                    # Can't determine result reliably: we've already recorded the match
                    # for weight-assignment purposes above, but we skip stats/relationships.
                    continue
                
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
                # Use (w1, w2, date) as the base key - this identifies the match uniquely
                # regardless of which team's file it came from or what the original result was
                match_identity_key = (w1_id_normalized, w2_id_normalized, match_date)
                
                # Store match by key to avoid duplicates
                if match_weight not in weight_classes:
                    weight_classes[match_weight] = {'wrestlers': {}, 'matches': [], 'match_keys': set()}
                elif 'match_keys' not in weight_classes[match_weight]:
                    weight_classes[match_weight]['match_keys'] = set()
                
                # Only add if we haven't seen this match before (by identity, not by result)
                # This ensures that if a match appears in both team files, we only add it once
                # The override is applied before this check, so both instances will have the
                # same overridden result and will be deduplicated correctly
                if match_identity_key not in weight_classes[match_weight]['match_keys']:
                    weight_classes[match_weight]['matches'].append(match_record)
                    weight_classes[match_weight]['match_keys'].add(match_identity_key)
                
                # Update wrestler stats (only once per unique match)
                # Use the same identity key for stats to ensure we don't double-count
                if match_identity_key not in processed_matches_for_stats:
                    if is_winner:
                        wrestler_info['wins'] += 1
                        opponent_info['losses'] += 1
                    else:
                        wrestler_info['losses'] += 1
                        opponent_info['wins'] += 1
                    
                    wrestler_info['matches_count'] += 1
                    opponent_info['matches_count'] += 1
                    
                    processed_matches_for_stats.add(match_identity_key)
    
    # Third pass: determine weight class assignment for each wrestler
    wrestler_weight_class = {}  # wrestler_id -> assigned weight_class

    # ========================================================================
    # NEW HS WEIGHT CHANGE LOGIC (Threshold + Confirmation System)
    # ========================================================================
    
    def evaluate_weight_threshold(matches: List[Tuple], current_weight: str, league: str, state: str, gender: str) -> Optional[str]:
        """
        Evaluate weight change threshold based on last 7 matches.
        
        Returns:
            Proposed weight if threshold met, None otherwise
        """
        if not matches:
            return None
        
        # Sort matches by date (most recent first)
        sorted_matches = sorted(matches, key=lambda x: parse_date(x[2]), reverse=True)
        
        # Take last 7 matches (or fewer if <7 exist)
        recent_matches = sorted_matches[:7]
        
        if len(recent_matches) < 7:
            # Simple majority if <7 matches
            weight_counts = defaultdict(int)
            for _, match_weight, _ in recent_matches:
                normalized = normalize_weight_class(match_weight, league, state, gender) or match_weight
                weight_counts[normalized] += 1
            
            if weight_counts:
                most_common = max(weight_counts.items(), key=lambda x: x[1])[0]
                if most_common != current_weight:
                    return most_common
            return None
        
        # Count weights in last 7 matches
        weight_counts = defaultdict(int)
        for _, match_weight, _ in recent_matches:
            normalized = normalize_weight_class(match_weight, league, state, gender) or match_weight
            weight_counts[normalized] += 1
        
        if not weight_counts:
            return None
        
        # Get current weight as integer for comparison
        try:
            current_weight_int = int(current_weight) if current_weight else None
        except (ValueError, TypeError):
            current_weight_int = None
        
        # Get all weight classes for comparison
        if league == 'hs' and state and state.upper() == 'KY':
            if gender == 'boys':
                valid_weights = KY_HS_BOYS_WEIGHTS
            elif gender == 'girls':
                valid_weights = KY_HS_GIRLS_WEIGHTS
            else:
                valid_weights = []
        else:
            valid_weights = []
        
        # Check for moving DOWN (to lower weight)
        # Check ALL lower weights, not just adjacent
        if current_weight_int and valid_weights:
            current_idx = valid_weights.index(current_weight_int) if current_weight_int in valid_weights else -1
            if current_idx > 0:
                # Check all weights below current weight
                best_lower_weight = None
                best_lower_count = 0
                
                for i in range(current_idx - 1, -1, -1):  # Check from adjacent down to lowest
                    lower_weight = str(valid_weights[i])
                    count_at_lower = weight_counts.get(lower_weight, 0)
                    if count_at_lower >= 3:  # Threshold met
                        # Prefer the weight with highest count, or closest if tied
                        if count_at_lower > best_lower_count:
                            best_lower_weight = lower_weight
                            best_lower_count = count_at_lower
                        elif count_at_lower == best_lower_count and best_lower_weight:
                            # If tied, prefer the one closer to current weight (higher weight)
                            if int(lower_weight) > int(best_lower_weight):
                                best_lower_weight = lower_weight
                
                if best_lower_weight:
                    return best_lower_weight
        
        # Check for moving UP (to higher weight)
        # Check ALL higher weights, not just adjacent
        if current_weight_int and valid_weights:
            current_idx = valid_weights.index(current_weight_int) if current_weight_int in valid_weights else -1
            if current_idx >= 0 and current_idx < len(valid_weights) - 1:
                # Check all weights above current weight
                best_higher_weight = None
                best_higher_count = 0
                
                for i in range(current_idx + 1, len(valid_weights)):  # Check from adjacent up to highest
                    higher_weight = str(valid_weights[i])
                    count_at_higher = weight_counts.get(higher_weight, 0)
                    if count_at_higher >= 6:  # Threshold met
                        # Prefer the weight with highest count, or closest if tied
                        if count_at_higher > best_higher_count:
                            best_higher_weight = higher_weight
                            best_higher_count = count_at_higher
                        elif count_at_higher == best_higher_count and best_higher_weight:
                            # If tied, prefer the one closer to current weight (lower weight)
                            if int(higher_weight) < int(best_higher_weight):
                                best_higher_weight = higher_weight
                
                if best_higher_weight:
                    return best_higher_weight
        
        # No threshold met
        return None
    
    def is_wrestler_ranked(wrestler_id: str, weight: str, season: int, league: str, state: str, gender: str, data_dir: str) -> bool:
        """
        Check if wrestler is ranked in top 40 (boys) or top 24 (girls) at their current weight.
        
        Note: Rankings files may not exist on first run of load_data (before rankings are generated).
        In that case, returns False (unranked), which means weight changes will be auto-applied.
        On subsequent runs after rankings are generated, this will correctly identify ranked wrestlers.
        
        Returns:
            True if ranked, False otherwise (including if rankings file doesn't exist)
        """
        if league != 'hs':
            return False  # Only applies to HS
        
        # Determine top N based on gender
        top_n = 24 if gender == 'girls' else 40
        
        # Load rankings for this weight
        state_lower = state.lower() if state else 'ky'
        rankings_path = Path(data_dir) / f"hs_{state_lower}_{gender}" / str(season) / f"rankings_{weight}.json"
        
        if not rankings_path.exists():
            # Rankings don't exist yet (first run) - treat as unranked
            return False
        
        try:
            with open(rankings_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            rankings = data.get('rankings', [])
            
            # Check if wrestler is in top N
            for entry in rankings[:top_n]:
                if entry.get('wrestler_id') == wrestler_id:
                    rank = entry.get('rank')
                    if rank and isinstance(rank, int) and rank <= top_n:
                        return True
            
            return False
        except Exception:
            # Error reading rankings - treat as unranked to be safe
            return False
    
    def load_weight_confirmations(season: int, league: str, state: str, gender: str, data_dir: str) -> Dict[str, Dict]:
        """
        Load weight confirmation state from weight_confirmation.json.
        
        Returns:
            Dict mapping wrestler_id -> {confirmed_weight, last_reviewed_match_date}
        """
        if league != 'hs':
            return {}
        
        state_lower = state.lower() if state else 'ky'
        confirmations_path = Path(data_dir) / f"hs_{state_lower}_{gender}" / str(season) / "weight_confirmation.json"
        
        if not confirmations_path.exists():
            return {}
        
        try:
            with open(confirmations_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get('confirmations', {})
        except Exception:
            return {}
    
    def save_weight_confirmations(confirmations: Dict[str, Dict], season: int, league: str, state: str, gender: str, data_dir: str) -> None:
        """Save weight confirmation state to weight_confirmation.json."""
        if league != 'hs':
            return
        
        state_lower = state.lower() if state else 'ky'
        confirmations_path = Path(data_dir) / f"hs_{state_lower}_{gender}" / str(season) / "weight_confirmation.json"
        confirmations_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            'confirmations': confirmations,
            'last_updated': datetime.now().isoformat()
        }
        
        with open(confirmations_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    
    def get_most_recent_match_date(matches: List[Tuple]) -> Optional[str]:
        """Get the most recent match date from a list of matches."""
        if not matches:
            return None
        
        sorted_matches = sorted(matches, key=lambda x: parse_date(x[2]), reverse=True)
        return sorted_matches[0][2] if sorted_matches else None
    
    def compare_dates(date1: str, date2: str) -> int:
        """
        Compare two dates in MM/DD/YYYY format.
        Returns: -1 if date1 < date2, 0 if equal, 1 if date1 > date2
        """
        d1_tuple = parse_date(date1)
        d2_tuple = parse_date(date2)
        if d1_tuple < d2_tuple:
            return -1
        elif d1_tuple > d2_tuple:
            return 1
        return 0
    
    def prompt_weight_confirmation(
        wrestler_info: Dict,
        current_weight: str,
        proposed_weight: str,
        matches: List[Tuple],
        team_wrestlers: Dict[str, Dict],
        league: str,
        state: str,
        gender: str,
        season: int,
        data_dir: str
    ) -> Tuple[str, str]:
        """
        Interactive prompt for weight change confirmation.
        
        Returns:
            Tuple of (confirmed_weight, last_reviewed_match_date)
        """
        wrestler_id = wrestler_info['id']
        name = wrestler_info.get('name', 'Unknown')
        team = wrestler_info.get('team', 'Unknown')
        
        print(f"\n{'='*80}")
        print(f"WEIGHT CHANGE PROPOSAL - RANKED WRESTLER")
        print(f"{'='*80}")
        print(f"Wrestler: {name} ({team})")
        print(f"Current confirmed weight: {current_weight}")
        print(f"Proposed weight: {proposed_weight}")
        
        # Count matches at proposed weight
        sorted_matches = sorted(matches, key=lambda x: parse_date(x[2]), reverse=True)
        recent_7 = sorted_matches[:7]
        count_at_proposed = sum(1 for _, w, _ in recent_7 if normalize_weight_class(w, league, state, gender) == proposed_weight)
        print(f"Threshold reason: {count_at_proposed} of last 7 matches at {proposed_weight}")
        
        # Show last 10 matches
        print(f"\nLast 10 matches (most recent first):")
        print(f"{'Date':<12} {'Weight':<8} {'Result':<20}")
        print(f"{'-'*40}")
        for _, match_weight, match_date in sorted_matches[:10]:
            normalized_weight = normalize_weight_class(match_weight, league, state, gender) or match_weight
            # Try to get result from match if available
            result = "—"
            print(f"{match_date:<12} {normalized_weight:<8} {result:<20}")
        
        # Show team context
        print(f"\nTeam context:")
        team_name = team
        current_weight_int = int(current_weight) if current_weight.isdigit() else None
        
        if league == 'hs' and state and state.upper() == 'KY':
            if gender == 'boys':
                valid_weights = KY_HS_BOYS_WEIGHTS
            elif gender == 'girls':
                valid_weights = KY_HS_GIRLS_WEIGHTS
            else:
                valid_weights = []
        else:
            valid_weights = []
        
        weights_to_show = []
        if current_weight_int and current_weight_int in valid_weights:
            current_idx = valid_weights.index(current_weight_int)
            if current_idx > 0:
                weights_to_show.append(str(valid_weights[current_idx - 1]))
            weights_to_show.append(str(current_weight_int))
            if current_idx < len(valid_weights) - 1:
                weights_to_show.append(str(valid_weights[current_idx + 1]))
        
        # Helper function to find wrestler's rank across all weight classes
        def find_wrestler_rank(wid: str, all_weights: List[int]) -> Optional[Tuple[int, int]]:
            """
            Find wrestler's rank across all weight classes.
            Returns: (weight, rank) if found, None otherwise
            """
            state_lower = state.lower() if state else 'ky'
            top_n = 24 if gender == 'girls' else 40
            
            for weight in all_weights:
                rankings_path = Path(data_dir) / f"hs_{state_lower}_{gender}" / str(season) / f"rankings_{weight}.json"
                if not rankings_path.exists():
                    continue
                
                try:
                    with open(rankings_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    rankings = data.get('rankings', [])
                    
                    # Check top N only
                    for entry in rankings[:top_n]:
                        if entry.get('wrestler_id') == wid:
                            rank = entry.get('rank')
                            if rank and isinstance(rank, int) and rank <= top_n:
                                return (weight, rank)
                except Exception:
                    continue
            
            return None
        
        # Build map of wrestlers by their RANKED weight (not roster weight)
        wrestlers_by_ranked_weight = defaultdict(list)  # weight -> [(wid, winfo, rank)]
        
        for wid, winfo in team_wrestlers.items():
            rank_info = find_wrestler_rank(wid, valid_weights)
            if rank_info:
                rank_weight, rank = rank_info
                wrestlers_by_ranked_weight[rank_weight].append((wid, winfo, rank))
            else:
                # Unranked wrestlers - check if they have a confirmed weight from weight_confirmations
                # (This helps show unranked wrestlers at their confirmed weight)
                # For now, we'll only show ranked wrestlers in team context
                pass
        
        # Display wrestlers grouped by their RANKED weight
        for w in weights_to_show:
            w_int = int(w)
            wrestlers_at_weight = wrestlers_by_ranked_weight.get(w_int, [])
            
            if wrestlers_at_weight:
                print(f"\n  Weight {w}:")
                # Sort by rank
                wrestlers_at_weight.sort(key=lambda x: x[2])  # Sort by rank
                for wid, winfo, rank in wrestlers_at_weight:
                    print(f"    - {winfo.get('name', 'Unknown')} (#{rank})")
        
        # Prompt for decision
        while True:
            response = input(f"\nAccept weight change to {proposed_weight}? [a]ccept / [r]eject: ").strip().lower()
            if response in ['a', 'accept']:
                most_recent_date = get_most_recent_match_date(matches)
                return proposed_weight, most_recent_date or ''
            elif response in ['r', 'reject']:
                most_recent_date = get_most_recent_match_date(matches)
                return current_weight, most_recent_date or ''
            else:
                print("Invalid response. Please enter 'a' to accept or 'r' to reject.")
    
    # Load weight confirmations
    weight_confirmations = load_weight_confirmations(season, league, state, gender, data_dir) if league == 'hs' else {}
    
    # Load manual weight overrides (virtual match hints) if present.
    # File format (mt/rankings_data/{season}/weight_overrides.json for NCAA or
    # mt/rankings_data/hs_{state}_{gender}/weight_overrides.json for HS):
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
    # Setup weight overrides path based on league type
    if league == 'hs':
        state_lower = state.lower() if state else 'ky'
        overrides_path = Path(data_dir) / f"hs_{state_lower}_{gender}" / str(season) / "weight_overrides.json"
    else:  # ncaa
        overrides_path = Path(data_dir) / str(season) / "weight_overrides.json"
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
                # Normalize weight before storing
                normalized_weight = normalize_weight_class(weight, league, state, gender) or weight
                overrides_by_wrestler[wid].append((normalized_weight, date, count))
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
        # Normalize override weights before adding
        for weight, date, count in overrides_by_wrestler.get(wrestler_id, []):
            normalized_weight = normalize_weight_class(weight, league, state, gender) or weight
            for _ in range(max(0, count)):
                matches.append((None, normalized_weight, date))
        
        primary_weight = wrestler_info['weight_class']
        
        # NEW HS WEIGHT CHANGE LOGIC
        if league == 'hs' and state and state.upper() == 'KY':
            # Get current confirmed weight from confirmations, or use primary weight
            confirmation = weight_confirmations.get(wrestler_id, {})
            current_confirmed_weight = confirmation.get('confirmed_weight', primary_weight)
            last_reviewed_date = confirmation.get('last_reviewed_match_date', '')
            
            # Normalize current confirmed weight
            current_confirmed_weight = normalize_weight_class(current_confirmed_weight, league, state, gender) or current_confirmed_weight
            
            # Evaluate weight threshold
            proposed_weight = None
            if matches:
                proposed_weight = evaluate_weight_threshold(matches, current_confirmed_weight, league, state, gender)
            
            # Determine if weight change is needed
            if proposed_weight and proposed_weight != current_confirmed_weight:
                # Check if wrestler is ranked
                is_ranked = is_wrestler_ranked(wrestler_id, current_confirmed_weight, season, league, state, gender, data_dir)
                
                if is_ranked:
                    # Ranked wrestler: check if new match exists
                    most_recent_match_date = get_most_recent_match_date(matches)
                    
                    # Check if we need to prompt (new match exists OR never reviewed)
                    needs_prompt = False
                    if not last_reviewed_date:
                        needs_prompt = True
                    elif most_recent_match_date:
                        # Compare dates properly
                        if compare_dates(most_recent_match_date, last_reviewed_date) > 0:
                            needs_prompt = True
                    
                    if needs_prompt:
                        # Prompt for confirmation
                        # Get team wrestlers for context
                        team_name = wrestler_info.get('team', '')
                        team_wrestlers_dict = {
                            wid: info for wid, info in all_wrestlers.items()
                            if info.get('team') == team_name
                        }
                        
                        confirmed_weight, reviewed_date = prompt_weight_confirmation(
                            wrestler_info,
                            current_confirmed_weight,
                            proposed_weight,
                            matches,
                            team_wrestlers_dict,
                            league,
                            state,
                            gender,
                            season,
                            data_dir
                        )
                        
                        # Update confirmation state
                        weight_confirmations[wrestler_id] = {
                            'confirmed_weight': confirmed_weight,
                            'last_reviewed_match_date': reviewed_date
                        }
                        
                        # Save immediately after confirmation to preserve state if interrupted
                        save_weight_confirmations(weight_confirmations, season, league, state, gender, data_dir)
                        
                        assigned_weight = confirmed_weight
                    else:
                        # No new match, keep current confirmed weight
                        assigned_weight = current_confirmed_weight
                else:
                    # Unranked wrestler: auto-apply weight change
                    assigned_weight = proposed_weight
                    # Update confirmation state
                    most_recent_match_date = get_most_recent_match_date(matches)
                    weight_confirmations[wrestler_id] = {
                        'confirmed_weight': proposed_weight,
                        'last_reviewed_match_date': most_recent_match_date or ''
                    }
                    # Save immediately for unranked auto-applies too (in case of interruption)
                    save_weight_confirmations(weight_confirmations, season, league, state, gender, data_dir)
            else:
                # No threshold met or no change needed
                assigned_weight = current_confirmed_weight
        else:
            # NCAA or non-HS: use original logic
            if len(matches) == 0:
                # No matches: use primary weight (already normalized)
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
        
        # Normalize assigned weight one more time to ensure consistency
        assigned_weight = normalize_weight_class(assigned_weight, league, state, gender) or assigned_weight

        wrestler_weight_class[wrestler_id] = assigned_weight
    
    # Save weight confirmations (HS only)
    if league == 'hs':
        save_weight_confirmations(weight_confirmations, season, league, state, gender, data_dir)
    
    # Add wrestlers to their assigned weight classes
    # Note: Synthetic opponents are included here for relationship building (common opponent analysis)
    # but will be filtered out when generating rankings matrices
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
    # For HS Boys and Girls, only keep the standard weight classes
    result = {}
    for wc, data in weight_classes.items():
        if data['wrestlers']:  # Only include weight classes with wrestlers
            # For KY HS Boys, filter to only standard weights
            if league == 'hs' and state and state.upper() == 'KY' and gender == 'boys':
                if wc not in [str(w) for w in KY_HS_BOYS_WEIGHTS]:
                    # Skip non-standard weights for HS Boys
                    continue
            # For KY HS Girls, filter to only standard weights
            elif league == 'hs' and state and state.upper() == 'KY' and gender == 'girls':
                if wc not in [str(w) for w in KY_HS_GIRLS_WEIGHTS]:
                    # Skip non-standard weights for HS Girls
                    continue
            result[wc] = {
                'wrestlers': data['wrestlers'],
                'matches': data['matches']
            }
    
    # Print summary
    # Count only non-synthetic wrestlers for summary (these are the rankable wrestlers)
    non_synthetic_count = sum(1 for w in all_wrestlers.values() if not w.get('is_synthetic', False))
    synthetic_count = sum(1 for w in all_wrestlers.values() if w.get('is_synthetic', False))
    print(f"\nData Summary:")
    print(f"Total wrestlers: {non_synthetic_count} (rankable)")
    if synthetic_count > 0:
        print(f"Out-of-state opponents: {synthetic_count} (included in relationships for common opponent analysis, excluded from rankings)")
    
    # Count rankable wrestlers per weight class (excluding synthetic)
    for wc in sorted(result.keys()):
        rankable_wrestlers = [w for w in result[wc]['wrestlers'].values() if not w.get('is_synthetic', False)]
        wrestler_count = len(rankable_wrestlers)
        match_count = len(result[wc]['matches'])
        print(f"  {wc}: {wrestler_count} wrestlers, {match_count} matches")
    
    return result


def load_season_data(season: int, league: str = 'ncaa', state: str = None, gender: str = None) -> Dict[str, Dict]:
    """
    Main function to load all data for a season.
    
    Args:
        season: Season year (e.g., 2026)
        league: League type ('ncaa' or 'hs')
        state: State code (required for HS)
        gender: Gender ('boys' or 'girls', required for HS)
        
    Returns:
        Dictionary mapping weight_class -> {
            'wrestlers': {wrestler_id: wrestler_info},
            'matches': [match_info]
        }
    """
    league_label = f"{league.upper()}" if league == 'ncaa' else f"{state} HS {gender.capitalize()}" if league == 'hs' else league
    print(f"Loading data for season {season} ({league_label})...")
    
    # Load team data
    teams = load_team_data(season, league=league, state=state, gender=gender)
    
    if not teams:
        raise ValueError(f"No team data found for season {season} ({league_label})")
    
    # Extract wrestlers and matches (pass season and league info for match overrides)
    data_by_weight = extract_wrestlers_and_matches(teams, season=season, league=league, state=state, gender=gender)
    
    return data_by_weight


def dedupe_matches_across_weights(data: Dict[str, Dict]) -> None:
    """
    Remove duplicate matches that appear in multiple weight classes.

    Deduplication key is based on:
      - date
      - unordered pair of wrestler IDs

    Note: We use (date, pair) as the identity key, not including winner_id or result,
    because the same match (same wrestlers, same date) should only appear once,
    regardless of which weight class file it's in or what the result was.
    
    This ensures that if a match appears in multiple weight classes (which shouldn't
    happen but could due to data issues), or if it appears in both team files with
    different original results that get unified by an override, we only keep one copy.

    This keeps the first occurrence encountered and drops later duplicates,
    so downstream tools that scan all weight_class_*.json files don't
    double-count the same bout.
    """
    seen = set()
    for wc, wc_data in data.items():
        matches = wc_data.get("matches", [])
        new_matches = []
        for m in matches:
            w1 = m.get("wrestler1_id")
            w2 = m.get("wrestler2_id")
            if not w1 or not w2:
                continue
            pair = tuple(sorted([w1, w2]))
            # Use just (date, pair) as the identity key
            # This matches the identity key used in extract_wrestlers_and_matches
            key = (
                m.get("date"),
                pair,
            )
            if key in seen:
                continue
            seen.add(key)
            new_matches.append(m)
        wc_data["matches"] = new_matches


def save_loaded_data(data: Dict[str, Dict], season: int, output_dir: str = "mt/rankings_data", league: str = 'ncaa', state: str = None, gender: str = None):
    """
    Save the loaded data to JSON files for inspection.
    
    Args:
        data: Data dictionary from load_season_data
        season: Season year
        output_dir: Directory to save files
        league: League type ('ncaa' or 'hs')
        state: State code (required for HS)
        gender: Gender ('boys' or 'girls', required for HS)
    """
    # Setup output path based on league type
    if league == 'hs':
        state_lower = state.lower() if state else 'ky'
        output_path = Path(output_dir) / f"hs_{state_lower}_{gender}" / str(season)
    else:  # ncaa
        output_path = Path(output_dir) / str(season)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # First, de-duplicate matches across all weight classes so that any given
    # bout only appears once in the weight_class_*.json files.
    dedupe_matches_across_weights(data)
    
    # Apply match overrides AFTER deduplication
    # This ensures overrides are applied to the final deduplicated matches
    apply_match_overrides(data, season, output_dir, league=league, state=state, gender=gender)
    
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
    parser.add_argument('-league', type=str, default='ncaa', choices=['ncaa', 'hs'],
                        help='League type: ncaa (default) or hs')
    parser.add_argument('-state', type=str, help='State code (required when league=hs, currently only KY supported)')
    parser.add_argument('-gender', type=str, choices=['boys', 'girls'],
                        help='Gender: boys or girls (required when league=hs)')
    args = parser.parse_args()
    
    # Validate HS parameters
    if args.league == 'hs':
        if not args.state:
            raise ValueError("-state is required when -league=hs")
        state_upper = args.state.upper()
        if state_upper != 'KY':
            raise ValueError(f"Only KY is currently supported for HS. Got: {args.state}")
        if not args.gender:
            raise ValueError("-gender is required when -league=hs")
        if args.gender not in ['boys', 'girls']:
            raise ValueError(f"-gender must be 'boys' or 'girls'. Got: {args.gender}")
    
    data = load_season_data(args.season, league=args.league, state=args.state, gender=args.gender)
    
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
        save_loaded_data(data, args.season, league=args.league, state=args.state, gender=args.gender)

