#!/usr/bin/env python3
"""
Calculate Elo ratings for wrestling (review only).

This script implements an Elo rating system for analysis purposes only.
It does NOT modify existing matrix rankings, dual rankings, or website behavior.

Usage:
    python scripts/rankings/calculate_elo_ratings.py -season 2026 --gender boys
    python scripts/rankings/calculate_elo_ratings.py -season 2026 --league ncaa --gender men
"""

import argparse
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def league_dir_key(league: str, gender: str, state: str = None) -> str:
    if league == 'hs':
        return f"hs_{state.lower()}_{gender}"
    return f"ncaa_{gender}"


def get_weights(league: str, gender: str) -> list:
    if league == 'ncaa':
        return [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]
    if gender == 'boys':
        return [106, 113, 120, 126, 132, 138, 144, 150, 157, 165, 175, 190, 215, 285]
    return [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235]


def get_manual_rank_cutoff(league: str, gender: str) -> int:
    if league == 'ncaa':
        return 33
    return 60 if gender == 'boys' else 36


# Elo constants
INITIAL_ELO = 1500
K_FACTOR_NOVICE = 40  # Matches 1-5
K_FACTOR_INTERMEDIATE = 24  # Matches 6-15
K_FACTOR_EXPERIENCED = 16  # Matches 16+

# NCAA only: seed a Flo-ranked wrestler's starting Elo from their Flo rank
# instead of the flat INITIAL_ELO everyone else gets. Without this, a
# Flo-ranked wrestler who simply hasn't wrestled much yet (or dropped an
# early match) can carry a computed Elo well below their true caliber --
# and since that live Elo is exactly what feeds the expected-score formula
# for anyone who beats them, the win gets under-credited. Seeding from rank
# fixes this at the source: their trajectory starts from an honest point
# instead of the same baseline as an unranked walk-on, and normal Elo
# updates take over from there. Tunable like the K-factors above.
NCAA_FLO_SEED_TOP = 2000     # Elo seed for Flo rank #1
NCAA_FLO_SEED_BOTTOM = 1550  # Elo seed for Flo's rank == the manual cutoff (33)


def flo_seed_elo(rank: int, cutoff: int) -> float:
    """Linear interpolation from NCAA_FLO_SEED_TOP (rank 1) down to
    NCAA_FLO_SEED_BOTTOM (rank == cutoff). Anchored to the fixed cutoff, not
    however many wrestlers Flo actually ranked that week at that weight, so
    a wrestler ranked e.g. 25th reads the same regardless of whether Flo
    published 25 or 33 names that week."""
    rank = max(1, min(rank, cutoff))
    if cutoff <= 1:
        return NCAA_FLO_SEED_TOP
    t = (rank - 1) / (cutoff - 1)
    return NCAA_FLO_SEED_TOP - t * (NCAA_FLO_SEED_TOP - NCAA_FLO_SEED_BOTTOM)


