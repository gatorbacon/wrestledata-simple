#!/usr/bin/env python3
"""
Batch-runs scrape_official_roster.py's scrape_season() across every CURRENT
D1 team for the current season (default "2026-27"), the current-season
counterpart to batch_scrape_historical_rosters.py (which is scoped to the
2012-2019 backfill and keys off each historical season's own team list).

Two modes, via --mode:
  missing (default) -- only scrape teams that don't already have
    {season}.json on file. Cheapest way to fill gaps as more schools finish
    posting their roster for the year.
  all -- re-scrape every current team regardless of what's on file, to catch
    roster changes (transfers, new commits added, corrections) on teams
    already scraped earlier in the season. Mirrors the same before/after
    comparison batch_scrape_schedules.py does for schedules.

Team -> base roster URL is resolved the same way batch_scrape_historical_
rosters.py's current_base_url() does: reuse whatever real (non-manual)
team_roster_url that team's own most-recent on-disk roster file already
recorded, stripping the trailing season segment. The 3 manual-only schools
(Wyoming, Little Rock, George Mason -- webarchive/PDF-captured because their
live sites don't parse with any of scrape_official_roster.py's fallbacks)
get their real domains hardcoded here instead, same as
batch_scrape_schedules.py's MANUAL_SCHOOL_BASE_URLS -- a live attempt is
still made (harmless if it fails the same way it did before) rather than
silently skipping them forever.

Maintains mt/data/official_rosters/_status.json (per-team last success,
player count, most recent check's result) and, in --mode all, never
silently overwrites a roster whose player count DROPPED versus the last
saved pull -- parks the new pull as {season}.pending.json and records the
diff in mt/data/official_rosters/_coherency_flags.json, same reasoning as
the schedule scraper's coherency gate: a couple of players leaving (transfer,
graduation correction) is a normal real change, but it's indistinguishable
from inside the scraper alone from a site redesign silently breaking the
parser -- only a human can tell those apart.

Usage:
  .venv/bin/python scripts/scraping/batch_scrape_current_rosters.py
  .venv/bin/python scripts/scraping/batch_scrape_current_rosters.py --mode all
  .venv/bin/python scripts/scraping/batch_scrape_current_rosters.py --season 2026-27 --dry-run
"""

import argparse
import glob
import json
import re
import sys
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from scrape_official_roster import scrape_season  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ROSTERS_DIR = PROJECT_ROOT / "mt" / "data" / "official_rosters"
STATUS_PATH = ROSTERS_DIR / "_status.json"
FLAGS_PATH = ROSTERS_DIR / "_coherency_flags.json"
MD_PATH = ROSTERS_DIR / "ROSTER_STATUS.md"
TEAM_LIST_PATH = PROJECT_ROOT / "data" / "team_lists" / "ncaa_men" / "2026" / "teams.json"

# Same irregular-slug map used by batch_scrape_schedules.py /
# batch_scrape_historical_rosters.py -- current slugs use several
# abbreviations that don't fall out of a plain normalize() of the team
# list's own display name.
NAME_ALIASES = {
    "Army West Point": "army",
    "Binghamton University": "binghamton",
    "North Carolina State": "nc_state",
    "NC State": "nc_state",
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
    "George Mason": "george_mason",
}

# No live-scrapable roster URL on file (every on-disk season is annotated
# "manual webarchive capture") -- real domains known from that manual
# capture work, hardcoded here. Little Rock/Wyoming DO have working
# schedule pages (see batch_scrape_schedules.py) -- it's specifically the
# roster page that needed manual capture on these three.
MANUAL_SCHOOL_BASE_URLS = {
    "wyoming": "https://gowyo.com/sports/wrestling/roster",
    "little_rock": "https://lrtrojans.com/sports/wrestling/roster",
    "george_mason": "https://gomason.com/sports/wrestling/roster",
}


def normalize(name):
    n = name.lower().replace("&", "").replace("'", "")
    n = re.sub(r"[^a-z0-9]+", "_", n)
    return n.strip("_")


def existing_slugs():
    return {Path(d).name for d in glob.glob(str(ROSTERS_DIR / "*")) if Path(d).is_dir()}


def current_base_url(slug):
    """Reuse an already-scraped file's own team_roster_url (any season, most
    recent first), stripping the trailing season segment. Skips any URL
    annotated as a manual capture -- those aren't live-fetchable."""
    for f in sorted(glob.glob(str(ROSTERS_DIR / slug / "*.json")), reverse=True):
        try:
            data = json.loads(Path(f).read_text())
        except (json.JSONDecodeError, OSError):
            continue
        url = data.get("team_roster_url", "")
        if not url or "manual" in url.lower():
            continue
        base = re.sub(r"/season/[\w-]+/?$", "", url)
        base = re.sub(r"/(20\d{2}-?\d{0,4})/?$", "", base)
        return base
    return None


