"""
Quick test: does adding finer tier anchors in the 50-100 range improve
TPAR tournament predictability?

Current anchors:  [1, 10, 30, 50, 100, 150, 200]
Test anchors:     [1, 10, 30, 50, 65, 80, 100, 150, 200]

Approach: monkey-patch the anchor lists, recompute TPAR, compare.
Does NOT write any files or touch the main pipeline.
"""

import json
import sys
import glob
import unicodedata
import re
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, "scripts/mat_value")
import compute_mat_value
from compute_mat_value import (
    classify_result_type, result_to_signed,
    load_rankings, shrink_opponent_avg,
)

SEASON       = 2026
DATA_DIR     = "mt/rankings_data/ncaa_men"
FRONTEND_DIR = "frontend/wrestledata-ui/public/data"
NCAA_WEIGHTS = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]
NCAA_EVENT   = "2026 NCAA Division I Championships"
NCAA_DATE    = "03/21/2026"

ANCHORS_V1 = [1, 10, 30, 50, 100, 150, 200]
ANCHORS_V2 = [1, 10, 30, 50, 65, 80, 100, 150, 200]

CONF_EVENT_MAP = {
    "Big Ten": "Big Ten", "ACC": "ACC", "Big 12": "Big 12",
    "Ivy League": "Ivy League", "MAC Wrestling": "MAC",
    "Southern Conference": "SoCon", "EIWA": "EIWA",
    "PAC-12": "Pac-12", "Pac-12": "Pac-12",
    "Colonial": "CAA", "CAA": "CAA", "SoCon": "SoCon",
}


def normalize_name(name):
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", name.strip().lower())


def compute_tier_avgs_custom(season, weight, rank_map, data_dir, anchors):
    """Replicates compute_tier_averages with custom anchor points."""
    full_anchors = list(anchors)
    max_rank = rank_map.get("__max_rank__", 200)
    if full_anchors[-1] < max_rank:
        full_anchors.append(max_rank)

    data_path = Path(data_dir) / str(season)
    all_matches = []
    for pattern in [f"weight_class_{weight}.json", f"weight_class_{weight}A.json"]:
        wc_file = data_path / pattern
        if wc_file.exists():
            with wc_file.open() as f:
                all_matches.extend(json.load(f).get("matches", []))

    tier_avgs = {}
    for i in range(len(full_anchors) - 1):
        start, end = full_anchors[i], full_anchors[i + 1]
        tier_ids = {wid for wid, rank in rank_map.items()
                    if wid != "__max_rank__" and start <= rank <= end}
        results = []
        for match in all_matches:
            result = match.get("result", "")
            if "MFF" in result.upper() or "FORFEIT" in result.upper():
                continue
            for wid in [match.get("wrestler1_id"), match.get("wrestler2_id")]:
                if wid in tier_ids:
                    is_winner = match.get("winner_id") == wid
                    rt = classify_result_type(result)
                    s = result_to_signed(rt, is_winner)
                    if s is not None:
                        results.append(s)
        tier_avgs[(start, end)] = sum(results) / len(results) if results else 0.0

    return tier_avgs, full_anchors


def interpolate_mu_custom(rank, tier_avgs, anchors):
    for i in range(len(anchors) - 1):
        a, b = anchors[i], anchors[i + 1]
        if a <= rank <= b:
            mu_a = tier_avgs.get((a, b), 0.0)
            if i + 1 < len(anchors) - 1:
                nb = anchors[i + 2]
                mu_b = tier_avgs.get((b, nb), 0.0)
            else:
                mu_b = mu_a
            return mu_a + (rank - a) / (b - a) * (mu_b - mu_a) if b > a else mu_a
    return 0.0


def compute_tpar_with_anchors(anchors, label):
    """Full TPAR recompute using custom tier anchors. Returns pretourney dict."""
    data_path = Path(DATA_DIR) / str(SEASON)

    # Build wrestler -> (weight, rank) from rank maps
    rank_maps  = {}
    tier_cache = {}
    anchor_cache = {}
    wrestler_wr = {}

    for w in NCAA_WEIGHTS:
        rmap = load_rankings(SEASON, w, DATA_DIR, use_cache=True, league="ncaa")
        rank_maps[w] = rmap
        t, anch = compute_tier_avgs_custom(SEASON, w, rmap, DATA_DIR, anchors)
        tier_cache[w]   = t
        anchor_cache[w] = anch
        for wid, rank in rmap.items():
            if wid != "__max_rank__":
                wrestler_wr[wid] = (w, rank)

    # Compute raw averages (needed for shrinkage)
    raw_sums   = defaultdict(float)
    raw_counts = defaultdict(int)
    for w in NCAA_WEIGHTS:
        for pattern in [f"weight_class_{w}.json", f"weight_class_{w}A.json"]:
            wc_file = data_path / pattern
            if not wc_file.exists():
                continue
            with wc_file.open() as f:
                matches = json.load(f).get("matches", [])
            for match in matches:
                result = match.get("result", "")
                if "MFF" in result.upper() or "FORFEIT" in result.upper():
                    continue
                rt = classify_result_type(result)
                for wid in [match.get("wrestler1_id"), match.get("wrestler2_id")]:
                    if wid:
                        is_winner = match.get("winner_id") == wid
                        s = result_to_signed(rt, is_winner)
                        if s is not None:
                            raw_sums[wid]   += s
                            raw_counts[wid] += 1

    raw_avgs = {wid: raw_sums[wid] / raw_counts[wid]
                for wid in raw_counts if raw_counts[wid] > 0}

    # Per-match TPAR
    impact: dict = defaultdict(list)

    for w in NCAA_WEIGHTS:
        for pattern in [f"weight_class_{w}.json", f"weight_class_{w}A.json"]:
            wc_file = data_path / pattern
            if not wc_file.exists():
                continue
            with wc_file.open() as f:
                matches = json.load(f).get("matches", [])

            for match in matches:
                result = match.get("result", "")
                date   = match.get("date", "")
                if "MFF" in result.upper() or "FORFEIT" in result.upper():
                    continue
                w1     = match.get("wrestler1_id")
                w2     = match.get("wrestler2_id")
                winner = match.get("winner_id")
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
                    ow, orank = opp_wr
                    mu = interpolate_mu_custom(orank, tier_cache[ow], anchor_cache[ow])
                    opp_raw = raw_avgs.get(opp_id, mu)
                    opp_n   = raw_counts.get(opp_id, 0)
                    shrunk  = shrink_opponent_avg(opp_raw, mu, opp_n)
                    mv      = rs - (-shrunk)
                    impact[wrestler_id].append({
                        "date": date, "mv_impact": mv, "opponent_id": opp_id
                    })

    # Pre-tournament averages
    pretourney = {}
    for wid, ms in impact.items():
        reg = [m["mv_impact"] for m in ms if m["date"] != NCAA_DATE]
        if reg:
            pretourney[wid] = sum(reg) / len(reg)

    return pretourney


