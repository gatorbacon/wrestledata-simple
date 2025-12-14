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


def load_rankings(season: int, weight: int, data_dir: str) -> Dict[str, int]:
    """Load rankings and return dict mapping wrestler_id -> rank."""
    rankings_file = Path(data_dir) / str(season) / f"rankings_{weight}.json"
    
    if not rankings_file.exists():
        raise FileNotFoundError(f"Rankings file not found: {rankings_file}")
    
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
    
    return rank_map


def load_wrestler_matches(season: int, weight: int, wrestler_id: str, data_dir: str) -> List[Dict]:
    """Load all matches for a wrestler from weight class files."""
    data_path = Path(data_dir) / str(season)
    matches = []
    
    # Check both weight_class_<weight>.json and weight_class_<weight>A.json
    for pattern in [f"weight_class_{weight}.json", f"weight_class_{weight}A.json"]:
        wc_file = data_path / pattern
        if not wc_file.exists():
            continue
        
        try:
            with wc_file.open("r", encoding="utf-8") as f:
                wc_data = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load {wc_file}: {e}")
            continue
        
        for match in wc_data.get("matches", []):
            w1_id = match.get("wrestler1_id")
            w2_id = match.get("wrestler2_id")
            
            # Include match if wrestler is either participant
            if w1_id == wrestler_id or w2_id == wrestler_id:
                matches.append(match)
    
    return matches


def get_opponent_info(match: Dict, wrestler_id: str, rank_map: Dict[str, int]) -> Tuple[Optional[str], Optional[int]]:
    """Get opponent ID and rank from a match."""
    w1_id = match.get("wrestler1_id")
    w2_id = match.get("wrestler2_id")
    
    if w1_id == wrestler_id:
        opp_id = w2_id
    elif w2_id == wrestler_id:
        opp_id = w1_id
    else:
        return None, None
    
    # Get rank (use max_rank if missing)
    opp_rank = rank_map.get(opp_id, rank_map.get("__max_rank__", 200))
    
    return opp_id, opp_rank


def load_all_matches_for_opponents(season: int, weight: int, opponent_ids: set, data_dir: str) -> Dict[str, List[Dict]]:
    """Load all matches for a set of opponents."""
    data_path = Path(data_dir) / str(season)
    matches_by_opponent = defaultdict(list)
    
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
            winner_id = match.get("winner_id")
            result = match.get("result", "")
            
            # Skip forfeits
            if "MFF" in result.upper() or "FORFEIT" in result.upper():
                continue
            
            # Include if either wrestler is in our opponent set
            if w1_id in opponent_ids:
                matches_by_opponent[w1_id].append(match)
            if w2_id in opponent_ids:
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
    debug: bool = False
) -> Dict[Tuple[int, int], float]:
    """
    Compute tier averages for rank anchor bands.
    
    For each tier (e.g., 1-10), includes ALL matches by ALL wrestlers in that rank range.
    
    Returns dict mapping (start_rank, end_rank) -> average
    """
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
        print("TIER AVERAGES (μ at anchor nodes)")
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
    """Load all wrestlers from all weight class rankings files."""
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
    """Load all wrestlers from rankings file for a specific weight."""
    rankings_file = Path(data_dir) / str(season) / f"rankings_{weight}.json"
    
    if not rankings_file.exists():
        return []
    
    with rankings_file.open("r", encoding="utf-8") as f:
        data = json.load(f)
    
    return data.get("rankings", [])


