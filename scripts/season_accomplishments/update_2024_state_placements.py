#!/usr/bin/env python3
"""
Update 2024 season accomplishments with state tournament placements.

This script matches state tournament results to wrestlers and updates
their state_qualifier, state_place, and state_champion fields.
"""

import json
import re
from pathlib import Path
from collections import defaultdict
from difflib import SequenceMatcher


def normalize_name(name: str) -> str:
    """Normalize name for matching."""
    if not name:
        return ""
    return name.lower().strip()


def normalize_team_name(team: str) -> str:
    """Normalize team name for matching."""
    if not team:
        return ""
    # Remove parentheticals like "(Louisville)"
    team = re.sub(r'\s*\([^)]+\)', '', team)
    # Remove "High School" suffix
    team = re.sub(r'\s+High School$', '', team, flags=re.IGNORECASE)
    # Normalize hyphens and spaces
    team = re.sub(r'[-–—]', ' ', team)  # Replace hyphens with spaces
    team = re.sub(r'\s+', ' ', team)  # Collapse multiple spaces
    return team.lower().strip()


def name_similarity(name1: str, name2: str) -> float:
    """Calculate name similarity score (0-1)."""
    return SequenceMatcher(None, normalize_name(name1), normalize_name(name2)).ratio()


def parse_state_results():
    """Parse the state tournament results text."""
    results_text = """106

Guaranteed Places

1st Place - Jackson Wells of Harrison County

2nd Place - Henry Koller of South Oldham

3rd Place - Luke Cornwell of Ryle

4th Place - Roman Valera of Trinity (Louisville)

5th Place - Braxton Corbett of Union County

6th Place - Nathan Reusch of Simon Kenton

7th Place - Aluma Enwa of Great Crossing High School

8th Place - Wyatt Payne of Henderson County

113

Guaranteed Places

1st Place - Christian Delos Santos of John Hardin

2nd Place - Zac Scott of Johnson Central

3rd Place - Kapela Joseph of Frederick Douglass

4th Place - Clayton Badida of Conner

5th Place - Blaine Kimery of South Oldham

6th Place - Brennen East of Walton Verona

7th Place - Dakota Phillips of Boyle County

8th Place - Osvaldo Menchacha of Harrison County

120

Guaranteed Places

1st Place - George Dennis of Harrison County

2nd Place - Ethan Davis of Grant County

3rd Place - Landon Evans of Ryle

4th Place - Utah Heady of Union County

5th Place - Madden Brown of Oldham County

6th Place - Maalik Washington of Conner

7th Place - Corbin Nance of Anderson County

8th Place - Ryan Smith of Johnson Central

126

Guaranteed Places

1st Place - Jayden Raney of Union County

2nd Place - Jonah McCloskey of Simon Kenton

3rd Place - Anthony Condi of Frederick Douglass

4th Place - Jayven Williams of Paducah Tilghman

5th Place - Seth Page of Ryle

6th Place - Rowdy Benner of Great Crossing High School

7th Place - Michael Smith of Scott

8th Place - Blake Luttrell of Fairdale

132

Guaranteed Places

1st Place - Jordyn Raney of Union County

2nd Place - Leland Reeves of Taylor County

3rd Place - Kaygen Roberts of Boyle County

4th Place - Dakota Ferguson of Johnson Central

5th Place - Cordion Abernathy of Conner

6th Place - Jagger Irvin of Ryle

7th Place - Jack Finley of Great Crossing High School

8th Place - Andrew Pomeroy of Male

138

Guaranteed Places

1st Place - Breyden Whorton of LaRue County

2nd Place - TJ Meyer of Walton Verona

3rd Place - Cofy Walls of Caldwell County

4th Place - Hunter Luttrell of Fairdale

5th Place - James Morris of Johnson Central

6th Place - LOGAN CANTRELL of Madison Central

7th Place - JONAH BAYSINGER of Scott County

8th Place - Xavier Gonzalez of Moore

144

Guaranteed Places

1st Place - Isaac Johns of Woodford County

2nd Place - Hunter Jenkins of Union County

3rd Place - Micah Thompson of Boyle County

4th Place - Tyler Lattin of Meade County

5th Place - Deacon Heisler of Campbell County

6th Place - Parker Maynard of Martin County High School

7th Place - Timothy Sulfsted of Walton Verona

8th Place - Stephen Ntchou of Moore

150

Guaranteed Places

1st Place - Miller Brown of Oldham County

2nd Place - Ayden Lehman of Trinity (Louisville)

3rd Place - Rider Trumble of Ryle

4th Place - Timothy Nichols of Caldwell County

5th Place - Kyle Wojcicki of North Oldham

6th Place - Jacob McDonald of Taylor County

7th Place - Jeremy Ray of Union County

8th Place - Westin Brown of LaRue County

157

Guaranteed Places

1st Place - Malachia Harris of Trinity (Louisville)

2nd Place - Rilen Pinkston of Highlands High School

3rd Place - Ethan Sentelle of Great Crossing High School

4th Place - Reese McGill of Oldham County

5th Place - Abreyan Fletcher of Union County

6th Place - Owen Lamer of Taylor County

7th Place - Bryant Faucett of Bullitt Central

8th Place - Jaimen Carey of Boyle County

165

Guaranteed Places

1st Place - Aiden Butler of Great Crossing High School

2nd Place - Max Speaker of St. Xavier

3rd Place - Dalton Matney of Johnson Central

4th Place - DJ Wilson of Paducah Tilghman

5th Place - Tristin Millet of Oldham County

6th Place - CARSON HERBST of Madison Central

7th Place - Creed Williams of North Oldham

8th Place - Jaylin Littleton of Hopkinsville

175

Guaranteed Places

1st Place - Lucas Ricketts of Union County

2nd Place - Joshua Strayer of Great Crossing High School

3rd Place - Marcus James of Taylor County

4th Place - Logan Dingus of Harrison County

5th Place - Seth Davis of Johnson Central

6th Place - Brandon Burchett of Fairdale

7th Place - Jax Crowe of Boyle County

8th Place - Caleb Duke of Ryle

190

Guaranteed Places

1st Place - Lane Kiser of Trinity (Louisville)

2nd Place - Uriah Virzi of Paducah Tilghman

3rd Place - Josh Soeder of Oldham County

4th Place - Logan Castle of Johnson Central

5th Place - Travis Steiber of Ryle

6th Place - Jackson Burger of Boyle County

7th Place - Landon Newman of McCracken County

8th Place - Brock Sexton of Harrison County

215

Guaranteed Places

1st Place - Jack James of Paducah Tilghman

2nd Place - Jahvon Frazier of Bryan Station

3rd Place - Luke Hyden of Walton Verona

4th Place - Tucker Roth of Pleasure Ridge Park

5th Place - Mac Darland of Lexington Christian

6th Place - Michael Williams of Moore

7th Place - Drew Stearman of North Oldham

8th Place - Payton Lyons of Johnson Central

285

Guaranteed Places

1st Place - Carter Guillaume of St. Xavier

2nd Place - Stephen Whitehead of Madison Southern

3rd Place - Jimmy Mooney of Paducah Tilghman

4th Place - Colton Lewis of Pleasure Ridge Park

5th Place - Peyton Mayo of Frederick Douglass

6th Place - Cole Christian of Ashland Blazer

7th Place - Jake Heady of LaRue County

8th Place - Jacob Wilson of Great Crossing High School"""

    placements = []
    lines = results_text.strip().split('\n')
    current_weight = None

    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Check if this is a weight class header
        if line.isdigit():
            current_weight = int(line)
            continue
        
        # Parse placement lines: "1st Place - Name of Team"
        match = re.match(r'(\d+)(?:st|nd|rd|th)\s+Place\s+-\s+(.+?)\s+of\s+(.+)', line)
        if match:
            place = int(match.group(1))
            name = match.group(2).strip()
            team = match.group(3).strip()
            
            # Normalize team names (remove parentheticals)
            team = re.sub(r'\s*\([^)]+\)', '', team)
            
            placements.append({
                'weight': current_weight,
                'name': name,
                'team': team,
                'place': place
            })
    
    return placements


