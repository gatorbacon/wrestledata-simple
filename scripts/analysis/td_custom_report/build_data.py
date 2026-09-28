#!/usr/bin/env python3
"""Data for the custom takedown report (data/analysis/td_custom_report.html) -- computed straight from the
bouts (NOT parsed from the older text reports). Re-uses the loaders in scripts/analysis/td_differential_report.py.

Universe: every NCAA / conference-tournament bout that has play-by-play, 2015-2026 (2020 had no NCAA tournament),
minus forfeits/injury defaults/DQs that have no wrestled action (official result Forfeit/Inj./DQ AND no events AND 0-0).
Differential = winner's takedowns minus loser's takedowns.  "Decided by points" = official Dec/MD/TF/UTB/SV-*/TB-*.
"""
import json, sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
sys.path.insert(0, str(HERE.parent))
import td_differential_report as R

WINDOWS = [(2014, 2016), (2017, 2019), (2021, 2023), (2024, 2026)]
WL = ["2015–16", "2017–19", "2021–23", "2024–26"]  # no play-by-play before 2015


def wrestled(b):
    """Drop bouts that were never wrestled (forfeit / default with nothing on the scoreboard)."""
    return not (b["cls"] == "forfeit" and b["ws"] == 0 and b["ls"] == 0 and not b["td"])


def diff(b):
    return b["td"]["winner"] - b["td"]["loser"]


def equal_count_cuts(gaps, n_bins, first_split=True):
    """Cut a sorted list of pin gaps into ~equal-count bins without splitting identical gaps; returns the first
    gap of each bin after the first. With first_split the leftmost bin is halved again (the far-left tail is the
    widest range, so it gets a second look)."""
    per = len(gaps) / n_bins
    cuts, start = [], 0
    def advance(end):
        while 0 < end < len(gaps) and gaps[end] == gaps[end - 1]:
            end += 1
        return end
    for k in range(1, n_bins):
        end = advance(round(per * k))
        if end >= len(gaps) or end <= start:
            continue
        cuts.append(gaps[end]); start = end
    if first_split and cuts:
        first = [g for g in gaps if g < cuts[0]]
        mid = advance(len(first) // 2)
        if 0 < mid < len(first):
            cuts.insert(0, first[mid])
    return cuts


def seed_analysis(rows):
    """Equal-count seed-gap bins + logistic fit of 'takedown leader got the pin' on the signed gap, over pins."""
    import math
    import numpy as np
    pins = sorted((g, w) for g, w, p in rows if p)
    gaps = [g for g, _ in pins]
    cuts = equal_count_cuts(gaps, 8)
    edges = [-32] + cuts + [33]           # bin i = gaps in [edges[i], edges[i+1] - 1]
    bins = []
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1] - 1
        pn = [(g, w) for g, w in pins if lo <= g <= hi]
        al = [(g, w) for g, w, p in rows if lo <= g <= hi]
        bins.append({"lo": lo, "hi": hi, "pins": len(pn), "lead_pins": sum(w for _, w in pn),
                     "edge": len(al), "lead_won": sum(w for _, w in al)})
    # logistic regression by Newton / IRLS
    X = np.array([[1.0, g] for g, _ in pins]); y = np.array([float(w) for _, w in pins])
    beta = np.zeros(2)
    for _ in range(50):
        p = 1 / (1 + np.exp(-X @ beta)); W = p * (1 - p)
        H = X.T @ (X * W[:, None]); step = np.linalg.solve(H, X.T @ (y - p))
        beta = beta + step
        if np.abs(step).max() < 1e-10:
            break
    cov = np.linalg.inv(X.T @ (X * (p * (1 - p))[:, None]))
    se = np.sqrt(np.diag(cov))
    z = beta[1] / se[1]
    pval = math.erfc(abs(z) / math.sqrt(2))
    def at(g):
        x = np.array([1.0, g]); eta = x @ beta; s_ = math.sqrt(x @ cov @ x)
        f = lambda t: 1 / (1 + math.exp(-t))
        return {"g": g, "p": 100 * f(eta), "lo": 100 * f(eta - 1.96 * s_), "hi": 100 * f(eta + 1.96 * s_)}
    fit = {"n": len(pins), "a": beta[0], "b": beta[1], "se_b": se[1], "p_value": pval,
           "or10": math.exp(10 * beta[1]), "or10_lo": math.exp(10 * (beta[1] - 1.96 * se[1])),
           "or10_hi": math.exp(10 * (beta[1] + 1.96 * se[1])), "at0": at(0),
           "curve": [at(g) for g in range(min(gaps), max(gaps) + 1)]}
    return bins, fit


