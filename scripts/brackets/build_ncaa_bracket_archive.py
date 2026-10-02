#!/usr/bin/env python3
"""
Builds the NCAA Championships bracket archive for the MatSavant Lab (/lab/brackets/):
one file per tournament year, 1928-2026, in the viewer's format, plus a directory index.

Sources (TJ, 2026-10-01):
  1928-2012  data/ncaa_historical_brackets/data/NCAA{year}.json  (wrestlingstats.com sheets, schema 2.0;
             read data/ncaa_historical_brackets/SPEC.md first -- every rebuild rule below follows it)
  2013-2026  data/ncaa-tourney-parsed/all_matches.json  (our TrackWrestling results; no 2020 tournament)
             The 2013/2014/2016 sheet files are a cross-check only.

Output: frontend/wrestledata-ui/public/lab/brackets/data/{year}.json + index.json

Per-year file
  event   {year, name, host, dates, team_champion, team_champion_label, outstanding_wrestler,
           gorriaran_award, model, model_label, places, source}
  notes   [str]                      year-level notes shown under the title
  team_scores {kind, official, rows:[{rank, tied, team, points, champions}], note}
           kind: "printed" (summary-page top ten), "calculated" (computed from the bouts) or "none"
  weights [{id, label, kind, sections, columns, matches, placements, notes, rounds?}]
           kind "bracket": rendered by the bracket engine (schema below)
           kind "badpoints": `rounds` table (1936, 1948); kind "summary": placements only
  Bracket engine schema (shared with labs/bracket_viewer):
    sections [{id, label}]; columns [{<section id>: label|null}] (a shared left-to-right timeline)
    match {id, s: section, c: column, r: round code, lbl?, y: vertical position (pair units,
           section-local), a, b: {n, t, s: seed, k: wrestler key, f: [match id, "W"|"L"] | null},
           w: "a" | "b" | null (null = winner not recorded), res}

Layout
  Championship: y comes from the draw lines (a first-round pairing on lines 2i-1/2i has y = i-1;
  a round-r match covers 2^(r+1) lines), so byes need no special case. Top/bottom = lower line on top.
  Drawn consolation: SPEC 5.3 -- leaves get rows 0, 2, 4 ... in walk order, a result slot sits
  midway between its feeders; y = row / 2. Place bouts stack after the consolation semifinals.
  Bergman wrestle-backs: one section per ladder (for 2nd, for 3rd), one column per round code.
  2013+: TrackWrestling lists R32 pairings in bracket order; inside a pairing the odd seed is drawn on
  top (checked against the 2014 and 2016 sheets' real lines), later rounds follow their feeders.

Run: .venv/bin/python scripts/brackets/build_ncaa_bracket_archive.py [--year 1979]
"""
import argparse
import json
import math
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HIST_DIR = ROOT / "data" / "ncaa_historical_brackets" / "data"
MODERN_SRC = ROOT / "data" / "ncaa-tourney-parsed" / "all_matches.json"
OUT = ROOT / "frontend" / "wrestledata-ui" / "public" / "lab" / "brackets" / "data"
FIRST_MODERN = 2013

MODEL_LABELS = {
    "bergman": "Single elimination; Bergman wrestle-backs for 2nd and 3rd",
    "bad_points": "Bad-point rounds (no bracket)",
    "summary_only": "Placewinners only (no bouts in the source)",
    "wrestleback_finalists": "Consolation bracket for wrestlers who lost to the finalists",
    "wrestleback_semifinalists": "Consolation bracket for wrestlers who lost to the semifinalists",
    "wrestleback_quarterfinalists": "Consolation bracket for wrestlers who lost to the quarterfinalists",
    "wrestleback_all": "Full consolation bracket (every championship loser)",
}
CHAMP_LABEL = {"PIG": "Pigtail", "R32": "Round of 32", "R16": "Round of 16", "QF": "Quarterfinal",
               "SF": "Semifinal", "Final": "Final"}
CONS_LABEL = {"C_PIG": "Cons. pigtail", "C_QF": "Cons. QF", "C_SF": "Cons. SF"}
PLACE_LABEL = {"Final": "1st place", "3rd": "3rd place", "5th": "5th place", "7th": "7th place",
               "2nd": "2nd place"}
WB_SECTIONS = {"WB2": "Wrestle-backs for 2nd", "WB3": "Wrestle-backs for 3rd"}


