#!/usr/bin/env python3
"""
Generate state predictions graphics, one weight class at a time.

GIRLS: 16-man seeded bracket simulation. Seeds from seed file, winners by rank.
- Slot = seed (1-16). Bracket layout: Match 1=1v16, 2=8v9, 3=5v12, 4=4v13, 5=3v14, 6=6v11, 7=7v10, 8=2v15.
- Places 1-8 from placement matches (27/28/29/30)
- BR1-BR4 = losers of matches 18, 19, 21, 22 (blood round finishers)

BOYS: 32-man seeded bracket simulation. Same seed format, same resolver.
- Slot = sequential (1-2 in match 1, 3-4 in match 2, etc.). Top to bottom.
- Places 1-8 from placement matches (59/60/61/62)
- BR1-BR4 = losers of matches 49, 50, 51, 52 (blood round finishers)

Templates: mt/graphics/templates/State-Predictions/{girls|boys}/
Output: mt/graphics/State-Predictions/{girls|boys}/

Usage:
  python scripts/state/run_state_predictions.py --season 2026
  python scripts/state/run_state_predictions.py --season 2026 -gender boys
  python scripts/state/run_state_predictions.py --season 2026 --weight 106
  python scripts/state/run_state_predictions.py --season 2026 --debug
"""

import argparse
import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

HS_GIRLS_WEIGHTS = [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235]
HS_BOYS_WEIGHTS = [106, 113, 120, 126, 132, 138, 144, 150, 157, 165, 175, 190, 215, 285]

PLACEMENT_LABELS = [
    "1st-place",
    "2nd-place",
    "3rd-place",
    "4th-place",
    "5th-place",
    "6th-place",
    "7th-place",
    "8th-place",
]
BLOOD_ROUND_LABELS = ["br1", "br2", "br3", "br4"]

# ============================================================
# GIRLS 16-MAN BRACKET (do not modify wiring)
# ============================================================

GIRLS_BRACKET = {
    1: {"winner_to": 9, "loser_to": 10},
    2: {"winner_to": 9, "loser_to": 10},
    3: {"winner_to": 11, "loser_to": 12},
    4: {"winner_to": 11, "loser_to": 12},
    5: {"winner_to": 13, "loser_to": 14},
    6: {"winner_to": 13, "loser_to": 14},
    7: {"winner_to": 15, "loser_to": 16},
    8: {"winner_to": 15, "loser_to": 16},
    9: {"winner_to": 17, "loser_to": 22},
    11: {"winner_to": 17, "loser_to": 21},
    13: {"winner_to": 20, "loser_to": 19},
    15: {"winner_to": 20, "loser_to": 18},
    10: {"winner_to": 18, "loser_to": None},
    12: {"winner_to": 19, "loser_to": None},
    14: {"winner_to": 21, "loser_to": None},
    16: {"winner_to": 22, "loser_to": None},
    17: {"winner_to": 30, "loser_to": 25},
    20: {"winner_to": 30, "loser_to": 26},
    18: {"winner_to": 23, "loser_to": None},
    19: {"winner_to": 23, "loser_to": None},
    21: {"winner_to": 24, "loser_to": None},
    22: {"winner_to": 24, "loser_to": None},
    23: {"winner_to": 25, "loser_to": 27},
    24: {"winner_to": 26, "loser_to": 27},
    25: {"winner_to": 29, "loser_to": 28},
    26: {"winner_to": 29, "loser_to": 28},
    27: {"placement": {"winner": 7, "loser": 8}},
    28: {"placement": {"winner": 5, "loser": 6}},
    29: {"placement": {"winner": 3, "loser": 4}},
    30: {"placement": {"winner": 1, "loser": 2}},
}

GIRLS_BLOOD_ROUND_MATCHES = (18, 19, 21, 22)
GIRLS_OPENING_MATCH_COUNT = 8
GIRLS_REQUIRED_SLOTS = set(range(1, 17))
GIRLS_FIRST_CONSO_LOSS_HIDDEN = (10, 12, 14, 16)

# Girls 16-man bracket: slot = seed. Standard bracket layout (1v16, 8v9, etc.).
# Match 1 = 1v16, 2 = 8v9, 3 = 5v12, 4 = 4v13, 5 = 3v14, 6 = 6v11, 7 = 7v10, 8 = 2v15.
GIRLS_OPENING_MATCH_SLOTS = [
    (1, 16),   # Match 1
    (8, 9),    # Match 2
    (5, 12),   # Match 3
    (4, 13),   # Match 4
    (3, 14),   # Match 5
    (6, 11),   # Match 6
    (7, 10),   # Match 7
    (2, 15),   # Match 8
]


# ============================================================
# BOYS 32-MAN BRACKET (do not modify wiring)
# ============================================================

BOYS_BRACKET = {
    # Round of 32 (1–16)
    1: {"winner_to": 17, "loser_to": 18},
    2: {"winner_to": 17, "loser_to": 18},
    3: {"winner_to": 19, "loser_to": 20},
    4: {"winner_to": 19, "loser_to": 20},
    5: {"winner_to": 21, "loser_to": 22},
    6: {"winner_to": 21, "loser_to": 22},
    7: {"winner_to": 23, "loser_to": 24},
    8: {"winner_to": 23, "loser_to": 24},
    9: {"winner_to": 25, "loser_to": 26},
    10: {"winner_to": 25, "loser_to": 26},
    11: {"winner_to": 27, "loser_to": 28},
    12: {"winner_to": 27, "loser_to": 28},
    13: {"winner_to": 29, "loser_to": 30},
    14: {"winner_to": 29, "loser_to": 30},
    15: {"winner_to": 31, "loser_to": 32},
    16: {"winner_to": 31, "loser_to": 32},
    # Round of 16
    17: {"winner_to": 33, "loser_to": 44},
    19: {"winner_to": 33, "loser_to": 43},
    21: {"winner_to": 36, "loser_to": 41},
    23: {"winner_to": 36, "loser_to": 40},
    25: {"winner_to": 39, "loser_to": 38},
    27: {"winner_to": 39, "loser_to": 37},
    29: {"winner_to": 42, "loser_to": 35},
    31: {"winner_to": 42, "loser_to": 34},
    # Quarterfinals
    33: {"winner_to": 53, "loser_to": 50},
    36: {"winner_to": 53, "loser_to": 49},
    39: {"winner_to": 54, "loser_to": 52},
    42: {"winner_to": 54, "loser_to": 51},
    # Semifinals
    53: {"winner_to": 59, "loser_to": 58},
    54: {"winner_to": 59, "loser_to": 57},
    # Consolation Round 1
    18: {"winner_to": 34, "loser_to": None},
    20: {"winner_to": 35, "loser_to": None},
    22: {"winner_to": 37, "loser_to": None},
    24: {"winner_to": 38, "loser_to": None},
    26: {"winner_to": 40, "loser_to": None},
    28: {"winner_to": 41, "loser_to": None},
    30: {"winner_to": 43, "loser_to": None},
    32: {"winner_to": 44, "loser_to": None},
    # Consolation Round 2
    34: {"winner_to": 45, "loser_to": None},
    35: {"winner_to": 45, "loser_to": None},
    37: {"winner_to": 46, "loser_to": None},
    38: {"winner_to": 46, "loser_to": None},
    40: {"winner_to": 47, "loser_to": None},
    41: {"winner_to": 47, "loser_to": None},
    43: {"winner_to": 48, "loser_to": None},
    44: {"winner_to": 48, "loser_to": None},
    # Consolation Round 3
    45: {"winner_to": 49, "loser_to": None},
    46: {"winner_to": 50, "loser_to": None},
    47: {"winner_to": 51, "loser_to": None},
    48: {"winner_to": 52, "loser_to": None},
    # Consolation Round 4 (Blood Round)
    49: {"winner_to": 55, "loser_to": None},
    50: {"winner_to": 55, "loser_to": None},
    51: {"winner_to": 56, "loser_to": None},
    52: {"winner_to": 56, "loser_to": None},
    # Consolation Round 5
    55: {"winner_to": 57, "loser_to": 62},
    56: {"winner_to": 58, "loser_to": 62},
    # Consolation Round 6
    57: {"winner_to": 60, "loser_to": 61},
    58: {"winner_to": 60, "loser_to": 61},
    # Placement
    59: {"placement": {"winner": 1, "loser": 2}},
    60: {"placement": {"winner": 3, "loser": 4}},
    61: {"placement": {"winner": 5, "loser": 6}},
    62: {"placement": {"winner": 7, "loser": 8}},
}

