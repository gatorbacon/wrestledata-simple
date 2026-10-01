#!/usr/bin/env python3
"""Compare a parsed year (out/NCAAyyyy.json) against an independent match list in the
same house format. Usage: python compare.py theirs.json out/NCAA2013.json [report.md]"""
import json, re, sys
from collections import defaultdict, Counter

theirs = json.load(open(sys.argv[1]))
mine = json.load(open(sys.argv[2]))['matches']
rep_path = sys.argv[3] if len(sys.argv) > 3 else None


def norm(s):
    w = re.sub(r'[^a-z ]', '', (s or '').lower().replace('-', ' ')).split()
    return [x for x in w if x not in ('jr', 'sr', 'ii', 'iii', 'iv')] or w


def edit(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def people(rows):
    out = defaultdict(dict)   # weight -> name -> (team, seed)
    for r in rows:
        for s in ('winner', 'loser'):
            if r.get(f'{s}_name'):
                out[r['weight']][r[f'{s}_name']] = (r.get(f'{s}_team'), r.get(f'{s}_seed'))
    return out


P_t, P_m = people(theirs), people(mine)
alias, name_notes = {}, []           # (weight, their name) -> my name
for wt in P_t:
    mine_names = list(P_m.get(wt, {}))
    for tn in P_t[wt]:
        if tn in P_m.get(wt, {}):
            alias[(wt, tn)] = tn; continue
        tt = norm(tn)
        best = None
        for mn in mine_names:
            mm = norm(mn)
            if not tt or not mm:
                continue
            same_last = tt[-1] == mm[-1] or edit(tt[-1], mm[-1]) <= 2
            first_ok = tt[0][0] == mm[0][0] or tt[0].startswith(mm[0][:3]) or mm[0].startswith(tt[0][:3])
            score = (0 if tt[-1] == mm[-1] else 1) + (0 if tt[0] == mm[0] else 1)
            if same_last and first_ok and (best is None or score < best[0]):
                best = (score, mn)
        if not best:   # different first name: accept a unique surname (+ same school initial) at this weight
            same = [mn for mn in mine_names if norm(mn) and tt and norm(mn)[-1] == tt[-1]]
            if len(same) == 1:
                best = (9, same[0])
        if best:
            alias[(wt, tn)] = best[1]
            name_notes.append((wt, tn, best[1]))

fam = lambda t: {'Dec': 'D', 'MD': 'D', 'TF': 'D', 'SV-1': 'D', 'SV-2': 'D', 'SV-3': 'D', 'TB-1': 'D', 'TB-2': 'D',
                 'TB-3': 'D', 'Dec-OT': 'D', 'Fall': 'F', 'Fall-OT': 'F', 'Inj.': 'X', 'Default': 'X', 'Forfeit': 'X',
                 'MFF': 'X', 'DQ': 'Q', 'Unknown': '?'}.get(t, t)


def pts(s):
    m = re.findall(r'\d+-\d+', s or '')
    return m[-1] if m else None


def tm(s):
    m = re.search(r'\d+:\d\d', s or '')
    return m.group(0) if m else None


mk = defaultdict(list)     # rematches: same pair can meet twice (e.g. R16 and 5th)
for r in mine:
    mk[(r['weight'], r['winner_name'], r['loser_name'])].append(r)


def take(key, rnd):
    lst = [x for x in mk.get(key, []) if id(x) not in matched]
    if not lst:
        return None
    return next((x for x in lst if x['round'] == rnd), lst[0])
stats = Counter()
issues = defaultdict(list)
matched = set()
for r in theirs:
    wt = r['weight']
    w, l = alias.get((wt, r['winner_name'])), alias.get((wt, r['loser_name']))
    m = take((wt, w, l), r['round'])
    if not m:
        rev = take((wt, l, w), r['round'])
        if rev:
            issues['winner reversed'].append(f"{wt} {r['round']}: yours {r['winner_name']} over {r['loser_name']}; sheet {rev['winner_name']} over {rev['loser_name']} ({rev['result_raw']})")
            matched.add(id(rev)); stats['reversed'] += 1
        else:
            issues['bout only in your file'].append(f"{wt} {r['round']}: {r['winner_name']} over {r['loser_name']} {r['score']}")
            stats['missing'] += 1
        continue
    matched.add(id(m)); stats['matched'] += 1
    if m['round'] != r['round']:
        issues['round differs'].append(f"{wt} {r['winner_name']} over {r['loser_name']}: yours {r['round']}, sheet {m['round']}")
    else:
        stats['round ok'] += 1
    ft, fm = fam(r['result_type']), fam(m['result_type'])
    if ft != fm and fm != '?':
        issues['result type differs'].append(f"{wt} {r['round']} {r['winner_name']} over {r['loser_name']}: yours {r['result_type']} {r['score']}, sheet {m['result_raw']}")
    elif fm == '?':
        stats['sheet had no result'] += 1
    else:
        stats['type ok'] += 1
    if ft == 'D' and fm == 'D':
        a, b = pts(r['score']), pts(m['result_raw'])
        if a and b and a != b:
            issues['score differs'].append(f"{wt} {r['round']} {r['winner_name']} over {r['loser_name']}: yours {r['result_type']} {r['score']}, sheet {m['result_raw']}")
        elif a and b:
            stats['score ok'] += 1
    if ft == 'F' and fm == 'F':
        a, b = tm(r['score']), tm(m['result_raw'])
        if a and b and a != b:
            issues['fall time differs'].append(f"{wt} {r['round']} {r['winner_name']} over {r['loser_name']}: yours {r['score']}, sheet {m['result_raw']}")
        elif a and b:
            stats['score ok'] += 1
    for side in ('winner', 'loser'):
        ms, ts = m.get(f'{side}_seed'), r.get(f'{side}_seed')
        if ms is not None:
            if ms != ts:
                issues['seed differs'].append(f"{wt} {r[f'{side}_name']}: yours {ts}, sheet {ms}")
            else:
                stats['seed ok'] += 1
extra = [m for m in mine if id(m) not in matched]
for m in extra:
    issues['bout only on the sheet'].append(f"{m['weight']} {m['round']}: {m['winner_name']} over {m['loser_name']} {m['result_raw']}")

lines = [f"# Comparison: {sys.argv[2]} vs {sys.argv[1]}", '',
         f"- bouts: yours {len(theirs)}, sheet {len(mine)}; matched {stats['matched']}, winner reversed {stats['reversed']}, "
         f"only yours {stats['missing']}, only sheet {len(extra)}",
         f"- same round: {stats['round ok']} / {stats['matched']}",
         f"- same result type (Dec/MD/TF/SV/TB all count as decision): {stats['type ok']}; sheet printed no result: {stats['sheet had no result']}",
         f"- same score or fall time: {stats['score ok']}",
         f"- seeds agreeing where the sheet prints one: {stats['seed ok']}",
         f"- names matched with a spelling/short-form difference: {len(name_notes)}", '']
for k, v in issues.items():
    if k == 'seed differs':
        v = sorted(set(v))
    lines.append(f"## {k} ({len(v)})")
    lines += [f"- {x}" for x in v]
    lines.append('')
lines.append('## name differences (yours -> sheet)')
lines += [f"- {w}: {a} -> {b}" for w, a, b in name_notes]
txt = '\n'.join(lines)
print(txt if not rep_path else txt[:4000])
if rep_path:
    open(rep_path, 'w').write(txt)
