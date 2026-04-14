#!/usr/bin/env python3
"""
KY Wrestling participation growth chart (2016–2026).
Shows wrestler count (line) and match count (shaded area) on dual y-axes.
Match count = deduped matches containing at least one KY wrestler,
sourced from mt/processed_data/hs_ky_boys per season.
"""

import json
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_ROOT = ROOT / "mt" / "processed_data" / "hs_ky_boys"
SEASONS = list(range(2016, 2027))


def compute_stats(seasons):
    wrestler_counts, match_counts = [], []
    for season in seasons:
        season_dir = PROCESSED_ROOT / str(season)
        seen = set()
        active_wrestlers = 0
        for team_file in season_dir.glob("*.json"):
            with team_file.open(encoding="utf-8") as f:
                data = json.load(f)
            for w in data.get("roster", []):
                matches = w.get("matches", [])
                if matches:
                    active_wrestlers += 1
                for m in matches:
                    key = (
                        m.get("date", ""),
                        m.get("weight", ""),
                        tuple(sorted([m.get("winner_name", ""), m.get("loser_name", "")])),
                    )
                    seen.add(key)
        wrestler_counts.append(active_wrestlers)
        match_counts.append(len(seen))
    return wrestler_counts, match_counts


wrestler_counts, match_counts = compute_stats(SEASONS)

for s, wc, mc in zip(SEASONS, wrestler_counts, match_counts):
    print(f"{s}: {wc:,} wrestlers | {mc:,} matches | {mc/wc:.1f} per wrestler")

# ── Colors ───────────────────────────────────────────────────────────────────
LINE_COLOR = "#1a56a4"
AREA_COLOR = "#f59e0b"

fig, ax1 = plt.subplots(figsize=(11, 6))
fig.patch.set_facecolor("#f8f9fa")
ax1.set_facecolor("#f8f9fa")

# ── Match count — shaded area (right axis) ───────────────────────────────────
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

# ── Wrestler count — line (left axis) ────────────────────────────────────────
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
    ax1.annotate(f"{wc:,}", (season, wc), textcoords="offset points",
                 xytext=(0, 9), ha="center", fontsize=7.5, color=LINE_COLOR)
    ax2.annotate(f"{mc:,}", (season, mc), textcoords="offset points",
                 xytext=(0, -13), ha="center", fontsize=7.5, color=AREA_COLOR)

# ── Title & legend ────────────────────────────────────────────────────────────
ax1.set_title("KY Wrestling Participation  ·  2016 – 2026",
              fontsize=15, fontweight="bold", pad=16, color="#222222")

from matplotlib.lines import Line2D
from matplotlib.patches import Patch
legend_handles = [
    Line2D([0], [0], color=LINE_COLOR, linewidth=2.5, marker="o", markersize=6, label="Wrestlers"),
    Patch(facecolor=AREA_COLOR, alpha=0.5, label="Matches (deduped)"),
]
ax1.legend(handles=legend_handles, loc="upper left", fontsize=10,
           framealpha=0.85, edgecolor="#dddddd")

plt.tight_layout()
out = ROOT / "scripts" / "growth_chart.png"
plt.savefig(out, dpi=150, bbox_inches="tight")
print(f"\nSaved → {out}")
plt.show()