# Team names are shown as printed at the time; this only fixes spelling. Historical sheets have a few names
# cut off by the PDF columns or with a seed leaking in ("Tennessee-Chattanooga [11"); TrackWrestling spells one
# school several ways, even within a year ("Penn St." / "Penn State", "UNI" / "Northern Iowa"), which would split
# a team's points. Renames (Army -> Army West Point) are kept as they were; linking old names to today's
# programs for team history is a separate map.
TEAM_FIXES = {
    "Cal State-Fullerto": "Cal State-Fullerton", "California-Santa Barbar": "California-Santa Barbara",
    "Minnesota State-Manka": "Minnesota State-Mankato", "Minnesota State-Moor": "Minnesota State-Moorhead",
    "North Carolina-Gre": "North Carolina-Greensboro", "North Carolina-Greensbor": "North Carolina-Greensboro",
    "Southwestern Oklaho": "Southwestern Oklahoma", "Tennessee-Chattanoog": "Tennessee-Chattanooga",
    # TrackWrestling (2013+)
    "Appalachian S.": "Appalachian State", "Boston U.": "Boston University", "Central Mich.": "Central Michigan",
    "Eastern Mich.": "Eastern Michigan", "Frank. & Marsh.": "Franklin & Marshall",
    "Franklin and Marshall": "Franklin & Marshall", "North Carolina St.": "NC State", "Northern Colo.": "Northern Colorado",
    "Northern Ill.": "Northern Illinois", "UNI": "Northern Iowa", "Penn": "Pennsylvania", "Citadel": "The Citadel",
    "Bakersfield": "CSU Bakersfield", "Csu Bakersfield": "CSU Bakersfield", "Binghamton University": "Binghamton",
    "North Dakota State University": "North Dakota State", "Utah Valley University": "Utah Valley",
    "SIUE": "SIU Edwardsville", "Southern Illinois Edwardsville": "SIU Edwardsville",
}


def team_name(t):
    if not t:
        return t
    t = re.sub(r"\s*\[\d*$", "", t.strip())
    t = TEAM_FIXES.get(t, t)
    return re.sub(r" St\.$", " State", t)


def cons_label(code):
    if code in CONS_LABEL:
        return CONS_LABEL[code]
    m = re.match(r"C_R(\d+)$", code)
    return f"Cons. R{m.group(1)}" if m else code


def result_text(m):
    rt = m.get("result_type") or ""
    sc = m.get("score")
    if rt == "Unknown" and not sc:
        return m.get("result_raw") or ""
    return f"{rt} {sc}".strip() if sc else rt


def side(name, team, seed, key, feeder=None):
    return {"n": name, "t": team_name(team), "s": seed, "k": key, "f": feeder}


def feeder_of(frm, ids):
    """'W:<mid>' / 'L:<mid>' -> [mid, 'W'|'L'] when that match is in this weight's output."""
    if not frm or frm[:2] not in ("W:", "L:"):
        return None
    mid = frm[2:]
    return [mid, frm[0]] if mid in ids else None


# ---------------------------------------------------------------------------
# Historical (schema 2.0) -> viewer
# ---------------------------------------------------------------------------

