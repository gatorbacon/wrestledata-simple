import boto3
from boto3.dynamodb.conditions import Key
from collections import defaultdict

DB = boto3.resource('dynamodb', endpoint_url='http://localhost:8001')
season_table = DB.Table('season_wrestler')
link_table = DB.Table('career_link')

team_id = 'AMER'
season_2014 = 2014
season_2015 = 2015

# Fetch wrestlers by team/season
def fetch_wrestlers(season):
    response = season_table.scan(
        FilterExpression=Key('season').eq(season) & Key('team_id').eq(team_id)
    )
    return {w['season_wrestler_id']: w for w in response['Items']}

def fetch_links():
    response = link_table.scan()
    return {item['season_wrestler_id']: item for item in response['Items']}

def simplify_class_year(grade):
    if not grade:
        return ""
    norm = grade.upper().replace("-", "").replace(".", "").replace(" ", "")
    if "FR" in norm:
        return "FR"
    elif "SO" in norm:
        return "SO"
    elif "JR" in norm:
        return "JR"
    elif "SR" in norm:
        return "SR"
    return norm

w2014 = fetch_wrestlers(season_2014)
w2015 = fetch_wrestlers(season_2015)
links = fetch_links()

# Group by career_id
career_map = defaultdict(lambda: {'2014': None, '2015': None})

for sid, w in w2014.items():
    link = links.get(sid)
    if link:
        career_map[link['linked_career_id']]['2014'] = w

for sid, w in w2015.items():
    link = links.get(sid)
    if link:
        career_map[link['linked_career_id']]['2015'] = w

print(f"\n📊 Career Linking Report for Team '{team_id}'\n")

for cid, record in career_map.items():
    w14 = record['2014']
    w15 = record['2015']

    name_2014 = w14['name'] if w14 else "—"
    name_2015 = w15['name'] if w15 else "—"
    year = "MATCHED" if w14 and w15 else "2015 ONLY"

    line = f"Career ID: {cid}\n  2014: {name_2014}\n  2015: {name_2015}"

    if w15 and not w14:
        grade = simplify_class_year(w15.get('class_year', ''))
        if grade not in ["FR", "RSFR"]:
            line += f"\n  ⚠️  Unexpected new wrestler (class: {w15.get('class_year', '')})"

    if cid in links:
        match_info = links.get(w15['season_wrestler_id'], {})
        line += f"\n  Match Type: {match_info.get('match_type', '?')}, Confidence: {match_info.get('confidence_score', '?')}"

    print(line + "\n")
