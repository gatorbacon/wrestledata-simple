"""
Massey matrix rating system for NCAA wrestling.

Same iterative network structure as Colley, but uses team point differentials
instead of binary win/loss. A fall win = +6, decision win = +3, decision loss = -3, etc.
The matrix equation Mr = p gives ratings where r_i - r_j = expected point differential.

This tests whether the Colley accuracy drop came from removing margin of victory
(Massey keeps it) or from the network propagation structure (both share).

Compared against TPAR v1, Colley, and seeds.
"""

import json, sys, glob, unicodedata, re
import numpy as np
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, "scripts/mat_value")
from compute_mat_value import classify_result_type

SEASON       = 2026
DATA_DIR     = "mt/rankings_data/ncaa_men"
FRONTEND_DIR = "frontend/wrestledata-ui/public/data"
NCAA_DATE    = "03/21/2026"
NCAA_WEIGHTS = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]

CONF_EVENT_MAP = {
    "Big Ten": "Big Ten", "ACC": "ACC", "Big 12": "Big 12",
    "Ivy League": "Ivy League", "MAC Wrestling": "MAC",
    "Southern Conference": "SoCon", "EIWA": "EIWA",
    "PAC-12": "Pac-12", "Pac-12": "Pac-12",
    "Colonial": "CAA", "CAA": "CAA", "SoCon": "SoCon",
}

RT_PTS = {"Fall": 6, "TF": 5, "MD": 4}   # default = 3 (decision)


def normalize(name):
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", name.strip().lower())


def rt_to_pts(rt):
    for key, pts in RT_PTS.items():
        if key.lower() in rt.lower():
            return pts
    return 3


def build_massey(matches):
    wrestlers = set()
    for m in matches:
        if m.get("wrestler1_id"): wrestlers.add(m["wrestler1_id"])
        if m.get("wrestler2_id"): wrestlers.add(m["wrestler2_id"])
    wrestlers = sorted(wrestlers)
    n = len(wrestlers)
    if n == 0:
        return {}
    idx = {wid: i for i, wid in enumerate(wrestlers)}

    M = np.zeros((n, n))
    p = np.zeros(n)

    for m in matches:
        w1     = m.get("wrestler1_id")
        w2     = m.get("wrestler2_id")
        winner = m.get("winner_id")
        rt     = classify_result_type(m.get("result", ""))
        if not w1 or not w2 or not winner: continue
        if w1 not in idx or w2 not in idx: continue

        pts   = rt_to_pts(rt)
        loser = w2 if winner == w1 else w1
        wi, li = idx[winner], idx[loser]

        M[wi][wi] += 1;  M[li][li] += 1
        M[wi][li] -= 1;  M[li][wi] -= 1
        p[wi] += pts;    p[li] -= pts

    # Massey matrix is rank-deficient — fix by replacing last row with
    # the constraint that ratings sum to zero (sets the scale)
    M[-1, :] = 1
    p[-1]    = 0

    try:
        ratings = np.linalg.solve(M, p)
    except np.linalg.LinAlgError:
        ratings = np.linalg.lstsq(M, p, rcond=None)[0]

    return {wid: float(ratings[idx[wid]]) for wid in wrestlers}


def load_reg_matches(weight):
    raw = []
    for pat in [f"weight_class_{weight}.json", f"weight_class_{weight}A.json"]:
        fp = Path(DATA_DIR) / str(SEASON) / pat
        if fp.exists():
            with fp.open() as f:
                raw.extend(json.load(f).get("matches", []))
    return [
        m for m in raw
        if classify_result_type(m.get("result", "")) not in ("MFF", "Forfeit")
        and "NCAA Division I Championships" not in m.get("event", "")
    ]


