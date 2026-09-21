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

from duplicate_events import match_ident, processed_drop_idents  # scripts/rankings/ (same dir as this script)


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


# NCAA only: seed a wrestler's starting Elo from their OWN prior-season
# ending Elo whenever real prior data exists -- this takes priority over
# Flo-seeding, since a real season of match results is richer signal than
# an ordinal Flo rank. Flo-seeding is the fallback for wrestlers with no
# usable prior season at all (true freshmen, or transfers from a level we
# don't track).
#
# Weight decreases as the gap since that last real season grows -- a
# 1-year gap (the normal returning-starter case) keeps the most of the
# earned rating; a 2+ year gap (redshirt/layoff, e.g. a wrestler who
# competed two seasons ago but sat out last year) trusts it less.
#
# Backtested (scripts/rankings/backtest_prior_shrink.py, not checked in --
# rebuilds a fully self-consistent Elo chain 2012-2026 per candidate config
# and scores log-loss/Brier/accuracy on each seeded wrestler's first 3-5
# matches of the season, i.e. exactly the window the seed is meant to help)
# against every season 2016-2026: counterintuitively, WEIGHTS ABOVE 1.0 win
# outright, consistently across all three gap tiers and both early-match
# windows tested, with log-loss bottoming out in a flat 1.15-1.30 band and
# degrading sharply past ~1.4 (2.0 was tested and is clearly too far --
# log-loss roughly 40% worse than the tier-1 optimum). A naive <1.0 shrink
# (the original guess before backtesting) underperforms even a flat
# INITIAL_ELO baseline in relative terms -- straight carry-over, and
# slightly beyond, calibrates better than discounting toward the mean.
# Reasoning: the season's own K-factor is highest (40) for a wrestler's
# first 5 matches, making their fresh in-season Elo noisier than their own
# already-converged prior-season rating, so trusting last year at ~1.2x
# outperforms treating it as a decaying prior.
PRIOR_SEASON_SHRINK = {1: 1.20, 2: 1.05}
PRIOR_SEASON_SHRINK_DEFAULT = 0.80  # 3+ seasons back
PRIOR_SEASON_LOOKBACK_LIMIT = 5     # don't search back further than this

CAREERS_DIR = Path("data/careers/ncaa_men")

_career_seasons_cache: Optional[Dict[str, Dict[str, str]]] = None


def build_wid_to_career_seasons() -> Dict[str, Dict[str, str]]:
    """wrestler_id (any season) -> that career's full {season_str: wrestler_id}
    dict. Same pattern as build_p4p_rankings.py's build_wid_to_career_index()."""
    global _career_seasons_cache
    if _career_seasons_cache is not None:
        return _career_seasons_cache
    index: Dict[str, Dict[str, str]] = {}
    if CAREERS_DIR.exists():
        for f in CAREERS_DIR.glob("career_*.json"):
            try:
                career = json.loads(f.read_text())
            except Exception:
                continue
            seasons = career.get("seasons", {})
            for wid in seasons.values():
                index[str(wid)] = seasons
    _career_seasons_cache = index
    return index


_elo_ratings_by_season_cache: Dict[int, Dict[str, Dict]] = {}


def load_elo_ratings_for_season(season: int) -> Dict[str, Dict]:
    """wrestler_id -> that season's own elo_ratings.json entry, for a PRIOR
    (already-completed) season. Cached since many wrestlers share lookups
    into the same prior-season file."""
    if season in _elo_ratings_by_season_cache:
        return _elo_ratings_by_season_cache[season]
    path = Path(f"mt/elo_ratings/ncaa_men/{season}/elo_ratings.json")
    result: Dict[str, Dict] = {}
    if path.exists():
        try:
            data = json.loads(path.read_text())
            result = {str(e["wrestler_id"]): e for e in data}
        except Exception:
            result = {}
    _elo_ratings_by_season_cache[season] = result
    return result


