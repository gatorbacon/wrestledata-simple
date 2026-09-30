#!/usr/bin/env python3
"""
WPA step 7 -- strength layer on NCAA seeds (spec Section 5), revised in step 8.

    logit(WP) = alpha(rs) * logit(WP_state) + beta(t) * rs + beta_ot * P(tied at the end of regulation | state) * rs
    beta(t)   = beta0 * (t_rem / 420) ** gamma          (x an E3 multiplier for 2024-26, decision 5)
    alpha(t)  = a0 + a2 * (1 - t_rem / 420)             (step 8; the spec's form is alpha = 1)

  * WP_state: the step 5-6 state model (fit_state_model.py), computed OUT OF FOLD -- each NCAA year's states are
    scored by a state model built without that year (NCAA or conference), so the seed effect isn't fitted against
    probabilities that have already seen the result. Cached in data/wpa/model/ncaa_oof_state.parquet (+ .json with the
    settings it was built with; rebuilt automatically when stale, or with --refresh; ~6 min). The cache also keeps each
    row's out-of-fold riding-time probabilities (p_rt_a / p_rt_b), which the tie model needs.
  * rs = rank signal = strength(A) - strength(B), from NCAA committee seeds. Two scales (spec 5.2): log-rank,
    strength = -log(seed); normal quantile, strength = -Phi^-1((seed - 0.5) / N). Unseeded wrestlers (2015-2018 seeds
    17-33, which were a random draw -- decision C) get one tail value, an "equivalent seed" R_tail. Unseeded vs
    unseeded -> 0. N and R_tail are tuned on held-out log loss.
  * Overtime (TJ decision 6): a tie at the end of regulation is worth the overtime win rate, and the seed effect in
    overtime is fitted on all NCAA overtime bouts (beta_ot, logistic on rs, no intercept). The spec's fading beta(t)
    reaches 0 at the buzzer, so on its own a tie at 0:00 would carry no seed effect into overtime; the extra term
    carries it in proportion to the chance the bout is still headed for overtime. That chance uses the SAME split as
    the state model: P(tie | S) = sum over r of P(r | S) * P(tie | S, r), with P(r | S) from the riding-time model and
    P(tie | S, r) a small boosted model on (margin, time, position, era, break state, r), symmetrised. (Step 8: the
    first version, a separate model on the riding-time differential, disagreed with the riding-time model -- it put
    a tie with 0:05 left in neutral at 56% to reach overtime against 89% in the data, and made WP fall as a
    favourite's riding-time lead grew.)
  * alpha (step 8): the state table is learned from all bouts, where the wrestler who leads is usually the better
    one -- so "up 3" already carries an average strength edge, and adding the seed shift on top double-counts it.
    Held out, the spec's form was overconfident in evenly matched bouts (calibration slope ~0.8) but not in big-gap
    bouts (~0.96). alpha shrinks the state part; three forms (none = spec, one constant, changing with the clock) are
    compared leave-one-year-out and the data picks. alpha never depends on rs: a form that did (a0 + a1*(1 - e^-|rs|))
    fitted marginally better (0.3930 vs 0.3933) but let a better seed LOWER WP in a losing position (1 seed down 3 at
    0:10: 4.9% vs 7.5% with equal seeds), so WP must stay increasing in rs -- it does whenever alpha is free of rs.
  * Fitting: maximum likelihood on the 10-second samples. Validation: leave one NCAA tournament (= year) out;
    scale / N / R_tail chosen with the spec's form, then the alpha form, then whether E3 wants its own beta0.

Outputs: data/wpa/model/strength_params.json, tie_model.joblib, data/wpa/reports/strength_layer.md.
Usage: .venv/bin/python scripts/wpa/fit_strength.py [--refresh]
"""
import argparse
import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.optimize import minimize, minimize_scalar
from scipy.special import expit, logit
from scipy.stats import norm
from sklearn.ensemble import HistGradientBoostingClassifier

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts/wpa"))
import fit_state_model as F  # noqa: E402

