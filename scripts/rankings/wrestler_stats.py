#!/usr/bin/env python3
"""
wrestler_stats.py

Quickly calculate a wrestler's basic statistics for a given season.

Given:
  - A season (e.g., 2026)
  - A name fragment (e.g., "Roark")

This script:
  - Lets you choose the exact wrestler (name + team + weight) from matches.
  - Scans that wrestler's season matches from mt/processed_data/{season}.
  - Computes:
      * Wins, losses, win%
      * Falls (pins), fall% (falls / wins)
      * Average points scored (only matches with a numeric score)
      * Average points allowed (only matches with a numeric score)
      * Average point differential (where score is known)
      * Overall ranking (best rank across all rankings_*.json), if any
      * Weight class (from roster)
      * Team
  - Prints a clean, console-friendly summary.

Usage (from repo root):

    python scripts/rankings/wrestler_stats.py -season 2026
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from load_data import load_team_data
from scoringbyrank import _load_rank_map, _parse_score_from_result


@dataclass
class WrestlerRef:
    wrestler_id: str
    name: str
    team: str
    weight_class: str
    raw: Dict


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute basic statistics for a wrestler in a given season."
    )
    parser.add_argument(
        "-season",
        type=int,
        required=True,
        help="Season year (e.g., 2026).",
    )
    return parser.parse_args()


def build_wrestler_index(season: int) -> List[WrestlerRef]:
    teams = load_team_data(season)
    wrestlers: List[WrestlerRef] = []

    for team in teams:
        team_name = team.get("team_name", "Unknown")
        for w in team.get("roster", []):
            wid = str(w.get("season_wrestler_id") or "")
            if not wid or wid == "null":
                continue
            name = w.get("name", "Unknown")
            wc = str(w.get("weight_class", "") or "")
            wrestlers.append(
                WrestlerRef(
                    wrestler_id=wid,
                    name=name,
                    team=team_name,
                    weight_class=wc,
                    raw=w,
                )
            )

    return wrestlers


def search_wrestlers(
    wrestlers: List[WrestlerRef],
    query: str,
) -> List[WrestlerRef]:
    q = query.lower()
    results: List[WrestlerRef] = []
    for w in wrestlers:
        haystack = f"{w.name} {w.team} {w.weight_class}".lower()
        if q in haystack:
            results.append(w)
    return results


def prompt_for_wrestler(wrestlers: List[WrestlerRef]) -> Optional[WrestlerRef]:
    while True:
        q = input(
            "Enter wrestler name fragment (or blank to exit, e.g. 'Roark'): "
        ).strip()
        if not q:
            return None

        matches = search_wrestlers(wrestlers, q)
        if not matches:
            print("  No wrestlers found matching that fragment. Try again.\n")
            continue

        print(f"\nFound {len(matches)} wrestler(s):")
        for idx, w in enumerate(matches, start=1):
            wc_display = w.weight_class or "?"
            print(f"  {idx:2d}) {w.name} ({w.team}, {wc_display})")

        while True:
            sel = input(
                f"Select wrestler by number (1-{len(matches)}), or blank to search again: "
            ).strip()
            if not sel:
                print()
                break
            try:
                num = int(sel)
                if 1 <= num <= len(matches):
                    chosen = matches[num - 1]
                    print(f"\nSelected: {chosen.name} ({chosen.team}, {chosen.weight_class})\n")
                    return chosen
            except ValueError:
                pass
            print("  Invalid selection; please enter a valid number.")


def compute_stats_for_wrestler(
    season: int,
    ref: WrestlerRef,
) -> Dict[str, object]:
    """
    Scan all matches for this wrestler in the season and compute summary stats.
    """
    wins = 0
    losses = 0
    falls = 0

    pts_for = 0.0
    pts_against = 0.0
    pts_matches = 0

    # For reusable PD7 (point differential per 7 minutes) calculation:
    # We accumulate total point differential and total match time (in seconds)
    # over matches where a numeric score is known and the result is not a fall.
    pd7_total_diff = 0.0
    pd7_total_seconds = 0
    pd7_matches = 0

    team_name = ref.team
    wname = ref.name
    wid = ref.wrestler_id

    # The raw wrestler entry already has all matches for this season for that team.
    matches = ref.raw.get("matches", []) or []

    def estimate_match_duration_seconds(result_str: str) -> int:
        """
        Estimate match duration in seconds from a result string.

        Rules:
          - Default for a standard match: 7:00 (420 seconds).
          - Sudden Victory (SV-1, SV-2, SV-3): assume 8:15 total (495 seconds).
          - Tie Breakers (TB-1, TB-2): assume 10:00 total (600 seconds).
          - Tech fall (TF ... MM:SS): if a time like '5:21' is present, use that;
            otherwise fall back to 7:00.

        This is written as a standalone helper so it can be reused elsewhere
        (e.g., in Hodge-score style computations).
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
            import re

            # Find all MM:SS time tokens; use the last one in the string.
            times = list(re.finditer(r"(\d+):(\d{2})", result_str))
            if times:
                m = times[-1]
                minutes = int(m.group(1))
                seconds = int(m.group(2))
                return minutes * 60 + seconds

        return base

    for m in matches:
        # Skip byes / no-result
        result = m.get("result", "") or ""
        if result in ("BYE", "NoResult"):
            continue
        summary = m.get("summary", "") or ""
        if "received a bye" in summary.lower():
            continue

        # Determine if this wrestler is the winner or loser in this match.
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
            # Can't reliably tell which side we are.
            continue

        # Update record.
        if is_winner:
            wins += 1
        else:
            losses += 1

        # Falls: only count when this wrestler wins and result indicates a fall.
        if is_winner:
            res_lower = result.lower()
            if "fall" in res_lower or "pin" in res_lower or "pinned" in res_lower:
                falls += 1

        # Points-based stats: only when we can parse a numeric score.
        score_pair = _parse_score_from_result(result)
        if score_pair:
            winner_pts, loser_pts = score_pair
            if is_winner:
                pts_for += float(winner_pts)
                pts_against += float(loser_pts)
            else:
                pts_for += float(loser_pts)
                pts_against += float(winner_pts)
            pts_matches += 1

            # PD7: skip matches that end in a fall/pin; otherwise accumulate
            # both point differential and estimated match time.
            res_lower = result.lower()
            if "fall" in res_lower or "pin" in res_lower or "pinned" in res_lower:
                # We don't trust the score for fall outcomes; ignore for PD7.
                continue

            # Signed point differential from this wrestler's perspective.
            diff = float(winner_pts - loser_pts)
            if is_loser:
                diff = -diff

            duration_seconds = estimate_match_duration_seconds(result)
            pd7_total_diff += diff
            pd7_total_seconds += duration_seconds
            pd7_matches += 1

    total_matches = wins + losses
    win_pct = (wins / total_matches * 100.0) if total_matches > 0 else 0.0
    fall_pct = (falls / wins * 100.0) if wins > 0 else 0.0

    avg_for = (pts_for / pts_matches) if pts_matches > 0 else 0.0
    avg_against = (pts_against / pts_matches) if pts_matches > 0 else 0.0
    avg_diff = avg_for - avg_against

    # Point differential per 7 minutes.
    if pd7_total_seconds > 0:
        pd7 = pd7_total_diff * (7 * 60) / float(pd7_total_seconds)
    else:
        pd7 = 0.0

    # Ranking (best overall rank across all weights for this season).
    rank_by_id = _load_rank_map(season)
    overall_rank = rank_by_id.get(ref.wrestler_id)

    return {
        "wins": wins,
        "losses": losses,
        "win_pct": win_pct,
        "falls": falls,
        "fall_pct": fall_pct,
        "avg_points_for": avg_for,
        "avg_points_against": avg_against,
        "avg_point_diff": avg_diff,
        "points_matches": pts_matches,
        "pd7": pd7,
        "pd7_matches": pd7_matches,
        "overall_rank": overall_rank,
        "team": team_name,
        "weight_class": ref.weight_class,
        "name": ref.name,
        "wrestler_id": ref.wrestler_id,
    }


