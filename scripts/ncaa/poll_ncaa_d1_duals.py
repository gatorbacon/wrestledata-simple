#!/usr/bin/env python3
"""
Poll TrackWrestling's season-wide "Results" feed for newly-completed NCAA
duals involving a D1 team, and fetch full weight-by-weight bout detail for
any new ones found.

This SUPPLEMENTS (does not replace) the team-by-team roster scraper
(wrestle_scraper_raw_mt_locked.py). That scraper is the source of truth and
runs weekly; this script is meant to run far more often (e.g. nightly) as a
cheap way to detect "did a dual happen" without re-crawling every D1 team's
roster and every wrestler's match page.

How it works (discovered via manual TrackWrestling investigation, 2026-09-13):
  Browse > Seasons > <season> College Men > NCAA lands on seasons/Results.jsp,
  which embeds ALL of that season's events (tournaments + duals) in a single
  client-side JS array called `dataGrid` -- one row per event, ~250 rows for
  a full season, regardless of the visible "Show" page size. Each row is a
  fixed-position array:

    idx 0   event id (dualId, for dual rows)
    idx 3/4 start/end date (YYYYMMDD)
    idx 5   tournament name (set ONLY for tournament rows; empty for duals)
    idx 8   team1 teamId   (empty for tournament rows)
    idx 9   team1 name
    idx 10  team1 state
    idx 11  team1 final score
    idx 12  team2 teamId
    idx 13  team2 name
    idx 14  team2 state
    idx 15  team2 final score

  A row is a DUAL iff idx 9 and idx 13 are both non-empty (this is a cleaner
  discriminator than event-name pattern matching).

  Weight-by-weight bout detail for a dual lives at a separate, plain
  authenticated page: seasons/DualMatches.jsp?dualId=<idx0>&teamId=<idx8 or
  idx12>&twSessionId=<session>. It renders a `.dataGridRow` per weight class,
  each with columns [_, weight, summary, team1_points, team2_points], where
  summary looks like:
    "Troy Spratley (Oklahoma State) over Dean Peterson (Iowa) (Dec 5-2)"
  Confirmed identical output whether you fetch it directly (no click needed)
  or reach it by clicking the dual in the Results list -- clicking triggers
  `openEvent(idx)` which opens this exact URL in a popup. IMPORTANT: clicking
  it via a synthetic (non-trusted) click hangs the page indefinitely -- when
  window.open() is silently blocked, this site's JS does not handle the null
  return and hangs. A real navigation to the URL (which is all this script
  does) has no such problem.

D1 team identification:
  Rather than re-scraping Teams.jsp here, this reuses the team list already
  produced by scrape_ncaa_d1_teams.py:
    data/team_lists/ncaa_men/<season>/teams.json
  (each entry's `url` embeds `teamId` as a query param). Run that script
  first if the file is missing or stale for the target season.

State / output:
  mt/tracking/ncaa_dual_poll_state_<season>_<gender>.json
      {"seen_dual_ids": [...]}  -- dualIds already fetched; a dual is only
      added here after its detail fetch succeeds, so a failed fetch is
      retried on the next run instead of being silently skipped.
  mt/data/ncaa_<gender>/<season>/duals/<dualId>.json
      One file per newly-detected dual: date, both teams (name/state/score),
      and the parsed weight-by-weight bout list.

This is a PROTOTYPE. Open decisions before this becomes a production/cron
job: whether "D1 dual" should require both teams to be D1 or just one
(currently: just one, see --d1-mode), how often to run it, and whether the
per-dual output feeds directly into an existing data path or stays separate.

Usage:
  .venv/bin/python scripts/ncaa/poll_ncaa_d1_duals.py -season 2026
  .venv/bin/python scripts/ncaa/poll_ncaa_d1_duals.py -season 2026 -headless
  .venv/bin/python scripts/ncaa/poll_ncaa_d1_duals.py -season 2026 -dry-run
"""

import argparse
import json
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Set
from urllib.parse import parse_qs, urlparse

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException

BASE_URL = "https://www.trackwrestling.com"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TEAM_LISTS_DIR = PROJECT_ROOT / "data" / "team_lists"
TRACKING_DIR = PROJECT_ROOT / "mt" / "tracking"
DATA_DIR = PROJECT_ROOT / "mt" / "data"

