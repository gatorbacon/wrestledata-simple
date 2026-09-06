#!/usr/bin/env python3
"""
Scrape a college wrestling team's OFFICIAL athletics roster page (e.g.
gopsusports.com) for a season, capturing what TrackWrestling scrapes don't:
class/eligibility year (Fr/So/Jr/Sr/Grad), hometown, high school, and a
current-season photo per wrestler.

This is NOT a competitor-data scrape -- every field here is public
information the school itself publishes about its own athletes. (Explicitly
NOT sourced from wrestlestat.com or similar aggregators -- see CLAUDE.md/
project notes on why that's off-limits.)

Site platform: most D1 athletics sites checked so far (Penn State, Iowa;
likely others on the same "Sidearm 6" template -- unconfirmed for other
vendors like PrestoSports/WMT) are Nuxt.js apps that embed their page data
as a <script type="application/json"> blob using Nuxt's payload
serialization (devalue-style: a flat array where objects/arrays reference
other elements by index, and special two-element arrays like
["ShallowReactive", N] or ["Set", [...]] wrap a referenced value). This
script implements a minimal resolver for that format -- see
resolve_nuxt_payload() -- then finds the roster's player list structurally
(find_roster_entries(), matching by shape, not a specific container key
name, since PSU/Iowa nest it under root["data"] while other sites may not).

Confirmed variant: Oklahoma State runs the same Nuxt shell but its payload
resolves to genuinely empty page data -- the roster widget there is a
classic server-rendered "s-person-card" component, not a JS-hydrated one.
parse_html_roster() is a BeautifulSoup fallback for that case, used
automatically when find_roster_entries() comes up empty. Expect more site
variants as more schools get checked.

Usage:
  python scripts/scraping/scrape_official_roster.py --team penn_state \
    --base-url https://gopsusports.com/sports/wrestling/roster \
    --seasons 2025-26,2024-25,2026-27

Output:
  mt/data/official_rosters/{team}/{season}.json
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = PROJECT_ROOT / "mt" / "data" / "official_rosters"

WRAP_TAGS = {"ShallowReactive", "Reactive", "ShallowRef", "Ref", "Raw"}


def resolve_nuxt_payload(arr):
    """
    Resolves a Nuxt devalue-style payload array into plain Python data.

    The root's shape varies by site/Nuxt config -- confirmed two variants:
    Penn State/Iowa have arr[0] == ["ShallowReactive", 1] (a wrap-tag
    pointing at the real root); Oklahoma State has arr[0] be the root dict
    directly, with page data under "state" instead of "data". resolve(0)
    handles both, since a wrap-tag at any index transparently unwraps.
    """
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
            if val and isinstance(val[0], str) and val[0] == "Date" and len(val) == 2:
                cache[i] = val[1]
                return val[1]
            out = []
            cache[i] = out
            for x in val:
                out.append(resolve(x, depth + 1) if isinstance(x, int) else x)
            return out
        cache[i] = val
        return val

    return resolve(0)


def fetch_page(session, url, debug=False):
    """Returns (html_text, resolved_nuxt_root_or_None, error_or_None, final_url)."""
    resp = session.get(url, timeout=20)
    if resp.status_code == 404:
        return None, None, "not_found", resp.url
    resp.raise_for_status()
    m = re.search(r'<script type="application/json"[^>]*>(.*?)</script>', resp.text, re.DOTALL)
    if not m:
        if debug:
            print(f"    [WARN] no application/json payload found in {url}")
        return resp.text, None, None, resp.url
    arr = json.loads(m.group(1))
    return resp.text, resolve_nuxt_payload(arr), None, resp.url


def find_roster_entries(node, depth=0, seen=None):
    """
    Recursively searches the resolved payload for the roster's player list,
    identified structurally (a list of dicts each shaped like {"player": {...},
    "class_level"/"player_position": {...}}) rather than by a specific
    container key name -- confirmed necessary since Penn State/Iowa nest it
    under root["data"]["roster-<id>-players-list-..."] while Oklahoma State
    nests it elsewhere under root["state"]. Structural matching is robust to
    whatever a given school's site happens to call the container.
    """
    if seen is None:
        seen = set()
    if id(node) in seen or depth > 12:
        return None
    seen.add(id(node))

    if isinstance(node, list):
        if node and all(isinstance(x, dict) and "player" in x for x in node):
            return node
        for item in node:
            found = find_roster_entries(item, depth + 1, seen)
            if found:
                return found
        return None
    if isinstance(node, dict):
        for v in node.values():
            found = find_roster_entries(v, depth + 1, seen)
            if found:
                return found
    return None


def extract_photo_url(photo_dict):
    if not photo_dict:
        return None
    return photo_dict.get("url")


WEIGHT_LIKE_RE = re.compile(r"^\d{2,3}(\s*/\s*\d{2,3})*(\s*lbs\.?)?$", re.IGNORECASE)


def extract_weight(entry, position):
    """
    player_position is meant to hold the weight class (e.g. "133", "157
    lbs.") but at least one program's older-season data has it corrupted
    to the player's own name instead (confirmed: Iowa 2022-23). Only trust
    it if it actually looks like a weight class; otherwise fall back to
    the entry's raw numeric `weight` field.
    """
    candidate = position.get("abbreviation") or position.get("name")
    if candidate and WEIGHT_LIKE_RE.match(candidate.strip()):
        return candidate
    raw_weight = entry.get("weight")
    if isinstance(raw_weight, (int, float)):
        return f"{raw_weight:g} lbs."
    return None  # confirmed case (Iowa, Aiden Riggins 2022-23): no usable weight anywhere in the source data


def parse_roster_entry(entry, base_url):
    player = entry.get("player") or {}
    class_level = entry.get("class_level") or player.get("class_level") or {}
    position = entry.get("player_position") or player.get("player_position") or {}
    slug = player.get("slug")
    return {
        "player_id": player.get("id"),
        "name": player.get("full_name"),
        "first_name": player.get("first_name"),
        "last_name": player.get("last_name"),
        "class_level": class_level.get("name"),
        "weight": extract_weight(entry, position),
        "hometown": player.get("hometown"),
        "high_school": player.get("high_school"),
        "previous_school": player.get("previous_school"),
        "photo_url": extract_photo_url(entry.get("photo")) or extract_photo_url(player.get("master_photo")),
        "bio_url": f"{base_url}/player/{slug}" if slug else None,
        "slug": slug,
    }


WEIGHT_LIKE_HTML_RE = re.compile(r"^(hwt|\d{2,3})(\s*/\s*(hwt|\d{2,3}))*(\s*lbs\.?)?$", re.IGNORECASE)


def parse_html_roster(html, base_url):
    """
    Fallback for sites whose roster widget renders straight to server-side
    HTML instead of embedding a JS data payload (confirmed: Oklahoma State --
    its Nuxt payload resolves but is genuinely empty; the roster is a
    classic Sidearm "s-person-card" component). Filters cards to ones with a
    weight-class-shaped "Custom Field 1" value to exclude coaching staff,
    who share the same card markup with no weight.

    NOTE: unlike the JSON path's `player.id` (confirmed stable across a
    wrestler's seasons at one school for Penn State/Iowa), the numeric ID in
    this card's bio URL (.../roster/{slug}/{id}) has NOT been verified
    stable across seasons here -- treat it as provisional until checked.
    """
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".s-person-card.s-person-card--list, .s-person-card")
    players = []
    for card in cards:
        h3 = card.find("h3")
        if not h3:
            continue
        name = h3.get_text(strip=True)

        fields = {}
        for sr in card.select(".sr-only"):
            label = sr.get_text(strip=True)
            full_text = sr.parent.get_text(strip=True)
            fields[label] = full_text[len(label):].strip()

        # Filtering staff out by requiring a weight field was wrong (confirmed:
        # NC State 2022-23) -- real wrestlers legitimately have no weight yet
        # (true freshmen with no confirmed weight class), and requiring one
        # silently dropped them along with actual staff. "Academic Year" is
        # the reliable discriminator instead: every wrestler card has it
        # (even weightless ones); staff cards (coaches, support staff) never
        # do (confirmed: NC State's coaching staff cards have no Academic
        # Year field at all, just a bio link and sometimes a phone number).
        if not fields.get("Academic Year"):
            continue  # no Academic Year -- this is a coach/staff card, not a wrestler

        # The weight field's label is inconsistent even across seasons on
        # the SAME site: confirmed "Weight" (Oklahoma State, some seasons),
        # "Custom Field 1" (Oklahoma State/NC State, other seasons -- generic
        # CMS label), and "Position" (Ohio State). Try all known variants.
        # Missing entirely is valid (see above) -- becomes weight=None below.
        weight_raw = fields.get("Weight") or fields.get("Custom Field 1") or fields.get("Position")
        weight = weight_raw if weight_raw and WEIGHT_LIKE_HTML_RE.match(weight_raw.strip()) else None

        link = card.select_one('a[data-test-id="s-person-details__personal-single-line-person-link"]') or card.find("a", href=True)
        href = link.get("href") if link else None
        player_id, slug = None, None
        if href:
            m = re.search(r"/roster/([^/]+)/(\d+)", href)
            if m:
                slug, player_id = m.group(1), int(m.group(2))

        img = card.find("img")
        photo_url = img.get("src") if img else None

        previous_school_raw = fields.get("Previous School")
        previous_school = None
        if previous_school_raw:
            previous_school = re.sub(r"^Last College:\s*", "", previous_school_raw).strip()

        players.append({
            "player_id": player_id,
            "name": name,
            "first_name": None,
            "last_name": None,
            "class_level": fields.get("Academic Year"),
            "weight": weight,
            "hometown": fields.get("Hometown"),
            "high_school": fields.get("Last School"),
            "previous_school": previous_school,
            "photo_url": photo_url,
            "bio_url": f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}{href}" if href and href.startswith("/") else href,
            "slug": slug,
        })
    return dedupe_html_players(players)


def parse_legacy_sidearm_list_roster(html, base_url):
    """
    Second fallback, for an older/plainer Sidearm template than
    parse_html_roster()'s Vue "s-person-card" (confirmed: Wyoming -- its
    roster page has neither a JS data payload nor s-person-card markup;
    it's a classic server-rendered <li class="sidearm-roster-list-item">
    list, one per wrestler, with well-labeled sub-classes for every field
    directly -- no ambiguous "sr-only" label variants to sort through, and
    no coaching-staff cards in this same list at all (they're a separate
    "Coaching Staff" page/section), so no staff-filtering is needed here.
    """
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select(".sidearm-roster-list-item")
    players = []
    for item in items:
        link = item.select_one(".sidearm-roster-list-item-link")
        href = link.get("href") if link else None
        player_id, slug = None, None
        if href:
            m = re.search(r"/roster/([^/]+)/(\d+)", href)
            if m:
                slug, player_id = m.group(1), int(m.group(2))

        def text_of(cls):
            el = item.select_one(cls)
            return el.get_text(strip=True) if el else None

        name = text_of(".sidearm-roster-list-item-name")
        if not name:
            continue
        name = re.sub(r"\s+", " ", name)  # confirmed: double-space between first/last name

        img = item.select_one(".sidearm-roster-list-item-photo-img")
        photo_src = img.get("src") if img else None
        photo_url = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}{photo_src}" if photo_src and photo_src.startswith("/") else photo_src

        players.append({
            "player_id": player_id,
            "name": name,
            "first_name": None,
            "last_name": None,
            "class_level": text_of(".sidearm-roster-list-item-year"),
            "weight": text_of(".sidearm-roster-list-item-position"),
            "hometown": text_of(".sidearm-roster-list-item-hometown"),
            "high_school": text_of(".sidearm-roster-list-item-highschool"),
            "previous_school": None,
            "photo_url": photo_url,
            "bio_url": f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}{href}" if href and href.startswith("/") else href,
            "slug": slug,
        })
    return dedupe_html_players(players)


def parse_roster_list_item(html, base_url):
    """
    Fourth fallback, for a newer Sidearm template distinct from both
    parse_html_roster()'s "s-person-card" and parse_legacy_sidearm_list_
    roster()'s older ".sidearm-roster-list-item" (confirmed: Little Rock/
    lrtrojans.com -- ".roster-list-item" cards, with fields under
    ".roster-player-list-profile-field--{class-level,height,hometown,
    high-school,previous-school,weight}"). Real wrestlers are discriminated
    from coaching-staff cards (same markup) by the presence of a weight
    field -- unlike parse_html_roster()'s "Academic Year" discriminator,
    confirmed safe here because this template's Nuxt payload consistently
    labels a weightless true-freshman card with an explicit (empty-string)
    weight field rather than omitting it, so no legitimate wrestler gets
    misclassified as staff.

    Written primarily to parse a *saved* page snapshot (ingest_manual_
    roster_webarchive.py) rather than a live fetch: this template lazy-loads
    its roster list client-side, so the embedded Nuxt JSON payload a live
    fetch would resolve (find_roster_entries()) reflects only the page's
    initial SSR state and undercounts once a real browser has scrolled/
    hydrated further entries into the DOM -- confirmed on Little Rock's
    2020-21 season, where the JSON payload had 20 players but this template's
    rendered card markup (present in the same saved HTML) had the true 30.
    """
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".roster-list-item")
    players = []
    for card in cards:
        title = card.select_one(".roster-list-item__title")
        if not title:
            continue
        name = title.get_text(strip=True)

        def field(cls):
            el = card.select_one(f".roster-player-list-profile-field--{cls}")
            return el.get_text(strip=True) if el else None

        weight = field("weight")
        if not weight:
            continue  # no weight field at all -- coaching staff/support card, not a wrestler

        link = title if title.name == "a" else card.select_one("a[href]")
        href = link.get("href") if link else None
        slug = href.rstrip("/").rsplit("/", 1)[-1] if href else None

        img = card.find("img")
        photo_url = img.get("src") if img else None

        players.append({
            "player_id": None,
            "name": name,
            "first_name": None,
            "last_name": None,
            "class_level": field("class-level"),
            "weight": weight,
            "hometown": field("hometown"),
            "high_school": field("high-school"),
            "previous_school": field("previous-school"),
            "photo_url": photo_url,
            "bio_url": f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}{href}" if href and href.startswith("/") else href,
            "slug": slug,
        })
    return dedupe_html_players(players)


def extract_legacy_sidearm_weight(position_div):
    """
    The ".sidearm-roster-player-position" div's internal markup varies
    school-to-school even though every one of these schools shares the
    exact same "sidearm-roster-player-container" template (all confirmed
    across this batch: Bellarmine, Bloomsburg, Clarion, CSU Bakersfield,
    Harvard, Hofstra, LIU, Mercyhurst, Campbell, VMI). Blindly concatenating
    the whole div's text (the original approach) silently corrupted the
    weight field several different ways:
      - Clarion/CSU Bakersfield/Harvard/Hofstra/VMI: a ".text-bold" span
        wraps TWO "position-long-short" child spans holding the responsive
        small-screen/medium-screen copies of the SAME value (occasionally
        NOT byte-identical, e.g. VMI's "133 lbs" vs "133" -- take the first
        either way) -- concatenating both produced "149149"-style doubles.
      - Bloomsburg/Morgan State/CSU Bakersfield/VMI: a sibling
        ".sidearm-roster-player-height" span holds the wrestler's HEIGHT
        immediately next to the weight -- concatenating it on produced
        "149 lbs5'8\""-style corruption.
      - Bellarmine: no ".text-bold" at all; the weight instead lives in the
        generic-CMS-labeled ".sidearm-roster-player-custom2", again next to
        a ".sidearm-roster-player-height" sibling to exclude.
      - LIU/Campbell: an explicit ".sidearm-roster-player-weight" span --
        the cleanest case, checked first.
      - Mercyhurst: some wrestlers (true freshmen, no confirmed weight yet)
        have ONLY the height span and no weight-bearing element anywhere --
        correctly returns None rather than misreporting height as weight.
      - Penn: this template has NO separate staff/coaching-staff list --
        student managers share the exact same card markup and get their
        role name ("Student Manager") stuffed into ".sidearm-roster-
        player-custom2", the same slot a wrestler's weight would occupy.
        Returning it unvalidated leaked "Student Manager" into the weight
        field as a literal string. Validate against WEIGHT_LIKE_HTML_RE
        before returning; a non-weight-shaped value becomes None here, and
        the caller uses the pre-validation raw text to drop the entry
        entirely (a manager isn't a wrestler with unknown weight, they're
        not a wrestler at all).
    Priority order below always extracts exactly one value and never
    touches the height span. Returns (raw_text, validated_weight).
    """
    if position_div is None:
        return None, None
    weight_span = position_div.select_one(".sidearm-roster-player-weight")
    if weight_span:
        candidates = [weight_span.get_text(strip=True)]
    else:
        text_bold = position_div.select_one(".text-bold")
        if text_bold:
            # confirmed (App State): the long/short pair isn't always two
            # equivalent numeric spellings (VMI's "133 lbs" vs "133") -- for
            # the heavyweight class it can be a WORD ("Heavyweight") paired
            # with an abbreviation ("HWT"), and DOM order isn't consistent
            # about which comes first. Try every span, not just the first.
            spans = text_bold.select(".sidearm-roster-player-position-long-short")
            candidates = [s.get_text(strip=True) for s in spans] or [text_bold.get_text(strip=True)]
        else:
            custom = position_div.select_one(".sidearm-roster-player-custom2, .sidearm-roster-player-custom1")
            candidates = [custom.get_text(strip=True)] if custom else []
    raw = candidates[0] if candidates else None
    weight = next((c for c in candidates if c and WEIGHT_LIKE_HTML_RE.match(c.strip())), None)
    return raw, weight


STAFF_ROLE_RE = re.compile(
    r"student manager|team manager|head coach|assistant coach|associate head coach|"
    r"volunteer coach|director of|video coordinator|strength (and conditioning )?coach|"
    r"athletic trainer",
    re.IGNORECASE,
)


def parse_legacy_sidearm_player_roster(html, base_url):
    """
    Third fallback -- yet another classic-Sidearm naming convention
    (confirmed: Cornell), <div class="sidearm-roster-player-container">
    per wrestler with "sidearm-roster-player-*" sub-classes, distinct from
    both parse_html_roster()'s Vue "s-person-card" and
    parse_legacy_sidearm_list_roster()'s "sidearm-roster-list-item-*".
    Each container legitimately holds TWO nested academic-year/hometown
    blocks (a "hide-on-large" mobile copy and a "hide-on-medium-down"
    desktop copy of the same data, abbreviated vs full class-level text
    respectively) -- select_one() naturally takes the first (abbreviated)
    one, which is fine, just note it's not a duplicate-card situation like
    dedupe_html_players() handles for the Vue template.
    Photos are lazy-loaded: the real URL is in `data-src`, not `src`.
    """
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select(".sidearm-roster-player-container")
    players = []
    for item in items:
        link = item.select_one('.sidearm-roster-player-name a[href*="/roster/"]')
        href = link.get("href") if link else None
        player_id, slug = None, None
        if href:
            m = re.search(r"/roster/([^/]+)/(\d+)", href)
            if m:
                slug, player_id = m.group(1), int(m.group(2))

        def text_of(cls):
            el = item.select_one(cls)
            return el.get_text(strip=True) if el else None

        name = link.get_text(strip=True) if link else None
        if not name:
            continue

        raw_weight, weight = extract_legacy_sidearm_weight(item.select_one(".sidearm-roster-player-position"))
        if raw_weight and STAFF_ROLE_RE.search(raw_weight):
            continue  # role name (e.g. "Student Manager") in the weight slot -- not a wrestler

        img = item.select_one("img")
        photo_src = (img.get("data-src") or img.get("src")) if img else None
        photo_src = photo_src.split("?")[0] if photo_src else None
        photo_url = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}{photo_src}" if photo_src and photo_src.startswith("/") else photo_src

        players.append({
            "player_id": player_id,
            "name": name,
            "first_name": None,
            "last_name": None,
            "class_level": text_of(".sidearm-roster-player-academic-year"),
            "weight": weight,
            "hometown": text_of(".sidearm-roster-player-hometown"),
            "high_school": text_of(".sidearm-roster-player-highschool"),
            "previous_school": None,
            "photo_url": photo_url,
            "bio_url": f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}{href}" if href and href.startswith("/") else href,
            "slug": slug,
        })
    return dedupe_html_players(players)


def _photo_width(photo_url):
    if not photo_url:
        return 0
    m = re.search(r"width=(\d+)", photo_url)
    return int(m.group(1)) if m else 0


def dedupe_html_players(players):
    """
    Confirmed (Oklahoma State, 2025-26, Jax Forrest): some seasons render
    two nearly-identical cards per wrestler -- likely a responsive
    mobile/desktop layout pair matching the same CSS selector -- differing
    only in photo resolution. Dedupe by player_id (falling back to
    name+bio_url when player_id is missing).

    Confirmed separately (Michigan State, 2025-26, Cam Adams): the
    mobile/desktop pair can ALSO differ in which fields render at all, not
    just photo resolution -- one copy had "Custom Field 1" (weight: "165"),
    the other omitted it entirely. Preferring by photo width alone let the
    weight-less copy win, silently dropping real weight data wholesale
    across a school. Prefer whichever duplicate actually has a weight value
    first; only fall back to photo-width as a tiebreaker when both (or
    neither) have one.
    """
    best = {}
    order = []
    for p in players:
        key = p["player_id"] if p["player_id"] is not None else (p["name"], p["bio_url"])
        if key not in best:
            best[key] = p
            order.append(key)
            continue
        current = best[key]
        if current["weight"] is None and p["weight"] is not None:
            best[key] = p
        elif (current["weight"] is None) == (p["weight"] is None) and _photo_width(p["photo_url"]) > _photo_width(current["photo_url"]):
            best[key] = p
    return [best[k] for k in order]


def scrape_season(session, base_url, season_slug, debug=False):
    """
    Three confirmed URL schemes for a past season: Penn State/Iowa use
    "{base}/season/{slug}"; Oklahoma State uses "{base}/{slug}" directly
    (its "/season/" path 404s); Lehigh uses "{base}/{full-4-digit-slug}"
    (e.g. "2025-2026", not "2025-26" -- confirmed via its own season
    dropdown, which also displays full years unlike every other site
    checked so far). Try all three rather than requiring the caller to
    know which -- this is exactly the kind of per-school variance we
    don't want to have to rediscover each time.
    """
    if season_slug is None:
        url_candidates = [base_url]
    else:
        full_year_slug = re.sub(r"^(\d{4})-(\d{2})$", lambda m: f"{m.group(1)}-{int(m.group(1)[:2] + m.group(2))}", season_slug)
        url_candidates = [
            f"{base_url}/season/{season_slug}",
            f"{base_url}/{season_slug}",
            f"{base_url}/{full_year_slug}",
        ]

    # Try every candidate URL fully (fetch AND parse), not just until the
    # first non-404 -- confirmed necessary: Lehigh's short-form URL
    # ("/2025-26") returns 200 with an empty/unrendered placeholder page
    # (unfilled "@season" template title, zero roster cards), which would
    # otherwise get mistaken for "found the page, just no roster data" and
    # stop before ever trying the URL that actually has the roster
    # ("/2025-2026", full 4-digit year).
    html, root, entries, html_players = None, None, None, None
    last_error = "not_found"
    for url in url_candidates:
        html, root, error, final_url = fetch_page(session, url, debug=debug)
        if error == "not_found":
            continue
        if html is None:
            last_error = error or "unknown_error"
            continue
        # Confirmed (Edinboro/gofightingscots.com): the short-form season
        # URL ("{base}/2022-23") 301-redirects silently to the bare
        # current-season roster URL instead of 404ing -- requests follows
        # it transparently, so without this check we'd "successfully" parse
        # a full page of real-looking roster data and stop, never trying
        # the full-year-slug candidate that actually has that season's
        # roster. If we asked for a specific season (not "current") and got
        # redirected clean back to base_url (no season segment survived at
        # all), treat it the same as not_found so the loop keeps trying
        # other candidates instead of silently mislabeling current-season
        # data as the requested season.
        if season_slug is not None and final_url.rstrip("/") == base_url.rstrip("/"):
            last_error = "redirected_to_current"
            continue
        entries = find_roster_entries(root) if root is not None else None
        if entries:
            break
        html_players = parse_html_roster(html, base_url)
        if html_players:
            break
        html_players = parse_legacy_sidearm_list_roster(html, base_url)
        if html_players:
            break
        html_players = parse_legacy_sidearm_player_roster(html, base_url)
        if html_players:
            break
        html_players = parse_roster_list_item(html, base_url)
        if html_players:
            break
        last_error = "no_players_found"
    else:
        return None, last_error

    if entries:
        roster_meta = (entries[0].get("roster") or {}) if entries else {}
        season_name = ((roster_meta.get("season") or {}).get("name"))
        players = [parse_roster_entry(e, base_url) for e in entries]
        return {"season": season_name or season_slug, "team_roster_url": url, "players": players}, None

    if html_players:
        if debug:
            print(f"    [INFO] used HTML fallback parser (no JS data payload found)")
        # Prefer the <title> tag (confirmed: Oklahoma State includes the
        # season there, as "YYYY-YY"; Lehigh does too but as full
        # "YYYY-YYYY" -- normalize that back to "YYYY-YY"). Michigan's
        # title omits the season entirely, so fall back to the
        # season-selector widget's rendered "selected" value.
        title_match = re.search(r"<title>\s*(\d{4})-(\d{2,4})\b", html)
        select_match = re.search(r'selected-option__text">\s*(\d{4})-(\d{2,4})', html)
        m = title_match or select_match
        season_name = f"{m.group(1)}-{m.group(2)[-2:]}" if m else season_slug
        return {"season": season_name, "team_roster_url": url, "players": html_players}, None

    return None, "no_players_found"


def main():
    parser = argparse.ArgumentParser(description="Scrape a college team's official athletics roster page")
    parser.add_argument("--team", required=True, help="Team slug for output directory, e.g. penn_state")
    parser.add_argument("--base-url", required=True, help="Roster page base URL, e.g. https://gopsusports.com/sports/wrestling/roster")
    parser.add_argument("--seasons", required=True, help="Comma-separated season slugs (e.g. 2025-26,2024-25) or 'current' for the base URL's default season")
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    session = requests.Session()
    # Identify honestly. Confirmed necessary for at least one site
    # (Edinboro/gofightingscots.com): its WAF 404s the default
    # "python-requests/x.y" UA specifically while serving normal 200s to
    # curl's UA and to an honest bot UA -- not a robots.txt disallow (its
    # robots.txt is the same generic Sidearm-network policy as every other
    # school here), just a basic UA-string block. Setting a real identifying
    # UA fixes it without pretending to be a browser.
    session.headers["User-Agent"] = "ClaudeBot/1.0 (+https://www.anthropic.com/claude-bot)"
    out_dir = OUT_DIR / args.team
    out_dir.mkdir(parents=True, exist_ok=True)

    season_slugs = [s.strip() for s in args.seasons.split(",")]
    for i, season_slug in enumerate(season_slugs):
        is_current = season_slug.lower() == "current"
        print(f"\nSeason {season_slug}:")
        data, error = scrape_season(session, args.base_url, None if is_current else season_slug, debug=args.debug)
        if error:
            print(f"   [SKIP] {error}")
            continue
        out_name = data["season"].replace("/", "-") if data["season"] else season_slug
        out_path = out_dir / f"{out_name}.json"
        out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        print(f"   [OK] {len(data['players'])} players saved: {out_path}")
        if i < len(season_slugs) - 1:
            time.sleep(args.delay)


if __name__ == "__main__":
    main()
