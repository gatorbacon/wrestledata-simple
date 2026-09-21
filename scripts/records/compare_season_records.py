#!/usr/bin/env python3
"""
READ-ONLY report: how do today's season records differ from the canonical bout list (`canonical_bouts.py`)?

For every HS season it compares, per wrestler, the canonical W-L against the two numbers the site shows today:
  ACC   `data/season_accomplishments/{g}/{season}/season_accomplishments.json` -> record   (header record / career total)
  LIST  the wrestler profile's `match_list` W/L count  (what the "Season Stats" box on the profile page counts)
and attributes every ACC difference to a named cause using row-level provenance (each raw row knows the canonical
bout it belongs to), so the totals reconcile exactly:  ACC = canonical + sum(causes).
LIST differences are attributed by matching match_list entries to canonical bouts (opponent id + date + method type).
Nothing is written except the report files under mt/audits/season_records/.

Usage (repo root):  .venv/bin/python scripts/records/compare_season_records.py [--gender boys|girls|both] [--season N] [--exclude-exhibitions]
Outputs: mt/audits/season_records/summary.md, wrestler_diffs_{gender}_{season}.csv  (one row per wrestler whose numbers differ)
"""
import argparse
import collections
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from canonical_bouts import COUNTED_TYPES, build_season, iso, result_type  # noqa: E402

OUT = ROOT / "mt" / "audits" / "season_records"
PUB = ROOT / "frontend" / "hs-ky-ui" / "public" / "data"
SEASONS = {"boys": range(2013, 2027), "girls": range(2024, 2027)}


def load_acc(gender, season):
    p = ROOT / "data" / "season_accomplishments" / gender / str(season) / "season_accomplishments.json"
    if not p.exists():
        return {}
    return {str(w["season_wrestler_id"]): w for w in json.load(open(p, encoding="utf-8")).get("wrestlers", [])}


def load_profile(gender, season, wid):
    p = PUB / "wrestlers" / gender / str(season) / "by_id" / f"{wid}.json"
    if not p.exists():
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def acc_rows_for(sb, wid):
    """The raw rows the accomplishments script counts for this wrestler, as (row, outcome)."""
    out = []
    for r in sb.rows:
        if r.owner != wid or not r.acc_counted:
            continue
        out.append(r)
    return out


def acc_outcome(r):
    # accomplishments: win iff winner name+team match the wrestler; else loss (only rows where one side matched are counted)
    return "W" if r.owner_won else "L"


LIST_SAMPLES = []


def load_wc_index(gender, season):
    """(sorted id pair, iso date) of every match in the merged rankings_data weight_class files (what profiles are built from)."""
    idx = collections.Counter()
    for f in (ROOT / "mt" / "rankings_data" / f"hs_ky_{gender}" / str(season)).glob("weight_class_*.json"):
        for m in json.load(open(f, encoding="utf-8")).get("matches", []):
            a, b = m.get("wrestler1_id"), m.get("wrestler2_id")
            if a and b:
                idx[(tuple(sorted([str(a), str(b)])), iso(m.get("date")))] += 1
    return idx


def method_lite(m):
    return result_type(m.get("method") or m.get("result_detail") or "")


