#!/usr/bin/env python3
"""
generate_match_highlights.py

Generates weekly match highlights (Top Matchups and Upsets) for a given date range.

This script:
1. Loads archived rankings snapshots
2. Collects matches from wrestler profiles within the date range
3. For each match, determines which ranking snapshot to use (most recent drop before match date)
4. Classifies matches as Top Matchups (Top 10 vs Top 10) or Upsets (Top 20 loss to lower-ranked/unranked)
5. Outputs JSON file for frontend consumption

Usage:
    python scripts/rankings/generate_match_highlights.py \
        --start-date 2026-01-06 \
        --end-date 2026-01-13 \
        --season 2026 \
        --gender boys \
        --league hs
"""

import argparse
import json
from collections import defaultdict
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate match highlights for a date range"
    )
    parser.add_argument(
        "--start-date",
        type=str,
        required=True,
        help="Start date (YYYY-MM-DD). Matches on this date are included."
    )
    parser.add_argument(
        "--end-date",
        type=str,
        required=True,
        help="End date (YYYY-MM-DD). Matches on this date are included."
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
        help="Gender ('boys' or 'girls')"
    )
    parser.add_argument(
        "--league",
        type=str,
        default="hs",
        choices=["hs"],
        help="League (currently only 'hs' supported)"
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="frontend/hs-ky-ui/public/data",
        help="Base directory for data files"
    )
    
    return parser.parse_args()


