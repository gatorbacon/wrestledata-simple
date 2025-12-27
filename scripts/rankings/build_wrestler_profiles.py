#!/usr/bin/env python3
"""
Build static JSON profiles for all wrestlers.

This script generates:
  - /wrestlers/<season>/by_id/<wrestlerId>.json (one per wrestler)
  - /wrestlers/<season>/by_team/<team_slug>/<wrestlerId>.json (duplicates)
  - /wrestlers/<season>/index_wrestlers.json
  - /wrestlers/<season>/index_teams.json
  - /wrestlers/<season>/index_search.json

IMPORTANT: This script uses starter-only rankings (rankings_starters_*.json)
for determining opponent ranks. Run build_starter_rankings.py first.

Usage:
    python scripts/rankings/build_starter_rankings.py -season 2026
    python scripts/rankings/build_wrestler_profiles.py -season 2026
"""

import argparse
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Import functions from existing scripts
from normalized_scoring import (
    _compute_plus_metrics_for_all,
)
from matches_and_diff_by_rank import estimate_match_duration_seconds
from scoringbyrank import _parse_score_from_result


def _load_starter_rank_map(season: int, data_dir: str = "mt/rankings_data") -> Dict[str, int]:
    """
    Load starter-only rankings and create a map from wrestler_id -> best (lowest) starter rank.
    
    Uses rankings_starters_*.json files which contain only starters with re-numbered ranks.
    
    NOTE: Always reads from the public data location (frontend/wrestledata-ui/public/data/rankings)
    regardless of data_dir parameter, since rankings_starters files are stored there.
    """
    # Always read from public location - rankings_starters files are stored there
    rankings_dir = Path("frontend/wrestledata-ui/public/data/rankings") / str(season)
    if not rankings_dir.exists():
        raise FileNotFoundError(f"Rankings directory not found: {rankings_dir}")
    
    rank_by_id: Dict[str, int] = {}
    
    # Load from starter-only rankings files
    for p in sorted(rankings_dir.glob("rankings_starters_*.json")):
        try:
            with p.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        
        for r in data.get("rankings", []):
            wid = str(r.get("wrestler_id") or "")
            raw_rank = r.get("rank")
            if not wid or raw_rank is None:
                continue
            try:
                rk = int(raw_rank)
            except Exception:
                continue
            
            # Keep best (lowest) rank across all weights
            if wid not in rank_by_id or rk < rank_by_id[wid]:
                rank_by_id[wid] = rk
    
    return rank_by_id


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build static JSON profiles for all wrestlers"
    )
    parser.add_argument(
        "-season",
        type=int,
        required=True,
        help="Season year (e.g., 2026)",
    )
    parser.add_argument(
        "-data_dir",
        type=str,
        default="mt/rankings_data",
        help="Directory containing rankings data (default: mt/rankings_data)",
    )
    parser.add_argument(
        "-output_dir",
        type=str,
        default="frontend/wrestledata-ui/public/data/wrestlers",
        help="Output directory for wrestler profiles (default: frontend/wrestledata-ui/public/data/wrestlers)",
    )
    return parser.parse_args()


def team_name_to_slug(team_name: str) -> str:
    """Convert team name to slug (lowercase, spaces to underscores, remove punctuation)."""
    slug = team_name.lower()
    slug = slug.replace(" ", "_")
    slug = re.sub(r"[^\w_]", "", slug)
    return slug


def calculate_team_rankings(
    season: int, data_dir: str
) -> Tuple[Dict[str, int], Dict[str, float]]:
    """
    Calculate team rankings based on team scores.
    
    Returns:
        - team_rank_by_name: dict mapping team_name -> rank (1-based)
        - team_scores: dict mapping team_name -> total_points
    """
    from team_score_estimator import calculate_team_scores
    
    team_scores, _ = calculate_team_scores(season, data_dir)
    
    # Sort teams by score (descending) to get rankings
    sorted_teams = sorted(team_scores.items(), key=lambda x: (-x[1], x[0]))
    
    team_rank_by_name = {}
    for rank, (team_name, _) in enumerate(sorted_teams, start=1):
        team_rank_by_name[team_name] = rank
    
    return team_rank_by_name, team_scores


