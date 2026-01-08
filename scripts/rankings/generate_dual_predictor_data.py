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
from typing import Dict, List, Optional


def get_weights_for_gender(gender: str) -> List[int]:
    """Return weight classes for the given gender."""
    if gender == 'boys':
        return [106, 113, 120, 126, 132, 138, 144, 150, 157, 165, 175, 190, 215, 285]
    elif gender == 'girls':
        return [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235]
    else:
        raise ValueError(f"Invalid gender: {gender}")


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


def load_team_rosters(
    season: int,
    gender: str,
    teams_dir: Path,
    rankings_by_weight: Dict[int, Dict[str, int]]
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
                name = starter_data.get("name", "Unknown")
                
                # Get rank from rankings
                rank = rankings_by_weight.get(weight, {}).get(wrestler_id)
                
                if weight_str not in roster["weights"]:
                    roster["weights"][weight_str] = []
                
                roster["weights"][weight_str].append({
                    "wrestler_id": wrestler_id,
                    "name": name,
                    "weight": weight,
                    "rank": rank,
                    "is_starter": True
                })
            
            # Process remaining roster
            remaining = team_data.get("remaining", [])
            for wrestler_data in remaining:
                weight = wrestler_data.get("weight")
                if not weight:
                    continue
                
                weight_str = str(weight)
                wrestler_id = str(wrestler_data.get("wrestler_id", ""))
                name = wrestler_data.get("name", "Unknown")
                
                # Get rank from rankings
                rank = rankings_by_weight.get(weight, {}).get(wrestler_id)
                
                if weight_str not in roster["weights"]:
                    roster["weights"][weight_str] = []
                
                roster["weights"][weight_str].append({
                    "wrestler_id": wrestler_id,
                    "name": name,
                    "weight": weight,
                    "rank": rank,
                    "is_starter": False
                })
            
            # Sort wrestlers within each weight: starters first, then by rank
            for weight_str in roster["weights"]:
                wrestlers = roster["weights"][weight_str]
                wrestlers.sort(key=lambda w: (
                    not w["is_starter"],  # Starters first
                    w["rank"] if w["rank"] is not None else 9999  # Then by rank
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
                # Determine is_highest_ranked: True if is_starter is True or not present
                # (in full rankings, starters are marked with is_starter: true)
                is_starter = wrestler.get("is_starter", False)
                is_highest_ranked = wrestler.get("is_highest_ranked", is_starter)
                
                simplified.append({
                    "wrestler_id": str(wrestler.get("wrestler_id", "")),
                    "rank": wrestler.get("rank"),
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
    
    # Load FULL rankings to resolve ranks
    print("Loading FULL rankings from mt/rankings_data...")
    rankings_by_weight = load_rankings_by_weight(season, gender, data_dir)
    
    # Load team rosters
    all_rosters = load_team_rosters(season, gender, teams_dir, rankings_by_weight)
    
    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(all_rosters, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Generated: {output_path}")
    print(f"  Teams: {len(all_rosters)}")


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
    
    print(f"Generating Dual Predictor data for {args.gender} {args.season}...")
    print(f"Teams directory: {teams_dir}")
    print(f"Rankings data directory: {data_dir}")
    print(f"Using FULL rankings from: {data_dir}/hs_ky_{args.gender}/{args.season}/")
    
    # Generate both files
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
    
    print("\n✓ Dual Predictor data generation complete!")


if __name__ == "__main__":
    main()

