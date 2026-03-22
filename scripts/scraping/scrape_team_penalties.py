#!/usr/bin/env python3
"""
Scrape team USC (unsportsmanlike conduct) penalties from TrackWrestling.

Fetches TournamentTeams.jsp to get the team→teamId map, then hits
TeamPointsDetail.jsp for each team to sum any USC penalty rows.

Returns {team_name: total_penalty_pts} — only teams with penalties included.
"""

import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

BASE_URL = "https://www.trackwrestling.com"

TOURNAMENT_IDS = {
    2026: 931299132,
    2025: 855048132,
    2024: 771443132,
    2023: 683912132,
    2022: 632767132,
    2021: 602346132,
    2019: 208644132,
}


def get_tim() -> int:
    return int(time.time() * 1000)


def _build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    return session


def _get_session_id(session: requests.Session) -> str | None:
    resp = session.get(f"{BASE_URL}/Login.jsp", timeout=15)
    m = re.search(r'twMenuSessionId\s*=\s*["\']([a-zA-Z0-9]+)["\']', resp.text)
    if not m:
        m = re.search(r'twSessionId[="\s]+([a-zA-Z0-9]{8,})', resp.text)
    return m.group(1) if m else None


def _enter_tournament(session: requests.Session, sid: str, tournament_id: int) -> bool:
    resp = session.get(
        f"{BASE_URL}/predefinedtournaments/VerifyPassword.jsp"
        f"?TIM={get_tim()}&twSessionId={sid}"
        f"&tournamentId={tournament_id}&userType=viewer&userName=&password=",
        timeout=15, allow_redirects=True,
    )
    return "flowrestling.org" not in resp.url


def _fetch(session: requests.Session, sid: str, page: str, extra: dict = None) -> requests.Response:
    params = f"TIM={get_tim()}&twSessionId={sid}"
    if extra:
        params += "&" + "&".join(f"{k}={v}" for k, v in extra.items())
    return session.get(f"{BASE_URL}/predefinedtournaments/{page}?{params}", timeout=15)


def _get_team_id_map(session: requests.Session, sid: str, tournament_id: int) -> dict[str, int]:
    """Return {team_name: teamId} from TournamentTeams.jsp."""
    resp = _fetch(session, sid, "TournamentTeams.jsp", {"tournamentId": tournament_id})
    soup = BeautifulSoup(resp.text, "html.parser")
    teams = {}
    for a in soup.find_all("a"):
        href = a.get("href", "")
        m = re.search(r"viewTeamMembers\((\d+)\)", href)
        if not m:
            continue
        team_id = int(m.group(1))
        # Strip state abbreviation: "Penn State, PA" → "Penn State"
        raw_name = a.get_text(strip=True)
        name = raw_name.rsplit(",", 1)[0].strip()
        if name:
            teams[name] = team_id
    return teams


def _get_team_penalties(session: requests.Session, sid: str, team_id: int) -> float:
    """Fetch TeamPointsDetail for one team and sum all USC penalty rows."""
    resp = _fetch(session, sid, "TeamPointsDetail.jsp", {"teamId": team_id})
    soup = BeautifulSoup(resp.text, "html.parser")
    total_penalty = 0.0
    for tr in soup.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
        # USC rows have 2 cells: description starting with "USC" and a negative value
        if len(cells) == 2 and cells[0].upper().startswith("USC"):
            try:
                total_penalty += float(cells[1])
            except ValueError:
                pass
    return total_penalty


def scrape_penalties(year: int, debug: bool = False) -> dict[str, float]:
    """
    Scrape all USC penalties for the given tournament year.
    Returns {team_name: total_penalty} — only teams with non-zero penalties.
    """
    tournament_id = TOURNAMENT_IDS.get(year)
    if not tournament_id:
        print(f"  [penalties] No tournament ID for {year}", file=sys.stderr)
        return {}

    session = _build_session()

    sid = _get_session_id(session)
    if not sid:
        print("  [penalties] Could not get TW session ID", file=sys.stderr)
        return {}

    if not _enter_tournament(session, sid, tournament_id):
        print("  [penalties] Could not enter tournament", file=sys.stderr)
        return {}

    team_id_map = _get_team_id_map(session, sid, tournament_id)
    if not team_id_map:
        print("  [penalties] Could not fetch team list", file=sys.stderr)
        return {}

    if debug:
        print(f"  [penalties] Found {len(team_id_map)} teams")

    penalties = {}
    for team_name, team_id in team_id_map.items():
        penalty = _get_team_penalties(session, sid, team_id)
        if penalty != 0.0:
            penalties[team_name] = round(penalty, 1)
            print(f"  [penalties] {team_name}: {penalty:+.1f}")
        time.sleep(0.2)  # be polite

    return penalties


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    result = scrape_penalties(args.year, debug=args.debug)
    print(f"\nPenalties for {args.year}: {result}")
