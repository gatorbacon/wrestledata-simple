#!/usr/bin/env python3
"""
WPA step 8 -- validation (spec Section 7).

Scores the step 5-7 model (state model + seed strength layer) on NCAA bouts it didn't see, against the spec's two
baselines (margin + time only; the state model without seeds), and writes data/wpa/reports/validation.md with
charts in data/wpa/reports/img/validation_*.png.

Held out (spec 7.1):
  * Leave one tournament out (LOTO), all 11 NCAA years: each year is scored by a state model, riding-time model,
    tie model, margin-only baseline and strength layer fitted without that year (NCAA or conference). The state
    model's out-of-fold probabilities come from fit_strength.load_oof (cached, rebuilt when stale); everything else
    is refitted here per year. For 2024-26 this is exactly TJ's E3 rotation (train on two, test on the third).
  * Forward in time (the spec's "train on earlier years, test on the most recent 2-3"): 2025 from 2015-24, 2026 from
    2015-25, and 2024 from 2015-23 -- a new-rules cold start with no E3 data at all, so 2024 states are read from
    the E12 table (what the model would have said in the first season of the 3-point takedown).
  Caveats: the hyperparameters (k, k2, row set, table variant, seed scale, N, unseeded value) were picked on these
  same held-out years in steps 5-7 -- a handful of numbers against ~550k samples, so the optimism is small but not
  zero. In the forward runs the strength layer is fitted on earlier years' out-of-fold state probabilities, whose
  state models had seen later years (it affects two parameters; negligible).

Scored unit: the 10-second samples of NCAA bouts (the opening whistle, then the centre of every 10-second bin),
both wrestlers' sides -- so every calibration table is symmetric (the 10-20% bin mirrors 80-90%); tables by slice
show the predicted favourite's side (p > 0.5). Intervals are 90% bootstrap intervals resampling BOUTS (samples within
a bout are strongly correlated; a per-sample interval would be far too narrow).

Also: the hand-checked states (7.6), the monotonicity report (7.7, incl. riding time and the strength layer), a
preliminary negative-scoring-WPA check (7.8; the full WPA is step 9), the tie model's calibration, and the era
comparison of spec Section 4.

Usage: .venv/bin/python scripts/wpa/validate.py [--reuse]   (--reuse: skip the refits, re-read the cached held-out
predictions in data/wpa/model/validation_cache.* and just redo the checks + report)
"""
import argparse
import json
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.special import expit, logit  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts/wpa"))
import fit_state_model as F  # noqa: E402
import fit_strength as S     # noqa: E402
import wp_model as W         # noqa: E402
import wpa_common as C       # noqa: E402

MODEL = ROOT / "data/wpa/model"
STATES = ROOT / "data/wpa/states"
REP = ROOT / "data/wpa/reports/validation.md"
IMG = ROOT / "data/wpa/reports/img"
CACHE_P = MODEL / "validation_cache.parquet"
CACHE_J = MODEL / "validation_cache.json"
EPS = 1e-6
B = 300
RNG = np.random.default_rng(0)
FORWARD = [2024, 2025, 2026]
COL = {"full": "#1f4e79", "e3": "#c55a11", "state": "#8a8a8a"}
DROP = 1e-4  # a "drop" = WP falling by more than 0.01 points (smaller ones are floating-point noise)
TERMINAL = {"regulation_end", "fall", "tech_fall", "injury", "dq", "overtime", "decision"}


# ---------------------------------------------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------------------------------------------
def ll(p, y):
    return F.logloss(np.asarray(p), np.asarray(y))


def br(p, y):
    return F.brier(np.asarray(p), np.asarray(y))


def pct(x, d=1):
    return f"{100 * x:.{d}f}%"


def clock(t_rem, period):
    c = int(t_rem - C.REG[int(period)][1])
    return f"P{int(period)} {c // 60}:{c % 60:02d}"


def boot_counts(n, nb=B):
    return RNG.multinomial(n, np.full(n, 1 / n), size=nb).astype(float)


def group_rates(d, g, pcols):
    """For each value of the array g: samples, bouts, mean of each prediction column, actual win rate and its 90%
    interval (bootstrap over bouts)."""
    g = np.asarray(g)
    bc, bu = pd.factorize(d["bout_key"])
    gu = np.array(sorted(pd.unique(g[pd.notna(g)])))
    gi = {v: i for i, v in enumerate(gu)}
    gc = np.array([gi.get(v, -1) for v in g])
    ok = gc >= 0
    y = d["y"].to_numpy(float)
    Yb = np.zeros((len(bu), len(gu)))
    Nb = np.zeros((len(bu), len(gu)))
    np.add.at(Yb, (bc[ok], gc[ok]), y[ok])
    np.add.at(Nb, (bc[ok], gc[ok]), 1)
    cnt = boot_counts(len(bu))
    r = (cnt @ Yb) / np.maximum(cnt @ Nb, 1)
    lo, hi = np.percentile(r, [5, 95], axis=0)
    out = pd.DataFrame({"group": gu, "samples": Nb.sum(0).astype(int), "bouts": (Nb > 0).sum(0),
                        "actual": Yb.sum(0) / np.maximum(Nb.sum(0), 1), "lo": lo, "hi": hi})
    for c in pcols:
        out[c] = pd.Series(d[c].to_numpy()[ok]).groupby(gc[ok]).mean().reindex(range(len(gu))).to_numpy()
    return out


def cal_slope(x, y, w):
    """Logistic recalibration slope, no intercept (the data are symmetric, so the intercept is 0): 1 = calibrated,
    < 1 = overconfident, > 1 = underconfident."""
    b = 1.0
    for _ in range(50):
        q = expit(b * x)
        g = np.sum(w * (y - q) * x)
        h = np.sum(w * q * (1 - q) * x * x)
        if h <= 0:
            break
        step = g / h
        b += step
        if abs(step) < 1e-7:
            break
    return b


def slope_ci(d, pcol, nb=150):
    x = logit(np.clip(d[pcol].to_numpy(), EPS, 1 - EPS))
    y = d["y"].to_numpy(float)
    b0 = cal_slope(x, y, np.ones_like(x))
    bc, bu = pd.factorize(d["bout_key"])
    cnt = boot_counts(len(bu), nb)
    bs = np.array([cal_slope(x, y, cnt[i][bc]) for i in range(nb)])
    lo, hi = np.percentile(bs, [5, 95])
    return b0, lo, hi


def deciles(d, pcol):
    t = group_rates(d, np.minimum((d[pcol].to_numpy() * 10).astype(int), 9), [pcol])
    return t.rename(columns={pcol: "pred"})


def folded(d, pcol):
    """Calibration on the predicted favourite's side: bins 50-60 ... 90-100%."""
    f = d[d[pcol] > 0.5]
    t = group_rates(f, np.minimum(((f[pcol].to_numpy() - 0.5) * 10).astype(int), 4), [pcol])
    return t.rename(columns={pcol: "pred"})


def flag(row):
    """' ▼' = prediction above the 90% interval of the actual rate (overconfident), ' ▲' = below it
    (underconfident), '' = inside."""
    if row["pred"] > row["hi"]:
        return " ▼"
    if row["pred"] < row["lo"]:
        return " ▲"
    return ""


