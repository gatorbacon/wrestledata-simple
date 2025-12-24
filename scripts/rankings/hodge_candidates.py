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
from datetime import datetime, timezone
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
    eligible: bool = True
    eligibility_reason: Optional[str] = None
    component_data: Dict = field(default_factory=dict)

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
        default="frontend/wrestledata-ui/public/data/awards/hodge",
        help="Directory to save JSON Hodge report (subdir per season will be created)",
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

    # Apply loss and match-count filters (pre-filtering before eligibility check)
    # Note: Eligibility gate is checked AFTER scoring, so we don't filter here
    # based on losses == 0. The eligibility function will handle that.
    filtered_candidates: List[HodgeStats] = [
        s
        for s in all_candidates
        if s.total_matches >= args.minmatch
    ]

    # --- Compute numeric Hodge scores (NEW SPEC: no weight-class rank in score) ---

    def compute_s_rec(wins: int, losses: int) -> tuple[float, dict]:
        """Compute record score and return (score, raw_data)."""
        total = wins + losses
        raw = {
            "wins": wins,
            "losses": losses,
            "win_pct": wins / total if total > 0 else 0.0
        }
        if total <= 0:
            return (0.0, raw)
        win_pct = wins / total
        if win_pct < 0.85:
            s = 0.0
        else:
            s = min(100.0, (win_pct - 0.85) / 0.15 * 100.0)
        if losses == 0:
            s = min(100.0, s + 5.0)
        return (s, raw)

    def value_for_rank(r: Optional[int]) -> float:
        if r is None:
            return 0.0
        if r <= 10:
            return 10.0 + (11 - r)
        if r <= 25:
            return 5.0 + (26 - r) / 3.0
        return 0.0

    def compute_s_qual(ranks: List[int], ranked_wins: int, top10_wins: int) -> tuple[float, dict]:
        """Compute quality score and return (score, raw_data)."""
        raw = {
            "ranked_wins": ranked_wins,
            "top10_wins": top10_wins,
            "raw_quality": 0.0
        }
        if not ranks:
            return (0.0, raw)
        raw_quality = sum(value_for_rank(r) for r in ranks)
        raw["raw_quality"] = raw_quality
        top10_wins_local = sum(1 for r in ranks if r <= 10)
        s = min(100.0, (raw_quality / 120.0) * 100.0)
        s = min(100.0, s + 2.0 * min(top10_wins_local, 5))
        return (s, raw)

    def compute_s_dom(
        weighted_tp_num: float,
        weighted_tp_den: float,
        unranked_tp_sum: float,
        unranked_matches: int,
    ) -> tuple[float, dict]:
        """
        Compute S_DOM and return (score, raw_data).

        - Use team-points per match (DEC=3, MD=4, TF=5, PIN=6)
          weighted by opponent quality on a Top-50 scale.
        - Map weighted average team points in [3.0, 6.0] to [0, 100].
        - Optionally apply a small penalty for weak dominance vs unranked
          opponents (avg team points < 3.2).
        """
        raw = {"avg_team_points": 0.0}
        if weighted_tp_den <= 0.0:
            return (0.0, raw)

        # Weighted average dominance across all opponents.
        avg_tp_weighted = weighted_tp_num / weighted_tp_den
        raw["avg_team_points"] = avg_tp_weighted
        
        if avg_tp_weighted <= 3.0:
            return (0.0, raw)

        s_dom = min(100.0, (avg_tp_weighted - 3.0) / 3.0 * 100.0)

        # Optional weak-opponent penalty based on unranked dominance only.
        if unranked_matches > 0:
            avg_tp_unranked = unranked_tp_sum / float(unranked_matches)
            if avg_tp_unranked < 3.2:
                penalty = min(10.0, (3.2 - avg_tp_unranked) * 10.0)
                s_dom = max(0.0, s_dom - penalty)

        return (s_dom, raw)

    def compute_s_pins(pins: int, wins: int) -> tuple[float, dict]:
        """Compute pin score and return (score, raw_data)."""
        raw = {"pin_pct": 0.0}
        if wins <= 0 or pins <= 0:
            return (0.0, raw)
        pin_pct = pins / wins
        raw["pin_pct"] = pin_pct
        if pin_pct <= 0.10:
            return (0.0, raw)
        if pin_pct >= 0.60:
            return (100.0, raw)
        return ((pin_pct - 0.10) / 0.50 * 100.0, raw)

    def check_eligibility(s: HodgeStats, s_qual: float) -> tuple[bool, Optional[str]]:
        """Check eligibility gate and return (eligible, reason)."""
        if s.weight_rank > 3:
            return (False, f"Weight class rank {s.weight_rank} > 3")
        if s.total_matches < 5:
            return (False, f"Matches {s.total_matches} < 5")
        # Allow 1 loss OR ≥90% win rate
        win_pct = s.win_pct if s.total_matches > 0 else 0.0
        if s.losses > 1 and win_pct < 0.90:
            return (False, f"Has {s.losses} loss(es) and win% {win_pct:.1%} < 90%")
        if s.ranked_wins < 1 and s_qual < 20.0:
            return (False, f"Ranked wins {s.ranked_wins} < 1 and quality score {s_qual:.1f} < 20")
        return (True, None)

    # NEW WEIGHTS (no weight-class rank)
    W_REC = 0.30
    W_QUAL = 0.30
    W_DOM = 0.25
    W_PINS = 0.15

    for s in filtered_candidates:
        # Compute component scores with raw data
        s_rec_score, rec_raw = compute_s_rec(s.wins, s.losses)
        s_qual_score, qual_raw = compute_s_qual(s.ranked_win_ranks, s.ranked_wins, s.top10_wins)
        s_dom_score, dom_raw = compute_s_dom(
            s.dom_weighted_tp_num,
            s.dom_weighted_tp_den,
            s.dom_unranked_tp_sum,
            s.dom_unranked_matches,
        )
        s_pins_score, pins_raw = compute_s_pins(s.pins, s.wins)
        
        # Store component data
        s.component_data = {
            "record": {"raw": rec_raw, "score": s_rec_score},
            "quality": {"raw": qual_raw, "score": s_qual_score},
            "dominance": {"raw": dom_raw, "score": s_dom_score},
            "pins": {"raw": pins_raw, "score": s_pins_score},
        }
        
        # Compute weighted contributions
        s.component_data["record"]["weight"] = W_REC
        s.component_data["record"]["contribution"] = W_REC * s_rec_score
        s.component_data["quality"]["weight"] = W_QUAL
        s.component_data["quality"]["contribution"] = W_QUAL * s_qual_score
        s.component_data["dominance"]["weight"] = W_DOM
        s.component_data["dominance"]["contribution"] = W_DOM * s_dom_score
        s.component_data["pins"]["weight"] = W_PINS
        s.component_data["pins"]["contribution"] = W_PINS * s_pins_score
        
        # Compute Hodge Score (no weight-class rank)
        s.hodge_score = (
            W_REC * s_rec_score
            + W_QUAL * s_qual_score
            + W_DOM * s_dom_score
            + W_PINS * s_pins_score
        )
        
        # Check eligibility
        s.eligible, s.eligibility_reason = check_eligibility(s, s_qual_score)

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

    # Sort candidates: eligible first, then by Hodge score descending
    scored_candidates = sorted(
        filtered_candidates, key=lambda s: (-s.eligible, -s.hodge_score)
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

    # --- Generate JSON report ---
    season_dir = output_root / str(season)
    season_dir.mkdir(parents=True, exist_ok=True)
    json_path = season_dir / f"hodge_{season}.json"

    generated_at = datetime.now(timezone.utc).isoformat()

    # Build JSON structure with new format
    rows = []
    for idx, s in enumerate(scored_candidates, start=1):
        row = {
            "rank": idx,
            "wrestler_id": s.wrestler_id,
            "name": s.name,
            "team": s.team,
            "weight": int(s.weight_class) if s.weight_class.isdigit() else s.weight_class,
            "weight_rank": s.weight_rank,
            "eligible": s.eligible,
            "eligibility_reason": s.eligibility_reason,
            "hodge_score": round(s.hodge_score, 2),
            "components": {
                "record": {
                    "raw": {
                        "wins": s.component_data["record"]["raw"]["wins"],
                        "losses": s.component_data["record"]["raw"]["losses"],
                        "win_pct": round(s.component_data["record"]["raw"]["win_pct"], 3),
                    },
                    "score": round(s.component_data["record"]["score"], 1),
                    "weight": s.component_data["record"]["weight"],
                    "contribution": round(s.component_data["record"]["contribution"], 2),
                },
                "quality": {
                    "raw": {
                        "ranked_wins": s.component_data["quality"]["raw"]["ranked_wins"],
                        "top10_wins": s.component_data["quality"]["raw"]["top10_wins"],
                        "raw_quality": round(s.component_data["quality"]["raw"]["raw_quality"], 1),
                    },
                    "score": round(s.component_data["quality"]["score"], 1),
                    "weight": s.component_data["quality"]["weight"],
                    "contribution": round(s.component_data["quality"]["contribution"], 2),
                },
                "dominance": {
                    "raw": {
                        "avg_team_points": round(s.component_data["dominance"]["raw"]["avg_team_points"], 2),
                    },
                    "score": round(s.component_data["dominance"]["score"], 1),
                    "weight": s.component_data["dominance"]["weight"],
                    "contribution": round(s.component_data["dominance"]["contribution"], 2),
                },
                "pins": {
                    "raw": {
                        "pin_pct": round(s.component_data["pins"]["raw"]["pin_pct"], 3),
                    },
                    "score": round(s.component_data["pins"]["score"], 1),
                    "weight": s.component_data["pins"]["weight"],
                    "contribution": round(s.component_data["pins"]["contribution"], 2),
                },
            }
        }
        rows.append(row)

    json_data = {
        "season": season,
        "generated_at": generated_at,
        "description": (
            "Hodge Score evaluates performance only. "
            "Eligibility determines who appears on the Hodge Watch. "
            "Weight-class rank influences eligibility — not scoring."
        ),
        "rows": rows
    }

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)

    print(f"\nJSON report written to {json_path}\n")


if __name__ == "__main__":
    main()


