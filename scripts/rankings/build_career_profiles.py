#!/usr/bin/env python3
"""
Build career profile JSONs aggregating all seasons for each linked career.

Reads:
  data/careers/career_*.json   — career→{season: wrestler_id} mappings
  frontend/hs-ky-ui/public/data/wrestlers/{gender}/{season}/by_id/{wrestler_id}.json

Writes:
  frontend/hs-ky-ui/public/data/careers/{gender}/{career_id}.json

Usage:
    python scripts/rankings/build_career_profiles.py --gender boys
    python scripts/rankings/build_career_profiles.py --gender girls
"""

import argparse
import json
import re
from pathlib import Path


CAREERS_DIR = Path("data/careers")  # may be overridden in main() for girls
WRESTLERS_BASE = Path("frontend/hs-ky-ui/public/data/wrestlers")
OUTPUT_BASE = Path("frontend/hs-ky-ui/public/data/careers")
TEAMS_BASE = Path("frontend/hs-ky-ui/public/data/teams")


def slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r'[^a-z0-9\s]', '', slug)
    slug = re.sub(r'\s+', '_', slug)
    return re.sub(r'_+', '_', slug).strip('_')


def load_ky_team_slugs(gender: str) -> set:
    """Collect all known KY team slugs across all seasons."""
    slugs = set()
    teams_dir = TEAMS_BASE / gender
    if teams_dir.exists():
        for season_dir in teams_dir.iterdir():
            for f in season_dir.glob("*.json"):
                slugs.add(f.stem)
    return slugs


def load_career_files():
    return sorted(CAREERS_DIR.glob("career_*.json"))


def load_wrestler_profile(gender: str, season: int, wrestler_id: str):
    path = WRESTLERS_BASE / gender / str(season) / "by_id" / f"{wrestler_id}.json"
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def build_career_profile(career_data: dict, gender: str, ky_team_slugs: set) -> dict:
    career_id = career_data["career_id"]
    canonical_name = career_data.get("canonical_name", "")
    seasons_map = career_data.get("seasons", {})  # {season_str: wrestler_id}

    season_profiles = []
    total_wins = 0
    total_losses = 0

    # Process seasons newest → oldest
    for season_str in sorted(seasons_map.keys(), reverse=True):
        season = int(season_str)
        wrestler_id = seasons_map[season_str]

        profile = load_wrestler_profile(gender, season, wrestler_id)
        if profile is None:
            print(f"  ⚠ No profile for {career_id} season {season} ({wrestler_id}) — skipping")
            continue

        record = profile.get("record", {})
        if isinstance(record, dict):
            record_str = record.get("overall", "0-0")
        else:
            record_str = record or "0-0"

        wins, losses = 0, 0
        if "-" in record_str:
            parts = record_str.split("-")
            try:
                wins = int(parts[0])
                losses = int(parts[1])
            except (ValueError, IndexError):
                pass

        total_wins += wins
        total_losses += losses

        # Add season field and opponent_ky flag to each match
        matches = profile.get("match_list") or profile.get("matches", [])
        for m in matches:
            m["season"] = season
            oid = m.get("opponent_id", "")
            if oid.startswith("OUTSTATE_"):
                m["opponent_ky"] = False
            else:
                opp_team = m.get("opponent_team", "")
                m["opponent_ky"] = bool(opp_team and slugify(opp_team) in ky_team_slugs)

        # Pull season accomplishment placements from season_summary if available
        regional_place = None
        state_place = None
        grade = None
        season_summary = profile.get("season_summary") or []
        for summary_entry in season_summary:
            if summary_entry.get("season") == season:
                regional_place = summary_entry.get("regional_place")
                state_place = summary_entry.get("state_place")
                grade = summary_entry.get("grade")
                break

        season_entry = {
            "season": season,
            "wrestler_id": wrestler_id,
            "grade": grade,
            "team": profile.get("team_name") or profile.get("team"),
            "weight_class": profile.get("weight_class"),
            "record": record_str,
            "regional_place": regional_place,
            "state_place": state_place,
            "matches": matches,
        }
        season_profiles.append(season_entry)

    total_matches = total_wins + total_losses
    win_pct = round(total_wins / total_matches, 3) if total_matches > 0 else 0.0

    return {
        "career_id": career_id,
        "canonical_name": canonical_name,
        "career_record": {
            "wins": total_wins,
            "losses": total_losses,
            "win_pct": win_pct,
        },
        "seasons": season_profiles,
    }


def main():
    parser = argparse.ArgumentParser(description="Build career profile JSONs")
    parser.add_argument("--gender", required=True, choices=["boys", "girls"])
    args = parser.parse_args()

    gender = args.gender
    global CAREERS_DIR
    CAREERS_DIR = Path("data/careers") if gender == "boys" else Path("data/careers/girls")

    out_dir = OUTPUT_BASE / gender
    out_dir.mkdir(parents=True, exist_ok=True)

    ky_team_slugs = load_ky_team_slugs(gender)
    print(f"Loaded {len(ky_team_slugs)} KY team slugs")

    career_files = load_career_files()
    print(f"Found {len(career_files)} career files")

    built = 0
    skipped = 0

    for cf in career_files:
        with cf.open(encoding="utf-8") as f:
            career_data = json.load(f)

        seasons_map = career_data.get("seasons", {})
        if not seasons_map:
            skipped += 1
            continue

        career_id = career_data["career_id"]
        profile = build_career_profile(career_data, gender, ky_team_slugs)

        if not profile["seasons"]:
            skipped += 1
            continue

        out_path = out_dir / f"{career_id}.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2, ensure_ascii=False)

        built += 1

    print(f"\nDone. Built {built} career profiles → {out_dir}")
    if skipped:
        print(f"Skipped {skipped} careers with no season data")


if __name__ == "__main__":
    main()
