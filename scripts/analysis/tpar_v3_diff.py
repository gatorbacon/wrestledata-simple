"""
Shows every match where v1 and v3 TPAR predictions differ.
Prints the 14 fixed (v1 wrong → v3 right) and 7 broken (v1 right → v3 wrong).
"""

import json
import unicodedata
import re

FRONTEND_DIR = "frontend/wrestledata-ui/public/data"
SEASON       = 2026
NCAA_DATE    = "03/21/2026"

CONF_EVENT_MAP = {
    "Big Ten": "Big Ten", "ACC": "ACC", "Big 12": "Big 12",
    "Ivy League": "Ivy League", "MAC Wrestling": "MAC",
    "Southern Conference": "SoCon", "EIWA": "EIWA",
    "PAC-12": "Pac-12", "Pac-12": "Pac-12",
    "Colonial": "CAA", "CAA": "CAA", "SoCon": "SoCon",
}


def normalize(name):
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", name.strip().lower())


def load_pretourney(path):
    with open(path) as f:
        data = json.load(f)
    out = {}
    for wid, matches in data.items():
        reg = [m["mv_impact"] for m in matches if m["date"] != NCAA_DATE]
        if reg:
            out[wid] = sum(reg) / len(reg)
    return out


def build_team_conf():
    import glob
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
    with open(f"{FRONTEND_DIR}/wrestlers/{SEASON}/index_wrestlers.json") as f:
        index = json.load(f)
    by_id      = {w["wrestler_id"]: w for w in index}
    by_name_wt = {(normalize(w["name"]), int(w["weight_class"])): w["wrestler_id"] for w in index}

    team_conf = build_team_conf()

    v1 = load_pretourney(f"{FRONTEND_DIR}/mat_value/{SEASON}/match_mv_impact_2026.json")
    v3 = load_pretourney(f"{FRONTEND_DIR}/mat_value/{SEASON}/match_mv_impact_v3_2026.json")

    with open(f"data/{SEASON}/ncaa-tourney/parsed/matches.json") as f:
        tourney = json.load(f)

    fixed   = []
    broken  = []

    for m in tourney:
        if m.get("result_type") in {"Forfeit", "MFF"}:
            continue
        wt    = int(m["weight"])
        w_id  = by_name_wt.get((normalize(m["winner_name"]), wt))
        l_id  = by_name_wt.get((normalize(m["loser_name"]), wt))
        if not w_id or not l_id:
            continue

        wv1 = v1.get(w_id); lv1 = v1.get(l_id)
        wv3 = v3.get(w_id); lv3 = v3.get(l_id)
        if None in (wv1, lv1, wv3, lv3):
            continue

        v1_correct = wv1 >= lv1
        v3_correct = wv3 >= lv3

        if v1_correct == v3_correct:
            continue  # no change

        winner_team = m["winner_team"]
        loser_team  = m["loser_team"]
        wconf = team_conf.get(winner_team, "?")
        lconf = team_conf.get(loser_team, "?")

        row = {
            "weight":       wt,
            "round":        m.get("round", "?"),
            "winner_name":  m["winner_name"],
            "winner_seed":  m["winner_seed"],
            "winner_team":  winner_team,
            "winner_conf":  wconf,
            "loser_name":   m["loser_name"],
            "loser_seed":   m["loser_seed"],
            "loser_team":   loser_team,
            "loser_conf":   lconf,
            "v1_diff":      abs(wv1 - lv1),
            "v3_diff":      abs(wv3 - lv3),
            "v1_w_tpar":    wv1,
            "v1_l_tpar":    lv1,
            "v3_w_tpar":    wv3,
            "v3_l_tpar":    lv3,
        }

        if not v1_correct and v3_correct:
            fixed.append(row)
        else:
            broken.append(row)

    def print_matches(label, rows, emoji):
        print(f"\n{'='*80}")
        print(f"  {emoji}  {label}  ({len(rows)} matches)")
        print(f"{'='*80}")
        print(f"  {'Wt':>3}  {'Rd':<6}  {'Winner':<24} {'Loser':<24}  {'Seed':>5}  {'v1Δ':>6}  {'v3Δ':>6}  {'Conf'}")
        print(f"  {'-'*3}  {'-'*6}  {'-'*24} {'-'*24}  {'-'*5}  {'-'*6}  {'-'*6}  {'-'*12}")
        for r in sorted(rows, key=lambda x: (x["weight"], x["winner_seed"])):
            seed_str  = f"#{r['winner_seed']} def #{r['loser_seed']}"
            conf_str  = f"{r['winner_conf']} def {r['loser_conf']}"
            winner_short = r["winner_name"][:23]
            loser_short  = r["loser_name"][:23]
            print(f"  {r['weight']:>3}  {r['round']:<6}  {winner_short:<24} {loser_short:<24}  {seed_str:>5}  {r['v1_diff']:>6.2f}  {r['v3_diff']:>6.2f}  {conf_str}")
        print()
        print(f"  {'Wt':>3}  {'Winner':<24}  v1_TPAR    v3_TPAR  |  {'Loser':<24}  v1_TPAR    v3_TPAR")
        print(f"  {'-'*3}  {'-'*24}  {'-'*9}  {'-'*9}  |  {'-'*24}  {'-'*9}  {'-'*9}")
        for r in sorted(rows, key=lambda x: (x["weight"], x["winner_seed"])):
            wn = r["winner_name"][:23]
            ln = r["loser_name"][:23]
            print(f"  {r['weight']:>3}  {wn:<24}  {r['v1_w_tpar']:>+9.3f}  {r['v3_w_tpar']:>+9.3f}  |  {ln:<24}  {r['v1_l_tpar']:>+9.3f}  {r['v3_l_tpar']:>+9.3f}")

    print_matches("FIXED  (v1 wrong → v3 right)", fixed,  "✓")
    print_matches("BROKEN (v1 right → v3 wrong)", broken, "✗")

    # Conference summary
    from collections import defaultdict
    conf_fixed  = defaultdict(int)
    conf_broken = defaultdict(int)
    for r in fixed:
        conf_fixed[r["winner_conf"]]  += 1
        conf_fixed[r["loser_conf"]]   += 0  # loser benefited from v1 being wrong
    for r in broken:
        conf_broken[r["winner_conf"]] += 0
        conf_broken[r["loser_conf"]]  += 1  # loser was incorrectly flipped

    all_confs = sorted(set(list(conf_fixed) + list(conf_broken)))
    print(f"\n{'='*40}")
    print("  Conference impact summary")
    print(f"{'='*40}")
    print(f"  {'Conf':<12}  {'Fixed':>6}  {'Broken':>7}")
    print(f"  {'-'*12}  {'-'*6}  {'-'*7}")
    for c in all_confs:
        f = conf_fixed.get(c, 0)
        b = conf_broken.get(c, 0)
        print(f"  {c:<12}  {f:>6}  {b:>7}")


if __name__ == "__main__":
    main()
