#!/usr/bin/env python3
"""
Show all ranked freshmen at each weight class and generate SVG/JPG graphics.

Prints to console: name, school, ranking for each weight.
Freshman only (grade 9).
Generates SVG and JPG graphics from template for each weight class.
"""

import argparse
import json
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


def normalize_grade(grade: str) -> bool:
    """Check if grade indicates freshman (9th grade)."""
    if not grade:
        return False
    
    grade_lower = grade.lower().strip()
    # Check for various freshman indicators
    freshman_indicators = ["9", "9th", "fr.", "freshman"]
    
    return any(indicator in grade_lower for indicator in freshman_indicators)


def load_rankings(season: int, gender: str, data_dir: str = "mt/rankings_data") -> Dict[int, List[Dict]]:
    """Load all rankings files, organized by weight class."""
    base_dir = Path(data_dir) / f"hs_ky_{gender}" / str(season)
    
    if not base_dir.exists():
        raise FileNotFoundError(f"Rankings directory not found: {base_dir}")
    
    rankings_by_weight = defaultdict(list)
    
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
                rankings_by_weight[weight].append({
                    "wrestler_id": entry.get("wrestler_id"),
                    "name": entry.get("name", ""),
                    "team": entry.get("team", ""),
                    "rank": entry.get("rank"),
                    "record": entry.get("record", ""),  # May be in rankings file
                })
        except Exception as e:
            print(f"Warning: Could not load {rankings_file}: {e}")
            continue
    
    return dict(rankings_by_weight)


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


def format_name_parts(name: str) -> Tuple[str, str]:
    """Split name into first name (ALL CAPS) and last name (Capitalized).
    Returns: (first_name, last_name)
    """
    if not name:
        return "", ""
    
    parts = name.strip().split()
    if len(parts) == 0:
        return "", ""
    elif len(parts) == 1:
        # Single name - treat as last name
        return "", parts[0].capitalize()
    else:
        # First name(s) in ALL CAPS, last name capitalized
        first_names = " ".join(parts[:-1]).upper()
        last_name = parts[-1].capitalize()
        return first_names, last_name


