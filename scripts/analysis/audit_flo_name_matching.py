#!/usr/bin/env python3
"""
Audits name-matching quality between scraped FloWrestling rankings and the
actual NCAA tournament roster (all_wrestlers.json), across every touch-point
file collected so far. Answers: are we silently losing real wrestlers to
nickname/spelling mismatches, or are "unmatched" entries genuine non-qualifiers?

For every (weight, name) entry in every scraped file:
  - EXACT match: normalized full name matches directly.
  - FALLBACK match: last-name + first-initial matches a unique candidate
    (handles nickname variants, e.g. "Michael Caliendo" -> "Mikey Caliendo").
  - UNMATCHED, split into:
      - same_school_no_name_match: some wrestler from the SAME school wrestled
        that weight that year, but the name didn't match at all -- likely a
        real mismatch (bigger nickname/spelling gap than the fallback catches,
        or a genuine transfer/backup-replaced-starter case) worth reviewing by hand.
      - no_wrestler_from_school: no wrestler from that school appears at that
        weight in that year's results at all -- consistent with a genuine
        non-qualifier (injury, DNQ, moved weight/school) rather than a data bug.

Usage:
  python scripts/analysis/audit_flo_name_matching.py
  python scripts/analysis/audit_flo_name_matching.py --show-all
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

from flo_preseason_vs_score import load_tourney_results, normalize_name

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def classify(weight, name, school, by_weight_name, by_weight_lastname, by_weight_school):
    key = (weight, normalize_name(name))
    if key in by_weight_name:
        return "exact", by_weight_name[key]

    parts = normalize_name(name).split()
    if len(parts) >= 2:
        candidates = by_weight_lastname.get((weight, parts[-1], parts[0][0]))
        if candidates and len(candidates) == 1:
            return "fallback", candidates[0]

    school_matches = by_weight_school.get((weight, normalize_name(school)), [])
    if school_matches:
        return "same_school_no_name_match", school_matches
    return "no_wrestler_from_school", None


def main():
    parser = argparse.ArgumentParser(description="Audit FloWrestling name-matching quality")
    parser.add_argument("--show-all", action="store_true", help="List every same_school_no_name_match case (default: first 40)")
    args = parser.parse_args()

    results_cache = {}
    school_index_cache = {}

    counts = defaultdict(int)
    review_cases = []  # (file, weight, flo_name, flo_school, candidates)
    total = 0

    for path in sorted(DATA_DIR.glob("*/flo-preseason-rankings/*.json")):
        data = json.loads(path.read_text())
        tourney_year = data["season"]
        if tourney_year not in results_cache:
            by_weight_name, by_weight_lastname = load_tourney_results(tourney_year)
            results_cache[tourney_year] = (by_weight_name, by_weight_lastname)
            by_weight_school = defaultdict(list)
            for rec in by_weight_name.values():
                by_weight_school[(rec["weight"], normalize_name(rec["team"]))].append(rec["name"])
            school_index_cache[tourney_year] = by_weight_school
        by_weight_name, by_weight_lastname = results_cache[tourney_year]
        by_weight_school = school_index_cache[tourney_year]

        for weight_str, entries in data["weights"].items():
            weight = int(weight_str)
            for e in entries:
                total += 1
                kind, extra = classify(
                    weight, e["name"], e["school"], by_weight_name, by_weight_lastname, by_weight_school
                )
                counts[kind] += 1
                if kind == "same_school_no_name_match":
                    review_cases.append((path.relative_to(PROJECT_ROOT), weight, e["name"], e["school"], extra))

    print("=" * 90)
    print(f"Name-matching audit across {total} scraped (weight, name) entries")
    print("=" * 90)
    for kind in ["exact", "fallback", "same_school_no_name_match", "no_wrestler_from_school"]:
        n = counts[kind]
        pct = 100 * n / total if total else 0
        print(f"  {kind:<28} {n:>6}  ({pct:5.1f}%)")

    print(f"\nTotal matched (exact + fallback): {counts['exact'] + counts['fallback']} "
          f"({100 * (counts['exact'] + counts['fallback']) / total:.1f}%)")
    print(f"Total unmatched (both kinds):     {counts['same_school_no_name_match'] + counts['no_wrestler_from_school']} "
          f"({100 * (counts['same_school_no_name_match'] + counts['no_wrestler_from_school']) / total:.1f}%)")

    if review_cases:
        print(f"\n{'='*90}")
        print(f"SAME-SCHOOL NAME MISMATCHES -- worth reviewing by hand ({len(review_cases)} total)")
        print(f"{'='*90}")
        shown = review_cases if args.show_all else review_cases[:40]
        for path, weight, flo_name, flo_school, candidates in shown:
            print(f"  [{path}] {weight}lb  Flo: '{flo_name}' ({flo_school})  ->  roster has: {candidates}")
        if not args.show_all and len(review_cases) > 40:
            print(f"  ... and {len(review_cases) - 40} more (use --show-all to see everything)")
    else:
        print("\nNo same-school name mismatches found -- every unmatched entry has no same-school/weight "
              "wrestler in the results at all, consistent with genuine non-qualifiers.")


if __name__ == "__main__":
    main()
