#!/usr/bin/env python3
"""
Compute Top-33 bonus expected values for all wrestlers in a season.

This script processes all weight classes and updates wrestler JSON files
with bonus data, similar to compute_all_mat_values.py.
"""

import argparse
import json
from pathlib import Path
from typing import Dict

# Import from compute_top33_bonus
import sys
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))

from compute_top33_bonus import process_weight, find_wrestler_by_name
from typing import Optional


def compute_all_bonus(
    season: int,
    rankings_dir: str,
    wrestlers_dir: str,
    output_dir: str,
    debug_wrestler_id: Optional[str] = None,
    debug_weight: Optional[int] = None
) -> Dict[str, Dict]:
    """
    Compute Top-33 bonus for all wrestlers across all weight classes.
    
    Args:
        season: Season year
        rankings_dir: Directory containing rankings files
        wrestlers_dir: Directory containing wrestler JSON files
        output_dir: Directory for output files
    
    Returns:
        Dict mapping wrestler_id to bonus data
    """
    weights = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]
    
    all_bonus_data = {}
    
    print(f"Computing Top-33 bonus for season {season}...")
    print(f"Processing {len(weights)} weight classes\n")
    
    for weight in weights:
        try:
            # Only show debug for the specified weight
            debug_id = debug_wrestler_id if debug_weight == weight else None
            bonus_data = process_weight(
                season,
                weight,
                rankings_dir,
                wrestlers_dir,
                output_dir,
                debug_wrestler_id=debug_id
            )
            all_bonus_data.update(bonus_data)
        except FileNotFoundError as e:
            print(f"  ⚠ Skipping {weight} lbs: {e}")
            continue
        except Exception as e:
            print(f"  ✗ Error processing {weight} lbs: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print(f"\n✓ Processed {len(all_bonus_data)} wrestlers across all weights")
    
    return all_bonus_data


def write_bonus_cache(
    bonus_data: Dict[str, Dict],
    season: int,
    output_dir: str
) -> None:
    """
    Write bonus data cache file for use by other scripts.
    
    Args:
        bonus_data: Dict mapping wrestler_id to bonus data
        season: Season year
        output_dir: Directory for output files
    """
    cache_file = Path(output_dir) / str(season) / f"bonus_cache_{season}.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    
    with cache_file.open("w", encoding="utf-8") as f:
        json.dump(bonus_data, f, indent=2)
    
    print(f"\nWrote bonus cache: {cache_file}")
    print(f"  {len(bonus_data)} wrestlers")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Compute Top-33 bonus expected values for all wrestlers in a season"
    )
    parser.add_argument(
        "--season",
        type=int,
        required=True,
        help="Season year"
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
        default="data/bonus",
        help="Directory for output files"
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
    parser.add_argument(
        "--debug-weight",
        type=int,
        default=None,
        help="Weight class for debug output (required if using --debug-name or --debug-wrestler-id)"
    )
    
    args = parser.parse_args()
    
    debug_wrestler_id = args.debug_wrestler_id
    debug_weight = args.debug_weight
    
    # If name provided, search for wrestler
    if args.debug_name and not debug_wrestler_id:
        if not debug_weight:
            print("Error: --debug-weight is required when using --debug-name")
            return
        debug_wrestler_id = find_wrestler_by_name(
            args.debug_name,
            args.season,
            debug_weight,
            args.wrestlers_dir
        )
        if not debug_wrestler_id:
            print(f"Warning: No wrestler found matching '{args.debug_name}' at weight {debug_weight}")
    
    # Compute bonus for all wrestlers
    bonus_data = compute_all_bonus(
        args.season,
        args.rankings_dir,
        args.wrestlers_dir,
        args.output_dir,
        debug_wrestler_id=debug_wrestler_id,
        debug_weight=debug_weight
    )
    
    # Write cache file
    write_bonus_cache(bonus_data, args.season, args.output_dir)
    
    print("\n✓ Top-33 bonus computation complete for all weights")


if __name__ == "__main__":
    main()