def find_last_real_season_elo(
    wrestler_id: str, season: int, career_index: Dict[str, Dict[str, str]]
) -> Optional[Tuple[float, int]]:
    """Walk this wrestler's own career backward from `season - 1` and return
    (elo_score, season_gap) for the most recent season where they actually
    competed (has_matches=True) -- not just the immediately preceding
    season, so a multi-year layoff (redshirt, injury) still finds their
    real last season instead of treating them as a total unknown."""
    seasons_map = career_index.get(str(wrestler_id))
    if not seasons_map:
        return None
    for gap in range(1, PRIOR_SEASON_LOOKBACK_LIMIT + 1):
        prior_season = season - gap
        prior_wid = seasons_map.get(str(prior_season))
        if not prior_wid:
            continue
        prior_ratings = load_elo_ratings_for_season(prior_season)
        entry = prior_ratings.get(str(prior_wid))
        if entry and entry.get("has_matches"):
            return (entry["elo_score"], gap)
    return None


def seed_from_prior_elo(prior_elo: float, gap: int) -> float:
    w = PRIOR_SEASON_SHRINK.get(gap, PRIOR_SEASON_SHRINK_DEFAULT)
    return INITIAL_ELO + w * (prior_elo - INITIAL_ELO)


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
                    if league == 'hs':
                        # Bout identity shared with load_data.py / duplicate_events.py, used below to drop the
                        # approved duplicate events (this loader reads raw processed_data, not weight_class files).
                        match_dict["_bout"] = match_ident(match, wrestler_id)
                    all_matches.append(match_dict)
        
        except Exception as e:
            print(f"Warning: Error loading {team_file}: {e}")
            continue
    
    if league == 'hs':
        # Remove the extra copy of every bout in the human-APPROVED duplicated events (CLAUDE.md Known Gotcha 9),
        # exactly as load_data.py does for the weight_class files -- otherwise ELO would still count them.
        drop = processed_drop_idents(gender, season, state=state)
        if drop:
            before = len(all_matches)
            all_matches = [m for m in all_matches if m.get("_bout") not in drop]
            print(f"Dropped {before - len(all_matches)} match rows ({len(drop)} bouts) from approved duplicate events")
        for m in all_matches:
            m.pop("_bout", None)

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


def load_ncaa_matches_and_info(season: int) -> Tuple[List[Dict], Dict[str, Dict]]:
    """NCAA-only match + wrestler-info source, read from
    mt/rankings_data/ncaa_men/{season}/relationships_<weight>.json instead of
    the raw mt/processed_data/ team files.

    Why: the raw team files record every real match from BOTH sides
    independently (Penn State's file has "Mesenbrink beat Eck," Oklahoma's
    file separately has "Eck lost to Mesenbrink" -- same match). Naively
    concatenating all team files and crediting both participants for every
    entry double-counts ~69% of matches (confirmed: 18,056 of 26,315 raw
    entries were the same match from both sides), which distorts Elo
    non-linearly since the second application uses the already-updated
    rating from the first.

    build_relationships.py already produces a clean, deduped, one-record-
    per-real-match dataset (`direct_relationships`), scoped to matches
    between two wrestlers who are both in that weight's tracked D1
    population -- confirmed 8,291 of 8,292 "missing" matches vs. a naive
    raw-data dedup are specifically matches against a non-D1 opponent
    (D2/NAIA/etc.), which is exactly the scope Elo should exclude here (a
    deliberate decision, not an oversight -- these opponents aren't
    calibrated against the same population and often appear only once or
    twice with no other connections). Reusing this file means no new
    dedup logic is needed and Elo's population exactly matches what the
    rest of the ranking pipeline already considers "the field."
    """
    data_dir = Path("mt/rankings_data/ncaa_men") / str(season)
    all_matches: List[Dict] = []
    wrestler_info: Dict[str, Dict] = {}
    seen_matches: set = set()  # (date, frozenset({w1, w2})) -- guards the rare
                                # case of a pair appearing in >1 weight file

    for rel_path in sorted(data_dir.glob("relationships_*.json")):
        try:
            data = json.loads(rel_path.read_text())
        except Exception as e:
            print(f"Warning: Error loading {rel_path}: {e}")
            continue

        for wid, info in data.get("wrestlers", {}).items():
            wrestler_info.setdefault(str(wid), {
                "name": info.get("name", "Unknown"),
                "team": info.get("team", "Unknown"),
            })

        for pair_key, rel in data.get("direct_relationships", {}).items():
            w1 = str(rel.get("wrestler1_id"))
            w2 = str(rel.get("wrestler2_id"))
            for m in rel.get("matches", []):
                dedup_key = (m.get("date"), frozenset({w1, w2}))
                if dedup_key in seen_matches:
                    continue
                seen_matches.add(dedup_key)

                winner_id = str(m.get("winner_id"))
                is_winner = winner_id == w1
                w1_info = wrestler_info.get(w1, {})
                w2_info = wrestler_info.get(w2, {})
                all_matches.append({
                    "wrestler_id": w1,
                    "opponent_id": w2,
                    "date": m.get("date"),
                    "is_winner": is_winner,
                    "wrestler_name": w1_info.get("name", "Unknown"),
                    "opponent_name": w2_info.get("name", "Unknown"),
                    "opponent_team": w2_info.get("team", "Unknown"),
                    "team": w1_info.get("team", "Unknown"),
                })

    print(f"Loaded {len(all_matches)} deduped D1 matches from relationships_<weight>.json "
          f"({len(wrestler_info)} tracked wrestlers)")
    return all_matches, wrestler_info


