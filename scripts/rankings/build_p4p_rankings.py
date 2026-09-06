#!/usr/bin/env python3
"""
Builds the homepage P4P + per-weight rankings feed for MatSavant (NCAA D1
men) from FloWrestling's own rankings, enriched with our own per-wrestler
performance stats.

Why enrichment is needed: FloWrestling's rankings pages only give rank/
name/school -- no record, bonus rate, pin rate, or TPAR. The new season
hasn't started (every wrestler is genuinely 0-0), so "record" is just "0-0"
for everyone by design, but bonus rate / pin rate / TPAR are each
wrestler's most recent REAL performance numbers, carried over from the
last completed season (frontend/wrestledata-ui/public/data/wrestlers/2026/,
which is labeled by tourney-year -- i.e. the 2025-26 season that just
finished -- not the upcoming 2026-27 one, which has no per-wrestler stats
yet since it has no matches). Showing last season's real form alongside a
fresh 0-0 record is the intended reading, not a bug: "here's who they were
last year," reset to zero for the year that's about to start.

Join key is (name, school) -- confirmed by hand that all of FloWrestling's
2026-27 P4P entries resolve to exactly one wrestler each in the 2025-26
index via this key, with only one school-name variant needing an alias
("OK State" -> "Oklahoma State"). A wrestler with no match (a true
newcomer with no prior D1 season on file) still gets a row -- just with
"--" for the three enriched stats -- rather than being dropped, since Flo's
own rank order is the thing this table exists to show. Same join logic is
reused across P4P and all 10 weight classes -- one homepage widget with
tabs, per the site's usual weight-tab convention (see e.g. the TPAR Leaders
panel already on the homepage).

Usage:
  .venv/bin/python scripts/rankings/build_p4p_rankings.py
"""
import json
import re
from pathlib import Path

DATE_FILENAME = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
FLO_DIR = PROJECT_ROOT / "data" / "2027" / "flo-preseason-rankings"
WRESTLERS_DIR = PROJECT_ROOT / "frontend" / "wrestledata-ui" / "public" / "data" / "wrestlers" / "2026"
OUT_PATH = PROJECT_ROOT / "frontend" / "wrestledata-ui" / "public" / "data" / "p4p" / "2027.json"

WEIGHT_ORDER = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]

# School-name variants seen in Flo's own text that don't match our index's
# canonical team name -- extend as new ones surface (same "match first, fix
# as it comes" approach used elsewhere in this pipeline). Same short-name
# convention already seen from team_odds/schedule data, plus one literal
# typo in Flo's own page text ("West Virgnia").
SCHOOL_ALIASES = {
    "ok state": "oklahoma state",
    "nd state": "north dakota state",
    "sd state": "south dakota state",
    "app state": "appalachian state",
    "uni": "northern iowa",
    "army": "army west point",
    "siue": "siu edwardsville",
    "n. colorado": "northern colorado",
    "west virgnia": "west virginia",
}


def latest_flo_snapshot():
    """Only real date-stamped snapshots ("YYYY-MM-DD.json") -- this
    directory also holds non-date auxiliary files (e.g.
    "*_individual_modifiers.json") that would otherwise sort after a date
    string and get picked as "latest" by mistake."""
    files = sorted(f for f in FLO_DIR.glob("*.json") if DATE_FILENAME.match(f.name))
    if not files:
        raise SystemExit(f"No dated Flo snapshots found in {FLO_DIR}")
    return files[-1]


def build_wrestler_index():
    """Returns (by_name_school, by_name_only) from last season's completed
    index. by_name_only maps a lowercased name to a list of wrestler_ids --
    used as a fallback for transfers (someone whose CURRENT preseason school
    differs from where they played last season, so a (name, school) lookup
    can never find them no matter how many school-name aliases exist -- the
    old school is simply a different string). Only usable as a fallback
    when that list has exactly one entry; a name shared by multiple
    wrestlers stays unresolved rather than risk a wrong match."""
    entries = json.loads((WRESTLERS_DIR / "index_wrestlers.json").read_text())
    by_name_school = {}
    by_name_only = {}
    slug_to_display = {}
    for w in entries:
        name_key = w["name"].strip().lower()
        by_name_school[(name_key, w["team"].strip().lower())] = w["wrestler_id"]
        by_name_only.setdefault(name_key, []).append(w["wrestler_id"])
        slug_to_display[w["team_slug"]] = w["team"]
    return by_name_school, by_name_only, slug_to_display


