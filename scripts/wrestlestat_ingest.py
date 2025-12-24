#!/usr/bin/env python3
"""
WrestleStat Ingestion Pipeline
Supplemental dual results ingestion with human-gated navigation and permanent ID mappings.
"""

import json
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse, parse_qs
import requests
from bs4 import BeautifulSoup

from wrestlestat_ui import (
    resolve_wrestlestat_team,
    resolve_wrestlestat_wrestler,
    load_team_mappings,
    load_wrestler_mappings
)

# Paths
BASE_DIR = Path(__file__).parent.parent
RAW_DUALS_DIR = BASE_DIR / "data" / "raw" / "wrestlestat_duals"
PROCESSED_DIR = BASE_DIR / "data" / "processed" / "wrestlestat"
WRESTLERS_DATA_DIR = BASE_DIR / "mt" / "data"

# WrestleStat URLs
WRESTLESTAT_BASE = "https://www.wrestlestat.com"
RECENT_DUALS_URL = f"{WRESTLESTAT_BASE}/d1/event/recentduals"

# Configuration
MIN_MATCH_THRESHOLD = 5  # Minimum matches to consider dual already ingested
SEASON = 2026


def normalize_name(name: str) -> str:
    """Normalize name for comparison."""
    if not name:
        return ""
    name = re.sub(r'[^\w\s]', '', name)
    name = re.sub(r'\s+', ' ', name)
    return name.strip().lower()


def parse_result_text(result_text: str) -> Dict:
    """
    Parse WrestleStat result text (e.g., "WTF5 19 - 4 6:38" or "LDEC 12 - 5").
    
    Returns dict with:
    - winner_is_a: bool (True if W prefix, False if L prefix)
    - result_type: str (DEC, MD, TF, FALL, SV-1, INJ, TB-2, FORFEIT)
      Note: TF5 is converted to TF to match MatSavant nomenclature
    - score: str or None (e.g., "19-4" or None)
    - time: str or None (e.g., "6:38" or None)
    """
    if not result_text:
        return {"winner_is_a": True, "result_type": "DEC", "score": None, "time": None}
    
    result_text = result_text.strip()
    
    # Determine winner from W/L prefix
    winner_is_a = result_text.startswith('W')
    
    # Remove W/L prefix
    result_text = result_text[1:] if result_text.startswith(('W', 'L')) else result_text
    
    # Extract result type
    result_type = None
    score = None
    time_str = None
    
    # Match result types (in order of specificity)
    if result_text.startswith('TF5'):
        result_type = 'TF'  # Convert TF5 to TF to match MatSavant nomenclature
        result_text = result_text[3:].strip()
    elif result_text.startswith('FALL'):
        result_type = 'FALL'
        result_text = result_text[4:].strip()
    elif result_text.startswith('SV-1'):
        result_type = 'SV-1'
        result_text = result_text[4:].strip()
    elif result_text.startswith('TB-2'):
        result_type = 'TB-2'
        result_text = result_text[4:].strip()
    elif result_text.startswith('INJ'):
        result_type = 'INJ'
        result_text = result_text[3:].strip()
    elif result_text.startswith('MD'):
        result_type = 'MD'
        result_text = result_text[2:].strip()
    elif result_text.startswith('DEC'):
        result_type = 'DEC'
        result_text = result_text[3:].strip()
    elif result_text.startswith('FORFEIT') or result_text.startswith('FOR'):
        result_type = 'FORFEIT'
        result_text = result_text.replace('FORFEIT', '').replace('FOR', '').strip()
    else:
        # Default to DEC if we can't determine
        result_type = 'DEC'
    
    # Extract score (format: "X - Y" or "X-Y")
    score_match = re.search(r'(\d+)\s*-\s*(\d+)', result_text)
    if score_match:
        score = f"{score_match.group(1)}-{score_match.group(2)}"
        # Remove score from remaining text
        result_text = re.sub(r'\d+\s*-\s*\d+', '', result_text).strip()
    
    # Extract time (format: "M:SS" or "MM:SS")
    time_match = re.search(r'(\d+:\d{2})', result_text)
    if time_match:
        time_str = time_match.group(1)
    
    return {
        "winner_is_a": winner_is_a,
        "result_type": result_type,
        "score": score,
        "time": time_str
    }


def get_dual_id_from_url(url: str) -> str:
    """Extract dual ID from WrestleStat URL."""
    # WrestleStat URLs have format: /event/{id}/{team}-{team}-dual/boxscore
    # Or /d1/event/dual/{id}
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split('/') if p]  # Remove empty strings
    
    # Check for /event/{id}/... format (most common)
    if 'event' in path_parts:
        idx = path_parts.index('event')
        if idx + 1 < len(path_parts):
            # Next part should be the ID
            potential_id = path_parts[idx + 1]
            # Verify it's numeric (dual IDs are numeric)
            if potential_id.isdigit():
                return potential_id
    
    # Check for /d1/event/dual/{id} format
    if 'dual' in path_parts:
        idx = path_parts.index('dual')
        if idx + 1 < len(path_parts):
            return path_parts[idx + 1]
    
    # Try query params
    params = parse_qs(parsed.query)
    if 'id' in params:
        return params['id'][0]
    
    # Fallback: use URL hash (shouldn't happen with valid WrestleStat URLs)
    print(f"⚠ Warning: Could not extract dual ID from URL: {url}, using hash fallback")
    return str(hash(url))[-8:]


