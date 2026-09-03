#!/usr/bin/env python3
"""
Derives data/season_accomplishments/{gender}/{season}/season_accomplishments.json
from a season's transcribed bracket_instances — same output shape as
scripts/season_accomplishments/generate_season_accomplishments.py so it slots
into the existing pipeline (build_career_profiles.py, build_link_index() in
enter_bracket.py, etc.) unchanged.

Regionals are out of scope for now: regional_* fields are always null/false.
Every entrant in a state bracket is, by definition, a state qualifier.

Usage:
    python scripts/historical_brackets/build_season_accomplishments.py --season 2012 --gender boys
"""

import argparse
import json
from pathlib import Path

INSTANCES_DIR = Path("data/bracket_instances")
TEMPLATES_DIR = Path("data/bracket_templates")
OUT_DIR = Path("data/season_accomplishments")


def build(season: int, gender: str) -> dict:
    season_dir = INSTANCES_DIR / f"hs_ky_{gender}" / str(season)
    if not season_dir.exists():
        raise SystemExit(f"no bracket instances at {season_dir}")

    template_cache: dict[str, dict] = {}
    wrestlers = []

    for path in sorted(season_dir.glob("*.json")):
        instance = json.loads(path.read_text(encoding="utf-8"))
        template_id = instance["template_id"]
        if template_id not in template_cache:
            template_cache[template_id] = json.loads(
                (TEMPLATES_DIR / f"{template_id}.json").read_text(encoding="utf-8"))
        template = template_cache[template_id]
        entrants = instance["entrants"]
        results = instance["results"]
        weight = instance["weight_class"]

        record = {ref: {"wins": 0, "losses": 0} for ref, e in entrants.items() if e != "BYE"}
        for res in results.values():
            if res.get("method") == "bye" or not res.get("winner"):
                continue
            winner, loser = res.get("winner"), res.get("loser")
            if winner in record:
                record[winner]["wins"] += 1
            if loser in record:
                record[loser]["losses"] += 1

        place_by_ref: dict[str, int] = {}
        for sid, pm in template["placement_map"].items():
            res = results.get(sid)
            if not res:
                continue
            if res.get("winner"):
                place_by_ref[res["winner"]] = pm["winner"]["place"]
            if res.get("loser"):
                place_by_ref[res["loser"]] = pm["loser"]["place"]

        for ref, e in entrants.items():
            if e == "BYE" or not e:
                continue
            place = place_by_ref.get(ref)
            wrestlers.append({
                "season_wrestler_id": e["historical_wrestler_id"],
                "name": e["name"],
                "team": e["team"],
                "gender": gender,
                "season": season,
                "grade": e.get("grade"),
                "final_weight": weight,
                "record": record[ref],
                "regional_qualifier": False,
                "regional_place": None,
                "regional_region": None,
                "state_qualifier": True,
                "state_place": place,
                "state_champion": place == 1,
                "career_id": e.get("career_id"),
            })

    return {"season": season, "gender": gender, "wrestlers": wrestlers}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build season_accomplishments.json from bracket instances")
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--gender", choices=["boys", "girls"], required=True)
    args = parser.parse_args()

    out = build(args.season, args.gender)
    out_path = OUT_DIR / args.gender / str(args.season) / "season_accomplishments.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(out['wrestlers'])} wrestlers -> {out_path}")


if __name__ == "__main__":
    main()
