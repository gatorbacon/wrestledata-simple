#!/usr/bin/env python3
"""
Build team metrics by aggregating wrestler-level metrics.

This script MUST run AFTER build_wrestler_profiles.py.

Usage:
    python scripts/team_metrics/build_team_metrics.py \
        --season 2026 \
        --teams-list data/team_lists/2026/ncaa_d1_teams.json \
        --rankings-dir mt/rankings_data/2026 \
        --starter-overrides mt/rankings_data/2026/starter_overrides.json \
        --wrestler-profiles-dir mt/wrestlers/2026/by_id \
        --out-file mt/team_metrics/2026/team_metrics.json
"""

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build team metrics from wrestler profiles"
    )
    parser.add_argument(
        "--season",
        type=int,
        required=True,
        help="Season year (e.g., 2026)",
    )
    parser.add_argument(
        "--teams-list",
        type=str,
        default=None,
        help="Path to NCAA D1 teams JSON file (auto-determined if not specified)",
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
        help="Path to starter_overrides.json (optional, auto-determined if not specified)",
    )
    parser.add_argument(
        "--wrestler-profiles-dir",
        type=str,
        default=None,
        help="Directory containing wrestler profile JSON files (auto-determined if not specified)",
    )
    parser.add_argument(
        "--out-file",
        type=str,
        default=None,
        help="Output JSON file path (auto-determined if not specified)",
    )
    parser.add_argument('-league', type=str, default='ncaa', choices=['ncaa', 'hs'],
                        help='League type: ncaa (default) or hs')
    parser.add_argument('-state', type=str, help='State code (required when league=hs, currently only KY supported)')
    parser.add_argument('-gender', type=str, choices=['boys', 'girls'],
                        help='Gender: boys or girls (optional when league=hs, defaults to processing both)')
    parser.add_argument(
        "--debug-team",
        type=str,
        default=None,
        help="Team name or team_id to debug (optional)",
    )
    return parser.parse_args()


def slugify_team_name(team_name: str) -> str:
    """Convert team name to team_id (slug)."""
    slug = team_name.lower()
    slug = slug.replace(" ", "_")
    # Remove periods and apostrophes
    slug = slug.replace(".", "").replace("'", "")
    # Collapse multiple underscores
    slug = re.sub(r"_+", "_", slug)
    slug = slug.strip("_")
    return slug


def extract_conference(division: str) -> Optional[str]:
    """Extract conference from division string (e.g., 'DI - Big 12' -> 'Big 12')."""
    if not division:
        return None
    
    # Look for pattern "DI - {Conference}"
    match = re.search(r"DI\s*-\s*([^,]+)", division)
    if match:
        return match.group(1).strip()
    
    # If just "Division I" with no conference, return None
    return None


def load_teams_list(teams_list_path: str) -> List[Dict]:
    """Load team list JSON file."""
    with open(teams_list_path, "r", encoding="utf-8") as f:
        teams = json.load(f)
    return teams


def load_starter_overrides(overrides_path: Optional[str]) -> Set[str]:
    """Load starter overrides (force_backup_ids)."""
    if not overrides_path or not Path(overrides_path).exists():
        return set()
    
    with open(overrides_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    return set(data.get("force_backup_ids", []))


def load_rankings(rankings_dir: str, league: str = 'ncaa', gender: str = None) -> Dict[str, List[Dict]]:
    """Load all rankings_*.json files, organized by weight."""
    rankings_dir_path = Path(rankings_dir)
    rankings_by_weight = {}
    
    if league == 'hs':
        if gender == 'boys':
            weight_classes = [106, 113, 120, 126, 132, 138, 144, 150, 157, 165, 175, 190, 215, 285]
        else: # girls
            weight_classes = [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235]
    else: # ncaa
        weight_classes = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]
    
    weight_strs = [str(w) for w in weight_classes]
    
    for weight in weight_strs:
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


