#!/usr/bin/env python3
"""Generates the program-strength-adjusted HTML dashboard: uniform-color rows,
green/medal-intensity percentage cells, 10 exact-placement columns, and a
date dropdown that discovers every scraped rankings touch point so far."""
import json
import re
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path("/Users/tjthompson/Documents/Cursor/wrestledata-simple")
COMBINED_DIR = PROJECT_ROOT / "data/ncaa-tourney-parsed"

SCALE_MAX = 200  # fixed domain for every team/date, so bands are directly comparable
HEAT_FLOOR = 10.0  # below this, cell gets no tint at all -- reads as "not a realistic finish"

# Places 1-4 all earn a team trophy at NCAAs, so they get medal tints instead of
# the generic green intensity ramp (3rd and 4th share bronze -- same trophy tier).
PLACE_COLOR = {1: "gold", 2: "silver", 3: "bronze", 4: "bronze"}
MEDAL = {1: "medal-gold", 2: "medal-silver", 3: "medal-bronze"}


def heat_cell(pct, place):
    color = PLACE_COLOR.get(place, "green")
    if pct < HEAT_FLOOR:
        return f'<td class="col-pct">{pct:.1f}%</td>'
    linear = max(0.0, min(1.0, (pct - HEAT_FLOOR) / (100 - HEAT_FLOOR)))
    intensity = linear ** 1.6
    glow = ' hot' if (intensity > 0.6 and color == "green") else ''
    return f'<td class="col-pct heat heat-{color}{glow}" style="--heat:{intensity:.3f}">{pct:.1f}%</td>'


def range_bar(t):
    lo, hi, exp = t["p5"], t["p95"], t["expected"]
    lo_pct = 100 * lo / SCALE_MAX
    hi_pct = 100 * hi / SCALE_MAX
    exp_pct = 100 * exp / SCALE_MAX
    width_pct = hi_pct - lo_pct
    return f'''<div class="rangebar" role="img" aria-label="90% confidence range {lo} to {hi}, expected {exp}">
      <div class="rangebar-track"></div>
      <div class="rangebar-band" style="left:{lo_pct:.2f}%;width:{width_pct:.2f}%"></div>
      <div class="rangebar-tick" style="left:{exp_pct:.2f}%"></div>
    </div>'''


def expected_delta_chip(team, new_expected, baseline_by_team):
    b = baseline_by_team.get(team)
    if not b:
        return '<span class="team-delta delta-neutral">new</span>'
    delta = new_expected - b["expected"]
    sign = "+" if delta >= 0 else ""
    cls = "delta-pos" if delta > 0.05 else ("delta-neg" if delta < -0.05 else "delta-neutral")
    return f'<span class="team-delta {cls}">{sign}{delta:.1f}</span>'


DETAIL_COLSPAN = 14  # col-rank + col-team + col-lineup + col-range + 10 place columns


def wrestler_detail_rows(lineup_detail):
    rows = []
    for w in lineup_detail:
        if w["rank"] is not None:
            rank_cell = f'{w["rank"]}'
            name_cell = w["name"]
        else:
            rank_cell = '<span class="unranked">unranked</span>'
            name_cell = '<span class="unranked">&mdash; (fallback estimate)</span>'
        rows.append(f'''<tr>
          <td class="wd-weight">{w['weight']}</td>
          <td class="wd-name">{name_cell}</td>
          <td class="wd-rank">{rank_cell}</td>
          <td class="wd-expected">{w['expected']:.1f}</td>
          <td class="wd-range">{w['p5']:.1f}&ndash;{w['p95']:.1f}</td>
        </tr>''')
    return "".join(rows)


