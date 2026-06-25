"""
TPAR v3b — Bayesian Conference Prior with Differential Weighting

Same as v3 except Pass 3 (cross-conference exposure) weights each cross-conf
match by the QUALITY DIFFERENTIAL between the two conferences instead of the
opposing conference's absolute offset:

  v3:   weight = min(1, |offset_opp|)
  v3b:  weight = min(1, |offset_me - offset_opp|)

Effect:
  MAC  (-0.83) vs EIWA  (-0.73) → |gap|=0.10  → barely counts
  MAC  (-0.83) vs Big 12(+0.75) → |gap|=1.58  → capped at 1.0
  Big Ten(+1.19) vs Big 12(+0.75) → |gap|=0.44 → moderate credit
  Big Ten(+1.19) vs MAC  (-0.83) → |gap|=2.02  → capped at 1.0

This prevents the echo chamber where weak conferences only wrestling each
other still earn "outside exposure" credit and resist the conference prior.

Passes 1 and 2 (raw averages + offset computation) are identical to v3.
Sweeps K_CONF ∈ {4, 6, 8, 10, 12} and reports accuracy for each.
Saves the best-K model to match_mv_impact_v3b_{SEASON}.json.
"""

import json, sys, glob, pathlib, unicodedata, re
from collections import defaultdict

sys.path.insert(0, "scripts/mat_value")
from compute_mat_value import (
    classify_result_type, result_to_signed, load_rankings,
    compute_tier_averages, interpolate_mu, shrink_opponent_avg,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SEASON         = 2026
DATA_DIR       = "mt/rankings_data/ncaa_men"
FRONTEND_DIR   = "frontend/wrestledata-ui/public/data"
NCAA_WEIGHTS   = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]
K_SHRINK       = 20
NCAA_DATE      = "03/21/2026"
K_VALUES       = [4, 6, 8, 10, 12]

