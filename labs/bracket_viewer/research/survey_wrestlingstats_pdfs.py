import subprocess,re,sys,collections,json
def run(a): return subprocess.run(a,capture_output=True,text=True).stdout
def npages(y):
    m=re.search(r'Pages:\s+(\d+)',run(['pdfinfo',f'{y}.pdf'])); return int(m.group(1)) if m else 0
def crop_count(y,pg,W):
    t=run(['pdftotext','-f',str(pg),'-l',str(pg),'-x','0','-y','40','-W',str(W),'-H','560','-layout',f'{y}.pdf','-'])
    return sum(1 for l in t.splitlines() if ',' in l and 'Compiled' not in l)
def rng(v):
    v=[x for x in v if x is not None]
    return '-' if not v else (str(min(v)) if min(v)==max(v) else f'{min(v)}-{max(v)}')
out={}
for y in range(int(sys.argv[1]),int(sys.argv[2])-1,-1):
    try: n=npages(y)
    except Exception: continue
    if n<3: continue
    W=collections.OrderedDict(); places=set(); kinds=[]
    for pg in range(2,n+1):
        t=run(['pdftotext','-f',str(pg),'-l',str(pg),'-layout',f'{y}.pdf','-'])
        m=re.search(r'([\w]+)\s+Weight Class',t); kind=None
        if m: kind='C'; w=m.group(1)
        else:
            m=re.search(r'([\w]+)\s+Consolation Bracket',t)
            if m: kind='X'; w=m.group(1)
            else:
                m=re.search(r'Pigtail Bouts for (\w+)',t) or re.search(r'Bouts for (\w+)',t)
                if m: kind='P'; w=m.group(1)
                else: kinds.append('?'); continue
        kinds.append(kind); d=W.setdefault(w,{})
        if kind=='C': d['champ']=crop_count(y,pg,190)
        if kind=='X': d['cons']=crop_count(y,pg,135)
        if kind=='P':
            cp=re.search(r'Championship Pigtail Bouts.*?(?=Consolation Pigtail|\Z)',t,re.S)
            d['pc']=len(re.findall(r' - ',cp.group(0)))//2 if cp else 0
            cc=re.search(r'Consolation Pigtail Bouts.*',t,re.S)
            d['px']=len(re.findall(r' - ',cc.group(0)))//2 if cc else 0
        for k in ('Third','Fourth','Fifth','Sixth','Seventh','Eighth'):
            if re.search(k+r' Place:',t): places.add(k)
    ws=list(W)
    g=lambda k:[d.get(k) for d in W.values()]
    ppw=''.join(kinds[:3])
    print(f"{y} pg={n} wts={ws} slots(champ)={rng(g('champ'))} slots(cons)={rng(g('cons'))} pigC={rng(g('pc'))} pigX={rng(g('px'))} places={len(places)+2 if places else 0} seq={ppw}")
