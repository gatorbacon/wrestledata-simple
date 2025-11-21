import boto3
from boto3.dynamodb.conditions import Key
from decimal import Decimal

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb', endpoint_url='http://localhost:8001')
teams_table = dynamodb.Table('teams')
team_seasons_table = dynamodb.Table('team_seasons')

def get_all_teams():
    """Get all teams from the teams table."""
    teams = []
    response = teams_table.scan()
    teams.extend(response['Items'])
    
    while 'LastEvaluatedKey' in response:
        response = teams_table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        teams.extend(response['Items'])
    
    return teams

def get_team_seasons(team_id):
    """Get all seasons for a specific team, sorted by season number."""
    seasons = []
    response = team_seasons_table.query(
        KeyConditionExpression=Key('team_id').eq(team_id)
    )
    seasons.extend(response['Items'])
    
    while 'LastEvaluatedKey' in response:
        response = team_seasons_table.query(
            KeyConditionExpression=Key('team_id').eq(team_id),
            ExclusiveStartKey=response['LastEvaluatedKey']
        )
        seasons.extend(response['Items'])
    
    # Sort seasons by season number in descending order (most recent first)
    return sorted(seasons, key=lambda x: x['season'], reverse=True)

def update_team_abbreviation(team_id, abbreviation):
    """Update a team's abbreviation in the teams table."""
    try:
        teams_table.update_item(
            Key={'team_id': team_id},
            UpdateExpression='SET abbreviation = :abbr',
            ExpressionAttributeValues={':abbr': abbreviation}
        )
        return True
    except Exception as e:
        print(f"❌ Error updating team {team_id}: {str(e)}")
        return False

def main():
    print("Starting team abbreviation update process...")
    teams = get_all_teams()
    print(f"Found {len(teams)} teams to process")
    
    updated_count = 0
    skipped_count = 0
    error_count = 0
    
    for team in teams:
        team_id = team['team_id']
        print(f"\nProcessing team: {team_id}")
        
        # Get all seasons for this team
        seasons = get_team_seasons(team_id)
        
        if not seasons:
            print(f"⚠️ No seasons found for team {team_id}")
            skipped_count += 1
            continue
        
        # Get the most recent season's abbreviation
        most_recent_season = seasons[0]
        most_recent_abbr = most_recent_season.get('abbreviation')
        
        if not most_recent_abbr:
            print(f"⚠️ No abbreviation found in season {most_recent_season['season']} for team {team_id}")
            skipped_count += 1
            continue
            
        print(f"Most recent season: {most_recent_season['season']}, abbreviation: {most_recent_abbr}")
        
        # Update the team's abbreviation
        if update_team_abbreviation(team_id, most_recent_abbr):
            updated_count += 1
            print(f"✅ Updated {team_id} with abbreviation {most_recent_abbr}")
        else:
            error_count += 1
    
    print("\n=== Summary ===")
    print(f"Total teams processed: {len(teams)}")
    print(f"Successfully updated: {updated_count}")
    print(f"Skipped (no seasons/abbreviation): {skipped_count}")
    print(f"Errors: {error_count}")

if __name__ == "__main__":
    main() 