# Bout summary line, e.g.:
#   "Troy Spratley (Oklahoma State) over Dean Peterson (Iowa) (Dec 5-2)"
BOUT_SUMMARY_RE = re.compile(
    r"^(?P<winner>.+?) \((?P<winner_team>.+?)\) over "
    r"(?P<loser>.+?) \((?P<loser_team>.+?)\) \((?P<method>.+?)\)$"
)

# Forfeit / no-opponent-team variant, e.g.:
#   "Tucker Owens (Air Force) over Unknown (For.)"
# There's no loser_team here since there was no opposing wrestler.
BOUT_SUMMARY_FORFEIT_RE = re.compile(
    r"^(?P<winner>.+?) \((?P<winner_team>.+?)\) over "
    r"(?P<loser>.+?) \((?P<method>.+?)\)$"
)


def get_tim() -> int:
    return int(time.time() * 1000)


def get_season_text(season_year: int) -> List[str]:
    start_year = season_year - 1
    short_end = str(season_year)[-2:]
    return [
        f"{start_year}-{short_end} College Men",
        f"{start_year}-{short_end} College",
    ]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Poll TrackWrestling for newly-completed D1 duals."
    )
    parser.add_argument("-season", type=int, required=True,
                        help="Season ending year (e.g. 2026 for 2025-26 season)")
    parser.add_argument("-gender", type=str, default="men", choices=["men"],
                        help="Only NCAA men supported so far")
    parser.add_argument("-headless", action="store_true", help="Run browser headless")
    parser.add_argument("-dry-run", action="store_true",
                        help="Detect and print new D1 duals but do not fetch bout detail or write state")
    parser.add_argument("-d1-mode", choices=["either", "both"], default="either",
                        help="'either': at least one team is D1 (default). 'both': both teams must be D1.")
    parser.add_argument("-limit", type=int, default=None,
                        help="Only fetch bout detail for the first N new duals (for testing).")
    return parser.parse_args()


def load_d1_team_ids(season_year: int) -> Set[str]:
    path = TEAM_LISTS_DIR / "ncaa_men" / str(season_year) / "teams.json"
    if not path.exists():
        raise FileNotFoundError(
            f"D1 team list not found at {path}. Run "
            f"`scripts/scrape_ncaa_d1_teams.py -league ncaa -gender men -season {season_year}` first."
        )
    teams = json.loads(path.read_text())
    ids = set()
    for team in teams:
        qs = parse_qs(urlparse(team["url"]).query)
        team_id = qs.get("teamId", [None])[0]
        if team_id:
            ids.add(team_id)
    return ids


def state_path(season_year: int, gender: str) -> Path:
    return TRACKING_DIR / f"ncaa_dual_poll_state_{season_year}_{gender}.json"


def load_seen_dual_ids(season_year: int, gender: str) -> Set[str]:
    path = state_path(season_year, gender)
    if not path.exists():
        return set()
    data = json.loads(path.read_text())
    return set(data.get("seen_dual_ids", []))


def save_seen_dual_ids(season_year: int, gender: str, seen: Set[str]):
    path = state_path(season_year, gender)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"seen_dual_ids": sorted(seen)}, indent=2))


def dual_output_path(season_year: int, gender: str, dual_id: str) -> Path:
    return DATA_DIR / f"ncaa_{gender}" / str(season_year) / "duals" / f"{dual_id}.json"


