#!/usr/bin/env python3
"""
Compute a simple "Freshman of the Year" report for a season.

This mirrors the Hodge Trophy metrics, but filters to wrestlers
who are listed as true freshmen or redshirt freshmen in the
team/weight-class data (grade == 'Fr.' or 'RS Fr.').

Behavior:
  - For each NCAA weight class, look at wrestlers ranked in the TOP N
    of that weight (default: 10) based on
        mt/rankings_data/{season}/rankings_{weight}.json
  - Restrict to those whose grade is 'Fr.' or 'RS Fr.' in
        mt/rankings_data/{season}/weight_class_{weight}.json
  - Use the same match data and metrics as hodge_candidates.py:
        * Win percentage
        * Bonus percentage (F/TF/MD/INJ/MFF wins)
        * Fall percentage (F wins)
        * Ranked wins (current top‑33 in same/adjacent weights)
        * Top‑10 wins (current top‑10 in same/adjacent weights)
        * Ranked bonus percentage
  - Sort across all weights by:
        1) Win percentage (desc)
        2) Bonus percentage (desc)
        3) Ranked bonus percentage (desc)
        4) Fall percentage (desc)
        5) Total matches (desc)
  - Print a console table and emit an HTML report:
        mt/rankings_html/{season}/freshman_{season}.html
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set


BONUS_CODES = {"F", "TF", "MD", "INJ", "MFF"}
FALL_CODES = {"F"}
FRESHMAN_GRADES = {"Fr.", "RS Fr."}


def classify_result_type(result: str) -> str:
    """
    Roughly classify a result string into a simple code.
    Mirrors the logic used in `generate_matrix.py`, but kept local here.
    """
    if not result:
        return "O"

    r = result.lower()

    # Medical forfeit
    if "mffl" in r or "m. for." in r or "medical forfeit" in r:
        return "MFF"

    # No contest
    clean = r.strip()
    if clean == "nc" or "no contest" in clean:
        return "NC"

    # Injury-related
    if "inj" in r or "injury" in r:
        return "INJ"

    # Falls (non-injury)
    if "fall" in r or " pin" in r or r.startswith("fall"):
        return "F"

    # Technical fall
    if "tf" in r or "technical fall" in r:
        return "TF"

    # Major decision
    if "md" in r or "major" in r:
        return "MD"

    # Regular decision (incl. sudden victory)
    if "dec" in r or "sv-" in r:
        return "D"

    return "O"


@dataclass
class FreshmanStats:
    wrestler_id: str
    name: str
    team: str
    weight_class: str
    grade: str
    weight_rank: int
    wins: int = 0
    losses: int = 0
    bonus_wins: int = 0
    fall_wins: int = 0
    ranked_wins: int = 0
    top10_wins: int = 0
    ranked_bonus_wins: int = 0

    @property
    def total_matches(self) -> int:
        return self.wins + self.losses

    @property
    def win_pct(self) -> float:
        return (self.wins / self.total_matches) if self.total_matches > 0 else 0.0

    @property
    def bonus_pct(self) -> float:
        return (self.bonus_wins / self.wins) if self.wins > 0 else 0.0

    @property
    def fall_pct(self) -> float:
        return (self.fall_wins / self.wins) if self.wins > 0 else 0.0

    @property
    def ranked_bonus_pct(self) -> float:
        return (self.ranked_bonus_wins / self.ranked_wins) if self.ranked_wins > 0 else 0.0


def load_weight_classes(season: int, data_dir: str) -> Dict[str, Dict]:
    """Load all `weight_class_*.json` files for a season."""
    base = Path(data_dir) / str(season)
    if not base.exists():
        raise FileNotFoundError(f"Data directory not found: {base}")

    result: Dict[str, Dict] = {}
    for wc_file in sorted(base.glob("weight_class_*.json")):
        weight = wc_file.stem.replace("weight_class_", "")
        with wc_file.open("r", encoding="utf-8") as f:
            result[weight] = json.load(f)
    return result


def load_grade_overrides(data_dir: str) -> Dict[str, str]:
    """
    Load grade overrides from mt/rankings_data/grade_overrides.json.
    Returns mapping wrestler_id -> override_grade.
    """
    path = Path(data_dir) / "grade_overrides.json"
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}

    overrides: Dict[str, str] = {}
    for o in data.get("overrides", []):
        wid = o.get("wrestler_id")
        grade = o.get("grade")
        if wid and grade:
            overrides[wid] = grade
    return overrides


def load_rankings_for_weight(
    season: int, weight: str, data_dir: str
) -> Optional[List[Dict]]:
    """
    Load rankings_{weight}.json for a weight class, if present.
    Returns list of ranking entries or None.
    """
    rankings_path = Path(data_dir) / str(season) / f"rankings_{weight}.json"
    if not rankings_path.exists():
        return None
    with rankings_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("rankings", [])


def compute_stats_for_weight(
    weight: str,
    wc_data: Dict,
    rankings: Optional[List[Dict]],
    ranked_opponent_ids: Set[str],
    top10_opponent_ids: Set[str],
    top_n: int = 10,
) -> List[FreshmanStats]:
    """Compute FreshmanStats for top-N ranked freshmen in a single weight."""
    wrestlers: Dict[str, Dict] = wc_data["wrestlers"]
    matches: List[Dict] = wc_data["matches"]

    if not rankings:
        return []

    # Map wrestler_id -> overall rank from rankings file
    rank_by_id: Dict[str, int] = {}
    for entry in rankings:
        wid = entry.get("wrestler_id")
        rank = entry.get("rank")
        if not wid or rank is None:
            continue
        try:
            r = int(rank)
        except (TypeError, ValueError):
            continue
        rank_by_id[wid] = r

    # Collect wrestler IDs whose overall RANK is <= top_n, but only freshmen.
    # This mirrors the Hodge script semantics: "top N by rank", then we filter.
    top_ranked_ids: List[str] = []
    for entry in rankings:
        wid = entry.get("wrestler_id")
        rank = entry.get("rank")
        if not wid or rank is None:
            continue
        if wid not in wrestlers:
            continue
        # Only consider wrestlers whose *overall* rank is within top_n
        try:
            r = int(rank)
        except (TypeError, ValueError):
            continue
        if r > top_n:
            continue

        grade = wrestlers[wid].get("grade", "")
        if grade not in FRESHMAN_GRADES:
            continue
        top_ranked_ids.append(wid)

    if not top_ranked_ids:
        return []

    # Initialize stats for those wrestlers
    stats: Dict[str, FreshmanStats] = {}
    for wid in top_ranked_ids:
        info = wrestlers[wid]
        stats[wid] = FreshmanStats(
            wrestler_id=wid,
            name=info.get("name", f"ID:{wid}"),
            team=info.get("team", "Unknown"),
            weight_class=weight,
            grade=info.get("grade", ""),
            weight_rank=rank_by_id.get(wid, 999),
        )

    # Iterate matches once and update stats for involved freshmen
    for m in matches:
        w1 = m.get("wrestler1_id")
        w2 = m.get("wrestler2_id")
        winner = m.get("winner_id")
        result = m.get("result", "") or ""
        code = classify_result_type(result)

        # Only process matches that involve at least one tracked freshman
        if w1 not in stats and w2 not in stats:
            continue

        # Skip NC for win/loss accounting
        if code == "NC":
            continue

        def update_for(wid: str, opp_id: Optional[str]) -> None:
            if wid not in stats:
                return
            s = stats[wid]
            if winner == wid:
                s.wins += 1
                if code in BONUS_CODES:
                    s.bonus_wins += 1
                if code in FALL_CODES:
                    s.fall_wins += 1

                # Ranked opponent metrics (current top-33 in same/adjacent weights)
                if opp_id and opp_id in ranked_opponent_ids:
                    s.ranked_wins += 1
                    if code in BONUS_CODES:
                        s.ranked_bonus_wins += 1
                    if opp_id in top10_opponent_ids:
                        s.top10_wins += 1
            else:
                s.losses += 1

        update_for(w1, w2)
        update_for(w2, w1)

    return list(stats.values())


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compute Freshman of the Year metrics for top-ranked freshmen "
            "in each weight class (grades 'Fr.' and 'RS Fr.')."
        )
    )
    parser.add_argument("-season", type=int, required=True, help="Season year (e.g., 2026)")
    parser.add_argument(
        "-data-dir",
        default="mt/rankings_data",
        help="Directory containing weight_class_*.json and rankings_*.json",
    )
    parser.add_argument(
        "-output-dir",
        default="frontend/wrestledata-ui/public/data/awards/freshman",
        help="Directory to save JSON Freshman report (subdir per season will be created)",
    )
    parser.add_argument(
        "-top-n",
        type=int,
        default=10,
        help="Number of ranked wrestlers per weight class to consider (default: 10)",
    )
    args = parser.parse_args()

    season = args.season
    data_dir = args.data_dir
    output_root = Path(args.output_dir)

    wc_by_weight = load_weight_classes(season, data_dir)

    # Apply grade overrides, if any
    grade_overrides = load_grade_overrides(data_dir)
    if grade_overrides:
        for wc_data in wc_by_weight.values():
            wrestlers = wc_data.get("wrestlers", {})
            for wid, info in wrestlers.items():
                if wid in grade_overrides:
                    info["grade"] = grade_overrides[wid]

    # Only consider numeric weight classes (e.g., '125', '133')
    numeric_weights = sorted(
        [w for w in wc_by_weight.keys() if w.isdigit()],
        key=lambda w: int(w),
    )

    # Preload rankings and build top-10 / top-33 sets per weight
    rankings_by_weight: Dict[str, Optional[List[Dict]]] = {}
    top10_ids_by_weight: Dict[str, Set[str]] = {}
    top33_ids_by_weight: Dict[str, Set[str]] = {}

    for weight in numeric_weights:
        rankings = load_rankings_for_weight(season, weight, data_dir)
        rankings_by_weight[weight] = rankings
        top10: Set[str] = set()
        top33: Set[str] = set()
        if rankings:
            for entry in rankings:
                wid = entry.get("wrestler_id")
                rank = entry.get("rank")
                if not wid or rank is None:
                    continue
                try:
                    r = int(rank)
                except (TypeError, ValueError):
                    continue
                if r <= 10:
                    top10.add(wid)
                if r <= 33:
                    top33.add(wid)
        top10_ids_by_weight[weight] = top10
        top33_ids_by_weight[weight] = top33

    all_candidates: List[FreshmanStats] = []

    # For each weight, build the set of ranked/top10 opponent IDs from
    # the current and adjacent weight classes only.
    for idx, weight in enumerate(numeric_weights):
        wc_data = wc_by_weight[weight]
        rankings = rankings_by_weight.get(weight)
        if not rankings:
            continue

        neighbor_weights = [weight]
        if idx > 0:
            neighbor_weights.append(numeric_weights[idx - 1])
        if idx < len(numeric_weights) - 1:
            neighbor_weights.append(numeric_weights[idx + 1])

        ranked_ids: Set[str] = set()
        top10_ids: Set[str] = set()
        for w in neighbor_weights:
            ranked_ids.update(top33_ids_by_weight.get(w, set()))
            top10_ids.update(top10_ids_by_weight.get(w, set()))

        stats = compute_stats_for_weight(
            weight,
            wc_data,
            rankings,
            ranked_ids,
            top10_ids,
            top_n=args.top_n,
        )
        all_candidates.extend(stats)

    # Calculate FreshScore for each candidate
    # Find max values for normalization
    if all_candidates:
        max_ranked_wins = max(s.ranked_wins for s in all_candidates) if all_candidates else 1
        max_top10_wins = max(s.top10_wins for s in all_candidates) if all_candidates else 1
    else:
        max_ranked_wins = 1
        max_top10_wins = 1

    # Calculate FreshScore: weighted sum of normalized components
    # Weights: Win% 20%, Bonus% 20%, Pin% 20%, RankedBonus% 20%, RankedWins 10%, Top10Wins 10%
    for s in all_candidates:
        # Percentage components (already 0-1 scale, convert to 0-100)
        win_pct_score = s.win_pct * 100
        bonus_pct_score = s.bonus_pct * 100
        pin_pct_score = s.fall_pct * 100
        ranked_bonus_pct_score = s.ranked_bonus_pct * 100

        # Count components (normalize by max, then convert to 0-100)
        ranked_wins_score = (s.ranked_wins / max_ranked_wins * 100) if max_ranked_wins > 0 else 0
        top10_wins_score = (s.top10_wins / max_top10_wins * 100) if max_top10_wins > 0 else 0

        # Weighted sum
        fresh_score = (
            win_pct_score * 0.20 +
            bonus_pct_score * 0.20 +
            pin_pct_score * 0.20 +
            ranked_bonus_pct_score * 0.20 +
            ranked_wins_score * 0.10 +
            top10_wins_score * 0.10
        )
        s.fresh_score = fresh_score

    # Sort by FreshScore descending
    all_candidates.sort(key=lambda s: -s.fresh_score)

    print(
        f"\nFreshman of the Year candidate metrics for season {season} "
        f"(top {args.top_n} freshmen per weight, sorted by FreshScore):\n"
    )
    header = (
        f"{'#':>3}  {'Name':<25} {'Team':<20} {'Wt':>4}  "
        f"{'W-L':>7}  {'Win%':>6}  {'Bonus%':>7}  {'Pin%':>6}  "
        f"{'# RankedWins':>12}  {'# Top10Wins':>11}  {'RankedBon%':>10}  {'FreshScore':>10}"
    )
    print(header)
    print("-" * len(header))

    for idx, s in enumerate(all_candidates, start=1):
        wl = f"{s.wins}-{s.losses}"
        print(
            f"{idx:>3}  {s.name:<25.25} {s.team:<20.20} {s.weight_class:>4}  "
            f"{wl:>7}  {s.win_pct:6.3f}  {s.bonus_pct:7.3f}  {s.fall_pct:6.3f}  "
            f"{s.ranked_wins:12d}  {s.top10_wins:11d}  {s.ranked_bonus_pct:10.3f}  {s.fresh_score:10.2f}"
        )

    # --- Generate JSON report ---
    season_dir = output_root / str(season)
    season_dir.mkdir(parents=True, exist_ok=True)
    json_path = season_dir / f"freshman_{season}.json"

    generated_at = datetime.now(timezone.utc).isoformat()

    # Build JSON structure
    rows = []
    for idx, s in enumerate(all_candidates, start=1):
        rows.append({
            "rank": idx,
            "wrestler_id": s.wrestler_id,
            "name": s.name,
            "team": s.team,
            "weight": int(s.weight_class) if s.weight_class.isdigit() else s.weight_class,
            "weight_rank": s.weight_rank,
            "grade": s.grade,
            "wins": s.wins,
            "losses": s.losses,
            "record": f"{s.wins}-{s.losses}",
            "metrics": {
                "win_pct": round(s.win_pct, 3),
                "bonus_pct": round(s.bonus_pct, 3),
                "fall_pct": round(s.fall_pct, 3),
                "ranked_wins": s.ranked_wins,
                "top10_wins": s.top10_wins,
                "ranked_bonus_pct": round(s.ranked_bonus_pct, 3),
            },
            "fresh_score": round(s.fresh_score, 2)
        })

    json_data = {
        "season": season,
        "generated_at": generated_at,
        "description": (
            f"Top {args.top_n} ranked freshmen per weight class (grades 'Fr.' and 'RS Fr.'). "
            "Ranked wins and bonus stats computed against current top-33 in the same and adjacent weights."
        ),
        "rows": rows
    }

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)

    print(f"\nJSON report written to {json_path}\n")


if __name__ == "__main__":
    main()


