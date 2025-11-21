#!/usr/bin/env python3
"""
Team Resolver Module

Provides functions to resolve team names to consistent team IDs during initial data processing.
This helps prevent team naming inconsistencies from being introduced into the database.
"""

import json
import os
import re
from difflib import SequenceMatcher
from typing import List, Dict
from pathlib import Path
from datetime import datetime

# File paths
EXTERNAL_TEAMS_PATH = 'data/external_teams.json'
TEAM_MAPPINGS_PATH = 'data/team_mappings.json'
TEAM_CHANGES_LOG_PATH = 'data/team_changes.log'

def load_external_teams():
    """Load external teams from JSON file."""
    try:
        if os.path.exists(EXTERNAL_TEAMS_PATH):
            with open(EXTERNAL_TEAMS_PATH, 'r') as f:
                return json.load(f)
        else:
            # Create empty external teams file if it doesn't exist
            external_teams = {}
            with open(EXTERNAL_TEAMS_PATH, 'w') as f:
                json.dump(external_teams, f, indent=2)
            return external_teams
    except Exception as e:
        print(f"❌ Error loading external teams: {e}")
        return {}

def save_external_teams(external_teams):
    """Save external teams to JSON file."""
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(EXTERNAL_TEAMS_PATH), exist_ok=True)
        
        with open(EXTERNAL_TEAMS_PATH, 'w') as f:
            json.dump(external_teams, f, indent=2)
        return True
    except Exception as e:
        print(f"❌ Error saving external teams: {e}")
        return False

def load_team_mappings():
    """Load team mappings from JSON file."""
    try:
        if os.path.exists(TEAM_MAPPINGS_PATH):
            with open(TEAM_MAPPINGS_PATH, 'r') as f:
                return json.load(f)
        else:
            # Create empty mappings file if it doesn't exist
            mappings = {}
            with open(TEAM_MAPPINGS_PATH, 'w') as f:
                json.dump(mappings, f, indent=2)
            return mappings
    except Exception as e:
        print(f"❌ Error loading team mappings: {e}")
        return {}

def save_team_mappings(mappings):
    """Save team mappings to JSON file."""
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(TEAM_MAPPINGS_PATH), exist_ok=True)
        
        with open(TEAM_MAPPINGS_PATH, 'w') as f:
            json.dump(mappings, f, indent=2)
        return True
    except Exception as e:
        print(f"❌ Error saving team mappings: {e}")
        return False

def calculate_similarity(str1, str2):
    """Calculate string similarity between two team names."""
    # Convert to lowercase for comparison
    s1 = str1.lower()
    s2 = str2.lower()
    
    # Direct match
    if s1 == s2:
        return 1.0
        
    # Check if one is substring of the other
    if s1 in s2 or s2 in s1:
        return 0.8
    
    # Use sequence matcher for fuzzy matching
    return SequenceMatcher(None, s1, s2).ratio()

def get_similar_teams(team_name, teams_by_name, external_teams, threshold=0.6):
    """Find similar teams in both NCAA and external teams."""
    similar_teams = []
    
    # Search NCAA teams
    for name, team_id in teams_by_name.items():
        similarity = calculate_similarity(team_name, name)
        if similarity >= threshold:
            similar_teams.append({
                'name': name,
                'id': team_id,
                'source': 'NCAA',
                'similarity': similarity
            })
    
    # Search external teams
    for team_id, team_info in external_teams.items():
        name = team_info.get('name', team_id)
        similarity = calculate_similarity(team_name, name)
        if similarity >= threshold:
            similar_teams.append({
                'name': name,
                'id': team_id,
                'source': 'External',
                'similarity': similarity
            })
    
    # Sort by similarity (highest first)
    similar_teams.sort(key=lambda x: x['similarity'], reverse=True)
    return similar_teams

def find_matches_with_team(team_name: str, season_folder: str = None) -> List[Dict]:
    """Find all matches containing a specific team name."""
    matches = []
    
    # If season_folder is provided, only search in that folder
    folders_to_search = [Path(season_folder)] if season_folder else [f for f in Path('data').glob('*') if f.is_dir() and f.name.isdigit()]
    
    # Search through specified folders
    for season_folder in folders_to_search:
        if not season_folder.is_dir():
            continue
            
        # Search through all team JSON files in this season
        for team_file in season_folder.glob('*.json'):
            with open(team_file) as f:
                team_data = json.load(f)
                
            for wrestler in team_data.get('roster', []):
                for match in wrestler.get('matches', []):
                    # Get team names with original case, defaulting to empty string if None
                    winner_team = match.get('winner_team', '') or ''
                    loser_team = match.get('loser_team', '') or ''
                    
                    # Skip if both team names are empty
                    if not winner_team and not loser_team:
                        continue
                    
                    # Check if either team matches (case-insensitive)
                    if (team_name.lower() == winner_team.lower() or 
                        team_name.lower() == loser_team.lower()):
                        matches.append({
                            'wrestler': wrestler['name'],
                            'match': match,
                            'file': str(team_file)
                        })
    
    return matches

