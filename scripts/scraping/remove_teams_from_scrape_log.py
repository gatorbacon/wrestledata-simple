#!/usr/bin/env python3
"""
Remove specific teams from the scrape log so they can be re-scraped.

Usage:
    python scripts/scraping/remove_teams_from_scrape_log.py --season 2024 --gender boys --teams "Great Crossing" "Oldham County"
"""

import json
import argparse
from pathlib import Path


def remove_teams_from_log(season: int, gender: str, team_names: list):
    """Remove teams from the scrape log."""
    # Determine log file path
    if gender:
        log_file = Path(f"mt/logs/hs_ky_boys/scrape_log_{season}.json")
    else:
        log_file = Path(f"mt/logs/scrape_log_{season}.json")
    
    if not log_file.exists():
        print(f"❌ Log file not found: {log_file}")
        return False
    
    # Load log
    with open(log_file, 'r') as f:
        log_data = json.load(f)
    
    teams_scraped = log_data.get('teams_scraped', [])
    original_count = len(teams_scraped)
    
    print(f"Original teams in log: {original_count}")
    
    # Remove teams (case-insensitive matching)
    removed = []
    for team_name in team_names:
        # Find exact or partial matches
        matches = [t for t in teams_scraped if team_name.lower() in t.lower() or t.lower() in team_name.lower()]
        for match in matches:
            if match in teams_scraped:
                teams_scraped.remove(match)
                removed.append(match)
                print(f"  Removed: {match}")
    
    if not removed:
        print(f"⚠️  No teams removed. Check team names:")
        print(f"   Looking for: {team_names}")
        print(f"   Available teams (first 10): {teams_scraped[:10]}")
        return False
    
    # Update log
    log_data['teams_scraped'] = teams_scraped
    
    # Save log
    with open(log_file, 'w') as f:
        json.dump(log_data, f, indent=2)
    
    print(f"\n✅ Removed {len(removed)} teams from log")
    print(f"   Teams remaining: {len(teams_scraped)}")
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Remove teams from scrape log to allow re-scraping'
    )
    parser.add_argument(
        '--season',
        type=int,
        required=True,
        help='Season year'
    )
    parser.add_argument(
        '--gender',
        type=str,
        choices=['boys', 'girls'],
        help='Gender (required for HS)'
    )
    parser.add_argument(
        '--teams',
        nargs='+',
        required=True,
        help='Team names to remove (space-separated)'
    )
    
    args = parser.parse_args()
    
    print(f"\n{'='*60}")
    print("REMOVE TEAMS FROM SCRAPE LOG")
    print(f"{'='*60}")
    print(f"Season: {args.season}")
    print(f"Gender: {args.gender}")
    print(f"Teams to remove: {args.teams}")
    print(f"{'='*60}\n")
    
    success = remove_teams_from_log(args.season, args.gender, args.teams)
    
    if success:
        print(f"\n✅ Teams removed. You can now re-scrape them.")
        print(f"\nNext steps:")
        print(f"1. Re-scrape the teams:")
        print(f"   python wrestle_scraper_raw_mt_locked.py -season {args.season} -league hs -state ky -gender {args.gender}")
        print(f"2. Re-run season accomplishments:")
        print(f"   python scripts/season_accomplishments/generate_season_accomplishments.py --season {args.season} --gender {args.gender}")
        print(f"3. Re-run state placement update:")
        print(f"   python scripts/season_accomplishments/update_2024_state_placements.py")
        return 0
    else:
        return 1


if __name__ == '__main__':
    exit(main())

