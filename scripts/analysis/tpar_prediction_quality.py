"""
Continuous prediction quality comparison: v1 vs v3b.

For every NCAA tournament match, compute:
  diff_v1  = tpar_v1[winner]  - tpar_v1[loser]
  diff_v3b = tpar_v3b[winner] - tpar_v3b[loser]
  delta    = diff_v3b - diff_v1

Positive delta = v3b moved in the RIGHT direction (more confident the winner
  wins, or less confident in the wrong direction — either way, better).
Negative delta = v3b moved in the WRONG direction.

This is model-agnostic to the binary correct/incorrect threshold.
"""

import json, glob, unicodedata, re
from collections import defaultdict
from pathlib import Path

SEASON       = 2026
FRONTEND_DIR = "frontend/wrestledata-ui/public/data"
NCAA_DATE    = "03/21/2026"

CONF_EVENT_MAP = {
    "Big Ten": "Big Ten", "ACC": "ACC", "Big 12": "Big 12",
    "Ivy League": "CAA", "MAC Wrestling": "MAC",
    "Southern Conference": "SoCon", "EIWA": "EIWA",
    "PAC-12": "Pac-12", "Pac-12": "Pac-12",
    "Colonial": "CAA", "CAA": "CAA", "SoCon": "SoCon",
}


def norm(name):
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", name.strip().lower())


def pretourney(path):
    with open(path) as f:
        raw = json.load(f)
    out = {}
    for wid, matches in raw.items():
        reg = [m["mv_impact"] for m in matches if m["date"] != NCAA_DATE]
        if reg:
            out[wid] = sum(reg) / len(reg)
    return out


