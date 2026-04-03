#!/usr/bin/env python3
"""
Fetch bout sheet (TextCam.jsp) data for all TB matches in the 2026 NCAA championships.

Flow:
  1. Establish TW session for tournament 931299132
  2. Fetch BracketViewer.jsp per weight class to extract matchId → wrestler mapping
  3. Cross-reference with our 25 known TB matches
  4. Fetch TextCam.jsp for each match and save raw HTML + parsed data
  5. Write summary to data/2026/ncaa-tourney/tb_bouts/tb_bouts.json

Usage:
  python scripts/scraping/scrape_tb_bouts.py
  python scripts/scraping/scrape_tb_bouts.py --debug
"""

import argparse
import json
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
TOURNAMENT_ID = 931299132  # 2026 NCAA Championships, Rocket Arena, Cleveland OH

OUT_DIR = Path("data/2026/ncaa-tourney/tb_bouts")

WEIGHT_CLASSES = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]

# All 25 TB matches identified from results.txt
# (weight, round_fragment, winner, loser, result_str)
TB_MATCHES = [
    # 125
    (125, "Quarterfinal",   "Luke Lilledahl",    "Dean Peterson",    "TB-1 2-1"),
    (125, "Cons. Semi",     "Vincent Robinson",  "Troy Spratley",    "TB-1 3-2"),
    # 133
    (133, "Semifinal",      "Ben Davino",        "Marcus Blaze",     "TB-1 3-2"),
    (133, "7th Place",      "Jacob Van Dee",     "Lucas Byrd",       "TB-1 6-5"),
    # 141
    (141, "Cons. Round 1",  "Dylan Chappell",    "Braden Basile",    "TB-1 2-1"),
    # 149
    (149, "Cons. Round 2",  "Michael Gioffre",   "Ethan Stiles",     "TB-1 3-1"),
    # 157
    (157, "Semifinal",      "Landon Robideau",   "PJ Duke",          "TB-1 3-1"),
    # 165
    (165, "Champ. Round 1", "Matty Bianchi",     "Mac Church",       "TB-1 5-2"),
    (165, "Champ. Round 1", "Max Brignola",      "Tyler Lillard",    "TB-1 3-2"),
    (165, "Champ. Round 2", "Nicco Ruiz",        "Andrew Sparks",    "TB-1 2-1"),
    (165, "Cons. Round 1",  "Thomas Snipes",     "Andrew Barbosa",   "TB-1 3-1"),
    (165, "Cons. Round 2",  "LaDarion Lockett",  "LJ Araujo",        "TB-1 8-3"),
    # 174
    (174, "Prelim",         "Grant O`Dell",      "Luke Condon",      "TB-1 4-1"),
    (174, "Champ. Round 1", "Matty Singleton",   "Collin Carrigan",  "TB-1 2-1"),
    (174, "Quarterfinal",   "Patrick Kennedy",   "Carson Kharchla",  "TB-1 2-1"),
    (174, "Cons. Round 3",  "Colin Kelly",       "Alex Facundo",     "TB-3 2-2"),
    (174, "Cons. Round 4",  "Danny Wask",        "Carter Schubert",  "TB-1 2-1"),
    # 184
    (184, "Prelim",         "Sam Goin",          "Tyler Bienus",     "TB-1 2-1"),
    (184, "Champ. Round 1", "Jaden Bullock",     "Jared McGill",     "TB-1 6-5"),
    (184, "Cons. Round 2",  "Jaden Bullock",     "Nick Fox",         "TB-1 4-3"),
    (184, "Semifinal",      "Max McEnelly",      "Angelo Ferrari",   "TB-2 2-2"),
    # 197
    (197, "Cons. Round 4",  "Branson John",      "Colton Hawks",     "TB-1 5-1"),
    (197, "Semifinal",      "Cody Merrill",      "Stephen Little",   "TB-2 2-2"),
    # 285
    (285, "Champ. Round 1", "Dayton Pitzer",     "Spencer Lanosga",  "TB-1 3-2"),
    (285, "Champ. Round 2", "Hunter Catka",      "Devon Dawson",     "TB-1 2-1"),
]

# Weight classes that have at least one TB match
WEIGHTS_WITH_TB = sorted(set(m[0] for m in TB_MATCHES))

