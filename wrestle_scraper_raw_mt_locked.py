import json

import os
from pathlib import Path
import time
import tempfile
import shutil

LOCK_DIR = Path("mt/locks")
LOCK_DIR.mkdir(parents=True, exist_ok=True)

# Teams/seasons that skip weight-class validation in the wrestler dropdown.
# Dropdown entries without " - " (e.g. "Jayden Pointer" vs "120 - Cole Young") are
# normally skipped; for these (team, season) pairs we accept them and try roster lookup.
SKIP_WEIGHT_VALIDATION_TEAMS = {("Boone County", "2026")}

# Log file lock directory
LOG_LOCK_DIR = Path("mt/log_locks")
LOG_LOCK_DIR.mkdir(parents=True, exist_ok=True)

# Tracking file lock directory
TRACKING_LOCK_DIR = Path("mt/tracking_locks")
TRACKING_LOCK_DIR.mkdir(parents=True, exist_ok=True)

def acquire_lock(team_id):
    lock_file = LOCK_DIR / f"{team_id}.lock"
    if lock_file.exists():
        return False
    try:
        lock_file.write_text("locked")
        return True
    except Exception:
        return False

def release_lock(team_id):
    lock_file = LOCK_DIR / f"{team_id}.lock"
    try:
        lock_file.unlink()
    except FileNotFoundError:
        pass

# Log file locking mechanism
def acquire_log_lock(season_year):
    """Acquire a lock for the log file for the given season."""
    lock_file = LOG_LOCK_DIR / f"log_{season_year}.lock"
    max_attempts = 5
    attempt = 0
    
    while attempt < max_attempts:
        if not lock_file.exists():
            try:
                lock_file.write_text(f"locked by {os.getpid()} at {datetime.now().isoformat()}")
                return True
            except Exception:
                # If we failed to create the lock file, wait and retry
                time.sleep(0.5)
        else:
            # If lock file exists, wait and retry
            time.sleep(0.5)
        
        attempt += 1
    
    return False
    
def release_log_lock(season_year):
    """Release the lock for the log file for the given season."""
    lock_file = LOG_LOCK_DIR / f"log_{season_year}.lock"
    try:
        lock_file.unlink()
    except FileNotFoundError:
        pass

# Tracking file locking mechanism
def acquire_tracking_lock(season_year, league, state=None, gender=None):
    """Acquire a lock for the tracking file."""
    if league == 'hs':
        if not state or not gender:
            raise ValueError("state and gender are required for HS tracking lock")
        lock_file = TRACKING_LOCK_DIR / f"tracking_{season_year}_hs_{state.lower()}_{gender}.lock"
    else:  # ncaa
        lock_file = TRACKING_LOCK_DIR / f"tracking_{season_year}_ncaa.lock"
    
    max_attempts = 5
    attempt = 0
    
    while attempt < max_attempts:
        if not lock_file.exists():
            try:
                lock_file.write_text(f"locked by {os.getpid()} at {datetime.now().isoformat()}")
                return True
            except Exception:
                time.sleep(0.5)
        else:
            time.sleep(0.5)
        
        attempt += 1
    
    return False

def release_tracking_lock(season_year, league, state=None, gender=None):
    """Release the lock for the tracking file."""
    if league == 'hs':
        if not state or not gender:
            raise ValueError("state and gender are required for HS tracking lock")
        lock_file = TRACKING_LOCK_DIR / f"tracking_{season_year}_hs_{state.lower()}_{gender}.lock"
    else:  # ncaa
        lock_file = TRACKING_LOCK_DIR / f"tracking_{season_year}_ncaa.lock"
    try:
        lock_file.unlink()
    except FileNotFoundError:
        pass

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
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException, ElementClickInterceptedException

# Configuration
BASE_URL = "https://www.trackwrestling.com"
DATA_DIR = Path("mt/data")
LOGS_DIR = Path("mt/logs")
#SCRAPE_LOG_FILE = LOGS_DIR / "scrape_log.json"
SCRAPE_LOG_FILE = lambda season: LOGS_DIR / f"scrape_log_{season}.json"


# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True, parents=True)
LOGS_DIR.mkdir(exist_ok=True)

# DynamoDB setup
db = boto3.resource('dynamodb', endpoint_url='http://localhost:8001')
teams_table = db.Table('teams')  # Keep this for reference but we won't use it to add teams

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Scrape wrestling team data.')
    parser.add_argument('-teams', type=int, help='Number of teams to scrape. If not provided, scrapes all teams.')
    parser.add_argument('-season', type=int, required=True, help='Season ending year (e.g. 2023 for 2022-23 season)')
    parser.add_argument('-headless', action='store_true', help='Run browser in headless mode')
    parser.add_argument('-league', type=str, default='ncaa', choices=['ncaa', 'hs'],
                        help='League type: ncaa (default) or hs')
    parser.add_argument('-state', type=str, help='State code (required when league=hs, currently only KY supported)')
    parser.add_argument('-gender', type=str, choices=['boys', 'girls'],
                        help='Gender: boys or girls (required when league=hs)')
    parser.add_argument('-force', action='store_true',
                        help='Force complete re-scrape: archive logs and delete all team data files')
    return parser.parse_args()

