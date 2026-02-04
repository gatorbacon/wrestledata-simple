#!/usr/bin/env python3
"""
create_rankings_release.py

Creates official rankings releases with multiple output formats:
- Archive JSON files for frontend (with movement tracking)
- PDF reports
- SVG/JPG graphics

This script:
1. Loads full rankings from mt/rankings_data (source of truth)
2. Enriches with region data, region places, and movement indicators
3. Generates archive JSON files (optional)
4. Generates PDF reports (optional)
5. Generates SVG/JPG graphics (optional)

CRITICAL: This script is READ-ONLY with respect to ranking order.
It NEVER modifies rankings order, filters beyond top-N limits, or infers editorial intent.

Usage:
    # Generate all outputs
    python scripts/rankings/create_rankings_release.py -season 2026 -gender boys -drop-id 2026-01-09 --archive --pdf --jpg
    
    # Generate just archive
    python scripts/rankings/create_rankings_release.py -season 2026 -gender boys -drop-id 2026-01-09 --archive
    
    # Generate just PDF and JPG
    python scripts/rankings/create_rankings_release.py -season 2026 -gender boys --pdf --jpg
"""

import argparse
import json
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
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
    print("Warning: reportlab not installed. PDF generation will be skipped. Install with: pip install reportlab")

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
    1: 20, 2: 16, 3: 13.5, 4: 12.5, 5: 10, 6: 9, 7: 6.5, 8: 5.5,
    9: 2, 10: 2, 11: 2, 12: 2, 13: 1, 14: 1, 15: 1, 16: 1,
    17: 0.5, 18: 0.5, 19: 0.5, 20: 0.5, 21: 0.5, 22: 0.5, 23: 0.5, 24: 0.5,
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
    Returns region number as string, or "-" if not found.
    """
    return region_mapping.get(team_name, "-")


def parse_record(record_str: str) -> Optional[Dict]:
    """
    Parse record string (e.g., "7-0", "12-1") into structured format.
    
    Args:
        record_str: Record string like "7-0" or "12-1"
    
    Returns:
        Dictionary with wins, losses, pct, or None if invalid
    """
    if not record_str:
        return None
    
    # Try to parse "wins-losses" format
    match = re.match(r'^(\d+)-(\d+)$', str(record_str).strip())
    if match:
        wins = int(match.group(1))
        losses = int(match.group(2))
        total = wins + losses
        pct = (wins / total) * 100 if total > 0 else 0.0
        return {
            "wins": wins,
            "losses": losses,
            "pct": pct
        }
    
    return None


def format_record_str(wins: int, losses: int) -> str:
    """
    Format record as string with percentage.
    
    Args:
        wins: Number of wins
        losses: Number of losses
    
    Returns:
        Formatted string like "7-0 (100%)"
    """
    total = wins + losses
    if total == 0:
        return "0-0 (—)"
    
    pct = (wins / total) * 100
    return f"{wins}-{losses} ({pct:.0f}%)"


def load_wrestler_profile(wrestler_id: str, season: int, gender: str) -> Optional[Dict]:
    """
    Load wrestler profile JSON.
    
    Args:
        wrestler_id: Wrestler ID
        season: Season year
        gender: Gender ('boys' or 'girls')
    
    Returns:
        Wrestler profile dict or None if not found
    """
    profile_path = Path(f"frontend/hs-ky-ui/public/data/wrestlers/{gender}") / str(season) / "by_id" / f"{wrestler_id}.json"
    
    if not profile_path.exists():
        return None
    
    try:
        with profile_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load_placement_notes(season: int, gender: str) -> Dict[str, str]:
    """
    Load placement notes and return wrestler_id -> note mapping.
    
    Args:
        season: Season year
        gender: Gender ('boys' or 'girls')
    
    Returns:
        Dictionary mapping wrestler_id -> placement note (e.g., "1", "3", "BR", "Q")
    """
    notes_path = Path("mt/rankings_data") / f"hs_ky_{gender}" / str(season) / "placement_notes.json"
    
    if not notes_path.exists():
        return {}
    
    try:
        with notes_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        
        lookup = {}
        for entry in data.get("notes", []):
            wid = entry.get("wrestler_id")
            note = str(entry.get("note", "")).strip().upper()
            if wid and note:
                lookup[wid] = note
        
        return lookup
    except Exception:
        return {}


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
    - Non-starters ALWAYS get "N/A"
    
    Args:
        top_wrestlers: List of wrestler entries (top 40 for boys, top 24 for girls)
        region_mapping: Dictionary mapping team_name -> region number
        team_best_wrestler: Dictionary mapping team -> wrestler_id of highest ranked wrestler
        gender: 'boys' or 'girls'
        
    Returns:
        Dictionary mapping wrestler_id -> region_place ("1", "2", "3", "4", or "N/A")
    """
    region_places = {}
    
    # Group wrestlers by region (only starters)
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
        region = get_region_for_team(team, region_mapping)
        if not region or region == "-":
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


def load_previous_drop_rankings(
    archive_base: Path,
    gender: str,
    season: int,
    weight: int,
    previous_drop_id: str
) -> Dict[str, int]:
    """
    Load previous drop's rankings and return mapping of wrestler_id -> previous_rank.
    
    Args:
        archive_base: Base directory for archive structure
        gender: 'boys' or 'girls'
        season: Season year
        weight: Weight class
        previous_drop_id: Previous drop identifier
    
    Returns:
        Dictionary mapping wrestler_id -> previous_rank (or empty dict if not found)
    """
    previous_file = archive_base / gender / str(season) / previous_drop_id / f"{weight}.json"
    
    if not previous_file.exists():
        return {}
    
    try:
        with previous_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        
        previous_rankings = {}
        for wrestler in data.get("wrestlers", []):
            wid = wrestler.get("wrestler_id")
            rank = wrestler.get("rank")
            if wid and rank:
                previous_rankings[wid] = rank
        
        return previous_rankings
    except Exception as e:
        print(f"Warning: Could not load previous drop rankings for {weight}: {e}")
        return {}


def format_rank_with_movement(rank: int, movement: Optional[int], is_new: bool) -> str:
    """
    Format rank with movement indicator in parentheses.
    
    Args:
        rank: Current rank
        movement: Movement value (positive = up, negative = down)
        is_new: Whether wrestler is new to rankings
    
    Returns:
        Formatted string like "5 (+11)", "7 (-4)", "8 (N)", or "3"
    """
    if is_new:
        return f"{rank} (N)"
    elif movement is not None and movement != 0:
        sign = "+" if movement > 0 else ""
        return f"{rank} ({sign}{movement})"
    else:
        return str(rank)


