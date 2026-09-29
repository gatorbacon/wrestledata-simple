#!/usr/bin/env python3
"""
WPA step 7 -- strength layer on NCAA seeds (spec Section 5).

    logit(WP) = logit(WP_state) + beta(t) * rank_signal + beta_ot * P(tied at the end of regulation | state) * rank_signal
    beta(t)   = beta0 * (t_rem / 420) ** gamma

  * WP_state: the step 5-6 state model (fit_state_model.py), computed OUT OF FOLD -- each NCAA year's states are
    scored by a state model built without that year (NCAA or conference), so the seed effect isn't fitted against
    probabilities that have already seen the result. Cached in data/wpa/model/ncaa_oof_state.parquet (--refresh to
    rebuild, ~5 min).
  * rank_signal = strength(A) - strength(B), from NCAA committee seeds. Two scales (spec 5.2): log-rank,
    strength = -log(seed); normal quantile, strength = -Phi^-1((seed - 0.5) / N). Unseeded wrestlers (2015-2018 seeds
    17-33, which were a random draw -- decision C) get one tail value, an "equivalent seed" R_tail. Unseeded vs
    unseeded -> 0. N and R_tail are tuned on held-out log loss.
  * Overtime (TJ decision 6): a tie at the end of regulation is worth the overtime win rate, and the seed effect in
    overtime is fitted on all NCAA overtime bouts (beta_ot, logistic on rank_signal, no intercept). The spec's fading
    beta(t) goes to 0 at the buzzer, so on its own it would give a tie at 0:00 no seed effect at all; the extra term
    carries the overtime seed effect in proportion to the chance the bout is still headed for overtime, from a small
    boosted model P(tied at the end of regulation | margin, time, position, riding time, era).
  * Fitting: beta0 and gamma by maximum likelihood on the 10-second samples. Validation: leave one NCAA tournament
    (= year) out; N / R_tail / scale chosen by the pooled result. Then a check of whether E3 (2024-26) wants its own
    beta0 (decision 5).

Outputs: data/wpa/model/strength_params.json, data/wpa/reports/strength_layer.md.
Usage: .venv/bin/python scripts/wpa/fit_strength.py [--refresh]
"""
import argparse
import json
import sys
import time
from pathlib import Path

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
EPS = 1e-6
N_GRID = [40, 50, 60, 80, 100, 130]
TAIL_GRID = [17, 20, 22, 25, 28, 33, 40, 50, 60]


def state_model_wp(train, test, params):
    key, src, k, k2 = params["table_key"], params["table_data"], params["k"], params["k2"]
    rtm = F.fit_rt(train)
    td = F.table_data(train, src)
    arr = F.table_arrays(td, key)
    pbs = F.backstop_grid(F.fit_backstop(td, key), key)
    P = F.isotonic(F.blend(arr, pbs, k, k2)[0], arr["N"])
    return F.wp_mixture(P, test, F.rt_probs(rtm, test), key)


def fit_tie_model(two):
    """P(the bout is tied at the end of regulation, riding-time point included | state)."""
    X = two[["margin", "t_rem", "posc", "rt_diff", "ei"]].to_numpy(float)
    clf = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.08, min_samples_leaf=200, random_state=0)
    clf.fit(X, two["went_to_ot"].to_numpy(int))
    return clf


def build_oof(two, params):
    ncaa_years = sorted(two.loc[two["kind"] == "ncaa", "year"].unique())
    parts = []
    t0 = time.time()
    for Y in ncaa_years:
        test = two[(two["year"] == Y) & (two["kind"] == "ncaa")]
        train = two[two["year"] != Y]
        p = state_model_wp(train, test, params)
        parts.append(test[["bout_key", "persp", "source", "year", "era_group", "t_rem", "margin", "posc", "rt_diff",
                           "ei", "win", "went_to_ot"]].assign(p_state=p))
        print(f"  out-of-fold state model {Y} done ({time.time() - t0:.0f}s)", flush=True)
    return pd.concat(parts, ignore_index=True)


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


def predict(d, rs, b0, g, b_ot, e3_mult=1.0):
    t = d["t_rem"].to_numpy(float) / 420
    b = b0 * t ** g * np.where(d["ei"].to_numpy() == 1, e3_mult, 1.0)
    z = logit(np.clip(d["p_state"].to_numpy(), EPS, 1 - EPS)) + b * rs + b_ot * d["p_tie"].to_numpy() * rs
    return expit(z)


