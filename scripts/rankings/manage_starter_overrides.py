#!/usr/bin/env python3
"""
Interactive tool to manage global starter overrides (force backups) by name.

Behavior:
- You specify a season.
- The script loads all rankings_{weight}.json files under
  mt/rankings_data/{season}/.
- You search by a name fragment (e.g. "Nate Des"), pick a wrestler, and
  toggle whether they are *forced* to be treated as a backup.

Overrides are stored per season in:
  mt/rankings_data/{season}/starter_overrides.json

Format:
  {
    "season": 2026,
    "force_backup_ids": ["34941775132", ...]
  }

Any code that respects these overrides should:
  - Never treat a force-backup ID as a starter.
  - When choosing a starter per team/weight, pick the best-ranked
    wrestler NOT in force_backup_ids.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List


def load_all_ranked_wrestlers(season: int, data_dir: str) -> List[Dict]:
    """
    Load all rankings_{weight}.json files for a season and flatten into
    a list of {wrestler_id, name, team, weight_class, rank}.
    """
    base = Path(data_dir) / str(season)
    if not base.exists():
        raise FileNotFoundError(f"Rankings directory not found for season {season}: {base}")

    entries: List[Dict] = []
    for path in sorted(base.glob("rankings_*.json")):
        weight = path.stem.replace("rankings_", "")
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Warning: could not read {path}: {e}")
            continue
        for entry in data.get("rankings", []):
            wid = entry.get("wrestler_id")
            name = entry.get("name")
            team = entry.get("team")
            rank = entry.get("rank")
            if not wid or not name:
                continue
            try:
                r_int = int(rank)
            except (TypeError, ValueError):
                r_int = 10**9
            entries.append(
                {
                    "wrestler_id": wid,
                    "name": name,
                    "team": team or "",
                    "weight_class": weight,
                    "rank": r_int,
                }
            )
    return entries


def load_overrides(season: int, data_dir: str) -> Dict:
    base = Path(data_dir) / str(season)
    path = base / "starter_overrides.json"
    if not path.exists():
        return {"season": season, "force_backup_ids": []}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("force_backup_ids", [])
    return data


def save_overrides(season: int, data_dir: str, overrides: Dict) -> None:
    base = Path(data_dir) / str(season)
    base.mkdir(parents=True, exist_ok=True)
    path = base / "starter_overrides.json"
    overrides["season"] = season
    with path.open("w", encoding="utf-8") as f:
        json.dump(overrides, f, indent=2)
    print(f"Saved overrides to {path}")


def interactive_manage_overrides(season: int, data_dir: str) -> None:
    entries = load_all_ranked_wrestlers(season, data_dir)
    if not entries:
        print(f"No ranked wrestlers found for season {season} in {data_dir}.")
        return

    overrides = load_overrides(season, data_dir)
    force_backup_ids = set(overrides.get("force_backup_ids", []))

    print(
        f"\nLoaded {len(entries)} ranked wrestlers for season {season}. "
        f"{len(force_backup_ids)} wrestler(s) currently forced as backups.\n"
    )

    while True:
        frag = input(
            "Enter name fragment to search (or press Enter to quit, 'list' to show all overrides): "
        ).strip()
        if not frag:
            break
        if frag.lower() == "list":
            if not force_backup_ids:
                print("No forced backups set.")
                continue
            print("\nForced backup wrestlers:")
            for e in entries:
                if e["wrestler_id"] in force_backup_ids:
                    print(
                        f"  {e['name']} — {e['team']} — {e['weight_class']} lbs — "
                        f"rank #{e['rank']} — id={e['wrestler_id']}"
                    )
            print()
            continue

        frag_lower = frag.lower()
        matches = [
            e
            for e in entries
            if frag_lower in e["name"].lower()
        ]
        if not matches:
            print("No wrestlers found with that fragment.")
            continue

        # Sort matches by name, then weight, then rank
        matches.sort(key=lambda e: (e["name"], int(e["weight_class"]), e["rank"]))

        print(f"\nMatches for '{frag}':")
        for idx, e in enumerate(matches, start=1):
            is_forced = e["wrestler_id"] in force_backup_ids
            mark = "[B]" if is_forced else "   "
            print(
                f"{idx:3d}. {mark} {e['name']} — {e['team']} — "
                f"{e['weight_class']} lbs — rank #{e['rank']} — id={e['wrestler_id']}"
            )

        pick = input(
            "\nEnter number to toggle backup status, or press Enter to cancel: "
        ).strip()
        if not pick:
            continue
        try:
            choice = int(pick)
        except ValueError:
            print("Invalid choice.")
            continue
        if not (1 <= choice <= len(matches)):
            print("Choice out of range.")
            continue

        sel = matches[choice - 1]
        wid = sel["wrestler_id"]
        if wid in force_backup_ids:
            force_backup_ids.remove(wid)
            print(f"\nRemoved forced-backup override for {sel['name']} ({wid}).\n")
        else:
            force_backup_ids.add(wid)
            print(f"\nAdded forced-backup override for {sel['name']} ({wid}).\n")

        overrides["force_backup_ids"] = sorted(force_backup_ids)
        save_overrides(season, data_dir, overrides)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage season-wide starter overrides (force certain wrestlers as backups)."
    )
    parser.add_argument(
        "-season",
        type=int,
        required=True,
        help="Season year (e.g., 2026).",
    )
    parser.add_argument(
        "-data-dir",
        default="mt/rankings_data",
        help="Base rankings directory containing rankings_*.json.",
    )

    args = parser.parse_args()
    interactive_manage_overrides(args.season, args.data_dir)


if __name__ == "__main__":
    main()