def enrich_rankings_with_region_data(
    rankings: List[Dict],
    region_mapping: Dict[str, str],
    gender: str,
    season: int,
    top_n: int,
    placement_notes: Optional[Dict[str, str]] = None,
    previous_rankings: Optional[Dict[str, int]] = None
) -> Tuple[List[Dict], Dict[str, str], Dict[str, str]]:
    """
    Enrich rankings with region data, region places, and is_highest_ranked flags.
    
    Args:
        rankings: Full list of ranked wrestlers (preserves exact order)
        region_mapping: Dictionary mapping team_name -> region number
        gender: 'boys' or 'girls'
        top_n: Maximum number of wrestlers to include (40 for boys, 24 for girls)
        placement_notes: Optional placement notes mapping
        previous_rankings: Optional previous drop rankings for movement calculation
    
    Returns:
        Tuple of (enriched_rankings, region_places, team_best_wrestler)
    """
    # Limit to top N (preserves order)
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
    
    # Calculate region places
    region_places = calculate_region_places(top_wrestlers, region_mapping, team_best_wrestler, gender)
    
    # Enrich each wrestler entry
    enriched_rankings = []
    for entry in top_wrestlers:
        wid = entry.get('wrestler_id', '')
        team = entry.get('team', '')
        
        # Load wrestler profile for record and bonus_pct
        profile = load_wrestler_profile(wid, season, gender)
        
        # Extract record from profile (preferred) or ranking entry
        record_data = None
        record_str = None
        
        if profile and "record" in profile:
            record_overall = profile["record"].get("overall")
            if record_overall:
                record_data = parse_record(record_overall)
                if record_data:
                    record_str = format_record_str(
                        record_data["wins"],
                        record_data["losses"]
                    )
        
        # Fallback to ranking entry record
        if not record_data:
            ranking_record = entry.get("record")
            if ranking_record:
                record_data = parse_record(str(ranking_record))
                if record_data:
                    record_str = format_record_str(
                        record_data["wins"],
                        record_data["losses"]
                    )
        
        # Extract bonus rate from profile
        bonus_pct = None
        if profile and "metrics" in profile:
            bonus_rate = profile["metrics"].get("bonus_rate")
            if bonus_rate is not None:
                bonus_pct = float(bonus_rate)
        
        # Create enriched entry
        enriched_entry = {
            "rank": entry.get("rank"),
            "wrestler_id": entry.get("wrestler_id"),
            "name": entry.get("name"),
            "team": entry.get("team"),
            "region": get_region_for_team(team, region_mapping),
            "region_place": region_places.get(wid, "N/A"),
            "is_highest_ranked": team_best_wrestler.get(team) == wid,
        }
        
        # Add record data
        if record_data:
            enriched_entry["record"] = record_data
            if record_str:
                enriched_entry["record_str"] = record_str
        else:
            enriched_entry["record"] = None
            enriched_entry["record_str"] = None
        
        # Add bonus_pct
        if bonus_pct is not None:
            enriched_entry["bonus_pct"] = bonus_pct
        else:
            enriched_entry["bonus_pct"] = None
        
        # Preserve is_starter if present (for compatibility)
        if "is_starter" in entry:
            enriched_entry["is_starter"] = entry["is_starter"]
        
        # Add placement note if available
        if placement_notes:
            placement_note = placement_notes.get(wid)
            if placement_note:
                enriched_entry["placement_note"] = placement_note
        
        # Add previous rank and movement if previous rankings available
        if previous_rankings:
            previous_rank = previous_rankings.get(wid)
            current_rank = enriched_entry.get("rank")
            
            if previous_rank is not None and current_rank is not None:
                # Wrestler was in previous rankings - calculate movement
                enriched_entry["previous_rank"] = previous_rank
                movement = previous_rank - current_rank  # Positive = moved up, Negative = moved down
                enriched_entry["movement"] = movement
                enriched_entry["is_new"] = False
            else:
                # Wrestler not in previous rankings (new entry or moved from different weight)
                enriched_entry["previous_rank"] = None
                enriched_entry["movement"] = None
                enriched_entry["is_new"] = True
        else:
            # No previous rankings available (baseline drop)
            enriched_entry["is_new"] = False
        
        # DO NOT include: mv, tpar, mat_value, or any TPAR-related fields
        # These are removed from the archive output
        
        enriched_rankings.append(enriched_entry)
    
    return enriched_rankings, region_places, team_best_wrestler


