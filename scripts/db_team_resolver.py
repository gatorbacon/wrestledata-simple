#!/usr/bin/env python3
"""
DynamoDB Team Resolver

This module provides functions for resolving team names to team IDs
using DynamoDB tables instead of JSON files.
"""

import boto3
import os
import json
import re
from pathlib import Path
from difflib import SequenceMatcher
from typing import Dict, List, Tuple, Optional, Set, Any
from boto3.dynamodb.conditions import Key, Attr

# DynamoDB setup - use local by default, can be overridden
ENDPOINT_URL = os.environ.get('DYNAMODB_ENDPOINT', 'http://localhost:8001')
dynamodb = boto3.resource('dynamodb', endpoint_url=ENDPOINT_URL)
teams_table = dynamodb.Table('teams')
team_seasons_table = dynamodb.Table('team_seasons')

def calculate_similarity(str1: str, str2: str) -> float:
    """Calculate similarity between two strings."""
    return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()

def normalize_team_name(name: str) -> str:
    """Normalize team name for comparison."""
    if not name:
        return ""
    name = re.sub(r'[^\w\s]', '', name)  # Remove punctuation
    name = re.sub(r'\s+', ' ', name)      # Normalize whitespace
    return name.strip().lower()

def load_teams_from_db() -> Tuple[Dict[str, str], Dict[str, Dict]]:
    """
    Load teams from DynamoDB.
    
    Returns:
        Tuple containing:
        - teams_by_name: Dictionary mapping normalized team names to team_ids
        - team_details: Dictionary mapping team_ids to full team details
    """
    teams_by_name = {}
    team_details = {}

    # Scan teams table
    response = teams_table.scan()
    teams = response['Items']
    
    # Process pagination if needed
    while 'LastEvaluatedKey' in response:
        response = teams_table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        teams.extend(response['Items'])
    
    print(f"Loaded {len(teams)} teams from DynamoDB")
    
    # Build lookup dictionaries
    for team in teams:
        team_id = team['team_id']
        name = team.get('name', '')
        
        if name:
            teams_by_name[normalize_team_name(name)] = team_id
        
        # Store full team details
        team_details[team_id] = team
        
        # Also index by aliases
        aliases = team.get('aliases', [])
        for alias in aliases:
            teams_by_name[normalize_team_name(alias)] = team_id
    
    return teams_by_name, team_details

def load_team_seasons() -> Dict[str, List[Dict]]:
    """
    Load team seasons from DynamoDB.
    
    Returns:
        Dictionary mapping team_ids to lists of season data
    """
    team_seasons = {}
    
    # Scan team_seasons table
    response = team_seasons_table.scan()
    seasons = response['Items']
    
    # Process pagination if needed
    while 'LastEvaluatedKey' in response:
        response = team_seasons_table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        seasons.extend(response['Items'])
    
    print(f"Loaded {len(seasons)} team seasons from DynamoDB")
    
    # Group seasons by team_id
    for season in seasons:
        team_id = season['team_id']
        if team_id not in team_seasons:
            team_seasons[team_id] = []
        team_seasons[team_id].append(season)
    
    return team_seasons

def get_similar_teams(team_name: str, teams_by_name: Dict[str, str], team_details: Dict[str, Dict], threshold: float = 0.6) -> List[Dict]:
    """
    Find teams with similar names to the given team name.
    
    Args:
        team_name: The team name to find similar matches for
        teams_by_name: Dictionary mapping team names to team_ids
        team_details: Dictionary mapping team_ids to full team details
        threshold: Minimum similarity score (0-1) to include in results
        
    Returns:
        List of dictionaries with team details and similarity scores
    """
    similar_teams = []
    norm_team_name = normalize_team_name(team_name)
    
    # Skip empty or very short team names
    if len(norm_team_name) < 3:
        return []
    
    # Check each team name for similarity
    for name, team_id in teams_by_name.items():
        # Skip exact matches - we only want similar, not identical
        if name == norm_team_name:
            continue
            
        similarity = calculate_similarity(norm_team_name, name)
        if similarity >= threshold:
            # Get team details
            team_info = team_details.get(team_id, {})
            
            # Add to results
            similar_teams.append({
                'team_id': team_id,
                'name': team_info.get('name', name),
                'state': team_info.get('state', ''),
                'similarity': similarity,
                'aliases': team_info.get('aliases', [])
            })
    
    # Sort by similarity (highest first)
    similar_teams.sort(key=lambda x: x['similarity'], reverse=True)
    
    # Return top 10 results
    return similar_teams[:10]

