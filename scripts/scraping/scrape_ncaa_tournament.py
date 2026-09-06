#!/usr/bin/env python3
"""
Scrape NCAA Division I wrestling tournament results from TrackWrestling.

Establishes a session via Login.jsp, enters each tournament using the
classic viewer (viewer_ngw), then scrapes seeds and bracket results
for each weight class.

Output mirrors the 2025 hand-collected format:
  data/{year}/ncaa-tourney/seeds/{weight}.txt   — seedings list
  data/{year}/ncaa-tourney/results.txt           — full bracket results

Usage:
  python scripts/scraping/scrape_ncaa_tournament.py --year 2024
  python scripts/scraping/scrape_ncaa_tournament.py --year 2010 --debug
  python scripts/scraping/scrape_ncaa_tournament.py --all
"""

import argparse
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://www.trackwrestling.com"

WEIGHT_CLASSES = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]

# Tournament IDs discovered from trackwrestling Events Classic search.
# 2020 was cancelled but the entry still exists.
TOURNAMENT_IDS = {
    2026: 931299132,  # Rocket Arena, Cleveland OH, 03/19–03/21/2026
    2025: 855048132,
    2024: 771443132,
    2023: 683912132,
    2022: 632767132,
    2021: 602346132,
    2020: 503102132,  # CANCELLED — skip by default
    2019: 208644132,
    2018: 40917132,
    2017: 251028009,
    2016: 218273009,
    2015: 169694009,
    2014: 129877009,
    2013: 80861009,
    2012: 38110009,
    2011: 425838132,
    2010: 425839132,
    2009: 425840132,
    2008: 425841132,
    2007: 425842132,
    2006: 425843132,
    2005: 425844132,
    2004: 425845132,
    2003: 425846132,
    2002: 425847132,
    2001: 425848132,
    2000: 425849132,
}

DATA_DIR = Path("data")

# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def get_tim() -> int:
    return int(time.time() * 1000)


def build_session() -> requests.Session:
    # NOTE: trackwrestling.com's WAF now rejects requests with a spoofed
    # browser User-Agent (Chrome, etc.) with a 406 — likely a TLS/JA3
    # fingerprint mismatch check, since curl's own default UA and requests'
    # default UA both pass fine. Do not set a browser-looking User-Agent here.
    session = requests.Session()
    session.headers.update({
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })
    return session


def establish_session(session: requests.Session, debug: bool = False) -> str | None:
    """
    Visit Login.jsp to get an initial twSessionId.
    Returns the session ID string, or None on failure.
    """
    url = f"{BASE_URL}/Login.jsp"
    print(f"  GET {url}")
    resp = session.get(url, timeout=15)

    match = re.search(r'twMenuSessionId\s*=\s*["\']([a-zA-Z0-9]+)["\']', resp.text)
    if not match:
        match = re.search(r'twSessionId[="\s]+([a-zA-Z0-9]{8,})', resp.text)

    if not match:
        print("[FAIL] Could not find twSessionId in Login.jsp response.")
        if debug:
            print(resp.text[:2000])
        return None

    session_id = match.group(1)
    print(f"  [OK] Initial session ID: {session_id}")
    return session_id


def enter_tournament(
    session: requests.Session,
    session_id: str,
    tournament_id: int,
    debug: bool = False,
) -> str | None:
    """
    Enter the tournament via VerifyPassword.jsp (userType=viewer = Viewer Classic),
    then load MainFrame.jsp to obtain the tournament-scoped session ID that is
    used by the inner PageFrame iframe.

    Returns the tournament session ID string, or None on failure.
    """
    # Step 1: VerifyPassword — sets USER_SESSIONID cookie on the requests session
    url = (
        f"{BASE_URL}/predefinedtournaments/VerifyPassword.jsp"
        f"?TIM={get_tim()}&twSessionId={session_id}"
        f"&tournamentId={tournament_id}&userType=viewer"
        f"&userName=&password="
    )
    print(f"  GET VerifyPassword.jsp ...")
    resp = session.get(url, timeout=15, allow_redirects=True)

    if "flowrestling.org" in resp.url:
        print(f"  [FAIL] Redirected to Flowrestling: {resp.url}")
        return None

    print(f"  [OK] VerifyPassword stayed on TW. Cookie set: {bool(session.cookies.get('USER_SESSIONID'))}")

    # Step 2: Load MainFrame.jsp — it contains the tournament session ID in JS
    tim = get_tim()
    main_url = (
        f"{BASE_URL}/predefinedtournaments/MainFrame.jsp"
        f"?newSession=false&TIM={tim}"
        f"&pageName=%2Fpredefinedtournaments%2FViewWeightClass.jsp"
        f"&twSessionId={session_id}"
    )
    print(f"  GET MainFrame.jsp ...")
    main_resp = session.get(main_url, timeout=15)

    # Extract the tournament-scoped session ID from the JS in MainFrame
    # It appears as: twMenuSessionId = "donirpxlfi"  and in the iframe src
    t_match = re.search(r'twMenuSessionId\s*=\s*["\']([a-zA-Z0-9]+)["\']', main_resp.text)
    if not t_match:
        # Fallback: look for it in the PageFrame location assignment
        t_match = re.search(
            r'ViewWeightClass\.jsp\?TIM=\d+&twSessionId=([a-zA-Z0-9]+)',
            main_resp.text,
        )

    if not t_match:
        print("  [FAIL] Could not extract tournament session ID from MainFrame.jsp")
        if debug:
            Path("data/_debug/MainFrame_raw.html").parent.mkdir(parents=True, exist_ok=True)
            Path("data/_debug/MainFrame_raw.html").write_text(main_resp.text)
            print("  Saved MainFrame HTML to data/_debug/MainFrame_raw.html")
        return None

    tournament_session_id = t_match.group(1)
    print(f"  [OK] Tournament session ID: {tournament_session_id}")
    return tournament_session_id


