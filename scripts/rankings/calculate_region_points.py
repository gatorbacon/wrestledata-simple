#!/usr/bin/env python3
"""
Calculate total team points scored per region for state tournament.

Outputs:
- Total team points by region
- Top 3 teams scoring for each region
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple


# xTP_simple scoring table (KHSAA-style, simplified rank-based)
# "Projected points are based on statewide rank."
XTP_SIMPLE_POINTS = {
    1: 30.0,
    2: 24.0,
    3: 21.0,
    4: 19.0,
    5: 15.0,
    6: 13.5,
    7: 10.5,
    8: 8.5,
    9: 3.0,
    10: 3.0,
    11: 3.0,
    12: 3.0,
    13: 2.5,
    14: 2.5,
    15: 2.5,
    16: 2.5,
    17: 0.5,
    18: 0.5,
    19: 0.5,
    20: 0.5,
    21: 0.5,
    22: 0.5,
    23: 0.5,
    24: 0.5,
}


def get_xtp_simple(rank: int) -> float:
    """
    Get xTP_simple points for a given starter rank.
    
    Uses KHSAA-style simplified scoring:
    - Rank 1: 30.0
    - Rank 2: 24.0
    - Rank 3: 21.0
    - Rank 4: 19.0
    - Rank 5: 15.0
    - Rank 6: 13.5
    - Rank 7: 10.5
    - Rank 8: 8.5
    - Ranks 9-12: 3.0
    - Ranks 13-16: 2.5
    - Ranks 17-24: 0.5
    - Ranks 25+ or unranked: 0.0
    
    Args:
        rank: Starter-only statewide rank (1-based)
    
    Returns:
        xTP_simple points
    """
    if rank is None or rank < 1:
        return 0.0
    if rank > 24:
        return 0.0
    return XTP_SIMPLE_POINTS.get(rank, 0.0)


def load_team_region_mapping(gender: str) -> Dict[str, str]:
    """
    Load team to region mapping from teams.json file.
    
    Args:
        gender: Gender ('boys' or 'girls')
        
    Returns:
        Dictionary mapping team_name -> region number (as string)
    """
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


def get_weight_class_data(
    weight_class: str,
    season: int,
    gender: str,
    region_mapping: Dict[str, str],
    data_dir: str = "mt/rankings_data"
) -> Tuple[List[Dict], Dict[str, str], Dict[str, str]]:
    """
    Load rankings for a weight class and calculate region places.
    
    Returns:
        Tuple of (wrestlers, region_places, team_best_wrestler)
    """
    from collections import defaultdict
    
    # Load rankings file - try both naming conventions
    base_path = Path(data_dir) / f"hs_ky_{gender}" / str(season)
    rankings_path = base_path / f"rankings_{weight_class}.json"
    if not rankings_path.exists():
        rankings_path = base_path / f"weight_class_{weight_class}.json"
    
    if not rankings_path.exists():
        return [], {}, {}
    
    with open(rankings_path, 'r', encoding='utf-8') as f:
        rankings_data = json.load(f)
    
    wrestlers = rankings_data.get('rankings', [])
    if not wrestlers:
        return [], {}, {}
    
    # Find best wrestler per team (highest ranked)
    team_best_wrestler = {}
    for entry in wrestlers:
        wid = entry.get('wrestler_id', '')
        team = entry.get('team', '')
        rank = entry.get('rank')
        
        if not wid or not team or rank is None:
            continue
        
        # Only consider starters (highest ranked per team)
        if team not in team_best_wrestler:
            team_best_wrestler[team] = wid
        else:
            # Check if this wrestler is ranked higher
            current_best_entry = next((e for e in wrestlers if e.get('wrestler_id') == team_best_wrestler[team]), None)
            if current_best_entry:
                current_rank = current_best_entry.get('rank', 9999)
                if rank < current_rank:
                    team_best_wrestler[team] = wid
    
    # Calculate region places (top 4 per region)
    region_places = {}
    wrestlers_by_region = defaultdict(list)  # region -> list of (rank, wrestler_entry)
    
    for entry in wrestlers:
        wid = entry.get('wrestler_id', '')
        team = entry.get('team', '')
        rank = entry.get('rank')
        
        if not wid or not team or rank is None:
            region_places[wid] = "N/A"
            continue
        
        # Only consider starters
        if team_best_wrestler.get(team) != wid:
            region_places[wid] = "N/A"
            continue
        
        # Get region for this team
        region = region_mapping.get(team, "")
        if not region:
            region_places[wid] = "N/A"
            continue
        
        wrestlers_by_region[region].append((rank, entry))
    
    # For each region, sort by rank and assign places 1-4
    for region, wrestler_list in wrestlers_by_region.items():
        wrestler_list.sort(key=lambda x: x[0])  # Sort by rank
        
        # Assign region places 1-4
        for place_idx, (rank, entry) in enumerate(wrestler_list[:4], start=1):
            wid = entry.get('wrestler_id', '')
            region_places[wid] = str(place_idx)
        
        # Any wrestlers beyond 4th in region get N/A
        for rank, entry in wrestler_list[4:]:
            wid = entry.get('wrestler_id', '')
            region_places[wid] = "N/A"
    
    return wrestlers, region_places, team_best_wrestler


def calculate_team_scores(
    season: int,
    gender: str,
    region_mapping: Dict[str, str],
    data_dir: str = "mt/rankings_data"
) -> List[Tuple[str, float]]:
    """
    Calculate team scores across all weight classes using xTP_simple.
    
    Uses starter-only rankings and xTP_simple scoring (rank-based points).
    This matches the team profile and team tournament prediction scores exactly.
    
    Returns:
        List of (team_name, total_points) tuples, sorted by points descending
    """
    from collections import defaultdict
    
    # Define weight classes based on gender
    if gender == 'boys':
        weight_classes = ['106', '113', '120', '126', '132', '138', '144', '150', '157', '165', '175', '190', '215', '285']
    else:  # girls
        weight_classes = ['100', '107', '114', '120', '126', '132', '138', '145', '152', '165', '185', '235']
    
    team_points = defaultdict(float)
    
    # Load starter rankings for each weight class
    for weight_class in weight_classes:
        # Load starter-only rankings
        starter_rankings_path = Path("frontend/hs-ky-ui/public/data/rankings") / gender / str(season) / f"rankings_starters_{weight_class}.json"
        
        if not starter_rankings_path.exists():
            # Fall back to regular rankings
            base_path = Path(data_dir) / f"hs_ky_{gender}" / str(season)
            rankings_path = base_path / f"rankings_{weight_class}.json"
            if not rankings_path.exists():
                continue
            
            with open(rankings_path, 'r', encoding='utf-8') as f:
                rankings_data = json.load(f)
            wrestlers = rankings_data.get('rankings', [])
            
            # Filter to starters only (highest ranked per team)
            team_best = {}
            for entry in wrestlers:
                team = entry.get('team', '')
                rank = entry.get('rank')
                if team and rank is not None:
                    if team not in team_best or rank < team_best[team].get('rank', 9999):
                        team_best[team] = entry
            
            # Award points based on original rank (xTP_simple)
            for team, entry in team_best.items():
                rank = entry.get('rank')
                if rank is not None:
                    points = get_xtp_simple(rank)
                    team_points[team] += points
        else:
            # Use starter-only rankings (preferred)
            with open(starter_rankings_path, 'r', encoding='utf-8') as f:
                starter_data = json.load(f)
            
            starters = starter_data.get('rankings', [])
            
            # Award points based on starter rank (xTP_simple)
            for entry in starters:
                team = entry.get('team', '')
                rank = entry.get('rank')  # This is the re-ranked starter-only rank
                
                if team and rank is not None:
                    points = get_xtp_simple(rank)
                    team_points[team] += points
    
    # Sort by points descending
    sorted_teams = sorted(team_points.items(), key=lambda x: x[1], reverse=True)
    return sorted_teams


def main():
    parser = argparse.ArgumentParser(
        description="Calculate total team points scored per region for state tournament"
    )
    parser.add_argument(
        "--season",
        type=int,
        required=True,
        help="Season year (e.g., 2026)"
    )
    parser.add_argument(
        "--gender",
        type=str,
        required=True,
        choices=["boys", "girls"],
        help="Gender (boys or girls)"
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="mt/rankings_data",
        help="Data directory (default: mt/rankings_data)"
    )
    parser.add_argument(
        "--generate-graphic",
        action="store_true",
        help="Generate SVG/JPG graphic of region scoring results"
    )
    
    args = parser.parse_args()
    
    print(f"\n{'='*80}")
    print(f"Region Team Points Analysis - {args.gender.title()} {args.season}")
    print(f"{'='*80}\n")
    
    # Load region mapping
    print("Loading team region mapping...")
    region_mapping = load_team_region_mapping(args.gender)
    if not region_mapping:
        print(f"Error: No region mapping found for {args.gender}")
        print(f"Expected file: data/team_lists/hs_ky_{args.gender}/teams.json")
        return
    
    print(f"Loaded region mapping for {len(region_mapping)} teams\n")
    
    # Calculate team scores
    print("Calculating team points...")
    team_scores = calculate_team_scores(args.season, args.gender, region_mapping, args.data_dir)
    print(f"Calculated scores for {len(team_scores)} teams\n")
    
    # Group teams by region and sum points
    region_totals = defaultdict(float)
    teams_by_region = defaultdict(list)
    
    for team_name, points in team_scores:
        region = region_mapping.get(team_name, "Unknown")
        region_totals[region] += points
        teams_by_region[region].append((team_name, points))
    
    # Sort regions by total points
    sorted_regions = sorted(region_totals.items(), key=lambda x: x[1], reverse=True)
    
    # Print results
    print(f"{'='*80}")
    print("TOTAL TEAM POINTS BY REGION")
    print(f"{'='*80}\n")
    print(f"{'Region':<10} {'Total Points':<15}")
    print("-" * 25)
    
    for region, total_points in sorted_regions:
        print(f"{region:<10} {total_points:<15.1f}")
    
    print(f"\n{'='*80}")
    print("TOP 3 TEAMS BY REGION")
    print(f"{'='*80}\n")
    
    for region, total_points in sorted_regions:
        teams = teams_by_region[region]
        # Sort teams by points (already sorted, but ensure)
        teams.sort(key=lambda x: x[1], reverse=True)
        top_3 = teams[:3]
        
        print(f"Region {region} (Total: {total_points:.1f} points)")
        print("-" * 50)
        for idx, (team_name, points) in enumerate(top_3, start=1):
            print(f"  {idx}. {team_name:<35} {points:>6.1f} points")
        print()
    
    print(f"{'='*80}\n")
    
    # Generate graphic if requested
    if args.generate_graphic:
        generate_region_scoring_graphic(
            sorted_regions,
            teams_by_region,
            args.season,
            args.gender
        )


def generate_region_scoring_graphic(
    sorted_regions: List[Tuple[str, float]],
    teams_by_region: Dict[str, List[Tuple[str, float]]],
    season: int,
    gender: str
) -> None:
    """
    Generate SVG/JPG graphic showing region scoring results.
    
    For boys: Uses region_scoring_template2.svg (8 regions)
    For girls: Uses region_scoring_template-girls.svg (4 regions)
    """
    import xml.etree.ElementTree as ET
    from pathlib import Path
    
    try:
        import cairosvg
        from PIL import Image
        from io import BytesIO
        CAIROSVG_AVAILABLE = True
    except ImportError:
        CAIROSVG_AVAILABLE = False
        print("Warning: cairosvg/PIL not available. Skipping graphic generation.")
        return
    
    # Select template based on gender
    if gender == 'girls':
        template_path = Path("mt/graphics/templates/region_scoring_template-girls.svg")
        max_regions = 4
    else:  # boys
        template_path = Path("mt/graphics/templates/region_scoring_template2.svg")
        max_regions = 8
    
    if not template_path.exists():
        print(f"Warning: Template not found: {template_path}")
        return
    
    tree = ET.parse(template_path)
    root = tree.getroot()
    
    # Define namespaces
    ns = {
        "svg": "http://www.w3.org/2000/svg",
        "inkscape": "http://www.inkscape.org/namespaces/inkscape",
    }
    
    # Process each region (up to max_regions)
    for region_idx in range(1, max_regions + 1):
        if region_idx - 1 >= len(sorted_regions):
            # No more regions, leave template values as-is or clear them
            continue
        
        region, total_points = sorted_regions[region_idx - 1]
        
        # Update region number (reg1, reg2, ..., reg8)
        region_el = root.find(f".//svg:text[@inkscape:label='reg{region_idx}']", namespaces=ns)
        if region_el is not None:
            tspan = region_el.find("svg:tspan", ns)
            target = tspan if tspan is not None else region_el
            target.text = f"REGION {region}"
        
        # Update total region score (reg1_score, reg2_score, ..., reg8_score)
        # Format: "Total: <points> pts"
        total_score_el = root.find(f".//svg:text[@inkscape:label='reg{region_idx}_score']", namespaces=ns)
        if total_score_el is not None:
            tspan = total_score_el.find("svg:tspan", ns)
            target = tspan if tspan is not None else total_score_el
            target.text = f"Total: {total_points:.1f} pts"
        
        # Get top 3 teams for this region
        teams = teams_by_region[region]
        teams.sort(key=lambda x: x[1], reverse=True)
        top_3 = teams[:3]
        
        # Update team names and scores (reg1_team1, reg1_team2, reg1_team3, etc.)
        for team_idx in range(1, 4):
            if team_idx - 1 < len(top_3):
                team_name, team_points = top_3[team_idx - 1]
            else:
                # No team at this position, leave empty or use placeholder
                team_name = ""
                team_points = 0.0
            
            # Update team name (reg1_team1, reg1_team2, reg1_team3, etc.)
            team_el = root.find(f".//svg:text[@inkscape:label='reg{region_idx}_team{team_idx}']", namespaces=ns)
            if team_el is not None:
                tspan = team_el.find("svg:tspan", ns)
                target = tspan if tspan is not None else team_el
                target.text = team_name
            
            # Update team score (reg1_score1, reg1_score2, reg1_score3, etc.)
            score_el = root.find(f".//svg:text[@inkscape:label='reg{region_idx}_score{team_idx}']", namespaces=ns)
            if score_el is not None:
                tspan = score_el.find("svg:tspan", ns)
                target = tspan if tspan is not None else score_el
                if team_name:  # Only show score if there's a team
                    target.text = f"{team_points:.1f}"
                else:
                    target.text = ""
    
    # Save SVG
    output_dir = Path(f"mt/graphics/{season}")
    output_dir.mkdir(parents=True, exist_ok=True)
    svg_path = output_dir / f"region_scoring_{gender}_{season}.svg"
    tree.write(svg_path, encoding="utf-8", xml_declaration=True)
    print(f"✓ SVG generated: {svg_path}")
    
    # Convert to JPG
    jpg_path = output_dir / f"region_scoring_{gender}_{season}.jpg"
    
    # Try Inkscape first (better SVG filter support, including shadows)
    import subprocess
    import shutil
    
    # Try to find Inkscape - check PATH first, then common macOS installation paths
    inkscape_path = shutil.which("inkscape")
    if not inkscape_path:
        # Check common macOS installation paths
        mac_paths = [
            "/Applications/Inkscape.app/Contents/MacOS/inkscape",
            "/usr/local/bin/inkscape",
            "/opt/homebrew/bin/inkscape",
        ]
        for path in mac_paths:
            if Path(path).exists():
                inkscape_path = path
                break
    if inkscape_path:
        try:
            # Use Inkscape to export PNG, then convert to JPG
            png_temp = jpg_path.with_suffix('.png')
            subprocess.run(
                [
                    inkscape_path,
                    str(svg_path),
                    "--export-filename", str(png_temp),
                    "--export-type=png",
                    f"--export-width=2000",
                    f"--export-height=2000"
                ],
                check=True,
                capture_output=True
            )
            # Convert PNG to JPG
            img = Image.open(png_temp).convert("RGB")
            img.save(jpg_path, format="JPEG", quality=95)
            png_temp.unlink()  # Clean up temp PNG
            print(f"✓ JPG generated (via Inkscape): {jpg_path}")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            # Fall back to cairosvg if Inkscape fails
            print(f"  Note: Inkscape conversion failed, using cairosvg (filters may not render): {e}")
            png_bytes = cairosvg.svg2png(url=str(svg_path), output_width=2000, output_height=2000)
            img = Image.open(BytesIO(png_bytes)).convert("RGB")
            img.save(jpg_path, format="JPEG", quality=95)
            print(f"✓ JPG generated (via cairosvg): {jpg_path}")
    else:
        # No Inkscape available, use cairosvg
        print("  Note: Inkscape not found. Using cairosvg (SVG filters like shadows may not render).")
        print("  To enable shadow rendering, install Inkscape: https://inkscape.org/")
        png_bytes = cairosvg.svg2png(url=str(svg_path), output_width=2000, output_height=2000)
        img = Image.open(BytesIO(png_bytes)).convert("RGB")
        img.save(jpg_path, format="JPEG", quality=95)
        print(f"✓ JPG generated (via cairosvg): {jpg_path}")


if __name__ == "__main__":
    main()

