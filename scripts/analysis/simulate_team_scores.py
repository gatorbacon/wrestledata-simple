#!/usr/bin/env python3
"""
Monte Carlo team-score simulation for NCAA D1 wrestling, driven by FloWrestling
rankings + the empirical per-(rank, month) score distributions built by
build_rank_score_distributions.py.

For a given scraped rankings file (one season, one date/touch-point month):
  1. Build each team's lineup: for each of the 10 weight classes, their
     best-ranked (lowest rank number) wrestler, if any is ranked in the
     scraped top-N.
  2. For weight slots with no ranked wrestler, use a fallback distribution
     (pooled ranks 25-33, i.e. the deepest tier we have data for) as a rough
     stand-in for "not nationally ranked." This is a known simplification --
     see the open task on stratifying unranked wrestlers by program strength
     (e.g. a Penn State backup replacing an injured starter likely outscores
     this generic fallback) -- not yet implemented.
  3. Run N Monte Carlo trials: each trial draws one random sample per weight
     slot from that (month, rank) empirical distribution, sums to a team
     total, then ranks all teams that trial to record each team's placement.
  4. Aggregate across trials: min/max/expected (mean) team score, plus
     cumulative placement odds (P(1st), P(top 3), P(top 5), P(top 10)).

Optionally applies two adjustments on top of the generic rank-based points:
  - --team-offsets: a per-program seed-relative strength adjustment (see
    compute_team_seed_offsets.py), applied to every wrestler on that roster.
  - --individual-modifiers: an upside-only per-wrestler track-record
    adjustment for top-3-ranked wrestlers (see compute_individual_modifiers.py),
    applied only to that specific wrestler's slot.

Usage:
  python scripts/analysis/simulate_team_scores.py --rankings-file data/2027/flo-preseason-rankings/2026-08-26.json --month Sep
  python scripts/analysis/simulate_team_scores.py --rankings-file <path> --month Sep --trials 10000
  python scripts/analysis/simulate_team_scores.py --rankings-file <path> --month Sep \
    --team-offsets data/ncaa-tourney-parsed/team_seed_offsets.json \
    --individual-modifiers data/2027/flo-preseason-rankings/2026-08-26_individual_modifiers.json \
    --out-suffix _adjusted
"""

import argparse
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
COMBINED_DIR = DATA_DIR / "ncaa-tourney-parsed"

WEIGHTS = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]
FALLBACK_RANK_RANGE = range(25, 34)  # deepest tier we have data for -- stand-in for "unranked"
MIN_POSSIBLE_POINTS, MAX_POSSIBLE_POINTS = 0.0, 30.0


def clip(x):
    return max(MIN_POSSIBLE_POINTS, min(MAX_POSSIBLE_POINTS, x))


def percentile(sorted_vals, p):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p
    f, c = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


# Known scrape-side data-entry typos that would otherwise fragment one real
# program's lineup into two synthetic "teams" (e.g. one wrestler tagged
# "West Virgnia" while the rest of the roster says "West Virginia").
SCHOOL_NAME_FIXES = {
    "West Virgnia": "West Virginia",
}


def build_team_lineups(rankings_data: dict) -> dict:
    """team -> {weight: {"rank": int, "name": str}}, best (lowest) rank per weight per team."""
    teams = defaultdict(dict)
    for weight_str, entries in rankings_data["weights"].items():
        weight = int(weight_str)
        for e in entries:
            school = SCHOOL_NAME_FIXES.get(e["school"], e["school"])
            existing = teams[school].get(weight)
            if existing is None or e["rank"] < existing["rank"]:
                teams[school][weight] = {"rank": e["rank"], "name": e["name"]}
    return teams


def build_fallback_points(dist_for_month: dict) -> list:
    pooled = []
    for rank in FALLBACK_RANK_RANGE:
        entry = dist_for_month.get(str(rank))
        if entry:
            pooled.extend(entry["points"])
    return pooled


