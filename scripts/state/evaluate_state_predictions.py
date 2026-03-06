#!/usr/bin/env python3
"""
Evaluate state tournament predictions against actual results.

For boys: matches from KHSAA Boys/Coed State Championship on 2/26, 2/27, or 2/28.
Predictions: higher-ranked wrestler wins (using most recent rankings prior to 2/26).

Usage:
  python scripts/state/evaluate_state_predictions.py --season 2026
  python scripts/state/evaluate_state_predictions.py --season 2026 -gender boys
"""

import argparse
import json
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# State tournament dates are derived from season (Feb 26-28 of season year)
STATE_EVENT_BOYS = "KHSAA Boys/Coed State Championship"
STATE_EVENT_GIRLS = "KHSAA Girls State Championship"

# Tournament start date - use rankings from most recent drop before this
TOURNAMENT_START_MMDD = "02/26"

# Skip these result types (no real opponent)
SKIP_RESULTS = {"BYE", "For."}

# Placement points (standard team scoring)
PLACEMENT_POINTS = {1: 20, 2: 16, 3: 12, 4: 10, 5: 8, 6: 6, 7: 4, 8: 2}

# Impressiveness constants
IMPRESS_A, IMPRESS_B = 0.03, 0.10  # BracketMult: a*RP + b*RC
IMPRESS_C = 0.08  # PathMult: c * PathScore
IMPRESS_BRACKET_CAP = 1.40
IMPRESS_PATH_CAP = 1.35
PLACEMENT_WEIGHT = {1: 1.00, 2: 0.85, 3: 0.75, 4: 0.65, 5: 0.50, 6: 0.40, 7: 0.25, 8: 0.15}
ROUND_MULT = {"F": 1.30, "SF": 1.15, "QF": 1.00, "Early": 0.80}

# Upset run constants
UNRANKED = 999
EFFECTIVE_RANK_CAP = 40
PLACEMENT_WEIGHT_UPSET = {1: 2.5, 2: 2.2, 3: 2.0, 4: 1.8, 5: 1.5, 6: 1.3, 7: 1.1, 8: 1.0}
ROUND_WEIGHT_UPSET = {"final": 1.5, "semi": 1.3, "quarter": 1.2, "blood": 1.2, "early": 1.0}
COMBO_MULT_PER_RANKED_WIN = 0.15


def _state_dates_for_season(season: int) -> Set[str]:
    """Return MM/DD/YYYY dates for state tournament (Feb 26, 27, 28)."""
    return {f"02/26/{season}", f"02/27/{season}", f"02/28/{season}"}


def _collect_state_matches(
    processed_dir: Path,
    gender: str,
    season: int,
    state_dates: Set[str],
    state_event: str,
) -> List[Tuple[int, str, str, str, str, str, str]]:
    """
    Collect unique state tournament matches from processed team data.
    Returns list of (weight, winner_id, loser_id, winner_name, loser_name, winner_team, loser_team).
    Skips BYE, For., Unknown opponents.
    """
    data_dir = processed_dir / f"hs_ky_{gender}" / str(season)
    if not data_dir.exists():
        return []

    seen: Set[Tuple[int, FrozenSet[str]]] = set()
    matches: List[Tuple[int, str, str, str, str, str, str]] = []

    for team_file in sorted(data_dir.glob("*.json")):
        try:
            with team_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        roster = data.get("roster") or []
        for wrestler in roster:
            wid = str(wrestler.get("season_wrestler_id", ""))
            if not wid:
                continue

            for m in wrestler.get("matches") or []:
                event = (m.get("event") or "").strip()
                if state_event not in event:
                    continue

                date = (m.get("date") or "").strip()
                if date not in state_dates:
                    continue

                result = (m.get("result") or "").strip()
                if result in SKIP_RESULTS:
                    continue

                winner_name = (m.get("winner_name") or "").strip()
                loser_name = (m.get("loser_name") or "").strip()
                winner_team = (m.get("winner_team") or "").strip()
                loser_team = (m.get("loser_team") or "").strip()
                if not winner_name or not loser_name or "Unknown" in (winner_name, loser_name):
                    continue

                opponent_id = m.get("opponent_id")
                if opponent_id is None or opponent_id == "" or str(opponent_id) == "-1":
                    continue

                weight_str = (m.get("weight") or "").strip()
                if not weight_str or not weight_str.isdigit():
                    continue
                weight = int(weight_str)

                # Determine winner_id and loser_id from roster wrestler + opponent
                roster_name = (wrestler.get("name") or "").strip()
                if roster_name == winner_name:
                    winner_id, loser_id = wid, str(opponent_id)
                elif roster_name == loser_name:
                    winner_id, loser_id = str(opponent_id), wid
                else:
                    continue

                key = (weight, frozenset([winner_id, loser_id]))
                if key in seen:
                    continue
                seen.add(key)
                matches.append((weight, winner_id, loser_id, winner_name, loser_name, winner_team, loser_team))

    return matches


def _collect_actual_placements(
    processed_dir: Path,
    gender: str,
    season: int,
    state_dates: Set[str],
    state_event: str,
) -> Dict[int, Dict[int, str]]:
    """
    Extract actual 1st-8th place wrestler IDs per weight from state placement matches.
    Returns dict: weight -> {1: winner_id, 2: loser_id, 3: winner_id, ... 8: loser_id}
    Excludes Junior Varsity matches.
    """
    data_dir = processed_dir / f"hs_ky_{gender}" / str(season)
    if not data_dir.exists():
        return {}

    # placement match summary pattern -> (winner_place, loser_place)
    placement_matches = {
        "1st Place Match": (1, 2),
        "3rd Place Match": (3, 4),
        "5th Place Match": (5, 6),
        "7th Place Match": (7, 8),
    }

    # weight -> place -> wrestler_id (take first occurrence per weight/place)
    result: Dict[int, Dict[int, str]] = {}

    for team_file in sorted(data_dir.glob("*.json")):
        try:
            with team_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        roster = data.get("roster") or []
        for wrestler in roster:
            wid = str(wrestler.get("season_wrestler_id", ""))
            if not wid:
                continue

            for m in wrestler.get("matches") or []:
                event = (m.get("event") or "").strip()
                if state_event not in event:
                    continue

                date = (m.get("date") or "").strip()
                if date not in state_dates:
                    continue

                summary = (m.get("summary") or "").strip()
                if "Junior Varsity" in summary:
                    continue

                opponent_id = m.get("opponent_id")
                if opponent_id is None or opponent_id == "" or str(opponent_id) == "-1":
                    continue

                weight_str = (m.get("weight") or "").strip()
                if not weight_str or not weight_str.isdigit():
                    continue
                weight = int(weight_str)

                winner_name = (m.get("winner_name") or "").strip()
                loser_name = (m.get("loser_name") or "").strip()
                roster_name = (wrestler.get("name") or "").strip()

                if roster_name == winner_name:
                    winner_id, loser_id = wid, str(opponent_id)
                elif roster_name == loser_name:
                    winner_id, loser_id = str(opponent_id), wid
                else:
                    continue

                for pattern, (wp, lp) in placement_matches.items():
                    if pattern in summary:
                        if weight not in result:
                            result[weight] = {}
                        if wp not in result[weight]:
                            result[weight][wp] = winner_id
                        if lp not in result[weight]:
                            result[weight][lp] = loser_id
                        break

    return result