def fill_svg_template(
    template_path: Path,
    weight: int,
    freshmen: List[Dict],
    output_svg_path: Path
) -> None:
    """Fill SVG template with freshmen data and save."""
    # Load template
    tree = ET.parse(template_path)
    root = tree.getroot()
    
    # Define namespaces
    ns = {
        "svg": "http://www.w3.org/2000/svg",
        "inkscape": "http://www.inkscape.org/namespaces/inkscape",
    }
    
    # Fill in data for up to 4 freshmen
    for idx in range(1, 5):
        if idx - 1 < len(freshmen):
            wrestler = freshmen[idx - 1]
            rank = str(wrestler.get("rank", ""))
            wrestler_name = wrestler.get("name", "")
            school = wrestler.get("team", "")
            record = wrestler.get("record", "0-0")
        else:
            rank = ""
            wrestler_name = ""
            school = ""
            record = ""
        
        # Find and update rank element
        rank_el = root.find(f".//svg:text[@inkscape:label='rank{idx}']", namespaces=ns)
        if rank_el is not None:
            tspan = rank_el.find("svg:tspan", ns)
            target = tspan if tspan is not None else rank_el
            target.text = rank
        
        # Find and update name element (handles nested tspan structure)
        name_el = root.find(f".//svg:text[@inkscape:label='name{idx}']", namespaces=ns)
        if name_el is not None:
            first_name, last_name = format_name_parts(wrestler_name)
            
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
        description="Show all ranked freshmen at each weight class"
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
        "--template",
        type=str,
        default="mt/graphics/templates/top_ranked_freshmen.svg",
        help="SVG template path (default: mt/graphics/templates/top_ranked_freshmen.svg)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="mt/graphics/freshmen",
        help="Output directory for SVG/JPG files (default: mt/graphics/freshmen)"
    )
    parser.add_argument(
        "--no-graphics",
        action="store_true",
        help="Skip SVG/JPG generation, only print to console"
    )
    
    args = parser.parse_args()
    
    print(f"\n{'='*80}")
    print(f"Ranked Freshmen - {args.gender.title()} {args.season}")
    print(f"{'='*80}\n")
    
    # Load rankings, grade info, and records
    print("Loading rankings, grade, and record data...")
    rankings_by_weight = load_rankings(args.season, args.gender, args.data_dir)
    grade_by_id, record_by_id = load_grade_and_record_info(args.season, args.gender, args.data_dir)
    
    print(f"Loaded rankings for {len(rankings_by_weight)} weight classes")
    print(f"Loaded grade info for {len(grade_by_id)} wrestlers")
    print(f"Loaded record info for {len(record_by_id)} wrestlers\n")
    
    # Filter freshmen and organize by weight (top 40, minimum 4)
    freshmen_by_weight = defaultdict(list)
    
    for weight, rankings in sorted(rankings_by_weight.items()):
        # First, collect ALL freshmen at this weight
        all_freshmen = []
        
        for entry in rankings:
            wid = entry.get("wrestler_id")
            if not wid:
                continue
            
            rank = entry.get("rank")
            if rank is None:
                continue
            
            grade = grade_by_id.get(wid, "")
            if normalize_grade(grade):
                # Prefer record from rankings file, fallback to calculated record
                record = entry.get("record") or record_by_id.get(wid, "0-0")
                all_freshmen.append({
                    "name": entry.get("name", "Unknown"),
                    "team": entry.get("team", "Unknown"),
                    "rank": rank,
                    "record": record,
                })
        
        # Sort by rank
        all_freshmen.sort(key=lambda x: x["rank"] if x["rank"] else 9999)
        
        # Take top 40, but ensure minimum of 4
        if len(all_freshmen) > 0:
            # Get top 40
            top_40 = [w for w in all_freshmen if w["rank"] <= 40]
            
            # If we have less than 4 in top 40, include more until we have at least 4
            if len(top_40) < 4:
                # Take at least top 4 (even if ranked > 40)
                # But don't exceed what we have available
                min_to_show = min(4, len(all_freshmen))
                freshmen_by_weight[weight] = all_freshmen[:min_to_show]
            else:
                # Use top 40
                freshmen_by_weight[weight] = top_40
    
    # Print results and generate graphics
    total_freshmen = 0
    template_path = Path(args.template)
    output_dir = Path(args.output_dir) / args.gender / str(args.season)
    
    # Check if template exists (only if generating graphics)
    if not args.no_graphics and not template_path.exists():
        print(f"Warning: SVG template not found: {template_path}")
        print("Skipping SVG/JPG generation. Use --no-graphics to suppress this warning.")
        args.no_graphics = True
    
    for weight in sorted(freshmen_by_weight.keys()):
        freshmen = freshmen_by_weight[weight]
        if not freshmen:
            continue
        
        total_freshmen += len(freshmen)
        print(f"\n{weight} lbs ({len(freshmen)} ranked freshmen):")
        print("-" * 95)
        print(f"{'Rank':<6} {'Name':<30} {'School':<30} {'Record':<10}")
        print("-" * 95)
        
        for wrestler in freshmen:
            rank = wrestler["rank"] if wrestler["rank"] else "—"
            name = wrestler["name"][:30]
            team = wrestler["team"][:30]
            record = wrestler.get("record", "0-0")
            print(f"{rank:<6} {name:<30} {team:<30} {record:<10}")
        
        # Generate SVG and JPG for this weight (top 4 only)
        if not args.no_graphics:
            top_4 = freshmen[:4]  # Only top 4 for graphics
            
            # Generate SVG
            svg_filename = f"freshmen_{weight}.svg"
            svg_path = output_dir / svg_filename
            fill_svg_template(template_path, weight, top_4, svg_path)
            
            # Generate JPG
            jpg_filename = f"freshmen_{weight}.jpg"
            jpg_path = output_dir / jpg_filename
            render_svg_to_jpg(svg_path, jpg_path, width=1080, height=1080)
    
    print(f"\n{'='*80}")
    print(f"Total: {total_freshmen} ranked freshmen across {len(freshmen_by_weight)} weight classes")
    if not args.no_graphics:
        print(f"Graphics saved to: {output_dir}")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()

