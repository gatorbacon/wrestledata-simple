#!/usr/bin/env python3
"""
Generate editable HTML matrix for manual ranking.

This script creates an interactive HTML matrix where you can manually
adjust wrestler rankings and save them to JSON files.
"""

import json
import re
import shutil
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Optional


def abbreviate_name(full_name: str) -> str:
    """
    Return a short version of the name for column headers:
    First initial + last name (e.g., 'Levi Haines' -> 'L. Haines').
    """
    if not full_name:
        return ""
    parts = full_name.split()
    if len(parts) == 1:
        return parts[0]
    first_initial = parts[0][0]
    last = parts[-1]
    return f"{first_initial}. {last}"


def parse_match_date(date_str: str) -> date | None:
    """Parse a match date in MM/DD/YYYY form to a date object."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%m/%d/%Y").date()
    except Exception:
        return None


def is_recent_date(date_str: str, today: date, days: int = 7) -> bool:
    """
    Return True if date_str is within the last `days` days relative to `today`.
    """
    d = parse_match_date(date_str)
    if not d:
        return False
    delta = today - d
    return timedelta(0) <= delta <= timedelta(days=days)


def classify_result_type(result: str) -> str:
    """
    Classify a single match result string into a display code.
    
    Categories:
        - D   : Decision (incl. SV-1, SV-2)
        - MD  : Major Decision
        - TF  : Technical Fall
        - F   : Fall (pin)
        - INJ : Injury-related (injury fall/default)
        - O   : Other / unknown
    """
    if not result:
        return "O"
    
    r = result.lower()
    
    # Medical forfeit (scraped as "MFFL" or "M. For.")
    if "mffl" in r or "m. for." in r or "medical forfeit" in r:
        return "MFF"
    
    # No contest
    clean = r.strip()
    if clean == "nc" or "no contest" in clean:
        return "NC"
    
    # Injury-related first
    if "inj" in r or "injury" in r:
        return "INJ"
    
    # Falls (but not injury falls)
    if "fall" in r or " pin" in r or r.startswith("fall"):
        return "F"
    
    # Technical fall
    if "tf" in r or "technical fall" in r:
        return "TF"
    
    # Major decision
    if "md" in r or "major" in r:
        return "MD"
    
    # Regular decision (including sudden victory)
    if "dec" in r or "sv-" in r:
        return "D"
    
    return "O"


def classify_best_win(matches: List[Dict], winner_id: str) -> str:
    """
    Given a list of match dicts and a winner_id, choose the best
    (most dominant) result type code for that winner.
    """
    # Lower rank is "better" / more dominant
    rank_order = {
        "F": 0,
        "TF": 1,
        "INJ": 2,
        "MFF": 3,
        "MD": 4,
        "D": 5,
        "NC": 6,
        "O": 7
    }
    
    best_code = "O"
    best_rank = rank_order[best_code]
    
    for m in matches:
        if m.get("winner_id") != winner_id:
            continue
        code = classify_result_type(m.get("result", ""))
        rank = rank_order.get(code, rank_order["O"])
        if rank < best_rank:
            best_code = code
            best_rank = rank
    
    return best_code


def severity_for_result_code(code: str) -> str:
    """
    Map a result code to a severity level for cell shading.
    
    - strong : Fall / Technical Fall
    - medium : Major Decision
    - light  : Decision / Other
    - co     : Medical forfeit (MFF) / Injury (INJ), styled like common opponents
    - nc     : No contest (NC), neutral grey for both wrestlers
    """
    if code == "NC":
        return "nc"
    if code in ("MFF", "INJ"):
        return "co"
    if code in ("F", "TF"):
        return "strong"
    if code == "MD":
        return "medium"
    return "light"


def format_result_for_tooltip(result: str) -> str:
    """
    Format a raw result string into a readable phrase for tooltips.
    
    Examples:
        "Dec 3-2"        -> "Decision 3-2"
        "Fall 4:32"      -> "Fall"
        "MD 12-3"        -> "Major Decision 12-3"
        "TF 18-0 2:33"   -> "Technical Fall"
    """
    if not result:
        return "Decision"
    
    code = classify_result_type(result)
    # Try to pull out a score like "3-2"
    score_match = re.search(r"(\\d+-\\d+)", result)
    score = score_match.group(1) if score_match else ""
    
    if code == "F":
        return "Fall"
    if code == "TF":
        return "Technical Fall"
    if code == "MD":
        return f"Major Decision {score}" if score else "Major Decision"
    if code == "D":
        return f"Decision {score}" if score else "Decision"
    if code == "INJ":
        return "Injury Default"
    if code == "NC":
        return "No Contest"
    
    # Fallback: return the raw result trimmed
    return result.strip()


def build_matrix_data(
    relationships_data: Dict, placement_notes: Optional[Dict[str, str]] = None
) -> Dict:
    """
    Build matrix data structure from relationships.
    
    Args:
        relationships_data: Dictionary with wrestlers and relationships
        
    Returns:
        Dictionary with matrix data for HTML generation
    """
    wrestlers = relationships_data['wrestlers']
    direct_rels = relationships_data.get('direct_relationships', {})
    co_rels = relationships_data.get('common_opponent_relationships', {})
    
    # Determine ordering for wrestlers
    ranking_order: List[str] = relationships_data.get('ranking_order', [])
    placement_notes = placement_notes or {}

    if ranking_order:
        # Use saved ranking order where available
        wrestler_list = []
        seen = set()
        for wid in ranking_order:
            if wid in wrestlers and wid not in seen:
                info = dict(wrestlers[wid])
                info['is_unranked'] = False
                note = placement_notes.get(wid)
                if note:
                    info['placement_note'] = note
                wrestler_list.append((wid, info))
                seen.add(wid)
        # Append any wrestlers not present in the ranking file
        for wid, winfo in sorted(wrestlers.items(), key=lambda x: x[0]):
            if wid not in seen:
                info = dict(winfo)
                info['is_unranked'] = True
                note = placement_notes.get(wid)
                if note:
                    info['placement_note'] = note
                wrestler_list.append((wid, info))
    else:
        # Fallback: sort by ID for initial ordering
        wrestler_list = []
        for wid, winfo in sorted(wrestlers.items(), key=lambda x: x[0]):
            info = dict(winfo)
            info['is_unranked'] = True
            note = placement_notes.get(wid)
            if note:
                info['placement_note'] = note
            wrestler_list.append((wid, info))
    
    # Build matrix
    matrix = {}
    today = datetime.today().date()
    
    for i, (w1_id, w1_info) in enumerate(wrestler_list):
        for j, (w2_id, w2_info) in enumerate(wrestler_list):
            if i == j:
                continue
            
            # Create normalized pair key
            pair_key = tuple(sorted([w1_id, w2_id]))
            pair_key_str = f"{pair_key[0]}_{pair_key[1]}"
            
            cell_data = {
                'type': 'none',
                'value': '',
                'tooltip': ''
            }
            
            # Check direct relationships
            if pair_key_str in direct_rels:
                rel = direct_rels[pair_key_str]
                wins_1 = rel.get('direct_wins_1', 0)
                wins_2 = rel.get('direct_wins_2', 0)
                matches = rel.get('matches', [])
                
                if w1_id == rel['wrestler1_id']:
                    if wins_1 > wins_2:
                        # w1 has direct advantage
                        code = classify_best_win(matches, w1_id)
                        cell_data['type'] = 'direct_win'
                        cell_data['value'] = code
                        cell_data['tooltip'] = f"{w1_info['name']} leads head-to-head over {w2_info['name']} ({code})"
                        cell_data['severity'] = severity_for_result_code(code)
                        cell_data['matches'] = matches
                        # Recent highlight: direct matches within the last week
                        cell_data['recent'] = any(
                            is_recent_date(m.get('date', ''), today) for m in matches
                        )
                    elif wins_2 > wins_1:
                        # w2 has direct advantage
                        code = classify_best_win(matches, rel['wrestler2_id'])
                        cell_data['type'] = 'direct_loss'
                        cell_data['value'] = code
                        cell_data['tooltip'] = f"{w2_info['name']} leads head-to-head over {w1_info['name']} ({code})"
                        cell_data['severity'] = severity_for_result_code(code)
                        cell_data['matches'] = matches
                        cell_data['recent'] = any(
                            is_recent_date(m.get('date', ''), today) for m in matches
                        )
                else:
                    # w1 is rel['wrestler2_id']
                    if wins_2 > wins_1:
                        # w1 has direct advantage (as wrestler2)
                        code = classify_best_win(matches, w1_id)
                        cell_data['type'] = 'direct_win'
                        cell_data['value'] = code
                        cell_data['tooltip'] = f"{w1_info['name']} leads head-to-head over {w2_info['name']} ({code})"
                        cell_data['severity'] = severity_for_result_code(code)
                        cell_data['matches'] = matches
                        cell_data['recent'] = any(
                            is_recent_date(m.get('date', ''), today) for m in matches
                        )
                    elif wins_1 > wins_2:
                        # w2 has direct advantage
                        code = classify_best_win(matches, rel['wrestler1_id'])
                        cell_data['type'] = 'direct_loss'
                        cell_data['value'] = code
                        cell_data['tooltip'] = f"{w2_info['name']} leads head-to-head over {w1_info['name']} ({code})"
                        cell_data['severity'] = severity_for_result_code(code)
                        cell_data['matches'] = matches
                        cell_data['recent'] = any(
                            is_recent_date(m.get('date', ''), today) for m in matches
                        )
            
            # Check common opponent relationships (only if no direct relationship)
            elif pair_key_str in co_rels:
                rel = co_rels[pair_key_str]
                co_wins_1 = rel.get('common_opp_wins_1', 0)
                co_wins_2 = rel.get('common_opp_wins_2', 0)
                co_details_1 = rel.get('co_details_1', [])
                co_details_2 = rel.get('co_details_2', [])
                
                # Determine which wrestler is which in the relationship
                # rel['wrestler1_id'] and rel['wrestler2_id'] are the normalized pair
                rel_w1_id = rel['wrestler1_id']
                rel_w2_id = rel['wrestler2_id']
                
                # Map to our current wrestlers
                if w1_id == rel_w1_id:
                    # w1 is wrestler1 in relationship, w2 is wrestler2
                    if co_wins_1 > co_wins_2:
                        cell_data['type'] = 'common_win'
                        cell_data['value'] = "CO"
                        cell_data['co_details'] = co_details_1
                        cell_data['co_winner'] = w1_id
                        cell_data['co_loser'] = w2_id
                        cell_data['severity'] = 'co'
                        cell_data['tooltip'] = f"{w1_info['name']} has common opponent win(s) over {w2_info['name']}"
                    elif co_wins_2 > co_wins_1:
                        cell_data['type'] = 'common_loss'
                        cell_data['value'] = "CO"
                        cell_data['co_details'] = co_details_2
                        cell_data['co_winner'] = w2_id
                        cell_data['co_loser'] = w1_id
                        cell_data['severity'] = 'co'
                        cell_data['tooltip'] = f"{w2_info['name']} has common opponent win(s) over {w1_info['name']}"
                else:
                    # w1 is wrestler2 in relationship, w2 is wrestler1
                    if co_wins_2 > co_wins_1:
                        cell_data['type'] = 'common_win'
                        cell_data['value'] = "CO"
                        cell_data['co_details'] = co_details_2
                        cell_data['co_winner'] = w1_id
                        cell_data['co_loser'] = w2_id
                        cell_data['severity'] = 'co'
                        cell_data['tooltip'] = f"{w1_info['name']} has common opponent win(s) over {w2_info['name']}"
                    elif co_wins_1 > co_wins_2:
                        cell_data['type'] = 'common_loss'
                        cell_data['value'] = "CO"
                        cell_data['co_details'] = co_details_1
                        cell_data['co_winner'] = w2_id
                        cell_data['co_loser'] = w1_id
                        cell_data['severity'] = 'co'
                        cell_data['tooltip'] = f"{w2_info['name']} has common opponent win(s) over {w1_info['name']}"
            
            # For common-opponent cells, check if any underlying match is recent
            if cell_data.get('co_details'):
                recent_any = False
                for detail in cell_data['co_details']:
                    wm = detail.get('winner_match', {})
                    lm = detail.get('loser_match', {})
                    if is_recent_date(wm.get('date', ''), today) or is_recent_date(
                        lm.get('date', ''), today
                    ):
                        recent_any = True
                        break
                cell_data['recent'] = recent_any
            
            matrix[f"{w1_id}_{w2_id}"] = cell_data
    
    return {
        'wrestlers': [{'id': w_id, **w_info} for w_id, w_info in wrestler_list],
        'matrix': matrix
    }


def generate_html_matrix(matrix_data: Dict, weight_class: str, season: int) -> str:
    """
    Generate HTML for editable ranking matrix.
    
    Args:
        matrix_data: Dictionary with wrestlers and matrix data
        weight_class: Weight class string
        season: Season year
        
    Returns:
        HTML string
    """
    import html as html_escape
    wrestlers = matrix_data['wrestlers']
    matrix = matrix_data['matrix']
    total_wrestlers = len(wrestlers)
    
    # Build tooltip data object for JavaScript
    tooltip_data_js = {}
    
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Ranking Matrix: {weight_class} - Season {season}</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            margin-top: 0;
        }}
        .controls {{
            margin-bottom: 20px;
            padding: 10px;
            background-color: #f9f9f9;
            border-radius: 4px;
        }}
        .matrix-wrapper {{
            overflow-x: auto;
            overflow-y: auto;
            max-height: 80vh;
        }}
        table {{
            border-collapse: collapse;
            font-size: 12px;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 4px;
            text-align: center;
        }}
        th {{
            background-color: #f2f2f2;
            position: sticky;
            top: 0;
            z-index: 10;
        }}
        .header-rank-row th {{
            top: 0;
            z-index: 12;
        }}
        .header-name-row th {{
            top: 28px;
            z-index: 11;
        }}
        /* Ensure top-left corner headers stay above body cells */
        .header-rank-row .rank-col,
        .header-rank-row .wrestler-col,
        .header-name-row .rank-col,
        .header-name-row .wrestler-col {{
            z-index: 20;
        }}
        th.rotate {{
            height: 80px;
            white-space: nowrap;
            padding: 2px !important;
            font-size: 10px;
            vertical-align: bottom;
        }}
        th.rotate > div {{
            transform: rotate(270deg);
            width: 15px;
            height: 15px;
        }}
        th.rotate > div > span {{
            padding: 2px;
            display: inline-block;
        }}
        .rank-col {{
            position: sticky;
            left: 0;
            background-color: #f2f2f2;
            z-index: 15;
            width: 50px;
        }}
        .wrestler-col {{
            position: sticky;
            left: 50px;
            background-color: #f2f2f2;
            z-index: 15;
            min-width: 240px;
            text-align: left;
            padding: 8px;
        }}
        .wrestler-name {{
            font-weight: bold;
        }}
        .wrestler-main-line {{
            display: block;
        }}
        .wrestler-controls-line {{
            display: flex;
            align-items: center;
            gap: 6px;
            margin-top: 2px;
        }}
        /* Recent matches (within last 7 days when matrix generated) */
        .matrix-cell.recent {{
            border-width: 3px;
            border-style: solid;
        }}
        .matrix-cell.direct_win.recent,
        .matrix-cell.common_win.recent {{
            border-color: #008000;
        }}
        .matrix-cell.direct_loss.recent,
        .matrix-cell.common_loss.recent {{
            border-color: #cc0000;
        }}
        /* Anchor win/loss highlighting */
        .matrix-cell.anchor-win {{
            font-weight: bold;
            color: #005500;
        }}
        .matrix-cell.anchor-loss {{
            font-weight: bold;
            color: #990000;
        }}
        /* Nudge first column header a bit right so it doesn't sit under 'Wrestler' */
        .header-name-row th.rotate:first-of-type > div {{
            margin-left: 20px;
        }}
        .wrestler-team {{
            font-size: 10px;
            color: #666;
        }}
        .wrestler-note {{
            font-size: 11px;
            color: #0066ff;
            font-weight: bold;
            margin-left: 4px;
        }}
        .rank-arrows {{
            display: inline-flex;
            align-items: center;
            gap: 4px;
            margin-left: 10px;
        }}
        .wrestler-controls-line .rank-arrows {{
            margin-left: 0;
        }}
        .rank-arrow {{
            cursor: pointer;
            padding: 2px 6px;
            margin: 0 2px;
            border: 1px solid #ddd;
            border-radius: 3px;
            background: #f8f8f8;
            font-size: 14px;
        }}
        .rank-input {{
            width: 38px;
            padding: 2px;
            font-size: 11px;
            border: 1px solid #ccc;
            border-radius: 3px;
        }}
        .rank-go {{
            padding: 2px 6px;
            font-size: 11px;
            border: 1px solid #ddd;
            border-radius: 3px;
            background: #f8f8f8;
            cursor: pointer;
        }}
        .rank-go:hover {{
            background: #e8e8e8;
        }}
        .rank-setter {{
            display: inline-flex;
            align-items: center;
            margin-left: 6px;
        }}
        .rank-set-input {{
            width: 32px;
            font-size: 10px;
            padding: 1px 2px;
            margin-right: 2px;
        }}
        .rank-set-button {{
            font-size: 10px;
            padding: 1px 4px;
            cursor: pointer;
        }}
        .rank-arrow:hover {{
            background: #e8e8e8;
        }}
        .matrix-cell {{
            width: 30px;
            height: 30px;
            min-width: 30px;
            min-height: 30px;
            font-size: 9px;
            padding: 2px;
        }}
        .same-wrestler {{
            background-color: #e0e0e0;
        }}
        .direct_win {{
            background-color: #b3ffb3;
        }}
        .direct_loss {{
            background-color: #ffb3b3;
        }}
        /* Severity shading for direct wins/losses */
        .matrix-cell.direct_win.severity-strong {{
            background-color: #33cc33;
        }}
        .matrix-cell.direct_loss.severity-strong {{
            background-color: #ff3333;
        }}
        .matrix-cell.direct_win.severity-medium {{
            background-color: #66e066;
        }}
        .matrix-cell.direct_loss.severity-medium {{
            background-color: #ff6666;
        }}
        .matrix-cell.direct_win.severity-light {{
            background-color: #b3ffb3;
        }}
        .matrix-cell.direct_loss.severity-light {{
            background-color: #ffb3b3;
        }}
        /* Very light shading for common opponent cells */
        .common_win {{
            background-color: #e6ffe6;
        }}
        .common_loss {{
            background-color: #ffe6e6;
        }}
        .matrix-cell.common_win.severity-co {{
            background-color: #f2fff2;
        }}
        .matrix-cell.common_loss.severity-co {{
            background-color: #fff2f2;
        }}
        /* Medical forfeit (MFF) uses same light palette as common opponents */
        .matrix-cell.direct_win.severity-co {{
            background-color: #f2fff2;
        }}
        .matrix-cell.direct_loss.severity-co {{
            background-color: #fff2f2;
        }}
        /* No contest (NC) neutral grey for both winner and loser */
        .matrix-cell.direct_win.severity-nc,
        .matrix-cell.direct_loss.severity-nc {{
            background-color: #e6e6e6;
        }}
        .col-rank-header {{
            font-weight: bold;
        }}
        /* Unranked wrestlers */
        .unranked-row .wrestler-name {{
            background-color: #fff6a3;
            padding: 2px 4px;
            border-radius: 3px;
        }}
        .unranked-row .rank-col {{
            font-weight: bold;
        }}
        /* Wrestlers with no matches (0-0 record) */
        .no-matches-row .wrestler-name {{
            background-color: lightskyblue;
            padding: 2px 4px;
            border-radius: 3px;
        }}
        #matrix-tooltip {{
            display: none;
            position: fixed;
            background-color: #333;
            color: white;
            padding: 10px;
            border-radius: 4px;
            z-index: 10000;
            font-size: 11px;
            max-width: 400px;
            white-space: normal;
            line-height: 1.4;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
            pointer-events: none;
        }}
        .matrix-cell[data-tooltip-id] {{
            cursor: help;
        }}
        .tooltip-header {{
            font-weight: bold;
            margin-bottom: 8px;
            border-bottom: 1px solid #555;
            padding-bottom: 4px;
        }}
        .tooltip-detail {{
            margin: 6px 0;
            padding-left: 10px;
        }}
        .tooltip-match {{
            margin: 4px 0;
            padding-left: 20px;
            font-size: 10px;
            color: #ccc;
        }}
        #save-button {{
            position: fixed;
            bottom: 20px;
            right: 20px;
            padding: 12px 24px;
            background-color: #4CAF50;
            color: white;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 16px;
            font-weight: bold;
            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
        }}
        #save-button:hover {{
            background-color: #45a049;
        }}
        #save-button:disabled {{
            background-color: #ccc;
            cursor: not-allowed;
        }}
        .save-status {{
            margin-left: 10px;
            font-size: 14px;
        }}
        .save-success {{
            color: #4CAF50;
        }}
        .save-error {{
            color: #f44336;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Weight Class {weight_class} - Season {season}</h1>
        <div class="controls">
            <button id="save-button" onclick="saveRankings()">Save Rankings</button>
            <span id="save-status"></span>
        </div>
        <div class="matrix-wrapper">
            <table id="ranking-table">
                <thead>
                    <tr class="header-rank-row">
                        <th class="rank-col"></th>
                        <th class="wrestler-col"></th>
"""

    # Top header row: column ranks only
    for idx, wrestler in enumerate(wrestlers):
        col_rank = "UNR" if wrestler.get('is_unranked') else str(idx + 1)
        html_content += f"""                        <th class="col-rank-header">{col_rank}</th>
"""

    html_content += """                    </tr>
                    <tr class="header-name-row">
                        <th class="rank-col">Rank</th>
                        <th class="wrestler-col">Wrestler</th>
"""
    
    # Second header row: rotated wrestler names (first initial + last name)
    for wrestler in wrestlers:
        short_name = abbreviate_name(wrestler['name'])
        html_content += f"""                        <th class="rotate">
                            <div><span>{short_name}</span></div>
                        </th>
"""
    
    html_content += """                    </tr>
                </thead>
                <tbody>
"""
    
    # Add data rows
    for i, wrestler in enumerate(wrestlers):
        wins = wrestler.get('wins', 0) or 0
        losses = wrestler.get('losses', 0) or 0
        has_no_matches = (wins == 0 and losses == 0)
        placement_note = wrestler.get('placement_note')

        row_classes = []
        if wrestler.get('is_unranked'):
            row_classes.append("unranked-row")
        if has_no_matches:
            row_classes.append("no-matches-row")
        row_class_attr = f' class="{" ".join(row_classes)}"' if row_classes else ""

        rank_label = "UNR" if wrestler.get('is_unranked') else str(i + 1)
        note_html = (
            f'<span class="wrestler-note">({placement_note})</span>'
            if placement_note
            else ""
        )

        html_content += f"""                    <tr data-wrestler-id="{wrestler['id']}"{row_class_attr}>
                        <td class="rank-col">{rank_label}</td>
                        <td class="wrestler-col">
                            <div class="wrestler-main-line">
                            <span class="wrestler-name">{wrestler['name']}</span>
                            <span class="wrestler-team">({wrestler['team']})</span>
                            <span class="wrestler-record"> - {wins}-{losses}</span>{note_html}
                            </div>
                            <div class="wrestler-controls-line">
                            <div class="rank-arrows">
                                    <span class="rank-arrow" onclick="moveUp(this)" title="Move up">↑</span>
                                    <span class="rank-arrow" onclick="moveDown(this)" title="Move down">↓</span>
                                </div>"""
        if has_no_matches:
            html_content += f"""
                                <div class="rank-setter">
                                    <input type="number" min="1" max="{total_wrestlers}" class="rank-set-input" value="{total_wrestlers}" />
                                    <button class="rank-set-button" onclick="setRank(this)" title="Set rank">Go</button>
                                </div>"""
        else:
            html_content += f"""
                                <div class="rank-setter">
                                    <input type="number" min="1" max="{total_wrestlers}" class="rank-set-input" placeholder="#" />
                                    <button class="rank-set-button" onclick="setRank(this)" title="Set rank">Go</button>
                                </div>"""
        html_content += """
                            </div>
                        </td>
"""
        # Add matrix cells
        for j, opponent in enumerate(wrestlers):
            if i == j:
                html_content += f"""                        <td class="matrix-cell same-wrestler">-</td>
"""
            else:
                cell_key = f"{wrestler['id']}_{opponent['id']}"
                cell_data = matrix.get(cell_key, {'type': 'none', 'value': '', 'tooltip': ''})
                
                # Build lightweight tooltip ID instead of inline JSON for performance
                tooltip_data_attr = ''
                tooltip_id = None
                tooltip_info = None

                # Common-opponent tooltip
                if cell_data.get('co_details'):
                    tooltip_id = f"{wrestler['id']}_{opponent['id']}"
                    tooltip_data_attr = f' data-tooltip-id="{tooltip_id}"'
                    winner_id = cell_data.get('co_winner')
                    tooltip_info = {
                        'header': f"{wrestler['name']} has common opponent win(s) over {opponent['name']}" if winner_id == wrestler['id'] else f"{opponent['name']} has common opponent win(s) over {wrestler['name']}",
                        'details': []
                    }
                    for detail in cell_data['co_details'][:5]:
                        if detail['winner_id'] == wrestler['id']:
                            tooltip_info['details'].append({
                                'opponent': detail['opponent_name'],
                                'wrestler_result': f"{wrestler['name']} beat {detail['opponent_name']}",
                                'wrestler_match': f"({detail['winner_match']['date']}, {detail['winner_match']['result']})",
                                'opponent_result': f"{opponent['name']} lost to {detail['opponent_name']}",
                                'opponent_match': f"({detail['loser_match']['date']}, {detail['loser_match']['result']})"
                            })
                        else:
                            tooltip_info['details'].append({
                                'opponent': detail['opponent_name'],
                                'opponent_result': f"{opponent['name']} beat {detail['opponent_name']}",
                                'opponent_match': f"({detail['winner_match']['date']}, {detail['winner_match']['result']})",
                                'wrestler_result': f"{wrestler['name']} lost to {detail['opponent_name']}",
                                'wrestler_match': f"({detail['loser_match']['date']}, {detail['loser_match']['result']})"
                            })
                    if len(cell_data['co_details']) > 5:
                        tooltip_info['more_count'] = len(cell_data['co_details']) - 5

                # Direct head-to-head tooltip
                elif cell_data.get('type') in ('direct_win', 'direct_loss') and cell_data.get('matches'):
                    tooltip_id = f"{wrestler['id']}_{opponent['id']}"
                    tooltip_data_attr = f' data-tooltip-id="{tooltip_id}"'
                    tooltip_info = {
                        'header': f"{wrestler['name']} vs {opponent['name']}",
                        'details': []
                    }
                    for m in cell_data['matches'][:10]:
                        winner_id = m.get('winner_id')
                        date_str = m.get('date', '')
                        raw_result = m.get('result', '')

                        # Determine winner/loser and their teams from current cell context
                        if winner_id == wrestler['id']:
                            winner_name = wrestler['name']
                            winner_team = wrestler.get('team', '')
                            loser_name = opponent['name']
                            loser_team = opponent.get('team', '')
                        elif winner_id == opponent['id']:
                            winner_name = opponent['name']
                            winner_team = opponent.get('team', '')
                            loser_name = wrestler['name']
                            loser_team = wrestler.get('team', '')
                        else:
                            # If winner_id doesn't match either wrestler (shouldn't happen), skip this match
                            continue

                        summary_line = (
                            f"{winner_name} ({winner_team}) defeated "
                            f"{loser_name} ({loser_team}) ({raw_result})"
                        ).strip()

                        if date_str:
                            line = f"{date_str}<br>{summary_line}"
                        else:
                            line = summary_line
                    
                        tooltip_info['details'].append({'line': line})
                    
                if tooltip_id and tooltip_info:
                    tooltip_data_js[tooltip_id] = tooltip_info
                
                # Use simple title only for cells without rich tooltips
                simple_tooltip = cell_data.get('tooltip', '').replace('\\n', ' ')
                if cell_data['type'] in ('common_win', 'common_loss', 'direct_win', 'direct_loss'):
                    # Let the rich tooltip handle hover; suppress native title
                    simple_tooltip = ''
                severity_class = ''
                if cell_data.get('severity'):
                    severity_class = f" severity-{cell_data['severity']}"
                recent_class = ' recent' if cell_data.get('recent') else ''
                html_content += f"""                        <td class="matrix-cell {cell_data['type']}{severity_class}{recent_class}" title="{simple_tooltip}"{tooltip_data_attr}>
                            {cell_data['value']}
                        </td>
"""
        
        html_content += """                    </tr>
"""
    
    html_content += """                </tbody>
            </table>
        </div>
    </div>
    
    <!-- Single tooltip element for performance -->
    <div id="matrix-tooltip"></div>
    
    <script>
        console.log('Script starting to execute...'); // Debug
        const weightClass = """ + json.dumps(weight_class) + """;
        const season = """ + str(season) + """;
        const wrestlers = """ + json.dumps(wrestlers) + """;
        console.log('Variables initialized, wrestlers count:', wrestlers.length); // Debug
        
        // Store tooltip data in global object for tooltip system
        window.tooltipData = """ + json.dumps(tooltip_data_js) + """;
        
        const tooltip = document.getElementById("matrix-tooltip");
        
        // Attach handlers to all cells with tooltip IDs
        function attachTooltipHandlers() {
            document.querySelectorAll(".matrix-cell[data-tooltip-id]").forEach(cell => {
                cell.addEventListener("mouseenter", e => {
                    const id = cell.dataset.tooltipId;
                    const data = window.tooltipData[id];
        
                    if (!data) {
                        tooltip.style.display = "none";
                        return;
                    }
        
                    tooltip.innerHTML = `
                        <div class="tooltip-header">${data.header}</div>
                        ${data.details.map(d => `
                            <div class="tooltip-detail">${
                                d.line
                                    ? d.line
                                    : `${d.wrestler_result || ""}<br>${d.opponent_result || ""}`
                            }</div>
                        `).join("")}
                    `;
        
                    tooltip.style.display = "block";
                });
        
                cell.addEventListener("mousemove", e => {
                    tooltip.style.left = (e.pageX + 12) + "px";
                    tooltip.style.top = (e.pageY + 12) + "px";
                });
        
                cell.addEventListener("mouseleave", e => {
                    tooltip.style.display = "none";
                });
            });
        }
        
        // Anchor win/loss computation
        function recomputeAnchors() {
            const table = document.getElementById('ranking-table');
            if (!table) return;

            // Clear previous anchors
            table.querySelectorAll('.anchor-win, .anchor-loss').forEach(td => {
                td.classList.remove('anchor-win', 'anchor-loss');
            });

            const tbody = table.querySelector('tbody');
            if (!tbody) return;
            const rows = Array.from(tbody.querySelectorAll('tr'));

            rows.forEach(row => {
                const cells = Array.from(row.querySelectorAll('td'));
                // Skip first two columns (rank + wrestler)
                const dataCells = cells.slice(2);
                if (!dataCells.length) return;

                const lossIdxs = [];
                const winIdxs = [];

                dataCells.forEach((cell, idx) => {
                    if (cell.classList.contains('direct_loss') || cell.classList.contains('common_loss')) {
                        lossIdxs.push(idx);
                    } else if (cell.classList.contains('direct_win') || cell.classList.contains('common_win')) {
                        winIdxs.push(idx);
                    }
                });

                if (!lossIdxs.length && !winIdxs.length) {
                    return;
                }

                // Anchor win: use lowest-ranked (rightmost) loss as boundary,
                // then find the first win to the right of that boundary.
                if (lossIdxs.length) {
                    const worstLossIdx = Math.max(...lossIdxs);
                    for (let idx = worstLossIdx + 1; idx < dataCells.length; idx++) {
                        const cell = dataCells[idx];
                        if (cell.classList.contains('direct_win') || cell.classList.contains('common_win')) {
                            cell.classList.add('anchor-win');
                            break;
                        }
                    }
                }

                // Anchor loss: highest-ranked loss that has no win to its left.
                if (lossIdxs.length) {
                    const sortedLoss = lossIdxs.slice().sort((a, b) => a - b); // left to right
                    for (const lossIdx of sortedLoss) {
                        const hasHigherWin = winIdxs.some(wIdx => wIdx < lossIdx);
                        if (!hasHigherWin) {
                            dataCells[lossIdx].classList.add('anchor-loss');
                            break;
                        }
                    }
                }
            });
        }

        function initializeMatrixInteractions() {
            attachTooltipHandlers();
            recomputeAnchors();
        }

        // Initialize tooltip handlers and anchors
        window.addEventListener("DOMContentLoaded", initializeMatrixInteractions);
        
        function getRowIndexFromElement(elem) {
            const row = elem.closest('tr');
            if (!row) return -1;
            const tbody = row.parentNode;
            const rows = Array.from(tbody.querySelectorAll('tr'));
            return rows.indexOf(row);
        }
        
        function moveUp(elem) {
            const index = getRowIndexFromElement(elem);
            console.log('moveUp clicked, row index:', index);
            if (index <= 0) return;
            swapRows(index, index - 1);
            updateRanks();
            recomputeAnchors();
        }
        
        function moveDown(elem) {
            const index = getRowIndexFromElement(elem);
            console.log('moveDown clicked, row index:', index);
            const table = document.getElementById('ranking-table');
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));
            if (index < 0 || index >= rows.length - 1) return;
            swapRows(index, index + 1);
            updateRanks();
            recomputeAnchors();
        }

        // Expose movement functions globally for inline onclick handlers
        window.moveUp = moveUp;
        window.moveDown = moveDown;
        
        function swapRows(index1, index2) {
            const table = document.getElementById('ranking-table');
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));
            
            // Swap the rows in tbody
            const row1 = rows[index1];
            const row2 = rows[index2];
            if (!row1 || !row2) return;
            
            if (index1 < index2) {
                // Moving down: place row1 after row2
            tbody.insertBefore(row1, row2.nextSibling);
            } else {
                // Moving up: place row1 before row2
                tbody.insertBefore(row1, row2);
            }
            
            // Swap columns in header (both rank row and name row; skip first 2 columns)
            const thead = table.querySelector('thead');
            const rankRow = thead.querySelector('.header-rank-row');
            const nameRow = thead.querySelector('.header-name-row');
            if (rankRow && nameRow) {
                const rankHeaders = Array.from(rankRow.querySelectorAll('th.col-rank-header'));
                const nameHeaders = Array.from(nameRow.querySelectorAll('th.rotate'));
                if (rankHeaders.length > Math.max(index1, index2) && nameHeaders.length > Math.max(index1, index2)) {
                    const r1 = rankHeaders[index1];
                    const r2 = rankHeaders[index2];
                    const n1 = nameHeaders[index1];
                    const n2 = nameHeaders[index2];
                    if (index1 < index2) {
                        // Moving down: place r1/n1 after r2/n2
                        rankRow.insertBefore(r1, r2.nextSibling);
                        nameRow.insertBefore(n1, n2.nextSibling);
                    } else {
                        // Moving up: place r1/n1 before r2/n2
                        rankRow.insertBefore(r1, r2);
                        nameRow.insertBefore(n1, n2);
                    }
                }
            }
            
            // Swap cells in all data rows (skip first 2 cells: rank and wrestler name)
            const allRows = Array.from(tbody.querySelectorAll('tr'));
            allRows.forEach(row => {
                const cells = Array.from(row.querySelectorAll('td'));
                // Skip first 2 cells (rank and wrestler columns)
                const matrixCells = cells.slice(2);
                if (matrixCells.length > Math.max(index1, index2)) {
                    const c1 = matrixCells[index1];
                    const c2 = matrixCells[index2];
                    const parent = c1.parentNode;
                    if (index1 < index2) {
                        // Moving down: place c1 after c2
                    parent.insertBefore(c1, c2.nextSibling);
                    } else {
                        // Moving up: place c1 before c2
                        parent.insertBefore(c1, c2);
                    }
                }
            });
            
            // Update the wrestlers array order
            [wrestlers[index1], wrestlers[index2]] = [wrestlers[index2], wrestlers[index1]];
            
            // Fix diagonal same-wrestler cells
            updateDiagonalCells();
        }

        function updateDiagonalCells() {
            const table = document.getElementById('ranking-table');
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));
            
            rows.forEach(row => {
                const rowWrestlerId = row.getAttribute('data-wrestler-id');
                const cells = Array.from(row.querySelectorAll('td')).slice(2);
                
                cells.forEach((cell, colIndex) => {
                    const colWrestler = wrestlers[colIndex];
                    if (!colWrestler) return;
                    const colWrestlerId = colWrestler.id;
                    
                    if (rowWrestlerId === colWrestlerId) {
                        cell.classList.add('same-wrestler');
                        cell.textContent = '-';
                        cell.title = '';
                    } else if (cell.classList.contains('same-wrestler')) {
                        cell.classList.remove('same-wrestler');
                        if (cell.textContent.trim() === '-') {
                            cell.textContent = '';
                        }
                    }
                });
            });
        }
        
        function moveRowToRank(row, targetRank) {
            const table = document.getElementById('ranking-table');
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));
            
            let currentIndex = rows.indexOf(row);
            const targetIndex = targetRank - 1;
            
            if (currentIndex === -1 || targetIndex < 0 || targetIndex >= rows.length) {
                return;
            }
            
            // Move step-by-step using swapRows so headers and cells stay in sync
            while (currentIndex < targetIndex) {
                swapRows(currentIndex, currentIndex + 1);
                currentIndex++;
            }
            while (currentIndex > targetIndex) {
                swapRows(currentIndex, currentIndex - 1);
                currentIndex--;
            }
            
            updateRanks();
            recomputeAnchors();
        }
        
        function setRank(buttonElem) {
            const row = buttonElem.closest('tr');
            if (!row) return;
            
            const input = row.querySelector('.rank-set-input');
            if (!input) return;
            
            const value = parseInt(input.value, 10);
            if (isNaN(value)) return;
            
            moveRowToRank(row, value);
        }
        
        // Expose setRank globally for inline onclick handlers
        window.setRank = setRank;
        
        function updateRanks() {
            const table = document.getElementById('ranking-table');
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));
            rows.forEach((row, index) => {
                // Once ranks are updated manually, clear unranked highlighting
                row.classList.remove('unranked-row');
                const rankCell = row.querySelector('.rank-col');
                if (rankCell) {
                    rankCell.textContent = index + 1;
                }
            });

            // Also update column rank numbers in the header
            const thead = table.querySelector('thead');
            if (thead) {
                const rankRow = thead.querySelector('.header-rank-row');
                if (rankRow) {
                    const rankHeaders = Array.from(rankRow.querySelectorAll('th.col-rank-header'));
                    rankHeaders.forEach((th, index) => {
                        th.textContent = index + 1;
                    });
                }
            }
        }
        
        function getCurrentRankings() {
            const table = document.getElementById('ranking-table');
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));
            const rankings = [];
            
            rows.forEach((row, index) => {
                const wrestlerId = row.getAttribute('data-wrestler-id');
                const wrestler = wrestlers.find(w => w.id === wrestlerId);
                if (wrestler) {
                    rankings.push({
                        rank: index + 1,
                        wrestler_id: wrestlerId,
                        name: wrestler.name,
                        team: wrestler.team,
                        record: `${wrestler.wins || 0}-${wrestler.losses || 0}`
                    });
                }
            });
            
            return rankings;
        }
        
        async function saveRankings() {
            const button = document.getElementById('save-button');
            const status = document.getElementById('save-status');
            
            button.disabled = true;
            status.textContent = 'Saving...';
            status.className = 'save-status';
            
            const rankings = getCurrentRankings();
            const data = {
                weight_class: weightClass,
                season: season,
                rankings: rankings
            };
            
            // Download as JSON file (works locally)
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `rankings_${weightClass}.json`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            
            status.textContent = 'Downloaded rankings JSON file';
            status.className = 'save-status save-success';
            
            button.disabled = false;
            
            setTimeout(() => {
                status.textContent = '';
            }, 3000);
        }
    </script>
</body>
</html>"""
    
    return html_content


