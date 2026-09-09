#!/usr/bin/env python3
"""
Builds one JSON per team+season: that team's full roster for the year, with
each wrestler's full known career (every school, every year) embedded --
"team roster, and each guy's career DPG progress," independent of whether
they ever transferred (unlike the transfer report, which only keeps
wrestlers who also played elsewhere).

Reads already-built wrestler_view files (build_wrestler_view.py) rather than
re-deriving career links itself -- run that script first (or as part of the
same pipeline step) so the files this script reads are current.

Usage:
    python scripts/reports/build_team_roster_view.py                       # full backfill, every team x every season
    python scripts/reports/build_team_roster_view.py --season 2026         # only this season, all teams (weekly pipeline)
    python scripts/reports/build_team_roster_view.py --team penn_state --season 2026
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_transfer_dpg_report as base  # noqa: E402

WRESTLER_VIEW_DIR = Path("frontend/wrestledata-ui/public/data/reports/wrestler_view")
OUTPUT_DIR = Path("frontend/wrestledata-ui/public/data/reports/team_roster")

_wrestler_view_cache = {}


def load_wrestler_view(career_id):
    if career_id not in _wrestler_view_cache:
        p = WRESTLER_VIEW_DIR / f"{career_id}.json"
        _wrestler_view_cache[career_id] = json.loads(p.read_text()) if p.exists() else None
    return _wrestler_view_cache[career_id]


def build_wid_to_career_id():
    idx = {}
    for f in base.CAREERS_DIR.glob("career_*.json"):
        try:
            career = json.loads(f.read_text())
        except Exception:
            continue
        career_id = career.get("career_id") or f.stem
        for wid in career.get("seasons", {}).values():
            idx[str(wid)] = career_id
    return idx


def build_team_roster(team_slug, year, wid_to_career_id):
    roster_dir = base.WRESTLERS_DIR / str(year) / "by_team" / team_slug
    if not roster_dir.exists():
        return None

    seen_careers = set()
    roster = []
    team_name = None
    for f in sorted(roster_dir.glob("*.json")):
        wid = f.stem
        career_id = wid_to_career_id.get(wid)
        if not career_id or career_id in seen_careers:
            continue
        seen_careers.add(career_id)

        view = load_wrestler_view(career_id)
        if not view:
            continue  # no qualifying DPG/matches data for this wrestler at all
        # confirm this wrestler actually has a real season entry at this team/year
        # (roster dir membership should already guarantee this, but the wrestler
        # view is filtered independently, so check rather than assume)
        this_season = next((s for s in view["seasons"] if s["year"] == year and s["team_slug"] == team_slug), None)
        if not this_season:
            continue
        team_name = team_name or this_season["team"]
        roster.append(view)

    if not roster:
        return None

    roster.sort(key=lambda w: (w.get("weight_class") or 0, w.get("name") or ""))

    return {
        "team_slug": team_slug,
        "team_name": team_name,
        "year": year,
        "roster": roster,
    }


def all_team_slugs_for_year(year):
    year_dir = base.WRESTLERS_DIR / str(year) / "by_team"
    if not year_dir.exists():
        return []
    return sorted(p.name for p in year_dir.iterdir() if p.is_dir())


def main():
    parser = argparse.ArgumentParser(description="Build per-team-per-season roster view JSON")
    parser.add_argument("--team", help="Team slug, e.g. penn_state. Omit to build every team.")
    parser.add_argument("--season", type=int,
                         help="Single season to build. Omit for a full backfill of every season "
                              f"{base.MIN_KNOWN_SEASON}-{base.MAX_KNOWN_SEASON}.")
    args = parser.parse_args()

    years = [args.season] if args.season else list(range(base.MIN_KNOWN_SEASON, base.MAX_KNOWN_SEASON + 1))
    wid_to_career_id = build_wid_to_career_id()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    n_written = 0
    for year in years:
        slugs = [args.team] if args.team else all_team_slugs_for_year(year)
        for slug in slugs:
            out = build_team_roster(slug, year, wid_to_career_id)
            if not out:
                continue
            (OUTPUT_DIR / f"{slug}_{year}.json").write_text(
                json.dumps(out, indent=2, ensure_ascii=False))
            n_written += 1

    scope = f"season {args.season}" if args.season else f"full backfill {base.MIN_KNOWN_SEASON}-{base.MAX_KNOWN_SEASON}"
    print(f"Team roster views ({scope}): wrote {n_written}")
    print(f"Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
