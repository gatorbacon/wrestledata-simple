#!/usr/bin/env python3
"""
DPG going into the NCAA Championships vs. team points scored there, 2024-2026 (TJ, 2026-10-02, "just for fun").

Sources
  NCAA bouts:        data/ncaa-tourney-parsed/all_matches.json (TrackWrestling)
  Per-match DPG:     frontend/wrestledata-ui/public/data/mat_value/{year}/match_mv_impact_{year}.json
  Name/team/weight:  frontend/wrestledata-ui/public/data/mat_value/{year}/mat_value_{year}.json

"DPG going in" = mean mv_impact of the wrestler's matches dated before March 15 (every conference tournament is
done by then; the NCAA bouts are all dated the tournament's last day). Note the per-match values still use
full-season opponent strength, so this is the season-end view of the pre-tournament matches, not a live snapshot.

Points = individual NCAA team points, same rules as scripts/brackets/build_ncaa_bracket_archive.py:
advancement 1 per championship win (pigtail-SF), 0.5 per consolation win before the place bouts; placement
16-12-10-9-7-6-4-3; bonus 2 fall/forfeit/default/DQ, 1.5 tech fall, 1 major.

Output: data/analysis/dpg_vs_ncaa_points.html (self-contained, inline SVG; styled like td_custom_report.html)
Run:    .venv/bin/python scripts/analysis/dpg_vs_ncaa_points.py
"""
import json
import re
import statistics
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
YEARS = (2024, 2025, 2026)
MV_DIR = ROOT / "frontend" / "wrestledata-ui" / "public" / "data" / "mat_value"
OUT = ROOT / "data" / "analysis" / "dpg_vs_ncaa_points.html"
PLACE_PTS = {1: 16, 2: 12, 3: 10, 4: 9, 5: 7, 6: 6, 7: 4, 8: 3}
PLACE_BOUT = {"Final": (1, 2), "3rd": (3, 4), "5th": (5, 6), "7th": (7, 8)}


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", s)


def bonus(rt):
    rt = (rt or "").upper()
    if rt.startswith(("FALL", "FF", "MFF", "FOR", "DEF", "INJ", "DQ")):
        return 2.0
    if rt.startswith("TF"):
        return 1.5
    if rt.startswith("MD"):
        return 1.0
    return 0.0


def ncaa_points(rows):
    pts, place, seed, wins, losses = defaultdict(float), {}, {}, defaultdict(int), defaultdict(int)
    for m in rows:
        w = (m["winner_name"], m["winner_team"], m["weight"])
        l = (m["loser_name"], m["loser_team"], m["weight"])
        seed[w], seed[l] = m["winner_seed"], m["loser_seed"]
        pts[l] += 0
        r = m["round"]
        if r in ("PIG", "R32", "R16", "QF", "SF"):
            pts[w] += 1.0
        elif r in ("C_PIG", "C_R1", "C_R2", "C_R3", "C_R4", "C_QF", "C_SF"):
            pts[w] += 0.5
        pts[w] += bonus(m["result_type"])
        wins[w] += 1
        losses[l] += 1
        if r in PLACE_BOUT:
            wp, lp = PLACE_BOUT[r]
            place[w], place[l] = wp, lp
    for k, p in place.items():
        pts[k] += PLACE_PTS[p]
    return pts, place, seed, wins, losses