MODEL = ROOT / "data/wpa/model"
STATES = ROOT / "data/wpa/states"
REP = ROOT / "data/wpa/reports/strength_layer.md"
OOF = MODEL / "ncaa_oof_state.parquet"
OOF_VERSION = 2  # 2 = with the riding-time probabilities
EPS = 1e-6
N_GRID = [40, 50, 60, 80, 100, 130]
TAIL_GRID = [17, 20, 22, 25, 28, 33, 40, 50, 60]
ALPHA_FORMS = {"none": "none (spec 5.4 as written)", "const": "one constant α",
               "time": "α changes with the clock: a0 + a2·(share of regulation elapsed)"}


# ---------------------------------------------------------------------------------------------------------------
# state model out of fold
# ---------------------------------------------------------------------------------------------------------------
def state_model_wp(train, test, params, return_probs=False):
    key, src, k, k2 = params["table_key"], params["table_data"], params["k"], params["k2"]
    train = F.model_rows(train, params.get("table_rows", "all"))
    rtm = F.fit_rt(train, params.get("rt_model_variant", F.RT_DEFAULT))
    td = F.table_data(train, src)
    arr = F.table_arrays(td, key)
    pbs = F.backstop_grid(F.fit_backstop(td, key), key)
    P = F.isotonic(F.blend(arr, pbs, k, k2)[0], arr["N"])
    probs = F.rt_probs(rtm, test)
    p = F.wp_mixture(P, test, probs, key)
    return (p, probs) if return_probs else p


OOF_KEYS = ["table_key", "table_data", "table_rows", "k", "k2", "rt_model_variant"]
OOF_COLS = ["bout_key", "persp", "source", "year", "era_group", "t_rem", "period", "margin", "pos", "choice", "posc",
            "chc", "rt_diff", "rt_status", "ei", "win", "went_to_ot"]


def ncaa_in_oof_order(two):
    """NCAA rows of `two` in the order build_oof writes them."""
    years = sorted(two.loc[two["kind"] == "ncaa", "year"].unique())
    return pd.concat([two[(two["year"] == Y) & (two["kind"] == "ncaa")] for Y in years], ignore_index=True)


def build_oof(two, params):
    parts = []
    t0 = time.time()
    for Y in sorted(two.loc[two["kind"] == "ncaa", "year"].unique()):
        test = two[(two["year"] == Y) & (two["kind"] == "ncaa")]
        p, (pa, _, pb) = state_model_wp(two[two["year"] != Y], test, params, return_probs=True)
        parts.append(test[OOF_COLS].assign(p_state=p, p_rt_a=pa, p_rt_b=pb))
        print(f"  out-of-fold state model {Y} done ({time.time() - t0:.0f}s)", flush=True)
    return pd.concat(parts, ignore_index=True)


def load_oof(two, params, refresh=False):
    """The out-of-fold state probabilities, rebuilt when the cache was made with other model settings or other rows
    (e.g. after the states were rebuilt)."""
    meta_f = OOF.with_suffix(".json")
    # the state model's own settings, plus when it was last fitted (a refit with unchanged settings -- e.g. a code
    # change -- must still invalidate the cache)
    want = {k: params.get(k) for k in OOF_KEYS} | {"oof_version": OOF_VERSION,
                                                   "state_table_mtime": int((MODEL / "state_table.parquet").stat().st_mtime)}
    if not refresh and OOF.exists() and meta_f.exists() and json.loads(meta_f.read_text()) == want:
        oof = pd.read_parquet(OOF)
        nr = ncaa_in_oof_order(two)
        if len(oof) == len(nr) and all((oof[c].to_numpy() == nr[c].to_numpy()).all()
                                       for c in ("bout_key", "persp", "source", "t_rem", "margin", "win")):
            return oof
    print("building the out-of-fold state probabilities (~6 min)", flush=True)
    oof = build_oof(two, params)
    oof.to_parquet(OOF, index=False)
    meta_f.write_text(json.dumps(want))
    return oof