def hist_weight(d, w, rows, warnings):
    model = d["model"]["bracket_model"]
    wid = str(w["weight"])
    tag = f"{d['tournament']['year']} {wid}"
    ents = {e["id"]: e for e in w["entrants"]}
    out = {"id": wid, "label": wid, "notes": list(w.get("notes") or []),
           "discrepancies": list(w.get("source_discrepancies") or []),
           "placements": [{"place": p["place"], "n": p.get("name"), "t": team_name(p.get("team")),
                           "s": (ents.get(p.get("wrestler_id")) or {}).get("seed"),
                           "k": p.get("wrestler_id"), "method": p.get("method")}
                          for p in w.get("placements") or []]}
    if model == "summary_only" or not rows:
        out["kind"] = "summary"
        return out
    if model == "bad_points":
        out["kind"] = "badpoints"
        rounds = defaultdict(list)
        for r in sorted(rows, key=lambda r: r.get("seq") or 0):
            rounds[r["round"]].append({
                "w": {"n": r["winner_name"], "t": team_name(r["winner_team"])},
                "l": {"n": r["loser_name"], "t": team_name(r["loser_team"])},
                "res": result_text(r),
                "wbp": r.get("winner_bad_points"), "lbp": r.get("loser_bad_points"),
                "wbt": r.get("winner_bad_points_total"), "lbt": r.get("loser_bad_points_total")})
        def rkey(lbl):
            m = re.match(r"R(\d+)", lbl)
            return (int(m.group(1)) if m else 99, len(lbl))
        out["rounds"] = [{"label": lbl.replace("R", "Round ", 1), "bouts": rounds[lbl]}
                         for lbl in sorted(rounds, key=rkey)]
        bpf = w.get("bad_points_final") or {}
        out["bad_points_final"] = [{"n": ents[k]["name"], "t": team_name(ents[k]["team"]), "bp": v}
                                   for k, v in sorted(bpf.items(), key=lambda kv: kv[1]) if k in ents]
        return out

    out["kind"] = "bracket"
    ids = {r["match_id"] for r in rows}
    lines = w.get("draw_lines") or 0
    champ_rows = [r for r in rows if r["bracket"] == "champ"]
    cons_rows = [r for r in rows if r["bracket"] == "consol"]
    has_pig = any(r["round"] == "PIG" for r in champ_rows)
    n_rounds = int(round(math.log2(lines))) if lines else 0
    champ_codes = (["R32", "R16", "QF", "SF", "Final"] if lines == 32 else
                   ["R16", "QF", "SF", "Final"] if lines == 16 else
                   ["QF", "SF", "Final"] if lines == 8 else [])
    off = 1 if has_pig else 0
    col_of_champ = {code: off + i for i, code in enumerate(champ_codes)}
    if has_pig:
        col_of_champ["PIG"] = 0
    line_of = {e["id"]: e.get("line") for e in w["entrants"]}

    sections = [{"id": "champ", "label": "Championship"}]
    columns = defaultdict(dict)
    for code, c in col_of_champ.items():
        columns[c]["champ"] = CHAMP_LABEL.get(code, code)
    matches = []

    def mk(r, sec, c, y, top_first=None):
        a = side(r["winner_name"], r["winner_team"], r.get("winner_seed"), r.get("winner_id"),
                 feeder_of(r.get("winner_from"), ids))
        b = side(r["loser_name"], r["loser_team"], r.get("loser_seed"), r.get("loser_id"),
                 feeder_of(r.get("loser_from"), ids))
        wside = "a"
        if r.get("winner_id") is None and r.get("participants"):
            ps = r["participants"]
            a = side(ps[0]["name"], ps[0]["team"], None, ps[0]["id"], feeder_of(ps[0].get("from"), ids))
            b = side(ps[1]["name"], ps[1]["team"], None, ps[1]["id"], feeder_of(ps[1].get("from"), ids)) \
                if len(ps) > 1 else side("?", "", None, None)
            wside = None
        if top_first is not None and top_first == b["k"] and top_first is not None:
            a, b = b, a
            wside = "b" if wside == "a" else wside
        m = {"id": r["match_id"], "s": sec, "c": c, "r": r["round"], "y": round(float(y), 3),
             "a": a, "b": b, "w": wside, "res": result_text(r)}
        if r["round"] in PLACE_LABEL and sec != "champ" or r["round"] == "Final":
            m["lbl"] = PLACE_LABEL.get(r["round"])
        return m

    # championship
    for r in champ_rows:
        code = r["round"]
        if code == "PIG":
            ln = line_of.get(r.get("winner_id"))
            if not ln:
                warnings.append(f"{tag}: pigtail {r['match_id']} winner has no line")
                ln = 1
            matches.append(mk(r, "champ", 0, (ln - 1) / 2))
            continue
        if code not in champ_codes:
            warnings.append(f"{tag}: champ round {code} not in a {lines}-line draw")
            continue
        ri = champ_codes.index(code)
        la, lb = line_of.get(r.get("winner_id")), line_of.get(r.get("loser_id"))
        ln = la or lb
        if not ln:
            warnings.append(f"{tag}: {r['match_id']} has no line for either wrestler")
            continue
        block = (ln - 1) // (2 ** (ri + 1))
        y = block * 2 ** ri + (2 ** ri - 1) / 2
        top = r.get("winner_id") if (la or 99) <= (lb or 99) else r.get("loser_id")
        matches.append(mk(r, "champ", col_of_champ[code], y, top))

    sheet = w.get("consolation_sheet")
    if model == "bergman":
        by_sec = defaultdict(list)
        for r in sorted(cons_rows, key=lambda r: r.get("seq") or 0):
            sec = "WB3" if r["round"].startswith("WB3") or r["round"] == "3rd" else "WB2"
            by_sec[sec].append(r)
        base = (max(col_of_champ.values()) if col_of_champ else 0) - 1
        for sec in ("WB2", "WB3"):
            rs = by_sec.get(sec)
            if not rs:
                continue
            sections.append({"id": sec, "label": WB_SECTIONS[sec]})
            order = []
            for r in rs:
                if r["round"] not in order:
                    order.append(r["round"])
            order.sort(key=lambda c: (c in ("2nd", "3rd"), ["R16", "QF", "SF"].index(c.split("_")[1])
                                      if "_" in c and c.split("_")[1] in ("R16", "QF", "SF") else 9))
            col = {code: max(0, base - len(order) + 1) + i + 1 for i, code in enumerate(order)}
            ys = {}
            nxt = 0
            for r in rs:
                fs = [feeder_of(r.get(k), ids) for k in ("winner_from", "loser_from")]
                same = [ys[f[0]] for f in fs if f and f[0] in ys]
                y = same[0] if same else nxt
                nxt = max(nxt, y + 1)
                ys[r["match_id"]] = y
                c = col[r["round"]]
                columns[c][sec] = PLACE_LABEL.get(r["round"]) or \
                    {"R16": "Round 1", "QF": "Quarterfinal", "SF": "Semifinal"}.get(r["round"].split("_")[-1], r["round"])
                m = mk(r, sec, c, y)
                if r["round"] in ("2nd", "3rd"):
                    m["lbl"] = PLACE_LABEL[r["round"]]
                matches.append(m)
    elif sheet:
        sections.append({"id": "consol", "label": "Consolation"})
        slots = {s["slot"]: s for s in sheet["slots"]}

        def skey(sid):
            c, rr = sid[1:].split(".")
            return (int(c), int(rr))
        # SPEC 5.3 gives every entry slot a row, but entries aren't drawn as boxes here, so that leaves
        # big gaps. Compact version: only bout slots get rows; a bout whose feeders are all entries is a leaf
        # (next free row), one with a single bout feeder sits one row below it (the drop-in joins there),
        # two bout feeders -> midway. Rows are 2 apart for leaves, so y = row / 2 keeps the engine's units.
        rows_y = {}
        nxt = [0]

        def walk(sid):
            s = slots[sid]
            if s["kind"] == "entry" or (not s.get("top") and not s.get("bottom")):
                return
            for k in ("top", "bottom"):
                if s.get(k):
                    walk(s[k])
            fy = [rows_y[s[k]] for k in ("top", "bottom") if s.get(k) in rows_y]
            if not fy:
                row = nxt[0]
            elif len(fy) == 1:
                row = fy[0] + 1
            else:
                row = sum(fy) / 2
            rows_y[sid] = row
            if not fy:
                nxt[0] = row + 2
        for sid in sorted((s for s in slots if not slots[s].get("feeds")), key=skey):
            walk(sid)
        # consolation pigtails can chain (2007 174: the winner of one meets another pigtail winner), so
        # each gets a column by how many pigtails still lie ahead of its winner
        pig_rows = {r["match_id"]: r for r in cons_rows if r["round"] == "C_PIG"}
        pig_next = {}
        for r in pig_rows.values():
            for k in ("winner_from", "loser_from"):
                f = r.get(k) or ""
                if f.startswith("W:") and f[2:] in pig_rows:
                    pig_next[f[2:]] = r["match_id"]

        def pig_depth(mid):
            return 0 if mid not in pig_next else 1 + pig_depth(pig_next[mid])
        n_pig = 1 + max((pig_depth(m) for m in pig_rows), default=-1)
        first_c = (col_of_champ.get("R16", off) if lines == 32 else off) + n_pig
        for i in range(n_pig):
            columns[first_c - 1 - i]["consol"] = cons_label("C_PIG")
        by_mid = {r["match_id"]: r for r in cons_rows}
        placed = set()
        slot_wr = {sid: s.get("wrestler_id") for sid, s in slots.items()}
        for sid, s in slots.items():
            if s["kind"] not in ("bout", "unrecorded") or not s.get("match_id"):
                continue
            r = by_mid.get(s["match_id"])
            if not r:
                warnings.append(f"{tag}: sheet slot {sid} names unknown match {s['match_id']}")
                continue
            c = first_c + int(s["column"]) - 2
            columns[c]["consol"] = cons_label(r["round"])
            top = slot_wr.get(s.get("top"))
            matches.append(mk(r, "consol", c, rows_y[sid] / 2, top))
            placed.add(r["match_id"])
        last_c = max([m["c"] for m in matches if m["s"] == "consol"], default=first_c)
        entry_y = {}   # consolation pigtail: sits beside the bout its winner went on to
        for sid, s in slots.items():
            if s["kind"] == "entry" and s.get("feeds") in rows_y:
                entry_y[s.get("wrestler_id")] = rows_y[s["feeds"]] / 2
        csf = [m["y"] for m in matches if m["r"] == "C_SF"]
        base_y = sum(csf) / len(csf) if csf else 0.0
        place_c = last_c + 1
        pig_y = {}
        for mid in sorted(pig_rows, key=pig_depth):
            r = pig_rows[mid]
            y = pig_y.get(pig_next.get(mid)) if mid in pig_next else entry_y.get(r.get("winner_id"))
            pig_y[mid] = y if y is not None else 0.0
        for r in cons_rows:
            if r["match_id"] in placed:
                continue
            if r["round"] == "C_PIG":
                matches.append(mk(r, "consol", first_c - 1 - pig_depth(r["match_id"]), pig_y[r["match_id"]]))
            elif r["round"] in ("3rd", "5th", "7th"):
                columns[place_c]["consol"] = "Placement"
                dy = {"3rd": -1.5, "5th": 0.0, "7th": 1.5}[r["round"]]
                matches.append(mk(r, "consol", place_c, base_y + dy))
            else:
                warnings.append(f"{tag}: consolation row {r['match_id']} ({r['round']}) not on the sheet -> parked")
                col = [m["y"] for m in matches if m["s"] == "consol"]
                matches.append(mk(r, "consol", place_c, (max(col) + 2) if col else 0.0))
    elif cons_rows:
        warnings.append(f"{tag}: {len(cons_rows)} consolation rows but no sheet")

    n_cols = (max(columns) + 1) if columns else 0
    out["sections"] = [s for s in sections if any(m["s"] == s["id"] for m in matches)]
    out["columns"] = [{sec["id"]: columns[i].get(sec["id"]) for sec in sections} for i in range(n_cols)]
    out["matches"] = matches
    return out


