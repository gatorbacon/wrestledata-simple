#!/usr/bin/env python3
"""
Generate projected top-10 individual matchups for a 12-team seeded dual tournament.

This script projects bracket advancement (higher seed always wins) and identifies
individual matchups where both wrestlers are ranked top-10 statewide.
"""

import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Tuple, Optional


def get_weights_for_gender(gender: str) -> List[int]:
    """Get weight classes for the given gender."""
    if gender == 'boys':
        return [106, 113, 120, 126, 132, 138, 144, 150, 157, 165, 175, 190, 215, 285]
    else:  # girls
        return [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235]


def load_rankings_by_weight(season: int, gender: str, data_dir: str = "mt/rankings_data") -> Dict[int, Dict[str, int]]:
    """
    Load rankings organized by weight class.
    
    Returns:
        Dict mapping weight -> {wrestler_id -> rank}
    """
    rankings_by_weight = {}
    data_path = Path(data_dir) / f"hs_ky_{gender}" / str(season)
    
    if not data_path.exists():
        raise FileNotFoundError(f"Rankings directory not found: {data_path}")
    
    weights = get_weights_for_gender(gender)
    
    for weight in weights:
        rankings_file = data_path / f"rankings_{weight}.json"
        if not rankings_file.exists():
            continue
        
        try:
            with open(rankings_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            rankings = data.get("rankings", [])
            weight_ranks = {}
            
            for entry in rankings:
                wrestler_id = str(entry.get("wrestler_id", ""))
                rank = entry.get("rank")
                
                if wrestler_id and rank is not None:
                    weight_ranks[wrestler_id] = rank
            
            rankings_by_weight[weight] = weight_ranks
        
        except Exception as e:
            print(f"Warning: Error loading {rankings_file}: {e}")
            continue
    
    return rankings_by_weight


def load_team_roster(team_name: str, season: int, gender: str, 
                     teams_dir: Path, rankings_by_weight: Dict[int, Dict[str, int]]) -> Optional[Dict]:
    """
    Load a single team's roster with rankings.
    
    Returns:
        Dict with structure:
        {
            "team_name": str,
            "weights": {
                weight: {
                    "wrestler_id": str,
                    "name": str,
                    "rank": int | None
                }
            }
        }
        or None if team not found
    """
    teams_path = teams_dir / gender / str(season)
    
    if not teams_path.exists():
        return None
    
    # Try exact match first
    team_file = teams_path / f"{team_name.replace(' ', '_')}.json"
    
    if not team_file.exists():
        # Try case-insensitive search
        for file in teams_path.glob("*.json"):
            with open(file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            file_team_name = data.get("team_name") or data.get("name", "")
            if file_team_name.lower() == team_name.lower():
                team_file = file
                break
        else:
            return None
    
    try:
        with open(team_file, 'r', encoding='utf-8') as f:
            team_data = json.load(f)
        
        roster = {
            "team_name": team_data.get("team_name") or team_data.get("name", team_name),
            "weights": {}
        }
        
        # Process starters
        starters = team_data.get("starters", {})
        for weight_str, starter_data in starters.items():
            if not starter_data:
                continue
            
            try:
                weight = int(weight_str)
            except ValueError:
                continue
            
            wrestler_id = str(starter_data.get("wrestler_id", ""))
            name = starter_data.get("name", "Unknown")
            
            # Get rank from rankings
            rank = rankings_by_weight.get(weight, {}).get(wrestler_id)
            
            # Only include if ranked (we'll filter for top-10 later)
            roster["weights"][weight] = {
                "wrestler_id": wrestler_id,
                "name": name,
                "rank": rank
            }
        
        return roster
    
    except Exception as e:
        print(f"Warning: Error loading {team_file}: {e}")
        return None


def parse_seed_file(seed_file: Path) -> Dict[int, str]:
    """
    Parse seed file and return dict mapping seed -> team_name.
    
    Validates:
    - Exactly 12 teams
    - Seeds 1-12, unique
    - Format: <seed>,<team_name>
    """
    seeds = {}
    
    with open(seed_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            
            # Parse: seed,team_name
            parts = line.split(',', 1)
            if len(parts) != 2:
                raise ValueError(f"Invalid format at line {line_num}: expected '<seed>,<team_name>'")
            
            try:
                seed = int(parts[0].strip())
                team_name = parts[1].strip()
            except ValueError:
                raise ValueError(f"Invalid seed at line {line_num}: '{parts[0]}' must be an integer")
            
            if seed < 1 or seed > 12:
                raise ValueError(f"Invalid seed at line {line_num}: {seed} must be between 1 and 12")
            
            if seed in seeds:
                raise ValueError(f"Duplicate seed {seed} at line {line_num}")
            
            seeds[seed] = team_name
    
    if len(seeds) != 12:
        raise ValueError(f"Expected 12 teams, found {len(seeds)}")
    
    # Verify all seeds 1-12 are present
    missing_seeds = set(range(1, 13)) - set(seeds.keys())
    if missing_seeds:
        raise ValueError(f"Missing seeds: {sorted(missing_seeds)}")
    
    return seeds


def build_bracket(seeds: Dict[int, str]) -> List[Tuple[str, str, str]]:
    """
    Build bracket progression assuming higher seed always wins.
    
    Returns:
        List of tuples: (round_name, team_a, team_b)
    """
    bracket = []
    
    # FIRST ROUND (Play-in)
    first_round = [
        (8, 9),
        (5, 12),
        (6, 11),
        (7, 10)
    ]
    
    winners = {}
    for seed_a, seed_b in first_round:
        winner = min(seed_a, seed_b)  # Higher seed (lower number) wins
        winners[(seed_a, seed_b)] = winner
        bracket.append(("FIRST ROUND", seeds[seed_a], seeds[seed_b]))
    
    # QUARTERFINALS
    qf_winners = {}
    quarterfinals = [
        (1, winners[(8, 9)]),
        (4, winners[(5, 12)]),
        (3, winners[(6, 11)]),
        (2, winners[(7, 10)])
    ]
    
    for seed_a, seed_b in quarterfinals:
        winner = min(seed_a, seed_b)
        qf_winners[(seed_a, seed_b)] = winner
        bracket.append(("QUARTERFINALS", seeds[seed_a], seeds[seed_b]))
    
    # SEMIFINALS
    sf1_teams = (qf_winners[(1, winners[(8, 9)])], qf_winners[(4, winners[(5, 12)])])
    sf2_teams = (qf_winners[(3, winners[(6, 11)])], qf_winners[(2, winners[(7, 10)])])
    
    sf1_winner = min(sf1_teams)
    sf2_winner = min(sf2_teams)
    
    bracket.append(("SEMIFINALS", seeds[sf1_teams[0]], seeds[sf1_teams[1]]))
    bracket.append(("SEMIFINALS", seeds[sf2_teams[0]], seeds[sf2_teams[1]]))
    
    # FINALS
    finals_winner = min(sf1_winner, sf2_winner)
    bracket.append(("FINALS", seeds[sf1_winner], seeds[sf2_winner]))
    
    # 3RD PLACE MATCH
    sf1_loser = max(sf1_teams)
    sf2_loser = max(sf2_teams)
    bracket.append(("3RD PLACE MATCH", seeds[sf1_loser], seeds[sf2_loser]))
    
    return bracket


def find_top10_matchups(roster_a: Dict, roster_b: Dict, weights: List[int]) -> List[Dict]:
    """
    Find all weight classes where both teams have top-10 ranked wrestlers.
    
    Returns:
        List of matchups, each with:
        {
            "weight": int,
            "wrestler_a": {"name": str, "rank": int, "team": str},
            "wrestler_b": {"name": str, "rank": int, "team": str}
        }
    """
    matchups = []
    
    for weight in weights:
        wrestler_a = roster_a.get("weights", {}).get(weight)
        wrestler_b = roster_b.get("weights", {}).get(weight)
        
        # Both must exist and both must be ranked top-10
        if not wrestler_a or not wrestler_b:
            continue
        
        rank_a = wrestler_a.get("rank")
        rank_b = wrestler_b.get("rank")
        
        if rank_a is None or rank_b is None:
            continue
        
        if rank_a > 10 or rank_b > 10:
            continue
        
        matchups.append({
            "weight": weight,
            "wrestler_a": {
                "name": wrestler_a["name"],
                "rank": rank_a,
                "team": roster_a["team_name"]
            },
            "wrestler_b": {
                "name": wrestler_b["name"],
                "rank": rank_b,
                "team": roster_b["team_name"]
            }
        })
    
    return matchups


def format_output(tournament_name: str, bracket: List[Tuple[str, str, str]], 
                  all_matchups: Dict[Tuple[str, str], List[Dict]]) -> str:
    """
    Format output grouped by round -> dual -> weight.
    """
    output = []
    output.append(f"=== {tournament_name.upper()} ===")
    output.append("")
    
    current_round = None
    
    for round_name, team_a, team_b in bracket:
        # Start new round section
        if round_name != current_round:
            if current_round is not None:
                output.append("")
            output.append(f"=== {round_name} ===")
            current_round = round_name
        
        # Get matchups for this dual
        dual_key = (team_a, team_b)
        matchups = all_matchups.get(dual_key, [])
        
        if not matchups:
            output.append(f"{team_a} vs {team_b}")
            output.append("  (No top-10 matchups)")
            output.append("")
            continue
        
        output.append(f"{team_a} vs {team_b}")
        
        # Sort matchups by weight
        matchups.sort(key=lambda m: m["weight"])
        
        for matchup in matchups:
            weight = matchup["weight"]
            wa = matchup["wrestler_a"]
            wb = matchup["wrestler_b"]
            
            output.append(f"{weight} lbs:")
            output.append(f"  #{wa['rank']} {wa['name']} ({wa['team']})")
            output.append("  vs")
            output.append(f"  #{wb['rank']} {wb['name']} ({wb['team']})")
        
        if matchups:  # Add blank line after matchups if any exist
            output.append("")
    
    return "\n".join(output)


def generate_svg_graphic(template_path: Path, all_matchups: Dict[Tuple[str, str], List[Dict]], 
                         output_path: Path) -> None:
    """
    Generate SVG graphic from template, copying match1 structure for all matches.
    
    Template structure:
    - Group with inkscape:label="match1"
    - Inside match1: groups with inkscape:label="wrestler1_1" and "wrestler1_1" (second one)
    - Inside each wrestler: rank1_1/rank1_2, name1_1/name1_2, school1_1/school1_2
    """
    # Load template
    tree = ET.parse(template_path)
    root = tree.getroot()
    
    # Define namespaces
    ns = {
        "svg": "http://www.w3.org/2000/svg",
        "inkscape": "http://www.inkscape.org/namespaces/inkscape",
    }
    
    # Find match1 group and its parent
    match1 = None
    parent = None
    
    # Search for match1 and track its parent
    for elem in root.iter():
        if elem.tag.endswith('}g') or elem.tag == 'g':
            label = elem.get(f"{{{ns['inkscape']}}}label")
            if label == 'match1':
                match1 = elem
                # Find parent by searching backwards
                for candidate in root.iter():
                    if match1 in list(candidate):
                        parent = candidate
                        break
                break
    
    if match1 is None:
        raise ValueError("Template must contain a group with inkscape:label='match1'")
    
    if parent is None:
        raise ValueError("match1 group must have a parent element")
    
    # Collect all matchups into a flat list (sorted by weight)
    all_matches = []
    for matchups in all_matchups.values():
        all_matches.extend(matchups)
    
    # Sort by weight
    all_matches.sort(key=lambda m: m["weight"])
    
    # Include ALL top-10 matchups (no limit)
    # All matches in all_matchups are already filtered to be top-10 vs top-10
    
    # Fill match1 with first matchup
    if all_matches:
        fill_match_data(match1, all_matches[0], 1, ns)
    
    # Copy match1 for remaining matches
    for idx, matchup in enumerate(all_matches[1:], start=2):
        # Deep copy match1
        new_match = ET.fromstring(ET.tostring(match1, encoding='unicode'))
        
        # Update label from match1 to match{idx}
        new_match.set(f"{{{ns['inkscape']}}}label", f"match{idx}")
        
        # Update all IDs to be unique (increment numbers)
        update_ids_recursive(new_match, idx)
        
        # Fill with data
        fill_match_data(new_match, matchup, idx, ns)
        
        # Append to parent
        parent.append(new_match)
    
    # Save SVG
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(output_path, encoding='utf-8', xml_declaration=True)
    print(f"✓ SVG graphic written to: {output_path}")


def fill_match_data(match_group: ET.Element, matchup: Dict, match_num: int, ns: Dict) -> None:
    """Fill a match group with matchup data."""
    weight = matchup["weight"]
    wa = matchup["wrestler_a"]
    wb = matchup["wrestler_b"]
    
    # Find and update rank1_1 (wrestler A rank)
    rank1_1 = match_group.find(f".//svg:text[@inkscape:label='rank1_1']", namespaces=ns)
    if rank1_1 is not None:
        tspan = rank1_1.find("svg:tspan", ns)
        if tspan is not None:
            inner_tspan = tspan.find("svg:tspan", ns)
            if inner_tspan is not None:
                inner_tspan.text = f"#{wa['rank']}"
            else:
                tspan.text = f"#{wa['rank']}"
        else:
            rank1_1.text = f"#{wa['rank']}"
    
    # Find and update name1_1 (wrestler A name)
    name1_1 = match_group.find(f".//svg:text[@inkscape:label='name1_1']", namespaces=ns)
    if name1_1 is not None:
        tspan = name1_1.find("svg:tspan", ns)
        if tspan is not None:
            tspan.text = wa['name']
        else:
            name1_1.text = wa['name']
    
    # Find and update school1_1 (wrestler A team) - also check for team1_1
    school1_1 = match_group.find(f".//svg:text[@inkscape:label='school1_1']", namespaces=ns)
    if school1_1 is None:
        school1_1 = match_group.find(f".//svg:text[@inkscape:label='team1_1']", namespaces=ns)
    if school1_1 is not None:
        tspan = school1_1.find("svg:tspan", ns)
        if tspan is not None:
            inner_tspan = tspan.find("svg:tspan", ns)
            if inner_tspan is not None:
                inner_tspan.text = wa['team']
            else:
                tspan.text = wa['team']
        else:
            school1_1.text = wa['team']
    
    # Find and update rank1_2 (wrestler B rank)
    rank1_2 = match_group.find(f".//svg:text[@inkscape:label='rank1_2']", namespaces=ns)
    if rank1_2 is not None:
        tspan = rank1_2.find("svg:tspan", ns)
        if tspan is not None:
            inner_tspan = tspan.find("svg:tspan", ns)
            if inner_tspan is not None:
                inner_tspan.text = f"#{wb['rank']}"
            else:
                tspan.text = f"#{wb['rank']}"
        else:
            rank1_2.text = f"#{wb['rank']}"
    
    # Find and update name1_2 (wrestler B name)
    name1_2 = match_group.find(f".//svg:text[@inkscape:label='name1_2']", namespaces=ns)
    if name1_2 is not None:
        tspan = name1_2.find("svg:tspan", ns)
        if tspan is not None:
            tspan.text = wb['name']
        else:
            name1_2.text = wb['name']
    
    # Find and update school1_2 (wrestler B team) - also check for team1_2
    school1_2 = match_group.find(f".//svg:text[@inkscape:label='school1_2']", namespaces=ns)
    if school1_2 is None:
        school1_2 = match_group.find(f".//svg:text[@inkscape:label='team1_2']", namespaces=ns)
    if school1_2 is not None:
        tspan = school1_2.find("svg:tspan", ns)
        if tspan is not None:
            inner_tspan = tspan.find("svg:tspan", ns)
            if inner_tspan is not None:
                inner_tspan.text = wb['team']
            else:
                tspan.text = wb['team']
        else:
            school1_2.text = wb['team']


def update_ids_recursive(element: ET.Element, match_num: int) -> None:
    """Update all id attributes in element tree to be unique for copied matches."""
    if element.get('id'):
        # Update ID to include match number
        old_id = element.get('id')
        # Try to preserve ID structure but make unique
        if old_id and old_id[-1].isdigit():
            # If ID ends with digit, replace with match_num
            new_id = old_id[:-1] + str(match_num)
        else:
            new_id = f"{old_id}_{match_num}"
        element.set('id', new_id)
    
    # Recursively update children
    for child in element:
        update_ids_recursive(child, match_num)


def main():
    parser = argparse.ArgumentParser(
        description="Generate projected top-10 individual matchups for 12-team seeded dual tournament"
    )
    parser.add_argument(
        "--seed-file",
        type=Path,
        required=True,
        help="Path to seed file (format: <seed>,<team_name>)"
    )
    parser.add_argument(
        "--season",
        type=int,
        required=True,
        help="Season year (e.g., 2026)"
    )
    parser.add_argument(
        "--gender",
        choices=["boys", "girls"],
        required=True,
        help="Gender: 'boys' or 'girls'"
    )
    parser.add_argument(
        "--teams-dir",
        type=Path,
        default=Path("frontend/hs-ky-ui/public/data/teams"),
        help="Base directory for team JSON files"
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="mt/rankings_data",
        help="Base directory for rankings data"
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file path (default: print to stdout)"
    )
    parser.add_argument(
        "--template",
        type=Path,
        help="SVG template file path (if provided, generates SVG graphic)"
    )
    parser.add_argument(
        "--svg-output",
        type=Path,
        help="Output SVG file path (required if --template is provided)"
    )
    
    args = parser.parse_args()
    
    if args.template and not args.svg_output:
        parser.error("--svg-output is required when --template is provided")
    
    # Parse seed file
    print(f"Parsing seed file: {args.seed_file}")
    try:
        seeds = parse_seed_file(args.seed_file)
    except Exception as e:
        print(f"ERROR: Failed to parse seed file: {e}")
        return 1
    
    print(f"✓ Loaded {len(seeds)} teams")
    
    # Get tournament name from filename
    tournament_name = args.seed_file.stem
    
    # Load rankings
    print(f"\nLoading rankings for {args.gender} {args.season}...")
    try:
        rankings_by_weight = load_rankings_by_weight(args.season, args.gender, args.data_dir)
    except Exception as e:
        print(f"ERROR: Failed to load rankings: {e}")
        return 1
    
    print(f"✓ Loaded rankings for {len(rankings_by_weight)} weight classes")
    
    # Validate all teams exist
    print(f"\nValidating teams...")
    missing_teams = []
    team_rosters = {}
    
    for seed, team_name in seeds.items():
        roster = load_team_roster(team_name, args.season, args.gender, 
                                 args.teams_dir, rankings_by_weight)
        
        if roster is None:
            missing_teams.append((seed, team_name))
        else:
            team_rosters[team_name] = roster
    
    if missing_teams:
        print(f"\nERROR: Tournament '{tournament_name}' - Teams not found in rankings data:")
        for seed, team_name in missing_teams:
            print(f"  Seed {seed}: '{team_name}'")
        print(f"\nReason: Team names must exactly match team names in rankings data.")
        return 1
    
    print(f"✓ All {len(team_rosters)} teams validated")
    
    # Build bracket
    print(f"\nBuilding bracket...")
    bracket = build_bracket(seeds)
    print(f"✓ Generated {len(bracket)} projected duals")
    
    # Find top-10 matchups for each dual
    print(f"\nFinding top-10 matchups...")
    all_matchups = {}
    weights = get_weights_for_gender(args.gender)
    
    for round_name, team_a, team_b in bracket:
        roster_a = team_rosters.get(team_a)
        roster_b = team_rosters.get(team_b)
        
        if not roster_a or not roster_b:
            continue
        
        matchups = find_top10_matchups(roster_a, roster_b, weights)
        all_matchups[(team_a, team_b)] = matchups
    
    total_matchups = sum(len(m) for m in all_matchups.values())
    print(f"✓ Found {total_matchups} total top-10 matchups")
    
    # Format and output
    output_text = format_output(tournament_name, bracket, all_matchups)
    
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output_text)
        print(f"\n✓ Output written to: {args.output}")
    else:
        print("\n" + "=" * 80)
        print(output_text)
    
    # Generate SVG graphic if template provided
    if args.template:
        print(f"\nGenerating SVG graphic from template...")
        try:
            generate_svg_graphic(args.template, all_matchups, args.svg_output)
        except Exception as e:
            print(f"ERROR: Failed to generate SVG graphic: {e}")
            return 1
    
    return 0


if __name__ == "__main__":
    exit(main())

