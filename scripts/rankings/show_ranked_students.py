#!/usr/bin/env python3
"""
Show all ranked students at each weight class and generate SVG/JPG graphics.

Supports:
- Freshmen (9th grade)
- Middle schoolers (7th and 8th grade)

Prints to console: name, school, ranking for each weight.
Generates SVG and JPG graphics from template for each weight class.
"""

import argparse
import json
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Tuple, Optional

try:
    import cairosvg
    from PIL import Image
    CAIROSVG_AVAILABLE = True
except ImportError:
    CAIROSVG_AVAILABLE = False


def normalize_grade(grade: str, student_type: str) -> Tuple[bool, Optional[int]]:
    """
    Check if grade matches the student type and extract grade number.
    
    Args:
        grade: Grade string (e.g., "9", "9th", "Fr.", "7", "8th")
        student_type: "freshmen" or "middleschool"
    
    Returns:
        Tuple of (is_match, grade_number)
        - is_match: True if grade matches the student type
        - grade_number: Numeric grade (7, 8, or 9) if match, None otherwise
    """
    if not grade:
        return False, None
    
    grade_lower = grade.lower().strip()
    
    if student_type == "freshmen":
        # Check for various freshman indicators (9th grade)
        freshman_indicators = ["9", "9th", "fr.", "freshman"]
        if any(indicator in grade_lower for indicator in freshman_indicators):
            return True, 9
    elif student_type == "middleschool":
        # Check for 7th or 8th grade - use word boundaries to avoid matching "17" or "18"
        # Match "7" or "7th" as whole words or at start/end
        if re.search(r'\b7\b|7th', grade_lower):
            return True, 7
        elif re.search(r'\b8\b|8th', grade_lower):
            return True, 8
    
    return False, None


def load_rankings(season: int, gender: str, data_dir: str = "mt/rankings_data") -> Tuple[Dict[int, List[Dict]], Dict[str, bool]]:
    """
    Load all rankings files, organized by weight class.
    Also returns a map of wrestler_id -> is_starter for starter filtering.
    
    Returns:
        Tuple of (rankings_by_weight, starter_by_id)
    """
    base_dir = Path(data_dir) / f"hs_ky_{gender}" / str(season)
    
    if not base_dir.exists():
        raise FileNotFoundError(f"Rankings directory not found: {base_dir}")
    
    rankings_by_weight = defaultdict(list)
    starter_by_id = {}  # wrestler_id -> is_starter (True/False)
    
    for rankings_file in sorted(base_dir.glob("rankings_*.json")):
        try:
            weight_str = rankings_file.stem.replace("rankings_", "")
            weight = int(weight_str)
        except ValueError:
            continue
        
        try:
            with rankings_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            
            for entry in data.get("rankings", []):
                wid = entry.get("wrestler_id")
                rankings_by_weight[weight].append({
                    "wrestler_id": wid,
                    "name": entry.get("name", ""),
                    "team": entry.get("team", ""),
                    "rank": entry.get("rank"),
                    "record": entry.get("record", ""),  # May be in rankings file
                })
                # Store starter status (defaults to False if not present)
                if wid:
                    starter_by_id[wid] = entry.get("is_starter", False)
        except Exception as e:
            print(f"Warning: Could not load {rankings_file}: {e}")
            continue
    
    return dict(rankings_by_weight), starter_by_id


