#!/usr/bin/env python3
"""
Simple test runner that doesn't require pytest.
Run with: python xtp/tests/run_tests.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from xtp.engine.bracket_schema import Slot, get_all_slots, ALL_SLOTS


def test_all_slots_loaded():
    """Verify all slots are loaded."""
    slots = get_all_slots()
    assert len(slots) > 0, "No slots loaded"
    assert ALL_SLOTS == slots, "ALL_SLOTS != get_all_slots()"
    print("✓ test_all_slots_loaded")


def test_every_slot_has_exactly_two_inputs():
    """Test that every slot has exactly 2 inputs (except terminals)."""
    slots = get_all_slots()
    
    for slot_id, slot in slots.items():
        if slot.round == "PLACE" and slot.id.startswith("PLACE_"):
            continue
        
        assert len(slot.inputs) == 2, f"Slot {slot_id} has {len(slot.inputs)} inputs, expected 2"
    print("✓ test_every_slot_has_exactly_two_inputs")


def test_all_input_references_are_valid():
    """Test that all input references point to valid slots or SEED_*."""
    slots = get_all_slots()
    valid_refs = set(slots.keys())
    valid_refs.update([f"SEED_{i}" for i in range(1, 34)])
    valid_refs.add("PIG_WINNER")
    
    for slot_id in slots.keys():
        valid_refs.add(f"{slot_id}_WINNER")
        valid_refs.add(f"{slot_id}_LOSER")
    
    for slot_id, slot in slots.items():
        if slot.round == "PLACE" and slot.id.startswith("PLACE_"):
            continue
        
        for input_ref in slot.inputs:
            if input_ref in valid_refs:
                continue
            
            if input_ref.startswith("SEED_"):
                seed_num = int(input_ref.split("_")[1])
                assert 1 <= seed_num <= 33, f"Invalid seed number in {slot_id}: {input_ref}"
                continue
            
            if "_WINNER" in input_ref or "_LOSER" in input_ref:
                base_slot = input_ref.rsplit("_", 1)[0]
                assert base_slot in slots, f"Invalid reference in {slot_id}: {input_ref} (base slot {base_slot} not found)"
                continue
            
            if input_ref == "PIG_WINNER":
                continue
            
            raise AssertionError(f"Invalid input reference in {slot_id}: {input_ref}")
    print("✓ test_all_input_references_are_valid")


def test_no_dangling_winner_to_references():
    """Test that all winner_to references point to valid slots."""
    slots = get_all_slots()
    valid_slot_ids = set(slots.keys())
    valid_slot_ids.update(["PLACE_1", "PLACE_2", "PLACE_3", "PLACE_4", "PLACE_5", "PLACE_6", "PLACE_7", "PLACE_8"])
    
    for slot_id, slot in slots.items():
        if slot.winner_to is not None:
            assert slot.winner_to in valid_slot_ids, \
                f"Slot {slot_id} has invalid winner_to: {slot.winner_to}"
    print("✓ test_no_dangling_winner_to_references")


def test_no_dangling_loser_to_references():
    """Test that all loser_to references point to valid slots or None."""
    slots = get_all_slots()
    valid_slot_ids = set(slots.keys())
    valid_slot_ids.update(["PLACE_1", "PLACE_2", "PLACE_3", "PLACE_4", "PLACE_5", "PLACE_6", "PLACE_7", "PLACE_8"])
    
    for slot_id, slot in slots.items():
        if slot.loser_to is not None:
            assert slot.loser_to in valid_slot_ids, \
                f"Slot {slot_id} has invalid loser_to: {slot.loser_to}"
    print("✓ test_no_dangling_loser_to_references")


def test_exactly_eight_placement_terminals():
    """Test that there are exactly 8 placement terminals (1st-8th)."""
    slots = get_all_slots()
    
    place_slots = [slot_id for slot_id in slots.keys() if slot_id.startswith("PLACE_")]
    assert len(place_slots) == 8, f"Expected 8 placement slots, found {len(place_slots)}"
    
    for i in range(1, 9):
        assert f"PLACE_{i}" in slots, f"Missing PLACE_{i}"
    print("✓ test_exactly_eight_placement_terminals")


def test_cons_pig_0_feeds_exactly_one_cons_r1_slot():
    """Test that CONS_PIG_0 winner feeds exactly one CONS_R1 slot."""
    slots = get_all_slots()
    
    cons_pig_0 = slots.get("CONS_PIG_0")
    assert cons_pig_0 is not None, "CONS_PIG_0 not found"
    assert cons_pig_0.winner_to == "CONS_R1_4", "CONS_PIG_0 winner should go to CONS_R1_4"
    
    cons_r1_4 = slots.get("CONS_R1_4")
    assert cons_r1_4 is not None, "CONS_R1_4 not found"
    assert "CONS_PIG_0_WINNER" in cons_r1_4.inputs, "CONS_R1_4 should have CONS_PIG_0_WINNER as input"
    print("✓ test_cons_pig_0_feeds_exactly_one_cons_r1_slot")


def test_c_r32_8_loser_not_in_cons_r1_directly():
    """Test that loser(C_R32_8) does NOT appear directly in CONS_R1."""
    slots = get_all_slots()
    
    for i in range(8):
        cons_r1_id = f"CONS_R1_{i}"
        cons_r1 = slots.get(cons_r1_id)
        assert cons_r1 is not None, f"{cons_r1_id} not found"
        assert "C_R32_8_LOSER" not in cons_r1.inputs, \
            f"{cons_r1_id} should not have C_R32_8_LOSER as direct input"
    print("✓ test_c_r32_8_loser_not_in_cons_r1_directly")


def main():
    """Run all tests."""
    tests = [
        test_all_slots_loaded,
        test_every_slot_has_exactly_two_inputs,
        test_all_input_references_are_valid,
        test_no_dangling_winner_to_references,
        test_no_dangling_loser_to_references,
        test_exactly_eight_placement_terminals,
        test_cons_pig_0_feeds_exactly_one_cons_r1_slot,
        test_c_r32_8_loser_not_in_cons_r1_directly,
    ]
    
    print("Running bracket schema tests...\n")
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"✗ {test.__name__}")
            print(f"  Error: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test.__name__}")
            print(f"  Unexpected error: {e}")
            failed += 1
    
    print(f"\n{'=' * 50}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'=' * 50}")
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

