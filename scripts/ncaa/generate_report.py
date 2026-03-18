#!/usr/bin/env python3
"""
NCAA D1 Wrestling Tournament Analytical Report
Generates two self-contained HTML pages:
  ncaa_report.html       — overall analytical report
  ncaa_team_report.html  — interactive team comparison tool

Usage:
  python scripts/ncaa/generate_report.py
"""

import argparse
import json
import statistics
from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
COMBINED_DIR = DATA_DIR / "ncaa-tourney-parsed"
DEFAULT_OUT             = PROJECT_ROOT / "ncaa_report.html"
DEFAULT_TEAM_OUT        = PROJECT_ROOT / "ncaa_team_report.html"
DEFAULT_LEADERBOARD_OUT = PROJECT_ROOT / "ncaa_team_leaderboard.html"
DEFAULT_CONF_LB_OUT     = PROJECT_ROOT / "ncaa_conf_leaderboard.html"
DEFAULT_CONF_OUT        = PROJECT_ROOT / "ncaa_conf_analysis.html"
DEFAULT_BRACKET_OUT     = PROJECT_ROOT / "ncaa_bracket_odds.html"

# ---------------------------------------------------------------------------
# Team name normalization
# ---------------------------------------------------------------------------
TEAM_ALIASES: dict[str, str] = {
    # Appalachian State
    "Appalachian S.":              "Appalachian State",
    "Appalachian St.":             "Appalachian State",
    # Arizona State
    "Arizona St.":                 "Arizona State",
    # Army
    "Army West Point":             "Army",
    # CSU Bakersfield
    "Bakersfield":                 "CSU Bakersfield",
    "Csu Bakersfield":             "CSU Bakersfield",
    # Binghamton
    "Binghamton University":       "Binghamton",
    # Central Michigan
    "Central Mich.":               "Central Michigan",
    # Cleveland State
    "Cleveland St.":               "Cleveland State",
    # Eastern Michigan
    "Eastern Mich.":               "Eastern Michigan",
    # Franklin & Marshall
    "Frank. & Marsh.":             "Franklin & Marshall",
    "Franklin and Marshall":       "Franklin & Marshall",
    # Iowa State
    "Iowa St.":                    "Iowa State",
    # Kent State
    "Kent St.":                    "Kent State",
    # Michigan State
    "Michigan St.":                "Michigan State",
    # NC State
    "North Carolina St.":          "NC State",
    # North Dakota State
    "North Dakota St.":            "North Dakota State",
    "North Dakota State University": "North Dakota State",
    # Northern Colorado
    "Northern Colo.":              "Northern Colorado",
    # Northern Illinois
    "Northern Ill.":               "Northern Illinois",
    # Northern Iowa
    "UNI":                         "Northern Iowa",
    # Ohio State
    "Ohio St.":                    "Ohio State",
    # Oklahoma State
    "Oklahoma St.":                "Oklahoma State",
    # Oregon State
    "Oregon St.":                  "Oregon State",
    # Penn State
    "Penn St.":                    "Penn State",
    # Penn
    "Pennsylvania":                "Penn",
    # SIU Edwardsville
    "SIUE":                        "SIU Edwardsville",
    "Southern Illinois Edwardsville": "SIU Edwardsville",
    # South Dakota State
    "South Dakota St.":            "South Dakota State",
    # The Citadel
    "Citadel":                     "The Citadel",
    # Utah Valley
    "Utah Valley University":      "Utah Valley",
}


def normalize_team(name: str) -> str:
    return TEAM_ALIASES.get(name, name)


# ---------------------------------------------------------------------------
# Conference mapping (current 2025-26 alignment)
# None  = program no longer active in D1 wrestling
# ---------------------------------------------------------------------------
CONFERENCE_MAP: dict[str, str | None] = {
    # Big Ten (14)
    "Illinois": "Big Ten",      "Indiana": "Big Ten",       "Iowa": "Big Ten",
    "Maryland": "Big Ten",      "Michigan": "Big Ten",      "Michigan State": "Big Ten",
    "Minnesota": "Big Ten",     "Nebraska": "Big Ten",      "Northwestern": "Big Ten",
    "Ohio State": "Big Ten",    "Penn State": "Big Ten",    "Purdue": "Big Ten",
    "Rutgers": "Big Ten",       "Wisconsin": "Big Ten",

    # Big 12 (14) — Cal Poly and NC State are NOT in Big 12 wrestling
    "Air Force": "Big 12",          "Arizona State": "Big 12",      "California Baptist": "Big 12",
    "Iowa State": "Big 12",         "Missouri": "Big 12",           "North Dakota State": "Big 12",
    "Northern Colorado": "Big 12",  "Northern Iowa": "Big 12",      "Oklahoma": "Big 12",
    "Oklahoma State": "Big 12",     "South Dakota State": "Big 12", "Utah Valley": "Big 12",
    "West Virginia": "Big 12",      "Wyoming": "Big 12",

    # EIWA (11) — Ivy schools now have their own separate conference
    "American": "EIWA",     "Army": "EIWA",             "Binghamton": "EIWA",
    "Bucknell": "EIWA",     "Drexel": "EIWA",           "Franklin & Marshall": "EIWA",
    "Hofstra": "EIWA",      "Lehigh": "EIWA",           "LIU": "EIWA",
    "Navy": "EIWA",         "Sacred Heart": "EIWA",

    # MAC (12) — includes several historically paused programs still in conference
    "Bloomsburg": "MAC",        "Buffalo": "MAC",           "Central Michigan": "MAC",
    "Clarion": "MAC",           "Edinboro": "MAC",          "George Mason": "MAC",
    "Kent State": "MAC",        "Lock Haven": "MAC",        "Northern Illinois": "MAC",
    "Ohio": "MAC",              "Rider": "MAC",             "SIU Edwardsville": "MAC",

    # ACC (7)
    "Duke": "ACC",      "NC State": "ACC",      "North Carolina": "ACC",
    "Pittsburgh": "ACC","Stanford": "ACC",      "Virginia": "ACC",
    "Virginia Tech": "ACC",

    # SoCon (8 in dataset — Presbyterian not in data)
    "Appalachian State": "SoCon",   "Bellarmine": "SoCon",  "Campbell": "SoCon",
    "Chattanooga": "SoCon",         "Davidson": "SoCon",    "Gardner-Webb": "SoCon",
    "The Citadel": "SoCon",         "VMI": "SoCon",

    # Ivy League (6) — now a separate wrestling conference from EIWA
    "Brown": "Ivy League",  "Columbia": "Ivy League",   "Cornell": "Ivy League",
    "Harvard": "Ivy League","Penn": "Ivy League",        "Princeton": "Ivy League",

    # Pac-12 (4)
    "Cal Poly": "Pac-12",       "CSU Bakersfield": "Pac-12",
    "Little Rock": "Pac-12",    "Oregon State": "Pac-12",

    # Inactive programs — no longer competing in D1 wrestling
    "Boise State":      "Inactive",
    "Boston U.":        "Inactive",
    "Cleveland State":  "Inactive",
    "Eastern Michigan": "Inactive",
    "Fresno State":     "Inactive",
    "Old Dominion":     "Inactive",
}


def get_conference(team: str) -> str | None:
    return CONFERENCE_MAP.get(team, "Unassigned")


# ---------------------------------------------------------------------------
# Range midpoints for non-exact placements
# ---------------------------------------------------------------------------
RANGE_MIDPOINTS = {
    "C_PIG": 33.0,
    "C_R1":  28.5,   # 25–32
    "C_R2":  20.5,   # 17–24
    "C_R3":  14.5,   # 13–16
    "C_R4":  10.5,   # 9–12
}


def effective_placement(w: dict) -> float:
    if w["placement_exact"]:
        return float(w["placement"])
    return RANGE_MIDPOINTS.get(w["last_round"], float(w["placement"]))


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Seeding cutoffs by year
# Pre-2014: only top 12 were seeded; 13-33 randomly placed.
# 2014-2018: top 16 seeded; 17-33 randomly placed.
# 2019+:     all 33 seeded.
# ---------------------------------------------------------------------------
SEEDING_CUTOFF: dict[int, int] = {
    2013: 12,
    2014: 16, 2015: 16, 2016: 16, 2017: 16, 2018: 16,
}

def is_truly_seeded(w: dict) -> bool:
    """Return True if this wrestler's seed was an official merit-based seed that year."""
    return w.get("seed", 99) <= SEEDING_CUTOFF.get(w["year"], 33)


def load_data():
    wrestlers = json.loads((COMBINED_DIR / "all_wrestlers.json").read_text())
    matches   = json.loads((COMBINED_DIR / "all_matches.json").read_text())
    for w in wrestlers:
        w["team"]       = normalize_team(w["team"])
        w["conference"] = get_conference(w["team"])
    for m in matches:
        m["winner_team"] = normalize_team(m["winner_team"])
        m["loser_team"]  = normalize_team(m["loser_team"])
    # Keep only wrestlers who held a merit-based seed that year
    wrestlers = [w for w in wrestlers if is_truly_seeded(w)]
    return wrestlers, matches


# ---------------------------------------------------------------------------
# Section 1: Seed vs. Placement
# ---------------------------------------------------------------------------

