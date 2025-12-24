#!/usr/bin/env python3
"""
WrestleStat UI Helpers
CLI utilities for team and wrestler resolution during WrestleStat ingestion.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from difflib import SequenceMatcher
from datetime import datetime

# Paths
MAPPINGS_DIR = Path(__file__).parent.parent / "data" / "mappings"
TEAMS_MAPPING_FILE = MAPPINGS_DIR / "wrestlestat_teams.json"
WRESTLERS_MAPPING_FILE = MAPPINGS_DIR / "wrestlestat_wrestlers.json"
TEAMS_DATA_DIR = Path(__file__).parent.parent / "data" / "team_lists"
WRESTLERS_DATA_DIR = Path(__file__).parent.parent / "mt" / "data"


def normalize_name(name: str) -> str:
    """Normalize name for comparison."""
    if not name:
        return ""
    # Strip ranking prefix (e.g., "#12 " or "12 ") if present
    name = re.sub(r'^#?\d+\s+', '', name)
    # Remove non-word characters except spaces
    name = re.sub(r'[^\w\s]', '', name)
    # Normalize whitespace
    name = re.sub(r'\s+', ' ', name)
    return name.strip().lower()


def load_team_mappings() -> List[Dict]:
    """Load WrestleStat team mappings."""
    if TEAMS_MAPPING_FILE.exists():
        with open(TEAMS_MAPPING_FILE, 'r') as f:
            return json.load(f)
    return []


def save_team_mappings(mappings: List[Dict]) -> None:
    """Save WrestleStat team mappings."""
    MAPPINGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(TEAMS_MAPPING_FILE, 'w') as f:
        json.dump(mappings, f, indent=2)


def load_wrestler_mappings() -> List[Dict]:
    """Load WrestleStat wrestler mappings."""
    if WRESTLERS_MAPPING_FILE.exists():
        with open(WRESTLERS_MAPPING_FILE, 'r') as f:
            return json.load(f)
    return []


def save_wrestler_mappings(mappings: List[Dict]) -> None:
    """Save WrestleStat wrestler mappings."""
    MAPPINGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(WRESTLERS_MAPPING_FILE, 'w') as f:
        json.dump(mappings, f, indent=2)


def load_matsavant_teams(season: int) -> Dict[str, Dict]:
    """Load MatSavant teams for a season."""
    teams_file = TEAMS_DATA_DIR / str(season) / "ncaa_d1_teams.json"
    if not teams_file.exists():
        return {}
    
    with open(teams_file, 'r') as f:
        teams_list = json.load(f)
    
    # Create lookup by normalized name
    teams_by_name = {}
    for team in teams_list:
        name = team.get("name", "")
        norm_name = normalize_name(name)
        # Use team name as ID (or create ID from name)
        team_id = team.get("abbreviation", "").lower() or name.lower().replace(" ", "_")
        teams_by_name[norm_name] = {
            "id": team_id,
            "name": name,
            "abbreviation": team.get("abbreviation", ""),
            "raw": team
        }
    
    return teams_by_name


def resolve_wrestlestat_team(
    wrestlestat_team_id: int,
    wrestlestat_name: str,
    season: int = 2026
) -> Optional[str]:
    """
    Resolve WrestleStat team to MatSavant team ID.
    
    Returns MatSavant team ID if found, None if user skips.
    """
    mappings = load_team_mappings()
    
    # Check existing mapping
    for mapping in mappings:
        if mapping.get("wrestlestat_team_id") == wrestlestat_team_id:
            # Check if marked as non-D1
            if mapping.get("non_d1", False):
                print(f"✓ Team marked as non-D1: {wrestlestat_name}")
                return None  # Return None to indicate non-D1 team
            print(f"✓ Using existing mapping: {wrestlestat_name} → {mapping['matsavant_team_id']}")
            return mapping["matsavant_team_id"]
    
    # Need to resolve
    print(f"\n{'='*60}")
    print(f"Resolving WrestleStat team:")
    print(f"  ID: {wrestlestat_team_id}")
    print(f"  Name: {wrestlestat_name}")
    print(f"{'='*60}")
    
    matsavant_teams = load_matsavant_teams(season)
    
    # Try exact match
    norm_wrestlestat = normalize_name(wrestlestat_name)
    if norm_wrestlestat in matsavant_teams:
        team_info = matsavant_teams[norm_wrestlestat]
        print(f"\n✓ Exact match found: {team_info['name']} ({team_info['id']})")
        print("Options:")
        print("  [Y] Confirm this match")
        print("  [n] Reject and search manually")
        print("  [d] Mark as non-D1")
        response = input("Choose [Y/n/d]: ").strip().lower()
        if response == 'd':
            # Mark as non-D1
            mapping = {
                "wrestlestat_team_id": wrestlestat_team_id,
                "wrestlestat_name": wrestlestat_name,
                "non_d1": True,
                "confirmed_at": datetime.now().isoformat()
            }
            mappings.append(mapping)
            save_team_mappings(mappings)
            print(f"✓ Marked {wrestlestat_name} as non-D1. Duals with this team will be skipped.")
            return None
        if response != 'n':
            mapping = {
                "wrestlestat_team_id": wrestlestat_team_id,
                "wrestlestat_name": wrestlestat_name,
                "matsavant_team_id": team_info['id'],
                "confirmed_at": datetime.now().isoformat()
            }
            mappings.append(mapping)
            save_team_mappings(mappings)
            return team_info['id']
    
    # Fuzzy match
    candidates = []
    for norm_name, team_info in matsavant_teams.items():
        similarity = SequenceMatcher(None, norm_wrestlestat, norm_name).ratio()
        if similarity >= 0.7:
            candidates.append((similarity, team_info))
    
    candidates.sort(reverse=True, key=lambda x: x[0])
    
    if candidates:
        print(f"\nSimilar MatSavant teams found:")
        for idx, (sim, team_info) in enumerate(candidates[:5], 1):
            print(f"  {idx}. {team_info['name']} ({team_info['id']}) - {sim*100:.1f}% match")
        
        choice = input("\nSelect team number, 'm' for manual search, or 'd' to mark as non-D1: ").strip().lower()
        
        if choice == 'd':
            # Mark as non-D1
            mapping = {
                "wrestlestat_team_id": wrestlestat_team_id,
                "wrestlestat_name": wrestlestat_name,
                "non_d1": True,
                "confirmed_at": datetime.now().isoformat()
            }
            mappings.append(mapping)
            save_team_mappings(mappings)
            print(f"✓ Marked {wrestlestat_name} as non-D1. Duals with this team will be skipped.")
            return None
        
        if choice == 'm':
            search_term = input("Enter search term: ").strip().lower()
            # Search all teams, not just candidates
            filtered = []
            for norm_name, team_info in matsavant_teams.items():
                if search_term in team_info['name'].lower() or search_term in team_info['id'].lower():
                    filtered.append(team_info)
            
            if not filtered:
                print("No matches found. Showing all teams:")
                filtered = list(matsavant_teams.values())[:20]  # Show first 20 as fallback
            
            print(f"\nSearch results ({len(filtered)} found):")
            for idx, team_info in enumerate(filtered[:20], 1):
                print(f"  {idx}. {team_info['name']} ({team_info['id']})")
            
            if len(filtered) > 20:
                print(f"  ... and {len(filtered) - 20} more")
            
            choice = input("\nSelect team number: ").strip().lower()
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(filtered):
                    selected = filtered[idx]
                else:
                    print("Invalid selection.")
                    return None
            except ValueError:
                print("Invalid input.")
                return None
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(candidates):
                    selected = candidates[idx][1]
                else:
                    print("Invalid selection.")
                    return None
            except ValueError:
                print("Invalid input.")
                return None
        
        mapping = {
            "wrestlestat_team_id": wrestlestat_team_id,
            "wrestlestat_name": wrestlestat_name,
            "matsavant_team_id": selected['id'],
            "confirmed_at": datetime.now().isoformat()
        }
        mappings.append(mapping)
        save_team_mappings(mappings)
        print(f"✓ Mapped {wrestlestat_name} → {selected['name']} ({selected['id']})")
        return selected['id']
    
    # No fuzzy matches found - show manual search interface or mark as non-D1
    print("\nNo similar MatSavant teams found.")
    print("Options:")
    print("  1. Search for a MatSavant team manually")
    print("  2. Mark this team as non-D1 (will skip duals with this team)")
    
    choice = input("\nEnter '1' to search, '2' to mark as non-D1, or 's' to skip: ").strip().lower()
    
    if choice == '2':
        # Mark as non-D1
        mapping = {
            "wrestlestat_team_id": wrestlestat_team_id,
            "wrestlestat_name": wrestlestat_name,
            "non_d1": True,
            "confirmed_at": datetime.now().isoformat()
        }
        mappings.append(mapping)
        save_team_mappings(mappings)
        print(f"✓ Marked {wrestlestat_name} as non-D1. Duals with this team will be skipped.")
        return None
    
    if choice == 's':
        return None
    
    # Manual search
    while True:
        search_term = input("Enter search term (or 'list' to see all teams): ").strip().lower()
        
        if search_term == 'list':
            # Show all teams
            all_teams = list(matsavant_teams.values())
            print(f"\nAll MatSavant teams ({len(all_teams)} total):")
            for idx, team_info in enumerate(all_teams[:50], 1):
                print(f"  {idx}. {team_info['name']} ({team_info['id']})")
            if len(all_teams) > 50:
                print(f"  ... and {len(all_teams) - 50} more")
            
            choice = input("\nSelect team number: ").strip()
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(all_teams):
                    selected = all_teams[idx]
                    break
                else:
                    print("Invalid selection. Please try again.")
                    continue
            except ValueError:
                print("Invalid input. Please try again.")
                continue
        
        if not search_term:
            print("Search term cannot be empty.")
            continue
        
        # Search all teams
        filtered = []
        for norm_name, team_info in matsavant_teams.items():
            if search_term in team_info['name'].lower() or search_term in team_info['id'].lower():
                filtered.append(team_info)
        
        if not filtered:
            print("No matches found. Try a different search term or use 'list' to see all teams.")
            continue
        
        print(f"\nSearch results ({len(filtered)} found):")
        for idx, team_info in enumerate(filtered[:20], 1):
            print(f"  {idx}. {team_info['name']} ({team_info['id']})")
        
        if len(filtered) > 20:
            print(f"  ... and {len(filtered) - 20} more")
            print("  (Refine your search to see more results)")
        
        choice = input("\nSelect team number, or press Enter to search again: ").strip()
        
        if not choice:
            continue
        
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(filtered):
                selected = filtered[idx]
                break
            else:
                print("Invalid selection. Please try again.")
                continue
        except ValueError:
            print("Invalid input. Please try again.")
            continue
    
    # Save the mapping
    mapping = {
        "wrestlestat_team_id": wrestlestat_team_id,
        "wrestlestat_name": wrestlestat_name,
        "matsavant_team_id": selected['id'],
        "confirmed_at": datetime.now().isoformat()
    }
    mappings.append(mapping)
    save_team_mappings(mappings)
    print(f"✓ Mapped {wrestlestat_name} → {selected['name']} ({selected['id']})")
    return selected['id']


def get_ranking_weight_from_rankings(wrestler_id: str, season: int) -> Optional[int]:
    """
    Look up a wrestler's ranking weight from rankings files.
    Searches all weight class rankings files to find where this wrestler is ranked.
    
    Returns the weight class where the wrestler is found, or None if not found.
    """
    weights = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]
    
    # Check both public and mt/rankings_data directories
    # Public directory may only have starters files, mt/rankings_data has full rankings
    rankings_dirs = [
        Path("frontend/wrestledata-ui/public/data/rankings") / str(season),
        Path("mt/rankings_data") / str(season)
    ]
    
    wrestler_id_str = str(wrestler_id)
    
    # Search through all weight classes
    for weight in weights:
        # Check both directories, and both starters file and full rankings file
        # Some wrestlers may be in full rankings but not starters
        for rankings_dir in rankings_dirs:
            if not rankings_dir.exists():
                continue
            
            files_to_check = [
                rankings_dir / f"rankings_starters_{weight}.json",
                rankings_dir / f"rankings_{weight}.json"
            ]
            
            for rankings_file in files_to_check:
                if not rankings_file.exists():
                    continue
                
                try:
                    with open(rankings_file, 'r') as f:
                        data = json.load(f)
                    
                    rankings = data.get("rankings", [])
                    for entry in rankings:
                        # Check both wrestler_id and season_wrestler_id fields
                        entry_id = entry.get("wrestler_id") or entry.get("season_wrestler_id")
                        # Convert both to strings for comparison
                        entry_id_str = str(entry_id) if entry_id is not None else ""
                        if entry_id_str == wrestler_id_str:
                            return weight
                except Exception as e:
                    # Debug: log errors
                    print(f"[DEBUG] Error reading {rankings_file.name}: {e}")
                    continue
    
    return None


def load_matsavant_wrestlers(team_id: str, season: int) -> List[Dict]:
    """Load MatSavant wrestlers for a team and season."""
    wrestlers_dir = WRESTLERS_DATA_DIR / str(season)
    
    # Try multiple naming conventions
    # 1. team_id with title case (e.g., "uva" -> "Uva.json")
    team_file = wrestlers_dir / f"{team_id.replace('_', ' ').title().replace(' ', '_')}.json"
    
    # 2. team_id as-is (e.g., "uva.json")
    if not team_file.exists():
        team_file = wrestlers_dir / f"{team_id}.json"
    
    # 3. Search for file by team_name in JSON (team_id might be abbreviation)
    if not team_file.exists():
        # Load team data from team profiles to get team_name
        # team_id might be an abbreviation, so search all team profile files
        teams_dir = Path(__file__).parent.parent / "mt" / "teams"
        
        # First try direct filename match
        team_profile_file = teams_dir / f"{team_id}.json"
        if not team_profile_file.exists():
            # Search all team profile files for matching team_id or abbreviation
            team_profile_file = None
            for profile_file in teams_dir.glob("*.json"):
                try:
                    with open(profile_file, 'r') as f:
                        team_profile = json.load(f)
                    profile_team_id = team_profile.get("team_id", "").lower()
                    profile_abbreviation = team_profile.get("abbreviation", "").upper()
                    team_id_upper = team_id.upper()
                    
                    # Check if team_id matches profile's team_id or abbreviation
                    if profile_team_id == team_id.lower() or profile_abbreviation == team_id_upper:
                        team_profile_file = profile_file
                        break
                except:
                    continue
        
        if team_profile_file and team_profile_file.exists():
            try:
                with open(team_profile_file, 'r') as f:
                    team_profile = json.load(f)
                team_name = team_profile.get("team_name", "")
                if team_name:
                    # Try team_name as filename
                    team_file = wrestlers_dir / f"{team_name.replace(' ', '_')}.json"
            except:
                pass
    
    # 4. Search all files for matching team_name
    if not team_file.exists():
        # Last resort: search all JSON files for matching team_name
        for json_file in wrestlers_dir.glob("*.json"):
            try:
                with open(json_file, 'r') as f:
                    team_data = json.load(f)
                file_team_name = team_data.get("team_name", "").lower()
                file_team_id = team_data.get("team_id", "").lower()
                
                # Check if team_id or team_name matches
                if file_team_id == team_id.lower() or file_team_name == team_id.lower():
                    team_file = json_file
                    break
            except:
                continue
    
    if not team_file.exists():
        print(f"[DEBUG] Could not find team file for team_id '{team_id}'. Searched:")
        alt_name1 = team_id.replace("_", " ").title().replace(" ", "_")
        print(f"  - {wrestlers_dir / f'{alt_name1}.json'}")
        print(f"  - {wrestlers_dir / f'{team_id}.json'}")
        return []
    
    with open(team_file, 'r') as f:
        team_data = json.load(f)
    
    wrestlers = team_data.get("roster", [])
    
    # For each wrestler, look up their ranking weight from rankings files
    for wrestler in wrestlers:
        wrestler_id = wrestler.get("season_wrestler_id")
        if wrestler_id:
            ranking_weight = get_ranking_weight_from_rankings(str(wrestler_id), season)
            if ranking_weight:
                stored_weight_class = int(wrestler.get("weight_class", 0))
                wrestler["_ranking_weight"] = ranking_weight
                wrestler["_weight_class_mismatch"] = (stored_weight_class != ranking_weight)
    
    return wrestlers


def resolve_wrestlestat_wrestler(
    wrestlestat_wrestler_id: int,
    wrestlestat_name: str,
    team_id: str,
    listed_weight: int,
    season: int = 2026
) -> Optional[str]:
    """
    Resolve WrestleStat wrestler to MatSavant wrestler ID.
    
    Returns MatSavant season_wrestler_id if found, None if user skips.
    """
    mappings = load_wrestler_mappings()
    
    # Check existing mapping
    print(f"[DEBUG] Checking for existing mapping: WrestleStat ID={wrestlestat_wrestler_id}, name='{wrestlestat_name}'")
    for mapping in mappings:
        if mapping.get("wrestlestat_wrestler_id") == wrestlestat_wrestler_id:
            print(f"✓ Using existing mapping: {wrestlestat_name} → {mapping['matsavant_wrestler_id']}")
            return mapping["matsavant_wrestler_id"]
    
    print(f"[DEBUG] No existing mapping found for WrestleStat ID {wrestlestat_wrestler_id}")
    
    # Load MatSavant wrestlers for this team
    matsavant_wrestlers = load_matsavant_wrestlers(team_id, season)
    
    if not matsavant_wrestlers:
        print(f"⚠ No MatSavant wrestlers found for team {team_id}")
        return None
    
    norm_wrestlestat = normalize_name(wrestlestat_name)
    
    # DEBUG: Show normalized names for troubleshooting
    print(f"\n[DEBUG] WrestleStat name: '{wrestlestat_name}' → normalized: '{norm_wrestlestat}'")
    
    # IMPORTANT: Use ranking weight (weight_class) for matching, not listed weight
    # The listed_weight is the weight class of the match from WrestleStat
    # We want to match wrestlers whose ranking weight (weight_class) matches the match weight
    # Ranking weight is authoritative - it's what the wrestler is actually ranked at
    
    # Tier A: Exact name match - prioritize by ranking weight match
    # Use ranking weight from rankings files (authoritative source)
    exact_matches = []
    for wrestler in matsavant_wrestlers:
        matsavant_name = wrestler.get("name", "")
        norm_matsavant = normalize_name(matsavant_name)
        if norm_matsavant == norm_wrestlestat:
            # Use ranking weight from rankings files if available, otherwise use weight_class
            ranking_weight_from_rankings = wrestler.get("_ranking_weight")
            stored_weight_class = int(wrestler.get("weight_class", 0))
            
            if ranking_weight_from_rankings:
                ranking_weight = ranking_weight_from_rankings
                weight_mismatch = wrestler.get("_weight_class_mismatch", False)
            else:
                ranking_weight = stored_weight_class
                weight_mismatch = False
            
            # Prioritize wrestlers whose ranking weight matches the match weight
            weight_match = (ranking_weight == listed_weight)
            weight_diff = abs(ranking_weight - listed_weight)
            # Sort: weight match first, then by weight diff
            exact_matches.append((not weight_match, weight_diff, wrestler, ranking_weight, weight_mismatch))
            print(f"[DEBUG] Exact match found: '{matsavant_name}' → normalized: '{norm_matsavant}' (matches WrestleStat: '{norm_wrestlestat}')")
    
    if exact_matches:
        print(f"[DEBUG] Found {len(exact_matches)} exact name match(es), processing...")
        exact_matches.sort(key=lambda x: (x[0], x[1]))  # False (match) comes before True (no match)
        best_match_data = exact_matches[0]
        best_match = best_match_data[2]
        ranking_weight = best_match_data[3]  # Use inferred or stored ranking weight
        weight_mismatch_flag = best_match_data[4]
        stored_weight_class = int(best_match.get("weight_class", 0))
        weight_match = (ranking_weight == listed_weight)
        
        print(f"\n✓ Exact name match found:")
        print(f"  Name: {best_match.get('name')}")
        print(f"  ID: {best_match.get('season_wrestler_id')}")
        if weight_mismatch_flag:
            print(f"  Stored weight_class: {stored_weight_class} lbs")
            print(f"  Ranking weight (from rankings): {ranking_weight} lbs")
            print(f"  Match weight: {listed_weight} lbs")
        else:
            print(f"  Ranking Weight: {ranking_weight} lbs (match weight: {listed_weight} lbs)")
        
        if weight_match:
            if weight_mismatch_flag:
                print(f"  ✓ Ranking weight from rankings ({ranking_weight}) matches match weight ({listed_weight})")
                print(f"  ⚠ Note: Stored weight_class ({stored_weight_class}) is incorrect - using ranking weight")
            else:
                print("  ✓ Ranking weight matches match weight - this is the correct wrestler")
            # Auto-confirm exact matches with matching weight - no prompt needed
            print("  ✓ Auto-confirming exact match with matching weight")
            mapping = {
                "wrestlestat_wrestler_id": wrestlestat_wrestler_id,
                "wrestlestat_name": wrestlestat_name,
                "matsavant_wrestler_id": best_match.get("season_wrestler_id"),
                "team_id": team_id,
                "ranking_weight": ranking_weight,  # Use ranking weight from rankings
                "match_type": "exact",
                "confirmed_at": datetime.now().isoformat()
            }
            mappings.append(mapping)
            save_wrestler_mappings(mappings)
            return best_match.get("season_wrestler_id")
        else:
            print(f"  ⚠ Ranking weight ({ranking_weight}) does not match match weight ({listed_weight})")
            if weight_mismatch_flag:
                print(f"     Stored weight_class: {stored_weight_class} (may be incorrect)")
            print(f"     Note: If this wrestler's ranking weight is wrong in MatSavant data, you may need to update it.")
            if len(exact_matches) > 1:
                print(f"\n  Other exact name matches found:")
                for idx, match_data in enumerate(exact_matches[1:], 2):
                    w = match_data[2]
                    rw = match_data[3]
                    wm_flag = match_data[4]
                    stored_wc = int(w.get("weight_class", 0))
                    if wm_flag:
                        print(f"    {idx}. Ranking weight: {rw} lbs, Stored: {stored_wc} lbs (match: {rw == listed_weight})")
                    else:
                        print(f"    {idx}. Ranking Weight: {rw} lbs (match: {rw == listed_weight})")
            response = input("Confirm this wrestler anyway? [y/N]: ").strip().lower()
            if response == 'y':
                mapping = {
                    "wrestlestat_wrestler_id": wrestlestat_wrestler_id,
                    "wrestlestat_name": wrestlestat_name,
                    "matsavant_wrestler_id": best_match.get("season_wrestler_id"),
                    "team_id": team_id,
                    "ranking_weight": ranking_weight,  # Use inferred ranking weight
                    "match_type": "exact",
                    "override": True,
                    "confirmed_at": datetime.now().isoformat()
                }
                mappings.append(mapping)
                save_wrestler_mappings(mappings)
                return best_match.get("season_wrestler_id")
            else:
                # User declined exact match, continue to fuzzy match
                print("  Skipping exact match, checking for fuzzy matches...")
    else:
        print(f"[DEBUG] No exact name matches found. WrestleStat normalized: '{norm_wrestlestat}'")
        # Show a few MatSavant names for comparison
        print(f"[DEBUG] Sample MatSavant names:")
        for idx, wrestler in enumerate(matsavant_wrestlers[:5], 1):
            matsavant_name = wrestler.get("name", "")
            norm_matsavant = normalize_name(matsavant_name)
            print(f"  {idx}. '{matsavant_name}' → normalized: '{norm_matsavant}'")
    
    # Tier B: Fuzzy match - prioritize by ranking weight match, then similarity
    # IMPORTANT: Ranking weight from rankings files is authoritative, not stored weight_class
    fuzzy_matches = []
    for wrestler in matsavant_wrestlers:
        matsavant_name = wrestler.get("name", "")
        norm_matsavant = normalize_name(matsavant_name)
        similarity = SequenceMatcher(None, norm_wrestlestat, norm_matsavant).ratio()
        if similarity >= 0.90:
            # DEBUG: Show why exact match failed
            if similarity < 1.0:
                print(f"[DEBUG] Fuzzy match: '{matsavant_name}' → normalized: '{norm_matsavant}' (similarity: {similarity*100:.1f}%)")
            # Use ranking weight from rankings files if available, otherwise use weight_class
            ranking_weight_from_rankings = wrestler.get("_ranking_weight")
            if ranking_weight_from_rankings:
                ranking_weight = ranking_weight_from_rankings
            else:
                ranking_weight = int(wrestler.get("weight_class", 0))
            
            weight_match = (ranking_weight == listed_weight)
            weight_diff = abs(ranking_weight - listed_weight)
            # Sort: weight match first, then similarity, then weight diff
            fuzzy_matches.append((not weight_match, -similarity, weight_diff, wrestler, ranking_weight))
    
    if fuzzy_matches:
        fuzzy_matches.sort(key=lambda x: (x[0], x[1], x[2]))  # False (match) first, then higher similarity
        print(f"\n⚠ Fuzzy match candidates (≥90% similarity):")
        print(f"   Match weight: {listed_weight} lbs")
        print(f"   Ranking weight is authoritative (from rankings files)")
        for idx, match_data in enumerate(fuzzy_matches[:5], 1):
            weight_match_flag, neg_sim, weight_diff, wrestler, ranking_weight = match_data
            similarity = -neg_sim
            stored_weight_class = int(wrestler.get("weight_class", 0))
            weight_mismatch_flag = wrestler.get("_weight_class_mismatch", False)
            
            if not weight_match_flag:
                weight_status = f"✓ MATCHES match weight ({listed_weight})"
            else:
                weight_status = f"diff: {weight_diff} (ranking: {ranking_weight}, match: {listed_weight})"
            
            print(f"  {idx}. {wrestler.get('name')} (ID: {wrestler.get('season_wrestler_id')})")
            if weight_mismatch_flag:
                print(f"     Similarity: {similarity*100:.1f}%, Ranking Weight: {ranking_weight} (from rankings, stored: {stored_weight_class}) - {weight_status}")
            else:
                print(f"     Similarity: {similarity*100:.1f}%, Ranking Weight: {ranking_weight} - {weight_status}")
        
        choice = input("\nSelect wrestler number, or 'm' for manual search: ").strip().lower()
        
        if choice == 'm':
            return manual_wrestler_search(wrestlestat_wrestler_id, wrestlestat_name, team_id, listed_weight, season)
        
        # Allow 'y' or 'yes' to confirm the first (best) match
        if choice in ['y', 'yes'] and len(fuzzy_matches) > 0:
            choice = '1'
        
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(fuzzy_matches):
                match_data = fuzzy_matches[idx]
                selected = match_data[3]
                ranking_weight = match_data[4]  # Use inferred or stored ranking weight
                weight_match = (ranking_weight == listed_weight)
                weight_mismatch_flag = selected.get("_weight_class_mismatch", False)
                stored_weight_class = int(selected.get("weight_class", 0))
                
                if not weight_match:
                    print(f"⚠ Ranking weight ({ranking_weight}) does not match match weight ({listed_weight})")
                    if weight_mismatch_flag:
                        print(f"   Stored weight_class: {stored_weight_class} (may be incorrect)")
                    print(f"   Note: Ranking weight is authoritative. Match weight is just the weight class of this match.")
                    confirm = input("Confirm anyway? [y/N]: ").strip().lower()
                    if confirm != 'y':
                        return None
                
                mapping = {
                    "wrestlestat_wrestler_id": wrestlestat_wrestler_id,
                    "wrestlestat_name": wrestlestat_name,
                    "matsavant_wrestler_id": selected.get("season_wrestler_id"),
                    "team_id": team_id,
                    "ranking_weight": ranking_weight,  # Use inferred ranking weight
                    "match_type": "fuzzy",
                    "override": not weight_match,
                    "confirmed_at": datetime.now().isoformat()
                }
                mappings.append(mapping)
                save_wrestler_mappings(mappings)
                return selected.get("season_wrestler_id")
        except ValueError:
            print("Invalid input.")
            return None
    
    # Tier C: Manual search
    return manual_wrestler_search(wrestlestat_wrestler_id, wrestlestat_name, team_id, listed_weight, season)


def manual_wrestler_search(
    wrestlestat_wrestler_id: int,
    wrestlestat_name: str,
    team_id: str,
    listed_weight: int,
    season: int
) -> Optional[str]:
    """Manual wrestler search."""
    print(f"\nManual search for: {wrestlestat_name}")
    search_term = input("Enter search term (or 's' to skip): ").strip().lower()
    
    if search_term == 's':
        return None
    
    matsavant_wrestlers = load_matsavant_wrestlers(team_id, season)
    filtered = []
    
    for wrestler in matsavant_wrestlers:
        name = wrestler.get("name", "").lower()
        if search_term in name:
            ranking_weight = int(wrestler.get("weight_class", 0))
            filtered.append((abs(ranking_weight - listed_weight), wrestler))
    
    if not filtered:
        print("No matches found.")
        return None
    
    filtered.sort(key=lambda x: x[0])
    
    print(f"\nFiltered results:")
    for idx, (weight_diff, wrestler) in enumerate(filtered[:10], 1):
        ranking_weight = int(wrestler.get("weight_class", 0))
        print(f"  {idx}. {wrestler.get('name')} (ID: {wrestler.get('season_wrestler_id')}, Weight: {ranking_weight})")
    
    choice = input("\nSelect wrestler number, or 's' to skip: ").strip().lower()
    if choice == 's':
        return None
    
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(filtered):
            selected = filtered[idx][1]
            ranking_weight = int(selected.get("weight_class", 0))
            weight_diff = abs(ranking_weight - listed_weight)
            
            if weight_diff > 1:
                print(f"⚠ Weight mismatch: {ranking_weight} vs {listed_weight}")
                confirm = input("Confirm anyway? [y/N]: ").strip().lower()
                if confirm != 'y':
                    return None
            
            # Save the mapping
            mappings = load_wrestler_mappings()
            mapping = {
                "wrestlestat_wrestler_id": wrestlestat_wrestler_id,
                "wrestlestat_name": wrestlestat_name,
                "matsavant_wrestler_id": selected.get("season_wrestler_id"),
                "team_id": team_id,
                "ranking_weight": ranking_weight,
                "match_type": "manual",
                "override": weight_diff > 1,
                "confirmed_at": datetime.now().isoformat()
            }
            mappings.append(mapping)
            save_wrestler_mappings(mappings)
            print(f"✓ Saved mapping: {wrestlestat_name} → {selected.get('name')} ({selected.get('season_wrestler_id')})")
            return selected.get("season_wrestler_id")
    except ValueError:
        return None
    
    return None