BOYS_BLOOD_ROUND_MATCHES = (49, 50, 51, 52)
BOYS_OPENING_MATCH_COUNT = 16
BOYS_REQUIRED_SLOTS = set(range(1, 33))

# Championship vs consolation (for advancement scoring)
GIRLS_CHAMP_MATCHES = {1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 13, 15, 17, 20}
GIRLS_PLACEMENT_MATCHES = {27, 28, 29, 30}
BOYS_CHAMP_MATCHES = {
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16,
    17, 19, 21, 23, 25, 27, 29, 31, 33, 36, 39, 42, 53, 54,
}
BOYS_PLACEMENT_MATCHES = {59, 60, 61, 62}

# Team scoring
PLACEMENT_POINTS = {1: 20, 2: 16, 3: 12, 4: 10, 5: 8, 6: 6, 7: 4, 8: 2}


def bonus_points_from_rank_gap(winner_rank: int, loser_rank: int) -> float:
    """Estimated bonus from rank gap: pin +2, tech +1.5, major +1, dec +0."""
    gap = loser_rank - winner_rank
    if gap >= 7:
        return 2.0
    if gap == 6:
        return 1.5
    if gap >= 5:
        return 1.0
    return 0.0


def _add_points(
    team_totals: Dict[str, float], team: str, pts: float
) -> None:
    if not team:
        team = "UNKNOWN"
    team_totals[team] = team_totals.get(team, 0.0) + pts


def compute_team_scores(
    results_per_weight: List[Tuple[Dict[int, dict], Dict[int, dict]]],
    champ_set: set,
    placement_set: set,
) -> Tuple[Dict[str, float], Dict[str, dict], Dict[str, Dict[str, float]], Dict[str, dict]]:
    """
    Compute team totals from match results and placements across all weights.
    results_per_weight: list of (match_results, placements_by_place) per weight.
    Returns (team_totals, team_breakdown, wrestler_points, wrestler_info).
    wrestler_info: wrestler_id -> {name, team} for display.
    """
    team_totals: Dict[str, float] = {}
    breakdown: Dict[str, dict] = {}
    wrestler_points: Dict[str, Dict[str, float]] = {}
    wrestler_info: Dict[str, dict] = {}

    def register_wrestler(team: str, wid: str, wname: str) -> None:
        """Ensure wrestler is in wrestler_info and wrestler_points (for counting all participants)."""
        if wid:
            if wid not in wrestler_points:
                wrestler_points[wid] = {"adv": 0.0, "place": 0.0, "bonus": 0.0, "total": 0.0}
            wrestler_info[wid] = {"name": wname, "team": team}

    def bump(team: str, wid: str, wname: str, bucket: str, pts: float) -> None:
        _add_points(team_totals, team, pts)
        if team not in breakdown:
            breakdown[team] = {"adv": 0.0, "place": 0.0, "bonus": 0.0, "total": 0.0}
        breakdown[team][bucket] += pts
        breakdown[team]["total"] += pts
        if wid:
            if wid not in wrestler_points:
                wrestler_points[wid] = {"adv": 0.0, "place": 0.0, "bonus": 0.0, "total": 0.0}
            wrestler_points[wid][bucket] += pts
            wrestler_points[wid]["total"] += pts
            wrestler_info[wid] = {"name": wname, "team": team}

    for match_results, placements_by_place in results_per_weight:
        for match_id, res in match_results.items():
            winner = res["winner"]
            loser = res["loser"]
            # Register both so we count all wrestlers in bracket (including 0-2)
            register_wrestler(
                winner.get("team") or "UNKNOWN",
                str(winner.get("wrestler_id", "")),
                winner.get("name", ""),
            )
            register_wrestler(
                loser.get("team") or "UNKNOWN",
                str(loser.get("wrestler_id", "")),
                loser.get("name", ""),
            )
            wteam = winner.get("team") or "UNKNOWN"
            wid = str(winner.get("wrestler_id", ""))
            wname = winner.get("name", "")
            if not wteam or wteam == "UNKNOWN":
                raise RuntimeError(f"Winner missing team in match {match_id}: {winner}")
            wr = winner.get("rank")
            lr = loser.get("rank")
            if wr is None or lr is None:
                raise RuntimeError(
                    f"Match {match_id}: winner or loser missing rank (winner={wr}, loser={lr})"
                )
            wr = int(wr)
            lr = int(lr)

            if match_id in placement_set:
                adv = 0.0
            elif match_id in champ_set:
                adv = 1.0
            else:
                adv = 0.5
            if adv:
                bump(wteam, wid, wname, "adv", adv)

            b = bonus_points_from_rank_gap(wr, lr)
            if b:
                bump(wteam, wid, wname, "bonus", b)

        for place, wrestler in placements_by_place.items():
            team = wrestler.get("team") or "UNKNOWN"
            wid = str(wrestler.get("wrestler_id", ""))
            wname = wrestler.get("name", "")
            pts = PLACEMENT_POINTS.get(place, 0)
            if pts:
                bump(team, wid, wname, "place", float(pts))

    return team_totals, breakdown, wrestler_points, wrestler_info


# ============================================================
# SEED FILE PARSING
# ============================================================

def parse_seed_file(seed_file_path: str) -> Dict[int, Tuple[str, str]]:
    """
    Parse seed text file. Leading integer before dot = SLOT NUMBER (bracket position).
    Format: tab-separated, col0=slot (e.g. "3."), col1=name, col2=team.
    Returns dict[int, tuple[str, str]] mapping slot -> (raw_name, raw_team).
    Raises on duplicate slot numbers.
    """
    slot_map: Dict[int, Tuple[str, str]] = {}
    path = Path(seed_file_path)
    if not path.exists():
        return slot_map
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split("\t") if p.strip() != ""]
            if len(parts) < 3:
                continue
            slot_str = parts[0].replace(".", "").strip()
            if not slot_str.isdigit():
                continue
            slot = int(slot_str)
            if slot in slot_map:
                raise RuntimeError(
                    f"Duplicate slot number {slot} in seed file {seed_file_path}. "
                    f"Each slot must appear exactly once."
                )
            raw_name = parts[1]
            raw_team = parts[2]
            slot_map[slot] = (raw_name, raw_team)
    return slot_map


# ============================================================
# NORMALIZATION (for resolve_seeded_wrestlers)
# ============================================================