def section_seed_vs_placement(wrestlers: list[dict]) -> tuple[str, str]:
    """Return (html_table, plotly_div) for seed vs. placement analysis."""

    # Gather placements per seed
    by_seed: dict[int, list[float]] = {s: [] for s in range(1, 34)}
    for w in wrestlers:
        seed = w["seed"]
        if 1 <= seed <= 33:
            by_seed[seed].append(effective_placement(w))

    seeds  = list(range(1, 34))
    means  = [statistics.mean(by_seed[s])   if by_seed[s] else 0.0 for s in seeds]
    stdevs = [statistics.stdev(by_seed[s])  if len(by_seed[s]) > 1 else 0.0 for s in seeds]
    counts = [len(by_seed[s]) for s in seeds]

    # ---- Table ----
    rows = ""
    for s, mean, sd, n in zip(seeds, means, stdevs, counts):
        rows += (
            f"<tr>"
            f"<td>{s}</td>"
            f"<td>{mean:.2f}</td>"
            f"<td>{sd:.2f}</td>"
            f"<td>{n}</td>"
            f"</tr>\n"
        )

    table_html = f"""
<table class="data-table">
  <thead>
    <tr>
      <th>Seed</th>
      <th>Avg Placement</th>
      <th>Std Dev</th>
      <th>n</th>
    </tr>
  </thead>
  <tbody>
{rows}  </tbody>
</table>
"""

    # ---- Chart ----
    fig = go.Figure()

    # Individual data points (jittered x for visibility)
    import random
    random.seed(42)
    all_x, all_y = [], []
    for s in seeds:
        for p in by_seed[s]:
            all_x.append(s + random.uniform(-0.3, 0.3))
            all_y.append(p)

    fig.add_trace(go.Scatter(
        x=all_x, y=all_y,
        mode="markers",
        marker=dict(color="rgba(99,155,210,0.25)", size=5),
        name="Individual results",
        hoverinfo="skip",
    ))

    # Reference diagonal: "finished exactly at seed"
    fig.add_trace(go.Scatter(
        x=[1, 33], y=[1, 33],
        mode="lines",
        line=dict(color="rgba(180,180,180,0.6)", dash="dash", width=1),
        name="Perfect seed = placement",
        hoverinfo="skip",
    ))

    # Mean line + error bars
    fig.add_trace(go.Scatter(
        x=seeds,
        y=means,
        mode="lines+markers",
        marker=dict(color="#1f77b4", size=7),
        line=dict(color="#1f77b4", width=2),
        error_y=dict(
            type="data",
            array=stdevs,
            visible=True,
            color="#1f77b4",
            thickness=1.5,
            width=4,
        ),
        name="Mean ± 1 SD",
        hovertemplate="Seed %{x}<br>Avg placement: %{y:.2f}<br>±1 SD: %{error_y.array:.2f}<extra></extra>",
    ))

    fig.update_layout(
        title=dict(text="Average Final Placement by Seed (2013–2024)", font=dict(size=18)),
        xaxis=dict(title="Seed", tickmode="linear", tick0=1, dtick=2, range=[0, 34]),
        yaxis=dict(title="Placement", autorange="reversed", range=[34, 0]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor="#fafafa",
        paper_bgcolor="#ffffff",
        height=520,
        hovermode="closest",
    )
    fig.update_xaxes(showgrid=True, gridcolor="#ebebeb")
    fig.update_yaxes(showgrid=True, gridcolor="#ebebeb")

    chart_div = pio.to_html(fig, full_html=False, include_plotlyjs=False)
    return table_html, chart_div


# ---------------------------------------------------------------------------
# Shared styles & constants
# ---------------------------------------------------------------------------

PLOTLYJS_CDN = '<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>'

NAV_LINKS = {
    "ncaa_report.html":            "Overall Report",
    "ncaa_team_report.html":       "Team Analysis",
    "ncaa_team_leaderboard.html":  "Team Leaderboard",
    "ncaa_conf_analysis.html":     "Conference Analysis",
    "ncaa_conf_leaderboard.html":  "Conference Leaderboard",
    "ncaa_bracket_odds.html":      "Bracket Odds",
}

def nav_bar(active_file: str) -> str:
    items = ""
    for fname, label in NAV_LINKS.items():
        cls = "nav-link active" if fname == active_file else "nav-link"
        items += f'<a href="{fname}" class="{cls}">{label}</a>\n'
    return f'<nav class="top-nav">{items}</nav>'


BASE_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: #f4f6f9;
  color: #222;
}
.top-nav {
  background: #1a1a2e;
  padding: 0 32px;
  display: flex;
  gap: 4px;
  align-items: center;
  height: 48px;
}
.nav-link {
  color: rgba(255,255,255,0.65);
  text-decoration: none;
  font-size: 0.9rem;
  font-weight: 500;
  padding: 6px 14px;
  border-radius: 5px;
  transition: background 0.15s;
}
.nav-link:hover { background: rgba(255,255,255,0.1); color: #fff; }
.nav-link.active { background: rgba(255,255,255,0.15); color: #fff; }
.page-body { padding: 32px 24px; }
.report-header { text-align: center; margin-bottom: 40px; }
.report-header h1 {
  font-size: 2rem; font-weight: 700; color: #1a1a2e; letter-spacing: -0.5px;
}
.report-header p { color: #666; margin-top: 6px; font-size: 0.95rem; }
.section {
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.08);
  padding: 28px 32px;
  margin-bottom: 32px;
  max-width: 1100px;
  margin-left: auto;
  margin-right: auto;
}
.section h2 {
  font-size: 1.35rem; font-weight: 600; color: #1a1a2e;
  margin-bottom: 6px; border-bottom: 2px solid #e8ecf0; padding-bottom: 10px;
}
.section .subtitle { color: #666; font-size: 0.9rem; margin-bottom: 20px; }
.two-col {
  display: grid; grid-template-columns: 1fr 2fr; gap: 28px; align-items: start;
}
.data-table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
.data-table thead th {
  background: #1a1a2e; color: #fff; padding: 9px 14px;
  text-align: left; font-weight: 500; letter-spacing: 0.3px;
}
.data-table tbody tr:nth-child(even) { background: #f7f9fb; }
.data-table tbody tr:hover { background: #eef2f7; }
.data-table tbody td { padding: 7px 14px; border-bottom: 1px solid #ebebeb; }
.chart-container { width: 100%; }
"""


def html_shell(title: str, active_file: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  {PLOTLYJS_CDN}
  <style>{BASE_CSS}</style>
</head>
<body>
{nav_bar(active_file)}
<div class="page-body">
{body}
</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Section 2: Team points per seed
# ---------------------------------------------------------------------------

def section_seed_vs_points(wrestlers: list[dict]) -> tuple[str, str]:
    """Return (html_table, plotly_div) for avg team points scored by seed."""
    import random

    by_seed: dict[int, list[float]] = {s: [] for s in range(1, 34)}
    for w in wrestlers:
        seed = w["seed"]
        if 1 <= seed <= 33:
            by_seed[seed].append(float(w["total_points"]))

    seeds  = list(range(1, 34))
    means  = [statistics.mean(by_seed[s])  if by_seed[s] else 0.0 for s in seeds]
    stdevs = [statistics.stdev(by_seed[s]) if len(by_seed[s]) > 1 else 0.0 for s in seeds]
    counts = [len(by_seed[s]) for s in seeds]

    # ---- Table ----
    rows = ""
    for s, mean, sd, n in zip(seeds, means, stdevs, counts):
        rows += (
            f"<tr><td>{s}</td><td>{mean:.2f}</td><td>{sd:.2f}</td><td>{n}</td></tr>\n"
        )
    table_html = f"""
<table class="data-table">
  <thead>
    <tr>
      <th>Seed</th>
      <th>Avg Points</th>
      <th>Std Dev</th>
      <th>n</th>
    </tr>
  </thead>
  <tbody>
{rows}  </tbody>
</table>
"""

    # ---- Chart ----
    fig = go.Figure()

    random.seed(42)
    all_x, all_y = [], []
    for s in seeds:
        for pts in by_seed[s]:
            all_x.append(s + random.uniform(-0.3, 0.3))
            all_y.append(pts)

    fig.add_trace(go.Scatter(
        x=all_x, y=all_y,
        mode="markers",
        marker=dict(color="rgba(46,204,113,0.2)", size=5),
        name="Individual results",
        hoverinfo="skip",
    ))

    fig.add_trace(go.Scatter(
        x=seeds, y=means,
        mode="lines+markers",
        marker=dict(color="#27ae60", size=7),
        line=dict(color="#27ae60", width=2),
        error_y=dict(
            type="data", array=stdevs, visible=True,
            color="#27ae60", thickness=1.5, width=4,
        ),
        name="Mean ± 1 SD",
        hovertemplate="Seed %{x}<br>Avg points: %{y:.2f}<br>±1 SD: %{error_y.array:.2f}<extra></extra>",
    ))

    fig.update_layout(
        title=dict(text="Average Team Points Scored by Seed (2013–2025)", font=dict(size=18)),
        xaxis=dict(title="Seed", tickmode="linear", tick0=1, dtick=2, range=[0, 34]),
        yaxis=dict(title="Team Points"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor="#fafafa",
        paper_bgcolor="#ffffff",
        height=520,
        hovermode="closest",
    )
    fig.update_xaxes(showgrid=True, gridcolor="#ebebeb")
    fig.update_yaxes(showgrid=True, gridcolor="#ebebeb")

    chart_div = pio.to_html(fig, full_html=False, include_plotlyjs=False)
    return table_html, chart_div


# ---------------------------------------------------------------------------
# Main report page
# ---------------------------------------------------------------------------

def build_report(wrestlers, matches) -> str:
    table_html,  chart_div  = section_seed_vs_placement(wrestlers)
    pts_table,   pts_chart  = section_seed_vs_points(wrestlers)

    years = sorted(set(w["year"] for w in wrestlers))
    year_range = f"{min(years)}–{max(years)} (excl. 2020)"
    n_matches  = len(matches)
    n_records  = len(wrestlers)

    body = f"""
<div class="report-header">
  <h1>NCAA Division I Wrestling — Analytical Report</h1>
  <p>{year_range} &nbsp;·&nbsp; {n_records:,} wrestler-seasons (merit-based seeds only: top 12 in 2013, top 16 in 2014–2018, all 33 from 2019)</p>
</div>

<div class="section">
  <h2>Seed vs. Final Placement</h2>
  <p class="subtitle">
    Average final placement for each seed (1–33) across all weight classes and years.
    Non-top-8 placements are estimated at the midpoint of their elimination range
    (e.g., C_R4 loss → 10.5). Error bars show ±1 standard deviation.
    The dashed diagonal represents a perfect seed = placement outcome.
  </p>
  <div class="two-col">
    <div>{table_html}</div>
    <div class="chart-container">{chart_div}</div>
  </div>
</div>

<div class="section">
  <h2>Seed vs. Team Points Scored</h2>
  <p class="subtitle">
    Average team points contributed per seed. Points = advancement points (wins through bracket)
    + bonus points (MD +1, TF +1.5, Fall/FF/DQ/Inj +2) + placement points (top-8 finishes).
    Error bars show ±1 standard deviation.
  </p>
  <div class="two-col">
    <div>{pts_table}</div>
    <div class="chart-container">{pts_chart}</div>
  </div>
</div>
"""
    return html_shell("NCAA D1 Wrestling — Analytical Report", "ncaa_report.html", body)


# ---------------------------------------------------------------------------
# Team analysis page
# ---------------------------------------------------------------------------

def build_team_page(wrestlers: list[dict]) -> str:
    # Pre-compute overall stats (used for reference lines + delta calc)
    by_seed: dict[int, list[float]] = {s: [] for s in range(1, 34)}
    for w in wrestlers:
        if 1 <= w["seed"] <= 33:
            by_seed[w["seed"]].append(effective_placement(w))

    overall_means  = {s: statistics.mean(v)  for s, v in by_seed.items() if v}
    overall_stdevs = {s: statistics.stdev(v) if len(v) > 1 else 0.0
                      for s, v in by_seed.items() if v}

    # Slim wrestler records for JS embedding (only fields we need)
    slim = [
        {
            "year":      w["year"],
            "weight":    w["weight"],
            "seed":      w["seed"],
            "name":      w["name"],
            "team":      w["team"],
            "ep":        effective_placement(w),   # effective placement (float)
            "exact":     w["placement_exact"],
        }
        for w in wrestlers
        if 1 <= w["seed"] <= 33
    ]

    teams_sorted = sorted(set(w["team"] for w in wrestlers))
    team_options = "\n".join(
        f'<option value="{t}">{t}</option>' for t in teams_sorted
    )

    # Serialize pre-computed overall stats for JS
    overall_stats_js = json.dumps(
        {str(s): {"mean": overall_means[s], "stdev": overall_stdevs[s]}
         for s in range(1, 34) if s in overall_means}
    )

    # Serialize raw data for JS
    slim_js = json.dumps(slim)

    # Build static background chart (all wrestlers, mean line) via Plotly Python
    # — exported as JSON config so JS can init Plotly with it, then add team traces
    import random
    random.seed(42)
    bg_x, bg_y = [], []
    for s in range(1, 34):
        for p in by_seed[s]:
            bg_x.append(s + random.uniform(-0.3, 0.3))
            bg_y.append(p)

    seeds = list(range(1, 34))
    means_list  = [overall_means.get(s, 0)  for s in seeds]
    stdevs_list = [overall_stdevs.get(s, 0) for s in seeds]

    fig_bg = go.Figure()
    fig_bg.add_trace(go.Scatter(
        x=bg_x, y=bg_y, mode="markers",
        marker=dict(color="rgba(180,180,180,0.2)", size=4),
        name="All results", hoverinfo="skip",
    ))
    fig_bg.add_trace(go.Scatter(
        x=[1, 33], y=[1, 33], mode="lines",
        line=dict(color="rgba(180,180,180,0.5)", dash="dash", width=1),
        name="Seed = placement", hoverinfo="skip",
    ))
    fig_bg.add_trace(go.Scatter(
        x=seeds, y=means_list, mode="lines+markers",
        marker=dict(color="rgba(99,155,210,0.6)", size=5),
        line=dict(color="rgba(99,155,210,0.6)", width=1.5),
        error_y=dict(type="data", array=stdevs_list, visible=True,
                     color="rgba(99,155,210,0.4)", thickness=1, width=3),
        name="Overall mean ± 1SD",
        hovertemplate="Seed %{x}<br>Overall avg: %{y:.2f}<extra></extra>",
    ))
    # Placeholder for team scatter trace (index 3) — filled by JS
    # Marker color/size are set per-point by JS (green=better, amber=worse, sized by count)
    fig_bg.add_trace(go.Scatter(
        x=[], y=[], mode="markers",
        marker=dict(size=[], color=[], symbol="circle",
                    line=dict(color="#fff", width=1)),
        name="Team results",
        hovertemplate="<b>%{text}</b><br>Seed %{customdata}<br>Placement: %{y:.1f}<extra></extra>",
        text=[], customdata=[],
    ))
    fig_bg.update_layout(
        title=dict(text="Placement Distribution — Select a Team", font=dict(size=17)),
        xaxis=dict(title="Seed", tickmode="linear", tick0=1, dtick=2, range=[0, 34]),
        yaxis=dict(title="Placement", autorange="reversed", range=[34, 0]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor="#fafafa", paper_bgcolor="#ffffff",
        height=500, hovermode="closest",
    )
    fig_bg.update_xaxes(showgrid=True, gridcolor="#ebebeb")
    fig_bg.update_yaxes(showgrid=True, gridcolor="#ebebeb")

    overlay_div = pio.to_html(fig_bg, full_html=False, include_plotlyjs=False,
                              div_id="overlay-chart")

    # Delta chart — empty placeholder, filled by JS
    fig_delta = go.Figure()
    fig_delta.add_trace(go.Bar(x=[], y=[], marker_color=[], name="Delta vs. average",
                               hovertemplate="Seed %{x}<br>Delta: %{y:+.2f}<extra></extra>"))
    fig_delta.update_layout(
        title=dict(text="Team Performance vs. Average (select a team)", font=dict(size=17)),
        xaxis=dict(title="Seed", tickmode="linear", tick0=1, dtick=1, range=[0, 34]),
        yaxis=dict(title="Δ Placement vs. Average  (negative = better)"),
        plot_bgcolor="#fafafa", paper_bgcolor="#ffffff",
        height=380, hovermode="x",
        shapes=[dict(type="line", x0=0, x1=34, y0=0, y1=0,
                     line=dict(color="#999", width=1, dash="dash"))],
    )
    fig_delta.update_xaxes(showgrid=True, gridcolor="#ebebeb")
    fig_delta.update_yaxes(showgrid=True, gridcolor="#ebebeb")

    delta_div = pio.to_html(fig_delta, full_html=False, include_plotlyjs=False,
                            div_id="delta-chart")

    js = f"""
<script>
const ALL_WRESTLERS = {slim_js};
const OVERALL_STATS = {overall_stats_js};

const RANGE_MID = {{
  "C_PIG": 33.0, "C_R1": 28.5, "C_R2": 20.5, "C_R3": 14.5, "C_R4": 10.5
}};

function mean(arr) {{
  return arr.reduce((a,b) => a+b, 0) / arr.length;
}}
function stdev(arr) {{
  if (arr.length < 2) return 0;
  const m = mean(arr);
  return Math.sqrt(arr.reduce((s,x) => s + (x-m)**2, 0) / (arr.length-1));
}}

function updateCharts() {{
  const team = document.getElementById("team-select").value;
  if (!team) return;

  document.getElementById("team-label").textContent = team;

  const teamData = ALL_WRESTLERS.filter(w => w.team === team);

  // Group by seed
  const bySeed = {{}};
  teamData.forEach(w => {{
    if (!bySeed[w.seed]) bySeed[w.seed] = [];
    bySeed[w.seed].push({{ ep: w.ep, label: w.name + " (" + w.year + ", " + w.weight + "lb)" }});
  }});

  // --- Overlay chart: bubble dots (aggregated by seed+placement, sized by count, colored by vs-average) ---
  // Group by (seed, placement)
  const groups = {{}};
  teamData.forEach(w => {{
    const key = w.seed + "_" + w.ep;
    if (!groups[key]) groups[key] = {{ seed: w.seed, ep: w.ep, names: [] }};
    groups[key].names.push(w.name + " (" + w.year + ", " + w.weight + "lb)");
  }});

  const ptX=[], ptY=[], ptText=[], ptCustom=[], ptColors=[], ptSizes=[];
  Object.values(groups).forEach(g => {{
    const n = g.names.length;
    const om = OVERALL_STATS[g.seed] ? OVERALL_STATS[g.seed].mean : null;
    // Green = better (lower placement), amber = worse, gray = no reference
    const color = om === null ? "#aaaaaa"
                : g.ep < om  ? "#27ae60"
                : g.ep > om  ? "#f0a500"
                :               "#aaaaaa";
    ptX.push(g.seed);
    ptY.push(g.ep);
    ptColors.push(color);
    ptSizes.push(9 + Math.sqrt(n) * 5);  // sqrt scale: 1→9, 4→19, 9→24
    const nameList = g.names.join("<br>");
    ptText.push(n > 1 ? nameList + "<br><i>(" + n + " wrestlers)</i>" : nameList);
    ptCustom.push(g.seed);
  }});

  Plotly.update("overlay-chart",
    {{
      x: [ptX],
      y: [ptY],
      text: [ptText],
      customdata: [ptCustom],
      "marker.color": [ptColors],
      "marker.size":  [ptSizes],
    }},
    {{}},
    [3]
  );
  Plotly.relayout("overlay-chart", {{
    "title.text": "Placement Distribution — " + team
  }});

  // --- Delta chart ---
  const dX=[], dY=[], dColors=[], dText=[];
  for (let s = 1; s <= 33; s++) {{
    if (!bySeed[s] || !OVERALL_STATS[s]) continue;
    const vals = bySeed[s].map(d => d.ep);
    const tm = mean(vals);
    const om = OVERALL_STATS[s].mean;
    const delta = om - tm;  // positive = outperformed (placed better than average)
    dX.push(s);
    dY.push(parseFloat(delta.toFixed(2)));
    dColors.push(delta >= 0 ? "#2ecc71" : "#e05c2a");
    dText.push("n=" + vals.length + " | team avg " + tm.toFixed(1) + ", overall " + om.toFixed(1));
  }};

  Plotly.react("delta-chart", [{{
    type: "bar",
    x: dX, y: dY,
    marker: {{ color: dColors }},
    name: "Delta",
    text: dText,
    hovertemplate: "Seed %{{x}}<br>Δ %{{y:+.2f}}<br>%{{text}}<extra></extra>",
  }}], {{
    title: {{ text: team + " vs. Average Placement by Seed" }},
    xaxis: {{ title: "Seed", tickmode: "linear", tick0: 1, dtick: 1, range: [0,34] }},
    yaxis: {{ title: "Δ Placement (positive = outperformed average)" }},
    plot_bgcolor: "#fafafa", paper_bgcolor: "#ffffff",
    height: 380, hovermode: "x",
    shapes: [{{ type:"line", x0:0, x1:34, y0:0, y1:0,
                line:{{ color:"#999", width:1, dash:"dash" }} }}],
  }});

  // Update stats table
  let rows = "";
  for (let s = 1; s <= 33; s++) {{
    if (!bySeed[s]) continue;
    const vals = bySeed[s].map(d => d.ep);
    const tm = mean(vals);
    const sd = stdev(vals);
    const om = OVERALL_STATS[s] ? OVERALL_STATS[s].mean : null;
    const delta = om !== null ? (om - tm) : null;  // positive = outperformed
    const deltaStr = delta !== null
      ? `<span style="color:${{delta>=0?"#27ae60":"#c0392b"}};font-weight:600">${{delta>=0?"+":""}}${{delta.toFixed(2)}}</span>`
      : "—";
    rows += `<tr><td>${{s}}</td><td>${{tm.toFixed(2)}}</td><td>${{sd.toFixed(2)}}</td><td>${{om!==null?om.toFixed(2):"—"}}</td><td>${{deltaStr}}</td><td>${{vals.length}}</td></tr>`;
  }}
  document.getElementById("team-table-body").innerHTML = rows || "<tr><td colspan=6>No data</td></tr>";
}}
</script>
"""

    team_css = """
<style>
.team-controls {
  display: flex; align-items: center; gap: 16px; margin-bottom: 24px;
}
.team-controls label { font-weight: 600; color: #1a1a2e; font-size: 1rem; }
.team-controls select {
  padding: 8px 14px; border-radius: 6px; border: 1px solid #ccd0d8;
  font-size: 0.95rem; background: #fff; color: #222; cursor: pointer;
  min-width: 240px;
}
.team-controls select:focus { outline: 2px solid #1f77b4; }
#team-label { font-size: 0.95rem; color: #888; font-style: italic; }
</style>
"""

    body = f"""
{team_css}
<div class="report-header">
  <h1>Team Analysis</h1>
  <p>Select a team to compare their seed-placement performance against the overall average.</p>
</div>

<div class="section">
  <div class="team-controls">
    <label for="team-select">Team:</label>
    <select id="team-select" onchange="updateCharts()">
      <option value="">— select a team —</option>
      {team_options}
    </select>
    <span id="team-label"></span>
  </div>

  <!-- Overlay chart -->
  <div class="chart-container" style="margin-bottom:28px">
    {overlay_div}
  </div>

  <!-- Delta chart -->
  <div class="chart-container" style="margin-bottom:28px">
    {delta_div}
  </div>

  <!-- Stats table -->
  <h2 style="margin-bottom:14px">Per-Seed Summary</h2>
  <p class="subtitle">Team average vs. overall average at each seed. Green delta = outperformed average.</p>
  <table class="data-table">
    <thead>
      <tr>
        <th>Seed</th>
        <th>Team Avg</th>
        <th>Team SD</th>
        <th>Overall Avg</th>
        <th>Delta</th>
        <th>n</th>
      </tr>
    </thead>
    <tbody id="team-table-body">
      <tr><td colspan="6" style="text-align:center;color:#aaa;padding:20px">Select a team above</td></tr>
    </tbody>
  </table>
</div>

{js}
"""

    return html_shell("NCAA D1 Wrestling — Team Analysis", "ncaa_team_report.html", body)


# ---------------------------------------------------------------------------
# Team leaderboard page
# ---------------------------------------------------------------------------

def build_leaderboard_page(wrestlers: list[dict]) -> str:
    # Pre-compute overall mean per seed
    by_seed: dict[int, list[float]] = {s: [] for s in range(1, 34)}
    for w in wrestlers:
        if 1 <= w["seed"] <= 33:
            by_seed[w["seed"]].append(effective_placement(w))
    overall_means = {s: statistics.mean(v) for s, v in by_seed.items() if v}

    # Accumulate per-team deltas
    team_acc: dict[str, dict] = {}
    for w in wrestlers:
        if not (1 <= w["seed"] <= 33):
            continue
        om = overall_means.get(w["seed"])
        if om is None:
            continue
        ep = effective_placement(w)
        delta = ep - om
        t = w["team"]
        if t not in team_acc:
            team_acc[t] = {"n": 0, "delta_sum": 0.0, "beat": 0}
        team_acc[t]["n"]         += 1
        team_acc[t]["delta_sum"] += delta
        if delta < 0:
            team_acc[t]["beat"] += 1

    # Build summary list, sorted best → worst
    summaries = []
    for team, d in team_acc.items():
        n = d["n"]
        avg_delta   = d["delta_sum"] / n
        pct_better  = d["beat"] / n * 100
        summaries.append({
            "team":       team,
            "n":          n,
            "avg_delta":  round(avg_delta, 3),
            "pct_better": round(pct_better, 1),
        })
    summaries.sort(key=lambda x: x["avg_delta"])

    summaries_js = json.dumps(summaries)

    js = f"""
<script>
const ALL_TEAM_SUMMARIES = {summaries_js};

// Returns a clipped axis range based on the 2nd-98th percentile of values,
// so a single extreme outlier doesn't compress the whole chart.
// Returns an object with range and clipped fields.
function deltaAxisRange(arr) {{
  if (arr.length < 4) {{
    const lo = Math.min(...arr), hi = Math.max(...arr);
    const pad = Math.max(0.3, (hi - lo) * 0.1);
    return {{ range: [lo - pad, hi + pad], clipped: false }};
  }}
  const s = [...arr].sort((a, b) => a - b);
  const n = s.length;
  const lo = s[Math.max(0, Math.round(n * 0.02))];
  const hi = s[Math.min(n - 1, Math.round(n * 0.98))];
  const span = Math.max(hi - lo, 0.5);
  const range = [lo - span * 0.10, hi + span * 0.10];
  const clipped = arr.some(v => v < range[0] || v > range[1]);
  return {{ range: range, clipped: clipped }};
}}

function renderLeaderboard() {{
  const minN = parseInt(document.getElementById("min-n").value) || 1;
  const filtered = ALL_TEAM_SUMMARIES.filter(t => t.n >= minN);
  // Already sorted best→worst by avg_delta; reverse for horizontal bar (Plotly draws bottom→top)
  const rev = [...filtered].reverse();

  // Labels: "Team Name (n)" — shared by both charts so they align
  const labels      = rev.map(t => t.team + "  (" + t.n + ")");
  const deltas      = rev.map(t => -t.avg_delta);   // invert: positive = outperformed
  const deltaColors = rev.map(t => t.avg_delta <= 0 ? "#27ae60" : "#f0a500");
  const deltaTexts  = rev.map(t => (-t.avg_delta >= 0 ? "+" : "") + (-t.avg_delta).toFixed(2));

  const pcts      = rev.map(t => t.pct_better);
  const pctColors = rev.map(t => t.pct_better >= 50 ? "#27ae60" : "#f0a500");
  const pctTexts  = rev.map(t => t.pct_better.toFixed(1) + "%");

  const chartHeight = Math.max(420, filtered.length * 26 + 120);
  const sharedLayout = {{
    height: chartHeight,
    margin: {{ l: 10, r: 90, t: 44, b: 50 }},
    yaxis: {{ automargin: true, tickfont: {{ size: 11 }} }},
    plot_bgcolor: "#fafafa",
    paper_bgcolor: "#ffffff",
    hovermode: "closest",
  }};

  // --- Avg Delta chart ---
  const axisInfo = deltaAxisRange(deltas);
  const deltaTitle = "Avg Performance vs. Field  (positive = outperformed)"
    + (axisInfo.clipped ? "  <i style='font-size:12px;color:#999'>· outlier(s) clipped — see hover for full value</i>" : "");
  Plotly.react("leaderboard-chart", [{{
    type: "bar",
    orientation: "h",
    x: deltas,
    y: labels,
    marker: {{ color: deltaColors }},
    text: deltaTexts,
    textposition: "inside",
    insidetextanchor: "middle",
    textfont: {{ color: "#fff", size: 11 }},
    cliponaxis: true,
    hovertemplate: "<b>%{{y}}</b><br>Avg Δ: %{{x:+.2f}}<extra></extra>",
  }}], {{
    ...sharedLayout,
    title: {{ text: deltaTitle, font: {{ size: 15 }} }},
    xaxis: {{
      title: "Avg Δ vs. Field  (positive = outperformed)",
      range: axisInfo.range,
      zeroline: true, zerolinecolor: "#888", zerolinewidth: 1.5,
      gridcolor: "#ebebeb",
    }},
    shapes: [{{ type:"line", x0:0, x1:0, y0:-0.5, y1:filtered.length-0.5,
                line:{{ color:"#555", width:1, dash:"dot" }} }}],
  }});

  // --- % Beat Average chart ---
  Plotly.react("pct-chart", [{{
    type: "bar",
    orientation: "h",
    x: pcts,
    y: labels,
    marker: {{ color: pctColors }},
    text: pctTexts,
    textposition: "inside",
    insidetextanchor: "middle",
    textfont: {{ color: "#fff", size: 11 }},
    hovertemplate: "<b>%{{y}}</b><br>Beat avg: %{{x:.1f}}%<extra></extra>",
  }}], {{
    ...sharedLayout,
    title: {{ text: "% of Appearances Beating Seed Average", font: {{ size: 15 }} }},
    xaxis: {{
      title: "% Beat Average",
      range: [0, 100],
      gridcolor: "#ebebeb",
    }},
    shapes: [{{ type:"line", x0:50, x1:50, y0:-0.5, y1:filtered.length-0.5,
                line:{{ color:"#888", width:1.5, dash:"dash" }} }}],
  }});

  // --- Quadrant chart ---
  const qX=[], qY=[], qColors=[], qSizes=[], qText=[], qLabels=[];
  filtered.forEach(t => {{
    const inv = -t.avg_delta;
    const inQ1 = inv >= 0 && t.pct_better >= 50;  // top-right: elite
    const inQ2 = inv <  0 && t.pct_better >= 50;  // top-left:  often beats but thin margin
    const inQ3 = inv >= 0 && t.pct_better <  50;  // bottom-right: big wins, inconsistent
    const inQ4 = inv <  0 && t.pct_better <  50;  // bottom-left: consistently poor
    const color = inQ1 ? "#27ae60" : inQ4 ? "#e74c3c" : inQ2 ? "#f0a500" : "#3498db";
    qX.push(parseFloat(inv.toFixed(3)));
    qY.push(t.pct_better);
    qColors.push(color);
    qSizes.push(10 + Math.sqrt(t.n) * 2.2);
    qLabels.push(t.team);
    qText.push(t.team + "<br>Avg Δ: " + (inv >= 0 ? "+" : "") + inv.toFixed(2)
               + "<br>% Beat: " + t.pct_better.toFixed(1) + "%"
               + "<br>n = " + t.n);
  }});

  const qMidX = (Math.min(...qX) + Math.max(...qX)) / 2;
  Plotly.react("quadrant-chart", [{{
    type: "scatter",
    mode: "markers+text",
    x: qX,
    y: qY,
    marker: {{ color: qColors, size: qSizes, opacity: 0.85,
               line: {{ color: "#fff", width: 1 }} }},
    text: qLabels,
    textposition: "top center",
    textfont: {{ size: 9, color: "#444" }},
    hovertext: qText,
    hoverinfo: "text",
    customdata: qLabels,
  }}], {{
    height: 540,
    margin: {{ l: 60, r: 30, t: 60, b: 60 }},
    title: {{ text: "Performance Matrix — Avg Δ vs. % Beat Average", font: {{ size: 16 }} }},
    xaxis: {{
      title: "Avg Δ vs. Field  (positive = outperformed)",
      zeroline: true, zerolinecolor: "#888", zerolinewidth: 1.5,
      gridcolor: "#ebebeb",
    }},
    yaxis: {{
      title: "% Beat Average",
      range: [0, 100],
      gridcolor: "#ebebeb",
    }},
    plot_bgcolor: "#fafafa",
    paper_bgcolor: "#ffffff",
    hovermode: "closest",
    shapes: [
      // zero vertical line
      {{ type:"line", x0:0, x1:0, y0:0, y1:100,
         line:{{ color:"#aaa", width:1, dash:"dot" }} }},
      // 50% horizontal line
      {{ type:"line", x0:Math.min(...qX)-0.5, x1:Math.max(...qX)+0.5, y0:50, y1:50,
         line:{{ color:"#aaa", width:1, dash:"dot" }} }},
    ],
    annotations: [
      {{ x: Math.max(...qX)*0.85, y: 94, text: "Consistent Overperformers",
         showarrow: false, font: {{ size: 10, color: "#27ae60" }}, xref:"x", yref:"y" }},
      {{ x: Math.min(...qX)*0.85, y: 94, text: "Often Beats, Thin Margin",
         showarrow: false, font: {{ size: 10, color: "#f0a500" }}, xref:"x", yref:"y" }},
      {{ x: Math.max(...qX)*0.85, y:  6, text: "Big Wins, Inconsistent",
         showarrow: false, font: {{ size: 10, color: "#3498db" }}, xref:"x", yref:"y" }},
      {{ x: Math.min(...qX)*0.85, y:  6, text: "Consistent Underperformers",
         showarrow: false, font: {{ size: 10, color: "#e74c3c" }}, xref:"x", yref:"y" }},
    ],
  }});

  // --- Table ---
  let rows = "";
  filtered.forEach((t, i) => {{
    const inv   = -t.avg_delta;
    const sign  = inv >= 0 ? "+" : "";
    const dColor = inv >= 0 ? "#27ae60" : "#c0392b";
    const pColor = t.pct_better >= 50 ? "#27ae60" : "#c0392b";
    rows += `<tr>
      <td>${{i + 1}}</td>
      <td>${{t.team}} <span style="color:#999;font-size:0.82em">(n=${{t.n}})</span></td>
      <td style="color:${{dColor}};font-weight:600">${{sign}}${{inv.toFixed(2)}}</td>
      <td style="color:${{pColor}};font-weight:600">${{t.pct_better.toFixed(1)}}%</td>
    </tr>`;
  }});
  document.getElementById("leaderboard-table-body").innerHTML =
    rows || '<tr><td colspan="4" style="text-align:center;color:#aaa;padding:20px">No teams meet minimum</td></tr>';

  document.getElementById("team-count").textContent =
    filtered.length + " team" + (filtered.length !== 1 ? "s" : "");
}}

document.addEventListener("DOMContentLoaded", () => {{
  document.getElementById("min-n").addEventListener("input", renderLeaderboard);
  renderLeaderboard();
}});
</script>
"""

    leaderboard_css = """
<style>
.controls-bar {
  display: flex; align-items: center; gap: 20px; margin-bottom: 24px; flex-wrap: wrap;
}
.controls-bar label { font-weight: 600; color: #1a1a2e; font-size: 1rem; }
.controls-bar input[type=number] {
  width: 80px; padding: 7px 10px; border-radius: 6px;
  border: 1px solid #ccd0d8; font-size: 0.95rem; text-align: center;
}
.controls-bar input[type=number]:focus { outline: 2px solid #1f77b4; }
#team-count { font-size: 0.9rem; color: #888; font-style: italic; }
</style>
"""

    body = f"""
{leaderboard_css}
<div class="report-header">
  <h1>Team Leaderboard</h1>
  <p>All-time team performance vs. the overall average placement for each seed (2013–2024).</p>
</div>

<div class="section">
  <div class="controls-bar">
    <label for="min-n">Minimum wrestlers:</label>
    <input type="number" id="min-n" value="10" min="1" max="999">
    <span id="team-count"></span>
  </div>

  <p class="subtitle" style="margin-bottom:20px">
    <span style="color:#27ae60;font-weight:600">Green</span> = outperformed the field for their seeds &nbsp;·&nbsp;
    <span style="color:#f0a500;font-weight:600">Amber</span> = underperformed &nbsp;·&nbsp;
    Δ = how many placement spots better (+) or worse (−) than the field average at each seed
  </p>

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;align-items:start">
    <div id="leaderboard-chart"></div>
    <div id="pct-chart"></div>
  </div>
</div>

<div class="section">
  <h2 style="margin-bottom:8px">Performance Matrix</h2>
  <p class="subtitle" style="margin-bottom:16px">
    Both metrics on one chart. Bubble size = number of wrestlers (n).
    Color indicates quadrant:
    <span style="color:#27ae60;font-weight:600">green</span> = consistently overperform,
    <span style="color:#e74c3c;font-weight:600">red</span> = consistently underperform,
    <span style="color:#f0a500;font-weight:600">amber</span> = beat avg often but slight negative delta,
    <span style="color:#3498db;font-weight:600">blue</span> = positive avg delta but inconsistent.
  </p>
  <div id="quadrant-chart"></div>
</div>

<div class="section">
  <h2 style="margin-bottom:14px">Full Rankings Table</h2>
  <p class="subtitle" style="margin-bottom:14px">Sorted by Avg Δ (best first). n shown in team name.</p>
  <table class="data-table">
    <thead>
      <tr>
        <th>#</th>
        <th>Team</th>
        <th>Avg Δ vs. Field</th>
        <th>% Beat Average</th>
      </tr>
    </thead>
    <tbody id="leaderboard-table-body"></tbody>
  </table>
</div>

{js}
"""

    return html_shell("NCAA D1 Wrestling — Team Leaderboard", "ncaa_team_leaderboard.html", body)


# ---------------------------------------------------------------------------
# Conference analysis page  (mirrors build_team_page)
# ---------------------------------------------------------------------------

def build_conference_analysis_page(wrestlers: list[dict]) -> str:
    by_seed: dict[int, list[float]] = {s: [] for s in range(1, 34)}
    for w in wrestlers:
        if 1 <= w["seed"] <= 33:
            by_seed[w["seed"]].append(effective_placement(w))

    overall_means  = {s: statistics.mean(v)  for s, v in by_seed.items() if v}
    overall_stdevs = {s: statistics.stdev(v) if len(v) > 1 else 0.0
                      for s, v in by_seed.items() if v}

    # Slim records — include team for hover text, exclude unassigned/inactive
    slim = [
        {
            "year":       w["year"],
            "weight":     w["weight"],
            "seed":       w["seed"],
            "name":       w["name"],
            "team":       w["team"],
            "conference": w["conference"],
            "ep":         effective_placement(w),
            "exact":      w["placement_exact"],
        }
        for w in wrestlers
        if 1 <= w["seed"] <= 33
        and w["conference"] not in (None, "Inactive")
    ]

    confs_sorted = sorted(set(w["conference"] for w in slim))
    conf_options = "\n".join(
        f'<option value="{c}">{c}</option>' for c in confs_sorted
    )

    overall_stats_js = json.dumps(
        {str(s): {"mean": overall_means[s], "stdev": overall_stdevs[s]}
         for s in range(1, 34) if s in overall_means}
    )
    slim_js = json.dumps(slim)

    import random
    random.seed(42)
    bg_x, bg_y = [], []
    for s in range(1, 34):
        for p in by_seed[s]:
            bg_x.append(s + random.uniform(-0.3, 0.3))
            bg_y.append(p)

    seeds = list(range(1, 34))
    means_list  = [overall_means.get(s, 0)  for s in seeds]
    stdevs_list = [overall_stdevs.get(s, 0) for s in seeds]

    fig_bg = go.Figure()
    fig_bg.add_trace(go.Scatter(
        x=bg_x, y=bg_y, mode="markers",
        marker=dict(color="rgba(180,180,180,0.2)", size=4),
        name="All results", hoverinfo="skip",
    ))
    fig_bg.add_trace(go.Scatter(
        x=[1, 33], y=[1, 33], mode="lines",
        line=dict(color="rgba(180,180,180,0.5)", dash="dash", width=1),
        name="Seed = placement", hoverinfo="skip",
    ))
    fig_bg.add_trace(go.Scatter(
        x=seeds, y=means_list, mode="lines+markers",
        marker=dict(color="rgba(99,155,210,0.6)", size=5),
        line=dict(color="rgba(99,155,210,0.6)", width=1.5),
        error_y=dict(type="data", array=stdevs_list, visible=True,
                     color="rgba(99,155,210,0.4)", thickness=1, width=3),
        name="Overall mean ± 1SD",
        hovertemplate="Seed %{x}<br>Overall avg: %{y:.2f}<extra></extra>",
    ))
    fig_bg.add_trace(go.Scatter(
        x=[], y=[], mode="markers",
        marker=dict(size=[], color=[], symbol="circle",
                    line=dict(color="#fff", width=1)),
        name="Conference results",
        hovertemplate="<b>%{text}</b><br>Seed %{customdata}<br>Placement: %{y:.1f}<extra></extra>",
        text=[], customdata=[],
    ))
    fig_bg.update_layout(
        title=dict(text="Placement Distribution — Select a Conference", font=dict(size=17)),
        xaxis=dict(title="Seed", tickmode="linear", tick0=1, dtick=2, range=[0, 34]),
        yaxis=dict(title="Placement", autorange="reversed", range=[34, 0]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor="#fafafa", paper_bgcolor="#ffffff",
        height=500, hovermode="closest",
    )
    fig_bg.update_xaxes(showgrid=True, gridcolor="#ebebeb")
    fig_bg.update_yaxes(showgrid=True, gridcolor="#ebebeb")
    overlay_div = pio.to_html(fig_bg, full_html=False, include_plotlyjs=False,
                              div_id="conf-overlay-chart")

    fig_delta = go.Figure()
    fig_delta.add_trace(go.Bar(x=[], y=[], marker_color=[], name="Delta vs. average",
                               hovertemplate="Seed %{x}<br>Delta: %{y:+.2f}<extra></extra>"))
    fig_delta.update_layout(
        title=dict(text="Conference Performance vs. Average (select a conference)", font=dict(size=17)),
        xaxis=dict(title="Seed", tickmode="linear", tick0=1, dtick=1, range=[0, 34]),
        yaxis=dict(title="Δ Placement vs. Average  (negative = better)"),
        plot_bgcolor="#fafafa", paper_bgcolor="#ffffff",
        height=380, hovermode="x",
        shapes=[dict(type="line", x0=0, x1=34, y0=0, y1=0,
                     line=dict(color="#999", width=1, dash="dash"))],
    )
    fig_delta.update_xaxes(showgrid=True, gridcolor="#ebebeb")
    fig_delta.update_yaxes(showgrid=True, gridcolor="#ebebeb")
    delta_div = pio.to_html(fig_delta, full_html=False, include_plotlyjs=False,
                            div_id="conf-delta-chart")

    js = f"""
<script>
const CONF_WRESTLERS = {slim_js};
const CONF_OVERALL_STATS = {overall_stats_js};

function confMean(arr) {{ return arr.reduce((a,b)=>a+b,0)/arr.length; }}
function confStdev(arr) {{
  if (arr.length < 2) return 0;
  const m = confMean(arr);
  return Math.sqrt(arr.reduce((s,x)=>s+(x-m)**2,0)/(arr.length-1));
}}

function updateConfCharts() {{
  const conf = document.getElementById("conf-select").value;
  if (!conf) return;
  document.getElementById("conf-label").textContent = conf;

  const confData = CONF_WRESTLERS.filter(w => w.conference === conf);

  const bySeed = {{}};
  confData.forEach(w => {{
    if (!bySeed[w.seed]) bySeed[w.seed] = [];
    bySeed[w.seed].push({{ ep: w.ep, label: w.name + " (" + w.team + ", " + w.year + " " + w.weight + "lb)" }});
  }});

  // Bubble dots grouped by (seed, placement)
  const groups = {{}};
  confData.forEach(w => {{
    const key = w.seed + "_" + w.ep;
    if (!groups[key]) groups[key] = {{ seed: w.seed, ep: w.ep, names: [] }};
    groups[key].names.push(w.name + " (" + w.team + ", " + w.year + " " + w.weight + "lb)");
  }});

  const ptX=[], ptY=[], ptText=[], ptCustom=[], ptColors=[], ptSizes=[];
  Object.values(groups).forEach(g => {{
    const n = g.names.length;
    const om = CONF_OVERALL_STATS[g.seed] ? CONF_OVERALL_STATS[g.seed].mean : null;
    const color = om===null ? "#aaaaaa" : g.ep<om ? "#27ae60" : g.ep>om ? "#f0a500" : "#aaaaaa";
    ptX.push(g.seed); ptY.push(g.ep); ptColors.push(color);
    ptSizes.push(9 + Math.sqrt(n)*5);
    const nameList = g.names.join("<br>");
    ptText.push(n>1 ? nameList+"<br><i>("+n+" wrestlers)</i>" : nameList);
    ptCustom.push(g.seed);
  }});

  Plotly.update("conf-overlay-chart",
    {{ x:[ptX], y:[ptY], text:[ptText], customdata:[ptCustom],
       "marker.color":[ptColors], "marker.size":[ptSizes] }},
    {{}}, [3]);
  Plotly.relayout("conf-overlay-chart", {{"title.text": "Placement Distribution — "+conf}});

  // Delta bar chart
  const dX=[], dY=[], dColors=[], dText=[];
  for (let s=1; s<=33; s++) {{
    if (!bySeed[s] || !CONF_OVERALL_STATS[s]) continue;
    const vals = bySeed[s].map(d=>d.ep);
    const tm=confMean(vals), om=CONF_OVERALL_STATS[s].mean, delta=om-tm;  // positive = outperformed
    dX.push(s); dY.push(parseFloat(delta.toFixed(2)));
    dColors.push(delta>=0?"#2ecc71":"#e05c2a");
    dText.push("n="+vals.length+" | conf avg "+tm.toFixed(1)+", overall "+om.toFixed(1));
  }}
  Plotly.react("conf-delta-chart", [{{
    type:"bar", x:dX, y:dY, marker:{{color:dColors}}, name:"Delta",
    text:dText, hovertemplate:"Seed %{{x}}<br>Δ %{{y:+.2f}}<br>%{{text}}<extra></extra>",
  }}], {{
    title:{{text:conf+" vs. Average Placement by Seed"}},
    xaxis:{{title:"Seed",tickmode:"linear",tick0:1,dtick:1,range:[0,34]}},
    yaxis:{{title:"Δ Placement (positive = outperformed average)"}},
    plot_bgcolor:"#fafafa", paper_bgcolor:"#ffffff", height:380, hovermode:"x",
    shapes:[{{type:"line",x0:0,x1:34,y0:0,y1:0,line:{{color:"#999",width:1,dash:"dash"}}}}],
  }});

  // Table
  let rows="";
  for (let s=1; s<=33; s++) {{
    if (!bySeed[s]) continue;
    const vals=bySeed[s].map(d=>d.ep), tm=confMean(vals), sd=confStdev(vals);
    const om=CONF_OVERALL_STATS[s]?CONF_OVERALL_STATS[s].mean:null;
    const delta=om!==null?(om-tm):null;  // positive = outperformed
    const deltaStr=delta!==null
      ?`<span style="color:${{delta>=0?"#27ae60":"#c0392b"}};font-weight:600">${{delta>=0?"+":""}}${{delta.toFixed(2)}}</span>`
      :"—";
    rows+=`<tr><td>${{s}}</td><td>${{tm.toFixed(2)}}</td><td>${{sd.toFixed(2)}}</td><td>${{om!==null?om.toFixed(2):"—"}}</td><td>${{deltaStr}}</td><td>${{vals.length}}</td></tr>`;
  }}
  document.getElementById("conf-table-body").innerHTML=rows||"<tr><td colspan=6>No data</td></tr>";
}}
</script>
"""

    conf_css = """
<style>
.conf-controls { display:flex; align-items:center; gap:16px; margin-bottom:24px; }
.conf-controls label { font-weight:600; color:#1a1a2e; font-size:1rem; }
.conf-controls select {
  padding:8px 14px; border-radius:6px; border:1px solid #ccd0d8;
  font-size:0.95rem; background:#fff; color:#222; cursor:pointer; min-width:200px;
}
.conf-controls select:focus { outline:2px solid #1f77b4; }
#conf-label { font-size:0.95rem; color:#888; font-style:italic; }
</style>
"""

    body = f"""
{conf_css}
<div class="report-header">
  <h1>Conference Analysis</h1>
  <p>Select a conference to compare seed-placement performance against the overall average.</p>
</div>

<div class="section">
  <div class="conf-controls">
    <label for="conf-select">Conference:</label>
    <select id="conf-select" onchange="updateConfCharts()">
      <option value="">— select a conference —</option>
      {conf_options}
    </select>
    <span id="conf-label"></span>
  </div>

  <div class="chart-container" style="margin-bottom:28px">{overlay_div}</div>
  <div class="chart-container" style="margin-bottom:28px">{delta_div}</div>

  <h2 style="margin-bottom:14px">Per-Seed Summary</h2>
  <p class="subtitle">Conference average vs. overall average at each seed. Green delta = outperformed average.</p>
  <table class="data-table">
    <thead>
      <tr><th>Seed</th><th>Conf Avg</th><th>Conf SD</th><th>Overall Avg</th><th>Delta</th><th>n</th></tr>
    </thead>
    <tbody id="conf-table-body">
      <tr><td colspan="6" style="text-align:center;color:#aaa;padding:20px">Select a conference above</td></tr>
    </tbody>
  </table>
</div>

{js}
"""
    return html_shell("NCAA D1 Wrestling — Conference Analysis", "ncaa_conf_analysis.html", body)


# ---------------------------------------------------------------------------
# Conference leaderboard page  (mirrors build_leaderboard_page)
# ---------------------------------------------------------------------------

def build_conference_leaderboard_page(wrestlers: list[dict]) -> str:
    by_seed: dict[int, list[float]] = {s: [] for s in range(1, 34)}
    for w in wrestlers:
        if 1 <= w["seed"] <= 33:
            by_seed[w["seed"]].append(effective_placement(w))
    overall_means = {s: statistics.mean(v) for s, v in by_seed.items() if v}

    conf_acc: dict[str, dict] = {}
    for w in wrestlers:
        if not (1 <= w["seed"] <= 33):
            continue
        conf = w["conference"]
        if conf in (None, "Inactive"):
            continue
        om = overall_means.get(w["seed"])
        if om is None:
            continue
        ep = effective_placement(w)
        delta = ep - om
        if conf not in conf_acc:
            conf_acc[conf] = {"n": 0, "delta_sum": 0.0, "beat": 0}
        conf_acc[conf]["n"]         += 1
        conf_acc[conf]["delta_sum"] += delta
        if delta < 0:
            conf_acc[conf]["beat"] += 1

    summaries = []
    for conf, d in conf_acc.items():
        n = d["n"]
        summaries.append({
            "conf":       conf,
            "n":          n,
            "avg_delta":  round(d["delta_sum"] / n, 3),
            "pct_better": round(d["beat"] / n * 100, 1),
        })
    summaries.sort(key=lambda x: x["avg_delta"])
    summaries_js = json.dumps(summaries)

    js = f"""
<script>
const ALL_CONF_SUMMARIES = {summaries_js};

function deltaAxisRange(arr) {{
  if (arr.length < 4) {{
    const lo = Math.min(...arr), hi = Math.max(...arr);
    const pad = Math.max(0.3, (hi - lo) * 0.1);
    return {{ range: [lo - pad, hi + pad], clipped: false }};
  }}
  const s = [...arr].sort((a, b) => a - b);
  const n = s.length;
  const lo = s[Math.max(0, Math.round(n * 0.02))];
  const hi = s[Math.min(n - 1, Math.round(n * 0.98))];
  const span = Math.max(hi - lo, 0.5);
  const range = [lo - span * 0.10, hi + span * 0.10];
  const clipped = arr.some(v => v < range[0] || v > range[1]);
  return {{ range: range, clipped: clipped }};
}}

function renderConfLeaderboard() {{
  const minN = parseInt(document.getElementById("conf-min-n").value) || 1;
  const filtered = ALL_CONF_SUMMARIES.filter(c => c.n >= minN);
  const rev = [...filtered].reverse();

  const labels      = rev.map(c => c.conf + "  (" + c.n + ")");
  const deltas      = rev.map(c => -c.avg_delta);
  const deltaColors = rev.map(c => c.avg_delta <= 0 ? "#27ae60" : "#f0a500");
  const deltaTexts  = rev.map(c => (-c.avg_delta >= 0 ? "+" : "") + (-c.avg_delta).toFixed(2));
  const pcts        = rev.map(c => c.pct_better);
  const pctColors   = rev.map(c => c.pct_better >= 50 ? "#27ae60" : "#f0a500");
  const pctTexts    = rev.map(c => c.pct_better.toFixed(1) + "%");

  const chartHeight = Math.max(300, filtered.length * 38 + 120);
  const sharedLayout = {{
    height: chartHeight,
    margin: {{ l:10, r:90, t:44, b:50 }},
    yaxis: {{ automargin:true, tickfont:{{size:12}} }},
    plot_bgcolor:"#fafafa", paper_bgcolor:"#ffffff", hovermode:"closest",
  }};

  const axisInfo = deltaAxisRange(deltas);
  Plotly.react("conf-lb-chart", [{{
    type:"bar", orientation:"h", x:deltas, y:labels, marker:{{color:deltaColors}},
    text:deltaTexts, textposition:"inside", insidetextanchor:"middle",
    textfont:{{color:"#fff",size:12}}, cliponaxis:true,
    hovertemplate:"<b>%{{y}}</b><br>Avg Δ: %{{x:+.2f}}<extra></extra>",
  }}], {{
    ...sharedLayout,
    title:{{text:"Avg Performance vs. Field  (positive = outperformed)",font:{{size:15}}}},
    xaxis:{{ title:"Avg Δ vs. Field  (positive = outperformed)",
             range:axisInfo.range, zeroline:true, zerolinecolor:"#888",
             zerolinewidth:1.5, gridcolor:"#ebebeb" }},
  }});

  Plotly.react("conf-pct-chart", [{{
    type:"bar", orientation:"h", x:pcts, y:labels, marker:{{color:pctColors}},
    text:pctTexts, textposition:"inside", insidetextanchor:"middle",
    textfont:{{color:"#fff",size:12}},
    hovertemplate:"<b>%{{y}}</b><br>Beat avg: %{{x:.1f}}%<extra></extra>",
  }}], {{
    ...sharedLayout,
    title:{{text:"% of Appearances Beating Seed Average",font:{{size:15}}}},
    xaxis:{{title:"% Beat Average", range:[0,100], gridcolor:"#ebebeb"}},
    shapes:[{{type:"line",x0:50,x1:50,y0:-0.5,y1:filtered.length-0.5,
              line:{{color:"#888",width:1.5,dash:"dash"}}}}],
  }});

  // Quadrant chart
  const qX=[], qY=[], qColors=[], qSizes=[], qText=[], qLabels=[];
  filtered.forEach(c => {{
    const inv=-c.avg_delta;
    const color = inv>=0&&c.pct_better>=50?"#27ae60"
                : inv< 0&&c.pct_better< 50?"#e74c3c"
                : inv< 0&&c.pct_better>=50?"#f0a500":"#3498db";
    qX.push(parseFloat(inv.toFixed(3))); qY.push(c.pct_better);
    qColors.push(color); qSizes.push(14+Math.sqrt(c.n)*1.8);
    qLabels.push(c.conf);
    qText.push(c.conf+"<br>Avg Δ:"+(inv>=0?"+":"")+inv.toFixed(2)
               +"<br>% Beat:"+c.pct_better.toFixed(1)+"%<br>n="+c.n);
  }});
  const qXmin=Math.min(...qX)-0.1, qXmax=Math.max(...qX)+0.1;
  Plotly.react("conf-quad-chart",[{{
    type:"scatter", mode:"markers+text",
    x:qX, y:qY, marker:{{color:qColors,size:qSizes,opacity:0.88,line:{{color:"#fff",width:1}}}},
    text:qLabels, textposition:"top center", textfont:{{size:10,color:"#333"}},
    hovertext:qText, hoverinfo:"text",
  }}],{{
    height:480, margin:{{l:60,r:30,t:60,b:60}},
    title:{{text:"Conference Performance Matrix",font:{{size:16}}}},
    xaxis:{{title:"Avg Δ vs. Field  (positive = outperformed)",
            zeroline:true,zerolinecolor:"#888",zerolinewidth:1.5,gridcolor:"#ebebeb"}},
    yaxis:{{title:"% Beat Average",range:[0,100],gridcolor:"#ebebeb"}},
    plot_bgcolor:"#fafafa", paper_bgcolor:"#ffffff", hovermode:"closest",
    shapes:[
      {{type:"line",x0:0,x1:0,y0:0,y1:100,line:{{color:"#aaa",width:1,dash:"dot"}}}},
      {{type:"line",x0:qXmin,x1:qXmax,y0:50,y1:50,line:{{color:"#aaa",width:1,dash:"dot"}}}},
    ],
    annotations:[
      {{x:qXmax*0.8,y:94,text:"Consistent Overperformers",showarrow:false,font:{{size:10,color:"#27ae60"}},xref:"x",yref:"y"}},
      {{x:qXmin*0.8,y:94,text:"Often Beats, Thin Margin",showarrow:false,font:{{size:10,color:"#f0a500"}},xref:"x",yref:"y"}},
      {{x:qXmax*0.8,y: 6,text:"Big Wins, Inconsistent",showarrow:false,font:{{size:10,color:"#3498db"}},xref:"x",yref:"y"}},
      {{x:qXmin*0.8,y: 6,text:"Consistent Underperformers",showarrow:false,font:{{size:10,color:"#e74c3c"}},xref:"x",yref:"y"}},
    ],
  }});

  // Table
  let rows="";
  filtered.forEach((c,i) => {{
    const inv=-c.avg_delta, sign=inv>=0?"+":"";
    const dColor=inv>=0?"#27ae60":"#c0392b", pColor=c.pct_better>=50?"#27ae60":"#c0392b";
    rows+=`<tr><td>${{i+1}}</td><td>${{c.conf}} <span style="color:#999;font-size:0.82em">(n=${{c.n}})</span></td>`
         +`<td style="color:${{dColor}};font-weight:600">${{sign}}${{inv.toFixed(2)}}</td>`
         +`<td style="color:${{pColor}};font-weight:600">${{c.pct_better.toFixed(1)}}%</td></tr>`;
  }});
  document.getElementById("conf-lb-table-body").innerHTML=
    rows||'<tr><td colspan="4" style="text-align:center;color:#aaa;padding:20px">No data</td></tr>';
  document.getElementById("conf-count").textContent=
    filtered.length+" conference"+(filtered.length!==1?"s":"");
}}

document.addEventListener("DOMContentLoaded",()=>{{
  document.getElementById("conf-min-n").addEventListener("input",renderConfLeaderboard);
  renderConfLeaderboard();
}});
</script>
"""

    lb_css = """
<style>
.controls-bar { display:flex; align-items:center; gap:20px; margin-bottom:24px; flex-wrap:wrap; }
.controls-bar label { font-weight:600; color:#1a1a2e; font-size:1rem; }
.controls-bar input[type=number] {
  width:80px; padding:7px 10px; border-radius:6px;
  border:1px solid #ccd0d8; font-size:0.95rem; text-align:center;
}
.controls-bar input[type=number]:focus { outline:2px solid #1f77b4; }
#conf-count { font-size:0.9rem; color:#888; font-style:italic; }
</style>
"""

    body = f"""
{lb_css}
<div class="report-header">
  <h1>Conference Leaderboard</h1>
  <p>All-time conference performance vs. the overall average placement for each seed (2013–2025).</p>
</div>

<div class="section">
  <div class="controls-bar">
    <label for="conf-min-n">Minimum wrestlers:</label>
    <input type="number" id="conf-min-n" value="10" min="1" max="9999">
    <span id="conf-count"></span>
  </div>
  <p class="subtitle" style="margin-bottom:20px">
    <span style="color:#27ae60;font-weight:600">Green</span> = outperformed the field &nbsp;·&nbsp;
    <span style="color:#f0a500;font-weight:600">Amber</span> = underperformed &nbsp;·&nbsp;
    Δ = avg spots better (+) or worse (−) than the field average at each seed
  </p>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;align-items:start">
    <div id="conf-lb-chart"></div>
    <div id="conf-pct-chart"></div>
  </div>
</div>

<div class="section">
  <h2 style="margin-bottom:8px">Performance Matrix</h2>
  <p class="subtitle" style="margin-bottom:16px">
    Both metrics on one chart. Bubble size = number of wrestlers (n).
  </p>
  <div id="conf-quad-chart"></div>
</div>

<div class="section">
  <h2 style="margin-bottom:14px">Full Rankings Table</h2>
  <table class="data-table">
    <thead>
      <tr><th>#</th><th>Conference</th><th>Avg Δ vs. Field</th><th>% Beat Average</th></tr>
    </thead>
    <tbody id="conf-lb-table-body"></tbody>
  </table>
</div>

{js}
"""
    return html_shell("NCAA D1 Wrestling — Conference Leaderboard", "ncaa_conf_leaderboard.html", body)


# ---------------------------------------------------------------------------
# Bracket Odds Page
# ---------------------------------------------------------------------------

def build_bracket_odds_page(wrestlers: list[dict]) -> str:
    """Show each seed's probability of reaching each championship bracket round."""

    # PIG excluded: seeds 32-33 threshold offsets account for it internally
    ROUNDS = ["R16", "QF", "SF", "Final", "Champ"]

    # Build per-seed stats
    by_seed: dict[int, list[dict]] = {s: [] for s in range(1, 34)}
    for w in wrestlers:
        s = w.get("seed")
        if s and 1 <= s <= 33:
            by_seed[s].append(w)

    def compute(seed: int, wrestlers_list: list[dict], rnd: str) -> tuple[int, int]:
        """Return (numerator, denominator) for a seed/round combination."""
        n = len(wrestlers_list)
        if n == 0:
            return (0, 0)
        cw = "champ_wins"
        # Seeds 32-33 need an extra champ win to account for the pigtail
        if seed >= 32:
            thresholds = {"R16": 2, "QF": 3, "SF": 4, "Final": 5}
        else:
            thresholds = {"R16": 1, "QF": 2, "SF": 3, "Final": 4}
        if rnd == "Champ":
            num = sum(1 for w in wrestlers_list if w.get("placement") == 1)
        else:
            t = thresholds[rnd]
            num = sum(1 for w in wrestlers_list if w.get(cw, 0) >= t)
        return (num, n)

    counts = [len(by_seed[s]) for s in range(1, 34)]

    # Build z, text, and customdata matrices
    # Sentinel -1 in z = true zero (0/n); None = N/A (not used here — all seeds have all rounds)
    # Colorscale maps -1 → gray, 0+ → amber→green
    SENTINEL = -1
    z_vals: list[list] = []
    text_vals: list[list] = []
    custom_vals: list[list] = []  # [[num, denom], ...]

    for s in range(1, 34):
        z_row, t_row, c_row = [], [], []
        for rnd in ROUNDS:
            num, denom = compute(s, by_seed[s], rnd)
            if denom == 0:
                z_row.append(None)
                t_row.append("—")
                c_row.append([None, None])
            elif num == 0:
                z_row.append(SENTINEL)
                t_row.append("0%")
                c_row.append([0, denom])
            else:
                pct_val = round(num / denom * 100, 1)
                z_row.append(pct_val)
                t_row.append(f"{pct_val:.0f}%")
                c_row.append([num, denom])
        z_vals.append(z_row)
        text_vals.append(t_row)
        custom_vals.append(c_row)

    y_labels = [f"Seed {s} (n={counts[s-1]})" for s in range(1, 34)]

    # Survival curve data
    curve_data: list[dict] = []
    for s in range(1, 34):
        frac = (s - 1) / 32
        r = int(39 + frac * (200 - 39))
        g = int(174 - frac * (174 - 50))
        b = int(96 - frac * 96)
        color = f"rgb({r},{g},{b})"
        y_pts = []
        for rnd in ROUNDS:
            num, denom = compute(s, by_seed[s], rnd)
            y_pts.append(round(num / denom * 100, 1) if denom else None)
        x_plot = [ROUNDS[i] for i, v in enumerate(y_pts) if v is not None]
        y_plot = [v for v in y_pts if v is not None]
        curve_data.append({"seed": s, "x": x_plot, "y": y_plot, "color": color, "n": counts[s - 1]})

    z_json      = json.dumps(list(reversed(z_vals)))
    text_json   = json.dumps(list(reversed(text_vals)))
    custom_json = json.dumps(list(reversed(custom_vals)))
    y_json      = json.dumps(list(reversed(y_labels)))
    rounds_json = json.dumps(ROUNDS)
    curve_json  = json.dumps(curve_data)

    # Colorscale: zmin=-1, zmax=100
    # position(z) = (z+1)/101
    # position(-1) = 0.000  → gray
    # position(~0) = 0.0099 → amber  (sharp jump via duplicate stop)
    # position(100) = 1.000 → green
    colorscale_json = json.dumps([
        [0.0000, "#d0d0d0"],
        [0.0098, "#d0d0d0"],
        [0.0099, "#f0a500"],
        [0.35,   "#e8c840"],
        [0.65,   "#a8d860"],
        [1.0000, "#27ae60"],
    ])

    js = f"""
<script>
(function() {{

const zVals      = {z_json};
const textVals   = {text_json};
const customVals = {custom_json};
const yLabels    = {y_json};
const rounds     = {rounds_json};
const colorscale = {colorscale_json};

const hmTrace = {{
  type: "heatmap",
  x: rounds,
  y: yLabels,
  z: zVals,
  text: textVals,
  customdata: customVals,
  texttemplate: "%{{text}}",
  textfont: {{ size: 12, color: "#222" }},
  colorscale: colorscale,
  zmin: -1,
  zmax: 100,
  showscale: true,
  colorbar: {{
    title: "% Reaching Round",
    titleside: "right",
    tickvals: [0, 25, 50, 75, 100],
    ticktext: ["0%", "25%", "50%", "75%", "100%"],
    len: 0.6
  }},
  hovertemplate: "%{{y}}<br>%{{x}}: %{{customdata[0]}}/%{{customdata[1]}}<extra></extra>"
}};

Plotly.newPlot("heatmap-chart", [hmTrace], {{
  margin: {{ t: 50, b: 20, l: 170, r: 120 }},
  xaxis: {{ side: "top", fixedrange: true }},
  yaxis: {{ fixedrange: true, automargin: true }},
  plot_bgcolor: "#ffffff",
  paper_bgcolor: "#ffffff"
}}, {{ responsive: true, displayModeBar: false }});

// ---- Survival Curve ----
const curveData = {curve_json};

const traces = curveData.map(d => ({{
  type: "scatter",
  mode: "lines+markers",
  name: "Seed " + d.seed,
  x: d.x,
  y: d.y,
  line: {{ color: d.color, width: d.seed <= 8 ? 2.5 : 1.5 }},
  marker: {{ color: d.color, size: 5 }},
  hovertemplate: "Seed " + d.seed + " (n=" + d.n + ")<br>%{{x}}: %{{y:.1f}}%<extra></extra>"
}}));

Plotly.newPlot("curve-chart", traces, {{
  margin: {{ t: 20, b: 60, l: 60, r: 20 }},
  xaxis: {{
    title: "Championship Round",
    categoryorder: "array",
    categoryarray: rounds,
    fixedrange: true
  }},
  yaxis: {{
    title: "% Reaching Round",
    range: [0, 105],
    ticksuffix: "%",
    fixedrange: true
  }},
  legend: {{
    orientation: "h",
    y: -0.18,
    x: 0.5,
    xanchor: "center",
    font: {{ size: 10 }},
    tracegroupgap: 2
  }},
  showlegend: true,
  plot_bgcolor: "#f9f9f9",
  paper_bgcolor: "#ffffff"
}}, {{ responsive: true, displayModeBar: false }});

}})();
</script>
"""

    body = f"""
<div class="section">
  <h2 style="margin-bottom:6px">Bracket Odds by Seed</h2>
  <p style="color:#555;font-size:14px;margin-bottom:18px">
    Percentage of wrestlers at each seed who reached each championship bracket round.
    Only merit-based seeds included: top 12 in 2013, top 16 in 2014–2018, all 33 from 2019.
    Gray cells = zero occurrences. Hover for exact ratio.
  </p>
  <div id="heatmap-chart" style="width:100%;height:880px"></div>
</div>

<div class="section" style="margin-top:24px">
  <h2 style="margin-bottom:6px">Bracket Survival Curves</h2>
  <p style="color:#555;font-size:14px;margin-bottom:18px">
    Each line shows one seed's survival rate through the championship bracket.
    Color gradient: <span style="color:#27ae60;font-weight:600">green = seed 1</span>
    → <span style="color:#c83232;font-weight:600">red = seed 33</span>.
  </p>
  <div id="curve-chart" style="width:100%;height:520px"></div>
</div>

{js}
"""
    return html_shell("NCAA D1 Wrestling — Bracket Odds", "ncaa_bracket_odds.html", body)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Loading data...")
    wrestlers, matches = load_data()

    print("Building main report...")
    html = build_report(wrestlers, matches)
    DEFAULT_OUT.write_text(html, encoding="utf-8")
    print(f"  → {DEFAULT_OUT}")

    print("Building team analysis page...")
    team_html = build_team_page(wrestlers)
    DEFAULT_TEAM_OUT.write_text(team_html, encoding="utf-8")
    print(f"  → {DEFAULT_TEAM_OUT}")

    print("Building team leaderboard page...")
    leaderboard_html = build_leaderboard_page(wrestlers)
    DEFAULT_LEADERBOARD_OUT.write_text(leaderboard_html, encoding="utf-8")
    print(f"  → {DEFAULT_LEADERBOARD_OUT}")

    print("Building conference analysis page...")
    conf_html = build_conference_analysis_page(wrestlers)
    DEFAULT_CONF_OUT.write_text(conf_html, encoding="utf-8")
    print(f"  → {DEFAULT_CONF_OUT}")

    print("Building conference leaderboard page...")
    conf_lb_html = build_conference_leaderboard_page(wrestlers)
    DEFAULT_CONF_LB_OUT.write_text(conf_lb_html, encoding="utf-8")
    print(f"  → {DEFAULT_CONF_LB_OUT}")

    print("Building bracket odds page...")
    bracket_html = build_bracket_odds_page(wrestlers)
    DEFAULT_BRACKET_OUT.write_text(bracket_html, encoding="utf-8")
    print(f"  → {DEFAULT_BRACKET_OUT}")


if __name__ == "__main__":
    main()
