#!/usr/bin/env python3
"""
Upload Teams to DynamoDB

This script reads the universal_teams.json file and uploads the data to DynamoDB tables:
- teams table: Contains basic team information
- team_seasons table: Contains team data for each season
"""

import json
import boto3
import re
from pathlib import Path
from typing import Dict, List, Set
import argparse

# Configuration
DATA_DIR = Path("data")
TEAM_LISTS_DIR = DATA_DIR / "team_lists"
UNIVERSAL_TEAMS_FILE = TEAM_LISTS_DIR / "universal_teams.json"

def normalize_for_id(name: str) -> str:
    """Normalize a team name for use as an ID."""
    # Replace spaces and special chars with hyphens
    normalized = re.sub(r'[^a-zA-Z0-9]', '-', name)
    # Remove consecutive hyphens
    normalized = re.sub(r'-+', '-', normalized)
    # Remove leading and trailing hyphens
    normalized = normalized.strip('-')
    return normalized

def parse_divisions(division_str: str) -> List[str]:
    """Parse the division string into a unique list of divisions."""
    if not division_str or division_str == "Unknown":
        return ["Unknown"]
    
    # Split by commas and remove duplicates while preserving order
    divisions = []
    seen = set()
    for div in division_str.split(', '):
        div = div.strip()
        if div and div not in seen:
            divisions.append(div)
            seen.add(div)
    
    return divisions or ["Unknown"]

