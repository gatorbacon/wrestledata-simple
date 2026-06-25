#!/usr/bin/env python3
"""
TPAR Massey/BT Fusion — prototype (parallel to production TPAR v1/v3b).

Implements docs/tpar_reference.py exactly (same constants, same algorithm).
Additions over the reference:
  - reads from mt/rankings_data/ncaa_men/{SEASON}/
  - evaluates tournament accuracy vs seeds and vs TPAR v1/v3b
  - saves per-wrestler ratings to frontend/.../tpar_mbt_{SEASON}.json
  - --warm-start flag: off for 2026 (no prior season data linked yet);
    enabled for 2027+ by passing a JSON of {wrestler_id: prior_tpar}

Run modes:
  .venv/bin/python scripts/analysis/tpar_massey_bt.py
      Full-season ratings (tournament matches included). Prints top 30 per split.
  .venv/bin/python scripts/analysis/tpar_massey_bt.py --eval-tournament
      Exclude tournament matches, evaluate predictive accuracy vs seeds + v1 + v3b.
  .venv/bin/python scripts/analysis/tpar_massey_bt.py --split 50_50 --top 50
      Print top 50 for the 50/50 split.
"""

import argparse, json, os, pathlib, re, unicodedata
import numpy as np
from collections import defaultdict

# ── Constants (locked — must match docs/tpar_reference.py) ──────────────────
WEIGHTS         = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]
MASSEY_LAMBDA   = 2.0
BT_REG          = 1.0
BT_ITERS        = 500
MIN_MATCHES     = 3
FLOOR_RANKS     = (62, 66)
SPLITS          = {"100_0": 1.00, "75_25": 0.75, "50_50": 0.50}
TOURNAMENT_DATE = "03/21/2026"

# Warm-start: K_WARM phantom matches toward prior-season TPAR (Section 10 of spec).
# Higher = stronger pull toward prior at low match counts, decays naturally as
# real matches accumulate. Off by default; activated by --warm-start flag.
K_WARM = 10

MARGIN_MAP = {
    "Dec": 3, "SV-1": 3, "SV-2": 3, "SV-3": 3,
    "TB-1": 3, "TB-2": 3, "TB-3": 3,
    "MD": 4, "TF": 5, "Fall": 6, "Inj.": 6, "DQ": 6,
}

SEASON       = 2026
DATA_DIR     = f"mt/rankings_data/ncaa_men/{SEASON}"
FRONTEND_DIR = "frontend/wrestledata-ui/public/data"
TOURNEY_FILE = f"data/{SEASON}/ncaa-tourney/parsed/matches.json"
V1_FILE      = f"{FRONTEND_DIR}/mat_value/{SEASON}/match_mv_impact_{SEASON}.json"
V3B_FILE     = f"{FRONTEND_DIR}/mat_value/{SEASON}/match_mv_impact_v3b_{SEASON}.json"
INDEX_FILE   = f"{FRONTEND_DIR}/wrestlers/{SEASON}/index_wrestlers.json"
OUT_FILE     = f"{FRONTEND_DIR}/mat_value/{SEASON}/tpar_mbt_{SEASON}.json"


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_margin(result):
    if not result:
        return None
    return MARGIN_MAP.get(result.split()[0])  # None → skip (forfeit/default)

def loser_id(m):
    return m["wrestler2_id"] if m["winner_id"] == m["wrestler1_id"] else m["wrestler1_id"]

def build_edges(matches, weight, exclude_dates):
    edges = []
    for m in matches:
        if m["weight_class"] != str(weight):
            continue
        if m["date"] in exclude_dates:
            continue
        v = get_margin(m["result"])
        if v is None:
            continue
        edges.append((m["winner_id"], loser_id(m), v))
    return edges

def norm_name(name):
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", name.strip().lower())


# ── Rating algorithms ─────────────────────────────────────────────────────────

def massey(edges, ids, warm_prior=None):
    """Ridge least-squares: margin_ij ≈ r_i - r_j. LAMBDA=2.0."""
    idx = {w: k for k, w in enumerate(ids)}
    n = len(ids)
    A = np.zeros((n, n)); b = np.zeros(n)
    for w, l, v in edges:
        i, j = idx[w], idx[l]
        A[i,i] += 1; A[j,j] += 1; A[i,j] -= 1; A[j,i] -= 1
        b[i] += v; b[j] -= v
    # Warm-start: K_WARM phantom matches vs average (0-rated) opponent, anchored
    # at prior-season TPAR. Pulls toward prior when match count is low, fades
    # automatically as real matches accumulate (prior weight ≈ K_WARM/(K_WARM+n)).
    if warm_prior:
        for k, wid in enumerate(ids):
            prior = warm_prior.get(wid, 0.0)  # 0.0 for freshmen / unlinked wrestlers
            A[k, k] += K_WARM
            b[k]    += K_WARM * prior
    A += MASSEY_LAMBDA * np.eye(n)
    r = np.linalg.solve(A, b)
    return {ids[k]: r[k] for k in range(n)}

