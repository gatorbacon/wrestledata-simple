#!/usr/bin/env python3
"""
Add a wrestler to Injured Reserve (IR) for a season.

Interactive script: prompts for season, gender, and name (searches by string match).
IR date is set to the day you run the script.
IR status remains "active" until the wrestler wrestles a match after
the IR date, at which point the matrix generation will update status
to "cleared" for logging.
"""

import json
from datetime import date
from pathlib import Path

from rankings.ir_utils import load_ir_data, save_ir_data

IR_JSON_PATH = Path("mt/ir_injured_reserve.json")
DATA_DIR = Path("mt/rankings_data")
STATE = "ky"


def search_wrestlers(query: str, season: int, gender: str) -> list:
    """Search wrestlers by partial name match (case-insensitive)."""
    query_lower = query.lower()
    matches = []
    weight_dir = DATA_DIR / f"hs_{STATE}_{gender}" / str(season)

    if not weight_dir.exists():
        return matches

    for weight_file in weight_dir.glob("weight_class_*.json"):
        try:
            with weight_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            wrestlers = data.get("wrestlers", {})
            for wrestler_id, wrestler_info in wrestlers.items():
                name = wrestler_info.get("name", "")
                if query_lower in name.lower():
                    matches.append({
                        "id": wrestler_id,
                        "name": name,
                        "team": wrestler_info.get("team", "Unknown"),
                        "weight_class": wrestler_info.get("weight_class", ""),
                        "wins": wrestler_info.get("wins", 0),
                        "losses": wrestler_info.get("losses", 0),
                    })
        except Exception as e:
            print(f"Warning: Error reading {weight_file}: {e}")
            continue

    matches.sort(key=lambda x: x["name"])
    return matches


def main() -> None:
    print("Add wrestler to Injured Reserve (IR)")
    print("=" * 40)

    # Season
    while True:
        season_str = input("Season (e.g., 2026): ").strip()
        if not season_str:
            print("Please enter a season.")
            continue
        try:
            season = int(season_str)
            if season < 2000 or season > 2100:
                print("Please enter a valid season year.")
                continue
            break
        except ValueError:
            print("Please enter a number.")

    # Gender
    while True:
        gender = input("Gender (boys or girls): ").strip().lower()
        if gender in ("boys", "girls"):
            break
        print("Please enter 'boys' or 'girls'.")

    # Name search
    while True:
        name_query = input("Wrestler name (partial match): ").strip()
        if not name_query:
            print("Please enter a name.")
            continue

        matches = search_wrestlers(name_query, season, gender)
        if not matches:
            print(f"No wrestlers found matching '{name_query}' for {season} {gender}.")
            retry = input("Try another name? (y/n): ").strip().lower()
            if retry != "y":
                print("Cancelled.")
                return
            continue

        print(f"\nFound {len(matches)} wrestler(s):")
        print("-" * 70)
        for i, w in enumerate(matches, 1):
            record = f"{w['wins']}-{w['losses']}" if w.get("wins", 0) > 0 or w.get("losses", 0) > 0 else "N/A"
            print(f"  {i:2d}. {w['name']:30s} | {w['team']:22s} | {w['weight_class']:>4s} | {record:>6s}")
        print("-" * 70)

        choice = input(f"Select wrestler (1-{len(matches)}, or 'q' to cancel): ").strip()
        if choice.lower() == "q":
            print("Cancelled.")
            return
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(matches):
                wrestler = matches[idx]
                break
            print(f"Please enter a number between 1 and {len(matches)}.")
        except ValueError:
            print("Please enter a valid number or 'q'.")

    # Add to IR (date = today)
    ir_date = date.today().isoformat()
    data = load_ir_data(IR_JSON_PATH)
    season_key = str(season)
    if season_key not in data:
        data[season_key] = {}
    if gender not in data[season_key]:
        data[season_key][gender] = {}

    data[season_key][gender][str(wrestler["id"])] = {
        "name": wrestler["name"],
        "ir_date": ir_date,
        "status": "active",
    }
    save_ir_data(data, IR_JSON_PATH)
    print(f"\nAdded {wrestler['name']} ({wrestler['id']}) to IR for {season} {gender} as of {ir_date}")


if __name__ == "__main__":
    main()
