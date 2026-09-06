#!/usr/bin/env python3
"""
Batch-ingest manually-saved Safari .webarchive captures of a school's roster
page (data/_tmp/) -- a strictly better source than the PDF path
(parse_manual_roster_pdf.py): a .webarchive is a binary plist wrapping the
page's real HTML plus every embedded resource (images included), so it
parses with the EXACT same BeautifulSoup logic scrape_official_roster.py
uses for a live fetch, rather than reconstructing fields from PDF text
layout. Real player_id/slug/bio_url come through when the markup has them;
headshot images come through as actual embedded bytes (matched by URL to
each player's photo_url), even when the live URL now 302s (confirmed on
Wyoming's 2012 capture -- the site no longer serves that era's photos, but
the bytes are still sitting in the archive).

Expects files in data/_tmp/ named "{label} Wrestling Roster - {School Name}.webarchive"
where {label} is whatever single/range year the school's own site uses in its
URL (e.g. gowyo.com labels a roster page by a single year, "2012"). Pass
--season on the CLI to control the OUTPUT filename (this repo's convention:
season 2012 tournament -> roster file "2011-12.json"), since a single-year
site label is ambiguous about which convention it follows.

Usage:
  .venv/bin/python scripts/scraping/ingest_manual_roster_webarchive.py \\
      --team wyoming --season 2011-12 \\
      "data/_tmp/2012 Wrestling Roster - University of Wyoming Athletics.webarchive"
"""
import argparse
import json
import plistlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from scrape_official_roster import (
    parse_html_roster,
    parse_legacy_sidearm_list_roster,
    parse_legacy_sidearm_player_roster,
    parse_roster_list_item,
    find_roster_entries,
    parse_roster_entry,
    resolve_nuxt_payload,
)

OUT_DIR = Path("mt/data/official_rosters")
IMG_DIR_NAME = "photos"


def load_webarchive(path):
    with open(path, "rb") as f:
        d = plistlib.load(f)
    main = d["WebMainResource"]
    html = main["WebResourceData"].decode(main.get("WebResourceTextEncodingName") or "utf-8", errors="replace")
    base_url = main["WebResourceURL"]
    subs = main.get("WebSubresources") or d.get("WebSubresources") or []
    images_by_url = {
        s["WebResourceURL"]: s["WebResourceData"]
        for s in subs
        if str(s.get("WebResourceMIMEType", "")).startswith("image")
    }
    return html, base_url, images_by_url


def parse_players(html, base_url):
    """DOM-based parsers first, Nuxt JSON payload last -- the reverse of
    scrape_season()'s live-fetch order. A webarchive captures the page's
    FINAL rendered DOM (whatever scrolling/lazy-loading happened before the
    user saved it), but the embedded <script type="application/json"> payload
    is frozen at initial SSR time and does not get updated as more entries
    hydrate in -- confirmed on Little Rock/lrtrojans.com's 2020-21 season,
    where the JSON payload had only 20 of the roster's true 30 players, while
    the rendered ".roster-list-item" cards in that same saved HTML had all
    30. For a live network fetch this staleness risk doesn't apply the same
    way (scrape_season() has no rendered DOM to prefer over the payload at
    all), so that order is left alone -- this reordering is specific to
    parsing an already-saved capture.
    """
    players = parse_html_roster(html, base_url)
    if players:
        return players, "vue_person_card"

    players = parse_legacy_sidearm_list_roster(html, base_url)
    if players:
        return players, "legacy_list"

    players = parse_legacy_sidearm_player_roster(html, base_url)
    if players:
        return players, "legacy_player_card"

    players = parse_roster_list_item(html, base_url)
    if players:
        return players, "roster_list_item"

    root = None
    m = re.search(r'<script type="application/json"[^>]*>(.*?)</script>', html, re.DOTALL)
    if m:
        try:
            root = resolve_nuxt_payload(json.loads(m.group(1)))
        except (json.JSONDecodeError, RecursionError):
            root = None

    entries = find_roster_entries(root) if root is not None else None
    if entries:
        return [parse_roster_entry(e, base_url) for e in entries], "nuxt_payload"

    return [], None


def ext_for_mime(mime):
    return {"image/jpeg": "jpg", "image/webp": "webp", "image/png": "png", "image/gif": "gif"}.get(mime, "jpg")