def bradley_terry(edges, ids):
    """MM algorithm, BT_REG=1.0, BT_ITERS=500, mean-normalized each pass.
    Returns log-strength. Deterministic (fixed init + fixed iteration count)."""
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


# ── Offset ────────────────────────────────────────────────────────────────────

def weight_floor(values_by_id, ids):
    """Mean fused score of wrestlers ranked 29-33 (1-based) at this weight."""
    order = sorted(ids, key=lambda i: (-values_by_id[i], str(i)))
    lo, hi = FLOOR_RANKS
    if len(order) >= hi:
        chosen = order[lo - 1:hi]          # ranks 29..33 inclusive
    else:
        chosen = order[-5:] if len(order) >= 5 else order
    return float(np.mean([values_by_id[i] for i in chosen]))


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run(data_dir, exclude_dates, warm_prior=None):
    """
    Returns {split: (rows, global_offset, (b0, b1), scores_by_id)}
    where scores_by_id[wrestler_id] = tpar (no MIN_MATCHES filter, for accuracy eval).
    """
    per_weight = {}
    pool_bt, pool_ma = [], []

    for w in WEIGHTS:
        path = os.path.join(data_dir, f"weight_class_{w}.json")
        with open(path) as f:
            d = json.load(f)
        names = {i: x["name"] for i, x in d["wrestlers"].items()}
        teams = {i: x.get("team", "") for i, x in d["wrestlers"].items()}
        edges = build_edges(d["matches"], w, exclude_dates)
        ids   = sorted({x for e in edges for x in e[:2]})
        deg   = defaultdict(int)
        for a, bb, _ in edges:
            deg[a] += 1; deg[bb] += 1
        ma = massey(edges, ids, warm_prior=warm_prior)
        bt = bradley_terry(edges, ids)
        per_weight[w] = dict(names=names, teams=teams, ids=ids, deg=deg, ma=ma, bt=bt)
        for i in ids:
            pool_bt.append(bt[i]); pool_ma.append(ma[i])

    # Global BT→Massey alignment (one polyfit across all weights, not per-weight)
    b1, b0 = np.polyfit(np.array(pool_bt), np.array(pool_ma), 1)

    results = {}
    for split, wm in SPLITS.items():
        rows = []
        floors = []
        fused_by_weight = {}

        for w in WEIGHTS:
            pw = per_weight[w]
            fused = {
                i: wm * pw["ma"][i] + (1 - wm) * (b0 + b1 * pw["bt"][i])
                for i in pw["ids"]
            }
            fused_by_weight[w] = fused
            floors.append(weight_floor(fused, pw["ids"]))

        global_offset = float(np.mean(floors))

        # Full score lookup (no match-count filter) for accuracy evaluation
        scores_by_id = {}
        for w in WEIGHTS:
            pw = per_weight[w]
            for i in pw["ids"]:
                scores_by_id[i] = round(fused_by_weight[w][i] - global_offset, 4)

        for w in WEIGHTS:
            pw = per_weight[w]
            for i in pw["ids"]:
                rows.append(dict(
                    wrestler_id=i,
                    name=pw["names"].get(i, "?"),
                    team=pw["teams"].get(i, ""),
                    weight=w,
                    matches=pw["deg"][i],
                    tpar=round(fused_by_weight[w][i] - global_offset, 4),
                ))

        rows = [r for r in rows if r["matches"] >= MIN_MATCHES]
        rows.sort(key=lambda r: (-r["tpar"], r["name"]))
        for rk, r in enumerate(rows, 1):
            r["rank"] = rk
        results[split] = (rows, global_offset, (b0, b1), scores_by_id)

    return results, (b0, b1)


# ── Tournament accuracy evaluation ────────────────────────────────────────────

def load_pretourney_avg(path):
    """Load a v1/v3b match_mv_impact file → {wrestler_id: pre-tournament avg}."""
    with open(path) as f:
        raw = json.load(f)
    out = {}
    for wid, matches in raw.items():
        reg = [m["mv_impact"] for m in matches if m["date"] != TOURNAMENT_DATE]
        if reg:
            out[wid] = sum(reg) / len(reg)
    return out