def generate_matrix_for_weight_class(
    weight_class: str,
    season: int,
    data_dir: str = "mt/rankings_data",
    output_dir: str = "mt/rankings_html"
) -> Path:
    """
    Generate HTML matrix for a single weight class.
    
    Args:
        weight_class: Weight class string
        season: Season year
        data_dir: Directory containing relationship files
        output_dir: Directory to save HTML files
        
    Returns:
        Path to generated HTML file
    """
    # Load relationships
    rel_file = Path(data_dir) / str(season) / f"relationships_{weight_class}.json"
    
    if not rel_file.exists():
        raise FileNotFoundError(f"Relationship file not found: {rel_file}")
    
    with open(rel_file, 'r', encoding='utf-8') as f:
        relationships_data = json.load(f)
    
    # If a manual rankings file exists, load it and attach ordering
    rankings_file = Path(data_dir) / str(season) / f"rankings_{weight_class}.json"
    if rankings_file.exists():
        try:
            with open(rankings_file, 'r', encoding='utf-8') as rf:
                rankings_data = json.load(rf)
            ranking_ids = [r['wrestler_id'] for r in rankings_data.get('rankings', [])]
            relationships_data['ranking_order'] = ranking_ids
        except Exception as e:
            print(f"Warning: Failed to load rankings file {rankings_file}: {e}")

    # Load placement notes (season-agnostic, keyed by wrestler_id)
    placement_notes_path = Path(data_dir) / "placement_notes.json"
    placement_notes_map: Dict[str, str] = {}
    if placement_notes_path.exists():
        try:
            with open(placement_notes_path, "r", encoding="utf-8") as pf:
                raw_notes = json.load(pf)
            for entry in raw_notes.get("notes", []):
                wid = entry.get("wrestler_id")
                note = str(entry.get("note", "")).strip().upper()
                if wid and note:
                    placement_notes_map[wid] = note
        except Exception as e:
            print(f"Warning: Failed to load placement notes from {placement_notes_path}: {e}")
    
    # Build matrix data
    matrix_data = build_matrix_data(relationships_data, placement_notes=placement_notes_map)
    
    # Generate HTML
    html = generate_html_matrix(matrix_data, weight_class, season)
    
    # Save HTML file
    output_path = Path(output_dir) / str(season)
    output_path.mkdir(parents=True, exist_ok=True)
    
    html_file = output_path / f"matrix_{weight_class}.html"
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    return html_file


