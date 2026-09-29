#!/usr/bin/env python3
"""Data for the MatSavant page "NCAA Championships -> Takedowns & Team Points"
(frontend/wrestledata-ui/public/ncaa_takedowns.html). Writes ONE file the page fetches:
    frontend/wrestledata-ui/public/data/reports/ncaa_td_share_team_points.json
Rebuild after each NCAA tournament (full how-to: docs/matsavant.md, "NCAA Takedowns & Team Points page"):
    .venv/bin/python scripts/analysis/td_share_team_points/build_data.py
Years are detected automatically: every year >= 2015 that has BOTH data/{year}/ncaa-tourney/parsed/matches.json
and data/{year}/ncaa-tourney/bout_detail/ (so a new season appears once those two exist).

One point per NCAA tournament entrant per year.
  x = takedown share = takedowns scored / (scored + allowed), over that wrestler's NCAA bouts with
      play-by-play (bout_detail), unwrestled forfeits/defaults dropped (same rules as the takedown report)
  y = NCAA team points scored = advancement + bonus + placement, using the point tables in
      scripts/ncaa/parse_ncaa_results.py (ADVANCEMENT_PTS, BONUS_PTS, PLACEMENT_PTS)
Team points are recomputed here from data/{year}/ncaa-tourney/parsed/matches.json, keyed by
(year, weight, surname + first initial), because parsed/wrestlers.json is keyed by seed and silently drops
entrants whose name doesn't match the seeds file (e.g. 2018 197 Kyle Conel, 3rd place).
Not modelled: bye points (advancement for a bye followed by a win), so a few totals can be 0.5-1 low.
Wrestlers with no takedowns either way in their bouts have no takedown share and are left off the chart.
"""
import json, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE.parent / "td_custom_report"))
sys.path.insert(0, str(ROOT / "scripts/ncaa"))
import td_differential_report as R
import build_data as B
from parse_ncaa_results import ADVANCEMENT_PTS, BONUS_PTS, PLACEMENT_PTS

FIRST_YEAR = 2015  # no NCAA play-by-play before 2015
YEARS = sorted(int(d.name) for d in (ROOT / "data").iterdir()
               if d.name.isdigit() and int(d.name) >= FIRST_YEAR
               and (d / "ncaa-tourney/parsed/matches.json").exists() and (d / "ncaa-tourney/bout_detail").is_dir())
OUT = ROOT / "frontend/wrestledata-ui/public/data/reports/ncaa_td_share_team_points.json"
AMBIG = set()  # (year, weight, nkey) shared by two different entrants -> key those by full name instead


def key(y, wt, name):
    k = (y, wt, R.nkey(name))
    return (y, wt, " ".join(name.lower().split())) if k in AMBIG else k


def find_ambiguous():
    seen = defaultdict(set)
    for y in YEARS:
        for m in json.load(open(ROOT / f"data/{y}/ncaa-tourney/parsed/matches.json")):
            for side in ("winner", "loser"):
                seen[(y, m["weight"], R.nkey(m[f"{side}_name"]))].add(" ".join(m[f"{side}_name"].lower().split()))
    AMBIG.update(k for k, v in seen.items() if len(v) > 1)
    return {k: v for k, v in seen.items() if len(v) > 1}


PLACE = {"Final": (1, 2), "3rd": (3, 4), "5th": (5, 6), "7th": (7, 8)}


def team_points():
    pts = {}
    for y in YEARS:
        for m in json.load(open(ROOT / f"data/{y}/ncaa-tourney/parsed/matches.json")):
            for side in ("winner", "loser"):
                k = key(y, m["weight"], m[f"{side}_name"])
                p = pts.setdefault(k, {"name": m[f"{side}_name"], "team": m[f"{side}_team"],
                                       "adv": 0.0, "bonus": 0.0, "place": None})
                if side == "winner":
                    p["adv"] += ADVANCEMENT_PTS.get(m["round"], 0.0)
                    p["bonus"] += BONUS_PTS.get(m["result_type"], 0.0)
            if m["round"] in PLACE:
                pts[key(y, m["weight"], m["winner_name"])]["place"] = PLACE[m["round"]][0]
                pts[key(y, m["weight"], m["loser_name"])]["place"] = PLACE[m["round"]][1]
    for p in pts.values():
        p["total"] = p["adv"] + p["bonus"] + PLACEMENT_PTS.get(p["place"], 0.0)
    return pts


def main():
    print("ambiguous surname+initial keys:", find_ambiguous())
    pts = team_points()
    nb, _ = R.load(YEARS)
    td = defaultdict(lambda: [0, 0, 0, 0])  # wins, losses, TDs for, TDs against
    for b in nb:
        if not B.wrestled(b):
            continue
        for s, o in (("winner", "loser"), ("loser", "winner")):
            r = td[key(b["year"], b["weight"], b[s])]
            r[0 if s == "winner" else 1] += 1
            r[2] += b["td"][s]; r[3] += b["td"][o]
    rows, no_td, no_pbp = [], 0, 0
    for k, p in sorted(pts.items(), key=lambda kv: str(kv[0])):
        t = td.get(k)
        if not t:
            no_pbp += 1; continue
        if t[2] + t[3] == 0:
            no_td += 1; continue
        rows.append({"y": k[0], "wt": k[1], "name": p["name"], "team": p["team"], "p": p["place"],
                     "pts": round(p["total"], 1), "adv": p["adv"], "bonus": p["bonus"], "r": t})
    from datetime import date
    meta = {"years": YEARS, "entrants": len(pts), "plotted": len(rows), "no_td": no_td, "no_pbp": no_pbp,
            "built": date.today().isoformat()}
    OUT.write_text(json.dumps({"meta": meta, "rows": rows}, separators=(",", ":")))
    print(f"years {YEARS[0]}-{YEARS[-1]} ({len(YEARS)}): {len(rows)} plotted of {len(pts)} entrants "
          f"(no TDs either way: {no_td}, no play-by-play: {no_pbp}) -> {OUT.relative_to(ROOT)}")

    # cross-check against parsed/wrestlers.json where it has the wrestler
    diffs = []
    for y in YEARS:
        for w in json.load(open(ROOT / f"data/{y}/ncaa-tourney/parsed/wrestlers.json")):
            p = pts.get(key(y, w["weight"], w["name"]))
            if p is None:
                diffs.append((y, w["weight"], w["name"], w["total_points"], None))
            elif abs(p["total"] - w["total_points"]) > 0.01:
                diffs.append((y, w["weight"], w["name"], w["total_points"], p["total"]))
    print(f"differences vs parsed/wrestlers.json: {len(diffs)}")
    for d in diffs[:15]:
        print("  ", d)


if __name__ == "__main__":
    main()
