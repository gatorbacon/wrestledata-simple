#!/usr/bin/env python3
"""
Lookup + local plotting for the win-probability model (Phase 6, "any match
-> a plot" step). Two ways to pick matches:

  --tournament ncaa --year 2026 --round Final
      plots every bout matching those filters (one weight class each,
      subject = the eventual winner)

  --winner "Luke Lilledahl" [--tournament ncaa --year 2026]
      finds and plots that wrestler's bout(s), narrowed by any filters given

Saves a single PNG locally (matplotlib) -- this is a local file, NOT a
published Claude Artifact (see feedback_no_artifacts_without_approval).

Usage:
    python scripts/win_prob/plot_matches.py --tournament ncaa --year 2026 --round Final \
        --out data/pbp/plots/2026_ncaa_finals.png
    python scripts/win_prob/plot_matches.py --winner "Luke Lilledahl" --year 2026
"""

import argparse
import math
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from compute_match_win_prob import compute_trace, PBP_DIR, MODEL_DIR


def find_bouts(df: pd.DataFrame, tournament=None, year=None, weight=None, round_=None, winner=None) -> pd.DataFrame:
    """Returns one row per matching bout (subject_side == 'winner'), i.e. the
    key columns needed to call compute_trace for each."""
    sub = df[df["subject_side"] == "winner"] if "subject_side" in df.columns else df
    if tournament:
        sub = sub[sub.tournament == tournament]
    if year:
        sub = sub[sub.year == year]
    if weight:
        sub = sub[sub.weight == weight]
    if round_:
        sub = sub[sub["round"].str.lower() == round_.lower()]
    if winner:
        sub = sub[sub.subject_name.str.lower() == winner.lower()]
    return sub.drop_duplicates(subset=["tournament", "year", "weight", "bout_number"])[
        ["tournament", "year", "weight", "bout_number", "subject_name", "opponent_name", "round"]
    ].sort_values("weight")


def plot_grid(traces: list[dict], out_path: Path):
    n = len(traces)
    cols = min(5, n) if n > 1 else 1
    rows = math.ceil(n / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 4.2, rows * 3.2), squeeze=False)

    for i, t in enumerate(traces):
        ax = axes[i // cols][i % cols]
        xs = [p["elapsed_sec"] for p in t["trace"]]
        ys = [p["win_prob"] * 100 for p in t["trace"]]
        ax.plot(xs, ys, color="#1f5fae", linewidth=1.8)
        ax.fill_between(xs, ys, 50, where=[y >= 50 for y in ys], color="#1f5fae", alpha=0.15)
        ax.fill_between(xs, ys, 50, where=[y < 50 for y in ys], color="#c6011f", alpha=0.15)
        ax.axhline(50, color="#999", linestyle="--", linewidth=0.8)
        for period_end in t["period_starts"].values():
            if 0 < period_end < t["match_length_sec"]:
                ax.axvline(period_end, color="#ddd", linewidth=0.8)
        for e in t["events"]:
            if e["action"] not in ("match_start", "choice", "defer"):
                ax.scatter([e["elapsed_sec"]], [e["win_prob"] * 100], s=14, color="#1f5fae", zorder=3)
        ax.set_ylim(0, 100)
        ax.set_xlim(0, t["match_length_sec"])
        title = f"{t['weight']} lbs: {t['subject_name']} {t['final_subject_score']}-{t['final_opponent_score']} {t['opponent_name']}"
        ax.set_title(title, fontsize=8.5)
        ax.tick_params(labelsize=7)

    for j in range(n, rows * cols):
        axes[j // cols][j % cols].axis("off")

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    print(f"[DONE] wrote {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tournament", default=None)
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--weight", type=int, default=None)
    ap.add_argument("--round", dest="round_", default=None)
    ap.add_argument("--winner", default=None)
    ap.add_argument("--out", default="data/pbp/plots/matches.png")
    args = ap.parse_args()

    df = pd.read_csv(PBP_DIR / "training_rows.csv", low_memory=False)
    model = joblib.load(MODEL_DIR / "baseline_logreg.joblib")

    bouts = find_bouts(df, args.tournament, args.year, args.weight, args.round_, args.winner)
    if bouts.empty:
        raise SystemExit("No bouts matched those filters.")
    print(f"Found {len(bouts)} bout(s):")
    for _, b in bouts.iterrows():
        print(f"  {b.tournament} {b.year} {b.weight}lbs {b['round']}: {b.subject_name} def {b.opponent_name} (bout {b.bout_number})")

    traces = [
        compute_trace(df, model, b.tournament, b.year, b.weight, b.bout_number, b.subject_name)
        for _, b in bouts.iterrows()
    ]
    plot_grid(traces, Path(args.out))


if __name__ == "__main__":
    main()