# ---------------------------------------------------------------------------
# Session helpers (mirrors scrape_ncaa_tournament.py)
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
    url = f"{BASE_URL}/Login.jsp"
    print(f"  GET {url}")
    resp = session.get(url, timeout=15)
    match = re.search(r'twMenuSessionId\s*=\s*["\']([a-zA-Z0-9]+)["\']', resp.text)
    if not match:
        match = re.search(r'twSessionId[="\s]+([a-zA-Z0-9]{8,})', resp.text)
    if not match:
        print("[FAIL] Could not find twSessionId in Login.jsp")
        if debug:
            print(resp.text[:2000])
        return None
    sid = match.group(1)
    print(f"  [OK] Initial session ID: {sid}")
    return sid


def enter_tournament(
    session: requests.Session, session_id: str, debug: bool = False
) -> str | None:
    url = (
        f"{BASE_URL}/predefinedtournaments/VerifyPassword.jsp"
        f"?TIM={get_tim()}&twSessionId={session_id}"
        f"&tournamentId={TOURNAMENT_ID}&userType=viewer&userName=&password="
    )
    print(f"  GET VerifyPassword.jsp ...")
    resp = session.get(url, timeout=15, allow_redirects=True)
    if "flowrestling.org" in resp.url:
        print(f"  [FAIL] Redirected to Flowrestling: {resp.url}")
        return None
    print(f"  [OK] VerifyPassword OK. Cookie: {bool(session.cookies.get('USER_SESSIONID'))}")

    main_url = (
        f"{BASE_URL}/predefinedtournaments/MainFrame.jsp"
        f"?newSession=false&TIM={get_tim()}"
        f"&pageName=%2Fpredefinedtournaments%2FViewWeightClass.jsp"
        f"&twSessionId={session_id}"
    )
    print(f"  GET MainFrame.jsp ...")
    main_resp = session.get(main_url, timeout=15)
    t_match = re.search(r'twMenuSessionId\s*=\s*["\']([a-zA-Z0-9]+)["\']', main_resp.text)
    if not t_match:
        t_match = re.search(
            r'ViewWeightClass\.jsp\?TIM=\d+&twSessionId=([a-zA-Z0-9]+)',
            main_resp.text,
        )
    if not t_match:
        print("  [FAIL] Could not extract tournament session ID from MainFrame.jsp")
        if debug:
            Path("data/_debug").mkdir(parents=True, exist_ok=True)
            Path("data/_debug/MainFrame_raw.html").write_text(main_resp.text)
        return None
    tsid = t_match.group(1)
    print(f"  [OK] Tournament session ID: {tsid}")
    return tsid


def get_weight_class_id_map(
    session: requests.Session, tsid: str, debug: bool = False
) -> dict[int, str]:
    url = (
        f"{BASE_URL}/predefinedtournaments/RoundResults.jsp"
        f"?TIM={get_tim()}&twSessionId={tsid}&tournamentId={TOURNAMENT_ID}"
    )
    resp = session.get(url, timeout=15)
    if debug:
        Path("data/_debug").mkdir(parents=True, exist_ok=True)
        Path("data/_debug/RoundResults_raw.html").write_text(resp.text)
    soup = BeautifulSoup(resp.text, "html.parser")
    sel = soup.find("select", {"id": "groupIdBox"}) or soup.find("select", {"name": "groupIdBox"})
    if not sel:
        print("  [WARN] groupIdBox select not found")
        return {}
    wc_map = {}
    for opt in sel.find_all("option"):
        text = opt.get_text(strip=True)
        val = opt.get("value", "").strip()
        if text.isdigit() and val:
            wc_map[int(text)] = val
    return wc_map

# ---------------------------------------------------------------------------
# Bracket scraping — extract TextCam matchIds
# ---------------------------------------------------------------------------

def fetch_bracket(
    session: requests.Session, tsid: str, group_id: str, debug: bool = False
) -> str:
    url = (
        f"{BASE_URL}/predefinedtournaments/BracketViewer.jsp"
        f"?TIM={get_tim()}&twSessionId={tsid}"
        f"&tournamentId={TOURNAMENT_ID}&groupId={group_id}"
    )
    if debug:
        print(f"  [DEBUG] GET {url}")
    resp = session.get(url, timeout=15)
    if debug:
        Path("data/_debug").mkdir(parents=True, exist_ok=True)
        Path(f"data/_debug/BracketViewer_{group_id}.html").write_text(resp.text)
    return resp.text


