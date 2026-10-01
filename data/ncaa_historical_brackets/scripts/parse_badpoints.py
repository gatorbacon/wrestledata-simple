#!/usr/bin/env python3
"""1936-style 'bad points' (Olympic elimination) sheets, and summary-only years
(1934, 1938), straight to house format.

Bad-points layout: per weight, blocks headed 'Round N:' / 'Rounds 6 & 7:' in two
page columns; each bout is two lines 'Name - School (p)', the winner's line carries
'Won <result>'.  (p) = bad points charged for that bout (0 fall/forfeit win,
1 decision win, 2-3 loss). Wrestlers drop out after too many bad points, so there
is no bracket: each bout's sources are simply the previous bout of each wrestler.

Usage: python parse_badpoints.py raw/NCAA1936.txt meta/_base.json > out/NCAA1936.json
"""
import json, re, sys
from parse_ws import load_pages, build_meta, parse_summary, parse_result, HEADER_RX

RT = {'FALL': 'Fall', 'DEC': 'Dec', 'TF': 'TF', 'TA': 'TA', 'MFF': 'MFF', 'DEF': 'Default',
      'FF': 'Forfeit', 'DQ': 'DQ', 'UNKNOWN': 'Unknown'}
ENTRY = re.compile(r'^(.*?) - (.*?) \((\d+)\)$')


def round_code(h):
    nums = re.findall(r'\d+', h)
    return 'R' + '-'.join(nums)


def parse_page(items, year):
    items = [i for i in items if not HEADER_RX.match(i['s'])]
    lab = next(i for i in items if re.match(r'^\S+ Weight Class$', i['s']))
    wt = lab['s'].split()[0]
    heads = [i for i in items if re.match(r'^Rounds? [\d &]+:$', i['s'])]
    colx = sorted({h['x'] for h in heads})
    bouts = []
    for cx in colx:
        hs = sorted([h for h in heads if h['x'] == cx], key=lambda h: -h['y'])
        for hi, h in enumerate(hs):
            lo = hs[hi + 1]['y'] if hi + 1 < len(hs) else -1
            ent = sorted([i for i in items if i['x'] == cx and lo < i['y'] < h['y'] and ENTRY.match(i['s'])],
                         key=lambda i: -i['y'])
            for a, b in zip(ent[0::2], ent[1::2]):
                won = {e['y']: next((i['s'] for i in items if i['x'] > cx + 100 and abs(i['y'] - e['y']) <= 2
                                     and i['s'].startswith('Won')), None) for e in (a, b)}
                w, l = (a, b) if won[a['y']] else (b, a)
                bouts.append((h['s'], cx, h['y'], w, l, won[w['y']]))
    # order: by round number, then page position
    bouts.sort(key=lambda t: (int(re.findall(r'\d+', t[0])[0]), -t[3]['y']))
    rows, last, counters = [], {}, {}
    for seq, (hd, cx, hy, w, l, won) in enumerate(bouts, start=1):
        rc = round_code(hd)
        counters[rc] = counters.get(rc, 0) + 1
        mid = f'{wt}-{rc}-{counters[rc]:02d}'
        wn, ws, wp = ENTRY.match(w['s']).groups()
        ln, ls, lp = ENTRY.match(l['s']).groups()
        raw = (won or '').replace('Won', '', 1).strip()
        r = parse_result(raw) or {}
        rt = RT.get(r.get('type'), 'Unknown') + ('-OT' if r.get('ot') else '')
        row = {'year': year, 'weight': int(wt) if wt.isdigit() else wt, 'round': rc, 'bracket': 'badpoints',
               'winner_seed': None, 'winner_name': wn, 'winner_team': ws,
               'loser_seed': None, 'loser_name': ln, 'loser_team': ls,
               'result_type': rt, 'score': r.get('time') or r.get('points'),
               'match_id': mid, 'seq': seq,
               'winner_from': last.get(wn, 'entry'), 'loser_from': last.get(ln, 'entry'),
               'winner_to': None, 'loser_to': None, 'result_raw': raw or None,
               'winner_bad_points': int(wp), 'loser_bad_points': int(lp)}
        for nm, side in ((wn, 'winner'), (ln, 'loser')):
            prev = last.get(nm)
            if prev and prev != 'entry':
                pm = next(x for x in rows if x['match_id'] == prev[2:])
                pm['winner_to' if prev[0] == 'W' else 'loser_to'] = mid
        last[wn], last[ln] = f'W:{mid}', f'L:{mid}'
        rows.append(row)
    # running bad-point totals, for the record
    tot = {}
    for r in rows:
        for side in ('winner', 'loser'):
            tot[r[f'{side}_name']] = tot.get(r[f'{side}_name'], 0) + r[f'{side}_bad_points']
            r[f'{side}_bad_points_total'] = tot[r[f'{side}_name']]
    teams = {}
    for r in rows:
        teams[r['winner_name']] = r['winner_team']; teams[r['loser_name']] = r['loser_team']
    return wt, rows, teams, tot


