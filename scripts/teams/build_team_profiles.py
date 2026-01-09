#!/usr/bin/env python3
"""
Generate per-team profile JSON files (identity + starters snapshot).

This script creates lightweight team profiles derived from rankings + overrides.
Output files are disposable snapshots for frontend consumption.

For HS teams, this script now embeds FULL wrestler profiles in the team JSON,
eliminating the need for frontend to fetch individual wrestler JSON files.

IMPORTANT:
- Starters are NOT authoritative here; rankings + overrides are.
- This script MUST be re-run whenever rankings change.
- For HS: Requires wrestler profiles to already exist (run build_wrestler_profiles.py first).

Pipeline position:
  rankings build → build_wrestler_profiles.py → build_team_profiles.py → build_team_metrics.py

Usage:
    python scripts/teams/build_team_profiles.py \
        --season 2026 \
        --teams-list data/team_lists/2026/ncaa_d1_teams.json \
        --rankings-dir mt/rankings_data/2026 \
        --starter-overrides mt/rankings_data/2026/starter_overrides.json \
        --out-dir mt/teams
"""

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build team profile JSON files from rankings"
    )
    parser.add_argument(
        "--season",
        type=int,
        required=True,
        help="Season year (e.g., 2026)",
    )
    parser.add_argument(
        "-league",
        type=str,
        choices=["ncaa", "hs"],
        default="ncaa",
        help="League: 'ncaa' (default) or 'hs' for high school",
    )
    parser.add_argument(
        "-state",
        type=str,
        default=None,
        help="State code (required when league=hs, e.g., 'KY')",
    )
    parser.add_argument(
        "-gender",
        type=str,
        choices=["boys", "girls"],
        default=None,
        help="Gender: 'boys' or 'girls' (optional when league=hs, will process both if not specified)",
    )
    parser.add_argument(
        "--teams-list",
        type=str,
        default=None,
        help="Path to teams JSON file (auto-determined if not specified)",
    )
    parser.add_argument(
        "--rankings-dir",
        type=str,
        default=None,
        help="Directory containing rankings_*.json files (auto-determined if not specified)",
    )
    parser.add_argument(
        "--starter-overrides",
        type=str,
        default=None,
        help="Path to starter_overrides.json (optional)",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default=None,
        help="Output directory for team profile JSON files (auto-determined if not specified)",
    )
    return parser.parse_args()


def slugify_team_name(team_name: str) -> str:
    """Convert team name to team_id (slug)."""
    slug = team_name.lower()
    slug = slug.replace(" ", "_")
    # Strip punctuation
    slug = re.sub(r"[^\w_]", "", slug)
    # Collapse multiple underscores
    slug = re.sub(r"_+", "_", slug)
    slug = slug.strip("_")
    return slug


def extract_conference(division: str) -> Optional[str]:
    """Extract conference from division string (e.g., 'DI - Big 12' -> 'Big 12')."""
    if not division:
        return None
    
    # Look for pattern "DI - {Conference}" and extract unique conferences
    matches = re.findall(r"DI\s*-\s*([^,]+)", division)
    if matches:
        # Take first unique value
        conferences = [m.strip() for m in matches]
        if conferences:
            return conferences[0]
    
    return None


def load_teams_list(teams_list_path: str) -> List[Dict]:
    """Load team list JSON file."""
    with open(teams_list_path, "r", encoding="utf-8") as f:
        teams = json.load(f)
    return teams


def load_starter_overrides(overrides_path: Optional[str]) -> Set[str]:
    """Load starter overrides (force_backup_ids)."""
    if not overrides_path or not Path(overrides_path).exists():
        return set()
    
    try:
        with open(overrides_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("force_backup_ids", []))
    except Exception as e:
        print(f"Warning: Error loading starter overrides: {e}")
        return set()