# ---------------------------------------------------------------------------------------------------------------
# tie model: P(tied at the end of regulation | S) = sum_r P(r | S) * P(tie | S, r)
# ---------------------------------------------------------------------------------------------------------------
def tie_X(d, r, mirror=False):
    """Features of (S, r), or of its mirror (margin, position and r flipped)."""
    s = -1.0 if mirror else 1.0
    rr = np.broadcast_to(np.asarray(r, float), (len(d),))
    return np.column_stack([s * d["margin"].to_numpy(float), d["t_rem"].to_numpy(float),
                            s * d["posc"].to_numpy(float), d["ei"].to_numpy(float),
                            d["pos"].str.startswith("pending").to_numpy(float), s * rr])


def fit_tie_model(two):
    """P(the bout is tied at the end of regulation, riding-time point included | state, eventual point r)."""
    clf = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.08, min_samples_leaf=200, random_state=0)
    clf.fit(tie_X(two, two["r"].to_numpy()), two["went_to_ot"].to_numpy(int))
    return clf


def tie_prob(clf, d):
    """Mixture over the eventual riding-time point, P(r | S) from d's p_rt_a / p_rt_b columns; symmetrised."""
    pa, pb = d["p_rt_a"].to_numpy(float), d["p_rt_b"].to_numpy(float)
    out = np.zeros(len(d))
    for r, p in ((1, pa), (0, 1 - pa - pb), (-1, pb)):
        f = clf.predict_proba(tie_X(d, r))[:, 1]
        fm = clf.predict_proba(tie_X(d, r, mirror=True))[:, 1]
        out += p * (f + fm) / 2
    return out


# ---------------------------------------------------------------------------------------------------------------
# strength layer
# ---------------------------------------------------------------------------------------------------------------
def strength(seed, scale, N, tail):
    s = np.where(np.isnan(seed), tail, seed)
    if scale == "log":
        return -np.log(s)
    return -norm.ppf((s - 0.5) / N)


def rank_signal(d, scale, N, tail):
    sa, sb = d["seed_a"].to_numpy(float), d["seed_b"].to_numpy(float)
    rs = strength(sa, scale, N, tail) - strength(sb, scale, N, tail)
    return np.where(np.isnan(sa) & np.isnan(sb), 0.0, rs)


def nll(p, y):
    p = np.clip(p, EPS, 1 - EPS)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def fit_beta_ot(ot, rs_fun):
    rs = rs_fun(ot)
    y = ot["win"].to_numpy()
    r = minimize_scalar(lambda b: nll(expit(b * rs), y), bounds=(-5, 10), method="bounded")
    return float(r.x)


def alpha(t_share, prm):
    """Weight on the state model's log-odds; t_share = t_rem / 420 (1 at the opening whistle, 0 at the buzzer)."""
    return prm.get("a0", 1.0) + prm.get("a2", 0.0) * (1 - t_share)


def predict(d, rs, prm):
    """prm: b0, g, b_ot, e3m (default 1), a0 (default 1), a2 (default 0)."""
    t = d["t_rem"].to_numpy(float) / 420
    b = prm["b0"] * t ** prm["g"] * np.where(d["ei"].to_numpy() == 1, prm.get("e3m", 1.0), 1.0)
    z = (alpha(t, prm) * logit(np.clip(d["p_state"].to_numpy(), EPS, 1 - EPS)) + b * rs
         + prm["b_ot"] * d["p_tie"].to_numpy() * rs)
    return expit(z)


X0 = {"b0": 1.0, "g": 1.0, "e3m": 1.0, "a0": 1.0, "a2": 0.0}
BOUNDS = {"b0": (0, 5), "g": (0.05, 5), "e3m": (0.2, 3), "a0": (0.3, 1.5), "a2": (-1, 1)}