def _normalize_team(team: str) -> str:
    """Uppercase + collapse whitespace. Strips 'High School' for matching."""
    if not team:
        return ""
    s = re.sub(r"\s+", " ", (team or "").strip())
    s = re.sub(r"\s+High\s+School\b", "", s, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", s).strip().upper()


def _normalize_name_for_match(name: str) -> str:
    """Lower + remove punctuation + collapse whitespace. Handle 'Last, First' -> 'first last'."""
    if not name:
        return ""
    s = (name or "").strip()
    # Handle "Last, First" format
    if "," in s:
        parts = [p.strip() for p in s.split(",", 1)]
        if len(parts) == 2:
            s = f"{parts[1]} {parts[0]}"
    s = re.sub(r"[^\w\s]", "", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


# ============================================================
# RESOLVE SEEDS TO RANKED WRESTLERS
# ============================================================

def _build_rankings_index(rankings: List[dict]) -> Dict[str, List[dict]]:
    """Build index: norm_key -> list of wrestler dicts (sorted by rank for tie-break)."""
    index: Dict[str, List[dict]] = {}
    for w in rankings:
        name = (w.get("name") or "").strip()
        team = (w.get("team") or "").strip()
        if not name or not team:
            continue
        norm_key = _normalize_name_for_match(name) + "|" + _normalize_team(team)
        index.setdefault(norm_key, []).append(w)
    for k in index:
        index[k] = sorted(index[k], key=lambda x: (x.get("rank") or 9999, x.get("wrestler_id", "")))
    return index


def _search_rankings(rankings: List[dict], test_str: str) -> List[dict]:
    """Search rankings by substring in name or team. Case-insensitive."""
    norm = _normalize_name_for_match(test_str)
    if not norm:
        return []
    return [
        w
        for w in rankings
        if norm in _normalize_name_for_match(w.get("name", ""))
        or norm in _normalize_team(w.get("team", "")).lower()
    ]


def _interactive_resolve_seed(
    raw_name: str,
    raw_team: str,
    seed: int,
    rankings: List[dict],
    suggested_candidates: List[dict],
) -> dict:
    """
    Halt and prompt user to pick a wrestler from rankings.
    Returns chosen wrestler dict. Raises on cancel.
    """
    print()
    print("=" * 60)
    print("SEED NOT FOUND IN RANKINGS")
    print("=" * 60)
    print(f"  Seed {seed}: {raw_name} ({raw_team})")
    print()
    print("Enter a test string to search rankings (name or team substring):")
    print("  (or enter wrestler_id:XXXX to use a specific ID)")
    print()

    while True:
        try:
            test_str = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            raise RuntimeError(f"Interactive resolution cancelled for seed {seed}: {raw_name} ({raw_team})")
        if not test_str:
            print("Please enter a non-empty string.")
            continue

        if test_str.lower().startswith("wrestler_id:"):
            wid = test_str[12:].strip()
            if wid:
                for w in rankings:
                    if str(w.get("wrestler_id", "")) == wid:
                        return w
                print(f"  Wrestler ID {wid} not found in rankings.")
            continue

        matches = _search_rankings(rankings, test_str)
        if not matches:
            print(f"  No matches for '{test_str}'. Try another string.")
            continue

        while True:
            print(f"  Found {len(matches)} match(es):")
            for i, m in enumerate(matches[:20], 1):
                r = m.get("rank", "?")
                wid = m.get("wrestler_id", "")
                n = m.get("name", "")
                t = m.get("team", "")
                wgt = m.get("weight", "")
                wgt_str = f" @{wgt}lbs" if wgt else ""
                print(f"    {i}. #{r} {n} ({t}){wgt_str} [id={wid}]")
            if len(matches) > 20:
                print(f"    ... and {len(matches) - 20} more")
            print()
            print("Enter number to select, or another search string:")
            try:
                choice = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nAborted.")
                raise RuntimeError(f"Interactive resolution cancelled for seed {seed}: {raw_name} ({raw_team})")
            if not choice:
                continue
            if choice.isdigit():
                idx = int(choice)
                if 1 <= idx <= min(len(matches), 20):
                    return matches[idx - 1]
                print(f"  Invalid. Enter 1-{min(len(matches), 20)}.")
            else:
                test_str = choice
                matches = _search_rankings(rankings, test_str)
                if not matches:
                    print(f"  No matches for '{test_str}'. Try another string.")
                    break


def resolve_seeded_wrestlers(
    slot_entries: Dict[int, Tuple[str, str]],
    rankings: List[dict],
    seed_file_path: str,
    interactive_resolver_fn: Callable[[str, str, int, List[dict], List[dict]], dict],
    non_interactive: bool = False,
    rankings_search: Optional[List[dict]] = None,
    current_weight: Optional[int] = None,
) -> Dict[int, dict]:
    """
    Returns slot -> wrestler_obj from rankings.
    wrestler_obj includes: wrestler_id, name, team, rank.
    Uses persisted map (seed_file_path + ".map.json"), automatch, then interactive.
    rankings: current + adjacent weights (for automatch); each wrestler has "weight" field.
    rankings_search: all weights (for interactive lookup); defaults to rankings if None.
    current_weight: when multiple candidates match, prefer those from this weight.
    """
    path = Path(seed_file_path)
    map_path = path.parent / (path.name + ".map.json")
    search_list = rankings_search if rankings_search is not None else rankings
    rankings_by_id = {str(w.get("wrestler_id", "")): w for w in search_list if w.get("wrestler_id")}
    index = _build_rankings_index(rankings)

    persisted: Dict[str, str] = {}
    if map_path.exists():
        try:
            with map_path.open("r", encoding="utf-8") as f:
                persisted = json.load(f)
        except Exception:
            pass

    result: Dict[int, dict] = {}
    to_persist: Dict[str, str] = dict(persisted)

    for slot in sorted(slot_entries.keys()):
        raw_name, raw_team = slot_entries[slot]
        raw_key = f"{raw_name}|{raw_team}"

        # 1) Check persisted map
        if raw_key in to_persist:
            wid = to_persist[raw_key]
            if wid in rankings_by_id:
                result[slot] = rankings_by_id[wid]
                continue

        # 2) Automatch via norm_key (prefer current weight when multiple candidates)
        norm_key = _normalize_name_for_match(raw_name) + "|" + _normalize_team(raw_team)
        candidates = index.get(norm_key, [])

        if candidates:
            if current_weight is not None:
                at_weight = [w for w in candidates if w.get("weight") == current_weight]
                candidates = at_weight if at_weight else candidates
            chosen = min(candidates, key=lambda x: (x.get("rank") or 9999, x.get("wrestler_id", "")))
            result[slot] = chosen
            to_persist[raw_key] = str(chosen.get("wrestler_id", ""))
            continue

        # 3) Interactive resolve (or raise if non-interactive)
        if non_interactive:
            raise RuntimeError(
                f"Slot {slot} could not be resolved: {raw_name} ({raw_team}). "
                f"Run without --non-interactive to resolve interactively, or add mapping to {map_path}."
            )
        suggested = []
        norm_team = _normalize_team(raw_team)
        last_name = raw_name.split(",")[0].strip() if "," in raw_name else raw_name.split()[-1] if raw_name.split() else ""
        for w in search_list:
            if _normalize_team(w.get("team", "")) == norm_team:
                suggested.append(w)
            elif last_name and last_name.lower() in (w.get("name") or "").lower():
                suggested.append(w)
        suggested = list({id(w): w for w in suggested}.values())[:20]

        chosen = interactive_resolver_fn(raw_name, raw_team, slot, search_list, suggested)
        if not chosen:
            raise RuntimeError(f"Interactive resolution returned None for slot {slot}: {raw_name} ({raw_team})")
        result[slot] = chosen
        to_persist[raw_key] = str(chosen.get("wrestler_id", ""))

    # Persist map
    map_path.parent.mkdir(parents=True, exist_ok=True)
    with map_path.open("w", encoding="utf-8") as f:
        json.dump(to_persist, f, indent=2)
    return result


# ============================================================
# GIRLS BRACKET SIMULATION
# ============================================================

def _put_into_match(
    match_inputs: Dict[int, List[Optional[dict]]],
    match_id: int,
    wrestler_obj: dict,
) -> None:
    """Place wrestler into first None slot of match_inputs[match_id]. Raise if both slots filled."""
    slots = match_inputs[match_id]
    if slots[0] is None:
        slots[0] = wrestler_obj
    elif slots[1] is None:
        slots[1] = wrestler_obj
    else:
        raise RuntimeError(f"Match {match_id} already has both slots filled; cannot add wrestler")


def simulate_girls_bracket(
    slot_to_wrestler: Dict[int, dict],
    debug: bool = False,
) -> Tuple[List[dict], List[dict], Dict[int, dict], Dict[int, dict]]:
    """
    Simulate 16-man girls bracket. Returns (placements_ordered, blood_round_ordered, match_results, placements_by_place).
    Girls bracket: slot = seed. Opening matches use standard layout:
      Match 1=1v16, 2=8v9, 3=5v12, 4=4v13, 5=3v14, 6=6v11, 7=7v10, 8=2v15.
    Slots 1-16 required.
    Raises on any failure.
    """
    # Fail-fast: require all slots 1-16
    present = set(slot_to_wrestler.keys())
    missing = GIRLS_REQUIRED_SLOTS - present
    if missing:
        raise RuntimeError(
            f"Missing required slots for girls bracket: {sorted(missing)}. "
            f"Seed file must contain exactly slots 1-16."
        )

    match_inputs: Dict[int, List[Optional[dict]]] = {}
    for mid in GIRLS_BRACKET:
        match_inputs[mid] = [None, None]

    match_results: Dict[int, dict] = {}
    placements_by_place: Dict[int, dict] = {}
    blood_round_by_match: Dict[int, dict] = {}
    paths: Dict[str, List[int]] = {}

    # Opening matches: girls use standard bracket layout (1v16, 8v9, etc.)
    for match_id in range(1, GIRLS_OPENING_MATCH_COUNT + 1):
        slot_a, slot_b = GIRLS_OPENING_MATCH_SLOTS[match_id - 1]
        match_inputs[match_id][0] = slot_to_wrestler[slot_a]
        match_inputs[match_id][1] = slot_to_wrestler[slot_b]

    # Run simulation
    while True:
        progress = False
        for match_id in sorted(GIRLS_BRACKET.keys()):
            if match_id in match_results:
                continue
            slots = match_inputs[match_id]
            if slots[0] is None or slots[1] is None:
                continue

            a, b = slots[0], slots[1]
            rank_a = a.get("rank") or 9999
            rank_b = b.get("rank") or 9999
            winner = a if rank_a < rank_b else b
            loser = b if winner is a else a

            match_results[match_id] = {"winner": winner, "loser": loser}
            wid_w = str(winner.get("wrestler_id", ""))
            wid_l = str(loser.get("wrestler_id", ""))
            paths.setdefault(wid_w, []).append(match_id)
            paths.setdefault(wid_l, []).append(match_id)

            if match_id in GIRLS_BLOOD_ROUND_MATCHES:
                blood_round_by_match[match_id] = loser

            info = GIRLS_BRACKET[match_id]
            if "placement" in info:
                placements_by_place[info["placement"]["winner"]] = winner
                placements_by_place[info["placement"]["loser"]] = loser
            else:
                winner_to = info.get("winner_to")
                loser_to = info.get("loser_to")
                if winner_to is not None:
                    _put_into_match(match_inputs, winner_to, winner)
                if loser_to is not None:
                    _put_into_match(match_inputs, loser_to, loser)

            if debug:
                print(f"  Match {match_id}: #{winner.get('rank')} {winner.get('name')} ({winner.get('team')}) def. #{loser.get('rank')} {loser.get('name')} ({loser.get('team')})")
            progress = True

        if not progress:
            break

    # Post-condition checks
    for place in range(1, 9):
        if place not in placements_by_place:
            missing = [mid for mid in GIRLS_BRACKET if match_inputs[mid][0] and match_inputs[mid][1] and mid not in match_results]
            raise RuntimeError(
                f"Bracket stalled: placement {place} missing. "
                f"Matches lacking inputs: {missing}. "
                f"Match results so far: {list(match_results.keys())}"
            )

    for mid in GIRLS_BLOOD_ROUND_MATCHES:
        if mid not in blood_round_by_match:
            raise RuntimeError(f"Blood round match {mid} not resolved")

    placement_wrestler_ids = {str(w.get("wrestler_id", "")) for w in placements_by_place.values()}
    blood_wrestler_ids = {str(blood_round_by_match[m].get("wrestler_id", "")) for m in GIRLS_BLOOD_ROUND_MATCHES}
    if placement_wrestler_ids & blood_wrestler_ids:
        raise RuntimeError(f"Overlap between placements and blood round: {placement_wrestler_ids & blood_wrestler_ids}")

    all_placed = list(placements_by_place.values()) + [blood_round_by_match[m] for m in GIRLS_BLOOD_ROUND_MATCHES]
    if len(all_placed) != len({str(w.get("wrestler_id", "")) for w in all_placed}):
        raise RuntimeError(f"Duplicate wrestler in placements/blood round: {all_placed}")

    placements_ordered = [placements_by_place[i] for i in range(1, 9)]
    blood_round_ordered = [blood_round_by_match[m] for m in GIRLS_BLOOD_ROUND_MATCHES]

    if debug:
        for wid, p in paths.items():
            print(f"  Path {wid}: {p}")

    return placements_ordered, blood_round_ordered, match_results, placements_by_place


# ============================================================
# BOYS BRACKET SIMULATION
# ============================================================

def simulate_boys_bracket(
    slot_to_wrestler: Dict[int, dict],
    debug: bool = False,
) -> Tuple[List[dict], List[dict], Dict[int, dict], Dict[int, dict]]:
    """
    Simulate 32-man boys bracket. Returns (placements_ordered, blood_round_ordered, match_results, placements_by_place).
    Opening: Match N = slot (2*N-1) vs slot (2*N). Slots 1-32 required.
    Blood round = LOSERS of matches 49, 50, 51, 52 (order preserved).
    Raises on any failure.
    """
    # Fail-fast: require all slots 1-32
    present = set(slot_to_wrestler.keys())
    missing = BOYS_REQUIRED_SLOTS - present
    if missing:
        raise RuntimeError(
            f"Missing required slots for boys bracket: {sorted(missing)}. "
            f"Seed file must contain exactly slots 1-32."
        )

    match_inputs: Dict[int, List[Optional[dict]]] = {}
    for mid in BOYS_BRACKET:
        match_inputs[mid] = [None, None]

    match_results: Dict[int, dict] = {}
    placements_by_place: Dict[int, dict] = {}
    blood_round_by_match: Dict[int, dict] = {}
    paths: Dict[str, List[int]] = {}

    # Opening matches: Match N = slot (2*N-1) vs slot (2*N)
    for match_id in range(1, BOYS_OPENING_MATCH_COUNT + 1):
        slot_a = 2 * match_id - 1
        slot_b = 2 * match_id
        match_inputs[match_id][0] = slot_to_wrestler[slot_a]
        match_inputs[match_id][1] = slot_to_wrestler[slot_b]

    # Run simulation
    while True:
        progress = False
        for match_id in sorted(BOYS_BRACKET.keys()):
            if match_id in match_results:
                continue
            slots = match_inputs[match_id]
            if slots[0] is None or slots[1] is None:
                continue

            a, b = slots[0], slots[1]
            rank_a = a.get("rank") or 9999
            rank_b = b.get("rank") or 9999
            winner = a if rank_a < rank_b else b
            loser = b if winner is a else a

            match_results[match_id] = {"winner": winner, "loser": loser}
            wid_w = str(winner.get("wrestler_id", ""))
            wid_l = str(loser.get("wrestler_id", ""))
            paths.setdefault(wid_w, []).append(match_id)
            paths.setdefault(wid_l, []).append(match_id)

            if match_id in BOYS_BLOOD_ROUND_MATCHES:
                blood_round_by_match[match_id] = loser

            info = BOYS_BRACKET[match_id]
            if "placement" in info:
                placements_by_place[info["placement"]["winner"]] = winner
                placements_by_place[info["placement"]["loser"]] = loser
            else:
                winner_to = info.get("winner_to")
                loser_to = info.get("loser_to")
                if winner_to is not None:
                    _put_into_match(match_inputs, winner_to, winner)
                if loser_to is not None:
                    _put_into_match(match_inputs, loser_to, loser)

            if debug:
                print(
                    f"  Match {match_id}: #{winner.get('rank')} {winner.get('name')} ({winner.get('team')}) def. "
                    f"#{loser.get('rank')} {loser.get('name')} ({loser.get('team')})"
                )
            progress = True

        if not progress:
            break

    # Stall detection: dump debug info if simulation didn't complete
    missing_placements = [p for p in range(1, 9) if p not in placements_by_place]
    if missing_placements:
        lacking = [
            mid
            for mid in BOYS_BRACKET
            if match_inputs[mid][0] is None or match_inputs[mid][1] is None
            and mid not in match_results
        ]
        print("DEBUG: Bracket stalled")
        print(f"  Missing placements: {missing_placements}")
        print(f"  Matches lacking inputs: {lacking}")
        print(f"  Match results so far: {sorted(match_results.keys())}")
        for mid in lacking[:10]:
            print(f"    Match {mid}: {match_inputs[mid]}")
        raise RuntimeError(
            f"Bracket stalled: placements {missing_placements} missing. "
            f"Matches lacking inputs: {lacking}. "
            f"Match results: {list(match_results.keys())}"
        )

    for mid in BOYS_BLOOD_ROUND_MATCHES:
        if mid not in blood_round_by_match:
            raise RuntimeError(f"Blood round match {mid} not resolved")

    placement_wrestler_ids = {str(w.get("wrestler_id", "")) for w in placements_by_place.values()}
    blood_wrestler_ids = {
        str(blood_round_by_match[m].get("wrestler_id", "")) for m in BOYS_BLOOD_ROUND_MATCHES
    }
    if placement_wrestler_ids & blood_wrestler_ids:
        raise RuntimeError(
            f"Overlap between placements and blood round: {placement_wrestler_ids & blood_wrestler_ids}"
        )

    all_placed = list(placements_by_place.values()) + [
        blood_round_by_match[m] for m in BOYS_BLOOD_ROUND_MATCHES
    ]
    if len(all_placed) != len({str(w.get("wrestler_id", "")) for w in all_placed}):
        raise RuntimeError(f"Duplicate wrestler in placements/blood round: {all_placed}")

    placements_ordered = [placements_by_place[i] for i in range(1, 9)]
    blood_round_ordered = [blood_round_by_match[m] for m in BOYS_BLOOD_ROUND_MATCHES]

    if debug:
        for wid, p in paths.items():
            print(f"  Path {wid}: {p}")

    return placements_ordered, blood_round_ordered, match_results, placements_by_place


# ============================================================
# DISPLAY HELPERS (for SVG)
# ============================================================

def normalize_wrestler_name(name: str) -> str:
    """Capitalize first letter of each word."""
    if not name or not name.strip():
        return ""
    return " ".join(word.capitalize() for word in name.strip().split())


def format_wrestler_name_for_display(name: str, max_length: int = 20) -> str:
    """
    Format name for graphic display. If longer than max_length, use "F. LastName".
    Handles "Last, First" format.
    """
    if not name or not name.strip():
        return ""
    s = name.strip()
    if "," in s:
        parts = [p.strip() for p in s.split(",", 1)]
        if len(parts) == 2:
            s = f"{parts[1]} {parts[0]}"
    s = " ".join(word.title() for word in s.split())
    if len(s) <= max_length:
        return s
    words = s.split()
    if not words:
        return s
    first_initial = words[0][0].upper() + "."
    last_name = words[-1] if len(words) > 1 else ""
    if len(words) == 1:
        return s[:max_length] if len(s) > max_length else s
    return f"{first_initial} {last_name}"


def normalize_school_name(name: str) -> str:
    """School name in ALL CAPS."""
    if not name or not name.strip():
        return ""
    return name.strip().upper()


# ============================================================
# RANKINGS / ARCHIVE
# ============================================================

def load_archive_index(rankings_base: Path, gender: str, season: int) -> Optional[str]:
    """Load index.json and return latest drop ID."""
    path = rankings_base / gender / str(season) / "index.json"
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("latest")
    except Exception:
        return None


def load_rankings_for_weight(
    rankings_base: Path, gender: str, season: int, drop_id: str, weight: int
) -> List[dict]:
    """
    Load rankings from archive. Returns list of wrestler dicts with rank, name, team, wrestler_id.
    Falls back to rankings_starters_{weight}.json to include wrestlers outside top-24 archive.
    """
    seen_ids: set = set()
    result: List[dict] = []

    # Primary: archive (top 24/40)
    path = rankings_base / gender / str(season) / drop_id / f"{weight}.json"
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            for w in data.get("wrestlers") or []:
                if w.get("rank") is not None:
                    wid = str(w.get("wrestler_id", ""))
                    if wid and wid not in seen_ids:
                        seen_ids.add(wid)
                        result.append(w)
        except Exception:
            pass

    # Fallback: rankings_starters (broader set for seed resolution)
    starters_path = rankings_base / gender / str(season) / f"rankings_starters_{weight}.json"
    if starters_path.exists():
        try:
            with starters_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            for w in data.get("rankings") or []:
                wid = str(w.get("wrestler_id", ""))
                if wid and wid not in seen_ids:
                    seen_ids.add(wid)
                    result.append(w)
        except Exception:
            pass

    return result


def load_rankings_all_weights(
    rankings_base: Path, gender: str, season: int, drop_id: str, weights: List[int]
) -> List[dict]:
    """
    Load rankings from specified weight classes. Returns combined list.
    Each wrestler gets a "weight" field indicating which weight class they came from.
    """
    result: List[dict] = []
    for wgt in weights:
        for w in load_rankings_for_weight(rankings_base, gender, season, drop_id, wgt):
            w_copy = dict(w)
            w_copy["weight"] = wgt
            result.append(w_copy)
    return result


def load_public_rankings_all_weights(
    rankings_base: Path, gender: str, season: int, weights: List[int]
) -> List[dict]:
    """
    Load from public_rankings/all_weights.json (broader coverage including unranked).
    Used as fallback for interactive search when wrestler not in archive/starters.
    Returns same format: wrestler dicts with weight, rank, name, team, wrestler_id.
    """
    data_dir = rankings_base.parent
    path = data_dir / "public_rankings" / gender / str(season) / "all_weights.json"
    if not path.exists():
        return []
    result: List[dict] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        for wgt in weights:
            wgt_key = str(wgt)
            for w in data.get(wgt_key) or []:
                w_copy = {
                    "wrestler_id": w.get("wrestler_id"),
                    "rank": w.get("rank") or w.get("hybrid_rank"),
                    "name": w.get("name", ""),
                    "team": w.get("team", ""),
                }
                w_copy["weight"] = wgt
                if w_copy.get("wrestler_id") and w_copy.get("name"):
                    result.append(w_copy)
    except Exception:
        pass
    return result


def _weights_for_automatch(weight: int, all_weights: List[int]) -> List[int]:
    """
    Current weight first, then adjacent weights (one below, one above).
    Used for automatch fallback when wrestler not found at current weight.
    """
    if weight not in all_weights:
        return [weight]
    idx = all_weights.index(weight)
    result = [weight]
    if idx > 0:
        result.append(all_weights[idx - 1])
    if idx < len(all_weights) - 1:
        result.append(all_weights[idx + 1])
    return result


# ============================================================
# SVG / GRAPHIC HELPERS
# ============================================================

def _set_label_text(root: ET.Element, ns: dict, label: str, value: str) -> None:
    el = root.find(f".//*[@inkscape:label='{label}']", namespaces=ns)
    if el is None:
        return
    tspan = el.find("svg:tspan", ns) if el.tag.endswith("text") else None
    target = tspan if tspan is not None else el
    target.text = value or ""


def _set_text_in_element(el: ET.Element, ns: dict, value: str) -> None:
    if el is None:
        return
    tspan = el.find("svg:tspan", ns)
    if tspan is None:
        el.text = value or ""
        return
    inner = tspan.find("svg:tspan", ns)
    target = inner if inner is not None else tspan
    target.text = value or ""


def _find_inkscape() -> Optional[str]:
    exe = shutil.which("inkscape")
    if exe:
        return exe
    mac_path = Path("/Applications/Inkscape.app/Contents/MacOS/inkscape")
    if mac_path.is_file():
        return str(mac_path)
    return None


def _export_svg_to_jpg_inkscape(
    svg_path: Path,
    jpg_path: Path,
    width: int = 1500,
    height: int = 1500,
    preserve_aspect_ratio: bool = False,
) -> Tuple[bool, Optional[str]]:
    inkscape = _find_inkscape()
    if not inkscape:
        return False, "Inkscape not found"
    try:
        from PIL import Image
    except ImportError:
        return False, "PIL/Pillow not installed"
    png_path = jpg_path.with_suffix(".png")
    cmd = [
        inkscape,
        str(svg_path),
        "--export-type=png",
        f"--export-filename={png_path}",
        f"--export-width={width}",
    ]
    if not preserve_aspect_ratio:
        cmd.append(f"--export-height={height}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip() or f"exit code {result.returncode}"
            if png_path.exists():
                png_path.unlink(missing_ok=True)
            return False, f"Inkscape failed: {err}"
        img = Image.open(png_path).convert("RGB")
        img.save(jpg_path, format="JPEG", quality=95)
        png_path.unlink(missing_ok=True)
        return True, None
    except Exception as e:
        if png_path.exists():
            png_path.unlink(missing_ok=True)
        return False, str(e)


TEAM_RANK_LABELS = ["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th", "10th"]


def _generate_team_predictions_graphic(
    team_totals: Dict[str, float],
    wrestler_points: Dict[str, Dict[str, float]],
    wrestler_info: Dict[str, dict],
    template_path: Path,
    out_dir: Path,
    output_basename: str,
) -> bool:
    """
    Fill team predictions template with top 10 teams.
    Writes SVG and exports JPG via Inkscape.
    """
    if not template_path.exists():
        print(f"  Team template not found: {template_path}")
        return False

    def count_wrestlers(team: str) -> int:
        """Count all wrestlers from team who are in the bracket (seed files), including 0-2."""
        return len(
            [
                wid
                for wid in wrestler_points
                if wrestler_info.get(wid, {}).get("team") == team
            ]
        )

    sorted_teams = sorted(
        team_totals.items(), key=lambda x: x[1], reverse=True
    )[:10]

    ns = {
        "svg": "http://www.w3.org/2000/svg",
        "inkscape": "http://www.inkscape.org/namespaces/inkscape",
    }
    tree = ET.parse(template_path)
    root = tree.getroot()

    for i, label in enumerate(TEAM_RANK_LABELS):
        group = root.find(f".//*[@inkscape:label='{label}']", namespaces=ns)
        if group is None:
            continue
        if i < len(sorted_teams):
            team_name, pts = sorted_teams[i]
            team_display = (team_name or "").strip().title()
            qty = count_wrestlers(team_name)
            pts_rounded = round(pts * 2) / 2
            rank_str = str(i + 1)
        else:
            team_display = ""
            qty = 0
            pts_rounded = 0.0
            rank_str = ""

        for sublabel, val in [
            ("team", team_display),
            ("rank", rank_str),
            ("qty", str(qty) if qty else ""),
            ("pts", str(pts_rounded) if pts_rounded else ""),
        ]:
            el = group.find(f".//*[@inkscape:label='{sublabel}']", namespaces=ns)
            if el is not None:
                _set_text_in_element(el, ns, str(val) if val else "")

    out_dir.mkdir(parents=True, exist_ok=True)
    svg_path = out_dir / f"{output_basename}.svg"
    jpg_path = out_dir / f"{output_basename}.jpg"
    tree.write(svg_path, encoding="utf-8", xml_declaration=True)
    print(f"  ✓ Team SVG: {svg_path}")

    inkscape_ok, inkscape_err = _export_svg_to_jpg_inkscape(
        svg_path, jpg_path, width=1500, preserve_aspect_ratio=True
    )
    if inkscape_ok:
        print(f"  ✓ Team JPG: {jpg_path}")
    else:
        if inkscape_err:
            print(f"  (Team JPG skipped: {inkscape_err})")

    return True


# ============================================================
# GIRLS PREDICTION (16-MAN BRACKET)
# ============================================================

def _generate_girls_state_predictions(
    rankings_base: Path,
    season: int,
    weight: int,
    template_path: Path,
    out_dir: Path,
    debug: bool = False,
    non_interactive: bool = False,
) -> Tuple[bool, Optional[Dict[int, dict]], Optional[Dict[int, dict]]]:
    """Girls: seeded 16-man bracket simulation. Uses seed file + rankings."""
    drop_id = load_archive_index(rankings_base, "girls", season)
    if not drop_id:
        print(f"  No archive index for girls {season}")
        return False, None, None

    rankings = load_rankings_for_weight(rankings_base, "girls", season, drop_id, weight)
    if not rankings:
        print(f"  No rankings for girls {weight} lbs")
        return False, None, None

    rankings_automatch = load_rankings_all_weights(
        rankings_base, "girls", season, drop_id, _weights_for_automatch(weight, HS_GIRLS_WEIGHTS)
    )
    rankings_all = load_rankings_all_weights(
        rankings_base, "girls", season, drop_id, HS_GIRLS_WEIGHTS
    )
    public_rankings = load_public_rankings_all_weights(
        rankings_base, "girls", season, HS_GIRLS_WEIGHTS
    )
    seen_ids = {str(w.get("wrestler_id", "")) for w in rankings_all}
    for w in public_rankings:
        if str(w.get("wrestler_id", "")) not in seen_ids:
            seen_ids.add(str(w.get("wrestler_id", "")))
            rankings_all.append(w)

    seed_file_path = PROJECT_ROOT / "data" / "hs_ky_girls" / "States" / str(weight)
    if not Path(seed_file_path).exists():
        raise FileNotFoundError(
            f"Seed file not found: {seed_file_path}. "
            f"Create a tab-separated file with columns: seed, name, team (e.g. '1.\tBrown, Bijou\tWoodford County')"
        )

    slot_entries = parse_seed_file(str(seed_file_path))
    missing = GIRLS_REQUIRED_SLOTS - set(slot_entries.keys())
    if missing:
        raise RuntimeError(
            f"Seed file {seed_file_path} missing required slots: {sorted(missing)}. "
            f"Must have slots 1-16. Found: {sorted(slot_entries.keys())}"
        )

    slot_to_wrestler = resolve_seeded_wrestlers(
        slot_entries,
        rankings_automatch,
        str(seed_file_path),
        _interactive_resolve_seed,
        non_interactive=non_interactive,
        rankings_search=rankings_all,
        current_weight=weight,
    )

    placements_ordered, blood_round_ordered, match_results, placements_by_place = simulate_girls_bracket(
        slot_to_wrestler, debug=debug
    )

    # Feed SVG with placements 1..8 and br1..br4
    ns = {
        "svg": "http://www.w3.org/2000/svg",
        "inkscape": "http://www.inkscape.org/namespaces/inkscape",
    }
    tree = ET.parse(template_path)
    root = tree.getroot()

    _set_label_text(root, ns, "Weight-Class", f"{weight} lbs")

    for i, label in enumerate(PLACEMENT_LABELS):
        group = root.find(f".//*[@inkscape:label='{label}']", namespaces=ns)
        if group is None:
            continue
        if i < len(placements_ordered):
            w = placements_ordered[i]
            rank = w.get("rank", "?")
            name = f"#{rank} {format_wrestler_name_for_display(w.get('name') or '')}"
            team = normalize_school_name(w.get("team") or "")
            wrestler_el = group.find(f".//*[@inkscape:label='wrestler-name']", namespaces=ns)
            school_el = group.find(f".//*[@inkscape:label='school-name']", namespaces=ns)
            if wrestler_el is not None:
                _set_text_in_element(wrestler_el, ns, name)
            if school_el is not None:
                _set_text_in_element(school_el, ns, team)
        else:
            wrestler_el = group.find(f".//*[@inkscape:label='wrestler-name']", namespaces=ns)
            school_el = group.find(f".//*[@inkscape:label='school-name']", namespaces=ns)
            if wrestler_el is not None:
                _set_text_in_element(wrestler_el, ns, "")
            if school_el is not None:
                _set_text_in_element(school_el, ns, "")

    for i, label in enumerate(BLOOD_ROUND_LABELS):
        group = root.find(f".//*[@inkscape:label='{label}']", namespaces=ns)
        if group is None:
            continue
        if i < len(blood_round_ordered):
            w = blood_round_ordered[i]
            rank = w.get("rank", "?")
            name = f"#{rank} {format_wrestler_name_for_display(w.get('name') or '')}"
            team = normalize_school_name(w.get("team") or "")
            wrestler_el = group.find(f".//*[@inkscape:label='wrestler-name']", namespaces=ns)
            school_el = group.find(f".//*[@inkscape:label='school-name']", namespaces=ns)
            if wrestler_el is not None:
                _set_text_in_element(wrestler_el, ns, name)
            if school_el is not None:
                _set_text_in_element(school_el, ns, team)
        else:
            wrestler_el = group.find(f".//*[@inkscape:label='wrestler-name']", namespaces=ns)
            school_el = group.find(f".//*[@inkscape:label='school-name']", namespaces=ns)
            if wrestler_el is not None:
                _set_text_in_element(wrestler_el, ns, "")
            if school_el is not None:
                _set_text_in_element(school_el, ns, "")

    out_dir.mkdir(parents=True, exist_ok=True)
    svg_path = out_dir / f"girls_{weight}.svg"
    jpg_path = out_dir / f"girls_{weight}.jpg"
    tree.write(svg_path, encoding="utf-8", xml_declaration=True)
    print(f"  ✓ SVG: {svg_path}")

    inkscape_ok, inkscape_err = _export_svg_to_jpg_inkscape(svg_path, jpg_path)
    if inkscape_ok:
        print(f"  ✓ JPG: {jpg_path}")
    else:
        if inkscape_err:
            print(f"  (JPG skipped: {inkscape_err})")

    return True, match_results, placements_by_place


# ============================================================
# BOYS PREDICTION (32-MAN BRACKET)
# ============================================================

def _generate_boys_state_predictions(
    rankings_base: Path,
    season: int,
    weight: int,
    template_path: Path,
    out_dir: Path,
    debug: bool = False,
    non_interactive: bool = False,
) -> Tuple[bool, Optional[Dict[int, dict]], Optional[Dict[int, dict]]]:
    """Boys: seeded 32-man bracket simulation. Uses seed file + rankings."""
    drop_id = load_archive_index(rankings_base, "boys", season)
    if not drop_id:
        print(f"  No archive index for boys {season}")
        return False, None, None

    rankings = load_rankings_for_weight(rankings_base, "boys", season, drop_id, weight)
    if not rankings:
        print(f"  No rankings for boys {weight} lbs")
        return False, None, None

    rankings_automatch = load_rankings_all_weights(
        rankings_base, "boys", season, drop_id, _weights_for_automatch(weight, HS_BOYS_WEIGHTS)
    )
    rankings_all = load_rankings_all_weights(
        rankings_base, "boys", season, drop_id, HS_BOYS_WEIGHTS
    )
    public_rankings = load_public_rankings_all_weights(
        rankings_base, "boys", season, HS_BOYS_WEIGHTS
    )
    seen_ids = {str(w.get("wrestler_id", "")) for w in rankings_all}
    for w in public_rankings:
        if str(w.get("wrestler_id", "")) not in seen_ids:
            seen_ids.add(str(w.get("wrestler_id", "")))
            rankings_all.append(w)

    seed_file_path = PROJECT_ROOT / "data" / "hs_ky_boys" / "States" / str(weight)
    if not Path(seed_file_path).exists():
        raise FileNotFoundError(
            f"Seed file not found: {seed_file_path}. "
            f"Create a tab-separated file with columns: seed, name, team (e.g. '1.\tSmith, John\tTeam Name')"
        )

    slot_entries = parse_seed_file(str(seed_file_path))
    missing = BOYS_REQUIRED_SLOTS - set(slot_entries.keys())
    if missing:
        raise RuntimeError(
            f"Seed file {seed_file_path} missing required slots: {sorted(missing)}. "
            f"Must have slots 1-32. Found: {sorted(slot_entries.keys())}"
        )

    slot_to_wrestler = resolve_seeded_wrestlers(
        slot_entries,
        rankings_automatch,
        str(seed_file_path),
        _interactive_resolve_seed,
        non_interactive=non_interactive,
        rankings_search=rankings_all,
        current_weight=weight,
    )

    placements_ordered, blood_round_ordered, match_results, placements_by_place = simulate_boys_bracket(
        slot_to_wrestler, debug=debug
    )

    # Feed SVG with placements 1..8 and br1..br4 (same structure as girls)
    ns = {
        "svg": "http://www.w3.org/2000/svg",
        "inkscape": "http://www.inkscape.org/namespaces/inkscape",
    }
    tree = ET.parse(template_path)
    root = tree.getroot()

    _set_label_text(root, ns, "Weight-Class", f"{weight} lbs")

    for i, label in enumerate(PLACEMENT_LABELS):
        group = root.find(f".//*[@inkscape:label='{label}']", namespaces=ns)
        if group is None:
            continue
        if i < len(placements_ordered):
            w = placements_ordered[i]
            rank = w.get("rank", "?")
            name = f"#{rank} {format_wrestler_name_for_display(w.get('name') or '')}"
            team = normalize_school_name(w.get("team") or "")
            wrestler_el = group.find(f".//*[@inkscape:label='wrestler-name']", namespaces=ns)
            school_el = group.find(f".//*[@inkscape:label='school-name']", namespaces=ns)
            if wrestler_el is not None:
                _set_text_in_element(wrestler_el, ns, name)
            if school_el is not None:
                _set_text_in_element(school_el, ns, team)
        else:
            wrestler_el = group.find(f".//*[@inkscape:label='wrestler-name']", namespaces=ns)
            school_el = group.find(f".//*[@inkscape:label='school-name']", namespaces=ns)
            if wrestler_el is not None:
                _set_text_in_element(wrestler_el, ns, "")
            if school_el is not None:
                _set_text_in_element(school_el, ns, "")

    for i, label in enumerate(BLOOD_ROUND_LABELS):
        group = root.find(f".//*[@inkscape:label='{label}']", namespaces=ns)
        if group is None:
            continue
        if i < len(blood_round_ordered):
            w = blood_round_ordered[i]
            rank = w.get("rank", "?")
            name = f"#{rank} {format_wrestler_name_for_display(w.get('name') or '')}"
            team = normalize_school_name(w.get("team") or "")
            wrestler_el = group.find(f".//*[@inkscape:label='wrestler-name']", namespaces=ns)
            school_el = group.find(f".//*[@inkscape:label='school-name']", namespaces=ns)
            if wrestler_el is not None:
                _set_text_in_element(wrestler_el, ns, name)
            if school_el is not None:
                _set_text_in_element(school_el, ns, team)
        else:
            wrestler_el = group.find(f".//*[@inkscape:label='wrestler-name']", namespaces=ns)
            school_el = group.find(f".//*[@inkscape:label='school-name']", namespaces=ns)
            if wrestler_el is not None:
                _set_text_in_element(wrestler_el, ns, "")
            if school_el is not None:
                _set_text_in_element(school_el, ns, "")

    out_dir.mkdir(parents=True, exist_ok=True)
    svg_path = out_dir / f"boys_{weight}.svg"
    jpg_path = out_dir / f"boys_{weight}.jpg"
    tree.write(svg_path, encoding="utf-8", xml_declaration=True)
    print(f"  ✓ SVG: {svg_path}")

    inkscape_ok, inkscape_err = _export_svg_to_jpg_inkscape(svg_path, jpg_path)
    if inkscape_ok:
        print(f"  ✓ JPG: {jpg_path}")
    else:
        if inkscape_err:
            print(f"  (JPG skipped: {inkscape_err})")

    return True, match_results, placements_by_place


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate state predictions graphics (girls: 16-man seeded bracket)"
    )
    parser.add_argument("--season", type=int, default=2026, help="Season year")
    parser.add_argument(
        "-gender",
        type=str,
        choices=["girls", "boys"],
        default="girls",
        help="Gender (girls: 16-man bracket, boys: 32-man bracket)",
    )
    parser.add_argument(
        "--weight",
        type=int,
        default=None,
        help="Single weight class (e.g. 100); default all for gender",
    )
    parser.add_argument(
        "--rankings-dir",
        type=str,
        default=None,
        help="Override rankings base dir",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print bracket match results and wrestler paths",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Fail if any seed needs interactive resolution (for CI/batch)",
    )
    args = parser.parse_args()

    rankings_base = (
        Path(args.rankings_dir)
        if args.rankings_dir
        else PROJECT_ROOT / "frontend" / "hs-ky-ui" / "public" / "data" / "rankings"
    )

    if args.gender == "girls":
        weights = HS_GIRLS_WEIGHTS
        template_path = (
            PROJECT_ROOT
            / "mt"
            / "graphics"
            / "templates"
            / "State-Predictions"
            / "girls"
            / "Girls-States-Predictions-Template.svg"
        )
        team_template_path = (
            PROJECT_ROOT
            / "mt"
            / "graphics"
            / "templates"
            / "State-Predictions"
            / "girls"
            / "Girls-States-Teams-Predictions-Template.svg"
        )
        out_dir = PROJECT_ROOT / "mt" / "graphics" / "State-Predictions" / "girls"
        team_output_basename = "girls_teams"
        title = "STATE PREDICTIONS GRAPHICS (GIRLS 16-MAN BRACKET)"
    else:
        weights = HS_BOYS_WEIGHTS
        template_path = (
            PROJECT_ROOT
            / "mt"
            / "graphics"
            / "templates"
            / "State-Predictions"
            / "boys"
            / "Boys-States-Predictions-Template.svg"
        )
        team_template_path = (
            PROJECT_ROOT
            / "mt"
            / "graphics"
            / "templates"
            / "State-Predictions"
            / "boys"
            / "Boys-States-Teams-Predictions-Template copy.svg"
        )
        out_dir = PROJECT_ROOT / "mt" / "graphics" / "State-Predictions" / "boys"
        team_output_basename = "boys_teams"
        title = "STATE PREDICTIONS GRAPHICS (BOYS 32-MAN BRACKET)"

    if args.weight is not None:
        if args.weight not in weights:
            print(f"Invalid weight {args.weight} for {args.gender}. Valid: {weights}")
            return
        weights = [args.weight]

    if not template_path.exists():
        print(f"Template not found: {template_path}")
        return

    print("=" * 60)
    print(title)
    print("=" * 60)
    print(f"Gender: {args.gender}, Season: {args.season}")
    print(f"Weights: {weights}")
    if args.debug:
        print("(debug mode: match-by-match output enabled)")
    print()

    results_per_weight: List[Tuple[Dict[int, dict], Dict[int, dict]]] = []

    for weight in weights:
        print(f"{args.gender.capitalize()} {weight} lbs:")
        if args.gender == "girls":
            ok, match_results, placements_by_place = _generate_girls_state_predictions(
                rankings_base,
                args.season,
                weight,
                template_path,
                out_dir,
                debug=args.debug,
                non_interactive=args.non_interactive,
            )
        else:
            ok, match_results, placements_by_place = _generate_boys_state_predictions(
                rankings_base,
                args.season,
                weight,
                template_path,
                out_dir,
                debug=args.debug,
                non_interactive=args.non_interactive,
            )
        if ok and match_results is not None and placements_by_place is not None:
            results_per_weight.append((match_results, placements_by_place))
        print()

    print("=" * 60)
    print(f"Output: {out_dir}")
    print("=" * 60)

    if results_per_weight:
        champ_set = GIRLS_CHAMP_MATCHES if args.gender == "girls" else BOYS_CHAMP_MATCHES
        placement_set = (
            GIRLS_PLACEMENT_MATCHES if args.gender == "girls" else BOYS_PLACEMENT_MATCHES
        )
        team_totals, team_breakdown, wrestler_points, wrestler_info = compute_team_scores(
            results_per_weight, champ_set, placement_set
        )

        sorted_teams = sorted(
            team_totals.items(), key=lambda x: x[1], reverse=True
        )
        print()
        print("=" * 60)
        print("TEAM POINTS (ESTIMATED)")
        print("=" * 60)
        for i, (team, pts) in enumerate(sorted_teams[:10], 1):
            pts_rounded = round(pts * 2) / 2
            print(f"  {i:2}. {team}: {pts_rounded} pts")
        print()

        for i, (team, pts) in enumerate(sorted_teams[:3], 1):
            print(f"--- Top {i}: {team} (itemized) ---")
            team_wrestlers = [
                (wid, wp)
                for wid, wp in wrestler_points.items()
                if wrestler_info.get(wid, {}).get("team") == team and wp["total"] > 0
            ]
            team_wrestlers.sort(key=lambda x: x[1]["total"], reverse=True)
            for wid, wp in team_wrestlers:
                info = wrestler_info.get(wid, {})
                name = info.get("name", "?")
                total = round(wp["total"] * 2) / 2
                print(f"    {name}: {total} pts (adv={wp['adv']}, place={wp['place']}, bonus={wp['bonus']})")
            print()

        if args.debug and team_breakdown:
            print("--- Team breakdown (debug) ---")
            for team in sorted_teams[:10]:
                t = team[0]
                b = team_breakdown.get(t, {})
                print(f"  {t}: adv={b.get('adv',0)}, place={b.get('place',0)}, bonus={b.get('bonus',0)}, total={b.get('total',0)}")

        print()
        _generate_team_predictions_graphic(
            team_totals,
            wrestler_points,
            wrestler_info,
            team_template_path,
            out_dir,
            team_output_basename,
        )


if __name__ == "__main__":
    main()