def load_rankings_by_weight(rankings_dir: str, league: str = 'ncaa', gender: str = None) -> Dict[str, List[Dict]]:
    """Load all rankings_*.json files, organized by weight."""
    rankings_dir_path = Path(rankings_dir)
    rankings_by_weight = {}
    
    # Determine weight classes based on league and gender
    if league == 'hs':
        if gender == 'boys':
            weight_classes = ["106", "113", "120", "126", "132", "138", "144", "150", "157", "165", "175", "190", "215", "285"]
        else:  # girls
            weight_classes = ["100", "107", "114", "120", "126", "132", "138", "145", "152", "165", "185", "235"]
    else:  # ncaa
        weight_classes = ["125", "133", "141", "149", "157", "165", "174", "184", "197", "285"]
    
    for weight in weight_classes:
        rankings_file = rankings_dir_path / f"rankings_{weight}.json"
        if not rankings_file.exists():
            print(f"Warning: Rankings file not found: {rankings_file}")
            rankings_by_weight[weight] = []
            continue
        
        try:
            with rankings_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            rankings = data.get("rankings", [])
            rankings_by_weight[weight] = rankings
        except Exception as e:
            print(f"Warning: Error loading {rankings_file}: {e}")
            rankings_by_weight[weight] = []
    
    return rankings_by_weight


def apply_starter_overrides(
    rankings: List[Dict], force_backup_ids: Set[str]
) -> List[Dict]:
    """Apply starter overrides to rankings."""
    result = []
    for entry in rankings:
        wrestler_id = entry.get("wrestler_id")
        is_starter = entry.get("is_starter", True)
        
        # If wrestler is in force_backup_ids, set is_starter to False
        if wrestler_id in force_backup_ids:
            is_starter = False
        
        new_entry = {**entry, "is_starter": is_starter}
        result.append(new_entry)
    
    return result


def resolve_starters_for_team(
    team_id: str,
    rankings_by_weight: Dict[str, List[Dict]],
    force_backup_ids: Set[str],
    weight_classes: List[str] = None,
) -> Dict[str, Optional[str]]:
    """
    Resolve starters for a team across all weights.
    
    Returns: dict mapping weight -> wrestler_id (or None)
    """
    starters = {}
    if weight_classes is None:
        weight_classes = ["125", "133", "141", "149", "157", "165", "174", "184", "197", "285"]
    
    for weight in weight_classes:
        rankings = rankings_by_weight.get(weight, [])
        
        # Apply overrides
        rankings = apply_starter_overrides(rankings, force_backup_ids)
        
        # Filter to entries for this team
        team_entries = []
        for entry in rankings:
            team_name = entry.get("team", "")
            entry_team_id = slugify_team_name(team_name)
            if entry_team_id == team_id:
                team_entries.append(entry)
        
        if not team_entries:
            starters[weight] = None
            continue
        
        # Sort by rank (ascending)
        team_entries.sort(key=lambda x: (
            int(x.get("rank", 9999)) if isinstance(x.get("rank"), (int, str)) and str(x.get("rank")).isdigit() else 9999
        ))
        
        # First, try to find one marked as starter
        starter = None
        for entry in team_entries:
            if entry.get("is_starter", False):
                starter = entry
                break
        
        # If no starter found, use lowest rank as fallback
        if not starter and team_entries:
            starter = team_entries[0]
        
        if starter:
            wrestler_id = starter.get("wrestler_id")
            starters[weight] = wrestler_id
        else:
            starters[weight] = None
    
    return starters


def load_wrestler_profile(wrestler_id: str, wrestlers_dir: Path) -> Optional[Dict]:
    """
    Load wrestler profile JSON from by_id directory.
    
    Args:
        wrestler_id: Wrestler ID
        wrestlers_dir: Base directory for wrestlers (e.g., frontend/hs-ky-ui/public/data/wrestlers/{gender}/{season})
    
    Returns:
        Wrestler profile dict or None if not found
    """
    profile_path = wrestlers_dir / "by_id" / f"{wrestler_id}.json"
    
    if not profile_path.exists():
        return None
    
    try:
        with profile_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Error loading profile {wrestler_id}: {e}")
        return None