def build_hist_year(path, warnings):
    d = json.loads(path.read_text())
    t = d["tournament"]
    y = t["year"]
    rows_by_w = defaultdict(list)
    for r in d["matches"]:
        rows_by_w[str(r["weight"])].append(r)
    weights = [hist_weight(d, w, rows_by_w.get(str(w["weight"]), []), warnings) for w in d["weights"]]
    ts = d.get("team_scores") or {}
    team_scores = {"kind": "printed" if ts.get("scores") else "none", "official": ts.get("official"),
                   "rows": [dict(r, team=team_name(r["team"])) for r in ts.get("scores") or []], "note": "; ".join(ts.get("notes") or []) or None}
    if y == 1928:
        team_scores["note"] = "No team scoring in 1928."
    model = d["model"]["bracket_model"]
    notes = []
    if (t.get("source") or {}).get("incomplete_consolations"):
        notes.append("The source marks this year's consolation results as incomplete.")
    if model == "summary_only":
        notes.append("Only the placewinners survive in the source; no bracket is available.")
    return {
        "event": {"year": y, "name": f"{y} NCAA Wrestling Championships", "host": t.get("host"),
                  "dates": t.get("dates"), "team_champion": t.get("team_champion"),
                  "team_champion_label": t.get("team_champion_label"),
                  "outstanding_wrestler": t.get("outstanding_wrestler"),
                  "gorriaran_award": t.get("gorriaran_award"), "model": model,
                  "model_label": MODEL_LABELS.get(model, model),
                  "places": d["model"].get("placements_awarded"),
                  "source": "wrestlingstats.com bracket sheets"},
        "notes": notes, "team_scores": team_scores, "weights": weights,
    }


