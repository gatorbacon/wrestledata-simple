#!/usr/bin/env python3
"""
State-tournament placement bouts from the bracket results (TJ 2026-10-07).

Why: the season match data comes only from the per-team TrackWrestling scrape (mt/processed_data). When coaches didn't enter a
bout (common in 2024 girls, the first sanctioned season), it's missing from records, match lists and the compare tool -- even
though the state bracket results (data/hs_ky_{gender}/{season}/placement.txt, which already set state_place) have it. Example:
2024 girls 114 final, Lyla Smith over Juliette Ruiz (MD 13-2): Lyla showed as state champion with no final in her match list.

What this does: reads placement.txt (1st/3rd/5th/7th Place Matches only -- that's all the bracket file holds), resolves each
wrestler to a season_wrestler_id, and writes data/state_bracket_bouts/{gender}/{season}.json. Names are resolved through the
already-settled state placements in data/season_accomplishments/{gender}/{season}/season_accomplishments.json (state_place +
weight + name/team), so hand-made matches from the accomplishments step are reused, not redone.

The file is only a list of the bracket's bouts. Whether each one is ADDED is decided every time the canonical bout list is built
(scripts/records/canonical_bouts.py, `apply_state_bracket_bouts`), against the scraped data as it is at that moment -- a bout is
added only when the scrape doesn't already have it, so a later re-scrape never double-counts it. See that function for the
duplicate checks.

Run:  .venv/bin/python scripts/records/build_state_bracket_bouts.py -gender girls -season 2024
      .venv/bin/python scripts/records/build_state_bracket_bouts.py --all          (every season with a placement.txt)
Prints, per bout: in scrape / ADDED / held for review / unresolved.
"""
import argparse
import collections
import difflib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "records"))
from canonical_bouts import build_season, iso  # noqa: E402

OUT_DIR = ROOT / "data" / "state_bracket_bouts"

# "1st Place Match - Lyla Smith (Boyle County) 21-2 won by major decision over Juliette Ruiz (Ballard) 40-4 (MD 13-2)"
# Team names can hold one level of parens ("Trinity (Louisville)"); results can too ("TF-1.5 4:40 (17-1)").
_TEAM = r"((?:[^()]|\([^()]*\))+)"
LINE_RE = re.compile(
    r"^(?P<place>\d+)(?:st|nd|rd|th)\s+Place\s+Match\s+-\s+(?P<wname>.+?)\s+\(" + _TEAM + r"\)\s+\d+-\d+\s+(?:won|wins)\b.*?\s+over\s+"
    r"(?P<lname>.+?)\s+\(" + _TEAM + r"\)\s+\d+-\d+\s+\((?P<result>(?:[^()]|\([^()]*\))+)\)\s*$")


def parse_placement(path):
    out, weight = [], None
    for raw in open(path, encoding="utf-8"):
        line = raw.strip()
        if not line:
            continue
        if line.isdigit():
            weight = line
            continue
        if "Place Match" not in line:
            continue
        m = LINE_RE.match(line)
        if not m or not weight:
            out.append(dict(weight=weight, line=line, parse_error=True))
            continue
        g = m.groups()
        out.append(dict(weight=weight, place=int(m["place"]), round=f"{m['place']}{'st' if m['place'] == '1' else 'rd' if m['place'] == '3' else 'th'} Place Match",
                        winner_name=m["wname"].strip(), winner_team=g[2].strip(), loser_name=m["lname"].strip(), loser_team=g[4].strip(),
                        result=m["result"].strip(), line=line))
    return out


def _norm(s):
    return re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", (s or "").lower())).strip()


def _team_ok(a, b):
    a, b = _norm(a).replace(" county", " co"), _norm(b).replace(" county", " co")
    return a == b or a in b or b in a


def resolve(acc, name, team, weight, place):
    """season_wrestler_id for a placer: the accomplishments wrestler with this state_place whose name/team/weight fit best."""
    cands = []
    for w in acc:
        if w.get("state_place") != place:
            continue
        sim = difflib.SequenceMatcher(None, _norm(name), _norm(w.get("name"))).ratio()
        team_ok = _team_ok(team, w.get("team"))
        wt_ok = str(w.get("final_weight")) == str(weight)
        score = sim + (0.5 if team_ok else 0) + (0.3 if wt_ok else 0)
        if sim >= 0.85 or (team_ok and (sim >= 0.5 or wt_ok)):
            cands.append((score, w))
    cands.sort(key=lambda x: -x[0])
    if not cands:
        return None
    if len(cands) > 1 and cands[0][0] - cands[1][0] < 0.2:
        return None          # ambiguous -- report, don't guess
    return str(cands[0][1]["season_wrestler_id"])


