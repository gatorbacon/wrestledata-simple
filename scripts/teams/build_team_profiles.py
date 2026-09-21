#!/usr/bin/env python3
"""
Generate per-team profile JSON files (identity + starters snapshot).

This script creates lightweight team profiles derived from rankings + overrides.
Output files are disposable snapshots for frontend consumption.

For HS teams, this script now embeds FULL wrestler profiles in the team JSON,
eliminating the need for frontend to fetch individual wrestler JSON files.

IMPORTANT:
- Starters are NOT authoritative here; rankings + overrides are.
- This script MUST be re-run whenever rankings change.
- For HS: Requires wrestler profiles to already exist (run build_wrestler_profiles.py first).

Pipeline position:
  rankings build → build_wrestler_profiles.py → build_team_profiles.py → build_team_metrics.py

Usage:
    python scripts/teams/build_team_profiles.py \
        --season 2026 \
        --teams-list data/team_lists/2026/ncaa_d1_teams.json \
        --rankings-dir mt/rankings_data/2026 \
        --starter-overrides mt/rankings_data/2026/starter_overrides.json \
        --out-dir mt/teams
"""

import argparse
import json
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build team profile JSON files from rankings"
    )
    parser.add_argument(
        "--season",
        type=int,
        required=True,
        help="Season year (e.g., 2026)",
    )
    parser.add_argument(
        "-league",
        type=str,
        choices=["ncaa", "hs"],
        default="ncaa",
        help="League: 'ncaa' (default) or 'hs' for high school",
    )
    parser.add_argument(
        "-state",
        type=str,
        default=None,
        help="State code (required when league=hs, e.g., 'KY')",
    )
    parser.add_argument(
        "-gender",
        type=str,
        choices=["boys", "girls"],
        default=None,
        help="Gender: 'boys' or 'girls' (optional when league=hs, will process both if not specified)",
    )
    parser.add_argument(
        "--teams-list",
        type=str,
        default=None,
        help="Path to teams JSON file (auto-determined if not specified)",
    )
    parser.add_argument(
        "--rankings-dir",
        type=str,
        default=None,
        help="Directory containing rankings_*.json files (auto-determined if not specified)",
    )
    parser.add_argument(
        "--starter-overrides",
        type=str,
        default=None,
        help="Path to starter_overrides.json (optional)",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default=None,
        help="Output directory for team profile JSON files (auto-determined if not specified)",
    )
    parser.add_argument(
        "--as-of-date",
        type=str,
        default=None,
        help="Reference date (YYYY-MM-DD) for absence checks; defaults to today (testing only)",
    )
    return parser.parse_args()


def slugify_team_name(team_name: str) -> str:
    """Convert team name to team_id (slug)."""
    slug = team_name.lower()
    slug = slug.replace(" ", "_")
    # Strip punctuation
    slug = re.sub(r"[^\w_]", "", slug)
    # Collapse multiple underscores
    slug = re.sub(r"_+", "_", slug)
    slug = slug.strip("_")
    return slug


def extract_conference(division: str) -> Optional[str]:
    """Extract conference from division string (e.g., 'DI - Big 12' -> 'Big 12')."""
    if not division:
        return None
    
    # Look for pattern "DI - {Conference}" and extract unique conferences
    matches = re.findall(r"DI\s*-\s*([^,]+)", division)
    if matches:
        # Take first unique value
        conferences = [m.strip() for m in matches]
        if conferences:
            return conferences[0]
    
    return None


def load_teams_list(teams_list_path: str) -> List[Dict]:
    """Load team list JSON file.

    Entries that slugify to the same team_id (e.g. "Waggener" and "Waggener " with a stray trailing space, which the
    TrackWrestling scrape can list twice) are collapsed to ONE entry -- the one that has a region, else the first --
    so a team never gets two rows/files under the same id.
    """
    with open(teams_list_path, "r", encoding="utf-8") as f:
        teams = json.load(f)
    by_id: Dict[str, Dict] = {}
    for team in teams:
        tid = slugify_team_name(team.get("name", ""))
        kept = by_id.get(tid)
        if kept is None or (team.get("region") and not kept.get("region")):
            by_id[tid] = team
    return list(by_id.values()) if len(by_id) != len(teams) else teams


def load_boys_inactive_mask(season: int, rankings_dir: Path) -> Set[str]:
    """
    Load boys inactive wrestlers mask file.
    
    Returns:
        Set of wrestler IDs to mask (empty set if file doesn't exist or not boys)
    """
    mask_file = rankings_dir / "boys_inactive_wrestlers.json"
    
    if not mask_file.exists():
        return set()
    
    try:
        with mask_file.open("r", encoding="utf-8") as f:
            mask_data = json.load(f)
        
        masked_ids = set()
        for wrestler in mask_data.get("masked_wrestlers", []):
            wrestler_id = wrestler.get("boys_wrestler_id")
            if wrestler_id:
                masked_ids.add(str(wrestler_id))
        
        return masked_ids
    except Exception as e:
        print(f"Warning: Could not load boys inactive mask: {e}")
        return set()


