#!/usr/bin/env python3
"""
Same-season join: match each official-athletics-site roster entry (see
scrape_official_roster.py) to its TrackWrestling season_wrestler_id, for the
same team and season. This is step 1 of the NCAA career-linking game plan --
purely a name match within one team's ~30-person roster for one season, NOT
the cross-year "career" problem (see project notes: (school, official
player_id) already solves that part for non-transfers).

Persists the join as mt/data/roster_links/{team_slug}/{season}.json, so it
becomes the shared input for both career-linking (chain player_id across
seasons at one school) and profile enrichment (copy hometown/class_level/
photo onto a TW season_wrestler_id). Also prints match-rate reporting and
every unmatched entry on both sides so quality can be judged directly,
rather than just trusting an aggregate percentage.

Usage:
  python scripts/analysis/match_official_rosters_to_trackwrestling.py
  python scripts/analysis/match_official_rosters_to_trackwrestling.py --team penn_state
"""

import argparse
import json
import re
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OFFICIAL_DIR = PROJECT_ROOT / "mt" / "data" / "official_rosters"
TW_DIR = PROJECT_ROOT / "mt" / "data" / "ncaa_men"
LINKS_DIR = PROJECT_ROOT / "mt" / "data" / "roster_links"

# official_rosters slug -> mt/data/ncaa_men/{year}/ file stem, for the handful
# of schools where slugifying the TW name doesn't land on the slug already in
# use under official_rosters/ (established during roster collection: some
# slugs are abbreviations chosen at collection time, not a slugify() output).
SLUG_OVERRIDES = {
    "Army_West_Point": "army",
    "North_Dakota_State": "nd_state",
    "South_Dakota_State": "sd_state",
    "Northern_Iowa": "uni",
    "Northern_Colorado": "n_colorado",
    "SIU_Edwardsville": "siue",
    "The_Citadel": "citadel",
    "Franklin_&_Marshall": "franklin_marshall",
    "Appalachian_State": "app_state",
}


def slugify(name):
    s = name.lower().replace("&", "and").replace(".", "").replace("'", "")
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def build_team_tw_name_map():
    """
    official_rosters slug -> TW file stem, auto-derived from whatever teams
    currently exist on both sides (not hardcoded to a handful of schools),
    so a newly-collected school gets picked up automatically next run.
    """
    official_slugs = {d.name for d in OFFICIAL_DIR.iterdir() if d.is_dir()}
    mapping = {}
    for year_dir in sorted(TW_DIR.iterdir(), reverse=True):
        if not year_dir.is_dir():
            continue
        for f in year_dir.glob("*.json"):
            tw_name = f.stem
            slug = SLUG_OVERRIDES.get(tw_name, slugify(tw_name))
            if slug in official_slugs:
                mapping.setdefault(slug, tw_name)
    return mapping


