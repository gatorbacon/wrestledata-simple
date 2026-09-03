#!/usr/bin/env python3
"""
Interactive wizard to transcribe one historical KY state bracket (one weight
class) against an already-built bracket template (see template_builder.py).

Walks the template's rounds in order. For each match, resolves its two
participants (prompting for fresh info the first time an ENTRANT_i slot is
seen; otherwise following the winner/loser of an earlier match), asks for
the winner, and advances both wrestlers according to the template's wiring.
Non-senior wrestlers are looked up against a later, already-scraped season
(2013 by default) and linked into their existing career if found — since
we're working backward from 2012, a 2012 junior IS the 2013 senior already
in the system.

When the bracket is complete, prints the 8 placers with team + points, and
saves a bracket-instance JSON to data/bracket_instances/hs_ky_{gender}/{season}/{weight}.json.

Usage:
    python scripts/historical_brackets/enter_bracket.py --season 2012 --weight 106 --gender boys
    python scripts/historical_brackets/enter_bracket.py --season 2012 --weight 106 --gender boys --resume
"""

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.common import weight_class_eras as era_weight_classes  # noqa: E402

TEMPLATES_DIR = Path("data/bracket_templates")
INSTANCES_DIR = Path("data/bracket_instances")
LEDGER_DIR = Path("data/historical_wrestlers")
TEAM_LISTS_DIR = Path("data/team_lists")
SEASON_ACCOMPLISHMENTS_DIR = Path("data/season_accomplishments")
CAREERS_BOYS_DIR = Path("data/careers")
CAREERS_GIRLS_DIR = Path("data/careers/girls")

BYE = object()  # sentinel for an empty bracket slot


# ---------------------------------------------------------------------------
# Small prompt helpers
# ---------------------------------------------------------------------------

def ask(prompt: str, default: str | None = None) -> str | None:
    raw = input(f"{prompt}{' [' + default + ']' if default else ''}: ").strip()
    if not raw:
        return default
    return raw


def ask_choice(prompt: str, choices: list[str]) -> str:
    while True:
        raw = input(f"{prompt} ({'/'.join(choices)}): ").strip().lower()
        if raw in choices:
            return raw
        print(f"  please enter one of: {', '.join(choices)}")


# ---------------------------------------------------------------------------
# Template / registry
# ---------------------------------------------------------------------------

def find_template(gender: str, season: int) -> dict:
    index_path = TEMPLATES_DIR / "index.json"
    if not index_path.exists():
        raise SystemExit(f"no template registry at {index_path} — run template_builder.py first")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    matches = [
        t for t in index["templates"]
        if t["gender"] == gender and t["first_season"] <= season
        and (t["last_season"] is None or season <= t["last_season"])
    ]
    if not matches:
        raise SystemExit(f"no registered template covers gender={gender} season={season}")
    if len(matches) > 1:
        print(f"[WARN] multiple templates match {gender}/{season}, using the first: {matches[0]['template_id']}")
    template_id = matches[0]["template_id"]
    path = TEMPLATES_DIR / f"{template_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Team list — fuzzy match + inline "add new team"
# ---------------------------------------------------------------------------

def load_teams(gender: str) -> list[dict]:
    path = TEAM_LISTS_DIR / f"hs_ky_{gender}" / "teams.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_teams(gender: str, teams: list[dict]) -> None:
    path = TEAM_LISTS_DIR / f"hs_ky_{gender}" / "teams.json"
    path.write_text(json.dumps(teams, indent=2) + "\n", encoding="utf-8")


def _team_candidates(raw_name: str, teams_cache: list[dict]) -> list[str]:
    """
    Abbreviation match first (handles bracket sheets that only print 'CENT', 'MEAD',
    etc.), then substring lookup (handles 'Meade' -> 'Meade County'), then fuzzy fallback.
    """
    raw_lower = raw_name.lower()
    names = [t["name"] for t in teams_cache]

    abbrev_hits = [t["name"] for t in teams_cache if (t.get("abbreviation") or "").lower() == raw_lower]
    if abbrev_hits:
        return abbrev_hits[:5]  # more than one = a genuine duplicate/ambiguous abbreviation in teams.json

    substring = [n for n in names if raw_lower in n.lower() or n.lower() in raw_lower]
    if substring:
        return substring[:5]
    return difflib.get_close_matches(raw_name, names, n=5, cutoff=0.6)


