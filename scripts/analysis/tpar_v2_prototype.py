"""
TPAR v2 Prototype — 2nd-Order Opponent Quality (Schedule Strength Adjustment)

Approach (single-pass, no circular dependency):

  Pass 1 — build global raw averages
    Load every match for every wrestler. Compute raw signed average for each.

  Pass 2 — compute SOS adjustment per wrestler
    For each wrestler B, look at each of B's opponents C.
    Compute C's deviation from their tier expectation (C_raw - C_tier_mu).
    B's SOS score = mean of those deviations.
    B's adjusted avg = B_raw + alpha * B_SOS

  Pass 3 — recompute TPAR using adjusted opponent quality
    Same formula as v1 but substitute adjusted avg for raw avg in the
    shrinkage step before computing expected value.

Output:
    frontend/wrestledata-ui/public/data/mat_value/2026/match_mv_impact_v2_2026.json
    (parallel structure to match_mv_impact_2026.json — drop-in for analysis)

Does NOT modify any existing files or the main TPAR pipeline.
"""

import json
import sys
import glob
from collections import defaultdict
from pathlib import Path
from typing import Dict, Tuple, Optional

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

SEASON      = 2026
DATA_DIR    = "mt/rankings_data/ncaa_men"
FRONTEND_DIR = "frontend/wrestledata-ui/public/data"
NCAA_WEIGHTS = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]
ALPHA       = 0.5   # SOS adjustment weight; 0 = v1 behaviour, 1 = full 2nd-order
K_SHRINK    = 20    # same as v1

NCAA_EVENT       = "2026 NCAA Division I Championships"
NCAA_DATE_IMPACT = "03/21/2026"


# ---------------------------------------------------------------------------
# Pass 1 — global raw averages and match graph
# ---------------------------------------------------------------------------

def build_global_match_graph() -> Tuple[Dict, Dict, Dict]:
    """
    Returns:
        raw_avgs:    wrestler_id -> float (raw signed avg across all matches)
        n_matches:   wrestler_id -> int
        opp_graph:   wrestler_id -> list of opponent_ids they faced
    """
    signed_totals: Dict[str, float] = defaultdict(float)
    match_counts:  Dict[str, int]   = defaultdict(int)
    opp_graph:     Dict[str, list]  = defaultdict(list)

    data_path = Path(DATA_DIR) / str(SEASON)

    for weight in NCAA_WEIGHTS:
        for pattern in [f"weight_class_{weight}.json", f"weight_class_{weight}A.json"]:
            wc_file = data_path / pattern
            if not wc_file.exists():
                continue
            with wc_file.open() as f:
                wc_data = json.load(f)

            for match in wc_data.get("matches", []):
                result = match.get("result", "")
                if "MFF" in result.upper() or "FORFEIT" in result.upper():
                    continue

                w1 = match.get("wrestler1_id")
                w2 = match.get("wrestler2_id")
                winner = match.get("winner_id")
                if not w1 or not w2:
                    continue

                result_type = classify_result_type(result)

                for wrestler_id, is_w1 in [(w1, True), (w2, False)]:
                    is_winner = (winner == wrestler_id)
                    signed = result_to_signed(result_type, is_winner)
                    if signed is None:
                        continue
                    signed_totals[wrestler_id] += signed
                    match_counts[wrestler_id]  += 1
                    opp_id = w2 if is_w1 else w1
                    opp_graph[wrestler_id].append(opp_id)

    raw_avgs = {
        wid: signed_totals[wid] / match_counts[wid]
        for wid in match_counts
        if match_counts[wid] > 0
    }

    return raw_avgs, dict(match_counts), dict(opp_graph)


# ---------------------------------------------------------------------------
# Pass 2 — SOS adjustments
# ---------------------------------------------------------------------------