def cell(bs):
    """Counts for one (window, tourney type)."""
    bs = [b for b in bs if wrestled(b)]
    out = {"bouts": len(bs), "tied": sum(1 for b in bs if diff(b) == 0)}
    edge = [b for b in bs if diff(b) >= 1 or diff(b) <= -1]
    out["edge_n"] = len(edge)
    out["edge_won"] = sum(1 for b in edge if diff(b) > 0)
    pts = [b for b in edge if b["cls"] == "points"]
    out["pts_n"] = len(pts)
    out["pts_won"] = sum(1 for b in pts if diff(b) > 0)
    # matches the wrestler BEHIND on takedowns won: by official fall / any way / no official result to tell
    trail = [b for b in edge if diff(b) < 0]
    out["upsets"] = len(trail)
    out["fall_up"] = sum(1 for b in trail if b["cls"] == "fall")
    out["up_unknown"] = sum(1 for b in trail if b["cls"] == "unknown")
    out["fall_n"] = sum(1 for b in edge if b["cls"] == "fall")        # all pins in matches with a takedown edge
    out["edge_unknown"] = sum(1 for b in edge if b["cls"] == "unknown")  # no official result -> can't tell if a pin
    by = {}
    for lab, ok in (("1", lambda a: a == 1), ("2", lambda a: a == 2), ("3", lambda a: a == 3), ("4+", lambda a: a >= 4)):
        for basis, pool in (("all", edge), ("pts", pts)):
            sel = [b for b in pool if ok(abs(diff(b)))]
            by.setdefault(lab, {})[basis] = {"n": len(sel), "won": sum(1 for b in sel if diff(b) > 0),
                                             "fall_up": sum(1 for b in sel if diff(b) < 0 and b["cls"] == "fall"),
                                             "fall_n": sum(1 for b in sel if b["cls"] == "fall")}
    out["by_edge"] = by
    return out


TEAM_ALIAS = {"OK State": "Oklahoma State", "Arizona State University": "Arizona State"}


def team(t):
    return TEAM_ALIAS.get(t, t)


def person_key(name):
    """(surname, first initial) -- conference vs NCAA files spell first names differently (Timmy/Timothy)."""
    n = R.nkey(name)
    return n if isinstance(n, tuple) else n


