#!/usr/bin/env python3
"""
Build recruiting.json for the College Recruiting page.

Reads career profiles, groups active wrestlers into graduating classes,
computes state placement points, and merges commitment data.

Classes follow the site season in frontend/hs-ky-ui/public/hs_config.js
(siteSeason {season, phase}; docs/kentuckymat_preseason_rankings.md, "Recruiting"):
  - current classes: site season .. site season + 3 (2027-2030 for 2027)
  - plus last year's seniors as a "Graduated" class (2026 for 2027)
Wrestlers are placed by their grade in the stats season (last season during the
preseason). Rank: the published preseason rank in the preseason (blank outside
the top 40/24), otherwise the current rank. An "8th" placement (state place as an
8th grader) is shown, and counts toward ordering only for a class with no high
school seasons yet (the incoming freshmen).

Usage:
    python scripts/recruiting/build_recruiting_data.py --gender boys
    python scripts/recruiting/build_recruiting_data.py --gender girls
"""

import argparse
import json
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent

HS_CONFIG_JS = REPO_ROOT / "frontend/hs-ky-ui/public/hs_config.js"
MAX_PER_CLASS = 100

PLACEMENT_POINTS = {1: 20, 2: 16, 3: 12, 4: 10, 5: 8, 6: 6, 7: 4, 8: 3}
GRADE_LABELS = ["8th", "Fr", "So", "Jr", "Sr"]

# Recency multipliers: senior-year results count more, freshman results less
# (8th only counts for a class with no high school seasons yet; see build())
GRADE_WEIGHTS = {"8th": 0.60, "Fr": 0.75, "So": 0.90, "Jr": 1.10, "Sr": 1.75}

# Set by main() from hs_config.js (or --site-season/--phase)
SITE_SEASON: int = None
PRESEASON: bool = None
STATS_SEASON: int = None
GRAD_CLASSES: list = None
GRADUATED_CLASS: int = None

# Set by main() based on --gender
CAREERS_DIR: Path = None
WRESTLERS_INDEX: Path = None
COMMITMENTS_FILE: Path = None
OUTPUT_FILE: Path = None


def read_site_season():
    """(season, phase) from hs_config.js's siteSeason: { season: 2027, phase: 'preseason' }."""
    import re
    m = re.search(r"siteSeason:\s*\{\s*season:\s*(\d{4}),\s*phase:\s*'(\w+)'", HS_CONFIG_JS.read_text())
    if not m:
        raise SystemExit(f"Could not read siteSeason from {HS_CONFIG_JS}")
    return int(m.group(1)), m.group(2)


def set_season(site_season: int, phase: str) -> None:
    global SITE_SEASON, PRESEASON, STATS_SEASON, GRAD_CLASSES, GRADUATED_CLASS
    SITE_SEASON = site_season
    PRESEASON = phase == "preseason"
    STATS_SEASON = site_season - 1 if PRESEASON else site_season
    GRAD_CLASSES = [site_season + i for i in range(4)]
    GRADUATED_CLASS = site_season - 1


def grade_to_season(grad_class: int, grade_label: str) -> int:
    """Return the season year for a given grade label within a grad class."""
    offset = GRADE_LABELS.index(grade_label) - 1  # 8th=-1, Fr=0, So=1, Jr=2, Sr=3
    return grad_class - 3 + offset


def load_preseason_ranks(gender: str) -> dict:
    """wrestler_id (last-season ID) -> rank in the latest published preseason drop (top 40/24)."""
    base = REPO_ROOT / f"frontend/hs-ky-ui/public/data/rankings/{gender}/{SITE_SEASON}"
    index_file = base / "index.json"
    if not index_file.exists():
        print(f"  Warning: no {SITE_SEASON} rankings drop ({index_file}); ranks left blank")
        return {}
    drop = json.loads(index_file.read_text())["latest"]
    ranks = {}
    for f in (base / drop).glob("*.json"):
        if f.name == "meta.json":
            continue
        for w in json.loads(f.read_text()).get("wrestlers", []):
            ranks[str(w["wrestler_id"])] = w["rank"]
    return ranks


def load_rank_map() -> dict:
    """wrestler_id → current_rank from the wrestlers index of WRESTLERS_INDEX's season."""
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


