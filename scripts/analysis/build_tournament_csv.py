"""
Builds a CSV of every 2026 NCAA tournament match with:
  weight, round, result_type,
  winner_name, winner_team, winner_conf, winner_seed, winner_tpar_v1, winner_tpar_v3b,
  loser_name,  loser_team,  loser_conf,  loser_seed,  loser_tpar_v1,  loser_tpar_v3b
"""

import csv, glob, json, pathlib, re, unicodedata

SEASON       = 2026
FRONTEND_DIR = "frontend/wrestledata-ui/public/data"
NCAA_DATE    = "03/21/2026"
OUT_PATH     = f"data/{SEASON}/ncaa-tourney/tournament_matches_{SEASON}.csv"

CONF_EVENT_MAP = {
    "Big Ten": "Big Ten", "ACC": "ACC", "Big 12": "Big 12",
    "Ivy League": "CAA", "MAC Wrestling": "MAC",
    "Southern Conference": "SoCon", "EIWA": "EIWA",
    "PAC-12": "Pac-12", "Pac-12": "Pac-12",
    "Colonial": "CAA", "CAA": "CAA", "SoCon": "SoCon",
}


def norm(name):
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", name.strip().lower())


def norm_team(team):
    """Normalize team name for matching across data sources."""
    return team.strip().lower().replace(" and ", " & ")


def build_tpar(path):
    with open(path) as f:
        raw = json.load(f)
    out = {}
    for wid, matches in raw.items():
        reg = [m["mv_impact"] for m in matches if m["date"] != NCAA_DATE]
        if reg:
            out[wid] = sum(reg) / len(reg)
    return out


def main():
    # Wrestler index
    with open(f"{FRONTEND_DIR}/wrestlers/{SEASON}/index_wrestlers.json") as f:
        index = json.load(f)
    by_name_wt = {(norm(w["name"]), int(w["weight_class"])): w["wrestler_id"] for w in index}
    wrestler_team = {w["wrestler_id"]: w["team"] for w in index}

    # Conference lookup from conference championship events
    # Keyed by norm_team(team_name) to handle "Franklin and Marshall" vs "Franklin & Marshall"
    team_conf_norm = {}
    for fpath in glob.glob(f"{FRONTEND_DIR}/wrestlers/{SEASON}/by_id/*.json"):
        with open(fpath) as f:
            d = json.load(f)
        team = d.get("team")
        if not team:
            continue
        for m in d.get("match_list", []):
            event = m.get("event", "")
            if "championship" not in event.lower():
                continue
            for kw, conf in CONF_EVENT_MAP.items():
                if kw.lower() in event.lower():
                    team_conf_norm[norm_team(team)] = conf
                    break

    def get_conf(team_name):
        return team_conf_norm.get(norm_team(team_name), "")

    # TPAR scores
    tpar_v1  = build_tpar(f"{FRONTEND_DIR}/mat_value/{SEASON}/match_mv_impact_{SEASON}.json")
    tpar_v3b = build_tpar(f"{FRONTEND_DIR}/mat_value/{SEASON}/match_mv_impact_v3b_{SEASON}.json")

    # Tournament matches
    with open(f"data/{SEASON}/ncaa-tourney/parsed/matches.json") as f:
        tourney = json.load(f)

    rows = []
    skipped = 0
    for m in tourney:
        wt = int(m["weight"])
        w_id = by_name_wt.get((norm(m["winner_name"]), wt))
        l_id = by_name_wt.get((norm(m["loser_name"]),  wt))

        w_conf = get_conf(m.get("winner_team", ""))
        l_conf = get_conf(m.get("loser_team",  ""))

        def fmt(v):
            return f"{v:.4f}" if v is not None else ""

        rows.append({
            "weight":         wt,
            "round":          m.get("round", ""),
            "result_type":    m.get("result_type", ""),
            "winner_name":    m["winner_name"],
            "winner_team":    m.get("winner_team", ""),
            "winner_conf":    w_conf,
            "winner_seed":    m.get("winner_seed", ""),
            "winner_tpar_v1":  fmt(tpar_v1.get(w_id))  if w_id else "",
            "winner_tpar_v3b": fmt(tpar_v3b.get(w_id)) if w_id else "",
            "loser_name":     m["loser_name"],
            "loser_team":     m.get("loser_team", ""),
            "loser_conf":     l_conf,
            "loser_seed":     m.get("loser_seed", ""),
            "loser_tpar_v1":  fmt(tpar_v1.get(l_id))  if l_id else "",
            "loser_tpar_v3b": fmt(tpar_v3b.get(l_id)) if l_id else "",
        })

    # Sort by weight, then round order
    ROUND_ORDER = {
        "First Round": 1, "Round of 64": 1,
        "Second Round": 2, "Round of 32": 2,
        "Quarterfinals": 3,
        "Semifinals": 4,
        "Championship": 5,
        "Third Place": 6,
        "Fifth Place": 7,
        "Seventh Place": 8,
        "Consolation Round of 32": 9,
        "Consolation Quarterfinals": 10,
        "Consolation Semifinals": 11,
        "Consolation": 12,
    }
    rows.sort(key=lambda r: (r["weight"], ROUND_ORDER.get(r["round"], 99)))

    pathlib.Path(OUT_PATH).parent.mkdir(parents=True, exist_ok=True)
    cols = [
        "weight", "round", "result_type",
        "winner_name", "winner_team", "winner_conf", "winner_seed", "winner_tpar_v1", "winner_tpar_v3b",
        "loser_name",  "loser_team",  "loser_conf",  "loser_seed",  "loser_tpar_v1",  "loser_tpar_v3b",
    ]
    with open(OUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} matches to {OUT_PATH}")

    # Quick sanity: how many have TPAR data for both sides?
    both = sum(1 for r in rows if r["winner_tpar_v1"] and r["loser_tpar_v1"])
    neither = sum(1 for r in rows if not r["winner_tpar_v1"] and not r["loser_tpar_v1"])
    missing_conf = sum(1 for r in rows if not r["winner_conf"] or not r["loser_conf"])
    print(f"  Both sides have v1 TPAR:  {both}/{len(rows)}")
    print(f"  Missing TPAR both sides:  {neither}")
    print(f"  Missing a conference:     {missing_conf}")

    # Preview first few rows
    print(f"\n{'='*120}")
    print("  Sample rows (first 5):")
    print(f"{'='*120}")
    for r in rows[:5]:
        print(f"  {r['weight']:>3} | {r['round']:<30} | {r['winner_name']:<22} ({r['winner_conf']:<8} #{r['winner_seed']}) "
              f"v1={r['winner_tpar_v1']:>7} | {r['loser_name']:<22} ({r['loser_conf']:<8} #{r['loser_seed']}) "
              f"v1={r['loser_tpar_v1']:>7}")

    # Rounds present
    from collections import Counter
    round_counts = Counter(r["round"] for r in rows)
    print(f"\n  Rounds in data:")
    for rnd, cnt in sorted(round_counts.items(), key=lambda x: ROUND_ORDER.get(x[0], 99)):
        print(f"    {rnd:<35} {cnt:>4}")


if __name__ == "__main__":
    main()