def fit_params(d, rs, b_ot, e3=False, form="none"):
    """Maximum likelihood for beta0, gamma (+ the E3 multiplier, + alpha by form); b_ot fixed."""
    names = ["b0", "g"] + (["e3m"] if e3 else []) + (["a0"] if form in ("const", "time") else []) \
        + (["a2"] if form == "time" else [])
    y = d["win"].to_numpy()

    def f(th):
        return nll(predict(d, rs, dict(zip(names, th), b_ot=b_ot)), y)
    r = minimize(f, [X0[n] for n in names], bounds=[BOUNDS[n] for n in names], method="L-BFGS-B")
    out = dict(X0, b_ot=float(b_ot))
    out.update(dict(zip(names, map(float, r.x))))
    return out


def cal_slope(p, y):
    """Logistic recalibration slope, no intercept (symmetric data): 1 = calibrated, < 1 = overconfident."""
    x = logit(np.clip(p, EPS, 1 - EPS))
    b = 1.0
    for _ in range(50):
        q = expit(b * x)
        step = np.sum((y - q) * x) / max(np.sum(q * (1 - q) * x * x), 1e-12)
        b += step
        if abs(step) < 1e-7:
            break
    return b


def pct(a, b, d=1):
    return f"{100 * a / b:.{d}f}%" if b else "—"


