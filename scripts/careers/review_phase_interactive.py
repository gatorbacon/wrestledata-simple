#!/usr/bin/env python3
"""
Interactive review tool for career linking phases.

Shows side-by-side comparison of 2024 wrestler vs career (2025) wrestler
and allows approving/rejecting links one at a time.
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional

_CAREERS_DIR = None  # overridden in main() based on --gender


def load_season_accomplishments(season: int, gender: str) -> Dict[str, Dict]:
    """Load season accomplishments and create lookup by season_wrestler_id."""
    file_path = Path(f"data/season_accomplishments/{gender}/{season}/season_accomplishments.json")
    
    if not file_path.exists():
        raise FileNotFoundError(f"Season accomplishments file not found: {file_path}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Create lookup by season_wrestler_id
    lookup = {}
    for wrestler in data.get('wrestlers', []):
        wrestler_id = wrestler.get('season_wrestler_id')
        if wrestler_id:
            lookup[wrestler_id] = wrestler
    
    return lookup


def load_career(career_id: str) -> Optional[Dict]:
    """Load a single career file."""
    career_file = _CAREERS_DIR / f"{career_id}.json"
    if not career_file.exists():
        return None
    
    with open(career_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def format_wrestler_info(wrestler: Dict, label: str) -> str:
    """Format wrestler info for display."""
    name = wrestler.get('name', 'Unknown')
    team = wrestler.get('team', 'Unknown')
    weight = wrestler.get('final_weight', '?')
    grade = wrestler.get('grade', '?')
    record = wrestler.get('record', {})
    wins = record.get('wins', 0) if record else 0
    losses = record.get('losses', 0) if record else 0
    
    return f"""
{label}:
  Name:     {name}
  Team:     {team}
  Weight:   {weight}
  Grade:    {grade}
  Record:   {wins}-{losses}