def load_grade_and_record_info(season: int, gender: str, data_dir: str = "mt/rankings_data") -> Tuple[Dict[str, str], Dict[str, str]]:
    """Load grade and record information from weight class files."""
    base_dir = Path(data_dir) / f"hs_ky_{gender}" / str(season)
    
    if not base_dir.exists():
        return {}, {}
    
    grade_by_id = {}
    record_by_id = {}
    
    for wc_file in sorted(base_dir.glob("weight_class_*.json")):
        try:
            with wc_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            
            wrestlers = data.get("wrestlers", {})
            matches = data.get("matches", [])
            
            # Calculate wins/losses for each wrestler from matches
            wins_by_id = {}
            losses_by_id = {}
            
            for match in matches:
                result = match.get("result", "").upper()
                
                # Skip medical forfeits
                if "MFF" in result or "MEDICAL" in result:
                    continue
                
                # Handle both match formats: winner_id/loser_id or wrestler1_id/wrestler2_id
                winner_id = match.get("winner_id")
                loser_id = match.get("loser_id")
                
                # If no winner_id/loser_id, try to determine from wrestler1_id/wrestler2_id
                if not winner_id:
                    w1_id = match.get("wrestler1_id")
                    w2_id = match.get("wrestler2_id")
                    # If we can't determine winner, skip this match for stats
                    if not w1_id or not w2_id:
                        continue
                    # Without winner info, we can't count wins/losses
                    continue
                
                if winner_id:
                    wins_by_id[winner_id] = wins_by_id.get(winner_id, 0) + 1
                if loser_id:
                    losses_by_id[loser_id] = losses_by_id.get(loser_id, 0) + 1
            
            for wid, wrestler_data in wrestlers.items():
                if wid and wid not in grade_by_id:
                    grade = wrestler_data.get("grade", "")
                    grade_by_id[wid] = grade
                    
                    # Calculate record
                    wins = wins_by_id.get(wid, 0)
                    losses = losses_by_id.get(wid, 0)
                    if wins > 0 or losses > 0:
                        record_by_id[wid] = f"{wins}-{losses}"
                    else:
                        record_by_id[wid] = "0-0"
        except Exception as e:
            print(f"Warning: Could not load {wc_file}: {e}")
            continue
    
    return grade_by_id, record_by_id


def format_name_parts(name: str, grade_number: Optional[int] = None) -> Tuple[str, str]:
    """
    Split name into first name (ALL CAPS) and last name (Capitalized).
    For middle schoolers, grade number is appended to last name in parentheses.
    
    Returns: (first_name, last_name_with_grade)
    """
    if not name:
        return "", ""
    
    parts = name.strip().split()
    if len(parts) == 0:
        return "", ""
    elif len(parts) == 1:
        # Single name - treat as last name
        last_name = parts[0].capitalize()
        if grade_number:
            last_name = f"{last_name} ({grade_number})"
        return "", last_name
    else:
        # First name(s) in ALL CAPS, last name capitalized
        first_names = " ".join(parts[:-1]).upper()
        last_name = parts[-1].capitalize()
        if grade_number:
            last_name = f"{last_name} ({grade_number})"
        return first_names, last_name


