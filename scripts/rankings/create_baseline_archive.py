#!/usr/bin/env python3
"""
create_baseline_archive.py

Creates official rankings archive drops from full rankings files (mt/rankings_data).

This script:
1. Loads full rankings from mt/rankings_data (source of truth)
2. Enriches with region data and region places
3. Limits to top 40 (boys) or top 24 (girls)
4. Removes TPAR/mv fields
5. Creates archive structure with meta.json, notes/, and index.json

CRITICAL: This script is READ-ONLY with respect to ranking order.
It NEVER modifies rankings order, filters beyond top-N limits, or infers editorial intent.
"""

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def load_team_region_mapping(gender: str) -> Dict[str, str]:
    """
    Load team to region mapping from teams.json file.
    
    Args:
        gender: Gender ('boys' or 'girls')
        
    Returns:
        Dictionary mapping team_name -> region number (as string)
    """
    teams_path = Path(f"data/team_lists/hs_ky_{gender}/teams.json")
    if not teams_path.exists():
        return {}
    
    mapping = {}
    with open(teams_path, 'r', encoding='utf-8') as f:
        teams = json.load(f)
        for team in teams:
            team_name = team.get('name', '')
            region = team.get('region')
            if team_name and region:
                mapping[team_name] = str(region)
    
    return mapping


def get_region_for_team(team_name: str, region_mapping: Dict[str, str]) -> str:
    """
    Get region number for a team.
    Returns region number as string, or "-" if not found.
    """
    return region_mapping.get(team_name, "-")


def parse_record(record_str: str) -> Optional[Dict]:
    """
    Parse record string (e.g., "7-0", "12-1") into structured format.
    
    Args:
        record_str: Record string like "7-0" or "12-1"
    
    Returns:
        Dictionary with wins, losses, pct, or None if invalid
    """
    if not record_str:
        return None
    
    # Try to parse "wins-losses" format
    match = re.match(r'^(\d+)-(\d+)$', str(record_str).strip())
    if match:
        wins = int(match.group(1))
        losses = int(match.group(2))
        total = wins + losses
        pct = (wins / total) * 100 if total > 0 else 0.0
        return {
            "wins": wins,
            "losses": losses,
            "pct": pct
        }
    
    return None


def format_record_str(wins: int, losses: int) -> str:
    """
    Format record as string with percentage.
    
    Args:
        wins: Number of wins
        losses: Number of losses
    
    Returns:
        Formatted string like "7-0 (100%)"
    """
    total = wins + losses
    if total == 0:
        return "0-0 (—)"
    
    pct = (wins / total) * 100
    return f"{wins}-{losses} ({pct:.0f}%)"


def load_wrestler_profile(wrestler_id: str, season: int, gender: str) -> Optional[Dict]:
    """
    Load wrestler profile JSON.
    
    Args:
        wrestler_id: Wrestler ID
        season: Season year
        gender: Gender ('boys' or 'girls')
    
    Returns:
        Wrestler profile dict or None if not found
    """
    profile_path = Path(f"frontend/hs-ky-ui/public/data/wrestlers/{gender}") / str(season) / "by_id" / f"{wrestler_id}.json"
    
    if not profile_path.exists():
        return None
    
    try:
        with profile_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def format_grade_display(grade) -> str:
    """
    Format grade for display: Sr., Jr., So., Fr., 8th, 7th.
    """
    if grade is None:
        return ""
    if isinstance(grade, str):
        return grade.strip() if grade.strip() else ""
    if isinstance(grade, int):
        mapping = {7: "7th", 8: "8th", 9: "Fr.", 10: "So.", 11: "Jr.", 12: "Sr."}
        return mapping.get(grade, "")
    return ""


