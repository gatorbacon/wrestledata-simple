"""
Investigates what TPAR is missing in the sub-0.5 differential bucket.

Hypothesis: TPAR over-rewards bonus points against weak schedules.
Wrestlers who built TPAR through bonus-heavy wins against unranked/low-ranked
opponents look better than ones who grinded close wins against elite fields.
Seeds account for quality-of-win implicitly; TPAR doesn't.

For the 48 "seed right, TPAR wrong" cases, we compare:
  - actual winner (better seeded, lower TPAR)
  - actual loser  (worse seeded, higher TPAR)
on: % matches vs ranked, win rate vs ranked, bonus rate vs ranked,
    bonus rate vs unranked, avg opponent rank.
"""

import json
import glob
import unicodedata
import re
from collections import defaultdict

DATA_DIR = "frontend/wrestledata-ui/public/data"
SEASON = 2026
NCAA_EVENT = "2026 NCAA Division I Championships"
NCAA_DATE_IMPACT = "03/21/2026"
EXCLUDE_RESULT_TYPES = {"Forfeit", "MFF"}


def normalize_name(name):
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
    by_id = {w["wrestler_id"]: w for w in index}
    by_name_weight = {}
    for w in index:
        key = (normalize_name(w["name"]), int(w["weight_class"]))
        by_name_weight[key] = w["wrestler_id"]
    return by_id, by_name_weight


def load_wrestler_profile(wrestler_id):
    path = f"{DATA_DIR}/wrestlers/{SEASON}/by_id/{wrestler_id}.json"
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def is_bonus(method):
    m = (method or "").upper()
    return any(x in m for x in ("FALL", "PIN", "TF", "TECH", "MD", "MAJ"))


def compute_schedule_profile(wrestler_id, exclude_event=NCAA_EVENT):
    """
    Returns dict of schedule metrics from the wrestler's regular-season matches.
    """
    profile = load_wrestler_profile(wrestler_id)
    if not profile:
        return None

    matches = [
        m for m in profile.get("match_list", [])
        if m.get("event") != exclude_event
        and m.get("method", "") != "MFF"
    ]

    if not matches:
        return None

    total = len(matches)
    wins = [m for m in matches if m.get("result") == "W"]
    losses = [m for m in matches if m.get("result") == "L"]

    ranked_matches = [m for m in matches if m.get("opponent_rank") is not None]
    unranked_matches = [m for m in matches if m.get("opponent_rank") is None]

    ranked_wins = [m for m in ranked_matches if m.get("result") == "W"]
    ranked_losses = [m for m in ranked_matches if m.get("result") == "L"]

    bonus_wins = [m for m in wins if is_bonus(m.get("method"))]
    bonus_wins_ranked = [m for m in ranked_wins if is_bonus(m.get("method"))]
    bonus_wins_unranked = [m for m in wins
                           if is_bonus(m.get("method")) and m.get("opponent_rank") is None]

    top10_matches = [m for m in matches if (m.get("opponent_rank") or 999) <= 10]
    top10_wins = [m for m in top10_matches if m.get("result") == "W"]

    avg_opp_rank = (
        sum(m["opponent_rank"] for m in ranked_matches) / len(ranked_matches)
        if ranked_matches else None
    )

    return {
        "total_matches": total,
        "win_pct": len(wins) / total if total else 0,
        "ranked_match_pct": len(ranked_matches) / total if total else 0,
        "ranked_matches": len(ranked_matches),
        "win_rate_vs_ranked": len(ranked_wins) / len(ranked_matches) if ranked_matches else None,
        "bonus_rate_overall": len(bonus_wins) / len(wins) if wins else 0,
        "bonus_rate_vs_ranked": len(bonus_wins_ranked) / len(ranked_wins) if ranked_wins else None,
        "bonus_rate_vs_unranked": len(bonus_wins_unranked) / len([m for m in wins if m.get("opponent_rank") is None])
                                   if [m for m in wins if m.get("opponent_rank") is None] else None,
        "top10_matches": len(top10_matches),
        "top10_wins": len(top10_wins),
        "avg_opp_rank": avg_opp_rank,
    }


def fmt(val, pct=False, decimals=1):
    if val is None:
        return "  n/a"
    if pct:
        return f"{100*val:>{decimals+4}.{decimals}f}%"
    return f"{val:>{decimals+3}.{decimals}f}"