def apply_starter_overrides(
    rankings: List[Dict], force_backup_ids: Set[str]
) -> List[Dict]:
    """Apply starter overrides to rankings."""
    result = []
    for entry in rankings:
        wrestler_id = entry.get("wrestler_id")
        is_starter = entry.get("is_starter", True)
        
        # If wrestler is in force_backup_ids, set is_starter to False
        if wrestler_id in force_backup_ids:
            is_starter = False
        
        new_entry = {**entry, "is_starter": is_starter}
        result.append(new_entry)
    
    return result


def build_starters_by_team(
    rankings_by_weight: Dict[str, List[Dict]],
    teams_master: List[Dict],
    force_backup_ids: Set[str],
    weights: List[int] = None,
) -> Dict[str, Dict[str, Optional[str]]]:
    """
    Build starters map: team_id -> weight -> wrestler_id.
    
    For each team, for each weight, pick the lowest rank entry with is_starter==true.
    If none marked starter (after overrides), pick the lowest rank entry as fallback.
    """
    starters_map = defaultdict(dict)  # team_id -> weight -> wrestler_id
    
    # Build team_id lookup from teams_master
    team_id_by_name = {}
    for team in teams_master:
        team_name = team.get("name", "")
        team_id = slugify_team_name(team_name)
        team_id_by_name[team_name] = team_id
        starters_map[team_id] = {}  # Initialize for all teams
    
    # Process each weight
    for weight, rankings in rankings_by_weight.items():
        # Apply overrides
        rankings = apply_starter_overrides(rankings, force_backup_ids)
        
        # Group by team_id
        by_team = defaultdict(list)
        for entry in rankings:
            team_name = entry.get("team", "")
            team_id = slugify_team_name(team_name)
            by_team[team_id].append(entry)
        
        # For each team, find starter
        for team_id, team_entries in by_team.items():
            # Sort by rank (ascending)
            team_entries.sort(key=lambda x: (
                int(x.get("rank", 9999)) if isinstance(x.get("rank"), (int, str)) and str(x.get("rank")).isdigit() else 9999
            ))
            
            # First, try to find one marked as starter
            starter = None
            for entry in team_entries:
                if entry.get("is_starter", False):
                    starter = entry
                    break
            
            # If no starter found, use lowest rank as fallback
            if not starter and team_entries:
                starter = team_entries[0]
            
            if starter:
                wrestler_id = starter.get("wrestler_id")
                starters_map[team_id][weight] = wrestler_id
            else:
                starters_map[team_id][weight] = None
    
    return dict(starters_map)


def load_all_wrestler_profiles(profiles_dir: str) -> Dict[str, Dict]:
    """Load all wrestler profiles from directory."""
    profiles_dir_path = Path(profiles_dir)
    profiles = {}
    
    for profile_file in profiles_dir_path.glob("*.json"):
        try:
            with profile_file.open("r", encoding="utf-8") as f:
                profile = json.load(f)
            wrestler_id = profile.get("wrestler_id")
            if wrestler_id:
                profiles[wrestler_id] = profile
        except Exception as e:
            print(f"Warning: Error loading {profile_file}: {e}")
            continue
    
    return profiles


