#!/usr/bin/env python3
"""
Script to fix matches where a wrestler's nickname in parentheses was incorrectly parsed as the team name.
Handles the following cases:
1. Aaron (A.J.) Schopp - Edinboro
2. Martin (Josh) Martinez - Air Force 
3. Mathew (Keilan) Torres - Oklahoma State

This script processes files in specific season folders.
"""

import json
from pathlib import Path
import re

# Define the wrestlers with nickname issues and their correct information
WRESTLERS_TO_FIX = [
    {
        'first_name': 'Aaron',
        'nickname': 'A.J.',
        'full_name': 'Aaron (A.J.) Schopp',
        'team': 'Edinboro'
    },
    {
        'first_name': 'Martin',
        'nickname': 'Josh',
        'full_name': 'Martin (Josh) Martinez',
        'team': 'Air Force'
    },
    {
        'first_name': 'Mathew',
        'nickname': 'Keilan',
        'full_name': 'Mathew (Keilan) Torres',
        'team': 'Oklahoma State'
    }
]

def fix_match(match):
    """Fix a single match if it involves wrestlers with nickname parsing issues."""
    modified = False
    
    # Check each wrestler that needs fixing
    for wrestler in WRESTLERS_TO_FIX:
        # Check winner
        if match.get('winner_name') == wrestler['first_name'] and match.get('winner_team') == wrestler['nickname']:
            match['winner_name'] = wrestler['full_name']
            match['winner_team'] = wrestler['team']
            modified = True
        
        # Check loser
        if match.get('loser_name') == wrestler['first_name'] and match.get('loser_team') == wrestler['nickname']:
            match['loser_name'] = wrestler['full_name']
            match['loser_team'] = wrestler['team']
            modified = True
        
        # Fix summary if needed
        if modified and 'summary' in match:
            summary = match['summary']
            # Replace pattern in summary with consistent format
            pattern = f"{wrestler['first_name']}\\s*\\({wrestler['nickname']}\\)"
            replacement = wrestler['full_name']
            summary = re.sub(pattern, replacement, summary)
            
            # Ensure team is properly formatted
            team_pattern = f"{wrestler['full_name']} \\({wrestler['team']}\\)"
            if wrestler['full_name'] in summary and team_pattern not in summary:
                summary = summary.replace(wrestler['full_name'], f"{wrestler['full_name']} ({wrestler['team']})")
            
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
    """Main function to process all JSON files in relevant season folders."""
    # Process multiple season folders
    folders_to_check = [
        Path('data/2014'),
        Path('data/2015'),  # Include 2015 since some issues might span seasons
        Path('data/team_lists/2014'),
        Path('data/team_lists/2015')
    ]
    
    total_files = 0
    total_matches_fixed = 0
    
    print("Starting to process files in season folders...")
    
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
    
    # Print the wrestlers that were fixed for clarity
    print("\nFixed nickname parsing issues for the following wrestlers:")
    for wrestler in WRESTLERS_TO_FIX:
        print(f"- {wrestler['full_name']} ({wrestler['team']})")

if __name__ == '__main__':
    main() 