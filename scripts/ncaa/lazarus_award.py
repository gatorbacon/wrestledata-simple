#!/usr/bin/env python3
"""
Lazarus Award
-------------
Finds the highest-ranked wrestler who:
  1. Lost in the first round of the championship bracket (R32 or PIG)
  2. Came back through consolation to finish 3rd

If no one qualifies, falls back to the highest-ranked wrestler who:
  - Lost in R32/PIG and still finished in the top 8 (All-American)

Run from project root:
  python3 scripts/ncaa/iron_man.py [year]
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def load_data(year: int):
    matches_path = PROJECT_ROOT / "data" / str(year) / "ncaa-tourney" / "parsed" / "matches.json"
    wrestlers_path = PROJECT_ROOT / "data" / str(year) / "ncaa-tourney" / "parsed" / "wrestlers.json"

    if not matches_path.exists():
        # Fall back to combined historical file
        matches_path = PROJECT_ROOT / "data" / "ncaa-tourney-parsed" / "all_matches.json"
        wrestlers_path = PROJECT_ROOT / "data" / "ncaa-tourney-parsed" / "all_wrestlers.json"
        matches = [m for m in json.loads(matches_path.read_text()) if m["year"] == year]
        wrestlers = [w for w in json.loads(wrestlers_path.read_text()) if w["year"] == year]
    else:
        matches = json.loads(matches_path.read_text())
        wrestlers = json.loads(wrestlers_path.read_text())

    return matches, wrestlers


def iron_man(year: int):
    matches, wrestlers = load_data(year)

    # --- Step 1: find wrestlers who lost in their very first match ---
    # PIG losers are eliminated in pigtail; R32 losers lost in the true first round.
    # Both count as "lost in round 1" for this award.
    first_round_loss_rounds = {"R32", "PIG"}
    first_round_losers: set[tuple[str, int]] = set()  # (name, weight)
    for m in matches:
        if m["round"] in first_round_loss_rounds:
            first_round_losers.add((m["loser_name"], m["weight"]))

    # --- Step 2: find 3rd-place finishers among first-round losers ---
    candidates = [
        w for w in wrestlers
        if (w["name"], w["weight"]) in first_round_losers
        and w["placement"] == 3
    ]

    print(f"\n=== Iron Man Award — {year} NCAA Tournament ===\n")

    if candidates:
        # Highest ranked = lowest seed number (seed 1 is best)
        candidates.sort(key=lambda w: (w["seed"], w["weight"]))
        winner = candidates[0]

        print(f"WINNER: {winner['name']} ({winner['team']}) — {winner['weight']} lbs")
        print(f"  Seed:      #{winner['seed']}")
        print(f"  Placement: 3rd")
        print()

        if len(candidates) > 1:
            print("Other qualifiers (lost R1, finished 3rd):")
            for w in candidates[1:]:
                print(f"  #{w['seed']} {w['name']} ({w['team']}) — {w['weight']} lbs")
        else:
            print("(Only one wrestler qualified this year.)")
    else:
        # --- Fallback: highest-ranked first-round loser who made All-American (top 8) ---
        aa_candidates = [
            w for w in wrestlers
            if (w["name"], w["weight"]) in first_round_losers
            and isinstance(w["placement"], int)
            and 1 <= w["placement"] <= 8
        ]

        if aa_candidates:
            aa_candidates.sort(key=lambda w: (w["seed"], w["placement"], w["weight"]))
            print("No wrestler lost in round 1 AND finished 3rd this year.")
            print("\nFallback — highest-ranked first-round loser who earned All-American status:\n")
            winner = aa_candidates[0]
            print(f"WINNER: {winner['name']} ({winner['team']}) — {winner['weight']} lbs")
            print(f"  Seed:      #{winner['seed']}")
            print(f"  Placement: {winner['placement']}")
            print()
            if len(aa_candidates) > 1:
                print("Other All-American first-round losers:")
                for w in aa_candidates[1:]:
                    print(f"  #{w['seed']} {w['name']} ({w['team']}) — {w['weight']} lbs, placed {w['placement']}")
        else:
            print("No first-round losers achieved All-American status this year.")

    # --- Always show: full list of first-round losers who placed 3rd ---
    print("\n--- All first-round losers who finished 3rd ---")
    thirds = [
        w for w in wrestlers
        if (w["name"], w["weight"]) in first_round_losers
        and w["placement"] == 3
    ]
    if thirds:
        thirds.sort(key=lambda w: w["weight"])
        for w in thirds:
            print(f"  {w['weight']} lbs: #{w['seed']} {w['name']} ({w['team']})")
    else:
        print("  None.")

    # --- Debug: show all first-round losers and their current placements ---
    print("\n--- All first-round losers and their placements ---")
    losers_with_placement = [
        w for w in wrestlers
        if (w["name"], w["weight"]) in first_round_losers
    ]
    losers_with_placement.sort(key=lambda w: (w["seed"], w["weight"]))
    for w in losers_with_placement:
        place = w["placement"] if w["placement"] else "still alive / unknown"
        print(f"  #{w['seed']:2d} {w['name']:<25} ({w['team']:<20}) {w['weight']} lbs — placed {place}")


if __name__ == "__main__":
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    iron_man(year)
