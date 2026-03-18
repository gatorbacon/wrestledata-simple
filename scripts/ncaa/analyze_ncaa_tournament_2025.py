#!/usr/bin/env python3
"""
Analyze 2025 NCAA Wrestling Tournament results.

Computes seed-to-placement discrepancy by team and conference.
Placement for top 8 is explicit from results. For consolation round losers,
uses range + closest to seed: Cons Pig Tails=33, Cons R1=25-32, Cons R2=17-24,
Cons R3=13-16, Cons R4=9-12.

Usage:
  python scripts/ncaa/analyze_ncaa_tournament_2025.py

Interactive: choose team, conference, or seed view; drill down to wrestler breakdown.
"""

import json
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SEEDS_DIR = PROJECT_ROOT / "data" / "2025" / "ncaa-tourney" / "seeds"
RESULTS_FILE = PROJECT_ROOT / "data" / "2025" / "ncaa-tourney" / "results.txt"
TEAMS_FILE = PROJECT_ROOT / "data" / "team_lists" / "2025" / "ncaa_d1_teams.json"
PARSED_DIR = PROJECT_ROOT / "data" / "2025" / "ncaa-tourney" / "parsed"

# Consolation round -> (min_place, max_place)
CONS_ROUND_PLACEMENT = {
    "Consolation Pig Tails": (33, 33),
    "Cons. Round 1": (25, 32),
    "Cons. Round 2": (17, 24),
    "Cons. Round 3": (13, 16),
    "Cons. Round 4": (9, 12),
    "Cons. Round 5": (7, 8),  # losers go to 7th place match
}

# Match line pattern: "Winner Name (Team) X-Y won ... over Loser Name (Team) X-Y"
# Handles optional prefix like "Prelim - " or "Cons. Round 4 - "
MATCH_PATTERN = re.compile(
    r"(.+?)\s+\(([^)]+)\)\s+\d+-\d+\s+won\s+.+?\s+over\s+(.+?)\s+\(([^)]+)\)\s+\d+-\d+"
)


def normalize_name_for_match(seed_name: str, result_name: str) -> bool:
    """
    Check if seed name (Last, First) matches result name (First Last).
    Handles: "McGowan, Marc-Anthony" vs "Marc-Anthony McGowan"
    """
    # Seed: "Last, First" or "Last, First-Middle"
    # Result: "First Last" or "First-Middle Last"
    seed_clean = seed_name.strip()
    result_clean = result_name.strip()
    if "," in seed_clean:
        parts = seed_clean.split(",", 1)
        last = parts[0].strip()
        first = parts[1].strip()
        # Build "First Last" from seed
        seed_as_first_last = f"{first} {last}"
        return _names_match(seed_as_first_last, result_clean)
    return _names_match(seed_clean, result_clean)


def _normalize_name(s: str) -> str:
    """Normalize name for matching: case, spaces, apostrophe/backtick."""
    s = " ".join(s.lower().split())
    s = s.replace("`", "'")  # backtick -> apostrophe
    return s


def _names_match(a: str, b: str) -> bool:
    """Normalize and compare names (case-insensitive, collapse spaces)."""
    return _normalize_name(a) == _normalize_name(b)


def load_seeds() -> Dict[int, List[Dict]]:
    """Load seeds for each weight. Returns {weight: [{seed, name, team}, ...]}."""
    seeds_by_weight = {}
    for p in sorted(SEEDS_DIR.glob("*.txt")):
        try:
            weight = int(p.stem)
        except ValueError:
            continue
        entries = []
        with p.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) < 2:
            continue
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            seed_str = parts[0].strip().rstrip(".")
            try:
                seed_num = int(seed_str)
            except ValueError:
                continue
            name = parts[1].strip()
            team = parts[2].strip()
            entries.append({"seed": seed_num, "name": name, "team": team})
        seeds_by_weight[weight] = entries
    return seeds_by_weight


def load_teams() -> Dict[str, str]:
    """Load team name -> conference. Returns {team_name: conference}."""
    with TEAMS_FILE.open("r", encoding="utf-8") as f:
        teams = json.load(f)
    team_to_conf = {}
    for t in teams:
        name = t.get("name", "")
        div = t.get("division", "")
        if not name:
            continue
        # Extract first conference from "DI - Big 12, DI - Big 12, ..."
        conf = "Unknown"
        for part in div.split(","):
            part = part.strip()
            if part.startswith("DI - "):
                conf = part.replace("DI - ", "").strip()
                break
        team_to_conf[name] = conf
    return team_to_conf


