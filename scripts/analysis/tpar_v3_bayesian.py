"""
TPAR v3 Prototype — Bayesian Conference Quality Prior

Two-level shrinkage:
  Level 1 (existing): shrink opponent raw avg toward weight-class tier mean
  Level 2 (new):      also shrink toward a conference-adjusted tier mean,
                      weighted by how cross-conference-exposed the opponent is

Conference quality offsets are computed from cross-conference match residuals —
no anchor conference, no hardcoded values. League average = 0.

Cross-conference exposure is weighted by the opposing conference's quality
distance from average, so MAC vs EIWA counts less than MAC vs Big Ten.

Does NOT modify any existing files or the main pipeline.
Output: match_mv_impact_v3_{SEASON}.json (parallel to v1)
"""

import json
import sys
import glob
import pathlib
from collections import defaultdict

sys.path.insert(0, "scripts/mat_value")
from compute_mat_value import (
    classify_result_type,
    result_to_signed,
    load_rankings,
    compute_tier_averages,
    interpolate_mu,
    shrink_opponent_avg,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SEASON       = 2026
DATA_DIR     = "mt/rankings_data/ncaa_men"
FRONTEND_DIR = "frontend/wrestledata-ui/public/data"
NCAA_WEIGHTS = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]
K_SHRINK     = 20    # same as v1
K_CONF       = 8     # cross-conference matches needed to halve the conference pull
NCAA_EVENT   = "2026 NCAA Division I Championships"
NCAA_DATE    = "03/21/2026"

CONF_EVENT_MAP = {
    "Big Ten": "Big Ten", "ACC": "ACC", "Big 12": "Big 12",
    "Ivy League": "CAA", "MAC Wrestling": "MAC",
    "Southern Conference": "SoCon", "EIWA": "EIWA",
    "PAC-12": "Pac-12", "Pac-12": "Pac-12",
    "Colonial": "CAA", "CAA": "CAA", "SoCon": "SoCon",
}


# ---------------------------------------------------------------------------
# Shared lookups
# ---------------------------------------------------------------------------

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
    wrestler_wr    = {}   # wrestler_id -> (weight, rank)

    rank_maps  = {}
    tier_cache = {}
    for w in NCAA_WEIGHTS:
        rmap = load_rankings(SEASON, w, DATA_DIR, use_cache=True, league="ncaa")
        rank_maps[w]  = rmap
        tier_cache[w] = compute_tier_averages(SEASON, w, rmap, DATA_DIR, use_cache=True)
        for wid, rank in rmap.items():
            if wid != "__max_rank__":
                wrestler_wr[wid] = (w, rank)

    return by_id, wrestler_team, wrestler_wr, rank_maps, tier_cache


def load_all_matches():
    """Returns: weight -> list of match dicts."""
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
# ---------------------------------------------------------------------------

def compute_raw_avgs(all_matches, wrestler_team, team_conf):
    """
    Returns:
      raw_avgs:       wrestler_id -> float
      raw_counts:     wrestler_id -> int
      cross_matches:  wrestler_id -> list of (opp_id, opp_conf, weight)
    """
    sums   = defaultdict(float)
    counts = defaultdict(int)
    cross  = defaultdict(list)

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
# Pass 2 — conference quality offsets
#
# For every cross-conference match, compute the residual under the current
# model: actual_signed - expected_signed.
# Average by (conference, weight) to get the systematic bias per conference.
# Normalize so league average = 0.
# No anchor: the scale is purely relative to the population mean.
# ---------------------------------------------------------------------------

