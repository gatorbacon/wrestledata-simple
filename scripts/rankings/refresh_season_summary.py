#!/usr/bin/env python3
"""
Patch `season_summary` on already-published NCAA wrestler profiles WITHOUT
redoing the full profile build (TPAR, rank, bonus, etc.) for every wrestler
in a season.

Why this exists: `season_summary` (the array driving the profile page's
season-selector table) is baked into each season's own published JSON at
build time -- it's not looked up dynamically when the page loads. So linking
a new season into an existing multi-season career leaves every OTHER already-
published season's file holding a stale summary (missing the just-added row)
until something rewrites it. Re-running `build_wrestler_profiles.py -season X`
for every affected season works, but it recomputes everything for every
wrestler in that season just to fix a field that changed for a small subset
of them -- expensive, and it compounds every time you backfill one season
further back (link 2015, refresh 2015-2026; link 2014 next, refresh
2014-2026 again). This script does only the cheap part: recompute the
lookup once, then patch just the `season_summary` key on whichever profile
files it actually touches.

Only the NEWLY backfilled season needs a full `build_wrestler_profiles.py`
run (it needs TPAR/rank computed for the first time). Every other season
sharing a career with it just needs this.

Usage:
  .venv/bin/python scripts/rankings/refresh_season_summary.py
  .venv/bin/python scripts/rankings/refresh_season_summary.py --dry-run
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_wrestler_profiles import build_ncaa_season_summary_lookup

WRESTLERS_DIR = Path("frontend/wrestledata-ui/public/data/wrestlers")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Report what would change without writing")
    args = ap.parse_args()

    print("Building season_summary lookup from career files...")
    lookup = build_ncaa_season_summary_lookup()
    print(f"  {len(lookup)} wrestler_ids covered across every multi-season career")

    patched = unchanged = missing = 0
    seasons_touched = set()

    for wid, summary in lookup.items():
        # Which season does this wid belong to? It's whichever entry in its
        # own summary has this exact wid.
        own = next((s for s in summary if s["wrestler_id"] == wid), None)
        if not own:
            continue
        season = str(own["season"])
        by_id_path = WRESTLERS_DIR / season / "by_id" / f"{wid}.json"
        if not by_id_path.exists():
            missing += 1
            continue

        with by_id_path.open("r", encoding="utf-8") as f:
            profile = json.load(f)

        if profile.get("season_summary") == summary:
            unchanged += 1
            continue

        profile["season_summary"] = summary
        seasons_touched.add(season)

        if not args.dry_run:
            with by_id_path.open("w", encoding="utf-8") as f:
                json.dump(profile, f, indent=2, ensure_ascii=False)

            team_slug = profile.get("team_slug")
            if team_slug:
                by_team_path = WRESTLERS_DIR / season / "by_team" / team_slug / f"{wid}.json"
                if by_team_path.exists():
                    with by_team_path.open("w", encoding="utf-8") as f:
                        json.dump(profile, f, indent=2, ensure_ascii=False)

        patched += 1

    verb = "Would patch" if args.dry_run else "Patched"
    print(f"\n{verb} {patched} profiles, {unchanged} already up to date, {missing} skipped (no published file for that season)")
    if seasons_touched:
        print(f"Seasons touched: {sorted(seasons_touched, reverse=True)}")


if __name__ == "__main__":
    main()
