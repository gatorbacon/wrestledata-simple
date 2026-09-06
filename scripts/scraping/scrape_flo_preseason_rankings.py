#!/usr/bin/env python3
"""
Deterministic scraper for FloWrestling's NCAA DI weekly rankings archive.

No AI/agent involvement needed to run this -- the URL scheme and page
structure were reverse-engineered once (see conversation history / commit
message) and are now fully mechanical:

  https://www.flowrestling.org/rankings/{event_id}-{season}-ncaa-di-wrestling-rankings/{ranking_id}-{weight}

Within one season+date, the 10 weight classes occupy 10 CONSECUTIVE
ranking_ids in a fixed order (WEIGHT_ORDER below). Given any one known
(weight, ranking_id) pair for a season, this script:
  1. Loads that page and reads its date <select> to get every date's
     ranking_id for that one weight.
  2. Computes each date's "base" id (the id weight 125 would have) via
     the fixed offset table, then derives all 10 weights' ids for any
     target date by arithmetic -- no extra navigation needed to discover
     ids, only to fetch each page's actual table.
  3. Picks the closest available date to each target month (default:
     Oct 1, Nov 1, Dec 1, Jan 1, Feb 1) and scrapes every ranked wrestler
     per weight (rank/name/school) that the page actually shows -- this
     varies by date/season (sometimes 20, sometimes 24, sometimes the
     full 33-man field), so no fixed cutoff is applied.
  4. Writes data/{tourney_year}/flo-preseason-rankings/{date}.json in the
     same schema as the existing files (source, rankings_url, ranking_date,
     season, note, weights: {weight_str: [{rank, name, school}, ...]}).

Skips any output file that already exists (idempotent -- safe to re-run).

Usage:
  .venv/bin/python scripts/scraping/scrape_flo_preseason_rankings.py --season 2023-24
  .venv/bin/python scripts/scraping/scrape_flo_preseason_rankings.py --all
  .venv/bin/python scripts/scraping/scrape_flo_preseason_rankings.py --season 2022-23 --headless
"""

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

WEIGHT_ORDER = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]
WEIGHT_OFFSET = {w: i for i, w in enumerate(WEIGHT_ORDER)}

# Pound-for-pound sits immediately BEFORE the 10 weights' consecutive run of
# ranking_ids -- confirmed empirically (not guessed) via the site's own tab
# bar: for 2026-27, weight 125's bootstrap_id is 56563 and the "Pound-for-
# pound" tab resolves to ranking_id 56562 (base_id - 1); same -1 relationship
# holds for 2025-26 (54619 -> 54618). Uses the exact same table markup/parser
# as the weight pages (scrape_table() already detects columns by header text,
# and P4P pages have their own layout quirks -- e.g. a "WT" column instead of
# "Year" in some seasons -- so no parsing changes needed, just the offset).
P4P_OFFSET = -1

# season label -> (event_id, bootstrap ranking_id, bootstrap weight, tourney_year,
#                   calendar year the season STARTS in -- Oct/Nov/Dec targets use
#                   this year, Jan/Feb targets use start_year + 1)
SEASONS = {
    "2026-27": {"event_id": 16146571, "bootstrap_id": 56563, "bootstrap_weight": 125,
                "tourney_year": 2027, "start_year": 2026},
    "2025-26": {"event_id": 14300895, "bootstrap_id": 54619, "bootstrap_weight": 125,
                "tourney_year": 2026, "start_year": 2025},
    "2024-25": {"event_id": 12557781, "bootstrap_id": 50608, "bootstrap_weight": 125,
                "tourney_year": 2025, "start_year": 2024},
    "2023-24": {"event_id": 10846490, "bootstrap_id": 46418, "bootstrap_weight": 125,
                "tourney_year": 2024, "start_year": 2023},
    "2022-23": {"event_id": 7981809, "bootstrap_id": 43346, "bootstrap_weight": 184,
                "tourney_year": 2023, "start_year": 2022},
    "2021-22": {"event_id": 7174019, "bootstrap_id": 39700, "bootstrap_weight": 125,
                "tourney_year": 2022, "start_year": 2021},
}

TARGET_MONTHS = [10, 11, 12, 1, 2]  # Oct, Nov, Dec, Jan, Feb
RETRY_WAIT_SECONDS = 2.5


def build_url(event_id: int, season: str, ranking_id: int, weight) -> str:
    return f"https://www.flowrestling.org/rankings/{event_id}-{season}-ncaa-di-wrestling-rankings/{ranking_id}-{weight}"