def build_tbody(date: str, adjusted: dict, baseline_by_team: dict) -> str:
    teams = adjusted["teams"]
    rows_html = []
    for i, t in enumerate(teams, start=1):
        place_cells = "".join(heat_cell(t["p_place"][str(p)], p) for p in range(1, 11))
        medal_class = MEDAL.get(i, "")
        trophy = '<span class="trophy" aria-hidden="true">&#127942;</span> ' if i == 1 else ""
        rows_html.append(f'''
    <tr class="team-row" onclick="toggleDetail(this)">
      <td class="col-rank {medal_class}">{i}</td>
      <td class="col-team">
        <span class="expand-caret" aria-hidden="true">&#9656;</span>
        {trophy}<span class="team-name">{t['team']}</span>
        {expected_delta_chip(t['team'], t['expected'], baseline_by_team)}
      </td>
      <td class="col-lineup"><span class="lineup-chip">{t['lineup_size']}<span class="lineup-of10">/10</span></span></td>
      <td class="col-range">{range_bar(t)}<div class="range-labels"><span>{t['p5']:.0f}</span><span class="range-expected">{t['expected']:.0f}</span><span>{t['p95']:.0f}</span></div></td>
      {place_cells}
    </tr>
    <tr class="detail-row" hidden>
      <td colspan="{DETAIL_COLSPAN}">
        <div class="detail-wrap">
          <table class="detail-table">
            <thead><tr><th>Wt</th><th>Wrestler</th><th>Rank</th><th>Expected</th><th>90% range</th></tr></thead>
            <tbody>{wrestler_detail_rows(t['lineup_detail'])}</tbody>
          </table>
        </div>
      </td>
    </tr>''')
    return f'<tbody class="date-panel" data-date="{date}">{"".join(rows_html)}</tbody>'


def discover_dates():
    """Find every (date, adjusted_path, baseline_path) touch point we have a
    simulation for, newest first. Adding a new scraped date + simulation run
    later is all it takes for it to show up here automatically."""
    found = []
    for path in COMBINED_DIR.glob("team_score_simulation_adjusted_*.json"):
        m = re.match(r"team_score_simulation_adjusted_(\d{4}-\d{2}-\d{2})\.json$", path.name)
        if not m:
            continue
        date = m.group(1)
        baseline_path = COMBINED_DIR / f"team_score_simulation_{date}.json"
        if baseline_path.exists():
            found.append((date, path, baseline_path))
    found.sort(key=lambda x: x[0], reverse=True)
    return found


date_entries = discover_dates()
if not date_entries:
    raise SystemExit("No team_score_simulation_adjusted_*.json files found -- run simulate_team_scores.py first")

tbody_blocks = []
option_blocks = []

for i, (date, adj_path, base_path) in enumerate(date_entries):
    adjusted = json.loads(adj_path.read_text())
    baseline = json.loads(base_path.read_text())
    baseline_by_team = {t["team"]: t for t in baseline["teams"]}
    tbody_blocks.append(build_tbody(date, adjusted, baseline_by_team))

    label = datetime.strptime(date, "%Y-%m-%d").strftime("%b %-d, %Y")
    selected = " selected" if i == 0 else ""
    option_blocks.append(f'<option value="{date}"{selected}>{label}</option>')

newest_date = date_entries[0][0]

tbody_joined = "\n".join(tbody_blocks)
options_joined = "\n            ".join(option_blocks)
place_headers = "".join(f'<th class="col-pct">{p}{"st" if p==1 else "nd" if p==2 else "rd" if p==3 else "th"}</th>' for p in range(1, 11))

