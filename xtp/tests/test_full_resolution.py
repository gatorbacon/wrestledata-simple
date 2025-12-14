"""
Tests for full bracket probability resolution.

Ensures that all slots, including placement terminals, are resolved.
"""

from xtp.engine.engine import BracketEngine
from xtp.engine.bracket_schema import get_all_slots


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


def test_all_placement_slots_resolved():
    """
    Test that all placement slots (1st-8th) are resolved.
    
    Assert all PLACE_* slots have non-empty distributions.
    """
    engine = create_test_engine_with_data()
    
    # Resolve all slots
    engine.resolve_all_probabilistically()
    
    # Check placement terminals
    placement_slots = [
        "C_F_0",  # 1st and 2nd
        "CONS_3RD",  # 3rd and 4th
        "CONS_5TH",  # 5th and 6th
        "CONS_7TH",  # 7th and 8th
    ]
    
    for slot_id in placement_slots:
        assert slot_id in engine.resolved_slots or slot_id in engine.slot_prob_results, \
            f"Placement slot {slot_id} not resolved"
        
        # Check that it has probability results
        if slot_id in engine.slot_prob_results:
            prob_results = engine.slot_prob_results[slot_id]
            winner_dist = prob_results.get("winner", {})
            loser_dist = prob_results.get("loser", {})
            
            # At least one distribution should have mass
            total_winner = sum(winner_dist.values())
            total_loser = sum(loser_dist.values())
            
            assert total_winner > 0.0 or total_loser > 0.0, \
                f"Placement slot {slot_id} has no probability mass"


def test_xTP_P_nonzero():
    """
    Test that at least one wrestler has xTP_P > 0.
    
    Placement points should be non-zero after full resolution.
    """
    engine = create_test_engine_with_data()
    
    # Resolve all slots
    engine.resolve_all_probabilistically()
    
    # Compute expected points
    engine.compute_expected_points()
    
    # Get components
    components = engine.get_xtp_components()
    
    # Check that at least one wrestler has placement points
    max_xTP_P = max(comps.get("xTP_P", 0.0) for comps in components.values())
    
    assert max_xTP_P > 0.0, \
        f"No wrestler has placement points. Max xTP_P: {max_xTP_P}"


def test_total_placement_points_conserved():
    """
    Test that total expected placement points equals NCAA total.
    
    Sum of xTP_P across all wrestlers should equal:
    16 + 12 + 10 + 9 + 7 + 6 + 4 + 3 = 67
    """
    engine = create_test_engine_with_data()
    
    # Resolve all slots
    engine.resolve_all_probabilistically()
    
    # Compute expected points
    engine.compute_expected_points()
    
    # Get components
    components = engine.get_xtp_components()
    
    # Sum all placement points
    total_xTP_P = sum(comps.get("xTP_P", 0.0) for comps in components.values())
    
    # NCAA placement points: 1st=16, 2nd=12, 3rd=10, 4th=9, 5th=7, 6th=6, 7th=4, 8th=3
    expected_total = 16 + 12 + 10 + 9 + 7 + 6 + 4 + 3  # = 67
    
    # Allow small floating point differences
    assert abs(total_xTP_P - expected_total) < 0.1, \
        f"Total placement points mismatch: {total_xTP_P} != {expected_total}"


def test_resolution_converges():
    """
    Test that bracket resolution converges within max_iterations.
    
    Engine should resolve without raising RuntimeError.
    """
    engine = create_test_engine_with_data()
    
    # Should not raise RuntimeError
    try:
        engine.resolve_all_probabilistically(max_iterations=100, epsilon=1e-9)
        converged = True
    except RuntimeError:
        converged = False
    
    assert converged, "Bracket resolution did not converge"
    
    # Should have resolved most slots
    total_slots = len(engine.slots)
    resolved_slots = len(engine.resolved_slots)
    
    # At least 80% of slots should be resolved
    resolution_rate = resolved_slots / total_slots
    assert resolution_rate >= 0.8, \
        f"Only {resolution_rate:.1%} of slots resolved ({resolved_slots}/{total_slots})"


def test_placement_terminals_have_mass():
    """
    Test that placement terminals receive probability mass.
    
    After full resolution, placement matches should have non-zero mass.
    """
    engine = create_test_engine_with_data()
    
    # Resolve all slots
    engine.resolve_all_probabilistically()
    
    # Check that placement slots have probability mass
    placement_slots = ["C_F_0", "CONS_3RD", "CONS_5TH", "CONS_7TH"]
    
    total_placement_mass = 0.0
    
    for slot_id in placement_slots:
        if slot_id in engine.slot_prob_results:
            prob_results = engine.slot_prob_results[slot_id]
            winner_dist = prob_results.get("winner", {})
            loser_dist = prob_results.get("loser", {})
            
            total_placement_mass += sum(winner_dist.values())
            total_placement_mass += sum(loser_dist.values())
    
    # Total mass at placements should be close to 8.0 (8 placements)
    assert total_placement_mass > 0.0, \
        f"No probability mass at placement terminals: {total_placement_mass}"
    
    # Should be close to 8.0 (one placement per wrestler, 8 placements total)
    assert abs(total_placement_mass - 8.0) < 1.0, \
        f"Placement mass should be ~8.0, got {total_placement_mass}"

