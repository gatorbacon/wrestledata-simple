"""
Tests for bracket schema validation.

Tests wiring structure only - no probabilities or scoring.
"""

import pytest
from xtp.engine.bracket_schema import Slot, get_all_slots, ALL_SLOTS


def test_all_slots_loaded():
    """Verify all slots are loaded."""
    slots = get_all_slots()
    assert len(slots) > 0
    assert ALL_SLOTS == slots


def test_every_slot_has_exactly_two_inputs():
    """Test that every slot has exactly 2 inputs (except terminals)."""
    slots = get_all_slots()
    
    for slot_id, slot in slots.items():
        if slot.round == "PLACE" and slot.id.startswith("PLACE_"):
            # Terminal placement nodes don't have inputs defined here
            # They are referenced by other slots
            continue
        
        assert len(slot.inputs) == 2, f"Slot {slot_id} has {len(slot.inputs)} inputs, expected 2"


def test_all_input_references_are_valid():
    """Test that all input references point to valid slots or SEED_*."""
    slots = get_all_slots()
    valid_refs = set(slots.keys())
    valid_refs.update([f"SEED_{i}" for i in range(1, 34)])  # SEED_1 through SEED_33
    valid_refs.add("PIG_WINNER")
    
    # Also valid: *_WINNER and *_LOSER references
    for slot_id in slots.keys():
        valid_refs.add(f"{slot_id}_WINNER")
        valid_refs.add(f"{slot_id}_LOSER")
    
    for slot_id, slot in slots.items():
        if slot.round == "PLACE" and slot.id.startswith("PLACE_"):
            continue
        
        for input_ref in slot.inputs:
            # Check if it's a direct slot reference
            if input_ref in valid_refs:
                continue
            
            # Check if it's a SEED reference
            if input_ref.startswith("SEED_"):
                seed_num = int(input_ref.split("_")[1])
                assert 1 <= seed_num <= 33, f"Invalid seed number in {slot_id}: {input_ref}"
                continue
            
            # Check if it's a WINNER/LOSER reference
            if "_WINNER" in input_ref or "_LOSER" in input_ref:
                base_slot = input_ref.rsplit("_", 1)[0]  # Remove _WINNER or _LOSER
                assert base_slot in slots, f"Invalid reference in {slot_id}: {input_ref} (base slot {base_slot} not found)"
                continue
            
            # Check PIG_WINNER
            if input_ref == "PIG_WINNER":
                continue
            
            pytest.fail(f"Invalid input reference in {slot_id}: {input_ref}")


def test_no_dangling_winner_to_references():
    """Test that all winner_to references point to valid slots."""
    slots = get_all_slots()
    valid_slot_ids = set(slots.keys())
    valid_slot_ids.update(["PLACE_1", "PLACE_2", "PLACE_3", "PLACE_4", "PLACE_5", "PLACE_6", "PLACE_7", "PLACE_8"])
    
    for slot_id, slot in slots.items():
        if slot.winner_to is not None:
            assert slot.winner_to in valid_slot_ids, \
                f"Slot {slot_id} has invalid winner_to: {slot.winner_to}"


def test_no_dangling_loser_to_references():
    """Test that all loser_to references point to valid slots or None."""
    slots = get_all_slots()
    valid_slot_ids = set(slots.keys())
    valid_slot_ids.update(["PLACE_1", "PLACE_2", "PLACE_3", "PLACE_4", "PLACE_5", "PLACE_6", "PLACE_7", "PLACE_8"])
    
    for slot_id, slot in slots.items():
        if slot.loser_to is not None:
            assert slot.loser_to in valid_slot_ids, \
                f"Slot {slot_id} has invalid loser_to: {slot.loser_to}"


