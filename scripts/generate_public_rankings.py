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


def load_rankings_starters(season: int, weight: int, rankings_dir: str, league: str = 'ncaa', state: str = None, gender: str = None) -> Optional[List[Dict]]:
    """
    Load starter-only rankings JSON.
    
    Args:
        season: Season year
        weight: Weight class
        rankings_dir: Base directory for rankings data
        league: League type ('ncaa' or 'hs')
        state: State code (for HS)
        gender: Gender ('boys' or 'girls' for HS)
    
    Returns:
        List of wrestler dicts from rankings file, or None if not found
    """
    if league == 'hs':
        # For HS, rankings_dir already includes gender (e.g., frontend/hs-ky-ui/public/data/rankings/boys)
        # Just add season and filename
        rankings_path = Path(rankings_dir) / str(season) / f"rankings_starters_{weight}.json"
    else:
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


def load_wrestler_profile(wrestler_id: str, season: int, wrestlers_dir: str, league: str = 'ncaa', gender: str = None) -> Optional[Dict]:
    """
    Load wrestler profile JSON.
    
    Args:
        wrestler_id: Wrestler ID
        season: Season year
        wrestlers_dir: Base directory for wrestler profiles
        league: League type ('ncaa' or 'hs')
        gender: Gender ('boys' or 'girls' for HS)
    
    Returns:
        Wrestler profile dict or None if not found
    """
    if league == 'hs':
        # For HS, wrestlers_dir already includes gender (e.g., frontend/hs-ky-ui/public/data/wrestlers/boys)
        # Just add season and by_id
        profile_path = Path(wrestlers_dir) / str(season) / "by_id" / f"{wrestler_id}.json"
    else:
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


