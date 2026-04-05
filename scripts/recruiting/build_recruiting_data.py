#!/usr/bin/env python3
"""
Build recruiting.json for the College Recruiting page.

Reads boys career profiles, groups active wrestlers into graduating classes
(2026-2029), computes state placement points, and merges commitment data.

Usage:
    python scripts/recruiting/build_recruiting_data.py
"""

import json
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
CAREERS_DIR = REPO_ROOT / "frontend/hs-ky-ui/public/data/careers/boys"
WRESTLERS_INDEX = REPO_ROOT / "frontend/hs-ky-ui/public/data/wrestlers/boys/2026/index_wrestlers.json"
COMMITMENTS_FILE = REPO_ROOT / "data/recruiting/boys/commitments.json"
OUTPUT_FILE = REPO_ROOT / "frontend/hs-ky-ui/public/data/recruiting/boys/recruiting.json"

CURRENT_SEASON = 2026
GRAD_CLASSES = [2026, 2027, 2028, 2029]
MAX_PER_CLASS = 100

PLACEMENT_POINTS = {1: 20, 2: 16, 3: 12, 4: 10, 5: 8, 6: 6, 7: 4, 8: 3}
GRADE_LABELS = ["Fr", "So", "Jr", "Sr"]


def grade_to_season(grad_class: int, grade_label: str) -> int:
    """Return the season year for a given grade label within a grad class."""
    offset = GRADE_LABELS.index(grade_label)  # Fr=0, So=1, Jr=2, Sr=3
    return grad_class - 3 + offset


def load_rank_map() -> dict:
    """career_id → current_rank from 2026 wrestlers index."""
    rank_map = {}
    if not WRESTLERS_INDEX.exists():
        print(f"  Warning: {WRESTLERS_INDEX} not found")
        return rank_map
    with open(WRESTLERS_INDEX) as f:
        wrestlers = json.load(f)
    # Index is by wrestler_id, not career_id; we'll match via career lookup
    for w in wrestlers:
        rank_map[str(w.get("wrestler_id", ""))] = w.get("current_rank")
    return rank_map


def load_commitments() -> dict:
    if not COMMITMENTS_FILE.exists():
        return {}
    with open(COMMITMENTS_FILE) as f:
        return json.load(f)


def main():
    print("Building recruiting data...")

    commitments = load_commitments()
    rank_by_wrestler_id = load_rank_map()
    print(f"  Loaded {len(commitments)} commitments")

    career_files = sorted(CAREERS_DIR.glob("career_*.json"))
    print(f"  Processing {len(career_files)} career profiles...")

    classes: dict[int, list] = {gc: [] for gc in GRAD_CLASSES}

    for cf in career_files:
        try:
            with cf.open() as f:
                career = json.load(f)
        except Exception:
            continue

        career_id = career.get("career_id", "")
        name = career.get("canonical_name", "")
        seasons = career.get("seasons", [])
        if not career_id or not name or not seasons:
            continue

        # Only care about wrestlers active in 2026
        active = next((s for s in seasons if s.get("season") == CURRENT_SEASON), None)
        if not active:
            continue

        grade = active.get("grade")
        if grade is None:
            continue

        grad_class = CURRENT_SEASON + (12 - grade)
        if grad_class not in GRAD_CLASSES:
            continue

        team = active.get("team", "")
        weight = active.get("weight_class")
        wrestler_id = str(active.get("wrestler_id", ""))
        rank = rank_by_wrestler_id.get(wrestler_id)

        # Build season lookup: year → state_place
        season_by_year = {s["season"]: s for s in seasons}

        # Build placements dict {Fr/So/Jr/Sr: place_or_None}
        placements = {}
        total_points = 0
        for label in GRADE_LABELS:
            yr = grade_to_season(grad_class, label)
            entry = season_by_year.get(yr)
            place = entry.get("state_place") if entry else None
            placements[label] = place
            if place and place in PLACEMENT_POINTS:
                total_points += PLACEMENT_POINTS[place]

        # Build team_slug from team name
        team_slug = team.lower().strip().replace(" ", "_").replace("-", "_")
        import re
        team_slug = re.sub(r"[^a-z0-9_]", "", team_slug)
        team_slug = re.sub(r"_+", "_", team_slug).strip("_")

        classes[grad_class].append({
            "career_id": career_id,
            "name": name,
            "weight": weight,
            "rank": rank,
            "team": team,
            "team_slug": team_slug,
            "placements": placements,
            "total_points": total_points,
            "committed_to": commitments.get(career_id),
        })

    # Sort and trim each class
    output_classes = {}
    for gc in GRAD_CLASSES:
        entries = classes[gc]

        def sort_key(e):
            # 1. Has state points → sort by points desc, then rank asc
            # 2. No points but ranked → sort by rank asc
            # 3. No points, unranked → last
            pts = e["total_points"]
            rank = e["rank"]
            if pts > 0:
                tier = 0
                rank_val = rank if rank else 9999
                return (tier, -pts, rank_val)
            elif rank is not None:
                return (1, 0, rank)
            else:
                return (2, 0, 9999)

        entries.sort(key=sort_key)

        # Post-sort: for adjacent same-weight wrestlers, give priority to the one
        # with a better most-recent-year state placement (bubble-sort one pass).
        changed = True
        while changed:
            changed = False
            for i in range(len(entries) - 1):
                a, b = entries[i], entries[i + 1]
                if a.get("weight") != b.get("weight"):
                    continue
                # Find most recent placement for each
                def most_recent_place(e):
                    for label in reversed(GRADE_LABELS):
                        p = (e.get("placements") or {}).get(label)
                        if p is not None:
                            return p
                    return None
                pa = most_recent_place(a)
                pb = most_recent_place(b)
                if pa is None and pb is None:
                    continue
                if pb is not None and (pa is None or pb < pa):
                    entries[i], entries[i + 1] = entries[i + 1], entries[i]
                    changed = True

        output_classes[str(gc)] = entries[:MAX_PER_CLASS]

        placers = sum(1 for e in entries if e["total_points"] > 0)
        print(f"  Class of {gc}: {len(entries)} total, {placers} with state pts → trimmed to {len(output_classes[str(gc)])}")

    output = {
        "generated_at": date.today().isoformat(),
        "current_season": CURRENT_SEASON,
        "classes": output_classes,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    total = sum(len(v) for v in output_classes.values())
    print(f"\nDone. {total} wrestlers written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
