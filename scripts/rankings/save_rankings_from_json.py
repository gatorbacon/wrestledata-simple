#!/usr/bin/env python3
"""
Save rankings from downloaded JSON files to the rankings directory.

After editing rankings in the HTML matrix and downloading the JSON file,
use this script to save it to the proper location.
"""

import json
import shutil
from pathlib import Path
from typing import Dict


def save_rankings_file(json_file: Path, season: int, output_dir: str = "mt/rankings_data") -> Path:
    """
    Save a rankings JSON file to the proper location.
    
    Args:
        json_file: Path to downloaded JSON file
        season: Season year
        output_dir: Directory to save rankings
        
    Returns:
        Path to saved file
    """
    # Load the JSON file
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Validate structure
    if 'weight_class' not in data or 'rankings' not in data:
        raise ValueError("Invalid rankings JSON structure. Expected 'weight_class' and 'rankings' keys.")
    
    weight_class = data['weight_class']
    
    # Create output directory
    output_path = Path(output_dir) / str(season)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Save to proper location
    rankings_file = output_path / f"rankings_{weight_class}.json"
    
    with open(rankings_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    
    return rankings_file


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Save rankings from downloaded JSON file to rankings directory'
    )
    parser.add_argument('json_file', type=Path, help='Path to downloaded rankings JSON file')
    parser.add_argument('-season', type=int, help='Season year (if not in JSON file)')
    parser.add_argument('-output-dir', default='mt/rankings_data', help='Directory to save rankings')
    args = parser.parse_args()
    
    # Load JSON to get season if not provided
    with open(args.json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    season = args.season or data.get('season')
    if not season:
        raise ValueError("Season not found in JSON file and not provided via -season argument")
    
    saved_file = save_rankings_file(args.json_file, season, args.output_dir)
    print(f"Saved rankings to: {saved_file}")
    print(f"  Weight class: {data['weight_class']}")
    print(f"  Season: {season}")
    print(f"  Wrestlers ranked: {len(data['rankings'])}")

