#!/usr/bin/env python3
"""
Batch official-roster scrape for the 2012-2019 historical backfill, one
season at a time, synchronized against that season's OWN already-scraped
team list (data/team_lists/ncaa_men/{season}/teams.json) -- not the current
2026 list, since teams come and go over 14 years (renamed, discontinued,
or newly-added programs all show up as real mismatches, not scraper bugs).

For each team in a season's list:
  1. Normalize its name and check if that slug already has official-roster
     data scraped for the CURRENT season -- if so, reuse that team's own
     `team_roster_url` (stripping the trailing `/season/{slug}` or `/{slug}`)
     as the base URL for this historical season too.
  2. Else check HISTORICAL_NAME_ALIASES (teams whose current site still
     exists, just under a different display name in old TrackWrestling data
     -- e.g. "Pennsylvania" -> penn, "The Citadel" -> citadel).
  3. Else check DISCONTINUED_BASE_URLS (teams that no longer exist / renamed
     entirely -- Fresno State, Boise State, Old Dominion, Boston University,
     Eastern Michigan, Grand Canyon -- confirmed via WebSearch to still have
     a real, reachable historical roster page on their own athletics site).
  4. Else check SKIP_TEAMS (confirmed via WebSearch to have NO roster to
     scrape at all for this era -- Cal State Fullerton/UNC-Greensboro were
     cut before the 2012 season started).
  5. Else: unresolved -- printed for manual follow-up, not silently dropped.

Usage:
  .venv/bin/python scripts/scraping/batch_scrape_historical_rosters.py --season 2019
  .venv/bin/python scripts/scraping/batch_scrape_historical_rosters.py --season 2019 --dry-run
"""
import argparse
import glob
import json
import re
import subprocess
import sys
from pathlib import Path

TEAM_LISTS_DIR = Path("data/team_lists/ncaa_men")
OFFICIAL_ROSTERS_DIR = Path("mt/data/official_rosters")

# Historical display name (exactly as it appears in a season's own
# teams.json) -> current team slug, for schools whose real athletics site
# still exists today under a different name/abbreviation than the one
# TrackWrestling's older data uses. Found by cross-referencing every
# historical season's team list against the current (2026) slug set and
# resolving each mismatch by hand -- current slugs use several irregular
# abbreviations (uni, nd_state, n_colorado, siue, sd_state, citadel,
# app_state) that don't follow a guessable transform from the display name.
HISTORICAL_NAME_ALIASES = {
    "Army West Point": "army",
    "Binghamton University": "binghamton",
    "North Carolina State": "nc_state",
    "North Dakota State": "nd_state",
    "North Dakota State University": "nd_state",
    "Pennsylvania": "penn",
    "SIU Edwardsville": "siue",
    "Southern Illinois Edwardsville": "siue",
    "Utah Valley University": "utah_valley",
    "Vmi": "vmi",
    "Appalachian State": "app_state",
    "The Citadel": "citadel",
    "Northern Colorado": "n_colorado",
    "Northern Iowa": "uni",
    "South Dakota State": "sd_state",
}

# Teams with no CURRENT roster page to derive a base URL from (renamed,
# merged, or the program was discontinued) but a real, reachable roster
# page still exists somewhere on the school's own athletics site for the
# years they did compete -- confirmed via WebSearch, not guessed.
DISCONTINUED_BASE_URLS = {
    "Fresno State": "https://gobulldogs.com/sports/wrestling/roster",
    "Boise State": "https://broncosports.com/sports/wrestling/roster",
    "Old Dominion": "https://odusports.com/sports/wrestling/roster",  # discontinued April 2020
    "Boston U.": "https://goterriers.com/sports/wrestling/roster",
    "Eastern Michigan": "https://emueagles.com/sports/wrestling/roster",
    "Grand Canyon": "https://gculopes.com/sports/wrestling/roster",
}

