#!/usr/bin/env python3
"""Generates a static HTML dashboard from team_score_simulation.json."""
import json
from pathlib import Path

PROJECT_ROOT = Path("/Users/tjthompson/Documents/Cursor/wrestledata-simple")
sim = json.loads((PROJECT_ROOT / "data/ncaa-tourney-parsed/team_score_simulation.json").read_text())
rankings = json.loads(Path(sim["rankings_file"]).read_text())

teams = sim["teams"]
max_score = max(t["max"] for t in teams)

def heat_style(pct):
    # 0-100 -> tint intensity var used by CSS (0..1)
    intensity = max(0.0, min(1.0, pct / 100))
    return f'style="--heat:{intensity:.3f}"'

def range_bar(t):
    lo, hi, exp = t["min"], t["max"], t["expected"]
    lo_pct = 100 * lo / max_score
    hi_pct = 100 * hi / max_score
    exp_pct = 100 * exp / max_score
    width_pct = hi_pct - lo_pct
    return f'''<div class="rangebar" role="img" aria-label="Score range {lo} to {hi}, expected {exp}">
      <div class="rangebar-track"></div>
      <div class="rangebar-fill" style="left:{lo_pct:.2f}%;width:{width_pct:.2f}%"></div>
      <div class="rangebar-tick" style="left:{exp_pct:.2f}%"></div>
    </div>'''

rows_html = []
for i, t in enumerate(teams, start=1):
    is_leader = i == 1
    leader_class = " leader" if is_leader else ""
    crown = '<span class="crown" aria-hidden="true">&#9819;</span> ' if is_leader else ""
    rows_html.append(f'''
    <tr class="{leader_class.strip()}">
      <td class="col-rank">{i}</td>
      <td class="col-team">{crown}<span class="team-name">{t['team']}</span></td>
      <td class="col-lineup"><span class="lineup-chip" title="{t['lineup_size']} of 10 weight classes have a nationally-ranked wrestler">{t['lineup_size']}<span class="lineup-of10">/10</span></span></td>
      <td class="col-range">{range_bar(t)}<div class="range-labels"><span>{t['min']:.0f}</span><span class="range-expected">{t['expected']:.0f}</span><span>{t['max']:.0f}</span></div></td>
      <td class="col-pct heat" {heat_style(t['p_1st'])}>{t['p_1st']:.1f}%</td>
      <td class="col-pct heat" {heat_style(t['p_top3'])}>{t['p_top3']:.1f}%</td>
      <td class="col-pct heat" {heat_style(t['p_top5'])}>{t['p_top5']:.1f}%</td>
      <td class="col-pct heat" {heat_style(t['p_top10'])}>{t['p_top10']:.1f}%</td>
    </tr>''')

rows_joined = "\n".join(rows_html)
ranking_date = rankings["ranking_date"]
season = rankings.get("season")
trials = sim["trials"]
month = sim["month"]