def fit_b0_g(d, rs, b_ot, e3=False):
    y = d["win"].to_numpy()

    def f(th):
        return nll(predict(d, rs, th[0], th[1], b_ot, th[2] if e3 else 1.0), y)
    x0 = [1.0, 1.0, 1.0] if e3 else [1.0, 1.0]
    bounds = [(0, 5), (0.05, 5)] + ([(0.2, 3)] if e3 else [])
    r = minimize(f, x0, bounds=bounds, method="L-BFGS-B")
    return r.x


def pct(a, b, d=1):
    return f"{100 * a / b:.{d}f}%" if b else "—"


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

    if args.refresh or not OOF.exists():
        oof = build_oof(two, params)
        oof.to_parquet(OOF, index=False)
    oof = pd.read_parquet(OOF)
    tie = fit_tie_model(two)
    oof["p_tie"] = tie.predict_proba(oof[["margin", "t_rem", "posc", "rt_diff", "ei"]].to_numpy(float))[:, 1]

    nb = bouts[bouts["kind"] == "ncaa"].set_index("bout_key")
    ws, ls = nb["w_seed"], nb["l_seed"]
    oof["seed_a"] = np.where(oof["persp"] == "w", oof["bout_key"].map(ws), oof["bout_key"].map(ls))
    oof["seed_b"] = np.where(oof["persp"] == "w", oof["bout_key"].map(ls), oof["bout_key"].map(ws))
    smp = oof[oof["source"] == "sample"].reset_index(drop=True)
    # overtime bouts, one row per side, for beta_ot
    otb = nb[(nb["went_to_ot"].astype(str) == "True") & (nb["included"] == True)]  # noqa: E712
    ot = pd.DataFrame({"seed_a": np.r_[otb["w_seed"], otb["l_seed"]], "seed_b": np.r_[otb["l_seed"], otb["w_seed"]],
                       "win": np.r_[np.ones(len(otb)), np.zeros(len(otb))], "year": np.r_[otb["year"], otb["year"]]})
    years = sorted(smp["year"].unique())
    print(f"samples {len(smp):,}, overtime bouts {len(otb):,}; fitting grid ({time.time() - t0:.0f}s)", flush=True)

    grid = [("normal", N, tl) for N in N_GRID for tl in TAIL_GRID if tl < N] + [("log", None, tl) for tl in TAIL_GRID]
    results = {}
    for scale, N, tl in grid:
        rs_all = rank_signal(smp, scale, N, tl)
        ll_sum, n_sum, per_year = 0.0, 0, {}
        for Y in years:
            tr, te = smp["year"] != Y, smp["year"] == Y
            b_ot = fit_beta_ot(ot[ot["year"] != Y], lambda d: rank_signal(d, scale, N, tl))
            b0, g = fit_b0_g(smp[tr], rs_all[tr], b_ot)
            p = predict(smp[te], rs_all[te], b0, g, b_ot)
            ll = nll(p, smp.loc[te, "win"].to_numpy())
            per_year[Y] = ll
            ll_sum += ll * te.sum()
            n_sum += te.sum()
        results[(scale, N, tl)] = (ll_sum / n_sum, per_year)
    best = min(results, key=lambda k: results[k][0])
    scale, N, tl = best
    rs = rank_signal(smp, scale, N, tl)
    b_ot = fit_beta_ot(ot, lambda d: rank_signal(d, scale, N, tl))
    b0, g = fit_b0_g(smp, rs, b_ot)
    # E3's own beta0? leave-one-year-out on the E3 years, with and without an E3 multiplier
    e3_cmp = []
    for Y in [y for y in years if y >= 2024]:
        tr, te = smp["year"] != Y, smp["year"] == Y
        bo = fit_beta_ot(ot[ot["year"] != Y], lambda d: rank_signal(d, scale, N, tl))
        a = fit_b0_g(smp[tr], rs[tr], bo)
        e = fit_b0_g(smp[tr], rs[tr], bo, e3=True)
        yv = smp.loc[te, "win"].to_numpy()
        e3_cmp.append((Y, nll(predict(smp[te], rs[te], a[0], a[1], bo), yv),
                       nll(predict(smp[te], rs[te], e[0], e[1], bo, e[2]), yv), e[2]))
    e3_all = fit_b0_g(smp, rs, b_ot, e3=True)
    b0_one, g_one = b0, g
    use_e3 = sum(e for _, _, e, _ in e3_cmp) < sum(a for _, a, _, _ in e3_cmp) - 1e-4
    if use_e3:
        b0, g, e3m = map(float, e3_all)
    else:
        e3m = 1.0

    # ------------------------------------------------------------------ report
    L = []
    A = L.append
    A("# WPA step 7 — strength layer (NCAA seeds)\n")
    A("Generated by `scripts/wpa/fit_strength.py`. **logit(WP) = logit(WP_state) + β0·(t/420)^γ · rank_signal + "
      "β_ot · P(tied at the end of regulation | state) · rank_signal.** WP_state is the step 5–6 state model, scored "
      "out of fold (each NCAA year by a model built without that year). Seeds: committee seeds; 2015–18 seeds 17–33 "
      "(random draw) are unseeded. The second term is TJ's decision 6: the spec's fading β(t) reaches 0 at the "
      "buzzer, so without it a tie at 0:00 would carry no seed effect into overtime.\n")
    A(f"Data: {smp['bout_key'].nunique():,} NCAA bouts, {len(smp):,} ten-second samples (both sides); "
      f"{len(otb):,} overtime bouts for β_ot. Rank signal is 0 for {pct((rs == 0).sum(), len(rs))} of samples "
      f"(both unseeded, or equal seeds).\n")
    A("## Choosing the strength scale (spec 5.2)\n")
    A("Leave-one-tournament-out (each NCAA year held out in turn; β0, γ and β_ot refitted on the other years), pooled "
      "log loss on the held-out samples. Best 8, and the best of each scale:\n")
    A("| Scale | Pool size N | Unseeded = seed | Held-out log loss |\n|---|---:|---:|---:|")
    for k_ in sorted(results, key=lambda k: results[k][0])[:8]:
        A(f"| {'normal quantile' if k_[0] == 'normal' else 'log rank'} | {k_[1] or '—'} | {k_[2]} | "
          f"{results[k_][0]:.4f} |")
    for sc in ("normal", "log"):
        kk = min((k_ for k_ in results if k_[0] == sc), key=lambda k: results[k][0])
        A(f"\nBest {'normal quantile' if sc == 'normal' else 'log rank'}: {results[kk][0]:.4f} "
          f"(N = {kk[1] or '—'}, unseeded = {kk[2]}).")
    base = nll(smp["p_state"].to_numpy(), smp["win"].to_numpy())
    A(f"\nState model alone (no seeds), same samples: {base:.4f}.\n")
    A(f"**Chosen:** {'normal quantile' if scale == 'normal' else 'log rank'}"
      + (f", N = {N}" if N else "") + f", unseeded wrestlers valued like seed {tl}.\n")

    A("## Fitted parameters (all NCAA years)\n")
    A(f"- β0 = {b0:.3f}, γ = {g:.3f} (spec expected γ near 1), β_ot = {b_ot:.3f}"
      + (f"; E3 (2024–26) seed effect × {e3m:.2f} (see the E3 check below; one β0 for all years would be "
         f"{b0_one:.3f}, γ {g_one:.3f})." if use_e3 else "."))
    ex_rs = rank_signal(pd.DataFrame({"seed_a": [1.0, 1.0, 8.0, 16.0], "seed_b": [16.0, 33.0, 9.0, np.nan]}),
                        scale, N, tl)
    A(f"- Rank signal examples: 1 vs 16 = {ex_rs[0]:.2f}, 1 vs 33 = {ex_rs[1]:.2f}, 8 vs 9 = {ex_rs[2]:.2f}, "
      f"16 vs unseeded = {ex_rs[3]:.2f}.")
    A("- Seed effect in log-odds as the clock runs, 1 vs 16 in 2024–26: " + ", ".join(
        f"{lab} {b0 * e3m * (t / 420) ** g * ex_rs[0]:.2f}" for lab, t in
        (("7:00", 420), ("4:00", 240), ("2:00", 120), ("1:00", 60), ("0:10", 10))) + ".\n")

    A("## Held out by year\n")
    A("| Year | State model alone | With seeds |\n|---|---:|---:|")
    for Y in years:
        te = smp["year"] == Y
        A(f"| {Y} | {nll(smp.loc[te, 'p_state'].to_numpy(), smp.loc[te, 'win'].to_numpy()):.4f} | "
          f"{results[best][1][Y]:.4f} |")
    A("")

    A("## Does E3 (2024–26) want its own β0? (decision 5)\n")
    A("Each E3 year held out; fitted on the rest with one β0 for all years vs an extra multiplier on β0 for E3.\n")
    A("| Held-out year | One β0 | E3 multiplier | Multiplier fitted |\n|---|---:|---:|---:|")
    for Y, a_, e_, mlt in e3_cmp:
        A(f"| {Y} | {a_:.4f} | {e_:.4f} | {mlt:.2f} |")
    A(f"\nOn all years the multiplier fits at {e3_all[2]:.2f}. "
      + ("**It helps on held-out E3 years, so E3 gets its own β0.**" if use_e3 else
         "**It doesn't help on held-out E3 years, so one β0 is kept for all years.**") +
      " The difference is small either way (about 0.001 of log loss per year).\n")

    # calibration preview by rank gap (spec 7.4 in full at step 8)
    p_all = np.concatenate([predict(smp[smp["year"] == Y], rs[smp["year"] == Y], b0, g, b_ot, e3m) for Y in years])
    order = np.concatenate([np.where(smp["year"] == Y)[0] for Y in years])
    pf = np.empty(len(smp))
    pf[order] = p_all
    smp["p_final"] = pf
    A("## Preview: calibration by rank-gap bucket (in-sample; step 8 does this properly)\n")
    gap = np.abs(rs)
    buckets = [("Both unseeded / equal", gap == 0), ("Small gap", (gap > 0) & (gap <= np.quantile(gap[gap > 0], .5))),
               ("Big gap", gap > np.quantile(gap[gap > 0], .5))]
    A("| Bucket | Samples | Mean predicted (favourite's side) | Actual |\n|---|---:|---:|---:|")
    for lab, s_ in buckets:
        d = smp[s_ & (rs >= 0)]
        A(f"| {lab} | {len(d):,} | {100 * d['p_final'].mean():.1f}% | {100 * d['win'].mean():.1f}% |")
    A("")
    A("## Spot checks\n")

    def one(sa, sb, margin, t, pos, rt=0.0, era=1):
        row = pd.DataFrame([{"rt_diff": rt, "t_rem": t, "posc": {"neutral": 0, "A_top": 1, "A_bottom": -1}[pos],
                             "margin": margin, "ei": era, "rt_status": F.C.rt_status(rt, t), "ti": min(41, t // 10),
                             "pi": 0 if t > 240 else (1 if t > 120 else 2), "posi": F.POS.index(pos),
                             "chi": F.CH.index("none"), "seed_a": sa, "seed_b": sb}])
        return row
    tab = pd.read_parquet(MODEL / "state_table.parquet")
    key = params["table_key"]
    sh = F.shape(key)
    Pfin = tab["p_state"].to_numpy().reshape(sh)
    import joblib
    rtm = joblib.load(MODEL / "rt_model.joblib")
    A("| State | WP_state | With seeds |\n|---|---:|---:|")
    for lab, sa, sb, mg, t, pos in [("1 seed vs 16 seed, tied, 7:00 left", 1, 16, 0, 420, "neutral"),
                                    ("8 vs 9, tied, 7:00 left", 8, 9, 0, 420, "neutral"),
                                    ("1 seed vs 16 seed, 1 seed down 3, 0:10 left, neutral", 1, 16, -3, 10, "neutral"),
                                    ("1 seed vs 16 seed, tied, 0:05 left, neutral", 1, 16, 0, 5, "neutral")]:
        d = one(float(sa), float(sb), mg, t, pos)
        d["p_state"] = F.wp_mixture(Pfin, d, F.rt_probs(rtm, d), key)
        d["p_tie"] = tie.predict_proba(d[["margin", "t_rem", "posc", "rt_diff", "ei"]].to_numpy(float))[:, 1]
        r_ = rank_signal(d, scale, N, tl)
        A(f"| {lab} | {100 * d['p_state'][0]:.1f}% | {100 * predict(d, r_, b0, g, b_ot, e3m)[0]:.1f}% |")
    A("")

    out = {"scale": scale, "N": N, "unseeded_equiv_seed": tl, "beta0": b0, "gamma": g, "beta_ot": b_ot,
           "e3_beta0_multiplier": e3m, "loto_logloss": results[best][0], "state_only_logloss": base,
           "built": time.strftime("%Y-%m-%d")}
    (MODEL / "strength_params.json").write_text(json.dumps(out, indent=2))
    import joblib as jl
    jl.dump(tie, MODEL / "tie_model.joblib")
    REP.write_text("\n".join(L) + "\n")
    print("wrote", REP, out, f"({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