def get_wrestler_name(wrestler_id: str, rank_map: Dict[str, int], data_dir: str, season: int, weight: int) -> str:
    """Get wrestler name from rankings."""
    rankings_file = Path(data_dir) / str(season) / f"rankings_{weight}.json"
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
    """Get wrestler's weight class by searching all weight files."""
    for weight in [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]:
        rankings_file = Path(data_dir) / str(season) / f"rankings_{weight}.json"
        if not rankings_file.exists():
            continue
        
        try:
            with rankings_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            for entry in data.get("rankings", []):
                if entry.get("wrestler_id") == wrestler_id:
                    return weight
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
    rank_map = load_rankings(args.season, weight, args.data_dir)
    max_rank = rank_map.get("__max_rank__", 200)
    print(f"Loaded {len(rank_map) - 1} ranked wrestlers (max rank: {max_rank})")
    
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
    
    # Collect opponent IDs
    opponent_ids = set()
    for match in wrestler_matches:
        opp_id, _ = get_opponent_info(match, wrestler_id, rank_map)
        if opp_id:
            opponent_ids.add(opp_id)
    
    print(f"Found {len(opponent_ids)} unique opponents")
    
    # Load all matches for opponents
    print("\nLoading opponent matches...")
    opponent_matches = load_all_matches_for_opponents(args.season, weight, opponent_ids, args.data_dir)
    print(f"Loaded matches for {len(opponent_matches)} opponents")
    
    # Compute raw opponent averages
    print("\nComputing opponent raw averages...")
    opponent_raw_avgs = compute_opponent_raw_averages(opponent_matches, rank_map)
    
    # Compute tier averages (from ALL matches by ALL wrestlers in each tier)
    print("\nComputing tier averages...")
    tier_avgs = compute_tier_averages(args.season, weight, rank_map, args.data_dir, debug=True)
    
    # Show expected values at each anchor point
    print("\n" + "=" * 80)
    print("EXPECTED VALUES AT ANCHOR NODES")
    print("=" * 80)
    print("These are the μ(r) values at each major rank anchor point.")
    print("Values represent the average observed performance for wrestlers in each tier.")
    print("(Values are interpolated between anchors for intermediate ranks)")
    print("-" * 80)
    anchors = [1, 10, 30, 50, 100, 150, 200]
    anchors = [a for a in anchors if a <= max_rank]
    if anchors[-1] < max_rank:
        anchors.append(max_rank)
    
    print(f"{'Anchor Rank':<15} {'μ(r)':<12} {'Tier Range':<15} {'Description'}")
    print("-" * 80)
    for i in range(len(anchors)):
        anchor = anchors[i]
        # Find which tier this anchor belongs to
        if i == 0:
            # First anchor uses first tier
            tier_key = (anchors[0], anchors[1])
            mu_val = tier_avgs.get(tier_key, 0.0)
            print(f"Rank {anchor:>3}        {mu_val:>11.3f}  {anchors[0]}-{anchors[1]:<10}  Start of curve")
        elif i == len(anchors) - 1:
            # Last anchor uses last tier
            tier_key = (anchors[i-1], anchors[i])
            mu_val = tier_avgs.get(tier_key, 0.0)
            print(f"Rank {anchor:>3}        {mu_val:>11.3f}  {anchors[i-1]}-{anchors[i]:<10}  End of curve")
        else:
            # Middle anchors: show both adjacent tiers and interpolate
            prev_tier = (anchors[i-1], anchors[i])
            next_tier = (anchors[i], anchors[i+1])
            mu_prev = tier_avgs.get(prev_tier, 0.0)
            mu_next = tier_avgs.get(next_tier, 0.0)
            # At the anchor point, use the value from the tier it starts
            mu_val = mu_next
            print(f"Rank {anchor:>3}        {mu_val:>11.3f}  {anchors[i]}-{anchors[i+1]:<10}  Transition point")
    print("=" * 80)
    
    # Process each match
    print("\n" + "=" * 80)
    print("PER-MATCH ANALYSIS")
    print("=" * 80)
    print(f"{'Match':<6} {'Opponent':<25} {'Rank':<6} {'n':<4} {'RawAvg':<8} {'μ(r)':<8} {'Shrunk':<8} {'ExpVal':<8} {'Result':<8} {'MV':<8} {'Running Avg':<12}")
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
        
        # Get opponent info
        opp_id, opp_rank = get_opponent_info(match, wrestler_id, rank_map)
        if not opp_id:
            print(f"{idx:<6} {'UNKNOWN OPPONENT':<25}")
            continue
        
        # Get opponent name
        opp_name = get_wrestler_name(opp_id, rank_map, args.data_dir, args.season, weight)
        opp_name = opp_name[:24]  # Truncate for display
        
        # Get opponent match count
        opp_match_list = opponent_matches.get(opp_id, [])
        opp_n = len([m for m in opp_match_list if "MFF" not in m.get("result", "").upper()])
        
        # Get raw average
        opp_raw_avg = opponent_raw_avgs.get(opp_id, 0.0)
        
        # Interpolate μ(r)
        mu_r, mu_debug = interpolate_mu(opp_rank, tier_avgs, max_rank, debug=(idx <= 3))
        
        # Debug output for first few matches
        if idx <= 3 and mu_debug:
            print(f"\n[DEBUG Match {idx}] μ(r) calculation for rank {opp_rank}:")
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
            print(f"{idx:<6} {opp_name:<25} {opp_rank:<6} {opp_n:<4} {'UNKNOWN':<8}")
            continue
        
        # MV for this match
        mv_match = result_signed - expected_signed
        mv_values.append(mv_match)
        running_sum += mv_match
        running_avg = running_sum / len(mv_values)
        
        # Print row
        print(f"{idx:<6} {opp_name:<25} {opp_rank:<6} {opp_n:<4} "
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

