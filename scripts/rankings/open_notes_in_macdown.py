#!/usr/bin/env python3
"""
open_notes_in_macdown.py

Opens all weight class notes markdown files for a specific rankings drop in MacDown.

Usage:
    python scripts/rankings/open_notes_in_macdown.py -gender boys -season 2026 -drop-id 2026-01-02
    python scripts/rankings/open_notes_in_macdown.py -gender girls -season 2026 -drop-id 2026-01-02
"""

import argparse
import subprocess
from pathlib import Path


# Weight classes for each gender
BOYS_WEIGHTS = [106, 113, 120, 126, 132, 138, 144, 150, 157, 165, 175, 190, 215, 285]
GIRLS_WEIGHTS = [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235]


def open_notes_in_macdown(gender: str, season: int, drop_id: str) -> None:
    """
    Open all weight class notes files for a specific drop in MacDown.
    
    Args:
        gender: 'boys' or 'girls'
        season: Season year (e.g., 2026)
        drop_id: Drop identifier (e.g., '2026-01-02')
    """
    # Determine weight classes based on gender
    if gender == 'boys':
        weights = BOYS_WEIGHTS
    elif gender == 'girls':
        weights = GIRLS_WEIGHTS
    else:
        raise ValueError(f"Invalid gender: {gender}. Must be 'boys' or 'girls'")
    
    # Construct base path
    archive_base = Path("frontend/hs-ky-ui/public/data/rankings")
    notes_dir = archive_base / gender / str(season) / drop_id / "notes"
    
    if not notes_dir.exists():
        print(f"Error: Notes directory not found: {notes_dir}")
        print(f"  Make sure the drop exists and has a notes/ subdirectory")
        return
    
    # Collect all note files
    note_files = []
    missing_files = []
    
    for weight in weights:
        note_file = notes_dir / f"{weight}.md"
        if note_file.exists():
            note_files.append(note_file)
        else:
            missing_files.append(weight)
    
    if not note_files:
        print(f"No note files found in {notes_dir}")
        if missing_files:
            print(f"Expected files for weights: {weights}")
        return
    
    # Report status
    print(f"Opening {len(note_files)} note file(s) in MacDown...")
    if missing_files:
        print(f"Warning: Missing files for weights: {missing_files}")
    
    # Open each file in MacDown
    for note_file in note_files:
        try:
            # Use 'open -a MacDown' to open file in MacDown app
            subprocess.run(['open', '-a', 'MacDown', str(note_file)], check=True)
            print(f"✓ Opened {note_file.name}")
        except subprocess.CalledProcessError as e:
            print(f"✗ Error opening {note_file.name}: {e}")
        except FileNotFoundError:
            print(f"✗ Error: MacDown not found. Is it installed?")
            print(f"  You can install MacDown from: https://macdown.uranusjr.com/")
            return
    
    print(f"\n✓ Opened {len(note_files)} file(s) in MacDown")


def main():
    parser = argparse.ArgumentParser(
        description="Open all weight class notes files for a rankings drop in MacDown"
    )
    parser.add_argument(
        '-gender',
        required=True,
        choices=['boys', 'girls'],
        help="Gender ('boys' or 'girls')"
    )
    parser.add_argument(
        '-season',
        type=int,
        required=True,
        help="Season year (e.g., 2026)"
    )
    parser.add_argument(
        '-drop-id',
        required=True,
        help="Drop identifier (e.g., '2026-01-02')"
    )
    
    args = parser.parse_args()
    
    open_notes_in_macdown(args.gender, args.season, args.drop_id)


if __name__ == "__main__":
    main()