html = f'''<title>2026-27 NCAA D1 Wrestling Championship Odds</title>
<style>
:root {{
  --bg: #F2F6F4;
  --surface: #FFFFFF;
  --surface-2: #EAF0EE;
  --ink: #12211D;
  --ink-dim: #55685F;
  --border: #D9E3DE;
  --teal: #1E4A44;
  --teal-ink: #EAF3F0;
  --gold: #B9832A;
  --gold-soft: #F3E4C6;
  --heat-rgb: 30, 74, 68;
  --shadow: 0 1px 2px rgba(18,33,29,0.06), 0 8px 24px rgba(18,33,29,0.06);
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #0B1512;
    --surface: #13211D;
    --surface-2: #182C26;
    --ink: #E7F1ED;
    --ink-dim: #91A79E;
    --border: #223832;
    --teal: #143430;
    --teal-ink: #E7F1ED;
    --gold: #E0B15C;
    --gold-soft: #3A2E15;
    --heat-rgb: 224, 177, 92;
    --shadow: 0 1px 2px rgba(0,0,0,0.3), 0 8px 24px rgba(0,0,0,0.35);
  }}
}}
:root[data-theme="dark"] {{
  --bg: #0B1512; --surface: #13211D; --surface-2: #182C26; --ink: #E7F1ED; --ink-dim: #91A79E;
  --border: #223832; --teal: #143430; --teal-ink: #E7F1ED; --gold: #E0B15C; --gold-soft: #3A2E15;
  --heat-rgb: 224, 177, 92; --shadow: 0 1px 2px rgba(0,0,0,0.3), 0 8px 24px rgba(0,0,0,0.35);
}}
:root[data-theme="light"] {{
  --bg: #F2F6F4; --surface: #FFFFFF; --surface-2: #EAF0EE; --ink: #12211D; --ink-dim: #55685F;
  --border: #D9E3DE; --teal: #1E4A44; --teal-ink: #EAF3F0; --gold: #B9832A; --gold-soft: #F3E4C6;
  --heat-rgb: 30, 74, 68; --shadow: 0 1px 2px rgba(18,33,29,0.06), 0 8px 24px rgba(18,33,29,0.06);
}}

* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; }}
body {{
  background: var(--bg);
  color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  line-height: 1.45;
}}
.wrap {{ max-width: 1100px; margin: 0 auto; padding: 0 20px 64px; }}

.header {{
  background: linear-gradient(180deg, var(--teal), color-mix(in srgb, var(--teal) 82%, black));
  color: var(--teal-ink);
  padding: 40px 20px 32px;
  margin-bottom: 28px;
}}
.header-inner {{ max-width: 1100px; margin: 0 auto; }}
.eyebrow {{
  text-transform: uppercase;
  letter-spacing: 0.14em;
  font-size: 12px;
  font-weight: 700;
  color: var(--gold);
  margin: 0 0 10px;
}}
h1 {{
  font-size: clamp(28px, 4vw, 40px);
  font-weight: 800;
  letter-spacing: -0.02em;
  margin: 0 0 10px;
  text-wrap: balance;
}}
.header-meta {{
  display: flex;
  flex-wrap: wrap;
  gap: 6px 22px;
  font-size: 14px;
  color: color-mix(in srgb, var(--teal-ink) 78%, transparent);
  margin-top: 14px;
}}
.header-meta strong {{ color: var(--teal-ink); font-variant-numeric: tabular-nums; }}

.caveat {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-left: 3px solid var(--gold);
  border-radius: 6px;
  padding: 14px 18px;
  font-size: 13.5px;
  color: var(--ink-dim);
  margin-bottom: 28px;
}}
.caveat strong {{ color: var(--ink); }}

.table-card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: var(--shadow);
  overflow: hidden;
}}
.table-scroll {{ overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; min-width: 800px; }}
thead th {{
  position: sticky; top: 0;
  background: var(--surface-2);
  text-align: left;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--ink-dim);
  font-weight: 700;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}}
th.col-pct, th.col-rank {{ text-align: center; }}
tbody td {{
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  font-size: 14px;
  vertical-align: middle;
}}
tbody tr:last-child td {{ border-bottom: none; }}
tbody tr:hover td {{ background: color-mix(in srgb, var(--surface-2) 60%, transparent); }}
tr.leader td {{ background: color-mix(in srgb, var(--gold-soft) 55%, transparent); }}
tr.leader:hover td {{ background: var(--gold-soft); }}

.col-rank {{
  text-align: center;
  font-variant-numeric: tabular-nums;
  color: var(--ink-dim);
  font-size: 13px;
  width: 36px;
}}
.col-team {{ font-weight: 600; min-width: 150px; }}
.crown {{ color: var(--gold); }}
.team-name {{ font-weight: 600; }}

.lineup-chip {{
  font-family: ui-monospace, "SF Mono", "Cascadia Code", Consolas, monospace;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--ink-dim);
  font-variant-numeric: tabular-nums;
}}
.lineup-of10 {{ color: color-mix(in srgb, var(--ink-dim) 60%, transparent); font-weight: 500; }}

.col-range {{ min-width: 190px; }}
.rangebar {{ position: relative; height: 6px; margin: 4px 0 5px; }}
.rangebar-track {{
  position: absolute; inset: 0;
  background: var(--surface-2);
  border-radius: 3px;
}}
.rangebar-fill {{
  position: absolute; top: 0; bottom: 0;
  background: color-mix(in srgb, var(--teal) 55%, var(--surface-2));
  border-radius: 3px;
}}
.rangebar-tick {{
  position: absolute; top: -3px;
  width: 2px; height: 12px;
  background: var(--gold);
  transform: translateX(-1px);
  border-radius: 1px;
}}
.range-labels {{
  display: flex; justify-content: space-between;
  font-family: ui-monospace, "SF Mono", "Cascadia Code", Consolas, monospace;
  font-size: 11px;
  color: var(--ink-dim);
  font-variant-numeric: tabular-nums;
}}
.range-expected {{ color: var(--ink); font-weight: 700; }}

.col-pct {{
  text-align: center;
  font-family: ui-monospace, "SF Mono", "Cascadia Code", Consolas, monospace;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  min-width: 78px;
}}
.heat {{
  background: rgba(var(--heat-rgb), calc(var(--heat) * 0.42));
}}

.legend {{
  display: flex; align-items: center; gap: 10px;
  font-size: 12px; color: var(--ink-dim);
  margin: 14px 2px 0;
}}
.legend-swatch {{
  display: inline-block; width: 60px; height: 8px; border-radius: 4px;
  background: linear-gradient(90deg, rgba(var(--heat-rgb),0), rgba(var(--heat-rgb),0.42));
}}

footer {{
  margin-top: 28px;
  font-size: 12.5px;
  color: var(--ink-dim);
}}
footer code {{
  font-family: ui-monospace, "SF Mono", "Cascadia Code", Consolas, monospace;
  background: var(--surface-2);
  padding: 1px 5px;
  border-radius: 4px;
}}

@media (max-width: 640px) {{
  .header {{ padding: 28px 16px 24px; }}
  .col-range {{ min-width: 150px; }}
}}
</style>

<div class="header">
  <div class="header-inner">
    <p class="eyebrow">Preseason Projection</p>
    <h1>2026&ndash;27 NCAA D1 Wrestling &mdash; Team Championship Odds</h1>
    <div class="header-meta">
      <span>Rankings snapshot: <strong>{ranking_date}</strong> ({month} touch point)</span>
      <span>Simulated trials: <strong>{trials:,}</strong></span>
      <span>Teams tracked: <strong>{len(teams)}</strong></span>
    </div>
  </div>
</div>

<div class="wrap">
  <div class="caveat">
    <strong>How to read this:</strong> each team's score range comes from 10,000 Monte&nbsp;Carlo simulated tournaments, drawing from the actual historical scoring distribution of wrestlers ranked at each weight&nbsp;class position (2023&ndash;2026 NCAA results). Weight classes where a team has no nationally-ranked wrestler use a generic low-rank fallback &mdash; teams with strong unranked depth (like perennial contenders replacing an injured starter) are likely underrated here until that's modeled directly.
  </div>

  <div class="table-card">
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th class="col-rank">#</th>
            <th class="col-team">Team</th>
            <th class="col-lineup">Ranked</th>
            <th class="col-range">Score range (min &middot; expected &middot; max)</th>
            <th class="col-pct">1st</th>
            <th class="col-pct">Top&nbsp;3</th>
            <th class="col-pct">Top&nbsp;5</th>
            <th class="col-pct">Top&nbsp;10</th>
          </tr>
        </thead>
        <tbody>
          {rows_joined}
        </tbody>
      </table>
    </div>
  </div>

  <div class="legend">
    <span class="legend-swatch" aria-hidden="true"></span>
    <span>Cell shading = probability intensity (darker = more likely)</span>
  </div>

  <footer>
    Built from FloWrestling's {ranking_date} rankings snapshot and 2023&ndash;2026 NCAA D1 Championship results.
    Simulation: <code>scripts/analysis/simulate_team_scores.py</code> &middot;
    Distributions: <code>scripts/analysis/build_rank_score_distributions.py</code> (recentered &plusmn;1-rank blend).
  </footer>
</div>
'''

out_path = PROJECT_ROOT / "scratch" / "team_odds_page.html"
out_path.write_text(html)
print(f"wrote {out_path} ({len(html)} bytes, {len(teams)} teams)")
