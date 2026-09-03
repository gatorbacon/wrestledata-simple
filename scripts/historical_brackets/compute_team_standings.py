#!/usr/bin/env python3
"""
Computes historical KY state team standings from transcribed bracket
instances (see enter_bracket.py). Sums placement + advancement + bonus
points per team across every weight class's bracket_instances file for a
season, using the applicable row from data/team_scoring_eras/hs_ky_{gender}.json.

Usage:
    python scripts/historical_brackets/compute_team_standings.py --season 2012 --gender boys
"""

import argparse
import json
from pathlib import Path

TEMPLATES_DIR = Path("data/bracket_templates")
INSTANCES_DIR = Path("data/bracket_instances")
STANDINGS_DIR = Path("data/team_standings")

METHOD_TO_BONUS_KEY = {"fall": "fall", "tf": "tech_fall", "md": "major_decision"}


def load_template(template_id: str) -> dict:
    return json.loads((TEMPLATES_DIR / f"{template_id}.json").read_text(encoding="utf-8"))


def compute_standings(season: int, gender: str) -> list[dict]:
    season_dir = INSTANCES_DIR / f"hs_ky_{gender}" / str(season)
    if not season_dir.exists():
        raise SystemExit(f"no bracket instances at {season_dir}")

    totals: dict[str, float] = {}
    place_counts: dict[str, dict[int, int]] = {}
    template_cache: dict[str, dict] = {}

    for path in sorted(season_dir.glob("*.json")):
        instance = json.loads(path.read_text(encoding="utf-8"))
        template_id = instance["template_id"]
        if template_id not in template_cache:
            template_cache[template_id] = load_template(template_id)
        template = template_cache[template_id]
        slots = template["slots"]
        bonus_table = template.get("bonus_points", {})
        entrants = instance["entrants"]

        def team_of(ref: str | None) -> str | None:
            if not ref:
                return None
            e = entrants.get(ref)
            if not e or e == "BYE":
                return None
            return e.get("team")

        for sid, res in instance["results"].items():
            winner = res.get("winner")
            if not winner or res.get("method") == "bye":
                continue
            team = team_of(winner)
            if not team:
                continue
            adv = slots[sid].get("win_points") or 0
            totals[team] = totals.get(team, 0) + adv
            bonus_key = METHOD_TO_BONUS_KEY.get((res.get("method") or "").lower())
            if bonus_key:
                totals[team] = totals.get(team, 0) + bonus_table.get(bonus_key, 0)

        for sid, pm in template["placement_map"].items():
            res = instance["results"].get(sid)
            if not res:
                continue
            for side in ("winner", "loser"):
                ref = res.get(side)
                team = team_of(ref)
                if not team:
                    continue
                place = pm[side]["place"]
                points = pm[side]["points"]
                totals[team] = totals.get(team, 0) + points
                place_counts.setdefault(team, {}).setdefault(place, 0)
                place_counts[team][place] += 1

    rows = [
        {"team": team, "score": round(totals[team], 2), "places": place_counts.get(team, {})}
        for team in totals
    ]
    rows.sort(key=lambda r: (-r["score"], r["team"]))
    return rows


def merge_official(rows: list[dict], official_scores: dict[str, float]) -> list[dict]:
    """
    Combine modern-formula rows with hand-transcribed official scores (see
    WORKFLOW.md — we display/rank by the document's own printed score and
    keep the modern-formula score only for cross-era comparison).
    """
    all_teams = set(r["team"] for r in rows) | set(official_scores.keys())
    by_team = {r["team"]: r for r in rows}
    merged = []
    for team in all_teams:
        r = by_team.get(team, {"places": {}, "score": 0.0})
        merged.append({
            "team": team,
            "official_score": official_scores.get(team),
            "modern_score": r["score"],
            "places": r["places"],
        })
    merged.sort(key=lambda r: (-(r["official_score"] if r["official_score"] is not None else -1), r["team"]))
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute historical KY state team standings")
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--gender", choices=["boys", "girls"], required=True)
    parser.add_argument("--official-json", type=str, default=None,
                         help="path to a {team: official_score} spec hand-transcribed from the "
                              "document — if given, output is ranked/displayed by this score, "
                              "with the computed modern-formula score alongside for comparison")
    parser.add_argument("--save", action="store_true", help="write data/team_standings/hs_ky_{gender}/{season}.json")
    args = parser.parse_args()

    rows = compute_standings(args.season, args.gender)

    if args.official_json:
        official_scores = json.loads(Path(args.official_json).read_text(encoding="utf-8"))
        rows = merge_official(rows, official_scores)
        print(f"{'Place':<6}{'Official':<10}{'Modern':<9}{'Team':<25}")
        for i, r in enumerate(rows, 1):
            off = r["official_score"]
            off_str = f"{off:.2f}" if off is not None else "?"
            print(f"{i:<6}{off_str:<10}{r['modern_score']:<9.2f}{r['team']:<25}")
    else:
        print(f"{'Place':<6}{'Score':<10}{'Team':<25}" + "".join(f"{h:<5}" for h in
              ["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th"]))
        for i, r in enumerate(rows, 1):
            place_str = "".join(f"{r['places'].get(p, '') or '':<5}" for p in range(1, 9))
            print(f"{i:<6}{r['score']:<10.2f}{r['team']:<25}{place_str}")

    if args.save:
        out_path = STANDINGS_DIR / f"hs_ky_{args.gender}" / f"{args.season}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
        print(f"\nSaved -> {out_path}")


if __name__ == "__main__":
    main()