def extract_textcam_links(html: str) -> list[dict]:
    """
    Find all TextCam.jsp links in bracket HTML.
    Returns list of {match_id, context} where context is nearby text.
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_ids = set()

    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        if "TextCam.jsp" not in href and "textcam" not in href.lower():
            continue
        m = re.search(r'matchId=(\d+)', href, re.IGNORECASE)
        if not m:
            continue
        match_id = m.group(1)
        if match_id in seen_ids:
            continue
        seen_ids.add(match_id)

        # Gather context: text from this tag and nearby siblings/parent
        context_parts = [tag.get_text(" ", strip=True)]
        parent = tag.parent
        if parent:
            context_parts.append(parent.get_text(" ", strip=True))
        # Also check grandparent row
        gp = parent.parent if parent else None
        if gp:
            context_parts.append(gp.get_text(" ", strip=True))

        context = " | ".join(filter(None, context_parts))
        results.append({"match_id": match_id, "href": href, "context": context})

    # Also search raw HTML for matchId patterns not inside <a> tags
    # (some TW pages use onclick= or data attributes)
    for raw_match in re.finditer(r'matchId[=:][\'""]?(\d+)', html, re.IGNORECASE):
        mid = raw_match.group(1)
        if mid not in seen_ids:
            seen_ids.add(mid)
            # Get surrounding raw text (±200 chars)
            start = max(0, raw_match.start() - 200)
            end = min(len(html), raw_match.end() + 200)
            context = re.sub(r'<[^>]+>', ' ', html[start:end])
            context = re.sub(r'\s+', ' ', context).strip()
            results.append({"match_id": mid, "href": None, "context": context})

    return results


def names_from_tb(tb: tuple) -> tuple[list[str], list[str]]:
    """Return last-name tokens for winner and loser of a TB match entry."""
    _, _, winner, loser, _ = tb
    w_last = [winner.split()[-1].lower()]
    l_last = [loser.split()[-1].lower()]
    # Also add first name for disambiguation
    w_first = [winner.split()[0].lower()]
    l_first = [loser.split()[0].lower()]
    return w_last + w_first, l_last + l_first


def find_match_id_for_tb(tb: tuple, links: list[dict], debug: bool = False) -> str | None:
    """
    Try to match a TB bout to a bracket link by checking if both wrestlers'
    last names appear in the context text.
    """
    _, round_frag, winner, loser, _ = tb
    w_last = winner.split()[-1].lower()
    l_last = loser.split()[-1].lower()
    w_first = winner.split()[0].lower()
    l_first = loser.split()[0].lower()

    candidates = []
    for link in links:
        ctx = link["context"].lower()
        # Both last names must appear
        if w_last in ctx and l_last in ctx:
            # Score: also check first names for confidence
            score = 2
            if w_first in ctx:
                score += 1
            if l_first in ctx:
                score += 1
            candidates.append((score, link["match_id"], link))

    if not candidates:
        if debug:
            print(f"    [DEBUG] No match found for {winner} vs {loser}")
        return None

    # Take highest-scoring candidate
    candidates.sort(key=lambda x: -x[0])
    best_score, best_id, best_link = candidates[0]
    if debug and len(candidates) > 1:
        print(f"    [DEBUG] Multiple candidates for {winner} vs {loser}: {[c[1] for c in candidates]}, using {best_id} (score={best_score})")
    return best_id

# ---------------------------------------------------------------------------
# TextCam fetching and parsing
# ---------------------------------------------------------------------------

def fetch_textcam(
    session: requests.Session, tsid: str, match_id: str, debug: bool = False
) -> str:
    url = (
        f"{BASE_URL}/TextCam.jsp"
        f"?TIM={get_tim()}&twSessionId={tsid}"
        f"&eventType=predefined&eventId={TOURNAMENT_ID}&matchId={match_id}"
    )
    if debug:
        print(f"    [DEBUG] GET {url}")
    resp = session.get(url, timeout=15)
    return resp.text


def parse_textcam(html: str) -> dict:
    """
    Parse a TextCam bout sheet into structured data.
    Returns a dict with whatever we can extract.
    """
    soup = BeautifulSoup(html, "html.parser")
    result = {"raw_text": "", "tables": [], "rows": []}

    # Get all visible text
    result["raw_text"] = soup.get_text(separator="\n", strip=True)

    # Extract all table data
    for table in soup.find_all("table"):
        table_rows = []
        for row in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
            if any(cells):
                table_rows.append(cells)
        if table_rows:
            result["tables"].append(table_rows)

    # Flatten all rows for easy inspection
    for table in result["tables"]:
        for row in table:
            result["rows"].append(row)

    return result

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scrape TB bout sheets from 2026 NCAA")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("\n=== 2026 NCAA TB Bout Sheet Scraper ===\n")

    # Step 1: Establish session
    print("1. Establishing session...")
    session = build_session()
    session_id = establish_session(session, debug=args.debug)
    if not session_id:
        sys.exit(1)

    print("\n2. Entering tournament...")
    tsid = enter_tournament(session, session_id, debug=args.debug)
    if not tsid:
        sys.exit(1)

    print("\n3. Getting weight class ID map...")
    wc_map = get_weight_class_id_map(session, tsid, debug=args.debug)
    if not wc_map:
        sys.exit(1)
    print(f"   [OK] {len(wc_map)} weight classes: {list(wc_map.keys())}")

    # Step 2: For each weight with TB matches, fetch bracket and extract matchIds
    print(f"\n4. Scraping brackets for TB-match weights: {WEIGHTS_WITH_TB}")
    weight_links: dict[int, list[dict]] = {}

    for weight in WEIGHTS_WITH_TB:
        group_id = wc_map.get(weight)
        if not group_id:
            print(f"   [SKIP] {weight} not in weight class map")
            continue
        print(f"\n   Bracket {weight} lbs (group_id={group_id})...")
        html = fetch_bracket(session, tsid, group_id, debug=args.debug)
        links = extract_textcam_links(html)
        weight_links[weight] = links
        print(f"   Found {len(links)} TextCam links")
        if args.debug:
            for lnk in links[:5]:
                print(f"     matchId={lnk['match_id']}  ctx={lnk['context'][:80]}")
        time.sleep(0.5)

    # Step 3: Match TB bouts to matchIds
    print("\n5. Matching TB bouts to bracket links...")
    matched = []
    unmatched = []

    for tb in TB_MATCHES:
        weight, round_frag, winner, loser, result = tb
        links = weight_links.get(weight, [])
        match_id = find_match_id_for_tb(tb, links, debug=args.debug)
        if match_id:
            matched.append({
                "weight": weight,
                "round": round_frag,
                "winner": winner,
                "loser": loser,
                "result": result,
                "match_id": match_id,
            })
            print(f"   [{weight}] {winner} vs {loser} ({round_frag}) → matchId={match_id}")
        else:
            unmatched.append(tb)
            print(f"   [{weight}] !! NO MATCH: {winner} vs {loser} ({round_frag})")

    print(f"\n   Matched: {len(matched)}/{len(TB_MATCHES)}")

    if not matched:
        print("\n[ERROR] No matches found — bracket HTML may not contain TextCam links.")
        print("        Try running with --debug and inspect data/_debug/BracketViewer_*.html")
        sys.exit(1)

    # Step 4: Fetch TextCam for each matched bout
    print(f"\n6. Fetching {len(matched)} bout sheets from TextCam.jsp...")
    all_bouts = []

    for bout in matched:
        match_id = bout["match_id"]
        label = f"{bout['weight']}_{bout['winner'].split()[-1]}_{bout['loser'].split()[-1]}"
        label = re.sub(r"[^a-zA-Z0-9_]", "", label)

        print(f"   Fetching matchId={match_id} ({bout['weight']} lbs: {bout['winner']} vs {bout['loser']})...")
        html = fetch_textcam(session, tsid, match_id, debug=args.debug)

        # Save raw HTML
        raw_path = OUT_DIR / f"{label}_{match_id}.html"
        raw_path.write_text(html)

        # Parse
        parsed = parse_textcam(html)
        bout_record = {**bout, "bout_sheet": parsed}
        all_bouts.append(bout_record)

        time.sleep(0.4)

    # Step 5: Save summary JSON
    # Don't include raw_text in the JSON summary (too verbose) — it's in the HTML files
    summary = []
    for b in all_bouts:
        entry = {k: v for k, v in b.items() if k != "bout_sheet"}
        entry["rows"] = b["bout_sheet"]["rows"]
        entry["table_count"] = len(b["bout_sheet"]["tables"])
        summary.append(entry)

    summary_path = OUT_DIR / "tb_bouts.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"\n[OK] Summary saved: {summary_path}")
    print(f"[OK] Raw HTML files saved to: {OUT_DIR}/")

    if unmatched:
        print(f"\n[WARN] {len(unmatched)} bouts could not be matched to bracket links:")
        for tb in unmatched:
            print(f"  {tb[0]} lbs — {tb[2]} vs {tb[3]} ({tb[1]})")
        print("  → Try --debug to inspect the bracket HTML for those weight classes.")


if __name__ == "__main__":
    main()
