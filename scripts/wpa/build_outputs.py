#!/usr/bin/env python3
"""
WPA step 11 -- the spec's final outputs (Section 8) in data/wpa/output/:

  state_table.parquet     copy of data/wpa/model/state_table.parquet (every cell: n_obs, n_matches, p_emp, p_smooth, w,
                          p_state, plus p_emp_match / p_backstop / p_blend; keyed on era_group, margin, t_bin, period,
                          pos, choice, rt_point = the eventual riding-time point -- see docs/matsavant.md, WPA section)
  model_params.json       every fitted parameter in one file: state model (model_params.json), riding-time rate model
                          (rt_params.json), strength layer incl. the conference scale (strength_params.json) and the
                          overtime model (ot_params.json), each under its own key, as fitted
  events_wpa.parquet      (compute_wpa.py) one row per link of each bout's WP chain
  wrestler_wpa.csv        (compute_wpa.py) per wrestler per tournament
  match_wp_curves.parquet WP over time for every bout in the chain, for charting (this script):
      bout_key, kind, tournament, year, weight, round, w_name, l_name, source ('chain' = a point of the WPA chain,
      'sample' = the model at a 10-second sample), elapsed_s (regulation 0-420; overtime on the same clock: sudden
      victory 420-540, tiebreaker ride 1 540-570, ride 2 570-600, later rounds at 600; before 2022 overtime is one
      60-second block 420-480), phase (P1 / P2 / P3 / SV1 / TB1 / TB2 / later / OT), event_type (chain points),
      wp_w (the bout winner's WP), order (sort key within the bout). A score / choice is two chain points at the same
      elapsed_s (before and after) so a step plot draws a jump. Samples fill in the curve inside long clock stretches
      (the chain only has the stretch's ends and riding-time locks); samples after a bout ended are dropped.

Run after compute_wpa.py. Usage: .venv/bin/python scripts/wpa/build_outputs.py   (~1 min)
The parquet outputs are gitignored (rebuild); model_params.json is tracked.
"""
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts/wpa"))
import compute_wpa as CW  # noqa: E402
import wp_model as W  # noqa: E402

MODEL = ROOT / "data/wpa/model"
OUT = ROOT / "data/wpa/output"
STATES = ROOT / "data/wpa/states"
OTX = {"SV1": (420, 120), "TB1": (540, 30), "TB2": (570, 30)}


def params():
    out = {"_note": "Merged by scripts/wpa/build_outputs.py from data/wpa/model/*_params.json; each block as fitted. "
                    "Meaning of every parameter: docs/matsavant.md (WPA section) and the fitting scripts' docstrings."}
    for key, f in (("state_model", "model_params.json"), ("riding_time_rate_model", "rt_params.json"),
                   ("strength_layer", "strength_params.json"), ("overtime_model", "ot_params.json")):
        out[key] = json.loads((MODEL / f).read_text())
    (OUT / "model_params.json").write_text(json.dumps(out, indent=1))


def chain_points(o):
    """Chain points on the elapsed clock (winner's side)."""
    o = o.sort_values(["bout_key", "seq"]).reset_index(drop=True)
    ot = (o["category"] == "overtime").to_numpy()
    new = o["year"].to_numpy() >= 2022
    sub = o["subtype"].astype(str).to_numpy()
    t = o["t_after"].to_numpy(float)
    el = 420.0 - t
    for ph, (x0, L) in OTX.items():
        m_ = ot & new & (sub == ph)
        el[m_] = x0 + L - t[m_]
    el[ot & new & ~np.isin(sub, list(OTX))] = 600.0
    el[ot & ~new] = 480.0
    per = o["period"].to_numpy(float)
    phase = np.where(ot & new & np.isin(sub, list(OTX)), sub,
                     np.where(ot & new, "later", np.where(ot, "OT", np.char.add("P", np.nan_to_num(per).astype(int)
                                                                                .astype(str)))))
    # a clock link that ends at a period break / regulation end has period NaN? keep the previous row's phase then
    phase = pd.Series(phase).replace("P0", np.nan).ffill().fillna("P1")
    # a row's period is the state BEFORE it; a clock stretch's end point belongs to the link it leads into
    nxt = phase.groupby(o["bout_key"].to_numpy()).shift(-1)
    phase = np.where((o["event_type"] == "clock").to_numpy() & nxt.notna().to_numpy(), nxt, phase)
    base = pd.DataFrame({"bout_key": o["bout_key"], "elapsed_s": el, "phase": phase, "event_type": o["event_type"],
                         "wp_w": o["wp_w_after"].to_numpy(), "k": o.index.to_numpy() * 3 + 2})
    jump = o["event_type"] != "clock"
    before = base[jump].assign(wp_w=o.loc[jump, "wp_w_before"].to_numpy(), k=lambda d: d["k"] - 1,
                               event_type=lambda d: d["event_type"] + ":before")
    first = o.groupby("bout_key").head(1)
    start = pd.DataFrame({"bout_key": first["bout_key"], "elapsed_s": 0.0, "phase": "P1", "event_type": "start",
                          "wp_w": first["wp_w_before"].to_numpy(), "k": first.index.to_numpy() * 3})
    pts = pd.concat([start, before, base], ignore_index=True)
    # a pre-2022 overtime starts where regulation ended: its first "before" point sits at 420
    pre = pts["phase"].eq("OT") & pts["event_type"].str.endswith(":before")
    firstpre = pts[pre].sort_values("k").groupby("bout_key").head(1).index
    pts.loc[firstpre, "elapsed_s"] = 420.0
    return pts.assign(source="chain")