# ---------------------------------------------------------------------------------------------------------------
# strength layer per fold
# ---------------------------------------------------------------------------------------------------------------
def fit_layer(train_rows, st_rows, ot, sp, use_e3):
    """Tie model on the fold's training moments; seed layer (same form as production) on the fold's training
    samples, whose out-of-fold state and riding-time probabilities come from the cache."""
    tie = S.fit_tie_model(train_rows)
    st_rows = st_rows.assign(p_tie=S.tie_prob(tie, st_rows))

    def rsf(d):
        return S.rank_signal(d, sp["scale"], sp["N"], sp["unseeded_equiv_seed"])
    b_ot = S.fit_beta_ot(ot, rsf)
    prm = S.fit_params(st_rows, rsf(st_rows), b_ot, e3=use_e3, form=sp.get("alpha_form", "none"))
    return {"tie": tie, "rsf": rsf, "prm": prm}


def apply_layer(L, d):
    p_tie = S.tie_prob(L["tie"], d)
    return S.predict(d.assign(p_tie=p_tie), L["rsf"](d), L["prm"]), p_tie


def ot_table(nb):
    otb = nb[(nb["went_to_ot"].astype(str) == "True") & (nb["included"] == True)]  # noqa: E712
    return pd.DataFrame({"seed_a": np.r_[otb["w_seed"], otb["l_seed"]], "seed_b": np.r_[otb["l_seed"], otb["w_seed"]],
                         "win": np.r_[np.ones(len(otb)), np.zeros(len(otb))],
                         "year": np.r_[otb["year"], otb["year"]]})


def add_seeds(d, nb):
    ws = d["bout_key"].map(nb["w_seed"]).astype(float)
    ls = d["bout_key"].map(nb["l_seed"]).astype(float)
    w = (d["persp"] == "w").to_numpy()
    d["seed_a"] = np.where(w, ws, ls)
    d["seed_b"] = np.where(w, ls, ws)
    return d


# ---------------------------------------------------------------------------------------------------------------
# held-out predictions
# ---------------------------------------------------------------------------------------------------------------
def heldout(two, nb, params, sp):
    rows = params.get("table_rows", "all")
    oof = S.load_oof(two, params)
    sm = oof[oof["source"] == "sample"].reset_index(drop=True)
    sm = add_seeds(sm, nb)
    sm["y"] = sm["win"].astype(float)
    ot = ot_table(nb)
    use_e3 = sp["e3_beta0_multiplier"] != 1.0
    years = sorted(sm["year"].unique())
    t0 = time.time()

    parts, folds = [], []
    for Y in years:
        mr = F.model_rows(two[(two["year"] != Y).to_numpy()], rows)
        te = sm[sm["year"] == Y].copy()
        L = fit_layer(mr, sm[sm["year"] != Y], ot[ot["year"] != Y], sp, use_e3)
        te["p_full"], te["p_tie"] = apply_layer(L, te)
        te["p_mo"] = F.margin_only(mr[mr["source"] == "sample"], te)
        parts.append(te)
        folds.append({"year": int(Y), **L["prm"]})
        print(f"  LOTO {Y} done ({time.time() - t0:.0f}s)", flush=True)
    hp = pd.concat(parts, ignore_index=True)

    fw = []
    for Y in FORWARD:
        tr = two[(two["year"] < Y).to_numpy()]
        mr = F.model_rows(tr, rows)
        te = sm[sm["year"] == Y].copy()
        look = W.prep(te)  # table-index columns (ti, pi, posi, chi)
        if Y == 2024:
            look["ei"] = 0  # new-rules cold start: read 2024 states from the E12 table
        look["p_state"], (pa, _, pb) = S.state_model_wp(tr, look, params, return_probs=True)
        look["p_rt_a"], look["p_rt_b"] = pa, pb
        L = fit_layer(mr, sm[sm["year"] < Y], ot[ot["year"] < Y], sp, use_e3 and Y > 2024)
        pf, _ = apply_layer(L, look)
        pmo = F.margin_only(mr[mr["source"] == "sample"], look)
        y = te["y"].to_numpy()
        h = hp[hp["year"] == Y]
        fw.append({"year": Y, "bouts": int(te["bout_key"].nunique()), "mo": ll(pmo, y), "state": ll(look["p_state"], y),
                   "full": ll(pf, y), "brier_full": br(pf, y), "loto_full": ll(h["p_full"], h["y"])})
        print(f"  forward {Y} done ({time.time() - t0:.0f}s)", flush=True)
    return hp, folds, fw


# ---------------------------------------------------------------------------------------------------------------
# checks on the production model
# ---------------------------------------------------------------------------------------------------------------
def st(margin, t, pos, choice="none", rt=0.0, era="E3", sa=np.nan, sb=np.nan, period=None):
    if period is None:
        period = 1 if t > 240 else 2 if t > 120 else 3
    return {"margin": margin, "t_rem": t, "period": period, "pos": pos, "choice": choice, "rt_diff": rt,
            "era_group": era, "seed_a": sa, "seed_b": sb}


HC_05 = "A up 1, 0:05 left, A on top, A +0:55 riding time (live)"
HC_04 = "A up 1, 0:04 left, A on top, A +0:55 riding time (out of reach)"
HC_S3 = "1 seed vs 16 seed, 1 seed down 3, 0:10 left, neutral"
HC_S3E = "  … same, equal seeds"


def hand_checks(m):
    """Spec 7.6, plus a few neighbours that make each one readable. Expected + a pass rule per row."""
    rows = [
        ("Tied, 7:00 left, neutral, equal seeds", "≈ 50%", st(0, 420, "neutral", period=1),
         lambda p: abs(p - 0.5) < 0.005),
        ("Tied, 0:30 left, A on bottom (riding time: nobody can reach 1:00)", "modestly above 50%",
         st(0, 30, "A_bottom"), lambda p: 0.5 < p < 0.7),
        ("  … same, but B has +0:45 riding time (B can still earn the point)", "(below the row above)",
         st(0, 30, "A_bottom", rt=-45.0), None),
        ("A down 1, start of period 3, A holds the choice", "close to a coin flip",
         st(-1, 120, "pending_pick", choice="A", period=3), lambda p: 0.35 < p < 0.6),
        ("  … A picks bottom", "", st(-1, 120, "A_bottom", period=3), None),
        ("  … A picks top", "", st(-1, 120, "A_top", period=3), None),
        ("  … A picks neutral", "", st(-1, 120, "neutral", period=3), None),
        ("  … same, B holds the choice", "", st(-1, 120, "pending_pick", choice="B", period=3), None),
        (HC_05, "A likely secures the point", st(1, 5, "A_top", rt=55.0), None),
        (HC_04, "noticeably different", st(1, 4, "A_top", rt=55.0), None),
        ("  tied, 0:05 left, A on top, A +0:55 (live)", "", st(0, 5, "A_top", rt=55.0), None),
        ("  tied, 0:04 left, A on top, A +0:55 (out of reach)", "", st(0, 4, "A_top", rt=55.0), None),
        ("1 seed vs 16 seed, tied, start of the match", "heavily favours the 1 seed",
         st(0, 420, "neutral", period=1, sa=1.0, sb=16.0), lambda p: p > 0.85),
        (HC_S3, "rank barely matters", st(-3, 10, "neutral", sa=1.0, sb=16.0), None),
        (HC_S3E, "", st(-3, 10, "neutral"), None),
        ("1 seed vs 16 seed, tied, 0:05 left, neutral (overtime likely)", "", st(0, 5, "neutral", sa=1.0, sb=16.0), None),
    ]
    pr = m.parts(pd.DataFrame([r[2] for r in rows]))
    out = []
    for i, (lab, exp, _, rule) in enumerate(rows):
        p = pr.iloc[i]
        out.append({"State": lab, "Expected": exp, "P(A pt)": float(p["p_rt_a"]), "P(B pt)": float(p["p_rt_b"]),
                    "WP_state": float(p["p_state"]), "WP": float(p["wp"]),
                    "ok": None if rule is None else bool(rule(float(p["wp"])))})
    by = {r["State"]: r for r in out}
    a5, a4 = by[HC_05], by[HC_04]
    a5["ok"] = bool(a5["P(A pt)"] > 0.75 and a5["WP"] > a4["WP"] + 0.005)
    a4["ok"] = bool(a4["P(A pt)"] == 0 and a5["WP"] - a4["WP"] > 0.005)
    by[HC_S3]["ok"] = bool(abs(by[HC_S3]["WP"] - by[HC_S3E]["WP"]) < 0.03 and by[HC_S3]["WP"] >= by[HC_S3E]["WP"])
    return out