CONF_EVENT_MAP = {
    "Big Ten": "Big Ten", "ACC": "ACC", "Big 12": "Big 12",
    "Ivy League": "CAA", "MAC Wrestling": "MAC",
    "Southern Conference": "SoCon", "EIWA": "EIWA",
    "PAC-12": "Pac-12", "Pac-12": "Pac-12",
    "Colonial": "CAA", "CAA": "CAA", "SoCon": "SoCon",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_name(name):
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


def load_shared():
    with open(f"{FRONTEND_DIR}/wrestlers/{SEASON}/index_wrestlers.json") as f:
        index = json.load(f)
    by_id          = {w["wrestler_id"]: w for w in index}
    wrestler_team  = {w["wrestler_id"]: w["team"] for w in index}
    wrestler_wr    = {}

    rank_maps  = {}
    tier_cache = {}
    for w in NCAA_WEIGHTS:
        rmap = load_rankings(SEASON, w, DATA_DIR, use_cache=True, league="ncaa")
        rank_maps[w]  = rmap
        tier_cache[w] = compute_tier_averages(SEASON, w, rmap, DATA_DIR, use_cache=True)
        for wid, rank in rmap.items():
            if wid != "__max_rank__":
                wrestler_wr[wid] = (w, rank)

    return by_id, wrestler_team, wrestler_wr, rank_maps, tier_cache, index


def load_all_matches():
    all_matches = {}
    for w in NCAA_WEIGHTS:
        matches = []
        for pattern in [f"weight_class_{w}.json", f"weight_class_{w}A.json"]:
            wc_file = pathlib.Path(DATA_DIR) / str(SEASON) / pattern
            if wc_file.exists():
                with wc_file.open() as f:
                    matches.extend(json.load(f).get("matches", []))
        all_matches[w] = matches
    return all_matches


# ---------------------------------------------------------------------------
# Pass 1 — raw averages + cross-conference match graph
#           (identical to v3)
# ---------------------------------------------------------------------------

def compute_raw_avgs(all_matches, wrestler_team, team_conf):
    sums   = defaultdict(float)
    counts = defaultdict(int)
    cross  = defaultdict(list)   # wrestler_id -> [(opp_id, opp_conf, weight)]

    for weight, matches in all_matches.items():
        for m in matches:
            result = m.get("result", "")
            if "MFF" in result.upper() or "FORFEIT" in result.upper():
                continue
            w1, w2, winner = m.get("wrestler1_id"), m.get("wrestler2_id"), m.get("winner_id")
            if not w1 or not w2:
                continue
            rt = classify_result_type(result)
            for wid, opp_id in [(w1, w2), (w2, w1)]:
                is_winner = winner == wid
                s = result_to_signed(rt, is_winner)
                if s is None:
                    continue
                sums[wid]   += s
                counts[wid] += 1
                c1 = team_conf.get(wrestler_team.get(wid))
                c2 = team_conf.get(wrestler_team.get(opp_id))
                if c1 and c2 and c1 != c2:
                    cross[wid].append((opp_id, c2, weight))

    raw_avgs = {wid: sums[wid] / counts[wid] for wid in counts if counts[wid] > 0}
    return raw_avgs, dict(counts), dict(cross)


# ---------------------------------------------------------------------------
# Pass 2 — conference quality offsets from cross-conference residuals
#           (identical to v3)
# ---------------------------------------------------------------------------

def compute_conf_offsets(all_matches, raw_avgs, raw_counts, wrestler_wr,
                         wrestler_team, team_conf, rank_maps, tier_cache):
    residuals = defaultdict(lambda: defaultdict(list))

    for weight, matches in all_matches.items():
        rmap     = rank_maps[weight]
        t_avgs   = tier_cache[weight]

        for m in matches:
            result = m.get("result", "")
            if "MFF" in result.upper() or "FORFEIT" in result.upper():
                continue
            w1, w2, winner = m.get("wrestler1_id"), m.get("wrestler2_id"), m.get("winner_id")
            if not w1 or not w2:
                continue
            c1 = team_conf.get(wrestler_team.get(w1))
            c2 = team_conf.get(wrestler_team.get(w2))
            if not c1 or not c2 or c1 == c2:
                continue

            rt = classify_result_type(result)

            for wrestler_id, opp_id, my_conf in [(w1, w2, c1), (w2, w1, c2)]:
                is_winner = winner == wrestler_id
                actual = result_to_signed(rt, is_winner)
                if actual is None:
                    continue
                opp_wr = wrestler_wr.get(opp_id)
                if opp_wr is None:
                    continue
                opp_weight, opp_rank = opp_wr
                opp_t    = tier_cache.get(opp_weight, {})
                opp_max  = rank_maps.get(opp_weight, {}).get("__max_rank__", 200)
                mu_opp, _ = interpolate_mu(opp_rank, opp_t, opp_max)
                opp_raw  = raw_avgs.get(opp_id, mu_opp)
                opp_n    = raw_counts.get(opp_id, 0)
                shrunk   = shrink_opponent_avg(opp_raw, mu_opp, opp_n, k=K_SHRINK)
                expected = -shrunk
                residuals[my_conf][weight].append(actual - expected)

    conf_offsets = {}
    for conf, wt_data in residuals.items():
        conf_offsets[conf] = {}
        for weight, vals in wt_data.items():
            conf_offsets[conf][weight] = sum(vals) / len(vals) if vals else 0.0

    # Normalize: weighted-mean = 0 at each weight
    for weight in NCAA_WEIGHTS:
        vals_and_counts = [
            (conf_offsets[c].get(weight, 0.0), len(residuals[c].get(weight, [])))
            for c in conf_offsets if weight in residuals.get(c, {})
        ]
        if not vals_and_counts:
            continue
        total_n  = sum(n for _, n in vals_and_counts)
        mean_off = sum(v * n for v, n in vals_and_counts) / total_n if total_n else 0.0
        for conf in conf_offsets:
            if weight in conf_offsets[conf]:
                conf_offsets[conf][weight] -= mean_off

    return conf_offsets


# ---------------------------------------------------------------------------
# Pass 3 — cross-conference exposure  ← v3b CHANGE
#
# Weight each cross-conf match by |offset_me - offset_opp| rather than
# just |offset_opp|. This makes MAC vs EIWA (gap≈0.10) count almost
# nothing, while MAC vs Big 12 (gap≈1.58) counts fully.
# ---------------------------------------------------------------------------

def compute_cross_exposure_v3b(cross_matches, conf_offsets, wrestler_team, team_conf):
    """Returns wrestler_id -> effective cross-conference exposure (float)."""
    exposure = {}
    for wid, matches in cross_matches.items():
        my_conf = team_conf.get(wrestler_team.get(wid))
        eff = 0.0
        for opp_id, opp_conf, weight in matches:
            my_off  = conf_offsets.get(my_conf, {}).get(weight, 0.0) if my_conf else 0.0
            opp_off = conf_offsets.get(opp_conf, {}).get(weight, 0.0)
            eff    += min(1.0, abs(my_off - opp_off))
        exposure[wid] = eff
    return exposure


def compute_cross_exposure_v3(cross_matches, conf_offsets, wrestler_wr):
    """Original v3 exposure (for comparison)."""
    exposure = {}
    for wid, matches in cross_matches.items():
        eff = 0.0
        for opp_id, opp_conf, weight in matches:
            off = conf_offsets.get(opp_conf, {}).get(weight, 0.0)
            eff += min(1.0, abs(off))
        exposure[wid] = eff
    return exposure


# ---------------------------------------------------------------------------
# Pass 4 — TPAR computation for a given K_CONF
# ---------------------------------------------------------------------------

def compute_tpar(all_matches, raw_avgs, raw_counts, wrestler_wr,
                 wrestler_team, team_conf, rank_maps, tier_cache,
                 conf_offsets, cross_exposure, k_conf):
    impact = defaultdict(list)

    for weight, matches in all_matches.items():
        rmap     = rank_maps[weight]

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
                conf_adj_mu = mu_opp + offset * (1.0 - discount)

                opp_raw    = raw_avgs.get(opp_id, mu_opp)
                opp_n      = raw_counts.get(opp_id, 0)
                opp_shrunk = shrink_opponent_avg(opp_raw, conf_adj_mu, opp_n, k=K_SHRINK)

                mv = rs - (-opp_shrunk)
                impact[wrestler_id].append({
                    "wrestler_id": wrestler_id,
                    "opponent_id": opp_id,
                    "date":        date,
                    "result":      result,
                    "mv_impact":   round(mv, 2),
                })

    return dict(impact)


# ---------------------------------------------------------------------------
# Tournament accuracy
# ---------------------------------------------------------------------------

def pretourney_avg(impact_data):
    out = {}
    for wid, matches in impact_data.items():
        reg = [m["mv_impact"] for m in matches if m["date"] != NCAA_DATE]
        if reg:
            out[wid] = sum(reg) / len(reg)
    return out


def tournament_accuracy(tpar_scores, by_name_wt, tourney_matches):
    correct = total = 0
    buckets = defaultdict(lambda: [0, 0])

    for m in tourney_matches:
        if m.get("result_type") in {"Forfeit", "MFF"}:
            continue
        wt   = int(m["weight"])
        w_id = by_name_wt.get((normalize_name(m["winner_name"]), wt))
        l_id = by_name_wt.get((normalize_name(m["loser_name"]), wt))
        wt_  = tpar_scores.get(w_id) if w_id else None
        lt_  = tpar_scores.get(l_id) if l_id else None
        if wt_ is None or lt_ is None:
            continue
        total += 1
        if wt_ >= lt_:
            correct += 1
        diff = abs(wt_ - lt_)
        b = ("< 0.5" if diff < 0.5 else "0.5-1.0" if diff < 1.0
             else "1.0-2.0" if diff < 2.0 else "2.0-3.0" if diff < 3.0 else "3.0+")
        buckets[b][1] += 1
        if wt_ >= lt_:
            buckets[b][0] += 1

    return correct, total, dict(buckets)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print(f"TPAR v3b — Differential Conference Exposure")
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
    n_cross_total = sum(len(v) for v in cross_matches.values())
    print(f"  {len(raw_avgs):,} wrestlers with match data")
    print(f"  {n_cross_total:,} cross-conference match appearances")

    print("Pass 2: conference quality offsets...")
    conf_offsets = compute_conf_offsets(
        all_matches, raw_avgs, raw_counts, wrestler_wr,
        wrestler_team, team_conf, rank_maps, tier_cache
    )

    # Print offsets with average per conference
    print(f"\n  Conference quality offsets (league avg = 0):")
    print(f"  {'Conf':<12}" + "".join(f"  {w:>5}" for w in NCAA_WEIGHTS) + "   AVG")
    print("  " + "-" * (12 + 7 * len(NCAA_WEIGHTS) + 6))
    for conf in sorted(conf_offsets, key=lambda c: -sum(conf_offsets[c].values())/max(1,len(conf_offsets[c]))):
        row  = f"  {conf:<12}"
        vals = []
        for w in NCAA_WEIGHTS:
            v = conf_offsets[conf].get(w)
            if v is not None:
                row  += f"  {v:>+5.2f}"
                vals.append(v)
            else:
                row  += f"  {'--':>5}"
        avg  = sum(vals)/len(vals) if vals else 0
        row += f"   {avg:>+.2f}"
        print(row)

    print("\nPass 3: computing cross-conference exposure...")
    exp_v3  = compute_cross_exposure_v3(cross_matches, conf_offsets, wrestler_wr)
    exp_v3b = compute_cross_exposure_v3b(cross_matches, conf_offsets, wrestler_team, team_conf)

    # Show the difference for a sample of conferences
    print(f"\n  Exposure comparison: v3 (|opp_offset|) vs v3b (|gap|)")
    print(f"  Sample — wrestlers with >0 cross-conference matches:")
    print(f"  {'Conf':<12}  {'n_wres':>6}  {'v3_med':>7}  {'v3b_med':>8}  {'ratio':>7}")
    print(f"  {'-'*12}  {'-'*6}  {'-'*7}  {'-'*8}  {'-'*7}")
    conf_exposures = defaultdict(lambda: {"v3": [], "v3b": []})
    for wid in exp_v3:
        conf = team_conf.get(wrestler_team.get(wid))
        if conf and exp_v3[wid] > 0:
            conf_exposures[conf]["v3"].append(exp_v3[wid])
            conf_exposures[conf]["v3b"].append(exp_v3b.get(wid, 0.0))
    for conf in sorted(conf_exposures, key=lambda c: -sum(conf_exposures[c]["v3"])/max(1,len(conf_exposures[c]["v3"]))):
        v3l  = conf_exposures[conf]["v3"]
        v3bl = conf_exposures[conf]["v3b"]
        if not v3l:
            continue
        med_v3  = sorted(v3l)[len(v3l)//2]
        med_v3b = sorted(v3bl)[len(v3bl)//2]
        ratio   = med_v3b / med_v3 if med_v3 > 0 else 0
        print(f"  {conf:<12}  {len(v3l):>6}  {med_v3:>7.2f}  {med_v3b:>8.2f}  {ratio:>6.2f}x")

    # Load v1 for comparison baseline
    v1_raw  = json.load(open(f"{FRONTEND_DIR}/mat_value/{SEASON}/match_mv_impact_{SEASON}.json"))
    tpar_v1 = pretourney_avg(v1_raw)
    v1_c, v1_t, _ = tournament_accuracy(tpar_v1, by_name_wt, tourney_matches)

    # Load v3 for comparison
    v3_path = pathlib.Path(f"{FRONTEND_DIR}/mat_value/{SEASON}/match_mv_impact_v3_{SEASON}.json")
    tpar_v3_scores = None
    v3_c = v3_t = None
    if v3_path.exists():
        v3_raw = json.load(open(v3_path))
        tpar_v3_scores = pretourney_avg(v3_raw)
        v3_c, v3_t, _ = tournament_accuracy(tpar_v3_scores, by_name_wt, tourney_matches)

    print(f"\n{'='*60}")
    print(f"  K_CONF sweep — tournament accuracy")
    print(f"{'='*60}")
    print(f"  Baseline:")
    print(f"    v1 (no conf prior):       {v1_c}/{v1_t}  ({100*v1_c/v1_t:.1f}%)")
    if v3_c is not None:
        print(f"    v3 (|opp_offset|, K=8):   {v3_c}/{v3_t}  ({100*v3_c/v3_t:.1f}%)")
    print(f"\n  v3b (|gap| weighting):")
    print(f"  {'K':>5}  {'Correct':>8}  {'Total':>6}  {'Acc':>7}  {'vs v1':>7}  {'vs v3':>7}")
    print(f"  {'-'*5}  {'-'*8}  {'-'*6}  {'-'*7}  {'-'*7}  {'-'*7}")

    BUCKETS = ["< 0.5", "0.5-1.0", "1.0-2.0", "2.0-3.0", "3.0+"]
    best_k = None
    best_acc = -1
    best_impact = None

    for k_conf in K_VALUES:
        print(f"\n  Computing TPAR v3b K={k_conf}...", end="", flush=True)
        impact_v3b = compute_tpar(
            all_matches, raw_avgs, raw_counts, wrestler_wr,
            wrestler_team, team_conf, rank_maps, tier_cache,
            conf_offsets, exp_v3b, k_conf
        )
        tpar_v3b = pretourney_avg(impact_v3b)
        c, t, bkts = tournament_accuracy(tpar_v3b, by_name_wt, tourney_matches)
        acc = c / t
        dv1 = f"+{(acc - v1_c/v1_t)*100:.1f}" if acc > v1_c/v1_t else f"{(acc - v1_c/v1_t)*100:.1f}"
        dv3 = (f"+{(acc - v3_c/v3_t)*100:.1f}" if v3_c and acc > v3_c/v3_t
               else f"{(acc - v3_c/v3_t)*100:.1f}" if v3_c else "  —")
        print(f"\r  {k_conf:>5}  {c:>8}  {t:>6}  {100*acc:>6.1f}%  {dv1:>7}  {dv3:>7}")

        # Bucket breakdown
        for b in BUCKETS:
            bk = bkts.get(b, [0, 0])
            if bk[1] > 0:
                print(f"         {b:<10} {bk[1]:>4}  {bk[0]:>4}  {100*bk[0]/bk[1]:>5.1f}%")

        if acc > best_acc:
            best_acc    = acc
            best_k      = k_conf
            best_impact = impact_v3b

    # Save best model
    out_path = pathlib.Path(f"{FRONTEND_DIR}/mat_value/{SEASON}/match_mv_impact_v3b_{SEASON}.json")
    with out_path.open("w") as f:
        json.dump(best_impact, f)
    print(f"\n  Best K={best_k}  ({100*best_acc:.1f}%)  saved to {out_path}")

    # Conference breakdown for best K
    tpar_best = pretourney_avg(best_impact)
    conf_stats = defaultdict(lambda: {"v1": [0,0], "v3b": [0,0]})
    for m in tourney_matches:
        if m.get("result_type") in {"Forfeit", "MFF"}:
            continue
        wt   = int(m["weight"])
        w_id = by_name_wt.get((normalize_name(m["winner_name"]), wt))
        l_id = by_name_wt.get((normalize_name(m["loser_name"]), wt))
        if not w_id or not l_id:
            continue
        wv1 = tpar_v1.get(w_id);   lv1 = tpar_v1.get(l_id)
        wb  = tpar_best.get(w_id); lb  = tpar_best.get(l_id)
        if None in (wv1, lv1, wb, lb):
            continue
        wteam = m["winner_team"]; lteam = m["loser_team"]
        for conf in {team_conf.get(wteam,"?"), team_conf.get(lteam,"?")}:
            conf_stats[conf]["v1"][1]  += 1
            conf_stats[conf]["v3b"][1] += 1
            if wv1 >= lv1: conf_stats[conf]["v1"][0]  += 1
            if wb  >= lb:  conf_stats[conf]["v3b"][0] += 1

    print(f"\n{'='*68}")
    print(f"  Best model (K={best_k}) — by conference")
    print(f"{'='*68}")
    print(f"  {'Conf':<12}  {'n':>5}  {'v1%':>7}  {'v3b%':>8}  {'Δ':>6}")
    print(f"  {'-'*12}  {'-'*5}  {'-'*7}  {'-'*8}  {'-'*6}")
    for conf, s in sorted(conf_stats.items(), key=lambda x: -x[1]["v1"][1]):
        v1n, v1t = s["v1"];  v1p = 100*v1n/v1t if v1t else 0
        v3n, v3t = s["v3b"]; v3p = 100*v3n/v3t if v3t else 0
        d = v3p - v1p
        arrow = f"+{d:.1f}" if d > 0 else f"{d:.1f}"
        print(f"  {conf:<12}  {v1t:>5}  {v1p:>6.1f}%  {v3p:>7.1f}%  {arrow:>6}")

    # Fixed / broken vs v1
    fixed = broken = both_right = both_wrong = 0
    for m in tourney_matches:
        if m.get("result_type") in {"Forfeit", "MFF"}:
            continue
        wt   = int(m["weight"])
        w_id = by_name_wt.get((normalize_name(m["winner_name"]), wt))
        l_id = by_name_wt.get((normalize_name(m["loser_name"]), wt))
        if not w_id or not l_id:
            continue
        wv1 = tpar_v1.get(w_id);   lv1 = tpar_v1.get(l_id)
        wb  = tpar_best.get(w_id); lb  = tpar_best.get(l_id)
        if None in (wv1, lv1, wb, lb):
            continue
        tc = wv1 >= lv1; bc = wb >= lb
        if tc and bc:      both_right += 1
        elif bc and not tc: fixed      += 1
        elif tc and not bc: broken     += 1
        else:              both_wrong  += 1

    print(f"\n  vs TPAR v1:  fixed={fixed}  broken={broken}  "
          f"both_right={both_right}  both_wrong={both_wrong}  "
          f"net={fixed - broken:+d}")


if __name__ == "__main__":
    main()