class DualPoller:
    def __init__(self, season_year: int, gender: str, headless: bool, d1_mode: str):
        self.season_year = season_year
        self.gender = gender
        self.headless = headless
        self.d1_mode = d1_mode
        self.driver = None
        self.wait = None
        self.session_id: Optional[str] = None

    # -- driver / navigation -------------------------------------------------

    def setup_driver(self):
        options = webdriver.ChromeOptions()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--start-maximized")
        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 20)

    def _dismiss_cookie_modal_if_present(self, timeout: float = 5.0):
        """Best-effort dismissal of TrackWrestling's cookie/consent modal
        overlay, which intermittently blocks clicks on the main navigation.
        Ported from wrestle_scraper_raw_mt_locked.py -- same site, same issue.
        """
        try:
            overlay = None
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
                    continue

            if not overlay or not overlay.is_displayed():
                return

            print("Cookie/consent modal detected; attempting to dismiss it...")
            buttons = overlay.find_elements(
                By.CSS_SELECTOR, "button, a, input[type='button'], input[type='submit']"
            )
            preferred_keywords = ["accept", "agree", "save", "continue", "ok", "got it", "close"]
            clicked = False
            for btn in buttons:
                label = (btn.text or btn.get_attribute("value") or "").strip().lower()
                if any(k in label for k in preferred_keywords):
                    try:
                        btn.click()
                    except Exception:
                        self.driver.execute_script("arguments[0].click();", btn)
                    clicked = True
                    break
            if not clicked and buttons:
                try:
                    buttons[0].click()
                except Exception:
                    self.driver.execute_script("arguments[0].click();", buttons[0])

            try:
                WebDriverWait(self.driver, 5).until(EC.invisibility_of_element(overlay))
            except TimeoutException:
                pass
        except Exception as e:
            print(f"Error while attempting to dismiss cookie/consent modal: {e}")

    def _click_with_retry(self, locator, attempts: int = 3, delay: float = 2.0):
        """Click a link-text/CSS locator, retrying through cookie-modal
        interference. Handles the same flakiness the main scraper works
        around -- the top nav dropdown occasionally fails to open on the
        first click for no visible reason.
        """
        last_error = None
        for attempt in range(1, attempts + 1):
            try:
                self._dismiss_cookie_modal_if_present(timeout=3.0)
                el = self.wait.until(EC.element_to_be_clickable(locator))
                el.click()
                return el
            except (TimeoutException, ElementClickInterceptedException) as e:
                last_error = e
                print(f"  click attempt {attempt}/{attempts} failed for {locator}: {e.__class__.__name__}; retrying...")
                time.sleep(delay)
        raise last_error

    def navigate_to_results(self):
        """Browse > Seasons > <season> College Men > NCAA > Results."""
        print("Navigating to TrackWrestling...")
        self.driver.get(BASE_URL)
        time.sleep(3)
        self._dismiss_cookie_modal_if_present(timeout=7.0)

        print("Clicking Browse...")
        self._click_with_retry((By.CSS_SELECTOR, "nav.main-menu li a[href*='subMenu-browse']"))
        time.sleep(1)

        print("Clicking Seasons...")
        self._click_with_retry((By.LINK_TEXT, "Seasons"))
        time.sleep(2)

        print("Clicking More Seasons...")
        more_seasons_btn = self.wait.until(EC.presence_of_element_located((By.LINK_TEXT, "More Seasons")))
        self.driver.execute_script("arguments[0].scrollIntoView(true);", more_seasons_btn)
        time.sleep(1)
        try:
            more_seasons_btn.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", more_seasons_btn)

        # Wait for the season grid to actually render before searching it --
        # a bare sleep() here is exactly how the earlier flaky run raced the
        # page load and found zero elements on a genuinely-empty grid.
        try:
            self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#pageGridFrame .dataGridElement"))
            )
        except TimeoutException:
            print("  Warning: season grid did not appear within timeout, continuing anyway...")
        time.sleep(1)

        season_options = get_season_text(self.season_year)
        print(f"Looking for season: {season_options}")

        def find_season_on_page(max_attempts: int = 3):
            for attempt in range(max_attempts):
                elements = self.driver.find_elements(
                    By.CSS_SELECTOR, "#pageGridFrame .dataGridElement .publicLogin a"
                )
                if elements:
                    for elem in elements:
                        if any(opt in elem.text.strip() for opt in season_options):
                            return elem
                    return None  # grid loaded but no match on this page
                time.sleep(1)  # grid not loaded yet; retry
            return None

        season_link = find_season_on_page()
        page_num = 1
        while not season_link:
            next_arrows = self.driver.find_elements(By.CSS_SELECTOR, "i.icon-arrow_r.dgNext")
            if not next_arrows or not next_arrows[0].is_displayed():
                break
            page_num += 1
            print(f"Checking page {page_num}...")
            next_arrows[0].click()
            time.sleep(1)
            season_link = find_season_on_page()

        if not season_link:
            raise RuntimeError(f"Could not find season (tried: {season_options})")

        print(f"Found: {season_link.text}")
        season_link.click()
        time.sleep(2)

        # Select NCAA governing body and log in.
        self.wait.until(EC.presence_of_element_located((By.ID, "gbFrame")))
        select_elem = self.wait.until(EC.presence_of_element_located((By.ID, "gbId")))
        select = Select(select_elem)
        found = False
        for option in select.options:
            if "NCAA" in option.text.strip() and "NCWA" not in option.text.strip() and "NJCAA" not in option.text.strip():
                select.select_by_value(option.get_attribute("value"))
                found = True
                break
        if not found:
            raise RuntimeError(f"Could not find NCAA in governing body dropdown. Available: {[o.text for o in select.options]}")

        self._click_with_retry((By.CSS_SELECTOR, "input[value='Login']"))
        time.sleep(2)

        # We land on Results.jsp by default; confirm via the Results nav link.
        self.wait.until(EC.presence_of_element_located((By.ID, "PageFrame")))
        self.driver.switch_to.frame("PageFrame")
        try:
            self._click_with_retry((By.LINK_TEXT, "Results"), attempts=2)
        except TimeoutException:
            pass  # already on Results
        time.sleep(2)

        # Capture the session id for building direct URLs later.
        current_url = self.driver.current_url
        self.session_id = parse_qs(urlparse(current_url).query).get("twSessionId", [None])[0]
        if not self.session_id:
            raise RuntimeError("Could not extract twSessionId from URL after login.")
        print(f"Session established: {self.session_id}")

    def expand_results_page_size(self):
        """Bump the 'Show N' input to 250 so dataGrid holds the full season."""
        # NOTE: dataGrid already holds the FULL season regardless of the visible
        # page size (confirmed: Teams.jsp dataGrid had 289 entries while only
        # 50 were shown). This is kept only in case that changes; safe no-op
        # otherwise.
        try:
            show_input = self.driver.execute_script(
                "var inputs = document.querySelectorAll('input');"
                "for (var i = 0; i < inputs.length; i++) {"
                "  if (inputs[i].type === 'text' && inputs[i].value === '50') return inputs[i];"
                "}"
                "return null;"
            )
            if show_input:
                self.driver.execute_script(
                    "arguments[0].value = '250';"
                    "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));"
                    "arguments[0].dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true, keyCode:13, which:13}));",
                    show_input,
                )
                time.sleep(2)
        except Exception as e:
            print(f"Warning: could not bump page size (non-fatal): {e}")

    def get_data_grid(self) -> List[List[str]]:
        grid = self.driver.execute_script("return window.dataGrid;")
        if grid is None:
            raise RuntimeError("window.dataGrid not found on Results page.")
        return grid

    # -- dual detail -----------------------------------------------------------

    def fetch_dual_detail(self, dual_id: str, team_id: str, attempts: int = 3) -> List[Dict]:
        """Navigate directly to DualMatches.jsp and parse weight-by-weight bouts.

        Retries on a 0-row result: a batch run of ~100 sequential fetches with
        no delay between them produced 0 bouts across the board, which then
        succeeded cleanly once slowed down -- looks like TrackWrestling
        throttling/rate-limiting rapid-fire full-page navigations rather than
        a real absence of data, so a short backoff + retry recovers it.
        """
        url = (
            f"{BASE_URL}/seasons/DualMatches.jsp"
            f"?TIM={get_tim()}&twSessionId={self.session_id}"
            f"&dualId={dual_id}&teamId={team_id}"
        )
        for attempt in range(1, attempts + 1):
            self.driver.switch_to.default_content()
            self.driver.get(url)
            time.sleep(2)

            rows = self.driver.find_elements(By.CSS_SELECTOR, ".dataGridRow")
            if rows:
                break
            print(f"    0 .dataGridRow found on attempt {attempt}/{attempts} "
                  f"(title={self.driver.title!r}); backing off and retrying...")
            time.sleep(4 * attempt)
        else:
            print(f"    WARNING: giving up on dual_id={dual_id} after {attempts} attempts with 0 rows.")
            return []

        bouts = []
        for row in rows:
            cols = row.find_elements(By.CSS_SELECTOR, "[class*='data-grid-col-']")
            texts = [c.text.strip() for c in cols]
            if len(texts) < 3 or not texts[1] or not texts[2]:
                continue  # skip empty trailer rows
            weight, summary = texts[1], texts[2]
            m = BOUT_SUMMARY_RE.match(summary)
            bout = {"weight": weight, "summary": summary}
            if m:
                bout.update(m.groupdict())
            else:
                m2 = BOUT_SUMMARY_FORFEIT_RE.match(summary)
                if m2:
                    bout.update(m2.groupdict())
                    bout["loser_team"] = None
            bouts.append(bout)

        # Courtesy delay between duals to avoid re-triggering the throttling
        # behavior observed above.
        time.sleep(1.5)
        return bouts

    # -- main loop ---------------------------------------------------------

    def run(self, dry_run: bool = False, limit: Optional[int] = None):
        d1_ids = load_d1_team_ids(self.season_year)
        print(f"Loaded {len(d1_ids)} D1 team IDs for season {self.season_year}.")

        seen = load_seen_dual_ids(self.season_year, self.gender)
        print(f"{len(seen)} duals already seen from previous polls.")

        self.setup_driver()
        try:
            self.navigate_to_results()
            self.expand_results_page_size()
            grid = self.get_data_grid()
            print(f"Results feed has {len(grid)} events for the season.")

            new_duals = []
            for row in grid:
                if len(row) < 16:
                    continue
                dual_id = row[0]
                team1_id, team1_name, team1_state, team1_score = row[8], row[9], row[10], row[11]
                team2_id, team2_name, team2_state, team2_score = row[12], row[13], row[14], row[15]

                if not team1_name or not team2_name:
                    continue  # tournament row, not a dual

                team1_is_d1 = team1_id in d1_ids
                team2_is_d1 = team2_id in d1_ids
                if self.d1_mode == "both" and not (team1_is_d1 and team2_is_d1):
                    continue
                if self.d1_mode == "either" and not (team1_is_d1 or team2_is_d1):
                    continue

                if dual_id in seen:
                    continue

                new_duals.append({
                    "dual_id": dual_id,
                    "date": row[3],
                    "team1": {"teamId": team1_id, "name": team1_name, "state": team1_state, "score": team1_score, "is_d1": team1_is_d1},
                    "team2": {"teamId": team2_id, "name": team2_name, "state": team2_state, "score": team2_score, "is_d1": team2_is_d1},
                })

            print(f"Found {len(new_duals)} new D1 dual(s) since last poll.")
            for d in new_duals:
                t1, t2 = d["team1"], d["team2"]
                print(f"  [{d['date']}] {t1['name']}, {t1['state']} {t1['score']} - "
                      f"{t2['name']}, {t2['state']} {t2['score']} (dual_id={d['dual_id']})")

            if dry_run:
                print("Dry run: skipping bout-detail fetch and state update.")
                return new_duals

            if limit is not None:
                new_duals = new_duals[:limit]
                print(f"Limiting to first {limit} new dual(s) for this run.")

            for d in new_duals:
                t1, t2 = d["team1"], d["team2"]
                fetch_team_id = t1["teamId"] if t1["is_d1"] else t2["teamId"]
                try:
                    bouts = self.fetch_dual_detail(d["dual_id"], fetch_team_id)
                except Exception as e:
                    print(f"  ERROR fetching detail for dual_id={d['dual_id']}: {e}")
                    continue

                out = {
                    "dual_id": d["dual_id"],
                    "date": d["date"],
                    "team1": t1,
                    "team2": t2,
                    "bouts": bouts,
                }
                out_path = dual_output_path(self.season_year, self.gender, d["dual_id"])
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(json.dumps(out, indent=2))
                print(f"  Saved {len(bouts)} bouts -> {out_path}")

                seen.add(d["dual_id"])

            save_seen_dual_ids(self.season_year, self.gender, seen)
            return new_duals
        finally:
            if self.driver:
                self.driver.quit()


def main():
    args = parse_args()
    poller = DualPoller(
        season_year=args.season,
        gender=args.gender,
        headless=args.headless,
        d1_mode=args.d1_mode,
    )
    poller.run(dry_run=getattr(args, "dry_run"), limit=args.limit)


if __name__ == "__main__":
    main()
