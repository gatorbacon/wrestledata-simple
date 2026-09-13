#!/usr/bin/env python3
"""
Generates the underlying prediction data behind the win-probability model
explainer chart (an Artifact, not part of the site) -- sweeps one feature
at a time through the fitted model, holding everything else at a typical
("evenly matched, tied") baseline, so the abstract coefficients turn into
actual predicted percentages a non-technical reader can look at directly.

Two curves, chosen to make the two headline findings visible rather than
just quoting their coefficients:
  1. Win probability vs. score differential, one line per "how much time is
     left" scenario -- shows the score_diff x time_fraction interaction:
     the same lead is worth more late than early.
  2. Win probability vs. net riding time advantage, tied game -- shows both
     the smooth trend AND the discrete jump right at the 60-second rule
     threshold.
Plus the raw coefficient list for a simple magnitude/direction bar chart.

Usage:
    python scripts/win_prob/generate_viz_data.py
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PBP_DIR = PROJECT_ROOT / "data/pbp"
MODEL_DIR = PBP_DIR / "models"

# "Evenly matched, tied game" baseline -- isolates the state effects being
# charted without either wrestler's own quality skewing the curve.
BASELINE = {
    "subject_dpg": 2.4, "opponent_dpg": 2.4,
    "subject_position": "neutral",
    "subject_stalling_warned": False, "opponent_stalling_warned": False,
    "subject_is_flip_winner_filled": False,
    "riding_time_net_sec": 0.0, "subject_riding_time_criterion_met_filled": False,
    "period": "2",
}
FEATURE_COLS = [
    "score_diff", "time_fraction_remaining", "score_diff_x_time_fraction",
    "subject_dpg", "opponent_dpg", "riding_time_net_sec",
    "period", "subject_position",
    "subject_stalling_warned", "opponent_stalling_warned", "subject_is_flip_winner_filled",
    "subject_riding_time_criterion_met_filled",
]


def make_row(**overrides):
    row = dict(BASELINE)
    row.update(overrides)
    row["score_diff_x_time_fraction"] = row.get("score_diff", 0) * row.get("time_fraction_remaining", 0)
    return row


def predict(pipeline, rows):
    df = pd.DataFrame(rows)[FEATURE_COLS]
    return pipeline.predict_proba(df)[:, 1]


def main():
    pipeline = joblib.load(MODEL_DIR / "baseline_logreg.joblib")

    # --- Curve 1: score differential x time remaining ---
    score_range = list(range(-10, 11))
    time_scenarios = [
        ("Lots of time left", 0.9),
        ("Halfway through the period", 0.5),
        ("10 seconds left in the period", 10 / 120),
        ("Buzzer about to sound", 0.02),
    ]
    curve1 = []
    for label, frac in time_scenarios:
        rows = [make_row(score_diff=s, time_fraction_remaining=frac) for s in score_range]
        probs = predict(pipeline, rows)
        curve1.append({"label": label, "time_fraction": frac,
                        "points": [{"score_diff": s, "win_prob": float(p)} for s, p in zip(score_range, probs)]})

    # --- Curve 2: net riding time advantage, tied game ---
    riding_range = list(range(-90, 91, 5))
    rows2 = [make_row(score_diff=0, time_fraction_remaining=0.5,
                       riding_time_net_sec=r, subject_riding_time_criterion_met_filled=r >= 60)
             for r in riding_range]
    probs2 = predict(pipeline, rows2)
    curve2 = [{"riding_net_sec": r, "win_prob": float(p)} for r, p in zip(riding_range, probs2)]

    # --- Coefficients (already printed by fit_baseline_model.py; regenerated here for the chart) ---
    ohe = pipeline.named_steps["preprocess"].named_transformers_["cat"]
    categorical_features = ["period", "subject_position"]
    boolean_features = [
        "subject_stalling_warned", "opponent_stalling_warned", "subject_is_flip_winner_filled",
        "subject_riding_time_criterion_met_filled",
    ]
    numeric_features = [
        "score_diff", "time_fraction_remaining", "score_diff_x_time_fraction",
        "subject_dpg", "opponent_dpg", "riding_time_net_sec",
    ]
    feature_names = numeric_features + list(ohe.get_feature_names_out(categorical_features)) + boolean_features
    coefs = pipeline.named_steps["model"].coef_[0]
    coefficients = sorted(
        [{"feature": n, "coef": float(c)} for n, c in zip(feature_names, coefs)],
        key=lambda x: -abs(x["coef"]),
    )

    out = {"curve1_score_by_time": curve1, "curve2_riding_time": curve2, "coefficients": coefficients}
    out_path = PBP_DIR / "viz_data.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"[DONE] wrote {out_path}")


if __name__ == "__main__":
    main()
