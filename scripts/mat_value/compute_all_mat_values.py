#!/usr/bin/env python3
"""
Compute Mat Value (MV) for all wrestlers in a season.

This script processes all wrestlers and outputs:
1. A dictionary mapping wrestler_id -> MV data (for injection into profiles)
2. A season-wide dataset file for leaderboards
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add parent directory to path to import from compute_mat_value
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))

# Import functions from compute_mat_value.py
try:
    from compute_mat_value import (
        classify_result_type,
        result_to_signed,
        load_rankings,
        load_wrestler_matches,
        get_opponent_info,
        load_all_matches_for_opponents,
        compute_opponent_raw_averages,
        compute_tier_averages,
        interpolate_mu,
        shrink_opponent_avg,
        get_wrestler_name,
    )
except ImportError as e:
    print(f"Error importing from compute_mat_value.py: {e}")
    print("Make sure compute_mat_value.py is in the same directory")
    sys.exit(1)


def compute_mv_for_wrestler(
    wrestler_id: str,
    season: int,
    weight: int,
    data_dir: str,
    rank_map: Dict[str, int],
    tier_avgs: Dict[Tuple[int, int], float],
    max_rank: int,
    all_matches: List[Dict],
) -> Tuple[Optional[Dict], List[Dict]]:
    """
    Compute MV for a single wrestler and per-match MV impact.
    
    Returns:
        - Tuple of (mv_data_dict, matches_with_impact)
        - mv_data_dict: dict with mv_avg and matches, or None if no valid matches
        - matches_with_impact: list of match dicts with mv_impact field added
    """
    # Load wrestler's matches
    wrestler_matches = load_wrestler_matches(season, weight, wrestler_id, data_dir)
    
    if not wrestler_matches:
        return None, []
    
    # Collect opponent IDs
    opponent_ids = set()
    for match in wrestler_matches:
        opp_id, _ = get_opponent_info(match, wrestler_id, rank_map)
        if opp_id:
            opponent_ids.add(opp_id)
    
    if not opponent_ids:
        return None, []
    
    # Load all matches for opponents
    opponent_matches = load_all_matches_for_opponents(season, weight, opponent_ids, data_dir)
    
    # Compute raw opponent averages
    opponent_raw_avgs = compute_opponent_raw_averages(opponent_matches, rank_map)
    
    # Process each match
    mv_values = []
    matches_with_impact = []
    
    for match in wrestler_matches:
        winner_id = match.get("winner_id")
        result = match.get("result", "")
        date = match.get("date", "")
        
        # Skip forfeits
        if "MFF" in result.upper() or "FORFEIT" in result.upper():
            continue
        
        # Get opponent info
        opp_id, opp_rank = get_opponent_info(match, wrestler_id, rank_map)
        if not opp_id:
            continue
        
        # Get opponent raw average
        opp_raw_avg = opponent_raw_avgs.get(opp_id, 0.0)
        
        # Get opponent match count
        opp_match_list = opponent_matches.get(opp_id, [])
        opp_n = len([m for m in opp_match_list if "MFF" not in m.get("result", "").upper()])
        
        # Interpolate μ(r)
        mu_r, _ = interpolate_mu(opp_rank, tier_avgs, max_rank, debug=False)
        
        # Shrink
        opp_shrunk = shrink_opponent_avg(opp_raw_avg, mu_r, opp_n)
        
        # Expected value
        expected_signed = -opp_shrunk
        
        # Result signed
        is_winner = (winner_id == wrestler_id)
        result_type = classify_result_type(result)
        result_signed = result_to_signed(result_type, is_winner)
        
        if result_signed is None:
            continue
        
        # MV for this match
        mv_match = result_signed - expected_signed
        mv_values.append(mv_match)
        
        # Create match entry with MV impact for cache
        match_with_impact = {
            "wrestler_id": wrestler_id,
            "opponent_id": opp_id,
            "date": date,
            "result": result,
            "mv_impact": round(mv_match, 2),
        }
        matches_with_impact.append(match_with_impact)
    
    if not mv_values:
        return None, []
    
    mv_avg = sum(mv_values) / len(mv_values)
    
    mv_data = {
        "mv_avg": round(mv_avg, 3),
        "matches": len(mv_values),
    }
    
    return mv_data, matches_with_impact


def compute_all_mv(season: int, data_dir: str, output_file: Optional[Path] = None) -> Tuple[Dict[str, Dict], Dict[str, List[Dict]]]:
    """
    Compute MV for all wrestlers across all weights and per-match MV impact.
    
    Returns:
        - Tuple of (all_mv_data, match_impact_cache)
        - all_mv_data: dict mapping wrestler_id -> MV data
        - match_impact_cache: dict mapping wrestler_id -> list of matches with mv_impact
    """
    data_path = Path(data_dir) / str(season)
    all_mv_data = {}
    match_impact_cache = {}
    
    weights = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]
    
    print(f"Computing Mat Value for all wrestlers in season {season}...")
    print("=" * 80)
    
    for weight in weights:
        print(f"\nProcessing weight {weight}...")
        
        # Load rankings
        try:
            rank_map = load_rankings(season, weight, data_dir)
            max_rank = rank_map.get("__max_rank__", 200)
        except FileNotFoundError:
            print(f"  Skipping weight {weight} (rankings file not found)")
            continue
        
        # Compute tier averages (once per weight)
        print(f"  Computing tier averages for weight {weight}...")
        tier_avgs = compute_tier_averages(season, weight, rank_map, data_dir, debug=False)
        
        # Load all matches for this weight
        all_matches = []
        for pattern in [f"weight_class_{weight}.json", f"weight_class_{weight}A.json"]:
            wc_file = data_path / pattern
            if not wc_file.exists():
                continue
            try:
                with wc_file.open("r", encoding="utf-8") as f:
                    wc_data = json.load(f)
                all_matches.extend(wc_data.get("matches", []))
            except Exception:
                continue
        
        # Get all wrestler IDs from rankings
        wrestler_ids = [wid for wid in rank_map.keys() if wid != "__max_rank__"]
        
        print(f"  Processing {len(wrestler_ids)} wrestlers...")
        
        processed = 0
        for wrestler_id in wrestler_ids:
            mv_data, matches_with_impact = compute_mv_for_wrestler(
                wrestler_id,
                season,
                weight,
                data_dir,
                rank_map,
                tier_avgs,
                max_rank,
                all_matches,
            )
            
            if mv_data:
                all_mv_data[wrestler_id] = mv_data
                if matches_with_impact:
                    match_impact_cache[wrestler_id] = matches_with_impact
                processed += 1
        
        print(f"  Computed MV for {processed} wrestlers at weight {weight}")
    
    print("\n" + "=" * 80)
    print(f"Total: Computed MV for {len(all_mv_data)} wrestlers")
    print(f"Total: Computed per-match MV impact for {len(match_impact_cache)} wrestlers")
    print("=" * 80)
    
    # Write season-wide dataset if output file specified
    if output_file:
        write_season_dataset(season, all_mv_data, data_dir, output_file)
    
    return all_mv_data, match_impact_cache


def compute_mv_rankings(leaderboard_entries: List[Dict]) -> List[Dict]:
    """
    Compute MV rankings (weight-class and overall).
    
    Returns entries with mv_rank_weight and mv_rank_overall added.
    """
    # Sort for overall ranking
    overall_sorted = sorted(
        leaderboard_entries,
        key=lambda x: (-x["mv_avg"], -x["matches"], x.get("current_rank") or 9999)
    )
    
    # Assign overall ranks
    for rank, entry in enumerate(overall_sorted, start=1):
        entry["mv_rank_overall"] = rank
    
    # Compute weight-class ranks
    weights = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]
    
    for weight in weights:
        weight_entries = [e for e in leaderboard_entries if e.get("weight") == weight]
        if not weight_entries:
            continue
        
        # Sort by MV (descending), then matches (descending), then current_rank (ascending)
        weight_sorted = sorted(
            weight_entries,
            key=lambda x: (-x["mv_avg"], -x["matches"], x.get("current_rank") or 9999)
        )
        
        # Assign weight-class ranks
        for rank, entry in enumerate(weight_sorted, start=1):
            entry["mv_rank_weight"] = rank
    
    return leaderboard_entries


def write_season_dataset(season: int, mv_data: Dict[str, Dict], data_dir: str, output_file: Path) -> None:
    """Write season-wide MV dataset for leaderboards."""
    data_path = Path(data_dir) / str(season)
    leaderboard_entries = []
    
    # Load wrestler info from rankings files
    wrestler_info = {}
    weights = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]
    
    for weight in weights:
        rankings_file = data_path / f"rankings_{weight}.json"
        if not rankings_file.exists():
            continue
        
        try:
            with rankings_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            for entry in data.get("rankings", []):
                wrestler_id = entry.get("wrestler_id")
                if wrestler_id and wrestler_id in mv_data:
                    wrestler_info[wrestler_id] = {
                        "name": entry.get("name", "Unknown"),
                        "team": entry.get("team", "Unknown"),
                        "weight": weight,
                        "current_rank": entry.get("rank"),
                    }
        except Exception:
            continue
    
    # Build leaderboard entries
    for wrestler_id, mv in mv_data.items():
        info = wrestler_info.get(wrestler_id, {})
        leaderboard_entries.append({
            "wrestler_id": wrestler_id,
            "name": info.get("name", "Unknown"),
            "team": info.get("team", "Unknown"),
            "weight": info.get("weight"),
            "current_rank": info.get("current_rank"),
            "mv_avg": mv["mv_avg"],
            "matches": mv["matches"],
        })
    
    # Compute rankings
    leaderboard_entries = compute_mv_rankings(leaderboard_entries)
    
    # Write output file
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(leaderboard_entries, f, indent=2)
    
    print(f"\nWrote season-wide dataset: {output_file}")
    print(f"  {len(leaderboard_entries)} entries")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute Mat Value (MV) for all wrestlers in a season"
    )
    parser.add_argument(
        "--season",
        type=int,
        required=True,
        help="Season year (e.g., 2026)",
    )
    parser.add_argument(
        "--data_dir",
        type=str,
        default="mt/rankings_data",
        help="Directory containing rankings and match data",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file for season-wide dataset (optional)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    
    output_file = None
    if args.output:
        output_file = Path(args.output)
    else:
        # Default output location
        output_file = Path(f"data/mat_value/{args.season}/mat_value_{args.season}.json")
    
    mv_data, match_impact_cache = compute_all_mv(args.season, args.data_dir, output_file)
    
    # Write MV cache file that can be loaded by build_wrestler_profiles.py
    cache_file = Path(f"data/mat_value/{args.season}/mv_cache_{args.season}.json")
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with cache_file.open("w", encoding="utf-8") as f:
        json.dump(mv_data, f, indent=2)
    
    print(f"\nWrote MV cache: {cache_file}")
    print(f"  {len(mv_data)} wrestlers")
    
    # Write match-level MV impact cache
    match_impact_file = Path(f"data/mat_value/{args.season}/match_mv_impact_{args.season}.json")
    match_impact_file.parent.mkdir(parents=True, exist_ok=True)
    with match_impact_file.open("w", encoding="utf-8") as f:
        json.dump(match_impact_cache, f, indent=2)
    
    print(f"\nWrote match MV impact cache: {match_impact_file}")
    print(f"  {len(match_impact_cache)} wrestlers with match-level data")


if __name__ == "__main__":
    main()