def fill_svg_top40_by_weight_template(
    template_path: Path,
    students_by_weight: Dict[int, List[Dict]],
    output_svg_path: Path,
    gender: str
) -> None:
    """Fill top 40 by weight template with 3 columns - specific weight class distribution."""
    # Load template
    tree = ET.parse(template_path)
    root = tree.getroot()
    
    # Define namespaces
    ns = {
        "svg": "http://www.w3.org/2000/svg",
        "inkscape": "http://www.inkscape.org/namespaces/inkscape",
    }
    
    # Find the columns group
    columns_group = root.find(".//svg:g[@inkscape:label='columns']", namespaces=ns)
    if columns_group is None:
        print("  ⚠ Warning: Could not find columns group in template")
        return
    
    # Clear existing content
    columns_group.clear()
    
    # First, collect all top-40 ranked middle schoolers grouped by weight class
    top40_by_weight = {}
    for weight in sorted(students_by_weight.keys()):
        students = students_by_weight[weight]
        top40_in_weight = [s for s in students if s.get("rank") is not None and s.get("rank") <= 40]
        if top40_in_weight:
            # Sort by rank within weight
            top40_in_weight.sort(key=lambda x: x.get("rank", 9999))
            top40_by_weight[weight] = top40_in_weight
    
    # Define column assignments (as specified by user)
    column_1_weights = [106, 132, 138]
    column_2_weights = [113, 150, 190]
    column_3_weights = [120, 126, 157]
    
    # Layout parameters
    header_height = 90  # ~15% of 1080 = 162, but we'll use 90 for compact header
    start_y = header_height + 10
    available_height = 1080 - start_y - 20  # Leave room for footer
    column_width = 340  # 1080 / 3 = 360, but leave some margin
    col1_x = 30
    col2_x = 370
    col3_x = 710
    
    weight_header_height = 22
    row_height = 30  # Name line (15px) + school line (12px) + spacing
    weight_spacing = 5
    
    # Helper function to add weight header
    def add_weight_header(parent, x, y, weight):
        header_text = ET.SubElement(parent, "text", {
            "x": str(x),
            "y": str(y),
            "font-family": "Arial, sans-serif",
            "font-size": "16",
            "font-weight": "bold",
            "fill": "#000000"
        })
        header_text.text = f"{weight} lbs"
        return y + weight_header_height + 2
    
    # Helper function to add wrestler row
    def add_wrestler_row(parent, x, y, wrestler):
        rank = wrestler.get("rank", "")
        wrestler_name = wrestler.get("name", "")
        grade_number = wrestler.get("grade_number")
        school = wrestler.get("team", "")
        
        # Format name with grade
        if grade_number:
            name_with_grade = f"{wrestler_name} ({grade_number})"
        else:
            name_with_grade = wrestler_name
        
        # Capitalize name properly
        name_parts = name_with_grade.split()
        name_formatted = " ".join([part.capitalize() for part in name_parts])
        
        # Rank (bold) — Name (Grade) on first line
        # Use tspan for mixed formatting
        rank_name_group = ET.SubElement(parent, "text", {
            "x": str(x),
            "y": str(y),
            "font-family": "Arial, sans-serif",
            "font-size": "15",
            "fill": "#000000"
        })
        
        # Rank (bold)
        rank_tspan = ET.SubElement(rank_name_group, "tspan", {
            "font-weight": "bold"
        })
        rank_tspan.text = f"{rank}  "
        
        # Name (regular)
        name_tspan = ET.SubElement(rank_name_group, "tspan")
        name_tspan.text = name_formatted
        
        # School on second line (smaller, lighter)
        school_text = ET.SubElement(parent, "text", {
            "x": str(x),
            "y": str(y + 16),
            "font-family": "Arial, sans-serif",
            "font-size": "12",  # ~80% of 15
            "fill": "#666666"
        })
        school_text.text = school
        
        # Return new y position (name line + school line + small spacing)
        return y + row_height
    
    # Fill Column 1 (106, 132, 138)
    col1_y = start_y
    for weight in column_1_weights:
        if weight in top40_by_weight:
            col1_y = add_weight_header(columns_group, col1_x, col1_y, weight)
            for wrestler in top40_by_weight[weight]:
                col1_y = add_wrestler_row(columns_group, col1_x, col1_y, wrestler)
            col1_y += weight_spacing
    
    # Fill Column 2 (113, 150, 190)
    col2_y = start_y
    for weight in column_2_weights:
        if weight in top40_by_weight:
            col2_y = add_weight_header(columns_group, col2_x, col2_y, weight)
            for wrestler in top40_by_weight[weight]:
                col2_y = add_wrestler_row(columns_group, col2_x, col2_y, wrestler)
            col2_y += weight_spacing
    
    # Fill Column 3 (120, 126, 157)
    col3_y = start_y
    for weight in column_3_weights:
        if weight in top40_by_weight:
            col3_y = add_weight_header(columns_group, col3_x, col3_y, weight)
            for wrestler in top40_by_weight[weight]:
                col3_y = add_wrestler_row(columns_group, col3_x, col3_y, wrestler)
            col3_y += weight_spacing
    
    # Update subtitle based on gender
    subtitle_text = "Kentucky Boys Wrestling" if gender == "boys" else "Kentucky Girls Wrestling"
    date_str = datetime.now().strftime("%m.%d.%Y")
    full_subtitle = f"{subtitle_text} — {date_str}"
    
    subtitle_el = root.find(".//svg:text[@inkscape:label='subtitle']", namespaces=ns)
    if subtitle_el is not None:
        tspan = subtitle_el.find("svg:tspan", ns)
        target = tspan if tspan is not None else subtitle_el
        target.text = full_subtitle
    
    # Save SVG
    output_svg_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(output_svg_path, encoding="utf-8", xml_declaration=True)
    print(f"  ✓ SVG generated: {output_svg_path}")