def build_sos_adjustments(
    raw_avgs:   Dict[str, float],
    n_matches:  Dict[str, int],
    opp_graph:  Dict[str, list],
    rank_maps:  Dict[int, dict],
    tier_avgs:  Dict[int, dict],
) -> Dict[str, float]:
    """
    For each wrestler B, compute their schedule-strength deviation:
        SOS_B = mean over C in B's opponents of (raw_avg_C - tier_mu_C)

    Returns wrestler_id -> SOS score (positive = faced harder-than-expected opponents).
    """
    sos: Dict[str, float] = {}

    # Build a wrestler -> (weight, rank) lookup from all rank maps
    wrestler_weight_rank: Dict[str, Tuple[int, int]] = {}
    for weight, rmap in rank_maps.items():
        max_rank = rmap.get("__max_rank__", 200)
        for wid, rank in rmap.items():
            if wid == "__max_rank__":
                continue
            wrestler_weight_rank[wid] = (weight, rank)

    for b_id, opponents in opp_graph.items():
        if not opponents:
            continue

        deviations = []
        for c_id in opponents:
            c_raw = raw_avgs.get(c_id)
            if c_raw is None:
                continue
            c_wr = wrestler_weight_rank.get(c_id)
            if c_wr is None:
                continue
            c_weight, c_rank = c_wr
            c_tier = tier_avgs.get(c_weight, {})
            c_max_rank = rank_maps[c_weight].get("__max_rank__", 200)
            mu_c, _ = interpolate_mu(c_rank, c_tier, c_max_rank)
            deviations.append(c_raw - mu_c)

        if deviations:
            sos[b_id] = sum(deviations) / len(deviations)

    return sos


# ---------------------------------------------------------------------------
# Pass 3 — recompute TPAR v2
# ---------------------------------------------------------------------------

def compute_tpar_v2(
    raw_avgs:   Dict[str, float],
    n_matches:  Dict[str, int],
    sos:        Dict[str, float],
    rank_maps:  Dict[int, dict],
    tier_avgs:  Dict[int, dict],
) -> Dict[str, list]:
    """
    For every wrestler A, for every pre-tournament match, compute v2 mv_impact.
    Returns match_impact_v2: wrestler_id -> list of {wrestler_id, opponent_id,
                                                      date, result, mv_impact}
    """
    data_path = Path(DATA_DIR) / str(SEASON)
    match_impact_v2: Dict[str, list] = defaultdict(list)

    # Wrestler -> (weight, rank)
    wrestler_weight_rank: Dict[str, Tuple[int, int]] = {}
    for weight, rmap in rank_maps.items():
        for wid, rank in rmap.items():
            if wid == "__max_rank__":
                continue
            wrestler_weight_rank[wid] = (weight, rank)

    for weight in NCAA_WEIGHTS:
        for pattern in [f"weight_class_{weight}.json", f"weight_class_{weight}A.json"]:
            wc_file = data_path / pattern
            if not wc_file.exists():
                continue
            with wc_file.open() as f:
                wc_data = json.load(f)

            rmap     = rank_maps[weight]
            t_avgs   = tier_avgs[weight]
            max_rank = rmap.get("__max_rank__", 200)

            for match in wc_data.get("matches", []):
                result = match.get("result", "")
                date   = match.get("date", "")
                if "MFF" in result.upper() or "FORFEIT" in result.upper():
                    continue

                w1     = match.get("wrestler1_id")
                w2     = match.get("wrestler2_id")
                winner = match.get("winner_id")
                if not w1 or not w2:
                    continue

                result_type = classify_result_type(result)

                for wrestler_id, opp_id in [(w1, w2), (w2, w1)]:
                    is_winner = (winner == wrestler_id)
                    result_signed = result_to_signed(result_type, is_winner)
                    if result_signed is None:
                        continue

                    # Opponent's weight and rank
                    opp_wr = wrestler_weight_rank.get(opp_id)
                    if opp_wr is None:
                        continue
                    opp_weight, opp_rank = opp_wr

                    opp_tier  = tier_avgs.get(opp_weight, {})
                    opp_rmap  = rank_maps.get(opp_weight, {})
                    opp_max   = opp_rmap.get("__max_rank__", 200)

                    mu_opp, _ = interpolate_mu(opp_rank, opp_tier, opp_max)

                    # v2: adjust opponent raw avg by their SOS
                    opp_raw = raw_avgs.get(opp_id, mu_opp)
                    opp_sos = sos.get(opp_id, 0.0)
                    opp_n   = n_matches.get(opp_id, 0)

                    opp_adjusted = opp_raw + ALPHA * opp_sos
                    opp_shrunk   = shrink_opponent_avg(opp_adjusted, mu_opp, opp_n, k=K_SHRINK)

                    expected_v2  = -opp_shrunk
                    mv2          = result_signed - expected_v2

                    match_impact_v2[wrestler_id].append({
                        "wrestler_id": wrestler_id,
                        "opponent_id": opp_id,
                        "date":        date,
                        "result":      result,
                        "mv_impact":   round(mv2, 2),
                    })

    return dict(match_impact_v2)


