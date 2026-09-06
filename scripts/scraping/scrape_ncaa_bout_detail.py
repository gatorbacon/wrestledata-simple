#!/usr/bin/env python3
"""
Scrape period-by-period, timestamped match detail for NCAA Division I
Championship bouts from TrackWrestling's "classic" bracket viewer.

This is a separate, more granular data source than scrape_ncaa_tournament.py
(which only captures round + final result). It gives per-period scoring
events with clock timestamps (e.g. "Escape (1:53)", "Takedown 3 (0:47)"),
period choices (Defer/Bottom/Top/Neutral), and riding time.

TrackWrestling's play-by-play page has no round label of its own, so after
each weight class is scraped this script automatically calls
reconcile_bout_detail.reconcile_weight() to tag every bout with round/bracket
by joining against the existing data/{year}/ncaa-tourney/parsed/matches.json
(by weight + wrestler names). That join requires matches.json to already
exist for the year (i.e. scrape_ncaa_tournament.py + parse_ncaa_results.py
have already been run) — if it's missing, reconciliation just warns and
bouts are saved with round=None, so re-run reconcile_bout_detail.py manually
once matches.json exists.

Known gap: pigtail matches (round PIG/C_PIG) have no play-by-play page on
TrackWrestling at all — confirmed by checking the bracket UI directly, the
link simply isn't active for them. They will always be absent from this
output; reconcile_bout_detail.py reports them, it doesn't try to fetch them.

Discovered request chain (see scrape_ncaa_tournament.py for session setup):
  1. PBPBoutCheck.jsp?groupId={weight_group_id}&boutNumber={n}&prelimInd=N
     resolves a per-weight-class sequential bout number to a global matchId.
     boutNumber restarts at 1 for each weight class. An out-of-range
     boutNumber returns a fixed short placeholder page with no matchId,
     which is how we detect the end of a weight class's bout list.
  2. TextCam.jsp?eventId={tournament_id}&matchId={matchId} returns the
     actual play-by-play page (period-by-period HTML tables).

IMPORTANT: the two wrestler columns in the play-by-play tables are NOT
consistently ordered winner-then-loser or loser-then-winner — the position
(left/right, green/red) reflects a match-display assignment, not who won.
The winner must be resolved by matching the "X defeated Y" headline against
each column's wrestler name.

Output:
  data/{year}/ncaa-tourney/bout_detail/{weight}.json — list of parsed bouts
  for that weight class, each tagged with bout_number and match_id.

Usage:
  python scripts/scraping/scrape_ncaa_bout_detail.py --year 2026
  python scripts/scraping/scrape_ncaa_bout_detail.py --year 2026 --weights 125,133
  python scripts/scraping/scrape_ncaa_bout_detail.py --year 2026 --debug
  python scripts/scraping/scrape_ncaa_bout_detail.py --year 2026 --delay 2.0
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from bs4 import BeautifulSoup

from scripts.ncaa.reconcile_bout_detail import reconcile_weight
from scripts.scraping.scrape_ncaa_tournament import (
    BASE_URL,
    TOURNAMENT_IDS,
    WEIGHT_CLASSES,
    build_session,
    enter_tournament,
    establish_session,
    get_tim,
    get_weight_class_id_map,
)

DATA_DIR = PROJECT_ROOT / "data"

MAX_BOUTS_PER_WEIGHT = 100  # safety cap; NCAA D1 weight classes top out well under this

# ---------------------------------------------------------------------------
# Bout number -> matchId resolution
# ---------------------------------------------------------------------------

class RateLimitedError(Exception):
    """
    Raised when trackwrestling.com returns a non-200 status (observed: 406,
    empty body) instead of real content. This happens when the site's WAF
    rate-limits our IP. Critically, a blocked response and a genuine "no
    more matches at this boutNumber" response can look identical if you only
    check the response body (both lack "matchId=" / a parseable table) — so
    status code must be checked explicitly, or a mid-run block gets silently
    misread as "this weight class is done" and produces a truncated file
    that looks complete. Raising here instead lets the caller stop the whole
    run immediately rather than burning requests against a wall across every
    remaining weight class.
    """
    pass


def resolve_match_id(session, tournament_session_id, group_id, bout_number, prelim_ind="N"):
    """
    Calls PBPBoutCheck.jsp to resolve a (group_id, bout_number) pair to a
    global matchId. Returns the matchId string, or None if bout_number is
    genuinely out of range for this weight class.
    """
    url = (
        f"{BASE_URL}/predefinedtournaments/PBPBoutCheck.jsp"
        f"?TIM={get_tim()}&twSessionId={tournament_session_id}"
        f"&groupId={group_id}&boutNumber={bout_number}&prelimInd={prelim_ind}"
    )
    resp = session.get(url, timeout=15)
    if resp.status_code != 200:
        raise RateLimitedError(f"PBPBoutCheck.jsp returned HTTP {resp.status_code}")
    match = re.search(r"matchId=(\d+)", resp.text)
    return match.group(1) if match else None


def fetch_bout_html(session, tournament_session_id, tournament_id, match_id):
    url = (
        f"{BASE_URL}/TextCam.jsp"
        f"?TIM={get_tim()}&twSessionId={tournament_session_id}"
        f"&eventType=predefined&eventId={tournament_id}&matchId={match_id}"
    )
    resp = session.get(url, timeout=15)
    if resp.status_code != 200:
        raise RateLimitedError(f"TextCam.jsp returned HTTP {resp.status_code}")
    return resp.text

# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _parse_wrestler_cell(td):
    parts = list(td.stripped_strings)
    if len(parts) < 3:
        return None
    return {"name": parts[0], "team": parts[1], "score": int(parts[2])}


def parse_bout_html(html: str, debug: bool = False) -> dict | None:
    """
    Parses a TextCam.jsp response into structured period-by-period data.
    Returns None if the page doesn't contain the expected summary table
    (e.g. an unexpected/error response).
    """
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if len(tables) < 1:
        if debug:
            print(f"    [WARN] No tables found at all")
        return None
    # A second (period-breakdown) table is only present when at least one
    # scoring event occurred. Matches decided 0-0 (forfeit/injury default/etc
    # before any scoring) legitimately have just the summary table — treat
    # that as a valid zero-event match, not a parse failure.

    summary_table = tables[0]
    rows = summary_table.find_all("tr")
    if len(rows) < 2:
        return None

    headline = rows[0].get_text(strip=True)
    m = re.match(r"^(.*?) defeated (.*)$", headline)
    winner_full = m.group(1) if m else None

    cells = rows[1].find_all("td")
    if len(cells) < 2:
        return None
    left = _parse_wrestler_cell(cells[0])
    right = _parse_wrestler_cell(cells[1])
    if left is None or right is None:
        return None

    # The left/right column position is NOT reliably winner/loser — resolve
    # by matching the headline text against each wrestler's parsed name.
    if winner_full and winner_full.startswith(left["name"]):
        winner_pos = "left"
    elif winner_full and winner_full.startswith(right["name"]):
        winner_pos = "right"
    else:
        if debug:
            print(f"    [WARN] Could not match headline '{headline}' to a wrestler cell; defaulting to left=winner")
        winner_pos = "left"

    winner, loser = (left, right) if winner_pos == "left" else (right, left)

    col_tables = tables[1].find_all("table") if len(tables) > 1 else []
    columns = []
    for ct in col_tables:
        ctrows = ct.find_all("tr")
        if not ctrows:
            continue
        label = ctrows[0].get_text(strip=True)
        body_rows = ctrows[1:]

        period_points = None
        event_rows = body_rows
        if body_rows:
            last_cells = body_rows[-1].find_all("td")
            if len(last_cells) == 2 and all(c.get_text(strip=True).isdigit() for c in last_cells):
                left_pts = int(last_cells[0].get_text(strip=True))
                right_pts = int(last_cells[1].get_text(strip=True))
                period_points = {
                    "winner": left_pts if winner_pos == "left" else right_pts,
                    "loser": right_pts if winner_pos == "left" else left_pts,
                }
                event_rows = body_rows[:-1]

        events, notes = [], []
        for r in event_rows:
            tds = r.find_all("td")
            if len(tds) == 1:
                text = tds[0].get_text(strip=True)
                if text:
                    notes.append(text)
            elif len(tds) == 2:
                left_text = tds[0].get_text(strip=True)
                right_text = tds[1].get_text(strip=True)
                left_side = "winner" if winner_pos == "left" else "loser"
                right_side = "loser" if winner_pos == "left" else "winner"
                if left_text:
                    events.append({"side": left_side, "text": left_text})
                if right_text:
                    events.append({"side": right_side, "text": right_text})

        columns.append({
            "label": label,
            "notes": notes,
            "events": events,
            "period_points": period_points,
        })

    return {
        "headline": headline,
        "winner": winner,
        "loser": loser,
        "columns": columns,
    }

# ---------------------------------------------------------------------------
# Scrape a full weight class
# ---------------------------------------------------------------------------

def load_cached_bouts(out_path: Path) -> dict[int, dict]:
    """
    Loads a previously-saved {weight}.json (if any) into {bout_number: bout_dict}.
    Only entries with a valid parsed payload count as cached — this is how a
    prior run's parse failures get naturally retried on the next run instead
    of being treated as permanently done.
    """
    if not out_path.exists():
        return {}
    try:
        existing = json.loads(out_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    cache = {}
    for bout in existing:
        bn = bout.get("bout_number")
        if bn is not None and bout.get("winner") and bout.get("loser"):
            cache[bn] = bout
    return cache


def scrape_weight_class(
    session,
    tournament_session_id,
    tournament_id,
    weight,
    group_id,
    delay: float,
    cache: dict[int, dict],
    debug: bool = False,
) -> tuple[list[dict], bool]:
    # NOTE: cache entries are trusted as final without re-checking match status.
    # That's safe today because every 2026 bout is long since completed. If this
    # is ever reused for live in-progress tracking, an in-progress match must
    # NOT be cached/skipped this way — only bouts confirmed complete should be.
    bouts = []
    bout_number = 1
    skipped = 0
    fetched = 0
    blocked = False
    while bout_number <= MAX_BOUTS_PER_WEIGHT:
        cached = cache.get(bout_number)
        if cached is not None:
            bouts.append(cached)
            skipped += 1
            bout_number += 1
            continue

        try:
            match_id = resolve_match_id(session, tournament_session_id, group_id, bout_number)
            if not match_id:
                break

            time.sleep(delay)
            html = fetch_bout_html(session, tournament_session_id, tournament_id, match_id)
        except RateLimitedError as e:
            print(f"      [BLOCKED] {e} at bout {bout_number} — stopping this weight class early, progress saved")
            blocked = True
            break

        parsed = parse_bout_html(html, debug=debug)
        if parsed is None:
            print(f"      [WARN] bout {bout_number} (matchId={match_id}): could not parse, skipping")
        else:
            parsed["weight"] = weight
            parsed["bout_number"] = bout_number
            parsed["match_id"] = match_id
            bouts.append(parsed)
            fetched += 1
            if debug:
                w, l = parsed["winner"], parsed["loser"]
                print(f"      bout {bout_number}: {w['name']} def. {l['name']}  {w['score']}-{l['score']}")

        bout_number += 1
        time.sleep(delay)

    if skipped:
        print(f"      ({skipped} bout(s) already cached, skipped; {fetched} newly fetched)")

    return bouts, blocked

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def scrape_year(year: int, weights: list[int], delay: float, debug: bool = False) -> bool:
    if year not in TOURNAMENT_IDS:
        print(f"[ERROR] No tournament ID known for {year}.")
        return False
    tournament_id = TOURNAMENT_IDS[year]

    print(f"\n{'='*60}")
    print(f"Scraping {year} NCAA D1 Championships bout detail (ID: {tournament_id})")
    print(f"{'='*60}")

    out_dir = DATA_DIR / str(year) / "ncaa-tourney" / "bout_detail"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("\n1. Establishing session...")
    session = build_session()
    session_id = establish_session(session, debug=debug)
    if not session_id:
        return False

    print(f"\n2. Entering tournament {tournament_id}...")
    tournament_session_id = enter_tournament(session, session_id, tournament_id, debug=debug)
    if not tournament_session_id:
        print("[FAIL] Could not establish tournament session.")
        return False

    print("\n3. Building weight class ID map...")
    wc_map = get_weight_class_id_map(session, tournament_session_id, tournament_id, debug=debug)
    if not wc_map:
        print("[FAIL] Could not build weight class map. Aborting.")
        return False

    total_bouts = 0
    for weight in weights:
        group_id = wc_map.get(weight)
        if not group_id:
            print(f"\n   [SKIP] Weight {weight} not found in tournament.")
            continue

        out_path = out_dir / f"{weight}.json"
        cache = load_cached_bouts(out_path)

        print(f"\n4. Weight class {weight} (group_id={group_id})" + (f" — {len(cache)} cached" if cache else ""))
        bouts, blocked = scrape_weight_class(
            session, tournament_session_id, tournament_id, weight, group_id, delay, cache, debug=debug,
        )
        out_path.write_text(json.dumps(bouts, indent=2, ensure_ascii=False))
        print(f"   [OK] {len(bouts)} bouts saved: {out_path}")
        total_bouts += len(bouts)

        # Tag each bout with its round/bracket from the existing
        # matches.json (see scripts/ncaa/reconcile_bout_detail.py). Runs
        # automatically so a scrape always leaves round-tagged output —
        # no separate manual step required.
        reconcile_weight(year, weight)

        if blocked:
            print(f"\n[STOPPED] Rate-limited partway through weight {weight}. "
                  f"Progress so far is saved and cached — re-run this same command "
                  f"once the block clears to pick up exactly where this left off; "
                  f"remaining weight classes ({[w for w in weights if w > weight]}) were not attempted.")
            return False

    print(f"\n[DONE] {total_bouts} total bouts scraped for {year}.")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Scrape timestamped period-by-period NCAA D1 bout detail from TrackWrestling"
    )
    parser.add_argument("--year", type=int, required=True, help="Tournament year (e.g. 2026)")
    parser.add_argument(
        "--weights",
        type=str,
        default=None,
        help="Comma-separated weight classes to scrape (default: all 10)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Seconds to sleep between each request to trackwrestling.com (default: 1.5)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable verbose per-bout output")
    args = parser.parse_args()

    weights = (
        [int(w.strip()) for w in args.weights.split(",")]
        if args.weights
        else WEIGHT_CLASSES
    )

    ok = scrape_year(args.year, weights, args.delay, debug=args.debug)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