def fill_svg_list_template(
    template_path: Path,
    weight: int,
    students: List[Dict],
    output_svg_path: Path,
    max_rows: int = 18
) -> None:
    """Fill comprehensive list SVG template with all student data and save."""
    # Load template
    tree = ET.parse(template_path)
    root = tree.getroot()
    
    # Define namespaces
    ns = {
        "svg": "http://www.w3.org/2000/svg",
        "inkscape": "http://www.inkscape.org/namespaces/inkscape",
    }
    
    # Fill in data for up to max_rows students
    for idx in range(1, max_rows + 1):
        if idx - 1 < len(students):
            wrestler = students[idx - 1]
            rank = str(wrestler.get("rank", ""))
            wrestler_name = wrestler.get("name", "")
            school = wrestler.get("team", "")
            grade_number = wrestler.get("grade_number")  # For middle schoolers
            
            # Format name with grade in parentheses for middle schoolers
            if grade_number:
                display_name = f"{wrestler_name} ({grade_number})"
            else:
                display_name = wrestler_name
        else:
            rank = ""
            display_name = ""
            school = ""
        
        # Find and update rank element
        rank_el = root.find(f".//svg:text[@inkscape:label='rank{idx}']", namespaces=ns)
        if rank_el is not None:
            tspan = rank_el.find("svg:tspan", ns)
            target = tspan if tspan is not None else rank_el
            target.text = rank
        
        # Find and update name element
        name_el = root.find(f".//svg:text[@inkscape:label='name{idx}']", namespaces=ns)
        if name_el is not None:
            tspan = name_el.find("svg:tspan", ns)
            target = tspan if tspan is not None else name_el
            target.text = display_name
        
        # Find and update school/team element
        school_el = root.find(f".//svg:text[@inkscape:label='team{idx}']", namespaces=ns)
        if school_el is not None:
            tspan = school_el.find("svg:tspan", ns)
            target = tspan if tspan is not None else school_el
            target.text = school
    
    # Update weight class text
    weightclass_el = root.find(".//svg:text[@inkscape:label='weightclass']", namespaces=ns)
    if weightclass_el is not None:
        tspan = weightclass_el.find("svg:tspan", ns)
        target = tspan if tspan is not None else weightclass_el
        target.text = f"AT {weight} POUNDS"
    
    # Update date text (format: mm.dd.yyyy)
    date_str = datetime.now().strftime("%m.%d.%Y")
    date_el = root.find(".//svg:text[@inkscape:label='date']", namespaces=ns)
    if date_el is not None:
        tspan = date_el.find("svg:tspan", ns)
        target = tspan if tspan is not None else date_el
        target.text = date_str
    
    # Save SVG
    output_svg_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(output_svg_path, encoding="utf-8", xml_declaration=True)
    print(f"  ✓ SVG generated: {output_svg_path}")


