#!/usr/bin/env python3
"""
Team Standardization Script

This script identifies and standardizes team IDs across the database:
1. Scans all unique team_ids in the season_wrestler table
2. Checks if each team exists in the NCAA database or external teams file
3. For unmapped teams, allows user to:
   - Link to an existing team
   - Add as a new team to external_teams.json
4. Creates a team_mappings.json file to store decisions
5. Updates all wrestler records to use standardized team IDs
"""

import json
import os
import re
import boto3
from boto3.dynamodb.conditions import Key
import copy
from typing import Dict, List, Set, Tuple, Any, Optional
from decimal import Decimal
from pathlib import Path

# Initialize DynamoDB resources
dynamodb = boto3.resource(
    'dynamodb',
    endpoint_url='http://localhost:8001',
    region_name='us-east-1',
    aws_access_key_id='dummy',
    aws_secret_access_key='dummy'
)
season_table = dynamodb.Table('season_wrestler')
teams_table = dynamodb.Table('teams')
team_seasons_table = dynamodb.Table('team_seasons')
career_table = dynamodb.Table('career_wrestler')

# Define paths
EXTERNAL_TEAMS_PATH = 'data/external_teams.json'
TEAM_MAPPINGS_PATH = 'data/team_mappings.json'

def load_external_teams() -> Dict:
    """Load external teams from JSON file."""
    try:
        if os.path.exists(EXTERNAL_TEAMS_PATH):
            with open(EXTERNAL_TEAMS_PATH, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"❌ Error loading external teams: {e}")
        return {}

def save_external_teams(external_teams: Dict) -> bool:
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

def load_team_mappings() -> Dict:
    """Load team mappings from JSON file."""
    try:
        if os.path.exists(TEAM_MAPPINGS_PATH):
            with open(TEAM_MAPPINGS_PATH, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"❌ Error loading team mappings: {e}")
        return {}

def save_team_mappings(mappings: Dict) -> bool:
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

def get_all_ncaa_teams() -> Dict:
    """Get all NCAA teams from the database."""
    teams = {}
    try:
        # Scan the teams table
        response = teams_table.scan()
        items = response['Items']
        
        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = teams_table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            items.extend(response['Items'])
        
        for team in items:
            team_id = team.get('team_id')
            if team_id:
                teams[team_id] = {
                    'name': team.get('name', ''),
                    'division': team.get('division', ''),
                    'abbreviation': team.get('abbreviation', ''),
                    'state': team.get('state', '')
                }
        
        print(f"✅ Loaded {len(teams)} NCAA teams from database")
        return teams
    except Exception as e:
        print(f"❌ Error loading NCAA teams: {e}")
        return {}

def get_all_unique_team_ids() -> Set[str]:
    """Get all unique team_ids from the season_wrestler table."""
    team_ids = set()
    try:
        # Scan the season_wrestler table
        response = season_table.scan(
            ProjectionExpression="team_id"
        )
        items = response['Items']
        
        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = season_table.scan(
                ExclusiveStartKey=response['LastEvaluatedKey'],
                ProjectionExpression="team_id"
            )
            items.extend(response['Items'])
        
        for item in items:
            team_id = item.get('team_id')
            if team_id:
                team_ids.add(team_id)
        
        print(f"✅ Found {len(team_ids)} unique team IDs in the season_wrestler table")
        return team_ids
    except Exception as e:
        print(f"❌ Error scanning season_wrestler table: {e}")
        return set()

def calculate_team_similarity(team1: str, team2: str) -> float:
    """Calculate similarity between two team IDs."""
    # Simple check for exact match or substring
    if team1.lower() == team2.lower():
        return 1.0
    if team1.lower() in team2.lower() or team2.lower() in team1.lower():
        return 0.8
        
    # Check for common prefix/suffix (like BCC vs JUCO-BCC)
    t1_parts = set(re.split(r'[-_\s]', team1.lower()))
    t2_parts = set(re.split(r'[-_\s]', team2.lower()))
    common_parts = t1_parts.intersection(t2_parts)
    
    if common_parts:
        return 0.6 * len(common_parts) / max(len(t1_parts), len(t2_parts))
    
    return 0.0

