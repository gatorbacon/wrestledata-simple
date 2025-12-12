#!/usr/bin/env python3
"""
Show wrestlers with the most matches for D1 teams.

By default shows all wrestlers, or use -starters flag to show only starters.
Use -team flag to group by team and show top teams by total matches.

Usage:
    python scripts/rankings/most_matches.py -season 2026
    python scripts/rankings/most_matches.py -season 2026 -starters
    python scripts/rankings/most_matches.py -season 2026 -team
    python scripts/rankings/most_matches.py -season 2026 -team -starters
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Set
from collections import defaultdict


def load_wrestlers_from_weight_classes(
    season: int, data_dir: str = "mt/rankings_data"
) -> Dict[str, Dict]:
    """
    Load all wrestlers from weight_class_*.json files.
    Returns dict mapping wrestler_id -> {name, team, weight_class, matches_count, wins, losses}
    Note: matches_count, wins, losses from the file may include MFF matches.
    These will be recalculated if ranked filtering is used, or should be filtered separately.
    """
    wrestlers = {}
    data_path = Path(data_dir) / str(season)
    
    if not data_path.exists():
        raise FileNotFoundError(f"Data directory not found: {data_path}")
    
    # Load matches to recalculate stats excluding MFF
    all_matches = []
    for wc_file in sorted(data_path.glob("weight_class_*.json")):
        try:
            with wc_file.open("r", encoding="utf-8") as f:
                wc_data = json.load(f)
        except Exception:
            continue
        
        weight_class = wc_file.stem.replace("weight_class_", "")
        
        # Collect wrestlers first
        for wid, winfo in wc_data.get("wrestlers", {}).items():
            if wid not in wrestlers:
                wrestlers[wid] = {
                    "wrestler_id": wid,
                    "name": winfo.get("name", "Unknown"),
                    "team": winfo.get("team", "Unknown"),
                    "weight_class": weight_class,
                    "matches_count": 0,  # Will be recalculated excluding MFF
                    "wins": 0,
                    "losses": 0,
                }
            else:
                # If wrestler appears in multiple weight classes, keep the first weight class
                # but we'll recalculate stats from all matches
                pass
        
        # Collect matches for this weight class
        for match in wc_data.get("matches", []):
            match["weight_class"] = weight_class
            all_matches.append(match)
    
    # Recalculate stats for all wrestlers excluding MFF matches
    for match in all_matches:
        w1_id = match.get("wrestler1_id")
        w2_id = match.get("wrestler2_id")
        winner_id = match.get("winner_id")
        result = match.get("result", "")
        
        if not w1_id or not w2_id or not winner_id:
            continue
        
        # Skip MFF matches
        if is_mff_result(result):
            continue
        
        # Update stats for wrestler 1
        if w1_id in wrestlers:
            wrestlers[w1_id]["matches_count"] += 1
            if winner_id == w1_id:
                wrestlers[w1_id]["wins"] += 1
            else:
                wrestlers[w1_id]["losses"] += 1
        
        # Update stats for wrestler 2
        if w2_id in wrestlers:
            wrestlers[w2_id]["matches_count"] += 1
            if winner_id == w2_id:
                wrestlers[w2_id]["wins"] += 1
            else:
                wrestlers[w2_id]["losses"] += 1
    
    return wrestlers


def load_starter_ids(season: int, data_dir: str = "mt/rankings_data") -> Set[str]:
    """
    Load all starter wrestler IDs from rankings_*.json files.
    Returns set of wrestler IDs that are marked as starters.
    """
    starter_ids = set()
    data_path = Path(data_dir) / str(season)
    
    if not data_path.exists():
        return starter_ids
    
    for rankings_file in sorted(data_path.glob("rankings_*.json")):
        try:
            with rankings_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        
        rankings = data.get("rankings", [])
        for entry in rankings:
            if entry.get("is_starter", False):
                wid = entry.get("wrestler_id")
                if wid:
                    starter_ids.add(wid)
    
    return starter_ids


def load_ranked_wrestlers(season: int, max_rank: int, data_dir: str = "mt/rankings_data") -> Set[str]:
    """
    Load wrestler IDs that are ranked within the specified max_rank.
    Returns set of wrestler IDs that are ranked 1 through max_rank.
    """
    ranked_ids = set()
    data_path = Path(data_dir) / str(season)
    
    if not data_path.exists():
        return ranked_ids
    
    for rankings_file in sorted(data_path.glob("rankings_*.json")):
        try:
            with rankings_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        
        rankings = data.get("rankings", [])
        for entry in rankings:
            rank = entry.get("rank")
            if rank is None:
                continue
            try:
                rank_int = int(rank)
            except (TypeError, ValueError):
                continue
            
            if rank_int <= max_rank:
                wid = entry.get("wrestler_id")
                if wid:
                    ranked_ids.add(wid)
    
    return ranked_ids


def load_matches_from_weight_classes(
    season: int, data_dir: str = "mt/rankings_data"
) -> List[Dict]:
    """
    Load all matches from weight_class_*.json files.
    Returns list of match dictionaries.
    """
    matches = []
    data_path = Path(data_dir) / str(season)
    
    if not data_path.exists():
        return matches
    
    for wc_file in sorted(data_path.glob("weight_class_*.json")):
        try:
            with wc_file.open("r", encoding="utf-8") as f:
                wc_data = json.load(f)
        except Exception:
            continue
        
        for match in wc_data.get("matches", []):
            matches.append(match)
    
    return matches


def normalize_wrestler_ids(w1_id: str, w2_id: str) -> tuple[str, str]:
    """Normalize wrestler IDs (smaller ID first) to match deduplication logic."""
    return tuple(sorted([w1_id, w2_id]))


def is_mff_result(result: str) -> bool:
    """
    Check if a match result is a medical forfeit (MFF).
    
    Returns True if the result string indicates MFF/MFFL/M. For./medical forfeit.
    """
    if not result:
        return False
    result_str = str(result).lower().strip()
    return (
        'mffl' in result_str
        or 'm. for.' in result_str
        or 'medical forfeit' in result_str
        or result_str == 'mff'
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Show wrestlers with the most matches for D1 teams"
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
        help="Directory containing weight_class_*.json files"
    )
    parser.add_argument(
        "-starters",
        action="store_true",
        help="Show only starters (wrestlers marked is_starter=True in rankings)"
    )
    parser.add_argument(
        "-team",
        action="store_true",
        help="Group by team and show top teams by total matches"
    )
    parser.add_argument(
        "-verbose",
        action="store_true",
        help="Show individual wrestler details when using -team flag"
    )
    parser.add_argument(
        "-matchesperwrestler",
        action="store_true",
        help="Show teams sorted by average matches per wrestler"
    )
    parser.add_argument(
        "-ranked33",
        action="store_true",
        help="Only include matches against opponents ranked in top 33"
    )
    parser.add_argument(
        "-ranked10",
        action="store_true",
        help="Only include matches against opponents ranked in top 10"
    )
    parser.add_argument(
        "-wins",
        action="store_true",
        help="Sort by wins instead of total matches"
    )
    parser.add_argument(
        "-wins10",
        action="store_true",
        help="Sort by wins vs top 10 opponents (implies -ranked10)"
    )
    parser.add_argument(
        "-wins33",
        action="store_true",
        help="Sort by wins vs top 33 opponents (implies -ranked33)"
    )
    parser.add_argument(
        "-top-n",
        type=int,
        default=50,
        help="Number of top wrestlers/teams to display (default: 50)"
    )
    args = parser.parse_args()
    
    season = args.season
    data_dir = args.data_dir
    
    print(f"Loading wrestler data for season {season}...")
    
    # Load all wrestlers
    wrestlers = load_wrestlers_from_weight_classes(season, data_dir)
    
    if not wrestlers:
        print("No wrestler data found.")
        return
    
    # Load ranked opponent sets if filtering by rank
    ranked_opponent_ids = None
    rank_label = ""
    sort_by_wins = args.wins or args.wins10 or args.wins33
    
    if args.wins10:
        print("Loading top 10 ranked opponents...")
        ranked_opponent_ids = load_ranked_wrestlers(season, 10, data_dir)
        rank_label = " (Wins vs Top 10)"
        print(f"Found {len(ranked_opponent_ids)} wrestlers ranked in top 10")
    elif args.wins33:
        print("Loading top 33 ranked opponents...")
        ranked_opponent_ids = load_ranked_wrestlers(season, 33, data_dir)
        rank_label = " (Wins vs Top 33)"
        print(f"Found {len(ranked_opponent_ids)} wrestlers ranked in top 33")
    elif args.ranked10:
        print("Loading top 10 ranked opponents...")
        ranked_opponent_ids = load_ranked_wrestlers(season, 10, data_dir)
        rank_label = " (vs Top 10)"
        print(f"Found {len(ranked_opponent_ids)} wrestlers ranked in top 10")
    elif args.ranked33:
        print("Loading top 33 ranked opponents...")
        ranked_opponent_ids = load_ranked_wrestlers(season, 33, data_dir)
        rank_label = " (vs Top 33)"
        print(f"Found {len(ranked_opponent_ids)} wrestlers ranked in top 33")
    
    # Filter to starters if requested
    if args.starters:
        print("Loading starter information...")
        starter_ids = load_starter_ids(season, data_dir)
        wrestlers = {
            wid: winfo
            for wid, winfo in wrestlers.items()
            if wid in starter_ids
        }
        print(f"Filtered to {len(wrestlers)} starters")
    
    # If filtering by ranked opponents, load team info for all ranked opponents
    # (they might not be in our wrestlers set) so we can check for same-team matches
    ranked_opponent_teams = {}
    if ranked_opponent_ids is not None:
        print("Loading team info for ranked opponents...")
        data_path = Path(data_dir) / str(season)
        for wc_file in sorted(data_path.glob("weight_class_*.json")):
            try:
                with wc_file.open("r", encoding="utf-8") as f:
                    wc_data = json.load(f)
            except Exception:
                continue
            
            for wid, winfo in wc_data.get("wrestlers", {}).items():
                if wid in ranked_opponent_ids:
                    ranked_opponent_teams[wid] = winfo.get("team", "Unknown")
    
    # If filtering by ranked opponents, recalculate stats based on filtered matches
    if ranked_opponent_ids is not None:
        print("Recalculating stats based on ranked opponent matches...")
        all_matches = load_matches_from_weight_classes(season, data_dir)
        
        # Reset stats for all wrestlers
        for wid, winfo in wrestlers.items():
            winfo["matches_count"] = 0
            winfo["wins"] = 0
            winfo["losses"] = 0
        
        # Process matches and count only those against ranked opponents (excluding MFF and same-team matches)
        for match in all_matches:
            w1_id = match.get("wrestler1_id")
            w2_id = match.get("wrestler2_id")
            winner_id = match.get("winner_id")
            result = match.get("result", "")
            
            if not w1_id or not w2_id or not winner_id:
                continue
            
            # Skip MFF matches
            if is_mff_result(result):
                continue
            
            # Skip same-team matches when using ranked filtering
            # (we only want wins against opponents from other teams)
            w1_team = None
            w2_team = None
            
            if w1_id in wrestlers:
                w1_team = wrestlers[w1_id].get("team")
            elif w1_id in ranked_opponent_teams:
                w1_team = ranked_opponent_teams[w1_id]
            
            if w2_id in wrestlers:
                w2_team = wrestlers[w2_id].get("team")
            elif w2_id in ranked_opponent_teams:
                w2_team = ranked_opponent_teams[w2_id]
            
            # If we can determine both teams and they're the same, skip this match
            if w1_team and w2_team and w1_team == w2_team:
                continue  # Same team - skip this match
            
            # Check if opponent is ranked (for each wrestler, check if their opponent is ranked)
            w1_opponent_ranked = w2_id in ranked_opponent_ids
            w2_opponent_ranked = w1_id in ranked_opponent_ids
            
            # Update stats for wrestler 1 if their opponent is ranked
            if w1_id in wrestlers and w1_opponent_ranked:
                wrestlers[w1_id]["matches_count"] += 1
                if winner_id == w1_id:
                    wrestlers[w1_id]["wins"] += 1
                else:
                    wrestlers[w1_id]["losses"] += 1
            
            # Update stats for wrestler 2 if their opponent is ranked
            if w2_id in wrestlers and w2_opponent_ranked:
                wrestlers[w2_id]["matches_count"] += 1
                if winner_id == w2_id:
                    wrestlers[w2_id]["wins"] += 1
                else:
                    wrestlers[w2_id]["losses"] += 1
    
    if args.matchesperwrestler:
        # Calculate average matches per wrestler for each team
        teams_dict = defaultdict(lambda: {
            "team": "",
            "wrestlers": [],
            "total_matches": 0,
        })
        
        for wid, winfo in wrestlers.items():
            team = winfo.get("team", "Unknown")
            teams_dict[team]["team"] = team
            teams_dict[team]["wrestlers"].append(winfo)
            teams_dict[team]["total_matches"] += winfo.get("matches_count", 0)
        
        # Calculate average matches per wrestler for each team
        team_averages = []
        for team, team_data in teams_dict.items():
            num_wrestlers = len(team_data["wrestlers"])
            if num_wrestlers > 0:
                avg_matches = team_data["total_matches"] / num_wrestlers
                team_averages.append({
                    "team": team,
                    "avg_matches": avg_matches,
                    "num_wrestlers": num_wrestlers,
                })
        
        # Sort by average matches or wins (descending)
        if sort_by_wins:
            # Calculate average wins per wrestler for each team
            for team_info in team_averages:
                team = team_info["team"]
                team_wrestlers = [w for w in wrestlers.values() if w.get("team") == team]
                if team_wrestlers:
                    total_wins = sum(w.get("wins", 0) for w in team_wrestlers)
                    team_info["avg_wins"] = total_wins / len(team_wrestlers)
                else:
                    team_info["avg_wins"] = 0.0
            team_averages.sort(key=lambda x: (-x.get("avg_wins", 0), x["team"]))
            sort_label = "Average Wins"
        else:
            team_averages.sort(key=lambda x: (-x["avg_matches"], x["team"]))
            sort_label = "Average Matches"
        
        # Display results
        filter_label = "Starters" if args.starters else "All Wrestlers"
        print(f"\nAll Teams by {sort_label} per Wrestler{rank_label} ({len(team_averages)} teams, {filter_label}):")
        print("=" * 50)
        
        for idx, team_info in enumerate(team_averages, start=1):
            team = team_info["team"]
            if sort_by_wins:
                avg_value = team_info.get("avg_wins", 0.0)
            else:
                avg_value = team_info["avg_matches"]
            print(f"{idx:>3}. {team:<30} {avg_value:>6.1f}")
    
    elif args.team:
        # Load matches to count unique matches per team (avoiding double-counting)
        print("Loading match data...")
        all_matches = load_matches_from_weight_classes(season, data_dir)
        
        # Filter matches if ranked opponent filtering is enabled
        # We want matches where a wrestler in our set faces a ranked opponent
        # The opponent doesn't need to be in our set (e.g., ranked but not a starter)
        if ranked_opponent_ids is not None:
            filtered_matches = []
            for match in all_matches:
                w1_id = match.get("wrestler1_id")
                w2_id = match.get("wrestler2_id")
                result = match.get("result", "")
                
                if not w1_id or not w2_id:
                    continue
                
                # Skip MFF matches
                if is_mff_result(result):
                    continue
                
                # Skip same-team matches when using ranked filtering
                # (we only want matches against opponents from other teams)
                w1_team = None
                w2_team = None
                
                if w1_id in wrestlers:
                    w1_team = wrestlers[w1_id].get("team")
                elif w1_id in ranked_opponent_teams:
                    w1_team = ranked_opponent_teams[w1_id]
                
                if w2_id in wrestlers:
                    w2_team = wrestlers[w2_id].get("team")
                elif w2_id in ranked_opponent_teams:
                    w2_team = ranked_opponent_teams[w2_id]
                
                # If we can determine both teams and they're the same, skip this match
                if w1_team and w2_team and w1_team == w2_team:
                    continue  # Same team - skip this match
                
                # Include match if:
                # - w1 is in our set AND w2 is ranked, OR
                # - w2 is in our set AND w1 is ranked
                if (w1_id in wrestlers and w2_id in ranked_opponent_ids) or \
                   (w2_id in wrestlers and w1_id in ranked_opponent_ids):
                    filtered_matches.append(match)
            all_matches = filtered_matches
            print(f"Filtered to {len(all_matches)} matches against ranked opponents (MFF excluded)")
        
        # Create wrestler_id -> team mapping
        wrestler_teams = {wid: winfo.get("team", "Unknown") for wid, winfo in wrestlers.items()}
        
        # Group by team and count unique matches
        teams_dict = defaultdict(lambda: {
            "team": "",
            "wrestlers": [],
            "unique_matches": set(),  # Set of (w1_id, w2_id, date) tuples
            "total_wins": 0,
            "total_losses": 0,
        })
        
        # First, add wrestlers to teams
        for wid, winfo in wrestlers.items():
            team = winfo.get("team", "Unknown")
            teams_dict[team]["team"] = team
            teams_dict[team]["wrestlers"].append(winfo)
        
        # Process matches to count unique matches per team
        # For ranked filtering, we want to count matches where our wrestlers face ranked opponents
        # The opponent might not be in our wrestler set (e.g., not a starter), but that's OK
        for match in all_matches:
            w1_id = match.get("wrestler1_id")
            w2_id = match.get("wrestler2_id")
            date = match.get("date", "")
            winner_id = match.get("winner_id")
            result = match.get("result", "")
            
            if not w1_id or not w2_id or not date:
                continue
            
            # Skip MFF matches (should already be filtered, but double-check)
            if is_mff_result(result):
                continue
            
            # For ranked filtering, we need at least one wrestler in our set
            # The opponent can be ranked but not in our set (e.g., opponent is ranked but not a starter)
            w1_in_set = w1_id in wrestler_teams
            w2_in_set = w2_id in wrestler_teams
            
            # Skip if neither wrestler is in our set
            if not w1_in_set and not w2_in_set:
                continue
            
            # Normalize IDs for match identity
            w1_norm, w2_norm = normalize_wrestler_ids(w1_id, w2_id)
            match_key = (w1_norm, w2_norm, date)
            
            # Get teams for both wrestlers (only if they're in our set)
            team1 = wrestler_teams.get(w1_id) if w1_in_set else None
            team2 = wrestler_teams.get(w2_id) if w2_in_set else None
            
            # If both wrestlers are from the same team and both in our set, only count once
            if team1 and team2 and team1 == team2:
                if match_key not in teams_dict[team1]["unique_matches"]:
                    teams_dict[team1]["unique_matches"].add(match_key)
                    # For same-team matches, we can't really assign a win/loss to the team
                    # But we'll count it as a match
            else:
                # Different teams or one wrestler not in our set - count for teams in our set
                # Only count the match for teams where we have a wrestler in our set
                if team1 and match_key not in teams_dict[team1]["unique_matches"]:
                    teams_dict[team1]["unique_matches"].add(match_key)
                    # Only count win/loss if we have a winner and it's one of our wrestlers
                    if winner_id and winner_id == w1_id:
                        teams_dict[team1]["total_wins"] += 1
                    elif winner_id and winner_id == w2_id:
                        teams_dict[team1]["total_losses"] += 1
                
                if team2 and team2 != team1 and match_key not in teams_dict[team2]["unique_matches"]:
                    teams_dict[team2]["unique_matches"].add(match_key)
                    # Only count win/loss if we have a winner and it's one of our wrestlers
                    if winner_id and winner_id == w2_id:
                        teams_dict[team2]["total_wins"] += 1
                    elif winner_id and winner_id == w1_id:
                        teams_dict[team2]["total_losses"] += 1
        
        # Calculate team totals by summing individual wrestler matches
        # This ensures consistency with individual wrestler stats (especially for ranked filtering)
        for team_data in teams_dict.values():
            # Sum individual wrestler matches, wins, and losses
            team_data["total_matches"] = sum(w.get("matches_count", 0) for w in team_data["wrestlers"])
            team_data["total_wins"] = sum(w.get("wins", 0) for w in team_data["wrestlers"])
            team_data["total_losses"] = sum(w.get("losses", 0) for w in team_data["wrestlers"])
            # Remove the unique_matches set as we're using individual sums now
            if "unique_matches" in team_data:
                del team_data["unique_matches"]
        
        # Sort wrestlers within each team by matches (descending)
        for team_data in teams_dict.values():
            team_data["wrestlers"].sort(
                key=lambda w: (-w.get("matches_count", 0), w.get("name", ""))
            )
        
        # Sort teams by total matches or wins (descending) - now using sum of individual matches
        if sort_by_wins:
            sorted_teams = sorted(
                teams_dict.values(),
                key=lambda t: (-t["total_wins"], -t["total_matches"], t["team"])
            )
            sort_label = "Total Wins"
        else:
            sorted_teams = sorted(
                teams_dict.values(),
                key=lambda t: (-t["total_matches"], t["team"])
            )
            sort_label = "Total Matches"
        
        # Display results
        filter_label = "Starters" if args.starters else "All Wrestlers"
        print(f"\nTop {min(args.top_n, len(sorted_teams))} Teams by {sort_label}{rank_label} ({filter_label}):")
        print("=" * 60)
        
        for idx, team_data in enumerate(sorted_teams[:args.top_n], start=1):
            team = team_data["team"]
            
            # Recalculate team totals by summing individual wrestler matches
            # This ensures consistency with individual wrestler stats
            individual_match_sum = sum(w.get("matches_count", 0) for w in team_data["wrestlers"])
            individual_wins_sum = sum(w.get("wins", 0) for w in team_data["wrestlers"])
            individual_losses_sum = sum(w.get("losses", 0) for w in team_data["wrestlers"])
            
            # Use the sum of individual matches as the team total (more accurate)
            total_matches = individual_match_sum
            total_wins = individual_wins_sum
            total_losses = individual_losses_sum
            team_win_pct = (total_wins / total_matches * 100) if total_matches > 0 else 0.0
            team_wl = f"{total_wins}-{total_losses}"
            
            print(f"{idx:>3}. {team}")
            print(f"     Total: {total_matches} matches, {team_wl} ({team_win_pct:.1f}%)")
            
            # Show individual wrestler details only if verbose flag is set
            if args.verbose:
                print(f"     {'Name':<30} {'Weight':<8} {'Matches':<8} {'W-L':<10} {'Win%':<8}")
                print(f"     {'-' * 30} {'-' * 8} {'-' * 8} {'-' * 10} {'-' * 8}")
                
                # Show top wrestlers for this team (up to 10)
                for w in team_data["wrestlers"][:10]:
                    matches = w.get("matches_count", 0)
                    wins = w.get("wins", 0)
                    losses = w.get("losses", 0)
                    win_pct = (wins / matches * 100) if matches > 0 else 0.0
                    wl = f"{wins}-{losses}"
                    
                    print(
                        f"     {w.get('name', 'Unknown'):<30} "
                        f"{w.get('weight_class', '?'):<8} "
                        f"{matches:<8} "
                        f"{wl:<10} "
                        f"{win_pct:>6.1f}%"
                    )
                
                if len(team_data["wrestlers"]) > 10:
                    print(f"     ... and {len(team_data['wrestlers']) - 10} more wrestlers")
                print()  # Add blank line after each team in verbose mode
        
        # Summary stats
        if sorted_teams:
            total_teams = len(sorted_teams)
            total_matches_all = sum(t["total_matches"] for t in sorted_teams)
            total_wrestlers_all = sum(len(t["wrestlers"]) for t in sorted_teams)
            avg_matches_per_team = total_matches_all / total_teams if total_teams > 0 else 0
            max_team_matches = sorted_teams[0]["total_matches"] if sorted_teams else 0
            
            print("\n" + "=" * 90)
            print(f"\nSummary ({filter_label}):")
            print(f"  Total teams: {total_teams}")
            print(f"  Total wrestlers: {total_wrestlers_all}")
            print(f"  Total matches: {total_matches_all}")
            print(f"  Average matches per team: {avg_matches_per_team:.1f}")
            print(f"  Most matches (team): {max_team_matches}")
    
    else:
        # Individual wrestler view (original behavior)
        # Sort by matches_count or wins (descending), then by name
        if sort_by_wins:
            sorted_wrestlers = sorted(
                wrestlers.values(),
                key=lambda w: (-w.get("wins", 0), -w.get("matches_count", 0), w.get("name", ""))
            )
            sort_label = "Wins"
        else:
            sorted_wrestlers = sorted(
                wrestlers.values(),
                key=lambda w: (-w.get("matches_count", 0), w.get("name", ""))
            )
            sort_label = "Match Count"
        
        # Display results
        filter_label = "Starters" if args.starters else "All Wrestlers"
        print(f"\nTop {min(args.top_n, len(sorted_wrestlers))} {filter_label} by {sort_label}{rank_label}:")
        print("=" * 90)
        print(f"{'Rank':<6} {'Name':<30} {'Team':<25} {'Weight':<8} {'Matches':<8} {'W-L':<10} {'Win%':<8}")
        print("-" * 90)
        
        for idx, w in enumerate(sorted_wrestlers[:args.top_n], start=1):
            matches = w.get("matches_count", 0)
            wins = w.get("wins", 0)
            losses = w.get("losses", 0)
            win_pct = (wins / matches * 100) if matches > 0 else 0.0
            wl = f"{wins}-{losses}"
            
            print(
                f"{idx:<6} "
                f"{w.get('name', 'Unknown'):<30} "
                f"{w.get('team', 'Unknown'):<25} "
                f"{w.get('weight_class', '?'):<8} "
                f"{matches:<8} "
                f"{wl:<10} "
                f"{win_pct:>6.1f}%"
            )
        
        # Summary stats
        if sorted_wrestlers:
            total_matches = sum(w.get("matches_count", 0) for w in sorted_wrestlers)
            avg_matches = total_matches / len(sorted_wrestlers) if sorted_wrestlers else 0
            max_matches = sorted_wrestlers[0].get("matches_count", 0) if sorted_wrestlers else 0
            
            print("-" * 90)
            print(f"\nSummary ({filter_label}):")
            print(f"  Total wrestlers: {len(sorted_wrestlers)}")
            print(f"  Total matches: {total_matches}")
            print(f"  Average matches per wrestler: {avg_matches:.1f}")
            print(f"  Most matches: {max_matches}")


if __name__ == "__main__":
    main()

