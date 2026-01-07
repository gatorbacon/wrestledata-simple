#!/usr/bin/env python3
"""
Generate KY HS Boys/Girls rankings PDF report.

This script generates a PDF report with:
- 14 pages (one per weight class) showing top 40 wrestlers
- 1 team report page showing team rankings based on top 4 per region

Usage:
    python scripts/rankings/generate_hs_rankings_pdf.py -season 2026 -gender boys
    python scripts/rankings/generate_hs_rankings_pdf.py -season 2026 -gender girls
"""

import argparse
import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    print("Warning: reportlab not installed. Install with: pip install reportlab")

try:
    import cairosvg
    from PIL import Image
    CAIROSVG_AVAILABLE = True
except ImportError:
    CAIROSVG_AVAILABLE = False
    print("Warning: cairosvg and/or PIL not installed. JPG generation will be skipped. Install with: pip install cairosvg pillow")


# Standard weight classes for KY HS Boys
KY_HS_BOYS_WEIGHTS = [106, 113, 120, 126, 132, 138, 144, 150, 157, 165, 175, 190, 215, 285]

# Standard weight classes for KY HS Girls
KY_HS_GIRLS_WEIGHTS = [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235]

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


def load_rankings(rankings_path: Path) -> Dict:
    """Load rankings file."""
    if not rankings_path.exists():
        raise FileNotFoundError(f"Rankings file not found: {rankings_path}")
    
    with open(rankings_path, 'r', encoding='utf-8') as f:
        return json.load(f)


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


def get_region_for_team(team_name: str, region_mapping: Dict[str, str], gender: str = 'boys') -> str:
    """
    Get region number for a team.
    Returns region number as-is from the JSON file (already correctly formatted).
    Returns region number as string, or "?" if not found.
    """
    return region_mapping.get(team_name, "?")


