import json

with open('matches_backup.json') as f:
    data = json.load(f)

types_found = {
    'winner_id': set(),
    'loser_id': set()
}

for item in data[:1000]:  # check first 1000 entries for speed
    types_found['winner_id'].add(type(item.get('winner_id')).__name__)
    types_found['loser_id'].add(type(item.get('loser_id')).__name__)

print("winner_id types found:", types_found['winner_id'])
print("loser_id types found:", types_found['loser_id'])