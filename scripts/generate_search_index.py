#!/usr/bin/env python3
"""
Generate search_index.js for global site search.

This script reads wrestler and team index files and creates a JavaScript
file with searchable data for Fuse.js autocomplete.

Supports both NCAA and HS modes.
"""

import argparse
import json
import re
from pathlib import Path


def slug_to_name(slug):
    """Convert team slug to display name."""
    return slug.replace('_', ' ').title()


def generate_search_tokens(name, team=None, weight=None, team_slug=None):
    """Generate search tokens from name, team, weight, and common abbreviations."""
    tokens = set()
    
    # Add name tokens (lowercase, split on spaces)
    name_lower = name.lower()
    tokens.update(name_lower.split())
    
    # Add team tokens
    if team:
        team_lower = team.lower()
        tokens.update(team_lower.split())
    
    # Add weight class
    if weight:
        tokens.add(str(weight))
    
    # Add common team abbreviations (NCAA only)
    if team_slug:
        # PSU for Penn State
        if 'penn_state' in team_slug:
            tokens.add('psu')
        # Common abbreviations
        abbrev_map = {
            'iowa_state': 'isu',
            'oklahoma_state': 'osu',
            'ohio_state': 'osu',
            'nc_state': 'ncsu',
            'virginia_tech': 'vt',
            'northern_iowa': 'uni',
        }
        if team_slug in abbrev_map:
            tokens.add(abbrev_map[team_slug])
    
    return sorted(list(tokens))


def team_slug_to_url(team_slug, gender=None):
    """Convert team slug to URL."""
    if gender:
        return f"/team.html?team={team_slug}&gender={gender}"
    return f"/team.html?team={team_slug}"


def wrestler_id_to_url(wrestler_id, gender=None):
    """Convert wrestler ID to URL."""
    if gender:
        return f"/wrestler.html?id={wrestler_id}&gender={gender}"
    return f"/wrestler.html?id={wrestler_id}"


def load_boys_inactive_mask(script_dir, season):
    """Load boys inactive wrestlers mask file."""
    mask_file = script_dir / f"mt/rankings_data/hs_ky_boys/{season}/boys_inactive_wrestlers.json"
    
    if not mask_file.exists():
        return set()
    
    try:
        with open(mask_file, 'r', encoding='utf-8') as f:
            mask_data = json.load(f)
        
        masked_ids = set()
        for wrestler in mask_data.get("masked_wrestlers", []):
            wrestler_id = wrestler.get("boys_wrestler_id")
            if wrestler_id:
                masked_ids.add(str(wrestler_id))
        
        return masked_ids
    except Exception as e:
        print(f"Warning: Could not load boys inactive mask: {e}")
        return set()


def load_gender_data(script_dir, gender, season):
    """Load wrestlers and teams for a specific gender."""
    wrestlers_index = script_dir / f"frontend/hs-ky-ui/public/data/wrestlers/{gender}/{season}/index_wrestlers.json"
    teams_index = script_dir / f"frontend/hs-ky-ui/public/data/wrestlers/{gender}/{season}/index_teams.json"
    
    search_items = []
    
    # Load boys inactive mask if processing boys
    masked_wrestler_ids = set()
    if gender == 'boys':
        masked_wrestler_ids = load_boys_inactive_mask(script_dir, season)
        if masked_wrestler_ids:
            print(f"Loaded mask for {len(masked_wrestler_ids)} inactive boys wrestlers")
    
    # Load wrestlers
    if wrestlers_index.exists():
        with open(wrestlers_index, 'r', encoding='utf-8') as f:
            wrestlers = json.load(f)
        
        for wrestler in wrestlers:
            wrestler_id = wrestler.get('wrestler_id')
            
            if not wrestler_id:
                continue
            
            # Skip masked wrestlers (boys only)
            if masked_wrestler_ids and str(wrestler_id) in masked_wrestler_ids:
                continue
            
            name = wrestler.get('name', 'Unknown')
            team = wrestler.get('team', 'Unknown')
            team_slug = wrestler.get('team_slug', '')
            weight = wrestler.get('weight_class')
            rank = wrestler.get('current_rank')  # May be None if unranked
            
            # Generate secondary text
            secondary_parts = []
            if team:
                secondary_parts.append(team)
            if weight:
                secondary_parts.append(str(weight))
            secondary = " · ".join(secondary_parts) if secondary_parts else ""
            
            # Generate search tokens
            search_tokens = generate_search_tokens(name, team, weight, team_slug)
            
            # Build URL with gender
            url = wrestler_id_to_url(wrestler_id, gender)
            
            search_items.append({
                "type": "wrestler",
                "name": name,
                "secondary": secondary,
                "url": url,
                "searchTokens": search_tokens,
                "rank": rank,  # None if unranked, number if ranked
                "gender": gender  # 'boys' or 'girls'
            })
    
    # Load teams (only once, but include gender in URL)
    teams_loaded = set()
    if teams_index.exists():
        with open(teams_index, 'r', encoding='utf-8') as f:
            teams = json.load(f)
        
        for team_data in teams:
            team_name = team_data.get('team', 'Unknown')
            team_slug = team_data.get('team_slug', '')
            
            if not team_slug or team_slug in teams_loaded:
                continue
            
            teams_loaded.add(team_slug)
            
            # Generate secondary text
            secondary = f"KY HS"
            
            # Generate search tokens
            search_tokens = generate_search_tokens(team_name, team_slug=team_slug)
            
            # Build URL with gender (default to boys if not specified)
            url = team_slug_to_url(team_slug, gender)
            
            search_items.append({
                "type": "team",
                "name": team_name,
                "secondary": secondary,
                "url": url,
                "searchTokens": search_tokens,
                "gender": gender  # 'boys' or 'girls'
            })
    
    return search_items


