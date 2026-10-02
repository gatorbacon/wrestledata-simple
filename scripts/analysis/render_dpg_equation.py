"""Renders the DPG formula as a typeset equation (matplotlib mathtext, Computer Modern font).

Matches scripts/mat_value/compute_mat_value.py (result_to_signed, interpolate_mu, shrink_opponent_avg) and
compute_all_mat_values.py (per-match expected = -opp_shrunk, season = mean). If that formula changes, update
this and re-run:  .venv/bin/python scripts/analysis/render_dpg_equation.py
Writes data/analysis/dpg_equation.{png,svg} and the About page copy frontend/wrestledata-ui/public/assets/dpg_equation.svg.
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams.update({"mathtext.fontset": "cm", "font.family": "serif", "font.serif": ["cmr10", "DejaVu Serif"],
                     "axes.formatter.use_mathtext": True})
fig = plt.figure(figsize=(11, 8.2), dpi=200)
fig.patch.set_facecolor("white")
ink, muted = "#111111", "#555555"
def eq(y, s, size=22, x=0.06, c=ink):
    fig.text(x, y, s, fontsize=size, color=c, va="center")
def note(y, s, x=0.10):
    fig.text(x, y, s, fontsize=13.5, color=muted, va="center", family="serif")

fig.text(0.06, 0.94, "DPG  (Dual Points Gained)", fontsize=24, color=ink, va="center", family="serif", weight="bold")
fig.text(0.06, 0.895, "per-match result vs. what a typical wrestler gets against that same opponent, averaged over the season",
         fontsize=12.5, color=muted, va="center", family="serif", style="italic")

eq(0.80, r"$\mathrm{DPG}_w \;=\; \dfrac{1}{N_w}\sum_{i=1}^{N_w}\left(\,s_i \;-\; E_i\,\right)\qquad E_i \;=\; -\,\hat{\theta}_{o(i)}$", 25)
note(0.705, "$N_w$ = the wrestler's matches (forfeits and medical forfeits excluded);  $o(i)$ = opponent in match $i$")

eq(0.635, r"$s_i \;=\; \pm\,v_i, \qquad v_i \in \{\,3\ (\mathrm{DEC}),\ 4\ (\mathrm{MD}),\ 5\ (\mathrm{TF}),\ 6\ (\mathrm{FALL,\ INJ,\ DQ})\,\}$", 21)
note(0.575, "$+$ for a win, $-$ for a loss  (sudden victory and tiebreaker wins count as decisions)")

eq(0.475, r"$\hat{\theta}_o \;=\; \dfrac{n_o\,\bar{s}_o \;+\; k\,\mu(r_o)}{n_o \;+\; k}, \qquad k = 20$", 23)
note(0.40, r"$\bar{s}_o$ = opponent's average signed result over his $n_o$ matches;  $r_o$ = opponent's rank")
note(0.365, "(an opponent with few matches is pulled toward the average for his rank)")

eq(0.295, r"$\mu(r) \;=\; \mu_{[a,b]} \;+\; \dfrac{r-a}{b-a}\,\left(\mu_{[b,c]} - \mu_{[a,b]}\right), \qquad a \leq r \leq b$", 22)
eq(0.195, r"$a,b,c \in \{\,1,\ 10,\ 30,\ 50,\ 100,\ 150,\ 200\,\}$", 18, x=0.10)
note(0.125, r"$\mu_{[a,b]}$ = average signed result of every wrestler ranked $a$ to $b$, at that weight, that season (recomputed every run)")

fig.text(0.06, 0.045, "So each match adds  $s_i + \\hat{\\theta}_{o(i)}$:  beating a strong opponent ($\\hat{\\theta}>0$) is worth more than the raw 3-6 points.",
         fontsize=13, color=ink, va="center", family="serif")
out = str(ROOT / "data/analysis/dpg_equation")
fig.savefig(out + ".png", facecolor="white")
fig.savefig(out + ".svg", facecolor="white")
shutil.copy(out + ".svg", ROOT / "frontend/wrestledata-ui/public/assets/dpg_equation.svg")
print(out)
