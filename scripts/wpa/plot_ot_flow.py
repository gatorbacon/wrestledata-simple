#!/usr/bin/env python3
"""
Overtime flow chart for one season (NCAA Championships + conference tournaments): how many bouts went to overtime,
how sudden victory ended, who chose the tiebreaker position (earned vs coin flip, chose vs deferred), how ride 1 went,
what the ride-2 chooser picked after each ride-1 outcome, and how TB-1 was decided (points / riding time / tied).

Current overtime rules only (2:00 sudden victory, data years 2022+). Reading rules (see docs/matsavant.md, WPA section,
"Overtime model", and scripts/wpa/ot_model.py's docstring):
  * `Choice 3` names the ride-1 BOTTOM wrestler ("X: Bottom"); "X: Defer" before it = the holder deferred.
  * The holder = the first takedown / near fall in regulation ("earned"), else a coin flip (not logged).
  * The ride-2 chooser is the wrestler on top in ride 1. His pick: a logged "Neutral/Top/Bottom" entry in ride 2, else
    who escaped / reversed first in ride 2; "nothing logged" = no score and no entry.
  * A scoreless ride isn't logged and later rounds share the TB-1 columns, so a bout that went to TB-2 / TB-3 / UTB (or
    to SV-2 / SV-3 with no tiebreaker score logged) is counted as TB-1 = ride-out, bottom, ridden out (30-30, tied).
  * Riding time only breaks a points tie; a TB-1 bout tied on points was decided on riding time.
  * Bouts with a wrong / missing result label (Dec / Unknown / blank) that reached the tiebreaker are counted from
    their logged rides as TB-1 finishes.

Usage: .venv/bin/python scripts/wpa/plot_ot_flow.py --year 2026   -> data/wpa/reports/img/ot_flow_{year}.png
"""
import argparse
import statistics
import sys
from collections import Counter
from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts/wpa"))
sys.path.insert(0, str(ROOT / "scripts/analysis"))
import build_states as BS  # noqa: E402
import wpa_common as C  # noqa: E402

STATES = ROOT / "data/wpa/states"


def oth(s):
    return "l" if s == "w" else "w"


def extract(year):
    """Raw overtime columns of every overtime bout of the season (winner-oriented)."""
    b = pd.concat([pd.read_csv(STATES / f"{k}_bouts.csv", low_memory=False).assign(k=k) for k in ("ncaa", "conf")])
    b = b.set_index("bout_key")
    e = pd.concat([pd.read_csv(STATES / f"{k}_events.csv", low_memory=False) for k in ("ncaa", "conf")])
    reg = e[e["section"] == "reg"].sort_values(["bout_key", "seq"])
    holder = reg[reg["event"].isin(["takedown", "near_fall"]) & (reg["points"] > 0)].groupby("bout_key")["actor"].first()
    recs = []
    for kind in ("ncaa", "conf"):
        for r in C.load_bouts(kind):
            if r["year"] != year:
                continue
            m = r["bout"]
            key = f"{kind}|{r['tournament']}|{year}|{r['weight']}|{m.get('bout_number')}"
            if key not in b.index or str(b.at[key, "went_to_ot"]) != "True":
                continue
            cols = {c["label"]: c for c in m.get("columns") or []}
            pc = lambda lab: [(x["side"], x["action"], x["points"], x["clock"], x["word"])  # noqa: E731
                              for x in BS.parse_col(cols[lab], r["swapped"])] if lab in cols else []
            recs.append({"key": key, "kind": kind, "res": b.at[key, "result_type"], "c3": pc("Choice 3"),
                         "o1": pc("Overtime 1"), "o2": pc("Overtime 2"), "o3": pc("Overtime 3"),
                         "holder": holder.get(key)})
    return b[b["year"] == year], recs