def _bonus_points_from_result(result: str) -> float:
    """Bonus points: Major=1, Tech=1.5, Fall/DQ/Injury=2."""
    r = (result or "").strip().upper()
    if "FALL" in r or "DQ" in r or "INJ" in r or "INJURY" in r or "M. FOR" in r or "FOR." == r:
        return 2.0
    if "TF" in r or "TECH" in r:
        return 1.5
    if "MD" in r or "MAJOR" in r:
        return 1.0
    return 0.0


def _is_winners_bracket_win(summary: str) -> bool:
    """True if this is a championship bracket win (not finals, not consolation)."""
    s = (summary or "").strip()
    if "Junior Varsity" in s:
        return False
    if "1st Place Match" in s or "2nd Place Match" in s:
        return False  # Finals - no advancement per user spec
    if "Cons." in s or "Consolation" in s:
        return False
    if "Champ." in s or "Quarterfinals" in s or "Semifinals" in s:
        return True
    return False


def _compute_wrestler_state_points(
    processed_dir: Path,
    gender: str,
    season: int,
    state_dates: Set[str],
    state_event: str,
    actual_placements: Dict[int, Dict[int, str]],
) -> List[Tuple[str, str, str, int, float]]:
    """
    Compute team points per wrestler at state tournament.
    Returns list of (wrestler_id, name, team, weight, points) sorted by points desc.
    Scoring: placement (20/16/12/10/8/6/4/2) + 1 per winners bracket win (except finals)
    + bonus (Major=1, Tech=1.5, Fall/DQ/Injury=2).
    """
    data_dir = processed_dir / f"hs_ky_{gender}" / str(season)
    if not data_dir.exists():
        return []

    # wrestler_id -> (name, team, weight, points)
    points_by_id: Dict[str, Tuple[str, str, int, float]] = {}
    seen_matches: Set[Tuple[int, FrozenSet[str]]] = set()

    for team_file in sorted(data_dir.glob("*.json")):
        try:
            with team_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        roster = data.get("roster") or []
        for wrestler in roster:
            wid = str(wrestler.get("season_wrestler_id", ""))
            if not wid:
                continue

            for m in wrestler.get("matches") or []:
                event = (m.get("event") or "").strip()
                if state_event not in event:
                    continue

                date = (m.get("date") or "").strip()
                if date not in state_dates:
                    continue

                summary = (m.get("summary") or "").strip()
                if "Junior Varsity" in summary:
                    continue

                result = (m.get("result") or "").strip()
                if result in SKIP_RESULTS:
                    continue

                winner_name = (m.get("winner_name") or "").strip()
                winner_team = (m.get("winner_team") or "").strip()
                loser_name = (m.get("loser_name") or "").strip()
                if not winner_name or not loser_name or "Unknown" in (winner_name, loser_name):
                    continue

                opponent_id = m.get("opponent_id")
                if opponent_id is None or opponent_id == "" or str(opponent_id) == "-1":
                    continue

                weight_str = (m.get("weight") or "").strip()
                if not weight_str or not weight_str.isdigit():
                    continue
                weight = int(weight_str)

                roster_name = (wrestler.get("name") or "").strip()
                if roster_name == winner_name:
                    winner_id, loser_id = wid, str(opponent_id)
                elif roster_name == loser_name:
                    continue  # Loser gets no points from this match
                else:
                    continue

                key = (weight, frozenset([winner_id, loser_id]))
                if key in seen_matches:
                    continue
                seen_matches.add(key)

                # Advancement: 1 for winners bracket win (except finals)
                adv = 1.0 if _is_winners_bracket_win(summary) else 0.0
                bonus = _bonus_points_from_result(result)

                if winner_id not in points_by_id:
                    points_by_id[winner_id] = (winner_name, winner_team, weight, 0.0)
                name, team, wgt, pts = points_by_id[winner_id]
                points_by_id[winner_id] = (name, team, wgt, pts + adv + bonus)

    # Add placement points
    for weight, placements in actual_placements.items():
        for place, wrestler_id in placements.items():
            pts = PLACEMENT_POINTS.get(place, 0)
            if pts and wrestler_id:
                if wrestler_id not in points_by_id:
                    points_by_id[wrestler_id] = ("?", "?", weight, 0.0)
                name, team, wgt, total = points_by_id[wrestler_id]
                points_by_id[wrestler_id] = (name, team, wgt, total + pts)

    result_list = [
        (wid, name, team, weight, total)
        for wid, (name, team, weight, total) in points_by_id.items()
        if total > 0
    ]
    result_list.sort(key=lambda x: x[4], reverse=True)
    return result_list


def _get_bracket_predicted_placements(
    rankings_base: Path,
    season: int,
    weights: List[int],
    gender: str,
) -> Dict[int, Dict[int, str]]:
    """
    Run bracket simulation (run_state_predictions) to get predicted 1st-8th per weight.
    Returns dict: weight -> {1: wrestler_id, 2: wrestler_id, ..., 8: wrestler_id}
    """
    import sys
    sys.path.insert(0, str(PROJECT_ROOT))
    from scripts.state.run_state_predictions import (
        HS_BOYS_WEIGHTS,
        HS_GIRLS_WEIGHTS,
        BOYS_REQUIRED_SLOTS,
        GIRLS_REQUIRED_SLOTS,
        load_archive_index,
        load_rankings_all_weights,
        load_public_rankings_all_weights,
        parse_seed_file,
        resolve_seeded_wrestlers,
        simulate_boys_bracket,
        simulate_girls_bracket,
        _weights_for_automatch,
        _interactive_resolve_seed,
    )

    all_weights = HS_BOYS_WEIGHTS if gender == "boys" else HS_GIRLS_WEIGHTS
    required_slots = BOYS_REQUIRED_SLOTS if gender == "boys" else GIRLS_REQUIRED_SLOTS
    data_subdir = "hs_ky_boys" if gender == "boys" else "hs_ky_girls"
    seed_base = PROJECT_ROOT / "data" / data_subdir / "States"

    drop_id = load_archive_index(rankings_base, gender, season)
    if not drop_id:
        return {}

    result: Dict[int, Dict[int, str]] = {}

    for weight in weights:
        if weight not in all_weights:
            continue

        seed_file_path = seed_base / str(weight)
        if not seed_file_path.exists():
            continue

        rankings_automatch = load_rankings_all_weights(
            rankings_base, gender, season, drop_id, _weights_for_automatch(weight, all_weights)
        )
        rankings_all = load_rankings_all_weights(
            rankings_base, gender, season, drop_id, all_weights
        )
        public_rankings = load_public_rankings_all_weights(
            rankings_base, gender, season, all_weights
        )
        seen_ids = {str(w.get("wrestler_id", "")) for w in rankings_all}
        for w in public_rankings:
            if str(w.get("wrestler_id", "")) not in seen_ids:
                seen_ids.add(str(w.get("wrestler_id", "")))
                rankings_all.append(w)

        slot_entries = parse_seed_file(str(seed_file_path))
        missing = required_slots - set(slot_entries.keys())
        if missing:
            continue

        try:
            slot_to_wrestler = resolve_seeded_wrestlers(
                slot_entries,
                rankings_automatch,
                str(seed_file_path),
                _interactive_resolve_seed,
                non_interactive=True,
                rankings_search=rankings_all,
                current_weight=weight,
            )
        except RuntimeError:
            continue

        if gender == "boys":
            placements_ordered, _, _, _ = simulate_boys_bracket(slot_to_wrestler)
        else:
            placements_ordered, _, _, _ = simulate_girls_bracket(slot_to_wrestler)

        result[weight] = {}
        for place, wrestler in enumerate(placements_ordered, start=1):
            wid = str(wrestler.get("wrestler_id", ""))
            if wid:
                result[weight][place] = wid

    return result


