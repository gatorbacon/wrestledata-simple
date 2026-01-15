#!/usr/bin/env python3
"""
Roster-only scraper to extract grade data for HS seasons.

This script scrapes ONLY roster pages (no matches) to collect grade information
for all wrestlers across all teams. It is designed to be fast, safe, and fail-loud.

Output: data/roster_grades/{season}/{gender}_roster_grades.json
"""

import json
import argparse
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse, parse_qs

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


def normalize_grade(grade_raw: str) -> Optional[int]:
    """
    Normalize grade string to integer.
    
    Mapping:
    - "7th", "7"              → 7
    - "8th", "8"              → 8
    - "Fr.", "Freshman"       → 9
    - "RS Fr.", "RS-Fr."     → 9
    - "So.", "Sophomore"     → 10
    - "Jr.", "Junior"         → 11
    - "Sr.", "Senior"         → 12
    - Empty / Unknown         → null
    """
    if not grade_raw:
        return None
    
    grade_raw = grade_raw.strip()
    
    # Handle numeric grades (7th, 8th, or just "7", "8")
    if grade_raw.endswith('th'):
        try:
            return int(grade_raw[:-2])
        except ValueError:
            pass
    
    # Handle plain numbers
    try:
        num = int(grade_raw)
        if 7 <= num <= 8:
            return num
    except ValueError:
        pass
    
    # Handle high school grades
    grade_map = {
        'Fr.': 9,
        'Freshman': 9,
        'RS Fr.': 9,
        'RS-Fr.': 9,
        'So.': 10,
        'Sophomore': 10,
        'Jr.': 11,
        'Junior': 11,
        'Sr.': 12,
        'Senior': 12,
    }
    
    return grade_map.get(grade_raw, None)


