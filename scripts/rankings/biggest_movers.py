#!/usr/bin/env python3
"""
Report biggest rank gainers and losers per weight class.

Logic:
  - "Current" rankings are the rankings_{weight}.json files in
    mt/rankings_data/{season}.
  - "Baseline" rankings are taken from the archive snapshot that was the
    latest one available as of 11:59:59 PM exactly N days ago (default: 7),
    based on the timestamps in mt/rankings_data/{season}/rankings_archive.
  - For movement math, any rank > 33 and any unranked/missing wrestler
    are all treated as rank 34.

For each weight class, the script prints to stdout:
  - Biggest gainer (if any)
  - Biggest loser (if any)

For each wrestler, we report: name, team, weight, previous rank (baseline),
current rank, and rank differential (positive = moved up, negative = dropped).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple


RANK_CAP = 34  # anything >33 or unranked is treated as 34 for movement math


@dataclass
class WrestlerRank:
    wrestler_id: str
    name: str
    team: str
    norm_rank: int  # 1..33 or 34
    raw_rank: Optional[int]  # original numeric rank if present, else None


def parse_timestamp_dir(name: str) -> Optional[datetime]:
    """Parse rankings_archive directory name like 'YYYYMMDD-HHMMSS'."""
    try:
        return datetime.strptime(name, "%Y%m%d-%H%M%S")
    except ValueError:
        return None


def find_baseline_snapshot(
    base_dir: Path,
    lookback_days: int = 7,
    now: Optional[datetime] = None,
) -> Optional[Path]:
    """
    Find the snapshot directory that represents the "current" rankings
    as of 23:59:59 local time exactly `lookback_days` days ago.
    """
    archive_root = base_dir / "rankings_archive"
    if not archive_root.exists() or not archive_root.is_dir():
        print(f"No rankings_archive directory found at {archive_root}")
        return None

    now = now or datetime.now()
    target_date = (now.date() - timedelta(days=lookback_days))
    target_eod = datetime(
        target_date.year, target_date.month, target_date.day, 23, 59, 59
    )

    candidates: List[Tuple[datetime, Path]] = []
    for entry in archive_root.iterdir():
        if not entry.is_dir():
            continue
        ts = parse_timestamp_dir(entry.name)
        if ts is None:
            continue
        if ts <= target_eod:
            candidates.append((ts, entry))

    if not candidates:
        print(
            f"No archive snapshot found on or before end-of-day {target_date} "
            f"in {archive_root}"
        )
        return None

    # Use the latest snapshot at or before the target end-of-day
    candidates.sort(key=lambda x: x[0])
    _, chosen_dir = candidates[-1]
    print(
        f"Using baseline snapshot {chosen_dir.name} "
        f"for target end-of-day {target_date}"
    )
    return chosen_dir


def normalize_rank(raw: Optional[int]) -> int:
    """
    Normalize a rank value so that:
      - 1..33 stay as-is
      - 34 and higher, or None/unranked, are treated as 34.
    """
    if raw is None:
        return RANK_CAP
    try:
        r = int(raw)
    except (TypeError, ValueError):
        return RANK_CAP
    if 1 <= r <= 33:
        return r
    return RANK_CAP


def load_rankings_file(path: Path) -> List[Dict]:
    """Load rankings JSON file and return its 'rankings' list (may be empty)."""
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("rankings", [])


def load_rank_map_from_dir(
    dir_path: Path,
) -> Dict[str, Dict[str, WrestlerRank]]:
    """
    Load all rankings_{weight}.json files from dir_path and return:

      { weight_class: { wrestler_id: WrestlerRank } }
    """
    result: Dict[str, Dict[str, WrestlerRank]] = {}
    for f in sorted(dir_path.glob("rankings_*.json")):
        weight_class = f.stem.replace("rankings_", "")
        entries = load_rankings_file(f)
        weight_map: Dict[str, WrestlerRank] = {}

        for e in entries:
            wid = e.get("wrestler_id")
            if not wid:
                continue
            name = str(e.get("name", "")).strip() or f"ID:{wid}"
            team = str(e.get("team", "")).strip()
            raw_rank_val = e.get("rank")
            try:
                raw_rank_int: Optional[int] = int(raw_rank_val)
            except (TypeError, ValueError):
                raw_rank_int = None

            norm = normalize_rank(raw_rank_int)
            weight_map[wid] = WrestlerRank(
                wrestler_id=wid,
                name=name,
                team=team,
                norm_rank=norm,
                raw_rank=raw_rank_int,
            )

        if weight_map:
            result[weight_class] = weight_map

    return result


def compute_biggest_movers(
    baseline: Dict[str, Dict[str, WrestlerRank]],
    current: Dict[str, Dict[str, WrestlerRank]],
) -> Dict[str, Dict[str, Tuple[str, int, int, int]]]:
    """
    For each weight class, compute and print biggest gainer and loser.
    """
    all_weights = sorted(set(baseline.keys()) | set(current.keys()))
    if not all_weights:
        print("No rankings found in baseline or current directories.")
        return {}

    summary: Dict[str, Dict[str, Tuple[str, int, int, int]]] = {}
    # weight -> {
    #   "gainer": (wrestler_id, prev_rank, curr_rank, delta),
    #   "loser": (wrestler_id, prev_rank, curr_rank, delta),
    # }

    for weight in all_weights:
        base_map = baseline.get(weight, {})
        curr_map = current.get(weight, {})

        # Only consider wrestlers who were actually in the rankings at this
        # weight in the baseline week. This avoids treating weight-class moves
        # from other weights (or brand-new entries) as huge gainers/losers.
        all_ids = set(base_map.keys())
        if not all_ids:
            continue

        biggest_gain_delta = 0
        biggest_gain_ids: List[str] = []

        biggest_loss_delta = 0
        biggest_loss_ids: List[str] = []

        # Track per-wrestler movement
        deltas: Dict[str, Tuple[int, int, int]] = {}
        # wid -> (baseline_norm, current_norm, delta)

        for wid in all_ids:
            base_info = base_map.get(wid)
            curr_info = curr_map.get(wid)

            base_rank = base_info.norm_rank if base_info else RANK_CAP
            curr_rank = curr_info.norm_rank if curr_info else RANK_CAP

            # Positive delta = moved up; negative = dropped
            delta = base_rank - curr_rank
            deltas[wid] = (base_rank, curr_rank, delta)

            if delta > biggest_gain_delta:
                biggest_gain_delta = delta
                biggest_gain_ids = [wid]
            elif delta == biggest_gain_delta and delta != 0:
                biggest_gain_ids.append(wid)

            if delta < biggest_loss_delta:
                biggest_loss_delta = delta
                biggest_loss_ids = [wid]
            elif delta == biggest_loss_delta and delta != 0:
                biggest_loss_ids.append(wid)

        print(f"\nWeight {weight}:")

        gainer_entry: Optional[Tuple[str, int, int, int]] = None
        if biggest_gain_delta == 0:
            print("  Biggest gainer: (no movement)")
        else:
            # If multiple share the same delta, print them all but store one
            for wid in biggest_gain_ids:
                base_rank, curr_rank, delta = deltas[wid]
                info = curr_map.get(wid) or base_map.get(wid)
                if not info:
                    continue
                print(
                    f"  Biggest gainer: {info.name} ({info.team}) "
                    f"prev={base_rank}, current={curr_rank}, "
                    f"Δrank=+{delta}"
                )
                if gainer_entry is None:
                    gainer_entry = (wid, base_rank, curr_rank, delta)

        loser_entry: Optional[Tuple[str, int, int, int]] = None
        if biggest_loss_delta == 0:
            print("  Biggest loser : (no movement)")
        else:
            for wid in biggest_loss_ids:
                base_rank, curr_rank, delta = deltas[wid]
                info = curr_map.get(wid) or base_map.get(wid)
                if not info:
                    continue
                print(
                    f"  Biggest loser : {info.name} ({info.team}) "
                    f"prev={base_rank}, current={curr_rank}, "
                    f"Δrank={delta}"
                )
                if loser_entry is None:
                    loser_entry = (wid, base_rank, curr_rank, delta)

        if gainer_entry or loser_entry:
            summary[weight] = {}
            if gainer_entry:
                summary[weight]["gainer"] = gainer_entry
            if loser_entry:
                summary[weight]["loser"] = loser_entry

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Report biggest rank gainers and losers per weight class, "
            "using archived rankings snapshots."
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
        help="Directory containing rankings_{weight}.json and rankings_archive.",
    )
    parser.add_argument(
        "-days",
        type=int,
        default=7,
        help="Look-back window in days (default: 7).",
    )

    args = parser.parse_args()

    base_dir = Path(args.data_dir) / str(args.season)
    if not base_dir.exists() or not base_dir.is_dir():
        raise SystemExit(f"Data directory not found for season {args.season}: {base_dir}")

    # Find baseline archive snapshot for target end-of-day
    baseline_dir = find_baseline_snapshot(
        base_dir, lookback_days=args.days, now=datetime.now()
    )
    if baseline_dir is None:
        raise SystemExit("Could not determine baseline snapshot; aborting.")

    print(f"Current rankings directory : {base_dir}")
    print(f"Baseline rankings directory: {baseline_dir}")

    baseline_ranks = load_rank_map_from_dir(baseline_dir)
    current_ranks = load_rank_map_from_dir(base_dir)

    # First, compute and print the basic biggest movers per weight.
    summary = compute_biggest_movers(baseline_ranks, current_ranks)

    # Then, for each weight, list the biggest gainer's wins in the last N days,
    # annotated with opponents' baseline ranks (or 34 if unranked).
    lookback_days = args.days
    now = datetime.now()
    cutoff_date = (now.date() - timedelta(days=lookback_days))
    cutoff_dt = datetime(cutoff_date.year, cutoff_date.month, cutoff_date.day)

    print("\n=== Biggest gainer win details (last "
          f"{lookback_days} day(s), using opponents' baseline ranks) ===")

    for weight, entries in sorted(summary.items()):
        gainer_info = entries.get("gainer")
        if not gainer_info:
            continue

        gainer_id, base_rank, curr_rank, delta = gainer_info
        base_weight_map = baseline_ranks.get(weight, {})
        curr_weight_map = current_ranks.get(weight, {})
        gainer = curr_weight_map.get(gainer_id) or base_weight_map.get(gainer_id)
        if not gainer:
            continue

        # Load matches for this weight from the current data-dir (matches live
        # in weight_class_{weight}.json alongside current rankings).
        wc_path = base_dir / f"weight_class_{weight}.json"
        if not wc_path.exists():
            continue

        try:
            with wc_path.open("r", encoding="utf-8") as f:
                wc_data = json.load(f)
        except Exception:
            continue

        matches = wc_data.get("matches", [])
        if not matches:
            continue

        def parse_match_date(date_str: str) -> Optional[datetime]:
            try:
                return datetime.strptime(date_str, "%m/%d/%Y")
            except Exception:
                return None

        print(f"\nWeight {weight} – biggest gainer: "
              f"{gainer.name} ({gainer.team}) "
              f"prev={base_rank}, current={curr_rank}, Δrank=+{delta}")
        print("  Wins in last week (using opponents' baseline ranks):")

        found_any = False
        for m in matches:
            date_str = m.get("date", "")
            dt = parse_match_date(date_str)
            if not dt or dt < cutoff_dt:
                continue

            winner_id = m.get("winner_id")
            if winner_id != gainer_id:
                continue

            w1 = m.get("wrestler1_id")
            w2 = m.get("wrestler2_id")
            opp_id = w2 if w1 == gainer_id else w1
            if not opp_id:
                continue

            opp_info = base_weight_map.get(opp_id)
            opp_rank_norm = opp_info.norm_rank if opp_info else RANK_CAP
            opp_name = opp_info.name if opp_info else f"ID:{opp_id}"
            opp_team = opp_info.team if opp_info else ""

            result = m.get("result", "")
            event = m.get("event", "")

            found_any = True
            print(
                f"    {date_str}: beat {opp_name} ({opp_team}) "
                f"(baseline rank {opp_rank_norm}) – {result} at {event}"
            )

        if not found_any:
            print("    (no wins in the last week)")


if __name__ == "__main__":
    main()


