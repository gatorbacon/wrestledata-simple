#!/usr/bin/env python3
"""
Generate KY HS Boys/Girls rankings PDF report.

This script generates a PDF report with:
- 14 pages (one per weight class) showing top 40 wrestlers
- 1 team report page showing team rankings based on top 4 per region

Usage:
    python scripts/rankings/print_hs_rankings.py -season 2026 -gender boys
    python scripts/rankings/print_hs_rankings.py -season 2026 -gender girls
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.pdfgen import canvas
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    print("Warning: reportlab not installed. Install with: pip install reportlab")


def load_rankings(rankings_path: Path) -> Dict:
    """Load rankings file."""
    if not rankings_path.exists():
        raise FileNotFoundError(f"Rankings file not found: {rankings_path}")
    
    with open(rankings_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_placement_notes(notes_path: Path) -> Dict[str, Dict]:
    """Load placement notes and return wrestler_id -> note mapping."""
    if not notes_path.exists():
        return {}
    
    with open(notes_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    lookup = {}
    for entry in data.get('notes', []):
        wid = entry.get('wrestler_id')
        note = str(entry.get('note', '')).strip().upper()
        if wid and note:
            lookup[wid] = {
                'note': note,
                'name': entry.get('name', ''),
                'team': entry.get('team', '')
            }
    
    return lookup


def load_team_region_mapping(gender: str) -> Dict[str, str]:
    """
    Load team to region mapping from teams.json file.
    
    Args:
        gender: Gender ('boys' or 'girls')
        
    Returns:
        Dictionary mapping team_name -> region number (as string)
    """
    # Load from teams.json file
    teams_path = Path(f"data/team_lists/hs_ky_{gender}/teams.json")
    if not teams_path.exists():
        return {}
    
    mapping = {}
    with open(teams_path, 'r', encoding='utf-8') as f:
        teams = json.load(f)
        for team in teams:
            team_name = team.get('name', '')
            region = team.get('region')
            if team_name and region:
                mapping[team_name] = str(region)
    
    return mapping


def get_region_for_team(team_name: str, region_mapping: Dict[str, str]) -> str:
    """
    Get region number for a team.
    Returns region number as string, or "?" if not found.
    """
    return region_mapping.get(team_name, "?")


def calculate_region_places(
    top_wrestlers: List[Dict],
    region_mapping: Dict[str, str],
    team_best_wrestler: Dict[str, str]
) -> Dict[str, str]:
    """
    Calculate region place (1-4) for each wrestler based on their rank within their region.
    
    Rules:
    - Only assign region place to highest ranked wrestler per team
    - Within each region, rank wrestlers by their current ranking
    - Assign region place 1-4 based on rank within region (top 4 per region)
    
    Args:
        top_wrestlers: List of wrestler entries (top 40)
        region_mapping: Dictionary mapping team_name -> region number
        team_best_wrestler: Dictionary mapping team -> wrestler_id of highest ranked wrestler
        
    Returns:
        Dictionary mapping wrestler_id -> region_place ("1", "2", "3", "4", or "N/A")
    """
    region_places = {}
    
    # Group wrestlers by region
    wrestlers_by_region = defaultdict(list)  # region -> list of (rank, wrestler_entry)
    
    for entry in top_wrestlers:
        wid = entry.get('wrestler_id', '')
        team = entry.get('team', '')
        rank = entry.get('rank', 9999)
        
        # Only consider highest ranked wrestler per team
        if team_best_wrestler.get(team) != wid:
            region_places[wid] = "N/A"
            continue
        
        # Get region for this team
        region = region_mapping.get(team, '')
        if not region or region == '?':
            region_places[wid] = "N/A"
            continue
        
        wrestlers_by_region[region].append((rank, entry))
    
    # For each region, sort by rank and assign places 1-4
    for region, wrestler_list in wrestlers_by_region.items():
        # Sort by rank (ascending - lower rank number = better)
        wrestler_list.sort(key=lambda x: x[0])
        
        # Assign region places 1-4
        for place_idx, (rank, entry) in enumerate(wrestler_list[:4], start=1):
            wid = entry.get('wrestler_id', '')
            region_places[wid] = str(place_idx)
        
        # Any wrestlers beyond 4th in region get N/A
        for rank, entry in wrestler_list[4:]:
            wid = entry.get('wrestler_id', '')
            region_places[wid] = "N/A"
    
    return region_places


# Standard weight classes for KY HS Boys
KY_HS_BOYS_WEIGHTS = [106, 113, 120, 126, 132, 138, 144, 150, 157, 165, 175, 190, 215, 285]

# Points mapping based on ranking
RANKING_POINTS = {
    1: 20,
    2: 16,
    3: 13.5,
    4: 12.5,
    5: 10,
    6: 9,
    7: 6.5,
    8: 5.5,
    9: 2,
    10: 2,
    11: 2,
    12: 2,
    13: 1,
    14: 1,
    15: 1,
    16: 1,
    17: 0.5,
    18: 0.5,
    19: 0.5,
    20: 0.5,
    21: 0.5,
    22: 0.5,
    23: 0.5,
    24: 0.5,
}


def get_points_for_rank(rank: int) -> float:
    """Get points for a given ranking."""
    return RANKING_POINTS.get(rank, 0.0)


def get_weight_class_data(
    weight_class: str,
    season: int,
    gender: str,
    region_mapping: Dict[str, str],
    top_n: int = 40
) -> Tuple[List[Dict], Dict[str, str], Dict[str, str]]:
    """
    Load and process weight class data.
    
    Returns:
        Tuple of (top_wrestlers, region_places, team_best_wrestler)
    """
    # Setup paths
    data_dir = Path(f"mt/rankings_data/hs_ky_{gender}")
    rankings_path = data_dir / f"rankings_{weight_class}.json"
    
    # Load data
    rankings_data = load_rankings(rankings_path)
    rankings = rankings_data.get('rankings', [])
    
    if not rankings:
        return [], {}, {}
    
    # Get top N wrestlers
    top_wrestlers = rankings[:top_n]
    
    # Determine highest ranked wrestler per team at this weight
    team_best_wrestler = {}  # team -> wrestler_id
    
    for entry in top_wrestlers:
        team = entry.get('team', '')
        rank = entry.get('rank', 9999)
        wid = entry.get('wrestler_id')
        
        if not team or not wid:
            continue
        
        if team not in team_best_wrestler:
            team_best_wrestler[team] = wid
        else:
            # Check if this wrestler is better ranked
            existing_wid = team_best_wrestler[team]
            existing_entry = next((e for e in top_wrestlers if e.get('wrestler_id') == existing_wid), None)
            if existing_entry and rank < existing_entry.get('rank', 9999):
                team_best_wrestler[team] = wid
    
    # Calculate region places based on rank within each region
    region_places = calculate_region_places(top_wrestlers, region_mapping, team_best_wrestler)
    
    return top_wrestlers, region_places, team_best_wrestler


def calculate_team_scores(
    all_weight_data: Dict[str, Tuple[List[Dict], Dict[str, str], Dict[str, str]]],
    region_mapping: Dict[str, str]
) -> List[Tuple[str, float]]:
    """
    Calculate team scores across all weight classes.
    
    Only considers wrestlers who are top 4 in their region (region place 1-4).
    Re-ranks eligible wrestlers sequentially, then awards points.
    
    Returns:
        List of (team_name, total_points) tuples, sorted by points descending
    """
    team_points = defaultdict(float)
    
    # Process each weight class
    for weight_class, (wrestlers, region_places, team_best_wrestler) in all_weight_data.items():
        # Filter to only eligible wrestlers (top 4 in their region)
        eligible_wrestlers = []
        for entry in wrestlers:
            wid = entry.get('wrestler_id', '')
            team = entry.get('team', '')
            
            # Must be highest ranked for their team
            if team_best_wrestler.get(team) != wid:
                continue
            
            # Must be top 4 in their region
            region_place = region_places.get(wid, "N/A")
            if region_place not in ['1', '2', '3', '4']:
                continue
            
            eligible_wrestlers.append(entry)
        
        # Sort eligible wrestlers by original rank
        eligible_wrestlers.sort(key=lambda x: x.get('rank', 9999))
        
        # Re-rank sequentially (1, 2, 3, ...)
        for new_rank, entry in enumerate(eligible_wrestlers, start=1):
            points = get_points_for_rank(new_rank)
            team = entry.get('team', '')
            if team:
                team_points[team] += points
    
    # Sort by points descending
    sorted_teams = sorted(team_points.items(), key=lambda x: x[1], reverse=True)
    return sorted_teams


def main():
    parser = argparse.ArgumentParser(
        description="Print KY HS Boys/Girls rankings report for a weight class."
    )
    parser.add_argument(
        '-season',
        type=int,
        required=True,
        help='Season year (e.g., 2026)'
    )
    parser.add_argument(
        '-gender',
        type=str,
        required=True,
        choices=['boys', 'girls'],
        help='Gender: boys or girls'
    )
    parser.add_argument(
        '-weight',
        type=str,
        required=True,
        help='Weight class (e.g., 106, 113, 190, 285)'
    )
    parser.add_argument(
        '-top',
        type=int,
        default=40,
        help='Number of wrestlers to show (default: 40)'
    )
    
    args = parser.parse_args()
    
    print_rankings_report(
        weight_class=args.weight,
        season=args.season,
        gender=args.gender,
        top_n=args.top
    )


if __name__ == '__main__':
    main()

