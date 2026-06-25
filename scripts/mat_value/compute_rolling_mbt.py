#!/usr/bin/env python3
"""
Rolling MBT ratings — compute each wrestler's TPAR trajectory through the season.

Strategy: collect every unique match date in the season, then run one full MBT
solve per date using all matches up to and including that date. Each wrestler's
timeline is their rating extracted at each date they competed.

Output: rolling_mbt_{season}.json
  {
    "wrestler_id": [
      {"date": "11/02/2025", "tpar": 1.23, "matches": 3},
      {"date": "11/15/2025", "tpar": 1.87, "matches": 5},
      ...
    ],
    ...
  }

Run:
  .venv/bin/python scripts/mat_value/compute_rolling_mbt.py
  .venv/bin/python scripts/mat_value/compute_rolling_mbt.py --season 2026 --min-matches 2
"""

import argparse, json, os, pathlib, re, sys
import numpy as np
from collections import defaultdict
from datetime import datetime

# ── Constants (must match tpar_massey_bt.py) ─────────────────────────────────
WEIGHTS         = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]
MASSEY_LAMBDA   = 2.0
BT_REG          = 1.0
BT_ITERS        = 500
FLOOR_RANKS     = (62, 66)
TOURNAMENT_DATE = "03/21/2026"
SPLIT_WM        = 0.50          # 50/50 Massey/BT

MARGIN_MAP = {
    "Dec": 3, "SV-1": 3, "SV-2": 3, "SV-3": 3,
    "TB-1": 3, "TB-2": 3, "TB-3": 3,
    "MD": 4, "TF": 5, "Fall": 6, "Inj.": 6, "DQ": 6,
}

def parse_date(s):
    """Parse MM/DD/YYYY to a sortable datetime."""
    try:
        return datetime.strptime(s, "%m/%d/%Y")
    except Exception:
        return datetime.min

def get_margin(result):
    if not result:
        return None
    return MARGIN_MAP.get(result.split()[0])

def loser_id(m):
    return m["wrestler2_id"] if m["winner_id"] == m["wrestler1_id"] else m["wrestler1_id"]

def build_edges(matches, weight, cutoff_date):
    """Edges for one weight using matches on or before cutoff_date."""
    edges = []
    for m in matches:
        if m["weight_class"] != str(weight):
            continue
        if parse_date(m["date"]) > cutoff_date:
            continue
        if m["date"] == TOURNAMENT_DATE:
            continue
        v = get_margin(m["result"])
        if v is None:
            continue
        edges.append((m["winner_id"], loser_id(m), v))
    return edges


# ── Rating algorithms ─────────────────────────────────────────────────────────

def massey(edges, ids):
    if not ids:
        return {}
    idx = {w: k for k, w in enumerate(ids)}
    n = len(ids)
    A = np.zeros((n, n)); b = np.zeros(n)
    for w, l, v in edges:
        i, j = idx[w], idx[l]
        A[i,i] += 1; A[j,j] += 1; A[i,j] -= 1; A[j,i] -= 1
        b[i] += v; b[j] -= v
    A += MASSEY_LAMBDA * np.eye(n)
    r = np.linalg.solve(A, b)
    return {ids[k]: r[k] for k in range(n)}

def bradley_terry(edges, ids):
    if not ids:
        return {}
    wins  = defaultdict(float)
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
            den = (sum(games[i][j] / (p[i] + p[j]) for j in games[i])
                   + 2.0 * BT_REG / (p[i] + 1.0))
            new[i] = num / den if den > 0 else p[i]
        s = np.mean(list(new.values()))
        p = {i: new[i] / s for i in ids}
    return {i: np.log(max(p[i], 1e-9)) for i in ids}

def weight_floor(fused, ids):
    order = sorted(ids, key=lambda i: (-fused[i], str(i)))
    lo, hi = FLOOR_RANKS
    if len(order) >= hi:
        chosen = order[lo - 1:hi]
    else:
        chosen = order[-5:] if len(order) >= 5 else order
    return float(np.mean([fused[i] for i in chosen])) if chosen else 0.0

