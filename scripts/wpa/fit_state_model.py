#!/usr/bin/env python3
"""
WPA steps 5-6 -- the state model: smoothing / shrinkage of the empirical table (spec 3.3), the parametric backstop
(3.4), monotonicity (3.5), with riding time factored out of the table (TJ, 2026-09-29, after the sparsity audit).

    WP_state(S) = sum over r in {A's point, none, B's point} of  P(r | S) * T(S, r)

  * T = empirical table keyed on (era_group, current margin, t_bin, period, position, choice, r), r = the riding-time
    point actually awarded in that bout (0 if none, or if the bout ended early). Margin and r are kept APART: a first
    version pooled them (key = margin + r) and got "tied, 0:30 left, A on bottom" badly wrong -- A won 70% of E3
    bouts where nobody got the point but 17% where A was up 1 and B got it. The only assumption left: given the
    eventual point, the exact riding-time differential adds nothing. E3 cells come from E3 bouts (NCAA + conference
    -- tested against NCAA-only, which was worse on held-out NCAA bouts); E12 cells from E12 bouts.
  * Each cell is blended continuously: p_state = w * p_emp + (1 - w) * p_nb with w = n / (n + k) (n = bouts in the
    cell), and p_nb = the neighbours' pooled rate (margin +/-1, time +/-10 s, same everything else; diagonal
    neighbours at half weight) shrunk toward the backstop with strength k2:
        p_nb = (sum_i n_i * p_i + k2 * p_backstop) / (sum_i n_i + k2)
    This is the spec's 3.3 + 3.4 as one continuous blend (the spec switches to the backstop "when neighbour volume
    is below a threshold"; a pseudo-count does the same without a seam).
  * Backstop: gradient-boosted model on all eras (era as a feature), monotone increasing in margin and in r,
    symmetrised so WP(S) = 1 - WP(mirror S) exactly. (A no-intercept logistic regression on mirror-odd features was
    compared in the first run: 0.4689 vs 0.4687 held-out.)
  * Riding-time point model (replaced 2026-09-29, after step 9): a simple rate model with an exact dynamic program
    (rt_hazard.py -- per-second escape / reversal / near-fall / takedown / early-end rates and period-pick shares by
    era and by how far the wrestler concerned leads or trails; P(point) computed exactly over the rest of regulation).
    Variants (how finely the rates depend on the margin) are chosen on held-out WP; the step-8 boosted-tree classifier
    is kept as a comparison row only. Fitted on bouts whose rebuilt riding time matches the actual point.
  * Step 6: isotonic regression along margin for every (era, time, period, position, choice, r) slice.
  * Which moments feed the table and the models (ROW_SETS; added in step 8, 2026-09-29): the state just BEFORE an
    in-period event is a biased moment -- it was picked because something was about to happen, and late in close
    bouts that something is usually the trailing wrestler scoring (in the same cells, leaders won 7-8 points less
    often in those moments than at the 10-second samples in the last minute). The state just after an event and the
    break states (toss / defer / pick, where the next event is scheduled, not random) are kept. The row set is chosen
    on held-out log loss like everything else: all rows (spec 3.1 as written) vs no in-period "before" rows vs
    samples + break states only.

Validation / tuning (TJ): rotate within E3 -- train on two of 2024/2025/2026 (all E12 data is always in training),
test on the third year's NCAA bouts; all three rotations; nothing from the test year (NCAA or conference) is used in
training. Objective = log loss on the test bouts' 10-second samples, both wrestlers' sides, pooled over rotations;
k / k2, the row set, and the table variant (margin and r apart vs pooled; E3 table from NCAA + conference vs NCAA
only) are chosen by it -- the row set first (on the step-5 variant), then the table variants on that row set.

Outputs: data/wpa/model/state_table.parquet (final table: n_obs, n_matches, p_emp, p_smooth, w, p_state),
data/wpa/model/rt_params.json, data/wpa/model/backstop.joblib, data/wpa/model/model_params.json,
data/wpa/reports/state_model.md.

Usage: .venv/bin/python scripts/wpa/fit_state_model.py
"""
import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts/wpa"))
import build_table as BT  # noqa: E402
import rt_hazard as H     # noqa: E402
import wpa_common as C    # noqa: E402

TAB = ROOT / "data/wpa/table"
MODEL = ROOT / "data/wpa/model"
REP = ROOT / "data/wpa/reports/state_model.md"

ERA = ["E12", "E3"]
POS = ["neutral", "A_top", "A_bottom", "pending_pre_toss", "pending_defer_option", "pending_pick"]
CH = ["A", "B", "none"]
POS_MIR = np.array([0, 2, 1, 3, 4, 5])
CH_MIR = np.array([1, 0, 2])
M = 15
SHAPE = (2, 2 * M + 1, 42, 3, len(POS), len(CH))
TEST_YEARS = [2024, 2025, 2026]
EPS = 1e-6
RTL = {"live": 0, "locked_in": 1, "locked_out": 2, "locked_none": 3}  # riding-time lock as a category
ROW_SETS = {
    "all": "10-s samples + the state just before and just after every event (spec 3.1 as written)",
    "no_pre": "10-s samples + the state just after every event + break states; in-period 'just before' states dropped",
    "samples": "10-s samples + break states only",
}


def model_rows(d, rows):
    """The moments the table and the models are fitted on (ROW_SETS). Break states (pos pending_*) are always kept:
    they exist only at the breaks, and the event that follows them is scheduled, not a selection."""
    if rows == "all":
        return d
    brk = d["pos"].str.startswith("pending")
    if rows == "no_pre":
        return d[(d["source"] != "event_before") | brk]
    return d[(d["source"] == "sample") | brk]


# ---------------------------------------------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------------------------------------------
def load():
    ncaa = pd.read_csv(TAB / "ncaa_obs.csv.gz")
    conf = pd.read_csv(TAB / "conf_obs.csv.gz")
    obs = pd.concat([ncaa, conf], ignore_index=True)
    bad = ~obs["choice"].isin(CH) | ~obs["pos"].isin(POS)
    two = BT.both_sides(obs[~bad])
    two["ei"] = (two["era_group"] == "E3").astype(int)
    two["ti"] = two["t_bin"].astype(int)
    two["pi"] = two["period"].astype(int) - 1
    two["posi"] = two["pos"].map({p: i for i, p in enumerate(POS)}).astype(int)
    two["chi"] = two["choice"].map({c: i for i, c in enumerate(CH)}).astype(int)
    two["posc"] = np.select([two["pos"] == "A_top", two["pos"] == "A_bottom"], [1, -1], 0)
    two["chc"] = np.select([two["choice"] == "A", two["choice"] == "B"], [1, -1], 0)
    two["meff"] = (two["margin"] + two["r"]).clip(-M, M).astype(int)
    two["rtl"] = two["rt_status"].map(RTL).astype(int)
    return two, int(bad.sum())