class WrestlingScraper:
    def __init__(self, max_teams=None, season_year=None, headless=False, league='ncaa', state=None, gender=None):
        self.ua = UserAgent()
        self.driver = None
        self.wait = None
        self.season_year = season_year
        self.max_teams = max_teams
        self.headless = headless
        self.name_aliases = self._load_name_aliases()
        self.eligibility_overrides = self._load_eligibility_overrides()
        self.league = league
        self.state = state
        self.gender = gender
        
        # Validate HS parameters
        if self.league == 'hs':
            if not self.state:
                raise ValueError("-state is required when -league=hs")
            # Normalize state to uppercase for comparison
            state_upper = self.state.upper()
            if state_upper != 'KY':
                raise ValueError(f"Only KY is currently supported for HS. Got: {self.state}")
            # Store normalized state
            self.state = state_upper
            if not self.gender:
                raise ValueError("-gender is required when -league=hs")
            if self.gender not in ['boys', 'girls']:
                raise ValueError(f"-gender must be 'boys' or 'girls'. Got: {self.gender}")
        
        # Create season-specific data directory
        if self.league == 'hs':
            # HS data goes to season-specific subdirectories: mt/data/hs_ky_boys/{season}/ or mt/data/hs_ky_girls/{season}/
            self.season_data_dir = DATA_DIR / f"hs_{self.state.lower()}_{self.gender}" / str(season_year)
        else:  # ncaa
            # NCAA data goes to season-specific directory: mt/data/{season_year}/
            self.season_data_dir = DATA_DIR / str(season_year)
        self.season_data_dir.mkdir(exist_ok=True, parents=True)
        
        # Load scrape log AFTER league/state/gender are set (needed for log file path)
        self.scrape_log = self._load_scrape_log()
        
        # Load wrestler match tracking (for regression detection)
        self.wrestler_match_tracking = self._load_wrestler_match_tracking()

    def _get_tracking_file_path(self) -> Path:
        """Get the tracking file path based on league type."""
        tracking_dir = Path("mt/tracking")
        tracking_dir.mkdir(parents=True, exist_ok=True)
        
        if self.league == 'hs':
            filename = f"wrestler_match_history_{self.season_year}_hs_{self.state.lower()}_{self.gender}.json"
        else:  # ncaa
            filename = f"wrestler_match_history_{self.season_year}_ncaa.json"
        
        return tracking_dir / filename
    
    def _load_wrestler_match_tracking(self) -> Dict:
        """Load or create the wrestler match tracking file."""
        default_tracking = {
            "season": self.season_year,
            "league": self.league,
            "state": self.state,
            "gender": self.gender,
            "wrestlers": {}
        }
        
        tracking_file_path = self._get_tracking_file_path()
        
        if tracking_file_path.exists():
            # Try to acquire the tracking lock
            if acquire_tracking_lock(self.season_year, self.league, self.state, self.gender):
                try:
                    with open(tracking_file_path, 'r', encoding='utf-8') as f:
                        tracking_data = json.load(f)
                    release_tracking_lock(self.season_year, self.league, self.state, self.gender)
                    return tracking_data
                except Exception as e:
                    print(f"Error loading tracking file: {e}")
                    release_tracking_lock(self.season_year, self.league, self.state, self.gender)
                    return default_tracking
            else:
                print(f"Warning: Could not acquire tracking lock for reading. Using default tracking.")
                return default_tracking
        
        return default_tracking
    
    def _save_wrestler_match_tracking(self):
        """Save wrestler match tracking file with atomic write and locking."""
        tracking_file_path = self._get_tracking_file_path()
        
        # Try to acquire the tracking lock
        if acquire_tracking_lock(self.season_year, self.league, self.state, self.gender):
            try:
                # First read the current tracking file to merge with
                current_tracking = {
                    "season": self.season_year,
                    "league": self.league,
                    "state": self.state,
                    "gender": self.gender,
                    "wrestlers": {}
                }
                
                if tracking_file_path.exists():
                    with open(tracking_file_path, 'r', encoding='utf-8') as f:
                        try:
                            current_tracking = json.load(f)
                        except json.JSONDecodeError:
                            print("Warning: Tracking file exists but is corrupted. Creating new tracking.")
                            current_tracking = {
                                "season": self.season_year,
                                "league": self.league,
                                "state": self.state,
                                "gender": self.gender,
                                "wrestlers": {}
                            }
                
                # Merge wrestler data (our in-memory tracking takes precedence for updated entries)
                # But preserve entries we haven't seen in this scrape
                for wrestler_id, entry in self.wrestler_match_tracking.get("wrestlers", {}).items():
                    current_tracking["wrestlers"][wrestler_id] = entry
                
                # Create a temporary file for atomic write
                temp_file = tempfile.NamedTemporaryFile(delete=False, mode='w', encoding='utf-8', dir=tracking_file_path.parent)
                
                # Write the merged tracking to the temporary file
                json.dump(current_tracking, temp_file, indent=2, ensure_ascii=False)
                temp_file.flush()
                temp_file.close()
                
                # Atomically replace the tracking file with the temporary file
                shutil.move(temp_file.name, tracking_file_path)
                
                # Update our in-memory tracking with the merged data
                self.wrestler_match_tracking = current_tracking
                
            except Exception as e:
                print(f"Error saving tracking file: {e}")
                try:
                    # Clean up the temporary file if it exists
                    if 'temp_file' in locals() and os.path.exists(temp_file.name):
                        os.unlink(temp_file.name)
                except:
                    pass
            finally:
                release_tracking_lock(self.season_year, self.league, self.state, self.gender)
        else:
            print(f"Warning: Could not acquire tracking lock for writing. Tracking update skipped.")
    
    def _is_valid_match(self, match: Dict) -> bool:
        """
        Determine if a match is valid (should be counted).
        
        Excludes:
        - BYE matches
        - NoResult matches
        - Matches with "received a bye" in summary
        """
        result = match.get("result", "").strip()
        summary = match.get("summary", "").strip().lower()
        
        # Skip BYE and NoResult
        if result in ("BYE", "NoResult"):
            return False
        
        # Skip matches with "received a bye" in summary
        if "received a bye" in summary:
            return False
        
        return True
    
    def _validate_wrestler_match_count(self, wrestler_id: str, wrestler_name: str, matches: List[Dict]) -> tuple[str, str]:
        """
        Validate wrestler match count against tracking history.
        
        Returns:
            (status, message) tuple where:
            - status is "OK" if validation passes
            - status is "REGRESSION_DETECTED" if wrestler previously had matches but now has zero
            - message contains descriptive text
        """
        # Count valid matches
        valid_matches = [m for m in matches if self._is_valid_match(m)]
        valid_match_count = len(valid_matches)
        
        # Ensure wrestlers dict exists
        if "wrestlers" not in self.wrestler_match_tracking:
            self.wrestler_match_tracking["wrestlers"] = {}
        
        wrestlers = self.wrestler_match_tracking["wrestlers"]
        
        # First time seeing this wrestler
        if wrestler_id not in wrestlers:
            if valid_match_count > 0:
                wrestlers[wrestler_id] = {
                    "has_ever_had_matches": True,
                    "first_seen_with_matches": datetime.now().isoformat(),
                    "last_verified_with_matches": datetime.now().isoformat()
                }
            else:
                wrestlers[wrestler_id] = {
                    "has_ever_had_matches": False,
                    "first_seen_zero_matches": datetime.now().isoformat()
                }
            return ("OK", f"First time seeing wrestler {wrestler_id} ({wrestler_name})")
        
        # Wrestler exists in tracking
        entry = wrestlers[wrestler_id]
        
        # Check for regression: previously had matches, now zero
        # Skip check if we've already accepted zero matches for this wrestler
        if entry.get("has_ever_had_matches", False) and valid_match_count == 0:
            if entry.get("accepted_zero_matches", False):
                # We've already accepted zero matches for this wrestler - update timestamp and continue
                entry["last_seen_zero_matches"] = datetime.now().isoformat()
                return ("OK", f"Wrestler {wrestler_id} ({wrestler_name}) has zero matches (previously accepted)")
            
            last_verified = entry.get("last_verified_with_matches", "unknown")
            return (
                "REGRESSION_DETECTED",
                (
                    f"REGRESSION DETECTED: Wrestler {wrestler_id} ({wrestler_name}) "
                    f"previously had matches but now scrapes as zero matches. "
                    f"Last verified with matches: {last_verified}. "
                    f"Aborting team scrape to prevent data loss."
                )
            )
        
        # Update tracking based on current state
        if valid_match_count > 0:
            # Wrestler has matches - update timestamp
            if not entry.get("has_ever_had_matches", False):
                # Upgrade from zero to non-zero
                entry["has_ever_had_matches"] = True
                entry["first_seen_with_matches"] = datetime.now().isoformat()
            entry["last_verified_with_matches"] = datetime.now().isoformat()
        else:
            # Wrestler has zero matches - update timestamp if never had matches
            if not entry.get("has_ever_had_matches", False):
                if "last_seen_zero_matches" not in entry:
                    entry["first_seen_zero_matches"] = datetime.now().isoformat()
                entry["last_seen_zero_matches"] = datetime.now().isoformat()
        
        return ("OK", f"Wrestler {wrestler_id} ({wrestler_name}) validated: {valid_match_count} valid matches")

    def _load_name_aliases(self):
        """Load name aliases from mt/name_alias.json."""
        try:
            with open("mt/name_alias.json", "r") as f:
                alias_data = json.load(f)
                return alias_data.get("aliases", [])
        except Exception:
            return []
    
    def _load_eligibility_overrides(self):
        """Load eligibility overrides from mt/eligibility_overrides.json."""
        try:
            with open("mt/eligibility_overrides.json", "r") as f:
                override_data = json.load(f)
                return override_data.get("overrides", [])
        except FileNotFoundError:
            return []
        except Exception:
            print("Warning: Could not load eligibility overrides file")
            return []

    def _get_name_variants(self, name: str, team: str, season: int):
        """Return canonical + variant names for a wrestler for a given team/season."""
        variants = [name]
        season_str = str(season)
        for alias in self.name_aliases:
            cond = alias.get("conditions", {})
            if (cond.get("season") == season_str and
                cond.get("team") == team and
                (alias.get("canonical_name") == name or name in alias.get("name_variants", []))):
                variants.append(alias.get("canonical_name"))
                variants.extend(alias.get("name_variants", []))
        # de-duplicate and strip
        out = []
        seen = set()
        for v in variants:
            if not v:
                continue
            vv = v.strip()
            if vv and vv.lower() not in seen:
                seen.add(vv.lower())
                out.append(vv)
        return out

    def _text_has_any(self, haystack: str, needles: list[str]) -> bool:
        h = (haystack or "").lower()
        for n in needles or []:
            try:
                if n and n.lower() in h:
                    return True
            except Exception:
                continue
        return False

    def _verify_wrestler_table_hydrated(self, wrestler_id: str, timeout_sec: float = 8.0) -> str:
        """Best-effort check that the match table has hydrated for this wrestler.
        
        This is intentionally lightweight: it does a single pass to see if the
        table contains any links with wrestlerId=<wrestler_id>. It does NOT try
        to infer 'no matches' empties; that is handled explicitly later using
        page text and, when needed, a reset to the 'wrestler' placeholder.
        
        Returns:
            'hydrated' if table rows contain wrestlerId=<wrestler_id>
            'timeout'  otherwise
        """
        try:
            table = self.driver.find_element(By.CSS_SELECTOR, "table.dataGrid")
            links = table.find_elements(By.CSS_SELECTOR, "a[href*='wrestlerId=']")
            for a in links:
                href = a.get_attribute("href") or ""
                if f"wrestlerId={wrestler_id}" in href:
                    return "hydrated"
        except Exception:
            # If we cannot inspect the table, just signal that we couldn't confirm hydration.
            pass
        return "timeout"

    def _get_log_file_path(self) -> Path:
        """Get the log file path based on league type."""
        if self.league == 'hs':
            # HS logs: mt/logs/hs_ky_boys/scrape_log_2026.json or mt/logs/hs_ky_girls/scrape_log_2026.json
            log_dir = LOGS_DIR / f"hs_{self.state.lower()}_{self.gender}"
            log_dir.mkdir(exist_ok=True, parents=True)
            return log_dir / f"scrape_log_{self.season_year}.json"
        else:  # ncaa
            # NCAA logs: mt/logs/scrape_log_{season_year}.json (unchanged)
            return SCRAPE_LOG_FILE(self.season_year)
    
    def _load_scrape_log(self) -> Dict:
        """Load or create the scrape log file."""
        default_log = {
            "teams_scraped": [],
            "last_run": None,
            "errors": [],
            "successes": []
        }
        
        log_file_path = self._get_log_file_path()
        if log_file_path.exists():
            # Try to acquire the log lock
            if acquire_log_lock(self.season_year):
                try:
                    with open(log_file_path, 'r') as f:
                        log_data = json.load(f)
                    release_log_lock(self.season_year)
                    return log_data
                except Exception as e:
                    print(f"Error loading log file: {e}")
                    release_log_lock(self.season_year)
                    return default_log
            else:
                print(f"Warning: Could not acquire log lock for reading. Using default log.")
                return default_log
        return default_log

    def _save_scrape_log(self):
        """Save current progress to the scrape log with atomic write and proper merging."""
        self.scrape_log["last_run"] = datetime.now().isoformat()
        
        # Try to acquire the log lock
        if acquire_log_lock(self.season_year):
            try:
                # First read the current log file to merge with
                current_log = {}
                log_file_path = self._get_log_file_path()
                
                if log_file_path.exists():
                    with open(log_file_path, 'r') as f:
                        try:
                            current_log = json.load(f)
                        except json.JSONDecodeError:
                            print("Warning: Log file exists but is corrupted. Creating new log.")
                            current_log = {"teams_scraped": [], "errors": [], "successes": [], "last_run": None}
                
                # Merge the logs
                # 1. Merge teams_scraped (avoid duplicates)
                for team in self.scrape_log.get("teams_scraped", []):
                    if team not in current_log.get("teams_scraped", []):
                        current_log.setdefault("teams_scraped", []).append(team)
                
                # 2. Append new errors
                for error in self.scrape_log.get("errors", []):
                    if error not in current_log.get("errors", []):
                        current_log.setdefault("errors", []).append(error)
                
                # 3. Append new successes
                for success in self.scrape_log.get("successes", []):
                    if success not in current_log.get("successes", []):
                        current_log.setdefault("successes", []).append(success)
                
                # 4. Update last_run with the most recent timestamp
                current_log["last_run"] = self.scrape_log["last_run"]
                
                # Create a temporary file for atomic write
                temp_file = tempfile.NamedTemporaryFile(delete=False, mode='w', dir=LOGS_DIR)
                
                # Write the merged log to the temporary file
                json.dump(current_log, temp_file, indent=2)
                temp_file.flush()
                temp_file.close()
                
                # Atomically replace the log file with the temporary file
                shutil.move(temp_file.name, log_file_path)
                
                # Update our in-memory log with the merged data
                self.scrape_log = current_log
                
            except Exception as e:
                print(f"Error saving log file: {e}")
                try:
                    # Clean up the temporary file if it exists
                    if os.path.exists(temp_file.name):
                        os.unlink(temp_file.name)
                except:
                    pass
            finally:
                release_log_lock(self.season_year)
        else:
            print(f"Warning: Could not acquire log lock for writing. Log update skipped.")

    def _refresh_log_data(self):
        """Refresh all log data from the log file."""
        # First, ensure our in-memory log has all required fields initialized
        self.scrape_log.setdefault("teams_scraped", [])
        self.scrape_log.setdefault("errors", [])
        self.scrape_log.setdefault("successes", [])
        
        log_file_path = self._get_log_file_path()
        if log_file_path.exists():
            if acquire_log_lock(self.season_year):
                try:
                    with open(log_file_path, 'r') as f:
                        log_data = json.load(f)
                    
                    # Update all log sections
                    self.scrape_log["teams_scraped"] = log_data.get("teams_scraped", [])
                    
                    # Merge errors and successes (don't overwrite)
                    for error in log_data.get("errors", []):
                        if error not in self.scrape_log.get("errors", []):
                            self.scrape_log.setdefault("errors", []).append(error)
                    
                    for success in log_data.get("successes", []):
                        if success not in self.scrape_log.get("successes", []):
                            self.scrape_log.setdefault("successes", []).append(success)
                    
                    print(f"Refreshed log data from file, found {len(self.scrape_log['teams_scraped'])} teams already scraped.")
                except Exception as e:
                    print(f"Error refreshing log data: {e}")
                finally:
                    release_log_lock(self.season_year)
            else:
                print("Warning: Could not acquire log lock to refresh log data.")
        else:
            print("Log file doesn't exist yet. Using empty log with initialized structure.")

    def _random_delay(self):
        """Add random delay between requests."""
        time.sleep(random.uniform(0.5, 1.0))

    def _dismiss_cookie_modal_if_present(self, timeout: float = 5.0):
        """Best-effort dismissal of Trackwrestling cookie/consent modal overlay.
        
        This targets the rfmodal / rFastModalWrapper overlay that has been
        intermittently blocking clicks on the main navigation.
        """
        try:
            print(f"Checking for cookie/consent modal overlay (timeout={timeout}s)...")
            overlay = None
            # Try a few locator variants since TW may tweak classnames slightly.
            overlay_locators = [
                (By.CSS_SELECTOR, "div.rfmodal.rFastModalWrapper"),
                (By.CSS_SELECTOR, "div[class*='rFastModalWrapper']"),
                (By.CSS_SELECTOR, "div[class*='rfmodal'][class*='rFastModalWrapper']"),
            ]
            for by, selector in overlay_locators:
                try:
                    overlay = WebDriverWait(self.driver, timeout).until(
                        EC.presence_of_element_located((by, selector))
                    )
                    if overlay:
                        break
                except TimeoutException:
                    # Try next locator flavor
                    continue

            if not overlay:
                print("No cookie/consent modal overlay found.")
                return

            if not overlay.is_displayed():
                print("Cookie/consent modal element present but not displayed; skipping.")
                return

            print("Cookie/consent modal detected; attempting to dismiss it...")

            # Look for likely action buttons/links inside the modal.
            buttons = overlay.find_elements(
                By.CSS_SELECTOR,
                "button, a, input[type='button'], input[type='submit']",
            )
            preferred_keywords = [
                "accept",
                "agree",
                "save",
                "continue",
                "ok",
                "got it",
                "close",
            ]

            clicked = False
            for btn in buttons:
                try:
                    label = (btn.text or btn.get_attribute("value") or "").strip()
                    label_lower = label.lower()
                    if label:
                        print(f"Found modal button: '{label}'")
                    if any(k in label_lower for k in preferred_keywords):
                        print(f"Clicking modal button '{label}' via normal click...")
                        try:
                            btn.click()
                        except Exception as e:
                            print(f"Normal click on modal button '{label}' failed: {e}; trying JS click...")
                            self.driver.execute_script("arguments[0].click();", btn)
                        clicked = True
                        break
                except Exception as e:
                    print(f"Error inspecting modal button: {e}")
                    continue

            # If we didn't find a preferred button, click the first as a fallback.
            if not clicked and buttons:
                btn = buttons[0]
                label = (btn.text or btn.get_attribute("value") or "").strip()
                print(f"No preferred modal button found; clicking first modal button '{label}'")
                try:
                    btn.click()
                except Exception as e:
                    print(f"Normal click on first modal button failed: {e}; trying JS click...")
                    self.driver.execute_script("arguments[0].click();", btn)

            # Wait briefly for overlay to disappear.
            try:
                WebDriverWait(self.driver, 5).until(EC.invisibility_of_element(overlay))
                print("Cookie/consent modal dismissed (overlay is now invisible).")
            except TimeoutException:
                print("Cookie/consent modal still visible after dismissal attempt; continuing anyway.")

        except Exception as e:
            print(f"Error while attempting to dismiss cookie/consent modal overlay: {e}")

    def _log_error(self, error_type: str, details: str):
        """Log an error with timestamp and save immediately."""
        error_entry = {
            "type": error_type,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.scrape_log.setdefault("errors", []).append(error_entry)
        # Save immediately to ensure errors are persisted
        self._save_scrape_log()
        
    def _log_success(self, success_type: str, details: str):
        """Log a success event with timestamp and save immediately."""
        success_entry = {
            "type": success_type,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.scrape_log.setdefault("successes", []).append(success_entry)
        # Save immediately to ensure successes are persisted
        self._save_scrape_log()

    def _refresh_teams_scraped(self):
        """Refresh the list of scraped teams from the log file."""
        # Load the latest version of the log file
        log_file_path = self._get_log_file_path()
        if log_file_path.exists():
            if acquire_log_lock(self.season_year):
                try:
                    with open(log_file_path, 'r') as f:
                        log_data = json.load(f)
                    # Update only the teams_scraped list, preserving other log data
                    self.scrape_log["teams_scraped"] = log_data.get("teams_scraped", [])
                    print(f"Refreshed teams_scraped list, found {len(self.scrape_log['teams_scraped'])} teams already scraped.")
                except Exception as e:
                    print(f"Error refreshing teams_scraped: {e}")
                finally:
                    release_log_lock(self.season_year)
            else:
                print("Warning: Could not acquire log lock to refresh teams list.")

    def setup_driver(self):
        """Initialize the Selenium WebDriver with appropriate options."""
        try:
            options = webdriver.ChromeOptions()
            options.add_argument(f'user-agent={self.ua.random}')
            
            # Add headless mode if specified
            if self.headless:
                options.add_argument('--headless=new')
                print("Running in headless mode")
            else:
                print("Running with browser visible")
                
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

    def navigate_to_events_classic(self) -> bool:
        """Navigate to Events Classic (tournament/events list) via Browse menu.
        Use this to get a session ID that has access to TournamentHub.
        Returns True on success, False on failure.
        """
        try:
            print("Navigating to homepage...")
            self.driver.get(BASE_URL)
            time.sleep(3)
            print(f"Current URL: {self.driver.current_url}")
            print(f"Page title: {self.driver.title}")

            self._dismiss_cookie_modal_if_present(timeout=7.0)

            print("Attempting to click Browse...")
            browse_btn = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "nav.main-menu li a[href*='subMenu-browse']"))
            )
            browse_btn.click()
            self._random_delay()
            time.sleep(2)

            print("Clicking Events Classic...")
            self._dismiss_cookie_modal_if_present(timeout=3.0)
            events_btn = self.wait.until(
                EC.element_to_be_clickable((By.LINK_TEXT, "EVENTS CLASSIC"))
            )
            events_btn.click()
            self._random_delay()
            time.sleep(3)

            print("Events Classic page loaded successfully")
            return True

        except Exception as e:
            error_msg = f"Error navigating to Events Classic: {e}"
            print(f"Navigation error: {error_msg}")
            try:
                if self.driver:
                    print(f"Current URL when error occurred: {self.driver.current_url}")
            except Exception:
                pass
            return False

    def get_season_text(self):
        """Convert season year to possible season text formats."""
        start_year = self.season_year - 1
        short_end = str(self.season_year)[-2:]  # Get last 2 digits
        
        if self.league == 'hs':
            if self.gender == 'boys':
                # 2013 and 2014 seasons used "High School" without gender suffix
                if self.season_year in (2013, 2014):
                    return [
                        f"{start_year}-{short_end} High School",
                    ]
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

    def navigate_to_season(self) -> bool:
        """Navigate to the wrestling season page.
        
        Returns True on success, False on failure.
        """
        try:
            print("Navigating to homepage...")
            self.driver.get(BASE_URL)
            time.sleep(3)
            print(f"Initial window size: {self.driver.get_window_size()}")
            
            # Print page title and URL for debugging
            print(f"Current URL: {self.driver.current_url}")
            print(f"Page title: {self.driver.title}")

            # Best-effort: clear any cookie / consent modal that may be blocking the nav bar.
            self._dismiss_cookie_modal_if_present(timeout=7.0)
            
            # Click Browse using the correct selector
            print("Attempting to click Browse...")
            browse_btn = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "nav.main-menu li a[href*='subMenu-browse']"))
            )
            browse_btn.click()
            self._random_delay()
            time.sleep(2)

            print("Clicking Seasons...")
            # Re‑check for modal overlay before trying to hit the Seasons item.
            self._dismiss_cookie_modal_if_present(timeout=3.0)
            seasons_btn = self.wait.until(
                EC.element_to_be_clickable((By.LINK_TEXT, "Seasons"))
            )
            print("Clicking Seasons...2")
            seasons_btn.click()
            print("Clicking Seasons...3")
            self._random_delay()
            time.sleep(3)

            print("Clicking More Seasons...")
            # One more modal check here, as logs show the overlay sometimes appears by this point.
            self._dismiss_cookie_modal_if_present(timeout=3.0)

            # Wait for the More Seasons link to be present/clickable
            more_seasons_btn = self.wait.until(
                EC.element_to_be_clickable((By.LINK_TEXT, "More Seasons"))
            )

            print("Clicking More Seasons...2")
            # Try to scroll the element into view
            self.driver.execute_script("arguments[0].scrollIntoView(true);", more_seasons_btn)
            time.sleep(1)  # Wait for scroll to complete
            
            # Try regular click first
            try:
                more_seasons_btn.click()
                print("Clicked 'More Seasons' via normal click.")
            except ElementClickInterceptedException as e:
                print(f"'More Seasons' click intercepted (likely by overlay): {e}")
                # Attempt to clear modal/overlay and retry using JS click.
                self._dismiss_cookie_modal_if_present(timeout=5.0)
                try:
                    print("Retrying 'More Seasons' click via JavaScript after dismissing overlay...")
                    self.driver.execute_script("arguments[0].click();", more_seasons_btn)
                    print("'More Seasons' clicked via JavaScript after overlay dismissal.")
                except Exception as js_e:
                    print(f"JavaScript click on 'More Seasons' failed after overlay dismissal: {js_e}")
                    raise
            except Exception as e:
                print(f"Regular click on 'More Seasons' failed for non-intercept reason, trying JavaScript click: {e}")
                # If regular click fails, try JavaScript click
                self.driver.execute_script("arguments[0].click();", more_seasons_btn)
                print("'More Seasons' clicked via JavaScript fallback.")
            
            self._random_delay()
            
            # Wait for the page grid to load after clicking More Seasons
            print("Waiting for season grid to load...")
            try:
                self.wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "#pageGridFrame .dataGridElement"))
                )
                print("Season grid loaded successfully")
            except TimeoutException:
                print("Warning: Season grid did not appear within timeout, continuing anyway...")
            
            time.sleep(2)  # Additional wait for page to stabilize

            # Look for either season format
            season_options = self.get_season_text()
            season_found = False
            
            print(f"Looking for season options: {season_options}")
            
            # Function to check if season exists on current page with timeout handling
            def find_season_on_page(max_attempts=3):
                for attempt in range(max_attempts):
                    try:
                        print(f"Attempt {attempt + 1} to find season elements...")
                        # Wait a bit for elements to be available
                        time.sleep(1)
                        
                        # Get all season elements
                        season_elements = self.driver.find_elements(By.CSS_SELECTOR, "#pageGridFrame .dataGridElement .publicLogin a")
                        print(f"Found {len(season_elements)} season elements on current page")
                        
                        if len(season_elements) == 0:
                            print(f"No season elements found, waiting and retrying... (attempt {attempt + 1}/{max_attempts})")
                            time.sleep(2)
                            continue
                        
                        # Print all seasons for debugging
                        for elem in season_elements:
                            try:
                                season_text = elem.text.strip()
                                if season_text:  # Only print non-empty text
                                    print(f"Found season: {season_text}")
                                    if any(option in season_text for option in season_options):
                                        print(f"Found matching season: {season_text}")
                                        return elem
                            except Exception as e:
                                print(f"Error reading season element text: {e}")
                                continue
                        
                        # If we found elements but none matched, return None
                        if len(season_elements) > 0:
                            print("Found season elements but none matched the target season")
                            return None
                            
                    except Exception as e:
                        print(f"Error searching for season on page (attempt {attempt + 1}): {e}")
                        if attempt < max_attempts - 1:
                            time.sleep(2)
                            continue
                return None

            # Try to find season on current page first
            season_link = find_season_on_page()
            
            # If not found, try clicking through pages
            if not season_link:
                print("Season not found on first page, checking other pages...")
                page_num = 1
                max_pages = 20  # Limit to prevent infinite loops
                while page_num < max_pages:
                    try:
                        # Look for next page arrow
                        print(f"Looking for next page arrow (currently on page {page_num})...")
                        time.sleep(0.3)  # Wait for page to stabilize
                        
                        next_arrows = self.driver.find_elements(By.CSS_SELECTOR, "i.icon-arrow_r.dgNext")
                        print(f"Found {len(next_arrows)} next arrows")
                        
                        if not next_arrows:
                            print("No next arrows found - reached end of pages")
                            break
                            
                        next_arrow = next_arrows[0]
                        if not next_arrow.is_displayed():
                            print("Next arrow is not visible - reached end of pages")
                            break
                            
                        page_num += 1
                        print(f"Clicking next page (page {page_num})...")
                        next_arrow.click()
                        time.sleep(0.8)  # Wait for page to load
                        
                        # Wait for page grid to update
                        try:
                            self.wait.until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, "#pageGridFrame .dataGridElement"))
                            )
                        except TimeoutException:
                            print("Warning: Page grid did not update after clicking next")
                        
                        # Check if season exists on new page
                        season_link = find_season_on_page()
                        if season_link:
                            print(f"Found season on page {page_num}")
                            break
                            
                    except Exception as e:
                        print(f"Error navigating pages: {e}")
                        print(f"Current URL: {self.driver.current_url}")
                        print("Current page source (first 500 chars):")
                        try:
                            print(self.driver.page_source[:500])
                        except:
                            print("Could not get page source")
                        break
                
                if page_num >= max_pages:
                    print(f"Reached maximum page limit ({max_pages}), stopping search")

            if not season_link:
                raise Exception(f"Could not find season {self.season_year} (tried {season_options})")

            print(f"Found season link: {season_link.text}")
            try:
                season_link.click()
            except Exception:
                print("Regular click intercepted (likely ad overlay), trying JavaScript click...")
                self.driver.execute_script("arguments[0].click();", season_link)
            self._random_delay()

            # Handle the governing body selection popup
            print("Waiting for governing body selection popup...")
            try:
                gb_frame_elem = self.wait.until(
                    EC.presence_of_element_located((By.ID, "gbFrame"))
                )
                try:
                    print(f"'gbFrame' popup located. tag={gb_frame_elem.tag_name}, displayed={gb_frame_elem.is_displayed()}")
                except Exception:
                    print("'gbFrame' popup located (could not read tag/displayed safely).")
            except TimeoutException as te:
                print(f"Timed out waiting for 'gbFrame' governing body popup: {te}")
                raise

            # Select governing body from the dropdown
            if self.league == 'hs':
                print(f"Selecting {self.state} HS governing body from dropdown...")
            else:
                print("Selecting NCAA from dropdown...")
            try:
                gb_select_elem = self.wait.until(
                    EC.presence_of_element_located((By.ID, "gbId"))
                )
                print("Governing body dropdown element located...")
                select = Select(gb_select_elem)
                
                if self.league == 'hs':
                    # For HS, search for the governing body by text
                    found = False
                    for option in select.options:
                        option_text = option.text.strip()
                        # For HS Kentucky, check for various forms
                        if self.state == 'KY':
                            if ("Kentucky" in option_text or 
                                "KHSAA" in option_text.upper() or
                                option_text == "Kentucky High School Athletic Association"):
                                select.select_by_value(option.get_attribute("value"))
                                found = True
                                print(f"Selected governing body: {option_text}")
                                break
                        # For other states, use exact match
                        elif self.state in option_text:
                            select.select_by_value(option.get_attribute("value"))
                            found = True
                            print(f"Selected governing body: {option_text}")
                            break
                    
                    if not found:
                        print(f"Warning: Could not find governing body for {self.state} in dropdown")
                        print("Available options:")
                        for option in select.options:
                            print(f"  - {option.text}")
                        raise Exception(f"Could not find governing body for {self.state}")
                else:  # ncaa
                    select.select_by_value("3")  # 3 is the value for NCAA
                    print("NCAA governing body selected successfully.")
            except Exception as e:
                print(f"Error while selecting governing body from dropdown: {e}")
                raise
            
            # Click the Login button to submit
            print("Clicking Login button...")
            try:
                login_btn = self.wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "input[value='Login']"))
                )
                login_btn.click()
                print("Governing body Login button clicked successfully.")
            except Exception as e:
                print(f"Error while clicking Login button on governing body popup: {e}")
                raise
            self._random_delay()
            print("Finished navigate_to_season successfully")
            return True

        except Exception as e:
            error_msg = f"Error navigating to season: {e}"
            self._log_error("navigation", error_msg)
            print(f"Navigation error: {error_msg}")
            try:
                if self.driver:
                    print(f"Current URL when error occurred: {self.driver.current_url}")
            except Exception:
                pass

            # Best-effort debug: capture a small slice of the current page text
            try:
                body_text = self.driver.find_element(By.TAG_NAME, "body").text
                print("Body text (first 500 chars) at navigation failure:")
                print((body_text or "")[:500])
            except Exception:
                print("Could not read body text at navigation failure.")

            return False

    def get_teams(self):
        """Get list of teams from the pre-scraped JSON file or fall back to scraping from the season page."""
        try:
            # Determine team list file path based on league type
            if self.league == 'hs':
                # HS teams: data/team_lists/hs_ky_boys/teams.json or data/team_lists/hs_ky_girls/teams.json
                team_list_file = Path(f"data/team_lists/hs_{self.state.lower()}_{self.gender}/teams.json")
            else:  # ncaa
                # NCAA teams: data/team_lists/{season_year}/ncaa_d1_teams.json
                team_list_file = Path(f"data/team_lists/{self.season_year}/ncaa_d1_teams.json")
            
            if team_list_file.exists():
                league_label = f"{self.league.upper()}" if self.league == 'ncaa' else f"{self.state} HS {self.gender.capitalize()}"
                print(f"Loading teams from pre-scraped {league_label} list: {team_list_file}")
                with open(team_list_file, 'r') as f:
                    teams = json.load(f)
                
                print(f"Loaded {len(teams)} teams from JSON file")
                
                # Get the current session ID from the driver
                # We need to navigate to a page that has the session ID
                print("Getting current session ID...")
                try:
                    # Switch to PageFrame to get the session ID
                    self.driver.switch_to.frame("PageFrame")
                    current_url = self.driver.current_url
                    self.driver.switch_to.default_content()
                except Exception:
                    # If we can't get it from PageFrame, try the main URL
                    current_url = self.driver.current_url
                
                parsed_url = urlparse(current_url)
                query_params = parse_qs(parsed_url.query)
                session_id = query_params.get('twSessionId', [''])[0]
                
                if not session_id:
                    print("Warning: Could not extract session ID. Teams may need manual URL updates.")
                else:
                    print(f"Current session ID: {session_id}")
                
                # Update all team URLs with the current session ID
                for team in teams:
                    # Extract team ID from the existing URL
                    team_url = team.get("url", "")
                    if team_url:
                        team_parsed = urlparse(team_url)
                        team_params = parse_qs(team_parsed.query)
                        team_id = team_params.get('teamId', [''])[0]
                        
                        if team_id and session_id:
                            # Update URL with current session ID
                            team["url"] = f"{BASE_URL}/seasons/TeamSchedule.jsp?twSessionId={session_id}&teamId={team_id}"
                        elif not team_id:
                            print(f"Warning: Could not extract team ID from URL for team: {team.get('name', 'Unknown')}")
                
                print(f"Successfully loaded and updated {len(teams)} D1 teams from JSON file")
                return teams
            else:
                print(f"D1 team list not found at {team_list_file}")
                print("Falling back to scraping teams from website...")
            
            # Fall back to scraping from website if JSON file doesn't exist
            print("Waiting for PageFrame...")
            # Add a longer delay after login to handle cookie consent
            time.sleep(5)
            
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
                        team = {
                            "name": team_data[1],  # Team Name
                            "state": team_data[2],  # State
                            "abbreviation": team_data[3],  # Abbr
                            "governing_body": team_data[4],  # Gov. Body
                            "division": team_data[5] if len(team_data) > 5 else "Unknown",  # Division
                            "url": f"{BASE_URL}/seasons/TeamSchedule.jsp?twSessionId={session_id}&teamId={team_id}"  # Construct URL with both session ID and team ID
                        }
                        
                        teams.append(team)
                        print(f"Processed team: {team['name']} ({team['state']}) - {team['division']}")
                        
                    except Exception as e:
                        print(f"Error processing team data: {e}")
                        continue
                
                print(f"Successfully processed {len(teams)} teams")
                # Removed the call to save_teams_to_db
                return teams
                
            except Exception as e:
                print(f"Error parsing teams data: {e}")
                print(f"Raw JSON string: {teams_json[:200]}...")  # Print first 200 chars of raw JSON for debugging
                return []
            
        except Exception as e:
            print(f"Error in get_teams: {e}")
            return []
        finally:
            # Switch back to default content
            try:
                self.driver.switch_to.default_content()
                print("Switched back to default content")
            except Exception as e:
                print(f"Error switching back to default content: {e}")

    def get_wrestler_id_from_url(self, url: str) -> Optional[str]:
        """Extract wrestler ID from URL."""
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        return params.get("wrestlerId", [None])[0]

    def scrape_matches(self, wrestler_id: str) -> List[Dict]:
        """Scrape match history for a wrestler."""
        matches = []
        try:
            # Wait for matches table to load
            match_rows = self.wait.until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "table.tw-table tbody tr"))
            )

            for row in match_rows:
                cols = row.find_elements(By.TAG_NAME, "td")
                if len(cols) < 6:  # Basic validation of table structure
                    continue

                match_data = {
                    "date": cols[0].text.strip().split("-")[-1].strip(),  # Take last date if range
                    "event_name": cols[1].text.strip(),
                    "weight_class": cols[2].text.strip(),
                    "opponent_name": cols[3].text.strip(),
                    "result": cols[4].text.strip(),
                    "win_type": cols[5].text.strip()
                }

                # Try to get opponent_id from link
                opponent_link = cols[3].find_elements(By.TAG_NAME, "a")
                if opponent_link:
                    match_data["opponent_id"] = self.get_wrestler_id_from_url(
                        opponent_link[0].get_attribute("href")
                    )

                matches.append(match_data)

        except Exception as e:
            error_msg = f"Error scraping matches for wrestler {wrestler_id}: {e}"
            self._log_error("match_scraping", error_msg)
            return []

        return matches

    def scrape_team(self, team_url: str, team_info: Dict) -> Optional[Dict]:
        """Scrape data for a single team."""
        # Reset debug flag for each team
        self._debug_printed = False
        try:
            print(f"\n=== Starting to scrape team: {team_url} ===")
            print(f"Team name from list: {team_info['name']} ({team_info['abbreviation']})")
            
            # Create team_data dictionary once at the start
            team_data = {
                "team_name": team_info["name"],
                "abbreviation": team_info["abbreviation"],
                "season": self.season_year,
                "division": team_info["division"],
                "roster": []
            }
            
            self.driver.get(team_url)
            time.sleep(2)  # Wait for page to load

            # Click the Roster tab first
            print("\nClicking Roster tab...")
            roster_tab = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href*='TeamRoster.jsp']"))
            )
            roster_tab.click()
            time.sleep(2)  # Wait for roster page to load

            # Now get the roster information
            print("\nGetting roster information...")
            roster_info = {}
            ineligible_wrestlers = set()  # Track ineligible wrestlers by name
            eligible_wrestlers = set()  # Track eligible wrestlers by name
            
            # Load eligibility overrides early to check during roster scan
            season_str = str(self.season_year) if self.season_year else ""
            override_wrestler_names = set()
            for override in self.eligibility_overrides:
                override_team = override.get("team", "")
                override_season = override.get("season", "")
                if (override_team == team_info.get("name", "") and override_season == season_str):
                    override_wrestler_names.add(override.get("wrestler_name", ""))
            
            # Wait for and get the roster table
            roster_table = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table.dataGrid"))
            )
            
            # Get all rows except header
            roster_rows = roster_table.find_elements(By.CSS_SELECTOR, "tr.dataGridRow, tr.dataGridRowAlt")
            print(f"Found {len(roster_rows)} roster rows")
            
            # First pass - collect all eligible and ineligible wrestlers
            for row in roster_rows:
                try:
                    cols = row.find_elements(By.TAG_NAME, "td")
                    if len(cols) >= 6:  # Make sure we have enough columns
                        name = cols[1].text.strip()
                        mwc = cols[3].text.strip()  # MWC (Minimum Weight Class)
                        weight_class = cols[5].text.strip() if len(cols) > 5 else ""  # Actual Weight Class
                        
                        # Grade column: Based on screenshot column order:
                        # 0: Icon, 1: Name, 2: Eligible, 3: MWC, 4: MWW, 5: Wt. Class, 6: Gender, 7: Grade, 8: Record
                        # Grade should be at cols[7] (8th column, 0-indexed)
                        grade = ""
                        grade_patterns = ["So.", "Jr.", "Sr.", "Fr.", "7th", "8th", "9th", "10th", "11th", "12th", 
                                         "Freshman", "Sophomore", "Junior", "Senior"]
                        
                        # Try cols[7] first (expected location)
                        if len(cols) > 7:
                            potential_grade = cols[7].text.strip()
                            if any(pattern in potential_grade for pattern in grade_patterns) or \
                               potential_grade in ["So.", "Jr.", "Sr.", "Fr.", "7th", "8th", "9th", "10th", "11th", "12th"]:
                                grade = potential_grade
                            else:
                                # If cols[7] doesn't match grade pattern, search other columns
                                for i in range(min(len(cols), 12)):
                                    if i == 7:  # Skip the one we already checked
                                        continue
                                    potential_grade = cols[i].text.strip()
                                    if any(pattern in potential_grade for pattern in grade_patterns) or \
                                       potential_grade in ["So.", "Jr.", "Sr.", "Fr.", "7th", "8th", "9th", "10th", "11th", "12th"]:
                                        grade = potential_grade
                                        # Debug: Print which column had the grade (only once)
                                        if name and not hasattr(self, '_debug_printed'):
                                            print(f"DEBUG: Found grade '{grade}' for {name} in cols[{i}] (not cols[7])")
                                            print(f"DEBUG: cols[7] was '{cols[7].text.strip()}'")
                                            self._debug_printed = True
                                        break
                                
                                # If still not found, use cols[7] anyway (might be empty or wrong)
                                if not grade:
                                    grade = cols[7].text.strip()
                                    # Debug output
                                    if name and not hasattr(self, '_debug_printed'):
                                        print(f"DEBUG: Using cols[7]='{grade}' for {name} (didn't match grade patterns)")
                                        print(f"DEBUG: All columns for {name}:")
                                        for j, col in enumerate(cols[:12]):
                                            print(f"  cols[{j}]: '{col.text.strip()}'")
                                        self._debug_printed = True
                        else:
                            grade = ""  # Fallback if not enough columns
                            if name and not hasattr(self, '_debug_printed'):
                                print(f"DEBUG: Only {len(cols)} columns found for {name}, expected at least 8")
                                for i, col in enumerate(cols):
                                    print(f"  cols[{i}]: '{col.text.strip()}'")
                                self._debug_printed = True
                        
                        # Check eligibility icons in the correct column
                        eligible_cell = cols[2]
                        cell_html = eligible_cell.get_attribute('innerHTML')
                        
                        # Check for eligibility status
                        if 'greenIcon' in cell_html:
                            eligible_wrestlers.add(name)
                            # Store roster info for eligible wrestlers using ACTUAL weight class (cols[5]), not MWC
                            # This matches what we use when looking up from the dropdown
                            # Normalize name and weight class for consistent key matching
                            normalized_name = name.strip()
                            normalized_weight_class = weight_class.strip() if weight_class else ""
                            if normalized_weight_class:  # Only store if we have a weight class
                                key = f"{normalized_name}_{normalized_weight_class}"
                                roster_info[key] = grade
                                print(f"Found eligible entry for: {name} ({normalized_weight_class}) - {grade}")
                            else:
                                # Fallback to MWC if weight class not available
                                normalized_mwc = mwc.strip() if mwc else ""
                                if normalized_mwc:
                                    key = f"{normalized_name}_{normalized_mwc}"
                                    roster_info[key] = grade
                                    print(f"Found eligible entry for: {name} ({normalized_mwc}) - {grade} [using MWC]")
                        elif 'redIcon' in cell_html and name not in eligible_wrestlers:
                            ineligible_wrestlers.add(name)
                            # Store roster info for override wrestlers (even if ineligible)
                            if name in override_wrestler_names and weight_class:  # Only store if weight_class is not empty
                                key = f"{name}_{weight_class}"
                                roster_info[key] = grade
                                print(f"Found ineligible entry for override wrestler: {name} ({weight_class}) - {grade} [storing roster info]")
                            else:
                                print(f"Found ineligible entry for: {name} ({weight_class if weight_class else mwc}) - {grade}")
                except Exception as e:
                    print(f"Error processing roster row: {e}")
                    continue

            # Second pass - remove any wrestlers from ineligible set if they have an eligible entry
            for name in list(ineligible_wrestlers):
                if name in eligible_wrestlers:
                    ineligible_wrestlers.remove(name)
                    print(f"Removed {name} from ineligible list due to having an eligible entry")
            
            # Third pass - apply eligibility overrides
            season_str = str(self.season_year) if self.season_year else ""
            overrides_applied = []
            for override in self.eligibility_overrides:
                override_team = override.get("team", "")
                override_season = override.get("season", "")
                override_name = override.get("wrestler_name", "")
                override_reason = override.get("reason", "")
                
                # Check if this override applies to current team/season
                if (override_team == team_info.get("name", "") and 
                    override_season == season_str and 
                    override_name in ineligible_wrestlers):
                    # Remove from ineligible and add to eligible
                    ineligible_wrestlers.remove(override_name)
                    eligible_wrestlers.add(override_name)
                    overrides_applied.append((override_name, override_reason))
                    print(f"✓ Eligibility override applied: {override_name} (Reason: {override_reason})")
            
            # Print final eligibility counts
            print(f"\nFinal eligibility status:")
            print(f"Total eligible wrestlers: {len(eligible_wrestlers)}")
            print(f"Total ineligible wrestlers: {len(ineligible_wrestlers)}")
            if overrides_applied:
                print(f"Eligibility overrides applied: {len(overrides_applied)}")
            if ineligible_wrestlers:
                print("Ineligible wrestlers that will be skipped:")
                for name in ineligible_wrestlers:
                    print(f"- {name}")

            # Now get the matches information
            print("\nGetting matches information...")
            matches_link = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='WrestlerMatches.jsp']"))
            )
            print("Found Matches link, clicking...")
            self.driver.execute_script("arguments[0].click();", matches_link)
            print("Clicked Matches link")
            time.sleep(2)  # Wait for page update

            # Now find the wrestler dropdown in pageGridFrame
            print("\nLooking for wrestler dropdown...")
            wrestler_select = self.wait.until(
                EC.presence_of_element_located((By.ID, "wrestler"))
            )
            print("Found wrestler dropdown")
            
            # Get the options
            wrestler_options = Select(wrestler_select).options
            print(f"\nFound {len(wrestler_options)} wrestlers in dropdown")
            
            # Store wrestler info before processing
            wrestler_info = []
            
            # Build override lookup: name -> {weight_class, reason}
            override_lookup = {}
            season_str = str(self.season_year) if self.season_year else ""
            for override in self.eligibility_overrides:
                override_team = override.get("team", "")
                override_season = override.get("season", "")
                if (override_team == team_info.get("name", "") and override_season == season_str):
                    override_name = override.get("wrestler_name", "")
                    override_lookup[override_name] = {
                        "weight_class": override.get("weight_class", ""),
                        "reason": override.get("reason", "")
                    }
            
            for option in wrestler_options[1:]:  # Skip first option (placeholder)
                try:
                    wrestler_id = option.get_attribute("value")
                    wrestler_name = option.text.strip()
                    
                    # Check if this wrestler has a weight class prefix
                    has_weight_class = " - " in wrestler_name
                    
                    if not has_weight_class:
                        # No weight class prefix - check skip config, override, or skip
                        skip_validation = (team_info.get("name", ""), season_str) in SKIP_WEIGHT_VALIDATION_TEAMS
                        if skip_validation:
                            # Team/season in config: accept wrestler and try roster lookup for weight/grade
                            weight_class = ""
                            grade = ""
                            normalized_name = wrestler_name.strip()
                            matching_keys = [k for k in roster_info.keys() if k.startswith(normalized_name + "_")]
                            if len(matching_keys) == 1:
                                key = matching_keys[0]
                                weight_class = key[len(normalized_name) + 1:].strip()
                                grade = roster_info.get(key, "")
                            elif matching_keys:
                                key = matching_keys[0]
                                weight_class = key[len(normalized_name) + 1:].strip()
                                grade = roster_info.get(key, "")
                            print(f"✓ Accepting wrestler without weight prefix (team in skip config): {wrestler_name}" + (f" ({weight_class})" if weight_class else ""))
                        elif wrestler_name in override_lookup:
                            # This is an override wrestler - get weight class from override file
                            override_info = override_lookup[wrestler_name]
                            weight_class = override_info.get("weight_class", "")
                            grade = ""
                            
                            # Try to find grade from roster_info if available
                            if weight_class:
                                key = f"{wrestler_name}_{weight_class}"
                                grade = roster_info.get(key, "")
                                print(f"✓ Override wrestler {wrestler_name} using weight class {weight_class} from override file")
                            else:
                                # No weight class in override file - skip with warning
                                print(f"⚠ Override wrestler {wrestler_name} has no weight_class in override file - skipping")
                                continue
                        else:
                            # Not an override wrestler - skip normally
                            print(f"Skipping entry without weight class: {wrestler_name}")
                            continue
                    else:
                        # Extract weight class from name (e.g., "125 - Gerald Huff")
                        weight_class, wrestler_name = wrestler_name.split(" -", 1)
                        weight_class = weight_class.strip()
                        wrestler_name = wrestler_name.strip()
                        grade = ""  # Initialize grade for regular wrestlers
                    
                    # Skip if wrestler was marked as ineligible (unless overridden)
                    if wrestler_name in ineligible_wrestlers and wrestler_name not in override_lookup:
                        print(f"Skipping matches for ineligible wrestler: {wrestler_name}")
                        continue
                    
                    # Look up grade from roster info (if not already found)
                    if not grade:
                        # Normalize name and weight class for consistent key matching
                        normalized_wrestler_name = wrestler_name.strip()
                        normalized_weight_class = weight_class.strip() if weight_class else ""
                        key = f"{normalized_wrestler_name}_{normalized_weight_class}"
                        grade = roster_info.get(key, "")
                        # Debug: Print lookup attempt for first few failures
                        if not grade and wrestler_name and not hasattr(self, '_lookup_debug_count'):
                            self._lookup_debug_count = 0
                        if not grade and wrestler_name and hasattr(self, '_lookup_debug_count') and self._lookup_debug_count < 3:
                            print(f"\nDEBUG: Grade lookup failed for {wrestler_name} (weight_class: {normalized_weight_class})")
                            print(f"DEBUG: Lookup key was: '{key}'")
                            print(f"DEBUG: Available keys in roster_info (first 10): {list(roster_info.keys())[:10]}")
                            # Try to find a matching key
                            matching_keys = [k for k in roster_info.keys() if normalized_wrestler_name in k]
                            if matching_keys:
                                print(f"DEBUG: Keys containing '{normalized_wrestler_name}': {matching_keys[:5]}")
                            self._lookup_debug_count += 1
                    
                    wrestler_info.append({
                        "id": wrestler_id,
                        "name": wrestler_name,
                        "weight_class": weight_class,
                        "grade": grade
                    })
                    print(f"Added wrestler: {wrestler_name} ({weight_class}) - Grade: {grade}")
                except Exception as e:
                    print(f"Error getting wrestler info: {e}")
                    continue
            
            # Track whether the previous wrestler definitively had matches
            prev_had_matches: Optional[bool] = None

            # Process each wrestler's matches
            for info in wrestler_info:
                # Retry loop for stale element errors
                stale_retry_attempts = 0
                max_stale_retries = 3
                wrestler_processed = False
                
                while not wrestler_processed and stale_retry_attempts < max_stale_retries:
                    try:
                        if stale_retry_attempts > 0:
                            print(f"\n🔄 Retry attempt #{stale_retry_attempts} for wrestler {info['name']} after stale element error...")
                        
                        print(f"\n=== Processing wrestler: {info['name']} ({info['weight_class']}) - Grade: {info['grade']} ===")
                        
                        # Re-find the dropdown each time
                        print("Re-finding wrestler dropdown...")
                        wrestler_select = self.wait.until(
                            EC.presence_of_element_located((By.ID, "wrestler"))
                        )
                        print("Found dropdown, selecting wrestler...")
                        
                        # Select the wrestler
                        try:
                            old_table = self.driver.find_element(By.CSS_SELECTOR, "table.dataGrid")
                        except Exception:
                            old_table = None
                        Select(wrestler_select).select_by_value(info["id"])
                        print(f"Selected wrestler: {info['name']}")
                        
                        # Wait for the previous table to go stale to ensure re-render
                        try:
                            if old_table is not None:
                                self.wait.until(EC.staleness_of(old_table))
                        except Exception:
                            pass
                        
                        # Give the data grid a brief moment to refresh before inspecting rows.
                        # This helps avoid reading an intermediate "empty" state before matches load.
                        time.sleep(1.2)
                        
                        # Lightweight hydration check; empties are handled explicitly below
                        status = self._verify_wrestler_table_hydrated(info["id"], timeout_sec=8.0)
                        if status == "timeout":
                            print("⚠️ Could not positively confirm table hydration for this wrestler — proceeding with explicit checks")
                        else:
                            print("Table appears hydrated for this wrestler")

                        # Ensure we have a table element to work with
                        table = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.dataGrid")))
                        print("Found match table")
                        
                        # DIAGNOSTIC: Print raw HTML of the match table section
                        print(f"\n=== DIAGNOSTIC HTML for {info['name']} ===")
                        try:
                            table_html = table.get_attribute('outerHTML')
                            print(f"Table HTML (first 500 chars): {table_html[:500]}")
                            
                            # Check for "no matches" text
                            page_text = self.driver.find_element(By.TAG_NAME, "body").text
                            if "no matches" in page_text.lower():
                                print(f"'No matches' text found on page: {page_text[:200]}")
                            
                            # Check for where wrestler name might appear
                            name_variants = self._get_name_variants(info['name'], team_info['name'], self.season_year)
                            if self._text_has_any(page_text, name_variants):
                                print(f"Wrestler name (alias-aware) found in page text")
                                # Try to locate where in the text
                                # Use the first matching variant for context
                                variant = next((v for v in name_variants if v.lower() in page_text.lower()), None)
                                name_pos = page_text.lower().find(variant.lower()) if variant else -1
                                context = page_text[max(0, name_pos-50):min(len(page_text), name_pos+150)]
                                print(f"Name context: {context}")
                            else:
                                print(f"WARNING: Wrestler name (alias-aware) NOT found in page text")
                                
                        except Exception as e:
                            print(f"Error during HTML diagnostics: {e}")
                        print("=== END DIAGNOSTIC ===\n")
                        
                        # Get all rows from the table
                        rows = table.find_elements(By.TAG_NAME, "tr")
                        print(f"Found {len(rows)} total rows in table")
                        
                        # Skip the first row (dropdown) and the two header rows
                        match_rows = [row for row in rows[3:] if row.get_attribute("class") == "dataGridRow"]
                        print(f"Found {len(match_rows)} match rows after filtering")
                        
                        # Initialize matches list and tracking variables outside the if statement
                        matches = []
                        wrestler_verified = False
                        skipped_rows = 0
                        
                        # Special handling for wrestlers with no matches
                        if len(match_rows) == 0:
                            no_matches_message = "There are no matches associated with this wrestler"
                            try:
                                grid_text = table.text or ""
                            except Exception:
                                grid_text = ""
                            has_no_matches_banner = no_matches_message.lower() in grid_text.lower()

                            if has_no_matches_banner:
                                # Case 1: previous wrestler had matches (or this is the first wrestler)
                                if prev_had_matches is True or prev_had_matches is None:
                                    print(f"No matches found for {info['name']} - message: '{no_matches_message}' - recording as verified (previous wrestler had matches or none).")
                                    wrestler_verified = True
                                    matches = []  # Empty matches list
                                    prev_had_matches = False
                                else:
                                    # Case 2: consecutive 'no matches' wrestlers — re-click Matches tab
                                    # to fully reset the page, then treat this wrestler like the first
                                    # one after a fresh load.
                                    print(f"Consecutive 'no matches' wrestlers detected (previous also had no matches). Re-clicking Matches tab and reloading {info['name']}...")
                                    try:
                                        # Click the Matches tab again to reload WrestlerMatches.jsp
                                        matches_link = self.wait.until(
                                            EC.presence_of_element_located(
                                                (By.CSS_SELECTOR, "a[href*='WrestlerMatches.jsp']")
                                            )
                                        )
                                        self.driver.execute_script("arguments[0].click();", matches_link)
                                        print("Clicked Matches tab to reset matches page.")
                                    except Exception as e:
                                        print(f"Error while clicking Matches tab to reset page: {e}")

                                    # Wait briefly for the base "You must select a wrestler..." state
                                    base_confirmed = False
                                    try:
                                        deadline = time.time() + 10.0
                                        while time.time() < deadline:
                                            try:
                                                base_table = self.driver.find_element(By.CSS_SELECTOR, "table.dataGrid")
                                                base_text = (base_table.text or "").lower()
                                                if "you must select a wrestler to view matches for." in base_text:
                                                    base_confirmed = True
                                                    break
                                            except Exception:
                                                pass
                                            time.sleep(0.5)
                                    except Exception:
                                        pass

                                    if base_confirmed:
                                        print("Confirmed base Matches state ('You must select a wrestler to view matches for.'). Treating this wrestler like the first after a fresh load.")
                                    else:
                                        print("Warning: Did not see base 'You must select a wrestler to view matches for.' message after clicking Matches; proceeding cautiously.")

                                    # Re-select the current wrestler and re-evaluate rows/banner
                                    try:
                                        wrestler_select_reload = self.wait.until(
                                            EC.presence_of_element_located((By.ID, "wrestler"))
                                        )
                                        Select(wrestler_select_reload).select_by_value(info["id"])
                                        print(f"Re-selected wrestler after Matches reset: {info['name']}")

                                        table = self.wait.until(
                                            EC.presence_of_element_located((By.CSS_SELECTOR, "table.dataGrid"))
                                        )
                                        rows = table.find_elements(By.TAG_NAME, "tr")
                                        match_rows = [
                                            row for row in rows[3:] if row.get_attribute("class") == "dataGridRow"
                                        ]
                                        print(f"After Matches reset, found {len(match_rows)} match rows")

                                        try:
                                            grid_text = table.text or ""
                                        except Exception:
                                            grid_text = ""
                                        if len(match_rows) == 0 and no_matches_message.lower() in grid_text.lower():
                                            # After a full Matches reload and re-selection, treat this like
                                            # the first wrestler: trust the banner as accurate.
                                            print(f"No matches found for {info['name']} after Matches reset - message: '{no_matches_message}' - recording as verified.")
                                            wrestler_verified = True
                                            matches = []  # Empty matches list
                                            prev_had_matches = False
                                        else:
                                            # If we now see real matches, or the banner disappeared, update prev_had_matches accordingly
                                            prev_had_matches = bool(match_rows)
                                    except Exception as e:
                                        print(f"Error while re-selecting wrestler after Matches reset: {e}")
                            # If there are no match rows and no banner, leave wrestler_verified as-is;
                            # downstream verification / re-navigation logic will handle ambiguous states.
                        
                        # Hard-coded exception for specific wrestlers with known bad data
                        if self.season_year == 2014 and (
                            info['name'] == "Calvin Campbell" or 
                            info['name'] == "Garett Hammond"):
                            
                            # Check if known bad wrestler data is visible
                            page_text = self.driver.find_element(By.TAG_NAME, "body").text
                            
                            if info['name'] == "Calvin Campbell" and "Vito Pasone" in page_text:
                                warning_msg = f"Known data issue: Skipping verification for {info['name']} (showing Vito Pasone) in team {team_info['name']}"
                                self._log_error("verification_override", warning_msg)
                                print(f"⚠️ {warning_msg}")
                                wrestler_verified = True  # Skip verification
                                
                            elif info['name'] == "Garett Hammond" and "Garrett Hildebrand" in page_text:
                                warning_msg = f"Known data issue: Skipping verification for {info['name']} (showing Garett Hildebrand) in team {team_info['name']}"
                                self._log_error("verification_override", warning_msg)
                                print(f"⚠️ {warning_msg}")
                                wrestler_verified = True  # Skip verification
                        
                        # Joe Lemmon/Dane Lemmon exception for Navy in 2015 season
                        elif self.season_year == 2015 and info['name'] == "Joe Lemmon" and team_info['name'] == "Navy":
                            warning_msg = f"Known data issue: Skipping verification for {info['name']} (listed as Dane Lemmon) in team {team_info['name']}"
                            self._log_error("verification_override", warning_msg)
                            print(f"⚠️ {warning_msg}")
                            wrestler_verified = True  # Skip verification
                        
                        # Eric Hess/Eric Ness exception for Navy in 2015 season
                        elif self.season_year == 2015 and info['name'] == "Eric Hess" and team_info['name'] == "Navy":
                            warning_msg = f"Known data issue: Skipping verification for {info['name']} (listed as Eric Ness) in team {team_info['name']}"
                            self._log_error("verification_override", warning_msg)
                            print(f"⚠️ {warning_msg}")
                            wrestler_verified = True  # Skip verification

                        # Eric Hess/Eric Ness exception for Navy in 2015 season
                        elif self.season_year == 2017 and info['name'] == "Jeremy Nurnberger" and team_info['name'] == "Centenary University(NJ)":
                            warning_msg = f"Known data issue: Skipping verification for {info['name']} (listed as Jeremy Nurnberger) in team {team_info['name']}"
                            self._log_error("verification_override", warning_msg)
                            print(f"⚠️ {warning_msg}")
                            wrestler_verified = True  # Skip verification

                        # Eric Hess/Eric Ness exception for Navy in 2015 season
                        elif self.season_year == 2017 and info['name'] == "Christian Messick" and team_info['name'] == "Central (IA)":
                            warning_msg = f"Known data issue: Skipping verification for {info['name']} (listed as Christian Messick) in team {team_info['name']}"
                            self._log_error("verification_override", warning_msg)
                            print(f"⚠️ {warning_msg}")
                            wrestler_verified = True  # Skip verification       

                        # Eric Hess/Eric Ness exception for Navy in 2015 season
                        elif self.season_year == 2018 and info['name'] == "Araad Fisher" and team_info['name'] == "Duke":
                            warning_msg = f"Known data issue: Skipping verification for {info['name']} (listed as Araad Fisher) in team {team_info['name']}"
                            self._log_error("verification_override", warning_msg)
                            print(f"⚠️ {warning_msg}")
                            wrestler_verified = True  # Skip verification

                        # Eric Hess/Eric Ness exception for Navy in 2015 season
                        elif self.season_year == 2018 and info['name'] == "Brendan O`Hara" and team_info['name'] == "Princeton":
                            warning_msg = f"Known data issue: Skipping verification for {info['name']} (listed as Brendan O`Hara) in team {team_info['name']}"
                            self._log_error("verification_override", warning_msg)
                            print(f"⚠️ {warning_msg}")
                            wrestler_verified = True  # Skip verification   

                        
                        if match_rows:
                            # We have concrete matches for this wrestler
                            prev_had_matches = True
                            print("\nProcessing match rows...")
                            
                            for i, row in enumerate(match_rows):
                                try:
                                    print(f"\nProcessing match row {i+1}:")
                                    cols = row.find_elements(By.TAG_NAME, "td")
                                    print(f"Found {len(cols)} columns in row")
                                
                                    if len(cols) < 5:
                                        print("Skipping row - not enough columns")
                                        continue
                                    
                                    summary = cols[4].text.strip()
                                    print(f"Raw summary: {summary}")
                                
                                    # Skip double forfeit matches
                                    if "Double Forfeit" in summary:
                                        print("Match is a double forfeit - skipping this match")
                                        continue
                                
                                    # Check if this match contains the wrestler's name (alias-aware)
                                    name_variants = self._get_name_variants(info['name'], team_info['name'], self.season_year)
                                
                                    # Alias-aware check: for byes/forfeits, still verify name appears
                                    lower_summary = summary.lower()
                                    is_bye_or_forfeit = ("received a bye" in lower_summary or
                                                        "forfeit" in lower_summary or
                                                        "(for.)" in lower_summary or
                                                        "(ff)" in lower_summary)
                                
                                    if is_bye_or_forfeit:
                                        # For byes/forfeits, verify the wrestler's name appears in the summary
                                        if self._text_has_any(summary, name_variants):
                                            print("Detected bye/forfeit with wrestler name — marking as verified for this row")
                                            wrestler_verified = True
                                        else:
                                            print(f"⚠️ WARNING: Bye/forfeit summary does not contain wrestler (alias-aware) '{info['name']}': '{summary}'")
                                
                                    if not wrestler_verified and not self._text_has_any(summary, name_variants):
                                        # Only start passive waiting if we haven't verified the wrestler yet
                                        if not wrestler_verified:
                                            print(f"⚠️ WARNING: Match summary does not contain wrestler (alias-aware) '{info['name']}'")
                                        
                                            # Quick scan of all match rows to see if the wrestler's name appears in any of them
                                            matches_with_name = 0
                                        
                                            print(f"Scanning all {len(match_rows)} matches to see if wrestler name appears in at least two...")
                                            for scan_row in match_rows:
                                                try:
                                                    scan_cols = scan_row.find_elements(By.TAG_NAME, "td")
                                                    if len(scan_cols) >= 5:
                                                        scan_summary = scan_cols[4].text.strip()
                                                        if self._text_has_any(scan_summary, name_variants):
                                                            matches_with_name += 1
                                                            print(f"✅ Found wrestler (alias-aware) in match summary: '{scan_summary}'")
                                                            if matches_with_name >= 2:
                                                                break
                                                except Exception as e:
                                                    print(f"Error during match row scan: {e}")
                                                    continue
                                        
                                            # If name found in at least two matches, mark as verified and continue
                                            if matches_with_name >= 2:
                                                print(f"Wrestler '{info['name']}' appears in {matches_with_name} matches. Continuing without retry.")
                                                wrestler_verified = True
                                                # Continue processing all matches, including those without the wrestler's name
                                            else:
                                                # Name not found in any match, proceed with original retry logic
                                                print(f"Wrestler (alias-aware) '{info['name']}' not found in any match summaries.")
                                                print(f"DEBUG: Full summary text: '{summary}'")
                                            
                                                # Check for name variants or encoding issues
                                                for variant in [
                                                    info['name'].replace("'", "`"),
                                                    info['name'].replace("'", "'"),
                                                    info['name'].replace("'", "&#39;"),
                                                    info['name'].replace(" ", "")
                                                ]:
                                                    if variant in summary:
                                                        print(f"DEBUG: Found variant '{variant}' in summary")
                                            
                                                print("Page may not have fully loaded. Waiting for data to update...")
                                        
                                            # Begin passive waiting loop
                                            retry_count = 1
                                            max_retries = 3  # Will wait for about 15 seconds (3 * 5 seconds)
                                            wrestler_found = False
                                        
                                            while not wrestler_found and retry_count <= max_retries:
                                                try:
                                                    print(f"Passive wait attempt #{retry_count}...")
                                                    # Wait for 5 seconds and check again
                                                    time.sleep(5)
                                                
                                                    # Get updated data from the current row without reselecting
                                                    updated_summary = cols[4].text.strip()
                                                
                                                    # Check if we found the wrestler now (alias-aware)
                                                    if self._text_has_any(updated_summary, name_variants):
                                                        print(f"✅ SUCCESS: Found wrestler (alias-aware) in match summary after {retry_count} retries")
                                                        summary = updated_summary  # Update the summary with the correct one
                                                        wrestler_found = True
                                                        wrestler_verified = True
                                                        break
                                                    else:
                                                        # Still not found
                                                        print(f"⚠️ Retry #{retry_count}: Still can't find wrestler (alias-aware) in summary: '{updated_summary}'")
                                                        retry_count += 1
                                                except Exception as e:
                                                    print(f"❌ Error during passive wait: {e}")
                                                    retry_count += 1
                                        
                                            # If we didn't find the wrestler after max retries and this is our first check
                                            if not wrestler_found and not wrestler_verified:
                                                # Try re-navigating to the team up to 3 times
                                                renavigation_attempts = 0
                                                renavigation_success = False
                                            
                                                while renavigation_attempts < 3 and not renavigation_success:
                                                    renavigation_attempts += 1
                                                    print(f"\n⏳ Attempt #{renavigation_attempts} to re-navigate to team {team_info['name']} and find wrestler {info['name']}...")
                                                
                                                    try:
                                                        # Instead of trying to navigate through the UI, use direct URL navigation
                                                        print("Directly navigating back to the team page via URL...")
                                                    
                                                        # First get the current URL to extract the session ID
                                                        current_url = self.driver.current_url
                                                        parsed_url = urlparse(current_url)
                                                        query_params = parse_qs(parsed_url.query)
                                                        session_id = query_params.get('twSessionId', [''])[0]
                                                    
                                                        if not session_id:
                                                            print("⚠️ Could not extract session ID from current URL. Using original team URL.")
                                                            team_page_url = team_url
                                                        else:
                                                            # Extract team ID from the team URL
                                                            team_parsed_url = urlparse(team_url)
                                                            team_params = parse_qs(team_parsed_url.query)
                                                            team_id = team_params.get('teamId', [''])[0]
                                                        
                                                            if not team_id:
                                                                print("⚠️ Could not extract team ID from team URL. Using original team URL.")
                                                                team_page_url = team_url
                                                            else:
                                                                # Construct URL with session ID and team ID
                                                                team_page_url = f"{BASE_URL}/seasons/TeamSchedule.jsp?twSessionId={session_id}&teamId={team_id}"
                                                    
                                                        # Navigate directly to the team page
                                                        print(f"Navigating to team page: {team_page_url}")
                                                        self.driver.get(team_page_url)
                                                        time.sleep(3)  # Wait for page to load
                                                    
                                                        # Click on the Matches tab
                                                        print("Clicking on Matches tab...")
                                                        matches_link = self.wait.until(
                                                            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='WrestlerMatches.jsp']"))
                                                        )
                                                        self.driver.execute_script("arguments[0].click();", matches_link)
                                                        time.sleep(3)  # Wait for matches page to load
                                                    
                                                        # Find the wrestler dropdown
                                                        print("Finding wrestler dropdown...")
                                                        wrestler_select = self.wait.until(
                                                            EC.presence_of_element_located((By.ID, "wrestler"))
                                                        )
                                                    
                                                        # Select the wrestler
                                                        print(f"Selecting wrestler: {info['name']}...")
                                                        try:
                                                            prev_table = self.driver.find_element(By.CSS_SELECTOR, "table.dataGrid")
                                                        except Exception:
                                                            prev_table = None
                                                        Select(wrestler_select).select_by_value(info["id"])
                                                        # Prefer staleness to ensure re-render
                                                        try:
                                                            if prev_table is not None:
                                                                self.wait.until(EC.staleness_of(prev_table))
                                                        except Exception:
                                                            pass
                                                        # Verify hydration for this wrestler before proceeding
                                                        status = self._verify_wrestler_table_hydrated(info["id"], timeout_sec=8.0)
                                                        if status == "timeout":
                                                            print("⚠️ Retry: Table did not hydrate after selection; will retry re-navigation")
                                                            continue
                                                    
                                                        # Wait for the table to be present and visible
                                                        print("Looking for match table...")
                                                        table = self.wait.until(
                                                            EC.presence_of_element_located((By.CSS_SELECTOR, "table.dataGrid"))
                                                        )
                                                    
                                                        # DIAGNOSTIC: Print HTML after renavigation
                                                        print(f"\n=== RETRY {renavigation_attempts} DIAGNOSTIC HTML for {info['name']} ===")
                                                        try:
                                                            retry_table_html = table.get_attribute('outerHTML')
                                                            print(f"Retry Table HTML (first 500 chars): {retry_table_html[:500]}")
                                                        
                                                            retry_page_text = self.driver.find_element(By.TAG_NAME, "body").text
                                                            if "no matches" in retry_page_text.lower():
                                                                print(f"Retry: 'No matches' text found on page: {retry_page_text[:200]}")
                                                        
                                                            # Check for wrestler name in page text (alias-aware)
                                                            name_variants = self._get_name_variants(info['name'], team_info['name'], self.season_year)
                                                            if self._text_has_any(retry_page_text, name_variants):
                                                                print(f"Retry: Wrestler name (alias-aware) found in page text")
                                                                variant = next((v for v in name_variants if v.lower() in retry_page_text.lower()), None)
                                                                name_pos = retry_page_text.lower().find(variant.lower()) if variant else -1
                                                                context = retry_page_text[max(0, name_pos-50):min(len(retry_page_text), name_pos+150)]
                                                                print(f"Retry Name context: {context}")
                                                            else:
                                                                print(f"Retry WARNING: Wrestler name (alias-aware) NOT found in page text")
                                                            
                                                                # Try different variants of the name
                                                                for variant in [
                                                                    info['name'].replace("'", "`"),
                                                                    info['name'].replace("'", "'"),
                                                                    info['name'].replace(" ", ""),
                                                                    info['name'].lower()
                                                                ]:
                                                                    if variant != info['name'] and variant in retry_page_text:
                                                                        print(f"Retry: Found name VARIANT '{variant}' in page text")
                                                        except Exception as e:
                                                            print(f"Error during retry diagnostics: {e}")
                                                        print(f"=== END RETRY {renavigation_attempts} DIAGNOSTIC ===\n")
                                                    
                                                        # Get all match rows again
                                                        all_rows = table.find_elements(By.TAG_NAME, "tr")
                                                        new_match_rows = [row for row in all_rows[3:] if row.get_attribute("class") == "dataGridRow"]
                                                        print(f"Found {len(new_match_rows)} match rows after re-navigation")
                                                    
                                                        # Verify at least some match has the wrestler's name (alias-aware)
                                                        if len(new_match_rows) > 0:
                                                            verification_success = False
                                                            # Check multiple rows to ensure we load the correct data
                                                            for check_row in new_match_rows[:min(3, len(new_match_rows))]:
                                                                check_cols = check_row.find_elements(By.TAG_NAME, "td")
                                                                if len(check_cols) >= 5:
                                                                    check_summary = check_cols[4].text.strip()
                                                                    name_variants = self._get_name_variants(info['name'], team_info['name'], self.season_year)
                                                                    if self._text_has_any(check_summary, name_variants):
                                                                        verification_success = True
                                                                        break
                                                        
                                                            if verification_success:
                                                                print(f"✅ Successfully verified wrestler {info['name']} after re-navigation!")
                                                            
                                                                # Reset the match processing from the beginning with these new rows
                                                                match_rows = new_match_rows
                                                                renavigation_success = True
                                                                wrestler_verified = True
                                                            
                                                                # Clear existing matches to start fresh
                                                                matches = []
                                                            
                                                                # Process all the match rows with the new data
                                                                print("\nProcessing match rows after re-navigation...")
                                                                for i, row in enumerate(match_rows):
                                                                    try:
                                                                        print(f"\nProcessing match row {i+1} after re-navigation:")
                                                                        cols = row.find_elements(By.TAG_NAME, "td")
                                                                        print(f"Found {len(cols)} columns in row")
                                                                    
                                                                        if len(cols) < 5:
                                                                            print("Skipping row - not enough columns")
                                                                            continue
                                                                        
                                                                        summary = cols[4].text.strip()
                                                                        print(f"Raw summary: {summary}")
                                                                    
                                                                        # Skip double forfeit matches
                                                                        if "Double Forfeit" in summary:
                                                                            print("Match is a double forfeit - skipping this match")
                                                                            continue
                                                                    
                                                                        # Skip verification check - we already verified the wrestler above
                                                                    
                                                                        # Extract opponent ID from links in the row if available
                                                                        opponent_id = None
                                                                    
                                                                        # Check if this is a bye or forfeit before trying to extract opponent ID
                                                                        if "received a bye" in summary:
                                                                            print("Match is a bye - setting opponent_id to null")
                                                                            opponent_id = None
                                                                        elif "forfeit" in summary.lower() or "(for.)" in summary.lower() or "(ff)" in summary.lower() or "received a forfeit" in summary.lower():
                                                                            print("Match is a forfeit - setting opponent_id to null")
                                                                            opponent_id = None
                                                                        else:
                                                                            # For normal matches, try to extract opponent ID from links
                                                                            links = cols[4].find_elements(By.TAG_NAME, "a")
                                                                        
                                                                            # If there are multiple links, we need to find the one that's NOT the current wrestler
                                                                            current_wrestler_id = info["id"]
                                                                        
                                                                            for link in links:
                                                                                href = link.get_attribute("href")
                                                                                if href and "wrestlerId=" in href:
                                                                                    extracted_id = self.get_wrestler_id_from_url(href)
                                                                                
                                                                                    # Only use ID if it's not the current wrestler's ID
                                                                                    if extracted_id != current_wrestler_id:
                                                                                        opponent_id = extracted_id
                                                                                        print(f"Found opponent ID: {opponent_id}")
                                                                                        break
                                                                        
                                                                            if opponent_id is None:
                                                                                print("Could not find opponent ID in links")
                                                                    
                                                                        # Store only raw match data without winner/loser processing
                                                                        match_data = {
                                                                            "date": cols[1].text.strip(),
                                                                            "event": cols[2].text.strip(),
                                                                            "weight": cols[3].text.strip(),
                                                                            "summary": summary,
                                                                            "opponent_id": opponent_id  # Store opponent ID from URL
                                                                        }
                                                                    
                                                                        # Handle date ranges
                                                                        date = match_data["date"]
                                                                        if " - " in date:
                                                                            # Take the end date from the range
                                                                            match_data["date"] = date.split(" - ")[1].strip()
                                                                    
                                                                        matches.append(match_data)
                                                                    
                                                                    except Exception as e:
                                                                        print(f"Error processing match row after re-navigation: {e}")
                                                                        continue
                                                            
                                                                # We've successfully processed all matches, break out of renavigation loop
                                                                break
                                                            else:
                                                                print(f"❌ Still could not verify wrestler {info['name']} after re-navigation. Trying again...")
                                                        else:
                                                            # Special handling for wrestlers with no matches during renavigation
                                                            page_text = self.driver.find_element(By.TAG_NAME, "body").text
                                                            no_matches_message = "There are no matches associated with this wrestler"
                                                            if no_matches_message in page_text and info['name'] in page_text:
                                                                print(f"No matches found for {info['name']} during renavigation - message: '{no_matches_message}' - marking as verified")
                                                                verification_success = True
                                                                renavigation_success = True
                                                                wrestler_verified = True
                                                                matches = []  # Empty matches list
                                                                break  # Exit renavigation loop successfully
                                                            else:
                                                                print(f"❌ No match rows found after re-navigation. Trying again...")
                                                
                                                    except Exception as e:
                                                        print(f"❌ Error during re-navigation attempt #{renavigation_attempts}: {e}")
                                            
                                                # If all renavigation attempts failed, log error and skip team
                                                if not renavigation_success:
                                                    error_msg = f"Failed to verify wrestler {info['name']} (ID: {info['id']}) for team {team_info['name']} after {renavigation_attempts} re-navigation attempts. Skipping team."
                                                    self._log_error("wrestler_verification", error_msg)
                                                    print(f"❌ {error_msg}")
                                                    # Ensure log is saved before returning
                                                    self._save_scrape_log()
                                                    # Return None to indicate the team scraping failed
                                                    return None
                                                else:
                                                    # Successfully renavigated and processed matches, continue to next wrestler
                                                    break
                                
                                    # Extract opponent ID from links in the row if available
                                    opponent_id = None
                                
                                    # Check if this is a bye or forfeit before trying to extract opponent ID
                                    if "received a bye" in summary:
                                        print("Match is a bye - setting opponent_id to null")
                                        opponent_id = None
                                    elif "forfeit" in summary.lower() or "(for.)" in summary.lower() or "(ff)" in summary.lower() or "received a forfeit" in summary.lower():
                                        print("Match is a forfeit - setting opponent_id to null")
                                        opponent_id = None
                                    else:
                                        # For normal matches, try to extract opponent ID from links
                                        links = cols[4].find_elements(By.TAG_NAME, "a")
                                    
                                        # If there are multiple links, we need to find the one that's NOT the current wrestler
                                        current_wrestler_id = info["id"]
                                    
                                        for link in links:
                                            href = link.get_attribute("href")
                                            if href and "wrestlerId=" in href:
                                                extracted_id = self.get_wrestler_id_from_url(href)
                                            
                                                # Only use ID if it's not the current wrestler's ID
                                                if extracted_id != current_wrestler_id:
                                                    opponent_id = extracted_id
                                                    print(f"Found opponent ID: {opponent_id}")
                                                    break
                                
                                    if opponent_id is None:
                                        print("Could not find opponent ID in links")
                                
                                    # Store only raw match data without winner/loser processing
                                    match_data = {
                                        "date": cols[1].text.strip(),
                                        "event": cols[2].text.strip(),
                                        "weight": cols[3].text.strip(),
                                        "summary": summary,
                                        "opponent_id": opponent_id  # Store opponent ID from URL
                                    }
                                
                                    # Handle date ranges
                                    date = match_data["date"]
                                    if " - " in date:
                                        # Take the end date from the range
                                        match_data["date"] = date.split(" - ")[1].strip()
                                
                                    matches.append(match_data)
                                
                                except Exception as e:
                                    print(f"Error processing match row: {e}")
                                    continue
                        else:
                            print("No match rows found")
                            matches = []
                        
                            # If wrestler previously had matches, try re-navigation before declaring regression
                            wrestler_id = info["id"]
                            if "wrestlers" in self.wrestler_match_tracking:
                                wrestler_entry = self.wrestler_match_tracking["wrestlers"].get(wrestler_id)
                                if wrestler_entry and wrestler_entry.get("has_ever_had_matches", False):
                                    print(f"⚠️ Wrestler {info['name']} previously had matches but now shows zero. Attempting re-navigation retry...")
                                
                                    renavigation_attempts = 0
                                    renavigation_success = False
                                    max_renavigation_attempts = 3
                                
                                    while renavigation_attempts < max_renavigation_attempts and not renavigation_success:
                                        renavigation_attempts += 1
                                        print(f"\n⏳ Zero-match re-navigation attempt #{renavigation_attempts} for {info['name']}...")
                                    
                                        try:
                                            # Navigate back to team page
                                            current_url = self.driver.current_url
                                            parsed_url = urlparse(current_url)
                                            query_params = parse_qs(parsed_url.query)
                                            session_id = query_params.get('twSessionId', [''])[0]
                                        
                                            if not session_id:
                                                team_page_url = team_url
                                            else:
                                                team_parsed_url = urlparse(team_url)
                                                team_params = parse_qs(team_parsed_url.query)
                                                team_id = team_params.get('teamId', [''])[0]
                                            
                                                if not team_id:
                                                    team_page_url = team_url
                                                else:
                                                    team_page_url = f"{BASE_URL}/seasons/TeamSchedule.jsp?twSessionId={session_id}&teamId={team_id}"
                                        
                                            print(f"Navigating to team page: {team_page_url}")
                                            self.driver.get(team_page_url)
                                            time.sleep(3)
                                        
                                            # Click Matches tab
                                            matches_link = self.wait.until(
                                                EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='WrestlerMatches.jsp']"))
                                            )
                                            self.driver.execute_script("arguments[0].click();", matches_link)
                                            time.sleep(3)

                                            # Re-select wrestler
                                            wrestler_select = self.wait.until(
                                                EC.presence_of_element_located((By.ID, "wrestler"))
                                            )
                                        
                                            try:
                                                prev_table = self.driver.find_element(By.CSS_SELECTOR, "table.dataGrid")
                                            except Exception:
                                                prev_table = None
                                        
                                            Select(wrestler_select).select_by_value(info["id"])
                                        
                                            try:
                                                if prev_table is not None:
                                                    self.wait.until(EC.staleness_of(prev_table))
                                            except Exception:
                                                pass
                                        
                                            # Verify hydration
                                            status = self._verify_wrestler_table_hydrated(info["id"], timeout_sec=8.0)
                                            if status == "timeout":
                                                print("⚠️ Table did not hydrate after re-navigation; will retry")
                                                continue
                                        
                                            # Check for matches
                                            table = self.wait.until(
                                                EC.presence_of_element_located((By.CSS_SELECTOR, "table.dataGrid"))
                                            )
                                            rows = table.find_elements(By.TAG_NAME, "tr")
                                            retry_match_rows = [row for row in rows[3:] if row.get_attribute("class") == "dataGridRow"]
                                        
                                            print(f"After re-navigation, found {len(retry_match_rows)} match rows")
                                        
                                            if len(retry_match_rows) > 0:
                                                # Found matches! Process them
                                                print(f"✅ Successfully found matches after re-navigation!")
                                                match_rows = retry_match_rows
                                                renavigation_success = True
                                                matches = []
                                            
                                                # Process all match rows
                                                for i, row in enumerate(match_rows):
                                                    try:
                                                        cols = row.find_elements(By.TAG_NAME, "td")
                                                        if len(cols) < 5:
                                                            continue
                                                    
                                                        summary = cols[4].text.strip()
                                                    
                                                        if "Double Forfeit" in summary:
                                                            continue
                                                    
                                                        # Extract opponent ID
                                                        opponent_id = None
                                                        if "received a bye" in summary:
                                                            opponent_id = None
                                                        elif "forfeit" in summary.lower() or "(for.)" in summary.lower() or "(ff)" in summary.lower() or "received a forfeit" in summary.lower():
                                                            opponent_id = None
                                                        else:
                                                            links = cols[4].find_elements(By.TAG_NAME, "a")
                                                            current_wrestler_id = info["id"]
                                                            for link in links:
                                                                href = link.get_attribute("href")
                                                                if href and "wrestlerId=" in href:
                                                                    extracted_id = self.get_wrestler_id_from_url(href)
                                                                    if extracted_id != current_wrestler_id:
                                                                        opponent_id = extracted_id
                                                                        break
                                                    
                                                        match_data = {
                                                            "date": cols[1].text.strip(),
                                                            "event": cols[2].text.strip(),
                                                            "weight": cols[3].text.strip(),
                                                            "summary": summary,
                                                            "opponent_id": opponent_id
                                                        }
                                                    
                                                        date = match_data["date"]
                                                        if " - " in date:
                                                            match_data["date"] = date.split(" - ")[1].strip()
                                                    
                                                        matches.append(match_data)
                                                    except Exception as e:
                                                        print(f"Error processing match row after re-navigation: {e}")
                                                        continue
                                            
                                                # Break out of renavigation loop - we found matches
                                                break
                                            else:
                                                # Still zero matches - check for "no matches" banner
                                                page_text = self.driver.find_element(By.TAG_NAME, "body").text
                                                no_matches_message = "There are no matches associated with this wrestler"
                                                if no_matches_message in page_text and info['name'] in page_text:
                                                    print(f"No matches confirmed after re-navigation attempt #{renavigation_attempts}")
                                                    # Continue to next attempt or will fall through to validation
                                                else:
                                                    print(f"⚠️ Ambiguous state after re-navigation attempt #{renavigation_attempts}")
                                    
                                        except Exception as e:
                                            print(f"❌ Error during zero-match re-navigation attempt #{renavigation_attempts}: {e}")
                                
                                    if renavigation_success:
                                        print(f"✅ Re-navigation successful - found {len(matches)} matches for {info['name']}")
                    
                        # VALIDATION: Check for match count regression before adding to team_data
                        validation_status, validation_message = self._validate_wrestler_match_count(
                            info["id"],
                            info["name"],
                            matches
                        )
                    
                        if validation_status == "REGRESSION_DETECTED":
                            # REGRESSION DETECTED - prompt user for action
                            error_msg = validation_message
                            print(f"\n❌ {error_msg}")
                            self._log_error("match_regression", error_msg)
                            
                            # Prompt user for action
                            print("\n" + "="*60)
                            print("MATCH REGRESSION DETECTED")
                            print("="*60)
                            print(f"Wrestler: {info['name']} (ID: {wrestler_id})")
                            print(f"Previously had matches but now scrapes as zero matches.")
                            print("\nOptions:")
                            print("  1. Abort team scrape (default) - retry the scrape")
                            print("  2. Continue and accept zero matches for this wrestler")
                            print()
                            
                            while True:
                                try:
                                    choice = input("Choose an option (1=abort, 2=continue, default=1): ").strip()
                                    if not choice:
                                        choice = "1"  # Default to abort
                                    
                                    if choice == "1":
                                        # Abort team scrape
                                        print("\n❌ Aborting team scrape. Please retry the scrape.")
                                        
                                        # Save tracking file before aborting
                                        try:
                                            self._save_wrestler_match_tracking()
                                        except Exception as e:
                                            print(f"Warning: Error saving tracking file before abort: {e}")
                                        
                                        # Save log state before aborting
                                        try:
                                            self._save_scrape_log()
                                        except Exception:
                                            pass
                                        
                                        return None  # Abort team scrape (no data written)
                                    
                                    elif choice == "2":
                                        # Accept zero matches - update tracking to reflect this
                                        print(f"\n✅ Accepting zero matches for {info['name']}. Continuing with scrape...")
                                        
                                        # Update tracking to mark that we've accepted zero matches
                                        # This prevents future regressions for this wrestler
                                        if wrestler_id in self.wrestler_match_tracking.get("wrestlers", {}):
                                            entry = self.wrestler_match_tracking["wrestlers"][wrestler_id]
                                            # Mark that we've explicitly accepted zero matches
                                            entry["accepted_zero_matches"] = True
                                            entry["accepted_zero_matches_date"] = datetime.now().isoformat()
                                            entry["last_seen_zero_matches"] = datetime.now().isoformat()
                                        
                                        # Continue processing this wrestler with zero matches
                                        break
                                    
                                    else:
                                        print("Invalid choice. Please enter '1' to abort or '2' to continue.")
                                
                                except KeyboardInterrupt:
                                    print("\n\n❌ Aborting team scrape (Ctrl+C).")
                                    return None
                                except Exception as e:
                                    print(f"Error: {e}. Please try again.")
                            
                            # If we get here, user chose to continue - wrestler will be processed with zero matches
                    
                        # Validation passed - update tracking and continue
                        # (tracking is updated in _validate_wrestler_match_count)
                    
                        # Add wrestler data to roster
                        wrestler_data = {
                            "season_wrestler_id": info["id"],
                            "name": info["name"],
                            "weight_class": info["weight_class"],
                            "grade": info["grade"],
                            "matches": matches
                        }
                    
                        # Append wrestler data to the team's roster
                        team_data["roster"].append(wrestler_data)
                    
                        # Log processing summary including skipped rows if any
                        if skipped_rows > 0:
                            print(f"\nProcessed {len(matches)} matches for {info['name']} (Grade: {info['grade']}) - Skipped {skipped_rows} problematic rows")
                            # Add to log with team name for easier searching
                            skip_summary = f"Team {team_info['name']}: Processed wrestler {info['name']} with {skipped_rows} skipped match rows out of {len(matches) + skipped_rows} total"
                            self._log_error("match_processing_summary", skip_summary)
                        else:
                            success_msg = f"Processed {len(matches)} matches for {info['name']} (Grade: {info['grade']}) - All rows verified"
                            print(f"\n{success_msg}")
                            self._log_success("wrestler_processing", f"Team {team_info['name']}: {success_msg}")
                    
                        # Wrestler processed successfully - exit retry loop
                        wrestler_processed = True
                    
                    except Exception as e:
                        print(f"Error processing wrestler {info['name']}: {e}")
                        # Log error with team name
                        error_msg = f"Error processing wrestler {info['name']} for team {team_info['name']}: {e}"
                        self._log_error("wrestler_processing", error_msg)
                        
                        # If this looks like a stale element error, attempt re-navigation and retry
                        if "stale element reference" in str(e).lower():
                            stale_retry_attempts += 1
                            print(f"⚠️ Stale element error detected (attempt {stale_retry_attempts}/{max_stale_retries})")
                            
                            if stale_retry_attempts < max_stale_retries:
                                print(f"Attempting re-navigation to recover from stale element error...")
                                
                                try:
                                    # Use the same re-navigation pattern as zero-match retry
                                    current_url = self.driver.current_url
                                    parsed_url = urlparse(current_url)
                                    query_params = parse_qs(parsed_url.query)
                                    session_id = query_params.get('twSessionId', [''])[0]
                                    
                                    if not session_id:
                                        team_page_url = team_url
                                    else:
                                        team_parsed_url = urlparse(team_url)
                                        team_params = parse_qs(team_parsed_url.query)
                                        team_id = team_params.get('teamId', [''])[0]
                                        
                                        if not team_id:
                                            team_page_url = team_url
                                        else:
                                            team_page_url = f"{BASE_URL}/seasons/TeamSchedule.jsp?twSessionId={session_id}&teamId={team_id}"
                                    
                                    print(f"Navigating to team page: {team_page_url}")
                                    self.driver.get(team_page_url)
                                    time.sleep(3)
                                    
                                    # Click Matches tab
                                    matches_link = self.wait.until(
                                        EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='WrestlerMatches.jsp']"))
                                    )
                                    self.driver.execute_script("arguments[0].click();", matches_link)
                                    time.sleep(3)

                                    print(f"✅ Re-navigation successful, retrying wrestler {info['name']}...")
                                    # Continue the while loop to retry processing this wrestler
                                    continue
                                    
                                except Exception as nav_error:
                                    print(f"❌ Error during re-navigation attempt: {nav_error}")
                                    # If re-navigation fails, continue the while loop to retry
                                    # The retry counter will prevent infinite loops
                                    continue
                            else:
                                # All retry attempts exhausted
                                fatal_msg = (
                                    f"Fatal stale element error while processing wrestler {info['name']} "
                                    f"for team {team_info['name']} after {max_stale_retries} retry attempts. Marking team scrape as failed."
                                )
                                print(f"❌ {fatal_msg}")
                                self._log_error("team_scraping", fatal_msg)
                                # Save log state before aborting this team
                                try:
                                    self._save_scrape_log()
                                except Exception:
                                    pass
                                return None
                        else:
                            # Not a stale element error - break out of retry loop and continue to next wrestler
                            break

            # Save tracking file after successful team scrape
            try:
                self._save_wrestler_match_tracking()
            except Exception as e:
                print(f"Warning: Error saving tracking file after team scrape: {e}")
            
            return team_data

        except Exception as e:
            error_msg = f"Error scraping team {team_url}: {e}"
            self._log_error("team_scraping", error_msg)
            print(f"\n❌ Team scraping error: {e}")
            return None
        finally:
            # Switch back to default content
            try:
                print("\nSwitching back to default content...")
                self.driver.switch_to.default_content()
                print("Successfully switched back to default content")
            except Exception as e:
                print(f"Error switching back to default content: {e}")

    def save_team_data(self, team_data: Dict):
        """Save team data to a JSON file in the season-specific directory."""
        team_name = team_data["team_name"].replace(" ", "_").replace("/", "_")
        filename = self.season_data_dir / f"{team_name}.json"
        
        with open(filename, "w") as f:
            json.dump(team_data, f, indent=2)

    def run(self):
        """Main scraping process."""
        try:
            # Set up the browser and navigate to the desired season, with limited retries
            max_nav_attempts = 3
            attempt = 0
            nav_ok = False

            while attempt < max_nav_attempts and not nav_ok:
                attempt += 1
                print(f"=== Navigation attempt {attempt}/{max_nav_attempts} ===")
                self.setup_driver()
                nav_ok = self.navigate_to_season()

                if not nav_ok:
                    print("Navigation attempt failed; closing browser and retrying...")
                    try:
                        if self.driver:
                            self.driver.quit()
                    except Exception:
                        pass
                    self.driver = None
                    self.wait = None
                    time.sleep(5)

            if not nav_ok:
                msg = f"Failed to navigate to season {self.season_year} after {max_nav_attempts} attempts; aborting run."
                print(msg)
                self._log_error("navigation_fatal", msg)
                return

            # Get list of teams
            teams = self.get_teams()
            
            # Apply max_teams limit if specified
            if self.max_teams is not None:
                teams = teams[:self.max_teams]

            print(f"Found {len(teams)} teams total.")

            # Initialize required log structure even if empty
            self.scrape_log.setdefault("teams_scraped", [])
            self.scrape_log.setdefault("errors", [])
            self.scrape_log.setdefault("successes", [])

            # Loop over the team list multiple times if needed to pick up
            # teams that failed on an earlier pass. Most teams will be
            # skipped quickly once they are in teams_scraped.
            max_passes = 10
            for pass_idx in range(1, max_passes + 1):
                print(f"\n=== Scrape pass {pass_idx}/{max_passes} over team list ===")
                self._refresh_teams_scraped()

                any_pending = False
                any_progress = False

                for team in teams:
                    # Refresh log data before each team to pick up updates
                    self._refresh_teams_scraped()

                    # Skip special "Season Team" or already scraped teams
                    if team["name"] == "Season Team":
                        continue
                    if team["name"] in self.scrape_log.get("teams_scraped", []):
                        continue

                    any_pending = True

                    # Extract team ID from the URL
                    team_url = team["url"]
                    parsed_url = urlparse(team_url)
                    query_params = parse_qs(parsed_url.query)
                    team_id = query_params.get('teamId', ['unknown_team'])[0]
                    
                    if not acquire_lock(team_id):
                        print(f"Skipping team {team['name']} (ID: {team_id}) — locked by another process.")
                        continue
                        
                    try:
                        print(f"Scraping team: {team['name']} ({team['state']}) - {team['division']}")
                        team_data = self.scrape_team(team["url"], team)
                        
                        if team_data:
                            self.save_team_data(team_data)
                            
                            # Update the teams_scraped list and save the log with locking
                            if team["name"] not in self.scrape_log.get("teams_scraped", []):
                                self.scrape_log.setdefault("teams_scraped", []).append(team["name"])
                            
                            success_msg = f"Successfully scraped team: {team['name']} with {len(team_data.get('roster', []))} wrestlers"
                            self._log_success("team_completed", success_msg)
                            print(f"✅ {success_msg}")
                            any_progress = True
                        else:
                            print(f"❌ Failed to scrape team: {team['name']} - Will retry in a later pass if possible")
                        
                        self._random_delay()

                    except Exception as e:
                        self._log_error("general", f"General error processing team {team['name']}: {e}")
                    finally:
                        # Only release the lock, don't quit the driver here
                        release_lock(team_id)

                # After one full pass over all teams:
                if not any_pending:
                    print("All teams are marked as scraped; no teams remaining to process.")
                    break
                if not any_progress:
                    print("No progress made on this pass (likely all remaining teams are locked or failing repeatedly); stopping early.")
                    break

        except Exception as e:
            self._log_error("general", f"General error in run method: {e}")
            raise
        finally:
            # Only quit the driver once at the end of all processing
            if self.driver:
                print("Closing browser instance at end of processing.")
                self.driver.quit()

    def parse_name_and_team(self, text: str) -> tuple:
        """Parse a name and team from text that may contain nested parentheses.
        Returns (name, team)"""
        # Find the first opening parenthesis
        start_paren = text.find("(")
        if start_paren == -1:
            return text.strip(), None
        
        name = text[:start_paren].strip()
        
        # Now find the matching closing parenthesis by counting
        stack = 1  # We've found one opening parenthesis
        pos = start_paren + 1
        
        while pos < len(text) and stack > 0:
            if text[pos] == "(":
                stack += 1
            elif text[pos] == ")":
                stack -= 1
            pos += 1
        
        if stack == 0:
            # We found the matching closing parenthesis
            # Everything between start_paren+1 and pos-1 is the team
            team = text[start_paren + 1:pos - 1]
            return name, team
        
        return text.strip(), None

    def test_parser(self):
        """Test the name and team parser with various cases."""
        test_cases = [
            "Shawn Hatlestad (Augustana (SD))",
            "Max Ortega (Adams State)",
            "Joshua Douglas (Minot State (N.D.))",
            "Bryce Shoemaker (Baker (Kan.))",
        ]
        
        print("\nTesting name and team parser:")
        for test in test_cases:
            name, team = self.parse_name_and_team(test)
            print(f"\nInput: {test}")
            print(f"Name: {name}")
            print(f"Team: {team}")

