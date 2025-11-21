#!/usr/bin/env python3
import json
import os
import sys
import glob
import argparse
import shutil
from pathlib import Path

ALIAS_FILE = "mt/name_alias.json"

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Apply name aliases to wrestler data.')
    parser.add_argument('season', type=str, help='Season year (e.g. 2015)')
    return parser.parse_args()

def load_aliases(season):
    """Load name aliases for the specified season."""
    try:
        with open(ALIAS_FILE, 'r') as f:
            alias_data = json.load(f)
            
        # Filter aliases for the specified season
        season_aliases = []
        for alias in alias_data.get('aliases', []):
            if alias.get('conditions', {}).get('season') == season:
                season_aliases.append(alias)
                
        print(f"Loaded {len(season_aliases)} aliases for season {season}")
        return season_aliases
    except Exception as e:
        print(f"Error loading aliases: {e}")
        return []

def apply_aliases_to_file(file_path, aliases, output_dir):
    """Apply aliases to a single JSON file."""
    try:
        # Load the team data
        with open(file_path, 'r') as f:
            team_data = json.load(f)
            
        team_name = team_data.get('team_name', '')
        print(f"\nProcessing team: {team_name}")
        
        changes_made = False
        roster = team_data.get('roster', [])
        
        # Track all replacements for reporting
        replacements = []
        
        # First, check if any wrestlers on this team match our aliases
        for wrestler in roster:
            wrestler_name = wrestler.get('name', '')
            
            # Check each alias
            for alias in aliases:
                # Check if this wrestler's name matches any variant
                for variant in alias.get('name_variants', []):
                    if variant == wrestler_name:
                        # Check if team condition matches
                        if alias.get('conditions', {}).get('team') == team_name:
                            canonical_name = alias.get('canonical_name')
                            print(f"MATCH FOUND: {wrestler_name} → {canonical_name} on team {team_name}")
                            
                            # Replace the wrestler's own name
                            old_name = wrestler['name']
                            wrestler['name'] = canonical_name
                            replacements.append(f"Changed wrestler name: {old_name} → {canonical_name}")
                            changes_made = True
        
        # Next, scan through all matches in all wrestlers to find name variants
        for wrestler in roster:
            for match in wrestler.get('matches', []):
                summary = match.get('summary', '')
                
                # Check each alias for each match
                for alias in aliases:
                    canonical_name = alias.get('canonical_name')
                    alias_team = alias.get('conditions', {}).get('team')
                    
                    # Check each variant of the name
                    for variant in alias.get('name_variants', []):
                        if variant in summary:
                            # Need to verify if this is for the correct team
                            # This is challenging since we need to check if the team is mentioned in the summary
                            
                            # Simple approach: if team name appears in summary near the variant
                            # or we've confirmed this team has this wrestler
                            if alias_team in summary or any(w['name'] == variant for w in roster):
                                # Replace the variant with canonical name in the summary
                                new_summary = summary.replace(variant, canonical_name)
                                if new_summary != summary:
                                    match['summary'] = new_summary
                                    replacements.append(f"In match: {summary} → {new_summary}")
                                    changes_made = True
        
        # Save the modified file if changes were made
        if changes_made:
            # Create output filename
            team_filename = os.path.basename(file_path)
            output_path = os.path.join(output_dir, team_filename)
            
            with open(output_path, 'w') as f:
                json.dump(team_data, f, indent=2)
            
            print(f"Made {len(replacements)} replacements in {team_name}:")
            for replacement in replacements:
                print(f"  - {replacement}")
            
            return len(replacements)
        else:
            print(f"No changes needed for {team_name}")
            # Copy the file unchanged
            team_filename = os.path.basename(file_path)
            output_path = os.path.join(output_dir, team_filename)
            shutil.copy(file_path, output_path)
            return 0
            
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return 0

def process_season(season):
    """Process all team files for a season."""
    # Setup directories
    in_dir = os.path.join("mt", "data", season)
    out_dir = os.path.join("mt", "data_alias", season)
    os.makedirs(out_dir, exist_ok=True)
    
    # Load aliases for this season
    aliases = load_aliases(season)
    if not aliases:
        print(f"No aliases found for season {season}. Copying files without changes.")
        # Copy all files without changes
        for file_path in glob.glob(os.path.join(in_dir, "*.json")):
            out_path = os.path.join(out_dir, os.path.basename(file_path))
            shutil.copy(file_path, out_path)
        return
    
    # Process each file
    total_replacements = 0
    team_files = glob.glob(os.path.join(in_dir, "*.json"))
    print(f"Found {len(team_files)} team files to process")
    
    for file_path in team_files:
        replacements = apply_aliases_to_file(file_path, aliases, out_dir)
        total_replacements += replacements
    
    print(f"\nProcessing complete for season {season}:")
    print(f"- Processed {len(team_files)} team files")
    print(f"- Made {total_replacements} total replacements")
    print(f"- Output saved to {out_dir}")

def main():
    args = parse_args()
    print(f"Starting name alias processing for season {args.season}")
    process_season(args.season)
    
if __name__ == "__main__":
    main() 