def monotonicity(m):
    tab = pd.read_parquet(MODEL / "state_table.parquet")
    sh = F.shape(m.key)
    P, Pb, N = (tab[c].to_numpy().reshape(sh) for c in ("p_state", "p_blend", "n_matches"))
    adj = np.abs(P - Pb)
    res = {"cells": int(P.size), "iso_adj": int((adj > 1e-9).sum()),
           "iso_adj_data": int(((adj > 1e-9) & (N > 0)).sum()), "iso_max": float(adj.max()),
           "iso_mean": float(adj[adj > 1e-9].mean()) if (adj > 1e-9).any() else 0.0}
    # the table in the eventual riding-time point r (B's point <= none <= A's point)
    if m.key == "m_r":
        d1 = P[..., 1] - P[..., 2]
        d0 = P[..., 0] - P[..., 1]
        h1 = (N[..., 1] > 0) & (N[..., 2] > 0)
        h0 = (N[..., 0] > 0) & (N[..., 1] > 0)
        v = np.concatenate([d1.ravel(), d0.ravel()])
        h = np.concatenate([h1.ravel(), h0.ravel()])
        res.update(r_pairs=int(v.size), r_viol=int((v > 1e-6).sum()), r_viol_data=int(((v > 1e-6) & h).sum()),
                   r_viol_big=int((v > 0.02).sum()), r_max=float(v.max()))
        rv = F.release_violations(P)
        res.update(rel_pairs=int(rv.size), rel_viol=int((rv > 1e-6).sum()), rel_max=float(max(rv.max(), 0.0)))
    # WP in the riding-time differential, period 3
    g = [st(mg, t, pos, rt=float(rt), era=era) for era in ("E12", "E3") for mg in range(-3, 4)
         for t in (5, 15, 25, 35, 45, 55, 65, 85, 105) for pos in ("neutral", "A_top", "A_bottom")
         for rt in range(-119, 120)]
    gd = pd.DataFrame(g)
    live = W.rt_status_vec(gd["rt_diff"], gd["t_rem"]) == "live"
    out_rt = {}
    for lab, sa, sb in (("no seeds", np.nan, np.nan), ("A = 1 seed vs 16", 1.0, 16.0), ("A = 16 seed vs 1", 16.0, 1.0)):
        pr = m.parts(gd.assign(seed_a=sa, seed_b=sb))
        x = gd.assign(wp=pr["wp"].to_numpy(), live=live)
        grp = x.groupby(["era_group", "margin", "t_rem", "pos"], sort=False)
        dwp = grp["wp"].diff()
        prev_live = grp["live"].shift()
        both_live = x["live"] & (prev_live == True)  # noqa: E712
        drop = dwp < -DROP
        out_rt[lab] = {"steps": int(dwp.notna().sum()), "drops": int(drop.sum()),
                       "drops_live": int((drop & both_live).sum()),
                       "max_drop": float(max(0.0, -dwp.min())),
                       "worst": x.loc[dwp.idxmin(), ["era_group", "margin", "t_rem", "pos", "rt_diff"]].to_dict()
                       if drop.any() else None}
    res["rt"] = out_rt
    # final WP in margin, with the strength layer (P(tie) peaks at margin 0, so this is not automatic)
    g = []
    for t in range(5, 420, 10):
        per = 1 if t > 240 else 2 if t > 120 else 3
        combos = [("neutral", "none")] if per == 1 else \
            [(p, c) for p in ("neutral", "A_top", "A_bottom") for c in ("A", "B")] if per == 2 else \
            [(p, "none") for p in ("neutral", "A_top", "A_bottom")]
        for pos, ch in combos:
            for rt in ((0.0,) if per == 1 else (-30.0, 0.0, 30.0)):
                for mg in range(-14, 15):
                    g.append(st(mg, t, pos, choice=ch, rt=rt, era="E3", period=per))
    gd = pd.DataFrame(g)
    out_m = {}
    for lab, sa, sb in (("no seeds", np.nan, np.nan), ("A = 1 seed vs 16", 1.0, 16.0), ("A = 16 seed vs 1", 16.0, 1.0)):
        pr = m.parts(gd.assign(seed_a=sa, seed_b=sb))
        x = gd.assign(wp=pr["wp"].to_numpy())
        dwp = x.groupby(["t_rem", "pos", "choice", "rt_diff"], sort=False)["wp"].diff()
        drop = dwp < -DROP
        out_m[lab] = {"steps": int(dwp.notna().sum()), "drops": int(drop.sum()),
                      "max_drop": float(max(0.0, -dwp.min())),
                      "worst": x.loc[dwp.idxmin(), ["margin", "t_rem", "pos", "choice", "rt_diff"]].to_dict()
                      if drop.any() else None}
    res["margin"] = out_m
    # final WP in the seed advantage: every state below, A's seed 1-33 or unseeded vs B = 16 seed / unseeded
    states = [st(mg, t, pos, choice="none" if t <= 120 or t > 240 else "A", rt=0.0, era=era,
                 period=1 if t > 240 else 2 if t > 120 else 3)
              for era in ("E12", "E3") for mg in range(-5, 6) for t in (415, 245, 125, 65, 35, 15, 5)
              for pos in (("neutral",) if t > 240 else ("neutral", "A_top", "A_bottom"))]
    seeds = [float(x) for x in range(1, 34)] + [np.nan]
    g = [dict(s_, seed_a=sa, seed_b=sb, sid=i) for i, s_ in enumerate(states) for sb in (16.0, np.nan) for sa in seeds]
    gd = pd.DataFrame(g)
    pr = m.parts(gd)
    x = gd.assign(wp=pr["wp"].to_numpy(), rs=pr["rs"].to_numpy()).sort_values(["sid", "seed_b", "rs"])
    dwp = x.groupby(["sid", "seed_b"], dropna=False)["wp"].diff()
    res["rs"] = {"steps": int(dwp.notna().sum()), "drops": int((dwp < -DROP).sum()),
                 "max_drop": float(max(0.0, -dwp.min()))}
    return res