# Confirmed via WebSearch: no roster exists to scrape at all for this era --
# both programs were cut before the 2012 season even started.
SKIP_TEAMS = {
    "Cal State Fullerton", "North Carolina-Greensboro",
    # Manual-capture-only teams, handled outside this batch script:
    # Wyoming already has full webarchive coverage for every season back to
    # 2011-12 (see ingest_manual_roster_webarchive.py). George Mason's site
    # (gomason.com) returns 200 but has no payload any existing parser can
    # read (confirmed: tried all 4 HTML/JSON fallback parsers live, all
    # returned 0) -- needs the same manual .webarchive/PDF capture Wyoming
    # gets; not yet done for any season.
    "Wyoming", "George Mason",
}


def normalize(name):
    n = name.lower().replace("&", "").replace("'", "")
    n = re.sub(r"[^a-z0-9]+", "_", n)
    return n.strip("_")


def season_to_roster_slug(season):
    """season 2019 (tournament March 2019) -> roster school year '2018-19'."""
    return f"{season - 1}-{str(season)[2:]}"


def current_base_url(slug):
    """Reuse an already-scraped current-season file's own team_roster_url,
    stripping the trailing season segment -- same technique proven across
    the 2020/2021/2022/2023 backfills."""
    candidates = sorted(glob.glob(str(OFFICIAL_ROSTERS_DIR / slug / "*.json")), reverse=True)
    for path in candidates:
        try:
            data = json.load(open(path))
        except (json.JSONDecodeError, OSError):
            continue
        url = data.get("team_roster_url", "")
        if not url or "manual" in url.lower():
            continue
        base = re.sub(r"/season/[\w-]+/?$", "", url)
        base = re.sub(r"/(20\d{2}-?\d{0,4})/?$", "", base)
        return base
    return None


def resolve_team(name):
    """Returns (slug_or_label, base_url) or (None, None) if unresolved, or
    ("SKIP", None) if confirmed no roster exists."""
    if name in SKIP_TEAMS:
        return "SKIP", None

    slug = normalize(name)
    base = current_base_url(slug)
    if base:
        return slug, base

    alias_slug = HISTORICAL_NAME_ALIASES.get(name)
    if alias_slug:
        base = current_base_url(alias_slug)
        if base:
            return alias_slug, base

    if name in DISCONTINUED_BASE_URLS:
        return slug, DISCONTINUED_BASE_URLS[name]

    return None, None


def run_season(season, dry_run=False, delay=1.0):
    team_list_path = TEAM_LISTS_DIR / str(season) / "teams.json"
    teams = json.load(open(team_list_path))
    roster_season = season_to_roster_slug(season)

    resolved, skipped, unresolved = [], [], []
    for t in teams:
        name = t.get("name", "")
        slug, base_url = resolve_team(name)
        if slug == "SKIP":
            skipped.append(name)
        elif slug and base_url:
            resolved.append((name, slug, base_url))
        else:
            unresolved.append(name)

    print(f"=== Season {season} (roster year {roster_season}): "
          f"{len(teams)} teams -- {len(resolved)} resolved, {len(skipped)} skipped, {len(unresolved)} unresolved ===")
    if unresolved:
        print("UNRESOLVED (need manual follow-up):", unresolved)

    if dry_run:
        for name, slug, base_url in resolved:
            print(f"  [DRY-RUN] {name} ({slug}) -> {base_url}")
        return

    py = sys.executable
    ok, fail = [], []
    for i, (name, slug, base_url) in enumerate(resolved, 1):
        print(f"[{i}/{len(resolved)}] {name} ({slug}) -> {base_url}", flush=True)
        out = subprocess.run(
            [py, "scripts/scraping/scrape_official_roster.py", "--team", slug,
             "--base-url", base_url, "--seasons", roster_season],
            capture_output=True, text=True, timeout=60,
        )
        combined = (out.stdout + out.stderr).strip()
        print(combined[-300:], flush=True)
        if "[OK]" in combined:
            ok.append(name)
        else:
            fail.append(name)

    print(f"\n=== Season {season} summary: OK {len(ok)}, FAIL {len(fail)} ===")
    if fail:
        print("Failed:", fail)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run_season(args.season, dry_run=args.dry_run)
