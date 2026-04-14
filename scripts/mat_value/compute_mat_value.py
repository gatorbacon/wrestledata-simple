#!/usr/bin/env python3
"""
Compute Mat Value (MV) for a single wrestler.

MV measures how much value a wrestler adds (or costs) his team each time he steps on the mat,
relative to expectation based on opponent quality.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute Mat Value (MV) for a single wrestler"
    )
    parser.add_argument(
        "--season",
        type=int,
        required=True,
        help="Season year (e.g., 2026)",
    )
    parser.add_argument(
        "--weight",
        type=int,
        default=None,
        help="Weight class (e.g., 125). If not provided, will be determined from wrestler data.",
    )
    parser.add_argument(
        "--wrestler_id",
        type=str,
        default=None,
        help="Wrestler ID (optional if using name search)",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Wrestler name (partial match supported)",
    )
    parser.add_argument(
        "--data_dir",
        type=str,
        default="mt/rankings_data",
        help="Directory containing rankings and match data",
    )
    return parser.parse_args()


def classify_result_type(result: str) -> str:
    """Classify match result type: D, MD, TF, F, INJ, DQ, etc."""
    if not result:
        return "O"
    
    s = result.upper()
    
    # Check for injury first
    if "INJ" in s or "INJURY" in s:
        return "INJ"
    
    # Check for disqualification
    if "DQ" in s or "DISQUAL" in s:
        return "DQ"
    
    # Check for tech fall (before fall/pin)
    if "TF" in s or "TECH" in s or "TECHNICAL" in s:
        return "TF"
    
    # Check for falls/pins
    if ("PIN" in s or "FALL" in s) and "TF" not in s:
        return "F"
    
    # Check for major decision
    if "MD" in s or "MAJOR" in s:
        return "MD"
    
    # Check for decision (including sudden victory)
    if "DEC" in s or "DECISION" in s or "SV-" in s:
        return "D"
    
    # Check for tiebreaker
    if "TB-" in s or "TIEBREAK" in s:
        return "D"  # Treat as decision
    
    return "O"


def result_to_signed(result_type: str, is_winner: bool) -> Optional[int]:
    """
    Convert result type to signed value.
    
    WIN:  DEC=+3, MD=+4, TF=+5, PIN=+6, INJ=+6, DQ=+6
    LOSS: DEC=-3, MD=-4, TF=-5, PIN=-6, INJ=-6, DQ=-6
    """
    if result_type == "O":
        return None  # Unknown result type
    
    base_values = {
        "D": 3,
        "MD": 4,
        "TF": 5,
        "F": 6,
        "INJ": 6,
        "DQ": 6,
    }
    
    base = base_values.get(result_type)
    if base is None:
        return None
    
    return base if is_winner else -base


# Cache for rankings and tier averages
_rankings_cache: Dict[Tuple[int, int], Dict[str, int]] = {}
_tier_averages_cache: Dict[Tuple[int, int], Dict[Tuple[int, int], float]] = {}

def load_rankings(season: int, weight: int, data_dir: str, use_cache: bool = True, league: str = 'ncaa', gender: str = None) -> Dict[str, int]:
    """
    Load rankings and return dict mapping wrestler_id -> rank. Uses cache for performance.
    
    IMPORTANT: Always uses rankings_<weight>.json (full rankings with all wrestlers),
    NEVER rankings_starters_<weight>.json. This ensures:
    - Opponent ranks are found in the full list
    - Tier averages are calculated from the full list
    """
    cache_key = (season, weight, league, gender)
    
    if use_cache and cache_key in _rankings_cache:
        return _rankings_cache[cache_key]
    
    # Setup data path based on league type
    if league == 'hs':
        state_lower = 'ky'  # Assuming KY for HS
        data_path = Path(data_dir) / str(season)
    else:  # ncaa
        data_path = Path(data_dir) / str(season)
    
    # ALWAYS use full rankings file (contains all wrestlers)
    rankings_file = data_path / f"rankings_{weight}.json"
    
    if not rankings_file.exists():
        raise FileNotFoundError(
            f"Full rankings file not found for weight {weight}: {rankings_file}\n"
            f"Must use rankings_{weight}.json (full list), not rankings_starters_{weight}.json"
        )
    
    with rankings_file.open("r", encoding="utf-8") as f:
        data = json.load(f)
    
    rank_map = {}
    max_rank = 0
    
    for entry in data.get("rankings", []):
        wrestler_id = entry.get("wrestler_id")
        rank = entry.get("rank")
        if wrestler_id and rank:
            rank_map[wrestler_id] = rank
            max_rank = max(max_rank, rank)
    
    # Store max_rank for missing opponents
    rank_map["__max_rank__"] = max_rank
    
    if use_cache:
        _rankings_cache[cache_key] = rank_map
    
    return rank_map


def find_opponent_weight_and_rank(
    opponent_id: str,
    season: int,
    primary_weight: int,
    data_dir: str,
    league: str = 'ncaa',
    gender: str = None,
) -> Tuple[int, int]:
    """
    Find opponent's weight class and rank using flexible search.
    
    Search order:
    1. Primary weight (wrestler's weight class)
    2. Adjacent weights (primary_weight ± 1)
    3. All other weights
    
    IMPORTANT: Always uses rankings_<weight>.json (full rankings), never starters file.
    
    Returns: (opponent_weight, opponent_rank)
    Raises: ValueError if opponent not found in any weight class
    """
    # Determine weight classes based on league and gender
    if league == 'hs':
        if gender == 'boys':
            weights = [106, 113, 120, 126, 132, 138, 144, 150, 157, 165, 175, 190, 215, 285]
        else:  # girls
            weights = [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235]
    else:  # ncaa
        weights = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]
    data_path = Path(data_dir) / str(season)
    
    # Build search order: primary, adjacent, then rest
    search_order = [primary_weight]
    
    # Add adjacent weights if they exist
    if primary_weight - 1 in weights:
        search_order.append(primary_weight - 1)
    if primary_weight + 1 in weights:
        search_order.append(primary_weight + 1)
    
    # Add remaining weights
    for w in weights:
        if w not in search_order:
            search_order.append(w)
    
    # Search in order - ALWAYS use full rankings file
    for weight in search_order:
        rankings_file = data_path / f"rankings_{weight}.json"
        if not rankings_file.exists():
            continue
        
        try:
            with rankings_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Check if opponent is in this file
            for entry in data.get("rankings", []):
                if entry.get("wrestler_id") == opponent_id:
                    rank = entry.get("rank")
                    if rank is not None:
                        return weight, rank
        except Exception:
            continue
    
    # Opponent not found in any weight class
    raise ValueError(
        f"Opponent {opponent_id} not found in any weight class rankings for season {season}. "
        f"Searched weights: {search_order} (using full rankings files only)"
    )


def load_wrestler_matches(season: int, weight: int, wrestler_id: str, data_dir: str, league: str = 'ncaa', gender: str = None) -> List[Dict]:
    """
    Load all matches for a wrestler from ALL weight class files.
    
    This includes matches at any weight class, not just the wrestler's primary weight.
    """
    data_path = Path(data_dir) / str(season)
    matches = []
    # Determine weight classes based on league and gender
    if league == 'hs':
        if gender == 'boys':
            weights = [106, 113, 120, 126, 132, 138, 144, 150, 157, 165, 175, 190, 215, 285]
        else:  # girls
            weights = [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235]
    else:  # ncaa
        weights = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]
    
    # Search all weight classes
    for w in weights:
        # Check both weight_class_<weight>.json and weight_class_<weight>A.json
        for pattern in [f"weight_class_{w}.json", f"weight_class_{w}A.json"]:
            wc_file = data_path / pattern
            if not wc_file.exists():
                continue
            
            try:
                with wc_file.open("r", encoding="utf-8") as f:
                    wc_data = json.load(f)
            except Exception as e:
                continue  # Silently skip files that can't be loaded
            
            for match in wc_data.get("matches", []):
                w1_id = match.get("wrestler1_id")
                w2_id = match.get("wrestler2_id")
                
                # Include match if wrestler is either participant
                if w1_id == wrestler_id or w2_id == wrestler_id:
                    matches.append(match)
    
    return matches


def get_opponent_info(
    match: Dict,
    wrestler_id: str,
    season: int,
    primary_weight: int,
    data_dir: str,
    league: str = 'ncaa',
    gender: str = None,
) -> Tuple[Optional[str], int, int]:
    """
    Get opponent ID, weight class, and rank from a match using flexible search.
    
    Returns: (opponent_id, opponent_weight, opponent_rank)
    Raises: ValueError if opponent not found in any weight class
    """
    w1_id = match.get("wrestler1_id")
    w2_id = match.get("wrestler2_id")
    
    if w1_id == wrestler_id:
        opp_id = w2_id
    elif w2_id == wrestler_id:
        opp_id = w1_id
    else:
        return None, None, None
    
    if not opp_id:
        return None, None, None
    
    # Find opponent's weight class and rank using flexible search
    opp_weight, opp_rank = find_opponent_weight_and_rank(opp_id, season, primary_weight, data_dir, league=league, gender=gender)
    
    return opp_id, opp_weight, opp_rank


def load_all_matches_for_opponents(
    season: int,
    opponent_weight_map: Dict[str, int],
    data_dir: str,
    league: str = 'ncaa',
    gender: str = None,
) -> Dict[str, List[Dict]]:
    """
    Load all matches for a set of opponents from their respective weight classes.
    
    Args:
        season: Season year
        opponent_weight_map: Dict mapping opponent_id -> weight_class
        data_dir: Data directory path
        league: League type ('ncaa' or 'hs')
        gender: Gender ('boys' or 'girls', required for HS)
    
    Returns:
        Dict mapping opponent_id -> list of matches
    """
    data_path = Path(data_dir) / str(season)
    matches_by_opponent = defaultdict(list)
    
    # Group opponents by weight class for efficient loading
    opponents_by_weight = defaultdict(set)
    for opp_id, weight in opponent_weight_map.items():
        opponents_by_weight[weight].add(opp_id)
    
    # Load matches for each weight class
    for weight, opp_ids in opponents_by_weight.items():
        # Check both weight_class_<weight>.json and weight_class_<weight>A.json
        for pattern in [f"weight_class_{weight}.json", f"weight_class_{weight}A.json"]:
            wc_file = data_path / pattern
            if not wc_file.exists():
                continue
            
            try:
                with wc_file.open("r", encoding="utf-8") as f:
                    wc_data = json.load(f)
            except Exception:
                continue
            
            for match in wc_data.get("matches", []):
                w1_id = match.get("wrestler1_id")
                w2_id = match.get("wrestler2_id")
                result = match.get("result", "")
                
                # Skip forfeits
                if "MFF" in result.upper() or "FORFEIT" in result.upper():
                    continue
                
                # Include if either wrestler is in our opponent set for this weight
                if w1_id in opp_ids:
                    matches_by_opponent[w1_id].append(match)
                if w2_id in opp_ids:
                    matches_by_opponent[w2_id].append(match)
    
    return dict(matches_by_opponent)


def compute_opponent_raw_averages(
    opponent_matches: Dict[str, List[Dict]],
    rank_map: Dict[str, int]
) -> Dict[str, float]:
    """Compute raw observed averages for each opponent."""
    opp_avgs = {}
    
    for opp_id, matches in opponent_matches.items():
        total_signed = 0.0
        count = 0
        
        for match in matches:
            winner_id = match.get("winner_id")
            result = match.get("result", "")
            
            # Skip forfeits
            if "MFF" in result.upper() or "FORFEIT" in result.upper():
                continue
            
            is_winner = (winner_id == opp_id)
            result_type = classify_result_type(result)
            signed = result_to_signed(result_type, is_winner)
            
            if signed is not None:
                total_signed += signed
                count += 1
        
        if count > 0:
            opp_avgs[opp_id] = total_signed / count
        else:
            opp_avgs[opp_id] = 0.0
    
    return opp_avgs


def compute_tier_averages(
    season: int,
    weight: int,
    rank_map: Dict[str, int],
    data_dir: str,
    debug: bool = False,
    use_cache: bool = True
) -> Dict[Tuple[int, int], float]:
    """
    Compute tier averages for rank anchor bands for a specific weight class.
    
    For each tier (e.g., 1-10), includes ALL matches by ALL wrestlers in that rank range.
    Uses cache for performance.
    
    Returns dict mapping (start_rank, end_rank) -> average
    """
    cache_key = (season, weight)
    
    if use_cache and cache_key in _tier_averages_cache:
        return _tier_averages_cache[cache_key]
    
    anchors = [1, 10, 30, 50, 100, 150, 200]
    max_rank = rank_map.get("__max_rank__", 200)
    anchors = [a for a in anchors if a <= max_rank]
    if anchors[-1] < max_rank:
        anchors.append(max_rank)
    
    tier_avgs = {}
    tier_counts = {}
    tier_match_counts = {}
    
    # Load all matches for the weight class
    data_path = Path(data_dir) / str(season)
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
    
    if debug:
        print(f"Loaded {len(all_matches)} total matches for weight {weight}")
    
    # For each tier, compute average across all matches by wrestlers in that tier
    for i in range(len(anchors) - 1):
        start = anchors[i]
        end = anchors[i + 1]
        
        # Find all wrestler IDs in this tier
        tier_wrestler_ids = set()
        for wrestler_id, rank in rank_map.items():
            if wrestler_id == "__max_rank__":
                continue
            if start <= rank <= end:
                tier_wrestler_ids.add(wrestler_id)
        
        if debug:
            print(f"Tier {start}-{end}: {len(tier_wrestler_ids)} wrestlers")
        
        # Collect all matches by wrestlers in this tier
        tier_match_results = []
        for match in all_matches:
            w1_id = match.get("wrestler1_id")
            w2_id = match.get("wrestler2_id")
            winner_id = match.get("winner_id")
            result = match.get("result", "")
            
            # Skip forfeits
            if "MFF" in result.upper() or "FORFEIT" in result.upper():
                continue
            
            # Check if either wrestler is in this tier
            if w1_id in tier_wrestler_ids:
                is_winner = (winner_id == w1_id)
                result_type = classify_result_type(result)
                signed = result_to_signed(result_type, is_winner)
                if signed is not None:
                    tier_match_results.append(signed)
            
            if w2_id in tier_wrestler_ids:
                is_winner = (winner_id == w2_id)
                result_type = classify_result_type(result)
                signed = result_to_signed(result_type, is_winner)
                if signed is not None:
                    tier_match_results.append(signed)
        
        if tier_match_results:
            tier_avgs[(start, end)] = sum(tier_match_results) / len(tier_match_results)
            tier_counts[(start, end)] = len(tier_wrestler_ids)
            tier_match_counts[(start, end)] = len(tier_match_results)
        else:
            tier_avgs[(start, end)] = 0.0
            tier_counts[(start, end)] = 0
            tier_match_counts[(start, end)] = 0
    
    if debug:
        print("\n" + "=" * 80)
        print(f"TIER AVERAGES (μ at anchor nodes) - Weight {weight}")
        print("=" * 80)
        print("Computed from ALL matches by ALL wrestlers in each rank tier")
        print(f"{'Rank Range':<15} {'Wrestlers':<12} {'Matches':<12} {'μ (avg)':<12} {'Description'}")
        print("-" * 80)
        for i in range(len(anchors) - 1):
            start = anchors[i]
            end = anchors[i + 1]
            key = (start, end)
            mu_val = tier_avgs.get(key, 0.0)
            wrestler_count = tier_counts.get(key, 0)
            match_count = tier_match_counts.get(key, 0)
            desc = f"Rank {start}-{end}"
            if start == end:
                desc = f"Rank {start}"
            print(f"{desc:<15} {wrestler_count:<12} {match_count:<12} {mu_val:>11.3f}")
        print("=" * 80)
    
    if use_cache:
        _tier_averages_cache[cache_key] = tier_avgs
    
    return tier_avgs


def interpolate_mu(rank: int, tier_avgs: Dict[Tuple[int, int], float], max_rank: int, debug: bool = False) -> Tuple[float, Optional[Dict]]:
    """
    Interpolate expected value μ(r) for a given rank.
    
    Returns (mu_r, debug_info) where debug_info is None if debug=False
    """
    anchors = [1, 10, 30, 50, 100, 150, 200]
    anchors = [a for a in anchors if a <= max_rank]
    if anchors[-1] < max_rank:
        anchors.append(max_rank)
    
    debug_info = None
    if debug:
        debug_info = {
            "rank": rank,
            "anchors": anchors,
            "band": None,
            "mu_a": None,
            "mu_b": None,
            "interpolated": False
        }
    
    # Find which band this rank falls into
    for i in range(len(anchors) - 1):
        a = anchors[i]
        b = anchors[i + 1]
        
        if a <= rank <= b:
            mu_a = tier_avgs.get((a, b), 0.0)
            # Get next band for interpolation
            if i + 1 < len(anchors) - 1:
                next_b = anchors[i + 2]
                mu_b = tier_avgs.get((b, next_b), 0.0)
            else:
                mu_b = mu_a
            
            if debug:
                debug_info["band"] = (a, b)
                debug_info["mu_a"] = mu_a
                debug_info["mu_b"] = mu_b
                debug_info["interpolated"] = (rank != a and rank != b)
            
            # Linear interpolation
            if b > a:
                mu_r = mu_a + (rank - a) / (b - a) * (mu_b - mu_a)
            else:
                mu_r = mu_a
            
            return mu_r, debug_info
    
    # Fallback
    return 0.0, debug_info


def shrink_opponent_avg(raw_avg: float, mu_r: float, n: int, k: int = 20) -> float:
    """Apply shrinkage to opponent observed average."""
    return (n * raw_avg + k * mu_r) / (n + k)


def load_all_wrestlers_all_weights(season: int, data_dir: str) -> List[Dict]:
    """Load all wrestlers from all weight class full rankings files."""
    data_path = Path(data_dir) / str(season)
    all_wrestlers = []
    
    for weight in [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]:
        rankings_file = data_path / f"rankings_{weight}.json"
        
        if not rankings_file.exists():
            continue
        
        try:
            with rankings_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            for wrestler in data.get("rankings", []):
                wrestler["weight_class"] = weight
                all_wrestlers.append(wrestler)
        except Exception:
            continue
    
    return all_wrestlers


def load_all_wrestlers(season: int, weight: int, data_dir: str) -> List[Dict]:
    """Load all wrestlers from full rankings file for a specific weight."""
    data_path = Path(data_dir) / str(season)
    rankings_file = data_path / f"rankings_{weight}.json"
    
    if rankings_file.exists():
        with rankings_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("rankings", [])
    
    return []


def get_wrestler_name(wrestler_id: str, rank_map: Dict[str, int], data_dir: str, season: int, weight: int) -> str:
    """Get wrestler name from full rankings file."""
    data_path = Path(data_dir) / str(season)
    rankings_file = data_path / f"rankings_{weight}.json"
    
    if rankings_file.exists():
        with rankings_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        for entry in data.get("rankings", []):
            if entry.get("wrestler_id") == wrestler_id:
                return entry.get("name", "Unknown")
    
    return "Unknown"


def search_wrestlers_by_name(name_query: str, season: int, weight: Optional[int], data_dir: str) -> List[Dict]:
    """Search for wrestlers by name (case-insensitive partial match)."""
    if weight is not None:
        all_wrestlers = load_all_wrestlers(season, weight, data_dir)
    else:
        all_wrestlers = load_all_wrestlers_all_weights(season, data_dir)
    
    if not name_query:
        return []
    
    query_lower = name_query.lower()
    matches = []
    
    for wrestler in all_wrestlers:
        name = wrestler.get("name", "")
        if query_lower in name.lower():
            matches.append(wrestler)
    
    return matches


def prompt_for_wrestler_selection(matches: List[Dict]) -> Optional[Dict]:
    """Prompt user to select a wrestler from matches. Returns dict with wrestler_id and weight_class."""
    if not matches:
        print("No matches found.")
        return None
    
    if len(matches) == 1:
        selected = matches[0]
        print(f"\nFound 1 match: {selected.get('name')} ({selected.get('team')})")
        return {
            "wrestler_id": selected.get("wrestler_id"),
            "weight_class": selected.get("weight_class")
        }
    
    print(f"\nFound {len(matches)} matches:")
    for idx, wrestler in enumerate(matches, 1):
        name = wrestler.get("name", "Unknown")
        team = wrestler.get("team", "Unknown")
        rank = wrestler.get("rank", "—")
        record = wrestler.get("record", "—")
        weight = wrestler.get("weight_class", "?")
        print(f"  {idx}. {name} ({team}) - {weight} lbs, Rank #{rank}, Record: {record}")
    
    while True:
        try:
            choice = input(f"\nSelect wrestler (1-{len(matches)}): ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(matches):
                selected = matches[idx]
                print(f"\nSelected: {selected.get('name')} ({selected.get('team')})")
                return {
                    "wrestler_id": selected.get("wrestler_id"),
                    "weight_class": selected.get("weight_class")
                }
            else:
                print(f"Please enter a number between 1 and {len(matches)}")
        except ValueError:
            print("Please enter a valid number")
        except KeyboardInterrupt:
            print("\nCancelled.")
            return None


def get_wrestler_weight(wrestler_id: str, season: int, data_dir: str) -> Optional[int]:
    """Get wrestler's weight class by searching all weight files. Checks both starters and full rankings files."""
    for weight in [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]:
        try:
            rank_map = load_rankings(season, weight, data_dir, use_cache=True)
            if wrestler_id in rank_map:
                return weight
        except FileNotFoundError:
            continue
        except Exception:
            continue
    
    return None


def main() -> None:
    args = parse_args()
    
    # Determine wrestler_id and weight
    wrestler_id = args.wrestler_id
    weight = args.weight
    selected_wrestler_info = None
    
    if not wrestler_id and args.name:
        # Search by name
        print(f"Searching for wrestlers matching '{args.name}'...")
        matches = search_wrestlers_by_name(args.name, args.season, weight, args.data_dir)
        selected_wrestler_info = prompt_for_wrestler_selection(matches)
        if not selected_wrestler_info:
            print("No wrestler selected. Exiting.")
            return
        wrestler_id = selected_wrestler_info.get("wrestler_id")
        if weight is None:
            weight = selected_wrestler_info.get("weight_class")
    elif not wrestler_id:
        # Interactive prompt
        name_query = input("Enter wrestler name (or partial name): ").strip()
        if not name_query:
            print("No name provided. Exiting.")
            return
        
        print(f"Searching for wrestlers matching '{name_query}'...")
        matches = search_wrestlers_by_name(name_query, args.season, weight, args.data_dir)
        selected_wrestler_info = prompt_for_wrestler_selection(matches)
        if not selected_wrestler_info:
            print("No wrestler selected. Exiting.")
            return
        wrestler_id = selected_wrestler_info.get("wrestler_id")
        if weight is None:
            weight = selected_wrestler_info.get("weight_class")
    
    # Determine weight if still not provided (e.g., if wrestler_id was provided directly)
    if weight is None:
        print("\nDetermining weight class...")
        weight = get_wrestler_weight(wrestler_id, args.season, args.data_dir)
        if weight is None:
            print(f"Error: Could not determine weight class for wrestler {wrestler_id}")
            return
        print(f"Found weight class: {weight}")
    
    print(f"\nComputing Mat Value for wrestler {wrestler_id}")
    print(f"Season: {args.season}, Weight: {weight}")
    print("=" * 80)
    
    # Load rankings
    print("\nLoading rankings...")
    rank_map = load_rankings(args.season, weight, args.data_dir, use_cache=True)
    max_rank = rank_map.get("__max_rank__", 200)
    print(f"Loaded {len(rank_map) - 1} ranked wrestlers at weight {weight} (max rank: {max_rank})")
    
    # Get wrestler name
    wrestler_name = get_wrestler_name(wrestler_id, rank_map, args.data_dir, args.season, weight)
    print(f"Wrestler: {wrestler_name}")
    
    # Load wrestler's matches
    print("\nLoading wrestler matches...")
    wrestler_matches = load_wrestler_matches(args.season, weight, wrestler_id, args.data_dir)
    print(f"Found {len(wrestler_matches)} matches")
    
    if not wrestler_matches:
        print("No matches found for this wrestler.")
        return
    
    # Collect opponent IDs and their weight classes using flexible search
    print("\nFinding opponent weight classes and ranks...")
    opponent_weight_map = {}  # opponent_id -> weight_class
    opponent_rank_map = {}     # opponent_id -> rank
    opponent_errors = []
    
    for match in wrestler_matches:
        try:
            opp_id, opp_weight, opp_rank = get_opponent_info(
                match, wrestler_id, args.season, weight, args.data_dir
            )
            if opp_id:
                opponent_weight_map[opp_id] = opp_weight
                opponent_rank_map[opp_id] = opp_rank
        except ValueError as e:
            opponent_errors.append(str(e))
            continue
    
    if opponent_errors:
        print("\nERROR: Failed to find opponents:")
        for error in opponent_errors:
            print(f"  {error}")
        raise ValueError("One or more opponents not found in rankings. Cannot compute MV.")
    
    print(f"Found {len(opponent_weight_map)} unique opponents")
    
    # Load all matches for opponents from their respective weight classes
    print("\nLoading opponent matches...")
    opponent_matches = load_all_matches_for_opponents(
        args.season, opponent_weight_map, args.data_dir
    )
    print(f"Loaded matches for {len(opponent_matches)} opponents")
    
    # Compute raw opponent averages (using opponent's own weight class rankings)
    print("\nComputing opponent raw averages...")
    # Build rank maps for each weight class that appears
    weight_rank_maps = {}
    for opp_id, opp_weight in opponent_weight_map.items():
        if opp_weight not in weight_rank_maps:
            weight_rank_maps[opp_weight] = load_rankings(
                args.season, opp_weight, args.data_dir, use_cache=True
            )
    
    # Compute raw averages using correct rank map for each opponent
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
    print("\nComputing tier averages...")
    tier_avgs_by_weight = {}
    for opp_weight in set(opponent_weight_map.values()):
        opp_rank_map = weight_rank_maps[opp_weight]
        tier_avgs_by_weight[opp_weight] = compute_tier_averages(
            args.season, opp_weight, opp_rank_map, args.data_dir, debug=(opp_weight == weight)
        )
    
    # Show expected values at each anchor point (for primary weight class)
    primary_tier_avgs = tier_avgs_by_weight.get(weight, {})
    primary_max_rank = weight_rank_maps[weight].get("__max_rank__", 200)
    
    print("\n" + "=" * 80)
    print(f"EXPECTED VALUES AT ANCHOR NODES (Weight {weight})")
    print("=" * 80)
    print("These are the μ(r) values at each major rank anchor point.")
    print("Values represent the average observed performance for wrestlers in each tier.")
    print("(Values are interpolated between anchors for intermediate ranks)")
    print("-" * 80)
    anchors = [1, 10, 30, 50, 100, 150, 200]
    anchors = [a for a in anchors if a <= primary_max_rank]
    if anchors[-1] < primary_max_rank:
        anchors.append(primary_max_rank)
    
    print(f"{'Anchor Rank':<15} {'μ(r)':<12} {'Tier Range':<15} {'Description'}")
    print("-" * 80)
    for i in range(len(anchors)):
        anchor = anchors[i]
        # Find which tier this anchor belongs to
        if i == 0:
            # First anchor uses first tier
            tier_key = (anchors[0], anchors[1])
            mu_val = primary_tier_avgs.get(tier_key, 0.0)
            print(f"Rank {anchor:>3}        {mu_val:>11.3f}  {anchors[0]}-{anchors[1]:<10}  Start of curve")
        elif i == len(anchors) - 1:
            # Last anchor uses last tier
            tier_key = (anchors[i-1], anchors[i])
            mu_val = primary_tier_avgs.get(tier_key, 0.0)
            print(f"Rank {anchor:>3}        {mu_val:>11.3f}  {anchors[i-1]}-{anchors[i]:<10}  End of curve")
        else:
            # Middle anchors: show both adjacent tiers and interpolate
            prev_tier = (anchors[i-1], anchors[i])
            next_tier = (anchors[i], anchors[i+1])
            mu_prev = primary_tier_avgs.get(prev_tier, 0.0)
            mu_next = primary_tier_avgs.get(next_tier, 0.0)
            # At the anchor point, use the value from the tier it starts
            mu_val = mu_next
            print(f"Rank {anchor:>3}        {mu_val:>11.3f}  {anchors[i]}-{anchors[i+1]:<10}  Transition point")
    print("=" * 80)
    
    # Process each match
    print("\n" + "=" * 80)
    print("PER-MATCH ANALYSIS")
    print("=" * 80)
    print(f"{'Match':<6} {'Opponent':<25} {'Wt':<4} {'Rank':<6} {'n':<4} {'RawAvg':<8} {'μ(r)':<8} {'Shrunk':<8} {'ExpVal':<8} {'Result':<8} {'MV':<8} {'Running Avg':<12}")
    print("-" * 80)
    
    mv_values = []
    running_sum = 0.0
    
    for idx, match in enumerate(wrestler_matches, 1):
        winner_id = match.get("winner_id")
        result = match.get("result", "")
        
        # Skip forfeits
        if "MFF" in result.upper() or "FORFEIT" in result.upper():
            print(f"{idx:<6} {'FORFEIT (skipped)':<25}")
            continue
        
        # Get opponent info (with weight class)
        try:
            opp_id, opp_weight, opp_rank = get_opponent_info(
                match, wrestler_id, args.season, weight, args.data_dir
            )
        except ValueError as e:
            print(f"{idx:<6} {'ERROR: ' + str(e):<25}")
            raise
        
        if not opp_id:
            print(f"{idx:<6} {'NO OPPONENT ID':<25}")
            continue
        
        # Get opponent name (from their weight class)
        opp_rank_map = weight_rank_maps[opp_weight]
        opp_name = get_wrestler_name(opp_id, opp_rank_map, args.data_dir, args.season, opp_weight)
        opp_name = opp_name[:24]  # Truncate for display
        
        # Get opponent match count
        opp_match_list = opponent_matches.get(opp_id, [])
        opp_n = len([m for m in opp_match_list if "MFF" not in m.get("result", "").upper()])
        
        # Get raw average
        opp_raw_avg = opponent_raw_avgs.get(opp_id, 0.0)
        
        # Get tier averages for opponent's weight class
        opp_tier_avgs = tier_avgs_by_weight[opp_weight]
        opp_max_rank = opp_rank_map.get("__max_rank__", 200)
        
        # Interpolate μ(r) using opponent's weight class tier averages
        mu_r, mu_debug = interpolate_mu(opp_rank, opp_tier_avgs, opp_max_rank, debug=(idx <= 3))
        
        # Debug output for first few matches
        if idx <= 3 and mu_debug:
            print(f"\n[DEBUG Match {idx}] μ(r) calculation for rank {opp_rank} (weight {opp_weight}):")
            if mu_debug["interpolated"]:
                band = mu_debug["band"]
                print(f"  Rank {opp_rank} is between anchors {band[0]} and {band[1]}")
                print(f"  μ({band[0]}) = {mu_debug['mu_a']:.3f}")
                print(f"  μ({band[1]}) = {mu_debug['mu_b']:.3f}")
                print(f"  Interpolated μ({opp_rank}) = {mu_r:.3f}")
            else:
                print(f"  Rank {opp_rank} is at anchor point")
                print(f"  μ({opp_rank}) = {mu_r:.3f}")
        
        # Shrink
        opp_shrunk = shrink_opponent_avg(opp_raw_avg, mu_r, opp_n)
        
        # Expected value
        expected_signed = -opp_shrunk
        
        # Result signed
        is_winner = (winner_id == wrestler_id)
        result_type = classify_result_type(result)
        result_signed = result_to_signed(result_type, is_winner)
        
        if result_signed is None:
            print(f"{idx:<6} {opp_name:<25} {opp_weight:<4} {opp_rank:<6} {opp_n:<4} {'UNKNOWN':<8}")
            continue
        
        # MV for this match
        mv_match = result_signed - expected_signed
        mv_values.append(mv_match)
        running_sum += mv_match
        running_avg = running_sum / len(mv_values)
        
        # Print row
        print(f"{idx:<6} {opp_name:<25} {opp_weight:<4} {opp_rank:<6} {opp_n:<4} "
              f"{opp_raw_avg:>7.2f} {mu_r:>7.2f} {opp_shrunk:>7.2f} {expected_signed:>7.2f} "
              f"{result_signed:>7.1f} {mv_match:>7.2f} {running_avg:>11.2f}")
    
    # Summary
    print("=" * 80)
    print("\nSUMMARY")
    print("=" * 80)
    if mv_values:
        final_mv = sum(mv_values) / len(mv_values)
        print(f"Wrestler: {wrestler_name}")
        print(f"Weight: {weight}")
        print(f"Matches counted: {len(mv_values)}")
        print(f"Final MV_avg: {final_mv:.3f}")
    else:
        print("No valid matches to compute MV.")


if __name__ == "__main__":
    main()

