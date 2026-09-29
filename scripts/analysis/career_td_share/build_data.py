#!/usr/bin/env python3
"""Data for the MatSavant page "NCAA Championships -> Career Takedowns"
(frontend/wrestledata-ui/public/ncaa_career_takedowns.html). Writes ONE file the page fetches:
    frontend/wrestledata-ui/public/data/reports/ncaa_career_td_share.json
Rebuild after each season (full how-to: docs/matsavant.md, "NCAA Career Takedowns page"):
    .venv/bin/python scripts/analysis/career_td_share/build_data.py
Years are detected automatically: every year >= 2015 with data/{year}/ncaa-tourney/bout_detail/. That year's
conference tournaments are included wherever data/{year}/{conf}-tourney/bout_detail/ exists.
Run the NCAA career linking for the new season first (data/careers/ncaa_men/), or its wrestlers fall back to
name+team grouping (the mapping rate printed below drops).

Matches: every NCAA-tournament and conference-tournament bout with play-by-play (bout_detail), 2015 onward,
loaded by scripts/analysis/td_differential_report.py (R.load / R.load_conf); never-wrestled forfeits dropped.
x = takedown share over those matches, y = win % over those matches. Only wrestlers with >= MIN_MATCHES.

Career identity: a bout names a wrestler by (year, name, team). That is mapped to a season_wrestler_id via the
season rosters in mt/processed_data/ncaa_men/{year}/{Team}.json (same surname + first initial, then team, then
weight to break ties), and the season id to a career via data/careers/ncaa_men/career_*.json (seasons dict).
Bouts that can't be mapped are grouped by (surname + first initial, team) instead, so a transfer or a name
the rosters don't know may show up as more than one dot. The script prints the mapping rate.
"""
import json, re, sys
from collections import defaultdict, Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE.parent / "td_custom_report"))
import td_differential_report as R
import build_data as B

MIN_MATCHES = 5
FIRST_YEAR = 2015
YEARS = sorted(int(d.name) for d in (ROOT / "data").iterdir()
               if d.name.isdigit() and int(d.name) >= FIRST_YEAR and (d / "ncaa-tourney/bout_detail").is_dir())
PLACE = {"Final": (1, 2), "3rd": (3, 4), "5th": (5, 6), "7th": (7, 8)}
STOP = {"university", "of", "the", "state", "st", "college", "at", "u"}


def tnorm(t):
    t = (t or "").lower().replace("&", " and ")
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return " ".join(w for w in t.split() if w not in STOP)


def team_match(a, b):
    a, b = tnorm(a), tnorm(b)
    return bool(a and b) and (a == b or a in b or b in a)


def team_label(teams):
    """Most common spelling of each distinct team (by tnorm), up to two teams, e.g. 'Oklahoma / Wyoming'."""
    groups = defaultdict(Counter)
    for t, n in teams.items():
        groups[tnorm(t)][t] += n
    ranked = sorted(groups.values(), key=lambda c: -sum(c.values()))
    return " / ".join(c.most_common(1)[0][0] for c in ranked[:2])


def roster_index():
    idx = defaultdict(list)   # (year, nkey) -> [(sid, team, weight, full name)]
    for y in YEARS:
        d = ROOT / f"mt/processed_data/ncaa_men/{y}"
        if not d.is_dir():
            continue
        for f in d.glob("*.json"):
            t = json.load(open(f))
            for w in t.get("roster", []):
                idx[(y, R.nkey(w["name"]))].append((w["season_wrestler_id"], t["team_name"], str(w.get("weight_class")), w["name"]))
    return idx


def career_index():
    sid2c, cname = {}, {}
    for f in (ROOT / "data/careers/ncaa_men").glob("career_*.json"):
        c = json.load(open(f))
        cname[c["career_id"]] = c["canonical_name"]
        for sid in c["seasons"].values():
            sid2c[str(sid)] = c["career_id"]
    return sid2c, cname


