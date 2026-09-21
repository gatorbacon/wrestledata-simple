#!/usr/bin/env python3
"""
READ-ONLY preview of the all-time CAREER WINS leaderboard: live site (git HEAD) vs current working tree vs canonical bout list.

Canonical career total = sum of each linked season's canonical W-L (`canonical_bouts.py`), honoring `data/career_record_overrides/{gender}.json`
exactly like `build_career_profiles.py` does (final override -> override numbers; `through_season` -> override + later seasons).
Usage (repo root):  .venv/bin/python scripts/records/career_wins_preview.py [--gender boys] [--top 15]
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from canonical_bouts import build_season  # noqa: E402

LB = "frontend/hs-ky-ui/public/data/leaderboards/{g}/2026/career_wins.json"


def rank_map(entries):
    ordered = sorted(entries, key=lambda e: (-e[1], -(e[1] / max(1, e[1] + e[2])), e[3].lower()))
    return {e[0]: i + 1 for i, e in enumerate(ordered)}, {e[0]: e for e in ordered}


def career_totals(g, sbs, cdir, overrides, include_zero=False):
    canon = {}
    for f in sorted(cdir.glob("career_*.json")):
        c = json.load(open(f, encoding="utf-8"))
        ov = overrides.get(c["career_id"])
        W = L = 0
        if ov:
            W, L = ov["wins"], ov["losses"]
        for y, wid in c["seasons"].items():
            y = int(y)
            if ov and (ov.get("through_season") is None or y <= ov["through_season"]):
                continue
            if y in sbs:
                r = sbs[y].record(str(wid))
                W += r["W"]
                L += r["L"]
        if W or include_zero:
            canon[c["career_id"]] = (c["career_id"], W, L, c.get("canonical_name", ""))
    return canon


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gender", default="boys")
    ap.add_argument("--top", type=int, default=15)
    a = ap.parse_args()
    g = a.gender
    cdir = ROOT / "data" / "careers" / ("girls" if g == "girls" else "")
    op = ROOT / "data" / "career_record_overrides" / f"{g}.json"
    overrides = json.load(open(op)) if op.exists() else {}
    seasons = range(2013, 2027) if g == "boys" else range(2024, 2027)
    canon = career_totals(g, {s: build_season(g, s) for s in seasons}, cdir, overrides)
    canon2 = career_totals(g, {s: build_season(g, s, same_round_is_one_bout=True) for s in seasons}, cdir, overrides)

    live_raw = json.loads(subprocess.check_output(["git", "show", "HEAD:" + LB.format(g=g)], cwd=ROOT))
    local_raw = json.load(open(ROOT / LB.format(g=g), encoding="utf-8"))
    info = {e["career_id"]: e for e in local_raw + live_raw}
    live = [(e["career_id"], e["career_wins"], e["career_losses"], e["name"]) for e in live_raw]
    local = [(e["career_id"], e["career_wins"], e["career_losses"], e["name"]) for e in local_raw]
    rl, el = rank_map(live)
    rw, ew = rank_map(local)
    rc, ec = rank_map(list(canon.values()))
    r2, e2 = rank_map(list(canon2.values()))

    print(f"{'#':>3} {'name':<20} {'team':<16} | {'LIVE site':>12} | {'working tree':>13} | {'CANONICAL':>12} | {'alt: same round=1 bout':>22}")
    top = sorted(rc, key=rc.get)[:a.top]
    ids = top + [i for i in sorted(rl, key=rl.get)[:a.top] if i not in top]
    def fmt(m, r, cid):
        return f"{m[cid][1]}-{m[cid][2]} (#{r[cid]})" if cid in m else "-"
    for cid in ids:
        nm = ec[cid][3] if cid in ec else el[cid][3]
        team = (info.get(cid) or {}).get("team", "")[:16]
        print(f"{rc.get(cid, '-'):>3} {nm:<20} {team:<16} | {fmt(el, rl, cid):>12} | {fmt(ew, rw, cid):>13} | {fmt(ec, rc, cid):>12} | {fmt(e2, r2, cid):>22}")


if __name__ == "__main__":
    main()