# ---------------------------------------------------------------------------
# Tournament analysis (shared between v1 and v2)
# ---------------------------------------------------------------------------

import unicodedata, re
from collections import defaultdict

CONF_EVENT_MAP = {
    "Big Ten": "Big Ten", "ACC": "ACC", "Big 12": "Big 12",
    "Ivy League": "Ivy League", "MAC Wrestling": "MAC",
    "Southern Conference": "SoCon", "EIWA": "EIWA",
    "PAC-12": "Pac-12", "Pac-12": "Pac-12",
    "Colonial": "CAA", "CAA": "CAA", "Patriot": "Patriot", "SoCon": "SoCon",
}

def normalize_name(name):
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", name.strip().lower())

def load_analysis_data():
    with open(f"{FRONTEND_DIR}/wrestlers/{SEASON}/index_wrestlers.json") as f:
        index = json.load(f)
    by_id         = {w["wrestler_id"]: w for w in index}
    by_name_wt    = {(normalize_name(w["name"]), int(w["weight_class"])): w["wrestler_id"] for w in index}

    team_conf = {}
    for fpath in glob.glob(f"{FRONTEND_DIR}/wrestlers/{SEASON}/by_id/*.json"):
        with open(fpath) as f:
            d = json.load(f)
        team = d.get("team")
        if not team:
            continue
        for m in d.get("match_list", []):
            event = m.get("event", "")
            for kw, conf in CONF_EVENT_MAP.items():
                if kw.lower() in event.lower() and "championship" in event.lower():
                    team_conf[team] = conf
                    break

    with open("data/2026/ncaa-tourney/parsed/matches.json") as f:
        tourney_matches = json.load(f)

    return by_id, by_name_wt, team_conf, tourney_matches


def pretourney_tpar(impact_data: Dict[str, list]) -> Dict[str, float]:
    result = {}
    for wid, matches in impact_data.items():
        reg = [m["mv_impact"] for m in matches if m["date"] != NCAA_DATE_IMPACT]
        if reg:
            result[wid] = sum(reg) / len(reg)
    return result


