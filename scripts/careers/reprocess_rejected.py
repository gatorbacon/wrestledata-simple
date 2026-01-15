#!/usr/bin/env python3
"""
Re-process rejected links from a phase.

For wrestlers that were rejected from linking to a specific career,
re-run the analysis excluding that career, allowing them to either:
1. Match to a different career (if a better match exists)
2. Be auto-created as a new career (if no match found)
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Set
import sys
import importlib.util


def load_rejected_links(rejected_file: Path) -> List[Dict]:
    """Load rejected links from review."""
    with open(rejected_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('rejected', [])


def reprocess_rejected_wrestlers(
    rejected_file: Path,
    season: int,
    gender: str
):
    """Re-process rejected wrestlers, excluding their rejected careers."""
    print(f"\n{'='*70}")
    print("RE-PROCESSING REJECTED WRESTLERS")
    print(f"{'='*70}")
    
    # Load rejected links
    rejected_links = load_rejected_links(rejected_file)
    if not rejected_links:
        print("No rejected links found")
        return
    
    print(f"Found {len(rejected_links)} rejected links")
    
    # Extract wrestler IDs and their rejected career IDs
    rejected_wrestlers = {}
    for link in rejected_links:
        wrestler_id = link['wrestler_2024']['season_wrestler_id']
        rejected_career_id = link['career_id']
        
        if wrestler_id not in rejected_wrestlers:
            rejected_wrestlers[wrestler_id] = {
                'wrestler_2024': link['wrestler_2024'],
                'rejected_careers': set()
            }
        rejected_wrestlers[wrestler_id]['rejected_careers'].add(rejected_career_id)
    
    print(f"Unique rejected wrestlers: {len(rejected_wrestlers)}")
    
    # Import the linking script functions
    link_script_path = Path(__file__).parent / "link_season_to_careers.py"
    spec = importlib.util.spec_from_file_location("link_season_to_careers", link_script_path)
    link_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(link_module)
    
    # Load data
    print("\nLoading data...")
    careers = link_module.load_careers(Path("data/careers"))
    season_accomplishments = {
        2024: link_module.load_season_accomplishments(2024, gender),
        2025: link_module.load_season_accomplishments(2025, gender)
    }
    aliases = link_module.load_name_aliases()
    
    # Build lookups
    print("Building lookups...")
    name_to_careers = {}
    for career_id, career in careers.items():
        name_norm = career.get('name_norm', '')
        if name_norm:
            if name_norm not in name_to_careers:
                name_to_careers[name_norm] = []
            name_to_careers[name_norm].append(career_id)
    
    wrestler_lookup_2024 = {w.get('season_wrestler_id'): w for w in season_accomplishments[2024]}
    wrestler_lookup_2025 = {w.get('season_wrestler_id'): w for w in season_accomplishments[2025]}
    
    career_teams_cache = {}
    for career_id, career in careers.items():
        career_teams_cache[career_id] = link_module.get_career_teams(career, {
            2024: season_accomplishments[2024],
            2025: season_accomplishments[2025]
        })
    
    # Process each rejected wrestler
    results = {
        'matched_to_different_career': [],
        'auto_created': [],
        'still_no_match': []
    }
    
    print(f"\nProcessing {len(rejected_wrestlers)} rejected wrestlers...")
    
    for wrestler_id, info in rejected_wrestlers.items():
        wrestler_2024 = wrestler_lookup_2024.get(wrestler_id)
        if not wrestler_2024:
            results['still_no_match'].append({
                'wrestler_2024': info['wrestler_2024'],
                'reason': 'wrestler_not_found'
            })
            continue
        
        rejected_career_ids = info['rejected_careers']
        
        # Find candidate careers (excluding rejected ones)
        name_2024_norm = link_module.apply_name_alias(wrestler_2024.get('name', ''), aliases)
        
        candidate_career_ids = set()
        if name_2024_norm in name_to_careers:
            candidate_career_ids.update(name_to_careers[name_2024_norm])
        
        # Remove rejected careers
        candidate_career_ids = candidate_career_ids - rejected_career_ids
        
        # Also check last name matches
        name_parts = name_2024_norm.split()
        if len(name_parts) > 0:
            last_name = name_parts[-1]
            for name_norm, career_ids in name_to_careers.items():
                if name_norm.split()[-1] == last_name if name_norm.split() else False:
                    candidate_career_ids.update(career_ids)
        
        # Remove rejected careers again
        candidate_career_ids = candidate_career_ids - rejected_career_ids
        
        # Limit candidates
        if len(candidate_career_ids) > 50:
            candidate_career_ids = set(name_to_careers.get(name_2024_norm, [])) - rejected_career_ids
        
        # Find best match from remaining candidates
        best_match = None
        best_score = 0
        
        for career_id in candidate_career_ids:
            career = careers.get(career_id)
            if not career:
                continue
            
            # Skip if already has 2024 season
            if '2024' in link_module.get_career_seasons(career):
                continue
            
            # Only consider careers active within ±3 years
            career_seasons = link_module.get_career_seasons(career)
            if career_seasons:
                min_season = min(career_seasons)
                max_season = max(career_seasons)
                if min_season > 2027 or max_season < 2021:
                    continue
            
            # Get 2025 wrestler
            wrestler_2025_id = career.get('seasons', {}).get('2025')
            wrestler_2025 = wrestler_lookup_2025.get(wrestler_2025_id) if wrestler_2025_id else None
            
            # Calculate confidence score
            score, reasons = link_module.calculate_confidence_score_optimized(
                wrestler_2024,
                career,
                wrestler_2025,
                career_teams_cache.get(career_id, set())
            )
            
            if score > best_score:
                best_score = score
                best_match = (career_id, career, score, reasons)
        
        # Decide what to do
        if best_match and best_score >= 50:
            # Found a match with decent confidence
            career_id, career, score, reasons = best_match
            results['matched_to_different_career'].append({
                'wrestler_2024': {
                    'name': wrestler_2024.get('name'),
                    'season_wrestler_id': wrestler_id,
                    'team': wrestler_2024.get('team'),
                    'grade': wrestler_2024.get('grade')
                },
                'career_id': career_id,
                'confidence': score,
                'reasons': reasons,
                'rejected_careers': list(rejected_career_ids)
            })
        else:
            # No good match found - create new career
            results['auto_created'].append({
                'wrestler_2024': {
                    'name': wrestler_2024.get('name'),
                    'season_wrestler_id': wrestler_id,
                    'team': wrestler_2024.get('team'),
                    'grade': wrestler_2024.get('grade')
                },
                'reason': 'no_good_match_after_rejection',
                'rejected_careers': list(rejected_career_ids),
                'best_score_found': best_score if best_match else 0
            })
    
    # Print summary
    print(f"\n{'='*70}")
    print("RE-PROCESSING SUMMARY")
    print(f"{'='*70}")
    print(f"Matched to different career: {len(results['matched_to_different_career'])}")
    print(f"Auto-created (new career): {len(results['auto_created'])}")
    print(f"Still no match: {len(results['still_no_match'])}")
    
    # Save results
    log_dir = rejected_file.parent
    output_file = log_dir / f"{rejected_file.stem}_reprocessed.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'season': season,
            'gender': gender,
            'source': str(rejected_file),
            'results': results
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Saved results to: {output_file}")
    
    # Show matches that need review
    if results['matched_to_different_career']:
        print(f"\n⚠️  Found {len(results['matched_to_different_career'])} matches to different careers")
        print("   Review these before applying:")
        for match in results['matched_to_different_career'][:5]:
            print(f"   - {match['wrestler_2024']['name']} → {match['career_id']} (confidence: {match['confidence']})")
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description='Re-process rejected links to find alternative matches or create new careers'
    )
    parser.add_argument(
        '--rejected-file',
        type=str,
        required=True,
        help='Path to rejected links file (e.g., 2024_phase3_high_confidence_rejected.json)'
    )
    parser.add_argument(
        '--season',
        type=int,
        default=2024,
        help='Season being linked (default: 2024)'
    )
    parser.add_argument(
        '--gender',
        type=str,
        required=True,
        choices=['boys', 'girls'],
        help='Gender (boys or girls)'
    )
    
    args = parser.parse_args()
    
    rejected_file = Path(args.rejected_file)
    if not rejected_file.exists():
        # Try in default location
        rejected_file = Path("data/career_linking_logs") / args.rejected_file
        if not rejected_file.exists():
            print(f"❌ Error: Rejected file not found: {args.rejected_file}")
            return 1
    
    reprocess_rejected_wrestlers(rejected_file, args.season, args.gender)
    
    return 0


if __name__ == '__main__':
    exit(main())