def calculate_region_places(
    top_wrestlers: List[Dict],
    region_mapping: Dict[str, str],
    team_best_wrestler: Dict[str, str],
    gender: str = 'boys'
) -> Dict[str, str]:
    """
    Calculate region place (1-4) for each wrestler based on their rank within their region.
    
    Rules:
    - Only assign region place to highest ranked wrestler per team
    - Within each region, rank wrestlers by their current ranking
    - Assign region place 1-4 based on rank within region (top 4 per region)
    - Regions are already correctly formatted in the JSON file (no combination needed)
    
    Args:
        top_wrestlers: List of wrestler entries (top 40 for boys, top 24 for girls)
        region_mapping: Dictionary mapping team_name -> region number
        team_best_wrestler: Dictionary mapping team -> wrestler_id of highest ranked wrestler
        gender: 'boys' or 'girls' (for consistency, but regions are already correct)
        
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
        
        # Get region for this team (already correctly formatted in JSON)
        region = get_region_for_team(team, region_mapping, gender)
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


def get_weight_class_data(
    weight_class: str,
    season: int,
    gender: str,
    region_mapping: Dict[str, str],
    top_n: Optional[int] = None
) -> Tuple[List[Dict], Dict[str, str], Dict[str, str]]:
    """
    Load and process weight class data.
    
    Args:
        weight_class: Weight class string
        season: Season year
        gender: 'boys' or 'girls'
        region_mapping: Dictionary mapping team_name -> region number
        top_n: Number of top wrestlers to return (defaults to 40 for boys, 24 for girls)
    
    Returns:
        Tuple of (top_wrestlers, region_places, team_best_wrestler)
    """
    # Determine top_n based on gender if not specified
    if top_n is None:
        top_n = 24 if gender == 'girls' else 40
    
    # Setup paths
    data_dir = Path(f"mt/rankings_data/hs_ky_{gender}") / str(season)
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
    
    # Calculate region places based on rank within each region (with gender-specific mapping)
    region_places = calculate_region_places(top_wrestlers, region_mapping, team_best_wrestler, gender)
    
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


def truncate_text(text: str, max_length: int) -> str:
    """Truncate text to max_length, adding ellipsis if needed."""
    # If max_length is very large (999), don't truncate
    if max_length >= 999:
        return text
    if len(text) > max_length:
        return text[:max_length-1] + '…'
    return text


def build_rankings_table_data(
    weight_class: str,
    season: int,
    gender: str,
    wrestlers: List[Dict],
    region_places: Dict[str, str],
    team_best_wrestler: Dict[str, str],
    region_mapping: Dict[str, str],
    top_n: int = 40,
    name_max_len: int = 18,
    school_max_len: int = 20
) -> List[List[str]]:
    """Build table data for rankings page with combined Region column."""
    # Header row - blank for Rank, combined Region column
    table_data = [["", "Name", "School", "Region"]]
    
    # Wrestler rows
    for entry in wrestlers[:top_n]:
        rank = entry.get('rank', '')
        name = entry.get('name', 'Unknown')
        team = entry.get('team', 'Unknown')
        wid = entry.get('wrestler_id', '')
        
        # Truncate long names/teams with ellipsis (only if max_len is reasonable)
        name = truncate_text(name, name_max_len)
        team = truncate_text(team, school_max_len)
        
        # Get region (with gender-specific mapping)
        region = get_region_for_team(team, region_mapping, gender)
        
        # Get region place
        region_place = region_places.get(wid, "N/A")
        
        # Combine Region and Region Place into single column
        # Format: "RegionNumber (RegionPlace)" or "RegionNumber (-)" if place is N/A
        if region and region != "?":
            if region_place and region_place != "N/A":
                region_display = f"{region} ({region_place})"
            else:
                region_display = f"{region} (-)"
        else:
            region_display = "-"
        
        table_data.append([
            str(rank),
            name,
            team,
            region_display
        ])
    
    return table_data


def build_team_report_table_data(
    team_scores: List[Tuple[str, float]],
    start_rank: int = 1,
    end_rank: int = 50
) -> List[List[str]]:
    """Build table data for team report page."""
    # Header row
    table_data = [["Rank", "Team", "Points"]]
    
    # Team rows (slice based on start/end rank)
    for rank, (team_name, points) in enumerate(team_scores[start_rank-1:end_rank], start=start_rank):
        # Format points (show .5 as .5, whole numbers as integers)
        points_str = f"{points:.1f}" if points % 1 != 0 else f"{int(points)}"
        table_data.append([
            str(rank),
            team_name,
            points_str
        ])
    
    return table_data


def load_grade_info(weight_class: str, gender: str) -> Dict[str, str]:
    """
    Load grade information for wrestlers from weight_class JSON file.
    
    Returns:
        Dictionary mapping wrestler_id -> grade
    """
    data_dir = Path(f"mt/rankings_data/hs_ky_{gender}")
    weight_class_file = data_dir / f"weight_class_{weight_class}.json"
    
    grade_info = {}
    if weight_class_file.exists():
        with open(weight_class_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            wrestlers = data.get('wrestlers', {})
            for wid, wrestler_data in wrestlers.items():
                grade = wrestler_data.get('grade', '')
                grade_info[wid] = grade if grade else ''
    
    return grade_info


def apply_text_color(element: ET.Element, color: str) -> None:
    """
    Apply a fill color to an SVG text element by updating its style attribute.
    
    Args:
        element: SVG text or tspan element
        color: Color string (e.g., "#000000" or "#BBBBBB")
    """
    style = element.get("style", "")
    style_parts = [p.strip() for p in style.split(";") if p.strip()]
    style_dict = {}
    for part in style_parts:
        if ":" in part:
            k, v = part.split(":", 1)
            style_dict[k.strip()] = v.strip()
    style_dict["fill"] = color
    new_style = ";".join(f"{k}:{v}" for k, v in style_dict.items())
    element.set("style", new_style)


def fill_svg_template(
    template_path: Path,
    weight1: str,
    weight2: str,
    wrestlers1: List[Dict],
    wrestlers2: List[Dict],
    region_mapping: Dict[str, str],
    region_places1: Dict[str, str],
    region_places2: Dict[str, str],
    grade_info1: Dict[str, str],
    grade_info2: Dict[str, str],
    team_best_wrestler1: Dict[str, str],
    team_best_wrestler2: Dict[str, str],
    gender: str = 'boys',
    max_rows: int = 40
) -> ET.Element:
    """
    Fill SVG template with rankings data for two weight classes.
    
    Args:
        template_path: Path to SVG template file
        weight1: First weight class (e.g., "106")
        weight2: Second weight class (e.g., "113")
        wrestlers1: List of wrestler entries for weight1 (top 40 for boys, top 24 for girls)
        wrestlers2: List of wrestler entries for weight2 (top 40 for boys, top 24 for girls)
        region_mapping: Dictionary mapping team_name -> region number
        region_places1: Dictionary mapping wrestler_id -> region_place for weight1
        region_places2: Dictionary mapping wrestler_id -> region_place for weight2
        grade_info1: Dictionary mapping wrestler_id -> grade for weight1
        grade_info2: Dictionary mapping wrestler_id -> grade for weight2
        team_best_wrestler1: Dictionary mapping team -> wrestler_id of highest ranked wrestler for weight1
        team_best_wrestler2: Dictionary mapping team -> wrestler_id of highest ranked wrestler for weight2
        gender: 'boys' or 'girls' (affects region mapping)
        max_rows: Maximum number of rows to fill (40 for boys, 24 for girls)
    
    Returns:
        Modified XML root element
    """
    tree = ET.parse(template_path)
    root = tree.getroot()
    
    # Define namespaces
    ns = {
        "svg": "http://www.w3.org/2000/svg",
        "inkscape": "http://www.inkscape.org/namespaces/inkscape",
    }
    
    # Set weight labels
    weight1_el = root.find(".//svg:text[@inkscape:label='weight_1']", namespaces=ns)
    if weight1_el is not None:
        tspan = weight1_el.find("svg:tspan", ns)
        target = tspan if tspan is not None else weight1_el
        target.text = f"{weight1} lbs"
    
    weight2_el = root.find(".//svg:text[@inkscape:label='weight_2']", namespaces=ns)
    if weight2_el is not None:
        tspan = weight2_el.find("svg:tspan", ns)
        target = tspan if tspan is not None else weight2_el
        target.text = f"{weight2} lbs"
    
    # Fill data for weight1 (max_rows rows)
    for row in range(1, max_rows + 1):
        if row - 1 < len(wrestlers1):
            entry = wrestlers1[row - 1]
            wid = entry.get('wrestler_id', '')
            name = entry.get('name', '')
            team = entry.get('team', '')
            region = get_region_for_team(team, region_mapping, gender)
            region_place = region_places1.get(wid, 'N/A')
            grade = grade_info1.get(wid, '')
            
            # Format region display
            if region and region != '?':
                if region_place and region_place != 'N/A':
                    region_display = f"{region} ({region_place})"
                else:
                    region_display = f"{region} (-)"
            else:
                region_display = "-"
            
            # Check if this wrestler is the highest ranked for their team
            is_highest_ranked = team_best_wrestler1.get(team) == wid
            grey_color = "#BBBBBB" if not is_highest_ranked else "#000000"
            
            # Update name
            name_el = root.find(f".//svg:text[@inkscape:label='name_1_{row}']", namespaces=ns)
            if name_el is not None:
                tspan = name_el.find("svg:tspan", ns)
                target = tspan if tspan is not None else name_el
                target.text = name
                apply_text_color(target, grey_color)
            
            # Update school
            school_el = root.find(f".//svg:text[@inkscape:label='school_1_{row}']", namespaces=ns)
            if school_el is not None:
                tspan = school_el.find("svg:tspan", ns)
                target = tspan if tspan is not None else school_el
                target.text = team
                apply_text_color(target, grey_color)
            
            # Update grade
            grade_el = root.find(f".//svg:text[@inkscape:label='grade_1_{row}']", namespaces=ns)
            if grade_el is not None:
                tspan = grade_el.find("svg:tspan", ns)
                target = tspan if tspan is not None else grade_el
                target.text = grade if grade else ""
                apply_text_color(target, grey_color)
            
            # Update region
            region_el = root.find(f".//svg:text[@inkscape:label='region_1_{row}']", namespaces=ns)
            if region_el is not None:
                tspan = region_el.find("svg:tspan", ns)
                target = tspan if tspan is not None else region_el
                target.text = region_display
                apply_text_color(target, grey_color)
    
    # Fill data for weight2 (max_rows rows)
    for row in range(1, max_rows + 1):
        if row - 1 < len(wrestlers2):
            entry = wrestlers2[row - 1]
            wid = entry.get('wrestler_id', '')
            name = entry.get('name', '')
            team = entry.get('team', '')
            region = get_region_for_team(team, region_mapping, gender)
            region_place = region_places2.get(wid, 'N/A')
            grade = grade_info2.get(wid, '')
            
            # Format region display
            if region and region != '?':
                if region_place and region_place != 'N/A':
                    region_display = f"{region} ({region_place})"
                else:
                    region_display = f"{region} (-)"
            else:
                region_display = "-"
            
            # Check if this wrestler is the highest ranked for their team
            is_highest_ranked = team_best_wrestler2.get(team) == wid
            grey_color = "#BBBBBB" if not is_highest_ranked else "#000000"
            
            # Update name
            name_el = root.find(f".//svg:text[@inkscape:label='name_2_{row}']", namespaces=ns)
            if name_el is not None:
                tspan = name_el.find("svg:tspan", ns)
                target = tspan if tspan is not None else name_el
                target.text = name
                apply_text_color(target, grey_color)
            
            # Update school
            school_el = root.find(f".//svg:text[@inkscape:label='school_2_{row}']", namespaces=ns)
            if school_el is not None:
                tspan = school_el.find("svg:tspan", ns)
                target = tspan if tspan is not None else school_el
                target.text = team
                apply_text_color(target, grey_color)
            
            # Update grade
            grade_el = root.find(f".//svg:text[@inkscape:label='grade_2_{row}']", namespaces=ns)
            if grade_el is not None:
                tspan = grade_el.find("svg:tspan", ns)
                target = tspan if tspan is not None else grade_el
                target.text = grade if grade else ""
                apply_text_color(target, grey_color)
            
            # Update region
            region_el = root.find(f".//svg:text[@inkscape:label='region_2_{row}']", namespaces=ns)
            if region_el is not None:
                tspan = region_el.find("svg:tspan", ns)
                target = tspan if tspan is not None else region_el
                target.text = region_display
                apply_text_color(target, grey_color)
    
    return root


def render_svg_to_jpg(svg_path: Path, jpg_path: Path, width: int = 1500, height: int = 1500) -> None:
    """
    Render SVG to JPG using cairosvg.
    
    Args:
        svg_path: Path to SVG file
        jpg_path: Path to output JPG file
        width: Output width in pixels
        height: Output height in pixels
    """
    if not CAIROSVG_AVAILABLE:
        print("Warning: cairosvg/PIL not available. Skipping JPG generation.")
        return
    
    jpg_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Render SVG to PNG in memory, then convert to JPG via Pillow
    png_bytes = cairosvg.svg2png(url=str(svg_path), output_width=width, output_height=height)
    img = Image.open(BytesIO(png_bytes)).convert("RGB")
    img.save(jpg_path, format="JPEG", quality=95)
    print(f"  ✓ JPG generated: {jpg_path}")


def generate_svg_graphics(
    season: int,
    gender: str,
    all_weight_data: Dict[str, Tuple[List[Dict], Dict[str, str], Dict[str, str]]],
    region_mapping: Dict[str, str],
    output_dir: Path,
    data_dir: Path
) -> None:
    """
    Generate SVG/JPG graphics from template for all weight classes.
    
    Args:
        season: Season year
        gender: Gender ('boys' or 'girls')
        all_weight_data: Dictionary mapping weight_class -> (wrestlers, region_places, team_best_wrestler)
        region_mapping: Dictionary mapping team_name -> region number
        output_dir: Output directory for JPG files
    """
    # Select template based on gender
    if gender == 'boys':
        template_path = Path("mt/graphics/templates/top40v1-boys.svg")
        max_rows = 40
    else:
        template_path = Path("mt/graphics/templates/top40v1-girls.svg")
        max_rows = 24
    
    if not template_path.exists():
        print(f"Warning: SVG template not found: {template_path}")
        print("Skipping SVG graphics generation.")
        return
    
    if not CAIROSVG_AVAILABLE:
        print("Warning: cairosvg/PIL not available. Skipping SVG graphics generation.")
        return
    
    # Get weight classes list based on gender
    if gender == 'boys':
        weight_classes = [str(w) for w in KY_HS_BOYS_WEIGHTS]
    else:
        weight_classes = [str(w) for w in KY_HS_GIRLS_WEIGHTS]
    
    # Generate date string for filename
    date_str = datetime.now().strftime("%Y%m%d")
    
    # Process weight classes in pairs
    for i in range(0, len(weight_classes), 2):
        weight1 = weight_classes[i]
        
        # Get data for weight1
        if weight1 not in all_weight_data:
            continue
        
        wrestlers1, region_places1, team_best_wrestler1 = all_weight_data[weight1]
        grade_info1 = load_grade_info(weight1, gender)
        
        # Check if there's a second weight class
        if i + 1 < len(weight_classes):
            weight2 = weight_classes[i + 1]
            
            # Get data for weight2
            if weight2 not in all_weight_data:
                continue
            
            wrestlers2, region_places2, team_best_wrestler2 = all_weight_data[weight2]
            grade_info2 = load_grade_info(weight2, gender)
            
            # Fill SVG template
            root = fill_svg_template(
                template_path,
                weight1,
                weight2,
                wrestlers1,
                wrestlers2,
                region_mapping,
                region_places1,
                region_places2,
                grade_info1,
                grade_info2,
                team_best_wrestler1,
                team_best_wrestler2,
                gender=gender,
                max_rows=max_rows
            )
            
            # Save temporary SVG
            temp_svg = output_dir / f"temp_top40_{weight1}_{weight2}.svg"
            tree = ET.ElementTree(root)
            tree.write(temp_svg, encoding="utf-8", xml_declaration=True)
            
            # Generate JPG filename
            jpg_filename = f"hs_top40_{gender}_{date_str}_{weight1}_{weight2}.jpg"
            jpg_path = output_dir / jpg_filename
            
            # Render to JPG
            render_svg_to_jpg(temp_svg, jpg_path, width=1500, height=1500)
            
            # Clean up temporary SVG
            temp_svg.unlink()
            
            print(f"  Generated: {jpg_filename}")
        else:
            # Only one weight class left - skip (template requires two)
            print(f"  Skipping {weight1} (no pair available)")


def generate_pdf_report(
    season: int,
    gender: str,
    output_path: Path
):
    """Generate PDF report with all weight classes and team report."""
    if not REPORTLAB_AVAILABLE:
        raise ImportError("reportlab is required. Install with: pip install reportlab")
    
    # Load region mapping
    region_mapping = load_team_region_mapping(gender)
    
    # Debug: Print region mapping status
    if not region_mapping:
        print(f"Warning: No region mapping found for {gender}. Teams may not have region data in teams.json.")
        print(f"  Expected file: data/team_lists/hs_ky_{gender}/teams.json")
        print(f"  You may need to re-scrape teams to populate region data.")
    else:
        print(f"Loaded region mapping for {len(region_mapping)} teams")
    
    # Smaller page size for dense layout - make it compact
    # Use a smaller custom size that fits the content better
    page_size = (612, 792)  # Standard letter size (8.5x11 inches)
    
    # Create PDF with minimal margins
    doc = SimpleDocTemplate(str(output_path), pagesize=page_size,
                           leftMargin=20, rightMargin=20,
                           topMargin=20, bottomMargin=20)
    story = []
    styles = getSampleStyleSheet()
    
    # Reduce leading (line height) for denser vertical spacing
    # Set leading to fontSize + 1 for tight spacing
    body_style = styles["Normal"]
    body_style.leading = body_style.fontSize + 1
    
    # Color scheme
    header_color = colors.HexColor('#1a237e')  # Dark blue
    accent_color = colors.HexColor('#ffc107')  # Gold/amber
    light_bg = colors.HexColor('#e3f2fd')  # Light blue
    dark_text = colors.HexColor('#212121')  # Dark grey
    
    # Create custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=header_color,
        spaceAfter=6,
        alignment=1,  # Center
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=11,
        textColor=dark_text,
        spaceAfter=8,
        alignment=1  # Center
    )
    
    # Load data for all weight classes
    all_weight_data = {}
    # Get weight classes based on gender
    if gender == 'boys':
        weights = KY_HS_BOYS_WEIGHTS
    else:
        # For girls, use the standard girls weights
        weights = [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235]
    
    print(f"Loading data for {len(weights)} weight classes...")
    for weight_class in weights:
        weight_str = str(weight_class)
        try:
            wrestlers, region_places, team_best_wrestler = get_weight_class_data(
                weight_str, season, gender, region_mapping, top_n=40
            )
            if wrestlers:
                all_weight_data[weight_str] = (wrestlers, region_places, team_best_wrestler)
                print(f"  Loaded {weight_class}: {len(wrestlers)} wrestlers")
        except FileNotFoundError:
            print(f"  Skipping {weight_class}: rankings file not found")
    
    if not all_weight_data:
        raise ValueError("No weight class data found!")
    
    # Calculate team scores
    print("\nCalculating team scores...")
    team_scores = calculate_team_scores(all_weight_data, region_mapping)
    print(f"  Calculated scores for {len(team_scores)} teams")
    
    # Generate pages with TWO tables side-by-side
    weight_classes = sorted(all_weight_data.keys(), key=lambda x: int(x))
    
    # Calculate column widths for side-by-side layout
    # Each table gets half the page width minus gutter
    gutter = 10  # Space between columns
    available_width = page_size[0] - 40  # Total width minus margins
    table_width = (available_width - gutter) / 2  # Each table gets half
    
    # Column widths with Name getting most space, numeric columns tight
    # Now 4 columns: Rank (blank header), Name, School, Region (combined)
    col_widths = [
        0.06 * table_width,   # Rank - very narrow (6%)
        0.45 * table_width,    # Name - wide (45%)
        0.32 * table_width,    # School - medium (32%)
        0.17 * table_width,    # Region (combined) - narrow but readable (17%)
    ]
    
    # Track which column we're filling (left=0, right=1)
    current_column = 0
    left_table_elements = []
    right_table_elements = []
    
    def create_table_for_weight(weight_class, wrestlers, region_places, team_best_wrestler, table_width, col_widths):
        """Create table elements (label + table) for a weight class."""
        # Determine top_n based on gender (24 for girls, 40 for boys)
        top_n_for_table = 24 if gender == 'girls' else 40
        # Build table data WITHOUT truncation - let column width handle it
        table_data = build_rankings_table_data(
            weight_class, season, gender,
            wrestlers, region_places, team_best_wrestler, region_mapping, 
            top_n=top_n_for_table, name_max_len=999, school_max_len=999  # No truncation
        )
        
        # Create table
        t = Table(table_data, colWidths=col_widths, repeatRows=1)
        
        # Style: black and white only, dense with larger fonts
        table_style = TableStyle([
            # Headers - bold black, larger font
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),  # Rank centered
            ('ALIGN', (1, 0), (2, -1), 'LEFT'),    # Name, School left
            ('ALIGN', (3, 0), (3, -1), 'CENTER'),  # Region (combined) centered
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
            ('TOPPADDING', (0, 0), (-1, 0), 2),
            ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.black),
            # Data rows - larger font, minimal padding
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('TOPPADDING', (0, 1), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 2),
            # Allow word wrapping for Name/School if needed
            ('WORDWRAP', (1, 0), (2, -1), True),  # Name and School can wrap if absolutely necessary
            ('WORDWRAP', (0, 0), (0, -1), False),  # Rank no wrap
            ('WORDWRAP', (3, 0), (3, -1), False),  # Region no wrap
        ])
        
        # Apply grey color to non-starter rows
        # Use top_n based on gender (24 for girls, 40 for boys)
        top_n_for_table = 24 if gender == 'girls' else 40
        for i, entry in enumerate(wrestlers[:top_n_for_table], start=1):
            wid = entry.get('wrestler_id', '')
            team = entry.get('team', '')
            is_highest_ranked = team_best_wrestler.get(team) == wid
            if not is_highest_ranked:
                table_style.add('TEXTCOLOR', (0, i), (-1, i), colors.HexColor('#BBBBBB'))
        
        t.setStyle(table_style)
        
        # Create weight class label - slightly larger
        weight_label_style = ParagraphStyle(
            'WeightLabel',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.black,
            spaceAfter=0,
            alignment=1,
            fontName='Helvetica-Bold'
        )
        
        weight_label_table = Table([[Paragraph(f"{weight_class} lbs", weight_label_style)]], colWidths=[table_width])
        weight_label_table_style = TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.black),
        ])
        weight_label_table.setStyle(weight_label_table_style)
        
        return weight_label_table, t
    
    # Process each weight class, placing two side-by-side
    # Merge data into single table with 10 columns (5 per weight) for side-by-side display
    for i in range(0, len(weight_classes), 2):
        weight1 = weight_classes[i]
        weight2 = weight_classes[i + 1] if i + 1 < len(weight_classes) else None
        
        # Determine top_n based on gender (24 for girls, 40 for boys)
        top_n_for_table = 24 if gender == 'girls' else 40
        
        # Get data for first weight
        wrestlers1, region_places1, team_best_wrestler1 = all_weight_data[weight1]
        table_data1 = build_rankings_table_data(
            weight1, season, gender,
            wrestlers1, region_places1, team_best_wrestler1, region_mapping, 
            top_n=top_n_for_table, name_max_len=16, school_max_len=18
        )
        
        if weight2:
            # Get data for second weight - no truncation
            wrestlers2, region_places2, team_best_wrestler2 = all_weight_data[weight2]
            table_data2 = build_rankings_table_data(
                weight2, season, gender,
                wrestlers2, region_places2, team_best_wrestler2, region_mapping, 
                top_n=top_n_for_table, name_max_len=999, school_max_len=999  # No truncation
            )
            
            # Merge into single table with 8 columns (4 per weight)
            combined_data = []
            max_rows = max(len(table_data1), len(table_data2))
            
            # Header row: combine both headers
            combined_data.append(table_data1[0] + table_data2[0])
            
            # Data rows: combine both
            for row_idx in range(1, max_rows):
                left_row = table_data1[row_idx] if row_idx < len(table_data1) else [''] * 4
                right_row = table_data2[row_idx] if row_idx < len(table_data2) else [''] * 4
                combined_data.append(left_row + right_row)
            
            # Combined column widths
            combined_col_widths = col_widths + col_widths
            
            # Create combined table
            combined_table = Table(combined_data, colWidths=combined_col_widths, repeatRows=1)
            
            # Style: black and white, dense, with vertical divider, larger fonts
            combined_style = TableStyle([
                # Headers - bold black, larger font
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),  # Rank 1 centered
                ('ALIGN', (1, 0), (2, -1), 'LEFT'),    # Name 1, School 1 left
                ('ALIGN', (3, 0), (3, -1), 'CENTER'),  # Region 1 (combined) centered
                ('ALIGN', (4, 0), (4, -1), 'CENTER'),  # Rank 2 centered
                ('ALIGN', (5, 0), (6, -1), 'LEFT'),    # Name 2, School 2 left
                ('ALIGN', (7, 0), (7, -1), 'CENTER'),  # Region 2 (combined) centered
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
                ('TOPPADDING', (0, 0), (-1, 0), 2),
                ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.black),
                # Vertical divider between the two weight classes
                ('LINEAFTER', (3, 0), (3, -1), 0.5, colors.black),
                # Data rows - larger font, minimal padding
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 2),
                ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                ('TOPPADDING', (0, 1), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 2),
                # Allow wrapping for Name/School columns only
                ('WORDWRAP', (1, 0), (2, -1), True),  # Name 1, School 1 can wrap
                ('WORDWRAP', (5, 0), (6, -1), True),  # Name 2, School 2 can wrap
                ('WORDWRAP', (0, 0), (0, -1), False),  # Rank columns no wrap
                ('WORDWRAP', (3, 0), (3, -1), False),  # Region columns no wrap
                ('WORDWRAP', (4, 0), (4, -1), False),  # Rank 2 no wrap
                ('WORDWRAP', (7, 0), (7, -1), False),  # Region 2 no wrap
            ])
            
            # Apply grey color to non-starter rows for left table
            num_rows_left = min(len(wrestlers1), top_n_for_table)
            for row_idx, entry in enumerate(wrestlers1[:num_rows_left], start=1):
                wid = entry.get('wrestler_id', '')
                team = entry.get('team', '')
                is_highest_ranked = team_best_wrestler1.get(team) == wid
                if not is_highest_ranked:
                    combined_style.add('TEXTCOLOR', (0, row_idx), (3, row_idx), colors.HexColor('#BBBBBB'))
            
            # Apply grey color to non-starter rows for right table
            num_rows_right = min(len(wrestlers2), top_n_for_table)
            for row_idx, entry in enumerate(wrestlers2[:num_rows_right], start=1):
                wid = entry.get('wrestler_id', '')
                team = entry.get('team', '')
                is_highest_ranked = team_best_wrestler2.get(team) == wid
                if not is_highest_ranked:
                    combined_style.add('TEXTCOLOR', (4, row_idx), (7, row_idx), colors.HexColor('#BBBBBB'))
            
            combined_table.setStyle(combined_style)
            
            # Create weight labels side-by-side - slightly larger
            weight_label_style = ParagraphStyle(
                'WeightLabel',
                parent=styles['Normal'],
                fontSize=10,
                textColor=colors.black,
                spaceAfter=0,
                alignment=1,
                fontName='Helvetica-Bold'
            )
            
            label_table = Table([
                [Paragraph(f"{weight1} lbs", weight_label_style), Paragraph(f"{weight2} lbs", weight_label_style)]
            ], colWidths=[table_width, table_width])
            label_table_style = TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.black),
                ('LINEAFTER', (0, 0), (0, -1), 0.5, colors.black),
                ('LEFTPADDING', (0, 0), (0, -1), 0),
                ('RIGHTPADDING', (0, 0), (0, -1), gutter),
                ('LEFTPADDING', (1, 0), (1, -1), gutter),
                ('RIGHTPADDING', (1, 0), (1, -1), 0),
            ])
            label_table.setStyle(label_table_style)
            
            story.append(label_table)
            story.append(combined_table)
        else:
            # Only one weight left - create single table
            wrestlers1, region_places1, team_best_wrestler1 = all_weight_data[weight1]
            label1, table1 = create_table_for_weight(
                weight1, wrestlers1, region_places1, team_best_wrestler1, table_width, col_widths
            )
            story.append(label1)
            story.append(table1)
        
        story.append(PageBreak())
    
    # Team report page
    team_title_style = ParagraphStyle(
        'TeamTitle',
        parent=styles['Heading1'],
        fontSize=22,
        textColor=colors.black,
        spaceAfter=8,
        alignment=1,  # Center
        fontName='Helvetica-Bold'
    )
    
    team_subtitle_style = ParagraphStyle(
        'TeamSubtitle',
        parent=styles['Normal'],
        fontSize=12,
        textColor=colors.black,
        spaceAfter=12,
        alignment=1  # Center
    )
    
    title = Paragraph(f"KY HS {gender.capitalize()} Team Rankings", team_title_style)
    story.append(title)
    
    subtitle = Paragraph(f"Season {season} - Based on Top 4 Per Region", team_subtitle_style)
    story.append(subtitle)
    
    story.append(Spacer(1, 0.1*inch))
    
    # Split teams into two tables: 1-25 (left) and 26-50 (right)
    teams_left = team_scores[0:25]
    teams_right = team_scores[25:50]
    
    # Build table data for both sides
    team_table_data_left = build_team_report_table_data(teams_left, start_rank=1, end_rank=25)
    team_table_data_right = build_team_report_table_data(teams_right, start_rank=26, end_rank=50)
    
    # Calculate column widths for side-by-side layout (matching wrestler rankings density)
    gutter = 25  # Increased space between tables (was 10, now 25 for 10-15pt more)
    available_width = page_size[0] - 40  # Total width minus minimal margins
    table_width = (available_width - gutter) / 2  # Each table gets half
    
    # Tight column widths for team tables (reduced Team width by ~18%)
    team_col_widths = [
        0.08 * table_width,   # Rank (minimal, just enough for 2 digits)
        0.57 * table_width,   # Team Name (reduced from 0.70 to 0.57, ~18% reduction)
        0.35 * table_width,   # Points (increased slightly to compensate)
    ]
    
    # Merge both tables into a single combined table (like wrestler rankings)
    # This ensures both tables render correctly side-by-side
    combined_data = []
    max_rows = max(len(team_table_data_left), len(team_table_data_right))
    
    # Header row: combine both headers
    combined_data.append(team_table_data_left[0] + team_table_data_right[0])
    
    # Data rows: combine both
    for row_idx in range(1, max_rows):
        left_row = team_table_data_left[row_idx] if row_idx < len(team_table_data_left) else [''] * 3
        right_row = team_table_data_right[row_idx] if row_idx < len(team_table_data_right) else [''] * 3
        combined_data.append(left_row + right_row)
    
    # Combined column widths (3 columns for left table + 3 columns for right table)
    combined_col_widths = team_col_widths + team_col_widths
    
    # Create combined table
    combined_table = Table(combined_data, colWidths=combined_col_widths, repeatRows=1)
    
    # Style: dense, matching wrestler rankings density
    combined_style = TableStyle([
        # Headers - bold black, compact
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),  # Rank 1 centered
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),    # Team 1 left-aligned
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),   # Points 1 right-aligned
        ('ALIGN', (3, 0), (3, -1), 'CENTER'),  # Rank 2 centered
        ('ALIGN', (4, 0), (4, -1), 'LEFT'),    # Team 2 left-aligned
        ('ALIGN', (5, 0), (5, -1), 'RIGHT'),   # Points 2 right-aligned
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
        ('TOPPADDING', (0, 0), (-1, 0), 2),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.black),
        # Vertical divider between the two tables
        ('LINEAFTER', (2, 0), (2, -1), 0.5, colors.black),
        # Data rows - dense spacing matching wrestler tables
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 1), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 2),
    ])
    
    combined_table.setStyle(combined_style)
    story.append(combined_table)
    
    # Generate SVG graphics before building PDF
    print(f"\nGenerating SVG graphics...")
    output_dir = output_path.parent
    # Determine data directory for grade info
    if gender == 'boys':
        data_dir = Path("mt/rankings_data/hs_ky_boys") / str(season)
    else:
        data_dir = Path("mt/rankings_data/hs_ky_girls") / str(season)
    generate_svg_graphics(season, gender, all_weight_data, region_mapping, output_dir, data_dir)
    
    # Build PDF
    print(f"\nGenerating PDF: {output_path}")
    doc.build(story)
    num_ranking_pages = len(all_weight_data)  # One weight per page
    print(f"✓ PDF generated: {output_path}")
    print(f"  Ranking pages: {num_ranking_pages} (1 weight class per page)")
    print(f"  Team report page: 1")
    print(f"  Total pages: {num_ranking_pages + 1}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate KY HS Boys/Girls rankings PDF report."
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
        '-output',
        type=str,
        help='Output PDF file path (default: mt/graphics/{season}/hs_rankings_{gender}_{season}.pdf)'
    )
    
    args = parser.parse_args()
    
    if not REPORTLAB_AVAILABLE:
        print("Error: reportlab is required. Install with: pip install reportlab")
        return
    
    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_dir = Path(f"mt/graphics/{args.season}")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"hs_rankings_{args.gender}_{args.season}.pdf"
    
    generate_pdf_report(
        season=args.season,
        gender=args.gender,
        output_path=output_path
    )


if __name__ == '__main__':
    main()

