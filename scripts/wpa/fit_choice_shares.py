#!/usr/bin/env python3
"""
How often wrestlers make each period choice -- the weights that tie the break states together (TJ, 2026-09-30).

Why: the break states (before the period-2 toss, toss winner deciding, a wrestler about to pick) used to be their own
state-table cells, each fitted on ~100-200 bouts per margin with nothing tying them to each other or to the states the
choice leads to. Result: winning a coin toss could be worth -2 points (down 2) or +1.6 (down 1), and picking the
option nearly everyone picks could show -0.4. wp_model.WPModel now values every break state from the regulation
states it leads to, weighted by these shares:

    V(X about to pick, period p) = sum over o of share_p(o | X's margin) * V(X took o; P2: the other wrestler holds the P3 choice)
    V(H won the toss)             = defer(H's margin) * V(other wrestler about to pick P2)
                                    + (1 - defer(H's margin)) * V(H about to pick P2)
    V(before the toss)            = 1/2 * V(A won the toss) + 1/2 * V(B won the toss)

So a toss is worth half the gap between holding and not holding the choice, and a choice's WPA is how much better or
worse the option taken is than the options wrestlers in that spot actually take, on average.

Shares: every recorded period-2 / period-3 pick and every toss (NCAA + conference, all bouts with a choice column),
by rules era (E12 2015-23, E3 2024-26), period and margin from the chooser's side (clipped to -6..6), shrunk toward the
era x period share with K pseudo-bouts.

Usage: .venv/bin/python scripts/wpa/fit_choice_shares.py   (seconds; reads data/wpa/states/{ncaa,conf}_events.csv)
Writes data/wpa/model/choice_shares.json (tracked) and prints the table.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
STATES = ROOT / "data/wpa/states"
OUT = ROOT / "data/wpa/model/choice_shares.json"
K = 20.0
MARGINS = list(range(-6, 7))
OPTS = ["bottom", "top", "neutral"]


def load():
    parts = []
    for kind in ("ncaa", "conf"):
        e = pd.read_csv(STATES / f"{kind}_events.csv", low_memory=False,
                        usecols=["bout_key", "seq", "event", "actor", "b_margin", "b_period", "a_pos"])
        parts.append(e[e["event"].isin(["toss", "defer", "choose"])])
    e = pd.concat(parts, ignore_index=True)
    e = e[e["actor"].isin(["w", "l"])].copy()
    e["year"] = e["bout_key"].str.split("|").str[2].astype(int)
    e["era"] = np.where(e["year"] >= 2024, "E3", "E12")
    e["m"] = np.where(e["actor"] == "w", e["b_margin"], -e["b_margin"]).clip(-6, 6).astype(int)
    e["period"] = pd.to_numeric(e["b_period"], errors="coerce")
    return e


def shrunk(counts, prior):
    """counts: DataFrame margin x option; prior: Series option -> share. Returns margin -> {option: share}."""
    out = {}
    for m in MARGINS:
        c = counts.loc[m] if m in counts.index else pd.Series(0.0, index=prior.index)
        s = (c.reindex(prior.index, fill_value=0) + K * prior) / (c.sum() + K)
        out[str(m)] = {k: round(float(v), 4) for k, v in s.items()}
    return out


def main():
    e = load()
    ch = e[e["event"] == "choose"].copy()
    top = ((ch["a_pos"] == "w_top") & (ch["actor"] == "w")) | ((ch["a_pos"] == "l_top") & (ch["actor"] == "l"))
    bot = ((ch["a_pos"] == "w_top") & (ch["actor"] == "l")) | ((ch["a_pos"] == "l_top") & (ch["actor"] == "w"))
    ch["opt"] = np.select([bot, top, ch["a_pos"] == "neutral"], OPTS, "")
    ch = ch[(ch["opt"] != "") & ch["period"].isin([2, 3])]
    toss = e[e["event"] == "toss"].copy()
    deferred = set(zip(e.loc[e["event"] == "defer", "bout_key"], e.loc[e["event"] == "defer", "actor"]))
    toss["opt"] = np.where([(k, a) in deferred for k, a in zip(toss["bout_key"], toss["actor"])], "defer", "choose")
    res = {"_note": __doc__.strip().split("\n\n")[2], "K": K, "margin_range": [MARGINS[0], MARGINS[-1]]}
    for era, g in ch.groupby("era"):
        res[era] = {"pick": {}, "counts": {}}
        for p, gp in g.groupby("period"):
            cnt = gp.groupby(["m", "opt"]).size().unstack(fill_value=0).reindex(columns=OPTS, fill_value=0)
            prior = cnt.sum() / cnt.values.sum()
            res[era]["pick"][str(int(p))] = shrunk(cnt, prior)
            res[era]["counts"][f"pick_p{int(p)}"] = int(cnt.values.sum())
        t = toss[toss["era"] == era]
        cnt = t.groupby(["m", "opt"]).size().unstack(fill_value=0).reindex(columns=["defer", "choose"], fill_value=0)
        prior = cnt.sum() / cnt.values.sum()
        res[era]["defer"] = {m: v["defer"] for m, v in shrunk(cnt, prior).items()}
        res[era]["counts"]["toss"] = int(cnt.values.sum())
    OUT.write_text(json.dumps(res, indent=1))
    for era in ("E12", "E3"):
        print(era, res[era]["counts"])
        print("  defer share by toss winner's margin:", {m: round(v, 2) for m, v in res[era]["defer"].items()})
        for p in ("2", "3"):
            print(f"  P{p} bottom share by margin:", {m: round(v["bottom"], 2) for m, v in res[era]["pick"][p].items()})
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
