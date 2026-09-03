#!/usr/bin/env python3
"""
Bracket template builder for historical KY high school wrestling brackets.

Generates JSON "bracket template" definitions — round structure plus
winner/loser slot wiring plus a placement map — for a single-elimination
championship bracket with an optional single-backside consolation ladder.

This generalizes the Slot{id, bracket, round, inputs, winner_to, loser_to}
pattern hardcoded for one fixed 33-man NCAA bracket in
xtp/engine/bracket_schema.py into a parametrized builder for arbitrary
power-of-2 entrant counts and places-awarded counts (2/4/6/8), so a new
template can be generated on demand for whatever KY state bracket shape
a given historical year actually used, instead of hand-wiring slots.

Usage:
    # Build + save + register a template, then print a summary
    python scripts/historical_brackets/template_builder.py \\
        --entrants 16 --places 8 --consolation-style single_backside \\
        --gender boys --first-season 2012 --last-season 2012

    # Sanity-check the generator itself across common sizes (no file writes)
    python scripts/historical_brackets/template_builder.py --self-test
"""

import argparse
import json
import math
from pathlib import Path

TEMPLATES_DIR = Path("data/bracket_templates")
INDEX_PATH = TEMPLATES_DIR / "index.json"
SCORING_DIR = Path("data/team_scoring_eras")

STYLE_ABBREV = {
    "none": "none",
    "single_backside": "std",
    "double_backside_crossover": "dbl",
}


# ---------------------------------------------------------------------------
# Championship (frontside) bracket
# ---------------------------------------------------------------------------

def _champ_round_meta(round_num: int, total_rounds: int) -> tuple[str, str]:
    """Return (round_id, label) for 1-indexed champ round `round_num` of `total_rounds`."""
    remaining_after = total_rounds - round_num
    if remaining_after == 0:
        return "champ_final", "1st Place Match"
    if remaining_after == 1:
        return "champ_sf", "Semifinals"
    if remaining_after == 2:
        return "champ_qf", "Quarterfinals"
    return f"champ_r{round_num}", f"Champ. Round {round_num}"


