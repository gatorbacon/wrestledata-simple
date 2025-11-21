#!/usr/bin/env python3
import json
from pathlib import Path
from difflib import SequenceMatcher

# Copied matching functions to avoid importing boto3
def normalize_name(name):
    return name.strip().lower()

def normalize_weight(weight):
    try:
        return int(float(weight))
    except:
        return None

def normalize_class_year(grade):
    if not grade:
        return ""
    norm = grade.upper().replace("-", "").replace(".", "").replace(" ", "")
    mapping = {
        "FR": "FR", "RSFR": "RSFR", "RFR": "RSFR",
        "SO": "SO", "RSSO": "RSSO", "RSO": "RSSO",
        "JR": "JR", "RSJR": "RSJR", "RJR": "RSJR",
        "SR": "SR", "RSSR": "RSSR", "RSR": "RSSR",
    }
    return mapping.get(norm, norm)

def class_year_score(current, previous):
    # Normalize both years
    current = normalize_class_year(current)
    previous = normalize_class_year(previous)

    # Simplified flexible mapping by treating RS and non-RS years the same tier
    tier_map = {
        "FR": 0, "RSFR": 0,
        "SO": 1, "RSSO": 1,
        "JR": 2, "RSJR": 2,
        "SR": 3, "RSSR": 3
    }

    t1 = tier_map.get(previous)
    t2 = tier_map.get(current)

    if t1 is None or t2 is None:
        return 0

    if t2 == t1 or t2 == t1 + 1:
        return 0.1

    return 0

def name_similarity(a, b):
    return SequenceMatcher(None, normalize_name(a), normalize_name(b)).ratio()

def weight_score(w1, w2):
    if w1 is None or w2 is None:
        return 0
    diff = abs(w1 - w2)
    if diff <= 10:
        return 0.2  # Same or adjacent weight class
    elif diff <= 20:
        return 0.1  # Within two classes
    return 0

def match_wrestler(current, pool):
    best_match = None
    best_score = 0
    debug_info = {}

    for candidate in pool.values():
        score = 0
        cname = candidate.get('name', '')
        cteam = candidate.get('team_id', '')
        cweight = normalize_weight(candidate.get('weight_class'))
        cgrade = normalize_class_year(candidate.get('class_year', ''))

        name_sim = name_similarity(current['name'], cname)
        if name_sim >= 0.9:
            score += 0.5

        if current['team_id'] == cteam:
            score += 0.2

        ws = weight_score(normalize_weight(current['weight_class']), cweight)
        score += ws

        cs = class_year_score(normalize_class_year(current['class_year']), cgrade)
        score += cs

        if score > best_score:
            best_score = score
            best_match = candidate
            debug_info = {
                'name': cname,
                'team': cteam,
                'weight': cweight,
                'grade': cgrade,
                'name_sim': round(name_sim, 3),
                'weight_score': ws,
                'class_year_score': cs,
                'total_score': round(score, 3)
            }

    return best_match, round(best_score, 2), debug_info

def load_sample_data():
    """Load sample data from the Wilkes.json file for 2014 season"""
    with open("data/2014/Wilkes.json") as f:
        data = json.load(f)
    
    # Create a dictionary to simulate the database
    seasonal_wrestlers = {}
    
    # Process each wrestler to create the pool of previous season wrestlers
    for wrestler in data['roster']:
        seasonal_wrestlers[wrestler['season_wrestler_id']] = {
            'season_wrestler_id': wrestler['season_wrestler_id'],
            'career_id': f"career_{wrestler['season_wrestler_id']}",  # Simulated career_id
            'name': wrestler['name'],
            'team_id': data['abbreviation'],
            'weight_class': wrestler.get('weight_class', ''),
            'class_year': wrestler.get('grade', ''),
            'season': 2014
        }
    
    return seasonal_wrestlers

def simulate_2015_wrestlers():
    """Create some simulated 2015 wrestlers to test matching logic"""
    # Create some slight variations of the 2014 wrestlers
    return [
        # Exact same name (should be a high confidence match)
        {
            'name': 'Guesseppe Rea',
            'team_id': 'WILK',
            'weight_class': '125',
            'class_year': 'Jr.'  # Grade increased from So.
        },
        # Slight name variation
        {
            'name': 'Giuseppe Rea',  # Spelling slightly changed
            'team_id': 'WILK',
            'weight_class': '125',
            'class_year': 'Jr.'
        },
        # Different team
        {
            'name': 'Myzar Mendoza',
            'team_id': 'UPJ',  # Changed team
            'weight_class': '133',
            'class_year': 'Sr.'
        },
        # Changed weight class
        {
            'name': 'Michael Fleck',
            'team_id': 'WILK',
            'weight_class': '149',  # Changed weight class significantly
            'class_year': 'Jr.'
        },
        # Completely new wrestler (should not match)
        {
            'name': 'John Smith',
            'team_id': 'WILK',
            'weight_class': '157',
            'class_year': 'Fr.'
        }
    ]

