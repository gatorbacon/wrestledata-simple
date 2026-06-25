"""
Record of each rank group (0-10, 11-20, ...) vs the central cohort (ranks 78-102)
at a single weight class. Shows win%, avg team pts scored/given/net.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, "scripts/mat_value")
from compute_mat_value import load_rankings, classify_result_type

SEASON   = 2026
WEIGHT   = 157
DATA_DIR = "mt/rankings_data/ncaa_men"

CENTRAL_LO = 78
CENTRAL_HI = 102

RESULT_PTS = {
    "Fall":    6,
    "TF":      5,
    "MD":      4,
    "Dec":     3,
    "Forfeit": 6,
    "Inj":     6,
}


def result_to_pts(result_type):
    for key in RESULT_PTS:
        if key.lower() in result_type.lower():
            return RESULT_PTS[key]
    return 3  # default to decision


def rank_bucket(rank):
    if rank is None:
        return "Unranked"
    for lo in range(1, 210, 10):
        hi = lo + 9
        if lo <= rank <= hi:
            return f"{lo}-{hi}"
    return "Unranked"


def main():
    # Load rankings
    rmap = load_rankings(SEASON, WEIGHT, DATA_DIR, use_cache=True, league="ncaa")
    rmap.pop("__max_rank__", None)

    central = {wid for wid, rank in rmap.items() if CENTRAL_LO <= rank <= CENTRAL_HI}
    print(f"Central cohort ({CENTRAL_LO}-{CENTRAL_HI}): {len(central)} wrestlers")

    # Load all matches
    matches = []
    data_path = Path(DATA_DIR) / str(SEASON)
    for pattern in [f"weight_class_{WEIGHT}.json", f"weight_class_{WEIGHT}A.json"]:
        wc_file = data_path / pattern
        if wc_file.exists():
            with wc_file.open() as f:
                matches.extend(json.load(f).get("matches", []))

    print(f"Total matches loaded: {len(matches)}")

    # Bucket records: bucket -> {wins, losses, pts_scored, pts_given, n}
    buckets = defaultdict(lambda: {"wins": 0, "losses": 0, "pts_scored": 0, "pts_given": 0, "n": 0})

    for m in matches:
        result = m.get("result", "")
        rt     = classify_result_type(result)
        if rt in ("MFF", "Forfeit"):
            continue

        w1     = m.get("wrestler1_id")
        w2     = m.get("wrestler2_id")
        winner = m.get("winner_id")
        if not w1 or not w2:
            continue

        r1 = rmap.get(w1)
        r2 = rmap.get(w2)

        # We want matches where exactly one participant is in the central cohort
        w1_central = w1 in central
        w2_central = w2 in central
        if w1_central == w2_central:
            continue  # both or neither in central cohort — skip

        # Identify the non-central wrestler and their rank
        if w1_central:
            other_id   = w2
            other_rank = r2
            other_won  = (winner == w2)
        else:
            other_id   = w1
            other_rank = r1
            other_won  = (winner == w1)

        pts = result_to_pts(rt)
        bucket = rank_bucket(other_rank)

        buckets[bucket]["n"] += 1
        if other_won:
            buckets[bucket]["wins"]       += 1
            buckets[bucket]["pts_scored"] += pts
        else:
            buckets[bucket]["losses"]     += 1
            buckets[bucket]["pts_given"]  += pts

    # Define display order
    ordered = []
    for lo in range(1, 210, 10):
        hi  = lo + 9
        key = f"{lo}-{hi}"
        if key == f"{CENTRAL_LO-2}-{CENTRAL_LO+7}":  # skip the central bucket itself
            continue
        ordered.append(key)
    ordered.append("Unranked")

    # Filter to buckets that overlap the central range
    central_bucket = rank_bucket(CENTRAL_LO)

    print(f"\n{'='*75}")
    print(f"  157 lbs — Record vs central cohort (ranks {CENTRAL_LO}–{CENTRAL_HI})")
    print(f"{'='*75}")
    print(f"  {'Rank group':<12} {'n':>4}  {'W':>4} {'L':>4}  {'Win%':>7}  {'Pts/match':>10}  {'Opp pts':>8}  {'Net':>7}")
    print(f"  {'-'*12} {'-'*4}  {'-'*4} {'-'*4}  {'-'*7}  {'-'*10}  {'-'*8}  {'-'*7}")

    for key in ordered:
        b = buckets.get(key)
        if not b or b["n"] == 0:
            continue
        # Skip the bucket that contains the central cohort itself
        lo_val = int(key.split("-")[0]) if key != "Unranked" else 999
        if CENTRAL_LO <= lo_val <= CENTRAL_HI or (lo_val < CENTRAL_LO and lo_val + 9 >= CENTRAL_LO):
            marker = "  ← central"
        else:
            marker = ""

        n           = b["n"]
        wins        = b["wins"]
        losses      = b["losses"]
        win_pct     = 100 * wins / n
        pts_per     = b["pts_scored"] / n
        opp_pts     = b["pts_given"] / n
        net         = pts_per - opp_pts

        print(f"  {key:<12} {n:>4}  {wins:>4} {losses:>4}  {win_pct:>6.1f}%  {pts_per:>10.2f}  {opp_pts:>8.2f}  {net:>+7.2f}{marker}")

    # Also show the central-vs-central record as a reference
    cc_wins = cc_total = cc_pts = 0
    for m in matches:
        result = m.get("result", "")
        rt     = classify_result_type(result)
        if rt in ("MFF", "Forfeit"):
            continue
        w1 = m.get("wrestler1_id")
        w2 = m.get("wrestler2_id")
        winner = m.get("winner_id")
        if not w1 or not w2:
            continue
        if w1 in central and w2 in central:
            cc_total += 1
            pts = result_to_pts(rt)
            if winner in central:
                cc_wins += 1
                cc_pts  += pts

    if cc_total:
        avg_pts = cc_pts / cc_total
        print(f"\n  Central vs Central (internal): {cc_wins}W/{cc_total-cc_wins}L  {100*cc_wins/cc_total:.1f}%  {avg_pts:.2f} pts/match scored")


if __name__ == "__main__":
    main()
