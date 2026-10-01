#!/usr/bin/env python3
"""Reference renderer for schema-2.0 bracket files (see SPEC.md). Uses nothing but the JSON file.

  python render_bracket.py v2/NCAA1979.json 118            # draw one weight as text
  python render_bracket.py v2/NCAA1979.json 118 --view     # canonical view (JSON) used for testing
  python render_bracket.py v2/NCAA1979.json --all --view   # every weight
"""
import json, sys


# ---------------------------------------------------------------- helpers
def load(path):
    return json.load(open(path))


def weight_of(d, wt):
    for w in d['weights']:
        if str(w['weight']) == str(wt):
            return w
    raise SystemExit(f'weight {wt} not in file')


def rows_of(d, w):
    return [m for m in d['matches'] if str(m['weight']) == str(w['weight'])]


# ---------------------------------------------------------------- championship (SPEC 4)
def championship_columns(d, w):
    """Column 0 = draw lines (wrestler id or None). Column k+1 pairs column k two by two:
    both present -> the championship row between them gives the winner; one present -> he advances (bye);
    none -> None."""
    rows = [m for m in rows_of(d, w) if m['bracket'] == 'champ' and m['round'] != 'PIG']
    pair = {frozenset((m['winner_id'], m['loser_id'])): m for m in rows}
    col = [None] * w['draw_lines']
    for e in w['entrants']:
        if e['line']:
            col[e['line'] - 1] = e['id']
    cols = [col]
    while len(col) > 1:
        nxt = []
        for a, b in zip(col[0::2], col[1::2]):
            if a and b:
                m = pair.get(frozenset((a, b)))
                nxt.append(m['winner_id'] if m else None)
            else:
                nxt.append(a or b)
        cols.append(nxt)
        col = nxt
    return cols


def pigtails(d, w, kind='PIG'):
    return [[m['winner_id'], m['loser_id']] for m in rows_of(d, w) if m['round'] == kind]


# ---------------------------------------------------------------- consolation sheet (SPEC 5)
def sheet_columns(w):
    """Every slot of the drawn consolation sheet, column by column, top to bottom.
    Order is fixed by the tree: start at the roots (slots that feed nothing) in slot order, and walk
    top feeder before bottom feeder."""
    sh = w['consolation_sheet']
    slots = {s['slot']: s for s in sh['slots']}
    order, seen = [], set()

    def walk(sid):
        if sid is None or sid in seen:
            return
        seen.add(sid)
        s = slots[sid]
        walk(s.get('top'))
        order.append(sid)
        walk(s.get('bottom'))

    roots = sorted([s for s in sh['slots'] if not s.get('feeds')], key=lambda s: (s['column'], int(s['slot'].split('.')[1])))
    for r in roots:
        walk(r['slot'])
    cols = [[] for _ in range(sh['columns'])]
    for sid in order:
        s = slots[sid]
        cols[s['column'] - 1].append(s.get('wrestler_id') if s['kind'] in ('entry', 'bout', 'advance') else None)
    return cols, order, slots


# ---------------------------------------------------------------- canonical view (used by the cold test)
def view(d, wt):
    w = weight_of(d, wt)
    model = d['model']['bracket_model']
    v = {'year': d['tournament']['year'], 'weight': w['weight'], 'bracket_model': model,
         'placements': sorted([[p['place'], p['wrestler_id']] for p in w['placements']])}
    if model == 'summary_only':
        return v
    if model == 'bad_points':
        rounds = {}
        for m in rows_of(d, w):
            rounds.setdefault(m['round'], []).append([m['winner_id'], m['loser_id']])
        v['rounds'] = rounds
        return v
    v['championship_columns'] = championship_columns(d, w)
    v['pigtails'] = pigtails(d, w)
    if model == 'bergman':
        # every wrestle-back / place bout in flow order
        v['consolation_bouts'] = [[m['round'], m['winner_id'], m['loser_id']] for m in rows_of(d, w)
                                  if m['bracket'] == 'consol']
    else:
        if w.get('consolation_sheet'):
            v['consolation_columns'] = sheet_columns(w)[0]
        v['consolation_pigtails'] = pigtails(d, w, 'C_PIG')
        v['place_bouts'] = {m['round']: [m['winner_id'], m['loser_id']] for m in rows_of(d, w)
                            if m['round'] in ('3rd', '5th', '7th')}
    return v


