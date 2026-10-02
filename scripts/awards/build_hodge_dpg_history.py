#!/usr/bin/env python3
"""
Builds the data for the Lab page "DPG and the Hodge Trophy" (/lab/hodge/): the five best DPG seasons each year
with the Hodge winner and the vote runner-up marked.

RUN ONCE A YEAR, after the season is over and the Hodge Trophy has been announced:
  1. add the new season to data/awards/hodge_trophy_history.json (winner(s), runner-up, first-place votes)
  2. make sure that season's DPG is final (mat_value_{year}.json rebuilt after the NCAAs)
  3. .venv/bin/python scripts/awards/build_hodge_dpg_history.py
  4. check /lab/hodge/ locally, then commit + push with the usual smoke test

Inputs
  data/awards/hodge_trophy_history.json                                  winners, runner-up, votes (source of truth)
  frontend/wrestledata-ui/public/data/mat_value/{year}/mat_value_{year}.json   season DPG (mv_avg), full season incl.
                                                                         the NCAAs, since the vote comes after them
Output
  frontend/wrestledata-ui/public/lab/hodge/hodge_dpg.json  (read by lab/hodge/index.html)

Rules: only wrestlers with MIN_MATCHES+ matches count (drops one-match flukes). Names match on letters only, with
ALIASES for spellings our data has differently (Ed Ruth = "Edward Ruth"). The script stops if a winner or runner-up
can't be found in that season's DPG file, so a typo in the history file doesn't silently drop a highlight.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HISTORY = ROOT / "data" / "awards" / "hodge_trophy_history.json"
MV_DIR = ROOT / "frontend" / "wrestledata-ui" / "public" / "data" / "mat_value"
OUT = ROOT / "frontend" / "wrestledata-ui" / "public" / "lab" / "hodge" / "hodge_dpg.json"
MIN_MATCHES = 10
ALIASES = {"edruth": "edwardruth"}


def key(name):
    k = re.sub(r"[^a-z]", "", (name or "").lower())
    return ALIASES.get(k, k)


def main():
    hist = json.loads(HISTORY.read_text())["seasons"]
    seasons, problems = [], []
    for y_str in sorted(hist, key=int):
        y = int(y_str)
        h = hist[y_str]
        path = MV_DIR / str(y) / f"mat_value_{y}.json"
        if not path.exists():
            problems.append(f"{y}: no DPG file {path.relative_to(ROOT)}")
            continue
        rows = json.loads(path.read_text())
        q = sorted((w for w in rows if w["matches"] >= MIN_MATCHES), key=lambda w: -w["mv_avg"])
        tag = {key(n): "win" for n in h["winners"]}
        if h.get("runner_up"):
            tag[key(h["runner_up"])] = "ru"
        votes = {key(n): v for n, v in (h.get("votes") or {}).items()}
        found = {key(w["name"]) for w in q}
        for n in tag:
            if n not in found:
                problems.append(f"{y}: '{n}' not in that season's DPG list ({MIN_MATCHES}+ matches) -- check the name")

        def entry(rank, w):
            k = key(w["name"])
            return {"rank": rank, "id": w["wrestler_id"], "n": w["name"].replace("`", "'"), "t": w["team"],
                    "w": w["weight"], "d": round(w["mv_avg"], 2), "m": w["matches"],
                    "tag": tag.get(k), "votes": votes.get(k)}
        seasons.append({
            "y": y,
            "top": [entry(i + 1, w) for i, w in enumerate(q[:5])],
            "extra": [entry(i + 1, w) for i, w in enumerate(q) if i >= 5 and key(w["name"]) in tag],
            "shared": len(h["winners"]) > 1,
            "no_votes": not h.get("votes") and len(h["winners"]) == 1,
        })
    if problems:
        print("Stopped, fix these first:\n  " + "\n  ".join(problems))
        sys.exit(1)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"min_matches": MIN_MATCHES, "seasons": seasons}, separators=(",", ":")))
    lead = sum(1 for s in seasons if s["top"][0]["tag"] == "win")
    print(f"{len(seasons)} seasons ({seasons[0]['y']}-{seasons[-1]['y']}); DPG leader won the Hodge in {lead} -> "
          f"{OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
