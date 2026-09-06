#!/usr/bin/env python3
"""
Batch-runs scrape_official_schedule.py across every current D1 team, and
maintains a persistent status log (mt/data/official_schedules/_status.json)
tracking, per team: the last time a real schedule was successfully pulled,
how many events it had, and what happened on the most recent attempt.

Designed to be re-run periodically as more schools publish their 2026-27
schedule (many hadn't as of the first pass, 2026-09) -- a team that
succeeds today keeps its last_success_date; a team that still isn't posted
just updates last_checked_date/last_checked_result, so re-running never
loses a team's most recent real success.

Team -> base URL is derived the same way batch_scrape_historical_rosters.py
resolves team names to slugs: normalize + a small alias map for irregular
current slugs, then reuse whatever roster URL that team's own official-
roster scrape already recorded (any season, most recent first), converting
the roster page's own URL to its schedule-page equivalent (swap the
trailing "/roster" for "/schedule"). The 3 manual-only schools (Wyoming,
Little Rock, George Mason -- no scrapeable roster URL since those were
webarchive/PDF-captured) get their real domains hardcoded here instead.

Usage:
  .venv/bin/python scripts/scraping/batch_scrape_schedules.py
  .venv/bin/python scripts/scraping/batch_scrape_schedules.py --season 2026-27
  .venv/bin/python scripts/scraping/batch_scrape_schedules.py --render-only
"""

import argparse
import glob
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from scrape_official_schedule import scrape_schedule

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
STATUS_PATH = PROJECT_ROOT / "mt" / "data" / "official_schedules" / "_status.json"
FLAGS_PATH = PROJECT_ROOT / "mt" / "data" / "official_schedules" / "_coherency_flags.json"
MD_PATH = PROJECT_ROOT / "mt" / "data" / "official_schedules" / "SCHEDULE_STATUS.md"
ROSTERS_DIR = PROJECT_ROOT / "mt" / "data" / "official_rosters"
TEAM_LIST_PATH = PROJECT_ROOT / "data" / "team_lists" / "ncaa_men" / "2026" / "teams.json"


def event_key(e):
    return (e.get("date"), e.get("opponent") or e.get("event_name"), e.get("venue_type"))


def diff_events(old_events, new_events):
    """Returns (dropped, added) -- events present in one side but not the
    other, keyed by (date, opponent, venue_type). A schedule ADDING events
    (a newly-announced tournament, say) is never concerning on its own --
    only DROPPED events need a human's judgment call, matching the same
    principle already used for match-scrape validation: a couple of
    legitimately-cancelled duals is normal, but a mass disappearance (or
    everything dropping to zero) usually means the scrape broke, not that
    the season fell apart."""
    old_by_key = {event_key(e): e for e in old_events}
    new_by_key = {event_key(e): e for e in new_events}
    dropped = [e for k, e in old_by_key.items() if k not in new_by_key]
    added = [e for k, e in new_by_key.items() if k not in old_by_key]
    return dropped, added


def load_flags():
    if FLAGS_PATH.exists():
        return json.loads(FLAGS_PATH.read_text())
    return {}


def save_flags(flags):
    FLAGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    FLAGS_PATH.write_text(json.dumps(flags, indent=2, ensure_ascii=False))

# Irregular current slugs that don't fall out of a plain normalize() of the
# team-list's own display name -- same map used for the 2012-2019 historical
# roster backfill.
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

# No scrapeable roster URL on file (webarchive/PDF-captured) -- real domains
# known from manual capture work, hardcoded here.
MANUAL_SCHOOL_BASE_URLS = {
    "wyoming": "https://gowyo.com/sports/wrestling/schedule",
    "little_rock": "https://lrtrojans.com/sports/wrestling/schedule",
    "george_mason": "https://gomason.com/sports/wrestling/schedule",
}


def normalize(name):
    n = name.lower().replace("&", "").replace("'", "")
    n = re.sub(r"[^a-z0-9]+", "_", n)
    return n.strip("_")