def _load_rankings_before_tournament(
    rankings_base: Path,
    season: int,
    weights: List[int],
    gender: str,
) -> Tuple[str, Dict[Tuple[int, str], int]]:
    """
    Load most recent rankings prior to tournament start (2/26).
    Returns (drop_id, dict of (weight, wrestler_id) -> rank).
    Unranked wrestlers are not in the dict.
    """
    index_path = rankings_base / gender / str(season) / "index.json"
    if not index_path.exists():
        raise RuntimeError(f"No rankings index for {gender} {season}")

    with index_path.open("r", encoding="utf-8") as f:
        index = json.load(f)

    # Find latest drop with date < tournament start (02/26)
    tournament_start = f"{season}-02-26"
    drop_id = None
    for d in index.get("drops") or []:
        did = d.get("id", "")
        if did and did < tournament_start:
            if drop_id is None or did > drop_id:
                drop_id = did

    if not drop_id:
        # Fallback to "latest" if it's before tournament
        drop_id = index.get("latest", "")
        if drop_id and drop_id >= tournament_start:
            raise RuntimeError(
                f"No rankings drop before {tournament_start}. Latest is {drop_id}."
            )

    if not drop_id:
        raise RuntimeError(f"No rankings drops found for {gender} {season}")

    rank_by_weight_id: Dict[Tuple[int, str], int] = {}

    for weight in weights:
        # Primary: archive drop
        archive_path = rankings_base / gender / str(season) / drop_id / f"{weight}.json"
        starters_path = rankings_base / gender / str(season) / f"rankings_starters_{weight}.json"

        for path in [archive_path, starters_path]:
            if not path.exists():
                continue
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            wrestlers = data.get("wrestlers") or data.get("rankings") or []
            for w in wrestlers:
                wid = str(w.get("wrestler_id", ""))
                rank = w.get("rank")
                if wid and rank is not None and (weight, wid) not in rank_by_weight_id:
                    rank_by_weight_id[(weight, wid)] = int(rank)

    return drop_id, rank_by_weight_id


def _load_placement_notes_from_rankings(
    rankings_base: Path,
    season: int,
    weights: List[int],
    gender: str,
    drop_id: str,
) -> Dict[str, int]:
    """
    Load last year's state placement (1-8) from rankings placement_note.
    Returns wrestler_id -> place (1-8). Used for returning placer count (RP/RC).
    """
    out: Dict[str, int] = {}
    for weight in weights:
        path = rankings_base / gender / str(season) / drop_id / f"{weight}.json"
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        for w in data.get("wrestlers") or []:
            wid = str(w.get("wrestler_id", ""))
            note = (w.get("placement_note") or "").strip()
            if wid and note in ("1", "2", "3", "4", "5", "6", "7", "8"):
                out[wid] = int(note)
    return out


# ============================================================
# IMPRESSIVENESS SCORE
# ============================================================

def _round_from_summary(summary: str) -> str:
    """Map match summary to round bucket: F, SF, QF, Early."""
    s = (summary or "").strip()
    if "1st Place Match" in s and "Semi" not in s:
        return "F"
    if "Semifinals" in s or "Semi" in s:
        return "SF"
    if "Quarterfinals" in s or "Quarter" in s:
        return "QF"
    return "Early"


def _get_round_bucket_upset(summary: str) -> str:
    """Map match summary to upset round bucket: final, semi, quarter, blood, early."""
    s = (summary or "").strip()
    if "Consolation Semi" in s or "Cons. Semi" in s or "Blood" in s:
        return "blood"
    if "1st Place Match" in s or "3rd Place Match" in s or "5th Place Match" in s or "7th Place Match" in s:
        if "Semi" not in s:
            return "final"
    if "Semifinals" in s or "Semi" in s:
        return "semi"
    if "Quarterfinals" in s or "Quarter" in s:
        return "quarter"
    return "early"


def _load_career_lookup(project_root: Path) -> Dict[str, Dict[str, str]]:
    """Build season_wrestler_id -> {career_id, seasons dict}. Lazy-load careers."""
    careers_dir = project_root / "data" / "careers"
    if not careers_dir.exists():
        return {}
    lookup: Dict[str, Dict[str, str]] = {}
    for cf in careers_dir.glob("career_*.json"):
        try:
            with cf.open("r", encoding="utf-8") as f:
                c = json.load(f)
        except Exception:
            continue
        cid = c.get("career_id", "")
        seasons = c.get("seasons") or {}
        for _yr, sid in seasons.items():
            if sid:
                lookup[str(sid)] = {"career_id": cid, "seasons": seasons}
    return lookup


def _collect_bracket_wins(
    processed_dir: Path,
    gender: str,
    season: int,
    state_dates: Set[str],
    state_event: str,
) -> Dict[Tuple[int, str], List[Tuple[str, str, str]]]:
    """
    Collect wins per (weight, wrestler_id). Returns (weight, wid) -> [(opp_id, opp_name, round)]
    Excludes BYE, For., Junior Varsity. Only real wins.
    """
    data_dir = processed_dir / f"hs_ky_{gender}" / str(season)
    if not data_dir.exists():
        return {}

    result: Dict[Tuple[int, str], List[Tuple[str, str, str]]] = {}
    seen: Set[Tuple[int, FrozenSet[str]]] = set()

    for team_file in sorted(data_dir.glob("*.json")):
        try:
            with team_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        roster = data.get("roster") or []
        for wrestler in roster:
            wid = str(wrestler.get("season_wrestler_id", ""))
            if not wid:
                continue

            for m in wrestler.get("matches") or []:
                event = (m.get("event") or "").strip()
                if state_event not in event:
                    continue
                date = (m.get("date") or "").strip()
                if date not in state_dates:
                    continue
                summary = (m.get("summary") or "").strip()
                if "Junior Varsity" in summary:
                    continue
                result_str = (m.get("result") or "").strip()
                if result_str in SKIP_RESULTS:
                    continue

                winner_name = (m.get("winner_name") or "").strip()
                loser_name = (m.get("loser_name") or "").strip()
                if not winner_name or not loser_name or "Unknown" in (winner_name, loser_name):
                    continue

                opponent_id = m.get("opponent_id")
                if opponent_id is None or opponent_id == "" or str(opponent_id) == "-1":
                    continue

                weight_str = (m.get("weight") or "").strip()
                if not weight_str or not weight_str.isdigit():
                    continue
                weight = int(weight_str)

                roster_name = (wrestler.get("name") or "").strip()
                if roster_name == winner_name:
                    winner_id, loser_id = wid, str(opponent_id)
                elif roster_name == loser_name:
                    continue
                else:
                    continue

                key = (weight, frozenset([winner_id, loser_id]))
                if key in seen:
                    continue
                seen.add(key)

                round_label = _round_from_summary(summary)
                k = (weight, winner_id)
                result.setdefault(k, []).append((loser_id, loser_name, round_label))

    return result


