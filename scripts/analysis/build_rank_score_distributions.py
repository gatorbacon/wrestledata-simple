#!/usr/bin/env python3
"""
Builds the empirical per-(rank, month) point-score distributions used to drive
a Monte Carlo team-score simulation later.

For each FloWrestling rank (1-33) and each touch-point month (Sep-Feb), this
pools that rank's own historical NCAA total_points across all 4 tournament
years (2023-2026) as the base sample, then blends in the immediate neighbor
ranks' (rank-1, rank+1) points for that same month, RECENTERED to the target
rank's own mean first:

    adjusted_neighbor_points = neighbor_points - mean(neighbor_points) + own_mean

This borrows the neighbor's spread/shape (more data -> a more stable variance
estimate) without importing their different central tendency into the target
rank's mean. Validated via leave-one-year-out testing (see conversation/commit
history): MAE-of-mean is unaffected by construction, and fold-to-fold std-dev
stability improves for 27 of 33 ranks vs. no blending at all, including rank 1
(which specifically got WORSE with naive un-centered pooling -- centering fixes
that by design).

Output: data/ncaa-tourney-parsed/rank_score_distributions.json
  { month: { rank: { n_own, n_blended, mean, std, min, max, p10, p25, p50, p75,
                      p90, points: [full blended points list, for sampling] } } }

Usage:
  python scripts/analysis/build_rank_score_distributions.py
"""

import json
import statistics
from collections import defaultdict
from pathlib import Path

from flo_rank_vs_score_trend import find_touchpoint_files, MONTH_ORDER
from flo_preseason_vs_score import load_tourney_results, lookup_result

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
COMBINED_DIR = PROJECT_ROOT / "data" / "ncaa-tourney-parsed"

MAX_RANK = 33
MIN_POSSIBLE_POINTS = 0.0
MAX_POSSIBLE_POINTS = 30.0  # theoretical ceiling: 4.0 advancement + 10.0 bonus (5 falls) + 16.0 for 1st


def percentile(sorted_vals, p):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p
    f, c = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


SKIP_MONTHS = {"Sep"}  # thin sample (n_own=10 vs 40+ for other months) -- pure noise, see note in main()


def build_points_by_rank_month():
    """points_by_rank_month[month][rank] = list of NCAA total_points, pooled
    across all years/weights for that (rank, month) touch point."""
    points_by_rank_month = defaultdict(lambda: defaultdict(list))
    results_cache = {}

    for tourney_year, month, path, data in find_touchpoint_files():
        if month in SKIP_MONTHS:
            continue
        if tourney_year not in results_cache:
            results_cache[tourney_year] = load_tourney_results(tourney_year)
        by_weight_name, by_weight_lastname = results_cache[tourney_year]

        for weight_str, entries in data["weights"].items():
            weight = int(weight_str)
            for e in entries:
                if e["rank"] > MAX_RANK:
                    continue
                rec = lookup_result(weight, e["name"], by_weight_name, by_weight_lastname)
                points = rec["total_points"] if rec is not None else 0.0
                points_by_rank_month[month][e["rank"]].append(points)

    return points_by_rank_month


def clip(x):
    return max(MIN_POSSIBLE_POINTS, min(MAX_POSSIBLE_POINTS, x))


def recentered_blend(own_points, neighbor_points_list):
    """own_points + each neighbor's points shifted to own_points' mean.

    Clipped to [0, 30] -- real NCAA scores can't go negative or exceed the
    theoretical max, but a flat mean-shift on real data near those bounds can
    otherwise produce impossible values (e.g. shifting a neighbor's near-zero
    points up/down by a few points pushes some below 0)."""
    if own_points:
        own_mean = statistics.mean(own_points)
        blended = list(own_points)
        for nb in neighbor_points_list:
            if not nb:
                continue
            nb_mean = statistics.mean(nb)
            blended.extend(clip(p - nb_mean + own_mean) for p in nb)
        return blended
    # No own data at all for this cell -- fall back to raw neighbor pooling
    # (nothing to preserve/center around, so use whatever's available as-is).
    blended = []
    for nb in neighbor_points_list:
        blended.extend(nb)
    return blended


def summarize(points):
    if not points:
        return None
    n = len(points)
    sorted_pts = sorted(points)
    return {
        "n": n,
        "mean": round(statistics.mean(points), 2),
        "std": round(statistics.stdev(points), 2) if n > 1 else 0.0,
        "min": round(min(points), 2),
        "max": round(max(points), 2),
        "p10": round(percentile(sorted_pts, 0.10), 2),
        "p25": round(percentile(sorted_pts, 0.25), 2),
        "p50": round(percentile(sorted_pts, 0.50), 2),
        "p75": round(percentile(sorted_pts, 0.75), 2),
        "p90": round(percentile(sorted_pts, 0.90), 2),
        "points": [round(p, 2) for p in points],
    }


def main():
    points_by_rank_month = build_points_by_rank_month()

    out = {}
    for month in MONTH_ORDER:
        rank_map = points_by_rank_month.get(month, {})
        if not rank_map:
            continue
        out[month] = {}
        for rank in range(1, MAX_RANK + 1):
            own = rank_map.get(rank, [])
            neighbors = [rank_map.get(r, []) for r in (rank - 1, rank + 1) if 1 <= r <= MAX_RANK]
            blended = recentered_blend(own, neighbors)
            summary = summarize(blended)
            if summary is None:
                continue
            summary["n_own"] = len(own)
            out[month][rank] = summary

    # September only has ~1 year of scraped touch-point data (n_own=10 vs.
    # 40+ every other month) -- too thin to trust on its own, so alias it to
    # October's fuller distribution instead of pooling it independently.
    if "Sep" in MONTH_ORDER and "Oct" in out:
        out["Sep"] = out["Oct"]

    out_path = COMBINED_DIR / "rank_score_distributions.json"
    out_path.write_text(json.dumps(out, indent=2))

    print("=" * 80)
    print("Rank score distributions built (recentered ±1 blend)")
    print("=" * 80)
    print(f"{'Month':>6} {'Rank':>5} {'n_own':>6} {'n_blend':>8} {'Mean':>7} {'Std':>7} {'P10':>6} {'P90':>6}")
    for month in MONTH_ORDER:
        if month not in out:
            continue
        for rank in sorted(out[month].keys()):
            s = out[month][rank]
            print(f"{month:>6} {rank:>5} {s['n_own']:>6} {s['n']:>8} {s['mean']:>7} {s['std']:>7} {s['p10']:>6} {s['p90']:>6}")

    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