def add_team_alias(team_id: str, alias: str) -> bool:
    """
    Add an alias to a team.
    
    Args:
        team_id: The team ID
        alias: The new alias to add
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get current team data
        response = teams_table.get_item(Key={'team_id': team_id})
        if 'Item' not in response:
            print(f"Team {team_id} not found in database")
            return False
        
        team = response['Item']
        aliases = team.get('aliases', [])
        
        # Check if alias already exists
        if alias in aliases:
            print(f"Alias '{alias}' already exists for team {team_id}")
            return True
        
        # Add new alias
        aliases.append(alias)
        
        # Update team record
        teams_table.update_item(
            Key={'team_id': team_id},
            UpdateExpression='SET aliases = :aliases',
            ExpressionAttributeValues={':aliases': aliases}
        )
        
        print(f"Added alias '{alias}' to team {team_id}")
        return True
    except Exception as e:
        print(f"Error adding alias: {e}")
        return False

def create_new_team(name: str, state: str, aliases: List[str] = None) -> Optional[str]:
    """
    Create a new team in the database.
    
    Args:
        name: The team name
        state: Two-letter state code
        aliases: Optional list of aliases
        
    Returns:
        The new team_id if successful, None otherwise
    """
    try:
        # Generate team_id from name
        base_id = normalize_team_id(name)
        
        # Check if team_id already exists
        response = teams_table.get_item(Key={'team_id': base_id})
        if 'Item' in response:
            # Try with state suffix
            state_id = f"{base_id}-{state}"
            response = teams_table.get_item(Key={'team_id': state_id})
            
            if 'Item' in response:
                # Try with numeric suffix
                counter = 2
                while True:
                    numeric_id = f"{state_id}{counter}"
                    response = teams_table.get_item(Key={'team_id': numeric_id})
                    if 'Item' not in response:
                        base_id = numeric_id
                        break
                    counter += 1
            else:
                base_id = state_id
        
        # Create new team
        teams_table.put_item(Item={
            'team_id': base_id,
            'name': name,
            'state': state,
            'aliases': aliases or []
        })
        
        print(f"Created new team: {name} (ID: {base_id})")
        return base_id
    except Exception as e:
        print(f"Error creating team: {e}")
        return None

def normalize_team_id(name: str) -> str:
    """Normalize a team name for use as an ID."""
    # Replace spaces and special chars with hyphens
    normalized = re.sub(r'[^a-zA-Z0-9]', '-', name)
    # Remove consecutive hyphens
    normalized = re.sub(r'-+', '-', normalized)
    # Remove leading and trailing hyphens
    normalized = normalized.strip('-')
    return normalized

def search_teams(query: str, teams_by_name: Dict[str, str], team_details: Dict[str, Dict]) -> List[Dict]:
    """
    Search for teams by name, state, or other attributes.
    
    Args:
        query: The search query
        teams_by_name: Dictionary mapping team names to team_ids
        team_details: Dictionary mapping team_ids to full team details
        
    Returns:
        List of dictionaries with team details
    """
    query_lower = query.lower()
    results = []
    
    # Check each team for matches
    for team_id, team_info in team_details.items():
        name = team_info.get('name', '')
        state = team_info.get('state', '')
        aliases = team_info.get('aliases', [])
        
        # Check name
        if query_lower in name.lower():
            results.append({
                'team_id': team_id,
                'name': name,
                'state': state,
                'match_type': 'name',
                'aliases': aliases
            })
            continue
            
        # Check team_id
        if query_lower in team_id.lower():
            results.append({
                'team_id': team_id,
                'name': name,
                'state': state,
                'match_type': 'id',
                'aliases': aliases
            })
            continue
            
        # Check state
        if query_lower == state.lower():
            results.append({
                'team_id': team_id,
                'name': name,
                'state': state, 
                'match_type': 'state',
                'aliases': aliases
            })
            continue
            
        # Check aliases
        for alias in aliases:
            if query_lower in alias.lower():
                results.append({
                    'team_id': team_id,
                    'name': name,
                    'state': state,
                    'match_type': 'alias',
                    'aliases': aliases
                })
                break
    
    # Sort results by match type (name matches first, then id, then state)
    match_type_order = {'name': 0, 'id': 1, 'alias': 2, 'state': 3}
    results.sort(key=lambda x: match_type_order.get(x['match_type'], 4))
    
    return results

def resolve_team(team_name: str, teams_by_name: Dict[str, str], team_details: Dict[str, Dict], 
                interactive: bool = True, auto_create: bool = False, season_year: int = None,
                auto_unattached: bool = False, match_count: int = None) -> Optional[str]:
    """
    Resolve a team name to a consistent team_id.
    
    Args:
        team_name: The team name to resolve
        teams_by_name: Dictionary mapping team names to team_ids
        team_details: Dictionary mapping team_ids to full team details
        interactive: Whether to prompt for user input when team is not found
        auto_create: Whether to automatically create new teams (if interactive=False)
        season_year: The season year (optional)
        auto_unattached: Whether to automatically mark single-match teams as Unattached
        match_count: Number of matches this team appears in (optional)
        
    Returns:
        team_id: The resolved team ID
    """
    # Skip empty team names
    if not team_name or team_name.strip() == '':
        return None
    
    # Check for Unattached, Bye, or similar
    norm_name = normalize_team_name(team_name)
    if 'unattached' in norm_name or 'unat' in norm_name:
        return 'UNAT'
    if 'bye' in norm_name:
        return 'BYE'
    
    # 1. Check for exact match
    norm_team_name = normalize_team_name(team_name)
    if norm_team_name in teams_by_name:
        return teams_by_name[norm_team_name]
    
    # 2. Check for similar teams
    similar_teams = get_similar_teams(team_name, teams_by_name, team_details)
    
    # If not interactive, we're done
    if not interactive:
        if auto_create:
            # Create a new team with default state
            return create_new_team(team_name, 'XX')
        return None
    
    # 3. Interactive resolution
    match_info = f" ({match_count} matches)" if match_count is not None else ""
    print(f"\nTeam not found: '{team_name}'{match_info}")
    
    if similar_teams:
        print("\nSimilar teams found:")
        for i, team in enumerate(similar_teams, 1):
            print(f"{i}. {team['name']} ({team['state']}) [ID: {team['team_id']}] - Similarity: {team['similarity']:.2f}")
            
            # Show aliases if available
            if team['aliases']:
                print(f"   Aliases: {', '.join(team['aliases'])}")
    else:
        print("No similar teams found")
    
    print("\nOptions:")
    print("1. Select from similar teams")
    print("2. Search for a team")
    print("3. Create a new team")
    print("4. Mark as Unattached (UNAT)")
    print("5. Skip this team")
    
    choice = input("Choose an option (1-5): ").strip()
    
    if choice == '1' and similar_teams:
        while True:
            team_choice = input(f"Select team (1-{len(similar_teams)}): ").strip()
            try:
                idx = int(team_choice) - 1
                if 0 <= idx < len(similar_teams):
                    selected_team = similar_teams[idx]
                    
                    # Ask if user wants to create an alias
                    alias_choice = input(f"Create alias '{team_name}' -> '{selected_team['name']}' for future use? (y/n): ").lower()
                    if alias_choice == 'y':
                        add_team_alias(selected_team['team_id'], team_name)
                    
                    return selected_team['team_id']
                else:
                    print(f"Please enter a number between 1 and {len(similar_teams)}")
            except ValueError:
                print("Please enter a valid number")
    
    elif choice == '2':
        search_query = input("Enter search term: ").strip()
        search_results = search_teams(search_query, teams_by_name, team_details)
        
        if not search_results:
            print("No teams found matching your search")
            return resolve_team(team_name, teams_by_name, team_details, interactive, auto_create, season_year, auto_unattached, match_count)
        
        print("\nSearch results:")
        for i, team in enumerate(search_results, 1):
            print(f"{i}. {team['name']} ({team['state']}) [ID: {team['team_id']}]")
            
            # Show aliases if available
            if team['aliases']:
                print(f"   Aliases: {', '.join(team['aliases'])}")
        
        while True:
            team_choice = input(f"Select team (1-{len(search_results)}) or 'b' to go back: ").strip().lower()
            if team_choice == 'b':
                return resolve_team(team_name, teams_by_name, team_details, interactive, auto_create, season_year, auto_unattached, match_count)
                
            try:
                idx = int(team_choice) - 1
                if 0 <= idx < len(search_results):
                    selected_team = search_results[idx]
                    
                    # Ask if user wants to create an alias
                    alias_choice = input(f"Create alias '{team_name}' -> '{selected_team['name']}' for future use? (y/n): ").lower()
                    if alias_choice == 'y':
                        add_team_alias(selected_team['team_id'], team_name)
                    
                    return selected_team['team_id']
                else:
                    print(f"Please enter a number between 1 and {len(search_results)}")
            except ValueError:
                print("Please enter a valid number")
    
    elif choice == '3':
        name = input(f"Team name [{team_name}]: ").strip() or team_name
        state = input("State (2-letter code): ").strip().upper()
        
        # Validate state code
        while len(state) != 2 or not re.match(r'^[A-Z]{2}$', state):
            print("Please enter a valid 2-letter state code (e.g., CA, NY)")
            state = input("State (2-letter code): ").strip().upper()
        
        aliases = []
        add_alias = input(f"Add an alias? (y/n): ").lower()
        while add_alias == 'y':
            alias = input("Alias: ").strip()
            if alias:
                aliases.append(alias)
            add_alias = input(f"Add another alias? (y/n): ").lower()
        
        team_id = create_new_team(name, state, aliases)
        if team_id:
            return team_id
        
        print("Failed to create team. Please try again.")
        return resolve_team(team_name, teams_by_name, team_details, interactive, auto_create, season_year, auto_unattached, match_count)
    
    elif choice == '4':
        print(f"Marking '{team_name}' as Unattached (UNAT)")
        return 'UNAT'
    
    elif choice == '5':
        print(f"Skipping team '{team_name}'")
        return None
    
    # If we reach here, something went wrong with the input
    print("Invalid choice. Please try again.")
    return resolve_team(team_name, teams_by_name, team_details, interactive, auto_create, season_year, auto_unattached, match_count)

def count_unidentified_teams(teams_list: List[str], teams_by_name: Dict[str, str]) -> int:
    """Count how many teams in the list are not in the known teams dictionary."""
    unidentified = 0
    for team in teams_list:
        if normalize_team_name(team) not in teams_by_name:
            unidentified += 1
    return unidentified

# Helper function to get team info by ID
def get_team_info(team_id: str) -> Optional[Dict]:
    """
    Get team information by team_id.
    
    Args:
        team_id: The team ID
        
    Returns:
        Dictionary with team details or None if not found
    """
    try:
        response = teams_table.get_item(Key={'team_id': team_id})
        if 'Item' in response:
            return response['Item']
        return None
    except Exception as e:
        print(f"Error getting team info: {e}")
        return None

# Helper function to get team season info
def get_team_season(team_id: str, season: int) -> Optional[Dict]:
    """
    Get team season information.
    
    Args:
        team_id: The team ID
        season: The season year
        
    Returns:
        Dictionary with team season details or None if not found
    """
    try:
        # Query the GSI for team_id + season
        response = team_seasons_table.query(
            IndexName='team_id-season-index',
            KeyConditionExpression=Key('team_id').eq(team_id) & Key('season').eq(season)
        )
        
        if response['Items']:
            return response['Items'][0]
        return None
    except Exception as e:
        print(f"Error getting team season: {e}")
        return None 