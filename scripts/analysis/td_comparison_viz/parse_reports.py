import re, json, glob
from pathlib import Path
HERE=Path(__file__).resolve().parent
DIR=HERE.parent.parent.parent/"data"/"analysis"
WINDOWS=["2014-2016","2017-2019","2021-2023","2024-2026"]
def num(x): return int(x.replace(",",""))
def parse(path):
    txt=path.read_text()
    lines=txt.splitlines()
    flat=" ".join(l.strip() for l in lines)
    d={}
    m=re.search(r"Seasons included: ([\d, ]+)\.",flat); d["seasons"]=[int(x) for x in m[1].replace(" ","").split(",")]
    m=re.search(r"([\d,]+) bouts with play-by-play data",flat); d["bouts"]=num(m[1])
    m=re.search(r"([\d,]+) more had none",flat) or re.search(r"\(([\d,]+) more had none",flat); d["no_pbp"]=num(m[1]) if m else None
    m=re.search(r"([\d.]+)% of bouts \(([\d,]+) of ([\d,]+)\) had a takedown differential; ([\d.]+)% \(([\d,]+)\) were tied",flat)
    d["with_diff"]=num(m[2]); d["tied"]=num(m[5])
    m=re.search(r"wrestler with MORE takedowns won ([\d,]+) of ([\d,]+) bouts \(([\d.]+)%\)",flat); d["more_td_all"]=[num(m[1]),num(m[2])]
    m=re.search(r"decided by points, that figure is ([\d,]+) of ([\d,]+) \(([\d.]+)%\)",flat); d["more_td_pts"]=[num(m[1]),num(m[2])]
    m=re.search(r"How the ([\d,]+) bouts ended: ([\d,]+) by points .*?, ([\d,]+) by fall .*?, ([\d,]+) forfeit/injury/DQ, ([\d,]+) unmatched",flat)
    d["ended"]={"points":num(m[2]),"fall":num(m[3]),"forfeit":num(m[4]),"unmatched":num(m[5])}
    m=re.search(r"Matched to an official result: ([\d,]+) of ([\d,]+)",flat); d["matched"]=num(m[1]) if m else None
    d["swapped"]=sum(1 for l in lines if l.startswith("      * "))
    # section 1
    diff={}
    for l in lines:
        m=re.match(r"^(0 \(tied\)|\+1|\+2|\+3|\+4 or more)\s+\|\s+(.*)$",l)
        if m:
            k={"0 (tied)":"0","+1":"1","+2":"2","+3":"3","+4 or more":"4"}[m[1]]
            blocks=m[2].split("|")
            vals=[]
            for b in blocks:
                mm=re.match(r"\s*([\d,]+)\s+(?:-|([\d,]+))\s+([\d.]+)%\s*(?:([\d.]+)-([\d.]+))?",b)
                vals.append(dict(n=num(mm[1]),won=num(mm[2]) if mm[2] else None,pct=float(mm[3]),lo=float(mm[4]) if mm[4] else None,hi=float(mm[5]) if mm[5] else None))
            diff[k]={"all":vals[0],"pts":vals[1] if len(vals)>1 else None}
    d["diff"]=diff
    ups={}
    for l in lines:
        m=re.match(r"^(1 takedown|2 takedowns|3 takedowns|4\+ takedowns)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([\d,]+)$",l)
        if m: ups[m[1][0]]=dict(points=int(m[2]),ot=int(m[3]),fall=int(m[4]),forfeit=int(m[5]),unknown=int(m[6]),total=int(m[7]),of=num(m[8]))
    d["upsets"]=ups
    m=re.search(r"behind by 2 or more takedowns \((\d+) bouts\)",flat); d["big_upsets"]=int(m[1])
    # section 2
    sc=[]
    for l in lines:
        m=re.match(r"^(.{56})\|(.*)$",l)
        if m and re.search(r"\d+\.\d%",m[2]) and not l.startswith("Scenario"):
            lab=m[1].strip(); blocks=m[2].split("|")
            vals=[]
            for b in blocks:
                mm=re.match(r"\s*([\d,]+)\s+([\d,]+)\s+([\d.]+)%\s+([\d.]+)-([\d.]+)",b)
                vals.append(dict(n=num(mm[1]),won=num(mm[2]),pct=float(mm[3]),lo=float(mm[4]),hi=float(mm[5])))
            sc.append({"label":lab,"all":vals[0],"pts":vals[1] if len(vals)>1 else None})
    d["scen"]=sc
    # section 3
    m=re.search(r"([\d,]+) bouts \(([\d.]+)%\) were tied on takedowns",flat); d["tied_n"]=num(m[1])
    s3={}
    for key,pat in [("reg",r"Decided by points in regulation\s+(\d+)"),("ot",r"Went to overtime\s+(\d+)"),("fall",r"Ended in a fall \(regulation\)\s+(\d+)"),("other",r"Forfeit / injury / DQ / unmatched\s+(\d+)")]:
        mm=re.search(pat,txt); s3[key]=int(mm[1])
    d["tied_how"]=s3
    cat={}
    for l in lines:
        m=re.match(r"^(Escape|Reversal|Nearfall|Penalty|Riding time)\s{3,}(.*)$",l)
        if m and "=" in m[2] or (m and m[2].strip().startswith("-")):
            cells=re.findall(r"(\d+)/(\d+) = (\d+)%",m[2]); 
            cat[m[1]]=[{"won":int(a),"n":int(b),"pct":int(c)} for a,b,c in cells]
            # placeholders '-' : need positions; re-parse columns by fixed width
            body=l[24:]
            cols=[body[i*16:(i+1)*16].strip() for i in range(3)]
            cat[m[1]]=[]
            for c in cols:
                mm=re.match(r"(\d+)/(\d+) = (\d+)%",c)
                cat[m[1]].append({"won":int(mm[1]),"n":int(mm[2]),"pct":int(mm[3])} if mm else None)
    d["cat_edge"]=cat
    ahead={}
    for m in re.finditer(r"^  (Escape|Riding time|Nearfall|Reversal|Penalty)\s+(\d+)\s+\(([\d.]+)% of (\d+) bouts\)",txt,re.M):
        ahead[m[1]]={"n":int(m[2]),"pct":float(m[3]),"of":int(m[4])}
    d["ahead"]=ahead
    combos=[]
    for m in re.finditer(r"^\s+(\d+)\s+([\d.]+)%\s+([a-z +]+)$",txt,re.M): combos.append({"n":int(m[1]),"pct":float(m[2]),"combo":m[3].strip()})
    d["combos"]=combos
    m=re.search(r"Margin of victory: (\d+) of (\d+) \(([\d.]+)%\) were decided by 1 point; (\d+) \(([\d.]+)%\) by 2",flat)
    d["margin"]={"one":int(m[1]),"of":int(m[2]),"one_pct":float(m[3]),"two_pct":float(m[5])}
    m=re.search(r"3b\. OVERTIME.*?(\d+) bouts\. Regulation was tied on points in (\d+) of them",flat); d["ot_n"]=int(m[1])
    kinds=[]
    a=txt.index("3b. OVERTIME"); b=txt.index("Overtime winner had MORE")
    for m in re.finditer(r"^\s+(\d+)  (Tiebreaker|Sudden victory):? (.*)$",txt[a:b],re.M): kinds.append({"n":int(m[1]),"kind":m[2],"detail":m[3]})
    d["ot_kinds"]=kinds
    m=re.search(r"MORE overtime points in (\d+) bouts, FEWER in (\d+), equal in (\d+)",flat); d["ot_pts"]={"more":int(m[1]),"fewer":int(m[2]),"equal":int(m[3])}
    # section 4
    a=txt.index("4. "); s4=txt[a:txt.index("DATA NOTES")]
    m=re.search(r"([\d]+) such wins?\.",re.sub(r"\s+"," ",s4)); d["nd_top"]=int(m[1])
    rows=[]; cur=None
    for l in s4.splitlines():
        if l.startswith("| ") and not l.startswith("| Wrestler"):
            cells=[c.strip() for c in l.strip().strip("|").split("|")]
            if cells[-2:-1] and re.match(r"\d+ of \d+",cells[-2]):
                cur={"cells":cells}; rows.append(cur)
            elif cur: 
                cur["cont"]=cur.get("cont",[])+[cells]
    out=[]
    for r in rows:
        c=r["cells"]; name=c[0]; 
        for cc in r.get("cont",[]): name+=" "+cc[0]
        if len(c)==5: out.append({"name":name.strip(),"where":c[1],"place":c[2],"wins":c[3],"beat":" ".join([c[4]]+[cc[-1] for cc in r.get("cont",[])])})
        else: 
            where=c[1]+"".join(" "+cc[1] for cc in r.get("cont",[]))
            out.append({"name":name.strip(),"where":where.strip(),"place":None,"wins":c[2],"beat":" ".join([c[3]]+[cc[-1] for cc in r.get("cont",[])])})
    d["nd_rows"]=out
    m=re.search(r"and (\d+) more wrestlers tied",s4); d["nd_more"]=int(m[1]) if m else 0
    m=re.search(r"For comparison: (.*?)\.\s",re.sub(r"\s+"," ",s4)+" "); d["nd_compare"]=m[1] if m else ""
    m=re.search(r"All-Americans in the window: (\d+)",s4); d["aa_pop"]=int(m[1]) if m else None
    return d
R={}
for kind in ("ncaa","conf"):
    for w in WINDOWS:
        f=DIR/f"td_differential_report_{w}_{kind}.txt"
        R[f"{kind}|{w}"]=parse(f)
out=HERE/"reports.json"
out.write_text(json.dumps(R,indent=1))
for k,v in R.items():
    print(k,v["bouts"],v["seasons"],"more_td_pts",v["more_td_pts"],"tied",v["tied"],"diff+1",v["diff"]["1"]["pts"]["pct"],"scen",len(v["scen"]),"cats",list(v["cat_edge"]),"ahead",len(v["ahead"]),"otk",len(v["ot_kinds"]),"nd",v["nd_top"],len(v["nd_rows"]),v["nd_more"],v["nd_compare"][:70])