def build_year(y, allm):
    rows = [m for m in allm if m["year"] == y]
    pts, place, seed, wins, losses = ncaa_points(rows)
    mv = json.loads((MV_DIR / str(y) / f"mat_value_{y}.json").read_text())
    imp = json.loads((MV_DIR / str(y) / f"match_mv_impact_{y}.json").read_text())
    by_nw, by_n = defaultdict(list), defaultdict(list)
    for w in mv:
        by_nw[(norm(w["name"]), w["weight"])].append(w)
        by_n[norm(w["name"])].append(w)
    cutoff = date(y, 3, 15)
    out, missing = [], []
    for (name, team, wt), p in pts.items():
        cands = by_nw.get((norm(name), wt)) or by_n.get(norm(name)) or []
        if len(cands) > 1:   # same name twice: prefer the same team
            same = [c for c in cands if norm(c["team"])[:6] == norm(team)[:6]]
            cands = same or cands
        if not cands:
            missing.append(f"{y} {wt} {name} ({team})")
            continue
        wid = cands[0]["wrestler_id"]
        vals = []
        for r in imp.get(wid, []):
            mm, dd, yy = (int(x) for x in r["date"].split("/"))
            if date(yy, mm, dd) < cutoff and r.get("mv_impact") is not None:
                vals.append(r["mv_impact"])
        if not vals:
            missing.append(f"{y} {wt} {name} ({team}): no pre-tournament DPG matches")
            continue
        out.append({"y": y, "n": name, "t": team, "w": wt, "s": seed.get((name, team, wt)),
                    "d": round(statistics.mean(vals), 3), "m": len(vals), "p": p,
                    "pl": place.get((name, team, wt)), "rec": f"{wins[(name, team, wt)]}-{losses[(name, team, wt)]}"})
    return out, missing