def create_tables(dynamodb):
    """Create teams and team_seasons tables if they don't exist."""
    existing_tables = dynamodb.meta.client.list_tables()['TableNames']
    
    # Create teams table if it doesn't exist
    if 'teams' not in existing_tables:
        print("Creating teams table...")
        try:
            dynamodb.create_table(
                TableName='teams',
                KeySchema=[
                    {'AttributeName': 'team_id', 'KeyType': 'HASH'}
                ],
                AttributeDefinitions=[
                    {'AttributeName': 'team_id', 'AttributeType': 'S'}
                ],
                BillingMode='PAY_PER_REQUEST'
            )
            print("Teams table created")
        except Exception as e:
            print(f"Error creating teams table: {e}")
    
    # Create team_seasons table if it doesn't exist
    if 'team_seasons' not in existing_tables:
        print("Creating team_seasons table...")
        try:
            dynamodb.create_table(
                TableName='team_seasons',
                KeySchema=[
                    {'AttributeName': 'team_season_id', 'KeyType': 'HASH'}
                ],
                AttributeDefinitions=[
                    {'AttributeName': 'team_season_id', 'AttributeType': 'S'},
                    {'AttributeName': 'team_id', 'AttributeType': 'S'},
                    {'AttributeName': 'season', 'AttributeType': 'N'}
                ],
                GlobalSecondaryIndexes=[
                    {
                        'IndexName': 'team_id-season-index',
                        'KeySchema': [
                            {'AttributeName': 'team_id', 'KeyType': 'HASH'},
                            {'AttributeName': 'season', 'KeyType': 'RANGE'}
                        ],
                        'Projection': {'ProjectionType': 'ALL'},
                        'ProvisionedThroughput': {'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
                    }
                ],
                ProvisionedThroughput={'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
            )
            print("Team seasons table created")
        except Exception as e:
            print(f"Error creating team_seasons table: {e}")
    
    # Wait for tables to be created
    print("Waiting for tables to be ready...")
    teams_table = dynamodb.Table('teams')
    team_seasons_table = dynamodb.Table('team_seasons')
    try:
        teams_table.wait_until_exists()
        team_seasons_table.wait_until_exists()
    except Exception as e:
        print(f"Error waiting for tables: {e}")
    
    return teams_table, team_seasons_table

def clear_tables(teams_table, team_seasons_table, skip_clear=False):
    """Clear existing data from both tables."""
    if skip_clear:
        print("Skipping table clearing as requested")
        return
    
    # Clear teams table
    print("Clearing teams table...")
    try:
        scan_response = teams_table.scan(ProjectionExpression='team_id')
        items = scan_response.get('Items', [])
        if items:
            for item in items:
                try:
                    teams_table.delete_item(Key={'team_id': item['team_id']})
                except Exception as e:
                    print(f"Error deleting team {item['team_id']}: {e}")
            print(f"Cleared {len(items)} teams")
        else:
            print("No teams to clear")
    except Exception as e:
        print(f"Error clearing teams table: {e}")
    
    # Clear team_seasons table
    print("Clearing team_seasons table...")
    try:
        scan_response = team_seasons_table.scan(ProjectionExpression='team_season_id')
        items = scan_response.get('Items', [])
        if items:
            print(f"Found {len(items)} team seasons to delete")
            for i, item in enumerate(items):
                try:
                    team_seasons_table.delete_item(Key={'team_season_id': item['team_season_id']})
                    if (i + 1) % 100 == 0:
                        print(f"Deleted {i + 1}/{len(items)} team seasons")
                except Exception as e:
                    print(f"Error deleting team season {item['team_season_id']}: {e}")
            print(f"Cleared {len(items)} team seasons")
        else:
            print("No team seasons to clear")
    except Exception as e:
        print(f"Error clearing team_seasons table: {e}")

def check_team_id_uniqueness(team_ids: Dict[str, str], base_id: str, state: str) -> str:
    """Check if a team ID is unique, and handle conflicts."""
    if base_id not in team_ids:
        return base_id
    
    # Try adding state
    state_id = f"{base_id}-{state}"
    if state_id not in team_ids:
        return state_id
    
    # If still not unique, add a number
    counter = 2
    while f"{state_id}{counter}" in team_ids:
        counter += 1
    return f"{state_id}{counter}"

def process_teams(universal_teams: Dict) -> Dict[str, str]:
    """Process universal teams and return a mapping of original IDs to new team_ids."""
    team_id_mapping = {}
    new_team_ids = {}  # To check for uniqueness
    
    for original_id, team_data in universal_teams.items():
        universal_name = team_data['universal_name']
        state = team_data['state']
        
        # Create normalized team_id
        base_id = normalize_for_id(universal_name)
        team_id = check_team_id_uniqueness(new_team_ids, base_id, state)
        
        # Store mapping
        team_id_mapping[original_id] = team_id
        new_team_ids[team_id] = original_id
    
    return team_id_mapping

def upload_to_dynamodb(teams_table, team_seasons_table, universal_teams: Dict, team_id_mapping: Dict[str, str]):
    """Upload data to DynamoDB tables."""
    team_count = 0
    season_count = 0
    
    # First upload teams (smaller table)
    print("Uploading teams...")
    for original_id, team_data in universal_teams.items():
        team_id = team_id_mapping[original_id]
        universal_name = team_data['universal_name']
        state = team_data['state']
        
        # Add to teams table
        try:
            teams_table.put_item(Item={
                'team_id': team_id,
                'name': universal_name,
                'state': state,
                'aliases': []  # Empty for now
            })
            team_count += 1
            if team_count % 50 == 0:
                print(f"Uploaded {team_count} teams...")
        except Exception as e:
            print(f"Error uploading team {team_id}: {e}")
    
    print(f"Uploaded {team_count} teams")
    
    # Then upload seasons (larger table) with duplicate checking
    print("Uploading team seasons...")
    processed_season_ids = set()
    
    # Process each team and its seasons
    for original_id, team_data in universal_teams.items():
        team_id = team_id_mapping[original_id]
        
        # Process each season individually
        for season in team_data['seasons']:
            # Create unique team_season_id
            base_season_id = f"{team_id}-{season['year']}"
            
            # Handle potential duplicates (same team in same season but different records)
            if base_season_id in processed_season_ids:
                # Add a suffix for uniqueness
                suffix = 1
                while f"{base_season_id}-{suffix}" in processed_season_ids:
                    suffix += 1
                team_season_id = f"{base_season_id}-{suffix}"
            else:
                team_season_id = base_season_id
            
            processed_season_ids.add(team_season_id)
            
            # Parse divisions
            divisions = parse_divisions(season.get('division', 'Unknown'))
            
            # Add to team_seasons table
            try:
                team_seasons_table.put_item(Item={
                    'team_season_id': team_season_id,
                    'team_id': team_id,
                    'name': season['name'],
                    'abbreviation': season['abbreviation'],
                    'season': season['year'],
                    'governing_body': season['governing_body'],
                    'division': divisions
                })
                season_count += 1
                
                # Print progress periodically
                if season_count % 100 == 0:
                    print(f"Uploaded {season_count} team seasons...")
            except Exception as e:
                print(f"Error uploading season {team_season_id}: {e}")
    
    return team_count, season_count

def delete_table(dynamodb, table_name):
    """Delete a table if it exists."""
    try:
        table = dynamodb.Table(table_name)
        table.delete()
        print(f"Deleting {table_name} table...")
        waiter = dynamodb.meta.client.get_waiter('table_not_exists')
        waiter.wait(TableName=table_name)
        print(f"{table_name} table deleted")
        return True
    except Exception as e:
        print(f"Error deleting {table_name} table: {e}")
        return False

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description='Upload teams data to DynamoDB.')
    parser.add_argument('--endpoint-url', help='DynamoDB endpoint URL (for local testing)')
    parser.add_argument('--region', default='us-east-1', help='AWS region')
    parser.add_argument('--skip-clear', action='store_true', help='Skip clearing tables before upload')
    parser.add_argument('--force-recreate', action='store_true', help='Drop and recreate tables')
    args = parser.parse_args()
    
    # Check if universal teams file exists
    if not UNIVERSAL_TEAMS_FILE.exists():
        print(f"Error: {UNIVERSAL_TEAMS_FILE} does not exist")
        return
    
    # Load universal teams data
    print(f"Loading data from {UNIVERSAL_TEAMS_FILE}...")
    with open(UNIVERSAL_TEAMS_FILE, 'r') as f:
        universal_teams = json.load(f)
    
    print(f"Loaded {len(universal_teams)} teams from file")
    
    # Connect to DynamoDB
    dynamodb_kwargs = {'region_name': args.region}
    if args.endpoint_url:
        dynamodb_kwargs['endpoint_url'] = args.endpoint_url
        print(f"Connecting to local DynamoDB at {args.endpoint_url}")
    else:
        print("Connecting to AWS DynamoDB")
    
    dynamodb = boto3.resource('dynamodb', **dynamodb_kwargs)
    
    # Handle force recreate option
    if args.force_recreate:
        print("Force recreate option selected. Dropping and recreating tables...")
        delete_table(dynamodb, 'teams')
        delete_table(dynamodb, 'team_seasons')
    
    # Create or get tables
    teams_table, team_seasons_table = create_tables(dynamodb)
    
    # Skip clearing if force recreate was used
    if not args.force_recreate and not args.skip_clear:
        # Clear existing data
        clear_tables(teams_table, team_seasons_table, args.skip_clear)
    
    # Process teams to generate unique team_ids
    print("Processing teams and generating unique IDs...")
    team_id_mapping = process_teams(universal_teams)
    
    # Upload to DynamoDB
    print("Uploading data to DynamoDB...")
    team_count, season_count = upload_to_dynamodb(
        teams_table, team_seasons_table, universal_teams, team_id_mapping
    )
    
    print(f"Successfully uploaded {team_count} teams and {season_count} team seasons to DynamoDB")

if __name__ == "__main__":
    main() 