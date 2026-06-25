"""
Trace the v3b calculation for a specific wrestler as opponent.
Shows exactly what conf offset is applied, how discount is computed,
how conf_adj_mu differs from v1, and the resulting impact difference.
Target: Wyatt Henson (MAC, 141) as opponent — appears repeatedly in regression list.
"""

import json, sys, glob, pathlib, unicodedata, re
from collections import defaultdict

sys.path.insert(0, "scripts/mat_value")
from compute_mat_value import (
    classify_result_type, result_to_signed, load_rankings,
    compute_tier_averages, interpolate_mu, shrink_opponent_avg,
)

SEASON       = 2026
DATA_DIR     = "mt/rankings_data/ncaa_men"
FRONTEND_DIR = "frontend/wrestledata-ui/public/data"
NCAA_DATE    = "03/21/2026"
K_SHRINK     = 20
K_CONF       = 10   # best K from v3b sweep

CONF_EVENT_MAP = {
    "Big Ten": "Big Ten", "ACC": "ACC", "Big 12": "Big 12",
    "Ivy League": "CAA", "MAC Wrestling": "MAC",
    "Southern Conference": "SoCon", "EIWA": "EIWA",
    "PAC-12": "Pac-12", "Pac-12": "Pac-12",
    "Colonial": "CAA", "CAA": "CAA", "SoCon": "SoCon",
}

TARGET_NAME = "wyatt henson"
TARGET_WT   = 141


def norm(name):
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
                if kw.lower() in m.get("event","").lower() and "championship" in m.get("event","").lower():
                    team_conf[team] = conf
                    break
    return team_conf


