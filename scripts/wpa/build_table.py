#!/usr/bin/env python3
"""
WPA step 3 -- empirical state table (spec 3.1) with mirrored perspectives (spec 2.1).

Reads the step-2 states (data/wpa/states/, built by build_states.py) for bouts with table_ok and turns every
observed moment into two observations -- one from each wrestler's side, the second the mirror of the first with the
outcome flipped -- keyed by the spec's state tuple:

    era_group  E12 (2015-2023, TJ decision D: E1 pooled with E2) | E3 (2024-2026, the anchor)
    margin     A minus B, excluding the pending riding-time point, clamped to +/-15
    t_bin      10-second bins of regulation time left (0-41)
    period     1 / 2 / 3
    pos        neutral | A_top | A_bottom | pending_<step> (the P1/P2 and P2/P3 breaks: pre_toss, defer_option, pick)
    choice     A | B | none -- who holds the next period choice (none throughout period 1: the toss is at P2 start)
    rt_status  live | locked_in | locked_out | locked_none (wpa_common.rt_status)
    rt_bin     riding-time differential in 10-s bins, +/-6 -- only while rt_status = live (0 otherwise: once the point
               is locked the exact differential no longer matters)

Observations (spec 3.1): the state every 10 s of regulation (fixed cadence, so quiet stretches count) plus the state
before and after every regulation event. Not included: end-of-regulation states (t_rem 0 -- terminal, value set by
the result / overtime), tech-fall states (|margin| >= 15, terminal), and the instant before a fall / injury default
(sampled only because the bout ended there).

Outputs (data/wpa/table/):
  {name}_obs.csv.gz     one row per observation from the WINNER's side (mirror on load) -- step 5 needs the raw
                        observations for held-out tuning
  {name}_table.csv      one row per cell: n_obs, n_matches (distinct bouts), wins, p_emp = wins / n_obs, and
                        p_emp_match (each bout weighted once per cell, the spec's guard against long scoreless
                        bouts dominating a cell)
Names: ncaa (NCAA clean bouts), conf (conference clean bouts).

Each observation also carries `r`: the riding-time point actually awarded in that bout, from A's side (+1 A, -1 B, 0
none -- including bouts that ended early). After the sparsity audit riding time was factored out of the table (TJ,
2026-09-29): step 5 keys the table on margin + r and models r separately (fit_state_model.py). `rt_model_ok` marks
bouts whose rebuilt riding time matches the actual point (usable for fitting that model). The step-4 audit was run
on the earlier state_table_ok filter (slightly fewer bouts); rerunning it now gives marginally different numbers.

Usage: .venv/bin/python scripts/wpa/build_table.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts/wpa"))
import wpa_common as C  # noqa: E402

STATES = ROOT / "data/wpa/states"
OUT = ROOT / "data/wpa/table"
KEY = ["era_group", "margin", "t_bin", "period", "pos", "choice", "rt_status", "rt_bin"]
TERMINAL_EVENTS = {"regulation_end", "fall", "tech_fall", "injury", "dq"}


def load_obs(kind):
    """Winner-side observations for bouts with state_table_ok."""
    bouts = pd.read_csv(STATES / f"{kind}_bouts.csv", low_memory=False)
    ok = bouts[bouts["table_ok"] == True].copy()  # noqa: E712
    ok["r"] = ok["rt_point_logged"].map({"w": 1, "l": -1}).fillna(0).astype(int)
    meta = ok.set_index("bout_key")[["year", "era", "tournament", "weight", "r", "rt_model_ok"]]

    s = pd.read_csv(STATES / f"{kind}_samples.csv")
    s = s[s["bout_key"].isin(meta.index)].copy()
    s["source"] = "sample"

    e = pd.read_csv(STATES / f"{kind}_events.csv", low_memory=False)
    e = e[e["bout_key"].isin(meta.index) & (e["section"] == "reg") & ~e["event"].isin(TERMINAL_EVENTS)]
    cols = ["t_rem", "period", "margin", "pos", "choice", "break_step", "rt_diff", "rt_status"]
    parts = [s[["bout_key", "source"] + cols]]
    for pre, src in (("b_", "event_before"), ("a_", "event_after")):
        x = e[["bout_key"] + [pre + c for c in cols]].rename(columns={pre + c: c for c in cols})
        x["source"] = src
        x["event"] = e["event"].values
        parts.append(x)
    obs = pd.concat(parts, ignore_index=True)
    obs = obs.join(meta, on="bout_key")
    obs = obs[(obs["t_rem"] > 0) & (obs["margin"].abs() < 15)].copy()

    obs["era_group"] = np.where(obs["era"] == "E3", "E3", "E12")
    obs["t_bin"] = (obs["t_rem"] // 10).clip(upper=41).astype(int)
    obs["period"] = obs["period"].astype(int)
    obs["break_step"] = obs["break_step"].fillna("")
    obs["pos"] = np.where(obs["pos"] == "pending", "pending_" + obs["break_step"], obs["pos"])
    obs["pos"] = obs["pos"].replace({"w_top": "A_top", "l_top": "A_bottom"})
    obs["choice"] = obs["choice"].replace({"w": "A", "l": "B"})
    b = (obs["rt_diff"].abs() // 10).clip(upper=C.RT_BIN_CLAMP).astype(int)
    obs["rt_bin"] = np.where(obs["rt_status"] == "live", np.sign(obs["rt_diff"]).astype(int) * b, 0)
    obs["margin"] = obs["margin"].astype(int)
    obs["kind"] = kind
    return obs[["bout_key", "kind", "tournament", "year", "weight", "era", "source"] + KEY
               + ["rt_diff", "t_rem", "r", "rt_model_ok"]]


def both_sides(obs):
    """Winner rows (A = winner, win = 1) plus mirrored loser rows (win = 0)."""
    a = obs.copy()
    a["persp"], a["win"] = "w", 1
    m = obs.copy()
    m["persp"], m["win"] = "l", 0
    m["margin"] = -m["margin"]
    m["pos"] = m["pos"].replace({"A_top": "A_bottom", "A_bottom": "A_top"})
    m["choice"] = m["choice"].replace({"A": "B", "B": "A"})
    m["rt_status"] = m["rt_status"].replace({"locked_in": "locked_out", "locked_out": "locked_in"})
    m["rt_bin"] = -m["rt_bin"]
    m["rt_diff"] = -m["rt_diff"]
    if "r" in m:
        m["r"] = -m["r"]
    return pd.concat([a, m], ignore_index=True)


def aggregate(two, key=KEY):
    g = two.groupby(key, observed=True)
    t = g.agg(n_obs=("win", "size"), wins=("win", "sum"), n_matches=("bout_key", "nunique")).reset_index()
    t["p_emp"] = t["wins"] / t["n_obs"]
    pm = two.groupby(key + ["bout_key", "persp"], observed=True)["win"].first().groupby(key, observed=True).mean()
    t = t.merge(pm.rename("p_emp_match").reset_index(), on=key)
    return t


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for kind in ("ncaa", "conf"):
        obs = load_obs(kind)
        obs.to_csv(OUT / f"{kind}_obs.csv.gz", index=False)
        tab = aggregate(both_sides(obs))
        tab.to_csv(OUT / f"{kind}_table.csv", index=False)
        print(f"{kind}: {obs['bout_key'].nunique():,} bouts, {len(obs):,} observations (x2 mirrored), "
              f"{len(tab):,} cells")


if __name__ == "__main__":
    main()