def test_exactly_eight_placement_terminals():
    """Test that there are exactly 8 placement terminals (1st-8th)."""
    slots = get_all_slots()
    
    place_slots = [slot_id for slot_id in slots.keys() if slot_id.startswith("PLACE_")]
    assert len(place_slots) == 8, f"Expected 8 placement slots, found {len(place_slots)}"
    
    for i in range(1, 9):
        assert f"PLACE_{i}" in slots, f"Missing PLACE_{i}"


def test_cons_pig_0_feeds_exactly_one_cons_r1_slot():
    """Test that CONS_PIG_0 winner feeds exactly one CONS_R1 slot."""
    slots = get_all_slots()
    
    cons_pig_0 = slots.get("CONS_PIG_0")
    assert cons_pig_0 is not None, "CONS_PIG_0 not found"
    assert cons_pig_0.winner_to == "CONS_R1_4", "CONS_PIG_0 winner should go to CONS_R1_4"
    
    # Verify CONS_R1_4 has CONS_PIG_0_WINNER as an input
    cons_r1_4 = slots.get("CONS_R1_4")
    assert cons_r1_4 is not None, "CONS_R1_4 not found"
    assert "CONS_PIG_0_WINNER" in cons_r1_4.inputs, "CONS_R1_4 should have CONS_PIG_0_WINNER as input"


def test_c_r32_8_loser_not_in_cons_r1_directly():
    """Test that loser(C_R32_8) does NOT appear directly in CONS_R1."""
    slots = get_all_slots()
    
    # Check all CONS_R1 slots
    for i in range(8):
        cons_r1_id = f"CONS_R1_{i}"
        cons_r1 = slots.get(cons_r1_id)
        assert cons_r1 is not None, f"{cons_r1_id} not found"
        
        # C_R32_8_LOSER should NOT be a direct input
        assert "C_R32_8_LOSER" not in cons_r1.inputs, \
            f"{cons_r1_id} should not have C_R32_8_LOSER as direct input"
    
    # But it should go to CONS_PIG_0
    c_r32_8 = slots.get("C_R32_8")
    assert c_r32_8 is not None, "C_R32_8 not found"
    assert c_r32_8.loser_to == "CONS_PIG_0", "C_R32_8 loser should go to CONS_PIG_0"


def test_c_r32_8_loser_goes_to_cons_pig_0():
    """Test that C_R32_8 loser goes to CONS_PIG_0."""
    slots = get_all_slots()
    
    c_r32_8 = slots.get("C_R32_8")
    assert c_r32_8 is not None
    assert c_r32_8.loser_to == "CONS_PIG_0"
    
    cons_pig_0 = slots.get("CONS_PIG_0")
    assert cons_pig_0 is not None
    assert "C_R32_8_LOSER" in cons_pig_0.inputs


def test_all_championship_slots_have_winner_to():
    """Test that all championship bracket slots (except final) have winner_to."""
    slots = get_all_slots()
    
    champ_slots = [s for s in slots.values() if s.bracket == "champ" and s.round != "PLACE"]
    
    for slot in champ_slots:
        if slot.id == "C_F_0":
            # Final winner goes to PLACE_1
            assert slot.winner_to == "PLACE_1"
        else:
            assert slot.winner_to is not None, f"Championship slot {slot.id} missing winner_to"


def test_all_consolation_slots_have_appropriate_routing():
    """Test that consolation slots have appropriate routing."""
    slots = get_all_slots()
    
    cons_slots = [s for s in slots.values() if s.bracket == "consol"]
    
    for slot in cons_slots:
        if slot.id.startswith("PLACE_"):
            continue
        
        # Most consolation slots should have winner_to (except eliminated ones)
        if slot.loser_to is None and slot.winner_to is None:
            # This is an elimination slot - verify it's intentional
            if slot.id == "CONS_PIG_0":
                assert slot.loser_to is None  # Eliminated
            elif "LOSER" in str(slot.inputs):
                # Slots that take losers might eliminate
                pass
            else:
                # Should have at least one output
                assert slot.winner_to is not None or slot.loser_to is not None, \
                    f"Consolation slot {slot.id} has no outputs"