def calculate_elo_ratings(season: int, state: str = 'ky', gender: str = 'boys', league: str = 'hs') -> Dict:
    """
    Calculate Elo ratings for all wrestlers in a season.

    Returns:
        Dictionary with Elo data for each wrestler
    """
    print(f"\n{'='*80}")
    print(f"ELO RATING CALCULATION - Season {season} ({league.upper()} {gender.upper()})")
    print(f"{'='*80}\n")

    # Load data. NCAA uses the deduped, D1-scoped relationships_<weight>.json
    # dataset instead of raw team files -- see load_ncaa_matches_and_info()'s
    # docstring for why (raw team files double-count ~69% of matches). HS
    # keeps today's behavior unchanged; it doesn't have this relationships
    # dataset built out the same way.
    if league == 'ncaa':
        all_matches, wrestler_info = load_ncaa_matches_and_info(season)
    else:
        all_matches = load_all_matches(season, state, gender, league)
        wrestler_info = load_wrestler_info(season, state, gender, league)
    top_60_ids = load_matrix_top_60(season, state, gender, league)

    # NCAA only: seed Flo-ranked wrestlers' starting Elo from their Flo rank
    # instead of the flat INITIAL_ELO everyone gets (see flo_seed_elo above).
    # HS keeps today's behavior unchanged -- flo_rank_map is empty for league='hs'.
    flo_rank_map = load_flo_rank_map(season, league)
    flo_cutoff = get_manual_rank_cutoff(league, gender)
    career_index = build_wid_to_career_seasons() if league == 'ncaa' else {}

    prior_seed_count = 0

    def initial_elo_for(wrestler_id: str) -> float:
        nonlocal prior_seed_count
        if league == 'ncaa':
            prior = find_last_real_season_elo(wrestler_id, season, career_index)
            if prior is not None:
                prior_elo, gap = prior
                prior_seed_count += 1
                return seed_from_prior_elo(prior_elo, gap)
        flo_rank = flo_rank_map.get(wrestler_id)
        if flo_rank is not None:
            return flo_seed_elo(flo_rank, flo_cutoff)
        return INITIAL_ELO

    if flo_rank_map:
        print(f"Seeding {len(flo_rank_map)} Flo-ranked wrestlers' starting Elo from rank "
              f"({NCAA_FLO_SEED_TOP} at #1 down to {NCAA_FLO_SEED_BOTTOM} at #{flo_cutoff}) "
              f"-- overridden below for anyone with real prior-season data")

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

    if prior_seed_count:
        print(f"Seeded {prior_seed_count} wrestlers' starting Elo from their own prior-season "
              f"rating (weighted per PRIOR_SEASON_SHRINK), taking priority over Flo-seeding")

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