def apply_text_color(element: ET.Element, color: str) -> None:
    """
    Apply a fill color to an SVG text element by updating its style attribute.
    
    Args:
        element: SVG text or tspan element
        color: Hex color string (e.g., "#000000" or "#BBBBBB")
    """
    # Get existing style string
    style_str = element.get("style", "")
    
    # Parse style into dict
    style_parts = [part.strip() for part in style_str.split(";") if part.strip()]
    style_dict: Dict[str, str] = {}
    for part in style_parts:
        if ":" not in part:
            continue
        k, v = part.split(":", 1)
        style_dict[k.strip()] = v.strip()
    
    # Update fill color
    style_dict["fill"] = color
    
    # Rebuild style string
    new_style = ";".join(f"{k}:{v}" for k, v in style_dict.items())
    
    # Apply to element
    element.set("style", new_style)
    
    # Also apply to tspan if it exists (for consistency)
    # Check for tspan in the SVG namespace
    ns = {"svg": "http://www.w3.org/2000/svg"}
    tspan = element.find("svg:tspan", ns)
    if tspan is not None:
        tspan.set("style", new_style)


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
    Includes movement indicators in rank column.
    
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
    
    # Update date elements
    # Girls template: format mm.dd.yyyy
    # Boys template: format yyyy.mm.dd
    if gender == 'girls':
        date_str = datetime.now().strftime("%m.%d.%Y")
    elif gender == 'boys':
        date_str = datetime.now().strftime("%Y.%m.%d")
    else:
        date_str = None
    
    if date_str:
        # Find elements with inkscape:label="date1" and inkscape:label="date2"
        for date_label in ["date1", "date2"]:
            date_el = root.find(f".//svg:text[@inkscape:label='{date_label}']", namespaces=ns)
            if date_el is not None:
                # Try to find tspan within the element using namespace
                tspan = date_el.find("svg:tspan", ns)
                if tspan is not None:
                    tspan.text = date_str
                else:
                    # If no tspan, set text directly on the element
                    date_el.text = date_str
    
    # Fill data for weight1 (max_rows rows)
    for row in range(1, max_rows + 1):
        if row - 1 < len(wrestlers1):
            entry = wrestlers1[row - 1]
            wid = entry.get('wrestler_id', '')
            name = entry.get('name', '')
            team = entry.get('team', '')
            rank = entry.get('rank', '')
            movement = entry.get('movement')
            is_new = entry.get('is_new', False)
            region = get_region_for_team(team, region_mapping)
            region_place = region_places1.get(wid, 'N/A')
            grade = grade_info1.get(wid, '')
            
            # Format rank with movement indicator
            rank_display = format_rank_with_movement(rank, movement, is_new)
            
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
            
            # Update rank delta (movement indicator only)
            rank_el = root.find(f".//svg:text[@inkscape:label='rank_1_{row}']", namespaces=ns)
            if rank_el is not None:
                tspan = rank_el.find("svg:tspan", ns)
                target = tspan if tspan is not None else rank_el
                
                # Debug output
                if row <= 5:  # Only debug first 5 rows to avoid spam
                    print(f"  DEBUG weight1 row {row}: name={name}, rank={rank}, movement={movement}, is_new={is_new}")
                
                # Set text to movement indicator only (not full rank)
                if is_new:
                    target.text = "N"
                    apply_text_color(target, "#0066CC")  # Blue for new
                    if row <= 5:
                        print(f"    -> Set rank_1_{row} to 'N' (blue)")
                elif movement and movement > 0:
                    target.text = f"+{movement}"
                    apply_text_color(target, "#00AA00")  # Green for up
                    if row <= 5:
                        print(f"    -> Set rank_1_{row} to '+{movement}' (green)")
                elif movement and movement < 0:
                    target.text = str(movement)  # Already negative, e.g., "-4"
                    apply_text_color(target, "#CC0000")  # Red for down
                    if row <= 5:
                        print(f"    -> Set rank_1_{row} to '{movement}' (red)")
                else:
                    # No movement - leave empty
                    target.text = ""
                    if row <= 5:
                        print(f"    -> Set rank_1_{row} to '' (no movement)")
            else:
                if row <= 5:
                    print(f"  DEBUG weight1 row {row}: rank_1_{row} element NOT FOUND in SVG")
            
            # Update name (truncate to 20 characters with "...")
            name_el = root.find(f".//svg:text[@inkscape:label='name_1_{row}']", namespaces=ns)
            if name_el is not None:
                tspan = name_el.find("svg:tspan", ns)
                target = tspan if tspan is not None else name_el
                truncated_name = truncate_name_for_svg(name, max_length=20)
                target.text = truncated_name
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
            rank = entry.get('rank', '')
            movement = entry.get('movement')
            is_new = entry.get('is_new', False)
            region = get_region_for_team(team, region_mapping)
            region_place = region_places2.get(wid, 'N/A')
            grade = grade_info2.get(wid, '')
            
            # Format rank with movement indicator
            rank_display = format_rank_with_movement(rank, movement, is_new)
            
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
            
            # Update rank delta (movement indicator only)
            rank_el = root.find(f".//svg:text[@inkscape:label='rank_2_{row}']", namespaces=ns)
            if rank_el is not None:
                tspan = rank_el.find("svg:tspan", ns)
                target = tspan if tspan is not None else rank_el
                
                # Debug output
                if row <= 5:  # Only debug first 5 rows to avoid spam
                    print(f"  DEBUG weight2 row {row}: name={name}, rank={rank}, movement={movement}, is_new={is_new}")
                
                # Set text to movement indicator only (not full rank)
                if is_new:
                    target.text = "N"
                    apply_text_color(target, "#0066CC")  # Blue for new
                    if row <= 5:
                        print(f"    -> Set rank_2_{row} to 'N' (blue)")
                elif movement and movement > 0:
                    target.text = f"+{movement}"
                    apply_text_color(target, "#00AA00")  # Green for up
                    if row <= 5:
                        print(f"    -> Set rank_2_{row} to '+{movement}' (green)")
                elif movement and movement < 0:
                    target.text = str(movement)  # Already negative, e.g., "-4"
                    apply_text_color(target, "#CC0000")  # Red for down
                    if row <= 5:
                        print(f"    -> Set rank_2_{row} to '{movement}' (red)")
                else:
                    # No movement - leave empty
                    target.text = ""
                    if row <= 5:
                        print(f"    -> Set rank_2_{row} to '' (no movement)")
            else:
                if row <= 5:
                    print(f"  DEBUG weight2 row {row}: rank_2_{row} element NOT FOUND in SVG")
            
            # Update name (truncate to 20 characters with "...")
            name_el = root.find(f".//svg:text[@inkscape:label='name_2_{row}']", namespaces=ns)
            if name_el is not None:
                tspan = name_el.find("svg:tspan", ns)
                target = tspan if tspan is not None else name_el
                truncated_name = truncate_name_for_svg(name, max_length=20)
                target.text = truncated_name
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
        raise ImportError("cairosvg and PIL are required for JPG generation")
    
    jpg_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Render SVG to PNG in memory, then convert to JPG via Pillow
    png_bytes = cairosvg.svg2png(url=str(svg_path), output_width=width, output_height=height)
    img = Image.open(BytesIO(png_bytes)).convert("RGB")
    img.save(jpg_path, format="JPEG", quality=95)
    print(f"  ✓ JPG generated: {jpg_path}")


def combine_jpgs_to_pdf(jpg_files: List[Path], pdf_path: Path) -> None:
    """
    Combine multiple JPG files into a single PDF.
    
    Args:
        jpg_files: List of JPG file paths (sorted in desired order)
        pdf_path: Path to output PDF file
    """
    if not REPORTLAB_AVAILABLE:
        raise ImportError("reportlab is required for PDF combination")
    
    if not jpg_files:
        print("Warning: No JPG files to combine into PDF")
        return
    
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create PDF document
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import Image as RLImage
    
    doc = SimpleDocTemplate(str(pdf_path), pagesize=letter)
    story = []
    
    # Add each JPG as a page
    for jpg_file in sorted(jpg_files):
        if not jpg_file.exists():
            print(f"Warning: JPG file not found: {jpg_file}")
            continue
        
        try:
            # Open image to get dimensions
            img = Image.open(jpg_file)
            img_width, img_height = img.size
            
            # Calculate scaling to fit letter size (8.5 x 11 inches)
            # Leave small margins
            page_width = letter[0] - 40  # 20px margin on each side
            page_height = letter[1] - 40  # 20px margin on top/bottom
            
            # Calculate scale to fit while maintaining aspect ratio
            scale_w = page_width / img_width
            scale_h = page_height / img_height
            scale = min(scale_w, scale_h)
            
            # Create ReportLab Image
            rl_img = RLImage(str(jpg_file), width=img_width * scale, height=img_height * scale)
            story.append(rl_img)
            if jpg_file != sorted(jpg_files)[-1]:  # Don't add page break after last image
                story.append(PageBreak())
        except Exception as e:
            print(f"Warning: Could not add {jpg_file} to PDF: {e}")
            continue
    
    if story:
        doc.build(story)
        print(f"✓ PDF generated: {pdf_path} ({len([f for f in jpg_files if f.exists()])} pages)")
    else:
        print("Warning: No images were added to PDF")


def get_weight_class_data(
    weight_class: str,
    season: int,
    gender: str,
    region_mapping: Dict[str, str],
    top_n: int = 40,
    placement_notes: Optional[Dict[str, str]] = None,
    previous_rankings: Optional[Dict[str, int]] = None
) -> Tuple[List[Dict], Dict[str, str], Dict[str, str]]:
    """
    Load and enrich weight class data.
    
    Returns:
        Tuple of (wrestlers, region_places, team_best_wrestler)
    """
    # Load rankings file
    rankings_path = Path(f"mt/rankings_data/hs_ky_{gender}") / str(season) / f"rankings_{weight_class}.json"
    
    if not rankings_path.exists():
        raise FileNotFoundError(f"Rankings file not found: {rankings_path}")
    
    rankings_data = load_rankings(rankings_path)
    rankings = rankings_data.get('rankings', [])
    
    if not rankings:
        return [], {}, {}
    
    # Enrich with region data
    enriched_rankings, region_places, team_best_wrestler = enrich_rankings_with_region_data(
        rankings, region_mapping, gender, season, top_n, placement_notes, previous_rankings
    )
    
    return enriched_rankings, region_places, team_best_wrestler


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
    from collections import defaultdict
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
    if max_length >= 999:
        return text
    if len(text) > max_length:
        return text[:max_length-1] + '…'
    return text


