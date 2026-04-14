#!/usr/bin/env python3
"""
Find and clean duplicate career entries.

This script identifies duplicate careers (same name, same season/wrestler_id combinations)
and determines which ones are safe to delete.

Safety rules:
- Keep the career with the most seasons linked
- If tied, keep the one with links to earlier seasons (e.g., 2021)
- Never delete a career that has unique season links not in the duplicate
"""

import json
import argparse
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Set


def load_all_careers(careers_dir: Path) -> Dict[str, Dict]:
    """Load all career files."""
    careers = {}
    career_files = list(careers_dir.glob("career_*.json"))
    
    print(f"Loading {len(career_files)} career files...")
    
    for career_file in career_files:
        try:
            with open(career_file, 'r', encoding='utf-8') as f:
                career = json.load(f)
                career_id = career.get('career_id')
                if career_id:
                    careers[career_id] = career
        except Exception as e:
            print(f"Warning: Could not load {career_file}: {e}")
            continue
    
    return careers


def find_duplicate_groups(careers: Dict[str, Dict]) -> Dict[Tuple, List[Tuple[str, Dict]]]:
    """
    Find groups of duplicate careers (exact matches).
    
    Returns:
        Dictionary mapping (name_norm, season_signature) -> list of (career_id, career) tuples
    """
    duplicate_groups = defaultdict(list)
    
    for career_id, career in careers.items():
        name_norm = career.get('name_norm', '').lower().strip()
        seasons = career.get('seasons', {})
        
        # Create signature: sorted tuple of (season, wrestler_id) pairs
        season_pairs = tuple(sorted(
            (int(s), wid) for s, wid in seasons.items() 
            if s.isdigit() and wid
        ))
        
        key = (name_norm, season_pairs)
        duplicate_groups[key].append((career_id, career))
    
    # Return only groups with duplicates
    return {k: v for k, v in duplicate_groups.items() if len(v) > 1}


def find_subset_duplicates(careers: Dict[str, Dict]) -> List[Dict]:
    """
    Find subset duplicates where one career's seasons are a subset of another's.
    
    Returns:
        List of dictionaries with merge information:
        {
            'name': name,
            'superset_career_id': career_id with more seasons,
            'subset_career_id': career_id with fewer seasons,
            'superset_seasons': set of seasons in superset,
            'subset_seasons': set of seasons in subset,
            'common_seasons': set of overlapping seasons
        }
    """
    subset_duplicates = []
    
    # Group careers by normalized name
    careers_by_name = defaultdict(list)
    for career_id, career in careers.items():
        name_norm = career.get('name_norm', '').lower().strip()
        if name_norm:
            careers_by_name[name_norm].append((career_id, career))
    
    # Check each name group for subset relationships
    for name_norm, careers_list in careers_by_name.items():
        if len(careers_list) < 2:
            continue
        
        # Compare each pair
        for i, (career_id1, career1) in enumerate(careers_list):
            seasons1 = set(
                (int(s), wid) for s, wid in career1.get('seasons', {}).items()
                if s.isdigit() and wid
            )
            
            for j, (career_id2, career2) in enumerate(careers_list[i+1:], start=i+1):
                seasons2 = set(
                    (int(s), wid) for s, wid in career2.get('seasons', {}).items()
                    if s.isdigit() and wid
                )
                
                # Check if one is a subset of the other
                if seasons1.issubset(seasons2) and seasons1 != seasons2:
                    # career1 is subset, career2 is superset
                    common_seasons = seasons1
                    subset_duplicates.append({
                        'name': name_norm,
                        'superset_career_id': career_id2,
                        'subset_career_id': career_id1,
                        'superset_seasons': seasons2,
                        'subset_seasons': seasons1,
                        'common_seasons': common_seasons
                    })
                elif seasons2.issubset(seasons1) and seasons1 != seasons2:
                    # career2 is subset, career1 is superset
                    common_seasons = seasons2
                    subset_duplicates.append({
                        'name': name_norm,
                        'superset_career_id': career_id1,
                        'subset_career_id': career_id2,
                        'superset_seasons': seasons1,
                        'subset_seasons': seasons2,
                        'common_seasons': common_seasons
                    })
    
    return subset_duplicates