def pre_event_bias(two):
    """How far the leader's win rate at 'just before' / 'just after' event moments sits from the 10-second samples
    in the SAME cell (era, margin, time bin, position, eventual riding-time point, lock status). Leaders up 1-3."""
    key = ["era_group", "margin", "t_bin", "pos", "r", "rt_status"]
    d0 = two[(two["margin"] > 0) & (two["margin"] <= 3)]
    out = []
    for lo, hi, lab in [(1, 2, "0:10–0:29"), (3, 6, "0:30–1:09"), (7, 12, "1:10–2:09"), (13, 41, "periods 1–2")]:
        d = d0[(d0["t_bin"] >= lo) & (d0["t_bin"] <= hi)]
        g = d.groupby(key + ["source"])["win"].agg(["mean", "size"]).unstack("source")
        row = {"Time left": lab}
        for src, name in (("event_before", "Just before an event"), ("event_after", "Just after an event")):
            both = g[[("mean", "sample"), ("mean", src), ("size", src), ("size", "sample")]].dropna()
            w = np.minimum(both[("size", src)], both[("size", "sample")])
            row[name] = float(np.average(both[("mean", src)] - both[("mean", "sample")], weights=w)) if len(w) else np.nan
        out.append(row)
    b0 = d0[d0["t_bin"] == 0]["source"].value_counts()
    return out, b0


# ---------------------------------------------------------------------------------------------------------------
# riding-time point model
# ---------------------------------------------------------------------------------------------------------------
# Since 2026-09-29 (after step 9, TJ): a BLEND. The step-8 boosted trees give the better held-out WIN probability
# (2026: 0.4634 vs 0.4651 for the best rate model) although the rate model (rt_hazard.py: per-second escape /
# reversal / near-fall / takedown / early-end rates + an exact dynamic program) predicts the point itself better
# (0.338 vs 0.350) and gets the late, fan-checkable states right (tied 2-2, 0:43 left, +1:01 riding time: trees 58%
# for the point, rate model 89%; the "must ride all of the last 5 s" knife edge). Late in the bout the two are
# equally accurate on WP (last minute 0.2250 vs 0.2242), so TJ chose: trees until 1:30 left, a linear handoff, the
# rate model alone from 0:30 -- no jump in the line at a fixed second.
RT_VARIANTS = {"hazard, era only": None, "hazard, riding-time lead": "rt", "hazard, lead 1-3 / 4-7 / 8+": "size3"}
RT_TREE = "boosted trees (step 8)"
RT_BLEND_RATE = "hazard, era only"
BLEND_T = (90, 30)   # seconds left: the handoff starts / ends
RT_BLEND = "trees, handing off to the rate model 1:30 → 0:30"
RT_DEFAULT = RT_BLEND
# step-8 trees: a_need / b_need = share of the remaining time A / B must still ride to reach 1:00; chc = who holds
# the next choice; pend = a break state; monotone in rt_diff, A on top, margin and both needs
RT_FEATS = ["rt_diff", "t_rem", "posc", "margin", "ei", "a_need", "b_need", "chc", "pend"]
RT_CST = [1, 0, 1, 1, 0, -1, 1, 0, 0]
RT_NEED = C.RT_THRESHOLD


def rt_frame(df, feats=RT_FEATS):
    """Feature matrix for A's point, and the mirrored one (B's point) -- step-8 trees only."""
    t = np.maximum(df["t_rem"].to_numpy(float), 1.0)
    rt = df["rt_diff"].to_numpy(float)
    c = {"rt_diff": rt, "t_rem": df["t_rem"].to_numpy(float), "posc": df["posc"].to_numpy(float),
         "margin": df["margin"].to_numpy(float), "ei": df["ei"].to_numpy(float),
         "a_need": np.clip((RT_NEED - rt) / t, -3, 3), "b_need": np.clip((RT_NEED + rt) / t, -3, 3),
         "chc": df["chc"].to_numpy(float), "pend": df["pos"].str.startswith("pending").to_numpy(float)}
    mir = {"rt_diff": -c["rt_diff"], "posc": -c["posc"], "margin": -c["margin"], "a_need": c["b_need"],
           "b_need": c["a_need"], "chc": -c["chc"]}
    return np.column_stack([c[f] for f in feats]), np.column_stack([mir.get(f, c[f]) for f in feats])


def make_blend(tree, rate):
    return {"kind": "blend", "tree": tree, "rate": rate, "t_hi": BLEND_T[0], "t_lo": BLEND_T[1]}


def fit_rt(train, variant=RT_DEFAULT):
    """Fitted on the training bouts whose rebuilt riding time matches the official point."""
    if variant == RT_BLEND:
        return make_blend(fit_rt(train, RT_TREE), fit_rt(train, RT_BLEND_RATE))
    d = train[train["rt_model_ok"] == True]  # noqa: E712
    if variant != RT_TREE:
        prm = H.fit(d["bout_key"].unique(), RT_VARIANTS[variant])
        prm["variant"] = variant
        return prm
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08, max_leaf_nodes=31, min_samples_leaf=200,
                                         monotonic_cst=RT_CST, random_state=0)
    clf.fit(rt_frame(d)[0], (d["r"] == 1).to_numpy(int))
    return clf


def rt_probs(model, df):
    """(pA, pN, pB) for each row. Rate model (a params dict): exact by construction. Trees: pB = the model on the
    mirrored state; exact wherever the clock decides it, per wrestler (0 when he can't reach 1:00 even riding every
    remaining second, 1 when he keeps it even if ridden every remaining second)."""
    if isinstance(model, dict) and model.get("kind") == "blend":
        ta, _, tb = rt_probs(model["tree"], df)
        ra, _, rb = rt_probs(model["rate"], df)
        w = np.clip((model["t_hi"] - df["t_rem"].to_numpy(float)) / (model["t_hi"] - model["t_lo"]), 0, 1)
        pa, pb = (1 - w) * ta + w * ra, (1 - w) * tb + w * rb
        return pa, 1 - pa - pb, pb
    if isinstance(model, dict):
        return H.probs(model, df)
    X, Xm = rt_frame(df)
    pa = model.predict_proba(X)[:, 1]
    pb = model.predict_proba(Xm)[:, 1]
    rt, t = df["rt_diff"].to_numpy(float), df["t_rem"].to_numpy(float)
    pa = np.where(rt - t >= RT_NEED, 1.0, np.where(rt + t >= RT_NEED, pa, 0.0))
    pb = np.where(rt + t <= -RT_NEED, 1.0, np.where(rt - t <= -RT_NEED, pb, 0.0))
    s = pa + pb
    scale = np.where(s > 1, 1 / np.maximum(s, EPS), 1.0)
    pa, pb = pa * scale, pb * scale
    return pa, 1 - pa - pb, pb