def main():
    with open(f"{FRONTEND_DIR}/wrestlers/{SEASON}/index_wrestlers.json") as f:
        index = json.load(f)
    by_name_wt = {(norm(w["name"]), int(w["weight_class"])): w["wrestler_id"] for w in index}
    by_id      = {w["wrestler_id"]: w for w in index}

    team_conf = {}
    for fpath in glob.glob(f"{FRONTEND_DIR}/wrestlers/{SEASON}/by_id/*.json"):
        with open(fpath) as f:
            d = json.load(f)
        team = d.get("team")
        if not team:
            continue
        for m in d.get("match_list", []):
            for kw, conf in CONF_EVENT_MAP.items():
                if kw.lower() in m.get("event","").lower() and "championship" in m.get("event","").lower():
                    team_conf[team] = conf
                    break

    tpar_v1  = pretourney(f"{FRONTEND_DIR}/mat_value/{SEASON}/match_mv_impact_{SEASON}.json")
    tpar_v3b = pretourney(f"{FRONTEND_DIR}/mat_value/{SEASON}/match_mv_impact_v3b_{SEASON}.json")

    with open(f"data/{SEASON}/ncaa-tourney/parsed/matches.json") as f:
        tourney = json.load(f)

    rows = []
    for m in tourney:
        if m.get("result_type") in {"Forfeit", "MFF"}:
            continue
        wt   = int(m["weight"])
        w_id = by_name_wt.get((norm(m["winner_name"]), wt))
        l_id = by_name_wt.get((norm(m["loser_name"]), wt))
        if not w_id or not l_id:
            continue
        wv1 = tpar_v1.get(w_id);   lv1 = tpar_v1.get(l_id)
        wb  = tpar_v3b.get(w_id);  lb  = tpar_v3b.get(l_id)
        if None in (wv1, lv1, wb, lb):
            continue

        diff_v1  = wv1 - lv1
        diff_v3b = wb  - lb
        delta    = diff_v3b - diff_v1

        wteam = m["winner_team"]; lteam = m["loser_team"]
        wconf = team_conf.get(wteam, "?"); lconf = team_conf.get(lteam, "?")

        rows.append({
            "wt":       wt,
            "round":    m.get("round", "?"),
            "winner":   m["winner_name"],
            "loser":    m["loser_name"],
            "wconf":    wconf,
            "lconf":    lconf,
            "ws":       m["winner_seed"],
            "ls":       m["loser_seed"],
            "diff_v1":  diff_v1,
            "diff_v3b": diff_v3b,
            "delta":    delta,
        })

    total = len(rows)
    improved = sum(1 for r in rows if r["delta"] > 0)
    worsened = sum(1 for r in rows if r["delta"] < 0)
    unchanged = total - improved - worsened
    mean_delta = sum(r["delta"] for r in rows) / total

    # Binary accuracy
    correct_v1  = sum(1 for r in rows if r["diff_v1"]  > 0)
    correct_v3b = sum(1 for r in rows if r["diff_v3b"] > 0)

    print(f"\n{'='*65}")
    print(f"  Continuous prediction quality  —  v1 vs v3b")
    print(f"{'='*65}")
    print(f"  Matches analyzed: {total}")
    print(f"  Binary accuracy:  v1={correct_v1}/{total} ({100*correct_v1/total:.1f}%)  "
          f"v3b={correct_v3b}/{total} ({100*correct_v3b/total:.1f}%)")
    print(f"  Mean delta (v3b - v1):  {mean_delta:+.4f}  {'← moving right direction' if mean_delta > 0 else '← moving wrong direction'}")
    print(f"  Improved (delta > 0):   {improved:>4} / {total}  ({100*improved/total:.1f}%)")
    print(f"  Worsened (delta < 0):   {worsened:>4} / {total}  ({100*worsened/total:.1f}%)")
    print(f"  Unchanged (delta = 0):  {unchanged:>4} / {total}  ({100*unchanged/total:.1f}%)")

    # Distribution of deltas
    DBKTS = [
        ("< -1.0",  None,  -1.0),
        ("-1.0–-0.5", -1.0, -0.5),
        ("-0.5–-0.2", -0.5, -0.2),
        ("-0.2–0.0", -0.2,  0.0),
        ("0.0–+0.2",  0.0,  0.2),
        ("+0.2–+0.5", 0.2,  0.5),
        ("+0.5–+1.0", 0.5,  1.0),
        ("> +1.0",   1.0,  None),
    ]
    print(f"\n  Distribution of delta (v3b diff - v1 diff):")
    print(f"  {'Bucket':<14}  {'n':>5}  {'%':>6}  {'sum_delta':>10}  direction")
    print(f"  {'-'*14}  {'-'*5}  {'-'*6}  {'-'*10}  {'-'*18}")
    for label, lo, hi in DBKTS:
        subset = [r for r in rows if
                  (lo is None or r["delta"] >= lo) and
                  (hi is None or r["delta"] <  hi)]
        if not subset:
            continue
        s = sum(r["delta"] for r in subset)
        pct = 100 * len(subset) / total
        direction = "WORSE  ◄" if (hi is not None and hi <= 0) else ("better" if (lo is not None and lo >= 0) else "")
        print(f"  {label:<14}  {len(subset):>5}  {pct:>5.1f}%  {s:>+10.2f}  {direction}")

    # Breakdown by conference of the loser (who is v3b adjusting?)
    print(f"\n{'='*70}")
    print(f"  By conference — mean delta and direction")
    print(f"{'='*70}")
    print(f"  {'Conf (winner)':<14}  {'n':>5}  {'mean Δ':>8}  {'improved':>9}  {'worsened':>9}")
    print(f"  {'-'*14}  {'-'*5}  {'-'*8}  {'-'*9}  {'-'*9}")
    conf_wrows = defaultdict(list)
    conf_lrows = defaultdict(list)
    for r in rows:
        conf_wrows[r["wconf"]].append(r)
        conf_lrows[r["lconf"]].append(r)

    all_confs = sorted(set(r["wconf"] for r in rows) | set(r["lconf"] for r in rows))
    for conf in all_confs:
        wr = conf_wrows.get(conf, [])
        lr = conf_lrows.get(conf, [])
        combined = list({id(r): r for r in wr + lr}.values())  # deduplicate
        if not combined:
            continue
        md = sum(r["delta"] for r in combined) / len(combined)
        imp = sum(1 for r in combined if r["delta"] > 0)
        wrs = sum(1 for r in combined if r["delta"] < 0)
        print(f"  {conf:<14}  {len(combined):>5}  {md:>+8.3f}  {imp:>8}  {wrs:>9}")

    # Top 20 most improved
    rows_sorted = sorted(rows, key=lambda r: -r["delta"])
    print(f"\n{'='*100}")
    print(f"  Top 20 MOST IMPROVED matches (delta most positive)")
    print(f"{'='*100}")
    print(f"  {'Wt':>3}  {'Rd':<7}  {'Winner':<22} {'WConf':<10}  {'Loser':<22} {'LConf':<10}  "
          f"{'v1 diff':>8}  {'v3b diff':>9}  {'delta':>7}")
    print(f"  {'-'*3}  {'-'*7}  {'-'*22} {'-'*10}  {'-'*22} {'-'*10}  "
          f"{'-'*8}  {'-'*9}  {'-'*7}")
    for r in rows_sorted[:20]:
        wn = r["winner"][:21]; ln = r["loser"][:21]
        print(f"  {r['wt']:>3}  {r['round']:<7}  {wn:<22} {r['wconf']:<10}  "
              f"{ln:<22} {r['lconf']:<10}  "
              f"{r['diff_v1']:>+8.3f}  {r['diff_v3b']:>+9.3f}  {r['delta']:>+7.3f}")

    # Top 20 most regressed
    print(f"\n{'='*100}")
    print(f"  Top 20 MOST REGRESSED matches (delta most negative)")
    print(f"{'='*100}")
    print(f"  {'Wt':>3}  {'Rd':<7}  {'Winner':<22} {'WConf':<10}  {'Loser':<22} {'LConf':<10}  "
          f"{'v1 diff':>8}  {'v3b diff':>9}  {'delta':>7}")
    print(f"  {'-'*3}  {'-'*7}  {'-'*22} {'-'*10}  {'-'*22} {'-'*10}  "
          f"{'-'*8}  {'-'*9}  {'-'*7}")
    for r in reversed(rows_sorted[-20:]):
        wn = r["winner"][:21]; ln = r["loser"][:21]
        print(f"  {r['wt']:>3}  {r['round']:<7}  {wn:<22} {r['wconf']:<10}  "
              f"{ln:<22} {r['lconf']:<10}  "
              f"{r['diff_v1']:>+8.3f}  {r['diff_v3b']:>+9.3f}  {r['delta']:>+7.3f}")


if __name__ == "__main__":
    main()
