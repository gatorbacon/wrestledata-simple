#!/usr/bin/env python3
"""
generate_dual_predictor_data.py — Dual Predictor Data Generator

Generates optimized JSON files for the Dual Predictor page:
- all_rosters.json: Complete team rosters (starters + remaining) with ranks
- all_weights.json: Combined rankings across all weight classes

This script runs during ranking releases to pre-compute all data needed
by the Dual Predictor, eliminating hundreds of runtime fetches.

Usage:
    python scripts/rankings/generate_dual_predictor_data.py -season 2026 -gender boys
    python scripts/rankings/generate_dual_predictor_data.py -season 2026 -gender girls
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict


def get_weights_for_gender(gender: str) -> List[int]:
    """Return weight classes for the given gender."""
    if gender == 'boys':
        return [106, 113, 120, 126, 132, 138, 144, 150, 157, 165, 175, 190, 215, 285]
    elif gender == 'girls':
        return [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235]
    else:
        raise ValueError(f"Invalid gender: {gender}")


def load_elo_data(season: int, gender: str) -> Dict[str, Dict]:
    """
    Load Elo ratings data including hybrid_rank.
    
    Returns:
        Dict mapping wrestler_id -> Elo data with hybrid_rank_by_weight
    """
    elo_file = Path(f"mt/elo_ratings/{gender}/{season}/elo_ratings.json")
    
    if not elo_file.exists():
        print(f"  Warning: Elo ratings file not found: {elo_file}")
        return {}
    
    try:
        with elo_file.open("r", encoding="utf-8") as f:
            elo_data = json.load(f)
        
        elo_by_id = {}
        for entry in elo_data:
            wrestler_id = entry.get("wrestler_id")
            if wrestler_id:
                elo_by_id[str(wrestler_id)] = entry
        
        print(f"  Loaded Elo data for {len(elo_by_id)} wrestlers")
        return elo_by_id
    except Exception as e:
        print(f"  Warning: Error loading Elo data: {e}")
        return {}


def load_rankings_by_weight(
    season: int,
    gender: str,
    data_dir: str = "mt/rankings_data"
) -> Dict[int, Dict[str, int]]:
    """
    Load FULL rankings from mt/rankings_data (source of truth) and create a map:
    weight -> {wrestler_id -> rank}
    
    Uses rankings_{weight}.json files which contain ALL ranked wrestlers (not just starters).
    
    Args:
        season: Season year
        gender: 'boys' or 'girls'
        data_dir: Base directory for rankings data (default: mt/rankings_data)
        
    Returns:
        Dictionary mapping weight -> {wrestler_id -> rank}
    """
    rankings_by_weight = {}
    weights = get_weights_for_gender(gender)
    
    # Source: mt/rankings_data/hs_ky_{gender}/{season}/rankings_{weight}.json
    rankings_path = Path(data_dir) / f"hs_ky_{gender}" / str(season)
    
    if not rankings_path.exists():
        raise FileNotFoundError(f"Rankings directory not found: {rankings_path}")
    
    for weight in weights:
        weight_file = rankings_path / f"rankings_{weight}.json"
        if not weight_file.exists():
            print(f"  Warning: Rankings file not found for {weight}: {weight_file}")
            rankings_by_weight[weight] = {}
            continue
        
        try:
            with weight_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Full rankings files use "rankings" array
            wrestlers = data.get("rankings", [])
            
            rank_map = {}
            for wrestler in wrestlers:
                wrestler_id = wrestler.get("wrestler_id")
                rank = wrestler.get("rank")
                if wrestler_id and rank is not None:
                    rank_map[str(wrestler_id)] = rank
            
            rankings_by_weight[weight] = rank_map
            print(f"  Loaded {len(rank_map)} ranked wrestlers for {weight} (full rankings)")
            
        except Exception as e:
            print(f"  Error loading rankings for {weight}: {e}")
            rankings_by_weight[weight] = {}
    
    return rankings_by_weight


def load_boys_inactive_mask(season: int, data_dir: str) -> Set[str]:
    """Load boys inactive wrestlers mask file."""
    mask_file = Path(data_dir) / f"hs_ky_boys/{season}/boys_inactive_wrestlers.json"
    
    if not mask_file.exists():
        return set()
    
    try:
        with mask_file.open("r", encoding="utf-8") as f:
            mask_data = json.load(f)
        
        masked_ids = set()
        for wrestler in mask_data.get("masked_wrestlers", []):
            wrestler_id = wrestler.get("boys_wrestler_id")
            if wrestler_id:
                masked_ids.add(str(wrestler_id))
        
        return masked_ids
    except Exception as e:
        print(f"Warning: Could not load boys inactive mask: {e}")
        return set()


def load_team_rosters(
    season: int,
    gender: str,
    teams_dir: Path,
    rankings_by_weight: Dict[int, Dict[str, int]],
    elo_by_id: Dict[str, Dict] = None,
    masked_wrestler_ids: Set[str] = None
) -> Dict[str, Dict]:
    """
    Load all team JSON files and build unified roster structure.
    
    Args:
        season: Season year
        gender: 'boys' or 'girls'
        teams_dir: Base directory for team JSON files
        rankings_by_weight: Map of weight -> {wrestler_id -> rank}
        
    Returns:
        Dictionary mapping team_name -> {
            "team_slug": str,
            "weights": {
                weight: [
                    {
                        "wrestler_id": str,
                        "name": str,
                        "weight": int,
                        "rank": int | null,
                        "is_starter": bool
                    }
                ]
            }
        }
    """
    teams_path = teams_dir / gender / str(season)
    
    if not teams_path.exists():
        raise FileNotFoundError(f"Teams directory not found: {teams_path}")
    
    all_rosters = {}
    team_files = sorted(teams_path.glob("*.json"))
    
    print(f"\nLoading {len(team_files)} team files...")
    
    for team_file in team_files:
        try:
            with team_file.open("r", encoding="utf-8") as f:
                team_data = json.load(f)
            
            team_name = team_data.get("team_name") or team_data.get("name")
            team_slug = team_data.get("team_id") or team_file.stem
            
            if not team_name:
                print(f"  Warning: Skipping {team_file.name} (no team_name)")
                continue
            
            # Initialize team roster structure
            roster = {
                "team_slug": team_slug,
                "weights": {}
            }
            
            # Process starters
            starters = team_data.get("starters", {})
            for weight_str, starter_data in starters.items():
                if not starter_data:
                    continue
                
                try:
                    weight = int(weight_str)
                except ValueError:
                    print(f"  Warning: Invalid weight '{weight_str}' in {team_file.name}")
                    continue
                
                wrestler_id = str(starter_data.get("wrestler_id", ""))
                
                # Skip masked wrestlers (boys only)
                if masked_wrestler_ids and wrestler_id in masked_wrestler_ids:
                    continue
                
                name = starter_data.get("name", "Unknown")
                
                # Get rank from rankings
                rank = rankings_by_weight.get(weight, {}).get(wrestler_id)
                
                # Get hybrid_rank from Elo data (per weight class)
                hybrid_rank = None
                is_active = None  # Only set if Elo data exists
                record = None  # Only set if Elo data exists
                if elo_by_id:
                    elo_entry = elo_by_id.get(wrestler_id)
                    if elo_entry:
                        hybrid_rank_by_weight = elo_entry.get("hybrid_rank_by_weight", {})
                        # Keys in hybrid_rank_by_weight are strings, so convert weight to string
                        hybrid_rank = hybrid_rank_by_weight.get(str(weight))
                        is_active = not elo_entry.get("inactive_flag", False)
                        record = elo_entry.get("record_string")
                
                if weight_str not in roster["weights"]:
                    roster["weights"][weight_str] = []
                
                roster["weights"][weight_str].append({
                    "wrestler_id": wrestler_id,
                    "name": name,
                    "weight": weight,
                    "rank": rank,  # Keep matrix rank for reference
                    "hybrid_rank": hybrid_rank,  # Use this for dual simulations
                    "is_active": is_active,
                    "record": record,
                    "is_starter": True,
                    "is_highest_ranked": True  # Starters are highest-ranked at their weight
                })
            
            # Process remaining roster
            remaining = team_data.get("remaining", [])
            for wrestler_data in remaining:
                weight = wrestler_data.get("weight")
                if not weight:
                    continue
                
                weight_str = str(weight)
                wrestler_id = str(wrestler_data.get("wrestler_id", ""))
                
                # Skip masked wrestlers (boys only)
                if masked_wrestler_ids and wrestler_id in masked_wrestler_ids:
                    continue
                
                name = wrestler_data.get("name", "Unknown")
                
                # Get rank from rankings
                rank = rankings_by_weight.get(weight, {}).get(wrestler_id)
                
                # Get hybrid_rank from Elo data (per weight class)
                hybrid_rank = None
                is_active = None  # Only set if Elo data exists
                record = None  # Only set if Elo data exists
                if elo_by_id:
                    elo_entry = elo_by_id.get(wrestler_id)
                    if elo_entry:
                        hybrid_rank_by_weight = elo_entry.get("hybrid_rank_by_weight", {})
                        # Keys in hybrid_rank_by_weight are strings, so convert weight to string
                        hybrid_rank = hybrid_rank_by_weight.get(str(weight))
                        is_active = not elo_entry.get("inactive_flag", False)
                        record = elo_entry.get("record_string")
                
                if weight_str not in roster["weights"]:
                    roster["weights"][weight_str] = []
                
                roster["weights"][weight_str].append({
                    "wrestler_id": wrestler_id,
                    "name": name,
                    "weight": weight,
                    "rank": rank,  # Keep matrix rank for reference
                    "hybrid_rank": hybrid_rank,  # Use this for dual simulations
                    "is_active": is_active,
                    "record": record,
                    "is_starter": False,
                    "is_highest_ranked": False  # Non-starters are not highest-ranked
                })
            
            # Sort wrestlers within each weight: starters first, then by hybrid_rank (or rank if no hybrid_rank)
            for weight_str in roster["weights"]:
                wrestlers = roster["weights"][weight_str]
                wrestlers.sort(key=lambda w: (
                    not w["is_starter"],  # Starters first
                    w["hybrid_rank"] if w["hybrid_rank"] is not None else (w["rank"] if w["rank"] is not None else 9999)  # Then by hybrid_rank
                ))
            
            all_rosters[team_name] = roster
            
        except Exception as e:
            print(f"  Error processing {team_file.name}: {e}")
            continue
    
    print(f"  Processed {len(all_rosters)} teams")
    
    # Log statistics
    total_wrestlers = sum(
        sum(len(wrestlers) for wrestlers in roster["weights"].values())
        for roster in all_rosters.values()
    )
    print(f"  Total wrestlers: {total_wrestlers}")
    
    return all_rosters


def generate_all_weights_json(
    season: int,
    gender: str,
    data_dir: str = "mt/rankings_data",
    output_path: Path = None
) -> None:
    """
    Generate combined rankings file (all_weights.json) from FULL rankings.
    Includes hybrid_rank from Elo data.
    
    Args:
        season: Season year
        gender: 'boys' or 'girls'
        data_dir: Base directory for rankings data (default: mt/rankings_data)
        output_path: Output file path
    """
    weights = get_weights_for_gender(gender)
    
    # Source: mt/rankings_data/hs_ky_{gender}/{season}/rankings_{weight}.json
    rankings_path = Path(data_dir) / f"hs_ky_{gender}" / str(season)
    
    if not rankings_path.exists():
        raise FileNotFoundError(f"Rankings directory not found: {rankings_path}")
    
    # Load Elo data for hybrid_rank
    print("  Loading Elo data for hybrid_rank...")
    elo_by_id = load_elo_data(season, gender)
    
    all_weights = {}
    
    print(f"\nGenerating all_weights.json from FULL rankings...")
    
    for weight in weights:
        weight_file = rankings_path / f"rankings_{weight}.json"
        if not weight_file.exists():
            print(f"  Warning: Rankings file not found for {weight}: {weight_file}")
            all_weights[str(weight)] = []
            continue
        
        try:
            with weight_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Full rankings files use "rankings" array
            wrestlers = data.get("rankings", [])
            
            # Extract only fields needed by Dual Predictor
            simplified = []
            for wrestler in wrestlers:
                wrestler_id = str(wrestler.get("wrestler_id", ""))
                
                # Determine is_highest_ranked: True if is_starter is True or not present
                # (in full rankings, starters are marked with is_starter: true)
                is_starter = wrestler.get("is_starter", False)
                is_highest_ranked = wrestler.get("is_highest_ranked", is_starter)
                
                # Get hybrid_rank from Elo data (per weight class)
                hybrid_rank = None
                if elo_by_id:
                    elo_entry = elo_by_id.get(wrestler_id)
                    if elo_entry:
                        hybrid_rank_by_weight = elo_entry.get("hybrid_rank_by_weight", {})
                        # Keys in hybrid_rank_by_weight are strings, so convert weight to string
                        hybrid_rank = hybrid_rank_by_weight.get(str(weight))
                
                simplified.append({
                    "wrestler_id": wrestler_id,
                    "rank": wrestler.get("rank"),
                    "hybrid_rank": hybrid_rank,
                    "name": wrestler.get("name", "Unknown"),
                    "team": wrestler.get("team", ""),
                    "is_highest_ranked": is_highest_ranked
                })
            
            all_weights[str(weight)] = simplified
            print(f"  Added {len(simplified)} wrestlers for {weight} (full rankings)")
            
        except Exception as e:
            print(f"  Error loading rankings for {weight}: {e}")
            all_weights[str(weight)] = []
    
    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(all_weights, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Generated: {output_path}")


def generate_all_rosters_json(
    season: int,
    gender: str,
    teams_dir: Path,
    data_dir: str = "mt/rankings_data",
    output_path: Path = None
) -> None:
    """
    Generate combined rosters file (all_rosters.json).
    
    Args:
        season: Season year
        gender: 'boys' or 'girls'
        teams_dir: Base directory for team JSON files
        data_dir: Base directory for rankings data (default: mt/rankings_data)
        output_path: Output file path
    """
    print(f"\nGenerating all_rosters.json...")
    
    # Load boys inactive mask (if boys)
    masked_wrestler_ids = set()
    if gender == 'boys':
        masked_wrestler_ids = load_boys_inactive_mask(season, data_dir)
        if masked_wrestler_ids:
            print(f"Loaded mask for {len(masked_wrestler_ids)} inactive boys wrestlers")
    
    # Load FULL rankings to resolve ranks
    print("Loading FULL rankings from mt/rankings_data...")
    rankings_by_weight = load_rankings_by_weight(season, gender, data_dir)
    
    # Load Elo data for hybrid_rank
    print("Loading Elo data for hybrid_rank...")
    elo_by_id = load_elo_data(season, gender)
    
    # Load team rosters
    all_rosters = load_team_rosters(season, gender, teams_dir, rankings_by_weight, elo_by_id, masked_wrestler_ids)
    
    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(all_rosters, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Generated: {output_path}")
    print(f"  Teams: {len(all_rosters)}")


def get_starter(wrestlers: List[Dict]) -> Optional[Dict]:
    """
    Get the starter (highest-ranked wrestler) from a list.
    Filters out inactive and 0-0 wrestlers, uses hybrid_rank for comparison.
    """
    if not wrestlers:
        return None
    
    # Filter out inactive and 0-0 wrestlers
    # Only filter if explicitly False or "0-0", not if None/undefined
    available_wrestlers = [
        w for w in wrestlers
        if w.get("is_active") is not False and w.get("record") != "0-0"
    ]
    
    # If no available wrestlers, return None (forfeit)
    if not available_wrestlers:
        return None
    
    # Find highest-ranked wrestler using hybrid_rank (or rank as fallback)
    # Sort by hybrid_rank first, then by rank
    sorted_wrestlers = sorted(
        available_wrestlers,
        key=lambda x: (
            x.get("hybrid_rank") if x.get("hybrid_rank") is not None else 9999,
            x.get("rank") if x.get("rank") is not None else 9999
        )
    )
    
    return sorted_wrestlers[0] if sorted_wrestlers else None


def get_highest_ranked_wrestler_from_weight_below(
    roster: Dict,
    weight: int,
    all_weights: List[int],
    weight_index: int,
    exclude_wrestler_ids: set = None
) -> Optional[Dict]:
    """
    Get highest-ranked NON-STARTER from the weight class directly below.
    Filters out starters, inactive and 0-0 wrestlers, uses hybrid_rank for comparison.
    Matches frontend logic: only gets non-starters (is_highest_ranked = false).
    """
    if weight_index <= 0:
        return None  # No weight class below (can't go below the lowest weight)
    
    # Weight "below" means lower weight number, which is lower index in sorted array
    # Example: For 113 (index 1), look at 106 (index 0)
    weight_below = all_weights[weight_index - 1]
    weights_dict = roster.get("weights", {})
    wrestlers_below = weights_dict.get(str(weight_below), [])
    
    if not wrestlers_below:
        return None
    
    # Filter out excluded wrestlers (already assigned elsewhere)
    if exclude_wrestler_ids:
        wrestlers_below = [w for w in wrestlers_below if w.get("wrestler_id") not in exclude_wrestler_ids]
    
    # Filter out starters (they're already starting at that weight below, can't move them up)
    # Filter out inactive and 0-0 wrestlers
    # Only filter if explicitly False or "0-0", not if None/undefined
    available_wrestlers = [
        w for w in wrestlers_below
        if not w.get("is_highest_ranked", False)  # Exclude starters
        and w.get("is_active") is not False  # Exclude inactive (only if explicitly False)
        and w.get("record") != "0-0"  # Exclude 0-0 records (only if explicitly "0-0")
    ]
    
    if not available_wrestlers:
        return None
    
    # Find highest-ranked non-starter using hybrid_rank (or rank as fallback)
    sorted_wrestlers = sorted(
        available_wrestlers,
        key=lambda x: (
            x.get("hybrid_rank") if x.get("hybrid_rank") is not None else 9999,
            x.get("rank") if x.get("rank") is not None else 9999
        )
    )
    
    if sorted_wrestlers:
        result = sorted_wrestlers[0].copy()
        result["source_weight"] = weight_below
        return result
    
    return None


def get_default_wrestler(
    roster: Dict,
    weight: int,
    all_weights: List[int],
    weight_index: int,
    assigned_wrestler_ids: set = None
) -> Optional[Dict]:
    """
    Get default wrestler for a weight class using dual predictor logic.
    Matches frontend logic exactly:
    1. Starter at current weight (if not already assigned elsewhere) - ALWAYS use if exists
    2. Highest-ranked NON-STARTER from weight below (only if no starter exists)
    3. None (forfeit)
    
    Wrestlers can only bump up ONE weight class and can only fill ONE weight class.
    """
    if assigned_wrestler_ids is None:
        assigned_wrestler_ids = set()
    
    weights_dict = roster.get("weights", {})
    wrestlers_at_weight = weights_dict.get(str(weight), [])
    starter = get_starter(wrestlers_at_weight)
    
    # Priority 1: Use starter if exists and not already assigned
    if starter and starter.get("wrestler_id") not in assigned_wrestler_ids:
        return starter
    
    # Priority 2: No starter at this weight (or starter already assigned elsewhere)
    # Get highest-ranked NON-STARTER from weight below (only non-starters, matching frontend)
    wrestler_below = get_highest_ranked_wrestler_from_weight_below(
        roster, weight, all_weights, weight_index, exclude_wrestler_ids=assigned_wrestler_ids
    )
    
    if wrestler_below:
        return wrestler_below
    
    # Priority 3: No wrestler available - forfeit
    return None


def adjust_rank_for_weight_class(rank: Optional[int], actual_weight: int, matchup_weight: int) -> Optional[float]:
    """Adjust rank based on weight class difference."""
    if rank is None:
        return None
    
    actual_weight_num = int(actual_weight)
    matchup_weight_num = int(matchup_weight)
    
    # If wrestler is from weight class below, add 2.5 to rank
    if actual_weight_num < matchup_weight_num:
        return rank + 2.5
    
    # If wrestler is from weight class above or same, use rank as-is
    return float(rank)


def calculate_points_for_rank_difference(rank_diff: float, gender: str) -> int:
    """Calculate match points based on rank difference."""
    rank_diff_int = int(rank_diff)
    
    if gender == 'boys':
        if 1 <= rank_diff_int <= 7:
            return 3  # Regular decision
        elif 8 <= rank_diff_int <= 14:
            return 4  # Major decision
        elif rank_diff_int >= 15:
            return 6  # Fall
    elif gender == 'girls':
        if 1 <= rank_diff_int <= 4:
            return 3  # Regular decision
        elif 5 <= rank_diff_int <= 8:
            return 4  # Major decision
        elif rank_diff_int >= 9:
            return 6  # Fall
    
    # Default to regular decision
    return 3


def simulate_dual_meet(
    team_a: str,
    team_b: str,
    team_rosters: Dict[str, Dict],
    gender: str
) -> Tuple[int, int]:
    """Simulate a dual meet between two teams. Returns (score_a, score_b)."""
    weights = get_weights_for_gender(gender)
    roster_a = team_rosters.get(team_a, {"weights": {}})
    roster_b = team_rosters.get(team_b, {"weights": {}})
    
    score_a = 0
    score_b = 0
    
    # Track assigned wrestlers to prevent double-assignment
    assigned_a = set()
    assigned_b = set()
    
    for weight_index, weight in enumerate(weights):
        # Get default wrestlers (pass assigned sets to prevent double-assignment)
        wrestler_a = get_default_wrestler(roster_a, weight, weights, weight_index, assigned_wrestler_ids=assigned_a)
        wrestler_b = get_default_wrestler(roster_b, weight, weights, weight_index, assigned_wrestler_ids=assigned_b)
        
        # Mark wrestlers as assigned
        if wrestler_a:
            assigned_a.add(wrestler_a.get("wrestler_id"))
        if wrestler_b:
            assigned_b.add(wrestler_b.get("wrestler_id"))
        
        # Handle forfeits
        if not wrestler_a and not wrestler_b:
            # Both forfeit - skip
            continue
        elif not wrestler_a:
            # Team A forfeits
            score_b += 6
            continue
        elif not wrestler_b:
            # Team B forfeits
            score_a += 6
            continue
        
        # Get wrestler info - use hybrid_rank instead of rank
        hybrid_rank_a = wrestler_a.get("hybrid_rank")
        hybrid_rank_b = wrestler_b.get("hybrid_rank")
        # Fallback to rank if hybrid_rank not available
        rank_a = hybrid_rank_a if hybrid_rank_a is not None else wrestler_a.get("rank")
        rank_b = hybrid_rank_b if hybrid_rank_b is not None else wrestler_b.get("rank")
        actual_weight_a = wrestler_a.get("source_weight", weight)
        actual_weight_b = wrestler_b.get("source_weight", weight)
        
        # Adjust ranks
        adjusted_rank_a = adjust_rank_for_weight_class(rank_a, actual_weight_a, weight)
        adjusted_rank_b = adjust_rank_for_weight_class(rank_b, actual_weight_b, weight)
        
        # Determine winner and points
        if adjusted_rank_a is None and adjusted_rank_b is None:
            # Both unranked - default to Team A, regular decision
            points = 3
            score_a += points
        elif adjusted_rank_a is None:
            # Team A unranked
            points = 3
            score_b += points
        elif adjusted_rank_b is None:
            # Team B unranked
            points = 3
            score_a += points
        else:
            # Both ranked - determine winner
            rank_diff = abs(adjusted_rank_a - adjusted_rank_b)
            
            if adjusted_rank_a < adjusted_rank_b:
                # Team A wins
                points = calculate_points_for_rank_difference(rank_diff, gender)
                score_a += points
            elif adjusted_rank_b < adjusted_rank_a:
                # Team B wins
                points = calculate_points_for_rank_difference(rank_diff, gender)
                score_b += points
            else:
                # Tie - default to Team A, regular decision
                points = 3
                score_a += points
    
    return score_a, score_b


def calculate_dual_standings(
    season: int,
    gender: str,
    teams_dir: Path,
    data_dir: str = "mt/rankings_data"
) -> List[Dict]:
    """
    Calculate theoretical dual meet standings by simulating all pairwise matchups.
    
    Returns:
        List of team standings sorted by record, each with:
        {
            "rank": int,
            "team": str,
            "team_slug": str,
            "wins": int,
            "losses": int,
            "ties": int,
            "points_for": int,
            "points_against": int,
            "point_diff": int,
            "win_pct": float
        }
    """
    print(f"\nCalculating dual meet standings...")
    
    # Load boys inactive mask (if boys)
    masked_wrestler_ids = set()
    if gender == 'boys':
        masked_wrestler_ids = load_boys_inactive_mask(season, data_dir)
        if masked_wrestler_ids:
            print(f"  Loaded mask for {len(masked_wrestler_ids)} inactive boys wrestlers")
    
    # Load FULL rankings to resolve ranks
    print("  Loading FULL rankings from mt/rankings_data...")
    rankings_by_weight = load_rankings_by_weight(season, gender, data_dir)
    
    # Load Elo data for hybrid_rank
    print("  Loading Elo data for hybrid_rank...")
    elo_by_id = load_elo_data(season, gender)
    
    # Load team rosters
    all_rosters = load_team_rosters(season, gender, teams_dir, rankings_by_weight, elo_by_id, masked_wrestler_ids)
    
    # Filter out teams with 0 wrestlers
    def count_wrestlers(roster: Dict) -> int:
        """Count total number of wrestlers in a roster."""
        return sum(len(wrestlers) for wrestlers in roster.get("weights", {}).values())
    
    # Filter teams: only keep those with at least 1 wrestler
    valid_rosters = {}
    filtered_count = 0
    for team_name, roster in all_rosters.items():
        wrestler_count = count_wrestlers(roster)
        if wrestler_count > 0:
            valid_rosters[team_name] = roster
        else:
            filtered_count += 1
    
    if filtered_count > 0:
        print(f"  Filtered out {filtered_count} teams with 0 wrestlers")
    
    all_rosters = valid_rosters
    team_names = sorted(all_rosters.keys())
    print(f"  Found {len(team_names)} teams with wrestlers")
    
    # Track records
    records = defaultdict(lambda: {'wins': 0, 'losses': 0, 'ties': 0, 'points_for': 0, 'points_against': 0})
    
    print(f"  Simulating {len(team_names) * (len(team_names) - 1) // 2} dual meets...")
    
    # Simulate all pairwise matchups
    for i, team_a in enumerate(team_names):
        for team_b in team_names[i+1:]:
            score_a, score_b = simulate_dual_meet(
                team_a, team_b, all_rosters, gender
            )
            
            records[team_a]['points_for'] += score_a
            records[team_a]['points_against'] += score_b
            records[team_b]['points_for'] += score_b
            records[team_b]['points_against'] += score_a
            
            if score_a > score_b:
                records[team_a]['wins'] += 1
                records[team_b]['losses'] += 1
            elif score_b > score_a:
                records[team_b]['wins'] += 1
                records[team_a]['losses'] += 1
            else:
                records[team_a]['ties'] += 1
                records[team_b]['ties'] += 1
    
    # Sort by record using scoring formula: wins = 3 points, ties = 1 point
    # Then by point differential as tiebreaker
    def sort_key(team):
        rec = records[team]
        # Calculate points: wins * 3 + ties * 1
        points = rec['wins'] * 3 + rec['ties'] * 1
        point_diff = rec['points_for'] - rec['points_against']
        return (-points, -point_diff)  # Negative for descending order
    
    sorted_teams = sorted(team_names, key=sort_key)
    
    # Build standings list
    standings = []
    for rank, team in enumerate(sorted_teams, 1):
        rec = records[team]
        total_games = rec['wins'] + rec['losses'] + rec['ties']
        win_pct = rec['wins'] / total_games if total_games > 0 else 0
        point_diff = rec['points_for'] - rec['points_against']
        
        team_slug = all_rosters[team].get("team_slug", team.lower().replace(" ", "_"))
        
        standings.append({
            "rank": rank,
            "team": team,
            "team_slug": team_slug,
            "wins": rec['wins'],
            "losses": rec['losses'],
            "ties": rec['ties'],
            "points_for": rec['points_for'],
            "points_against": rec['points_against'],
            "point_diff": point_diff,
            "win_pct": round(win_pct, 3)
        })
    
    print(f"  ✓ Calculated standings for {len(standings)} teams")
    
    return standings


def generate_dual_standings_json(
    season: int,
    gender: str,
    teams_dir: Path,
    data_dir: str = "mt/rankings_data",
    output_path: Path = None
) -> None:
    """
    Generate dual standings JSON file.
    
    Args:
        season: Season year
        gender: 'boys' or 'girls'
        teams_dir: Base directory for team JSON files
        data_dir: Base directory for rankings data (default: mt/rankings_data)
        output_path: Output file path
    """
    print(f"\nGenerating dual_standings.json...")
    
    standings = calculate_dual_standings(season, gender, teams_dir, data_dir)
    
    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(standings, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Generated: {output_path}")
    print(f"  Teams: {len(standings)}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate optimized data files for Dual Predictor"
    )
    parser.add_argument(
        "-season",
        type=int,
        required=True,
        help="Season year (e.g., 2026)"
    )
    parser.add_argument(
        "-gender",
        choices=["boys", "girls"],
        required=True,
        help="Gender"
    )
    parser.add_argument(
        "--teams-dir",
        type=str,
        default="frontend/hs-ky-ui/public/data/teams",
        help="Base directory for team JSON files"
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="mt/rankings_data",
        help="Base directory for rankings data (default: mt/rankings_data)"
    )
    parser.add_argument(
        "--output-rosters",
        type=str,
        help="Output path for all_rosters.json (default: frontend/hs-ky-ui/public/data/rosters/{gender}/{season}/all_rosters.json)"
    )
    parser.add_argument(
        "--output-weights",
        type=str,
        help="Output path for all_weights.json (default: frontend/hs-ky-ui/public/data/public_rankings/{gender}/{season}/all_weights.json)"
    )
    parser.add_argument(
        "--output-standings",
        type=str,
        help="Output path for dual_standings.json (default: frontend/hs-ky-ui/public/data/dual_standings/{gender}/{season}/dual_standings.json)"
    )
    
    args = parser.parse_args()
    
    teams_dir = Path(args.teams_dir)
    data_dir = args.data_dir
    
    # Set default output paths
    if args.output_rosters:
        rosters_output = Path(args.output_rosters)
    else:
        rosters_output = Path("frontend/hs-ky-ui/public/data/rosters") / args.gender / str(args.season) / "all_rosters.json"
    
    if args.output_weights:
        weights_output = Path(args.output_weights)
    else:
        weights_output = Path("frontend/hs-ky-ui/public/data/public_rankings") / args.gender / str(args.season) / "all_weights.json"
    
    if args.output_standings:
        standings_output = Path(args.output_standings)
    else:
        standings_output = Path("frontend/hs-ky-ui/public/data/dual_standings") / args.gender / str(args.season) / "dual_standings.json"
    
    print(f"Generating Dual Predictor data for {args.gender} {args.season}...")
    print(f"Teams directory: {teams_dir}")
    print(f"Rankings data directory: {data_dir}")
    print(f"Using FULL rankings from: {data_dir}/hs_ky_{args.gender}/{args.season}/")
    
    # Generate all files
    generate_all_rosters_json(
        args.season,
        args.gender,
        teams_dir,
        data_dir,
        rosters_output
    )
    
    generate_all_weights_json(
        args.season,
        args.gender,
        data_dir,
        weights_output
    )
    
    generate_dual_standings_json(
        args.season,
        args.gender,
        teams_dir,
        data_dir,
        standings_output
    )
    
    print("\n✓ Dual Predictor data generation complete!")


if __name__ == "__main__":
    main()

