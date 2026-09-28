#!/usr/bin/env python3
"""
NCAA DI adapter for the bracket viewer.

Source : data/ncaa-tourney-parsed/all_matches.json  (one row per match: year, weight,
         round, bracket, seeds/names/teams, result_type, score). Built by
         scripts/ncaa/parse_ncaa_results.py from data/{season}/ncaa-tourney/results.txt.
Output : labs/bracket_viewer/data/ncaa/{year}.json  + labs/bracket_viewer/data/index.json

The viewer engine is format-agnostic: it only reads the normalized schema below, so a new
bracket type (HS state, dual tournament, ...) needs only its own adapter that emits it.

Normalized schema (schema 1)
  event    {id, name, short, format}
  sections [{id, label}]                       e.g. Championship / Consolation
  columns  [{<section id>: label|null}, ...]   shared time-ordered columns; the viewer's
                                               navigator selects a window over these
  brackets [{id, label, matches:[match]}]      one per weight class
  match    {id, s: section id, c: column, r: round code, lbl?: str,
            y: vertical position in "match-slot" units (float, section-local),
            a, b: {n: name, t: team, s: seed|null, f: [matchId, 'W'|'L']|null},
            w: 'a'|'b', res: "MD 11-2"}
  f (feeder) says where that wrestler came from; it is derived by tracing each
  wrestler's previous match, so the wiring is never hand-coded.

Layout rules (NCAA 33-man):
  - Column index is a shared timeline: champ PIG=0 R32=1 R16=2 QF=3 SF=4 Final=5;
    consol C_PIG=1 C_R1=2 C_R2=3 C_R3=4 C_R4=5 C_QF=6 C_SF=7 placement=8.
  - Champ R32 order = order in the parsed file (verified: adjacent pairs feed one R16 match).
    In an R32 match the odd seed sits on top (matches the published 2026 125 bracket:
    1v32, 17v16, 9v24, 25v8, ...). This is a heuristic for slot order only.
  - Every other match: y = mean y of its same-section feeders (else of all feeders).
  - Slot order elsewhere: lower feeder y on top; a drop-in from the other section goes below.

Run: .venv/bin/python labs/bracket_viewer/build_ncaa_bracket_data.py [--year 2026]
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "ncaa-tourney-parsed" / "all_matches.json"
OUT = Path(__file__).resolve().parent / "data"

# round code -> (section, column, chronological tier used only for tracing feeders)
ROUNDS = {
    "PIG": ("champ", 0, 0), "R32": ("champ", 1, 1), "R16": ("champ", 2, 2),
    "QF": ("champ", 3, 3), "SF": ("champ", 4, 4), "Final": ("champ", 5, 5),
    "C_PIG": ("consol", 1, 2), "C_R1": ("consol", 2, 3), "C_R2": ("consol", 3, 4),
    "C_R3": ("consol", 4, 5), "C_R4": ("consol", 5, 6), "C_QF": ("consol", 6, 7),
    "C_SF": ("consol", 7, 8), "3rd": ("consol", 8, 9), "5th": ("consol", 8, 9),
    "7th": ("consol", 8, 9),
}
LABELS = {"Final": "1st place", "3rd": "3rd place", "5th": "5th place", "7th": "7th place"}
COLUMNS = [
    {"champ": "Pigtail", "consol": None},
    {"champ": "Round of 32", "consol": "Cons. pigtail"},
    {"champ": "Round of 16", "consol": "Cons. R1"},
    {"champ": "Quarterfinal", "consol": "Cons. R2"},
    {"champ": "Semifinal", "consol": "Cons. R3"},
    {"champ": "Final", "consol": "Cons. R4"},
    {"champ": None, "consol": "Cons. QF"},
    {"champ": None, "consol": "Cons. SF"},
    {"champ": None, "consol": "Placement"},
]
SECTIONS = [{"id": "champ", "label": "Championship"}, {"id": "consol", "label": "Consolation"}]


def wkey(name, team):
    return f"{name}|{team}"


def result_text(m):
    return f"{m['result_type']} {m['score']}".strip() if m.get("score") else str(m["result_type"])


def build_bracket(rows, warnings, tag):
    """rows: all matches for one (year, weight), in file order."""
    matches = []
    r32_i = 0
    for m in rows:
        code = m["round"]
        if code not in ROUNDS:
            warnings.append(f"{tag}: unknown round {code!r} skipped")
            continue
        sec, col, tier = ROUNDS[code]
        obj = {
            "id": "", "s": sec, "c": col, "r": code, "_tier": tier,
            "a": {"n": m["winner_name"], "t": m["winner_team"], "s": m["winner_seed"], "f": None},
            "b": {"n": m["loser_name"], "t": m["loser_team"], "s": m["loser_seed"], "f": None},
            "w": "a", "res": result_text(m),
        }
        if code in LABELS:
            obj["lbl"] = LABELS[code]
        if code == "R32":
            obj["_leaf"] = r32_i
            r32_i += 1
        matches.append(obj)

    counters = defaultdict(int)
    for obj in matches:
        obj["id"] = f"{obj['r']}-{counters[obj['r']]}"
        counters[obj["r"]] += 1
    by_id = {o["id"]: o for o in matches}

    # feeders: each wrestler's most recent earlier match (by tier)
    appear = defaultdict(list)
    for o in matches:
        for side in ("a", "b"):
            appear[wkey(o[side]["n"], o[side]["t"])].append(o)
    for k, lst in appear.items():
        lst.sort(key=lambda o: o["_tier"])
    for k, lst in appear.items():
        for i, o in enumerate(lst):
            side = "a" if wkey(o["a"]["n"], o["a"]["t"]) == k else "b"
            prev = None
            for p in lst[:i]:
                if p["_tier"] < o["_tier"]:
                    prev = p
            if prev is not None:
                pside = "a" if wkey(prev["a"]["n"], prev["a"]["t"]) == k else "b"
                o[side]["f"] = [prev["id"], "W" if pside == "a" else "L"]

    # ---- y layout ----
    for o in matches:
        if o["r"] == "R32":
            o["y"] = float(o["_leaf"])
    def feeders(o):
        return [by_id[o[s]["f"][0]] for s in ("a", "b") if o[s]["f"]]
    order = sorted(matches, key=lambda o: (o["_tier"], o["c"]))
    for o in order:
        if "y" in o:
            continue
        fs = feeders(o)
        same = [f for f in fs if f["s"] == o["s"] and "y" in f]
        if o["r"] == "C_PIG":                       # sit beside the R32 match the loser came from
            same = [f for f in fs if f["r"] == "R32" and "y" in f]
        elif o["r"] in ("3rd", "5th", "7th"):
            same = [f for f in fs if f["s"] == o["s"] and "y" in f]
        pool = same or [f for f in fs if "y" in f]
        if o["r"] == "C_R1":                        # both feeders are R32 losers / the cons pigtail
            pool = [f for f in fs if "y" in f]
        if not pool:
            o["y"] = None
            continue
        o["y"] = sum(f["y"] for f in pool) / len(pool)
    # pigtail sits beside the R32 match it feeds
    for o in matches:
        if o["r"] == "PIG":
            nxt = [p for p in matches if p["r"] == "R32" and any(
                p[s]["f"] and p[s]["f"][0] == o["id"] for s in ("a", "b"))]
            o["y"] = nxt[0]["y"] if nxt else 0.0
    # placement column: stack 3rd / 5th / 7th so they don't collide
    plc = {o["r"]: o for o in matches if o["r"] in ("3rd", "5th", "7th")}
    csf = [o["y"] for o in matches if o["r"] == "C_SF" and o["y"] is not None]
    base = sum(csf) / len(csf) if csf else 0.0
    for r, dy in (("3rd", -2.0), ("5th", 0.0), ("7th", 2.0)):
        if r in plc:
            plc[r]["y"] = base + dy
    # any match we could not place (data gap): park it after the column's placed matches
    for o in matches:
        if o.get("y") is None:
            warnings.append(f"{tag}: could not place {o['id']} (missing feeder) -> parked")
            col = [p["y"] for p in matches if p["c"] == o["c"] and p["s"] == o["s"] and p.get("y") is not None]
            o["y"] = (max(col) + 1.0) if col else 0.0

    # ---- slot order (top/bottom) ----
    for o in matches:
        a, b = o["a"], o["b"]
        if o["r"] == "R32":
            def odd(x):
                return x["s"] is not None and x["s"] % 2 == 1
            top = a if odd(a) or (not odd(b)) else b
        else:
            def sy(x):
                if not x["f"]:
                    return 1e9
                f = by_id[x["f"][0]]
                same_sec = f["s"] == o["s"]
                return f["y"] + (0 if same_sec else 1e6)
            top = a if sy(a) <= sy(b) else b
        if top is b:
            o["a"], o["b"] = b, a
            o["w"] = "b"
        else:
            o["w"] = "a"
    # strip helpers
    for o in matches:
        for k in [k for k in o if k.startswith("_")]:
            del o[k]
        o["y"] = round(o["y"], 3)
    return matches


def check_tree(matches, warnings, tag):
    """Sanity: each champ R16 match's feeders should be adjacent R32 matches."""
    by_id = {o["id"]: o for o in matches}
    for o in matches:
        if o["r"] != "R16":
            continue
        ys = sorted(by_id[o[s]["f"][0]]["y"] for s in ("a", "b") if o[s]["f"] and o[s]["f"][0] in by_id
                    and by_id[o[s]["f"][0]]["r"] == "R32")
        if len(ys) == 2 and ys[1] - ys[0] != 1.0:
            warnings.append(f"{tag}: R16 {o['id']} feeders not adjacent in file order (y {ys})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=None)
    args = ap.parse_args()
    data = json.loads(SRC.read_text())
    years = sorted({m["year"] for m in data})
    if args.year:
        years = [args.year]
    (OUT / "ncaa").mkdir(parents=True, exist_ok=True)
    warnings, events = [], []
    for y in years:
        weights = sorted({m["weight"] for m in data if m["year"] == y})
        brackets = []
        for w in weights:
            rows = [m for m in data if m["year"] == y and m["weight"] == w]
            tag = f"{y} {w}"
            ms = build_bracket(rows, warnings, tag)
            check_tree(ms, warnings, tag)
            brackets.append({"id": str(w), "label": str(w), "matches": ms})
        ev = {"id": f"ncaa-{y}", "name": f"{y} NCAA Division I Wrestling Championships",
              "short": f"NCAA {y}", "format": "ncaa33"}
        doc = {"schema": 1, "event": ev, "sections": SECTIONS, "columns": COLUMNS, "brackets": brackets}
        (OUT / "ncaa" / f"{y}.json").write_text(json.dumps(doc, separators=(",", ":")))
        events.append({"id": ev["id"], "year": y, "name": ev["short"], "file": f"data/ncaa/{y}.json",
                       "weights": [str(w) for w in weights]})
        print(f"{y}: {len(weights)} weights, {sum(len(b['matches']) for b in brackets)} matches")
    if not args.year:
        (OUT / "index.json").write_text(json.dumps({"events": events}, indent=1))
    print(f"\n{len(warnings)} warnings")
    for w in warnings[:60]:
        print("  ", w)


if __name__ == "__main__":
    main()