def _state_ish(event, gender):
    el = (event or "").lower()
    return ("state" in el and "jv" not in el and "semi" not in el and "first round" not in el
            and (gender == "girls" or "girls" not in el))


def state_event(gender, season, state="ky"):
    """(event name, MM/DD/YYYY date) of the varsity state tournament in the scraped data: the state event with the most placement-match
    rows, or (older seasons whose summaries have no round labels, e.g. 2013/2014) the state event with the most rows. JV, girls (in the
    boys data), semi-state and 2021/2023-style "First Round" events are skipped."""
    placed, rows = collections.Counter(), collections.Counter()
    for f in (ROOT / "mt" / "processed_data" / f"hs_{state}_{gender}" / str(season)).glob("*.json"):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for w in d.get("roster", []):
            for m in w.get("matches", []):
                if not _state_ish(m.get("event"), gender):
                    continue
                rows[(m.get("event"), m.get("date"))] += 1
                if "place match" in (m.get("summary") or "").lower():
                    placed[(m.get("event"), m.get("date"))] += 1
    c = placed or rows
    return c.most_common(1)[0][0] if c else (None, None)


def build(gender, season, state="ky", write=True):
    pfile = ROOT / "data" / f"hs_{state}_{gender}" / str(season) / "placement.txt"
    afile = ROOT / "data" / "season_accomplishments" / gender / str(season) / "season_accomplishments.json"
    if not pfile.exists() or not afile.exists():
        print(f"{gender} {season}: no placement.txt or accomplishments, skipped")
        return None
    acc = json.load(open(afile, encoding="utf-8"))
    acc = acc.get("wrestlers", acc) if isinstance(acc, dict) else acc
    event, date = state_event(gender, season, state)
    bouts, unresolved = [], []
    for p in parse_placement(pfile):
        if p.get("parse_error"):
            unresolved.append(dict(reason="could not parse line", **p))
            continue
        wid = resolve(acc, p["winner_name"], p["winner_team"], p["weight"], p["place"])
        lid = resolve(acc, p["loser_name"], p["loser_team"], p["weight"], p["place"] + 1)
        if not wid or not lid or wid == lid:
            unresolved.append(dict(reason="wrestler not found" if not (wid and lid) else "same id both sides",
                                   winner_id=wid, loser_id=lid, **p))
            continue
        bouts.append(dict(weight=p["weight"], round=p["round"], winner_id=wid, winner_name=p["winner_name"], winner_team=p["winner_team"],
                          loser_id=lid, loser_name=p["loser_name"], loser_team=p["loser_team"], result=p["result"], line=p["line"]))
    data = dict(gender=gender, season=season, source=str(pfile.relative_to(ROOT)), event=event, date=date,
                note="State placement bouts from the bracket results. canonical_bouts.py adds each one only if the scraped data "
                     "doesn't already have it (scripts/records/build_state_bracket_bouts.py).",
                bouts=bouts, unresolved=unresolved)
    if write:
        out = OUT_DIR / gender / f"{season}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        json.dump(data, open(out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    return data


def report(gender, season, verbose=True):
    sb = build_season(gender, season)
    st = collections.Counter(s for _, s in sb.bracket_status)
    print(f"\n{gender} {season}: {dict(st)}")
    if verbose:
        for bb, s in sb.bracket_status:
            if s != "in scrape":
                print(f"   {s:<34} {bb['weight']:>4} {bb['round']:<16} {bb['winner_name']} ({bb['winner_team']}) over "
                      f"{bb['loser_name']} ({bb['loser_team']}) ({bb['result']})")
    return st


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-gender", choices=["boys", "girls"])
    ap.add_argument("-season", type=int)
    ap.add_argument("--all", action="store_true", help="every gender/season that has a placement.txt")
    ap.add_argument("-state", default="ky")
    a = ap.parse_args()
    if a.all:
        jobs = sorted((p.parts[-3].split("_")[-1], int(p.parts[-2])) for p in (ROOT / "data").glob(f"hs_{a.state}_*/*/placement.txt"))
    elif a.gender and a.season:
        jobs = [(a.gender, a.season)]
    else:
        ap.error("give -gender and -season, or --all")
    total = collections.Counter()
    for g, s in jobs:
        d = build(g, s, a.state)
        if d is None:
            continue
        print(f"{g} {s}: {len(d['bouts'])} bracket bouts, event {d['event']!r} {d['date']}, {len(d['unresolved'])} unresolved")
        for u in d["unresolved"]:
            print(f"   UNRESOLVED ({u['reason']}): {u['line']}")
        total.update(report(g, s))
    print("\nTOTAL", dict(total))


if __name__ == "__main__":
    main()