def load_wrestler_metrics(profile: Dict) -> Optional[Dict]:
    """
    Extract metrics from wrestler profile.
    
    Note: opponent_rank values in match_list should be from starter-only rankings
    (generated by build_starter_rankings.py and used by build_wrestler_profiles.py).
    
    Returns dict with:
    - match_count, win_count
    - pf7, pa7
    - si_plus, df_plus, apr_plus
    - top10_wins, top10_matches (based on starter-only ranks)
    - top33_wins, top33_matches (based on starter-only ranks)
    - bonus_wins, pin_wins, tech_wins
    """
    if not profile:
        return None
    
    # Basic counts from record
    record = profile.get("record", {})
    overall = record.get("overall", "0-0")
    try:
        wins_str, losses_str = overall.split("-")
        win_count = int(wins_str)
        match_count = win_count + int(losses_str)
    except Exception:
        win_count = 0
        match_count = 0
    
    # Skip if no matches
    if match_count == 0:
        return None
    
    # Metrics
    metrics = profile.get("metrics", {})
    pf7 = metrics.get("pf7", 0.0)
    pa7 = metrics.get("pa7", 0.0)
    si_plus = metrics.get("si_plus", 100.0)
    df_plus = metrics.get("df_plus", 100.0)
    apr_plus = metrics.get("apr_plus", 100.0)
    
    # Counts from match_list if available
    match_list = profile.get("match_list", [])
    top10_wins = 0
    top10_matches = 0
    top33_wins = 0
    top33_matches = 0
    bonus_wins = 0
    pin_wins = 0
    tech_wins = 0
    
    if match_list:
        for match in match_list:
            result = match.get("result", "")
            method = match.get("method", "")
            opponent_rank = match.get("opponent_rank")
            
            is_win = (result == "W")
            
            if opponent_rank is not None:
                if opponent_rank <= 10:
                    top10_matches += 1
                    if is_win:
                        top10_wins += 1
                if opponent_rank <= 33:
                    top33_matches += 1
                    if is_win:
                        top33_wins += 1
            
            if is_win:
                # Check for bonus wins
                # User specified: "MD", "TF", "FALL" are the bonus methods
                method_upper = method.upper() if method else ""
                if method_upper == "MD":
                    bonus_wins += 1
                elif method_upper == "TF":
                    bonus_wins += 1
                    tech_wins += 1
                elif method_upper in ["FALL", "PIN"]:  # PIN is alias for FALL in data
                    bonus_wins += 1
                    pin_wins += 1
    
    return {
        "match_count": match_count,
        "win_count": win_count,
        "pf7": pf7,
        "pa7": pa7,
        "si_plus": si_plus,
        "df_plus": df_plus,
        "apr_plus": apr_plus,
        "top10_wins": top10_wins,
        "top10_matches": top10_matches,
        "top33_wins": top33_wins,
        "top33_matches": top33_matches,
        "bonus_wins": bonus_wins,
        "pin_wins": pin_wins,
        "tech_wins": tech_wins,
    }


def compute_team_metrics(
    included_wrestler_ids: List[str],
    all_profiles: Dict[str, Dict],
) -> Optional[Dict]:
    """Compute team-level metrics from included wrestlers."""
    wrestler_metrics = []
    
    for wrestler_id in included_wrestler_ids:
        profile = all_profiles.get(wrestler_id)
        if not profile:
            continue
        
        metrics = load_wrestler_metrics(profile)
        if metrics and metrics["match_count"] > 0:
            wrestler_metrics.append(metrics)
    
    if not wrestler_metrics:
        return None
    
    # Sum totals
    total_matches = sum(w["match_count"] for w in wrestler_metrics)
    total_wins = sum(w["win_count"] for w in wrestler_metrics)
    
    if total_matches == 0:
        return None
    
    # Match-weighted averages
    avg_pf7 = sum(w["pf7"] * w["match_count"] for w in wrestler_metrics) / total_matches
    avg_pa7 = sum(w["pa7"] * w["match_count"] for w in wrestler_metrics) / total_matches
    avg_pd7 = avg_pf7 - avg_pa7
    
    si_plus = sum(w["si_plus"] * w["match_count"] for w in wrestler_metrics) / total_matches
    df_plus = sum(w["df_plus"] * w["match_count"] for w in wrestler_metrics) / total_matches
    apr_plus = sum(w["apr_plus"] * w["match_count"] for w in wrestler_metrics) / total_matches
    
    # Rates (wins denominator)
    total_bonus_wins = sum(w["bonus_wins"] for w in wrestler_metrics)
    total_pin_wins = sum(w["pin_wins"] for w in wrestler_metrics)
    total_tech_wins = sum(w["tech_wins"] for w in wrestler_metrics)
    
    bonus_rate = (total_bonus_wins / total_wins) if total_wins > 0 else None
    pin_rate = (total_pin_wins / total_wins) if total_wins > 0 else None
    tech_rate = (total_tech_wins / total_wins) if total_wins > 0 else None
    
    # Top win percentages
    total_top10_wins = sum(w["top10_wins"] for w in wrestler_metrics)
    total_top10_matches = sum(w["top10_matches"] for w in wrestler_metrics)
    total_top33_wins = sum(w["top33_wins"] for w in wrestler_metrics)
    total_top33_matches = sum(w["top33_matches"] for w in wrestler_metrics)
    
    top10_win_pct = (total_top10_wins / total_top10_matches) if total_top10_matches > 0 else None
    top33_win_pct = (total_top33_wins / total_top33_matches) if total_top33_matches > 0 else None
    
    total_losses = total_matches - total_wins
    win_pct = (total_wins / total_matches) if total_matches > 0 else None
    
    return {
        "avg_pf7": round(avg_pf7, 2),
        "avg_pa7": round(avg_pa7, 2),
        "avg_pd7": round(avg_pd7, 2),
        "bonus_rate": round(bonus_rate, 3) if bonus_rate is not None else None,
        "pin_rate": round(pin_rate, 3) if pin_rate is not None else None,
        "tech_rate": round(tech_rate, 3) if tech_rate is not None else None,
        "top10_win_pct": round(top10_win_pct, 3) if top10_win_pct is not None else None,
        "top33_win_pct": round(top33_win_pct, 3) if top33_win_pct is not None else None,
        "si_plus": round(si_plus, 1),
        "df_plus": round(df_plus, 1),
        "apr_plus": round(apr_plus, 1),
        "total_matches": total_matches,
        "total_wins": total_wins,
        "total_losses": total_losses,
        "win_pct": round(win_pct, 3) if win_pct is not None else None,
        "wrestlers_included": len(wrestler_metrics),
    }


