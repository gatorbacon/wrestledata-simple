#!/usr/bin/env python3
"""One team-score file per year (team_scores/NCAAyyyy_team_scores.json) + team_scores_all.csv,
taken from the 'Top Ten Team Scores' table on each PDF's summary page, cross-checked against the
champions found in the brackets."""
import json, glob, re, csv, os
from collections import Counter

os.makedirs('out/team_scores', exist_ok=True)
norm = lambda s: re.sub(r'[^a-z]', '', (s or '').lower().replace('university', '').replace('state', 'st'))
rows_all = []
for f in sorted(glob.glob('out/NCAA[0-9][0-9][0-9][0-9].json')):
    d = json.load(open(f)); y = d['year']
    ts = d.get('team_scores') or []
    ranks = Counter(t['rank'] for t in ts)
    champs = Counter(norm(p['team']) for w in d['weights'] for p in w['placements'] if p['place'] == 1)
    notes = []
    if not ts:
        notes.append('No team scores printed on the summary page'
                     + (' (team scoring was not kept in 1928)' if y == 1928 else '')
                     + (f" - {d.get('team_champion_label')}: {d.get('team_champion')}" if y != 1928 else ''))
    elif not d.get('team_scores_official', True):
        notes.append('Summary page labels these as unofficial team scores')
    scores = []
    for t in ts:
        c = champs.get(norm(t['team']), 0)
        if c != t['champions']:
            notes.append(f"{t['team']}: table shows {t['champions']} individual champion(s) but the place winners include {c}")
        scores.append({'rank': t['rank'], 'tied': ranks[t['rank']] > 1, 'team': t['team'],
                       'points': t['points'], 'champions': t['champions']})
        rows_all.append({'year': y, 'rank': t['rank'], 'tied': ranks[t['rank']] > 1, 'team': t['team'],
                         'points': t['points'], 'champions': t['champions'],
                         'official': d.get('team_scores_official', True)})
    out = {'year': y, 'event': d.get('event'), 'edition': d.get('edition'), 'host': d.get('host'),
           'dates': d.get('dates'), 'team_champion': d.get('team_champion'),
           'team_champion_label': d.get('team_champion_label'),
           'team_scoring': bool(ts), 'official': d.get('team_scores_official', True) if ts else None,
           'scope': 'Top ten as printed on the summary page (more than ten rows when teams tie)',
           'source': d['source']['url'], 'scores': scores, 'notes': notes,
           'fields': {'rank': 'place as printed; tied teams share a rank', 'points': 'team points',
                      'champions': "individual champions for that team (the '(n)' in the table)"}}
    json.dump(out, open(f'out/team_scores/NCAA{y}_team_scores.json', 'w'), indent=1, ensure_ascii=False)
with open('out/team_scores/team_scores_all.csv', 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=['year', 'rank', 'tied', 'team', 'points', 'champions', 'official'])
    w.writeheader(); w.writerows(rows_all)
print(len(glob.glob('out/team_scores/*.json')), 'files,', len(rows_all), 'rows')