def archive_rankings_snapshot(
    season: int,
    data_dir: str = "mt/rankings_data",
) -> Path | None:
    """
    Archive current rankings_{weight}.json files for a season into a
    timestamped folder so we can analyze movement over time later.
    """
    base_dir = Path(data_dir) / str(season)
    if not base_dir.exists():
        print(f"No rankings directory found to archive for season {season}: {base_dir}")
        return None

    rankings_files = list(base_dir.glob("rankings_*.json"))
    if not rankings_files:
        print(f"No rankings_*.json files found to archive for season {season} in {base_dir}")
        return None

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_root = base_dir / "rankings_archive"
    archive_root.mkdir(parents=True, exist_ok=True)
    snapshot_dir = archive_root / timestamp
    snapshot_dir.mkdir(exist_ok=True)

    for f in rankings_files:
        dest = snapshot_dir / f.name
        shutil.copy2(f, dest)

    print(f"Archived {len(rankings_files)} rankings file(s) to {snapshot_dir}")
    return snapshot_dir


def generate_all_matrices(
    season: int,
    data_dir: str = "mt/rankings_data",
    output_dir: str = "mt/rankings_html"
) -> List[Path]:
    """
    Generate HTML matrices for all weight classes.
    
    Args:
        season: Season year
        data_dir: Directory containing relationship files
        output_dir: Directory to save HTML files
        
    Returns:
        List of paths to generated HTML files
    """
    data_path = Path(data_dir) / str(season)
    
    if not data_path.exists():
        raise FileNotFoundError(f"Data directory not found: {data_path}")
    
    html_files = []
    
    # Find all relationship files
    for rel_file in sorted(data_path.glob("relationships_*.json")):
        weight_class = rel_file.stem.replace("relationships_", "")
        print(f"Generating matrix for weight class {weight_class}...")
        
        try:
            html_file = generate_matrix_for_weight_class(
                weight_class, season, data_dir, output_dir
            )
            html_files.append(html_file)
            print(f"  Saved to {html_file}")
        except Exception as e:
            print(f"  Error: {e}")
    
    return html_files


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate editable HTML ranking matrices')
    parser.add_argument('-season', type=int, required=True, help='Season year (e.g., 2026)')
    parser.add_argument('-weight-class', help='Specific weight class to generate (default: all)')
    parser.add_argument('-data-dir', default='mt/rankings_data', help='Directory containing relationship data')
    parser.add_argument('-output-dir', default='mt/rankings_html', help='Directory to save HTML files')
    args = parser.parse_args()
    
    # Archive current rankings JSON files before generating matrices
    archive_rankings_snapshot(args.season, args.data_dir)
    
    if args.weight_class:
        # Generate single weight class
        html_file = generate_matrix_for_weight_class(
            args.weight_class, args.season, args.data_dir, args.output_dir
        )
        print(f"Generated matrix: {html_file}")
    else:
        # Generate all weight classes
        html_files = generate_all_matrices(args.season, args.data_dir, args.output_dir)
        print(f"\nGenerated {len(html_files)} matrix files")

