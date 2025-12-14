"""
Tests for Phase 4B: Real win probability and bonus models.

Tests that real models are integrated correctly without breaking existing functionality.
"""

from xtp.engine.engine import BracketEngine
from xtp.engine.bracket_schema import get_all_slots
from xtp.engine.probability import compute_win_probability
from xtp.engine.scoring import expected_bonus_for_slot, get_opponent_multiplier
from xtp.engine.bracket_schema import Slot


def create_test_engine_with_data():
    """Create a test engine with rank, MV, and bonus data."""
    slots = get_all_slots()
    seeds = {i: f"wrestler_{i}" for i in range(1, 34)}
    
    # Create rank, MV, and bonus data
    rank_by_id = {f"wrestler_{i}": i for i in range(1, 34)}
    mv_by_id = {f"wrestler_{i}": 0.0 for i in range(1, 34)}  # Default MV
    bonus_ev_by_id = {f"wrestler_{i}": 1.0 for i in range(1, 34)}  # Default bonus EV
    
    return BracketEngine(
        slots, seeds, enable_probability=True,
        rank_by_id=rank_by_id,
        mv_by_id=mv_by_id,
        bonus_ev_by_id=bonus_ev_by_id
    )


def test_xTP_components_sum():
    """
    Test that xTP == xTP_A + xTP_P + xTP_B.
    
    Components must sum correctly.
    """
    engine = create_test_engine_with_data()
    
    # Resolve some slots
    engine.set_winner("C_PIG_0", "wrestler_32")
    engine.set_winner("C_R32_0", "wrestler_1")
    
    # Compute expected points
    engine.compute_expected_points()
    
    # Get components
    components = engine.get_xtp_components()
    
    # Verify sum for each wrestler
    for wrestler_id, comps in components.items():
        xTP_A = comps["xTP_A"]
        xTP_P = comps["xTP_P"]
        xTP_B = comps["xTP_B"]
        xTP = comps["xTP"]
        
        expected_sum = xTP_A + xTP_P + xTP_B
        assert abs(xTP - expected_sum) < 0.001, \
            f"xTP components don't sum correctly for {wrestler_id}: " \
            f"xTP={xTP}, sum={expected_sum}"


def test_bonus_only_on_wins():
    """
    Test that bonus is added only when P(win) > 0.
    
    Bonus should only accumulate for potential winners.
    """
    engine = create_test_engine_with_data()
    
    # Resolve a slot deterministically
    engine.set_winner("C_PIG_0", "wrestler_32")
    
    # Compute expected points
    engine.compute_expected_points()
    
    # Loser (wrestler_33) should have no bonus points
    loser_bonus = engine.expected_bonus_points.get("wrestler_33", 0.0)
    assert loser_bonus == 0.0, \
        f"Loser should have 0 bonus points, got {loser_bonus}"
    
    # Winner might have bonus (if probability model was used before deterministic override)
    # But in deterministic mode, bonus is computed from the override, not probabilities
    # This test verifies that bonus is only added for winners


def test_higher_MV_increases_prob():
    """
    Test that holding rank constant, higher MV increases P(win).
    
    Higher MV should lead to higher win probability.
    """
    # Test with same ranks, different MVs
    rank = 10
    
    # Lower MV
    p_low_mv = compute_win_probability(rank, rank, mv_i=0.0, mv_j=0.0)
    
    # Higher MV for wrestler i
    p_high_mv = compute_win_probability(rank, rank, mv_i=5.0, mv_j=0.0)
    
    assert p_high_mv > p_low_mv, \
        f"Higher MV should increase win probability. Low MV: {p_low_mv}, High MV: {p_high_mv}"
    
    # Test with different ranks but same MV difference
    p_rank10_vs_rank10 = compute_win_probability(10, 10, mv_i=3.0, mv_j=0.0)
    p_rank20_vs_rank20 = compute_win_probability(20, 20, mv_i=3.0, mv_j=0.0)
    
    # Should be similar (both have same rank difference and MV difference)
    assert abs(p_rank10_vs_rank10 - p_rank20_vs_rank20) < 0.1, \
        "Same rank difference and MV difference should give similar probabilities"