def resolve_team(raw_name: str, gender: str, teams_cache: list[dict]) -> str:
    """Return a confirmed team name, offering to add it to teams.json if unknown."""
    exact = [t for t in teams_cache if t["name"].lower() == raw_name.lower()]
    if exact:
        return exact[0]["name"]

    candidates = _team_candidates(raw_name, teams_cache)
    if candidates:
        print(f"  team {raw_name!r} not found exactly. Possible matches:")
        for i, c in enumerate(candidates, 1):
            print(f"    [{i}] {c}")
        pick = ask_choice(
            f"  pick a number (1-{len(candidates)}), or 'n' for a new team",
            [str(i) for i in range(1, len(candidates) + 1)] + ["n"],
        )
        if pick != "n":
            return candidates[int(pick) - 1]

    confirm = ask_choice(f"  add {raw_name!r} as a new team in teams.json?", ["y", "n"])
    if confirm == "y":
        teams_cache.append({
            "name": raw_name,
            "state": "KY",
            "abbreviation": None,
            "governing_body": "Kentucky High School Athletic Association",
            "division": f"KY HS {'Girls' if gender == 'girls' else 'Boys'}",
            "url": None,
        })
        save_teams(gender, teams_cache)
        print(f"  added {raw_name!r} to data/team_lists/hs_ky_{gender}/teams.json")
    return raw_name


# ---------------------------------------------------------------------------
# Career linking against an already-scraped later season
# ---------------------------------------------------------------------------

def careers_dir(gender: str) -> Path:
    return CAREERS_GIRLS_DIR if gender == "girls" else CAREERS_BOYS_DIR


def build_link_index(gender: str, link_season: int) -> dict[str, list[dict]]:
    """{normalized_last_name: [{career_id, canonical_name, team, grade, wrestler_id}, ...]}"""
    acc_path = SEASON_ACCOMPLISHMENTS_DIR / gender / str(link_season) / "season_accomplishments.json"
    by_wrestler_id = {}
    if acc_path.exists():
        acc = json.loads(acc_path.read_text(encoding="utf-8"))
        for w in acc.get("wrestlers", []):
            by_wrestler_id[w["season_wrestler_id"]] = w

    index: dict[str, list[dict]] = {}
    d = careers_dir(gender)
    print(f"  Building {link_season} link index from {d}/ ...")
    for path in d.glob("career_*.json"):
        career = json.loads(path.read_text(encoding="utf-8"))
        wid = career.get("seasons", {}).get(str(link_season))
        if not wid:
            continue
        w = by_wrestler_id.get(wid, {})
        last_name = career["canonical_name"].split()[-1].lower() if career.get("canonical_name") else ""
        entry = {
            "career_id": career["career_id"],
            "canonical_name": career["canonical_name"],
            "team": w.get("team"),
            "grade": w.get("grade"),
            "wrestler_id": wid,
        }
        index.setdefault(last_name, []).append(entry)
    print(f"  Indexed {sum(len(v) for v in index.values())} {link_season} wrestlers with careers.")
    return index


def find_link_candidates(first: str | None, last: str | None, team: str | None,
                          index: dict[str, list[dict]]) -> list[dict]:
    if not last:
        return []
    last_norm = last.lower()
    candidates = index.get(last_norm, [])
    if not candidates:
        close_keys = difflib.get_close_matches(last_norm, index.keys(), n=3, cutoff=0.8)
        for k in close_keys:
            candidates.extend(index[k])

    def score(c: dict) -> float:
        s = 0.0
        if team and c.get("team") and c["team"].lower() == team.lower():
            s += 2.0
        if first:
            full_guess = f"{first} {last}".lower()
            s += difflib.SequenceMatcher(None, full_guess, c["canonical_name"].lower()).ratio()
        return s

    return sorted(candidates, key=score, reverse=True)[:5]


