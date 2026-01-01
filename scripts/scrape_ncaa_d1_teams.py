#!/usr/bin/env python3
"""
NCAA D1 Team Scraper

This script scrapes team information from the NCAA wrestling website for NCAA Division I schools only.

It follows the same scraping strategy as wrestle_scraper.py but focuses only on team information
without scraping individual team pages or match data.
"""

import argparse
import boto3
import json
import os
import platform
import random
import re
import time
from boto3.dynamodb.conditions import Attr
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from fake_useragent import UserAgent
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.common.exceptions import TimeoutException

# Configuration
BASE_URL = "https://www.trackwrestling.com"
DATA_DIR = Path("data")
LOGS_DIR = Path("logs")
SCRAPE_LOG_FILE = lambda season: LOGS_DIR / f"scrape_log_{season}.json"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# DynamoDB setup
db = boto3.resource('dynamodb', endpoint_url='http://localhost:8001')
teams_table = db.Table('teams')

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Scrape wrestling team data.')
    parser.add_argument('-teams', type=int, help='Number of teams to scrape. If not provided, scrapes all teams.')
    parser.add_argument('-season', type=int, required=True, help='Season ending year (e.g. 2023 for 2022-23 season)')
    parser.add_argument('-league', type=str, default='ncaa', choices=['ncaa', 'hs'],
                        help='League type: ncaa (default) or hs')
    parser.add_argument('-state', type=str, help='State code (required when league=hs, currently only KY supported)')
    parser.add_argument('-gender', type=str, choices=['boys', 'girls'],
                        help='Gender: boys or girls (required when league=hs)')
    return parser.parse_args()