def fetch_inner_page(
    session: requests.Session,
    tournament_session_id: str,
    tournament_id: int,
    page_jsp: str,
    extra_params: dict | None = None,
) -> requests.Response:
    """
    Fetch an inner JSP page directly using the tournament-scoped session ID.
    This bypasses the MainFrame.jsp wrapper and fetches the raw server-rendered content.
    """
    params = f"TIM={get_tim()}&twSessionId={tournament_session_id}&tournamentId={tournament_id}"
    if extra_params:
        for k, v in extra_params.items():
            params += f"&{k}={v}"
    url = f"{BASE_URL}/predefinedtournaments/{page_jsp}?{params}"
    return session.get(url, timeout=15)

# ---------------------------------------------------------------------------
# Weight-class ID mapping and results fetching
# ---------------------------------------------------------------------------

def get_weight_class_id_map(
    session: requests.Session,
    tournament_session_id: str,
    tournament_id: int,
    debug: bool = False,
) -> dict[int, str]:
    """
    Fetch RoundResults.jsp once to read the groupIdBox select element.
    Returns {weight_int: internal_group_id_string}, e.g. {125: '2133348135', ...}
    """
    resp = fetch_inner_page(session, tournament_session_id, tournament_id, "RoundResults.jsp")

    if debug:
        raw_path = DATA_DIR / "_debug"
        raw_path.mkdir(parents=True, exist_ok=True)
        (raw_path / "RoundResults_raw.html").write_text(resp.text)

    soup = BeautifulSoup(resp.text, "html.parser")
    sel = soup.find("select", {"id": "groupIdBox"}) or soup.find("select", {"name": "groupIdBox"})
    if not sel:
        print("  [WARN] groupIdBox select not found — cannot map weight classes.")
        return {}

    wc_map = {}
    for opt in sel.find_all("option"):
        text = opt.get_text(strip=True)
        val = opt.get("value", "").strip()
        if text.isdigit() and val:
            wc_map[int(text)] = val

    if debug:
        print(f"  [DEBUG] Weight class ID map: {wc_map}")
    return wc_map


def fetch_results_for_weight(
    session: requests.Session,
    tournament_session_id: str,
    tournament_id: int,
    group_id: str,
    debug: bool = False,
) -> str:
    """
    Fetch bracket results for a specific weight class using its internal group ID.
    Must be a POST — the form uses method=post with displayResult=Y in the action URL
    and the form fields in the request body.
    """
    action_url = (
        f"{BASE_URL}/predefinedtournaments/RoundResults.jsp"
        f"?TIM={get_tim()}&twSessionId={tournament_session_id}"
        f"&tournamentId={tournament_id}"
        f"&displayResult=Y&roundId=&groupId={group_id}"
    )
    post_data = {
        "patternBox": "1",
        "displayFormatBox": "2",   # Weight Class display format
        "roundIdBox": "",
        "groupIdBox": group_id,
        "includeByesBox": "Y",
        "fontSizeBox": "10",
    }
    if debug:
        print(f"  [DEBUG] POST {action_url}")
    resp = session.post(action_url, data=post_data, timeout=15)
    if debug:
        raw_path = DATA_DIR / "_debug"
        raw_path.mkdir(parents=True, exist_ok=True)
        (raw_path / f"RoundResults_{group_id}.html").write_text(resp.text)
    return resp.text