def _collect_bracket_wins_detailed(
    processed_dir: Path,
    gender: str,
    season: int,
    state_dates: Set[str],
    state_event: str,
) -> Dict[Tuple[int, str], List[Dict]]:
    """
    Collect wins per (weight, wrestler_id) with full opponent/round info for upset scoring.
    Returns (weight, wid) -> [{opp_id, opp_name, opp_team, round_bucket, summary, result}]
    """
    data_dir = processed_dir / f"hs_ky_{gender}" / str(season)
    if not data_dir.exists():
        return {}

    result: Dict[Tuple[int, str], List[Dict]] = {}
    seen: Set[Tuple[int, FrozenSet[str]]] = set()

    for team_file in sorted(data_dir.glob("*.json")):
        try:
            with team_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        roster = data.get("roster") or []
        for wrestler in roster:
            wid = str(wrestler.get("season_wrestler_id", ""))
            if not wid:
                continue

            for m in wrestler.get("matches") or []:
                event = (m.get("event") or "").strip()
                if state_event not in event:
                    continue
                date = (m.get("date") or "").strip()
                if date not in state_dates:
                    continue
                summary = (m.get("summary") or "").strip()
                if "Junior Varsity" in summary:
                    continue
                result_str = (m.get("result") or "").strip()
                if result_str in SKIP_RESULTS:
                    continue

                winner_name = (m.get("winner_name") or "").strip()
                loser_name = (m.get("loser_name") or "").strip()
                loser_team = (m.get("loser_team") or "").strip()
                if not winner_name or not loser_name or "Unknown" in (winner_name, loser_name):
                    continue

                opponent_id = m.get("opponent_id")
                if opponent_id is None or opponent_id == "" or str(opponent_id) == "-1":
                    continue

                weight_str = (m.get("weight") or "").strip()
                if not weight_str or not weight_str.isdigit():
                    continue
                weight = int(weight_str)

                roster_name = (wrestler.get("name") or "").strip()
                if roster_name == winner_name:
                    winner_id, loser_id = wid, str(opponent_id)
                    opp_name, opp_team = loser_name, loser_team
                elif roster_name == loser_name:
                    continue
                else:
                    continue

                key = (weight, frozenset([winner_id, loser_id]))
                if key in seen:
                    continue
                seen.add(key)

                round_bucket = _get_round_bucket_upset(summary)
                k = (weight, winner_id)
                result.setdefault(k, []).append({
                    "opp_id": loser_id,
                    "opp_name": opp_name,
                    "opp_team": opp_team,
                    "round_bucket": round_bucket,
                    "summary": summary,
                    "result": result_str,
                })

    return result


def _get_entrants_per_weight(
    actual_placements: Dict[int, Dict[int, str]],
    bracket_wins: Dict[Tuple[int, str], List[Tuple[str, str, str]]],
    wrestler_points: List[Tuple[str, str, str, int, float]],
) -> Dict[int, Set[str]]:
    """Entrants = all wrestlers who participated at state at that weight."""
    entrants: Dict[int, Set[str]] = {}
    for weight, placements in actual_placements.items():
        s = set()
        for wid in placements.values():
            if wid:
                s.add(wid)
        entrants.setdefault(weight, set()).update(s)
    for (weight, wid), wins in bracket_wins.items():
        entrants.setdefault(weight, set()).add(wid)
        for opp_id, _, _ in wins:
            if opp_id:
                entrants.setdefault(weight, set()).add(opp_id)
    for wid, _name, _team, weight, _pts in wrestler_points:
        if weight not in entrants:
            entrants[weight] = set()
        entrants[weight].add(wid)
    return entrants


def _build_placement_lookup(
    placements: Dict[int, Dict[int, str]],
) -> Dict[Tuple[int, str], int]:
    """(weight, wrestler_id) -> place (1-8)."""
    out: Dict[Tuple[int, str], int] = {}
    for weight, by_place in placements.items():
        for place, wid in by_place.items():
            if wid:
                out[(weight, wid)] = place
    return out


def _load_last_year_placements_from_accomplishments(
    project_root: Path,
    gender: str,
    last_year: int,
) -> Dict[Tuple[int, str], int]:
    """
    Load last year's state placements from season_accomplishments.
    Returns (weight, season_wrestler_id) -> place (1-8).
    Used as fallback when processed-data placement extraction misses matches
    (e.g. different event names or dates across seasons).
    """
    path = (
        project_root
        / "data"
        / "season_accomplishments"
        / gender
        / str(last_year)
        / "season_accomplishments.json"
    )
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    out: Dict[Tuple[int, str], int] = {}
    for w in data.get("wrestlers") or []:
        wid = w.get("season_wrestler_id")
        state_place = w.get("state_place")
        final_weight = w.get("final_weight")
        if wid and state_place is not None and 1 <= state_place <= 8 and final_weight:
            out[(int(final_weight), str(wid))] = int(state_place)
    return out