def main():
    # ── shared data ───────────────────────────────────────────────────────────
    with open(f"{FRONTEND_DIR}/wrestlers/{SEASON}/index_wrestlers.json") as f:
        index = json.load(f)
    by_id      = {w["wrestler_id"]: w for w in index}
    by_name_wt = {(normalize(w["name"]), int(w["weight_class"])): w["wrestler_id"] for w in index}

    team_conf = {}
    for fpath in glob.glob(f"{FRONTEND_DIR}/wrestlers/{SEASON}/by_id/*.json"):
        with open(fpath) as f:
            d = json.load(f)
        team = d.get("team")
        if not team: continue
        for m in d.get("match_list", []):
            for kw, conf in CONF_EVENT_MAP.items():
                if kw.lower() in m.get("event", "").lower() and "championship" in m.get("event", "").lower():
                    team_conf[team] = conf
                    break

    # ── TPAR v1 ───────────────────────────────────────────────────────────────
    with open(f"{FRONTEND_DIR}/mat_value/{SEASON}/match_mv_impact_2026.json") as f:
        impact_raw = json.load(f)
    tpar_v1 = {}
    for wid, ms in impact_raw.items():
        reg = [m["mv_impact"] for m in ms if m["date"] != NCAA_DATE]
        if reg:
            tpar_v1[wid] = sum(reg) / len(reg)

    # ── Build Massey ratings ──────────────────────────────────────────────────
    print("Building Massey ratings...")
    massey = {}
    for weight in NCAA_WEIGHTS:
        matches = load_reg_matches(weight)
        massey.update(build_massey(matches))
    print(f"  {len(massey)} wrestlers rated across all weights")

    # ── Tournament prediction accuracy ────────────────────────────────────────
    with open(f"data/{SEASON}/ncaa-tourney/parsed/matches.json") as f:
        tourney = json.load(f)

    counters = defaultdict(lambda: [0, 0])   # [correct, total]
    conf_stats = defaultdict(lambda: {"tpar": [0,0], "massey": [0,0]})

    for m in tourney:
        if m.get("result_type") in {"Forfeit", "MFF"}: continue
        wt   = int(m["weight"])
        w_id = by_name_wt.get((normalize(m["winner_name"]), wt))
        l_id = by_name_wt.get((normalize(m["loser_name"]), wt))
        ws, ls = m["winner_seed"], m["loser_seed"]
        if not w_id or not l_id: continue

        wt1 = tpar_v1.get(w_id);   lt1 = tpar_v1.get(l_id)
        wm  = massey.get(w_id);    lm  = massey.get(l_id)

        if ws < ls:
            counters["seed"][0] += 1
        counters["seed"][1] += 1

        if wt1 is not None and lt1 is not None:
            if wt1 >= lt1: counters["tpar"][0] += 1
            counters["tpar"][1] += 1

        if wm is not None and lm is not None:
            if wm >= lm: counters["massey"][0] += 1
            counters["massey"][1] += 1

        if wm is not None and lm is not None and wt1 is not None and lt1 is not None:
            wteam = m["winner_team"]; lteam = m["loser_team"]
            for conf in {team_conf.get(wteam,"?"), team_conf.get(lteam,"?")}:
                conf_stats[conf]["tpar"][1]   += 1
                conf_stats[conf]["massey"][1]  += 1
                if wt1 >= lt1: conf_stats[conf]["tpar"][0]   += 1
                if wm  >= lm:  conf_stats[conf]["massey"][0]  += 1

    print(f"\n{'='*55}")
    print(f"  Tournament prediction accuracy — 2026 NCAA")
    print(f"{'='*55}")
    for label, key in [("Seeds", "seed"), ("TPAR v1", "tpar"), ("Colley (binary)", "colley"), ("Massey (margin)", "massey")]:
        if key == "colley":
            print(f"  {label:<18}  380/628  (60.5%)   [prior run]")
            continue
        c, t = counters[key]
        print(f"  {label:<18}  {c}/{t}  ({100*c/t:.1f}%)")

    # ── Breakdown: what did Massey fix vs break vs TPAR? ─────────────────────
    fixed = broken = both_wrong = both_right = 0
    for m in tourney:
        if m.get("result_type") in {"Forfeit", "MFF"}: continue
        wt   = int(m["weight"])
        w_id = by_name_wt.get((normalize(m["winner_name"]), wt))
        l_id = by_name_wt.get((normalize(m["loser_name"]), wt))
        if not w_id or not l_id: continue
        wt1 = tpar_v1.get(w_id); lt1 = tpar_v1.get(l_id)
        wm  = massey.get(w_id);  lm  = massey.get(l_id)
        if None in (wt1, lt1, wm, lm): continue
        tc = wt1 >= lt1;  mc = wm >= lm
        if tc and mc:      both_right += 1
        elif mc and not tc: fixed += 1
        elif tc and not mc: broken += 1
        else:              both_wrong += 1

    print(f"\n  vs TPAR v1:  fixed={fixed}  broken={broken}  both_right={both_right}  both_wrong={both_wrong}")

    # ── Conference breakdown ──────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  By conference")
    print(f"{'='*65}")
    print(f"  {'Conf':<12}  {'n':>5}  {'TPAR%':>7}  {'Massey%':>8}  {'Δ':>6}")
    print(f"  {'-'*12}  {'-'*5}  {'-'*7}  {'-'*8}  {'-'*6}")
    for conf, s in sorted(conf_stats.items(), key=lambda x: -x[1]["tpar"][1]):
        tn, tt = s["tpar"];   tp = 100*tn/tt if tt else 0
        mn, mt = s["massey"]; mp = 100*mn/mt if mt else 0
        d = mp - tp
        arrow = f"+{d:.1f}" if d > 0 else f"{d:.1f}"
        print(f"  {conf:<12}  {tt:>5}  {tp:>6.1f}%  {mp:>7.1f}%  {arrow:>6}")

    # ── 125 lb rankings ───────────────────────────────────────────────────────
    w125 = {w["wrestler_id"]: w for w in index if int(w["weight_class"]) == 125}
    massey_125  = {wid: massey[wid]  for wid in w125 if wid in massey}
    tpar_125    = {wid: tpar_v1[wid] for wid in w125 if wid in tpar_v1}

    massey_rank = {wid: i+1 for i, wid in enumerate(sorted(massey_125,  key=lambda x: -massey_125[x]))}
    tpar_rank   = {wid: i+1 for i, wid in enumerate(sorted(tpar_125,    key=lambda x: -tpar_125[x]))}

    print(f"\n{'='*95}")
    print(f"  125 lbs — Massey vs TPAR v1")
    print(f"{'='*95}")
    print(f"  {'Mas':>4}  {'V1':>4}  {'Δ':>5}  {'Name':<26}  {'Team':<24}  {'Massey':>8}  {'TPAR':>8}")
    print(f"  {'-'*4}  {'-'*4}  {'-'*5}  {'-'*26}  {'-'*24}  {'-'*8}  {'-'*8}")

    HIGHLIGHT = {"tyler klinsky", "jore volk", "christian tanefeu"}
    prev_grp = -1
    for wid in sorted(massey_125, key=lambda x: -massey_125[x])[:45]:
        mr  = massey_rank[wid]
        v1r = tpar_rank.get(wid, "—")
        d   = (v1r - mr) if isinstance(v1r, int) else 0
        ds  = f"+{d}" if d > 0 else (str(d) if d != 0 else "—")
        name = w125[wid]["name"][:25]
        team = w125[wid].get("team", "")[:23]
        mv   = massey_125[wid]
        tv   = tpar_125.get(wid, 0)
        grp  = (mr - 1) // 10
        if grp != prev_grp:
            print(f"  {'─'*90}")
            prev_grp = grp
        flag = " ◄◄◄" if any(h in name.lower() for h in HIGHLIGHT) else ""
        print(f"  {mr:>4}  {str(v1r):>4}  {ds:>5}  {name:<26}  {team:<24}  {mv:>8.3f}  {tv:>+8.3f}{flag}")


if __name__ == "__main__":
    main()
