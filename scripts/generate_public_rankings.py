#!/usr/bin/env python3
"""
generate_public_rankings.py — Public Traditional Rankings Generator

This script generates public-facing traditional rankings JSON files for WrestleData.
It is a post-processing step ONLY. It does not compute rankings, Mat Value, or any metrics.

It transforms already-computed data into a format optimized for the "Rankings (Traditional)" page.

This script exists to:
- Separate analytics from presentation
- Lock public rankings to a stable contract
- Avoid UI code touching analytic internals
- Ensure ONE source of truth for rankings

No math. No logic. No interpretation.
"""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


def parse_record(record_str: str) -> Optional[Dict[str, int]]:
    """
    Parse record string like "6-0" or "12-2" into wins/losses.
    
    Returns: {"wins": int, "losses": int} or None if invalid
    """
    if not record_str:
        return None
    
    match = re.match(r'(\d+)-(\d+)', str(record_str))
    if not match:
        return None
    
    wins = int(match.group(1))
    losses = int(match.group(2))
    
    return {
        "wins": wins,
        "losses": losses,
        "pct": wins / (wins + losses) if (wins + losses) > 0 else 0.0
    }


def format_record_str(wins: int, losses: int) -> str:
    """
    Format wins/losses into display string like "12-1 (92%)".
    """
    total = wins + losses
    if total == 0:
        return "0-0 (—)"
    
    pct = (wins / total) * 100
    return f"{wins}-{losses} ({pct:.0f}%)"


def load_rankings_starters(season: int, weight: int, rankings_dir: str) -> Optional[List[Dict]]:
    """
    Load starter-only rankings JSON.
    
    Args:
        season: Season year
        weight: Weight class
        rankings_dir: Base directory for rankings data
    
    Returns:
        List of wrestler dicts from rankings file, or None if not found
    """
    rankings_path = Path(rankings_dir) / str(season) / f"rankings_starters_{weight}.json"
    
    if not rankings_path.exists():
        return None
    
    try:
        with rankings_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("rankings", [])
    except Exception as e:
        print(f"Error loading rankings file {rankings_path}: {e}")
        return None


def load_wrestler_profile(wrestler_id: str, season: int, wrestlers_dir: str) -> Optional[Dict]:
    """
    Load wrestler profile JSON.
    
    Args:
        wrestler_id: Wrestler ID
        season: Season year
        wrestlers_dir: Base directory for wrestler profiles
    
    Returns:
        Wrestler profile dict or None if not found
    """
    profile_path = Path(wrestlers_dir) / str(season) / "by_id" / f"{wrestler_id}.json"
    
    if not profile_path.exists():
        return None
    
    try:
        with profile_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading wrestler profile {profile_path}: {e}")
        return None


def load_team_abbreviation(team_slug: str, teams_dir: str) -> Optional[str]:
    """
    Load team abbreviation from team JSON file.
    
    Args:
        team_slug: Team slug (e.g., "penn_state")
        teams_dir: Base directory for team files
    
    Returns:
        Team abbreviation (e.g., "PSU") or None if not found
    """
    team_path = Path(teams_dir) / f"{team_slug}.json"
    
    if not team_path.exists():
        return None
    
    try:
        with team_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("abbreviation")
    except Exception:
        return None


def extract_wrestler_data(
    ranking_entry: Dict,
    profile: Optional[Dict],
    team_abbreviation: Optional[str]
) -> Dict:
    """
    Extract and format wrestler data from ranking entry and profile.
    
    Args:
        ranking_entry: Entry from rankings_starters JSON
        profile: Wrestler profile JSON (may be None)
        team_abbreviation: Team abbreviation (may be None)
    
    Returns:
        Formatted wrestler dict for output JSON
    """
    wrestler_id = ranking_entry.get("wrestler_id", "")
    name = ranking_entry.get("name", "")
    team = ranking_entry.get("team", "")
    rank = ranking_entry.get("rank", 0)
    
    # Extract record from profile (preferred) or ranking entry
    record_data = None
    record_str = None
    
    if profile and "record" in profile:
        record_overall = profile["record"].get("overall")
        if record_overall:
            record_data = parse_record(record_overall)
            if record_data:
                record_str = format_record_str(
                    record_data["wins"],
                    record_data["losses"]
                )
    
    # Fallback to ranking entry record
    if not record_data:
        ranking_record = ranking_entry.get("record")
        if ranking_record:
            record_data = parse_record(ranking_record)
            if record_data:
                record_str = format_record_str(
                    record_data["wins"],
                    record_data["losses"]
                )
    
    # Extract bonus rate from profile
    bonus_pct = None
    if profile and "metrics" in profile:
        bonus_rate = profile["metrics"].get("bonus_rate")
        if bonus_rate is not None:
            # Already 0-1, keep as is
            bonus_pct = float(bonus_rate)
    
    # Extract MV value and weight rank from profile
    mv_value = None
    mv_weight_rank = None
    
    if profile and "metrics" in profile:
        mat_value = profile["metrics"].get("mat_value")
        if mat_value:
            mv_value = mat_value.get("mv_avg")
            mv_weight_rank = mat_value.get("rank_weight")
    
    # Build output object
    output = {
        "rank": rank,
        "wrestler_id": wrestler_id,
        "name": name,
        "team": team,
    }
    
    if team_abbreviation:
        output["team_short"] = team_abbreviation
    
    if record_data:
        output["record"] = record_data
        if record_str:
            output["record_str"] = record_str
    else:
        output["record"] = None
        output["record_str"] = None
    
    if bonus_pct is not None:
        output["bonus_pct"] = bonus_pct
    else:
        output["bonus_pct"] = None
    
    if mv_value is not None:
        output["mv"] = {
            "value": mv_value,
            "weight_rank": mv_weight_rank
        }
    else:
        output["mv"] = None
    
    return output


