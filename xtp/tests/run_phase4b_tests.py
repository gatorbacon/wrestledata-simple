#!/usr/bin/env python3
"""
Test runner for Phase 4B tests.
Run with: python xtp/tests/run_phase4b_tests.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Now import and run tests
from xtp.tests.test_phase4b import (
    test_xTP_components_sum,
    test_bonus_only_on_wins,
    test_higher_MV_increases_prob,
    test_rank_dominates_MV,
    test_bonus_cap_respected,
    test_opponent_multipliers,
    test_win_probability_symmetry,
)


def main():
    """Run all Phase 4B tests."""
    tests = [
        ("xTP Components Sum", test_xTP_components_sum),
        ("Bonus Only on Wins", test_bonus_only_on_wins),
        ("Higher MV Increases Prob", test_higher_MV_increases_prob),
        ("Rank Dominates MV", test_rank_dominates_MV),
        ("Bonus Cap Respected", test_bonus_cap_respected),
        ("Opponent Multipliers", test_opponent_multipliers),
        ("Win Probability Symmetry", test_win_probability_symmetry),
    ]
    
    print("Running Phase 4B tests...\n")
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

