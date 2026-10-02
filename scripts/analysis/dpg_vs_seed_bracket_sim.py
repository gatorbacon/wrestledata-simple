#!/usr/bin/env python3
"""
Fair test of DPG vs. seed as NCAA predictors: both get the real bracket (TJ, 2026-10-02).

Why: a raw correlation flatters the seed, because the seed also *builds* the bracket (a 5 seed meets the 1 in
the semis, a 3 seed meets the 2), so part of seed's "accuracy" is the path it hands out. Here both models
predict inside the bracket as actually drawn:

1. Win models (symmetric logistic, no intercept), fitted on NCAA bouts 2015-2023 (no 2020) where both
   wrestlers have a seed and a pre-tournament DPG:
     DPG only:   P(i beats j) = sigmoid(b * (DPG_i - DPG_j))
     Seed only:  P(i beats j) = sigmoid(a * (ln seed_j - ln seed_i))     (same form as xtp/engine/probability.py)
     Both:       sigmoid(a * ln-seed term + b * DPG term)                  (reference only)
2. Each 2024-2026 bracket (all follow the standard 33-seed wiring of xtp/engine/bracket_schema.py; checked)
   is Monte Carlo simulated N times per model -> expected advancement + placement points per wrestler
   (no bonus: neither model predicts bonus, so bonus is left out of both sides of the comparison).
3. Scored against what happened: correlation (Pearson, Spearman) and mean squared error of expected vs. actual
   non-bonus points, plus bout-level log loss / accuracy on the actual 2024-26 pairings (bracket-free check).

"DPG going in" = mean per-match DPG before March 15, as in dpg_vs_ncaa_points.py (same caveats: opponent strength
is season-end). Output: data/analysis/dpg_vs_seed_bracket_sim.json (read by dpg_vs_ncaa_points.py, section 4).
Run: .venv/bin/python scripts/analysis/dpg_vs_seed_bracket_sim.py
"""
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import optimize, stats

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "analysis"))
from xtp.engine.bracket_schema import get_all_slots  # noqa: E402
import dpg_vs_ncaa_points as base  # noqa: E402  (entrant -> pre-tournament DPG matching, scoring)

FIT_YEARS = (2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023)
TEST_YEARS = (2024, 2025, 2026)
N_SIMS = 20000
OUT = ROOT / "data" / "analysis" / "dpg_vs_seed_bracket_sim.json"
ADV = {"PIG": 1.0, "R32": 1.0, "R16": 1.0, "QF": 1.0, "SF": 1.0}          # championship slot rounds
CONS_ADV = {"PIG": 0.5, "R1": 0.5, "R2": 0.5, "R3": 0.5, "R4": 0.5, "QF": 0.5, "SF": 0.5}


def year_entrants(y, allm):
    """{(weight, seed): DPG going in} and the bout list with both sides' seed + DPG."""
    rows, _ = base.build_year(y, allm)
    dpg = {(r["w"], r["s"]): r["d"] for r in rows if r["s"] is not None}
    by_name = {(r["n"], r["t"], r["w"]): r for r in rows}
    bouts = []
    for m in allm:
        if m["year"] != y:
            continue
        a = by_name.get((m["winner_name"], m["winner_team"], m["weight"]))
        b = by_name.get((m["loser_name"], m["loser_team"], m["weight"]))
        if a and b and a["s"] and b["s"]:
            bouts.append((a["d"], b["d"], a["s"], b["s"]))   # winner first
    return dpg, rows, bouts


def fit(bouts):
    """Max-likelihood a (seed) and b (DPG) for the three models on winner-first bouts."""
    dd = np.array([w - l for w, l, _, _ in bouts])
    ds = np.array([math.log(ls) - math.log(ws) for _, _, ws, ls in bouts])   # >0 when the better seed won

    def nll(x, use_s, use_d):
        z = (x[0] if use_s else 0) * ds + (x[-1] if use_d else 0) * dd
        return np.sum(np.logaddexp(0, -z))
    res = {}
    res["dpg"] = {"b": float(optimize.minimize(lambda x: nll(x, False, True), [0.5]).x[0])}
    res["seed"] = {"a": float(optimize.minimize(lambda x: nll(x, True, False), [1.0]).x[0])}
    xb = optimize.minimize(lambda x: nll(x, True, True), [1.0, 0.3]).x
    res["both"] = {"a": float(xb[0]), "b": float(xb[1])}
    return res


