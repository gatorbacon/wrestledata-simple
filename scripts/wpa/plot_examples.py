#!/usr/bin/env python3
"""
WPA step 11 -- example charts (spec Section 8): the winner's WP over time for a handful of bouts, as a step plot with
the biggest swings annotated (event, wrestler, WPA). Reads data/wpa/output/match_wp_curves.parquet and
events_wpa.parquet (run compute_wpa.py, then build_outputs.py).

Default examples (picked from the data, 2026-09-30):
  upset        2021 197 R32  #31 Owen Pentz pins #2 Eric Schultz (3% at the opening whistle)
  comeback     2023 125 SF   Matt Ramos over Spencer Lee (Ramos' low point 0.3%)
  riding time  2024 157 QF   #6 Daniel Cardenas over #3 Meyer Shapiro 5-4 on the riding-time point (39% at 0:30)
  tiebreaker   2023 133 C_R4 Jesse Mendez over Lucas Byrd, TB-1 (the overtime model)

Usage: .venv/bin/python scripts/wpa/plot_examples.py [--bout BOUT_KEY ...]
Writes data/wpa/reports/img/examples/{slug}.png
"""
import argparse
import re
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "data/wpa/output"
IMG = ROOT / "data/wpa/reports/img/examples"
EXAMPLES = {"ncaa|NCAA|2021|197|16": "upset", "ncaa|NCAA|2023|125|53": "comeback",
            "ncaa|NCAA|2024|157|39": "riding time", "ncaa|NCAA|2023|133|51": "tiebreaker"}
LABEL = {"takedown": "TD", "escape": "Escape", "reversal": "Reversal", "near_fall": "NF", "penalty": "Penalty pt",
         "fall": "Fall", "tech_fall": "Tech fall", "rt_lock": "RT locked", "regulation_end": "RT point",
         "ot_choice": "Picks", "ot_riding_time": "TB riding time", "overtime": "Later OT", "choose": "Picks",
         "defer": "Defers", "toss": "Wins toss", "injury": "Injury default", "dq": "DQ"}
INK, MUT, GRID, LINE = "#1f2328", "#5b636e", "#d5d9de", "#1f4e79"


def last(name):
    return name.split()[-1]


def mmss(el):
    if el <= 420:
        t = int(round(el))
        return f"{t // 60}:{t % 60:02d}"
    if el <= 540:
        return f"SV {int(el - 420)}s"
    return "TB"