def main():
    allm = json.loads((ROOT / "data" / "ncaa-tourney-parsed" / "all_matches.json").read_text())
    data, missing = [], []
    for y in YEARS:
        d, miss = build_year(y, allm)
        data += d
        missing += miss
    tpl = TEMPLATE.replace("__DATA__", json.dumps(data, separators=(",", ":"))) \
                  .replace("__MISSING__", json.dumps(missing))
    OUT.write_text(tpl)
    print(f"{len(data)} wrestlers, {len(missing)} not matched -> {OUT}")
    for m in missing:
        print("  ", m)


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DPG and NCAA Points</title>
<style>
:root{
  color-scheme: light;
  --surface:#fcfcfb; --page:#f9f9f7; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --border:rgba(11,11,11,.10); --wash:rgba(11,11,11,.045);
  --y2024:#2a78d6; --y2025:#eb6834; --y2026:#4a3aa7; --fit:#0b0b0b; --bar:#1f8a70;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    color-scheme: dark;
    --surface:#1a1a19; --page:#0d0d0d; --ink:#ffffff; --ink2:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,.10); --wash:rgba(255,255,255,.06);
    --y2024:#3987e5; --y2025:#d95926; --y2026:#9085e9; --fit:#ffffff; --bar:#3aa888;
  }
}
:root[data-theme="dark"]{
  color-scheme: dark;
  --surface:#1a1a19; --page:#0d0d0d; --ink:#ffffff; --ink2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,.10); --wash:rgba(255,255,255,.06);
  --y2024:#3987e5; --y2025:#d95926; --y2026:#9085e9; --fit:#ffffff; --bar:#3aa888;
}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1000px;margin:0 auto;padding:0 16px 80px}
header.top{padding:32px 0 6px}
h1{font-size:28px;line-height:1.2;margin:0 0 6px;letter-spacing:-.01em}
h2{font-size:21px;line-height:1.25;margin:0 0 4px}
p{margin:6px 0}
.sub{color:var(--ink2);max-width:72ch}
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px 18px;margin:12px 0}
section.sec{margin-top:44px}
.num{display:inline-block;min-width:26px;height:26px;padding:0 6px;line-height:26px;text-align:center;font-size:13px;font-weight:700;color:var(--surface);background:var(--ink);border-radius:13px;margin-right:8px;vertical-align:2px}
.bar{display:flex;flex-wrap:wrap;gap:10px 22px;align-items:center;padding:10px 0;border-bottom:1px solid var(--border);margin-top:12px}
.fg{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--ink2)}
.seg{display:inline-flex;border:1px solid var(--border);border-radius:8px;overflow:hidden;background:var(--surface)}
.seg button{font:inherit;font-size:13px;border:0;background:transparent;color:var(--ink2);padding:6px 12px;cursor:pointer}
.seg button+button{border-left:1px solid var(--border)}
.seg button[aria-pressed="true"]{background:var(--ink);color:var(--surface);font-weight:600}
.seg button:focus-visible{outline:2px solid var(--y2024);outline-offset:-2px}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:13px;color:var(--ink2);align-items:center}
.legend .it{display:inline-flex;align-items:center;gap:6px}
.sw{width:12px;height:12px;border-radius:50%;display:inline-block}
.sw.ln{width:18px;height:2px;border-radius:1px}
svg{display:block;width:100%;height:auto;overflow:visible}
svg text{font-family:inherit;fill:var(--ink2);font-size:11px}
svg text.tk{fill:var(--muted)}
svg text.ink{fill:var(--ink)}
svg .dot{stroke:var(--surface);stroke-width:1.5;cursor:default}
svg .dot:hover,svg .dot:focus{stroke:var(--ink);stroke-width:2;outline:none}
svg .b:hover,svg .b:focus{stroke:var(--ink);stroke-width:2;outline:none}
.cap{font-size:12.5px;color:var(--ink2);margin:8px 2px 0}
.info{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin-top:10px}
.ig{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:18px 18px 14px}
.ig .kicker{font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--ink2)}
.ig .big{font-size:48px;line-height:1.05;font-weight:750;letter-spacing:-.03em;color:var(--ink);margin-top:6px}
.ig .say{font-size:14px;line-height:1.45;margin-top:6px;color:var(--ink)}
details.tw{margin-top:8px}
details.tw summary{cursor:pointer;font-size:13px;color:var(--ink2)}
.tabwrap{overflow-x:auto;background:var(--surface);border:1px solid var(--border);border-radius:12px;margin-top:8px}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{padding:7px 9px;text-align:right;border-bottom:1px solid var(--border);white-space:nowrap}
th{font-weight:600;color:var(--ink2)}
td.l,th.l{text-align:left}
td small{color:var(--muted);font-size:11px}
.two td.l{white-space:normal}.two td.l small{display:block}
tr:last-child td{border-bottom:0}
.two{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
.tt{position:fixed;z-index:50;pointer-events:none;background:var(--ink);color:var(--surface);border-radius:8px;padding:8px 10px;font-size:12.5px;line-height:1.35;max-width:280px;box-shadow:0 4px 18px rgba(0,0,0,.25);opacity:0;transition:opacity .08s}
.tt .th{font-weight:650;margin-bottom:2px}.tt .tv{font-size:17px;font-weight:700}.tt .m{opacity:.7}
.foot2{font-size:13px;color:var(--ink2)}
.foot2 li{margin:4px 0}
</style>
</head>
<body>
<div class="wrap">
<header class="top">
  <h1>Does DPG going in predict NCAA points?</h1>
  <p class="sub">Every NCAA Division I qualifier from 2024, 2025 and 2026. Across: the wrestler's DPG from the regular season and his conference tournament. Up: the team points he scored at the NCAA Championships.</p>
</header>
<div class="bar">
  <div class="fg"><span>Year</span><div class="seg" id="f-year"><button data-v="all" aria-pressed="true">All 3</button><button data-v="2024" aria-pressed="false">2024</button><button data-v="2025" aria-pressed="false">2025</button><button data-v="2026" aria-pressed="false">2026</button></div></div>
  <div class="fg"><span>Theme</span><div class="seg" id="f-theme"><button data-v="auto" aria-pressed="true">Auto</button><button data-v="light" aria-pressed="false">Light</button><button data-v="dark" aria-pressed="false">Dark</button></div></div>
  <div class="legend"><span class="it"><span class="sw" style="background:var(--y2024)"></span>2024</span><span class="it"><span class="sw" style="background:var(--y2025)"></span>2025</span><span class="it"><span class="sw" style="background:var(--y2026)"></span>2026</span><span class="it"><span class="sw ln" style="background:var(--fit)"></span>Average for that DPG</span></div>
</div>

<section class="sec">
  <h2><span class="num">1</span>Higher DPG, more points</h2>
  <div class="info" id="info"></div>
  <div class="card" style="padding:12px 8px 8px"><div id="c1"></div></div>
  <p class="cap" id="c1cap"></p>
</section>

<section class="sec">
  <h2><span class="num">2</span>Average points by DPG going in</h2>
  <p class="sub">Wrestlers grouped by DPG. Each bar is the average NCAA team points for that group; the label under it is how many wrestlers and how many of them became All-Americans.</p>
  <div class="card" style="padding:12px 8px 8px"><div id="c2"></div></div>
  <details class="tw"><summary>Show as table</summary><div id="t2"></div></details>
</section>

<section class="sec">
  <h2><span class="num">3</span>Who beat their DPG, and who fell short</h2>
  <p class="sub">Points scored minus the average for wrestlers with the same DPG going in (the line in chart 1).</p>
  <div class="two" id="t3"></div>
</section>

<section class="sec">
  <h2>How this was built</h2>
  <ul class="foot2">
    <li><b>DPG going in</b>: average DPG of every match before March 15 (regular season plus conference tournament). Opponent strength in those matches uses the full season, so it's the season-end view of those matches rather than the number shown on the site the day before the tournament.</li>
    <li><b>Points</b>: individual team points with NCAA scoring. 1 per championship win (pigtail through semifinal), 0.5 per consolation win, 16-12-10-9-7-6-4-3 for 1st to 8th, plus 2 for a fall, forfeit, default or DQ, 1.5 for a tech fall and 1 for a major.</li>
    <li><b>Average line</b>: mean points of every wrestler within 0.5 DPG of each point (drawn where there are at least 8). <b>r</b> is the correlation: 0 means no relationship, 1 means a perfect straight line. For comparison, the same r is shown for the seed (1 = best).</li>
    <li id="missing"></li>
  </ul>
</section>
</div>
<div class="tt" id="tt" role="tooltip"></div>
<script>
const DATA = __DATA__;
const MISSING = __MISSING__;
(function(){
"use strict";
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const COL = (y) => `var(--y${y})`;
const PLACE = ["", "1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th"];
let year = "all";

// average points in a 1-DPG-wide window (needs 8+ wrestlers), every 0.25, joined into a curve;
// expected(x) interpolates it. A straight line misfits: points stay near 0 until about +2 DPG, then climb.
function curve(R){
  const pts = [];
  for (let c = -1; c <= 6.01; c += 0.25) {
    const g = R.filter((d) => Math.abs(d.d - c) <= 0.5);
    if (g.length >= 8) pts.push([c, g.reduce((s, d) => s + d.p, 0) / g.length]);
  }
  return pts;
}
function expected(cv, x){
  if (!cv.length) return 0;
  if (x <= cv[0][0]) return cv[0][1];
  for (let i = 1; i < cv.length; i++) if (x <= cv[i][0]) {
    const [x0, y0] = cv[i-1], [x1, y1] = cv[i]; return y0 + (x - x0) / (x1 - x0) * (y1 - y0);
  }
  return cv[cv.length - 1][1];
}
function fit(xs, ys){
  const n = xs.length, mx = xs.reduce((a,b)=>a+b,0)/n, my = ys.reduce((a,b)=>a+b,0)/n;
  let sxy=0, sxx=0, syy=0;
  for (let i=0;i<n;i++){ sxy+=(xs[i]-mx)*(ys[i]-my); sxx+=(xs[i]-mx)**2; syy+=(ys[i]-my)**2; }
  const b = sxy/sxx; return {b, a: my-b*mx, r: sxy/Math.sqrt(sxx*syy)};
}
const fmt = (v, d=1) => (v>0?"+":v<0?"−":"") + Math.abs(v).toFixed(d);

// tooltip
const tt = $("tt");
function showTT(e, html){ tt.innerHTML = html; tt.style.opacity = 1; moveTT(e); }
function moveTT(e){
  const r = tt.getBoundingClientRect(), pad = 14;
  let x = (e.clientX ?? 0) + pad, y = (e.clientY ?? 0) + pad;
  if (x + r.width > innerWidth - 8) x = (e.clientX ?? 0) - r.width - pad;
  if (y + r.height > innerHeight - 8) y = (e.clientY ?? 0) - r.height - pad;
  tt.style.left = Math.max(8, x) + "px"; tt.style.top = Math.max(8, y) + "px";
}
function hideTT(){ tt.style.opacity = 0; }
function bindTT(root, sel, htmlFor){
  root.querySelectorAll(sel).forEach((el) => {
    const h = () => htmlFor(el);
    el.addEventListener("mouseenter", (e) => showTT(e, h()));
    el.addEventListener("mousemove", moveTT);
    el.addEventListener("mouseleave", hideTT);
    el.addEventListener("focus", () => { const b = el.getBoundingClientRect(); showTT({clientX:b.right, clientY:b.top}, h()); });
    el.addEventListener("blur", hideTT);
    el.addEventListener("click", (e) => { showTT(e, h()); e.stopPropagation(); });
  });
}
document.addEventListener("click", hideTT);
addEventListener("scroll", hideTT, {passive:true});

function rows(){ return year === "all" ? DATA : DATA.filter((d) => String(d.y) === year); }

function wrestlerTT(d){
  return `<div class="th">${esc(d.n)}</div><div class="m">${esc(d.t)} · ${d.w} · ${d.y} · seed ${d.s ?? "–"}</div>` +
    `<div class="tv">${d.p} pts</div><div>DPG going in ${fmt(d.d,2)} (${d.m} matches)</div>` +
    `<div class="m">${d.pl ? PLACE[d.pl] + " place" : "Did not place"} · NCAA record ${d.rec}</div>`;
}

// ---------- 1: scatter ----------
function drawScatter(){
  const R = rows(), W = 940, H = 520, m = {l:52, r:16, t:14, b:46};
  const xs = R.map((d)=>d.d), ys = R.map((d)=>d.p);
  const x0 = Math.floor(Math.min(...DATA.map((d)=>d.d))), x1 = Math.ceil(Math.max(...DATA.map((d)=>d.d)));
  const y1 = Math.ceil(Math.max(...DATA.map((d)=>d.p))/5)*5;
  const X = (v) => m.l + (v-x0)/(x1-x0)*(W-m.l-m.r), Y = (v) => H-m.b - v/y1*(H-m.t-m.b);
  let g = "";
  for (let v=0; v<=y1; v+=5) g += `<line x1="${m.l}" x2="${W-m.r}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--grid)"/><text class="tk" x="${m.l-8}" y="${Y(v)+4}" text-anchor="end">${v}</text>`;
  for (let v=x0; v<=x1; v++) g += `<line x1="${X(v)}" x2="${X(v)}" y1="${m.t}" y2="${H-m.b}" stroke="var(--grid)"${v===0?' stroke-dasharray="4 3" style="stroke:var(--axis)"':""}/><text class="tk" x="${X(v)}" y="${H-m.b+16}" text-anchor="middle">${v>0?"+"+v:v<0?"−"+(-v):0}</text>`;
  g += `<line x1="${m.l}" x2="${W-m.r}" y1="${H-m.b}" y2="${H-m.b}" stroke="var(--axis)"/>`;
  g += `<text x="${(m.l+W-m.r)/2}" y="${H-6}" text-anchor="middle" class="ink">DPG going into the tournament</text>`;
  g += `<text transform="translate(14 ${(m.t+H-m.b)/2}) rotate(-90)" text-anchor="middle" class="ink">NCAA team points scored</text>`;
  const f = fit(xs, ys);
  f.cv = curve(R);
  g += `<path d="${f.cv.map(([x, y], i) => (i ? "L" : "M") + X(x).toFixed(1) + " " + Y(y).toFixed(1)).join("")}" fill="none" stroke="var(--fit)" stroke-width="2.5" stroke-linejoin="round" opacity=".85"/>`;
  const sorted = R.slice().sort((a,b) => a.p - b.p);
  g += sorted.map((d) => `<circle class="dot" tabindex="0" data-i="${DATA.indexOf(d)}" cx="${X(d.d).toFixed(1)}" cy="${Y(d.p).toFixed(1)}" r="5" fill="${COL(d.y)}" fill-opacity=".8"/>`).join("");
  $("c1").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Scatter of DPG going in versus NCAA points">${g}</svg>`;
  bindTT($("c1"), ".dot", (el) => wrestlerTT(DATA[+el.dataset.i]));
  $("c1cap").textContent = `${R.length} wrestlers. The line is the average points of wrestlers with about that DPG. Hover or tap a dot for the wrestler.`;
  return f;
}

// ---------- headline cards ----------
function drawInfo(f){
  const R = rows();
  const seedFit = fit(R.filter((d)=>d.s!=null).map((d)=>-d.s), R.filter((d)=>d.s!=null).map((d)=>d.p));
  const top = R.filter((d)=>d.d>=4), aaTop = top.filter((d)=>d.pl).length;
  $("info").innerHTML =
    `<div class="ig"><div class="kicker">DPG vs. points</div><div class="big">r = ${f.r.toFixed(2)}</div><div class="say">A real but loose link: DPG explains about <b>${Math.round(f.r*f.r*100)}%</b> of the spread in points.</div></div>` +
    `<div class="ig"><div class="kicker">Seed vs. points</div><div class="big">r = ${seedFit.r.toFixed(2)}</div><div class="say">${Math.abs(seedFit.r) > Math.abs(f.r) ? "The seed tracks points <b>more closely</b> than DPG does." : "DPG tracks points <b>at least as well</b> as the seed does."}</div></div>` +
    `<div class="ig"><div class="kicker">DPG +4 or better going in</div><div class="big">${top.length ? Math.round(aaTop/top.length*100) : 0}%</div><div class="say">became All-Americans (${aaTop} of ${top.length}).</div></div>`;
}

// ---------- 2: bands ----------
const BANDS = [[-99,0,"below 0"],[0,1,"0 to 1"],[1,2,"1 to 2"],[2,3,"2 to 3"],[3,4,"3 to 4"],[4,5,"4 to 5"],[5,99,"5+"]];
function drawBands(){
  const R = rows();
  const B = BANDS.map(([a,b,l]) => {
    const g = R.filter((d) => d.d >= a && d.d < b);
    return {l, n: g.length, avg: g.length ? g.reduce((s,d)=>s+d.p,0)/g.length : 0, aa: g.filter((d)=>d.pl).length,
            champ: g.filter((d)=>d.pl===1).length};
  });
  const W = 940, H = 330, m = {l:44, r:12, t:22, b:56};
  const ymax = Math.ceil(Math.max(...B.map((b)=>b.avg))/5)*5 || 5;
  const bw = (W-m.l-m.r)/B.length, Y = (v) => H-m.b - v/ymax*(H-m.t-m.b);
  let g = "";
  for (let v=0; v<=ymax; v+=5) g += `<line x1="${m.l}" x2="${W-m.r}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--grid)"/><text class="tk" x="${m.l-8}" y="${Y(v)+4}" text-anchor="end">${v}</text>`;
  B.forEach((b, i) => {
    const x = m.l + i*bw + bw*0.18, w = bw*0.64, y = Y(b.avg), h = H-m.b-y;
    if (b.n) g += `<path class="b" tabindex="0" data-i="${i}" fill="var(--bar)" d="M${x} ${H-m.b}V${y+Math.min(4,h)}q0 -4 4 -4h${w-8}q4 0 4 4V${H-m.b}Z"/>` +
      `<text class="ink" x="${x+w/2}" y="${y-6}" text-anchor="middle" style="font-weight:650">${b.avg.toFixed(1)}</text>`;
    g += `<text class="ink" x="${m.l+i*bw+bw/2}" y="${H-m.b+16}" text-anchor="middle">${b.l}</text>` +
         `<text class="tk" x="${m.l+i*bw+bw/2}" y="${H-m.b+31}" text-anchor="middle">${b.n} wr · ${b.aa} AA</text>`;
  });
  g += `<line x1="${m.l}" x2="${W-m.r}" y1="${H-m.b}" y2="${H-m.b}" stroke="var(--axis)"/>`;
  g += `<text x="${(m.l+W-m.r)/2}" y="${H-4}" text-anchor="middle" class="ink">DPG going into the tournament</text>`;
  $("c2").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Average NCAA points by DPG group">${g}</svg>`;
  bindTT($("c2"), ".b", (el) => { const b = B[+el.dataset.i];
    return `<div class="th">DPG ${b.l}</div><div class="tv">${b.avg.toFixed(1)} pts avg</div><div>${b.n} wrestlers · ${b.aa} All-Americans · ${b.champ} champions</div>`; });
  $("t2").innerHTML = `<div class="tabwrap"><table><thead><tr><th class="l">DPG going in</th><th>Wrestlers</th><th>Avg points</th><th>All-Americans</th><th>AA rate</th><th>Champions</th></tr></thead><tbody>` +
    B.map((b) => `<tr><td class="l">${b.l}</td><td>${b.n}</td><td>${b.avg.toFixed(1)}</td><td>${b.aa}</td><td>${b.n?Math.round(b.aa/b.n*100):0}%</td><td>${b.champ}</td></tr>`).join("") + `</tbody></table></div>`;
}

// ---------- 3: over / under ----------
function drawResid(f){
  const R = rows().map((d) => ({...d, exp: expected(f.cv, d.d)})).map((d) => ({...d, res: d.p - d.exp}));
  const tbl = (title, list) => `<div><h3 style="font-size:15px;margin:10px 0 6px">${title}</h3><div class="tabwrap"><table><thead><tr><th class="l">Wrestler</th><th>DPG in</th><th>Pts</th><th>vs. avg</th></tr></thead><tbody>` +
    list.map((d) => `<tr><td class="l">${esc(d.n)} <small>${esc(d.t)} · ${d.w} · ${d.y} · #${d.s ?? "–"}</small></td><td>${fmt(d.d,2)}</td><td>${d.p}</td><td><b>${fmt(d.res)}</b></td></tr>`).join("") + `</tbody></table></div></div>`;
  const s = R.slice().sort((a,b) => b.res - a.res);
  $("t3").innerHTML = tbl("Beat their DPG", s.slice(0,10)) + tbl("Fell short of it", s.slice(-10).reverse());
}

function render(){ const f = drawScatter(); drawInfo(f); drawBands(); drawResid(f); }

function seg(id, cb){ $(id).addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b) return;
  $(id).querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", x === b)); cb(b.dataset.v); }); }
seg("f-year", (v) => { year = v; render(); });
seg("f-theme", (v) => { if (v === "auto") document.documentElement.removeAttribute("data-theme"); else document.documentElement.setAttribute("data-theme", v); });
$("missing").innerHTML = MISSING.length ? `<b>Left out</b> (no DPG match found): ${MISSING.map(esc).join("; ")}.` : "Every qualifier was matched to his DPG.";
render();
})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
