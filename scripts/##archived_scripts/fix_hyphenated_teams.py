#!/usr/bin/env python3
import json
import sys
from pathlib import Path
import argparse

def fix_match_data(match):
    """Fix match data where team names containing hyphens were incorrectly parsed."""
    fixed = False
    if not match.get('summary'):
        return fixed

    summary = match['summary']
    
    # Skip matches that never happened
    if ' vs. ' in summary or 'received a bye' in summary:
        return fixed
    
    # Only handle matches that actually happened (with "over")
    if 'over' in summary:
        parts = summary.split(' over ')
        if len(parts) != 2:
            return fixed

        # Handle winner part
        winner_part = parts[0]
        try:
            # Remove "Varsity - " or "Junior Varsity - " prefix if present
            if winner_part.startswith('Varsity - '):
                winner_part = winner_part[10:]
            elif winner_part.startswith('Junior Varsity - '):
                winner_part = winner_part[17:]
                
            # Extract wrestler and team info
            if '(' in winner_part and ')' in winner_part:
                wrestler_name = winner_part.split('(')[0].strip()
                team_name = winner_part.split('(')[1].split(')')[0].strip()
                
                # Fix if the team is null and name ends with )
                if match.get('winner_team') is None and match.get('winner_name', '').endswith(')'):
                    match['winner_name'] = wrestler_name
                    match['winner_team'] = team_name
                    fixed = True
        except IndexError:
            pass

        # Handle loser part
        loser_part = parts[1]
        try:
            # Remove "Varsity - " or "Junior Varsity - " prefix if present
            if loser_part.startswith('Varsity - '):
                loser_part = loser_part[10:]
            elif loser_part.startswith('Junior Varsity - '):
                loser_part = loser_part[17:]
                
            # Extract wrestler and team info
            if '(' in loser_part and ')' in loser_part:
                wrestler_name = loser_part.split('(')[0].strip()
                team_name = loser_part.split('(')[1].split(')')[0].strip()
                
                # Fix if the team is null and name ends with )
                if match.get('loser_team') is None and match.get('loser_name', '').endswith(')'):
                    match['loser_name'] = wrestler_name
                    match['loser_team'] = team_name
                    fixed = True
        except IndexError:
            pass

    return fixed

def process_file(file_path):
    """Process a single JSON file and fix any malformed matches."""
    matches_fixed = 0
    byes_found = 0
    vs_matches_found = 0
    hyphenated_issues_found = 0
    
    with open(file_path, 'r') as f:
        data = json.load(f)
    
    modified = False
    for wrestler in data.get('roster', []):
        for match in wrestler.get('matches', []):
            summary = match.get('summary', '')
            
            # Count different types of matches
            if 'received a bye' in summary:
                byes_found += 1
                continue
            if ' vs. ' in summary:
                vs_matches_found += 1
                continue
                
            # Check for hyphenated team issues
            if (match.get('winner_team') is None and 
                match.get('winner_name', '').endswith(')')) or (
                match.get('loser_team') is None and 
                match.get('loser_name', '').endswith(')')):
                hyphenated_issues_found += 1
                
                # Print the match details before attempting fix
                print(f"\nExamining match in {file_path}:")
                print(f"Summary: {summary}")
                print(f"Current winner: {match.get('winner_name')} ({match.get('winner_team')})")
                print(f"Current loser: {match.get('loser_name')} ({match.get('loser_team')})")
                
                # Store original values for comparison
                orig_winner_name = match.get('winner_name')
                orig_winner_team = match.get('winner_team')
                orig_loser_name = match.get('loser_name')
                orig_loser_team = match.get('loser_team')
                
                # Try to fix and check what happened
                was_fixed = fix_match_data(match)
                if was_fixed:
                    matches_fixed += 1
                    modified = True
                    print("✅ Fixed match:")
                    if orig_winner_team is None:
                        print(f"  Winner: {orig_winner_name} ({orig_winner_team}) -> {match['winner_name']} ({match['winner_team']})")
                    if orig_loser_team is None:
                        print(f"  Loser: {orig_loser_name} ({orig_loser_team}) -> {match['loser_name']} ({match['loser_team']})")
                else:
                    print("❌ Could not fix match. Debug info:")
                    if 'over' not in summary:
                        print("  - Match summary doesn't contain 'over'")
                    else:
                        parts = summary.split(' over ')
                        if len(parts) != 2:
                            print("  - Match summary doesn't split into exactly 2 parts")
                        else:
                            winner_part = parts[0].split(' - ')[-1]
                            if '(' not in winner_part or ')' not in winner_part:
                                print("  - Winner part doesn't contain properly formatted team info")
                            loser_part = parts[1]
                            if '(' not in loser_part or ')' not in loser_part:
                                print("  - Loser part doesn't contain properly formatted team info")
    
    if modified:
        # Write the fixed data back to the file
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
        
    if hyphenated_issues_found > 0:
        print(f"\nFile: {file_path}")
        print(f"Found {hyphenated_issues_found} matches with hyphenated team issues")
        print(f"Fixed {matches_fixed} matches")
        print(f"Skipped {byes_found} byes and {vs_matches_found} uncontested matches")
    
    return matches_fixed, hyphenated_issues_found

def main():
    parser = argparse.ArgumentParser(description='Fix incorrectly parsed hyphenated team names in wrestling match data')
    parser.add_argument('folder', help='Folder containing season JSON files')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be fixed without making changes')
    args = parser.parse_args()
    
    folder_path = Path(args.folder)
    if not folder_path.exists():
        print(f"Error: Folder {args.folder} does not exist")
        sys.exit(1)
    
    total_files = 0
    total_matches_fixed = 0
    total_issues_found = 0
    
    # Process all JSON files in the folder
    for file_path in folder_path.glob('*.json'):
        matches_fixed, issues_found = process_file(file_path)
        if issues_found > 0:
            total_files += 1
            total_matches_fixed += matches_fixed
            total_issues_found += issues_found
    
    print(f"\nFinal Summary:")
    print(f"Found {total_issues_found} matches with hyphenated team issues in {total_files} files")
    print(f"Successfully fixed {total_matches_fixed} matches")

if __name__ == '__main__':
    main() 