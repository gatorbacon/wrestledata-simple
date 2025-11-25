#!/usr/bin/env python3
"""
Manage manual grade overrides for wrestlers.

These overrides are primarily used by `freshman_of_year.py` to correct
grade classifications (e.g., when a wrestler is incorrectly listed as
Fr. / RS Fr. in the scraped data).

File format (mt/rankings_data/grade_overrides.json):
{
  "overrides": [
    {
      "wrestler_id": "12345",
      "name": "John Smith",
      "team": "Oklahoma State",
      "grade": "So."
    },
    ...
  ]
}

Usage:
  python scripts/rankings/manage_grade_overrides.py -season 2026

Interactive flow:
  - Prompt for a name fragment (case-insensitive, e.g. "Facu")
  - List all matching wrestlers with ID / team / listed grade
  - Let you choose one by number
  - Prompt for an override grade string (e.g. "Fr.", "RS Fr.", "So.", "Jr.", "Sr.")
  - Store or update the override in grade_overrides.json
  - Loop for the next name fragment
"""

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Dict, List

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
                        "grade": wrestler.get("grade", ""),
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


def upsert_override(
    overrides_path: Path,
    wrestler_id: str,
    name: str,
    team: str,
    grade: str,
) -> None:
    """Insert or update a grade override for a wrestler."""
    data = load_overrides(overrides_path)
    overrides = data.setdefault("overrides", [])

    for ov in overrides:
        if ov.get("wrestler_id") == wrestler_id:
            ov["name"] = name
            ov["team"] = team
            ov["grade"] = grade
            break
    else:
        overrides.append(
            {
                "wrestler_id": wrestler_id,
                "name": name,
                "team": team,
                "grade": grade,
            }
        )

    save_overrides(overrides_path, data)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Interactively search wrestlers and add/update grade overrides."
    )
    parser.add_argument(
        "-season",
        type=int,
        required=True,
        help="Season year (e.g., 2026)",
    )

    args = parser.parse_args()

    overrides_path = Path("mt/rankings_data") / "grade_overrides.json"

    # Load all teams once for faster interactive searching
    teams = load_team_data(args.season)

    print(
        f"Interactive grade override tool for season {args.season}.\n"
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
                f"listed weight={r['weight_class']}, grade={r['grade']}"
            )

        chosen = None
        while True:
            sel = input(
                "Select wrestler number for grade override "
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

        if not chosen:
            continue

        print(
            "Enter new grade string (examples: 'Fr.', 'RS Fr.', 'So.', 'Jr.', 'Sr.').\n"
            "The value will be used as-is by downstream reports."
        )
        new_grade = input(
            f"Override grade for {chosen['name']} (current '{chosen.get('grade', '')}'): "
        ).strip()
        if not new_grade:
            print("  No grade entered; override not added.\n")
            continue

        upsert_override(
            overrides_path=overrides_path,
            wrestler_id=chosen["wrestler_id"],
            name=chosen["name"],
            team=chosen["team"],
            grade=new_grade,
        )
        today_str = date.today().strftime("%m/%d/%Y")
        print(
            f"  [{today_str}] Set grade override: {chosen['name']} ({chosen['team']}), "
            f"ID={chosen['wrestler_id']}, grade='{new_grade}'\n"
        )


if __name__ == "__main__":
    main()


