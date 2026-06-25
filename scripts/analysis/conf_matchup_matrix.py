"""
Conference matchup matrix for 2026 NCAA tournament.

For every conference pair (winner conf × loser conf), shows:
  n       — matches played
  TPAR%   — % TPAR v1 correctly predicted the winner
  Seed%   — % seeds correctly predicted the winner

Rows = winner conference, columns = loser conference.
Also prints flat sorted tables for easy pattern reading.
"""

import json, glob, unicodedata, re
from collections import defaultdict

SEASON       = 2026
FRONTEND_DIR = "frontend/wrestledata-ui/public/data"
NCAA_DATE    = "03/21/2026"

CONF_EVENT_MAP = {
    "Big Ten": "Big Ten", "ACC": "ACC", "Big 12": "Big 12",
    "Ivy League": "CAA", "MAC Wrestling": "MAC",
    "Southern Conference": "SoCon", "EIWA": "EIWA",
    "PAC-12": "Pac-12", "Pac-12": "Pac-12",
    "Colonial": "CAA", "CAA": "CAA", "SoCon": "SoCon",
}

CONF_ORDER = ["Big Ten", "Big 12", "ACC", "CAA", "Pac-12", "EIWA", "MAC", "SoCon"]


def norm(name):
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", name.strip().lower())


