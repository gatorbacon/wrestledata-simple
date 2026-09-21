#!/usr/bin/env python3
"""
Apply an explicit list of season links to backend career files: `career["seasons"][season] = season_wrestler_id`.

This is the non-interactive counterpart of `link_season_interactive.py`, for links that have already been decided
(e.g. the AUTO plan from `audit_unlinked_seasons.py`, or a list you approved by hand). It only ever ADDS a season key to
an existing career; it never creates careers, merges careers, or changes/removes an existing link.

Plan file = JSON list of {"gender": "boys"|"girls", "career_id": "career_000839", "season": 2024,
                          "season_wrestler_id": "24674709132", "note": "free text"}.

Safety checks (a link that fails any of them is SKIPPED and reported, nothing else is affected):
  - the career file exists and does not already have that season with a different id (same id = already applied, no-op)
  - the season_wrestler_id exists in mt/processed_data/hs_ky_{gender}/{season}/ (the roster the link refers to)
  - the season_wrestler_id is not already linked to some other career
Every applied link is appended to data/career_linking_logs/batch_links_log.json (who/what/when) so it is auditable.

After linking, downstream data must be rebuilt (see CLAUDE.md "Known Gotcha 13"): wrestler profiles for the affected
seasons (they carry career_id / opponent_career_id), career profiles, career-win leaderboards, search index.

Usage (from repo root):
    .venv/bin/python scripts/careers/link_seasons_batch.py --plan plan.json --dry-run
    .venv/bin/python scripts/careers/link_seasons_batch.py --plan plan.json
"""
import argparse
import datetime
import glob
import json
import sys
from pathlib import Path

CAREER_DIRS = {"boys": Path("data/careers"), "girls": Path("data/careers/girls")}
PROCESSED = {"boys": "hs_ky_boys", "girls": "hs_ky_girls"}
LOG = Path("data/career_linking_logs/batch_links_log.json")


def roster_ids(gender, season):
    ids = set()
    for f in glob.glob(f"mt/processed_data/{PROCESSED[gender]}/{season}/*.json"):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        ids.update(str(w.get("season_wrestler_id")) for w in d.get("roster", []))
    return ids


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    plan = json.load(open(args.plan, encoding="utf-8"))

    # every currently linked (gender, season, id) -> career_id, to catch double-linking
    linked = {}
    for g, d in CAREER_DIRS.items():
        for f in glob.glob(str(d / "career_*.json")):
            c = json.load(open(f, encoding="utf-8"))
            for y, i in c["seasons"].items():
                linked[(g, int(y), str(i))] = c["career_id"]

    roster_cache = {}
    applied, skipped = [], []
    for e in plan:
        g, cid, season, wid = e["gender"], e["career_id"], int(e["season"]), str(e["season_wrestler_id"])
        path = CAREER_DIRS[g] / f"{cid}.json"

        def skip(why):
            skipped.append((e, why))

        if not path.exists():
            skip("career file not found")
            continue
        career = json.load(open(path, encoding="utf-8"))
        have = career["seasons"].get(str(season))
        if have is not None:
            skip("already linked (same id)" if str(have) == wid else f"career already has season {season} with id {have}")
            continue
        if (g, season) not in roster_cache:
            roster_cache[(g, season)] = roster_ids(g, season)
        if wid not in roster_cache[(g, season)]:
            skip("season_wrestler_id not in the processed roster for that season")
            continue
        other = linked.get((g, season, wid))
        if other:
            skip(f"id already linked to {other}")
            continue
        career["seasons"][str(season)] = wid
        linked[(g, season, wid)] = cid
        if not args.dry_run:
            path.write_text(json.dumps(career, indent=2, ensure_ascii=False), encoding="utf-8")   # same formatting as the existing files
        applied.append(e)

    print(f"{'DRY RUN: ' if args.dry_run else ''}{len(applied)} link(s) applied, {len(skipped)} skipped")
    for e, why in skipped:
        print(f"  SKIPPED {e['gender']} {e['career_id']} {e['season']} {e['season_wrestler_id']}: {why}")
    if applied and not args.dry_run:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        log = json.load(open(LOG, encoding="utf-8")) if LOG.exists() else []
        stamp = datetime.datetime.now().isoformat(timespec="seconds")
        log.extend({**e, "applied_at": stamp, "plan_file": Path(args.plan).name} for e in applied)
        LOG.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Logged to {LOG}")
    seasons = sorted({(e["gender"], int(e["season"])) for e in applied})
    print("Affected (gender, season):", seasons)


if __name__ == "__main__":
    sys.exit(main())
