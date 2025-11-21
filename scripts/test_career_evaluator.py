#!/usr/bin/env python3
"""
Test script for the career match evaluator.
"""

import sys
from link_and_upload_season import (
    evaluate_career_match,
    name_similarity,
    is_exact_name_match,
    normalize_weight,
    normalize_class_year,
    class_year_score
)

def test_career_match_evaluator():
    """
    Test function for the career match evaluator.
    Tests key rules from the decision table.
    """
    # Helper function to create test wrestlers
    def create_test_wrestlers(is_freshman, name_match, exact_name, team_match, 
                            weight_match, grade_match):
        current_name = "John Smith"
        
        # Set match name based on parameters
        if not name_match:
            match_name = "Mike Jones"  # Completely different name
        elif not exact_name:
            match_name = "Johnny Smith"  # Similar but not exact
        else:
            match_name = "John Smith"  # Exact match
        
        # Debugging
        if not name_match:
            print(f"DEBUG In create_test_wrestlers: name_match is FALSE, so match_name should be different: '{match_name}'")
        
        # Set up team IDs
        current_team = "TEAM1"
        match_team = current_team if team_match else "TEAM2"
        
        # Set up weight classes
        current_weight = 165
        match_weight = current_weight if weight_match else current_weight - 30
        
        # Set up class years for grade progression
        if is_freshman:
            current_class = "FR"
            match_class = "SO" if grade_match else "FR"  # FR->SO is progression
        else:
            current_class = "SO"
            match_class = "FR" if grade_match else "SO"  # FR->SO is progression, SO->SO is not
        
        current = {
            'name': current_name,
            'class_year': current_class,
            'team_id': current_team,
            'weight_class': str(current_weight)
        }
        
        match = {
            'name': match_name,
            'class_year': match_class,
            'team_id': match_team,
            'weight_class': str(match_weight)
        }
        
        return current, match
    
    # Test case for row 12 specifically
    print("\n=== TESTING ROW 12 ===")
    wrestler, match = {
        'name': 'John Smith',
        'class_year': 'FR',
        'team_id': 'TEAM1',
        'weight_class': '165'
    }, {
        'name': 'Mike Jones',
        'class_year': 'FR',
        'team_id': 'TEAM2',
        'weight_class': '135'
    }
    
    # Direct test before the main loop
    name_sim = name_similarity(wrestler.get('name', ''), match.get('name', ''))
    print(f"Name similarity: {name_sim}")
    print(f"Names are different: {wrestler.get('name', '').lower() != match.get('name', '').lower()}")
    print(f"Name match (>= 0.4): {name_sim >= 0.4}")
    
    action, score = evaluate_career_match(wrestler, match)
    print(f"Result for Row 12: {action} (score: {score})")
    print(f"Expected: AUTO New Career")
    
    # Test cases based directly on the rules table
    test_cases = [
        # Row 1: Non-freshman, no name match
        {'row': 1, 'is_freshman': False, 'name_match': False, 'exact_name': False, 
         'team_match': False, 'weight_match': False, 'grade_match': False,
         'expected_action': 'Add to Suspect List'},
        
        # Row 5: Non-freshman, name match but not exact, same team, no weight match, grade match
        {'row': 5, 'is_freshman': False, 'name_match': True, 'exact_name': False, 
         'team_match': True, 'weight_match': False, 'grade_match': True,
         'expected_action': 'Add to Suspect List'},
        
        # Row 6: Non-freshman, name match but not exact, same team, weight match, no grade match
        {'row': 6, 'is_freshman': False, 'name_match': True, 'exact_name': False, 
         'team_match': True, 'weight_match': True, 'grade_match': False,
         'expected_action': 'AUTO Link Career'},
        
        # Row 11: Non-freshman, exact name, same team, weight match, grade match
        {'row': 11, 'is_freshman': False, 'name_match': True, 'exact_name': True, 
         'team_match': True, 'weight_match': True, 'grade_match': True,
         'expected_action': 'AUTO Link Career'},
        
        # Row 28: Freshman, exact name, same team, weight match, grade match
        {'row': 28, 'is_freshman': True, 'name_match': True, 'exact_name': True, 
         'team_match': True, 'weight_match': True, 'grade_match': True,
         'expected_action': 'AUTO Link Career'},
    ]
    
    # Direct test for row 12 (freshman with no name match)
    print("\n=== TESTING ROW 12 DIRECTLY ===")
    row12_current = {
        'name': 'John Smith',
        'class_year': 'FR',
        'team_id': 'TEAM1',
        'weight_class': '165'
    }
    row12_match = {
        'name': 'Mike Jones',
        'class_year': 'FR',
        'team_id': 'TEAM2',
        'weight_class': '135'
    }
    
    # Test name similarity calculation
    name_sim = name_similarity('John Smith', 'Mike Jones')
    print(f"Direct name_similarity('John Smith', 'Mike Jones') = {name_sim}")
    
    # Try with very different names
    name_sim2 = name_similarity('ABCDEFG', 'HIJKLMN')
    print(f"Direct name_similarity('ABCDEFG', 'HIJKLMN') = {name_sim2}")
    
    row12_action, row12_score = evaluate_career_match(row12_current, row12_match)
    
    if row12_action == 'AUTO New Career':
        print(f"✅ Row 12 Direct Test PASSED: {row12_action} (score: {row12_score})")
    else:
        print(f"❌ Row 12 Direct Test FAILED: Expected AUTO New Career, got {row12_action}")
        print(f"Current: {row12_current}")
        print(f"Match: {row12_match}")
        print(f"Score: {row12_score}")
    
    print("\n=== TESTING CAREER MATCH EVALUATOR ===")
    
    # Run all tests
    passed = 0
    for i, test in enumerate(test_cases, 1):
        current, match = create_test_wrestlers(
            test['is_freshman'], test['name_match'], test['exact_name'],
            test['team_match'], test['weight_match'], test['grade_match']
        )
        
        action, score = evaluate_career_match(current, match)
        
        # Check if result matches expected action
        if action != test['expected_action']:
            print(f"❌ Test {i} (Row {test['row']}) FAILED: Expected {test['expected_action']}, got {action}")
            print(f"Wrestler: {current}")
            print(f"Match: {match}")
            print(f"Score: {score}")
        else:
            print(f"✅ Test {i} (Row {test['row']}) PASSED: {action} (score: {score})")
            passed += 1
    
    # Output summary
    print(f"\nTest results: {passed}/{len(test_cases)} tests passed")
    if passed == len(test_cases):
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed!")

if __name__ == "__main__":
    test_career_match_evaluator() 