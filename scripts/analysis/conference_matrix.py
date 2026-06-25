"""
Builds a conference vs. conference W/L matrix for a given weight class.
Shows: win rate, match count (confidence), and an overall cross-conference
win % per conference — derived entirely from match data, no anchors.
"""

import json
import sys
import glob
import pathlib
from collections import defaultdict

sys.path.insert(0, "scripts/mat_value")
from compute_mat_value import classify_result_type

DATA_DIR     = "mt/rankings_data/ncaa_men"
FRONTEND_DIR = "frontend/wrestledata-ui/public/data"
SEASON       = 2026
WEIGHT       = 157

CONF_EVENT_MAP = {
    "Big Ten": "Big Ten", "ACC": "ACC", "Big 12": "Big 12",
    "Ivy League": "CAA", "MAC Wrestling": "MAC",
    "Southern Conference": "SoCon", "EIWA": "EIWA",
    "PAC-12": "Pac-12", "Pac-12": "Pac-12",
    "Colonial": "CAA", "CAA": "CAA", "SoCon": "SoCon",
}


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


def main():
    team_conf = build_team_conf()

    with open(f"{FRONTEND_DIR}/wrestlers/{SEASON}/index_wrestlers.json") as f:
        index = json.load(f)
    wrestler_team = {w["wrestler_id"]: w["team"] for w in index}

    # Load matches
    matches = []
    for pattern in [f"weight_class_{WEIGHT}.json", f"weight_class_{WEIGHT}A.json"]:
        wc_file = pathlib.Path(DATA_DIR) / str(SEASON) / pattern
        if wc_file.exists():
            with wc_file.open() as f:
                matches.extend(json.load(f).get("matches", []))

    # Build conf_vs_conf matrix: [conf_a][conf_b] = {wins, total}
    matrix = defaultdict(lambda: defaultdict(lambda: {"wins": 0, "total": 0}))

    skipped = 0
    for m in matches:
        result = m.get("result", "")
        if "MFF" in result.upper() or "FORFEIT" in result.upper():
            continue

        w1     = m.get("wrestler1_id")
        w2     = m.get("wrestler2_id")
        winner = m.get("winner_id")
        if not w1 or not w2:
            continue

        t1 = wrestler_team.get(w1)
        t2 = wrestler_team.get(w2)
        c1 = team_conf.get(t1)
        c2 = team_conf.get(t2)

        if not c1 or not c2:
            skipped += 1
            continue

        # Skip in-conference matches for the cross-conference analysis
        # (keep for overall record calculation)
        matrix[c1][c2]["total"] += 1
        matrix[c2][c1]["total"] += 1

        if winner == w1:
            matrix[c1][c2]["wins"] += 1
        elif winner == w2:
            matrix[c2][c1]["wins"] += 1

    confs = sorted(set(
        c for row in matrix for c in [row] + list(matrix[row].keys())
    ))

    # ---------------------------------------------------------------
    # Table 1: Wins matrix (row conf beat col conf N times)
    # ---------------------------------------------------------------
    col_w = 7
    print(f"\n{'=' * 70}")
    print(f"  {WEIGHT} lbs — WINS matrix (row beat col)")
    print(f"{'=' * 70}")
    header = f"  {'':12}" + "".join(f"{c[:col_w]:>{col_w}}" for c in confs)
    print(header)
    print("  " + "-" * (12 + col_w * len(confs)))
    for c_row in confs:
        row = f"  {c_row:<12}"
        for c_col in confs:
            if c_row == c_col:
                row += f"{'—':>{col_w}}"
            else:
                wins = matrix[c_row][c_col]["wins"]
                row += f"{wins:>{col_w}}"
        print(row)

    # ---------------------------------------------------------------
    # Table 2: Match count matrix (confidence of each linkage)
    # ---------------------------------------------------------------
    print(f"\n{'=' * 70}")
    print(f"  {WEIGHT} lbs — MATCH COUNT matrix (confidence of linkage)")
    print(f"{'=' * 70}")
    print(header)
    print("  " + "-" * (12 + col_w * len(confs)))
    for c_row in confs:
        row = f"  {c_row:<12}"
        for c_col in confs:
            if c_row == c_col:
                row += f"{'—':>{col_w}}"
            else:
                total = matrix[c_row][c_col]["total"]
                row += f"{total:>{col_w}}"
        print(row)

    # ---------------------------------------------------------------
    # Table 3: Win % matrix (only cells with >=3 matches)
    # ---------------------------------------------------------------
    print(f"\n{'=' * 70}")
    print(f"  {WEIGHT} lbs — WIN% matrix (blank if <3 matches)")
    print(f"{'=' * 70}")
    col_w2 = 8
    header2 = f"  {'':12}" + "".join(f"{c[:col_w2]:>{col_w2}}" for c in confs)
    print(header2)
    print("  " + "-" * (12 + col_w2 * len(confs)))
    for c_row in confs:
        row = f"  {c_row:<12}"
        for c_col in confs:
            if c_row == c_col:
                row += f"{'—':>{col_w2}}"
            else:
                cell = matrix[c_row][c_col]
                if cell["total"] >= 3:
                    pct = 100 * cell["wins"] / cell["total"]
                    row += f"{pct:>{col_w2-1}.0f}%"
                else:
                    row += f"{'':>{col_w2}}"
        print(row)

    # ---------------------------------------------------------------
    # Summary: cross-conference win % per conference (all opponents combined)
    # ---------------------------------------------------------------
    print(f"\n{'=' * 70}")
    print(f"  {WEIGHT} lbs — CROSS-CONFERENCE RECORD (excluding in-conf matches)")
    print(f"{'=' * 70}")
    print(f"  {'Conference':<14} {'W':>5} {'L':>5} {'Matches':>8} {'Win%':>7}  {'Connections'}")
    print(f"  {'-'*14} {'-'*5} {'-'*5} {'-'*8} {'-'*7}  {'-'*30}")

    conf_summary = []
    for c_row in confs:
        cross_wins = cross_total = 0
        connections = []
        for c_col in confs:
            if c_col == c_row:
                continue
            cell = matrix[c_row][c_col]
            if cell["total"] > 0:
                cross_wins  += cell["wins"]
                cross_total += cell["total"]
                connections.append(f"{c_col}({cell['total']})")
        cross_pct = 100 * cross_wins / cross_total if cross_total else 0
        conf_summary.append((c_row, cross_wins, cross_total - cross_wins, cross_total, cross_pct, connections))

    conf_summary.sort(key=lambda x: -x[4])
    for c, w, l, tot, pct, conns in conf_summary:
        conn_str = ", ".join(conns[:6])
        print(f"  {c:<14} {w:>5} {l:>5} {tot:>8} {pct:>6.1f}%  {conn_str}")

    print(f"\n  (Skipped {skipped} matches with unmapped conferences)")


if __name__ == "__main__":
    main()
