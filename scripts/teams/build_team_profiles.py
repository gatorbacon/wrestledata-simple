#!/usr/bin/env python3
"""
Generate per-team profile JSON files (identity + starters snapshot).

This script creates lightweight team profiles derived from rankings + overrides.
Output files are disposable snapshots for frontend consumption.

IMPORTANT:
- Starters are NOT authoritative here; rankings + overrides are.
- This script MUST be re-run whenever rankings change.
- Does NOT compute metrics or read wrestler profiles.

Pipeline position:
  rankings build → build_team_profiles.py → build_wrestler_profiles.py → build_team_metrics.py

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


def validate_and_warn(teams_data: List[Dict], rankings_by_weight: Dict[str, List[Dict]], force_backup_ids: Set[str]) -> None:
    """Perform validation and emit warnings."""
    # Warn if team has fewer than 7 non-null starters
    for team_data in teams_data:
        team_id = team_data["team_id"]
        team_name = team_data["name"]
        starters = team_data["roster"]["starters"]
        
        non_null_count = sum(1 for wid in starters.values() if wid is not None)
        if non_null_count < 7:
            print(f"Warning: {team_name} ({team_id}) has only {non_null_count} starters (less than 7)")
    
    # Warn if the same wrestler_id is starter for multiple teams
    wrestler_to_teams = defaultdict(list)
    for team_data in teams_data:
        team_id = team_data["team_id"]
        team_name = team_data["name"]
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
        if gender == 'boys':
            weights = [106, 113, 120, 126, 132, 138, 144, 150, 157, 165, 175, 190, 215, 285]
        else: # girls
            weights = [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235]
    else: # ncaa
        teams_list_path = Path(f"data/team_lists/{season}/ncaa_d1_teams.json")
        rankings_dir = Path("mt/rankings_data") / str(season)
        starter_overrides_path = rankings_dir / "starter_overrides.json"
        out_dir = Path("frontend/wrestledata-ui/public/data/teams") / str(season)
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
        
        # Build team data
        team_data = {
            "schema_version": "1.0",
            "season": season,
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
            "roster": {
                "weights": weights,
                "starters": {str(w): starters.get(str(w)) for w in weights},
                "starters_source": "ranking_files_with_overrides",
            },
            "derived_from": {
                "rankings_dir": str(rankings_dir),
                "starter_overrides_file": str(starter_overrides_path) if starter_overrides_path else None,
            },
            "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
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