def compute_conf_offsets(all_matches, raw_avgs, raw_counts, wrestler_wr,
                         wrestler_team, team_conf, rank_maps, tier_cache):
    """
    Returns: conf_offsets[conf][weight] = float
    Positive = conference performs better than tier model expects (underrated).
    Negative = conference performs worse (overrated by rank).
    """
    residuals = defaultdict(lambda: defaultdict(list))

    for weight, matches in all_matches.items():
        rmap     = rank_maps[weight]
        t_avgs   = tier_cache[weight]
        max_rank = rmap.get("__max_rank__", 200)

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
                continue  # only cross-conference

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

                opp_raw = raw_avgs.get(opp_id, mu_opp)
                opp_n   = raw_counts.get(opp_id, 0)
                shrunk  = shrink_opponent_avg(opp_raw, mu_opp, opp_n, k=K_SHRINK)
                expected = -shrunk

                residuals[my_conf][weight].append(actual - expected)

    # Average residuals per (conf, weight), then normalize so mean across
    # conferences = 0 at each weight class
    conf_offsets = {}
    for conf, wt_data in residuals.items():
        conf_offsets[conf] = {}
        for weight, vals in wt_data.items():
            conf_offsets[conf][weight] = sum(vals) / len(vals) if vals else 0.0

    # Normalize: subtract the weighted mean across conferences at each weight
    for weight in NCAA_WEIGHTS:
        vals_and_counts = [
            (conf_offsets[c].get(weight, 0.0),
             len(residuals[c].get(weight, [])))
            for c in conf_offsets
            if weight in residuals.get(c, {})
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
# Pass 3 — cross-conference exposure per wrestler
#
# Each cross-conference match is weighted by the absolute quality offset of
# the opposing conference — so MAC vs EIWA (both near-average) counts less
# than MAC vs Big Ten (large offset).
# ---------------------------------------------------------------------------

def compute_cross_exposure(cross_matches, conf_offsets, wrestler_wr):
    """
    Returns: wrestler_id -> n_cross_effective (float)
    """
    exposure = {}
    for wid, matches in cross_matches.items():
        eff = 0.0
        for opp_id, opp_conf, weight in matches:
            off = conf_offsets.get(opp_conf, {}).get(weight, 0.0)
            # Weight by absolute offset — conferences far from average are
            # more informative about absolute quality
            eff += min(1.0, abs(off))   # cap at 1.0 per match
        exposure[wid] = eff
    return exposure


# ---------------------------------------------------------------------------
# Pass 4 — TPAR v3
# ---------------------------------------------------------------------------

def compute_tpar_v3(all_matches, raw_avgs, raw_counts, wrestler_wr,
                    wrestler_team, team_conf, rank_maps, tier_cache,
                    conf_offsets, cross_exposure):
    """
    Recomputes per-match TPAR with conference-adjusted expected values.

    For each opponent B:
      offset     = conf_offsets[B.conf][weight]
      discount   = n_cross_eff_B / (n_cross_eff_B + K_CONF)
      conf_adj_mu = tier_mu + offset * (1 - discount)
      opp_shrunk = shrink(raw_avg_B, conf_adj_mu, n_B)
      expected   = -opp_shrunk
    """
    impact = defaultdict(list)

    for weight, matches in all_matches.items():
        rmap     = rank_maps[weight]
        t_avgs   = tier_cache[weight]
        max_rank = rmap.get("__max_rank__", 200)

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

                opp_t    = tier_cache.get(opp_weight, {})
                opp_max  = rank_maps.get(opp_weight, {}).get("__max_rank__", 200)
                mu_opp, _ = interpolate_mu(opp_rank, opp_t, opp_max)

                # Conference offset + cross-conference discount
                offset   = conf_offsets.get(opp_conf, {}).get(opp_weight, 0.0) if opp_conf else 0.0
                n_cross  = cross_exposure.get(opp_id, 0.0)
                discount = n_cross / (n_cross + K_CONF)
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
# Tournament analysis
# ---------------------------------------------------------------------------

import unicodedata, re

def normalize_name(name):
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", name.strip().lower())

def pretourney_tpar(impact_data):
    result = {}
    for wid, matches in impact_data.items():
        reg = [m["mv_impact"] for m in matches if m["date"] != NCAA_DATE]
        if reg:
            result[wid] = sum(reg) / len(reg)
    return result

def run_analysis(tpar_scores, by_id, by_name_wt, team_conf, tourney_matches, label):
    BUCKETS = ["< 0.5", "0.5–1.0", "1.0–2.0", "2.0–3.0", "3.0+"]

    def bucket(d):
        if d < 0.5: return "< 0.5"
        if d < 1.0: return "0.5–1.0"
        if d < 2.0: return "1.0–2.0"
        if d < 3.0: return "2.0–3.0"
        return "3.0+"

    tb         = defaultdict(lambda: {"total": 0, "correct": 0})
    conf_fav   = defaultdict(int)
    conf_bad   = defaultdict(int)
    total = correct = 0

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

        diff         = abs(wt_ - lt_)
        tpar_correct = wt_ >= lt_
        seed_correct = m["winner_seed"] < m["loser_seed"]
        total += 1
        if tpar_correct:
            correct += 1
        b = bucket(diff)
        tb[b]["total"] += 1
        if tpar_correct:
            tb[b]["correct"] += 1

        fav_id   = w_id if tpar_correct else l_id
        fav_conf = team_conf.get(by_id.get(fav_id, {}).get("team", ""), "?")
        conf_fav[fav_conf] += 1
        if seed_correct and not tpar_correct:
            conf_bad[fav_conf] += 1

    print(f"\n{'=' * 54}")
    print(f"  {label}")
    print(f"{'=' * 54}")
    print(f"  Overall: {correct}/{total}  ({100*correct/total:.1f}%)")
    print()
    print(f"  {'Bucket':<12} {'n':>6} {'Correct':>8} {'Acc':>7}")
    print(f"  {'-'*12} {'-'*6} {'-'*8} {'-'*7}")
    for b in BUCKETS:
        s = tb[b]
        if not s["total"]: continue
        acc = 100 * s["correct"] / s["total"]
        print(f"  {b:<12} {s['total']:>6} {s['correct']:>8} {acc:>6.1f}%{'  ◄' if b == '< 0.5' else ''}")
    print()
    print(f"  {'Conf':<12} {'Bad':>5} {'TotFav':>7} {'Rate':>7}")
    print(f"  {'-'*12} {'-'*5} {'-'*7} {'-'*7}")
    confs = sorted(conf_fav, key=lambda c: -conf_bad.get(c,0)/conf_fav[c] if conf_fav[c] else 0)
    for conf in confs:
        if not conf_fav[conf]: continue
        rate = 100 * conf_bad.get(conf, 0) / conf_fav[conf]
        print(f"  {conf:<12} {conf_bad.get(conf,0):>5} {conf_fav[conf]:>7} {rate:>6.1f}%")

    return correct / total


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 54)
    print(f"TPAR v3 — Bayesian Conference Prior  (K_CONF={K_CONF})")
    print("=" * 54)

    print("\nLoading shared data...")
    team_conf = build_team_conf()
    by_id, wrestler_team, wrestler_wr, rank_maps, tier_cache = load_shared()

    with open(f"{FRONTEND_DIR}/wrestlers/{SEASON}/index_wrestlers.json") as f:
        index = json.load(f)
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
    print(f"  {len(raw_avgs):,} wrestlers with match data")
    print(f"  {sum(len(v) for v in cross_matches.values()):,} cross-conference match appearances")

    print("Pass 2: conference quality offsets...")
    conf_offsets = compute_conf_offsets(
        all_matches, raw_avgs, raw_counts, wrestler_wr,
        wrestler_team, team_conf, rank_maps, tier_cache
    )

    # Print the offsets — unbiased, league-average-centered
    print(f"\n  Conference quality offsets (league avg = 0, per weight class):")
    print(f"  {'Conf':<12}" + "".join(f"  {w:>5}" for w in NCAA_WEIGHTS) + "   AVG")
    print("  " + "-" * (12 + 7 * len(NCAA_WEIGHTS) + 6))
    for conf in sorted(conf_offsets):
        row = f"  {conf:<12}"
        vals = []
        for w in NCAA_WEIGHTS:
            v = conf_offsets[conf].get(w)
            if v is not None:
                row  += f"  {v:>+5.2f}"
                vals.append(v)
            else:
                row  += f"  {'--':>5}"
        avg = sum(vals)/len(vals) if vals else 0
        row += f"   {avg:>+.2f}"
        print(row)

    print("\nPass 3: cross-conference exposure...")
    cross_exposure = compute_cross_exposure(cross_matches, conf_offsets, wrestler_wr)
    exposed = [v for v in cross_exposure.values() if v > 0]
    print(f"  Wrestlers with any cross-conf exposure: {len(exposed):,}")
    print(f"  Median effective cross-conf matches: {sorted(exposed)[len(exposed)//2]:.1f}")

    print("\nPass 4: computing TPAR v3...")
    match_impact_v3 = compute_tpar_v3(
        all_matches, raw_avgs, raw_counts, wrestler_wr,
        wrestler_team, team_conf, rank_maps, tier_cache,
        conf_offsets, cross_exposure
    )
    print(f"  {len(match_impact_v3):,} wrestlers with v3 impacts")

    # Save
    out_path = pathlib.Path(f"{FRONTEND_DIR}/mat_value/{SEASON}/match_mv_impact_v3_{SEASON}.json")
    with out_path.open("w") as f:
        json.dump(match_impact_v3, f)
    print(f"  Saved: {out_path}")

    # Compare
    v1_raw  = json.load(open(f"{FRONTEND_DIR}/mat_value/{SEASON}/match_mv_impact_{SEASON}.json"))
    tpar_v1 = pretourney_tpar(v1_raw)
    tpar_v3 = pretourney_tpar(match_impact_v3)

    acc_v1 = run_analysis(tpar_v1, by_id, by_name_wt, team_conf, tourney_matches, "TPAR v1  (current)")
    acc_v3 = run_analysis(tpar_v3, by_id, by_name_wt, team_conf, tourney_matches,
                          f"TPAR v3  (Bayesian conf prior, K_CONF={K_CONF})")

    delta = (acc_v3 - acc_v1) * 100
    print(f"\n  Overall delta: {'+' if delta >= 0 else ''}{delta:.1f} pp")


if __name__ == "__main__":
    main()
