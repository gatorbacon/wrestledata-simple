#!/usr/bin/env python3
"""
scoringbyrank.py

Generate a match-level scatter plot showing the relationship between
rank and points scored for a given season (and optional date range).

Specification summary (from scoringbyrank_spec.txt), adapted to current data:

  - Input:
        Ranked wrestlers from:
            mt/rankings_data/<season>/rankings_*.json
        Match lists per wrestler from processed team files:
            mt/processed_data/<season>/*.json
    For each ranked wrestler, we build match-level rows using their team
    JSON `matches` array:
        wrestler_id, wrestler_name, team, opponent_id, opponent_name,
        points_scored (actual match points for that wrestler), date (MMDDYY), rank
  - CLI:
        python scoringbyrank.py -season 2026 -startdate 120125 -enddate 123125
    Dates are MMDDYY strings. If any args are missing, the script
    prompts interactively.
  - Output:
        mt/graphics/<season>/scoring_by_rank_<start>_<end>.png
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
except Exception:  # pragma: no cover - optional dependency
    lowess = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scatter plot of points scored vs rank for a season."
    )
    parser.add_argument("-season", type=int, help="Season year (e.g. 2026)")
    parser.add_argument(
        "-startdate",
        type=str,
        help="Optional start date (MMDDYY). If omitted, no lower bound.",
    )
    parser.add_argument(
        "-enddate",
        type=str,
        help="Optional end date (MMDDYY). If omitted, no upper bound.",
    )
    parser.add_argument(
        "-maxrank",
        type=int,
        default=50,
        help="Maximum rank to include (default: 50).",
    )
    return parser.parse_args()


def prompt_for_missing(args: argparse.Namespace) -> argparse.Namespace:
    if args.season is None:
        args.season = int(input("Enter season (e.g. 2026): ").strip())

    if args.startdate is None:
        val = input("Enter start date (MMDDYY, or blank for no minimum): ").strip()
        args.startdate = val or None

    if args.enddate is None:
        val = input("Enter end date (MMDDYY, or blank for no maximum): ").strip()
        args.enddate = val or None

    if args.maxrank is None:
        val = input("Enter max rank to include (default 50): ").strip()
        args.maxrank = int(val) if val else 50

    return args


def _validate_mmddyy(label: str, value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = value.strip()
    if not v:
        return None
    if len(v) != 6 or not v.isdigit():
        raise ValueError(f"{label} must be MMDDYY (6 digits), got '{value}'.")
    return v


def _load_rank_map(season: int) -> Dict[str, int]:
    """
    Build a map from wrestler_id -> best (lowest) rank across all weights.
    """
    base = Path("mt/rankings_data") / str(season)
    if not base.exists():
        raise FileNotFoundError(f"Rankings data directory not found: {base}")

    rank_by_id: Dict[str, int] = {}
    for path in sorted(base.glob("rankings_*.json")):
        try:
            with path.open("r", encoding="utf-8") as f:
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
            except (TypeError, ValueError):
                continue
            if wid not in rank_by_id or rk < rank_by_id[wid]:
                rank_by_id[wid] = rk
    return rank_by_id


def _parse_score_from_result(result: str) -> Optional[tuple[int, int]]:
    """
    Extract (winner_points, loser_points) from a result string, e.g.:
        "TF 18-3 5:38" -> (18, 3)
        "Dec 11-5"     -> (11, 5)
    Returns None if no score pair is found.
    """
    if not result:
        return None
    m = re.search(r"(\d+)\s*-\s*(\d+)", result)
    if not m:
        return None
    try:
        return int(m.group(1)), int(m.group(2))
    except ValueError:
        return None


def build_matches_df(season: int, max_rank: int = 50) -> pd.DataFrame:
    """
    Build a match-level DataFrame using team-level processed data.

    For each ranked wrestler (any weight):
      - Look up their processed matches in mt/processed_data/<season>/*.json.
      - For each match where we can determine winner/loser and parse a score,
        add one row giving that wrestler's actual match points.
    
    Args:
        season: The season year (e.g. 2026).
        max_rank: Only include wrestlers ranked <= max_rank (default 50).
    """
    rank_by_id = _load_rank_map(season)
    if not rank_by_id:
        raise ValueError(f"No ranked wrestlers found for season {season}.")
    
    # Filter to only include wrestlers within max_rank
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
            if not wid or wid not in rank_by_id:
                continue  # not a ranked wrestler

            rank = rank_by_id[wid]
            wrestler_name = wrestler.get("name", f"ID:{wid}")

            for match in wrestler.get("matches", []):
                result = (match.get("result") or "").strip()
                score_pair = _parse_score_from_result(result)
                if not score_pair:
                    # If we can't parse a score, skip this match.
                    continue

                winner_pts, loser_pts = score_pair
                date_raw = (match.get("date") or "").strip()
                if not date_raw:
                    continue

                # Convert date to MMDDYY.
                mmddyy: Optional[str]
                try:
                    dt = datetime.strptime(date_raw, "%m/%d/%Y").date()
                    mmddyy = f"{dt.month:02}{dt.day:02}{dt.year % 100:02}"
                except Exception:
                    clean = date_raw.replace("-", "").replace("/", "")
                    if len(clean) == 6 and clean.isdigit():
                        mmddyy = clean
                    else:
                        continue

                opponent_name = ""
                opponent_id = match.get("opponent_id")

                # Determine if this wrestler is winner or loser via names/teams.
                winner_name = match.get("winner_name", "")
                winner_team = match.get("winner_team", "")
                loser_name = match.get("loser_name", "")
                loser_team = match.get("loser_team", "")

                is_winner = (
                    wrestler_name == winner_name and team_name == winner_team
                )
                is_loser = (
                    wrestler_name == loser_name and team_name == loser_team
                )

                if not (is_winner or is_loser):
                    # Can't confidently orient the score, skip.
                    continue

                if is_winner:
                    points_scored = float(winner_pts)
                    opponent_name = loser_name
                else:
                    points_scored = float(loser_pts)
                    opponent_name = winner_name

                rows.append(
                    {
                        "wrestler_id": wid,
                        "wrestler_name": wrestler_name,
                        "team": team_name,
                        "opponent_id": opponent_id,
                        "opponent_name": opponent_name,
                        "points_scored": points_scored,
                        "date": mmddyy,
                        "rank": float(rank),
                    }
                )

    if not rows:
        raise ValueError(
            f"No ranked match data could be built for season {season} "
            f"from mt/processed_data/{season}."
        )

    return pd.DataFrame(rows)


def filter_by_date(
    df: pd.DataFrame, start_mmddyy: Optional[str], end_mmddyy: Optional[str]
) -> pd.DataFrame:
    """
    Filter matches by inclusive MMDDYY date range.

    The `date` field in the input is expected to be MMDDYY or something
    convertible to an integer like 120125.
    """
    if "date" not in df.columns:
        return df

    # Dates are stored as MMDDYY strings; convert to integers like 120125.
    def _to_int(s: str) -> Optional[int]:
        if s is None:
            return None
        s = str(s).strip()
        if not s:
            return None
        if len(s) == 6 and s.isdigit():
            return int(s)
        return None

    date_int = df["date"].apply(_to_int)
    df = df.assign(date_int=date_int)
    df = df.dropna(subset=["date_int"])
    df["date_int"] = df["date_int"].astype(int)

    if start_mmddyy:
        df = df[df["date_int"] >= int(start_mmddyy)]
    if end_mmddyy:
        df = df[df["date_int"] <= int(end_mmddyy)]
    return df


def jitter(values: np.ndarray, amount: float = 0.15) -> np.ndarray:
    """Apply symmetric uniform jitter to a 1D array."""
    return values + np.random.uniform(-amount, amount, size=len(values))


def make_plot(
    df: pd.DataFrame, season: int, start_mmddyy: Optional[str], end_mmddyy: Optional[str]
) -> Path:
    # Prepare X/Y
    ranks = df["rank"].astype(float).to_numpy()
    points = df["points_scored"].astype(float).to_numpy()

    x = jitter(ranks, amount=0.15)
    y = points

    plt.figure(figsize=(12, 7))
    plt.scatter(x, y, alpha=0.25, s=4)

    # LOWESS curve overlay (optional if statsmodels is available)
    if lowess is not None:
        try:
            smoothed = lowess(y, ranks, frac=0.2)
            plt.plot(smoothed[:, 0], smoothed[:, 1], color="black", linewidth=2)
        except Exception as exc:  # pragma: no cover
            print(f"Warning: LOWESS smoothing failed ({exc}); continuing without curve.")

    start_label = start_mmddyy or "start"
    end_label = end_mmddyy or "end"

    plt.xlabel("Rank")
    plt.ylabel("Points Scored")
    plt.title(f"Points Scored vs Rank — Season {season} ({start_label}–{end_label})")

    out_dir = Path(f"mt/graphics/{season}")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"scoring_by_rank_{start_label}_{end_label}.png"
    plt.tight_layout()
    plt.savefig(out_path, dpi=300)
    plt.close()
    print(f"Saved: {out_path}")
    return out_path


def main() -> None:
    args = parse_args()
    args = prompt_for_missing(args)

    try:
        start_mmddyy = _validate_mmddyy("startdate", args.startdate)
        end_mmddyy = _validate_mmddyy("enddate", args.enddate)
    except ValueError as e:
        print(f"Error: {e}")
        return

    try:
        df = build_matches_df(args.season, max_rank=args.maxrank)
    except (FileNotFoundError, ValueError) as e:
        print(e)
        return

    # Drop rows missing essential fields (defensive; build_matches_df should
    # already guarantee these columns exist).
    df = df.dropna(subset=["rank", "points_scored"])
    if df.empty:
        print("No matches with both rank and points_scored available.")
        return

    df = filter_by_date(df, start_mmddyy, end_mmddyy)
    if df.empty:
        print("No matches found for the given date range.")
        return

    make_plot(df, args.season, start_mmddyy, end_mmddyy)


if __name__ == "__main__":
    main()


