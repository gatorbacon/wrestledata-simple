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
        find_opponent_weight_and_rank,
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
    
    Uses flexible opponent search across all weight classes.
    
    Returns:
        - Tuple of (mv_data_dict, matches_with_impact)
        - mv_data_dict: dict with mv_avg and matches, or None if no valid matches
        - matches_with_impact: list of match dicts with mv_impact field added
    """
    # Load wrestler's matches from ALL weight classes
    wrestler_matches = load_wrestler_matches(season, weight, wrestler_id, data_dir)
    
    if not wrestler_matches:
        return None, []
    
    # Collect opponent IDs and their weight classes using flexible search
    opponent_weight_map = {}  # opponent_id -> weight_class
    opponent_rank_map = {}     # opponent_id -> rank
    
    for match in wrestler_matches:
        try:
            opp_id, opp_weight, opp_rank = get_opponent_info(
                match, wrestler_id, season, weight, data_dir
            )
            if opp_id:
                opponent_weight_map[opp_id] = opp_weight
                opponent_rank_map[opp_id] = opp_rank
        except ValueError as e:
            # Opponent not found - halt with error
            raise ValueError(
                f"Failed to find opponent for wrestler {wrestler_id} (weight {weight}): {e}"
            )
    
    if not opponent_weight_map:
        return None, []
    
    # Load all matches for opponents from their respective weight classes
    opponent_matches = load_all_matches_for_opponents(
        season, opponent_weight_map, data_dir
    )
    
    # Build rank maps for each weight class that appears
    weight_rank_maps = {}
    for opp_id, opp_weight in opponent_weight_map.items():
        if opp_weight not in weight_rank_maps:
            weight_rank_maps[opp_weight] = load_rankings(
                season, opp_weight, data_dir, use_cache=True
            )
    
    # Compute raw opponent averages using correct rank map for each opponent
    opponent_raw_avgs = {}
    for opp_id, opp_weight in opponent_weight_map.items():
        opp_rank_map = weight_rank_maps[opp_weight]
        opp_match_list = opponent_matches.get(opp_id, [])
        if not opp_match_list:
            opponent_raw_avgs[opp_id] = 0.0
            continue
        
        total_signed = 0.0
        count = 0
        for match in opp_match_list:
            w1_id = match.get("wrestler1_id")
            w2_id = match.get("wrestler2_id")
            winner_id = match.get("winner_id")
            result = match.get("result", "")
            
            if "MFF" in result.upper() or "FORFEIT" in result.upper():
                continue
            
            if w1_id == opp_id:
                is_winner = (winner_id == opp_id)
            elif w2_id == opp_id:
                is_winner = (winner_id == opp_id)
            else:
                continue
            
            result_type = classify_result_type(result)
            signed = result_to_signed(result_type, is_winner)
            if signed is not None:
                total_signed += signed
                count += 1
        
        if count > 0:
            opponent_raw_avgs[opp_id] = total_signed / count
        else:
            opponent_raw_avgs[opp_id] = 0.0
    
    # Compute tier averages for each weight class that appears (cached)
    tier_avgs_by_weight = {}
    for opp_weight in set(opponent_weight_map.values()):
        opp_rank_map = weight_rank_maps[opp_weight]
        tier_avgs_by_weight[opp_weight] = compute_tier_averages(
            season, opp_weight, opp_rank_map, data_dir, debug=False, use_cache=True
        )
    
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
        
        # Get opponent info (with weight class)
        try:
            opp_id, opp_weight, opp_rank = get_opponent_info(
                match, wrestler_id, season, weight, data_dir
            )
        except ValueError as e:
            raise ValueError(
                f"Failed to find opponent for wrestler {wrestler_id} (weight {weight}): {e}"
            )
        
        if not opp_id:
            continue
        
        # Get opponent raw average
        opp_raw_avg = opponent_raw_avgs.get(opp_id, 0.0)
        
        # Get opponent match count
        opp_match_list = opponent_matches.get(opp_id, [])
        opp_n = len([m for m in opp_match_list if "MFF" not in m.get("result", "").upper()])
        
        # Get tier averages for opponent's weight class
        opp_tier_avgs = tier_avgs_by_weight[opp_weight]
        opp_max_rank = weight_rank_maps[opp_weight].get("__max_rank__", 200)
        
        # Interpolate μ(r) using opponent's weight class tier averages
        mu_r, _ = interpolate_mu(opp_rank, opp_tier_avgs, opp_max_rank, debug=False)
        
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
        
        # Load rankings for this weight (for getting wrestler list)
        try:
            rank_map = load_rankings(season, weight, data_dir, use_cache=True)
            max_rank = rank_map.get("__max_rank__", 200)
        except FileNotFoundError:
            print(f"  Skipping weight {weight} (rankings file not found)")
            continue
        
        # Get all wrestler IDs from rankings
        wrestler_ids = [wid for wid in rank_map.keys() if wid != "__max_rank__"]
        
        print(f"  Processing {len(wrestler_ids)} wrestlers...")
        
        processed = 0
        errors = 0
        for wrestler_id in wrestler_ids:
            try:
                mv_data, matches_with_impact = compute_mv_for_wrestler(
                    wrestler_id,
                    season,
                    weight,
                    data_dir,
                    rank_map,
                    {},  # tier_avgs no longer used (computed per opponent weight)
                    max_rank,
                    [],  # all_matches no longer used (loaded per opponent weight)
                )
                
                if mv_data:
                    all_mv_data[wrestler_id] = mv_data
                    if matches_with_impact:
                        match_impact_cache[wrestler_id] = matches_with_impact
                    processed += 1
            except ValueError as e:
                print(f"  ERROR for wrestler {wrestler_id}: {e}")
                errors += 1
                continue
        
        print(f"  Computed MV for {processed} wrestlers at weight {weight}")
        if errors > 0:
            print(f"  Errors encountered: {errors}")
    
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
        # Default output location - write directly to public data directory
        output_file = Path(f"frontend/wrestledata-ui/public/data/mat_value/{args.season}/mat_value_{args.season}.json")
    
    mv_data, match_impact_cache = compute_all_mv(args.season, args.data_dir, output_file)
    
    # Write MV cache file that can be loaded by build_wrestler_profiles.py
    cache_file = Path(f"frontend/wrestledata-ui/public/data/mat_value/{args.season}/mv_cache_{args.season}.json")
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with cache_file.open("w", encoding="utf-8") as f:
        json.dump(mv_data, f, indent=2)
    
    print(f"\nWrote MV cache: {cache_file}")
    print(f"  {len(mv_data)} wrestlers")
    
    # Write match-level MV impact cache
    match_impact_file = Path(f"frontend/wrestledata-ui/public/data/mat_value/{args.season}/match_mv_impact_{args.season}.json")
    match_impact_file.parent.mkdir(parents=True, exist_ok=True)
    with match_impact_file.open("w", encoding="utf-8") as f:
        json.dump(match_impact_cache, f, indent=2)
    
    print(f"\nWrote match MV impact cache: {match_impact_file}")
    print(f"  {len(match_impact_cache)} wrestlers with match-level data")


if __name__ == "__main__":
    main()