def classify(recs):
    out = []
    for r in recs:
        res = r["res"] if isinstance(r["res"], str) else ""
        tb = bool(r["c3"]) or bool(r["o2"]) or bool(r["o3"]) or res.startswith(("TB", "SV-2", "SV-3", "UTB"))
        d = {"key": r["key"], "res": res, "reached_tb": tb}
        if not tb:
            sc = [x for x in r["o1"] if x[2] > 0]
            d["sv_by"] = sc[0][1] if sc else ("fall" if res == "Fall" else "none logged")
            d["sv_el"] = (120 - sc[0][3]) if sc and sc[0][3] is not None else None
            out.append(d)
            continue
        d["defer"] = any(x[1] == "defer" for x in r["c3"])
        d["earned"] = r["holder"] is not None
        pick = [x for x in r["c3"] if x[1] == "choice" and x[4] in ("bottom", "top")]
        if pick:
            bot1 = pick[0][0] if pick[0][4] == "bottom" else oth(pick[0][0])
        else:
            f = [x for x in r["o2"] if x[1] in ("escape", "reversal")]
            bot1 = f[0][0] if f else None
        d["bot1"] = bot1
        f = [x for x in r["o2"] if x[1] in ("escape", "reversal", "takedown", "near_fall")]
        if bot1 is None:
            d["r1"] = "unknown"
        elif not f:
            d["r1"] = "ride-out"
        elif f[0][1] in ("escape", "reversal"):
            d["r1"] = f[0][1]           # (an escape logged for the rider = a position slip in the log; still an escape)
        else:
            d["r1"] = "unknown"
        d["r1_t"] = (30 - f[0][3]) if f and f[0][3] is not None else None
        c2 = oth(bot1) if bot1 else None
        ch = [x for x in r["o3"] if x[1] == "choice" and x[4] in ("neutral", "top", "bottom")]
        g = [x for x in r["o3"] if x[1] in ("escape", "reversal", "takedown")]
        if ch:
            d["r2"] = "neutral" if ch[0][4] == "neutral" else ("bottom" if (ch[0][4] == "bottom") == (ch[0][0] == c2)
                                                                else "top")
        elif g:
            d["r2"] = "neutral" if g[0][1] == "takedown" else ("bottom" if g[0][0] == c2 else "top")
        else:
            d["r2"] = "not logged"
        d["r2_out"] = g[0][1] if g else "no score"
        tbsc = any(x[2] and x[1] != "riding_time" for x in r["o2"] + r["o3"])
        d["tie"] = res in ("TB-2", "TB-3", "UTB") or (res in ("SV-2", "SV-3") and not tbsc)
        if d["tie"] and bot1:
            d.update(r1="ride-out", r2="bottom", r2_out="ridden out", dec="tied", winner_role=None, r1_t=None)
            out.append(d)
            continue
        pts = sum((x[2] if x[0] == "w" else -x[2]) for x in r["o2"] + r["o3"] if x[1] != "riding_time" and x[2])
        d["mislabelled"] = res in ("Dec", "Unknown", "")
        if res == "Fall":
            d["dec"] = "fall"
        elif res in ("TB-1", "Dec", "Unknown", "") or d["tie"]:
            d["dec"] = "riding time" if pts <= 0 else "points"
        else:
            d["dec"] = "tied"
        d["rt_role"] = ("rode first" if c2 == "w" else "rode second") if d["dec"] == "riding time" and bot1 else None
        d["winner_role"] = None if not bot1 else ("ride-1 bottom" if bot1 == "w" else "ride-1 top")
        out.append(d)
    return out