def log_team_change(old_name: str, new_name: str, matches_updated: int, files_updated: List[str]) -> None:
    """Log a team name change to the changes log file."""
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(TEAM_CHANGES_LOG_PATH), exist_ok=True)
        
        # Format the log entry
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = {
            'timestamp': timestamp,
            'old_name': old_name,
            'new_name': new_name,
            'matches_updated': matches_updated,
            'files_updated': files_updated
        }
        
        # Append to log file
        with open(TEAM_CHANGES_LOG_PATH, 'a') as f:
            json.dump(log_entry, f)
            f.write('\n')  # Add newline for readability
            
        print(f"✅ Logged change from '{old_name}' to '{new_name}'")
    except Exception as e:
        print(f"❌ Error logging team change: {e}")

def update_matches_with_team(old_team: str, new_team: str, matches: List[Dict]) -> None:
    """Update all matches to use the new team name."""
    updated_files = set()
    
    print(f"DEBUG: Updating matches - Old team: '{old_team}', New team: '{new_team}'")
    
    # Group matches by file to minimize file operations
    matches_by_file = {}
    for match_info in matches:
        file_path = match_info['file']
        if file_path not in matches_by_file:
            matches_by_file[file_path] = []
        matches_by_file[file_path].append(match_info)
    
    # Process each file
    for file_path, file_matches in matches_by_file.items():
        try:
            with open(file_path) as f:
                team_data = json.load(f)
            
            file_modified = False
            
            # Process each match in this file
            for match_info in file_matches:
                wrestler = match_info['wrestler']
                match = match_info['match']
                
                # Find the wrestler and match in the loaded data
                for w in team_data.get('roster', []):
                    if w['name'] == wrestler:
                        for m in w.get('matches', []):
                            # Check if this is the exact match we want to update
                            if (m.get('date') == match.get('date') and 
                                m.get('event') == match.get('event') and 
                                m.get('weight') == match.get('weight') and 
                                m.get('winner_name') == match.get('winner_name') and 
                                m.get('loser_name') == match.get('loser_name')):
                                
                                print(f"DEBUG: Found match to update - Original winner_team: '{m.get('winner_team')}', Original loser_team: '{m.get('loser_team')}'")
                                
                                # Update team names using exact name from database
                                if m.get('winner_team', '').lower() == old_team.lower():
                                    m['winner_team'] = new_team
                                    print(f"DEBUG: Updated winner_team to: '{new_team}'")
                                    file_modified = True
                                if m.get('loser_team', '').lower() == old_team.lower():
                                    m['loser_team'] = new_team
                                    print(f"DEBUG: Updated loser_team to: '{new_team}'")
                                    file_modified = True
                                
                                # Update the summary field
                                if 'summary' in m:
                                    summary = m['summary']
                                    # Replace team name in parentheses, preserving exact case
                                    summary = re.sub(
                                        rf'\({re.escape(old_team)}\)',
                                        f'({new_team})',
                                        summary,
                                        flags=re.IGNORECASE  # Make the search case-insensitive but preserve replacement case
                                    )
                                    m['summary'] = summary
                                    print(f"DEBUG: Updated summary to: '{summary}'")
            
            # Save the updated data if we modified anything
            if file_modified:
                with open(file_path, 'w') as f:
                    json.dump(team_data, f, indent=2)
                updated_files.add(file_path)
        
        except Exception as e:
            print(f"Error processing file {file_path}: {e}")
    
    # Log the changes
    log_team_change(old_team, new_team, len(matches), list(updated_files))

