"""
Scoring utilities for xTP (expected Tournament Points) calculation.

Phase 4B: Real bonus expectation model with opponent difficulty multipliers.
"""

from typing import Optional
from xtp.engine.bracket_schema import Slot

# Configuration constants
BONUS_CAP = 2.0

# Opponent difficulty multipliers by rank range
OPPONENT_MULTIPLIERS = {
    (1, 8): 0.50,      # Ranks 1-8
    (9, 16): 0.75,     # Ranks 9-16
    (17, 24): 1.00,    # Ranks 17-24
    (25, 9999): 1.15,  # Ranks 25+
}


def advancement_points_for_slot(slot: Slot) -> float:
    """
    Get advancement points for winning a slot.
    
    NCAA standard:
    - Championship R32, R16, QF, SF wins: 1.0
    - Consolation wins (any round): 0.5
    - Other: 0.0
    
    Args:
        slot: The slot/match
    
    Returns:
        Advancement points for winning this slot
    """
    if slot.bracket == "champ":
        # Championship bracket
        if slot.round in ["R32", "R16", "QF", "SF"]:
            return 1.0
        # Final doesn't give advancement points (only placement)
        return 0.0
    elif slot.bracket == "consol":
        # Consolation bracket - any win gives 0.5, except placement matches (no advancement pts)
        if slot.round in ["PIG", "R1", "R2", "R3", "R4", "QF", "SF"]:
            return 0.5
        return 0.0
    
    return 0.0


def placement_points(place: int) -> float:
    """
    Get placement points for finishing at a given place.
    
    NCAA standard:
    - 1st: 16
    - 2nd: 12
    - 3rd: 10
    - 4th: 9
    - 5th: 7
    - 6th: 6
    - 7th: 4
    - 8th: 3
    
    Args:
        place: Placement (1-8)
    
    Returns:
        Placement points
    """
    placement_table = {
        1: 16.0,
        2: 12.0,
        3: 10.0,
        4: 9.0,
        5: 7.0,
        6: 6.0,
        7: 4.0,
        8: 3.0
    }
    
    return placement_table.get(place, 0.0)


def get_opponent_multiplier(opponent_rank: Optional[int]) -> float:
    """
    Get opponent difficulty multiplier based on rank.
    
    Args:
        opponent_rank: Opponent's rank (None if unranked)
    
    Returns:
        Multiplier value
    """
    if opponent_rank is None:
        # Unranked opponents use highest multiplier
        return OPPONENT_MULTIPLIERS[(25, 9999)]
    
    for (min_rank, max_rank), multiplier in OPPONENT_MULTIPLIERS.items():
        if min_rank <= opponent_rank <= max_rank:
            return multiplier
    
    # Default to highest multiplier
    return OPPONENT_MULTIPLIERS[(25, 9999)]


def expected_bonus_for_slot(
    slot: Slot,
    winner_id: str,
    loser_id: str,
    p_win: float,
    bonus_ev_shrunk: float,
    opponent_rank: Optional[int] = None
) -> float:
    """
    Compute expected bonus points for a slot.
    
    Phase 4B: Real bonus model using shrunk Top-33 bonus EV and opponent multipliers.
    
    Expected_Bonus = P(win) * min(bonus_ev_shrunk * opponent_multiplier, BONUS_CAP)
    
    Args:
        slot: The slot/match
        winner_id: ID of the winner
        loser_id: ID of the loser
        p_win: Probability of winning this match
        bonus_ev_shrunk: Wrestler's shrunk Top-33 bonus EV
        opponent_rank: Opponent's rank (for multiplier)
    
    Returns:
        Expected bonus points
    """
    # Bonus applies ONLY on wins
    if p_win <= 0.0:
        return 0.0
    
    # Get opponent multiplier
    opponent_mult = get_opponent_multiplier(opponent_rank)
    
    # Compute base bonus
    base_bonus = bonus_ev_shrunk * opponent_mult
    
    # Apply cap
    capped_bonus = min(base_bonus, BONUS_CAP)
    
    # Expected bonus = P(win) * capped bonus
    expected_bonus = p_win * capped_bonus
    
    return expected_bonus

