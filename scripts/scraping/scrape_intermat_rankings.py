#!/usr/bin/env python3
"""
Deterministic scraper for InterMat's NCAA DI rankings page.

Unlike FloWrestling (scrape_flo_preseason_rankings.py), InterMat does not
publish a dated archive with a date <select> -- one URL (per season) always
shows whatever InterMat's CURRENT live rankings are, and all 10 weight
classes are already rendered server-side in one page load as Bootstrap tab
panes (confirmed: a plain `requests.get()` with no JS execution returns the
full 33-wrestler table for every weight -- no Selenium needed here, unlike
Flo). So there's no per-date discovery step, and no way to ask the site
itself "what's new since last time" -- every run just re-scrapes today's
live page.

To avoid piling up an identical file every single run, this diffs the
freshly-scraped data against the most recently archived snapshot and only
writes (datestamped with today's date) when something actually changed --
a rank moved, a record updated, a wrestler entered/dropped out, etc. A run
with no real changes touches nothing on disk. Safe to run as often as
you like (e.g. daily via cron/a scheduled task) -- meant to be re-run
often so "the latest file on disk" is always current for
correlate_intermat_rankings.py and anything downstream to pull for the
website. Never rewrites a PRIOR date's file; if content changes more than
once on the same calendar day, that day's own file is updated in place.

Output schema deliberately mirrors scrape_flo_preseason_rankings.py's
(source, rankings_url, ranking_date, season, note, weights: {weight_str:
[{rank, name, school, ...}, ...]}) so the two sources can be compared
apples-to-apples and run through the same wrestler-matching approach
(see scripts/rankings/correlate_intermat_rankings.py). InterMat's table
happens to also expose class/conference/record for free -- kept as extra
per-entry fields, additive only, so nothing that reads rank/name/school
like Flo's files breaks.

Usage:
  .venv/bin/python scripts/scraping/scrape_intermat_rankings.py
  .venv/bin/python scripts/scraping/scrape_intermat_rankings.py --season 2026-27 --force
"""

import argparse
import json
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

WEIGHT_ORDER = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]

# season label -> (URL slug, tourney_year). InterMat's slug ("r78" etc.) is
# season-specific and NOT derivable by formula (confirmed no date/season
# param in the URL or page -- it's just an opaque incrementing id) -- add a
# new entry here each fall by browsing https://intermatwrestle.com/rankings.html/
# and copying the NCAA DI link's slug.
SEASONS = {
    "2026-27": {"slug": "ncaa-di-r78", "tourney_year": 2027},
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
}

COLUMN_NAMES = ("RANK", "WRESTLER", "SCHOOL", "CLASS", "CONFERENCE", "RECORD")


def build_url(slug: str) -> str:
    return f"https://intermatwrestle.com/rankings.html/{slug}/"


def scrape_weight_table(soup: BeautifulSoup, weight: int) -> list[dict]:
    """Parse one weight's tab pane (a <div id="{weight}">). Column meaning is
    read from the header row's text (same defensive approach as the Flo
    scraper) rather than hardcoded positions, in case InterMat's column
    order/set ever changes."""
    div = soup.find("div", id=str(weight))
    if not div:
        raise RuntimeError(f"No pane found for weight {weight}")
    table = div.find("table")
    if not table:
        raise RuntimeError(f"No table found for weight {weight}")

    rows = []
    for tr in table.find_all("tr"):
        cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
        if cells:
            rows.append(cells)

    header_idx = next((i for i, r in enumerate(rows) if r and r[0].strip().upper() == "RANK"), None)
    if header_idx is None:
        raise RuntimeError(f"No header row found for weight {weight}")

    header = [c.strip().upper() for c in rows[header_idx]]
    col = {name: header.index(name) for name in COLUMN_NAMES if name in header}
    if "RANK" not in col or "WRESTLER" not in col or "SCHOOL" not in col:
        raise RuntimeError(f"Header row for weight {weight} missing required column(s): {header}")

    out = []
    for r in rows[header_idx + 1:]:
        if len(r) <= col["RANK"]:
            continue
        try:
            rank = int(r[col["RANK"]])
        except ValueError:
            continue  # not a data row
        entry = {
            "rank": rank,
            "name": r[col["WRESTLER"]],
            "school": r[col["SCHOOL"]],
        }
        for extra in ("CLASS", "CONFERENCE", "RECORD"):
            if extra in col and len(r) > col[extra]:
                entry[extra.lower()] = r[col[extra]]
        out.append(entry)
    out.sort(key=lambda e: e["rank"])
    return out


def latest_snapshot(out_dir: Path) -> Path | None:
    """Newest existing raw snapshot in out_dir (YYYY-MM-DD.json filenames
    sort chronologically), or None if there isn't one yet. Excludes
    "_matched" companion files written by correlate_intermat_rankings.py."""
    files = sorted(f for f in out_dir.glob("*.json") if not f.stem.endswith("_matched"))
    return files[-1] if files else None


def scrape_and_save(season_label: str, force: bool = False) -> bool:
    """Scrape InterMat's current live snapshot and archive it ONLY if it
    differs from the most recently archived snapshot -- this is meant to be
    run often (e.g. daily/weekly) without piling up identical files every
    time nothing on InterMat's page has actually changed. Never touches or
    overwrites a PRIOR date's file; if the content changed more than once
    on the same calendar day, today's own file is updated in place (still
    "today's" snapshot, not old data). Returns False (no write) when
    nothing changed and force is not set."""
    cfg = SEASONS[season_label]
    url = build_url(cfg["slug"])
    tourney_year = cfg["tourney_year"]

    out_dir = DATA_DIR / str(tourney_year) / "intermat-preseason-rankings"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[{season_label}] fetching {url}")
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    weights_out = {}
    for w in WEIGHT_ORDER:
        entries = scrape_weight_table(soup, w)
        weights_out[str(w)] = entries
        print(f"  weight {w}: {len(entries)} entries")

    prior = latest_snapshot(out_dir)
    if prior and not force:
        prior_weights = json.loads(prior.read_text()).get("weights", {})
        if prior_weights == weights_out:
            print(f"[{season_label}] no change since {prior.name}, skipping")
            return False
        print(f"[{season_label}] change detected since {prior.name}")

    date_str = date.today().strftime("%Y-%m-%d")
    out_path = out_dir / f"{date_str}.json"
    payload = {
        "source": "InterMat",
        "rankings_url": url,
        "ranking_date": date_str,
        "season": tourney_year,
        "note": f"{season_label} season, live snapshot (scraped via "
                f"scripts/scraping/scrape_intermat_rankings.py)",
        "weights": weights_out,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"[{season_label}] saved {out_path}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Scrape InterMat's current NCAA DI rankings snapshot")
    parser.add_argument("--season", default=max(SEASONS.keys()), choices=list(SEASONS.keys()),
                         help="Season label, e.g. 2026-27 (default: latest configured season)")
    parser.add_argument("--force", action="store_true",
                         help="Archive today's snapshot even if it's identical to the last one on file")
    args = parser.parse_args()
    scrape_and_save(args.season, force=args.force)


if __name__ == "__main__":
    main()