def prob_matrix(model, params, dpg_by_seed):
    s = np.arange(1, 34, dtype=float)
    d = np.array([dpg_by_seed.get(i, np.nan) for i in range(1, 34)])
    d = np.where(np.isnan(d), np.nanmean(d), d)   # a qualifier with no DPG -> field average
    z = np.zeros((33, 33))
    if model in ("seed", "both"):
        z += params["a"] * (np.log(s)[None, :] - np.log(s)[:, None])
    if model in ("dpg", "both"):
        z += params["b"] * (d[:, None] - d[None, :])
    return 1 / (1 + np.exp(-z))           # P[i, j] = P(seed i+1 beats seed j+1)


SLOTS = [s for s in get_all_slots().values() if s.inputs]
PLACE_PTS = {1: 16, 2: 12, 3: 10, 4: 9, 5: 7, 6: 6, 7: 4, 8: 3}


def simulate(P, n, rng):
    """Expected non-bonus points per seed (index 0..32) over n simulated tournaments."""
    out = {}                                  # "<slot>_WINNER"/"_LOSER" -> array of seed indices
    pts = np.zeros(33)
    for slot in SLOTS:                        # schema order is already topological
        ins = []
        for ref in slot.inputs:
            if ref.startswith("SEED_"):
                ins.append(np.full(n, int(ref[5:]) - 1))
            elif ref == "PIG_WINNER":
                ins.append(out["C_PIG_0_WINNER"])
            else:
                ins.append(out[ref])
        a, b = ins
        win = rng.random(n) < P[a, b]
        w, l = np.where(win, a, b), np.where(win, b, a)
        out[f"{slot.id}_WINNER"], out[f"{slot.id}_LOSER"] = w, l
        if slot.bracket == "champ" and slot.round in ADV:
            np.add.at(pts, w, ADV[slot.round])
        elif slot.bracket == "consol" and slot.round in CONS_ADV:
            np.add.at(pts, w, CONS_ADV[slot.round])
        for to, who in ((slot.winner_to, w), (slot.loser_to, l)):
            if to and to.startswith("PLACE_"):
                np.add.at(pts, who, PLACE_PTS[int(to[6:])])
    return pts / n


def actual_nonbonus(rows_year, allm, y):
    """Actual advancement + placement points (bonus removed) keyed (weight, seed)."""
    rs = [m for m in allm if m["year"] == y]
    pts, place, seed, _, _ = base.ncaa_points(rs)
    bon = defaultdict(float)
    for m in rs:
        bon[(m["winner_name"], m["winner_team"], m["weight"])] += base.bonus(m["result_type"])
    return {(k[2], seed[k]): pts[k] - bon[k] for k in pts if seed.get(k)}