def plot(key, kind_label, cur, ev, bouts):
    c = cur[cur["bout_key"] == key].sort_values("order")
    e = ev[ev["bout_key"] == key].sort_values("seq")
    b = bouts.loc[key]
    x, y = c["elapsed_s"].to_numpy(), 100 * c["wp_w"].to_numpy()
    xmax = max(420.0, x.max())
    fig, ax = plt.subplots(figsize=(11, 5.4), dpi=150)
    fig.subplots_adjust(left=0.07, right=0.97, top=0.78, bottom=0.12)
    ax.plot(x, y, color=LINE, lw=2, solid_joinstyle="miter", zorder=4)
    ax.axhline(50, color="#9aa3ad", lw=1)
    breaks = [180, 300, 420] + ([540] if xmax > 540 else []) + ([570] if xmax > 570 else [])
    for bx in breaks:
        if bx < xmax:
            ax.axvline(bx, color=GRID, lw=1, ls=":")
    ticks = [90, 240, 360] + ([480] if xmax > 425 else []) + ([570] if xmax > 540 else [])
    labs = ["1st", "2nd", "3rd"] + (["SV" if b["year"] >= 2022 else "OT"] if xmax > 425 else []) + \
        (["TB"] if xmax > 540 else [])
    ax.set_xticks(ticks)
    ax.set_xticklabels(labs, color=MUT)
    ax.set_xlim(0, xmax)
    ax.set_ylim(0, 100)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"], color=MUT)
    ax.set_ylabel(f"{last(b['w_name'])}'s win probability", color=MUT)
    for s_ in ("top", "right"):
        ax.spines[s_].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(length=0)
    # annotate the biggest swings (not clock stretches), at most 7, in time order
    big = e[(e["event_type"] != "clock") & (e["wpa_w"].abs() >= 0.04)].copy()
    big = big.reindex(big["wpa_w"].abs().sort_values(ascending=False).index).head(7)
    rtp = e[(e["event_type"] == "regulation_end") & (e["category"] == "riding_time")]   # the RT point: always shown
    big = pd.concat([big, rtp[~rtp.index.isin(big.index)]])
    big = big.sort_values("seq")
    placed = []                                      # (x, y) of labels already placed
    for i, (_, r) in enumerate(big.iterrows()):
        et = r["event_type"]
        who = last(r["beneficiary"]) if et == "penalty" and r["beneficiary"] else last(r["wrestler"])
        lab = LABEL.get(et, et.replace("_", " "))
        if et == "near_fall" and isinstance(r["subtype"], str) and r["subtype"].startswith("nf"):
            lab = f"NF{r['subtype'][2:]}"
        xe = None
        yb, ya = 100 * r["wp_w_before"], 100 * r["wp_w_after"]
        cand = c[(c["event_type"] == et) & (np.isclose(c["wp_w"], r["wp_w_after"]))]
        if len(cand):
            xe = float(cand["elapsed_s"].iloc[0])
        if xe is None:
            continue
        up = ya >= yb
        if up and ya > 80:
            up = False                        # no room above: label below the line
        elif not up and ya < 20:
            up = True
        step = 14 if up else -14
        ty = ya + (9 if up else -9)
        # move away from labels already placed nearby (either direction) until there is room
        while any(abs(px - xe) < 60 and abs(py - ty) < 12 for px, py in placed) and 4 < ty < 96:
            ty += step
        ty = min(max(ty, 4), 96)
        placed.append((xe, ty))
        tx, ha = (xe - 6, "right") if xe > xmax - 40 else (xe, "center")
        txt = f"{lab} · {who}\n{'+' if r['wpa_w'] >= 0 else '−'}{abs(100 * r['wpa_w']):.0f} pts"
        if et == "regulation_end" and abs(r["wpa_w"]) < 0.005:
            txt = f"{lab} · {who}\n(already priced in)"
        ax.annotate(txt, (xe, ya), xytext=(tx, ty), ha=ha, va="bottom" if up else "top", fontsize=8.5,
                    color=INK, arrowprops=dict(arrowstyle="-", color="#9aa3ad", lw=0.8),
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.85), zorder=2)
    i_lo = int(np.argmin(y))
    ax.scatter([x[i_lo]], [y[i_lo]], s=36, facecolor="white", edgecolor=INK, zorder=5)
    near_end = x[i_lo] > 0.9 * xmax
    ax.annotate(f"low {y[i_lo]:.1f}%", (x[i_lo], y[i_lo]), xytext=(-8 if near_end else 8, 8),
                textcoords="offset points", fontsize=8.5, color=INK, ha="right" if near_end else "left")
    sd = lambda v: f"#{int(v)} " if pd.notna(v) else "unseeded "  # noqa: E731
    fig.text(0.07, 0.93, f"{kind_label.capitalize()}: {b['w_name']} over {b['l_name']}", fontsize=15,
             fontweight="bold", color=INK)
    fig.text(0.07, 0.87, f"{b['year']} NCAA Championships, {b['weight']} lbs, {b['round']} · {sd(b['w_seed_raw'])}"
             f"over {sd(b['l_seed_raw'])}· {b['result_type']} {b['final_w']}-{b['final_l']} · "
             f"opening WP {y[0]:.0f}%", fontsize=10.5, color=MUT)
    fig.text(0.07, 0.835, f"Labels: event · who · change in {last(b['w_name'])}'s win probability (points)",
             fontsize=9, color=MUT)
    slug = re.sub(r"[^a-z0-9]+", "_", f"{kind_label}_{b['year']}_{b['weight']}_{last(b['w_name'])}_"
                  f"{last(b['l_name'])}".lower())
    IMG.mkdir(parents=True, exist_ok=True)
    out = IMG / f"{slug}.png"
    fig.savefig(out, facecolor="white")
    plt.close(fig)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bout", nargs="*")
    a = ap.parse_args()
    keys = {k: "example" for k in a.bout} if a.bout else EXAMPLES
    cur = pd.read_parquet(OUT / "match_wp_curves.parquet", filters=[("bout_key", "in", list(keys))])
    ev = pd.read_parquet(OUT / "events_wpa.parquet", filters=[("bout_key", "in", list(keys))])
    bouts = pd.read_csv(ROOT / "data/wpa/states/ncaa_bouts.csv", low_memory=False).set_index("bout_key")
    for k, lab in keys.items():
        print(plot(k, lab, cur, ev, bouts).relative_to(ROOT))


if __name__ == "__main__":
    main()