def loto(smp, ot, years, rsf, form="none", e3=False):
    """Leave-one-year-out predictions for every sample, and the per-year parameters."""
    rs = rsf(smp)
    pred = np.empty(len(smp))
    prms = {}
    for Y in years:
        tr, te = (smp["year"] != Y).to_numpy(), (smp["year"] == Y).to_numpy()
        b_ot = fit_beta_ot(ot[ot["year"] != Y], rsf)
        prm = fit_params(smp[tr], rs[tr], b_ot, e3=e3, form=form)
        pred[te] = predict(smp[te], rs[te], prm)
        prms[Y] = prm
    return pred, prms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    params = json.loads((MODEL / "model_params.json").read_text())
    two, _ = F.load()
    bouts = pd.concat([pd.read_csv(STATES / f"{k}_bouts.csv", low_memory=False) for k in ("ncaa", "conf")])
    ot_flag = bouts.set_index("bout_key")["went_to_ot"].astype(str) == "True"
    two["went_to_ot"] = two["bout_key"].map(ot_flag).fillna(False).astype(bool)

    oof = load_oof(two, params, args.refresh)
    tie = fit_tie_model(F.model_rows(two, params.get("table_rows", "all")))
    oof["p_tie"] = tie_prob(tie, oof)

    nb = bouts[bouts["kind"] == "ncaa"].set_index("bout_key")
    ws, ls = nb["w_seed"], nb["l_seed"]
    oof["seed_a"] = np.where(oof["persp"] == "w", oof["bout_key"].map(ws), oof["bout_key"].map(ls))
    oof["seed_b"] = np.where(oof["persp"] == "w", oof["bout_key"].map(ls), oof["bout_key"].map(ws))
    smp = oof[oof["source"] == "sample"].reset_index(drop=True)
    y = smp["win"].to_numpy()
    # overtime bouts, one row per side, for beta_ot
    otb = nb[(nb["went_to_ot"].astype(str) == "True") & (nb["included"] == True)]  # noqa: E712
    ot = pd.DataFrame({"seed_a": np.r_[otb["w_seed"], otb["l_seed"]], "seed_b": np.r_[otb["l_seed"], otb["w_seed"]],
                       "win": np.r_[np.ones(len(otb)), np.zeros(len(otb))], "year": np.r_[otb["year"], otb["year"]]})
    years = sorted(smp["year"].unique())
    print(f"samples {len(smp):,}, overtime bouts {len(otb):,}; fitting grid ({time.time() - t0:.0f}s)", flush=True)

    # 1. seed scale, N, unseeded value -- with the spec's form
    grid = [("normal", N, tl) for N in N_GRID for tl in TAIL_GRID if tl < N] + [("log", None, tl) for tl in TAIL_GRID]
    results = {}
    for scale, N, tl in grid:
        pred, _ = loto(smp, ot, years, lambda d, s=scale, n=N, t=tl: rank_signal(d, s, n, t))
        results[(scale, N, tl)] = nll(pred, y)
    scale, N, tl = min(results, key=results.get)

    def rsf(d):
        return rank_signal(d, scale, N, tl)
    rs = rsf(smp)
    print(f"scale chosen: {scale} {N} {tl} ({time.time() - t0:.0f}s)", flush=True)

    # 2. alpha form
    gap = np.abs(rs)
    med = np.median(gap[gap > 0])
    buckets = {"Both unseeded": gap == 0, "Small seed gap": (gap > 0) & (gap <= med), "Big seed gap": gap > med}
    e3y = (smp["era_group"] == "E3").to_numpy()
    forms = {}
    for form in ALPHA_FORMS:
        pred, prms = loto(smp, ot, years, rsf, form=form)
        forms[form] = {"pred": pred, "ll": nll(pred, y), "ll_e3": nll(pred[e3y], y[e3y]),
                       "slope": cal_slope(pred, y), "slopes": {k: cal_slope(pred[m], y[m]) for k, m in buckets.items()}}
    best_form = min(forms, key=lambda f: forms[f]["ll"])
    form = best_form if forms[best_form]["ll"] < forms["none"]["ll"] - 1e-4 else "none"
    print(f"alpha form chosen: {form} ({time.time() - t0:.0f}s)", flush=True)

    # 3. E3's own beta0? (decision 5) -- leave-one-year-out on the E3 years
    e3_cmp = []
    for Y in [yy for yy in years if yy >= 2024]:
        tr, te = (smp["year"] != Y).to_numpy(), (smp["year"] == Y).to_numpy()
        bo = fit_beta_ot(ot[ot["year"] != Y], rsf)
        a = fit_params(smp[tr], rs[tr], bo, form=form)
        e = fit_params(smp[tr], rs[tr], bo, e3=True, form=form)
        e3_cmp.append((Y, nll(predict(smp[te], rs[te], a), y[te]), nll(predict(smp[te], rs[te], e), y[te]), e["e3m"]))
    use_e3 = sum(e for _, _, e, _ in e3_cmp) < sum(a for _, a, _, _ in e3_cmp) - 1e-4
    final_pred, _ = loto(smp, ot, years, rsf, form=form, e3=use_e3)
    b_ot = fit_beta_ot(ot, rsf)
    prm = fit_params(smp, rs, b_ot, e3=use_e3, form=form)
    prm_one = fit_params(smp, rs, b_ot, form=form)

    # ------------------------------------------------------------------ report
    L = []
    A = L.append
    A("# WPA step 7 — strength layer (NCAA seeds)\n")
    A("Generated by `scripts/wpa/fit_strength.py` (revised in step 8). **logit(WP) = α(rs)·logit(WP_state) + "
      "β0·(t/420)^γ·rs + β_ot·P(tied at the end of regulation | state)·rs**, rs = rank signal. WP_state is the step "
      "5–6 state model, scored out of fold (each NCAA year by a model built without that year). Seeds: committee "
      "seeds; 2015–18 seeds 17–33 (random draw) are unseeded. The overtime term is TJ's decision 6: the spec's "
      "fading β(t) reaches 0 at the buzzer, so without it a tie at 0:00 would carry no seed effect into overtime. "
      "α is the step-8 addition (below); the spec's form is α = 1.\n")
    A(f"Data: {smp['bout_key'].nunique():,} NCAA bouts, {len(smp):,} ten-second samples (both sides); "
      f"{len(otb):,} overtime bouts for β_ot. Rank signal is 0 for {pct((rs == 0).sum(), len(rs))} of samples "
      f"(both unseeded).\n")
    A("## Choosing the strength scale (spec 5.2)\n")
    A("Leave-one-tournament-out (each NCAA year held out in turn; β0, γ and β_ot refitted on the other years; spec "
      "form), pooled log loss on the held-out samples. Best 8, and the best of each scale:\n")
    A("| Scale | Pool size N | Unseeded = seed | Held-out log loss |\n|---|---:|---:|---:|")
    for k_ in sorted(results, key=results.get)[:8]:
        A(f"| {'normal quantile' if k_[0] == 'normal' else 'log rank'} | {k_[1] or '—'} | {k_[2]} | {results[k_]:.4f} |")
    for sc in ("normal", "log"):
        kk = min((k_ for k_ in results if k_[0] == sc), key=results.get)
        A(f"\nBest {'normal quantile' if sc == 'normal' else 'log rank'}: {results[kk]:.4f} "
          f"(N = {kk[1] or '—'}, unseeded = {kk[2]}).")
    base = nll(smp["p_state"].to_numpy(), y)
    A(f"\nState model alone (no seeds), same samples: {base:.4f}.\n")
    A(f"**Chosen:** {'normal quantile' if scale == 'normal' else 'log rank'}"
      + (f", N = {N}" if N else "") + f", unseeded wrestlers valued like seed {tl}.\n")

    A("## Shrinking the state part: α (added in step 8)\n")
    A("The state table is learned from all bouts, and in them the wrestler who leads is usually the better one — so "
      "a lead already carries an average strength edge, and adding the full seed shift on top counts it twice. "
      "Validation (step 8) showed the spec's form overconfident in evenly matched bouts and fine in big-gap ones. "
      "Three forms, each fitted leave-one-year-out (calibration slope: 1 = calibrated, < 1 = overconfident; small / "
      f"big gap split at the median seeded gap, {med:.2f}):\n")
    A("| α | Held-out log loss | 2024–26 | Slope, all | Slope, both unseeded | Slope, small gap | Slope, big gap |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for f_, r_ in forms.items():
        s_ = r_["slopes"]
        A(f"| {ALPHA_FORMS[f_]} | {r_['ll']:.4f} | {r_['ll_e3']:.4f} | {r_['slope']:.3f} | {s_['Both unseeded']:.3f} | "
          f"{s_['Small seed gap']:.3f} | {s_['Big seed gap']:.3f} |")
    A(f"\n**Chosen:** {ALPHA_FORMS[form]}.\n")

    A("## Does E3 (2024–26) want its own β0? (decision 5)\n")
    A("Each E3 year held out; fitted on the rest with one β0 for all years vs an extra multiplier on β0 for E3.\n")
    A("| Held-out year | One β0 | E3 multiplier | Multiplier fitted |\n|---|---:|---:|---:|")
    for Y, a_, e_, mlt in e3_cmp:
        A(f"| {Y} | {a_:.4f} | {e_:.4f} | {mlt:.2f} |")
    A("\n" + ("**It helps on held-out E3 years, so E3 gets its own β0.**" if use_e3 else
              "**It doesn't help on held-out E3 years, so one β0 is kept for all years.**") + "\n")

    A("## Fitted parameters (all NCAA years)\n")
    A(f"- β0 = {prm['b0']:.3f}, γ = {prm['g']:.3f} (spec expected γ near 1), β_ot = {b_ot:.3f}"
      + (f"; E3 (2024–26) seed effect × {prm['e3m']:.2f} (one β0 for all years would be {prm_one['b0']:.3f}, "
         f"γ {prm_one['g']:.3f})" if use_e3 else "")
      + (f"; α = {prm['a0']:.3f}" + (f" + {prm['a2']:.3f}·(share of regulation elapsed)" if form == "time" else "")
         if form != "none" else "") + ".")
    ex = pd.DataFrame({"seed_a": [1.0, 1.0, 8.0, 16.0], "seed_b": [16.0, 33.0, 9.0, np.nan]})
    ex_rs = rsf(ex)
    A(f"- Rank signal examples: 1 vs 16 = {ex_rs[0]:.2f}, 1 vs 33 = {ex_rs[1]:.2f}, 8 vs 9 = {ex_rs[2]:.2f}, "
      f"16 vs unseeded = {ex_rs[3]:.2f}.")
    if form != "none":
        A("- α (weight on the state model's log-odds): " + ", ".join(
            f"{lab} {alpha(v, prm):.2f}" for lab, v in
            (("7:00 left", 1.0), ("4:00", 240 / 420), ("2:00", 120 / 420), ("0:00", 0.0))) + ".")
    A("- Seed effect in log-odds as the clock runs, 1 vs 16 in 2024–26: " + ", ".join(
        f"{lab} {prm['b0'] * prm['e3m'] * (t / 420) ** prm['g'] * ex_rs[0]:.2f}" for lab, t in
        (("7:00", 420), ("4:00", 240), ("2:00", 120), ("1:00", 60), ("0:10", 10))) + ".\n")

    A("## Held out by year\n")
    A("| Year | State model alone | With seeds (final form) |\n|---|---:|---:|")
    for Y in years:
        te = (smp["year"] == Y).to_numpy()
        A(f"| {Y} | {nll(smp.loc[te, 'p_state'].to_numpy(), y[te]):.4f} | {nll(final_pred[te], y[te]):.4f} |")
    A(f"| **All** | {base:.4f} | **{nll(final_pred, y):.4f}** |\n")
    A("Full calibration, by bucket and by slice: `validation.md` (step 8).\n")

    A("## Spot checks\n")
    tab = pd.read_parquet(MODEL / "state_table.parquet")
    key = params["table_key"]
    Pfin = tab["p_state"].to_numpy().reshape(F.shape(key))
    rtm = joblib.load(MODEL / "rt_model.joblib")
    A("| State | WP_state | P(tied at the buzzer) | With seeds |\n|---|---:|---:|---:|")
    for lab, sa, sb, mg, t, pos in [("1 seed vs 16 seed, tied, 7:00 left", 1, 16, 0, 420, "neutral"),
                                    ("8 vs 9, tied, 7:00 left", 8, 9, 0, 420, "neutral"),
                                    ("1 seed vs 16 seed, 1 seed down 3, 0:10 left, neutral", 1, 16, -3, 10, "neutral"),
                                    ("1 seed vs 16 seed, tied, 0:05 left, neutral", 1, 16, 0, 5, "neutral"),
                                    ("Both unseeded, A up 3, 1:00 left, neutral", np.nan, np.nan, 3, 60, "neutral")]:
        d = pd.DataFrame([{"rt_diff": 0.0, "t_rem": t, "posc": 0, "margin": mg, "ei": 1, "pos": pos, "chc": 0,
                           "ti": min(41, t // 10), "pi": 0 if t > 240 else (1 if t > 120 else 2),
                           "posi": F.POS.index(pos), "chi": F.CH.index("none"), "seed_a": float(sa),
                           "seed_b": float(sb)}])
        pr = F.rt_probs(rtm, d)
        d["p_state"] = F.wp_mixture(Pfin, d, pr, key)
        d["p_rt_a"], d["p_rt_b"] = pr[0], pr[2]
        d["p_tie"] = tie_prob(tie, d)
        A(f"| {lab} | {100 * d['p_state'][0]:.1f}% | {100 * d['p_tie'][0]:.1f}% | "
          f"{100 * predict(d, rsf(d), prm)[0]:.1f}% |")
    A("")

    out = {"scale": scale, "N": N, "unseeded_equiv_seed": tl, "beta0": prm["b0"], "gamma": prm["g"], "beta_ot": b_ot,
           "e3_beta0_multiplier": prm["e3m"] if use_e3 else 1.0, "alpha_form": form, "alpha0": prm["a0"],
           "alpha_time": prm["a2"], "loto_logloss": nll(final_pred, y), "state_only_logloss": base,
           "tie_model": "sum over r of P(r | S) * P(tie | margin, time, position, era, break, r); symmetrised",
           "built": time.strftime("%Y-%m-%d")}
    (MODEL / "strength_params.json").write_text(json.dumps(out, indent=2))
    joblib.dump(tie, MODEL / "tie_model.joblib")
    REP.write_text("\n".join(L) + "\n")
    print("wrote", REP, out, f"({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