def build_team_map():
    """Returns {slug: (display_name, schedule_base_url_or_None)}."""
    teams = json.loads(TEAM_LIST_PATH.read_text())
    existing_slugs = {Path(d).name for d in glob.glob(str(ROSTERS_DIR / "*"))}

    out = {}
    for t in teams:
        name = t["name"]
        slug = normalize(name)
        if slug not in existing_slugs:
            slug = NAME_ALIASES.get(name, slug)

        base_url = MANUAL_SCHOOL_BASE_URLS.get(slug)
        if not base_url:
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
                base_url = re.sub(r"/roster$", "/schedule", base)
                break

        out[slug] = (name, base_url)
    return out


def load_status():
    if STATUS_PATH.exists():
        return json.loads(STATUS_PATH.read_text())
    return {}


def save_status(status):
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(status, indent=2, ensure_ascii=False))


def run_batch(season, dry_run=False):
    team_map = build_team_map()
    status = load_status()
    flags = load_flags()
    today = date.today().isoformat()

    ok, not_found, needs_work, flagged = 0, 0, 0, 0
    for slug, (name, base_url) in sorted(team_map.items()):
        entry = status.setdefault(slug, {"team_name": name, "base_url": base_url,
                                          "last_success_date": None, "last_success_season": None,
                                          "last_success_event_count": None, "last_success_template": None,
                                          "last_checked_date": None, "last_checked_result": None})
        entry["team_name"] = name
        entry["base_url"] = base_url
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
            data, error = scrape_schedule(base_url, season)
        except Exception as e:
            entry["last_checked_result"] = f"error: {e}"
            needs_work += 1
            print(f"{slug:20s} [ERROR] {e}")
            continue

        if error:
            entry["last_checked_result"] = error
            if error == "no_events_found":
                needs_work += 1
            else:
                not_found += 1
            print(f"{slug:20s} [{error}]")
            continue

        out_dir = ROSTERS_DIR.parent / "official_schedules" / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{season}.json"

        old_data = None
        if out_path.exists():
            try:
                old_data = json.loads(out_path.read_text())
            except (json.JSONDecodeError, OSError):
                old_data = None

        dropped, added = ([], [])
        if old_data and old_data.get("events"):
            dropped, added = diff_events(old_data["events"], data["events"])

        if dropped:
            # Never silently overwrite good data with a scrape that lost
            # events -- a couple of cancelled duals is a real, legitimate
            # change (fine to eventually accept), but the same signal also
            # covers "the site changed and our parser now misses half the
            # season" (never fine to accept blindly). Both look identical
            # from inside this loop -- only a human (or a deliberate,
            # separate investigation) can tell them apart, so park the new
            # data for review instead of guessing.
            new_path = out_dir / f"{season}.pending.json"
            new_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            flags[slug] = {
                "team_name": name,
                "season": season,
                "detected_date": today,
                "old_event_count": len(old_data["events"]),
                "new_event_count": len(data["events"]),
                "dropped": dropped,
                "added": added,
                "severity": "likely_bad_scrape" if len(data["events"]) == 0 else "changed",
                "pending_path": str(new_path),
            }
            save_flags(flags)
            entry["last_checked_result"] = f"coherency_flag: {len(dropped)} event(s) dropped, see _coherency_flags.json"
            flagged += 1
            print(f"{slug:20s} [FLAGGED] {len(old_data['events'])} -> {len(data['events'])} events "
                  f"({len(dropped)} dropped, {len(added)} added) -- needs review, old data kept")
            continue

        # No drops (only additions, or a first-time pull) -- safe to accept
        # automatically. Clear any older flag for this team/season now that
        # a clean pull came through.
        flags.pop(slug, None)
        save_flags(flags)

        entry["last_checked_result"] = "ok"
        entry["last_success_date"] = today
        entry["last_success_season"] = data["season"]
        entry["last_success_event_count"] = len(data["events"])
        entry["last_success_template"] = data["template"]
        ok += 1
        print(f"{slug:20s} [OK] template {data['template']}: {len(data['events'])} events")

        out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    if not dry_run:
        save_status(status)
        print(f"\nOK: {ok}  not-yet-posted: {not_found}  needs-work: {needs_work}  flagged-for-review: {flagged}  total: {len(team_map)}")
    return status