def setup_driver(headless: bool):
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1400,1000")
    # "normal" (default) blocks driver.get() until the browser's full `load` event
    # fires, i.e. every third-party ad/tracking script on the page has settled.
    # Measured impact: ~30s/page normally, but 4+ minutes on a fresh route's first
    # navigation (new event_id) where ~80 ad-tech requests fire, some hanging/503ing.
    # We only need the DOM table, which scrape_table()'s own retry loop already
    # waits for -- "eager" (return after DOMContentLoaded, don't wait on subresources)
    # is sufficient and avoids blocking on that ad-tech traffic entirely.
    options.page_load_strategy = "eager"
    driver = webdriver.Chrome(options=options)
    return driver


def dismiss_cookie_banner(driver):
    try:
        btn = WebDriverWait(driver, 3).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Reject Non-Essential')]"))
        )
        btn.click()
    except Exception:
        pass  # banner may not appear (already dismissed via cookie) -- fine either way


def get_date_options(driver) -> list[dict]:
    """Read the date <select> on the currently loaded page.
    Returns [{"text": "Oct 18, 2024", "value": "/rankings/.../{id}-{weight}[-slug]"}]"""
    for attempt in range(3):
        try:
            options = driver.execute_script("""
                const sel = document.querySelector('select');
                if (!sel) return null;
                return Array.from(sel.options).map(o => ({text: o.textContent.trim(), value: o.value}));
            """)
            if options:
                return options
        except Exception:
            pass
        time.sleep(RETRY_WAIT_SECONDS)
    raise RuntimeError("Could not read date <select> -- page may not have loaded correctly")


def extract_id_from_value(value: str) -> int:
    """Extract the ranking_id from the LAST path segment (e.g. '.../46394-125-matt-ramos'
    -> 46394). The event_id-season segment earlier in the path also matches a bare
    digits-dash-digits pattern, so this must not just take the first match in the string."""
    last_segment = value.rstrip("/").rsplit("/", 1)[-1]
    m = re.match(r"(\d+)-", last_segment)
    if not m:
        raise ValueError(f"Could not parse ranking_id from select value: {value}")
    return int(m.group(1))


def parse_date_text(text: str) -> datetime:
    return datetime.strptime(text, "%b %d, %Y")


def closest_date_to_target(date_options: list[dict], target: datetime) -> dict:
    best = min(date_options, key=lambda o: abs((parse_date_text(o["text"]) - target).days))
    return best


def scrape_table(driver, url: str) -> list[dict]:
    """Navigate to a ranking page and extract every ranked [{rank, name, school}] row
    the page actually shows (varies by date/season -- sometimes 20, sometimes 24,
    sometimes the full 33-man field). No fixed cutoff: keep whatever's there.

    Column layout is NOT stable across seasons -- confirmed two different real
    layouts in the wild: older seasons use [Rank, Grade, Name, School, Previous]
    (5 cols, sometimes with a real <th> header, sometimes headerless -- older
    archived pages render the labels outside the <table> entirely), while the
    2026-27 season switched to [Rank, Name, School, Year] (4 cols, always has a
    header). Hardcoding column positions silently produces garbage (e.g. "school"
    values like "3rd"/"2nd" -- actually the Year column) when the layout changes
    without warning. So: read column meaning from the header text when a header
    row is present (first cell not parseable as an int), and only fall back to
    the classic 5-column position default for genuinely headerless tables.
    """
    DEFAULT_RANK_I, DEFAULT_NAME_I, DEFAULT_SCHOOL_I = 0, 2, 3

    def find_column_indices(header_row: list[str]):
        lower = [c.lower() for c in header_row]
        try:
            return lower.index("rank"), lower.index("name"), lower.index("school")
        except ValueError:
            return None

    def parse_rows(rows: list[list[str]]) -> list[dict]:
        if not rows:
            return []
        header_cols = None
        first_cell = rows[0][0] if rows[0] else ""
        try:
            int(first_cell)
            is_header = False
        except ValueError:
            is_header = True
        if is_header:
            header_cols = find_column_indices(rows[0])
        rank_i, name_i, school_i = header_cols if header_cols else (DEFAULT_RANK_I, DEFAULT_NAME_I, DEFAULT_SCHOOL_I)

        out = []
        for r in rows:
            if len(r) <= max(rank_i, name_i, school_i):
                continue
            try:
                rank = int(r[rank_i])
            except ValueError:
                continue  # header row, or any other non-data row -- skip
            out.append({"rank": rank, "name": r[name_i], "school": r[school_i]})
        out.sort(key=lambda e: e["rank"])
        return out

    for attempt in range(5):
        driver.get(url)
        # Progressive backoff: "eager" page-load-strategy returns control before
        # subresources/hydration finish, so occasionally the table isn't populated
        # yet on the first check. Give later attempts more time rather than a flat wait.
        time.sleep(RETRY_WAIT_SECONDS * (attempt + 1))
        rows = driver.execute_script("""
            const table = document.querySelector('table');
            if (!table) return null;
            const rows = Array.from(table.querySelectorAll('tr'));
            const out = [];
            for (const r of rows) {
                const cells = Array.from(r.querySelectorAll('td,th')).map(c => c.textContent.trim());
                out.push(cells);
            }
            return out;
        """)
        if rows:
            parsed = parse_rows(rows)
            # Require at least rank 1 present -- a partially-hydrated/garbled page
            # (seen in testing: a mid-render read returned a corrupted header and
            # zero usable rows) will fail this check and get retried instead of
            # silently accepted as "0 entries".
            if parsed and parsed[0]["rank"] == 1:
                return parsed
        time.sleep(RETRY_WAIT_SECONDS)

    raise RuntimeError(f"Table never loaded cleanly for {url}")