def compute_league_ranks(
    teams_data: List[Dict],
) -> Dict[str, Dict[str, int]]:
    """
    Compute league ranks for all metrics.
    
    Returns: dict mapping team_id -> metric_name -> rank
    """
    # Collect all metric values
    metrics_to_rank = [
        "avg_pf7",
        "avg_pa7",
        "avg_pd7",
        "bonus_rate",
        "pin_rate",
        "tech_rate",
        "top10_win_pct",
        "top33_win_pct",
        "si_plus",
        "df_plus",
        "apr_plus",
    ]
    
    ranks = {}
    
    for metric in metrics_to_rank:
        # Collect (team_id, value, matches_included) tuples
        values = []
        for team in teams_data:
            team_id = team.get("team_id")
            metrics = team.get("metrics", {})
            advanced = team.get("advanced_metrics", {})
            counts = team.get("counts", {})
            
            if metric in metrics:
                value = metrics[metric].get("value")
            elif metric in advanced:
                value = advanced[metric].get("value")
            else:
                continue
            
            if value is not None:
                matches = counts.get("matches_included", 0)
                values.append((team_id, value, matches))
        
        # Sort: avg_pa7 is ascending (lower is better), all others descending
        if metric == "avg_pa7":
            values.sort(key=lambda x: (x[1], -x[2], x[0]))  # value asc, matches desc, team_id asc
        else:
            values.sort(key=lambda x: (-x[1], -x[2], x[0]))  # value desc, matches desc, team_id asc
        
        # Assign ranks
        for rank, (team_id, _, _) in enumerate(values, start=1):
            if team_id not in ranks:
                ranks[team_id] = {}
            ranks[team_id][metric] = rank
    
    return ranks


