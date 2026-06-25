"""
Investigates WHY SoCon shows less TPAR overvaluation than MAC/EIWA
despite having the worst conference modifier (-1.37).

Two hypotheses:
  H1: SoCon wrestlers have more cross-conf exposure → TPAR already
      captures their true quality, less echo chamber inflation.
  H2: SoCon wrestlers at nationals are so heavily seeded vs their
      opponents that seeds trivially win — small sample + lopsided
      matchups make it look fine when it isn't.

For each weak conference (MAC, EIWA, SoCon) and each NCAA qualifier:
  - How many matches are intra-conf vs cross-conf?
  - What's their v1 TPAR?
  - What's their seed?
  - How did they actually do in the tournament?
Also shows the full distribution of intra-conf % for each conference.
"""

import json, glob, pathlib, unicodedata, re, sys
from collections import defaultdict

sys.path.insert(0, "scripts/mat_value")
from compute_mat_value import classify_result_type, result_to_signed

SEASON       = 2026
DATA_DIR     = "mt/rankings_data/ncaa_men"
FRONTEND_DIR = "frontend/wrestledata-ui/public/data"
NCAA_DATE    = "03/21/2026"
NCAA_WEIGHTS = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]
TARGET_CONFS = {"MAC", "EIWA", "SoCon"}

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