class WrestlingScraper:
    def __init__(self, max_teams=None, season_year=None, league='ncaa', state=None, gender=None):
        self.ua = UserAgent()
        self.driver = None
        self.wait = None
        self.season_year = season_year
        self.scrape_log = self._load_scrape_log()
        self.max_teams = max_teams
        self.league = league
        self.state = state
        self.gender = gender
        
        # Validate HS parameters
        if self.league == 'hs':
            if not self.state:
                raise ValueError("--state is required when --league=hs")
            # Normalize state to uppercase for comparison
            state_upper = self.state.upper()
            if state_upper != 'KY':
                raise ValueError(f"Only KY is currently supported for HS. Got: {self.state}")
            # Store normalized state
            self.state = state_upper
            if not self.gender:
                raise ValueError("--gender is required when --league=hs")
            if self.gender not in ['boys', 'girls']:
                raise ValueError(f"--gender must be 'boys' or 'girls'. Got: {self.gender}")
        
        # Create season-specific data directory
        self.season_data_dir = DATA_DIR / str(season_year)
        self.season_data_dir.mkdir(exist_ok=True)

    def _load_scrape_log(self) -> Dict:
        """Load or create the scrape log file."""
        if SCRAPE_LOG_FILE(self.season_year).exists():
            with open(SCRAPE_LOG_FILE(self.season_year), 'r') as f:
                return json.load(f)
        return {
            "teams_scraped": [],
            "last_run": None,
            "errors": []
        }

    def _save_scrape_log(self):
        """Save current progress to the scrape log."""
        self.scrape_log["last_run"] = datetime.now().isoformat()
        with open(SCRAPE_LOG_FILE(self.season_year), 'w') as f:
            json.dump(self.scrape_log, f, indent=2)

    def _random_delay(self):
        """Add random delay between requests."""
        time.sleep(random.uniform(0.5, 1.0))

    def _log_error(self, error_type: str, details: str):
        """Log an error with timestamp."""
        error_entry = {
            "type": error_type,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.scrape_log.setdefault("errors", []).append(error_entry)
        self._save_scrape_log()

    def setup_driver(self):
        """Initialize the Selenium WebDriver with appropriate options."""
        try:
            options = webdriver.ChromeOptions()
            options.add_argument(f'user-agent={self.ua.random}')
            # Remove headless mode for debugging
            # options.add_argument('--headless=new')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--start-maximized')
            
            # Let Selenium Manager handle driver installation
            self.driver = webdriver.Chrome(options=options)
            self.wait = WebDriverWait(self.driver, 20)  # Increase wait time
            
        except Exception as e:
            error_msg = f"Failed to setup Chrome driver: {str(e)}"
            self._log_error("driver_setup", error_msg)
            print(f"Error: {error_msg}")
            print("Please make sure Google Chrome is installed.")
            print("You can install it using: brew install --cask google-chrome")
            raise

    def get_season_text(self):
        """Convert season year to possible season text formats."""
        start_year = self.season_year - 1
        short_end = str(self.season_year)[-2:]  # Get last 2 digits
        
        if self.league == 'hs':
            if self.gender == 'boys':
                return [
                    f"{start_year}-{short_end} High School Boys",
                    f"{start_year}-{short_end} HS Boys"
                ]
            else:  # girls
                return [
                    f"{start_year}-{short_end} High School Girls",
                    f"{start_year}-{short_end} HS Girls"
                ]
        else:  # ncaa
            return [
                f"{start_year}-{short_end} College Men",
                f"{start_year}-{short_end} College"
            ]

    def navigate_to_season(self):
        """Navigate to the wrestling season page."""
        try:
            print("Navigating to homepage...")
            self.driver.get(BASE_URL)
            time.sleep(3)
            
            # Print page title and URL for debugging
            print(f"Current URL: {self.driver.current_url}")
            print(f"Page title: {self.driver.title}")
            
            # Click Browse using the correct selector
            print("Attempting to click Browse...")
            browse_btn = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "nav.main-menu li a[href*='subMenu-browse']"))
            )
            browse_btn.click()
            self._random_delay()
            time.sleep(1)

            print("Clicking Seasons...")
            seasons_btn = self.wait.until(
                EC.element_to_be_clickable((By.LINK_TEXT, "Seasons"))
            )
            seasons_btn.click()
            self._random_delay()
            time.sleep(2)

            print("Clicking More Seasons...")
            # Wait for the More Seasons link to be present
            more_seasons_btn = self.wait.until(
                EC.presence_of_element_located((By.LINK_TEXT, "More Seasons"))
            )
            
            # Try to scroll the element into view
            self.driver.execute_script("arguments[0].scrollIntoView(true);", more_seasons_btn)
            time.sleep(1)  # Wait for scroll to complete
            
            # Try regular click first
            try:
                more_seasons_btn.click()
            except Exception as e:
                print(f"Regular click failed, trying JavaScript click: {e}")
                # If regular click fails, try JavaScript click
                self.driver.execute_script("arguments[0].click();", more_seasons_btn)
            
            self._random_delay()
            
            # Look for either season format
            season_options = self.get_season_text()
            season_found = False
            
            print(f"Looking for season options: {season_options}")
            
            # Function to check if season exists on current page
            def find_season_on_page():
                try:
                    # Get all season elements
                    season_elements = self.driver.find_elements(By.CSS_SELECTOR, "#pageGridFrame .dataGridElement .publicLogin a")
                    print(f"Found {len(season_elements)} season elements on current page")
                    
                    # Print all seasons for debugging
                    for elem in season_elements:
                        season_text = elem.text.strip()
                        print(f"Found season: {season_text}")
                        if any(option in season_text for option in season_options):
                            print(f"Found matching season: {season_text}")
                            return elem
                    return None
                except Exception as e:
                    print(f"Error searching for season on page: {e}")
                    return None

            # Try to find season on current page first
            season_link = find_season_on_page()
            
            # If not found, try clicking through pages
            if not season_link:
                print("Season not found on first page, checking other pages...")
                page_num = 1
                while True:
                    try:
                        # Look for next page arrow
                        print("Looking for next page arrow...")
                        next_arrows = self.driver.find_elements(By.CSS_SELECTOR, "i.icon-arrow_r.dgNext")
                        print(f"Found {len(next_arrows)} next arrows")
                        
                        if not next_arrows:
                            print("No next arrows found")
                            break
                            
                        next_arrow = next_arrows[0]
                        if not next_arrow.is_displayed():
                            print("Next arrow is not visible")
                            break
                            
                        page_num += 1
                        print(f"Clicking next page (page {page_num})...")
                        next_arrow.click()
                        time.sleep(0.5)  # Reduced wait time
                        
                        # Check if season exists on new page
                        season_link = find_season_on_page()
                        if season_link:
                            print(f"Found season on page {page_num}")
                            break
                            
                    except Exception as e:
                        print(f"Error navigating pages: {e}")
                        print("Current page source:")
                        print(self.driver.page_source[:1000])
                        break

            if not season_link:
                raise Exception(f"Could not find season {self.season_year} (tried {season_options})")

            print(f"Found season link: {season_link.text}")
            season_link.click()
            self._random_delay()

            # Handle the governing body selection popup
            print("Waiting for governing body selection popup...")
            self.wait.until(
                EC.presence_of_element_located((By.ID, "gbFrame"))
            )
            
            # Determine governing bodies based on league
            if self.league == 'hs':
                # For HS, TrackWrestling uses state association name
                # For Kentucky, use "Kentucky High School Athletic Association"
                if self.state == 'KY':
                    governing_bodies = ["Kentucky High School Athletic Association"]
                else:
                    # For other states, try state name
                    governing_bodies = [self.state]
            else:  # ncaa
                governing_bodies = ["NCAA"]
            processed_bodies = set()  # Track which governing bodies we've processed
            
            # Process each governing body
            for governing_body in governing_bodies:
                if governing_body in processed_bodies:
                    continue
                    
                try:
                    print(f"\nProcessing {governing_body}...")
                    
                    # Wait for governing body selection popup
                    print("Waiting for governing body selection popup...")
                    self.wait.until(
                        EC.presence_of_element_located((By.ID, "gbFrame"))
                    )
                    
                    # Get the governing body dropdown
                    select = self.wait.until(
                        EC.presence_of_element_located((By.ID, "gbId"))
                    )
                    select = Select(select)
                    
                    # Find and select the governing body
                    # For HS, try multiple variations
                    found = False
                    for option in select.options:
                        option_text = option.text.strip()
                        # For HS Kentucky, check for various forms
                        if self.league == 'hs' and self.state == 'KY':
                            if ("Kentucky" in option_text or 
                                "KHSAA" in option_text.upper() or
                                option_text == "Kentucky High School Athletic Association"):
                                select.select_by_value(option.get_attribute("value"))
                                found = True
                                print(f"Selected governing body: {option_text}")
                                break
                        # For NCAA or other cases, use exact match
                        elif governing_body in option_text:
                            select.select_by_value(option.get_attribute("value"))
                            found = True
                            print(f"Selected governing body: {option_text}")
                            break
                    
                    if not found:
                        print(f"Warning: Could not find governing body '{governing_body}' in dropdown")
                        print("Available options:")
                        for option in select.options:
                            print(f"  - {option.text}")
                        raise Exception(f"Could not find governing body '{governing_body}'")
                    
                    # Click the Login button to submit
                    print("Clicking Login button...")
                    login_btn = self.wait.until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "input[value='Login']"))
                    )
                    login_btn.click()
                    self._random_delay()
                    
                    # Get teams for this governing body
                    teams = self.get_teams_for_governing_body(governing_body)
                    
                    # Save teams to JSON
                    self.save_teams_to_json(teams, governing_body)
                    
                    # Mark this governing body as processed
                    processed_bodies.add(governing_body)
                    
                    # For HS, we only process one governing body, so break after processing
                    if self.league == 'hs':
                        print(f"Completed processing {governing_body} for HS")
                        break
                    
                    # For NCAA, go back to governing body selection to process other bodies
                    print("Returning to governing body selection...")
                    self.driver.get(BASE_URL)
                    time.sleep(3)  # Wait for page to load
                    
                    # Navigate back to season and governing body selection
                    browse_btn = self.wait.until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "nav.main-menu li a[href*='subMenu-browse']"))
                    )
                    browse_btn.click()
                    self._random_delay()
                    time.sleep(1)
                    
                    seasons_btn = self.wait.until(
                        EC.element_to_be_clickable((By.LINK_TEXT, "Seasons"))
                    )
                    seasons_btn.click()
                    self._random_delay()
                    time.sleep(2)
                    
                    more_seasons_btn = self.wait.until(
                        EC.presence_of_element_located((By.LINK_TEXT, "More Seasons"))
                    )
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", more_seasons_btn)
                    time.sleep(1)
                    more_seasons_btn.click()
                    self._random_delay()
                    
                    # Find and click the season link again
                    season_link = find_season_on_page()
                    if season_link:
                        season_link.click()
                        self._random_delay()
                    
                except Exception as e:
                    print(f"Error processing {governing_body}: {e}")
                    # If we get a stale element error, try refreshing the page and continuing
                    if "stale element" in str(e).lower():
                        print("Got stale element error, refreshing page...")
                        self.driver.refresh()
                        time.sleep(3)
                        continue
                    continue

        except Exception as e:
            error_msg = f"Error navigating to season: {e}"
            self._log_error("navigation", error_msg)
            print(f"Navigation error: {error_msg}")
            if self.driver:
                print(f"Current URL when error occurred: {self.driver.current_url}")
            raise

    def get_teams_for_governing_body(self, governing_body: str) -> List[Dict]:
        """Get list of teams for a specific governing body."""
        teams = []
        try:
            # Click on "Teams" link
            print("Clicking Teams link...")
            teams_link = self.wait.until(
                EC.element_to_be_clickable((By.LINK_TEXT, "Teams"))
            )
            teams_link.click()
            self._random_delay()
            time.sleep(3)  # Wait for page to load
            
            print("Waiting for PageFrame...")
            # Add a longer delay after login to handle cookie consent
            time.sleep(3)
            
            # First check if we're in the PageFrame
            try:
                self.driver.switch_to.frame("PageFrame")
                print("Successfully switched to PageFrame")
            except Exception as e:
                print(f"Error switching to PageFrame: {e}")
                # Try switching back to default content first
                self.driver.switch_to.default_content()
                # Then try switching to PageFrame again
                self.driver.switch_to.frame("PageFrame")
            
            # Switch back to default content to access the menu frame
            print("Switching back to default content to access menu...")
            self.driver.switch_to.default_content()
            
            # Click on Teams link in the menu frame
            print("Clicking Teams link in menu...")
            teams_btn = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "#g1MainMenuFrame a[href*='Teams.jsp']"))
            )
            teams_btn.click()
            self._random_delay()
            
            # Switch back to PageFrame for the teams data
            print("Switching back to PageFrame for teams data...")
            self.driver.switch_to.frame("PageFrame")
            
            # Get the current URL to extract session ID
            current_url = self.driver.current_url
            parsed_url = urlparse(current_url)
            query_params = parse_qs(parsed_url.query)
            session_id = query_params.get('twSessionId', [''])[0]
            print(f"Current session ID: {session_id}")
            
            # Get the page source and find the teams array
            page_source = self.driver.page_source
            print("Looking for teams data in page source...")
            
            # Find the teams array in the page source
            teams_data_start = page_source.find('initDataGrid(50, true, "')
            if teams_data_start == -1:
                print("Could not find teams data in page source")
                return []
                
            teams_data_start += len('initDataGrid(50, true, "')
            teams_data_end = page_source.find('", "./AjaxFunctions.jsp', teams_data_start)
            if teams_data_end == -1:
                print("Could not find end of teams data")
                return []
                
            teams_json = page_source[teams_data_start:teams_data_end]
            print(f"Found teams data: {teams_json[:100]}...")
            
            # Clean the JSON string before parsing
            teams_json = teams_json.replace('\\"', '"')  # Replace escaped quotes with regular quotes
            teams_json = teams_json.replace('\\\\', '\\')  # Replace double backslashes with single backslash
            
            # Parse the teams data
            teams = []
            try:
                # The data is a JSON array of arrays
                teams_array = json.loads(teams_json)
                print(f"Found {len(teams_array)} teams in data")
                
                for team_data in teams_array:
                    try:
                        # Extract team information from the array
                        team_id = team_data[0]  # Team ID is the first element
                        division = team_data[5] if len(team_data) > 5 else "Unknown"  # Division
                        
                        # Extract region from Leagues column (for HS only)
                        region = None
                        if self.league == 'hs':
                            # Leagues column is typically at index 4 (after Global Team, Abbr, Gov. Body)
                            # But need to check the actual structure - try multiple indices
                            leagues_str = ""
                            if len(team_data) > 4:
                                leagues_str = str(team_data[4]) if team_data[4] else ""
                            
                            # Parse region from "Region X" format
                            # Leagues can have multiple values like "Region 4, Region 4, Region 4, Region 4"
                            # Extract the first region number found
                            region_match = re.search(r'Region\s+(\d+)', leagues_str, re.IGNORECASE)
                            if region_match:
                                region = region_match.group(1)
                            else:
                                # Try other indices if index 4 doesn't have it
                                for idx in range(len(team_data)):
                                    if idx != 4 and idx < len(team_data):
                                        test_str = str(team_data[idx]) if team_data[idx] else ""
                                        region_match = re.search(r'Region\s+(\d+)', test_str, re.IGNORECASE)
                                        if region_match:
                                            region = region_match.group(1)
                                            break
                        
                        # Filter teams based on league type
                        if self.league == 'hs':
                            # For HS, include all teams (no division filtering)
                            # Filter by state if needed (though governing body should handle this)
                            team_state = team_data[2] if len(team_data) > 2 else ""
                            if self.state and team_state != self.state:
                                print(f"Skipping team from different state: {team_data[1]} - {team_state}")
                                continue
                            
                            # Set division label based on gender
                            division_label = f"KY HS {self.gender.capitalize()}"
                        else:  # ncaa
                            # Filter to only include NCAA D1 schools
                            # Check if division contains "DI" (not "DII" or "DIII") or "Division I"
                            # Split by comma to check each division part individually
                            division_parts = [part.strip() for part in division.split(',')]
                            is_d1 = False
                            
                            for part in division_parts:
                                part_upper = part.upper()
                                # Check for "DI " (with space), "DI-" (with dash), or exact "DI"
                                # Also check for "DIVISION I" but make sure it's not "DIVISION II" or "DIVISION III"
                                if (part_upper.startswith("DI ") or 
                                    part_upper.startswith("DI-") or 
                                    part_upper == "DI"):
                                    # Make sure it's not DII or DIII
                                    if not part_upper.startswith("DII") and not part_upper.startswith("DIII"):
                                        is_d1 = True
                                        break
                                # Check for "DIVISION I" but not "DIVISION II" or "DIVISION III"
                                elif ("DIVISION I" in part_upper and 
                                      "DIVISION II" not in part_upper and 
                                      "DIVISION III" not in part_upper):
                                    is_d1 = True
                                    break
                            
                            if not is_d1:
                                print(f"Skipping non-D1 team: {team_data[1]} - {division}")
                                continue
                            
                            division_label = "NCAA D1"
                        
                        team = {
                            "name": team_data[1],  # Team Name
                            "state": team_data[2],  # State
                            "abbreviation": team_data[3],  # Abbr
                            "governing_body": governing_body,
                            "division": division_label,
                            "url": f"{BASE_URL}/seasons/TeamSchedule.jsp?twSessionId={session_id}&teamId={team_id}"  # Construct URL with both session ID and team ID
                        }
                        
                        # Add region for HS teams only
                        if self.league == 'hs' and region:
                            team["region"] = region
                        
                        teams.append(team)
                        region_str = f" (Region {region})" if region else ""
                        print(f"Processed {self.league.upper()} team: {team['name']} ({team['state']}) - {team['division']}{region_str}")
                        
                    except Exception as e:
                        print(f"Error processing team data: {e}")
                        continue
                
                print(f"Successfully processed {len(teams)} teams")
                return teams
                
            except Exception as e:
                print(f"Error parsing teams data: {e}")
                print(f"Raw JSON string: {teams_json[:200]}...")  # Print first 200 chars of raw JSON for debugging
                return []
            
        except Exception as e:
            print(f"Error getting teams for {governing_body}: {e}")
            return []
        finally:
            # Switch back to default content
            try:
                self.driver.switch_to.default_content()
                print("Switched back to default content")
            except Exception as e:
                print(f"Error switching back to default content: {e}")

    def save_teams_to_json(self, teams: List[Dict], governing_body: str):
        """Save team data to a JSON file."""
        try:
            # Determine output path based on league type
            if self.league == 'hs':
                # HS output: data/team_lists/hs_ky_boys/teams.json or data/team_lists/hs_ky_girls/teams.json
                filename = f"data/team_lists/hs_{self.state.lower()}_{self.gender}/teams.json"
            else:  # ncaa
                # NCAA output remains unchanged
                filename = f"data/team_lists/{self.season_year}/ncaa_d1_teams.json"
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            
            # Load existing teams if file exists
            existing_teams_by_name = {}  # name -> team dict
            if os.path.exists(filename):
                with open(filename, 'r') as f:
                    existing_teams = json.load(f)
                    # Build lookup by name for easy updates
                    for team in existing_teams:
                        existing_teams_by_name[team['name']] = team
            
            # Merge new teams with existing teams, updating region data
            unique_teams = []
            seen_names = set()
            
            # First, process new teams from scrape (prioritize these)
            for team in teams:
                team_name = team['name']
                if team_name not in seen_names:
                    unique_teams.append(team)
                    seen_names.add(team_name)
            
            # Then add existing teams that weren't in the new scrape
            for team in existing_teams_by_name.values():
                if team['name'] not in seen_names:
                    unique_teams.append(team)
                    seen_names.add(team['name'])
            
            # Save to file
            with open(filename, 'w') as f:
                json.dump(unique_teams, f, indent=2)
            
            league_label = f"{self.league.upper()}" if self.league == 'ncaa' else f"{self.state} HS {self.gender.capitalize()}"
            print(f"Saved {len(unique_teams)} unique {league_label} teams to {filename}")
            
        except Exception as e:
            print(f"Error saving teams to JSON: {e}")

    def run(self):
        """Main scraping process."""
        try:
            self.setup_driver()
            self.navigate_to_season()  # This now handles all governing bodies
            
            # Only quit the driver after all governing bodies are processed
            if self.driver:
                print("\nAll governing bodies processed successfully!")
                self.driver.quit()
            
        except Exception as e:
            self._log_error("general", f"General error: {e}")
            if self.driver:
                self.driver.quit()
            raise

def main():
    """Main function."""
    args = parse_args()
    
    # Use season from args (required parameter)
    season_year = args.season
    
    # Create scraper and run
    scraper = WrestlingScraper(
        max_teams=args.teams,
        season_year=season_year,
        league=args.league,
        state=args.state,
        gender=args.gender
    )
    scraper.run()

if __name__ == "__main__":
    main() 