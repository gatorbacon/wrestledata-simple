#!/usr/bin/env python3
"""
Precomputes win-probability traces for the Lab win-probability page and
writes them as website-ready JSON -- per CLAUDE.md's static-site rule, the
frontend never runs the model itself, it just fetches this file.

Currently hardcoded to the 2026 NCAA finals (the Lab page's starting set);
extend MATCH_SETS as more matches/pages are added.

Usage:
    python scripts/win_prob/export_matches_for_site.py
"""

import json
from pathlib import Path

import joblib
import pandas as pd

from compute_match_win_prob import compute_trace, PBP_DIR, MODEL_DIR
from plot_matches import find_bouts

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = PROJECT_ROOT / "frontend/wrestledata-ui/public/data/win_prob"

MATCH_SETS = [
    {
        "key": "2026_ncaa_finals",
        "title": "2026 NCAA Championship Finals",
        "filters": {"tournament": "ncaa", "year": 2026, "round_": "Final"},
    },
]


def main():
    df = pd.read_csv(PBP_DIR / "training_rows.csv", low_memory=False)
    model = joblib.load(MODEL_DIR / "baseline_logreg.joblib")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for match_set in MATCH_SETS:
        bouts = find_bouts(df, **match_set["filters"])
        traces = [
            compute_trace(df, model, b.tournament, b.year, b.weight, b.bout_number, b.subject_name)
            for _, b in bouts.iterrows()
        ]
        traces.sort(key=lambda t: t["weight"])
        out = {"title": match_set["title"], "matches": traces}
        out_path = OUT_DIR / f"{match_set['key']}.json"
        out_path.write_text(json.dumps(out))
        print(f"[DONE] {match_set['key']}: {len(traces)} matches -> {out_path}")


if __name__ == "__main__":
    main()
