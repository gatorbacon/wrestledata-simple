#!/usr/bin/env python3
"""
Read-only audit: find HS wrestler-seasons that have matches but are NOT linked to any career file.

Why: `link_season_interactive.py` is a manual pass per season and can skip wrestlers (found 2026-09-21: Josh Tuttle's
2024 season had 29 matches, a season profile and an accomplishments entry, but no link in career_000839, so his career
page skipped a year and his career record was short). A wrestler-season is "unlinked" when its `season_wrestler_id`
(from mt/processed_data roster) is not in the `seasons` dict of any backend career file
(data/careers/career_*.json for boys, data/careers/girls/ for girls). Roster entries with 0 matches are ignored
(TrackWrestling lists many wrestlers who never wrestled; they don't need a career).

For each unlinked wrestler-season it proposes:
  AUTO     exact normalized-name match to exactly ONE career that lacks that season AND has a season within +/-3 years on
           the SAME team AND a plausible grade progression (or unknown grade). Safe to link in bulk.
  REVIEW   anything else that has a candidate: several same-team careers (possible duplicate careers), a transfer
           (name + grade fit but team changed), a name variant (Josh/Joshua, Brayden/Braydon), exact name with no team or
           grade support (usually a different person with the same name).
  NONE     no plausible existing career (new wrestler, or a name too different to guess) - would need a NEW career.

Usage (from repo root):
    .venv/bin/python scripts/careers/audit_unlinked_seasons.py                    # report to stdout
    .venv/bin/python scripts/careers/audit_unlinked_seasons.py --gender boys --write-plan plan.json
The plan file (AUTO entries only) is what `link_seasons_batch.py --plan plan.json` applies. Nothing is written by the audit itself
besides the optional plan file.
"""
import argparse
import collections
import difflib
import glob
import json
import re
import sys
from pathlib import Path

GRADES = {"7th": 7, "8th": 8, "Fr.": 9, "So.": 10, "Jr.": 11, "Sr.": 12}
CAREER_DIRS = {"boys": Path("data/careers"), "girls": Path("data/careers/girls")}
PROCESSED = {"boys": "hs_ky_boys", "girls": "hs_ky_girls"}
SEASONS = range(2013, 2027)


def norm(name):
    return re.sub(r"[^a-z ]", "", (name or "").lower()).strip()


def norm_team(team):
    return re.sub(r"\b(high school|hs)\b", "", (team or "").lower()).strip()


def grade_num(g):
    if g is None:
        return None
    return GRADES.get(g) or (int(g) if str(g).isdigit() else None)


def load_roster(gender):
    """(season, season_wrestler_id) -> dict(team, name, grade, n_matches)"""
    info = {}
    for y in SEASONS:
        for f in glob.glob(f"mt/processed_data/{PROCESSED[gender]}/{y}/*.json"):
            try:
                d = json.load(open(f, encoding="utf-8"))
            except Exception:
                continue
            for w in d.get("roster", []):
                info[(y, str(w.get("season_wrestler_id")))] = dict(
                    team=d.get("team_name"), name=w.get("name") or "", grade=grade_num(w.get("grade")),
                    n=len(w.get("matches", [])), wc=w.get("weight_class"))
    return info


def load_careers(gender):
    out = {}
    for f in glob.glob(str(CAREER_DIRS[gender] / "career_*.json")):
        c = json.load(open(f, encoding="utf-8"))
        out[c["career_id"]] = c
    return out


def first_names_similar(a, b):
    if a == b:
        return True
    if len(a) >= 3 and len(b) >= 3 and (a.startswith(b[:3]) or b.startswith(a[:3])):
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.8


def near_seasons(career, info, season, max_dist=3):
    """the career's linked seasons within max_dist years, as (year, roster info)"""
    res = []
    for y, i in career["seasons"].items():
        inf = info.get((int(y), str(i)))
        if inf and abs(int(y) - season) <= max_dist:
            res.append((int(y), inf))
    return res


def support(career, info, orphan):
    """(team_same, grade_ok, nearest_year) of the orphan vs the career's nearby seasons."""
    near = near_seasons(career, info, orphan["season"])
    if not near:
        return False, False, None
    team_same = any(norm_team(inf["team"]) == norm_team(orphan["team"]) for _, inf in near)
    og = orphan["grade"]
    grade_ok = og is None
    for y, inf in near:
        if og is None or inf["grade"] is None:
            grade_ok = True
        elif abs((og - inf["grade"]) - (orphan["season"] - y)) <= 1:
            grade_ok = True
    return team_same, grade_ok, min(near, key=lambda t: abs(t[0] - orphan["season"]))[0]