def search_teams(query: str, teams_by_name: Dict, external_teams: Dict) -> List[Dict]:
    """Search for teams by name, abbreviation, state, or other attributes."""
    query_lower = query.lower()
    results = []
    
    # Search NCAA teams
    for exact_name, team_id in teams_by_name.items():
        # Check full name
        if query_lower in exact_name.lower():
            # Get the exact name from the database
            results.append({
                'name': exact_name,  # Preserve exact case from database
                'id': team_id,
                'source': 'NCAA',
                'match_type': 'name'
            })
        
        # Check abbreviation in team_id
        if query_lower in team_id.lower():
            results.append({
                'name': exact_name,  # Preserve exact case from database
                'id': team_id,
                'source': 'NCAA',
                'match_type': 'abbreviation'
            })
    
    # Search external teams
    for team_id, info in external_teams.items():
        exact_name = info.get('name', '')
        state = info.get('state', '')
        division = info.get('division', '')
        conference = info.get('conference', '')
        
        # Check full name
        if query_lower in exact_name.lower():
            results.append({
                'name': exact_name,  # Preserve exact case from database
                'id': team_id,
                'source': 'External',
                'match_type': 'name',
                'state': state,
                'division': division,
                'conference': conference
            })
        
        # Check abbreviation
        if query_lower in team_id.lower():
            results.append({
                'name': exact_name,  # Preserve exact case from database
                'id': team_id,
                'source': 'External',
                'match_type': 'abbreviation',
                'state': state,
                'division': division,
                'conference': conference
            })
        
        # Check state
        if state and query_lower in state.lower():
            results.append({
                'name': exact_name,  # Preserve exact case from database
                'id': team_id,
                'source': 'External',
                'match_type': 'state',
                'state': state,
                'division': division,
                'conference': conference
            })
    
    # Sort results by match type (name matches first, then abbreviation, then state)
    match_type_order = {'name': 0, 'abbreviation': 1, 'state': 2}
    results.sort(key=lambda x: (match_type_order.get(x['match_type'], 3), x['name']))
    
    return results

