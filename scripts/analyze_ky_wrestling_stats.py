#!/usr/bin/env python3
"""
Comprehensive analysis of KY wrestling statistics.

This script analyzes:
1. Total number of matches for each gender at each weight class
2. Total number of KY competitors at each gender and each weight class
3. Total number of teams represented for each gender
4. Total number of wrestlers per team for each gender
5. Line chart showing matches by weight class for both genders
"""

import json
import argparse
from pathlib import Path
from collections import defaultdict
from typing import Dict, Set, Tuple

# Optional imports for charting
try:
    import matplotlib.pyplot as plt
    import numpy as np
    CHART_AVAILABLE = True
except ImportError:
    CHART_AVAILABLE = False

# Standard weight classes
BOYS_WEIGHTS = [106, 113, 120, 126, 132, 138, 144, 150, 157, 165, 175, 190, 215, 285]
GIRLS_WEIGHTS = [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235]


def is_ky_wrestler(wrestler_id: str) -> bool:
    """Check if a wrestler ID belongs to a KY wrestler (not out-of-state)."""
    if not wrestler_id:
        return False
    # Out-of-state wrestlers have IDs starting with "OUTSTATE_"
    return not wrestler_id.startswith("OUTSTATE_")


def analyze_gender_with_match_filter(season: int, gender: str, min_matches: int, data_dir: str = "mt/rankings_data") -> Dict[int, int]:
    """
    Analyze wrestler counts by weight class, filtering to only wrestlers with at least min_matches.
    
    Returns:
        Dictionary mapping weight_class (int) -> count of wrestlers with >= min_matches
    """
    state_lower = "ky"
    data_path = Path(data_dir) / f"hs_{state_lower}_{gender}" / str(season)
    
    if not data_path.exists():
        raise FileNotFoundError(f"Data directory not found: {data_path}")
    
    # Track wrestlers by weight class (deduplicate by wrestler ID)
    wrestlers_by_weight: Dict[int, Set[str]] = defaultdict(set)
    
    # Load all weight class files
    weight_class_files = sorted(data_path.glob("weight_class_*.json"))
    
    for wc_file in weight_class_files:
        try:
            with wc_file.open("r", encoding="utf-8") as f:
                wc_data = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load {wc_file.name}: {e}")
            continue
        
        # Process wrestlers
        wrestlers = wc_data.get("wrestlers", {})
        for wrestler_id, wrestler_info in wrestlers.items():
            # Only count KY wrestlers
            if not is_ky_wrestler(wrestler_id):
                continue
            
            # Check match count
            matches_count = wrestler_info.get("matches_count", 0)
            if matches_count < min_matches:
                continue
            
            # Get weight class
            weight_class = wrestler_info.get("weight_class", "")
            try:
                weight_int = int(weight_class)
                wrestlers_by_weight[weight_int].add(wrestler_id)
            except (ValueError, TypeError):
                # Skip if weight class can't be parsed
                pass
    
    # Convert sets to counts
    return {weight: len(wrestlers) for weight, wrestlers in wrestlers_by_weight.items()}


