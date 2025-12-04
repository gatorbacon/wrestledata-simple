#!/usr/bin/env python3
"""
scoringbyrank.py

Generate rank-based scoring analytics for a given season and date range:
    1. Average Points vs Rank (with IQR band + median)
    2. Rank Tier Boxplots in tiers of 5 ranks (1–5, 6–10, 11–15, ...)

This uses the SAME data-loading logic as your original script:

  - Ranked wrestlers from:
        mt/rankings_data/<season>/rankings_*.json
  - Processed match data from:
        mt/processed_data/<season>/*.json

CLI:
    python scoringbyrank.py -season 2026 -startdate 110125 -enddate 123125

Output files:
    mt/graphics/<season>/avg_points_vs_rank_<start>_<end>.png
    mt/graphics/<season>/rank_tier_boxplots_<start>_<end>.png
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    from statsmodels.nonparametric.smoothers_lowess import lowess
except Exception:
    lowess = None


# ------------------------------------------------------------
# CLI Handling
# ------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scoring analytics vs rank for a wrestling season."
    )
    parser.add_argument("-season", type=int, help="Season year (e.g. 2026)")
    parser.add_argument("-startdate", type=str, help="Optional start MMDDYY")
    parser.add_argument("-enddate", type=str, help="Optional end MMDDYY")
    parser.add_argument(
        "-maxrank", type=int, default=50,
        help="Maximum rank to include (default 50)."
    )
    return parser.parse_args()


def prompt_for_missing(args: argparse.Namespace) -> argparse.Namespace:
    if args.season is None:
        args.season = int(input("Enter season (e.g. 2026): ").strip())

    if args.startdate is None:
        v = input("Enter start date MMDDYY (blank = no minimum): ").strip()
        args.startdate = v or None

    if args.enddate is None:
        v = input("Enter end date MMDDYY (blank = no maximum): ").strip()
        args.enddate = v or None

    return args


def _validate_mmddyy(label: str, value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if len(value) != 6 or not value.isdigit():
        raise ValueError(f"{label} must be MMDDYY (6 digits), got '{value}'.")
    return value


# ------------------------------------------------------------
# Rankings Loader
# ------------------------------------------------------------

def _load_rank_map(season: int) -> Dict[str, int]:
    base = Path("mt/rankings_data") / str(season)
    if not base.exists():
        raise FileNotFoundError(f"Rankings directory not found: {base}")

    rank_by_id: Dict[str, int] = {}

    for p in sorted(base.glob("rankings_*.json")):
        try:
            with p.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        for r in data.get("rankings", []):
            wid = str(r.get("wrestler_id") or "")
            raw_rank = r.get("rank")
            if not wid or raw_rank is None:
                continue
            try:
                rk = int(raw_rank)
            except Exception:
                continue

            if wid not in rank_by_id or rk < rank_by_id[wid]:
                rank_by_id[wid] = rk

    return rank_by_id


# ------------------------------------------------------------
# Match Score Parser
# ------------------------------------------------------------

def _parse_score_from_result(result: str) -> Optional[tuple[int, int]]:
    if not result:
        return None
    m = re.search(r"(\d+)\s*-\s*(\d+)", result)
    if not m:
        return None
    try:
        return int(m.group(1)), int(m.group(2))
    except ValueError:
        return None


# ------------------------------------------------------------
# Build Full Match DataFrame
# ------------------------------------------------------------

def build_matches_df(season: int, max_rank: int = 50) -> pd.DataFrame:
    rank_by_id = _load_rank_map(season)
    if not rank_by_id:
        raise ValueError(f"No ranked wrestlers found for season {season}")

    # Only keeep wrestlers <= max_rank
    rank_by_id = {wid: r for wid, r in rank_by_id.items() if r <= max_rank}

    data_dir = Path("mt/processed_data") / str(season)
    if not data_dir.exists():
        raise FileNotFoundError(f"Processed data directory not found: {data_dir}")

    rows: List[Dict] = []

    for team_file in sorted(data_dir.glob("*.json")):
        try:
            with team_file.open("r", encoding="utf-8") as f:
                team_data = json.load(f)
        except Exception:
            continue

        team_name = team_data.get("team_name", "Unknown")

        for wrestler in team_data.get("roster", []):
            wid = str(wrestler.get("season_wrestler_id") or "")
            if wid not in rank_by_id:
                continue

            rank = rank_by_id[wid]
            wname = wrestler.get("name", f"ID:{wid}")

            for match in wrestler.get("matches", []):
                score_pair = _parse_score_from_result(match.get("result", ""))
                if not score_pair:
                    continue

                winner_pts, loser_pts = score_pair
                date_raw = match.get("date", "")
                if not date_raw:
                    continue

                # Convert date -> MMDDYY
                try:
                    dt = datetime.strptime(date_raw, "%m/%d/%Y").date()
                    mmddyy = f"{dt.month:02}{dt.day:02}{dt.year % 100:02}"
                except Exception:
                    clean = date_raw.replace("/", "").replace("-", "")
                    if len(clean) == 6 and clean.isdigit():
                        mmddyy = clean
                    else:
                        continue

                winner_name = match.get("winner_name", "")
                winner_team = match.get("winner_team", "")
                loser_name = match.get("loser_name", "")
                loser_team = match.get("loser_team", "")

                is_winner = (wname == winner_name and team_name == winner_team)
                is_loser  = (wname == loser_name and team_name == loser_team)

                if not (is_winner or is_loser):
                    continue

                points_scored = float(winner_pts if is_winner else loser_pts)
                opponent_name = loser_name if is_winner else winner_name

                rows.append({
                    "wrestler_id": wid,
                    "wrestler_name": wname,
                    "team": team_name,
                    "opponent_name": opponent_name,
                    "points_scored": points_scored,
                    "date": mmddyy,
                    "rank": float(rank),
                })

    if not rows:
        raise ValueError("No ranked match data found.")

    return pd.DataFrame(rows)


# ------------------------------------------------------------
# Date Filtering
# ------------------------------------------------------------

def filter_by_date(df: pd.DataFrame, start_mmddyy: Optional[str], end_mmddyy: Optional[str]) -> pd.DataFrame:
    def _to_int(s: str) -> Optional[int]:
        if s and len(s) == 6 and s.isdigit():
            return int(s)
        return None

    df["date_int"] = df["date"].apply(_to_int)
    df = df.dropna(subset=["date_int"])
    df["date_int"] = df["date_int"].astype(int)

    if start_mmddyy:
        df = df[df["date_int"] >= int(start_mmddyy)]
    if end_mmddyy:
        df = df[df["date_int"] <= int(end_mmddyy)]

    return df


# ------------------------------------------------------------
# Plot #1: Average Points vs Rank + IQR
# ------------------------------------------------------------

def plot_avg_with_iqr(df: pd.DataFrame, season: int, start_mmddyy: Optional[str], end_mmddyy: Optional[str]) -> Path:
    df["rank"] = df["rank"].astype(int)
    df["points_scored"] = df["points_scored"].astype(float)

    grouped = df.groupby("rank")["points_scored"]
    avg = grouped.mean()
    p25 = grouped.quantile(0.25)
    p75 = grouped.quantile(0.75)
    median = grouped.median()

    ranks = avg.index.to_numpy()

    plt.figure(figsize=(12, 7))

    # IQR shaded area
    plt.fill_between(ranks, p25, p75, color="skyblue", alpha=0.3, label="IQR (25–75%)")

    # Average line
    plt.plot(ranks, avg, color="blue", linewidth=3, label="Average")

    # Median line
    plt.plot(ranks, median, color="black", linestyle="--", linewidth=2, label="Median")

    start_label = start_mmddyy or "start"
    end_label = end_mmddyy or "end"

    plt.xlabel("Rank")
    plt.ylabel("Points Scored")
    plt.title(f"Average Points vs Rank — Season {season} ({start_label}–{end_label})")
    plt.legend()

    out_dir = Path(f"mt/graphics/{season}")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"avg_points_vs_rank_{start_label}_{end_label}.png"
    plt.tight_layout()
    plt.savefig(out_path, dpi=300)
    plt.close()

    print(f"Saved: {out_path}")
    return out_path


# ------------------------------------------------------------
# Plot #2: Rank Tier Boxplots
# ------------------------------------------------------------

def plot_rank_tier_boxplots(
    df: pd.DataFrame, season: int, start_mmddyy: Optional[str], end_mmddyy: Optional[str]
) -> Path:
    """
    Boxplot of points scored by 5-rank tiers (1–5, 6–10, 11–15, ...),
    with light color styling to make the plot more readable.
    """
    df["rank"] = df["rank"].astype(int)
    df["points_scored"] = df["points_scored"].astype(float)

    max_rank_in_data = int(df["rank"].max())

    tier_data: List[pd.Series] = []
    labels: List[str] = []

    # Dynamic tiers of width 5: 1–5, 6–10, ..., up to the max rank present
    for low in range(1, max_rank_in_data + 1, 5):
        high = min(low + 4, max_rank_in_data)
        subset = df[(df["rank"] >= low) & (df["rank"] <= high)]["points_scored"]
        if subset.empty:
            continue
        tier_data.append(subset)
        labels.append(f"{low}–{high}")

    if not tier_data:
        raise ValueError("No data available to plot rank tier boxplots.")

    plt.figure(figsize=(12, 7))

    bp = plt.boxplot(
        tier_data,
        labels=labels,
        showfliers=False,
        patch_artist=True,  # enable colored boxes
        medianprops={"color": "black", "linewidth": 2},
        boxprops={"linewidth": 1.5},
        whiskerprops={"linewidth": 1.2},
        capprops={"linewidth": 1.2},
    )

    # Use a smooth blue–green colormap across tiers
    cmap = plt.cm.get_cmap("viridis")
    n_boxes = len(bp["boxes"])
    for i, box in enumerate(bp["boxes"]):
        color = cmap(i / max(1, n_boxes - 1))
        box.set_facecolor(color)
        box.set_alpha(0.75)

    # --------------------------------------------------------
    # Highlight consistent top‑5 wrestlers (ranks 1–5 only):
    #  - Compute avg number of matches per wrestler in 1–5
    #  - Keep wrestlers with at least 50% of that many matches
    #  - Among them, find the top 3 and bottom 3 average scorers
    #  - Plot them as labeled dots on the 1–5 tier with leader lines
    # --------------------------------------------------------
    top5_df = df[(df["rank"] >= 1) & (df["rank"] <= 5)]
    if not top5_df.empty and "wrestler_id" in top5_df.columns:
        per_wrestler = (
            top5_df.groupby("wrestler_id")
            .agg(
                matches=("points_scored", "size"),
                avg_points=("points_scored", "mean"),
                name=("wrestler_name", "first"),
            )
            .reset_index()
        )

        if not per_wrestler.empty:
            avg_matches = per_wrestler["matches"].mean()
            threshold = 0.5 * avg_matches
            eligible = per_wrestler[per_wrestler["matches"] >= threshold]

            if not eligible.empty and labels:
                # Find x-position of the 1–5 tier (first tier that starts at 1)
                try:
                    tier_index = next(
                        i for i, lbl in enumerate(labels) if lbl.startswith("1–")
                    )
                except StopIteration:
                    tier_index = 0
                x_pos = tier_index + 1  # boxplot positions are 1-based

                # Top 3 by average points
                top_three = (
                    eligible.sort_values("avg_points", ascending=False)
                    .head(3)
                    .itertuples(index=False)
                )
                # Bottom 3 by average points
                bottom_three = (
                    eligible.sort_values("avg_points", ascending=True)
                    .head(3)
                    .itertuples(index=False)
                )

                # Plot and label dots for each selected wrestler, with slight
                # vertical offsets and arrows to avoid text overlap.
                def _plot_labeled_points(rows, color, side: str):
                    rows = list(rows)
                    if not rows:
                        return

                    # Sort rows so that label order matches y-position order,
                    # which keeps the leader lines from crossing.
                    if side == "right":
                        # Top scorers: highest avg_points at the top
                        rows.sort(key=lambda r: r.avg_points, reverse=True)
                        offsets = np.linspace(0.6, -0.6, len(rows))
                        x_offset = 0.35
                        ha = "left"
                    else:
                        # Bottom scorers: lowest avg_points at the bottom
                        rows.sort(key=lambda r: r.avg_points)
                        offsets = np.linspace(-0.6, 0.6, len(rows))
                        x_offset = -0.6
                        ha = "right"

                    for idx, row in enumerate(rows):
                        y_val = row.avg_points
                        label = f"{row.name} ({y_val:.1f} ppm)"
                        plt.scatter(
                            x_pos,
                            y_val,
                            color=color,
                            s=40,
                            zorder=4,
                            edgecolors="black",
                            linewidths=0.5,
                        )
                        plt.annotate(
                            label,
                            xy=(x_pos, y_val),
                            xytext=(x_pos + x_offset, y_val + offsets[idx]),
                            va="center",
                            ha=ha,
                            fontsize=8,
                            color=color,
                            bbox={
                                "boxstyle": "round,pad=0.2",
                                "fc": "white",
                                "ec": color,
                                "alpha": 0.8,
                            },
                            arrowprops={
                                "arrowstyle": "-",
                                "color": color,
                                "linewidth": 1.0,
                            },
                        )

                _plot_labeled_points(top_three, color="red", side="right")
                _plot_labeled_points(bottom_three, color="orange", side="left")

    # Light horizontal grid for easier comparison of medians/IQRs
    plt.grid(axis="y", linestyle="--", alpha=0.3)

    start_label = start_mmddyy or "start"
    end_label = end_mmddyy or "end"

    plt.xlabel("Rank Tier (5-Rank Buckets)")
    plt.ylabel("Points Scored")
    plt.title(
        f"Points Scored by 5-Rank Tiers — Season {season} ({start_label}–{end_label})"
    )

    out_dir = Path(f"mt/graphics/{season}")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"rank_tier_boxplots_{start_label}_{end_label}.png"
    plt.tight_layout()
    plt.savefig(out_path, dpi=300)
    plt.close()

    print(f"Saved: {out_path}")
    return out_path


# ------------------------------------------------------------
# Main Execution
# ------------------------------------------------------------

def main() -> None:
    args = parse_args()
    args = prompt_for_missing(args)

    try:
        start_mmddyy = _validate_mmddyy("startdate", args.startdate) if args.startdate else None
        end_mmddyy = _validate_mmddyy("enddate", args.enddate) if args.enddate else None
    except ValueError as e:
        print(f"Error: {e}")
        return

    try:
        df = build_matches_df(args.season, max_rank=args.maxrank)
    except Exception as e:
        print(e)
        return

    df = df.dropna(subset=["rank", "points_scored"])
    df = filter_by_date(df, start_mmddyy, end_mmddyy)
    if df.empty:
        print("No matches found after date filtering.")
        return

    # NEW VISUALIZATIONS
    plot_avg_with_iqr(df, args.season, start_mmddyy, end_mmddyy)
    plot_rank_tier_boxplots(df, args.season, start_mmddyy, end_mmddyy)


if __name__ == "__main__":
    main()