#!/usr/bin/env python3
"""
Analyze 2025 NCAA Tournament seeds: avg placement, std placement, avg points, std points per seed.

Uses wrestler_placements.json for placement data and parses results.txt to compute
advancement + placement + bonus points per wrestler.

Expects 33 seeds with 10 samples each (1 per weight class).
"""

import json
import re
import statistics
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PARSED_DIR = PROJECT_ROOT / "data" / "2025" / "ncaa-tourney" / "parsed"
RESULTS_FILE = PROJECT_ROOT / "data" / "2025" / "ncaa-tourney" / "results.txt"

# NCAA placement points (1st-8th only)
PLACEMENT_POINTS = {1: 16, 2: 12, 3: 10, 4: 9, 5: 7, 6: 6, 7: 4, 8: 3}

# Bonus points by result type
BONUS_POINTS = {"fall": 2.0, "tf": 1.5, "md": 1.0, "dec": 0.0, "sv": 0.0, "tb": 0.0}

# Champ rounds (advancement 1.0): R32, R16, QF, SF
CHAMP_ROUNDS = ("champ. round 1", "champ. round 2", "champ round 2", "round 1 (32 man)",
                "quarters", "quarterfinal", "semis (32 man)", "semifinal")

# Consol rounds (advancement 0.5)
CONSOL_ROUNDS = ("consolation pig tails", "prelim", "pig tails", "cons. round 1",
                 "cons. round 2", "cons. round 3", "cons. round 4", "cons. round 5",
                 "cons. semis (32 man)", "cons. semi")

MATCH_PATTERN = re.compile(
    r"(.+?)\s+\(([^)]+)\)\s+\d+-\d+\s+won\s+.+?\s+over\s+(.+?)\s+\(([^)]+)\)\s+\d+-\d+"
)


def _bonus_from_result(result_str: str) -> float:
    """Extract bonus points from result string like (Fall 6:18) or (MD 18-5)."""
    if not result_str:
        return 0.0
    r = result_str.lower()
    if "fall" in r or " pin" in r:
        return 2.0
    if "tf" in r or "tech" in r:
        return 1.5
    if "md" in r or "major" in r:
        return 1.0
    return 0.0


def _advancement_for_round(round_str: str) -> float:
    """1.0 for champ bracket win, 0.5 for consol win, 0 for placement match."""
    if not round_str:
        return 0.0
    r = round_str.lower()
    for c in CHAMP_ROUNDS:
        if c in r:
            return 1.0
    for c in CONSOL_ROUNDS:
        if c in r:
            return 0.5
    return 0.0


def parse_results_and_compute_points() -> dict:
    """
    Parse results.txt and compute advancement + bonus points per wrestler (from match wins).
    Placement points are added separately from wrestler_placements.json.
    Returns: {(weight, name, team): (advancement, bonus)}
    """
    with RESULTS_FILE.open("r", encoding="utf-8") as f:
        lines = f.readlines()

    adv_bonus_by_wrestler: dict[tuple, tuple[float, float]] = defaultdict(lambda: (0.0, 0.0))
    current_weight: int | None = None
    current_round: str = ""

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if re.match(r"^\d{3}$", line):
            try:
                current_weight = int(line)
            except ValueError:
                pass
            current_round = ""
            continue
        if current_weight is None:
            continue

        if "won" not in line or "over" not in line:
            # Round header (e.g. "Champ Round 2", "Cons. Round 1")
            current_round = line
            continue

        # Match line: "RoundName - Winner (Team) x-y won ... over Loser (Team) x-y (Result)"
        parts = line.split(" - ", 1)
        if len(parts) == 2:
            round_part, match_part = parts[0].strip(), parts[1]
            if "won" in match_part:
                current_round = round_part
        else:
            match_part = line

        m = MATCH_PATTERN.search(match_part)
        if not m:
            continue

        winner_name, winner_team = m.group(1).strip(), m.group(2).strip()

        # Placement matches (1st, 3rd, 5th, 7th): no advancement, only placement (handled via placements.json)
        if "Place Match" in current_round:
            continue

        # Extract result type from end: (Fall 6:18) or (MD 18-5) etc.
        result_match = re.search(r"\(([^)]+)\)\s*$", match_part)
        result_str = result_match.group(1) if result_match else ""
        bonus = _bonus_from_result(result_str)
        adv = _advancement_for_round(current_round)

        key = (current_weight, winner_name, winner_team)
        prev_adv, prev_bonus = adv_bonus_by_wrestler[key]
        adv_bonus_by_wrestler[key] = (prev_adv + adv, prev_bonus + bonus)

    return dict(adv_bonus_by_wrestler)


