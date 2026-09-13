#!/usr/bin/env python3
"""
Phase 3: fit a baseline live win-probability model on the labeled training
table from build_training_data.py (data/pbp/training_rows.csv).

Logistic regression first, per plan -- interpretable, fast, and a fair
baseline before reaching for anything nonlinear. No assumption is made
about which feature values help or hurt (e.g. top vs. bottom position,
being the flip winner, more/less DPG) -- the fitted coefficients are
printed precisely so the model's own findings are visible and checkable,
not asserted up front.

State features used (all describe the CURRENT moment, not what just
happened -- "action" that produced this state is deliberately excluded,
since a win-probability model should depend only on the state itself, not
its history, and two identical states should get identical predictions
regardless of how they were reached):
  - score_diff (subject - opponent)
  - period (categorical: "1","2","3","OT1","OT2","OT3")
  - time_remaining_in_period_sec
  - subject_position (top/bottom/neutral/unknown -- opponent_position is
    the mechanical mirror of this, so including both would just duplicate
    the same information)
  - subject_dpg, opponent_dpg (season DPG, kept as two separate features
    rather than a difference, per instruction -- both matter independently,
    not just their gap)
  - subject_stalling_warned, opponent_stalling_warned (booleans)
  - subject_is_flip_winner (bool; unresolved for ~5% of bouts that ended
    in period 1 before a flip choice was ever recorded -- filled as False
    with a separate flag so "unknown" isn't silently conflated with "no")
  - riding_time_net_sec (subject's cumulative riding time minus opponent's,
    reconstructed in parse_bout_pbp.py -- see docs/matsavant.md Known
    Gotcha #15, validated to 95%+ against the scorekeeper's own notes).
    Net, not two separate raw totals, for the same reason score is score_
    diff and not two separate raw scores: it's a zero-sum-ish shifting
    resource where the NET is the actual quantity the NCAA rule cares
    about (the whole-match riding-time bonus point is awarded on a >=60s
    NET advantage), unlike DPG where personal and opponent skill are two
    genuinely distinct traits worth keeping separate.
  - subject_riding_time_criterion_met (bool: net >= 60s) -- included
    ALONGSIDE the continuous net value, not instead of it: the actual NCAA
    rule is a hard cliff at 60 seconds (awarding a discrete point), which
    a single linear coefficient on the continuous net can't represent by
    itself. Together they let the model find both a smooth trend and a
    possible jump right at the threshold, without assuming the jump's
    size -- this is the model-driven version of the simplification
    discussed (a privately-assumed "extra point on the board"): the
    boolean's fitted coefficient IS that assumption's size, discovered
    from data rather than hardcoded as exactly 1.0.

Train/test split is by BOUT, not by row -- the two perspective-rows per
event are exact mirror images of each other, so splitting by row would put
a bout's winner-perspective rows in train and its loser-perspective rows
in test (or vice versa), leaking the answer.

Usage:
    python scripts/win_prob/fit_baseline_model.py
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, log_loss, brier_score_loss
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PBP_DIR = PROJECT_ROOT / "data/pbp"
MODEL_DIR = PBP_DIR / "models"

NUMERIC_FEATURES = [
    "score_diff", "match_time_fraction_remaining",
    "score_diff_x_match_time_fraction", "score_diff_x_match_time_fraction_sq", "score_diff_x_match_time_fraction_cube",
    "subject_dpg", "opponent_dpg", "riding_time_net_sec",
]
CATEGORICAL_FEATURES = ["period", "subject_position"]
BOOLEAN_FEATURES = [
    "subject_stalling_warned", "opponent_stalling_warned", "subject_is_flip_winner_filled",
    "subject_riding_time_criterion_met_filled",
]

# Shared with compute_match_win_prob.py -- pulled into wrestling_clock.py
# 2026-09-14 after the same period-boundary bug had to be fixed in both
# files independently once already; importing means it can't diverge again.
from wrestling_clock import (
    PERIOD_LENGTH_SEC as _REAL_PERIOD_LENGTH_SEC,
    PERIOD_START_ELAPSED as REAL_PERIOD_START,
    OVERTIME_PERIODS,
    real_period as real_period_of,
)

# load_data() also needs a period-keyed length map for the CATEGORICAL
# "choice_N" labels (used only for the period-relative time_fraction_
# remaining fallback below, not for elapsed/match-length math) -- those
# aren't real periods, so they aren't in wrestling_clock's map.
PERIOD_LENGTH_SEC = dict(_REAL_PERIOD_LENGTH_SEC, choice_1=1, choice_2=1, choice_3=1)
REAL_PERIOD_LENGTH = _REAL_PERIOD_LENGTH_SEC


def load_data() -> pd.DataFrame:
    df = pd.read_csv(PBP_DIR / "training_rows.csv")
    df["bout_id"] = df["tournament"] + "_" + df["year"].astype(str) + "_" + df["weight"].astype(str) + "_" + df["bout_number"].astype(str)

    # ~5% of bouts never reach a recorded flip choice (ended in period 1 by
    # fall/tech/injury before period 2's choice was ever made) -- fill as
    # False but keep a separate "known" flag so the model can tell "no"
    # from "never resolved" instead of conflating them.
    df["subject_is_flip_winner_known"] = df["subject_is_flip_winner"].notna()
    df["subject_is_flip_winner_filled"] = df["subject_is_flip_winner"].fillna(False)

    # riding_time_net_sec/criterion_met are only null for the same events
    # missing a position (state not yet established at all, very start of
    # a bout) -- 0 net / not-met is the correct value there, not a guess.
    df["riding_time_net_sec"] = df["riding_time_net_sec"].fillna(0)
    df["subject_riding_time_criterion_met_filled"] = df["subject_riding_time_criterion_met"].fillna(False)

    df["subject_position"] = df["subject_position"].fillna("unknown")

    # time_fraction_remaining: raw seconds isn't comparable across periods
    # of different length (Period 1 = 180s, Periods 2/3 = 120s, OT lengths
    # shorter still) -- normalize to [0, 1] of that period's length instead.
    # ~31% of rows have no embedded clock time at all (see module docstring
    # investigation, 2026-09-12): a row whose PERIOD LABEL is "choice_N"
    # genuinely IS a period-boundary event (0 remaining is factually
    # correct, not an imputation) -- but "riding_time" and "choice" actions
    # tagged with a REAL period label ("1"/"2"/"3"/OT*) are NOT boundaries,
    # they're mid-period events that just happen to be missing a scraped
    # timestamp (found 2026-09-13 via the win-prob chart: an untimed
    # riding_time note -- 5300 of 5366 riding_time rows have no timestamp --
    # was getting hardcoded to "period just ended," which is wrong when it's
    # actually near a period's END *or* its middle; same for 40 real-period
    # "choice" rows, e.g. an injury-default choice). Those, like any other
    # scrape gap (near_fall/penalty/takedown/etc, 1-17% missing), get the
    # median fraction for that action+period instead.
    period_length = df["period"].map(PERIOD_LENGTH_SEC)
    known_fraction = (df["time_remaining_in_period_sec"] / period_length).clip(0, 1)
    is_boundary_event = df["period"].astype(str).str.startswith("choice_")

    df["time_fraction_remaining"] = known_fraction
    df.loc[df["time_remaining_in_period_sec"].isna() & is_boundary_event, "time_fraction_remaining"] = 0.0

    needs_median_fill = df["time_fraction_remaining"].isna()
    fallback_median = df.loc[~needs_median_fill, "time_fraction_remaining"].median()
    group_medians = df.loc[~needs_median_fill].groupby(["action", "period"])["time_fraction_remaining"].median()
    df.loc[needs_median_fill, "time_fraction_remaining"] = df.loc[needs_median_fill].apply(
        lambda r: group_medians.get((r["action"], r["period"]), fallback_median), axis=1
    )

    # match_time_fraction_remaining: how much of the WHOLE MATCH is left, not
    # just the current period. This replaced a period-relative fraction after
    # checking the empirical data directly (2026-09-11): a 1-point lead with
    # <3% of the period left wins only ~69-74% of the time in periods 1-2
    # (because a full extra period still remains) but 97% of the time in
    # period 3 (because the match is actually about to end) -- a single
    # period-relative "time running out" feature can't tell those apart, so
    # the fitted model was underestimating a late lead's value everywhere.
    # elapsed_sec_in_match: cumulative seconds from the opening whistle,
    # built from REAL_PERIOD_START + how far into the (real) period we are.
    # choice_N rows are the boundary that STARTS period N+1, so they sit at
    # elapsed = start of period N+1 (fraction 1.0 of that period), not the
    # end of period N.
    real_period = df["period"].map(real_period_of)
    real_period_start = real_period.map(REAL_PERIOD_START)
    real_period_length = real_period.map(REAL_PERIOD_LENGTH)
    is_choice_boundary = df["period"].astype(str).str.startswith("choice_")
    within_period_fraction = df["time_fraction_remaining"].where(~is_choice_boundary, 1.0)
    df["elapsed_sec_in_match"] = real_period_start + real_period_length * (1 - within_period_fraction)

    # match_length_sec: how long this bout's own clock actually ran.
    # Regulation periods (1/2/3) run their full length -- decided at the
    # buzzer if not sooner -- so the end of the LAST regulation period
    # reached is correct (periods only progress forward, so the max over a
    # bout's own rows of period-start+length is exactly that). But EVERY
    # NCAA overtime period (OT1/OT2/OT3) is sudden-victory: the match ends
    # the INSTANT the deciding event happens, not at that period's nominal
    # length. Treating OT like a fixed-length period was a bug (found
    # 2026-09-14 on the 149lb final: an OT1 takedown that instantly won the
    # match got followed by ~90s of phantom continuation, as if OT1 ran its
    # full 2 minutes and the match could even reach a fictional next
    # tiebreaker period) -- for an OT-decided bout, match_length_sec is the
    # elapsed time of its own actual last event instead.
    df["_period_end_tmp"] = real_period_start + real_period_length
    df["_is_ot_row"] = real_period.isin(OVERTIME_PERIODS)
    bout_has_ot = df.groupby("bout_id")["_is_ot_row"].transform("any")
    regulation_length = df.groupby("bout_id")["_period_end_tmp"].transform("max")
    overtime_length = df.groupby("bout_id")["elapsed_sec_in_match"].transform("max")
    df["match_length_sec"] = np.where(bout_has_ot, overtime_length, regulation_length)
    df.drop(columns=["_period_end_tmp", "_is_ot_row"], inplace=True)

    df["match_time_fraction_remaining"] = (1 - df["elapsed_sec_in_match"] / df["match_length_sec"]).clip(0, 1)

    # A single linear score_diff x time interaction can't fit the actual
    # shape here: checked directly against the data (2026-09-13), a 1-point
    # lead wins ~66% of the time with the full match still ahead but ~99%
    # of the time in the final 3% of match time -- a sharp curve, not a
    # constant slope. Adding quadratic + cubic terms in match_time_fraction
    # lets logistic regression fit that curve directly (confirmed well
    # calibrated even in the frac<0.05 slice) without jumping to a black-box
    # model, which was tried and rejected: a gradient-boosted version of
    # this let extreme subject_dpg values swamp the score-state features
    # (predicted ~93%+ regardless of who was leading, for a big DPG
    # favorite) -- an overfitting failure mode in the sparse DPG tail that
    # a small set of engineered polynomial terms doesn't have.
    df["score_diff_x_match_time_fraction"] = df["score_diff"] * df["match_time_fraction_remaining"]
    df["score_diff_x_match_time_fraction_sq"] = df["score_diff"] * df["match_time_fraction_remaining"] ** 2
    df["score_diff_x_match_time_fraction_cube"] = df["score_diff"] * df["match_time_fraction_remaining"] ** 3
    return df


def build_pipeline() -> Pipeline:
    preprocess = ColumnTransformer([
        ("num", StandardScaler(), NUMERIC_FEATURES),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
        ("bool", "passthrough", BOOLEAN_FEATURES),
    ])
    return Pipeline([
        ("preprocess", preprocess),
        ("model", LogisticRegression(max_iter=1000)),
    ])


def reliability_table(y_true: np.ndarray, y_pred: np.ndarray, n_bins: int = 10) -> pd.DataFrame:
    """Calibration check: within each predicted-probability bin, does the
    actual win rate match? This is the real trust test for the model, not
    accuracy alone."""
    bins = pd.qcut(y_pred, n_bins, duplicates="drop")
    df = pd.DataFrame({"bin": bins, "pred": y_pred, "actual": y_true})
    return df.groupby("bin", observed=True).agg(
        n=("actual", "size"), mean_predicted=("pred", "mean"), actual_win_rate=("actual", "mean")
    )


def main():
    df = load_data()
    print(f"Loaded {len(df)} rows, {df['bout_id'].nunique()} bouts")

    feature_cols = NUMERIC_FEATURES + CATEGORICAL_FEATURES + BOOLEAN_FEATURES
    X = df[feature_cols]
    y = df["label"].values
    groups = df["bout_id"].values

    splitter = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    train_idx, test_idx = next(splitter.split(X, y, groups))
    X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]
    print(f"Train: {len(X_train)} rows / {df['bout_id'].iloc[train_idx].nunique()} bouts")
    print(f"Test:  {len(X_test)} rows / {df['bout_id'].iloc[test_idx].nunique()} bouts")

    pipeline = build_pipeline()
    pipeline.fit(X_train, y_train)

    y_pred_train = pipeline.predict_proba(X_train)[:, 1]
    y_pred_test = pipeline.predict_proba(X_test)[:, 1]

    print("\n=== Held-out test performance ===")
    print(f"  ROC-AUC:     {roc_auc_score(y_test, y_pred_test):.4f}")
    print(f"  Log loss:    {log_loss(y_test, y_pred_test):.4f}")
    print(f"  Brier score: {brier_score_loss(y_test, y_pred_test):.4f}  (lower is better; 0.25 = coin flip baseline)")
    print(f"  (train ROC-AUC: {roc_auc_score(y_train, y_pred_train):.4f} -- compare to test to check for overfitting)")

    print("\n=== Calibration (test set, 10 bins by predicted probability) ===")
    print(reliability_table(y_test, y_pred_test).to_string())

    print("\n=== Fitted coefficients (standardized numeric features; sign/magnitude is what the model found, not assumed) ===")
    ohe = pipeline.named_steps["preprocess"].named_transformers_["cat"]
    feature_names = NUMERIC_FEATURES + list(ohe.get_feature_names_out(CATEGORICAL_FEATURES)) + BOOLEAN_FEATURES
    coefs = pipeline.named_steps["model"].coef_[0]
    for name, coef in sorted(zip(feature_names, coefs), key=lambda x: -abs(x[1])):
        print(f"  {name:40s} {coef:+.4f}")

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_DIR / "baseline_logreg.joblib"
    joblib.dump(pipeline, model_path)
    meta = {
        "feature_cols": feature_cols,
        "n_train_rows": len(X_train), "n_test_rows": len(X_test),
        "n_train_bouts": int(df["bout_id"].iloc[train_idx].nunique()),
        "n_test_bouts": int(df["bout_id"].iloc[test_idx].nunique()),
        "test_roc_auc": float(roc_auc_score(y_test, y_pred_test)),
        "test_log_loss": float(log_loss(y_test, y_pred_test)),
        "test_brier": float(brier_score_loss(y_test, y_pred_test)),
    }
    (MODEL_DIR / "baseline_logreg_meta.json").write_text(json.dumps(meta, indent=2))
    print(f"\n[DONE] Model saved to {model_path}")


if __name__ == "__main__":
    main()
