#!/usr/bin/env python3
"""
Build official-result files for conference championships from the team scrapes
already on disk (mt/processed_data/ncaa_men/{year}/{Team}.json) -- NO new scraping.

Why: conference `bout_detail` (play-by-play) has no result type, round, or placement, and
there is no results file for conference tournaments the way there is for the NCAA
(data/{year}/ncaa-tourney/parsed/matches.json). But every wrestler's team-scrape record
lists each match with its event name, round label, and result string, e.g.
    "2019 Big Ten Wrestling Championships" | "Champ. Round 1 - A (X) over B (Y) (TF 17-0 4:39)"

Output (one file per conference tournament, same folder layout as the NCAA parsed data):
    data/{year}/{conf}-tourney/parsed/matches.json   -- list of official match records

Record fields
    year, conference, weight, round (raw label, None when the source has none, e.g. "Varsity - ..."),
    winner_name, winner_team, loser_name, loser_team,
    result_type  Dec | MD | TF | Fall | SV-1.. | TB-1.. | UTB | Forfeit | Inj. | DQ | Default | Unknown
    result_raw   the source's result string ("Dec 7-3", "TF 17-0 4:39", "Fall 1:06", "M. For.", ...)
    score        "winner-loser" for point results (Dec/MD/TF/SV/TB), else null
    time         match-ending time for Fall/TF/Inj., else null
    date, event

Notes
  * Both wrestlers' team files list the same match (one may lack the round label), so records are
    de-duplicated on (weight, winner, loser, result). A pair that meets twice with the same result in
    one tournament is kept twice (count = the most any single team file lists).
  * BYE and NoResult rows are dropped. Events are recognised by name (conference patterns below),
    excluding duals ("vs. ..."), NCAA, EIWA, and "duals" events.
  * The 6 conferences are the ones with play-by-play (bout_detail). EIWA is not included.
  * Names in these files differ from bout_detail's (Timothy vs Timmy McCall) -- join with a fuzzy
    (last name + first initial + weight) key, as td_differential_report.py does.

Usage:
    .venv/bin/python scripts/analysis/build_conference_results.py            # all years found
    .venv/bin/python scripts/analysis/build_conference_results.py --start 2017 --end 2019
"""

import argparse
import glob
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

PAT = {"big_ten": r"big ten", "big_12": r"big 12|big xii", "acc": r"\bacc\b",
       "mac": r"\bmac\b|mid.?american", "pac_12": r"pac.?12", "socon": r"southern conference|socon"}
LABEL = {"big_ten": "Big Ten", "big_12": "Big 12", "acc": "ACC", "mac": "MAC", "pac_12": "Pac-12",
         "socon": "SoCon"}


def conf_of(event):
    e = (event or "").lower()
    if e.startswith("vs") or "eiwa" in e or "ncaa" in e or "duals" in e:
        return None
    for c, p in PAT.items():
        if re.search(p, e):
            return c
    return None


def normalize_result(raw):
    """-> (result_type, score, time)"""
    r = (raw or "").strip()
    m = re.match(r"^(Dec|MD)\s+(\d+-\d+)$", r)
    if m:
        return m[1], m[2], None
    m = re.match(r"^(?:Min-)?TF\S*\s+(\d+-\d+)(?:\s+(\d+:\d+))?", r)
    if m:
        return "TF", m[1], m[2]
    m = re.match(r"^(SV-\d+)\s+\(Fall\)\s*(\d+:\d+)?", r)  # fall scored in sudden victory
    if m:
        return "Fall", None, m[2]
    m = re.match(r"^(SV-\d+)\s+(\d+-\d+)$", r)
    if m:
        return m[1], m[2], None
    m = re.match(r"^(TB-\d+|UTB)(?:\s+\(RT\))?\s+(\d+-\d+)$", r)
    if m:
        return m[1], m[2], None
    m = re.match(r"^Fall\s+(\d+:\d+)", r)
    if m:
        return "Fall", None, m[1]
    m = re.match(r"^Inj\.?\s*(\d+:\d+)?", r)
    if m:
        return "Inj.", None, m[1]
    if r in ("For.", "M. For.", "MFFL", "FFL"):
        return "Forfeit", None, None
    if r == "DQ":
        return "DQ", None, None
    if r == "Def.":
        return "Default", None, None
    return "Unknown", None, None