def run():
    print("Loading data...")
    pretourney = load_pretourney_tpar()
    by_id, by_name_weight = load_wrestler_index()

    with open("data/2026/ncaa-tourney/parsed/matches.json") as f:
        tourney_matches = json.load(f)

    # Build enriched matchup list
    enriched = []
    for m in tourney_matches:
        if m.get("result_type") in EXCLUDE_RESULT_TYPES:
            continue
        weight = int(m["weight"])
        w_id = by_name_weight.get((normalize_name(m["winner_name"]), weight))
        l_id = by_name_weight.get((normalize_name(m["loser_name"]), weight))
        w_tpar = pretourney.get(w_id) if w_id else None
        l_tpar = pretourney.get(l_id) if l_id else None
        if w_tpar is None or l_tpar is None:
            continue
        tpar_diff = abs(w_tpar - l_tpar)
        seed_correct = m["winner_seed"] < m["loser_seed"]
        tpar_correct = w_tpar >= l_tpar
        enriched.append({**m, "w_id": w_id, "l_id": l_id,
                         "w_tpar": w_tpar, "l_tpar": l_tpar,
                         "tpar_diff": tpar_diff, "tpar_correct": tpar_correct,
                         "seed_correct": seed_correct})

    # The 48 cases: seed right, TPAR wrong, sub-0.5 differential
    disagree = [r for r in enriched
                if r["tpar_diff"] < 0.5
                and r["seed_correct"] and not r["tpar_correct"]]

    print(f"Seed-right / TPAR-wrong cases (sub-0.5): {len(disagree)}")
    print()

    # For each case, "seed winner" = actual winner (better seed), "tpar winner" = loser (higher TPAR)
    seed_winner_profiles = []
    tpar_winner_profiles = []

    for r in disagree:
        # actual winner = better seeded = r["winner_*"]
        # tpar-predicted winner = higher TPAR = loser (since tpar_correct is False)
        sw_id = r["w_id"]   # seed winner
        tw_id = r["l_id"]   # tpar-predicted winner (higher TPAR, lost)
        sp = compute_schedule_profile(sw_id)
        tp = compute_schedule_profile(tw_id)
        if sp:
            seed_winner_profiles.append(sp)
        if tp:
            tpar_winner_profiles.append(tp)

    def avg(lst, key):
        vals = [p[key] for p in lst if p.get(key) is not None]
        return sum(vals) / len(vals) if vals else None

    metrics = [
        ("Win %",               "win_pct",              True),
        ("% matches vs ranked", "ranked_match_pct",     True),
        ("Win rate vs ranked",  "win_rate_vs_ranked",   True),
        ("Bonus rate overall",  "bonus_rate_overall",   True),
        ("Bonus rate vs ranked","bonus_rate_vs_ranked", True),
        ("Bonus rate vs unranked","bonus_rate_vs_unranked", True),
        ("Top-10 wins",         "top10_wins",           False),
        ("Avg opp rank (ranked matches)", "avg_opp_rank", False),
        ("Total matches",       "total_matches",        False),
    ]

    print("=" * 72)
    print("SCHEDULE PROFILE: Actual Winners vs TPAR-Predicted Winners")
    print("(sub-0.5 TPAR diff, seed correct, TPAR wrong — n=48)")
    print("=" * 72)
    print(f"  {'Metric':<35} {'Actual winner':>14} {'TPAR winner':>13} {'Δ':>8}")
    print(f"  {'-'*35} {'-'*14} {'-'*13} {'-'*8}")
    for label, key, is_pct in metrics:
        sw_val = avg(seed_winner_profiles, key)
        tw_val = avg(tpar_winner_profiles, key)
        if is_pct:
            sw_str = fmt(sw_val, pct=True)
            tw_str = fmt(tw_val, pct=True)
            delta = f"{100*(sw_val - tw_val):>+.1f}%" if sw_val is not None and tw_val is not None else "  n/a"
        else:
            sw_str = fmt(sw_val, pct=False)
            tw_str = fmt(tw_val, pct=False)
            delta = f"{sw_val - tw_val:>+.1f}" if sw_val is not None and tw_val is not None else "  n/a"
        print(f"  {label:<35} {sw_str:>14} {tw_str:>13} {delta:>8}")

    print()

    # -------------------------------------------------------------------
    # Breakdown: where did TPAR-winners build their bonus points?
    # -------------------------------------------------------------------
    print("=" * 72)
    print("BONUS WIN BREAKDOWN for TPAR-predicted winners (higher TPAR, lost)")
    print("=" * 72)
    print(f"  {'Name':<28} {'Seed':>5} {'TPAR':>6}  {'Bonus/Rnk':>10}  {'Bonus/Unrnk':>12}  {'AvgOppRnk':>10}")
    print(f"  {'-'*28} {'-'*5} {'-'*6}  {'-'*10}  {'-'*12}  {'-'*10}")
    for r in sorted(disagree, key=lambda x: -x["tpar_diff"]):
        tw_id = r["l_id"]
        tp = compute_schedule_profile(tw_id)
        if not tp:
            continue
        name = r["loser_name"]
        seed = r["loser_seed"]
        tpar = r["l_tpar"]
        bvr = f"{100*tp['bonus_rate_vs_ranked']:.0f}%" if tp["bonus_rate_vs_ranked"] is not None else "n/a"
        bvu = f"{100*tp['bonus_rate_vs_unranked']:.0f}%" if tp["bonus_rate_vs_unranked"] is not None else "n/a"
        aor = f"{tp['avg_opp_rank']:.0f}" if tp["avg_opp_rank"] is not None else "n/a"
        print(f"  {name:<28} #{seed:<4} {tpar:>+.2f}  {bvr:>10}  {bvu:>12}  {aor:>10}")


if __name__ == "__main__":
    run()
