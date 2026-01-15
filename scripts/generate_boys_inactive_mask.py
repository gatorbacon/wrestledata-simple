#!/usr/bin/env python3
"""
Generate boys_inactive_wrestlers.json - Build-time mask for inactive girls on boys rosters.

This script identifies boys-side wrestlers who:
1. Appear on both boys and girls rosters (same name, same team)
2. Have zero valid matches on the boys side

These wrestlers will be masked from boys frontend outputs but remain in raw data.

Usage:
    python scripts/generate_boys_inactive_mask.py -season 2026
"""

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate boys_inactive_wrestlers.json mask file"
    )
    parser.add_argument(
        "-season",
        type=int,
        required=True,
        help="Season year (e.g., 2026)",
    )
    parser.add_argument(
        "-state",
        type=str,
        default="KY",
        help="State code (default: KY)",
    )
    parser.add_argument(
        "--boys-data-dir",
        type=str,
        default=None,
        help="Directory containing boys team JSON files (default: mt/data/hs_ky_boys/{season})",
    )
    parser.add_argument(
        "--girls-data-dir",
        type=str,
        default=None,
        help="Directory containing girls team JSON files (default: mt/data/hs_ky_girls/{season})",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for mask file (default: mt/rankings_data/hs_ky_boys/{season})",
    )
    return parser.parse_args()


def normalize_name(name: str) -> str:
    """Normalize wrestler name for matching."""
    if not name:
        return ""
    # Lowercase
    normalized = name.lower()
    # Strip punctuation
    normalized = re.sub(r"[^\w\s]", "", normalized)
    # Collapse whitespace
    normalized = re.sub(r"\s+", " ", normalized)
    # Strip leading/trailing whitespace
    return normalized.strip()


def normalize_team_name(team_name: str) -> str:
    """Normalize team name for matching."""
    if not team_name:
        return ""
    # Lowercase
    normalized = team_name.lower()
    # Strip punctuation
    normalized = re.sub(r"[^\w\s]", "", normalized)
    # Collapse whitespace
    normalized = re.sub(r"\s+", " ", normalized)
    # Strip leading/trailing whitespace
    return normalized.strip()


def is_valid_match(match: Dict) -> bool:
    """
    Check if a match is valid (not BYE, NoResult, etc.).
    
    Returns True if match should be counted, False otherwise.
    """
    summary = match.get("summary", "").lower()
    
    # Skip BYE matches
    if "received a bye" in summary or "bye" in summary:
        return False
    
    # Skip NoResult matches (if result field exists)
    result = match.get("result", "").upper()
    if result in ("BYE", "NORESULT"):
        return False
    
    # If summary exists and doesn't indicate invalid match, consider it valid
    # Empty matches array or matches with only invalid entries will result in zero valid matches
    return True


def count_valid_matches(matches: List[Dict]) -> int:
    """Count valid matches (excluding BYE, NoResult, etc.)."""
    if not matches:
        return 0
    
    valid_count = 0
    for match in matches:
        if is_valid_match(match):
            valid_count += 1
    
    return valid_count


def load_boys_rosters(data_dir: Path) -> Dict[str, Dict]:
    """
    Load all boys team rosters.
    
    Returns:
        Dictionary mapping team_name -> {
            "wrestlers": {
                wrestler_id: {
                    "name": str,
                    "team": str,
                    "matches": List[Dict]
                }
            }
        }
    """
    boys_rosters = {}
    
    if not data_dir.exists():
        print(f"Warning: Boys data directory not found: {data_dir}")
        return boys_rosters
    
    team_files = sorted(data_dir.glob("*.json"))
    print(f"Loading {len(team_files)} boys team files...")
    
    for team_file in team_files:
        try:
            with team_file.open("r", encoding="utf-8") as f:
                team_data = json.load(f)
        except Exception as e:
            print(f"  Warning: Error loading {team_file.name}: {e}")
            continue
        
        team_name = team_data.get("team_name", "")
        if not team_name:
            continue
        
        wrestlers = {}
        for wrestler in team_data.get("roster", []):
            wrestler_id = wrestler.get("season_wrestler_id")
            name = wrestler.get("name", "")
            matches = wrestler.get("matches", [])
            
            if not wrestler_id or not name:
                continue
            
            wrestlers[wrestler_id] = {
                "name": name,
                "team": team_name,
                "matches": matches,
            }
        
        if wrestlers:
            boys_rosters[team_name] = {
                "wrestlers": wrestlers
            }
    
    total_wrestlers = sum(len(r["wrestlers"]) for r in boys_rosters.values())
    print(f"  Loaded {total_wrestlers} boys wrestlers from {len(boys_rosters)} teams")
    
    return boys_rosters


