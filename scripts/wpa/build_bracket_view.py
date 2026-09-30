#!/usr/bin/env python3
"""
WPA bracket viewer -- one NCAA weight class as a clickable bracket; clicking a bout opens its win-probability chart
(ESPN-style, like plot_wp_cards.py) and the list of every link of its WPA chain except clock time.

Everything shown comes straight from the WPA engine's outputs; nothing is re-modelled here:
  * the line        = data/wpa/output/match_wp_curves.parquet (build_outputs.py): the chain points plus the model at
                      10-second samples, winner's side, elapsed clock (regulation 0-420, SV 420-540, TB 540-600)
  * the events      = data/wpa/output/events_wpa.parquet (compute_wpa.py): every non-clock link -- scores, choices,
                      riding-time locks, cautions / warnings, terminal rows, overtime rows -- with the credited
                      wrestler's WPA; their x positions come from build_outputs.chain_points (the same mapping the
                      curve uses). Clock stretches are summed into one "clock time" number per wrestler so the list
                      still adds up to result - opening WP.
  * the bracket     = labs/bracket_viewer/data/ncaa/{year}.json (build_ncaa_bracket_data.py) for slot positions.
                      Bouts are matched to the WPA bouts by wrestler pair + score (not round: bouts file rounds can be
                      wrong for a rematch, e.g. 2026 149 Gaj-Lamer C_SF is labelled R16 there).
  * the score       = running score from each link's margin change (regulation); overtime links carry no margin, so
                      their points come from the event type. Checked against the official final score.

Usage: .venv/bin/python scripts/wpa/build_bracket_view.py --year 2026 --weight 149
Writes data/wpa/reports/bracket_{year}_{weight}.html (self-contained: open it in a browser, no server needed).
"""
import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts/wpa"))
import build_outputs as BO  # noqa: E402

OUT = ROOT / "data/wpa/output"
TEMPLATE = Path(__file__).resolve().parent / "bracket_view_template.html"
SITE = ROOT / "frontend/wrestledata-ui/public/data"
OT_PTS = {"escape": 1, "reversal": 2}                      # overtime links carry no margin
POS = {"A_top": "top", "A_bottom": "bottom", "neutral": "neutral"}


def slug(t):
    return re.sub(r"[^a-z0-9]+", "_", t.lower()).strip("_")


def team_info(t, colors, abbr):
    s = slug(t)
    c = colors.get(s, {}).get("hex") or "#111111"
    a = abbr.get(s) or "".join(w[0] for w in t.split() if w[:1].isupper())[:4] or t[:4].upper()
    return {"abbr": a, "color": c}


def rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])


def label(r, year):
    """(text, points) for one link, from the credited wrestler's side."""
    et, sub = r.event_type, r.subtype if isinstance(r.subtype, str) else ""
    d = r.margin_after - r.margin_before if pd.notna(r.margin_after) and pd.notna(r.margin_before) else np.nan
    if et == "takedown":
        return "Takedown", (3 if year >= 2024 else 2)
    if et == "escape":
        return "Escape", 1
    if et == "reversal":
        return "Reversal", 2
    if et == "near_fall":
        return f"Near fall {sub[2:]}" if sub.startswith("nf") else "Near fall", int(sub[2:]) if sub.startswith("nf") else d
    if et == "penalty":
        return ("Stalling point" if sub == "stalling" else "Penalty point") + f" → {r.beneficiary.split()[-1]}", -1
    if et == "toss":
        return "Wins the coin toss", 0
    if et == "defer":
        return "Defers the choice to P3", 0
    if et == "choose":
        return f"Chooses {POS.get(r.pos_after, r.pos_after)}", 0
    if et == "ot_choice":
        return f"Chooses {POS.get(r.pos_after, r.pos_after)} (ride {sub[-1]})", 0
    if et == "choice":
        return f"Position call: {POS.get(r.pos_after, r.pos_after)}", 0
    if et == "rt_lock":
        return ("Riding-time point locked in" if (r.rt_after or 0) >= 60 else
                "Riding-time point dead (nobody can reach 1:00)"), 0
    if et == "regulation_end":
        return ("Riding-time point" if d and d > 0 else "End of regulation"), (int(d) if d and d > 0 else 0)
    if et == "fall":
        return "Fall", 0
    if et == "tech_fall":
        return "Tech fall (reaches 15)", 0
    if et == "stalling":
        return "Stalling warning", 0
    if et == "caution":
        return "Caution", 0
    if et == "overtime":
        return "Wins in a later overtime round", 0
    return et.replace("_", " ").capitalize(), (int(d) if pd.notna(d) and d > 0 else 0)