def next_career_id(gender: str) -> str:
    max_n = 0
    for p in careers_dir(gender).glob("career_*.json"):
        m = re.match(r"career_(\d+)", p.stem)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"career_{max_n + 1:06d}"


def create_new_career(gender: str, name: str, season: int, hw_id: str) -> str:
    career_id = next_career_id(gender)
    path = careers_dir(gender) / f"{career_id}.json"
    career = {
        "career_id": career_id,
        "canonical_name": name,
        "name_norm": re.sub(r"\s+", " ", name.strip().lower()),
        "created_from_season": season,
        "seasons": {str(season): hw_id},
        "notes": None,
    }
    path.write_text(json.dumps(career, indent=2) + "\n", encoding="utf-8")
    return career_id


def link_into_existing_career(gender: str, career_id: str, season: int, hw_id: str) -> None:
    path = careers_dir(gender) / f"{career_id}.json"
    career = json.loads(path.read_text(encoding="utf-8"))
    existing = career["seasons"].get(str(season))
    if existing and existing != hw_id:
        print(f"  [WARN] {career_id} already has a {season} season ({existing}) — not overwriting")
        return
    career["seasons"][str(season)] = hw_id
    path.write_text(json.dumps(career, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# HW id ledger
# ---------------------------------------------------------------------------

def ledger_path(gender: str) -> Path:
    return LEDGER_DIR / f"hs_ky_{gender}" / "ledger.json"


def load_ledger(gender: str) -> dict:
    path = ledger_path(gender)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_ledger(gender: str, ledger: dict) -> None:
    path = ledger_path(gender)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")


def mint_hw_id(gender: str, ledger: dict) -> str:
    prefix = "HW_G" if gender == "girls" else "HW_B"
    max_n = 0
    for key in ledger:
        m = re.match(rf"{prefix}_(\d+)", key)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"{prefix}_{max_n + 1:06d}"


# ---------------------------------------------------------------------------
# Wrestler entry
# ---------------------------------------------------------------------------

def prompt_wrestler(entrant_ref: str, season: int, gender: str, link_season: int,
                     link_index: dict, teams_cache: list[dict], ledger: dict) -> dict | object:
    print(f"\n--- {entrant_ref} ---")
    raw = ask("  name (First Last), or 'bye'")
    if raw is None or raw.strip().lower() == "bye":
        print("  -> BYE")
        return BYE

    parts = raw.split()
    first = " ".join(parts[:-1]) if len(parts) > 1 else None
    last = parts[-1] if parts else None
    if not first:
        first = ask("  first name (blank if unknown)")
    if not last:
        last = ask("  last name")

    team_raw = ask("  team")
    team = resolve_team(team_raw, gender, teams_cache) if team_raw else None
    grade_raw = ask("  grade (9-12)")
    grade = int(grade_raw) if grade_raw and grade_raw.isdigit() else None
    record = ask("  record (e.g. 34-10)")

    name = f"{first} {last}".strip() if first else (last or "Unknown")
    partial_name = not bool(first)

    career_id = None
    if grade != 12:
        candidates = find_link_candidates(first, last, team, link_index)
        if candidates:
            print(f"  Possible {link_season} matches for {name!r}:")
            for i, c in enumerate(candidates, 1):
                print(f"    [{i}] {c['canonical_name']} ({c['team']}, grade {c['grade']}) -> {c['career_id']}")
            pick = ask("  link to one of these? (number, or blank for new career)")
            if pick and pick.isdigit() and 1 <= int(pick) <= len(candidates):
                career_id = candidates[int(pick) - 1]["career_id"]

    hw_id = mint_hw_id(gender, ledger)
    if career_id:
        link_into_existing_career(gender, career_id, season, hw_id)
        status = "linked"
    else:
        career_id = create_new_career(gender, name, season, hw_id)
        status = "new_career"

    ledger[hw_id] = {
        "name": name, "team": team, "season": season, "weight_class": None,
        "partial_name": partial_name, "status": status, "career_id": career_id,
    }
    save_ledger(gender, ledger)

    print(f"  -> {name} ({team}) grade={grade} record={record} career={career_id} [{status}]")
    return {
        "name": name, "first_name": first, "last_name": last, "team": team,
        "grade": grade, "record": record, "partial_name": partial_name,
        "historical_wrestler_id": hw_id, "career_id": career_id,
    }


# ---------------------------------------------------------------------------
# Bracket runner
# ---------------------------------------------------------------------------

def run_bracket(template: dict, season: int, weight: int, gender: str, link_season: int,
                 instance_path: Path, resume: dict | None) -> dict:
    slots = template["slots"]
    wrestlers: dict[str, dict | object] = {}   # ENTRANT_i -> wrestler dict or BYE
    match_results: dict[str, dict] = {}        # slot_id -> {winner, loser, method, score_text, round_label}

    if resume:
        wrestlers = {k: (BYE if v == "BYE" else v) for k, v in resume.get("entrants", {}).items()}
        match_results = resume.get("results", {})
        print(f"Resuming: {len(wrestlers)} entrants, {len(match_results)} matches already recorded.")

    ledger = load_ledger(gender)
    teams_cache = load_teams(gender)
    link_index = build_link_index(gender, link_season)

    round_label_by_slot = {}
    for rd in template["rounds"]:
        for sid in rd["slots"]:
            round_label_by_slot[sid] = rd["label"]

    def resolve_atomic(ref: str) -> str | None:
        if ref.startswith("ENTRANT_"):
            return ref
        for suffix, key in (("_WINNER", "winner"), ("_LOSER", "loser")):
            if ref.endswith(suffix):
                src = ref[: -len(suffix)]
                return match_results.get(src, {}).get(key)
        raise ValueError(f"unrecognized input ref {ref!r}")

    def get_participant(ref: str) -> dict | None:
        atomic = resolve_atomic(ref)
        if atomic is None:
            return None
        if atomic not in wrestlers:
            wrestlers[atomic] = prompt_wrestler(atomic, season, gender, link_season, link_index, teams_cache, ledger)
            _save_progress(instance_path, template, season, weight, gender, wrestlers, match_results)
        w = wrestlers[atomic]
        return None if w is BYE else {**w, "_ref": atomic}

    for rd in template["rounds"]:
        for sid in rd["slots"]:
            if sid in match_results:
                continue
            slot = slots[sid]
            p1 = get_participant(slot["inputs"][0])
            p2 = get_participant(slot["inputs"][1])

            if p1 is None and p2 is None:
                match_results[sid] = {"winner": None, "loser": None, "method": None,
                                       "score_text": None, "round_label": rd["label"]}
                continue
            if p1 is None or p2 is None:
                sole = p1 or p2
                print(f"\n{rd['label']} [{sid}]: {sole['name']} advances on a bye")
                match_results[sid] = {"winner": sole["_ref"], "loser": None, "method": "bye",
                                       "score_text": None, "round_label": rd["label"]}
                _save_progress(instance_path, template, season, weight, gender, wrestlers, match_results)
                continue

            print(f"\n{rd['label']} [{sid}]: (1) {p1['name']} ({p1['team']})  vs  (2) {p2['name']} ({p2['team']})")
            pick = ask_choice("  winner", ["1", "2"])
            winner, loser = (p1, p2) if pick == "1" else (p2, p1)
            method = ask("  method (fall/tf/md/dec/ff/dq/inj/default, blank to skip)")
            score_text = ask("  score/time (blank to skip)")
            match_results[sid] = {
                "winner": winner["_ref"], "loser": loser["_ref"], "method": method,
                "score_text": score_text, "round_label": rd["label"],
            }
            _save_progress(instance_path, template, season, weight, gender, wrestlers, match_results)

    return {"wrestlers": wrestlers, "match_results": match_results}


def run_bracket_batch(template: dict, season: int, weight: int, gender: str,
                       instance_path: Path, spec: dict) -> dict:
    """
    Non-interactive counterpart to run_bracket(). Takes a flat spec instead of
    prompting over stdin:
      spec["entrants"][ENTRANT_i] = {"name", "team", "grade", "record",
                                      "link": "career_XXXXXX" | "new" | null}
      spec["results"][slot_id]    = {"winner": ENTRANT_ref, "method", "score_text"}
    "link" omitted/null/"new" always creates a new career (no candidate search —
    do that research up front and put the decision directly in the spec).
    Existing wrestlers/results dicts are NOT reused across calls; this is meant
    to build a whole instance in one shot from fully-known data.
    """
    slots = template["slots"]
    ledger = load_ledger(gender)
    teams_cache = load_teams(gender)
    wrestlers: dict[str, dict | object] = {}
    match_results: dict[str, dict] = {}

    for ref, e in spec["entrants"].items():
        if e is None or (isinstance(e, str) and e.upper() == "BYE"):
            wrestlers[ref] = BYE
            continue
        team = resolve_team(e["team"], gender, teams_cache) if e.get("team") else None
        hw_id = mint_hw_id(gender, ledger)
        link = e.get("link")
        if link and link != "new":
            link_into_existing_career(gender, link, season, hw_id)
            career_id, status = link, "linked"
        else:
            career_id = create_new_career(gender, e["name"], season, hw_id)
            status = "new_career"
        ledger[hw_id] = {
            "name": e["name"], "team": team, "season": season, "weight_class": weight,
            "partial_name": bool(e.get("partial_name", False)), "status": status, "career_id": career_id,
        }
        wrestlers[ref] = {
            "name": e["name"], "first_name": e.get("first_name"), "last_name": e.get("last_name"),
            "team": team, "grade": e.get("grade"), "record": e.get("record"),
            "partial_name": bool(e.get("partial_name", False)),
            "historical_wrestler_id": hw_id, "career_id": career_id,
        }
    save_ledger(gender, ledger)

    def resolve_atomic(ref: str) -> str | None:
        if ref.startswith("ENTRANT_"):
            return ref
        for suffix, key in (("_WINNER", "winner"), ("_LOSER", "loser")):
            if ref.endswith(suffix):
                return match_results.get(ref[: -len(suffix)], {}).get(key)
        raise ValueError(f"unrecognized input ref {ref!r}")

    for rd in template["rounds"]:
        for sid in rd["slots"]:
            slot = slots[sid]
            a = resolve_atomic(slot["inputs"][0])
            b = resolve_atomic(slot["inputs"][1])
            pa = None if a is None or wrestlers.get(a) is BYE else a
            pb = None if b is None or wrestlers.get(b) is BYE else b
            if pa is None and pb is None:
                match_results[sid] = {"winner": None, "loser": None, "method": None,
                                       "score_text": None, "round_label": rd["label"]}
                continue
            if pa is None or pb is None:
                sole = pa or pb
                match_results[sid] = {"winner": sole, "loser": None, "method": "bye",
                                       "score_text": None, "round_label": rd["label"]}
                continue
            r = spec["results"].get(sid)
            if not r:
                raise SystemExit(f"missing result for {sid} ({a} vs {b})")
            winner = r["winner"]
            loser = b if winner == a else a
            if winner not in (a, b):
                raise SystemExit(f"{sid}: winner {winner!r} is not one of {a!r}/{b!r}")
            match_results[sid] = {
                "winner": winner, "loser": loser, "method": r.get("method"),
                "score_text": r.get("score_text"), "round_label": rd["label"],
            }

    _save_progress(instance_path, template, season, weight, gender, wrestlers, match_results)
    return {"wrestlers": wrestlers, "match_results": match_results}


def _save_progress(instance_path: Path, template: dict, season: int, weight: int, gender: str,
                    wrestlers: dict, match_results: dict) -> None:
    entrants_out = {}
    for ref, w in wrestlers.items():
        entrants_out[ref] = "BYE" if w is BYE else w
    instance = {
        "instance_id": f"hs_ky_{gender}_{season}_{weight}",
        "template_id": template["template_id"],
        "season": season, "gender": gender, "weight_class": weight,
        "entrants": entrants_out,
        "results": match_results,
    }
    instance_path.parent.mkdir(parents=True, exist_ok=True)
    instance_path.write_text(json.dumps(instance, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Final report
# ---------------------------------------------------------------------------

METHOD_TO_BONUS_KEY = {"fall": "fall", "tf": "tech_fall", "md": "major_decision"}


def print_final_report(template: dict, wrestlers: dict, match_results: dict) -> None:
    slots = template["slots"]
    bonus_table = template.get("bonus_points", {})
    adv_totals: dict[str, float] = {}
    bonus_totals: dict[str, float] = {}
    for sid, res in match_results.items():
        winner = res.get("winner")
        if not winner or res.get("method") == "bye":
            continue
        adv = slots[sid].get("win_points") or 0
        adv_totals[winner] = adv_totals.get(winner, 0) + adv
        bonus_key = METHOD_TO_BONUS_KEY.get((res.get("method") or "").lower())
        if bonus_key:
            bonus_totals[winner] = bonus_totals.get(winner, 0) + bonus_table.get(bonus_key, 0)

    placements = []  # (place, ref, points_from_placement_match)
    for sid, pm in template["placement_map"].items():
        res = match_results.get(sid)
        if not res:
            continue
        if res.get("winner"):
            placements.append((pm["winner"]["place"], res["winner"], pm["winner"]["points"]))
        if res.get("loser"):
            placements.append((pm["loser"]["place"], res["loser"], pm["loser"]["points"]))

    placements.sort(key=lambda t: t[0])

    print("\n" + "=" * 60)
    print(f"FINAL PLACEMENTS — {template['template_id']}")
    print("=" * 60)
    for place, ref, place_points in placements:
        w = wrestlers.get(ref)
        if w is BYE or w is None:
            continue
        adv = adv_totals.get(ref, 0)
        bonus = bonus_totals.get(ref, 0)
        total = adv + bonus + (place_points or 0)
        print(f"  {place}. {w['name']:25s} ({w['team']:20s}) career={w['career_id']:14s} "
              f"adv={adv:g} + bonus={bonus:g} + placement={place_points}  = {total:g} pts")
    print("\n(adv = advancement points per win: championship-bracket wins and consolation-")
    print(" bracket wins are rated separately per data/team_scoring_eras/hs_ky_{gender}.json,")
    print(" with 0 for the four medal-round matches (1st/3rd/5th/7th place) since those are")
    print(" scored via placement instead. bonus = fall/tech-fall/major-decision points earned")
    print(" along the way. Non-placers still earn adv+bonus for their team but aren't listed")
    print(" here — full team totals are computed later by compute_team_standings.py.)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Transcribe one historical KY bracket")
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--weight", type=int, required=True)
    parser.add_argument("--gender", choices=["boys", "girls"], required=True)
    parser.add_argument("--link-season", type=int, default=None,
                         help="already-scraped season to link non-seniors against (default: season+1)")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--batch-json", type=str, default=None,
                         help="path to a {entrants, results} spec — build the whole instance "
                              "non-interactively instead of prompting over stdin")
    args = parser.parse_args()

    link_season = args.link_season or (args.season + 1)
    valid_weights = era_weight_classes.get_weight_classes_for_season(args.gender, args.season)
    if args.weight not in valid_weights:
        print(f"[WARN] {args.weight} is not in the known {args.season} {args.gender} weight list: {valid_weights}")

    template = find_template(args.gender, args.season)
    instance_path = INSTANCES_DIR / f"hs_ky_{args.gender}" / str(args.season) / f"{args.weight}.json"

    if args.batch_json:
        if instance_path.exists() and not args.resume:
            raise SystemExit(f"{instance_path} already exists — remove it or pass --resume")
        spec = json.loads(Path(args.batch_json).read_text(encoding="utf-8"))
        result = run_bracket_batch(template, args.season, args.weight, args.gender, instance_path, spec)
        print_final_report(template, result["wrestlers"], result["match_results"])
        print(f"\nSaved -> {instance_path}")
        return

    resume = None
    if args.resume:
        if not instance_path.exists():
            raise SystemExit(f"--resume given but no existing file at {instance_path}")
        resume = json.loads(instance_path.read_text(encoding="utf-8"))
    elif instance_path.exists():
        raise SystemExit(f"{instance_path} already exists — pass --resume to continue it")

    result = run_bracket(template, args.season, args.weight, args.gender, link_season, instance_path, resume)
    print_final_report(template, result["wrestlers"], result["match_results"])
    print(f"\nSaved -> {instance_path}")


if __name__ == "__main__":
    main()