def generate_public_rankings(
    season: int,
    weight: int,
    rankings_dir: str,
    wrestlers_dir: str,
    teams_dir: str,
    output_dir: str
) -> bool:
    """
    Generate public rankings JSON for a single weight class.
    
    Args:
        season: Season year
        weight: Weight class
        rankings_dir: Base directory for rankings data
        wrestlers_dir: Base directory for wrestler profiles
        teams_dir: Base directory for team files
        output_dir: Base directory for output files
    
    Returns:
        True if successful, False otherwise
    """
    # Load starter rankings (authoritative order)
    rankings = load_rankings_starters(season, weight, rankings_dir)
    
    if not rankings:
        print(f"Warning: No rankings found for {season} {weight} lbs")
        return False
    
    # Build output wrestlers list
    output_wrestlers = []
    
    for ranking_entry in rankings:
        wrestler_id = ranking_entry.get("wrestler_id")
        if not wrestler_id:
            continue
        
        # Load wrestler profile
        profile = load_wrestler_profile(wrestler_id, season, wrestlers_dir)
        
        # Get team slug from profile or ranking entry
        team_slug = None
        if profile:
            team_slug = profile.get("team_slug")
        elif ranking_entry.get("team"):
            # Fallback: try to derive slug from team name
            team_name = ranking_entry.get("team", "").lower().replace(" ", "_")
            team_slug = team_name
        
        # Load team abbreviation
        team_abbreviation = None
        if team_slug:
            team_abbreviation = load_team_abbreviation(team_slug, teams_dir)
        
        # Extract and format data
        wrestler_data = extract_wrestler_data(ranking_entry, profile, team_abbreviation)
        output_wrestlers.append(wrestler_data)
    
    # Build output JSON
    output_data = {
        "season": season,
        "weight": weight,
        "generated_at": datetime.now(timezone.utc).isoformat() + "Z",
        "source": f"rankings_starters_{weight}.json",
        "wrestlers": output_wrestlers
    }
    
    # Write output file
    output_path = Path(output_dir) / str(season) / f"{weight}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"✓ Generated {output_path} ({len(output_wrestlers)} wrestlers)")
        return True
    except Exception as e:
        print(f"Error writing output file {output_path}: {e}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate public traditional rankings JSON files"
    )
    parser.add_argument(
        "--season",
        type=int,
        required=True,
        help="Season year (e.g., 2026)"
    )
    parser.add_argument(
        "--rankings-dir",
        type=str,
        default="mt/rankings_data",
        help="Base directory for rankings data (default: mt/rankings_data)"
    )
    parser.add_argument(
        "--wrestlers-dir",
        type=str,
        default="mt/wrestlers",
        help="Base directory for wrestler profiles (default: mt/wrestlers)"
    )
    parser.add_argument(
        "--teams-dir",
        type=str,
        default="mt/teams",
        help="Base directory for team files (default: mt/teams)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="frontend/wrestledata-ui/public/data/public_rankings",
        help="Base directory for output files (default: frontend/wrestledata-ui/public/data/public_rankings)"
    )
    parser.add_argument(
        "--weight",
        type=int,
        help="Single weight class to process (if not provided, processes all weights)"
    )
    
    args = parser.parse_args()
    
    # Determine weights to process
    if args.weight:
        weights = [args.weight]
    else:
        # Find all weights from rankings_starters files
        rankings_path = Path(args.rankings_dir) / str(args.season)
        weights = []
        
        for file_path in rankings_path.glob("rankings_starters_*.json"):
            weight_str = file_path.stem.replace("rankings_starters_", "")
            try:
                weight = int(weight_str)
                weights.append(weight)
            except ValueError:
                continue
        
        weights.sort()
    
    if not weights:
        print(f"No weights found for season {args.season}")
        return
    
    print(f"Generating public rankings for season {args.season}")
    print(f"Weights: {weights}")
    print()
    
    # Process each weight
    success_count = 0
    for weight in weights:
        success = generate_public_rankings(
            args.season,
            weight,
            args.rankings_dir,
            args.wrestlers_dir,
            args.teams_dir,
            args.output_dir
        )
        if success:
            success_count += 1
    
    print()
    print(f"Generated {success_count}/{len(weights)} weight classes")


if __name__ == "__main__":
    main()

