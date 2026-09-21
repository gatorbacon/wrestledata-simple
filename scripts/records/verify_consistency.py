#!/usr/bin/env python3
"""
READ-ONLY acceptance test for the canonical-bout rebuild (CLAUDE.md Known Gotcha 15): for every wrestler-season the SAME W-L must appear in
  canonical (scripts/records/canonical_bouts.py)  ==  data/season_accomplishments record  ==  profile record.overall  ==  profile match_list W/L count
and, once career profiles are rebuilt, ==  the season's row in the frontend career file (`seasons[].record` when present).
Prints a summary and the first mismatches; exit code 1 if any wrestler-season disagrees.

Usage (repo root):  .venv/bin/python scripts/records/verify_consistency.py [--gender boys|girls|both] [--season N] [--show 10]
"""
import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from canonical_bouts import build_season  # noqa: E402

PUB = ROOT / "frontend" / "hs-ky-ui" / "public" / "data"
SEASONS = {"boys": range(2013, 2027), "girls": range(2024, 2027)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gender", default="both")
    ap.add_argument("--season", type=int)
    ap.add_argument("--show", type=int, default=10)
    a = ap.parse_args()
    bad_total = 0
    for g in (["boys", "girls"] if a.gender == "both" else [a.gender]):
        for s in SEASONS[g]:
            if a.season and s != a.season:
                continue
            sb = build_season(g, s)
            acc = {str(w["season_wrestler_id"]): w for w in json.load(open(ROOT / "data" / "season_accomplishments" / g / str(s) / "season_accomplishments.json", encoding="utf-8"))["wrestlers"]}
            cnt = collections.Counter()
            bad = []
            for wid in sb.roster:
                r = sb.record(wid)
                canon = f"{r['W']}-{r['L']}"
                cnt["checked"] += 1
                w = acc.get(wid)
                accr = f"{w['record']['wins']}-{w['record']['losses']}" if w else None
                pf = PUB / "wrestlers" / g / str(s) / "by_id" / f"{wid}.json"
                if not pf.exists():
                    cnt["no profile"] += 1
                    profr = mlr = None
                else:
                    p = json.load(open(pf, encoding="utf-8"))
                    profr = p["record"]["overall"]
                    ml = p.get("match_list") or []
                    mlr = f"{sum(m['result'] == 'W' for m in ml)}-{sum(m['result'] == 'L' for m in ml)}"
                vals = {"canonical": canon, "accomplishments": accr, "profile": profr, "match_list": mlr}
                if len({v for v in vals.values() if v is not None}) > 1:
                    bad.append((wid, sb.roster[wid]["name"], vals))
                    cnt["MISMATCH"] += 1
            bad_total += len(bad)
            print(f"{g} {s}: checked {cnt['checked']}, mismatches {cnt['MISMATCH']}, no profile {cnt['no profile']}")
            for wid, name, vals in bad[:a.show]:
                print("   ", wid, name, vals)
    print("\nOK: all consistent" if not bad_total else f"\nFAILED: {bad_total} wrestler-season(s) disagree")
    return 1 if bad_total else 0


if __name__ == "__main__":
    sys.exit(main())
