#!/usr/bin/env python3
"""
Build starter-only rankings files by filtering and re-ranking.

This script creates starter-only versions of rankings files where:
- Only wrestlers with is_starter=True (after applying overrides) are included
- Ranks are re-numbered consecutively (1, 2, 3, ...)
- Starter overrides are applied (force_backup_ids)

Output files: rankings_starters_<weight>.json

Usage:
    python scripts/rankings/build_starter_rankings.py -season 2026
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Set


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build starter-only rankings files"
    )
    parser.add_argument(
        "-season",
        type=int,
        required=True,
        help="Season year (e.g., 2026)",
    )
    parser.add_argument(
        "-league",
        type=str,
        choices=["ncaa", "hs"],
        default="ncaa",
        help="League: 'ncaa' (default) or 'hs' for high school",
    )
    parser.add_argument(
        "-state",
        type=str,
        default=None,
        help="State code (required when league=hs, e.g., 'KY')",
    )
    parser.add_argument(
        "-gender",
        type=str,
        default=None,
        choices=["men", "women", "boys", "girls"],
        help="Gender: men/women (NCAA) or boys/girls (HS). Defaults to 'men' for NCAA.",
    )
    parser.add_argument(
        "-data_dir",
        type=str,
        default=None,
        help="Directory containing rankings data (auto-determined if not specified)",
    )
    parser.add_argument(
        "-output_dir",
        type=str,
        default=None,
        help="Directory for output files (auto-determined if not specified)",
    )
    parser.add_argument(
        "-starter_overrides",
        type=str,
        default=None,
        help="Path to starter_overrides.json (optional)",
    )
    return parser.parse_args()


def load_starter_overrides(overrides_path: str) -> Set[str]:
    """Load starter overrides (force_backup_ids)."""
    if not overrides_path or not Path(overrides_path).exists():
        return set()
    
    try:
        with open(overrides_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("force_backup_ids", []))
    except Exception as e:
        print(f"Warning: Error loading starter overrides: {e}")
        return set()


def build_starter_rankings_for_weight(
    rankings: List[Dict],
    force_backup_ids: Set[str],
) -> List[Dict]:
    """
    Filter rankings to starters only and re-rank consecutively.
    
    Args:
        rankings: List of ranking entries from rankings_*.json
        force_backup_ids: Set of wrestler IDs to force as non-starters
        
    Returns:
        List of starter-only rankings with re-numbered ranks
    """
    # Filter to starters only (applying overrides)
    starters = []
    for entry in rankings:
        wrestler_id = entry.get("wrestler_id")
        is_starter = entry.get("is_starter", True)
        
        # Apply overrides: if in force_backup_ids, set is_starter to False
        if wrestler_id in force_backup_ids:
            is_starter = False
        
        if not is_starter:
            continue
        
        # Only include entries with valid numeric ranks
        rank = entry.get("rank")
        if rank is None:
            continue
        try:
            rank_int = int(rank)
        except (TypeError, ValueError):
            continue
        
        starters.append((rank_int, entry))
    
    # Sort by original rank
    starters.sort(key=lambda x: x[0])
    
    # Re-rank consecutively
    starter_rankings = []
    for new_rank, (orig_rank, entry) in enumerate(starters, start=1):
        new_entry = {
            **entry,
            "rank": new_rank,
            "original_rank": orig_rank,  # Keep original for reference
        }
        starter_rankings.append(new_entry)
    
    return starter_rankings


def process_league(
    season: int,
    league: str,
    state: str,
    gender: str,
    data_dir: Path,
    output_dir: Path,
    starter_overrides_path: Path,
) -> int:
    """
    Process starter rankings for a specific league/gender combination.
    
    Returns:
        Total number of starters processed
    """
    # Determine weight classes based on league and gender
    if league == "hs":
        if gender == "boys":
            weight_classes = ["106", "113", "120", "126", "132", "138", "144", "150", "157", "165", "175", "190", "215", "285"]
        else:  # girls
            weight_classes = ["100", "107", "114", "120", "126", "132", "138", "145", "152", "165", "185", "235"]
    else:  # ncaa
        weight_classes = ["125", "133", "141", "149", "157", "165", "174", "184", "197", "285"]
    
    # Load starter overrides
    force_backup_ids = load_starter_overrides(str(starter_overrides_path))
    
    total_starters = 0
    
    for weight in weight_classes:
        rankings_file = data_dir / f"rankings_{weight}.json"
        if not rankings_file.exists():
            print(f"  Warning: Rankings file not found: {rankings_file}")
            continue
        
        try:
            with rankings_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"  Warning: Error loading {rankings_file}: {e}")
            continue
        
        rankings = data.get("rankings", [])
        
        # Build starter-only rankings
        starter_rankings = build_starter_rankings_for_weight(rankings, force_backup_ids)
        
        # Save starter-only rankings to output directory
        output_file = output_dir / f"rankings_starters_{weight}.json"
        output_data = {
            "weight_class": weight,
            "season": season,
            "rankings": starter_rankings,
            "note": "Starter-only rankings with consecutive re-ranking. Original ranks preserved in 'original_rank' field.",
        }
        
        with output_file.open("w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"    {weight}: {len(rankings)} total -> {len(starter_rankings)} starters")
        total_starters += len(starter_rankings)
    
    return total_starters


def main() -> None:
    args = parse_args()
    season = args.season
    league = args.league
    state = args.state
    
    # Validate HS parameters
    if league == "hs":
        if not state:
            raise ValueError("State is required when league=hs (e.g., -state KY)")
        if state != "KY":
            raise ValueError(f"Only KY is currently supported for HS. Got: {state}")
    
    # Determine data and output directories
    if league == "hs":
        # HS mode: process both boys and girls
        genders = ["boys", "girls"]
        
        # Determine data directories
        if args.data_dir:
            base_data_dir = Path(args.data_dir)
        else:
            base_data_dir = Path("mt/rankings_data")
        
        # Determine output directory
        if args.output_dir:
            base_output_dir = Path(args.output_dir)
        else:
            base_output_dir = Path("frontend/hs-ky-ui/public/data/rankings")
        
        print(f"Building starter-only rankings for HS {state} (boys and girls) - season {season}...")
        
        total_all_starters = 0
        
        for gender in genders:
            print(f"\nProcessing {gender}...")
            
            # Data directory for this gender
            data_dir = base_data_dir / f"hs_ky_{gender}" / str(season)
            if not data_dir.exists():
                print(f"  Warning: Data directory not found: {data_dir}")
                continue
            
            print(f"  Data directory: {data_dir}")
            
            # Output directory for this gender
            output_dir = base_output_dir / gender / str(season)
            output_dir.mkdir(parents=True, exist_ok=True)
            print(f"  Output directory: {output_dir}")
            
            # Starter overrides path
            if args.starter_overrides:
                overrides_path = Path(args.starter_overrides)
            else:
                overrides_path = data_dir / "starter_overrides.json"
            
            # Process this gender
            total_starters = process_league(
                season, league, state, gender, data_dir, output_dir, overrides_path
            )
            
            total_all_starters += total_starters
            print(f"  {gender.capitalize()}: {total_starters} total starters")
        
        print(f"\nDone! Generated starter-only rankings for {total_all_starters} total starters (boys + girls)")
    
    else:
        # NCAA mode: original behavior
        ncaa_gender = args.gender or 'men'
        if args.data_dir:
            data_dir = Path(args.data_dir) / str(season)
        else:
            data_dir = Path("mt/rankings_data") / f"ncaa_{ncaa_gender}" / str(season)
        
        if not data_dir.exists():
            raise FileNotFoundError(f"Rankings directory not found: {data_dir}")
        
        print(f"Building starter-only rankings for season {season}...")
        print(f"Data directory: {data_dir}")
        
        # Set up output directory
        if args.output_dir:
            output_dir = Path(args.output_dir) / str(season)
        else:
            output_dir = Path("frontend/wrestledata-ui/public/data/rankings") / str(season)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"Output directory: {output_dir}")
        
        # Load starter overrides
        if args.starter_overrides:
            overrides_path = Path(args.starter_overrides)
        else:
            overrides_path = data_dir / "starter_overrides.json"
        
        # Process NCAA weight classes
        total_starters = process_league(
            season, league, None, None, data_dir, output_dir, overrides_path
        )
        
        print(f"\nDone! Generated starter-only rankings for {total_starters} total starters")


if __name__ == "__main__":
    main()