def archive_scrape_logs(season: int, league: str, state: str = None, gender: str = None):
    """Archive scrape log files to a unique timestamped file, then delete originals."""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if league == 'hs':
        # HS logs: mt/logs/hs_ky_<gender>/scrape_log_*.json
        log_dir = LOGS_DIR / f"hs_{state.lower()}_{gender}"
        if not log_dir.exists():
            print(f"  No log directory found: {log_dir}")
            return
        
        # Find all scrape_log files
        log_files = list(log_dir.glob("scrape_log_*.json"))
        if not log_files:
            print(f"  No scrape log files found in {log_dir}")
            return
        
        # Create archive directory
        archive_dir = log_dir / "archived"
        archive_dir.mkdir(exist_ok=True, parents=True)
        
        # Archive each log file, then delete the original
        for log_file in log_files:
            archive_name = f"{log_file.stem}_{timestamp}.json"
            archive_path = archive_dir / archive_name
            shutil.copy2(log_file, archive_path)
            log_file.unlink()  # Delete the original file
            print(f"  Archived and deleted: {log_file.name} -> {archive_path.name}")
    else:
        # NCAA logs: mt/logs/scrape_log_*.json
        log_files = list(LOGS_DIR.glob(f"scrape_log_{season}.json"))
        if not log_files:
            print(f"  No scrape log file found for season {season}")
            return
        
        # Create archive directory
        archive_dir = LOGS_DIR / "archived"
        archive_dir.mkdir(exist_ok=True, parents=True)
        
        # Archive the log file, then delete the original
        for log_file in log_files:
            archive_name = f"{log_file.stem}_{timestamp}.json"
            archive_path = archive_dir / archive_name
            shutil.copy2(log_file, archive_path)
            log_file.unlink()  # Delete the original file
            print(f"  Archived and deleted: {log_file.name} -> {archive_path.name}")


