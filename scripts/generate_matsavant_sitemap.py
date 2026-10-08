#!/usr/bin/env python3
"""
Generate sitemap.xml for matsavant.com.

Includes:
  - Static pages (homepage, rankings, wrestlers/teams landing, events,
    notes, lab, tools, leaderboards, reports, about, etc.)
  - Individual notes (from data/notes/notes.json)
  - Wrestler pages: ONE name address per wrestler (/wrestler/levi-haines), from
    public/seo/wrestlers/*.json (scripts/seo/build_url_slugs.py; aliases left out).
    Until 2026-10-07 this listed every season's wrestler.html?id= (40,429 URLs for
    ~14,800 wrestlers, which Google flagged as duplicates) -- see
    docs/matsavant_seo_plan.md.
  - Team pages: /team/<name> for the teams in public/seo/teams.json (pages that
    actually have data; the edge function 404s the rest).
  - lastmod = when the content really changed: the latest profile's
    profile_generated_at, the team file's generated_at_utc, a static page's last
    git commit (today if it has uncommitted changes).

Excludes the two /leaderboards/tpar.html and /leaderboards/mat_value.html
files -- both are pure <meta refresh> redirects to dpg.html, not real pages.

Usage:
    python scripts/generate_matsavant_sitemap.py
"""

import json
import subprocess
from datetime import date, datetime
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, ElementTree, indent

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = REPO_ROOT / "frontend/wrestledata-ui/public"
OUTPUT_FILE = PUBLIC_DIR / "sitemap.xml"

BASE_URL = "https://www.matsavant.com"  # apex matsavant.com is a 301 -> www; sitemap URLs must be the canonical, directly-served host
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
    ("ncaa_takedowns.html", "0.5", "monthly"),
    ("ncaa_career_takedowns.html", "0.5", "monthly"),
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


def page_lastmod(rel_path):
    """Last git commit date of a static page; today if it has uncommitted changes."""
    f = PUBLIC_DIR / (rel_path or "index.html")
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", str(f)], cwd=REPO_ROOT).returncode != 0:
        return TODAY
    out = subprocess.run(["git", "log", "-1", "--format=%cs", "--", str(f)],
                         capture_output=True, text=True, cwd=REPO_ROOT).stdout.strip()
    return out or TODAY


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
    for f in sorted((PUBLIC_DIR / "seo/wrestlers").glob("*.json")):
        info = json.loads(f.read_text())
        if info.get("alias_of"):
            continue
        profile = PUBLIC_DIR / f"data/wrestlers/{info['latest_season']}/by_id/{info['latest_id']}.json"
        try:
            lastmod = json.loads(profile.read_text()).get("profile_generated_at") or TODAY
        except (json.JSONDecodeError, OSError):
            lastmod = TODAY
        priority = "0.6" if info["latest_season"] >= CURRENT_SEASON else "0.4"
        entries.append((f"wrestler/{info['slug']}", lastmod[:10], priority, "weekly" if priority == "0.6" else "yearly"))
    return entries


def team_entries():
    entries = []
    teams = json.loads((PUBLIC_DIR / "seo/teams.json").read_text())
    for team_id in sorted(teams):
        try:
            data = json.loads((PUBLIC_DIR / f"data/teams/{team_id}.json").read_text())
            lastmod = (data.get("generated_at_utc") or TODAY)[:10]
        except (json.JSONDecodeError, OSError):
            lastmod = TODAY
        entries.append((f"team/{team_id.replace('_', '-')}", lastmod, "0.6", "weekly"))
    return entries


def main():
    urlset = Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")

    for path, priority, changefreq in STATIC_PAGES:
        add_url(urlset, f"{BASE_URL}/{path}", page_lastmod(path), priority, changefreq)

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
