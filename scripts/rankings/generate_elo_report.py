#!/usr/bin/env python3
"""
Generate HTML report comparing Elo ratings with matrix rankings by weight class.

This is a review-only tool for validating Elo ratings against existing matrix rankings.

Usage:
    python scripts/rankings/generate_elo_report.py -season 2026
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional


# Boys weight classes in order
BOYS_WEIGHTS = [106, 113, 120, 126, 132, 138, 144, 150, 157, 165, 175, 190, 215, 285]

# Tier A cutoff (matrix-controlled)
TIER_A_CUTOFF_BOYS = 60
TIER_A_CUTOFF_GIRLS = 36


def load_matrix_rankings(season: int, state: str = 'ky', gender: str = 'boys') -> Dict[int, List[Dict]]:
    """
    Load matrix rankings organized by weight class.
    
    Returns:
        Dict mapping weight -> list of wrestler entries sorted by rank
    """
    data_dir = Path(f"mt/rankings_data/hs_{state}_{gender}") / str(season)
    
    if not data_dir.exists():
        raise FileNotFoundError(f"Rankings directory not found: {data_dir}")
    
    rankings_by_weight = {}
    
    # Get weight classes for gender
    if gender == 'boys':
        weights = BOYS_WEIGHTS
    else:  # girls
        weights = [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235]
    
    for weight in weights:
        rankings_file = data_dir / f"rankings_{weight}.json"
        if not rankings_file.exists():
            rankings_by_weight[weight] = []
            continue
        
        try:
            with open(rankings_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            rankings = data.get("rankings", [])
            # Sort by rank
            rankings.sort(key=lambda x: x.get("rank", 9999))
            rankings_by_weight[weight] = rankings
        
        except Exception as e:
            print(f"Warning: Error loading {rankings_file}: {e}")
            rankings_by_weight[weight] = []
    
    return rankings_by_weight


def load_elo_ratings(season: int, gender: str = 'boys') -> Dict[str, Dict]:
    """
    Load Elo ratings from JSON file.
    
    Returns:
        Dict mapping wrestler_id -> Elo data
    """
    elo_file = Path(f"mt/elo_ratings/{gender}/{season}/elo_ratings.json")
    
    if not elo_file.exists():
        raise FileNotFoundError(f"Elo ratings file not found: {elo_file}")
    
    with open(elo_file, 'r', encoding='utf-8') as f:
        elo_data = json.load(f)
    
    # Convert list to dict for easy lookup
    elo_by_id = {}
    for entry in elo_data:
        wrestler_id = entry.get("wrestler_id")
        if wrestler_id:
            elo_by_id[str(wrestler_id)] = entry
    
    return elo_by_id


def calculate_proposed_ranks(rankings: List[Dict], elo_by_id: Dict[str, Dict], 
                             tier_a_cutoff: int) -> tuple[Dict[str, int], Dict[str, str]]:
    """
    Calculate Proposed Rank for each wrestler using four-tier system (A/B/C/D).
    
    Args:
        rankings: List of wrestler entries from matrix rankings (sorted by matrix rank)
        elo_by_id: Dict mapping wrestler_id -> Elo data
        tier_a_cutoff: Tier A cutoff (60 for boys, 36 for girls)
    
    Returns:
        Tuple of (proposed_ranks dict, tier_labels dict)
    """
    proposed_ranks = {}
    tier_labels = {}  # Track which tier each wrestler is in
    
    # Separate wrestlers into Tier A, B, C, and D
    tier_a_wrestlers = []  # Matrix rank <= cutoff
    tier_b_wrestlers = []  # Matrix rank > cutoff, wins >= 1
    tier_c_wrestlers = []  # Matrix rank > cutoff, wins == 0 AND losses > 0
    tier_d_wrestlers = []  # matches == 0 (0-0 record)
    
    for entry in rankings:
        wrestler_id = str(entry.get("wrestler_id", ""))
        matrix_rank = entry.get("rank")
        
        elo_entry = elo_by_id.get(wrestler_id, {})
        wins = elo_entry.get("wins", 0)
        losses = elo_entry.get("losses", 0)
        match_count = elo_entry.get("match_count", 0)
        # Use 0 as default Elo if not found (will sort to bottom)
        elo_score = elo_entry.get("elo_score", 0) if elo_entry else 0
        
        wrestler_data = {
            "wrestler_id": wrestler_id,
            "matrix_rank": matrix_rank,
            "elo_score": elo_score,
            "wins": wins,
            "losses": losses,
            "match_count": match_count
        }
        
        if matrix_rank is not None and matrix_rank <= tier_a_cutoff:
            # Tier A: use matrix rank
            proposed_ranks[wrestler_id] = matrix_rank
            tier_labels[wrestler_id] = "A"
            tier_a_wrestlers.append(wrestler_data)
        else:
            # Tier B, C, or D: will be ranked by Elo
            if match_count == 0:
                # Tier D: No matches (0-0 record)
                tier_d_wrestlers.append(wrestler_data)
            elif wins == 0:
                # Tier C: Winless but has losses (0-X record)
                tier_c_wrestlers.append(wrestler_data)
            else:
                # Tier B: Has at least one win
                tier_b_wrestlers.append(wrestler_data)
    
    # Sort each tier by Elo descending
    tier_b_wrestlers.sort(key=lambda x: x["elo_score"], reverse=True)
    tier_c_wrestlers.sort(key=lambda x: x["elo_score"], reverse=True)
    tier_d_wrestlers.sort(key=lambda x: x["elo_score"], reverse=True)
    
    # Assign proposed ranks sequentially
    next_rank = tier_a_cutoff + 1
    
    # Tier B: Has wins, ordered by Elo
    for wrestler_data in tier_b_wrestlers:
        proposed_ranks[wrestler_data["wrestler_id"]] = next_rank
        tier_labels[wrestler_data["wrestler_id"]] = "B"
        next_rank += 1
    
    # Tier C: Winless but has losses, ordered by Elo (always below Tier B)
    for wrestler_data in tier_c_wrestlers:
        proposed_ranks[wrestler_data["wrestler_id"]] = next_rank
        tier_labels[wrestler_data["wrestler_id"]] = "C"
        next_rank += 1
    
    # Tier D: No matches (0-0), always at absolute bottom
    for wrestler_data in tier_d_wrestlers:
        proposed_ranks[wrestler_data["wrestler_id"]] = next_rank
        tier_labels[wrestler_data["wrestler_id"]] = "D"
        next_rank += 1
    
    return proposed_ranks, tier_labels


def get_elo_rank_in_weight(wrestler_id: str, weight: int, elo_by_id: Dict[str, Dict], 
                           rankings_by_weight: Dict[int, List[Dict]]) -> Optional[int]:
    """
    Calculate Elo rank within a specific weight class.
    
    Returns:
        Elo rank within weight class (1-based), or None if wrestler not found
    """
    if wrestler_id not in elo_by_id:
        return None
    
    wrestler_elo = elo_by_id[wrestler_id].get("elo_score", 0)
    
    # Get all wrestlers in this weight class with Elo scores
    weight_wrestlers = []
    for entry in rankings_by_weight.get(weight, []):
        wid = str(entry.get("wrestler_id", ""))
        if wid in elo_by_id:
            weight_wrestlers.append({
                "wrestler_id": wid,
                "elo_score": elo_by_id[wid].get("elo_score", 0)
            })
    
    # Sort by Elo score descending
    weight_wrestlers.sort(key=lambda x: x["elo_score"], reverse=True)
    
    # Find rank
    for rank, w in enumerate(weight_wrestlers, 1):
        if w["wrestler_id"] == wrestler_id:
            return rank
    
    return None


def generate_html_report(season: int, state: str = 'ky', gender: str = 'boys') -> str:
    """
    Generate HTML report comparing Elo ratings with matrix rankings.
    
    Returns:
        HTML content as string
    """
    # Load data
    print(f"Loading matrix rankings for season {season}...")
    rankings_by_weight = load_matrix_rankings(season, state, gender)
    
    print(f"Loading Elo ratings for season {season}...")
    elo_by_id = load_elo_ratings(season, gender)
    
    # Build HTML
    html_parts = []
    
    # HTML header
    html_parts.append("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Elo Ratings vs Matrix Rankings - Season """ + str(season) + """</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            border-bottom: 3px solid #0066cc;
            padding-bottom: 10px;
            margin-bottom: 30px;
        }
        h2 {
            color: #0066cc;
            margin-top: 40px;
            margin-bottom: 15px;
            font-size: 1.5em;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 30px;
            font-size: 0.9em;
        }
        th {
            background-color: #0066cc;
            color: white;
            padding: 12px 8px;
            text-align: left;
            font-weight: 600;
            position: sticky;
            top: 0;
        }
        td {
            padding: 10px 8px;
            border-bottom: 1px solid #e0e0e0;
        }
        tr:hover {
            background-color: #f9f9f9;
        }
        .rank-matrix {
            font-weight: 600;
            color: #333;
        }
        .rank-elo {
            color: #0066cc;
        }
        .elo-score {
            font-family: 'Courier New', monospace;
            font-weight: 600;
        }
        .record {
            text-align: center;
        }
        .inactive {
            color: #999;
            font-style: italic;
        }
        .active {
            color: #28a745;
        }
        .no-elo {
            color: #999;
            font-style: italic;
        }
        .zero-record {
            background-color: #fff3cd;
        }
        .proposed-rank {
            font-weight: 600;
            color: #0066cc;
        }
        .tier-a {
            background-color: #e8f4f8;
        }
        .tier-b {
            background-color: #ffffff;
        }
        .tier-c {
            background-color: #fff8e1;
        }
        .tier-d {
            background-color: #fce4ec;
        }
        .tier-label {
            font-weight: 600;
            text-align: center;
            font-size: 1.1em;
        }
        .tier-label.tier-a {
            color: #0066cc;
        }
        .tier-label.tier-b {
            color: #28a745;
        }
        .tier-label.tier-c {
            color: #ff9800;
        }
        .tier-label.tier-d {
            color: #e91e63;
        }
        .summary {
            background-color: #e8f4f8;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 30px;
        }
        .summary p {
            margin: 5px 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Elo Ratings vs Matrix Rankings - Season """ + str(season) + """</h1>
        <div class="summary">
            <p><strong>Report Generated:</strong> Review-only comparison of Elo ratings against matrix rankings</p>
            <p><strong>Purpose:</strong> Validate four-tier hybrid ranking system</p>
            <p><strong>Tier A:</strong> Matrix ranks 1-60 (boys) or 1-36 (girls) use Matrix Rank as Proposed Rank</p>
            <p><strong>Tier B:</strong> Matrix rank > cutoff, wins >= 1, ordered by Elo Score (descending)</p>
            <p><strong>Tier C:</strong> Matrix rank > cutoff, wins == 0 AND losses > 0, ordered by Elo Score (descending), always below Tier B</p>
            <p><strong>Tier D:</strong> matches == 0 (0-0 record), always at absolute bottom</p>
        </div>
""")
    
    # Determine tier cutoff based on gender
    tier_a_cutoff = TIER_A_CUTOFF_BOYS if gender == 'boys' else TIER_A_CUTOFF_GIRLS
    
    # Get weight classes for gender
    if gender == 'boys':
        weights = BOYS_WEIGHTS
    else:  # girls
        weights = [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235]
    
    # Generate table for each weight class
    for weight in weights:
        rankings = rankings_by_weight.get(weight, [])
        
        if not rankings:
            continue
        
        # Calculate proposed ranks for this weight class
        proposed_ranks, tier_labels = calculate_proposed_ranks(rankings, elo_by_id, tier_a_cutoff)
        
        # Calculate Elo ranks for this weight class
        weight_wrestlers_with_elo = []
        for entry in rankings:
            wid = str(entry.get("wrestler_id", ""))
            if wid in elo_by_id:
                weight_wrestlers_with_elo.append({
                    "wrestler_id": wid,
                    "elo_score": elo_by_id[wid].get("elo_score", 0)
                })
        
        weight_wrestlers_with_elo.sort(key=lambda x: x["elo_score"], reverse=True)
        elo_rank_map = {}
        for rank, w in enumerate(weight_wrestlers_with_elo, 1):
            elo_rank_map[w["wrestler_id"]] = rank
        
        # Sort rankings by proposed rank
        rankings_sorted = sorted(rankings, key=lambda x: proposed_ranks.get(str(x.get("wrestler_id", "")), 9999))
        
        html_parts.append(f'        <h2>{weight} lbs</h2>\n')
        html_parts.append('        <table>\n')
        html_parts.append('            <thead>\n')
        html_parts.append('                <tr>\n')
        html_parts.append('                    <th>Proposed Rank</th>\n')
        html_parts.append('                    <th>Tier</th>\n')
        html_parts.append('                    <th>Matrix Rank</th>\n')
        html_parts.append('                    <th>Wrestler Name</th>\n')
        html_parts.append('                    <th>Elo Rank</th>\n')
        html_parts.append('                    <th>Elo Score</th>\n')
        html_parts.append('                    <th>Record</th>\n')
        html_parts.append('                    <th>Active</th>\n')
        html_parts.append('                </tr>\n')
        html_parts.append('            </thead>\n')
        html_parts.append('            <tbody>\n')
        
        # Generate rows sorted by proposed rank
        for entry in rankings_sorted:
            wrestler_id = str(entry.get("wrestler_id", ""))
            matrix_rank = entry.get("rank")
            name = entry.get("name", "Unknown")
            proposed_rank = proposed_ranks.get(wrestler_id, 9999)
            
            # Get tier label
            tier_label = tier_labels.get(wrestler_id, "?")
            
            # Determine tier class for row styling
            if tier_label == "A":
                tier_class = "tier-a"
            elif tier_label == "B":
                tier_class = "tier-b"
            elif tier_label == "C":
                tier_class = "tier-c"
            elif tier_label == "D":
                tier_class = "tier-d"
            else:
                tier_class = "tier-unknown"
            
            # Get Elo data
            elo_entry = elo_by_id.get(wrestler_id)
            
            if elo_entry:
                elo_rank = elo_rank_map.get(wrestler_id)
                elo_score = elo_entry.get("elo_score", 0)
                record = elo_entry.get("record_string", "0-0")
                is_active = not elo_entry.get("inactive_flag", False)
                has_matches = elo_entry.get("has_matches", False)
                is_zero_record = record == "0-0"
            else:
                elo_rank = None
                elo_score = None
                record = entry.get("record", "0-0")
                is_active = True  # Default if no Elo data
                has_matches = False
                is_zero_record = record == "0-0"
            
            # Determine active status
            if not has_matches:
                active_text = "No matches"
                active_class = "inactive"
            elif is_active:
                active_text = "Active"
                active_class = "active"
            else:
                active_text = "Inactive"
                active_class = "inactive"
            
            # Add inactive indicator to name if needed
            display_name = name
            if not is_active:
                display_name = f"{name} <span class='inactive'>(inactive)</span>"
            
            # Determine row class
            row_class = tier_class
            if is_zero_record:
                row_class += " zero-record"
            
            html_parts.append(f'                <tr class="{row_class}">\n')
            html_parts.append(f'                    <td class="proposed-rank">{proposed_rank}</td>\n')
            html_parts.append(f'                    <td class="tier-label tier-{tier_label.lower()}">{tier_label}</td>\n')
            html_parts.append(f'                    <td class="rank-matrix">{matrix_rank if matrix_rank else "—"}</td>\n')
            html_parts.append(f'                    <td>{display_name}</td>\n')
            
            if elo_rank is not None:
                html_parts.append(f'                    <td class="rank-elo">{elo_rank}</td>\n')
                html_parts.append(f'                    <td class="elo-score">{elo_score:.2f}</td>\n')
            else:
                html_parts.append('                    <td class="no-elo">—</td>\n')
                html_parts.append('                    <td class="no-elo">—</td>\n')
            
            html_parts.append(f'                    <td class="record">{record}</td>\n')
            html_parts.append(f'                    <td class="{active_class}">{active_text}</td>\n')
            html_parts.append('                </tr>\n')
        
        html_parts.append('            </tbody>\n')
        html_parts.append('        </table>\n')
    
    # HTML footer
    html_parts.append("""    </div>
</body>
</html>""")
    
    return ''.join(html_parts)


def main():
    parser = argparse.ArgumentParser(
        description="Generate HTML report comparing Elo ratings with matrix rankings"
    )
    parser.add_argument(
        "-season",
        type=int,
        required=True,
        help="Season year (e.g., 2026)"
    )
    parser.add_argument(
        "--state",
        type=str,
        default="ky",
        help="State code (default: ky)"
    )
    parser.add_argument(
        "--gender",
        choices=["boys", "girls"],
        default="boys",
        help="Gender: 'boys' or 'girls' (default: boys)"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output HTML file path (default: mt/elo_ratings/{gender}/{season}/elo_report.html)"
    )
    
    args = parser.parse_args()
    
    print(f"\n{'='*80}")
    print(f"GENERATING ELO REPORT - Season {args.season} ({args.gender.upper()})")
    print(f"{'='*80}\n")
    
    # Generate HTML
    html_content = generate_html_report(args.season, args.state, args.gender)
    
    # Set output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = Path(f"mt/elo_ratings/{args.gender}/{args.season}/elo_report.html")
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write HTML file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✓ HTML report written to: {output_path}")
    print(f"\nOpen the file in a web browser to review Elo ratings vs matrix rankings.")


if __name__ == "__main__":
    main()