def normalize_name(name):
    if not name:
        return ""
    name = re.sub(r"[`´'‘’.]", "", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip().lower()


def season_label_to_year(label):
    """'2025-26' -> 2026 (this project's tournament-year convention)."""
    start = int(label.split("-")[0])
    return start + 1


def load_tw_roster(team_tw_name, year):
    path = TW_DIR / str(year) / f"{team_tw_name}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return data.get("roster", [])


def match_team_season(team_slug, tw_team_name, official_path, debug=False):
    official_data = json.loads(official_path.read_text())
    season_label = official_data["season"]
    if not season_label or not re.match(r"^\d{4}-\d{2}$", season_label):
        return None
    year = season_label_to_year(season_label)

    tw_roster = load_tw_roster(tw_team_name, year) if tw_team_name else None
    if tw_roster is None:
        return {"team": team_slug, "season": season_label, "skip": "no_tw_roster"}

    tw_by_name = defaultdict(list)
    for w in tw_roster:
        tw_by_name[normalize_name(w["name"])].append(w)

    official_players = official_data["players"]
    matched, unmatched_official = [], []
    used_tw_ids = set()

    for p in official_players:
        norm = normalize_name(p["name"])
        candidates = tw_by_name.get(norm, [])
        candidates = [c for c in candidates if c["season_wrestler_id"] not in used_tw_ids]
        if candidates:
            tw = candidates[0]
            used_tw_ids.add(tw["season_wrestler_id"])
            matched.append((p, tw, "exact"))
            continue

        # fuzzy fallback
        best, best_score = None, 0.0
        for tw_name_norm, tw_list in tw_by_name.items():
            for tw in tw_list:
                if tw["season_wrestler_id"] in used_tw_ids:
                    continue
                score = SequenceMatcher(None, norm, tw_name_norm).ratio()
                if score > best_score:
                    best_score, best = score, tw
        if best is not None and best_score >= 0.8:
            used_tw_ids.add(best["season_wrestler_id"])
            matched.append((p, best, f"fuzzy({best_score:.2f})"))
        else:
            unmatched_official.append(p)

    unmatched_tw = [w for w in tw_roster if w["season_wrestler_id"] not in used_tw_ids]

    return {
        "team": team_slug,
        "tw_team_name": tw_team_name,
        "season": season_label,
        "year": year,
        "matched": matched,
        "unmatched_official": unmatched_official,
        "unmatched_tw": unmatched_tw,
        "total_official": len(official_players),
        "total_tw": len(tw_roster),
    }


def persist_result(result):
    out = {
        "team": result["team"],
        "tw_team_name": result["tw_team_name"],
        "season": result["season"],
        "year": result["year"],
        "links": [
            {
                "season_wrestler_id": tw["season_wrestler_id"],
                "player_id": p["player_id"],
                "name": p["name"],
                "match_type": kind,
            }
            for p, tw, kind in result["matched"]
        ],
        "unmatched_official": [
            {"player_id": p["player_id"], "name": p["name"], "class_level": p["class_level"]}
            for p in result["unmatched_official"]
        ],
        "unmatched_tw": [
            {"season_wrestler_id": w["season_wrestler_id"], "name": w["name"], "weight_class": w.get("weight_class")}
            for w in result["unmatched_tw"]
        ],
    }
    out_dir = LINKS_DIR / result["team"]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{result['season']}.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="Match official roster entries to TrackWrestling season_wrestler_ids")
    parser.add_argument("--team", default=None, help="Single team slug (default: all teams with official roster data)")
    parser.add_argument("--debug", action="store_true", help="List every matched pair, not just summary")
    parser.add_argument("--no-persist", action="store_true", help="Report only, don't write mt/data/roster_links/")
    args = parser.parse_args()

    team_tw_name_map = build_team_tw_name_map()
    team_dirs = [OFFICIAL_DIR / args.team] if args.team else sorted(OFFICIAL_DIR.iterdir())

    grand_matched = grand_official = grand_tw = 0
    all_unmatched_official = []
    all_unmatched_tw = []
    low_match_teams = []

    for team_dir in team_dirs:
        if not team_dir.is_dir():
            continue
        team_slug = team_dir.name
        tw_team_name = team_tw_name_map.get(team_slug)
        for season_path in sorted(team_dir.glob("*.json")):
            result = match_team_season(team_slug, tw_team_name, season_path, debug=args.debug)
            if result is None:
                continue
            if result.get("skip"):
                print(f"{team_slug} {season_path.stem}: [SKIP] {result['skip']}")
                continue

            n_matched = len(result["matched"])
            grand_matched += n_matched
            grand_official += result["total_official"]
            grand_tw += result["total_tw"]

            fuzzy_count = sum(1 for _, _, kind in result["matched"] if kind != "exact")
            pct_official = 100 * n_matched / result["total_official"] if result["total_official"] else 0
            print(
                f"{team_slug:<20} {result['season']:<8} "
                f"official={result['total_official']:>3} tw={result['total_tw']:>3} "
                f"matched={n_matched:>3} ({pct_official:5.1f}%) (fuzzy={fuzzy_count}) "
                f"unmatched_official={len(result['unmatched_official'])} unmatched_tw={len(result['unmatched_tw'])}"
            )
            if pct_official < 80:
                low_match_teams.append((team_slug, result["season"], pct_official))
            if args.debug:
                for p, tw, kind in result["matched"]:
                    if kind != "exact":
                        print(f"    FUZZY: '{p['name']}' <-> '{tw['name']}' ({kind})")
            for p in result["unmatched_official"]:
                all_unmatched_official.append((team_slug, result["season"], p["name"], p["class_level"]))
            for w in result["unmatched_tw"]:
                all_unmatched_tw.append((team_slug, result["season"], w["name"], w.get("weight_class")))

            if not args.no_persist:
                persist_result(result)

    print(f"\n{'='*70}")
    print(f"TOTAL: official={grand_official} tw={grand_tw} matched={grand_matched} "
          f"({100*grand_matched/grand_official:.1f}% of official, {100*grand_matched/grand_tw:.1f}% of TW)")

    if low_match_teams:
        print(f"\nTeam-seasons under 80% official-match rate -- {len(low_match_teams)}:")
        for team, season, pct in sorted(low_match_teams, key=lambda x: x[2]):
            print(f"  {team:<20} {season:<8} {pct:.1f}%")

    if all_unmatched_official:
        print(f"\nUnmatched official-roster entries (no TW match found) -- {len(all_unmatched_official)}:")
        for team, season, name, class_level in all_unmatched_official:
            print(f"  {team:<20} {season:<8} {name:<25} {class_level}")

    if all_unmatched_tw:
        print(f"\nUnmatched TrackWrestling entries (no official-roster match found) -- {len(all_unmatched_tw)}:")
        for team, season, name, weight in all_unmatched_tw:
            print(f"  {team:<20} {season:<8} {name:<25} {weight}")


if __name__ == "__main__":
    main()