def render_markdown(status):
    flags = load_flags()
    rows = []
    for slug, e in status.items():
        rows.append({**e, "_slug": slug})

    def sort_key(e):
        # Most recent last_success_date first; teams with no success ever sort last.
        return (e["last_success_date"] is None, e["last_success_date"] or "", e["team_name"])

    rows.sort(key=sort_key, reverse=False)
    # reverse the date ordering specifically (most recent success first) while
    # keeping "never succeeded" pinned at the bottom
    rows_with_success = [r for r in rows if r["last_success_date"]]
    rows_without_success = [r for r in rows if not r["last_success_date"]]
    rows_with_success.sort(key=lambda e: e["last_success_date"], reverse=True)
    rows_without_success.sort(key=lambda e: e["team_name"])

    lines = [
        "# Official Schedule Scrape Status",
        "",
        f"Last batch run: {date.today().isoformat()}. Sorted by most recent successful pull.",
        "Re-run `scripts/scraping/batch_scrape_schedules.py` periodically -- a team",
        "with no success yet just hasn't published its schedule; rerun later to pick it up.",
    ]
    if flags:
        lines += [
            "",
            f"**{len(flags)} team(s) need coherency review** (events dropped since the last good pull -- "
            "could be a legitimate schedule change, or the scraper breaking). Run "
            "`scripts/scraping/review_schedule_coherency.py` to resolve. The old (last-known-good) data is "
            "kept as the live file until reviewed; the new scrape is parked in a `.pending.json` file.",
        ]
    lines += [
        "",
        "| Team | Last Successful Pull | Events | Last Checked | Status |",
        "|---|---|---|---|---|",
    ]
    for e in rows_with_success:
        # A row's "Status" reflects the MOST RECENT check, not just whether
        # it ever succeeded -- confirmed necessary: the underlying success
        # data (date/event count/saved JSON) is correctly preserved when a
        # later check fails (never overwritten), but rendering "ok" here
        # regardless would hide a real regression (e.g. a site redesign
        # breaking the template) behind stale good numbers. A stale-good
        # row still keeps its real last_success_event_count on display --
        # that data isn't lost, it's just labeled honestly as not
        # reconfirmed today.
        stale = e["last_checked_date"] != e["last_success_date"]
        if e["_slug"] in flags:
            f = flags[e["_slug"]]
            status_label = f"🚩 needs review -- {f['old_event_count']}→{f['new_event_count']} events ({len(f['dropped'])} dropped)"
        elif stale:
            status_label = f"⚠️ stale -- last check: {e['last_checked_result']}"
        else:
            status_label = "ok"
        lines.append(
            f"| {e['team_name']} | {e['last_success_date']} ({e['last_success_season']}) | "
            f"{e['last_success_event_count']} | {e['last_checked_date']} | {status_label} |"
        )
    for e in rows_without_success:
        result = e.get("last_checked_result") or "never checked"
        lines.append(f"| {e['team_name']} | never | — | {e.get('last_checked_date') or '—'} | {result} |")

    MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    MD_PATH.write_text("\n".join(lines) + "\n")
    print(f"Wrote {MD_PATH}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default="2026-27")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--render-only", action="store_true", help="Skip scraping, just regenerate the MD from existing status")
    args = ap.parse_args()

    if args.render_only:
        render_markdown(load_status())
    else:
        status = run_batch(args.season, dry_run=args.dry_run)
        if not args.dry_run:
            render_markdown(status)