def load_all_wrestler_info(season: int, data_dir: str) -> Dict[str, Dict]:
    """Load all wrestler info from weight class files."""
    data_path = Path(data_dir) / str(season)
    wrestlers = {}
    
    for wc_file in sorted(data_path.glob("weight_class_*.json")):
        try:
            with wc_file.open("r", encoding="utf-8") as f:
                wc_data = json.load(f)
        except Exception:
            continue
        
        weight_class_str = wc_file.stem.replace("weight_class_", "")
        try:
            weight_class = int(weight_class_str)
        except ValueError:
            continue
        
        for wid, winfo in wc_data.get("wrestlers", {}).items():
            if wid not in wrestlers:
                wrestlers[wid] = {
                    "wrestler_id": wid,
                    "name": winfo.get("name", "Unknown"),
                    "team": winfo.get("team", "Unknown"),
                    "weight_class": weight_class,
                    "grade": winfo.get("grade", ""),
                }
    
    return wrestlers


def load_all_matches_from_weight_classes(
    season: int, data_dir: str
) -> Dict[str, List[Dict]]:
    """Load all matches from weight class files, organized by wrestler_id."""
    data_path = Path(data_dir) / str(season)
    matches_by_wrestler = defaultdict(list)
    
    for wc_file in sorted(data_path.glob("weight_class_*.json")):
        try:
            with wc_file.open("r", encoding="utf-8") as f:
                wc_data = json.load(f)
        except Exception:
            continue
        
        for match in wc_data.get("matches", []):
            w1_id = match.get("wrestler1_id")
            w2_id = match.get("wrestler2_id")
            
            if w1_id:
                matches_by_wrestler[w1_id].append(match)
            if w2_id:
                matches_by_wrestler[w2_id].append(match)
    
    return dict(matches_by_wrestler)


def classify_result_type(result: str) -> str:
    """Classify match result type: D, MD, TF, F, INJ, etc."""
    if not result:
        return "O"
    
    s = result.upper()
    
    # Check for injury FIRST (before other classifications)
    if "INJ" in s or "INJURY" in s:
        return "INJ"
    
    # Check for medical forfeit (check "M. FOR" or "M FOR" to catch "M. For.")
    # This must come before checking for "MFF" to catch the "M. For." format
    if "M. FOR" in s or (s.startswith("M") and "FOR" in s and "MFF" not in s):
        return "MFF"
    
    # Check for default/forfeit (before decision to avoid misclassification)
    if "DEF" in s or "DEFAULT" in s:
        return "DEF"
    
    # Check for tech fall (before fall/pin) to avoid misclassification)
    # Tech falls have "TF" or "TECH" in the result string
    if "TF" in s or "TECH" in s or "TECHNICAL" in s:
        return "TF"
    # Then check for falls/pins (but exclude if "TF" appears anywhere)
    if ("PIN" in s or "FALL" in s) and "TF" not in s:
        return "F"
    if "MD" in s or "MAJOR" in s:
        return "MD"
    # SV-* and TB-* are decisions (treated as D for stats/MI), but we'll preserve the prefix for display
    if s.startswith("SV-") or s.startswith("TB-"):
        return "D"  # Treated as decision for stats/MI purposes
    if "DEC" in s or "DECISION" in s:
        return "D"
    if "DQ" in s or "DISQUAL" in s:
        return "DQ"
    if "MFF" in s or "MEDICAL" in s:
        return "MFF"
    if "FF" in s or "FORFEIT" in s:
        return "FF"
    
    return "O"


