#!/usr/bin/env python3
"""
Stage KentuckyMat PRESEASON ranking-matrix inputs for the next season.

Full process and reasoning: docs/kentuckymat_preseason_rankings.md

Takes the previous season's FINAL rankings and builds a starting order for
the new season, keeping every wrestler on the same team at the same weight:

  1. Order per weight = the manual block (matrix rank <= cutoff: 60 boys,
     36 girls -- same cutoff as calculate_elo_ratings.get_manual_rank_cutoff)
     followed by everyone below it in ELO order (wins tier, then winless,
     then 0-0 -- the same tiers as the hybrid rank).
  2. Seniors are removed and everyone moves up.
  3. relationships_{w}.json is copied with seniors' own rows/pairs removed.
     Common-opponent pairs whose common opponent was a senior are KEPT
     (that evidence still compares two returning wrestlers).
  4. placement_notes.json is rebuilt from the previous season's state
     tournament (1-8 placers, BR = lost in the round that decides placing --
     boys Cons. Round 4, girls Cons. Round 2 -- and Q = every other state
     entrant), from mt/processed_data via build_xtp_simple_hybrid's bracket
     collectors. Seniors dropped. data/hs_ky_*/bloodround.txt is NOT used.

Wrestler IDs stay the PREVIOUS season's TrackWrestling IDs (the new season
has no IDs yet). Output goes to a separate staging tree, never to
mt/rankings_data/, so it can't be mistaken for real season data:

    mt/preseason_{to}/rankings_data/hs_ky_{gender}/{to}/
        rankings_{w}.json, relationships_{w}.json, placement_notes.json

Then build the editable matrices from it:

    .venv/bin/python scripts/rankings/generate_matrix.py -season 2027 -league hs -state KY \\
        -gender boys -data-dir mt/preseason_2027/rankings_data \\
        -output-dir mt/preseason_2027/rankings_html

Usage:
    .venv/bin/python scripts/rankings/build_preseason_matrix_inputs.py --from-season 2026 --gender boys
"""

import argparse
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "xtp"))

from calculate_elo_ratings import get_manual_rank_cutoff, get_weights  # noqa: E402
from create_rankings_release import load_grade_lookup  # noqa: E402
import build_xtp_simple_hybrid as bx  # noqa: E402

BR_ROUND = {"boys": "Cons. Round 4", "girls": "Cons. Round 2"}


def grade_lookup_with_fallback(season: int, gender: str):
    """wrestler_id -> grade display. Falls back to the other gender's grade by
    exact name+team (girls who also wrestle on the boys side have no boys grade)."""
    gl = load_grade_lookup(season, gender)
    other = "girls" if gender == "boys" else "boys"
    ogl = load_grade_lookup(season, other)
    by_name = {}
    for f in glob.glob(f"mt/rankings_data/hs_ky_{other}/{season}/rankings_*.json"):
        for x in json.load(open(f))["rankings"]:
            if ogl.get(x["wrestler_id"]):
                by_name[(x["name"].lower(), x["team"])] = ogl[x["wrestler_id"]]
    for f in glob.glob(f"mt/rankings_data/hs_ky_{gender}/{season}/rankings_*.json"):
        for x in json.load(open(f))["rankings"]:
            key = (x["name"].lower(), x["team"])
            if not gl.get(x["wrestler_id"]) and key in by_name:
                gl[x["wrestler_id"]] = by_name[key]
    return gl