def process_league(season: int, league: str, state: Optional[str], gender: str, args: argparse.Namespace) -> None:
    """Process team metrics for a single league/gender combination."""
    # Setup paths based on league type
    if league == 'hs':
        if not state:
            raise ValueError("For HS league, --state is required.")
        teams_list_path = Path(f"data/team_lists/hs_{state.lower()}_{gender}/teams.json")
        rankings_dir = Path("mt/rankings_data") / f"hs_{state.lower()}_{gender}" / str(season)
        starter_overrides_path = rankings_dir / "starter_overrides.json"
        wrestler_profiles_dir = Path("frontend/hs-ky-ui/public/data/wrestlers") / gender / str(season) / "by_id"
        out_file = Path("frontend/hs-ky-ui/public/data/team_metrics") / gender / str(season) / "team_metrics.json"
        if gender == 'boys':
            weights = [106, 113, 120, 126, 132, 138, 144, 150, 157, 165, 175, 190, 215, 285]
        else: # girls
            weights = [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235]
    else: # ncaa
        teams_list_path = Path(f"data/team_lists/{season}/ncaa_d1_teams.json")
        rankings_dir = Path("mt/rankings_data") / str(season)
        starter_overrides_path = rankings_dir / "starter_overrides.json"
        wrestler_profiles_dir = Path("frontend/wrestledata-ui/public/data/wrestlers") / str(season) / "by_id"
        out_file = Path("frontend/wrestledata-ui/public/data/team_metrics") / str(season) / "team_metrics.json"
        weights = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]
    
    # Override with CLI args if provided
    if args.teams_list:
        teams_list_path = Path(args.teams_list)
    if args.rankings_dir:
        rankings_dir = Path(args.rankings_dir)
    if args.starter_overrides:
        starter_overrides_path = Path(args.starter_overrides)
    if args.wrestler_profiles_dir:
        wrestler_profiles_dir = Path(args.wrestler_profiles_dir)
    if args.out_file:
        out_file = Path(args.out_file)
    
    print(f"Building team metrics for season {season} ({league.upper()} {state or ''} {gender or ''})...")
    print(f"Teams list: {teams_list_path}")
    print(f"Rankings dir: {rankings_dir}")
    print(f"Wrestler profiles dir: {wrestler_profiles_dir}")
    print(f"Output file: {out_file}")
    
    # Step 0: Read and validate inputs
    print("\nStep 0: Loading inputs...")
    teams_master = load_teams_list(str(teams_list_path))
    print(f"Loaded {len(teams_master)} teams from teams list")
    
    force_backup_ids = load_starter_overrides(str(starter_overrides_path))
    print(f"Loaded {len(force_backup_ids)} starter overrides")
    
    rankings_by_weight = load_rankings(str(rankings_dir), league=league, gender=gender)
    print(f"Loaded rankings for {len(rankings_by_weight)} weight classes")
    
    profiles_dir_path = wrestler_profiles_dir
    if not profiles_dir_path.exists():
        raise FileNotFoundError(f"Wrestler profiles directory not found: {profiles_dir_path}")
    
    all_profiles = load_all_wrestler_profiles(str(wrestler_profiles_dir))
    print(f"Loaded {len(all_profiles)} wrestler profiles")
    
    # Step 1: Build starters by team
    print("\nStep 1: Building starters by team...")
    starters_map = build_starters_by_team(rankings_by_weight, teams_master, force_backup_ids, weights=weights)
    print(f"Built starters for {len(starters_map)} teams")
    
    # Step 2-4: Process each team
    print("\nStep 3-5: Computing team metrics...")
    teams_data = []
    
    # Convert weights to strings for consistency
    weight_strs = [str(w) for w in weights]
    
    for team in teams_master:
        team_name = team.get("name", "")
        team_id = slugify_team_name(team_name)
        division = team.get("division", "")
        conference = extract_conference(division) if league == 'ncaa' else None
        
        # Normalize division
        if league == 'hs':
            division = f"HS {gender.capitalize()}"
        else:
            division = "D1"
        
        # Get included wrestler IDs (starters only)
        included_wrestler_ids = []
        for weight in weight_strs:
            wrestler_id = starters_map.get(team_id, {}).get(weight)
            if wrestler_id:
                included_wrestler_ids.append(wrestler_id)
        
        # Compute metrics
        team_metrics = compute_team_metrics(included_wrestler_ids, all_profiles)
        
        if not team_metrics or team_metrics["total_matches"] == 0:
            continue  # Skip teams with 0 matches
        
        # Build team entry
        team_entry = {
            "team_id": team_id,
            "team_name": team_name,
            "conference": conference,
            "division": division,
            "team_rank": {"value": None, "rank": None, "rank_scope": "league"},
            "metrics": {
                "avg_pf7": {"value": team_metrics["avg_pf7"], "rank": None, "rank_scope": "league"},
                "avg_pa7": {"value": team_metrics["avg_pa7"], "rank": None, "rank_scope": "league"},
                "avg_pd7": {"value": team_metrics["avg_pd7"], "rank": None, "rank_scope": "league"},
                "bonus_rate": {"value": team_metrics["bonus_rate"], "rank": None, "rank_scope": "league"},
                "pin_rate": {"value": team_metrics["pin_rate"], "rank": None, "rank_scope": "league"},
                "tech_rate": {"value": team_metrics["tech_rate"], "rank": None, "rank_scope": "league"},
                "top10_win_pct": {"value": team_metrics["top10_win_pct"], "rank": None, "rank_scope": "league"},
                "top33_win_pct": {"value": team_metrics["top33_win_pct"], "rank": None, "rank_scope": "league"},
            },
            "advanced_metrics": {
                "si_plus": {"value": team_metrics["si_plus"], "rank": None, "rank_scope": "league"},
                "df_plus": {"value": team_metrics["df_plus"], "rank": None, "rank_scope": "league"},
                "apr_plus": {"value": team_metrics["apr_plus"], "rank": None, "rank_scope": "league"},
            },
            "counts": {
                "matches_included": team_metrics["total_matches"],
                "wins_included": team_metrics["total_wins"],
                "losses_included": team_metrics["total_losses"],
                "win_pct": team_metrics["win_pct"],
                "wrestlers_included": team_metrics["wrestlers_included"],
                "starters_mode": "ranking_files_with_overrides",
            },
        }
        
        teams_data.append(team_entry)
        
        # Debug output if requested
        if args.debug_team and (team_name == args.debug_team or team_id == args.debug_team):
            print(f"\n=== DEBUG: {team_name} ({team_id}) ===")
            print(f"Starters by weight:")
            for weight in weight_strs:
                wrestler_id = starters_map.get(team_id, {}).get(weight)
                if wrestler_id:
                    profile = all_profiles.get(wrestler_id)
                    if profile:
                        metrics = load_wrestler_metrics(profile)
                        if metrics:
                            print(f"  {weight}: {wrestler_id} - {profile.get('name')}")
                            print(f"    match_count={metrics['match_count']}, win_count={metrics['win_count']}")
                            print(f"    pf7={metrics['pf7']}, pa7={metrics['pa7']}")
                            print(f"    si_plus={metrics['si_plus']}, df_plus={metrics['df_plus']}, apr_plus={metrics['apr_plus']}")
                            print(f"    top10: {metrics['top10_wins']}/{metrics['top10_matches']}")
                            print(f"    top33: {metrics['top33_wins']}/{metrics['top33_matches']}")
                            print(f"    bonus={metrics['bonus_wins']}, pin={metrics['pin_wins']}, tech={metrics['tech_wins']}")
            print(f"\nFinal team metrics:")
            print(f"  avg_pf7={team_metrics['avg_pf7']}, avg_pa7={team_metrics['avg_pa7']}")
            print(f"  bonus_rate={team_metrics['bonus_rate']}, pin_rate={team_metrics['pin_rate']}")
            print(f"  top10_win_pct={team_metrics['top10_win_pct']}, top33_win_pct={team_metrics['top33_win_pct']}")
    
    print(f"Computed metrics for {len(teams_data)} teams")
    
    # Step 6: Compute league ranks
    print("\nStep 6: Computing league ranks...")
    ranks = compute_league_ranks(teams_data)
    
    # Apply ranks to team entries
    for team in teams_data:
        team_id = team["team_id"]
        team_ranks = ranks.get(team_id, {})
        
        for metric_name in ["avg_pf7", "avg_pa7", "avg_pd7", "bonus_rate", "pin_rate", "tech_rate", "top10_win_pct", "top33_win_pct"]:
            if metric_name in team_ranks:
                team["metrics"][metric_name]["rank"] = team_ranks[metric_name]
        
        for metric_name in ["si_plus", "df_plus", "apr_plus"]:
            if metric_name in team_ranks:
                team["advanced_metrics"][metric_name]["rank"] = team_ranks[metric_name]
    
    # Debug: print ranks if requested
    if args.debug_team:
        for team in teams_data:
            team_id = team["team_id"]
            team_name = team["team_name"]
            if team_name == args.debug_team or team_id == args.debug_team:
                print(f"\nFinal ranks for {team_name}:")
                for metric_name in ["avg_pf7", "avg_pa7", "avg_pd7", "bonus_rate", "pin_rate", "tech_rate", "top10_win_pct", "top33_win_pct"]:
                    rank = team["metrics"][metric_name].get("rank")
                    value = team["metrics"][metric_name].get("value")
                    print(f"  {metric_name}: {value} (rank {rank})")
                for metric_name in ["si_plus", "df_plus", "apr_plus"]:
                    rank = team["advanced_metrics"][metric_name].get("rank")
                    value = team["advanced_metrics"][metric_name].get("value")
                    print(f"  {metric_name}: {value} (rank {rank})")
    
    # Step 7-8: Build output JSON
    print("\nStep 7-8: Building output JSON...")
    
    # Check for wrestler profiles timestamp (if available)
    wrestler_profiles_built_at = None
    timestamp_file = profiles_dir_path / ".built_at"
    if timestamp_file.exists():
        try:
            with timestamp_file.open("r") as f:
                wrestler_profiles_built_at = f.read().strip()
        except Exception:
            pass
    
    # Determine governing body and division for output
    if league == 'hs':
        governing_body = "KHSAA"
        division_label = f"HS {gender.capitalize()}"
    else:
        governing_body = "NCAA"
        division_label = "D1"
    
    output_data = {
        "schema_version": "1.1",
        "season": season,
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "breaking_changes": [
            "Removed teams[].roster and teams[].highlights; use mt/teams/<team_id>.json for team identity and starters."
        ],
        "depends_on": {
            "wrestler_profiles_dir": str(wrestler_profiles_dir),
            "wrestler_profiles_built_at_utc": wrestler_profiles_built_at,
        },
        "source": {
            "teams_list_file": str(teams_list_path),
            "rankings_dir": str(rankings_dir),
            "starter_overrides_file": str(starter_overrides_path) if starter_overrides_path.exists() else None,
            "wrestler_profiles_dir": str(wrestler_profiles_dir),
        },
        "league": {
            "governing_body": governing_body,
            "division": division_label,
            "team_count": len(teams_data),
        },
        "metric_definitions": {
            "avg_pf7": "Match-weighted mean of wrestler PF7 across included wrestlers.",
            "avg_pa7": "Match-weighted mean of wrestler PA7 across included wrestlers.",
            "avg_pd7": "avg_pf7 - avg_pa7 (derived).",
            "bonus_rate": "Team bonus_wins / team_wins (wins denom).",
            "pin_rate": "Team pin_wins / team_wins (wins denom).",
            "tech_rate": "Team tech_wins / team_wins (wins denom).",
            "top10_win_pct": "Wins vs Top-10 opponents / matches vs Top-10 opponents.",
            "top33_win_pct": "Wins vs Top-33 opponents / matches vs Top-33 opponents.",
            "si_plus": "Match-weighted mean SI+ across included wrestlers.",
            "df_plus": "Match-weighted mean DF+ across included wrestlers.",
            "apr_plus": "Match-weighted mean APR+ across included wrestlers.",
        },
        "teams": teams_data,
    }
    
    # Write output file
    output_path = out_file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"\nDone! Wrote team metrics to {output_path}")
    print(f"Total teams: {len(teams_data)}")


def main() -> None:
    args = parse_args()
    season = args.season
    league = args.league
    state = args.state
    gender = args.gender
    
    # For HS, process both genders if gender not specified
    if league == 'hs':
        if not state:
            raise ValueError("For HS league, --state is required.")
        
        genders_to_process = [gender] if gender else ['boys', 'girls']
        
        for g in genders_to_process:
            print(f"\n{'=' * 80}")
            print(f"Processing {g}...")
            print(f"{'=' * 80}")
            process_league(season, league, state, g, args)
    else:  # ncaa
        process_league(season, league, state, None, args)


if __name__ == "__main__":
    main()

