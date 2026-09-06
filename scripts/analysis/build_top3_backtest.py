#!/usr/bin/env python3
"""
Backtest the live Team Championship Odds model against the real top-3
finishers of each completed NCAA D1 season: for every monthly FloWrestling
rankings snapshot that season, run the same rank-distribution + team-offset +
individual-modifier simulation used in production, then compare the
month-by-month projected score trajectory to what each team actually scored.

The individual-modifier regression (see compute_individual_modifiers.py) is
refit PER SEASON, excluding that season's own wrestler-to-wrestler
transitions from the fit -- otherwise a season's real outcome would leak into
its own backtest, making the model look better than it actually would have
performed in real time. This is the one place this script's logic
legitimately diverges from the live pipeline (run_team_xtp.py /
compute_individual_modifiers.py fit on ALL available history, which is
correct for a live projection but wrong for an honest backtest).

Seasons are discovered dynamically, not hardcoded: a season is included once
it has (a) at least one FloWrestling snapshot in
data/{season}/flo-preseason-rankings/, and (b) real final results parsed to
data/{season}/ncaa-tourney/parsed/wrestlers.json (i.e. that season's NCAAs
have happened and been scraped+parsed). So re-running this script after each
new season's tournament data lands is all that's needed to extend the
backtest -- no code changes required.

Output (consumed by frontend/wrestledata-ui/public/top3_backtest.html):
  frontend/wrestledata-ui/public/data/top3_backtest/{season}.json
  frontend/wrestledata-ui/public/data/top3_backtest/index.json

Usage:
  python scripts/analysis/build_top3_backtest.py
  python scripts/analysis/build_top3_backtest.py --season 2026
"""

import argparse
import json
import random
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
COMBINED_DIR = DATA_DIR / "ncaa-tourney-parsed"
OUT_DIR = PROJECT_ROOT / "frontend" / "wrestledata-ui" / "public" / "data" / "top3_backtest"

WEIGHTS = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]
FALLBACK_RANK_RANGE = range(25, 34)
MIN_P, MAX_P = 0.0, 30.0
TOP_N_RANKS = (1, 2, 3)
SCHOOL_FIXES = {"West Virgnia": "West Virginia"}

# Preseason-through-February snapshots are projection touchpoints; a
# same-season snapshot dated March+ (taken after that year's NCAAs) is
# redundant with the "NCAAs" real-seed touchpoint below and is excluded.
TOUCHPOINT_MONTHS = {9, 10, 11, 12, 1, 2}

