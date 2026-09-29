#!/usr/bin/env python3
"""
WPA step 4 -- sparsity audit (spec 3.2), plus the era comparison of spec Section 4 and the data-priority question TJ
raised before step 2 (build on 2024-26 only, or pool with older eras / conference data?).

Reads the step-3 observations (data/wpa/table/{ncaa,conf}_obs.csv.gz, build_table.py) and writes
data/wpa/reports/sparsity_audit.md with heatmaps in data/wpa/reports/img/. Read-only otherwise.

"Thin" = a cell with fewer than 50 distinct bouts (n_matches < 50), the spec's threshold. The number that matters is
the share of observed match-moments that land in thin cells, not the share of cells.

Usage: .venv/bin/python scripts/wpa/sparsity_audit.py
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts/wpa"))
import build_table as BT  # noqa: E402

TAB = ROOT / "data/wpa/table"
REP = ROOT / "data/wpa/reports/sparsity_audit.md"
IMG = ROOT / "data/wpa/reports/img"
THIN = 50
KEY_NO_ERA = [k for k in BT.KEY if k != "era_group"]


def pct(a, b, d=1):
    return f"{100 * a / b:.{d}f}%" if b else "—"


def cells_of(two, key):
    """Per-observation n_matches of its cell, plus the cell table."""
    t = two.groupby(key, observed=True).agg(n_obs=("win", "size"), n_matches=("bout_key", "nunique"),
                                             wins=("win", "sum")).reset_index()
    return t


def neighbor_matches(tab, key):
    """For each cell: n_matches summed over itself and its margin +/-1, t_bin +/-1 neighbours (same everything
    else) -- the spec 3.3 smoothing neighbourhood. An upper bound on distinct bouts (a bout can sit in two
    neighbouring cells), fine for 'are even the neighbours empty?'."""
    idx = tab.set_index(key)["n_matches"]
    lookup = idx.to_dict()
    ki = {k: i for i, k in enumerate(key)}
    out = []
    for row in tab[key].itertuples(index=False, name=None):
        tot = 0
        for dm in (-1, 0, 1):
            for dt in (-1, 0, 1):
                r = list(row)
                r[ki["margin"]] += dm
                r[ki["t_bin"]] += dt
                tot += lookup.get(tuple(r), 0)
        out.append(tot)
    return np.array(out)


def summarize(two, key, label, rows):
    """Sparsity metrics for one table definition. Appends a summary dict to rows and returns the cell table with
    per-cell neighbour volume."""
    tab = cells_of(two, key)
    tab["nb_matches"] = neighbor_matches(tab, key)
    m = two.merge(tab[key + ["n_matches", "nb_matches"]], on=key, how="left")
    thin = m["n_matches"] < THIN
    smp = m["source"] == "sample"
    late_close = (m["t_rem"] <= 120) & (m["margin"].abs() <= 3)
    empty_nb = m["nb_matches"] < THIN
    rows.append({
        "Table": label, "Bouts": two["bout_key"].nunique(), "Cells": len(tab),
        "Cells thin": pct((tab["n_matches"] < THIN).sum(), len(tab)),
        "Moments in thin cells": pct(thin.sum(), len(m)),
        "10-s samples in thin cells": pct((thin & smp).sum(), smp.sum()),
        "P3, within 3: in thin cells": pct((thin & late_close).sum(), late_close.sum()),
        "Moments where cell + neighbours < 50": pct(empty_nb.sum(), len(m)),
    })
    return tab, m


def heatmaps(m, title, fname):
    """Share of observed moments in thin cells, per margin x time-left pixel, faceted by position and rt_status."""
    m = m[m["pos"].isin(["neutral", "A_top", "A_bottom"]) & (m["margin"].abs() <= 8)]
    poss = ["neutral", "A_top", "A_bottom"]
    stats = ["live", "locked_none", "locked_in", "locked_out"]
    fig, axes = plt.subplots(len(stats), len(poss), figsize=(13, 12), sharex=True, sharey=True)
    for i, rs in enumerate(stats):
        for j, pos in enumerate(poss):
            ax = axes[i, j]
            d = m[(m["pos"] == pos) & (m["rt_status"] == rs)]
            grid = np.full((17, 42), np.nan)
            vol = np.zeros((17, 42))
            if len(d):
                g = d.assign(thin=d["n_matches"] < THIN).groupby(["margin", "t_bin"])["thin"].agg(["mean", "size"])
                for (mg, tb), r in g.iterrows():
                    grid[mg + 8, tb] = r["mean"]
                    vol[mg + 8, tb] = r["size"]
            grid[vol < 5] = np.nan
            im = ax.imshow(grid, origin="lower", aspect="auto", cmap="magma_r", vmin=0, vmax=1,
                           extent=[0, 420, -8.5, 8.5])
            ax.invert_xaxis()
            ax.set_title(f"{pos} · {rs}  (n={len(d):,})", fontsize=9)
            if j == 0:
                ax.set_ylabel("margin (A − B)")
            if i == len(stats) - 1:
                ax.set_xlabel("time left in regulation (s)")
            for x in (240, 120):
                ax.axvline(x, color="#888", lw=0.6)
    fig.suptitle(title + "\nshare of observed moments that sit in a thin cell (< 50 bouts); blank = fewer than 5 "
                 "moments", fontsize=11)
    fig.colorbar(im, ax=axes, shrink=0.6, label="share in thin cells")
    IMG.mkdir(parents=True, exist_ok=True)
    fig.savefig(IMG / fname, dpi=110, bbox_inches="tight")
    plt.close(fig)


def volume_map(m, title, fname):
    """Distinct bouts per margin x time-left pixel (all other state dims pooled), faceted by position."""
    m = m[m["pos"].isin(["neutral", "A_top", "A_bottom"]) & (m["margin"].abs() <= 8)]
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.2), sharey=True)
    for j, pos in enumerate(["neutral", "A_top", "A_bottom"]):
        d = m[m["pos"] == pos]
        g = d.groupby(["margin", "t_bin"])["bout_key"].nunique()
        grid = np.full((17, 42), np.nan)
        for (mg, tb), v in g.items():
            grid[mg + 8, tb] = np.log10(v)
        im = axes[j].imshow(grid, origin="lower", aspect="auto", cmap="viridis", vmin=0, vmax=3.5,
                            extent=[0, 420, -8.5, 8.5])
        axes[j].invert_xaxis()
        axes[j].set_title(pos, fontsize=10)
        axes[j].set_xlabel("time left in regulation (s)")
        for x in (240, 120):
            axes[j].axvline(x, color="#ddd", lw=0.6)
    axes[0].set_ylabel("margin (A − B)")
    fig.suptitle(title + " — distinct bouts per (margin, 10-s bin), other state dimensions pooled (log10)",
                 fontsize=10)
    cb = fig.colorbar(im, ax=axes, shrink=0.8)
    cb.set_ticks([0, 1, 2, 3])
    cb.set_ticklabels(["1", "10", "100", "1,000"])
    fig.savefig(IMG / fname, dpi=110, bbox_inches="tight")
    plt.close(fig)


def md_table(rows):
    cols = list(rows[0])
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" if i == 0 else "---:" for i in range(len(cols))) + "|"]
    for r in rows:
        out.append("| " + " | ".join(f"{v:,}" if isinstance(v, (int, np.integer)) else str(v) for v in r.values()) + " |")
    return "\n".join(out)


def main():
    ncaa = pd.read_csv(TAB / "ncaa_obs.csv.gz")
    conf = pd.read_csv(TAB / "conf_obs.csv.gz")
    two_n = BT.both_sides(ncaa)
    two_c = BT.both_sides(conf)
    L = []
    A = L.append
    A("# WPA step 4 — sparsity audit (spec 3.2)\n")
    A("Generated by `scripts/wpa/sparsity_audit.py` from the step-3 observations (`scripts/wpa/build_table.py` → "
      "`data/wpa/table/`). **Thin** = a cell with fewer than 50 distinct bouts, the spec's threshold. A *moment* is one "
      "observation: a 10-second sample or the state just before / after an event, counted from both wrestlers' sides. "
      "Only bouts with `state_table_ok` (step 2) are used.\n")
    A(f"- NCAA: {ncaa['bout_key'].nunique():,} bouts, {len(ncaa):,} moments per side "
      f"({(ncaa['source'] == 'sample').sum():,} 10-s samples, {(ncaa['source'] != 'sample').sum():,} event "
      f"before/after states).")
    A(f"- Conference (for the E3 question only — the spec folds conference in at step 10): "
      f"{conf['bout_key'].nunique():,} bouts, {len(conf):,} moments per side.\n")

    # ---- the spec table, and the alternatives
    rows = []
    tab_a, m_a = summarize(two_n, BT.KEY, "A. Spec key, eras split (E12 / E3) — NCAA", rows)
    summarize(two_n, KEY_NO_ERA, "B. Spec key, eras pooled — NCAA", rows)
    e3n = two_n[two_n["era_group"] == "E3"]
    tab_c, m_c = summarize(e3n, BT.KEY, "C. E3 only — NCAA", rows)
    e3nc = pd.concat([e3n, two_c[two_c["era_group"] == "E3"]], ignore_index=True)
    tab_d, m_d = summarize(e3nc, BT.KEY, "D. E3 only — NCAA + conference", rows)
    summarize(e3n, [k for k in BT.KEY if k != "rt_bin"], "C′. E3 NCAA, without rt_bin", rows)
    summarize(e3n, [k for k in BT.KEY if k not in ("rt_bin", "choice")], "C″. E3 NCAA, without rt_bin or choice", rows)
    e12n = two_n[two_n["era_group"] == "E12"]
    summarize(e12n, BT.KEY, "E. E12 only — NCAA (2015–23)", rows)

    def rt_last(two, h):
        t = two.copy()
        t.loc[t["t_rem"] > h, "rt_bin"] = 0
        return t
    summarize(rt_last(e3n, 60), BT.KEY, "F. E3 NCAA, rt_bin only in the last 60 s", rows)
    summarize(rt_last(e3nc, 60), BT.KEY, "G. E3 NCAA + conference, rt_bin only in the last 60 s", rows)

    A("## Headline\n")
    A(md_table(rows))
    A("\nColumns: *Moments in thin cells* is the spec's key number (all observations); *10-s samples* counts only the "
      "fixed-cadence samples (time-uniform); *P3, within 3* restricts to the third period with the margin within 3 "
      "points — where win probability actually moves and where WPA credit is decided; *cell + neighbours < 50* is "
      "the spec 3.4 test: moments whose cell AND its margin ±1 / time ±10 s neighbours together hold fewer than 50 "
      "bouts, i.e. where smoothing alone has nothing to borrow.\n")

    # ---- histogram (table A)
    A("## Cells by number of bouts (table A)\n")
    bins = [1, 2, 5, 10, 25, 50, 100, 250, 500, 1000, 10 ** 9]
    labels = ["1", "2–4", "5–9", "10–24", "25–49", "50–99", "100–249", "250–499", "500–999", "1,000+"]
    cut = pd.cut(tab_a["n_matches"], bins=bins, right=False, labels=labels)
    mm = m_a.assign(b=pd.cut(m_a["n_matches"], bins=bins, right=False, labels=labels))
    A("| Bouts in cell | Cells | Share of cells | Share of moments |\n|---|---:|---:|---:|")
    for lab in labels:
        nc = (cut == lab).sum()
        A(f"| {lab} | {nc:,} | {pct(nc, len(tab_a))} | {pct((mm['b'] == lab).sum(), len(mm))} |")
    A("")

    # ---- where the thin moments are (table A, by era and slice)
    A("## Where the thin moments are (table A)\n")
    A("| Slice | Moments | In thin cells | Cell + neighbours < 50 |\n|---|---:|---:|---:|")
    slices = [
        ("E12, all", m_a["era_group"] == "E12"), ("E3, all", m_a["era_group"] == "E3"),
        ("Period 1", m_a["period"] == 1), ("Period 2", m_a["period"] == 2), ("Period 3", m_a["period"] == 3),
        ("Break states (pending choice)", m_a["pos"].str.startswith("pending")),
        ("rt_status live", m_a["rt_status"] == "live"),
        ("rt_status locked (any)", m_a["rt_status"] != "live"),
        ("E3, P3, within 3", (m_a["era_group"] == "E3") & (m_a["t_rem"] <= 120) & (m_a["margin"].abs() <= 3)),
        ("E3, last 30 s, within 3", (m_a["era_group"] == "E3") & (m_a["t_rem"] <= 30) & (m_a["margin"].abs() <= 3)),
        ("E3, P3, within 3, rt live", (m_a["era_group"] == "E3") & (m_a["t_rem"] <= 120)
         & (m_a["margin"].abs() <= 3) & (m_a["rt_status"] == "live")),
    ]
    for lab, sel in slices:
        d = m_a[sel]
        A(f"| {lab} | {len(d):,} | {pct((d['n_matches'] < THIN).sum(), len(d))} | "
          f"{pct((d['nb_matches'] < THIN).sum(), len(d))} |")
    A("")
    # what splits the cells: rt_bin early in the match
    early_live = m_a[(m_a["t_rem"] > 180) & (m_a["rt_status"] == "live")]
    A(f"Why so many thin cells: while `rt_status` is live the 13 riding-time bins split every state 13 ways, and "
      f"before the last three minutes riding time is live in essentially every moment. With more than 3:00 left, "
      f"{pct((early_live['n_matches'] < THIN).sum(), len(early_live))} of live moments are in thin cells — yet the "
      f"point can't be settled that early. Table C′ (no `rt_bin`) and C″ (no `rt_bin`, no `choice`) show how much "
      f"of the thinness those two dimensions cause.\n")

    # ---- heatmaps
    heatmaps(m_a[m_a["era_group"] == "E3"], "Table A, E3 (2024–26) NCAA", "sparsity_E3_ncaa.png")
    heatmaps(m_a[m_a["era_group"] == "E12"], "Table A, E12 (2015–23) NCAA", "sparsity_E12_ncaa.png")
    heatmaps(m_d, "Table D, E3 NCAA + conference", "sparsity_E3_ncaa_conf.png")
    volume_map(m_a[m_a["era_group"] == "E3"], "E3 NCAA", "volume_E3_ncaa.png")
    A("## Maps\n")
    A("Share of moments in thin cells, margin × time left, by position (columns) and `rt_status` (rows). Dark = "
      "thin. Vertical lines = period boundaries.\n")
    A("![E3 NCAA](img/sparsity_E3_ncaa.png)\n")
    A("![E12 NCAA](img/sparsity_E12_ncaa.png)\n")
    A("![E3 NCAA + conference](img/sparsity_E3_ncaa_conf.png)\n")
    A("Raw volume, E3 NCAA (bouts per margin × time pixel, everything else pooled):\n")
    A("![E3 volume](img/volume_E3_ncaa.png)\n")

    # ---- 30 thinnest visited cells, where it matters
    A("## The 30 thinnest cells that real bouts visit — third period, margin within 3 (table A, E3)\n")
    A("Thousands of cells hold a single bout, so a flat list of the 30 thinnest is arbitrary. These are the thinnest "
      "cells in the slice that decides bouts (E3, period 3, within 3 points), most-visited first among ties.\n")
    sl = tab_a[(tab_a["era_group"] == "E3") & (tab_a["period"] == 3) & (tab_a["margin"].abs() <= 3)
               & (tab_a["margin"] >= 0)]
    sl = sl.sort_values(["n_matches", "n_obs"], ascending=[True, False]).head(30)
    A("| Margin | Time left | Position | Choice | rt_status | rt_bin | Bouts | Moments | Win % (raw) | "
      "Bouts in cell + neighbours |\n|---:|---|---|---|---|---:|---:|---:|---:|---:|")
    for r in sl.itertuples():
        A(f"| {r.margin:+d} | {r.t_bin * 10}–{r.t_bin * 10 + 9} s | {r.pos} | {r.choice} | {r.rt_status} | "
          f"{r.rt_bin:+d} | {r.n_matches} | {r.n_obs} | {100 * r.wins / r.n_obs:.0f}% | {r.nb_matches} |")
    A("")

    # ---- eras side by side (spec Section 4) and NCAA vs conference in E3
    A("## Same state, different era (spec Section 4)\n")
    A("Raw win rate for wrestler A in a few common states, pooled over riding time and choice so the cells are big "
      "enough to compare. 95% intervals are ± about 2·√(p(1−p)/n) with n = bouts.\n")

    def cell(two, sel):
        d = two[sel]
        n = d["bout_key"].nunique()
        return (f"{100 * d['win'].mean():.0f}% ({n:,})" if n >= 20 else f"— ({n})")

    def S(d, margin, lo, hi, pos, period):
        return (d["margin"] == margin) & (d["t_rem"] >= lo) & (d["t_rem"] <= hi) & (d["pos"] == pos) & \
               (d["period"] == period)

    states = [
        ("Tied, start of period 2, A on bottom", 0, 230, 240, "A_bottom", 2),
        ("Up 1, start of period 3, A on bottom", 1, 110, 120, "A_bottom", 3),
        ("Down 1, start of period 3, A on bottom", -1, 110, 120, "A_bottom", 3),
        ("Tied, start of period 3, A on bottom", 0, 110, 120, "A_bottom", 3),
        ("Up 2, 1:00 left, neutral", 2, 50, 60, "neutral", 3),
        ("Up 3, 1:00 left, neutral", 3, 50, 60, "neutral", 3),
        ("Up 3, 1:00 left, A on top", 3, 50, 60, "A_top", 3),
        ("Down 2, 0:30 left, A on bottom", -2, 20, 30, "A_bottom", 3),
        ("Up 1, 0:30 left, neutral", 1, 20, 30, "neutral", 3),
        ("Up 1, 0:30 left, A on bottom", 1, 20, 30, "A_bottom", 3),
        ("Up 5, anywhere in period 2, neutral", 5, 120, 240, "neutral", 2),
    ]
    two_ce3 = two_c[two_c["era_group"] == "E3"]
    A("| State | E12 NCAA (2015–23) | E3 NCAA (2024–26) | E3 conference |\n|---|---:|---:|---:|")
    for lab, mg, lo, hi, pos, per in states:
        A(f"| {lab} | {cell(two_n, S(two_n, mg, lo, hi, pos, per) & (two_n['era_group'] == 'E12'))} | "
          f"{cell(two_n, S(two_n, mg, lo, hi, pos, per) & (two_n['era_group'] == 'E3'))} | "
          f"{cell(two_ce3, S(two_ce3, mg, lo, hi, pos, per))} |")
    A("\n(win % (bouts); rows with fewer than 20 bouts show —.)\n")

    R = {r["Table"][:2].strip(". "): r for r in rows}
    A("## Reading it\n")
    A(f"1. **The spec's full state key is far too fine for this much data.** Most cells hold a handful of bouts; "
      f"{R['A']['Moments in thin cells']} of all NCAA moments and {R['C']['Moments in thin cells']} of E3 moments sit in "
      f"thin cells, and in the part that decides bouts (period 3, within 3 points) it's {R['C']['P3, within 3: in thin cells']} "
      f"for E3. The spec's rule was: keep 3.3 minimal and skip 3.4 only if thin cells carry a trivial share of real "
      f"moments. They don't.")
    A(f"2. **The parametric backstop (3.4) is needed.** Moments whose cell *and* its margin ±1 / time ±10 s "
      f"neighbours together hold fewer than 50 bouts: {R['A']['Moments where cell + neighbours < 50']} (all NCAA), "
      f"{R['C']['Moments where cell + neighbours < 50']} (E3 NCAA). Smoothing alone has nothing to borrow there.")
    A(f"3. **Riding-time bins are the main cause.** Dropping `rt_bin` takes E3 period-3 close moments from "
      f"{R['C']['P3, within 3: in thin cells']} thin to {R['C′']['P3, within 3: in thin cells']}; `choice` barely matters "
      f"(C″). Keeping riding-time bins only for the last 60 s: {R['F']['P3, within 3: in thin cells']} (F). But collapsing "
      f"`rt_bin` earlier throws away real information (55 s up with 1:30 left is very likely a point), so the better fix "
      f"is to keep the key and let smoothing borrow across neighbouring riding-time bins too, with the backstop "
      f"carrying riding time as a feature.")
    A("4. **Eras really do differ, as the spec expected.** A 2-point lead with a minute left held 93% of the time in "
      "2015–23 and 84% in 2024–26 — one 3-point takedown now erases it. Pooling eras (table B) looks less sparse but "
      "mixes two different meanings of the same margin, so it isn't a real fix.")
    A(f"5. **Conference E3 behaves like NCAA E3** in the comparison table (differences within noise), and adding it "
      f"cuts E3 thinness from {R['C']['Moments in thin cells']} to {R['D']['Moments in thin cells']} of moments "
      f"({R['C']['P3, within 3: in thin cells']} → {R['D']['P3, within 3: in thin cells']} in period 3 close). That is the "
      f"cleanest way to thicken E3 — same rules, same scoring — better than borrowing 2015–23 margins.\n")
    REP.parent.mkdir(parents=True, exist_ok=True)
    REP.write_text("\n".join(L) + "\n")
    print("wrote", REP)
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