def find_similar_teams(team_id: str, all_teams: Dict) -> List[Tuple[str, float]]:
    """Find similar teams to the given team_id."""
    similar_teams = []
    
    for other_id, team_info in all_teams.items():
        similarity = calculate_team_similarity(team_id, other_id)
        if similarity > 0.3:  # Threshold for similarity
            name = team_info.get('name', other_id)
            similar_teams.append((other_id, similarity, name))
    
    # Sort by similarity (highest first)
    similar_teams.sort(key=lambda x: x[1], reverse=True)
    return similar_teams

def update_wrestler_team_ids(old_id: str, new_id: str) -> bool:
    """Update all wrestler records with the new team ID."""
    try:
        # Find all wrestlers with the old team ID
        response = season_table.scan(
            FilterExpression=Key('team_id').eq(old_id)
        )
        items = response['Items']
        
        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = season_table.scan(
                ExclusiveStartKey=response['LastEvaluatedKey'],
                FilterExpression=Key('team_id').eq(old_id)
            )
            items.extend(response['Items'])
        
        print(f"Found {len(items)} wrestlers with team ID {old_id}")
        
        # Update each wrestler
        updated_count = 0
        for item in items:
            try:
                season_table.update_item(
                    Key={
                        'season_wrestler_id': item['season_wrestler_id'],
                    },
                    UpdateExpression="SET team_id = :new_id",
                    ExpressionAttributeValues={
                        ':new_id': new_id
                    }
                )
                updated_count += 1
            except Exception as e:
                print(f"❌ Error updating wrestler {item.get('name')}: {e}")
        
        print(f"✅ Updated {updated_count}/{len(items)} wrestlers from {old_id} to {new_id}")
        return True
    except Exception as e:
        print(f"❌ Error updating team IDs: {e}")
        return False

def get_team_context(team_id: str) -> Dict:
    """Get context about a team from the season_wrestler table."""
    context = {
        'seasons': set(),
        'wrestlers': [],
        'divisions': set(),
        'conferences': set()
    }
    
    try:
        # Get wrestlers from season_wrestler table
        response = season_table.scan(
            FilterExpression=Key('team_id').eq(team_id)
        )
        items = response['Items']
        
        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = season_table.scan(
                ExclusiveStartKey=response['LastEvaluatedKey'],
                FilterExpression=Key('team_id').eq(team_id)
            )
            items.extend(response['Items'])
        
        for item in items:
            # Add season
            if 'season' in item:
                context['seasons'].add(item['season'])
            
            # Add wrestler info
            wrestler_info = {
                'name': item.get('name', 'Unknown'),
                'season': item.get('season', 'Unknown'),
                'weight': item.get('weight_class', 'Unknown'),
                'class_year': item.get('class_year', 'Unknown')
            }
            context['wrestlers'].append(wrestler_info)
            
            # Add division/conference if available
            if 'division' in item:
                context['divisions'].add(item['division'])
            if 'conference' in item:
                context['conferences'].add(item['conference'])
        
        # Get team season info if available
        try:
            for season in context['seasons']:
                response = team_seasons_table.get_item(
                    Key={
                        'team_id': team_id,
                        'season': season
                    }
                )
                if 'Item' in response:
                    item = response['Item']
                    if 'division' in item:
                        context['divisions'].add(item['division'])
                    if 'conference' in item:
                        context['conferences'].add(item['conference'])
        except Exception as e:
            print(f"Note: Could not access team_seasons table: {e}")
        
        return context
    except Exception as e:
        print(f"❌ Error getting team context: {e}")
        return context

def display_team_context(team_id: str, context: Dict):
    """Display context about a team."""
    print(f"\n=== Context for {team_id} ===")
    
    # Display seasons
    if context['seasons']:
        seasons = sorted(str(season) for season in context['seasons'])
        print(f"Seasons: {', '.join(seasons)}")
    
    # Display divisions/conferences
    if context['divisions']:
        print(f"Divisions: {', '.join(context['divisions'])}")
    if context['conferences']:
        print(f"Conferences: {', '.join(context['conferences'])}")
    
    # Display sample wrestlers (up to 5)
    if context['wrestlers']:
        print("\nSample Wrestlers:")
        for wrestler in context['wrestlers'][:5]:
            season = str(wrestler['season']) if isinstance(wrestler['season'], (int, float, Decimal)) else wrestler['season']
            print(f"- {wrestler['name']} ({season}, {wrestler['weight']}, {wrestler['class_year']})")
        if len(context['wrestlers']) > 5:
            print(f"... and {len(context['wrestlers']) - 5} more")

