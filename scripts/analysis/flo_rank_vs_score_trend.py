#!/usr/bin/env python3
"""
Pools FloWrestling rank-vs-NCAA-score comparisons across every scraped
touch-point file (data/{year}/flo-preseason-rankings/*.json) and every
tournament year, grouped by calendar-month touch point, to see whether the
predictive accuracy of the rankings (avg points, std dev) improves as the
season progresses toward the seed (set right before NCAAs).

Reuses the join/DNQ-as-0/name-matching logic from flo_preseason_vs_score.py.

Usage:
  python scripts/analysis/flo_rank_vs_score_trend.py
  python scripts/analysis/flo_rank_vs_score_trend.py --top 20
"""

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

from flo_preseason_vs_score import (
    load_tourney_results,
    lookup_result,
    summarize_by_seed,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
COMBINED_DIR = DATA_DIR / "ncaa-tourney-parsed"

MONTH_ORDER = ["Sep", "Oct", "Nov", "Dec", "Jan", "Feb"]
MONTH_LABEL = {9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec", 1: "Jan", 2: "Feb"}

# The scraper always walks target months in this fixed order per season (see
# scripts/scraping/scrape_flo_preseason_rankings.py TARGET_MONTHS / --target-months),
# and dates within a season are monotonically increasing, one file per target month.
# 5 files -> Oct-Feb; 6 files -> Sep-Feb (2025-26 also has a Sep preseason touch point).
TARGET_MONTH_SEQUENCES = {
    5: [10, 11, 12, 1, 2],
    6: [9, 10, 11, 12, 1, 2],
}


def find_touchpoint_files():
    """Yield (tourney_year, month_label, path, data) for every scraped touch-point file.

    Bucketed by which TARGET month the file was collected for, not the literal
    calendar month of its filename/ranking_date -- a target date can land in an
    adjacent month if that's genuinely the closest snapshot available (e.g. a
    "February" touch point whose closest real snapshot was Jan 30). It still
    represents the Feb collection point and should count as Feb.
    """
    by_season: dict[int, list[Path]] = defaultdict(list)
    for path in sorted(DATA_DIR.glob("*/flo-preseason-rankings/*.json")):
        data = json.loads(path.read_text())
        by_season[data["season"]].append(path)

    years_with_results = {w["year"] for w in json.loads((COMBINED_DIR / "all_wrestlers.json").read_text())}

    for tourney_year, paths in by_season.items():
        paths = sorted(paths, key=lambda p: p.stem)  # filenames are YYYY-MM-DD, sorts chronologically
        seq = TARGET_MONTH_SEQUENCES.get(len(paths))
        if seq is None:
            if tourney_year not in years_with_results:
                # Current/in-progress season with no NCAA results yet (tournament
                # hasn't happened) -- not trainable data, skip rather than error.
                continue
            raise RuntimeError(
                f"Season {tourney_year} has {len(paths)} touch-point files -- no known "
                f"target-month sequence for that count, update TARGET_MONTH_SEQUENCES"
            )
        for path, target_month in zip(paths, seq):
            data = json.loads(path.read_text())
            yield tourney_year, MONTH_LABEL[target_month], path, data


def main():
    parser = argparse.ArgumentParser(description="Pooled rank-vs-score trend across seasons")
    parser.add_argument("--top", type=int, default=33, help="Max rank/seed to include (33 = full bracket)")
    args = parser.parse_args()

    # rank-level rows: month -> rank -> list of points
    by_month_rank = defaultdict(lambda: defaultdict(list))
    # month-level pooled points (all ranks 1-top together)
    by_month = defaultdict(list)
    seed_avg_by_year = {}
    all_seed_points = []  # pooled seeds 1-top_n points across every year, for the Seeds row
    by_seed = defaultdict(list)  # seed -> pooled points across every year, for the per-seed column

    years_seen = set()
    file_count = 0
    results_cache = {}

    for tourney_year, month, path, data in find_touchpoint_files():
        years_seen.add(tourney_year)
        file_count += 1
        if tourney_year not in results_cache:
            results_cache[tourney_year] = load_tourney_results(tourney_year)
        by_weight_name, by_weight_lastname = results_cache[tourney_year]

        if tourney_year not in seed_avg_by_year:
            seed_summary = summarize_by_seed(by_weight_name, args.top)
            pts = [s["avg_points"] for s in seed_summary if s["avg_points"] is not None]
            seed_avg_by_year[tourney_year] = round(statistics.mean(pts), 2) if pts else None
            all_seed_points.extend(
                rec["total_points"] for rec in by_weight_name.values()
                if 1 <= rec["seed"] <= args.top
            )
            for rec in by_weight_name.values():
                if 1 <= rec["seed"] <= args.top:
                    by_seed[rec["seed"]].append(rec["total_points"])

        for weight_str, entries in data["weights"].items():
            weight = int(weight_str)
            for e in entries:
                if e["rank"] > args.top:
                    continue
                rec = lookup_result(weight, e["name"], by_weight_name, by_weight_lastname)
                points = rec["total_points"] if rec is not None else 0.0
                by_month[month].append(points)
                by_month_rank[month][e["rank"]].append(points)

    print("=" * 90)
    print(f"Pooled preseason/in-season rank vs. NCAA score trend "
          f"({sorted(years_seen)} tournament years, {file_count} touch-point files, DNQ=0 pts)")
    print("=" * 90)
    print(f"{'Month':>6}  {'n':>4}  {'Avg Pts':>8}  {'Std Dev':>8}  {'Seed Avg (ref)':>15}  {'Diff vs Seed':>13}")
    print("-" * 90)

    seed_ref = round(statistics.mean(seed_avg_by_year.values()), 2) if seed_avg_by_year else None

    month_summary = []
    for month in MONTH_ORDER:
        pts = by_month.get(month)
        if not pts:
            continue
        n = len(pts)
        avg = round(statistics.mean(pts), 2)
        std = round(statistics.stdev(pts), 2) if n > 1 else 0.0
        diff = round(avg - seed_ref, 2) if seed_ref is not None else None
        print(f"{month:>6}  {n:>4}  {avg:>8}  {std:>8}  {str(seed_ref):>15}  {str(diff):>13}")
        month_summary.append({"month": month, "n": n, "avg_points": avg, "std_points": std})

    print("-" * 90)
    seed_row = None
    if all_seed_points:
        n = len(all_seed_points)
        avg = round(statistics.mean(all_seed_points), 2)
        std = round(statistics.stdev(all_seed_points), 2) if n > 1 else 0.0
        print(f"{'Seeds':>6}  {n:>4}  {avg:>8}  {std:>8}  {'--':>15}  {'--':>13}")
        seed_row = {"month": "Seeds", "n": n, "avg_points": avg, "std_points": std}
        month_summary.append(seed_row)

    print(f"\nSeed baseline (avg points, seeds 1-{args.top}), by year: "
          + ", ".join(f"{y}={v}" for y, v in sorted(seed_avg_by_year.items())))
    print(f"Seed baseline averaged across years: {seed_ref}")

    def summarize_points(pts: list[float]) -> dict:
        n = len(pts)
        avg = round(statistics.mean(pts), 2) if pts else None
        std = round(statistics.stdev(pts), 2) if n > 1 else 0.0
        # Coefficient of variation (std/mean): raw std dev mechanically scales with
        # the mean for bounded, zero-inflated scoring data like this, so comparing
        # raw std across ranks/months with very different average points (e.g. rank 1
        # at ~15 pts vs rank 20 at ~2 pts) isn't apples-to-apples. CoV normalizes for
        # that, showing RELATIVE uncertainty instead of absolute spread.
        cv = round(std / avg, 2) if avg else None
        return {"n": n, "avg_points": avg, "std_points": std, "cv": cv}

    # Rank-level breakdown for future chart use
    rank_breakdown = {}
    for month, rank_map in by_month_rank.items():
        rank_breakdown[month] = {}
        for rank, pts in rank_map.items():
            rank_breakdown[month][rank] = summarize_points(pts)

    seed_breakdown = {}
    for seed, pts in by_seed.items():
        seed_breakdown[seed] = summarize_points(pts)

    # Full per-rank (1..top) x month table, with a Seed column for reference.
    # This is the real test of "does confidence improve over the season": unlike
    # the pooled month table above (dominated by between-rank spread, since rank 1
    # scores ~15-20 pts and rank 33 scores ~0), holding rank constant isolates
    # within-rank variance so month-to-month narrowing (or lack of it) is visible.
    def print_full_table(stat_key: str, title: str):
        header_cols = "".join(f"{m:>8}" for m in MONTH_ORDER) + f"{'Seed':>8}"
        print(f"\n{title}")
        print(f"{'Rank':>5}{header_cols}")
        print("-" * (5 + 8 * (len(MONTH_ORDER) + 1)))
        for rank in range(1, args.top + 1):
            row = f"{rank:>5}"
            for month in MONTH_ORDER:
                v = rank_breakdown.get(month, {}).get(rank, {}).get(stat_key)
                row += f"{v if v is not None else '--':>8}"
            sv = seed_breakdown.get(rank, {}).get(stat_key)
            row += f"{sv if sv is not None else '--':>8}"
            print(row)

    print_full_table("std_points", "Std Dev by rank x month (full bracket, 1-33), Seed column = std dev for that seed position pooled across years")
    print_full_table("avg_points", "Avg Points by rank x month (full bracket, 1-33), Seed column = avg for that seed position pooled across years")
    print_full_table("cv", "Coefficient of Variation (std/mean) by rank x month -- normalized relative uncertainty, fairer than raw std dev across ranks/months with different average points")

    out_path = COMBINED_DIR / "flo_rank_vs_score_all_seasons.json"
    out_path.write_text(json.dumps({
        "years_included": sorted(years_seen),
        "top_n": args.top,
        "month_summary": month_summary,
        "seed_baseline_by_year": seed_avg_by_year,
        "seed_baseline_avg": seed_ref,
        "rank_breakdown_by_month": rank_breakdown,
        "seed_breakdown": seed_breakdown,
    }, indent=2))
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
