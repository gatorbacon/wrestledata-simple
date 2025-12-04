#!/usr/bin/env python3
"""
matches_and_diff_by_rank.py

Given a season and a maximum rank R, this script:

  1. Uses ranked wrestler IDs from mt/rankings_data/{season}/rankings_*.json.
  2. Looks at all wrestlers ranked from 1 through R (across all weights).
  3. Computes the average number of matches wrestled by those wrestlers
     (including pins and other non-scored results, but excluding BYEs / NoResult).
  4. Filters to wrestlers who have wrestled at least (50% of that average + 1 match).
  5. Among that filtered set, computes for each wrestler:
       - Average point differential per match (scored matches only).
       - PD7 (point differential per 7 minutes), using the same timing
         assumptions as in wrestler_stats.py.
  6. Prints:
       - Top 10 and bottom 10 by average point differential.
       - Top 10 and bottom 10 by PD7.

Notes:
  - Scored matches are those where a numeric score like '10-3' can be parsed.
  - Falls/pins are included in the full-match count for thresholds, but are
    excluded from PD7, since we typically do not know the true score at the
    stoppage time.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict

from load_data import load_team_data
from scoringbyrank import _load_rank_map, _parse_score_from_result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compute average match count for ranked wrestlers and list "
            "top/bottom 10 by point differential and PD7."
        )
    )
    parser.add_argument(
        "-season",
        type=int,
        required=True,
        help="Season year (e.g., 2026).",
    )
    parser.add_argument(
        "-maxrank",
        type=int,
        required=True,
        help="Include wrestlers ranked from 1 through this rank (across all weights).",
    )
    return parser.parse_args()


def estimate_match_duration_seconds(result_str: str) -> int:
    """
    Estimate match duration in seconds from a result string.

    Rules:
      - Default for a standard match: 7:00 (420 seconds).
      - Sudden Victory (SV-1, SV-2, SV-3): assume 8:15 total (495 seconds).
      - Tie Breakers (TB-1, TB-2): assume 10:00 total (600 seconds).
      - Tech fall (TF ... MM:SS): if a time like '5:21' is present, use that;
        otherwise fall back to 7:00.

    This mirrors the PD7 timing logic used in wrestler_stats.py so that it
    can be reused consistently for Hodge-style scoring later.
    """
    base = 7 * 60  # 7 minutes
    if not result_str:
        return base

    s = result_str.lower()

    # Tie breakers first (10:00 total)
    if "tb-1" in s or "tb-2" in s:
        return 10 * 60

    # Sudden victory (8:15 total)
    if "sv-1" in s or "sv-2" in s or "sv-3" in s or "sudden victory" in s:
        return 8 * 60 + 15

    # Tech fall with an explicit time (e.g. 'TF 21-3 5:21')
    if "tf" in s:
        times = list(re.finditer(r"(\d+):(\d{2})", result_str))
        if times:
            m = times[-1]
            minutes = int(m.group(1))
            seconds = int(m.group(2))
            return minutes * 60 + seconds

    return base


def compute_per_wrestler_stats(season: int, max_rank: int) -> Dict[str, Dict]:
    """
    For all wrestlers ranked 1..max_rank, compute:
      - full_matches (including pins / non-scored results, excluding BYEs)
      - scored_matches (numeric score known)
      - total_diff (sum of signed point differentials)
      - pd7_diff, pd7_seconds, pd7_matches
      - basic identity: name, team, rank
    """
    rank_by_id = _load_rank_map(season)
    if not rank_by_id:
        return {}

    # Only keep wrestlers within the requested rank range.
    rank_by_id = {wid: r for wid, r in rank_by_id.items() if r <= max_rank}
    if not rank_by_id:
        return {}

    teams = load_team_data(season)

    stats_by_id: Dict[str, Dict] = {}

    for team in teams:
        team_name = team.get("team_name", "Unknown")

        for wrestler in team.get("roster", []):
            wid = str(wrestler.get("season_wrestler_id") or "")
            if not wid or wid == "null" or wid not in rank_by_id:
                continue

            wname = wrestler.get("name", "Unknown")
            rank = int(rank_by_id[wid])

            s = stats_by_id.get(wid)
            if s is None:
                s = {
                    "wrestler_id": wid,
                    "name": wname,
                    "team": team_name,
                    "rank": rank,
                    "full_matches": 0,
                    "scored_matches": 0,
                    "total_diff": 0.0,
                    "pd7_diff": 0.0,
                    "pd7_seconds": 0,
                    "pd7_matches": 0,
                }
                stats_by_id[wid] = s

            matches = wrestler.get("matches", []) or []
            for m in matches:
                # Skip byes / no-result
                result = m.get("result", "") or ""
                if result in ("BYE", "NoResult"):
                    continue
                summary = m.get("summary", "") or ""
                if "received a bye" in summary.lower():
                    continue

                # For full match count, require a valid opponent_id (mirrors
                # matches_and_points_by_rank.py and load_data.py semantics).
                opponent_id = m.get("opponent_id")
                if opponent_id and opponent_id not in ("null", ""):
                    s["full_matches"] += 1

                # Points / differential stats require a numeric score.
                score_pair = _parse_score_from_result(result)
                if not score_pair:
                    continue

                winner_pts, loser_pts = score_pair

                # Determine if this wrestler is the winner or loser.
                winner_name = m.get("winner_name", "") or ""
                loser_name = m.get("loser_name", "") or ""
                winner_team = m.get("winner_team", "") or ""
                loser_team = m.get("loser_team", "") or ""

                is_winner = (
                    wid == str(m.get("winner_id") or "")
                    or (wname == winner_name and team_name == winner_team)
                )
                is_loser = (
                    wid == str(m.get("loser_id") or "")
                    or (wname == loser_name and team_name == loser_team)
                )

                if not (is_winner or is_loser):
                    continue

                # Signed point differential from this wrestler's perspective.
                diff = float(winner_pts - loser_pts)
                if is_loser:
                    diff = -diff

                s["total_diff"] += diff
                s["scored_matches"] += 1

                # PD7: skip falls/pins (we don't trust scores for these),
                # but otherwise accumulate both diff and estimated time.
                res_lower = result.lower()
                if "fall" in res_lower or "pin" in res_lower or "pinned" in res_lower:
                    continue

                duration_seconds = estimate_match_duration_seconds(result)
                s["pd7_diff"] += diff
                s["pd7_seconds"] += duration_seconds
                s["pd7_matches"] += 1

    return stats_by_id


def compute_and_print_stats(season: int, max_rank: int) -> None:
    stats_by_id = compute_per_wrestler_stats(season, max_rank)
    if not stats_by_id:
        print(f"No ranked wrestler stats found for season {season} (max rank {max_rank}).")
        return

    # Average matches (full_matches) across ranked wrestlers.
    full_matches_list = [s["full_matches"] for s in stats_by_id.values()]
    if not full_matches_list:
        print("No full match counts available; aborting.")
        return

    avg_matches = sum(full_matches_list) / float(len(full_matches_list))

    print(f"\nSeason {season} — ranks 1–{max_rank}")
    print(f"Average number of matches wrestled: {avg_matches:.2f}")

    # Threshold: at least 50% of average matches + 1.
    min_matches_threshold = 0.5 * avg_matches + 1.0

    eligible = [
        s
        for s in stats_by_id.values()
        if s["full_matches"] >= min_matches_threshold and s["scored_matches"] > 0
    ]

    if not eligible:
        print(
            "No wrestlers have wrestled at least 50% of the average number of matches plus one "
            f"(threshold: {min_matches_threshold:.2f}), with at least one scored match."
        )
        return

    print(
        "Wrestlers meeting threshold "
        f"(>= 50% of average matches + 1, i.e. >= {min_matches_threshold:.2f}): "
        f"{len(eligible)}"
    )

    # Compute per-wrestler averages.
    for s in eligible:
        scored = s["scored_matches"]
        s["avg_point_diff"] = s["total_diff"] / float(scored) if scored > 0 else 0.0

        if s["pd7_seconds"] > 0:
            s["pd7"] = s["pd7_diff"] * (7 * 60) / float(s["pd7_seconds"])
        else:
            s["pd7"] = None

    # Leaders by average point differential per match.
    eligible_diff = [s for s in eligible if s["scored_matches"] > 0]
    if eligible_diff:
        top_diff = sorted(
            eligible_diff,
            key=lambda s: (s["avg_point_diff"], s["scored_matches"]),
            reverse=True,
        )[:10]
        bottom_diff = sorted(
            eligible_diff,
            key=lambda s: (s["avg_point_diff"], s["scored_matches"]),
        )[:10]
    else:
        top_diff = []
        bottom_diff = []

    # Leaders by PD7 (exclude wrestlers without any PD7-eligible matches).
    eligible_pd7 = [s for s in eligible if s.get("pd7") is not None]
    if eligible_pd7:
        top_pd7 = sorted(
            eligible_pd7,
            key=lambda s: (s["pd7"], s["pd7_matches"]),
            reverse=True,
        )[:10]
        bottom_pd7 = sorted(
            eligible_pd7,
            key=lambda s: (s["pd7"], s["pd7_matches"]),
        )[:10]
    else:
        top_pd7 = []
        bottom_pd7 = []

    def _print_diff_list(title: str, subset) -> None:
        print(f"\n{title}")
        if not subset:
            print("  (no wrestlers)")
            return
        for idx, s in enumerate(subset, start=1):
            name = s["name"]
            team = s["team"]
            avg_diff = s["avg_point_diff"]
            full_matches = int(s["full_matches"])
            scored = int(s["scored_matches"])
            print(
                f"{idx}. {name} ({team}) - {avg_diff:+.2f} point diff per match "
                f"({full_matches} total, {scored} scored)"
            )

    def _print_pd7_list(title: str, subset) -> None:
        print(f"\n{title}")
        if not subset:
            print("  (no wrestlers)")
            return
        for idx, s in enumerate(subset, start=1):
            name = s["name"]
            team = s["team"]
            pd7_val = s["pd7"]
            full_matches = int(s["full_matches"])
            pd7_matches = int(s["pd7_matches"])
            print(
                f"{idx}. {name} ({team}) - {pd7_val:+.2f} PD7 "
                f"({full_matches} total, {pd7_matches} PD7 matches)"
            )

    _print_diff_list(
        "Top 10 wrestlers by average point differential (min 50% of average matches + 1):",
        top_diff,
    )
    _print_diff_list(
        "Bottom 10 wrestlers by average point differential (min 50% of average matches + 1):",
        bottom_diff,
    )

    _print_pd7_list(
        "Top 10 wrestlers by PD7 (min 50% of average matches + 1):",
        top_pd7,
    )
    _print_pd7_list(
        "Bottom 10 wrestlers by PD7 (min 50% of average matches + 1):",
        bottom_pd7,
    )


def main() -> None:
    args = parse_args()
    compute_and_print_stats(args.season, args.maxrank)


if __name__ == "__main__":
    main()


