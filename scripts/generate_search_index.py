#!/usr/bin/env python3
"""
Generate search_index.js for global site search.

This script reads wrestler and team index files and creates a JavaScript
file with searchable data for Fuse.js autocomplete.
"""

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
    
    # Add common team abbreviations
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


def team_slug_to_url(team_slug):
    """Convert team slug to URL."""
    return f"/team.html?team={team_slug}"


def wrestler_id_to_url(wrestler_id):
    """Convert wrestler ID to URL."""
    return f"/wrestler.html?id={wrestler_id}"


def main():
    # Paths
    script_dir = Path(__file__).parent.parent
    wrestlers_index = script_dir / "frontend/wrestledata-ui/public/wrestlers/2026/index_wrestlers.json"
    teams_index = script_dir / "frontend/wrestledata-ui/public/wrestlers/2026/index_teams.json"
    output_file = script_dir / "frontend/wrestledata-ui/public/search_index.js"
    
    search_index = []
    
    # Load wrestlers
    print(f"Loading wrestlers from {wrestlers_index}...")
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
    with open(teams_index, 'r', encoding='utf-8') as f:
        teams = json.load(f)
    
    for team_data in teams:
        team_name = team_data.get('team', 'Unknown')
        team_slug = team_data.get('team_slug', '')
        
        if not team_slug:
            continue
        
        # Generate secondary text (conference info would go here)
        secondary = "D1"  # Placeholder - can be enhanced later
        
        # Generate search tokens
        search_tokens = generate_search_tokens(team_name, team_slug=team_slug)
        
        search_index.append({
            "type": "team",
            "name": team_name,
            "secondary": secondary,
            "url": team_slug_to_url(team_slug),
            "searchTokens": search_tokens
        })
    
    print(f"  Added {len([x for x in search_index if x['type'] == 'team'])} teams")
    print(f"Total items: {len(search_index)}")
    
    # Write JavaScript file
    print(f"Writing search_index.js to {output_file}...")
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("// Search index for WrestleData global search\n")
        f.write("// Generated automatically - do not edit manually\n\n")
        f.write("window.SEARCH_INDEX = ")
        json.dump(search_index, f, indent=2, ensure_ascii=False)
        f.write(";\n")
    
    print("✓ Search index generated successfully!")


if __name__ == "__main__":
    main()