def plot(year, allb, F, out):
    nall = len(allb)
    nk = Counter(allb.loc[allb["went_to_ot"].astype(str) == "True", "k"])
    tb = [d for d in F if d["reached_tb"]]
    sv = [d for d in F if not d["reached_tb"]]
    n = len(tb)
    pc = lambda a, n_: f"{100 * a / n_:.0f}%" if n_ else "–"  # noqa: E731
    med = lambda v: statistics.median(v) if v else None  # noqa: E731
    svby = Counter(d["sv_by"] for d in sv)
    svt = med([d["sv_el"] for d in sv if d.get("sv_el") is not None])
    earned = sum(d["earned"] for d in tb)
    ndef = sum(d["defer"] for d in tb)
    r1 = Counter(d["r1"] for d in tb)
    esc_t = med([d["r1_t"] for d in tb if d["r1"] == "escape" and d["r1_t"] is not None])
    grp = lambda o: [d for d in tb if d["r1"] == o]  # noqa: E731
    tb1 = [d for d in tb if d["dec"] in ("points", "riding time", "fall")]
    rt = [d for d in tb1 if d["dec"] == "riding time"]
    rt_roles = Counter(d["rt_role"] for d in rt)
    lat = [d for d in tb if d["dec"] == "tied"]
    latc = Counter(d["res"] for d in lat)
    win_bot = sum(d["winner_role"] == "ride-1 bottom" for d in tb1)
    nmis = sum(d.get("mislabelled", False) for d in tb)

    def r2line(g, c):
        h = [d for d in g if d["r2"] == c]
        if not h:
            return None
        o = ", ".join(f"{v} {k}" for k, v in Counter(d["r2_out"] for d in h).most_common())
        lab = {"bottom": "Bottom", "neutral": "Neutral", "top": "Top", "not logged": "Nothing logged"}[c]
        return f"{lab} {len(h)}  →  {o}".replace("ridden out", "ridden out (tied)")

    INK, MUT, ACC, BOX, EDGE, ACCB = "#1f2328", "#5b636e", "#b4232a", "#f4f5f7", "#c9ced6", "#fbeaea"
    fig = plt.figure(figsize=(12, 17), dpi=130)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 20)
    ax.axis("off")

    def box(x, y, w, h, title, lines=(), acc=False, fs=13):
        ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.02,rounding_size=0.12",
                                    fc=ACCB if acc else BOX, ec=ACC if acc else EDGE, lw=1.4))
        ax.text(x, y + h / 2 - 0.28, title, ha="center", va="top", fontsize=fs, fontweight="bold", color=INK)
        for i, ln in enumerate(lines):
            ax.text(x, y + h / 2 - 0.72 - 0.36 * i, ln, ha="center", va="top", fontsize=10.2, color=MUT)

    def arrow(x0, y0, x1, y1):
        ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                    arrowprops=dict(arrowstyle="-|>", color="#8a929c", lw=1.3, shrinkA=0, shrinkB=0))

    ax.text(6, 19.6, f"Overtime in {year}: NCAA + conference tournaments", ha="center", fontsize=19,
            fontweight="bold", color=INK)
    ax.text(6, 19.15, f"{nall:,} bouts with play-by-play · current rules (2:00 sudden victory, then two 30-second "
            "tiebreaker rides)", ha="center", fontsize=11, color=MUT)
    box(6, 18.2, 5.2, 1.1, f"Went to overtime: {len(F)}  ({pc(len(F), nall)} of bouts)",
        [f"NCAA {nk['ncaa']} · conference {nk['conf']}"], acc=True)
    arrow(5, 17.65, 2.8, 16.95)
    arrow(7, 17.65, 9.2, 16.95)
    svl = [f"takedown {svby['takedown']} · penalty point {svby['penalty']} · other "
           f"{len(sv) - svby['takedown'] - svby['penalty']}"]
    if svt is not None:
        svl.append(f"median winning score {int(svt // 60)}:{int(svt % 60):02d} into the period")
    box(2.8, 16.3, 5.0, 1.3, f"Won in sudden victory: {len(sv)}  ({pc(len(sv), len(F))})", svl)
    box(9.2, 16.3, 5.0, 1.3, f"Reached the tiebreaker: {n}  ({pc(n, len(F))})",
        ["nobody scored in 2:00 of sudden victory"], acc=True)
    arrow(9.2, 15.65, 9.2, 15.05)
    box(9.2, 14.1, 5.0, 2.0, "Who chose the ride-1 position",
        [f"coin flip {n - earned} ({pc(n - earned, n)}): no takedown / near fall in regulation",
         f"earned {earned} ({pc(earned, n)}): first takedown or near fall",
         f"holder chose {n - ndef} · deferred {ndef} (the other man then picks)",
         "ride 1 starts with the picker on bottom"])
    xs = {"escape": 2.1, "reversal": 6.0, "ride-out": 9.9}
    for o, x in xs.items():
        arrow(9.2 if o != "escape" else 8.0, 13.1, x, 12.4)
    box(xs["escape"], 11.8, 3.6, 1.2, f"Ride 1: escape {r1['escape']}  ({pc(r1['escape'], n)})",
        [f"median {esc_t:.0f} s into the ride" if esc_t is not None else ""])
    box(xs["reversal"], 11.8, 3.6, 1.2, f"Ride 1: reversal {r1['reversal']}  ({pc(r1['reversal'], n)})",
        ["bottom man scores 2, goes on top"])
    box(xs["ride-out"], 11.8, 3.6, 1.2, f"Ride 1: ride-out {r1['ride-out']}  ({pc(r1['ride-out'], n)})",
        ["rider banks 30 s of riding time"])
    ax.text(6, 10.85, "Ride 2: the wrestler who rode in ride 1 picks the position", ha="center", fontsize=12.5,
            fontweight="bold", color=INK)
    for o, x in xs.items():
        arrow(x, 11.2, x, 10.55)
        g = grp(o)
        lines = [ln for ln in (r2line(g, c) for c in ("bottom", "neutral", "top", "not logged")) if ln]
        box(x, 9.3, 3.8, 2.3, f'{len(g)} after a{"n" if o == "escape" else ""} {o}', lines, fs=12)
        arrow(x, 8.15, x, 7.55)
        lr = sum(d["dec"] == "tied" for d in g)
        w_b = sum(d["winner_role"] == "ride-1 bottom" for d in g)
        w_t = sum(d["winner_role"] == "ride-1 top" for d in g)
        who = {"escape": "Escaper", "reversal": "Reverser", "ride-out": "Rider"}[o]
        main, other_ = (w_t, w_b) if o == "ride-out" else (w_b, w_t)
        box(x, 6.85, 3.8, 1.3, f"{who} won {main} of {len(g)}",
            [f"{'bottom man' if o == 'ride-out' else 'rider'} won {other_}",
             f"{lr} tied, 30-30 → later rounds" if lr else "all decided in TB-1"])
    ax.text(6, 5.72, f"All {n} tiebreakers", ha="center", fontsize=12.5, fontweight="bold", color=INK)
    rtl = (f"on riding time {len(rt)} ({pc(len(rt), len(tb1))}): the man who rode first won "
           f"{rt_roles.get('rode first', 0)}, rode second {rt_roles.get('rode second', 0)}")
    nf = sum(d["dec"] == "fall" for d in tb1)
    box(3.4, 4.6, 5.6, 1.5, f"Decided in TB-1: {len(tb1)}  ({pc(len(tb1), n)})",
        [f"on points {len(tb1) - len(rt) - nf}" + (f" · fall {nf}" if nf else ""), rtl], acc=True)
    box(9.0, 4.6, 5.2, 1.5, f"Tied after TB-1: {len(lat)}  ({pc(len(lat), n)})",
        [(f"scoreless (ride-out, bottom, ridden out = 30-30): {sum(d['tie'] for d in lat)}"
          + (f" · tied after scoring: {sum(not d['tie'] for d in lat)}" if any(not d["tie"] for d in lat) else "")),
         "then " + " · ".join(f"{k} {v}" for k, v in latc.most_common()) if lat else ""])
    box(6, 2.75, 9.6, 0.9, f"The wrestler on bottom in ride 1 won {win_bot} of the {len(tb1)} tiebreakers decided in "
        f"TB-1 ({pc(win_bot, len(tb1))})", [], fs=13.5)
    notes = ["Notes: 'Nothing logged' = no score and no choice entry in ride 2 — the chooser was ridden out (or picked "
             "neutral without it being logged); either way no score.",
             "'Earned' = had the first takedown or near fall in regulation (the rule); otherwise a coin flip, which "
             "TrackWrestling doesn't record.",
             "A scoreless ride isn't logged, so a bout that went to TB-2 shows only TB-2's rides; its TB-1 is counted "
             "here as ride-out, bottom, ridden out (the only way to tie at 0-0).",
             (f"{nmis} TB-1 finish{'es carry' if nmis != 1 else ' carries'} a wrong result label (Dec / Unknown / "
              "blank) and are counted from their logged rides." if nmis else "") +
             (f" {r1['unknown']} tiebreaker(s) with no usable ride-1 position are left out of the ride boxes."
              if r1.get("unknown") else ""),
             f"Source: data/wpa (WPA build), raw TrackWrestling play-by-play; {year} NCAA Championships + conference "
             "tournaments. scripts/wpa/plot_ot_flow.py"]
    for i, ln in enumerate(notes):
        ax.text(0.35, 1.85 - 0.33 * i, ln, fontsize=8.9, color=MUT, va="top")
    fig.savefig(out, facecolor="white")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, required=True)
    a = ap.parse_args()
    if C.ot_rules(a.year) != "SV120":
        sys.exit(f"{a.year}: not the current overtime rules (2:00 sudden victory starts in 2022)")
    allb, recs = extract(a.year)
    out = ROOT / f"data/wpa/reports/img/ot_flow_{a.year}.png"
    plot(a.year, allb, classify(recs), out)
    print(out.relative_to(ROOT))


if __name__ == "__main__":
    main()