def main():
    with open(f"{FRONTEND_DIR}/wrestlers/{SEASON}/index_wrestlers.json") as f:
        index = json.load(f)
    by_id         = {w["wrestler_id"]: w for w in index}
    by_name_wt    = {(norm(w["name"]), int(w["weight_class"])): w["wrestler_id"] for w in index}
    wrestler_team = {w["wrestler_id"]: w["team"] for w in index}

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

    # TPAR v1
    with open(f"{FRONTEND_DIR}/mat_value/{SEASON}/match_mv_impact_{SEASON}.json") as f:
        v1_raw = json.load(f)
    tpar_v1 = {}
    for wid, matches in v1_raw.items():
        reg = [m["mv_impact"] for m in matches if m["date"] != NCAA_DATE]
        if reg:
            tpar_v1[wid] = sum(reg) / len(reg)

    # Load regular season match data — count intra vs cross conf per wrestler
    intra_n  = defaultdict(int)
    cross_n  = defaultdict(int)

    for weight in NCAA_WEIGHTS:
        for pat in [f"weight_class_{weight}.json", f"weight_class_{weight}A.json"]:
            fp = pathlib.Path(DATA_DIR) / str(SEASON) / pat
            if not fp.exists(): continue
            with fp.open() as f:
                matches = json.load(f).get("matches", [])
            for m in matches:
                rt = classify_result_type(m.get("result", ""))
                if rt in ("MFF", "Forfeit"): continue
                if "NCAA Division I Championships" in m.get("event", ""): continue
                w1, w2 = m.get("wrestler1_id"), m.get("wrestler2_id")
                if not w1 or not w2: continue
                c1 = team_conf.get(wrestler_team.get(w1))
                c2 = team_conf.get(wrestler_team.get(w2))
                if not c1 or not c2: continue
                for wid, opp_conf in [(w1, c2), (w2, c1)]:
                    my_conf = team_conf.get(wrestler_team.get(wid))
                    if not my_conf: continue
                    if my_conf == opp_conf:
                        intra_n[wid] += 1
                    else:
                        cross_n[wid] += 1

    # Load tournament matches
    with open(f"data/{SEASON}/ncaa-tourney/parsed/matches.json") as f:
        tourney = json.load(f)

    # Build tournament record per wrestler
    tourney_wins  = defaultdict(int)
    tourney_total = defaultdict(int)
    tourney_seed  = {}
    for m in tourney:
        if m.get("result_type") in {"Forfeit", "MFF"}: continue
        wt   = int(m["weight"])
        w_id = by_name_wt.get((norm(m["winner_name"]), wt))
        l_id = by_name_wt.get((norm(m["loser_name"]), wt))
        ws, ls = m["winner_seed"], m["loser_seed"]
        if w_id:
            tourney_wins[w_id]  += 1
            tourney_total[w_id] += 1
            tourney_seed[w_id]   = ws
        if l_id:
            tourney_total[l_id] += 1
            tourney_seed[l_id]   = ls

    # All NCAA qualifiers from target conferences
    qualifiers = [
        wid for wid in tourney_total
        if team_conf.get(wrestler_team.get(wid)) in TARGET_CONFS
    ]

    # ── Distribution by conference ────────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"  Schedule composition for NCAA qualifiers — MAC vs EIWA vs SoCon")
    print(f"{'='*80}")
    print(f"  {'Conf':<8}  {'n_qual':>6}  {'intra_avg':>10}  {'cross_avg':>10}  "
          f"{'cross_%':>8}  {'total_avg':>10}")
    print(f"  {'-'*8}  {'-'*6}  {'-'*10}  {'-'*10}  {'-'*8}  {'-'*10}")

    conf_quals = defaultdict(list)
    for wid in qualifiers:
        conf = team_conf.get(wrestler_team.get(wid))
        conf_quals[conf].append(wid)

    for conf in ["MAC", "EIWA", "SoCon"]:
        wids = conf_quals[conf]
        if not wids: continue
        intra = [intra_n[w] for w in wids]
        cross = [cross_n[w] for w in wids]
        total = [intra_n[w] + cross_n[w] for w in wids]
        avg_intra  = sum(intra) / len(wids)
        avg_cross  = sum(cross) / len(wids)
        avg_total  = sum(total) / len(wids)
        cross_pct  = 100 * sum(cross) / sum(total) if sum(total) > 0 else 0
        print(f"  {conf:<8}  {len(wids):>6}  {avg_intra:>10.1f}  {avg_cross:>10.1f}  "
              f"{cross_pct:>7.1f}%  {avg_total:>10.1f}")

    # ── Per-wrestler detail ───────────────────────────────────────────────────
    print(f"\n{'='*100}")
    print(f"  Per-qualifier detail  (sorted by conference, then seed)")
    print(f"{'='*100}")
    print(f"  {'Conf':<8}  {'Seed':>5}  {'Name':<24}  {'TPAR':>7}  "
          f"{'Intra':>6}  {'Cross':>6}  {'Cross%':>7}  {'T-Wins':>7}  {'T-Total':>8}")
    print(f"  {'-'*8}  {'-'*5}  {'-'*24}  {'-'*7}  "
          f"{'-'*6}  {'-'*6}  {'-'*7}  {'-'*7}  {'-'*8}")

    for conf in ["MAC", "EIWA", "SoCon"]:
        wids = sorted(conf_quals[conf], key=lambda w: tourney_seed.get(w, 99))
        for wid in wids:
            info   = by_id.get(wid, {})
            name   = info.get("name", "?")[:23]
            seed   = tourney_seed.get(wid, "?")
            tv1    = tpar_v1.get(wid)
            tv1_s  = f"{tv1:>+7.3f}" if tv1 is not None else "     —"
            ic     = intra_n[wid]
            cc     = cross_n[wid]
            tot    = ic + cc
            cpct   = 100 * cc / tot if tot > 0 else 0
            tw     = tourney_wins[wid]
            tt     = tourney_total[wid]
            print(f"  {conf:<8}  {str(seed):>5}  {name:<24}  {tv1_s}  "
                  f"{ic:>6}  {cc:>6}  {cpct:>6.1f}%  {tw:>7}  {tt:>8}")
        print()

    # ── Aggregate: how much is intra-conference TPAR credit worth? ───────────
    # For each conf, compute avg TPAR of qualifiers who went out early vs late
    print(f"\n{'='*80}")
    print(f"  Cross-conf % distribution by conference (all qualifiers)")
    print(f"{'='*80}")
    print(f"  {'Conf':<8}  {'0-20%':>7}  {'20-40%':>8}  {'40-60%':>8}  {'60-80%':>8}  {'>80%':>6}")
    print(f"  {'-'*8}  {'-'*7}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*6}")
    for conf in ["MAC", "EIWA", "SoCon"]:
        wids = conf_quals[conf]
        if not wids: continue
        bkts = [0] * 5
        for wid in wids:
            tot = intra_n[wid] + cross_n[wid]
            pct = 100 * cross_n[wid] / tot if tot > 0 else 0
            i   = min(4, int(pct / 20))
            bkts[i] += 1
        print(f"  {conf:<8}  {bkts[0]:>7}  {bkts[1]:>8}  {bkts[2]:>8}  {bkts[3]:>8}  {bkts[4]:>6}")

    # ── Key question: does cross-conf % predict tournament accuracy? ──────────
    print(f"\n{'='*80}")
    print(f"  TPAR accuracy for qualifier losses — by cross-conf exposure bucket")
    print(f"  (when a MAC/EIWA/SoCon wrestler LOSES, did TPAR predict it?)")
    print(f"{'='*80}")
    print(f"  {'Conf':<8}  {'Cross%':<12}  {'n_losses':>9}  {'TPAR_right':>11}  {'Seed_right':>11}")
    print(f"  {'-'*8}  {'-'*12}  {'-'*9}  {'-'*11}  {'-'*11}")

    loss_rows = []
    for m in tourney:
        if m.get("result_type") in {"Forfeit", "MFF"}: continue
        wt   = int(m["weight"])
        l_id = by_name_wt.get((norm(m["loser_name"]), wt))
        w_id = by_name_wt.get((norm(m["winner_name"]), wt))
        if not l_id or not w_id: continue
        lconf = team_conf.get(wrestler_team.get(l_id))
        if lconf not in TARGET_CONFS: continue
        wv1 = tpar_v1.get(w_id); lv1 = tpar_v1.get(l_id)
        if wv1 is None or lv1 is None: continue
        tot = intra_n[l_id] + cross_n[l_id]
        cpct = 100 * cross_n[l_id] / tot if tot > 0 else 0
        loss_rows.append({
            "conf":       lconf,
            "cross_pct":  cpct,
            "tpar_right": wv1 > lv1,
            "seed_right": m["winner_seed"] < m["loser_seed"],
        })

    for conf in ["MAC", "EIWA", "SoCon"]:
        conf_rows = [r for r in loss_rows if r["conf"] == conf]
        buckets = [("<20%", 0, 20), ("20-40%", 20, 40), ("40-60%", 40, 60), (">60%", 60, 101)]
        for label, lo, hi in buckets:
            subset = [r for r in conf_rows if lo <= r["cross_pct"] < hi]
            if not subset: continue
            tr = sum(1 for r in subset if r["tpar_right"])
            sr = sum(1 for r in subset if r["seed_right"])
            print(f"  {conf:<8}  {label:<12}  {len(subset):>9}  "
                  f"{tr:>5}/{len(subset):<5} ({100*tr/len(subset):>4.0f}%)  "
                  f"{sr:>5}/{len(subset):<5} ({100*sr/len(subset):>4.0f}%)")
        print()


if __name__ == "__main__":
    main()