def load_flo_rank_map(season: int, league: str) -> Dict[str, int]:
    """wrestler_id -> Flo rank, for every wrestler apply_flo_rankings.py
    tagged flo_ranked=True. NCAA only -- HS has no FloWrestling data, so
    this returns empty and HS's Elo seeding is unaffected."""
    rank_map: Dict[str, int] = {}
    if league != 'ncaa':
        return rank_map

    rankings_dir = Path("mt/rankings_data/ncaa_men") / str(season)
    if not rankings_dir.exists():
        return rank_map

    for rankings_file in sorted(rankings_dir.glob("rankings_*.json")):
        if "starters" in rankings_file.name:
            continue
        try:
            with open(rankings_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for entry in data.get("rankings", []):
                if entry.get("flo_ranked"):
                    wrestler_id = entry.get("wrestler_id")
                    rank = entry.get("rank")
                    if wrestler_id and rank:
                        rank_map[str(wrestler_id)] = rank
        except Exception as e:
            print(f"Warning: Error loading {rankings_file}: {e}")
            continue

    return rank_map


def get_k_factor(match_count: int) -> int:
    """Get K-factor based on wrestler's match count at the time of the match."""
    if match_count <= 5:
        return K_FACTOR_NOVICE
    elif match_count <= 15:
        return K_FACTOR_INTERMEDIATE
    else:
        return K_FACTOR_EXPERIENCED


def calculate_expected_score(elo_a: float, elo_b: float) -> float:
    """Calculate expected score for wrestler A against wrestler B."""
    return 1 / (1 + 10 ** ((elo_b - elo_a) / 400))


def update_elo(elo_a: float, elo_b: float, actual_score_a: float, match_count_a: int) -> float:
    """
    Update Elo rating for wrestler A after a match.
    
    Args:
        elo_a: Current Elo of wrestler A
        elo_b: Current Elo of opponent B
        actual_score_a: Actual score (1 for win, 0 for loss)
        match_count_a: Number of matches wrestler A has had (for K-factor)
    
    Returns:
        New Elo rating for wrestler A
    """
    expected_a = calculate_expected_score(elo_a, elo_b)
    k = get_k_factor(match_count_a)
    new_elo = elo_a + k * (actual_score_a - expected_a)
    return new_elo


def parse_match_date(date_str: str) -> Optional[datetime]:
    """Parse match date from various formats."""
    if not date_str:
        return None
    
    # Try MM/DD/YYYY format (most common in processed data)
    try:
        return datetime.strptime(date_str, "%m/%d/%Y")
    except ValueError:
        pass
    
    # Try YYYY-MM-DD format
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        pass
    
    return None


def load_all_matches(season: int, state: str = 'ky', gender: str = 'boys', league: str = 'hs') -> List[Dict]:
    """
    Load all matches from processed team data files.

    Returns:
        List of match dictionaries with wrestler IDs, dates, and results
    """
    data_dir = Path("mt/processed_data") / league_dir_key(league, gender, state) / str(season)
    
    if not data_dir.exists():
        raise FileNotFoundError(f"Processed data directory not found: {data_dir}")
    
    all_matches = []
    team_files = sorted(data_dir.glob("*.json"))
    
    print(f"Loading matches from {len(team_files)} team files...")
    
    for team_file in team_files:
        try:
            with open(team_file, 'r', encoding='utf-8') as f:
                team_data = json.load(f)
            
            team_name = team_data.get("team_name", "Unknown")
            
            for wrestler in team_data.get("roster", []):
                wrestler_id = wrestler.get("season_wrestler_id")
                if not wrestler_id:
                    continue
                
                for match in wrestler.get("matches", []):
                    # Skip matches without winner/loser info
                    if "winner_name" not in match or "loser_name" not in match:
                        continue
                    
                    # Skip byes and no-result matches
                    result = match.get("result", "")
                    if result in ("BYE", "NoResult") or "received a bye" in match.get("summary", "").lower():
                        continue
                    
                    # Extract match information
                    date_str = match.get("date", "")
                    opponent_id = match.get("opponent_id", "")
                    winner_name = match.get("winner_name", "")
                    loser_name = match.get("loser_name", "")
                    winner_team = match.get("winner_team", "")
                    loser_team = match.get("loser_team", "")
                    wrestler_name = wrestler.get("name", "")
                    
                    # Determine if this wrestler won or lost
                    # Check both name and team to avoid false matches
                    is_winner = (
                        winner_name and wrestler_name and
                        winner_name.lower() == wrestler_name.lower() and
                        (not winner_team or winner_team == team_name)
                    )
                    is_loser = (
                        loser_name and wrestler_name and
                        loser_name.lower() == wrestler_name.lower() and
                        (not loser_team or loser_team == team_name)
                    )
                    
                    if not is_winner and not is_loser:
                        # Can't determine winner/loser, skip
                        continue
                    
                    # Determine opponent info
                    if is_winner:
                        opponent_name = loser_name
                        opponent_team = loser_team
                        if not opponent_id:
                            opponent_id = match.get("loser_matsavant_id") or match.get("loser_id")
                    else:
                        opponent_name = winner_name
                        opponent_team = winner_team
                        if not opponent_id:
                            opponent_id = match.get("winner_matsavant_id") or match.get("winner_id")
                    
                    match_dict = {
                        "wrestler_id": str(wrestler_id),
                        "opponent_id": str(opponent_id) if opponent_id else None,
                        "date": date_str,
                        "is_winner": is_winner,
                        "wrestler_name": wrestler_name,
                        "opponent_name": opponent_name,
                        "opponent_team": opponent_team,
                        "team": team_name
                    }
                    all_matches.append(match_dict)
        
        except Exception as e:
            print(f"Warning: Error loading {team_file}: {e}")
            continue
    
    print(f"Loaded {len(all_matches)} total matches")
    return all_matches


def load_matrix_top_60(season: int, state: str = 'ky', gender: str = 'boys', league: str = 'hs') -> set:
    """
    Load manually-ranked wrestlers across all weight classes (top 60/36 for HS, top 33 for NCAA).

    Returns:
        Set of wrestler IDs in the manually-ranked group
    """
    data_dir = Path("mt/rankings_data") / league_dir_key(league, gender, state) / str(season)

    if not data_dir.exists():
        print(f"Warning: Rankings directory not found: {data_dir}")
        return set()

    top_ids = set()
    cutoff = get_manual_rank_cutoff(league, gender)
    weights = get_weights(league, gender)

    for weight in weights:
        rankings_file = data_dir / f"rankings_{weight}.json"
        if not rankings_file.exists():
            continue
        
        try:
            with open(rankings_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            rankings = data.get("rankings", [])
            for entry in rankings:
                rank = entry.get("rank")
                wrestler_id = entry.get("wrestler_id")
                if rank and wrestler_id and rank <= cutoff:
                    top_ids.add(str(wrestler_id))
        
        except Exception as e:
            print(f"Warning: Error loading {rankings_file}: {e}")
            continue
    
    print(f"Found {len(top_ids)} wrestlers in manually-ranked top {cutoff}")
    return top_ids


def load_wrestler_info(season: int, state: str = 'ky', gender: str = 'boys', league: str = 'hs') -> Dict[str, Dict]:
    """
    Load wrestler information (name, team) from processed data.

    Returns:
        Dict mapping wrestler_id -> {name, team}
    """
    data_dir = Path("mt/processed_data") / league_dir_key(league, gender, state) / str(season)
    
    if not data_dir.exists():
        return {}
    
    wrestler_info = {}
    team_files = sorted(data_dir.glob("*.json"))
    
    for team_file in team_files:
        try:
            with open(team_file, 'r', encoding='utf-8') as f:
                team_data = json.load(f)
            
            team_name = team_data.get("team_name", "Unknown")
            
            for wrestler in team_data.get("roster", []):
                wrestler_id = wrestler.get("season_wrestler_id")
                if wrestler_id:
                    wrestler_info[str(wrestler_id)] = {
                        "name": wrestler.get("name", "Unknown"),
                        "team": team_name
                    }
        
        except Exception:
            continue
    
    return wrestler_info


def calculate_elo_ratings(season: int, state: str = 'ky', gender: str = 'boys', league: str = 'hs') -> Dict:
    """
    Calculate Elo ratings for all wrestlers in a season.

    Returns:
        Dictionary with Elo data for each wrestler
    """
    print(f"\n{'='*80}")
    print(f"ELO RATING CALCULATION - Season {season} ({league.upper()} {gender.upper()})")
    print(f"{'='*80}\n")

    # Load data
    all_matches = load_all_matches(season, state, gender, league)
    top_60_ids = load_matrix_top_60(season, state, gender, league)
    wrestler_info = load_wrestler_info(season, state, gender, league)

    # NCAA only: seed Flo-ranked wrestlers' starting Elo from their Flo rank
    # instead of the flat INITIAL_ELO everyone gets (see flo_seed_elo above).
    # HS keeps today's behavior unchanged -- flo_rank_map is empty for league='hs'.
    flo_rank_map = load_flo_rank_map(season, league)
    flo_cutoff = get_manual_rank_cutoff(league, gender)

    def initial_elo_for(wrestler_id: str) -> float:
        flo_rank = flo_rank_map.get(wrestler_id)
        if flo_rank is not None:
            return flo_seed_elo(flo_rank, flo_cutoff)
        return INITIAL_ELO

    if flo_rank_map:
        print(f"Seeding {len(flo_rank_map)} Flo-ranked wrestlers' starting Elo from rank "
              f"({NCAA_FLO_SEED_TOP} at #1 down to {NCAA_FLO_SEED_BOTTOM} at #{flo_cutoff})")

    # Initialize wrestler tracking
    wrestlers: Dict[str, Dict] = defaultdict(lambda: {
        "elo": INITIAL_ELO,
        "match_count": 0,
        "wins": 0,
        "losses": 0,
        "matches": []  # Track matches for chronological processing
    })

    # Add wrestler info
    for wrestler_id, info in wrestler_info.items():
        if wrestler_id not in wrestlers:
            wrestlers[wrestler_id] = {
                "elo": initial_elo_for(wrestler_id),
                "match_count": 0,
                "wins": 0,
                "losses": 0,
                "matches": []
            }
        wrestlers[wrestler_id]["name"] = info["name"]
        wrestlers[wrestler_id]["team"] = info["team"]
    
    # Collect all matches with dates
    match_list = []
    for match in all_matches:
        date_obj = parse_match_date(match["date"])
        if date_obj:
            match_list.append((date_obj, match))
    
    # Sort matches chronologically
    match_list.sort(key=lambda x: x[0])
    
    print(f"Processing {len(match_list)} matches chronologically...")
    
    # Process matches in chronological order
    for date_obj, match in match_list:
        wrestler_id = match["wrestler_id"]
        opponent_id = match.get("opponent_id")
        is_winner = match["is_winner"]
        
        # Initialize opponent if needed
        if opponent_id and opponent_id not in wrestlers:
            wrestlers[opponent_id] = {
                "elo": initial_elo_for(opponent_id),
                "match_count": 0,
                "wins": 0,
                "losses": 0,
                "matches": []
            }
            # Try to get opponent info from wrestler_info or match data
            if opponent_id in wrestler_info:
                wrestlers[opponent_id]["name"] = wrestler_info[opponent_id]["name"]
                wrestlers[opponent_id]["team"] = wrestler_info[opponent_id]["team"]
            else:
                # Use info from match
                wrestlers[opponent_id]["name"] = match.get("opponent_name", "Unknown")
                wrestlers[opponent_id]["team"] = match.get("opponent_team", "Unknown")
        
        # Get current Elo and match count
        wrestler_elo = wrestlers[wrestler_id]["elo"]
        wrestler_match_count = wrestlers[wrestler_id]["match_count"]
        
        if opponent_id:
            opponent_elo = wrestlers[opponent_id]["elo"]
            opponent_match_count = wrestlers[opponent_id]["match_count"]
        else:
            # Unknown opponent - use average Elo (1500)
            opponent_elo = INITIAL_ELO
            opponent_match_count = 0
        
        # Calculate actual score
        actual_score = 1.0 if is_winner else 0.0
        
        # Update Elo for wrestler
        new_elo = update_elo(wrestler_elo, opponent_elo, actual_score, wrestler_match_count)
        wrestlers[wrestler_id]["elo"] = new_elo
        wrestlers[wrestler_id]["match_count"] += 1
        
        if is_winner:
            wrestlers[wrestler_id]["wins"] += 1
        else:
            wrestlers[wrestler_id]["losses"] += 1
        
        # Update opponent Elo if opponent exists
        if opponent_id:
            opponent_actual_score = 1.0 - actual_score
            new_opponent_elo = update_elo(opponent_elo, wrestler_elo, opponent_actual_score, opponent_match_count)
            wrestlers[opponent_id]["elo"] = new_opponent_elo
            wrestlers[opponent_id]["match_count"] += 1
            
            if opponent_actual_score == 1.0:
                wrestlers[opponent_id]["wins"] += 1
            else:
                wrestlers[opponent_id]["losses"] += 1
        
        # Track match date
        wrestlers[wrestler_id]["matches"].append(date_obj)
        if opponent_id:
            wrestlers[opponent_id]["matches"].append(date_obj)
    
    print(f"Processed matches for {len(wrestlers)} wrestlers")
    
    # Calculate last match dates and inactive flags
    today = datetime.now().date()
    cutoff_date = today - timedelta(days=35)
    
    for wrestler_id, data in wrestlers.items():
        matches = data.get("matches", [])
        if matches:
            last_match = max(matches)
            data["last_match_date"] = last_match.strftime("%Y-%m-%d")
            last_match_date_obj = last_match.date()
            
            # Check inactive flag: no matches in last 35 days AND not in top 60
            is_inactive = (
                last_match_date_obj < cutoff_date and
                wrestler_id not in top_60_ids
            )
            data["inactive_flag"] = is_inactive
        else:
            data["last_match_date"] = None
            data["inactive_flag"] = False
    
    return wrestlers


def load_matrix_ranks(season: int, state: str = 'ky', gender: str = 'boys', league: str = 'hs') -> Dict[str, int]:
    """
    Load matrix ranks for all wrestlers across all weight classes.

    Returns:
        Dict mapping wrestler_id -> rank (None if unranked)
    """
    data_dir = Path("mt/rankings_data") / league_dir_key(league, gender, state) / str(season)

    if not data_dir.exists():
        return {}

    wrestler_to_rank = {}
    weights = get_weights(league, gender)

    for weight in weights:
        rankings_file = data_dir / f"rankings_{weight}.json"
        if not rankings_file.exists():
            continue
        
        try:
            with open(rankings_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            rankings = data.get("rankings", [])
            for entry in rankings:
                rank = entry.get("rank")
                wrestler_id = entry.get("wrestler_id")
                if rank is not None and wrestler_id:
                    # Keep the best (lowest) rank if wrestler appears in multiple weights
                    existing_rank = wrestler_to_rank.get(str(wrestler_id))
                    if existing_rank is None or rank < existing_rank:
                        wrestler_to_rank[str(wrestler_id)] = rank
        except Exception:
            continue
    
    return wrestler_to_rank


def load_matrix_ranks_by_weight(season: int, state: str = 'ky', gender: str = 'boys', league: str = 'hs') -> Dict[int, Dict[str, int]]:
    """
    Load matrix ranks organized by weight class.

    Returns:
        Dict mapping weight -> {wrestler_id -> rank}
    """
    data_dir = Path("mt/rankings_data") / league_dir_key(league, gender, state) / str(season)

    if not data_dir.exists():
        return {}

    ranks_by_weight = {}
    weights = get_weights(league, gender)

    for weight in weights:
        rankings_file = data_dir / f"rankings_{weight}.json"
        if not rankings_file.exists():
            ranks_by_weight[weight] = {}
            continue
        
        try:
            with open(rankings_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            rankings = data.get("rankings", [])
            weight_ranks = {}
            for entry in rankings:
                rank = entry.get("rank")
                wrestler_id = entry.get("wrestler_id")
                if rank is not None and wrestler_id:
                    weight_ranks[str(wrestler_id)] = rank
            ranks_by_weight[weight] = weight_ranks
        except Exception:
            ranks_by_weight[weight] = {}
    
    return ranks_by_weight


def calculate_hybrid_ranks_by_weight(
    wrestlers: Dict,
    elo_by_id: Dict[str, Dict],
    ranks_by_weight: Dict[int, Dict[str, int]],
    gender: str = 'boys',
    league: str = 'hs',
) -> Dict[int, Dict[str, int]]:
    """
    Calculate hybrid ranks for each weight class.

    Returns:
        Dict mapping weight -> {wrestler_id -> hybrid_rank}
    """
    tier_a_cutoff = get_manual_rank_cutoff(league, gender)
    hybrid_ranks_by_weight = {}
    weights = get_weights(league, gender)
    
    for weight in weights:
        weight_ranks = ranks_by_weight.get(weight, {})
        hybrid_ranks = {}
        
        # Get all wrestlers in this weight class from rankings
        weight_wrestlers = []
        for wrestler_id, matrix_rank in weight_ranks.items():
            elo_entry = elo_by_id.get(wrestler_id, {})
            wins = elo_entry.get("wins", 0)
            losses = elo_entry.get("losses", 0)
            match_count = elo_entry.get("match_count", 0)
            is_inactive = elo_entry.get("inactive_flag", False)
            elo_score = elo_entry.get("elo_score", 0)
            
            weight_wrestlers.append({
                "wrestler_id": wrestler_id,
                "matrix_rank": matrix_rank,
                "elo_score": elo_score,
                "wins": wins,
                "losses": losses,
                "match_count": match_count,
                "is_inactive": is_inactive
            })
        
        # Separate into Tier A, B, C, and D
        tier_a = []  # Matrix rank <= cutoff
        tier_b = []  # Matrix rank > cutoff, wins >= 1
        tier_c = []  # Matrix rank > cutoff, wins == 0 AND losses > 0
        tier_d = []  # matches == 0 (0-0 record)
        
        for w in weight_wrestlers:
            if w["matrix_rank"] <= tier_a_cutoff:
                # Tier A: use matrix rank
                hybrid_ranks[w["wrestler_id"]] = w["matrix_rank"]
                tier_a.append(w)
            else:
                # Tier B, C, or D: will be ranked by Elo
                if w["match_count"] == 0:
                    # Tier D: No matches (0-0 record)
                    tier_d.append(w)
                elif w["wins"] == 0:
                    # Tier C: Winless but has losses (0-X record)
                    tier_c.append(w)
                else:
                    # Tier B: Has at least one win
                    tier_b.append(w)
        
        # Sort each tier by Elo descending
        tier_b.sort(key=lambda x: x["elo_score"], reverse=True)
        tier_c.sort(key=lambda x: x["elo_score"], reverse=True)
        tier_d.sort(key=lambda x: x["elo_score"], reverse=True)
        
        # Assign hybrid ranks sequentially
        # Tier A already has ranks assigned (matrix ranks 1-60/36)
        next_rank = tier_a_cutoff + 1
        
        # Tier B: Has wins, ordered by Elo
        for w in tier_b:
            hybrid_ranks[w["wrestler_id"]] = next_rank
            next_rank += 1
        
        # Tier C: Winless but has losses, ordered by Elo (always below Tier B)
        for w in tier_c:
            hybrid_ranks[w["wrestler_id"]] = next_rank
            next_rank += 1
        
        # Tier D: No matches (0-0), always at absolute bottom
        for w in tier_d:
            hybrid_ranks[w["wrestler_id"]] = next_rank
            next_rank += 1
        
        hybrid_ranks_by_weight[weight] = hybrid_ranks
    
    return hybrid_ranks_by_weight


def build_output_table(wrestlers: Dict, top_60_ids: set, season: int, state: str = 'ky', gender: str = 'boys', league: str = 'hs') -> List[Dict]:
    """
    Build output table with all required fields, including hybrid_rank.

    Returns:
        List of wrestler dictionaries sorted by Elo score
    """
    # Load matrix ranks (global and by weight)
    wrestler_to_rank = load_matrix_ranks(season, state, gender, league)
    ranks_by_weight = load_matrix_ranks_by_weight(season, state, gender, league)

    # Build elo_by_id for hybrid rank calculation
    elo_by_id = {}
    for wrestler_id, data in wrestlers.items():
        wins = data.get("wins", 0)
        losses = data.get("losses", 0)
        match_count = data.get("match_count", 0)
        record_string = f"{wins}-{losses}" if match_count > 0 else "0-0"

        elo_by_id[wrestler_id] = {
            "elo_score": round(data.get("elo", INITIAL_ELO), 2),
            "record_string": record_string,
            "inactive_flag": data.get("inactive_flag", False),
            "matrix_rank": wrestler_to_rank.get(wrestler_id),
            "wins": wins,
            "losses": losses,
            "match_count": match_count
        }

    # Calculate hybrid ranks by weight
    hybrid_ranks_by_weight = calculate_hybrid_ranks_by_weight(
        wrestlers, elo_by_id, ranks_by_weight, gender, league
    )
    
    # Build output with hybrid_rank (use best hybrid_rank across all weights)
    output = []
    
    for wrestler_id, data in wrestlers.items():
        wins = data.get("wins", 0)
        losses = data.get("losses", 0)
        match_count = data.get("match_count", 0)
        
        # Get matrix rank
        matrix_rank = wrestler_to_rank.get(wrestler_id)
        
        record_string = f"{wins}-{losses}" if match_count > 0 else "0-0"
        
        # Get hybrid_rank by weight (store all weights where wrestler appears)
        hybrid_rank_by_weight = {}
        for weight, hybrid_ranks in hybrid_ranks_by_weight.items():
            if wrestler_id in hybrid_ranks:
                hybrid_rank_by_weight[weight] = hybrid_ranks[wrestler_id]
        
        # Also store best (lowest) hybrid_rank for convenience
        best_hybrid_rank = min(hybrid_rank_by_weight.values()) if hybrid_rank_by_weight else None
        
        entry = {
            "wrestler_id": wrestler_id,
            "name": data.get("name", "Unknown"),
            "team": data.get("team", "Unknown"),
            "matrix_rank": matrix_rank,
            "elo_score": round(data.get("elo", INITIAL_ELO), 2),
            "elo_rank": None,  # Will be assigned after sorting
            "hybrid_rank": best_hybrid_rank,  # Best hybrid rank across all weights
            "hybrid_rank_by_weight": hybrid_rank_by_weight,  # Per-weight hybrid ranks
            "wins": wins,
            "losses": losses,
            "record_string": record_string,
            "match_count": match_count,
            "last_match_date": data.get("last_match_date"),
            "has_matches": match_count > 0,
            "inactive_flag": data.get("inactive_flag", False)
        }
        output.append(entry)
    
    # Sort by Elo score descending
    output.sort(key=lambda x: x["elo_score"], reverse=True)
    
    # Assign Elo ranks
    for rank, entry in enumerate(output, 1):
        entry["elo_rank"] = rank
    
    return output


def write_rankings_from_elo(output_table: List[Dict], season: int, state: str, gender: str, league: str) -> None:
    """Write/overwrite rankings_<weight>.json per weight class from the just-
    computed Elo ratings -- this is the "hybrid Flo + modified Elo" rank
    compute_all_mat_values.py and the profile pages need. NCAA only (HS still
    uses the manually-curated matrix).

    This is a re-rank in place, not a reset: flo_ranked is preserved from
    whatever's already on disk (set earlier this same pipeline run by
    apply_flo_rankings.py, which runs before this step and either found a
    prior rankings_<weight>.json or bootstrapped one) -- Elo itself already
    reflects Flo's opinion for those wrestlers via flo_seed_elo()'s starting-
    rating seed above, so no separate overlay is needed here, only carrying
    the tag through so next run's Flo-seeding can still find it.
    """
    if league != 'ncaa':
        return

    data_dir = Path("mt/rankings_data") / league_dir_key(league, gender, state) / str(season)
    weights = get_weights(league, gender)

    # wrestler_id -> weight_class. Elo itself is computed weight-agnostic
    # (wins/losses/matches tracked globally, not per weight), so this is the
    # only place that knows which weight class someone is actually at.
    weight_by_id: Dict[str, int] = {}
    for weight in weights:
        wc_path = data_dir / f"weight_class_{weight}.json"
        if not wc_path.exists():
            continue
        wc_data = json.loads(wc_path.read_text())
        for wid in wc_data.get("wrestlers", {}):
            weight_by_id[wid] = weight

    elo_by_id = {str(e["wrestler_id"]): e for e in output_table}

    for weight in weights:
        existing_path = data_dir / f"rankings_{weight}.json"
        existing_by_id = {}
        if existing_path.exists():
            existing_data = json.loads(existing_path.read_text())
            existing_by_id = {e["wrestler_id"]: e for e in existing_data.get("rankings", [])}

        entries = []
        for wid, w in weight_by_id.items():
            if w != weight:
                continue
            elo_entry = elo_by_id.get(wid)
            if not elo_entry:
                continue
            existing = existing_by_id.get(wid, {})
            entries.append({
                "wrestler_id": wid,
                "name": elo_entry["name"],
                "team": elo_entry["team"],
                "record": elo_entry["record_string"],
                "elo_score": elo_entry["elo_score"],
                "flo_ranked": existing.get("flo_ranked", False),
            })

        # Sort by Elo score descending -- Flo-ranked wrestlers already got a
        # seeded starting Elo above, so their real match results just refine
        # a rating that already reflects Flo's opinion.
        entries.sort(key=lambda e: -e["elo_score"])

        # is_starter: best-ranked (i.e. first, since entries are already Elo-
        # sorted) wrestler per team -- same convention as the matrix UI's own
        # getCurrentRankings() (generate_matrix.py), recomputed here since
        # there's no manual matrix edit to read it from.
        starter_ids = set()
        seen_teams = set()
        for e in entries:
            if e["team"] not in seen_teams:
                seen_teams.add(e["team"])
                starter_ids.add(e["wrestler_id"])

        rankings = [
            {
                "rank": i + 1,
                "wrestler_id": e["wrestler_id"],
                "name": e["name"],
                "team": e["team"],
                "record": e["record"],
                "is_starter": e["wrestler_id"] in starter_ids,
                "flo_ranked": e["flo_ranked"],
            }
            for i, e in enumerate(entries)
        ]

        existing_path.write_text(json.dumps(
            {"weight_class": weight, "season": season, "rankings": rankings},
            indent=2, ensure_ascii=False,
        ))

    print(f"\n✓ Wrote hybrid rankings_<weight>.json for {len(weights)} weight classes to {data_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="Calculate Elo ratings for wrestling (review only)"
    )
    parser.add_argument(
        "-season",
        type=int,
        required=True,
        help="Season year (e.g., 2026)"
    )
    parser.add_argument(
        "--league",
        choices=["hs", "ncaa"],
        default="hs",
        help="League: 'hs' or 'ncaa' (default: hs)"
    )
    parser.add_argument(
        "--gender",
        choices=["boys", "girls", "men", "women"],
        default="boys",
        help="Gender: boys/girls (HS) or men/women (NCAA)"
    )
    parser.add_argument(
        "--state",
        type=str,
        default="ky",
        help="State code for HS (default: ky)"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output JSON file path (default: mt/elo_ratings/{league_key}/{season}/elo_ratings.json)"
    )

    args = parser.parse_args()

    if args.season < 2012 or args.season > 2030:
        print(f"Error: Invalid season {args.season}")
        return

    if args.league == 'ncaa' and args.gender not in ('men', 'women'):
        print("Error: --gender must be 'men' or 'women' for --league ncaa")
        return
    if args.league == 'hs' and args.gender not in ('boys', 'girls'):
        print("Error: --gender must be 'boys' or 'girls' for --league hs")
        return

    # Calculate Elo ratings
    wrestlers = calculate_elo_ratings(args.season, args.state, args.gender, args.league)

    # Load manually-ranked group for inactive flag calculation
    top_60_ids = load_matrix_top_60(args.season, args.state, args.gender, args.league)

    # Build output table
    output_table = build_output_table(wrestlers, top_60_ids, args.season, args.state, args.gender, args.league)

    # Set output path
    if args.output:
        output_path = Path(args.output)
    else:
        key = league_dir_key(args.league, args.gender, args.state)
        output_path = Path(f"mt/elo_ratings/{key}/{args.season}/elo_ratings.json")
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write output
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_table, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Elo ratings written to: {output_path}")

    # NCAA only: also write the per-weight hybrid rank compute_all_mat_values.py
    # and the profile pages need -- see write_rankings_from_elo()'s docstring.
    write_rankings_from_elo(output_table, args.season, args.state, args.gender, args.league)

    # Print summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"Total wrestlers: {len(output_table)}")
    
    wrestlers_with_matches = sum(1 for e in output_table if e["has_matches"])
    print(f"Wrestlers with matches: {wrestlers_with_matches}")
    
    inactive_count = sum(1 for e in output_table if e["inactive_flag"])
    print(f"Inactive wrestlers: {inactive_count}")
    
    print(f"\nTop 10 by Elo:")
    for i, entry in enumerate(output_table[:10], 1):
        print(f"  {i:2d}. {entry['name']:<30} {entry['team']:<25} Elo: {entry['elo_score']:7.2f} "
              f"({entry['wins']}-{entry['losses']}) Rank: {entry.get('matrix_rank', 'N/A')}")
    
    print(f"\nBottom 10 by Elo (with matches):")
    bottom_with_matches = [e for e in output_table if e["has_matches"]]
    for i, entry in enumerate(bottom_with_matches[-10:], 1):
        rank_idx = len(bottom_with_matches) - 10 + i
        print(f"  {rank_idx:2d}. {entry['name']:<30} {entry['team']:<25} Elo: {entry['elo_score']:7.2f} "
              f"({entry['wins']}-{entry['losses']}) Rank: {entry.get('matrix_rank', 'N/A')}")


if __name__ == "__main__":
    main()

