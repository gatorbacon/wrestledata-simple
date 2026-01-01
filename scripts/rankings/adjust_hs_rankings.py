#!/usr/bin/env python3
"""
Adjust KY HS Boys/Girls rankings based on placement notes and records.

Rules:
1. Top 8 placers (1-8): If not in top 8, move to #8. If already in top 8, leave alone.
2. BR (Blood Round): If not in top 20, move to #15. If already in top 20, leave alone.
3. Q (Qualifier): If not in top 33, move to #25. If already in top 33, leave alone.
4. 0-0 wrestlers: Move to bottom, UNLESS they have placement notes (1-8, BR, or Q) - in which case leave them where they are.
5. 0-x wrestlers (losses but no wins): Move to bottom, just above 0-0 wrestlers, ordered by least losses to most losses.

Usage:
    python scripts/rankings/adjust_hs_rankings.py -season 2026 -gender boys
    python scripts/rankings/adjust_hs_rankings.py -season 2026 -gender girls
"""

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple


def parse_record(record_str: str) -> Tuple[int, int]:
    """Parse record string like '5-3' into (wins, losses)."""
    if not record_str:
        return (0, 0)
    match = re.match(r'(\d+)-(\d+)', record_str)
    if match:
        return (int(match.group(1)), int(match.group(2)))
    return (0, 0)


