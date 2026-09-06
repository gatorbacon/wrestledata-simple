#!/usr/bin/env python3
"""
Write official-roster data (class_level/hometown/high_school/photo_url/
previous_school) onto
the matching wrestler entry in the raw mt/data/ncaa_men/{year}/{team}.json
roster files, using the join already built by
scripts/analysis/match_official_rosters_to_trackwrestling.py
(mt/data/roster_links/{team}/{season}.json).

This is additive only: "grade" already exists as a blank "" stub on every
roster entry (read straight through by scripts/rankings/load_data.py into
weight_class_*.json and from there into the wrestler profile "grade" field
with zero further code changes needed) -- this script is what actually fills
it in. hometown/high_school/photo_url/previous_school are new keys; scripts/rankings/
load_data.py and scripts/rankings/build_wrestler_profiles.py need a small
follow-up change to carry those three through to the published profile JSON
(not done by this script).

Usage:
  python scripts/enrichment/enrich_ncaa_rosters.py
  python scripts/enrichment/enrich_ncaa_rosters.py --team penn_state
  python scripts/enrichment/enrich_ncaa_rosters.py --dry-run
"""

import argparse
import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LINKS_DIR = PROJECT_ROOT / "mt" / "data" / "roster_links"
OFFICIAL_DIR = PROJECT_ROOT / "mt" / "data" / "official_rosters"
TW_DIR = PROJECT_ROOT / "mt" / "data" / "ncaa_men"


def normalize_name(name):
    if not name:
        return ""
    name = re.sub(r"[`´'‘’.]", "", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip().lower()


def load_official_players(team_slug, season):
    """Returns (by_id, by_name). Schools with no numeric player_id in their
    official-roster source (Wyoming, George Mason -- manually captured via
    webarchive/PDF, whose card markup has no extractable id) fall entirely
    into by_name -- match_official_rosters_to_trackwrestling.py's join
    already resolved these by name (confirmed: mt/data/roster_links/wyoming/
    *.json carries real season_wrestler_id/name pairs with player_id: null),
    but this script used to key ONLY on player_id, silently dropping every
    such school to 0 enriched wrestlers every season since `None` was never
    a real dict key any link could match. Keying by normalized name as a
    fallback fixes it without touching the roster_links schema."""
    path = OFFICIAL_DIR / team_slug / f"{season}.json"
    data = json.loads(path.read_text())
    by_id = {p["player_id"]: p for p in data["players"] if p.get("player_id") is not None}
    by_name = {normalize_name(p["name"]): p for p in data["players"] if p.get("name")}
    return by_id, by_name


def enrich_team_season(link_path, dry_run=False):
    link_data = json.loads(link_path.read_text())
    team_slug = link_data["team"]
    tw_team_name = link_data["tw_team_name"]
    year = link_data["year"]

    tw_path = TW_DIR / str(year) / f"{tw_team_name}.json"
    if not tw_path.exists():
        return None

    official_by_id, official_by_name = load_official_players(team_slug, link_data["season"])
    tw_data = json.loads(tw_path.read_text())
    roster_by_id = {w["season_wrestler_id"]: w for w in tw_data.get("roster", [])}

    updated = 0
    for link in link_data["links"]:
        wrestler = roster_by_id.get(link["season_wrestler_id"])
        official = official_by_id.get(link["player_id"])
        if official is None and link["player_id"] is None:
            official = official_by_name.get(normalize_name(link.get("name")))
        if wrestler is None or official is None:
            continue
        wrestler["grade"] = official.get("class_level") or ""
        wrestler["hometown"] = official.get("hometown")
        wrestler["high_school"] = official.get("high_school")
        wrestler["photo_url"] = official.get("photo_url")
        wrestler["previous_school"] = official.get("previous_school")
        updated += 1

    if updated and not dry_run:
        tw_path.write_text(json.dumps(tw_data, indent=2, ensure_ascii=False))

    return {"team": team_slug, "season": link_data["season"], "year": year, "updated": updated}


def main():
    parser = argparse.ArgumentParser(description="Enrich mt/data/ncaa_men roster entries with official-roster data")
    parser.add_argument("--team", default=None, help="Single team slug (default: all teams with a roster_links join)")
    parser.add_argument("--dry-run", action="store_true", help="Report only, don't write any files")
    args = parser.parse_args()

    team_dirs = [LINKS_DIR / args.team] if args.team else sorted(LINKS_DIR.iterdir())

    total_updated = 0
    per_team_year = {}
    for team_dir in team_dirs:
        if not team_dir.is_dir():
            continue
        for link_path in sorted(team_dir.glob("*.json")):
            result = enrich_team_season(link_path, dry_run=args.dry_run)
            if result is None:
                continue
            total_updated += result["updated"]
            key = (result["team"], result["year"])
            per_team_year[key] = per_team_year.get(key, 0) + result["updated"]

    for (team, year), n in sorted(per_team_year.items()):
        print(f"{team:<20} {year} -> {n} wrestlers enriched")

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}TOTAL: {total_updated} wrestler entries enriched across {len(per_team_year)} team-years")


if __name__ == "__main__":
    main()