def is_mff_result(result: str) -> bool:
    """Check if result is a medical forfeit."""
    if not result:
        return False
    s = result.upper()
    return "MFF" in s or "MEDICAL" in s


def calculate_bonus_stats(
    matches: List[Dict], wrestler_id: str
) -> Dict[str, int]:
    """Calculate bonus stats (majors, techs, pins) for a wrestler."""
    majors = 0
    techs = 0
    pins = 0
    
    for match in matches:
        result = match.get("result", "") or ""
        
        # Skip MFF and invalid results
        if is_mff_result(result):
            continue
        
        winner_id = match.get("winner_id")
        if winner_id != wrestler_id:
            continue
        
        result_type = classify_result_type(result)
        if result_type == "F":
            pins += 1
        elif result_type == "TF":
            techs += 1
        elif result_type == "MD":
            majors += 1
    
    return {"majors": majors, "techs": techs, "pins": pins}


def calculate_records(
    matches: List[Dict],
    wrestler_id: str,
    rank_by_id: Dict[str, int],
) -> Dict[str, any]:
    """Calculate win/loss records (overall, vs_ranked, vs_top10, vs_top25)."""
    wins = 0
    losses = 0
    ranked_wins = 0
    ranked_losses = 0
    top10_wins = 0
    top10_losses = 0
    top25_wins = 0
    top25_losses = 0
    
    for match in matches:
        result = match.get("result", "") or ""
        
        # Skip MFF and invalid results
        if is_mff_result(result):
            continue
        
        w1_id = match.get("wrestler1_id")
        w2_id = match.get("wrestler2_id")
        winner_id = match.get("winner_id")
        
        if not w1_id or not w2_id or not winner_id:
            continue
        
        # Determine opponent
        opp_id = w2_id if w1_id == wrestler_id else w1_id
        if opp_id == wrestler_id:
            continue  # Skip if wrestler is both w1 and w2 (shouldn't happen)
        
        # Determine if wrestler won
        is_winner = (winner_id == wrestler_id)
        
        if is_winner:
            wins += 1
            opp_rank = rank_by_id.get(opp_id)
            if opp_rank:
                ranked_wins += 1
                if opp_rank <= 10:
                    top10_wins += 1
                if opp_rank <= 25:
                    top25_wins += 1
        else:
            losses += 1
            opp_rank = rank_by_id.get(opp_id)
            if opp_rank:
                ranked_losses += 1
                if opp_rank <= 10:
                    top10_losses += 1
                if opp_rank <= 25:
                    top25_losses += 1
    
    return {
        "overall": f"{wins}-{losses}",
        "vs_ranked": f"{ranked_wins}-{ranked_losses}",
        "vs_top10": f"{top10_wins}-{top10_losses}",
        "vs_top25": f"{top25_wins}-{top25_losses}",
        "wins": wins,
        "losses": losses,
        "ranked_wins": ranked_wins,
        "ranked_losses": ranked_losses,
        "top10_wins": top10_wins,
        "top10_losses": top10_losses,
    }


