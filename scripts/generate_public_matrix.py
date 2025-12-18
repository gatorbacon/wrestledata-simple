#!/usr/bin/env python3
"""
generate_public_matrix.py — Public Rankings Matrix Generator

This script generates a public-facing rankings matrix JSON for WrestleData.
It is a post-processing step ONLY. It does not compute rankings, Mat Value, or match outcomes.

It transforms already-computed relationship data into a format optimized for
transparent, human-readable matrix visualization on the website.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def classify_result_type(result: str) -> str:
    """
    Classify match result type for normalization.
    
    Returns normalized types: D, MD, TF, F, TB, SV, etc.
    """
    if not result:
        return "D"  # Default to decision if unknown
    
    r = result.upper()
    
    # Check for tech fall (before fall/pin)
    if "TF" in r or "TECH" in r or "TECHNICAL" in r:
        return "TF"
    
    # Check for falls/pins (but not tech fall)
    if ("PIN" in r or "FALL" in r) and "TF" not in r:
        return "F"
    
    # Check for major decision
    if "MD" in r or "MAJOR" in r:
        return "MD"
    
    # Check for tiebreaker
    if "TB-" in r or "TIEBREAK" in r:
        return "TB"
    
    # Check for sudden victory
    if "SV-" in r or "SUDDEN VICTORY" in r:
        return "SV"
    
    # Default to decision (includes regular decisions)
    if "DEC" in r or "DECISION" in r:
        return "D"
    
    # Default fallback
    return "D"


def normalize_result_type(result_type: str) -> Tuple[str, str]:
    """
    Normalize result type to internal type and display code.
    
    Returns: (normalized_type, display_code)
    """
    result_type = result_type.upper()
    
    # Normalize to internal types
    if result_type in ("D", "TB", "SV"):
        return ("DECISION", "D")
    elif result_type == "MD":
        return ("MAJOR", "MD")
    elif result_type == "TF":
        return ("TECH", "TF")
    elif result_type == "F":
        return ("FALL", "F")
    elif result_type == "CO":
        return ("COMMON_OPPONENT", "CO")
    elif result_type == "SPLIT":
        return ("SPLIT", "S")
    else:
        # Default to decision
        return ("DECISION", "D")


def extract_method_from_result(result: str) -> str:
    """
    Extract method code from result string.
    
    Returns: D, MD, TF, F, TB, SV
    """
    return classify_result_type(result)


def parse_score_from_result(result: str) -> Optional[str]:
    """
    Extract score from result string if present.
    
    Example: "MD 11-2" -> "11-2"
    """
    if not result:
        return None
    
    # Look for score pattern like "11-2" or "17-16"
    import re
    score_match = re.search(r'(\d+)-(\d+)', result)
    if score_match:
        return score_match.group(0)
    
    return None


def determine_relationship_type(
    direct_rel: Optional[Dict],
    co_rel: Optional[Dict],
    wrestler1_id: str,
    wrestler2_id: str
) -> Optional[Tuple[str, str, List[Dict], Optional[str]]]:
    """
    Determine the relationship type and return normalized data.
    
    Returns: (normalized_type, display_code, results_array, co_result) or None
    co_result is only set for COMMON_OPPONENT type ("win", "loss", "tie")
    """
    # Rule 1: If direct relationship exists, use it
    if direct_rel:
        wins_1 = direct_rel.get('direct_wins_1', 0)
        wins_2 = direct_rel.get('direct_wins_2', 0)
        matches = direct_rel.get('matches', [])
        
        # Check if this is a split (both have wins)
        if wins_1 > 0 and wins_2 > 0:
            # SPLIT: both wrestlers have at least one win
            results = []
            for match in matches:
                winner_id = match.get('winner_id', '')
                result_str = match.get('result', '')
                date = match.get('date', '')
                
                # Parse date to YYYY-MM-DD format
                date_formatted = date
                if date and '/' in date:
                    try:
                        parts = date.split('/')
                        if len(parts) == 3:
                            month = parts[0].zfill(2)
                            day = parts[1].zfill(2)
                            year = parts[2]
                            if len(year) == 2:
                                year = "20" + year
                            date_formatted = f"{year}-{month}-{day}"
                    except Exception:
                        pass
                
                method = extract_method_from_result(result_str)
                score = parse_score_from_result(result_str)
                
                results.append({
                    "date": date_formatted,
                    "winner_id": winner_id,
                    "method": method,
                    "score": score
                })
            
            # Sort results by date
            results.sort(key=lambda x: x.get('date', ''))
            
            return ("SPLIT", "S", results, None)
        else:
            # Single result type - use actual winner_id from match data
            # CRITICAL: Use the winner_id from the match, not inferred from wins_1/wins_2
            # The match winner_id is the actual winner, regardless of relationship normalization
            
            if not matches:
                # No matches recorded (shouldn't happen, but handle gracefully)
                return None
            
            # Get the first match result
            match = matches[0]
            result_str = match.get('result', '')
            date = match.get('date', '')
            winner_id = match.get('winner_id', '')
            
            # Validate winner_id is one of the two wrestlers
            if winner_id not in [wrestler1_id, wrestler2_id]:
                # Fallback to wins_1/wins_2 if winner_id is invalid
                if wins_1 > 0:
                    winner_id = wrestler1_id
                elif wins_2 > 0:
                    winner_id = wrestler2_id
                else:
                    return None
            
            # Parse date
            date_formatted = date
            if date and '/' in date:
                try:
                    parts = date.split('/')
                    if len(parts) == 3:
                        month = parts[0].zfill(2)
                        day = parts[1].zfill(2)
                        year = parts[2]
                        if len(year) == 2:
                            year = "20" + year
                        date_formatted = f"{year}-{month}-{day}"
                except Exception:
                    pass
            
            method = extract_method_from_result(result_str)
            score = parse_score_from_result(result_str)
            
            result_type, display_code = normalize_result_type(method)
            
            return (result_type, display_code, [{
                "date": date_formatted,
                "winner_id": winner_id,  # Actual winner from match data
                "method": method,
                "score": score
            }], None)
    
    # Rule 2: If only common opponent relationship exists
    if co_rel:
        # Determine CO result from row wrestler's perspective
        co_wins_1 = co_rel.get('common_opp_wins_1', 0)
        co_losses_1 = co_rel.get('common_opp_losses_1', 0)
        co_wins_2 = co_rel.get('common_opp_wins_2', 0)
        co_losses_2 = co_rel.get('common_opp_losses_2', 0)
        
        # Determine which wrestler is which in the relationship
        rel_w1_id = co_rel.get('wrestler1_id', '')
        rel_w2_id = co_rel.get('wrestler2_id', '')
        
        # Map to row wrestler perspective
        if wrestler1_id == rel_w1_id:
            # Row wrestler is wrestler1 in relationship
            row_co_wins = co_wins_1
            row_co_losses = co_losses_1
        else:
            # Row wrestler is wrestler2 in relationship
            row_co_wins = co_wins_2
            row_co_losses = co_losses_2
        
        # Determine CO result
        if row_co_wins > row_co_losses:
            co_result = "win"
        elif row_co_losses > row_co_wins:
            co_result = "loss"
        else:
            co_result = "tie"
        
        return ("COMMON_OPPONENT", "CO", [], co_result)
    
    # Rule 3: No relationship
    return None


def load_relationships(season: int, weight: int, data_dir: str = "mt/rankings_data") -> Dict:
    """Load relationships JSON file."""
    rel_file = Path(data_dir) / str(season) / f"relationships_{weight}.json"
    
    if not rel_file.exists():
        raise FileNotFoundError(f"Relationships file not found: {rel_file}")
    
    with open(rel_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_rankings(season: int, weight: int, data_dir: str = "mt/rankings_data", starters_only: bool = False) -> Dict:
    """Load rankings JSON file."""
    filename = f"rankings_starters_{weight}.json" if starters_only else f"rankings_{weight}.json"
    rankings_file = Path(data_dir) / str(season) / filename
    
    if not rankings_file.exists():
        raise FileNotFoundError(f"Rankings file not found: {rankings_file}")
    
    with open(rankings_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def build_wrestler_list(rankings_data: Dict, wrestlers_data: Dict, starters_only: bool = False) -> List[Dict]:
    """
    Build ordered list of wrestlers from rankings.
    
    Ranked wrestlers first (by rank), then unranked wrestlers.
    If starters_only is True, exclude all non-starters (including unranked).
    """
    rankings = rankings_data.get('rankings', [])
    wrestlers_dict = wrestlers_data.get('wrestlers', {})
    
    # Separate ranked and unranked
    ranked = []
    unranked = []
    
    # Build ranked list
    for entry in rankings:
        wrestler_id = entry.get('wrestler_id')
        if not wrestler_id:
            continue
        
        # If starters_only, skip non-starters
        if starters_only and not entry.get('is_starter', False):
            continue
        
        wrestler_info = wrestlers_dict.get(wrestler_id, {})
        
        ranked.append({
            "id": wrestler_id,
            "name": entry.get('name') or wrestler_info.get('name', 'Unknown'),
            "team": entry.get('team') or wrestler_info.get('team', 'Unknown'),
            "rank": entry.get('rank'),
            "starter": entry.get('is_starter', False)
        })
    
    # Build unranked list (wrestlers in relationships but not in rankings)
    # Skip this entirely if starters_only is True
    if not starters_only:
        ranked_ids = {w['id'] for w in ranked}
        
        for wrestler_id, wrestler_info in wrestlers_dict.items():
            if wrestler_id not in ranked_ids:
                unranked.append({
                    "id": wrestler_id,
                    "name": wrestler_info.get('name', 'Unknown'),
                    "team": wrestler_info.get('team', 'Unknown'),
                    "rank": None,
                    "starter": False
                })
        
        # Sort unranked by name for consistency
        unranked.sort(key=lambda x: x['name'])
    
    return ranked + unranked


def build_matrix(
    relationships_data: Dict,
    wrestler_list: List[Dict]
) -> Dict[str, Dict[str, Dict]]:
    """
    Build the matrix structure.
    
    Returns: matrix[wrestler_id_A][wrestler_id_B] = cell_data
    """
    direct_rels = relationships_data.get('direct_relationships', {})
    co_rels = relationships_data.get('common_opponent_relationships', {})
    
    # Create lookup maps for relationships
    direct_map = {}
    for key, rel in direct_rels.items():
        w1_id = rel.get('wrestler1_id')
        w2_id = rel.get('wrestler2_id')
        if w1_id and w2_id:
            # Store both directions
            direct_map[(w1_id, w2_id)] = rel
            direct_map[(w2_id, w1_id)] = rel
    
    co_map = {}
    for key, rel in co_rels.items():
        w1_id = rel.get('wrestler1_id')
        w2_id = rel.get('wrestler2_id')
        if w1_id and w2_id:
            # Store both directions
            co_map[(w1_id, w2_id)] = rel
            co_map[(w2_id, w1_id)] = rel
    
    # Build matrix - include ALL wrestlers as rows and columns
    matrix = {}
    wrestler_ids = [w['id'] for w in wrestler_list]
    
    for w1_id in wrestler_ids:
        matrix[w1_id] = {}
        
        for w2_id in wrestler_ids:
            # Skip self
            if w1_id == w2_id:
                continue
            
            # Get relationships
            direct_rel = direct_map.get((w1_id, w2_id))
            co_rel = co_map.get((w1_id, w2_id))
            
            # Determine relationship type
            rel_data = determine_relationship_type(
                direct_rel, co_rel, w1_id, w2_id
            )
            
            # Only include cell if relationship exists
            # (frontend will render empty cells for missing relationships)
            if rel_data:
                rel_type, display_code, results, co_result = rel_data
                cell_obj = {
                    "type": rel_type,
                    "display": display_code,
                    "results": results
                }
                # Add co_result for COMMON_OPPONENT cells
                if rel_type == "COMMON_OPPONENT" and co_result:
                    cell_obj["co_result"] = co_result
                matrix[w1_id][w2_id] = cell_obj
            # If no relationship, don't create cell (frontend handles empty)
    
    return matrix


def generate_public_matrix(
    season: int,
    weight: int,
    data_dir: str = "mt/rankings_data",
    output_dir: str = "frontend/wrestledata-ui/public/matrix",
    starters_only: bool = False
) -> Dict:
    """
    Generate public matrix JSON for a single weight class.
    
    Args:
        season: Season year
        weight: Weight class
        data_dir: Directory containing relationships and rankings files
        output_dir: Directory to save output files
        starters_only: If True, use rankings_starters files instead of rankings files
    
    Returns: The matrix data dictionary
    """
    # Load data
    relationships_data = load_relationships(season, weight, data_dir)
    rankings_data = load_rankings(season, weight, data_dir, starters_only)
    
    # Build wrestler list (ordered by rank)
    # If starters_only, exclude all non-starters
    wrestler_list = build_wrestler_list(rankings_data, relationships_data, starters_only)
    
    # Build matrix
    matrix = build_matrix(relationships_data, wrestler_list)
    
    # Build output
    output = {
        "season": season,
        "weight": weight,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "wrestlers": wrestler_list,
        "matrix": matrix
    }
    
    return output


def save_public_matrix(
    matrix_data: Dict,
    season: int,
    weight: int,
    output_dir: str = "frontend/wrestledata-ui/public/matrix",
    starters_only: bool = False
) -> Path:
    """Save public matrix JSON to file."""
    output_path = Path(output_dir) / str(season)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Always use same filename format (no suffix)
    filename = f"public_matrix_{season}_{weight}.json"
    output_file = output_path / filename
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(matrix_data, f, indent=2, ensure_ascii=False)
    
    return output_file


def main():
    parser = argparse.ArgumentParser(
        description='Generate public-facing rankings matrix JSON'
    )
    parser.add_argument(
        '-season',
        type=int,
        required=True,
        help='Season year (e.g., 2026)'
    )
    parser.add_argument(
        '-weight',
        type=int,
        help='Weight class (e.g., 125). If not provided, processes all weight classes.'
    )
    parser.add_argument(
        '-data-dir',
        default='mt/rankings_data',
        help='Directory containing relationships and rankings files'
    )
    parser.add_argument(
        '-output-dir',
        default='frontend/wrestledata-ui/public/matrix',
        help='Directory to save output files'
    )
    parser.add_argument(
        '--starters-only',
        action='store_true',
        help='Use rankings_starters files instead of rankings files (generates starters-only matrix)'
    )
    
    args = parser.parse_args()
    
    weights = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]
    
    if args.weight:
        weights = [args.weight]
    
    mode_str = "starters-only" if args.starters_only else "all wrestlers"
    print(f"Generating public matrices for season {args.season} ({mode_str})...")
    
    for weight in weights:
        try:
            print(f"\nProcessing weight {weight}...")
            matrix_data = generate_public_matrix(
                args.season,
                weight,
                args.data_dir,
                args.output_dir,
                args.starters_only
            )
            
            output_file = save_public_matrix(
                matrix_data,
                args.season,
                weight,
                args.output_dir,
                args.starters_only
            )
            
            wrestler_count = len(matrix_data['wrestlers'])
            matrix_cells = sum(len(row) for row in matrix_data['matrix'].values())
            
            print(f"  ✓ Saved to {output_file}")
            print(f"    {wrestler_count} wrestlers, {matrix_cells} matrix cells")
            
        except FileNotFoundError as e:
            print(f"  ✗ Skipping {weight}: {e}")
        except Exception as e:
            print(f"  ✗ Error processing {weight}: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n✓ Public matrix generation complete!")


if __name__ == "__main__":
    main()

