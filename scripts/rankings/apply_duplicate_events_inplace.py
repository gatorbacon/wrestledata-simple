#!/usr/bin/env python3
"""
Apply the human-approved duplicate-event removals DIRECTLY to already-saved weight_class_*.json files.

Why this exists: `load_data.py -save` applies the approved removals automatically (that is the normal path for the
current season). But re-running load_data for an OLD season regenerates every file from raw data and can silently
change things that were settled by hand back then (e.g. weight_confirmation.json decisions, because historical seasons
have no rankings_*.json so every wrestler looks "unranked" and weight changes get auto-applied). This script edits
only what the approved list says to remove and leaves everything else in the saved files untouched.

It is idempotent: a second run finds nothing left to remove (and warns "no longer detected" for the approved pairs,
which is expected after they have been applied).

Usage (from repo root):
    .venv/bin/python scripts/rankings/apply_duplicate_events_inplace.py -gender boys -season 2014
    .venv/bin/python scripts/rankings/apply_duplicate_events_inplace.py -gender boys --all-seasons
    add --dry-run to report what would be removed without writing anything.

Downstream files (relationships_*.json, matrix, wrestler/career profiles, leaderboards) are NOT rebuilt here — re-run
the pipeline steps for the affected seasons afterwards (see CLAUDE.md Known Gotcha 9).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from duplicate_events import (ROOT, _apply_approved, load_approved)  # noqa: E402

RANKINGS_DIR = ROOT / "mt" / "rankings_data"


def season_dir(gender, season):
    return RANKINGS_DIR / f"hs_ky_{gender}" / str(season)


def apply_one(gender, season, dry_run, approved_file=None, log_dir=None):
    d = season_dir(gender, season)
    files = sorted(d.glob("weight_class_*.json"))
    if not files:
        print(f"{gender} {season}: no weight_class files at {d}")
        return 0
    data = {}
    for f in files:
        data[f.stem.replace("weight_class_", "")] = json.load(open(f, encoding="utf-8"))
    before = {wc: len(v["matches"]) for wc, v in data.items()}

    removed = _apply_approved(data, season, "hs", "KY", gender, approved_file=approved_file, log_dir=log_dir)
    if dry_run or not removed:
        return removed

    for f in files:
        wc = f.stem.replace("weight_class_", "")
        if len(data[wc]["matches"]) == before[wc] and data[wc] == json.load(open(f, encoding="utf-8")):
            continue                      # untouched weight class: leave the file alone
        with open(f, "w", encoding="utf-8") as fh:
            json.dump(data[wc], fh, indent=2)
    summary_path = d / "summary.json"
    if summary_path.exists():
        summary = json.load(open(summary_path, encoding="utf-8"))
        summary["weight_classes"] = {wc: {"wrestlers": len(v["wrestlers"]), "matches": len(v["matches"])}
                                     for wc, v in data.items()}
        summary["total_wrestlers"] = sum(len(v["wrestlers"]) for v in data.values())
        summary["total_matches"] = sum(len(v["matches"]) for v in data.values())
        with open(summary_path, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2)
    print(f"  {gender} {season}: wrote {sum(before.values()) - sum(len(v['matches']) for v in data.values())} "
          f"fewer match rows across weight files (a bout can sit in two weight files).")
    return removed


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-gender", required=True, choices=["boys", "girls"])
    ap.add_argument("-season", type=int)
    ap.add_argument("--all-seasons", action="store_true", help="every season that has approved pairs")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--approved-file")
    ap.add_argument("--log-dir")
    args = ap.parse_args()

    if args.all_seasons:
        seasons = sorted({int(e["season"]) for e in load_approved(args.approved_file) if e["gender"] == args.gender})
    elif args.season:
        seasons = [args.season]
    else:
        ap.error("give -season N or --all-seasons")

    total = 0
    for s in seasons:
        total += apply_one(args.gender, s, args.dry_run, args.approved_file, args.log_dir)
    print(f"\n{'DRY RUN - ' if args.dry_run else ''}{total} duplicate bout(s) removed across {len(seasons)} season(s).")


if __name__ == "__main__":
    main()