def find_best_win_and_worst_loss(
    matches: List[Dict],
    wrestler_id: str,
    rank_by_id: Dict[str, int],
    all_wrestlers: Dict[str, Dict],
) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Find best win (highest ranked opponent) and worst loss (lowest ranked opponent)."""
    best_win = None
    best_win_rank = 9999
    
    worst_loss = None
    worst_loss_rank = 0
    
    for match in matches:
        result = match.get("result", "") or ""
        
        # Skip MFF and invalid results
        if is_mff_result(result):
            continue
        
        w1_id = match.get("wrestler1_id")
        w2_id = match.get("wrestler2_id")
        winner_id = match.get("winner_id")
        
        if not w1_id or not w2_id or not winner_id:
            continue
        
        # Determine opponent
        opp_id = w2_id if w1_id == wrestler_id else w1_id
        if opp_id == wrestler_id:
            continue
        
        opp_info = all_wrestlers.get(opp_id)
        if not opp_info:
            continue
        
        opp_rank = rank_by_id.get(opp_id)
        if not opp_rank:
            continue
        
        # Determine if wrestler won
        is_winner = (winner_id == wrestler_id)
        
        # Extract method from result
        result_type = classify_result_type(result)
        method = result.strip()
        
        if is_winner and opp_rank < best_win_rank:
            best_win_rank = opp_rank
            best_win = {
                "opponent_id": opp_id,
                "opponent_rank": opp_rank,
                "opponent_name": opp_info.get("name", "Unknown"),
                "method": method,
            }
        elif not is_winner and opp_rank > worst_loss_rank:
            worst_loss_rank = opp_rank
            worst_loss = {
                "opponent_id": opp_id,
                "opponent_rank": opp_rank,
                "opponent_name": opp_info.get("name", "Unknown"),
                "method": method,
            }
    
    return best_win, worst_loss


def load_match_mv_impact(season: int) -> Dict[str, Dict]:
    """
    Load per-match MV impact cache.
    
    Returns dict mapping (wrestler_id, opponent_id, date, result) -> mv_impact
    
    NOTE: Always reads from the public data location (frontend/wrestledata-ui/public/data/mat_value)
    regardless of other parameters, since match_mv_impact files are stored there.
    """
    # Always read from public location - match_mv_impact files are stored there
    match_impact_file = Path(f"frontend/wrestledata-ui/public/data/mat_value/{season}/match_mv_impact_{season}.json")
    if not match_impact_file.exists():
        return {}
    
    try:
        with match_impact_file.open("r", encoding="utf-8") as f:
            cache_data = json.load(f)
        
        # Convert to lookup dict: (wrestler_id, opponent_id, date, result) -> mv_impact
        lookup = {}
        for wrestler_id, matches in cache_data.items():
            for match_entry in matches:
                key = (
                    match_entry.get("wrestler_id"),
                    match_entry.get("opponent_id"),
                    match_entry.get("date", ""),
                    match_entry.get("result", ""),
                )
                lookup[key] = match_entry.get("mv_impact")
        
        return lookup
    except Exception as e:
        print(f"Warning: Could not load match MV impact cache: {e}")
        return {}


def build_match_list(
    matches: List[Dict],
    wrestler_id: str,
    rank_by_id: Dict[str, int],
    all_wrestlers: Dict[str, Dict],
    team_rank_by_name: Dict[str, int],
    match_mv_impact_lookup: Optional[Dict] = None,
) -> List[Dict]:
    """Build formatted match list for JSON output."""
    match_list = []
    seen_match_keys = set()
    
    for match in matches:
        result = match.get("result", "") or ""
        date = match.get("date", "") or ""
        event = match.get("event")
        
        # Skip MFF and invalid results
        if is_mff_result(result):
            continue
        
        w1_id = match.get("wrestler1_id")
        w2_id = match.get("wrestler2_id")
        winner_id = match.get("winner_id")
        
        if not w1_id or not w2_id or not winner_id:
            continue
        
        # Determine opponent
        opp_id = w2_id if w1_id == wrestler_id else w1_id
        if opp_id == wrestler_id:
            continue
        
        # De-duplicate
        w1, w2 = sorted([wrestler_id, opp_id])
        match_key = (w1, w2, date, result)
        if match_key in seen_match_keys:
            continue
        seen_match_keys.add(match_key)
        
        opp_info = all_wrestlers.get(opp_id, {})
        opp_name = opp_info.get("name", "Unknown")
        opp_team = opp_info.get("team", "Unknown")
        opp_weight = opp_info.get("weight_class", None)
        opp_rank = rank_by_id.get(opp_id)
        opp_team_rank = team_rank_by_name.get(opp_team)
        
        # Determine result (W/L)
        is_winner = (winner_id == wrestler_id)
        result_code = "W" if is_winner else "L"
        
        # Extract method and score
        method = "DEC"  # default
        score = None
        
        result_type = classify_result_type(result)
        result_upper = result.upper()
        
        if result_type == "F":
            method = "FALL"
        elif result_type == "TF":
            method = "TF"
        elif result_type == "MD":
            method = "MD"
        elif result_type == "INJ":
            method = "INJ"
        elif result_type == "DEF":
            method = "DFLT"
        elif result_type == "MFF":
            method = "MFF"
        elif result_type == "D":
            # Check for SV-* or TB-* to preserve the prefix for display
            if result_upper.startswith("SV-"):
                # Extract SV-1, SV-3, etc. from original result
                sv_part = result.split()[0] if result.split() else "SV-1"
                method = sv_part.upper()
            elif result_upper.startswith("TB-"):
                # Extract TB-1, TB-2, etc. from original result
                tb_part = result.split()[0] if result.split() else "TB-1"
                method = tb_part.upper()
            else:
                method = "DEC"
        
        score_pair = _parse_score_from_result(result)
        if score_pair:
            score = f"{score_pair[0]}-{score_pair[1]}"
        
        # Calculate duration - extract time from result string if present
        duration_seconds = estimate_match_duration_seconds(result)
        # For falls, injuries, and tech falls, try to extract the actual time from the result string
        if result_type in ("F", "INJ", "TF"):
            # Look for time pattern like "1:29" or "5:40" in the result
            time_match = re.search(r"(\d+):(\d{2})", result)
            if time_match:
                minutes = int(time_match.group(1))
                seconds = int(time_match.group(2))
                duration_seconds = minutes * 60 + seconds
        
        minutes = duration_seconds // 60
        seconds = duration_seconds % 60
        duration = f"{minutes}:{seconds:02d}"
        
        # Parse date to YYYY-MM-DD format
        date_formatted = date
        try:
            # Try parsing M/D/YYYY or MM/DD/YYYY
            if "/" in date:
                parts = date.split("/")
                if len(parts) == 3:
                    month = parts[0].zfill(2)
                    day = parts[1].zfill(2)
                    year = parts[2]
                    if len(year) == 2:
                        year = "20" + year
                    date_formatted = f"{year}-{month}-{day}"
        except Exception:
            pass
        
        match_entry = {
            "date": date_formatted,
            "opponent_id": opp_id if opp_id else None,
            "opponent_name": opp_name,
            "opponent_team": opp_team,
            "opponent_team_rank": opp_team_rank,
            "opponent_weight": opp_weight,
            "opponent_rank": opp_rank,
            "result": result_code,
            "method": method,
            "score": score,
            "duration": duration,
            "event": event,
        }
        
        # Add MV impact if available from cache
        # Try both original date format and formatted date for matching
        if match_mv_impact_lookup:
            # Try with formatted date first (YYYY-MM-DD)
            lookup_key = (wrestler_id, opp_id, date_formatted, result)
            mv_impact = match_mv_impact_lookup.get(lookup_key)
            # If not found, try with original date format
            if mv_impact is None:
                lookup_key = (wrestler_id, opp_id, date, result)
                mv_impact = match_mv_impact_lookup.get(lookup_key)
            if mv_impact is not None:
                match_entry["mv_impact"] = mv_impact
        
        match_list.append(match_entry)
    
    # Sort by date (newest first)
    match_list.sort(key=lambda x: x.get("date", ""), reverse=True)
    
    return match_list


def load_mv_data(season: int) -> Dict[str, Dict]:
    """
    Load Mat Value data from season-wide file (includes rankings).
    
    Returns dict mapping wrestler_id -> MV data with ranks.
    
    NOTE: Always reads from the public data location (frontend/wrestledata-ui/public/data/mat_value)
    regardless of other parameters, since mat_value files are stored there.
    """
    # Always read from public location - mat_value files are stored there
    mv_file = Path(f"frontend/wrestledata-ui/public/data/mat_value/{season}/mat_value_{season}.json")
    if not mv_file.exists():
        # Fallback to cache file if season-wide file doesn't exist
        cache_file = Path(f"frontend/wrestledata-ui/public/data/mat_value/{season}/mv_cache_{season}.json")
        if cache_file.exists():
            try:
                with cache_file.open("r", encoding="utf-8") as f:
                    cache_data = json.load(f)
                # Convert cache format to include ranks (set to None if not available)
                mv_data = {}
                for wrestler_id, mv in cache_data.items():
                    mv_data[wrestler_id] = {
                        "mv_avg": mv["mv_avg"],
                        "matches": mv["matches"],
                        "rank_weight": None,
                        "rank_overall": None,
                    }
                return mv_data
            except Exception:
                return {}
        return {}
    
    try:
        with mv_file.open("r", encoding="utf-8") as f:
            entries = json.load(f)
        
        # Convert list format to dict format
        mv_data = {}
        for entry in entries:
            wrestler_id = entry.get("wrestler_id")
            if wrestler_id:
                mv_data[wrestler_id] = {
                    "mv_avg": entry.get("mv_avg"),
                    "matches": entry.get("matches"),
                    "rank_weight": entry.get("mv_rank_weight"),
                    "rank_overall": entry.get("mv_rank_overall"),
                }
        return mv_data
    except Exception:
        return {}


def build_wrestler_profile(
    wrestler_id: str,
    season: int,
    all_wrestlers: Dict[str, Dict],
    rank_by_id: Dict[str, int],
    team_rank_by_name: Dict[str, int],
    metrics_by_id: Dict[str, Dict],
    matches: List[Dict],
    mv_data: Optional[Dict[str, Dict]] = None,
    match_mv_impact_lookup: Optional[Dict] = None,
) -> Dict:
    """Build complete wrestler profile JSON."""
    wrestler_info = all_wrestlers.get(wrestler_id, {})
    name = wrestler_info.get("name", "Unknown")
    team = wrestler_info.get("team", "Unknown")
    weight_class = wrestler_info.get("weight_class", 0)
    grade = wrestler_info.get("grade", "")
    
    team_slug = team_name_to_slug(team)
    team_rank = team_rank_by_name.get(team)
    current_rank = rank_by_id.get(wrestler_id)
    
    # Get advanced metrics
    metrics_data = metrics_by_id.get(wrestler_id, {})
    pf7 = metrics_data.get("PF7_raw", 0.0)
    pa7 = metrics_data.get("PA7_raw", 0.0)
    pd7 = pf7 - pa7
    si_plus = metrics_data.get("SI_plus", 100.0)
    df_plus = metrics_data.get("DF_plus", 100.0)
    apr_plus = metrics_data.get("PE_plus", 100.0)  # PE+ is APR+
    
    # Calculate records
    records = calculate_records(matches, wrestler_id, rank_by_id)
    
    # Calculate bonus stats
    bonus_stats = calculate_bonus_stats(matches, wrestler_id)
    majors = bonus_stats["majors"]
    techs = bonus_stats["techs"]
    pins = bonus_stats["pins"]
    
    # Calculate rates
    wins = records["wins"]
    bonus_wins = majors + techs + pins
    bonus_rate = (bonus_wins / wins) if wins > 0 else 0.0
    pin_rate = (pins / wins) if wins > 0 else 0.0
    
    # Find best win and worst loss
    best_win, worst_loss = find_best_win_and_worst_loss(
        matches, wrestler_id, rank_by_id, all_wrestlers
    )
    
    # Build match list
    match_list = build_match_list(
        matches, wrestler_id, rank_by_id, all_wrestlers, team_rank_by_name, match_mv_impact_lookup
    )
    
    # Get Mat Value data if available
    mat_value_data = None
    if mv_data and wrestler_id in mv_data:
        mv = mv_data[wrestler_id]
        mat_value_data = {
            "mv_avg": mv["mv_avg"],
            "matches": mv["matches"],
            "rank_weight": mv.get("rank_weight"),
            "rank_overall": mv.get("rank_overall"),
            "version": "v1",
        }
    
    # Build metrics object
    metrics_obj = {
        "pf7": round(pf7, 2),
        "pa7": round(pa7, 2),
        "pd7": round(pd7, 2),
        "si_plus": round(si_plus, 1),
        "df_plus": round(df_plus, 1),
        "apr_plus": round(apr_plus, 1),
        "pin_rate": round(pin_rate, 3),
        "bonus_rate": round(bonus_rate, 3),
        "majors": majors,
        "techs": techs,
        "pins": pins,
    }
    
    # Add Mat Value if available
    if mat_value_data:
        metrics_obj["mat_value"] = mat_value_data
    
    # Build profile
    profile = {
        "wrestler_id": wrestler_id,
        "name": name,
        "team": team,
        "team_slug": team_slug,
        "team_rank": team_rank,
        "weight_class": weight_class,
        "year": season,
        "current_rank": current_rank,
        "record": {
            "overall": records["overall"],
            "vs_ranked": records["vs_ranked"],
            "vs_top10": records["vs_top10"],
            "vs_top25": records["vs_top25"],
        },
        "metrics": metrics_obj,
        "opponent_breakdown": {
            "ranked_wins": records["ranked_wins"],
            "ranked_losses": records["ranked_losses"],
            "top10_wins": records["top10_wins"],
            "top10_losses": records["top10_losses"],
            "win_over_highest_rank": best_win,
            "worst_loss": worst_loss,
        },
        "match_list": match_list,
    }
    
    return profile


def main() -> None:
    args = parse_args()
    season = args.season
    data_dir = args.data_dir
    output_dir = Path(args.output_dir)
    
    print(f"Building wrestler profiles for season {season}...")
    print(f"Data directory: {data_dir}")
    print(f"Output directory: {output_dir}")
    
    # Load data
    print("\nLoading wrestler data...")
    all_wrestlers = load_all_wrestler_info(season, data_dir)
    print(f"Loaded {len(all_wrestlers)} wrestlers")
    
    print("\nLoading starter-only rankings...")
    rank_by_id = _load_starter_rank_map(season, data_dir)
    print(f"Loaded starter-only rankings for {len(rank_by_id)} wrestlers")
    
    print("\nCalculating team rankings...")
    team_rank_by_name, team_scores = calculate_team_rankings(season, data_dir)
    print(f"Calculated rankings for {len(team_rank_by_name)} teams")
    
    print("\nCalculating advanced metrics...")
    metrics_by_id, _ = _compute_plus_metrics_for_all(season, 999)  # Use high max_rank to get all
    print(f"Calculated metrics for {len(metrics_by_id)} wrestlers")
    
    print("\nLoading matches from weight class files...")
    matches_by_wrestler = load_all_matches_from_weight_classes(season, data_dir)
    print(f"Loaded matches for {len(matches_by_wrestler)} wrestlers")
    
    # Load Mat Value data if available
    print("\nLoading Mat Value data...")
    mv_data = load_mv_data(season)
    if mv_data:
        print(f"Loaded MV data for {len(mv_data)} wrestlers")
    else:
        print("No MV data found (run compute_all_mat_values.py first)")
    
    # Load per-match MV impact cache if available
    print("\nLoading per-match MV impact data...")
    match_mv_impact_lookup = load_match_mv_impact(season)
    if match_mv_impact_lookup:
        print(f"Loaded MV impact data for {len(match_mv_impact_lookup)} match entries")
    else:
        print("No per-match MV impact data found (run compute_all_mat_values.py first)")
        match_mv_impact_lookup = {}
    
    # Create output directories
    season_dir = output_dir / str(season)
    by_id_dir = season_dir / "by_id"
    by_team_dir = season_dir / "by_team"
    
    # Delete existing directories
    if by_id_dir.exists():
        shutil.rmtree(by_id_dir)
    if by_team_dir.exists():
        shutil.rmtree(by_team_dir)
    
    # Create directories
    by_id_dir.mkdir(parents=True, exist_ok=True)
    by_team_dir.mkdir(parents=True, exist_ok=True)
    
    # Build profiles
    print("\nBuilding wrestler profiles...")
    index_wrestlers = []
    index_teams = defaultdict(list)
    index_search = []
    
    processed = 0
    for wrestler_id in all_wrestlers.keys():
        if processed % 100 == 0:
            print(f"  Processed {processed}/{len(all_wrestlers)}...")
        
        # Get matches for this wrestler
        matches = matches_by_wrestler.get(wrestler_id, [])
        
        # Build profile
        profile = build_wrestler_profile(
            wrestler_id,
            season,
            all_wrestlers,
            rank_by_id,
            team_rank_by_name,
            metrics_by_id,
            matches,
            mv_data,
            match_mv_impact_lookup,
        )
        
        # Preserve existing bonus data if it exists
        output_file = by_id_dir / f"{wrestler_id}.json"
        if output_file.exists():
            try:
                with output_file.open("r", encoding="utf-8") as f:
                    existing_profile = json.load(f)
                    existing_bonus = existing_profile.get("bonus")
                    if existing_bonus:
                        profile["bonus"] = existing_bonus
            except Exception:
                # If we can't read existing file, continue without preserving bonus
                pass
        
        # Write to by_id
        with output_file.open("w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2, ensure_ascii=False)
        
        # Write to by_team
        team_slug = profile["team_slug"]
        team_dir = by_team_dir / team_slug
        team_dir.mkdir(parents=True, exist_ok=True)
        team_file = team_dir / f"{wrestler_id}.json"
        with team_file.open("w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2, ensure_ascii=False)
        
        # Add to indexes
        index_wrestlers.append({
            "wrestler_id": wrestler_id,
            "name": profile["name"],
            "team": profile["team"],
            "team_slug": team_slug,
            "weight_class": profile["weight_class"],
            "current_rank": profile["current_rank"],
        })
        
        index_teams[profile["team"]].append(wrestler_id)
        
        index_search.append({
            "wrestler_id": wrestler_id,
            "name": profile["name"],
            "team": profile["team"],
            "weight_class": profile["weight_class"],
        })
        
        processed += 1
    
    print(f"\nProcessed {processed} wrestlers")
    
    # Build team index
    print("\nBuilding index files...")
    index_teams_list = []
    for team_name, roster in sorted(index_teams.items()):
        team_slug = team_name_to_slug(team_name)
        team_rank = team_rank_by_name.get(team_name)
        index_teams_list.append({
            "team": team_name,
            "team_slug": team_slug,
            "team_rank": team_rank,
            "roster": sorted(roster),
        })
    
    # Write index files
    index_wrestlers_file = season_dir / "index_wrestlers.json"
    with index_wrestlers_file.open("w", encoding="utf-8") as f:
        json.dump(index_wrestlers, f, indent=2, ensure_ascii=False)
    
    index_teams_file = season_dir / "index_teams.json"
    with index_teams_file.open("w", encoding="utf-8") as f:
        json.dump(index_teams_list, f, indent=2, ensure_ascii=False)
    
    index_search_file = season_dir / "index_search.json"
    with index_search_file.open("w", encoding="utf-8") as f:
        json.dump(index_search, f, indent=2, ensure_ascii=False)
    
    print(f"\nDone! Generated:")
    print(f"  - {len(index_wrestlers)} wrestler profiles")
    print(f"  - {len(index_teams_list)} team entries")
    print(f"  - Index files in {season_dir}")


if __name__ == "__main__":
    main()

