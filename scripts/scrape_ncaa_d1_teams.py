#!/usr/bin/env python3
"""
Team List Scraper — NCAA D1 and HS (KY)

Scrapes team information from TrackWrestling and saves to flat JSON files.
Overwrites any existing team list for the requested season.

Usage:
  NCAA men:   .venv/bin/python scripts/scrape_ncaa_d1_teams.py -league ncaa -gender men -season 2026
  NCAA women: .venv/bin/python scripts/scrape_ncaa_d1_teams.py -league ncaa -gender women -season 2026
  HS boys:    .venv/bin/python scripts/scrape_ncaa_d1_teams.py -league hs -gender boys -state KY -season 2026
  HS girls:   .venv/bin/python scripts/scrape_ncaa_d1_teams.py -league hs -gender girls -state KY -season 2026

Output paths:
  data/team_lists/ncaa_men/{season}/teams.json
  data/team_lists/ncaa_women/{season}/teams.json
  data/team_lists/hs_ky_boys/{season}/teams.json
  data/team_lists/hs_ky_girls/{season}/teams.json
"""

import argparse
import json
import os
import platform
import random
import re
import time
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

DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)


def parse_args():
    parser = argparse.ArgumentParser(description='Scrape wrestling team list from TrackWrestling.')
    parser.add_argument('-season', type=int, required=True,
                        help='Season ending year (e.g. 2026 for 2025-26 season)')
    parser.add_argument('-league', type=str, required=True, choices=['ncaa', 'hs'],
                        help='League type: ncaa or hs')
    parser.add_argument('-gender', type=str, required=True, choices=['boys', 'girls', 'men', 'women'],
                        help='Gender: boys/girls (HS) or men/women (NCAA)')
    parser.add_argument('-state', type=str,
                        help='State code — required when league=hs (e.g. KY)')
    parser.add_argument('-teams', type=int,
                        help='Max teams to scrape (omit for all)')
    return parser.parse_args()


def get_output_path(league: str, gender: str, state: str, season: int) -> Path:
    """Return the output JSON path for this league/gender/season combination."""
    if league == 'hs':
        key = f"hs_{state.lower()}_{gender}"
    else:
        key = f"ncaa_{gender}"
    return DATA_DIR / "team_lists" / key / str(season) / "teams.json"