def main():
    parser = argparse.ArgumentParser(description="Monte Carlo NCAA team score simulation")
    parser.add_argument("--rankings-file", required=True, help="Scraped FloWrestling rankings JSON to simulate from")
    parser.add_argument("--month", required=True, choices=["Sep", "Oct", "Nov", "Dec", "Jan", "Feb"],
                         help="Which built rank->score-distribution month bucket to use")
    parser.add_argument("--trials", type=int, default=10000)
    parser.add_argument("--top-n-display", type=int, default=30, help="How many teams to print (sorted by expected score)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--team-offsets", help="Path to team_seed_offsets.json to apply program-strength adjustment")
    parser.add_argument("--individual-modifiers", help="Path to a compute_individual_modifiers.py output file, applies upside-only per-wrestler track-record modifiers to top-3-ranked wrestlers")
    parser.add_argument("--out-suffix", default="", help="Suffix for output filename, e.g. '_adjusted'")
    args = parser.parse_args()

    random.seed(args.seed)

    rankings_data = json.loads(Path(args.rankings_file).read_text())
    teams = build_team_lineups(rankings_data)

    dist_path = COMBINED_DIR / "rank_score_distributions.json"
    all_dist = json.loads(dist_path.read_text())
    if args.month not in all_dist:
        raise SystemExit(f"No built distribution for month '{args.month}' -- run build_rank_score_distributions.py first")
    dist_for_month = all_dist[args.month]

    fallback_points = build_fallback_points(dist_for_month)
    if not fallback_points:
        raise SystemExit("No fallback distribution available (ranks 25-33) -- cannot simulate unranked slots")

    team_offsets = {}
    aliases = {}
    if args.team_offsets:
        offsets_data = json.loads(Path(args.team_offsets).read_text())
        team_offsets = offsets_data["offsets"]
        aliases = offsets_data.get("team_aliases", {})

    def offset_for(team: str) -> float:
        canon = aliases.get(team, team)
        entry = team_offsets.get(canon)
        return entry["offset"] if entry else 0.0

    # Per-wrestler upside-only track-record modifiers for top-3-ranked wrestlers
    # (see compute_individual_modifiers.py) -- keyed by weight -> rank -> {name, modifier}.
    individual_modifiers = {}
    if args.individual_modifiers:
        individual_modifiers = json.loads(Path(args.individual_modifiers).read_text())["modifiers"]

    def modifier_for(weight: int, rank: int, name: str) -> float:
        entry = individual_modifiers.get(str(weight), {}).get(str(rank))
        if entry and entry["name"] == name:
            return entry["modifier"]
        return 0.0

    # Pre-fetch each team's per-weight points list (rank dist, or fallback),
    # shifted by the team's program-strength offset when provided (applied
    # per-slot so it compounds naturally across the 10-man lineup, clipped to
    # the real [0,30] score bounds same as the blended rank distributions).
    # Also record per-wrestler detail (name/rank/own expected range) for the
    # team-detail drilldown -- these numbers already include the team offset
    # since they're computed from the exact same (possibly shifted) points list.
    team_weight_points = {}
    team_lineup_detail = {}
    for team, lineup in teams.items():
        off = offset_for(team)
        slots = []
        detail = []
        for weight in WEIGHTS:
            entry = lineup.get(weight)
            rank = entry["rank"] if entry else None
            name = entry["name"] if entry else None
            base = dist_for_month[str(rank)]["points"] if (rank is not None and str(rank) in dist_for_month) else fallback_points
            indiv_mod = modifier_for(weight, rank, name) if rank is not None else 0.0
            shift = off + indiv_mod
            pts = [clip(p + shift) for p in base] if shift else base
            slots.append(pts)
            pts_sorted = sorted(pts)
            detail.append({
                "weight": weight,
                "rank": rank,
                "name": name,
                "individual_modifier": round(indiv_mod, 2) if indiv_mod else 0.0,
                "expected": round(statistics.mean(pts), 1),
                "p5": round(percentile(pts_sorted, 0.05), 1),
                "p95": round(percentile(pts_sorted, 0.95), 1),
            })
        team_weight_points[team] = slots
        team_lineup_detail[team] = detail

    team_names = list(team_weight_points.keys())
    totals = {t: [] for t in team_names}
    placement_counts = {t: defaultdict(int) for t in team_names}

    for _ in range(args.trials):
        trial_totals = {}
        for team in team_names:
            trial_totals[team] = sum(random.choice(pts) for pts in team_weight_points[team])
        ranked = sorted(trial_totals.items(), key=lambda x: -x[1])
        for placement, (team, total) in enumerate(ranked, start=1):
            totals[team].append(total)
            placement_counts[team][placement] += 1

    summary = []
    for team in team_names:
        t = totals[team]
        pc = placement_counts[team]
        n = args.trials
        p1 = pc[1] / n
        p_top3 = sum(pc[p] for p in range(1, 4)) / n
        p_top5 = sum(pc[p] for p in range(1, 6)) / n
        p_top10 = sum(pc[p] for p in range(1, 11)) / n
        exact_placements = {str(p): round(100 * pc[p] / n, 1) for p in range(1, 11)}
        t_sorted = sorted(t)
        summary.append({
            "team": team,
            "lineup_size": len([w for w in WEIGHTS if w in teams[team]]),
            "program_offset": offset_for(team),
            "lineup_detail": team_lineup_detail[team],
            "min": round(min(t), 1),
            "max": round(max(t), 1),
            "p5": round(percentile(t_sorted, 0.05), 1),
            "p95": round(percentile(t_sorted, 0.95), 1),
            "expected": round(statistics.mean(t), 1),
            "p_1st": round(p1 * 100, 1),
            "p_top3": round(p_top3 * 100, 1),
            "p_top5": round(p_top5 * 100, 1),
            "p_top10": round(p_top10 * 100, 1),
            "p_place": exact_placements,
        })

    summary.sort(key=lambda s: -s["expected"])

    print("=" * 110)
    print(f"NCAA D1 Team Score Simulation -- {args.rankings_file} ({args.month} touch point, {args.trials} trials)")
    print("=" * 110)
    print(f"{'Team':<20}{'Ranked':>7}{'Min':>7}{'Max':>7}{'Expected':>10}{'P(1st)':>9}{'P(Top3)':>9}{'P(Top5)':>9}{'P(Top10)':>10}")
    print("-" * 110)
    for s in summary[:args.top_n_display]:
        print(f"{s['team']:<20}{s['lineup_size']:>7}{s['min']:>7.1f}{s['max']:>7.1f}{s['expected']:>10.1f}"
              f"{s['p_1st']:>8.1f}%{s['p_top3']:>8.1f}%{s['p_top5']:>8.1f}%{s['p_top10']:>9.1f}%")

    # Date-stamped filename (not a fixed name) so results from multiple ranking
    # snapshots over a season can coexist -- the results page discovers all of
    # them and offers a date dropdown, defaulting to the newest.
    ranking_date = rankings_data["ranking_date"]
    out_path = COMBINED_DIR / f"team_score_simulation{args.out_suffix}_{ranking_date}.json"
    out_path.write_text(json.dumps({
        "rankings_file": args.rankings_file,
        "ranking_date": ranking_date,
        "month": args.month,
        "trials": args.trials,
        "teams": summary,
    }, indent=2))
    print(f"\nSaved full results ({len(summary)} teams) to {out_path}")


if __name__ == "__main__":
    main()
