import os
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

def strip_result(text):
    text = text.strip()
    if not text.endswith(")"):
        return text, ""
    index = len(text) - 1
    depth = 1
    while index > 0:
        index -= 1
        if text[index] == ")":
            depth += 1
        elif text[index] == "(":
            depth -= 1
            if depth == 0:
                result = text[index + 1:-1].strip()
                rest = text[:index].strip()
                return rest, result
    return text, ""

def parse_name_team(segment):
    segment = segment.strip()
    if not segment.endswith(")"):
        return segment or "Unknown", "Unknown"
    index = len(segment) - 1
    depth = 1
    while index > 0:
        index -= 1
        if segment[index] == ")":
            depth += 1
        elif segment[index] == "(":
            depth -= 1
            if depth == 0:
                team = segment[index + 1:-1].strip()
                name = segment[:index].strip()
                return name or "Unknown", team or "Unknown"
    return segment or "Unknown", "Unknown"

def clean_winner_name(raw):
    raw = raw.strip()
    if raw.endswith("-"):
        return "Unknown"
    parts = [p.strip() for p in raw.split(" - ") if p.strip()]
    return parts[-1] if parts else "Unknown"

def update_alias_file(canonical_name, variant_name, team_name, season):
    """Add a new entry to the alias file."""
    alias_file_path = "mt/name_alias.json"
    
    try:
        # Load the current alias file
        with open(alias_file_path, "r") as f:
            alias_data = json.load(f)
    except FileNotFoundError:
        # Create new structure if file doesn't exist
        alias_data = {"aliases": []}
    
    # Create the new alias entry
    new_alias = {
        "canonical_name": canonical_name,
        "name_variants": [variant_name],
        "conditions": {
            "season": season,
            "team": team_name
        },
        "notes": ""
    }
    
    # Add to aliases list
    alias_data["aliases"].append(new_alias)
    
    # Write back to file with nice formatting
    with open(alias_file_path, "w") as f:
        json.dump(alias_data, f, indent=2)
    
    print(f"✅ Added alias: {variant_name} → {canonical_name} for {team_name} in {season}")

def process_match(summary, wrestler_name, team_name=None, season=None):
    summary = summary.strip()
    
    # Check for aliases if team_name and season are provided
    current_variants = [wrestler_name]
    if team_name and season:
        # Load existing aliases
        alias_file_path = "mt/name_alias.json"
        try:
            with open(alias_file_path, "r") as f:
                alias_data = json.load(f)
                # Find variants for this wrestler/team/season
                for alias in alias_data.get("aliases", []):
                    if (alias.get("conditions", {}).get("team") == team_name and 
                        alias.get("conditions", {}).get("season") == season and
                        alias.get("canonical_name") == wrestler_name):
                        current_variants.extend(alias.get("name_variants", []))
        except FileNotFoundError:
            pass
    
    # Check if any variant of the name is in the summary
    name_found = False
    matching_alias = None
    for variant in current_variants:
        if variant in summary:
            name_found = True
            if variant != wrestler_name:
                matching_alias = variant
            break
    
    if not name_found:
        error_msg = f"❌ SCRAPER_ERROR: '{wrestler_name}' not found in match summary: '{summary}'"
        print(error_msg)
        
        # If team_name and season are provided, offer to update alias
        if team_name and season:
            add_alias = input("Would you like to add an alias for this wrestler? (y/n): ").strip().lower()
            if add_alias == 'y' or add_alias == 'yes':
                variant_name = input(f"Enter the variant name for '{wrestler_name}' in this match summary: ").strip()
                if variant_name:
                    update_alias_file(wrestler_name, variant_name, team_name, season)
        
        return {"result": "SCRAPER_ERROR"}
    
    # If match passed using an alias, print message
    if matching_alias:
        print(f"✅ Match passed using alias '{matching_alias}' for '{wrestler_name}': {summary}")
    
    if "received a bye" in summary.lower():
        lparen = summary.find("(")
        rparen = summary.find(")")
        if lparen != -1 and rparen != -1 and rparen > lparen:
            winner_team = summary[lparen + 1:rparen].strip()
        else:
            winner_team = "Unknown"
        return {
            "winner_name": wrestler_name,
            "winner_team": winner_team,
            "loser_name": "Unknown",
            "loser_team": "Unknown",
            "result": "BYE"
        }
    if " vs. " in summary:
        return {
            "winner_name": "Unknown",
            "winner_team": "Unknown",
            "loser_name": "Unknown",
            "loser_team": "Unknown",
            "result": "NoResult"
        }
    if " over " not in summary:
        return {"result": "PARSE_ERROR"}
    try:
        before, after = summary.split(" over ", 1)
        after, result = strip_result(after)
        loser_name, loser_team = parse_name_team(after)
        winner_raw, winner_team = parse_name_team(before)
        winner_name = clean_winner_name(winner_raw)
        return {
            "winner_name": winner_name,
            "winner_team": winner_team,
            "loser_name": loser_name,
            "loser_team": loser_team,
            "result": result or "Unknown"
        }
    except:
        return {"result": "PARSE_ERROR"}

