# link_and_upload_season.py
import os
import json
import re
import argparse
from pathlib import Path
from boto3 import resource
from decimal import Decimal
from collections import defaultdict
from difflib import SequenceMatcher
import sys  # Add for more detailed error printing
import boto3
from boto3.dynamodb.conditions import Key, Attr
import time
import random
import string
from datetime import datetime
from db_team_resolver import (
    load_teams_from_db,
    resolve_team,
    count_unidentified_teams,
    get_team_info,
    get_team_season
)

# Load name variations mapping
def load_name_variations():
    """Load and process name variations into lookup dictionaries."""
    try:
        with open('data/name_variations.json', 'r') as f:
            data = json.load(f)
            
        # Create lookup from any variant to its group
        variant_to_group = {}
        for group_name, group_data in data['name_groups'].items():
            for variant in group_data['variants']:
                variant_to_group[variant.lower()] = group_data['variants']
                
        return variant_to_group
    except Exception as e:
        print(f"Warning: Could not load name variations file: {e}")
        return {}

# Global variable to store name mappings
NAME_VARIATIONS = load_name_variations()

# ---- DynamoDB Setup ----
db = resource('dynamodb', endpoint_url='http://localhost:8001')
career_table = db.Table('career_wrestler')
season_table = db.Table('season_wrestler')
link_table = db.Table('career_link')
matches_table = db.Table('matches')
teams_table = db.Table('teams')
team_seasons_table = db.Table('team_seasons')

