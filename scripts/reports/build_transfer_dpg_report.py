#!/usr/bin/env python3
"""
Build the data file behind the "transfer DPG" report -- for a given NCAA
team and season-year range, finds every wrestler who was on that team's
roster in any season within the range AND who wrestled for at least one
OTHER team at some point in their tracked career (before the range, after
it, or both) -- i.e. transfers in and transfers out, using this school as
the anchor. For each one, emits their full known season-by-season DPG
(mat_value) history, tagged by whether that season was at the query team.

This does NOT render anything -- it only writes the JSON the reusable
report page (frontend/wrestledata-ui/public/reports/transfers/index.html)
fetches at view time via ?team=&start=&end=. Same split as every other
page on this site: Python builds static JSON, a generic HTML/JS template
renders whichever JSON the URL asks for.

Usage:
    python scripts/reports/build_transfer_dpg_report.py --team "Penn State" --start-year 2023 --end-year 2026
    python scripts/reports/build_transfer_dpg_report.py --team penn_state --start-year 2023 --end-year 2026
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from team_colors import TEAM_COLORS, DEFAULT_COLOR  # noqa: E402

CAREERS_DIR = Path("data/careers/ncaa_men")
WRESTLERS_DIR = Path("frontend/wrestledata-ui/public/data/wrestlers")
MAT_VALUE_DIR = Path("frontend/wrestledata-ui/public/data/mat_value")
TEAM_COLORS_OUTPUT = Path("frontend/wrestledata-ui/public/data/team_colors.json")
TEAMS_LIST_PATH = Path("data/team_lists/ncaa_men/2026/teams.json")
OUTPUT_DIR = Path("frontend/wrestledata-ui/public/data/reports/transfers")

MIN_KNOWN_SEASON = 2012
MAX_KNOWN_SEASON = 2026


def slugify(name: str) -> str:
    """Matches build_wrestler_profiles.py's team_name_to_slug() exactly (no
    underscore-collapsing) -- NOT build_team_profiles.py's slugify_team_name(),
    which does collapse and produces a different slug for names with adjacent
    punctuation (e.g. "Franklin & Marshall" -> "franklin__marshall" here vs
    "franklin_marshall" there). This script reads wrestler roster membership
    from data/wrestlers/{season}/by_team/{slug}/, which is built by
    build_wrestler_profiles.py, so it must use that script's own slug form or
    roster lookups for affected teams silently return nothing."""
    s = name.lower().replace(" ", "_")
    s = re.sub(r"[^\w_]", "", s)
    return s


def resolve_team(query: str) -> Optional[Dict[str, str]]:
    """Accepts either a display name or a slug; returns {"slug":..,"name":..}."""
    query_slug = slugify(query)
    if TEAMS_LIST_PATH.exists():
        teams = json.loads(TEAMS_LIST_PATH.read_text())
        for t in teams:
            name = t.get("name", "")
            if slugify(name) == query_slug or name.lower() == query.lower():
                return {"slug": slugify(name), "name": name}
    # Fallback: no exact hit in the official list -- accept the slug as-is
    # if a roster directory for it exists in at least one season.
    for season_dir in WRESTLERS_DIR.glob("*/by_team/" + query_slug):
        return {"slug": query_slug, "name": query.title()}
    return None


_abbr_cache: Optional[Dict[str, str]] = None


def build_abbr_map() -> Dict[str, str]:
    """team display name -> official abbreviation (e.g. "Northern Iowa" -> "UNI"),
    straight from the same source build_team_profiles.py uses -- not guessed."""
    global _abbr_cache
    if _abbr_cache is None:
        _abbr_cache = {}
        if TEAMS_LIST_PATH.exists():
            for t in json.loads(TEAMS_LIST_PATH.read_text()):
                if t.get("name") and t.get("abbreviation"):
                    _abbr_cache[t["name"]] = t["abbreviation"]
    return _abbr_cache


def build_career_index() -> Dict[str, Dict[str, str]]:
    idx: Dict[str, Dict[str, str]] = {}
    for f in CAREERS_DIR.glob("career_*.json"):
        try:
            career = json.loads(f.read_text())
        except Exception:
            continue
        seasons = career.get("seasons", {})
        for wid in seasons.values():
            idx[str(wid)] = seasons
    return idx


_profile_cache: Dict[str, Optional[Dict]] = {}


def load_profile(season: int, wid: str) -> Optional[Dict]:
    key = f"{season}:{wid}"
    if key not in _profile_cache:
        p = WRESTLERS_DIR / str(season) / "by_id" / f"{wid}.json"
        if p.exists():
            try:
                _profile_cache[key] = json.loads(p.read_text())
            except Exception:
                _profile_cache[key] = None
        else:
            _profile_cache[key] = None
    return _profile_cache[key]


_mv_cache: Dict[int, Dict[str, Dict]] = {}


def mat_value_for(season: int, wid: str) -> Optional[Dict]:
    if season not in _mv_cache:
        p = MAT_VALUE_DIR / str(season) / f"mat_value_{season}.json"
        m: Dict[str, Dict] = {}
        if p.exists():
            try:
                data = json.loads(p.read_text())
                for e in data:
                    m[str(e.get("wrestler_id"))] = e
            except Exception:
                pass
        _mv_cache[season] = m
    return _mv_cache[season].get(str(wid))


def collect_roster_seed_ids(team_slug: str, start_year: int, end_year: int) -> set:
    seed_ids = set()
    for season in range(start_year, end_year + 1):
        roster_dir = WRESTLERS_DIR / str(season) / "by_team" / team_slug
        if roster_dir.exists():
            for f in roster_dir.glob("*.json"):
                seed_ids.add(f.stem)
    return seed_ids


def build_report(team_slug: str, team_name: str, start_year: int, end_year: int) -> Dict:
    career_index = build_career_index()
    seed_ids = collect_roster_seed_ids(team_slug, start_year, end_year)
    abbr_map = build_abbr_map()

    seen_careers = set()
    wrestlers_out = []

    for wid_seed in seed_ids:
        seasons_map = career_index.get(wid_seed)
        if not seasons_map:
            continue  # no career link at all -- can't trace other-team history
        career_key = tuple(sorted(seasons_map.items()))
        if career_key in seen_careers:
            continue
        seen_careers.add(career_key)

        season_ids = sorted(
            ((int(s), w) for s, w in seasons_map.items() if s.isdigit()),
            key=lambda x: x[0],
        )

        seasons = []
        for year, wid in season_ids:
            if year < MIN_KNOWN_SEASON or year > MAX_KNOWN_SEASON:
                continue
            profile = load_profile(year, wid)
            if not profile:
                continue
            team = profile.get("team")
            if not team:
                continue
            mv = mat_value_for(year, wid)
            if not mv or not mv.get("matches"):
                continue  # skip 0-match / no-DPG-data seasons entirely
            seasons.append({
                "year": year,
                "wrestler_id": wid,
                "team": team,
                "team_slug": slugify(team),
                "team_abbr": abbr_map.get(team, team[:4].upper()),
                "is_query_team": slugify(team) == team_slug,
                "dpg": round(mv["mv_avg"], 2) if mv.get("mv_avg") is not None else None,
                "matches": mv.get("matches"),
                "rank": profile.get("current_rank"),
                "record": (profile.get("record") or {}).get("overall"),
            })

        if not seasons:
            continue

        query_team_seasons = [s for s in seasons if s["is_query_team"]]
        other_team_seasons = [s for s in seasons if not s["is_query_team"]]
        if not query_team_seasons or not other_team_seasons:
            continue  # not a transfer relative to this team -- lifer or never actually played here

        first_query_year = min(s["year"] for s in query_team_seasons)
        last_query_year = max(s["year"] for s in query_team_seasons)
        transferred_in = any(s["year"] < first_query_year for s in other_team_seasons)
        transferred_out = any(s["year"] > last_query_year for s in other_team_seasons)
        if transferred_in and transferred_out:
            direction = "both"
        elif transferred_in:
            direction = "transfer_in"
        elif transferred_out:
            direction = "transfer_out"
        else:
            # an other-team season interleaved between query-team seasons
            # (e.g. a mid-career one-year stop elsewhere) -- still notable
            direction = "both"

        latest_profile = load_profile(seasons[-1]["year"], seasons[-1]["wrestler_id"])

        # Chronological path of distinct schools (not one entry per season --
        # a 2-year stint shows up once), for the "A -> B -> C" subtitle.
        path = []
        for s in seasons:
            if not path or path[-1] != s["team"]:
                path.append(s["team"])

        # NOTE: match-weighted averages / delta (excluding n<6 seasons) are
        # computed client-side from `seasons` -- single source of truth for
        # both the header stats and which seasons render hollow on the chart,
        # so the two can't drift apart.
        wrestlers_out.append({
            "name": latest_profile.get("name") if latest_profile else None,
            "weight_class": latest_profile.get("weight_class") if latest_profile else None,
            "photo_url": latest_profile.get("photo_url") if latest_profile else None,
            "direction": direction,
            "first_query_year": first_query_year,
            "last_query_year": last_query_year,
            "school_path": path,
            "seasons": seasons,
        })

    wrestlers_out.sort(key=lambda w: (w["first_query_year"], w["name"] or ""))

    return {
        "query": {
            "team_slug": team_slug,
            "team_name": team_name,
            "start_year": start_year,
            "end_year": end_year,
        },
        "wrestlers": wrestlers_out,
    }


def write_team_colors():
    """Publish the school-color reference the chart reads for disc fill/stroke.
    Cheap to rewrite every run; keeps it in sync with team_colors.py."""
    TEAM_COLORS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    TEAM_COLORS_OUTPUT.write_text(json.dumps(
        {"teams": TEAM_COLORS, "default": DEFAULT_COLOR}, indent=2, ensure_ascii=False
    ))


def main():
    parser = argparse.ArgumentParser(description="Build transfer DPG report data")
    parser.add_argument("--team", required=True, help="Team name or slug, e.g. 'Penn State' or penn_state")
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    args = parser.parse_args()

    resolved = resolve_team(args.team)
    if not resolved:
        print(f"Error: could not resolve team '{args.team}' against {TEAMS_LIST_PATH}")
        return

    print(f"Building transfer DPG report: {resolved['name']} ({resolved['slug']}), "
          f"{args.start_year}-{args.end_year}")

    report = build_report(resolved["slug"], resolved["name"], args.start_year, args.end_year)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{resolved['slug']}_{args.start_year}_{args.end_year}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    write_team_colors()

    n = len(report["wrestlers"])
    n_in = sum(1 for w in report["wrestlers"] if w["direction"] in ("transfer_in", "both"))
    n_out = sum(1 for w in report["wrestlers"] if w["direction"] in ("transfer_out", "both"))
    print(f"Found {n} transfer(s) touching {resolved['name']} in this window "
          f"({n_in} in, {n_out} out, overlap counted in both)")
    print(f"Wrote {out_path}")
    print(f"\nView at: /reports/transfers/index.html?team={resolved['slug']}"
          f"&start={args.start_year}&end={args.end_year}")


if __name__ == "__main__":
    main()
