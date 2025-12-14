"""
Probability calculation utilities for bracket engine.

Phase 4B: Real win probability model based on rank and MV.
"""

import math
from typing import Dict, Optional, Tuple

# Configuration constants (all tunable)
WIN_PROB_ALPHA = 1.0   # rank influence
WIN_PROB_BETA = 0.25   # MV influence


def compute_win_probability(
    rank_i: Optional[int],
    rank_j: Optional[int],
    mv_i: float,
    mv_j: float
) -> float:
    """
    Compute probability that wrestler i beats wrestler j.
    
    Uses rank and MV-based model:
    z = WIN_PROB_ALPHA * log(rank_j / rank_i) + WIN_PROB_BETA * (MV_i - MV_j)
    P(i wins) = 1 / (1 + exp(-z))
    
    Args:
        rank_i: Rank of wrestler i (lower is better, None if unranked)
        rank_j: Rank of wrestler j (lower is better, None if unranked)
        mv_i: Mat Value of wrestler i
        mv_j: Mat Value of wrestler j
    
    Returns:
        Probability that wrestler i wins (0.0 to 1.0)
    """
    # Handle unranked wrestlers (treat as very low rank)
    if rank_i is None:
        rank_i = 200  # High rank number for unranked
    if rank_j is None:
        rank_j = 200
    
    # Avoid division by zero or log of zero
    if rank_i <= 0:
        rank_i = 1
    if rank_j <= 0:
        rank_j = 1
    
    # Compute rank term: log(rank_j / rank_i)
    # If rank_i < rank_j, this is positive (i is better)
    rank_term = math.log(rank_j / rank_i) if rank_i > 0 and rank_j > 0 else 0.0
    
    # Compute MV term: MV_i - MV_j
    mv_term = mv_i - mv_j
    
    # Combined score
    z = WIN_PROB_ALPHA * rank_term + WIN_PROB_BETA * mv_term
    
    # Convert to probability using sigmoid
    p_i_wins = 1.0 / (1.0 + math.exp(-z))
    
    # Clamp to valid range
    p_i_wins = max(0.0, min(1.0, p_i_wins))
    
    return p_i_wins


def compute_match_probabilities(
    wrestler_a: str,
    wrestler_b: str,
    prob_mass_a: float,
    prob_mass_b: float,
    rank_a: Optional[int] = None,
    rank_b: Optional[int] = None,
    mv_a: float = 0.0,
    mv_b: float = 0.0
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """
    Compute probability distributions for a match.
    
    Phase 4B: Uses real win probability model based on rank and MV.
    
    Args:
        wrestler_a: ID of first wrestler
        wrestler_b: ID of second wrestler
        prob_mass_a: Current probability mass of wrestler A
        prob_mass_b: Current probability mass of wrestler B
        rank_a: Rank of wrestler A (optional, for real model)
        rank_b: Rank of wrestler B (optional, for real model)
        mv_a: Mat Value of wrestler A (optional, for real model)
        mv_b: Mat Value of wrestler B (optional, for real model)
    
    Returns:
        Tuple of (winner_dist, loser_dist)
        Each dict maps wrestler_id -> probability
    """
    # If rank/MV data provided, use real model
    if rank_a is not None or rank_b is not None:
        p_a_wins = compute_win_probability(rank_a, rank_b, mv_a, mv_b)
        p_b_wins = 1.0 - p_a_wins  # Guaranteed to sum to 1
    else:
        # Fallback to 50/50 if no rank/MV data
        p_a_wins = 0.5
        p_b_wins = 0.5
    
    # Winner distribution: each wrestler contributes their mass * win probability
    winner_dist = {
        wrestler_a: prob_mass_a * p_a_wins,
        wrestler_b: prob_mass_b * p_b_wins
    }
    
    # Loser distribution: each wrestler contributes their mass * loss probability
    loser_dist = {
        wrestler_a: prob_mass_a * (1 - p_a_wins),
        wrestler_b: prob_mass_b * (1 - p_b_wins)
    }
    
    return winner_dist, loser_dist


def compute_deterministic_match(
    winner_id: str,
    loser_id: str,
    prob_mass_winner: float,
    prob_mass_loser: float
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """
    Compute probability distributions for a deterministic match (override).
    
    Winner gets 100% of combined mass, loser gets 0%.
    
    Args:
        winner_id: ID of the forced winner
        loser_id: ID of the forced loser
        prob_mass_winner: Current probability mass of winner
        prob_mass_loser: Current probability mass of loser
    
    Returns:
        Tuple of (winner_dist, loser_dist)
    """
    total_mass = prob_mass_winner + prob_mass_loser
    
    winner_dist = {
        winner_id: total_mass,
        loser_id: 0.0
    }
    
    loser_dist = {
        winner_id: 0.0,
        loser_id: 0.0  # Loser gets no mass in deterministic override
    }
    
    return winner_dist, loser_dist