# ---------------------------------------------------------------------------
# 2013+ (TrackWrestling all_matches.json) -> viewer
# ---------------------------------------------------------------------------

ROUNDS = {
    "PIG": ("champ", 0, 0), "R32": ("champ", 1, 1), "R16": ("champ", 2, 2),
    "QF": ("champ", 3, 3), "SF": ("champ", 4, 4), "Final": ("champ", 5, 5),
    "C_PIG": ("consol", 1, 2), "C_R1": ("consol", 2, 3), "C_R2": ("consol", 3, 4),
    "C_R3": ("consol", 4, 5), "C_R4": ("consol", 5, 6), "C_QF": ("consol", 6, 7),
    "C_SF": ("consol", 7, 8), "3rd": ("consol", 8, 9), "5th": ("consol", 8, 9), "7th": ("consol", 8, 9),
}
MODERN_COLUMNS = [
    {"champ": "Pigtail", "consol": None}, {"champ": "Round of 32", "consol": "Cons. pigtail"},
    {"champ": "Round of 16", "consol": "Cons. R1"}, {"champ": "Quarterfinal", "consol": "Cons. R2"},
    {"champ": "Semifinal", "consol": "Cons. R3"}, {"champ": "Final", "consol": "Cons. R4"},
    {"champ": None, "consol": "Cons. QF"}, {"champ": None, "consol": "Cons. SF"},
    {"champ": None, "consol": "Placement"},
]
MODERN_SECTIONS = [{"id": "champ", "label": "Championship"}, {"id": "consol", "label": "Consolation"}]


