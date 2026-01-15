#!/usr/bin/env python3
"""
Merge two duplicate careers into one.

This script:
1. Combines seasons from both careers
2. Uses the better name (or prompts user)
3. Updates name_norm
4. Deletes the duplicate career file
5. Verifies no conflicts
"""

import json
import argparse
from pathlib import Path
from typing import Dict, Optional


def normalize_name(name: str) -> str:
    """Normalize a wrestler's name for matching."""
    if not name:
        return ""
    import re
    normalized = name.lower().strip()
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized


def load_career(career_id: str) -> Optional[Dict]:
    """Load a career file."""
    career_file = Path("data/careers") / f"{career_id}.json"
    if not career_file.exists():
        return None
    with open(career_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_career(career: Dict) -> None:
    """Save a career file."""
    career_id = career.get('career_id')
    if not career_id:
        raise ValueError("Career missing career_id")
    career_file = Path("data/careers") / f"{career_id}.json"
    with open(career_file, 'w', encoding='utf-8') as f:
        json.dump(career, f, indent=2, ensure_ascii=False)


def merge_careers(
    keep_career_id: str,
    merge_career_id: str,
    preferred_name: Optional[str] = None
) -> Dict:
    """
    Merge two careers.
    
    Args:
        keep_career_id: Career ID to keep (will be updated with merged data)
        merge_career_id: Career ID to merge into keep_career (will be deleted)
        preferred_name: Optional preferred name (if None, uses keep_career's name)
    
    Returns:
        Updated career dictionary
    
    Raises:
        ValueError: If careers can't be merged (conflicting seasons, etc.)
    """
    keep_career = load_career(keep_career_id)
    merge_career = load_career(merge_career_id)
    
    if not keep_career:
        raise ValueError(f"Career {keep_career_id} not found")
    if not merge_career:
        raise ValueError(f"Career {merge_career_id} not found")
    
    # Check for conflicting seasons
    keep_seasons = set(keep_career.get('seasons', {}).keys())
    merge_seasons = set(merge_career.get('seasons', {}).keys())
    conflicting_seasons = keep_seasons & merge_seasons
    
    if conflicting_seasons:
        raise ValueError(
            f"Cannot merge: Both careers have seasons {conflicting_seasons}. "
            f"Keep career has: {keep_career.get('seasons', {})}, "
            f"Merge career has: {merge_career.get('seasons', {})}"
        )
    
    # Merge seasons
    merged_seasons = {**keep_career.get('seasons', {}), **merge_career.get('seasons', {})}
    
    # Choose name
    if preferred_name:
        canonical_name = preferred_name
    else:
        # Use the name from the career with more seasons, or keep_career if equal
        if len(merge_seasons) > len(keep_seasons):
            canonical_name = merge_career.get('canonical_name', '')
        else:
            canonical_name = keep_career.get('canonical_name', '')
    
    # Update career
    keep_career['canonical_name'] = canonical_name
    keep_career['name_norm'] = normalize_name(canonical_name)
    keep_career['seasons'] = merged_seasons
    
    # Use the earlier created_from_season
    keep_created = keep_career.get('created_from_season', 9999)
    merge_created = merge_career.get('created_from_season', 9999)
    keep_career['created_from_season'] = min(keep_created, merge_created)
    
    # Merge notes if either has notes
    keep_notes = keep_career.get('notes')
    merge_notes = merge_career.get('notes')
    if merge_notes and not keep_notes:
        keep_career['notes'] = merge_notes
    elif keep_notes and merge_notes:
        keep_career['notes'] = f"{keep_notes}; Merged from {merge_career_id}: {merge_notes}"
    
    return keep_career


def main():
    parser = argparse.ArgumentParser(
        description='Merge two duplicate careers'
    )
    parser.add_argument(
        '--keep',
        type=str,
        required=True,
        help='Career ID to keep (e.g., career_000025)'
    )
    parser.add_argument(
        '--merge',
        type=str,
        required=True,
        help='Career ID to merge into keep (will be deleted)'
    )
    parser.add_argument(
        '--name',
        type=str,
        help='Preferred name (optional, will use keep career name if not specified)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )
    
    args = parser.parse_args()
    
    # Normalize career IDs
    keep_id = args.keep if args.keep.startswith('career_') else f"career_{args.keep.zfill(6)}"
    merge_id = args.merge if args.merge.startswith('career_') else f"career_{args.merge.zfill(6)}"
    
    print(f"\n{'='*80}")
    print("MERGE CAREERS")
    print(f"{'='*80}")
    
    # Load both careers
    keep_career = load_career(keep_id)
    merge_career = load_career(merge_id)
    
    if not keep_career:
        print(f"❌ Error: Career {keep_id} not found")
        return 1
    
    if not merge_career:
        print(f"❌ Error: Career {merge_id} not found")
        return 1
    
    print(f"\nKeep Career ({keep_id}):")
    print(f"  Name: {keep_career.get('canonical_name')}")
    print(f"  Seasons: {list(keep_career.get('seasons', {}).keys())}")
    
    print(f"\nMerge Career ({merge_id}):")
    print(f"  Name: {merge_career.get('canonical_name')}")
    print(f"  Seasons: {list(merge_career.get('seasons', {}).keys())}")
    
    # Check for conflicts
    keep_seasons = set(keep_career.get('seasons', {}).keys())
    merge_seasons = set(merge_career.get('seasons', {}).keys())
    conflicting = keep_seasons & merge_seasons
    
    if conflicting:
        print(f"\n❌ Error: Cannot merge - both careers have seasons: {conflicting}")
        return 1
    
    # Determine final name
    if args.name:
        final_name = args.name
    elif len(merge_seasons) > len(keep_seasons):
        final_name = merge_career.get('canonical_name', '')
    else:
        final_name = keep_career.get('canonical_name', '')
    
    print(f"\nMerged result:")
    print(f"  Name: {final_name}")
    print(f"  Seasons: {sorted(list(keep_seasons | merge_seasons))}")
    
    if args.dry_run:
        print("\n🔍 DRY RUN - No changes made")
        return 0
    
    # Confirm
    response = input(f"\n⚠️  This will merge {merge_id} into {keep_id} and DELETE {merge_id}. Continue? [y/N]: ").strip().lower()
    if response != 'y':
        print("Cancelled")
        return 0
    
    # Perform merge
    try:
        merged_career = merge_careers(keep_id, merge_id, args.name)
        
        # Save merged career
        save_career(merged_career)
        print(f"\n✅ Updated {keep_id}")
        
        # Delete merge career
        merge_file = Path("data/careers") / f"{merge_id}.json"
        merge_file.unlink()
        print(f"✅ Deleted {merge_id}")
        
        print(f"\n✅ Merge complete!")
        print(f"   Final career: {keep_id}")
        print(f"   Name: {merged_career.get('canonical_name')}")
        print(f"   Seasons: {sorted(list(merged_career.get('seasons', {}).keys()))}")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Error during merge: {e}")
        return 1


if __name__ == '__main__':
    exit(main())

