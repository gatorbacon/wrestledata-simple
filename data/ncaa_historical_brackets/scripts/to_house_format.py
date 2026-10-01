#!/usr/bin/env python3
"""Convert parse_ws.py output into the house format used for 2013-2026.

Every row in "matches" has exactly the 2013-2026 fields (year, weight, round,
bracket, winner_/loser_ seed/name/team, result_type, score) plus replay fields:
  match_id, seq, winner_from, loser_from, winner_to, loser_to, result_raw
from = "line:N" (draw line) | "W:<match_id>" | "L:<match_id>".  Byes are not
rows (same as 2013-2026); a wrestler who advanced on a bye simply shows
"line:N" as his source in his first real bout.
Usage: python to_house_format.py json/NCAA1928.json > out/NCAA1928.json
"""
import json, sys

RT = {'FALL': 'Fall', 'DEC': 'Dec', 'TF': 'TF', 'TA': 'TA', 'MFF': 'MFF', 'DEF': 'Default',
      'FF': 'Forfeit', 'DQ': 'DQ', 'UNKNOWN': 'Unknown'}
CONS_ROUND = {'P2-SF': 'WB2_SF', 'P2-QF': 'WB2_QF', 'P2-R16': 'WB2_R16', 'P3-R16': 'WB3_R16', 'P2-F': '2nd',
              'P3-SF': 'WB3_SF', 'P3-QF': 'WB3_QF', 'P3-F': '3rd'}

src = json.load(open(sys.argv[1]))
year = src['year']


def champ_round(r, draw):
    if r == 'F':
        return 'Final'
    if r in ('SF', 'QF', 'PIG'):
        return r
    k = int(r[1:])                       # R1, R2 ... -> R<draw>, R<draw/2> ...
    return f'R{draw >> (k - 1)}'


def new_id(mid, idmap):
    return idmap.get(mid, mid)


out_weights, out_matches = [], []
for w in src['weights']:
    wt = int(w['weight']) if w['weight'].isdigit() else w['weight']
    ent = {e['id']: e for e in w['entrants']}
    draw = w['draw_size']
    ms = [m for m in w['matches'] if m['status'] in ('contested', 'unknown_winner')]
    # new ids in house round vocabulary
    idmap = {}
    for m in w['matches']:
        if m['bracket'] == 'championship':
            rnd = champ_round(m['round'], draw)
            idmap[m['id']] = f"{w['weight']}-{rnd}" + ('' if rnd == 'Final' else f"-{m['bout']:02d}")
        else:
            rnd = CONS_ROUND.get(m['round'], m['round'])
            tail = m['id'].rsplit('-', 1)[-1]
            idmap[m['id']] = f"{w['weight']}-{rnd}" + (f'-{tail}' if tail.isdigit() else '')
    byid = {m['id']: m for m in w['matches']}

    def source(side):
        """Follow bye nodes back to the draw line or the last real bout."""
        f = side['from']
        if f == 'entry':
            return 'entry'
        while f and 'winner_of' in f and byid[f['winner_of']]['status'] == 'bye':
            b = byid[f['winner_of']]
            f = next(s['from'] for s in (b['top'], b['bottom']) if s['wrestler'])
        if not f:
            return 'entry'
        if 'line' in f and 'winner_of' not in f:
            return f"line:{f['line']}"
        if 'winner_of' in f:
            return f"W:{idmap[f['winner_of']]}"
        return f"L:{idmap[f['loser_of']]}"

    def dest(link):
        # skip over bye nodes to the next real bout
        while link and byid[link['match']]['status'] == 'bye':
            link = byid[link['match']]['winner_to']
        return idmap[link['match']] if link else None

    def side_of(m, wid):
        return m['top'] if m['top']['wrestler'] == wid else m['bottom']

    for seq, m in enumerate(ms, start=1):
        NONE = {'name': None, 'school': None, 'seed': None}
        unknown = m['status'] == 'unknown_winner'
        W, L = ent.get(m['winner'], NONE), ent.get(m['loser'], NONE)
        r = m['result'] or {}
        rtype = RT.get(r.get('type'), r.get('type')) or 'Unknown'
        if r.get('ot'):
            rtype += '-OT'
        out_matches.append({
            'year': year, 'weight': wt,
            'round': champ_round(m['round'], draw) if m['bracket'] == 'championship' else CONS_ROUND.get(m['round'], m['round']),
            'bracket': 'champ' if m['bracket'] == 'championship' else 'consol',
            'winner_seed': W.get('seed'), 'winner_name': W['name'], 'winner_team': W['school'],
            'loser_seed': L.get('seed'), 'loser_name': L['name'], 'loser_team': L['school'],
            'result_type': rtype,
            'score': (r.get('time') or r.get('points')) if r.get('type') in ('FALL', 'TA') else (r.get('points') or r.get('time')),
            'match_id': idmap[m['id']], 'seq': seq,
            'winner_from': None if unknown else source(side_of(m, m['winner'])),
            'loser_from': None if unknown else source(side_of(m, m['loser'])),
            'winner_to': dest(m['winner_to']), 'loser_to': dest(m['loser_to']),
            'result_raw': r.get('raw'),
        })
        if unknown:   # winner not recoverable from the sheet: keep both wrestlers and where they came from
            out_matches[-1]['result_type'] = 'Unknown'
            out_matches[-1]['participants'] = [
                {'name': ent[sd['wrestler']]['name'], 'team': ent[sd['wrestler']]['school'], 'from': source(sd)}
                for sd in (m['top'], m['bottom'])]
    out_weights.append({
        'weight': wt, 'draw_lines': draw, 'entrant_count': w['entrant_count'],
        'entrants': [{'line': e['line'], 'seed': e.get('seed'), 'name': e['name'], 'team': e['school']} for e in w['entrants']],
        'placements': [{'place': p['place'], 'name': ent[p['wrestler']]['name'], 'team': ent[p['wrestler']]['school'],
                        'match_id': idmap.get(p['decided_by']) if p['decided_by'] else None,
                        'method': p.get('method', 'bout'),
                        'as': (('winner' if byid[p['decided_by']]['winner'] == p['wrestler'] else 'loser')
                               if p['decided_by'] else None)} for p in w['placements']],
        'notes': w.get('notes', []), 'source_discrepancies': w['discrepancies'],
    })