def scrape_recent_duals_index(time_filter: str = "Last Week") -> List[Dict]:
    """
    Scrape Recent Duals index page (NO clicking into duals).
    
    Returns list of dual summaries with:
    - wrestlestat_url (to boxscore page, not compare page)
    - team_a_name, team_a_id
    - team_b_name, team_b_id
    """
    print(f"\n{'='*60}")
    print(f"STEP 1: Loading Recent Duals Index")
    print(f"URL: {RECENT_DUALS_URL}")
    print(f"Filter: {time_filter}")
    print(f"{'='*60}\n")
    
    print("⚠ IMPORTANT: This script will NOT automatically click into dual pages.")
    print("⚠ Each dual page load requires your ENTER key confirmation.\n")
    
    input("Press ENTER to fetch the Recent Duals index page...")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        response = requests.get(RECENT_DUALS_URL, headers=headers, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        duals = []
        
        # Find the main content area - look specifically for the "Last Week" tab panel
        # The tab panel has id="lastweek" and contains the completed dual results
        tab_panel = soup.find('div', {'id': 'lastweek'})
        
        if not tab_panel:
            # Try to find active tab panel as fallback
            tab_panel = soup.find('div', class_=re.compile(r'tab-pane.*active'))
        
        if not tab_panel:
            print("⚠ Warning: Could not find 'Last Week' tab panel. Trying to find any tab panel.")
            tab_panel = soup.find('div', class_=re.compile(r'tab-pane'))
        
        if not tab_panel:
            print("⚠ Warning: Could not find tab panel. Trying to find dual results in main content.")
            tab_panel = soup
        else:
            print(f"✓ Found tab panel: {tab_panel.get('id', 'unknown')}")
        
        # Find all dual result cards/rows in the main content
        # These are typically in cards with team names and boxscore links
        # Look specifically for cards within the tab panel that contain boxscore links
        dual_cards = tab_panel.find_all('div', class_=re.compile(r'card'))
        
        # Also check for rows that might contain dual results
        if not dual_cards:
            dual_cards = tab_panel.find_all('div', class_=re.compile(r'col-12.*mb-1'))
        
        print(f"  Found {len(dual_cards)} potential dual cards in tab panel")
        
        # Load team mappings to filter out non-D1 teams
        from wrestlestat_ui import load_team_mappings
        team_mappings = load_team_mappings()
        non_d1_team_ids = {
            m.get("wrestlestat_team_id") 
            for m in team_mappings 
            if m.get("non_d1", False)
        }
        
        for card in dual_cards:
            # Look for boxscore link - this is the primary indicator of a completed dual
            boxscore_link = card.find('a', href=re.compile(r'/event/\d+.*boxscore'))
            
            if not boxscore_link:
                continue
            
            boxscore_href = boxscore_link.get('href', '')
            if not boxscore_href:
                continue
            
            boxscore_url = urljoin(WRESTLESTAT_BASE, boxscore_href)
            
            # Extract team names from the card
            # Look for team links with /team/{id}/profile pattern
            team_links = card.find_all('a', href=re.compile(r'/team/\d+/.*profile'))
            
            if len(team_links) < 2:
                continue
            
            team_a_link = team_links[0]
            team_b_link = team_links[1]
            
            # Extract team IDs from URLs
            team_a_id_match = re.search(r'/team/(\d+)/', team_a_link.get('href', ''))
            team_b_id_match = re.search(r'/team/(\d+)/', team_b_link.get('href', ''))
            
            if not (team_a_id_match and team_b_id_match):
                continue
            
            team_a_id = int(team_a_id_match.group(1))
            team_b_id = int(team_b_id_match.group(1))
            
            # Skip duals with non-D1 teams
            if team_a_id in non_d1_team_ids or team_b_id in non_d1_team_ids:
                continue
            
            # Extract team names from link text
            # Format might be "#38 Pennsylvania" or just "Pennsylvania"
            team_a_text = team_a_link.get_text(strip=True)
            team_b_text = team_b_link.get_text(strip=True)
            
            # Remove ranking prefix if present (e.g., "#38 " -> "")
            team_a_name = re.sub(r'^#\d+\s+', '', team_a_text).strip()
            team_b_name = re.sub(r'^#\d+\s+', '', team_b_text).strip()
            
            if not (team_a_name and team_b_name):
                continue
            
            duals.append({
                "wrestlestat_url": boxscore_url,
                "team_a_name": team_a_name,
                "team_a_id": team_a_id,
                "team_b_name": team_b_name,
                "team_b_id": team_b_id
            })
        
        print(f"✓ Found {len(duals)} duals in index")
        return duals
        
    except Exception as e:
        print(f"❌ Error scraping Recent Duals index: {e}")
        import traceback
        traceback.print_exc()
        return []


def check_dual_already_ingested(
    team_a_id: str,
    team_b_id: str,
    dual_url: str
) -> Tuple[bool, str]:
    """
    Check if dual is already ingested.
    
    Returns (is_ingested, reason)
    """
    # Check WrestleStat supplemental data
    dual_id = get_dual_id_from_url(dual_url)
    raw_file = RAW_DUALS_DIR / f"{dual_id}.json"
    if raw_file.exists():
        return True, "WrestleStat raw file exists"
    
    # Check TrackWrestling data
    # Look for matches between these teams in last 7 days
    cutoff_date = datetime.now() - timedelta(days=7)
    
    match_count = 0
    
    # Load team data files using the same logic as load_matsavant_wrestlers
    wrestlers_dir = WRESTLERS_DATA_DIR / str(SEASON)
    if not wrestlers_dir.exists():
        return False, "Wrestlers data directory not found"
    
    def find_team_file(team_id: str) -> Optional[Path]:
        """Find team file using same logic as load_matsavant_wrestlers."""
        # Try multiple naming conventions
        # 1. team_id with title case (e.g., "uva" -> "Uva.json")
        team_file = wrestlers_dir / f"{team_id.replace('_', ' ').title().replace(' ', '_')}.json"
        
        # 2. team_id as-is (e.g., "uva.json")
        if not team_file.exists():
            team_file = wrestlers_dir / f"{team_id}.json"
        
        # 3. Search for file by team_name in JSON (team_id might be abbreviation)
        if not team_file.exists():
            # Load team data from team profiles to get team_name
            teams_dir = Path(__file__).parent.parent / "mt" / "teams"
            
            # First try direct filename match
            team_profile_file = teams_dir / f"{team_id}.json"
            if not team_profile_file.exists():
                # Search all team profile files for matching team_id or abbreviation
                team_profile_file = None
                for profile_file in teams_dir.glob("*.json"):
                    try:
                        with open(profile_file, 'r') as f:
                            team_profile = json.load(f)
                        profile_team_id = team_profile.get("team_id", "").lower()
                        profile_abbreviation = team_profile.get("abbreviation", "").upper()
                        team_id_upper = team_id.upper()
                        
                        # Check if team_id matches profile's team_id or abbreviation
                        if profile_team_id == team_id.lower() or profile_abbreviation == team_id_upper:
                            team_profile_file = profile_file
                            break
                    except:
                        continue
            
            if team_profile_file and team_profile_file.exists():
                try:
                    with open(team_profile_file, 'r') as f:
                        team_profile = json.load(f)
                    team_name = team_profile.get("team_name", "")
                    if team_name:
                        # Try team_name as filename
                        team_file = wrestlers_dir / f"{team_name.replace(' ', '_')}.json"
                except:
                    pass
        
        # 4. Search all files for matching team_name or team_id in JSON
        if not team_file.exists():
            for json_file in wrestlers_dir.glob("*.json"):
                try:
                    with open(json_file, 'r') as f:
                        team_data = json.load(f)
                    file_team_name = team_data.get("team_name", "").lower()
                    file_team_id = team_data.get("team_id", "").lower() if team_data.get("team_id") else ""
                    
                    # Check if team_id or team_name matches
                    if file_team_id == team_id.lower() or file_team_name == team_id.lower():
                        team_file = json_file
                        break
                except:
                    continue
        
        return team_file if team_file.exists() else None
    
    team_a_file = find_team_file(team_a_id)
    team_b_file = find_team_file(team_b_id)
    
    print(f"[DEBUG] check_dual_already_ingested: team_a_id={team_a_id}, team_b_id={team_b_id}")
    print(f"[DEBUG] Found team_a_file: {team_a_file}")
    print(f"[DEBUG] Found team_b_file: {team_b_file}")
    
    # If we have both team files, check for recent matches
    if team_a_file and team_b_file:
        with open(team_a_file, 'r') as f:
            team_a_data = json.load(f)
        
        with open(team_b_file, 'r') as f:
            team_b_data = json.load(f)
        
        # Get opponent IDs from both teams
        team_a_wrestler_ids = {
            w.get("season_wrestler_id") for w in team_a_data.get("roster", [])
        }
        team_b_wrestler_ids = {
            w.get("season_wrestler_id") for w in team_b_data.get("roster", [])
        }
        
        print(f"[DEBUG] Checking for matches between {team_a_id} and {team_b_id}")
        print(f"[DEBUG] Team A has {len(team_a_wrestler_ids)} wrestlers, Team B has {len(team_b_wrestler_ids)} wrestlers")
        print(f"[DEBUG] Cutoff date: {cutoff_date.strftime('%m/%d/%Y')}")
        
        # Check team A wrestlers for matches against team B wrestlers
        for wrestler in team_a_data.get("roster", []):
            for match in wrestler.get("matches", []):
                opponent_id = match.get("opponent_id")
                if opponent_id in team_b_wrestler_ids:
                    # Parse date
                    match_date_str = match.get("date", "")
                    try:
                        match_date = datetime.strptime(match_date_str, "%m/%d/%Y")
                        if match_date >= cutoff_date:
                            match_count += 1
                            print(f"[DEBUG] Found match (Team A): {wrestler.get('name')} vs opponent on {match_date_str}")
                    except Exception as e:
                        print(f"[DEBUG] Error parsing date '{match_date_str}': {e}")
                        pass
        
        # Also check team B wrestlers for matches against team A wrestlers
        # (matches might be stored in Team B's file, e.g., Clarion vs Columbia)
        for wrestler in team_b_data.get("roster", []):
            for match in wrestler.get("matches", []):
                opponent_id = match.get("opponent_id")
                if opponent_id in team_a_wrestler_ids:
                    # Parse date
                    match_date_str = match.get("date", "")
                    try:
                        match_date = datetime.strptime(match_date_str, "%m/%d/%Y")
                        if match_date >= cutoff_date:
                            match_count += 1
                            print(f"[DEBUG] Found match (Team B): {wrestler.get('name')} vs opponent on {match_date_str}")
                    except Exception as e:
                        print(f"[DEBUG] Error parsing date '{match_date_str}': {e}")
                        pass
        
        print(f"[DEBUG] Total matches found: {match_count} (threshold: {MIN_MATCH_THRESHOLD})")
        if match_count >= MIN_MATCH_THRESHOLD:
            return True, f"TrackWrestling: {match_count} matches found"
    
    return False, "Not ingested"


def scrape_dual_page(dual_url: str, team_a_name: str = None, team_b_name: str = None) -> Optional[Dict]:
    """
    Scrape a single dual page (HUMAN-GATED).
    
    Returns raw dual data with matches.
    """
    print(f"[DEBUG] scrape_dual_page called with team_a_name='{team_a_name}', team_b_name='{team_b_name}'")
    print(f"\n{'='*60}")
    print(f"Scraping dual page:")
    print(f"URL: {dual_url}")
    print(f"{'='*60}\n")
    
    print("⚠ Press ENTER to fetch this dual page...")
    input()
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        response = requests.get(dual_url, headers=headers, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract dual date from HTML
        # Look for pattern: "event date: <strong>12/21/25</strong>"
        dual_date = None
        dual_date_iso = None
        date_text = None
        
        # Try to find the event date span
        date_span = soup.find('span', string=re.compile(r'event date', re.I))
        if date_span:
            # Look for strong tag within or after the span
            strong_tag = date_span.find('strong')
            if strong_tag:
                date_text = strong_tag.get_text(strip=True)
            else:
                # Try to find date in the span's text
                span_text = date_span.get_text(strip=True)
                # Extract date pattern
                date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4})', span_text)
                if date_match:
                    date_text = date_match.group(1)
        
        # Fallback: search for date patterns in the page
        if not date_text:
            date_elements = soup.find_all(string=re.compile(r'\d{1,2}/\d{1,2}/\d{2,4}'))
            for date_elem in date_elements:
                elem_text = date_elem.strip()
                date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4})', elem_text)
                if date_match:
                    date_text = date_match.group(1)
                    break
        
        if date_text:
            try:
                # Parse date - handle 2-digit and 4-digit years
                if len(date_text.split('/')[-1]) == 2:
                    # 2-digit year (e.g., "12/21/25")
                    parsed_date = datetime.strptime(date_text, "%m/%d/%y")
                else:
                    # 4-digit year (e.g., "12/21/2025")
                    parsed_date = datetime.strptime(date_text, "%m/%d/%Y")
                
                # Store in ISO format (YYYY-MM-DD) for output
                dual_date_iso = parsed_date.strftime("%Y-%m-%d")
                dual_date = parsed_date.strftime("%m/%d/%Y")  # Keep for backward compatibility
                print(f"[DEBUG] Extracted date: {dual_date} (ISO: {dual_date_iso})")
            except Exception as e:
                print(f"[DEBUG] Error parsing date '{date_text}': {e}")
                date_text = None
        
        if not dual_date:
            dual_date = datetime.now().strftime("%m/%d/%Y")
            dual_date_iso = datetime.now().strftime("%Y-%m-%d")
            print(f"[DEBUG] Could not extract date from page, using current date: {dual_date_iso}")
        
        matches = []
        seen_matches = set()  # Track matches to avoid duplicates
        
        # Parse match results from the boxscore page
        # WrestleStat boxscore typically shows matches in a table
        # Structure: Weight | Team A Wrestler | Team B Wrestler | Result
        
        # First, determine team order from table headers
        team_a_column_idx = None
        team_b_column_idx = None
        
        # Find all tables and look for match data
        # Prefer desktop table (d-none d-sm-block) over mobile table (d-sm-none)
        # to avoid processing duplicates
        all_tables = soup.find_all('table')
        tables = []
        
        # First, try to find desktop table (has better structure)
        for table in all_tables:
            # Check if this table is in a desktop-only container
            parent = table.find_parent(['div', 'section'])
            if parent:
                classes = parent.get('class', [])
                if 'd-none' in classes and 'd-sm-block' in classes:
                    tables.append(table)
                    break
        
        # If no desktop table found, use all tables (fallback)
        if not tables:
            tables = all_tables
        
        print(f"[DEBUG] Processing {len(tables)} table(s) (filtered from {len(all_tables)} total)")
        
        for table in tables:
            # Check header row to determine team column order
            header_row = table.find('tr')
            if header_row:
                header_cells = header_row.find_all(['th', 'td'])
                print(f"[DEBUG] Found {len(header_cells)} header cells")
                for idx, cell in enumerate(header_cells):
                    header_text = cell.get_text(strip=True)
                    header_text_lower = header_text.lower()
                    print(f"[DEBUG] Header cell {idx}: '{header_text}'")
                    # Look for team names in headers (e.g., "Cornell Wrestler", "Illinois Wrestler", "PennsylvaniaWrestler")
                    if 'wrestler' in header_text_lower:
                        # Try to match team names
                        # Remove "wrestler" from header to get just the team name
                        header_without_wrestler = re.sub(r'\s*wrestler\s*', '', header_text_lower, flags=re.IGNORECASE)
                        header_normalized = normalize_name(header_without_wrestler)
                        print(f"[DEBUG] Header '{header_text}' → without wrestler: '{header_without_wrestler}' → normalized: '{header_normalized}'")
                        
                        if team_a_name:
                            team_a_normalized = normalize_name(team_a_name)
                            print(f"[DEBUG] Comparing team A '{team_a_name}' (normalized: '{team_a_normalized}') with header normalized '{header_normalized}'")
                            # Check if team name matches (either way)
                            match_a = team_a_normalized == header_normalized or team_a_normalized in header_normalized or header_normalized in team_a_normalized
                            print(f"[DEBUG] Match result for team A: {match_a} (==: {team_a_normalized == header_normalized}, in: {team_a_normalized in header_normalized}, reverse in: {header_normalized in team_a_normalized})")
                            if match_a:
                                team_a_column_idx = idx
                                print(f"[DEBUG] ✓ Found team A ({team_a_name}) in column {idx} (header: '{header_text}')")
                        if team_b_name:
                            team_b_normalized = normalize_name(team_b_name)
                            print(f"[DEBUG] Comparing team B '{team_b_name}' (normalized: '{team_b_normalized}') with header normalized '{header_normalized}'")
                            match_b = team_b_normalized == header_normalized or team_b_normalized in header_normalized or header_normalized in team_b_normalized
                            print(f"[DEBUG] Match result for team B: {match_b} (==: {team_b_normalized == header_normalized}, in: {team_b_normalized in header_normalized}, reverse in: {header_normalized in team_b_normalized})")
                            if match_b:
                                team_b_column_idx = idx
                                print(f"[DEBUG] ✓ Found team B ({team_b_name}) in column {idx} (header: '{header_text}')")
                
                if team_a_column_idx is None or team_b_column_idx is None:
                    print(f"[DEBUG] Warning: Could not determine team columns. team_a_column_idx={team_a_column_idx}, team_b_column_idx={team_b_column_idx}")
            
            rows = table.find_all('tr')
            
            for row in rows:
                # Skip header rows
                if row.find('th'):
                    continue
                
                cells = row.find_all(['td'])
                if len(cells) < 3:  # Need at least: weight, wrestler A, wrestler B
                    continue
                
                # Find all wrestler links in this row
                wrestler_links = row.find_all('a', href=re.compile(r'/wrestler/\d+'))
                
                if len(wrestler_links) < 2:
                    continue
                
                # Determine which wrestler belongs to which team based on column position
                # Find which cell each wrestler link is in
                wrestler_a_cell_idx = None
                wrestler_b_cell_idx = None
                
                for idx, cell in enumerate(cells):
                    cell_links = cell.find_all('a', href=re.compile(r'/wrestler/\d+'))
                    if cell_links:
                        for link in cell_links:
                            if link == wrestler_links[0]:
                                wrestler_a_cell_idx = idx
                            elif link == wrestler_links[1]:
                                wrestler_b_cell_idx = idx
                
                # If we couldn't determine column positions, fall back to order
                if wrestler_a_cell_idx is None:
                    wrestler_a_cell_idx = 1  # Assume first wrestler column
                if wrestler_b_cell_idx is None:
                    wrestler_b_cell_idx = 2  # Assume second wrestler column
                
                # Extract wrestler IDs and names FIRST (before weight, so we can use names in debug)
                wrestler_a_link = wrestler_links[0]
                wrestler_b_link = wrestler_links[1]
                
                wrestler_a_href = wrestler_a_link.get('href', '')
                wrestler_b_href = wrestler_b_link.get('href', '')
                
                wrestler_a_id_match = re.search(r'/wrestler/(\d+)', wrestler_a_href)
                wrestler_b_id_match = re.search(r'/wrestler/(\d+)', wrestler_b_href)
                
                if not (wrestler_a_id_match and wrestler_b_id_match):
                    continue
                
                wrestler_a_id = int(wrestler_a_id_match.group(1))
                wrestler_b_id = int(wrestler_b_id_match.group(1))
                wrestler_a_name_raw = wrestler_a_link.get_text(strip=True)
                wrestler_b_name_raw = wrestler_b_link.get_text(strip=True)
                
                # Strip ranking prefix (e.g., "#12 " or "12 ") from names
                wrestler_a_name = re.sub(r'^#?\d+\s+', '', wrestler_a_name_raw)
                wrestler_b_name = re.sub(r'^#?\d+\s+', '', wrestler_b_name_raw)
                
                # Extract weight class - look in all cells
                weight = None
                for cell in cells:
                    weight_text = cell.get_text(strip=True)
                    weight_match = re.search(r'(\d{3})', weight_text)
                    if weight_match:
                        weight = int(weight_match.group(1))
                        break
                
                if not weight:
                    continue
                
                # Now we can use weight in debug output
                print(f"[DEBUG] Weight {weight}: wrestler_a_cell_idx={wrestler_a_cell_idx}, wrestler_b_cell_idx={wrestler_b_cell_idx}")
                print(f"[DEBUG] Weight {weight}: team_a_column_idx={team_a_column_idx}, team_b_column_idx={team_b_column_idx}")
                
                # Determine which team each wrestler belongs to
                # If we found team column indices from headers, use those
                # Otherwise, assume first wrestler is team A, second is team B
                if team_a_column_idx is not None and team_b_column_idx is not None:
                    if wrestler_a_cell_idx == team_a_column_idx:
                        wrestler_a_team = 'a'
                        wrestler_b_team = 'b'
                        print(f"[DEBUG] Weight {weight}: wrestler_a ({wrestler_a_name}) is in team A column → team='a'")
                    elif wrestler_a_cell_idx == team_b_column_idx:
                        wrestler_a_team = 'b'
                        wrestler_b_team = 'a'
                        print(f"[DEBUG] Weight {weight}: wrestler_a ({wrestler_a_name}) is in team B column → team='b'")
                    else:
                        # Fallback: use order
                        wrestler_a_team = 'a'
                        wrestler_b_team = 'b'
                        print(f"[DEBUG] Weight {weight}: Could not match columns, using fallback: wrestler_a='a', wrestler_b='b'")
                else:
                    # Fallback: use order (first = team A, second = team B)
                    wrestler_a_team = 'a'
                    wrestler_b_team = 'b'
                    print(f"[DEBUG] Weight {weight}: No team columns found, using fallback: wrestler_a='a', wrestler_b='b'")
                
                # Extract result from remaining cells
                result_text = ""
                for cell in cells:
                    cell_text = cell.get_text(strip=True)
                    # Skip cells that are just weight or wrestler names
                    if str(weight) in cell_text or wrestler_a_name in cell_text or wrestler_b_name in cell_text:
                        continue
                    # Look for result indicators
                    if any(indicator in cell_text.lower() for indicator in ['dec', 'md', 'tf', 'fall', 'pin', 'forfeit', 'inj', 'sv', 'tb']):
                        result_text = cell_text
                        break
                    # Or look for score pattern
                    if re.search(r'\d+-\d+', cell_text):
                        result_text = cell_text
                        break
                
                if not result_text and len(cells) > 2:
                    # Fallback: use last cell
                    result_text = cells[-1].get_text(strip=True)
                
                # Parse result text using helper function
                parsed_result = parse_result_text(result_text)
                
                # Determine winner based on W/L prefix
                if parsed_result["winner_is_a"]:
                    winner_id = wrestler_a_id
                    loser_id = wrestler_b_id
                    winner_name = wrestler_a_name
                    loser_name = wrestler_b_name
                else:
                    winner_id = wrestler_b_id
                    loser_id = wrestler_a_id
                    winner_name = wrestler_b_name
                    loser_name = wrestler_a_name
                
                # Create unique key for this match to avoid duplicates
                match_key = (weight, wrestler_a_id, wrestler_b_id)
                if match_key not in seen_matches:
                    seen_matches.add(match_key)
                    
                    # Get event ID from URL
                    event_id = get_dual_id_from_url(dual_url)
                    
                    # Determine which team each wrestler belongs to
                    # (needed for resolution, but not in final output)
                    if parsed_result["winner_is_a"]:
                        winner_team = wrestler_a_team  # 'a' or 'b'
                        loser_team = wrestler_b_team
                    else:
                        winner_team = wrestler_b_team
                        loser_team = wrestler_a_team
                    
                    # Format match in new structure (matches normalize_match_data output format)
                    match_data = {
                        "date": dual_date_iso,  # ISO format date
                        "weight_ranked": weight,  # Will be updated to ranking weight in normalization
                        "winner": {
                            "wrestlestat_id": winner_id,
                            "matsavant_id": None,  # Will be filled during normalization
                            "name": winner_name,
                            "_team": winner_team  # Temporary: 'a' or 'b' for resolution
                        },
                        "loser": {
                            "wrestlestat_id": loser_id,
                            "matsavant_id": None,  # Will be filled during normalization
                            "name": loser_name,
                            "_team": loser_team  # Temporary: 'a' or 'b' for resolution
                        },
                        "result": parsed_result["result_type"],
                        "score": parsed_result["score"],
                        "source": "wrestlestat",
                        "event_id": int(event_id) if event_id.isdigit() else None
                    }
                    
                    # Add duration for FALL, TF, and INJ results (matches TrackWrestling format)
                    if parsed_result["result_type"] in ("FALL", "TF", "INJ") and parsed_result["time"]:
                        match_data["duration"] = parsed_result["time"]  # Already in "MM:SS" format
                    
                    matches.append(match_data)
                else:
                    print(f"[DEBUG] Skipping duplicate match: {weight} lbs - {wrestler_a_name} vs {wrestler_b_name}")
        
        if not matches:
            print("⚠ Warning: No matches found in boxscore page.")
            print("   Page structure may differ from expected.")
            print("   Please verify the HTML structure and update selectors if needed.")
        
        return {
            "wrestlestat_url": dual_url,
            "date": dual_date,  # Keep for backward compatibility
            "date_iso": dual_date_iso,  # ISO format for new output
            "scraped_at": datetime.now().isoformat(),
            "matches": matches
        }
        
    except Exception as e:
        print(f"❌ Error scraping dual page: {e}")
        return None