def a_frame(ev, pre, nb):
    """Events' before / after states (pre = 'b_' / 'a_') from the ACTOR's side (A = the wrestler credited)."""
    aw = (ev["actor"] == "w").to_numpy()
    sgn = np.where(aw, 1, -1)
    pos = ev[pre + "pos"].astype(str).to_numpy()
    a_top = ((pos == "w_top") & aw) | ((pos == "l_top") & ~aw)
    a_bot = ((pos == "l_top") & aw) | ((pos == "w_top") & ~aw)
    bs = ev[pre + "break_step"].fillna("").astype(str).to_numpy()
    posA = np.where(pos == "neutral", "neutral", np.where(a_top, "A_top", np.where(a_bot, "A_bottom", np.where(
        pos == "pending", np.char.add("pending_", bs.astype(str)), "unknown"))))
    ch = ev[pre + "choice"].fillna("none").astype(str).to_numpy()
    act = ev["actor"].astype(str).to_numpy()
    chA = np.where(ch == "none", "none", np.where(ch == act, "A", np.where(np.isin(ch, ["w", "l"]), "B", "unknown")))
    yr = ev["bout_key"].map(nb["year"]).to_numpy()
    ws, ls = ev["bout_key"].map(nb["w_seed"]).astype(float), ev["bout_key"].map(nb["l_seed"]).astype(float)
    return pd.DataFrame({"margin": sgn * ev[pre + "margin"].to_numpy(), "t_rem": ev[pre + "t_rem"].to_numpy(float),
                         "period": ev[pre + "period"].astype(int).to_numpy(), "pos": posA, "choice": chA,
                         "rt_diff": sgn * ev[pre + "rt_diff"].to_numpy(float),
                         "era_group": np.where(yr >= 2024, "E3", "E12"),
                         "seed_a": np.where(aw, ws, ls), "seed_b": np.where(aw, ls, ws)}, index=ev.index)


def negative_scoring(m, nb):
    ev = pd.read_csv(STATES / "ncaa_events.csv", low_memory=False)
    ok_b = set(nb.index[nb["table_ok"] == True])  # noqa: E712
    ev = ev[(ev["section"] == "reg") & (ev["points"] > 0) & ev["actor"].isin(["w", "l"]) & ev["bout_key"].isin(ok_b)
            & ~ev["event"].isin(TERMINAL) & (ev["b_t_rem"] > 0)].copy()
    bf, af = a_frame(ev, "b_", nb), a_frame(ev, "a_", nb)
    good = bf["pos"].isin(F.POS) & af["pos"].isin(F.POS) & bf["choice"].isin(F.CH) & af["choice"].isin(F.CH)
    n_skip = int((~good).sum())
    ev, bf, af = ev[good], bf[good], af[good]
    pb, pa = m.parts(bf), m.parts(af)
    term = (af["margin"] >= 15).to_numpy()  # the score ended it by tech fall: WP after = 1
    ev["wp_b"], ev["wp_a"] = pb["wp"].to_numpy(), np.where(term, 1.0, pa["wp"].to_numpy())
    ev["ps_b"], ev["ps_a"] = pb["p_state"].to_numpy(), np.where(term, 1.0, pa["p_state"].to_numpy())
    ev["wpa"], ev["wpa_state"] = ev["wp_a"] - ev["wp_b"], ev["ps_a"] - ev["ps_b"]
    ev = ev.join(bf.add_prefix("A_b_")).join(af.add_prefix("A_a_"))
    return ev, n_skip