def audit(gender):
    info = load_roster(gender)
    careers = load_careers(gender)
    linked = {(int(y), str(i)) for c in careers.values() for y, i in c["seasons"].items()}
    by_name = collections.defaultdict(list)
    by_last = collections.defaultdict(list)
    for c in careers.values():
        by_name[c["name_norm"]].append(c)
        toks = norm(c["canonical_name"]).split()
        if toks:
            by_last[toks[-1]].append(c)

    results = []
    for (y, i), inf in info.items():
        if inf["n"] == 0 or (y, i) in linked:
            continue
        o = dict(gender=gender, season=y, id=i, name=inf["name"], team=inf["team"], grade=inf["grade"], n=inf["n"], wc=inf["wc"])
        toks = norm(o["name"]).split()
        exact = [c for c in by_name.get(norm(o["name"]), []) if str(y) not in c["seasons"]]
        entry = dict(o=o, kind=None, cands=[])
        if exact:
            rows = [(c,) + support(c, info, o)[:2] for c in exact]
            same_team = [r for r in rows if r[1]]
            good = [r for r in same_team if r[2]]
            if len(good) == 1 and len(same_team) == 1:
                entry["kind"], entry["cands"] = "AUTO", [(good[0][0]["career_id"], "exact name + same team + grade fits")]
            elif len(same_team) > 1:
                entry["kind"], entry["cands"] = "REVIEW", [(r[0]["career_id"], "several careers with this name+team (duplicate careers?)") for r in same_team]
            elif same_team:
                entry["kind"], entry["cands"] = "REVIEW", [(same_team[0][0]["career_id"], "exact name + same team but grade does not fit")]
            else:
                why = lambda r: ("transfer? name+grade fit, team differs" if r[2] else "exact name only (team AND grade differ - likely a different person)")
                entry["kind"], entry["cands"] = "REVIEW", [(r[0]["career_id"], why(r)) for r in rows]
        elif toks:
            first, last = toks[0], toks[-1]
            fuzzy = []
            pool = list(by_last.get(last, []))
            # last-name spelling variants (Linton/Linton) via close matches on the last-name key
            for ln in difflib.get_close_matches(last, by_last.keys(), n=4, cutoff=0.85):
                if ln != last:
                    pool += by_last[ln]
            seen = set()
            for c in pool:
                if c["career_id"] in seen or str(y) in c["seasons"]:
                    continue
                seen.add(c["career_id"])
                ctoks = norm(c["canonical_name"]).split()
                if not ctoks or not first_names_similar(first, ctoks[0]):
                    continue
                ts, gk, _ = support(c, info, o)
                if ts:
                    fuzzy.append((c["career_id"], f"name variant '{c['canonical_name']}', same team" + ("" if gk else ", grade off")))
            if fuzzy:
                entry["kind"], entry["cands"] = "REVIEW", fuzzy
            else:
                entry["kind"] = "NONE"
        else:
            entry["kind"] = "NONE"
        results.append(entry)
    return results, careers


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gender", choices=["boys", "girls", "both"], default="both")
    ap.add_argument("--write-plan", help="write the AUTO entries as a plan file for link_seasons_batch.py")
    ap.add_argument("--json", help="write the full audit (all kinds) to this JSON file")
    args = ap.parse_args()
    genders = ["boys", "girls"] if args.gender == "both" else [args.gender]

    plan, everything = [], []
    for g in genders:
        res, careers = audit(g)
        print(f"\n=== {g}: {len(res)} unlinked wrestler-seasons with matches ===")
        for kind in ("AUTO", "REVIEW", "NONE"):
            rows = [r for r in res if r["kind"] == kind]
            print(f"  {kind}: {len(rows)}  by season {dict(sorted(collections.Counter(r['o']['season'] for r in rows).items()))}")
        for r in sorted(res, key=lambda r: (r["kind"], r["o"]["season"], r["o"]["name"])):
            o = r["o"]
            if r["kind"] == "AUTO":
                cid, why = r["cands"][0]
                plan.append(dict(gender=g, career_id=cid, season=o["season"], season_wrestler_id=o["id"],
                                 note=f"{o['name']} / {o['team']} / {why}"))
            everything.append({**r, "o": o})
            if r["kind"] != "AUTO":
                cs = "; ".join(f"{cid} {careers[cid]['canonical_name']} {sorted(careers[cid]['seasons'])} ({why})" for cid, why in r["cands"][:3])
                print(f"   [{r['kind']}] {o['season']} {o['name']} | {o['team']} gr{o['grade']} n={o['n']} id={o['id']}" + (f"  ->  {cs}" if cs else ""))
    if args.write_plan:
        Path(args.write_plan).write_text(json.dumps(plan, indent=2), encoding="utf-8")
        print(f"\nWrote {len(plan)} AUTO link(s) to {args.write_plan}")
    if args.json:
        Path(args.json).write_text(json.dumps(everything, indent=2), encoding="utf-8")
        print(f"Wrote full audit to {args.json}")


if __name__ == "__main__":
    sys.exit(main())