def analyze_gender(season: int, gender: str, data_dir: str = "mt/rankings_data") -> Dict:
    """
    Analyze all statistics for a given gender.
    
    Returns:
        Dictionary with:
        - matches_by_weight: Dict[int, int] - match counts by weight class
        - competitors_by_weight: Dict[int, int] - KY competitor counts by weight class
        - total_teams: int - total number of unique teams
        - wrestlers_by_team: Dict[str, int] - wrestler counts per team
    """
    state_lower = "ky"
    data_path = Path(data_dir) / f"hs_{state_lower}_{gender}" / str(season)
    
    if not data_path.exists():
        raise FileNotFoundError(f"Data directory not found: {data_path}")
    
    # Track all unique matches by (w1_id, w2_id, date, weight_class)
    seen_matches: Set[tuple] = set()
    matches_by_weight: Dict[int, int] = defaultdict(int)
    
    # Track KY competitors by weight class
    competitors_by_weight: Dict[int, Set[str]] = defaultdict(set)
    
    # Track teams and wrestlers per team
    teams: Set[str] = set()
    wrestlers_by_team: Dict[str, Set[str]] = defaultdict(set)
    
    # Load all weight class files
    weight_class_files = sorted(data_path.glob("weight_class_*.json"))
    
    print(f"Loading data from {len(weight_class_files)} weight class files...")
    
    for wc_file in weight_class_files:
        try:
            with wc_file.open("r", encoding="utf-8") as f:
                wc_data = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load {wc_file.name}: {e}")
            continue
        
        # Process wrestlers
        wrestlers = wc_data.get("wrestlers", {})
        for wrestler_id, wrestler_info in wrestlers.items():
            # Only count KY wrestlers
            if not is_ky_wrestler(wrestler_id):
                continue
            
            team = wrestler_info.get("team", "Unknown")
            weight_class = wrestler_info.get("weight_class", "")
            
            # Track team
            if team and team != "Unknown":
                teams.add(team)
                wrestlers_by_team[team].add(wrestler_id)
            
            # Track competitor by weight class
            try:
                weight_int = int(weight_class)
                competitors_by_weight[weight_int].add(wrestler_id)
            except (ValueError, TypeError):
                # Skip if weight class can't be parsed
                pass
        
        # Process matches
        matches = wc_data.get("matches", [])
        for match in matches:
            w1_id = match.get("wrestler1_id", "")
            w2_id = match.get("wrestler2_id", "")
            date = match.get("date", "")
            match_weight = match.get("weight_class", "")
            
            # Skip if missing required fields
            if not w1_id or not w2_id or not date or not match_weight:
                continue
            
            # Check if at least one wrestler is from KY
            if not (is_ky_wrestler(w1_id) or is_ky_wrestler(w2_id)):
                continue
            
            # Create unique match key (normalize wrestler IDs)
            w1_normalized = min(w1_id, w2_id)
            w2_normalized = max(w1_id, w2_id)
            match_key = (w1_normalized, w2_normalized, date, str(match_weight))
            
            # Only count each match once
            if match_key in seen_matches:
                continue
            
            seen_matches.add(match_key)
            
            # Parse weight class as integer
            try:
                weight_int = int(match_weight)
                matches_by_weight[weight_int] += 1
            except (ValueError, TypeError):
                # Skip if weight class can't be parsed
                continue
    
    # Convert sets to counts
    competitors_by_weight_count = {
        weight: len(competitors) 
        for weight, competitors in competitors_by_weight.items()
    }
    
    wrestlers_by_team_count = {
        team: len(wrestlers) 
        for team, wrestlers in wrestlers_by_team.items()
    }
    
    return {
        "matches_by_weight": dict(matches_by_weight),
        "competitors_by_weight": competitors_by_weight_count,
        "total_teams": len(teams),
        "wrestlers_by_team": wrestlers_by_team_count,
    }


def print_section(title: str):
    """Print a section header."""
    print(f"\n{'=' * 80}")
    print(f"{title}")
    print(f"{'=' * 80}")


def print_matches_by_weight(matches_by_weight: Dict[int, int], gender: str, season: int):
    """Print match counts by weight class."""
    if gender == "boys":
        standard_weights = BOYS_WEIGHTS
        title = "BOYS"
    else:
        standard_weights = GIRLS_WEIGHTS
        title = "GIRLS"
    
    print_section(f"1. MATCH COUNTS BY WEIGHT CLASS - {title.upper()} - SEASON {season}")
    print(f"\n{'Weight Class':<15} {'Match Count':<15}")
    print("-" * 30)
    
    total_matches = 0
    
    for weight in standard_weights:
        count = matches_by_weight.get(weight, 0)
        total_matches += count
        print(f"{weight:<15} {count:<15}")
    
    print("-" * 30)
    print(f"{'TOTAL':<15} {total_matches:<15}")


def print_competitors_by_weight(competitors_by_weight: Dict[int, int], gender: str, season: int):
    """Print competitor counts by weight class."""
    if gender == "boys":
        standard_weights = BOYS_WEIGHTS
        title = "BOYS"
    else:
        standard_weights = GIRLS_WEIGHTS
        title = "GIRLS"
    
    print_section(f"2. KY COMPETITORS BY WEIGHT CLASS - {title.upper()} - SEASON {season}")
    print(f"\n{'Weight Class':<15} {'Competitors':<15}")
    print("-" * 30)
    
    total_competitors = 0
    
    for weight in standard_weights:
        count = competitors_by_weight.get(weight, 0)
        total_competitors += count
        print(f"{weight:<15} {count:<15}")
    
    print("-" * 30)
    print(f"{'TOTAL':<15} {total_competitors:<15}")


def print_teams_summary(total_teams: int, gender: str, season: int):
    """Print total teams summary."""
    if gender == "boys":
        title = "BOYS"
    else:
        title = "GIRLS"
    
    print_section(f"3. TOTAL TEAMS - {title.upper()} - SEASON {season}")
    print(f"\nTotal number of teams: {total_teams}")


