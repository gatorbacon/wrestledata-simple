#!/usr/bin/env python3
"""
Generate sitemap.xml for kentuckymat.com.

Includes:
  - Career profile pages (boys + girls)
  - Team profile pages (boys + girls, current season)
  - Static pages

Usage:
    python scripts/generate_sitemap.py
"""

from datetime import date
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, ElementTree, indent

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = REPO_ROOT / "frontend/hs-ky-ui/public"
OUTPUT_FILE = PUBLIC_DIR / "sitemap.xml"

BASE_URL = "https://www.kentuckymat.com"
CURRENT_SEASON = 2026
TODAY = date.today().isoformat()

STATIC_PAGES = [
    ("", "1.0", "weekly"),          # homepage
    ("rankings.html?gender=boys", "0.9", "daily"),
    ("rankings.html?gender=girls", "0.9", "daily"),
    ("leaderboards.html?gender=boys", "0.8", "weekly"),
    ("leaderboards.html?gender=girls", "0.8", "weekly"),
    ("recruiting.html?gender=boys", "0.7", "weekly"),
    ("recruiting.html?gender=girls", "0.7", "weekly"),
    ("dual_predictor.html", "0.6", "monthly"),
    ("about.html", "0.4", "monthly"),
    ("report.html", "0.3", "monthly"),
]


def add_url(urlset, loc, priority, changefreq):
    url_el = SubElement(urlset, "url")
    SubElement(url_el, "loc").text = f"{BASE_URL}/{loc}"
    SubElement(url_el, "lastmod").text = TODAY
    SubElement(url_el, "changefreq").text = changefreq
    SubElement(url_el, "priority").text = priority


def main():
    urlset = Element("urlset")
    urlset.set("xmlns", "http://www.sitemaps.org/schemas/sitemap/0.9")

    # Static pages
    for path, priority, changefreq in STATIC_PAGES:
        add_url(urlset, path, priority, changefreq)

    static_count = len(STATIC_PAGES)
    career_count = 0
    team_count = 0

    # Career profiles
    for gender in ("boys", "girls"):
        careers_dir = PUBLIC_DIR / "data" / "careers" / gender
        if not careers_dir.exists():
            print(f"  Warning: {careers_dir} not found, skipping")
            continue
        for career_file in sorted(careers_dir.glob("career_*.json")):
            career_id = career_file.stem  # e.g. career_000001
            loc = f"wrestler.html?gender={gender}&career_id={career_id}"
            add_url(urlset, loc, "0.8", "weekly")
            career_count += 1

    # Team profiles (current season only)
    for gender in ("boys", "girls"):
        teams_dir = PUBLIC_DIR / "data" / "teams" / gender / str(CURRENT_SEASON)
        if not teams_dir.exists():
            print(f"  Warning: {teams_dir} not found, skipping")
            continue
        for team_file in sorted(teams_dir.glob("*.json")):
            team_slug = team_file.stem
            loc = f"team.html?gender={gender}&team={team_slug}&season={CURRENT_SEASON}"
            add_url(urlset, loc, "0.7", "weekly")
            team_count += 1

    tree = ElementTree(urlset)
    indent(tree, space="  ")
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(f, encoding="unicode", xml_declaration=False)

    total = static_count + career_count + team_count
    print(f"sitemap.xml written to {OUTPUT_FILE}")
    print(f"  {static_count} static pages")
    print(f"  {career_count} career profiles")
    print(f"  {team_count} team profiles")
    print(f"  {total} total URLs")


if __name__ == "__main__":
    main()