def analyze_duplicate_group(
    name_norm: str,
    season_pairs: Tuple,
    careers_list: List[Tuple[str, Dict]]
) -> Dict:
    """
    Analyze a duplicate group to determine which careers to keep/delete.
    
    Returns:
        Dictionary with analysis results
    """
    # Get all unique seasons across all careers in this group
    all_seasons = set()
    for _, career in careers_list:
        seasons = career.get('seasons', {})
        all_seasons.update(int(s) for s in seasons.keys() if s.isdigit())
    
    # Check if any career has additional seasons beyond the common ones
    careers_with_extras = []
    careers_without_extras = []
    
    common_seasons = set(s for s, _ in season_pairs)
    
    for career_id, career in careers_list:
        seasons = career.get('seasons', {})
        career_seasons = set(int(s) for s in seasons.keys() if s.isdigit())
        
        # Check if this career has seasons beyond the common ones
        extra_seasons = career_seasons - common_seasons
        
        if extra_seasons:
            careers_with_extras.append((career_id, career, extra_seasons))
        else:
            careers_without_extras.append((career_id, career))
    
    # Determine which to keep
    # Priority: careers with extra seasons > careers with more total seasons > lower career_id (arbitrary tiebreaker)
    
    if careers_with_extras:
        # Keep the one with the most extra seasons, or earliest extra season
        keep_career = max(careers_with_extras, key=lambda x: (len(x[2]), -min(x[2])))
        keep_id = keep_career[0]
        delete_ids = [c[0] for c in careers_list if c[0] != keep_id]
        reason = f"Has additional seasons: {sorted(keep_career[2])}"
    else:
        # All have same seasons - check if any have additional seasons beyond the signature
        # This handles cases where a duplicate was later linked to another season (e.g., 2021)
        careers_with_actual_extras = []
        for career_id, career in careers_list:
            seasons = career.get('seasons', {})
            career_seasons = set(int(s) for s in seasons.keys() if s.isdigit())
            extra = career_seasons - common_seasons
            if extra:
                careers_with_actual_extras.append((career_id, career, extra))
        
        if careers_with_actual_extras:
            # Keep the one with the most extra seasons, prioritizing earlier seasons
            keep_career = max(careers_with_actual_extras, key=lambda x: (len(x[2]), -min(x[2])))
            keep_id = keep_career[0]
            delete_ids = [c[0] for c in careers_list if c[0] != keep_id]
            reason = f"Has additional seasons beyond duplicate signature: {sorted(keep_career[2])}"
        else:
            # All have exactly the same seasons - keep the one with lowest career_id (arbitrary but consistent)
            careers_list_sorted = sorted(careers_list, key=lambda x: x[0])
            keep_id = careers_list_sorted[0][0]
            delete_ids = [c[0] for c in careers_list_sorted[1:]]
            reason = "All have same seasons, keeping lowest career_id"
    
    return {
        'name': name_norm,
        'seasons': sorted(common_seasons),
        'total_careers': len(careers_list),
        'keep_career_id': keep_id,
        'delete_career_ids': delete_ids,
        'reason': reason,
        'careers_with_extras': len(careers_with_extras),
        'all_seasons': sorted(all_seasons)
    }