html = f'''<title>2026-27 NCAA Wrestling Odds -- Program-Strength Adjusted</title>
<style>
:root {{
  --bg: #F2F6F4; --surface: #FFFFFF; --surface-2: #EAF0EE; --ink: #12211D; --ink-dim: #55685F;
  --border: #D9E3DE; --teal: #1E4A44; --teal-ink: #EAF3F0; --gold: #B9832A;
  --shadow: 0 1px 2px rgba(18,33,29,0.06), 0 8px 24px rgba(18,33,29,0.06);
  --up: #2E7D4F; --down: #B23B3B;
  --heat-h: 142; --heat-s-lo: 8%; --heat-s-hi: 66%; --heat-l-lo: 93%; --heat-l-hi: 42%;
  --gold-h: 42; --gold-s-lo: 10%; --gold-s-hi: 80%; --gold-l-lo: 93%; --gold-l-hi: 48%;
  --silver-h: 205; --silver-s-lo: 5%; --silver-s-hi: 14%; --silver-l-lo: 93%; --silver-l-hi: 56%;
  --bronze-h: 22; --bronze-s-lo: 10%; --bronze-s-hi: 62%; --bronze-l-lo: 92%; --bronze-l-hi: 44%;
  --gold-rgb: 185, 131, 42; --silver-rgb: 120, 130, 128; --bronze-rgb: 166, 106, 58;
  --band-fill: #5C9C8F;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #0B1512; --surface: #13211D; --surface-2: #182C26; --ink: #E7F1ED; --ink-dim: #91A79E;
    --border: #223832; --teal: #143430; --teal-ink: #E7F1ED; --gold: #E0B15C;
    --shadow: 0 1px 2px rgba(0,0,0,0.3), 0 8px 24px rgba(0,0,0,0.35);
    --up: #5FBF87; --down: #E17575;
    --heat-h: 142; --heat-s-lo: 6%; --heat-s-hi: 56%; --heat-l-lo: 17%; --heat-l-hi: 46%;
    --gold-h: 42; --gold-s-lo: 8%; --gold-s-hi: 62%; --gold-l-lo: 17%; --gold-l-hi: 48%;
    --silver-h: 205; --silver-s-lo: 4%; --silver-s-hi: 14%; --silver-l-lo: 17%; --silver-l-hi: 50%;
    --bronze-h: 22; --bronze-s-lo: 8%; --bronze-s-hi: 56%; --bronze-l-lo: 17%; --bronze-l-hi: 44%;
    --gold-rgb: 224, 177, 92; --silver-rgb: 168, 178, 176; --bronze-rgb: 210, 145, 95;
    --band-fill: #3A7A6D;
  }}
}}
:root[data-theme="dark"] {{
  --bg: #0B1512; --surface: #13211D; --surface-2: #182C26; --ink: #E7F1ED; --ink-dim: #91A79E;
  --border: #223832; --teal: #143430; --teal-ink: #E7F1ED; --gold: #E0B15C;
  --shadow: 0 1px 2px rgba(0,0,0,0.3), 0 8px 24px rgba(0,0,0,0.35);
  --up: #5FBF87; --down: #E17575;
  --heat-h: 142; --heat-s-lo: 6%; --heat-s-hi: 56%; --heat-l-lo: 17%; --heat-l-hi: 46%;
  --gold-h: 42; --gold-s-lo: 8%; --gold-s-hi: 62%; --gold-l-lo: 17%; --gold-l-hi: 48%;
  --silver-h: 205; --silver-s-lo: 4%; --silver-s-hi: 14%; --silver-l-lo: 17%; --silver-l-hi: 50%;
  --bronze-h: 22; --bronze-s-lo: 8%; --bronze-s-hi: 56%; --bronze-l-lo: 17%; --bronze-l-hi: 44%;
  --gold-rgb: 224, 177, 92; --silver-rgb: 168, 178, 176; --bronze-rgb: 210, 145, 95;
  --band-fill: #3A7A6D;
}}
:root[data-theme="light"] {{
  --bg: #F2F6F4; --surface: #FFFFFF; --surface-2: #EAF0EE; --ink: #12211D; --ink-dim: #55685F;
  --border: #D9E3DE; --teal: #1E4A44; --teal-ink: #EAF3F0; --gold: #B9832A;
  --shadow: 0 1px 2px rgba(18,33,29,0.06), 0 8px 24px rgba(18,33,29,0.06);
  --up: #2E7D4F; --down: #B23B3B;
  --heat-h: 142; --heat-s-lo: 8%; --heat-s-hi: 66%; --heat-l-lo: 93%; --heat-l-hi: 42%;
  --gold-h: 42; --gold-s-lo: 10%; --gold-s-hi: 80%; --gold-l-lo: 93%; --gold-l-hi: 48%;
  --silver-h: 205; --silver-s-lo: 5%; --silver-s-hi: 14%; --silver-l-lo: 93%; --silver-l-hi: 56%;
  --bronze-h: 22; --bronze-s-lo: 10%; --bronze-s-hi: 62%; --bronze-l-lo: 92%; --bronze-l-hi: 44%;
  --gold-rgb: 185, 131, 42; --silver-rgb: 120, 130, 128; --bronze-rgb: 166, 106, 58;
  --band-fill: #5C9C8F;
}}

* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; }}
body {{
  background: var(--bg); color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased; line-height: 1.45;
}}
.wrap {{ max-width: 1280px; margin: 0 auto; padding: 0 20px 64px; }}

.header {{
  position: relative;
  background:
    radial-gradient(circle at 88% 12%, rgba(var(--gold-rgb), 0.16), transparent 42%),
    repeating-linear-gradient(135deg, rgba(255,255,255,0.025) 0 2px, transparent 2px 26px),
    linear-gradient(180deg, var(--teal), color-mix(in srgb, var(--teal) 82%, black));
  color: var(--teal-ink); padding: 40px 20px 32px; margin-bottom: 28px;
  overflow: hidden;
}}
.header::after {{
  content: "";
  position: absolute; right: -60px; top: 50%; transform: translateY(-50%);
  width: 260px; height: 260px; border-radius: 50%;
  border: 1.5px solid rgba(var(--gold-rgb), 0.18);
  pointer-events: none;
}}
.header-inner {{ position: relative; max-width: 1280px; margin: 0 auto; }}
.header-top {{ display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: 16px; }}
.eyebrow {{ text-transform: uppercase; letter-spacing: 0.14em; font-size: 12px; font-weight: 700; color: var(--gold); margin: 0 0 10px; }}
h1 {{ font-size: clamp(26px, 3.6vw, 38px); font-weight: 800; letter-spacing: -0.02em; margin: 0 0 10px; text-wrap: balance; }}
.header-meta {{ display: flex; flex-wrap: wrap; gap: 6px 22px; font-size: 14px; color: color-mix(in srgb, var(--teal-ink) 78%, transparent); margin-top: 14px; }}
.header-meta strong {{ color: var(--teal-ink); font-variant-numeric: tabular-nums; }}

.date-picker {{ display: flex; flex-direction: column; gap: 5px; }}
.date-picker label {{
  text-transform: uppercase; letter-spacing: 0.1em; font-size: 10.5px; font-weight: 700;
  color: color-mix(in srgb, var(--teal-ink) 70%, transparent);
}}
.date-picker select {{
  appearance: none; -webkit-appearance: none;
  background: color-mix(in srgb, var(--teal-ink) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--teal-ink) 28%, transparent);
  color: var(--teal-ink); font-weight: 700; font-size: 14px;
  padding: 9px 34px 9px 14px; border-radius: 7px; cursor: pointer;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23EAF3F0'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-position: right 14px center;
}}
.date-picker select:focus-visible {{ outline: 2px solid var(--gold); outline-offset: 2px; }}
.date-picker select option {{ color: #12211D; }}

.callout {{
  background: var(--surface); border: 1px solid var(--border); border-left: 3px solid var(--gold);
  border-radius: 6px; padding: 16px 18px; font-size: 13.5px; color: var(--ink-dim); margin-bottom: 28px;
}}
.callout strong {{ color: var(--ink); }}
.callout p {{ margin: 0 0 8px; }}
.callout p:last-child {{ margin-bottom: 0; }}
.example {{
  display: inline-flex; align-items: center; gap: 6px; margin-top: 6px;
  font-family: ui-monospace, "SF Mono", "Cascadia Code", Consolas, monospace; font-size: 12.5px;
  background: var(--surface-2); padding: 4px 10px; border-radius: 5px; color: var(--ink);
}}

.table-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; box-shadow: var(--shadow); overflow: hidden; }}
.table-scroll {{ overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; min-width: 1180px; }}
thead th {{
  position: sticky; top: 0; background: var(--surface-2); text-align: left; font-size: 11px;
  text-transform: uppercase; letter-spacing: 0.08em; color: var(--ink-dim); font-weight: 700;
  padding: 12px 10px; border-bottom: 1px solid var(--border); white-space: nowrap;
}}
th.col-pct, th.col-rank {{ text-align: center; }}
tbody td {{ padding: 10px 10px; border-bottom: 1px solid var(--border); font-size: 14px; vertical-align: middle; color: var(--ink); }}
tbody tr:last-child td {{ border-bottom: none; }}
tbody tr:hover td {{ background: color-mix(in srgb, var(--surface-2) 55%, transparent); }}
tbody.date-panel[hidden] {{ display: none; }}

.col-rank {{ text-align: center; font-variant-numeric: tabular-nums; color: var(--ink-dim); font-size: 13px; width: 34px; font-weight: 600; }}
.col-rank.medal-gold {{ color: rgb(var(--gold-rgb)); font-size: 15px; font-weight: 800; }}
.col-rank.medal-silver {{ color: rgb(var(--silver-rgb)); font-weight: 800; }}
.col-rank.medal-bronze {{ color: rgb(var(--bronze-rgb)); font-weight: 800; }}

.col-team {{ font-weight: 600; min-width: 160px; }}
.team-name {{ font-weight: 600; color: var(--ink); }}
.trophy {{ filter: saturate(1.15); }}
.team-delta {{
  display: block; font-family: ui-monospace, "SF Mono", "Cascadia Code", Consolas, monospace;
  font-size: 11px; font-weight: 700; margin-top: 1px;
}}
.delta-pos {{ color: var(--up); }}
.delta-neg {{ color: var(--down); }}
.delta-neutral {{ color: var(--ink-dim); }}

.team-row {{ cursor: pointer; }}
.expand-caret {{
  display: inline-block; width: 10px; color: var(--ink-dim); font-size: 10px;
  transition: transform 0.15s ease; transform-origin: 45% 50%;
}}
.team-row.expanded .expand-caret {{ transform: rotate(90deg); }}
.team-row.expanded td {{ background: color-mix(in srgb, var(--surface-2) 70%, transparent); }}

.detail-row td {{ padding: 0; border-bottom: 1px solid var(--border); }}
.detail-wrap {{ background: var(--bg); padding: 10px 14px 12px 42px; }}
.detail-table {{
  width: auto; min-width: 460px; border-collapse: collapse;
  font-size: 12px; font-family: ui-monospace, "SF Mono", "Cascadia Code", Consolas, monospace;
}}
.detail-table thead th {{
  position: static; background: transparent; padding: 3px 12px 5px 0; font-size: 9.5px;
  text-transform: uppercase; letter-spacing: 0.07em; color: var(--ink-dim); font-weight: 700;
  border-bottom: 1px solid var(--border); text-align: left;
}}
.detail-table tbody td {{
  padding: 4px 12px 4px 0; border-bottom: 1px dashed color-mix(in srgb, var(--border) 70%, transparent);
  font-size: 12px; color: var(--ink-dim); font-variant-numeric: tabular-nums;
}}
.detail-table tbody tr:last-child td {{ border-bottom: none; }}
.detail-table tbody tr:hover td {{ background: transparent; }}
.wd-name {{ color: var(--ink); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; font-weight: 500; }}
.wd-expected {{ color: var(--ink); font-weight: 700; }}
.unranked {{ font-style: italic; opacity: 0.75; }}

.lineup-chip {{ font-family: ui-monospace, "SF Mono", "Cascadia Code", Consolas, monospace; font-size: 12.5px; font-weight: 600; color: var(--ink-dim); font-variant-numeric: tabular-nums; }}
.lineup-of10 {{ color: color-mix(in srgb, var(--ink-dim) 60%, transparent); font-weight: 500; }}

.col-range {{ min-width: 230px; }}
.rangebar {{ position: relative; height: 8px; margin: 4px 0 5px; }}
.rangebar-track {{
  position: absolute; inset: 0; background: var(--surface-2); border-radius: 4px;
  background-image: repeating-linear-gradient(90deg, var(--border) 0 1px, transparent 1px 25%);
}}
.rangebar-band {{ position: absolute; top: 0; bottom: 0; background: var(--band-fill); border-radius: 4px; }}
.rangebar-tick {{ position: absolute; top: -4px; width: 2px; height: 16px; background: var(--gold); transform: translateX(-1px); border-radius: 1px; box-shadow: 0 0 0 1px rgba(0,0,0,0.15); }}
.range-labels {{ display: flex; justify-content: space-between; font-family: ui-monospace, "SF Mono", "Cascadia Code", Consolas, monospace; font-size: 11px; color: var(--ink-dim); font-variant-numeric: tabular-nums; }}
.range-expected {{ color: var(--ink); font-weight: 700; }}

.col-pct {{
  text-align: center; font-family: ui-monospace, "SF Mono", "Cascadia Code", Consolas, monospace;
  font-variant-numeric: tabular-nums; font-weight: 600; min-width: 58px; color: var(--ink);
}}
.heat {{ transition: background 0.15s ease; }}
.heat-green {{
  background: hsl(var(--heat-h) calc(var(--heat-s-lo) + (var(--heat-s-hi) - var(--heat-s-lo)) * var(--heat)) calc(var(--heat-l-lo) - (var(--heat-l-lo) - var(--heat-l-hi)) * var(--heat)));
}}
.heat-green.hot {{
  color: color-mix(in srgb, var(--ink) 88%, white 12%);
  box-shadow: inset 0 0 0 1px rgba(var(--gold-rgb), calc((var(--heat) - 0.6) * 0.5));
}}
.heat-gold {{ background: hsl(var(--gold-h) calc(var(--gold-s-lo) + (var(--gold-s-hi) - var(--gold-s-lo)) * var(--heat)) calc(var(--gold-l-lo) - (var(--gold-l-lo) - var(--gold-l-hi)) * var(--heat))); }}
.heat-silver {{ background: hsl(var(--silver-h) calc(var(--silver-s-lo) + (var(--silver-s-hi) - var(--silver-s-lo)) * var(--heat)) calc(var(--silver-l-lo) - (var(--silver-l-lo) - var(--silver-l-hi)) * var(--heat))); }}
.heat-bronze {{ background: hsl(var(--bronze-h) calc(var(--bronze-s-lo) + (var(--bronze-s-hi) - var(--bronze-s-lo)) * var(--heat)) calc(var(--bronze-l-lo) - (var(--bronze-l-lo) - var(--bronze-l-hi)) * var(--heat))); }}

.legend {{ display: flex; flex-wrap: wrap; align-items: center; gap: 18px; font-size: 12px; color: var(--ink-dim); margin: 14px 2px 0; }}
.legend-item {{ display: flex; align-items: center; gap: 7px; }}
.legend-swatch {{
  display: inline-block; width: 70px; height: 10px; border-radius: 4px;
  background: linear-gradient(90deg,
    hsl(var(--heat-h) var(--heat-s-lo) var(--heat-l-lo)) 0%,
    hsl(var(--heat-h) var(--heat-s-hi) var(--heat-l-hi)) 100%);
}}
.legend-swatch-gold {{ background: linear-gradient(90deg, rgba(var(--gold-rgb),0.08) 0%, rgba(var(--gold-rgb),0.58) 100%); }}
.legend-swatch-silver {{ background: linear-gradient(90deg, rgba(var(--silver-rgb),0.08) 0%, rgba(var(--silver-rgb),0.58) 100%); }}
.legend-swatch-bronze {{ background: linear-gradient(90deg, rgba(var(--bronze-rgb),0.08) 0%, rgba(var(--bronze-rgb),0.58) 100%); }}

footer {{ margin-top: 28px; font-size: 12.5px; color: var(--ink-dim); }}
footer code {{ font-family: ui-monospace, "SF Mono", "Cascadia Code", Consolas, monospace; background: var(--surface-2); padding: 1px 5px; border-radius: 4px; }}
footer p {{ margin: 0 0 8px; }}
footer p:last-child {{ margin-bottom: 0; }}

@media (max-width: 640px) {{
  .header {{ padding: 28px 16px 24px; }}
}}
</style>

<div class="header">
  <div class="header-inner">
    <div class="header-top">
      <div>
        <h1>2026&ndash;27 NCAA D1 Wrestling &mdash; Championship Odds</h1>
      </div>
      <div class="date-picker">
        <label for="dateSelect">Rankings date</label>
        <select id="dateSelect" onchange="showDate(this.value)">
            {options_joined}
        </select>
      </div>
    </div>
  </div>
</div>

<div class="wrap">
  <div class="table-card">
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th class="col-rank">#</th>
            <th class="col-team">Team</th>
            <th class="col-lineup">Ranked</th>
            <th class="col-range">Scoring Range</th>
            {place_headers}
          </tr>
        </thead>
        {tbody_joined}
      </table>
    </div>
  </div>

  <div class="legend">
    <div class="legend-item"><span class="legend-swatch legend-swatch-gold" aria-hidden="true"></span><span>1st</span></div>
    <div class="legend-item"><span class="legend-swatch legend-swatch-silver" aria-hidden="true"></span><span>2nd</span></div>
    <div class="legend-item"><span class="legend-swatch legend-swatch-bronze" aria-hidden="true"></span><span>3rd &amp; 4th (trophy tier)</span></div>
    <div class="legend-item"><span class="legend-swatch" aria-hidden="true"></span><span>5th&ndash;10th</span></div>
    <div class="legend-item"><span>Cells under 10% are left blank &mdash; not a realistic finish</span></div>
  </div>

  <div class="callout">
    <p><strong>What this shows:</strong> each team's score is shifted by their historical seed-relative over/underperformance &mdash; on average, how many more or fewer points that program's wrestlers scored than the league-wide average wrestler holding the <em>same seed</em>, across 2023&ndash;2026. The number under each team name is how much this moved their expected score vs. the unadjusted base projection.</p>
    <p class="example">Penn State: +24.9 &mdash; their wrestlers have historically outscored the league average at their seed by +2.49&nbsp;pts each, compounded across a 10-man lineup.</p>
  </div>

  <footer>
    <p><strong>Scoring Range</strong> is the middle 90% of outcomes across 10,000 simulated tournaments for that team (5th&ndash;95th percentile), not the single most extreme best/worst case &mdash; shown on a fixed 0&ndash;200 scale for every team so ranges are directly comparable, with a tick mark at the expected (mean) score.</p>
    <p>Built from FloWrestling's rankings snapshots, 2023&ndash;2026 NCAA D1 Championship results, and each program's seed-relative scoring history (min. 5 wrestler-seasons to trust an offset, else neutral).
    Scripts: <code>compute_team_seed_offsets.py</code> &middot; <code>simulate_team_scores.py --team-offsets</code>.</p>
  </footer>
</div>

<script>
  function showDate(date) {{
    document.querySelectorAll('tbody.date-panel').forEach(tb => {{
      tb.hidden = tb.dataset.date !== date;
    }});
  }}
  function toggleDetail(row) {{
    const detail = row.nextElementSibling;
    const opening = detail.hidden;
    detail.hidden = !opening;
    row.classList.toggle('expanded', opening);
  }}
  showDate('{newest_date}');
</script>
'''

out_path = PROJECT_ROOT / "scratch" / "team_odds_page2_adjusted.html"
out_path.write_text(html)
print(f"wrote {out_path} ({len(html)} bytes, {len(date_entries)} date(s): {[d for d,_,_ in date_entries]})")