def evaluate_accuracy(scores, by_name_wt, tourney_matches, label=""):
    correct = total = 0
    conf_stats = defaultdict(lambda: [0, 0])
    bucket_stats = defaultdict(lambda: [0, 0])
    BUCKETS = [("< 0.5", 0, 0.5), ("0.5-1.0", 0.5, 1.0),
               ("1.0-2.0", 1.0, 2.0), ("2.0-3.0", 2.0, 3.0), ("3.0+", 3.0, 99)]

    for m in tourney_matches:
        if m.get("result_type") in {"Forfeit", "MFF"}:
            continue
        wt   = int(m["weight"])
        w_id = by_name_wt.get((norm_name(m["winner_name"]), wt))
        l_id = by_name_wt.get((norm_name(m["loser_name"]),  wt))
        ws   = scores.get(w_id) if w_id else None
        ls   = scores.get(l_id) if l_id else None
        if ws is None or ls is None:
            continue
        total += 1
        ok = ws >= ls
        if ok:
            correct += 1
        for wc in {m.get("winner_team","?"), m.get("loser_team","?")}:
            conf_stats[wc][1] += 1
            if ok: conf_stats[wc][0] += 1
        diff = abs(ws - ls)
        for blabel, lo, hi in BUCKETS:
            if lo <= diff < hi:
                bucket_stats[blabel][1] += 1
                if ok: bucket_stats[blabel][0] += 1
                break

    pct = 100 * correct / total if total else 0
    return correct, total, pct, bucket_stats