def parse_date(date_str: str) -> date:
    """Parse date string in YYYY-MM-DD format."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD")


def load_drops_index(data_dir: Path, gender: str, season: int) -> List[Dict]:
    """
    Load drops index to get all ranking drop dates.
    
    Returns:
        List of drop dictionaries with 'id' (drop date) and 'published_at' fields
    """
    index_file = data_dir / "rankings" / gender / str(season) / "index.json"
    
    if not index_file.exists():
        print(f"Warning: Index file not found: {index_file}")
        return []
    
    try:
        with index_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        
        drops = data.get("drops", [])
        # Sort by published_at (newest first) for easier processing
        drops.sort(key=lambda d: d.get("published_at", ""), reverse=True)
        return drops
    except Exception as e:
        print(f"Error loading drops index: {e}")
        return []


def find_ranking_basis_drop(match_date: date, drops: List[Dict]) -> Optional[str]:
    """
    Find the most recent drop that is strictly before the match date.
    
    Args:
        match_date: Date of the match
        drops: List of drop dictionaries (sorted newest first)
    
    Returns:
        Drop ID (date string) to use for rankings, or None if no drop found
    """
    for drop in drops:
        drop_id = drop.get("id")
        if not drop_id:
            continue
        
        try:
            drop_date = parse_date(drop_id)
            if drop_date < match_date:
                return drop_id
        except ValueError:
            continue
    
    return None


def load_rankings_snapshot(
    data_dir: Path,
    gender: str,
    season: int,
    drop_id: str
) -> Tuple[Dict[str, int], Dict[str, int]]:
    """
    Load historical rankings snapshot from archived drop directory.
    Uses rankings from the specific drop date (e.g., '2026-01-06').
    
    Args:
        data_dir: Base data directory (e.g., 'frontend/hs-ky-ui/public/data')
        gender: 'boys' or 'girls'
        season: Season year
        drop_id: Drop identifier (e.g., '2026-01-06') - used to determine which rankings to load
    
    Returns:
        Tuple of:
        - Dictionary mapping wrestler_id -> rank (across all weight classes, includes ALL ranked wrestlers)
        - Dictionary mapping wrestler_id -> weight_class (the weight at which they're ranked)
    """
    # Load from archived drop directory: frontend/hs-ky-ui/public/data/rankings/{gender}/{season}/{drop_id}/{weight}.json
    drop_dir = data_dir / "rankings" / gender / str(season) / drop_id
    
    if not drop_dir.exists():
        print(f"Warning: Drop directory not found: {drop_dir}")
        return {}, {}
    
    # Determine weight classes based on gender
    if gender == 'boys':
        weights = [106, 113, 120, 126, 132, 138, 144, 150, 157, 165, 175, 190, 215, 285]
    else:  # girls
        weights = [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235]
    
    rank_map = {}
    weight_map = {}  # wrestler_id -> weight_class at which they're ranked
    
    for weight in weights:
        weight_file = drop_dir / f"{weight}.json"
        if not weight_file.exists():
            continue
        
        try:
            with weight_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Archived drop files use "wrestlers" key (not "rankings")
            wrestlers = data.get("wrestlers", [])
            
            for wrestler in wrestlers:
                wid = wrestler.get("wrestler_id")
                rank = wrestler.get("rank")
                if wid and rank is not None:
                    wid_str = str(wid)
                    rank_map[wid_str] = rank
                    weight_map[wid_str] = weight  # Store the weight class at which they're ranked
        except Exception as e:
            print(f"Warning: Error loading {weight_file}: {e}")
            continue
    
    return rank_map, weight_map


def load_wrestler_profiles(
    data_dir: Path,
    gender: str,
    season: int
) -> Dict[str, Dict]:
    """
    Load all wrestler profiles and extract match data.
    
    Returns:
        Dictionary mapping wrestler_id -> wrestler profile dict
    """
    profiles_dir = data_dir / "wrestlers" / gender / str(season) / "by_id"
    
    if not profiles_dir.exists():
        print(f"Warning: Profiles directory not found: {profiles_dir}")
        return {}
    
    profiles = {}
    profile_files = list(profiles_dir.glob("*.json"))
    
    print(f"Loading {len(profile_files)} wrestler profiles...")
    
    for profile_file in profile_files:
        try:
            with profile_file.open("r", encoding="utf-8") as f:
                profile = json.load(f)
            
            wrestler_id = profile.get("wrestler_id")
            if wrestler_id:
                profiles[str(wrestler_id)] = profile
        except Exception as e:
            print(f"Warning: Error loading {profile_file}: {e}")
            continue
    
    print(f"Loaded {len(profiles)} wrestler profiles")
    return profiles


def collect_matches_in_range(
    profiles: Dict[str, Dict],
    start_date: date,
    end_date: date
) -> List[Dict]:
    """
    Collect all matches from wrestler profiles within the date range.
    
    Returns:
        List of match dictionaries with winner/loser information
    """
    matches = []
    seen_match_keys = set()
    
    for wrestler_id, profile in profiles.items():
        match_list = profile.get("match_list", [])
        name = profile.get("name", "Unknown")
        team = profile.get("team", "Unknown")
        
        for match in match_list:
            match_date_str = match.get("date", "")
            if not match_date_str:
                continue
            
            try:
                match_date = parse_date(match_date_str)
            except ValueError:
                continue
            
            # Filter by date range
            if match_date < start_date or match_date > end_date:
                continue
            
            result = match.get("result", "")
            opponent_id = match.get("opponent_id")
            opponent_name = match.get("opponent_name", "Unknown")
            opponent_team = match.get("opponent_team", "Unknown")
            weight_class = match.get("weight_class")  # Bout weight class
            method = match.get("method", "")  # Match method (DEC, FALL, TF, MD, etc.)
            score = match.get("score", "")  # Match score (e.g., "5-3")
            duration = match.get("duration", "")  # Match duration (e.g., "6:00")
            
            if not opponent_id:
                continue
            
            # Determine winner and loser
            if result == "W":
                winner_id = wrestler_id
                winner_name = name
                winner_team = team
                loser_id = str(opponent_id)
                loser_name = opponent_name
                loser_team = opponent_team
            elif result == "L":
                winner_id = str(opponent_id)
                winner_name = opponent_name
                winner_team = opponent_team
                loser_id = wrestler_id
                loser_name = name
                loser_team = team
            else:
                continue  # Skip matches without clear result
            
            # Deduplicate matches (each match appears in both wrestlers' profiles)
            match_key = tuple(sorted([winner_id, loser_id]) + [match_date_str])
            if match_key in seen_match_keys:
                continue
            seen_match_keys.add(match_key)
            
            matches.append({
                "date": match_date_str,
                "winner_id": winner_id,
                "winner_name": winner_name,
                "winner_team": winner_team,
                "loser_id": loser_id,
                "loser_name": loser_name,
                "loser_team": loser_team,
                "weight_class": weight_class,  # Bout weight class
                "method": method,
                "score": score,
                "duration": duration,
            })
    
    print(f"Collected {len(matches)} unique matches in date range")
    return matches


def classify_matches(
    matches: List[Dict],
    drops: List[Dict],
    data_dir: Path,
    gender: str,
    season: int
) -> Tuple[List[Dict], List[Dict]]:
    """
    Classify matches as Top Matchups or Upsets based on rankings at match time.
    
    Returns:
        Tuple of (top_matchups, upsets) lists
    """
    top_matchups = []
    upsets = []
    
    # Cache ranking snapshots to avoid reloading
    rankings_cache = {}  # drop_id -> (rank_map, weight_map)
    
    for match in matches:
        match_date_str = match["date"]
        try:
            match_date = parse_date(match_date_str)
        except ValueError:
            continue
        
        # Find which drop's rankings to use
        drop_id = find_ranking_basis_drop(match_date, drops)
        if not drop_id:
            # No rankings available before this match date
            continue
        
        # Load rankings snapshot (with caching)
        if drop_id not in rankings_cache:
            rank_map, weight_map = load_rankings_snapshot(
                data_dir, gender, season, drop_id
            )
            rankings_cache[drop_id] = (rank_map, weight_map)
            print(f"Loaded rankings snapshot from drop {drop_id}: {len(rank_map)} ranked wrestlers")
        
        rank_map, weight_map = rankings_cache[drop_id]
        
        # Look up ranks from full rankings (everyone should be ranked if they're KY wrestlers)
        winner_rank = rank_map.get(match["winner_id"])
        loser_rank = rank_map.get(match["loser_id"])
        
        # Exclude matches where either wrestler is not found in rankings (out-of-state wrestler)
        # If either wrestler is not in rankings, they're out-of-state and we can't evaluate the match
        if winner_rank is None or loser_rank is None:
            continue
        
        # Get ranking weights (weight class at which each wrestler is ranked)
        winner_rank_weight = weight_map.get(match["winner_id"])
        loser_rank_weight = weight_map.get(match["loser_id"])
        bout_weight = match.get("weight_class")
        
        # Top Matchup: Both ranked Top 10
        if winner_rank <= 10 and loser_rank <= 10:
            match_entry = {
                **match,
                "winner_rank": winner_rank,
                "loser_rank": loser_rank,
                "winner_rank_weight": winner_rank_weight,
                "loser_rank_weight": loser_rank_weight,
                "ranking_basis_date": drop_id
            }
            top_matchups.append(match_entry)
            # Note: Don't continue here - match can also be an upset
        
        # Upset: Loser ranked Top 10, winner ranked worse than loser
        # Weight class differences are ignored - rank comparison is global
        if loser_rank <= 10 and winner_rank > loser_rank:
            # Calculate upset scores
            prestige_score = (11 - loser_rank) * 10
            differential_score = (winner_rank - loser_rank) * 2
            upset_score = prestige_score + differential_score
            
            # Determine result_type and score_or_time
            method = match.get("method", "")
            score = match.get("score", "")
            duration = match.get("duration", "")
            
            result_type = method if method else ""
            
            # score_or_time: score for DEC/MD, duration for FALL/TF/INJ
            if method in ["DEC", "MD"]:
                score_or_time = score if score else ""
            elif method in ["FALL", "TF", "INJ"]:
                score_or_time = duration if duration else ""
            else:
                score_or_time = score if score else duration if duration else ""
            
            match_entry = {
                **match,
                "match_date": match.get("date", ""),
                "winner_rank": winner_rank,
                "loser_rank": loser_rank,
                "winner_rank_weight": winner_rank_weight,
                "loser_rank_weight": loser_rank_weight,
                "ranking_basis_date": drop_id,
                "result_type": result_type,
                "score_or_time": score_or_time,
                "prestige_score": prestige_score,
                "differential_score": differential_score,
                "upset_score": upset_score
            }
            upsets.append(match_entry)
    
    return top_matchups, upsets


def main():
    """Main execution function."""
    args = parse_args()
    
    # Parse dates
    try:
        start_date = parse_date(args.start_date)
        end_date = parse_date(args.end_date)
    except ValueError as e:
        print(f"Error: {e}")
        return
    
    if start_date > end_date:
        print("Error: Start date must be before or equal to end date")
        return
    
    data_dir = Path(args.data_dir)
    
    print("=" * 60)
    print(f"Generating match highlights")
    print(f"Date range: {args.start_date} to {args.end_date}")
    print(f"Season: {args.season}, Gender: {args.gender}")
    print("=" * 60)
    
    # Load drops index
    print("\nLoading drops index...")
    drops = load_drops_index(data_dir, args.gender, args.season)
    if not drops:
        print("Error: No drops found. Cannot generate highlights.")
        return
    
    print(f"Found {len(drops)} drops")
    
    # Load wrestler profiles
    print("\nLoading wrestler profiles...")
    profiles = load_wrestler_profiles(data_dir, args.gender, args.season)
    if not profiles:
        print("Error: No wrestler profiles found.")
        return
    
    # Collect matches in date range
    print("\nCollecting matches in date range...")
    matches = collect_matches_in_range(profiles, start_date, end_date)
    if not matches:
        print("No matches found in date range.")
        return
    
    # Classify matches
    print("\nClassifying matches...")
    top_matchups, upsets = classify_matches(
        matches, drops, data_dir, args.gender, args.season
    )
    
    print(f"\nFound {len(top_matchups)} top matchups")
    print(f"Found {len(upsets)} upsets")
    
    # Sort top matchups: better_rank + 1.51 * worse_rank
    # Lower value = better matchup (appears first)
    def top_matchup_sort_key(match):
        winner_rank = match["winner_rank"]
        loser_rank = match["loser_rank"]
        better_rank = min(winner_rank, loser_rank)
        worse_rank = max(winner_rank, loser_rank)
        return better_rank + 1.51 * worse_rank
    
    top_matchups.sort(key=top_matchup_sort_key)
    
    # Sort upsets by upset_score (descending) and select Top 10
    upsets.sort(key=lambda m: m["upset_score"], reverse=True)
    top_10_upsets = upsets[:10]
    remaining_upsets = upsets[10:]
    
    # Print matches to console
    print("\n" + "=" * 80)
    print("TOP MATCHUPS (Top 10 vs Top 10)")
    print("=" * 80)
    if top_matchups:
        for match in top_matchups:
            bout_weight = match.get('weight_class')
            winner_rank_weight = match.get('winner_rank_weight')
            loser_rank_weight = match.get('loser_rank_weight')
            
            # Build weight display
            weight_parts = []
            if bout_weight:
                weight_parts.append(f"{bout_weight} lbs")
            
            # Add ranking weights if different from bout weight
            winner_weight_note = ""
            loser_weight_note = ""
            
            if winner_rank_weight and bout_weight and winner_rank_weight != bout_weight:
                winner_weight_note = f" (ranked at {winner_rank_weight} lbs)"
            if loser_rank_weight and bout_weight and loser_rank_weight != bout_weight:
                loser_weight_note = f" (ranked at {loser_rank_weight} lbs)"
            
            weight_display = f" | {' | '.join(weight_parts)}" if weight_parts else ""
            
            # Build result display
            result_parts = []
            method = match.get("method", "")
            score = match.get("score", "")
            duration = match.get("duration", "")
            
            if method:
                result_parts.append(method)
            if score:
                result_parts.append(score)
            if duration and method in ["FALL", "TF", "INJ"]:
                result_parts.append(f"({duration})")
            
            result_display = " | ".join(result_parts) if result_parts else ""
            
            print(f"\n{match['date']}{weight_display} | Ranking Basis: {match['ranking_basis_date']}")
            print(f"  #{match['winner_rank']} {match['winner_name']} ({match['winner_team']}){winner_weight_note}")
            print(f"    def. #{match['loser_rank']} {match['loser_name']} ({match['loser_team']}){loser_weight_note}")
            if result_display:
                print(f"    Result: {result_display}")
    else:
        print("  No top matchups found")
    
    print("\n" + "=" * 80)
    print("UPSETS (Top 10 loss to lower-ranked opponent)")
    print("=" * 80)
    if top_10_upsets:
        for match in top_10_upsets:
            bout_weight = match.get('weight_class')
            winner_rank_weight = match.get('winner_rank_weight')
            loser_rank_weight = match.get('loser_rank_weight')
            
            # Build weight display
            weight_parts = []
            if bout_weight:
                weight_parts.append(f"{bout_weight} lbs")
            
            # Add ranking weights if different from bout weight
            winner_weight_note = ""
            loser_weight_note = ""
            
            if winner_rank_weight and bout_weight and winner_rank_weight != bout_weight:
                winner_weight_note = f" (ranked at {winner_rank_weight} lbs)"
            if loser_rank_weight and bout_weight and loser_rank_weight != bout_weight:
                loser_weight_note = f" (ranked at {loser_rank_weight} lbs)"
            
            weight_display = f" | {' | '.join(weight_parts)}" if weight_parts else ""
            
            # Build result display
            result_parts = []
            method = match.get("method", "")
            score = match.get("score", "")
            duration = match.get("duration", "")
            
            if method:
                result_parts.append(method)
            if score:
                result_parts.append(score)
            if duration and method in ["FALL", "TF", "INJ"]:
                result_parts.append(f"({duration})")
            
            result_display = " | ".join(result_parts) if result_parts else ""
            
            print(f"\n{match['date']}{weight_display} | Ranking Basis: {match['ranking_basis_date']}")
            print(f"  #{match['winner_rank']} {match['winner_name']} ({match['winner_team']}){winner_weight_note}")
            print(f"    def. #{match['loser_rank']} {match['loser_name']} ({match['loser_team']}){loser_weight_note}")
            if result_display:
                print(f"    Result: {result_display}")
            print(f"    Upset Score: {match['upset_score']} (Prestige: {match['prestige_score']}, Differential: {match['differential_score']})")
    else:
        print("  No upsets found")
    
    # Prepare output data
    # Include all upsets (not just top 10) in the full dataset, but mark top 10
    output_data = {
        "season": args.season,
        "gender": args.gender,
        "start_date": args.start_date,
        "end_date": args.end_date,
        "generated_at": datetime.now().isoformat(),
        "top_matchups": top_matchups,
        "upsets": upsets,  # All upsets with scores
        "top_10_upsets": top_10_upsets  # Top 10 upsets for easy access
    }
    
    # Write output file
    output_dir = data_dir / "highlights" / args.gender / str(args.season)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_filename = f"{args.start_date}_to_{args.end_date}.json"
    output_file = output_dir / output_filename
    
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Highlights written to: {output_file}")
    print(f"  Top Matchups: {len(top_matchups)}")
    print(f"  Total Upsets: {len(upsets)}")
    print(f"  Top 10 Upsets: {len(top_10_upsets)}")


if __name__ == "__main__":
    main()

