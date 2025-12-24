#!/usr/bin/env python3
"""
Auto-sort rankings by MV value, preserving top 100 and moving 0-0 records to bottom.

Priority order:
1. Top 100 wrestlers (ranks 1-100) are UNTOUCHED - kept exactly as-is, even if 0-0
2. 0-0 records (rank > 100) are moved to the bottom
3. Remaining wrestlers (rank > 100, not 0-0) are sorted by MV value descending, starting at rank 101
   - Even negative MV wrestlers are ranked above 0-0 records
4. All ranks are renumbered consecutively (1, 2, 3, ...)

Usage:
    # Single weight class
    python scripts/rankings/auto_sort_by_mv.py -season 2026 -weight 125
    
    # All weight classes
    python scripts/rankings/auto_sort_by_mv.py -season 2026 --all-weights
    
    # Dry run (preview without saving)
    python scripts/rankings/auto_sort_by_mv.py -season 2026 -weight 125 --dry-run
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def parse_record(record_str: str) -> Tuple[int, int]:
    """
    Parse a record string like "5-1" into (wins, losses).
    
    Args:
        record_str: Record string (e.g., "5-1", "0-0", "12-3")
        
    Returns:
        Tuple of (wins, losses)
    """
    if not record_str:
        return (0, 0)
    
    try:
        parts = record_str.split("-")
        if len(parts) == 2:
            wins = int(parts[0].strip())
            losses = int(parts[1].strip())
            return (wins, losses)
    except (ValueError, AttributeError):
        pass
    
    return (0, 0)


def is_zero_zero(record_str: str) -> bool:
    """Check if a record is 0-0."""
    wins, losses = parse_record(record_str)
    return wins == 0 and losses == 0


def load_mv_data(season: int, mv_file: Path) -> Dict[str, float]:
    """
    Load MV data from mat_value JSON file.
    
    Args:
        season: Season year
        mv_file: Path to mat_value_<season>.json
        
    Returns:
        Dictionary mapping wrestler_id -> mv_avg
    """
    if not mv_file.exists():
        print(f"Warning: MV file not found: {mv_file}")
        return {}
    
    try:
        with mv_file.open("r", encoding="utf-8") as f:
            mv_list = json.load(f)
        
        mv_map = {}
        for entry in mv_list:
            wrestler_id = str(entry.get("wrestler_id", ""))
            mv_avg = entry.get("mv_avg", 0.0)
            if wrestler_id:
                mv_map[wrestler_id] = mv_avg
        
        print(f"Loaded MV data for {len(mv_map)} wrestlers")
        return mv_map
    except Exception as e:
        print(f"Error loading MV data: {e}")
        return {}


def load_rankings(rankings_file: Path) -> Dict:
    """
    Load rankings from JSON file.
    
    Args:
        rankings_file: Path to rankings_<weight>.json
        
    Returns:
        Rankings dictionary with 'weight_class', 'season', 'rankings'
    """
    if not rankings_file.exists():
        raise FileNotFoundError(f"Rankings file not found: {rankings_file}")
    
    with rankings_file.open("r", encoding="utf-8") as f:
        return json.load(f)


def auto_sort_rankings(
    rankings_data: Dict,
    mv_map: Dict[str, float],
    weight_class: str
) -> Dict:
    """
    Auto-sort rankings with priority:
    1. Top 100 untouched (even if 0-0)
    2. 0-0 records (rank > 100) go to bottom
    3. Rest (rank > 100, not 0-0) sorted by MV, starting at rank 101
    
    Args:
        rankings_data: Original rankings dictionary
        mv_map: Dictionary mapping wrestler_id -> mv_avg
        weight_class: Weight class string (for filtering MV by weight if needed)
        
    Returns:
        Updated rankings dictionary with reordered and renumbered entries
    """
    original_rankings = rankings_data.get("rankings", [])
    
    if not original_rankings:
        print(f"  No rankings found for {weight_class}")
        return rankings_data
    
    # Split into three groups with correct priority
    top_100 = []        # Ranks 1-100 (untouched, even if 0-0)
    rest_not_zero = []  # Rank > 100, not 0-0 (will be sorted by MV)
    zero_zero_below_100 = []  # Rank > 100, 0-0 records (go to bottom)
    
    for entry in original_rankings:
        rank = entry.get("rank", 999999)
        record = entry.get("record", "")
        is_0_0 = is_zero_zero(record)
        
        if rank <= 100:
            # Top 100: keep exactly as-is, regardless of record
            top_100.append(entry)
        elif is_0_0:
            # 0-0 records below rank 100: move to bottom
            zero_zero_below_100.append(entry)
        else:
            # Rank > 100, not 0-0: sort by MV
            rest_not_zero.append(entry)
    
    # Sort rest by MV (descending), then by original rank if MV is missing
    # Even negative MV should be above 0-0 records
    def sort_key(entry):
        wrestler_id = str(entry.get("wrestler_id", ""))
        mv_value = mv_map.get(wrestler_id, -999.0)  # Missing MV goes to bottom
        original_rank = entry.get("rank", 999999)
        return (-mv_value, original_rank)  # Negative for descending
    
    rest_sorted = sorted(rest_not_zero, key=sort_key)
    
    # Combine: Top 100 (unchanged) + Rest (sorted by MV) + 0-0 records (bottom)
    new_rankings = top_100 + rest_sorted + zero_zero_below_100
    
    # Renumber ranks consecutively
    for idx, entry in enumerate(new_rankings, start=1):
        entry["rank"] = idx
    
    # Count statistics
    top_100_count = len(top_100)
    rest_count = len(rest_sorted)
    zero_zero_count = len(zero_zero_below_100)
    
    # Count 0-0 in top 100 for reporting
    top_100_zero_zero = sum(1 for e in top_100 if is_zero_zero(e.get("record", "")))
    
    print(f"  Top 100 (preserved, {top_100_zero_zero} with 0-0): {top_100_count}")
    print(f"  Rest (sorted by MV, starting rank 101): {rest_count}")
    print(f"  0-0 records (rank > 100, bottom): {zero_zero_count}")
    print(f"  Total: {len(new_rankings)}")
    
    # Update rankings data
    updated_data = rankings_data.copy()
    updated_data["rankings"] = new_rankings
    updated_data["auto_sorted_by_mv"] = True
    
    return updated_data


def process_weight_class(
    season: int,
    weight: int,
    data_dir: str,
    mv_map: Dict[str, float],
    dry_run: bool = False
) -> None:
    """
    Process a single weight class.
    
    Args:
        season: Season year
        weight: Weight class
        data_dir: Directory containing rankings files
        mv_map: MV data dictionary
        dry_run: If True, don't save changes
    """
    rankings_path = Path(data_dir) / str(season) / f"rankings_{weight}.json"
    
    if not rankings_path.exists():
        print(f"  Skipping {weight} lbs: file not found")
        return
    
    print(f"\nProcessing {weight} lbs...")
    
    # Load rankings
    rankings_data = load_rankings(rankings_path)
    original_count = len(rankings_data.get("rankings", []))
    
    # Auto-sort
    updated_data = auto_sort_rankings(rankings_data, mv_map, str(weight))
    
    if dry_run:
        print(f"  [DRY RUN] Would update {original_count} entries")
    else:
        # Save updated rankings
        with rankings_path.open("w", encoding="utf-8") as f:
            json.dump(updated_data, f, indent=2)
        print(f"  ✅ Saved updated rankings to {rankings_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Auto-sort rankings by MV, preserving top 100 and moving 0-0 to bottom"
    )
    parser.add_argument(
        "-season",
        type=int,
        required=True,
        help="Season year (e.g., 2026)",
    )
    parser.add_argument(
        "-weight",
        type=int,
        help="Weight class (e.g., 125). Required unless --all-weights is used.",
    )
    parser.add_argument(
        "--all-weights",
        action="store_true",
        help="Process all weight classes",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="mt/rankings_data",
        help="Directory containing rankings files (default: mt/rankings_data)",
    )
    parser.add_argument(
        "--mv-file",
        type=str,
        default=None,
        help="Path to mat_value JSON file (default: auto-detect)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without saving",
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.all_weights and args.weight is None:
        parser.error("Must specify either -weight or --all-weights")
    
    if args.all_weights and args.weight is not None:
        parser.error("Cannot specify both -weight and --all-weights")
    
    # Determine MV file path
    if args.mv_file:
        mv_file = Path(args.mv_file)
    else:
        mv_file = Path(f"frontend/wrestledata-ui/public/data/mat_value/{args.season}/mat_value_{args.season}.json")
    
    # Load MV data
    print(f"Loading MV data from {mv_file}...")
    mv_map = load_mv_data(args.season, mv_file)
    
    if not mv_map:
        print("Warning: No MV data loaded. Wrestlers without MV will be sorted by original rank.")
    
    # Process weight class(es)
    if args.all_weights:
        weights = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]
        print(f"\nProcessing all {len(weights)} weight classes...")
        for weight in weights:
            process_weight_class(
                args.season,
                weight,
                args.data_dir,
                mv_map,
                dry_run=args.dry_run
            )
    else:
        process_weight_class(
            args.season,
            args.weight,
            args.data_dir,
            mv_map,
            dry_run=args.dry_run
        )
    
    print("\n✅ Done!")


if __name__ == "__main__":
    main()