def parse_results() -> Dict[int, Dict[str, Dict]]:
    """
    Parse results.txt. Returns:
    {weight: {wrestler_key: {placement: int|None, last_round: str, ...}}}
    wrestler_key = "name (team)" normalized for matching.
    """
    with RESULTS_FILE.open("r", encoding="utf-8") as f:
        lines = f.readlines()

    # Placement matches: explicit placement for winner and loser
    placement_rounds = {
        "1st Place Match": (1, 2),
        "3rd Place Match": (3, 4),
        "5th Place Match": (5, 6),
        "7th Place Match": (7, 8),
    }

    # Track last round each wrestler appeared in (as loser)
    # For placement matches we get exact placement
    # For cons rounds we get the round they lost in
    result_by_weight: Dict[int, Dict[str, Dict]] = {}
    current_weight: Optional[int] = None
    current_round: Optional[str] = None

    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Weight header
        if re.match(r"^\d{3}$", line):
            try:
                current_weight = int(line)
                current_round = None
                if current_weight not in result_by_weight:
                    result_by_weight[current_weight] = {}
            except ValueError:
                pass
            continue
        if current_weight is None:
            continue

        # Round header (sets context for following match lines)
        for cons_round in CONS_ROUND_PLACEMENT:
            if cons_round in line and " - " not in line:
                current_round = cons_round
                break
        else:
            if any(r in line for r in placement_rounds):
                current_round = None  # placement match, round is in the line

        # Extract match part (after " - " for round-prefixed lines)
        match_part = line
        if " - " in line:
            parts = line.split(" - ", 1)
            if len(parts) == 2 and "won" in parts[1] and "over" in parts[1]:
                match_part = parts[1]

        # Match line - must have "won" and "over"
        if "won" not in line or "over" not in line:
            continue

        m = MATCH_PATTERN.search(match_part)
        if not m:
            continue

        winner_name, winner_team = m.group(1).strip(), m.group(2).strip()
        loser_name, loser_team = m.group(3).strip(), m.group(4).strip()

        # Placement matches: exact placement
        for round_name, (winner_place, loser_place) in placement_rounds.items():
            if round_name in line:
                result_by_weight[current_weight][f"{winner_name}|{winner_team}"] = {
                    "placement": winner_place,
                    "last_round": round_name,
                }
                result_by_weight[current_weight][f"{loser_name}|{loser_team}"] = {
                    "placement": loser_place,
                    "last_round": round_name,
                }
                break
        else:
            # Consolation round: loser eliminated
            if current_round and current_round in CONS_ROUND_PLACEMENT:
                if f"{loser_name}|{loser_team}" not in result_by_weight[current_weight]:
                    result_by_weight[current_weight][f"{loser_name}|{loser_team}"] = {
                        "placement": None,
                        "last_round": current_round,
                    }

    return result_by_weight


def find_wrestler_result(
    seed_name: str,
    seed_team: str,
    results: Dict[str, Dict],
) -> Optional[Dict]:
    """
    Find result for a seeded wrestler. Match by name+team.
    Returns {placement, last_round} or None.
    """
    for key, data in results.items():
        name_part, team_part = key.split("|", 1)
        if normalize_name_for_match(seed_name, name_part) and _team_match(seed_team, team_part):
            return data
    return None


def _team_match(seed_team: str, result_team: str) -> bool:
    """Match team names (case-insensitive, handle common variations)."""
    s = seed_team.strip().lower()
    r = result_team.strip().lower()
    return s == r


def placement_from_cons_round(round_name: str, seed: int) -> int:
    """
    Get placement for wrestler who lost in consolation round.
    Use closest value in range to seed.
    """
    if round_name not in CONS_ROUND_PLACEMENT:
        return 33  # fallback
    lo, hi = CONS_ROUND_PLACEMENT[round_name]
    if lo == hi:
        return lo
    # Closest: if seed <= lo use lo, if seed >= hi use hi, else use seed
    if seed <= lo:
        return lo
    if seed >= hi:
        return hi
    return seed


# Cons round -> display string (R12 = round of 12, places 9-12, etc.)
CONS_ROUND_DISPLAY = {
    "Consolation Pig Tails": "R33",
    "Cons. Round 1": "R32",
    "Cons. Round 2": "R24",
    "Cons. Round 3": "R16",
    "Cons. Round 4": "R12",
}


def _placement_display(w: Dict) -> str:
    """Return placement as string: R12/R16/R24/R32/R33 for cons rounds, else numeric."""
    last_round = w.get("last_round", "")
    if last_round in CONS_ROUND_DISPLAY:
        return CONS_ROUND_DISPLAY[last_round]
    return str(w["placement"])