def find_team_for_wrestler(wrestler_id: str, processed_dir: str) -> Optional[str]:
    """
    Find which team a wrestler belongs to by searching processed team files.
    
    Returns team filename (without .json extension) if found, None otherwise.
    """
    processed_path = Path(processed_dir)
    if not processed_path.exists():
        return None
    
    for team_file in processed_path.glob("*.json"):
        try:
            with open(team_file, 'r') as f:
                team_data = json.load(f)
            
            # Search through roster for this wrestler ID
            for wrestler in team_data.get("roster", []):
                if wrestler.get("season_wrestler_id") == wrestler_id:
                    return team_file.stem  # Return filename without .json extension
        except Exception:
            continue
    
    return None


def normalize_wrestlestat_result(result_type: str, score: Optional[str], duration: Optional[str]) -> str:
    """
    Normalize WrestleStat result to TrackWrestling format.
    
    Examples:
    - DEC with score "7-0" -> "Dec 7-0"
    - TF with score "15-0" and duration "4:02" -> "TF 15-0 4:02"
    - FALL with duration "2:49" -> "Fall 2:49"
    - MD with score "17-4" -> "MD 17-4"
    """
    # Map result types to TrackWrestling format
    result_map = {
        "DEC": "Dec",
        "MD": "MD",
        "TF": "TF",
        "FALL": "Fall",
        "SV-1": "SV-1",
        "INJ": "INJ",
        "TB-2": "TB-2",
        "FORFEIT": "FORFEIT"
    }
    
    normalized_type = result_map.get(result_type, result_type)
    
    # Build result string
    parts = [normalized_type]
    
    if score:
        parts.append(score)
    
    if duration and result_type in ("FALL", "TF", "INJ"):
        parts.append(duration)
    
    return " ".join(parts)


