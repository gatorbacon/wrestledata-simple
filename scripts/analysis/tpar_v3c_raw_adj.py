"""
TPAR v3c — Conference modifier applied to raw average, not tier_mu.

v3b applied the conference offset to conf_adj_mu (the prior), which gets
mostly washed out when a wrestler has many matches:
  opp_shrunk = (raw_avg × n + conf_adj_mu × 20) / (n + 20)
  → with 50 matches, prior only gets 29% weight

v3c applies the offset to the raw average itself, where the actual echo
chamber bias lives:
  conf_adj_raw = raw_avg + offset × (1 - discount)
  opp_shrunk   = (conf_adj_raw × n + tier_mu × 20) / (n + 20)
  → with 50 matches, the adjustment now hits the dominant 71% slice

Same differential exposure weighting as v3b: each cross-conf match weighted
by |my_conf_offset - opp_conf_offset|, K=10 from v3b sweep.
Sweeps K again since the dynamics change.
"""

import json, sys, glob, pathlib, unicodedata, re
from collections import defaultdict

sys.path.insert(0, "scripts/mat_value")
from compute_mat_value import (
    classify_result_type, result_to_signed, load_rankings,
    compute_tier_averages, interpolate_mu, shrink_opponent_avg,
)

sys.path.insert(0, "scripts/analysis")
from tpar_v3b_differential import (
    build_team_conf, load_shared, load_all_matches,
    compute_raw_avgs, compute_conf_offsets,
    compute_cross_exposure_v3b, pretourney_avg, tournament_accuracy,
    normalize_name,
)

SEASON       = 2026
DATA_DIR     = "mt/rankings_data/ncaa_men"
FRONTEND_DIR = "frontend/wrestledata-ui/public/data"
NCAA_WEIGHTS = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]
K_SHRINK     = 20
NCAA_DATE    = "03/21/2026"
K_VALUES     = [4, 6, 8, 10, 12, 16, 20]


def compute_tpar_v3c(all_matches, raw_avgs, raw_counts, wrestler_wr,
                     wrestler_team, team_conf, rank_maps, tier_cache,
                     conf_offsets, cross_exposure, k_conf):
    """
    v3c: applies conference offset to the raw average (not tier_mu).
    conf_adj_raw = raw_avg + offset × (1 - discount)
    opp_shrunk   = shrink(conf_adj_raw, tier_mu, n)
    """
    impact = defaultdict(list)

    for weight, matches in all_matches.items():
        rmap = rank_maps[weight]

        for m in matches:
            result = m.get("result", "")
            date   = m.get("date", "")
            if "MFF" in result.upper() or "FORFEIT" in result.upper():
                continue
            w1, w2, winner = m.get("wrestler1_id"), m.get("wrestler2_id"), m.get("winner_id")
            if not w1 or not w2:
                continue

            rt = classify_result_type(result)

            for wrestler_id, opp_id in [(w1, w2), (w2, w1)]:
                is_winner = winner == wrestler_id
                rs = result_to_signed(rt, is_winner)
                if rs is None:
                    continue

                opp_wr = wrestler_wr.get(opp_id)
                if opp_wr is None:
                    continue
                opp_weight, opp_rank = opp_wr
                opp_conf = team_conf.get(wrestler_team.get(opp_id))

                opp_t   = tier_cache.get(opp_weight, {})
                opp_max = rank_maps.get(opp_weight, {}).get("__max_rank__", 200)
                mu_opp, _ = interpolate_mu(opp_rank, opp_t, opp_max)

                offset   = conf_offsets.get(opp_conf, {}).get(opp_weight, 0.0) if opp_conf else 0.0
                n_cross  = cross_exposure.get(opp_id, 0.0)
                discount = n_cross / (n_cross + k_conf)

                # v3c: adjust the raw average, not the prior
                opp_raw      = raw_avgs.get(opp_id, mu_opp)
                opp_n        = raw_counts.get(opp_id, 0)
                conf_adj_raw = opp_raw + offset * (1.0 - discount)
                opp_shrunk   = shrink_opponent_avg(conf_adj_raw, mu_opp, opp_n, k=K_SHRINK)

                mv = rs - (-opp_shrunk)
                impact[wrestler_id].append({
                    "wrestler_id": wrestler_id,
                    "opponent_id": opp_id,
                    "date":        date,
                    "result":      result,
                    "mv_impact":   round(mv, 2),
                })

    return dict(impact)


