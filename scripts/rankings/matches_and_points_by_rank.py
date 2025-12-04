#!/usr/bin/env python3
"""
matches_and_points_by_rank.py

Given a season and a maximum rank R, this script:

  1. Uses the same ranked-wrestler + match data pipeline as scoringbyrank.py.
  2. Looks at all wrestlers ranked from 1 through R (across all weights).
  3. Computes the average number of matches wrestled by those wrestlers
     (including pins and other non-scored results, but excluding BYEs / NoResult).
  4. Filters to wrestlers who have wrestled at least (50% of that average + 1 match).
  5. Among that filtered set, prints:
       - Top 10 wrestlers by points scored per match.
       - Bottom 10 wrestlers by points scored per match.

Each wrestler line is printed as:

    "1. Joe Smith - 19.2 points per match (5)"

where 5 is the total number of matches (including pins) for that wrestler.

CLI example:

    python scripts/rankings/matches_and_points_by_rank.py -season 2026 -maxrank 25
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict

# Reuse the exact same data-loading logic as scoringbyrank.py
from scoringbyrank import build_matches_df, _load_rank_map


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compute average match count for ranked wrestlers and list "
            "top/bottom 10 by points per match."
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


def _build_full_match_counts(season: int, max_rank: int) -> Dict[str, int]:
    """
    Build a mapping of wrestler_id -> total matches for ranked wrestlers
    (1..max_rank), where "matches" includes pins and other non-scored results,
    but excludes BYEs / NoResult / explicit byes in the summary.
    """
    rank_by_id = _load_rank_map(season)
    if not rank_by_id:
        return {}

    # Only keep wrestlers within the requested rank range.
    rank_by_id = {wid: r for wid, r in rank_by_id.items() if r <= max_rank}

    data_dir = Path("mt/processed_data") / str(season)
    if not data_dir.exists():
        return {}

    counts: Dict[str, int] = defaultdict(int)

    for team_file in sorted(data_dir.glob("*.json")):
        try:
            with team_file.open("r", encoding="utf-8") as f:
                team_data = json.load(f)
        except Exception:
            continue

        for wrestler in team_data.get("roster", []):
            wid = str(wrestler.get("season_wrestler_id") or "")
            if wid not in rank_by_id:
                continue

            for match in wrestler.get("matches", []):
                # Skip byes / no-result matches, mirroring the logic in load_data.py.
                result = match.get("result", "")
                if result in ("BYE", "NoResult"):
                    continue
                summary = match.get("summary", "")
                if isinstance(summary, str) and "received a bye" in summary.lower():
                    continue

                # Require a valid opponent ID, same as in load_data.py.
                opponent_id = match.get("opponent_id")
                if not opponent_id or opponent_id in ("null", ""):
                    continue

                counts[wid] += 1

    return counts


def compute_and_print_stats(season: int, max_rank: int) -> None:
    # Build per-match DataFrame for all ranked wrestlers up to max_rank
    # (only matches with numeric scores are included here).
    df = build_matches_df(season, max_rank=max_rank)

    if df is None or df.empty:
        print(f"No ranked match data found for season {season} (max rank {max_rank}).")
        return

    # Aggregate to per‑wrestler stats for matches that have numeric scores.
    # We keep name / team / rank for context, plus:
    #   - matches: number of matches with numeric scores
    #   - total_points: total points from those scored matches
    per_wrestler = (
        df.groupby("wrestler_id")
        .agg(
            wrestler_name=("wrestler_name", "first"),
            team=("team", "first"),
            rank=("rank", "min"),
            matches=("points_scored", "size"),
            total_points=("points_scored", "sum"),
        )
        .reset_index()
    )

    if per_wrestler.empty:
        print(f"No per‑wrestler rows after aggregation for season {season}.")
        return

    # Build full match counts (including pins / non‑scored results) for
    # the same ranked wrestler set.
    full_match_counts = _build_full_match_counts(season, max_rank)

    # full_matches = total matches (including pins) for threshold + display.
    per_wrestler["full_matches"] = (
        per_wrestler["wrestler_id"]
        .map(full_match_counts)
        .fillna(per_wrestler["matches"])
        .astype(float)
    )

    # Average number of matches wrestled by wrestlers ranked 1..max_rank,
    # using full match counts (pins included).
    avg_matches: float = float(per_wrestler["full_matches"].mean())

    print(f"\nSeason {season} — ranks 1–{max_rank}")
    print(f"Average number of matches wrestled: {avg_matches:.2f}")

    # Eligibility threshold: at least (50% of average matches + 1).
    # Example: avg = 5.25 -> 0.5 * 5.25 + 1 = 3.625 -> needs at least 4 matches.
    min_matches_threshold: float = 0.5 * avg_matches + 1.0
    eligible = per_wrestler[per_wrestler["full_matches"] >= min_matches_threshold].copy()

    if eligible.empty:
        print(
            "No wrestlers have wrestled at least 50% of the average number of matches plus one "
            f"(threshold: {min_matches_threshold:.2f})."
        )
        return

    print(
        "Wrestlers meeting threshold "
        f"(>= 50% of average matches + 1, i.e. >= {min_matches_threshold:.2f}): "
        f"{len(eligible)}"
    )

    # Points per match for each eligible wrestler (pins / non‑scored matches
    # are counted in full_matches but excluded from the numerator and
    # denominator here).
    eligible["points_per_match"] = eligible["total_points"] / eligible["matches"]

    # Convenience: ensure numeric sort (DataFrame dtypes should already be numeric).
    # Top 10: highest points per match, break ties by more matches.
    top10 = (
        eligible.sort_values(
            by=["points_per_match", "matches"],
            ascending=[False, False],
        )
        .head(10)
        .reset_index(drop=True)
    )

    # Bottom 10: lowest points per match, break ties by more matches
    # (so a bigger sample size is preferred when ppm is the same).
    bottom10 = (
        eligible.sort_values(
            by=["points_per_match", "matches"],
            ascending=[True, False],
        )
        .head(10)
        .reset_index(drop=True)
    )

    def _print_list(title: str, subset) -> None:
        print(f"\n{title}")
        if subset.empty:
            print("  (no wrestlers)")
            return
        for idx, row in enumerate(subset.itertuples(index=False), start=1):
            # row attributes line up with our aggregated column names.
            name = row.wrestler_name
            ppm = float(row.points_per_match)
            matches = int(row.full_matches)
            print(f"{idx}. {name} - {ppm:.1f} points per match ({matches})")

    _print_list(
        "Top 10 wrestlers by points per match (min 50% of average matches):",
        top10,
    )
    _print_list(
        "Bottom 10 wrestlers by points per match (min 50% of average matches):",
        bottom10,
    )


def main() -> None:
    args = parse_args()
    compute_and_print_stats(args.season, args.maxrank)


if __name__ == "__main__":
    main()