def delete_team_data_files(season: int, league: str, state: str = None, gender: str = None):
    """Delete all team JSON files from the data directory."""
    if league == 'hs':
        # HS data: mt/data/hs_ky_<gender>/<season>/
        data_dir = DATA_DIR / f"hs_{state.lower()}_{gender}" / str(season)
    else:
        # NCAA data: mt/data/<season>/
        data_dir = DATA_DIR / str(season)
    
    if not data_dir.exists():
        print(f"  No data directory found: {data_dir}")
        return
    
    # Find all JSON files (team files)
    json_files = list(data_dir.glob("*.json"))
    if not json_files:
        print(f"  No team JSON files found in {data_dir}")
        return
    
    # Delete each file
    deleted_count = 0
    for json_file in json_files:
        try:
            json_file.unlink()
            deleted_count += 1
        except Exception as e:
            print(f"  Error deleting {json_file.name}: {e}")
    
    print(f"  Deleted {deleted_count} team JSON file(s) from {data_dir}")


if __name__ == "__main__":
    # Parse command line arguments
    args = parse_args()
    
    # Handle -force flag
    if args.force:
        print("\n" + "="*70)
        print("⚠️  FORCE RE-SCRAPE MODE")
        print("="*70)
        print("\nThis will:")
        print("  1. Archive all scrape log files")
        print("  2. Delete ALL team data JSON files")
        print("  3. Start a complete re-scrape from scratch")
        print("\n⚠️  WARNING: This action cannot be undone!")
        print("\n" + "="*70)
        
        # Require confirmation
        confirmation = input("\nType 'y' to confirm you want to proceed: ").strip().lower()
        if confirmation != 'y':
            print("\n❌ Force re-scrape cancelled. Exiting.")
            exit(0)
        
        print("\n🔄 Proceeding with force re-scrape...")
        
        # Archive scrape logs
        print("\n1. Archiving scrape logs...")
        archive_scrape_logs(args.season, args.league, args.state, args.gender)
        
        # Delete team data files
        print("\n2. Deleting team data files...")
        delete_team_data_files(args.season, args.league, args.state, args.gender)
        
        print("\n✅ Force re-scrape preparation complete. Starting scrape...\n")
    
    # Create scraper with specified parameters
    scraper = WrestlingScraper(
        max_teams=args.teams, 
        season_year=args.season, 
        headless=args.headless,
        league=args.league,
        state=args.state,
        gender=args.gender
    )
    
    # Run the test parser first
    scraper.test_parser()
    
    # Then run the main scraper
    scraper.run() 