def normalize_wrestlestat_match(wrestlestat_match: Dict, dual_id: str, processed_dir: str) -> Optional[Dict]:
    """
    Normalize a WrestleStat match to TrackWrestling format.
    
    Returns normalized match dict with team names filled in, or None if invalid.
    """
    winner_id = wrestlestat_match.get("winner", {}).get("matsavant_id")
    loser_id = wrestlestat_match.get("loser", {}).get("matsavant_id")
    
    if not winner_id or not loser_id:
        return None
    
    winner_name = wrestlestat_match.get("winner", {}).get("name", "Unknown")
    loser_name = wrestlestat_match.get("loser", {}).get("name", "Unknown")
    
    # Get team names for winner and loser
    winner_team = get_team_name_by_id(winner_id, processed_dir) or "Unknown"
    loser_team = get_team_name_by_id(loser_id, processed_dir) or "Unknown"
    
    # Convert date from ISO format (YYYY-MM-DD) to MM/DD/YYYY format
    date_iso = wrestlestat_match.get("date", "")
    date_formatted = date_iso
    try:
        if date_iso and "-" in date_iso and len(date_iso.split("-")[0]) == 4:
            date_obj = datetime.strptime(date_iso, "%Y-%m-%d")
            date_formatted = date_obj.strftime("%m/%d/%Y")
    except Exception:
        pass
    
    weight = str(wrestlestat_match.get("weight_ranked", ""))
    result_type = wrestlestat_match.get("result", "")
    score = wrestlestat_match.get("score")
    duration = wrestlestat_match.get("duration")
    
    # Normalize result string
    result_str = normalize_wrestlestat_result(result_type, score, duration)
    
    # Build summary string (TrackWrestling format)
    summary = f"Varsity - {winner_name} ({winner_team}) over {loser_name} ({loser_team}) ({result_str})"
    
    return {
        "date": date_formatted,  # Converted to MM/DD/YYYY format
        "event": f"Dual Meet (WS-{dual_id})",
        "weight": weight,
        "summary": summary,
        "opponent_id": loser_id,  # For winner's perspective
        "winner_matsavant_id": winner_id,
        "loser_matsavant_id": loser_id,
        "winner_name": winner_name,
        "winner_team": winner_team,
        "loser_name": loser_name,
        "loser_team": loser_team,
        "result": result_str,
        "source": "wrestlestat"
    }


def load_wrestlestat_matches(season: str, processed_dir: str) -> List[Tuple[Dict, str]]:
    """
    Load all WrestleStat processed files and return list of (normalized_match, dual_id) tuples.
    
    Filters by season based on match dates.
    """
    wrestlestat_dir = Path("data/processed/wrestlestat")
    if not wrestlestat_dir.exists():
        return []
    
    matches = []
    season_start = int(season)
    
    for dual_file in wrestlestat_dir.glob("*.json"):
        try:
            with open(dual_file, 'r') as f:
                dual_data = json.load(f)
            
            dual_id = dual_data.get("dual_id", dual_file.stem)
            
            for match in dual_data.get("matches", []):
                # Check if match date is in the season window
                match_date = match.get("date", "")
                if match_date:
                    try:
                        # Parse ISO date (YYYY-MM-DD)
                        date_obj = datetime.strptime(match_date, "%Y-%m-%d")
                        match_year = date_obj.year
                        
                        # Check if match is in season (e.g., 2026 season = matches from 2025-2026 academic year)
                        # For simplicity, check if year matches season or season-1
                        if match_year != season_start and match_year != season_start - 1:
                            continue
                    except Exception:
                        # If date parsing fails, include the match anyway
                        pass
                
                normalized = normalize_wrestlestat_match(match, dual_id, processed_dir)
                if normalized:
                    matches.append((normalized, dual_id))
        except Exception as e:
            print(f"⚠️ Error loading WrestleStat file {dual_file}: {e}")
            continue
    
    return matches


def normalize_date_for_key(date_str: str) -> str:
    """
    Normalize date string to consistent format for duplicate detection.
    
    Converts ISO format (YYYY-MM-DD) to MM/DD/YYYY format to match TrackWrestling.
    """
    if not date_str:
        return ""
    
    try:
        # Try ISO format first (YYYY-MM-DD)
        if "-" in date_str and len(date_str.split("-")[0]) == 4:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            return date_obj.strftime("%m/%d/%Y")
        # Already in MM/DD/YYYY format
        return date_str
    except Exception:
        return date_str


def build_duplicate_key(date: str, weight: str, winner_id: str, loser_id: str) -> Tuple[str, str, str, str]:
    """
    Build duplicate detection key: (date, weight, winner_matsavant_id, loser_matsavant_id)
    
    Dates are normalized to MM/DD/YYYY format for consistency.
    """
    normalized_date = normalize_date_for_key(date)
    return (normalized_date, str(weight), str(winner_id), str(loser_id))