def main():
    data = {"windows": WL, "cells": {}, "notes": {}}
    all_ncaa, all_conf = [], []
    seed_rows = []        # (signed seed gap, takedown leader won, ended in a pin) for NCAA matches with a TD edge, both seeded
    aa_rows = []          # all-American season rows (NCAA)
    aa_counts = Counter()
    per_window_aa = {}
    for (a, z), lab in zip(WINDOWS, WL):
        nb, nn = R.load(range(a, z + 1))
        cb, cn = R.load_conf(range(a, z + 1))
        data["cells"][lab] = {"ncaa": cell(nb), "conf": cell(cb), "ncaa_years": nn["years"], "conf_years": cn["years"]}
        all_ncaa += [(lab, b) for b in nb]; all_conf += [(lab, b) for b in cb]
        for b in nb:  # signed seed gap: seed of the wrestler BEHIND on takedowns minus seed of the one AHEAD
            d = diff(b)
            if d == 0 or b["cls"] == "forfeit" or not (b["wseed"] and b["lseed"]):
                continue
            lead_w = d > 0
            gap = (b["lseed"] - b["wseed"]) if lead_w else (b["wseed"] - b["lseed"])
            seed_rows.append((gap, lead_w, b["cls"] == "fall"))
        # ---- section 5: All-Americans, no-takedown wins in one tournament
        placers = nn["placers"]
        wins_by, notd = Counter(), defaultdict(list)
        for b in nb:
            k = (b["year"], b["weight"], b["winner"])
            if k not in placers or b["cls"] == "forfeit":
                continue
            wins_by[k] += 1
            if b["td"]["winner"] == 0:
                notd[k].append(b)
        for k, v in notd.items():
            aa_counts[len(v)] += 1
            per_window_aa.setdefault(lab, Counter())[len(v)] += 1
            aa_rows.append({"window": lab, "year": k[0], "weight": k[1], "name": k[2], "team": v[0]["wteam"],
                            "place": placers[k][0], "n": len(v), "wins": wins_by[k],
                            "beat": [{"opp": b["loser"], "team": team(b["lteam"]), "how": R.fmt_win(b),
                                      "round": b["round"]} for b in sorted(v, key=lambda b: R.ROUND_ORDER.get(b["round"], 9))]})
    data["seed_bins"], data["seed_fit"] = seed_analysis(seed_rows)
    top = max(aa_counts)
    data["aa_top"] = top
    data["aa_rows"] = sorted([r for r in aa_rows if r["n"] == top], key=lambda r: (r["year"], r["weight"]))
    data["aa_counts"] = {str(k): v for k, v in sorted(aa_counts.items(), reverse=True)}
    data["aa_counts_by_window"] = {w: {str(k): v for k, v in c.items()} for w, c in per_window_aa.items()}
    ord_ = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th", 6: "6th", 7: "7th", 8: "8th"}
    for r in data["aa_rows"]:
        r["place"] = ord_[r["place"]]

    # ---- section 6: career (2015-2026 tournaments) wins without a takedown
    person = defaultdict(lambda: {"ncaa": 0, "conf": 0, "wins_ncaa": 0, "wins_conf": 0, "names": Counter(),
                                  "teams": Counter(), "weights": Counter(), "years": set(), "wins_list": []})
    for kind, pool in (("ncaa", all_ncaa), ("conf", all_conf)):
        for lab, b in pool:
            if b["cls"] == "forfeit" or (b["ws"] == 0 and b["ls"] == 0 and b["cls"] != "fall"):
                continue
            k = person_key(b["winner"])
            p = person[k]
            p["wins_" + kind] += 1
            p["names"][b["winner"]] += 1
            p["teams"][team(b["wteam"])] += 1
            p["weights"][b["weight"]] += 1
            p["years"].add(b["year"])
            if b["td"]["winner"] == 0:
                p[kind] += 1
                p["wins_list"].append((b["year"], kind, b["weight"], b.get("conf") or "NCAA", b["loser"], b["lteam"], R.fmt_win(b)))
    rows = []
    for k, p in person.items():
        tot = p["ncaa"] + p["conf"]
        if tot < 5:
            continue
        rows.append({"key": str(k), "name": p["names"].most_common(1)[0][0], "names": sorted(p["names"]),
                     "team": p["teams"].most_common(1)[0][0], "teams": dict(p["teams"].most_common()),
                     "weights": dict(p["weights"]), "years": sorted(p["years"]),
                     "ncaa": p["ncaa"], "conf": p["conf"], "total": tot,
                     "wins": p["wins_ncaa"] + p["wins_conf"], "wins_ncaa": p["wins_ncaa"], "wins_conf": p["wins_conf"],
                     "list": p["wins_list"]})
    rows.sort(key=lambda r: (-r["total"], -r["ncaa"], r["name"]))
    data["career_candidates"] = rows
    (HERE / "data.json").write_text(json.dumps(data, indent=1, default=list))
    print("wrote", HERE / "data.json")
    for lab in WL:
        c = data["cells"][lab]
        for t in ("ncaa", "conf"):
            x = c[t]; print(lab, t, {k: x[k] for k in ("bouts", "tied", "edge_n", "edge_won", "pts_n", "pts_won")})
    print("AA top", top, len(data["aa_rows"]), data["aa_counts"], data["aa_counts_by_window"])
    for r in rows[:25]:
        print(r["total"], r["ncaa"], r["conf"], r["wins"], r["name"], r["teams"], sorted(r["weights"]), r["years"], r["names"])


if __name__ == "__main__":
    main()
