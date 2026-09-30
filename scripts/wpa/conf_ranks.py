#!/usr/bin/env python3
"""
WPA step 10 -- national rank for every conference-tournament bout (spec: the strength input for conference bouts is
NATIONAL RANK, not conference seed). Writes data/wpa/states/conf_ranks.csv (bout_key, w_rank, l_rank, rank_source,
leak_free) and data/wpa/reports/conf_ranks.md.

Rank source, by season (documented in docs/matsavant.md, WPA section, "Conference rank source"):
  * 2023-2026 -- LEAK-FREE: the latest FloWrestling snapshot dated before Feb 15 of the season
    (data/{season}/flo-preseason-rankings/{date}.json: 2023-01-30, 2024-02-02, 2025-02-03, 2026-02-02). Conference
    tournaments are in late February / March, so this is what a live model would have had (a few weeks old).
    Depth: 24 per weight in 2023, 33 from 2024.
  * 2015-2022 -- no dated pre-tournament ranking exists. Falls back to the end-of-season `current_rank` in the
    MatSavant season profiles (frontend/wrestledata-ui/public/data/wrestlers/{season}/by_id/*.json; era rules in
    docs/matsavant.md "NCAA Ranking Methodology"). Before 2023 its top 8 are NCAA PLACEMENTS -- results from after the
    conference tournament -- so these ranks LEAK the future (TJ decision E: accepted, with a caveat). They are used for
    WPA only; the conference strength layer is fitted and validated on the leak-free seasons alone.
  Ranks deeper than 33 (the profiles fill 34+ from ELO) count as unranked, matching Flo's depth.

Matching (names differ between Flo and TrackWrestling): surname + first initial (td_differential_report.nkey) at the
bout's weight (school must agree when it can be checked; SCHOOL_ALIASES maps the two sources' spellings -- exact
matches only, no fuzzy matching); else the same key at another weight when the school agrees (wrestlers move weights between February
and March); else unranked. The report counts, per conference and season, the Flo-ranked wrestlers from that
conference's teams who were never matched to a bout -- a direct check of the matching.

Usage: .venv/bin/python scripts/wpa/conf_ranks.py
"""
import glob
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts/analysis"))
import td_differential_report as R  # noqa: E402

STATES = ROOT / "data/wpa/states"
REP = ROOT / "data/wpa/reports/conf_ranks.md"
FLO_FIRST = 2023
FLO_CUTOFF = "-02-15"
MAX_RANK = 33


# the same school spelled differently by TrackWrestling and Flo (keys after school_key's normalisation)
SCHOOL_ALIASES = {
    "app state": "appalachian state", "csubakersfield": "csu bakersfield", "csu bakersfield": "csu bakersfield",
    "nd state": "north dakota state", "n dakota state": "north dakota state", "sd state": "south dakota state",
    "s dakota state": "south dakota state", "siue": "siu edwardsville", "uni": "northern iowa", "n iowa": "northern iowa",
    "iowa st": "iowa state", "kent st": "kent state", "n colorado": "northern colorado", "ok state": "oklahoma state",
    "w virginia": "west virginia", "arizona state": "arizona state", "davidson college": "davidson",
    "presbyterian college": "presbyterian", "cal baptist": "california baptist", "citadel": "the citadel",
    "pitt": "pittsburgh", "nc state": "nc state", "north carolina state": "nc state",
}