def build_team_map():
    """Returns {slug: (display_name, roster_base_url_or_None)}."""
    teams = json.loads(TEAM_LIST_PATH.read_text())
    slugs_on_disk = existing_slugs()

    out = {}
    for t in teams:
        name = t["name"]
        slug = normalize(name)
        if slug not in slugs_on_disk:
            slug = NAME_ALIASES.get(name, slug)

        base_url = MANUAL_SCHOOL_BASE_URLS.get(slug) or current_base_url(slug)
        out[slug] = (name, base_url)
    return out


def player_key(p):
    return p.get("player_id") if p.get("player_id") is not None else (p.get("name"), p.get("bio_url"))


def describe_player(p):
    bits = [p.get("name") or "?"]
    if p.get("weight"):
        bits.append(p["weight"])
    if p.get("class_level"):
        bits.append(p["class_level"])
    return " / ".join(bits)


def diff_players(old_players, new_players):
    old_by_key = {player_key(p): p for p in old_players}
    new_by_key = {player_key(p): p for p in new_players}
    dropped = [p for k, p in old_by_key.items() if k not in new_by_key]
    added = [p for k, p in new_by_key.items() if k not in old_by_key]
    return dropped, added


def load_json(path, default):
    if path.exists():
        return json.loads(path.read_text())
    return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def run_batch(season, mode, dry_run=False):
    team_map = build_team_map()
    status = load_json(STATUS_PATH, {})
    flags = load_json(FLAGS_PATH, {})
    today = date.today().isoformat()

    session = requests.Session()
    session.headers["User-Agent"] = "ClaudeBot/1.0 (+https://www.anthropic.com/claude-bot)"

    added_teams, updated_teams = [], []
    ok, not_found, needs_work, flagged, skipped_have = 0, 0, 0, 0, 0

    for slug, (name, base_url) in sorted(team_map.items()):
        entry = status.setdefault(slug, {
            "team_name": name, "base_url": base_url,
            "last_success_date": None, "last_success_season": None,
            "last_success_player_count": None,
            "last_checked_date": None, "last_checked_result": None,
        })
        entry["team_name"] = name
        entry["base_url"] = base_url

        out_path = ROSTERS_DIR / slug / f"{season}.json"
        already_have = out_path.exists()

        if mode == "missing" and already_have:
            skipped_have += 1
            continue

        entry["last_checked_date"] = today

        if not base_url:
            entry["last_checked_result"] = "no_base_url"
            needs_work += 1
            print(f"{slug:20s} [SKIP] no base URL on file")
            continue

        if dry_run:
            print(f"{slug:20s} would check {base_url}")
            continue

        try:
            data, error = scrape_season(session, base_url, season, debug=False)
        except Exception as e:
            entry["last_checked_result"] = f"error: {e}"
            needs_work += 1
            print(f"{slug:20s} [ERROR] {e}")
            continue

        if error:
            entry["last_checked_result"] = error
            if error == "no_players_found":
                needs_work += 1
            else:
                not_found += 1
            print(f"{slug:20s} [{error}]")
            continue

        old_data = None
        if already_have:
            try:
                old_data = json.loads(out_path.read_text())
            except (json.JSONDecodeError, OSError):
                old_data = None

        dropped, added = ([], [])
        if old_data and old_data.get("players"):
            dropped, added = diff_players(old_data["players"], data["players"])

        if dropped:
            new_path = ROSTERS_DIR / slug / f"{season}.pending.json"
            save_json(new_path, data)
            flags[slug] = {
                "team_name": name, "season": season, "detected_date": today,
                "old_player_count": len(old_data["players"]),
                "new_player_count": len(data["players"]),
                "dropped": dropped, "added": added,
                "severity": "likely_bad_scrape" if len(data["players"]) == 0 else "changed",
                "pending_path": str(new_path),
            }
            save_json(FLAGS_PATH, flags)
            entry["last_checked_result"] = f"coherency_flag: {len(dropped)} player(s) dropped, see _coherency_flags.json"
            flagged += 1
            print(f"{slug:20s} [FLAGGED] {len(old_data['players'])} -> {len(data['players'])} players "
                  f"({len(dropped)} dropped, {len(added)} added) -- needs review, old data kept")
            continue

        flags.pop(slug, None)
        save_json(FLAGS_PATH, flags)

        entry["last_checked_result"] = "ok"
        entry["last_success_date"] = today
        entry["last_success_season"] = data["season"]
        entry["last_success_player_count"] = len(data["players"])
        ok += 1

        if not already_have:
            added_teams.append((name, len(data["players"])))
            print(f"{slug:20s} [NEW] {len(data['players'])} players")
        elif added:
            updated_teams.append((name, len(old_data["players"]), len(data["players"]), added))
            print(f"{slug:20s} [OK] {len(old_data['players'])} -> {len(data['players'])} players (+{len(added)})")
        else:
            print(f"{slug:20s} [OK] {len(data['players'])} players (unchanged)")

        save_json(out_path, data)

    if not dry_run:
        save_json(STATUS_PATH, status)
        print(f"\nOK: {ok}  not-yet-posted: {not_found}  needs-work: {needs_work}  "
              f"flagged-for-review: {flagged}  already-had-it(skipped): {skipped_have}  total: {len(team_map)}")

        if added_teams:
            print(f"\nNew rosters added ({len(added_teams)}):")
            for name, count in added_teams:
                print(f"  {name}: {count} players")

        if updated_teams:
            print(f"\nExisting rosters with players added ({len(updated_teams)}):")
            for name, before, after, added in updated_teams:
                print(f"  {name}: {before} -> {after} players")
                for p in added:
                    print(f"    + {describe_player(p)}")

    return status, added_teams, updated_teams