def main():
    allm = json.loads((ROOT / "data" / "ncaa-tourney-parsed" / "all_matches.json").read_text())
    fit_bouts = []
    for y in FIT_YEARS:
        fit_bouts += year_entrants(y, allm)[2]
    params = fit(fit_bouts)
    print(f"fitted on {len(fit_bouts)} bouts: {params}")

    rng = np.random.default_rng(20261002)
    per = {m: {"exp": [], "act": [], "act_total": []} for m in ("dpg", "seed", "both")}
    test_bouts = []
    for y in TEST_YEARS:
        dpg, rows, bouts = year_entrants(y, allm)
        test_bouts += bouts
        act = actual_nonbonus(rows, allm, y)
        total = {(r["w"], r["s"]): r["p"] for r in rows}
        for wt in sorted({r["w"] for r in rows}):
            dpg_by_seed = {s: v for (w, s), v in dpg.items() if w == wt}
            for model in per:
                e = simulate(prob_matrix(model, params[model], dpg_by_seed), N_SIMS, rng)
                for s in range(1, 34):
                    if (wt, s) in act and (wt, s) in total:
                        per[model]["exp"].append(e[s - 1])
                        per[model]["act"].append(act[(wt, s)])
                        per[model]["act_total"].append(total[(wt, s)])
    # bout-level check on the actual 2024-26 pairings (no bracket involved)
    bout_scores, bout_ll = {}, {}
    for model in per:
        p = []
        for wd, ld, ws, ls in test_bouts:
            z = 0.0
            if model in ("seed", "both"):
                z += params[model]["a"] * (math.log(ls) - math.log(ws))
            if model in ("dpg", "both"):
                z += params[model]["b"] * (wd - ld)
            p.append(1 / (1 + math.exp(-z)))
        p = np.array(p)
        bout_ll[model] = -np.log(p)
        bout_scores[model] = {"log_loss": float(np.mean(-np.log(p))), "accuracy": float(np.mean(p > 0.5)),
                              "brier": float(np.mean((1 - p) ** 2))}
    summary = {}
    for model, v in per.items():
        e, a, t = np.array(v["exp"]), np.array(v["act"]), np.array(v["act_total"])
        summary[model] = {"pearson": float(stats.pearsonr(e, a)[0]), "spearman": float(stats.spearmanr(e, a)[0]),
                          "rmse": float(np.sqrt(np.mean((e - a) ** 2))),
                          "pearson_total": float(stats.pearsonr(e, t)[0]), "n": int(len(e)),
                          **bout_scores[model]}
    # paired bootstrap on squared error: is DPG's bracket-aware forecast better than seed's?
    ed, es = np.array(per["dpg"]["exp"]), np.array(per["seed"]["exp"])
    a = np.array(per["dpg"]["act"])
    diffs, rdiffs = [], []
    for _ in range(4000):
        i = rng.integers(0, len(a), len(a))
        diffs.append(np.mean((ed[i] - a[i]) ** 2) - np.mean((es[i] - a[i]) ** 2))
        rdiffs.append(stats.pearsonr(ed[i], a[i])[0] - stats.pearsonr(es[i], a[i])[0])
    summary["dpg_minus_seed"] = {
        "mse_diff_ci": [float(x) for x in np.percentile(diffs, [2.5, 97.5])],
        "pearson_diff_ci": [float(x) for x in np.percentile(rdiffs, [2.5, 97.5])],
        "p_dpg_better_mse": float(np.mean(np.array(diffs) < 0)),
    }
    for name, x in (("dpg", "dpg"), ("both", "both")):
        d = bout_ll[x] - bout_ll["seed"]
        bs = [np.mean(d[i]) for i in (rng.integers(0, len(d), len(d)) for _ in range(4000))]
        summary[f"{name}_minus_seed"] = {**summary.get(f"{name}_minus_seed", {}),
                                         "bout_log_loss_diff": float(np.mean(d)),
                                         "bout_log_loss_diff_ci": [float(v) for v in np.percentile(bs, [2.5, 97.5])]}
    # bouts where the two single models pick different winners: who was right?
    dis = [(w - l > 0, ls > ws) for w, l, ws, ls in test_bouts if (w - l > 0) != (ls > ws)]
    summary["disagreements"] = {"bouts": len(dis), "dpg_right": sum(a for a, _ in dis),
                                "seed_right": sum(b for _, b in dis),
                                "binom_p": float(stats.binomtest(sum(b for _, b in dis), len(dis)).pvalue)}
    out = {"params": params, "fit_bouts": len(fit_bouts), "test_bouts": len(test_bouts), "n_sims": N_SIMS,
           "fit_years": FIT_YEARS, "test_years": TEST_YEARS, "summary": summary}
    OUT.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