def fetch_seeds_for_weight(
    session: requests.Session,
    tournament_session_id: str,
    tournament_id: int,
    group_id: str,
    debug: bool = False,
) -> str:
    """
    Fetch the seedings page for a specific weight class.
    ViewWeightClass.jsp only renders inside the PageFrame iframe context,
    so we add the Referer header to simulate that and pass the groupId.
    """
    referer = (
        f"{BASE_URL}/predefinedtournaments/MainFrame.jsp"
        f"?newSession=false&TIM={get_tim()}"
        f"&pageName=%2Fpredefinedtournaments%2FViewWeightClass.jsp"
        f"&twSessionId={tournament_session_id}"
    )
    url = (
        f"{BASE_URL}/predefinedtournaments/ViewWeightClass.jsp"
        f"?TIM={get_tim()}&twSessionId={tournament_session_id}"
        f"&tournamentId={tournament_id}&groupId={group_id}"
    )
    if debug:
        print(f"  [DEBUG] GET {url}")
    resp = session.get(url, timeout=15, headers={"Referer": referer})
    if debug:
        raw_path = DATA_DIR / "_debug"
        raw_path.mkdir(parents=True, exist_ok=True)
        (raw_path / f"ViewWeightClass_{group_id}.html").write_text(resp.text)
    return resp.text

# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_seeds_page(html: str, weight: int, debug: bool = False) -> str:
    """
    Parse ViewWeightClass.jsp HTML into a seeds .txt file matching 2025 format:
      Seed\tName\tTeam\tGrade\tRecord\tScoring
    Returns the file content as a string.
    """
    soup = BeautifulSoup(html, "html.parser")
    lines = ["Seed\tName\tTeam\tGrade\tRecord\tScoring"]

    # Try to find a table with wrestler seeding data
    tables = soup.find_all("table")
    if debug:
        print(f"  [DEBUG] Found {len(tables)} tables in seeds page")

    best_table = None
    best_score = 0
    for table in tables:
        rows = table.find_all("tr")
        text = table.get_text()
        # Score this table by how much it looks like a seedings table
        score = 0
        if re.search(r'\b\d+\.\b', text):    # seed numbers like "1."
            score += 3
        if re.search(r'\d+-\d+', text):        # win-loss records
            score += 2
        if len(rows) >= 5:
            score += 1
        if score > best_score:
            best_score = score
            best_table = table

    if best_table is None:
        print(f"  [WARN] Could not identify seedings table for {weight}. Saving raw text.")
        if debug:
            raw_path = DATA_DIR / "_debug"
            raw_path.mkdir(parents=True, exist_ok=True)
            (raw_path / f"seeds_{weight}_raw.html").write_text(html)
        return "\n".join(lines)

    for row in best_table.find_all("tr"):
        cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
        if not cells:
            continue
        # Skip header rows
        if cells[0].lower() in ("seed", "#", ""):
            continue
        # Expect at least: seed, name, team
        if len(cells) < 3:
            continue
        # Extract seed (may have trailing dot: "1.")
        seed_raw = cells[0].rstrip(".")
        if not seed_raw.isdigit():
            continue
        seed = seed_raw
        name = cells[1] if len(cells) > 1 else ""
        team = cells[2] if len(cells) > 2 else ""
        grade = cells[3] if len(cells) > 3 else ""
        record = cells[4] if len(cells) > 4 else ""
        scoring = cells[5] if len(cells) > 5 else "Yes"
        lines.append(f"{seed}.\t{name}\t{team}\t{grade}\t{record}\t{scoring}")

    return "\n".join(lines)


def parse_results_page(html: str, weight: int, debug: bool = False) -> str:
    """
    Parse RoundResults.jsp POST response into the results text format matching 2025.
    The page renders match data as visible text in the body — extract non-empty lines
    that are round headers or match result lines, skipping boilerplate.
    Returns the text block for this weight class (without the leading weight number).
    """
    soup = BeautifulSoup(html, "html.parser")
    body = soup.find("body")
    if not body:
        return ""

    raw_text = body.get_text(separator="\n")

    round_keywords = [
        "Championships", "1st Place", "3rd Place", "5th Place", "7th Place",
        "Semifinal", "Quarterfinal", "Cons.", "Champ.", "Prelim",
        "Round", "Place Match", "Pig Tail",
    ]
    match_keywords = ["won by", "won in", "won with", "default", "forfeit", "medical", "disqualif"]
    # Lines to always skip
    skip_exact = {"LOADING...", str(weight)}

    result_lines = []
    for line in raw_text.splitlines():
        line = line.strip()
        if not line or line in skip_exact:
            continue
        is_round = any(kw in line for kw in round_keywords)
        is_match = any(kw in line.lower() for kw in match_keywords)
        if is_round or is_match:
            result_lines.append(line)

    if debug and not result_lines:
        print(f"  [DEBUG] No result lines found for weight {weight}.")

    return "\n".join(result_lines)

