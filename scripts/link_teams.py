#!/usr/bin/env python3
"""
Team Linking Script

This script creates and maintains a universal team list by linking teams across seasons
and governing bodies. It starts with the most recent season as the base and works
backwards, using fuzzy matching to handle team name changes and governing body changes.
"""

import json
import os
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Set
from difflib import SequenceMatcher
from datetime import datetime

# Configuration
DATA_DIR = Path("data")
TEAM_LISTS_DIR = DATA_DIR / "team_lists"
UNIVERSAL_TEAMS_FILE = TEAM_LISTS_DIR / "universal_teams.json"

# Ensure directories exist
TEAM_LISTS_DIR.mkdir(exist_ok=True)

class TeamLinker:
    def __init__(self, season_year: int, is_base_year: bool = False, ignore_abbreviation: bool = False):
        self.season_year = season_year
        self.is_base_year = is_base_year
        self.ignore_abbreviation = ignore_abbreviation
        self.universal_teams = self._load_universal_teams()
        self.governing_bodies = ["NCAA", "NAIA", "NJCAA", "CCC", "NCWA"]
        self.team_counter = 0  # Add counter for team IDs

    def _load_universal_teams(self) -> Dict:
        """Load the universal team list if it exists, otherwise return empty dict."""
        if UNIVERSAL_TEAMS_FILE.exists():
            with open(UNIVERSAL_TEAMS_FILE, 'r') as f:
                return json.load(f)
        return {}

    def _save_universal_teams(self):
        """Save the universal team list to file."""
        with open(UNIVERSAL_TEAMS_FILE, 'w') as f:
            json.dump(self.universal_teams, f, indent=2)

    def _load_season_teams(self) -> List[Dict]:
        """Load all team lists for the current season."""
        season_teams = []
        season_dir = TEAM_LISTS_DIR / str(self.season_year)
        
        if not season_dir.exists():
            print(f"No team lists found for season {self.season_year}")
            return season_teams

        print(f"Loading teams from {season_dir}")
        for governing_body in self.governing_bodies:
            team_file = season_dir / f"{governing_body.lower()}_teams.json"
            if team_file.exists():
                print(f"Loading {governing_body} teams from {team_file}")
                with open(team_file, 'r') as f:
                    teams = json.load(f)
                    print(f"Found {len(teams)} teams in {governing_body}")
                    # Add season and governing body info to each team
                    for team in teams:
                        team['season'] = self.season_year
                        team['governing_body'] = governing_body
                    season_teams.extend(teams)
            else:
                print(f"No team file found for {governing_body}")
        
        print(f"Total teams loaded: {len(season_teams)}")
        return season_teams

    def _calculate_similarity(self, team1: Dict, team2: Dict) -> float:
        """Calculate similarity score between two teams based on name, abbreviation, and state."""
        # Get the most recent season's data for team2
        most_recent_season = max(team2['seasons'], key=lambda x: x['year'])
        
        name_similarity = SequenceMatcher(None, team1['name'].lower(), most_recent_season['name'].lower()).ratio()
        abbr_similarity = SequenceMatcher(None, team1['abbreviation'].lower(), most_recent_season['abbreviation'].lower()).ratio()
        state_similarity = 1.0 if team1['state'] == team2['state'] else 0.0
        
        # Weight the similarities (name is most important)
        return (name_similarity * 0.6) + (abbr_similarity * 0.3) + (state_similarity * 0.1)

    def _find_exact_match(self, team: Dict) -> Optional[str]:
        """Find an exact match for a team in the universal list."""
        for team_id, universal_team in self.universal_teams.items():
            # Check for exact match with any season's data - all fields must match
            for season in universal_team['seasons']:
                # Base match conditions
                name_match = team['name'] == season['name']
                state_match = team['state'] == universal_team['state']
                gov_body_match = team['governing_body'] == season['governing_body']
                
                # Only check abbreviation if not ignoring it
                abbr_match = True if self.ignore_abbreviation else team['abbreviation'] == season['abbreviation']
                
                if (name_match and state_match and gov_body_match and abbr_match):
                    # If we found an exact match, check if this specific season already exists
                    if any(s['year'] == team['season'] and 
                          s['governing_body'] == team['governing_body']
                          for s in universal_team['seasons']):
                        print(f"Team {team['name']} already exists for {team['season']} {team['governing_body']}")
                        return None  # Skip this team as it's already processed
                    
                    return team_id
        return False  # No match found, should try fuzzy matching

    def _find_fuzzy_matches(self, team: Dict, threshold: float = 0.6) -> List[Dict]:
        """Find fuzzy matches for a team in the universal list."""
        matches = []
        for team_id, universal_team in self.universal_teams.items():
            # Calculate similarity with the team's data
            similarity = self._calculate_similarity(team, universal_team)
            if similarity >= threshold:
                # Get the most recent season info for display
                most_recent_season = max(universal_team['seasons'], key=lambda x: x['year'])
                
                # Only skip if this exact team entry already has this season
                if any(season['year'] == team['season'] and 
                      season['governing_body'] == team['governing_body'] and
                      season['name'] == team['name']
                      for season in universal_team['seasons']):
                    continue
                
                matches.append({
                    'team_id': team_id,
                    'similarity': similarity,
                    'universal_team': universal_team,
                    'most_recent_season': most_recent_season
                })
        
        # Sort by similarity score
        matches.sort(key=lambda x: x['similarity'], reverse=True)
        return matches[:20]  # Return top 20 matches

    def _generate_team_id(self, team: Dict) -> str:
        """Generate a unique team ID based on abbreviation and state."""
        base_id = team['abbreviation'].upper()
        state = team['state'].upper()
        
        # First try just the abbreviation
        if base_id not in self.universal_teams:
            return base_id
            
        # Then try abbreviation_state
        team_id = f"{base_id}_{state}"
        if team_id not in self.universal_teams:
            return team_id
            
        # If that exists too, add a number
        counter = 1
        while f"{team_id}{counter}" in self.universal_teams:
            counter += 1
        return f"{team_id}{counter}"

    def _create_new_team_entry(self, team: Dict) -> str:
        """Create a new entry in the universal team list."""
        # Generate a unique ID based on abbreviation and state
        team_id = self._generate_team_id(team)
        
        print(f"Creating new team entry for {team['name']} ({team['governing_body']}) with ID {team_id}")
        
        # Create the universal team entry
        self.universal_teams[team_id] = {
            'universal_name': team['name'],  # Most recent name
            'state': team['state'],
            'seasons': [{
                'name': team['name'],
                'year': team['season'],
                'abbreviation': team['abbreviation'],
                'governing_body': team['governing_body'],
                'division': team.get('division', 'Unknown')
            }]
        }
        
        return team_id

    def _add_season_to_team(self, team_id: str, team: Dict):
        """Add a season to an existing team in the universal list."""
        season_info = {
            'name': team['name'],
            'year': team['season'],
            'abbreviation': team['abbreviation'],
            'governing_body': team['governing_body'],
            'division': team.get('division', 'Unknown')
        }
        
        # Check if this season already exists for this team
        for season in self.universal_teams[team_id]['seasons']:
            if season['year'] == team['season'] and season['governing_body'] == team['governing_body']:
                print(f"Season {team['season']} {team['governing_body']} already exists for {team['name']}")
                return  # Season already exists
        
        # Add the new season
        self.universal_teams[team_id]['seasons'].append(season_info)
        print(f"Added season {team['season']} {team['governing_body']} to {team['name']}")
        
        # Update universal_name to the most recent name
        self.universal_teams[team_id]['universal_name'] = team['name']
        
        # Save after each addition to ensure changes are persisted
        self._save_universal_teams()

    def _search_teams(self, search_term: str) -> List[Dict]:
        """Search for teams containing the search term."""
        matches = []
        search_term = search_term.lower()
        for team_id, universal_team in self.universal_teams.items():
            # Search in universal name and all season names
            if (search_term in universal_team['universal_name'].lower() or
                any(search_term in season['name'].lower() for season in universal_team['seasons'])):
                most_recent_season = max(universal_team['seasons'], key=lambda x: x['year'])
                matches.append({
                    'team_id': team_id,
                    'similarity': 1.0,  # Not really used for search results
                    'universal_team': universal_team,
                    'most_recent_season': most_recent_season
                })
        return matches

    def _handle_fuzzy_matches(self, team: Dict, fuzzy_matches: List[Dict]) -> Optional[str]:
        """Handle fuzzy matches by getting user input."""
        print(f"\nNo exact match found for {team['name']}")
        print("\nCurrent team:")
        print(f"  Name: {team['name']}")
        print(f"  State: {team['state']}")
        print(f"  Abbreviation: {team['abbreviation']}")
        print(f"  Governing Body: {team['governing_body']}")
        
        while True:
            # Show fuzzy matches or search results
            print("\nTop matches:")
            for i, match in enumerate(fuzzy_matches, 1):
                most_recent = match['most_recent_season']
                universal_team = match['universal_team']
                print(f"\n{i}. Similarity: {match['similarity']:.2f}")
                print(f"   Name: {most_recent['name']}")
                print(f"   State: {universal_team['state']}")
                print(f"   Abbreviation: {most_recent['abbreviation']}")
                print(f"   Most recent season: {most_recent['year']} {most_recent['governing_body']}")
                print(f"   Team ID: {match['team_id']}")
                print(f"   All seasons: {[s['year'] for s in universal_team['seasons']]}")
            
            try:
                print("\nOptions:")
                print("  Enter a number (1-20) to select a match")
                print("  Enter 'n' to create a new entry")
                print("  Enter 's' to skip this team")
                print("  Enter 'search <term>' to search for teams")
                choice = input("Your choice: ").strip().lower()
                
                if choice == 'n':
                    return self._create_new_team_entry(team)
                elif choice == 's':
                    return None
                elif choice.startswith('search '):
                    search_term = choice[7:].strip()  # Remove 'search ' prefix
                    if search_term:
                        print(f"\nSearching for '{search_term}'...")
                        fuzzy_matches = self._search_teams(search_term)
                        if not fuzzy_matches:
                            print("No matches found")
                        continue
                    else:
                        print("Please provide a search term")
                else:
                    try:
                        index = int(choice) - 1
                        if 0 <= index < len(fuzzy_matches):
                            match = fuzzy_matches[index]
                            self._add_season_to_team(match['team_id'], team)
                            return match['team_id']
                    except ValueError:
                        pass
                
                print("Invalid choice. Please try again.")
            except KeyboardInterrupt:
                print("\nOperation cancelled by user.")
                return None

    def process_season(self):
        """Process all teams for the current season."""
        season_teams = self._load_season_teams()
        if not season_teams:
            print(f"No teams found for season {self.season_year}")
            return

        print(f"\nProcessing {len(season_teams)} teams for season {self.season_year}...")
        
        if self.is_base_year:
            print("This is the base year - creating new universal team list...")
            for i, team in enumerate(season_teams, 1):
                print(f"Processing team {i}/{len(season_teams)}: {team['name']}")
                self._create_new_team_entry(team)
        else:
            print("Looking for matches in existing universal team list...")
            for i, team in enumerate(season_teams, 1):
                print(f"\nProcessing team {i}/{len(season_teams)}: {team['name']}")
                
                # First try to find an exact match
                team_id = self._find_exact_match(team)
                
                if team_id is None:  # Team already exists in this season
                    print(f"Skipping {team['name']} - already exists in {team['season']} {team['governing_body']}")
                    continue
                elif team_id:  # Found a match in a different season
                    print(f"Found exact match for {team['name']} - adding to existing team")
                    self._add_season_to_team(team_id, team)
                else:  # No exact match found, try fuzzy matching
                    print(f"No exact match found for {team['name']} - checking fuzzy matches")
                    fuzzy_matches = self._find_fuzzy_matches(team)
                    
                    if fuzzy_matches:
                        team_id = self._handle_fuzzy_matches(team, fuzzy_matches)
                        if team_id:
                            print(f"Added {team['name']} to existing team {team_id}")
                        else:
                            print(f"Skipped {team['name']}")
                    else:
                        print(f"No matches found for {team['name']} - creating new entry")
                        self._create_new_team_entry(team)
                
                # Save periodically
                if i % 10 == 0:
                    self._save_universal_teams()
        
        # Save the final updated universal team list
        self._save_universal_teams()
        print(f"\nUniversal team list updated with {len(self.universal_teams)} teams")

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Link teams across seasons and governing bodies.')
    parser.add_argument('-season', type=int, required=True, help='Season year to process')
    parser.add_argument('-baseyear', action='store_true', help='Flag this season as the base year')
    parser.add_argument('-igabbr', action='store_true', help='Ignore abbreviation when finding exact matches')
    return parser.parse_args()

def main():
    """Main function."""
    args = parse_args()
    linker = TeamLinker(args.season, args.baseyear, args.igabbr)
    linker.process_season()

if __name__ == "__main__":
    main() 