# ---------------------------------------------------------------- text drawing
def draw(d, wt):
    w = weight_of(d, wt)
    model = d['model']['bracket_model']
    names = {e['id']: f"{e['name']} ({e['team']})" + (f" [{e['seed']}]" if e.get('seed') else '') for e in w['entrants']}
    short = {e['id']: e['name'] for e in w['entrants']}
    rows = rows_of(d, w)
    res = {}
    for m in rows:
        res[(m['winner_id'], m['loser_id'])] = m
    out = [f"{d['tournament']['year']} NCAA — {w['weight']} — {model}", '']
    if model == 'summary_only':
        out.append('(no bouts in source)')
    elif model == 'bad_points':
        cur = None
        for m in rows:
            if m['round'] != cur:
                cur = m['round']; out.append(f'Round {cur}:')
            out.append(f"  {m['winner_name']} ({m.get('winner_bad_points')}) over {m['loser_name']} "
                       f"({m.get('loser_bad_points')})  {m['result_raw'] or ''}")
    else:
        pig = pigtails(d, w)
        if pig:
            out.append('Pigtails: ' + '; '.join(f'{short[a]} over {short[b]}' for a, b in pig))
        cols = championship_columns(d, w)
        # print as a sideways bracket: column k entry i at row (2^k)(2i+1)-1
        W = 24
        nrows = 2 * len(cols[0])
        grid = [[' ' * W for _ in cols] for _ in range(nrows)]
        for k, col in enumerate(cols):
            for i, wid in enumerate(col):
                r = (2 ** k) * (2 * i + 1) - 1
                label = (names if k == 0 else short).get(wid, '—' if k else 'Bye') if wid else ('Bye' if k == 0 else '—')
                if k and wid:
                    prev = cols[k - 1]
                    a, b = prev[2 * i], prev[2 * i + 1]
                    if a and b:
                        m = res.get((wid, b if wid == a else a))
                        if m and m['result_raw']:
                            label += f" {m['result_raw']}"
                grid[r][k] = label[:W - 1].ljust(W)
        out.append('Championship:')
        out += ['  ' + ''.join(r).rstrip() for r in grid if ''.join(r).strip()]
        if model == 'bergman':
            out.append('Wrestle-backs / place bouts:')
            for m in rows:
                if m['bracket'] == 'consol':
                    out.append(f"  {m['round']:<7} {m['winner_name']} over {m['loser_name']}  {m['result_raw'] or ''}")
        elif w.get('consolation_sheet'):
            cp = pigtails(d, w, 'C_PIG')
            if cp:
                out.append('Consolation pigtails: ' + '; '.join(f'{short[a]} over {short[b]}' for a, b in cp))
            out.append('Consolation sheet:')
            ccols, order, slots = sheet_columns(w)
            # rows: leaves in walk order, parents midway between their feeders
            rowpos = {}
            nxt = 0
            for sid in order:
                s = slots[sid]
                if s.get('top') is None:
                    rowpos[sid] = nxt; nxt += 2
            for c in range(1, w['consolation_sheet']['columns'] + 1):
                for sid in order:
                    s = slots[sid]
                    if s['column'] == c and s.get('top') is not None:
                        rowpos[sid] = (rowpos[s['top']] + rowpos[s['bottom']]) // 2
            grid = [[' ' * W for _ in range(w['consolation_sheet']['columns'])] for _ in range(nxt + 1)]
            for sid, r in rowpos.items():
                s = slots[sid]
                txt = {'bye': 'Bye', 'empty': '', 'empty_result': '', 'unrecorded': '(not recorded)',
                       'unidentified': s.get('printed', '?')}.get(s['kind'])
                if txt is None:
                    txt = short.get(s.get('wrestler_id'), '?')
                    mid = s.get('match_id')
                    m = next((x for x in rows if x['match_id'] == mid), None) if mid else None
                    if m and m['result_raw']:
                        txt += f" {m['result_raw']}"
                grid[r][s['column'] - 1] = txt[:W - 1].ljust(W)
            out += ['  ' + ''.join(r).rstrip() for r in grid if ''.join(r).strip()]
            for rnd in ('3rd', '5th', '7th'):
                m = next((x for x in rows if x['round'] == rnd), None)
                if m:
                    out.append(f"  {rnd}: {m['winner_name']} over {m['loser_name']} {m['result_raw'] or ''}")
    out.append('Placements: ' + ', '.join(f"{p['place']}. {p['name']}" + ('' if p['method'] == 'bout' else f" ({p['method']})")
                                          for p in sorted(w['placements'], key=lambda p: p['place'])))
    return '\n'.join(out)


if __name__ == '__main__':
    d = load(sys.argv[1])
    wts = [w['weight'] for w in d['weights']] if '--all' in sys.argv else [sys.argv[2]]
    if '--view' in sys.argv:
        print(json.dumps([view(d, w) for w in wts] if '--all' in sys.argv else view(d, wts[0])))
    else:
        print('\n\n'.join(draw(d, w) for w in wts))