def normalize_name_for_svg(name: str) -> str:
    """
    Normalize name for SVG display: title case with proper handling of spaces, hyphens, apostrophes, and parentheses.
    
    Examples:
        "john smith" -> "John Smith"
        "mary-jane o'brien" -> "Mary-Jane O'Brien"
        "JEAN-PIERRE" -> "Jean-Pierre"
        "Masoka (ashley) Kilo" -> "Masoka (Ashley) Kilo"
        "Hannah liz' Porter" -> "Hannah Liz' Porter"
    """
    if not name:
        return ""
    
    result = []
    i = 0
    name = name.strip()
    
    while i < len(name):
        char = name[i]
        
        # Capitalize after spaces, hyphens, apostrophes, opening parentheses
        if i == 0 or name[i-1] in " -'(":
            # Capitalize this character if it's a letter
            if char.isalpha():
                result.append(char.upper())
            else:
                result.append(char)
        # After closing parentheses, capitalize if next char is a letter
        elif name[i-1] == ')' and char.isalpha():
            result.append(char.upper())
        # After apostrophes (like in "liz'"), capitalize if next char is a letter
        elif name[i-1] == "'" and char.isalpha():
            result.append(char.upper())
        else:
            # Lowercase everything else (letters)
            if char.isalpha():
                result.append(char.lower())
            else:
                result.append(char)
        
        i += 1
    
    return "".join(result)


def truncate_name_for_svg(name: str, max_length: int = 20) -> str:
    """
    Normalize and truncate wrestler name for SVG display.
    First normalizes the name (title case), then truncates to max_length characters with '...' if needed.
    """
    if not name:
        return ""
    
    # First normalize the name
    normalized = normalize_name_for_svg(name)
    
    # Then truncate if needed
    if len(normalized) > max_length:
        return normalized[:max_length] + "..."
    return normalized


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
        
        # Get region
        region = get_region_for_team(team, region_mapping)
        
        # Get region place
        region_place = region_places.get(wid, "N/A")
        
        # Combine Region and Region Place into single column
        if region and region != '?':
            if region_place and region_place != 'N/A':
                region_display = f"{region} ({region_place})"
            else:
                region_display = f"{region} (-)"
        else:
            region_display = "-"
        
        table_data.append([str(rank), name, team, region_display])
    
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


def load_previous_team_rankings(
    archive_base: Path,
    gender: str,
    season: int,
    ranking_type: str,
    previous_drop_id: str
) -> Dict[str, int]:
    """
    Load previous drop's team rankings and return mapping of team_name -> previous_rank.
    
    Args:
        archive_base: Base directory for archive structure
        gender: 'boys' or 'girls'
        season: Season year
        ranking_type: 'tournament' or 'dual'
        previous_drop_id: Previous drop identifier
    
    Returns:
        Dictionary mapping team_name -> previous_rank (or empty dict if not found)
    """
    previous_file = archive_base / gender / str(season) / "team" / ranking_type / "drops" / f"{previous_drop_id}.json"
    
    if not previous_file.exists():
        return {}
    
    try:
        with previous_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        
        previous_rankings = {}
        for team in data.get("rankings", []):
            team_name = team.get("team")
            rank = team.get("rank")
            if team_name and rank:
                previous_rankings[team_name] = rank
        
        return previous_rankings
    except Exception as e:
        print(f"Warning: Could not load previous team rankings for {ranking_type}: {e}")
        return {}


