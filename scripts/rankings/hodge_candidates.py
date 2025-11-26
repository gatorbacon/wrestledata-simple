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
import json
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
) -> List[HodgeStats]:
    """Compute HodgeStats for top-N ranked wrestlers in a single weight."""
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

    # Collect top-N ranked wrestler IDs (respect their order)
    top_ranked_ids: List[str] = []
    for entry in rankings:
        if len(top_ranked_ids) >= top_n:
            break
        wid = entry.get("wrestler_id")
        if wid and wid in wrestlers:
            top_ranked_ids.append(wid)

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
            global_rank_lookup,
            top_n=args.top_n,
        )
        all_candidates.extend(stats)

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

    def compute_s_dom(dec: int, maj: int, tf: int, pins: int, total: int) -> float:
        if total <= 0:
            return 0.0
        team_points = dec * 3 + maj * 4 + tf * 5 + pins * 6
        avg_tp = team_points / total
        if avg_tp <= 3.0:
            return 0.0
        return min(100.0, (avg_tp - 3.0) / 3.0 * 100.0)

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
        s.s_dom = compute_s_dom(s.decisions, s.majors, s.techs, s.pins, s.total_matches)
        s.s_pins = compute_s_pins(s.pins, s.wins)
        s.hodge_score = (
            W_WL * s.s_wl
            + W_REC * s.s_rec
            + W_QUAL * s.s_qual
            + W_DOM * s.s_dom
            + W_PINS * s.s_pins
        )

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
        f"{'Rank':>4}  {'W-L':>7}  "
        f"{'Score':>7}  {'S_WL':>7}  {'S_REC':>7}  {'S_QUAL':>7}  {'S_DOM':>7}  {'S_PINS':>7}"
    )
    print(detail_header)
    print("-" * len(detail_header))

    for idx, s in enumerate(scored_candidates, start=1):
        wl = f"{s.wins}-{s.losses}"
        print(
            f"{idx:>3}  {s.name:<25.25} {s.team:<20.20} {s.weight_class:>4}  "
            f"{s.weight_rank:4d}  {wl:>7}  "
            f"{s.hodge_score:7.2f}  {s.s_wl:7.1f}  {s.s_rec:7.1f}  {s.s_qual:7.1f}  "
            f"{s.s_dom:7.1f}  {s.s_pins:7.1f}"
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
            "<h2>Hodge Formula Scores (sorted by HodgeScore)</h2>",
            "<table>",
            "<thead>",
            "<tr>",
            "<th>#</th>",
            "<th>Name</th>",
            "<th>Team</th>",
            "<th>Wt</th>",
            "<th>Rank</th>",
            "<th>W-L</th>",
            "<th>Score</th>",
            "<th>S_WL</th>",
            "<th>S_REC</th>",
            "<th>S_QUAL</th>",
            "<th>S_DOM</th>",
            "<th>S_PINS</th>",
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
            f"<td>{s.weight_rank}</td>"
            f"<td>{wl}</td>"
            f"<td>{s.hodge_score:.2f}</td>"
            f"<td>{s.s_wl:.1f}</td>"
            f"<td>{s.s_rec:.1f}</td>"
            f"<td>{s.s_qual:.1f}</td>"
            f"<td>{s.s_dom:.1f}</td>"
            f"<td>{s.s_pins:.1f}</td>"
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


if __name__ == "__main__":
    main()