def modern_weight(rows, warnings, tag):
    wkey = lambda n, t: f"{n}|{t}"
    matches = []
    r32_i = 0
    for m in rows:
        code = m["round"]
        if code not in ROUNDS:
            warnings.append(f"{tag}: unknown round {code!r} skipped")
            continue
        sec, col, tier = ROUNDS[code]
        o = {"id": "", "s": sec, "c": col, "r": code, "_tier": tier,
             "a": side(m["winner_name"], m["winner_team"], m["winner_seed"], wkey(m["winner_name"], m["winner_team"])),
             "b": side(m["loser_name"], m["loser_team"], m["loser_seed"], wkey(m["loser_name"], m["loser_team"])),
             "w": "a", "res": result_text(m), "_src": m}
        if code in PLACE_LABEL:
            o["lbl"] = PLACE_LABEL[code]
        if code == "R32":
            o["_leaf"] = r32_i
            r32_i += 1
        matches.append(o)
    cnt = defaultdict(int)
    for o in matches:
        o["id"] = f"{o['r']}-{cnt[o['r']]}"
        cnt[o["r"]] += 1
    by_id = {o["id"]: o for o in matches}
    appear = defaultdict(list)
    for o in matches:
        for sd in ("a", "b"):
            appear[o[sd]["k"]].append(o)
    for k, lst in appear.items():
        lst.sort(key=lambda o: o["_tier"])
        for i, o in enumerate(lst):
            sd = "a" if o["a"]["k"] == k else "b"
            prev = None
            for p in lst[:i]:
                if p["_tier"] < o["_tier"]:
                    prev = p
            if prev is not None:
                o[sd]["f"] = [prev["id"], "W" if prev["a"]["k"] == k else "L"]
    for o in matches:
        if o["r"] == "R32":
            o["y"] = float(o["_leaf"])
    for o in sorted(matches, key=lambda o: (o["_tier"], o["c"])):
        if "y" in o:
            continue
        fs = [by_id[o[sd]["f"][0]] for sd in ("a", "b") if o[sd]["f"]]
        same = [f for f in fs if f["s"] == o["s"] and "y" in f]
        if o["r"] == "C_PIG":
            same = [f for f in fs if f["r"] == "R32" and "y" in f]
        pool = same or [f for f in fs if "y" in f]
        if o["r"] == "C_R1":
            pool = [f for f in fs if "y" in f]
        o["y"] = sum(f["y"] for f in pool) / len(pool) if pool else None
    for o in matches:
        if o["r"] == "PIG":
            nxt = [p for p in matches if p["r"] == "R32" and any(
                p[sd]["f"] and p[sd]["f"][0] == o["id"] for sd in ("a", "b"))]
            o["y"] = nxt[0]["y"] if nxt else 0.0
    plc = {o["r"]: o for o in matches if o["r"] in ("3rd", "5th", "7th")}
    csf = [o["y"] for o in matches if o["r"] == "C_SF" and o["y"] is not None]
    base = sum(csf) / len(csf) if csf else 0.0
    for r, dy in (("3rd", -2.0), ("5th", 0.0), ("7th", 2.0)):
        if r in plc:
            plc[r]["y"] = base + dy
    for o in matches:
        if o.get("y") is None:
            warnings.append(f"{tag}: could not place {o['id']} (missing feeder) -> parked")
            col = [p["y"] for p in matches if p["c"] == o["c"] and p["s"] == o["s"] and p.get("y") is not None]
            o["y"] = (max(col) + 1.0) if col else 0.0
    for o in matches:
        a, b = o["a"], o["b"]
        if o["r"] == "R32":
            odd = lambda x: x["s"] is not None and x["s"] % 2 == 1
            top = a if odd(a) or not odd(b) else b
        else:
            def sy(x):
                if not x["f"]:
                    return 1e9
                f = by_id[x["f"][0]]
                return f["y"] + (0 if f["s"] == o["s"] else 1e6)
            top = a if sy(a) <= sy(b) else b
        if top is b:
            o["a"], o["b"], o["w"] = b, a, "b"
    # placements from the place bouts
    places = []
    for code, (wp, lp) in {"Final": (1, 2), "3rd": (3, 4), "5th": (5, 6), "7th": (7, 8)}.items():
        src = next((o["_src"] for o in matches if o["r"] == code), None)
        if src:
            places.append({"place": wp, "n": src["winner_name"], "t": src["winner_team"], "s": src["winner_seed"],
                           "k": wkey(src["winner_name"], src["winner_team"]), "method": "bout"})
            places.append({"place": lp, "n": src["loser_name"], "t": src["loser_team"], "s": src["loser_seed"],
                           "k": wkey(src["loser_name"], src["loser_team"]), "method": "bout"})
    for o in matches:
        for k in [k for k in o if k.startswith("_")]:
            del o[k]
        o["y"] = round(o["y"], 3)
    return matches, sorted(places, key=lambda p: p["place"])


