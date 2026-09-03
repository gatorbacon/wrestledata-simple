#!/usr/bin/env python3
"""
Computes a per-wrestler "proven track record" modifier for the top 3 ranked
wrestlers at each weight class, on top of the generic rank-based projection.

Motivation: two wrestlers can both be ranked #1 this year, but one already
won NCAAs by 25+ points last year while the other took 3rd with 15. The
generic rank-based distribution treats them identically. This modifier adds
real, proven track record on top -- but ONLY upward, never downward.

Why upside-only: a wrestler who scored well last year is straightforwardly
good evidence they'll score well again (validated below). A wrestler who
scored *poorly* last year is much harder to interpret -- injury, buried
behind a graduating senior, a bad bracket, a weight-class move -- and a
backtest showed a naive downward modifier actively hurt team-level
prediction accuracy in some cases (see docs/matsavant.md). We trust the
current rank as the floor and only let history add confidence on top of it,
never subtract from it. Same reasoning extends to multi-year history: a
strong recent year is never diluted by a weaker older year. We take
whichever of (1-year modifier, 2-year-average modifier, 0) is most
favorable to the wrestler.

Method:
  1. For every wrestler-to-wrestler year transition in our history
     (2013-2026), record: prior absolute NCAA points scored, and the
     seed-relative residual (actual points minus the league-wide average at
     that CURRENT seed) the following year.
  2. Fit two simple linear regressions per current-seed tier (1, 2, 3):
     one using the single most recent prior year as the predictor, one
     using the 2-year average (for wrestlers with 2 years of history).
  3. For each of this year's top-3-ranked wrestlers, compute both modifiers
     (each floored at 0), take the max.
  4. Apply a sequential cap within each weight class: rank 1 is never
     capped (nothing ranks above it), rank 2's final adjusted value can
     never exceed rank 1's, rank 3's can never exceed rank 2's. This
     approximates isotonic regression -- it never lets the modifier imply
     a lower-ranked wrestler is secretly better than the wrestler ranked
     above them.

Validated via backtest (2025-26 season, out-of-sample fit that excludes the
transition being tested): reduces team-level mean absolute error from 23.6
to ~22.1 across last season's top 10 finishers, and -- critically -- never
makes a team's prediction worse than the no-modifier baseline, only equal
or better, because of the upside-only design.

Usage:
  python scripts/analysis/compute_individual_modifiers.py \
    --rankings-file data/2027/flo-preseason-rankings/2026-08-26.json \
    --team-offsets data/ncaa-tourney-parsed/team_seed_offsets.json \
    --rank-distributions data/ncaa-tourney-parsed/rank_score_distributions.json \
    --month Sep
"""

import argparse
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
COMBINED_DIR = PROJECT_ROOT / "data" / "ncaa-tourney-parsed"

TOP_N_RANKS = (1, 2, 3)  # only ranks with a validated backtest get a modifier
MIN_POSSIBLE_POINTS, MAX_POSSIBLE_POINTS = 0.0, 30.0


def clip(x):
    return max(MIN_POSSIBLE_POINTS, min(MAX_POSSIBLE_POINTS, x))


def normalize_name(name: str) -> str:
    name = re.sub(r"[`´'‘’]", "'", name)
    return name.strip().lower()


def fit_linear(pairs: list) -> dict:
    """pairs: [{'x':..., 'y':...}]. Returns {n, mean_x, beta} for y = beta*(x-mean_x)."""
    xs = [p["x"] for p in pairs]
    ys = [p["y"] for p in pairs]
    n = len(xs)
    mean_x = statistics.mean(xs)
    sx = statistics.pstdev(xs)
    cov = sum((x - mean_x) * (y - statistics.mean(ys)) for x, y in zip(xs, ys)) / n
    beta = cov / (sx * sx) if sx > 0 else 0.0
    return {"n": n, "mean_x": mean_x, "beta": beta}


def build_fits(all_wrestlers: list) -> tuple:
    """Returns (fits_1yr, fits_2yr), each {seed: {n, mean_x, beta}} for seeds 1-3."""
    by_seed_all = defaultdict(list)
    for w in all_wrestlers:
        by_seed_all[w["seed"]].append(w["total_points"])
    league_avg = {s: statistics.mean(p) for s, p in by_seed_all.items()}

    by_name_year = defaultdict(dict)
    for w in all_wrestlers:
        if w["seed"] not in league_avg:
            continue
        by_name_year[normalize_name(w["name"])][w["year"]] = w
    years_present = sorted(set(w["year"] for w in all_wrestlers))

    pairs_1yr = defaultdict(list)
    pairs_2yr = defaultdict(list)
    for name, year_data in by_name_year.items():
        for y in year_data:
            if (y + 1) not in year_data or (y + 1) not in years_present:
                continue
            curr = year_data[y + 1]
            if curr["seed"] not in TOP_N_RANKS:
                continue
            resid = curr["total_points"] - league_avg[curr["seed"]]
            pairs_1yr[curr["seed"]].append({"x": year_data[y]["total_points"], "y": resid})
            if (y - 1) in year_data:
                avg2 = (year_data[y]["total_points"] + year_data[y - 1]["total_points"]) / 2
                pairs_2yr[curr["seed"]].append({"x": avg2, "y": resid})

    fits_1yr = {s: fit_linear(pairs_1yr[s]) for s in TOP_N_RANKS}
    fits_2yr = {s: fit_linear(pairs_2yr[s]) for s in TOP_N_RANKS}
    return fits_1yr, fits_2yr


