#!/usr/bin/env python3
"""
Builds the NCAA career -> season wrestler_id lookup the MatSavant Compare tool
(frontend/wrestledata-ui/public/tools/compare.html) reads in the browser.

Why it exists: NCAA wrestler profiles are per season, keyed by a TrackWrestling
wrestler_id that changes every season, and their match_list rows carry
opponent_career_id = null (build_wrestler_profiles.py has no NCAA career lookup).
So from the frontend alone there's no way to (a) find every season of a picked
wrestler or (b) tell that an opponent faced in 2024 and in 2026 is one person.
This file inverts to wrestler_id -> (career, season) client-side and answers both.

Source: the backend career files data/careers/ncaa_men/career_*.json (the same
career links the rest of the NCAA pipeline uses). Only season ids whose profile
frontend/wrestledata-ui/public/data/wrestlers/{season}/by_id/{id}.json is tracked
in git are written (tracked = deployed; untracked local profiles aren't live yet),
so the page never fetches a missing file. Commit new profiles before re-running.

Output: frontend/wrestledata-ui/public/data/careers/career_seasons.json
    {"generated": "YYYY-MM-DD", "careers": {"1": {"2023": "20134439132", ...}, ...}}
    Keys are career numbers without the "career_" prefix / zero padding (size).

Re-run after career linking or after a new season's profiles are built:
    .venv/bin/python scripts/reports/build_career_seasons.py
"""

import datetime
import json
import subprocess
from pathlib import Path

CAREERS_DIR = Path("data/careers/ncaa_men")
PROFILES_DIR = Path("frontend/wrestledata-ui/public/data/wrestlers")
OUTPUT_PATH = Path("frontend/wrestledata-ui/public/data/careers/career_seasons.json")


def tracked_profiles():
    out = subprocess.run(["git", "ls-files", str(PROFILES_DIR)],
                         capture_output=True, text=True, check=True).stdout
    return set(out.splitlines())


def main():
    published = tracked_profiles()
    careers = {}
    total_ids = missing = 0
    for path in sorted(CAREERS_DIR.glob("career_*.json")):
        data = json.loads(path.read_text())
        num = str(int(data["career_id"].split("_")[1]))
        seasons = {}
        for season, wid in (data.get("seasons") or {}).items():
            if not wid or not str(season).isdigit():
                continue
            total_ids += 1
            if f"{PROFILES_DIR}/{season}/by_id/{wid}.json" not in published:
                missing += 1
                continue
            seasons[str(season)] = str(wid)
        if seasons:
            careers[num] = dict(sorted(seasons.items()))

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out = {"generated": datetime.date.today().isoformat(), "careers": careers}
    OUTPUT_PATH.write_text(json.dumps(out, separators=(",", ":")))
    print(f"{len(careers)} careers, {total_ids - missing} season ids written "
          f"({missing} skipped: no committed profile) -> {OUTPUT_PATH} "
          f"({OUTPUT_PATH.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
