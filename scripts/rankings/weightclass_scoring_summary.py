#!/usr/bin/env python3
"""
weightclass_scoring_summary.py

Super simple utility script:

For a given season, prints for each weight class:
  - Average number of (valid, scored, non-fall) matches per wrestler
  - Average PA7 (points allowed per 7 minutes)
  - Average PF7 (points for per 7 minutes)

At the end it also prints a single "ALL" line with the same stats
aggregated across all weight classes.

The definitions of "valid match", PA7 and PF7 are identical to those
used in the normalized_scoring / ANPPM code.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from typing import Dict

from normalized_scoring import build_all_matches
from load_data import load_team_data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Show average matches, PA7 and PF7 by weight class."
    )
    parser.add_argument(
        "-season",
        type=int,
        required=True,
        help="Season year (e.g., 2026).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    season = args.season

    # We don't need rank information here; pass an empty dict.
    (
        wrestlers,
        matches_by_wrestler,
        _pa7_sum_by_wrestler,
        _pa7_count_by_wrestler,
        pa7_sum_by_weight,
        pa7_count_by_weight,
        _excluded_invalid,
    ) = build_all_matches(season, {})

    # PF7 and match counts by weight class — reuse per-match pd7_for values.
    # Here we count matches by the actual match weight (e.g., '125'),
    # not by a wrestler's roster weight class, and each "side" of a bout
    # counts once (consistent with how PA7/PF7 are pooled elsewhere).
    pf7_sum_by_weight: Dict[str, float] = defaultdict(float)
    pf7_count_by_weight: Dict[str, int] = defaultdict(int)
    match_counts_by_weight: Dict[str, int] = defaultdict(int)

    for _wid, mlist in matches_by_wrestler.items():
        for e in mlist:
            wc = e.get("weight_class", "")
            if not wc:
                continue
            wc = str(wc)
            pf7_sum_by_weight[wc] += float(e.get("pd7_for", 0.0))
            pf7_count_by_weight[wc] += 1
            match_counts_by_weight[wc] += 1

    # Pin-rate (LPR) by weight from raw match data (all bouts, deduped).
    teams = load_team_data(season)
    pin_count_by_weight: Dict[str, int] = defaultdict(int)
    bout_count_by_weight: Dict[str, int] = defaultdict(int)
    seen_bouts = set()

    for team in teams:
        for w in team.get("roster", []) or []:
            wid = str(w.get("season_wrestler_id") or "")
            if not wid or wid == "null":
                continue
            for m in w.get("matches", []) or []:
                result = m.get("result", "") or ""
                summary = m.get("summary", "") or ""
                if result in ("BYE", "NoResult") or "received a bye" in summary.lower():
                    continue
                opp_id = str(m.get("opponent_id") or "")
                if not opp_id or opp_id == "null":
                    continue
                date = m.get("date", "") or ""
                w1, w2 = sorted([wid, opp_id])
                bout_key = (w1, w2, date, result)
                if bout_key in seen_bouts:
                    continue
                seen_bouts.add(bout_key)
                wc = str(m.get("weight", "") or "")
                if not wc:
                    continue
                bout_count_by_weight[wc] += 1
                s = result.lower()
                if "fall" in s or "pin" in s or "pinned" in s:
                    pin_count_by_weight[wc] += 1

    # Prepare overall accumulators for the "ALL" row.
    all_match_total = 0
    total_pf7_sum = 0.0
    total_pf7_count = 0
    total_bouts_all = 0
    total_pins_all = 0

    print(f"Weight-class scoring summary — Season {season}")
    print(
        f"{'Weight':>6}  {'TotalMatches':>12}  {'LSR':>8}  {'LPR%':>8}"
    )

    for wc in sorted(match_counts_by_weight.keys(), key=int):
        total_matches_wc = match_counts_by_weight[wc]
        if total_matches_wc == 0:
            continue

        pf_sum = float(pf7_sum_by_weight.get(wc, 0.0))
        pf_cnt = int(pf7_count_by_weight.get(wc, 0))

        lsr = (pf_sum / pf_cnt) if pf_cnt > 0 else 0.0

        bouts_wc = bout_count_by_weight.get(wc, 0)
        pins_wc = pin_count_by_weight.get(wc, 0)
        lpr = (pins_wc / bouts_wc * 100.0) if bouts_wc > 0 else 0.0

        all_match_total += total_matches_wc
        total_pf7_sum += pf_sum
        total_pf7_count += pf_cnt
        total_bouts_all += bouts_wc
        total_pins_all += pins_wc

        print(
            f"{wc:>6}  {total_matches_wc:12d}  {lsr:8.2f}  {lpr:8.2f}"
        )

    # Overall "ALL" row across all weights.
    overall_lsr = (
        total_pf7_sum / float(total_pf7_count) if total_pf7_count > 0 else 0.0
    )
    overall_lpr = (
        total_pins_all / float(total_bouts_all) * 100.0
        if total_bouts_all > 0
        else 0.0
    )

    print("-" * 48)
    print(
        f"{'ALL':>6}  {all_match_total:12d}  "
        f"{overall_lsr:8.2f}  {overall_lpr:8.2f}"
    )


if __name__ == "__main__":
    main()


