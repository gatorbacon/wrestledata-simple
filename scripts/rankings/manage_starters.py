#!/usr/bin/env python3
"""
Interactive tool to override starter designations in rankings_*.json.

Context:
- By default, many tools treat the highest-ranked wrestler per team/weight
  as the "starter", and everyone else as backups.
- Rankings files under mt/rankings_data/{season}/rankings_{weight}.json
  already include an `is_starter` boolean flag for each entry.

This script lets you:
  - Inspect all ranked wrestlers for a given weight class.
  - For each team, explicitly choose which wrestler is the starter.
  - The chosen starter gets is_starter = true; all others from that team
    in that weight get is_starter = false.

Only the `is_starter` flags are changed; ranks and other fields are left
unchanged. You can safely re-run this script as often as needed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List


def load_rankings_file(season: int, weight: str, data_dir: str) -> Dict:
    base = Path(data_dir) / str(season)
    path = base / f"rankings_{weight}.json"
    if not path.exists():
        raise FileNotFoundError(f"Rankings file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_rankings_file(season: int, weight: str, data_dir: str, data: Dict) -> None:
    base = Path(data_dir) / str(season)
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"rankings_{weight}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Saved updated rankings to {path}")


def interactive_manage_starters(season: int, weight: str, data_dir: str) -> None:
    data = load_rankings_file(season, weight, data_dir)
    rankings: List[Dict] = data.get("rankings", [])
    if not rankings:
        print(f"No rankings found in rankings_{weight}.json")
        return

    # Group indices by team name
    by_team: Dict[str, List[int]] = {}
    for idx, entry in enumerate(rankings):
        team = entry.get("team", "Unknown")
        by_team.setdefault(team, []).append(idx)

    teams_sorted = sorted(by_team.keys())

    while True:
        print("\n=== Starter Management ===")
        print(f"Season {season}, weight {weight} lbs\n")
        print("Teams in this weight (current starters marked with '*'):\n")

        for i, team in enumerate(teams_sorted, start=1):
            idxs = by_team[team]
            starters = [
                rankings[j]
                for j in idxs
                if rankings[j].get("is_starter", False)
            ]
            starter_names = ", ".join(f"#{s.get('rank')} {s.get('name')}" for s in starters) or "none"
            print(f"{i:3d}. {team}: starter(s) = {starter_names}")

        choice = input(
            "\nEnter team number to edit, or press Enter to finish (q to quit): "
        ).strip()
        if not choice or choice.lower() == "q":
            break

        try:
            team_idx = int(choice)
        except ValueError:
            print("Please enter a valid number.")
            continue

        if not (1 <= team_idx <= len(teams_sorted)):
            print("Team index out of range.")
            continue

        team = teams_sorted[team_idx - 1]
        idxs = by_team[team]

        print(f"\nWrestlers for team '{team}' at {weight} lbs:")
        for j, idx in enumerate(idxs, start=1):
            e = rankings[idx]
            mark = "*" if e.get("is_starter", False) else " "
            print(
                f"  {j:2d}. [{mark}] rank #{e.get('rank')} "
                f"{e.get('name')} (id={e.get('wrestler_id')})"
            )

        pick = input(
            "\nChoose starter number (1..N), 'n' for no starter, or Enter to cancel: "
        ).strip().lower()
        if not pick:
            continue
        if pick == "n":
            for idx in idxs:
                rankings[idx]["is_starter"] = False
            print(f"Cleared starter flag for all {team} wrestlers at this weight.")
        else:
            try:
                w_choice = int(pick)
            except ValueError:
                print("Invalid choice.")
                continue
            if not (1 <= w_choice <= len(idxs)):
                print("Wrestler index out of range.")
                continue
            chosen_idx = idxs[w_choice - 1]
            # Set chosen as starter, others in this team as non-starter
            for idx in idxs:
                rankings[idx]["is_starter"] = (idx == chosen_idx)

            chosen = rankings[chosen_idx]
            print(
                f"Set starter for {team} at {weight} lbs to "
                f"rank #{chosen.get('rank')} {chosen.get('name')}."
            )

        # Save after each team edit to keep state durable.
        data["rankings"] = rankings
        save_rankings_file(season, weight, data_dir, data)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Interactively override starter flags (is_starter) in rankings_*.json "
            "for a single weight class."
        )
    )
    parser.add_argument(
        "-season",
        type=int,
        required=True,
        help="Season year (e.g., 2026).",
    )
    parser.add_argument(
        "-weight-class",
        required=True,
        help="Weight class string (e.g., 125, 133, 141).",
    )
    parser.add_argument(
        "-data-dir",
        default="mt/rankings_data",
        help="Base rankings directory containing rankings_*.json.",
    )

    args = parser.parse_args()
    season = args.season
    weight = str(args.weight_class)

    interactive_manage_starters(season, weight, args.data_dir)


if __name__ == "__main__":
    main()


