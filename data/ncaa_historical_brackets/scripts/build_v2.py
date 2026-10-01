#!/usr/bin/env python3
"""Build schema-2.0 files (v2/NCAAyyyy.json) from the parser outputs.
  bracket years : json/NCAAyyyy.json (parser detail) + out/NCAAyyyy.json (house rows)
  other years   : out/NCAAyyyy.json (bad points / summary only)
Usage: python build_v2.py            (all years found in out/)
See SPEC.md for the meaning of every field."""
import json, glob, os, re, sys

SCHEMA = {'name': 'ncaa-wrestling-bracket', 'version': '2.0', 'spec': 'SPEC.md',
          'read_me_first': 'model.bracket_model says which rebuild procedure in SPEC.md applies to this file.'}

MODEL = {
    'bergman': dict(championship='single_elimination', consolation='bergman_list', years='1928-1940',
                    description='Single-elimination championship bracket. 2nd and 3rd are decided afterwards by '
                                'Bergman wrestle-backs: only wrestlers who lost to the champion may wrestle for '
                                '2nd (earliest loser first, rounds WB2_*), the survivor meets the finals loser in '
                                'the "2nd" bout; then the loser of that bout meets anyone who lost to the 2nd-place '
                                'winner for 3rd (rounds WB3_*, "3rd"). A place can be awarded with no bout '
                                '(method "automatic"). There is no drawn consolation sheet.'),
    'wrestleback_finalists': dict(championship='single_elimination', consolation='drawn_bracket', years='1941-1971',
                                  description='Single-elimination championship bracket plus a drawn consolation '
                                              'bracket (consolation_sheet). Only wrestlers who lost to one of the two '
                                              'finalists enter it. The finals loser is 2nd.'),
    'wrestleback_semifinalists': dict(championship='single_elimination', consolation='drawn_bracket', years='1972-1985',
                                      description='As wrestleback_finalists, but wrestlers who lost to any of the four '
                                                  'semifinalists enter the consolation bracket.'),
    'wrestleback_quarterfinalists': dict(championship='single_elimination', consolation='drawn_bracket', years='1986-1995',
                                         description='As wrestleback_finalists, but wrestlers who lost to any of the '
                                                     'eight quarterfinalists enter the consolation bracket.'),
    'wrestleback_all': dict(championship='single_elimination', consolation='drawn_bracket', years='1996-',
                            description='Full double elimination to 8th: every championship loser except the finals '
                                        'loser enters the consolation bracket.'),
    'bad_points': dict(championship='bad_point_rounds', consolation='none', years='1936, 1948',
                       description='Olympic-style elimination with no bracket: new pairings every round, each bout '
                                   'charges both wrestlers bad points, wrestlers drop out as points accumulate. '
                                   'Rebuild as a list of rounds; placements come from the summary page.'),
    'summary_only': dict(championship='not_available', consolation='not_available', years='1934, 1938, 2015',
                         description='The source has only the summary page (place winners, team scores); no bouts.'),
}

