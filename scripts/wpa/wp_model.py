#!/usr/bin/env python3
"""
The fitted win-probability model (WPA steps 5-7) as one predictor, so validation (step 8) and the WPA computation
(step 9) read the model the same way.

    WP_state = sum over r in {A's point, none, B's point} of P(r | S) * T(S, r)                (fit_state_model.py)
    WP       = expit( alpha(t) * logit(WP_state) + beta0 * m_E3 * (t_rem / 420) ** gamma * rs
                      + beta_ot * P(tied at the end of regulation | S) * rs )                     (fit_strength.py)
    P(tie | S) = sum over r of P(r | S) * P(tie | S, r)   -- the same riding-time split as WP_state

rs = strength(A) - strength(B) from NCAA seeds (normal-quantile scale; unseeded = one tail value; both unseeded -> 0).

Input: A-relative REGULATION states (t_rem > 0), one per DataFrame row, with columns
    margin      A - B, excluding the pending riding-time point
    t_rem       seconds left in regulation (1-420)
    period      1-3
    pos         neutral | A_top | A_bottom | pending_pre_toss | pending_defer_option | pending_pick
    choice      A | B | none  (who holds the next period choice; see build_states.py for the timing)
    rt_diff     A's riding-time advantage in seconds
    era_group   E12 (2015-2023) | E3 (2024-2026)
    seed_a, seed_b   strength seeds (wpa_common.strength_seed; NaN = unseeded). Optional: without them rs = 0.
    kind        optional; 'conf' = a conference-tournament bout: seed_a / seed_b are then NATIONAL RANKS (step 10)
End-of-regulation and terminal states (fall, tech fall, ...) are not model states -- their value is the result.

Usage:
    m = WPModel()
    m.wp(df)          -> final WP (np.ndarray)
    m.parts(df)       -> DataFrame: p_state, p_rt_a, p_rt_none, p_rt_b, p_tie, rs, wp
"""
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts/wpa"))
import fit_state_model as F  # noqa: E402
import fit_strength as S     # noqa: E402
import wpa_common as C       # noqa: E402

MODEL = ROOT / "data/wpa/model"


def rt_status_vec(rt_diff, t_rem):
    """Vectorised wpa_common.rt_status (same tests in the same order)."""
    rt, t = np.asarray(rt_diff, float), np.asarray(t_rem, float)
    mx, mn, th = rt + t, rt - t, C.RT_THRESHOLD
    return np.select([mn >= th, mx <= -th, (mx < th) & (mn > -th)], ["locked_in", "locked_out", "locked_none"],
                     "live")


def prep(df):
    """Adds the model's index / feature columns to a frame of A-relative states."""
    d = df.copy()
    bad = ~d["pos"].isin(F.POS) | ~d["choice"].isin(F.CH)
    if bad.any():
        raise ValueError(f"{int(bad.sum())} rows with a position / choice the model doesn't know: "
                         f"{d.loc[bad, ['pos', 'choice']].drop_duplicates().values.tolist()[:5]}")
    d["ei"] = (d["era_group"] == "E3").astype(int)
    d["ti"] = (d["t_rem"] // 10).clip(upper=41).astype(int)
    d["pi"] = d["period"].astype(int) - 1
    d["posi"] = d["pos"].map({p: i for i, p in enumerate(F.POS)}).astype(int)
    d["chi"] = d["choice"].map({c: i for i, c in enumerate(F.CH)}).astype(int)
    d["posc"] = np.select([d["pos"] == "A_top", d["pos"] == "A_bottom"], [1, -1], 0)
    d["chc"] = np.select([d["choice"] == "A", d["choice"] == "B"], [1, -1], 0)
    d["rt_status"] = rt_status_vec(d["rt_diff"], d["t_rem"])
    d["rtl"] = d["rt_status"].map(F.RTL).astype(int)
    for c in ("seed_a", "seed_b"):
        if c not in d:
            d[c] = np.nan
    return d


class WPModel:
    def __init__(self, model_dir=MODEL):
        self.params = json.loads((model_dir / "model_params.json").read_text())
        self.sp = json.loads((model_dir / "strength_params.json").read_text())
        self.key = self.params["table_key"]
        tab = pd.read_parquet(model_dir / "state_table.parquet")
        self.P = tab["p_state"].to_numpy().reshape(F.shape(self.key))
        self.N = tab["n_matches"].to_numpy().reshape(F.shape(self.key))
        self.rtm = joblib.load(model_dir / "rt_model.joblib")
        self.tie = joblib.load(model_dir / "tie_model.joblib")
        sp = self.sp
        self.prm = {"b0": sp["beta0"], "g": sp["gamma"], "b_ot": sp["beta_ot"], "e3m": sp["e3_beta0_multiplier"],
                    "a0": sp.get("alpha0", 1.0), "a2": sp.get("alpha_time", 0.0)}

    def rank_signal(self, d):
        """NCAA rows: committee seeds. Rows with kind == 'conf' (conference tournaments, step 10): seed_a / seed_b hold
        NATIONAL RANKS (conf_ranks.py; NaN = unranked), on the conference scale and multiplier."""
        rs = S.rank_signal(d, self.sp["scale"], self.sp["N"], self.sp["unseeded_equiv_seed"])
        c = self.sp.get("conf")
        if c and "kind" in d:
            m = (d["kind"] == "conf").to_numpy()
            if m.any():
                rs[m] = c["rank_multiplier"] * S.rank_signal(d[m], "normal", c["N"], c["unranked_equiv_rank"])
        return rs

    def parts(self, df):
        d = prep(df)
        pa, pn, pb = F.rt_probs(self.rtm, d)
        d["p_state"] = F.wp_mixture(self.P, d, (pa, pn, pb), self.key)
        d["p_rt_a"], d["p_rt_b"] = pa, pb
        d["p_tie"] = S.tie_prob(self.tie, d)
        rs = self.rank_signal(d)
        c = self.sp.get("conf") or {}
        am = np.where((d["kind"] == "conf").to_numpy(), c.get("alpha_multiplier", 1.0), 1.0) if "kind" in d else 1.0
        wp = S.predict(d, rs, self.prm, am)
        return pd.DataFrame({"p_state": d["p_state"].to_numpy(), "p_rt_a": pa, "p_rt_none": pn, "p_rt_b": pb,
                             "p_tie": d["p_tie"].to_numpy(), "rs": rs, "wp": wp}, index=df.index)

    def wp(self, df):
        return self.parts(df)["wp"].to_numpy()
