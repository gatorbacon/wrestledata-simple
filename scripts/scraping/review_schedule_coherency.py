#!/usr/bin/env python3
"""
Interactively resolve coherency flags raised by batch_scrape_schedules.py --
a team whose newest scrape has FEWER events than its last known-good pull.
That's the schedule-page equivalent of the same check already used for raw
match data (process_raw_matches_by_season.py's "DATA INTEGRITY VALIDATION
FAILED" prompt): a small drop is often a real, legitimate schedule change
(a dual got cancelled or moved), but it's indistinguishable, from inside the
scraper alone, from the site changing in a way that breaks the parser and
silently loses real events -- only a human (or a deliberate look at the
school's actual site) can tell those apart, so the scraper never guesses;
it parks the new data and waits here.

For each flagged team, shows what was dropped and what was added, then asks:
  1) Keep OLD data (reject this scrape -- treat the drop as a bad scrape)
  2) Accept NEW data (the drop was real -- overwrite with the new pull)
  3) MERGE (keep every event from both old and new, deduped -- use when
     some of the "dropped" events are still legitimately on the schedule
     and the scraper just missed them this one time, alongside genuine
     new additions)
  4) Skip for now (leave flagged, decide later)

Usage:
  .venv/bin/python scripts/scraping/review_schedule_coherency.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from batch_scrape_schedules import (
    FLAGS_PATH, STATUS_PATH, MD_PATH, ROSTERS_DIR,
    load_flags, save_flags, load_status, save_status, render_markdown, event_key,
)


def describe_event(e):
    who = e.get("opponent") or e.get("event_name") or "?"
    return f"{e.get('date')} [{e.get('venue_type')}] {who}"


def merge_events(old_events, new_events):
    by_key = {event_key(e): e for e in old_events}
    for e in new_events:
        by_key[event_key(e)] = e  # new data wins for anything present in both
    return sorted(by_key.values(), key=lambda e: (e.get("date") or ""))


def resolve_one(slug, flag, status):
    out_dir = ROSTERS_DIR.parent / "official_schedules" / slug
    live_path = out_dir / f"{flag['season']}.json"
    pending_path = Path(flag["pending_path"])

    print(f"\n{'='*70}")
    print(f"{flag['team_name']} ({slug}) -- {flag['season']}")
    print(f"  {flag['old_event_count']} events -> {flag['new_event_count']} events  "
          f"[{flag['severity']}]  detected {flag['detected_date']}")
    print(f"  Dropped ({len(flag['dropped'])}):")
    for e in flag["dropped"]:
        print(f"    - {describe_event(e)}")
    if flag["added"]:
        print(f"  Added ({len(flag['added'])}):")
        for e in flag["added"]:
            print(f"    + {describe_event(e)}")

    print("  1) Keep OLD data (reject this scrape)")
    print("  2) Accept NEW data (the drop was real)")
    print("  3) MERGE (keep events from both, deduped)")
    print("  4) Skip for now")
    choice = input("  Choice: ").strip()

    if choice == "1":
        pending_path.unlink(missing_ok=True)
        print("  -> kept old data, discarded new scrape")
        return True
    if choice == "2":
        new_data = json.loads(pending_path.read_text())
        live_path.write_text(json.dumps(new_data, indent=2, ensure_ascii=False))
        pending_path.unlink(missing_ok=True)
        entry = status.setdefault(slug, {})
        entry["last_success_date"] = flag["detected_date"]
        entry["last_success_season"] = flag["season"]
        entry["last_success_event_count"] = flag["new_event_count"]
        entry["last_checked_result"] = "ok"
        print("  -> accepted new data")
        return True
    if choice == "3":
        old_data = json.loads(live_path.read_text()) if live_path.exists() else {"events": []}
        new_data = json.loads(pending_path.read_text())
        merged_events = merge_events(old_data.get("events", []), new_data["events"])
        merged_data = dict(new_data)
        merged_data["events"] = merged_events
        live_path.write_text(json.dumps(merged_data, indent=2, ensure_ascii=False))
        pending_path.unlink(missing_ok=True)
        entry = status.setdefault(slug, {})
        entry["last_success_date"] = flag["detected_date"]
        entry["last_success_season"] = flag["season"]
        entry["last_success_event_count"] = len(merged_events)
        entry["last_checked_result"] = "ok"
        print(f"  -> merged, {len(merged_events)} total events")
        return True

    print("  -> skipped, still flagged")
    return False


def main():
    flags = load_flags()
    if not flags:
        print("No coherency flags to review.")
        return

    status = load_status()
    for slug in list(flags.keys()):
        resolved = resolve_one(slug, flags[slug], status)
        if resolved:
            del flags[slug]
            save_flags(flags)
            save_status(status)

    render_markdown(status)
    print(f"\nDone. {len(flags)} team(s) still flagged.")


if __name__ == "__main__":
    main()