def load_profile(wrestler_id):
    path = WRESTLERS_DIR / "by_id" / f"{wrestler_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def frontend_slug(name):
    """Same algorithm as teamNameToSlug() in the frontend JS -- used here so
    a transfer's displayed team/crest/link always reflects their CURRENT
    (preseason) school, not the stale one on their last-season profile."""
    s = name.lower()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^\w_]", "", s)
    s = re.sub(r"_+", "_", s)
    return s.strip("_")


def enrich_entries(entries, wrestler_index, unmatched_out):
    by_name_school, by_name_only, slug_to_display = wrestler_index
    out = []
    for entry in entries:
        name = entry["name"]
        school = entry["school"]
        resolved_school = SCHOOL_ALIASES.get(school.strip().lower(), school.strip().lower())
        name_key = name.strip().lower()
        team_slug = frontend_slug(resolved_school)

        wrestler_id = by_name_school.get((name_key, resolved_school))
        if not wrestler_id:
            # Transfer: last season's record lives under a DIFFERENT school
            # string than their current one, so no school-name alias could
            # ever bridge it. Fall back to name-only, but only when that
            # name is unambiguous across the whole index.
            candidates = by_name_only.get(name_key, [])
            if len(candidates) == 1:
                wrestler_id = candidates[0]

        profile = load_profile(wrestler_id) if wrestler_id else None
        metrics = (profile or {}).get("metrics", {})
        out.append({
            "rank": entry["rank"],
            "name": name,
            "wrestler_id": wrestler_id,  # links to last season's profile -- may be None for a true newcomer
            # Prefer our own index's full display name over Flo's raw text
            # (Flo uses abbreviations like "OK State", and at least one
            # outright typo -- "West Virgnia") -- fall back to Flo's text
            # only if the slug isn't one of our own known teams.
            "team": slug_to_display.get(team_slug, school),
            "team_slug": team_slug,
            "record": "0-0",
            "bonus_rate": metrics.get("bonus_rate"),
            "pin_rate": metrics.get("pin_rate"),
            "tpar": metrics.get("mat_value", {}).get("mv_avg"),
        })
        if not profile:
            unmatched_out.append(f"{name} ({school})")
    return out


def main():
    flo_path = latest_flo_snapshot()
    flo_data = json.loads(flo_path.read_text())
    p4p = flo_data.get("p4p", [])
    weights_raw = flo_data.get("weights", {})
    if not p4p:
        raise SystemExit(f"{flo_path} has no 'p4p' entries -- re-scrape with the updated scraper first")

    wrestler_index = build_wrestler_index()
    unmatched = []

    p4p_out = enrich_entries(p4p, wrestler_index, unmatched)
    weights_out = {}
    for w in WEIGHT_ORDER:
        entries = weights_raw.get(str(w), [])
        weights_out[str(w)] = enrich_entries(entries, wrestler_index, unmatched)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps({
        "source_snapshot": flo_path.name,
        "ranking_date": flo_data["ranking_date"],
        "p4p": p4p_out,
        "weights": weights_out,
    }, indent=2))

    total = len(p4p_out) + sum(len(v) for v in weights_out.values())
    print(f"Wrote {len(p4p_out)} P4P rows + {sum(len(v) for v in weights_out.values())} weight-class rows "
          f"({total} total) to {OUT_PATH.relative_to(PROJECT_ROOT)} (from {flo_path.name})")
    if unmatched:
        print(f"No prior-season stats found for {len(unmatched)}: {', '.join(unmatched)}")


if __name__ == "__main__":
    main()