def main():
    with open(f"{FRONTEND_DIR}/wrestlers/{SEASON}/index_wrestlers.json") as f:
        index = json.load(f)
    by_id         = {w["wrestler_id"]: w for w in index}
    wrestler_team = {w["wrestler_id"]: w["team"] for w in index}

    team_conf = build_team_conf()

    rmap     = load_rankings(SEASON, TARGET_WT, DATA_DIR, use_cache=True, league="ncaa")
    t_avgs   = compute_tier_averages(SEASON, TARGET_WT, rmap, DATA_DIR, use_cache=True)
    max_rank = rmap.get("__max_rank__", 200)

    wrestler_wr = {}
    for w in [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]:
        rm = load_rankings(SEASON, w, DATA_DIR, use_cache=True, league="ncaa")
        for wid, rank in rm.items():
            if wid != "__max_rank__":
                wrestler_wr[wid] = (w, rank)

    # Find target wrestler
    target_id = None
    for w in index:
        if norm(w["name"]) == TARGET_NAME and int(w["weight_class"]) == TARGET_WT:
            target_id = w["wrestler_id"]
            break
    if not target_id:
        print(f"Could not find {TARGET_NAME} at {TARGET_WT}")
        return

    target_rank = rmap.get(target_id)
    target_info = by_id[target_id]
    target_conf = team_conf.get(target_info["team"], "?")
    mu_target, _ = interpolate_mu(target_rank, t_avgs, max_rank)

    print(f"Target: {target_info['name']}  ({target_info['team']}, {target_conf})  rank={target_rank}  tier_mu={mu_target:+.3f}")
    print()

    # Load all 141 matches to compute raw avg and cross-conference exposure
    matches = []
    for pat in [f"weight_class_{TARGET_WT}.json", f"weight_class_{TARGET_WT}A.json"]:
        fp = pathlib.Path(DATA_DIR) / str(SEASON) / pat
        if fp.exists():
            with fp.open() as f:
                matches.extend(json.load(f).get("matches", []))

    raw_sums   = defaultdict(float)
    raw_counts = defaultdict(int)
    cross      = defaultdict(list)

    # Need all weights for raw avgs
    all_matches_all_wt = {}
    for w in [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]:
        wms = []
        for pat in [f"weight_class_{w}.json", f"weight_class_{w}A.json"]:
            fp = pathlib.Path(DATA_DIR) / str(SEASON) / pat
            if fp.exists():
                with fp.open() as f:
                    wms.extend(json.load(f).get("matches", []))
        all_matches_all_wt[w] = wms

    for weight, wms in all_matches_all_wt.items():
        for m in wms:
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
                raw_sums[wid]   += s
                raw_counts[wid] += 1
                c1 = team_conf.get(wrestler_team.get(wid))
                c2 = team_conf.get(wrestler_team.get(opp_id))
                if c1 and c2 and c1 != c2:
                    cross[wid].append((opp_id, c2, weight))

    raw_avgs = {wid: raw_sums[wid] / raw_counts[wid] for wid in raw_counts if raw_counts[wid] > 0}

    # Conference offsets (abbreviated — paste from v3b run output)
    # We'll recompute them inline using the same logic as v3b
    # For the trace, load from v3b script directly
    sys.path.insert(0, "scripts/analysis")
    from tpar_v3b_differential import (
        compute_raw_avgs, compute_conf_offsets,
        compute_cross_exposure_v3b, compute_cross_exposure_v3,
    )

    rank_maps  = {}
    tier_cache = {}
    for w in [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]:
        rm = load_rankings(SEASON, w, DATA_DIR, use_cache=True, league="ncaa")
        rank_maps[w]  = rm
        tier_cache[w] = compute_tier_averages(SEASON, w, rm, DATA_DIR, use_cache=True)

    all_matches = all_matches_all_wt
    raw_avgs2, raw_counts2, cross_matches = compute_raw_avgs(all_matches, wrestler_team, team_conf)
    conf_offsets = compute_conf_offsets(
        all_matches, raw_avgs2, raw_counts2, wrestler_wr,
        wrestler_team, team_conf, rank_maps, tier_cache
    )
    exp_v3  = compute_cross_exposure_v3(cross_matches, conf_offsets, wrestler_wr)
    exp_v3b = compute_cross_exposure_v3b(cross_matches, conf_offsets, wrestler_team, team_conf)

    target_raw  = raw_avgs2.get(target_id, mu_target)
    target_n    = raw_counts2.get(target_id, 0)
    target_exp_v3  = exp_v3.get(target_id, 0.0)
    target_exp_v3b = exp_v3b.get(target_id, 0.0)
    mac_offset  = conf_offsets.get("MAC", {}).get(TARGET_WT, 0.0)

    disc_v3  = target_exp_v3  / (target_exp_v3  + K_CONF)
    disc_v3b = target_exp_v3b / (target_exp_v3b + K_CONF)

    conf_adj_mu_v1  = mu_target                           # no conf adjustment
    conf_adj_mu_v3  = mu_target + mac_offset * (1 - disc_v3)
    conf_adj_mu_v3b = mu_target + mac_offset * (1 - disc_v3b)

    shrunk_v1  = shrink_opponent_avg(target_raw, conf_adj_mu_v1,  target_n, k=K_SHRINK)
    shrunk_v3  = shrink_opponent_avg(target_raw, conf_adj_mu_v3,  target_n, k=K_SHRINK)
    shrunk_v3b = shrink_opponent_avg(target_raw, conf_adj_mu_v3b, target_n, k=K_SHRINK)

    print(f"{'='*65}")
    print(f"  How Wyatt Henson is valued as an OPPONENT")
    print(f"  (each row = what a wrestler's TPAR calculation uses when they face him)")
    print(f"{'='*65}")
    print(f"  Rank:                    #{target_rank}")
    print(f"  Tier mu (v1 baseline):   {mu_target:+.3f}")
    print(f"  Raw season avg:          {target_raw:+.3f}  (over {target_n} matches)")
    print(f"  MAC offset at 141:       {mac_offset:+.3f}")
    print()
    print(f"  Cross-conf exposure:")
    print(f"    v3  (|opp_offset|):    {target_exp_v3:.2f} eff matches")
    print(f"    v3b (|gap|):           {target_exp_v3b:.2f} eff matches")
    print()
    print(f"  Discount (how much we trust outside exposure to override the conf prior):")
    print(f"    v3  discount:          {disc_v3:.3f}  ({target_exp_v3:.1f} / ({target_exp_v3:.1f} + {K_CONF}))")
    print(f"    v3b discount:          {disc_v3b:.3f}  ({target_exp_v3b:.1f} / ({target_exp_v3b:.1f} + {K_CONF}))")
    print()
    print(f"  conf_adj_mu = tier_mu + offset × (1 - discount):")
    print(f"    v1:                    {conf_adj_mu_v1:+.3f}  [no conf adj]")
    print(f"    v3:  {mu_target:+.3f} + ({mac_offset:+.3f}) × {1-disc_v3:.3f}  =  {conf_adj_mu_v3:+.3f}")
    print(f"    v3b: {mu_target:+.3f} + ({mac_offset:+.3f}) × {1-disc_v3b:.3f}  =  {conf_adj_mu_v3b:+.3f}")
    print()
    print(f"  opp_shrunk = (raw × n + conf_adj_mu × {K_SHRINK}) / (n + {K_SHRINK}):")
    print(f"    v1:   ({target_raw:+.3f} × {target_n} + {conf_adj_mu_v1:+.3f} × {K_SHRINK}) / {target_n + K_SHRINK} = {shrunk_v1:+.3f}")
    print(f"    v3:   ({target_raw:+.3f} × {target_n} + {conf_adj_mu_v3:+.3f} × {K_SHRINK}) / {target_n + K_SHRINK} = {shrunk_v3:+.3f}")
    print(f"    v3b:  ({target_raw:+.3f} × {target_n} + {conf_adj_mu_v3b:+.3f} × {K_SHRINK}) / {target_n + K_SHRINK} = {shrunk_v3b:+.3f}")
    print()
    print(f"  Expected = -opp_shrunk (from the other wrestler's POV):")
    print(f"    v1:   {-shrunk_v1:+.3f}")
    print(f"    v3:   {-shrunk_v3:+.3f}")
    print(f"    v3b:  {-shrunk_v3b:+.3f}")
    print()

    # Show impact for a specific match (decision win over Henson = +3)
    print(f"  Example: wrestling Henson and winning by decision (+3 pts):")
    for label, shrunk in [("v1", shrunk_v1), ("v3", shrunk_v3), ("v3b", shrunk_v3b)]:
        impact = 3.0 - (-shrunk)
        print(f"    {label}:  impact = 3.0 - ({-shrunk:+.3f}) = {impact:+.3f}")

    # Also show his cross-conf match breakdown
    target_cross = cross_matches.get(target_id, [])
    conf_tally = defaultdict(lambda: [0, 0.0, 0.0])  # [n, v3_weight, v3b_weight]
    for opp_id, opp_conf, weight in target_cross:
        my_off  = conf_offsets.get("MAC", {}).get(weight, 0.0)
        opp_off = conf_offsets.get(opp_conf, {}).get(weight, 0.0)
        w3   = min(1.0, abs(opp_off))
        w3b  = min(1.0, abs(my_off - opp_off))
        conf_tally[opp_conf][0] += 1
        conf_tally[opp_conf][1] += w3
        conf_tally[opp_conf][2] += w3b

    print()
    print(f"  Henson's cross-conf match breakdown:")
    print(f"  {'Opp Conf':<12}  {'n':>4}  {'MAC off':>8}  {'Opp off':>8}  {'|gap|':>7}  {'v3 wt':>7}  {'v3b wt':>8}")
    print(f"  {'-'*12}  {'-'*4}  {'-'*8}  {'-'*8}  {'-'*7}  {'-'*7}  {'-'*8}")
    for opp_conf, (n, w3, w3b) in sorted(conf_tally.items(), key=lambda x: -x[1][0]):
        sample_opp_off = conf_offsets.get(opp_conf, {}).get(TARGET_WT, 0.0)
        gap = abs(mac_offset - sample_opp_off)
        print(f"  {opp_conf:<12}  {n:>4}  {mac_offset:>+8.3f}  {sample_opp_off:>+8.3f}  {gap:>7.3f}  {w3:>7.3f}  {w3b:>8.3f}")
    print(f"  {'TOTAL':<12}  {sum(v[0] for v in conf_tally.values()):>4}  {'':>8}  {'':>8}  {'':>7}  "
          f"{sum(v[1] for v in conf_tally.values()):>7.3f}  {sum(v[2] for v in conf_tally.values()):>8.3f}")


if __name__ == "__main__":
    main()
