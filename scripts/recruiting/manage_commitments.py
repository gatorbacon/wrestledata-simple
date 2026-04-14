#!/usr/bin/env python3
"""
Manage college commitments for the Kentucky Mat recruiting page.

Interactively search for a wrestler by name, then add, update, or remove
their college commitment.

Usage:
    python scripts/recruiting/manage_commitments.py --gender boys
    python scripts/recruiting/manage_commitments.py --gender girls
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.recruiting.build_recruiting_data import build as build_recruiting

REPO_ROOT = Path(__file__).parent.parent.parent

CAREERS_DIR: Path = None
COMMITMENTS_FILE: Path = None
COLLEGES_FILE: Path = None

CURRENT_SEASON = 2026


def load_json(path: Path, default):
    if not path.exists():
        return default
    with open(path) as f:
        return json.load(f)


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    return re.sub(r"\s+", " ", s)


def search_careers(query: str) -> list[dict]:
    """Return career entries whose canonical_name fuzzy-matches query."""
    query_tokens = slugify(query).split()
    matches = []
    for cf in sorted(CAREERS_DIR.glob("career_*.json")):
        try:
            with cf.open() as f:
                career = json.load(f)
        except Exception:
            continue
        name = career.get("canonical_name", "")
        name_slug = slugify(name)
        # Require all query tokens to appear in the name
        if all(tok in name_slug for tok in query_tokens):
            seasons = career.get("seasons", [])
            active = next((s for s in seasons if s.get("season") == CURRENT_SEASON), None)
            if active:
                grade = active.get("grade")
                grad_class = (CURRENT_SEASON + (12 - grade)) if grade else None
                matches.append({
                    "career_id": career["career_id"],
                    "name": name,
                    "team": active.get("team", ""),
                    "weight": active.get("weight_class"),
                    "grade": grade,
                    "grad_class": grad_class,
                })
    return matches[:20]


def pick_from_list(items: list, label_fn) -> int | None:
    """Print numbered list, return 0-based index or None on cancel."""
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gender", required=True, choices=["boys", "girls"])
    args = parser.parse_args()
    gender = args.gender

    global CAREERS_DIR, COMMITMENTS_FILE, COLLEGES_FILE
    CAREERS_DIR = REPO_ROOT / f"frontend/hs-ky-ui/public/data/careers/{gender}"
    COMMITMENTS_FILE = REPO_ROOT / f"data/recruiting/{gender}/commitments.json"
    COLLEGES_FILE = REPO_ROOT / f"data/recruiting/{gender}/colleges.json"

    print(f"=== Kentucky Mat — Commitment Manager ({gender}) ===\n")

    commitments = load_json(COMMITMENTS_FILE, {})
    colleges = load_json(COLLEGES_FILE, [])

    while True:
        query = input("Search for wrestler (or 'q' to quit): ").strip()
        if query.lower() in ("q", "quit", "exit"):
            break
        if len(query) < 2:
            print("  Enter at least 2 characters.\n")
            continue

        results = search_careers(query)
        if not results:
            print("  No active wrestlers found matching that name.\n")
            continue

        print(f"\n  Found {len(results)} match(es):")
        idx = pick_from_list(
            results,
            lambda r: (
                f"{r['name']}  |  {r['team']}  |  {r['weight']} lbs  |  "
                f"Gr {r['grade']}  (Class of {r['grad_class']})"
            ),
        )
        if idx is None:
            print()
            continue

        wrestler = results[idx]
        career_id = wrestler["career_id"]
        current = commitments.get(career_id)
        print(f"\n  Selected: {wrestler['name']} ({wrestler['team']}, Class of {wrestler['grad_class']})")
        if current:
            print(f"  Current commitment: {current}")
        else:
            print("  Currently: Uncommitted")

        print("\n  Options:")
        print("  1. Set / update commitment")
        if current:
            print("  2. Remove commitment")
        print("  0. Cancel")
        action = input("  Choice: ").strip()

        if action == "0":
            print()
            continue

        if action == "1":
            # Show existing colleges
            if colleges:
                print(f"\n  Known colleges ({len(colleges)}):")
                for i, col in enumerate(colleges):
                    print(f"    {i + 1}. {col}")
                print(f"    0. Enter new college name")
                raw = input("  Pick number or 0 for new: ").strip()
                if raw.isdigit() and 1 <= int(raw) <= len(colleges):
                    college = colleges[int(raw) - 1]
                else:
                    college = input("  College name: ").strip()
                    if not college:
                        print("  Cancelled.\n")
                        continue
                    if college not in colleges:
                        colleges.append(college)
                        colleges.sort()
                        save_json(COLLEGES_FILE, colleges)
                        print(f"  Added '{college}' to known colleges.")
            else:
                college = input("  College name: ").strip()
                if not college:
                    print("  Cancelled.\n")
                    continue
                colleges.append(college)
                colleges.sort()
                save_json(COLLEGES_FILE, colleges)

            commitments[career_id] = college
            save_json(COMMITMENTS_FILE, commitments)
            print(f"  ✓ {wrestler['name']} → {college}")
            build_recruiting(gender)

        elif action == "2" and current:
            del commitments[career_id]
            save_json(COMMITMENTS_FILE, commitments)
            print(f"  ✓ Removed commitment for {wrestler['name']}")
            build_recruiting(gender)

        else:
            print("  Cancelled.\n")

    print("\nDone.")


if __name__ == "__main__":
    main()
