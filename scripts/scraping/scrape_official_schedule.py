#!/usr/bin/env python3
"""
Scrape a college wrestling team's OFFICIAL athletics schedule page (e.g.
gopsusports.com/sports/wrestling/schedule) for a season -- dual meets AND
tournaments, with date, home/away/neutral, location, result (score, time
if unplayed, or placement + team points), TV/streaming info, and a
recap/tickets link.

Unlike the roster page (see scrape_official_roster.py) where most schools
embed the data in the page's Nuxt JSON payload, schedule pages split roughly
into THREE template families, confirmed across 5 schools checked so far:

  A) Penn State (gopsusports.com): server-rendered plain HTML, cards under
     `.schedule-event`. No JSON payload involved at all, no XHR either
     (confirmed via live browser network-request inspection -- zero
     additional requests fire after load).
  B) Nebraska (huskers.com) / Iowa (hawkeyesports.com): also server-rendered
     plain HTML, but a DIFFERENT class family, `.schedule-event-item` --
     and Nebraska/Iowa aren't even identical to each other under that same
     wrapper (Nebraska: `.schedule-event-item-default__opponent-name`;
     Iowa: `.schedule-item-team__heading` free-text after a divider). Only
     the wrapper and a "reasonable subset of these fields" are safe
     assumptions -- parse_events_template_b tries several known sub-
     selectors per field rather than assuming one exact shape.
  C) Oklahoma State (okstate.com) / Ohio State (ohiostatebuckeyes.com):
     genuinely embedded as structured JSON under
     `pinia.schedule.schedules["schedules-wrestling,"].games` -- the
     richest, easiest source when it's there (real opponent id/logo, W/L
     score, TV network name, all as clean typed fields, no HTML guessing).

scrape_schedule() tries A, then B, then C against the same fetched HTML,
and reports which template matched.

Card structure notes (template A, `.schedule-event`):
  - `.schedule-event__venue-text`: "home" / "away" / "neutral"
  - `.schedule-event-date__time` holds two spans: day-of-week, "Mon DD" --
    NO YEAR present anywhere on the card. Inferred from the season string.
  - `.schedule-event-item-team__name`: opponent name for a dual, OR the
    tournament/event name for a tournament session (distinguished by
    whether a second `.schedule-event-item-team__logo-wrapper` exists).
  - `.schedule-events-by-tournament__wrapper` groups multiple sessions
    under one tournament title, also used for a same-day doubleheader
    against two different neutral-site opponents.
  - `.schedule-event-item-result__wrapper` holds EITHER a dual's W/L +
    score, OR a tournament's placement + team points, OR (for a
    not-yet-played event) nothing at all.

Year inference (all templates): none of these cards print a year, only
"Mon DD". Inferred from the season string (e.g. "2026-27"): Aug-Dec ->
first year, Jan-Jul -> second year.

Usage:
  python scripts/scraping/scrape_official_schedule.py --team penn_state \
    --base-url https://gopsusports.com/sports/wrestling/schedule --season 2025-26

Output:
  mt/data/official_schedules/{team}/{season}.json
"""

import argparse
import datetime
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = PROJECT_ROOT / "mt" / "data" / "official_schedules"
TEAM_LIST_PATH = PROJECT_ROOT / "data" / "team_lists" / "ncaa_men" / "2026" / "teams.json"

_KNOWN_TEAM_NAMES_NORM = None