MONTH_NAME = {9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec", 1: "Jan", 2: "Feb"}


def clip(x):
    return max(MIN_P, min(MAX_P, x))


def normalize_name(name):
    name = re.sub(r"[`´'‘’]", "'", name)
    return name.strip().lower()


def canonical_school(school, aliases):
    fixed = SCHOOL_FIXES.get(school, school)
    return aliases.get(fixed, fixed)


def offset_for(team, team_offsets, aliases):
    canon = aliases.get(team, team)
    entry = team_offsets.get(canon)
    return entry["offset"] if entry else 0.0


def fit_linear(pairs):
    xs = [p["x"] for p in pairs]
    ys = [p["y"] for p in pairs]
    n = len(xs)
    mean_x = statistics.mean(xs)
    sx = statistics.pstdev(xs)
    cov = sum((x - mean_x) * (y - statistics.mean(ys)) for x, y in zip(xs, ys)) / n
    beta = cov / (sx * sx) if sx > 0 else 0.0
    return {"n": n, "mean_x": mean_x, "beta": beta}


def build_oos_fits(all_wrestlers, exclude_year):
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
            ny = y + 1
            if ny not in year_data or ny not in years_present:
                continue
            if ny == exclude_year:
                continue
            curr = year_data[ny]
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


def compute_individual_modifiers(rankings_data, month, target_season, fits_1yr, fits_2yr,
                                  by_name_year, dist, team_offsets, aliases):
    prior_year = target_season - 1
    dfm = dist[month]
    out = {}
    for weight_str, entries in rankings_data["weights"].items():
        top3 = sorted([e for e in entries if e["rank"] in TOP_N_RANKS], key=lambda e: e["rank"])
        rows = []
        for e in top3:
            rank = e["rank"]
            school = canonical_school(e["school"], aliases)
            off = offset_for(school, team_offsets, aliases)
            base = statistics.mean([clip(p + off) for p in dfm[str(rank)]["points"]])
            key = normalize_name(e["name"])
            year_data = by_name_year.get(key, {})
            has_1yr = prior_year in year_data
            has_2yr = has_1yr and (prior_year - 1) in year_data
            mod_1yr = 0.0
            if has_1yr:
                f = fits_1yr[rank]
                mod_1yr = max(0.0, f["beta"] * (year_data[prior_year]["total_points"] - f["mean_x"]))
            mod_2yr = 0.0
            if has_2yr:
                f = fits_2yr[rank]
                avg2 = (year_data[prior_year]["total_points"] + year_data[prior_year - 1]["total_points"]) / 2
                mod_2yr = max(0.0, f["beta"] * (avg2 - f["mean_x"]))
            final_mod = max(mod_1yr, mod_2yr, 0.0)
            rows.append({"rank": rank, "name": e["name"], "school": e["school"], "base": base, "modifier": final_mod})
        ceiling = None
        for r in rows:
            adj = r["base"] + r["modifier"]
            if ceiling is not None:
                adj = min(adj, ceiling)
            ceiling = adj
            r["capped_modifier"] = round(adj - r["base"], 3)
        out[weight_str] = {str(r["rank"]): {"name": r["name"], "school": r["school"], "modifier": r["capped_modifier"]} for r in rows}
    return out


def modifier_for(individual_modifiers, weight, rank, name):
    entry = individual_modifiers.get(str(weight), {}).get(str(rank))
    if entry and entry["name"] == name:
        return entry["modifier"]
    return 0.0


def build_team_lineups(rankings_data, aliases):
    teams = defaultdict(dict)
    for weight_str, entries in rankings_data["weights"].items():
        weight = int(weight_str)
        for e in entries:
            school = canonical_school(e["school"], aliases)
            existing = teams[school].get(weight)
            if existing is None or e["rank"] < existing["rank"]:
                teams[school][weight] = {"rank": e["rank"], "name": e["name"]}
    return teams


def percentile(sorted_vals, p):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p
    f, c = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def build_fallback_points(dfm):
    pooled = []
    for rank in FALLBACK_RANK_RANGE:
        entry = dfm.get(str(rank))
        if entry:
            pooled.extend(entry["points"])
    return pooled


def simulate(rankings_data, month, individual_modifiers, dist, team_offsets, aliases, trials=10000, seed=42):
    rng = random.Random(seed)
    teams = build_team_lineups(rankings_data, aliases)
    dfm = dist[month]
    fallback_points = build_fallback_points(dfm)
    team_weight_points = {}
    for team, lineup in teams.items():
        off = offset_for(team, team_offsets, aliases)
        slots = []
        for weight in WEIGHTS:
            entry = lineup.get(weight)
            rank = entry["rank"] if entry else None
            name = entry["name"] if entry else None
            base = dfm[str(rank)]["points"] if (rank is not None and str(rank) in dfm) else fallback_points
            indiv_mod = modifier_for(individual_modifiers, weight, rank, name) if rank is not None else 0.0
            shift = off + indiv_mod
            pts = [clip(p + shift) for p in base] if shift else base
            slots.append(pts)
        team_weight_points[team] = slots
    team_names = list(team_weight_points.keys())
    totals = {t: [] for t in team_names}
    for _ in range(trials):
        for team in team_names:
            totals[team].append(sum(rng.choice(pts) for pts in team_weight_points[team]))
    result = {}
    for team in team_names:
        t = sorted(totals[team])
        result[team] = {
            "exp": round(statistics.mean(t), 1),
            "p5": round(percentile(t, 0.05), 1),
            "p95": round(percentile(t, 0.95), 1),
        }
    return result


def load_seeds_as_rankings(year):
    weights = {}
    for w in WEIGHTS:
        path = DATA_DIR / str(year) / "ncaa-tourney" / "seeds" / f"{w}.txt"
        if not path.exists():
            weights[str(w)] = []
            continue
        entries = []
        lines = path.read_text().splitlines()[1:]  # skip header
        for line in lines:
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            seed_str, name_raw, school = parts[0], parts[1], parts[2]
            seed_str = seed_str.rstrip(".").strip()
            if not seed_str.isdigit():
                continue
            if "," in name_raw:
                last, first = [x.strip() for x in name_raw.split(",", 1)]
                name = f"{first} {last}"
            else:
                name = name_raw.strip()
            entries.append({"rank": int(seed_str), "name": name, "school": school.strip()})
        weights[str(w)] = entries
    return {"weights": weights, "ranking_date": f"{year}-NCAAs", "season": year}


def discover_seasons():
    """
    A season is backtestable once it has FloWrestling snapshots AND its
    NCAAs have been scraped+parsed. Discovered from what's on disk, not
    hardcoded, so a newly-completed season needs no script changes.
    """
    seasons = []
    for d in sorted(DATA_DIR.iterdir()):
        if not d.is_dir() or not d.name.isdigit():
            continue
        year = int(d.name)
        snapshots_dir = d / "flo-preseason-rankings"
        wrestlers_path = d / "ncaa-tourney" / "parsed" / "wrestlers.json"
        if snapshots_dir.is_dir() and any(snapshots_dir.glob("*.json")) and wrestlers_path.exists():
            seasons.append(year)
    return seasons


def discover_snapshots(season):
    """
    Returns [(date_str, label), ...] sorted chronologically, for every
    snapshot file dated Sep-Feb (preseason through just before NCAAs).
    """
    snapshots_dir = DATA_DIR / str(season) / "flo-preseason-rankings"
    out = []
    for path in sorted(snapshots_dir.glob("*.json")):
        date_str = path.stem  # e.g. "2025-09-29"
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            continue
        _, month_str, day_str = date_str.split("-")
        month = int(month_str)
        if month not in TOUCHPOINT_MONTHS:
            continue
        label = f"{int(month_str)}/{int(day_str)}"
        out.append((date_str, label))
    return sorted(out, key=lambda t: t[0])


def build_season(season, all_wrestlers, dist, team_offsets, aliases, real_scores, debug=False):
    snapshots = discover_snapshots(season)
    if not snapshots:
        print(f"   [SKIP] season {season}: no Sep-Feb snapshots found")
        return None

    by_name_year = defaultdict(dict)
    for w in all_wrestlers:
        by_name_year[normalize_name(w["name"])][w["year"]] = w

    fits_1yr, fits_2yr = build_oos_fits(all_wrestlers, exclude_year=season)

    scores = real_scores.get(season)
    if not scores:
        print(f"   [SKIP] season {season}: no real final scores available")
        return None
    top3_real = sorted(scores.items(), key=lambda x: -x[1])[:3]
    top3_teams = [t for t, s in top3_real]

    touchpoints = []
    for date_str, label in snapshots:
        path = DATA_DIR / str(season) / "flo-preseason-rankings" / f"{date_str}.json"
        rankings_data = json.loads(path.read_text())
        month = MONTH_NAME[int(date_str.split("-")[1])]
        indiv_mods = compute_individual_modifiers(
            rankings_data, month, season, fits_1yr, fits_2yr, by_name_year, dist, team_offsets, aliases,
        )
        sim = simulate(rankings_data, month, indiv_mods, dist, team_offsets, aliases)
        touchpoints.append((label, sim))

    seeds_rankings = load_seeds_as_rankings(season)
    indiv_mods_tny = compute_individual_modifiers(
        seeds_rankings, "Feb", season, fits_1yr, fits_2yr, by_name_year, dist, team_offsets, aliases,
    )
    sim_tny = simulate(seeds_rankings, "Feb", indiv_mods_tny, dist, team_offsets, aliases)
    touchpoints.append(("NCAAs", sim_tny))

    season_out = {
        "season": season,
        "label": f"{season - 1}–{str(season)[2:]}",
        "top3_teams": [{"team": t, "real_score": round(s, 1)} for t, s in top3_real],
        "labels": [lbl for lbl, _ in touchpoints],
        "series": {
            team: [tp_data.get(team, {"exp": None, "p5": None, "p95": None}) for _, tp_data in touchpoints]
            for team in top3_teams
        },
    }
    if debug:
        print(f"   season {season}: top3 = {top3_teams}, touchpoints = {[l for l, _ in touchpoints]}")
    return season_out


def main():
    parser = argparse.ArgumentParser(description="Backtest the Team Championship Odds model against real season outcomes")
    parser.add_argument("--season", type=int, default=None, help="Single season to rebuild (default: all eligible seasons)")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    if not COMBINED_DIR.exists():
        print(f"[ERROR] {COMBINED_DIR} not found.")
        sys.exit(1)

    all_wrestlers = json.loads((COMBINED_DIR / "all_wrestlers.json").read_text())
    dist = json.loads((COMBINED_DIR / "rank_score_distributions.json").read_text())
    offsets_data = json.loads((COMBINED_DIR / "team_seed_offsets.json").read_text())
    team_offsets = offsets_data["offsets"]
    aliases = offsets_data.get("team_aliases", {})

    seasons = [args.season] if args.season else discover_seasons()
    print(f"Building top-3 backtest for seasons: {seasons}")

    real_scores = {}
    for y in seasons:
        wpath = DATA_DIR / str(y) / "ncaa-tourney" / "parsed" / "wrestlers.json"
        if not wpath.exists():
            continue
        wdata = json.loads(wpath.read_text())
        scores = defaultdict(float)
        for w in wdata:
            scores[w["team"]] += w.get("total_points", 0) or 0
        real_scores[y] = scores

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index = []
    for season in seasons:
        print(f"\nSeason {season}:")
        season_out = build_season(season, all_wrestlers, dist, team_offsets, aliases, real_scores, debug=args.debug)
        if season_out is None:
            continue
        out_path = OUT_DIR / f"{season}.json"
        out_path.write_text(json.dumps(season_out, indent=2))
        print(f"   [OK] saved {out_path}")
        index.append({"season": season, "label": season_out["label"]})

    # If rebuilding a single season, merge into the existing index rather
    # than clobbering it down to one entry.
    index_path = OUT_DIR / "index.json"
    if args.season and index_path.exists():
        existing = {e["season"]: e for e in json.loads(index_path.read_text()).get("seasons", [])}
        for e in index:
            existing[e["season"]] = e
        index = list(existing.values())

    index.sort(key=lambda e: e["season"])
    index_path.write_text(json.dumps({"seasons": index}, indent=2))
    print(f"\n[DONE] {len(index)} season(s) in index: {[e['season'] for e in index]}")


if __name__ == "__main__":
    main()