def find_wrestler_match(placement: dict, wrestlers: list) -> tuple:
    """
    Find matching wrestler for a placement.
    
    Returns (wrestler_index, confidence_score) or (None, 0.0)
    """
    best_match_idx = None
    best_score = 0.0
    
    placement_name_norm = normalize_name(placement['name'])
    placement_team_norm = normalize_team_name(placement['team'])
    placement_weight = placement['weight']
    
    for idx, wrestler in enumerate(wrestlers):
        wrestler_weight = wrestler.get('final_weight')
        if wrestler_weight != placement_weight:
            continue
        
        wrestler_name_norm = normalize_name(wrestler.get('name', ''))
        wrestler_team_norm = normalize_team_name(wrestler.get('team', ''))
        
        # Calculate match score
        name_score = name_similarity(placement['name'], wrestler.get('name', ''))
        team_score = 1.0 if placement_team_norm == wrestler_team_norm else 0.0
        
        # More flexible team matching - allow partial matches
        team_match = (
            placement_team_norm == wrestler_team_norm or
            placement_team_norm in wrestler_team_norm or
            wrestler_team_norm in placement_team_norm
        )
        
        if not team_match:
            continue
        
        # Team score based on how well it matches
        if placement_team_norm == wrestler_team_norm:
            team_score = 1.0
        elif placement_team_norm in wrestler_team_norm or wrestler_team_norm in placement_team_norm:
            team_score = 0.8  # Partial match
        
        score = name_score * 0.7 + team_score * 0.3
        
        if score > best_score:
            best_score = score
            best_match_idx = idx
    
    return (best_match_idx, best_score)


