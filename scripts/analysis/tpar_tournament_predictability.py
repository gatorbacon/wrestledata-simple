"""
Analyzes how well pre-tournament TPAR predicted NCAA tournament match outcomes.

Steps:
1. Load per-match TPAR impacts; exclude tournament day to get pre-tourney TPAR per wrestler
2. Extract all NCAA tournament matchups from wrestler profiles
3. For each matchup, compare pre-tourney TPAR to actual result
4. Report: overall accuracy, accuracy by TPAR differential, accuracy by weight class
"""

import json
import glob
from collections import defaultdict

DATA_DIR = "frontend/wrestledata-ui/public/data"
SEASON = 2026
NCAA_EVENT = "2026 NCAA Division I Championships"
NCAA_DATE_BY_ID = "2026-03-21"     # format in by_id wrestler files
NCAA_DATE_IMPACT = "03/21/2026"    # format in match_mv_impact file


def load_pretourney_tpar():
    """
    Returns dict: wrestler_id -> pre-tournament TPAR avg
    Only includes wrestlers with at least 1 pre-tourney match.
    """
    impact_path = f"{DATA_DIR}/mat_value/{SEASON}/match_mv_impact_{SEASON}.json"
    with open(impact_path) as f:
        impact_data = json.load(f)

    pretourney = {}
    for wrestler_id, matches in impact_data.items():
        regular = [m["mv_impact"] for m in matches if m["date"] != NCAA_DATE_IMPACT]
        if regular:
            pretourney[wrestler_id] = round(sum(regular) / len(regular), 3)
    return pretourney


def load_wrestler_index():
    """Returns dict: wrestler_id -> {name, team, weight_class}"""
    index_path = f"{DATA_DIR}/wrestlers/{SEASON}/index_wrestlers.json"
    with open(index_path) as f:
        index = json.load(f)
    return {w["wrestler_id"]: w for w in index}


def load_tournament_matches():
    """
    Returns list of dicts, one per unique matchup (deduped):
    {winner_id, loser_id, weight_class, result, method}
    """
    by_id_dir = f"{DATA_DIR}/wrestlers/{SEASON}/by_id/*.json"
    seen = set()
    matchups = []

    for fpath in glob.glob(by_id_dir):
        with open(fpath) as f:
            d = json.load(f)

        wrestler_id = d["wrestler_id"]
        weight_class = d["weight_class"]

        for m in d.get("match_list", []):
            if m.get("event") != NCAA_EVENT:
                continue

            opp_id = m.get("opponent_id")
            result = m.get("result")  # "W" or "L"
            method = m.get("method", "")
            score = m.get("score", "")

            if not opp_id or not result:
                continue
            if method == "MFF":
                continue

            # Deduplicate: store canonical pair as (min_id, max_id)
            pair = (min(wrestler_id, opp_id), max(wrestler_id, opp_id))
            if pair in seen:
                continue
            seen.add(pair)

            if result == "W":
                winner_id, loser_id = wrestler_id, opp_id
            else:
                winner_id, loser_id = opp_id, wrestler_id

            matchups.append({
                "winner_id": winner_id,
                "loser_id": loser_id,
                "weight_class": weight_class,
                "method": method,
                "score": score,
            })

    return matchups


def classify_method(method):
    """Broad result type for display."""
    m = method.upper()
    if "FALL" in m or "PIN" in m:
        return "fall"
    if "TF" in m or "TECH" in m:
        return "tech"
    if "MD" in m or "MAJ" in m:
        return "major"
    if "INJ" in m:
        return "inj"
    return "dec"


def differential_bucket(diff):
    if diff < 0.5:
        return "< 0.5"
    elif diff < 1.0:
        return "0.5–1.0"
    elif diff < 2.0:
        return "1.0–2.0"
    elif diff < 3.0:
        return "2.0–3.0"
    else:
        return "3.0+"