def main():
    ridx = roster_index()
    sid2c, cname = career_index()
    nb, _ = R.load(YEARS)
    cb, _ = R.load_conf(YEARS)
    for b in nb: b["src"] = "NCAA"
    for b in cb: b["src"] = b.get("conf") or "conf"

    # NCAA placements, keyed like bouts: (year, weight, nkey)
    place = {}
    for y in YEARS:
        p = ROOT / f"data/{y}/ncaa-tourney/parsed/matches.json"
        if p.exists():
            for m in json.load(open(p)):
                if m["round"] in PLACE:
                    place[(y, m["weight"], R.nkey(m["winner_name"]))] = PLACE[m["round"]][0]
                    place[(y, m["weight"], R.nkey(m["loser_name"]))] = PLACE[m["round"]][1]
    ncaa_entrants = {(b["year"], b["weight"], R.nkey(b[s])) for b in nb for s in ("winner", "loser")}

    memo, stats = {}, Counter()
    def ident(y, wt, name, team):
        k = (y, wt, R.nkey(name), tnorm(team))
        if k in memo:
            return memo[k]
        cands = ridx.get((y, R.nkey(name)), [])
        if len(cands) > 1:
            c2 = [c for c in cands if team_match(c[1], team)]
            cands = c2 or cands
        if len(cands) > 1:
            c2 = [c for c in cands if c[2] == str(wt)]
            cands = c2 or cands
        if len(cands) > 1:
            c2 = [c for c in cands if " ".join(c[3].lower().split()) == " ".join(name.lower().split())]
            cands = c2 or cands
        cid = sid2c.get(str(cands[0][0])) if len(cands) == 1 else None
        memo[k] = ("C", cid) if cid else ("U", R.nkey(name), tnorm(team))
        return memo[k]

    car = defaultdict(lambda: {"w": 0, "l": 0, "f": 0, "a": 0, "n_ncaa": 0, "names": Counter(), "teams": Counter(),
                               "years": set(), "best": None, "ncaa_years": set()})
    for b in nb + cb:
        if not B.wrestled(b):
            continue
        for s, o in (("winner", "loser"), ("loser", "winner")):
            team = b["wteam"] if s == "winner" else b["lteam"]
            key = ident(b["year"], b["weight"], b[s], team)
            stats["mapped" if key[0] == "C" else "unmapped"] += 1
            r = car[key]
            r["w" if s == "winner" else "l"] += 1
            r["f"] += b["td"][s]; r["a"] += b["td"][o]
            r["names"][b[s]] += 1; r["teams"][team] += 1; r["years"].add(b["year"])
            if b["src"] == "NCAA":
                r["n_ncaa"] += 1; r["ncaa_years"].add(b["year"])
                pl = place.get((b["year"], b["weight"], R.nkey(b[s])))
                if pl and (r["best"] is None or pl < r["best"]):
                    r["best"] = pl

    rows, dropped_few, dropped_td = [], 0, 0
    for key, r in car.items():
        n = r["w"] + r["l"]
        if n < MIN_MATCHES:
            dropped_few += 1; continue
        if r["f"] + r["a"] == 0:
            dropped_td += 1; continue
        name = cname.get(key[1]) if key[0] == "C" else None
        rows.append({"name": name or r["names"].most_common(1)[0][0],
                     "team": team_label(r["teams"]),
                     "yrs": [min(r["years"]), max(r["years"])], "best": r["best"],
                     "ncaa": len(r["ncaa_years"]), "linked": key[0] == "C",
                     "r": [r["w"], r["l"], r["f"], r["a"]]})
    tot = stats["mapped"] + stats["unmapped"]
    meta = {"years": YEARS, "min": MIN_MATCHES, "plotted": len(rows), "few": dropped_few, "no_td": dropped_td,
            "linked_pct": round(100 * stats["mapped"] / tot, 1)}
    from datetime import date
    meta["built"] = date.today().isoformat()
    out = ROOT / "frontend/wrestledata-ui/public/data/reports/ncaa_career_td_share.json"
    out.write_text(json.dumps({"meta": meta, "rows": rows}, separators=(",", ":")))
    print(f"bout-sides mapped to a career: {stats['mapped']}/{tot} ({meta['linked_pct']}%)")
    print(f"{len(rows)} wrestlers plotted (>= {MIN_MATCHES} matches); {dropped_few} with fewer; {dropped_td} with no TDs either way -> {out.relative_to(ROOT)}")
    print("unlinked plotted:", sum(1 for x in rows if not x["linked"]))


if __name__ == "__main__":
    main()