def test_rank_dominates_MV():
    """
    Test that large rank gaps overwhelm MV differences.
    
    Rank should be the primary factor, MV should only nudge close matches.
    """
    # Large rank gap: rank 1 vs rank 30
    p_rank1_vs_rank30 = compute_win_probability(1, 30, mv_i=0.0, mv_j=10.0)
    
    # Even with much higher MV, rank 30 should have very low probability
    assert p_rank1_vs_rank30 > 0.7, \
        f"Rank 1 should have high win probability vs rank 30 even with MV disadvantage: {p_rank1_vs_rank30}"
    
    # Reverse: rank 30 vs rank 1
    p_rank30_vs_rank1 = compute_win_probability(30, 1, mv_i=10.0, mv_j=0.0)
    
    # Even with much higher MV, rank 30 should have low probability
    assert p_rank30_vs_rank1 < 0.3, \
        f"Rank 30 should have low win probability vs rank 1 even with MV advantage: {p_rank30_vs_rank1}"
    
    # Close ranks: rank 10 vs rank 11
    p_close_ranks = compute_win_probability(10, 11, mv_i=0.0, mv_j=0.0)
    
    # Should be close to 0.5
    assert 0.4 < p_close_ranks < 0.6, \
        f"Close ranks should give probabilities near 0.5: {p_close_ranks}"


def test_bonus_cap_respected():
    """
    Test that xTP_B never exceeds 2.0 per match.
    
    Bonus should be capped at BONUS_CAP.
    """
    from xtp.engine.scoring import BONUS_CAP
    
    # Create a test slot
    slot = Slot(
        id="TEST_SLOT",
        bracket="champ",
        round="R32",
        inputs=["w1", "w2"],
        winner_to="TEST_WINNER",
        loser_to="TEST_LOSER"
    )
    
    # Test with very high bonus EV
    high_bonus_ev = 10.0  # Way above cap
    p_win = 1.0  # 100% win probability
    
    # Test with different opponent ranks
    for opponent_rank in [1, 10, 20, 30]:
        expected_bonus = expected_bonus_for_slot(
            slot, "w1", "w2", p_win, high_bonus_ev, opponent_rank
        )
        
        # Expected bonus should never exceed BONUS_CAP * p_win
        max_expected = BONUS_CAP * p_win
        assert expected_bonus <= max_expected, \
            f"Expected bonus exceeds cap: {expected_bonus} > {max_expected} for rank {opponent_rank}"
    
    # Test that cap is actually applied
    # With rank 1-8 opponent (0.5 multiplier), even 10.0 bonus EV should cap at 2.0
    expected_bonus_rank5 = expected_bonus_for_slot(
        slot, "w1", "w2", 1.0, 10.0, 5
    )
    assert expected_bonus_rank5 <= BONUS_CAP, \
        f"Bonus should be capped at {BONUS_CAP}, got {expected_bonus_rank5}"


def test_opponent_multipliers():
    """Test that opponent multipliers are applied correctly."""
    # Test each rank range
    assert get_opponent_multiplier(5) == 0.50, "Rank 5 should have 0.50 multiplier"
    assert get_opponent_multiplier(12) == 0.75, "Rank 12 should have 0.75 multiplier"
    assert get_opponent_multiplier(20) == 1.00, "Rank 20 should have 1.00 multiplier"
    assert get_opponent_multiplier(30) == 1.15, "Rank 30 should have 1.15 multiplier"
    assert get_opponent_multiplier(None) == 1.15, "Unranked should have 1.15 multiplier"


def test_win_probability_symmetry():
    """Test that P(i wins) + P(j wins) = 1.0."""
    rank_i, rank_j = 10, 15
    mv_i, mv_j = 2.0, 1.0
    
    p_i_wins = compute_win_probability(rank_i, rank_j, mv_i, mv_j)
    p_j_wins = compute_win_probability(rank_j, rank_i, mv_j, mv_i)
    
    total = p_i_wins + p_j_wins
    assert abs(total - 1.0) < 0.001, \
        f"Probabilities should sum to 1.0: P(i wins)={p_i_wins}, P(j wins)={p_j_wins}, sum={total}"

