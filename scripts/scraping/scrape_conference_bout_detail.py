#!/usr/bin/env python3
"""
Scrape period-by-period, timestamped bout detail for conference wrestling
championships from TrackWrestling's Classic bracket viewer -- same source
and schema as scrape_ncaa_bout_detail.py (see docs/matsavant.md's "NCAA
Bout-Level Play-by-Play" section for the full schema), just a different
tournament and output path. Reuses that script's scrape_tournament() core
unchanged.

Why this exists: the NCAA Championship bout-detail data (2021-2026, 3,720
bouts) is real event-level data suitable for a live win-probability / event-
value model, but it's exclusively national-qualifier-level talent. Conference
championships (Big Ten, Big 12, etc.) use the identical TrackWrestling
Classic viewer, cover 3+ more years of the same current scoring era, and
include lower-ranked/unranked wrestlers the NCAA bracket never reaches --
meaningfully increasing both data volume and the range of DPG levels
represented.

No round/bracket reconciliation is done for conference tournaments (unlike
NCAA) -- there's no parsed matches.json equivalent for these to join
against yet. Bouts are saved without a `round`/`bracket` field; add a
reconciler later if that's needed.

Finding a new conference's tournament ID: TrackWrestling has no public
listing of tournamentIds. Search Events Classic instead --
  https://www.trackwrestling.com/Login.jsp?TIM=<ms>&twSessionId=<sid>&tName=<query>&sDate=<mm/dd/yyyy>&eDate=<mm/dd/yyyy>&state=&lastName=&firstName=&teamName=&sfvString=&city=&gbId=&camps=false
(get a fresh twSessionId by GETing /Login.jsp first) -- then read the
tournamentId out of the matching result's `eventSelected(ID, 'name', ...)`
onclick/href. Confirm it's a real Classic tournament (not just a video
listing) by running it through enter_tournament() + get_weight_class_id_map()
before scraping -- a bad ID fails there, not silently mid-scrape.

Usage:
    python scripts/scraping/scrape_conference_bout_detail.py --conference big_ten --year 2026
    python scripts/scraping/scrape_conference_bout_detail.py --conference big_ten --year 2024 --weights 125,133
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.scraping.scrape_ncaa_bout_detail import scrape_tournament
from scripts.scraping.scrape_ncaa_tournament import WEIGHT_CLASSES

DATA_DIR = PROJECT_ROOT / "data"

# Tournament IDs discovered via Events Classic search (see module docstring).
# Add a new conference/year here once you've found and confirmed its ID.
CONFERENCE_TOURNAMENT_IDS = {
    "big_ten": {
        2026: 964607132,  # Bryce Jordan Center, State College PA, 03/07-03/08/2026
        2025: 911000132,  # Welsh Ryan Arena, Evanston IL, 03/08-03/09/2025
        2024: 825871132,  # XFINITY Center, College Park MD, 03/09-03/10/2024
        2023: 720278132,
        2022: 659853132,
        2021: 627927132,
        2019: 376962132,
        2018: 45444132,
        2017: 1510076,
        2016: 226034009,
        2015: 179825009,
        # 2020 cancelled (COVID).
    },
    "big_12": {
        2026: 974060132,  # BOK Center, Tulsa OK, 03/06-03/07/2026
        2025: 900890132,  # BOK Center, Tulsa OK, 03/08-03/09/2025
        2024: 848140132,  # BOK Center, Tulsa OK, 03/09-03/10/2024
        2023: 724521132,
        2022: 663928132,
        2021: 623655132,
        2020: 579474132,
        2019: 340409132,
        2015: 178809009,
        # 2016-2018 searched extensively (2026-09-15: "Big 12", "Big 12
        # Wrestling", "Big XII", "Cowboy", year-prefixed variants -- all with
        # a full-year date range) and not found on TrackWrestling Classic
        # under any tried name. Every "Big 12"/"Big XII" hit those years
        # resolved to an unrelated Illinois/Indiana high-school conference
        # ("NI Big 12", "Big XII Freshman/Sophomore"). Worth another look
        # with a specific host-school/venue name before concluding absent.
    },
    "acc": {
        2026: 948555132,  # Cassell Coliseum, Blacksburg VA, 03/08/2026
        2025: 882841132,  # Cameron Indoor Stadium, Durham NC, 03/09/2025
        2024: 815457132,  # Carmichael Arena, Chapel Hill NC, 03/10/2024
        2023: 696489132,
        2022: 653309132,
        2021: 618503132,
        2020: 545193132,
        2019: 291455132,
        2018: 45559132,
        2017: 260564009,
        2016: 228041009,
        2015: 128107,
    },
    "mac": {
        2026: 964861132,  # Alumni Arena, Buffalo NY, 03/06-03/07/2026
        2025: 911012132,  # CURE Insurance Arena, Trenton NJ, 03/07-03/08/2025
        2024: 830507132,  # Memorial Athletic and Convocation Center, Kent OH, 03/08-03/09/2024
        2022: 655295132,
        2020: 596502132,
        2018: 55261132,
        2017: 1517076,
        2016: 227036009,
        2015: 180829009,
        # 2019 (368799132) and 2021 (619497132) candidates are the correct
        # tournament by name/date but VerifyPassword's anonymous-viewer login
        # doesn't work on them (MainFrame.jsp comes back as a bare
        # GoToLogin.js redirect, unlike every working ID above) -- these two
        # editions appear to be password-protected on TrackWrestling itself,
        # not a wrong-ID problem. 2023's only found candidate (740818132,
        # "2023 MAC Wrestling Championship") resolved to a youth tournament
        # (weights 75-200) when verified -- wrong tournament, real one not
        # found under any tried name.
    },
    "pac_12": {
        2026: 974263132,  # Cal Poly, San Luis Obispo CA, 03/06/2026
        2023: 724583132,
        2022: 659781132,
        2021: 623766132,
        2020: 580101132,
        2019: 291172132,
        2018: 46882132,
        # 2024/2025 don't exist on TrackWrestling -- conference realignment
        # turmoil (most Pac-12 schools left in 2024).
        # 2015-2017 searched ("Pac-12", "Pac 12", "Pac12", "PAC-12", full
        # year range) and not found -- likely pre-dates Pac-12's
        # TrackWrestling adoption.
    },
    "socon": {
        2025: 896232132,  # Kimmel Arena, Asheville NC, 03/07-03/08/2025
        2024: 794933132,  # Holmes Convocation Center, Boone NC, 03/09/2024
        2023: 711986132,
        2022: 648217132,
        2021: 618689132,
        2020: 578857132,
        2019: 389127132,
        2018: 4805132,
        2017: 253335009,
        2016: 220835009,
        2015: 180832009,
        # 2026 not found on TrackWrestling under this or related names --
        # confirmed absent via a full-year 2026 date-range search, not just
        # an untried search term.
    },
}
# EIWA and Ivy League (per docs/matsavant.md's team_conferences.json) were
# searched for (2026-09-13: "EIWA", "EIWA Championship", "Eastern",
# "Intercollegiate", "EIWA Wrestling", "Ivy League" -- all with a
# 2024-2026 date range) and never found on TrackWrestling Classic. Ivy
# League schools wrestle their postseason through EIWA in real life, so
# these two are likely the same missing tournament, not two separate ones.
# Worth another look with different terms before concluding it's not on
# TrackWrestling at all -- add it here once found.


def scrape(conference: str, year: int, weights: list[int], delay: float, debug: bool = False) -> bool:
    ids = CONFERENCE_TOURNAMENT_IDS.get(conference)
    if not ids or year not in ids:
        print(f"[ERROR] No tournament ID known for {conference} {year}. "
              f"Add it to CONFERENCE_TOURNAMENT_IDS in this script (see module docstring for how to find it).")
        return False
    tournament_id = ids[year]
    out_dir = DATA_DIR / str(year) / f"{conference}-tourney" / "bout_detail"
    label = f"{year} {conference.replace('_', ' ').title()} Championships"
    return scrape_tournament(tournament_id, out_dir, weights, delay, label=label, reconcile_fn=None, debug=debug)


def main():
    parser = argparse.ArgumentParser(
        description="Scrape timestamped period-by-period conference championship bout detail from TrackWrestling"
    )
    parser.add_argument("--conference", type=str, required=True, choices=sorted(CONFERENCE_TOURNAMENT_IDS.keys()),
                         help="Conference key (must have tournament IDs registered in this script)")
    parser.add_argument("--year", type=int, required=True, help="Tournament year (e.g. 2026)")
    parser.add_argument("--weights", type=str, default=None, help="Comma-separated weight classes (default: all 10)")
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds between requests (default: 1.5)")
    parser.add_argument("--debug", action="store_true", help="Enable verbose per-bout output")
    args = parser.parse_args()

    weights = [int(w.strip()) for w in args.weights.split(",")] if args.weights else WEIGHT_CLASSES
    ok = scrape(args.conference, args.year, weights, args.delay, debug=args.debug)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