def load_team_roster_from_index(team_slug: str, index_teams_path: Path) -> List[str]:
    """
    Load full roster (all wrestler IDs) for a team from index_teams.json.
    
    Args:
        team_slug: Team slug (normalized team name)
        index_teams_path: Path to index_teams.json
    
    Returns:
        List of wrestler IDs (excluding OUTSTATE_ prefixed IDs)
    """
    if not index_teams_path.exists():
        return []
    
    try:
        with index_teams_path.open("r", encoding="utf-8") as f:
            index_data = json.load(f)
        
        # Find team entry
        for team_entry in index_data:
            if team_entry.get("team_slug") == team_slug:
                roster = team_entry.get("roster", [])
                # Filter out OUTSTATE_ IDs
                return [wid for wid in roster if wid and not str(wid).startswith("OUTSTATE_")]
        
        return []
    except Exception as e:
        print(f"Warning: Error loading index_teams.json: {e}")
        return []


def load_team_metrics(team_name: str, team_metrics_path: Path) -> Optional[Dict]:
    """
    Load team metrics for a specific team.
    
    Args:
        team_name: Team name
        team_metrics_path: Path to team_metrics.json
    
    Returns:
        Team metrics dict or None if not found
    """
    if not team_metrics_path.exists():
        return None
    
    try:
        with team_metrics_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        
        teams = data.get("teams", [])
        for team in teams:
            if team.get("team_name") == team_name or team.get("team") == team_name:
                return team
        
        return None
    except Exception as e:
        print(f"Warning: Error loading team metrics: {e}")
        return None


def load_team_xtp(team_name: str, xtp_path: Path) -> Optional[Dict]:
    """
    Load xTP data for a specific team.
    
    Args:
        team_name: Team name
        xtp_path: Path to xtp_teams_{season}.json
    
    Returns:
        Team xTP dict or None if not found
    """
    if not xtp_path.exists():
        return None
    
    try:
        with xtp_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Handle both array and object with 'teams' property
        teams_array = data if isinstance(data, list) else data.get("teams", [])
        
        for team in teams_array:
            if team.get("team") == team_name:
                return team
        
        return None
    except Exception as e:
        print(f"Warning: Error loading xTP data: {e}")
        return None


def calculate_top_record(match_list: List[Dict], max_rank: int) -> Dict[str, int]:
    """
    Calculate wins and losses vs opponents ranked <= max_rank.
    
    Args:
        match_list: List of match dicts with opponent_rank and result
        max_rank: Maximum rank to include (e.g., 10 for top-10, 33 for top-33)
    
    Returns:
        Dict with 'wins' and 'losses' keys
    """
    wins = 0
    losses = 0
    
    if not match_list:
        return {"wins": 0, "losses": 0}
    
    for match in match_list:
        opponent_rank = match.get("opponent_rank")
        if opponent_rank is None or opponent_rank > max_rank:
            continue
        
        result = match.get("result", "")
        if result and ("W" in result.upper() or "WIN" in result.upper()):
            wins += 1
        elif result and ("L" in result.upper() or "LOSS" in result.upper()):
            losses += 1
    
    return {"wins": wins, "losses": losses}


def count_top25_wins(match_list: List[Dict]) -> int:
    """
    Count wins vs opponents ranked <= 25.
    
    Args:
        match_list: List of match dicts with opponent_rank and result
    
    Returns:
        Number of wins vs top-25 opponents
    """
    if not match_list:
        return 0
    
    wins = 0
    for match in match_list:
        opponent_rank = match.get("opponent_rank")
        result = match.get("result", "")
        
        if opponent_rank is not None and opponent_rank <= 25:
            if result and ("W" in result.upper() or "WIN" in result.upper()):
                wins += 1
    
    return wins


def parse_record(record_str: str) -> Dict[str, int]:
    """
    Parse record string like "14-3" into wins and losses.
    
    Args:
        record_str: Record string like "14-3" or "0-0"
    
    Returns:
        Dict with 'wins' and 'losses' keys
    """
    if not record_str or not isinstance(record_str, str):
        return {"wins": 0, "losses": 0}
    
    parts = record_str.split("-")
    if len(parts) != 2:
        return {"wins": 0, "losses": 0}
    
    try:
        wins = int(parts[0].strip())
        losses = int(parts[1].strip())
        return {"wins": wins, "losses": losses}
    except ValueError:
        return {"wins": 0, "losses": 0}