def solve_mbt(all_matches_by_weight, cutoff_date):
    """
    Run full MBT pipeline for all matches on or before cutoff_date.
    Returns {wrestler_id: tpar_50_50} and {wrestler_id: match_count}.
    """
    per_weight = {}
    pool_bt, pool_ma = [], []

    for w in WEIGHTS:
        edges = build_edges(all_matches_by_weight[w], w, cutoff_date)
        if not edges:
            per_weight[w] = dict(ids=[], deg=defaultdict(int), ma={}, bt={})
            continue
        ids = sorted({x for e in edges for x in e[:2]})
        deg = defaultdict(int)
        for a, bb, _ in edges:
            deg[a] += 1; deg[bb] += 1
        ma = massey(edges, ids)
        bt = bradley_terry(edges, ids)
        per_weight[w] = dict(ids=ids, deg=deg, ma=ma, bt=bt)
        for i in ids:
            pool_bt.append(bt[i]); pool_ma.append(ma[i])

    if len(pool_bt) < 2:
        return {}, {}

    b1, b0 = np.polyfit(np.array(pool_bt), np.array(pool_ma), 1)

    floors = []
    fused_by_weight = {}
    for w in WEIGHTS:
        pw = per_weight[w]
        if not pw["ids"]:
            fused_by_weight[w] = {}
            continue
        fused = {
            i: SPLIT_WM * pw["ma"][i] + (1 - SPLIT_WM) * (b0 + b1 * pw["bt"][i])
            for i in pw["ids"]
        }
        fused_by_weight[w] = fused
        floors.append(weight_floor(fused, pw["ids"]))

    global_offset = float(np.mean(floors)) if floors else 0.0

    scores = {}
    deg_all = {}
    for w in WEIGHTS:
        pw = per_weight[w]
        fused = fused_by_weight[w]
        for i in pw["ids"]:
            scores[i]  = round(fused[i] - global_offset, 4)
            deg_all[i] = pw["deg"][i]

    return scores, deg_all


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season",       type=int, default=2026)
    ap.add_argument("--min-matches",  type=int, default=1,
                    help="Min matches for a wrestler to appear in timeline")
    ap.add_argument("--sample-every", type=int, default=1,
                    help="Include every Nth date (1=all dates, 7=~weekly)")
    a = ap.parse_args()

    DATA_DIR     = f"mt/rankings_data/ncaa_men/{a.season}"
    FRONTEND_DIR = "frontend/wrestledata-ui/public/data"
    OUT_FILE     = pathlib.Path(f"{FRONTEND_DIR}/mat_value/{a.season}/rolling_mbt_{a.season}.json")

    print(f"Loading match data for {a.season}...")
    all_matches_by_weight = {}
    all_dates = set()

    for w in WEIGHTS:
        path = os.path.join(DATA_DIR, f"weight_class_{w}.json")
        with open(path) as f:
            matches = json.load(f)["matches"]
        all_matches_by_weight[w] = matches
        for m in matches:
            if m.get("date") and m["date"] != TOURNAMENT_DATE and get_margin(m.get("result")):
                all_dates.add(m["date"])

    # Build sorted list of dates, sampling every Nth if requested
    sorted_dates = sorted(all_dates, key=parse_date)
    if a.sample_every > 1:
        sorted_dates = sorted_dates[::a.sample_every]

    print(f"  {len(all_dates)} unique match dates  →  {len(sorted_dates)} snapshots to compute")

    # Per-wrestler: which dates did they compete on?
    wrestler_dates = defaultdict(set)
    for w in WEIGHTS:
        for m in all_matches_by_weight[w]:
            if m.get("date") and m["date"] != TOURNAMENT_DATE and get_margin(m.get("result")):
                for wid in (m.get("wrestler1_id"), m.get("wrestler2_id")):
                    if wid:
                        wrestler_dates[wid].add(m["date"])

    # Solve MBT at each snapshot date
    print(f"Running {len(sorted_dates)} MBT solves...")
    snapshots = {}  # date_str -> {wrestler_id: (tpar, n_matches)}

    for i, date_str in enumerate(sorted_dates):
        cutoff = parse_date(date_str)
        scores, deg = solve_mbt(all_matches_by_weight, cutoff)
        snapshots[date_str] = {wid: (scores[wid], deg[wid]) for wid in scores}
        if (i + 1) % 10 == 0 or i == len(sorted_dates) - 1:
            print(f"  [{i+1}/{len(sorted_dates)}] through {date_str}  ({len(scores)} wrestlers rated)")

    # Build per-wrestler timelines
    # A wrestler's timeline includes a point for each snapshot date on or after
    # their first match — specifically on dates where they personally competed.
    print("\nBuilding wrestler timelines...")
    timelines = {}

    for wid, my_dates in wrestler_dates.items():
        # Find the snapshot dates that fall on or after the wrestler's first match
        # and where the wrestler had a match (so the point is "after this match")
        my_sorted_dates = sorted(my_dates, key=parse_date)
        if not my_sorted_dates:
            continue

        timeline = []
        for snap_date in sorted_dates:
            # Include this snapshot if the wrestler competed on this exact date
            if snap_date not in my_dates:
                continue
            snap = snapshots.get(snap_date, {})
            if wid not in snap:
                continue
            tpar, n = snap[wid]
            if n >= a.min_matches:
                timeline.append({
                    "date":    snap_date,
                    "tpar":    tpar,
                    "matches": n,
                })

        if timeline:
            timelines[wid] = timeline

    # Save
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUT_FILE.open("w") as f:
        json.dump(timelines, f)

    n_wrestlers = len(timelines)
    avg_points  = sum(len(v) for v in timelines.values()) / max(n_wrestlers, 1)
    print(f"\nSaved {n_wrestlers} wrestlers  (avg {avg_points:.1f} timeline points each)")
    print(f"→ {OUT_FILE}")

    # Quick sanity: show trajectory for one well-known wrestler
    with open(f"{FRONTEND_DIR}/wrestlers/{a.season}/index_wrestlers.json") as f:
        index = json.load(f)
    by_name = {w["name"]: w["wrestler_id"] for w in index}
    sample_name = "Luke Lilledahl"
    sample_id   = by_name.get(sample_name)
    if sample_id and sample_id in timelines:
        print(f"\nSample — {sample_name}:")
        for pt in timelines[sample_id]:
            print(f"  {pt['date']}  TPAR={pt['tpar']:+.3f}  matches={pt['matches']}")


if __name__ == "__main__":
    main()
