#!/usr/bin/env python3
"""
Auto-seed rankings for a single weight class using simple relationship data.

Goal:
    Produce a quick, reasonable initial ordering that roughly pushes
    "green" cells (wins/CO-wins) above the diagonal and "red" cells
    (losses/CO-losses) below the diagonal.

Heuristic (kept intentionally simple and fast):
    1. Load the saved relationships for the requested weight class.
    2. Build a base score for each wrestler:
         - +1 for each direct head-to-head win, -1 for each direct loss
         - +0.5 for each common-opponent win, -0.5 for each CO loss
         - tiny bonus for total wins to break ties
    3. Sort wrestlers by this base score.
    4. Make 2–3 "bubble" passes over the list:
         - For each adjacent pair (A above B), if B clearly has
           a direct or CO advantage over A, swap them.
    5. Save the result to rankings_{weight_class}.json in the same
       format that the HTML matrix expects.

This is not a perfect ranking algorithm; it is designed to be:
    - Deterministic
    - Very fast for a single weight class
    - Easy to reason about and adjust later
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple


def load_relationships(
    season: int,
    weight_class: str,
    data_dir: str = "mt/rankings_data",
) -> Dict:
    """Load relationships_{weight_class}.json for a given season."""
    rel_file = Path(data_dir) / str(season) / f"relationships_{weight_class}.json"
    if not rel_file.exists():
        raise FileNotFoundError(f"Relationship file not found: {rel_file}")

    with open(rel_file, "r", encoding="utf-8") as f:
        return json.load(f)


def compute_base_scores(rel_data: Dict) -> Dict[str, float]:
    """
    Compute a simple base score per wrestler from direct and CO relationships.

    - Direct win = +1, direct loss = -1
    - CO win = +0.5, CO loss = -0.5
    """
    wrestlers: Dict[str, Dict] = rel_data["wrestlers"]
    direct_rels: Dict[str, Dict] = rel_data.get("direct_relationships", {})
    co_rels: Dict[str, Dict] = rel_data.get("common_opponent_relationships", {})

    scores: Dict[str, float] = {wid: 0.0 for wid in wrestlers.keys()}

    # Direct head-to-head results
    for rel in direct_rels.values():
        w1 = rel["wrestler1_id"]
        w2 = rel["wrestler2_id"]
        w1_wins = float(rel.get("direct_wins_1", 0))
        w1_losses = float(rel.get("direct_losses_1", 0))
        w2_wins = float(rel.get("direct_wins_2", 0))
        w2_losses = float(rel.get("direct_losses_2", 0))

        scores[w1] += w1_wins - w1_losses
        scores[w2] += w2_wins - w2_losses

    # Common-opponent relationships (smaller weight)
    for rel in co_rels.values():
        w1 = rel["wrestler1_id"]
        w2 = rel["wrestler2_id"]
        w1_score = float(rel.get("common_opp_wins_1", 0)) - float(
            rel.get("common_opp_losses_1", 0)
        )
        w2_score = float(rel.get("common_opp_wins_2", 0)) - float(
            rel.get("common_opp_losses_2", 0)
        )
        scores[w1] += 0.5 * w1_score
        scores[w2] += 0.5 * w2_score

    # Tiny bonus for total wins to gently break ties
    for wid, info in wrestlers.items():
        scores[wid] += 0.01 * float(info.get("wins", 0))

    return scores


def _direct_advantage(
    a_id: str,
    b_id: str,
    direct_rels: Dict[str, Dict],
) -> int:
    """
    Return +1 if a_id has a clear direct advantage over b_id,
    -1 if b_id has the advantage, 0 otherwise.
    """
    if a_id == b_id:
        return 0

    key = f"{min(a_id, b_id)}_{max(a_id, b_id)}"
    rel = direct_rels.get(key)
    if not rel:
        return 0

    if a_id == rel["wrestler1_id"]:
        wins_a = rel.get("direct_wins_1", 0)
        wins_b = rel.get("direct_wins_2", 0)
    else:
        wins_a = rel.get("direct_wins_2", 0)
        wins_b = rel.get("direct_wins_1", 0)

    if wins_a > wins_b:
        return 1
    if wins_b > wins_a:
        return -1
    return 0


def _co_advantage(
    a_id: str,
    b_id: str,
    co_rels: Dict[str, Dict],
) -> int:
    """
    Return +1 if a_id has a CO advantage over b_id,
    -1 if b_id has the advantage, 0 otherwise.
    """
    if a_id == b_id:
        return 0

    key = f"{min(a_id, b_id)}_{max(a_id, b_id)}"
    rel = co_rels.get(key)
    if not rel:
        return 0

    if a_id == rel["wrestler1_id"]:
        wins_a = rel.get("common_opp_wins_1", 0)
        wins_b = rel.get("common_opp_wins_2", 0)
    else:
        wins_a = rel.get("common_opp_wins_2", 0)
        wins_b = rel.get("common_opp_wins_1", 0)

    if wins_a > wins_b:
        return 1
    if wins_b > wins_a:
        return -1
    return 0


def should_swap(
    upper_id: str,
    lower_id: str,
    direct_rels: Dict[str, Dict],
    co_rels: Dict[str, Dict],
    base_scores: Dict[str, float],
) -> bool:
    """
    Decide whether the lower wrestler should move above the upper one.

    We say "yes" if:
        - lower has a direct head-to-head advantage over upper, or
        - no direct edge, but lower has a CO advantage, or
        - neither, but lower's base score is significantly higher.
    """
    # Direct advantage for lower over upper?
    da = _direct_advantage(lower_id, upper_id, direct_rels)
    if da > 0:
        return True
    if da < 0:
        return False

    # Common-opponent advantage?
    ca = _co_advantage(lower_id, upper_id, co_rels)
    if ca > 0:
        return True
    if ca < 0:
        return False

    # Fallback: compare base scores with a small margin
    if base_scores.get(lower_id, 0.0) > base_scores.get(upper_id, 0.0) + 0.5:
        return True

    return False


def compute_order(
    rel_data: Dict,
    passes: int = 3,
) -> List[str]:
    """Compute a simple ordering of wrestler IDs for one weight class."""
    wrestlers: Dict[str, Dict] = rel_data["wrestlers"]
    direct_rels: Dict[str, Dict] = rel_data.get("direct_relationships", {})
    co_rels: Dict[str, Dict] = rel_data.get("common_opponent_relationships", {})

    base_scores = compute_base_scores(rel_data)

    # Initial sort by base score (descending), then by total wins.
    order: List[str] = sorted(
        wrestlers.keys(),
        key=lambda wid: (-base_scores[wid], -wrestlers[wid].get("wins", 0)),
    )

    n = len(order)
    if n <= 1:
        return order

    # A few bubble-style passes to respect clear pairwise advantages.
    for _ in range(max(1, passes)):
        i = 0
        while i < n - 1:
            upper = order[i]
            lower = order[i + 1]
            if should_swap(upper, lower, direct_rels, co_rels, base_scores):
                # Swap and step back one position to let the new item
                # keep bubbling if needed.
                order[i], order[i + 1] = order[i + 1], order[i]
                if i > 0:
                    i -= 1
                else:
                    i += 1
            else:
                i += 1

    return order


def build_rankings_json(
    season: int,
    weight_class: str,
    rel_data: Dict,
    order: List[str],
) -> Dict:
    """Build rankings JSON in the format expected by the HTML matrix."""
    wrestlers: Dict[str, Dict] = rel_data["wrestlers"]

    rankings = []
    for rank, wid in enumerate(order, start=1):
        info = wrestlers[wid]
        rankings.append(
            {
                "rank": rank,
                "wrestler_id": wid,
                "name": info.get("name", ""),
                "team": info.get("team", ""),
                "record": f"{info.get('wins', 0)}-{info.get('losses', 0)}",
            }
        )

    return {
        "season": season,
        "weight_class": weight_class,
        "generated_by": "auto_seed_rankings.py",
        "rankings": rankings,
    }


def save_rankings_json(
    data: Dict,
    season: int,
    output_dir: str = "mt/rankings_data",
) -> Path:
    """Save rankings JSON next to the relationship files."""
    weight_class = data["weight_class"]
    output_path = Path(output_dir) / str(season)
    output_path.mkdir(parents=True, exist_ok=True)

    rankings_file = output_path / f"rankings_{weight_class}.json"
    with open(rankings_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return rankings_file


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Auto-seed rankings for a single weight class using "
            "simple direct/common-opponent relationships."
        )
    )
    parser.add_argument(
        "-season",
        type=int,
        required=True,
        help="Season year (e.g., 2026)",
    )
    parser.add_argument(
        "-weight-class",
        required=True,
        help="Weight class string (e.g., '125')",
    )
    parser.add_argument(
        "-data-dir",
        default="mt/rankings_data",
        help="Directory containing relationship data",
    )
    parser.add_argument(
        "-passes",
        type=int,
        default=3,
        help="Number of bubble passes to refine ordering (default: 3)",
    )
    args = parser.parse_args()

    rel_data = load_relationships(args.season, args.weight_class, args.data_dir)
    order = compute_order(rel_data, passes=args.passes)

    rankings_json = build_rankings_json(
        args.season,
        args.weight_class,
        rel_data,
        order,
    )
    rankings_file = save_rankings_json(rankings_json, args.season, args.data_dir)

    print(f"Saved auto-seeded rankings to: {rankings_file}")
    print(f"  Season: {args.season}")
    print(f"  Weight class: {args.weight_class}")
    print(f"  Wrestlers ranked: {len(order)}")
    print("  Top 10 (rank, name, team, record):")
    for entry in rankings_json["rankings"][:10]:
        print(
            f"    {entry['rank']:>2}: {entry['name']} "
            f"({entry['team']}) {entry['record']}"
        )


if __name__ == "__main__":
    main()


