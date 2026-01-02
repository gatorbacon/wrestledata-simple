#!/usr/bin/env python3
"""
Build Simple Leaderboards (Pins, Techs, Majors, Wins)

Generates four JSON files for leaderboard pages:
- pins.json: Most pins
- techs.json: Most tech falls
- majors.json: Most major decisions
- wins.json: Most wins

Uses weight_class_*.json files from mt/rankings_data/<season>/ (same source as profile builder).
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Set


def classify_result_type(result: str) -> str:
    """
    Classify match result type.
    Returns: F (Fall/Pin), TF (Tech Fall), MD (Major Decision), D (Decision), etc.
    """
    if not result:
        return "O"
    
    s = result.upper()
    
    # Check for injury first
    if "INJ" in s or "INJURY" in s:
        return "INJ"
    
    # Check for disqualification
    if "DQ" in s or "DISQUAL" in s:
        return "DQ"
    
    # Check for tech fall (before fall/pin)
    if "TF" in s or "TECH" in s or "TECHNICAL" in s:
        return "TF"
    
    # Check for falls/pins
    if ("PIN" in s or "FALL" in s) and "TF" not in s:
        return "F"
    
    # Check for major decision
    if "MD" in s or "MAJOR" in s:
        return "MD"
    
    # Check for decision (including sudden victory)
    if "DEC" in s or "DECISION" in s or "SV-" in s:
        return "D"
    
    # Check for tiebreaker
    if "TB-" in s or "TIEBREAK" in s:
        return "D"  # Treat as decision
    
    return "O"


def is_win_result(result: str) -> bool:
    """Check if result represents a win (excluding BYE, NC, MFF, etc.)."""
    if not result:
        return False
    
    s = result.upper()
    
    # Exclude non-match results
    if "BYE" in s or "NC" in s or "NO CONTEST" in s:
        return False
    
    # Exclude forfeits (medical or otherwise)
    if "MFF" in s or "MEDICAL" in s or "FORFEIT" in s:
        return False
    
    # Any other result type is a win
    return True


def load_d1_wrestler_ids(season: int, data_dir: str = "mt/rankings_data", league: str = 'ncaa', state: str = None, gender: str = None) -> Set[str]:
    """
    Load all wrestler IDs from rankings files.
    
    Returns:
        Set of wrestler IDs
    """
    d1_ids = set()
    if league == 'hs':
        state_lower = state.lower() if state else 'ky'
        data_path = Path(data_dir) / f"hs_{state_lower}_{gender}" / str(season)
    else:
        data_path = Path(data_dir) / str(season)
    
    if not data_path.exists():
        print(f"Warning: Rankings directory not found: {data_path}")
        return d1_ids
    
    # Load from rankings_*.json files (full rankings, not starters-only)
    for rankings_file in sorted(data_path.glob("rankings_*.json")):
        try:
            with rankings_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load {rankings_file}: {e}")
            continue
        
        rankings = data.get("rankings", [])
        for entry in rankings:
            wrestler_id = entry.get("wrestler_id")
            if wrestler_id:
                d1_ids.add(str(wrestler_id))
    
    return d1_ids


def process_weight_class_files(season: int, data_dir: str, d1_wrestler_ids: Set[str], league: str = 'ncaa', state: str = None, gender: str = None) -> Dict[str, Dict]:
    """
    Process all weight_class_*.json files and return aggregated stats per wrestler.
    
    Returns:
        Dict mapping wrestler_id -> {
            'name': str,
            'team': str,
            'weight': int,
            'pins': int,
            'techs': int,
            'majors': int,
            'wins': int
        }
    """
    if league == 'hs':
        state_lower = state.lower() if state else 'ky'
        data_path = Path(data_dir) / f"hs_{state_lower}_{gender}" / str(season)
    else:
        data_path = Path(data_dir) / str(season)
    
    if not data_path.exists():
        raise FileNotFoundError(f"Data directory not found: {data_path}")
    
    # Build wrestler info map from all weight_class files
    wrestler_info_map = {}
    all_matches = []
    
    # DEBUG: Track specific wrestlers
    DEBUG_WRESTLER_IDS = ["34941782132", "34939039132"]  # Vinny Kilkeary, PJ Duke
    
    # First pass: collect wrestler info and all matches
    for wc_file in sorted(data_path.glob("weight_class_*.json")):
        try:
            with wc_file.open("r", encoding="utf-8") as f:
                wc_data = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load {wc_file.name}: {e}")
            continue
        
        # Collect wrestler info
        for wrestler_id, winfo in wc_data.get("wrestlers", {}).items():
            if wrestler_id not in wrestler_info_map:
                wrestler_info_map[wrestler_id] = {
                    "name": winfo.get("name", "Unknown"),
                    "team": winfo.get("team", "Unknown"),
                    "primary_weight": winfo.get("weight_class", ""),
                }
        
        # Collect matches
        for match in wc_data.get("matches", []):
            all_matches.append(match)
    
    # Initialize stats for all wrestlers
    stats_by_wrestler = {}
    for wrestler_id, info in wrestler_info_map.items():
        try:
            weight = int(info["primary_weight"]) if info["primary_weight"] else None
        except (ValueError, TypeError):
            weight = None
        
        if weight:
            stats_by_wrestler[wrestler_id] = {
                "name": info["name"],
                "team": info["team"],
                "weight": weight,
                "pins": 0,
                "techs": 0,
                "majors": 0,
                "wins": 0,
            }
    
    # Second pass: process matches and count stats
    for match in all_matches:
        w1_id = match.get("wrestler1_id")
        w2_id = match.get("wrestler2_id")
        winner_id = match.get("winner_id")
        result = match.get("result", "")
        
        if not w1_id or not w2_id or not winner_id:
            continue
        
        # Skip NC results
        if result.upper() == "NC" or "NO CONTEST" in result.upper():
            continue
        
        # Check for injury (matches profile builder logic)
        result_upper = result.upper()
        has_injury = ("INJ" in result_upper or "INJURY" in result_upper)
        
        if has_injury:
            continue
        
        # Process for wrestler 1
        if w1_id in stats_by_wrestler:
            is_winner = (winner_id == w1_id)
            opponent_id = w2_id
            
            if is_winner:
                # Check if opponent is D1
                opponent_id_str = str(opponent_id)
                if opponent_id_str in d1_wrestler_ids:
                    # Classify result type
                    result_type = classify_result_type(result)
                    
                    # Count wins
                    if is_win_result(result):
                        stats_by_wrestler[w1_id]["wins"] += 1
                    
                    # Count specific result types
                    if result_type == "F":
                        stats_by_wrestler[w1_id]["pins"] += 1
                    elif result_type == "TF":
                        stats_by_wrestler[w1_id]["techs"] += 1
                    elif result_type == "MD":
                        stats_by_wrestler[w1_id]["majors"] += 1
        
        # Process for wrestler 2
        if w2_id in stats_by_wrestler:
            is_winner = (winner_id == w2_id)
            opponent_id = w1_id
            
            if is_winner:
                # Check if opponent is D1
                opponent_id_str = str(opponent_id)
                if opponent_id_str in d1_wrestler_ids:
                    # Classify result type
                    result_type = classify_result_type(result)
                    
                    # Count wins
                    if is_win_result(result):
                        stats_by_wrestler[w2_id]["wins"] += 1
                    
                    # Count specific result types
                    if result_type == "F":
                        stats_by_wrestler[w2_id]["pins"] += 1
                    elif result_type == "TF":
                        stats_by_wrestler[w2_id]["techs"] += 1
                    elif result_type == "MD":
                        stats_by_wrestler[w2_id]["majors"] += 1
    
    # DEBUG: Print debug info for specific wrestlers
    for wrestler_id in DEBUG_WRESTLER_IDS:
        if wrestler_id in stats_by_wrestler:
            stats = stats_by_wrestler[wrestler_id]
            print(f"\n{'='*70}")
            print(f"DEBUG: {stats['name']} (ID: {wrestler_id})")
            print(f"{'='*70}")
            print(f"  Final pin count: {stats['pins']}")
            print(f"  Final tech count: {stats['techs']}")
            print(f"  Final major count: {stats['majors']}")
            print(f"  Final wins count: {stats['wins']}")
            print(f"{'='*70}\n")
    
    return stats_by_wrestler


def aggregate_all_weight_classes(season: int, data_dir: str, rankings_dir: str = "mt/rankings_data", league: str = 'ncaa', state: str = None, gender: str = None) -> Dict[str, Dict]:
    """
    Aggregate stats across all weight_class files.
    
    Returns:
        Dict mapping wrestler_id -> aggregated stats
    """
    # Load wrestler IDs
    print(f"Loading wrestler IDs from {rankings_dir}...")
    d1_wrestler_ids = load_d1_wrestler_ids(season, rankings_dir, league=league, state=state, gender=gender)
    print(f"Loaded {len(d1_wrestler_ids)} wrestler IDs")
    
    # Process all weight_class files
    print(f"Processing weight_class files from {data_dir}...")
    all_stats = process_weight_class_files(season, data_dir, d1_wrestler_ids, league=league, state=state, gender=gender)
    
    return all_stats


def generate_leaderboard_json(
    all_stats: Dict[str, Dict], stat_type: str
) -> List[Dict]:
    """
    Generate leaderboard JSON for a specific stat type.
    
    Args:
        all_stats: Aggregated stats by wrestler_id
        stat_type: One of 'pins', 'techs', 'majors', 'wins'
    
    Returns:
        List of entries sorted by count (descending)
    """
    entries = []
    
    for wrestler_id, stats in all_stats.items():
        count = stats[stat_type]
        
        # Only include wrestlers with at least 1 count
        if count > 0:
            entries.append({
                "wrestler_id": wrestler_id,
                "name": stats["name"],
                "team": stats["team"],
                "weight": stats["weight"],
                "count": count,
            })
    
    # Sort by count descending, then by name ascending
    entries.sort(key=lambda x: (-x["count"], x["name"]))
    
    return entries


def main():
    parser = argparse.ArgumentParser(
        description="Build simple leaderboard JSON files (pins, techs, majors, wins)"
    )
    parser.add_argument(
        "--season",
        type=int,
        default=2026,
        help="Season year (default: 2026)",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="mt/rankings_data",
        help="Directory containing weight_class JSON files",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="frontend/wrestledata-ui/public/data/leaderboards",
        help="Output directory for JSON files",
    )
    parser.add_argument(
        "--rankings-dir",
        type=str,
        default="mt/rankings_data",
        help="Directory containing rankings data (for filtering)",
    )
    parser.add_argument('-league', type=str, default='ncaa', choices=['ncaa', 'hs'],
                        help='League type: ncaa (default) or hs')
    parser.add_argument('-state', type=str, help='State code (required when league=hs, currently only KY supported)')
    parser.add_argument('-gender', type=str, choices=['boys', 'girls'],
                        help='Gender: boys or girls (optional when league=hs, defaults to processing both)')
    
    args = parser.parse_args()
    
    # For HS, process both genders if gender not specified
    if args.league == 'hs':
        if not args.state:
            raise ValueError("For HS league, --state is required.")
        
        genders_to_process = [args.gender] if args.gender else ['boys', 'girls']
        
        for gender in genders_to_process:
            print(f"\n{'=' * 80}")
            print(f"Building leaderboards for season {args.season} ({args.league.upper()} {args.state} {gender})...")
            print(f"{'=' * 80}\n")
            
            data_dir = Path("mt/rankings_data")
            rankings_dir = Path("mt/rankings_data")
            output_dir = Path("frontend/hs-ky-ui/public/data/leaderboards") / gender / str(args.season)
            
            # Override with CLI args if provided
            if args.data_dir:
                data_dir = Path(args.data_dir)
            if args.rankings_dir:
                rankings_dir = Path(args.rankings_dir)
            if args.output_dir:
                output_dir = Path(args.output_dir)
            
            # Aggregate stats from all weight_class files
            print(f"Aggregating stats for season {args.season}...")
            all_stats = aggregate_all_weight_classes(args.season, str(data_dir), str(rankings_dir), league=args.league, state=args.state, gender=gender)
            print(f"Found {len(all_stats)} unique wrestlers")
            
            # Generate JSON files
            output_path = output_dir
            output_path.mkdir(parents=True, exist_ok=True)
            
            stat_types = ["pins", "techs", "majors", "wins"]
            
            for stat_type in stat_types:
                entries = generate_leaderboard_json(all_stats, stat_type)
                output_file = output_path / f"{stat_type}.json"
                
                with output_file.open("w", encoding="utf-8") as f:
                    json.dump(entries, f, indent=2, ensure_ascii=False)
                
                print(f"Generated {output_file}: {len(entries)} entries")
                if entries:
                    print(f"  Top entry: {entries[0]['name']} ({entries[0]['team']}) - {entries[0]['count']} {stat_type}")
            
            print("\nDone!")
    else:  # ncaa
        # Aggregate stats from all weight_class files
        print(f"Aggregating stats for season {args.season}...")
        all_stats = aggregate_all_weight_classes(args.season, args.data_dir, args.rankings_dir, league=args.league)
        print(f"Found {len(all_stats)} unique wrestlers")
        
        # Generate JSON files
        output_path = Path(args.output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        stat_types = ["pins", "techs", "majors", "wins"]
        
        for stat_type in stat_types:
            entries = generate_leaderboard_json(all_stats, stat_type)
            output_file = output_path / f"{stat_type}.json"
            
            with output_file.open("w", encoding="utf-8") as f:
                json.dump(entries, f, indent=2, ensure_ascii=False)
            
            print(f"Generated {output_file}: {len(entries)} entries")
            if entries:
                print(f"  Top entry: {entries[0]['name']} ({entries[0]['team']}) - {entries[0]['count']} {stat_type}")
        
        print("\nDone!")


if __name__ == "__main__":
    main()