# NCAA Division I team scoring (2013+): advancement 1 per championship win (pigtail-SF),
# 0.5 per consolation win before the place bouts (incl. consolation pigtail); placement
# 16-12-10-9-7-6-4-3; bonus 2 fall / forfeit / default / DQ, 1.5 tech fall, 1 major decision.
# Team deductions (unsportsmanlike etc.) come from data/{year}/ncaa-tourney/team_penalties.json.
# Printed-summary mistakes that the bouts settle beyond doubt (shown with a flag on the page).
PRINTED_TEAM_CORRECTIONS = {
    (2014, "Northern Iowa"): ("Northwestern", "The summary prints Northern Iowa here. The bouts give Northwestern "
                              "exactly 46 points and Northern Iowa 40, so this row is Northwestern."),
}
MODERN_PLACE_PTS = {1: 16, 2: 12, 3: 10, 4: 9, 5: 7, 6: 6, 7: 4, 8: 3}


def modern_bonus(rt):
    rt = (rt or "").upper()
    if rt.startswith(("FALL", "FF", "MFF", "FOR", "DEF", "INJ", "DQ")):
        return 2.0
    if rt.startswith("TF"):
        return 1.5
    if rt.startswith("MD"):
        return 1.0
    return 0.0


def modern_team_scores(year, rows, place_lists):
    pts = defaultdict(float)
    champs = defaultdict(int)
    for m in rows:
        t, code = m["winner_team"], m["round"]
        if code in ("PIG", "R32", "R16", "QF", "SF"):
            pts[t] += 1.0
        elif code in ("C_PIG", "C_R1", "C_R2", "C_R3", "C_R4", "C_QF", "C_SF"):
            pts[t] += 0.5
        pts[t] += modern_bonus(m["result_type"])
    for places in place_lists:
        for p in places:
            pts[p["t"]] += MODERN_PLACE_PTS.get(p["place"], 0)
            if p["place"] == 1:
                champs[p["t"]] += 1
    pen_path = ROOT / "data" / str(year) / "ncaa-tourney" / "team_penalties.json"
    note = "Calculated from the bouts with NCAA Division I team scoring."
    if pen_path.exists():
        pens = json.loads(pen_path.read_text())
        items = pens.items() if isinstance(pens, dict) else [(p.get("team"), p.get("points")) for p in pens]
        for team, p in items:
            if isinstance(p, dict):
                p = p.get("points") or p.get("deduction")
            if team and isinstance(p, (int, float)):
                pts[team_name(team)] -= abs(p)
        note += " Includes team point deductions."
    ranked = sorted(pts.items(), key=lambda kv: -kv[1])
    rows_out, prev, rank = [], None, 0
    for i, (team, p) in enumerate(ranked):
        if p != prev:
            rank = i + 1
        rows_out.append({"rank": rank, "tied": False, "team": team, "points": round(p, 1),
                         "champions": champs.get(team, 0)})
        prev = p
    for i, r in enumerate(rows_out):
        r["tied"] = any(o is not r and o["rank"] == r["rank"] for o in rows_out[max(0, i - 1):i + 2])
    return {"kind": "calculated", "official": None, "rows": rows_out, "note": note}


# Host cities for years the sheet files don't cover (2013-2016 hosts/dates/awards come from the sheet files).
MODERN_HOSTS = {2017: "St. Louis, MO", 2018: "Cleveland, OH", 2019: "Pittsburgh, PA", 2021: "St. Louis, MO",
                2022: "Detroit, MI", 2023: "Tulsa, OK", 2024: "Kansas City, MO", 2025: "Philadelphia, PA",
                2026: "Cleveland, OH"}