def get_wrestler_name_by_id(wrestler_id: str, processed_dir: str) -> Optional[str]:
    """
    Find wrestler name by searching processed team files.
    """
    processed_path = Path(processed_dir)
    if not processed_path.exists():
        return None
    
    for team_file in processed_path.glob("*.json"):
        try:
            with open(team_file, 'r') as f:
                team_data = json.load(f)
            
            for wrestler in team_data.get("roster", []):
                if wrestler.get("season_wrestler_id") == wrestler_id:
                    return wrestler.get("name", "Unknown")
        except Exception:
            continue
    
    return None


def get_team_name_by_id(wrestler_id: str, processed_dir: str) -> Optional[str]:
    """
    Find team name for a wrestler by searching processed team files.
    """
    processed_path = Path(processed_dir)
    if not processed_path.exists():
        return None
    
    for team_file in processed_path.glob("*.json"):
        try:
            with open(team_file, 'r') as f:
                team_data = json.load(f)
            
            for wrestler in team_data.get("roster", []):
                if wrestler.get("season_wrestler_id") == wrestler_id:
                    return team_data.get("team_name", "Unknown")
        except Exception:
            continue
    
    return None


def process_file(input_path, output_path, season, wrestlestat_matches_by_wrestler: Dict[str, List[Tuple[Dict, str]]], existing_match_keys: Set[Tuple[str, str, str, str]], added_wrestlestat_keys: Set[Tuple[str, str, str, str]]):
    """
    Process a team file and merge WrestleStat matches.
    
    Args:
        input_path: Path to input team file
        output_path: Path to output team file
        season: Season string
        wrestlestat_matches_by_wrestler: Dict mapping wrestler_id -> list of (match, dual_id) tuples
        existing_match_keys: Set of (date, weight, winner_id, loser_id) tuples for TrackWrestling duplicate detection
        added_wrestlestat_keys: Set of WrestleStat match keys already added (to prevent adding same match twice to same wrestler)
    """
    with open(input_path, "r") as f:
        data = json.load(f)

    scraper_errors = 0
    parse_errors = 0
    total_matches = 0
    team_name = data.get("team_name", "Unknown")
    
    # Track WrestleStat matches added for this team
    wrestlestat_added = 0
    wrestlestat_duplicates = 0
    
    # Load existing aliases
    alias_file_path = "mt/name_alias.json"
    try:
        with open(alias_file_path, "r") as f:
            alias_data = json.load(f)
    except FileNotFoundError:
        alias_data = {"aliases": []}
    
    # Create a mapping of canonical names to their variants for this team/season
    name_variants = {}
    for alias in alias_data.get("aliases", []):
        if (alias.get("conditions", {}).get("team") == team_name and 
            alias.get("conditions", {}).get("season") == season):
            canonical_name = alias.get("canonical_name")
            if canonical_name not in name_variants:
                name_variants[canonical_name] = []
            name_variants[canonical_name].extend(alias.get("name_variants", []))

    for wrestler in data.get("roster", []):
        name = wrestler.get("name", "")
        wrestler_id = wrestler.get("season_wrestler_id", "")
        current_variants = [name]  # Start with original name
        if name in name_variants:
            current_variants.extend(name_variants[name])
        
        # Process matches and filter out NC results
        processed_matches = []
        
        # First, process existing TrackWrestling matches and build duplicate keys
        for match in wrestler.get("matches", []):
            total_matches += 1
            # Pass team_name and season to process_match
            parsed = process_match(match.get("summary", ""), name, team_name, season)
            if parsed.get("result") == "SCRAPER_ERROR":
                scraper_errors += 1
            elif parsed.get("result") == "PARSE_ERROR":
                parse_errors += 1
            match.update(parsed)
            
            # Filter out matches with NC (No Contest) result
            if parsed.get("result") != "NC":
                processed_matches.append(match)
                
                # Add to existing match keys for duplicate detection
                # Extract winner/loser IDs from match
                date = match.get("date", "")
                weight = match.get("weight", "")
                opponent_id = match.get("opponent_id", "")
                
                # Determine winner/loser from parsed fields
                winner_name = parsed.get("winner_name", "")
                loser_name = parsed.get("loser_name", "")
                
                # If this wrestler is the winner, opponent is loser
                # If this wrestler is the loser, opponent is winner
                # We need to check the result to determine
                if winner_name == name:
                    # This wrestler won, opponent lost
                    match_key = build_duplicate_key(date, weight, wrestler_id, opponent_id)
                elif loser_name == name:
                    # This wrestler lost, opponent won
                    match_key = build_duplicate_key(date, weight, opponent_id, wrestler_id)
                else:
                    # Can't determine, skip duplicate key
                    match_key = None
                
                if match_key:
                    existing_match_keys.add(match_key)
        
        # Now add WrestleStat matches for this wrestler (if any)
        if wrestler_id in wrestlestat_matches_by_wrestler:
            for ws_match, dual_id in wrestlestat_matches_by_wrestler[wrestler_id]:
                winner_id = ws_match.get("winner_matsavant_id", "")
                loser_id = ws_match.get("loser_matsavant_id", "")
                date = ws_match.get("date", "")
                weight = ws_match.get("weight", "")
                
                # Build duplicate key
                match_key = build_duplicate_key(date, weight, winner_id, loser_id)
                
                # Check for duplicate with TrackWrestling (skip if exists)
                if match_key in existing_match_keys:
                    wrestlestat_duplicates += 1
                    winner_name = ws_match.get("winner_name", "Unknown")
                    loser_name = ws_match.get("loser_name", "Unknown")
                    print(f"[WRESTLESTAT DUPLICATE]")
                    print(f"  Date: {date}")
                    print(f"  Weight: {weight}")
                    print(f"  Winner: {winner_name} ({winner_id})")
                    print(f"  Loser: {loser_name} ({loser_id})")
                    print(f"  Source: TrackWrestling already present")
                    continue
                
                # Check if we've already added this WrestleStat match for this wrestler
                # (prevents adding same match twice if wrestler appears in multiple teams)
                wrestler_match_key = (match_key[0], match_key[1], match_key[2] if wrestler_id == winner_id else match_key[3], wrestler_id)
                if wrestler_match_key in added_wrestlestat_keys:
                    # Already added this match for this wrestler, skip
                    continue
                
                # Not a duplicate - add the match
                # Create match from this wrestler's perspective
                if wrestler_id == winner_id:
                    # This wrestler won
                    match_entry = {
                        "date": date,
                        "event": ws_match.get("event", ""),
                        "weight": weight,
                        "summary": ws_match.get("summary", ""),
                        "opponent_id": loser_id,
                        "winner_name": ws_match.get("winner_name", ""),
                        "winner_team": ws_match.get("winner_team", ""),
                        "loser_name": ws_match.get("loser_name", ""),
                        "loser_team": ws_match.get("loser_team", ""),
                        "result": ws_match.get("result", "")
                    }
                else:
                    # This wrestler lost
                    match_entry = {
                        "date": date,
                        "event": ws_match.get("event", ""),
                        "weight": weight,
                        "summary": ws_match.get("summary", ""),
                        "opponent_id": winner_id,
                        "winner_name": ws_match.get("winner_name", ""),
                        "winner_team": ws_match.get("winner_team", ""),
                        "loser_name": ws_match.get("loser_name", ""),
                        "loser_team": ws_match.get("loser_team", ""),
                        "result": ws_match.get("result", "")
                    }
                
                processed_matches.append(match_entry)
                wrestlestat_added += 1
                
                # Mark this WrestleStat match as added for this wrestler
                # (allows same match to be added to other wrestler's list, but prevents duplicate for this wrestler)
                added_wrestlestat_keys.add(wrestler_match_key)
                
                # Log addition
                winner_name = ws_match.get("winner_name", "Unknown")
                loser_name = ws_match.get("loser_name", "Unknown")
                print(f"[WRESTLESTAT ADDED]")
                print(f"  Date: {date}")
                print(f"  Weight: {weight}")
                print(f"  Winner: {winner_name} ({winner_id})")
                print(f"  Loser: {loser_name} ({loser_id})")
                print(f"  Dual ID: {dual_id}")
        
        # Replace matches list with filtered matches (now including WrestleStat)
        wrestler["matches"] = processed_matches

    # Print a summary of errors for the file
    file_name = os.path.basename(input_path)
    print(f"File: {file_name} - Processed {total_matches} matches")
    if scraper_errors > 0:
        print(f"   ❌ Found {scraper_errors} SCRAPER_ERRORS")
    if parse_errors > 0:
        print(f"   ⚠️ Found {parse_errors} PARSE_ERRORS")
    if scraper_errors == 0 and parse_errors == 0:
        print(f"   ✅ No errors found")
    if wrestlestat_added > 0:
        print(f"   ➕ Added {wrestlestat_added} WrestleStat matches")
    if wrestlestat_duplicates > 0:
        print(f"   🔄 Skipped {wrestlestat_duplicates} WrestleStat duplicates")

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
        
    # Return error counts and WrestleStat stats for overall summary
    return total_matches, scraper_errors, parse_errors, wrestlestat_added, wrestlestat_duplicates