def _normalize_for_team_match(s):
    s = s.lower()
    s = re.sub(r"^university of\s+", "", s)
    s = re.sub(r"\b(university|college)\b", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s


def _known_team_names():
    global _KNOWN_TEAM_NAMES_NORM
    if _KNOWN_TEAM_NAMES_NORM is None:
        try:
            teams = json.loads(TEAM_LIST_PATH.read_text())
            _KNOWN_TEAM_NAMES_NORM = {_normalize_for_team_match(t["name"]) for t in teams}
        except (OSError, json.JSONDecodeError):
            _KNOWN_TEAM_NAMES_NORM = set()
    return _KNOWN_TEAM_NAMES_NORM


def looks_like_known_team(name):
    """Used to gate the tri-meet '/' split (see parse_events_template_d_text)
    -- confirmed necessary: an intra-squad scrimmage name can ALSO contain a
    literal '/' ("Blue / Gold Wrestle Offs" -- Clarion), which isn't two
    real opponent teams at all and must NOT be split, unlike a genuine
    tri-meet ("University of Maryland / Ohio University" -- Morgan State).
    Checks the normalized candidate against the current D1 team list as a
    substring match either direction, since a schedule page's own phrasing
    can be shorter or longer than our canonical name ("NC State" vs "North
    Carolina State", "Chattanooga" vs "UT Chattanooga")."""
    norm = _normalize_for_team_match(name)
    if not norm:
        return False
    for known in _known_team_names():
        if known and (known in norm or norm in known):
            return True
    return False

MONTHS_FIRST_HALF = {"Aug", "Sep", "Oct", "Nov", "Dec"}


def infer_year(month_abbrev, season_slug):
    """'2025-26' + 'Nov' -> 2025; '2025-26' + 'Jan' -> 2026."""
    start_year = int(season_slug.split("-")[0])
    return start_year if month_abbrev in MONTHS_FIRST_HALF else start_year + 1


def to_iso_date(month_abbrev, day, season_slug):
    if not month_abbrev or not day:
        return None
    year = infer_year(month_abbrev[:3], season_slug)
    try:
        return datetime.datetime.strptime(f"{month_abbrev[:3]} {day} {year}", "%b %d %Y").date().isoformat()
    except ValueError:
        return None


def absolutize(url, base_url):
    if url and url.startswith("/"):
        p = urlparse(base_url)
        return f"{p.scheme}://{p.netloc}{url}"
    return url


def parse_result_text(text):
    """Returns (win_loss, score, placement, points, time_str, raw) -- whichever apply."""
    text = (text or "").strip()
    if not text:
        return None, None, None, None, None, None

    m = re.match(r"^(\d+(?:st|nd|rd|th))\s*--\s*([\d.]+)\s*pts\.?$", text)
    if m:
        return None, None, m.group(1), float(m.group(2)), None, None

    m = re.match(r"^(W|L)\s*(?:Win|Loss)?\s*([\d]+-[\d]+)$", text)
    if m:
        return m.group(1), m.group(2), None, None, None, None

    m = re.match(r"^\d{1,2}:\d{2}\s*[AaPp][Mm]", text)
    if m:
        return None, None, None, None, text, None

    return None, None, None, None, None, text


def parse_tv_networks(tv_div):
    if tv_div is None:
        return []
    names = []
    for img in tv_div.select("img[alt]"):
        alt = img.get("alt", "").strip()
        if alt:
            names.append(alt)
    text = tv_div.get_text(" ", strip=True)
    if text and text not in names:
        names.append(text)
    return names


# ── Template A: Penn State-style (.schedule-event) ──────────────────────────

def parse_events_template_a(soup, season_slug, base_url):
    all_events = soup.select(".schedule-event")
    if not all_events:
        return None

    group_by_event_id = {}
    for wrapper in soup.select(".schedule-events-by-tournament__wrapper"):
        title_el = wrapper.select_one(".schedule-events-by-tournament__title")
        title = title_el.get_text(strip=True) if title_el else None
        if title:
            for ev in wrapper.select(".schedule-event"):
                group_by_event_id[id(ev)] = title

    events = []
    for event_el in all_events:
        venue_el = event_el.select_one(".schedule-event__venue-text")
        venue_type = venue_el.get_text(strip=True) if venue_el else "neutral"

        time_el = event_el.select_one(".schedule-event-date__time")
        day_of_week, month_day = None, None
        if time_el:
            spans = time_el.find_all("span")
            if len(spans) >= 2:
                day_of_week = spans[0].get_text(strip=True)
                month_day = spans[1].get_text(strip=True)

        month_abbrev, day = None, None
        if month_day:
            m = re.match(r"([A-Za-z]{3})\w*\s+(\d+)", month_day)
            if m:
                month_abbrev, day = m.group(1), int(m.group(2))

        name_el = event_el.select_one(".schedule-event-item-team__name")
        name = name_el.get_text(strip=True) if name_el else None
        is_dual = len(event_el.select(".schedule-event-item-team__logo-wrapper")) >= 2

        location_el = event_el.select_one(".schedule-event__location-text")
        location = location_el.get_text(strip=True) if location_el else None

        result_wrapper = event_el.select_one(".schedule-event-item-result__wrapper")
        win_loss, score, placement, points, time_str, unrecognized = parse_result_text(
            result_wrapper.get_text(" ", strip=True) if result_wrapper else None
        )

        recap_link = event_el.select_one(".schedule-event-links__link")

        events.append({
            "date": to_iso_date(month_abbrev, day, season_slug),
            "day_of_week": day_of_week,
            "venue_type": venue_type,
            "opponent": name if is_dual else None,
            "event_name": name if not is_dual else None,
            "tournament_group": group_by_event_id.get(id(event_el)),
            "location": location,
            "win_loss": win_loss,
            "score": score,
            "placement": placement,
            "team_points": points,
            "scheduled_time": time_str,
            "unrecognized_result_text": unrecognized,
            "tv_networks": parse_tv_networks(event_el.select_one(".schedule-event__tv-networks")),
            "recap_url": absolutize(recap_link.get("href") if recap_link else None, base_url),
        })
    return events


# ── Template B: Nebraska/Iowa-style (.schedule-event-item) ──────────────────

def _first_text(el, selectors):
    for sel in selectors:
        found = el.select_one(sel)
        if found and found.get_text(strip=True):
            return found.get_text(strip=True)
    return None


def parse_events_template_b(soup, season_slug, base_url):
    all_events = soup.select(".schedule-event-item")
    if not all_events:
        return None

    events = []
    for event_el in all_events:
        classes = event_el.get("class", [])
        venue_type = "home"
        if any("away" in c for c in classes):
            venue_type = "away"
        elif any("neutral" in c for c in classes):
            venue_type = "neutral"
        else:
            venue_label = _first_text(event_el, [".schedule-event-venue__type-label", ".schedule-event-venue__type"])
            if venue_label:
                venue_type = venue_label.strip().lower()

        times = event_el.select(".schedule-event-date time, .schedule-event-date__time time")
        day_of_week = times[0].get_text(strip=True) if len(times) >= 1 else None
        month_day = times[1].get_text(strip=True) if len(times) >= 2 else None
        month_abbrev, day = None, None
        if month_day:
            m = re.match(r"([A-Za-z]{3})\w*\s+(\d+)", month_day)
            if m:
                month_abbrev, day = m.group(1), int(m.group(2))

        # Opponent name: try the labeled-class variant first (Nebraska),
        # else fall back to whatever text follows the "vs."/"at" divider
        # inside the team heading (Iowa) -- excluding the divider word itself.
        name = _first_text(event_el, [".schedule-event-item-default__opponent-name", ".schedule-event-item__opponent-name", ".schedule-item-team__heading", ".schedule-default-event__title"])
        if name:
            for prefix in ("vs.", "at", "vs"):
                if name.startswith(prefix):
                    name = name[len(prefix):].strip()
                    break

        location = _first_text(event_el, [".schedule-event-location", ".schedule-event-item-default__location", ".schedule-event-item__location"])

        result_text = _first_text(event_el, [".schedule-event-item-result__label", ".schedule-event-item-result"])
        win_loss, score, placement, points, time_str, unrecognized = parse_result_text(result_text)

        recap_link = event_el.select_one(".schedule-event-item-links__link, .schedule-event-item-links a")

        events.append({
            "date": to_iso_date(month_abbrev, day, season_slug),
            "day_of_week": day_of_week,
            "venue_type": venue_type,
            "opponent": name,
            "event_name": None,  # template B schools checked so far had no multi-day tournament grouping to distinguish
            "tournament_group": None,
            "location": location,
            "win_loss": win_loss,
            "score": score,
            "placement": placement,
            "team_points": points,
            "scheduled_time": time_str,
            "unrecognized_result_text": unrecognized,
            "tv_networks": [],  # not yet located in this template -- revisit once a TV game is observed
            "recap_url": absolutize(recap_link.get("href") if recap_link else None, base_url),
        })
    return events


# ── Template D: legacy Sidearm -- prefer the plain-text accessibility feed ──
# Confirmed on Cornell, Clarion, Edinboro, Morgan State, Navy, Lock Haven --
# an older, classic Sidearm template family (same vendor as the legacy
# ".sidearm-roster-list-item" ROSTER template scrape_official_roster.py
# already handles). Two sub-variants found:
#   - Most of these schools server-render real `.sidearm-schedule-game-row`
#     markup directly (confirmed duplicated 2x per row on Clarion -- a
#     responsive desktop/mobile DOM pair -- deduped below).
#   - Lock Haven's specific template variant ("sidearm-schedule-template-3")
#     renders the schedule as a client-side `<vue-schedules>` web component
#     instead -- the raw HTML has no game data in it at all, JS required.
#     BUT every school on this whole legacy family also exposes a plain-
#     text accessibility feed (a "Text Format For Braille" link,
#     `/services/schedule_txt.ashx?schedule={id}`) with the exact same data
#     as clean fixed-width columns -- confirmed present even on schools
#     whose HTML rendering DOES work fine, so this is used as the PRIMARY
#     path for the whole template-D family (simpler, avoids the dup-row
#     bug entirely), falling back to the HTML row parser only if no such
#     link is found on the page at all.

def parse_events_template_d_text(html, season_slug, base_url):
    m = re.search(r'href="(/services/schedule_txt\.ashx\?schedule=\d+)"', html)
    if not m:
        return None
    text_url = absolutize(m.group(1), base_url)
    try:
        resp = requests.get(text_url, timeout=20, headers={"User-Agent": "ClaudeBot/1.0 (+https://www.anthropic.com/claude-bot)"})
        text = resp.text
    except requests.RequestException:
        return None

    lines = [l.strip() for l in text.replace("\r", "\n").split("\n")]
    header_idx = next((i for i, l in enumerate(lines) if l.startswith("Date") and "Opponent" in l), None)
    if header_idx is None:
        return None
    header = lines[header_idx]

    col_names = ["Date", "Time", "At", "Opponent", "Location", "Tournament", "Result"]
    try:
        positions = [header.index(c) for c in col_names]
    except ValueError:
        return None

    def slice_field(line, i):
        start = positions[i]
        end = positions[i + 1] if i + 1 < len(positions) else len(line)
        return line[start:end].strip() if start < len(line) else ""

    events = []
    for line in lines[header_idx + 1:]:
        if not line.strip():
            continue
        date_str = slice_field(line, 0)
        m2 = re.match(r"([A-Za-z]{3})\w*\s+(\d+)\s*\(([A-Za-z]+)\)", date_str)
        if not m2:
            continue
        month_abbrev, day, day_of_week = m2.group(1), int(m2.group(2)), m2.group(3)

        time_str = slice_field(line, 1) or None
        venue_type = slice_field(line, 2).lower() or "neutral"
        opponent = slice_field(line, 3) or None
        location = slice_field(line, 4) or None
        tournament = slice_field(line, 5) or None
        result_text = slice_field(line, 6)

        win_loss, score, placement, points, _, unrecognized = parse_result_text(result_text)

        # A tri-meet/quad (multiple opponents faced at one site on one day)
        # renders as a single row with all opponents joined by " / "
        # (confirmed: Morgan State -- "University of Maryland / Ohio
        # University", "American / Liberty", "Virginia Military Institute /
        # Brown", all real multi-team date+location gatherings, not one
        # team with a slash in its own name -- no team in the current D1
        # list has one). Split into one event per opponent rather than
        # keeping the raw joined string, so each is a normal, matchable
        # dual instead of an unresolvable combined name.
        opponent_names = [opponent]
        if opponent and " / " in opponent:
            candidates = [o.strip() for o in opponent.split(" / ")]
            # Only split when BOTH halves independently look like real D1
            # teams -- an intra-squad scrimmage name can also contain a
            # literal "/" ("Blue / Gold Wrestle Offs") without being two
            # real opponents at all, and must be left as one event name.
            if len(candidates) == 2 and all(looks_like_known_team(c) for c in candidates):
                opponent_names = candidates

        for opp in opponent_names:
            events.append({
                "date": to_iso_date(month_abbrev, day, season_slug),
                "day_of_week": day_of_week,
                "venue_type": venue_type,
                "opponent": opp,
                "event_name": None,
                "tournament_group": tournament,
                "location": location,
                "win_loss": win_loss,
                "score": score,
                "placement": placement,
                "team_points": points,
                "scheduled_time": time_str if not (win_loss or score) else None,
                "unrecognized_result_text": unrecognized,
                "tv_networks": [],
                "recap_url": None,
            })
    return events or None


def parse_events_template_d(soup, season_slug, base_url):
    rows = soup.select(".sidearm-schedule-game-row")
    if not rows:
        return None

    events = []
    for row in rows:
        date_el = row.select_one(".sidearm-schedule-game-opponent-date")
        day_of_week, month_day, time_str = None, None, None
        if date_el:
            spans = date_el.find_all("span")
            if len(spans) >= 1:
                m = re.match(r"([A-Za-z]{3})\w*\s+(\d+)\s*\(([A-Za-z]+)\)", spans[0].get_text(strip=True))
                if m:
                    month_day = (m.group(1), int(m.group(2)))
                    day_of_week = m.group(3)
            if len(spans) >= 2:
                time_str = spans[1].get_text(strip=True)

        home_marker = row.select_one(".sidearm-schedule-game-home")
        away_marker = row.select_one(".sidearm-schedule-game-away")
        venue_type = "home" if home_marker else ("away" if away_marker else "neutral")

        name_el = row.select_one(".sidearm-schedule-game-opponent-name")
        name = name_el.get_text(strip=True) if name_el else None

        location_spans = row.select(".sidearm-schedule-game-location span")
        location = " / ".join(s.get_text(strip=True) for s in location_spans if s.get_text(strip=True)) or None

        result_text = None
        result_el = row.select_one(".sidearm-schedule-game-result, .sidearm-schedule-game-score")
        if result_el:
            result_text = result_el.get_text(" ", strip=True)
        win_loss, score, placement, points, _, unrecognized = parse_result_text(result_text)
        # A schedule this far ahead of the season is normally all-upcoming
        # (no result template observed yet on any of the 5 schools checked)
        # -- treat the date-row's own "time" span as the scheduled time
        # only when there's no actual result recorded.
        scheduled_time = time_str if not (win_loss or score) else None

        link_el = row.select_one(".sidearm-schedule-game-opponent-name a, .sidearm-schedule-game-links a")
        link_url = absolutize(link_el.get("href") if link_el else None, base_url)

        events.append({
            "date": to_iso_date(month_day[0] if month_day else None, month_day[1] if month_day else None, season_slug),
            "day_of_week": day_of_week,
            "venue_type": venue_type,
            "opponent": name,
            "event_name": None,
            "tournament_group": None,
            "location": location,
            "win_loss": win_loss,
            "score": score,
            "placement": placement,
            "team_points": points,
            "scheduled_time": scheduled_time,
            "unrecognized_result_text": unrecognized,
            "tv_networks": [],
            "recap_url": link_url,
        })

    # Confirmed (Clarion): this template renders a duplicate DOM copy of
    # every single row (a responsive desktop/mobile pair) -- every event
    # showed up exactly twice with identical (date, opponent, venue_type).
    # Dedupe on that triple, keeping first occurrence, rather than assuming
    # a real doubleheader can't share all three (checked: Cornell's real
    # same-day doubleheader on Dec 20 has two DIFFERENT opponents, so this
    # key doesn't accidentally collapse a genuine case).
    seen = set()
    deduped = []
    for e in events:
        key = (e["date"], e["opponent"], e["venue_type"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)
    return deduped


# ── Template C: pinia-embedded JSON (Oklahoma State / Ohio State) ───────────

WRAP_TAGS = {"ShallowReactive", "Reactive", "ShallowRef", "Ref", "Raw"}


def resolve_nuxt_payload(arr):
    n = len(arr)
    cache = {}

    def resolve(i, depth=0):
        if i in cache:
            return cache[i]
        if depth > 200 or not isinstance(i, int) or i < 0 or i >= n:
            return None
        val = arr[i]
        if isinstance(val, dict):
            out = {}
            cache[i] = out
            for k, v in val.items():
                out[k] = resolve(v, depth + 1) if isinstance(v, int) else v
            return out
        if isinstance(val, list):
            if val and isinstance(val[0], str) and val[0] in WRAP_TAGS and len(val) == 2:
                inner = resolve(val[1], depth + 1)
                cache[i] = inner
                return inner
            if val and isinstance(val[0], str) and val[0] == "Set" and len(val) == 2 and isinstance(val[1], list):
                out = [resolve(x, depth + 1) for x in val[1]]
                cache[i] = out
                return out
            out = []
            cache[i] = out
            for x in val:
                out.append(resolve(x, depth + 1) if isinstance(x, int) else x)
            return out
        cache[i] = val
        return val

    return resolve(0)


def parse_events_template_c(html, season_slug):
    m = re.search(r'<script type="application/json"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        return None
    try:
        root = resolve_nuxt_payload(json.loads(m.group(1)))
    except (json.JSONDecodeError, RecursionError):
        return None

    schedules = ((root or {}).get("pinia") or {}).get("schedule", {}).get("schedules", {})
    games = None
    for key, val in schedules.items():
        if "wrestling" in key.lower() and isinstance(val, dict) and val.get("games"):
            games = val["games"]
            break
    if not games:
        return None

    events = []
    for g in games:
        dt = g.get("date")
        date_iso, time_str = None, g.get("time")
        if dt:
            date_iso = dt.split("T")[0]

        venue_type = {"H": "home", "A": "away", "N": "neutral"}.get(g.get("location_indicator"), "neutral")
        opponent = (g.get("opponent") or {}).get("title")

        result = g.get("result") or {}
        win_loss, score = None, None
        if result.get("status") in ("W", "L"):
            win_loss = result["status"]
            ts, os_ = result.get("team_score"), result.get("opponent_score")
            if ts is not None and os_ is not None:
                score = f"{ts}-{os_}"

        media = g.get("media") or {}
        tv_networks = [n for n in [media.get("tv")] if n]

        recap = ((media.get("preview") or {}) if result.get("status") not in ("W", "L") else (result.get("recap") or {}))
        recap_url = recap.get("url") if isinstance(recap, dict) else None

        events.append({
            "date": date_iso,
            "day_of_week": None,
            "venue_type": venue_type,
            "opponent": opponent,
            "event_name": None,
            "tournament_group": None,
            "location": g.get("location"),
            "win_loss": win_loss,
            "score": score,
            "placement": None,
            "team_points": None,
            "scheduled_time": None if win_loss else time_str,
            "unrecognized_result_text": None,
            "tv_networks": tv_networks,
            "recap_url": recap_url,
        })
    return events


# ── Driver ───────────────────────────────────────────────────────────────────

def title_confirms_season(html, season_slug):
    """Guards against the bare-URL fallback silently serving whatever
    season the site currently defaults to -- confirmed necessary (Penn
    State): its season-suffixed URLs 404/no-events for 2026-27 before that
    season is posted, so scrape_schedule() falls back to the bare URL,
    which returns 200 with a full, real-looking schedule -- but it's last
    season's, still labeled "2025-26" in the page's own <title>, not the
    requested season at all. Every template's page carries a real season
    string in <title> (confirmed across all templates checked), so this
    check applies universally rather than per-template.

    Returns True if the title's season matches (or no season was
    requested), False if it clearly shows a DIFFERENT season, None if no
    season string could be found in the title at all (fail open -- don't
    reject a page just because this specific check couldn't parse it)."""
    if season_slug is None:
        return True
    m = re.search(r"<title>[^<]*?(\d{4})-(\d{2,4})\b", html)
    if not m:
        return None
    title_season = f"{m.group(1)}-{m.group(2)[-2:]}"
    return title_season == season_slug


def scrape_schedule(base_url, season_slug, debug=False):
    """Tries every URL candidate FULLY (fetch AND parse), not just until the
    first non-404 -- confirmed necessary (Ohio State): a "/season/{slug}"
    URL can return 200 with a differently-rendered page that's missing the
    embedded schedule data entirely, while the bare base URL (already
    showing the right season by default) has it. Same trap documented in
    scrape_official_roster.py's scrape_season() for roster pages."""
    session = requests.Session()
    session.headers["User-Agent"] = "ClaudeBot/1.0 (+https://www.anthropic.com/claude-bot)"

    # Season-suffixed URLs tried first (correct for a PAST season, where the
    # bare URL would silently show whatever's current instead); bare URL
    # last as a fallback for the case just hit on Ohio State, where the
    # suffixed URL 200s but is missing the embedded data outright.
    url_candidates = [f"{base_url}/season/{season_slug}", f"{base_url}/{season_slug}", base_url] if season_slug else [base_url]

    last_error = "not_found"
    for url in url_candidates:
        resp = session.get(url, timeout=20)
        if resp.status_code == 404:
            continue
        html, final_url = resp.text, resp.url

        season_ok = title_confirms_season(html, season_slug)
        if season_ok is False:
            last_error = "wrong_season_not_posted_yet"
            continue

        soup = BeautifulSoup(html, "html.parser")

        for template_name, fn in [
            ("A", lambda: parse_events_template_a(soup, season_slug, base_url)),
            ("B", lambda: parse_events_template_b(soup, season_slug, base_url)),
            ("C", lambda: parse_events_template_c(html, season_slug)),
            ("D-text", lambda: parse_events_template_d_text(html, season_slug, base_url)),
            ("D-html", lambda: parse_events_template_d(soup, season_slug, base_url)),
        ]:
            events = fn()
            if events:
                if debug:
                    print(f"  [template {template_name}, url={url}]")
                    for e in events:
                        print(f"  {e['date']} {e['venue_type']:8s} {e['opponent'] or e['event_name']}")
                return {"season": season_slug, "schedule_url": final_url, "template": template_name, "events": events}, None
        last_error = "no_events_found"

    return None, last_error


def main():
    parser = argparse.ArgumentParser(description="Scrape a college wrestling team's official athletics schedule page")
    parser.add_argument("--team", required=True, help="Team slug for output directory, e.g. penn_state")
    parser.add_argument("--base-url", required=True, help="Schedule page base URL, e.g. https://gopsusports.com/sports/wrestling/schedule")
    parser.add_argument("--season", required=True, help="Season slug, e.g. 2025-26")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    data, error = scrape_schedule(args.base_url, args.season, debug=args.debug)
    if error:
        print(f"[SKIP] {error}")
        return

    out_dir = OUT_DIR / args.team
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.season}.json"
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"[OK] template {data['template']}: {len(data['events'])} events saved: {out_path}")


if __name__ == "__main__":
    main()