def print_wrestlers_by_team(wrestlers_by_team: Dict[str, int], gender: str, season: int, top_n: int = 20):
    """Print wrestlers per team."""
    if gender == "boys":
        title = "BOYS"
    else:
        title = "GIRLS"
    
    print_section(f"4. WRESTLERS PER TEAM - {title.upper()} - SEASON {season}")
    
    # Sort teams by wrestler count (descending)
    sorted_teams = sorted(wrestlers_by_team.items(), key=lambda x: x[1], reverse=True)
    
    print(f"\n{'Team':<40} {'Wrestlers':<15}")
    print("-" * 55)
    
    total_wrestlers = sum(wrestlers_by_team.values())
    
    # Print top N teams
    for team, count in sorted_teams[:top_n]:
        print(f"{team:<40} {count:<15}")
    
    if len(sorted_teams) > top_n:
        print(f"\n... and {len(sorted_teams) - top_n} more teams")
    
    print("-" * 55)
    print(f"{'TOTAL WRESTLERS':<40} {total_wrestlers:<15}")
    print(f"{'AVERAGE PER TEAM':<40} {total_wrestlers / len(wrestlers_by_team):.1f}" if wrestlers_by_team else f"{'AVERAGE PER TEAM':<40} 0")


def create_match_chart(all_results: Dict, season: int, output_file: str = None):
    """Create a grouped bar chart showing matches by weight class for both genders."""
    if not CHART_AVAILABLE:
        print("Warning: Cannot create chart - matplotlib is required")
        print("Install with: pip install matplotlib")
        return
    
    if "boys" not in all_results or "girls" not in all_results:
        print("Warning: Cannot create chart - need both boys and girls data")
        return
    
    boys_matches = all_results["boys"]["matches_by_weight"]
    girls_matches = all_results["girls"]["matches_by_weight"]
    
    # Get all unique weight classes from both genders, sorted
    all_weights = sorted(set(BOYS_WEIGHTS + GIRLS_WEIGHTS))
    
    # Align data - use 0 for weights not present in a gender
    boys_counts = [boys_matches.get(w, 0) for w in all_weights]
    girls_counts = [girls_matches.get(w, 0) for w in all_weights]
    
    # Create figure - square format for Instagram (1080x1080)
    plt.figure(figsize=(10, 10))
    
    # Set up bar positions
    x = np.arange(len(all_weights))
    width = 0.35  # Width of bars
    
    # Create grouped bars
    bars1 = plt.bar(x - width/2, boys_counts, width, label='Boys', color='#2E86AB', alpha=0.8)
    bars2 = plt.bar(x + width/2, girls_counts, width, label='Girls', color='#A23B72', alpha=0.8)
    
    # Set x-axis
    plt.xlabel('Weight Class (lbs)', fontsize=13, fontweight='bold')
    plt.ylabel('Number of Matches', fontsize=13, fontweight='bold')
    plt.title(f'Matches by Weight Class — Season {season}', fontsize=16, fontweight='bold', pad=15)
    
    # Set x-axis labels
    plt.xticks(x, all_weights, rotation=45, ha='right', fontsize=10)
    
    # Y-axis must start at 0
    plt.ylim(bottom=0)
    plt.yticks(fontsize=10)
    
    # Add legend
    plt.legend(fontsize=12, loc='best', framealpha=0.9)
    
    # Add light gridlines (y-axis only)
    plt.grid(True, axis='y', alpha=0.3, linestyle='--')
    plt.grid(False, axis='x')
    
    # Add value labels on bars (optional, but helpful for readability)
    def add_value_labels(bars):
        for bar in bars:
            height = bar.get_height()
            if height > 0:  # Only label non-zero bars
                plt.text(bar.get_x() + bar.get_width()/2., height,
                        f'{int(height)}',
                        ha='center', va='bottom', fontsize=9)
    
    add_value_labels(bars1)
    add_value_labels(bars2)
    
    plt.tight_layout()
    
    # Save or show chart
    if output_file:
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"\nMatches chart saved to: {output_file}")
    else:
        chart_file = f"matches_by_weight_class_{season}.png"
        plt.savefig(chart_file, dpi=300, bbox_inches='tight')
        print(f"\nMatches chart saved to: {chart_file}")
    
    plt.close()


