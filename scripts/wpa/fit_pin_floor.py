#!/usr/bin/env python3
"""
The comeback floor (TJ, 2026-10-03): no wrestler's win probability drops below the chance that a wrestler that far
behind wins by pin in the time left -- the "hail mary". The state table alone could go to ~0 where its cells were
thin (Swiderski 2023 NCAA, down 7 + a locked riding-time point with 1:38 left, came out at 1 in 22,000; he pinned
Cornella with 0:12 left). A pin doesn't care about the score, so the floor depends only on the time left.

Data: the 10-second samples of every table_ok bout (NCAA + conference, both eras) where one wrestler trails by 6 or
more, a locked riding-time point counted as already scored. y = the trailing wrestler went on to win by fall.
Fitted curve (maximum likelihood, samples within a bout are correlated, so read the fit as a point estimate):

    floor(t) = a * (min(t, 180) / 60) ** b        t = seconds left in regulation

(b > 1: pins from behind get rarer per second as the clock runs down -- the leader rides out or stays off the mat.)
Capped at its 3:00 value: earlier, the curve would keep rising (raw: 1.3% at 4:00, 2.0% at 5:00) and start overriding
the seed-based odds of big mismatches at the opening whistle, where nobody is behind yet.
The raw rates at 3:00 / 2:30 / ... / 0:10 are in the report for comparison. WPModel applies the floor to the final
WP in regulation: floor(t) <= WP <= 1 - floor(t). Overtime is not floored (sudden victory: nobody is "down 6").

Outputs: data/wpa/model/pin_floor.json, data/wpa/reports/pin_floor.md.
Usage: .venv/bin/python scripts/wpa/fit_pin_floor.py   (needs step 2; run before fit_strength / validate / compute_wpa)
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parent.parent.parent
STATES = ROOT / "data/wpa/states"
OUT = ROOT / "data/wpa/model/pin_floor.json"
REP = ROOT / "data/wpa/reports/pin_floor.md"
DEFICIT = 6
FIT_MAX_T = 240          # fitted on periods 2-3; earlier deficits of 6+ are rare and the floor is far below the WP there
CAP_T = 180              # the floor stops rising at 3:00 left (see the docstring)
CHECKPOINTS = [300, 240, 180, 150, 120, 90, 60, 30, 10]
LOCK = {"locked_in": 1, "locked_out": -1}


def floor(t, prm):
    return prm["a"] * (np.clip(np.asarray(t, float), 0, prm["cap_t"]) / 60.0) ** prm["b"]


def load():
    S, B = [], []
    for k in ("ncaa", "conf"):
        S.append(pd.read_csv(STATES / f"{k}_samples.csv"))
        B.append(pd.read_csv(STATES / f"{k}_bouts.csv", usecols=["bout_key", "table_ok", "result_type"]))
    b = pd.concat(B)
    s = pd.concat(S).merge(b[b["table_ok"] == True][["bout_key", "result_type"]], on="bout_key")  # noqa: E712
    s = s[s["t_rem"] > 0].copy()
    s["eff"] = s["margin"] + s["rt_status"].map(LOCK).fillna(0)   # winner-side: eff < 0 = the winner was behind
    s = s[s["eff"].abs() >= DEFICIT]
    s["y"] = ((s["eff"] < 0) & (s["result_type"] == "Fall")).astype(int)
    return s


def fit(s):
    d = s[s["t_rem"] <= FIT_MAX_T]
    t, y = d["t_rem"].to_numpy(float), d["y"].to_numpy(float)

    def nll(x):
        p = np.clip(np.exp(x[0]) * (t / 60.0) ** x[1], 1e-12, 1 - 1e-12)
        return -(y * np.log(p) + (1 - y) * np.log1p(-p)).sum()

    r = minimize(nll, [np.log(0.002), 1.0], method="Nelder-Mead")
    return {"a": float(np.exp(r.x[0])), "b": float(r.x[1]), "cap_t": CAP_T, "deficit": DEFICIT, "fit_max_t": FIT_MAX_T,
            "samples": int(len(d)), "bouts": int(d["bout_key"].nunique()),
            "pin_comebacks": int(d.loc[d["y"] == 1, "bout_key"].nunique())}


def checkpoints(s):
    rows = []
    for cp in CHECKPOINTS:
        x = s[(s["t_rem"] <= cp) & (s["t_rem"] >= cp - 9)].sort_values("t_rem", ascending=False)
        x = x.groupby("bout_key").head(1)
        rows.append((cp, len(x), int(x["y"].sum())))
    return rows


def main():
    t0 = time.time()
    s = load()
    prm = fit(s)
    prm["built"] = time.strftime("%Y-%m-%d")
    OUT.write_text(json.dumps(prm, indent=2) + "\n")
    L = ["# Comeback floor (pin from behind)\n",
         f"Built {prm['built']} by `scripts/wpa/fit_pin_floor.py`. Trailing by {DEFICIT}+ (a locked riding-time point "
         f"counted as scored), NCAA + conference tournaments, 10-s samples with {FIT_MAX_T // 60}:00 or less left: "
         f"{prm['samples']:,} samples from {prm['bouts']:,} bouts, {prm['pin_comebacks']} different pin comebacks.\n",
         f"**floor(t) = {prm['a']:.5f} × (min(seconds left, {CAP_T}) / 60) ^ {prm['b']:.3f}** (max "
         f"{100 * floor(CAP_T, prm):.2f}%, from 3:00 left on) — applied to the final WP in regulation: "
         "floor ≤ WP ≤ 1 − floor.\n",
         "| Time left | Bouts down 6+ then | Trailer won by pin | Raw rate | Floor |", "|---|---|---|---|---|"]
    for cp, n, k in checkpoints(s):
        L.append(f"| {cp // 60}:{cp % 60:02d} | {n:,} | {k} | {100 * k / n:.2f}% | {100 * floor(cp, prm):.2f}% |")
    L.append("\nEach row counts the wrestlers down 6+ at that moment (the same wrestler appears in every row where he "
             "was down 6+), so the rows overlap; the curve is fitted on all the samples at once.")
    REP.write_text("\n".join(L) + "\n")
    print("\n".join(L[3:]))
    print("wrote", OUT, REP, f"({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
