import os
import json
import uuid
import boto3
from pathlib import Path
from difflib import SequenceMatcher
from decimal import Decimal

DB = boto3.resource('dynamodb', endpoint_url='http://localhost:8001')
career_table = DB.Table('career_wrestler')
season_table = DB.Table('season_wrestler')
link_table = DB.Table('career_link')
match_table = DB.Table('matches')

ROSTER_PATH = Path("data/2015")

# --- Normalization Utilities ---
def normalize_name(name):
    return name.strip().lower()

def normalize_weight(weight):
    try:
        return int(float(weight))
    except:
        return None

def normalize_class_year(grade):
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

    return 0.1
    return 0

def name_similarity(a, b):
    return SequenceMatcher(None, normalize_name(a), normalize_name(b)).ratio()

def weight_score(w1, w2):
    if w1 is None or w2 is None:
        return 0
    diff = abs(w1 - w2)
    if diff <= 10:
        return 0.2  # Same or adjacent weight class
    elif diff <= 20:
        return 0.1  # Within two classes
    return 0
    diff = abs(w1 - w2)
    if diff <= 1:
        return 0.2
    elif diff == 2:
        return 0.1
    return 0

def match_wrestler(current, pool):
    best_match = None
    best_score = 0
    best_debug = {}

    for candidate in pool:
        score = 0
        cname = candidate.get('name', '')
        cteam = candidate.get('team_id', '')
        cweight = normalize_weight(candidate.get('weight_class'))
        cgrade = normalize_class_year(candidate.get('class_year', ''))

        name_sim = name_similarity(current['name'], cname)
        if name_sim >= 0.9:
            score += 0.5

        if current['team_id'] == cteam:
            score += 0.2

        ws = weight_score(normalize_weight(current['weight_class']), cweight)
        score += ws

        cs = class_year_score(normalize_class_year(current['class_year']), cgrade)
        score += cs

        if score > best_score:
            best_score = score
            best_match = candidate
            best_debug = {
                'name': cname,
                'team': cteam,
                'weight': cweight,
                'grade': cgrade,
                'name_sim': round(name_sim, 3),
                'weight_score': ws,
                'class_year_score': cs,
                'total_score': round(score, 3)
            }

    if normalize_name(current['name']) in ["carter mcelhany", "brett dempsey"]:
        print("\n🧪 Debug for Carter/Brett")
        print("  Input:", current)
        print("  Best match:", best_debug)

    return best_match, round(best_score, 2)

def get_next_career_id():
    response = career_table.scan(ProjectionExpression='career_id')
    ids = [int(item['career_id'].split('_')[1]) for item in response['Items']]
    return f"career_{(max(ids) + 1 if ids else 1):05}"

def fetch_2014_wrestlers():
    response = season_table.scan(
        FilterExpression=boto3.dynamodb.conditions.Attr('season').eq(2014)
    )
    return response['Items']

wrestlers_2014 = fetch_2014_wrestlers()

def upload_2015_roster(file_path):
    with open(file_path, 'r') as f:
        team_data = json.load(f)

    season = team_data['season']
    abbreviation = team_data.get('abbreviation', '')

    for wrestler in team_data['roster']:
        season_wrestler_id = wrestler['season_wrestler_id']
        name = wrestler['name']
        grade = normalize_class_year(wrestler.get('grade', ''))
        weight = normalize_weight(wrestler.get('weight_class', ''))

        current = {
            'name': name,
            'team_id': abbreviation,
            'weight_class': weight,
            'class_year': grade
        }

        if normalize_name(name) == "carter mcelhany":
            print("\n🧪 MATCH ATTEMPT: Carter McElhany (2015)")
            print("  Team:", abbreviation)
            print("  Weight:", weight)
            print("  Grade:", grade)

        match, confidence = match_wrestler(current, wrestlers_2014)

        if match and confidence >= 0.80:
            career_id = match['career_id']
            match_type = 'fuzzy' if name != match.get('name', '') else 'exact'
        else:
            career_id = get_next_career_id()
            match_type = 'new'
            career_table.put_item(Item={
                'career_id': career_id,
                'name_variants': [name],
                'notes': ''
            })

        season_table.put_item(Item={
            'season_wrestler_id': season_wrestler_id,
            'career_id': career_id,
            'team_id': abbreviation,
            'season': season,
            'weight_class': str(weight) if weight else '',
            'class_year': grade,
            'name': name
        })

        link_table.put_item(Item={
            'season_wrestler_id': season_wrestler_id,
            'linked_career_id': career_id,
            'match_type': match_type,
            'confidence_score': Decimal(str(confidence)),
            'manual_override': False
        })

        for match_data in wrestler.get('matches', []):
            match_id = str(uuid.uuid4())
            match_table.put_item(Item={
                'match_id': match_id,
                'wrestler1_id': season_wrestler_id,
                'wrestler2_id': match_data.get('opponent_id', 'unknown'),
                'winner_id': season_wrestler_id if match_data.get('is_winner') else match_data.get('opponent_id', 'unknown'),
                'result': match_data.get('result', ''),
                'event_name': match_data.get('event', ''),
                'date': match_data.get('date', '')
            })

if __name__ == '__main__':
    files = list(ROSTER_PATH.glob('*.json'))
    print(f"📁 Found {len(files)} team files in {ROSTER_PATH}")
    for file in files:
        print(f"🔄 Processing: {file.name}")
        upload_2015_roster(file)
        print(f"✅ Done with {file.name}\n")
    print("🎯 ALL 2015 WRESTLERS LINKED AND UPLOADED.")
