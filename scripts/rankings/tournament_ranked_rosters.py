#!/usr/bin/env python3
"""
tournament_ranked_rosters.py

Interactive helper for tournaments:

  - Create a tournament (name, date, list of teams) for a given season.
  - Save tournaments to JSON for reuse.
  - For a chosen tournament, list all ranked wrestlers at each weight class
    for the participating teams.

Ranked wrestlers are pulled from:

    mt/rankings_data/{season}/rankings_{weight}.json

Teams are discovered from the processed season data via load_team_data().

Usage (from repo root):

    python scripts/rankings/tournament_ranked_rosters.py -season 2026
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

from load_data import load_team_data


RANKINGS_BASE = Path("mt/rankings_data")

# Standard NCAA weights for D1
WEIGHTS = ["125", "133", "141", "149", "157", "165", "174", "184", "197", "285"]


@dataclass
class Tournament:
    name: str
    date: date
    date_code: str  # MMDDYY
    teams: List[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create tournaments and list ranked wrestlers at each weight class "
            "for the participating teams."
        )
    )
    parser.add_argument(
        "-season",
        type=int,
        default=2026,
        help="Season year (default: 2026).",
    )
    return parser.parse_args()


def tournaments_file_for_season(season: int) -> Path:
    return RANKINGS_BASE / str(season) / "tournaments.json"


def load_tournaments(season: int) -> List[Tournament]:
    path = tournaments_file_for_season(season)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    tournaments: List[Tournament] = []
    for item in raw:
        try:
            d = date.fromisoformat(item["date"])
            tournaments.append(
                Tournament(
                    name=item["name"],
                    date=d,
                    date_code=item.get("date_code", ""),
                    teams=list(item.get("teams", [])),
                )
            )
        except Exception:
            continue
    return tournaments


def save_tournaments(season: int, tournaments: List[Tournament]) -> None:
    path = tournaments_file_for_season(season)
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = [
        {
            "name": t.name,
            "date": t.date.isoformat(),
            "date_code": t.date_code,
            "teams": t.teams,
        }
        for t in tournaments
    ]
    with path.open("w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2)


def parse_mmddyy(code: str) -> date:
    """
    Parse MMDDYY into a date, assuming 2000-based year.
    Example: '113025' -> 2025-11-30.
    """
    if len(code) != 6 or not code.isdigit():
        raise ValueError("Date must be 6 digits in MMDDYY format.")
    month = int(code[0:2])
    day = int(code[2:4])
    year_suffix = int(code[4:6])
    year = 2000 + year_suffix
    return date(year, month, day)


def search_teams(teams: List[Dict], query: str) -> List[str]:
    """Return sorted list of team_name values containing the query."""
    query_lower = query.lower()
    names = set()
    for team in teams:
        name = team.get("team_name", "Unknown")
        if query_lower in name.lower():
            names.add(name)
    return sorted(names)


def prompt_for_team(teams: List[Dict], label: str) -> Optional[str]:
    """
    Interactively prompt for a team by name fragment and return the full name.

    Returns None if the user presses Enter at the fragment prompt (i.e., no team).
    """
    while True:
        fragment = input(
            f"Enter name fragment for {label} (e.g. 'Iowa', blank to finish): "
        ).strip()
        if not fragment:
            # Caller interprets this as "no more teams".
            return None

        matches = search_teams(teams, fragment)
        if not matches:
            print("  No teams found containing that fragment. Try again.\n")
            continue

        print(f"Found {len(matches)} team(s):")
        for idx, name in enumerate(matches, start=1):
            print(f"  {idx:2d}) {name}")

        while True:
            sel = input(
                f"Select {label} by number (1-{len(matches)}), "
                f"or blank to search again: "
            ).strip()
            if not sel:
                print("  Search cancelled, try another fragment.\n")
                break
            try:
                num = int(sel)
                if 1 <= num <= len(matches):
                    chosen = matches[num - 1]
                    print(f"  Selected {label}: {chosen}\n")
                    return chosen
            except ValueError:
                pass
            print("  Invalid selection; please enter a valid number.")


def prompt_create_tournament(season: int) -> Tournament:
    print("\n=== Create Tournament ===\n")
    name = input("Tournament name: ").strip()
    while not name:
        print("  Tournament name cannot be empty.")
        name = input("Tournament name: ").strip()

    while True:
        code = input(
            "Tournament date in MMDDYY format (e.g. 113025 for Nov 30, 2025): "
        ).strip()
        try:
            d = parse_mmddyy(code)
            break
        except Exception as e:
            print(f"  Invalid date: {e}")

    print("\nAdd teams attending this tournament.")
    print("Enter team name fragments; press Enter with no input at the fragment prompt to stop.\n")

    season_teams = load_team_data(season)
    print(f"Loaded {len(season_teams)} teams for season {season}.\n")

    teams: List[str] = []
    while True:
        team_name = prompt_for_team(season_teams, "team")
        if team_name is None:
            break
        if team_name not in teams:
            teams.append(team_name)
            print(f"  Added team: {team_name}")
        else:
            print("  Team already in tournament list.")

    if not teams:
        print("No teams added; creating an empty tournament entry.\n")

    return Tournament(name=name, date=d, date_code=code, teams=teams)


def choose_tournament(tournaments: List[Tournament]) -> Optional[Tournament]:
    if not tournaments:
        return None

    print("\nExisting tournaments:")
    for idx, t in enumerate(tournaments, start=1):
        print(f"  {idx:2d}) {t.name} ({t.date.isoformat()}) — {len(t.teams)} team(s)")

    while True:
        sel = input(
            f"Select a tournament by number (1-{len(tournaments)}), or blank to cancel: "
        ).strip()
        if not sel:
            print("  No tournament selected.")
            return None
        try:
            num = int(sel)
            if 1 <= num <= len(tournaments):
                return tournaments[num - 1]
        except ValueError:
            pass
        print("  Invalid selection; please enter a valid number.")


def load_rankings_for_weight(season: int, weight: str) -> List[Dict]:
    """
    Load rankings_{weight}.json; return list of entries (may be empty).
    """
    path = RANKINGS_BASE / str(season) / f"rankings_{weight}.json"
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("rankings", [])


def list_ranked_wrestlers_for_tournament(
    season: int,
    tournament: Tournament,
    max_rank: int,
) -> None:
    # Interpret 0 as "top 20 only" for convenience.
    effective_max_rank = 20 if max_rank == 0 else max_rank

    print(
        f"\n=== Ranked Wrestlers for '{tournament.name}' "
        f"({tournament.date.isoformat()}), season {season} "
        f"(top {effective_max_rank}) ===\n"
    )
    if not tournament.teams:
        print("No teams are assigned to this tournament.")
        return

    print("Teams in this tournament:")
    for t in tournament.teams:
        print(f"  - {t}")
    print()

    for wt in WEIGHTS:
        rankings = load_rankings_for_weight(season, wt)
        if not rankings:
            continue

        # Helper to interpret original overall rank (from rankings JSON).
        def orig_rank(e: Dict) -> int:
            r = e.get("rank")
            try:
                return int(r)
            except (TypeError, ValueError):
                return 10**9

        # Partition globally into starters and non-starters based on is_starter flag.
        starters_all: List[Dict] = [e for e in rankings if e.get("is_starter")]
        nonstarters_all: List[Dict] = [e for e in rankings if not e.get("is_starter")]

        # --- Global starter-only rankings ---
        # Re-number ranks consecutively among starters only (1, 2, 3, ...),
        # independent of tournament membership.
        starters_all.sort(key=orig_rank)
        starter_rank_by_id: Dict[str, int] = {}
        for idx, e in enumerate(starters_all, start=1):
            wid = str(e.get("wrestler_id") or "")
            if not wid:
                continue
            starter_rank_by_id[wid] = idx

        # --- Global non-starter-only rankings ---
        # Similarly, build a separate ranking among non-starters only.
        nonstarters_all.sort(key=orig_rank)
        nonstarter_rank_by_id: Dict[str, int] = {}
        for idx, e in enumerate(nonstarters_all, start=1):
            wid = str(e.get("wrestler_id") or "")
            if not wid:
                continue
            nonstarter_rank_by_id[wid] = idx

        combined_entries: List[Dict] = []

        # Add starters for tournament teams whose starter-only rank is within cutoff.
        for e in starters_all:
            if e.get("team") not in tournament.teams:
                continue
            wid = str(e.get("wrestler_id") or "")
            if not wid:
                continue
            s_rank = starter_rank_by_id.get(wid)
            if not s_rank or s_rank > effective_max_rank:
                continue
            combined_entries.append(
                {
                    "type": "starter",
                    "display_rank": s_rank,
                    "sort_rank": (0, s_rank),  # starters listed before non-starters
                    "wrestler": e,
                }
            )

        # Add non-starters for tournament teams whose non-starter-only rank is within cutoff.
        for e in nonstarters_all:
            if e.get("team") not in tournament.teams:
                continue
            wid = str(e.get("wrestler_id") or "")
            if not wid:
                continue
            ns_rank = nonstarter_rank_by_id.get(wid)
            if not ns_rank or ns_rank > effective_max_rank:
                continue
            combined_entries.append(
                {
                    "type": "nonstarter",
                    "display_rank": None,
                    "sort_rank": (1, ns_rank),
                    "wrestler": e,
                }
            )

        if not combined_entries:
            continue

        # Sort final list: starters first, then non-starters, each by their own rank.
        combined_entries.sort(key=lambda x: x["sort_rank"])

        print(f"--- Weight {wt} ---")
        for entry in combined_entries:
            e = entry["wrestler"]
            name = e.get("name", "Unknown")
            team = e.get("team", "Unknown")
            if entry["type"] == "starter":
                rank_str = f"#{entry['display_rank']:2d}"
            else:
                rank_str = "**"
            print(f"  {rank_str} {name} ({team})")
        print()


def main() -> None:
    args = parse_args()
    season = args.season

    tournaments = load_tournaments(season)

    print("Tournament Ranked Rosters\n")
    print(f"Season: {season}")
    print("Options:")
    print("  1. Create a new tournament")
    print("  2. Use an existing tournament")
    print("  0. Exit")

    choice = input("Enter choice: ").strip()

    if choice == "1":
        t = prompt_create_tournament(season)
        # Replace any existing tournament with the same name (case-insensitive).
        lowered = t.name.lower()
        tournaments = [x for x in tournaments if x.name.lower() != lowered]
        tournaments.append(t)
        save_tournaments(season, tournaments)
        # Prompt for ranking cutoff.
        cutoff_str = input(
            "Show ranked wrestlers up to what rank? (0 = top 20 only) [20]: "
        ).strip()
        try:
            max_rank = int(cutoff_str) if cutoff_str else 20
        except ValueError:
            max_rank = 20
        list_ranked_wrestlers_for_tournament(season, t, max_rank)
    elif choice == "2":
        if not tournaments:
            print("\nNo tournaments saved yet; create one first.")
            return
        t = choose_tournament(tournaments)
        if t is None:
            return
        cutoff_str = input(
            "Show ranked wrestlers up to what rank? (0 = top 20 only) [20]: "
        ).strip()
        try:
            max_rank = int(cutoff_str) if cutoff_str else 20
        except ValueError:
            max_rank = 20
        list_ranked_wrestlers_for_tournament(season, t, max_rank)
    else:
        print("Exiting.")


if __name__ == "__main__":
    main()