def extract_minimal_starter_data(
    profile: Dict,
    weight: str,
    xtp_weight_data: Optional[Dict]
) -> Dict:
    """
    Extract minimal starter data needed for team page UI.
    
    Args:
        profile: Full wrestler profile dict
        weight: Weight class string
        xtp_weight_data: xTP data for this weight (from xtp_teams JSON)
    
    Returns:
        Minimal starter data dict
    """
    match_list = profile.get("match_list", [])
    
    # Precompute top-10 and top-33 records
    top10_record = calculate_top_record(match_list, 10)
    top33_record = calculate_top_record(match_list, 33)
    
    return {
        "weight": int(weight),
        "wrestler_id": profile.get("wrestler_id"),
        "name": profile.get("name"),
        "current_rank": profile.get("current_rank"),
        "xtp": xtp_weight_data.get("xTP", 0.0) if xtp_weight_data else 0.0,
        "xtp_p": xtp_weight_data.get("xTP_P", 0.0) if xtp_weight_data else 0.0,
        "xtp_a": xtp_weight_data.get("xTP_A", 0.0) if xtp_weight_data else 0.0,
        "xtp_b": xtp_weight_data.get("xTP_B", 0.0) if xtp_weight_data else 0.0,
        "top10_record": top10_record,
        "top33_record": top33_record,
    }


def extract_minimal_roster_data(profile: Dict) -> Dict:
    """
    Extract minimal roster data needed for remaining roster table.
    
    Args:
        profile: Full wrestler profile dict
    
    Returns:
        Minimal roster data dict
    """
    match_list = profile.get("match_list", [])
    record_str = profile.get("record", {}).get("overall", "0-0")
    record = parse_record(record_str)
    
    # Precompute top-25 wins
    top25_wins = count_top25_wins(match_list)
    
    return {
        "weight": profile.get("weight_class"),
        "wrestler_id": profile.get("wrestler_id"),
        "name": profile.get("name"),
        "wins": record["wins"],
        "losses": record["losses"],
        "top25_wins": top25_wins,
        "bonus_rate": profile.get("metrics", {}).get("bonus_rate"),
    }


def validate_and_warn(teams_data: List[Dict], rankings_by_weight: Dict[str, List[Dict]], force_backup_ids: Set[str]) -> None:
    """Perform validation and emit warnings."""
    # Warn if team has fewer than 7 non-null starters
    for team_data in teams_data:
        team_id = team_data["team_id"]
        team_name = team_data["name"]
        
        # Handle both old format (roster.starters) and new format (starters)
        if "starters" in team_data:
            # New format: starters is dict of weight -> profile object
            starters = team_data["starters"]
            non_null_count = sum(1 for profile in starters.values() if profile is not None)
        elif "roster" in team_data and "starters" in team_data["roster"]:
            # Old format: roster.starters is dict of weight -> wrestler_id
            starters = team_data["roster"]["starters"]
            non_null_count = sum(1 for wid in starters.values() if wid is not None)
        else:
            non_null_count = 0
        
        if non_null_count < 7:
            print(f"Warning: {team_name} ({team_id}) has only {non_null_count} starters (less than 7)")
    
    # Warn if the same wrestler_id is starter for multiple teams
    wrestler_to_teams = defaultdict(list)
    for team_data in teams_data:
        team_id = team_data["team_id"]
        team_name = team_data["name"]
        
        # Handle both formats
        if "starters" in team_data:
            # New format: extract wrestler_id from profile objects
            starters = team_data["starters"]
            for weight, profile in starters.items():
                if profile and isinstance(profile, dict):
                    wrestler_id = profile.get("wrestler_id")
                    if wrestler_id:
                        wrestler_to_teams[wrestler_id].append((team_id, team_name, weight))
        elif "roster" in team_data and "starters" in team_data["roster"]:
            # Old format: wrestler_id is the value
            starters = team_data["roster"]["starters"]
            for weight, wrestler_id in starters.items():
                if wrestler_id:
                    wrestler_to_teams[wrestler_id].append((team_id, team_name, weight))
    
    for wrestler_id, teams_list in wrestler_to_teams.items():
        if len(teams_list) > 1:
            teams_str = ", ".join([f"{name} ({tid}) at {w}" for tid, name, w in teams_list])
            print(f"Warning: Wrestler {wrestler_id} is starter for multiple teams: {teams_str}")


