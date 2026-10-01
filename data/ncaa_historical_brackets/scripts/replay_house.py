#!/usr/bin/env python3
"""Rebuild every bracket from a house-format file alone (entrants + matches), including
the bye slots, then check every from/to link.  Prints the drawn bracket per weight.
Usage: python replay_house.py out/NCAA1928.json [weight]"""
import json, sys

d = json.load(open(sys.argv[1]))
only = sys.argv[2] if len(sys.argv) > 2 else None
errs = 0


def err(msg):
    global errs
    errs += 1
    print('  !!', msg)


for w in d['weights']:
    if only and str(w['weight']) != only:
        continue
    wt = w['weight']
    rows = sorted([m for m in d['matches'] if m['weight'] == wt], key=lambda m: m['seq'])
    byid = {m['match_id']: m for m in rows}
    who = {e['line']: (e['name'], e['team']) for e in w['entrants']}
    K = lambda m, side: (m[f'{side}_name'], m[f'{side}_team'])      # wrestler key = name + team

    # 1) every source link must point at a bout the wrestler actually won/lost, or his draw line
    def people(m):
        if m.get('participants'):
            return [(p['name'], p['team']) for p in m['participants']]
        return [K(m, 'winner'), K(m, 'loser')]
    for m in rows:
        if m.get('participants'):            # bout whose winner is unknown: check where both came from
            for p in m['participants']:
                kind, ref = p['from'].split(':', 1)
                src = byid.get(ref) if kind != 'line' else None
                ok = (who.get(int(ref)) == (p['name'], p['team'])) if kind == 'line' else \
                     (src and K(src, 'winner' if kind == 'W' else 'loser') == (p['name'], p['team']))
                if not ok:
                    err(f"{m['match_id']}: participant {p['name']} from {p['from']} does not check out")
            continue
        for side in ('winner', 'loser'):
            nm, f = K(m, side), m[f'{side}_from']
            if f == 'entry':
                ok = not any(x['seq'] < m['seq'] and nm in (K(x, 'winner'), K(x, 'loser')) for x in rows)
                if not ok: err(f"{m['match_id']}: {nm} marked as first bout but wrestled earlier")
                continue
            kind, ref = f.split(':', 1)
            if kind == 'line':
                ok = who.get(int(ref)) == nm
            else:
                src = byid.get(ref)
                ok = src and src['seq'] < m['seq'] and K(src, 'winner' if kind == 'W' else 'loser') == nm
            if not ok:
                err(f"{m['match_id']}: {side} {nm} from {f} does not check out")
            to = m[f'{side}_to']
            if to and nm not in people(byid[to]):
                err(f"{m['match_id']}: {side}_to {to} does not contain {nm}")

    if not w.get('draw_lines'):
        print(f"\n=== {d['year']} {wt}: {d['format'].get('system')} — {len(rows)} bouts ===")
        for m in rows:
            print(f"  {m['match_id']:<12} {m['winner_name']} over {m['loser_name']}  {m['result_raw'] or ''}")
        for p in w['placements']:
            print(f"  {p['place']}. {p['name']} ({p['team']}) [{p['method']}]")
        continue
    # 2) redraw the championship bracket column by column from the draw lines
    n = w['draw_lines']
    col = [who.get(i) for i in range(1, n + 1)]
    cols = [col]
    champ = [m for m in rows if m['bracket'] == 'champ']
    while len(col) > 1:
        nxt = []
        for a, b in zip(col[0::2], col[1::2]):
            if a and b:
                m = next((m for m in champ if {K(m, 'winner'), K(m, 'loser')} == {a, b}), None)
                if not m:
                    err(f'no bout found for {a} vs {b}')
                nxt.append(K(m, 'winner') if m else None)
            else:
                nxt.append(a or b)
        col = nxt
        cols.append(col)
    used = sum(1 for c in cols[1:] for i in range(len(c)))
    print(f"\n=== {d['year']} {wt}: {w['entrant_count']} entrants on {n} lines ===")
    for r, c in enumerate(cols):
        print(f"  col{r}: " + ' | '.join(x[0] if x else '-' for x in c))
    for p in w['placements']:
        m = byid.get(p['match_id'])
        if p['method'] == 'bout' and (not m or K(m, p.get('as') or 'winner') != (p['name'], p['team'])):
            err(f"place {p['place']} {p['name']} not the {p.get('as')} of {p['match_id']}")
        print(f"  {p['place']}. {p['name']} ({p['team']})" + ('' if p['method'] == 'bout' else f" [{p['method']}]"))
    if cols[-1][0] != (w['placements'][0]['name'], w['placements'][0]['team']):
        err('redrawn champion differs from placements')
print('\nerrors:', errs)
sys.exit(1 if errs else 0)
