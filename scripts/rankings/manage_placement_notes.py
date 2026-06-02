#!/usr/bin/env python3
"""
Manage placement notes (previous-year finishes) for wrestlers.

These notes are purely cosmetic and are displayed next to the
record in the HTML ranking matrix, e.g.:

    Brendan McCrone (Ohio State) - 7-0 (FR)

Allowed notes:
    - FR  (Freshman / first year)
    - 1-8 (NCAA placement)
    - BR  (Blood Round)
    - Q   (Qualifier)

File format (mt/rankings_data/placement_notes.json):
{
  "notes": [
    {
      "wrestler_id": "12345",
      "name": "John Smith",
      "team": "Oklahoma State",
      "note": "FR"
    },
    ...
  ]
}

Usage:
  Run the script and follow the interactive prompts:

      python scripts/rankings/manage_placement_notes.py -season 2026

  The script will:
    - Prompt for a name fragment (case-insensitive, e.g. "Volk")
    - List all matching wrestlers from the rosters
    - Let you pick one by number
    - Ask for a placement note (FR, 1-8, BR, Q)
    - Save/update that note in placement_notes.json
    - Loop again for the next name fragment
"""

import argparse
import json
import re
from datetime import date
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from load_data import load_team_data


def league_dir_key(league, gender, state=None):
    if league == 'hs':
        return f"hs_{state.lower()}_{gender}"
    return f"ncaa_{gender}"


ALLOWED_NOTES = {"FR", "1", "2", "3", "4", "5", "6", "7", "8", "BR", "Q"}


def search_wrestlers(teams: List[Dict], query: str) -> List[Dict]:
    """Return wrestlers whose names contain the query (case-insensitive)."""
    query_lower = query.lower()
    results: List[Dict] = []

    for team in teams:
        team_name = team.get("team_name", "Unknown")
        for wrestler in team.get("roster", []):
            wid = wrestler.get("season_wrestler_id")
            name = wrestler.get("name", "Unknown")
            if not wid or wid == "null":
                continue
            if query_lower in name.lower():
                results.append(
                    {
                        "wrestler_id": wid,
                        "name": name,
                        "team": team_name,
                        "weight_class": wrestler.get("weight_class", ""),
                    }
                )

    return results


def load_notes(path: Path) -> Dict:
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"notes": []}