class RosterGradeScraper:
    """Scraper for extracting roster grade data only."""
    
    def __init__(self, season: int, gender: str, headless: bool = False):
        self.season = season
        self.gender = gender
        self.headless = headless
        self.driver = None
        self.wait = None
        self.wrestlers = []
        self.seen_ids: Set[str] = set()
        self.unrecognized_grades: Set[str] = set()
        
    def setup_driver(self):
        """Set up Selenium WebDriver."""
        options = webdriver.ChromeOptions()
        if self.headless:
            options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        
        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 10)
        print("✅ WebDriver initialized")
    
    def navigate_to_season(self) -> bool:
        """Navigate to the season page."""
        try:
            base_url = "https://www.trackwrestling.com/seasons/SelectSeason.jsp"
            self.driver.get(base_url)
            time.sleep(2)
            
            # Find and click the season
            season_xpath = f"//a[contains(text(), '{self.season}-{self.season + 1}')]"
            season_link = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, season_xpath))
            )
            season_link.click()
            time.sleep(2)
            
            # Select governing body (KY HS)
            governing_body_xpath = "//a[contains(text(), 'KY HS')]"
            governing_body_link = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, governing_body_xpath))
            )
            governing_body_link.click()
            time.sleep(2)
            
            print(f"✅ Navigated to season {self.season}")
            return True
        except Exception as e:
            print(f"❌ Failed to navigate to season: {e}")
            return False
    
    def get_teams(self) -> List[Dict]:
        """Get list of teams from pre-scraped JSON file."""
        team_list_file = Path(f"data/team_lists/hs_ky_{self.gender}/teams.json")
        
        if not team_list_file.exists():
            raise FileNotFoundError(f"Team list file not found: {team_list_file}")
        
        print(f"Loading teams from: {team_list_file}")
        with open(team_list_file, 'r') as f:
            teams = json.load(f)
        
        # Update URLs with current session ID
        try:
            self.driver.switch_to.frame("PageFrame")
            current_url = self.driver.current_url
            self.driver.switch_to.default_content()
        except Exception:
            current_url = self.driver.current_url
        
        parsed_url = urlparse(current_url)
        query_params = parse_qs(parsed_url.query)
        session_id = query_params.get('twSessionId', [''])[0]
        
        if session_id:
            print(f"Current session ID: {session_id}")
            for team in teams:
                team_url = team.get("url", "")
                if team_url:
                    team_parsed = urlparse(team_url)
                    team_params = parse_qs(team_parsed.query)
                    team_id = team_params.get('teamId', [''])[0]
                    if team_id:
                        team["url"] = f"https://www.trackwrestling.com/seasons/TeamSchedule.jsp?twSessionId={session_id}&teamId={team_id}"
        
        print(f"✅ Loaded {len(teams)} teams")
        return teams
    
    def scrape_team_roster(self, team_url: str, team_info: Dict) -> bool:
        """
        Scrape roster for a single team.
        
        Returns True if successful, False if error occurred.
        """
        try:
            print(f"\n{'='*60}")
            print(f"Scraping: {team_info['name']} ({team_info.get('abbreviation', 'N/A')})")
            print(f"URL: {team_url}")
            print(f"{'='*60}")
            
            self.driver.get(team_url)
            time.sleep(2)
            
            # Click the Roster tab
            print("Clicking Roster tab...")
            roster_tab = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href*='TeamRoster.jsp']"))
            )
            roster_tab.click()
            time.sleep(2)
            
            # Get the roster table
            print("Extracting roster data...")
            roster_table = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table.dataGrid"))
            )
            
            # Get all rows except header
            roster_rows = roster_table.find_elements(By.CSS_SELECTOR, "tr.dataGridRow, tr.dataGridRowAlt")
            print(f"Found {len(roster_rows)} roster rows")
            
            if len(roster_rows) == 0:
                self._handle_error(
                    team_info['name'],
                    team_url,
                    "ZERO_ROSTER_ROWS",
                    "Roster table found but contains zero wrestlers"
                )
                return False
            
            team_wrestlers = []
            
            for row in roster_rows:
                try:
                    cols = row.find_elements(By.TAG_NAME, "td")
                    if len(cols) < 6:
                        continue
                    
                    # Extract wrestler data
                    name = cols[1].text.strip()
                    
                    # Get wrestler ID from the name link
                    try:
                        name_link = cols[1].find_element(By.TAG_NAME, "a")
                        href = name_link.get_attribute("href")
                        # Extract wrestler ID from URL
                        parsed = urlparse(href)
                        params = parse_qs(parsed.query)
                        wrestler_id = params.get('wrestlerId', [''])[0]
                    except (NoSuchElementException, KeyError, IndexError):
                        wrestler_id = None
                    
                    # Extract grade from cols[7] (8th column, 0-indexed)
                    grade_raw = ""
                    if len(cols) > 7:
                        grade_raw = cols[7].text.strip()
                    else:
                        # Try to find grade in other columns
                        grade_patterns = ["So.", "Jr.", "Sr.", "Fr.", "7th", "8th", 
                                         "Freshman", "Sophomore", "Junior", "Senior"]
                        for i, col in enumerate(cols):
                            if i == 1:  # Skip name column
                                continue
                            text = col.text.strip()
                            if any(pattern in text for pattern in grade_patterns):
                                grade_raw = text
                                break
                    
                    # Validate required fields
                    if not name:
                        self._handle_error(
                            team_info['name'],
                            team_url,
                            "MISSING_NAME",
                            f"Wrestler row found but name is empty"
                        )
                        return False
                    
                    if not wrestler_id:
                        self._handle_error(
                            team_info['name'],
                            team_url,
                            "MISSING_WRESTLER_ID",
                            f"Wrestler '{name}' has no wrestler ID in link"
                        )
                        return False
                    
                    # Check for duplicate ID
                    if wrestler_id in self.seen_ids:
                        print(f"⚠️  Warning: Duplicate wrestler ID {wrestler_id} ({name})")
                        continue
                    
                    # Normalize grade
                    grade_normalized = normalize_grade(grade_raw)
                    if grade_raw and grade_normalized is None:
                        self.unrecognized_grades.add(grade_raw)
                    
                    wrestler_data = {
                        "season_wrestler_id": wrestler_id,
                        "name": name,
                        "team": team_info['name'],
                        "grade_raw": grade_raw,
                        "grade_normalized": grade_normalized
                    }
                    
                    team_wrestlers.append(wrestler_data)
                    self.seen_ids.add(wrestler_id)
                    
                except Exception as e:
                    print(f"⚠️  Error processing roster row: {e}")
                    continue
            
            if len(team_wrestlers) == 0:
                self._handle_error(
                    team_info['name'],
                    team_url,
                    "ZERO_WRESTLERS_EXTRACTED",
                    "Roster rows found but zero wrestlers extracted"
                )
                return False
            
            self.wrestlers.extend(team_wrestlers)
            print(f"✅ Extracted {len(team_wrestlers)} wrestlers")
            return True
            
        except TimeoutException:
            self._handle_error(
                team_info['name'],
                team_url,
                "TIMEOUT",
                "Page failed to load or roster table not found"
            )
            return False
        except Exception as e:
            self._handle_error(
                team_info['name'],
                team_url,
                "UNEXPECTED_ERROR",
                str(e)
            )
            return False
    
    def _handle_error(self, team_name: str, team_url: str, error_type: str, error_msg: str):
        """Handle errors with fail-loud behavior."""
        print(f"\n{'='*60}")
        print("❌ ERROR DETECTED")
        print(f"{'='*60}")
        print(f"Team: {team_name}")
        print(f"URL: {team_url}")
        print(f"Error Type: {error_type}")
        print(f"Error Message: {error_msg}")
        print(f"{'='*60}")
        input("Press Enter to continue to next team...")
    
    def run(self):
        """Main execution loop."""
        try:
            self.setup_driver()
            
            if not self.navigate_to_season():
                print("❌ Failed to navigate to season. Aborting.")
                return False
            
            teams = self.get_teams()
            print(f"\nStarting to scrape {len(teams)} teams...")
            
            for i, team in enumerate(teams, 1):
                print(f"\n[{i}/{len(teams)}] Processing team...")
                success = self.scrape_team_roster(team['url'], team)
                if not success:
                    print(f"⚠️  Team {team['name']} failed, but continuing...")
            
            # Print summary
            print(f"\n{'='*60}")
            print("SCRAPING COMPLETE")
            print(f"{'='*60}")
            print(f"Total wrestlers extracted: {len(self.wrestlers)}")
            print(f"Unique wrestler IDs: {len(self.seen_ids)}")
            
            if self.unrecognized_grades:
                print(f"\n⚠️  Unrecognized grade strings ({len(self.unrecognized_grades)}):")
                for grade in sorted(self.unrecognized_grades):
                    print(f"  - '{grade}'")
            
            return True
            
        except Exception as e:
            print(f"❌ Fatal error: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            if self.driver:
                self.driver.quit()
    
    def save_results(self, output_dir: Path):
        """Save results to JSON file."""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = output_dir / f"{self.gender}_roster_grades.json"
        
        output_data = {
            "season": self.season,
            "gender": self.gender,
            "generated_at": datetime.now().isoformat(),
            "wrestlers": self.wrestlers
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Saved results to: {output_file}")
        print(f"   Total wrestlers: {len(self.wrestlers)}")


def main():
    parser = argparse.ArgumentParser(
        description='Scrape roster grades for HS season (roster-only, no matches)'
    )
    parser.add_argument(
        '--season',
        type=int,
        required=True,
        help='Season year (e.g., 2026)'
    )
    parser.add_argument(
        '--gender',
        type=str,
        required=True,
        choices=['boys', 'girls'],
        help='Gender (boys or girls)'
    )
    parser.add_argument(
        '--headless',
        action='store_true',
        help='Run browser in headless mode'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='data/roster_grades',
        help='Output directory (default: data/roster_grades)'
    )
    
    args = parser.parse_args()
    
    print(f"\n{'='*60}")
    print("ROSTER GRADE SCRAPER")
    print(f"{'='*60}")
    print(f"Season: {args.season}")
    print(f"Gender: {args.gender}")
    print(f"Headless: {args.headless}")
    print(f"{'='*60}\n")
    
    scraper = RosterGradeScraper(args.season, args.gender, headless=args.headless)
    
    if scraper.run():
        output_dir = Path(args.output_dir) / str(args.season)
        scraper.save_results(output_dir)
        return 0
    else:
        print("❌ Scraping failed")
        return 1


if __name__ == '__main__':
    exit(main())