def print_stats(season: int, stats: Dict[str, object]) -> None:
    name = stats["name"]
    team = stats["team"]
    weight_class = stats["weight_class"] or "?"
    overall_rank = stats["overall_rank"]

    wins = stats["wins"]
    losses = stats["losses"]
    win_pct = stats["win_pct"]
    falls = stats["falls"]
    fall_pct = stats["fall_pct"]

    avg_for = stats["avg_points_for"]
    avg_against = stats["avg_points_against"]
    avg_diff = stats["avg_point_diff"]
    pts_matches = stats["points_matches"]
    pd7 = stats["pd7"]
    pd7_matches = stats["pd7_matches"]

    print("=" * 48)
    print(f"Wrestler Stats — Season {season}")
    print("=" * 48)
    print(f"Name:      {name}")
    print(f"Team:      {team}")
    print(f"Weight:    {weight_class}")
    if overall_rank is not None:
        print(f"Ranking:   #{overall_rank}")
    else:
        print("Ranking:   Unranked")
    print()

    print(f"Record:    {wins}-{losses}  ({win_pct:5.1f}% win)")
    print(f"Falls:     {falls}  ({fall_pct:5.1f}% of wins)")
    print()

    if pts_matches > 0:
        print("Scored matches (numeric score known):")
        print(f"  Matches counted:      {pts_matches}")
        print(f"  Avg points for:       {avg_for:5.2f}")
        print(f"  Avg points against:   {avg_against:5.2f}")
        print(f"  Avg point differential:{avg_diff:6.2f}")
        if pd7_matches > 0:
            print()
            print("Point differential per 7 minutes (PD7):")
            print(f"  Matches counted:      {pd7_matches}")
            print(f"  PD per 7 minutes:     {pd7:5.2f}")
    else:
        print("No matches with parsable numeric scores were found for this wrestler.")
    print()


def main() -> None:
    args = parse_args()
    season = args.season

    wrestlers = build_wrestler_index(season)
    print(f"Loaded {len(wrestlers)} wrestlers for season {season}.\n")

    while True:
        ref = prompt_for_wrestler(wrestlers)
        if ref is None:
            print("Exiting.")
            break

        stats = compute_stats_for_wrestler(season, ref)
        print_stats(season, stats)


if __name__ == "__main__":
    main()