def run():
    print("Loading data...")
    pretourney = load_pretourney_tpar()
    wrestler_index = load_wrestler_index()
    matchups = load_tournament_matches()

    print(f"  Pre-tourney TPAR computed for {len(pretourney):,} wrestlers")
    print(f"  NCAA tournament matchups found: {len(matchups)}")
    print()

    # -------------------------------------------------------------------
    # Evaluate each matchup
    # -------------------------------------------------------------------
    results = []
    skipped = 0

    for m in matchups:
        wid = m["winner_id"]
        lid = m["loser_id"]

        w_tpar = pretourney.get(wid)
        l_tpar = pretourney.get(lid)

        if w_tpar is None or l_tpar is None:
            skipped += 1
            continue

        diff = abs(w_tpar - l_tpar)
        tpar_predicted_winner = wid if w_tpar >= l_tpar else lid
        correct = tpar_predicted_winner == wid  # wid is actual winner

        results.append({
            **m,
            "winner_tpar": w_tpar,
            "loser_tpar": l_tpar,
            "tpar_diff": round(diff, 3),
            "tpar_correct": correct,
            "bucket": differential_bucket(diff),
        })

    print(f"Matchups evaluated: {len(results)}  |  Skipped (missing TPAR): {skipped}")
    print()

    # -------------------------------------------------------------------
    # 1. Overall accuracy
    # -------------------------------------------------------------------
    total = len(results)
    correct = sum(1 for r in results if r["tpar_correct"])
    ties = sum(1 for r in results if r["tpar_diff"] == 0)
    print("=" * 60)
    print("OVERALL PREDICTION ACCURACY")
    print("=" * 60)
    print(f"  Correct:  {correct} / {total}  ({100*correct/total:.1f}%)")
    print(f"  Incorrect:{total - correct} / {total}  ({100*(total-correct)/total:.1f}%)")
    if ties:
        print(f"  Exact ties (TPAR equal): {ties}  (counted as correct above)")
    print()

    # -------------------------------------------------------------------
    # 2. Accuracy by TPAR differential bucket
    # -------------------------------------------------------------------
    bucket_order = ["< 0.5", "0.5–1.0", "1.0–2.0", "2.0–3.0", "3.0+"]
    bucket_stats = defaultdict(lambda: {"total": 0, "correct": 0})

    for r in results:
        b = r["bucket"]
        bucket_stats[b]["total"] += 1
        if r["tpar_correct"]:
            bucket_stats[b]["correct"] += 1

    print("=" * 60)
    print("ACCURACY BY PRE-TOURNEY TPAR DIFFERENTIAL")
    print("=" * 60)
    print(f"  {'Diff Bucket':<12}  {'Matches':>8}  {'Correct':>8}  {'Accuracy':>9}")
    print(f"  {'-'*12}  {'-'*8}  {'-'*8}  {'-'*9}")
    for b in bucket_order:
        s = bucket_stats[b]
        if s["total"] == 0:
            continue
        acc = 100 * s["correct"] / s["total"]
        print(f"  {b:<12}  {s['total']:>8}  {s['correct']:>8}  {acc:>8.1f}%")
    print()

    # -------------------------------------------------------------------
    # 3. Accuracy by weight class
    # -------------------------------------------------------------------
    weight_stats = defaultdict(lambda: {"total": 0, "correct": 0})

    for r in results:
        wc = r["weight_class"]
        weight_stats[wc]["total"] += 1
        if r["tpar_correct"]:
            weight_stats[wc]["correct"] += 1

    print("=" * 60)
    print("ACCURACY BY WEIGHT CLASS")
    print("=" * 60)
    print(f"  {'Weight':>7}  {'Matches':>8}  {'Correct':>8}  {'Accuracy':>9}")
    print(f"  {'-'*7}  {'-'*8}  {'-'*8}  {'-'*9}")
    for wc in sorted(weight_stats.keys()):
        s = weight_stats[wc]
        acc = 100 * s["correct"] / s["total"]
        print(f"  {wc:>7}  {s['total']:>8}  {s['correct']:>8}  {acc:>8.1f}%")
    print()

    # -------------------------------------------------------------------
    # 4. Biggest upsets (high TPAR diff, TPAR was wrong)
    # -------------------------------------------------------------------
    upsets = [r for r in results if not r["tpar_correct"]]
    upsets.sort(key=lambda x: -x["tpar_diff"])

    print("=" * 60)
    print("BIGGEST TPAR UPSETS (top 15)")
    print("=" * 60)
    for r in upsets[:15]:
        wi = wrestler_index.get(r["winner_id"], {})
        li = wrestler_index.get(r["loser_id"], {})
        w_name = wi.get("name", r["winner_id"])
        w_team = wi.get("team", "?")
        l_name = li.get("name", r["loser_id"])
        l_team = li.get("team", "?")
        method_str = f"{r['method']} {r['score']}".strip()
        print(f"  TPAR diff: {r['tpar_diff']:+.2f} | {w_name} ({w_team}, TPAR {r['winner_tpar']:+.2f})")
        print(f"             def. {l_name} ({l_team}, TPAR {r['loser_tpar']:+.2f}) via {method_str}")
        print()


if __name__ == "__main__":
    run()
