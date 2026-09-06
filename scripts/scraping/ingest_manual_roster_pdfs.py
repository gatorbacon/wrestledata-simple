#!/usr/bin/env python3
"""
Batch-ingest manually-captured roster PDFs (from the user's bulk URL->PDF
tool) for schools scrape_official_roster.py can't reach on its own -- Wyoming
(gowyo.com, JS-rendered) and Little Rock (lrtrojans.com, robots.txt-blocked)
so far. Parses each PDF with parse_manual_roster_pdf.py (auto-detects
Cards/Grid/List layout) and writes mt/data/official_rosters/{team}/{season}.json
in the same schema scrape_official_roster.py produces.

Expects PDFs in data/_tmp/ named "{season} Wrestling Roster - {School Name}.pdf"
(exactly how the user's bulk tool names its output) -- season as "2023-24" etc.

Usage:
  # Ingest every Wyoming + Little Rock PDF currently sitting in data/_tmp/
  .venv/bin/python scripts/scraping/ingest_manual_roster_pdfs.py

  # Add a new school (first time): give its team_roster_url pattern once here,
  # then future re-runs (new years dropped in data/_tmp/) need no code change.
"""
import glob
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from parse_manual_roster_pdf import parse_and_normalize, player_id_for

import json

TMP_DIR = Path("data/_tmp")
OUT_DIR = Path("mt/data/official_rosters")

# One entry per manually-captured school. `pdf_glob` matches this school's
# files in data/_tmp/; `list_style` disambiguates Sidearm's two different
# "List" layouts (see parse_manual_roster_pdf.py's module docstring) --
# 'wyoming' for the single-column 2-field-per-card version, 'two_col' for
# Little Rock's 2-column 3-line-per-card version. `url_template` matches
# each site's own URL pattern (used only for the team_roster_url metadata
# field, not fetched) with {season} substituted.
MANUAL_SCHOOLS = {
    "wyoming": {
        "pdf_glob": "*Wyoming*.pdf",
        "list_style": "wyoming",
        "url_template": "https://gowyo.com/sports/wrestling/roster/{season} (manual PDF - JS-rendered site)",
    },
    "little_rock": {
        "pdf_glob": "*Little Rock*.pdf",
        "list_style": "two_col",
        "url_template": "https://lrtrojans.com/sports/wrestling/roster/season/{season} (manual PDF - robots.txt blocked)",
    },
}

MIN_PLAYERS = 15  # below this, treat the capture as unreliable and skip rather than write bad data


def ingest_school(team_slug, cfg):
    print(f"=== {team_slug} ===")
    for pdf in sorted(glob.glob(str(TMP_DIR / cfg["pdf_glob"]))):
        m = re.search(r"(\d{4}-\d{2})", pdf)
        if not m:
            print(f"  WARNING: couldn't extract a season from filename: {pdf}")
            continue
        season_slug = m.group(1)
        try:
            players, view = parse_and_normalize(pdf, team_slug, cfg["list_style"])
        except Exception as e:
            print(f"  {season_slug}: FAILED to parse ({e}) -- {pdf}")
            continue

        print(f"  {season_slug}: [{view}] {len(players)} players -- {pdf}")
        if len(players) < MIN_PLAYERS:
            print(f"    WARNING: only {len(players)} players (unreliable capture) -- skipping, not writing. "
                  f"Consider asking for a re-capture in a different Roster View if this school offers one.")
            continue

        out_dir = OUT_DIR / team_slug
        out_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "season": season_slug,
            "team_roster_url": cfg["url_template"].format(season=season_slug),
            "players": players,
        }
        out_path = out_dir / f"{season_slug}.json"
        with out_path.open("w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"    wrote {out_path}")


def rekey_existing(team_slug, seasons):
    """Recompute player_id on already-existing files for a team using the
    SAME deterministic hash this module's parser uses, so seasons ingested
    in different sessions/batches still share stable (team, player_id)
    continuity for link_ncaa_season.py's tier-1 auto-link. No PDF needed --
    just rewrites the id on whatever's already on disk."""
    print(f"=== Re-keying existing {team_slug} files for ID consistency ===")
    for season_slug in seasons:
        path = OUT_DIR / team_slug / f"{season_slug}.json"
        if not path.exists():
            continue
        with path.open() as f:
            data = json.load(f)
        for p in data["players"]:
            p["player_id"] = player_id_for(team_slug, p["name"])
        with path.open("w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"  re-keyed {path} ({len(data['players'])} players)")


if __name__ == "__main__":
    for team_slug, cfg in MANUAL_SCHOOLS.items():
        ingest_school(team_slug, cfg)
