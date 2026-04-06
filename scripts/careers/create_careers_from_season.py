#!/usr/bin/env python3
"""
Create careers from season accomplishments (backend-only, authoritative data layer).

NEW SCHEMA: Careers contain ONLY identity and links to season accomplishments.
No embedded stats, records, or season data.

Output: data/careers/{career_id}.json
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Set


def normalize_name(name: str) -> str:
    """
    Normalize a wrestler's name for matching.
    
    Normalization:
    1. Convert to lowercase
    2. Remove extra whitespace
    3. Strip punctuation (optional, but common in matching)
    
    Args:
        name: Full name string
        
    Returns:
        Normalized name string
    """
    if not name:
        return ""
    
    # Basic normalization: lowercase and strip whitespace
    normalized = name.lower().strip()
    
    # Collapse multiple spaces into single space
    import re
    normalized = re.sub(r'\s+', ' ', normalized)
    
    return normalized


def generate_career_id(counter: int) -> str:
    """
    Generate a stable, opaque career ID.
    
    Format: career_000001, career_000002, etc.
    
    Args:
        counter: Monotonic counter (1-indexed)
        
    Returns:
        Career ID string
    """
    return f"career_{counter:06d}"


def create_career_from_wrestler(
    wrestler: Dict,
    career_id: str,
    anchor_season: int
) -> Dict:
    """
    Create a career record from a wrestler's season accomplishment.
    
    NEW SCHEMA: Only identity and links, no embedded stats.
    
    Args:
        wrestler: Wrestler record from season accomplishments
        career_id: Generated career ID
        anchor_season: Season used as anchor (e.g., 2025)
        
    Returns:
        Career dictionary with minimal schema
    """
    canonical_name = wrestler.get('name', '')
    season_wrestler_id = wrestler.get('season_wrestler_id')
    name_norm = normalize_name(canonical_name)
    
    # Create career record (minimal schema)
    career = {
        'career_id': career_id,
        'canonical_name': canonical_name,
        'name_norm': name_norm,
        'created_from_season': anchor_season,
        'seasons': {
            str(anchor_season): season_wrestler_id
        },
        'notes': None
    }
    
    return career


def load_season_accomplishments(season: int, gender: str) -> Dict:
    """
    Load season accomplishments file.
    
    Args:
        season: Season year
        gender: Gender ('boys' or 'girls')
        
    Returns:
        Season accomplishments dictionary
        
    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file is empty or invalid
    """
    file_path = Path(f"data/season_accomplishments/{gender}/{season}/season_accomplishments.json")
    
    if not file_path.exists():
        raise FileNotFoundError(f"Season accomplishments file not found: {file_path}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if not data.get('wrestlers'):
        raise ValueError(f"Season accomplishments file is empty or has no wrestlers: {file_path}")
    
    return data


def create_careers(season: int, gender: str, anchor_season: int = 2025) -> int:
    """
    Create careers from season accomplishments.
    
    NEW SCHEMA: Careers contain only identity and links.
    
    Args:
        season: Season year to use as anchor
        gender: Gender ('boys' or 'girls')
        anchor_season: Season used as anchor (default 2025)
        
    Returns:
        Number of careers created
        
    Raises:
        FileNotFoundError: If input file missing
        ValueError: If duplicate careers would be created
    """
    # Load season accomplishments
    print(f"Loading season accomplishments for {season} ({gender})...")
    accomplishments = load_season_accomplishments(season, gender)
    
    wrestlers = accomplishments.get('wrestlers', [])
    print(f"Found {len(wrestlers)} wrestlers")
    
    # Setup output directory
    output_dir = Path("data/careers") if gender == "boys" else Path("data/careers/girls")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Check for existing careers and build lookup
    existing_career_ids: Set[str] = set()
    existing_season_ids: Set[str] = set()  # Lookup: season_wrestler_id -> exists
    existing_files = list(output_dir.glob("career_*.json"))
    
    if existing_files:
        print(f"Found {len(existing_files)} existing career files")
        print("Building lookup index...")
        for career_file in existing_files:
            try:
                with open(career_file, 'r') as f:
                    career_data = json.load(f)
                    career_id = career_data.get('career_id')
                    if career_id:
                        existing_career_ids.add(career_id)
                    # Build lookup for season_wrestler_ids from seasons dict
                    seasons = career_data.get('seasons', {})
                    if isinstance(seasons, dict):
                        for season_id in seasons.values():
                            if season_id:
                                existing_season_ids.add(season_id)
            except Exception as e:
                print(f"⚠️  Warning: Could not read existing career file {career_file}: {e}")
        print(f"Indexed {len(existing_season_ids)} existing season_wrestler_ids")
    
    # Track seen season_wrestler_ids to detect duplicates
    seen_season_ids: Set[str] = set()
    careers_created = 0
    careers_skipped = 0
    errors = []
    
    # Generate careers
    career_counter = len(existing_career_ids)  # Start counter after existing careers
    
    for wrestler in wrestlers:
        # Validate required fields
        season_wrestler_id = wrestler.get('season_wrestler_id')
        name = wrestler.get('name')
        
        if not season_wrestler_id:
            errors.append(f"Wrestler missing season_wrestler_id: {name}")
            continue
        
        if not name:
            errors.append(f"Wrestler missing name: {season_wrestler_id}")
            continue
        
        # Check for duplicates in current batch
        if season_wrestler_id in seen_season_ids:
            errors.append(f"Duplicate season_wrestler_id: {season_wrestler_id} ({name})")
            continue
        
        seen_season_ids.add(season_wrestler_id)
        
        # Check if career already exists for this season_wrestler_id (fast lookup)
        if season_wrestler_id in existing_season_ids:
            careers_skipped += 1
            continue
        
        # Generate career ID
        career_counter += 1
        career_id = generate_career_id(career_counter)
        
        # Check for ID collision
        if career_id in existing_career_ids:
            raise ValueError(f"Career ID collision: {career_id} already exists")
        
        # Create career (minimal schema)
        career = create_career_from_wrestler(wrestler, career_id, anchor_season)
        
        # Save career file
        career_file = output_dir / f"{career_id}.json"
        with open(career_file, 'w', encoding='utf-8') as f:
            json.dump(career, f, indent=2, ensure_ascii=False)
        
        existing_career_ids.add(career_id)
        existing_season_ids.add(season_wrestler_id)
        careers_created += 1
    
    # Print summary
    print(f"\n{'='*60}")
    print("CAREER CREATION SUMMARY")
    print(f"{'='*60}")
    print(f"Gender: {gender}")
    print(f"Anchor Season: {anchor_season}")
    print(f"Total wrestlers processed: {len(wrestlers)}")
    print(f"Careers created: {careers_created}")
    print(f"Careers skipped (already exist): {careers_skipped}")
    
    if errors:
        print(f"\n⚠️  Errors/Warnings ({len(errors)}):")
        for error in errors[:10]:  # Show first 10
            print(f"  - {error}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more")
    
    return careers_created


def main():
    parser = argparse.ArgumentParser(
        description='Create careers from season accomplishments (backend-only, identity + links only)'
    )
    parser.add_argument(
        '--season',
        type=int,
        default=2025,
        help='Anchor season year (default: 2025)'
    )
    parser.add_argument(
        '--gender',
        type=str,
        required=True,
        choices=['boys', 'girls'],
        help='Gender (boys or girls)'
    )
    
    args = parser.parse_args()
    
    print(f"\n{'='*60}")
    print("CAREER CREATION FROM SEASON ACCOMPLISHMENTS")
    print("NEW SCHEMA: Identity + Links Only")
    print(f"{'='*60}")
    print(f"Anchor Season: {args.season}")
    print(f"Gender: {args.gender}")
    print(f"{'='*60}\n")
    
    try:
        careers_created = create_careers(args.season, args.gender, anchor_season=args.season)
        
        if careers_created > 0:
            print(f"\n✅ Successfully created {careers_created} careers")
            print(f"   Output directory: {Path('data/careers') if args.gender == 'boys' else Path('data/careers/girls')}")
        else:
            print("\n⚠️  No new careers created (all already exist)")
        
        return 0
        
    except FileNotFoundError as e:
        print(f"\n❌ Error: {e}")
        return 1
    except ValueError as e:
        print(f"\n❌ Error: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit(main())
