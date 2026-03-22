#!/usr/bin/env python3
"""
Generate simulation_replay.json for archived NCAA tournament years.

Replays all matches through the bracket engine one at a time, snapshotting
team projections after each match. Output is written to:
  data/{year}/ncaa-tourney/simulation_replay.json

The format matches live_data.json so the same frontend code renders both.

Usage:
  python scripts/ncaa/generate_replay.py --year 2025
  python scripts/ncaa/generate_replay.py --year 2024
  python scripts/ncaa/generate_replay.py --all
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ncaa.ncaa_bracket_engine import (
    NCAATournamentEngine,
    load_seed_model,
    load_seeds_by_weight,
)
from scripts.ncaa.live_monitor import (
    ROUND_ORDER,
    ROUND_TO_SESSION,
    BONUS_PTS,
    BONUS_RESULT_TYPES,
    build_moment,
    detect_leaderboard_changes,
    apply_penalties_to_projections,
)

SUPPORTED_YEARS = [2019, 2021, 2022, 2023, 2024, 2025]


def load_matches(year: int) -> list:
    path = PROJECT_ROOT / "data" / str(year) / "ncaa-tourney" / "parsed" / "matches.json"
    if not path.exists():
        print(f"  No matches found at {path}", file=sys.stderr)
        return []
    return json.loads(path.read_text())


def load_penalties(year: int) -> dict:
    path = PROJECT_ROOT / "data" / str(year) / "ncaa-tourney" / "team_penalties.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def generate_replay(year: int, verbose: bool = False) -> dict:
    print(f"\n{'='*60}")
    print(f"  Generating replay for {year}")
    print(f"{'='*60}")

    seed_model = load_seed_model()
    seeds_by_weight = load_seeds_by_weight(year)

    if not seeds_by_weight:
        print(f"  ERROR: No seed files for {year}", file=sys.stderr)
        return {}

    matches = load_matches(year)
    if not matches:
        print(f"  ERROR: No matches for {year}", file=sys.stderr)
        return {}

    penalties = load_penalties(year)
    if penalties:
        print(f"  Loaded penalties: {penalties}")

    # Pre-tournament baseline
    pre_engine = NCAATournamentEngine.from_matches(seed_model, seeds_by_weight, [])
    pre_tourney_teams = pre_engine.get_team_totals()
    pre_projections = pre_engine.get_projections()

    # Sort matches in the same round order used by live_monitor
    round_rank = {r: i for i, r in enumerate(ROUND_ORDER)}
    sorted_matches = sorted(
        matches,
        key=lambda m: (round_rank.get(m.get("round", ""), 99), m.get("weight", 0)),
    )

    # Build history, moments, and per-match projections
    history = [{
        "round": "pre",
        "match_n": 0,
        "projections": apply_penalties_to_projections(
            {t: round(v, 2) for t, v in pre_tourney_teams.items()}, penalties
        ),
    }]
    moments = []
    prev_totals = {t: round(v, 2) for t, v in pre_tourney_teams.items()}
    prev_ranking = [t for t, _ in sorted(prev_totals.items(), key=lambda x: -x[1])]

    print(f"  Replaying {len(sorted_matches)} matches...")
    for i, match in enumerate(sorted_matches):
        ws = match.get("winner_seed")
        ls = match.get("loser_seed")
        if ws is None or ls is None:
            continue

        match_n = i + 1
        eng = NCAATournamentEngine.from_matches(seed_model, seeds_by_weight, sorted_matches[:i + 1])
        curr_totals = eng.get_team_totals()

        session_label = ROUND_TO_SESSION.get(match.get("round", ""), match.get("round", ""))
        all_teams = set(prev_totals) | set(curr_totals)
        impacts = {
            t: round(curr_totals.get(t, 0.0) - prev_totals.get(t, 0.0), 2)
            for t in all_teams
            if abs(curr_totals.get(t, 0.0) - prev_totals.get(t, 0.0)) >= 2.0
        }

        curr_ranking = [t for t, _ in sorted(curr_totals.items(), key=lambda x: -x[1])]
        rt = match.get("result_type", "Dec")
        is_upset = ws > ls
        is_bonus = rt in BONUS_RESULT_TYPES
        top10 = set(curr_ranking[:10])
        if impacts and (is_upset or is_bonus) and any(t in top10 for t in impacts):
            moments.append(build_moment(match, match_n, session_label, impacts))
        lb_changes = detect_leaderboard_changes(prev_ranking, curr_ranking)
        if lb_changes:
            moments.append({
                "type": "leaderboard",
                "match_n": match_n,
                "round_label": session_label,
                "changes": lb_changes,
                "tag": "LEADERBOARD",
                "impacts": {},
            })

        history.append({
            "round": session_label,
            "match_n": match_n,
            "match": {
                "weight": match.get("weight"),
                "winner_name": match.get("winner_name"),
                "loser_name": match.get("loser_name"),
                "result_type": rt,
                "score": match.get("score"),
            },
            "projections": apply_penalties_to_projections(
                {t: round(v, 2) for t, v in curr_totals.items()}, penalties
            ),
        })

        prev_totals = {t: round(v, 2) for t, v in curr_totals.items()}
        prev_ranking = curr_ranking

        if verbose and match_n % 50 == 0:
            print(f"    ... {match_n}/{len(sorted_matches)}")

    print(f"  Built {len(history)} history entries, {len(moments)} moments")

    # Final engine state for snapshot
    final_engine = NCAATournamentEngine.from_matches(seed_model, seeds_by_weight, sorted_matches)
    snap = final_engine.get_snapshot(pre_projections=pre_projections)

    # Apply penalties to final snapshot
    if penalties:
        for team, adj in penalties.items():
            if team in snap.get("current_projection", {}):
                snap["current_projection"][team] = round(snap["current_projection"][team] + adj, 2)
            if team in snap.get("score_ranges", {}):
                r = snap["score_ranges"][team]
                r["min_score"] = round(r["min_score"] + adj, 2)
                r["max_score"] = round(r["max_score"] + adj, 2)
        snap["team_penalties"] = penalties

    snap["year"] = year
    snap["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    snap["pre_tourney_predictions"] = {t: round(v, 2) for t, v in pre_tourney_teams.items()}
    snap["history"] = history
    snap["moments"] = moments
    snap["sorted_matches"] = sorted_matches

    return snap


def main():
    parser = argparse.ArgumentParser(description="Generate simulation replay for archived NCAA years")
    parser.add_argument("--year", type=int, help="Year to generate (e.g. 2025)")
    parser.add_argument("--all", action="store_true", help="Generate for all supported years")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.all:
        years = SUPPORTED_YEARS
    elif args.year:
        years = [args.year]
    else:
        parser.error("Specify --year YYYY or --all")

    for year in years:
        replay = generate_replay(year, verbose=args.verbose)
        if not replay:
            print(f"  Skipping {year} (no data)", file=sys.stderr)
            continue

        out_path = PROJECT_ROOT / "data" / str(year) / "simulation_replay.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(replay))
        print(f"  Written: {out_path}")


if __name__ == "__main__":
    main()