def placements_from_summary(summary, wt):
    out = []
    for place, s in sorted(summary.get(wt, {}).items()):
        # ties are printed 'A - X & B - Y'
        parts = re.split(r' & (?=[^&]+ - )', f"{s['name']} - {s['school']}")
        for p in parts:
            nm, _, tm = p.partition(' - ')
            out.append({'place': place, 'name': nm.strip(), 'team': tm.strip(), 'match_id': None,
                        'method': 'summary_only' if len(parts) == 1 else 'tie',
                        'summary_result_raw': s['result_raw']})
    return out


def main(raw_path, base_path):
    pages = load_pages(raw_path)
    meta = build_meta(pages[0], json.load(open(base_path)))
    yr = meta['year']
    src = dict(meta['source']); src['url'] = src.pop('url_pattern').format(year=yr)
    src['incomplete_consolations'] = yr in src.pop('incomplete_consolation_years')
    meta['source'] = src
    meta['schema_version'] = 'hist-1.1'
    summary = parse_summary(pages[0])
    weights, matches = [], []
    has_bouts = len(pages) > 1
    if has_bouts:
        meta['format'] = {'system': 'bad_points',
                          'description': 'Olympic-style elimination (used in 1936, an Olympic year): every bout charges '
                                         'each wrestler bad points, printed in parentheses after his name '
                                         '(as printed: 0 = win by fall/forfeit, 1 = win by decision, 2 = close '
                                         'decision loss, 3 = loss). New pairings each round; wrestlers drop out as '
                                         'bad points pile up and the survivors are ranked 1-4. No bracket; '
                                         'placements are taken from the summary page.',
                          'bout_order_known': False, 'placements_awarded': 4}
        for items in pages[1:]:
            wt, rows, teams, tot = parse_page(items, yr)
            matches += rows
            pl = placements_from_summary(summary, wt)
            disc = [f"{wt} place {p['place']}: summary name '{p['name']}' does not appear in the bout sheets (spelling?)"
                    for p in pl if p['name'] not in teams]
            weights.append({'weight': int(wt) if wt.isdigit() else wt, 'draw_lines': None,
                            'entrant_count': len(teams),
                            'entrants': [{'line': None, 'seed': None, 'name': n, 'team': t} for n, t in teams.items()],
                            'bad_points_final': tot, 'placements': pl, 'notes': [], 'source_discrepancies': disc})
    else:
        meta['format'] = {'system': 'unknown', 'description': 'Source has the summary page only (champions and '
                          'place winners); no brackets or bout-by-bout results.', 'bout_order_known': False}
        for wt in summary:
            weights.append({'weight': int(wt) if wt.isdigit() else wt, 'draw_lines': None, 'entrant_count': None,
                            'entrants': [], 'placements': placements_from_summary(summary, wt),
                            'notes': ['summary page only; brackets not available in source'],
                            'source_discrepancies': []})
    for k in ('id_conventions', 'consolation_rules'):
        meta.pop(k, None)
    meta['field_notes'] = {
        'core': 'year..score match the 2013-2026 files exactly',
        'bracket': "'badpoints' for bad-point rounds (no champ/consol split)",
        'winner_from/loser_from': "'entry' = first bout, W:/L:<id> = previous bout",
        'winner_bad_points/loser_bad_points': 'bad points charged in this bout (as printed); *_total = running total'}
    json.dump({**meta, 'weights': weights, 'matches': matches}, sys.stdout, indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main(*sys.argv[1:3])