def build_existing_match_keys(in_dir: str, season: str) -> Set[Tuple[str, str, str, str]]:
    """
    Build set of existing match keys from all TrackWrestling files.
    
    This is done BEFORE processing WrestleStat matches to ensure accurate duplicate detection.
    We process matches to get parsed winner/loser information.
    """
    existing_keys = set()
    
    for filename in os.listdir(in_dir):
        if not filename.endswith(".json"):
            continue
        
        input_path = os.path.join(in_dir, filename)
        try:
            with open(input_path, "r") as f:
                data = json.load(f)
            
            team_name = data.get("team_name", "Unknown")
            
            for wrestler in data.get("roster", []):
                name = wrestler.get("name", "")
                wrestler_id = wrestler.get("season_wrestler_id", "")
                
                for match in wrestler.get("matches", []):
                    date = match.get("date", "")
                    weight = match.get("weight", "")
                    opponent_id = match.get("opponent_id", "")
                    
                    # Process match to get parsed winner/loser info
                    parsed = process_match(match.get("summary", ""), name, team_name, season)
                    
                    # Skip if parsing failed
                    if parsed.get("result") in ("SCRAPER_ERROR", "PARSE_ERROR"):
                        continue
                    
                    winner_name = parsed.get("winner_name", "")
                    loser_name = parsed.get("loser_name", "")
                    
                    # Determine if this wrestler is winner or loser
                    if winner_name == name:
                        # This wrestler won
                        match_key = build_duplicate_key(date, weight, wrestler_id, opponent_id)
                    elif loser_name == name:
                        # This wrestler lost
                        match_key = build_duplicate_key(date, weight, opponent_id, wrestler_id)
                    else:
                        # Can't determine, skip
                        continue
                    
                    existing_keys.add(match_key)
        except Exception as e:
            print(f"⚠️ Error reading file {filename} for duplicate detection: {e}")
            continue
    
    return existing_keys


