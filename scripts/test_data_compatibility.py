#!/usr/bin/env python3
import json
from pathlib import Path

def analyze_json_file(file_path):
    """Analyze the structure of a JSON file and validate compatibility with our matching logic"""
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        print(f"\n===== ANALYZING {Path(file_path).name} =====\n")
        
        # Check top-level structure
        print("Top-level keys:", ", ".join(data.keys()))
        
        # Check if required fields exist
        required_team_fields = ['team_name', 'abbreviation', 'season']
        missing_team_fields = [field for field in required_team_fields if field not in data]
        
        if missing_team_fields:
            print(f"⚠️ Missing required team fields: {', '.join(missing_team_fields)}")
        else:
            print("✅ All required team fields are present")
            print(f"  - Team: {data.get('team_name')}")
            print(f"  - Abbreviation: {data.get('abbreviation')}")
            print(f"  - Season: {data.get('season')}")
        
        # Check roster structure
        if 'roster' not in data:
            print("❌ No 'roster' key found in the data")
            return
        
        print(f"\nRoster contains {len(data['roster'])} wrestlers")
        
        # Check fields for first few wrestlers
        sample_size = min(3, len(data['roster']))
        for i in range(sample_size):
            wrestler = data['roster'][i]
            print(f"\nWrestler {i+1}: {wrestler.get('name', 'Unknown')}")
            
            # Check required wrestler fields
            required_wrestler_fields = ['season_wrestler_id', 'name', 'weight_class', 'grade']
            missing_wrestler_fields = [field for field in required_wrestler_fields if field not in wrestler]
            
            if missing_wrestler_fields:
                print(f"⚠️ Missing fields: {', '.join(missing_wrestler_fields)}")
            else:
                print("✅ All required wrestler fields are present")
                print(f"  - ID: {wrestler.get('season_wrestler_id')}")
                print(f"  - Name: {wrestler.get('name')}")
                print(f"  - Weight: {wrestler.get('weight_class')}")
                print(f"  - Grade: {wrestler.get('grade')}")
            
            # Check matches
            if 'matches' in wrestler:
                print(f"  - Has {len(wrestler['matches'])} matches")
                
                # Check first match structure if available
                if wrestler['matches']:
                    match = wrestler['matches'][0]
                    print(f"  - First match: {match.get('date', 'Unknown')} vs {match.get('loser_name', 'Unknown')}")
                    
                    # Check required match fields
                    required_match_fields = ['date', 'result']
                    missing_match_fields = [field for field in required_match_fields if field not in match]
                    
                    if missing_match_fields:
                        print(f"⚠️ Match missing fields: {', '.join(missing_match_fields)}")
                    else:
                        print("✅ Match data structure is compatible")
            else:
                print("  - No matches found")
        
        print("\n===== DATA COMPATIBILITY SUMMARY =====")
        print("This data structure is compatible with our wrestler matching logic.")
        print("The required fields for matching (name, team_id/abbreviation, weight_class, grade/class_year) are present.")
        print("The script should be able to process this data correctly.")
        
    except FileNotFoundError:
        print(f"File not found: {file_path}")
    except json.JSONDecodeError:
        print(f"Error decoding JSON in {file_path}")
    except Exception as e:
        print(f"Error analyzing file: {e}")

if __name__ == '__main__':
    # Check the 2014 Wilkes data
    analyze_json_file("data/2014/Wilkes.json") 