def main():
    with open(f"{FRONTEND_DIR}/wrestlers/{SEASON}/index_wrestlers.json") as f:
        index = json.load(f)
    by_name_wt = {(norm(w["name"]), int(w["weight_class"])): w["wrestler_id"] for w in index}

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

    with open(f"{FRONTEND_DIR}/mat_value/{SEASON}/match_mv_impact_{SEASON}.json") as f:
        v1_raw = json.load(f)
    tpar_v1 = {}
    for wid, matches in v1_raw.items():
        reg = [m["mv_impact"] for m in matches if m["date"] != NCAA_DATE]
        if reg:
            tpar_v1[wid] = sum(reg) / len(reg)

    with open(f"data/{SEASON}/ncaa-tourney/parsed/matches.json") as f:
        tourney = json.load(f)

    # cells[wconf][lconf] = {"n":0, "tpar":0, "seed":0}
    cells = defaultdict(lambda: defaultdict(lambda: {"n": 0, "tpar": 0, "seed": 0}))
    rows  = []

    for m in tourney:
        if m.get("result_type") in {"Forfeit", "MFF"}: continue
        wt   = int(m["weight"])
        w_id = by_name_wt.get((norm(m["winner_name"]), wt))
        l_id = by_name_wt.get((norm(m["loser_name"]), wt))
        if not w_id or not l_id: continue

        wv1 = tpar_v1.get(w_id)
        lv1 = tpar_v1.get(l_id)
        if wv1 is None or lv1 is None: continue

        wconf = team_conf.get(m["winner_team"], "?")
        lconf = team_conf.get(m["loser_team"],  "?")
        ws    = m["winner_seed"]
        ls    = m["loser_seed"]

        tpar_right = wv1 >= lv1
        seed_right = ws  <  ls

        cells[wconf][lconf]["n"]    += 1
        if tpar_right: cells[wconf][lconf]["tpar"] += 1
        if seed_right: cells[wconf][lconf]["seed"] += 1

        rows.append({
            "wconf": wconf, "lconf": lconf,
            "tpar_right": tpar_right, "seed_right": seed_right,
            "wt": wt, "round": m.get("round","?"),
            "winner": m["winner_name"], "loser": m["loser_name"],
            "ws": ws, "ls": ls, "wv1": wv1, "lv1": lv1,
        })

    # Collect all conferences seen
    all_confs = sorted(
        {r["wconf"] for r in rows} | {r["lconf"] for r in rows},
        key=lambda c: CONF_ORDER.index(c) if c in CONF_ORDER else 99
    )

    # ── Matrix: match count ───────────────────────────────────────────────────
    col_w = 9
    header_label = f"{'W\\L':<10}"

    def print_matrix(title, value_fn, fmt_fn):
        print(f"\n{'='*(10 + col_w * len(all_confs) + 4)}")
        print(f"  {title}")
        print(f"{'='*(10 + col_w * len(all_confs) + 4)}")
        hdr = f"  {header_label}" + "".join(f"{c[:8]:>{col_w}}" for c in all_confs)
        print(hdr)
        print("  " + "-"*(8 + col_w * len(all_confs)))
        for wc in all_confs:
            row_str = f"  {wc:<10}"
            for lc in all_confs:
                if wc == lc:
                    row_str += f"{'—':>{col_w}}"
                else:
                    cell = cells[wc][lc]
                    v = value_fn(cell)
                    row_str += fmt_fn(v, cell)
            print(row_str)

    # Count matrix
    print_matrix(
        "Match count  (row=winner conf, col=loser conf)",
        lambda c: c["n"],
        lambda v, c: f"{v:>{col_w}}" if v > 0 else f"{'':>{col_w}}"
    )

    # TPAR accuracy matrix
    print_matrix(
        "TPAR v1 accuracy %  (row=winner conf, col=loser conf)",
        lambda c: 100 * c["tpar"] / c["n"] if c["n"] >= 3 else None,
        lambda v, c: (f"{v:>{col_w-1}.0f}%" if v is not None and c['n'] >= 3
                      else f"{'—':>{col_w}}" if c['n'] > 0
                      else f"{'':>{col_w}}")
    )

    # Seed accuracy matrix
    print_matrix(
        "Seed accuracy %  (row=winner conf, col=loser conf)",
        lambda c: 100 * c["seed"] / c["n"] if c["n"] >= 3 else None,
        lambda v, c: (f"{v:>{col_w-1}.0f}%" if v is not None and c['n'] >= 3
                      else f"{'—':>{col_w}}" if c['n'] > 0
                      else f"{'':>{col_w}}")
    )

    # TPAR - Seed delta matrix
    print_matrix(
        "TPAR% − Seed%  (positive = TPAR better than seed for this matchup)",
        lambda c: None,
        lambda v, c: (
            f"{(100*c['tpar']/c['n'] - 100*c['seed']/c['n']):>+{col_w-1}.0f}%"
            if c['n'] >= 3 else
            f"{'—':>{col_w}}" if c['n'] > 0 else f"{'':>{col_w}}"
        )
    )

    # ── Flat table sorted by n ────────────────────────────────────────────────
    flat = []
    for wc in all_confs:
        for lc in all_confs:
            if wc == lc: continue
            c = cells[wc][lc]
            if c["n"] == 0: continue
            flat.append({
                "wconf": wc, "lconf": lc,
                "n": c["n"], "tpar": c["tpar"], "seed": c["seed"],
                "tpar_pct": 100*c["tpar"]/c["n"],
                "seed_pct": 100*c["seed"]/c["n"],
                "delta":    100*c["tpar"]/c["n"] - 100*c["seed"]/c["n"],
            })

    flat.sort(key=lambda x: -x["n"])

    print(f"\n{'='*78}")
    print(f"  All matchups — sorted by match count")
    print(f"{'='*78}")
    print(f"  {'Winner Conf':<12}  {'Loser Conf':<12}  {'n':>4}  {'TPAR%':>7}  {'Seed%':>7}  {'Δ(T-S)':>8}  {'TPAR':>6}  {'Seed':>6}")
    print(f"  {'-'*12}  {'-'*12}  {'-'*4}  {'-'*7}  {'-'*7}  {'-'*8}  {'-'*6}  {'-'*6}")
    for r in flat:
        flag = ""
        if r["tpar_pct"] < r["seed_pct"] - 10 and r["n"] >= 5:
            flag = "  ◄ TPAR lagging"
        elif r["tpar_pct"] > r["seed_pct"] + 10 and r["n"] >= 5:
            flag = "  ◄ TPAR leading"
        print(f"  {r['wconf']:<12}  {r['lconf']:<12}  {r['n']:>4}  "
              f"{r['tpar_pct']:>6.1f}%  {r['seed_pct']:>6.1f}%  "
              f"{r['delta']:>+7.1f}%  {r['tpar']:>6}  {r['seed']:>6}{flag}")

    # ── Aggregated: for each winner conference, how does TPAR do vs seed? ────
    print(f"\n{'='*65}")
    print(f"  By winner conference — overall TPAR vs seed accuracy")
    print(f"{'='*65}")
    print(f"  {'Winner Conf':<12}  {'n':>4}  {'TPAR%':>7}  {'Seed%':>7}  {'Δ':>7}")
    print(f"  {'-'*12}  {'-'*4}  {'-'*7}  {'-'*7}  {'-'*7}")
    for wc in all_confs:
        n = sum(cells[wc][lc]["n"]    for lc in all_confs if lc != wc)
        t = sum(cells[wc][lc]["tpar"] for lc in all_confs if lc != wc)
        s = sum(cells[wc][lc]["seed"] for lc in all_confs if lc != wc)
        if n == 0: continue
        print(f"  {wc:<12}  {n:>4}  {100*t/n:>6.1f}%  {100*s/n:>6.1f}%  {100*(t-s)/n:>+6.1f}%")

    # ── Aggregated: for each loser conference ─────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  By loser conference — overall TPAR vs seed accuracy")
    print(f"{'='*65}")
    print(f"  {'Loser Conf':<12}  {'n':>4}  {'TPAR%':>7}  {'Seed%':>7}  {'Δ':>7}")
    print(f"  {'-'*12}  {'-'*4}  {'-'*7}  {'-'*7}  {'-'*7}")
    for lc in all_confs:
        n = sum(cells[wc][lc]["n"]    for wc in all_confs if wc != lc)
        t = sum(cells[wc][lc]["tpar"] for wc in all_confs if wc != lc)
        s = sum(cells[wc][lc]["seed"] for wc in all_confs if wc != lc)
        if n == 0: continue
        print(f"  {lc:<12}  {n:>4}  {100*t/n:>6.1f}%  {100*s/n:>6.1f}%  {100*(t-s)/n:>+6.1f}%")


if __name__ == "__main__":
    main()
