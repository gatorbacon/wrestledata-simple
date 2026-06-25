"""
All matches where seed is correct (winner_seed < loser_seed)
but TPAR v1 is wrong (winner TPAR < loser TPAR).
"""

import json
import glob
import unicodedata
import re
from collections import defaultdict

FRONTEND_DIR = "frontend/wrestledata-ui/public/data"
SEASON       = 2026
NCAA_DATE    = "03/21/2026"

CONF_EVENT_MAP = {
    "Big Ten": "Big Ten", "ACC": "ACC", "Big 12": "Big 12",
    "Ivy League": "Ivy League", "MAC Wrestling": "MAC",
    "Southern Conference": "SoCon", "EIWA": "EIWA",
    "PAC-12": "Pac-12", "Pac-12": "Pac-12",
    "Colonial": "CAA", "CAA": "CAA", "SoCon": "SoCon",
}


def normalize(name):
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", name.strip().lower())


def build_team_conf():
    team_conf = {}
    for fpath in glob.glob(f"{FRONTEND_DIR}/wrestlers/{SEASON}/by_id/*.json"):
        with open(fpath) as f:
            d = json.load(f)
        team = d.get("team")
        if not team:
            continue
        for m in d.get("match_list", []):
            for kw, conf in CONF_EVENT_MAP.items():
                if kw.lower() in m.get("event", "").lower() and "championship" in m.get("event", "").lower():
                    team_conf[team] = conf
                    break
    return team_conf


def load_pretourney_v1():
    with open(f"{FRONTEND_DIR}/mat_value/{SEASON}/match_mv_impact_2026.json") as f:
        data = json.load(f)
    out = {}
    for wid, matches in data.items():
        reg = [m["mv_impact"] for m in matches if m["date"] != NCAA_DATE]
        if reg:
            out[wid] = sum(reg) / len(reg)
    return out


def main():
    with open(f"{FRONTEND_DIR}/wrestlers/{SEASON}/index_wrestlers.json") as f:
        index = json.load(f)
    by_name_wt = {(normalize(w["name"]), int(w["weight_class"])): w["wrestler_id"] for w in index}
    by_id      = {w["wrestler_id"]: w for w in index}

    team_conf = build_team_conf()
    tpar      = load_pretourney_v1()

    with open(f"data/{SEASON}/ncaa-tourney/parsed/matches.json") as f:
        tourney = json.load(f)

    rows = []
    for m in tourney:
        if m.get("result_type") in {"Forfeit", "MFF"}:
            continue

        wt   = int(m["weight"])
        w_id = by_name_wt.get((normalize(m["winner_name"]), wt))
        l_id = by_name_wt.get((normalize(m["loser_name"]), wt))
        if not w_id or not l_id:
            continue

        wt_  = tpar.get(w_id)
        lt_  = tpar.get(l_id)
        if wt_ is None or lt_ is None:
            continue

        ws = m["winner_seed"]
        ls = m["loser_seed"]

        seed_correct = ws < ls
        tpar_correct = wt_ >= lt_

        if not (seed_correct and not tpar_correct):
            continue

        wteam = m["winner_team"]
        lteam = m["loser_team"]
        wconf = team_conf.get(wteam, "?")
        lconf = team_conf.get(lteam, "?")

        rows.append({
            "wt":         wt,
            "round":      m.get("round", "?"),
            "winner":     m["winner_name"],
            "ws":         ws,
            "wteam":      wteam,
            "wconf":      wconf,
            "wt_score":   wt_,
            "loser":      m["loser_name"],
            "ls":         ls,
            "lteam":      lteam,
            "lconf":      lconf,
            "lt_score":   lt_,
            "tpar_diff":  lt_ - wt_,   # positive = how much TPAR favored loser
            "seed_diff":  ls - ws,
        })

    rows.sort(key=lambda x: (x["wt"], x["ws"]))

    print(f"\n{'='*110}")
    print(f"  Seed correct, TPAR v1 wrong  —  {len(rows)} matches")
    print(f"{'='*110}")
    print(f"  {'Wt':>3}  {'Rd':<7}  {'Winner':<24} {'WS':>3} {'WConf':<10}  {'WTPAR':>7}  |  "
          f"{'Loser':<24} {'LS':>3} {'LConf':<10}  {'LTPAR':>7}  {'TPARΔ':>7}")
    print(f"  {'-'*3}  {'-'*7}  {'-'*24} {'-'*3} {'-'*10}  {'-'*7}  |  "
          f"{'-'*24} {'-'*3} {'-'*10}  {'-'*7}  {'-'*7}")

    for r in rows:
        wn = r["winner"][:23]
        ln = r["loser"][:23]
        print(f"  {r['wt']:>3}  {r['round']:<7}  {wn:<24} #{r['ws']:<2} {r['wconf']:<10}  {r['wt_score']:>+7.3f}  |  "
              f"{ln:<24} #{r['ls']:<2} {r['lconf']:<10}  {r['lt_score']:>+7.3f}  {r['tpar_diff']:>+7.3f}")

    # Summary by loser conference (who is TPAR over-valuing?)
    print(f"\n{'='*60}")
    print(f"  By conference of TPAR-favored loser (over-valued conf)")
    print(f"{'='*60}")
    conf_counts = defaultdict(int)
    for r in rows:
        conf_counts[r["lconf"]] += 1
    for conf, n in sorted(conf_counts.items(), key=lambda x: -x[1]):
        print(f"  {conf:<14}  {n:>3}")

    # Summary by winner conference (who is TPAR under-valuing?)
    print(f"\n{'='*60}")
    print(f"  By conference of seed-correct winner (under-valued conf)")
    print(f"{'='*60}")
    conf_counts2 = defaultdict(int)
    for r in rows:
        conf_counts2[r["wconf"]] += 1
    for conf, n in sorted(conf_counts2.items(), key=lambda x: -x[1]):
        print(f"  {conf:<14}  {n:>3}")

    # Cross-tab: winner conf vs loser conf
    print(f"\n{'='*70}")
    print(f"  Cross-tab: winner conf (under-valued) vs loser conf (over-valued)")
    print(f"{'='*70}")
    xtab = defaultdict(lambda: defaultdict(int))
    for r in rows:
        xtab[r["wconf"]][r["lconf"]] += 1
    all_confs = sorted(set(r["wconf"] for r in rows) | set(r["lconf"] for r in rows))
    header = f"  {'Winner\\Loser':<14}" + "".join(f"{c[:8]:>9}" for c in all_confs)
    print(header)
    for wc in all_confs:
        row_str = f"  {wc:<14}"
        for lc in all_confs:
            n = xtab[wc][lc]
            row_str += f"{'—':>9}" if wc == lc else f"{n if n else '':>9}"
        print(row_str)


if __name__ == "__main__":
    main()