def _print_wrestler_breakdown(wrestlers: List[Dict], title: str) -> None:
    """Print detailed wrestler list: weight, name, seed, result, delta."""
    sorted_w = sorted(wrestlers, key=lambda w: (w.get("weight", 0), w.get("seed", 0)))
    print("\n" + "=" * 70)
    print(f"{title}")
    print("=" * 70)
    for w in sorted_w:
        name_display = w["name"].replace(",", ", ")
        delta_str = f"({w['discrepancy']:+d})"
        place_str = _placement_display(w)
        is_cons_round = place_str.startswith("R")
        if is_cons_round:
            result = f"lost {place_str}"
        else:
            result = f"placed {place_str}"
        print(f"  {w['weight']:3}  {name_display:35}  {w['seed']:2} → {result:12}  {delta_str}")
    if sorted_w:
        avg_d = sum(w["discrepancy"] for w in sorted_w) / len(sorted_w)
        print(f"  ---  Avg discrepancy: {avg_d:+.2f}  (n={len(sorted_w)})")
    print()


def run_interactive(
    wrestler_entries: List[Dict],
    team_avg: Dict[str, float],
    team_med: Dict[str, float],
    team_discrepancies: Dict[str, List[float]],
    conf_avg: Dict[str, float],
    conf_med: Dict[str, float],
    conf_discrepancies: Dict[str, List[float]],
    seed_placements: Dict[int, List[int]],
    seed_avg: Dict[int, float],
    seed_med: Dict[int, float],
) -> None:
    """Interactive menu: choose team/conference/seed, then drill down to wrestlers."""
    while True:
        print("\n" + "=" * 60)
        print("VIEW BY")
        print("=" * 60)
        print("  1. Team")
        print("  2. Conference")
        print("  3. Seed")
        print("  4. Quit")
        print()
        choice = input("Choose (1-4): ").strip()
        if choice == "4":
            print("Goodbye.")
            break
        if choice not in ("1", "2", "3"):
            print("Invalid choice. Try again.")
            continue

        # Build and show list
        items: List[Tuple[str, int]] = []  # (label, key for lookup)
        if choice == "1":
            sorted_teams = sorted(team_avg.keys(), key=lambda t: -team_avg[t])
            print("\n" + "-" * 60)
            print("BY TEAM (avg / median discrepancy, n)")
            print("(Positive = overperformed, Negative = underperformed)")
            print("-" * 60)
            for i, team in enumerate(sorted_teams, 1):
                avg = team_avg[team]
                med = team_med[team]
                n = len(team_discrepancies[team])
                print(f"  {i:2}. {team:30}  avg {avg:+.2f}  med {med:+.2f}  n={n}")
            items = [(str(i), team) for i, team in enumerate(sorted_teams, 1)]

        elif choice == "2":
            sorted_confs = sorted(conf_avg.keys(), key=lambda c: -conf_avg[c])
            print("\n" + "-" * 60)
            print("BY CONFERENCE (avg / median discrepancy, n)")
            print("(Positive = overperformed, Negative = underperformed)")
            print("-" * 60)
            for i, conf in enumerate(sorted_confs, 1):
                avg = conf_avg[conf]
                med = conf_med[conf]
                n = len(conf_discrepancies[conf])
                print(f"  {i:2}. {conf:30}  avg {avg:+.2f}  med {med:+.2f}  n={n}")
            items = [(str(i), conf) for i, conf in enumerate(sorted_confs, 1)]

        else:  # choice == "3"
            sorted_seeds = sorted(seed_placements.keys())
            print("\n" + "-" * 60)
            print("BY SEED (avg placed / median placed, delta, n)")
            print("(Delta = seed - placement; positive = overperformed)")
            print("-" * 60)
            for i, seed in enumerate(sorted_seeds, 1):
                placements = seed_placements[seed]
                avg_p = seed_avg[seed]
                med_p = seed_med[seed]
                delta_avg = seed - avg_p
                delta_med = seed - med_p
                n = len(placements)
                print(f"  {i:2}. Seed {seed:2}  avg placed {avg_p:5.2f} (delta {delta_avg:+.2f})  med placed {med_p:5.1f} (delta {delta_med:+.1f})  n={n}")
            items = [(str(i), seed) for i, seed in enumerate(sorted_seeds, 1)]

        # Drill down
        valid_nums = set(range(1, len(items) + 1))
        pick = input("\nEnter number for wrestler breakdown (or 0 to go back): ").strip()
        if pick == "0":
            continue
        try:
            idx = int(pick)
        except ValueError:
            print("Invalid input.")
            continue
        if idx not in valid_nums:
            print("Invalid number.")
            continue

        # Get selected key (team name, conf name, or seed int)
        selected_key = items[idx - 1][1]

        if choice == "1":
            wrestlers = [w for w in wrestler_entries if w["team"] == selected_key]
            _print_wrestler_breakdown(wrestlers, f"WRESTLERS: {selected_key}")
        elif choice == "2":
            wrestlers = [w for w in wrestler_entries if w["conference"] == selected_key]
            _print_wrestler_breakdown(wrestlers, f"WRESTLERS: {selected_key}")
        else:
            wrestlers = [w for w in wrestler_entries if w["seed"] == selected_key]
            _print_wrestler_breakdown(wrestlers, f"WRESTLERS: Seed {selected_key}")

        input("Press Enter to continue...")


