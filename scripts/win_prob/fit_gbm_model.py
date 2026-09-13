#!/usr/bin/env python3
"""
Phase 3b: gradient-boosted upgrade to the logistic-regression baseline.

Why: fixing match_time_fraction_remaining (see fit_baseline_model.py) exposed
a real limit of a LINEAR model -- the empirical data shows a 1-point lead
wins ~99% of the time in the final 3% of a match but only ~66% of the time
with a full match still ahead (checked directly against training_rows.csv,
2026-09-13). That's a steep, non-linear relationship between score_diff and
time remaining, and a single interaction coefficient can only fit one
constant slope for it -- logistic regression tops out around 72% for the
"1 up, 1% of the match left" case, far short of the data's actual 99%.
A tree-based model doesn't need this interaction hand-specified: it can
split on time and score jointly and learn the curve directly.

Reuses fit_baseline_model.load_data() so both models train on identical
rows/features -- comparable ROC-AUC/log-loss/Brier and comparable train/test
splits (same GroupShuffleSplit random_state).

Usage:
    python scripts/win_prob/fit_gbm_model.py
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score, log_loss, brier_score_loss
from sklearn.model_selection import GroupShuffleSplit

from fit_baseline_model import (
    NUMERIC_FEATURES, CATEGORICAL_FEATURES, BOOLEAN_FEATURES,
    PBP_DIR, MODEL_DIR, load_data, reliability_table,
)

FEATURE_COLS = NUMERIC_FEATURES + CATEGORICAL_FEATURES + BOOLEAN_FEATURES


def main():
    df = load_data()
    print(f"Loaded {len(df)} rows, {df['bout_id'].nunique()} bouts")

    X = df[FEATURE_COLS].copy()
    for c in CATEGORICAL_FEATURES:
        X[c] = X[c].astype("category")
    y = df["label"].values
    groups = df["bout_id"].values

    splitter = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    train_idx, test_idx = next(splitter.split(X, y, groups))
    X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]
    print(f"Train: {len(X_train)} rows / {df['bout_id'].iloc[train_idx].nunique()} bouts")
    print(f"Test:  {len(X_test)} rows / {df['bout_id'].iloc[test_idx].nunique()} bouts")

    model = HistGradientBoostingClassifier(
        categorical_features="from_dtype",
        max_iter=300, max_depth=6, learning_rate=0.06,
        l2_regularization=1.0, early_stopping=True, random_state=42,
    )
    model.fit(X_train, y_train)

    y_pred_train = model.predict_proba(X_train)[:, 1]
    y_pred_test = model.predict_proba(X_test)[:, 1]

    print("\n=== Held-out test performance ===")
    print(f"  ROC-AUC:     {roc_auc_score(y_test, y_pred_test):.4f}")
    print(f"  Log loss:    {log_loss(y_test, y_pred_test):.4f}")
    print(f"  Brier score: {brier_score_loss(y_test, y_pred_test):.4f}")
    print(f"  (train ROC-AUC: {roc_auc_score(y_train, y_pred_train):.4f} -- compare to test to check for overfitting)")

    print("\n=== Calibration (test set, 10 bins by predicted probability) ===")
    print(reliability_table(y_test, y_pred_test).to_string())

    # crunch-time sanity check: does it now find the ~99% empirical rate
    # for "1 up, almost no match time left"?
    check_rows = pd.DataFrame([
        {"score_diff": 1, "match_time_fraction_remaining": f,
         "score_diff_x_match_time_fraction": 1 * f,
         "subject_dpg": 3.0, "opponent_dpg": 3.0, "riding_time_net_sec": 0.0,
         "period": "3", "subject_position": "neutral",
         "subject_stalling_warned": False, "opponent_stalling_warned": False,
         "subject_is_flip_winner_filled": False, "subject_riding_time_criterion_met_filled": False}
        for f in [1.0, 0.5, 0.2, 0.05, 0.01]
    ])
    for c in CATEGORICAL_FEATURES:
        check_rows[c] = check_rows[c].astype("category")
    probs = model.predict_proba(check_rows[FEATURE_COLS])[:, 1]
    print("\n=== Crunch-time check: DPG-even, up 1 in period 3, varying match time left ===")
    for f, p in zip([1.0, 0.5, 0.2, 0.05, 0.01], probs):
        print(f"  match_frac={f:.2f} -> {p*100:.1f}%")

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_DIR / "gbm_model.joblib"
    joblib.dump(model, model_path)
    meta = {
        "feature_cols": FEATURE_COLS, "categorical_features": CATEGORICAL_FEATURES,
        "n_train_rows": len(X_train), "n_test_rows": len(X_test),
        "n_train_bouts": int(df["bout_id"].iloc[train_idx].nunique()),
        "n_test_bouts": int(df["bout_id"].iloc[test_idx].nunique()),
        "test_roc_auc": float(roc_auc_score(y_test, y_pred_test)),
        "test_log_loss": float(log_loss(y_test, y_pred_test)),
        "test_brier": float(brier_score_loss(y_test, y_pred_test)),
    }
    (MODEL_DIR / "gbm_model_meta.json").write_text(json.dumps(meta, indent=2))
    print(f"\n[DONE] Model saved to {model_path}")


if __name__ == "__main__":
    main()
