#!/usr/bin/env python3
"""
Test runner for scoring/xTP tests.
Run with: python xtp/tests/run_scoring_tests.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Now import and run tests
from xtp.tests.test_scoring_xtp import (
    test_xtp_non_negative,
    test_champion_has_max_expected_points,
    test_total_expected_placement_points,
    test_zero_bonus_phase_4a,
    test_advancement_points_accumulate_correctly,
)


def main():
    """Run all scoring tests."""
    tests = [
        ("xTP Non-Negative", test_xtp_non_negative),
        ("Champion Has Max Expected Points", test_champion_has_max_expected_points),
        ("Total Expected Placement Points", test_total_expected_placement_points),
        ("Zero Bonus Phase 4A", test_zero_bonus_phase_4a),
        ("Advancement Points Accumulate Correctly", test_advancement_points_accumulate_correctly),
    ]
    
    print("Running scoring/xTP tests...\n")
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            print(f"Testing: {test_name}...")
            test_func()
            print(f"  ✓ PASS\n")
            passed += 1
        except AssertionError as e:
            print(f"  ✗ FAIL: {e}\n")
            failed += 1
        except Exception as e:
            print(f"  ✗ ERROR: {e}\n")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print(f"{'=' * 50}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'=' * 50}")
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

