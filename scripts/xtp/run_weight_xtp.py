#!/usr/bin/env python3
"""
Compute and display xTP leaderboard for a weight class using real WrestleData.

This script:
1. Loads rankings for a weight class
2. Loads wrestler profiles (MV and bonus EV)
3. Builds NCAA bracket with seeds
4. Runs xTP engine with real data
5. Displays leaderboard
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from xtp.engine.engine import BracketEngine
from xtp.engine.bracket_schema import get_all_slots


def load_rankings(season: int, weight: int, rankings_dir: str) -> List[Dict]:
    """
    Load rankings for a weight class.
    
    Args:
        season: Season year
        weight: Weight class
        rankings_dir: Directory containing rankings files
    
    Returns:
        List of ranking entries with wrestler_id, name, team, rank
    """
    rankings_path = Path(rankings_dir) / str(season) / f"rankings_{weight}.json"
    
    if not rankings_path.exists():
        raise FileNotFoundError(f"Rankings file not found: {rankings_path}")
    
    with rankings_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    
    return data.get("rankings", [])


def load_wrestler_profile(wrestler_id: str, season: int, wrestlers_dir: str) -> Optional[Dict]:
    """
    Load wrestler profile JSON.
    
    Args:
        wrestler_id: Wrestler ID
        season: Season year
        wrestlers_dir: Directory containing wrestler JSON files
    
    Returns:
        Wrestler profile dict or None if not found
    """
    wrestler_path = Path(wrestlers_dir) / str(season) / "by_id" / f"{wrestler_id}.json"
    
    if not wrestler_path.exists():
        return None
    
    try:
        with wrestler_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def extract_mv_from_profile(profile: Dict) -> float:
    """
    Extract Mat Value from wrestler profile.
    
    Args:
        profile: Wrestler profile dict
    
    Returns:
        MV value (default 0.0 if not found)
    """
    metrics = profile.get("metrics", {})
    mat_value = metrics.get("mat_value", {})
    return mat_value.get("mv_avg", 0.0)


def extract_bonus_ev_from_profile(profile: Dict) -> float:
    """
    Extract Top-33 bonus EV from wrestler profile.
    
    Args:
        profile: Wrestler profile dict
    
    Returns:
        Bonus EV value (default 0.0 if not found)
    """
    bonus = profile.get("bonus", {})
    return bonus.get("top33_bonus_ev_shrunk", 0.0)


def build_seeds_from_rankings(rankings: List[Dict], max_seeds: int = 33) -> Dict[int, str]:
    """
    Build seed mapping from rankings.
    
    Args:
        rankings: List of ranking entries
        max_seeds: Maximum number of seeds (33 for NCAA)
    
    Returns:
        Dict mapping seed number (1-33) to wrestler_id
    """
    seeds = {}
    
    # Sort by rank
    sorted_rankings = sorted(rankings, key=lambda x: x.get("rank", 9999))
    
    for idx, entry in enumerate(sorted_rankings[:max_seeds], 1):
        wrestler_id = entry.get("wrestler_id")
        if wrestler_id:
            seeds[idx] = wrestler_id
    
    return seeds


def load_wrestler_data(
    rankings: List[Dict],
    season: int,
    wrestlers_dir: str
) -> Dict[str, Dict]:
    """
    Load all wrestler data (MV, bonus EV, metadata) for ranked wrestlers.
    
    Args:
        rankings: List of ranking entries
        season: Season year
        wrestlers_dir: Directory containing wrestler JSON files
    
    Returns:
        Dict mapping wrestler_id to data dict with:
            - name
            - team
            - rank
            - mv
            - bonus_ev
    """
    wrestler_data = {}
    
    for entry in rankings:
        wrestler_id = entry.get("wrestler_id")
        if not wrestler_id:
            continue
        
        # Load profile
        profile = load_wrestler_profile(wrestler_id, season, wrestlers_dir)
        
        if profile:
            mv = extract_mv_from_profile(profile)
            bonus_ev = extract_bonus_ev_from_profile(profile)
        else:
            # Default values if profile not found
            mv = 0.0
            bonus_ev = 0.0
        
        wrestler_data[wrestler_id] = {
            "name": entry.get("name", "Unknown"),
            "team": entry.get("team", "Unknown"),
            "rank": entry.get("rank"),
            "mv": mv,
            "bonus_ev": bonus_ev,
        }
    
    return wrestler_data


def compute_xtp_for_weight(
    season: int,
    weight: int,
    rankings_dir: str,
    wrestlers_dir: str
) -> List[Dict]:
    """
    Compute xTP for all wrestlers at a weight class.
    
    Args:
        season: Season year
        weight: Weight class
        rankings_dir: Directory containing rankings files
        wrestlers_dir: Directory containing wrestler JSON files
    
    Returns:
        List of xTP entries with wrestler_id, name, team, rank, xTP_A, xTP_P, xTP_B, xTP
    """
    # Step 1: Load rankings
    print(f"Loading rankings for {weight} lbs...")
    all_rankings = load_rankings(season, weight, rankings_dir)
    print(f"  Found {len(all_rankings)} ranked wrestlers")
    
    if len(all_rankings) == 0:
        raise ValueError(f"No rankings found for weight {weight}")
    
    # Step 1.5: Filter to starters only
    starter_rankings = [r for r in all_rankings if r.get("is_starter", False)]
    print(f"  Found {len(starter_rankings)} starters")
    
    if len(starter_rankings) == 0:
        raise ValueError(f"No starters found for weight {weight}")
    
    # Sort starters by rank
    starter_rankings = sorted(starter_rankings, key=lambda x: x.get("rank", 9999))
    
    # Step 2: Load wrestler data (MV, bonus EV) - only for starters
    print(f"Loading wrestler profiles...")
    wrestler_data = load_wrestler_data(starter_rankings, season, wrestlers_dir)
    print(f"  Loaded data for {len(wrestler_data)} starters")
    
    # Step 3: Build seeds (top 33 starters)
    seeds = build_seeds_from_rankings(starter_rankings, max_seeds=33)
    print(f"  Built {len(seeds)} seeds from starters")
    
    if len(seeds) < 33:
        print(f"  Warning: Only {len(seeds)} seeds available (expected 33)")
    
    # Step 4: Build rank, MV, and bonus EV maps for engine (starters only)
    rank_by_id = {}
    mv_by_id = {}
    bonus_ev_by_id = {}
    
    # Build starter set for validation
    starter_ids = set(seeds.values())
    
    for wrestler_id, data in wrestler_data.items():
        # Only include starters
        if wrestler_id not in starter_ids:
            continue
        
        rank = data.get("rank")
        if rank:
            rank_by_id[wrestler_id] = rank
        mv_by_id[wrestler_id] = data.get("mv", 0.0)
        bonus_ev_by_id[wrestler_id] = data.get("bonus_ev", 0.0)
    
    # Step 5: Create bracket engine
    print(f"Building bracket engine...")
    slots = get_all_slots()
    
    engine = BracketEngine(
        slots=slots,
        seeds=seeds,
        enable_probability=True,
        rank_by_id=rank_by_id,
        mv_by_id=mv_by_id,
        bonus_ev_by_id=bonus_ev_by_id
    )
    
    # Step 6: Run engine (probabilistic, no deterministic overrides)
    # Resolve all slots probabilistically until convergence
    print(f"Running xTP computation...")
    print(f"  Resolving bracket probabilistically...")
    
    try:
        engine.resolve_all_probabilistically(max_iterations=100, epsilon=1e-9)
        # Filter out PLACE_* terminals for count (they're terminal references, not resolvable slots)
        actual_resolved = [s for s in engine.resolved_slots if not s.startswith("PLACE_")]
        actual_total = [s for s in engine.slots if not s.startswith("PLACE_")]
        print(f"  Resolved {len(actual_resolved)}/{len(actual_total)} slots")
        
        # Check placement slots specifically
        placement_slots = ["C_F_0", "CONS_3RD", "CONS_5TH", "CONS_7TH"]
        placement_resolved = [s for s in placement_slots if s in engine.resolved_slots]
        if len(placement_resolved) == len(placement_slots):
            print(f"  ✓ All placement slots resolved")
        else:
            missing = [s for s in placement_slots if s not in engine.resolved_slots]
            print(f"  Warning: {len(missing)} placement slots not resolved: {missing}")
    except RuntimeError as e:
        print(f"  Warning: {e}")
        actual_resolved = [s for s in engine.resolved_slots if not s.startswith("PLACE_")]
        actual_total = [s for s in engine.slots if not s.startswith("PLACE_")]
        print(f"  Resolved {len(actual_resolved)}/{len(actual_total)} slots")
    
    # Step 7: Compute expected points
    engine.compute_expected_points()
    
    # Step 7: Extract xTP components (starters only)
    print(f"Extracting xTP results...")
    components = engine.get_xtp_components()
    
    # Build starter set for filtering output
    starter_ids = set(seeds.values())
    
    # Step 8: Build result list
    results = []
    for wrestler_id, comps in components.items():
        # Only include starters
        if wrestler_id not in starter_ids:
            continue
        
        # Only include wrestlers that were in wrestler_data
        if wrestler_id not in wrestler_data:
            continue
        
        data = wrestler_data[wrestler_id]
        
        # Round components first, then compute xTP to avoid rounding errors
        xTP_A = round(comps["xTP_A"], 2)
        xTP_P = round(comps["xTP_P"], 2)
        xTP_B = round(comps["xTP_B"], 2)
        xTP = round(xTP_A + xTP_P + xTP_B, 2)  # Sum rounded components
        
        results.append({
            "wrestler_id": wrestler_id,
            "name": data["name"],
            "team": data["team"],
            "rank": data["rank"],
            "weight": weight,
            "mv": data.get("mv", 0.0),
            "bonus_ev": data.get("bonus_ev", 0.0),
            "xTP_A": xTP_A,
            "xTP_P": xTP_P,
            "xTP_B": xTP_B,
            "xTP": xTP,
        })
    
    return results


def sort_xtp_leaderboard(entries: List[Dict]) -> List[Dict]:
    """
    Sort xTP leaderboard entries.
    
    Sort descending by:
    1) xTP
    2) xTP_P
    3) xTP_A
    4) Rank (ascending)
    
    Args:
        entries: List of xTP entries
    
    Returns:
        Sorted list
    """
    def sort_key(entry: Dict) -> tuple:
        xTP = entry.get("xTP", 0.0)
        xTP_P = entry.get("xTP_P", 0.0)
        xTP_A = entry.get("xTP_A", 0.0)
        rank = entry.get("rank") or 9999
        
        return (-xTP, -xTP_P, -xTP_A, rank)
    
    return sorted(entries, key=sort_key)


def print_xtp_leaderboard(entries: List[Dict], limit: Optional[int] = None) -> None:
    """
    Print formatted xTP leaderboard table.
    
    Args:
        entries: Sorted list of xTP entries
        limit: Optional limit on number of entries to print
    """
    if limit:
        entries = entries[:limit]
    
    if not entries:
        print("No xTP data found.")
        return
    
    # Calculate column widths
    max_name_len = max(len(entry.get("name", "")) for entry in entries)
    max_team_len = max(len(entry.get("team", "")) for entry in entries)
    
    name_width = max(15, min(max_name_len + 2, 30))
    team_width = max(15, min(max_team_len + 2, 25))
    
    # Print header
    header = (
        f"{'Rank':<6} "
        f"{'Name':<{name_width}} "
        f"{'Team':<{team_width}} "
        f"{'MV':<7} "
        f"{'Bonus':<7} "
        f"{'xTP_A':<8} "
        f"{'xTP_P':<8} "
        f"{'xTP_B':<8} "
        f"{'xTP':<8}"
    )
    print(header)
    print("-" * len(header))
    
    # Print entries
    for entry in entries:
        rank = entry.get("rank")
        rank_str = str(rank) if rank else "—"
        name = entry.get("name", "Unknown")
        team = entry.get("team", "Unknown")
        mv = entry.get("mv", 0.0)
        bonus_ev = entry.get("bonus_ev", 0.0)
        xTP_A = entry.get("xTP_A", 0.0)
        xTP_P = entry.get("xTP_P", 0.0)
        xTP_B = entry.get("xTP_B", 0.0)
        xTP = entry.get("xTP", 0.0)
        
        # Truncate name/team if too long
        if len(name) > name_width - 2:
            name = name[:name_width - 5] + "..."
        if len(team) > team_width - 2:
            team = team[:team_width - 5] + "..."
        
        row = (
            f"{rank_str:<6} "
            f"{name:<{name_width}} "
            f"{team:<{team_width}} "
            f"{mv:>6.3f} "
            f"{bonus_ev:>6.3f} "
            f"{xTP_A:>7.2f} "
            f"{xTP_P:>7.2f} "
            f"{xTP_B:>7.2f} "
            f"{xTP:>7.2f}"
        )
        print(row)
    
    print(f"\nTotal entries: {len(entries)}")


def export_xtp_json(entries: List[Dict], season: int, weight: int, output_dir: str) -> Path:
    """
    Export xTP leaderboard to JSON file.
    
    Args:
        entries: Sorted list of xTP entries
        season: Season year
        weight: Weight class
        output_dir: Directory for output file
    
    Returns:
        Path to written file
    """
    output_path = Path(output_dir) / str(season)
    output_path.mkdir(parents=True, exist_ok=True)
    
    output_file = output_path / f"xtp_weight_{season}_{weight}.json"
    
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)
    
    print(f"\nExported JSON: {output_file}")
    print(f"  {len(entries)} entries")
    
    return output_file


def validate_results(results: List[Dict]) -> bool:
    """
    Validate xTP results.
    
    Args:
        results: List of xTP entries
    
    Returns:
        True if all valid, False otherwise
    """
    valid = True
    
    for entry in results:
        xTP_A = entry.get("xTP_A", 0.0)
        xTP_P = entry.get("xTP_P", 0.0)
        xTP_B = entry.get("xTP_B", 0.0)
        xTP = entry.get("xTP", 0.0)
        
        # Check for NaN
        if xTP_A != xTP_A or xTP_P != xTP_P or xTP_B != xTP_B or xTP != xTP:
            print(f"Warning: NaN detected for {entry.get('name')}")
            valid = False
        
        # Check sum (allow small floating point differences)
        expected_sum = xTP_A + xTP_P + xTP_B
        if abs(xTP - expected_sum) > 0.02:  # Allow 0.02 tolerance for rounding
            print(f"Warning: xTP sum mismatch for {entry.get('name')}: {xTP} != {expected_sum}")
            valid = False
        
        # Check non-negative
        if xTP_A < 0 or xTP_P < 0 or xTP_B < 0 or xTP < 0:
            print(f"Warning: Negative xTP for {entry.get('name')}")
            valid = False
    
    return valid


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Compute and display xTP leaderboard for a weight class"
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
        default="data/xtp",
        help="Directory for JSON export (optional)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of entries to print (optional)"
    )
    parser.add_argument(
        "--export-json",
        action="store_true",
        help="Export results to JSON file"
    )
    
    args = parser.parse_args()
    
    print(f"{'=' * 80}")
    print(f"xTP Leaderboard: Season {args.season}, Weight {args.weight} lbs")
    print(f"{'=' * 80}\n")
    
    try:
        # Compute xTP
        results = compute_xtp_for_weight(
            args.season,
            args.weight,
            args.rankings_dir,
            args.wrestlers_dir
        )
        
        if not results:
            print("No results computed.")
            return
        
        # Sort
        sorted_results = sort_xtp_leaderboard(results)
        
        # Validate
        print(f"\nValidating results...")
        if not validate_results(sorted_results):
            print("Warning: Some validation checks failed")
        
        # Print
        print(f"\n{'=' * 80}")
        print_xtp_leaderboard(sorted_results, limit=args.limit)
        
        # Export JSON if requested
        if args.export_json:
            export_xtp_json(sorted_results, args.season, args.weight, args.output_dir)
    
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

