#!/usr/bin/env python3
"""
Recompute rank movement for an existing archive drop using a different baseline drop.

Use this when you remove an intermediate release (e.g. 2/1) and need the next release (e.g. 2/3)
to show movement vs the previous public release (e.g. 1/22) instead of the removed one.

Usage:
    python scripts/rankings/recompute_rank_movement.py -season 2026 -gender boys \\
        --drop-id 2026-02-03 --baseline-drop-id 2026-01-22
    python scripts/rankings/recompute_rank_movement.py -season 2026 -gender girls \\
        --drop-id 2026-02-03 --baseline-drop-id 2026-01-21
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List

BOYS_WEIGHTS = [106, 113, 120, 126, 132, 138, 144, 150, 157, 165, 175, 190, 215, 285]
GIRLS_WEIGHTS = [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235]


def load_baseline_ranks(
    archive_base: Path, gender: str, season: int, weight: int, baseline_drop_id: str
) -> Dict[str, int]:
    """Load wrestler_id -> rank from baseline drop for one weight."""
    path = archive_base / gender / str(season) / baseline_drop_id / f"{weight}.json"
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        out = {}
        for w in data.get("wrestlers", []):
            wid = w.get("wrestler_id")
            rank = w.get("rank")
            if wid and rank is not None:
                out[str(wid)] = rank
        return out
    except Exception as e:
        print(f"Warning: Could not load baseline {path}: {e}")
        return {}


def recompute_movement_for_drop(
    archive_base: Path,
    gender: str,
    season: int,
    drop_id: str,
    baseline_drop_id: str,
) -> None:
    weights = BOYS_WEIGHTS if gender == "boys" else GIRLS_WEIGHTS
    drop_dir = archive_base / gender / str(season) / drop_id
    if not drop_dir.exists():
        raise FileNotFoundError(f"Drop directory not found: {drop_dir}")

    for weight in weights:
        weight_file = drop_dir / f"{weight}.json"
        if not weight_file.exists():
            print(f"  Skip {weight}: no file")
            continue

        baseline_ranks = load_baseline_ranks(
            archive_base, gender, season, weight, baseline_drop_id
        )
        if not baseline_ranks:
            print(f"  Skip {weight}: no baseline rankings")
            continue

        with weight_file.open("r", encoding="utf-8") as f:
            data = json.load(f)

        wrestlers: List[dict] = data.get("wrestlers", [])
        for w in wrestlers:
            wid = str(w.get("wrestler_id", ""))
            current_rank = w.get("rank")
            prev_rank = baseline_ranks.get(wid)
            if current_rank is not None and prev_rank is not None:
                w["previous_rank"] = prev_rank
                w["movement"] = prev_rank - current_rank  # positive = moved up
                w["is_new"] = False
            else:
                w["previous_rank"] = prev_rank if prev_rank is not None else None
                w["movement"] = None
                w["is_new"] = current_rank is not None and prev_rank is None

        with weight_file.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"  Updated {weight}: {len(wrestlers)} wrestlers, movement vs {baseline_drop_id}")

    print(f"✓ Recomputed movement for {drop_id} (baseline: {baseline_drop_id})")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recompute rank movement for an existing drop from a different baseline"
    )
    parser.add_argument("-season", type=int, required=True, help="Season year (e.g. 2026)")
    parser.add_argument(
        "-gender",
        choices=["boys", "girls"],
        required=True,
        help="Gender",
    )
    parser.add_argument(
        "--drop-id",
        required=True,
        help="Drop to update (e.g. 2026-02-03)",
    )
    parser.add_argument(
        "--baseline-drop-id",
        required=True,
        help="Baseline drop for movement (e.g. 2026-01-22)",
    )
    parser.add_argument(
        "--archive-base",
        type=Path,
        default=Path("frontend/hs-ky-ui/public/data/rankings"),
        help="Archive root (default: frontend/hs-ky-ui/public/data/rankings)",
    )
    args = parser.parse_args()

    archive_base = args.archive_base
    if not archive_base.is_absolute():
        archive_base = Path.cwd() / archive_base

    print(f"Recomputing movement: {args.drop_id} vs baseline {args.baseline_drop_id}")
    print(f"  Gender: {args.gender}, Season: {args.season}")
    print(f"  Archive: {archive_base}")
    recompute_movement_for_drop(
        archive_base, args.gender, args.season, args.drop_id, args.baseline_drop_id
    )


if __name__ == "__main__":
    main()
