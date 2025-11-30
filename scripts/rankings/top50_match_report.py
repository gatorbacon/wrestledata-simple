#!/usr/bin/env python3
"""
Report scoring profile for matches between top-50 wrestlers in each weight.

For each weight class, using the CURRENT rankings_{weight}.json:
  - Identify the wrestlers ranked 1–50 at that weight.
  - From weight_class_{weight}.json, find all matches where BOTH wrestlers
    are in that top-50 set at this weight.

Then per weight class:
  - Print total number of such matches.
  - Print total number of Falls.
  - For the remaining matches that went to the "scorecards":
      * Decision (D)
      * Major Decision (MD)
      * Technical Fall (TF)
    compute, over just those matches where a numeric score like "12-3"
    can be parsed from the result string:
      - count
      - average winner points
      - average loser points
      - average total points
      - average point differential
      - median winner points
      - median loser points
      - median total points
      - median point differential
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from generate_matrix import classify_result_type


@dataclass
class MatchStats:
    total_matches: int = 0
    falls: int = 0
    scoring_count: int = 0
    winner_points: List[int] = None
    loser_points: List[int] = None

    def __post_init__(self) -> None:
        if self.winner_points is None:
            self.winner_points = []
        if self.loser_points is None:
            self.loser_points = []

    @property
    def total_points(self) -> List[int]:
        return [w + l for w, l in zip(self.winner_points, self.loser_points)]

    @property
    def diffs(self) -> List[int]:
        return [w - l for w, l in zip(self.winner_points, self.loser_points)]


def load_top50_ids(rankings_path: Path) -> Dict[str, int]:
    """
    Load rankings_{weight}.json and return a map wrestler_id -> rank
    for wrestlers ranked 1..50 at this weight.
    """
    with rankings_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    result: Dict[str, int] = {}
    for entry in data.get("rankings", []):
        wid = entry.get("wrestler_id")
        if not wid:
            continue
        r = entry.get("rank")
        try:
            rank_int = int(r)
        except (TypeError, ValueError):
            continue
        if 1 <= rank_int <= 50:
            result[wid] = rank_int
    return result


def parse_score(result: str) -> Optional[Tuple[int, int]]:
    """
    Extract (winner_points, loser_points) from a result string like:
      'Dec 4-2', 'MD 12-3', 'TF 18-0 2:33'
    If no score can be parsed, return None.
    """
    if not result:
        return None
    # Look for a pattern like "12-3" anywhere in the result string.
    # Use \d+ so we don't accidentally match literals like "\d" – earlier
    # we had an over-escaped pattern which never matched.
    m = re.search(r"(\d+)-(\d+)", result)
    if not m:
        return None
    a = int(m.group(1))
    b = int(m.group(2))
    # Winner always has more points in these scorelines; be robust anyway.
    winner_pts = max(a, b)
    loser_pts = min(a, b)
    return winner_pts, loser_pts


def compute_stats_for_weight(
    weight: str,
    base_dir: Path,
) -> Optional[MatchStats]:
    """
    For a single weight class, compute stats for matches between
    top-50-vs-top-50 wrestlers.
    """
    rankings_path = base_dir / f"rankings_{weight}.json"
    wc_path = base_dir / f"weight_class_{weight}.json"

    if not rankings_path.exists() or not wc_path.exists():
        return None

    top50 = load_top50_ids(rankings_path)
    if not top50:
        return None

    with wc_path.open("r", encoding="utf-8") as f:
        wc_data = json.load(f)
    matches = wc_data.get("matches", [])
    if not matches:
        return MatchStats()

    stats = MatchStats()

    for m in matches:
        w1 = m.get("wrestler1_id")
        w2 = m.get("wrestler2_id")
        if not w1 or not w2:
            continue
        if w1 not in top50 or w2 not in top50:
            continue

        stats.total_matches += 1
        result_str = m.get("result", "")
        code = classify_result_type(result_str)

        if code == "F":
            stats.falls += 1
            continue

        if code not in ("D", "MD", "TF"):
            # Not a scored outcome we care about for averages
            continue

        score = parse_score(result_str)
        if not score:
            continue

        winner_pts, loser_pts = score
        stats.scoring_count += 1
        stats.winner_points.append(winner_pts)
        stats.loser_points.append(loser_pts)

    return stats


def print_stats_for_weight(weight: str, stats: MatchStats) -> None:
    print(f"\nWeight {weight}:")
    print(f"  Top-50 vs Top-50 matches: {stats.total_matches}")
    print(f"  Falls: {stats.falls}")

    n = stats.scoring_count
    if n == 0:
        print("  Scoring matches (D/MD/TF with parsed scores): 0")
        return

    w = stats.winner_points
    l = stats.loser_points
    t = stats.total_points
    d = stats.diffs

    def fmt(x: float) -> str:
        return f"{x:.2f}"

    print(f"  Scoring matches (D/MD/TF with parsed scores): {n}")

    # Averages (arithmetic mean)
    print("    Averages:")
    print(f"      Winner points: {fmt(statistics.mean(w))}")
    print(f"      Loser points : {fmt(statistics.mean(l))}")
    print(f"      Total points : {fmt(statistics.mean(t))}")
    print(f"      Diff (W-L)   : {fmt(statistics.mean(d))}")

    # Medians
    print("    Medians:")
    print(f"      Winner points: {fmt(statistics.median(w))}")
    print(f"      Loser points : {fmt(statistics.median(l))}")
    print(f"      Total points : {fmt(statistics.median(t))}")
    print(f"      Diff (W-L)   : {fmt(statistics.median(d))}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Per-weight breakdown of matches between currently top-50 "
            "wrestlers, including falls and scoring averages."
        )
    )
    parser.add_argument(
        "-season",
        type=int,
        required=True,
        help="Season year (e.g., 2026).",
    )
    parser.add_argument(
        "-data-dir",
        default="mt/rankings_data",
        help="Base data directory containing rankings_*.json and weight_class_*.json.",
    )

    args = parser.parse_args()
    base_dir = Path(args.data_dir) / str(args.season)
    if not base_dir.exists() or not base_dir.is_dir():
        raise SystemExit(f"Data directory not found for season {args.season}: {base_dir}")

    # Discover weights from available rankings files
    weights: List[str] = []
    for f in sorted(base_dir.glob("rankings_*.json")):
        weights.append(f.stem.replace("rankings_", ""))

    if not weights:
        raise SystemExit(f"No rankings_*.json files found in {base_dir}")

    print(
        "Top-50 vs Top-50 match report "
        f"(season {args.season}, using current rankings at generation time)"
    )

    for weight in weights:
        stats = compute_stats_for_weight(weight, base_dir)
        if stats is None:
            continue
        print_stats_for_weight(weight, stats)


if __name__ == "__main__":
    main()