def main():
    parser = argparse.ArgumentParser(
        description="Find and clean duplicate career entries"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Only report duplicates, do not delete anything'
    )
    parser.add_argument(
        '--careers-dir',
        type=Path,
        default=Path('data/careers'),
        help='Directory containing career JSON files'
    )
    parser.add_argument(
        '--filter-season',
        type=int,
        help='Only show duplicates involving a specific season (e.g., 2022)'
    )
    
    args = parser.parse_args()
    
    # Load careers
    careers = load_all_careers(args.careers_dir)
    print(f"Loaded {len(careers)} careers\n")
    
    # Find exact duplicates
    duplicate_groups = find_duplicate_groups(careers)
    print(f"Found {len(duplicate_groups)} groups of exact duplicate careers")
    
    # Find subset duplicates
    subset_duplicates = find_subset_duplicates(careers)
    print(f"Found {len(subset_duplicates)} subset duplicate pairs")
    
    # Filter by season if requested
    if args.filter_season:
        filtered = {}
        for (name_norm, season_pairs), careers_list in duplicate_groups.items():
            seasons = [s for s, _ in season_pairs]
            if args.filter_season in seasons:
                filtered[(name_norm, season_pairs)] = careers_list
        duplicate_groups = filtered
        print(f"Filtered to {len(duplicate_groups)} exact duplicate groups involving season {args.filter_season}")
        
        # Filter subset duplicates
        subset_duplicates = [
            sd for sd in subset_duplicates
            if any(args.filter_season == s for s, _ in sd['common_seasons'])
        ]
        print(f"Filtered to {len(subset_duplicates)} subset duplicate pairs involving season {args.filter_season}")
    
    if not duplicate_groups and not subset_duplicates:
        print("\nNo duplicates found!")
        return
    
    # Analyze each duplicate group
    print("\n" + "="*80)
    print("DUPLICATE ANALYSIS")
    print("="*80)
    
    all_analyses = []
    total_to_delete = 0
    total_to_merge = 0
    
    # Process exact duplicates
    for (name_norm, season_pairs), careers_list in sorted(duplicate_groups.items()):
        analysis = analyze_duplicate_group(name_norm, season_pairs, careers_list)
        analysis['type'] = 'exact'
        all_analyses.append(analysis)
        total_to_delete += len(analysis['delete_career_ids'])
    
    # Process subset duplicates
    subset_analyses = []
    for subset_dup in subset_duplicates:
        # Check if subset career is already in an exact duplicate group
        subset_id = subset_dup['subset_career_id']
        superset_id = subset_dup['superset_career_id']
        
        # Check if either is already marked for deletion in exact duplicates
        already_handled = False
        for analysis in all_analyses:
            if subset_id in analysis['delete_career_ids'] or subset_id == analysis['keep_career_id']:
                already_handled = True
                break
            if superset_id in analysis['delete_career_ids'] or superset_id == analysis['keep_career_id']:
                already_handled = True
                break
        
        if not already_handled:
            subset_analyses.append({
                'type': 'subset',
                'name': subset_dup['name'],
                'superset_career_id': superset_id,
                'subset_career_id': subset_id,
                'superset_seasons': sorted(s for s, _ in subset_dup['superset_seasons']),
                'subset_seasons': sorted(s for s, _ in subset_dup['subset_seasons']),
                'common_seasons': sorted(s for s, _ in subset_dup['common_seasons']),
                'reason': f"Subset: {sorted(s for s, _ in subset_dup['subset_seasons'])} is subset of {sorted(s for s, _ in subset_dup['superset_seasons'])}"
            })
            total_to_merge += 1
    
    all_analyses.extend(subset_analyses)
    
    # Print summary
    exact_count = sum(1 for a in all_analyses if a.get('type') == 'exact')
    subset_count = sum(1 for a in all_analyses if a.get('type') == 'subset')
    
    print(f"\nTotal duplicate groups: {len(all_analyses)}")
    print(f"  - Exact duplicates: {exact_count}")
    print(f"  - Subset duplicates: {subset_count}")
    print(f"Total careers to delete: {total_to_delete}")
    print(f"Total careers to merge: {total_to_merge}")
    print(f"Total careers to keep: {exact_count + subset_count}")
    
    # Print detailed report
    print("\n" + "="*80)
    print("DETAILED REPORT")
    print("="*80)
    
    exact_idx = 0
    subset_idx = 0
    
    for analysis in all_analyses:
        if analysis.get('type') == 'exact':
            exact_idx += 1
            i = exact_idx
            print(f"\n{i}. {analysis['name'].upper()} (EXACT DUPLICATE)")
            print(f"   Seasons: {analysis['seasons']}")
            print(f"   Duplicate careers: {analysis['total_careers']}")
            print(f"   KEEP: {analysis['keep_career_id']}")
            print(f"   DELETE: {', '.join(analysis['delete_career_ids'])}")
            print(f"   Reason: {analysis['reason']}")
            
            # Show details of each career
            for career_id in [analysis['keep_career_id']] + analysis['delete_career_ids']:
                career = careers[career_id]
                seasons = career.get('seasons', {})
                created_from = career.get('created_from_season', 'unknown')
                season_list = sorted(int(s) for s in seasons.keys() if s.isdigit())
                print(f"     {career_id}: seasons={season_list}, created_from={created_from}")
        
        elif analysis.get('type') == 'subset':
            subset_idx += 1
            i = subset_idx
            print(f"\n{i}. {analysis['name'].upper()} (SUBSET DUPLICATE)")
            print(f"   Common seasons: {analysis['common_seasons']}")
            print(f"   MERGE INTO: {analysis['superset_career_id']} (has seasons: {analysis['superset_seasons']})")
            print(f"   DELETE: {analysis['subset_career_id']} (has seasons: {analysis['subset_seasons']})")
            print(f"   Reason: {analysis['reason']}")
            
            # Show details of both careers
            for career_id in [analysis['superset_career_id'], analysis['subset_career_id']]:
                career = careers[career_id]
                seasons = career.get('seasons', {})
                created_from = career.get('created_from_season', 'unknown')
                season_list = sorted(int(s) for s in seasons.keys() if s.isdigit())
                label = "MERGE INTO" if career_id == analysis['superset_career_id'] else "DELETE"
                print(f"     {label} {career_id}: seasons={season_list}, created_from={created_from}")
    
    # Delete duplicates and merge subsets if not dry-run
    if not args.dry_run:
        print("\n" + "="*80)
        print("CLEANING DUPLICATES")
        print("="*80)
        
        deleted_count = 0
        merged_count = 0
        
        # First, handle exact duplicates (just delete)
        for analysis in all_analyses:
            if analysis.get('type') == 'exact':
                for career_id in analysis['delete_career_ids']:
                    career_file = args.careers_dir / f"{career_id}.json"
                    if career_file.exists():
                        try:
                            career_file.unlink()
                            deleted_count += 1
                            print(f"Deleted (exact duplicate): {career_id}")
                        except Exception as e:
                            print(f"Error deleting {career_id}: {e}")
        
        # Then, handle subset duplicates (merge then delete)
        for analysis in all_analyses:
            if analysis.get('type') == 'subset':
                subset_id = analysis['subset_career_id']
                superset_id = analysis['superset_career_id']
                
                # Load superset career
                superset_file = args.careers_dir / f"{superset_id}.json"
                subset_file = args.careers_dir / f"{subset_id}.json"
                
                if not superset_file.exists():
                    print(f"Warning: Superset career {superset_id} not found, skipping merge")
                    continue
                
                if not subset_file.exists():
                    print(f"Warning: Subset career {subset_id} not found, skipping merge")
                    continue
                
                try:
                    # Load both careers
                    with open(superset_file, 'r', encoding='utf-8') as f:
                        superset_career = json.load(f)
                    
                    with open(subset_file, 'r', encoding='utf-8') as f:
                        subset_career = json.load(f)
                    
                    # Merge: superset already has all seasons, so we just need to ensure
                    # the subset's seasons are in the superset (they should be, but verify)
                    superset_seasons = superset_career.get('seasons', {})
                    subset_seasons = subset_career.get('seasons', {})
                    
                    # Add any missing seasons (shouldn't happen, but be safe)
                    merged = False
                    for season, wrestler_id in subset_seasons.items():
                        if season not in superset_seasons:
                            superset_seasons[season] = wrestler_id
                            merged = True
                    
                    # Save superset career if we merged anything
                    if merged:
                        with open(superset_file, 'w', encoding='utf-8') as f:
                            json.dump(superset_career, f, indent=2, ensure_ascii=False)
                        print(f"Merged {subset_id} into {superset_id} (added missing seasons)")
                    
                    # Delete subset career
                    subset_file.unlink()
                    deleted_count += 1
                    merged_count += 1
                    print(f"Deleted (subset duplicate): {subset_id}")
                    
                except Exception as e:
                    print(f"Error merging/deleting {subset_id}: {e}")
        
        print(f"\n✓ Deleted {deleted_count} duplicate career files")
        print(f"✓ Merged {merged_count} subset duplicates")
    else:
        print("\n" + "="*80)
        print("DRY RUN - No files were deleted")
        print("Run without --dry-run to actually delete duplicates")
        print("="*80)


if __name__ == "__main__":
    main()