def sample_points(nb, chain_bouts, end_el):
    m = W.WPModel()
    parts = []
    for kind in ("ncaa", "conf"):
        s = pd.read_csv(STATES / f"{kind}_samples.csv", low_memory=False)
        s = s[s["bout_key"].isin(chain_bouts)].reset_index(drop=True)
        ev = s.rename(columns={c: "b_" + c for c in s.columns if c != "bout_key"})
        X = CW.w_states(ev, "b_", nb)
        ok = CW.modelable(X, np.full(len(X), "reg"))
        X = X[ok]
        wp = CW.wp_of(m, X)
        d = s.loc[ok, ["bout_key", "t_rem", "period"]].assign(wp_w=wp)
        d["elapsed_s"] = 420.0 - d["t_rem"]
        d["phase"] = "P" + d["period"].astype(int).astype(str)
        parts.append(d)
    d = pd.concat(parts, ignore_index=True)
    d = d[d["elapsed_s"] < d["bout_key"].map(end_el)]
    return d.assign(source="sample", event_type="")[["bout_key", "elapsed_s", "phase", "event_type", "wp_w", "source"]]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(MODEL / "state_table.parquet", OUT / "state_table.parquet")
    params()
    o = pd.read_parquet(OUT / "events_wpa.parquet")
    nb = pd.concat([CW.load_bouts(k)[0] for k in ("ncaa", "conf")])
    ch = chain_points(o)
    reg = ch[ch["phase"].str.startswith("P")]
    end_el = reg.groupby("bout_key")["elapsed_s"].max()
    went_ot = o[o["category"] == "overtime"]["bout_key"].unique()
    end_el.loc[end_el.index.isin(went_ot)] = 420.0
    sm = sample_points(nb, set(o["bout_key"]), end_el)
    # order: chain points keep their chain order; a sample at the same second as an event is the state after it, so it goes last
    ch = ch.sort_values(["bout_key", "k"])
    ch["order"] = ch.groupby("bout_key").cumcount().astype(float)
    sm = sm.sort_values(["bout_key", "elapsed_s"])
    sm["order"] = np.nan
    cur = pd.concat([ch.drop(columns="k"), sm], ignore_index=True)
    cur = cur.sort_values(["bout_key", "elapsed_s", "order"], na_position="last", kind="stable")
    # re-index order after merging: stable sort by time keeps the chain's order among equal times
    cur["order"] = cur.groupby("bout_key").cumcount()
    info = nb[["kind", "tournament", "year", "weight", "round", "w_name", "l_name"]]
    cur = cur.join(info, on="bout_key")
    cols = ["bout_key", "kind", "tournament", "year", "weight", "round", "w_name", "l_name", "source", "elapsed_s",
            "phase", "event_type", "wp_w", "order"]
    cur[cols].to_parquet(OUT / "match_wp_curves.parquet", index=False)
    # checks: every bout ends at 1; chain points reproduce events_wpa
    last = cur.groupby("bout_key").tail(1)
    print(f"match_wp_curves: {len(cur):,} points, {cur['bout_key'].nunique():,} bouts "
          f"({(cur['source'] == 'sample').sum():,} samples); last point = 1 in {np.mean(last['wp_w'] > 1 - 1e-9):.4f}; "
          f"non-decreasing time within bouts: "
          f"{(cur.groupby('bout_key')['elapsed_s'].diff().fillna(0) >= -1e-9).mean():.4f}")
    print(f"wrote {OUT}/state_table.parquet, model_params.json, match_wp_curves.parquet")


if __name__ == "__main__":
    main()