def load_team_aliases():
    """Load team aliases from JSON file."""
    try:
        with open('data/team_aliases.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_team_aliases(aliases):
    """Save team aliases to JSON file."""
    with open('data/team_aliases.json', 'w') as f:
        json.dump(aliases, f, indent=2)

def resolve_team(team_name, teams_by_name, external_teams, interactive=True, auto_create=False, season_folder=None, auto_unattached=False):
    """
    Resolve a team name to a consistent team_id.
    
    Args:
        team_name: The team name to resolve
        teams_by_name: Dictionary mapping NCAA team names to team IDs
        external_teams: Dictionary of external teams
        interactive: Whether to prompt for user input when team is not found
        auto_create: Whether to automatically create external teams (if interactive=False)
        season_folder: The specific season folder to search in
        auto_unattached: Whether to automatically mark single-match teams as Unattached
    
    Returns:
        team_id: The resolved team ID
    """
    # Load team mappings and aliases
    team_mappings = load_team_mappings()
    team_aliases = load_team_aliases()
    
    # Check for exact match in aliases first
    if team_name in team_aliases:
        target_name = team_aliases[team_name]
        print(f"\nUsing alias: {team_name} -> {target_name}")
        # Recursively resolve the target name
        return resolve_team(target_name, teams_by_name, external_teams, interactive, auto_create, season_folder, auto_unattached)
    
    # 0. Check if we already have a mapping for this exact team name
    if team_name in team_mappings:
        return team_mappings[team_name]
    
    # 1. Try to find team in official NCAA database (case-insensitive)
    team_name_lower = team_name.lower()
    for exact_name, team_id in teams_by_name.items():
        if team_name_lower == exact_name.lower():
            # Found a match - use the exact name from the database
            return team_id
    
    # 2. Check external teams JSON file (case-insensitive)
    for team_id, info in external_teams.items():
        exact_name = info.get('name', '')
        if team_name_lower == exact_name.lower() or team_name.upper() == team_id:
            # Found a match - use the exact name from external teams
            return team_id
    
    # 3. If not interactive, create new or use abbreviation
    if not interactive:
        if auto_create:
            # Generate a new team ID
            new_id = team_name[:4].upper()
            suffix = 1
            
            # Ensure ID is unique
            base_id = new_id
            while new_id in external_teams:
                new_id = f"{base_id}{suffix}"
                suffix += 1
            
            # Add to external teams
            external_teams[new_id] = {
                "name": team_name,  # Keep original case
                "team_id": new_id,
                "auto_created": True  # Flag for later review
            }
            
            # Save updated external teams
            save_external_teams(external_teams)
            
            return new_id
        else:
            # Just use abbreviation without saving (old behavior)
            return team_name[:4].upper()
    
    # 4. Interactive resolution
    # Find matches first to show count
    matches = find_matches_with_team(team_name, season_folder)
    match_count = len(matches)
    print(f"\n⚠️ Unknown team: {team_name} ({match_count} match{'es' if match_count != 1 else ''})")
    
    # If auto_unattached is enabled and there's only one match, automatically mark as Unattached
    if auto_unattached and match_count == 1:
        target_name = "Unattached"
        target_id = "UNAT"
        
        print(f"\nAuto-marking single match as Unattached:")
        print(f"- {matches[0]['wrestler']}: {matches[0]['match']['summary']}")
        
        update_matches_with_team(team_name, target_name, matches)
        print(f"✅ Updated match to use Unattached")
        return target_id
    
    # Find similar teams
    similar_teams = get_similar_teams(team_name, teams_by_name, external_teams)
    
    # Build menu options
    menu_options = []
    
    # Add similar teams as options
    if similar_teams:
        print("\nSimilar teams found:")
        for i, team in enumerate(similar_teams[:10], 1):
            letter = chr(64 + i)  # A=1, B=2, etc.
            print(f"{letter}. {team['name']} ({team['id']}) - {team['source']} (Similarity: {team['similarity']:.2f})")
            menu_options.append(('similar', team))
    
    # Add other options
    print("\nOther options:")
    print("1. Enter a different team ID")
    print("2. Add as new external team")
    print("3. Skip (use temporary ID)")
    print("4. Search for team")
    print("5. Select Unattached (UNAT)")
    
    while True:
        choice = input("\nEnter choice (A/B/1/2/3/4/5): ").upper()
        
        if choice in [chr(65 + i) for i in range(len(menu_options))]:  # A, B, etc.
            selected_team = menu_options[ord(choice) - 65][1]
            target_name = selected_team['name']
            target_id = selected_team['id']
            
            # Ask if user wants to create an alias
            create_alias = input(f"\nCreate alias '{team_name}' -> '{target_name}' for future use? (y/n): ").lower() == 'y'
            if create_alias:
                team_aliases[team_name] = target_name
                save_team_aliases(team_aliases)
                print(f"✅ Alias saved: {team_name} -> {target_name}")
            
            # Update matches
            update_matches_with_team(team_name, target_name, matches)
            print(f"✅ Updated {len(matches)} matches to use {target_name}")
            return target_id
        elif choice == '1':
            target_id = input("Enter team ID: ").upper()
            target_name = None
            
            # Try to find the name for this ID
            for name, id in teams_by_name.items():
                if id == target_id:
                    target_name = name
                    break
            
            if not target_name:
                for id, info in external_teams.items():
                    if id == target_id:
                        target_name = info['name']
                        break
            
            if not target_name:
                print(f"⚠️ Warning: No team found with ID {target_id}")
                target_name = input("Enter team name: ")
            
            # Ask if user wants to create an alias
            create_alias = input(f"\nCreate alias '{team_name}' -> '{target_name}' for future use? (y/n): ").lower() == 'y'
            if create_alias:
                team_aliases[team_name] = target_name
                save_team_aliases(team_aliases)
                print(f"✅ Alias saved: {team_name} -> {target_name}")
            
            # Update matches
            update_matches_with_team(team_name, target_name, matches)
            print(f"✅ Updated {len(matches)} matches to use {target_name}")
            return target_id
        elif choice == '2':
            # Generate a new team ID
            new_id = team_name[:4].upper()
            suffix = 1
            
            # Ensure ID is unique
            base_id = new_id
            while new_id in external_teams:
                new_id = f"{base_id}{suffix}"
                suffix += 1
            
            # Add to external teams
            external_teams[new_id] = {
                "name": team_name,  # Keep original case
                "team_id": new_id
            }
            
            # Save updated external teams
            save_external_teams(external_teams)
            
            print(f"✅ Added new external team: {team_name} ({new_id})")
            return new_id
        elif choice == '3':
            return team_name[:4].upper()
        elif choice == '4':
            search_term = input("Enter search term: ")
            results = search_teams(search_term, teams_by_name, external_teams)
            
            if not results:
                print("No matches found.")
                continue
            
            print("\nSearch results:")
            for i, team in enumerate(results[:10], 1):
                print(f"{i}. {team['name']} ({team['id']}) - {team['source']}")
            
            while True:
                try:
                    choice = int(input("\nEnter choice (1-10) or 0 to search again: "))
                    if choice == 0:
                        break
                    if 1 <= choice <= len(results):
                        selected_team = results[choice - 1]
                        target_name = selected_team['name']
                        target_id = selected_team['id']
                        
                        # Ask if user wants to create an alias
                        create_alias = input(f"\nCreate alias '{team_name}' -> '{target_name}' for future use? (y/n): ").lower() == 'y'
                        if create_alias:
                            team_aliases[team_name] = target_name
                            save_team_aliases(team_aliases)
                            print(f"✅ Alias saved: {team_name} -> {target_name}")
                        
                        # Update matches
                        update_matches_with_team(team_name, target_name, matches)
                        print(f"✅ Updated {len(matches)} matches to use {target_name}")
                        return target_id
                except ValueError:
                    print("Invalid input. Please enter a number.")
        elif choice == '5':
            target_name = "Unattached"
            target_id = "UNAT"
            
            # Ask if user wants to create an alias
            create_alias = input(f"\nCreate alias '{team_name}' -> '{target_name}' for future use? (y/n): ").lower() == 'y'
            if create_alias:
                team_aliases[team_name] = target_name
                save_team_aliases(team_aliases)
                print(f"✅ Alias saved: {team_name} -> {target_name}")
            
            # Update matches
            update_matches_with_team(team_name, target_name, matches)
            print(f"✅ Updated {len(matches)} matches to use Unattached")
            return target_id
        else:
            print("Invalid choice. Please try again.")

def count_unidentified_teams(teams_by_name: Dict, team_mappings: Dict, external_teams: Dict, season_folder: str = None) -> Dict:
    """Count and list all unidentified teams in match data."""
    unidentified_teams = set()
    
    # If season_folder is provided, only search in that folder
    folders_to_search = [Path(season_folder)] if season_folder else [f for f in Path('data').glob('*') if f.is_dir() and f.name.isdigit()]
    
    # Search through specified folders
    for folder in folders_to_search:
        if not folder.is_dir():
            continue
            
        print(f"\nSearching in folder: {folder}")
        # Search through all team JSON files in this season
        for team_file in folder.glob('*.json'):
            with open(team_file) as f:
                team_data = json.load(f)
                
            for wrestler in team_data.get('roster', []):
                for match in wrestler.get('matches', []):
                    # Get team names
                    winner_team = match.get('winner_team', '')
                    loser_team = match.get('loser_team', '')
                    
                    # Skip if both team names are empty
                    if not winner_team and not loser_team:
                        continue
                    
                    # Check winner team
                    if winner_team:
                        winner_lower = winner_team.lower()
                        if (winner_lower not in teams_by_name and 
                            winner_team not in team_mappings and 
                            not any(winner_lower == info.get('name', '').lower() or 
                                  winner_team.upper() == team_id 
                                  for team_id, info in external_teams.items())):
                            unidentified_teams.add(winner_team)
                            print(f"\nFound unknown team '{winner_team}' in file {team_file}")
                            print(f"Match details: {match.get('date')} - {match.get('event')}")
                            print(f"Winner: {match.get('winner_name')} ({winner_team})")
                            print(f"Loser: {match.get('loser_name')} ({winner_team})")
                    
                    # Check loser team
                    if loser_team:
                        loser_lower = loser_team.lower()
                        if (loser_lower not in teams_by_name and 
                            loser_team not in team_mappings and 
                            not any(loser_lower == info.get('name', '').lower() or 
                                  loser_team.upper() == team_id 
                                  for team_id, info in external_teams.items())):
                            unidentified_teams.add(loser_team)
                            print(f"\nFound unknown team '{loser_team}' in file {team_file}")
                            print(f"Match details: {match.get('date')} - {match.get('event')}")
                            print(f"Winner: {match.get('winner_name')} ({winner_team})")
                            print(f"Loser: {match.get('loser_name')} ({loser_team})")
    
    return {
        'count': len(unidentified_teams),
        'teams': sorted(list(unidentified_teams))
    }

# Usage example
if __name__ == "__main__":
    # Test the resolver
    teams_by_name = {
        "penn state": "PEST-Penn-State",
        "ohio state": "OHST-Ohio-State",
        "michigan": "MICH-Michigan"
    }
    
    external_teams = load_external_teams()
    
    # Test resolution
    test_teams = [
        "Penn State",
        "Kent State",
        "Unknown College"
    ]
    
    for team in test_teams:
        resolved_id = resolve_team(team, teams_by_name, external_teams)
        print(f"{team} -> {resolved_id}") 