def run_tournament_analysis(tpar_scores, by_id, by_name_wt, team_conf, tourney_matches, label):
    TPAR_BUCKETS  = ["< 0.5", "0.5–1.0", "1.0–2.0", "2.0–3.0", "3.0+"]
    SEED_CONF_ORDER = ["Big Ten", "Big 12", "ACC", "MAC", "EIWA", "CAA", "Pac-12", "SoCon"]

    def tpar_bucket(diff):
        if diff < 0.5:   return "< 0.5"
        if diff < 1.0:   return "0.5–1.0"
        if diff < 2.0:   return "1.0–2.0"
        if diff < 3.0:   return "2.0–3.0"
        return "3.0+"

    tb = defaultdict(lambda: {"total": 0, "correct": 0})
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

        diff          = abs(wt_ - lt_)
        tpar_correct  = wt_ >= lt_
        seed_correct  = m["winner_seed"] < m["loser_seed"]

        total += 1
        if tpar_correct:
            correct += 1
        b = tpar_bucket(diff)
        tb[b]["total"] += 1
        if tpar_correct:
            tb[b]["correct"] += 1

        fav_id   = w_id if tpar_correct else l_id
        fav_info = by_id.get(fav_id, {})
        fav_conf = team_conf.get(fav_info.get("team", ""), "?")
        conf_fav[fav_conf] += 1
        if seed_correct and not tpar_correct:
            conf_bad[fav_conf] += 1

    print(f"\n{'=' * 56}")
    print(f"  {label}")
    print(f"{'=' * 56}")
    print(f"  Overall: {correct}/{total}  ({100*correct/total:.1f}%)")
    print()
    print(f"  {'Bucket':<12} {'Matches':>8} {'Correct':>8} {'Acc':>7}")
    print(f"  {'-'*12} {'-'*8} {'-'*8} {'-'*7}")
    for b in TPAR_BUCKETS:
        s = tb[b]
        if not s["total"]: continue
        acc = 100 * s["correct"] / s["total"]
        marker = " ◄" if b == "< 0.5" else ""
        print(f"  {b:<12} {s['total']:>8} {s['correct']:>8} {acc:>6.1f}%{marker}")
    print()
    print(f"  {'Conf':<12} {'Bad':>5} {'TotFav':>7} {'Rate':>7}")
    print(f"  {'-'*12} {'-'*5} {'-'*7} {'-'*7}")
    confs = sorted(conf_fav.keys(), key=lambda c: -conf_bad.get(c,0)/conf_fav[c] if conf_fav[c] else 0)
    for conf in confs:
        if not conf_fav[conf]: continue
        rate = 100 * conf_bad.get(conf, 0) / conf_fav[conf]
        print(f"  {conf:<12} {conf_bad.get(conf,0):>5} {conf_fav[conf]:>7} {rate:>6.1f}%")

    return correct / total


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 56)
    print(f"TPAR v2 Prototype  (alpha={ALPHA})")
    print("=" * 56)

    # ---- Pass 1 ----
    print("\nPass 1: building global match graph...")
    raw_avgs, n_matches, opp_graph = build_global_match_graph()
    print(f"  Wrestlers with match data: {len(raw_avgs):,}")

    # ---- Load shared lookups ----
    print("Loading rankings and tier averages...")
    rank_maps = {}
    tier_avgs_map = {}
    for w in NCAA_WEIGHTS:
        rmap = load_rankings(SEASON, w, DATA_DIR, use_cache=True, league="ncaa")
        rank_maps[w]     = rmap
        tier_avgs_map[w] = compute_tier_averages(SEASON, w, rmap, DATA_DIR, use_cache=True)

    # ---- Pass 2 ----
    print("Pass 2: computing SOS adjustments...")
    sos = build_sos_adjustments(raw_avgs, n_matches, opp_graph, rank_maps, tier_avgs_map)
    sos_vals = list(sos.values())
    print(f"  Wrestlers with SOS data: {len(sos):,}")
    print(f"  SOS range: {min(sos_vals):.3f} to {max(sos_vals):.3f}  (mean {sum(sos_vals)/len(sos_vals):.3f})")

    # ---- Pass 3 ----
    print("Pass 3: computing TPAR v2...")
    match_impact_v2 = compute_tpar_v2(raw_avgs, n_matches, sos, rank_maps, tier_avgs_map)
    print(f"  Wrestlers with v2 impacts: {len(match_impact_v2):,}")

    # ---- Save output ----
    out_path = Path(f"{FRONTEND_DIR}/mat_value/{SEASON}/match_mv_impact_v2_{SEASON}.json")
    with out_path.open("w") as f:
        json.dump(match_impact_v2, f)
    print(f"  Saved: {out_path}")

    # ---- Tournament comparison ----
    print("\nLoading analysis data...")
    by_id, by_name_wt, team_conf, tourney_matches = load_analysis_data()

    v1_impacts = json.load(open(f"{FRONTEND_DIR}/mat_value/{SEASON}/match_mv_impact_{SEASON}.json"))
    tpar_v1 = pretourney_tpar(v1_impacts)
    tpar_v2 = pretourney_tpar(match_impact_v2)

    acc_v1 = run_tournament_analysis(tpar_v1, by_id, by_name_wt, team_conf, tourney_matches,
                                     "TPAR v1  (current)")
    acc_v2 = run_tournament_analysis(tpar_v2, by_id, by_name_wt, team_conf, tourney_matches,
                                     f"TPAR v2  (2nd-order, alpha={ALPHA})")

    delta = (acc_v2 - acc_v1) * 100
    sign  = "+" if delta >= 0 else ""
    print(f"\n  Overall delta: {sign}{delta:.1f} percentage points")

    # ---- SOS sanity check: biggest adjustments ----
    print("\n--- Top 10 most upward-adjusted opponents (SOS helped them) ---")
    top_up = sorted(sos.items(), key=lambda x: -x[1])[:10]
    for wid, s in top_up:
        info = by_id.get(wid, {})
        print(f"  {info.get('name','?'):<28} {info.get('team','?'):<22} SOS: {s:+.3f}")

    print("\n--- Top 10 most downward-adjusted opponents (SOS hurt them) ---")
    top_dn = sorted(sos.items(), key=lambda x: x[1])[:10]
    for wid, s in top_dn:
        info = by_id.get(wid, {})
        print(f"  {info.get('name','?'):<28} {info.get('team','?'):<22} SOS: {s:+.3f}")


if __name__ == "__main__":
    main()
