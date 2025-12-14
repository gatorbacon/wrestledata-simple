"""
Scoring utilities for xTP (expected Tournament Points) calculation.

Phase 4A: Core scoring architecture with placeholder bonus model.
"""

from xtp.engine.bracket_schema import Slot


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
        # Consolation bracket - any win gives 0.5
        if slot.round in ["PIG", "R1", "R2", "R3", "R4", "QF", "SF", "PLACE"]:
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


def expected_bonus_for_slot(slot: Slot, winner_id: str, loser_id: str) -> float:
    """
    Compute expected bonus points for a slot.
    
    Phase 4A: Always returns 0.0 (placeholder).
    
    Args:
        slot: The slot/match
        winner_id: ID of the winner
        loser_id: ID of the loser
    
    Returns:
        Expected bonus points (0.0 in Phase 4A)
    """
    # Phase 4A: bonus is always 0.0
    return 0.0

