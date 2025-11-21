#!/usr/bin/env python3
"""
Script to fix matches involving Aaron (A.J.) Schopp where A.J. was incorrectly parsed as the team name.
Only processes files in the data/2014 folder.
"""

import json
from pathlib import Path
import re

def fix_match(match):
    """Fix a single match if it involves Aaron (A.J.) Schopp."""
    modified = False
    
    # Check winner
    if match.get('winner_name') == 'Aaron' and match.get('winner_team') == 'A.J.':
        match['winner_name'] = 'Aaron (A.J.) Schopp'
        match['winner_team'] = 'Edinboro'
        modified = True
    
    # Check loser
    if match.get('loser_name') == 'Aaron' and match.get('loser_team') == 'A.J.':
        match['loser_name'] = 'Aaron (A.J.) Schopp'
        match['loser_team'] = 'Edinboro'
        modified = True
    
    # Fix summary if needed
    if modified and 'summary' in match:
        # Replace "Aaron (A.J.) Schopp (Edinboro)" with the same text to ensure consistency
        summary = match['summary']
        summary = re.sub(r'Aaron \(A\.J\.\) Schopp \(Edinboro\)', 'Aaron (A.J.) Schopp (Edinboro)', summary)
        summary = re.sub(r'Aaron \(A\.J\.\)', 'Aaron (A.J.) Schopp', summary)
        match['summary'] = summary
    
    return modified

def process_file(file_path):
    """Process a single JSON file."""
    print(f"Processing {file_path}...")
    
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        matches_fixed = 0
        
        # Process each wrestler's matches
        for wrestler in data.get('roster', []):
            for match in wrestler.get('matches', []):
                if fix_match(match):
                    matches_fixed += 1
        
        # Only write back if we made changes
        if matches_fixed > 0:
            print(f"Fixed {matches_fixed} matches in {file_path}")
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
        
        return matches_fixed
    
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return 0

def main():
    """Main function to process all JSON files in 2014-related folders."""
    # Process all 2014-related folders
    folders_to_check = [
        Path('data/2014'),
        Path('data/2015'),
        Path('data/2014 copy'),
        Path('data/2014-old')
    ]
    
    total_files = 0
    total_matches_fixed = 0
    
    print("Starting to process files in 2014-related folders...")
    
    for data_dir in folders_to_check:
        if not data_dir.exists():
            print(f"Skipping {data_dir} - directory does not exist")
            continue
            
        print(f"\nProcessing files in {data_dir}...")
        # Process all JSON files in the directory
        for file_path in data_dir.glob('*.json'):
            total_files += 1
            matches_fixed = process_file(file_path)
            total_matches_fixed += matches_fixed
    
    print(f"\nSummary:")
    print(f"Processed {total_files} files")
    print(f"Fixed {total_matches_fixed} matches total")

if __name__ == '__main__':
    main() 