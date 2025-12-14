#!/usr/bin/env python3
"""
Test runner for probability mass tests.
Run with: python xtp/tests/run_probability_tests.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Now import and run tests
from xtp.tests.test_probability_mass import (
    test_mass_conservation,
    test_championship_final_mass_equals_1,
    test_exactly_eight_aa_probabilities,
    test_deterministic_override_collapses_mass,
    test_no_negative_or_nan_probabilities,
)


def main():
    """Run all probability tests."""
    tests = [
        ("Mass Conservation", test_mass_conservation),
        ("Championship Final Mass Equals 1", test_championship_final_mass_equals_1),
        ("Exactly Eight AA Probabilities", test_exactly_eight_aa_probabilities),
        ("Deterministic Override Collapses Mass", test_deterministic_override_collapses_mass),
        ("No Negative or NaN Probabilities", test_no_negative_or_nan_probabilities),
    ]
    
    print("Running probability mass tests...\n")
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

