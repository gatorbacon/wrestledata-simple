#!/usr/bin/env python3
"""
Script to fix Martin(Josh) Martinez matches where the name and team are incorrectly parsed.
"""

import json
import re
from pathlib import Path

def fix_martinez_matches(folder_path: str = 'data/2014') -> None:
    """
    Fix matches involving Martin(Josh) Martinez where the name and team are incorrectly parsed.
    
    The script will:
    1. Find matches where winner_name is "Martin" and winner_team is "Josh"
    2. Find matches where loser_name is "Martin" and loser_team is "Josh"
    3. Update these matches to use the correct name "Martin(Josh) Martinez" and team "Air Force"
    4. Update the match summary if needed
    """
    print(f"\nSearching for Martin(Josh) Martinez matches in {folder_path}...")
    
    # Track statistics
    files_checked = 0
    files_modified = 0
    matches_fixed = 0
    
    # Process all JSON files in the folder
    for file_path in Path(folder_path).glob('*.json'):
        files_checked += 1
        file_modified = False
        
        try:
            # Read the file
            with open(file_path) as f:
                team_data = json.load(f)
            
            # Process each wrestler's matches
            for wrestler in team_data.get('roster', []):
                for match in wrestler.get('matches', []):
                    needs_update = False
                    
                    # Check winner side
                    if match.get('winner_name') == 'Martin' and match.get('winner_team') == 'Josh':
                        match['winner_name'] = 'Martin(Josh) Martinez'
                        match['winner_team'] = 'Air Force'
                        needs_update = True
                    
                    # Check loser side
                    if match.get('loser_name') == 'Martin' and match.get('loser_team') == 'Josh':
                        match['loser_name'] = 'Martin(Josh) Martinez'
                        match['loser_team'] = 'Air Force'
                        needs_update = True
                    
                    # Update summary if needed
                    if needs_update and 'summary' in match:
                        # Replace "Martin(Josh)" with "Martin(Josh) Martinez" in summary
                        old_summary = match['summary']
                        new_summary = old_summary.replace('Martin(Josh)', 'Martin(Josh) Martinez')
                        
                        # Also ensure team is correctly shown as (Air Force)
                        new_summary = re.sub(r'\(Josh\)', '(Air Force)', new_summary)
                        
                        match['summary'] = new_summary
                        
                        print(f"\nFixed match in {file_path}:")
                        print(f"Old summary: {old_summary}")
                        print(f"New summary: {new_summary}")
                        
                        matches_fixed += 1
                        file_modified = True
            
            # Save changes if file was modified
            if file_modified:
                files_modified += 1
                with open(file_path, 'w') as f:
                    json.dump(team_data, f, indent=2)
        
        except Exception as e:
            print(f"Error processing {file_path}: {e}")
    
    # Print summary
    print(f"\nSummary:")
    print(f"Files checked: {files_checked}")
    print(f"Files modified: {files_modified}")
    print(f"Matches fixed: {matches_fixed}")

if __name__ == '__main__':
    fix_martinez_matches() 