# ---------------------------------------------------------------------------
# Main scrape logic
# ---------------------------------------------------------------------------

def scrape_year(year: int, debug: bool = False, skip_cancelled: bool = True) -> bool:
    """
    Scrape all weight classes for a given tournament year.
    Returns True on success.
    """
    if year not in TOURNAMENT_IDS:
        print(f"[ERROR] No tournament ID known for {year}.")
        return False

    tournament_id = TOURNAMENT_IDS[year]

    if skip_cancelled and year == 2020:
        print(f"[SKIP] {year} NCAA tournament was cancelled.")
        return True

    print(f"\n{'='*60}")
    print(f"Scraping {year} NCAA Division I Championships (ID: {tournament_id})")
    print(f"{'='*60}")

    # Output directories
    out_dir = DATA_DIR / str(year) / "ncaa-tourney"
    seeds_dir = out_dir / "seeds"
    out_dir.mkdir(parents=True, exist_ok=True)
    seeds_dir.mkdir(parents=True, exist_ok=True)

    # Establish session
    print("\n1. Establishing session...")
    session = build_session()
    session_id = establish_session(session, debug=debug)
    if not session_id:
        return False

    # Enter tournament — returns tournament-scoped session ID
    print(f"\n2. Entering tournament {tournament_id}...")
    tournament_session_id = enter_tournament(session, session_id, tournament_id, debug=debug)
    if not tournament_session_id:
        print("[FAIL] Could not establish tournament session. Skipping.")
        return False

    # Build weight-class → internal group ID mapping (one request)
    print(f"\n3. Building weight class ID map...")
    wc_map = get_weight_class_id_map(session, tournament_session_id, tournament_id, debug=debug)
    if not wc_map:
        print("[FAIL] Could not build weight class map. Aborting.")
        return False
    print(f"   [OK] Found {len(wc_map)} weight classes: {list(wc_map.keys())}")

    # Scrape each weight class
    all_results_blocks = []

    for weight in WEIGHT_CLASSES:
        group_id = wc_map.get(weight)
        if not group_id:
            print(f"\n   [SKIP] Weight {weight} not found in tournament.")
            continue

        print(f"\n4. Weight class: {weight} (group_id={group_id})")

        # --- Seeds ---
        print(f"   Fetching seeds...")
        seeds_html = fetch_seeds_for_weight(
            session, tournament_session_id, tournament_id, group_id, debug=debug,
        )
        seeds_text = parse_seeds_page(seeds_html, weight, debug=debug)
        seeds_path = seeds_dir / f"{weight}.txt"
        seeds_path.write_text(seeds_text)
        rows = seeds_text.count("\n")
        print(f"   Seeds saved: {seeds_path} ({rows} entries)")

        time.sleep(0.5)

        # --- Results ---
        print(f"   Fetching results...")
        results_html = fetch_results_for_weight(
            session, tournament_session_id, tournament_id, group_id, debug=debug,
        )
        results_text = parse_results_page(results_html, weight, debug=debug)
        if results_text:
            all_results_blocks.append(f"{weight}\n{results_text}")
            print(f"   Results parsed ({results_text.count(chr(10))+1} lines)")
        else:
            print(f"   [WARN] No match lines extracted for {weight}")

        time.sleep(0.5)

    # Write combined results file
    if all_results_blocks:
        results_path = out_dir / "results.txt"
        results_path.write_text("\n".join(all_results_blocks))
        print(f"\n[OK] Combined results saved: {results_path}")
    else:
        print(f"\n[WARN] No results data collected for {year}.")

    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scrape NCAA D1 wrestling tournament data from TrackWrestling")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--year", type=int, help="Year to scrape (e.g. 2024)")
    group.add_argument("--all", action="store_true", help="Scrape all years from 2010-2024")
    parser.add_argument("--debug", action="store_true", help="Enable debug output and save raw HTML")
    parser.add_argument("--include-cancelled", action="store_true", help="Include 2020 (cancelled tournament)")
    parser.add_argument(
        "--years",
        type=str,
        help="Comma-separated list of years to scrape (e.g. 2010,2011,2012)",
    )
    args = parser.parse_args()

    if args.year:
        years = [args.year]
    elif args.years:
        years = [int(y.strip()) for y in args.years.split(",")]
    else:
        # --all: 2010 through 2024
        years = [y for y in range(2010, 2025) if y != 2020 or args.include_cancelled]

    success_count = 0
    for year in years:
        ok = scrape_year(
            year,
            debug=args.debug,
            skip_cancelled=not args.include_cancelled,
        )
        if ok:
            success_count += 1
        time.sleep(1)  # pause between tournaments

    print(f"\nDone: {success_count}/{len(years)} years scraped successfully.")


if __name__ == "__main__":
    main()