def main():
    PARSED_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading seeds...")
    seeds_by_weight = load_seeds()
    print(f"  Weights: {sorted(seeds_by_weight.keys())}")

    print("Loading teams...")
    team_to_conf = load_teams()
    print(f"  Teams: {len(team_to_conf)}")

    print("Parsing results...")
    results_by_weight = parse_results()
    print(f"  Weights in results: {sorted(results_by_weight.keys())}")

    # Build wrestler entries with seed, placement, discrepancy
    wrestler_entries: List[Dict] = []
    unmatched_seeds: List[Dict] = []

    for weight, seeds in seeds_by_weight.items():
        results = results_by_weight.get(weight, {})
        for s in seeds:
            seed = s["seed"]
            name = s["name"]
            team = s["team"]
            conf = team_to_conf.get(team, "Unknown")

            result = find_wrestler_result(name, team, results)
            if result is None:
                unmatched_seeds.append({"weight": weight, "seed": seed, "name": name, "team": team})
                continue

            placement = result.get("placement")
            last_round = result.get("last_round", "")

            if placement is None:
                placement = placement_from_cons_round(last_round, seed)

            discrepancy = seed - placement  # positive = overperformed

            wrestler_entries.append({
                "weight": weight,
                "seed": seed,
                "name": name,
                "team": team,
                "conference": conf,
                "placement": placement,
                "last_round": last_round,
                "discrepancy": discrepancy,
            })

    if unmatched_seeds:
        weights_missing = set(u["weight"] for u in unmatched_seeds)
        print(f"\nNote: {len(unmatched_seeds)} seeded wrestlers not matched in results.")
        if weights_missing:
            print(f"  Weights with no results in file: {sorted(weights_missing)}")
        for u in unmatched_seeds[:5]:
            print(f"  {u['weight']} lbs seed {u['seed']}: {u['name']} ({u['team']})")
        if len(unmatched_seeds) > 5:
            print(f"  ... and {len(unmatched_seeds) - 5} more")

    # Save parsed data
    parsed_path = PARSED_DIR / "wrestler_placements.json"
    with parsed_path.open("w", encoding="utf-8") as f:
        json.dump(wrestler_entries, f, indent=2)
    print(f"\nSaved parsed data to {parsed_path}")

    # Aggregate by team
    team_discrepancies: Dict[str, List[float]] = defaultdict(list)
    for w in wrestler_entries:
        team_discrepancies[w["team"]].append(w["discrepancy"])

    team_avg = {team: sum(d) / len(d) for team, d in team_discrepancies.items() if d}
    team_med = {team: statistics.median(d) for team, d in team_discrepancies.items() if d}

    # Aggregate by conference
    conf_discrepancies: Dict[str, List[float]] = defaultdict(list)
    for w in wrestler_entries:
        conf_discrepancies[w["conference"]].append(w["discrepancy"])

    conf_avg = {conf: sum(d) / len(d) for conf, d in conf_discrepancies.items() if d}
    conf_med = {conf: statistics.median(d) for conf, d in conf_discrepancies.items() if d}

    # Aggregate by seed
    seed_placements: Dict[int, List[int]] = defaultdict(list)
    for w in wrestler_entries:
        seed_placements[w["seed"]].append(w["placement"])

    seed_avg = {s: sum(p) / len(p) for s, p in seed_placements.items() if p}
    seed_med = {s: statistics.median(p) for s, p in seed_placements.items() if p}

    # Interactive loop
    run_interactive(
        wrestler_entries=wrestler_entries,
        team_avg=team_avg,
        team_med=team_med,
        team_discrepancies=team_discrepancies,
        conf_avg=conf_avg,
        conf_med=conf_med,
        conf_discrepancies=conf_discrepancies,
        seed_placements=seed_placements,
        seed_avg=seed_avg,
        seed_med=seed_med,
    )

    # Save summary
    summary = {
        "by_team": {t: {"avg_discrepancy": round(v, 2), "n": len(team_discrepancies[t])}
                    for t, v in sorted(team_avg.items(), key=lambda x: x[1])},
        "by_conference": {c: {"avg_discrepancy": round(v, 2), "n": len(conf_discrepancies[c])}
                         for c, v in sorted(conf_avg.items(), key=lambda x: x[1])},
    }
    summary_path = PARSED_DIR / "seed_placement_summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSaved summary to {summary_path}")


if __name__ == "__main__":
    main()