def load_teams_lookup():
    """Load all teams from DynamoDB to create lookup dictionaries."""
    print("Loading teams from DynamoDB...")
    try:
        # Load teams from DynamoDB using the resolver function
        teams_by_name, team_details = load_teams_from_db()
        
        # Create lookup for abbreviations
        teams_by_abbr = {}
        
        # Scan team_seasons table to get abbreviations
        response = team_seasons_table.scan(ProjectionExpression="team_id,abbreviation")
        team_seasons = response['Items']
        
        # Process pagination if needed
        while 'LastEvaluatedKey' in response:
            response = team_seasons_table.scan(
                ProjectionExpression="team_id,abbreviation",
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            team_seasons.extend(response['Items'])
        
        # Build abbreviation lookup
        for season in team_seasons:
            team_id = season.get('team_id', '')
            abbr = season.get('abbreviation', '').upper()
            
            if team_id and abbr:
                teams_by_abbr[abbr] = team_id
        
        print(f"✅ Loaded {len(team_details)} teams from database")
        print(f"✅ Total teams by name: {len(teams_by_name)}")
        print(f"✅ Total teams by abbreviation: {len(teams_by_abbr)}")
        return teams_by_name, teams_by_abbr
    except Exception as e:
        print(f"⚠️ Warning: Failed to load teams from database: {e}")
        return {}, {}

def load_existing_seasonal_wrestlers():
    """Load all season wrestlers with strongly consistent reads to ensure we have latest data."""
    result = season_table.scan(
        ConsistentRead=True  # Use strongly consistent reads
    )
    items = result['Items']
    
    # Handle pagination if there are more items
    while 'LastEvaluatedKey' in result:
        result = season_table.scan(
            ConsistentRead=True,
            ExclusiveStartKey=result['LastEvaluatedKey']
        )
        items.extend(result['Items'])
    
    return {w['season_wrestler_id']: w for w in items}

def load_existing_career_wrestlers():
    """Load all career wrestlers from DynamoDB."""
    result = career_table.scan()
    return {w['career_id']: w for w in result['Items']}

def load_existing_links():
    """Load all career links from DynamoDB."""
    result = link_table.scan()
    return {w['season_wrestler_id']: w['linked_career_id'] for w in result['Items']}

def load_existing_match_ids():
    """Load all match IDs from DynamoDB."""
    result = matches_table.scan(ProjectionExpression='match_id')
    return set(item['match_id'] for item in result['Items'])

# Add this function after the DynamoDB setup section
def get_wrestler_details(season_wrestler_id):
    """Look up a wrestler's details from the season_wrestler table."""
    try:
        response = season_table.get_item(
            Key={'season_wrestler_id': season_wrestler_id}
        )
        if 'Item' in response:
            wrestler = response['Item']
            return {
                'name': wrestler.get('name', 'Unknown'),
                'team_id': wrestler.get('team_id', 'UNK'),
                'team_name': wrestler.get('team_name', 'Unknown')
            }
    except Exception as e:
        print(f"⚠️ Error looking up wrestler {season_wrestler_id}: {str(e)}")
    return None

# Add this function after the team lookup functions
def get_team_abbreviation(team_id):
    """Get the canonical team abbreviation from the teams table."""
    # Handle special cases
    if team_id == 'UNAT':
        return 'UNAT'
    if team_id == 'UNK':
        return 'UNK'
        
    try:
        response = teams_table.get_item(Key={'team_id': team_id})
        if 'Item' in response:
            abbr = response['Item'].get('abbreviation')
            if abbr:
                return abbr
            else:
                raise Exception(f"Team {team_id} exists but has no abbreviation set")
    except Exception as e:
        print(f"❌ Error getting team abbreviation for {team_id}: {str(e)}")
    return None

# ---- Utility Functions ----
def normalize_result(result):
    if not result:
        return "UNKNOWN"
    result = result.upper().strip()

    if "FALL" in result or "PIN" in result:
        match = re.search(r"FALL\s*(\d+:\d+)?", result)
        return f"FALL-{match.group(1)}" if match and match.group(1) else "FALL"
    elif "TECH" in result or "TF" in result:
        match = re.search(r"TF\s*(\d+-\d+)?", result)
        return f"TF-{match.group(1)}" if match and match.group(1) else "TF"
    elif "MAJOR" in result or "MD" in result:
        match = re.search(r"(\d+-\d+)", result)
        return f"MD-{match.group(1)}" if match else "MD"
    elif "DEC" in result or "DECISION" in result:
        match = re.search(r"(\d+-\d+)", result)
        return f"DEC-{match.group(1)}" if match else "DEC"
    else:
        return result.replace(" ", "-")

def generate_match_id(winner_id, loser_id, date, result):
    normalized = normalize_result(result)
    return f"{winner_id}-{loser_id}-{date}-{normalized}"

# ---- Matching Utilities ----
def normalize_name(name):
    """
    Normalize a wrestler's name by:
    1. Converting to lowercase
    2. Removing extra whitespace
    """
    if not name:
        return ""
        
    # Basic normalization only - we handle variants separately
    return name.lower().strip()

def normalize_weight(weight):
    try:
        return int(float(weight))
    except:
        return None

def normalize_class_year(grade):
    if not grade:
        return ""
    norm = grade.upper().replace("-", "").replace(".", "").replace(" ", "")
    mapping = {
        "FR": "FR", "RSFR": "RSFR", "RFR": "RSFR",
        "SO": "SO", "RSSO": "RSSO", "RSO": "RSSO",
        "JR": "JR", "RSJR": "RSJR", "RJR": "RSJR",
        "SR": "SR", "RSSR": "RSSR", "RSR": "RSSR",
    }
    return mapping.get(norm, norm)

def class_year_score(current, previous):
    # Normalize both years
    current = normalize_class_year(current)
    previous = normalize_class_year(previous)

    # Simplified flexible mapping by treating RS and non-RS years the same tier
    tier_map = {
        "FR": 0, "RSFR": 0,
        "SO": 1, "RSSO": 1,
        "JR": 2, "RSJR": 2,
        "SR": 3, "RSSR": 3
    }

    t1 = tier_map.get(previous)
    t2 = tier_map.get(current)

    if t1 is None or t2 is None:
        return 0

    if t2 == t1 or t2 == t1 + 1:
        return 0.1

    return 0

def name_similarity(a, b):
    """Calculate name similarity using sequence matcher."""
    return SequenceMatcher(None, normalize_name(a), normalize_name(b)).ratio()

def is_exact_name_match(a, b):
    """Check if two names are an exact match when normalized."""
    return normalize_name(a) == normalize_name(b)

def weight_score(w1, w2):
    if w1 is None or w2 is None:
        return 0
    diff = abs(w1 - w2)
    if diff <= 10:
        return 0.2  # Same or adjacent weight class
    elif diff <= 20:
        return 0.1  # Within two classes
    return 0

def get_name_variants(name):
    """
    Get all possible variations of a name.
    Returns a set of possible variations including the original name.
    Only varies the first name, keeps the last name as is.
    """
    if not name:
        return {name}
        
    # Split into parts
    parts = name.lower().strip().split()
    if len(parts) < 2:
        return {name}  # Can't process single names
        
    first_name = parts[0]
    rest = ' '.join(parts[1:])  # Keep rest of name unchanged
    
    # Get all variants of the first name
    variants = NAME_VARIATIONS.get(first_name, {first_name})
    
    # Combine each variant with the rest of the name
    return {f"{variant} {rest}" for variant in variants}

def find_name_variant_match(current_name, team_wrestlers):
    """
    Check if any variation of the current name matches any wrestler in the team.
    Returns (matched_wrestler, is_exact_match) or (None, False) if no match found.
    """
    # Get all variants of the current name
    current_variants = get_name_variants(current_name.lower())
    
    # Debug logging
    debug_log = []
    debug_log.append(f"\nChecking name variants for {current_name}:")
    debug_log.append(f"Possible variants: {current_variants}")
    
    exact_matches = []  # Store exact matches to prioritize them
    variant_matches = []  # Store variant matches as fallback
    
    for wrestler in team_wrestlers:
        wrestler_name = wrestler.get('name', '')
        wrestler_variants = get_name_variants(wrestler_name.lower())
        
        # Debug logging
        debug_log.append(f"\nComparing against {wrestler_name}:")
        debug_log.append(f"Wrestler variants: {wrestler_variants}")
        
        # Check for any overlap between the variant sets
        matching_variants = current_variants & wrestler_variants
        if matching_variants:
            # Check if it's an exact match (ignoring case)
            if current_name.lower() == wrestler_name.lower():
                debug_log.append(f"✅ Found exact match: {wrestler_name}")
                exact_matches.append(wrestler)
            else:
                debug_log.append(f"✅ Found variant match through: {matching_variants}")
                variant_matches.append(wrestler)
    
    # Write debug info to file
    Path("logs").mkdir(exist_ok=True)
    with open("logs/name_matching.log", "a") as f:
        f.write("\n".join(debug_log))
    
    # Return exact match if available, otherwise first variant match
    if exact_matches:
        return exact_matches[0], True
    elif variant_matches:
        return variant_matches[0], False
    
    return None, False

def match_wrestler(current, pool):
    """Match a wrestler against a pool of candidates, prioritizing exact matches on same team."""
    # Keep original name
    original_name = current['name']
    current_team = current.get('team_id', '')
    current_team_name = current.get('team_name', '')
    current_season = int(current.get('season', 0))
    prior_season = current_season - 1
    
    # Initialize debug log
    debug_log = []
    debug_log.append(f"\n=== Matching Process for {original_name} ===")
    debug_log.append(f"Current Details:")
    debug_log.append(f"- Name: {original_name}")
    debug_log.append(f"- Team ID: {current_team}")
    debug_log.append(f"- Team Name: {current_team_name}")
    debug_log.append(f"- Season: {current_season}")
    debug_log.append(f"- Weight: {current.get('weight_class', 'Unknown')}")
    debug_log.append(f"- Class Year: {current.get('class_year', 'Unknown')}")
    
    # First build a filtered pool of just the prior year's wrestlers from same team
    prior_year_team = {
        wid: w for wid, w in pool.items() 
        if w.get('team_id', '') == current_team 
        and (
            # Either team_name matches (case-insensitive)
            (w.get('team_name', '').lower() == current_team_name.lower())
            # Or team_name is not present in the old entry (backward compatibility)
            or ('team_name' not in w and w.get('team_id', '') == current_team)
        )
        and int(w.get('season', 0)) == prior_season
        and 'career_id' in w
    }
    
    debug_log.append(f"\nPrior Year Team Pool ({len(prior_year_team)} wrestlers):")
    for w in prior_year_team.values():
        debug_log.append(f"- {w.get('name')} ({w.get('season')})")
    
    # Check for name variant matches in prior year team
    matched_wrestler, is_exact = find_name_variant_match(
        original_name,
        prior_year_team.values()
    )
    
    if matched_wrestler:
        debug_log.append(f"\n✅ Found {'exact' if is_exact else 'variant'} match:")
        debug_log.append(f"- Matched with: {matched_wrestler.get('name')}")
        debug_log.append(f"- Career ID: {matched_wrestler.get('career_id')}")
        
        # Write debug info to file
        Path("logs").mkdir(exist_ok=True)
        with open("logs/wrestler_matching.log", "a") as f:
            f.write("\n".join(debug_log))
        
        return matched_wrestler, 1.0  # Perfect match through variants
    
    debug_log.append("\n❌ No variant matches found, trying fuzzy matching")
    
    # If no variant match found, continue with fuzzy matching as before
    best_match = None
    best_score = 0.0
    best_debug = {}
    
    for wrestler_id, wrestler in pool.items():
        if 'career_id' not in wrestler:
            continue
            
        score = 0
        cname = wrestler.get('name', '')
        cteam = wrestler.get('team_id', '')
        cweight = normalize_weight(wrestler.get('weight_class'))
        cgrade = normalize_class_year(wrestler.get('class_year', ''))
        
        # Calculate name similarity using original names
        name_sim = SequenceMatcher(None, original_name.lower(), cname.lower()).ratio()
        
        # Skip if name similarity is too low
        if name_sim < 0.4:
            continue
            
        # Calculate all scores
        name_points = 0.5 if name_sim >= 0.9 else 0
        team_points = 0.2 if current['team_id'] == cteam else 0
        ws = weight_score(normalize_weight(current['weight_class']), cweight)
        cs = class_year_score(normalize_class_year(current['class_year']), cgrade)
        
        score = name_points + team_points + ws + cs
        
        if score > best_score:
            best_score = score
            best_match = wrestler
            best_debug = {
                'name': cname,
                'name_similarity': name_sim,
                'name_points': name_points,
                'team_points': team_points,
                'weight_score': ws,
                'class_score': cs,
                'total_score': score
            }
    
    if best_match:
        debug_log.append(f"\nBest fuzzy match found:")
        debug_log.append(f"- Name: {best_debug['name']}")
        debug_log.append(f"- Name Similarity: {best_debug['name_similarity']:.2f}")
        debug_log.append(f"- Total Score: {best_debug['total_score']:.2f}")
    else:
        debug_log.append("\n❌ No fuzzy matches found above threshold")
    
    # Write debug info to file
    Path("logs").mkdir(exist_ok=True)
    with open("logs/wrestler_matching.log", "a") as f:
        f.write("\n".join(debug_log))
    
    return best_match, round(best_score, 2)

def convert_to_dynamodb_format(item):
    """Convert numeric values to Decimal for DynamoDB compatibility."""
    if isinstance(item, Decimal):
        return item  # Already a Decimal, return as-is
    elif isinstance(item, bool):
        return item  # Keep booleans as-is
    elif isinstance(item, (int, float)):
        return Decimal(str(item))
    elif isinstance(item, dict):
        return {k: convert_to_dynamodb_format(v) for k, v in item.items()}
    elif isinstance(item, list):
        return [convert_to_dynamodb_format(i) for i in item]
    return item  # Return everything else as-is

def process_folder(folder_path, is_base_year=False):
    season = int(Path(folder_path).name)
    print(f"Processing season {season}")
    
    # Define variables to cache lookups 
    teams_by_name, teams_by_abbr = load_teams_lookup() 
    teams_by_name, team_details = load_teams_from_db()  # Make teams_by_name and team_details available
    
    # Load existing data from the database
    existing_season_wrestlers = load_existing_seasonal_wrestlers()
    existing_career_wrestlers = load_existing_career_wrestlers()
    existing_links = load_existing_links()
    existing_match_ids = load_existing_match_ids()
    
    print(f"Found {len(existing_season_wrestlers)} season wrestlers, {len(existing_links)} with career links")
    
    # Track candidates that need manual review
    seasonal_wrestlers_pending_link = []
    
    # Track new items to create
    new_season_wrestlers = []
    new_career_wrestlers = []
    new_career_links = []
    new_matches = []
    suspect_log = []

    # Process each team file
    files = list(Path(folder_path).glob("*.json"))
    for i, file_path in enumerate(files, 1):
        print(f"\nProcessing file {i}/{len(files)}: {file_path.name}")
        
        with open(file_path) as file:
            team_data = json.load(file)
            
        team_name = team_data.get('team_name') 
        if not team_name:
            print(f"⚠️ Warning: File {file_path.name} is missing team_name - skipping")
            continue
            
        # Get/create a normalized team ID
        team_id = team_data.get('team_id')
        if not team_id:
            normalized_name = normalize_team_name(team_name)
            print(f"🔍 DEBUG: Resolving team: '{team_name}' (normalized: '{normalized_name}')")
            
            # Print keys in teams_by_name for comparison
            print(f"🔍 DEBUG: Available normalized team names in database:")
            for db_team_name in sorted(teams_by_name.keys())[:10]:  # Show first 10 for brevity
                print(f"  - '{db_team_name}'")
            print(f"  ... and {len(teams_by_name) - 10} more")
            
            # Is it a direct match?
            if normalized_name in teams_by_name:
                print(f"✅ DEBUG: Found direct match for '{normalized_name}'")
            else:
                print(f"❌ DEBUG: No direct match found for '{normalized_name}'")
                
                # Try fuzzy matching
                close_matches = []
                for db_name in teams_by_name.keys():
                    if normalized_name in db_name or db_name in normalized_name:
                        close_matches.append(db_name)
                
                if close_matches:
                    print(f"🔍 DEBUG: Found possible fuzzy matches:")
                    for match in close_matches:
                        print(f"  - '{match}'")
                else:
                    print(f"❌ DEBUG: No fuzzy matches found")
            
            team_id = resolve_team(team_name, teams_by_name, team_details)
            if not team_id:
                print(f"⚠️ WARNING: Could not resolve team ID for {team_name} - Using 'UNAT' instead")
                team_id = "UNAT"  # Use Unattached as fallback

        for wrestler in team_data['roster']:
            season_wrestler_id = f"{season}-{team_id}-{wrestler['name'].replace(' ', '_')}"
            
            # Check if this is an update to an incomplete entry
            is_completing = False
            if season_wrestler_id in existing_season_wrestlers and existing_season_wrestlers[season_wrestler_id].get('status') == 'incomplete':
                is_completing = True
                print(f"✅ Completing previously incomplete entry for: {wrestler['name']}")
            elif season_wrestler_id in existing_season_wrestlers:
                # Skip if already exists and is complete
                continue

            # Prepare current wrestler data for matching
            current = {
                'name': wrestler['name'],
                'team_id': team_id,
                'team_name': team_name,  # Add team name to matching data
                'weight_class': wrestler.get('weight_class', ''),
                'class_year': wrestler.get('grade', ''),
                'season': season
            }
            
            # Only attempt matching if it's not a base year
            if not is_base_year:
                # Find the best match using ONLY the original existing_seasonals
                # This ensures we don't match against wrestlers we just processed
                match, confidence = match_wrestler(current, existing_season_wrestlers)
            else:
                match, confidence = None, 0.0

            # Determine if this is a match we should accept
            accept_match = False
            new_career = False
            add_to_suspect_list = False

            if match:
                # Apply the new rule-based evaluation
                action, confidence_score = evaluate_career_match(current, match)
                
                # Log the evaluation
                print(f"🔍 Career evaluation for {current['name']}: {action} (score: {confidence_score:.1f})")
                
                if action == 'AUTO Link Career':
                    accept_match = True
                    print(f"✅ AUTO LINKING: {current['name']} -> {match.get('name')} with score {confidence_score:.1f}")
                elif action == 'AUTO New Career':
                    accept_match = False
                    new_career = True
                    print(f"🆕 AUTO NEW CAREER: {current['name']} (score: {confidence_score:.1f})")
                else:  # 'Add to Suspect List'
                    accept_match = False
                    add_to_suspect_list = True
                    print(f"⚠️ SUSPECT LIST: {current['name']} (score: {confidence_score:.1f})")

            if match and accept_match:
                career_id = match['career_id']
                
                # Track this name variant for later update
                name_variants_update = {
                    'career_id': career_id,
                    'name': wrestler['name']
                }
                new_career_wrestlers.append(name_variants_update)
                print(f"✅ Will add '{wrestler['name']}' as a name variant to career {career_id}")
                    
                status = 'linked_to_career'
            else:
                # Generate a unique career ID
                while True:
                    new_id = f"career_{str(len(existing_career_wrestlers) + 1).zfill(5)}"
                    if new_id not in existing_career_wrestlers:
                        break
                
                career_id = new_id
                new_career = True
                status = 'roster_verified'  # New career but verified from roster
                
                # Create a new career entry for batch processing
                if not is_completing:
                    new_career_wrestlers.append({
                        'career_id': career_id,
                        'is_new': True,
                        'name_variants': [wrestler['name']]
                    })
                    
                    # Add the new career ID to existing_career_wrestlers to ensure uniqueness
                    existing_career_wrestlers[career_id] = {'career_id': career_id}

            # Create season_wrestler entry for batch processing
            new_season_wrestlers.append({
                'season_wrestler_id': season_wrestler_id,
                'career_id': career_id,
                'season': Decimal(str(season)),
                'team_id': team_id,
                'team_name': team_name,
                'name': wrestler['name'],  # Keep original name
                'weight_class': wrestler.get('weight_class', 'UNKNOWN'),
                'class_year': wrestler.get('grade', 'UNKNOWN'),
                'status': status
            })

            # Update our working copy of existing_seasonals
            existing_season_wrestlers[season_wrestler_id] = {
                'season_wrestler_id': season_wrestler_id,
                'career_id': career_id,
                'name': wrestler['name'],  # Keep original name
                'team_id': team_id,
                'team_name': team_name,
                'weight_class': wrestler.get('weight_class', ''),
                'class_year': wrestler.get('grade', ''),
                'season': Decimal(str(season)),
                'status': status
            }

            # Create career link entry for batch processing
            if not is_completing:
                # For confidence value in link record, use the new confidence_score if available
                confidence_value = confidence_score if 'confidence_score' in locals() else (confidence * 100)
                
                new_career_links.append({
                    'season_wrestler_id': season_wrestler_id,
                    'linked_career_id': career_id,
                    'confidence_score': Decimal(str(confidence_value/100)),  # Store as decimal 0-1
                    'match_type': 'new' if new_career else ('fuzzy' if normalize_name(wrestler['name']) != normalize_name(match.get('name', '') if match else '') else 'exact'),
                    'manual_override': False
                })

            # Add to suspect log if the rule-based evaluator flagged it
            if add_to_suspect_list and not is_base_year:
                try:
                    # Add to suspect log with less debug noise
                    suspect_entry = {
                        'name': wrestler['name'],  # Keep original name
                        'team': team_id,
                        'weight_class': wrestler.get('weight_class'),
                        'class_year': wrestler.get('grade'),
                        'season': season,
                        'season_wrestler_id': season_wrestler_id,
                        'reason': 'unmatched' if new_career else 'rule_evaluation',
                    }
                    
                    # Safely add the suggested match
                    if match:
                        try:
                            suggested_match = {
                                'confidence': confidence_value/100  # Keep consistent with existing format
                            }
                            
                            # Safely get career_id
                            if 'career_id' in match:
                                suggested_match['career_id'] = match['career_id']
                            else:
                                suggested_match['career_id'] = None
                                
                            suspect_entry['suggested_match'] = suggested_match
                        except Exception as e:
                            print(f"❌ Error building suggested_match: {str(e)}")
                            suspect_entry['suggested_match'] = {'error': str(e), 'confidence': confidence_value/100}
                    else:
                        suspect_entry['suggested_match'] = None
                    
                    suspect_log.append(suspect_entry)
                    
                except Exception as e:
                    print(f"❌ Error adding to suspect_log: {str(e)}")
                    continue

            # Process matches
            for match in wrestler.get('matches', []):
                # EXTENSIVE DEBUG for vs match detection
                print(f"\n🔍 DEBUG: Processing match: {json.dumps(match, indent=2)}")
                if 'summary' in match:
                    summary = match.get('summary', '')
                    print(f"🔍 DEBUG: Match summary: '{summary}'")
                    print(f"🔍 DEBUG: Contains ' vs ': {' vs ' in summary}")
                    if ' vs ' in summary:
                        print(f"🔍 DEBUG: ✅ Detected as 'vs' match! Should skip.")
                    else:
                        print(f"🔍 DEBUG: ❌ Not detected as 'vs' match.")
                else:
                    print(f"🔍 DEBUG: No summary field in this match.")
                
                # Check if this is a "vs" match rather than a competitive match with a winner
                is_vs_match = False
                if 'summary' in match:
                    summary = match.get('summary', '')
                    # More robust detection - check for various "vs" formats
                    is_vs_match = ' vs ' in summary or ' vs. ' in summary or ' VS ' in summary or ' VS. ' in summary
                
                if is_vs_match:
                    # This is a "vs" match (exhibition, dual meet, etc.) without a winner/loser
                    # Skip processing as a competitive match
                    print(f"Skipping 'vs' match: {match.get('summary')}")
                    continue
                
                # Further debug
                print(f"🔍 DEBUG: Continuing to process match - not skipped as vs match")
                print(f"🔍 DEBUG: winner_name: {match.get('winner_name')}, loser_name: {match.get('loser_name')}")
                
                # Get winner/loser info
                is_wrestler1_winner = match.get('winner_name') == wrestler['name']
                
                # Get wrestler1 (current wrestler) team info
                # First resolve the season team ID to the canonical team ID
                wrestler1_season_team_id = team_id
                wrestler1_team_id = resolve_team(team_name, teams_by_name, team_details)  # Pass required arguments
                if not wrestler1_team_id:
                    raise Exception(f"❌ CRITICAL: Could not resolve team: {team_name} (season ID: {wrestler1_season_team_id})")

                wrestler1_team_name = team_name
                wrestler1_team_abbr = get_team_abbreviation(wrestler1_team_id)
                if not wrestler1_team_abbr:
                    raise Exception(f"❌ CRITICAL: Missing team abbreviation for {wrestler1_team_id} (resolved from {wrestler1_season_team_id})")

                # Get opponent's name and team
                opponent_name = match.get('winner_name') if not is_wrestler1_winner else match.get('loser_name')
                opponent_team = match.get('winner_team') if not is_wrestler1_winner else match.get('loser_team')
                
                if opponent_name == "BYE":
                    # For BYEs, set opponent details accordingly
                    opponent_team_id = "UNAT"
                    opponent_team_name = "Unattached"
                    opponent_team_abbr = "UNAT"
                elif opponent_name == "Unknown" and opponent_team is None:
                    # Special case for forfeits with unknown opponent and null team
                    opponent_team_id = "UNK"
                    opponent_team_name = "Unknown"
                    opponent_team_abbr = "UNK"
                elif not opponent_name or opponent_name == "Unknown":
                    # For other unknown opponents, we still require a team
                    if not opponent_team:
                        raise Exception(f"❌ CRITICAL: Match has unknown opponent but should have a team:\n{json.dumps(match, indent=2)}")
                    # Resolve opponent's team
                    opponent_team_id = resolve_team(opponent_team, teams_by_name, team_details)
                    if not opponent_team_id:
                        raise Exception(f"❌ CRITICAL: Could not resolve opponent team: {opponent_team}")
                    opponent_team_name = opponent_team
                    opponent_team_abbr = get_team_abbreviation(opponent_team_id)
                    if not opponent_team_abbr:
                        raise Exception(f"❌ CRITICAL: Missing team abbreviation for opponent {opponent_team_id} (resolved from {opponent_team})")
                else:
                    # For normal matches, get opponent team info
                    if not opponent_team or opponent_team == "":
                        # Fallback to mark as Unattached if a wrestler with name has no team
                        print(f"⚠️ WARNING: Wrestler {opponent_name} has no team. Defaulting to Unattached.")
                        opponent_team_id = "UNAT"
                        opponent_team_name = "Unattached"
                        opponent_team_abbr = "UNAT"
                    else:
                        # Resolve opponent's team
                        opponent_team_id = resolve_team(opponent_team, teams_by_name, team_details)
                        if not opponent_team_id:
                            raise Exception(f"❌ CRITICAL: Could not resolve opponent team: {opponent_team}")
                        opponent_team_name = opponent_team
                        opponent_team_abbr = get_team_abbreviation(opponent_team_id)
                        if not opponent_team_abbr:
                            raise Exception(f"❌ CRITICAL: Missing team abbreviation for opponent {opponent_team_id} (resolved from {opponent_team})")

                # Create wrestler IDs using team abbreviations
                wrestler1_id = f"{season}-{wrestler1_team_abbr}-{wrestler['name'].replace(' ', '_')}"
                wrestler2_id = f"{season}-{opponent_team_abbr}-{opponent_name.replace(' ', '_')}"
                
                # Determine winner ID
                winner_id = wrestler1_id if is_wrestler1_winner else wrestler2_id

                # Get match details
                date = match.get('date', 'unknown')
                result = match.get('result', 'DEC')
                match_id = generate_match_id(winner_id, wrestler1_id if winner_id == wrestler2_id else wrestler2_id, date, result)

                if match_id in existing_match_ids:
                    continue

                # Create match entry with all required fields
                new_matches.append({
                    'match_id': match_id,
                    
                    'wrestler1_id': wrestler1_id,
                    'wrestler1_name': wrestler['name'],
                    'wrestler1_team_id': wrestler1_team_id,
                    'wrestler1_team_name': wrestler1_team_name,
                    'wrestler1_team_abbr': wrestler1_team_abbr,
                    
                    'wrestler2_id': wrestler2_id,
                    'wrestler2_name': opponent_name,
                    'wrestler2_team_id': opponent_team_id,
                    'wrestler2_team_name': opponent_team_name,
                    'wrestler2_team_abbr': opponent_team_abbr,
                    
                    'winner_id': winner_id,
                    'result': normalize_result(result),
                    'event_name': match.get('event', 'Unknown'),
                    'date': date,
                    'weight_class': match.get('weight', 'UNKNOWN')
                })
                
                # Add to tracking set
                existing_match_ids.add(match_id)

    # Phase 2: Apply all database changes in batches
    print(f"\n=== Applying database changes ===")
    print(f"New season wrestlers: {len(new_season_wrestlers)}")
    print(f"New/updated career wrestlers: {len(new_career_wrestlers)}")
    print(f"New career links: {len(new_career_links)}")
    
    # Apply updates to career_wrestler table
    career_updates_by_id = {}
    for career_update in new_career_wrestlers:
        career_id = career_update['career_id']
        if 'is_new' in career_update and career_update['is_new']:
            # Create new career entry
            item = convert_to_dynamodb_format({
                'career_id': career_id,
                'name_variants': career_update['name_variants']
            })
            try:
                career_table.put_item(Item=item)
                print(f"Created new career {career_id}")
            except Exception as e:
                print(f"❌ Error creating career {career_id}: {str(e)}")
                print(f"Item data: {item}")
                raise
        else:
            # Update existing career with new name variant
            # Group updates by career_id to avoid race conditions
            if career_id not in career_updates_by_id:
                # Get current variants
                career_entry = career_table.get_item(Key={'career_id': career_id}).get('Item', {})
                name_variants = set(career_entry.get('name_variants', []))
                career_updates_by_id[career_id] = name_variants
            
            # Add the new variant
            career_updates_by_id[career_id].add(career_update['name'])
    
    # Apply name variant updates
    for career_id, variants in career_updates_by_id.items():
        try:
            career_table.update_item(
                Key={'career_id': career_id},
                UpdateExpression="SET name_variants = :variants",
                ExpressionAttributeValues={
                    ':variants': list(variants)
                }
            )
            print(f"Updated name variants for career {career_id}")
        except Exception as e:
            print(f"❌ Error updating career {career_id}: {str(e)}")
            raise
    
    # Apply updates to season_wrestler table
    for entry in new_season_wrestlers:
        # Convert numeric values to Decimal
        item = convert_to_dynamodb_format(entry)
        try:
            season_table.put_item(Item=item)
        except Exception as e:
            print(f"❌ Error creating season wrestler: {str(e)}")
            print(f"Item data: {item}")
            raise
    
    # Apply updates to career_link table
    for link in new_career_links:
        # Convert numeric values to Decimal
        try:
            item = convert_to_dynamodb_format(link)
            print(f"Converting career link: {link}")  # Debug the input
            print(f"Converted to: {item}")  # Debug the output
            link_table.put_item(Item=item)
        except Exception as e:
            print(f"❌ Error creating career link: {str(e)}")
            print(f"Original link data: {link}")
            print(f"Attempted conversion: {item if 'item' in locals() else 'conversion failed'}")
            raise
    
    # Process matches in batches
    print(f"New matches: {len(new_matches)}")
    
    # Add the matches in batches to avoid API limits
    batch_size = 25
    for i in range(0, len(new_matches), batch_size):
        batch = new_matches[i:i+batch_size]
        for match_data in batch:
            # Convert numeric values to Decimal
            item = convert_to_dynamodb_format(match_data)
            try:
                matches_table.put_item(Item=item)
            except Exception as e:
                print(f"❌ Error creating match: {str(e)}")
                print(f"Item data: {item}")
                raise
        print(f"Added matches batch {i//batch_size + 1}/{(len(new_matches)-1)//batch_size + 1}")
    
    print("\n✅ Database updates complete!")

    if suspect_log:
        output_path = Path("logs") / f"suspect_links_{season}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as out:
            json.dump(suspect_log, out, indent=2)
        print(f"📝 Suspect links saved to {output_path}")
    else:
        print("✅ No suspect links detected.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--folder', help='Folder containing season JSON files')
    parser.add_argument('--base_year', action='store_true', help='If this is a base year, skip career matching')
    parser.add_argument('--auto', type=int, help='Automatically accept matches above this confidence threshold')
    parser.add_argument('--test', action='store_true', help='Run tests for the career evaluator')
    args = parser.parse_args()
    
    # Run tests if requested
    if args.test:
        test_career_match_evaluator()
        return
    
    # For normal operation, folder is required
    if not args.folder:
        parser.error("the --folder argument is required for normal operation")

    # Load teams from database
    teams_by_name, team_details = load_teams_from_db()

    # Debug check for Cornell College
    print("\n🔍 DEBUG: TEAM RESOLUTION CHECK")
    test_names = ["Cornell College", "cornell college", "Cornell-College"]
    for test_name in test_names:
        norm = normalize_team_name(test_name)
        resolved = resolve_team(test_name, teams_by_name, team_details, interactive=False)
        print(f"Test name: '{test_name}' → normalized: '{norm}' → resolved: '{resolved}'")

    if "cornell college" in teams_by_name:
        print(f"✅ 'cornell college' found in teams_by_name → {teams_by_name['cornell college']}")
    else:
        print(f"❌ 'cornell college' NOT found in teams_by_name")
        # Print first few entries for reference
        print("First 5 entries in teams_by_name:")
        for i, (name, id) in enumerate(list(teams_by_name.items())[:5]):
            print(f"  {i+1}. '{name}' → '{id}'")

    # First scan for any unidentified teams
    print("\n🔍 Scanning for unidentified teams...")
    team_names_with_counts, empty_team_wrestlers = count_team_matches(args.folder)
    
    # Check for unidentified teams
    unidentified_teams = []
    for team_name, count in team_names_with_counts.items():
        if normalize_team_name(team_name) not in teams_by_name:
            unidentified_teams.append((team_name, count))
    
    # Auto-fix unidentified teams if --auto is enabled
    if args.auto is not None and unidentified_teams:
        print(f"\n🔧 Auto-fixing unidentified teams with {args.auto} or fewer matches...")
        auto_fixed_teams = []
        remaining_teams = []
        
        for team_name, count in unidentified_teams:
            if count <= args.auto:
                print(f"  Auto-fixing: {team_name} (appears {count} times) → Unattached")
                update_json_files_with_team(args.folder, team_name, "UNAT")
                auto_fixed_teams.append(team_name)
            else:
                remaining_teams.append((team_name, count))
        
        if auto_fixed_teams:
            print(f"✅ Auto-fixed {len(auto_fixed_teams)} teams to Unattached")
        
        # Update the list of unidentified teams to only include those that weren't auto-fixed
        unidentified_teams = remaining_teams
    
    # Use interactive resolution instead of exiting
    issues_found = False
    
    # First check for unidentified teams
    if unidentified_teams:
        issues_found = True
        print("\n⚠️ Found unidentified teams:")
        for team_name, count in unidentified_teams:
            print(f"- {team_name} (appears {count} times)")
    
    # Then check for empty team wrestlers
    if empty_team_wrestlers:
        issues_found = True
        print("\n⚠️ Found wrestlers with empty teams:")
        for wrestler in empty_team_wrestlers:
            count = team_names_with_counts[wrestler]
            print(f"- {wrestler} (appears {count} times)")
    
    # Proceed with interactive resolution if issues were found
    if issues_found:
        # Ask user if they want to resolve teams interactively
        choice = input("\nWould you like to resolve these issues interactively? (y/n): ").lower().strip()
        if choice == 'y':
            # First process unidentified teams
            for team_name, count in unidentified_teams:
                print(f"\nResolving team: {team_name} (appears {count} times)")
                # Interactively resolve the team using the resolver
                team_id = resolve_team(team_name, teams_by_name, team_details, match_count=count)
                
                # If a resolution was chosen, update the source files
                if team_id:
                    update_json_files_with_team(args.folder, team_name, team_id)
                    # Update teams_by_name to avoid resolving this team again
                    teams_by_name[normalize_team_name(team_name)] = team_id
            
            # Then process empty team wrestlers
            for wrestler in empty_team_wrestlers:
                print(f"\nResolving wrestler with empty team: {wrestler}")
                
                # Extract the wrestler name without the "(No Team)" suffix
                original_name = wrestler.replace(" (No Team)", "")
                
                print("Options:")
                print("1. Mark as Unattached")
                print("2. Specify a team")
                print("3. Skip this wrestler")
                
                choice = input("Choose an option (1-3): ").lower().strip()
                
                target_team = None
                if choice == '1':
                    target_team = "Unattached"
                    target_id = "UNAT"
                elif choice == '2':
                    search_term = input("Enter search term for team: ").strip()
                    # Let user search for a team
                    search_results = []
                    for name, team_id in teams_by_name.items():
                        if search_term.lower() in name.lower():
                            team_info = get_team_info(team_id)
                            if team_info:
                                search_results.append((name, team_id))
                    
                    if not search_results:
                        print("No teams found. Using Unattached.")
                        target_team = "Unattached"
                        target_id = "UNAT"
                    else:
                        print("\nFound teams:")
                        for i, (name, _) in enumerate(search_results, 1):
                            print(f"{i}. {name}")
                        
                        team_choice = input(f"Select team (1-{len(search_results)}) or 'u' for Unattached: ").strip()
                        if team_choice.lower() == 'u':
                            target_team = "Unattached"
                            target_id = "UNAT"
                        else:
                            try:
                                idx = int(team_choice) - 1
                                if 0 <= idx < len(search_results):
                                    target_team = search_results[idx][0]
                                    target_id = search_results[idx][1]
                                else:
                                    print("Invalid choice. Using Unattached.")
                                    target_team = "Unattached"
                                    target_id = "UNAT"
                            except ValueError:
                                print("Invalid input. Using Unattached.")
                                target_team = "Unattached"
                                target_id = "UNAT"
                else:
                    print(f"Skipping {wrestler}")
                    continue
                
                # Update empty team wrestlers in JSON files
                if target_team:
                    update_empty_team_wrestler(args.folder, original_name, target_team)
            
            # Re-check for any remaining unidentified teams
            teams_by_name, team_details = load_teams_from_db()  # Reload to get updated team data
            unresolved = []
            for team_name, count in team_names_with_counts.items():
                if normalize_team_name(team_name) not in teams_by_name:
                    unresolved.append((team_name, count))
            
            if unresolved:
                print("\n⚠️ There are still unresolved teams:")
                for team_name, count in unresolved:
                    print(f"- {team_name} (appears {count} times)")
                print("\nPlease add these teams to the database before proceeding.")
                sys.exit(1)
            else:
                print("\n✅ All issues have been successfully resolved!")
        else:
            print("\nPlease add these teams to the database before proceeding.")
            sys.exit(1)
    else:
        print("\n✅ All teams already exist in the database!")
    
    # Now proceed with processing the folder
    process_folder(args.folder, args.base_year)

# Function to count matches for each team
def count_team_matches(folder_path):
    """Count all unique team names in the season's JSON files."""
    team_counts = defaultdict(int)
    empty_team_wrestlers = []  # Track wrestlers with empty teams
    files = list(Path(folder_path).glob("*.json"))
    wrestlers_without_teams = {}  # Track wrestlers without teams by name
    
    for file in files:
        with open(file) as f:
            try:
                team_data = json.load(f)
            except json.JSONDecodeError as e:
                print(f"Error parsing JSON in {file}: {e}")
                continue
            
            # Count the team from the file itself
            team_name = team_data.get('team_name')
            if team_name:
                team_counts[team_name] += 1
            
            # Count teams from matches
            for wrestler in team_data.get('roster', []):
                for match in wrestler.get('matches', []):
                    # Skip vs matches as they don't have winners/losers
                    if 'summary' in match and (' vs ' in match['summary'] or ' vs. ' in match['summary']):
                        continue
                        
                    # Check if this is current wrestler's match
                    is_current_wrestler = match.get('winner_name') == wrestler['name']
                    
                    # Get opponent name and team
                    opp_name = match.get('loser_name') if is_current_wrestler else match.get('winner_name')
                    opp_team = match.get('loser_team') if is_current_wrestler else match.get('winner_team')
                    
                    # Count opponent teams
                    if opp_team:
                        team_counts[opp_team] += 1
                    elif opp_name and opp_name != "Unknown" and (opp_team == "" or opp_team is None):
                        # Track wrestlers with empty teams but known names
                        wrestler_key = f"{opp_name} (No Team)"
                        team_counts[wrestler_key] += 1
                        
                        # Store the file where we found this wrestler
                        if wrestler_key not in wrestlers_without_teams:
                            wrestlers_without_teams[wrestler_key] = {
                                "count": 0,
                                "files": [],
                                "example_match": None
                            }
                        
                        wrestlers_without_teams[wrestler_key]["count"] += 1
                        if file.name not in wrestlers_without_teams[wrestler_key]["files"]:
                            wrestlers_without_teams[wrestler_key]["files"].append(file.name)
                        
                        # Store an example match for debugging
                        if wrestlers_without_teams[wrestler_key]["example_match"] is None:
                            wrestlers_without_teams[wrestler_key]["example_match"] = match
                            
                        if wrestler_key not in empty_team_wrestlers:
                            empty_team_wrestlers.append(wrestler_key)
                    
                    # Always count Unattached if a wrestler has no team
                    if not match.get('winner_team') or match.get('loser_team'):
                        team_counts['Unattached'] += 1
    
    # Print detailed debug info about wrestlers without teams
    if wrestlers_without_teams:
        print("\n📊 DEBUG: Detailed info for wrestlers without teams:")
        for wrestler, data in wrestlers_without_teams.items():
            print(f"\n- {wrestler} (appears {data['count']} times)")
            print(f"  Found in files: {', '.join(data['files'])}")
            if data["example_match"]:
                print(f"  Example match: {json.dumps(data['example_match'], indent=2)}")
    
    return team_counts, empty_team_wrestlers

# Helper function to get all team names from a season folder
def get_all_team_names(folder_path):
    """Extract all team names from roster and match data in a folder."""
    return set(count_team_matches(folder_path).keys())

# Normalize team name for comparison
def normalize_team_name(name):
    """Normalize team name for comparison."""
    if not name:
        return ""
    name = re.sub(r'[^\w\s]', '', name)  # Remove punctuation
    name = re.sub(r'\s+', ' ', name)      # Normalize whitespace
    return name.strip().lower()

def update_json_files_with_team(folder_path, original_team, new_team_id):
    """
    Update all JSON files in the folder to replace original team name with the resolved team.
    
    Args:
        folder_path: Path to the season folder
        original_team: Original team name
        new_team_id: New team ID (e.g., 'UNAT' for Unattached)
    """
    # Get the proper team name from the database
    if new_team_id == 'UNAT':
        display_name = "Unattached"
    else:
        # Look up the team name in the database
        team_info = get_team_info(new_team_id)
        if team_info and 'name' in team_info:
            display_name = team_info['name']
        else:
            # Fallback to the ID if we can't find the name
            display_name = new_team_id
    
    print(f"\nUpdating source files: '{original_team}' -> '{display_name}'")
    files = list(Path(folder_path).glob("*.json"))
    files_updated = 0
    matches_updated = 0
    
    for file_path in files:
        file_updated = False
        with open(file_path, 'r') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                print(f"Error: Could not parse JSON file {file_path}")
                continue
        
        # Check if this team is the main team in the file
        if data.get('team_name') == original_team:
            data['team_name'] = display_name
            # If there's an abbreviation, update it too
            if 'abbreviation' in data:
                data['abbreviation'] = new_team_id
            file_updated = True
        
        # Check for this team in matches
        for wrestler in data.get('roster', []):
            for match in wrestler.get('matches', []):
                # Update winner_team and loser_team
                if match.get('winner_team') == original_team:
                    match['winner_team'] = display_name
                    file_updated = True
                    matches_updated += 1
                if match.get('loser_team') == original_team:
                    match['loser_team'] = display_name
                    file_updated = True
                    matches_updated += 1
                
                # Update summary field if it exists
                if 'summary' in match:
                    summary = match['summary']
                    # Handle both formats that might appear in summary:
                    # "Winner Name (Original Team) over Loser Name (Other Team)"
                    # "Winner Name (Original Team) won by fall over Loser Name (Other Team)"
                    if f"({original_team})" in summary:
                        new_summary = summary.replace(f"({original_team})", f"({display_name})")
                        if new_summary != summary:
                            match['summary'] = new_summary
                            file_updated = True
        
        # Write changes back to file if updated
        if file_updated:
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
            files_updated += 1
            
    print(f"✅ Updated {matches_updated} matches in {files_updated} files")
    return files_updated > 0

def update_empty_team_wrestler(folder_path, wrestler_name, target_team):
    """
    Update all JSON files in the folder to add a team name for wrestlers with empty teams.
    
    Args:
        folder_path: Path to the season folder
        wrestler_name: The name of the wrestler without a team
        target_team: The team name to assign to the wrestler
    """
    print(f"\nUpdating source files: wrestler '{wrestler_name}' -> team '{target_team}'")
    
    # First, find all files containing the wrestler name
    # This is a more direct approach than trying to load all files
    wrestler_files = []
    
    # Use grep-like functionality to quickly find relevant files
    for file_path in Path(folder_path).glob("*.json"):
        try:
            with open(file_path, 'r') as f:
                content = f.read()
                if f'"{wrestler_name}"' in content:
                    wrestler_files.append(file_path)
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
    
    print(f"Found {len(wrestler_files)} files containing '{wrestler_name}'")
    
    if not wrestler_files:
        print(f"⚠️ Could not find any files with wrestler '{wrestler_name}'")
        return False
    
    # Now process each file that contains the wrestler
    files_updated = 0
    matches_updated = 0
    
    for file_path in wrestler_files:
        print(f"Processing file: {file_path.name}")
        
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"❌ Error parsing JSON in {file_path}: {e}")
            continue
        
        file_updated = False
        
        # Process each wrestler's matches
        for wrestler in data.get('roster', []):
            for match in wrestler.get('matches', []):
                # Check if this match involves our target wrestler
                if match.get('winner_name') == wrestler_name:
                    print(f"  Found as winner in match: {match.get('summary', '')}")
                    
                    # Check if team is empty or null
                    if not match.get('winner_team') or match.get('winner_team') == "":
                        print(f"  ✅ Updating winner_team from '{match.get('winner_team')}' to '{target_team}'")
                        match['winner_team'] = target_team
                        file_updated = True
                        matches_updated += 1
                
                if match.get('loser_name') == wrestler_name:
                    print(f"  Found as loser in match: {match.get('summary', '')}")
                    
                    # Check if team is empty or null
                    if not match.get('loser_team') or match.get('loser_team') == "":
                        print(f"  ✅ Updating loser_team from '{match.get('loser_team')}' to '{target_team}'")
                        match['loser_team'] = target_team
                        file_updated = True
                        matches_updated += 1
                
                # Update summary if needed
                if 'summary' in match and wrestler_name in match['summary']:
                    # Get original summary
                    original_summary = match['summary']
                    
                    # Try different patterns for empty team
                    patterns = [
                        f"{wrestler_name} ()",
                        f"{wrestler_name}()"
                    ]
                    
                    for pattern in patterns:
                        if pattern in original_summary:
                            new_summary = original_summary.replace(pattern, f"{wrestler_name} ({target_team})")
                            if new_summary != original_summary:
                                print(f"  ✅ Updating summary from '{original_summary}' to '{new_summary}'")
                                match['summary'] = new_summary
                                file_updated = True
                
        # Write changes back to the file if updated
        if file_updated:
            files_updated += 1
            print(f"  Writing updated data to {file_path.name}")
            
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
    
    print(f"✅ Updated {matches_updated} matches in {files_updated} files")
    return matches_updated > 0



from difflib import SequenceMatcher

def normalize(name):
    return name.lower().strip()

def is_fuzzy_match(a, b, threshold=0.9):
    score = SequenceMatcher(None, a.lower(), b.lower()).ratio()
    print(f"FUZZY DEBUG: comparing '{a}' to '{b}' — similarity: {score:.3f}")
    return score >= threshold

def evaluate_career_match(current, match):
    name_match = is_fuzzy_match(current['name'], match['name'])
    exact_name = normalize(current['name']) == normalize(match['name'])
    team_match = current['team_id'] == match['team_id']

    try:
        current_weight = int(current.get('weight_class', 0))
        match_weight = int(match.get('weight_class', 0))
        weight_diff = abs(current_weight - match_weight)
        if weight_diff <= 10:
            weight_match = 2  # 20%
        elif weight_diff <= 20:
            weight_match = 1  # 10%
        else:
            weight_match = 0
    except:
        weight_match = 0

    current_class = current.get('class_year', '')
    match_class = match.get('class_year', '')
    freshman = current_class in {'FR', 'RSFR'}
    grade_match = (
        (current_class == match_class) or
        (current_class == 'SO' and match_class in {'FR', 'RSFR'}) or
        (current_class == 'JR' and match_class == 'SO') or
        (current_class == 'SR' and match_class == 'JR')
    )

    if not name_match:
        return 'Add to Suspect List', 50 * weight_match / 2

    if exact_name and team_match and weight_match == 2 and grade_match:
        return 'AUTO Link Career', 100

    if freshman and not team_match:
        return 'AUTO New Career', 80

    if freshman:
        if exact_name and team_match and weight_match == 2 and grade_match:
            return 'AUTO Link Career', 100
        return 'AUTO New Career', 50 + weight_match * 10 + (20 if team_match else 0)

    if name_match and team_match and weight_match > 0 and grade_match:
        return 'AUTO Link Career', 90
    elif name_match and (team_match or weight_match > 0 or grade_match):
        return 'Add to Suspect List', 70

    return 'Add to Suspect List', 60

    name_match = normalize(current['name']) in normalize(match['name']) or normalize(match['name']) in normalize(current['name'])
    exact_name = normalize(current['name']) == normalize(match['name'])
    team_match = current['team_id'] == match['team_id']

    try:
        current_weight = int(current.get('weight_class', 0))
        match_weight = int(match.get('weight_class', 0))
        weight_diff = abs(current_weight - match_weight)
        if weight_diff <= 10:
            weight_match = 2  # 20%
        elif weight_diff <= 20:
            weight_match = 1  # 10%
        else:
            weight_match = 0
    except:
        weight_match = 0

    current_class = current.get('class_year', '')
    match_class = match.get('class_year', '')
    freshman = current_class in {'FR', 'RSFR'}
    grade_match = (
        (current_class == match_class) or
        (current_class == 'SO' and match_class in {'FR', 'RSFR'}) or
        (current_class == 'JR' and match_class == 'SO') or
        (current_class == 'SR' and match_class == 'JR')
    )

    # Apply the decision table logic directly

    # No name match = Add to Suspect List
    if not name_match:
        return 'Add to Suspect List', 50 * weight_match / 2  # name is 0, team is unknown

    # Row 11, 21, 24, 28: Perfect match
    if exact_name and team_match and weight_match == 2 and grade_match:
        return 'AUTO Link Career', 100

    # Row 23: FR with no team match, even with perfect name/weight
    if freshman and not team_match:
        return 'AUTO New Career', 80

    # Other FR logic from rows: 12, 13, 14, 25 → all treated as AUTO New Career
    if freshman:
        if exact_name and team_match and weight_match == 2 and grade_match:
            return 'AUTO Link Career', 100
        return 'AUTO New Career', 50 + weight_match * 10 + (20 if team_match else 0)

    # Non-freshman with decent but partial matches → AUTO Link Career or Suspect
    if name_match and team_match and weight_match > 0 and grade_match:
        return 'AUTO Link Career', 90
    elif name_match and (team_match or weight_match > 0 or grade_match):
        return 'Add to Suspect List', 70

    return 'Add to Suspect List', 60



def test_career_match_evaluator():
    """
    Full test suite covering 28 decision rows from the career match rules.
    """
    from difflib import SequenceMatcher

    def create_test_wrestlers(row_id, is_freshman, name_match, exact_name, team_match,
                             weight_match, grade_match):
        current_name = "John Smith"
        match_name = (
            "John Smith" if exact_name else
            "Johnny Smith" if name_match else
            "Mike Jones"
        )
        current_team = "TEAM1"
        match_team = current_team if team_match else "TEAM2"
        current_weight = 165
        if weight_match == 2:
            match_weight = current_weight
        elif weight_match == 1:
            match_weight = current_weight - 15
        else:
            match_weight = current_weight - 30

        if is_freshman:
            current_class = "FR"
            if grade_match:
                match_class = "FR"
            else:
                match_class = "SR"
        else:
            current_class = "SO"
            if grade_match:
                match_class = "FR"  # progression match
            else:
                match_class = "SO"
    test_cases = [
        (1,0,0,0,0,0,0,'Add to Suspect List'),
        (2,0,1,0,0,0,0,'Add to Suspect List'),
        (3,0,1,0,0,0,1,'Add to Suspect List'),
        (4,0,1,0,1,0,0,'Add to Suspect List'),
        (5,0,1,0,1,0,1,'Add to Suspect List'),
        (6,0,1,0,1,1,0,'AUTO Link Career'),
        (7,0,1,0,1,1,0,'Add to Suspect List'),
        (8,0,1,1,0,0,0,'Add to Suspect List'),
        (9,0,1,1,1,0,1,'AUTO Link Career'),
        (10,0,1,1,1,1,0,'AUTO Link Career'),
        (11,0,1,1,1,1,1,'AUTO Link Career'),
        (12,1,0,0,0,0,0,'AUTO New Career'),
        (13,1,1,0,0,0,0,'AUTO New Career'),
        (14,1,1,0,0,0,1,'Add to Suspect List'),
        (15,1,1,0,0,1,0,'AUTO New Career'),
        (16,1,1,0,0,1,1,'Add to Suspect List'),
        (17,1,1,0,1,0,0,'Add to Suspect List'),
        (18,1,1,0,1,0,1,'AUTO Link Career'),
        (19,1,1,0,1,1,0,'Add to Suspect List'),
        (20,1,1,0,1,1,1,'AUTO Link Career'),
        (21,1,1,1,0,0,0,'AUTO New Career'),
        (22,1,1,1,0,0,1,'Add to Suspect List'),
        (23,1,1,1,0,1,0,'AUTO New Career'),
        (24,1,1,1,0,1,1,'Add to Suspect List'),
        (25,1,1,1,1,0,0,'Add to Suspect List'),
        (26,1,1,1,1,0,1,'AUTO Link Career'),
        (27,1,1,1,1,1,0,'Add to Suspect List'),
        (28,1,1,1,1,1,1,'AUTO Link Career')
    ]

    passed = 0
    print("=== TESTING CAREER MATCH EVALUATOR ===")
    for (row, fr, nm, ex, tm, wm, gm, expected) in test_cases:
        current, match = create_test_wrestlers(row, fr, nm, ex, tm, wm, gm)
        action, score = evaluate_career_match(current, match)
        if action == expected:
            print(f"✅ Test {row}: PASSED: {action} (score: {score})")
            passed += 1
        else:
            print(f"❌ Test {row}: FAILED: Expected {expected}, got {action}")
            print(f"  Wrestler: {current}")
            print(f"  Match: {match}")
            print(f"  Score: {score}")
    print(f"Test results: {passed}/{len(test_cases)} passed.")
    test_cases = [
        # Row, Freshman, Name, Exact, Team, Weight, Grade, Expected Action
        (1, 0, 0, 0, 0, 0, 0, 'Add to Suspect List'),
        (2, 0, 0, 0, 1, 1, 1, 'Add to Suspect List'),
        (3, 0, 1, 0, 0, 0, 0, 'Add to Suspect List'),
        (4, 0, 1, 0, 1, 0, 0, 'Add to Suspect List'),
        (5, 0, 1, 0, 1, 0, 1, 'Add to Suspect List'),
        (6, 0, 1, 0, 1, 1, 0, 'AUTO Link Career'),
        (7, 0, 1, 0, 1, 1, 1, 'AUTO Link Career'),
        (8, 0, 1, 1, 0, 1, 1, 'Add to Suspect List'),
        (9, 0, 1, 1, 1, 0, 1, 'AUTO Link Career'),
        (10, 0, 1, 1, 1, 1, 0, 'AUTO Link Career'),
        (11, 0, 1, 1, 1, 1, 1, 'AUTO Link Career'),
        (12, 1, 0, 0, 0, 0, 0, 'AUTO New Career'),
        (13, 1, 0, 0, 0, 0, 1, 'AUTO New Career'),
        (14, 1, 0, 0, 1, 1, 0, 'AUTO New Career'),
        (15, 1, 1, 0, 0, 0, 0, 'Add to Suspect List'),
        (16, 1, 1, 0, 1, 0, 0, 'Add to Suspect List'),
        (17, 1, 1, 1, 0, 1, 1, 'Add to Suspect List'),
        (18, 1, 1, 1, 1, 0, 0, 'Add to Suspect List'),
        (19, 1, 1, 1, 1, 0, 1, 'Add to Suspect List'),
        (20, 1, 1, 1, 1, 1, 0, 'Add to Suspect List'),
        (21, 1, 1, 1, 1, 1, 1, 'AUTO Link Career'),
        (22, 0, 1, 1, 1, 1, 0, 'AUTO Link Career'),
        (23, 1, 1, 1, 0, 1, 0, 'AUTO New Career'),
        (24, 0, 1, 1, 1, 1, 1, 'AUTO Link Career'),
        (25, 1, 1, 1, 1, 1, 0, 'AUTO New Career'),
        (26, 1, 1, 1, 1, 0, 1, 'Add to Suspect List'),
        (27, 0, 1, 0, 1, 1, 1, 'AUTO Link Career'),
        (28, 1, 1, 1, 1, 1, 1, 'AUTO Link Career'),
    ]

    passed = 0
    print("=== TESTING ALL 28 CAREER MATCH DECISIONS ===")
    for (row, fr, nm, ex, tm, wm, gm, expected) in test_cases:
        current, match = create_test_wrestlers(fr, nm, ex, tm, wm, gm)
        action, score = evaluate_career_match(current, match)
        if action == expected:
            print(f"✅ Row {row}: PASSED ({action}, score: {score})")
            passed += 1
        else:
            print(f"❌ Row {row}: FAILED. Expected {expected}, got {action}")
            print(f"  Score: {score}, Current: {current}, Match: {match}")
    print(f"Test results: {passed}/{len(test_cases)} passed.")

if __name__ == '__main__':
    main()