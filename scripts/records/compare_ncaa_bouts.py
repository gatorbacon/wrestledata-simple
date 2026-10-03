#!/usr/bin/env python3
"""
READ-ONLY before/after report for the NCAA bout-identity fix (TJ, 2026-10-03): which bouts the merged weight-class
files (mt/rankings_data/ncaa_men/{season}/weight_class_*.json, written by load_data.py) gained or lost.

A bout = (wrestler pair, date, result as printed, winner), counted once per season however many weight-class files
carry it (a cross-weight bout sits in both weights' files). A pair+date whose bout COUNT is unchanged but whose result
text changed (the importer now keeps a different team's copy of the same bout) is listed as "same bout, different
copy kept", not as an add + a drop.

Usage:
  .venv/bin/python scripts/records/compare_ncaa_bouts.py --before mt/audits/ncaa_rematch_fix/before_rankings_data \
      --after mt/rankings_data/ncaa_men [--seasons 2012-2026] [--out mt/audits/ncaa_rematch_fix]
Writes {out}/report.md and {out}/bout_changes.csv.
"""
import argparse
import collections
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(folder):
    bouts, names = collections.Counter(), {}
    for f in sorted(Path(folder).glob("weight_class_*.json")):
        d = json.load(open(f, encoding="utf-8"))
        for wid, w in d.get("wrestlers", {}).items():
            names.setdefault(wid, (w.get("name", ""), w.get("team", "")))
        seen = collections.Counter()
        for m in d.get("matches", []):
            k = (m["wrestler1_id"], m["wrestler2_id"], m.get("date", ""), (m.get("result") or "").strip(), m.get("winner_id"),
                 m.get("event", ""))
            seen[k] += 1
        for k, n in seen.items():              # one file can't hold the same bout twice; across files take the max copy count
            bouts[k] = max(bouts[k], n)
    return bouts, names


def seasons_arg(s):
    if "-" in s:
        a, b = s.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in s.split(",")]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--seasons", default="2012-2026")
    ap.add_argument("--out", default="mt/audits/ncaa_rematch_fix")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows, summary = [], []
    for y in seasons_arg(a.seasons):
        bdir, adir = Path(a.before) / str(y), Path(a.after) / str(y)
        if not bdir.exists() or not adir.exists():
            continue
        before, nb = load(bdir)
        after, na = load(adir)
        names = {**nb, **na}
        by_pd = collections.defaultdict(lambda: [collections.Counter(), collections.Counter()])
        for k, n in before.items():
            by_pd[k[:3]][0][k] += n
        for k, n in after.items():
            by_pd[k[:3]][1][k] += n
        cnt = collections.Counter()
        for (w1, w2, date), (bc, ac) in by_pd.items():
            if bc == ac:
                continue
            nbf, naf = sum(bc.values()), sum(ac.values())
            kind = "added" if naf > nbf else "dropped" if naf < nbf else "same bout, different copy kept"
            changed = (ac - bc) if kind != "dropped" else (bc - ac)
            if kind == "same bout, different copy kept":
                changed = ac - bc
            cnt[kind] += abs(naf - nbf) if kind != "same bout, different copy kept" else 1
            for k in changed:
                n1, t1 = names.get(w1, ("?", "?"))
                n2, t2 = names.get(w2, ("?", "?"))
                win = n1 if k[4] == w1 else n2
                rows.append({"season": y, "change": kind, "date": date, "event": k[5], "wrestler_1": f"{n1} ({t1})",
                             "wrestler_2": f"{n2} ({t2})", "winner": win, "result": k[3],
                             "before_results": " | ".join(sorted(x[3] for x in bc)), "after_results": " | ".join(sorted(x[3] for x in ac))})
        summary.append((y, sum(before.values()), sum(after.values()), cnt["added"], cnt["dropped"],
                        cnt["same bout, different copy kept"]))
    with open(out / "bout_changes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["season"])
        w.writeheader()
        w.writerows(rows)
    L = ["# NCAA bout-identity fix: before / after\n",
         "Bouts in the merged weight-class files (one per pair + date + result + winner, however many weight files hold it). "
         "Details per bout: `bout_changes.csv`.\n",
         "| Season | Bouts before | Bouts after | Added | Dropped | Same bout, different copy kept |", "|---|---:|---:|---:|---:|---:|"]
    for y, b, a_, ad, dr, ch in summary:
        L.append(f"| {y} | {b:,} | {a_:,} | {ad} | {dr} | {ch} |")
    t = [sum(x[i] for x in summary) for i in range(1, 6)]
    L.append(f"| **All** | {t[0]:,} | {t[1]:,} | {t[2]} | {t[3]} | {t[4]} |")
    nc = [r for r in rows if "Division I Championships" in r["event"]]
    if nc:
        L += ["\n## NCAA championships\n", "| Season | Change | Bout | Result | Before | After |", "|---|---|---|---|---|---|"]
        for r in nc:
            L.append(f"| {r['season']} | {r['change']} | {r['wrestler_1']} vs {r['wrestler_2']} | {r['winner']} {r['result']} | "
                     f"{r['before_results']} | {r['after_results']} |")
    (out / "report.md").write_text("\n".join(L) + "\n")
    print("\n".join(L[:len(summary) + 5]))
    print("wrote", out / "report.md", out / "bout_changes.csv")


if __name__ == "__main__":
    main()
