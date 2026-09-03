#!/usr/bin/env python3
"""
Scrape KHSAA regional wrestling placement results from TrackWrestling.

For each of 8 KHSAA regions and each season 2013-2026:
  1. Search TrackWrestling for "KHSAA Region N Wrestling"
  2. Find the tournament ID matching that season year
  3. Enter the tournament (public, no password)
  4. Scrape placement results from PlacementResults.jsp
  5. Save to data/hs_ky_boys/{season}/regional_placements/region_{N}.txt

Output format matches existing data/hs_ky_boys/{season}/placement.txt:
  106
  1st Place Match - Name (Team) W-L won by method over Name (Team) W-L (detail)
  3rd Place Match - ...
  5th Place Match - ...
  7th Place Match - ...
  113
  ...

Usage:
    # Scrape everything (all 8 regions, all seasons 2013-2026)
    python scripts/scraping/scrape_khsaa_regionals.py

    # Single region / single season
    python scripts/scraping/scrape_khsaa_regionals.py --region 1 --season 2026

    # Discover and cache tournament IDs only (no placement scraping)
    python scripts/scraping/scrape_khsaa_regionals.py --discover-only

    # Debug mode: save raw HTML to data/_debug/
    python scripts/scraping/scrape_khsaa_regionals.py --region 1 --season 2026 --debug

    # Skip seasons/regions already scraped
    python scripts/scraping/scrape_khsaa_regionals.py --skip-existing
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.common import weight_class_eras as era_weight_classes  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://www.trackwrestling.com"
SEASONS = list(range(2013, 2027))  # 2013-2026 inclusive
REGIONS = list(range(1, 9))        # 1-8 (boys); overridden to 1-4 for girls

# Output directories
DATA_BASE = Path("data/hs_ky_boys")
TOURNAMENT_ID_CACHE = Path("data/_debug/khsaa_regional_tournament_ids.json")
DEBUG_DIR = Path("data/_debug/khsaa_regionals")

# Search terms map: these are what we search on TW for each region
REGION_SEARCH_TERMS = {
    1: "KHSAA Region 1",
    2: "KHSAA Region 2",
    3: "KHSAA Region 3",
    4: "KHSAA Region 4",
    5: "KHSAA Region 5",
    6: "KHSAA Region 6",
    7: "KHSAA Region 7",
    8: "KHSAA Region 8",
}

# Gender — overridden in main() via --gender arg
GENDER = "boys"


def get_weight_classes_for_season(season: int) -> list[int]:
    """Delegates to the shared, era-aware table in data/weight_class_eras/hs_ky_{gender}.json."""
    return era_weight_classes.get_weight_classes_for_season(GENDER, season)


# ---------------------------------------------------------------------------
# HTTP Session helpers
# ---------------------------------------------------------------------------

def get_tim() -> int:
    return int(time.time() * 1000)


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })
    return session


def establish_session(session: requests.Session, debug: bool = False) -> str | None:
    """GET Login.jsp to get an anonymous session ID."""
    url = f"{BASE_URL}/Login.jsp"
    try:
        resp = session.get(url, timeout=15)
    except requests.RequestException as e:
        print(f"  [ERROR] GET Login.jsp failed: {e}")
        return None

    # Try several patterns for the session ID
    for pattern in [
        r'twMenuSessionId\s*=\s*["\']([a-zA-Z0-9]+)["\']',
        r'twSessionId[="\s]+([a-zA-Z0-9]{8,})',
        r'name="twSessionId"\s+value="([a-zA-Z0-9]+)"',
        r'TIM=\d+&twSessionId=([a-zA-Z0-9]+)',
    ]:
        m = re.search(pattern, resp.text)
        if m:
            sid = m.group(1)
            if debug:
                print(f"  [OK] Session ID: {sid} (pattern: {pattern[:40]})")
            return sid

    print("  [FAIL] Could not find twSessionId in Login.jsp")
    if debug:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        (DEBUG_DIR / "Login_raw.html").write_text(resp.text)
        print(f"  [DEBUG] Saved Login.jsp to {DEBUG_DIR}/Login_raw.html")
    return None


def enter_tournament(
    session: requests.Session,
    session_id: str,
    tournament_id: int,
    debug: bool = False,
) -> str | None:
    """
    Enter a tournament via VerifyPassword.jsp (empty password = public access).
    Returns the tournament-scoped session ID, or None on failure.
    """
    url = (
        f"{BASE_URL}/predefinedtournaments/VerifyPassword.jsp"
        f"?TIM={get_tim()}&twSessionId={session_id}"
        f"&tournamentId={tournament_id}&userType=viewer&userName=&password="
    )
    try:
        resp = session.get(url, timeout=15, allow_redirects=True)
    except requests.RequestException as e:
        print(f"  [ERROR] VerifyPassword.jsp: {e}")
        return None

    if "flowrestling.org" in resp.url or "flowrestling" in resp.url:
        print(f"  [FAIL] Redirected to Flowrestling: {resp.url}")
        return None

    # Try to get a tournament-scoped session ID from MainFrame.jsp
    main_url = (
        f"{BASE_URL}/predefinedtournaments/MainFrame.jsp"
        f"?newSession=false&TIM={get_tim()}"
        f"&pageName=%2Fpredefinedtournaments%2FViewWeightClass.jsp"
        f"&twSessionId={session_id}"
    )
    try:
        main_resp = session.get(main_url, timeout=15)
    except requests.RequestException as e:
        print(f"  [ERROR] MainFrame.jsp: {e}")
        return session_id

    for pattern in [
        r'twMenuSessionId\s*=\s*["\']([a-zA-Z0-9]+)["\']',
        r'ViewWeightClass\.jsp\?TIM=\d+&twSessionId=([a-zA-Z0-9]+)',
        r'twSessionId=([a-zA-Z0-9]{8,})',
    ]:
        m = re.search(pattern, main_resp.text)
        if m:
            tsid = m.group(1)
            if debug:
                print(f"  [OK] Tournament session ID: {tsid}")
            return tsid

    if debug:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        (DEBUG_DIR / f"MainFrame_{tournament_id}.html").write_text(main_resp.text)
        print(f"  [DEBUG] Saved MainFrame.jsp to {DEBUG_DIR}/MainFrame_{tournament_id}.html")

    return session_id


# ---------------------------------------------------------------------------
# Tournament search
# ---------------------------------------------------------------------------

def search_tournaments(
    session: requests.Session,
    session_id: str,
    query: str,
    debug: bool = False,
) -> list[dict]:
    """
    Search TrackWrestling for tournaments matching `query`.
    Returns list of {tournament_id, name, date_str} dicts.
    """
    # Try the main search endpoint
    results = []

    search_url = (
        f"{BASE_URL}/Search.jsp"
        f"?TIM={get_tim()}&twSessionId={session_id}"
        f"&searchTerm={requests.utils.quote(query)}&searchType=tournament"
    )
    try:
        resp = session.get(search_url, timeout=15)
    except requests.RequestException as e:
        print(f"  [ERROR] Search.jsp: {e}")
        return results

    if debug:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r'[^a-zA-Z0-9_]', '_', query)
        (DEBUG_DIR / f"Search_{safe}.html").write_text(resp.text)

    results.extend(_parse_search_results(resp.text, debug))

    # Also try POST to SearchResults.jsp (alternate TW pattern)
    if not results:
        post_url = f"{BASE_URL}/SearchResults.jsp"
        try:
            resp2 = session.post(
                post_url,
                data={"searchTerm": query, "twSessionId": session_id, "TIM": get_tim()},
                timeout=15,
            )
            results.extend(_parse_search_results(resp2.text, debug))
        except requests.RequestException:
            pass

    # Also try the AJAX JSON search
    if not results:
        ajax_url = (
            f"{BASE_URL}/api/tournaments/search"
            f"?query={requests.utils.quote(query)}&twSessionId={session_id}"
        )
        try:
            resp3 = session.get(ajax_url, timeout=15)
            if resp3.headers.get("Content-Type", "").startswith("application/json"):
                data = resp3.json()
                results.extend(_parse_json_search_results(data, debug))
        except (requests.RequestException, ValueError):
            pass

    return results


def _parse_search_results(html: str, debug: bool = False) -> list[dict]:
    """Parse tournament search results HTML into list of {tournament_id, name, date_str}."""
    results = []
    soup = BeautifulSoup(html, "html.parser")

    # Pattern 1: links to predefinedtournaments with tournamentId param
    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = re.search(r'tournamentId=(\d+)', href)
        if not m:
            continue
        tid = int(m.group(1))
        name = a.get_text(strip=True)
        # Look for a date near this link
        parent = a.find_parent()
        date_str = ""
        if parent:
            text = parent.get_text(" ", strip=True)
            dm = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4})', text)
            if dm:
                date_str = dm.group(1)
        if tid and name:
            results.append({"tournament_id": tid, "name": name, "date_str": date_str})

    # Pattern 2: raw JavaScript with tournamentId values
    for m in re.finditer(r'tournamentId[=:]\s*["\']?(\d{6,12})', html):
        tid = int(m.group(1))
        if any(r["tournament_id"] == tid for r in results):
            continue
        # Try to find a name nearby
        start = max(0, m.start() - 300)
        end = min(len(html), m.end() + 300)
        snippet = re.sub(r'<[^>]+>', ' ', html[start:end])
        snippet = re.sub(r'\s+', ' ', snippet).strip()
        results.append({"tournament_id": tid, "name": snippet[:120], "date_str": ""})

    # Deduplicate by tournament_id
    seen = set()
    deduped = []
    for r in results:
        if r["tournament_id"] not in seen:
            seen.add(r["tournament_id"])
            deduped.append(r)

    return deduped


def _parse_json_search_results(data, debug: bool = False) -> list[dict]:
    """Parse JSON search response."""
    results = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("tournaments") or data.get("results") or []
    else:
        return results

    for item in items:
        tid = item.get("tournamentId") or item.get("id")
        name = item.get("name") or item.get("tournamentName") or ""
        date_str = item.get("date") or item.get("startDate") or ""
        if tid and name:
            results.append({"tournament_id": int(tid), "name": name, "date_str": str(date_str)})
    return results


def infer_season_from_tournament(t: dict) -> int | None:
    """
    Guess the academic season year (e.g. 2026 = competed Jan/Feb 2026)
    from tournament name or date string.
    """
    name = t.get("name", "") + " " + t.get("date_str", "")

    # Explicit 4-digit year in name
    years = re.findall(r'\b(20\d{2})\b', name)
    if years:
        yr = int(years[0])
        # KHSAA regionals happen Jan/Feb, so the 4-digit year IS the season
        return yr

    # Date string like "1/25/26" or "01/25/2026"
    dm = re.search(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', t.get("date_str", ""))
    if dm:
        month = int(dm.group(1))
        yr_raw = dm.group(3)
        yr = int(yr_raw) if len(yr_raw) == 4 else 2000 + int(yr_raw)
        # Regionals: Jan = season matches calendar year; Aug-Dec = next season
        if month <= 6:
            return yr
        else:
            return yr + 1

    return None


# ---------------------------------------------------------------------------
# Placement results scraping
# ---------------------------------------------------------------------------

def _post_round_results(
    session: requests.Session,
    tsid: str,
    tournament_id: int,
    round_id: str,
) -> str:
    """POST RoundResults.jsp for a specific round ID and return response text."""
    action_url = (
        f"{BASE_URL}/predefinedtournaments/RoundResults.jsp"
        f"?TIM={get_tim()}&twSessionId={tsid}"
        f"&tournamentId={tournament_id}"
        f"&displayResult=Y&roundId={round_id}&groupId="
    )
    post_data = {
        "patternBox": "1",
        "displayFormatBox": "2",
        "roundIdBox": round_id,
        "groupIdBox": "",
        "includeByesBox": "Y",
        "fontSizeBox": "10",
    }
    resp = session.post(action_url, data=post_data, timeout=20)
    return resp.text


def _find_placement_rounds(round_sel) -> list[tuple[str, str]]:
    """
    Identify which round(s) contain placement match data.
    Returns list of (round_id, round_label) pairs to fetch.

    Strategy: collect ALL rounds that look like they could contain place matches.
    The parser will filter to only actual "Xst/Xnd/Xrd/Xth Place Match" lines,
    so including extra rounds (semifinals, etc.) is harmless.
    """
    options = [
        (opt.get("value", "").strip(), opt.get_text(strip=True))
        for opt in round_sel.find_all("option")
        if opt.get("value", "").strip()
    ]

    placement_rounds = []
    for val, text in options:
        if re.search(
            r'\bplacement'
            r'|\b(1st|2nd|3rd|4th|5th|6th|7th|8th)\s+place'
            r'|\bchamp'
            r'|\bfinals?\b'
            r'|\bfinal\s+round\b'
            r'|3rd\s+and\s+5th'
            r'|3rd\s+&\s+5th'
            r'|place\s+match',
            text, re.IGNORECASE,
        ):
            placement_rounds.append((val, text))

    return placement_rounds


def fetch_placement_html(
    session: requests.Session,
    tsid: str,
    tournament_id: int,
    debug: bool = False,
) -> str | None:
    """
    Fetch placement results from TrackWrestling via a two-step process:
    1. GET RoundResults.jsp to find placement round(s)
    2. POST RoundResults.jsp with displayResult=Y to get actual HTML content

    Some tournaments use a single "Placements" round; others split into
    separate rounds per place. In the latter case we fetch each round and
    stitch the HTML together so the parser sees all sections.
    """
    # Step 1: GET the filter form to discover available rounds
    filter_url = (
        f"{BASE_URL}/predefinedtournaments/RoundResults.jsp"
        f"?TIM={get_tim()}&twSessionId={tsid}&tournamentId={tournament_id}"
    )
    try:
        filter_resp = session.get(filter_url, timeout=15)
    except requests.RequestException as e:
        print(f"  [ERROR] GET RoundResults.jsp: {e}")
        return None

    soup = BeautifulSoup(filter_resp.text, "html.parser")
    round_sel = (
        soup.find("select", {"id": "roundIdBox"})
        or soup.find("select", {"name": "roundIdBox"})
    )
    if not round_sel:
        print(f"  [FAIL] No roundIdBox found for tournament {tournament_id}")
        if debug:
            DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            (DEBUG_DIR / f"RoundResults_filter_{tournament_id}.html").write_text(filter_resp.text)
        return None

    placement_rounds = _find_placement_rounds(round_sel)

    if not placement_rounds:
        all_rounds = [(o.get("value",""), o.get_text(strip=True))
                      for o in round_sel.find_all("option") if o.get("value","")]
        print(f"  [FAIL] No placement rounds identified for tournament {tournament_id}")
        if debug:
            print(f"  Available rounds: {all_rounds}")
        return None

    if debug:
        print(f"  [OK] Placement round(s): {placement_rounds}")

    # Step 2: POST each placement round and collect sections
    combined_sections: list[str] = []
    for round_id, round_label in placement_rounds:
        try:
            html = _post_round_results(session, tsid, tournament_id, round_id)
        except requests.RequestException as e:
            print(f"  [ERROR] POST RoundResults.jsp round={round_id}: {e}")
            continue

        if debug:
            DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            (DEBUG_DIR / f"Placement_{tournament_id}_{round_id}.html").write_text(html)

        # Extract tw-list sections from this round's response
        round_soup = BeautifulSoup(html, "html.parser")
        sections = round_soup.find_all("section", class_="tw-list")
        for sec in sections:
            combined_sections.append(str(sec))

        if not sections and re.search(r'(1st Place|Place Match)', html):
            # Fallback: return raw HTML if it has place match text but no sections
            combined_sections.append(html)

        time.sleep(0.2)

    if not combined_sections:
        print(f"  [FAIL] POST returned no placement content for tournament {tournament_id}")
        return None

    # Wrap combined sections in minimal HTML for the parser
    return "<html><body>" + "\n".join(combined_sections) + "</body></html>"


def parse_placement_html(html: str, season: int, debug: bool = False) -> dict[int, list[str]]:
    """
    Parse placement results HTML and return {weight_class: [line1, line2, ...]} dict.
    Each line is a place match line like:
      "1st Place Match - Name (Team) W-L won by method over Name (Team) W-L (detail)"

    Handles TrackWrestling's <section class='tw-list'> format:
      <h1>106</h1>
      <h2>Placements</h2>
      <ul><li>1st Place Match - ...</li>...</ul>
    """
    soup = BeautifulSoup(html, "html.parser")
    results: dict[int, list[str]] = {}

    # Regex for actual place match lines: "1st Place Match - ...", "3rd Place Match - ..."
    place_match_re = re.compile(
        r'^\d+(?:st|nd|rd|th)\s+Place\s+Match\b', re.IGNORECASE
    )

    # Primary: structured tw-list sections
    for section in soup.find_all("section", class_="tw-list"):
        h1 = section.find("h1")
        if not h1:
            continue
        weight_text = h1.get_text(strip=True)
        if not weight_text.isdigit():
            continue
        wt = int(weight_text)
        for li in section.find_all("li"):
            line = li.get_text(strip=True)
            # Only keep actual place match lines, skip byes/other rounds
            if line and place_match_re.match(line):
                results.setdefault(wt, []).append(line)

    if results:
        if debug:
            total = sum(len(v) for v in results.values())
            print(f"  [DEBUG] Parsed {total} place matches across {len(results)} weight classes")
        return results

    # Fallback: plain-text parse
    text = soup.get_text("\n")
    return _parse_placement_text(text, season, debug)


def _parse_placement_text(text: str, season: int, debug: bool = False) -> dict[int, list[str]]:
    """
    Parse plain-text placement output. Handles TrackWrestling text-results format.

    TW text results placement lines look like:
      "1st Place: Name (Team) W-L over Name (Team) W-L by Method (detail)"
    or:
      "1st Place Match - Name (Team) W-L won by method over Name (Team) W-L (detail)"
    or the raw CSV/TSV variant:
      "Place,Weight,Name,Team,W,L,Result"
    """
    results: dict[int, list[str]] = {}
    expected_weights = get_weight_classes_for_season(season)

    lines = text.splitlines()
    current_weight = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Weight class line — just a number matching a known weight class
        if re.match(r'^\d{2,3}$', line):
            wt = int(line)
            if wt in expected_weights or (90 <= wt <= 400):
                current_weight = wt
                if current_weight not in results:
                    results[current_weight] = []
                continue

        # Weight class embedded in line: "Weight Class: 106" or "106 lbs"
        wm = re.match(r'^(?:Weight\s+Class[:\s]+)?(\d{2,3})\s*(?:lbs?\.?|pounds?)?$', line, re.I)
        if wm:
            wt = int(wm.group(1))
            if 90 <= wt <= 400:
                current_weight = wt
                if current_weight not in results:
                    results[current_weight] = []
                continue

        # Place match lines — various TW formats
        place_match = _parse_place_match_line(line)
        if place_match and current_weight is not None:
            results[current_weight].append(place_match)
            continue

        # Try extracting weight from place match line itself
        # e.g. "106 - 1st Place: ..."
        wt_inline = re.match(r'^(\d{2,3})\s*[-–]\s*((?:1st|2nd|3rd|[4-9]th)\s+Place)', line, re.I)
        if wt_inline:
            wt = int(wt_inline.group(1))
            if 90 <= wt <= 400:
                current_weight = wt
                if current_weight not in results:
                    results[current_weight] = []
                rest = line[wt_inline.end():].strip()
                pm = _parse_place_match_line(rest)
                if pm and current_weight is not None:
                    results[current_weight].append(pm)

    if debug and results:
        print(f"  [DEBUG] Parsed {sum(len(v) for v in results.values())} place matches "
              f"across {len(results)} weight classes")

    return results


PLACE_LABELS = {
    1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th", 6: "6th", 7: "7th", 8: "8th",
}

# Patterns for different TW place-match line formats
_PLACE_PATTERNS = [
    # Format A (matches existing placement.txt style):
    # "1st Place Match - Name (Team) W-L won by method over Name (Team) W-L (detail)"
    re.compile(
        r'^(?P<ord>\d+(?:st|nd|rd|th))\s+Place\s+Match\s*[-–:]\s*'
        r'(?P<winner>[^(]+?)\s*\((?P<wteam>[^)]+)\)\s+(?P<wrec>\d+-\d+)\s+'
        r'won\s+(?P<verdict>.+?)\s+over\s+'
        r'(?P<loser>[^(]+?)\s*\((?P<lteam>[^)]+)\)\s+(?P<lrec>\d+-\d+)\s*'
        r'(?P<detail>\(.*\))?$',
        re.IGNORECASE,
    ),
    # Format B:
    # "1st Place: Name (Team) W-L def. Name (Team) W-L by Method (detail)"
    re.compile(
        r'^(?P<ord>\d+(?:st|nd|rd|th))\s+Place\s*[:]\s*'
        r'(?P<winner>[^(]+?)\s*\((?P<wteam>[^)]+)\)\s+(?P<wrec>\d+-\d+)\s+'
        r'(?:def\.?|defeated|over)\s+'
        r'(?P<loser>[^(]+?)\s*\((?P<lteam>[^)]+)\)\s+(?P<lrec>\d+-\d+)\s*'
        r'(?:by\s+)?(?P<verdict>.+?)\s*(?P<detail>\(.*\))?$',
        re.IGNORECASE,
    ),
    # Format C — TW text results "1st Place - Name def. Name":
    re.compile(
        r'^(?P<ord>\d+(?:st|nd|rd|th))\s+(?:Place\s+)?[-–]\s*'
        r'(?P<winner>[^(]+?)\s*\((?P<wteam>[^)]+)\)\s+(?P<wrec>\d+-\d+)\s+'
        r'(?:def\.?|won\s+over|over)\s+'
        r'(?P<loser>[^(]+?)\s*\((?P<lteam>[^)]+)\)\s+(?P<lrec>\d+-\d+)\s*'
        r'(?P<detail>\(.*\))?$',
        re.IGNORECASE,
    ),
]

# Method normalization
_METHOD_MAP = {
    r'\bfall\b': 'fall',
    r'\bpin\b': 'fall',
    r'\btech(?:nical)?\s+fall\b': 'tech fall',
    r'\bTF\b': 'tech fall',
    r'\bTF-1\.5\b': 'tech fall',
    r'\bmajor\s+decis(?:ion)?\b': 'major decision',
    r'\bMD\b': 'major decision',
    r'\bdecis(?:ion)?\b': 'decision',
    r'\bDec\b': 'decision',
    r'\bforfeit\b': 'forfeit',
    r'\bFF\b': 'forfeit',
    r'\binjury\s+default\b': 'injury default',
    r'\bdisqualification\b': 'disqualification',
    r'\btie\s+breaker\b': 'tie breaker - 1',
    r'\bTB-1\b': 'tie breaker - 1',
    r'\bTB-2\b': 'tie breaker - 2',
    r'\bsudden\s+victory\b': 'sudden victory - 1',
    r'\bSV-1\b': 'sudden victory - 1',
    r'\bultimate\s+tie\s+breaker\b': 'the ultimate tie breaker',
    r'\bUTB\b': 'the ultimate tie breaker',
}


def _normalize_method(verdict: str) -> str:
    """Normalize win method to standard form."""
    v = verdict.strip()
    for pat, replacement in _METHOD_MAP.items():
        v = re.sub(pat, replacement, v, flags=re.IGNORECASE)
    return v.strip()


def _parse_place_match_line(line: str) -> str | None:
    """
    Try to parse a place match line and return it in canonical format.
    Returns None if line doesn't match any known format.
    """
    line = line.strip()
    if not line:
        return None

    # Try each pattern
    for pat in _PLACE_PATTERNS:
        m = pat.match(line)
        if m:
            ord_str = m.group("ord").lower()
            winner = m.group("winner").strip()
            wteam = m.group("wteam").strip()
            wrec = m.group("wrec").strip()
            loser = m.group("loser").strip()
            lteam = m.group("lteam").strip()
            lrec = m.group("lrec").strip()
            verdict = _normalize_method(m.group("verdict"))
            detail = m.group("detail") or ""
            detail = detail.strip()

            # Reconstruct in canonical form
            # "Xst Place Match - Winner (Team) W-L won by method over Loser (Team) W-L (detail)"
            place_label = ord_str.title().replace("Nd", "nd").replace("Rd", "rd").replace("Th", "th")
            line_out = (
                f"{place_label} Place Match - {winner} ({wteam}) {wrec} "
                f"won by {verdict} over {loser} ({lteam}) {lrec}"
            )
            if detail:
                line_out += f" {detail}"
            return line_out

    # Check if line already looks like canonical format — pass through
    if re.match(
        r'^\d+(?:st|nd|rd|th)\s+Place\s+Match\s*[-–:]',
        line,
        re.IGNORECASE,
    ):
        return line

    return None


def format_placement_output(
    placements: dict[int, list[str]],
    season: int,
) -> str:
    """Format parsed placements as placement.txt text."""
    lines = []
    weights = sorted(placements.keys())
    expected = get_weight_classes_for_season(season)

    for w in weights:
        if placements[w]:  # Only include weights with actual results
            lines.append(str(w))
            lines.extend(placements[w])

    return "\n".join(lines) + "\n" if lines else ""


# ---------------------------------------------------------------------------
# Tournament ID discovery & caching
# ---------------------------------------------------------------------------

def load_tournament_id_cache() -> dict:
    """Load cached {region: {season: tournament_id}} map."""
    if TOURNAMENT_ID_CACHE.exists():
        with TOURNAMENT_ID_CACHE.open(encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_tournament_id_cache(cache: dict) -> None:
    TOURNAMENT_ID_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with TOURNAMENT_ID_CACHE.open("w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)
    print(f"  Saved tournament ID cache → {TOURNAMENT_ID_CACHE}")


def find_tournament_ids_for_region(
    session: requests.Session,
    session_id: str,
    region: int,
    target_seasons: list[int],
    debug: bool = False,
) -> dict[int, int]:
    """
    Search TW for all KHSAA Region N tournaments and return {season: tournament_id}.
    """
    query = REGION_SEARCH_TERMS[region]
    print(f"  Searching: '{query}'...")
    time.sleep(0.5)

    all_results = search_tournaments(session, session_id, query, debug=debug)
    print(f"  Found {len(all_results)} raw results")

    if debug:
        for r in all_results:
            print(f"    tournament_id={r['tournament_id']} name={r['name'][:80]} date={r['date_str']}")

    season_map: dict[int, int] = {}
    for r in all_results:
        # Filter to Kentucky / KHSAA results
        name_lower = r["name"].lower()
        if "khsaa" not in name_lower and "kentucky" not in name_lower and "ky" not in name_lower:
            # Allow if it's a clear region match (sometimes TW omits state)
            if f"region {region}" not in name_lower:
                continue

        # Filter by gender
        has_girls = "girl" in name_lower or "female" in name_lower
        if GENDER == "girls" and not has_girls:
            # Skip boys-only results when searching for girls
            if "boy" in name_lower or "male" in name_lower:
                continue
        elif GENDER == "boys" and has_girls:
            continue

        season = infer_season_from_tournament(r)
        if season is None:
            continue
        if season not in target_seasons:
            continue

        # Prefer the first / best match per season
        if season not in season_map:
            season_map[season] = r["tournament_id"]
            print(f"    → Season {season}: tournament_id={r['tournament_id']} ({r['name'][:60]})")

    return season_map


# ---------------------------------------------------------------------------
# Main scraping flow
# ---------------------------------------------------------------------------

def scrape_region_season(
    session: requests.Session,
    session_id: str,
    region: int,
    season: int,
    tournament_id: int,
    debug: bool = False,
) -> bool:
    """
    Scrape placement results for one region/season.
    Returns True on success, False on failure.
    """
    out_dir = DATA_BASE / str(season) / "regional_placements"
    out_path = out_dir / f"region_{region}.txt"

    print(f"  Entering tournament {tournament_id} ...")
    tsid = enter_tournament(session, session_id, tournament_id, debug=debug)
    if tsid is None:
        print(f"  [FAIL] Could not enter tournament {tournament_id}")
        return False

    time.sleep(0.3)

    print(f"  Fetching placement results ...")
    html = fetch_placement_html(session, tsid, tournament_id, debug=debug)
    if html is None:
        print(f"  [FAIL] No placement content found for tournament {tournament_id}")
        return False

    placements = parse_placement_html(html, season, debug=debug)
    if not placements:
        print(f"  [WARN] Parsed 0 weight classes from tournament {tournament_id}")
        if debug:
            DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            (DEBUG_DIR / f"Parsed_empty_{tournament_id}.txt").write_text(html[:5000])
        return False

    output = format_placement_output(placements, season)
    if not output.strip():
        print(f"  [WARN] No output generated for tournament {tournament_id}")
        return False

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(output, encoding="utf-8")
    total_matches = sum(len(v) for v in placements.values())
    print(f"  ✓ Saved {len(placements)} weight classes, {total_matches} place matches → {out_path}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Scrape KHSAA regional placement results")
    parser.add_argument("--gender", choices=["boys", "girls"], default="boys",
                        help="boys (8 regions, data/hs_ky_boys) or girls (4 regions, data/hs_ky_girls)")
    parser.add_argument("--region", type=int,
                        help="Single region to scrape (default: all regions for gender)")
    parser.add_argument("--season", type=int, choices=SEASONS,
                        help="Single season to scrape (default: all 2013-2026)")
    parser.add_argument("--discover-only", action="store_true",
                        help="Only discover and cache tournament IDs, don't scrape")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip region/seasons where output file already exists")
    parser.add_argument("--debug", action="store_true",
                        help="Save raw HTML to data/_debug/khsaa_regionals/")
    args = parser.parse_args()

    # Override module-level constants based on gender
    global DATA_BASE, REGIONS, REGION_SEARCH_TERMS, TOURNAMENT_ID_CACHE, GENDER
    if args.gender == "girls":
        GENDER = "girls"
        DATA_BASE = Path("data/hs_ky_girls")
        REGIONS = list(range(1, 5))
        REGION_SEARCH_TERMS = {i: f"KHSAA Girls Region {i}" for i in range(1, 5)}
        TOURNAMENT_ID_CACHE = Path("data/_debug/khsaa_girls_regional_tournament_ids.json")

    regions = [args.region] if args.region else REGIONS
    seasons = [args.season] if args.season else SEASONS

    print("Building HTTP session...")
    session = build_session()
    session_id = establish_session(session, debug=args.debug)
    if not session_id:
        print("[FATAL] Could not establish TW session. Exiting.")
        return

    print(f"Session ID: {session_id}")

    # Load cached tournament IDs
    cache = load_tournament_id_cache()  # {str(region): {str(season): tournament_id}}

    # Discover tournament IDs for any regions/seasons not yet cached
    for region in regions:
        r_key = str(region)
        if r_key not in cache:
            cache[r_key] = {}

        missing_seasons = [s for s in seasons if str(s) not in cache[r_key]]
        if missing_seasons:
            print(f"\n--- Discovering Region {region} tournament IDs ---")
            new_ids = find_tournament_ids_for_region(
                session, session_id, region, missing_seasons, debug=args.debug
            )
            for s, tid in new_ids.items():
                cache[r_key][str(s)] = tid
            if new_ids:
                save_tournament_id_cache(cache)
            time.sleep(1.0)

    if args.discover_only:
        print("\nDiscover-only mode — stopping before placement scrape.")
        return

    # Scrape placements
    success_count = 0
    fail_count = 0
    skip_count = 0

    for region in regions:
        r_key = str(region)
        for season in seasons:
            s_key = str(season)
            out_path = DATA_BASE / str(season) / "regional_placements" / f"region_{region}.txt"

            if args.skip_existing and out_path.exists():
                skip_count += 1
                continue

            tournament_id = cache.get(r_key, {}).get(s_key)
            if not tournament_id:
                print(f"\n[SKIP] Region {region} / {season}: no tournament ID found")
                fail_count += 1
                continue

            print(f"\n--- Region {region} / Season {season} (tourney {tournament_id}) ---")
            ok = scrape_region_season(
                session, session_id, region, season, tournament_id, debug=args.debug
            )
            if ok:
                success_count += 1
            else:
                fail_count += 1

            time.sleep(0.5)

        # Re-establish session every 2 regions to avoid timeouts
        if region % 2 == 0 and region != regions[-1]:
            print(f"\nRefreshing session after region {region}...")
            new_sid = establish_session(session, debug=args.debug)
            if new_sid:
                session_id = new_sid

    print(f"\n{'='*50}")
    print(f"Done. ✓ {success_count} scraped, ✗ {fail_count} failed, ⏭ {skip_count} skipped")
    if fail_count > 0:
        print(f"\nTip: For failed entries, check {TOURNAMENT_ID_CACHE} and manually add any")
        print("missing tournament IDs, then re-run with --skip-existing to fill gaps.")


if __name__ == "__main__":
    main()
