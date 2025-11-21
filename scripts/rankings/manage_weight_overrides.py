#!/usr/bin/env python3
"""
Manage manual weight overrides ("virtual matches") for wrestlers.

These overrides only influence the weight-assignment logic in load_data.py
by pretending the wrestler wrestled N matches at a given weight on a date.

File format (mt/rankings_data/weight_overrides.json):
{
  "overrides": [
    {
      "wrestler_id": "12345",
      "name": "John Smith",
      "team": "Oklahoma State",
      "date": "11/20/2025",
      "weight": "141",
      "matches_equivalent": 5
    },
    ...
  ]
}

Usage:
  Run the script and follow the interactive prompts:

      python scripts/rankings/manage_weight_overrides.py -season 2026

  The script will:
    - Prompt for a name fragment (case-insensitive, e.g. "Stan")
    - List all matching wrestlers
    - Let you pick one by number
    - Ask for a weight (e.g. 141)
    - Store a 5-match-equivalent override at today's date
    - Loop again for the next name fragment
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List
from datetime import date

from load_data import load_team_data


def search_wrestlers(teams: List[Dict], query: str) -> List[Dict]:
    """Return wrestlers whose names contain the query (case-insensitive)."""
    query_lower = query.lower()
    results: List[Dict] = []

    for team in teams:
        team_name = team.get("team_name", "Unknown")
        for wrestler in team.get("roster", []):
            wid = wrestler.get("season_wrestler_id")
            name = wrestler.get("name", "Unknown")
            if not wid or wid == "null":
                continue
            if query_lower in name.lower():
                results.append(
                    {
                        "wrestler_id": wid,
                        "name": name,
                        "team": team_name,
                        "weight_class": wrestler.get("weight_class", ""),
                    }
                )

    return results


def load_overrides(path: Path) -> Dict:
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"overrides": []}


def save_overrides(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def add_override(
    overrides_path: Path,
    wrestler_id: str,
    name: str,
    team: str,
    date: str,
    weight: str,
    matches_equivalent: int = 5,
) -> None:
    data = load_overrides(overrides_path)
    overrides = data.setdefault("overrides", [])

    overrides.append(
        {
            "wrestler_id": wrestler_id,
            "name": name,
            "team": team,
            "date": date,
            "weight": weight,
            "matches_equivalent": matches_equivalent,
        }
    )

    save_overrides(overrides_path, data)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Interactively search wrestlers and add manual weight overrides."
    )
    parser.add_argument(
        "-season",
        type=int,
        required=True,
        help="Season year (e.g., 2026)",
    )
    parser.add_argument(
        "--matches",
        type=int,
        default=5,
        help="Matches-equivalent weight (default: 5)",
    )

    args = parser.parse_args()

    overrides_path = Path("mt/rankings_data") / "weight_overrides.json"

    # Load all teams once for faster interactive searching
    teams = load_team_data(args.season)

    print(
        f"Interactive weight override tool for season {args.season}.\n"
        "Enter a name fragment to search (case-insensitive), or just press "
        "Enter to quit.\n"
    )

    while True:
        try:
            query = input("Name fragment (blank to quit): ").strip()
        except EOFError:
            break

        if not query:
            break

        results = search_wrestlers(teams, query)
        if not results:
            print("  No wrestlers found matching that fragment.\n")
            continue

        print(f"Found {len(results)} wrestlers:")
        for idx, r in enumerate(results, start=1):
            print(
                f"  {idx:>2}) ID={r['wrestler_id']}  "
                f"{r['name']} ({r['team']}), "
                f"listed weight={r['weight_class']}"
            )

        while True:
            sel = input(
                "Select wrestler number for override "
                "(blank to cancel this search): "
            ).strip()
            if not sel:
                print("  Search cancelled.\n")
                break
            try:
                idx = int(sel)
                if 1 <= idx <= len(results):
                    chosen = results[idx - 1]
                    break
            except ValueError:
                pass
            print("  Invalid selection, please enter a valid number.")

        if not sel:
            continue

        weight = input("Enter override weight (e.g., 141): ").strip()
        if not weight:
            print("  No weight entered; override not added.\n")
            continue

        today_str = date.today().strftime("%m/%d/%Y")
        add_override(
            overrides_path=overrides_path,
            wrestler_id=chosen["wrestler_id"],
            name=chosen["name"],
            team=chosen["team"],
            date=today_str,
            weight=weight,
            matches_equivalent=args.matches,
        )
        print(
            f"  Added override: {chosen['name']} ({chosen['team']}), "
            f"ID={chosen['wrestler_id']}, weight={weight}, date={today_str}, "
            f"matches_equivalent={args.matches}\n"
        )


if __name__ == "__main__":
    main()


