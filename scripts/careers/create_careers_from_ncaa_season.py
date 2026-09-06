#!/usr/bin/env python3
"""
Bootstrap NCAA careers from a single anchor season's TrackWrestling roster
data (mt/data/ncaa_men/{season}/*.json). One career per wrestler in that
season, same minimal schema as the HS career files (see
scripts/careers/create_careers_from_season.py) so downstream tooling
(merge_careers.py, build_career_profiles.py-style consumers) can be extended
the same way. Run once to bootstrap, then use link_ncaa_season.py for every
subsequent season.

Output: data/careers/ncaa_men/career_XXXXXX.json

Usage:
  python scripts/careers/create_careers_from_ncaa_season.py --season 2025
"""

import argparse
import json
import re
from pathlib import Path
from typing import Dict, Set

TW_DIR = Path("mt/data/ncaa_men")
OUTPUT_DIR = Path("data/careers/ncaa_men")


def normalize_name(name: str) -> str:
    if not name:
        return ""
    return re.sub(r"\s+", " ", name.lower().strip())


def generate_career_id(counter: int) -> str:
    return f"career_{counter:06d}"


def load_existing(output_dir: Path):
    existing_career_ids: Set[str] = set()
    existing_season_ids: Set[str] = set()
    for career_file in output_dir.glob("career_*.json"):
        career = json.loads(career_file.read_text())
        career_id = career.get("career_id")
        if career_id:
            existing_career_ids.add(career_id)
        for wid in career.get("seasons", {}).values():
            if wid:
                existing_season_ids.add(wid)
    return existing_career_ids, existing_season_ids


def main():
    parser = argparse.ArgumentParser(description="Bootstrap NCAA careers from one anchor season")
    parser.add_argument("--season", type=int, required=True, help="Anchor season year (e.g. 2025)")
    args = parser.parse_args()

    season_dir = TW_DIR / str(args.season)
    if not season_dir.exists():
        raise FileNotFoundError(f"No TW roster data for season {args.season}: {season_dir}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    existing_career_ids, existing_season_ids = load_existing(OUTPUT_DIR)
    print(f"Found {len(existing_career_ids)} existing careers, {len(existing_season_ids)} linked season_wrestler_ids")

    counter = len(existing_career_ids)
    created = 0
    skipped = 0

    for team_file in sorted(season_dir.glob("*.json")):
        team_data = json.loads(team_file.read_text())
        for wrestler in team_data.get("roster", []):
            wid = wrestler.get("season_wrestler_id")
            name = wrestler.get("name")
            if not wid or not name:
                continue
            if wid in existing_season_ids:
                skipped += 1
                continue

            counter += 1
            career_id = generate_career_id(counter)
            career = {
                "career_id": career_id,
                "canonical_name": name,
                "name_norm": normalize_name(name),
                "created_from_season": args.season,
                "seasons": {str(args.season): wid},
                "notes": None,
            }
            (OUTPUT_DIR / f"{career_id}.json").write_text(json.dumps(career, indent=2, ensure_ascii=False))
            existing_season_ids.add(wid)
            created += 1

    print(f"\nSeason {args.season}: {created} careers created, {skipped} already existed")
    print(f"Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
