#!/usr/bin/env python3
"""
Builds one chart-ready JSON per career-linked wrestler: their full known
season-by-season DPG/matches/rank/record history, across every school they
wrestled for -- the atomic data layer behind the transfer report, the
team-roster report, and a future wrestler-search chart / profile embed.

build_team_roster_view.py assembles itself by reading these files back off
disk rather than re-deriving career links -- the join happens once, here.

Usage:
    python scripts/reports/build_wrestler_view.py                # full backfill, every career file
    python scripts/reports/build_wrestler_view.py --season 2026  # only wrestlers active in 2026 (weekly pipeline)
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_transfer_dpg_report as base  # noqa: E402

OUTPUT_DIR = Path("frontend/wrestledata-ui/public/data/reports/wrestler_view")
INDEX_PATH = Path("frontend/wrestledata-ui/public/data/reports/wrestler_index.json")


def build_wrestler_view(career_id, seasons_map, abbr_map):
    season_ids = sorted(
        ((int(s), w) for s, w in seasons_map.items() if s.isdigit()),
        key=lambda x: x[0],
    )

    name = weight_class = photo_url = None
    seasons = []
    for year, wid in season_ids:
        if year < base.MIN_KNOWN_SEASON or year > base.MAX_KNOWN_SEASON:
            continue
        profile = base.load_profile(year, wid)
        if not profile:
            continue
        team = profile.get("team")
        if not team:
            continue
        mv = base.mat_value_for(year, wid)
        if not mv or not mv.get("matches"):
            continue  # skip 0-match / no-DPG-data seasons entirely

        name = profile.get("name") or name
        weight_class = profile.get("weight_class") or weight_class
        photo_url = profile.get("photo_url") or photo_url
        seasons.append({
            "year": year,
            "wrestler_id": wid,
            "team": team,
            "team_slug": base.slugify(team),
            "team_abbr": abbr_map.get(team, team[:4].upper()),
            "dpg": round(mv["mv_avg"], 2) if mv.get("mv_avg") is not None else None,
            "matches": mv.get("matches"),
            "rank": profile.get("current_rank"),
            "record": (profile.get("record") or {}).get("overall"),
        })

    if not seasons:
        return None

    path = []
    for s in seasons:
        if not path or path[-1] != s["team"]:
            path.append(s["team"])

    return {
        "career_id": career_id,
        "wrestler_id": seasons[-1]["wrestler_id"],
        "name": name,
        "weight_class": weight_class,
        "photo_url": photo_url,
        "school_path": path,
        "seasons": seasons,
    }


def main():
    parser = argparse.ArgumentParser(description="Build per-wrestler chart-ready view JSON")
    parser.add_argument("--season", type=int,
                         help="Only rebuild wrestlers active in this season (weekly pipeline mode). "
                              "Omit for a full backfill of every career file.")
    args = parser.parse_args()

    abbr_map = base.build_abbr_map()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    n_written = 0
    n_skipped = 0
    for f in sorted(base.CAREERS_DIR.glob("career_*.json")):
        try:
            career = json.loads(f.read_text())
        except Exception:
            continue
        career_id = career.get("career_id") or f.stem
        seasons_map = career.get("seasons", {})
        if args.season and str(args.season) not in seasons_map:
            continue

        view = build_wrestler_view(career_id, seasons_map, abbr_map)
        if not view:
            n_skipped += 1
            continue
        (OUTPUT_DIR / f"{career_id}.json").write_text(
            json.dumps(view, indent=2, ensure_ascii=False))
        n_written += 1

    scope = f"season {args.season}" if args.season else "full backfill"
    print(f"Wrestler views ({scope}): wrote {n_written}, skipped {n_skipped} (no qualifying season data)")
    print(f"Output: {OUTPUT_DIR}")

    write_search_index()


def write_search_index():
    """Rebuilt from every wrestler_view file currently on disk (not just the
    ones this run touched) -- a --season-scoped weekly run still needs the
    index to cover every wrestler ever built, not just this week's subset."""
    entries = []
    for f in sorted(OUTPUT_DIR.glob("career_*.json")):
        try:
            view = json.loads(f.read_text())
        except Exception:
            continue
        if not view.get("seasons"):
            continue
        latest = view["seasons"][-1]
        entries.append({
            "career_id": view["career_id"],
            "name": view.get("name"),
            "weight_class": view.get("weight_class"),
            "team": latest.get("team"),
            "team_abbr": latest.get("team_abbr"),
            "latest_year": latest.get("year"),
            "latest_rank": latest.get("rank"),
        })
    INDEX_PATH.write_text(json.dumps(entries, indent=2, ensure_ascii=False))
    print(f"Wrote search index ({len(entries)} wrestlers): {INDEX_PATH}")


if __name__ == "__main__":
    main()