def load_flo_ranked_by_weight(season: int) -> Dict[int, Dict[str, bool]]:
    """NCAA only: {weight -> {wrestler_id -> flo_ranked}} straight from
    rankings_<weight>.json. `flo_ranked=True` means this specific entry's
    `rank` field was set by apply_flo_rankings.py (real FloWrestling data,
    OR the seed+placement substitute for a season with no real Flo data --
    both are legitimate per docs/matsavant.md's "NCAA Ranking Methodology"
    section; what's NOT legitimate is a raw matrix-computed rank, which is
    exactly what flo_ranked=False marks here). This is the ONLY thing that
    should ever decide whether a wrestler's rank is trusted for NCAA --
    never a raw `rank <= cutoff` check, which would also catch untagged
    matrix-only entries that happen to fall inside 1..33 by coincidence."""
    out: Dict[int, Dict[str, bool]] = {}
    rankings_dir = Path("mt/rankings_data/ncaa_men") / str(season)
    for weight in get_weights('ncaa', 'men'):
        path = rankings_dir / f"rankings_{weight}.json"
        weight_map: Dict[str, bool] = {}
        if path.exists():
            try:
                data = json.loads(path.read_text())
                for entry in data.get("rankings", []):
                    wid = entry.get("wrestler_id")
                    if wid:
                        weight_map[str(wid)] = bool(entry.get("flo_ranked"))
            except Exception:
                pass
        out[weight] = weight_map
    return out


def calculate_ncaa_hybrid_ranks_by_weight(
    ranks_by_weight: Dict[int, Dict[str, int]],
    flo_ranked_by_weight: Dict[int, Dict[str, bool]],
    elo_by_id: Dict[str, Dict],
) -> Dict[int, Dict[str, int]]:
    """NCAA-specific hybrid rank: trust ONLY entries tagged flo_ranked=True
    (real Flo data, or the seed+placement substitute for a no-Flo season --
    see load_flo_ranked_by_weight) for the top tier, using their existing
    `rank` field as-is (apply_flo_rankings.py already numbers these entries
    1..N sequentially before anything else, so no renumbering is needed).
    Everyone else -- untagged, or not in rankings_<weight>.json at all --
    is ranked purely by Elo, filling N+1, N+2, ... This deliberately does
    NOT use the generic calculate_hybrid_ranks_by_weight()'s `matrix_rank
    <= cutoff` check, which would also trust untagged matrix-only entries
    that happen to fall inside 1..33 by coincidence -- exactly the banned
    "matrix rank used as a user-facing source" bug documented in
    docs/matsavant.md."""
    hybrid_ranks_by_weight: Dict[int, Dict[str, int]] = {}
    for weight in get_weights('ncaa', 'men'):
        weight_ranks = ranks_by_weight.get(weight, {})
        flo_flags = flo_ranked_by_weight.get(weight, {})
        hybrid_ranks: Dict[str, int] = {}

        trusted = []   # (rank, wrestler_id) -- flo_ranked=True, keep their existing rank
        untrusted = []  # wrestler_id -- everything else, to be Elo-sorted
        for wrestler_id, rank in weight_ranks.items():
            if flo_flags.get(wrestler_id):
                trusted.append((rank, wrestler_id))
                hybrid_ranks[wrestler_id] = rank
            else:
                untrusted.append(wrestler_id)

        next_rank = (max((r for r, _ in trusted), default=0)) + 1
        untrusted.sort(key=lambda wid: elo_by_id.get(wid, {}).get("elo_score", 0), reverse=True)
        for wrestler_id in untrusted:
            hybrid_ranks[wrestler_id] = next_rank
            next_rank += 1

        hybrid_ranks_by_weight[weight] = hybrid_ranks
    return hybrid_ranks_by_weight


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

    # Calculate hybrid ranks by weight. NCAA uses its own trust-tagged
    # (flo_ranked) version -- never the generic matrix_rank<=cutoff check,
    # which would wrongly trust untagged matrix-only entries. HS is
    # unaffected (unchanged path).
    if league == 'ncaa':
        flo_ranked_by_weight = load_flo_ranked_by_weight(season)
        hybrid_ranks_by_weight = calculate_ncaa_hybrid_ranks_by_weight(
            ranks_by_weight, flo_ranked_by_weight, elo_by_id
        )
    else:
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