def load_starter_overrides(overrides_path: Optional[str]) -> Set[str]:
    """Load starter overrides (force_backup_ids)."""
    if not overrides_path or not Path(overrides_path).exists():
        return set()
    
    try:
        with open(overrides_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("force_backup_ids", []))
    except Exception as e:
        print(f"Warning: Error loading starter overrides: {e}")
        return set()


def load_rankings_by_weight(rankings_dir: str, league: str = 'ncaa', gender: str = None) -> Dict[str, List[Dict]]:
    """Load all rankings_*.json files, organized by weight."""
    rankings_dir_path = Path(rankings_dir)
    rankings_by_weight = {}
    
    # Determine weight classes based on league and gender
    if league == 'hs':
        if gender == 'boys':
            weight_classes = ["106", "113", "120", "126", "132", "138", "144", "150", "157", "165", "175", "190", "215", "285"]
        else:  # girls
            weight_classes = ["100", "107", "114", "120", "126", "132", "138", "145", "152", "165", "185", "235"]
    else:  # ncaa
        weight_classes = ["125", "133", "141", "149", "157", "165", "174", "184", "197", "285"]
    
    for weight in weight_classes:
        rankings_file = rankings_dir_path / f"rankings_{weight}.json"
        if not rankings_file.exists():
            print(f"Warning: Rankings file not found: {rankings_file}")
            rankings_by_weight[weight] = []
            continue
        
        try:
            with rankings_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            rankings = data.get("rankings", [])
            rankings_by_weight[weight] = rankings
        except Exception as e:
            print(f"Warning: Error loading {rankings_file}: {e}")
            rankings_by_weight[weight] = []
    
    return rankings_by_weight


# A "starter" with 0 matches this season, or nothing recent, isn't really
# starting -- exclude them from the fallback pool below. Waived if they're
# still Flo-ranked (moot in practice: Rule 1 below already grabs any
# Flo-ranked candidate first, so this exemption never actually triggers
# today -- kept anyway so the filter is self-contained and doesn't
# silently break if Rule 1 ever changes).
ABSENCE_DAYS_THRESHOLD = 25


def _rank_value(entry: Dict) -> int:
    rank = entry.get("rank")
    if isinstance(rank, int):
        return rank
    if isinstance(rank, str) and rank.isdigit():
        return int(rank)
    return 9999  # UNR / missing rank -- sorts last


def _parse_date(date_str: Optional[str]) -> Optional[date]:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None


def _days_since(date_str: Optional[str], as_of: Optional[date] = None) -> Optional[int]:
    d = _parse_date(date_str)
    if d is None:
        return None
    return ((as_of or datetime.now().date()) - d).days


def resolve_starters_for_team_hs(
    team_id: str,
    rankings_by_weight: Dict[str, List[Dict]],
    force_backup_ids: Set[str],
    weight_classes: List[str],
) -> Dict[str, Optional[str]]:
    """
    HS (Kentucky) starter resolution -- the original rank-based logic.

    HS rankings entries (rankings_<weight>.json from the manual matrix) carry `rank` and `is_starter`, but NOT the
    NCAA-only `flo_ranked` / `match_count` / `last_match_date` fields resolve_starters_for_team() needs. Running the
    NCAA logic on HS data excludes every candidate (missing match_count is treated as 0), which silently produced
    "0 starters" for almost every HS team from 2026-06 until this was split out (2026-09-20).

    For each weight: the team's best-ranked entry marked is_starter (force_backup_ids override that flag to False);
    if none is marked, the team's lowest-ranked entry; None if the team has nobody ranked at that weight.
    """
    starters: Dict[str, Optional[str]] = {}
    for weight in weight_classes:
        team_entries = []
        for entry in rankings_by_weight.get(weight, []):
            if slugify_team_name(entry.get("team", "")) != team_id:
                continue
            is_starter = entry.get("is_starter", True)
            if entry.get("wrestler_id") in force_backup_ids:
                is_starter = False
            team_entries.append({**entry, "is_starter": is_starter})

        if not team_entries:
            starters[weight] = None
            continue

        team_entries.sort(key=_rank_value)
        starter = next((e for e in team_entries if e.get("is_starter", False)), team_entries[0])
        starters[weight] = starter.get("wrestler_id")
    return starters


