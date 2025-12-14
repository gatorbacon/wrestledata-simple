"""
Probability calculation utilities for bracket engine.

Phase 4B: Real win probability model based on rank and MV.
"""

import math
from typing import Dict, Optional, Tuple

# Configuration constants (all tunable)
WIN_PROB_ALPHA = 1.0   # rank influence
WIN_PROB_BETA = 0.25   # MV influence


def compute_match_probabilities(
    wrestler_a: str,
    wrestler_b: str,
    prob_mass_a: float,
    prob_mass_b: float
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """
    Compute probability distributions for a match.
    
    Uses simple 0.5/0.5 model for Phase 3.
    
    Args:
        wrestler_a: ID of first wrestler
        wrestler_b: ID of second wrestler
        prob_mass_a: Current probability mass of wrestler A
        prob_mass_b: Current probability mass of wrestler B
    
    Returns:
        Tuple of (winner_dist, loser_dist)
        Each dict maps wrestler_id -> probability
    """
    # Simple 50/50 model
    p_a_wins = 0.5
    p_b_wins = 0.5
    
    # Winner distribution: each wrestler contributes their mass * win probability
    winner_dist = {
        wrestler_a: prob_mass_a * p_a_wins,
        wrestler_b: prob_mass_b * p_b_wins
    }
    
    # Loser distribution: each wrestler contributes their mass * loss probability
    loser_dist = {
        wrestler_a: prob_mass_a * (1 - p_a_wins),  # prob_mass_a * 0.5
        wrestler_b: prob_mass_b * (1 - p_b_wins)   # prob_mass_b * 0.5
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

