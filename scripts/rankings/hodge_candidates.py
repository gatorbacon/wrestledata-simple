#!/usr/bin/env python3
"""
Compute simple Hodge Trophy front-runner metrics for a season.

For each NCAA weight class, this script:
  - Looks at wrestlers ranked in the TOP 10 of that weight
    (based on `mt/rankings_data/{season}/rankings_{weight}.json`)
  - Uses match data from `weight_class_{weight}.json` to compute:
        * Win percentage
        * Bonus percentage (F/TF/MD/INJ/MFF wins)
        * Fall percentage (F wins)
  - Collects all such wrestlers across weights and prints a
    combined table sorted by:
        1) Win percentage (descending)
        2) Bonus percentage (descending)
        3) Fall percentage (descending)

This is intentionally read‑only and console‑only for now.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set


BONUS_CODES = {"F", "TF", "MD", "INJ", "MFF"}
FALL_CODES = {"F"}


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
class HodgeStats:
    wrestler_id: str
    name: str
    team: str
    weight_class: str
    weight_rank: int = 999
    wins: int = 0
    losses: int = 0
    bonus_wins: int = 0
    fall_wins: int = 0
    ranked_wins: int = 0
    top10_wins: int = 0
    ranked_bonus_wins: int = 0
    # Detailed dominance + quality data
    decisions: int = 0
    majors: int = 0
    techs: int = 0
    pins: int = 0
    ranked_win_ranks: List[int] = field(default_factory=list)
    # Dominance accumulators for S_DOM (Top-50 weighted team points)
    dom_weighted_tp_num: float = 0.0
    dom_weighted_tp_den: float = 0.0
    dom_unranked_tp_sum: float = 0.0
    dom_unranked_matches: int = 0
    # Scores from hodge_formula.md
    s_wl: float = 0.0
    s_rec: float = 0.0
    s_qual: float = 0.0
    s_dom: float = 0.0
    s_pins: float = 0.0
    hodge_score: float = 0.0

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
    rank_lookup: Dict[str, int],
    top_n: int = 10,
    starters_only: bool = False,
) -> List[HodgeStats]:
    """
    Compute HodgeStats for ranked wrestlers in a single weight.
    
    If starters_only is True, only wrestlers explicitly marked as starters
    in the rankings JSON (entry['is_starter'] == True) are considered when
    building the candidate list for that weight.
    """
    wrestlers: Dict[str, Dict] = wc_data["wrestlers"]
    matches: List[Dict] = wc_data["matches"]

    if not rankings:
        return []

    # Map wrestler_id -> overall rank
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

    # Collect ranked wrestler IDs (respect their order), optionally
    # restricted to official starters only.
    top_ranked_ids: List[str] = []
    for entry in rankings:
        wid = entry.get("wrestler_id")
        if not wid or wid not in wrestlers:
            continue
        if starters_only and not entry.get("is_starter", False):
            continue
        top_ranked_ids.append(wid)
        if len(top_ranked_ids) >= top_n:
            break

    if not top_ranked_ids:
        return []

    # Initialize stats for those wrestlers
    stats: Dict[str, HodgeStats] = {}
    for wid in top_ranked_ids:
        info = wrestlers[wid]
        stats[wid] = HodgeStats(
            wrestler_id=wid,
            name=info.get("name", f"ID:{wid}"),
            team=info.get("team", "Unknown"),
            weight_class=weight,
            weight_rank=rank_by_id.get(wid, 999),
        )

    # Iterate matches once and update stats for involved top-10 wrestlers
    for m in matches:
        w1 = m.get("wrestler1_id")
        w2 = m.get("wrestler2_id")
        winner = m.get("winner_id")
        result = m.get("result", "") or ""
        code = classify_result_type(result)

        # Only process matches that involve at least one tracked wrestler
        if w1 not in stats and w2 not in stats:
            continue

        # Skip NC for win/loss accounting
        if code == "NC":
            continue

        # Helper to update stats for one side of the match
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

                # Dominance detail by result type
                if code == "F":
                    s.pins += 1
                elif code == "TF":
                    s.techs += 1
                elif code == "MD":
                    s.majors += 1
                elif code == "D":
                    s.decisions += 1

                # Dominance accumulators for S_DOM (team points weighted by opponent rank)
                tp = 0
                if code == "D":
                    tp = 3
                elif code == "MD":
                    tp = 4
                elif code == "TF":
                    tp = 5
                elif code == "F":
                    tp = 6
                if tp > 0:
                    opp_rank = rank_lookup.get(opp_id) if opp_id else None
                    if opp_rank is not None and 1 <= opp_rank <= 50:
                        weight = 1.0 + (50.0 - float(opp_rank)) / 49.0
                    else:
                        weight = 0.50
                    s.dom_weighted_tp_num += tp * weight
                    s.dom_weighted_tp_den += weight

                    # Track unranked dominance separately for optional penalty
                    if opp_rank is None or opp_rank > 50:
                        s.dom_unranked_tp_sum += tp
                        s.dom_unranked_matches += 1

                # Ranked opponent metrics (current top-33 in same/adjacent weights)
                if opp_id and opp_id in ranked_opponent_ids:
                    s.ranked_wins += 1
                    if code in BONUS_CODES:
                        s.ranked_bonus_wins += 1
                    if opp_id in top10_opponent_ids:
                        s.top10_wins += 1

                    # For quality-of-competition scoring we also record the
                    # actual rank (1-25) of each ranked opponent win when known.
                    opp_rank = rank_lookup.get(opp_id)
                    if opp_rank is not None and opp_rank <= 25:
                        s.ranked_win_ranks.append(opp_rank)
            else:
                s.losses += 1

        update_for(w1, w2)
        update_for(w2, w1)

    return list(stats.values())


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compute Hodge Trophy front-runner metrics for top-10 ranked wrestlers "
            "in each weight class."
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
        default="mt/rankings_html",
        help="Directory to save HTML Hodge report (subdir per season will be created)",
    )
    parser.add_argument(
        "-top-n",
        type=int,
        default=10,
        help="Number of ranked wrestlers per weight class to consider (default: 10)",
    )
    parser.add_argument(
        "-maxloss",
        type=int,
        default=0,
        help=(
            "Maximum number of losses allowed for inclusion in the report "
            "(default: 0, i.e. only undefeated wrestlers)."
        ),
    )
    parser.add_argument(
        "-minmatch",
        type=int,
        default=1,
        help=(
            "Minimum number of total matches required for inclusion "
            "(default: 1; set to 0 to include 0-0 wrestlers)."
        ),
    )
    args = parser.parse_args()

    season = args.season
    data_dir = args.data_dir
    output_root = Path(args.output_dir)

    wc_by_weight = load_weight_classes(season, data_dir)

    # Only consider numeric weight classes (e.g., '125', '133')
    numeric_weights = sorted(
        [w for w in wc_by_weight.keys() if w.isdigit()],
        key=lambda w: int(w),
    )

    # Preload rankings and build top-10 / top-33 sets per weight
    rankings_by_weight: Dict[str, Optional[List[Dict]]] = {}
    top10_ids_by_weight: Dict[str, Set[str]] = {}
    top33_ids_by_weight: Dict[str, Set[str]] = {}
    # Global rank lookup (wid -> best rank across all weights)
    global_rank_lookup: Dict[str, int] = {}

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
                # Track global best rank for quality/weight-class scoring
                if wid not in global_rank_lookup or r < global_rank_lookup[wid]:
                    global_rank_lookup[wid] = r
        top10_ids_by_weight[weight] = top10
        top33_ids_by_weight[weight] = top33

    all_candidates: List[HodgeStats] = []
    # For histograms: stats for all ranked (top-33) starters across weights
    all_ranked_for_hist: List[HodgeStats] = []

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

        # For primary Hodge candidate list, use only official starters.
        stats_starters = compute_stats_for_weight(
            weight,
            wc_data,
            rankings,
            ranked_ids,
            top10_ids,
            global_rank_lookup,
            top_n=args.top_n,
            starters_only=True,
        )
        all_candidates.extend(stats_starters)

        # For histograms: collect stats for all starters ranked in the top-33
        starter_rankings_33: List[Dict] = []
        if rankings:
            for entry in rankings:
                if not entry.get("is_starter", False):
                    continue
                wid = entry.get("wrestler_id")
                rank = entry.get("rank")
                if not wid or rank is None:
                    continue
                try:
                    r = int(rank)
                except (TypeError, ValueError):
                    continue
                if r <= 33:
                    starter_rankings_33.append(entry)

        if starter_rankings_33:
            hist_stats = compute_stats_for_weight(
                weight,
                wc_data,
                starter_rankings_33,
                ranked_ids,
                top10_ids,
                global_rank_lookup,
                top_n=len(starter_rankings_33),
                starters_only=True,
            )
            all_ranked_for_hist.extend(hist_stats)

    # Apply loss and match-count filters
    filtered_candidates: List[HodgeStats] = [
        s
        for s in all_candidates
        if s.losses <= args.maxloss and s.total_matches >= args.minmatch
    ]

    # --- Compute numeric Hodge scores (per hodge_formula.md) ---

    def compute_s_wl(rank_val: int) -> float:
        if rank_val == 1:
            return 100.0
        # S_WL = max(0, 80 - 10 * (wc_rank - 2))
        return max(0.0, 80.0 - 10.0 * (rank_val - 2))

    def compute_s_rec(wins: int, losses: int) -> float:
        total = wins + losses
        if total <= 0:
            return 0.0
        win_pct = wins / total
        if win_pct < 0.85:
            s = 0.0
        else:
            s = min(100.0, (win_pct - 0.85) / 0.15 * 100.0)
        if losses == 0:
            s = min(100.0, s + 5.0)
        return s

    def value_for_rank(r: Optional[int]) -> float:
        if r is None:
            return 0.0
        if r <= 10:
            return 10.0 + (11 - r)
        if r <= 25:
            return 5.0 + (26 - r) / 3.0
        return 0.0

    def compute_s_qual(ranks: List[int]) -> float:
        if not ranks:
            return 0.0
        raw_quality = sum(value_for_rank(r) for r in ranks)
        top10_wins_local = sum(1 for r in ranks if r <= 10)
        s = min(100.0, (raw_quality / 120.0) * 100.0)
        s = min(100.0, s + 2.0 * min(top10_wins_local, 5))
        return s

    def compute_s_dom(
        weighted_tp_num: float,
        weighted_tp_den: float,
        unranked_tp_sum: float,
        unranked_matches: int,
    ) -> float:
        """
        Compute S_DOM per s_dom_spec.txt.

        - Use team-points per match (DEC=3, MD=4, TF=5, PIN=6)
          weighted by opponent quality on a Top-50 scale.
        - Map weighted average team points in [3.0, 6.0] to [0, 100].
        - Optionally apply a small penalty for weak dominance vs unranked
          opponents (avg team points < 3.2).
        """
        if weighted_tp_den <= 0.0:
            return 0.0

        # Weighted average dominance across all opponents.
        avg_tp_weighted = weighted_tp_num / weighted_tp_den
        if avg_tp_weighted <= 3.0:
            return 0.0

        s_dom = min(100.0, (avg_tp_weighted - 3.0) / 3.0 * 100.0)

        # Optional weak-opponent penalty based on unranked dominance only.
        if unranked_matches > 0:
            avg_tp_unranked = unranked_tp_sum / float(unranked_matches)
            if avg_tp_unranked < 3.2:
                penalty = min(10.0, (3.2 - avg_tp_unranked) * 10.0)
                s_dom = max(0.0, s_dom - penalty)

        return s_dom

    def compute_s_pins(pins: int, wins: int) -> float:
        if wins <= 0 or pins <= 0:
            return 0.0
        pin_pct = pins / wins
        if pin_pct <= 0.10:
            return 0.0
        if pin_pct >= 0.60:
            return 100.0
        return (pin_pct - 0.10) / 0.50 * 100.0

    W_WL = 0.25
    W_REC = 0.20
    W_QUAL = 0.25
    W_DOM = 0.20
    W_PINS = 0.10

    for s in filtered_candidates:
        s.s_wl = compute_s_wl(s.weight_rank)
        s.s_rec = compute_s_rec(s.wins, s.losses)
        s.s_qual = compute_s_qual(s.ranked_win_ranks)
        s.s_dom = compute_s_dom(
            s.dom_weighted_tp_num,
            s.dom_weighted_tp_den,
            s.dom_unranked_tp_sum,
            s.dom_unranked_matches,
        )
        s.s_pins = compute_s_pins(s.pins, s.wins)
        s.hodge_score = (
            W_WL * s.s_wl
            + W_REC * s.s_rec
            + W_QUAL * s.s_qual
            + W_DOM * s.s_dom
            + W_PINS * s.s_pins
        )

    def green_scale01(t: float) -> str:
        """
        Map t in [0,1] to a light-to-dark green hex color.
        t=0 -> very light green, t=1 -> dark green.
        """
        t = max(0.0, min(1.0, t))
        # Light and dark green RGB anchors
        light = (230, 244, 234)  # #e6f4ea
        dark = (21, 87, 36)      # #155724
        r = int(light[0] + (dark[0] - light[0]) * t)
        g = int(light[1] + (dark[1] - light[1]) * t)
        b = int(light[2] + (dark[2] - light[2]) * t)
        return f"#{r:02x}{g:02x}{b:02x}"

    # Sort candidates by overall Hodge formula score (primary) then by weight rank.
    scored_candidates = sorted(
        filtered_candidates, key=lambda s: (-s.hodge_score, s.weight_rank)
    )

    # --- Report 1: summary view (sorted by HodgeScore) ---

    print(
        f"\nHodge Trophy candidate metrics for season {season} "
        f"(top {args.top_n} per weight, max losses={args.maxloss}, "
        f"min matches={args.minmatch}, "
        f"sorted by HodgeScore):\n"
    )
    header = (
        f"{'#':>3}  {'Name':<25} {'Team':<20} {'Wt':>4}  "
        f"{'W-L':>7}  {'Win%':>6}  {'Bonus%':>7}  {'Fall%':>6}  "
        f"{'RkW':>4}  {'Top10W':>6}  {'RkBon%':>7}"
    )
    print(header)
    print("-" * len(header))

    for idx, s in enumerate(scored_candidates, start=1):
        wl = f"{s.wins}-{s.losses}"
        print(
            f"{idx:>3}  {s.name:<25.25} {s.team:<20.20} {s.weight_class:>4}  "
            f"{wl:>7}  {s.win_pct:6.3f}  {s.bonus_pct:7.3f}  {s.fall_pct:6.3f}  "
            f"{s.ranked_wins:4d}  {s.top10_wins:6d}  {s.ranked_bonus_pct:7.3f}"
        )

    # --- Report 2: detailed Hodge formula scores (score-based sort) ---

    print(
        f"\nDetailed Hodge formula scores for season {season} "
        f"(same candidate set, sorted by HodgeScore):\n"
    )
    detail_header = (
        f"{'#':>3}  {'Name':<25} {'Team':<20} {'Wt':>4}  "
        f"{'W-L':>7}  "
        f"{'Score':>7}  {'WtCl':>4}  {'Qual':>7}  {'Dom':>7}  {'Pin%':>7}"
    )
    print(detail_header)
    print("-" * len(detail_header))

    for idx, s in enumerate(scored_candidates, start=1):
        wl = f"{s.wins}-{s.losses}"
        pin_pct_display = s.fall_pct * 100.0
        print(
            f"{idx:>3}  {s.name:<25.25} {s.team:<20.20} {s.weight_class:>4}  "
            f"{wl:>7}  "
            f"{s.hodge_score:7.2f}  {s.weight_rank:4d}  {s.s_qual:7.1f}  "
            f"{s.s_dom:7.1f}  {pin_pct_display:7.1f}"
        )

    # --- Generate HTML report (both tables) ---
    season_dir = output_root / str(season)
    season_dir.mkdir(parents=True, exist_ok=True)
    html_path = season_dir / f"hodge_{season}.html"

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        f"<meta charset='utf-8'>",
        f"<title>Hodge Trophy Candidates - Season {season}</title>",
        "<style>",
        "body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }",
        "h1 { margin-top: 0; }",
        ".meta { margin-bottom: 16px; color: #555; }",
        "table { border-collapse: collapse; width: 100%; font-size: 12px; background-color: #fff; }",
        "th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: center; }",
        "th { background-color: #f0f0f0; position: sticky; top: 0; z-index: 2; }",
        "thead th { white-space: nowrap; }",
        "tbody tr:nth-child(even) { background-color: #fafafa; }",
        "tbody tr:hover { background-color: #f1f7ff; }",
        ".name-cell { text-align: left; }",
        ".team-cell { text-align: left; }",
        "</style>",
        "</head>",
        "<body>",
        f"<h1>Hodge Trophy Candidates &mdash; Season {season}</h1>",
        f"<div class='meta'>",
        f"Top {args.top_n} per weight class; max losses={args.maxloss}, "
        f"min matches={args.minmatch}. Ranked wins and bonus stats computed "
        f"against current top-33 in the same and adjacent weights. ",
        f"Generated at {generated_at}.",
        "</div>",
    ]

    # First: detailed Hodge formula scores table (the "formula" view).
    html.extend(
        [
            "<h2>Hodge Formula Scores (sorted by HodgeScore)</h2>",
            "<table>",
            "<thead>",
            "<tr>",
            "<th>#</th>",
            "<th>Name</th>",
            "<th>Team</th>",
            "<th>Wt</th>",
            "<th>W-L</th>",
            "<th>Score</th>",
            "<th>WtCl Rank</th>",
            "<th>Quality<br>of Competition</th>",
            "<th>Dominance Score</th>",
            "<th>Pin%</th>",
            "</tr>",
            "</thead>",
            "<tbody>",
        ]
    )

    # Precompute rank range for WtCl coloring so best rank is darkest, worst is lightest.
    rank_values = [s.weight_rank for s in scored_candidates if s.weight_rank < 999]
    if rank_values:
        min_rank = min(rank_values)
        max_rank = max(rank_values)
    else:
        min_rank = 1
        max_rank = 1

    for idx, s in enumerate(scored_candidates, start=1):
        wl = f"{s.wins}-{s.losses}"
        # Rank: map best ranks (lowest value) to dark green, worst (highest) to light.
        if max_rank > min_rank:
            rank_t = (max_rank - float(s.weight_rank)) / (max_rank - min_rank)
            rank_t = max(0.0, min(1.0, rank_t))
        else:
            rank_t = 1.0
        wtcl_color = green_scale01(rank_t)
        # Quality, dominance, and pin scores get their own green shades based on 0–100 scale.
        qual_color = green_scale01(s.s_qual / 100.0)
        dom_color = green_scale01(s.s_dom / 100.0)
        pin_color = green_scale01(s.s_pins / 100.0)
        pin_pct_display = s.fall_pct * 100.0

        html.append(
            "<tr>"
            f"<td>{idx}</td>"
            f"<td class='name-cell'>{s.name}</td>"
            f"<td class='team-cell'>{s.team}</td>"
            f"<td>{s.weight_class}</td>"
            f"<td>{wl}</td>"
            f"<td>{s.hodge_score:.2f}</td>"
            f"<td style='background-color:{wtcl_color};'>{s.weight_rank}</td>"
            f"<td style='background-color:{qual_color};'>{s.s_qual:.1f}</td>"
            f"<td style='background-color:{dom_color};'>{s.s_dom:.1f}</td>"
            f"<td style='background-color:{pin_color};'>{pin_pct_display:.1f}</td>"
            "</tr>"
        )

    html.extend(
        [
            "</tbody>",
            "</table>",
        ]
    )

    # Then: high-level summary table.
    html.extend(
        [
            "<h2>Summary (sorted by HodgeScore)</h2>",
            "<table>",
            "<thead>",
            "<tr>",
            "<th>#</th>",
            "<th>Name</th>",
            "<th>Team</th>",
            "<th>Wt</th>",
            "<th>W-L</th>",
            "<th>Win%</th>",
            "<th>Bonus%</th>",
            "<th>Fall%</th>",
            "<th>RkW</th>",
            "<th>Top10W</th>",
            "<th>RkBon%</th>",
            "</tr>",
            "</thead>",
            "<tbody>",
        ]
    )

    for idx, s in enumerate(scored_candidates, start=1):
        wl = f"{s.wins}-{s.losses}"
        html.append(
            "<tr>"
            f"<td>{idx}</td>"
            f"<td class='name-cell'>{s.name}</td>"
            f"<td class='team-cell'>{s.team}</td>"
            f"<td>{s.weight_class}</td>"
            f"<td>{wl}</td>"
            f"<td>{s.win_pct:.3f}</td>"
            f"<td>{s.bonus_pct:.3f}</td>"
            f"<td>{s.fall_pct:.3f}</td>"
            f"<td>{s.ranked_wins}</td>"
            f"<td>{s.top10_wins}</td>"
            f"<td>{s.ranked_bonus_pct:.3f}</td>"
            "</tr>"
        )

    html.extend(
        [
            "</tbody>",
            "</table>",
            "</body>",
            "</html>",
        ]
    )

    with html_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(html))

    print(f"\nHTML report written to {html_path}\n")
    try:
        webbrowser.open(html_path.as_uri())
    except Exception:
        pass


if __name__ == "__main__":
    main()


