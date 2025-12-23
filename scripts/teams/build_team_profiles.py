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
        "--teams-list",
        type=str,
        required=True,
        help="Path to NCAA D1 teams JSON file",
    )
    parser.add_argument(
        "--rankings-dir",
        type=str,
        required=True,
        help="Directory containing rankings_*.json files",
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
        default="frontend/wrestledata-ui/public/data/teams",
        help="Output directory for team profile JSON files (default: frontend/wrestledata-ui/public/data/teams)",
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


def load_rankings_by_weight(rankings_dir: str) -> Dict[str, List[Dict]]:
    """Load all rankings_*.json files, organized by weight."""
    rankings_dir_path = Path(rankings_dir)
    rankings_by_weight = {}
    
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
) -> Dict[str, Optional[str]]:
    """
    Resolve starters for a team across all weights.
    
    Returns: dict mapping weight -> wrestler_id (or None)
    """
    starters = {}
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


def main() -> None:
    args = parse_args()
    
    print(f"Building team profiles for season {args.season}...")
    print(f"Teams list: {args.teams_list}")
    print(f"Rankings dir: {args.rankings_dir}")
    print(f"Output dir: {args.out_dir}")
    
    # Step 1: Load team list
    print("\nStep 1: Loading team list...")
    teams_master = load_teams_list(args.teams_list)
    print(f"Loaded {len(teams_master)} teams")
    
    # Step 2: Load starter overrides
    print("\nStep 2: Loading starter overrides...")
    if args.starter_overrides:
        overrides_path = args.starter_overrides
    else:
        overrides_path = Path(args.rankings_dir) / "starter_overrides.json"
    
    force_backup_ids = load_starter_overrides(str(overrides_path))
    if force_backup_ids:
        print(f"Loaded {len(force_backup_ids)} starter overrides")
    else:
        print("No starter overrides found")
    
    # Step 3: Load rankings per weight
    print("\nStep 3: Loading rankings...")
    rankings_by_weight = load_rankings_by_weight(args.rankings_dir)
    print(f"Loaded rankings for {len(rankings_by_weight)} weight classes")
    
    # Step 4: Resolve starters for each team
    print("\nStep 4: Resolving starters...")
    teams_data = []
    
    for team in teams_master:
        team_name = team.get("name", "")
        abbreviation = team.get("abbreviation", "")
        state = team.get("state", "")
        governing_body = team.get("governing_body", "NCAA")
        division_str = team.get("division", "")
        url = team.get("url")
        
        # Normalize division
        division = "D1"
        
        # Extract conference
        conference = extract_conference(division_str)
        
        # Compute team_id
        team_id = slugify_team_name(team_name)
        
        # Resolve starters
        starters = resolve_starters_for_team(team_id, rankings_by_weight, force_backup_ids)
        
        # Build team data
        team_data = {
            "schema_version": "1.0",
            "season": args.season,
            "team_id": team_id,
            "team_name": team_name,
            "name": team_name,  # Keep for backward compatibility
            "abbreviation": abbreviation,
            "governing_body": governing_body,
            "division": division,
            "conference": conference,
            "location": {
                "state": state,
            },
            "urls": {
                "trackwrestling": url,
                "school": None,
            },
            "roster": {
                "weights": [125, 133, 141, 149, 157, 165, 174, 184, 197, 285],
                "starters": {
                    "125": starters.get("125"),
                    "133": starters.get("133"),
                    "141": starters.get("141"),
                    "149": starters.get("149"),
                    "157": starters.get("157"),
                    "165": starters.get("165"),
                    "174": starters.get("174"),
                    "184": starters.get("184"),
                    "197": starters.get("197"),
                    "285": starters.get("285"),
                },
                "starters_source": "ranking_files_with_overrides",
            },
            "derived_from": {
                "rankings_dir": args.rankings_dir,
                "starter_overrides_file": str(overrides_path) if overrides_path else None,
            },
            "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        
        teams_data.append(team_data)
    
    print(f"Resolved starters for {len(teams_data)} teams")
    
    # Step 5: Write team profile JSON files
    print("\nStep 5: Writing team profile files...")
    out_dir = Path(args.out_dir)
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


if __name__ == "__main__":
    main()