def _normalize_name(seed_name: str, result_name: str) -> bool:
    """Match seed 'Last, First' to result 'First Last'."""
    seed_clean = " ".join(seed_name.strip().lower().split())
    result_clean = " ".join(result_name.strip().lower().split())
    if "," in seed_name:
        parts = seed_name.split(",", 1)
        last, first = parts[0].strip(), parts[1].strip()
        seed_as_first_last = f"{first} {last}".lower()
        return seed_as_first_last == result_clean
    return seed_clean == result_clean


def _team_match(a: str, b: str) -> bool:
    return a.strip().lower() == b.strip().lower()


def find_points_for_wrestler(
    weight: int, name: str, team: str, points_lookup: dict
) -> tuple[float, float]:
    """Find (advancement, bonus) for a wrestler by matching name+team in points lookup."""
    for (w, n, t), (adv, bonus) in points_lookup.items():
        if w == weight and _normalize_name(name, n) and _team_match(team, t):
            return (adv, bonus)
    return (0.0, 0.0)


def main():
    print("Loading wrestler placements...")
    placements_path = PARSED_DIR / "wrestler_placements.json"
    with placements_path.open("r", encoding="utf-8") as f:
        wrestlers = json.load(f)

    print("Parsing results and computing advancement+bonus...")
    adv_bonus_lookup = parse_results_and_compute_points()

    # Attach total points and components to each wrestler
    for w in wrestlers:
        adv, bonus = find_points_for_wrestler(
            w["weight"], w["name"], w["team"], adv_bonus_lookup
        )
        placement_pts = PLACEMENT_POINTS.get(w["placement"], 0)
        w["advancement"] = adv
        w["bonus"] = bonus
        w["placement_pts"] = placement_pts
        w["points"] = adv + bonus + placement_pts

    # Group by seed: seed -> list of (placement, points, adv, bonus, placement_pts)
    by_seed: dict[int, list] = defaultdict(list)
    for w in wrestlers:
        by_seed[w["seed"]].append(w)

    # Stats per seed
    print("\n" + "=" * 120)
    print("2025 NCAA Tournament Seed Analysis (10 weight classes, 33 seeds)")
    print("=" * 120)
    print(f"{'Seed':>4}  {'n':>3}  {'Avg Place':>10}  {'Std Place':>10}  {'Avg Pts':>10}  {'Std Pts':>10}  {'Avg Adv':>8}  {'Avg Bonus':>9}  {'Avg PlacePts':>12}")
    print("-" * 120)

    rows = []
    for seed in sorted(by_seed.keys()):
        data = by_seed[seed]
        placements = [w["placement"] for w in data]
        points = [w["points"] for w in data]
        advs = [w["advancement"] for w in data]
        bonuses = [w["bonus"] for w in data]
        place_pts = [w["placement_pts"] for w in data]

        n = len(data)
        avg_place = statistics.mean(placements) if placements else 0
        std_place = statistics.stdev(placements) if len(placements) > 1 else 0
        avg_pts = statistics.mean(points) if points else 0
        std_pts = statistics.stdev(points) if len(points) > 1 else 0
        avg_adv = statistics.mean(advs) if advs else 0
        avg_bonus = statistics.mean(bonuses) if bonuses else 0
        avg_place_pts = statistics.mean(place_pts) if place_pts else 0

        print(f"{seed:4d}  {n:3d}  {avg_place:10.2f}  {std_place:10.2f}  {avg_pts:10.2f}  {std_pts:10.2f}  {avg_adv:8.2f}  {avg_bonus:9.2f}  {avg_place_pts:12.2f}")

        rows.append({
            "seed": seed,
            "n": n,
            "avg_placement": round(avg_place, 2),
            "std_placement": round(std_place, 2),
            "avg_points": round(avg_pts, 2),
            "std_points": round(std_pts, 2),
            "avg_advancement": round(avg_adv, 2),
            "avg_bonus": round(avg_bonus, 2),
            "avg_placement_points": round(avg_place_pts, 2),
        })

    # Save JSON
    out_path = PARSED_DIR / "seed_analysis_2025.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump({"seeds": rows}, f, indent=2)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
