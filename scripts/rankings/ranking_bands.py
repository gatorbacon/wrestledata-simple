#!/usr/bin/env python3
"""
ranking_bands.py

Compute hard/soft ranking bands and a recommended rank for each ranked
wrestler in a season, using existing rankings_* and relationships_* files.

Inputs per weight class (mt/rankings_data/<season>/):
  - rankings_<weight>.json
      {
        "weight_class": "125",
        "season": 2026,
        "rankings": [
          {
            "rank": 1,
            "wrestler_id": "34941779132",
            "name": "Brendan McCrone",
            "team": "Ohio State",
            "record": "7-0",
            "is_starter": false
          },
          ...
        ]
      }

  - relationships_<weight>.json
      {
        "wrestlers": { ... },
        "direct_relationships": {
          "id1_id2": {
            "wrestler1_id": "id1",
            "wrestler2_id": "id2",
            "direct_wins_1": ...,
            "direct_losses_1": ...,
            "direct_wins_2": ...,
            "direct_losses_2": ...,
            "matches": [...]
          },
          ...
        },
        "common_opponent_relationships": {
          "id1_id2": {
            "wrestler1_id": "id1",
            "wrestler2_id": "id2",
            "common_opp_wins_1": ...,
            "common_opp_losses_1": ...,
            "common_opp_wins_2": ...,
            "common_opp_losses_2": ...,
            "common_opponents": [...],
            "co_details_1": [...],
            "co_details_2": [...]
          },
          ...
        }
      }

Outputs per weight class:
  - ranking_bands_<weight>.json
      {
        "weight_class": "125",
        "season": 2026,
        "bands": [
          {
            "wrestler_id": "...",
            "name": "...",
            "team": "...",
            "current_rank": 12,
            "has_matches": true,

            "hard_min": 9,
            "hard_max": 25,

            "soft_min": 10,
            "soft_max": 20,

            "recommended_rank": 13,

            "debug": {
              "direct_wins_over": [
                {"wrestler_id": "...", "rank": 18, "net_record": "2-0"}
              ],
              "direct_losses_to": [
                {"wrestler_id": "...", "rank": 7, "net_record": "0-1"}
              ],
              "co_advantages": [
                {"wrestler_id": "...", "rank": 15, "net_margin": 1}
              ],
              "co_disadvantages": []
            }
          },
          ...
        ]
      }

NOTE: This is v1 logic, meant to be readable and tunable. The exact
guardrail rules (off-by-one, thresholds, etc.) can be tightened later.
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple, Any, Set


def load_rankings_for_season(season: int, data_dir: str) -> Dict[str, Dict[str, Any]]:
    """
    Load rankings_<weight>.json for all weight classes for a season.

    Returns:
        { weight_class: rankings_json_dict }
    """
    base = Path(data_dir) / str(season)
    if not base.exists():
        raise FileNotFoundError(f"Rankings directory not found: {base}")

    result: Dict[str, Dict[str, Any]] = {}
    for path in sorted(base.glob("rankings_*.json")):
        weight = path.stem.replace("rankings_", "")
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        result[weight] = data

    if not result:
        raise ValueError(f"No rankings_*.json files found under {base}")

    return result


def load_relationships_for_season(season: int, data_dir: str) -> Dict[str, Dict[str, Any]]:
    """
    Load relationships_<weight>.json for all weight classes for a season.

    Returns:
        { weight_class: relationships_json_dict }
    """
    base = Path(data_dir) / str(season)
    if not base.exists():
        raise FileNotFoundError(f"Relationships directory not found: {base}")

    result: Dict[str, Dict[str, Any]] = {}
    for path in sorted(base.glob("relationships_*.json")):
        weight = path.stem.replace("relationships_", "")
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        result[weight] = data

    if not result:
        raise ValueError(f"No relationships_*.json files found under {base}")

    return result


def build_rank_lookup(rankings_data: Dict[str, Any]) -> Dict[str, int]:
    """
    Build wrestler_id -> current_rank mapping from rankings JSON.
    """
    lookup: Dict[str, int] = {}
    for entry in rankings_data.get("rankings", []):
        wid = entry["wrestler_id"]
        r = entry["rank"]
        lookup[wid] = r
    return lookup


def index_direct_relationships(
    direct_rels: Dict[str, Dict[str, Any]]
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Build wrestler-centric index of direct relationships.

    Returns:
        { wrestler_id: [ { 'opponent_id', 'wins', 'losses', 'raw': rel_dict }, ... ] }
    """
    index: Dict[str, List[Dict[str, Any]]] = {}

    for rel in direct_rels.values():
        w1 = rel["wrestler1_id"]
        w2 = rel["wrestler2_id"]

        # Perspective for wrestler1
        wins_1 = rel.get("direct_wins_1", 0)
        losses_1 = rel.get("direct_losses_1", 0)
        wins_2 = rel.get("direct_wins_2", 0)
        losses_2 = rel.get("direct_losses_2", 0)

        index.setdefault(w1, []).append(
            {
                "opponent_id": w2,
                "wins": wins_1,
                "losses": losses_1,
                "raw": rel,
            }
        )
        index.setdefault(w2, []).append(
            {
                "opponent_id": w1,
                "wins": wins_2,
                "losses": losses_2,
                "raw": rel,
            }
        )

    return index