ROUND_CODES = {
    'PIG': 'championship pigtail (play-in) bout; the winner holds the draw line given in entrants',
'R32': 'championship first round of a 32-line draw',
    'R16': 'championship round of 16 lines', 'QF': 'championship quarterfinal', 'SF': 'championship semifinal',
    'Final': 'championship final (winner 1st, loser 2nd in all drawn-consolation models)',
    'WB2_R16': 'Bergman wrestle-back for 2nd, first stage', 'WB2_QF': 'Bergman wrestle-back for 2nd',
    'WB2_SF': 'Bergman wrestle-back for 2nd, last stage before the 2nd-place bout',
    '2nd': 'Bergman 2nd-place bout (wrestle-back survivor vs finals loser); winner is 2nd',
    'WB3_R16': 'Bergman wrestle-back for 3rd', 'WB3_QF': 'Bergman wrestle-back for 3rd',
    'WB3_SF': 'Bergman wrestle-back for 3rd',
    'C_PIG': 'consolation pigtail bout (winner enters the consolation sheet)',
    'C_R1': 'consolation round in sheet column 2', 'C_R2': 'next consolation round', 'C_R3': 'next consolation round',
    'C_R4': 'next consolation round', 'C_QF': 'second-to-last consolation round',
    'C_SF': 'last consolation round; its winners meet for 3rd',
    '3rd': 'bout for 3rd place (winner 3rd, loser 4th)', '5th': 'bout for 5th place (winner 5th, loser 6th)',
    '7th': 'bout for 7th place (winner 7th, loser 8th)',
}
RESULT_CODES = {
    'Fall': 'pin; score = time of fall (m:ss)', 'Dec': 'decision; score = points, when printed',
    'TA': 'time-advantage decision (riding-time era); score = net advantage m:ss',
    'TF': 'technical fall; score = points (the fall-style time, if printed, is in result_raw)',
    'MFF': 'medical forfeit', 'Default': 'win by default (injury etc.)', 'Forfeit': 'forfeit',
    'DQ': 'disqualification', 'Unknown': 'the source prints no result for this bout',
}
SLOT_KINDS = {
    'entry': 'a wrestler enters the consolation sheet here (he lost in the championship bracket or won a C_PIG bout)',
    'bye': 'the sheet prints "Bye" in this slot', 'empty': 'blank slot (nothing printed, nobody here)',
    'bout': 'a consolation bout; wrestler = its winner, match_id = the bout',
    'advance': 'one feeder was empty/bye: the other wrestler moves on without a bout',
    'empty_result': 'both feeders empty: nobody comes out of this slot',
    'unrecorded': 'a bout took place but the sheet does not say who won',
    'unidentified': 'the sheet prints a name here that could not be matched to a wrestler',
}
CONS_ROUND = {'P2-SF': 'WB2_SF', 'P2-QF': 'WB2_QF', 'P2-R16': 'WB2_R16', 'P3-R16': 'WB3_R16', 'P2-F': '2nd',
              'P3-SF': 'WB3_SF', 'P3-QF': 'WB3_QF', 'P3-F': '3rd'}


def champ_round(r, draw):
    if r == 'F':
        return 'Final'
    if r in ('SF', 'QF', 'PIG'):
        return r
    return f'R{draw >> (int(r[1:]) - 1)}'


def house_id(w, m):
    if m['bracket'] == 'championship':
        rnd = champ_round(m['round'], w['draw_size'])
        return f"{w['weight']}-{rnd}" + ('' if rnd == 'Final' else f"-{m['bout']:02d}")
    rnd = CONS_ROUND.get(m['round'], m['round'])
    tail = m['id'].rsplit('-', 1)[-1]
    return f"{w['weight']}-{rnd}" + (f'-{tail}' if tail.isdigit() else '')