def school_key(s):
    s = re.sub(r"[^a-z ]", " ", (s or "").lower())
    s = re.sub(r"\b(university|univ)\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return SCHOOL_ALIASES.get(s, SCHOOL_ALIASES.get(s.replace(" ", ""), s))


def same_school(a, b):
    """Exact after normalisation + aliases -- no fuzzy / substring matching ("Penn" must never match "Penn State")."""
    a, b = school_key(a), school_key(b)
    return bool(a) and a == b


def flo_snapshot(season):
    files = sorted(f for f in glob.glob(str(ROOT / f"data/{season}/flo-preseason-rankings/*.json"))
                   if re.search(r"\d{4}-\d{2}-\d{2}\.json$", f) and Path(f).stem < f"{season}{FLO_CUTOFF}")
    if not files:
        return None, None
    d = json.load(open(files[-1]))
    if d.get("source") != "FloWrestling":
        return None, None
    idx = defaultdict(list)   # nkey -> [(rank, school, weight)]
    for w, rows in d["weights"].items():
        for r in rows:
            idx[R.nkey(r["name"])].append((int(r["rank"]), r.get("school"), int(w)))
    return idx, Path(files[-1]).stem


def profile_index(season):
    idx = defaultdict(list)
    for f in glob.glob(str(ROOT / f"frontend/wrestledata-ui/public/data/wrestlers/{season}/by_id/*.json")):
        try:
            p = json.load(open(f))
        except Exception:
            continue
        r = p.get("current_rank")
        wc = p.get("weight_class")
        try:
            wc = int(wc)
        except (TypeError, ValueError):
            wc = None
        idx[R.nkey(p.get("name"))].append((r if isinstance(r, int) else None, p.get("team"), wc))
    return idx


def lookup(idx, name, team, weight):
    """(rank or None, matched?) -- None = unranked (or not found)."""
    c = idx.get(R.nkey(name), [])
    if not c:
        return None, False
    at_w = [x for x in c if x[2] == weight]
    pick = [x for x in at_w if same_school(x[1], team)] or (at_w if len(at_w) == 1 else []) \
        or [x for x in c if same_school(x[1], team)]
    if not pick:
        return None, False
    r = pick[0][0]
    return (r if r is not None and r <= MAX_RANK else None), True


def main():
    b = pd.read_csv(STATES / "conf_bouts.csv", low_memory=False)
    rows, found = [], defaultdict(set)
    src_of = {}
    for season in sorted(b["year"].unique()):
        flo, date = flo_snapshot(season) if season >= FLO_FIRST else (None, None)
        idx = flo if flo is not None else profile_index(season)
        src_of[season] = f"FloWrestling {date} (leak-free)" if flo is not None else "end-of-season current_rank (leaks)"
        for r in b[b["year"] == season].itertuples():
            wr, _ = lookup(idx, r.w_name, r.w_team, int(r.weight))
            lr, _ = lookup(idx, r.l_name, r.l_team, int(r.weight))
            rows.append({"bout_key": r.bout_key, "w_rank": wr, "l_rank": lr, "rank_source": src_of[season],
                         "leak_free": flo is not None})
            for nm in (r.w_name, r.l_name):
                found[season].add(R.nkey(nm))
    out = pd.DataFrame(rows)
    out.to_csv(STATES / "conf_ranks.csv", index=False)

    # ---- report
    m = b.merge(out, on="bout_key")
    L = ["# WPA step 10 — national rank for conference bouts\n",
         "Generated by `scripts/wpa/conf_ranks.py` → `data/wpa/states/conf_ranks.csv`. Source and matching rules: the "
         "script's docstring and `docs/matsavant.md` (WPA section, \"Conference rank source\"). Ranked = top 33 "
         "(top 24 in Flo's 2023 snapshot).\n",
         "| Season | Rank source | Bouts | Both ranked | One | Neither |", "|---|---|---:|---:|---:|---:|"]
    for season, d in m.groupby("year"):
        k = d["w_rank"].notna().astype(int) + d["l_rank"].notna().astype(int)
        L.append(f"| {season} | {src_of[season]} | {len(d):,} | {100 * (k == 2).mean():.0f}% | {100 * (k == 1).mean():.0f}% | "
                 f"{100 * (k == 0).mean():.0f}% |")
    L.append("\n**Matching check (leak-free seasons):** Flo-ranked wrestlers whose school had a wrestler in that "
             "season's conference tournaments at the same weight, but who were never matched to a bout.\n")
    L.append("| Season | Flo-ranked wrestlers from those schools | Not matched | Examples |\n|---|---:|---:|---|")
    for season in sorted(s for s in b["year"].unique() if s >= FLO_FIRST):
        flo, _ = flo_snapshot(season)
        if flo is None:
            continue
        d = b[b["year"] == season]
        teams_w = set(zip(d["w_team"].map(school_key), d["weight"])) | set(zip(d["l_team"].map(school_key), d["weight"]))
        teams = {t for t, _ in teams_w}
        cand, miss = 0, []
        for key, lst in flo.items():
            for rank, school, w in lst:
                if not any(same_school(school, t) for t in teams):
                    continue
                cand += 1
                if key not in found[season]:
                    miss.append(f"{key[1]}. {key[0]} ({school}, {w})")
        L.append(f"| {season} | {cand} | {len(miss)} | {', '.join(miss[:6])}{' …' if len(miss) > 6 else ''} |")
    L.append("\nA miss can be real (the ranked wrestler didn't enter the tournament — injury, redshirt, a weight change "
             "outside the conference field) or a name mismatch; the list is for eyeballing.\n")
    REP.write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
