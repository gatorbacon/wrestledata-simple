#!/usr/bin/env python3
"""
READ-ONLY before/after for one wrestler's career: what the site shows today (header record from season_accomplishments,
Season Stats = profile match_list, career record) vs the canonical bout list (`canonical_bouts.py`), season by season, with every
bout that differs listed and the reason.

Usage (repo root):  .venv/bin/python scripts/records/show_wrestler.py --gender boys --career career_000279 [--all-bouts]
"""
import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from canonical_bouts import COUNTED_TYPES, EXCLUDED_TYPES, build_season  # noqa: E402

PUB = ROOT / "frontend" / "hs-ky-ui" / "public" / "data"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gender", default="boys")
    ap.add_argument("--career", required=True)
    ap.add_argument("--all-bouts", action="store_true")
    a = ap.parse_args()
    cdir = ROOT / "data" / "careers" / ("girls" if a.gender == "girls" else "")
    career = json.load(open(cdir / f"{a.career}.json", encoding="utf-8"))
    pub_career = json.load(open(PUB / "careers" / a.gender / f"{a.career}.json", encoding="utf-8"))
    cr = pub_career.get("career_record", {})
    print(f"# {career['canonical_name']} ({a.career}, {a.gender})  |  site career record today: {cr.get('wins')}-{cr.get('losses')}\n")
    tot = collections.Counter()
    for season in sorted(career["seasons"], key=int):
        wid = str(career["seasons"][season])
        sb = build_season(a.gender, int(season))
        info = sb.roster.get(wid, {})
        acc_p = ROOT / "data" / "season_accomplishments" / a.gender / season / "season_accomplishments.json"
        acc = {str(w["season_wrestler_id"]): w for w in json.load(open(acc_p, encoding="utf-8"))["wrestlers"]}.get(wid)
        prof = json.load(open(PUB / "wrestlers" / a.gender / season / "by_id" / f"{wid}.json", encoding="utf-8"))
        ml = prof.get("match_list") or []
        lW, lL = sum(m["result"] == "W" for m in ml), sum(m["result"] == "L" for m in ml)
        rec = sb.record(wid)
        aw, al = (acc["record"]["wins"], acc["record"]["losses"]) if acc else (None, None)
        print(f"## {season}: {info.get('name', '?')} — {info.get('team', '?')} (grade {info.get('grade')})")
        print(f"   header record today (accomplishments): {aw}-{al}   profile record.overall: {prof['record']['overall']}   "
              f"Season Stats (match list) today: {lW}-{lL}   ->  CANONICAL: {rec['W']}-{rec['L']}")
        tot["cW"] += rec["W"]
        tot["cL"] += rec["L"]
        tot["aW"] += aw or 0
        tot["aL"] += al or 0
        tot["lW"] += lW
        tot["lL"] += lL
        # bout-level differences
        name = {i: v["name"] for i, v in sb.roster.items()}
        acc_rows = collections.Counter(r.bout for r in sb.rows if r.owner == wid and r.acc_counted)
        lst = collections.Counter()
        for m in ml:
            lst[(str(m.get("opponent_id")) if m.get("opponent_name") not in (None, "", "Unknown") and not str(m.get("opponent_id")).startswith("OUTSTATE") else None,
                 m["date"], m["result"])] += 1
        used = collections.Counter()
        lines = []
        for b in sorted(sb.wrestler_bouts(wid), key=lambda b: b["date"]):
            if b["rtype"] not in COUNTED_TYPES:
                continue
            opp = [x for x in b["ids"] if x != wid]
            own_rows = [r for r in b["rows"] if r.owner == wid and r.opp_name]
            oname = (own_rows[0].opp_name if own_rows else None) or (name.get(opp[0]) if opp else None) or "(opponent not identified)"
            out = "W" if b["winner"] == wid else "L"
            k = (opp[0] if opp else None, b["date"], out)
            in_list = used[k] < lst[k]
            used[k] += 1
            n_acc = acc_rows.get(b["idx"], 0)
            flags = []
            if n_acc == 0:
                mine = [r for r in b["rows"] if r.owner == wid]
                flags.append("header record MISSES it (" + ("row is in his file but the name/team text doesn't match exactly" if mine
                                                             else "listed only in the opponent's file, not his") + ")")
            elif n_acc > 1:
                flags.append(f"header record counts it {n_acc}x")
            if not in_list:
                flags.append("Season Stats MISSES it")
            if b["rematch"]:
                flags.append("same-day 2nd bout vs same opponent")
            if flags or a.all_bouts:
                lines.append(f"   {b['date']} {out} {b['result']:<14} vs {oname}  [{b['event']}, {b['round'] or '-'}]  " + ("; ".join(flags) or "ok"))
        # match_list entries canonical lacks
        canon_keys = collections.Counter()
        for b in sb.wrestler_bouts(wid):
            if b["rtype"] in COUNTED_TYPES:
                opp = [x for x in b["ids"] if x != wid]
                canon_keys[(opp[0] if opp else None, b["date"], "W" if b["winner"] == wid else "L")] += 1
        for k, n in (lst - canon_keys).items():
            lines.append(f"   Season Stats has {n} entr{'y' if n == 1 else 'ies'} canonical lacks: {k}")
        print("\n".join(lines) if lines else "   (no bout-level differences)")
        print()
    print(f"TOTAL career:  today header-record sum {tot['aW']}-{tot['aL']} | Season Stats sum {tot['lW']}-{tot['lL']} | site career record {cr.get('wins')}-{cr.get('losses')}  ->  CANONICAL {tot['cW']}-{tot['cL']}")


if __name__ == "__main__":
    main()
