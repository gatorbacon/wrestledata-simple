#!/usr/bin/env python3
"""
TPAR — Massey/BT Fusion : CANONICAL REFERENCE IMPLEMENTATION
============================================================
This file is authoritative. Any re-implementation must reproduce its output
exactly. Every step is deterministic given the constants below.

Pipeline (per the spec):
  1. Load matches from per-weight JSON files.
  2. Map each result to a signed margin (forfeits skipped).
  3. Build one independent match graph per weight (optionally excluding dates).
  4. MASSEY rating  : ridge-regularized least squares on margins (lambda=2.0).
  5. BRADLEY-TERRY  : MM algorithm on wins/losses (reg=1.0, 500 iters), log-strength.
  6. GLOBAL alignment: one linear map BT->Massey units, fit over ALL rated wrestlers.
  7. FUSE at 100/0, 75/25, 50/50 (Massey weight / BT weight).
  8. OFFSET: per-weight floor = mean of the wrestlers ranked 29-33 in that weight
     (by the fused metric); GLOBAL offset = mean of weight floors; subtract from all.
     Computed independently per split. Bracket-independent (works any week).
  9. Output ranked tables (min 3 matches to be listed).

Inputs: weight_class_<W>.json for W in WEIGHTS. No other files required.
(The tournament bracket CSV was used only for development validation; production
 does not need it. NCAA results live in the JSON as date == TOURNAMENT_DATE.)
"""
import argparse, glob, json, os, re
import numpy as np
from collections import defaultdict

# ----------------------------- CONSTANTS (locked) ---------------------------
WEIGHTS = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]
MASSEY_LAMBDA   = 2.0     # ridge; ~2 phantom matches vs an average (rating-0) opponent
BT_REG          = 1.0     # Bradley-Terry regularization (virtual win+loss vs avg)
BT_ITERS        = 500     # fixed MM iterations (deterministic)
MIN_MATCHES     = 3       # display threshold only; ratings computed for everyone
FLOOR_RANKS     = (29, 33)  # inclusive 1-based ranks defining the replacement floor
SPLITS = {"100_0": 1.00, "75_25": 0.75, "50_50": 0.50}  # value = Massey weight
TOURNAMENT_DATE = "03/21/2026"

# result token -> signed margin for the winner (loser is negated). None = skip.
MARGIN = {"Dec": 3, "SV-1": 3, "SV-2": 3, "SV-3": 3, "TB-1": 3, "TB-2": 3, "TB-3": 3,
          "MD": 4, "TF": 5, "Fall": 6, "Inj.": 6, "DQ": 6}
# Forfeit-like tokens are skipped: MFFL, "M." (M. For.), "Def.", Forfeit, etc.


# ------------------------------- helpers ------------------------------------
def margin(result):
    if not result:
        return None
    return MARGIN.get(result.split()[0])  # None => forfeit/default => skip

def loser_id(m):
    return m["wrestler2_id"] if m["winner_id"] == m["wrestler1_id"] else m["wrestler1_id"]

def build_edges(matches, weight, exclude_dates):
    """List of (winner_id, loser_id, margin) for one weight."""
    E = []
    for m in matches:
        if m["weight_class"] != str(weight):
            continue
        if m["date"] in exclude_dates:
            continue
        v = margin(m["result"])
        if v is None:
            continue
        E.append((m["winner_id"], loser_id(m), v))
    return E


# ------------------------------- ratings ------------------------------------
def massey(edges, ids):
    """Ridge least squares: for each match margin_ij ~ r_i - r_j. Deterministic."""
    idx = {w: k for k, w in enumerate(ids)}
    n = len(ids)
    A = np.zeros((n, n)); b = np.zeros(n)
    for w, l, v in edges:
        i, j = idx[w], idx[l]
        A[i, i] += 1; A[j, j] += 1; A[i, j] -= 1; A[j, i] -= 1
        b[i] += v; b[j] -= v
    A += MASSEY_LAMBDA * np.eye(n)
    r = np.linalg.solve(A, b)
    return {ids[k]: r[k] for k in range(n)}

def bradley_terry(edges, ids):
    """MM algorithm with regularization. Returns log-strength. Deterministic
    (fixed init p=1.0, fixed iteration count, mean-normalized each pass)."""
    wins = defaultdict(float)
    games = defaultdict(lambda: defaultdict(float))
    for w, l, v in edges:
        wins[w] += 1.0
        games[w][l] += 1.0
        games[l][w] += 1.0
    p = {i: 1.0 for i in ids}
    for _ in range(BT_ITERS):
        new = {}
        for i in ids:
            num = wins[i] + BT_REG
            den = sum(games[i][j] / (p[i] + p[j]) for j in games[i]) + 2.0 * BT_REG / (p[i] + 1.0)
            new[i] = num / den if den > 0 else p[i]
        s = np.mean(list(new.values()))
        p = {i: new[i] / s for i in ids}
    return {i: np.log(max(p[i], 1e-9)) for i in ids}