# ---------------------------------------------------------------------------------------------------------------
# charts
# ---------------------------------------------------------------------------------------------------------------
def style(ax):
    ax.grid(alpha=0.25, lw=0.6)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def plot_calibration(series, path):
    fig, ax = plt.subplots(figsize=(6.4, 6.0), dpi=150)
    ax.plot([0, 1], [0, 1], color="#b8b8b8", lw=1, ls="--", zorder=1)
    for lab, t, color, ls_, mk in series:
        ax.errorbar(t["pred"], t["actual"], yerr=[t["actual"] - t["lo"], t["hi"] - t["actual"]], color=color, ls=ls_,
                    marker=mk, ms=4.5, lw=1.5, capsize=2, label=lab, zorder=3)
    ax.set(xlim=(0, 1), ylim=(0, 1), xlabel="Predicted win probability (10 bins)", ylabel="Actual win rate")
    ax.set_title("Held-out calibration, NCAA 10-second samples", fontsize=11)
    style(ax)
    ax.legend(frameon=False, loc="upper left", fontsize=8.5)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def plot_slices(panels, path):
    n = len(panels)
    ncol = 4
    nrow = int(np.ceil(n / ncol))
    fig, axs = plt.subplots(nrow, ncol, figsize=(12, 3.1 * nrow), dpi=130, sharex=True, sharey=True)
    for ax in axs.ravel()[n:]:
        ax.axis("off")
    for ax, (title, t) in zip(axs.ravel(), panels):
        ax.plot([0.5, 1], [0.5, 1], color="#b8b8b8", lw=1, ls="--")
        ax.errorbar(t["pred"], t["actual"], yerr=[t["actual"] - t["lo"], t["hi"] - t["actual"]], color=COL["full"],
                    marker="o", ms=3.5, lw=1.3, capsize=2)
        ax.set_title(title, fontsize=9)
        ax.set(xlim=(0.5, 1), ylim=(0.4, 1.02))
        style(ax)
    fig.supxlabel("Predicted win probability (favourite's side)", fontsize=10)
    fig.supylabel("Actual win rate", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reuse", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    params = json.loads((MODEL / "model_params.json").read_text())
    sp = json.loads((MODEL / "strength_params.json").read_text())
    bouts = pd.concat([pd.read_csv(STATES / f"{k}_bouts.csv", low_memory=False) for k in ("ncaa", "conf")],
                      ignore_index=True)
    nb = bouts[bouts["kind"] == "ncaa"].set_index("bout_key")

    if args.reuse and CACHE_P.exists():
        hp = pd.read_parquet(CACHE_P)
        cj = json.loads(CACHE_J.read_text())
        folds, fw = cj["folds"], cj["forward"]
    else:
        two, _ = F.load()
        ot_flag = bouts.set_index("bout_key")["went_to_ot"].astype(str) == "True"
        two["went_to_ot"] = two["bout_key"].map(ot_flag).fillna(False).astype(bool)
        hp, folds, fw = heldout(two, nb, params, sp)
        del two
        hp.to_parquet(CACHE_P, index=False)
        CACHE_J.write_text(json.dumps({"folds": folds, "forward": fw}, indent=1))
    print(f"held-out predictions ready ({time.time() - t0:.0f}s)", flush=True)

    m = W.WPModel()
    hp["rs"] = m.rank_signal(hp)
    e3 = hp["era_group"] == "E3"
    IMG.mkdir(parents=True, exist_ok=True)
    L = []
    A = L.append

    # ------------------------------------------------------------ 1 + 3: holdout, log loss, Brier
    def metric_row(lab, d):
        return (f"| {lab} | {d['bout_key'].nunique():,} | {ll(d['p_mo'], d['y']):.4f} | {ll(d['p_state'], d['y']):.4f} | "
                f"**{ll(d['p_full'], d['y']):.4f}** | {br(d['p_mo'], d['y']):.4f} | {br(d['p_state'], d['y']):.4f} | "
                f"**{br(d['p_full'], d['y']):.4f}** |")
    head = ("| Held-out year | Bouts | Log loss: margin + time | Log loss: state model | Log loss: **full model** | "
            "Brier: margin + time | Brier: state model | Brier: **full model** |\n|---|---:|---:|---:|---:|---:|---:|---:|")
    loto_tab = [head] + [metric_row(str(Y), hp[hp["year"] == Y]) for Y in sorted(hp["year"].unique())]
    loto_tab += [metric_row("**All 11 years**", hp), metric_row("2015–2023", hp[~e3]),
                 metric_row("**2024–2026 (TJ's rotation)**", hp[e3])]
    fw_tab = ["| Test year | Trained on | Bouts | Margin + time | State model | **Full model** | Brier, full | "
              "Same year, leave-one-out (full) |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for f in fw:
        tr = "2015–2023 (no 2024–26 data: E12 table used)" if f["year"] == 2024 else f"2015–{f['year'] - 1}"
        fw_tab.append(f"| {f['year']} | {tr} | {f['bouts']:,} | {f['mo']:.4f} | {f['state']:.4f} | **{f['full']:.4f}** | "
                      f"{f['brier_full']:.4f} | {f['loto_full']:.4f} |")

    # ------------------------------------------------------------ 2: calibration
    cal_all = deciles(hp, "p_full")
    cal_e3 = deciles(hp[e3], "p_full")
    cal_state = deciles(hp, "p_state")
    plot_calibration([("Full model, all 11 years", cal_all, COL["full"], "-", "o"),
                      ("Full model, 2024–26 only", cal_e3, COL["e3"], "-", "s"),
                      ("State model alone (no seeds), all years", cal_state, COL["state"], ":", "^")],
                     IMG / "validation_calibration.png")
    sl_all = slope_ci(hp, "p_full")
    sl_e3 = slope_ci(hp[e3], "p_full")
    sl_state = slope_ci(hp, "p_state")

    # ------------------------------------------------------------ 4: rank-gap buckets
    gap = hp["rs"].abs().to_numpy()
    med = float(np.median(gap[gap > 0]))
    hp["gap"] = np.select([gap == 0, gap <= med], ["Both unseeded", "Small seed gap"], "Big seed gap")
    ex_pairs = [(a, b) for a in range(1, 17) for b in list(range(a + 1, 34)) + [np.nan]]
    ex_rs = m.rank_signal(pd.DataFrame({"seed_a": [float(a) for a, _ in ex_pairs],
                                        "seed_b": [float(b) for _, b in ex_pairs]}))
    near = [ex_pairs[i] for i in np.argsort(np.abs(ex_rs - med))[:3]]
    fav = hp[hp["rs"] > 0]
    gap_rows = []
    for bk in ("Small seed gap", "Big seed gap"):
        d = fav[fav["gap"] == bk]
        t = group_rates(d, d["period"].to_numpy(), ["p_full", "p_state"])
        t_all = group_rates(d, np.zeros(len(d), int), ["p_full", "p_state"])
        for _, r in t.iterrows():
            gap_rows.append((bk, f"Period {int(r['group'])}", r))
        gap_rows.append((bk, "**All**", t_all.iloc[0]))
    gap_slopes = {bk: slope_ci(hp[hp["gap"] == bk], "p_full") for bk in ("Small seed gap", "Big seed gap", "Both unseeded")}
    # opening whistle: seeds are the only information
    ow = hp[(hp["t_rem"] == C.T_TOTAL) & (hp["rs"] > 0)].copy()
    edges = [0, 0.25, 0.5, 1.0, 1.5, 10]
    ow["b"] = np.digitize(ow["rs"], edges[1:-1])
    ow_t = group_rates(ow, ow["b"].to_numpy(), ["p_full"])
    ow_ex = {}
    for b_, d in ow.groupby("b"):
        pair = d.assign(sa=d["seed_a"].fillna(99), sb=d["seed_b"].fillna(99)).groupby(["sa", "sb"]).size().idxmax()
        ow_ex[b_] = " vs ".join("unseeded" if s == 99 else f"{int(s)}" for s in pair)

    # ------------------------------------------------------------ 5: period, riding-time status
    rs_ = hp["rt_status"]
    hp["rt_group"] = np.select([(rs_ == "live") & (hp["t_rem"] > 60), (rs_ == "live") & (hp["t_rem"] <= 60),
                                rs_.isin(["locked_in", "locked_out"]), rs_ == "locked_none"],
                               ["Live, more than 1:00 left", "Live, last 1:00", "Point decided (locked)",
                                "Nobody can reach 1:00"], "other")
    hp["per_group"] = "Period " + hp["period"].astype(int).astype(str)
    slices = []
    for col, order in (("per_group", ["Period 1", "Period 2", "Period 3"]),
                       ("rt_group", ["Live, more than 1:00 left", "Live, last 1:00", "Point decided (locked)",
                                     "Nobody can reach 1:00"]),
                       ("gap", ["Small seed gap", "Big seed gap", "Both unseeded"])):
        for g_ in order:
            d = hp[hp[col] == g_]
            if len(d) == 0:
                continue
            slices.append({"group": g_, "d": d, "fold": folded(d, "p_full"),
                           "slope": gap_slopes[g_] if col == "gap" else slope_ci(d, "p_full")})
    plot_slices([(f"{s['group']} ({s['d']['bout_key'].nunique():,} bouts)", s["fold"]) for s in slices],
                IMG / "validation_slices.png")
    late = hp[(hp["t_rem"] <= 60) & (hp["margin"].abs() <= 2)]
    sl_late = slope_ci(late, "p_full")

    # ------------------------------------------------------------ tie model
    tie_d = hp.assign(y=hp["went_to_ot"].astype(float))
    tie_cal = group_rates(tie_d, np.minimum((tie_d["p_tie"].to_numpy() * 10).astype(int), 9), ["p_tie"])
    tie_late = []
    for t_ in (5, 15, 25, 55):
        for pos in ("neutral", "A_top"):
            d = tie_d[(tie_d["t_rem"] == t_) & (tie_d["margin"] == 0) & (tie_d["pos"] == pos)
                      & (tie_d["rt_status"] == "locked_none")]
            if len(d) >= 20:
                tie_late.append((t_, pos, len(d), d["p_tie"].mean(), d["y"].mean()))

    # ------------------------------------------------------------ 6, 7, 8 + era comparison (production model)
    hc = hand_checks(m)
    mono = monotonicity(m)
    ev, n_skip = negative_scoring(m, nb)
    era_states = [("Up 1, 1:00 left, neutral", st(1, 60, "neutral")), ("Up 2, 1:00 left, neutral", st(2, 60, "neutral")),
                  ("Up 3, 1:00 left, neutral", st(3, 60, "neutral")),
                  ("Up 3, start of period 3, A on bottom", st(3, 120, "A_bottom", period=3)),
                  ("Up 1, 0:30 left, A on bottom", st(1, 30, "A_bottom")),
                  ("Down 2, 1:30 left, neutral", st(-2, 90, "neutral")),
                  ("Up 2, end of period 1, neutral", st(2, 245, "neutral", period=1)),
                  ("Up 4, start of period 2, A on top, B holds P3 choice", st(4, 235, "A_top", choice="B", period=2))]
    ed = pd.DataFrame([dict(s, era_group=e) for _, s in era_states for e in ("E12", "E3")])
    ew = m.parts(ed)["p_state"].to_numpy().reshape(-1, 2)

    # ------------------------------------------------------------ report
    A("# WPA step 8 — validation\n")
    A("Generated by `scripts/wpa/validate.py` (spec Section 7). Model = the step 5–6 state model (riding time "
      "factored out) + the step-7 seed layer, fitted by `fit_state_model.py` / `fit_strength.py`; one predictor for "
      "everything downstream: `scripts/wpa/wp_model.py`. Baselines (spec 7.3): **margin + time only** (logistic on "
      "margin and time left) and the **state model alone** (no seeds).\n")
    A("Scored on the 10-second samples of NCAA bouts (opening whistle, then the centre of every 10-second bin), both "
      "wrestlers' sides; log loss (guessing 50% = 0.693) and Brier score, lower is better. Intervals are 90% "
      "bootstrap intervals over bouts. Hyperparameters were chosen on these same held-out years in steps 5–7 (a "
      "handful of numbers against ~550k samples: little optimism, but not none).\n")
    A("**Changes made during this step** (each found by the validation, each re-validated here):\n")
    A("1. **Moments just before an event were biased.** Spec 3.1 puts the state just before every event into the "
      "table. A moment chosen because something is about to happen isn't a typical moment. Late in close bouts that "
      "something is usually the trailing wrestler scoring, so in the same cells leaders won 7–8 points less often "
      "at those moments than at the 10-second samples. The row set was put to a held-out test "
      f"(`state_model.md`, \"Which moments feed the model\"). Chosen: **{params.get('table_rows_desc', '')}**.")
    A("2. **The last 10 seconds were never sampled.** The old grid (420, 410 … 10 s left) sat on bin edges, so the "
      "0:00–0:09 bin was built only from event moments, half of them the biased kind. Samples now sit at bin "
      "centres (415 … 5) plus the opening whistle.")
    A("3. **The tie model** (the chance a bout is tied at the end of regulation, which carries the seed effect into "
      "overtime) put \"tied, 0:05 left, neutral, nobody can reach 1:00\" at 56% to reach overtime, against 89% in the "
      "data, and it disagreed with the riding-time model (as a favourite's riding-time lead grew, his WP could fall by "
      "up to 7 points). It now uses the state model's own split — P(tie) = Σ over the eventual riding-time point r of "
      "P(r | state) × P(tie | state, r) — on the unbiased moments, symmetrised.")
    A("4. **The riding-time model missed the knife edge.** \"A on top, 5 s left, needs all 5 to reach 1:00\": the "
      "model said 58%, the data 89–96%. It now has the share of the remaining time each wrestler must still ride, "
      "who holds the next choice and whether it's a break; it is monotone in both wrestlers' remaining need (without "
      "that, WP could fall as a riding-time lead grew); and it is exact per wrestler whenever the clock decides it (the spec's "
      "four-way status calls a state \"live\" when only one wrestler can still reach 1:00, and the model was left "
      "guessing for the other). Whether it's also monotone in margin is chosen on held-out WP (`state_model.md`): "
      "free fits the point better (a big lead often ends in a tech fall with no point), monotone keeps WP rising "
      "with the margin. "
      "**After step 9** (TJ): the trees still missed this edge (69%). A simple rate model with an exact dynamic "
      "program (`scripts/wpa/rt_hazard.py`) gets it right but gives worse WP early in bouts, so the riding-time model "
      "is now a blend: the trees until 1:30 left, a linear handoff, the rate model alone from 0:30 "
      "(`state_model.md`, \"Riding-time point model\").")
    A("5. **The table is now also monotone in the eventual riding-time point** (B's point ≤ nobody's ≤ A's point), "
      "alternated with the margin projection.")
    A("6. **The seed layer double-counted strength.** The state table already builds in that leaders are usually the "
      "better wrestler, so adding the full seed shift made evenly matched bouts overconfident (calibration slope "
      "0.80 with a small seed gap, 0.76 with both unseeded; 0.96 with a big gap). The seed layer now scales the state "
      "part, logit(WP) = α·logit(WP_state) + …, with the form of α chosen leave-one-year-out (`strength_layer.md`). "
      "The spec's form is α = 1. α never depends on the seed gap: WP must rise with the seed advantage.")
    A("7. **The table respects the release option.** The top wrestler can always let his man go, so A on top at "
      "margin m is worth at least neutral at m − 1 — and, mirrored, an escape can't lower the escaper's WP. Before, "
      "2.7% of escapes had negative WPA (largest 4.4 points). With margin monotonicity this also covers takedowns "
      "and reversals.\n")
    A("Steps 2–7 were re-run with these changes; `state_model.md` and `strength_layer.md` are current. **Before the "
      "step-8 changes** (same validation): held-out log loss 0.3967 all years / 0.4198 in 2024–26; calibration slope "
      "0.880 / 0.850; 5 of 7 hand checks; WP fell as the margin grew in 2,404 grid steps and as a riding-time lead "
      "grew in 40,548; 3.04% of scoring events lowered the scorer's WP.\n")

    A("## Summary\n")
    fa, fe = ll(hp["p_full"], hp["y"]), ll(hp[e3]["p_full"], hp[e3]["y"])
    A(f"- **Held out, all 11 NCAA years (leave one year out):** log loss {ll(hp['p_mo'], hp['y']):.3f} margin + time "
      f"→ {ll(hp['p_state'], hp['y']):.3f} state model → **{fa:.3f} full model**; 2024–26 (TJ's rotation) "
      f"{ll(hp[e3]['p_mo'], hp[e3]['y']):.3f} → {ll(hp[e3]['p_state'], hp[e3]['y']):.3f} → **{fe:.3f}**.")
    A("- **Forward in time** (trained only on earlier years): " + "; ".join(
        f"{f['year']} {f['full']:.3f} (vs {f['loto_full']:.3f} leave-one-out)" for f in fw) + ".")
    A(f"- **Calibration:** recalibration slope {sl_all[0]:.3f} (90% {sl_all[1]:.3f}–{sl_all[2]:.3f}) on all years, "
      f"{sl_e3[0]:.3f} ({sl_e3[1]:.3f}–{sl_e3[2]:.3f}) on 2024–26 (1 = calibrated, < 1 overconfident); largest "
      f"decile gap {100 * np.max(np.abs(cal_all['pred'] - cal_all['actual'])):.1f} points (all years).")
    n_ok = sum(1 for r in hc if r["ok"] is True)
    n_rule = sum(1 for r in hc if r["ok"] is not None)
    A(f"- **Hand-checked states:** {n_ok} of {n_rule} pass.")
    A(f"- **Monotonicity:** {mono['iso_adj_data']:,} table cells with data adjusted by the projections (max "
      f"{mono['iso_max']:.3f}); final WP (with seeds) falling as the margin grows: "
      f"{sum(v['drops'] for v in mono['margin'].values())} grid steps; as a riding-time lead grows: "
      f"{sum(v['drops'] for v in mono['rt'].values())}; as the seed advantage grows: {mono['rs']['drops']}.")
    neg = ev[ev["wpa"] < -1e-9]
    A(f"- **Negative scoring WPA (preliminary):** {len(neg):,} of {len(ev):,} NCAA scoring events "
      f"({100 * len(neg) / max(len(ev), 1):.2f}%) lower the scorer's WP; largest "
      f"{-ev['wpa'].min() if len(neg) else 0:.3f}.\n")

    A("## 1. Holdout by tournament year (spec 7.1) and log loss / Brier vs the baselines (7.3)\n")
    A("**Leave one tournament out.** Every model piece refitted without the held-out year (NCAA and conference). The "
      "2024–26 rows are TJ's rotation.\n")
    A("\n".join(loto_tab))
    A("\n**Forward in time** (the spec's \"train on earlier years, test on the most recent\"). 2024 is a cold start "
      "under new rules: no 2024–26 data at all, so its states are read from the 2015–23 table — what the model would "
      "have said in the first season of the 3-point takedown.\n")
    A("\n".join(fw_tab))
    A("\nStrength-layer parameters per held-out year (spread = how stable the fit is): " + ", ".join(
        f"{f['year']}: β0 {f['b0']:.2f}, γ {f['g']:.2f}, β_ot {f['b_ot']:.2f}"
        + (f", E3 × {f['e3m']:.2f}" if f["e3m"] != 1 else "")
        + (f", α {f['a0']:.2f}{f['a2']:+.2f}·elapsed" if (f["a0"], f["a2"]) != (1.0, 0.0) else "") for f in folds) + ".\n")

    A("## 2. Calibration (spec 7.2)\n")
    A("![Held-out calibration](img/validation_calibration.png)\n")
    A("Full model, leave-one-year-out, 10 equal-width bins of predicted WP (symmetric: each bin mirrors its "
      "opposite).\n")
    A("| Predicted | Samples | Bouts | Mean predicted | Actual (all years) | 90% interval | 2024–26: predicted | "
      "2024–26: actual |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|")
    ce = cal_e3.set_index("group")
    for _, r in cal_all.iterrows():
        g_ = int(r["group"])
        e_ = ce.loc[g_] if g_ in ce.index else None
        A(f"| {10 * g_}–{10 * g_ + 10}% | {int(r['samples']):,} | {int(r['bouts']):,} | {pct(r['pred'])} | "
          f"{pct(r['actual'])}{flag(r)} | {pct(r['lo'])}–{pct(r['hi'])} | "
          + (f"{pct(e_['pred'])} | {pct(e_['actual'])}{flag(e_)} |" if e_ is not None else "— | — |"))
    A("\n▼ = prediction above the 90% interval of the actual rate (overconfident there), ▲ = below (underconfident).\n")
    A(f"Recalibration slope (logistic fit of the outcome on logit WP; 1 = calibrated, < 1 = overconfident): full "
      f"model {sl_all[0]:.3f} ({sl_all[1]:.3f}–{sl_all[2]:.3f}); 2024–26 {sl_e3[0]:.3f} ({sl_e3[1]:.3f}–{sl_e3[2]:.3f}); "
      f"state model alone {sl_state[0]:.3f} ({sl_state[1]:.3f}–{sl_state[2]:.3f}). Last minute, margin within 2: "
      f"{sl_late[0]:.3f} ({sl_late[1]:.3f}–{sl_late[2]:.3f}).\n")

    A("## 4. Calibration by rank-gap bucket (spec 7.4)\n")
    A(f"Rank signal = strength(A) − strength(B) on the fitted seed scale. Small / big gap split at the median gap "
      f"among seeded matchups ({med:.2f}, about " + ", ".join(
          f"{a} vs {'unseeded' if b != b else int(b)}" for a, b in near) + "). From the favourite's side:\n")
    A("| Bucket | Phase | Bouts | Favourite's predicted WP | Actual | 90% interval | State model alone |")
    A("|---|---|---:|---:|---:|---:|---:|")
    for bk, ph, r in gap_rows:
        rr = {"pred": r["p_full"], "lo": r["lo"], "hi": r["hi"]}
        A(f"| {bk} | {ph} | {int(r['bouts']):,} | {pct(r['p_full'])} | {pct(r['actual'])}{flag(rr)} | "
          f"{pct(r['lo'])}–{pct(r['hi'])} | {pct(r['p_state'])} |")
    A("\nRecalibration slope by bucket (both sides): " + "; ".join(
        f"{k} {v[0]:.3f} ({v[1]:.3f}–{v[2]:.3f})" for k, v in gap_slopes.items()) + ". The spec's reading: "
      "big-gap bouts overconfident → β0 too high; miscalibration concentrated late → γ off.\n")
    A("**Opening whistle** — at 7:00 the state is always tied and neutral, so seeds are the only information and "
      "this is the cleanest check of β0 and the seed scale (favourite's side, one row per bout):\n")
    A("| Rank signal | Most common matchup | Bouts | Predicted | Actual | 90% interval |\n|---|---|---:|---:|---:|---:|")
    for _, r in ow_t.iterrows():
        b_ = int(r["group"])
        rr = {"pred": r["p_full"], "lo": r["lo"], "hi": r["hi"]}
        rng_ = f"{edges[b_]:.2f}+" if b_ == len(edges) - 2 else f"{edges[b_]:.2f}–{edges[b_ + 1]:.2f}"
        A(f"| {rng_} | {ow_ex.get(b_, '')} | {int(r['bouts']):,} | {pct(r['p_full'])} | {pct(r['actual'])}{flag(rr)} | "
          f"{pct(r['lo'])}–{pct(r['hi'])} |")
    A("")

    A("## 5. Calibration by period and by riding-time status (spec 7.5)\n")
    A("![Calibration by slice](img/validation_slices.png)\n")
    A("| Slice | Bouts | Samples | Log loss: margin + time | State model | **Full model** | Slope (90%) |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for s in slices:
        d = s["d"]
        A(f"| {s['group']} | {d['bout_key'].nunique():,} | {len(d):,} | {ll(d['p_mo'], d['y']):.4f} | "
          f"{ll(d['p_state'], d['y']):.4f} | **{ll(d['p_full'], d['y']):.4f}** | "
          f"{s['slope'][0]:.2f} ({s['slope'][1]:.2f}–{s['slope'][2]:.2f}) |")
    A("\nFavourite's side, predicted → actual per bin (▼ overconfident / ▲ underconfident beyond the 90% interval; "
      "bins with fewer than 30 bouts left out):\n")
    names = [s["group"] for s in slices]
    A("| Bin | " + " | ".join(names) + " |\n|---|" + "|".join("---:" for _ in names) + "|")
    for b_ in range(5):
        cells = []
        for s in slices:
            f = s["fold"].set_index("group")
            if b_ in f.index and f.loc[b_, "bouts"] >= 30:
                r = f.loc[b_]
                cells.append(f"{100 * r['pred']:.0f} → {100 * r['actual']:.0f}{flag(r)}")
            else:
                cells.append("—")
        A(f"| {50 + 10 * b_}–{60 + 10 * b_}% | " + " | ".join(cells) + " |")
    A("")

    A("## 6. Hand-checked states (spec 7.6)\n")
    A("Final model (fitted on all data), 2024–26 rules; no seeds unless stated (equal seeds = rank signal 0). "
      "P(A pt) / P(B pt) = the riding-time model's chance of each wrestler getting the point.\n")
    A("| State | Spec expects | P(A pt) | P(B pt) | WP, state | WP, with seeds | Check |\n"
      "|---|---|---:|---:|---:|---:|:---:|")
    for r in hc:
        ck = "✓" if r["ok"] is True else "✗" if r["ok"] is False else ""
        A(f"| {r['State']} | {r['Expected']} | {pct(r['P(A pt)'], 0)} | {pct(r['P(B pt)'], 0)} | "
          f"{pct(r['WP_state'])} | {pct(r['WP'])} | {ck} |")
    A("\nCheck rules: tied start within 0.5 points of 50%; tied 0:30 bottom between 50% and 70%; down 1 with the "
      "choice between 35% and 60%; 0:05 riding-time state: P(A's point) > 75% and WP above the 0:04 state; 0:04: "
      "P(A's point) = 0 (out of reach) and WP lower; 1 v 16 start > 85%; 1 seed down 3 at 0:10: seeds move WP by "
      "less than 3 points, and not below the equal-seeds value.\n")
    a5 = next(r for r in hc if r["State"] == HC_05)
    if a5["ok"]:
        A(f"The 0:05 riding-time state (A on top, needing every one of the last seconds to reach 1:00) is the thinnest "
          f"in the data: 1–5 held-out moments a year, A got the point in all of them. The step-8 trees put it anywhere "
          f"from 53% to 78% depending on the training years; the blend (the rate model alone at 0:05) gives {pct(a5['P(A pt)'], 0)} — the "
          "chance of no escape, reversal or early end in 5 seconds — which is what the data says.\n")
    else:
        A("The 0:05 riding-time state is the thinnest in the data: A on top, needing every one of the last few seconds to "
          "reach 1:00. Each held-out year has 1–5 such moments (A got the point in all of them), and refits of the "
          "riding-time model put this state anywhere from 53% to 78% depending on the training years and on whether the "
          "model is monotone in margin. Training only on moments where A's point is still undecided by the clock "
          "didn't steady it. At 69% instead of ~90%, WP is ~1 point low when A is up 1 and ~6 points low when tied. "
          "These moments are rare (a few per tournament), so this is left as a known soft spot, not tuned by hand.\n")

    A("## 7. Monotonicity (spec 3.5 / 7.7)\n")
    A(f"- **Table projections (step 6: margin, riding-time point, release option):** {mono['iso_adj']:,} of {mono['cells']:,} grid cells adjusted "
      f"({mono['iso_adj_data']:,} with data); largest change {mono['iso_max']:.3f}, mean {mono['iso_mean']:.4f}.")
    if "r_pairs" in mono:
        A(f"- **Eventual riding-time point** (the table should rank B's point ≤ none ≤ A's point in every cell): "
          f"{mono['r_viol']:,} of {mono['r_pairs']:,} adjacent pairs out of order ({mono['r_viol_data']:,} where both "
          f"cells have data; {mono['r_viol_big']:,} by more than 2 points; largest {mono['r_max']:.3f}).")
    if "rel_pairs" in mono:
        A(f"- **Release option** (A on top at m ≥ neutral at m − 1; mirrored, bottom at m ≤ neutral at m + 1): "
          f"{mono['rel_viol']:,} of {mono['rel_pairs']:,} pairs out of order, largest {mono['rel_max']:.2e}.")
    for lab, v in mono["rt"].items():
        A(f"- **WP in the riding-time differential**, period 3, {lab}: {v['steps']:,} one-second steps, "
          f"{v['drops']:,} drops ({v['drops_live']:,} with riding time live at both ends), largest "
          f"{v['max_drop']:.4f}" + (f" (at {v['worst']})" if v["worst"] else "") + ".")
    for lab, v in mono["margin"].items():
        A(f"- **Final WP in margin** (all times, positions, choices; riding time −30/0/+30), {lab}: {v['steps']:,} "
          f"steps, {v['drops']:,} drops, largest {v['max_drop']:.4f}" + (f" (at {v['worst']})" if v["worst"] else "")
          + ".")
    v = mono["rs"]
    A(f"- **Final WP in the seed advantage** (A seeded 1–33 or unseeded vs a 16 seed / an unseeded B, 77 states per "
      f"era across the match): {v['steps']:,} steps, {v['drops']:,} drops, largest {v['max_drop']:.4f}.")
    A(f"\nA drop = WP falling by more than {100 * DROP:.2f} points as the quantity grows (smaller moves are "
      "floating-point noise).\n")

    A("## 8. Negative scoring WPA (spec 6.2 / 7.8) — preliminary\n")
    A(f"Every NCAA regulation scoring event in a model-quality bout, scored with the final model from the scorer's "
      f"side (a score that reaches a 15-point margin ends the bout: WP after = 1). {len(ev):,} events"
      + (f"; {n_skip:,} skipped (position or choice unknown)" if n_skip else "") + ". The full WPA and its "
      "decomposition are step 9; this is the bug check.\n")
    A("| Event | Events | Negative (full model) | Negative (state model) | Mean WPA |\n|---|---:|---:|---:|---:|")
    for e_, d in ev.groupby("event"):
        A(f"| {e_} | {len(d):,} | {(d['wpa'] < -1e-9).sum():,} | {(d['wpa_state'] < -1e-9).sum():,} | "
          f"{d['wpa'].mean():+.3f} |")
    if len(neg):
        A("\nWorst cases:\n")
        A("| Bout | Event | Before (scorer's side) | After | WP before → after |\n|---|---|---|---|---|")
        for _, r in neg.nsmallest(12, "wpa").iterrows():
            k = r["bout_key"].split("|")
            bef = (f"{int(r['A_b_margin']):+d}, {clock(r['A_b_t_rem'], r['A_b_period'])}, {r['A_b_pos']}, "
                   f"RT {r['A_b_rt_diff']:+.0f}")
            aft = f"{int(r['A_a_margin']):+d}, {r['A_a_pos']}, RT {r['A_a_rt_diff']:+.0f}"
            A(f"| {k[2]} {k[3]} #{k[4]} | {r['raw_text']} | {bef} | {aft} | {pct(r['wp_b'])} → {pct(r['wp_a'])} |")
    A("")

    A("## Tie model (the overtime seed term)\n")
    A("Held-out (leave one year out) calibration of P(tied at the end of regulation) against whether the bout went "
      "to overtime:\n")
    A("| Predicted | Samples | Mean predicted | Actual |\n|---|---:|---:|---:|")
    for _, r in tie_cal.iterrows():
        A(f"| {10 * int(r['group'])}–{10 * int(r['group']) + 10}% | {int(r['samples']):,} | {pct(r['p_tie'])} | "
          f"{pct(r['actual'])} |")
    if tie_late:
        A("\nTied late with nobody able to reach 1:00 of riding time (the case the first version got wrong):\n")
        A("| Time left | Position | Samples | Predicted | Actual |\n|---|---|---:|---:|---:|")
        for t_, pos, n_, p_, a_ in tie_late:
            A(f"| 0:{t_:02d} | {pos} | {n_:,} | {pct(p_)} | {pct(a_)} |")
    A("")

    A("## Rules eras side by side (spec Section 4)\n")
    A("State model, no seeds. The 3-point takedown (2024–26) makes the same lead worth less.\n")
    A("| State | 2015–23 | 2024–26 | Difference |\n|---|---:|---:|---:|")
    for (lab, _), (a_, b_) in zip(era_states, ew):
        A(f"| {lab} | {pct(a_)} | {pct(b_)} | {100 * (b_ - a_):+.1f} pts |")
    A("")
    REP.write_text("\n".join(L) + "\n")
    print("wrote", REP, f"({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