# ---------------------------------------------------------------------------------------------------------------
# table arrays -- axis order (era, margin, t_bin, period, pos, choice, r); r axis has 1 slot ("meff" key: margin + r
# pooled) or 3 slots ("m_r" key: current margin and the eventual point kept apart)
# ---------------------------------------------------------------------------------------------------------------
IDX = ["ei", "mi", "ti", "pi", "posi", "chi", "ri"]


def shape(key):
    return SHAPE + ((3,) if key == "m_r" else (1,))


def with_index(d, key):
    if key == "m_r":
        return d.assign(mi=d["margin"].clip(-M, M) + M, ri=d["r"] + 1)
    return d.assign(mi=d["meff"] + M, ri=0)


def table_arrays(train, key):
    d = with_index(train, key)
    g = d.groupby(IDX, observed=True)
    agg = g.agg(n_obs=("win", "size"), wins=("win", "sum"), n=("bout_key", "nunique")).reset_index()
    pm = d.groupby(IDX + ["bout_key", "persp"], observed=True)["win"].first().groupby(IDX, observed=True).mean()
    agg = agg.merge(pm.rename("pm").reset_index(), on=IDX)
    O, Wn, N, PM = (np.zeros(shape(key)) for _ in range(4))
    ix = tuple(agg[c].to_numpy() for c in IDX)
    O[ix], Wn[ix], N[ix], PM[ix] = agg["n_obs"], agg["wins"], agg["n"], agg["pm"]
    return {"O": O, "W": Wn, "N": N, "PM": PM}


def shift(a, dm, dt):
    out = np.zeros_like(a)
    sm = slice(max(dm, 0), a.shape[1] + min(dm, 0))
    st = slice(max(dt, 0), a.shape[2] + min(dt, 0))
    dm_ = slice(max(-dm, 0), a.shape[1] + min(-dm, 0))
    dt_ = slice(max(-dt, 0), a.shape[2] + min(-dt, 0))
    out[:, sm, st] = a[:, dm_, dt_]
    return out


def blend(arr, pbs, k, k2, weighting="obs"):
    N = arr["N"]
    pe = np.where(arr["O"] > 0, arr["W"] / np.maximum(arr["O"], 1), 0.0) if weighting == "obs" else arr["PM"]
    SN = np.zeros(N.shape)
    SNP = np.zeros(N.shape)
    for dm in (-1, 0, 1):
        for dt in (-1, 0, 1):
            if dm == 0 and dt == 0:
                continue
            wgt = 0.5 if (dm and dt) else 1.0
            SN += wgt * shift(N, dm, dt)
            SNP += wgt * shift(N * pe, dm, dt)
    p_nb = (SNP + k2 * pbs) / (SN + k2)
    w = N / (N + k)
    return w * pe + (1 - w) * p_nb, p_nb, w, pe


# ---------------------------------------------------------------------------------------------------------------
# backstop: gradient-boosted, monotone increasing in margin (and in the eventual riding-time point), symmetrised
# (a no-intercept logistic on mirror-odd features was also tried in the first run: 0.4689 vs 0.4687 held-out)
# ---------------------------------------------------------------------------------------------------------------
def fit_backstop(train, key):
    d = with_index(train, key)
    m = d["meff"] if key == "meff" else d["margin"]
    X = np.column_stack([m, d["t_rem"], d["pi"], d["posi"], d["chi"], d["ei"], d["ri"]])
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08, max_leaf_nodes=31, min_samples_leaf=200,
                                         monotonic_cst=[1, 0, 0, 0, 0, 0, 1],
                                         categorical_features=[False, False, True, True, True, True, False],
                                         random_state=0)
    clf.fit(X, d["win"].to_numpy())
    return clf


def grid_frame(key):
    sh = shape(key)
    e, m, t, p, po, c, r = np.meshgrid(*[np.arange(s) for s in sh], indexing="ij")
    return {"ei": e.ravel(), "m": m.ravel() - M, "ti": t.ravel(), "pi": p.ravel(), "posi": po.ravel(),
            "chi": c.ravel(), "ri": r.ravel()}


def backstop_grid(clf, key):
    g = grid_frame(key)
    t = g["ti"] * 10.0 + 5
    ri_m = (2 - g["ri"]) if key == "m_r" else g["ri"]
    X = np.column_stack([g["m"], t, g["pi"], g["posi"], g["chi"], g["ei"], g["ri"]])
    Xm = np.column_stack([-g["m"], t, g["pi"], POS_MIR[g["posi"]], CH_MIR[g["chi"]], g["ei"], ri_m])
    p = (clf.predict_proba(X)[:, 1] + 1 - clf.predict_proba(Xm)[:, 1]) / 2
    return p.reshape(shape(key))


def mirror_table(P):
    """The table seen from the other wrestler: margin reversed, positions / choice swapped, r reversed."""
    return P[:, ::-1][:, :, :, :, POS_MIR][:, :, :, :, :, CH_MIR][..., ::-1]


# ---------------------------------------------------------------------------------------------------------------
# isotonic (step 6)
# ---------------------------------------------------------------------------------------------------------------
def isotonic_margin(P, N):
    """Non-decreasing in margin within every slice (spec 3.5), weighted PAV (weights = bouts + 1)."""
    out = P.copy()
    iso = IsotonicRegression(increasing=True, y_min=0, y_max=1)
    x = np.arange(P.shape[1])
    for ix in np.ndindex(P.shape[0], *P.shape[2:]):
        sl = (ix[0], slice(None)) + ix[1:]
        y = out[sl]
        if np.all(np.diff(y) >= -1e-12):
            continue
        out[sl] = iso.fit_transform(x, y, sample_weight=N[sl] + 1)
    return out


