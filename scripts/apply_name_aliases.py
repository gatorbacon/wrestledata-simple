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
    parser.add_argument('-league', type=str, default='ncaa', choices=['ncaa', 'hs'],
                        help='League type: ncaa (default) or hs')
    parser.add_argument('-state', type=str, help='State code (required when league=hs, currently only KY supported)')
    parser.add_argument('-gender', type=str, choices=['boys', 'girls', 'men', 'women'],
                        help='Gender: boys/girls (HS) or men/women (NCAA)')
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

def apply_aliases_to_file(file_path, aliases, output_dir, league='ncaa'):
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
        
        # TrackWrestling occasionally labels a heavyweight bracket "HWT" or
        # "235" (the girls' HS heavyweight label -- never valid for NCAA men)
        # instead of "285" for a specific tournament (seen recurring across
        # backfilled seasons). Either splits that wrestler's record across a
        # phantom weight_class_*.json and breaks opponent lookups downstream,
        # so normalize here rather than hand-fixing it every time. NCAA-only:
        # "235" is a real, valid girls' HS weight class elsewhere.
        STANDARD_WEIGHTS = {'125', '133', '141', '149', '157', '165', '174', '184', '197', '285'}
        if league == 'ncaa':
            for wrestler in roster:
                for match in wrestler.get('matches', []):
                    if match.get('weight') in ('HWT', '235'):
                        bad = match['weight']
                        match['weight'] = '285'
                        replacements.append(f"Normalized weight label: {bad} → 285 for {wrestler.get('name', '')}")
                        changes_made = True

            # The COVID-shortened 2020-21 season saw at least one regional
            # tournament run in lettered/paired "pod" brackets (Air Force,
            # Northern Colorado, Utah Valley), producing weight labels like
            # "125A", "141-149", "165 (9th)", "165 True", or a blank string --
            # none of which are a real weight class, and some of which don't
            # even numerically match the wrestler's own weight. Rather than
            # adjudicate each pod label, trust the wrestler's own roster-level
            # weight_class as ground truth (same principle as the HWT/235 fix
            # above) and normalize any non-standard match weight to it.
            for wrestler in roster:
                own_weight = wrestler.get('weight_class')
                if not own_weight:
                    continue
                for match in wrestler.get('matches', []):
                    wt = match.get('weight')
                    if wt not in STANDARD_WEIGHTS:
                        match['weight'] = own_weight
                        replacements.append(f"Normalized non-standard weight label {wt!r} → {own_weight} for {wrestler.get('name', '')}")
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
                            # Only apply if the alias's own target team is the
                            # one actually named alongside this variant in the
                            # match text. The previous fallback here --
                            # "or any(w['name'] == variant for w in roster)" --
                            # checked the CURRENT team's own roster, which is
                            # wrong: it fires whenever some OTHER, unrelated
                            # real wrestler on the current team happens to
                            # share the exact variant name, silently
                            # corrupting their name into a different alias's
                            # canonical_name (confirmed: an alias scoped to
                            # "Holy Cross (Louisville)"'s "Tyler Hunt" variant
                            # was overwriting North Carolina State's own real,
                            # unrelated "Tyler Hunt" in 2013 data). Team scope
                            # must be confirmed via the alias's own team
                            # appearing in the summary text, not the current
                            # roster's contents.
                            if alias_team in summary:
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

def league_dir_key(league, gender, state=None):
    if league == 'hs':
        return f"hs_{state.lower()}_{gender}"
    return f"ncaa_{gender}"


def process_season(season, league='ncaa', state=None, gender=None):
    """Process all team files for a season."""
    if league == 'hs':
        if not state:
            raise ValueError("-state is required when -league=hs")
        if state.upper() != 'KY':
            raise ValueError(f"Only KY is currently supported for HS. Got: {state}")
        if not gender:
            raise ValueError("-gender is required when -league=hs")
        if gender not in ['boys', 'girls']:
            raise ValueError(f"-gender must be 'boys' or 'girls' for HS. Got: {gender}")
    else:  # ncaa
        if not gender:
            raise ValueError("-gender is required when -league=ncaa")
        if gender not in ['men', 'women']:
            raise ValueError(f"-gender must be 'men' or 'women' for NCAA. Got: {gender}")

    key = league_dir_key(league, gender, state)
    in_dir = os.path.join("mt", "data", key, str(season))
    out_dir = os.path.join("mt", "data_alias", key, str(season))
    
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
        replacements = apply_aliases_to_file(file_path, aliases, out_dir, league=league)
        total_replacements += replacements
    
    print(f"\nProcessing complete for season {season}:")
    print(f"- Processed {len(team_files)} team files")
    print(f"- Made {total_replacements} total replacements")
    print(f"- Output saved to {out_dir}")

def main():
    args = parse_args()
    league_label = f"{args.league.upper()}" if args.league == 'ncaa' else f"{args.state} HS {args.gender.capitalize()}" if args.league == 'hs' else args.league
    print(f"Starting name alias processing for season {args.season} ({league_label})")
    process_season(args.season, league=args.league, state=args.state, gender=args.gender)
    
if __name__ == "__main__":
    main() 