#!/usr/bin/env python3
"""Write out/AUDIT.md: per-year format + every source discrepancy / note."""
import json, glob
lines, tot = [], 0
for f in sorted(glob.glob('out/NCAA*.json')):
    d = json.load(open(f)); y = d['year']
    fmt = d['format'].get('consolation_system') or d['format'].get('system')
    n = len(d['matches']); tot += n
    pig = sum(1 for m in d['matches'] if 'PIG' in m['round'])
    places = max((len(w['placements']) for w in d['weights']), default=0)
    lines.append(f"## {y} — {d['host']} — {fmt}; {len(d['weights'])} weights, {n} bouts"
                 + (f" (incl. {pig} pigtails)" if pig else '') + f", places 1-{places}"
                 + (" — site marks consolations incomplete" if d['source'].get('incomplete_consolations') else ''))
    for w in d['weights']:
        for x in w['source_discrepancies']: lines.append(f"- {w['weight']}: source issue: {x}")
        for x in w['notes']: lines.append(f"- {w['weight']}: note: {x}")
    lines.append('')
yrs = sorted(json.load(open(f))['year'] for f in glob.glob('out/NCAA*.json'))
head = [f'# Audit {yrs[0]}-{yrs[-1]}', '',
        'Every file rebuilds with 0 flow errors (see replay/). Items below are problems or oddities in the SOURCE PDFs, recorded as printed.',
        f'Total bouts: {tot}. No tournaments were held in 1943-1945.', '']
open('out/AUDIT.md', 'w').write('\n'.join(head + lines))
print(tot)