def build(gender: str):
    global CAREERS_DIR, WRESTLERS_INDEX, COMMITMENTS_FILE, OUTPUT_FILE

    CAREERS_DIR = REPO_ROOT / f"frontend/hs-ky-ui/public/data/careers/{gender}"
    WRESTLERS_INDEX = REPO_ROOT / f"frontend/hs-ky-ui/public/data/wrestlers/{gender}/{STATS_SEASON}/index_wrestlers.json"
    COMMITMENTS_FILE = REPO_ROOT / f"data/recruiting/{gender}/commitments.json"
    OUTPUT_FILE = REPO_ROOT / f"frontend/hs-ky-ui/public/data/recruiting/{gender}/recruiting.json"

    if SITE_SEASON is None:  # imported (manage_commitments.py): use hs_config.js
        set_season(*read_site_season())

    print(f"Building recruiting data ({gender})...")

    commitments = load_commitments()
    season_rank = load_rank_map()  # STATS_SEASON current_rank (used for the graduated class)
    rank_by_wrestler_id = load_preseason_ranks(gender) if PRESEASON else season_rank
    print(f"  Site season {SITE_SEASON} ({'preseason' if PRESEASON else 'season'}), "
          f"grades from {STATS_SEASON}; classes {GRAD_CLASSES} + graduated {GRADUATED_CLASS}")
    print(f"  Loaded {len(commitments)} commitments")

    career_files = sorted(CAREERS_DIR.glob("career_*.json"))
    print(f"  Processing {len(career_files)} career profiles...")

    all_classes = GRAD_CLASSES + [GRADUATED_CLASS]
    classes: dict[int, list] = {gc: [] for gc in all_classes}

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

        # Wrestlers active in the stats season; in-season, last year's seniors too
        # (the graduated class has no stats-season entry once the new season starts)
        active = next((s for s in seasons if s.get("season") == STATS_SEASON), None)
        if not active and not PRESEASON:
            last = next((s for s in seasons if s.get("season") == GRADUATED_CLASS), None)
            if last and last.get("grade") == 12:
                active = last
        if not active:
            continue

        grade = active.get("grade")
        if grade is None:
            continue

        grad_class = active["season"] + (12 - grade)
        if grad_class not in classes:
            continue

        team = active.get("team", "")
        weight = active.get("weight_class")
        wrestler_id = str(active.get("wrestler_id", ""))
        if grad_class == GRADUATED_CLASS:
            rank = season_rank.get(wrestler_id) if active["season"] == STATS_SEASON else active.get("current_rank")
        else:
            rank = rank_by_wrestler_id.get(wrestler_id)

        # Build season lookup: year → state_place
        season_by_year = {s["season"]: s for s in seasons}

        # Build placements dict {8th/Fr/So/Jr/Sr: place_or_None}
        placements = {}
        total_points = 0
        # 8th-grade places only order a class that has no high school seasons yet
        count_8th = grade_to_season(grad_class, "Fr") > STATS_SEASON
        for label in GRADE_LABELS:
            yr = grade_to_season(grad_class, label)
            entry = season_by_year.get(yr)
            place = entry.get("state_place") if entry else None
            placements[label] = place
            if place and place in PLACEMENT_POINTS and (label != "8th" or count_8th):
                total_points += PLACEMENT_POINTS[place] * GRADE_WEIGHTS[label]

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
    for gc in all_classes:
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

        # Post-sort: within 3 spots, if two wrestlers share a weight class and
        # the lower-ranked one placed better at states this year, swap them.
        # Uses only the stats-season placement so injuries/absences don't
        # cause undeserved jumps from prior-year results.
        cur_label = next((lb for lb in GRADE_LABELS
                          if grade_to_season(gc, lb) == min(STATS_SEASON, gc)), None)
        SWAP_WINDOW = 3
        changed = True
        while changed:
            changed = False
            for i in range(len(entries)):
                for j in range(i + 1, min(i + SWAP_WINDOW + 1, len(entries))):
                    a, b = entries[i], entries[j]
                    if a.get("weight") != b.get("weight"):
                        continue
                    sa = (a.get("placements") or {}).get(cur_label) or 999
                    sb = (b.get("placements") or {}).get(cur_label) or 999
                    if sb < sa:
                        entries[i], entries[j] = entries[j], entries[i]
                        changed = True

        top = entries[:MAX_PER_CLASS]
        # Append any committed wrestlers beyond the top 100 that aren't already included
        top_ids = {e["career_id"] for e in top}
        bonus = [e for e in entries[MAX_PER_CLASS:] if e["committed_to"] and e["career_id"] not in top_ids]
        output_classes[str(gc)] = top + bonus

        placers = sum(1 for e in entries if e["total_points"] > 0)
        print(f"  Class of {gc}: {len(entries)} total, {placers} with state pts → top {len(top)} + {len(bonus)} bonus committed")

    output = {
        "generated_at": date.today().isoformat(),
        "site_season": SITE_SEASON,
        "phase": "preseason" if PRESEASON else "season",
        "stats_season": STATS_SEASON,
        "class_order": [str(gc) for gc in GRAD_CLASSES],
        "graduated_class": str(GRADUATED_CLASS),
        "classes": output_classes,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    total = sum(len(v) for v in output_classes.values())
    print(f"\nDone. {total} wrestlers written to {OUTPUT_FILE}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gender", choices=["boys", "girls"])
    parser.add_argument("--rebuild", action="store_true", help="Rebuild recruiting JSON without editing commitments")
    parser.add_argument("--site-season", type=int, help="Override hs_config.js siteSeason.season")
    parser.add_argument("--phase", choices=["preseason", "season"], help="Override hs_config.js siteSeason.phase")
    args = parser.parse_args()

    cfg_season, cfg_phase = read_site_season()
    set_season(args.site_season or cfg_season, args.phase or cfg_phase)

    if args.rebuild:
        for gender in (["boys", "girls"] if not args.gender else [args.gender]):
            build(gender)
    elif args.gender:
        build(args.gender)
    else:
        parser.error("--gender is required unless using --rebuild")


if __name__ == "__main__":
    main()