def isotonic_r(P, N):
    """Non-decreasing in the eventual riding-time point (B's point <= none <= A's point) in every cell -- the last
    axis, 3 values; weighted pool-adjacent-violators done in closed form."""
    out = P.copy()
    w = N + 1.0
    for _ in range(2):
        for i in (0, 1):
            a, b = out[..., i], out[..., i + 1]
            bad = a > b + 1e-12
            if bad.any():
                avg = (a * w[..., i] + b * w[..., i + 1]) / (w[..., i] + w[..., i + 1])
                out[..., i] = np.where(bad, avg, a)
                out[..., i + 1] = np.where(bad, avg, b)
    return out


def isotonic_release(P, N):
    """The top wrestler can always let his man go (the bottom man is awarded an escape), so being on top at margin m
    is worth at least being in neutral at m - 1: T(neutral, m - 1) <= T(A_top, m). Its mirror -- the opponent can let
    A go -- is T(A_bottom, m) <= T(neutral, m + 1): an escape can't lower the escaper's WP. With margin monotonicity
    this also makes takedowns (neutral m -> top m + 2/3) and reversals (bottom m -> top m + 2) non-negative. Pairwise
    pooling of the violating pairs (weights = bouts + 1), same period / time / choice / riding-time point."""
    out = P.copy()
    w = N + 1.0
    i_n, i_t, i_b = POS.index("neutral"), POS.index("A_top"), POS.index("A_bottom")
    for lo_p, hi_p in ((i_n, i_t), (i_b, i_n)):  # lo cell at margin m must not exceed hi cell at margin m + 1
        lo, hi = out[:, :-1, :, :, lo_p], out[:, 1:, :, :, hi_p]
        wl, wh = w[:, :-1, :, :, lo_p], w[:, 1:, :, :, hi_p]
        bad = lo > hi + 1e-12
        if bad.any():
            avg = (lo * wl + hi * wh) / (wl + wh)
            out[:, :-1, :, :, lo_p] = np.where(bad, avg, lo)
            out[:, 1:, :, :, hi_p] = np.where(bad, avg, hi)
    return out


def release_violations(P):
    i_n, i_t, i_b = POS.index("neutral"), POS.index("A_top"), POS.index("A_bottom")
    v = np.concatenate([(P[:, :-1, :, :, lo] - P[:, 1:, :, :, hi]).ravel() for lo, hi in ((i_n, i_t), (i_b, i_n))])
    return v


def isotonic(P, N, rounds=6):
    """Step 6: monotone in margin, and (m_r table) in the eventual riding-time point and the release option, by
    alternating the projections, ending on margin; then averaged with its mirror so WP(S) = 1 - WP(mirror S) stays
    exact (every constraint set is closed under mirroring, so the average still satisfies them). Step 8 added the
    riding-time point (out-of-order cells let WP fall as a riding-time lead grew) and the release option (escapes
    with negative WPA)."""
    out = isotonic_margin(P, N)
    if P.shape[-1] == 3:
        for _ in range(rounds):
            out = isotonic_margin(isotonic_release(isotonic_r(out, N), N), N)
        out = (out + 1 - mirror_table(out)) / 2
    return out


# ---------------------------------------------------------------------------------------------------------------
# prediction for observations
# ---------------------------------------------------------------------------------------------------------------
def lookup(P, df, margins, ri):
    mi = np.clip(margins, -M, M) + M
    return P[df["ei"].to_numpy(), mi, df["ti"].to_numpy(), df["pi"].to_numpy(), df["posi"].to_numpy(),
             df["chi"].to_numpy(), ri]


def wp_mixture(P, df, probs, key):
    pa, pn, pb = probs
    m = df["margin"].to_numpy()
    if key == "m_r":
        return pa * lookup(P, df, m, 2) + pn * lookup(P, df, m, 1) + pb * lookup(P, df, m, 0)
    return pa * lookup(P, df, m + 1, 0) + pn * lookup(P, df, m, 0) + pb * lookup(P, df, m - 1, 0)


def logloss(p, y):
    p = np.clip(p, EPS, 1 - EPS)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def brier(p, y):
    return float(np.mean((p - y) ** 2))


def margin_only(train, test):
    """Spec baseline: margin and time only (current margin, no position / choice / riding time)."""
    def f(d):
        m, t = d["margin"].to_numpy(float), d["t_rem"].to_numpy(float)
        st_ = np.sqrt(t + 10.0)
        return np.column_stack([m / st_, m, m * t / 420, m / st_ * d["ei"], m * d["ei"]])
    clf = LogisticRegression(fit_intercept=False, C=10.0, max_iter=500).fit(f(train), train["win"])
    return clf.predict_proba(f(test))[:, 1]


# ---------------------------------------------------------------------------------------------------------------
def pct(a, b, d=1):
    return f"{100 * a / b:.{d}f}%" if b else "—"


VARIANTS = [("m_r", "ncaa+conf"), ("m_r", "ncaa"), ("meff", "ncaa+conf"), ("meff", "ncaa")]
K_GRID = [20, 40, 80, 160, 320]
K2_GRID = [5, 20, 80]
VLABEL = {"m_r": "margin and point kept apart", "meff": "margin + point pooled"}


def table_data(train, src):
    return train if src == "ncaa+conf" else train[train["kind"] == "ncaa"]