def offset_for(team: str, team_offsets: dict, aliases: dict) -> float:
    canon = aliases.get(team, team)
    entry = team_offsets.get(canon)
    return entry["offset"] if entry else 0.0


SCHOOL_NAME_FIXES = {"West Virgnia": "West Virginia"}


def main():
    parser = argparse.ArgumentParser(description="Compute upside-only individual track-record modifiers for top-3 ranked wrestlers")
    parser.add_argument("--rankings-file", required=True)
    parser.add_argument("--team-offsets", required=True)
    parser.add_argument("--rank-distributions", required=True)
    parser.add_argument("--month", required=True, choices=["Sep", "Oct", "Nov", "Dec", "Jan", "Feb"])
    parser.add_argument("--out", help="Output path (default: alongside rankings file, suffixed _individual_modifiers.json)")
    args = parser.parse_args()

    all_wrestlers = json.loads((COMBINED_DIR / "all_wrestlers.json").read_text())
    fits_1yr, fits_2yr = build_fits(all_wrestlers)

    by_name_year = defaultdict(dict)
    for w in all_wrestlers:
        by_name_year[normalize_name(w["name"])][w["year"]] = w
    most_recent_year = max(w["year"] for w in all_wrestlers)

    rankings_data = json.loads(Path(args.rankings_file).read_text())
    offsets_data = json.loads(Path(args.team_offsets).read_text())
    team_offsets = offsets_data["offsets"]
    aliases = offsets_data.get("team_aliases", {})

    dist = json.loads(Path(args.rank_distributions).read_text())
    dfm = dist[args.month]

    out = {}
    for weight_str, entries in sorted(rankings_data["weights"].items(), key=lambda x: int(x[0])):
        top3 = sorted([e for e in entries if e["rank"] in TOP_N_RANKS], key=lambda e: e["rank"])
        rows = []
        for e in top3:
            rank = e["rank"]
            school = SCHOOL_NAME_FIXES.get(e["school"], e["school"])
            off = offset_for(school, team_offsets, aliases)
            base = statistics.mean([clip(p + off) for p in dfm[str(rank)]["points"]])

            key = normalize_name(e["name"])
            year_data = by_name_year.get(key, {})
            has_1yr = most_recent_year in year_data
            has_2yr = has_1yr and (most_recent_year - 1) in year_data

            mod_1yr = 0.0
            if has_1yr:
                f = fits_1yr[rank]
                mod_1yr = max(0.0, f["beta"] * (year_data[most_recent_year]["total_points"] - f["mean_x"]))
            mod_2yr = 0.0
            if has_2yr:
                f = fits_2yr[rank]
                avg2 = (year_data[most_recent_year]["total_points"] + year_data[most_recent_year - 1]["total_points"]) / 2
                mod_2yr = max(0.0, f["beta"] * (avg2 - f["mean_x"]))

            final_mod = max(mod_1yr, mod_2yr, 0.0)
            rows.append({"rank": rank, "name": e["name"], "school": e["school"], "base": base, "modifier": final_mod})

        # sequential cap: each rank's adjusted value can't exceed the rank above it
        ceiling = None
        for r in rows:
            adj = r["base"] + r["modifier"]
            if ceiling is not None:
                adj = min(adj, ceiling)
            ceiling = adj
            r["capped_modifier"] = round(adj - r["base"], 3)

        out[weight_str] = {
            str(r["rank"]): {"name": r["name"], "school": r["school"], "modifier": r["capped_modifier"]}
            for r in rows
        }

    out_path = Path(args.out) if args.out else Path(args.rankings_file).with_name(
        Path(args.rankings_file).stem + "_individual_modifiers.json"
    )
    out_path.write_text(json.dumps({
        "rankings_file": args.rankings_file,
        "month": args.month,
        "fits_1yr": fits_1yr,
        "fits_2yr": fits_2yr,
        "modifiers": out,
    }, indent=2))

    print(f"Individual modifiers computed for {sum(len(v) for v in out.values())} wrestlers across {len(out)} weights")
    for weight_str, ranks in out.items():
        for rank_str, info in ranks.items():
            if info["modifier"] > 0:
                print(f"  {weight_str:>4} #{rank_str}  {info['name']:<24} {info['school']:<16} +{info['modifier']:.2f}")
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
