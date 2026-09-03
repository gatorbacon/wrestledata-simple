#!/usr/bin/env python3
"""
Publishes team_score_simulation_adjusted_{date}.json outputs into MatSavant's
static frontend data directory, in the site's established pre-built-JSON
pattern (frontend/wrestledata-ui/public/data/{category}/{season}/...).

Writes:
  frontend/wrestledata-ui/public/data/team_odds/{season}/{date}.json  (one per date)
  frontend/wrestledata-ui/public/data/team_odds/{season}/index.json  ({"dates": [...]})

The site is 100% static (no backend), so a browser can't glob a folder --
index.json is what team_odds.js fetches first to know which per-date files
exist, then fetches each on demand.

Usage:
  python scripts/analysis/publish_team_odds_to_site.py
"""

import json
import re
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
COMBINED_DIR = PROJECT_ROOT / "data" / "ncaa-tourney-parsed"
SITE_DATA_DIR = PROJECT_ROOT / "frontend" / "wrestledata-ui" / "public" / "data" / "team_odds"


def main():
    by_season: dict[int, list[str]] = {}

    for path in sorted(COMBINED_DIR.glob("team_score_simulation_adjusted_*.json")):
        m = re.match(r"team_score_simulation_adjusted_(\d{4}-\d{2}-\d{2})\.json$", path.name)
        if not m:
            continue
        date = m.group(1)
        data = json.loads(path.read_text())
        season = data["teams"][0].get("season") if data["teams"] else None
        # season isn't stored per-team; derive from the rankings_file's tourney_year instead
        rankings_file = Path(data["rankings_file"])
        rankings_data = json.loads(rankings_file.read_text())
        season = rankings_data["season"]

        out_dir = SITE_DATA_DIR / str(season)
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / f"{date}.json"
        shutil.copy(path, dest)
        by_season.setdefault(season, []).append(date)
        print(f"  published {dest.relative_to(PROJECT_ROOT)}")

    for season, dates in by_season.items():
        dates_sorted = sorted(set(dates), reverse=True)
        index_path = SITE_DATA_DIR / str(season) / "index.json"
        index_path.write_text(json.dumps({"season": season, "dates": dates_sorted}, indent=2))
        print(f"  wrote {index_path.relative_to(PROJECT_ROOT)}: {dates_sorted}")


if __name__ == "__main__":
    main()