def resolve_starters_for_team(
    team_id: str,
    rankings_by_weight: Dict[str, List[Dict]],
    force_backup_ids: Set[str],
    weight_classes: List[str] = None,
    as_of_date: Optional[date] = None,
    league: str = "ncaa",
) -> Dict[str, Optional[str]]:
    """
    Resolve starters for a team across all weights.

    league="hs" uses resolve_starters_for_team_hs (the rules below are NCAA-only: they need Flo/match-count fields
    that HS rankings don't have).

    Priority:
      1. Any Flo-ranked candidate on the roster at that weight is the
         starter, full stop -- Flo doesn't rank non-starters, so this is
         trusted outright. Best rank among Flo-ranked candidates if more
         than one (rare, e.g. a recent transfer both still show up for).
      2. Otherwise, the best-ranked candidate with at least one match
         this season AND (Flo-ranked OR wrestled within the last
         ABSENCE_DAYS_THRESHOLD days). This is what stops a 0-match
         "ghost" from out-ranking a real, evidenced starter (rank alone
         used to decide this, and a fresh/seeded Elo can beat a proven
         teammate's earned one), and stops a long-inactive starter from
         still winning the slot over whoever's actually wrestling now.
      3. If nobody qualifies, a genuine vacancy -- None.

    force_backup_ids always excludes a wrestler from consideration,
    regardless of rank or Flo status.

    The 25-day check in rule 2 is measured against this TEAM's own most
    recent match across ANY weight (not a single global "today" passed in
    via as_of_date) -- a starter sidelined mid-season is still correctly
    flagged relative to a team that's still actively competing every week,
    and a fully completed season evaluates each team against its own real
    final activity instead of a still-later date driven by some other
    team's still-live tournament run (different programs' seasons end on
    different calendar dates -- a small conference team's season is often
    over by mid-February while a national qualifier wrestles into late
    March). as_of_date is only a fallback for a team with literally no
    match history at all anywhere (in which case every candidate already
    fails the match_count>0 check first regardless).

    Returns: dict mapping weight -> wrestler_id (or None)
    """
    if league == "hs":
        return resolve_starters_for_team_hs(team_id, rankings_by_weight, force_backup_ids, weight_classes or [])
    starters = {}
    if weight_classes is None:
        weight_classes = ["125", "133", "141", "149", "157", "165", "174", "184", "197", "285"]

    team_last_activity = None
    for weight in weight_classes:
        for entry in rankings_by_weight.get(weight, []):
            if slugify_team_name(entry.get("team", "")) != team_id:
                continue
            d = _parse_date(entry.get("last_match_date"))
            if d and (team_last_activity is None or d > team_last_activity):
                team_last_activity = d
    reference_date = team_last_activity or as_of_date

    for weight in weight_classes:
        rankings = rankings_by_weight.get(weight, [])

        # NOTE: rankings' own "is_starter" flag (set by write_rankings_from_elo)
        # is an unrelated, naive "best-Elo-per-team among has_matches" tag used
        # elsewhere (e.g. the matrix UI) -- it is NOT this function's concept of
        # starter and must not be used to filter candidates here, or every
        # teammate but that one naive pick gets silently dropped from the pool
        # this function is supposed to be choosing among. The only exclusion
        # that belongs here is an explicit force-backup override.
        team_entries = [
            entry for entry in rankings
            if slugify_team_name(entry.get("team", "")) == team_id
            and entry.get("wrestler_id") not in force_backup_ids
        ]

        if not team_entries:
            starters[weight] = None
            continue

        flo_candidates = [e for e in team_entries if e.get("flo_ranked")]
        if flo_candidates:
            starters[weight] = min(flo_candidates, key=_rank_value).get("wrestler_id")
            continue

        eligible = []
        for entry in team_entries:
            if entry.get("match_count", 0) == 0:
                continue
            days = _days_since(entry.get("last_match_date"), reference_date)
            if days is not None and days > ABSENCE_DAYS_THRESHOLD and not entry.get("flo_ranked"):
                continue
            eligible.append(entry)

        starters[weight] = min(eligible, key=_rank_value).get("wrestler_id") if eligible else None

    return starters


def load_wrestler_profile(wrestler_id: str, wrestlers_dir: Path) -> Optional[Dict]:
    """
    Load wrestler profile JSON from by_id directory.
    
    Args:
        wrestler_id: Wrestler ID
        wrestlers_dir: Base directory for wrestlers (e.g., frontend/hs-ky-ui/public/data/wrestlers/{gender}/{season})
    
    Returns:
        Wrestler profile dict or None if not found
    """
    profile_path = wrestlers_dir / "by_id" / f"{wrestler_id}.json"
    
    if not profile_path.exists():
        return None
    
    try:
        with profile_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Error loading profile {wrestler_id}: {e}")
        return None