def render_markdown(status):
    flags = load_json(FLAGS_PATH, {})
    rows = [{**e, "_slug": slug} for slug, e in status.items()]

    rows_with_success = [r for r in rows if r["last_success_date"]]
    rows_without_success = [r for r in rows if not r["last_success_date"]]
    rows_with_success.sort(key=lambda e: e["last_success_date"], reverse=True)
    rows_without_success.sort(key=lambda e: e["team_name"])

    lines = [
        "# Official Roster Scrape Status (Current Season)",
        "",
        f"Last batch run: {date.today().isoformat()}. Sorted by most recent successful pull.",
        "Re-run `scripts/scraping/batch_scrape_current_rosters.py` periodically -- a team",
        "with no success yet just hasn't posted its roster; rerun later to pick it up.",
        "Use `--mode all` to re-check every team (not just ones missing a file) for roster changes.",
    ]
    if flags:
        lines += [
            "",
            f"**{len(flags)} team(s) need coherency review** (players dropped since the last good pull). "
            "Inspect `_coherency_flags.json` by hand (no dedicated review CLI yet, unlike the schedule "
            "scraper's `review_schedule_coherency.py`) -- the old (last-known-good) data is kept live "
            "until you replace it with the parked `.pending.json` file.",
        ]
    lines += [
        "",
        "| Team | Last Successful Pull | Players | Last Checked | Status |",
        "|---|---|---|---|---|",
    ]
    for e in rows_with_success:
        stale = e["last_checked_date"] != e["last_success_date"]
        if e["_slug"] in flags:
            f = flags[e["_slug"]]
            status_label = f"needs review -- {f['old_player_count']}->{f['new_player_count']} players ({len(f['dropped'])} dropped)"
        elif stale:
            status_label = f"stale -- last check: {e['last_checked_result']}"
        else:
            status_label = "ok"
        lines.append(
            f"| {e['team_name']} | {e['last_success_date']} ({e['last_success_season']}) | "
            f"{e['last_success_player_count']} | {e['last_checked_date']} | {status_label} |"
        )
    for e in rows_without_success:
        result = e.get("last_checked_result") or "never checked"
        lines.append(f"| {e['team_name']} | never | — | {e.get('last_checked_date') or '—'} | {result} |")

    MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    MD_PATH.write_text("\n".join(lines) + "\n")
    print(f"Wrote {MD_PATH}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default="2026-27", help="Roster season slug, e.g. 2026-27")
    ap.add_argument("--mode", choices=["missing", "all"], default="missing",
                     help="missing = only scrape teams without a file yet (default); all = re-check every team")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--render-only", action="store_true", help="Skip scraping, just regenerate the MD from existing status")
    args = ap.parse_args()

    if args.render_only:
        render_markdown(load_json(STATUS_PATH, {}))
    else:
        status, added_teams, updated_teams = run_batch(args.season, args.mode, dry_run=args.dry_run)
        if not args.dry_run:
            render_markdown(status)