meta = {k: v for k, v in src.items() if k != 'weights'}
meta['schema_version'] = 'hist-1.1'
meta['result_legend'] = {
    'Fall': 'Pin; score = time', 'Dec': "Referee's decision (no score recorded in this era)",
    'TA': 'Time-advantage decision; score = net riding-time advantage',
    'MFF': 'Medical forfeit (source: "Med FFT")', 'Default': 'Won by default (source: "WDF")',
    '-OT suffix': 'Bout went to an overtime period', 'Forfeit': 'Forfeit', 'DQ': 'Disqualification'}
if src['format'].get('consolation_system', '').startswith('wrestleback_to'):
    meta['round_legend'] = {
        'PIG': 'Championship pigtail (play-in) bout; winner takes the draw line',
        'R32/R16/QF/SF/Final': 'Championship rounds, named by the number of draw lines as in 2013-2026',
        'C_PIG': 'Consolation pigtail bout',
        'C_R1, C_R2 ...': 'Early consolation rounds, left to right on the consolation sheet; -NN = slot top to bottom',
        'C_QF': 'Second-to-last consolation round',
        'C_SF': 'Last consolation round (survivor vs a semifinal loser)',
        '3rd/5th/7th': 'Placement bouts; winner takes that place, loser the next'}
else:
    meta['round_legend'] = {
        'R16/QF/SF/Final': 'Championship rounds, named by the number of draw lines as in 2013-2026',
        'WB2_QF/WB2_SF': 'Bergman wrestle-backs for 2nd (losers to the champion, earliest loser first)',
        '2nd': 'Second-place bout (wrestle-back survivor vs finals loser)',
        'WB3_QF/WB3_SF': 'Bergman wrestle-backs for 3rd',
        '3rd': 'Third-place bout (2nd-bout loser vs anyone who lost to the 2nd-place winner)'}
meta.pop('id_conventions', None)
meta['field_notes'] = {
    'core': 'year..score match the 2013-2026 files exactly',
    'match_id': '<weight>-<round>[-<bout# top to bottom>]',
    'seq': 'logical order within the weight (round order; true bout order unknown)',
    'winner_from/loser_from': 'line:N = draw line (includes advancing on byes), W:<id> = won that bout, L:<id> = lost that bout',
    'winner_to/loser_to': 'next bout that wrestler appeared in, null if finished',
}
json.dump({**meta, 'weights': out_weights, 'matches': out_matches}, sys.stdout, indent=1, ensure_ascii=False)