def load_girls_rosters(data_dir: Path) -> Set[Tuple[str, str]]:
    """
    Load all girls team rosters and create normalized name+team lookup.
    
    Returns:
        Set of (normalized_name, normalized_team) tuples
    """
    girls_lookup = set()
    
    if not data_dir.exists():
        print(f"Warning: Girls data directory not found: {data_dir}")
        return girls_lookup
    
    team_files = sorted(data_dir.glob("*.json"))
    print(f"Loading {len(team_files)} girls team files...")
    
    for team_file in team_files:
        try:
            with team_file.open("r", encoding="utf-8") as f:
                team_data = json.load(f)
        except Exception as e:
            print(f"  Warning: Error loading {team_file.name}: {e}")
            continue
        
        team_name = team_data.get("team_name", "")
        if not team_name:
            continue
        
        normalized_team = normalize_team_name(team_name)
        
        for wrestler in team_data.get("roster", []):
            name = wrestler.get("name", "")
            if not name:
                continue
            
            normalized_name = normalize_name(name)
            if normalized_name and normalized_team:
                girls_lookup.add((normalized_name, normalized_team))
    
    print(f"  Loaded {len(girls_lookup)} unique girls wrestlers from {len(team_files)} teams")
    
    return girls_lookup


def generate_mask(
    season: int,
    boys_rosters: Dict[str, Dict],
    girls_lookup: Set[Tuple[str, str]]
) -> List[Dict]:
    """
    Generate list of masked wrestlers.
    
    Returns:
        List of dicts with masked wrestler info
    """
    masked_wrestlers = []
    
    print("\nAnalyzing wrestlers for masking...")
    
    for team_name, team_data in boys_rosters.items():
        for wrestler_id, wrestler_info in team_data["wrestlers"].items():
            name = wrestler_info["name"]
            team = wrestler_info["team"]
            matches = wrestler_info["matches"]
            
            # Check if wrestler has zero valid matches
            valid_match_count = count_valid_matches(matches)
            if valid_match_count > 0:
                continue  # Has matches, not a candidate
            
            # Normalize name and team for matching
            normalized_name = normalize_name(name)
            normalized_team = normalize_team_name(team)
            
            if not normalized_name or not normalized_team:
                continue
            
            # Check if matching wrestler exists on girls roster
            if (normalized_name, normalized_team) in girls_lookup:
                masked_wrestlers.append({
                    "boys_wrestler_id": wrestler_id,
                    "name": name,
                    "team": team,
                    "reason": "on girls roster; 0 boys matches"
                })
    
    print(f"  Found {len(masked_wrestlers)} wrestlers to mask")
    
    return masked_wrestlers


def main() -> None:
    args = parse_args()
    season = args.season
    state = args.state
    
    # Setup paths
    if args.boys_data_dir:
        boys_data_dir = Path(args.boys_data_dir)
    else:
        boys_data_dir = Path(f"mt/data/hs_{state.lower()}_boys") / str(season)
    
    if args.girls_data_dir:
        girls_data_dir = Path(args.girls_data_dir)
    else:
        girls_data_dir = Path(f"mt/data/hs_{state.lower()}_girls") / str(season)
    
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = Path(f"mt/rankings_data/hs_{state.lower()}_boys") / str(season)
    
    output_file = output_dir / "boys_inactive_wrestlers.json"
    
    print("=" * 80)
    print(f"Generating boys inactive wrestlers mask for season {season}")
    print("=" * 80)
    print(f"Boys data: {boys_data_dir}")
    print(f"Girls data: {girls_data_dir}")
    print(f"Output: {output_file}")
    print()
    
    # Load rosters
    boys_rosters = load_boys_rosters(boys_data_dir)
    girls_lookup = load_girls_rosters(girls_data_dir)
    
    if not boys_rosters:
        print("Error: No boys rosters loaded. Exiting.")
        return
    
    if not girls_lookup:
        print("Warning: No girls rosters loaded. No wrestlers will be masked.")
    
    # Generate mask
    masked_wrestlers = generate_mask(season, boys_rosters, girls_lookup)
    
    # Create output structure
    mask_data = {
        "season": season,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "masked_wrestlers": masked_wrestlers
    }
    
    # Write output file
    output_dir.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(mask_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Mask file generated: {output_file}")
    print(f"  Masked {len(masked_wrestlers)} wrestlers")
    
    # Print summary by team
    if masked_wrestlers:
        print("\nMasked wrestlers by team:")
        by_team = defaultdict(list)
        for w in masked_wrestlers:
            by_team[w["team"]].append(w["name"])
        
        for team in sorted(by_team.keys()):
            wrestlers = by_team[team]
            print(f"  {team}: {len(wrestlers)} wrestler(s)")
            for name in sorted(wrestlers):
                print(f"    - {name}")


if __name__ == "__main__":
    main()

