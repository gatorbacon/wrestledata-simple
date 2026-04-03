#!/usr/bin/env python3
"""
Boyle County wrestling participation chart (2016–2026).
Wrestler count (line) and match count (shaded area) on dual y-axes.
"""

import json
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

ROOT = Path(__file__).resolve().parent.parent
ACC_ROOT = ROOT / "data" / "season_accomplishments"
SEASONS = list(range(2016, 2027))
GENDERS = ["boys", "girls"]
TEAM_FILTER = "boyle county"


def load_season(gender: str, season: int):
    path = ACC_ROOT / gender / str(season) / "season_accomplishments.json"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return json.load(f).get("wrestlers", [])


def compute_stats(seasons):
    wrestler_counts, match_counts = [], []
    for season in seasons:
        wrestlers = []
        for gender in GENDERS:
            wrestlers.extend(load_season(gender, season))
        active = [
            w for w in wrestlers
            if TEAM_FILTER in (w.get("team") or "").lower()
            and w.get("record")
            and (w["record"]["wins"] + w["record"]["losses"]) > 0
        ]
        wrestler_counts.append(len(active))
        # Each win/loss in a wrestler's record = one match they competed in.
        # Don't divide by 2 — for a single team, opponents are mostly external
        # so each match only appears once in the team's records.
        total_bouts = sum(w["record"]["wins"] + w["record"]["losses"] for w in active)
        match_counts.append(total_bouts)
    return wrestler_counts, match_counts


wrestler_counts, match_counts = compute_stats(SEASONS)

# Print the ratio for each year
print(f"{'Season':<8} {'Wrestlers':<12} {'Matches':<12} {'Matches/Wrestler'}")
for s, wc, mc in zip(SEASONS, wrestler_counts, match_counts):
    ratio = mc / wc if wc else 0
    print(f"{s:<8} {wc:<12} {mc:<12} {ratio:.1f}")

# ── Colors ────────────────────────────────────────────────────────────────────
LINE_COLOR = "#1a56a4"
AREA_COLOR = "#f59e0b"

fig, ax1 = plt.subplots(figsize=(11, 6))
fig.patch.set_facecolor("#f8f9fa")
ax1.set_facecolor("#f8f9fa")

# ── Match count — shaded area (right axis) ────────────────────────────────────
ax2 = ax1.twinx()
ax2.fill_between(SEASONS, match_counts, alpha=0.25, color=AREA_COLOR, zorder=2)
ax2.plot(SEASONS, match_counts, color=AREA_COLOR, linewidth=1.5, alpha=0.7, zorder=3)
ax2.set_ylabel("Matches", fontsize=12, color=AREA_COLOR, labelpad=10)
ax2.tick_params(axis="y", colors=AREA_COLOR)
ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
ax2.set_ylim(bottom=0)
ax2.spines["right"].set_color(AREA_COLOR)
ax2.spines["right"].set_alpha(0.5)
for spine in ["top", "left", "bottom"]:
    ax2.spines[spine].set_visible(False)

# ── Wrestler count — line (left axis) ─────────────────────────────────────────
ax1.plot(SEASONS, wrestler_counts, color=LINE_COLOR, linewidth=2.5, marker="o",
         markersize=6, zorder=4)
ax1.set_ylabel("Wrestlers", fontsize=12, color=LINE_COLOR, labelpad=10)
ax1.tick_params(axis="y", colors=LINE_COLOR)
ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
ax1.set_ylim(bottom=0)
ax1.spines["left"].set_color(LINE_COLOR)
ax1.spines["left"].set_alpha(0.5)
for spine in ["top", "right"]:
    ax1.spines[spine].set_visible(False)
ax1.spines["bottom"].set_color("#cccccc")

# ── X axis ────────────────────────────────────────────────────────────────────
ax1.set_xticks(SEASONS)
ax1.set_xticklabels([str(s) for s in SEASONS], fontsize=10)
ax1.set_xlim(SEASONS[0] - 0.4, SEASONS[-1] + 0.4)

# ── Data labels ───────────────────────────────────────────────────────────────
for season, wc, mc in zip(SEASONS, wrestler_counts, match_counts):
    ax1.annotate(f"{wc}", (season, wc), textcoords="offset points",
                 xytext=(0, 9), ha="center", fontsize=7.5, color=LINE_COLOR)
    ax2.annotate(f"{mc}", (season, mc), textcoords="offset points",
                 xytext=(0, -13), ha="center", fontsize=7.5, color=AREA_COLOR)

# ── Title & legend ─────────────────────────────────────────────────────────────
ax1.set_title("Boyle County Wrestling  ·  2016 – 2026  (wrestlers with ≥1 match)",
              fontsize=14, fontweight="bold", pad=16, color="#222222")

from matplotlib.lines import Line2D
from matplotlib.patches import Patch
legend_handles = [
    Line2D([0], [0], color=LINE_COLOR, linewidth=2.5, marker="o", markersize=6, label="Wrestlers"),
    Patch(facecolor=AREA_COLOR, alpha=0.5, label="Matches"),
]
ax1.legend(handles=legend_handles, loc="upper left", fontsize=10,
           framealpha=0.85, edgecolor="#dddddd")

plt.tight_layout()
out = ROOT / "scripts" / "growth_chart_boyle.png"
plt.savefig(out, dpi=150, bbox_inches="tight")
print(f"\nSaved → {out}")
plt.show()
