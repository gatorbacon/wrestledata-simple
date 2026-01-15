#!/usr/bin/env python3
"""
Build leaderboard JSON files for HS KY wrestling.

Generates pre-aggregated leaderboards (Wins, Pins, Techs) from wrestler profiles.
All aggregation happens at build time - frontend only loads and displays.
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Set
from datetime import datetime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build leaderboard JSON files for HS KY wrestling"
    )
    parser.add_argument(
        "-season",
        type=int,
        required=True,
        help="Season year (e.g., 2026)",
    )
    parser.add_argument(
        "-league",
        type=str,
        default="hs",
        choices=["hs"],
        help="League type (default: hs)",
    )
    parser.add_argument(
        "-state",
        type=str,
        default="KY",
        help="State code (default: KY)",
    )
    parser.add_argument(
        "-gender",
        type=str,
        choices=["boys", "girls"],
        default=None,
        help="Gender: boys or girls (optional, processes both if not specified)",
    )
    return parser.parse_args()


def parse_record(record_str: str) -> tuple[int, int]:
    """
    Parse a record string like "26-2" into (wins, losses).
    Returns (0, 0) if parsing fails.
    """
    try:
        parts = record_str.split("-")
        if len(parts) == 2:
            wins = int(parts[0].strip())
            losses = int(parts[1].strip())
            return wins, losses
    except (ValueError, AttributeError):
        pass
    return 0, 0


def load_wrestler_profiles(profiles_dir: Path) -> List[Dict]:
    """Load all wrestler profile JSON files from the by_id directory."""
    profiles = []
    
    if not profiles_dir.exists():
        print(f"Warning: Profiles directory not found: {profiles_dir}")
        return profiles
    
    profile_files = list(profiles_dir.glob("*.json"))
    print(f"Found {len(profile_files)} wrestler profile files")
    
    for profile_file in profile_files:
        try:
            with open(profile_file, 'r', encoding='utf-8') as f:
                profile = json.load(f)
                profiles.append(profile)
        except Exception as e:
            print(f"Warning: Error loading {profile_file}: {e}")
            continue
    
    return profiles


def filter_wrestlers(profiles: List[Dict]) -> List[Dict]:
    """
    Filter wrestlers to include only those with valid stats.
    
    Include if:
    - Has record.overall that can be parsed
    - Has at least one match (wins + losses > 0)
    - Has metrics object
    """
    filtered = []
    
    for profile in profiles:
        # Check for record
        record_str = profile.get("record", {}).get("overall", "")
        if not record_str:
            continue
        
        wins, losses = parse_record(record_str)
        if wins + losses == 0:
            continue  # No matches
        
        # Check for metrics
        if "metrics" not in profile:
            continue
        
        # All checks passed
        filtered.append(profile)
    
    return filtered


def build_leaderboard(
    profiles: List[Dict],
    stat_type: str,  # "wins", "pins", or "techs"
    limit: int = 40
) -> List[Dict]:
    """
    Build a leaderboard for a specific stat type.
    
    Sorting rules (in order):
    1. Primary stat (descending)
    2. Fewer losses (ascending)
    3. Higher rank (lower number, use 999 for unranked)
    4. Alphabetical name (ascending)
    """
    entries = []
    
    for profile in profiles:
        wrestler_id = profile.get("wrestler_id", "")
        name = profile.get("name", "")
        team = profile.get("team", "")
        weight_class = profile.get("weight_class", 0)
        current_rank = profile.get("current_rank")
        rank = current_rank if current_rank is not None else 999
        
        record_str = profile.get("record", {}).get("overall", "")
        wins, losses = parse_record(record_str)
        
        metrics = profile.get("metrics", {})
        
        # Get the primary stat
        if stat_type == "wins":
            primary_stat = wins
        elif stat_type == "pins":
            primary_stat = metrics.get("pins", 0)
        elif stat_type == "techs":
            primary_stat = metrics.get("techs", 0)
        else:
            continue
        
        # Skip if primary stat is 0
        if primary_stat == 0:
            continue
        
        # Get other stats for display
        pins = metrics.get("pins", 0)
        techs = metrics.get("techs", 0)
        
        entry = {
            "wrestler_id": wrestler_id,
            "name": name,
            "team": team,
            "weight": weight_class,
            "rank": rank,
            "wins": wins,
            "losses": losses,
            "pins": pins,
            "techs": techs,
        }
        
        entries.append(entry)
    
    # Sort entries
    def sort_key(entry):
        if stat_type == "wins":
            primary = -entry["wins"]  # Negative for descending
        elif stat_type == "pins":
            primary = -entry["pins"]
        elif stat_type == "techs":
            primary = -entry["techs"]
        else:
            primary = 0
        
        return (
            primary,  # Primary stat (descending)
            entry["losses"],  # Fewer losses (ascending)
            entry["rank"],  # Higher rank/lower number (ascending)
            entry["name"].lower(),  # Alphabetical (ascending)
        )
    
    entries.sort(key=sort_key)
    
    # Limit to top N
    return entries[:limit]


def load_boys_inactive_mask(season: int) -> Set[str]:
    """Load boys inactive wrestlers mask file."""
    mask_file = Path(f"mt/rankings_data/hs_ky_boys/{season}/boys_inactive_wrestlers.json")
    
    if not mask_file.exists():
        return set()
    
    try:
        with mask_file.open("r", encoding="utf-8") as f:
            mask_data = json.load(f)
        
        masked_ids = set()
        for wrestler in mask_data.get("masked_wrestlers", []):
            wrestler_id = wrestler.get("boys_wrestler_id")
            if wrestler_id:
                masked_ids.add(str(wrestler_id))
        
        return masked_ids
    except Exception as e:
        print(f"Warning: Could not load boys inactive mask: {e}")
        return set()


def build_leaderboards_for_gender(
    season: int,
    gender: str,
    profiles_dir: Path,
    output_dir: Path
) -> None:
    """Build leaderboard JSON files for a single gender."""
    print(f"\n{'=' * 80}")
    print(f"Building leaderboards for {gender} season {season}")
    print(f"{'=' * 80}")
    
    # Load boys inactive mask (if boys)
    masked_wrestler_ids = set()
    if gender == 'boys':
        masked_wrestler_ids = load_boys_inactive_mask(season)
        if masked_wrestler_ids:
            print(f"Loaded mask for {len(masked_wrestler_ids)} inactive boys wrestlers")
    
    # Load profiles
    print(f"Loading profiles from: {profiles_dir}")
    profiles = load_wrestler_profiles(profiles_dir)
    print(f"Loaded {len(profiles)} profiles")
    
    # Filter out masked wrestlers (boys only)
    if masked_wrestler_ids:
        original_count = len(profiles)
        profiles = [p for p in profiles if str(p.get("wrestler_id", "")) not in masked_wrestler_ids]
        filtered_count = original_count - len(profiles)
        if filtered_count > 0:
            print(f"Filtered out {filtered_count} masked wrestler(s)")
    
    # Filter profiles
    filtered = filter_wrestlers(profiles)
    print(f"Filtered to {len(filtered)} wrestlers with valid stats")
    
    # Build leaderboards
    wins_leaderboard = build_leaderboard(filtered, "wins", limit=40)
    pins_leaderboard = build_leaderboard(filtered, "pins", limit=40)
    techs_leaderboard = build_leaderboard(filtered, "techs", limit=40)
    
    print(f"Generated leaderboards:")
    print(f"  Wins: {len(wins_leaderboard)} entries")
    print(f"  Pins: {len(pins_leaderboard)} entries")
    print(f"  Techs: {len(techs_leaderboard)} entries")
    
    # Build output JSON
    output_data = {
        "season": season,
        "gender": gender,
        "generated_at": datetime.now().strftime("%Y-%m-%d"),
        "wins": wins_leaderboard,
        "pins": pins_leaderboard,
        "techs": techs_leaderboard,
    }
    
    # Write output file
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "leaderboards.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Saved leaderboards to: {output_file}")


def main() -> None:
    args = parse_args()
    season = args.season
    league = args.league
    state = args.state
    gender = args.gender
    
    # Validate HS parameters
    if league == 'hs':
        if state.upper() != 'KY':
            raise ValueError(f"Only KY is currently supported for HS. Got: {state}")
        
        # Determine genders to process
        genders = [args.gender] if args.gender else ['boys', 'girls']
        
        for gender in genders:
            # Input: wrestler profiles
            profiles_dir = Path(f"frontend/hs-ky-ui/public/data/wrestlers/{gender}/{season}/by_id")
            
            # Output: leaderboard JSON
            output_dir = Path(f"frontend/hs-ky-ui/public/data/leaderboards/{gender}/{season}")
            
            build_leaderboards_for_gender(season, gender, profiles_dir, output_dir)
    else:
        raise ValueError(f"Only 'hs' league is supported. Got: {league}")
    
    print("\n✓ Leaderboard generation complete!")


if __name__ == "__main__":
    main()

