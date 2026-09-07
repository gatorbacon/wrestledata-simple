#!/usr/bin/env python3
"""
Builds a single slug -> official abbreviation lookup (e.g. "penn_state":
"PSU") from every team's own profile file, so pages that need to abbreviate
many teams at once (the homepage dual ticker, the dual schedule page) don't
have to fetch 60+ individual team files client-side just to get one field
each already has.

Usage:
  python3 scripts/generate_team_abbreviations.py
"""
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEAMS_DIR = PROJECT_ROOT / "frontend" / "wrestledata-ui" / "public" / "data" / "teams"
OUT_PATH = TEAMS_DIR / "abbreviations.json"


def main():
    out = {}
    for f in sorted(TEAMS_DIR.glob("*.json")):
        if f.name == "abbreviations.json":
            continue
        team = json.loads(f.read_text())
        slug = f.stem
        abbr = team.get("abbreviation")
        if abbr:
            out[slug] = abbr

    OUT_PATH.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {len(out)} team abbreviations to {OUT_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
