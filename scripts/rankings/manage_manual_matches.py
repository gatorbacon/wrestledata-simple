#!/usr/bin/env python3
"""
Manage manual head-to-head match overrides for rankings.

This script allows operators to add/remove manual match entries that influence
rankings but do NOT contaminate scraped data, profiles, or historical records.

Manual matches are ONLY used in the rankings matrix and are automatically
ignored once a real TrackWrestling match exists between the same two wrestlers.
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime


def load_manual_matches(season: int, data_dir: str = "mt/rankings_data", 
                       league: str = 'hs', state: str = None, gender: str = None) -> List[Dict]:
    """Load manual matches from JSON file."""
    if league == 'hs' and state and gender:
        # HS path format: hs_{state}_{gender}/{season}
        manual_file = Path(data_dir) / f"hs_{state}_{gender}" / str(season) / "manual_matches.json"
    else:
        manual_file = Path(data_dir) / str(season) / "manual_matches.json"
    
    if not manual_file.exists():
        return []
    
    try:
        with manual_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("manual_matches", [])
    except Exception as e:
        print(f"Error loading manual matches: {e}")
        return []


def save_manual_matches(manual_matches: List[Dict], season: int, 
                       data_dir: str = "mt/rankings_data", league: str = 'hs', 
                       state: str = None, gender: str = None) -> None:
    """Save manual matches to JSON file."""
    if league == 'hs' and state and gender:
        # HS path format: hs_{state}_{gender}/{season}
        manual_file = Path(data_dir) / f"hs_{state}_{gender}" / str(season) / "manual_matches.json"
    else:
        manual_file = Path(data_dir) / str(season) / "manual_matches.json"
    
    manual_file.parent.mkdir(parents=True, exist_ok=True)
    
    data = {
        "version": "1.0",
        "description": "Manual head-to-head match overrides for rankings only. These do NOT appear in profiles or historical data.",
        "manual_matches": manual_matches
    }
    
    with manual_file.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"Saved {len(manual_matches)} manual match(es) to {manual_file}")


def search_wrestlers(query: str, season: int, data_dir: str = "mt/rankings_data",
                    league: str = 'hs', state: str = None, gender: str = None) -> List[Dict]:
    """Search wrestlers by partial name match."""
    query_lower = query.lower()
    matches = []
    
    # Load weight class data to find wrestlers
    if league == 'hs' and state and gender:
        # HS path format: hs_{state}_{gender}/{season}
        weight_dir = Path(data_dir) / f"hs_{state}_{gender}" / str(season)
    else:
        weight_dir = Path(data_dir) / str(season)
    
    if not weight_dir.exists():
        return matches
    
    # Search through all weight class files
    for weight_file in weight_dir.glob("weight_class_*.json"):
        try:
            with weight_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            
            wrestlers = data.get("wrestlers", {})
            for wrestler_id, wrestler_info in wrestlers.items():
                name = wrestler_info.get("name", "")
                if query_lower in name.lower():
                    matches.append({
                        "id": wrestler_id,
                        "name": name,
                        "team": wrestler_info.get("team", "Unknown"),
                        "weight_class": wrestler_info.get("weight_class", ""),
                        "wins": wrestler_info.get("wins", 0),
                        "losses": wrestler_info.get("losses", 0)
                    })
        except Exception as e:
            print(f"Warning: Error reading {weight_file}: {e}")
            continue
    
    # Sort by name for easier selection
    matches.sort(key=lambda x: x["name"])
    return matches


def display_wrestler_list(wrestlers: List[Dict]) -> None:
    """Display list of wrestlers for selection."""
    if not wrestlers:
        print("No wrestlers found.")
        return
    
    print(f"\nFound {len(wrestlers)} wrestler(s):")
    print("-" * 80)
    for i, w in enumerate(wrestlers, 1):
        record = f"{w['wins']}-{w['losses']}" if w.get('wins', 0) > 0 or w.get('losses', 0) > 0 else "N/A"
        print(f"{i:3d}. {w['name']:30s} | {w['team']:25s} | {w['weight_class']:>4s} | {record:>6s} | ID: {w['id']}")
    print("-" * 80)


def select_wrestler(wrestlers: List[Dict], prompt: str) -> Optional[Dict]:
    """Prompt user to select a wrestler from list."""
    if not wrestlers:
        return None
    
    while True:
        try:
            choice = input(f"\n{prompt} (1-{len(wrestlers)}, or 'q' to cancel): ").strip()
            if choice.lower() == 'q':
                return None
            idx = int(choice) - 1
            if 0 <= idx < len(wrestlers):
                return wrestlers[idx]
            else:
                print(f"Please enter a number between 1 and {len(wrestlers)}")
        except ValueError:
            print("Please enter a valid number or 'q' to cancel")
        except KeyboardInterrupt:
            print("\nCancelled.")
            return None


def add_manual_match(season: int, data_dir: str = "mt/rankings_data",
                    league: str = 'hs', state: str = None, gender: str = None) -> None:
    """Interactive function to add a manual match entry."""
    print("\n=== Add Manual Match Override ===")
    print("This will add a head-to-head result that influences rankings only.")
    print("It will be automatically ignored if a real TrackWrestling match exists.\n")
    
    # Search for winner
    winner_query = input("Search for WINNING wrestler (name or partial): ").strip()
    if not winner_query:
        print("Cancelled.")
        return
    
    winner_matches = search_wrestlers(winner_query, season, data_dir, league, state, gender)
    if not winner_matches:
        print(f"No wrestlers found matching '{winner_query}'")
        return
    
    display_wrestler_list(winner_matches)
    winner = select_wrestler(winner_matches, "Select WINNING wrestler")
    if not winner:
        print("Cancelled.")
        return
    
    # Search for loser
    loser_query = input("\nSearch for LOSING wrestler (name or partial): ").strip()
    if not loser_query:
        print("Cancelled.")
        return
    
    loser_matches = search_wrestlers(loser_query, season, data_dir, league, state, gender)
    if not loser_matches:
        print(f"No wrestlers found matching '{loser_query}'")
        return
    
    display_wrestler_list(loser_matches)
    loser = select_wrestler(loser_matches, "Select LOSING wrestler")
    if not loser:
        print("Cancelled.")
        return
    
    # Validate they're different
    if winner["id"] == loser["id"]:
        print("Error: Winner and loser cannot be the same wrestler.")
        return
    
    # Optional fields
    date = input("\nDate (optional, e.g., '01/15/2026' or press Enter to skip): ").strip()
    note = input("Note/source (optional, e.g., 'Dual meet, not entered in TrackWrestling' or press Enter to skip): ").strip()
    
    # Create entry
    entry = {
        "winner_id": winner["id"],
        "loser_id": loser["id"],
        "date": date if date else None,
        "note": note if note else None,
        "added_date": datetime.now().isoformat(),
        "added_by": "manual_entry_script"
    }
    
    # Load existing entries
    existing = load_manual_matches(season, data_dir, league, state, gender)
    
    # Check for duplicates (same winner/loser pair)
    pair_key = tuple(sorted([winner["id"], loser["id"]]))
    for existing_entry in existing:
        existing_pair = tuple(sorted([existing_entry["winner_id"], existing_entry["loser_id"]]))
        if existing_pair == pair_key:
            print(f"\nWarning: A manual match already exists between these two wrestlers.")
            print(f"  Existing: {existing_entry.get('note', 'No note')}")
            overwrite = input("Overwrite? (y/n): ").strip().lower()
            if overwrite == 'y':
                existing.remove(existing_entry)
                break
            else:
                print("Cancelled.")
                return
    
    # Add new entry
    existing.append(entry)
    save_manual_matches(existing, season, data_dir, league, state, gender)
    
    print(f"\n✅ Added manual match: {winner['name']} beat {loser['name']}")
    print(f"   This will appear as 'M' in the rankings matrix.")


def list_manual_matches(season: int, data_dir: str = "mt/rankings_data",
                       league: str = 'hs', state: str = None, gender: str = None) -> None:
    """List all manual match entries."""
    matches = load_manual_matches(season, data_dir, league, state, gender)
    
    if not matches:
        print(f"\nNo manual matches found for season {season}.")
        return
    
    print(f"\n=== Manual Matches for Season {season} ===")
    print(f"Total: {len(matches)}")
    print("-" * 100)
    
    for i, match in enumerate(matches, 1):
        winner_id = match.get("winner_id", "?")
        loser_id = match.get("loser_id", "?")
        date = match.get("date") or "N/A"
        note = match.get("note") or ""
        added = match.get("added_date") or ""
        
        print(f"{i:3d}. Winner: {winner_id:20s} | Loser: {loser_id:20s} | Date: {date:12s}")
        if note:
            print(f"     Note: {note}")
        if added:
            print(f"     Added: {added}")
        print()


def delete_manual_match(season: int, data_dir: str = "mt/rankings_data",
                       league: str = 'hs', state: str = None, gender: str = None) -> None:
    """Interactive function to delete a manual match entry."""
    matches = load_manual_matches(season, data_dir, league, state, gender)
    
    if not matches:
        print(f"\nNo manual matches found for season {season}.")
        return
    
    print(f"\n=== Delete Manual Match ===")
    list_manual_matches(season, data_dir, league, state, gender)
    
    try:
        choice = input(f"\nSelect match to delete (1-{len(matches)}, or 'q' to cancel): ").strip()
        if choice.lower() == 'q':
            print("Cancelled.")
            return
        
        idx = int(choice) - 1
        if 0 <= idx < len(matches):
            deleted = matches.pop(idx)
            save_manual_matches(matches, season, data_dir, league, state, gender)
            print(f"\n✅ Deleted manual match: {deleted.get('winner_id')} beat {deleted.get('loser_id')}")
        else:
            print(f"Please enter a number between 1 and {len(matches)}")
    except ValueError:
        print("Please enter a valid number or 'q' to cancel")
    except KeyboardInterrupt:
        print("\nCancelled.")


def main():
    parser = argparse.ArgumentParser(description="Manage manual head-to-head match overrides for rankings")
    parser.add_argument("-season", type=int, required=True, help="Season year")
    parser.add_argument("-action", choices=["add", "list", "delete"], required=True,
                       help="Action to perform")
    parser.add_argument("-data_dir", type=str, default="mt/rankings_data",
                       help="Data directory (default: mt/rankings_data)")
    parser.add_argument("-league", type=str, default="hs", choices=["hs", "ncaa"],
                       help="League type (default: hs)")
    parser.add_argument("-state", type=str, help="State code (required for HS)")
    parser.add_argument("-gender", type=str, choices=["boys", "girls"], help="Gender (required for HS)")
    
    args = parser.parse_args()
    
    if args.league == 'hs' and (not args.state or not args.gender):
        parser.error("--state and --gender are required for HS league")
    
    if args.action == "add":
        add_manual_match(args.season, args.data_dir, args.league, args.state, args.gender)
    elif args.action == "list":
        list_manual_matches(args.season, args.data_dir, args.league, args.state, args.gender)
    elif args.action == "delete":
        delete_manual_match(args.season, args.data_dir, args.league, args.state, args.gender)


if __name__ == "__main__":
    main()

