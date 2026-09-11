#!/usr/bin/env python3
"""
Generate sitemap.xml for matsavant.com.

Includes:
  - Static pages (homepage, rankings, wrestlers/teams landing, events,
    notes, lab, tools, leaderboards, reports, about, etc.)
  - Individual notes (from data/notes/notes.json)
  - Wrestler profile pages, every season 2012-2026 (each season's
    wrestler_id is its own crawlable entry point into that person's career
    page -- see season_summary in the wrestler JSON)
  - Team profile pages (current roster snapshot, one per team)

Excludes the two /leaderboards/tpar.html and /leaderboards/mat_value.html
files -- both are pure <meta refresh> redirects to dpg.html, not real pages.

Usage:
    python scripts/generate_matsavant_sitemap.py
"""

import json
from datetime import date, datetime
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, ElementTree, indent

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = REPO_ROOT / "frontend/wrestledata-ui/public"
OUTPUT_FILE = PUBLIC_DIR / "sitemap.xml"

BASE_URL = "https://matsavant.com"
CURRENT_SEASON = 2026
TODAY = date.today().isoformat()

STATIC_PAGES = [
    ("", "1.0", "daily"),                                 # homepage
    ("rankings.html", "0.9", "daily"),
    ("wrestlers.html", "0.8", "weekly"),
    ("teams.html", "0.8", "weekly"),
    ("matrix.html", "0.6", "weekly"),
    ("hodge.html", "0.6", "weekly"),
    ("schedule.html", "0.6", "weekly"),
    ("team_odds.html", "0.6", "weekly"),
    ("events/ncaa.html", "0.7", "weekly"),
    ("ncaa_live.html", "0.6", "weekly"),
    ("ncaa_report.html", "0.5", "monthly"),
    ("ncaa_scoring_trends.html", "0.5", "monthly"),
    ("ncaa_team_leaderboard.html", "0.5", "monthly"),
    ("ncaa_team_report.html", "0.5", "monthly"),
    ("ncaa_conf_leaderboard.html", "0.5", "monthly"),
    ("ncaa_conf_analysis.html", "0.5", "monthly"),
    ("leaderboards/dpg.html", "0.5", "weekly"),
    ("leaderboards/leaderboard_wins.html", "0.4", "weekly"),
    ("leaderboards/leaderboard_pins.html", "0.4", "weekly"),
    ("leaderboards/leaderboard_techs.html", "0.4", "weekly"),
    ("leaderboards/leaderboard_majors.html", "0.4", "weekly"),
    ("leaderboards/xtp/teams.html", "0.6", "weekly"),
    ("notes/index.html", "0.7", "daily"),
    ("lab/index.html", "0.4", "monthly"),
    ("tools/index.html", "0.3", "monthly"),
    ("reports/index.html", "0.4", "monthly"),
    ("reports/transfers/index.html", "0.4", "monthly"),
    ("reports/wrestler/index.html", "0.4", "monthly"),
    ("reports/team/index.html", "0.4", "monthly"),
    ("aa_odds.html", "0.3", "monthly"),
    ("freshman.html", "0.3", "monthly"),
    ("final_scores.html", "0.3", "monthly"),
    ("top3_backtest.html", "0.3", "monthly"),
    ("about.html", "0.3", "monthly"),
]


def add_url(urlset, loc, lastmod, priority, changefreq):
    url = SubElement(urlset, "url")
    SubElement(url, "loc").text = loc
    SubElement(url, "lastmod").text = lastmod
    SubElement(url, "changefreq").text = changefreq
    SubElement(url, "priority").text = priority


def notes_entries():
    notes_file = PUBLIC_DIR / "data/notes/notes.json"
    if not notes_file.exists():
        return []
    notes = json.loads(notes_file.read_text())
    return [(f"notes/note.html?slug={n['slug']}", n.get("date", TODAY), "0.6", "monthly") for n in notes]


def wrestler_entries():
    entries = []
    wrestlers_dir = PUBLIC_DIR / "data/wrestlers"
    for season_dir in sorted(wrestlers_dir.iterdir()):
        if not season_dir.is_dir() or not season_dir.name.isdigit():
            continue
        season = int(season_dir.name)
        by_id_dir = season_dir / "by_id"
        if not by_id_dir.exists():
            continue
        priority = "0.5" if season == CURRENT_SEASON else "0.3"
        for f in by_id_dir.glob("*.json"):
            wrestler_id = f.stem
            try:
                data = json.loads(f.read_text())
                lastmod = data.get("profile_generated_at", TODAY)
            except (json.JSONDecodeError, OSError):
                lastmod = TODAY
            entries.append((f"wrestler.html?id={wrestler_id}", lastmod, priority, "yearly"))
    return entries


def team_entries():
    entries = []
    teams_dir = PUBLIC_DIR / "data/teams"
    for f in teams_dir.glob("*.json"):
        if f.stem == "abbreviations":
            continue
        try:
            data = json.loads(f.read_text())
            lastmod = data.get("generated_at_utc", TODAY)[:10]
        except (json.JSONDecodeError, OSError):
            lastmod = TODAY
        entries.append((f"team.html?team={f.stem}", lastmod, "0.5", "weekly"))
    return entries


def main():
    urlset = Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")

    for path, priority, changefreq in STATIC_PAGES:
        add_url(urlset, f"{BASE_URL}/{path}", TODAY, priority, changefreq)

    for path, lastmod, priority, changefreq in notes_entries():
        add_url(urlset, f"{BASE_URL}/{path}", lastmod, priority, changefreq)

    wrestlers = wrestler_entries()
    teams = team_entries()
    for path, lastmod, priority, changefreq in wrestlers + teams:
        add_url(urlset, f"{BASE_URL}/{path}", lastmod, priority, changefreq)

    total = len(STATIC_PAGES) + len(notes_entries()) + len(wrestlers) + len(teams)
    print(f"Sitemap URLs: {len(STATIC_PAGES)} static + {len(notes_entries())} notes "
          f"+ {len(wrestlers)} wrestlers + {len(teams)} teams = {total} total")
    if total > 50000:
        print("WARNING: over the 50,000-URL single-sitemap limit -- split into a sitemap index.")

    tree = ElementTree(urlset)
    indent(tree, space="  ")
    tree.write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
    print(f"Wrote {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