def find_matches_with_team(team_name: str) -> List[Dict]:
    """Find all matches where a specific team appears."""
    matches = []
    # Search through all season folders
    for season_folder in Path('data').glob('*'):
        if not season_folder.is_dir() or not season_folder.name.isdigit():
            continue
            
        # Search through all team JSON files in this season
        for team_file in season_folder.glob('*.json'):
            with open(team_file) as f:
                team_data = json.load(f)
                
            for wrestler in team_data.get('roster', []):
                for match in wrestler.get('matches', []):
                    if (match.get('winner_team', '').lower() == team_name.lower() or 
                        match.get('loser_team', '').lower() == team_name.lower()):
                        matches.append({
                            'file': team_file,
                            'wrestler': wrestler['name'],
                            'match': match
                        })
    
    return matches

def update_matches_with_team(team_name: str, new_team_name: str, matches: List[Dict]) -> None:
    """Update all matches with a specific team name to use the new team name."""
    for match_info in matches:
        file_path = match_info['file']
        match = match_info['match']
        
        # Update the team name in the match
        if match.get('winner_team', '').lower() == team_name.lower():
            match['winner_team'] = new_team_name
        if match.get('loser_team', '').lower() == team_name.lower():
            match['loser_team'] = new_team_name
            
        # Update the summary field to reflect the new team name
        if 'summary' in match:
            summary = match['summary']
            # Replace team name in parentheses
            summary = re.sub(
                rf'\({re.escape(team_name)}\)',
                f'({new_team_name})',
                summary
            )
            match['summary'] = summary
    
    # Save the updated files
    for match_info in matches:
        file_path = match_info['file']
        with open(file_path, 'w') as f:
            json.dump(team_data, f, indent=2)