def generate_team_tournament_rankings(
    season: int,
    gender: str,
    drop_id: str,
    archive_base: Path,
    previous_drop_id: Optional[str] = None
) -> None:
    """
    Generate team tournament rankings archive from xTP data.
    
    Args:
        season: Season year
        gender: 'boys' or 'girls'
        drop_id: Drop identifier
        archive_base: Base directory for archive structure
        previous_drop_id: Optional previous drop ID for delta calculation
    """
    # Load team xTP data
    xtp_path = Path(f"frontend/hs-ky-ui/public/data/xtp/{gender}/{season}/xtp_teams_{season}.json")
    
    if not xtp_path.exists():
        print(f"Warning: Team xTP file not found: {xtp_path}")
        print("  Skipping team tournament rankings archive")
        return
    
    with xtp_path.open("r", encoding="utf-8") as f:
        xtp_data = json.load(f)
    
    teams_list = xtp_data.get("teams", [])
    if not teams_list:
        print(f"Warning: No teams found in xTP data")
        return
    
    # Sort by team_xTP_simple (descending)
    teams_list.sort(key=lambda t: -t.get("team_xTP_simple", 0.0))
    
    # Load previous rankings for delta calculation
    previous_rankings = {}
    if previous_drop_id:
        previous_rankings = load_previous_team_rankings(
            archive_base, gender, season, "tournament", previous_drop_id
        )
    
    # Build rankings with deltas
    rankings = []
    for rank, team in enumerate(teams_list, start=1):
        team_name = team.get("team", "")
        points = team.get("team_xTP_simple", 0.0)
        
        # Calculate delta
        prev_rank = previous_rankings.get(team_name)
        if prev_rank is not None:
            delta = prev_rank - rank  # Positive = moved up, Negative = moved down
        else:
            prev_rank = None
            delta = None
        
        entry = {
            "rank": rank,
            "team": team_name,
            "points": points,
            "prev_rank": prev_rank,
            "delta": delta
        }
        # Include per-weight wrestler breakdown for expandable rows on Team Tournament Rankings page
        if team.get("weights"):
            entry["weights"] = team.get("weights")
        rankings.append(entry)
    
    # Create output structure
    output_data = {
        "season": season,
        "gender": gender,
        "ranking_type": "team_tournament",
        "drop_id": drop_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rankings": rankings
    }
    
    # Write to archive
    archive_dir = archive_base / gender / str(season) / "team" / "tournament" / "drops"
    archive_dir.mkdir(parents=True, exist_ok=True)
    
    drop_file = archive_dir / f"{drop_id}.json"
    with drop_file.open("w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    # Update latest.json
    latest_file = archive_base / gender / str(season) / "team" / "tournament" / "latest.json"
    with latest_file.open("w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Team Tournament Rankings: {len(rankings)} teams archived")


def generate_dual_rankings(
    season: int,
    gender: str,
    drop_id: str,
    archive_base: Path,
    previous_drop_id: Optional[str] = None
) -> None:
    """
    Generate dual rankings archive from dual_standings.json.
    
    Args:
        season: Season year
        gender: 'boys' or 'girls'
        drop_id: Drop identifier
        archive_base: Base directory for archive structure
        previous_drop_id: Optional previous drop ID for delta calculation
    """
    # Load dual standings data
    dual_path = Path(f"frontend/hs-ky-ui/public/data/dual_standings/{gender}/{season}/dual_standings.json")
    
    if not dual_path.exists():
        print(f"Warning: Dual standings file not found: {dual_path}")
        print("  Skipping dual rankings archive")
        return
    
    with dual_path.open("r", encoding="utf-8") as f:
        standings = json.load(f)
    
    if not standings:
        print(f"Warning: No dual standings found")
        return
    
    # Load previous rankings for delta calculation
    previous_rankings = {}
    if previous_drop_id:
        previous_rankings = load_previous_team_rankings(
            archive_base, gender, season, "dual", previous_drop_id
        )
    
    # Build rankings with deltas
    rankings = []
    for entry in standings:
        rank = entry.get("rank")
        team_name = entry.get("team", "")
        wins = entry.get("wins", 0)
        losses = entry.get("losses", 0)
        ties = entry.get("ties", 0)
        point_diff = entry.get("point_diff", 0)
        win_pct = entry.get("win_pct", 0.0)
        
        # Calculate delta
        prev_rank = previous_rankings.get(team_name)
        if prev_rank is not None:
            delta = prev_rank - rank  # Positive = moved up, Negative = moved down
        else:
            prev_rank = None
            delta = None
        
        rankings.append({
            "rank": rank,
            "team": team_name,
            "wins": wins,
            "losses": losses,
            "ties": ties,
            "point_diff": point_diff,
            "win_pct": win_pct,
            "prev_rank": prev_rank,
            "delta": delta
        })
    
    # Create output structure
    output_data = {
        "season": season,
        "gender": gender,
        "ranking_type": "dual",
        "drop_id": drop_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rankings": rankings
    }
    
    # Write to archive
    archive_dir = archive_base / gender / str(season) / "team" / "dual" / "drops"
    archive_dir.mkdir(parents=True, exist_ok=True)
    
    drop_file = archive_dir / f"{drop_id}.json"
    with drop_file.open("w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    # Update latest.json
    latest_file = archive_base / gender / str(season) / "team" / "dual" / "latest.json"
    with latest_file.open("w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Dual Rankings: {len(rankings)} teams archived")


def create_baseline_archive(
    season: int,
    gender: str,
    drop_id: str,
    archive_base: Path = Path("frontend/hs-ky-ui/public/data/rankings"),
    force: bool = False
) -> None:
    """
    Create baseline archive from full rankings files with region enrichment.
    
    Args:
        season: Season year (e.g., 2026)
        gender: 'boys' or 'girls'
        drop_id: Drop identifier (e.g., '2026-01-02')
        archive_base: Base directory for archive structure
        force: If True, proceed even if rankings files appear stale
    """
    # Construct archive paths
    archive_dir = archive_base / gender / str(season) / drop_id
    archive_dir.mkdir(parents=True, exist_ok=True)
    
    # Determine weight classes and top-N limit based on gender
    if gender == 'boys':
        weights = KY_HS_BOYS_WEIGHTS
        top_n = 40
    else:  # girls
        weights = KY_HS_GIRLS_WEIGHTS
        top_n = 24
    
    # Load region mapping
    region_mapping = load_team_region_mapping(gender)
    if not region_mapping:
        print(f"Warning: No region mapping found for {gender}")
        print(f"  Expected file: data/team_lists/hs_ky_{gender}/teams.json")
        if not force:
            print("  Use --force to proceed anyway")
            raise ValueError("Region mapping required for archive creation")
    else:
        print(f"Loaded region mapping for {len(region_mapping)} teams")
    
    # Load placement notes
    placement_notes = load_placement_notes(season, gender)
    if placement_notes:
        print(f"Loaded {len(placement_notes)} placement notes")
    else:
        print("No placement notes found (this is okay)")
    
    # Determine if this is a baseline drop and find previous drop
    index_dir = archive_base / gender / str(season)
    index_file = index_dir / "index.json"
    is_baseline = True
    previous_drop_id = None
    
    if index_file.exists():
        try:
            with index_file.open("r", encoding="utf-8") as f:
                index_data = json.load(f)
            
            # Check if this drop already exists (updating existing)
            existing_drops = [d for d in index_data.get("drops", []) if d.get("id") != drop_id]
            
            if existing_drops:
                # Not baseline - find most recent previous drop
                is_baseline = False
                # Drops are sorted by published_at (newest first)
                previous_drop_id = existing_drops[0].get("id")
                print(f"Previous drop found: {previous_drop_id}")
            else:
                print("This is the first drop (baseline)")
        except Exception as e:
            print(f"Warning: Could not read index.json: {e}")
            print("Treating as baseline drop")
    
    # Setup source directory
    source_dir = Path(f"mt/rankings_data/hs_ky_{gender}") / str(season)
    if not source_dir.exists():
        raise ValueError(f"Source directory not found: {source_dir}")
    
    # Check file freshness (warn but don't block)
    from datetime import timedelta
    now = datetime.now()
    stale_threshold = timedelta(days=7)
    stale_files = []
    
    # Process each weight class
    processed_files = []
    for weight in weights:
        source_file = source_dir / f"rankings_{weight}.json"
        if not source_file.exists():
            print(f"Warning: Source file not found: {source_file}")
            continue
        
        # Check freshness
        file_mtime = datetime.fromtimestamp(source_file.stat().st_mtime)
        age = now - file_mtime
        if age > stale_threshold:
            stale_files.append((weight, age.days))
        
        try:
            # Load rankings file
            with source_file.open("r", encoding="utf-8") as f:
                rankings_data = json.load(f)
            
            rankings = rankings_data.get('rankings', [])
            if not rankings:
                print(f"Warning: No rankings found in {source_file}")
                continue
            
            # Load previous drop rankings if not baseline
            previous_rankings = {}
            if not is_baseline and previous_drop_id:
                previous_rankings = load_previous_drop_rankings(
                    archive_base, gender, season, weight, previous_drop_id
                )
                if previous_rankings:
                    print(f"  Loaded previous rankings for {len(previous_rankings)} wrestlers")
            
            # Enrich with region data (and movement if previous rankings available)
            enriched_rankings, region_places, team_best_wrestler = enrich_rankings_with_region_data(
                rankings, region_mapping, gender, season, top_n, placement_notes,
                previous_rankings if previous_rankings else None
            )
            
            # Create output structure
            output_data = {
                "season": season,
                "weight": weight,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source": f"rankings_{weight}.json",
                "wrestlers": enriched_rankings
            }
            
            # Save to archive
            dest_file = archive_dir / f"{weight}.json"
            with dest_file.open("w", encoding="utf-8") as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            
            processed_files.append(str(weight))
            print(f"✓ Processed {weight}.json ({len(enriched_rankings)} wrestlers)")
            
        except Exception as e:
            print(f"Error processing {weight}.json: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    if not processed_files:
        raise ValueError(f"No ranking files processed from {source_dir}")
    
    # Warn about stale files
    if stale_files:
        print(f"\n⚠ Warning: {len(stale_files)} rankings file(s) appear stale:")
        for weight, days in stale_files:
            print(f"  {weight}.json: {days} days old")
        if not force:
            print("  Consider updating rankings before archiving")
    
    # Create meta.json
    meta = {
        "id": drop_id,
        "season": season,
        "gender": gender,
        "published_at": f"{drop_id}T00:00:00Z",
        "baseline": is_baseline
    }
    
    meta_file = archive_dir / "meta.json"
    with meta_file.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    print(f"✓ Created meta.json")
    
    # Create notes/ subdirectory with blank markdown files for each weight
    # Files are created blank by default and only shown if they have content
    notes_dir = archive_dir / "notes"
    notes_dir.mkdir(exist_ok=True)
    
    for weight in weights:
        notes_file = notes_dir / f"{weight}.md"
        if not notes_file.exists():
            # Create blank file - will only be displayed if user adds content
            with notes_file.open("w", encoding="utf-8") as f:
                f.write("")
    
    print(f"✓ Created notes/ subdirectory")
    
    # Create/update index.json
    index_dir = archive_base / gender / str(season)
    index_dir.mkdir(parents=True, exist_ok=True)
    index_file = index_dir / "index.json"
    
    if index_file.exists():
        with index_file.open("r", encoding="utf-8") as f:
            index_data = json.load(f)
    else:
        index_data = {
            "latest": drop_id,
            "drops": []
        }
    
    # Add this drop to the registry if not already present
    drop_exists = any(d["id"] == drop_id for d in index_data["drops"])
    if not drop_exists:
        index_data["drops"].append({
            "id": drop_id,
            "published_at": f"{drop_id}T00:00:00Z"
        })
        # Sort drops by published_at (newest first)
        index_data["drops"].sort(key=lambda x: x["published_at"], reverse=True)
        index_data["latest"] = drop_id
    
    with index_file.open("w", encoding="utf-8") as f:
        json.dump(index_data, f, indent=2)
    print(f"✓ Updated index.json")
    
    print(f"\n✓ Archive created: {archive_dir}")
    print(f"  Processed {len(processed_files)} weight class files")
    print(f"  Top {top_n} wrestlers per weight class")


def generate_svg_graphics(
    season: int,
    gender: str,
    all_weight_data: Dict[str, Tuple[List[Dict], Dict[str, str], Dict[str, str]]],
    region_mapping: Dict[str, str],
    output_dir: Path,
    release_date_yyyymmdd: Optional[str] = None
) -> None:
    """
    Generate SVG/JPG graphics from template for all weight classes.
    Includes movement indicators in rank column.
    
    Args:
        season: Season year
        gender: Gender ('boys' or 'girls')
        all_weight_data: Dictionary mapping weight_class -> (wrestlers, region_places, team_best_wrestler)
        region_mapping: Dictionary mapping team_name -> region number
        output_dir: Output directory for JPG files
        release_date_yyyymmdd: Optional date for JPG filename (YYYYMMDD). If None, uses today.
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
    
    # Generate date string for filename (use release_date when provided, e.g. from drop_id)
    date_str = release_date_yyyymmdd if release_date_yyyymmdd else datetime.now().strftime("%Y%m%d")
    
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
            
            # Debug: Check if movement data exists
            if wrestlers1 and len(wrestlers1) > 0:
                first_wrestler = wrestlers1[0]
                print(f"  DEBUG {weight1}: First wrestler has movement={first_wrestler.get('movement')}, is_new={first_wrestler.get('is_new')}")
            if wrestlers2 and len(wrestlers2) > 0:
                first_wrestler = wrestlers2[0]
                print(f"  DEBUG {weight2}: First wrestler has movement={first_wrestler.get('movement')}, is_new={first_wrestler.get('is_new')}")
            
            # Fill SVG template
            print(f"  Filling SVG template for {weight1} and {weight2}...")
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
    output_path: Path,
    all_weight_data: Optional[Dict[str, Tuple[List[Dict], Dict[str, str], Dict[str, str]]]] = None,
    region_mapping: Optional[Dict[str, str]] = None
):
    """Generate PDF report with all weight classes and team report."""
    if not REPORTLAB_AVAILABLE:
        print("Error: reportlab is required for PDF generation. Install with: pip install reportlab")
        return
    
    # Load region mapping if not provided
    if region_mapping is None:
        region_mapping = load_team_region_mapping(gender)
        if not region_mapping:
            print(f"Warning: No region mapping found for {gender}.")
            print(f"  Expected file: data/team_lists/hs_ky_{gender}/teams.json")
        else:
            print(f"Loaded region mapping for {len(region_mapping)} teams")
    
    # Load data if not provided
    if all_weight_data is None:
        all_weight_data = {}
        if gender == 'boys':
            weights = KY_HS_BOYS_WEIGHTS
        else:
            weights = KY_HS_GIRLS_WEIGHTS
        
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
    
    # Page setup
    page_size = (612, 792)  # Standard letter size
    doc = SimpleDocTemplate(str(output_path), pagesize=page_size,
                           leftMargin=20, rightMargin=20,
                           topMargin=20, bottomMargin=20)
    story = []
    styles = getSampleStyleSheet()
    
    body_style = styles["Normal"]
    body_style.leading = body_style.fontSize + 1
    
    # Color scheme
    header_color = colors.HexColor('#1a237e')
    accent_color = colors.HexColor('#ffc107')
    light_bg = colors.HexColor('#e3f2fd')
    dark_text = colors.HexColor('#212121')
    
    # Create custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=header_color,
        spaceAfter=6,
        alignment=1,
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=11,
        textColor=dark_text,
        spaceAfter=8,
        alignment=1
    )
    
    # Calculate column widths for side-by-side layout
    gutter = 10
    available_width = page_size[0] - 40
    table_width = (available_width - gutter) / 2
    
    col_widths = [
        0.06 * table_width,   # Rank
        0.45 * table_width,   # Name
        0.32 * table_width,   # School
        0.17 * table_width,   # Region
    ]
    
    # Generate pages with TWO tables side-by-side
    weight_classes = sorted(all_weight_data.keys(), key=lambda x: int(x))
    top_n_for_table = 24 if gender == 'girls' else 40
    
    for i in range(0, len(weight_classes), 2):
        weight1 = weight_classes[i]
        weight2 = weight_classes[i + 1] if i + 1 < len(weight_classes) else None
        
        wrestlers1, region_places1, team_best_wrestler1 = all_weight_data[weight1]
        table_data1 = build_rankings_table_data(
            weight1, season, gender,
            wrestlers1, region_places1, team_best_wrestler1, region_mapping, 
            top_n=top_n_for_table, name_max_len=16, school_max_len=18
        )
        
        if weight2:
            wrestlers2, region_places2, team_best_wrestler2 = all_weight_data[weight2]
            table_data2 = build_rankings_table_data(
                weight2, season, gender,
                wrestlers2, region_places2, team_best_wrestler2, region_mapping, 
                top_n=top_n_for_table, name_max_len=16, school_max_len=18
            )
            
            # Merge into single table with 8 columns
            combined_data = []
            max_rows = max(len(table_data1), len(table_data2))
            combined_data.append(table_data1[0] + table_data2[0])
            
            for row_idx in range(1, max_rows):
                left_row = table_data1[row_idx] if row_idx < len(table_data1) else [''] * 4
                right_row = table_data2[row_idx] if row_idx < len(table_data2) else [''] * 4
                combined_data.append(left_row + right_row)
            
            combined_col_widths = col_widths + col_widths
            combined_table = Table(combined_data, colWidths=combined_col_widths, repeatRows=1)
            
            combined_style = TableStyle([
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('ALIGN', (1, 0), (2, -1), 'LEFT'),
                ('ALIGN', (3, 0), (3, -1), 'CENTER'),
                ('ALIGN', (4, 0), (4, -1), 'CENTER'),
                ('ALIGN', (5, 0), (6, -1), 'LEFT'),
                ('ALIGN', (7, 0), (7, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
                ('TOPPADDING', (0, 0), (-1, 0), 2),
                ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.black),
                ('LINEAFTER', (3, 0), (3, -1), 0.5, colors.black),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 2),
                ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                ('TOPPADDING', (0, 1), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 2),
                ('WORDWRAP', (1, 0), (2, -1), True),
                ('WORDWRAP', (5, 0), (6, -1), True),
            ])
            
            # Apply grey color to non-starter rows
            for row_idx, entry in enumerate(wrestlers1[:top_n_for_table], start=1):
                wid = entry.get('wrestler_id', '')
                team = entry.get('team', '')
                is_highest_ranked = team_best_wrestler1.get(team) == wid
                if not is_highest_ranked:
                    combined_style.add('TEXTCOLOR', (0, row_idx), (3, row_idx), colors.HexColor('#BBBBBB'))
            
            for row_idx, entry in enumerate(wrestlers2[:top_n_for_table], start=1):
                wid = entry.get('wrestler_id', '')
                team = entry.get('team', '')
                is_highest_ranked = team_best_wrestler2.get(team) == wid
                if not is_highest_ranked:
                    combined_style.add('TEXTCOLOR', (4, row_idx), (7, row_idx), colors.HexColor('#BBBBBB'))
            
            combined_table.setStyle(combined_style)
            
            # Weight labels
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
            # Single weight
            table_data1 = build_rankings_table_data(
                weight1, season, gender,
                wrestlers1, region_places1, team_best_wrestler1, region_mapping, 
                top_n=top_n_for_table, name_max_len=999, school_max_len=999
            )
            t = Table(table_data1, colWidths=col_widths, repeatRows=1)
            table_style = TableStyle([
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('ALIGN', (1, 0), (2, -1), 'LEFT'),
                ('ALIGN', (3, 0), (3, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
                ('TOPPADDING', (0, 0), (-1, 0), 2),
                ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.black),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 2),
                ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                ('TOPPADDING', (0, 1), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 2),
            ])
            
            for i, entry in enumerate(wrestlers1[:top_n_for_table], start=1):
                wid = entry.get('wrestler_id', '')
                team = entry.get('team', '')
                is_highest_ranked = team_best_wrestler1.get(team) == wid
                if not is_highest_ranked:
                    table_style.add('TEXTCOLOR', (0, i), (-1, i), colors.HexColor('#BBBBBB'))
            
            t.setStyle(table_style)
            story.append(Paragraph(f"{weight1} lbs", weight_label_style))
            story.append(t)
        
        story.append(PageBreak())
    
    # Team report page
    team_title_style = ParagraphStyle(
        'TeamTitle',
        parent=styles['Heading1'],
        fontSize=22,
        textColor=colors.black,
        spaceAfter=8,
        alignment=1,
        fontName='Helvetica-Bold'
    )
    
    team_subtitle_style = ParagraphStyle(
        'TeamSubtitle',
        parent=styles['Normal'],
        fontSize=12,
        textColor=colors.black,
        spaceAfter=12,
        alignment=1
    )
    
    story.append(Paragraph(f"KY HS {gender.capitalize()} Team Rankings", team_title_style))
    story.append(Paragraph(f"Season {season} - Based on Top 4 Per Region", team_subtitle_style))
    story.append(Spacer(1, 0.1*inch))
    
    # Split teams into two tables
    teams_left = team_scores[0:25]
    teams_right = team_scores[25:50]
    
    team_table_data_left = build_team_report_table_data(teams_left, start_rank=1, end_rank=25)
    team_table_data_right = build_team_report_table_data(teams_right, start_rank=26, end_rank=50)
    
    gutter = 25
    available_width = page_size[0] - 40
    table_width = (available_width - gutter) / 2
    
    team_col_widths = [
        0.08 * table_width,
        0.57 * table_width,
        0.35 * table_width,
    ]
    
    combined_data = []
    max_rows = max(len(team_table_data_left), len(team_table_data_right))
    combined_data.append(team_table_data_left[0] + team_table_data_right[0])
    
    for row_idx in range(1, max_rows):
        left_row = team_table_data_left[row_idx] if row_idx < len(team_table_data_left) else [''] * 3
        right_row = team_table_data_right[row_idx] if row_idx < len(team_table_data_right) else [''] * 3
        combined_data.append(left_row + right_row)
    
    combined_col_widths = team_col_widths + team_col_widths
    combined_table = Table(combined_data, colWidths=combined_col_widths, repeatRows=1)
    
    combined_style = TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('ALIGN', (3, 0), (3, -1), 'CENTER'),
        ('ALIGN', (4, 0), (4, -1), 'LEFT'),
        ('ALIGN', (5, 0), (5, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
        ('TOPPADDING', (0, 0), (-1, 0), 2),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.black),
        ('LINEAFTER', (2, 0), (2, -1), 0.5, colors.black),
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
    
    # Build PDF
    print(f"\nGenerating PDF: {output_path}")
    doc.build(story)
    print(f"✓ PDF generated: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Create official rankings releases with multiple output formats"
    )
    parser.add_argument(
        "-season",
        type=int,
        required=True,
        help="Season year (e.g., 2026)"
    )
    parser.add_argument(
        "-gender",
        choices=["boys", "girls"],
        required=True,
        help="Gender"
    )
    parser.add_argument(
        "-drop-id",
        type=str,
        help="Drop identifier for archive/JPG (e.g., '2026-01-09'). Required if --archive is used. Recommended for --jpg to calculate movement indicators."
    )
    parser.add_argument(
        "--archive",
        action="store_true",
        help="Generate archive JSON files"
    )
    parser.add_argument(
        "--pdf",
        action="store_true",
        help="Generate PDF report"
    )
    parser.add_argument(
        "--jpg",
        action="store_true",
        help="Generate SVG/JPG graphics"
    )
    parser.add_argument(
        "--archive-base",
        type=str,
        default="frontend/hs-ky-ui/public/data/rankings",
        help="Base directory for archive structure"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Proceed even if rankings files appear stale"
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.archive and not args.drop_id:
        parser.error("--drop-id is required when --archive is used")
    
    # Warn if generating JPG without drop-id (movement won't be calculated)
    if args.jpg and not args.drop_id:
        print("Warning: --drop-id not specified. Movement indicators will not be calculated for JPG.")
        print("  To show movement, specify --drop-id (e.g., -drop-id 2026-01-07)")
    
    if not (args.archive or args.pdf or args.jpg):
        parser.error("At least one output format must be specified (--archive, --pdf, or --jpg)")
    
    # Load region mapping (shared across all outputs)
    region_mapping = load_team_region_mapping(args.gender)
    
    # Load placement notes (shared)
    placement_notes = load_placement_notes(args.season, args.gender)
    
    # Determine previous drop for movement calculation
    # Load previous rankings even if not creating archive (for JPG movement indicators)
    previous_rankings_map = {}
    previous_drop_id = None
    archive_base = Path(args.archive_base)
    index_dir = archive_base / args.gender / str(args.season)
    index_file = index_dir / "index.json"
    
    if index_file.exists():
        try:
            with index_file.open("r", encoding="utf-8") as f:
                index_data = json.load(f)
            
            # Find most recent drop (for JPG) or previous drop (for archive)
            existing_drops = index_data.get("drops", [])
            if existing_drops:
                # Exclude current drop_id if provided (for both archive and JPG)
                if args.drop_id:
                    existing_drops = [d for d in existing_drops if d.get("id") != args.drop_id]
                
                if existing_drops:
                    # Drops are sorted by published_at (newest first)
                    previous_drop_id = existing_drops[0].get("id")
                    print(f"Previous drop found: {previous_drop_id}")
                    
                    # Load previous rankings for all weights
                    if args.gender == 'boys':
                        weights = KY_HS_BOYS_WEIGHTS
                    else:
                        weights = KY_HS_GIRLS_WEIGHTS
                    
                    for weight in weights:
                        previous_rankings = load_previous_drop_rankings(
                            archive_base, args.gender, args.season, weight, previous_drop_id
                        )
                        if previous_rankings:
                            previous_rankings_map[str(weight)] = previous_rankings
                            print(f"  Loaded previous rankings for {weight}: {len(previous_rankings)} wrestlers")
                        else:
                            print(f"  DEBUG: No previous rankings loaded for {weight}")
        except Exception as e:
            print(f"Warning: Could not load previous drop rankings: {e}")
    
    # Generate archive if requested
    if args.archive:
        print(f"\n{'='*60}")
        print(f"Creating archive for {args.gender} {args.season}...")
        print(f"{'='*60}")
        archive_base = Path(args.archive_base)
        
        # Create individual rankings archive
        create_baseline_archive(
            season=args.season,
            gender=args.gender,
            drop_id=args.drop_id,
            archive_base=archive_base,
            force=args.force
        )
        
        # Generate team tournament rankings archive
        print(f"\n{'='*60}")
        print(f"Creating Team Tournament Rankings archive...")
        print(f"{'='*60}")
        generate_team_tournament_rankings(
            season=args.season,
            gender=args.gender,
            drop_id=args.drop_id,
            archive_base=archive_base,
            previous_drop_id=previous_drop_id
        )
        
        # Generate dual rankings archive
        print(f"\n{'='*60}")
        print(f"Creating Dual Rankings archive...")
        print(f"{'='*60}")
        generate_dual_rankings(
            season=args.season,
            gender=args.gender,
            drop_id=args.drop_id,
            archive_base=archive_base,
            previous_drop_id=previous_drop_id
        )
    
    # Load weight class data (shared for PDF and JPG)
    all_weight_data = None
    if args.pdf or args.jpg:
        all_weight_data = {}
        if args.gender == 'boys':
            weights = KY_HS_BOYS_WEIGHTS
        else:
            weights = KY_HS_GIRLS_WEIGHTS
        
        print(f"\n{'='*60}")
        print(f"Loading data for {len(weights)} weight classes...")
        print(f"{'='*60}")
        
        for weight_class in weights:
            weight_str = str(weight_class)
            try:
                # Use previous rankings for movement if available
                previous_rankings = previous_rankings_map.get(weight_str)
                
                wrestlers, region_places, team_best_wrestler = get_weight_class_data(
                    weight_str, args.season, args.gender, region_mapping, top_n=40,
                    placement_notes=placement_notes, previous_rankings=previous_rankings
                )
                if wrestlers:
                    all_weight_data[weight_str] = (wrestlers, region_places, team_best_wrestler)
                    print(f"  Loaded {weight_class}: {len(wrestlers)} wrestlers")
                    
                    # Debug: Check if movement was calculated
                    if previous_rankings:
                        wrestlers_with_movement = [w for w in wrestlers if (w.get('movement') is not None and w.get('movement') != 0) or w.get('is_new')]
                        if wrestlers_with_movement:
                            print(f"    DEBUG: Found {len(wrestlers_with_movement)} wrestlers with movement/new status")
                            # Show first few examples
                            for w in wrestlers_with_movement[:3]:
                                print(f"      - {w.get('name')}: movement={w.get('movement')}, is_new={w.get('is_new')}, prev_rank={w.get('previous_rank')}")
                        else:
                            print(f"    DEBUG: No movement calculated (previous_rankings has {len(previous_rankings)} entries, checking first wrestler...)")
                            if wrestlers:
                                first_w = wrestlers[0]
                                wid = first_w.get('wrestler_id')
                                prev_rank = previous_rankings.get(wid) if wid else None
                                print(f"      First wrestler: {first_w.get('name')}, ID={wid}, prev_rank={prev_rank}, current_rank={first_w.get('rank')}")
                    else:
                        print(f"    DEBUG: No previous_rankings provided for {weight_class}")
            except FileNotFoundError:
                print(f"  Skipping {weight_class}: rankings file not found")
    
    # Generate PDF if requested
    if args.pdf:
        if not REPORTLAB_AVAILABLE:
            print(f"\n{'='*60}")
            print("Skipping PDF generation (reportlab not installed)")
            print("Install with: pip install reportlab")
            print(f"{'='*60}")
        else:
            print(f"\n{'='*60}")
            print(f"Generating PDF report...")
            print(f"{'='*60}")
            output_dir = Path(f"mt/graphics/{args.season}")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"hs_rankings_{args.gender}_{args.season}.pdf"
            
            generate_pdf_report(
                season=args.season,
                gender=args.gender,
                output_path=output_path,
                all_weight_data=all_weight_data,
                region_mapping=region_mapping
            )
    
    # Generate JPG if requested
    jpg_files_generated = []
    if args.jpg:
        if not CAIROSVG_AVAILABLE:
            print(f"\n{'='*60}")
            print("Skipping JPG generation (cairosvg/PIL not installed)")
            print(f"{'='*60}")
        else:
            print(f"\n{'='*60}")
            print(f"Generating SVG/JPG graphics...")
            print(f"{'='*60}")
            output_dir = Path(f"mt/graphics/{args.season}")
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Use drop_id for JPG filename date when provided (e.g. 2026-02-03 -> 20260203)
            release_date_yyyymmdd = None
            if args.drop_id and re.match(r"^\d{4}-\d{2}-\d{2}$", args.drop_id):
                release_date_yyyymmdd = args.drop_id.replace("-", "")
            
            generate_svg_graphics(
                season=args.season,
                gender=args.gender,
                all_weight_data=all_weight_data,
                region_mapping=region_mapping,
                output_dir=output_dir,
                release_date_yyyymmdd=release_date_yyyymmdd
            )
            
            # Collect generated JPG files for PDF combination
            if args.gender == 'boys':
                weight_classes = [str(w) for w in KY_HS_BOYS_WEIGHTS]
            else:
                weight_classes = [str(w) for w in KY_HS_GIRLS_WEIGHTS]
            
            date_str = release_date_yyyymmdd or datetime.now().strftime("%Y%m%d")
            for i in range(0, len(weight_classes), 2):
                weight1 = weight_classes[i]
                if i + 1 < len(weight_classes):
                    weight2 = weight_classes[i + 1]
                    jpg_filename = f"hs_top40_{args.gender}_{date_str}_{weight1}_{weight2}.jpg"
                    jpg_path = output_dir / jpg_filename
                    if jpg_path.exists():
                        jpg_files_generated.append(jpg_path)
            
            # Combine JPGs into PDF if drop_id is provided
            if args.drop_id and jpg_files_generated:
                print(f"\n{'='*60}")
                print(f"Combining JPGs into PDF...")
                print(f"{'='*60}")
                
                # Save PDF to frontend-accessible location
                pdf_dir = Path(args.archive_base) / args.gender / str(args.season) / args.drop_id
                pdf_dir.mkdir(parents=True, exist_ok=True)
                pdf_path = pdf_dir / "rankings.pdf"
                
                try:
                    combine_jpgs_to_pdf(jpg_files_generated, pdf_path)
                except Exception as e:
                    print(f"Warning: Could not create PDF: {e}")
                    import traceback
                    traceback.print_exc()
    
    print(f"\n{'='*60}")
    print("✓ Rankings release generation complete!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()