def load_placement_notes(notes_path: Path) -> Dict[str, str]:
    """Load placement notes and return wrestler_id -> note mapping."""
    if not notes_path.exists():
        return {}
    
    with open(notes_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    lookup = {}
    for entry in data.get('notes', []):
        wid = entry.get('wrestler_id')
        note = str(entry.get('note', '')).strip().upper()
        if wid and note:
            lookup[wid] = note
    
    return lookup


def load_rankings(rankings_path: Path) -> Dict:
    """Load rankings file."""
    with open(rankings_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_rankings(rankings_path: Path, data: Dict) -> None:
    """Save rankings file."""
    with open(rankings_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def adjust_rankings_for_weight_class(
    rankings_data: Dict,
    placement_notes: Dict[str, str]
) -> Dict:
    """
    Adjust rankings for a single weight class based on placement notes and records.
    
    Returns:
        Updated rankings data dictionary
    """
    rankings = rankings_data.get('rankings', [])
    if not rankings:
        return rankings_data
    
    # Separate wrestlers into categories
    regular_wrestlers = []  # Wrestlers with wins > 0, or 0-0/0-x with placement notes
    zero_zero_no_placement = []  # 0-0 wrestlers without placement notes
    zero_x_no_placement = []  # 0-x wrestlers without placement notes
    
    for entry in rankings:
        wid = entry.get('wrestler_id')
        record_str = entry.get('record', '')
        wins, losses = parse_record(record_str)
        note = placement_notes.get(wid, '')
        
        # Check if has placement note (1-8, BR, or Q)
        has_placement = note in ['1', '2', '3', '4', '5', '6', '7', '8', 'BR', 'Q']
        
        if wins == 0 and losses == 0:
            # 0-0 wrestler
            if has_placement:
                regular_wrestlers.append(entry)
            else:
                zero_zero_no_placement.append(entry)
        elif wins == 0 and losses > 0:
            # 0-x wrestler
            if has_placement:
                regular_wrestlers.append(entry)
            else:
                zero_x_no_placement.append(entry)
        else:
            # Has wins
            regular_wrestlers.append(entry)
    
    # Sort 0-x by losses (ascending)
    zero_x_no_placement.sort(key=lambda x: parse_record(x.get('record', ''))[1])
    
    # Apply placement adjustments to regular wrestlers
    # Use a sort key that preserves original order for wrestlers with same target rank
    adjusted_regular = []
    for entry in regular_wrestlers:
        wid = entry.get('wrestler_id')
        current_rank = entry.get('rank', 9999)
        note = placement_notes.get(wid, '')
        
        new_entry = entry.copy()
        
        # Rule 1: Top 8 placers - move to #8 if not already in top 8
        if note in ['1', '2', '3', '4', '5', '6', '7', '8']:
            if current_rank > 8:
                # Use a sort key: (target_rank, original_rank) to preserve order
                new_entry['_sort_key'] = (8, current_rank)
                new_entry['rank'] = 8
            else:
                new_entry['_sort_key'] = (current_rank, current_rank)
                new_entry['rank'] = current_rank
        # Rule 2: BR wrestlers - move to #15 if not already in top 20
        elif note == 'BR':
            if current_rank > 20:
                new_entry['_sort_key'] = (15, current_rank)
                new_entry['rank'] = 15
            else:
                new_entry['_sort_key'] = (current_rank, current_rank)
                new_entry['rank'] = current_rank
        # Rule 3: Q wrestlers - move to #25 if not already in top 33
        elif note == 'Q':
            if current_rank > 33:
                new_entry['_sort_key'] = (25, current_rank)
                new_entry['rank'] = 25
            else:
                new_entry['_sort_key'] = (current_rank, current_rank)
                new_entry['rank'] = current_rank
        else:
            # No placement adjustment needed, keep current rank
            new_entry['_sort_key'] = (current_rank, current_rank)
            new_entry['rank'] = current_rank
        
        adjusted_regular.append(new_entry)
    
    # Sort by sort key to group wrestlers with same target rank together
    adjusted_regular.sort(key=lambda x: x.get('_sort_key', (9999, 9999)))
    
    # Build final rankings list: regular wrestlers, then 0-x, then 0-0
    all_rankings = adjusted_regular.copy()
    
    # Rule 5: Add 0-x wrestlers (ordered by losses, ascending)
    # Assign them ranks starting after the highest regular rank
    max_regular_rank = max((e.get('rank', 0) for e in adjusted_regular), default=0)
    next_rank = max_regular_rank + 1
    
    for entry in zero_x_no_placement:
        new_entry = entry.copy()
        new_entry['rank'] = next_rank
        all_rankings.append(new_entry)
        next_rank += 1
    
    # Rule 4: Add 0-0 wrestlers at the bottom
    for entry in zero_zero_no_placement:
        new_entry = entry.copy()
        new_entry['rank'] = next_rank
        all_rankings.append(new_entry)
        next_rank += 1
    
    # Sort by rank
    all_rankings.sort(key=lambda x: x.get('rank', 9999))
    
    # Reassign ranks sequentially (in case of ties or gaps)
    # Remove temporary sort keys
    final_rankings = []
    for idx, entry in enumerate(all_rankings, start=1):
        new_entry = entry.copy()
        new_entry['rank'] = idx
        if '_sort_key' in new_entry:
            del new_entry['_sort_key']
        final_rankings.append(new_entry)
    
    rankings_data['rankings'] = final_rankings
    return rankings_data


def main():
    parser = argparse.ArgumentParser(
        description="Adjust KY HS Boys/Girls rankings based on placement notes and records."
    )
    parser.add_argument(
        '-season',
        type=int,
        required=True,
        help='Season year (e.g., 2026)'
    )
    parser.add_argument(
        '-gender',
        type=str,
        required=True,
        choices=['boys', 'girls'],
        help='Gender: boys or girls'
    )
    parser.add_argument(
        '-dry-run',
        action='store_true',
        help='Show what would be changed without saving'
    )
    
    args = parser.parse_args()
    
    # Setup paths
    data_dir = Path(f"mt/rankings_data/hs_ky_{args.gender}")
    notes_path = data_dir / "placement_notes.json"
    
    if not data_dir.exists():
        print(f"Error: Data directory not found: {data_dir}")
        return
    
    # Load placement notes
    placement_notes = load_placement_notes(notes_path)
    print(f"Loaded {len(placement_notes)} placement notes")
    
    # Find all rankings files
    rankings_files = sorted(data_dir.glob("rankings_*.json"))
    
    if not rankings_files:
        print(f"No rankings files found in {data_dir}")
        return
    
    print(f"Found {len(rankings_files)} weight classes to process\n")
    
    total_adjusted = 0
    
    for rankings_file in rankings_files:
        weight_class = rankings_file.stem.replace('rankings_', '')
        print(f"Processing {weight_class}...")
        
        # Load rankings
        rankings_data = load_rankings(rankings_file)
        original_rankings = rankings_data.get('rankings', [])
        
        if not original_rankings:
            print(f"  No rankings found, skipping\n")
            continue
        
        # Adjust rankings
        adjusted_data = adjust_rankings_for_weight_class(rankings_data.copy(), placement_notes)
        adjusted_rankings = adjusted_data.get('rankings', [])
        
        # Build lookup by wrestler_id for comparison
        orig_lookup = {e.get('wrestler_id'): e for e in original_rankings}
        adj_lookup = {e.get('wrestler_id'): e for e in adjusted_rankings}
        
        # Count changes - compare by wrestler_id, not position
        changes = []
        for wid in orig_lookup.keys():
            if wid not in adj_lookup:
                continue
            orig_entry = orig_lookup[wid]
            adj_entry = adj_lookup[wid]
            orig_rank = orig_entry.get('rank')
            adj_rank = adj_entry.get('rank')
            if orig_rank != adj_rank:
                changes.append({
                    'name': adj_entry.get('name'),
                    'team': adj_entry.get('team'),
                    'from': orig_rank,
                    'to': adj_rank,
                    'record': adj_entry.get('record'),
                    'note': placement_notes.get(wid, '')
                })
        
        if changes:
            print(f"  Adjusted {len(changes)} wrestler(s):")
            for change in changes[:10]:  # Show first 10 changes
                note_str = f" [{change['note']}]" if change['note'] else ""
                print(f"    {change['name']} ({change['team']}): {change['from']} → {change['to']} {change['record']}{note_str}")
            if len(changes) > 10:
                print(f"    ... and {len(changes) - 10} more")
            total_adjusted += len(changes)
            
            if not args.dry_run:
                save_rankings(rankings_file, adjusted_data)
                print(f"  ✓ Saved updated rankings")
        else:
            print(f"  No changes needed")
        
        print()
    
    if args.dry_run:
        print(f"\nDRY RUN: Would adjust {total_adjusted} wrestler(s) across all weight classes")
        print("Run without -dry-run to apply changes")
    else:
        print(f"\n✓ Complete: Adjusted {total_adjusted} wrestler(s) across all weight classes")


if __name__ == '__main__':
    main()