def main():
    print("=" * 60)
    print(f"TPAR v3c — Conference offset applied to raw average")
    print("=" * 60)

    print("\nLoading shared data...")
    team_conf = build_team_conf()
    by_id, wrestler_team, wrestler_wr, rank_maps, tier_cache, index = load_shared()
    by_name_wt = {
        (normalize_name(w["name"]), int(w["weight_class"])): w["wrestler_id"]
        for w in index
    }

    with open("data/2026/ncaa-tourney/parsed/matches.json") as f:
        tourney_matches = json.load(f)

    print("Loading all match data...")
    all_matches = load_all_matches()

    print("Pass 1: raw averages + cross-conference graph...")
    raw_avgs, raw_counts, cross_matches = compute_raw_avgs(all_matches, wrestler_team, team_conf)

    print("Pass 2: conference quality offsets...")
    conf_offsets = compute_conf_offsets(
        all_matches, raw_avgs, raw_counts, wrestler_wr,
        wrestler_team, team_conf, rank_maps, tier_cache
    )

    print("Pass 3: differential cross-conference exposure (same as v3b)...")
    exp_v3b = compute_cross_exposure_v3b(cross_matches, conf_offsets, wrestler_team, team_conf)

    # Baselines
    v1_raw  = json.load(open(f"{FRONTEND_DIR}/mat_value/{SEASON}/match_mv_impact_{SEASON}.json"))
    tpar_v1 = pretourney_avg(v1_raw)
    v1_c, v1_t, _ = tournament_accuracy(tpar_v1, by_name_wt, tourney_matches)

    v3b_path = pathlib.Path(f"{FRONTEND_DIR}/mat_value/{SEASON}/match_mv_impact_v3b_{SEASON}.json")
    v3b_c = v3b_t = None
    if v3b_path.exists():
        v3b_raw = json.load(open(v3b_path))
        tpar_v3b = pretourney_avg(v3b_raw)
        v3b_c, v3b_t, _ = tournament_accuracy(tpar_v3b, by_name_wt, tourney_matches)

    BUCKETS = ["< 0.5", "0.5-1.0", "1.0-2.0", "2.0-3.0", "3.0+"]

    print(f"\n{'='*60}")
    print(f"  K_CONF sweep — tournament accuracy")
    print(f"{'='*60}")
    print(f"  Baseline:")
    print(f"    v1  (no conf prior):      {v1_c}/{v1_t}  ({100*v1_c/v1_t:.1f}%)")
    if v3b_c:
        print(f"    v3b (offset→tier_mu K=10): {v3b_c}/{v3b_t}  ({100*v3b_c/v3b_t:.1f}%)")
    print(f"\n  v3c (offset→raw_avg):")
    print(f"  {'K':>5}  {'Correct':>8}  {'Total':>6}  {'Acc':>7}  {'vs v1':>7}  {'vs v3b':>7}")
    print(f"  {'-'*5}  {'-'*8}  {'-'*6}  {'-'*7}  {'-'*7}  {'-'*7}")

    best_k = None
    best_acc = -1
    best_impact = None

    for k_conf in K_VALUES:
        print(f"\n  Computing v3c K={k_conf}...", end="", flush=True)
        impact_v3c = compute_tpar_v3c(
            all_matches, raw_avgs, raw_counts, wrestler_wr,
            wrestler_team, team_conf, rank_maps, tier_cache,
            conf_offsets, exp_v3b, k_conf
        )
        tpar_v3c = pretourney_avg(impact_v3c)
        c, t, bkts = tournament_accuracy(tpar_v3c, by_name_wt, tourney_matches)
        acc = c / t
        dv1 = f"+{(acc - v1_c/v1_t)*100:.1f}" if acc > v1_c/v1_t else f"{(acc - v1_c/v1_t)*100:.1f}"
        dv3b = (f"+{(acc - v3b_c/v3b_t)*100:.1f}" if v3b_c and acc > v3b_c/v3b_t
                else f"{(acc - v3b_c/v3b_t)*100:.1f}" if v3b_c else "  —")
        print(f"\r  {k_conf:>5}  {c:>8}  {t:>6}  {100*acc:>6.1f}%  {dv1:>7}  {dv3b:>7}")
        for b in BUCKETS:
            bk = bkts.get(b, [0, 0])
            if bk[1] > 0:
                print(f"         {b:<10} {bk[1]:>4}  {bk[0]:>4}  {100*bk[0]/bk[1]:>5.1f}%")

        if acc > best_acc:
            best_acc   = acc
            best_k     = k_conf
            best_impact = impact_v3c

    # Save best
    out_path = pathlib.Path(f"{FRONTEND_DIR}/mat_value/{SEASON}/match_mv_impact_v3c_{SEASON}.json")
    with out_path.open("w") as f:
        json.dump(best_impact, f)
    print(f"\n  Best K={best_k}  ({100*best_acc:.1f}%)  →  {out_path}")

    # Conference breakdown for best K
    tpar_best = pretourney_avg(best_impact)
    conf_stats = defaultdict(lambda: {"v1": [0,0], "v3c": [0,0]})

    CONF_EVENT_MAP = {
        "Big Ten": "Big Ten", "ACC": "ACC", "Big 12": "Big 12",
        "Ivy League": "CAA", "MAC Wrestling": "MAC",
        "Southern Conference": "SoCon", "EIWA": "EIWA",
        "PAC-12": "Pac-12", "Pac-12": "Pac-12",
        "Colonial": "CAA", "CAA": "CAA", "SoCon": "SoCon",
    }
    tc = {}
    import glob as _glob
    for fpath in _glob.glob(f"{FRONTEND_DIR}/wrestlers/{SEASON}/by_id/*.json"):
        with open(fpath) as f:
            d = json.load(f)
        team = d.get("team")
        if not team: continue
        for mm in d.get("match_list", []):
            for kw, conf in CONF_EVENT_MAP.items():
                if kw.lower() in mm.get("event","").lower() and "championship" in mm.get("event","").lower():
                    tc[team] = conf
                    break

    for m in tourney_matches:
        if m.get("result_type") in {"Forfeit", "MFF"}: continue
        wt   = int(m["weight"])
        w_id = by_name_wt.get((normalize_name(m["winner_name"]), wt))
        l_id = by_name_wt.get((normalize_name(m["loser_name"]), wt))
        if not w_id or not l_id: continue
        wv1 = tpar_v1.get(w_id);  lv1 = tpar_v1.get(l_id)
        wc  = tpar_best.get(w_id); lc  = tpar_best.get(l_id)
        if None in (wv1, lv1, wc, lc): continue
        wteam = m["winner_team"]; lteam = m["loser_team"]
        for conf in {tc.get(wteam,"?"), tc.get(lteam,"?")}:
            conf_stats[conf]["v1"][1]  += 1
            conf_stats[conf]["v3c"][1] += 1
            if wv1 >= lv1: conf_stats[conf]["v1"][0]  += 1
            if wc  >= lc:  conf_stats[conf]["v3c"][0] += 1

    print(f"\n{'='*68}")
    print(f"  Best model (K={best_k}) — by conference")
    print(f"{'='*68}")
    print(f"  {'Conf':<12}  {'n':>5}  {'v1%':>7}  {'v3c%':>8}  {'Δ':>6}")
    print(f"  {'-'*12}  {'-'*5}  {'-'*7}  {'-'*8}  {'-'*6}")
    for conf, s in sorted(conf_stats.items(), key=lambda x: -x[1]["v1"][1]):
        v1n, v1t = s["v1"];  v1p = 100*v1n/v1t if v1t else 0
        v3n, v3t = s["v3c"]; v3p = 100*v3n/v3t if v3t else 0
        d = v3p - v1p
        arrow = f"+{d:.1f}" if d > 0 else f"{d:.1f}"
        print(f"  {conf:<12}  {v1t:>5}  {v1p:>6.1f}%  {v3p:>7.1f}%  {arrow:>6}")

    # Fixed / broken vs v1
    fixed = broken = both_right = both_wrong = 0
    for m in tourney_matches:
        if m.get("result_type") in {"Forfeit", "MFF"}: continue
        wt   = int(m["weight"])
        w_id = by_name_wt.get((normalize_name(m["winner_name"]), wt))
        l_id = by_name_wt.get((normalize_name(m["loser_name"]), wt))
        if not w_id or not l_id: continue
        wv1 = tpar_v1.get(w_id);  lv1 = tpar_v1.get(l_id)
        wc  = tpar_best.get(w_id); lc  = tpar_best.get(l_id)
        if None in (wv1, lv1, wc, lc): continue
        tc2 = wv1 >= lv1; bc = wc >= lc
        if tc2 and bc:       both_right += 1
        elif bc and not tc2: fixed      += 1
        elif tc2 and not bc: broken     += 1
        else:               both_wrong  += 1

    print(f"\n  vs TPAR v1:  fixed={fixed}  broken={broken}  "
          f"both_right={both_right}  both_wrong={both_wrong}  net={fixed-broken:+d}")

    # Continuous quality vs v1 and v3b
    rows = []
    v3b_scores = pretourney_avg(json.load(open(v3b_path))) if v3b_path.exists() else {}
    for m in tourney_matches:
        if m.get("result_type") in {"Forfeit", "MFF"}: continue
        wt   = int(m["weight"])
        w_id = by_name_wt.get((normalize_name(m["winner_name"]), wt))
        l_id = by_name_wt.get((normalize_name(m["loser_name"]), wt))
        if not w_id or not l_id: continue
        wv1 = tpar_v1.get(w_id);  lv1 = tpar_v1.get(l_id)
        wc  = tpar_best.get(w_id); lc  = tpar_best.get(l_id)
        if None in (wv1, lv1, wc, lc): continue
        rows.append({
            "diff_v1":  wv1 - lv1,
            "diff_v3c": wc  - lc,
            "diff_v3b": v3b_scores.get(w_id, 0) - v3b_scores.get(l_id, 0) if v3b_scores else None,
        })

    total = len(rows)
    mean_delta_v1  = sum(r["diff_v3c"] - r["diff_v1"] for r in rows) / total
    imp_v1  = sum(1 for r in rows if r["diff_v3c"] > r["diff_v1"])
    wrs_v1  = sum(1 for r in rows if r["diff_v3c"] < r["diff_v1"])

    print(f"\n  Continuous quality vs v1:")
    print(f"    Mean delta:  {mean_delta_v1:+.4f}")
    print(f"    Improved:    {imp_v1} / {total}  ({100*imp_v1/total:.1f}%)")
    print(f"    Worsened:    {wrs_v1} / {total}  ({100*wrs_v1/total:.1f}%)")

    if v3b_scores:
        mean_delta_v3b = sum(r["diff_v3c"] - r["diff_v3b"] for r in rows if r["diff_v3b"] is not None) / total
        imp_v3b = sum(1 for r in rows if r["diff_v3b"] is not None and r["diff_v3c"] > r["diff_v3b"])
        wrs_v3b = sum(1 for r in rows if r["diff_v3b"] is not None and r["diff_v3c"] < r["diff_v3b"])
        print(f"\n  Continuous quality vs v3b:")
        print(f"    Mean delta:  {mean_delta_v3b:+.4f}")
        print(f"    Improved:    {imp_v3b} / {total}  ({100*imp_v3b/total:.1f}%)")
        print(f"    Worsened:    {wrs_v3b} / {total}  ({100*wrs_v3b/total:.1f}%)")


if __name__ == "__main__":
    main()
