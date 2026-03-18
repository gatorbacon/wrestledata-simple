#!/usr/bin/env python3
"""
Replay NCAA tournament bracket match-by-match using parsed historical data.

Applies matches one at a time in round order, printing team leaderboards
after each round. Saves full replay snapshots for dashboard testing.

Usage:
  python scripts/ncaa/simulate_tournament.py --year 2024
  python scripts/ncaa/simulate_tournament.py --year 2024 --through-round R16
  python scripts/ncaa/simulate_tournament.py --year 2024 --verbose
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ncaa.ncaa_bracket_engine import (
    NCAATournamentEngine,
    load_seed_model,
    load_seeds_by_weight,
    WEIGHTS,
)

# Round processing order (matches parse_ncaa_results.py round names)
ROUND_ORDER = [
    "PIG",
    "R32", "C_PIG",   # C_PIG needs C_R32_8_LOSER, so comes after R32
    "C_R1",
    "R16", "C_R2",
    "C_R3", "QF",
    "C_R4", "C_QF",
    "SF",  "C_SF",
    "Final",
    "3rd", "5th", "7th",
]

# Sessions group parse rounds into chronological tournament sessions.
# Each entry: (session_label, [parse_rounds_included])
SESSIONS = [
    ("R32",       ["PIG", "R32"]),
    ("Consi 1",   ["C_PIG", "C_R1"]),
    ("R16",       ["R16"]),
    ("Consi 2",   ["C_R2"]),
    ("Consi 3",   ["C_R3"]),
    ("QF",        ["QF"]),
    ("Consi 4",   ["C_R4"]),
    ("Consi QF",  ["C_QF"]),
    ("SF",        ["SF"]),
    ("Consi SF",  ["C_SF"]),
    ("Medals",    ["3rd", "5th", "7th"]),
    ("Finals",    ["Final"]),
]

ROUND_TO_SESSION = {r: label for label, rounds in SESSIONS for r in rounds}
BONUS_RESULT_TYPES = {"Fall", "TF", "MD", "Forfeit", "DQ", "Inj."}

# Bonus points by result type
BONUS_PTS = {
    "Dec": 0.0, "SV-1": 0.0, "SV-2": 0.0, "SV-3": 0.0,
    "TB-1": 0.0, "TB-2": 0.0, "TB-3": 0.0, "UTB": 0.0,
    "MD": 1.0, "TF": 1.5,
    "Fall": 2.0, "Forfeit": 2.0, "DQ": 2.0, "Inj.": 2.0,
}

PLACEMENT_PTS = {1: 16.0, 2: 12.0, 3: 10.0, 4: 9.0, 5: 7.0, 6: 6.0, 7: 4.0, 8: 3.0}


def load_parsed_matches(year: int) -> list:
    """Load per-year parsed matches."""
    path = PROJECT_ROOT / "data" / str(year) / "ncaa-tourney" / "parsed" / "matches.json"
    if not path.exists():
        print(f"ERROR: {path} not found", file=sys.stderr)
        print(f"Run: python scripts/ncaa/parse_ncaa_results.py --year {year}", file=sys.stderr)
        sys.exit(1)
    return json.loads(path.read_text())


def load_parsed_wrestlers(year: int) -> list:
    """Load per-year parsed wrestlers for actual placement points."""
    path = PROJECT_ROOT / "data" / str(year) / "ncaa-tourney" / "parsed" / "wrestlers.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())


def group_by_round(matches: list) -> dict:
    """Group matches by round name."""
    groups = {r: [] for r in ROUND_ORDER}
    for m in matches:
        r = m.get("round", "")
        if r in groups:
            groups[r].append(m)
    return groups


def print_leaderboard(team_totals: dict, pre_tourney: dict, top_n: int = 10, label: str = ""):
    """Print team leaderboard."""
    sorted_teams = sorted(team_totals.items(), key=lambda x: -x[1])
    header = f"\n{'='*60}"
    if label:
        header += f"\n  {label}"
    header += f"\n{'='*60}"
    print(header)
    print(f"  {'Rank':4s} {'Team':30s} {'Proj':8s} {'Pre-Δ':8s}")
    print(f"  {'-'*52}")
    for i, (team, pts) in enumerate(sorted_teams[:top_n], 1):
        pre = pre_tourney.get(team, 0.0)
        delta = pts - pre
        delta_str = f"+{delta:.1f}" if delta >= 0 else f"{delta:.1f}"
        print(f"  {i:4d} {team:30s} {pts:8.2f} {delta_str:8s}")


def compute_actual_team_totals(wrestlers: list, matches_applied: list) -> dict:
    """Compute actual (not projected) team totals from applied matches."""
    # Build wrestler seed→team map
    seed_team = {}  # {(weight, seed): team}
    seed_pts = {}   # {(weight, seed): actual_pts}

    for w in wrestlers:
        key = (w["weight"], w["seed"])
        seed_team[key] = w["team"]
        seed_pts[key] = 0.0

    for m in matches_applied:
        wt = m["weight"]
        ws = m.get("winner_seed")
        ls = m.get("loser_seed")
        rnd = m.get("round", "")

        # Advancement points
        from scripts.ncaa.parse_ncaa_results import ADVANCEMENT_PTS
        adv = ADVANCEMENT_PTS.get(rnd, 0.0)
        bonus = BONUS_PTS.get(m.get("result_type", ""), 0.0)

        if ws and (wt, ws) in seed_pts:
            seed_pts[(wt, ws)] = seed_pts.get((wt, ws), 0.0) + adv + bonus

    totals: dict = {}
    for (wt, seed), pts in seed_pts.items():
        team = seed_team.get((wt, seed), "Unknown")
        totals[team] = totals.get(team, 0.0) + pts

    return totals


def detect_leaderboard_changes(prev_ranking, curr_ranking):
    """Detect top-5 position changes and top-10 entries/exits."""
    changes = []
    reported = set()

    # Top 5 position changes
    prev_top5 = prev_ranking[:5]
    curr_top5 = curr_ranking[:5]
    if prev_top5 != curr_top5:
        for i, team in enumerate(curr_top5):
            curr_pos = i + 1
            prev_pos = (prev_ranking.index(team) + 1) if team in prev_ranking else None
            if prev_pos != curr_pos and team not in reported:
                reported.add(team)
                arrow = "↑" if (prev_pos is None or curr_pos < prev_pos) else "↓"
                from_str = f"#{prev_pos}" if prev_pos else "outside top 5"
                changes.append(f"{arrow} {team} {from_str}→#{curr_pos}")
        for i, team in enumerate(prev_top5):
            if team not in curr_top5 and team not in reported:
                reported.add(team)
                curr_pos = (curr_ranking.index(team) + 1) if team in curr_ranking else None
                to_str = f"#{curr_pos}" if curr_pos else "unranked"
                changes.append(f"↓ {team} #{i+1}→{to_str}")

    # Top 10 entries/exits (skip teams already covered by top-5 reporting)
    prev_top10 = set(prev_ranking[:10])
    curr_top10 = set(curr_ranking[:10])
    for team in curr_top10 - prev_top10:
        if team not in reported:
            rank = curr_ranking.index(team) + 1
            changes.append(f"↑ {team} enters Top 10 (#{rank})")
    for team in prev_top10 - curr_top10:
        if team not in reported:
            prev_rank = prev_ranking.index(team) + 1
            changes.append(f"↓ {team} exits Top 10 (was #{prev_rank})")

    return changes


def build_moment(match, match_n, session_label, impacts):
    ws, ls = match.get("winner_seed"), match.get("loser_seed")
    rt = match.get("result_type", "Dec")
    is_upset = ws is not None and ls is not None and ws > ls
    is_bonus = rt in BONUS_RESULT_TYPES
    if is_upset and is_bonus: tag = "UPSET+BONUS"
    elif is_upset:            tag = "UPSET"
    elif is_bonus:            tag = "BONUS"
    else:                     tag = None
    return {
        "match_n": match_n, "round_label": session_label,
        "weight": match.get("weight"),
        "winner_seed": ws, "winner_name": match.get("winner_name", f"Seed {ws}"),
        "winner_team": match.get("winner_team", "Unknown"),
        "loser_seed": ls,  "loser_name": match.get("loser_name", f"Seed {ls}"),
        "loser_team": match.get("loser_team", "Unknown"),
        "result_type": rt, "tag": tag, "impacts": impacts,
    }


def run_simulation(
    year: int,
    through_round: str = None,
    verbose: bool = False,
    save_replay: bool = True,
):
    """
    Replay a tournament year match-by-match.

    Args:
        year: Tournament year
        through_round: Stop after this round (e.g. "R16")
        verbose: Print each match result
        save_replay: Save snapshot history to simulation_replay.json
    """
    print(f"\nLoading {year} tournament data...")
    matches = load_parsed_matches(year)
    wrestlers = load_parsed_wrestlers(year)
    seed_model = load_seed_model()
    seeds_by_weight = load_seeds_by_weight(year)

    print(f"  {len(matches)} matches loaded")
    print(f"  Weights with seed data: {sorted(seeds_by_weight.keys())}")

    # Fallback: if no seed files, build seeds from wrestler data
    if not seeds_by_weight:
        print("  WARNING: No seed files found, building from wrestler data")
        for w in wrestlers:
            wt = w["weight"]
            s = w.get("seed")
            if s and 1 <= s <= 33:
                if wt not in seeds_by_weight:
                    seeds_by_weight[wt] = {}
                seeds_by_weight[wt][s] = {
                    "name": w.get("name", f"Seed {s}"),
                    "team": w.get("team", "Unknown"),
                }

    # Pre-tournament projections (no results applied)
    print("Computing pre-tournament projections...")
    pre_engine = NCAATournamentEngine.from_matches(seed_model, seeds_by_weight, [])
    pre_tourney_teams = pre_engine.get_team_totals()

    print_leaderboard(pre_tourney_teams, pre_tourney_teams, label="PRE-TOURNAMENT PROJECTIONS")

    by_round = group_by_round(matches)
    applied_matches = []
    history = []

    history.append({
        "round": "pre",
        "match_n": 0,
        "projections": {t: round(v, 2) for t, v in pre_tourney_teams.items()},
    })

    match_counter = 0
    stop_after = through_round
    final_engine = pre_engine
    moments = []
    prev_totals = {t: round(v, 2) for t, v in pre_tourney_teams.items()}
    prev_ranking = [t for t, _ in sorted(pre_tourney_teams.items(), key=lambda x: -x[1])]

    for session_label, session_rounds in SESSIONS:
        session_count = 0
        for round_name in session_rounds:
            for m in by_round.get(round_name, []):
                ws, ls = m.get("winner_seed"), m.get("loser_seed")
                if ws is None or ls is None:
                    continue
                applied_matches.append(m)
                match_counter += 1
                session_count += 1

                # Per-match engine for xTP delta
                eng = NCAATournamentEngine.from_matches(seed_model, seeds_by_weight, applied_matches)
                curr_totals = eng.get_team_totals()
                all_teams = set(prev_totals) | set(curr_totals)
                impacts = {
                    t: round(curr_totals.get(t, 0.0) - prev_totals.get(t, 0.0), 2)
                    for t in all_teams
                    if abs(curr_totals.get(t, 0.0) - prev_totals.get(t, 0.0)) >= 2.0
                }
                curr_ranking = [t for t, _ in sorted(curr_totals.items(), key=lambda x: -x[1])]
                # Only record match moments for upsets or bonus finishes that affect a top-10 team
                rt = m.get("result_type", "Dec")
                is_upset = ws > ls
                is_bonus = rt in BONUS_RESULT_TYPES
                top10 = set(curr_ranking[:10])
                if impacts and (is_upset or is_bonus) and any(t in top10 for t in impacts):
                    moments.append(build_moment(m, match_counter, session_label, impacts))
                # Detect leaderboard changes
                lb_changes = detect_leaderboard_changes(prev_ranking, curr_ranking)
                if lb_changes:
                    moments.append({
                        "type": "leaderboard",
                        "match_n": match_counter,
                        "round_label": session_label,
                        "changes": lb_changes,
                        "tag": "LEADERBOARD",
                        "impacts": {},
                    })
                prev_ranking = curr_ranking
                prev_totals = {t: round(v, 2) for t, v in curr_totals.items()}

        if session_count == 0:
            continue

        # Session-level history snapshot (unchanged behavior)
        final_engine = NCAATournamentEngine.from_matches(seed_model, seeds_by_weight, applied_matches)
        team_totals = final_engine.get_team_totals()
        history.append({"round": session_label, "match_n": match_counter,
                        "projections": {t: round(v, 2) for t, v in team_totals.items()}})
        print_leaderboard(team_totals, pre_tourney_teams,
                          label=f"After {session_label} ({match_counter} matches completed)")
        if stop_after and stop_after == session_label:
            break

    print(f"Found {len(moments)} big moments.")

    # Final snapshot with history
    final_snap = final_engine.get_snapshot()
    final_snap["year"] = year
    final_snap["matches_completed"] = match_counter
    final_snap["matches_total"] = match_counter
    final_snap["pre_tourney_predictions"] = {t: round(v, 2) for t, v in pre_tourney_teams.items()}
    final_snap["history"] = history
    final_snap["moments"] = moments

    if save_replay:
        out_path = PROJECT_ROOT / "data" / str(year) / "simulation_replay.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(final_snap, indent=2))
        print(f"\nReplay saved to {out_path}")

    # Final leaderboard
    final_teams = final_engine.get_team_totals()
    print_leaderboard(
        final_teams, pre_tourney_teams,
        top_n=20,
        label=f"FINAL PROJECTIONS ({match_counter} matches)"
    )

    return final_snap


def main():
    parser = argparse.ArgumentParser(description="Simulate NCAA tournament round by round")
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument(
        "--through-round",
        choices=[s[0] for s in SESSIONS],
        default=None,
        help="Stop after this session (e.g. R16, QF, SF)",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--no-save", action="store_true", help="Don't save replay file")
    args = parser.parse_args()

    run_simulation(
        year=args.year,
        through_round=args.through_round,
        verbose=args.verbose,
        save_replay=not args.no_save,
    )


if __name__ == "__main__":
    main()