def save_notes(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def set_note(
    notes_path: Path,
    wrestler_id: str,
    name: str,
    team: str,
    note: str,
    overwrite: bool = True,
) -> bool:
    """
    Insert or update a placement note for a wrestler.
    
    Args:
        notes_path: Path to placement_notes.json
        wrestler_id: Wrestler ID
        name: Wrestler name
        team: Team name
        note: Placement note to set
        overwrite: If False, don't overwrite existing notes
        
    Returns:
        True if note was set/updated, False if skipped (existing note and overwrite=False)
    """
    data = load_notes(notes_path)
    notes = data.setdefault("notes", [])

    updated = False
    for entry in notes:
        if entry.get("wrestler_id") == wrestler_id:
            # If overwrite is False and note already exists, skip
            if not overwrite and entry.get("note"):
                return False
            entry["note"] = note
            entry["name"] = name
            entry["team"] = team
            updated = True
            break

    if not updated:
        notes.append(
            {
                "wrestler_id": wrestler_id,
                "name": name,
                "team": team,
                "note": note,
            }
        )

    save_notes(notes_path, data)
    return True


def build_note_lookup(data: Dict) -> Dict[str, str]:
    """Return wrestler_id -> note mapping from raw notes data."""
    lookup: Dict[str, str] = {}
    for entry in data.get("notes", []):
        wid = entry.get("wrestler_id")
        note = str(entry.get("note", "")).strip().upper()
        if wid and note:
            lookup[wid] = note
    return lookup


def parse_bloodround_line(line: str, round_number: int = 4) -> Optional[Tuple[str, str]]:
    """
    Parse a bloodround file line to extract loser name and team.
    
    Format: "Cons. Round X - Winner Name (Winner Team) X-Y won by ... over Loser Name (Loser Team) X-Y (...)"
    
    Args:
        line: Line from bloodround file
        round_number: Round number to match (4 for boys, 2 for girls)
    
    Returns:
        Tuple of (loser_name, loser_team) or None if line doesn't match format
    """
    line = line.strip()
    expected_prefix = f"Cons. Round {round_number}"
    if not line.startswith(expected_prefix):
        return None
    
    # Pattern: "over Loser Name (Loser Team)"
    # Match "over" followed by name, then team in parentheses
    pattern = r'over\s+([^(]+)\s+\(([^)]+)\)'
    match = re.search(pattern, line)
    
    if not match:
        return None
    
    loser_name = match.group(1).strip()
    loser_team = match.group(2).strip()
    
    return (loser_name, loser_team)


def parse_firstround_line(line: str) -> Optional[Tuple[Tuple[str, str], Tuple[str, str]]]:
    """
    Parse a firstround file line to extract both winner and loser names and teams.
    
    Format: "Champ. Round 1 - Winner Name (Winner Team) X-Y won by ... over Loser Name (Loser Team) X-Y (...)"
    
    Returns:
        Tuple of ((winner_name, winner_team), (loser_name, loser_team)) or None if line doesn't match format
    """
    line = line.strip()
    if not line.startswith("Champ. Round 1"):
        return None
    
    # Pattern: "Champ. Round 1 - Winner Name (Winner Team) ... over Loser Name (Loser Team)"
    # Extract winner: everything after "Champ. Round 1 - " until " won by"
    # Extract loser: everything after "over " until the next " ("
    winner_pattern = r'Champ\. Round 1\s+-\s+([^(]+)\s+\(([^)]+)\)'
    loser_pattern = r'over\s+([^(]+)\s+\(([^)]+)\)'
    
    winner_match = re.search(winner_pattern, line)
    loser_match = re.search(loser_pattern, line)
    
    if not winner_match or not loser_match:
        return None
    
    winner_name = winner_match.group(1).strip()
    winner_team = winner_match.group(2).strip()
    loser_name = loser_match.group(1).strip()
    loser_team = loser_match.group(2).strip()
    
    return ((winner_name, winner_team), (loser_name, loser_team))


def import_bloodround_file(
    file_path: Path,
    teams: List[Dict],
    notes_path: Path,
    note_lookup: Dict[str, str],
    round_number: int = 4
) -> List[Dict]:
    """
    Import bloodround file and apply "BR" placement notes to losers.
    
    Args:
        file_path: Path to bloodround.txt file
        teams: List of team data dictionaries
        notes_path: Path to placement_notes.json file
        note_lookup: Existing note lookup dictionary
        round_number: Round number to match (4 for boys, 2 for girls)
        
    Returns:
        List of wrestlers that got "BR" placement applied
    """
    if not file_path.exists():
        print(f"Bloodround file not found: {file_path}")
        return []
    
    # Build a lookup of wrestlers by exact name and team match
    wrestler_lookup: Dict[Tuple[str, str], Dict] = {}
    for team in teams:
        team_name = team.get("team_name", "Unknown")
        for wrestler in team.get("roster", []):
            wid = wrestler.get("season_wrestler_id")
            name = wrestler.get("name", "Unknown")
            if not wid or wid == "null":
                continue
            # Use exact name and team as key
            key = (name, team_name)
            wrestler_lookup[key] = {
                "wrestler_id": wid,
                "name": name,
                "team": team_name,
            }
    
    applied_wrestlers = []
    
    # Parse bloodround file
    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, start=1):
            result = parse_bloodround_line(line, round_number=round_number)
            if not result:
                continue
            
            loser_name, loser_team = result
            
            # Find exact match in current season's wrestlers
            key = (loser_name, loser_team)
            if key not in wrestler_lookup:
                # No exact match found - skip silently
                continue
            
            wrestler_info = wrestler_lookup[key]
            wid = wrestler_info["wrestler_id"]
            
            # Skip if wrestler already has a placement note
            if wid in note_lookup:
                continue
            
            # Apply "BR" placement note (don't overwrite existing notes)
            success = set_note(
                notes_path=notes_path,
                wrestler_id=wid,
                name=wrestler_info["name"],
                team=wrestler_info["team"],
                note="BR",
                overwrite=False,
            )
            
            if not success:
                continue
            
            # Update in-memory lookup
            note_lookup[wid] = "BR"
            
            applied_wrestlers.append(wrestler_info)
    
    return applied_wrestlers


