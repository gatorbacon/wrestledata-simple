#!/usr/bin/env python3
"""
NCAA D1 Team Scraper

This script scrapes team information from the NCAA wrestling website for NCAA Division I schools only.

It follows the same scraping strategy as wrestle_scraper.py but focuses only on team information
without scraping individual team pages or match data.
"""

import json
import os
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse
import platform
import argparse
import boto3
from boto3.dynamodb.conditions import Attr

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
    return parser.parse_args()

class WrestlingScraper:
    def __init__(self, max_teams=None, season_year=None):
        self.ua = UserAgent()
        self.driver = None
        self.wait = None
        self.season_year = season_year
        self.scrape_log = self._load_scrape_log()
        self.max_teams = max_teams
        
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
            
            # List of governing bodies to process - only NCAA for D1 schools
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
                    for option in select.options:
                        if governing_body in option.text:
                            select.select_by_value(option.get_attribute("value"))
                            break
                    
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
                    
                    # Go back to governing body selection
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
                        
                        team = {
                            "name": team_data[1],  # Team Name
                            "state": team_data[2],  # State
                            "abbreviation": team_data[3],  # Abbr
                            "governing_body": governing_body,
                            "division": division,
                            "url": f"{BASE_URL}/seasons/TeamSchedule.jsp?twSessionId={session_id}&teamId={team_id}"  # Construct URL with both session ID and team ID
                        }
                        
                        teams.append(team)
                        print(f"Processed D1 team: {team['name']} ({team['state']}) - {team['division']}")
                        
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
            # Create filename based on governing body and season year
            # Since we're only scraping D1 teams, use d1 in the filename
            filename = f"data/team_lists/{self.season_year}/ncaa_d1_teams.json"
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            
            # Load existing teams if file exists
            existing_teams = []
            if os.path.exists(filename):
                with open(filename, 'r') as f:
                    existing_teams = json.load(f)
            
            # Combine and remove duplicates
            all_teams = existing_teams + teams
            unique_teams = []
            seen_names = set()
            
            for team in all_teams:
                if team['name'] not in seen_names:
                    seen_names.add(team['name'])
                    unique_teams.append(team)
            
            # Save to file
            with open(filename, 'w') as f:
                json.dump(unique_teams, f, indent=2)
            
            print(f"Saved {len(unique_teams)} unique NCAA D1 teams to {filename}")
            
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
    # Get season year from user
    while True:
        try:
            season_year = int(input("Enter the season year (e.g., 2014 for 2013-14 season): "))
            if 1900 <= season_year <= 2100:
                break
            print("Please enter a valid year between 1900 and 2100")
        except ValueError:
            print("Please enter a valid year")

    # Create scraper and run
    scraper = WrestlingScraper(season_year=season_year)
    scraper.run()

if __name__ == "__main__":
    main() 