#!/usr/bin/env python3
"""
Top 5 season DPG each year (2012-2026) with the Hodge Trophy winner and runner-up highlighted (TJ, 2026-10-02).

DPG = full-season mv_avg from frontend/wrestledata-ui/public/data/mat_value/{year}/mat_value_{year}.json (the Hodge is
voted after the NCAAs, so the whole season counts). Wrestlers with fewer than MIN_MATCHES matches are left out (drops
one-match flukes). Hodge winners / vote runners-up: Wikipedia "Dan Hodge Trophy" (fetched 2026-10-02); 2021 was a shared
award (Lee + Steveson, no runner-up); 2012 has no published vote counts. Names are matched on letters only
(Ed Ruth = "Edward Ruth" in our data, hence ALIASES).

Output: data/analysis/hodge_vs_dpg.html (self-contained; same look as td_custom_report / dpg_vs_ncaa_points)
Run:    .venv/bin/python scripts/analysis/hodge_vs_dpg.py
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MV_DIR = ROOT / "frontend" / "wrestledata-ui" / "public" / "data" / "mat_value"
OUT = ROOT / "data" / "analysis" / "hodge_vs_dpg.html"
MIN_MATCHES = 10

# year: ([winners], runner-up or None, {name: votes})
HODGE = {
    2012: (["David Taylor"], None, {}),
    2013: (["Kyle Dake"], "Ed Ruth", {"Kyle Dake": 39, "Ed Ruth": 4}),
    2014: (["David Taylor"], "Logan Stieber", {"David Taylor": 38, "Logan Stieber": 3}),
    2015: (["Logan Stieber"], "Alex Dieringer", {"Logan Stieber": 38, "Alex Dieringer": 3}),
    2016: (["Alex Dieringer"], "Zain Retherford", {"Alex Dieringer": 27, "Zain Retherford": 14}),
    2017: (["Zain Retherford"], "J'Den Cox", {"Zain Retherford": 33, "J'Den Cox": 5}),
    2018: (["Zain Retherford"], "Bo Nickal", {"Zain Retherford": 35, "Bo Nickal": 6}),
    2019: (["Bo Nickal"], "Jason Nolf", {"Bo Nickal": 37, "Jason Nolf": 10}),
    2020: (["Spencer Lee"], "Kollin Moore", {"Spencer Lee": 52, "Kollin Moore": 3}),
    2021: (["Spencer Lee", "Gable Steveson"], None, {}),
    2022: (["Gable Steveson"], "Yianni Diakomihalis", {"Gable Steveson": 49, "Yianni Diakomihalis": 5}),
    2023: (["Mason Parris"], "Carter Starocci", {"Mason Parris": 38, "Carter Starocci": 14}),
    2024: (["Aaron Brooks"], "Parker Keckeisen", {"Aaron Brooks": 48, "Parker Keckeisen": 8}),
    2025: (["Wyatt Hendrickson"], "Carter Starocci", {"Wyatt Hendrickson": 30, "Carter Starocci": 26}),
    2026: (["Mitchell Mesenbrink"], "Jax Forrest", {"Mitchell Mesenbrink": 66, "Jax Forrest": 4}),
}
ALIASES = {"edruth": "edwardruth"}


def key(name):
    k = re.sub(r"[^a-z]", "", (name or "").lower())
    return ALIASES.get(k, k)


def main():
    years = []
    for y, (winners, runner, votes) in HODGE.items():
        rows = json.loads((MV_DIR / str(y) / f"mat_value_{y}.json").read_text())
        q = sorted((w for w in rows if w["matches"] >= MIN_MATCHES), key=lambda w: -w["mv_avg"])
        tag = {key(n): "win" for n in winners}
        if runner:
            tag[key(runner)] = "ru"
        vote_by = {key(n): v for n, v in votes.items()}

        def entry(rank, w):
            k = key(w["name"])
            return {"rank": rank, "n": w["name"].replace("`", "'"), "t": w["team"], "w": w["weight"],
                    "d": round(w["mv_avg"], 2), "m": w["matches"], "tag": tag.get(k), "votes": vote_by.get(k)}
        top = [entry(i + 1, w) for i, w in enumerate(q[:5])]
        extra = [entry(i + 1, w) for i, w in enumerate(q[5:], start=5) if key(w["name"]) in tag]
        years.append({"y": y, "top": top, "extra": extra, "shared": len(winners) > 1,
                      "no_votes": not votes and len(winners) == 1})
    OUT.write_text(TEMPLATE.replace("__DATA__", json.dumps(years, separators=(",", ":"))))
    lead = sum(1 for yr in years if yr["top"][0]["tag"] == "win")
    print(f"{len(years)} seasons; DPG leader won the Hodge in {lead} -> {OUT}")


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DPG and the Hodge</title>
<style>
:root{
  color-scheme: light;
  --surface:#fcfcfb; --page:#f9f9f7; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --border:rgba(11,11,11,.10); --wash:rgba(11,11,11,.045);
  --gold:#a8790a; --gold-soft:#f6e7bf; --gold-line:#d9ad3c;
  --silver:#5f6b78; --silver-soft:#e4e8ee; --silver-line:#a3adb9;
  --bar:#c9c7be;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    color-scheme: dark;
    --surface:#1a1a19; --page:#0d0d0d; --ink:#ffffff; --ink2:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,.10); --wash:rgba(255,255,255,.06);
    --gold:#f0c24b; --gold-soft:#3a2f12; --gold-line:#b8901f;
    --silver:#c5ced8; --silver-soft:#2a3038; --silver-line:#6d7885;
    --bar:#46453f;
  }
}
:root[data-theme="dark"]{
  color-scheme: dark;
  --surface:#1a1a19; --page:#0d0d0d; --ink:#ffffff; --ink2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,.10); --wash:rgba(255,255,255,.06);
  --gold:#f0c24b; --gold-soft:#3a2f12; --gold-line:#b8901f;
  --silver:#c5ced8; --silver-soft:#2a3038; --silver-line:#6d7885;
  --bar:#46453f;
}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:0 16px 80px}
header.top{padding:32px 0 6px}
h1{font-size:28px;line-height:1.2;margin:0 0 6px;letter-spacing:-.01em}
.sub{color:var(--ink2);max-width:74ch;margin:6px 0}
.bar{display:flex;flex-wrap:wrap;gap:10px 22px;align-items:center;padding:10px 0;border-bottom:1px solid var(--border);margin-top:12px}
.fg{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--ink2)}
.seg{display:inline-flex;border:1px solid var(--border);border-radius:8px;overflow:hidden;background:var(--surface)}
.seg button{font:inherit;font-size:13px;border:0;background:transparent;color:var(--ink2);padding:6px 12px;cursor:pointer}
.seg button+button{border-left:1px solid var(--border)}
.seg button[aria-pressed="true"]{background:var(--ink);color:var(--surface);font-weight:600}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:13px;color:var(--ink2);align-items:center}
.legend .it{display:inline-flex;align-items:center;gap:6px}
.sw{width:14px;height:14px;border-radius:4px;display:inline-block;border:1.5px solid}
.info{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:22px 0 8px}
.ig{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:16px 18px 14px}
.ig .kicker{font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--ink2)}
.ig .big{font-size:44px;line-height:1.05;font-weight:750;letter-spacing:-.03em;margin-top:6px}
.ig .big small{font-size:22px;font-weight:650;color:var(--ink2);letter-spacing:0}
.ig .say{font-size:14px;line-height:1.45;margin-top:6px}

/* the board */
.board{margin-top:18px;background:var(--surface);border:1px solid var(--border);border-radius:14px;overflow:hidden}
.hdr,.yr{display:grid;grid-template-columns:64px repeat(5,minmax(0,1fr)) minmax(0,1.05fr);align-items:stretch}
.hdr{font-size:11.5px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--muted);border-bottom:1px solid var(--border)}
.hdr div{padding:9px 10px}
.yr{border-bottom:1px solid var(--border)}
.yr:last-child{border-bottom:0}
.yr:hover{background:var(--wash)}
.ylab{display:flex;flex-direction:column;justify-content:center;padding:8px 10px;font-weight:750;font-size:17px;letter-spacing:-.01em}
.ylab small{font-size:11px;font-weight:600;color:var(--muted);letter-spacing:0}
.cell{padding:6px 5px;min-width:0}
.c{height:100%;border-radius:9px;padding:7px 9px 8px;border:1.5px solid transparent;display:flex;flex-direction:column;gap:2px;min-width:0;position:relative}
.c .nm{font-weight:650;font-size:13.5px;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.c .tl{display:flex;align-items:center;gap:6px;min-width:0}
.c .tm{flex:1 1 auto;min-width:0;font-size:11.5px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.c .row{display:flex;align-items:center;gap:7px;margin-top:3px}
.c .val{font-variant-numeric:tabular-nums;font-weight:700;font-size:13px;min-width:34px}
.c .trk{flex:1;height:5px;border-radius:3px;background:var(--wash);overflow:hidden}
.c .trk i{display:block;height:100%;border-radius:3px;background:var(--bar)}
.c.win{background:var(--gold-soft);border-color:var(--gold-line)}
.c.win .trk i{background:var(--gold)}
.c.ru{background:var(--silver-soft);border-color:var(--silver-line)}
.c.ru .trk i{background:var(--silver)}
.badge{flex:0 0 auto;font-size:10px;font-weight:750;letter-spacing:.04em;text-transform:uppercase;border-radius:999px;padding:1px 7px}
.c.win .badge{background:var(--gold);color:var(--surface)}
.c.ru .badge{background:var(--silver);color:var(--surface)}
.c .vt{font-size:11px;color:var(--ink2)}
.out{display:flex;flex-direction:column;gap:6px;justify-content:center}
.out .c{height:auto}
.out .rk{font-size:11px;font-weight:700;color:var(--ink2)}
.none{display:flex;align-items:center;height:100%;padding:0 8px;font-size:12px;color:var(--muted)}
.cap{font-size:12.5px;color:var(--ink2);margin:10px 2px 0}
.foot2{font-size:13px;color:var(--ink2);margin-top:30px}
.foot2 li{margin:4px 0}
.foot2 a{color:inherit}
@media (max-width:820px){
  .hdr{display:none}
  .yr{grid-template-columns:1fr;padding:6px 0 10px}
  .ylab{flex-direction:row;justify-content:flex-start;align-items:baseline;gap:8px;padding:8px 12px 2px}
  .cell{padding:3px 10px}
  .c{flex-direction:row;align-items:center;flex-wrap:wrap;gap:2px 10px;padding:7px 10px}
  .c .nm{flex:1 1 auto}
  .c .tl{flex:1 1 100%;order:3}
  .c .row{margin:0;flex:0 0 130px}
  .cell .rkm{display:inline}
  .out{padding:3px 10px}
}
.rkm{display:none;font-size:11px;font-weight:700;color:var(--muted);min-width:18px}
</style>
</head>
<body>
<div class="wrap">
<header class="top">
  <h1>DPG and the Hodge Trophy</h1>
  <p class="sub">The five best DPG seasons each year, 2012–2026, with the Hodge Trophy winner and the runner-up in the vote marked. When the voters picked someone outside the top five, he's shown at the end of that year's row with his DPG rank.</p>
</header>
<div class="bar">
  <div class="legend"><span class="it"><span class="sw" style="background:var(--gold-soft);border-color:var(--gold-line)"></span>Hodge winner</span><span class="it"><span class="sw" style="background:var(--silver-soft);border-color:var(--silver-line)"></span>Runner-up in the vote</span></div>
  <div class="fg" style="margin-left:auto"><span>Theme</span><div class="seg" id="f-theme"><button data-v="auto" aria-pressed="true">Auto</button><button data-v="light" aria-pressed="false">Light</button><button data-v="dark" aria-pressed="false">Dark</button></div></div>
</div>
<div class="info" id="info"></div>
<div class="board" role="table" aria-label="Top five DPG per season with Hodge winner and runner-up">
  <div class="hdr" role="row"><div>Year</div><div>#1 DPG</div><div>#2</div><div>#3</div><div>#4</div><div>#5</div><div>Hodge pick outside the top 5</div></div>
  <div id="rows"></div>
</div>
<p class="cap">Bars run from DPG 4.5 to the best season shown. Only wrestlers with 10 or more matches count.</p>
<ul class="foot2">
  <li><b>DPG</b> here is the full season including the NCAA Championships, because the Hodge is voted on after them.</li>
  <li>The number on each badge is first-place votes. <b>Runner-up</b> = second in the published vote. 2021 was a shared award (Spencer Lee and Gable Steveson) with no runner-up; 2012 has no published vote counts.</li>
  <li>Winners and votes: <a href="https://en.wikipedia.org/wiki/Dan_Hodge_Trophy">Wikipedia, Dan Hodge Trophy</a>.</li>
</ul>
</div>
<script>
const DATA = __DATA__;
(function(){
"use strict";
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const all = DATA.flatMap((y) => [...y.top, ...y.extra]);
const lo = 4.5, hi = Math.max(...all.map((e) => e.d));
const pct = (d) => Math.max(3, Math.min(100, (d - lo) / (hi - lo) * 100));

function card(e, showRank){
  const badge = e.tag === "win" ? "Hodge" : e.tag === "ru" ? "2nd" : "";
  const tip = `${e.n} · ${e.t} · ${e.w} lbs · ${e.m} matches` + (e.votes != null ? ` · ${e.votes} first-place votes` : "");
  return `<div class="c ${e.tag || ""}" title="${esc(tip)}">` +
    `<div class="nm"><span class="rkm">${e.rank}</span> ${esc(e.n)}</div>` +
    `<div class="tl"><span class="tm">${showRank ? `<span class="rk">#${e.rank} in DPG · </span>` : ""}${esc(e.t)} · ${e.w}</span>` +
    (badge ? `<span class="badge">${badge}${e.votes != null ? ` · ${e.votes}` : ""}</span>` : "") + `</div>` +
    `<div class="row"><span class="val">${e.d.toFixed(2)}</span><span class="trk"><i style="width:${pct(e.d).toFixed(1)}%"></i></span></div></div>`;
}

$("rows").innerHTML = DATA.slice().reverse().map((y) => {
  const out = y.extra.length ? `<div class="out">${y.extra.map((e) => card(e, true)).join("")}</div>`
    : `<div class="none">${y.shared ? "Shared award, no runner-up" : y.no_votes ? "Vote counts not published" : ""}</div>`;
  return `<div class="yr" role="row"><div class="ylab">${y.y}${y.top[0].tag === "win" ? "<small>DPG #1 won</small>" : ""}</div>` +
    y.top.map((e) => `<div class="cell">${card(e)}</div>`).join("") + `<div class="cell">${out}</div></div>`;
}).join("");

const n = DATA.length;
const leadWon = DATA.filter((y) => y.top[0].tag === "win").length;
const winTop5 = DATA.filter((y) => y.top.some((e) => e.tag === "win")).length;
const ruYears = DATA.filter((y) => [...y.top, ...y.extra].some((e) => e.tag === "ru"));
const ruTop5 = ruYears.filter((y) => y.top.some((e) => e.tag === "ru")).length;
$("info").innerHTML =
  `<div class="ig"><div class="kicker">DPG leader won the Hodge</div><div class="big">${leadWon}<small> of ${n}</small></div><div class="say">seasons, counting 2021's shared award.</div></div>` +
  `<div class="ig"><div class="kicker">Hodge winner in the DPG top 5</div><div class="big">${winTop5}<small> of ${n}</small></div><div class="say">Every winner. The lowest was Kyle Dake, #4 in 2013, the year of his fourth title.</div></div>` +
  `<div class="ig"><div class="kicker">Runner-up in the DPG top 5</div><div class="big">${ruTop5}<small> of ${ruYears.length}</small></div><div class="say">Second place is looser: it's ranged from #1 to #10 in DPG.</div></div>`;

$("f-theme").addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b) return;
  $("f-theme").querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", x === b));
  if (b.dataset.v === "auto") document.documentElement.removeAttribute("data-theme"); else document.documentElement.setAttribute("data-theme", b.dataset.v); });
})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