def run_analysis(tpar_scores, by_id, by_name_wt, team_conf, tourney_matches, label):
    TPAR_BUCKETS = ["< 0.5", "0.5–1.0", "1.0–2.0", "2.0–3.0", "3.0+"]

    def bucket(diff):
        if diff < 0.5:  return "< 0.5"
        if diff < 1.0:  return "0.5–1.0"
        if diff < 2.0:  return "1.0–2.0"
        if diff < 3.0:  return "2.0–3.0"
        return "3.0+"

    tb = defaultdict(lambda: {"total": 0, "correct": 0})
    conf_fav = defaultdict(int)
    conf_bad = defaultdict(int)
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
        tb[b]["total"]   += 1
        if tpar_correct:
            tb[b]["correct"] += 1

        fav_id   = w_id if tpar_correct else l_id
        fav_conf = team_conf.get(by_id.get(fav_id, {}).get("team", ""), "?")
        conf_fav[fav_conf] += 1
        if seed_correct and not tpar_correct:
            conf_bad[fav_conf] += 1

    print(f"\n{'=' * 52}")
    print(f"  {label}")
    print(f"{'=' * 52}")
    print(f"  Overall: {correct}/{total}  ({100*correct/total:.1f}%)")
    print()
    print(f"  {'Bucket':<12} {'n':>6} {'Correct':>8} {'Acc':>7}")
    print(f"  {'-'*12} {'-'*6} {'-'*8} {'-'*7}")
    for b in TPAR_BUCKETS:
        s = tb[b]
        if not s["total"]: continue
        acc = 100 * s["correct"] / s["total"]
        marker = " ◄" if b == "< 0.5" else ""
        print(f"  {b:<12} {s['total']:>6} {s['correct']:>8} {acc:>6.1f}%{marker}")

    print()
    print(f"  {'Conf':<12} {'Bad':>5} {'Total':>7} {'Rate':>7}")
    print(f"  {'-'*12} {'-'*5} {'-'*7} {'-'*7}")
    confs = sorted(conf_fav, key=lambda c: -conf_bad.get(c,0)/conf_fav[c] if conf_fav[c] else 0)
    for conf in confs:
        if not conf_fav[conf]: continue
        rate = 100 * conf_bad.get(conf, 0) / conf_fav[conf]
        print(f"  {conf:<12} {conf_bad.get(conf,0):>5} {conf_fav[conf]:>7} {rate:>6.1f}%")

    return correct / total


def main():
    # Load shared data
    with open(f"{FRONTEND_DIR}/wrestlers/{SEASON}/index_wrestlers.json") as f:
        index = json.load(f)
    by_id      = {w["wrestler_id"]: w for w in index}
    by_name_wt = {(normalize_name(w["name"]), int(w["weight_class"])): w["wrestler_id"] for w in index}

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

    with open("data/2026/ncaa-tourney/parsed/matches.json") as f:
        tourney_matches = json.load(f)

    print("Computing TPAR with current anchors    [1,10,30,50,100,150,200]...")
    tpar_v1 = compute_tpar_with_anchors(ANCHORS_V1, "v1")

    print("Computing TPAR with finer anchors      [1,10,30,50,65,80,100,150,200]...")
    tpar_v2 = compute_tpar_with_anchors(ANCHORS_V2, "v2")

    acc_v1 = run_analysis(tpar_v1, by_id, by_name_wt, team_conf, tourney_matches,
                          "Current anchors  [1,10,30,50,100,150,200]")
    acc_v2 = run_analysis(tpar_v2, by_id, by_name_wt, team_conf, tourney_matches,
                          "Finer anchors    [1,10,30,50,65,80,100,150,200]")

    delta = (acc_v2 - acc_v1) * 100
    print(f"\n  Overall delta: {'+' if delta >= 0 else ''}{delta:.1f} pp  — {'negligible' if abs(delta) < 0.5 else 'meaningful'}")


if __name__ == "__main__":
    main()