def import_firstround_file(
    file_path: Path,
    teams: List[Dict],
    notes_path: Path,
    note_lookup: Dict[str, str]
) -> List[Dict]:
    """
    Import firstround file and apply "Q" placement notes to both winners and losers.
    
    Args:
        file_path: Path to firstround.txt file
        teams: List of team data dictionaries
        notes_path: Path to placement_notes.json file
        note_lookup: Existing note lookup dictionary
        
    Returns:
        List of wrestlers that got "Q" placement applied
    """
    if not file_path.exists():
        print(f"Firstround file not found: {file_path}")
        return []
    
    # Build a lookup of wrestlers by exact name and team match
    wrestler_lookup: Dict[Tuple[str, str], Dict] = {}
    for team in teams:
        team_name = team.get("team_name", "Unknown")
        for wrestler in team.get("roster", []):
            wid = wrestler.get("season_wrestler_id")
            name = wrestler.get("name", "Unknown")
            if not wid or wid == "null":
                continue
            # Use exact name and team as key
            key = (name, team_name)
            wrestler_lookup[key] = {
                "wrestler_id": wid,
                "name": name,
                "team": team_name,
            }
    
    applied_wrestlers = []
    
    # Parse firstround file
    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, start=1):
            result = parse_firstround_line(line)
            if not result:
                continue
            
            (winner_name, winner_team), (loser_name, loser_team) = result
            
            # Process winner
            winner_key = (winner_name, winner_team)
            if winner_key in wrestler_lookup:
                winner_info = wrestler_lookup[winner_key]
                wid = winner_info["wrestler_id"]
                
                # Skip if wrestler already has a placement note
                if wid not in note_lookup:
                    # Apply "Q" placement note
                    success = set_note(
                        notes_path=notes_path,
                        wrestler_id=wid,
                        name=winner_info["name"],
                        team=winner_info["team"],
                        note="Q",
                        overwrite=False,
                    )
                    
                    if success:
                        # Update in-memory lookup
                        note_lookup[wid] = "Q"
                        applied_wrestlers.append(winner_info)
            
            # Process loser
            loser_key = (loser_name, loser_team)
            if loser_key in wrestler_lookup:
                loser_info = wrestler_lookup[loser_key]
                wid = loser_info["wrestler_id"]
                
                # Skip if wrestler already has a placement note
                if wid not in note_lookup:
                    # Apply "Q" placement note
                    success = set_note(
                        notes_path=notes_path,
                        wrestler_id=wid,
                        name=loser_info["name"],
                        team=loser_info["team"],
                        note="Q",
                        overwrite=False,
                    )
                    
                    if success:
                        # Update in-memory lookup
                        note_lookup[wid] = "Q"
                        applied_wrestlers.append(loser_info)
    
    return applied_wrestlers


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Interactively add/edit placement notes for wrestlers."
    )
    parser.add_argument(
        "-season",
        type=int,
        required=True,
        help="Season year (e.g., 2026)",
    )
    parser.add_argument('-league', type=str, default='ncaa', choices=['ncaa', 'hs'],
                        help='League type: ncaa (default) or hs')
    parser.add_argument('-state', type=str, help='State code (required when league=hs, currently only KY supported)')
    parser.add_argument('-gender', type=str, choices=['boys', 'girls', 'men', 'women'],
                        help='Gender: boys/girls (HS) or men/women (NCAA)')
    parser.add_argument('-import-bloodround', action='store_true',
                        help='Import bloodround.txt file and apply BR placement notes (HS only)')
    parser.add_argument('-import-firstround', action='store_true',
                        help='Import firstround.txt file and apply Q placement notes (HS only)')

    args = parser.parse_args()

    if args.league == 'hs':
        if not args.state:
            raise ValueError("-state is required when -league=hs")
        if args.state.upper() != 'KY':
            raise ValueError(f"Only KY is currently supported for HS. Got: {args.state}")
        if not args.gender:
            raise ValueError("-gender is required when -league=hs")
        if args.gender not in ['boys', 'girls']:
            raise ValueError(f"-gender must be 'boys' or 'girls' for HS. Got: {args.gender}")
    else:  # ncaa
        if not args.gender:
            raise ValueError("-gender is required when -league=ncaa")
        if args.gender not in ['men', 'women']:
            raise ValueError(f"-gender must be 'men' or 'women' for NCAA. Got: {args.gender}")

    notes_path = Path("mt/rankings_data") / league_dir_key(args.league, args.gender, args.state) / str(args.season) / "placement_notes.json"

    # Load all teams once for faster interactive searching
    teams = load_team_data(args.season, league=args.league, state=args.state, gender=args.gender)

    # Preload existing notes for reference
    existing_data = load_notes(notes_path)
    note_lookup = build_note_lookup(existing_data)

    league_label = f"{args.league.upper()}" if args.league == 'ncaa' else f"{args.state} HS {args.gender.capitalize()}" if args.league == 'hs' else args.league
    
    # Handle bloodround import if requested (HS only)
    if args.import_bloodround:
        if args.league != 'hs':
            print("Error: -import-bloodround is only available for HS (use -league hs)")
            return
        
        # Determine bloodround file path
        # Handle case-insensitive directory name (hs_ky_girls vs hs_ky_GIRLS)
        gender_lower = args.gender.lower()
        bloodround_file = Path(f"data/hs_{args.state.lower()}_{gender_lower}/bloodround.txt")
        # Try uppercase variant if lowercase doesn't exist
        if not bloodround_file.exists():
            bloodround_file_upper = Path(f"data/hs_{args.state.lower()}_{args.gender.upper()}/bloodround.txt")
            if bloodround_file_upper.exists():
                bloodround_file = bloodround_file_upper
        
        # Determine round number: 2 for girls, 4 for boys
        round_number = 2 if args.gender.lower() == 'girls' else 4
        
        print(f"Importing bloodround file: {bloodround_file}")
        print(f"Applying 'BR' placement notes to wrestlers who lost in Cons. Round {round_number}...\n")
        
        applied = import_bloodround_file(bloodround_file, teams, notes_path, note_lookup, round_number=round_number)
        
        if applied:
            print(f"\n✓ Applied 'BR' placement note to {len(applied)} wrestler(s):")
            for w in applied:
                print(f"  - {w['name']} ({w['team']})")
        else:
            print("\nNo wrestlers matched from bloodround file.")
            print("(This could mean names/teams don't match exactly, or all wrestlers already have placement notes)")
        
        print("\nImport complete. Exiting.")
        return
    
    # Handle firstround import if requested (HS only)
    if args.import_firstround:
        if args.league != 'hs':
            print("Error: -import-firstround is only available for HS (use -league hs)")
            return
        
        # Determine firstround file path
        firstround_file = Path(f"data/hs_{args.state.lower()}_{args.gender}/firstround.txt")
        
        print(f"Importing firstround file: {firstround_file}")
        print("Applying 'Q' placement notes to wrestlers who wrestled in Champ. Round 1...\n")
        
        applied = import_firstround_file(firstround_file, teams, notes_path, note_lookup)
        
        if applied:
            print(f"\n✓ Applied 'Q' placement note to {len(applied)} wrestler(s):")
            for w in applied:
                print(f"  - {w['name']} ({w['team']})")
        else:
            print("\nNo wrestlers matched from firstround file.")
            print("(This could mean names/teams don't match exactly, or all wrestlers already have placement notes)")
        
        print("\nImport complete. Exiting.")
        return
    
    print(
        f"Interactive placement note tool for season {args.season} ({league_label}).\n"
        "Enter a name fragment to search (case-insensitive), or just press "
        "Enter to quit.\n"
        "Allowed notes: FR, 1-8, BR, Q\n"
    )

    while True:
        try:
            query = input("Name fragment (blank to quit): ").strip()
        except EOFError:
            break

        if not query:
            break

        results = search_wrestlers(teams, query)
        if not results:
            print("  No wrestlers found matching that fragment.\n")
            continue

        print(f"Found {len(results)} wrestlers:")
        for idx, r in enumerate(results, start=1):
            wid = r["wrestler_id"]
            existing_note = note_lookup.get(wid, "")
            note_str = f"  [current note: {existing_note}]" if existing_note else ""
            print(
                f"  {idx:>2}) ID={wid}  "
                f"{r['name']} ({r['team']}), "
                f"listed weight={r['weight_class']}{note_str}"
            )

        while True:
            sel = input(
                "Select wrestler number to edit placement note "
                "(blank to cancel this search): "
            ).strip()
            if not sel:
                print("  Search cancelled.\n")
                break
            try:
                idx = int(sel)
                if 1 <= idx <= len(results):
                    chosen = results[idx - 1]
                    break
            except ValueError:
                pass
            print("  Invalid selection, please enter a valid number.")

        if not sel:
            continue

        while True:
            note_input = input(
                "Enter placement note (FR, 1-8, BR, Q), or blank to cancel: "
            ).strip().upper()
            if not note_input:
                print("  No note entered; no changes made.\n")
                note = ""
                break
            if note_input in ALLOWED_NOTES:
                note = note_input
                break
            print("  Invalid note. Allowed values are: FR, 1-8, BR, Q.")

        if not note:
            continue

        set_note(
            notes_path=notes_path,
            wrestler_id=chosen["wrestler_id"],
            name=chosen["name"],
            team=chosen["team"],
            note=note,
        )

        # Update in-memory lookup so we show the new note in subsequent searches
        note_lookup[chosen["wrestler_id"]] = note

        today_str = date.today().strftime("%m/%d/%Y")
        print(
            f"  Set placement note for {chosen['name']} ({chosen['team']}), "
            f"ID={chosen['wrestler_id']}: {note}  [{today_str}]\n"
        )


if __name__ == "__main__":
    main()