def load_team_roster_from_index(team_slug: str, index_teams_path: Path) -> List[str]:
    """
    Load full roster (all wrestler IDs) for a team from index_teams.json.
    
    Args:
        team_slug: Team slug (normalized team name)
        index_teams_path: Path to index_teams.json
    
    Returns:
        List of wrestler IDs (excluding OUTSTATE_ prefixed IDs)
    """
    if not index_teams_path.exists():
        return []
    
    try:
        with index_teams_path.open("r", encoding="utf-8") as f:
            index_data = json.load(f)
        
        # Find team entry
        for team_entry in index_data:
            if team_entry.get("team_slug") == team_slug:
                roster = team_entry.get("roster", [])
                # Filter out OUTSTATE_ IDs
                return [wid for wid in roster if wid and not str(wid).startswith("OUTSTATE_")]
        
        return []
    except Exception as e:
        print(f"Warning: Error loading index_teams.json: {e}")
        return []


def load_team_metrics(team_name: str, team_metrics_path: Path) -> Optional[Dict]:
    """
    Load team metrics for a specific team.
    
    Args:
        team_name: Team name
        team_metrics_path: Path to team_metrics.json
    
    Returns:
        Team metrics dict or None if not found
    """
    if not team_metrics_path.exists():
        return None
    
    try:
        with team_metrics_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        
        teams = data.get("teams", [])
        for team in teams:
            if team.get("team_name") == team_name or team.get("team") == team_name:
                return team
        
        return None
    except Exception as e:
        print(f"Warning: Error loading team metrics: {e}")
        return None


def load_team_xtp(team_name: str, xtp_path: Path) -> Optional[Dict]:
    """
    Load xTP data for a specific team.
    
    Args:
        team_name: Team name
        xtp_path: Path to xtp_teams_{season}.json
    
    Returns:
        Team xTP dict or None if not found
    """
    if not xtp_path.exists():
        return None
    
    try:
        with xtp_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Handle both array and object with 'teams' property
        teams_array = data if isinstance(data, list) else data.get("teams", [])
        
        for team in teams_array:
            if team.get("team") == team_name:
                return team
        
        return None
    except Exception as e:
        print(f"Warning: Error loading xTP data: {e}")
        return None


def calculate_top_record(match_list: List[Dict], max_rank: int) -> Dict[str, int]:
    """
    Calculate wins and losses vs opponents ranked <= max_rank.
    
    Args:
        match_list: List of match dicts with opponent_rank and result
        max_rank: Maximum rank to include (e.g., 10 for top-10, 33 for top-33)
    
    Returns:
        Dict with 'wins' and 'losses' keys
    """
    wins = 0
    losses = 0
    
    if not match_list:
        return {"wins": 0, "losses": 0}
    
    for match in match_list:
        opponent_rank = match.get("opponent_rank")
        if opponent_rank is None or opponent_rank > max_rank:
            continue
        
        result = match.get("result", "")
        if result and ("W" in result.upper() or "WIN" in result.upper()):
            wins += 1
        elif result and ("L" in result.upper() or "LOSS" in result.upper()):
            losses += 1
    
    return {"wins": wins, "losses": losses}


def count_top25_wins(match_list: List[Dict]) -> int:
    """
    Count wins vs opponents ranked <= 25.
    
    Args:
        match_list: List of match dicts with opponent_rank and result
    
    Returns:
        Number of wins vs top-25 opponents
    """
    if not match_list:
        return 0
    
    wins = 0
    for match in match_list:
        opponent_rank = match.get("opponent_rank")
        result = match.get("result", "")
        
        if opponent_rank is not None and opponent_rank <= 25:
            if result and ("W" in result.upper() or "WIN" in result.upper()):
                wins += 1
    
    return wins


def parse_record(record_str: str) -> Dict[str, int]:
    """
    Parse record string like "14-3" into wins and losses.
    
    Args:
        record_str: Record string like "14-3" or "0-0"
    
    Returns:
        Dict with 'wins' and 'losses' keys
    """
    if not record_str or not isinstance(record_str, str):
        return {"wins": 0, "losses": 0}
    
    parts = record_str.split("-")
    if len(parts) != 2:
        return {"wins": 0, "losses": 0}
    
    try:
        wins = int(parts[0].strip())
        losses = int(parts[1].strip())
        return {"wins": wins, "losses": losses}
    except ValueError:
        return {"wins": 0, "losses": 0}


