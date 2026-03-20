#!/usr/bin/env python3
"""
Live NCAA tournament prediction monitor.

Polls TrackWrestling every ~2 minutes, updates bracket engine with new
results, writes live_data.json for the dashboard.

Usage:
  python scripts/ncaa/live_monitor.py --year 2026
  python scripts/ncaa/live_monitor.py --year 2026 --interval 120
  python scripts/ncaa/live_monitor.py --year 2026 --once  # single pass
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ncaa.ncaa_bracket_engine import (
    NCAATournamentEngine,
    load_seed_model,
    load_seeds_by_weight,
    WEIGHTS,
)

LIVE_DATA_PATH = PROJECT_ROOT / "live_data.json"
PARSED_DIR_TEMPLATE = str(PROJECT_ROOT / "data" / "{year}" / "ncaa-tourney" / "parsed")

BONUS_PTS = {
    "Dec": 0.0, "SV-1": 0.0, "SV-2": 0.0, "SV-3": 0.0,
    "TB-1": 0.0, "TB-2": 0.0, "TB-3": 0.0, "UTB": 0.0,
    "MD": 1.0, "TF": 1.5,
    "Fall": 2.0, "Forfeit": 2.0, "DQ": 2.0, "Inj.": 2.0,
}

BONUS_RESULT_TYPES = {"Fall", "TF", "MD", "Forfeit", "DQ", "Inj."}

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

# Round processing order
ROUND_ORDER = [
    "PIG",
    "R32", "C_PIG",   # C_PIG needs C_R32_8_LOSER → must come after R32
    "C_R1",
    "R16", "C_R2",
    "QF", "C_R3", "C_R4",
    "SF", "C_QF",
    "C_SF", "Final",
    "3rd", "5th", "7th",
]


def detect_leaderboard_changes(prev_ranking, curr_ranking):
    """Detect top-5 position changes and top-10 entries/exits."""
    changes = []
    reported = set()

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


def scrape_and_parse(year: int) -> bool:
    """
    Invoke scraper then parser for the given year.
    Returns True if successful.
    """
    import subprocess

    scrape_script = PROJECT_ROOT / "scripts" / "scraping" / "scrape_ncaa_tournament.py"
    parse_script = PROJECT_ROOT / "scripts" / "ncaa" / "parse_ncaa_results.py"

    print(f"  Scraping {year}...", end=" ", flush=True)
    result = subprocess.run(
        [sys.executable, str(scrape_script), "--year", str(year)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"FAILED")
        print(f"  {result.stderr[:200]}", file=sys.stderr)
        return False
    print("OK")

    print(f"  Parsing {year}...", end=" ", flush=True)
    result = subprocess.run(
        [sys.executable, str(parse_script), "--year", str(year)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"FAILED")
        print(f"  {result.stderr[:200]}", file=sys.stderr)
        return False
    print("OK")

    return True


def load_matches(year: int) -> list:
    """Load parsed matches for this year, or empty list if not available."""
    path = Path(PARSED_DIR_TEMPLATE.format(year=year)) / "matches.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())


def matches_key(m: dict) -> tuple:
    """Unique key for a match record."""
    return (
        m.get("weight"),
        m.get("round"),
        m.get("winner_seed"),
        m.get("loser_seed"),
    )


def diff_matches(old: list, new: list) -> list:
    """Return matches in new that are not in old."""
    old_keys = {matches_key(m) for m in old}
    return [m for m in new if matches_key(m) not in old_keys]


def apply_matches_to_engine(engine: NCAATournamentEngine, matches: list) -> int:
    """Apply a list of match results to the engine. Returns count applied."""
    applied = 0
    # Sort by round order so dependencies are resolved first
    round_rank = {r: i for i, r in enumerate(ROUND_ORDER)}

    sorted_matches = sorted(
        matches,
        key=lambda m: (
            round_rank.get(m.get("round", ""), 99),
            m.get("weight", 0),
        ),
    )

    for m in sorted_matches:
        ws = m.get("winner_seed")
        ls = m.get("loser_seed")
        wt = m.get("weight")
        result_type = m.get("result_type", "Dec")
        bonus = BONUS_PTS.get(result_type, 0.0)

        if ws is None or ls is None or wt is None:
            continue

        ok = engine.set_result(wt, ws, ls, result_type=result_type, actual_bonus=bonus)
        if ok:
            applied += 1

    return applied


def reconstruct_history(matches, pre_tourney_teams, seed_model, seeds_by_weight):
    """Rebuild per-session projection snapshots from a complete match list.

    Called after a fresh start (ephemeral filesystem restart) once all current
    matches have been scraped, so the chart has all historical round data points.
    """
    history = [{
        "round": "pre",
        "match_n": 0,
        "projections": {t: round(v, 2) for t, v in pre_tourney_teams.items()},
    }]
    if not matches:
        return history

    # Group matches by session label
    session_groups = {}
    for m in matches:
        session = ROUND_TO_SESSION.get(m.get("round", ""), m.get("round", "Live"))
        session_groups.setdefault(session, []).append(m)

    # Replay sessions in order, snapshotting after each one
    cumulative = []
    for label, _ in SESSIONS:
        if label not in session_groups:
            continue
        cumulative.extend(session_groups[label])
        eng = NCAATournamentEngine.from_matches(seed_model, seeds_by_weight, cumulative)
        totals = eng.get_team_totals()
        history.append({
            "round": label,
            "match_n": len(cumulative),
            "projections": {t: round(v, 2) for t, v in totals.items()},
        })

    print(f"  Reconstructed {len(history)} history entries from {len(matches)} matches")
    return history


def build_live_data(
    engine: NCAATournamentEngine,
    pre_tourney_teams: dict,
    history: list,
    moments: list = None,
    pre_projections: dict = None,
) -> dict:
    """Build live_data.json content."""
    snap = engine.get_snapshot(pre_projections=pre_projections)
    snap["pre_tourney_predictions"] = {t: round(v, 2) for t, v in pre_tourney_teams.items()}
    snap["history"] = history
    snap["moments"] = moments or []
    return snap


def run_live(
    year: int,
    interval_seconds: int = 120,
    once: bool = False,
    skip_scrape: bool = False,
):
    """Main live monitor loop."""
    print(f"\n{'='*60}")
    print(f"  NCAA Live Monitor — {year} Season")
    print(f"  Output: {LIVE_DATA_PATH}")
    print(f"  Interval: {interval_seconds}s")
    print(f"{'='*60}\n")

    # Load static data
    print("Loading seed model and seeding data...")
    seed_model = load_seed_model()
    seeds_by_weight = load_seeds_by_weight(year)

    if not seeds_by_weight:
        print(f"WARNING: No seed files found for {year}.", file=sys.stderr)
        print(f"Expected: data/{year}/ncaa-tourney/seeds/125.txt etc.", file=sys.stderr)

    # Compute pre-tournament projections
    print("Computing pre-tournament projections...")
    pre_engine = NCAATournamentEngine.from_matches(seed_model, seeds_by_weight, [])
    pre_tourney_teams = pre_engine.get_team_totals()
    pre_projections = pre_engine.get_projections()  # per-wrestler baseline for delta tracking

    top10 = sorted(pre_tourney_teams.items(), key=lambda x: -x[1])[:10]
    print("Pre-tournament top 10:")
    for i, (team, pts) in enumerate(top10, 1):
        print(f"  {i:2d}. {team:30s} {pts:.2f}")

    # State tracking — restore from disk so restarts don't lose history or moments
    moments: list = []
    history: list = []
    if LIVE_DATA_PATH.exists():
        try:
            existing = json.loads(LIVE_DATA_PATH.read_text())
            moments = existing.get("moments", [])
            history = existing.get("history", [])
            print(f"Restored {len(moments)} moments, {len(history)} history entries from existing live_data.json")
        except Exception:
            pass

    # Ensure history always has the pre-tourney baseline as its first entry
    if not history:
        history = [{
            "round": "pre",
            "match_n": 0,
            "projections": {t: round(v, 2) for t, v in pre_tourney_teams.items()},
        }]

    # Pre-populate known_matches from disk so the first cycle doesn't replay
    # all existing results as "new" (which would add duplicate history entries).
    # On Railway (ephemeral filesystem), this will be empty after a restart —
    # is_fresh_start tracks that so we can reconstruct history after first scrape.
    known_matches: list = load_matches(year)
    is_fresh_start = len(known_matches) == 0
    match_counter = len(known_matches)
    if known_matches:
        print(f"Pre-loaded {len(known_matches)} matches from disk")
    else:
        print("No existing matches on disk — will reconstruct history after first scrape")

    # Compute correct baseline for moment detection
    if known_matches:
        bootstrap_engine = NCAATournamentEngine.from_matches(seed_model, seeds_by_weight, known_matches)
        prev_totals = {t: round(v, 2) for t, v in bootstrap_engine.get_team_totals().items()}
    else:
        prev_totals = {t: round(v, 2) for t, v in pre_tourney_teams.items()}
    prev_ranking = [t for t, _ in sorted(prev_totals.items(), key=lambda x: -x[1])]

    # Initial snapshot (reflects current match state + restored history)
    engine = NCAATournamentEngine.from_matches(seed_model, seeds_by_weight, known_matches)
    snap = build_live_data(engine, pre_tourney_teams, history, moments, pre_projections=pre_projections)
    LIVE_DATA_PATH.write_text(json.dumps(snap, indent=2))
    print(f"\nInitial live_data.json written.")

    cycle = 0
    try:
        while True:
            cycle += 1
            now = datetime.now().strftime("%H:%M:%S")
            print(f"\n[{now}] Cycle {cycle} — {match_counter} matches applied")

            # 1. Scrape and parse
            if not skip_scrape:
                ok = scrape_and_parse(year)
                if not ok:
                    print("  Scrape failed, using cached data")

            # 2. Load current match state
            new_matches = load_matches(year)
            if not new_matches:
                print("  No parsed matches found yet")
                if once:
                    break
                print(f"  Sleeping {interval_seconds}s...")
                time.sleep(interval_seconds)
                continue

            # 3. Diff against known state
            new_results = diff_matches(known_matches, new_matches)

            if new_results:
                print(f"  {len(new_results)} new match results found")

                # Sort new results by round order for consistent processing
                round_rank = {r: i for i, r in enumerate(ROUND_ORDER)}
                sorted_new = sorted(
                    new_results,
                    key=lambda m: (round_rank.get(m.get("round", ""), 99), m.get("weight", 0)),
                )

                # Process each match individually to capture per-match xTP deltas
                n_applied = 0
                for m in sorted_new:
                    ws, ls = m.get("winner_seed"), m.get("loser_seed")
                    if ws is None or ls is None:
                        continue
                    known_matches.append(m)
                    match_counter += 1
                    n_applied += 1

                    eng = NCAATournamentEngine.from_matches(seed_model, seeds_by_weight, known_matches)
                    curr_totals = eng.get_team_totals()
                    all_teams = set(prev_totals) | set(curr_totals)
                    impacts = {
                        t: round(curr_totals.get(t, 0.0) - prev_totals.get(t, 0.0), 2)
                        for t in all_teams
                        if abs(curr_totals.get(t, 0.0) - prev_totals.get(t, 0.0)) >= 2.0
                    }
                    session_label = ROUND_TO_SESSION.get(m.get("round", ""), m.get("round", ""))
                    curr_ranking = [t for t, _ in sorted(curr_totals.items(), key=lambda x: -x[1])]
                    rt = m.get("result_type", "Dec")
                    is_upset = ws > ls
                    is_bonus = rt in BONUS_RESULT_TYPES
                    top10 = set(curr_ranking[:10])
                    if impacts and (is_upset or is_bonus) and any(t in top10 for t in impacts):
                        moments.append(build_moment(m, match_counter, session_label, impacts))
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

                # Sync known_matches to full new_matches list (catches any we missed)
                known_matches = new_matches
                print(f"  Applied {n_applied} results ({match_counter} total)")
            else:
                print("  No new results")

            # 4. Rebuild engine fresh with all known matches → correct projection
            engine = NCAATournamentEngine.from_matches(seed_model, seeds_by_weight, known_matches)
            team_totals = engine.get_team_totals()

            # 5. Update history and write live_data.json only when new results arrived
            if new_results:
                if is_fresh_start:
                    # Ephemeral restart: rebuild full round-by-round history from
                    # all current matches so the chart doesn't lose earlier rounds
                    history = reconstruct_history(
                        known_matches, pre_tourney_teams, seed_model, seeds_by_weight
                    )
                    is_fresh_start = False
                else:
                    round_order_map = {r: i for i, r in enumerate(ROUND_ORDER)}
                    latest_round = max(
                        (m.get("round", "") for m in known_matches),
                        key=lambda r: round_order_map.get(r, -1),
                        default="",
                    )
                    history.append({
                        "round": ROUND_TO_SESSION.get(latest_round, latest_round or "Live"),
                        "match_n": match_counter,
                        "projections": {t: round(v, 2) for t, v in team_totals.items()},
                    })
                live_data = build_live_data(engine, pre_tourney_teams, history, moments, pre_projections=pre_projections)
                LIVE_DATA_PATH.write_text(json.dumps(live_data, indent=2))

            # 6. Console summary
            top10_current = sorted(team_totals.items(), key=lambda x: -x[1])[:10]
            print(f"  Top 10 projected teams:")
            print(f"  {'Rank':4s} {'Team':28s} {'Proj':8s} {'Δ Pre':8s}")
            for i, (team, pts) in enumerate(top10_current, 1):
                pre = pre_tourney_teams.get(team, 0.0)
                delta = pts - pre
                dstr = f"+{delta:.1f}" if delta >= 0 else f"{delta:.1f}"
                print(f"  {i:4d} {team:28s} {pts:8.2f} {dstr:8s}")

            if once:
                break

            print(f"\n  Sleeping {interval_seconds}s... (Ctrl-C to stop)")
            time.sleep(interval_seconds)

    except KeyboardInterrupt:
        print(f"\n\nMonitor stopped after {cycle} cycles, {match_counter} matches applied.")
        print(f"Final live_data.json: {LIVE_DATA_PATH}")


def main():
    parser = argparse.ArgumentParser(description="Live NCAA tournament prediction monitor")
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--interval", type=int, default=120, help="Poll interval (seconds)")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    parser.add_argument("--skip-scrape", action="store_true", help="Use existing data, don't scrape")
    args = parser.parse_args()

    run_live(
        year=args.year,
        interval_seconds=args.interval,
        once=args.once,
        skip_scrape=args.skip_scrape,
    )


if __name__ == "__main__":
    main()