def state_notes(season: int, gender: str):
    """wrestler_id -> '1'..'8' / 'BR' / 'Q' from that season's state tournament."""
    ev = bx.esp.STATE_EVENT_BOYS if gender == "boys" else bx.esp.STATE_EVENT_GIRLS
    dates = bx.esp._state_dates_for_season(season)
    final_rounds = bx.collect_final_rounds(gender, season, dates, ev)
    places = bx.collect_placements(gender, season, dates, ev)
    notes = {}
    for wid in set(final_rounds) | set(places):
        if wid in places:
            notes[wid] = str(places[wid])
        elif final_rounds[wid][0] == BR_ROUND[gender] and not final_rounds[wid][1]:
            notes[wid] = "BR"
        else:
            notes[wid] = "Q"
    return notes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-season", type=int, required=True, help="Season whose final rankings are the start point")
    ap.add_argument("--gender", choices=["boys", "girls"], required=True)
    args = ap.parse_args()
    g, frm = args.gender, args.from_season
    to = frm + 1
    cut = get_manual_rank_cutoff("hs", g)

    src = Path(f"mt/rankings_data/hs_ky_{g}/{frm}")
    dst = Path(f"mt/preseason_{to}/rankings_data/hs_ky_{g}/{to}")
    dst.mkdir(parents=True, exist_ok=True)

    gl = grade_lookup_with_fallback(frm, g)
    acc = {
        w["season_wrestler_id"]: w
        for w in json.load(open(f"data/season_accomplishments/{g}/{frm}/season_accomplishments.json"))["wrestlers"]
    }
    seniors = {wid for wid, gr in gl.items() if gr == "Sr."}
    seniors |= {wid for wid, a in acc.items() if a.get("grade") == 12 and not gl.get(wid)}
    elo = {e["wrestler_id"]: e for e in json.load(open(f"mt/elo_ratings/{g}/{frm}/elo_ratings.json"))}

    def elo_tier(x):
        e = elo.get(x["wrestler_id"], {})
        tier = 0 if e.get("wins", 0) > 0 else 1 if e.get("match_count", 0) > 0 else 2
        return (tier, -(e.get("elo_score") or 0))

    print(f"{g} {frm} -> {to} preseason | manual cutoff {cut} | seniors {len(seniors)}")
    for w in get_weights("hs", g):
        ranks = json.load(open(src / f"rankings_{w}.json"))["rankings"]
        manual = [x for x in ranks if x["rank"] <= cut]
        rest = sorted((x for x in ranks if x["rank"] > cut), key=elo_tier)
        order = [x for x in manual + rest if x["wrestler_id"] not in seniors]
        manual_left = sum(1 for x in manual if x["wrestler_id"] not in seniors)
        seen_team, out = set(), []
        for i, x in enumerate(order, 1):
            out.append({
                "rank": i, "wrestler_id": x["wrestler_id"], "name": x["name"], "team": x["team"],
                "record": x.get("record"), "is_starter": x["team"] not in seen_team,
            })
            seen_team.add(x["team"])
        json.dump({"weight_class": str(w), "season": to, "rankings": out},
                  open(dst / f"rankings_{w}.json", "w"), indent=2)

        rel = json.load(open(src / f"relationships_{w}.json"))
        rel["wrestlers"] = {k: v for k, v in rel["wrestlers"].items() if k not in seniors}
        for key in ("direct_relationships", "common_opponent_relationships"):
            rel[key] = {k: v for k, v in rel[key].items()
                        if v["wrestler1_id"] not in seniors and v["wrestler2_id"] not in seniors}
        json.dump(rel, open(dst / f"relationships_{w}.json", "w"))
        print(f"  {w}: {len(out)} ranked, manual ranks run through #{manual_left}")

    notes = []
    for wid, note in state_notes(frm, g).items():
        a = acc.get(wid, {})
        if wid in seniors or a.get("grade") == 12:
            continue
        notes.append({"wrestler_id": wid, "name": a.get("name"), "team": a.get("team"), "note": note})
    notes.sort(key=lambda x: (x["note"] not in list("12345678"), x["note"], x["name"] or ""))
    json.dump({"notes": notes, "source": f"{frm} KHSAA state tournament (mt/processed_data), seniors removed"},
              open(dst / "placement_notes.json", "w"), indent=2)
    print(f"  placement notes: {len(notes)} returning state entrants")
    print(f"Wrote {dst}")


if __name__ == "__main__":
    main()