def copy_full_rankings_to_public(
    season: int,
    league: str = 'ncaa',
    state: str = None,
    gender: str = None
) -> None:
    """
    Copy full rankings files from mt/rankings_data to public location.
    
    This ensures the frontend has access to ALL ranked wrestlers (not just starters or top 40/24).
    Source: mt/rankings_data/hs_ky_{gender}/{season}/rankings_{weight}.json
    Destination: frontend/hs-ky-ui/public/data/rankings_full/{gender}/{season}/{weight}.json
    """
    if league != 'hs':
        # Only needed for HS (NCAA can use existing public rankings)
        return
    
    # Source directory
    state_lower = state.lower() if state else 'ky'
    source_dir = Path("mt/rankings_data") / f"hs_{state_lower}_{gender}" / str(season)
    
    if not source_dir.exists():
        print(f"Warning: Source directory not found: {source_dir}")
        print("Skipping full rankings copy.")
        return
    
    # Destination directory
    dest_dir = Path("frontend/hs-ky-ui/public/data/rankings_full") / gender / str(season)
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    # Determine weight classes
    if gender == 'boys':
        weights = [106, 113, 120, 126, 132, 138, 144, 150, 157, 165, 175, 190, 215, 285]
    else:  # girls
        weights = [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235]
    
    copied_count = 0
    
    for weight in weights:
        source_file = source_dir / f"rankings_{weight}.json"
        
        if not source_file.exists():
            continue
        
        try:
            # Read and validate the file
            with source_file.open('r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Ensure it has the expected structure
            if 'rankings' not in data:
                continue
            
            rankings = data.get('rankings', [])
            
            # Copy to destination (simplified format for frontend)
            dest_file = dest_dir / f"{weight}.json"
            
            # Write simplified format (just rankings array, not full metadata)
            output_data = {
                "season": season,
                "weight": weight,
                "rankings": rankings
            }
            
            with dest_file.open('w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            
            copied_count += 1
            print(f"  ✓ Copied full rankings for {weight} lbs ({len(rankings)} wrestlers)")
            
        except Exception as e:
            print(f"  ✗ Error copying {weight}.json: {e}")
            continue
    
    if copied_count > 0:
        print(f"\n✓ Copied {copied_count} full rankings file(s) to {dest_dir}")
    else:
        print(f"\n⚠ No full rankings files found to copy")


def generate_public_rankings(
    season: int,
    weight: int,
    rankings_dir: str,
    wrestlers_dir: str,
    teams_dir: str,
    output_dir: str,
    league: str = 'ncaa',
    state: str = None,
    gender: str = None
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
    rankings = load_rankings_starters(season, weight, rankings_dir, league=league, state=state, gender=gender)
    
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
        profile = load_wrestler_profile(wrestler_id, season, wrestlers_dir, league=league, gender=gender)
        
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
    if league == 'hs':
        # For HS, output_dir already includes gender (e.g., frontend/hs-ky-ui/public/data/public_rankings/boys)
        # Just add season and filename
        output_path = Path(output_dir) / str(season) / f"{weight}.json"
    else:
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
        default="frontend/wrestledata-ui/public/data/rankings",
        help="Base directory for rankings data (default: frontend/wrestledata-ui/public/data/rankings)"
    )
    parser.add_argument(
        "--wrestlers-dir",
        type=str,
        default="frontend/wrestledata-ui/public/data/wrestlers",
        help="Base directory for wrestler profiles (default: frontend/wrestledata-ui/public/data/wrestlers)"
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
            print(f"Generating public rankings for season {args.season} ({args.league.upper()} {args.state} {gender})...")
            print(f"{'=' * 80}\n")
            
            if gender == 'boys':
                default_weights = [106, 113, 120, 126, 132, 138, 144, 150, 157, 165, 175, 190, 215, 285]
            else:
                default_weights = [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235]
            
            # Setup HS-specific paths (use defaults unless explicitly overridden)
            # Check if user explicitly provided these args by comparing to defaults
            if args.rankings_dir != "frontend/wrestledata-ui/public/data/rankings":
                rankings_dir = Path(args.rankings_dir)
            else:
                rankings_dir = Path("frontend/hs-ky-ui/public/data/rankings") / gender
            
            if args.wrestlers_dir != "frontend/wrestledata-ui/public/data/wrestlers":
                wrestlers_dir = Path(args.wrestlers_dir)
            else:
                wrestlers_dir = Path("frontend/hs-ky-ui/public/data/wrestlers") / gender
            
            if args.teams_dir != "mt/teams":
                teams_dir = Path(args.teams_dir)
            else:
                teams_dir = Path("frontend/hs-ky-ui/public/data/teams") / gender / str(args.season)
            
            if args.output_dir != "frontend/wrestledata-ui/public/data/public_rankings":
                output_dir = Path(args.output_dir)
            else:
                output_dir = Path("frontend/hs-ky-ui/public/data/public_rankings") / gender
            
            # Determine weights to process
            if args.weight:
                weights = [args.weight]
            else:
                # Find all weights from rankings_starters files
                rankings_path = rankings_dir / str(args.season)
                weights = []
                
                if rankings_path.exists():
                    for file_path in rankings_path.glob("rankings_starters_*.json"):
                        weight_str = file_path.stem.replace("rankings_starters_", "")
                        try:
                            weight = int(weight_str)
                            weights.append(weight)
                        except ValueError:
                            continue
                
                if not weights:
                    weights = default_weights
                
                weights.sort()
            
            if not weights:
                print(f"No weights found for season {args.season}")
                continue
            
            print(f"Generating public rankings for season {args.season}")
            print(f"Weights: {weights}")
            print()
            
            # Copy full rankings files to public location FIRST
            print("Copying full rankings files to public location...")
            copy_full_rankings_to_public(
                args.season,
                league=args.league,
                state=args.state,
                gender=gender
            )
            print()
            
            # Process each weight
            success_count = 0
            for weight in weights:
                success = generate_public_rankings(
                    args.season,
                    weight,
                    str(rankings_dir),
                    str(wrestlers_dir),
                    str(teams_dir),
                    str(output_dir),
                    league=args.league,
                    state=args.state,
                    gender=gender
                )
                if success:
                    success_count += 1
            
            print()
            print(f"Generated {success_count}/{len(weights)} weight classes")
    else:  # ncaa
        # Determine weights to process
        if args.weight:
            weights = [args.weight]
        else:
            # Find all weights from rankings_starters files
            rankings_path = Path(args.rankings_dir) / str(args.season)
            weights = []
            
            if rankings_path.exists():
                for file_path in rankings_path.glob("rankings_starters_*.json"):
                    weight_str = file_path.stem.replace("rankings_starters_", "")
                    try:
                        weight = int(weight_str)
                        weights.append(weight)
                    except ValueError:
                        continue
            
            if not weights:
                weights = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]
            
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
                args.output_dir,
                league=args.league
            )
            if success:
                success_count += 1
        
        print()
        print(f"Generated {success_count}/{len(weights)} weight classes")


if __name__ == "__main__":
    main()