def compare(gender, season, exclude_exh):
    sb = build_season(gender, season, exclude_exhibitions=exclude_exh)
    acc = load_acc(gender, season)
    wc_idx = load_wc_index(gender, season)
    causes = collections.Counter()           # ACC cause -> net wins/losses moved (list of (dW, dL))
    cause_w, cause_l, cause_n = collections.Counter(), collections.Counter(), collections.Counter()
    diffs = []
    tot = collections.Counter()
    list_causes = collections.Counter()
    list_samples = LIST_SAMPLES
    for wid, info in sb.roster.items():
        canon = sb.record(wid)
        cW, cL = canon["W"], canon["L"]
        a = acc.get(wid)
        aW = a["record"]["wins"] if a else None
        aL = a["record"]["losses"] if a else None
        # ---- rebuild ACC from rows and attribute the differences to causes ----
        rows = acc_rows_for(sb, wid)
        by_bout = collections.defaultdict(list)
        for r in rows:
            by_bout[r.bout].append(r)
        w_causes = collections.Counter()
        seen = set()
        my_bouts = {b["idx"]: b for b in sb.wrestler_bouts(wid) if b["rtype"] in COUNTED_TYPES}
        acc_from_rows_w = acc_from_rows_l = 0
        for bi, rs in by_bout.items():
            for r in rs:
                if acc_outcome(r) == "W":
                    acc_from_rows_w += 1
                else:
                    acc_from_rows_l += 1
            b = sb.bouts[bi] if bi is not None else None
            if bi is None or b is None or b["idx"] not in my_bouts:
                # counted by ACC but not a canonical bout for this wrestler
                for r in rs:
                    why = r.drop_reason or "not a canonical bout"
                    w_causes[(why, acc_outcome(r))] += 1
                continue
            canon_out = "W" if b["winner"] == wid else "L"
            k = len(rs)
            if k > 1:
                for r in rs[1:]:
                    w_causes[("duplicate row(s) of the same bout counted more than once", acc_outcome(r))] += 1
            if acc_outcome(rs[0]) != canon_out:
                w_causes[("winner differs (override / rows disagree)", acc_outcome(rs[0]))] += 1
                w_causes[("winner differs (override / rows disagree)", canon_out)] -= 1
            seen.add(bi)
        for bi, b in my_bouts.items():
            if bi in seen:
                continue
            out = "W" if b["winner"] == wid else "L"
            if b["n_rows"] and not any(r.owner == wid for r in b["rows"]):
                why = "bout only listed in the opponent's file (missing from this wrestler's)"
            elif b["rematch"]:
                why = "rematch (distinct round labels)"
            else:
                why = "in canonical, not counted by accomplishments (name/team mismatch)"
            w_causes[(why, out)] -= 1
        # acc_from_rows should equal the file; track that our replication is right
        tot["wrestlers"] += 1
        if a:
            tot["acc replicated exactly"] += int((acc_from_rows_w, acc_from_rows_l) == (aW, aL))
            tot["acc replicated NOT exactly"] += int((acc_from_rows_w, acc_from_rows_l) != (aW, aL))
        else:
            tot["no accomplishments entry"] += 1
        # ---- LIST (profile match_list) ----
        p = load_profile(gender, season, wid)
        lW = lL = None
        if p is not None:
            ml = p.get("match_list") or []
            lW = sum(1 for m in ml if m.get("result") == "W")
            lL = sum(1 for m in ml if m.get("result") == "L")
            def okey(oid, name=None):
                return None if (not oid or str(oid).startswith("OUTSTATE") or name in ("Unknown", "")) else str(oid)
            keys = collections.Counter()
            for m in ml:
                keys[(okey(m.get("opponent_id"), m.get("opponent_name")), m.get("date"), m.get("result"))] += 1
            cset = collections.Counter()
            cb_by = collections.defaultdict(list)
            for b in my_bouts.values():
                opp = [x for x in b["ids"] if x != wid]
                k3 = (okey(opp[0]) if opp else None, b["date"], "W" if b["winner"] == wid else "L")
                cset[k3] += 1
                cb_by[k3].append(b)
            same_day_opp = collections.Counter((k3[0], k3[1]) for k3 in cset.elements())
            for k2, n in (cset - keys).items():
                b = cb_by[k2][0]
                if k2[0] is None:
                    why = "LIST merges same-day bouts vs unknown/out-of-state opponents (e.g. two forfeits) into one"
                elif (tuple(sorted(b["ids"])), b["date"]) not in wc_idx:
                    why = "LIST lacks a bout that is in raw data but NOT in the rankings_data weight_class files (dropped by load_data)"
                elif same_day_opp[(k2[0], k2[1])] > 1:
                    why = "LIST lacks the 2nd+ bout vs the same opponent on the same day"
                elif b["rtype"] == "MFF":
                    why = "LIST lacks medical forfeits (MFF)"
                elif (tuple(sorted(b["ids"])), b["date"]) not in wc_idx:
                    why = "LIST lacks a bout that is in raw data but NOT in the rankings_data weight_class files (dropped by load_data)"
                else:
                    why = "LIST lacks a bout canonical has (other)"
                    if len(list_samples) < 12:
                        list_samples.append((gender, season, wid, info["name"], k2, b["result"], b["event"], b["n_rows"]))
                list_causes[why] += n
            for k2, n in (keys - cset).items():
                other = [kk for kk in cset if kk[0] == k2[0] and kk[1] == k2[1] and kk[2] != k2[2]]
                if other:
                    why = "LIST has the opposite outcome for this bout (winner differs)"
                elif keys[k2] > 1 and k2[0] is not None:
                    why = "LIST lists the same bout twice"
                else:
                    why = "LIST has an entry canonical lacks (other)"
                    if len(list_samples) < 12:
                        list_samples.append((gender, season, wid, info["name"], k2, "list-only", "", 0))
                list_causes[why] += n
        for (why, out), n in w_causes.items():
            if n:
                cause_n[why] += abs(n)
                (cause_w if out == "W" else cause_l)[why] += n
        tot["canW"] += cW
        tot["canL"] += cL
        if a:
            tot["accW"] += aW
            tot["accL"] += aL
            tot["canW_withacc"] += cW
            tot["canL_withacc"] += cL
        ad = (aW, aL) != (cW, cL) if a else None
        ld = (lW, lL) != (cW, cL) if lW is not None else None
        tot["acc differs"] += int(bool(ad))
        tot["list differs"] += int(bool(ld))
        tot["acc vs list differ"] += int(bool(a and lW is not None and (aW, aL) != (lW, lL)))
        tot["all three agree"] += int(bool(a and lW is not None and (aW, aL) == (cW, cL) == (lW, lL)))
        if ad or ld:
            diffs.append(dict(id=wid, name=info["name"], team=info["team"], canon=f"{cW}-{cL}",
                              acc=f"{aW}-{aL}" if a else "", list=f"{lW}-{lL}" if lW is not None else ""))
    return sb, tot, cause_w, cause_l, cause_n, list_causes, diffs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gender", choices=["boys", "girls", "both"], default="both")
    ap.add_argument("--season", type=int)
    ap.add_argument("--exclude-exhibitions", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    lines = ["# Season record differences: today's site vs the canonical bout list", ""]
    grand_causes = collections.defaultdict(lambda: [0, 0, 0])
    grand_list = collections.Counter()
    rematch_pairs = collections.Counter()
    stat_sum = collections.Counter()
    rematch_ev = collections.Counter()
    grand_tot = collections.Counter()
    for g in (["boys", "girls"] if a.gender == "both" else [a.gender]):
        lines += [f"## {g}", "", "| season | wrestlers | canon bouts | ACC differs | LIST differs | ACC≠LIST | all agree | ACC replicated | ACC not |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for s in SEASONS[g]:
            if a.season and s != a.season:
                continue
            sb, tot, cw, cl, cn, lc, diffs = compare(g, s, a.exclude_exhibitions)
            lines.append(f"| {s} | {tot['wrestlers']} | {sb.stats['canonical bouts']} | {tot['acc differs']} | {tot['list differs']} | "
                         f"{tot['acc vs list differ']} | {tot['all three agree']} | {tot['acc replicated exactly']} | {tot['acc replicated NOT exactly']} |")
            for why in cn:
                grand_causes[why][0] += cn[why]
                grand_causes[why][1] += cw[why]
                grand_causes[why][2] += cl[why]
            grand_list.update(lc)
            grand_tot.update(tot)
            rematch_pairs.update(sb.rematch_round_pairs)
            stat_sum.update(sb.stats)
            with open(OUT / f"rematch_groups_{g}_{s}.csv", "w", newline="", encoding="utf-8") as f:
                wr = csv.writer(f)
                wr.writerow(["evidence", "date", "event", "names", "rounds", "results"])
                gr = collections.defaultdict(list)
                for b in sb.bouts:
                    if b["rematch"] and b["rtype"] in COUNTED_TYPES:
                        gr[(tuple(b["ids"]), b["date"], b["rtype"])].append(b)
                for (ids, d, _), bs in gr.items():
                    both = all(len({r.owner for r in b["rows"]}) == 2 for b in bs) if len(ids) == 2 else False
                    res = [b["result"] for b in bs]
                    real_diff = all(" 0:00" not in x for x in res) and len(set(res)) == len(res)
                    ev = "STRONG" if (both or real_diff) else "WEAK"
                    rematch_ev[ev] += 1
                    nm = " vs ".join(sb.roster.get(i, {}).get("name", i) for i in ids)
                    wr.writerow([ev, d, bs[0]["event"], nm, " | ".join(str(b["round"]) for b in bs), " | ".join(map(str, res))])
            with open(OUT / f"wrestler_diffs_{g}_{s}.csv", "w", newline="", encoding="utf-8") as f:
                wr = csv.DictWriter(f, fieldnames=["id", "name", "team", "canon", "acc", "list"])
                wr.writeheader()
                wr.writerows(sorted(diffs, key=lambda d: d["name"]))
        lines.append("")
    lines += ["## Why ACC (header record) differs from canonical — net wins / losses that ACC has extra (+) or is missing (−)", "",
              "| cause | bouts | wins | losses |", "|---|---|---|---|"]
    for why, (n, w, l) in sorted(grand_causes.items(), key=lambda kv: -kv[1][0]):
        lines.append(f"| {why} | {n} | {w:+d} | {l:+d} |")
    net_w = sum(v[1] for v in grand_causes.values())
    net_l = sum(v[2] for v in grand_causes.values())
    lines += ["", f"Reconciliation (wrestlers with an accomplishments entry): canonical {grand_tot['canW_withacc']}-{grand_tot['canL_withacc']} "
              f"+ causes ({net_w:+d}/{net_l:+d}) = {grand_tot['canW_withacc'] + net_w}-{grand_tot['canL_withacc'] + net_l}; "
              f"accomplishments file total = {grand_tot['accW']}-{grand_tot['accL']}. "
              f"All-wrestler canonical total = {grand_tot['canW']}-{grand_tot['canL']}."]
    lines += ["", "## Why LIST (Season Stats / match list) differs from canonical", "", "| cause | bouts |", "|---|---|"]
    for why, n in grand_list.most_common():
        lines.append(f"| {why} | {n} |")
    lines += ["", "## Builder stats (all seasons)", "", "| stat | count |", "|---|---|"]
    for k, v in stat_sum.most_common():
        lines.append(f"| {k} | {v} |")
    lines += ["", f"## Rematch evidence (all seasons): STRONG = both wrestlers' files list both bouts, or the results differ with real times; "
              f"WEAK = only one side lists each / 0:00 placeholders (these are the judgment calls): {dict(rematch_ev)}"]
    lines += ["", "## Round-label pairs behind 'same-day rematch' bouts (top 25)", "", "| labels | groups |", "|---|---|"]
    for k, v in rematch_pairs.most_common(25):
        lines.append(f"| {k} | {v} |")
    lines += ["", "## Samples of unexplained LIST differences", ""] + [f"- {x}" for x in LIST_SAMPLES]
    (OUT / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