def build_modern_year(year, rows, warnings, printed=None, sheet_meta=None):
    rows = [dict(m, winner_team=team_name(m["winner_team"]), loser_team=team_name(m["loser_team"])) for m in rows]
    weights = []
    place_lists = []
    for wt in sorted({m["weight"] for m in rows}):
        wr = [m for m in rows if m["weight"] == wt]
        ms, places = modern_weight(wr, warnings, f"{year} {wt}")
        place_lists.append(places)
        weights.append({"id": str(wt), "label": str(wt), "kind": "bracket", "sections": MODERN_SECTIONS,
                        "columns": MODERN_COLUMNS, "matches": ms, "placements": places, "notes": [],
                        "discrepancies": []})
    champ = None
    ts = modern_team_scores(year, rows, place_lists)
    if printed:
        # TJ: where the printed top ten exists, it wins. The rest of the field stays calculated.
        top = [dict(r, team=team_name(r["team"])) for r in printed["scores"]]
        for r in top:
            fix = PRINTED_TEAM_CORRECTIONS.get((year, r["team"]))
            if fix:
                r["printed_team"], r["team"], r["flag"] = r["team"], fix[0], fix[1]
        names = {r["team"] for r in top}
        rest = [dict(r, calc=True) for r in ts["rows"] if r["team"] not in names]
        calc_top = {r["team"]: r["points"] for r in ts["rows"]}
        for r in top:
            if calc_top.get(r["team"]) is not None and calc_top[r["team"]] != r["points"]:
                r["calc_points"] = calc_top[r["team"]]
        for i, r in enumerate(rest):
            r["rank"] = len(top) + 1 + sum(1 for o in rest[:i] if o["points"] > r["points"])
        ts = {"kind": "printed", "official": printed.get("official"), "rows": top + rest,
              "note": "Top ten as printed on the official summary; the rest of the field is calculated from the bouts."}
    if ts["rows"]:
        champ = ts["rows"][0]["team"]
    return {
        "event": {"year": year, "name": f"{year} NCAA Division I Wrestling Championships",
                  "host": (sheet_meta or {}).get("host") or MODERN_HOSTS.get(year),
                  "dates": (sheet_meta or {}).get("dates"), "team_champion": champ, "team_champion_label": "Team Champion",
                  "outstanding_wrestler": (sheet_meta or {}).get("outstanding_wrestler"),
                  "gorriaran_award": (sheet_meta or {}).get("gorriaran_award"),
                  "model": "wrestleback_all", "model_label": MODEL_LABELS["wrestleback_all"], "places": 8,
                  "source": "TrackWrestling"},
        "notes": [], "team_scores": ts, "weights": weights,
    }


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    warnings, index = [], []
    modern = json.loads(MODERN_SRC.read_text())
    modern_years = sorted({m["year"] for m in modern if m["year"] >= FIRST_MODERN})
    hist_paths = {int(p.stem[4:]): p for p in HIST_DIR.glob("NCAA*.json")}
    years = sorted({y for y in hist_paths if y < FIRST_MODERN} | set(modern_years))
    for y in years:
        if args.year and y != args.year:
            continue
        if y >= FIRST_MODERN:
            printed = meta = None
            if y in hist_paths:
                sheet = json.loads(hist_paths[y].read_text())
                printed = sheet.get("team_scores")
                printed = printed if printed and printed.get("scores") else None
                meta = sheet.get("tournament")
            doc = build_modern_year(y, [m for m in modern if m["year"] == y], warnings, printed, meta)
        else:
            doc = build_hist_year(hist_paths[y], warnings)
        doc["schema"] = "ncaa-bracket-archive/1"
        (OUT / f"{y}.json").write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False))
        ev = doc["event"]
        index.append({"year": y, "host": ev.get("host"), "team_champion": ev.get("team_champion"),
                      "model": ev["model"], "weights": len(doc["weights"]),
                      "bouts": sum(len(w.get("matches") or []) + sum(len(r["bouts"]) for r in w.get("rounds") or [])
                                   for w in doc["weights"]),
                      "source": ev["source"]})
        print(f"{y}: {len(doc['weights'])} weights, {index[-1]['bouts']} bouts, team scores {doc['team_scores']['kind']}")
    if not args.year:
        (OUT / "index.json").write_text(json.dumps({"years": index}, indent=1, ensure_ascii=False))
    print(f"\n{len(warnings)} warnings")
    for w in warnings[:80]:
        print("  ", w)


if __name__ == "__main__":
    main()