def compute_impressiveness_scores(
    processed_dir: Path,
    project_root: Path,
    season: int,
    gender: str,
    state_dates: Set[str],
    state_event: str,
    actual_placements: Dict[int, Dict[int, str]],
    wrestler_points: List[Tuple[str, str, str, int, float]],
    placement_notes: Optional[Dict[str, int]] = None,
    debug: bool = False,
) -> List[Dict]:
    """
    Compute impressiveness for all state placers/participants.
    Returns list of dicts sorted by impressiveness desc, with full breakdown.
    """
    last_year = season - 1
    last_year_dates = _state_dates_for_season(last_year)
    last_year_placements = _collect_actual_placements(
        processed_dir, gender, last_year, last_year_dates, state_event
    )

    this_year_place = _build_placement_lookup(actual_placements)
    last_year_place = _build_placement_lookup(last_year_placements)
    # Fallback: season_accomplishments has canonical state_place (handles different
    # event names/dates across seasons, e.g. 2025 "KHSAA State Championship" vs
    # 2026 "KHSAA Boys/Coed State Championship")
    accomplishments_place = _load_last_year_placements_from_accomplishments(
        project_root, gender, last_year
    )
    last_year_place.update(accomplishments_place)

    bracket_wins = _collect_bracket_wins(
        processed_dir, gender, season, state_dates, state_event
    )
    entrants = _get_entrants_per_weight(
        actual_placements, bracket_wins, wrestler_points
    )

    career_lookup = _load_career_lookup(project_root)

    # Resolve current_id -> last_year_id for placement lookup
    def get_last_year_place_at_weight(current_id: str, weight: int) -> Optional[int]:
        """Resolve current (this year) wrestler_id to last year's placement at this weight."""
        # Via career: current_id is this year; get last year's id
        info = career_lookup.get(current_id)
        if info:
            seasons = info.get("seasons") or {}
            ly_id = seasons.get(str(last_year))
            if ly_id:
                p = last_year_place.get((weight, ly_id))
                if p is not None:
                    return p
        # Direct match (same id both years, e.g. stable id)
        return last_year_place.get((weight, current_id))

    def get_best_place(opp_id: str, weight: int) -> Tuple[Optional[int], Optional[int]]:
        """Return (best_place, year) - year when opponent had that placement."""
        this_p = this_year_place.get((weight, opp_id))
        ly_p = get_last_year_place_at_weight(opp_id, weight)
        if this_p is not None and ly_p is not None:
            best = min(this_p, ly_p)
            year = season if this_p == best else last_year
            return (best, year)
        if this_p is not None:
            return (this_p, season)
        if ly_p is not None:
            return (ly_p, last_year)
        return (None, None)

    tp_by_id: Dict[str, float] = {}
    info_by_id: Dict[str, Tuple[str, str, int, Optional[int]]] = {}
    for wid, name, team, weight, pts in wrestler_points:
        tp_by_id[wid] = pts
        place = this_year_place.get((weight, wid))
        info_by_id[wid] = (name, team, weight, place)

    results: List[Dict] = []

    for wid, (name, team, weight, place) in info_by_id.items():
        tp = tp_by_id.get(wid, 0.0)
        if tp <= 0:
            continue

        # BracketMult: count returning placers (RP/RC) from placement_notes when available.
        # placement_notes comes from rankings (wrestler_id -> last year's place 1-8), matching
        # the UI's blue numbers. Fallback to career+season_accomplishments when not available.
        entrant_ids = entrants.get(weight, set()) - {wid}
        rp = 0
        rc = 0
        if placement_notes:
            for eid in entrant_ids:
                ly_place = placement_notes.get(eid)
                if ly_place is not None and 1 <= ly_place <= 8:
                    rp += 1
                    if ly_place == 1:
                        rc += 1
        else:
            for (w, ly_id), ly_place in last_year_place.items():
                if w != weight or ly_place is None or not 1 <= ly_place <= 8:
                    continue
                info = career_lookup.get(ly_id)
                ty_id = (info.get("seasons") or {}).get(str(season)) if info else None
                if ty_id and ty_id in entrant_ids and ty_id != wid:
                    rp += 1
                    if ly_place == 1:
                        rc += 1
        bracket_raw = 1.0 + IMPRESS_A * rp + IMPRESS_B * rc
        bracket_mult = min(IMPRESS_BRACKET_CAP, bracket_raw)

        # PathMult
        wins = bracket_wins.get((weight, wid), [])
        path_score = 0.0
        win_details: List[Dict] = []
        for opp_id, opp_name, round_label in wins:
            best, best_year = get_best_place(opp_id, weight)
            p_val = PLACEMENT_WEIGHT.get(best, 0.0) if best else 0.0
            r_val = ROUND_MULT.get(round_label, ROUND_MULT["Early"])
            contrib = p_val * r_val
            path_score += contrib
            win_details.append({
                "round": round_label,
                "opponent": opp_name,
                "best_place": best,
                "best_place_year": best_year,
                "p": p_val,
                "r": r_val,
                "contrib": contrib,
            })

        path_raw = 1.0 + IMPRESS_C * path_score
        path_mult = min(IMPRESS_PATH_CAP, path_raw)

        impress = tp * bracket_mult * path_mult

        place_str = f"{place}st" if place == 1 else (f"{place}nd" if place == 2 else (f"{place}rd" if place == 3 else f"{place}th"))
        results.append({
            "wrestler_id": wid,
            "name": name,
            "team": team,
            "weight": weight,
            "place": place,
            "place_str": place_str,
            "tp": tp,
            "rp": rp,
            "rc": rc,
            "bracket_mult": bracket_mult,
            "bracket_raw": bracket_raw,
            "path_score": path_score,
            "path_mult": path_mult,
            "path_raw": path_raw,
            "impressiveness": impress,
            "win_details": win_details,
        })

    results.sort(key=lambda x: x["impressiveness"], reverse=True)
    return results


# ============================================================
# UPSET RUN SCORE
# ============================================================