def discover_dated_base_ids(season_label: str, driver):
    """Load the bootstrap weight's page ONCE, read its date <select>, and
    derive every available date's base_id (the id weight 125 would have) via
    the fixed offset table. This is the only page load needed to know what
    dates exist -- scraping the other 9 weights only happens later, per date,
    once a caller has decided that date is actually new."""
    cfg = SEASONS[season_label]
    event_id = cfg["event_id"]

    bootstrap_url = build_url(event_id, season_label, cfg["bootstrap_id"], cfg["bootstrap_weight"])
    print(f"[{season_label}] bootstrapping from {bootstrap_url}")
    driver.get(bootstrap_url)
    time.sleep(RETRY_WAIT_SECONDS)
    dismiss_cookie_banner(driver)
    date_options = get_date_options(driver)

    bootstrap_offset = WEIGHT_OFFSET[cfg["bootstrap_weight"]]
    dated_base_ids = []  # (date, base_id_for_weight_125)
    for opt in date_options:
        try:
            d = parse_date_text(opt["text"])
        except ValueError:
            continue
        rid = extract_id_from_value(opt["value"])
        base_id = rid - bootstrap_offset
        dated_base_ids.append((d, base_id))

    out_dir = DATA_DIR / str(cfg["tourney_year"]) / "flo-preseason-rankings"
    out_dir.mkdir(parents=True, exist_ok=True)
    return cfg, out_dir, dated_base_ids


def scrape_and_save_date(season_label: str, cfg: dict, out_dir: Path, date_obj: datetime,
                          base_id: int, driver, note: str, force: bool = False) -> bool:
    """Scrape all 10 weights plus pound-for-pound for one already-chosen date
    and archive it. Returns False (no scraping done) if the file already
    exists and force is not set -- callers use this to decide whether
    anything happened."""
    event_id = cfg["event_id"]
    tourney_year = cfg["tourney_year"]
    date_str = date_obj.strftime("%Y-%m-%d")
    out_path = out_dir / f"{date_str}.json"
    if out_path.exists() and not force:
        print(f"  [{season_label}] {date_str}: already exists, skipping")
        return False

    print(f"  [{season_label}] scraping {date_str} (base_id={base_id})")
    weights_out = {}
    for w in WEIGHT_ORDER:
        rid = base_id + WEIGHT_OFFSET[w]
        url = build_url(event_id, season_label, rid, w)
        try:
            entries = scrape_table(driver, url)
        except Exception as e:
            print(f"    WARN weight {w}: {e}")
            entries = []
        weights_out[str(w)] = entries
        print(f"    weight {w}: {len(entries)} entries")

    p4p_rid = base_id + P4P_OFFSET
    p4p_url = build_url(event_id, season_label, p4p_rid, "p4p")
    try:
        p4p_out = scrape_table(driver, p4p_url)
    except Exception as e:
        print(f"    WARN p4p: {e}")
        p4p_out = []
    print(f"    p4p: {len(p4p_out)} entries")

    payload = {
        "source": "FloWrestling",
        "rankings_url": f"https://www.flowrestling.org/rankings/{event_id}-{season_label}-ncaa-di-wrestling-rankings",
        "ranking_date": date_str,
        "season": tourney_year,
        "note": note,
        "weights": weights_out,
        "p4p": p4p_out,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"  [{season_label}] saved {out_path}")
    return True