def main():
    print("="*60)
    print("UPDATE 2024 STATE TOURNAMENT PLACEMENTS")
    print("="*60)
    
    # Parse state results
    print("\nParsing state tournament results...")
    placements = parse_state_results()
    print(f"Found {len(placements)} placements")
    
    # Load season accomplishments
    file_path = Path("data/season_accomplishments/boys/2024/season_accomplishments.json")
    print(f"\nLoading season accomplishments from: {file_path}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    wrestlers = data['wrestlers']
    print(f"Loaded {len(wrestlers)} wrestlers")
    
    # Match placements to wrestlers
    print("\nMatching placements to wrestlers...")
    matches = []
    unmatched = []
    
    for placement in placements:
        match_idx, score = find_wrestler_match(placement, wrestlers)
        
        if match_idx is not None and score >= 0.7:  # Require at least 70% name similarity
            matches.append((match_idx, placement, score))
        else:
            unmatched.append(placement)
    
    print(f"Matched: {len(matches)}")
    print(f"Unmatched: {len(unmatched)}")
    
    if unmatched:
        print("\n⚠️  Unmatched placements:")
        for p in unmatched:
            print(f"  {p['weight']} lbs, {p['place']}: {p['name']} ({p['team']})")
    
    # Update wrestlers
    print("\nUpdating wrestler records...")
    updated_count = 0
    
    for match_idx, placement, score in matches:
        wrestler = wrestlers[match_idx]
        
        # Update fields
        wrestler['state_qualifier'] = True
        wrestler['state_place'] = placement['place']
        wrestler['state_champion'] = (placement['place'] == 1)
        
        updated_count += 1
        
        if score < 0.95:  # Log low-confidence matches
            print(f"  Low confidence match ({score:.2f}): {placement['name']} -> {wrestler.get('name')}")
    
    print(f"Updated {updated_count} wrestlers")
    
    # Save updated file
    print(f"\nSaving updated file...")
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    # Verify results
    print("\n" + "="*60)
    print("VERIFICATION")
    print("="*60)
    
    state_placers = [w for w in wrestlers if w.get('state_place')]
    state_champions = [w for w in wrestlers if w.get('state_champion')]
    
    from collections import Counter
    placements_count = Counter(w.get('state_place') for w in state_placers)
    
    print(f"Total state placers: {len(state_placers)}")
    print(f"State champions: {len(state_champions)}")
    print(f"\nPlacement distribution:")
    for place in sorted([p for p in placements_count.keys() if p]):
        count = placements_count[place]
        expected = 14
        status = "✅" if count == expected else "❌"
        print(f"  {status} {place}: {count} (expected {expected})")
    
    if all(placements_count.get(p, 0) == 14 for p in range(1, 9)):
        print("\n✅ SUCCESS: All placements correct (14 at each place)")
    else:
        print("\n⚠️  WARNING: Some placements are missing or incorrect")


if __name__ == '__main__':
    main()

