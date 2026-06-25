"""
Colley matrix rating system for NCAA wrestling.

Pure win/loss from regular-season matches — no margin of victory.
Solves the linear system Cr = b where:
  C[i][i] = 2 + total games played
  C[i][j] = -(games between i and j)
  b[i]    = 1 + (wins - losses) / 2

Compared against TPAR v1 and seeds for 2026 tournament prediction accuracy.
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


def normalize(name):
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", name.strip().lower())


def build_colley(matches):
    wrestlers = set()
    for m in matches:
        if m.get("wrestler1_id"): wrestlers.add(m["wrestler1_id"])
        if m.get("wrestler2_id"): wrestlers.add(m["wrestler2_id"])
    wrestlers = sorted(wrestlers)
    n = len(wrestlers)
    if n == 0:
        return {}
    idx = {wid: i for i, wid in enumerate(wrestlers)}

    C = np.zeros((n, n))
    b = np.zeros(n)
    for i in range(n):
        C[i][i] = 2.0
        b[i]    = 1.0

    for m in matches:
        w1     = m.get("wrestler1_id")
        w2     = m.get("wrestler2_id")
        winner = m.get("winner_id")
        if not w1 or not w2 or not winner: continue
        if w1 not in idx or w2 not in idx: continue
        loser = w2 if winner == w1 else w1
        wi, li = idx[winner], idx[loser]
        C[wi][wi] += 1;  C[li][li] += 1
        C[wi][li] -= 1;  C[li][wi] -= 1
        b[wi] += 0.5;    b[li] -= 0.5

    try:
        ratings = np.linalg.solve(C, b)
    except np.linalg.LinAlgError:
        ratings = np.linalg.lstsq(C, b, rcond=None)[0]

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
    # ── shared data ──────────────────────────────────────────────────────────
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
                if kw.lower() in m.get("event","").lower() and "championship" in m.get("event","").lower():
                    team_conf[team] = conf
                    break

    # ── TPAR v1 (pre-tournament) ──────────────────────────────────────────────
    with open(f"{FRONTEND_DIR}/mat_value/{SEASON}/match_mv_impact_2026.json") as f:
        impact_raw = json.load(f)
    tpar_v1 = {}
    for wid, ms in impact_raw.items():
        reg = [m["mv_impact"] for m in ms if m["date"] != NCAA_DATE]
        if reg:
            tpar_v1[wid] = sum(reg) / len(reg)

    # ── Build Colley ratings ──────────────────────────────────────────────────
    print("Building Colley ratings...")
    colley = {}
    for weight in NCAA_WEIGHTS:
        matches = load_reg_matches(weight)
        colley.update(build_colley(matches))
        print(f"  {weight} lbs: {len([m for m in load_reg_matches(weight)])} matches")

    # ── Tournament prediction accuracy ───────────────────────────────────────
    with open(f"data/{SEASON}/ncaa-tourney/parsed/matches.json") as f:
        tourney = json.load(f)

    tpar_w = tpar_n = 0
    colley_w = colley_n = 0
    seed_w = seed_n = 0
    conf_rows = []

    for m in tourney:
        if m.get("result_type") in {"Forfeit", "MFF"}: continue
        wt   = int(m["weight"])
        w_id = by_name_wt.get((normalize(m["winner_name"]), wt))
        l_id = by_name_wt.get((normalize(m["loser_name"]), wt))
        if not w_id or not l_id: continue

        ws, ls = m["winner_seed"], m["loser_seed"]

        wt1 = tpar_v1.get(w_id);  lt1 = tpar_v1.get(l_id)
        wc  = colley.get(w_id);   lc  = colley.get(l_id)

        if wt1 is not None and lt1 is not None:
            tpar_n += 1
            if wt1 >= lt1: tpar_w += 1

        if wc is not None and lc is not None:
            colley_n += 1
            if wc >= lc: colley_w += 1

        if ws < ls: seed_w += 1
        seed_n += 1

        if wc is not None and lc is not None and wt1 is not None and lt1 is not None:
            wteam = m["winner_team"]; lteam = m["loser_team"]
            conf_rows.append({
                "w_id": w_id, "l_id": l_id,
                "wconf": team_conf.get(wteam,"?"),
                "lconf": team_conf.get(lteam,"?"),
                "seed_correct":   ws < ls,
                "tpar_correct":   wt1 >= lt1,
                "colley_correct": wc >= lc,
            })

    print(f"\n{'='*50}")
    print(f"  Tournament prediction accuracy (2026)")
    print(f"{'='*50}")
    print(f"  Seeds:    {seed_w}/{seed_n}  ({100*seed_w/seed_n:.1f}%)")
    print(f"  TPAR v1:  {tpar_w}/{tpar_n}  ({100*tpar_w/tpar_n:.1f}%)")
    print(f"  Colley:   {colley_w}/{colley_n}  ({100*colley_w/colley_n:.1f}%)")

    # ── Colley vs TPAR breakdown ──────────────────────────────────────────────
    both_right = sum(1 for r in conf_rows if r["tpar_correct"]  and r["colley_correct"])
    colley_only= sum(1 for r in conf_rows if not r["tpar_correct"] and r["colley_correct"])
    tpar_only  = sum(1 for r in conf_rows if r["tpar_correct"]  and not r["colley_correct"])
    both_wrong = sum(1 for r in conf_rows if not r["tpar_correct"] and not r["colley_correct"])

    print(f"\n  Breakdown vs TPAR v1:")
    print(f"  Both right:   {both_right}")
    print(f"  Colley only:  {colley_only}  (Colley fixed, TPAR missed)")
    print(f"  TPAR only:    {tpar_only}   (TPAR right, Colley missed)")
    print(f"  Both wrong:   {both_wrong}")

    # ── Conference error rates ────────────────────────────────────────────────
    conf_stats = defaultdict(lambda: {"tpar_w":0,"colley_w":0,"n":0})
    for r in conf_rows:
        for conf in {r["wconf"], r["lconf"]}:
            conf_stats[conf]["n"] += 1
            if r["tpar_correct"]:   conf_stats[conf]["tpar_w"]   += 1
            if r["colley_correct"]: conf_stats[conf]["colley_w"] += 1

    print(f"\n{'='*60}")
    print(f"  By conference (matches involving conf wrestlers)")
    print(f"{'='*60}")
    print(f"  {'Conf':<12}  {'n':>5}  {'TPAR%':>7}  {'Colley%':>8}")
    print(f"  {'-'*12}  {'-'*5}  {'-'*7}  {'-'*8}")
    for conf, s in sorted(conf_stats.items(), key=lambda x: -x[1]["n"]):
        tp = 100 * s["tpar_w"]   / s["n"]
        cp = 100 * s["colley_w"] / s["n"]
        delta = cp - tp
        arrow = f"  (+{delta:.1f})" if delta > 0 else (f"  ({delta:.1f})" if delta < 0 else "")
        print(f"  {conf:<12}  {s['n']:>5}  {tp:>6.1f}%  {cp:>7.1f}%{arrow}")

    # ── 125 lb rankings: Colley vs TPAR v1 ───────────────────────────────────
    w125 = {w["wrestler_id"]: w for w in index if int(w["weight_class"]) == 125}

    tpar_ranked = sorted(
        [wid for wid in w125 if wid in tpar_v1],
        key=lambda x: -tpar_v1[x]
    )
    tpar_rank = {wid: i+1 for i, wid in enumerate(tpar_ranked)}

    colley_ranked = sorted(
        [wid for wid in w125 if wid in colley],
        key=lambda x: -colley[x]
    )
    colley_rank = {wid: i+1 for i, wid in enumerate(colley_ranked)}

    print(f"\n{'='*90}")
    print(f"  125 lbs — Colley vs TPAR v1 rankings")
    print(f"{'='*90}")
    print(f"  {'Col':>4}  {'V1':>4}  {'Δ':>4}  {'Name':<26}  {'Team':<24}  {'Colley':>8}  {'TPAR':>8}")
    print(f"  {'-'*4}  {'-'*4}  {'-'*4}  {'-'*26}  {'-'*24}  {'-'*8}  {'-'*8}")

    HIGHLIGHT = {"tyler klinsky", "jore volk"}
    prev_grp = -1

    for wid in colley_ranked[:40]:
        cr  = colley_rank[wid]
        v1r = tpar_rank.get(wid, "—")
        d   = (v1r - cr) if isinstance(v1r, int) else 0
        ds  = f"+{d}" if d > 0 else (str(d) if d != 0 else "—")
        name = w125[wid]["name"][:25]
        team = w125[wid].get("team","")[:23]
        cv  = colley.get(wid, 0)
        tv  = tpar_v1.get(wid, 0)
        grp = (cr - 1) // 10
        if grp != prev_grp:
            print(f"  {'─'*85}")
            prev_grp = grp
        flag = " ◄◄◄" if any(h in name.lower() for h in HIGHLIGHT) else ""
        print(f"  {cr:>4}  {str(v1r):>4}  {ds:>4}  {name:<26}  {team:<24}  {cv:>8.4f}  {tv:>+8.3f}{flag}")


if __name__ == "__main__":
    main()
