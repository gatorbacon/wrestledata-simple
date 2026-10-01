import json,glob
from collections import Counter
probs=Counter(); ex=[]; nw=0
for f in sorted(glob.glob('json/NCAA*.json')):
    d=json.load(open(f))
    for w in d['weights']:
        sh=w.get('consolation_sheet')
        if not sh: continue
        nw+=1
        slots={n['slot']:n for n in sh}
        maxc=max(x['column'] for x in sh)
        bouts=[m['id'] for m in w['matches'] if m['bracket']=='consolation' and m['round'].startswith('C_') and m['round']!='C_PIG']
        onsheet=Counter(n.get('bout') for n in sh if n.get('bout'))
        miss=[b for b in bouts if onsheet[b]!=1]
        loose=[n['slot'] for n in sh if not n.get('feeds') and n['column']!=maxc]
        res_bad=[n['slot'] for n in sh if n['kind'] not in ('entry','bye','empty','unidentified') and not (n.get('top') and n.get('bottom'))]
        fed=Counter(n.get('feeds') for n in sh if n.get('feeds'))
        over=[k for k,v in fed.items() if v!=2]
        for name,lst in (('bout not on sheet',miss),('loose slot',loose),('result w/o 2 feeders',res_bad),('slot not fed by exactly 2',over)):
            if lst: probs[name]+=1; ex.append((d['year'],w['weight'],name,[(s,slots.get(s,{}).get('kind'),slots.get(s,{}).get('printed')) for s in lst][:4] if name!='bout not on sheet' else lst[:3]))
print(nw,'weights with sheets;',dict(probs) or 'all consistent')
for e in ex[:30]: print(e)