"""


def print_comparison(wrestler_2024: Dict, career: Dict, wrestler_2025: Optional[Dict], index: int, total: int):
    """Print compact side-by-side comparison."""
    print("\n" + "="*80)
    print(f"COMPARISON {index}/{total}")
    print("="*80)
    
    # Get data
    name_2024 = wrestler_2024.get('name', 'Unknown')
    team_2024 = wrestler_2024.get('team', 'Unknown')
    weight_2024 = wrestler_2024.get('final_weight', '?')
    grade_2024 = wrestler_2024.get('grade', '?')
    record_2024 = wrestler_2024.get('record', {})
    wins_2024 = record_2024.get('wins', 0) if record_2024 else 0
    losses_2024 = record_2024.get('losses', 0) if record_2024 else 0
    
    name_2025 = career.get('canonical_name', 'Unknown')
    team_2025 = 'Unknown'
    weight_2025 = '?'
    grade_2025 = '?'
    wins_2025 = 0
    losses_2025 = 0
    
    if wrestler_2025:
        team_2025 = wrestler_2025.get('team', 'Unknown')
        weight_2025 = wrestler_2025.get('final_weight', '?')
        grade_2025 = wrestler_2025.get('grade', '?')
        record_2025 = wrestler_2025.get('record', {})
        wins_2025 = record_2025.get('wins', 0) if record_2025 else 0
        losses_2025 = record_2025.get('losses', 0) if record_2025 else 0
    
    # Compact format - side by side
    print(f"\nCareer (2025): {name_2025} / {team_2025} / Grade {grade_2025} / {weight_2025} lbs / {wins_2025}-{losses_2025}")
    print(f"2024:          {name_2024} / {team_2024} / Grade {grade_2024} / {weight_2024} lbs / {wins_2024}-{losses_2024}")
    
    # Check for matches
    name_match = name_2024.lower().strip() == name_2025.lower().strip()
    team_match = team_2024.lower().strip() == team_2025.lower().strip()
    grade_progression = False
    if grade_2024 != '?' and grade_2025 != '?':
        grade_progression = (grade_2024 + 1 == grade_2025)
    
    # Match indicators
    print(f"\nMatch: Name={'✅' if name_match else '❌'}  Team={'✅' if team_match else '❌'}  Grade={'✅' if grade_progression else '❌'}")
    print(f"Career ID: {career.get('career_id', 'Unknown')}")
    print("="*80)


def check_if_already_linked(wrestler_2024_id: str, career_id: str) -> bool:
    """Check if a wrestler is already linked to a career."""
    career = load_career(career_id)
    if not career:
        return False
    
    seasons = career.get('seasons', {})
    return seasons.get('2024') == wrestler_2024_id


def review_phase_interactive(phase_file: Path, season: int, gender: str):
    """Interactive review of a phase file."""
    # Load phase data
    with open(phase_file, 'r', encoding='utf-8') as f:
        phase_data = json.load(f)
    
    links = phase_data.get('links', [])
    if not links:
        print(f"No links found in {phase_file}")
        return [], []
    
    print(f"\n{'='*70}")
    print(f"REVIEWING: {phase_data.get('phase', 'Unknown Phase')}")
    print(f"Total links in file: {len(links)}")
    
    # Filter out already-linked wrestlers
    print("\nChecking for already-linked wrestlers...")
    links_to_review = []
    already_linked_count = 0
    
    for link in links:
        wrestler_2024_id = link['wrestler_2024']['season_wrestler_id']
        career_id = link['career_id']
        
        if check_if_already_linked(wrestler_2024_id, career_id):
            already_linked_count += 1
        else:
            links_to_review.append(link)
    
    print(f"Already linked: {already_linked_count}")
    print(f"Needs review: {len(links_to_review)}")
    print(f"{'='*70}")
    
    if not links_to_review:
        print("\n✅ All links in this file are already applied!")
        return [], []
    
    # Load lookups
    print("\nLoading data...")
    wrestler_lookup_2024 = load_season_accomplishments(2024, gender)
    wrestler_lookup_2025 = load_season_accomplishments(2025, gender)
    print("✅ Data loaded")
    
    # Track approvals/rejections
    approved = []
    rejected = []
    
    # Review each link
    for i, link in enumerate(links_to_review, 1):
        wrestler_2024_id = link['wrestler_2024']['season_wrestler_id']
        career_id = link['career_id']
        
        # Get wrestler data
        wrestler_2024 = wrestler_lookup_2024.get(wrestler_2024_id)
        if not wrestler_2024:
            print(f"\n⚠️  Warning: Could not find 2024 wrestler {wrestler_2024_id}")
            rejected.append(link)
            continue
        
        # Get career
        career = load_career(career_id)
        if not career:
            print(f"\n⚠️  Warning: Could not find career {career_id}")
            rejected.append(link)
            continue
        
        # Get 2025 wrestler from career
        wrestler_2025_id = career.get('seasons', {}).get('2025')
        wrestler_2025 = wrestler_lookup_2025.get(wrestler_2025_id) if wrestler_2025_id else None
        
        # Show comparison
        print_comparison(wrestler_2024, career, wrestler_2025, i, len(links_to_review))
        
        # Get user decision
        while True:
            print("\nOptions:")
            print("  [a]pprove - Link this wrestler to this career")
            print("  [r]eject  - Skip this link")
            print("  [s]kip    - Skip for now, review later")
            print("  [q]uit    - Save progress and exit")
            print("  [A]pprove all remaining - Approve all remaining links")
            
            response = input("\n> ").strip()
            response_lower = response.lower()
            
            # Check for "approve all" first (before single character checks)
            if response == 'A' or response_lower in ['approve all', 'approveall', 'approve-all']:
                # Approve all remaining
                remaining = links_to_review[i-1:]
                approved.extend(remaining)
                print(f"✅ Approved all {len(remaining)} remaining links")
                # Break out of while loop AND for loop - we're done
                break
            elif response_lower in ['a', 'approve']:
                approved.append(link)
                print("✅ Approved")
                break
            elif response_lower in ['r', 'reject']:
                rejected.append(link)
                print("❌ Rejected")
                break
            elif response_lower in ['s', 'skip']:
                print("⏭️  Skipped")
                break
            elif response_lower in ['q', 'quit']:
                print("\n💾 Saving progress...")
                # Save approved/rejected so far
                remaining = links_to_review[i-1:]
                save_review_results(phase_file, approved, rejected, remaining)
                print(f"✅ Saved: {len(approved)} approved, {len(rejected)} rejected, {len(remaining)} remaining")
                return approved, rejected
            else:
                print(f"Invalid option: '{response}'. Please try again.")
        
        # Show progress
        print(f"\nProgress: {i}/{len(links_to_review)} | Approved: {len(approved)} | Rejected: {len(rejected)}")
        
        # If we approved all, break out of the for loop
        if response == 'A' or response_lower in ['approve all', 'approveall', 'approve-all']:
            break
    
    # Final summary
    print(f"\n{'='*70}")
    print("REVIEW COMPLETE")
    print(f"{'='*70}")
    print(f"Total reviewed: {len(links_to_review)}")
    print(f"Approved: {len(approved)}")
    print(f"Rejected: {len(rejected)}")
    print(f"Skipped: {len(links_to_review) - len(approved) - len(rejected)}")
    
    # Save results
    save_review_results(phase_file, approved, rejected, [])
    
    return approved, rejected


def save_review_results(phase_file: Path, approved: List[Dict], rejected: List[Dict], remaining: List[Dict]):
    """Save review results to separate files."""
    log_dir = phase_file.parent
    
    # Save approved
    approved_file = log_dir / f"{phase_file.stem}_approved.json"
    with open(approved_file, 'w', encoding='utf-8') as f:
        json.dump({
            'phase': phase_file.stem,
            'approved': approved
        }, f, indent=2, ensure_ascii=False)
    
    # Save rejected
    rejected_file = log_dir / f"{phase_file.stem}_rejected.json"
    with open(rejected_file, 'w', encoding='utf-8') as f:
        json.dump({
            'phase': phase_file.stem,
            'rejected': rejected
        }, f, indent=2, ensure_ascii=False)
    
    # Save remaining (if any)
    if remaining:
        remaining_file = log_dir / f"{phase_file.stem}_remaining.json"
        with open(remaining_file, 'w', encoding='utf-8') as f:
            json.dump({
                'phase': phase_file.stem,
                'remaining': remaining
            }, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Saved results:")
    print(f"   Approved: {approved_file}")
    print(f"   Rejected: {rejected_file}")
    if remaining:
        print(f"   Remaining: {remaining_file}")


def apply_approved_links(approved_file: Path):
    """Apply approved links from review."""
    try:
        with open(approved_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Error loading approved file: {e}")
        return 0
    
    approved = data.get('approved', [])
    if not approved:
        print("No approved links to apply")
        return 0
    
    print(f"\nLoaded {len(approved)} approved links from file")
    
    # Filter out already-linked wrestlers
    print("Checking for already-linked wrestlers...")
    links_to_apply = []
    already_linked_count = 0
    
    for link in approved:
        wrestler_2024_id = link['wrestler_2024']['season_wrestler_id']
        career_id = link['career_id']
        
        if check_if_already_linked(wrestler_2024_id, career_id):
            already_linked_count += 1
        else:
            links_to_apply.append(link)
    
    print(f"Already linked: {already_linked_count}")
    print(f"Will apply: {len(links_to_apply)}")
    
    if not links_to_apply:
        print("\n✅ All approved links are already applied!")
        return 0
    
    print(f"\nApplying {len(links_to_apply)} approved links...")
    
    # Import from the main linking script
    try:
        import sys
        import importlib.util
        link_script_path = Path(__file__).parent / "link_season_to_careers.py"
        if not link_script_path.exists():
            print(f"❌ Error: Could not find link_season_to_careers.py at {link_script_path}")
            return 0
        
        spec = importlib.util.spec_from_file_location("link_season_to_careers", link_script_path)
        link_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(link_module)
        
        careers = link_module.load_careers(_CAREERS_DIR)
        applied = link_module.apply_links_phase(links_to_apply, careers, "Approved Links")
        
        print(f"\n✅ Applied {applied} links")
        if already_linked_count > 0:
            print(f"ℹ️  Skipped {already_linked_count} already-linked wrestlers")
        return applied
    except Exception as e:
        print(f"❌ Error applying links: {e}")
        import traceback
        traceback.print_exc()
        return 0


def main():
    parser = argparse.ArgumentParser(
        description='Interactive review of career linking phases'
    )
    parser.add_argument(
        '--phase-file',
        type=str,
        required=True,
        help='Path to phase JSON file (e.g., 2024_phase1_rule_a.json)'
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
    parser.add_argument(
        '--apply-approved',
        action='store_true',
        help='Apply approved links from review (use approved file)'
    )
    
    args = parser.parse_args()

    global _CAREERS_DIR
    _CAREERS_DIR = Path("data/careers") if args.gender == "boys" else Path("data/careers/girls")

    phase_file = Path(args.phase_file)
    if not phase_file.exists():
        # Try in default location
        phase_file = Path("data/career_linking_logs") / args.phase_file
        if not phase_file.exists():
            print(f"❌ Error: Phase file not found: {args.phase_file}")
            return 1
    
    if args.apply_approved:
        # Apply approved links
        approved_file = phase_file.parent / f"{phase_file.stem}_approved.json"
        if not approved_file.exists():
            print(f"❌ Error: Approved file not found: {approved_file}")
            return 1
        apply_approved_links(approved_file)
        return 0
    
    # Interactive review
    approved, rejected = review_phase_interactive(phase_file, args.season, args.gender)
    
    if approved:
        print(f"\n💡 To apply approved links, run:")
        print(f"   python3 scripts/careers/review_phase_interactive.py --phase-file {phase_file.name} --gender {args.gender} --apply-approved")
    
    return 0


if __name__ == '__main__':
    exit(main())