def compute_upset_run_scores(
    processed_dir: Path,
    season: int,
    gender: str,
    state_dates: Set[str],
    state_event: str,
    actual_placements: Dict[int, Dict[int, str]],
    wrestler_points: List[Tuple[str, str, str, int, float]],
    rank_by_weight_id: Dict[Tuple[int, str], int],
    drop_id: str,
) -> List[Dict]:
    """
    Compute upset run scores for wrestlers ranked outside top 8 who placed top 8.
    Returns list sorted by UpsetRunScore desc.
    """
    # Build placement lookup: (weight, wid) -> place (1-8)
    place_by_weight_id: Dict[Tuple[int, str], int] = {}
    for weight, by_place in actual_placements.items():
        for place, wid in by_place.items():
            if wid and 1 <= place <= 8:
                place_by_weight_id[(weight, wid)] = place

    # Wrestler info: wid -> (name, team, weight)
    info_by_id: Dict[str, Tuple[str, str, int]] = {}
    for wid, name, team, weight, _pts in wrestler_points:
        info_by_id[wid] = (name, team, weight)

    bracket_wins = _collect_bracket_wins_detailed(
        processed_dir, gender, season, state_dates, state_event
    )

    candidates: List[Dict] = []

    for wid, (name, team, weight) in info_by_id.items():
        final_place = place_by_weight_id.get((weight, wid))
        if final_place is None or final_place > 8:
            continue

        pre_rank = rank_by_weight_id.get((weight, wid))
        if pre_rank is None:
            pre_rank = UNRANKED
        if pre_rank <= 8:
            continue

        effective_pre_rank = min(pre_rank, EFFECTIVE_RANK_CAP)
        wrestler_effective_rank = effective_pre_rank

        # PlacementScore
        placement_surprise = max(0, effective_pre_rank - final_place)
        placement_weight = PLACEMENT_WEIGHT_UPSET.get(final_place, 1.0)
        placement_score = placement_surprise * placement_weight

        # WinScore and RankedWins
        wins = bracket_wins.get((weight, wid), [])
        win_score = 0.0
        ranked_wins = 0
        key_wins: List[Dict] = []

        for w in wins:
            opp_id = w.get("opp_id")
            if not opp_id:
                continue
            opp_pre_rank = rank_by_weight_id.get((weight, opp_id))
            if opp_pre_rank is None:
                opp_pre_rank = UNRANKED
            effective_opp_rank = min(opp_pre_rank, EFFECTIVE_RANK_CAP)
            upset_value = max(0, wrestler_effective_rank - effective_opp_rank)
            round_bucket = w.get("round_bucket", "early")
            round_weight = ROUND_WEIGHT_UPSET.get(round_bucket, 1.0)
            contrib = upset_value * round_weight
            win_score += contrib

            if opp_pre_rank <= 8 and opp_pre_rank != UNRANKED:
                ranked_wins += 1

            key_wins.append({
                "opp_id": opp_id,
                "opp_name": w.get("opp_name", "?"),
                "opp_team": w.get("opp_team", ""),
                "opp_pre_rank": opp_pre_rank,
                "round_bucket": round_bucket,
                "summary": w.get("summary", ""),
                "upset_value": upset_value,
                "round_weight": round_weight,
                "contrib": contrib,
            })

        combo_mult = 1.0 + (ranked_wins * COMBO_MULT_PER_RANKED_WIN)
        upset_run_score = (placement_score + win_score) * combo_mult

        pre_rank_str = str(pre_rank) if pre_rank != UNRANKED else "UNRANKED"
        candidates.append({
            "wrestler_id": wid,
            "name": name,
            "team": team,
            "weight": weight,
            "pre_rank": pre_rank,
            "pre_rank_str": pre_rank_str,
            "effective_pre_rank": effective_pre_rank,
            "final_place": final_place,
            "placement_score": placement_score,
            "win_score": win_score,
            "ranked_wins": ranked_wins,
            "combo_mult": combo_mult,
            "upset_run_score": upset_run_score,
            "key_wins": sorted(key_wins, key=lambda x: x["contrib"], reverse=True),
        })

    candidates.sort(key=lambda x: x["upset_run_score"], reverse=True)
    return candidates


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate state tournament predictions vs actual results"
    )
    parser.add_argument("--season", type=int, default=2026, help="Season year")
    parser.add_argument(
        "-gender",
        type=str,
        choices=["boys", "girls"],
        default="boys",
        help="Gender (boys: 32-man bracket, girls: 16-man)",
    )
    parser.add_argument(
        "--processed-dir",
        type=str,
        default=None,
        help="Override processed data base dir (default: frontend/wrestledata-ui/public/data/processed_data)",
    )
    parser.add_argument(
        "--rankings-dir",
        type=str,
        default=None,
        help="Override rankings base dir (default: frontend/hs-ky-ui/public/data/rankings)",
    )
    parser.add_argument(
        "--impressiveness",
        action="store_true",
        help="Compute and print impressiveness scores for top placers",
    )
    parser.add_argument(
        "--impressiveness-top",
        type=int,
        default=10,
        help="Number of top impressiveness breakdowns to show (default: 10)",
    )
    parser.add_argument(
        "--impressiveness-debug",
        action="store_true",
        help="Print debug info for impressiveness calculation",
    )
    parser.add_argument(
        "--upset-runs",
        action="store_true",
        help="Compute and print top 5 upset runs (ranked outside top 8, placed top 8)",
    )
    args = parser.parse_args()

    processed_base = (
        Path(args.processed_dir)
        if args.processed_dir
        else PROJECT_ROOT / "frontend" / "wrestledata-ui" / "public" / "data" / "processed_data"
    )
    rankings_base = (
        Path(args.rankings_dir)
        if args.rankings_dir
        else PROJECT_ROOT / "frontend" / "hs-ky-ui" / "public" / "data" / "rankings"
    )

    state_dates = _state_dates_for_season(args.season)
    if args.gender == "boys":
        state_event = STATE_EVENT_BOYS
        weights = [106, 113, 120, 126, 132, 138, 144, 150, 157, 165, 175, 190, 215, 285]
    else:
        state_event = STATE_EVENT_GIRLS
        weights = [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235]

    print("=" * 60)
    print("STATE TOURNAMENT PREDICTION EVALUATION")
    print("=" * 60)
    print(f"Gender: {args.gender}, Season: {args.season}")
    print(f"Event: {state_event}")
    print(f"Dates: {', '.join(sorted(state_dates))}")
    print()

    # Collect actual matches
    print("Collecting actual state tournament matches...")
    actual_matches = _collect_state_matches(
        processed_base, args.gender, args.season, state_dates, state_event
    )
    print(f"  Found {len(actual_matches)} unique matches")
    print()

    # Load rankings (most recent before 2/26)
    print("Loading rankings (most recent prior to 2/26)...")
    try:
        drop_id, rank_by_weight_id = _load_rankings_before_tournament(
            rankings_base, args.season, weights, args.gender
        )
        print(f"  Using drop: {drop_id}")
        print(f"  Ranked wrestlers: {len(rank_by_weight_id)}")
    except Exception as e:
        print(f"  Error: {e}")
        raise SystemExit(1) from e
    print()

    # Collect actual placements and bracket predictions (for champ/finalists/top8 accuracy)
    print("Collecting actual placements and bracket predictions...")
    actual_placements = _collect_actual_placements(
        processed_base, args.gender, args.season, state_dates, state_event
    )
    predicted_placements = _get_bracket_predicted_placements(
        rankings_base, args.season, weights, args.gender
    )
    weights_with_actual = set(actual_placements.keys())
    weights_with_pred = set(predicted_placements.keys())
    placement_weights = sorted(weights_with_actual & weights_with_pred)
    print(f"  Weights with both actual and predicted: {len(placement_weights)}")
    print()

    # Top 10 dominant wrestlers by team points
    wrestler_points = _compute_wrestler_state_points(
        processed_base, args.gender, args.season, state_dates, state_event, actual_placements
    )

    # Evaluate: predict higher-ranked wrestler wins
    correct = 0
    wrong = 0
    no_prediction = 0
    wrong_details: List[Tuple[int, str, str, str, str]] = []

    # Per-weight accuracy and team upset stats
    weight_correct: Dict[int, int] = {}
    weight_total: Dict[int, int] = {}
    team_upsets: Dict[str, int] = {}
    team_wins: Dict[str, int] = {}
    team_losses: Dict[str, int] = {}
    team_favored_total: Dict[str, int] = {}
    team_underdog_total: Dict[str, int] = {}
    team_upset_losses: Dict[str, int] = {}

    for weight, winner_id, loser_id, winner_name, loser_name, winner_team, loser_team in actual_matches:
        rank_winner = rank_by_weight_id.get((weight, winner_id))
        rank_loser = rank_by_weight_id.get((weight, loser_id))

        if rank_winner is None and rank_loser is None:
            no_prediction += 1
            continue

        # Predict: lower rank number = better, so predicted winner has lower rank
        if rank_winner is not None and rank_loser is not None:
            pred_winner_id = winner_id if rank_winner < rank_loser else loser_id
        elif rank_winner is not None:
            pred_winner_id = winner_id
        else:
            pred_winner_id = loser_id

        if pred_winner_id == winner_id:
            correct += 1
        else:
            wrong += 1
            wrong_details.append((weight, winner_name, loser_name, winner_id, loser_id))

        # Per-weight accuracy
        weight_total[weight] = weight_total.get(weight, 0) + 1
        if pred_winner_id == winner_id:
            weight_correct[weight] = weight_correct.get(weight, 0) + 1

        # Team upset: winner had worse rank than loser (winner "upset" the higher-ranked loser)
        is_upset = (
            (rank_winner is not None and rank_loser is not None and rank_winner > rank_loser)
            or (rank_winner is None and rank_loser is not None)
        )
        if winner_team:
            team_wins[winner_team] = team_wins.get(winner_team, 0) + 1
            if is_upset:
                team_upsets[winner_team] = team_upsets.get(winner_team, 0) + 1
        if loser_team:
            team_losses[loser_team] = team_losses.get(loser_team, 0) + 1

        # Team "got upset": team was favored (had better rank) but lost
        # Team underdog: team had worse rank (candidate to upset)
        winner_favored = (
            (rank_winner is not None and rank_loser is not None and rank_winner < rank_loser)
            or (rank_winner is not None and rank_loser is None)
        )
        loser_favored = (
            (rank_winner is not None and rank_loser is not None and rank_winner > rank_loser)
            or (rank_winner is None and rank_loser is not None)
        )
        if winner_favored and winner_team:
            team_favored_total[winner_team] = team_favored_total.get(winner_team, 0) + 1
            if loser_team:
                team_underdog_total[loser_team] = team_underdog_total.get(loser_team, 0) + 1
        if loser_favored and loser_team:
            team_favored_total[loser_team] = team_favored_total.get(loser_team, 0) + 1
            if winner_team:
                team_underdog_total[winner_team] = team_underdog_total.get(winner_team, 0) + 1
            team_upset_losses[loser_team] = team_upset_losses.get(loser_team, 0) + 1

    total_evaluated = correct + wrong
    pct = (100.0 * correct / total_evaluated) if total_evaluated else 0.0

    # Placement accuracy (champ, finalists, top 8)
    # Champ: predicted 1st == actual 1st
    # Finalists: predicted finalists (our 1st+2nd) who actually made finals (actual top 2)
    # Top 8: predicted medalists (our 1-8) who actually medaled (actual top 8)
    champ_correct = 0
    finalist_correct = 0
    top8_correct = 0
    champ_total = 0
    finalist_total = 0
    top8_total = 0

    for wgt in placement_weights:
        actual = actual_placements.get(wgt, {})
        pred = predicted_placements.get(wgt, {})

        actual_top2_ids = {actual[p] for p in (1, 2) if p in actual}
        actual_top8_ids = {actual[p] for p in range(1, 9) if p in actual}

        if 1 in actual and 1 in pred:
            champ_total += 1
            if actual[1] == pred[1]:
                champ_correct += 1

        for place in (1, 2):
            if place in pred and actual_top2_ids:
                finalist_total += 1
                if pred[place] in actual_top2_ids:
                    finalist_correct += 1

        for place in range(1, 9):
            if place in pred and actual_top8_ids:
                top8_total += 1
                if pred[place] in actual_top8_ids:
                    top8_correct += 1

    champ_pct = (100.0 * champ_correct / champ_total) if champ_total else 0.0
    finalist_pct = (100.0 * finalist_correct / finalist_total) if finalist_total else 0.0
    top8_pct = (100.0 * top8_correct / top8_total) if top8_total else 0.0

    # Report
    print("=" * 60)
    print("REPORT")
    print("=" * 60)
    print(f"  Total state matches (date filter): {len(actual_matches)}")
    print(f"  Matches with prediction:          {total_evaluated}")
    print(f"  Matches without prediction:      {no_prediction}")
    print()
    print(f"  Match prediction:")
    print(f"    Correct:   {correct}")
    print(f"    Wrong:     {wrong}")
    print(f"    Win %:     {pct:.1f}%")
    print()
    print(f"  Placement prediction (bracket simulation):")
    print(f"    Champ:           {champ_correct}/{champ_total} correct ({champ_pct:.1f}%) - predicted champ won")
    print(f"    Finalists:       {finalist_correct}/{finalist_total} correct ({finalist_pct:.1f}%) - predicted finalists made finals")
    print(f"    Top 8 medalists: {top8_correct}/{top8_total} correct ({top8_pct:.1f}%) - predicted medalists placed in top 8")
    print()

    # Accuracy by weight (lowest to highest)
    print("  Accuracy by weight class (lowest to highest):")
    weight_accuracies = []
    for wgt in sorted(weight_total.keys()):
        c = weight_correct.get(wgt, 0)
        t = weight_total.get(wgt, 0)
        pct = (100.0 * c / t) if t else 0.0
        weight_accuracies.append((wgt, c, t, pct))
    weight_accuracies.sort(key=lambda x: x[3])
    for wgt, c, t, pct in weight_accuracies:
        print(f"    {wgt:3} lbs: {c:3}/{t:3} ({pct:5.1f}%)")
    print()

    # Teams that outperformed (most upsets)
    print("  Teams with most upsets (by count and % of their wins):")
    team_upset_list = []
    for team, wins in team_wins.items():
        upsets = team_upsets.get(team, 0)
        pct = (100.0 * upsets / wins) if wins else 0.0
        team_upset_list.append((team, upsets, wins, pct))
    team_upset_list.sort(key=lambda x: (-x[1], -x[3]))
    for team, upsets, wins, pct in team_upset_list[:15]:
        print(f"    {team}: {upsets} upsets ({pct:.1f}% of {wins} wins)")
    print()

    # Teams least often upset when favored (min 10 favored matches)
    print("  Teams least upset when favored (min 10 favored matches):")
    team_got_upset_list = []
    for team, favored in team_favored_total.items():
        if favored < 10:
            continue
        upset_losses = team_upset_losses.get(team, 0)
        pct = (100.0 * upset_losses / favored) if favored else 0.0
        team_got_upset_list.append((team, upset_losses, favored, pct))
    team_got_upset_list.sort(key=lambda x: (x[3], -x[2]))
    for team, upset_losses, favored, pct in team_got_upset_list[:10]:
        print(f"    {team}: {upset_losses}/{favored} upset losses ({pct:.1f}%)")
    print()

    # Top 10 teams by points: win %, upset %, getting upset %
    team_points: Dict[str, float] = {}
    for _wid, _name, team, _weight, pts in wrestler_points:
        team_points[team] = team_points.get(team, 0.0) + pts
    top10_teams = sorted(team_points.items(), key=lambda x: -x[1])[:10]

    print("  Top 10 teams by points - win %, upset %, getting upset %:")
    print("    (Total = favored + underdog; upset % = when underdog; got upset % = when favored)")
    print(f"    {'Team':<25} {'Win %':<22} {'Upset %':<22} {'Got upset %':<22}")
    for team, pts in top10_teams:
        wins = team_wins.get(team, 0)
        losses = team_losses.get(team, 0)
        total = wins + losses
        favored = team_favored_total.get(team, 0)
        underdog = team_underdog_total.get(team, 0)
        win_pct = (100.0 * wins / total) if total else 0.0
        win_str = f"{win_pct:.1f}% ({wins}/{total})" if total else "0.0% (0/0)"
        upsets = team_upsets.get(team, 0)
        upset_pct = (100.0 * upsets / underdog) if underdog else 0.0
        upset_str = f"{upset_pct:.1f}% ({upsets}/{underdog})" if underdog else "0.0% (0/0)"
        upset_losses = team_upset_losses.get(team, 0)
        got_upset_pct = (100.0 * upset_losses / favored) if favored else 0.0
        got_upset_str = f"{got_upset_pct:.1f}% ({upset_losses}/{favored})" if favored else "0.0% (0/0)"
        print(f"    {team:<25} {win_str:<22} {upset_str:<22} {got_upset_str:<22}")
    print()

    print(f"  Top 10 dominant wrestlers (team points):")
    for i, (wid, name, team, weight, pts) in enumerate(wrestler_points[:10], 1):
        pts_str = f"{pts:.1f}" if pts % 1 else f"{int(pts)}"
        print(f"    {i:2}. {name} ({team}) {weight} lbs - {pts_str} pts")
    print()

    # Impressiveness scores
    if args.impressiveness:
        placement_notes = _load_placement_notes_from_rankings(
            rankings_base, args.season, weights, args.gender, drop_id
        )
        impress_results = compute_impressiveness_scores(
            processed_base,
            PROJECT_ROOT,
            args.season,
            args.gender,
            state_dates,
            state_event,
            actual_placements,
            wrestler_points,
            placement_notes=placement_notes,
            debug=args.impressiveness_debug,
        )
        top_n = min(args.impressiveness_top, len(impress_results))

        print("=" * 60)
        print("TOP IMPRESSIVENESS SCORES")
        print("=" * 60)
        print(f"{'Rank':<5} {'Name':<25} {'Team':<20} {'Wt':<5} {'Place':<6} {'TP':<6} {'Bracket':<8} {'Path':<8} {'Score':<8}")
        print("-" * 95)
        for i, r in enumerate(impress_results[:top_n], 1):
            place_str = f"{r['place']}th" if r["place"] else "?"
            if r["place"] == 1:
                place_str = "1st"
            elif r["place"] == 2:
                place_str = "2nd"
            elif r["place"] == 3:
                place_str = "3rd"
            name_short = (r["name"][:24] + "..") if len(r["name"]) > 25 else r["name"]
            team_short = (r["team"][:19] + "..") if len(r["team"]) > 20 else r["team"]
            print(f"{i:<5} {name_short:<25} {team_short:<20} {r['weight']:<5} {place_str:<6} {r['tp']:<6.1f} {r['bracket_mult']:<8.2f} {r['path_mult']:<8.2f} {r['impressiveness']:<8.1f}")
        print()

        for i, r in enumerate(impress_results[:top_n], 1):
            place_str = f"{r['place']}th" if r["place"] else "?"
            if r["place"] == 1:
                place_str = "1st"
            elif r["place"] == 2:
                place_str = "2nd"
            elif r["place"] == 3:
                place_str = "3rd"
            print(f"#{i} {r['name']} ({r['team']}) — wt {r['weight']} — Placed {place_str}")
            print(f"  TP: {r['tp']:.1f}  (placement + advancement + bonus)")
            print(f"  Bracket Difficulty:")
            print(f"    Returning placers (RP): {r['rp']}")
            print(f"    Returning champs  (RC): {r['rc']}")
            print(f"    BracketMult: {r['bracket_mult']:.2f}  (raw 1 + {IMPRESS_A}*{r['rp']} + {IMPRESS_B}*{r['rc']})")
            print(f"  Path Bonus:")
            print(f"    Wins:")
            for wd in r["win_details"]:
                bp = wd["best_place"]
                if bp == 1:
                    bp_str = "1st"
                elif bp == 2:
                    bp_str = "2nd"
                elif bp == 3:
                    bp_str = "3rd"
                else:
                    bp_str = f"{bp}th" if bp else "None"
                year_str = f" ({wd['best_place_year']})" if wd.get("best_place_year") else ""
                print(f"     - {wd['round']:5} vs {wd['opponent'][:30]} (best_place: {bp_str}{year_str}) P={wd['p']:.2f} R={wd['r']:.2f} => {wd['contrib']:.4f}")
            print(f"    PathScore: {r['path_score']:.4f}")
            print(f"    PathMult: {r['path_mult']:.4f}  (raw 1 + {IMPRESS_C}*{r['path_score']:.4f})")
            print(f"  Final: Impressiveness = {r['tp']:.1f} * {r['bracket_mult']:.2f} * {r['path_mult']:.4f} = {r['impressiveness']:.1f}")
            print()

    # Top 5 upset runs
    if args.upset_runs:
        upset_results = compute_upset_run_scores(
            processed_base,
            args.season,
            args.gender,
            state_dates,
            state_event,
            actual_placements,
            wrestler_points,
            rank_by_weight_id,
            drop_id,
        )
        top5 = upset_results[:5]
        print("=" * 60)
        print(f"Top 5 Upset Runs — {args.season} {args.gender} State Tournament (drop {drop_id})")
        print("=" * 60)
        for i, r in enumerate(top5, 1):
            place_str = f"{r['final_place']}th"
            if r["final_place"] == 1:
                place_str = "1st"
            elif r["final_place"] == 2:
                place_str = "2nd"
            elif r["final_place"] == 3:
                place_str = "3rd"
            print(f"\n{i}) {r['name']} ({r['team']}) — {r['weight']} lbs")
            print(f"   Rank → Finish: #{r['pre_rank_str']} → {place_str}")
            print(f"   EffectiveRankUsed: #{r['effective_pre_rank']}")
            print(f"   PlacementScore: {r['placement_score']:.2f}")
            print(f"   WinScore: {r['win_score']:.2f}")
            print(f"   RankedWins (vs top-8): {r['ranked_wins']}")
            print(f"   ComboMult: {r['combo_mult']:.2f}")
            print(f"   UpsetRunScore: {r['upset_run_score']:.2f}")
            print(f"   Key Wins (sorted by impact):")
            for kw in r["key_wins"]:
                if kw["contrib"] > 0:
                    opp_rank_str = f"#{kw['opp_pre_rank']}" if kw["opp_pre_rank"] != UNRANKED else "UNRANKED"
                    opp_team_str = f" ({kw['opp_team']})" if kw.get("opp_team") else ""
                    print(f"     - {kw['round_bucket']:8} def {opp_rank_str} {kw['opp_name']}{opp_team_str}")
                    print(f"       UpsetValue={kw['upset_value']:.1f}, RoundWeight={kw['round_weight']:.2f}, Contribution={kw['contrib']:.2f}")
        if not top5:
            print("\n  (No upset run candidates: no wrestlers ranked outside top 8 placed top 8)")
        print()

    if wrong_details and len(wrong_details) <= 30:
        print("  Incorrect predictions (weight, actual winner def. actual loser):")
        for wgt, wname, lname, _wid, _lid in wrong_details[:30]:
            print(f"    {wgt} lbs: {wname} def. {lname}")
    elif wrong_details:
        print(f"  (First 10 of {len(wrong_details)} incorrect predictions:)")
        for wgt, wname, lname, _wid, _lid in wrong_details[:10]:
            print(f"    {wgt} lbs: {wname} def. {lname}")
    print("=" * 60)


if __name__ == "__main__":
    main()