def normalize_match_data(
    raw_dual: Dict,
    team_a_id: str,
    team_b_id: str
) -> List[Dict]:
    """
    Convert WrestleStat match data to MatSavant format.
    
    Uses ranking weights (not listed weights) and MatSavant wrestler IDs.
    Outputs in new format with winner/loser structure.
    """
    normalized_matches = []
    
    mappings = load_wrestler_mappings()
    wrestler_id_map = {
        m["wrestlestat_wrestler_id"]: m["matsavant_wrestler_id"]
        for m in mappings
    }
    
    # Get wrestler names from mappings
    wrestler_name_map = {
        m["wrestlestat_wrestler_id"]: m.get("wrestlestat_name", "")
        for m in mappings
    }
    
    # Get event ID from URL
    event_id = get_dual_id_from_url(raw_dual.get("wrestlestat_url", ""))
    
    # Get date in ISO format
    date_iso = raw_dual.get("date_iso")
    if not date_iso:
        # Fallback: try to parse existing date format
        date_str = raw_dual.get("date", "")
        try:
            if len(date_str.split('/')[-1]) == 2:
                parsed_date = datetime.strptime(date_str, "%m/%d/%y")
            else:
                parsed_date = datetime.strptime(date_str, "%m/%d/%Y")
            date_iso = parsed_date.strftime("%Y-%m-%d")
        except:
            date_iso = datetime.now().strftime("%Y-%m-%d")
    
    for match in raw_dual.get("matches", []):
        # Raw file now uses new format with winner/loser structure
        winner_ws_id = match["winner"]["wrestlestat_id"]
        loser_ws_id = match["loser"]["wrestlestat_id"]
        
        winner_ms_id = wrestler_id_map.get(winner_ws_id)
        loser_ms_id = wrestler_id_map.get(loser_ws_id)
        
        if not (winner_ms_id and loser_ms_id):
            print(f"⚠ Skipping match: missing wrestler mappings")
            continue
        
        # Get ranking weights from mappings
        winner_weight = None
        loser_weight = None
        
        for m in mappings:
            if m["wrestlestat_wrestler_id"] == winner_ws_id:
                winner_weight = m.get("ranking_weight")
            if m["wrestlestat_wrestler_id"] == loser_ws_id:
                loser_weight = m.get("ranking_weight")
        
        if not (winner_weight and loser_weight):
            print(f"⚠ Skipping match: missing weight mappings")
            continue
        
        # Use ranking weight (not listed weight)
        weight_ranked = winner_weight  # Should be same for both
        
        # Get names (prefer from match, fallback to mappings)
        winner_name = match["winner"].get("name", wrestler_name_map.get(winner_ws_id, ""))
        loser_name = match["loser"].get("name", wrestler_name_map.get(loser_ws_id, ""))
        
        # Build normalized match (updating matsavant_id and weight_ranked)
        normalized_match = match.copy()
        normalized_match["weight_ranked"] = weight_ranked
        normalized_match["winner"]["matsavant_id"] = winner_ms_id
        normalized_match["loser"]["matsavant_id"] = loser_ms_id
        normalized_match["winner"]["name"] = winner_name
        normalized_match["loser"]["name"] = loser_name
        
        # Remove temporary fields used for resolution
        normalized_match["winner"].pop("_team", None)
        normalized_match["loser"].pop("_team", None)
        
        normalized_matches.append(normalized_match)
    
    return normalized_matches


