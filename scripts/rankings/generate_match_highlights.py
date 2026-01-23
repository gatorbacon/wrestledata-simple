#!/usr/bin/env python3
"""
generate_match_highlights.py

Generates weekly match highlights (Top Matchups and Upsets) for a given date range.

This script:
1. Loads archived rankings snapshots
2. Collects matches from wrestler profiles within the date range
3. Optionally includes manual matches (if --state is provided for HS mode)
4. For each match, determines which ranking snapshot to use (most recent drop before match date)
5. Classifies matches as Top Matchups (Top 10 vs Top 10) or Upsets (Top 20 loss to lower-ranked/unranked)
6. Outputs JSON file for frontend consumption

Usage:
    python scripts/rankings/generate_match_highlights.py \
        --start-date 2026-01-06 \
        --end-date 2026-01-13 \
        --season 2026 \
        --gender boys \
        --league hs \
        --state KY
"""

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, date
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Try to import cairosvg and PIL for SVG to JPG conversion
try:
    import cairosvg
    from PIL import Image
    CAIROSVG_AVAILABLE = True
except ImportError:
    CAIROSVG_AVAILABLE = False


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
        "--state",
        type=str,
        default=None,
        help="State code (e.g., 'KY') - required for loading manual matches in HS mode"
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="frontend/hs-ky-ui/public/data",
        help="Base directory for data files"
    )
    parser.add_argument(
        "--rankings-data-dir",
        type=str,
        default="mt/rankings_data",
        help="Directory for rankings data (where manual matches are stored)"
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


def load_manual_matches(
    season: int,
    rankings_data_dir: str,
    league: str = 'hs',
    state: str = None,
    gender: str = None
) -> List[Dict]:
    """
    Load manual match overrides from JSON file.
    
    Manual matches are ranking hints only - they do NOT appear in profiles or historical data.
    
    Returns:
        List of manual match dictionaries with winner_id, loser_id, optional date/note
    """
    from pathlib import Path
    
    if league == 'hs' and state and gender:
        # HS path format: hs_{state}_{gender}/{season}
        manual_file = Path(rankings_data_dir) / f"hs_{state}_{gender}" / str(season) / "manual_matches.json"
    else:
        manual_file = Path(rankings_data_dir) / str(season) / "manual_matches.json"
    
    if not manual_file.exists():
        return []
    
    try:
        with manual_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("manual_matches", [])
    except Exception as e:
        print(f"Warning: Could not load manual matches: {e}")
        return []


def collect_matches_in_range(
    profiles: Dict[str, Dict],
    start_date: date,
    end_date: date,
    manual_matches: List[Dict] = None
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
    
    # Now add manual matches (if provided)
    if manual_matches:
        manual_count = 0
        for manual_match in manual_matches:
            winner_id = str(manual_match.get('winner_id', ''))
            loser_id = str(manual_match.get('loser_id', ''))
            manual_date_str = manual_match.get('date')
            
            # Skip if no date (can't filter by date range)
            if not manual_date_str:
                continue
            
            # Parse and filter by date range
            # Manual matches might have dates in MM/DD/YYYY format
            manual_date = None
            try:
                # Try YYYY-MM-DD format first
                manual_date = parse_date(manual_date_str)
            except ValueError:
                # Try MM/DD/YYYY format
                try:
                    manual_date = datetime.strptime(manual_date_str, "%m/%d/%Y").date()
                except ValueError:
                    # Try other common formats
                    for fmt in ["%m-%d-%Y", "%Y/%m/%d"]:
                        try:
                            manual_date = datetime.strptime(manual_date_str, fmt).date()
                            break
                        except ValueError:
                            continue
            
            if not manual_date:
                continue
            
            if manual_date < start_date or manual_date > end_date:
                continue
            
            # Normalize date format to YYYY-MM-DD for consistency
            normalized_date_str = manual_date.strftime("%Y-%m-%d")
            
            # Skip if either wrestler not in profiles
            if winner_id not in profiles or loser_id not in profiles:
                continue
            
            # Check if this match already exists in regular matches (deduplicate)
            # Use normalized date for deduplication
            match_key = tuple(sorted([winner_id, loser_id]) + [normalized_date_str])
            if match_key in seen_match_keys:
                continue
            seen_match_keys.add(match_key)
            
            # Get wrestler info from profiles
            winner_profile = profiles[winner_id]
            loser_profile = profiles[loser_id]
            
            matches.append({
                "date": normalized_date_str,
                "winner_id": winner_id,
                "winner_name": winner_profile.get("name", "Unknown"),
                "winner_team": winner_profile.get("team", "Unknown"),
                "loser_id": loser_id,
                "loser_name": loser_profile.get("name", "Unknown"),
                "loser_team": loser_profile.get("team", "Unknown"),
                "weight_class": None,  # Manual matches don't have weight class
                "method": "M",  # Mark as manual
                "score": None,
                "duration": None,
                "is_manual": True,  # Flag to indicate this is a manual match
                "note": manual_match.get("note")
            })
            manual_count += 1
        
        if manual_count > 0:
            print(f"Added {manual_count} manual matches to collection")
    
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
    
    # Load manual matches (if state is provided for HS mode)
    manual_matches = []
    if args.league == 'hs' and args.state:
        print("\nLoading manual matches...")
        manual_matches = load_manual_matches(
            args.season,
            args.rankings_data_dir,
            args.league,
            args.state,
            args.gender
        )
        if manual_matches:
            print(f"Loaded {len(manual_matches)} manual match(es)")
        else:
            print("No manual matches found")
    elif args.league == 'hs' and not args.state:
        print("\nNote: --state not provided, skipping manual matches (use --state to include them)")
    
    # Collect matches in date range
    print("\nCollecting matches in date range...")
    matches = collect_matches_in_range(profiles, start_date, end_date, manual_matches)
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
    
    # Generate upsets graphic if we have at least one upset
    if top_10_upsets:
        print("\nGenerating upsets graphic...")
        generate_upsets_graphic(
            top_10_upsets[:5],  # Top 5 upsets
            start_date,
            end_date,
            args.gender,
            args.season
        )


def format_date_range(start_date: date, end_date: date) -> str:
    """Format date range as 'WEEK OF [MONTH] [DAY]-[DAY]'."""
    month_names = ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
                   "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"]
    
    start_month = month_names[start_date.month - 1]
    start_day = start_date.day
    
    # If same month, just show day range
    if start_date.month == end_date.month:
        end_day = end_date.day
        return f"WEEK OF {start_month} {start_day}-{end_day}"
    else:
        # Different months - show full dates
        end_month = month_names[end_date.month - 1]
        end_day = end_date.day
        return f"WEEK OF {start_month} {start_day} - {end_month} {end_day}"


def format_match_result(method: str) -> str:
    """Format match method as abbreviation (FALL, DEC, MD, TF, etc.)."""
    if not method:
        return ""
    method_upper = method.upper()
    # Map common methods
    method_map = {
        "FALL": "FALL",
        "PIN": "FALL",
        "DEC": "DEC",
        "DECISION": "DEC",
        "MD": "MD",
        "MAJOR": "MD",
        "TF": "TF",
        "TECH": "TF",
        "TECHNICAL": "TF",
        "MFF": "MFF",
        "FOR": "FF",
        "FORFEIT": "FF",
        "FF": "FF",
        "INJ": "INJ",
        "INJURY": "INJ",
        "DQ": "DQ",
        "DISQUAL": "DQ"
    }
    return method_map.get(method_upper, method_upper[:4])


def format_match_details(method: str, score: str, duration: str) -> str:
    """Format match details (time for pin, score for decision)."""
    if not method:
        return ""
    method_upper = method.upper()
    
    if method_upper in ["FALL", "PIN", "TF", "TECH", "TECHNICAL", "INJ", "INJURY"]:
        # Use duration (time) for falls and tech falls
        # Special case: if duration is "0:00", it means we don't know the actual time, so omit it
        if duration and duration.strip() not in ["0:00", "0:0", "00:00"]:
            return f"({duration})"
        return ""
    elif method_upper in ["DEC", "DECISION", "MD", "MAJOR"]:
        # Use score for decisions
        if score:
            return f"({score})"
        return ""
    else:
        # For other types, prefer score, fallback to duration
        if score:
            return f"({score})"
        if duration and duration.strip() not in ["0:00", "0:0", "00:00"]:
            return f"({duration})"
        return ""


def generate_upsets_graphic(
    top_5_upsets: List[Dict],
    start_date: date,
    end_date: date,
    gender: str,
    season: int
) -> None:
    """Generate JPG graphic from SVG template for top 5 upsets."""
    template_path = Path("mt/graphics/templates/TOP-UPSETS-TEMPLATE.svg")
    output_dir = Path(f"mt/graphics/{season}")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate filename based on date range
    date_str = f"{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}"
    output_jpg = output_dir / f"top_upsets_{gender}_{season}_{date_str}.jpg"
    
    if not template_path.exists():
        print(f"Warning: Template not found at {template_path}, skipping graphic generation")
        return
    
    # Read template
    with open(template_path, 'r', encoding='utf-8') as f:
        svg_content = f.read()
    
    # Replace description (KENTUCKY BOYS WRESTLING or KENTUCKY GIRLS WRESTLING)
    gender_display = "KENTUCKY BOYS WRESTLING" if gender == "boys" else "KENTUCKY GIRLS WRESTLING"
    svg_content = re.sub(
        r'(inkscape:label="description"[^>]*>[\s\S]*?<tspan[^>]*>)[^<]*(</tspan>)',
        lambda m: m.group(1) + gender_display + m.group(2),
        svg_content
    )
    
    # Replace daterange (find "WEEK OF" text and replace)
    date_range_str = format_date_range(start_date, end_date)
    svg_content = re.sub(
        r'(<tspan[^>]*>WEEK OF[^<]*</tspan>)',
        rf'<tspan sodipodi:role="line" id="tspan52" style="stroke-width:0.287863" x="1820.8248" y="288.31433">{date_range_str}</tspan>',
        svg_content
    )
    
    # Process top 5 upsets
    for idx, upset in enumerate(top_5_upsets[:5], 1):
        # Check if this is a manual match and prompt for missing info
        is_manual = upset.get('is_manual', False)
        if is_manual:
            print(f"\n⚠️  Manual match detected in top 5 upsets (#{idx}):")
            print(f"   {upset.get('winner_name', 'Unknown')} def. {upset.get('loser_name', 'Unknown')}")
            
            # Prompt for weight class if missing
            weight_class = upset.get('weight_class', '')
            if not weight_class:
                weight_input = input(f"   Enter weight class (e.g., '185'): ").strip()
                if weight_input:
                    weight_class = weight_input
                    upset['weight_class'] = weight_class
            
            # Always prompt for match result and details for manual matches
            method = upset.get('method', '')
            score = upset.get('score', '')
            duration = upset.get('duration', '')
            
            # Prompt for match result type
            method_input = input(f"   Enter match result type (FALL, DEC, MD, TF, etc.): ").strip()
            if method_input:
                method = method_input.upper()
                upset['method'] = method
                
                # Prompt for details based on result type
                if method in ['FALL', 'PIN', 'TF', 'TECH', 'TECHNICAL', 'INJ', 'INJURY']:
                    detail_input = input(f"   Enter time (e.g., '2:33'): ").strip()
                    if detail_input:
                        duration = detail_input
                        upset['duration'] = duration
                elif method in ['DEC', 'DECISION', 'MD', 'MAJOR']:
                    detail_input = input(f"   Enter score (e.g., '17-1'): ").strip()
                    if detail_input:
                        score = detail_input
                        upset['score'] = score
                else:
                    # For other result types, ask if they want to add details
                    detail_input = input(f"   Enter match details (optional, e.g., score or time): ").strip()
                    if detail_input:
                        # Try to determine if it's a score or time
                        if ':' in detail_input:
                            duration = detail_input
                            upset['duration'] = duration
                        else:
                            score = detail_input
                            upset['score'] = score
        
        # Get weight class (may have been updated above)
        weight_class = upset.get('weight_class', '')
        if weight_class:
            # Replace weight (use lambda to avoid regex group reference issues)
            pattern = rf'(inkscape:label="weight{idx}"[^>]*>[\s\S]*?<tspan[^>]*>)[^<]*(</tspan>)'
            svg_content = re.sub(pattern, lambda m: m.group(1) + str(weight_class) + m.group(2), svg_content)
        
        # Get winner info
        winner_rank = upset.get('winner_rank', '')
        winner_name = upset.get('winner_name', 'Unknown')
        winner_team = upset.get('winner_team', 'Unknown')
        
        # Replace winner (complex nested structure: #X   Name (Team))
        # Pattern: inkscape:label="winnerX">...<tspan>#X   <tspan>Name</tspan> <tspan>(Team)</tspan></tspan>
        # We need to replace the rank number, name, and team while preserving structure
        winner_pattern = rf'(inkscape:label="winner{idx}"[^>]*>[\s\S]*?<tspan[^>]*>)#X\s+<tspan[^>]*>[^<]*</tspan>\s+<tspan[^>]*>\([^)]*\)</tspan>(</tspan>)'
        # Escape XML special characters in names/teams
        winner_name_escaped = winner_name.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        winner_team_escaped = winner_team.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        # Use lambda to avoid regex group reference issues
        winner_replacement_text = f'#{winner_rank}   <tspan style="letter-spacing:0px" id="tspan46">{winner_name_escaped}</tspan> <tspan style="font-style:normal;font-variant:normal;font-weight:500;font-stretch:normal;font-size:7.76111px;line-height:1.25;font-family:\'Alegreya Sans\';-inkscape-font-specification:\'Alegreya Sans Medium\';font-variant-ligatures:normal;font-variant-position:normal;font-variant-caps:normal;font-variant-numeric:normal;font-variant-alternates:normal;font-variant-east-asian:normal;font-feature-settings:\'ss3\';text-indent:0;text-align:start;text-decoration:none;text-decoration-line:none;text-decoration-style:solid;text-decoration-color:#000000;letter-spacing:-0.195781px;word-spacing:0px;text-transform:none;writing-mode:lr-tb;direction:ltr;text-orientation:mixed;dominant-baseline:auto;baseline-shift:baseline;white-space:normal;vector-effect:none;fill:#ffffff;fill-opacity:1;stroke-width:0.425147;stroke-linecap:butt;stroke-linejoin:miter;stroke-miterlimit:4;stroke-dasharray:none;stroke-dashoffset:0;stroke-opacity:1;-inkscape-stroke:none;paint-order:markers fill stroke;filter:url(#filter30);stop-color:#000000;stop-opacity:1" id="tspan68">({winner_team_escaped})</tspan>'
        svg_content = re.sub(winner_pattern, lambda m: m.group(1) + winner_replacement_text + m.group(2), svg_content)
        
        # Get loser info
        loser_rank = upset.get('loser_rank', '')
        loser_name = upset.get('loser_name', 'Unknown')
        loser_team = upset.get('loser_team', 'Unknown')
        
        # Replace loser (complex nested structure: def. #Y   Name (Team))
        # Pattern: inkscape:label="loserX">...<tspan><tspan>def.   </tspan>#Y   <tspan>Name</tspan> <tspan>(Team)</tspan></tspan>
        # Note: The template has "def.   " (with multiple spaces) before #Y
        loser_pattern = rf'(inkscape:label="loser{idx}"[^>]*>[\s\S]*?<tspan[^>]*><tspan[^>]*>def\.\s+</tspan>)#Y\s+<tspan[^>]*>[^<]*</tspan>\s+<tspan[^>]*>\([^)]*\)</tspan>(</tspan>)'
        # Escape XML special characters in names/teams
        loser_name_escaped = loser_name.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        loser_team_escaped = loser_team.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        # Use lambda to avoid regex group reference issues
        loser_replacement_text = f'#{loser_rank}   <tspan style="letter-spacing:0px" id="tspan47">{loser_name_escaped}</tspan> <tspan style="font-style:normal;font-variant:normal;font-weight:500;font-stretch:normal;font-size:7.76111px;line-height:1.25;font-family:\'Alegreya Sans\';-inkscape-font-specification:\'Alegreya Sans Medium\';font-variant-ligatures:normal;font-variant-position:normal;font-variant-caps:normal;font-variant-numeric:normal;font-variant-alternates:normal;font-variant-east-asian:normal;font-feature-settings:\'ss3\';text-indent:0;text-align:start;text-decoration:none;text-decoration-line:none;text-decoration-style:solid;text-decoration-color:#000000;letter-spacing:-0.195781px;word-spacing:0px;text-transform:none;writing-mode:lr-tb;direction:ltr;text-orientation:mixed;dominant-baseline:auto;baseline-shift:baseline;white-space:normal;vector-effect:none;fill:#ffffff;fill-opacity:1;stroke-width:0.425147;stroke-linecap:butt;stroke-linejoin:miter;stroke-miterlimit:4;stroke-dasharray:none;stroke-dashoffset:0;stroke-opacity:1;-inkscape-stroke:none;paint-order:markers fill stroke;filter:url(#filter30);stop-color:#000000;stop-opacity:1" id="tspan72">({loser_team_escaped})</tspan>'
        svg_content = re.sub(loser_pattern, lambda m: m.group(1) + loser_replacement_text + m.group(2), svg_content)
        
        # Get match result and details (may have been updated above for manual matches)
        method = upset.get('method', '')
        score = upset.get('score', '')
        duration = upset.get('duration', '')
        
        result_type = format_match_result(method)
        match_details = format_match_details(method, score, duration)
        
        # Replace match result (use lambda to avoid regex group reference issues)
        result_pattern = rf'(inkscape:label="matchresult{idx}"[^>]*>[\s\S]*?<tspan[^>]*>)[^<]*(</tspan>)'
        svg_content = re.sub(result_pattern, lambda m: m.group(1) + result_type + " " + m.group(2), svg_content)
        
        # Replace match details (use lambda to avoid regex group reference issues)
        details_pattern = rf'(inkscape:label="matchdetails{idx}"[^>]*>[\s\S]*?<tspan[^>]*>)[^<]*(</tspan>)'
        svg_content = re.sub(details_pattern, lambda m: m.group(1) + match_details + m.group(2), svg_content)
    
    # Save temporary SVG
    temp_svg = output_dir / f"temp_upsets_{gender}_{season}_{date_str}.svg"
    with open(temp_svg, 'w', encoding='utf-8') as f:
        f.write(svg_content)
    
    # Convert to JPG
    if CAIROSVG_AVAILABLE:
        render_svg_to_jpg(temp_svg, output_jpg, width=2000, height=2000)
        # Clean up temporary SVG
        temp_svg.unlink()
    else:
        print("Warning: cairosvg/PIL not available. SVG saved but JPG conversion skipped.")
        print(f"  SVG saved to: {temp_svg}")
        print("  Install with: pip install cairosvg pillow")


def render_svg_to_jpg(svg_path: Path, jpg_path: Path, width: int = 2000, height: int = 2000) -> None:
    """Render SVG to JPG using cairosvg."""
    if not CAIROSVG_AVAILABLE:
        return
    
    jpg_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Render SVG to PNG in memory, then convert to JPG via Pillow
    png_bytes = cairosvg.svg2png(url=str(svg_path), output_width=width, output_height=height)
    img = Image.open(BytesIO(png_bytes)).convert("RGB")
    img.save(jpg_path, format="JPEG", quality=95)
    
    print(f"  ✓ Upsets graphic generated: {jpg_path}")


if __name__ == "__main__":
    main()