def save_images(players, images_by_url, out_img_dir, team_slug):
    saved = 0
    for p in players:
        url = p.get("photo_url")
        if not url or url not in images_by_url:
            continue
        data = images_by_url[url]
        pid = p.get("player_id") or p.get("slug") or p["name"].lower().replace(" ", "_")
        ext = "jpg" if ".jpeg" in url or ".jpg" in url else ("webp" if url.endswith((".webp",)) else "jpg")
        # sniff actual bytes over trusting the URL extension -- webp is common
        # even on a ".jpeg" URL (confirmed: Wyoming 2012 capture serves every
        # photo as image/webp regardless of the URL's own extension)
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            ext = "webp"
        elif data[:3] == b"\xff\xd8\xff":
            ext = "jpg"
        elif data[:8] == b"\x89PNG\r\n\x1a\n":
            ext = "png"
        out_path = out_img_dir / f"{pid}.{ext}"
        out_path.write_bytes(data)
        p["photo_local_path"] = str(out_path)
        saved += 1
    return saved


def ingest_one(webarchive_path, team_slug, season):
    """Core routine shared by single-file and --batch mode. Returns
    (n_players, n_images, method) or raises on unparseable input."""
    html, base_url, images_by_url = load_webarchive(webarchive_path)
    players, method = parse_players(html, base_url)
    if not players:
        raise ValueError("no players found (tried all fallback parsers)")

    out_dir = OUT_DIR / team_slug
    out_dir.mkdir(parents=True, exist_ok=True)
    img_dir = out_dir / IMG_DIR_NAME / season
    img_dir.mkdir(parents=True, exist_ok=True)

    n_images = save_images(players, images_by_url, img_dir, team_slug)

    data = {
        "season": season,
        "team_roster_url": f"{base_url} (manual webarchive capture)",
        "players": players,
    }
    out_path = out_dir / f"{season}.json"
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return len(players), n_images, method, out_path


# ── Batch mode: auto-resolve team + season from data/_tmp/ filenames ────────

# Maps the "{School Name}" segment of "{label} Wrestling Roster - {School
# Name}.webarchive" (exactly how the user's Safari-saved filenames read) to
# our team slug. Extend this dict, not the parsing logic, when a new school
# gets captured this way.
SCHOOL_NAME_TO_SLUG = {
    "University of Wyoming Athletics": "wyoming",
    "Little Rock Trojans": "little_rock",
}

FILENAME_RE = re.compile(r"^(.+?) Wrestling Roster - (.+)\.webarchive$")


def label_to_season(label):
    """gowyo.com's older pages label a roster page by a single spring year
    ('2012'), which this repo's own season convention treats as season 2012
    -> roster year '2011-12' (confirmed against the already-existing 2020-21
    school year files, whose site label already comes as a 'YYYY-YY' range
    and needs no conversion)."""
    m = re.match(r"^(\d{4})$", label)
    if m:
        year = int(m.group(1))
        return f"{year - 1}-{str(year)[2:]}"
    return label  # already "YYYY-YY"


def run_batch(tmp_dir, dry_run=False):
    results = []
    for path in sorted(Path(tmp_dir).glob("*.webarchive")):
        m = FILENAME_RE.match(path.name)
        if not m:
            print(f"[SKIP] filename doesn't match expected pattern: {path.name}")
            continue
        label, school_name = m.group(1), m.group(2)
        team_slug = SCHOOL_NAME_TO_SLUG.get(school_name)
        if not team_slug:
            print(f"[SKIP] unknown school (add to SCHOOL_NAME_TO_SLUG): {school_name!r} -- {path.name}")
            continue
        season = label_to_season(label)
        if dry_run:
            print(f"[DRY-RUN] {path.name} -> team={team_slug} season={season}")
            continue
        try:
            n_players, n_images, method, out_path = ingest_one(path, team_slug, season)
            print(f"[OK] {team_slug} {season}: {n_players} players ({n_images} photos, via {method}) -> {out_path}")
            results.append((team_slug, season, n_players, n_images))
        except Exception as e:
            print(f"[FAIL] {path.name}: {e}")
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("webarchive", nargs="?", help="Path to a single .webarchive file (omit for --batch)")
    ap.add_argument("--team", help="Team slug for output directory, e.g. wyoming (single-file mode)")
    ap.add_argument("--season", help="Output season label, e.g. 2011-12 (single-file mode)")
    ap.add_argument("--batch", action="store_true",
                     help="Process every .webarchive in data/_tmp/, auto-resolving team+season from filenames")
    ap.add_argument("--dry-run", action="store_true", help="With --batch, show what would be processed without writing")
    args = ap.parse_args()

    if args.batch:
        run_batch("data/_tmp", dry_run=args.dry_run)
        return

    if not args.webarchive or not args.team or not args.season:
        ap.error("single-file mode requires: webarchive --team TEAM --season SEASON (or use --batch)")

    n_players, n_images, method, out_path = ingest_one(args.webarchive, args.team, args.season)
    print(f"[OK] parsed via {method}: {n_players} players ({n_images} photos extracted) -> {out_path}")


if __name__ == "__main__":
    main()