def load_grade_lookup(season: int, gender: str) -> Dict[str, str]:
    """
    Load grade lookup from team profiles (starters + remaining), with fallback to
    weight_class JSON files in mt/rankings_data (which have grade for girls when
    team profiles do not).
    """
    grade_lookup: Dict[str, str] = {}
    
    # Primary: team profiles (works for boys; girls often have grade: null)
    teams_dir = Path(f"frontend/hs-ky-ui/public/data/teams/{gender}") / str(season)
    if teams_dir.exists():
        for team_file in teams_dir.glob("*.json"):
            try:
                with team_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                for slot in data.get("starters", {}).values():
                    wid = slot.get("wrestler_id")
                    grade = slot.get("grade")
                    if wid:
                        disp = format_grade_display(grade)
                        if disp and wid not in grade_lookup:
                            grade_lookup[wid] = disp
                for entry in data.get("remaining", []):
                    wid = entry.get("wrestler_id")
                    grade = entry.get("grade")
                    if wid:
                        disp = format_grade_display(grade)
                        if disp and wid not in grade_lookup:
                            grade_lookup[wid] = disp
            except Exception:
                continue
    
    # Fallback: weight_class files in mt/rankings_data (has grade for girls)
    wc_dir = Path(f"mt/rankings_data/hs_ky_{gender}") / str(season)
    if wc_dir.exists():
        for wc_file in wc_dir.glob("weight_class_*.json"):
            try:
                with wc_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                for wid, wdata in data.get("wrestlers", {}).items():
                    if wid and wid not in grade_lookup:
                        grade = wdata.get("grade")
                        if grade and isinstance(grade, str) and grade.strip():
                            grade_lookup[wid] = grade.strip()
                        else:
                            disp = format_grade_display(grade)
                            if disp:
                                grade_lookup[wid] = disp
            except Exception:
                continue
    
    return grade_lookup


def load_placement_notes(season: int, gender: str) -> Dict[str, str]:
    """
    Load placement notes and return wrestler_id -> note mapping.
    
    Args:
        season: Season year
        gender: Gender ('boys' or 'girls')
    
    Returns:
        Dictionary mapping wrestler_id -> placement note (e.g., "1", "3", "BR", "Q")
    """
    notes_path = Path("mt/rankings_data") / f"hs_ky_{gender}" / str(season) / "placement_notes.json"
    
    if not notes_path.exists():
        return {}
    
    try:
        with notes_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        
        lookup = {}
        for entry in data.get("notes", []):
            wid = entry.get("wrestler_id")
            note = str(entry.get("note", "")).strip().upper()
            if wid and note:
                lookup[wid] = note
        
        return lookup
    except Exception:
        return {}


def calculate_region_places(
    top_wrestlers: List[Dict],
    region_mapping: Dict[str, str],
    team_best_wrestler: Dict[str, str],
    gender: str = 'boys'
) -> Dict[str, str]:
    """
    Calculate region place (1-4) for each wrestler based on their rank within their region.
    
    Rules:
    - Only assign region place to highest ranked wrestler per team
    - Within each region, rank wrestlers by their current ranking
    - Assign region place 1-4 based on rank within region (top 4 per region)
    - Non-starters ALWAYS get "N/A"
    
    Args:
        top_wrestlers: List of wrestler entries (top 40 for boys, top 24 for girls)
        region_mapping: Dictionary mapping team_name -> region number
        team_best_wrestler: Dictionary mapping team -> wrestler_id of highest ranked wrestler
        gender: 'boys' or 'girls'
        
    Returns:
        Dictionary mapping wrestler_id -> region_place ("1", "2", "3", "4", or "N/A")
    """
    region_places = {}
    
    # Group wrestlers by region (only starters)
    wrestlers_by_region = defaultdict(list)  # region -> list of (rank, wrestler_entry)
    
    for entry in top_wrestlers:
        wid = entry.get('wrestler_id', '')
        team = entry.get('team', '')
        rank = entry.get('rank', 9999)
        
        # Only consider highest ranked wrestler per team
        if team_best_wrestler.get(team) != wid:
            region_places[wid] = "N/A"
            continue
        
        # Get region for this team
        region = get_region_for_team(team, region_mapping)
        if not region or region == "-":
            region_places[wid] = "N/A"
            continue
        
        wrestlers_by_region[region].append((rank, entry))
    
    # For each region, sort by rank and assign places 1-4
    for region, wrestler_list in wrestlers_by_region.items():
        # Sort by rank (ascending - lower rank number = better)
        wrestler_list.sort(key=lambda x: x[0])
        
        # Assign region places 1-4
        for place_idx, (rank, entry) in enumerate(wrestler_list[:4], start=1):
            wid = entry.get('wrestler_id', '')
            region_places[wid] = str(place_idx)
        
        # Any wrestlers beyond 4th in region get N/A
        for rank, entry in wrestler_list[4:]:
            wid = entry.get('wrestler_id', '')
            region_places[wid] = "N/A"
    
    return region_places