def process_unmapped_teams():
    """Process all unmapped team IDs."""
    # Load existing data
    ncaa_teams = get_all_ncaa_teams()
    external_teams = load_external_teams()
    team_mappings = load_team_mappings()
    all_unique_team_ids = get_all_unique_team_ids()
    
    # Combine NCAA and external teams
    all_known_teams = {**ncaa_teams, **external_teams}
    
    # Find unmapped teams
    unmapped_teams = []
    for team_id in all_unique_team_ids:
        if team_id not in ncaa_teams and team_id not in external_teams and team_id not in team_mappings:
            unmapped_teams.append(team_id)
    
    print(f"Found {len(unmapped_teams)} unmapped team IDs")
    
    # Process each unmapped team
    for i, team_id in enumerate(unmapped_teams, 1):
        print(f"\n[{i}/{len(unmapped_teams)}] Processing team: {team_id}")
        
        # Get and display context
        context = get_team_context(team_id)
        display_team_context(team_id, context)
        
        # Find similar teams
        similar_teams = find_similar_teams(team_id, all_known_teams)
        
        if similar_teams:
            print(f"\nFound {len(similar_teams)} potentially similar teams:")
            for j, (similar_id, similarity, name) in enumerate(similar_teams[:10], 1):
                print(f"{j}. {similar_id} - {name} (Similarity: {similarity:.2f})")
                # Display context for similar teams too
                similar_context = get_team_context(similar_id)
                display_team_context(similar_id, similar_context)
        
        print("\nOptions:")
        print("1. Link to an existing team")
        print("2. Add as a new team to external_teams.json")
        print("3. Skip this team")
        
        choice = input("Enter your choice (1-3): ")
        
        if choice == '1':
            if similar_teams:
                team_choice = input("Enter the number of the team to link to (or 0 to cancel): ")
                try:
                    team_index = int(team_choice) - 1
                    if 0 <= team_index < len(similar_teams):
                        target_id = similar_teams[team_index][0]
                        team_mappings[team_id] = target_id
                        print(f"✅ Linked {team_id} to {target_id}")
                        
                        # Find all matches with this team
                        matches = find_matches_with_team(team_id)
                        if matches:
                            print(f"\nFound {len(matches)} matches with team '{team_id}'")
                            print("\nSample matches:")
                            for match in matches[:5]:  # Show first 5 matches
                                print(f"- {match['wrestler']}: {match['match']['summary']}")
                            
                            if len(matches) > 5:
                                print(f"... and {len(matches) - 5} more matches")
                            
                            update_now = input(f"\nUpdate all {len(matches)} matches to use '{target_id}' instead of '{team_id}'? (y/n): ")
                            if update_now.lower() == 'y':
                                update_matches_with_team(team_id, target_id, matches)
                                print(f"✅ Updated {len(matches)} matches")
                                
                                # Also update wrestler team IDs
                                update_wrestler_team_ids(team_id, target_id)
                    else:
                        print("Invalid choice, skipping...")
                except ValueError:
                    print("Invalid input, skipping...")
            else:
                custom_id = input("Enter the exact team ID to link to: ")
                if custom_id in all_known_teams:
                    team_mappings[team_id] = custom_id
                    print(f"✅ Linked {team_id} to {custom_id}")
                    
                    # Find all matches with this team
                    matches = find_matches_with_team(team_id)
                    if matches:
                        print(f"\nFound {len(matches)} matches with team '{team_id}'")
                        print("\nSample matches:")
                        for match in matches[:5]:  # Show first 5 matches
                            print(f"- {match['wrestler']}: {match['match']['summary']}")
                        
                        if len(matches) > 5:
                            print(f"... and {len(matches) - 5} more matches")
                        
                        update_now = input(f"\nUpdate all {len(matches)} matches to use '{custom_id}' instead of '{team_id}'? (y/n): ")
                        if update_now.lower() == 'y':
                            update_matches_with_team(team_id, custom_id, matches)
                            print(f"✅ Updated {len(matches)} matches")
                            
                            # Also update wrestler team IDs
                            update_wrestler_team_ids(team_id, custom_id)
                else:
                    print(f"❌ Team ID {custom_id} not found in known teams")
        
        elif choice == '2':
            team_name = input("Enter the team name: ")
            division = input("Enter the division (if known): ")
            conference = input("Enter the conference (if known): ")
            
            external_teams[team_id] = {
                "name": team_name,
                "team_id": team_id,
                "division": division if division else None,
                "conference": conference if conference else None
            }
            print(f"✅ Added {team_id} to external teams")
        
        # Save progress after each team
        save_team_mappings(team_mappings)
        save_external_teams(external_teams)
    
    print("\n✅ All unmapped teams processed")
    print(f"- {len(team_mappings)} teams mapped")
    print(f"- {len(external_teams)} teams in external_teams.json")

def apply_all_team_mappings():
    """Apply all team mappings to update the database."""
    team_mappings = load_team_mappings()
    
    if not team_mappings:
        print("No team mappings found. Nothing to apply.")
        return
    
    print(f"Found {len(team_mappings)} team mappings to apply")
    
    # Confirm before proceeding
    confirm = input("This will update all wrestler records. Do you want to proceed? (y/n): ")
    if confirm.lower() != 'y':
        print("Operation cancelled")
        return
    
    # Apply each mapping
    for old_id, new_id in team_mappings.items():
        print(f"Applying mapping: {old_id} -> {new_id}")
        update_wrestler_team_ids(old_id, new_id)
    
    print("✅ All team mappings applied")

def main():
    """Main function."""
    print("=== Team Standardization Tool ===\n")
    print("Options:")
    print("1. Process unmapped teams")
    print("2. Apply all team mappings")
    print("3. Exit")
    
    choice = input("Enter your choice (1-3): ")
    
    if choice == '1':
        process_unmapped_teams()
    elif choice == '2':
        apply_all_team_mappings()
    else:
        print("Exiting...")

if __name__ == "__main__":
    main() 