def extract_minimal_starter_data(
    profile: Dict,
    weight: str,
    xtp_weight_data: Optional[Dict],
    season: int
) -> Dict:
    """
    Extract minimal starter data needed for team page UI.
    
    Args:
        profile: Full wrestler profile dict
        weight: Weight class string
        xtp_weight_data: xTP data for this weight (from xtp_teams JSON)
        season: Season year (e.g., 2026)
    
    Returns:
        Minimal starter data dict
    """
    match_list = profile.get("match_list", [])
    
    # Precompute top-10 and top-33 records
    top10_record = calculate_top_record(match_list, 10)
    top33_record = calculate_top_record(match_list, 33)
    
    # Parse overall record
    record_str = profile.get("record", {}).get("overall", "0-0")
    record = parse_record(record_str)
    
    # Precompute top-25 wins
    top25_wins = count_top25_wins(match_list)
    
    # Extract grade from season_summary (for current season)
    grade = None
    season_summary = profile.get("season_summary", [])
    if season_summary:
        # Find the entry for the current season
        for entry in season_summary:
            if entry.get("season") == season:
                grade = entry.get("grade")
                break
        # Fallback: use first entry if current season not found (shouldn't happen normally)
        if grade is None and season_summary:
            grade = season_summary[0].get("grade")
    
    return {
        "weight": int(weight),
        "wrestler_id": profile.get("wrestler_id"),
        "name": profile.get("name"),
        "current_rank": profile.get("current_rank"),
        "grade": grade,  # Grade for display in table
        "xtp": xtp_weight_data.get("xTP", 0.0) if xtp_weight_data else 0.0,
        "xtp_p": xtp_weight_data.get("xTP_P", 0.0) if xtp_weight_data else 0.0,
        "xtp_a": xtp_weight_data.get("xTP_A", 0.0) if xtp_weight_data else 0.0,
        "xtp_b": xtp_weight_data.get("xTP_B", 0.0) if xtp_weight_data else 0.0,
        "xtp_simple": xtp_weight_data.get("xTP_simple", 0.0) if xtp_weight_data else 0.0,  # Simplified rank-based scoring
        "top10_record": top10_record,
        "top33_record": top33_record,
        "wins": record["wins"],
        "losses": record["losses"],
        "top25_wins": top25_wins,
        "bonus_rate": profile.get("metrics", {}).get("bonus_rate"),
    }


def extract_minimal_roster_data(profile: Dict, season: int) -> Dict:
    """
    Extract minimal roster data needed for remaining roster table.
    
    Args:
        profile: Full wrestler profile dict
        season: Season year (e.g., 2026)
    
    Returns:
        Minimal roster data dict
    """
    match_list = profile.get("match_list", [])
    record_str = profile.get("record", {}).get("overall", "0-0")
    record = parse_record(record_str)
    
    # Precompute top-25 wins
    top25_wins = count_top25_wins(match_list)
    
    # Extract grade from season_summary (for current season)
    grade = None
    season_summary = profile.get("season_summary", [])
    if season_summary:
        # Find the entry for the current season
        for entry in season_summary:
            if entry.get("season") == season:
                grade = entry.get("grade")
                break
        # Fallback: use first entry if current season not found (shouldn't happen normally)
        if grade is None and season_summary:
            grade = season_summary[0].get("grade")
    
    return {
        "weight": profile.get("weight_class"),
        "wrestler_id": profile.get("wrestler_id"),
        "name": profile.get("name"),
        "grade": grade,  # Grade for display in table
        "wins": record["wins"],
        "losses": record["losses"],
        "top25_wins": top25_wins,
        "bonus_rate": profile.get("metrics", {}).get("bonus_rate"),
    }


def validate_and_warn(teams_data: List[Dict], rankings_by_weight: Dict[str, List[Dict]], force_backup_ids: Set[str]) -> None:
    """Perform validation and emit warnings."""
    # Warn if team has fewer than 7 non-null starters
    for team_data in teams_data:
        team_id = team_data["team_id"]
        team_name = team_data["name"]
        
        # Handle both old format (roster.starters) and new format (starters)
        if "starters" in team_data:
            # New format: starters is dict of weight -> profile object
            starters = team_data["starters"]
            non_null_count = sum(1 for profile in starters.values() if profile is not None)
        elif "roster" in team_data and "starters" in team_data["roster"]:
            # Old format: roster.starters is dict of weight -> wrestler_id
            starters = team_data["roster"]["starters"]
            non_null_count = sum(1 for wid in starters.values() if wid is not None)
        else:
            non_null_count = 0
        
        if non_null_count < 7:
            print(f"Warning: {team_name} ({team_id}) has only {non_null_count} starters (less than 7)")
    
    # Warn if the same wrestler_id is starter for multiple teams
    wrestler_to_teams = defaultdict(list)
    for team_data in teams_data:
        team_id = team_data["team_id"]
        team_name = team_data["name"]
        
        # Handle both formats
        if "starters" in team_data:
            # New format: extract wrestler_id from profile objects
            starters = team_data["starters"]
            for weight, profile in starters.items():
                if profile and isinstance(profile, dict):
                    wrestler_id = profile.get("wrestler_id")
                    if wrestler_id:
                        wrestler_to_teams[wrestler_id].append((team_id, team_name, weight))
        elif "roster" in team_data and "starters" in team_data["roster"]:
            # Old format: wrestler_id is the value
            starters = team_data["roster"]["starters"]
            for weight, wrestler_id in starters.items():
                if wrestler_id:
                    wrestler_to_teams[wrestler_id].append((team_id, team_name, weight))
    
    for wrestler_id, teams_list in wrestler_to_teams.items():
        if len(teams_list) > 1:
            teams_str = ", ".join([f"{name} ({tid}) at {w}" for tid, name, w in teams_list])
            print(f"Warning: Wrestler {wrestler_id} is starter for multiple teams: {teams_str}")