def fill_svg_template(
    template_path: Path,
    weight: int,
    students: List[Dict],
    output_svg_path: Path
) -> None:
    """Fill SVG template with student data and save."""
    # Load template
    tree = ET.parse(template_path)
    root = tree.getroot()
    
    # Define namespaces
    ns = {
        "svg": "http://www.w3.org/2000/svg",
        "inkscape": "http://www.inkscape.org/namespaces/inkscape",
    }
    
    # Fill in data for up to 4 students
    for idx in range(1, 5):
        if idx - 1 < len(students):
            wrestler = students[idx - 1]
            rank = str(wrestler.get("rank", ""))
            wrestler_name = wrestler.get("name", "")
            school = wrestler.get("team", "")
            record = wrestler.get("record", "0-0")
            grade_number = wrestler.get("grade_number")  # For middle schoolers
        else:
            rank = ""
            wrestler_name = ""
            school = ""
            record = ""
            grade_number = None
        
        # Find and update rank element
        rank_el = root.find(f".//svg:text[@inkscape:label='rank{idx}']", namespaces=ns)
        if rank_el is not None:
            tspan = rank_el.find("svg:tspan", ns)
            target = tspan if tspan is not None else rank_el
            target.text = rank
        
        # Find and update name element (handles nested tspan structure)
        name_el = root.find(f".//svg:text[@inkscape:label='name{idx}']", namespaces=ns)
        if name_el is not None:
            first_name, last_name = format_name_parts(wrestler_name, grade_number)
            
            # Find the first tspan (contains first name)
            first_tspan = name_el.find("svg:tspan", ns)
            if first_tspan is not None:
                # Set first name in first tspan (with trailing space if last name exists)
                first_tspan.text = f"{first_name} " if last_name else first_name
                
                # Find nested tspan for last name
                nested_tspan = first_tspan.find("svg:tspan", ns)
                if nested_tspan is not None:
                    nested_tspan.text = last_name
                elif last_name:
                    # If no nested tspan exists, append to first tspan
                    first_tspan.text = f"{first_name} {last_name}" if first_name else last_name
            else:
                # No tspan structure, just set text directly
                name_el.text = f"{first_name} {last_name}" if first_name else last_name
        
        # Find and update school element
        school_el = root.find(f".//svg:text[@inkscape:label='school{idx}']", namespaces=ns)
        if school_el is not None:
            tspan = school_el.find("svg:tspan", ns)
            target = tspan if tspan is not None else school_el
            target.text = school
        
        # Find and update record element
        record_el = root.find(f".//svg:text[@inkscape:label='record{idx}']", namespaces=ns)
        if record_el is not None:
            tspan = record_el.find("svg:tspan", ns)
            target = tspan if tspan is not None else record_el
            target.text = record
    
    # Update weight class text
    weightclass_el = root.find(".//svg:text[@inkscape:label='weightclass']", namespaces=ns)
    if weightclass_el is not None:
        tspan = weightclass_el.find("svg:tspan", ns)
        target = tspan if tspan is not None else weightclass_el
        target.text = f"AT {weight} POUNDS"
    
    # Update date text (format: mm.dd.yyyy)
    date_str = datetime.now().strftime("%m.%d.%Y")
    date_el = root.find(".//svg:text[@inkscape:label='date']", namespaces=ns)
    if date_el is not None:
        tspan = date_el.find("svg:tspan", ns)
        target = tspan if tspan is not None else date_el
        target.text = date_str
    
    # Save SVG
    output_svg_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(output_svg_path, encoding="utf-8", xml_declaration=True)
    print(f"  ✓ SVG generated: {output_svg_path}")


