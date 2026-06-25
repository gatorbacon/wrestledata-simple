"""
Two-pass ranking refinement at 157 lbs.

Pass 1: TPAR v1 gives initial ordering → groups of 10
Pass 2: Weighted record vs same/adjacent groups refines sort within each group
        Weights: same group = 1.0, ±1 group = 0.5, ±2 groups = 0.25
        Binary wins only (no margin credit) for the refinement pass.

Shows where each wrestler lands vs their TPAR v1 position.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, "scripts/mat_value")
from compute_mat_value import classify_result_type

SEASON       = 2026
WEIGHT       = 157
DATA_DIR     = "mt/rankings_data/ncaa_men"
FRONTEND_DIR = "frontend/wrestledata-ui/public/data"
NCAA_DATE    = "03/21/2026"
GROUP_SIZE   = 10
WEIGHTS      = {0: 1.0, 1: 0.5, 2: 0.25}

HIGHLIGHT = {"tyler klinsky", "jore volk"}   # lowercase for matching


def main():
    # --- Load data ---
    with open(f"{FRONTEND_DIR}/wrestlers/{SEASON}/index_wrestlers.json") as f:
        index = json.load(f)
    w157 = {w["wrestler_id"]: w for w in index if int(w["weight_class"]) == WEIGHT}

    with open(f"{FRONTEND_DIR}/mat_value/{SEASON}/match_mv_impact_2026.json") as f:
        impact_raw = json.load(f)

    # Pre-tournament TPAR v1
    tpar = {}
    for wid in w157:
        if wid in impact_raw:
            reg = [m["mv_impact"] for m in impact_raw[wid] if m["date"] != NCAA_DATE]
            if reg:
                tpar[wid] = sum(reg) / len(reg)

    # TPAR v1 rank (higher score = better)
    v1_sorted = sorted(tpar, key=lambda x: -tpar[x])
    v1_rank   = {wid: i + 1 for i, wid in enumerate(v1_sorted)}
    group_of  = {wid: (v1_rank[wid] - 1) // GROUP_SIZE for wid in v1_rank}

    # --- Load regular-season matches ---
    raw = []
    for pat in [f"weight_class_{WEIGHT}.json", f"weight_class_{WEIGHT}A.json"]:
        fp = Path(DATA_DIR) / str(SEASON) / pat
        if fp.exists():
            with fp.open() as f:
                raw.extend(json.load(f).get("matches", []))

    matches = []
    for m in raw:
        rt = classify_result_type(m.get("result", ""))
        if rt in ("MFF", "Forfeit"):
            continue
        if "NCAA Division I Championships" in m.get("event", ""):
            continue
        matches.append(m)

    # --- Compute weighted records ---
    w_wins  = defaultdict(float)
    w_total = defaultdict(float)
    detail  = defaultdict(lambda: defaultdict(lambda: [0, 0]))  # [wins, total] per delta

    for m in matches:
        w1, w2   = m.get("wrestler1_id"), m.get("wrestler2_id")
        winner   = m.get("winner_id")
        if not w1 or not w2 or w1 not in v1_rank or w2 not in v1_rank:
            continue

        delta = abs(group_of[w1] - group_of[w2])
        if delta not in WEIGHTS:
            continue

        wt = WEIGHTS[delta]
        for wrestler, opp in [(w1, w2), (w2, w1)]:
            w_total[wrestler] += wt
            detail[wrestler][delta][1] += 1
            if winner == wrestler:
                w_wins[wrestler] += wt
                detail[wrestler][delta][0] += 1

    # --- Sort within each group by refined score ---
    groups = defaultdict(list)
    for wid in v1_rank:
        groups[group_of[wid]].append(wid)

    new_rank = {}
    rank_ctr = 1
    for g in sorted(groups):
        members = groups[g]
        members.sort(key=lambda x: (
            -(w_wins[x] / w_total[x]) if w_total[x] > 0 else -0.5,
            -tpar.get(x, 0)
        ))
        for wid in members:
            new_rank[wid] = rank_ctr
            rank_ctr += 1

    # --- Display ---
    DISPLAY_ROWS = 80   # show top N wrestlers

    print(f"\n{'='*108}")
    print(f"  157 lbs — TPAR v1 vs Group-Refined ranking  (group size={GROUP_SIZE}, weights: Δ0=1.0 Δ1=0.5 Δ2=0.25)")
    print(f"{'='*108}")
    print(f"  {'V1':>4}  {'New':>4}  {'Δ':>4}  {'Name':<26}  {'Team':<24}  {'TPAR':>7}  {'WinRt':>6}  {'W-W/N':>10}  Breakdown (Δ:W-L)")
    print(f"  {'-'*4}  {'-'*4}  {'-'*4}  {'-'*26}  {'-'*24}  {'-'*7}  {'-'*6}  {'-'*10}  {'-'*30}")

    display = sorted(new_rank, key=lambda x: new_rank[x])[:DISPLAY_ROWS]

    prev_group = -1
    for wid in display:
        info  = w157[wid]
        v1r   = v1_rank[wid]
        newr  = new_rank[wid]
        grp   = group_of[wid]
        delta = v1r - newr
        name  = info["name"][:25]
        team  = info.get("team", "")[:23]
        t     = tpar.get(wid, 0)
        wt_w  = w_wins.get(wid, 0)
        wt_n  = w_total.get(wid, 0)
        wr    = wt_w / wt_n if wt_n > 0 else None
        wr_s  = f"{wr:.3f}" if wr is not None else "  n/a"
        wn_s  = f"{wt_w:.1f}/{wt_n:.1f}" if wt_n > 0 else "—"

        d = detail[wid]
        bk = "  ".join(
            f"Δ{k}:{d[k][0]}-{d[k][1]-d[k][0]}"
            for k in sorted(d) if d[k][1] > 0
        )

        delta_s = f"+{delta}" if delta > 0 else (str(delta) if delta != 0 else "—")

        # Group separator
        if grp != prev_group:
            print(f"  {'─'*4}  {'─'*4}  {'─'*4}  group {grp+1} (ranks {grp*GROUP_SIZE+1}–{(grp+1)*GROUP_SIZE})")
            prev_group = grp

        flag = " ◄" if name.lower() in HIGHLIGHT or any(h in name.lower() for h in HIGHLIGHT) else ""

        print(f"  {v1r:>4}  {newr:>4}  {delta_s:>4}  {name:<26}  {team:<24}  {t:>+7.3f}  {wr_s:>6}  {wn_s:>10}  {bk}{flag}")

    # --- Summary: how much movement happened? ---
    all_wrestlers = list(new_rank.keys())
    movers_up   = [(wid, v1_rank[wid] - new_rank[wid]) for wid in all_wrestlers if new_rank[wid] < v1_rank[wid]]
    movers_down = [(wid, v1_rank[wid] - new_rank[wid]) for wid in all_wrestlers if new_rank[wid] > v1_rank[wid]]

    movers_up.sort(key=lambda x: -x[1])
    movers_down.sort(key=lambda x: x[1])

    print(f"\n  Top movers UP (gained most spots):")
    for wid, mv in movers_up[:8]:
        print(f"    +{mv:>2}  #{v1_rank[wid]:>3} → #{new_rank[wid]:>3}  {w157[wid]['name']:<28}  {w157[wid].get('team','')}")

    print(f"\n  Top movers DOWN (lost most spots):")
    for wid, mv in movers_down[:8]:
        print(f"    {mv:>3}  #{v1_rank[wid]:>3} → #{new_rank[wid]:>3}  {w157[wid]['name']:<28}  {w157[wid].get('team','')}")


if __name__ == "__main__":
    main()