def process_league(season: int, league: str, state: str, gender: str, args: argparse.Namespace) -> None:
    """Process team profiles for a single league/gender combination."""
    # Setup paths based on league type
    if league == 'hs':
        teams_list_path = Path(f"data/team_lists/hs_{state.lower()}_{gender}/teams.json")
        rankings_dir = Path("mt/rankings_data") / f"hs_{state.lower()}_{gender}" / str(season)
        starter_overrides_path = rankings_dir / "starter_overrides.json"
        out_dir = Path("frontend/hs-ky-ui/public/data/teams") / gender / str(season)
        wrestlers_dir = Path("frontend/hs-ky-ui/public/data/wrestlers") / gender / str(season)
        index_teams_path = wrestlers_dir / "index_teams.json"
        team_metrics_path = Path("frontend/hs-ky-ui/public/data/team_metrics") / gender / str(season) / "team_metrics.json"
        xtp_path = Path("frontend/hs-ky-ui/public/data/xtp") / gender / str(season) / f"xtp_teams_{season}.json"
        if gender == 'boys':
            weights = [106, 113, 120, 126, 132, 138, 144, 150, 157, 165, 175, 190, 215, 285]
        else: # girls
            weights = [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235]
    else: # ncaa
        teams_list_path = Path(f"data/team_lists/ncaa_men/{season}/teams.json")
        rankings_dir = Path("mt/rankings_data") / "ncaa_men" / str(season)
        starter_overrides_path = rankings_dir / "starter_overrides.json"
        out_dir = Path("frontend/wrestledata-ui/public/data/teams")
        wrestlers_dir = None  # Not used for NCAA
        index_teams_path = None
        team_metrics_path = None
        xtp_path = None
        weights = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]
    
    # Override with CLI args if provided
    if args.teams_list:
        teams_list_path = Path(args.teams_list)
    if args.rankings_dir:
        rankings_dir = Path(args.rankings_dir)
    if args.starter_overrides:
        starter_overrides_path = Path(args.starter_overrides)
    if args.out_dir:
        out_dir = Path(args.out_dir)

    as_of_date = date.fromisoformat(args.as_of_date) if getattr(args, "as_of_date", None) else None

    print(f"Building team profiles for season {season} ({league.upper()} {state or ''} {gender or ''})...")
    print(f"Teams list: {teams_list_path}")
    print(f"Rankings dir: {rankings_dir}")
    print(f"Output dir: {out_dir}")
    if league == 'hs':
        print(f"Wrestlers dir: {wrestlers_dir}")
        print(f"Index teams: {index_teams_path}")
    
    # Step 1: Load team list
    print("\nStep 1: Loading team list...")
    teams_master = load_teams_list(str(teams_list_path))
    print(f"Loaded {len(teams_master)} teams")
    
    # Step 2: Load starter overrides
    print("\nStep 2: Loading starter overrides...")
    force_backup_ids = load_starter_overrides(str(starter_overrides_path))
    if force_backup_ids:
        print(f"Loaded {len(force_backup_ids)} starter overrides")
    else:
        print("No starter overrides found")
    
    # Step 3: Load boys inactive mask (if boys)
    masked_wrestler_ids = set()
    if league == 'hs' and gender == 'boys':
        print("\nStep 3: Loading boys inactive mask...")
        masked_wrestler_ids = load_boys_inactive_mask(season, rankings_dir)
        if masked_wrestler_ids:
            print(f"Loaded mask for {len(masked_wrestler_ids)} inactive wrestlers")
        else:
            print("No mask file found (or empty)")
    
    # Step 4: Load rankings per weight
    print("\nStep 4: Loading rankings...")
    rankings_by_weight = load_rankings_by_weight(str(rankings_dir), league=league, gender=gender)
    print(f"Loaded rankings for {len(rankings_by_weight)} weight classes")
    
    # Step 5: Resolve starters for each team
    print("\nStep 5: Resolving starters...")
    teams_data = []
    
    # Convert weights to strings for consistency
    weight_strs = [str(w) for w in weights]
    
    for team in teams_master:
        team_name = team.get("name", "")
        abbreviation = team.get("abbreviation", "")
        state_from_team = team.get("state", "")
        governing_body = team.get("governing_body", "NCAA")
        division_str = team.get("division", "")
        url = team.get("url")
        region = team.get("region") # Get region for HS
        
        # Normalize division
        if league == 'hs':
            division = f"HS {gender.capitalize()}"
        else:
            division = "D1"
        
        # Extract conference (only for NCAA)
        conference = extract_conference(division_str) if league == 'ncaa' else None
        
        # Compute team_id
        team_id = slugify_team_name(team_name)
        
        # Resolve starters
        starters = resolve_starters_for_team(team_id, rankings_by_weight, force_backup_ids, weight_classes=weight_strs, as_of_date=as_of_date, league=league)
        
        # Build base team data
        team_data = {
            "schema_version": "2.0",  # Bump version for embedded profiles
            "season": season,
            "gender": gender if league == 'hs' else None,
            "team_id": team_id,
            "team_name": team_name,
            "name": team_name,  # Keep for backward compatibility
            "abbreviation": abbreviation,
            "governing_body": governing_body,
            "division": division,
            "conference": conference,
            "location": {
                "state": state_from_team,
                "region": region # Add region for HS
            },
            "urls": {
                "trackwrestling": url,
                "school": None,
            },
            "derived_from": {
                "rankings_dir": str(rankings_dir),
                "starter_overrides_file": str(starter_overrides_path) if starter_overrides_path else None,
            },
            "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        
        # For HS: Build minimal team profile with only UI-required data
        if league == 'hs' and wrestlers_dir and wrestlers_dir.exists() and index_teams_path and index_teams_path.exists():
            print(f"  Building minimal team profile for {team_name}...")
            
            # Load xTP data for this team (needed for starter xTP values)
            xtp_data = None
            if xtp_path and xtp_path.exists():
                xtp_data = load_team_xtp(team_name, xtp_path)
            
            # Load full roster from index_teams.json
            roster_ids = load_team_roster_from_index(team_id, index_teams_path)
            if not roster_ids:
                print(f"    Warning: No roster found in index_teams.json, using old format")
                team_data["roster"] = {
                    "weights": weights,
                    "starters": {str(w): starters.get(str(w)) for w in weights},
                    "starters_source": "ranking_files_with_overrides",
                }
            else:
                print(f"    Found {len(roster_ids)} wrestlers in roster")
                
                # Filter out masked wrestlers (boys only)
                if masked_wrestler_ids:
                    original_count = len(roster_ids)
                    roster_ids = [wid for wid in roster_ids if str(wid) not in masked_wrestler_ids]
                    filtered_count = original_count - len(roster_ids)
                    if filtered_count > 0:
                        print(f"    Filtered out {filtered_count} masked wrestler(s)")
                
                # Load all wrestler profiles (needed to extract minimal data)
                wrestler_profiles = {}
                profiles_loaded = 0
                profiles_missing = 0
                
                for wrestler_id in roster_ids:
                    profile = load_wrestler_profile(wrestler_id, wrestlers_dir)
                    if profile:
                        wrestler_profiles[wrestler_id] = profile
                        profiles_loaded += 1
                    else:
                        profiles_missing += 1
                
                if profiles_missing > 0:
                    print(f"    Warning: {profiles_missing} profiles not found (may not be generated yet)")
                
                print(f"    Loaded {profiles_loaded} wrestler profiles")
                
                # Build starters with minimal data (keyed by weight)
                starters_minimal = {}
                starter_ids_set = set(str(v) for v in starters.values() if v)
                
                for weight_str, starter_id in starters.items():
                    # Skip masked starters (boys only)
                    if masked_wrestler_ids and starter_id and str(starter_id) in masked_wrestler_ids:
                        continue
                    
                    if starter_id and starter_id in wrestler_profiles:
                        profile = wrestler_profiles[starter_id]
                        # Get xTP data for this weight
                        xtp_weight_data = None
                        if xtp_data and "weights" in xtp_data:
                            xtp_weight_data = xtp_data["weights"].get(weight_str)
                        
                        starters_minimal[weight_str] = extract_minimal_starter_data(
                            profile, weight_str, xtp_weight_data, season
                        )
                    elif starter_id:
                        # Starter ID exists but profile not found - log warning
                        print(f"    Warning: Starter profile not found for {starter_id} at {weight_str}")
                
                # Build remaining roster with minimal data (non-starters)
                remaining_minimal = []
                for wrestler_id, profile in wrestler_profiles.items():
                    # Skip masked wrestlers (boys only)
                    if masked_wrestler_ids and str(wrestler_id) in masked_wrestler_ids:
                        continue
                    
                    if str(wrestler_id) not in starter_ids_set:
                        remaining_minimal.append(extract_minimal_roster_data(profile, season))
                
                # Sort remaining by weight, then by name
                remaining_minimal.sort(key=lambda p: (
                    p.get("weight", 999),
                    p.get("name", "")
                ))
                
                # Embed minimal data in team data
                team_data["starters"] = starters_minimal
                team_data["remaining"] = remaining_minimal
                
                # Compute team_xTP_simple total from starters (sum of all xTP_simple values)
                team_xTP_simple = sum(s.get("xtp_simple", 0.0) for s in starters_minimal.values())
                team_data["team_xTP_simple"] = round(team_xTP_simple, 2)
                
                # Load and embed team metrics if available
                if team_metrics_path and team_metrics_path.exists():
                    team_metrics = load_team_metrics(team_name, team_metrics_path)
                    if team_metrics:
                        # Extract metrics from nested structure (team_metrics.metrics.*)
                        metrics_obj = team_metrics.get("metrics", {})
                        
                        # Extract only the fields needed for team overview
                        # Get wins/losses from counts object (wins_included/losses_included)
                        counts = team_metrics.get("counts", {})
                        
                        team_data["team_metrics"] = {
                            "projected_state_points": team_xTP_simple,  # Use xTP_simple as primary score
                            "team_rank": team_metrics.get("team_rank"),
                            "placement_points": team_metrics.get("placement_points"),
                            "advancement_points": team_metrics.get("advancement_points"),
                            "bonus_points": team_metrics.get("bonus_points"),
                            "overall": {
                                "wins": counts.get("wins_included") or team_metrics.get("total_wins"),
                                "losses": counts.get("losses_included") or team_metrics.get("total_losses"),
                            },
                            "top33": {
                                "wins": None,  # Will be computed from starters
                                "losses": None,
                            },
                            "top10": {
                                "wins": None,  # Will be computed from starters
                                "losses": None,
                            },
                            # Extract from metrics.metrics.* structure (nested objects with value/rank)
                            "bonus_rate": metrics_obj.get("bonus_rate"),
                            "pin_rate": metrics_obj.get("pin_rate"),
                            "tech_rate": metrics_obj.get("tech_rate"),
                        }
                        
                        # Compute top10/top33 records from starters
                        top10_wins = sum(s.get("top10_record", {}).get("wins", 0) for s in starters_minimal.values())
                        top10_losses = sum(s.get("top10_record", {}).get("losses", 0) for s in starters_minimal.values())
                        top33_wins = sum(s.get("top33_record", {}).get("wins", 0) for s in starters_minimal.values())
                        top33_losses = sum(s.get("top33_record", {}).get("losses", 0) for s in starters_minimal.values())
                        
                        team_data["team_metrics"]["top10"]["wins"] = top10_wins
                        team_data["team_metrics"]["top10"]["losses"] = top10_losses
                        team_data["team_metrics"]["top33"]["wins"] = top33_wins
                        team_data["team_metrics"]["top33"]["losses"] = top33_losses
                
                # Log file size estimate
                json_str = json.dumps(team_data, indent=2, ensure_ascii=False)
                size_kb = len(json_str.encode('utf-8')) / 1024
                print(f"    Team JSON size: {size_kb:.1f} KB")
        else:
            # NCAA or HS without wrestler profiles: use old format
            team_data["roster"] = {
                "weights": weights,
                "starters": {str(w): starters.get(str(w)) for w in weights},
                "starters_source": "ranking_files_with_overrides",
            }
        
        teams_data.append(team_data)
    
    print(f"Resolved starters for {len(teams_data)} teams")
    
    # Step 5: Write team profile JSON files
    print("\nStep 5: Writing team profile files...")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    for team_data in teams_data:
        team_id = team_data["team_id"]
        output_file = out_dir / f"{team_id}.json"
        
        with output_file.open("w", encoding="utf-8") as f:
            json.dump(team_data, f, indent=2, ensure_ascii=False)
    
    print(f"Wrote {len(teams_data)} team profile files to {out_dir}")
    
    # Step 6: Validation and warnings
    print("\nStep 6: Validation...")
    validate_and_warn(teams_data, rankings_by_weight, force_backup_ids)
    
    print("\nDone!")


def main() -> None:
    args = parse_args()
    season = args.season
    league = args.league
    state = args.state
    gender = args.gender
    
    # Validate HS parameters
    if league == 'hs':
        if not state:
            raise ValueError("For HS league, -state is required.")
        # Process both genders automatically
        genders = ['boys', 'girls']
        for gender in genders:
            print(f"\n{'=' * 80}")
            print(f"Processing {gender}...")
            print(f"{'=' * 80}")
            process_league(season, league, state, gender, args)
    else: # ncaa
        process_league(season, league, state, None, args)


if __name__ == "__main__":
    main()