def build_championship(size: int) -> tuple[dict, list[list[str]], list[dict]]:
    """
    Build the championship bracket for `size` entrants (must be a power of 2, >= 2).

    Returns (slots, rounds, round_defs):
      slots:      {slot_id: {bracket, round, inputs, winner_to, loser_to}}
      rounds:     [[slot_id, ...], ...] one list per round, earliest -> final
      round_defs: [{round_id, bracket, label, slots}, ...] in the same order
    """
    if size < 2 or (size & (size - 1)) != 0:
        raise ValueError(f"bracket size must be a power of 2 >= 2, got {size}")

    total_rounds = int(math.log2(size))
    slots: dict = {}
    rounds: list[list[str]] = []
    round_defs: list[dict] = []
    prev_ids: list[str] = []

    for r in range(1, total_rounds + 1):
        round_id, label = _champ_round_meta(r, total_rounds)
        n_matches = size // (2 ** r)
        ids = [f"C_{round_id.upper()}_{i}" for i in range(n_matches)]
        for i, sid in enumerate(ids):
            if r == 1:
                inputs = [f"ENTRANT_{2 * i + 1}", f"ENTRANT_{2 * i + 2}"]
            else:
                inputs = [f"{prev_ids[2 * i]}_WINNER", f"{prev_ids[2 * i + 1]}_WINNER"]
            slots[sid] = {
                "bracket": "champ",
                "round": round_id,
                "inputs": inputs,
                "winner_to": None,
                "loser_to": None,
            }
        if r > 1:
            for i, pid in enumerate(prev_ids):
                slots[pid]["winner_to"] = ids[i // 2]
        rounds.append(ids)
        round_defs.append({"round_id": round_id, "bracket": "champ", "label": label, "slots": ids})
        prev_ids = ids

    final_id = rounds[-1][0]
    slots[final_id]["winner_to"] = "PLACE_1"
    slots[final_id]["loser_to"] = "PLACE_2"

    return slots, rounds, round_defs


# ---------------------------------------------------------------------------
# Consolation (backside) bracket — "single_backside" style
# ---------------------------------------------------------------------------

def _cons_round_meta(index_from_end: int) -> tuple[str, str]:
    """index_from_end: 0 = terminal round, 1 = round before it, 2 = round before that, ..."""
    if index_from_end == 0:
        return "cons_final", "3rd Place Match"
    if index_from_end == 1:
        return "cons_semis", "Cons. Semis"
    if index_from_end == 2:
        return "cons_qf", "Cons. Quarterfinals"
    return None, None  # assigned positionally below


def build_consolation_single_backside(
    places_awarded: int,
    champ_slots: dict,
    champ_rounds: list[list[str]],
) -> tuple[dict, list[dict], dict]:
    """
    Build a standard single-backside consolation ladder, mutating `champ_slots`
    in place to wire each non-final champ round's loser_to into the backside.

    Returns (slots, round_defs, placement_map_extra) for the consolation side.
    Only places_awarded in {2, 4, 6, 8} are supported (2 = no consolation at all).
    """
    if places_awarded not in (2, 4, 6, 8):
        raise ValueError(f"places_awarded must be one of 2/4/6/8, got {places_awarded}")

    total_champ_rounds = len(champ_rounds)

    # No consolation: eliminate every non-final champ round's losers.
    if places_awarded == 2 or total_champ_rounds < 2:
        for rnd in champ_rounds[:-1]:
            for sid in rnd:
                champ_slots[sid]["loser_to"] = None
        return {}, [], {}

    slots: dict = {}
    round_meta: list[dict] = []  # [{kind, ids}]

    # BR1: pair up champ-round-1 losers among themselves.
    r1_ids = champ_rounds[0]
    br1_ids = []
    for i in range(0, len(r1_ids), 2):
        bid = f"CONS_R1_{i // 2}"
        br1_ids.append(bid)
        slots[bid] = {
            "bracket": "consol",
            "round": None,  # assigned after we know final round positions
            "inputs": [f"{r1_ids[i]}_LOSER", f"{r1_ids[i + 1]}_LOSER"],
            "winner_to": None,
            "loser_to": None,
        }
        champ_slots[r1_ids[i]]["loser_to"] = bid
        champ_slots[r1_ids[i + 1]]["loser_to"] = bid
    round_meta.append({"kind": "merge", "ids": br1_ids})
    current = br1_ids

    # For each subsequent non-final champ round: merge round, then pure round.
    for i in range(1, total_champ_rounds - 1):
        champ_losers_ids = champ_rounds[i]
        if len(current) != len(champ_losers_ids):
            raise AssertionError(
                f"backside pool size {len(current)} != champ round {i + 1} loser "
                f"count {len(champ_losers_ids)} — bracket is malformed"
            )
        # The incoming champ-round losers are crossed against the backside winner order
        # at each merge stage, but the crossover pattern is NOT uniform across stages --
        # confirmed against a real 2012 KY state bracket scan (32e/8p), matching the same
        # two-pattern convention used in xtp/engine/bracket_schema.py's NCAA bracket:
        #   - the FIRST merge stage (this is where the widest field of new droppers enters,
        #     e.g. champ round-2 losers) uses a FULL reversal: position j <-> N-1-j.
        #     Confirmed: CONS_R1_0's winner played the round-2 loser seeded from champ R1
        #     matches 14&15 (the far end), not matches 0&1 (the near end).
        #   - every SUBSEQUENT merge stage (QF-losers, SF-losers, ...) instead uses a
        #     neighbor-swap: position j <-> j^1 (0<->1, 2<->3, ...). Confirmed: at the
        #     QF-loser merge, CONS_P1_0's winner played the QF-loser seeded from champ QF
        #     match 1 (the adjacent match), not match 3 (the far end a full reversal would
        #     have picked).
        is_first_merge_stage = (i == 1)
        merge_ids = []
        for j in range(len(current)):
            mirrored_j = (len(current) - 1 - j) if is_first_merge_stage else (j ^ 1)
            bid = f"CONS_M{i}_{j}"
            merge_ids.append(bid)
            slots[bid] = {
                "bracket": "consol",
                "round": None,
                "inputs": [f"{current[j]}_WINNER", f"{champ_losers_ids[mirrored_j]}_LOSER"],
                "winner_to": None,
                "loser_to": None,
            }
            champ_slots[champ_losers_ids[mirrored_j]]["loser_to"] = bid
        for j, prev_id in enumerate(current):
            slots[prev_id]["winner_to"] = merge_ids[j]
        round_meta.append({"kind": "merge", "ids": merge_ids})
        current = merge_ids

        pure_ids = []
        for j in range(0, len(current), 2):
            bid = f"CONS_P{i}_{j // 2}"
            pure_ids.append(bid)
            slots[bid] = {
                "bracket": "consol",
                "round": None,
                "inputs": [f"{current[j]}_WINNER", f"{current[j + 1]}_WINNER"],
                "winner_to": None,
                "loser_to": None,
            }
        for j, prev_id in enumerate(current):
            slots[prev_id]["winner_to"] = pure_ids[j // 2]
        round_meta.append({"kind": "pure", "ids": pure_ids})
        current = pure_ids

    if len(current) != 1:
        raise AssertionError(f"backside did not converge to a single terminal match (got {len(current)})")

    n_backside_rounds = len(round_meta)
    if places_awarded >= 6 and n_backside_rounds < 2:
        raise ValueError("bracket too small to award 5th/6th place (need more entrants)")
    if places_awarded >= 8 and n_backside_rounds < 3:
        raise ValueError("bracket too small to award 7th/8th place (need more entrants)")

    # Assign round_id/label positionally from the end; earlier rounds numbered from the start.
    round_defs: list[dict] = []
    for idx, rnd in enumerate(round_meta):
        from_end = n_backside_rounds - 1 - idx
        round_id, label = _cons_round_meta(from_end)
        if round_id is None:
            round_id, label = f"cons_r{idx + 1}", f"Cons. Round {idx + 1}"
        for sid in rnd["ids"]:
            slots[sid]["round"] = round_id
        round_defs.append({"round_id": round_id, "bracket": "consol", "label": label, "slots": rnd["ids"]})

    # Terminal round -> 3rd/4th.
    terminal_id = round_meta[-1]["ids"][0]
    slots[terminal_id]["winner_to"] = "PLACE_3"
    slots[terminal_id]["loser_to"] = "PLACE_4"
    placement_map_extra = {terminal_id: {"winner": 3, "loser": 4}}

    # Last merge round's losers -> 5th place match.
    if places_awarded >= 6:
        last_merge = round_meta[-2]["ids"]
        slots["CONS_5TH"] = {
            "bracket": "consol",
            "round": "cons_5th_place",
            "inputs": [f"{sid}_LOSER" for sid in last_merge],
            "winner_to": "PLACE_5",
            "loser_to": "PLACE_6",
        }
        for sid in last_merge:
            slots[sid]["loser_to"] = "CONS_5TH"
        round_defs.append({"round_id": "cons_5th_place", "bracket": "consol", "label": "5th Place Match", "slots": ["CONS_5TH"]})
        placement_map_extra["CONS_5TH"] = {"winner": 5, "loser": 6}

    # Pure round before that -> 7th place match.
    if places_awarded >= 8:
        pre_merge = round_meta[-3]["ids"]
        slots["CONS_7TH"] = {
            "bracket": "consol",
            "round": "cons_7th_place",
            "inputs": [f"{sid}_LOSER" for sid in pre_merge],
            "winner_to": "PLACE_7",
            "loser_to": "PLACE_8",
        }
        for sid in pre_merge:
            slots[sid]["loser_to"] = "CONS_7TH"
        round_defs.append({"round_id": "cons_7th_place", "bracket": "consol", "label": "7th Place Match", "slots": ["CONS_7TH"]})
        placement_map_extra["CONS_7TH"] = {"winner": 7, "loser": 8}

    return slots, round_defs, placement_map_extra


# ---------------------------------------------------------------------------
# Top-level builder
# ---------------------------------------------------------------------------

def _load_default_scoring(gender: str) -> dict | None:
    """Load the current scoring era (placement + advancement + bonus points) for `gender`."""
    path = SCORING_DIR / f"hs_ky_{gender}.json"
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    era = data["eras"][0]
    return {
        "placement_points": era["placement_points"],
        "win_points": era["advancement_points"],  # {"champ_win": N, "cons_win": N}
        "bonus_points": era.get("bonus_points", {}),  # {"fall": N, "tech_fall": N, "major_decision": N}
    }


def build_standard_bracket(
    entrants: int,
    places_awarded: int,
    consolation_style: str = "single_backside",
    gender: str | None = None,
    scoring: dict | None = None,
) -> dict:
    """
    Build a full bracket template dict matching the data/bracket_templates/ schema.

    Every match slot gets a `win_points` value (points the winner's team earns for
    that specific win) and every entry in `placement_map` carries both `place` and
    `points` for the winner/loser of that placement match — all directly hand-editable
    in the saved JSON. If `scoring` isn't passed explicitly, it's loaded from
    data/team_scoring_eras/hs_ky_{gender}.json (falls back to nulls if unavailable).
    """
    if scoring is None and gender is not None:
        scoring = _load_default_scoring(gender)

    if consolation_style not in STYLE_ABBREV:
        raise ValueError(f"unknown consolation_style {consolation_style!r}")
    if consolation_style == "double_backside_crossover":
        raise NotImplementedError(
            "double_backside_crossover is not yet implemented — hand-author this "
            "template's JSON directly against the schema if a historical bracket "
            "genuinely needs true crossover-avoidance wiring (see xtp/engine/bracket_schema.py "
            "for the closest reference, a hardcoded NCAA 33-man version of this style)."
        )

    champ_slots, champ_rounds, champ_round_defs = build_championship(entrants)

    if consolation_style == "none":
        if places_awarded != 2:
            raise ValueError('consolation_style "none" only supports places_awarded=2')
        cons_slots, cons_round_defs, placement_extra = {}, [], {}
    else:
        cons_slots, cons_round_defs, placement_extra = build_consolation_single_backside(
            places_awarded, champ_slots, champ_rounds
        )

    all_slots = {**champ_slots, **cons_slots}
    placement_map = {champ_rounds[-1][0]: {"winner": 1, "loser": 2}, **placement_extra}
    entrant_slots = [f"ENTRANT_{i}" for i in range(1, entrants + 1)]
    style_abbrev = STYLE_ABBREV[consolation_style]
    template_id = f"ky_state_{entrants}e_{places_awarded}p_{style_abbrev}_v1"

    # win_points: flat default per bracket side (champ/consol), same for every round.
    # Hand-edit individual slots afterward if a specific round should score differently.
    win_points = scoring["win_points"] if scoring else {}
    for slot in all_slots.values():
        key = "champ_win" if slot["bracket"] == "champ" else "cons_win"
        slot["win_points"] = win_points.get(key)

    # Medal-round matches (1st/3rd/5th/7th place matches -- every slot in placement_map)
    # earn no advancement points, only placement points, to avoid double-counting a win
    # that's already scored via placement.
    medal_round_points = win_points.get("medal_round_win", 0)
    for sid in placement_map:
        all_slots[sid]["win_points"] = medal_round_points

    # placement_map: always {"winner": {"place", "points"}, "loser": {"place", "points"}}.
    placement_points = scoring["placement_points"] if scoring else {}
    for pm in placement_map.values():
        for role in ("winner", "loser"):
            place = pm[role]
            pm[role] = {"place": place, "points": placement_points.get(str(place))}

    # bonus_points lives at the template top level (not per-slot) since it applies based
    # on the match METHOD entered during transcription, not on which round/slot it was.
    bonus_points = scoring["bonus_points"] if scoring else {}

    return {
        "template_id": template_id,
        "bracket_size": entrants,
        "places_awarded": places_awarded,
        "consolation_style": consolation_style,
        "rounds": champ_round_defs + cons_round_defs,
        "slots": all_slots,
        "placement_map": placement_map,
        "bonus_points": bonus_points,
        "entrant_slots": entrant_slots,
        "provenance": {
            "generated_by": (
                f"template_builder.py --entrants {entrants} --places {places_awarded} "
                f"--consolation-style {consolation_style} --gender {gender}"
            ),
            "hand_edited": False,
            "scoring_source": (
                f"data/team_scoring_eras/hs_ky_{gender}.json — edit values directly "
                "in this file to change scoring for this season/era"
                if scoring else None
            ),
        },
    }


# ---------------------------------------------------------------------------
# Validation (used by --self-test and after every build)
# ---------------------------------------------------------------------------

def validate_template(template: dict) -> list[str]:
    """Return a list of problems found (empty list = valid)."""
    problems = []
    slots = template["slots"]
    entrant_slots = set(template["entrant_slots"])
    places_awarded = template["places_awarded"]

    referenced_entrants = set()
    for sid, slot in slots.items():
        for inp in slot["inputs"]:
            if inp in entrant_slots:
                referenced_entrants.add(inp)
            elif inp.endswith("_WINNER") or inp.endswith("_LOSER"):
                src = inp.rsplit("_", 1)[0]
                if src not in slots:
                    problems.append(f"{sid}: input {inp!r} references unknown slot {src!r}")
            else:
                problems.append(f"{sid}: unrecognized input {inp!r}")

        for target_field in ("winner_to", "loser_to"):
            target = slot[target_field]
            if target is None:
                continue
            if target.startswith("PLACE_"):
                continue
            if target not in slots:
                problems.append(f"{sid}: {target_field} {target!r} is not a known slot id")

    missing_entrants = entrant_slots - referenced_entrants
    if missing_entrants:
        problems.append(f"entrant slots never referenced as an input: {sorted(missing_entrants)}")

    placed = sorted({v["winner"]["place"] for v in template["placement_map"].values()} |
                     {v["loser"]["place"] for v in template["placement_map"].values()})
    expected = list(range(1, places_awarded + 1))
    if placed != expected:
        problems.append(f"placement_map covers places {placed}, expected {expected}")

    return problems


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_template(template: dict) -> Path:
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    path = TEMPLATES_DIR / f"{template['template_id']}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(template, f, indent=2)
        f.write("\n")
    return path


def register_template(template_id: str, entrants: int, places: int, gender: str,
                       first_season: int, last_season: int | None, notes: str | None = None) -> None:
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    index = {"templates": []}
    if INDEX_PATH.exists():
        with INDEX_PATH.open(encoding="utf-8") as f:
            index = json.load(f)

    entry = {
        "template_id": template_id,
        "entrants": entrants,
        "places": places,
        "first_season": first_season,
        "last_season": last_season,
        "gender": gender,
    }
    if notes:
        entry["notes"] = notes

    for existing in index["templates"]:
        if (existing["template_id"] == template_id and existing["gender"] == gender
                and existing["first_season"] == first_season and existing["last_season"] == last_season):
            print(f"  [skip] registry already has {template_id} for {gender} {first_season}-{last_season}")
            return

    index["templates"].append(entry)
    with INDEX_PATH.open("w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)
        f.write("\n")
    print(f"  Registered {template_id} for {gender} seasons {first_season}-{last_season or 'present'}")


def print_summary(template: dict) -> None:
    print(f"\ntemplate_id: {template['template_id']}")
    print(f"entrants={template['bracket_size']} places_awarded={template['places_awarded']} "
          f"style={template['consolation_style']}")
    for rd in template["rounds"]:
        sample_wp = template["slots"][rd["slots"][0]].get("win_points")
        print(f"  [{rd['bracket']:6s}] {rd['round_id']:16s} {rd['label']:20s} "
              f"{len(rd['slots'])} match(es)  win_points={sample_wp}")
    print("  placement_map:")
    for sid, pm in sorted(template["placement_map"].items(), key=lambda kv: kv[1]["winner"]["place"]):
        w, l = pm["winner"], pm["loser"]
        print(f"    {sid}: winner -> place {w['place']} ({w['points']} pts), "
              f"loser -> place {l['place']} ({l['points']} pts)")


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def self_test() -> None:
    cases = [
        (4, 4), (8, 4), (8, 6), (16, 6), (16, 8), (32, 8), (64, 8), (2, 2),
    ]
    failures = 0
    for entrants, places in cases:
        try:
            tmpl = build_standard_bracket(
                entrants, places, "single_backside" if places > 2 else "none", gender="boys"
            )
            problems = validate_template(tmpl)
        except Exception as e:  # noqa: BLE001 — self-test wants to report, not raise
            print(f"[FAIL] entrants={entrants} places={places}: raised {e}")
            failures += 1
            continue
        if problems:
            print(f"[FAIL] entrants={entrants} places={places}:")
            for p in problems:
                print(f"    - {p}")
            failures += 1
        else:
            print(f"[OK]   entrants={entrants} places={places} "
                  f"({len(tmpl['rounds'])} rounds, {len(tmpl['slots'])} slots)")
    print(f"\n{len(cases) - failures}/{len(cases)} cases passed")
    if failures:
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Build a historical KY bracket template")
    parser.add_argument("--entrants", type=int, help="bracket size, power of 2 (e.g. 16, 32)")
    parser.add_argument("--places", type=int, help="places awarded: 2, 4, 6, or 8")
    parser.add_argument("--consolation-style", default="single_backside",
                         choices=["none", "single_backside", "double_backside_crossover"])
    parser.add_argument("--gender", choices=["boys", "girls"])
    parser.add_argument("--first-season", type=int)
    parser.add_argument("--last-season", type=int, default=None,
                         help="omit for an open-ended/current era")
    parser.add_argument("--notes", default=None)
    parser.add_argument("--dry-run", action="store_true", help="print only, don't write/register")
    parser.add_argument("--self-test", action="store_true", help="run internal validation cases and exit")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return

    if not args.entrants or not args.places or not args.gender or not args.first_season:
        parser.error("--entrants, --places, --gender, and --first-season are required "
                      "(unless --self-test)")

    template = build_standard_bracket(args.entrants, args.places, args.consolation_style, gender=args.gender)
    problems = validate_template(template)
    if problems:
        print("[FAIL] generated template did not validate:")
        for p in problems:
            print(f"  - {p}")
        raise SystemExit(1)

    print_summary(template)

    if args.dry_run:
        print("\n[dry-run] not saving or registering")
        return

    path = save_template(template)
    print(f"\nSaved -> {path}")
    register_template(
        template["template_id"], args.entrants, args.places, args.gender,
        args.first_season, args.last_season, args.notes,
    )


if __name__ == "__main__":
    main()