def main(season):
    in_dir = os.path.join("mt", "data_alias", season)
    out_dir = os.path.join("mt", "processed_data", season)
    public_out_dir = os.path.join("frontend", "wrestledata-ui", "public", "data", "processed_data", season)
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(public_out_dir, exist_ok=True)

    # Step 1: Build existing match keys from TrackWrestling files
    print("\n========== BUILDING DUPLICATE DETECTION INDEX ==========")
    existing_match_keys = build_existing_match_keys(in_dir, season)
    print(f"Found {len(existing_match_keys)} existing match keys")

    # Step 2: Load WrestleStat matches
    print("\n========== LOADING WRESTLESTAT DATA ==========")
    wrestlestat_matches = load_wrestlestat_matches(season, out_dir)
    print(f"Loaded {len(wrestlestat_matches)} WrestleStat matches")
    
    # Organize WrestleStat matches by wrestler ID (for both winner and loser)
    wrestlestat_matches_by_wrestler: Dict[str, List[Tuple[Dict, str]]] = {}
    for ws_match, dual_id in wrestlestat_matches:
        winner_id = ws_match.get("winner_matsavant_id", "")
        loser_id = ws_match.get("loser_matsavant_id", "")
        
        # Add to winner's list
        if winner_id:
            if winner_id not in wrestlestat_matches_by_wrestler:
                wrestlestat_matches_by_wrestler[winner_id] = []
            wrestlestat_matches_by_wrestler[winner_id].append((ws_match, dual_id))
        
        # Add to loser's list
        if loser_id:
            if loser_id not in wrestlestat_matches_by_wrestler:
                wrestlestat_matches_by_wrestler[loser_id] = []
            wrestlestat_matches_by_wrestler[loser_id].append((ws_match, dual_id))
    
    print(f"WrestleStat matches organized for {len(wrestlestat_matches_by_wrestler)} wrestlers")

    total_files = 0
    total_matches = 0
    total_scraper_errors = 0
    total_parse_errors = 0
    total_wrestlestat_added = 0
    total_wrestlestat_duplicates = 0

    # Set to track WrestleStat matches already added (per wrestler)
    # Format: (date, weight, opponent_id, wrestler_id) - allows same match for winner and loser
    added_wrestlestat_keys: Set[Tuple[str, str, str, str]] = set()

    # Step 3: Process TrackWrestling files and merge WrestleStat matches
    for filename in os.listdir(in_dir):
        if filename.endswith(".json"):
            total_files += 1
            input_path = os.path.join(in_dir, filename)
            output_path = os.path.join(out_dir, filename)
            public_output_path = os.path.join(public_out_dir, filename)
            matches, scraper_errors, parse_errors, ws_added, ws_duplicates = process_file(
                input_path, output_path, season, wrestlestat_matches_by_wrestler, existing_match_keys, added_wrestlestat_keys
            )
            
            # Also copy to public location for frontend access
            try:
                with open(output_path, "r") as f:
                    data = json.load(f)
                with open(public_output_path, "w") as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                print(f"⚠️ Warning: Could not copy to public location {public_output_path}: {e}")
            
            total_matches += matches
            total_scraper_errors += scraper_errors
            total_parse_errors += parse_errors
            total_wrestlestat_added += ws_added
            total_wrestlestat_duplicates += ws_duplicates
    
    # Print overall summary
    print("\n========== SEASON SUMMARY ==========")
    print(f"Processed {total_files} files with {total_matches} total matches")
    if total_scraper_errors > 0:
        print(f"❌ Total SCRAPER_ERRORS: {total_scraper_errors}")
    if total_parse_errors > 0:
        print(f"⚠️ Total PARSE_ERRORS: {total_parse_errors}")
    
    print(f"\n========== WRESTLESTAT MERGE SUMMARY ==========")
    print(f"WrestleStat matches processed: {len(wrestlestat_matches)}")
    print(f"Duplicates skipped: {total_wrestlestat_duplicates}")
    print(f"New matches added: {total_wrestlestat_added}")
    
    if total_scraper_errors == 0 and total_parse_errors == 0:
        print("✅ No errors found in any files!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-season", required=True, help="Season folder name (e.g., 2014)")
    args = parser.parse_args()
    main(args.season)
