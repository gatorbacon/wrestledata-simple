#!/usr/bin/env python3
"""
Compute Top-33 bonus expected values for wrestlers.

This script computes severity-weighted, NCAA-relevant bonus expectations
for each wrestler, to be consumed later by the xTP engine.
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


# Bonus severity mapping (NCAA-aligned)
BONUS_SEVERITY = {
    "DEC": 0.0,
    "MD": 1.0,
    "TF": 1.5,
    "FALL": 2.0,
    "INJ": 2.0,
    "DQ": 2.0,
}

# Shrinkage constant
K = 8

# Peer tier definitions
PEER_TIERS = {
    "P1": (1, 8),      # ranks 1-8
    "P2": (9, 16),     # ranks 9-16
    "P3": (17, 33),    # ranks 17-33
    "P4": (34, 9999),  # ranks 34+
}


def load_rankings(season: int, weight: int, data_dir: str) -> Tuple[Dict[str, int], Set[str]]:
    """
    Load rankings file and build Top-33 set.
    
    Args:
        season: Season year
        weight: Weight class
        data_dir: Directory containing rankings data
    
    Returns:
        Tuple of (rank_by_id dict, top33_ids set)
    """
    rankings_path = Path(data_dir) / str(season) / f"rankings_{weight}.json"
    
    if not rankings_path.exists():
        raise FileNotFoundError(f"Rankings file not found: {rankings_path}")
    
    with rankings_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    
    rank_by_id = {}
    top33_ids = set()
    
    for entry in data.get("rankings", []):
        wrestler_id = entry.get("wrestler_id")
        rank = entry.get("rank")
        
        if wrestler_id and rank:
            rank_by_id[wrestler_id] = rank
            if rank <= 33:
                top33_ids.add(wrestler_id)
    
    return rank_by_id, top33_ids


def get_bonus_severity(method: str) -> float:
    """
    Get bonus severity for a win method.
    
    Args:
        method: Win method (DEC, MD, TF, FALL, etc.)
    
    Returns:
        Severity value (0.0 to 2.0)
    """
    method_upper = method.upper() if method else "DEC"
    return BONUS_SEVERITY.get(method_upper, 0.0)


def get_peer_tier(rank: Optional[int]) -> str:
    """
    Get peer tier for a wrestler based on rank.
    
    Args:
        rank: Wrestler's rank (None if unranked)
    
    Returns:
        Peer tier (P1, P2, P3, or P4)
    """
    if rank is None:
        return "P4"
    
    for tier, (min_rank, max_rank) in PEER_TIERS.items():
        if min_rank <= rank <= max_rank:
            return tier
    
    return "P4"


def compute_raw_top33_bonus_ev(
    matches: List[Dict],
    wrestler_id: str,
    top33_ids: Set[str]
) -> Tuple[int, Optional[float]]:
    """
    Compute raw Top-33 bonus expected value for a wrestler.
    
    Args:
        matches: List of match dicts
        wrestler_id: Wrestler ID
        top33_ids: Set of Top-33 opponent IDs
    
    Returns:
        Tuple of (n_wins, raw_ev) where raw_ev is None if n_wins == 0
    """
    top33_wins = []
    
    for match in matches:
        # Only count wins
        if match.get("result") != "W":
            continue
        
        # Check if opponent is in Top-33
        opponent_id = match.get("opponent_id")
        if not opponent_id or opponent_id not in top33_ids:
            continue
        
        # Get method and compute severity
        method = match.get("method", "DEC")
        severity = get_bonus_severity(method)
        top33_wins.append(severity)
    
    n = len(top33_wins)
    
    if n == 0:
        return 0, None
    
    s = sum(top33_wins)
    raw_ev = s / n
    
    return n, raw_ev


def compute_peer_baselines(
    wrestler_data: Dict[str, Dict],
    rank_by_id: Dict[str, int]
) -> Dict[str, float]:
    """
    Compute peer baseline EVs for each tier.
    
    Args:
        wrestler_data: Dict mapping wrestler_id to bonus data
        rank_by_id: Dict mapping wrestler_id to rank
    
    Returns:
        Dict mapping tier -> baseline EV
    """
    tier_data = {tier: [] for tier in PEER_TIERS.keys()}
    
    # Collect raw EVs by tier
    for wrestler_id, data in wrestler_data.items():
        raw_ev = data.get("raw_ev")
        if raw_ev is None:
            continue
        
        rank = rank_by_id.get(wrestler_id)
        tier = get_peer_tier(rank)
        tier_data[tier].append(raw_ev)
    
    # Compute baselines with fallback hierarchy
    baselines = {}
    
    # Compute global baseline first (fallback for all tiers)
    all_evs = [ev for evs in tier_data.values() for ev in evs]
    global_baseline = sum(all_evs) / len(all_evs) if all_evs else 0.0
    
    # Compute baselines for each tier, with fallback
    for tier in ["P4", "P3", "P2", "P1"]:  # Process from broadest to narrowest
        if tier_data[tier]:
            baselines[tier] = sum(tier_data[tier]) / len(tier_data[tier])
        else:
            # Fall back to broader tier or global
            if tier == "P4":
                baselines[tier] = global_baseline
            elif tier == "P3":
                baselines[tier] = baselines.get("P4", global_baseline)
            elif tier == "P2":
                baselines[tier] = baselines.get("P3", baselines.get("P4", global_baseline))
            else:  # P1
                baselines[tier] = baselines.get("P2", baselines.get("P3", baselines.get("P4", global_baseline)))
    
    return baselines


def apply_shrinkage(
    n: int,
    raw_ev: Optional[float],
    peer_baseline: float
) -> float:
    """
    Apply shrinkage to raw bonus EV.
    
    Args:
        n: Number of Top-33 wins
        raw_ev: Raw bonus EV (None if n == 0)
        peer_baseline: Peer baseline EV
    
    Returns:
        Shrunk bonus EV (clamped to [0.0, 2.0])
    """
    if n == 0 or raw_ev is None:
        shrunk_ev = peer_baseline
    else:
        shrunk_ev = (n * raw_ev + K * peer_baseline) / (n + K)
    
    # Clamp to [0.0, 2.0]
    shrunk_ev = max(0.0, min(2.0, shrunk_ev))
    
    return shrunk_ev


def load_wrestler_json(wrestler_id: str, season: int, wrestlers_dir: str) -> Optional[Dict]:
    """
    Load wrestler JSON file.
    
    Args:
        wrestler_id: Wrestler ID
        season: Season year
        wrestlers_dir: Directory containing wrestler JSON files
    
    Returns:
        Wrestler JSON dict or None if not found
    """
    wrestler_path = Path(wrestlers_dir) / str(season) / "by_id" / f"{wrestler_id}.json"
    
    if not wrestler_path.exists():
        return None
    
    with wrestler_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def find_wrestler_by_name(
    name_query: str,
    season: int,
    weight: int,
    wrestlers_dir: str
) -> Optional[str]:
    """
    Find wrestler ID by name (partial match).
    
    Args:
        name_query: Name or partial name to search for
        season: Season year
        weight: Weight class
        wrestlers_dir: Directory containing wrestler JSON files
    
    Returns:
        Wrestler ID or None if not found
    """
    name_lower = name_query.lower()
    wrestler_files = Path(wrestlers_dir) / str(season) / "by_id"
    
    if not wrestler_files.exists():
        return None
    
    for wrestler_file in wrestler_files.glob("*.json"):
        try:
            with wrestler_file.open("r", encoding="utf-8") as f:
                wrestler_json = json.load(f)
            
            # Check weight
            if wrestler_json.get("weight_class") != weight:
                continue
            
            # Check name
            name = wrestler_json.get("name", "")
            if name_lower in name.lower():
                return wrestler_json.get("wrestler_id")
        except Exception:
            continue
    
    return None


def save_wrestler_json(wrestler_data: Dict, season: int, wrestlers_dir: str) -> None:
    """
    Save wrestler JSON file.
    
    Args:
        wrestler_data: Wrestler JSON dict
        season: Season year
        wrestlers_dir: Directory to save wrestler JSON files
    """
    wrestler_id = wrestler_data.get("wrestler_id")
    if not wrestler_id:
        return
    
    wrestler_path = Path(wrestlers_dir) / str(season) / "by_id" / f"{wrestler_id}.json"
    wrestler_path.parent.mkdir(parents=True, exist_ok=True)
    
    with wrestler_path.open("w", encoding="utf-8") as f:
        json.dump(wrestler_data, f, indent=2)


def compute_bonus_for_wrestler_debug(
    wrestler_id: str,
    matches: List[Dict],
    top33_ids: Set[str],
    rank_by_id: Dict[str, int],
    peer_baselines: Dict[str, float]
) -> None:
    """
    Debug output for bonus calculation for a specific wrestler.
    
    Args:
        wrestler_id: Wrestler ID
        matches: List of match dicts
        top33_ids: Set of Top-33 opponent IDs
        rank_by_id: Dict mapping wrestler_id to rank
        peer_baselines: Dict mapping tier to baseline EV
    """
    print("\n" + "=" * 80)
    print(f"BONUS CALCULATION DEBUG: {wrestler_id}")
    print("=" * 80)
    
    # Get wrestler rank and tier
    rank = rank_by_id.get(wrestler_id)
    tier = get_peer_tier(rank)
    peer_baseline = peer_baselines.get(tier, 0.0)
    
    print(f"\nWrestler Rank: {rank if rank else 'Unranked'}")
    print(f"Peer Tier: {tier}")
    print(f"Peer Baseline EV: {peer_baseline:.3f}")
    
    # Find Top-33 wins
    top33_wins = []
    print(f"\n{'Match':<6} {'Opponent ID':<20} {'Opponent Rank':<15} {'Method':<8} {'Severity':<10}")
    print("-" * 80)
    
    for idx, match in enumerate(matches, 1):
        # Only count wins
        if match.get("result") != "W":
            continue
        
        opponent_id = match.get("opponent_id")
        if not opponent_id or opponent_id not in top33_ids:
            continue
        
        method = match.get("method", "DEC")
        severity = get_bonus_severity(method)
        opp_rank = rank_by_id.get(opponent_id)
        
        top33_wins.append({
            "match_idx": idx,
            "opponent_id": opponent_id,
            "opponent_rank": opp_rank,
            "method": method,
            "severity": severity
        })
        
        print(f"{idx:<6} {opponent_id:<20} {str(opp_rank) if opp_rank else 'Unranked':<15} {method:<8} {severity:<10.1f}")
    
    print("=" * 80)
    
    # Compute raw EV
    n = len(top33_wins)
    if n == 0:
        print(f"\nTop-33 Wins: {n}")
        print(f"Raw Bonus EV: null (no Top-33 wins)")
        print(f"\nShrinkage Calculation:")
        print(f"  n = {n}")
        print(f"  Raw EV = null")
        print(f"  Peer Baseline = {peer_baseline:.3f}")
        print(f"  Shrunk EV = Peer Baseline = {peer_baseline:.3f}")
    else:
        s = sum(win["severity"] for win in top33_wins)
        raw_ev = s / n
        
        print(f"\nTop-33 Wins: {n}")
        print(f"Total Severity: {s:.1f}")
        print(f"Raw Bonus EV: {raw_ev:.3f} (sum of severities / number of wins)")
        
        # Shrinkage calculation
        shrunk_ev = apply_shrinkage(n, raw_ev, peer_baseline)
        
        print(f"\nShrinkage Calculation (K = {K}):")
        print(f"  n = {n}")
        print(f"  Raw EV = {raw_ev:.3f}")
        print(f"  Peer Baseline = {peer_baseline:.3f}")
        print(f"  Shrunk EV = (n * Raw + K * Baseline) / (n + K)")
        print(f"            = ({n} * {raw_ev:.3f} + {K} * {peer_baseline:.3f}) / ({n} + {K})")
        print(f"            = {(n * raw_ev + K * peer_baseline):.3f} / {n + K}")
        print(f"            = {shrunk_ev:.3f}")
    
    print("=" * 80)


def process_weight(
    season: int,
    weight: int,
    rankings_dir: str,
    wrestlers_dir: str,
    output_dir: str,
    debug_wrestler_id: Optional[str] = None
) -> Dict[str, Dict]:
    """
    Process a single weight class.
    
    Args:
        season: Season year
        weight: Weight class
        rankings_dir: Directory containing rankings files
        wrestlers_dir: Directory containing wrestler JSON files
        output_dir: Directory for output files
    
    Returns:
        Dict mapping wrestler_id to bonus data
    """
    print(f"\nProcessing {weight} lbs for season {season}...")
    
    # Step 1: Load rankings and build Top-33 set
    rank_by_id, top33_ids = load_rankings(season, weight, rankings_dir)
    print(f"  Loaded {len(rank_by_id)} ranked wrestlers")
    print(f"  Top-33 set: {len(top33_ids)} wrestlers")
    
    # Step 2: Process all wrestlers
    wrestler_data = {}
    wrestler_files = Path(wrestlers_dir) / str(season) / "by_id"
    
    if not wrestler_files.exists():
        print(f"  Warning: Wrestler directory not found: {wrestler_files}")
        return
    
    # If debug mode, check if wrestler exists first
    debug_wrestler_found = False
    if debug_wrestler_id:
        debug_wrestler_json = load_wrestler_json(debug_wrestler_id, season, wrestlers_dir)
        if debug_wrestler_json:
            debug_weight = debug_wrestler_json.get("weight_class")
            if debug_weight == weight:
                debug_wrestler_found = True
            else:
                print(f"  Debug: Wrestler {debug_wrestler_id} found but weight is {debug_weight} (expected {weight})")
        else:
            print(f"  Debug: Wrestler {debug_wrestler_id} JSON not found")
    
    for wrestler_file in wrestler_files.glob("*.json"):
        wrestler_id = wrestler_file.stem
        
        # Load wrestler JSON
        wrestler_json = load_wrestler_json(wrestler_id, season, wrestlers_dir)
        if not wrestler_json:
            continue
        
        # Check if this wrestler is at the correct weight
        if wrestler_json.get("weight_class") != weight:
            continue
        
        # Get match list
        matches = wrestler_json.get("match_list", [])
        
        # Step 3: Compute raw Top-33 bonus EV
        n_wins, raw_ev = compute_raw_top33_bonus_ev(matches, wrestler_id, top33_ids)
        
        wrestler_data[wrestler_id] = {
            "wrestler_id": wrestler_id,
            "n_wins": n_wins,
            "raw_ev": raw_ev,
            "wrestler_json": wrestler_json,
        }
    
    print(f"  Processed {len(wrestler_data)} wrestlers")
    
    # Step 4: Compute peer baselines
    bonus_data = {wid: {"raw_ev": data["raw_ev"]} for wid, data in wrestler_data.items()}
    peer_baselines = compute_peer_baselines(bonus_data, rank_by_id)
    print(f"  Peer baselines: {peer_baselines}")
    
    # Debug output for specific wrestler if requested
    if debug_wrestler_id:
        if debug_wrestler_id in wrestler_data:
            # Wrestler was processed - show full debug
            wrestler_json = wrestler_data[debug_wrestler_id]["wrestler_json"]
            matches = wrestler_json.get("match_list", [])
            compute_bonus_for_wrestler_debug(
                debug_wrestler_id,
                matches,
                top33_ids,
                rank_by_id,
                peer_baselines
            )
        else:
            # Try to load wrestler JSON directly for debug even if not in processed data
            debug_wrestler_json = load_wrestler_json(debug_wrestler_id, season, wrestlers_dir)
            if debug_wrestler_json:
                debug_weight = debug_wrestler_json.get("weight_class")
                if debug_weight == weight:
                    # Wrestler exists at this weight but wasn't processed - show debug anyway
                    matches = debug_wrestler_json.get("match_list", [])
                    print(f"\n  Debug: Wrestler {debug_wrestler_id} found but not in processed data")
                    print(f"  Showing debug output anyway...\n")
                    compute_bonus_for_wrestler_debug(
                        debug_wrestler_id,
                        matches,
                        top33_ids,
                        rank_by_id,
                        peer_baselines
                    )
                else:
                    print(f"\n  Debug: Wrestler {debug_wrestler_id} found but weight is {debug_weight} (expected {weight})")
                    print(f"  Cannot show debug for different weight class.")
            else:
                print(f"\n  Debug: Wrestler {debug_wrestler_id} not found")
                print(f"  Check if wrestler ID is correct and wrestler JSON exists")
                # Try to find similar wrestler IDs
                if debug_wrestler_id in rank_by_id:
                    rank = rank_by_id[debug_wrestler_id]
                    print(f"  Wrestler found in rankings at rank {rank}")
                else:
                    print(f"  Wrestler not found in rankings either")
    
    # Step 5: Apply shrinkage and update wrestler JSONs
    leaderboard_entries = []
    
    for wrestler_id, data in wrestler_data.items():
        n_wins = data["n_wins"]
        raw_ev = data["raw_ev"]
        wrestler_json = data["wrestler_json"]
        
        # Get peer tier and baseline
        rank = rank_by_id.get(wrestler_id)
        tier = get_peer_tier(rank)
        peer_baseline = peer_baselines.get(tier, 0.0)
        
        # Apply shrinkage
        shrunk_ev = apply_shrinkage(n_wins, raw_ev, peer_baseline)
        
        # Update wrestler JSON
        if "bonus" not in wrestler_json:
            wrestler_json["bonus"] = {}
        
        wrestler_json["bonus"]["top33_wins"] = n_wins
        wrestler_json["bonus"]["top33_bonus_ev_raw"] = raw_ev
        wrestler_json["bonus"]["top33_bonus_ev_shrunk"] = shrunk_ev
        
        # Save updated wrestler JSON
        save_wrestler_json(wrestler_json, season, wrestlers_dir)
        
        # Add to leaderboard (only if wrestler is in rankings or has Top-33 wins)
        if rank is not None or n_wins > 0:
            leaderboard_entries.append({
                "wrestler_id": wrestler_id,
                "weight": weight,
                "rank": rank,
                "top33_bonus_ev": shrunk_ev,
            })
    
    # Step 6: Create leaderboard JSON
    leaderboard_entries.sort(key=lambda x: (x["top33_bonus_ev"], -(x["rank"] or 9999)), reverse=True)
    
    output_path = Path(output_dir) / str(season)
    output_path.mkdir(parents=True, exist_ok=True)
    leaderboard_file = output_path / f"bonus_leaderboard_{season}_{weight}.json"
    
    with leaderboard_file.open("w", encoding="utf-8") as f:
        json.dump(leaderboard_entries, f, indent=2)
    
    print(f"  Wrote leaderboard: {leaderboard_file}")
    print(f"    {len(leaderboard_entries)} entries")
    
    # Validation
    for entry in leaderboard_entries:
        ev = entry["top33_bonus_ev"]
        assert not (ev != ev), f"NaN detected for {entry['wrestler_id']}"
        assert ev >= 0.0, f"Negative EV for {entry['wrestler_id']}: {ev}"
        assert ev <= 2.0, f"EV > 2.0 for {entry['wrestler_id']}: {ev}"
    
    print(f"  ✓ Validation passed")
    
    # Return bonus data for all wrestlers
    bonus_data = {}
    for wrestler_id, data in wrestler_data.items():
        rank = rank_by_id.get(wrestler_id)
        tier = get_peer_tier(rank)
        peer_baseline = peer_baselines.get(tier, 0.0)
        shrunk_ev = apply_shrinkage(data["n_wins"], data["raw_ev"], peer_baseline)
        
        bonus_data[wrestler_id] = {
            "top33_wins": data["n_wins"],
            "top33_bonus_ev_raw": data["raw_ev"],
            "top33_bonus_ev_shrunk": shrunk_ev,
        }
    
    return bonus_data


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Compute Top-33 bonus expected values for wrestlers"
    )
    parser.add_argument(
        "--season",
        type=int,
        required=True,
        help="Season year"
    )
    parser.add_argument(
        "--weight",
        type=int,
        required=True,
        help="Weight class"
    )
    parser.add_argument(
        "--rankings-dir",
        type=str,
        default="mt/rankings_data",
        help="Directory containing rankings files"
    )
    parser.add_argument(
        "--wrestlers-dir",
        type=str,
        default="frontend/wrestledata-ui/public/wrestlers",
        help="Directory containing wrestler JSON files"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="frontend/wrestledata-ui/public/data/bonus",
        help="Directory for output files (default: frontend/wrestledata-ui/public/data/bonus)"
    )
    parser.add_argument(
        "--debug-wrestler-id",
        type=str,
        default=None,
        help="Wrestler ID for debug output (optional)"
    )
    parser.add_argument(
        "--debug-name",
        type=str,
        default=None,
        help="Wrestler name (partial match) for debug output (optional)"
    )
    
    args = parser.parse_args()
    
    debug_wrestler_id = args.debug_wrestler_id
    
    # If name provided, search for wrestler
    if args.debug_name and not debug_wrestler_id:
        debug_wrestler_id = find_wrestler_by_name(
            args.debug_name,
            args.season,
            args.weight,
            args.wrestlers_dir
        )
        if not debug_wrestler_id:
            print(f"Warning: No wrestler found matching '{args.debug_name}'")
    
    process_weight(
        args.season,
        args.weight,
        args.rankings_dir,
        args.wrestlers_dir,
        args.output_dir,
        debug_wrestler_id=debug_wrestler_id
    )
    
    print("\n✓ Top-33 bonus computation complete")


if __name__ == "__main__":
    main()