def build(years):
    # (year, conf) -> key -> {team_file: [round labels]}, key = (weight, winner, loser, result_raw).
    # Both wrestlers' team files list the same match, and one file may carry the round label while the other
    # has none ("Varsity - ..."), so the round is NOT part of the key.
    seen = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    rec = {}
    for f in sorted(glob.glob(str(ROOT / "mt/processed_data/ncaa_men/*/*.json"))):
        y = int(Path(f).parent.name)
        if years and y not in years:
            continue
        team_file = Path(f).name
        for w in json.load(open(f))["roster"]:
            for m in w.get("matches", []):
                c = conf_of(m.get("event"))
                if not c or not m.get("winner_name") or not m.get("loser_name"):
                    continue
                if m.get("result") in ("BYE", "NoResult", None, ""):
                    continue
                round_label = m["summary"].split(" - ")[0] if " - " in m["summary"] else None
                if round_label and round_label.startswith("Varsity"):
                    round_label = None
                key = (str(m["weight"]), m["winner_name"], m["loser_name"], m["result"])
                seen[(y, c)][key][team_file].append(round_label)
                rtype, score, time = normalize_result(m["result"])
                rec[(y, c, key)] = {
                    "year": y, "conference": LABEL[c],
                    "weight": int(m["weight"]) if str(m["weight"]).isdigit() else m["weight"],
                    "round": None,
                    "winner_name": m["winner_name"], "winner_team": m.get("winner_team"),
                    "loser_name": m["loser_name"], "loser_team": m.get("loser_team"),
                    "result_type": rtype, "result_raw": m["result"], "score": score, "time": time,
                    "date": m.get("date"), "event": m.get("event"),
                }
    out = defaultdict(list)
    for (y, c), keys in seen.items():
        for key, per_team in keys.items():
            # the team file that lists this match the most times (a pair meeting twice = 2), preferring the
            # one with the most round labels, defines the records
            labels = max(per_team.values(), key=lambda ls: (len(ls), sum(1 for x in ls if x)))
            for lab in sorted(labels, key=lambda x: (x is None, x or "")):
                r = dict(rec[(y, c, key)])
                r["round"] = lab
                out[(y, c)].append(r)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", type=int)
    ap.add_argument("--end", type=int)
    a = ap.parse_args()
    years = set(range(a.start, a.end + 1)) if a.start and a.end else None
    out = build(years)
    unknown = Counter()
    for (y, c), recs in sorted(out.items()):
        recs.sort(key=lambda r: (r["weight"] if isinstance(r["weight"], int) else 0, r["round"] or "",
                                 r["winner_name"], r["loser_name"]))
        d = ROOT / f"data/{y}/{c}-tourney/parsed"
        d.mkdir(parents=True, exist_ok=True)
        (d / "matches.json").write_text(json.dumps(recs, indent=1, ensure_ascii=False))
        for r in recs:
            if r["result_type"] == "Unknown":
                unknown[r["result_raw"]] += 1
    n = sum(len(v) for v in out.values())
    print(f"Wrote {len(out)} conference-tournament result files, {n:,} matches "
          f"(years {sorted({y for y, _ in out})[:1]}..{sorted({y for y, _ in out})[-1:]})")
    print("Result types:", dict(Counter(r["result_type"] for v in out.values() for r in v).most_common()))
    if unknown:
        print("UNRECOGNISED result strings:", dict(unknown.most_common(10)))


if __name__ == "__main__":
    main()