class WrestlingScraper:
    def __init__(self, season_year: int, league: str, gender: str,
                 state: Optional[str] = None, max_teams: Optional[int] = None):
        self.season_year = season_year
        self.league = league
        self.gender = gender
        self.state = state.upper() if state else None
        self.max_teams = max_teams
        self.ua = UserAgent()
        self.driver = None
        self.wait = None
        self.output_path = get_output_path(league, gender, state or '', season_year)

        # Validate args
        if league == 'hs':
            if not self.state:
                raise ValueError("-state is required when -league=hs")
            if self.state != 'KY':
                raise ValueError(f"Only KY is currently supported for HS. Got: {self.state}")
            if gender not in ('boys', 'girls'):
                raise ValueError(f"-gender must be boys or girls for HS. Got: {gender}")
        else:  # ncaa
            if gender not in ('men', 'women'):
                raise ValueError(f"-gender must be men or women for NCAA. Got: {gender}")

    def get_season_text(self) -> List[str]:
        """Return list of TrackWrestling season text strings to match against."""
        start_year = self.season_year - 1
        short_end = str(self.season_year)[-2:]

        if self.league == 'hs':
            if self.gender == 'boys':
                if self.season_year in (2013, 2014):
                    return [f"{start_year}-{short_end} High School"]
                return [
                    f"{start_year}-{short_end} High School Boys",
                    f"{start_year}-{short_end} HS Boys",
                ]
            else:  # girls
                return [
                    f"{start_year}-{short_end} High School Girls",
                    f"{start_year}-{short_end} HS Girls",
                ]
        else:  # ncaa
            if self.gender == 'men':
                return [
                    f"{start_year}-{short_end} College Men",
                    f"{start_year}-{short_end} College",
                ]
            else:  # women
                return [
                    f"{start_year}-{short_end} College Women",
                ]

    def get_governing_bodies(self) -> List[str]:
        if self.league == 'hs':
            return ["Kentucky High School Athletic Association"]
        else:
            return ["NCAA"]

    def setup_driver(self):
        options = webdriver.ChromeOptions()
        options.add_argument(f'user-agent={self.ua.random}')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--start-maximized')
        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 20)

    def _random_delay(self):
        time.sleep(random.uniform(0.5, 1.0))

    def navigate_to_season(self):
        """Navigate through TrackWrestling to the target season."""
        print("Navigating to TrackWrestling...")
        self.driver.get(BASE_URL)
        time.sleep(3)

        print("Clicking Browse...")
        browse_btn = self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "nav.main-menu li a[href*='subMenu-browse']"))
        )
        browse_btn.click()
        self._random_delay()
        time.sleep(1)

        print("Clicking Seasons...")
        self.wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "Seasons"))).click()
        self._random_delay()
        time.sleep(2)

        print("Clicking More Seasons...")
        more_seasons_btn = self.wait.until(
            EC.presence_of_element_located((By.LINK_TEXT, "More Seasons"))
        )
        self.driver.execute_script("arguments[0].scrollIntoView(true);", more_seasons_btn)
        time.sleep(1)
        try:
            more_seasons_btn.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", more_seasons_btn)
        self._random_delay()

        season_options = self.get_season_text()
        print(f"Looking for season: {season_options}")

        def find_season_on_page():
            elements = self.driver.find_elements(
                By.CSS_SELECTOR, "#pageGridFrame .dataGridElement .publicLogin a"
            )
            for elem in elements:
                if any(opt in elem.text.strip() for opt in season_options):
                    return elem
            return None

        season_link = find_season_on_page()
        if not season_link:
            page_num = 1
            while True:
                next_arrows = self.driver.find_elements(By.CSS_SELECTOR, "i.icon-arrow_r.dgNext")
                if not next_arrows or not next_arrows[0].is_displayed():
                    break
                page_num += 1
                print(f"Checking page {page_num}...")
                next_arrows[0].click()
                time.sleep(0.5)
                season_link = find_season_on_page()
                if season_link:
                    break

        if not season_link:
            raise Exception(f"Could not find season {self.season_year} (tried: {season_options})")

        print(f"Found: {season_link.text}")
        season_link.click()
        self._random_delay()

        # Select governing body and scrape teams
        self.wait.until(EC.presence_of_element_located((By.ID, "gbFrame")))

        for governing_body in self.get_governing_bodies():
            print(f"\nProcessing governing body: {governing_body}")
            self._select_governing_body(governing_body)
            teams = self.get_teams_for_governing_body(governing_body)
            self.save_teams_to_json(teams)
            if self.league == 'hs':
                break  # HS only has one governing body per run

    def _select_governing_body(self, governing_body: str):
        """Select the governing body from the dropdown and log in."""
        self.wait.until(EC.presence_of_element_located((By.ID, "gbFrame")))
        select_elem = self.wait.until(EC.presence_of_element_located((By.ID, "gbId")))
        select = Select(select_elem)

        found = False
        for option in select.options:
            text = option.text.strip()
            if self.league == 'hs' and self.state == 'KY':
                if "Kentucky" in text or "KHSAA" in text.upper():
                    select.select_by_value(option.get_attribute("value"))
                    found = True
                    break
            elif governing_body in text:
                select.select_by_value(option.get_attribute("value"))
                found = True
                break

        if not found:
            available = [o.text for o in select.options]
            raise Exception(f"Could not find '{governing_body}' in governing body dropdown. Available: {available}")

        print(f"Selected: {governing_body}")
        login_btn = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[value='Login']")))
        login_btn.click()
        self._random_delay()

    def get_teams_for_governing_body(self, governing_body: str) -> List[Dict]:
        """Extract the team list from the TrackWrestling teams page."""
        teams = []
        try:
            # Navigate to the Teams page
            print("Clicking Teams link...")
            self.wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "Teams"))).click()
            self._random_delay()
            time.sleep(3)

            # Switch to PageFrame, back to default, then click Teams in menu
            try:
                self.driver.switch_to.frame("PageFrame")
            except Exception:
                self.driver.switch_to.default_content()
                self.driver.switch_to.frame("PageFrame")

            self.driver.switch_to.default_content()

            teams_btn = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "#g1MainMenuFrame a[href*='Teams.jsp']"))
            )
            teams_btn.click()
            self._random_delay()

            self.driver.switch_to.frame("PageFrame")

            # Extract session ID from URL
            current_url = self.driver.current_url
            query_params = parse_qs(urlparse(current_url).query)
            session_id = query_params.get('twSessionId', [''])[0]

            # Parse team data out of the embedded JS array
            page_source = self.driver.page_source
            marker = 'initDataGrid(50, true, "'
            start = page_source.find(marker)
            if start == -1:
                print("Could not find teams data in page source")
                return []
            start += len(marker)
            end = page_source.find('", "./AjaxFunctions.jsp', start)
            if end == -1:
                print("Could not find end of teams data")
                return []

            teams_json = page_source[start:end]
            teams_json = teams_json.replace('\\"', '"').replace('\\\\', '\\')

            teams_array = json.loads(teams_json)
            print(f"Found {len(teams_array)} raw team entries")

            for team_data in teams_array:
                try:
                    team_id  = team_data[0]
                    name     = team_data[1]
                    state    = team_data[2] if len(team_data) > 2 else ""
                    abbr     = team_data[3] if len(team_data) > 3 else ""
                    division = team_data[5] if len(team_data) > 5 else ""

                    if self.league == 'hs':
                        # Filter to correct state
                        if self.state and state != self.state:
                            continue

                        # Extract region from leagues column
                        region = None
                        leagues_str = str(team_data[4]) if len(team_data) > 4 and team_data[4] else ""
                        m = re.search(r'Region\s+(\d+)', leagues_str, re.IGNORECASE)
                        if m:
                            region = m.group(1)

                        division_label = f"KY HS {self.gender.capitalize()}"
                        team = {
                            "name": name,
                            "state": state,
                            "abbreviation": abbr,
                            "governing_body": governing_body,
                            "division": division_label,
                            "url": f"{BASE_URL}/seasons/TeamSchedule.jsp?twSessionId={session_id}&teamId={team_id}",
                        }
                        if region:
                            team["region"] = region

                    else:  # ncaa
                        # Filter to D1 only
                        parts = [p.strip().upper() for p in division.split(',')]
                        is_d1 = any(
                            (p.startswith("DI ") or p.startswith("DI-") or p == "DI" or
                             ("DIVISION I" in p and "DIVISION II" not in p and "DIVISION III" not in p))
                            for p in parts
                        )
                        if not is_d1:
                            continue

                        division_label = f"NCAA D1 {self.gender.capitalize()}"
                        team = {
                            "name": name,
                            "state": state,
                            "abbreviation": abbr,
                            "governing_body": governing_body,
                            "division": division_label,
                            "url": f"{BASE_URL}/seasons/TeamSchedule.jsp?twSessionId={session_id}&teamId={team_id}",
                        }

                    teams.append(team)
                    print(f"  {name} ({state}) — {division_label}")

                    if self.max_teams and len(teams) >= self.max_teams:
                        print(f"Reached max_teams limit ({self.max_teams})")
                        break

                except Exception as e:
                    print(f"  Error processing team row: {e}")
                    continue

            print(f"Kept {len(teams)} teams after filtering")
            return teams

        except Exception as e:
            print(f"Error scraping teams: {e}")
            return []
        finally:
            try:
                self.driver.switch_to.default_content()
            except Exception:
                pass

    def save_teams_to_json(self, teams: List[Dict]):
        """Write team list to the output JSON file, merging with any existing data."""
        path = self.output_path
        path.parent.mkdir(parents=True, exist_ok=True)

        # Merge with existing teams (new scrape takes priority)
        existing = {}
        if path.exists():
            with open(path) as f:
                for team in json.load(f):
                    existing[team['name']] = team

        merged = {team['name']: team for team in teams}
        for name, team in existing.items():
            if name not in merged:
                merged[name] = team

        result = sorted(merged.values(), key=lambda t: t['name'])

        with open(path, 'w') as f:
            json.dump(result, f, indent=2)

        print(f"\nSaved {len(result)} teams → {path}")

    def run(self):
        try:
            self.setup_driver()
            self.navigate_to_season()
        except Exception as e:
            print(f"Error: {e}")
            raise
        finally:
            if self.driver:
                self.driver.quit()


def main():
    args = parse_args()

    # Cross-validate league + gender
    if args.league == 'hs' and args.gender not in ('boys', 'girls'):
        print(f"Error: -gender must be boys or girls when -league=hs. Got: {args.gender}")
        exit(1)
    if args.league == 'ncaa' and args.gender not in ('men', 'women'):
        print(f"Error: -gender must be men or women when -league=ncaa. Got: {args.gender}")
        exit(1)
    if args.league == 'hs' and not args.state:
        print("Error: -state is required when -league=hs")
        exit(1)

    scraper = WrestlingScraper(
        season_year=args.season,
        league=args.league,
        gender=args.gender,
        state=args.state,
        max_teams=args.teams,
    )
    scraper.run()


if __name__ == "__main__":
    main()