def seed_accuracy(tourney_matches):
    correct = total = 0
    for m in tourney_matches:
        if m.get("result_type") in {"Forfeit", "MFF"}:
            continue
        ws, ls = m.get("winner_seed"), m.get("loser_seed")
        if ws is None or ls is None:
            continue
        total += 1
        if ws < ls:
            correct += 1
    return correct, total, 100 * correct / total if total else 0


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season",            type=int, default=SEASON)
    ap.add_argument("--split",             default="50_50", choices=list(SPLITS))
    ap.add_argument("--top",               type=int, default=30)
    ap.add_argument("--eval-tournament",   action="store_true",
                    help="Exclude tournament matches; evaluate predictive accuracy")
    ap.add_argument("--save",              action="store_true",
                    help="Save full ratings to tpar_mbt_{season}.json")
    ap.add_argument("--warm-start",        type=str, default=None,
                    help="Path to JSON {wrestler_id: prior_tpar} for warm-start prior")
    a = ap.parse_args()

    exclude = {TOURNAMENT_DATE} if a.eval_tournament else set()
    mode    = "PREDICTIVE (tournament excluded)" if a.eval_tournament else "FULL SEASON"

    warm_prior = None
    if a.warm_start:
        with open(a.warm_start) as f:
            warm_prior = json.load(f)
        print(f"  Warm-start: loaded {len(warm_prior)} prior-season ratings from {a.warm_start}")

    print(f"\n{'='*65}")
    print(f"  TPAR Massey/BT Fusion — {mode}")
    print(f"{'='*65}")

    data_dir = f"mt/rankings_data/ncaa_men/{a.season}"
    print(f"  Data: {data_dir}")
    print(f"  Building ratings...", flush=True)

    results, (b0, b1) = run(data_dir, exclude, warm_prior=warm_prior)

    print(f"  BT→Massey alignment: slope={b1:.3f}  intercept={b0:.3f}")

    # ── Reproduction checklist ────────────────────────────────────────────────
    print(f"\n  Reproduction check (from spec Section 12):")
    for sp in ["50_50", "75_25", "100_0"]:
        rows, off, _, _ = results[sp]
        top3 = [f"{r['name']} ({r['weight']})" for r in rows[:3]]
        print(f"    {sp}: offset={off:.3f}  top3={top3}")

    # ── Top-N table ───────────────────────────────────────────────────────────
    rows, global_offset, _, _ = results[a.split]
    print(f"\n{'='*65}")
    print(f"  Top {a.top} — split={a.split}  global_offset={global_offset:.3f}")
    print(f"{'='*65}")
    print(f"  {'Rk':>3}  {'TPAR':>6}  {'Name':<24}  {'Wt':>4}  {'Team':<26}  {'M':>4}")
    print(f"  {'-'*3}  {'-'*6}  {'-'*24}  {'-'*4}  {'-'*26}  {'-'*4}")
    for r in rows[:a.top]:
        print(f"  {r['rank']:>3}  {r['tpar']:>+6.2f}  {r['name']:<24}  "
              f"{r['weight']:>4}  {r['team']:<26}  {r['matches']:>4}")

    # ── Tournament accuracy evaluation ────────────────────────────────────────
    if a.eval_tournament:
        print(f"\n{'='*65}")
        print(f"  Tournament accuracy — predictive test")
        print(f"{'='*65}")

        with open(INDEX_FILE) as f:
            index = json.load(f)
        by_name_wt = {(norm_name(w["name"]), int(w["weight_class"])): w["wrestler_id"] for w in index}

        with open(TOURNEY_FILE) as f:
            tourney = json.load(f)

        # Seeds baseline
        sc, st, sp_ = seed_accuracy(tourney)
        print(f"  Seeds:     {sc}/{st}  ({sp_:.1f}%)")

        # v1 baseline
        tpar_v1 = load_pretourney_avg(V1_FILE)
        v1c, v1t, v1p, _ = evaluate_accuracy(tpar_v1, by_name_wt, tourney)
        print(f"  TPAR v1:   {v1c}/{v1t}  ({v1p:.1f}%)")

        # v3b baseline
        tpar_v3b = load_pretourney_avg(V3B_FILE)
        v3c, v3t, v3p, _ = evaluate_accuracy(tpar_v3b, by_name_wt, tourney)
        print(f"  TPAR v3b:  {v3c}/{v3t}  ({v3p:.1f}%)")

        # Massey/BT splits
        print()
        BUCKETS_ORDER = ["< 0.5", "0.5-1.0", "1.0-2.0", "2.0-3.0", "3.0+"]
        for sp in ["100_0", "75_25", "50_50"]:
            _, _, _, scores = results[sp]
            c, t, pct, bkts = evaluate_accuracy(scores, by_name_wt, tourney)
            dv1 = pct - v1p; ds = pct - sp_
            print(f"  MBT {sp}:  {c}/{t}  ({pct:.1f}%)   vs v1 {dv1:+.1f}pp   vs seeds {ds:+.1f}pp")
            for bl in BUCKETS_ORDER:
                bk = bkts.get(bl, [0, 0])
                if bk[1] > 0:
                    print(f"             {bl:<10} {bk[1]:>4} matches  {bk[0]:>4} correct  ({100*bk[0]/bk[1]:>5.1f}%)")
            print()

        # Per-weight breakdown for the headline split
        _, _, _, scores = results["50_50"]
        print(f"  Per-weight accuracy — MBT 50_50 vs seeds vs v1:")
        print(f"  {'Wt':>4}  {'n':>5}  {'MBT%':>7}  {'Seed%':>7}  {'v1%':>7}")
        print(f"  {'-'*4}  {'-'*5}  {'-'*7}  {'-'*7}  {'-'*7}")
        for wt in WEIGHTS:
            wt_matches = [m for m in tourney
                          if int(m["weight"]) == wt
                          and m.get("result_type") not in {"Forfeit","MFF"}]
            wt_total = len(wt_matches)
            if wt_total == 0:
                continue
            def _acc(score_dict):
                ok = 0
                for m in wt_matches:
                    w_id = by_name_wt.get((norm_name(m["winner_name"]), wt))
                    l_id = by_name_wt.get((norm_name(m["loser_name"]),  wt))
                    ws = score_dict.get(w_id) if w_id else None
                    ls = score_dict.get(l_id) if l_id else None
                    if ws is not None and ls is not None and ws >= ls:
                        ok += 1
                return ok
            def _seed_acc():
                ok = sum(1 for m in wt_matches
                         if m.get("winner_seed") and m.get("loser_seed")
                         and m["winner_seed"] < m["loser_seed"])
                return ok
            mbt_ok = _acc(scores)
            v1_ok  = _acc(tpar_v1)
            s_ok   = _seed_acc()
            print(f"  {wt:>4}  {wt_total:>5}  {100*mbt_ok/wt_total:>6.1f}%  "
                  f"{100*s_ok/wt_total:>6.1f}%  {100*v1_ok/wt_total:>6.1f}%")

    # ── Save output ───────────────────────────────────────────────────────────
    if a.save or a.eval_tournament:
        _, _, _, scores_50 = results["50_50"]
        _, _, _, scores_75 = results["75_25"]
        _, _, _, scores_100 = results["100_0"]

        # Build wrestler lookup from index for metadata
        with open(INDEX_FILE) as f:
            index = json.load(f)
        idx_meta = {w["wrestler_id"]: w for w in index}

        # Build rank lookup from 50/50 rows (the headline split)
        rows_50, _, _, _ = results["50_50"]
        rank_50 = {r["wrestler_id"]: r["rank"] for r in rows_50}

        out = {}
        all_ids = set(scores_50) | set(scores_75) | set(scores_100)
        for wid in all_ids:
            meta = idx_meta.get(wid, {})
            out[wid] = {
                "tpar_50_50":  scores_50.get(wid),
                "tpar_75_25":  scores_75.get(wid),
                "tpar_100_0":  scores_100.get(wid),
                "rank_50_50":  rank_50.get(wid),
                "weight":      meta.get("weight_class"),
                "name":        meta.get("name"),
                "team":        meta.get("team"),
            }

        pathlib.Path(OUT_FILE).parent.mkdir(parents=True, exist_ok=True)
        with open(OUT_FILE, "w") as f:
            json.dump(out, f, indent=2)
        print(f"\n  Saved {len(out)} wrestlers to {OUT_FILE}")


if __name__ == "__main__":
    main()
