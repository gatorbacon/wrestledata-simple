#!/usr/bin/env python3
"""
Publishes team_score_simulation_adjusted_{source}_{date}.json outputs into
MatSavant's static frontend data directory, in the site's established
pre-built-JSON pattern (frontend/wrestledata-ui/public/data/{category}/{season}/...).

Writes, per ranking source (FloWrestling stays at the un-prefixed path for
backward compatibility -- it was the only source before InterMat was added;
every other source gets its own slug subfolder):
  frontend/wrestledata-ui/public/data/team_odds/{season}/{date}.json                    (Flo, one per date)
  frontend/wrestledata-ui/public/data/team_odds/{season}/index.json                     (Flo dates)
  frontend/wrestledata-ui/public/data/team_odds/{season}/{slug}/{date}.json             (other sources, e.g. "intermat")
  frontend/wrestledata-ui/public/data/team_odds/{season}/{slug}/index.json

The site is 100% static (no backend), so a browser can't glob a folder --
each source's own index.json is what team_odds.js fetches first to know
which per-date files exist for that source, then fetches each on demand.

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

# source_slug (see simulate_team_scores.py's SOURCE_SLUGS) -> subfolder under
# team_odds/{season}/. Flo publishes at the season root with no subfolder --
# it's the original/default source and this keeps every existing published
# URL and frontend fetch path unchanged. Any other source gets its own
# slug-named subfolder so it can never collide with Flo's files.
SOURCE_SUBDIR = {
    "flo": "",
    "intermat": "intermat",
}


def main():
    # season -> slug -> [dates]
    by_season_source: dict[int, dict[str, list[str]]] = {}

    for path in sorted(COMBINED_DIR.glob("team_score_simulation_adjusted_*.json")):
        m = re.match(r"team_score_simulation_adjusted_([a-z0-9]+)_(\d{4}-\d{2}-\d{2})\.json$", path.name)
        if not m:
            continue
        slug, date = m.group(1), m.group(2)
        data = json.loads(path.read_text())
        # season isn't stored per-team; derive from the rankings_file's tourney_year instead
        rankings_file = Path(data["rankings_file"])
        rankings_data = json.loads(rankings_file.read_text())
        season = rankings_data["season"]

        subdir = SOURCE_SUBDIR.get(slug)
        if subdir is None:
            print(f"  WARNING: no SOURCE_SUBDIR entry for source slug '{slug}' ({path.name}) -- skipping. Add it to SOURCE_SUBDIR.")
            continue

        out_dir = SITE_DATA_DIR / str(season) / subdir if subdir else SITE_DATA_DIR / str(season)
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / f"{date}.json"
        shutil.copy(path, dest)
        by_season_source.setdefault(season, {}).setdefault(slug, []).append(date)
        print(f"  published {dest.relative_to(PROJECT_ROOT)}")

    for season, by_slug in by_season_source.items():
        for slug, dates in by_slug.items():
            subdir = SOURCE_SUBDIR[slug]
            dates_sorted = sorted(set(dates), reverse=True)
            index_dir = SITE_DATA_DIR / str(season) / subdir if subdir else SITE_DATA_DIR / str(season)
            index_path = index_dir / "index.json"
            index_path.write_text(json.dumps({"season": season, "source": slug, "dates": dates_sorted}, indent=2))
            print(f"  wrote {index_path.relative_to(PROJECT_ROOT)}: {dates_sorted}")


if __name__ == "__main__":
    main()
