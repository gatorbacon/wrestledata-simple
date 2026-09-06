#!/usr/bin/env python3
"""
Attach round/bracket labels to scraped NCAA bout-detail records.

scrape_ncaa_bout_detail.py pulls period-by-period, timestamped match detail
from TrackWrestling's classic bracket viewer, but that source only exposes a
per-weight-class sequential bout number — no round. Round labels already
exist in data/{year}/ncaa-tourney/parsed/matches.json (built by
parse_ncaa_results.py from the separate results.txt scrape), using the
existing round vocabulary: PIG, R32, R16, QF, SF, Final, C_PIG, C_R1-C_R4,
C_QF, C_SF, 3rd, 5th, 7th.

This script joins the two sources by (weight, winner_name, loser_name) and
writes the round/bracket back onto each bout-detail record in place.

Known gap: TrackWrestling's classic bracket viewer's boutNumber sequence
(what scrape_ncaa_bout_detail.py walks) does not appear to include pigtail
(play-in) matches — PIG / C_PIG in the round vocabulary. Those matches exist
in matches.json but currently have no bout-detail counterpart to reconcile
against, so they're reported as unmatched rather than silently dropped.

Usage:
  python scripts/ncaa/reconcile_bout_detail.py --year 2026
  python scripts/ncaa/reconcile_bout_detail.py --year 2026 --weights 125,133
  python scripts/ncaa/reconcile_bout_detail.py --year 2026 --dry-run
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

WEIGHT_CLASSES = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]


def load_matches_lookup(year: int, weight: int) -> dict[tuple[str, str], dict]:
    matches_path = DATA_DIR / str(year) / "ncaa-tourney" / "parsed" / "matches.json"
    if not matches_path.exists():
        return {}
    matches = json.loads(matches_path.read_text())
    return {
        (m["winner_name"], m["loser_name"]): m
        for m in matches
        if m["weight"] == weight
    }


def reconcile_weight(year: int, weight: int, dry_run: bool = False) -> tuple[int, int]:
    """
    Returns (matched_count, unmatched_count) for this weight class.
    """
    bout_path = DATA_DIR / str(year) / "ncaa-tourney" / "bout_detail" / f"{weight}.json"
    if not bout_path.exists():
        print(f"   [SKIP] weight {weight}: no bout_detail file yet")
        return (0, 0)

    bouts = json.loads(bout_path.read_text())
    lookup = load_matches_lookup(year, weight)
    if not lookup:
        print(f"   [WARN] weight {weight}: no matches.json entries found — is parse_ncaa_results.py run for {year}?")
        return (0, len(bouts))

    matched = 0
    unmatched = []
    for bout in bouts:
        key = (bout["winner"]["name"], bout["loser"]["name"])
        m = lookup.get(key)
        if m is None:
            unmatched.append(bout)
            bout["round"] = None
            bout["bracket"] = None
            continue
        bout["round"] = m["round"]
        bout["bracket"] = m["bracket"]
        matched += 1

    if unmatched:
        print(f"   [WARN] weight {weight}: {len(unmatched)} bout(s) could not be matched to a round:")
        for b in unmatched:
            print(f"       bout {b['bout_number']}: {b['winner']['name']} def. {b['loser']['name']} ({b['winner']['score']}-{b['loser']['score']})")

    unmatched_match_keys = set(lookup) - {
        (b["winner"]["name"], b["loser"]["name"]) for b in bouts
    }
    if unmatched_match_keys:
        print(f"   [INFO] weight {weight}: {len(unmatched_match_keys)} round(s) in matches.json have no scraped bout-detail counterpart:")
        for k in unmatched_match_keys:
            m = lookup[k]
            print(f"       {m['round']} | {k[0]} def. {k[1]} ({m['score']})")

    if not dry_run:
        bout_path.write_text(json.dumps(bouts, indent=2, ensure_ascii=False))

    return (matched, len(unmatched))


def main():
    parser = argparse.ArgumentParser(description="Attach round labels to scraped NCAA bout detail")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--weights", type=str, default=None, help="Comma-separated weight classes (default: all 10)")
    parser.add_argument("--dry-run", action="store_true", help="Report matches without writing files")
    args = parser.parse_args()

    weights = (
        [int(w.strip()) for w in args.weights.split(",")]
        if args.weights
        else WEIGHT_CLASSES
    )

    print(f"Reconciling bout detail with round labels for {args.year}...")
    total_matched, total_unmatched = 0, 0
    for weight in weights:
        print(f"\nWeight {weight}:")
        matched, unmatched = reconcile_weight(args.year, weight, dry_run=args.dry_run)
        total_matched += matched
        total_unmatched += unmatched

    print(f"\n[DONE] {total_matched} bouts tagged with round, {total_unmatched} unmatched.")


if __name__ == "__main__":
    main()