def clock_text(x, phase):
    for ph, (x0, L) in {"P1": (0, 180), "P2": (180, 120), "P3": (300, 120), "SV1": (420, 120), "TB1": (540, 30),
                        "TB2": (570, 30)}.items():
        if phase == ph:
            rem = max(0, round(x0 + L - x))
            return f"{'SV' if ph == 'SV1' else ph} {rem // 60}:{rem % 60:02d}"
    return "Later OT" if phase == "later" else phase


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--weight", type=int, default=149)
    a = ap.parse_args()
    pre = f"ncaa|NCAA|{a.year}|{a.weight}|"
    ev = pd.read_parquet(OUT / "events_wpa.parquet")
    ev = ev[ev["bout_key"].str.startswith(pre)]
    cur = pd.read_parquet(OUT / "match_wp_curves.parquet", filters=[("bout_key", "in", list(ev["bout_key"].unique()))])
    bouts = pd.read_csv(ROOT / "data/wpa/states/ncaa_bouts.csv", low_memory=False).set_index("bout_key")
    bouts = bouts[bouts.index.str.startswith(pre)]
    colors = json.loads((SITE / "team_colors.json").read_text())["teams"]
    abbr = json.loads((SITE / "teams/abbreviations.json").read_text())
    br = json.loads((ROOT / "labs/bracket_viewer/data/ncaa" / f"{a.year}.json").read_text())
    bracket = next(b for b in br["brackets"] if str(b["id"]) == str(a.weight))

    # event x positions: the same elapsed mapping the curve uses (build_outputs.chain_points)
    o = ev.sort_values(["bout_key", "seq"]).reset_index(drop=True)
    pts = BO.chain_points(o)
    base = pts[(pts["k"] % 3 == 2)].set_index(pts.loc[pts["k"] % 3 == 2, "k"] // 3)
    o["x"] = base["elapsed_s"].reindex(o.index).to_numpy()
    o["phase"] = base["phase"].reindex(o.index).to_numpy()

    data, problems = {}, []
    for k, g in o.groupby("bout_key", sort=False):
        b = bouts.loc[k]
        wn, ln = b["w_name"], b["l_name"]
        c = cur[cur["bout_key"] == k].sort_values("order")
        sw = sl = 0
        rows, clock = [], {"w": 0.0, "l": 0.0}
        for r in g.itertuples():
            side = "w" if r.wrestler == wn else "l"
            if r.event_type == "clock":
                clock[side] += r.wpa
                continue
            text, p = label(r, a.year)
            if r.category == "overtime" and r.event_type in ("takedown", "escape", "reversal", "near_fall"):
                p = (3 if a.year >= 2024 else 2) if r.event_type == "takedown" else OT_PTS.get(r.event_type, p)
            elif r.category != "overtime" and r.event_type not in ("penalty",) and pd.notna(r.margin_after):
                d = r.margin_after - r.margin_before
                p = int(d) if d > 0 else p
            if p and p > 0:
                if side == "w":
                    sw += p
                else:
                    sl += p
            elif p and p < 0:                                    # penalty point: to the other wrestler
                if side == "w":
                    sl += -p
                else:
                    sw += -p
            rows.append({"x": round(float(r.x), 1), "t": clock_text(r.x, r.phase), "side": side, "type": r.event_type,
                         "cat": r.category, "text": text, "pts": int(p) if p else 0, "wpa": round(float(r.wpa), 5),
                         "wb": round(float(r.wp_w_before), 5), "wa": round(float(r.wp_w_after), 5),
                         "sw": sw, "sl": sl})
        if (sw, sl) != (int(b["final_w"]), int(b["final_l"])) and b["result_type"] not in ("Fall",):
            problems.append(f"{k}: running score {sw}-{sl} vs official {b['final_w']}-{b['final_l']} "
                            f"({b['result_type']})")
        wt, lt = team_info(b["w_team"], colors, abbr), team_info(b["l_team"], colors, abbr)
        if np.linalg.norm(rgb(wt["color"]) - rgb(lt["color"])) < 0.4:           # same rule as plot_wp_cards
            lt["color"] = "#8a8a8a" if rgb(wt["color"]).mean() < 0.35 else "#3a3a3a"
        sd = lambda v: int(v) if pd.notna(v) else None  # noqa: E731
        data[k] = {
            "round": b["round"], "result": f"{b['result_type']} {b['final_w']}-{b['final_l']}",
            "w": {"name": wn, "team": b["w_team"], "seed": sd(b["w_seed_raw"]), **wt},
            "l": {"name": ln, "team": b["l_team"], "seed": sd(b["l_seed_raw"]), **lt},
            "curve": [[round(float(x), 1), round(float(y), 5)] for x, y in zip(c["elapsed_s"], c["wp_w"])],
            "events": rows, "clock": {s: round(v, 5) for s, v in clock.items()},
            "open": round(float(g["wp_w_before"].iloc[0]), 5), "ot": bool(b["went_to_ot"]),
        }

    # bracket matches -> WPA bout keys (pair + score)
    def digits(s):
        return tuple(sorted(int(v) for v in re.findall(r"\d+", s.split(" ", 1)[-1])[-2:]))
    by_pair = {}
    for k in data:
        b = bouts.loc[k]
        by_pair.setdefault(frozenset((b["w_name"], b["l_name"])), []).append(k)
    matches = []
    for m in bracket["matches"]:
        ks = by_pair.get(frozenset((m["a"]["n"], m["b"]["n"])), [])
        if len(ks) > 1:
            ks = [k for k in ks if digits(m["res"]) == tuple(sorted((int(bouts.loc[k, "final_w"]),
                                                                     int(bouts.loc[k, "final_l"]))))]
        mm = {key: m[key] for key in ("id", "s", "c", "r", "y", "w", "res")}
        mm.update({"lbl": m.get("lbl"), "a": {**m["a"], "t": m["a"]["t"]}, "b": m["b"],
                   "key": ks[0] if len(ks) == 1 else None})
        matches.append(mm)
    used = [m["key"] for m in matches if m["key"]]
    assert len(used) == len(set(used)), "a WPA bout is mapped twice"
    no_pbp = [f"{m['r']} {m['a']['n']} v {m['b']['n']}" for m in matches if not m["key"]]

    payload = {"year": a.year, "weight": a.weight, "columns": br["columns"], "sections": br["sections"],
               "matches": matches, "bouts": data}
    html = TEMPLATE.read_text().replace("/*__DATA__*/null", json.dumps(payload, separators=(",", ":")))
    html = html.replace("__TITLE__", f"{a.year} NCAA {a.weight} lbs — win probability")
    out = ROOT / f"data/wpa/reports/bracket_{a.year}_{a.weight}.html"
    out.write_text(html)
    print(f"{out.relative_to(ROOT)}: {len(matches)} bracket bouts, {len(used)} with a WPA chain; "
          f"no play-by-play: {no_pbp or 'none'}")
    for p in problems:
        print("  score check:", p)


if __name__ == "__main__":
    main()