def write_rankings_from_elo(
    output_table: List[Dict],
    season: int,
    state: str,
    gender: str,
    league: str,
    output_dir: Optional[Path] = None,
) -> None:
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

    Wrestlers with zero matches this season are pulled out of the numbered
    ranking entirely (rank: null, is_starter always False) instead of being
    slotted in by a default/seeded Elo they've never actually earned --
    this is the direct fix for a real bug (e.g. Bellarmine's 197s), where a
    0-match wrestler's seeded Elo out-ranked a teammate's real, evidenced
    season. `match_count`/`last_match_date` are also carried through so
    build_team_profiles.py's starter selection can apply its own games-
    played / recent-activity checks without re-fetching full profiles.

    `output_dir`: write here instead of the real rankings dir (existing
    flo_ranked tags are still READ from the real dir either way) -- used
    for dry-run validation before this touches production data.
    """
    if league != 'ncaa':
        return

    data_dir = Path("mt/rankings_data") / league_dir_key(league, gender, state) / str(season)
    out_dir = output_dir or data_dir
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
                "match_count": elo_entry.get("match_count", 0),
                "last_match_date": elo_entry.get("last_match_date"),
            })

        has_matches = [e for e in entries if e["match_count"] > 0]
        no_matches = [e for e in entries if e["match_count"] == 0]

        # Sort by Elo score descending -- Flo-ranked wrestlers already got a
        # seeded starting Elo above, so their real match results just refine
        # a rating that already reflects Flo's opinion.
        has_matches.sort(key=lambda e: -e["elo_score"])

        # is_starter: best-ranked (i.e. first, since entries are already Elo-
        # sorted) wrestler per team, among those with real matches only --
        # same convention as the matrix UI's own getCurrentRankings()
        # (generate_matrix.py), recomputed here since there's no manual
        # matrix edit to read it from. A 0-match wrestler can never win
        # this by construction (they're not in `has_matches`).
        starter_ids = set()
        seen_teams = set()
        for e in has_matches:
            if e["team"] not in seen_teams:
                seen_teams.add(e["team"])
                starter_ids.add(e["wrestler_id"])

        def _entry(e, rank):
            return {
                "rank": rank,
                "wrestler_id": e["wrestler_id"],
                "name": e["name"],
                "team": e["team"],
                "record": e["record"],
                "is_starter": rank is not None and e["wrestler_id"] in starter_ids,
                "flo_ranked": e["flo_ranked"],
                "match_count": e["match_count"],
                "last_match_date": e["last_match_date"],
            }

        rankings = [_entry(e, i + 1) for i, e in enumerate(has_matches)]
        rankings += [_entry(e, None) for e in no_matches]  # UNR -- rank: null

        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"rankings_{weight}.json").write_text(json.dumps(
            {"weight_class": weight, "season": season, "rankings": rankings},
            indent=2, ensure_ascii=False,
        ))

    print(f"\n✓ Wrote hybrid rankings_<weight>.json for {len(weights)} weight classes to {out_dir}")


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
    parser.add_argument(
        "--rankings-output-dir",
        type=str,
        help="NCAA only: write rankings_<weight>.json here instead of the real "
             "mt/rankings_data/ncaa_men/{season}/ dir -- for dry-run validation "
             "before this touches production data. Existing flo_ranked tags are "
             "still read from the real dir either way."
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
        # HS keeps the legacy mt/elo_ratings/{boys|girls}/{season}/ location: every HS reader
        # (build_wrestler_profiles, generate_dual_predictor_data, create_rankings_release, generate_elo_report)
        # looks there. (Writing to hs_ky_{gender}/ since 2026-06 meant nothing ever read the fresh output.)
        key = args.gender if args.league == 'hs' else league_dir_key(args.league, args.gender, args.state)
        output_path = Path(f"mt/elo_ratings/{key}/{args.season}/elo_ratings.json")
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write output
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_table, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Elo ratings written to: {output_path}")

    # NCAA only: also write the per-weight hybrid rank compute_all_mat_values.py
    # and the profile pages need -- see write_rankings_from_elo()'s docstring.
    rankings_output_dir = Path(args.rankings_output_dir) if args.rankings_output_dir else None
    write_rankings_from_elo(output_table, args.season, args.state, args.gender, args.league, rankings_output_dir)

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