def load_previous_drop_rankings(
    archive_base: Path,
    gender: str,
    season: int,
    weight: int,
    previous_drop_id: str
) -> Dict[str, int]:
    """
    Load previous drop's rankings and return mapping of wrestler_id -> previous_rank.
    
    Args:
        archive_base: Base directory for archive structure
        gender: 'boys' or 'girls'
        season: Season year
        weight: Weight class
        previous_drop_id: Previous drop identifier
    
    Returns:
        Dictionary mapping wrestler_id -> previous_rank (or empty dict if not found)
    """
    previous_file = archive_base / gender / str(season) / previous_drop_id / f"{weight}.json"
    
    if not previous_file.exists():
        return {}
    
    try:
        with previous_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        
        previous_rankings = {}
        for wrestler in data.get("wrestlers", []):
            wid = wrestler.get("wrestler_id")
            rank = wrestler.get("rank")
            if wid and rank:
                previous_rankings[wid] = rank
        
        return previous_rankings
    except Exception as e:
        print(f"Warning: Could not load previous drop rankings for {weight}: {e}")
        return {}


def enrich_rankings_with_region_data(
    rankings: List[Dict],
    region_mapping: Dict[str, str],
    gender: str,
    season: int,
    top_n: int,
    placement_notes: Optional[Dict[str, str]] = None,
    previous_rankings: Optional[Dict[str, int]] = None,
    grade_lookup: Optional[Dict[str, str]] = None
) -> Tuple[List[Dict], Dict[str, str], Dict[str, str]]:
    """
    Enrich rankings with region data, region places, and is_highest_ranked flags.
    
    Args:
        rankings: Full list of ranked wrestlers (preserves exact order)
        region_mapping: Dictionary mapping team_name -> region number
        gender: 'boys' or 'girls'
        top_n: Maximum number of wrestlers to include (40 for boys, 24 for girls)
    
    Returns:
        Tuple of (enriched_rankings, region_places, team_best_wrestler)
    """
    # Limit to top N (preserves order)
    top_wrestlers = rankings[:top_n]
    
    # Determine highest ranked wrestler per team at this weight
    team_best_wrestler = {}  # team -> wrestler_id
    
    for entry in top_wrestlers:
        team = entry.get('team', '')
        rank = entry.get('rank', 9999)
        wid = entry.get('wrestler_id')
        
        if not team or not wid:
            continue
        
        if team not in team_best_wrestler:
            team_best_wrestler[team] = wid
        else:
            # Check if this wrestler is better ranked
            existing_wid = team_best_wrestler[team]
            existing_entry = next((e for e in top_wrestlers if e.get('wrestler_id') == existing_wid), None)
            if existing_entry and rank < existing_entry.get('rank', 9999):
                team_best_wrestler[team] = wid
    
    # Calculate region places
    region_places = calculate_region_places(top_wrestlers, region_mapping, team_best_wrestler, gender)
    
    # Enrich each wrestler entry
    enriched_rankings = []
    for entry in top_wrestlers:
        wid = entry.get('wrestler_id', '')
        team = entry.get('team', '')
        
        # Load wrestler profile for record and bonus_pct
        profile = load_wrestler_profile(wid, season, gender)
        
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
            ranking_record = entry.get("record")
            if ranking_record:
                record_data = parse_record(str(ranking_record))
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
                bonus_pct = float(bonus_rate)
        
        # Create enriched entry
        enriched_entry = {
            "rank": entry.get("rank"),
            "wrestler_id": entry.get("wrestler_id"),
            "name": entry.get("name"),
            "team": entry.get("team"),
            "region": get_region_for_team(team, region_mapping),
            "region_place": region_places.get(wid, "N/A"),
            "is_highest_ranked": team_best_wrestler.get(team) == wid,
        }
        
        # Add record data
        if record_data:
            enriched_entry["record"] = record_data
            if record_str:
                enriched_entry["record_str"] = record_str
        else:
            enriched_entry["record"] = None
            enriched_entry["record_str"] = None
        
        # Add bonus_pct
        if bonus_pct is not None:
            enriched_entry["bonus_pct"] = bonus_pct
        else:
            enriched_entry["bonus_pct"] = None
        
        # Preserve is_starter if present (for compatibility)
        if "is_starter" in entry:
            enriched_entry["is_starter"] = entry["is_starter"]
        
        # Add grade (Sr., Jr., So., Fr., 8th, 7th)
        enriched_entry["grade"] = (grade_lookup or {}).get(wid, "") or ""
        
        # Add placement note if available
        if placement_notes:
            placement_note = placement_notes.get(wid)
            if placement_note:
                enriched_entry["placement_note"] = placement_note
        
        # Add previous rank and movement if previous rankings available
        if previous_rankings:
            previous_rank = previous_rankings.get(wid)
            current_rank = enriched_entry.get("rank")
            
            if previous_rank is not None and current_rank is not None:
                # Wrestler was in previous rankings - calculate movement
                enriched_entry["previous_rank"] = previous_rank
                movement = previous_rank - current_rank  # Positive = moved up, Negative = moved down
                enriched_entry["movement"] = movement
                enriched_entry["is_new"] = False
            else:
                # Wrestler not in previous rankings (new entry or moved from different weight)
                enriched_entry["previous_rank"] = None
                enriched_entry["movement"] = None
                enriched_entry["is_new"] = True
        else:
            # No previous rankings available (baseline drop)
            enriched_entry["is_new"] = False
        
        # DO NOT include: mv, tpar, mat_value, or any TPAR-related fields
        # These are removed from the archive output
        
        enriched_rankings.append(enriched_entry)
    
    return enriched_rankings, region_places, team_best_wrestler


