#!/usr/bin/env python3
"""
Manage manual match result overrides.

These overrides allow you to replace scraped match results with custom results
that will be used in ranking calculations and scoring stats.

File format (mt/rankings_data/{season}/match_overrides.json):
{
  "overrides": [
    {
      "wrestler1_id": "12345",
      "wrestler2_id": "67890",
      "date": "11/20/2025",
      "winner_id": "12345",
      "result": "Dec 5-3",
      "weight_class": "141",
      "event": "Dual Meet",
      "note": "Override: original result was incorrect"
    },
    ...
  ]
}

The override system works by:
1. Matching overrides to actual matches using (wrestler1_id, wrestler2_id, date)
2. Replacing the winner_id and result fields when matches are loaded
3. Applied before deduplication, so the override takes precedence

Usage:
  python scripts/rankings/manage_match_overrides.py -season 2026
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime


def league_dir_key(league, gender, state=None):
    if league == 'hs':
        return f"hs_{state.lower()}_{gender}"
    return f"ncaa_{gender}"


def load_overrides(season: int, data_dir: str = "mt/rankings_data") -> Dict:
    """Load match overrides for a season."""
    overrides_path = Path(data_dir) / str(season) / "match_overrides.json"
    if overrides_path.exists():
        with overrides_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {"overrides": []}


def save_overrides(season: int, data: Dict, data_dir: str = "mt/rankings_data") -> None:
    """Save match overrides for a season."""
    overrides_path = Path(data_dir) / str(season) / "match_overrides.json"
    overrides_path.parent.mkdir(parents=True, exist_ok=True)
    with overrides_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Saved overrides to {overrides_path}")


def normalize_wrestler_ids(w1_id: str, w2_id: str) -> tuple[str, str]:
    """Normalize wrestler IDs (smaller ID first) to match deduplication logic."""
    return tuple(sorted([w1_id, w2_id]))


def load_all_wrestlers(season: int, data_dir: str = "mt/rankings_data") -> Dict[str, Dict]:
    """
    Load all wrestlers from weight_class_*.json files.
    Returns dict mapping wrestler_id -> {name, team, weight_class}
    """
    wrestlers = {}
    data_path = Path(data_dir) / str(season)
    
    for wc_file in sorted(data_path.glob("weight_class_*.json")):
        try:
            with wc_file.open("r", encoding="utf-8") as f:
                wc_data = json.load(f)
        except Exception:
            continue
        
        weight_class = wc_file.stem.replace("weight_class_", "")
        
        for wid, winfo in wc_data.get("wrestlers", {}).items():
            if wid not in wrestlers:
                wrestlers[wid] = {
                    "wrestler_id": wid,
                    "name": winfo.get("name", "Unknown"),
                    "team": winfo.get("team", "Unknown"),
                    "weight_class": weight_class,
                }
    return wrestlers


def search_wrestlers_by_name(
    wrestlers: Dict[str, Dict], query: str
) -> List[Dict]:
    """
    Search for wrestlers by name (case-insensitive partial match).
    Returns list of wrestler dicts sorted by name.
    """
    query_lower = query.lower()
    results = []
    
    for wid, winfo in wrestlers.items():
        name = winfo.get("name", "")
        if query_lower in name.lower():
            results.append(winfo)
    
    # Sort by name
    results.sort(key=lambda x: x.get("name", ""))
    return results


def select_wrestler_interactive(
    wrestlers: Dict[str, Dict], prompt: str = "Search for wrestler"
) -> Optional[str]:
    """
    Interactively search for and select a wrestler by name.
    Returns wrestler_id or None if cancelled.
    """
    while True:
        query = input(f"{prompt} (or 'q' to cancel): ").strip()
        
        if query.lower() == 'q':
            return None
        
        if not query:
            print("Please enter a search term.")
            continue
        
        matches = search_wrestlers_by_name(wrestlers, query)
        
        if not matches:
            print(f"No wrestlers found matching '{query}'")
            continue
        
        if len(matches) == 1:
            w = matches[0]
            print(f"\nSelected: {w['name']} ({w['team']}) - ID: {w['wrestler_id']}")
            return w['wrestler_id']
        
        # Multiple matches - show list
        print(f"\nFound {len(matches)} wrestlers matching '{query}':")
        for idx, w in enumerate(matches, start=1):
            print(f"{idx}. {w['name']:<30} {w['team']:<25} {w.get('weight_class', '?')}")
        
        while True:
            choice = input(f"\nSelect wrestler (1-{len(matches)}) or 'q' to cancel: ").strip()
            
            if choice.lower() == 'q':
                return None
            
            if choice.isdigit():
                idx = int(choice)
                if 1 <= idx <= len(matches):
                    w = matches[idx - 1]
                    print(f"Selected: {w['name']} ({w['team']}) - ID: {w['wrestler_id']}")
                    return w['wrestler_id']
            
            print(f"Please enter a number between 1 and {len(matches)}")


def find_matching_matches(
    w1_id: str, w2_id: str, date: str, season: int, data_dir: str = "mt/rankings_data"
) -> List[Dict]:
    """
    Find actual matches that would match an override.
    Searches through weight_class_*.json files.
    """
    matches = []
    data_path = Path(data_dir) / str(season)
    
    # Normalize IDs for matching
    w1_norm, w2_norm = normalize_wrestler_ids(w1_id, w2_id)
    
    for wc_file in sorted(data_path.glob("weight_class_*.json")):
        try:
            with wc_file.open("r", encoding="utf-8") as f:
                wc_data = json.load(f)
        except Exception:
            continue
        
        for match in wc_data.get("matches", []):
            m_w1 = match.get("wrestler1_id")
            m_w2 = match.get("wrestler2_id")
            m_date = match.get("date", "")
            
            if not m_w1 or not m_w2:
                continue
            
            m_w1_norm, m_w2_norm = normalize_wrestler_ids(m_w1, m_w2)
            
            # Match on normalized IDs and date
            if m_w1_norm == w1_norm and m_w2_norm == w2_norm and m_date == date:
                matches.append({
                    **match,
                    "weight_class": wc_file.stem.replace("weight_class_", ""),
                    "source_file": str(wc_file)
                })
    
    return matches


def add_override(
    season: int,
    w1_id: str,
    w2_id: str,
    date: str,
    winner_id: str,
    result: str,
    weight_class: Optional[str] = None,
    event: Optional[str] = None,
    note: Optional[str] = None,
    data_dir: str = "mt/rankings_data"
) -> None:
    """Add a match override."""
    data = load_overrides(season, data_dir)
    overrides = data.setdefault("overrides", [])
    
    # Normalize IDs
    w1_norm, w2_norm = normalize_wrestler_ids(w1_id, w2_id)
    
    override = {
        "wrestler1_id": w1_norm,
        "wrestler2_id": w2_norm,
        "date": date,
        "winner_id": winner_id,
        "result": result,
    }
    
    if weight_class:
        override["weight_class"] = weight_class
    if event:
        override["event"] = event
    if note:
        override["note"] = note
    
    # Check if override already exists
    for existing in overrides:
        if (existing.get("wrestler1_id") == w1_norm and
            existing.get("wrestler2_id") == w2_norm and
            existing.get("date") == date):
            print(f"Override already exists for this match. Updating...")
            existing.update(override)
            save_overrides(season, data, data_dir)
            return
    
    overrides.append(override)
    save_overrides(season, data, data_dir)
    print(f"Added override: {w1_norm} vs {w2_norm} on {date}")


def list_overrides(season: int, data_dir: str = "mt/rankings_data") -> None:
    """List all match overrides for a season."""
    data = load_overrides(season, data_dir)
    overrides = data.get("overrides", [])
    
    if not overrides:
        print(f"No match overrides found for season {season}")
        return
    
    # Load wrestler data to show names
    wrestlers = load_all_wrestlers(season, data_dir)
    
    def get_wrestler_name(wid: str) -> str:
        if wid in wrestlers:
            w = wrestlers[wid]
            return f"{w['name']} ({w['team']})"
        return wid
    
    print(f"\nMatch Overrides for Season {season}:")
    print("=" * 80)
    for idx, ov in enumerate(overrides, start=1):
        w1_id = ov.get("wrestler1_id", "?")
        w2_id = ov.get("wrestler2_id", "?")
        date = ov.get("date", "?")
        winner_id = ov.get("winner_id", "?")
        result = ov.get("result", "?")
        weight = ov.get("weight_class", "?")
        note = ov.get("note", "")
        
        w1_name = get_wrestler_name(w1_id) if w1_id != "?" else "?"
        w2_name = get_wrestler_name(w2_id) if w2_id != "?" else "?"
        winner_name = get_wrestler_name(winner_id) if winner_id != "?" else "?"
        
        print(f"{idx}. {w1_name}")
        print(f"   vs {w2_name}")
        print(f"   Date: {date}, Weight: {weight}")
        print(f"   Winner: {winner_name} ({winner_id})")
        print(f"   Result: {result}")
        if note:
            print(f"   Note: {note}")
        print()


def remove_override(season: int, index: int, data_dir: str = "mt/rankings_data") -> None:
    """Remove a match override by index (from list display)."""
    data = load_overrides(season, data_dir)
    overrides = data.get("overrides", [])
    
    if 1 <= index <= len(overrides):
        removed = overrides.pop(index - 1)
        save_overrides(season, data, data_dir)
        print(f"Removed override: {removed.get('wrestler1_id')} vs {removed.get('wrestler2_id')} on {removed.get('date')}")
    else:
        print(f"Invalid index. Please use 1-{len(overrides)}")


def interactive_add_override(season: int, data_dir: str = "mt/rankings_data") -> None:
    """Interactively add a match override."""
    print("\nAdd Match Override")
    print("-" * 40)
    
    # Load all wrestlers for name-based search
    print("Loading wrestler data...")
    wrestlers = load_all_wrestlers(season, data_dir)
    
    if not wrestlers:
        print(f"Warning: No wrestler data found. You can still enter IDs manually.")
        w1_id = input("Wrestler 1 ID: ").strip()
        if not w1_id:
            print("Cancelled.")
            return
        w2_id = input("Wrestler 2 ID: ").strip()
        if not w2_id:
            print("Cancelled.")
            return
    else:
        # Search for wrestler 1
        w1_id = select_wrestler_interactive(wrestlers, "Search for Wrestler 1")
        if not w1_id:
            print("Cancelled.")
            return
        
        # Search for wrestler 2
        w2_id = select_wrestler_interactive(wrestlers, "Search for Wrestler 2")
        if not w2_id:
            print("Cancelled.")
            return
    
    # Get date
    date = input("Match date (MM/DD/YYYY): ").strip()
    if not date:
        print("Cancelled.")
        return
    
    # Find matching matches
    matches = find_matching_matches(w1_id, w2_id, date, season, data_dir)
    if matches:
        print(f"\nFound {len(matches)} matching match(es):")
        for idx, m in enumerate(matches, start=1):
            print(f"{idx}. Weight: {m.get('weight_class', '?')}, "
                  f"Original Winner: {m.get('winner_id', '?')}, "
                  f"Original Result: {m.get('result', '?')}")
        
        if len(matches) == 1:
            match = matches[0]
            weight_class = match.get("weight_class")
            event = match.get("event", "")
        else:
            choice = input(f"\nSelect match (1-{len(matches)}) or press Enter to use first: ").strip()
            if choice and choice.isdigit() and 1 <= int(choice) <= len(matches):
                match = matches[int(choice) - 1]
            else:
                match = matches[0]
            weight_class = match.get("weight_class")
            event = match.get("event", "")
    else:
        print("\nNo matching matches found. You can still create an override.")
        weight_class = input("Weight class (optional): ").strip() or None
        event = input("Event (optional): ").strip() or None
    
    # Get override details - winner
    if wrestlers:
        winner_id = select_wrestler_interactive(wrestlers, "Search for Winner")
        if not winner_id:
            print("Cancelled.")
            return
    else:
        winner_id = input("Winner ID: ").strip()
        if not winner_id:
            print("Cancelled.")
            return
    
    result = input("Result (e.g., 'Dec 5-3', 'Fall 2:30', 'TF 18-2'): ").strip()
    if not result:
        print("Cancelled.")
        return
    
    note = input("Note (optional): ").strip() or None
    
    add_override(
        season, w1_id, w2_id, date, winner_id, result,
        weight_class=weight_class, event=event, note=note, data_dir=data_dir
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage match result overrides for ranking calculations"
    )
    parser.add_argument(
        "-season",
        type=int,
        required=True,
        help="Season year (e.g., 2026)"
    )
    parser.add_argument(
        "-data-dir",
        default="mt/rankings_data",
        help="Directory containing rankings data"
    )
    parser.add_argument('-league', type=str, default='ncaa', choices=['ncaa', 'hs'],
                        help='League type: ncaa (default) or hs')
    parser.add_argument('-state', type=str, help='State code (required when league=hs)')
    parser.add_argument('-gender', type=str, choices=['boys', 'girls', 'men', 'women'],
                        help='Gender: boys/girls (HS) or men/women (NCAA)')
    parser.add_argument(
        "-list",
        action="store_true",
        help="List all overrides"
    )
    parser.add_argument(
        "-remove",
        type=int,
        help="Remove override by index (use with -list to see indices)"
    )
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

    # Bake league/gender into data_dir so all internal functions work unchanged
    data_dir = str(Path(args.data_dir) / league_dir_key(args.league, args.gender, args.state))

    if args.list:
        list_overrides(args.season, data_dir)
        return

    if args.remove:
        remove_override(args.season, args.remove, data_dir)
        return

    # Interactive mode
    while True:
        print(f"\nMatch Override Manager - Season {args.season}")
        print("1. List overrides")
        print("2. Add override")
        print("3. Remove override")
        print("4. Quit")
        
        choice = input("\nChoice: ").strip()
        
        if choice == "1":
            list_overrides(args.season, data_dir)
        elif choice == "2":
            interactive_add_override(args.season, data_dir)
        elif choice == "3":
            list_overrides(args.season, data_dir)
            idx_str = input("\nEnter index to remove (or 'q' to cancel): ").strip()
            if idx_str.lower() != 'q' and idx_str.isdigit():
                remove_override(args.season, int(idx_str), data_dir)
        elif choice == "4" or choice.lower() == "q":
            break
        else:
            print("Invalid choice.")


if __name__ == "__main__":
    main()