def main():
    parser = argparse.ArgumentParser(description="Generate search_index.js for site search")
    parser.add_argument(
        "-league",
        choices=["ncaa", "hs"],
        default="ncaa",
        help="League type (default: ncaa)"
    )
    parser.add_argument(
        "-gender",
        choices=["boys", "girls", "both"],
        help="Gender for HS (required if league=hs). Use 'both' to combine boys and girls."
    )
    parser.add_argument(
        "-season",
        type=int,
        default=2026,
        help="Season year (default: 2026)"
    )
    
    args = parser.parse_args()
    
    if args.league == 'hs' and not args.gender:
        parser.error("--gender is required when --league=hs")
    
    script_dir = Path(__file__).parent.parent
    
    search_index = []
    
    if args.league == 'hs':
        # For HS, load data for specified gender(s)
        if args.gender == 'both':
            print("Loading boys data...")
            boys_items = load_gender_data(script_dir, 'boys', args.season)
            search_index.extend(boys_items)
            print(f"  Added {len([x for x in boys_items if x['type'] == 'wrestler'])} boys wrestlers")
            print(f"  Added {len([x for x in boys_items if x['type'] == 'team'])} teams")
            
            print("\nLoading girls data...")
            girls_items = load_gender_data(script_dir, 'girls', args.season)
            search_index.extend(girls_items)
            print(f"  Added {len([x for x in girls_items if x['type'] == 'wrestler'])} girls wrestlers")
            print(f"  Added {len([x for x in girls_items if x['type'] == 'team'])} teams")
        else:
            items = load_gender_data(script_dir, args.gender, args.season)
            search_index.extend(items)
            print(f"  Added {len([x for x in items if x['type'] == 'wrestler'])} wrestlers")
            print(f"  Added {len([x for x in items if x['type'] == 'team'])} teams")
        
        output_file = script_dir / "frontend/hs-ky-ui/public/search_index.js"
    else:  # ncaa
        wrestlers_index = script_dir / f"frontend/wrestledata-ui/public/wrestlers/{args.season}/index_wrestlers.json"
        teams_index = script_dir / f"frontend/wrestledata-ui/public/wrestlers/{args.season}/index_teams.json"
        output_file = script_dir / "frontend/wrestledata-ui/public/search_index.js"
        
        # Load wrestlers
        print(f"Loading wrestlers from {wrestlers_index}...")
        if not wrestlers_index.exists():
            print(f"Error: Wrestlers index not found: {wrestlers_index}")
            return
        
        with open(wrestlers_index, 'r', encoding='utf-8') as f:
            wrestlers = json.load(f)
        
        for wrestler in wrestlers:
            name = wrestler.get('name', 'Unknown')
            team = wrestler.get('team', 'Unknown')
            team_slug = wrestler.get('team_slug', '')
            weight = wrestler.get('weight_class')
            wrestler_id = wrestler.get('wrestler_id')
            
            if not wrestler_id:
                continue
            
            # Generate secondary text
            secondary_parts = []
            if team:
                secondary_parts.append(team)
            if weight:
                secondary_parts.append(str(weight))
            secondary = " · ".join(secondary_parts) if secondary_parts else ""
            
            # Generate search tokens
            search_tokens = generate_search_tokens(name, team, weight, team_slug)
            
            search_index.append({
                "type": "wrestler",
                "name": name,
                "secondary": secondary,
                "url": wrestler_id_to_url(wrestler_id),
                "searchTokens": search_tokens
            })
        
        print(f"  Added {len(search_index)} wrestlers")
        
        # Load teams
        print(f"Loading teams from {teams_index}...")
        if not teams_index.exists():
            print(f"Error: Teams index not found: {teams_index}")
            return
        
        with open(teams_index, 'r', encoding='utf-8') as f:
            teams = json.load(f)
        
        for team_data in teams:
            team_name = team_data.get('team', 'Unknown')
            team_slug = team_data.get('team_slug', '')
            
            if not team_slug:
                continue
            
            secondary = "D1"
            search_tokens = generate_search_tokens(team_name, team_slug=team_slug)
            
            search_index.append({
                "type": "team",
                "name": team_name,
                "secondary": secondary,
                "url": team_slug_to_url(team_slug),
                "searchTokens": search_tokens
            })
        
        print(f"  Added {len([x for x in search_index if x['type'] == 'team'])} teams")
    
    print(f"\nTotal items: {len(search_index)}")
    
    # Write JavaScript file
    print(f"Writing search_index.js to {output_file}...")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("// Search index for WrestleData global search\n")
        f.write("// Generated automatically - do not edit manually\n\n")
        f.write("window.SEARCH_INDEX = ")
        json.dump(search_index, f, indent=2, ensure_ascii=False)
        f.write(";\n")
    
    print("✓ Search index generated successfully!")


if __name__ == "__main__":
    main()