def create_baseline_archive(
    season: int,
    gender: str,
    drop_id: str,
    archive_base: Path = Path("frontend/hs-ky-ui/public/data/rankings"),
    force: bool = False
) -> None:
    """
    Create baseline archive from full rankings files with region enrichment.
    
    Args:
        season: Season year (e.g., 2026)
        gender: 'boys' or 'girls'
        drop_id: Drop identifier (e.g., '2026-01-02')
        archive_base: Base directory for archive structure
        force: If True, proceed even if rankings files appear stale
    """
    # Construct archive paths
    archive_dir = archive_base / gender / str(season) / drop_id
    archive_dir.mkdir(parents=True, exist_ok=True)
    
    # Determine weight classes and top-N limit based on gender
    if gender == 'boys':
        weights = [106, 113, 120, 126, 132, 138, 144, 150, 157, 165, 175, 190, 215, 285]
        top_n = 40
    else:  # girls
        weights = [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235]
        top_n = 24
    
    # Load region mapping
    region_mapping = load_team_region_mapping(gender)
    if not region_mapping:
        print(f"Warning: No region mapping found for {gender}")
        print(f"  Expected file: data/team_lists/hs_ky_{gender}/teams.json")
        if not force:
            print("  Use --force to proceed anyway")
            raise ValueError("Region mapping required for archive creation")
    else:
        print(f"Loaded region mapping for {len(region_mapping)} teams")
    
    # Load placement notes
    placement_notes = load_placement_notes(season, gender)
    if placement_notes:
        print(f"Loaded {len(placement_notes)} placement notes")
    else:
        print("No placement notes found (this is okay)")
    
    # Load grade lookup from team profiles
    grade_lookup = load_grade_lookup(season, gender)
    
    # Determine if this is a baseline drop and find previous drop
    index_dir = archive_base / gender / str(season)
    index_file = index_dir / "index.json"
    is_baseline = True
    previous_drop_id = None
    
    if index_file.exists():
        try:
            with index_file.open("r", encoding="utf-8") as f:
                index_data = json.load(f)
            
            # Check if this drop already exists (updating existing)
            existing_drops = [d for d in index_data.get("drops", []) if d.get("id") != drop_id]
            
            if existing_drops:
                # Not baseline - find most recent previous drop
                is_baseline = False
                # Drops are sorted by published_at (newest first)
                previous_drop_id = existing_drops[0].get("id")
                print(f"Previous drop found: {previous_drop_id}")
            else:
                print("This is the first drop (baseline)")
        except Exception as e:
            print(f"Warning: Could not read index.json: {e}")
            print("Treating as baseline drop")
    
    # Setup source directory
    source_dir = Path(f"mt/rankings_data/hs_ky_{gender}") / str(season)
    if not source_dir.exists():
        raise ValueError(f"Source directory not found: {source_dir}")
    
    # Check file freshness (warn but don't block)
    from datetime import datetime, timedelta
    now = datetime.now()
    stale_threshold = timedelta(days=7)
    stale_files = []
    
    # Process each weight class
    processed_files = []
    for weight in weights:
        source_file = source_dir / f"rankings_{weight}.json"
        if not source_file.exists():
            print(f"Warning: Source file not found: {source_file}")
            continue
        
        # Check freshness
        file_mtime = datetime.fromtimestamp(source_file.stat().st_mtime)
        age = now - file_mtime
        if age > stale_threshold:
            stale_files.append((weight, age.days))
        
        try:
            # Load rankings file
            with source_file.open("r", encoding="utf-8") as f:
                rankings_data = json.load(f)
            
            rankings = rankings_data.get('rankings', [])
            if not rankings:
                print(f"Warning: No rankings found in {source_file}")
                continue
            
            # Load previous drop rankings if not baseline
            previous_rankings = {}
            if not is_baseline and previous_drop_id:
                previous_rankings = load_previous_drop_rankings(
                    archive_base, gender, season, weight, previous_drop_id
                )
                if previous_rankings:
                    print(f"  Loaded previous rankings for {len(previous_rankings)} wrestlers")
            
            # Enrich with region data (and movement if previous rankings available)
            enriched_rankings, region_places, team_best_wrestler = enrich_rankings_with_region_data(
                rankings, region_mapping, gender, season, top_n, placement_notes,
                previous_rankings if previous_rankings else None,
                grade_lookup=grade_lookup
            )
            
            # Create output structure
            output_data = {
                "season": season,
                "weight": weight,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source": f"rankings_{weight}.json",
                "wrestlers": enriched_rankings
            }
            
            # Save to archive
            dest_file = archive_dir / f"{weight}.json"
            with dest_file.open("w", encoding="utf-8") as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            
            processed_files.append(str(weight))
            print(f"✓ Processed {weight}.json ({len(enriched_rankings)} wrestlers)")
            
        except Exception as e:
            print(f"Error processing {weight}.json: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    if not processed_files:
        raise ValueError(f"No ranking files processed from {source_dir}")
    
    # Warn about stale files
    if stale_files:
        print(f"\n⚠ Warning: {len(stale_files)} rankings file(s) appear stale:")
        for weight, days in stale_files:
            print(f"  {weight}.json: {days} days old")
        if not force:
            print("  Consider updating rankings before archiving")
    
    # Create meta.json
    meta = {
        "id": drop_id,
        "season": season,
        "gender": gender,
        "published_at": f"{drop_id}T00:00:00Z",
        "baseline": is_baseline
    }
    
    meta_file = archive_dir / "meta.json"
    with meta_file.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    print(f"✓ Created meta.json")
    
    # Create notes/ subdirectory with blank markdown files for each weight
    # Files are created blank by default and only shown if they have content
    notes_dir = archive_dir / "notes"
    notes_dir.mkdir(exist_ok=True)
    
    for weight in weights:
        notes_file = notes_dir / f"{weight}.md"
        if not notes_file.exists():
            # Create blank file - will only be displayed if user adds content
            with notes_file.open("w", encoding="utf-8") as f:
                f.write("")
    
    print(f"✓ Created notes/ subdirectory")
    
    # Create/update index.json
    index_dir = archive_base / gender / str(season)
    index_dir.mkdir(parents=True, exist_ok=True)
    index_file = index_dir / "index.json"
    
    if index_file.exists():
        with index_file.open("r", encoding="utf-8") as f:
            index_data = json.load(f)
    else:
        index_data = {
            "latest": drop_id,
            "drops": []
        }
    
    # Add this drop to the registry if not already present
    drop_exists = any(d["id"] == drop_id for d in index_data["drops"])
    if not drop_exists:
        index_data["drops"].append({
            "id": drop_id,
            "published_at": f"{drop_id}T00:00:00Z"
        })
        # Sort drops by published_at (newest first)
        index_data["drops"].sort(key=lambda x: x["published_at"], reverse=True)
        index_data["latest"] = drop_id
    
    with index_file.open("w", encoding="utf-8") as f:
        json.dump(index_data, f, indent=2)
    print(f"✓ Updated index.json")
    
    print(f"\n✓ Baseline archive created: {archive_dir}")
    print(f"  Processed {len(processed_files)} weight class files")
    print(f"  Top {top_n} wrestlers per weight class")


def main():
    parser = argparse.ArgumentParser(
        description="Create baseline rankings archive from full rankings files (mt/rankings_data)"
    )
    parser.add_argument(
        "-season",
        type=int,
        required=True,
        help="Season year (e.g., 2026)"
    )
    parser.add_argument(
        "-gender",
        choices=["boys", "girls"],
        required=True,
        help="Gender"
    )
    parser.add_argument(
        "-drop-id",
        type=str,
        required=True,
        help="Drop identifier (e.g., '2026-01-02')"
    )
    parser.add_argument(
        "-archive-base",
        type=str,
        default="frontend/hs-ky-ui/public/data/rankings",
        help="Base directory for archive structure (default: frontend/hs-ky-ui/public/data/rankings)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Proceed even if rankings files appear stale"
    )
    
    args = parser.parse_args()
    
    archive_base = Path(args.archive_base)
    
    print(f"Creating baseline archive for {args.gender} {args.season}...")
    print(f"Source: mt/rankings_data/hs_ky_{args.gender}/{args.season}/")
    print(f"Archive: {archive_base}/{args.gender}/{args.season}/{args.drop_id}/")
    print()
    
    create_baseline_archive(
        season=args.season,
        gender=args.gender,
        drop_id=args.drop_id,
        archive_base=archive_base,
        force=args.force
    )
    
    print("\n✓ Baseline archive creation complete!")


if __name__ == "__main__":
    main()
