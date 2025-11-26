#!/usr/bin/env python3
"""
Manage placement notes (previous-year finishes) for wrestlers.

These notes are purely cosmetic and are displayed next to the
record in the HTML ranking matrix, e.g.:

    Brendan McCrone (Ohio State) - 7-0 (FR)

Allowed notes:
    - FR  (Freshman / first year)
    - 1-8 (NCAA placement)
    - BR  (Blood Round)
    - Q   (Qualifier)

File format (mt/rankings_data/placement_notes.json):
{
  "notes": [
    {
      "wrestler_id": "12345",
      "name": "John Smith",
      "team": "Oklahoma State",
      "note": "FR"
    },
    ...
  ]
}

Usage:
  Run the script and follow the interactive prompts:

      python scripts/rankings/manage_placement_notes.py -season 2026

  The script will:
    - Prompt for a name fragment (case-insensitive, e.g. "Volk")
    - List all matching wrestlers from the rosters
    - Let you pick one by number
    - Ask for a placement note (FR, 1-8, BR, Q)
    - Save/update that note in placement_notes.json
    - Loop again for the next name fragment
"""

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Dict, List

from load_data import load_team_data


ALLOWED_NOTES = {"FR", "1", "2", "3", "4", "5", "6", "7", "8", "BR", "Q"}


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


def load_notes(path: Path) -> Dict:
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"notes": []}


def save_notes(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def set_note(
    notes_path: Path,
    wrestler_id: str,
    name: str,
    team: str,
    note: str,
) -> None:
    """Insert or update a placement note for a wrestler."""
    data = load_notes(notes_path)
    notes = data.setdefault("notes", [])

    updated = False
    for entry in notes:
        if entry.get("wrestler_id") == wrestler_id:
            entry["note"] = note
            entry["name"] = name
            entry["team"] = team
            updated = True
            break

    if not updated:
        notes.append(
            {
                "wrestler_id": wrestler_id,
                "name": name,
                "team": team,
                "note": note,
            }
        )

    save_notes(notes_path, data)


def build_note_lookup(data: Dict) -> Dict[str, str]:
    """Return wrestler_id -> note mapping from raw notes data."""
    lookup: Dict[str, str] = {}
    for entry in data.get("notes", []):
        wid = entry.get("wrestler_id")
        note = str(entry.get("note", "")).strip().upper()
        if wid and note:
            lookup[wid] = note
    return lookup


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Interactively add/edit placement notes for wrestlers."
    )
    parser.add_argument(
        "-season",
        type=int,
        required=True,
        help="Season year (e.g., 2026)",
    )

    args = parser.parse_args()

    notes_path = Path("mt/rankings_data") / "placement_notes.json"

    # Load all teams once for faster interactive searching
    teams = load_team_data(args.season)

    # Preload existing notes for reference
    existing_data = load_notes(notes_path)
    note_lookup = build_note_lookup(existing_data)

    print(
        f"Interactive placement note tool for season {args.season}.\n"
        "Enter a name fragment to search (case-insensitive), or just press "
        "Enter to quit.\n"
        "Allowed notes: FR, 1-8, BR, Q\n"
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
            wid = r["wrestler_id"]
            existing_note = note_lookup.get(wid, "")
            note_str = f"  [current note: {existing_note}]" if existing_note else ""
            print(
                f"  {idx:>2}) ID={wid}  "
                f"{r['name']} ({r['team']}), "
                f"listed weight={r['weight_class']}{note_str}"
            )

        while True:
            sel = input(
                "Select wrestler number to edit placement note "
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

        while True:
            note_input = input(
                "Enter placement note (FR, 1-8, BR, Q), or blank to cancel: "
            ).strip().upper()
            if not note_input:
                print("  No note entered; no changes made.\n")
                note = ""
                break
            if note_input in ALLOWED_NOTES:
                note = note_input
                break
            print("  Invalid note. Allowed values are: FR, 1-8, BR, Q.")

        if not note:
            continue

        set_note(
            notes_path=notes_path,
            wrestler_id=chosen["wrestler_id"],
            name=chosen["name"],
            team=chosen["team"],
            note=note,
        )

        # Update in-memory lookup so we show the new note in subsequent searches
        note_lookup[chosen["wrestler_id"]] = note

        today_str = date.today().strftime("%m/%d/%Y")
        print(
            f"  Set placement note for {chosen['name']} ({chosen['team']}), "
            f"ID={chosen['wrestler_id']}: {note}  [{today_str}]\n"
        )


if __name__ == "__main__":
    main()