def create_competitors_chart(all_results: Dict, season: int, output_file: str = None):
    """Create a grouped bar chart showing competitors by weight class for both genders."""
    if not CHART_AVAILABLE:
        print("Warning: Cannot create chart - matplotlib is required")
        print("Install with: pip install matplotlib")
        return
    
    if "boys" not in all_results or "girls" not in all_results:
        print("Warning: Cannot create chart - need both boys and girls data")
        return
    
    boys_competitors = all_results["boys"]["competitors_by_weight"]
    girls_competitors = all_results["girls"]["competitors_by_weight"]
    
    # Get all unique weight classes from both genders, sorted
    all_weights = sorted(set(BOYS_WEIGHTS + GIRLS_WEIGHTS))
    
    # Align data - use 0 for weights not present in a gender
    boys_counts = [boys_competitors.get(w, 0) for w in all_weights]
    girls_counts = [girls_competitors.get(w, 0) for w in all_weights]
    
    # Create figure - square format for Instagram (1080x1080)
    plt.figure(figsize=(10, 10))
    
    # Set up bar positions
    x = np.arange(len(all_weights))
    width = 0.35  # Width of bars
    
    # Create grouped bars
    bars1 = plt.bar(x - width/2, boys_counts, width, label='Boys', color='#2E86AB', alpha=0.8)
    bars2 = plt.bar(x + width/2, girls_counts, width, label='Girls', color='#A23B72', alpha=0.8)
    
    # Set x-axis
    plt.xlabel('Weight Class (lbs)', fontsize=13, fontweight='bold')
    plt.ylabel('Competitors', fontsize=13, fontweight='bold')
    plt.title(f'Competitors by Weight Class — Season {season}', fontsize=16, fontweight='bold', pad=15)
    
    # Set x-axis labels
    plt.xticks(x, all_weights, rotation=45, ha='right', fontsize=10)
    
    # Y-axis must start at 0
    plt.ylim(bottom=0)
    plt.yticks(fontsize=10)
    
    # Add legend
    plt.legend(fontsize=12, loc='best', framealpha=0.9)
    
    # Add light gridlines (y-axis only)
    plt.grid(True, axis='y', alpha=0.3, linestyle='--')
    plt.grid(False, axis='x')
    
    # Add value labels on bars (optional, but helpful for readability)
    def add_value_labels(bars):
        for bar in bars:
            height = bar.get_height()
            if height > 0:  # Only label non-zero bars
                plt.text(bar.get_x() + bar.get_width()/2., height,
                        f'{int(height)}',
                        ha='center', va='bottom', fontsize=9)
    
    add_value_labels(bars1)
    add_value_labels(bars2)
    
    plt.tight_layout()
    
    # Save or show chart
    if output_file:
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"\nCompetitors chart saved to: {output_file}")
    else:
        chart_file = f"competitors_by_weight_class_{season}.png"
        plt.savefig(chart_file, dpi=300, bbox_inches='tight')
        print(f"\nCompetitors chart saved to: {chart_file}")
    
    plt.close()


def create_wrestlers_by_weight_chart(all_results: Dict, season: int, min_matches: int, data_dir: str, output_file: str = None):
    """Create a grouped bar chart showing wrestlers by weight class (with at least min_matches) for both genders."""
    if not CHART_AVAILABLE:
        print("Warning: Cannot create chart - matplotlib is required")
        print("Install with: pip install matplotlib")
        return
    
    if "boys" not in all_results or "girls" not in all_results:
        print("Warning: Cannot create chart - need both boys and girls data")
        return
    
    # Get wrestler counts by weight class (filtered by min_matches)
    boys_wrestlers = analyze_gender_with_match_filter(season, "boys", min_matches, data_dir)
    girls_wrestlers = analyze_gender_with_match_filter(season, "girls", min_matches, data_dir)
    
    # Get all unique weight classes from both genders, sorted
    all_weights = sorted(set(BOYS_WEIGHTS + GIRLS_WEIGHTS))
    
    # Align data - use 0 for weights not present in a gender
    boys_counts = [boys_wrestlers.get(w, 0) for w in all_weights]
    girls_counts = [girls_wrestlers.get(w, 0) for w in all_weights]
    
    # Create figure - square format for Instagram (1080x1080)
    plt.figure(figsize=(10, 10))
    
    # Set up bar positions
    x = np.arange(len(all_weights))
    width = 0.35  # Width of bars
    
    # Create grouped bars
    bars1 = plt.bar(x - width/2, boys_counts, width, label='Boys', color='#2E86AB', alpha=0.8)
    bars2 = plt.bar(x + width/2, girls_counts, width, label='Girls', color='#A23B72', alpha=0.8)
    
    # Set x-axis
    plt.xlabel('Weight Class (lbs)', fontsize=13, fontweight='bold')
    plt.ylabel('Number of Wrestlers', fontsize=13, fontweight='bold')
    plt.title(f'Wrestlers by Weight Class (≥{min_matches} matches) — Season {season}', fontsize=16, fontweight='bold', pad=15)
    
    # Set x-axis labels
    plt.xticks(x, all_weights, rotation=45, ha='right', fontsize=10)
    
    # Y-axis must start at 0
    plt.ylim(bottom=0)
    plt.yticks(fontsize=10)
    
    # Add legend
    plt.legend(fontsize=12, loc='best', framealpha=0.9)
    
    # Add light gridlines (y-axis only)
    plt.grid(True, axis='y', alpha=0.3, linestyle='--')
    plt.grid(False, axis='x')
    
    # Add value labels on bars
    def add_value_labels(bars):
        for bar in bars:
            height = bar.get_height()
            if height > 0:  # Only label non-zero bars
                plt.text(bar.get_x() + bar.get_width()/2., height,
                        f'{int(height)}',
                        ha='center', va='bottom', fontsize=9)
    
    add_value_labels(bars1)
    add_value_labels(bars2)
    
    plt.tight_layout()
    
    # Save or show chart
    if output_file:
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"\nWrestlers chart saved to: {output_file}")
    else:
        chart_file = f"wrestlers_by_weight_class_{season}.png"
        plt.savefig(chart_file, dpi=300, bbox_inches='tight')
        print(f"\nWrestlers chart saved to: {chart_file}")
    
    plt.close()


