import os
import json
import uuid
import boto3
from pathlib import Path
from decimal import Decimal


# Connect to local DynamoDB
DB = boto3.resource('dynamodb', endpoint_url='http://localhost:8001')
career_table = DB.Table('career_wrestler')
season_table = DB.Table('season_wrestler')
link_table = DB.Table('career_link')
match_table = DB.Table('matches')

# Path to 2014 JSON files
ROSTER_PATH = Path('/Users/tjthompson/Documents/Cursor/wrestledata.com/data/2014')

# Track assigned career IDs
career_id_counter = 1

def generate_career_id():
    global career_id_counter
    cid = f"career_{career_id_counter:05}"
    career_id_counter += 1
    return cid

def upload_2014_roster(file_path):
    with open(file_path, 'r') as f:
        team_data = json.load(f)

    team_name = team_data['team_name']
    season = team_data['season']
    division = team_data.get('division', '')
    abbreviation = team_data.get('abbreviation', '')

    for wrestler in team_data['roster']:
        season_wrestler_id = wrestler['season_wrestler_id']
        name = wrestler['name']
        grade = wrestler.get('grade', '')
        weight = wrestler.get('weight_class', '')

        # Create new career_id
        career_id = generate_career_id()

        # Insert into career_wrestler
        career_table.put_item(Item={
            'career_id': career_id,
            'name_variants': [name],
            'notes': ''
        })

        # Insert into season_wrestler
        season_table.put_item(Item={
            'season_wrestler_id': season_wrestler_id,
            'career_id': career_id,
            'team_id': abbreviation,
            'season': season,
            'weight_class': weight,
            'class_year': grade,
            'name': name
        })

        # Insert into career_link
        link_table.put_item(Item={
            'season_wrestler_id': season_wrestler_id,
            'linked_career_id': career_id,
            'match_type': 'new',
            'confidence_score': Decimal('1.0'),
            'manual_override': False
        })

        # Insert matches
        for match in wrestler.get('matches', []):
            match_id = str(uuid.uuid4())
            match_table.put_item(Item={
                'match_id': match_id,
                'wrestler1_id': season_wrestler_id,
                'wrestler2_id': match.get('opponent_id', 'unknown'),
                'winner_id': season_wrestler_id if match.get('is_winner') else match.get('opponent_id', 'unknown'),
                'result': match.get('result', ''),
                'event_name': match.get('event', ''),
                'date': match.get('date', '')
            })

if __name__ == '__main__':
    files = list(ROSTER_PATH.glob('*.json'))
    print(f"📁 Found {len(files)} team files in {ROSTER_PATH}")

    for file in files:
        print(f"📁 Processing: {file.name}")
        upload_2014_roster(file)
        print(f"✅ Done with {file.name}\n")

    print("✅ Finished uploading 2014 season data.")