def edit(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def wkey(x):
    return int(x) if str(x).isdigit() else x


def build(year):
    house = json.load(open(f'out/NCAA{year}.json'))
    detail = json.load(open(f'json/NCAA{year}.json')) if os.path.exists(f'json/NCAA{year}.json') and \
        house['format'].get('consolation_system') else None
    fmt = house['format']
    if detail:
        cs = fmt['consolation_system']
        model = 'bergman' if cs == 'bergman' else cs.replace('wrestleback_to_', 'wrestleback_')
    else:
        model = 'bad_points' if fmt.get('system') == 'bad_points' else 'summary_only'
    tourn = {k: house.get(k) for k in ('year', 'edition', 'event', 'host', 'dates', 'team_champion',
                                       'team_champion_label', 'outstanding_wrestler', 'gorriaran_award')
             if house.get(k) is not None}
    tourn['source'] = {k: house['source'][k] for k in ('url', 'compiled_by', 'incomplete_consolations')
                       if k in house['source']}
    ts = json.load(open(f'out/team_scores/NCAA{year}_team_scores.json'))
    weights, matches = [], []
    rows_by_w = {}
    for r in house['matches']:
        rows_by_w.setdefault(r['weight'], []).append(r)
    dw = {wkey(w['weight']): w for w in detail['weights']} if detail else {}
    for hw in house['weights']:
        wt = hw['weight']
        rows = rows_by_w.get(wt, [])
        # ---- wrestler ids -------------------------------------------------
        if detail:
            d = dw[wt]
            ents = []
            for e in d['entrants']:
                ents.append({'id': e['id'], 'line': e['line'], 'seed': e.get('seed'), 'name': e['name'],
                             'team': e['school'],
                             'entered_via': 'draw' if e['line'] else 'consolation_only' if e.get('consolation_only') else 'pigtail_only'})
        else:
            ents = [{'id': f'{wt}-{k:02d}', 'line': e.get('line'), 'seed': e.get('seed'), 'name': e['name'],
                     'team': e['team'], 'entered_via': 'bad_point_rounds' if model == 'bad_points' else 'summary'}
                    for k, e in enumerate(hw['entrants'], start=1)]
        by_nt = {(e['name'], e['team']): e['id'] for e in ents}
        # place winners from a summary page who are not in any bout still need ids
        extra_disc = []
        for p in hw['placements']:
            if (p['name'], p['team']) not in by_nt:
                near = [e for e in ents if e['team'] == p['team'] and edit(e['name'].lower(), p['name'].lower()) <= 2]
                if len(near) == 1:
                    by_nt[(p['name'], p['team'])] = near[0]['id']
                    extra_disc.append(f"summary page lists place {p['place']} as \"{p['name']}\"; the bout sheets spell it "
                                      f"\"{near[0]['name']}\" ({near[0]['id']}) - same wrestler")
                    continue
                nid = f"{wt}-S{len([e for e in ents if e['entered_via'] == 'summary']) + 1:02d}"
                ents.append({'id': nid, 'line': None, 'seed': None, 'name': p['name'], 'team': p['team'],
                             'entered_via': 'summary'})
                by_nt[(p['name'], p['team'])] = nid
        if detail:   # pigtail winners hold a line; mark who came through a pigtail
            pig_w = {(r['winner_name'], r['winner_team']) for r in rows if r['round'] == 'PIG'}
            for e in ents:
                if (e['name'], e['team']) in pig_w:
                    e['entered_via'] = 'pigtail'
        # ---- matches -------------------------------------------------------
        for r in rows:
            r2 = dict(r)
            r2['winner_id'] = by_nt.get((r['winner_name'], r['winner_team'])) if r['winner_name'] else None
            r2['loser_id'] = by_nt.get((r['loser_name'], r['loser_team'])) if r['loser_name'] else None
            if r.get('participants'):
                r2['participants'] = [dict(p, id=by_nt.get((p['name'], p['team']))) for p in r['participants']]
            matches.append(r2)
        # ---- consolation sheet --------------------------------------------
        sheet = None
        if detail and dw[wt].get('consolation_sheet'):
            d = dw[wt]
            idmap = {m['id']: house_id(d, m) for m in d['matches']}
            name = {e['id']: e for e in ents}
            slots = []
            for s in d['consolation_sheet']:
                o = {'slot': s['slot'], 'column': s['column'], 'kind': s['kind']}
                if s.get('wrestler'):
                    o['wrestler_id'] = s['wrestler']; o['name'] = name[s['wrestler']]['name']
                if s.get('bout'):
                    o['match_id'] = idmap[s['bout']]
                if 'top' in s:
                    o['top'], o['bottom'] = s.get('top'), s.get('bottom')
                o['feeds'] = s.get('feeds')
                if s.get('printed'):
                    o['printed'] = s['printed']
                slots.append(o)
            sheet = {'columns': max(s['column'] for s in slots), 'slots': slots}
        idmap_w = {m['id']: house_id(dw[wt], m) for m in dw[wt]['matches']} if detail else {}

        def fix_ids(txt):
            for old_id in sorted(idmap_w, key=len, reverse=True):
                if old_id != idmap_w[old_id] and old_id in txt:
                    txt = re.sub(re.escape(old_id) + r'(?![\w-])', idmap_w[old_id], txt)
            return txt
        bpf = hw.get('bad_points_final')
        if bpf:
            name_to_id = {e['name']: e['id'] for e in ents}
            bpf = {name_to_id.get(n, n): v for n, v in bpf.items()}
        weights.append({
            'weight': wt, 'draw_lines': hw.get('draw_lines'), 'entrant_count': len(ents), 'entrants': ents,
            'consolation_sheet': sheet,
            'placements': [{'place': p['place'], 'wrestler_id': by_nt[(p['name'], p['team'])], 'name': p['name'],
                            'team': p['team'], 'match_id': p.get('match_id'),
                            'as': p.get('as') or (None if not p.get('match_id') else 'winner'),
                            'method': p['method']} for p in hw['placements']],
            'bad_points_final': bpf,
            'notes': [fix_ids(x) for x in hw.get('notes', [])],
            'source_discrepancies': [fix_ids(x) for x in hw.get('source_discrepancies', [])] + extra_disc,
        })
        if weights[-1]['bad_points_final'] is None:
            weights[-1].pop('bad_points_final')
    m = MODEL[model]
    used_r = sorted({r['round'] for r in matches})
    used_t = sorted({re.sub(r'-OT$', '', r['result_type']) for r in matches})
    codes = {'rounds': {c: ROUND_CODES.get(c, 'bad-point round (R1, R2 ... ; R6-7 = combined rounds 6 and 7)'
                                            if re.match(r'R\d', c) and model == 'bad_points' else '?')
                        for c in used_r},
             'result_types': {c: RESULT_CODES.get(c, '?') for c in used_t},
             'result_type_suffix': {'-OT': 'overtime of any kind: OT, sudden victory (SV), tiebreaker (TB) or criteria (Cr) - see result_raw'} if any(r['result_type'].endswith('-OT') for r in matches) else {},
             }
    FROM = {'line': ('line:N', 'came from draw line N (possibly advancing on byes, which are not rows)'),
            'W': ('W:<match_id>', 'won that bout'), 'L': ('L:<match_id>', 'lost that bout'),
            'entry': ('entry', 'first bout for this wrestler (pigtail or bad-point round)')}
    used_f = {str(x).split(':')[0] for r in matches for x in (r.get('winner_from'), r.get('loser_from')) if x}
    used_f |= {str(p['from']).split(':')[0] for r in matches for p in r.get('participants') or [] if p.get('from')}
    if matches:
        codes['from'] = {FROM[k][0]: FROM[k][1] for k in ('line', 'W', 'L', 'entry') if k in used_f}
    kinds = {s['kind'] for w in weights if w['consolation_sheet'] for s in w['consolation_sheet']['slots']}
    if kinds:
        codes['slot_kinds'] = {k: v for k, v in SLOT_KINDS.items() if k in kinds}
    if not codes['result_type_suffix']:
        codes.pop('result_type_suffix')
    for c, v in codes['rounds'].items():
        if v == '?':
            print(f'warning {year}: no description for round {c}', file=sys.stderr)
    out = {'schema': SCHEMA, 'tournament': tourn,
           'model': {'bracket_model': model, 'championship': m['championship'], 'consolation': m['consolation'],
                     'model_years': m['years'],
                     'placements_awarded': max((p['place'] for w in weights for p in w['placements']), default=0),
                     'bout_order_known': False, 'description': m['description']},
           'codes': codes,
           'team_scores': {'official': ts['official'], 'scope': ts['scope'], 'scores': ts['scores'], 'notes': ts['notes']},
           'weights': weights, 'matches': matches}
    return out


if __name__ == '__main__':
    os.makedirs('v2', exist_ok=True)
    years = sorted(int(re.search(r'(\d{4})', f).group(1)) for f in glob.glob('out/NCAA[0-9][0-9][0-9][0-9].json'))
    for y in years:
        json.dump(build(y), open(f'v2/NCAA{y}.json', 'w'), indent=1, ensure_ascii=False)
    print(len(years), 'files written to v2/')