def main():
    parser = argparse.ArgumentParser(
        description="Comprehensive analysis of KY wrestling statistics"
    )
    parser.add_argument(
        "--season",
        type=int,
        required=True,
        help="Season year (e.g., 2026)",
    )
    parser.add_argument(
        "--gender",
        type=str,
        choices=["boys", "girls", "both"],
        default="both",
        help="Gender: 'boys', 'girls', or 'both' (default: both)",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="mt/rankings_data",
        help="Directory containing weight_class_*.json files (default: mt/rankings_data)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Optional: Output JSON file to save results",
    )
    parser.add_argument(
        "--top-teams",
        type=int,
        default=20,
        help="Number of top teams to show in wrestlers per team section (default: 20)",
    )
    parser.add_argument(
        "--chart",
        type=str,
        help="Optional: Output file for match chart (e.g., chart.png). If not specified, auto-generates filename.",
    )
    parser.add_argument(
        "--no-chart",
        action="store_true",
        help="Skip generating the chart",
    )
    
    args = parser.parse_args()
    
    genders_to_process = []
    if args.gender == "both":
        genders_to_process = ["boys", "girls"]
    else:
        genders_to_process = [args.gender]
    
    all_results = {}
    
    for gender in genders_to_process:
        print(f"\n{'#' * 80}")
        print(f"# ANALYZING {gender.upper()} - SEASON {args.season}")
        print(f"{'#' * 80}")
        
        # Analyze this gender
        results = analyze_gender(args.season, gender, args.data_dir)
        all_results[gender] = results
        
        # Print all sections
        print_matches_by_weight(results["matches_by_weight"], gender, args.season)
        print_competitors_by_weight(results["competitors_by_weight"], gender, args.season)
        print_teams_summary(results["total_teams"], gender, args.season)
        print_wrestlers_by_team(results["wrestlers_by_team"], gender, args.season, args.top_teams)
    
    # Create charts if both genders are available and not disabled
    if not args.no_chart and "boys" in all_results and "girls" in all_results:
        # Create matches chart
        match_chart_file = args.chart if args.chart and args.chart.endswith('.png') else None
        create_match_chart(all_results, args.season, match_chart_file)
        
        # Create competitors chart
        if args.chart:
            # If chart filename provided, create competitors chart with similar name
            competitors_chart_file = args.chart.replace('.png', '_competitors.png') if args.chart.endswith('.png') else f"{args.chart}_competitors.png"
        else:
            competitors_chart_file = None
        create_competitors_chart(all_results, args.season, competitors_chart_file)
        
        # Create wrestlers by weight chart (with at least 5 matches)
        if args.chart:
            wrestlers_chart_file = args.chart.replace('.png', '_wrestlers.png') if args.chart.endswith('.png') else f"{args.chart}_wrestlers.png"
        else:
            wrestlers_chart_file = None
        create_wrestlers_by_weight_chart(all_results, args.season, 5, args.data_dir, wrestlers_chart_file)
    
    # Save to JSON if requested
    if args.output:
        output_data = {
            "season": args.season,
            "results": all_results,
        }
        
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2)
        
        print(f"\n{'=' * 80}")
        print(f"Results saved to: {output_path}")
        print(f"{'=' * 80}")


if __name__ == "__main__":
    main()