def process_league(season: int, league: str, state: str, gender: str, args: argparse.Namespace) -> None:
    """Process team profiles for a single league/gender combination."""
    # Setup paths based on league type
    if league == 'hs':
        teams_list_path = Path(f"data/team_lists/hs_{state.lower()}_{gender}/teams.json")
        rankings_dir = Path("mt/rankings_data") / f"hs_{state.lower()}_{gender}" / str(season)
        starter_overrides_path = rankings_dir / "starter_overrides.json"
        out_dir = Path("frontend/hs-ky-ui/public/data/teams") / gender / str(season)
        wrestlers_dir = Path("frontend/hs-ky-ui/public/data/wrestlers") / gender / str(season)
        index_teams_path = wrestlers_dir / "index_teams.json"
        team_metrics_path = Path("frontend/hs-ky-ui/public/data/team_metrics") / gender / str(season) / "team_metrics.json"
        xtp_path = Path("frontend/hs-ky-ui/public/data/xtp") / gender / str(season) / f"xtp_teams_{season}.json"
        if gender == 'boys':
            weights = [106, 113, 120, 126, 132, 138, 144, 150, 157, 165, 175, 190, 215, 285]
        else: # girls
            weights = [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235]
    else: # ncaa
        teams_list_path = Path(f"data/team_lists/{season}/ncaa_d1_teams.json")
        rankings_dir = Path("mt/rankings_data") / str(season)
        starter_overrides_path = rankings_dir / "starter_overrides.json"
        out_dir = Path("frontend/wrestledata-ui/public/data/teams") / str(season)
        wrestlers_dir = None  # Not used for NCAA
        index_teams_path = None
        team_metrics_path = None
        xtp_path = None
        weights = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]
    
    # Override with CLI args if provided
    if args.teams_list:
        teams_list_path = Path(args.teams_list)
    if args.rankings_dir:
        rankings_dir = Path(args.rankings_dir)
    if args.starter_overrides:
        starter_overrides_path = Path(args.starter_overrides)
    if args.out_dir:
        out_dir = Path(args.out_dir)
    
    print(f"Building team profiles for season {season} ({league.upper()} {state or ''} {gender or ''})...")
    print(f"Teams list: {teams_list_path}")
    print(f"Rankings dir: {rankings_dir}")
    print(f"Output dir: {out_dir}")
    if league == 'hs':
        print(f"Wrestlers dir: {wrestlers_dir}")
        print(f"Index teams: {index_teams_path}")
    
    # Step 1: Load team list
    print("\nStep 1: Loading team list...")
    teams_master = load_teams_list(str(teams_list_path))
    print(f"Loaded {len(teams_master)} teams")
    
    # Step 2: Load starter overrides
    print("\nStep 2: Loading starter overrides...")
    force_backup_ids = load_starter_overrides(str(starter_overrides_path))
    if force_backup_ids:
        print(f"Loaded {len(force_backup_ids)} starter overrides")
    else:
        print("No starter overrides found")
    
    # Step 3: Load rankings per weight
    print("\nStep 3: Loading rankings...")
    rankings_by_weight = load_rankings_by_weight(str(rankings_dir), league=league, gender=gender)
    print(f"Loaded rankings for {len(rankings_by_weight)} weight classes")
    
    # Step 4: Resolve starters for each team
    print("\nStep 4: Resolving starters...")
    teams_data = []
    
    # Convert weights to strings for consistency
    weight_strs = [str(w) for w in weights]
    
    for team in teams_master:
        team_name = team.get("name", "")
        abbreviation = team.get("abbreviation", "")
        state_from_team = team.get("state", "")
        governing_body = team.get("governing_body", "NCAA")
        division_str = team.get("division", "")
        url = team.get("url")
        region = team.get("region") # Get region for HS
        
        # Normalize division
        if league == 'hs':
            division = f"HS {gender.capitalize()}"
        else:
            division = "D1"
        
        # Extract conference (only for NCAA)
        conference = extract_conference(division_str) if league == 'ncaa' else None
        
        # Compute team_id
        team_id = slugify_team_name(team_name)
        
        # Resolve starters
        starters = resolve_starters_for_team(team_id, rankings_by_weight, force_backup_ids, weight_classes=weight_strs)
        
        # Build base team data
        team_data = {
            "schema_version": "2.0",  # Bump version for embedded profiles
            "season": season,
            "gender": gender if league == 'hs' else None,
            "team_id": team_id,
            "team_name": team_name,
            "name": team_name,  # Keep for backward compatibility
            "abbreviation": abbreviation,
            "governing_body": governing_body,
            "division": division,
            "conference": conference,
            "location": {
                "state": state_from_team,
                "region": region # Add region for HS
            },
            "urls": {
                "trackwrestling": url,
                "school": None,
            },
            "derived_from": {
                "rankings_dir": str(rankings_dir),
                "starter_overrides_file": str(starter_overrides_path) if starter_overrides_path else None,
            },
            "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        
        # For HS: Build minimal team profile with only UI-required data
        if league == 'hs' and wrestlers_dir and wrestlers_dir.exists() and index_teams_path and index_teams_path.exists():
            print(f"  Building minimal team profile for {team_name}...")
            
            # Load xTP data for this team (needed for starter xTP values)
            xtp_data = None
            if xtp_path and xtp_path.exists():
                xtp_data = load_team_xtp(team_name, xtp_path)
            
            # Load full roster from index_teams.json
            roster_ids = load_team_roster_from_index(team_id, index_teams_path)
            if not roster_ids:
                print(f"    Warning: No roster found in index_teams.json, using old format")
                team_data["roster"] = {
                    "weights": weights,
                    "starters": {str(w): starters.get(str(w)) for w in weights},
                    "starters_source": "ranking_files_with_overrides",
                }
            else:
                print(f"    Found {len(roster_ids)} wrestlers in roster")
                
                # Load all wrestler profiles (needed to extract minimal data)
                wrestler_profiles = {}
                profiles_loaded = 0
                profiles_missing = 0
                
                for wrestler_id in roster_ids:
                    profile = load_wrestler_profile(wrestler_id, wrestlers_dir)
                    if profile:
                        wrestler_profiles[wrestler_id] = profile
                        profiles_loaded += 1
                    else:
                        profiles_missing += 1
                
                if profiles_missing > 0:
                    print(f"    Warning: {profiles_missing} profiles not found (may not be generated yet)")
                
                print(f"    Loaded {profiles_loaded} wrestler profiles")
                
                # Build starters with minimal data (keyed by weight)
                starters_minimal = {}
                starter_ids_set = set(str(v) for v in starters.values() if v)
                
                for weight_str, starter_id in starters.items():
                    if starter_id and starter_id in wrestler_profiles:
                        profile = wrestler_profiles[starter_id]
                        # Get xTP data for this weight
                        xtp_weight_data = None
                        if xtp_data and "weights" in xtp_data:
                            xtp_weight_data = xtp_data["weights"].get(weight_str)
                        
                        starters_minimal[weight_str] = extract_minimal_starter_data(
                            profile, weight_str, xtp_weight_data
                        )
                    elif starter_id:
                        # Starter ID exists but profile not found - log warning
                        print(f"    Warning: Starter profile not found for {starter_id} at {weight_str}")
                
                # Build remaining roster with minimal data (non-starters)
                remaining_minimal = []
                for wrestler_id, profile in wrestler_profiles.items():
                    if str(wrestler_id) not in starter_ids_set:
                        remaining_minimal.append(extract_minimal_roster_data(profile))
                
                # Sort remaining by weight, then by name
                remaining_minimal.sort(key=lambda p: (
                    p.get("weight", 999),
                    p.get("name", "")
                ))
                
                # Embed minimal data in team data
                team_data["starters"] = starters_minimal
                team_data["remaining"] = remaining_minimal
                
                # Load and embed team metrics if available
                if team_metrics_path and team_metrics_path.exists():
                    team_metrics = load_team_metrics(team_name, team_metrics_path)
                    if team_metrics:
                        # Extract metrics from nested structure (team_metrics.metrics.*)
                        metrics_obj = team_metrics.get("metrics", {})
                        
                        # Extract only the fields needed for team overview
                        # Get wins/losses from counts object (wins_included/losses_included)
                        counts = team_metrics.get("counts", {})
                        
                        team_data["team_metrics"] = {
                            "projected_state_points": team_metrics.get("projected_state_points"),
                            "team_rank": team_metrics.get("team_rank"),
                            "placement_points": team_metrics.get("placement_points"),
                            "advancement_points": team_metrics.get("advancement_points"),
                            "bonus_points": team_metrics.get("bonus_points"),
                            "overall": {
                                "wins": counts.get("wins_included") or team_metrics.get("total_wins"),
                                "losses": counts.get("losses_included") or team_metrics.get("total_losses"),
                            },
                            "top33": {
                                "wins": None,  # Will be computed from starters
                                "losses": None,
                            },
                            "top10": {
                                "wins": None,  # Will be computed from starters
                                "losses": None,
                            },
                            # Extract from metrics.metrics.* structure (nested objects with value/rank)
                            "bonus_rate": metrics_obj.get("bonus_rate"),
                            "pin_rate": metrics_obj.get("pin_rate"),
                            "tech_rate": metrics_obj.get("tech_rate"),
                        }
                        
                        # Compute top10/top33 records from starters
                        top10_wins = sum(s.get("top10_record", {}).get("wins", 0) for s in starters_minimal.values())
                        top10_losses = sum(s.get("top10_record", {}).get("losses", 0) for s in starters_minimal.values())
                        top33_wins = sum(s.get("top33_record", {}).get("wins", 0) for s in starters_minimal.values())
                        top33_losses = sum(s.get("top33_record", {}).get("losses", 0) for s in starters_minimal.values())
                        
                        team_data["team_metrics"]["top10"]["wins"] = top10_wins
                        team_data["team_metrics"]["top10"]["losses"] = top10_losses
                        team_data["team_metrics"]["top33"]["wins"] = top33_wins
                        team_data["team_metrics"]["top33"]["losses"] = top33_losses
                
                # Log file size estimate
                json_str = json.dumps(team_data, indent=2, ensure_ascii=False)
                size_kb = len(json_str.encode('utf-8')) / 1024
                print(f"    Team JSON size: {size_kb:.1f} KB")
        else:
            # NCAA or HS without wrestler profiles: use old format
            team_data["roster"] = {
                "weights": weights,
                "starters": {str(w): starters.get(str(w)) for w in weights},
                "starters_source": "ranking_files_with_overrides",
            }
        
        teams_data.append(team_data)
    
    print(f"Resolved starters for {len(teams_data)} teams")
    
    # Step 5: Write team profile JSON files
    print("\nStep 5: Writing team profile files...")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    for team_data in teams_data:
        team_id = team_data["team_id"]
        output_file = out_dir / f"{team_id}.json"
        
        with output_file.open("w", encoding="utf-8") as f:
            json.dump(team_data, f, indent=2, ensure_ascii=False)
    
    print(f"Wrote {len(teams_data)} team profile files to {out_dir}")
    
    # Step 6: Validation and warnings
    print("\nStep 6: Validation...")
    validate_and_warn(teams_data, rankings_by_weight, force_backup_ids)
    
    print("\nDone!")


def main() -> None:
    args = parse_args()
    season = args.season
    league = args.league
    state = args.state
    gender = args.gender
    
    # Validate HS parameters
    if league == 'hs':
        if not state:
            raise ValueError("For HS league, -state is required.")
        # Process both genders automatically
        genders = ['boys', 'girls']
        for gender in genders:
            print(f"\n{'=' * 80}")
            print(f"Processing {gender}...")
            print(f"{'=' * 80}")
            process_league(season, league, state, gender, args)
    else: # ncaa
        process_league(season, league, state, None, args)


if __name__ == "__main__":
    main()

