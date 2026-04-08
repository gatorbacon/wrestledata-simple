#!/usr/bin/env python3
"""
Manage career record overrides for KentuckyMat.

When a career record doesn't match what a wrestler/coach reports (e.g. due to
missing data in TrackWrestling), this tool lets you store an override that will
be applied when building career profiles.

For active wrestlers: specify through_season — the override covers through that
season, and future seasons are added on top automatically.

For wrestlers whose career is over: leave through_season null — the override IS
the final record.

Usage:
    python scripts/careers/manage_career_record_overrides.py --gender boys
    python scripts/careers/manage_career_record_overrides.py --gender girls
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CURRENT_SEASON = 2026


def load_json(path, default):
    if not path.exists():
        return default
    with open(path) as f:
        return json.load(f)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def slugify(name):
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    return re.sub(r"\s+", " ", s)


def search_careers(query, careers_dir, frontend_dir):
    """Search backend career files; enrich with calculated record from frontend files."""
    query_tokens = slugify(query).split()
    results = []

    for cf in sorted(careers_dir.glob("career_*.json")):
        try:
            with cf.open() as f:
                career = json.load(f)
        except Exception:
            continue

        name = career.get("canonical_name", "")
        name_slug = slugify(name)
        if not all(tok in name_slug for tok in query_tokens):
            continue

        career_id = career["career_id"]
        seasons_map = career.get("seasons", {})
        latest_season = max((int(s) for s in seasons_map), default=None)

        team = ""
        weight = None
        current_record = None

        frontend_file = frontend_dir / f"{career_id}.json"
        if frontend_file.exists():
            try:
                with frontend_file.open() as f:
                    fp = json.load(f)
                cr = fp.get("career_record", {})
                current_record = f"{cr.get('wins', 0)}-{cr.get('losses', 0)}"
                seasons_arr = fp.get("seasons", [])
                if seasons_arr:
                    most_recent = seasons_arr[0]  # sorted newest first
                    team = most_recent.get("team") or ""
                    weight = most_recent.get("weight_class")
            except Exception:
                pass

        results.append({
            "career_id": career_id,
            "name": name,
            "team": team,
            "weight": weight,
            "latest_season": latest_season,
            "current_record": current_record,
        })

    return results[:20]


def pick_from_list(items, label_fn):
    for i, item in enumerate(items):
        print(f"  {i + 1}. {label_fn(item)}")
    print("  0. Cancel")
    while True:
        raw = input("  Choice: ").strip()
        if raw == "0":
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(items):
            return int(raw) - 1
        print("  Invalid choice.")


def prompt_int(prompt, min_val=0, max_val=9999):
    while True:
        raw = input(prompt).strip()
        if raw.isdigit() and min_val <= int(raw) <= max_val:
            return int(raw)
        print(f"  Please enter a number between {min_val} and {max_val}.")


def view_all_overrides(overrides, gender):
    if not overrides:
        print(f"\n  No overrides set for {gender}.\n")
        return
    print(f"\n  Career record overrides for {gender} ({len(overrides)}):")
    for career_id, ov in sorted(overrides.items()):
        through = ov.get("through_season")
        through_str = f"through {through}, future seasons added on top" if through else "FINAL"
        notes_str = f"  [{ov['notes']}]" if ov.get("notes") else ""
        print(f"    {career_id}: {ov['wins']}-{ov['losses']} ({through_str}){notes_str}  updated {ov.get('updated', '?')}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Manage career record overrides")
    parser.add_argument("--gender", required=True, choices=["boys", "girls"])
    args = parser.parse_args()
    gender = args.gender

    careers_dir = REPO_ROOT / "data/careers" if gender == "boys" else REPO_ROOT / "data/careers/girls"
    frontend_dir = REPO_ROOT / f"frontend/hs-ky-ui/public/data/careers/{gender}"
    overrides_file = REPO_ROOT / f"data/career_record_overrides/{gender}.json"

    overrides = load_json(overrides_file, {})

    print(f"=== Kentucky Mat — Career Record Override Manager ({gender}) ===\n")
    print(f"  Overrides file: {overrides_file.relative_to(REPO_ROOT)}")
    print(f"  Active overrides: {len(overrides)}\n")

    while True:
        query = input("Search for wrestler (or 'q' to quit, 'v' to view all): ").strip()

        if query.lower() in ("q", "quit", "exit"):
            break

        if query.lower() == "v":
            view_all_overrides(overrides, gender)
            continue

        if len(query) < 2:
            print("  Enter at least 2 characters.\n")
            continue

        results = search_careers(query, careers_dir, frontend_dir)
        if not results:
            print("  No careers found matching that name.\n")
            continue

        print(f"\n  Found {len(results)} match(es):")
        idx = pick_from_list(
            results,
            lambda r: (
                f"{r['name']}  |  {r['team'] or '—'}  |  "
                f"{r['weight'] or '?'} lbs  |  Latest season: {r['latest_season']}  |  "
                f"Calc record: {r['current_record'] or '?'}"
            ),
        )
        if idx is None:
            print()
            continue

        selected = results[idx]
        career_id = selected["career_id"]
        existing = overrides.get(career_id)

        print(f"\n  Selected: {selected['name']}  ({selected['team'] or '—'})")
        print(f"  Calculated record: {selected['current_record'] or 'unknown'}")
        if existing:
            through = existing.get("through_season")
            through_str = f"through season {through} (future seasons added on top)" if through else "FINAL (career over)"
            print(f"  Existing override: {existing['wins']}-{existing['losses']} ({through_str})")
            if existing.get("notes"):
                print(f"  Notes: {existing['notes']}")
        else:
            print("  No existing override.")

        print("\n  Options:")
        print("  1. Set / update override")
        if existing:
            print("  2. Remove override")
        print("  0. Cancel")
        action = input("  Choice: ").strip()

        if action == "0":
            print()
            continue

        elif action == "1":
            print()
            wins = prompt_int("  Correct wins: ")
            losses = prompt_int("  Correct losses: ")

            print()
            print("  Is this the wrestler's final career record (career is over)?")
            print("  1. Yes — career over, use this as the final record")
            print("  2. No — still active, this corrects through a past season")
            final_choice = input("  Choice: ").strip()

            through_season = None
            if final_choice == "2":
                print(f"\n  Through which season does this correction apply?")
                print(f"  (If active in {CURRENT_SEASON}, enter {CURRENT_SEASON - 1} to cover all prior seasons.)")
                through_season = prompt_int("  Season year: ", min_val=2013, max_val=CURRENT_SEASON)

            notes = input("\n  Notes (optional, press Enter to skip): ").strip()

            overrides[career_id] = {
                "wins": wins,
                "losses": losses,
                "through_season": through_season,
                "notes": notes or None,
                "updated": str(date.today()),
            }
            save_json(overrides_file, overrides)

            through_str = f"through season {through_season}" if through_season else "FINAL"
            print(f"\n  ✓ Saved: {selected['name']} — {wins}-{losses} ({through_str})\n")
            print("  Run build_career_profiles.py to apply to the site.\n")

        elif action == "2" and existing:
            confirm = input(f"  Remove override for {selected['name']}? (y/n): ").strip().lower()
            if confirm == "y":
                del overrides[career_id]
                save_json(overrides_file, overrides)
                print(f"  ✓ Override removed for {selected['name']}\n")
                print("  Run build_career_profiles.py to apply to the site.\n")
            else:
                print("  Cancelled.\n")

        else:
            print("  Invalid choice.\n")

    print("\nDone.")


if __name__ == "__main__":
    main()