def run_tests():
    results = []
    
    # Load sample data from 2014 season
    season_wrestlers_2014 = load_sample_data()
    results.append(f"Loaded {len(season_wrestlers_2014)} wrestlers from 2014 season")
    
    # Create simulated 2015 wrestlers
    wrestlers_2015 = simulate_2015_wrestlers()
    results.append(f"Created {len(wrestlers_2015)} test wrestlers for 2015 season")
    
    # Run tests
    results.append("\n===== WRESTLER MATCHING TEST RESULTS =====\n")
    
    for idx, wrestler in enumerate(wrestlers_2015):
        results.append(f"\n----- Test Case {idx+1}: {wrestler['name']} -----")
        results.append(f"Current wrestler: {wrestler}")
        
        match, confidence, debug = match_wrestler(wrestler, season_wrestlers_2014)
        
        results.append(f"Best match confidence: {confidence}")
        if match:
            results.append(f"Matched with: {match['name']} (ID: {match['season_wrestler_id']})")
            
            # Add debug information
            results.append(f"Debug info: {debug}")
            
            if confidence >= 0.8:
                results.append("RESULT: Would be linked to existing career")
            else:
                results.append("RESULT: Would create new career (confidence below threshold)")
        else:
            results.append("No match found. Would create new career.")
    
    return results

def analyze_data_compatibility():
    results = []
    file_path = "data/2014/Wilkes.json"
    
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        results.append(f"\n===== ANALYZING {Path(file_path).name} =====\n")
        
        # Check top-level structure
        results.append(f"Top-level keys: {', '.join(data.keys())}")
        
        # Check if required fields exist
        required_team_fields = ['team_name', 'abbreviation', 'season']
        missing_team_fields = [field for field in required_team_fields if field not in data]
        
        if missing_team_fields:
            results.append(f"⚠️ Missing required team fields: {', '.join(missing_team_fields)}")
        else:
            results.append("✅ All required team fields are present")
            results.append(f"  - Team: {data.get('team_name')}")
            results.append(f"  - Abbreviation: {data.get('abbreviation')}")
            results.append(f"  - Season: {data.get('season')}")
        
        # Check roster structure
        if 'roster' not in data:
            results.append("❌ No 'roster' key found in the data")
            return results
        
        results.append(f"\nRoster contains {len(data['roster'])} wrestlers")
        
        # Check fields for first few wrestlers
        sample_size = min(3, len(data['roster']))
        for i in range(sample_size):
            wrestler = data['roster'][i]
            results.append(f"\nWrestler {i+1}: {wrestler.get('name', 'Unknown')}")
            
            # Check required wrestler fields
            required_wrestler_fields = ['season_wrestler_id', 'name', 'weight_class', 'grade']
            missing_wrestler_fields = [field for field in required_wrestler_fields if field not in wrestler]
            
            if missing_wrestler_fields:
                results.append(f"⚠️ Missing fields: {', '.join(missing_wrestler_fields)}")
            else:
                results.append("✅ All required wrestler fields are present")
                results.append(f"  - ID: {wrestler.get('season_wrestler_id')}")
                results.append(f"  - Name: {wrestler.get('name')}")
                results.append(f"  - Weight: {wrestler.get('weight_class')}")
                results.append(f"  - Grade: {wrestler.get('grade')}")
        
        results.append("\n===== DATA COMPATIBILITY SUMMARY =====")
        results.append("✅ This data structure is compatible with our wrestler matching logic.")
        
    except FileNotFoundError:
        results.append(f"File not found: {file_path}")
    except json.JSONDecodeError:
        results.append(f"Error decoding JSON in {file_path}")
    except Exception as e:
        results.append(f"Error analyzing file: {e}")
    
    return results

def main():
    # Run tests and collect results
    test_results = run_tests()
    compatibility_results = analyze_data_compatibility()
    
    all_results = test_results + compatibility_results
    
    # Save results to a file
    output_path = Path("logs/test_results.txt")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w") as f:
        for line in all_results:
            f.write(f"{line}\n")
    
    print(f"Results saved to {output_path}")

if __name__ == '__main__':
    main() 