# ------------------------------- offset -------------------------------------
def weight_floor(values_by_id, ids):
    """Mean of wrestlers ranked 29..33 (1-based) within this weight, by `values`.
    Deterministic tie-break: descending value, then ascending wrestler id.
    Fallback if <33 ranked: mean of the lowest 5 available (or all if <5)."""
    order = sorted(ids, key=lambda i: (-values_by_id[i], str(i)))
    lo, hi = FLOOR_RANKS
    if len(order) >= hi:
        chosen = order[lo - 1:hi]            # ranks 29..33
    else:
        chosen = order[-5:] if len(order) >= 5 else order
    return float(np.mean([values_by_id[i] for i in chosen]))


# ------------------------------- main pipeline ------------------------------
def run(data_dir, exclude_dates):
    # Pass A: per-weight networks, Massey + BT, collect pooled (bt, massey) for alignment.
    per_weight = {}
    pool_bt, pool_ma = [], []
    for w in WEIGHTS:
        path = os.path.join(data_dir, f"weight_class_{w}.json")
        with open(path) as f:
            d = json.load(f)
        names = {i: x["name"] for i, x in d["wrestlers"].items()}
        teams = {i: x.get("team", "") for i, x in d["wrestlers"].items()}
        edges = build_edges(d["matches"], w, exclude_dates)
        ids = sorted({x for e in edges for x in e[:2]})
        deg = defaultdict(int)
        for a, b, _ in edges:
            deg[a] += 1; deg[b] += 1
        ma = massey(edges, ids)
        bt = bradley_terry(edges, ids)
        per_weight[w] = dict(names=names, teams=teams, ids=ids, deg=deg, ma=ma, bt=bt)
        for i in ids:
            pool_bt.append(bt[i]); pool_ma.append(ma[i])

    # GLOBAL BT->Massey alignment (degree-1 polyfit over every rated wrestler).
    b1, b0 = np.polyfit(np.array(pool_bt), np.array(pool_ma), 1)   # aligned = b0 + b1*bt

    # Pass B: fuse + offset, per split.
    results = {}  # split -> list of dict rows
    for split, wm in SPLITS.items():
        rows = []
        floors = []
        fused_by_weight = {}
        for w in WEIGHTS:
            pw = per_weight[w]
            fused = {i: wm * pw["ma"][i] + (1 - wm) * (b0 + b1 * pw["bt"][i]) for i in pw["ids"]}
            fused_by_weight[w] = fused
            floors.append(weight_floor(fused, pw["ids"]))
        global_offset = float(np.mean(floors))
        for w in WEIGHTS:
            pw = per_weight[w]
            for i in pw["ids"]:
                rows.append(dict(
                    name=pw["names"].get(i, "?"), team=pw["teams"].get(i, ""),
                    weight=w, matches=pw["deg"][i],
                    tpar=round(fused_by_weight[w][i] - global_offset, 2),
                ))
        rows = [r for r in rows if r["matches"] >= MIN_MATCHES]
        rows.sort(key=lambda r: (-r["tpar"], r["name"]))   # deterministic
        for rk, r in enumerate(rows, 1):
            r["rank"] = rk
        results[split] = (rows, global_offset, (b0, b1))
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="/mnt/user-data/uploads")
    ap.add_argument("--split", default="50_50", choices=list(SPLITS))
    ap.add_argument("--exclude-tournament", action="store_true",
                    help="exclude NCAA results (predictive-test mode)")
    ap.add_argument("--top", type=int, default=30)
    a = ap.parse_args()
    excl = {TOURNAMENT_DATE} if a.exclude_tournament else set()
    res = run(a.data, excl)
    rows, off, (b0, b1) = res[a.split]
    print(f"split={a.split}  global_offset={off:.3f}  align: aligned={b0:+.3f}+{b1:.3f}*BT  "
          f"(tournament {'EXCLUDED' if excl else 'included'})")
    for r in rows[:a.top]:
        print(f"  {r['rank']:3d}. {r['tpar']:+5.2f}  {r['name']} ({r['weight']}, {r['team']})  [{r['matches']}m]")


if __name__ == "__main__":
    main()