def index_common_opponent_relationships(
    co_rels: Dict[str, Dict[str, Any]]
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Build wrestler-centric index of common-opponent relationships.

    Returns:
        { wrestler_id: [ { 'opponent_id', 'advantage', 'raw': rel_dict }, ... ] }
        where 'advantage' > 0 means this wrestler has CO edge,
              'advantage' < 0 means this wrestler is at CO disadvantage.
    """
    index: Dict[str, List[Dict[str, Any]]] = {}

    for rel in co_rels.values():
        w1 = rel["wrestler1_id"]
        w2 = rel["wrestler2_id"]

        # From w1 perspective
        adv_1 = rel.get("common_opp_wins_1", 0) - rel.get("common_opp_losses_1", 0)
        adv_2 = rel.get("common_opp_wins_2", 0) - rel.get("common_opp_losses_2", 0)

        index.setdefault(w1, []).append(
            {
                "opponent_id": w2,
                "advantage": adv_1,
                "raw": rel,
            }
        )
        index.setdefault(w2, []).append(
            {
                "opponent_id": w1,
                "advantage": adv_2,
                "raw": rel,
            }
        )

    return index


def collect_wrestlers_with_any_matches(
    direct_index: Dict[str, List[Dict[str, Any]]],
    co_index: Dict[str, List[Dict[str, Any]]],
) -> Set[str]:
    """
    Get set of wrestler_ids that appear in any direct or CO relationship.
    """
    ids: Set[str] = set()
    ids.update(direct_index.keys())
    ids.update(co_index.keys())
    return ids


def compute_bands_for_weight(
    weight_class: str,
    rankings_json: Dict[str, Any],
    rel_json: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Compute ranking bands for a single weight class.

    Returns:
        {
          "weight_class": "125",
          "season": 2026,
          "bands": [ ... per-wrestler dicts ... ]
        }
    """
    season = rankings_json.get("season")
    rankings = rankings_json.get("rankings", [])
    if not rankings:
        return {"weight_class": weight_class, "season": season, "bands": []}

    # Map wrestler_id -> current rank
    rank_lookup = build_rank_lookup(rankings_json)
    n_ranked = len(rank_lookup)

    # Index relationships
    direct_index = index_direct_relationships(
        rel_json.get("direct_relationships", {})
    )
    co_index = index_common_opponent_relationships(
        rel_json.get("common_opponent_relationships", {})
    )
    has_matches_ids = collect_wrestlers_with_any_matches(direct_index, co_index)

    bands_output: List[Dict[str, Any]] = []

    for r_entry in rankings:
        wid = r_entry["wrestler_id"]
        name = r_entry.get("name", "")
        team = r_entry.get("team", "")
        current_rank = r_entry.get("rank")

        has_matches = wid in has_matches_ids

        # Default hard band: whole table
        hard_min = 1
        hard_max = n_ranked

        direct_wins_debug: List[Dict[str, Any]] = []
        direct_losses_debug: List[Dict[str, Any]] = []

        # HARD BOUNDS from direct head-to-head
        for rel in direct_index.get(wid, []):
            opp_id = rel["opponent_id"]
            opp_rank = rank_lookup.get(opp_id)
            if opp_rank is None:
                # opponent not currently ranked – ignore for guardrails
                continue

            wins = rel["wins"]
            losses = rel["losses"]

            if wins > losses:
                # Net head-to-head advantage over a ranked opponent.
                # Constrain UPPER bound towards that opponent's rank:
                # You shouldn't be clearly worse than someone you beat.
                hard_max = min(hard_max, opp_rank)
                direct_wins_debug.append(
                    {
                        "wrestler_id": opp_id,
                        "rank": opp_rank,
                        "net_record": f"{wins}-{losses}",
                    }
                )
            elif losses > wins:
                # Net head-to-head disadvantage.
                # Constrain LOWER bound towards that opponent's rank:
                # You shouldn't be clearly better than someone who beat you.
                hard_min = max(hard_min, opp_rank)
                direct_losses_debug.append(
                    {
                        "wrestler_id": opp_id,
                        "rank": opp_rank,
                        "net_record": f"{wins}-{losses}",
                    }
                )
            # If wins == losses or both zero, ignore (neutral / weird case)

        # Ensure band is consistent
        if hard_min > hard_max:
            # If inconsistencies happen, collapse to current rank as a fallback
            hard_min = min(current_rank, n_ranked)
            hard_max = max(current_rank, 1)

        # SOFT BOUNDS start from HARD, then CO nudges
        soft_min = hard_min
        soft_max = hard_max

        co_adv_debug: List[Dict[str, Any]] = []
        co_disadv_debug: List[Dict[str, Any]] = []

        for rel in co_index.get(wid, []):
            opp_id = rel["opponent_id"]
            opp_rank = rank_lookup.get(opp_id)
            if opp_rank is None:
                continue

            advantage = rel["advantage"]
            if advantage > 0:
                # You have net CO advantage vs this ranked opponent.
                # Gently pull upper bound toward this rank.
                soft_max = min(soft_max, opp_rank)
                co_adv_debug.append(
                    {
                        "wrestler_id": opp_id,
                        "rank": opp_rank,
                        "net_margin": advantage,
                    }
                )
            elif advantage < 0:
                # You are at CO disadvantage vs this ranked opponent.
                # Gently push lower bound toward this rank.
                soft_min = max(soft_min, opp_rank)
                co_disadv_debug.append(
                    {
                        "wrestler_id": opp_id,
                        "rank": opp_rank,
                        "net_margin": advantage,
                    }
                )

        if soft_min > soft_max:
            # If CO pulls cross over, clamp back to HARD band
            soft_min = hard_min
            soft_max = hard_max

        # RECOMMENDED RANK
        if not has_matches:
            recommended_rank = None
        else:
            # Start from current_rank but clamp into soft band.
            rec = current_rank
            if rec < soft_min:
                rec = soft_min
            elif rec > soft_max:
                rec = soft_max
            recommended_rank = rec

        bands_output.append(
            {
                "wrestler_id": wid,
                "name": name,
                "team": team,
                "current_rank": current_rank,
                "has_matches": has_matches,
                "hard_min": hard_min,
                "hard_max": hard_max,
                "soft_min": soft_min,
                "soft_max": soft_max,
                "recommended_rank": recommended_rank,
                "debug": {
                    "direct_wins_over": direct_wins_debug,
                    "direct_losses_to": direct_losses_debug,
                    "co_advantages": co_adv_debug,
                    "co_disadvantages": co_disadv_debug,
                },
            }
        )

    return {
        "weight_class": weight_class,
        "season": season,
        "bands": bands_output,
    }


def save_bands_for_weight(
    season: int,
    weight_class: str,
    bands_json: Dict[str, Any],
    data_dir: str,
) -> None:
    """
    Save ranking_bands_<weight>.json under mt/rankings_data/<season>/.
    """
    base = Path(data_dir) / str(season)
    base.mkdir(parents=True, exist_ok=True)
    out_path = base / f"ranking_bands_{weight_class}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(bands_json, f, indent=2)
    print(f"  Saved bands for {weight_class} -> {out_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Compute ranking bands from rankings_* and relationships_* files."
    )
    parser.add_argument(
        "-season",
        type=int,
        required=True,
        help="Season year (e.g., 2026)",
    )
    parser.add_argument(
        "-data-dir",
        default="mt/rankings_data",
        help="Base directory containing season rankings/relationships",
    )
    args = parser.parse_args()

    season = args.season
    data_dir = args.data_dir

    print(f"Building ranking bands for season {season} from {data_dir}...")

    rankings_by_weight = load_rankings_for_season(season, data_dir)
    relationships_by_weight = load_relationships_for_season(season, data_dir)

    weights = sorted(rankings_by_weight.keys())
    print(f"Found rankings for weights: {', '.join(weights)}")

    for weight in weights:
        print(f"\nWeight class {weight}:")
        rankings_json = rankings_by_weight[weight]
        rel_json = relationships_by_weight.get(weight)

        if rel_json is None:
            print(f"  WARNING: No relationships file for {weight}, skipping.")
            continue

        bands_json = compute_bands_for_weight(weight, rankings_json, rel_json)
        save_bands_for_weight(season, weight, bands_json, data_dir)

        # Quick summary
        bands = bands_json.get("bands", [])
        n = len(bands)
        n_nomatches = sum(1 for b in bands if not b.get("has_matches"))
        if n > 0:
            avg_band_size = sum(
                (b["hard_max"] - b["hard_min"] + 1) for b in bands
            ) / n
        else:
            avg_band_size = 0.0
        print(
            f"  {n} wrestlers, {n_nomatches} with no matches; "
            f"avg HARD band size: {avg_band_size:.2f}"
        )

    print("\nDone.")


if __name__ == "__main__":
    main()