def render_svg_to_jpg(svg_path: Path, jpg_path: Path, width: int = 1080, height: int = 1080) -> None:
    """Render SVG to JPG using cairosvg."""
    if not CAIROSVG_AVAILABLE:
        print("  ⚠ Warning: cairosvg/PIL not available. Skipping JPG generation.")
        return
    
    jpg_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Render SVG to PNG in memory, then convert to JPG via Pillow
    png_bytes = cairosvg.svg2png(url=str(svg_path), output_width=width, output_height=height)
    img = Image.open(BytesIO(png_bytes)).convert("RGB")
    img.save(jpg_path, format="JPEG", quality=95)
    print(f"  ✓ JPG generated: {jpg_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Show all ranked students (freshmen or middle schoolers) at each weight class"
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
        "--type",
        type=str,
        required=True,
        choices=["freshmen", "middleschool"],
        help="Student type: 'freshmen' (9th grade) or 'middleschool' (7th and 8th grade)"
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="mt/rankings_data",
        help="Data directory (default: mt/rankings_data)"
    )
    parser.add_argument(
        "--template",
        type=str,
        help="SVG template path (default: auto-selected based on type)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        help="Output directory for SVG/JPG files (default: auto-selected based on type)"
    )
    parser.add_argument(
        "--no-graphics",
        action="store_true",
        help="Skip SVG/JPG generation, only print to console"
    )
    
    args = parser.parse_args()
    
    # Set defaults based on type
    if args.template is None:
        if args.type == "freshmen":
            args.template = "mt/graphics/templates/top_ranked_freshmen.svg"
        else:  # middleschool
            args.template = "mt/graphics/templates/top_ranked_middleschool.svg"
    
    if args.output_dir is None:
        if args.type == "freshmen":
            args.output_dir = "mt/graphics/freshmen"
        else:  # middleschool
            args.output_dir = "mt/graphics/middleschool"
    
    type_label = "Freshmen" if args.type == "freshmen" else "Middle Schoolers"
    print(f"\n{'='*80}")
    print(f"Ranked {type_label} - {args.gender.title()} {args.season}")
    print(f"{'='*80}\n")
    
    # Load rankings, grade info, and records
    print("Loading rankings, grade, and record data...")
    rankings_by_weight, starter_by_id = load_rankings(args.season, args.gender, args.data_dir)
    grade_by_id, record_by_id = load_grade_and_record_info(args.season, args.gender, args.data_dir)
    
    print(f"Loaded rankings for {len(rankings_by_weight)} weight classes")
    print(f"Loaded grade info for {len(grade_by_id)} wrestlers")
    print(f"Loaded record info for {len(record_by_id)} wrestlers\n")
    
    # Filter students and organize by weight
    # Keep all students for top 50 report, but use top 40 (min 4) for main report and graphics
    all_students_by_weight = defaultdict(list)  # All students for top 50 report
    students_by_weight = defaultdict(list)  # Top 40 (min 4) for main report and graphics
    
    for weight, rankings in sorted(rankings_by_weight.items()):
        # First, collect ALL matching students at this weight
        all_students = []
        
        for entry in rankings:
            wid = entry.get("wrestler_id")
            if not wid:
                continue
            
            rank = entry.get("rank")
            if rank is None:
                continue
            
            grade = grade_by_id.get(wid, "")
            is_match, grade_number = normalize_grade(grade, args.type)
            
            if is_match:
                # Prefer record from rankings file, fallback to calculated record
                record = entry.get("record") or record_by_id.get(wid, "0-0")
                student_data = {
                    "wrestler_id": wid,  # Store ID for starter checking
                    "name": entry.get("name", "Unknown"),
                    "team": entry.get("team", "Unknown"),
                    "rank": rank,
                    "record": record,
                }
                # For middle schoolers, store grade number for display
                if args.type == "middleschool" and grade_number:
                    student_data["grade_number"] = grade_number
                all_students.append(student_data)
        
        # Sort by rank
        all_students.sort(key=lambda x: x["rank"] if x["rank"] else 9999)
        
        # Store all students for top 50 report
        if len(all_students) > 0:
            all_students_by_weight[weight] = all_students
            
            # Take top 40, but ensure minimum of 4 for main report/graphics
            # Get top 40
            top_40 = [w for w in all_students if w["rank"] <= 40]
            
            # If we have less than 4 in top 40, include more until we have at least 4
            if len(top_40) < 4:
                # Take at least top 4 (even if ranked > 40)
                # But don't exceed what we have available
                min_to_show = min(4, len(all_students))
                students_by_weight[weight] = all_students[:min_to_show]
            else:
                # Use top 40
                students_by_weight[weight] = top_40
    
    # Print results and generate graphics
    total_students = 0
    template_path = Path(args.template)
    output_dir = Path(args.output_dir) / args.gender / str(args.season)
    
    # Check if template exists (only if generating graphics)
    if not args.no_graphics and not template_path.exists():
        print(f"Warning: SVG template not found: {template_path}")
        print("Skipping SVG/JPG generation. Use --no-graphics to suppress this warning.")
        args.no_graphics = True
    
    for weight in sorted(students_by_weight.keys()):
        students = students_by_weight[weight]
        if not students:
            continue
        
        total_students += len(students)
        type_label_lower = args.type.replace("middleschool", "middle schoolers")
        print(f"\n{weight} lbs ({len(students)} ranked {type_label_lower}):")
        print("-" * 95)
        print(f"{'Rank':<6} {'Name':<30} {'School':<30} {'Record':<10}")
        print("-" * 95)
        
        for wrestler in students:
            rank = wrestler["rank"] if wrestler["rank"] else "—"
            name = wrestler["name"][:30]
            # For middle schoolers, add grade in parentheses
            if args.type == "middleschool" and wrestler.get("grade_number"):
                name = f"{name} ({wrestler['grade_number']})"
            name = name[:30]  # Truncate after adding grade
            team = wrestler["team"][:30]
            record = wrestler.get("record", "0-0")
            print(f"{rank:<6} {name:<30} {team:<30} {record:<10}")
        
        # Generate SVG and JPG for this weight
        if not args.no_graphics:
            # Both freshmen and middle schoolers: top 4 only
            top_4 = students[:4]
            
            if args.type == "freshmen":
                svg_filename = f"freshmen_{weight}.svg"
                jpg_filename = f"freshmen_{weight}.jpg"
            else:  # middleschool
                svg_filename = f"middleschool_{weight}.svg"
                jpg_filename = f"middleschool_{weight}.jpg"
            
            svg_path = output_dir / svg_filename
            fill_svg_template(template_path, weight, top_4, svg_path)
            # Generate JPG
            jpg_path = output_dir / jpg_filename
            render_svg_to_jpg(svg_path, jpg_path, width=1080, height=1080)
    
    print(f"\n{'='*80}")
    print(f"Total: {total_students} ranked {type_label_lower} across {len(students_by_weight)} weight classes")
    if not args.no_graphics:
        print(f"Graphics saved to: {output_dir}")
    print(f"{'='*80}\n")
    
    # Generate separate formatted report for top 40 at each weight
    report_title = f"TOP 40 {type_label.upper()} BY WEIGHT CLASS"
    
    print(f"\n{'='*80}")
    print(report_title)
    print(f"{'='*80}\n")
    
    for weight in sorted(all_students_by_weight.keys()):
        all_students = all_students_by_weight[weight]
        if not all_students:
            continue
        
        # Filter to top 40
        top_40 = [s for s in all_students if s["rank"] and s["rank"] <= 40]
        if not top_40:
            continue
        
        print(f"{weight} lbs ({len(top_40)} ranked {type_label_lower}):")
        print("-" * 95)
        print(f"{'Rank':<6} {'Name':<30} {'School':<30} {'Record':<10}")
        print("-" * 95)
        
        for wrestler in top_40:
            rank = wrestler["rank"] if wrestler["rank"] else "—"
            name = wrestler["name"][:30]
            # For middle schoolers, add grade in parentheses
            if args.type == "middleschool" and wrestler.get("grade_number"):
                name = f"{name} ({wrestler['grade_number']})"
            name = name[:30]  # Truncate after adding grade
            team = wrestler["team"][:30]
            record = wrestler.get("record", "0-0")
            print(f"{rank:<6} {name:<30} {team:<30} {record:<10}")
        print()  # Blank line between weight classes
    
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()

