#!/usr/bin/env python3
"""
Builds frontend/hs-ky-ui/public/data/wrestlers/{gender}/{season}/by_id/{HW_id}.json
stub profiles from a season's transcribed bracket_instances — the input
build_career_profiles.py (unmodified) needs to fold historical seasons into
existing/new career pages.

Match dates are a placeholder (the state tournament's actual date) since the
bracket sheets don't record per-bout timestamps — this mirrors the plan's
"placeholder date" approach used elsewhere in this pipeline.

Usage:
    python scripts/historical_brackets/build_wrestler_stubs.py --season 2012 --gender boys
"""

import argparse
import json
import re
from pathlib import Path

INSTANCES_DIR = Path("data/bracket_instances")
TEMPLATES_DIR = Path("data/bracket_templates")
OUT_BASE = Path("frontend/hs-ky-ui/public/data/wrestlers")
CAREERS_BOYS_DIR = Path("data/careers")
CAREERS_GIRLS_DIR = Path("data/careers/girls")

METHOD_MAP = {
    "fall": "FALL", "dec": "DEC", "md": "MD", "tf": "TF",
    "ff": "FF", "forf": "FF", "default": "FF", "dq": "DQ", "inj": "INJ",
}

STATE_TOURNAMENT_DATE = {2012: "2012-02-18", 2011: "2011-02-19", 2010: "2010-02-20"}  # last day of the event; extend per season


def slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r'[^a-z0-9\s]', '', slug)
    slug = re.sub(r'\s+', '_', slug)
    return re.sub(r'_+', '_', slug).strip('_')


def careers_dir(gender: str) -> Path:
    return CAREERS_GIRLS_DIR if gender == "girls" else CAREERS_BOYS_DIR


def load_career_lookup(gender: str) -> dict[str, dict]:
    lookup = {}
    for p in careers_dir(gender).glob("career_*.json"):
        c = json.loads(p.read_text(encoding="utf-8"))
        lookup[c["career_id"]] = c
    return lookup


def build(season: int, gender: str) -> int:
    season_dir = INSTANCES_DIR / f"hs_ky_{gender}" / str(season)
    if not season_dir.exists():
        raise SystemExit(f"no bracket instances at {season_dir}")

    out_dir = OUT_BASE / gender / str(season) / "by_id"
    out_dir.mkdir(parents=True, exist_ok=True)

    career_lookup = load_career_lookup(gender)
    date = STATE_TOURNAMENT_DATE.get(season, f"{season}-02-15")
    event = f"{season} KHSAA State Championship"

    count = 0
    for path in sorted(season_dir.glob("*.json")):
        instance = json.loads(path.read_text(encoding="utf-8"))
        weight = instance["weight_class"]
        entrants = instance["entrants"]
        template = json.loads((TEMPLATES_DIR / f"{instance['template_id']}.json").read_text(encoding="utf-8"))
        placement_slot_ids = set(template["placement_map"].keys())

        place_by_ref: dict[str, int] = {}
        for sid, pm in template["placement_map"].items():
            res = instance["results"].get(sid)
            if not res:
                continue
            if res.get("winner"):
                place_by_ref[res["winner"]] = pm["winner"]["place"]
            if res.get("loser"):
                place_by_ref[res["loser"]] = pm["loser"]["place"]

        match_lists: dict[str, list] = {ref: [] for ref, e in entrants.items() if e != "BYE"}
        for res in instance["results"].values():
            if res.get("method") == "bye" or not res.get("winner") or not res.get("loser"):
                continue
            winner, loser = res["winner"], res["loser"]
            we, le = entrants.get(winner), entrants.get(loser)
            if not we or we == "BYE" or not le or le == "BYE":
                continue
            method = METHOD_MAP.get((res.get("method") or "").lower(), "DEC")
            score = res.get("score_text")
            match_lists[winner].append({
                "date": date, "opponent_id": le["historical_wrestler_id"],
                "opponent_career_id": le.get("career_id"), "opponent_name": le["name"],
                "opponent_team": le["team"], "opponent_team_rank": None,
                "opponent_weight": weight, "opponent_rank": None,
                "weight_class": str(weight), "result": "W", "method": method,
                "score": score, "duration": None, "event": event,
            })
            match_lists[loser].append({
                "date": date, "opponent_id": we["historical_wrestler_id"],
                "opponent_career_id": we.get("career_id"), "opponent_name": we["name"],
                "opponent_team": we["team"], "opponent_team_rank": None,
                "opponent_weight": weight, "opponent_rank": None,
                "weight_class": str(weight), "result": "L", "method": method,
                "score": score, "duration": None, "event": event,
            })

        for ref, e in entrants.items():
            if e == "BYE" or not e:
                continue
            matches = match_lists[ref]
            wins = sum(1 for m in matches if m["result"] == "W")
            losses = sum(1 for m in matches if m["result"] == "L")
            place = place_by_ref.get(ref)

            career = career_lookup.get(e.get("career_id"), {})
            profile = {
                "wrestler_id": e["historical_wrestler_id"],
                "name": e["name"],
                "team": e["team"],
                "team_slug": slugify(e["team"]) if e.get("team") else None,
                "team_rank": None,
                "weight_class": weight,
                "year": season,
                "current_rank": None,
                "record": {"overall": f"{wins}-{losses}", "vs_ranked": "0-0",
                           "vs_top10": "0-0", "vs_top25": "0-0"},
                "metrics": {},
                "opponent_breakdown": {},
                "match_list": matches,
                "career": {
                    "career_id": e.get("career_id"),
                    "canonical_name": career.get("canonical_name", e["name"]),
                    "seasons": sorted((int(s) for s in career.get("seasons", {})), reverse=True),
                },
                "season_summary": [{
                    "season": season, "grade": e.get("grade"), "team": e["team"],
                    "record": f"{wins}-{losses}", "regional_place": None, "state_place": place,
                    "regional_data_tracked": False,
                }],
                "career_record": {"wins": wins, "losses": losses,
                                   "win_pct": round(wins / (wins + losses), 3) if (wins + losses) else 0.0},
                "profile_generated_at": None,
            }
            out_path = out_dir / f"{e['historical_wrestler_id']}.json"
            out_path.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            count += 1

    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Build wrestler profile stubs from bracket instances")
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--gender", choices=["boys", "girls"], required=True)
    args = parser.parse_args()

    n = build(args.season, args.gender)
    print(f"Wrote {n} wrestler stubs -> {OUT_BASE / args.gender / str(args.season) / 'by_id'}")


if __name__ == "__main__":
    main()
