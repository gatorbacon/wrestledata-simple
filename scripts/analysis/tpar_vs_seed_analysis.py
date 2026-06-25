"""
Compares TPAR vs seeding as predictors of NCAA tournament outcomes.
Also investigates why TPAR differential < 0.5 is below 50% accuracy.
"""

import json
import glob
from collections import defaultdict
import unicodedata
import re

DATA_DIR = "frontend/wrestledata-ui/public/data"
SEASON = 2026
NCAA_EVENT = "2026 NCAA Division I Championships"
NCAA_DATE_IMPACT = "03/21/2026"
EXCLUDE_RESULT_TYPES = {"Forfeit", "MFF"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_name(name):
    """Lowercase, strip accents, collapse whitespace."""
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", name.strip().lower())


def load_pretourney_tpar():
    impact_path = f"{DATA_DIR}/mat_value/{SEASON}/match_mv_impact_{SEASON}.json"
    with open(impact_path) as f:
        impact_data = json.load(f)
    pretourney = {}
    for wrestler_id, matches in impact_data.items():
        regular = [m["mv_impact"] for m in matches if m["date"] != NCAA_DATE_IMPACT]
        if regular:
            pretourney[wrestler_id] = sum(regular) / len(regular)
    return pretourney


def load_wrestler_index():
    index_path = f"{DATA_DIR}/wrestlers/{SEASON}/index_wrestlers.json"
    with open(index_path) as f:
        index = json.load(f)
    # build both id->info and (norm_name, weight)->id
    by_id = {w["wrestler_id"]: w for w in index}
    by_name_weight = {}
    for w in index:
        key = (normalize_name(w["name"]), int(w["weight_class"]))
        by_name_weight[key] = w["wrestler_id"]
    return by_id, by_name_weight


def load_tournament_matches():
    """Load from the parsed NCAA tourney file (has seeds)."""
    with open("data/2026/ncaa-tourney/parsed/matches.json") as f:
        return json.load(f)


def seed_differential_bucket(diff):
    if diff <= 1:
        return "1"
    elif diff <= 2:
        return "2"
    elif diff <= 4:
        return "3–4"
    elif diff <= 8:
        return "5–8"
    else:
        return "9+"


def tpar_differential_bucket(diff):
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run():
    print("Loading data...")
    pretourney = load_pretourney_tpar()
    by_id, by_name_weight = load_wrestler_index()
    tourney_matches = load_tournament_matches()

    # Resolve name -> wrestler_id for TPAR lookup
    unmatched_names = set()

    enriched = []
    for m in tourney_matches:
        if m.get("result_type") in EXCLUDE_RESULT_TYPES:
            continue

        weight = int(m["weight"])
        w_key = (normalize_name(m["winner_name"]), weight)
        l_key = (normalize_name(m["loser_name"]), weight)

        w_id = by_name_weight.get(w_key)
        l_id = by_name_weight.get(l_key)

        if not w_id:
            unmatched_names.add(m["winner_name"])
        if not l_id:
            unmatched_names.add(m["loser_name"])

        w_tpar = pretourney.get(w_id) if w_id else None
        l_tpar = pretourney.get(l_id) if l_id else None
        has_tpar = w_tpar is not None and l_tpar is not None

        w_seed = m["winner_seed"]
        l_seed = m["loser_seed"]
        seed_diff = abs(w_seed - l_seed)
        seed_correct = w_seed < l_seed  # lower seed number = better seed

        tpar_diff = abs(w_tpar - l_tpar) if has_tpar else None
        tpar_correct = (w_tpar >= l_tpar) if has_tpar else None

        enriched.append({
            **m,
            "w_id": w_id,
            "l_id": l_id,
            "w_tpar": w_tpar,
            "l_tpar": l_tpar,
            "has_tpar": has_tpar,
            "tpar_diff": tpar_diff,
            "tpar_correct": tpar_correct,
            "seed_diff": seed_diff,
            "seed_correct": seed_correct,
        })

    if unmatched_names:
        print(f"  Name lookup misses: {len(unmatched_names)}")
        for n in sorted(unmatched_names)[:10]:
            print(f"    - {n}")
    print()

    tpar_matches = [r for r in enriched if r["has_tpar"]]
    print(f"Matches with both TPAR values: {len(tpar_matches)} / {len(enriched)}")
    print()

    # -------------------------------------------------------------------
    # 1. Seed prediction accuracy by seed differential
    # -------------------------------------------------------------------
    SEED_BUCKET_ORDER = ["1", "2", "3–4", "5–8", "9+"]
    seed_bucket_stats = defaultdict(lambda: {"total": 0, "correct": 0})
    for r in enriched:
        b = seed_differential_bucket(r["seed_diff"])
        seed_bucket_stats[b]["total"] += 1
        if r["seed_correct"]:
            seed_bucket_stats[b]["correct"] += 1

    total_s = sum(s["total"] for s in seed_bucket_stats.values())
    correct_s = sum(s["correct"] for s in seed_bucket_stats.values())

    print("=" * 60)
    print("SEEDING PREDICTION ACCURACY BY SEED DIFFERENTIAL")
    print("=" * 60)
    print(f"  Overall: {correct_s} / {total_s}  ({100*correct_s/total_s:.1f}%)")
    print()
    print(f"  {'Seed Diff':<10}  {'Matches':>8}  {'Correct':>8}  {'Accuracy':>9}")
    print(f"  {'-'*10}  {'-'*8}  {'-'*8}  {'-'*9}")
    for b in SEED_BUCKET_ORDER:
        s = seed_bucket_stats[b]
        if s["total"] == 0:
            continue
        acc = 100 * s["correct"] / s["total"]
        print(f"  {b:<10}  {s['total']:>8}  {s['correct']:>8}  {acc:>8.1f}%")
    print()

    # -------------------------------------------------------------------
    # 2. TPAR prediction accuracy (same as before, for comparison)
    # -------------------------------------------------------------------
    TPAR_BUCKET_ORDER = ["< 0.5", "0.5–1.0", "1.0–2.0", "2.0–3.0", "3.0+"]
    tpar_bucket_stats = defaultdict(lambda: {"total": 0, "correct": 0})
    for r in tpar_matches:
        b = tpar_differential_bucket(r["tpar_diff"])
        tpar_bucket_stats[b]["total"] += 1
        if r["tpar_correct"]:
            tpar_bucket_stats[b]["correct"] += 1

    total_t = len(tpar_matches)
    correct_t = sum(1 for r in tpar_matches if r["tpar_correct"])

    print("=" * 60)
    print("TPAR PREDICTION ACCURACY BY TPAR DIFFERENTIAL")
    print("=" * 60)
    print(f"  Overall: {correct_t} / {total_t}  ({100*correct_t/total_t:.1f}%)")
    print()
    print(f"  {'TPAR Diff':<12}  {'Matches':>8}  {'Correct':>8}  {'Accuracy':>9}")
    print(f"  {'-'*12}  {'-'*8}  {'-'*8}  {'-'*9}")
    for b in TPAR_BUCKET_ORDER:
        s = tpar_bucket_stats[b]
        if s["total"] == 0:
            continue
        acc = 100 * s["correct"] / s["total"]
        print(f"  {b:<12}  {s['total']:>8}  {s['correct']:>8}  {acc:>8.1f}%")
    print()

    # -------------------------------------------------------------------
    # 3. Investigate the sub-0.5 TPAR bucket: what are the seeds doing?
    # -------------------------------------------------------------------
    sub05 = [r for r in tpar_matches if r["tpar_diff"] < 0.5]

    print("=" * 60)
    print(f"DEEP DIVE: SUB-0.5 TPAR DIFFERENTIAL  (n={len(sub05)})")
    print("=" * 60)

    seed_agrees_tpar = sum(1 for r in sub05 if r["tpar_correct"] == r["seed_correct"])
    seed_correct_count = sum(1 for r in sub05 if r["seed_correct"])
    tpar_correct_count = sum(1 for r in sub05 if r["tpar_correct"])
    both_wrong = sum(1 for r in sub05 if not r["tpar_correct"] and not r["seed_correct"])
    both_right = sum(1 for r in sub05 if r["tpar_correct"] and r["seed_correct"])
    seed_right_tpar_wrong = sum(1 for r in sub05 if r["seed_correct"] and not r["tpar_correct"])
    tpar_right_seed_wrong = sum(1 for r in sub05 if r["tpar_correct"] and not r["seed_correct"])
    avg_seed_diff = sum(r["seed_diff"] for r in sub05) / len(sub05)

    print(f"  Seed accuracy in this bucket:  {seed_correct_count} / {len(sub05)}  ({100*seed_correct_count/len(sub05):.1f}%)")
    print(f"  TPAR accuracy in this bucket:  {tpar_correct_count} / {len(sub05)}  ({100*tpar_correct_count/len(sub05):.1f}%)")
    print(f"  Avg seed differential:         {avg_seed_diff:.1f}")
    print()
    print(f"  Agreement breakdown:")
    print(f"    Both right:              {both_right:>4}")
    print(f"    Seed right, TPAR wrong:  {seed_right_tpar_wrong:>4}  ← seed outperforms TPAR")
    print(f"    TPAR right, seed wrong:  {tpar_right_seed_wrong:>4}  ← TPAR outperforms seed")
    print(f"    Both wrong:              {both_wrong:>4}  ← genuine upsets")
    print()

    # Seed diff distribution within sub-0.5 TPAR bucket
    print(f"  Seed differential distribution within sub-0.5 TPAR bucket:")
    sd_counts = defaultdict(int)
    for r in sub05:
        sd_counts[seed_differential_bucket(r["seed_diff"])] += 1
    for b in SEED_BUCKET_ORDER:
        if sd_counts[b]:
            print(f"    Seed diff {b:<5}: {sd_counts[b]} matches")
    print()

    # Cases where seed correctly predicted but TPAR didn't
    print(f"  Matches where TPAR was wrong but seed was right (top 15 by seed diff):")
    seed_beats_tpar = [r for r in sub05 if r["seed_correct"] and not r["tpar_correct"]]
    seed_beats_tpar.sort(key=lambda x: -x["seed_diff"])
    print(f"  {'Winner':<25} {'Seed':>4}  {'TPAR':>6}  {'Loser':<25} {'Seed':>4}  {'TPAR':>6}  {'Wt':>4}")
    print(f"  {'-'*25} {'-'*4}  {'-'*6}  {'-'*25} {'-'*4}  {'-'*6}  {'-'*4}")
    for r in seed_beats_tpar[:15]:
        print(f"  {r['winner_name']:<25} #{r['winner_seed']:<3}  {r['w_tpar']:>+.2f}   "
              f"{r['loser_name']:<25} #{r['loser_seed']:<3}  {r['l_tpar']:>+.2f}   {r['weight']:>4}")


if __name__ == "__main__":
    run()
