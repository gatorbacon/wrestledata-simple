#!/usr/bin/env python3
"""
find_unranked_state_placers.py

Find wrestlers who:
- Are on rosters this year
- Placed at states last year (1-8) or lost in blood round (BR)
- Have NOT wrestled a match yet this year

Output: Clean PDF sorted by performance (best to worst)
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from load_data import load_team_data


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


def load_wrestler_matches(season: int, gender: str) -> Dict[str, List]:
    """
    Load all matches for all wrestlers to determine who has wrestled.
    
    Returns:
        Dictionary mapping wrestler_id -> list of matches
    """
    data_dir = Path("mt/rankings_data") / f"hs_ky_{gender}" / str(season)
    
    wrestler_matches = defaultdict(list)
    
    # Load from weight_class_*.json files
    for wc_file in sorted(data_dir.glob("weight_class_*.json")):
        try:
            with wc_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            
            matches = data.get("matches", [])
            for match in matches:
                w1_id = match.get("wrestler1_id")
                w2_id = match.get("wrestler2_id")
                
                if w1_id:
                    wrestler_matches[w1_id].append(match)
                if w2_id:
                    wrestler_matches[w2_id].append(match)
        except Exception as e:
            print(f"Warning: Failed to load {wc_file}: {e}")
    
    return wrestler_matches


def get_performance_sort_key(note: str) -> Tuple[int, str]:
    """
    Return a sort key for performance (lower is better).
    
    Returns:
        Tuple (numeric_rank, note) where numeric_rank is:
        - 0-7 for placements 1-8
        - 8 for BR (blood round)
        - 9 for Q (qualifier)
        - 999 for unknown
    """
    note_upper = note.upper().strip()
    
    # Top 8 placements
    if note_upper in ['1', '2', '3', '4', '5', '6', '7', '8']:
        return (int(note_upper) - 1, note_upper)
    
    # Blood round
    if note_upper == 'BR':
        return (8, 'BR')
    
    # Qualifier (shouldn't be included, but handle it)
    if note_upper == 'Q':
        return (9, 'Q')
    
    # Unknown
    return (999, note_upper)


def format_performance(note: str) -> str:
    """Format placement note for display."""
    note_upper = note.upper().strip()
    
    if note_upper in ['1', '2', '3', '4', '5', '6', '7', '8']:
        return f"{note_upper}st" if note_upper == '1' else f"{note_upper}nd" if note_upper == '2' else f"{note_upper}rd" if note_upper == '3' else f"{note_upper}th"
    
    if note_upper == 'BR':
        return "Blood Round"
    
    if note_upper == 'Q':
        return "State Qualifier"
    
    return note_upper


def find_unranked_state_placers(season: int, gender: str) -> List[Dict]:
    """
    Find wrestlers who placed at states but haven't wrestled this year.
    
    Returns:
        List of dicts with name, team, performance, wrestler_id
    """
    # Load current season rosters
    teams = load_team_data(season, league='hs', state='KY', gender=gender)
    
    # Load placement notes (last year's state tournament results)
    placement_notes = load_placement_notes(season, gender)
    
    # Load matches to see who has wrestled
    wrestler_matches = load_wrestler_matches(season, gender)
    
    # Build roster lookup
    roster_wrestlers = {}
    for team in teams:
        team_name = team.get("team_name", "Unknown")
        for wrestler in team.get("roster", []):
            wid = wrestler.get("season_wrestler_id")
            name = wrestler.get("name", "Unknown")
            if wid and wid != "null":
                roster_wrestlers[wid] = {
                    "name": name,
                    "team": team_name,
                    "wrestler_id": wid
                }
    
    # Find wrestlers who:
    # 1. Are on current rosters
    # 2. Have placement notes (placed or blood round)
    # 3. Have NOT wrestled any matches this year
    unranked_placers = []
    
    for wid, note in placement_notes.items():
        # Only include top 8 placements and blood round
        if note.upper() not in ['1', '2', '3', '4', '5', '6', '7', '8', 'BR']:
            continue
        
        # Must be on current roster
        if wid not in roster_wrestlers:
            continue
        
        # Must have NO matches this year
        if wid in wrestler_matches and len(wrestler_matches[wid]) > 0:
            continue
        
        wrestler_info = roster_wrestlers[wid].copy()
        wrestler_info["performance"] = note
        unranked_placers.append(wrestler_info)
    
    # Sort by performance (best to worst)
    unranked_placers.sort(key=lambda x: get_performance_sort_key(x["performance"]))
    
    return unranked_placers


def generate_pdf(wrestlers: List[Dict], season: int, gender: str, output_path: Path):
    """Generate a clean PDF report."""
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=0.75*inch,
        leftMargin=0.75*inch,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch
    )
    
    story = []
    styles = getSampleStyleSheet()
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#111111'),
        spaceAfter=12,
        alignment=1  # Center
    )
    
    title_text = f"Unranked State Placers - {gender.capitalize()} {season}"
    story.append(Paragraph(title_text, title_style))
    story.append(Spacer(1, 0.2*inch))
    
    # Subtitle
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#555555'),
        alignment=1  # Center
    )
    
    subtitle_text = f"Wrestlers who placed at states last year but have not wrestled this season"
    story.append(Paragraph(subtitle_text, subtitle_style))
    story.append(Spacer(1, 0.3*inch))
    
    if not wrestlers:
        no_data_style = ParagraphStyle(
            'NoData',
            parent=styles['Normal'],
            fontSize=12,
            textColor=colors.HexColor('#555555'),
            alignment=1  # Center
        )
        story.append(Paragraph("No wrestlers found matching the criteria.", no_data_style))
        doc.build(story)
        return
    
    # Table data
    table_data = [["Rank", "Name", "Team", "Last Year Performance"]]
    
    for idx, wrestler in enumerate(wrestlers, start=1):
        name = wrestler["name"]
        team = wrestler["team"]
        performance = format_performance(wrestler["performance"])
        
        table_data.append([
            str(idx),
            name,
            team,
            performance
        ])
    
    # Create table
    table = Table(table_data, colWidths=[0.5*inch, 2.5*inch, 2*inch, 1.5*inch])
    
    # Table style
    table_style = TableStyle([
        # Header row
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E0E0E0')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#111111')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),  # Rank column centered
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        
        # Data rows
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#FAFAFA')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E0E0E0')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 1), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
    ])
    
    table.setStyle(table_style)
    story.append(table)
    
    # Footer
    story.append(Spacer(1, 0.2*inch))
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor('#888888'),
        alignment=1  # Center
    )
    footer_text = f"Total: {len(wrestlers)} wrestler(s)"
    story.append(Paragraph(footer_text, footer_style))
    
    doc.build(story)


def main():
    parser = argparse.ArgumentParser(
        description="Find wrestlers who placed at states but haven't wrestled this year"
    )
    parser.add_argument(
        '-season',
        type=int,
        required=True,
        help="Season year (e.g., 2026)"
    )
    parser.add_argument(
        '-gender',
        type=str,
        required=True,
        choices=['boys', 'girls'],
        help="Gender: boys or girls"
    )
    parser.add_argument(
        '-output',
        type=str,
        help="Output PDF path (default: unranked_state_placers_{gender}_{season}.pdf)"
    )
    
    args = parser.parse_args()
    
    print(f"Finding unranked state placers for {args.gender} {args.season}...")
    
    # Find wrestlers
    wrestlers = find_unranked_state_placers(args.season, args.gender)
    
    print(f"Found {len(wrestlers)} wrestler(s) matching criteria")
    
    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = Path(f"unranked_state_placers_{args.gender}_{args.season}.pdf")
    
    # Generate PDF
    print(f"Generating PDF: {output_path}")
    generate_pdf(wrestlers, args.season, args.gender, output_path)
    
    print(f"✓ PDF generated: {output_path}")


if __name__ == "__main__":
    main()