def main():
    t0 = time.time()
    two, n_bad = load()
    L = []
    A = L.append
    A("# WPA steps 5–6 — the state model\n")
    A("Generated by `scripts/wpa/fit_state_model.py` from the step-3 observations (`data/wpa/table/`). Design and "
      "decisions: the script's docstring and `docs/matsavant.md` (WPA section). Riding time is factored out of the "
      "table (TJ, after the sparsity audit): **WP = Σ over r ∈ {A's point, none, B's point} of P(r | state) × "
      "T(state, r)**.\n")
    nb = two.groupby("bout_key")["kind"].first()
    src_n = two["source"].value_counts()
    A(f"Observations: {len(nb):,} bouts ({(nb == 'ncaa').sum():,} NCAA, {(nb == 'conf').sum():,} conference), "
      f"{len(two):,} moments counting both sides ({src_n.get('sample', 0):,} ten-second samples, "
      f"{src_n.get('event_before', 0):,} just before an event, {src_n.get('event_after', 0):,} just after); "
      f"{n_bad:,} moments with an undetermined choice holder dropped. Samples are taken at the opening whistle and "
      "then at the centre of every 10-second bin (415, 405 … 5 s left).\n")
    bias, bin0 = pre_event_bias(two)

    scores = {}   # (key, src, rows, k, k2) -> [(ll, n)]
    rot = []
    for Y in TEST_YEARS:
        test = two[(two["year"] == Y) & (two["kind"] == "ncaa") & (two["era_group"] == "E3")]
        ts = test[test["source"] == "sample"]
        rot.append({"year": Y, "tr": (two["year"] != Y).to_numpy(), "ts": ts, "y": ts["win"].to_numpy(),
                    "n_bouts": ts["bout_key"].nunique(), "rt": {}, "fits": {}})

    def rt_for(res, rows, var=RT_DEFAULT):
        if (rows, var) not in res["rt"]:
            if var == RT_BLEND:
                rtm = make_blend(rt_for(res, rows, RT_TREE)[0], rt_for(res, rows, RT_BLEND_RATE)[0])
            else:
                rtm = fit_rt(model_rows(two[res["tr"]], rows), var)
            res["rt"][(rows, var)] = (rtm, rt_probs(rtm, res["ts"]))
        return res["rt"][(rows, var)]

    def run(key, src, rows):
        for res in rot:
            td = table_data(model_rows(two[res["tr"]], rows), src)
            arr = table_arrays(td, key)
            pbs = backstop_grid(fit_backstop(td, key), key)
            res["fits"][(key, src, rows)] = (arr, pbs)
            probs = rt_for(res, rows)[1]
            for k in K_GRID:
                for k2 in K2_GRID:
                    ll = logloss(wp_mixture(blend(arr, pbs, k, k2)[0], res["ts"], probs, key), res["y"])
                    scores.setdefault((key, src, rows, k, k2), []).append((ll, len(res["ts"])))
        print(f"variant {key} / {src} / {rows} done {time.time() - t0:.0f}s", flush=True)

    def pooled():
        return {kk: sum(a * n for a, n in v) / sum(n for _, n in v) for kk, v in scores.items()}

    # stage 1: which moments (on the step-5 table variant); stage 2: table variants on the chosen moments
    for rows in ROW_SETS:
        run("m_r", "ncaa+conf", rows)
    pl = pooled()
    best_rows = {r: min((pl[kk], kk) for kk in pl if kk[2] == r) for r in ROW_SETS}
    rows = min(best_rows.values())[1][2]
    for key_, src_ in VARIANTS[1:]:
        run(key_, src_, rows)
    pl = pooled()
    best_by_variant = {v: min((pl[kk], kk) for kk in pl if kk[:2] == v and kk[2] == rows) for v in VARIANTS}
    # the k grid is scored BEFORE the step-6 projections (too slow to project every grid point), and the projections
    # improve some variants more than others -- so variants within 0.001 of the best are scored again after them, at
    # their best k / k2, and the final choice is made on the model that is actually used (step 8: without this the
    # pooled key won by 0.0001 before projection and lost clearly after it)
    # TJ (2026-09-29): only "margin and point kept apart" is eligible. The pooled key (margin + point) won held-out
    # log loss by 0.001 in one rebuild and broke structurally (tied 0:30 on bottom -> 41%, 4.2% of scoring events
    # lowering the scorer's WP), so it is scored for the report only
    best_pre = min(v[0] for v in best_by_variant.values())
    post = {}
    for v in VARIANTS:
        if best_by_variant[v][0] > best_pre + 0.001 and v[0] != "m_r":
            continue
        kk = best_by_variant[v][1]
        tot = n = 0
        for res in rot:
            arr, pbs = res["fits"][(v[0], v[1], rows)]
            Pi_ = isotonic(blend(arr, pbs, kk[3], kk[4])[0], arr["N"])
            tot += logloss(wp_mixture(Pi_, res["ts"], rt_for(res, rows)[1], v[0]), res["y"]) * len(res["ts"])
            n += len(res["ts"])
        post[v] = tot / n
    key, src = min((v for v in post if v[0] == "m_r"), key=post.get)
    _, _, _, k, k2 = best_by_variant[(key, src)][1]
    print(f"after projections: {post}", flush=True)

    # riding-time model: the rate-model variants (and the step-8 trees for comparison), judged on held-out WP of the
    # chosen table (and on the point itself); the choice is among the rate models -- the trees are reported only
    rt_cmp = {}
    for var in [RT_BLEND, RT_TREE] + list(RT_VARIANTS):
        tot = tot_rt = n = n_rt = 0
        for res in rot:
            if "Pi" not in res:
                arr, pbs = res["fits"][(key, src, rows)]
                res["Pi"] = isotonic(blend(arr, pbs, k, k2)[0], arr["N"])
            rtm_, pr_ = rt_for(res, rows, var)
            tot += logloss(wp_mixture(res["Pi"], res["ts"], pr_, key), res["y"]) * len(res["ts"])
            n += len(res["ts"])
            tt_ = res["ts"][res["ts"]["rt_model_ok"] == True]  # noqa: E712
            tot_rt += logloss(rt_probs(rtm_, tt_)[0], (tt_["r"] == 1).to_numpy()) * len(tt_)
            n_rt += len(tt_)
        rt_cmp[var] = (tot / n, tot_rt / n_rt)
    rt_var = RT_BLEND   # TJ's choice (above); the table reports how it compares
    print(f"riding-time model: {rt_cmp} -> {rt_var}", flush=True)

    for res in rot:
        train = model_rows(two[res["tr"]], rows)
        ts = res["ts"]
        rtm, probs = rt_for(res, rows, rt_var)
        res["probs"] = probs
        tt = ts[ts["rt_model_ok"] == True]  # noqa: E712
        base = (train.loc[train["rt_model_ok"] == True, "r"] == 1).mean()  # noqa: E712
        res["rt_ll"] = logloss(rt_probs(rtm, tt)[0], (tt["r"] == 1).to_numpy())
        res["rt_base"] = logloss(np.full(len(tt), base), (tt["r"] == 1).to_numpy())
        rt1 = rt_for(res, rows, RT_TREE)[0]  # the step-8 trees, for comparison
        res["rt_ll_v1"] = logloss(rt_probs(rt1, tt)[0], (tt["r"] == 1).to_numpy())
        ko = tt[(tt["pos"] == "A_top") & (tt["t_rem"] <= 15) & (RT_NEED - tt["rt_diff"] > 0)
                & (RT_NEED - tt["rt_diff"] <= tt["t_rem"])]  # A on top, can still reach 1:00, last 15 s
        res["ride_out"] = ko.assign(p_new=rt_probs(rtm, ko)[0], p_old=rt_probs(rt1, ko)[0])
        res["margin_only"] = margin_only(train, ts)
        # riding time ignored altogether: table on current margin only, no split
        td = table_data(train, "ncaa+conf").assign(r=0)
        td["meff"] = td["margin"].clip(-M, M)
        res["ignore"] = (table_arrays(td, "meff"), backstop_grid(fit_backstop(td, "meff"), "meff"))

    comp, iso_n, preds = [], [], []
    for res in rot:
        ts, probs = res["ts"], res["probs"]
        y = ts["win"].to_numpy()
        arr, pbs = res["fits"][(key, src, rows)]
        P = blend(arr, pbs, k, k2)[0]
        Pi = isotonic(P, arr["N"])
        p = wp_mixture(Pi, ts, probs, key)
        a0, b0 = res["ignore"]
        p_ign = lookup(isotonic(blend(a0, b0, k, k2)[0], a0["N"]), ts, ts["margin"].to_numpy(), 0)
        comp.append({"Test year": str(res["year"]), "Test bouts": res["n_bouts"],
                     "Margin + time only": logloss(res["margin_only"], y),
                     "Table, riding time ignored": logloss(p_ign, y),
                     "Model before monotonicity": logloss(wp_mixture(P, ts, probs, key), y),
                     "**Model**": logloss(p, y), "Brier, model": brier(p, y)})
        iso_n.append(int((np.abs(Pi - P) > 1e-9).sum()))
        preds.append(pd.DataFrame({"p": p, "p_ign": p_ign, "p_mo": res["margin_only"], "y": y,
                                   "t_rem": ts["t_rem"].values, "margin": ts["margin"].values,
                                   "rt_status": ts["rt_status"].values, "pos": ts["pos"].values,
                                   "pa": probs[0], "r": ts["r"].values}))
    hp = pd.concat(preds, ignore_index=True)

    # ---- final fit on all data
    mr = model_rows(two, rows)
    rtm = fit_rt(mr, rt_var)
    td = table_data(mr, src)
    bs = fit_backstop(td, key)
    pbs = backstop_grid(bs, key)
    arr = table_arrays(td, key)
    P, p_nb, w, pe = blend(arr, pbs, k, k2)
    Pi = isotonic(P, arr["N"])
    adj = np.abs(Pi - P)
    sym_err = float(np.max(np.abs(Pi + mirror_table(Pi) - 1)))
    rel_before, rel_after = release_violations(P), release_violations(Pi)
    MODEL.mkdir(parents=True, exist_ok=True)
    g = grid_frame(key)
    tabdf = pd.DataFrame({"era_group": np.array(ERA)[g["ei"]], "margin": g["m"], "t_bin": g["ti"],
                          "period": g["pi"] + 1, "pos": np.array(POS)[g["posi"]], "choice": np.array(CH)[g["chi"]],
                          "rt_point": (g["ri"] - 1) if key == "m_r" else 0,
                          "n_obs": arr["O"].ravel().astype(int), "n_matches": arr["N"].ravel().astype(int),
                          "p_emp": np.where(arr["O"].ravel() > 0, (arr["W"] / np.maximum(arr["O"], 1)).ravel(), np.nan),
                          "p_emp_match": np.where(arr["O"].ravel() > 0, arr["PM"].ravel(), np.nan),
                          "p_backstop": pbs.ravel(), "p_smooth": p_nb.ravel(), "w": w.ravel(),
                          "p_blend": P.ravel(), "p_state": Pi.ravel()})
    tabdf.to_parquet(MODEL / "state_table.parquet", index=False)
    joblib.dump(rtm, MODEL / "rt_model.joblib")                            # the blend (trees + rate parameters)
    (MODEL / "rt_params.json").write_text(json.dumps(rtm["rate"], indent=1))  # the rate model, readable
    joblib.dump(bs, MODEL / "backstop.joblib")
    params = {"table_key": key, "table_data": src, "table_rows": rows, "table_rows_desc": ROW_SETS[rows],
              "k": k, "k2": k2, "p_emp_weighting": "per moment",
              "backstop": "gradient boosted, monotone in margin and riding-time point, symmetrised",
              "margin_clamp": M, "t_bin_sec": 10, "sample_times": "420, then 415, 405, ... 5 (bin centres)",
              "neighbours": "margin +/-1, t_bin +/-1, diagonal weight 0.5",
              "eras": "E12 = 2015-2023, E3 = 2024-2026", "rt_threshold_sec": C.RT_THRESHOLD,
              "rt_model": "blend: step-8 boosted trees until 1:30 left, linear handoff, rate model (rt_hazard.py, "
                          "parameters in rt_params.json) alone from 0:30; rt_model.joblib holds both",
              "rt_blend_seconds": list(BLEND_T),
              "rt_model_variant": rt_var,
              "validation": "rotate within E3: train on two of 2024-26 (+ all E12), test on the third year's NCAA bouts",
              "built": time.strftime("%Y-%m-%d")}
    (MODEL / "model_params.json").write_text(json.dumps(params, indent=2))

    # ---------------------------------------------------------------- report
    A("## Validation design\n")
    A("Rotate within E3 (TJ): train on two of 2024 / 2025 / 2026 plus all of 2015–23, test on the third year's NCAA "
      "bouts; nothing from the test year (NCAA or conference) is in training. Score = log loss on the test bouts' "
      "10-second samples from both wrestlers' sides, pooled over the three rotations (lower is better; guessing 50% "
      "scores 0.693). No strength layer yet (step 7): every number here uses the match state alone.\n")

    A("## Riding-time point model\n")
    A("**A blend (TJ, after step 9):** the step-8 boosted trees until 1:30 left in the bout, a linear handoff, and the "
      "rate model alone from 0:30. The rate model (`scripts/wpa/rt_hazard.py`): per second, the bottom man escapes "
      "(+1) or reverses (+2), the top man scores near-fall points, either wrestler takes the other down in neutral "
      "(+2, +3 from 2024), or the bout ends by fall / injury / DQ; a margin of 15 is a tech fall. Rates come from the "
      "play-by-play (events ÷ seconds in that position), by era; period picks and the toss winner's defer share the "
      "same way. An exact dynamic program over the rest of regulation (position × margin × riding-time differential, "
      "second by second) gives P(A's point), P(nobody), P(B's point) — monotone and exact at the locks by "
      "construction.\n")
    A("Why a blend: the rate model predicts the point itself better, but the trees give the better held-out WIN "
      "probability overall — every rate-model variant tried (era only, by margin, by riding-time lead) lost WP accuracy "
      "early in bouts. In the last minute the two are equally accurate on WP, and the rate model gets the late states "
      "a fan can check by hand right (tied 2-2, 0:43 left, +1:01 riding time: trees 58% for the point, rate model "
      "89%; the \"must ride all of the last 5 s\" knife edge). The gradual handoff avoids a jump in the line at a "
      "fixed second. Held-out log loss for \"does A get the point\" (blend) vs a constant base rate: "
      + ", ".join(f"{r['year']}: {r['rt_ll']:.3f} vs {r['rt_base']:.3f}" for r in rot) + ".\n")
    A("| Riding-time model | Held-out WP log loss | Held-out log loss, the point itself |\n|---|---:|---:|")
    for v_, (a_, b_) in rt_cmp.items():
        A(f"| {'**' + v_ + '** (used)' if v_ == rt_var else v_} | {a_:.4f} | {b_:.4f} |")
    A("")
    A("The knife edge the trees kept missing — A on top in the last 15 s, still able to reach 1:00 only by riding "
      "most of what's left (held out):\n")
    ko = pd.concat([r["ride_out"] for r in rot], ignore_index=True)
    ko["need"] = pd.cut((RT_NEED - ko["rt_diff"]) / ko["t_rem"], [0, 0.5, 0.8, 1.0],
                        labels=["under half", "half to 80%", "80% to all of it"])
    A("| Share of remaining time A must ride | Samples | Actual share with A's point | Step-8 trees | Blend (= rate model here) |")
    A("|---|---:|---:|---:|---:|")
    for lab, d in ko.groupby("need", observed=True):
        A(f"| {lab} | {len(d):,} | {100 * (d['r'] == 1).mean():.0f}% | {100 * d['p_old'].mean():.0f}% | "
          f"{100 * d['p_new'].mean():.0f}% |")
    hp["t_grp"] = pd.cut(hp["t_rem"], [0, 30, 60, 120, 240, 420],
                         labels=["0:01–0:30", "0:31–1:00", "1:01–2:00", "period 2", "period 1"])
    A("| Time left | Samples | Predicted share with A's point | Actual |\n|---|---:|---:|---:|")
    for grp, d in hp.groupby("t_grp", observed=True):
        A(f"| {grp} | {len(d):,} | {100 * d['pa'].mean():.1f}% | {100 * (d['r'] == 1).mean():.1f}% |")
    A("")
    A("Rate model, fitted rates (final fit, per minute of wrestling in that position):\n")
    A("| Era | Escape | Reversal | Near fall | Takedown (per wrestler) |\n|---|---:|---:|---:|---:|")
    for eg in H.ERAS:
        pe_ = rtm["rate"]["eras"][eg]
        A(f"| {eg} | " + " | ".join(f"{60 * pe_[x]['0']:.2f}" for x in ("escape", "reversal", "near_fall", "takedown"))
          + " |")
    A("\nPeriod picks, the defer share and early-end rates are in `rt_params.json`.\n")

    A("## Which moments feed the model (added in step 8)\n")
    A("Spec 3.1 builds the table from the 10-second samples plus the state just before and just after every event. "
      "Validation (step 8) found the \"just before\" moments are biased: a moment picked because something is about "
      "to happen is not a typical moment in that state. Leader's win rate at event moments minus the 10-second "
      "samples' in the same cell (era, margin, time bin, position, eventual riding-time point, lock status), leaders "
      "up 1–3:\n")
    A("| Time left | Just before an event | Just after an event |\n|---|---:|---:|")
    for b in bias:
        A(f"| {b['Time left']} | {100 * b['Just before an event']:+.1f} pts | {100 * b['Just after an event']:+.1f} pts |")
    A("\nLate in close bouts the event that is about to happen is usually the trailing wrestler scoring, so those "
      "moments understate the leader. The old sample grid (420, 410 … 10) also never sampled the last 10 seconds, so "
      "that bin was built from event moments only — about half of them \"just before\". Samples now sit at the centre "
      f"of every bin (the last bin now has {int(bin0.get('sample', 0)):,} sample moments with a leader up 1–3), and "
      "the row set is chosen on held-out log loss (break states — toss, defer, pick — are always kept: they only exist "
      "at the breaks and what follows them is scheduled, not a selection):\n")
    A("| Moments used | Best k | Best k2 | Held-out log loss |\n|---|---:|---:|---:|")
    for r_ in ROW_SETS:
        ll, kk = best_rows[r_]
        A(f"| {ROW_SETS[r_]} | {kk[3]} | {kk[4]} | {ll:.4f} |")
    A(f"\n**Chosen:** {ROW_SETS[rows]}. The same moments train the riding-time model, the backstop and (step 7) the "
      "tie model.\n")

    A("## Table design: which variant\n")
    A("First run keyed the table on margin + eventual riding-time point pooled. That fails: tied with 0:30 left and A "
      "on bottom, A won 70% of E3 bouts where nobody got the point (21 bouts) but 17% where A was up 1 and B got the "
      "point (11) — pooling those as 'effectively tied' gave 49%. Keeping current margin and the point apart makes the "
      "split exact up to one assumption (given the eventual point, the exact riding-time differential adds nothing). "
      "Conference E3 leads also held a little more often than NCAA E3 leads (up 1 in neutral, last minute: 86% vs 81%), "
      "so conference-in vs NCAA-only was tested too. Best pooled held-out log loss per variant (on the chosen "
      "moments):\n")
    A("| Table key | Table data | Best k | Best k2 | Log loss (before the step-6 projections) | After them |\n"
      "|---|---|---:|---:|---:|---:|")
    for v in VARIANTS:
        ll, kk = best_by_variant[v]
        A(f"| {VLABEL[v[0]]} | {v[1]} | {kk[3]} | {kk[4]} | {ll:.4f} | "
          + (f"{post[v]:.4f}" if v in post else "—") + " |")
    A("\nThe k grid is scored before the projections (too slow to project every grid point); variants within 0.001 "
      "of the best are scored again after them and the choice is made there, on the model actually used.")
    A(f"\n**Chosen:** {VLABEL[key]}, table from {src}, k = {k} (bouts at which a cell is half its own data), "
      f"k2 = {k2} (pseudo-bouts of backstop in the neighbour estimate).\n")

    A("## Held-out results by test year\n")
    cols = list(comp[0])
    A("| " + " | ".join(cols) + " |\n|" + "|".join("---:" for _ in cols) + "|")
    for c in comp:
        A("| " + " | ".join(f"{v:.4f}" if isinstance(v, float) else (f"{v:,}" if isinstance(v, int) else v)
                            for v in c.values()) + " |")
    A("")

    A("## Where it matters: slices of the held-out samples\n")
    A("| Slice | Samples | Margin + time only | Table, riding time ignored | Model |\n|---|---:|---:|---:|---:|")
    sl = [("All", hp["t_rem"] > 0), ("Period 3, within 3", (hp["t_rem"] <= 120) & (hp["margin"].abs() <= 3)),
          ("Last 30 s, within 2", (hp["t_rem"] <= 30) & (hp["margin"].abs() <= 2)),
          ("Riding time live, last 60 s", (hp["t_rem"] <= 60) & (hp["rt_status"] == "live")),
          ("Riding time live, last 60 s, margin within 1",
           (hp["t_rem"] <= 60) & (hp["rt_status"] == "live") & (hp["margin"].abs() <= 1))]
    for lab, s_ in sl:
        d = hp[s_]
        A(f"| {lab} | {len(d):,} | {logloss(d['p_mo'], d['y']):.4f} | {logloss(d['p_ign'], d['y']):.4f} | "
          f"{logloss(d['p'], d['y']):.4f} |")
    A("")

    def calib(d, edges):
        d = d.assign(b=pd.cut(d["p"], edges, include_lowest=True))
        out = ["| Predicted | Samples | Mean predicted | Actual win rate |", "|---|---:|---:|---:|"]
        for b, x in d.groupby("b", observed=True):
            out.append(f"| {b} | {len(x):,} | {100 * x['p'].mean():.1f}% | {100 * x['y'].mean():.1f}% |")
        return "\n".join(out)
    A("## Calibration (held-out)\n")
    A("Whole held-out set, deciles of predicted win probability:\n")
    A(calib(hp, np.linspace(0, 1, 11)))
    A("\nThe independence check — riding time still live, 60 s or less left (where riding it out and the opponent "
      "escaping are the same event):\n")
    A(calib(hp[(hp["t_rem"] <= 60) & (hp["rt_status"] == "live")], [0, .1, .3, .5, .7, .9, 1]))
    A("")

    A("## Final table (fitted on all data)\n")
    live = arr["N"] > 0
    A(f"- Cells with data: {int(live.sum()):,}.")
    d = with_index(td, key)
    ow = w[d["ei"].to_numpy(), d["mi"].to_numpy(), d["ti"].to_numpy(), d["pi"].to_numpy(), d["posi"].to_numpy(),
           d["chi"].to_numpy(), d["ri"].to_numpy()]
    e3 = (d["ei"] == 1).to_numpy()
    A(f"- Share of observed moments whose cell leans mostly on its own data (w ≥ 0.5): all {pct((ow >= .5).sum(), len(ow))}, "
      f"E3 {pct((ow[e3] >= .5).sum(), e3.sum())}.")
    A(f"- **Monotonicity (step 6):** {int((adj > 1e-9).sum()):,} of {adj.size:,} grid cells adjusted "
      f"({int(((adj > 1e-9) & live).sum()):,} of them cells with data); largest change {adj.max():.3f}, mean change "
      f"among adjusted {adj[adj > 1e-9].mean() if (adj > 1e-9).any() else 0:.4f}. Held-out rotations: "
      + ", ".join(f"{n:,}" for n in iso_n) + " cells adjusted; effect on held-out log loss in the table above.")
    A(f"- **Release option (step 8):** before the projection {int((rel_before > 1e-9).sum()):,} (neutral m − 1, top m) "
      f"/ (bottom m, neutral m + 1) pairs out of order, largest {rel_before.max():.3f}; after: "
      f"{int((rel_after > 1e-6).sum()):,} above 0.000001, largest {max(rel_after.max(), 0):.2e}.")
    A(f"- Symmetry: max |WP(S) + WP(mirror S) − 1| over the whole table = {sym_err:.2e}.")
    A("- Files: `data/wpa/model/state_table.parquet` (every cell: `n_obs`, `n_matches`, `p_emp`, `p_emp_match`, "
      "`p_backstop`, `p_smooth` = neighbours + backstop, `w`, `p_blend`, `p_state` = after monotonicity; `rt_point` = "
      "the eventual riding-time point the cell is conditioned on), `rt_model.joblib` (the blend), `rt_params.json` (its rate model), `backstop.joblib`, "
      "`model_params.json`.\n")

    A("## A few states (final model, no strength layer)\n")
    ex = [("Tied, 7:00 left", 0, 420, 1, "neutral", 0.0, "E3"),
          ("Tied, 0:30 left, A on bottom", 0, 30, 3, "A_bottom", 0.0, "E3"),
          ("Down 1, start of P3, A on bottom", -1, 120, 3, "A_bottom", 0.0, "E3"),
          ("Up 1, 0:05 left, A on top, A +55 s riding", 1, 5, 3, "A_top", 55.0, "E3"),
          ("Up 1, 0:04 left, A on top, A +55 s riding", 1, 4, 3, "A_top", 55.0, "E3"),
          ("Tied, 0:05 left, A on top, A +55 s riding", 0, 5, 3, "A_top", 55.0, "E3"),
          ("Tied, 0:04 left, A on top, A +55 s riding", 0, 4, 3, "A_top", 55.0, "E3"),
          ("Up 2, 1:00 left, neutral", 2, 60, 3, "neutral", 0.0, "E12"),
          ("Up 2, 1:00 left, neutral", 2, 60, 3, "neutral", 0.0, "E3")]
    A("| State | Era | P(A point) | P(B point) | WP |\n|---|---|---:|---:|---:|")
    for lab, mg, t, per, pos, rt, era in ex:
        df = pd.DataFrame([{"rt_diff": rt, "t_rem": t, "posc": 1 if pos == "A_top" else -1 if pos == "A_bottom" else 0,
                            "margin": mg, "ei": 1 if era == "E3" else 0, "rt_status": C.rt_status(rt, t), "pos": pos,
                            "chc": 0, "ti": min(41, t // 10), "pi": per - 1, "posi": POS.index(pos),
                            "chi": CH.index("none")}])
        pr = rt_probs(rtm, df)
        A(f"| {lab} | {era} | {100 * pr[0][0]:.0f}% | {100 * pr[2][0]:.0f}% | "
          f"{100 * wp_mixture(Pi, df, pr, key)[0]:.1f}% |")
    A("\n(Step 8 runs the spec's full list of hand-checked states, with the strength layer.)\n")
    REP.write_text("\n".join(L) + "\n")
    print("wrote", REP, f"({time.time() - t0:.0f}s)", "chosen", key, src, rows, k, k2)


if __name__ == "__main__":
    main()
