#!/usr/bin/env python3
"""
Test runner for engine tests.
Run with: python xtp/tests/run_engine_tests.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Now import and run tests
from xtp.tests.test_engine_paths import (
    test_full_championship_path,
    test_consolation_pigtail_path,
    test_blood_round_path,
    test_final_placements,
    test_illegal_winner_raises,
)


def main():
    """Run all engine tests."""
    tests = [
        ("Full Championship Path", test_full_championship_path),
        ("Consolation Pigtail Path", test_consolation_pigtail_path),
        ("Blood Round Path", test_blood_round_path),
        ("Final Placements", test_final_placements),
        ("Illegal Winner Raises", test_illegal_winner_raises),
    ]
    
    print("Running engine tests...\n")
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