def main():
    """Main ingestion pipeline."""
    print("\n" + "="*60)
    print("WrestleStat → MatSavant Ingestion Pipeline")
    print("="*60)
    print("\n⚠ SAFETY RULES:")
    print("  - NO automatic page clicking")
    print("  - EVERY page load requires ENTER confirmation")
    print("  - ALL mappings are permanent and auditable")
    print("  - TrackWrestling remains primary source\n")
    
    # Step 1: Load Recent Duals Index
    duals = scrape_recent_duals_index("Last Week")
    
    if not duals:
        print("❌ No duals found. Exiting.")
        return
    
    print(f"\n✓ Found {len(duals)} duals")
    print("\nPress ENTER to begin processing duals one by one...")
    input()
    
    # Step 2-7: Process each dual
    processed_count = 0
    skipped_count = 0
    
    for idx, dual in enumerate(duals, 1):
        print(f"\n{'='*60}")
        print(f"Dual {idx}/{len(duals)}")
        print(f"{'='*60}")
        print(f"Team A: {dual['team_a_name']} (WS ID: {dual['team_a_id']})")
        print(f"Team B: {dual['team_b_name']} (WS ID: {dual['team_b_id']})")
        print(f"URL: {dual['wrestlestat_url']}")
        
        # Step 2: Resolve teams
        team_a_ms_id = resolve_wrestlestat_team(
            dual['team_a_id'],
            dual['team_a_name'],
            SEASON
        )
        team_b_ms_id = resolve_wrestlestat_team(
            dual['team_b_id'],
            dual['team_b_name'],
            SEASON
        )
        
        # Check if either team is non-D1 or resolution failed
        if team_a_ms_id is None or team_b_ms_id is None:
            if team_a_ms_id is None:
                print(f"⚠ Skipping dual: {dual['team_a_name']} is non-D1 or unresolved")
            if team_b_ms_id is None:
                print(f"⚠ Skipping dual: {dual['team_b_name']} is non-D1 or unresolved")
            skipped_count += 1
            continue
        
        # Step 3: Check if already ingested
        is_ingested, reason = check_dual_already_ingested(
            team_a_ms_id,
            team_b_ms_id,
            dual['wrestlestat_url']
        )
        
        if is_ingested:
            print(f"✓ Dual already ingested: {reason}")
            skipped_count += 1
            continue
        
        # Step 4: Human-gated page open
        print(f"\nNext dual requires scraping: {dual['team_a_name']} vs {dual['team_b_name']}")
        raw_dual = scrape_dual_page(
            dual['wrestlestat_url'],
            team_a_name=dual['team_a_name'],
            team_b_name=dual['team_b_name']
        )
        
        if not raw_dual:
            print("⚠ Skipping dual: scraping failed")
            skipped_count += 1
            continue
        
        # Step 5: Extract matches (already done in scrape_dual_page)
        print(f"✓ Extracted {len(raw_dual.get('matches', []))} matches")
        
        # Save raw data
        dual_id = get_dual_id_from_url(dual['wrestlestat_url'])
        RAW_DUALS_DIR.mkdir(parents=True, exist_ok=True)
        raw_file = RAW_DUALS_DIR / f"{dual_id}.json"
        with open(raw_file, 'w') as f:
            json.dump(raw_dual, f, indent=2)
        
        # Step 6: Resolve wrestlers
        print("\nResolving wrestlers...")
        all_wrestlers_resolved = True
        for match in raw_dual.get('matches', []):
            winner_ws_id = match['winner']['wrestlestat_id']
            loser_ws_id = match['loser']['wrestlestat_id']
            winner_name = match['winner']['name']
            loser_name = match['loser']['name']
            weight = match['weight_ranked']
            
            # Get team assignments from _team field (stored during scraping)
            winner_team = match['winner'].get('_team', 'a')  # Default to 'a' if not set
            loser_team = match['loser'].get('_team', 'b')  # Default to 'b' if not set
            
            # Determine MatSavant team IDs based on team assignments
            winner_ms_team_id = team_a_ms_id if winner_team == 'a' else team_b_ms_id
            loser_ms_team_id = team_b_ms_id if loser_team == 'b' else team_a_ms_id
            
            print(f"[DEBUG] Resolving {winner_name}: winner_team={winner_team}, using MatSavant team_id={winner_ms_team_id}")
            print(f"[DEBUG] Resolving {loser_name}: loser_team={loser_team}, using MatSavant team_id={loser_ms_team_id}")
            
            # Resolve winner
            winner_ms_id = resolve_wrestlestat_wrestler(
                winner_ws_id,
                winner_name,
                winner_ms_team_id,
                weight,
                SEASON
            )
            
            # Resolve loser
            loser_ms_id = resolve_wrestlestat_wrestler(
                loser_ws_id,
                loser_name,
                loser_ms_team_id,
                weight,
                SEASON
            )
            
            if not (winner_ms_id and loser_ms_id):
                print(f"⚠ Match unresolved: {winner_name} vs {loser_name}")
                all_wrestlers_resolved = False
                continue
        
        if not all_wrestlers_resolved:
            print("⚠ Some wrestlers could not be resolved. Processed matches will use available mappings.")
        
        # Step 7: Normalize match data
        normalized_matches = normalize_match_data(
            raw_dual,
            team_a_ms_id,
            team_b_ms_id
        )
        
        # Save processed data
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        processed_file = PROCESSED_DIR / f"{dual_id}.json"
        with open(processed_file, 'w') as f:
            json.dump({
                "dual_id": dual_id,
                "wrestlestat_url": dual['wrestlestat_url'],
                "team_a": team_a_ms_id,
                "team_b": team_b_ms_id,
                "matches": normalized_matches,
                "processed_at": datetime.now().isoformat()
            }, f, indent=2)
        
        processed_count += 1
        print(f"✓ Processed dual {idx}/{len(duals)}")
    
    print(f"\n{'='*60}")
    print("Ingestion Complete")
    print(f"{'='*60}")
    print(f"Processed: {processed_count}")
    print(f"Skipped: {skipped_count}")
    print(f"Total: {len(duals)}")


if __name__ == "__main__":
    main()