def scrape_latest(season_label: str, driver, force: bool = False) -> bool:
    """In-season weekly pull: find whatever date FloWrestling most recently
    posted (not a fixed preseason target month) and archive it if we don't
    already have it. If we already have the latest date logged, this stops
    after the single bootstrap page load -- it never touches the other 9
    weight pages. Returns True if a new snapshot was scraped."""
    cfg, out_dir, dated_base_ids = discover_dated_base_ids(season_label, driver)
    if not dated_base_ids:
        print(f"[{season_label}] no dates found on bootstrap page")
        return False

    date_obj, base_id = max(dated_base_ids, key=lambda x: x[0])
    note = f"{season_label} season, latest available snapshot (scraped via scripts/scraping/scrape_flo_preseason_rankings.py --latest)"
    return scrape_and_save_date(season_label, cfg, out_dir, date_obj, base_id, driver, note, force=force)


def scrape_season(season_label: str, driver, target_months=TARGET_MONTHS, force: bool = False):
    cfg, out_dir, dated_base_ids = discover_dated_base_ids(season_label, driver)
    start_year = cfg["start_year"]

    used_dates: set[str] = set()
    for month in target_months:
        target_year = start_year if month >= 8 else start_year + 1
        target = datetime(target_year, month, 1)
        # Snapshots are irregularly spaced (e.g. a big Sep->Oct gap), so the
        # nearest-by-days date for one target month can collide with the date
        # already picked for an earlier month. Exclude already-used dates so
        # each target month gets a DISTINCT snapshot -- falling back to the
        # closest unused one rather than silently duplicating/overwriting.
        candidates = [(d, b) for d, b in dated_base_ids if d.strftime("%Y-%m-%d") not in used_dates]
        if not candidates:
            print(f"  [{season_label}] target month {month}: no unused dates left, skipping")
            continue
        date_obj, base_id = min(candidates, key=lambda x: abs((x[0] - target).days))
        used_dates.add(date_obj.strftime("%Y-%m-%d"))
        note = f"{season_label} season, {month_label(month)} touch point (scraped via scripts/scraping/scrape_flo_preseason_rankings.py)"
        scrape_and_save_date(season_label, cfg, out_dir, date_obj, base_id, driver, note, force=force)


def month_label(month: int) -> str:
    return {9: "September", 10: "October", 11: "November", 12: "December",
            1: "January", 2: "February"}.get(month, str(month))


def main():
    parser = argparse.ArgumentParser(description="Scrape FloWrestling NCAA DI preseason/in-season rankings")
    parser.add_argument("--season", choices=list(SEASONS.keys()), help="Single season to scrape, e.g. 2023-24")
    parser.add_argument("--all", action="store_true", help="Scrape all seasons in SEASONS")
    parser.add_argument(
        "--headless", action="store_true", default=False,
        help="Run Chrome headless. NOT recommended: flowrestling.org serves an empty/unhydrated "
             "page to headless Chrome (confirmed via testing) even though it's fine with a normal "
             "automated window. Default is a visible window.",
    )
    parser.add_argument("--force", action="store_true", help="Re-scrape even if output file already exists")
    parser.add_argument(
        "--target-months", default="10,11,12,1,2",
        help="Comma-separated target months (1-12) to find closest snapshot for. Default: Oct-Feb.",
    )
    parser.add_argument(
        "--latest", action="store_true",
        help="In-season weekly pull: grab whatever date FloWrestling most recently posted, "
             "instead of the fixed preseason target months. Only touches the bootstrap page "
             "(cheap) if that date is already archived -- ignores --target-months.",
    )
    args = parser.parse_args()

    if not args.season and not args.all:
        parser.error("Specify --season <label> or --all")

    seasons_to_run = list(SEASONS.keys()) if args.all else [args.season]
    target_months = [int(m) for m in args.target_months.split(",")]

    driver = setup_driver(headless=args.headless)
    try:
        for season_label in seasons_to_run:
            if args.latest:
                scrape_latest(season_label, driver, force=args.force)
            else:
                scrape_season(season_label, driver, target_months=target_months, force=args.force)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
