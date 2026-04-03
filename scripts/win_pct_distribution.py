#!/usr/bin/env python3
"""
Bell curve of career winning percentages for KY wrestlers with 50+ career matches.
Data sourced from the all-time career wins leaderboard.
"""

import json
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
from scipy.stats import gaussian_kde

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "frontend/hs-ky-ui/public/data/leaderboards/boys/2026/career_wins.json"
MIN_MATCHES = 50

with DATA_FILE.open(encoding="utf-8") as f:
    data = json.load(f)

qualified = [
    e for e in data
    if e.get("career_wins", 0) + e.get("career_losses", 0) >= MIN_MATCHES
    and e.get("win_pct") is not None
]

win_pcts = np.array([e["win_pct"] for e in qualified])

mean = win_pcts.mean()
median = np.median(win_pcts)
std = win_pcts.std()

print(f"Wrestlers with {MIN_MATCHES}+ matches: {len(win_pcts)}")
print(f"Mean win %:   {mean:.3f}  ({mean*100:.1f}%)")
print(f"Median win %: {median:.3f}  ({median*100:.1f}%)")
print(f"Std dev:      {std:.3f}")

# ── KDE (smooth bell curve) ───────────────────────────────────────────────────
kde = gaussian_kde(win_pcts, bw_method=0.08)
x = np.linspace(0, 1, 500)
y = kde(x)

# ── Colors ────────────────────────────────────────────────────────────────────
CURVE_COLOR = "#1a56a4"
FILL_COLOR  = "#1a56a4"
MEAN_COLOR  = "#e63946"

fig, ax = plt.subplots(figsize=(11, 6))
fig.patch.set_facecolor("#f8f9fa")
ax.set_facecolor("#f8f9fa")

# Shaded area under curve
ax.fill_between(x, y, alpha=0.18, color=FILL_COLOR, zorder=2)
ax.plot(x, y, color=CURVE_COLOR, linewidth=2.5, zorder=3)

# Mean line
ax.axvline(mean, color=MEAN_COLOR, linewidth=1.8, linestyle="--", zorder=4,
           label=f"Mean  {mean*100:.1f}%")
ax.axvline(median, color="#2a9d8f", linewidth=1.8, linestyle=":", zorder=4,
           label=f"Median  {median*100:.1f}%")

# ── X axis — format as percentages ───────────────────────────────────────────
ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x*100:.0f}%"))
ax.set_xlim(0, 1)
ax.set_ylim(bottom=0)

# Light vertical grid at 25/50/75%
for xv in [0.25, 0.50, 0.75]:
    ax.axvline(xv, color="#cccccc", linewidth=0.8, zorder=1)

ax.set_xlabel("Career Winning Percentage", fontsize=12, labelpad=10)
ax.set_ylabel("Density", fontsize=12, labelpad=10)
ax.set_title(
    f"Career Win % Distribution  ·  KY Wrestlers with {MIN_MATCHES}+ Career Matches  (n={len(win_pcts):,})",
    fontsize=14, fontweight="bold", pad=16, color="#222222"
)

for spine in ["top", "right"]:
    ax.spines[spine].set_visible(False)
ax.spines["left"].set_color("#cccccc")
ax.spines["bottom"].set_color("#cccccc")

ax.legend(fontsize=11, framealpha=0.85, edgecolor="#dddddd")

plt.tight_layout()
out = ROOT / "scripts" / "win_pct_distribution.png"
plt.savefig(out, dpi=150, bbox_inches="tight")
print(f"Saved → {out}")
plt.show()
