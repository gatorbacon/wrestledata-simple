#!/usr/bin/env python3
"""
Experimental power ranking calculation for a single weight class.

Implements the algorithm described in docs/powerankings.md:

    Power Score = Quality Wins
                + Competitive Losses
                + Bonus Score
                + Consistency
                − Bad Loss Penalty

For now this:
  - Works on one weight class at a time.
  - Uses mt/rankings_data/{season}/rankings_{weight}.json and
    weight_class_{weight}.json.
  - Only scores matches where BOTH wrestlers are ranked in that weight.
  - Prints a comparison table: current rank vs power rank.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# Tunable modifiers (from docs/powerankings.md) and the refined behavior
# we discussed:
#
# - Quality Wins: based on absolute opponent rank with diminishing returns
#   for multiple good wins.
# - Bad Loss: based on absolute opponent rank of worst losses with
#   diminishing returns for additional similar losses.

# Base points for beating an opponent of rank r:
#   BaseWin(r) = max(0, BASE_QW_MAX - r)
# so beating #1 >> #20 >> #40; wins below that contribute almost nothing.
BASE_QW_MAX = 40
# Decay for additional good wins (first is full weight, second is 50%, etc.)
QW_DECAY = 0.5
MOD_QUALITY_WIN = 1.0

# Competitive losses: small credit for close losses vs high-ranked opponents.
MOD_QUALITY_LOSS = 0.4
COMP_LOSS_MAX_MARGIN = 3
COMP_LOSS_OPP_MAX_RANK = 10  # only count close losses to roughly top-10 guys

# Bonus multipliers relative to the quality-win core for that match.
BONUS_MD_MULT = 0.2
BONUS_TF_MULT = 0.4
BONUS_FALL_MULT = 0.6

# Bad loss: losing to significantly lower-ranked opponents.
BAD_LOSS_GOOD_THRESH = 10  # no penalty for losing to #10 or better
BAD_LOSS_DECAY = 0.5       # additional bad losses matter less
MOD_BAD_LOSS = 1.2

# We keep the consistency component in the dataclass for now, but don't
# currently apply any separate consistency scoring in this refined version.
MOD_CONSISTENCY = 0.0


def classify_result_type(result: str) -> str:
    """
    Roughly classify a result string into a simple code:
      'DEC', 'MD', 'TF', 'FALL', or 'OTHER'.
    """
    if not result:
        return "OTHER"
    r = result.lower()
    if "fall" in r and not "sv-" in r and not "tf" in r:
        return "FALL"
    if "tf" in r or "technical fall" in r:
        return "TF"
    if "md" in r or "major" in r:
        return "MD"
    # Default decision (including SV/TB OT)
    if "dec" in r or "sv-" in r or "tb-" in r:
        return "DEC"
    return "OTHER"


def parse_score_margin(result: str) -> Optional[Tuple[int, int]]:
    """
    Extract (winner_points, loser_points) from a result string like:
      'Dec 4-2', 'MD 12-3', 'TF 18-0 2:33'
    Returns None if no score can be parsed.
    """
    if not result:
        return None
    m = re.search(r"(\d+)-(\d+)", result)
    if not m:
        return None
    a = int(m.group(1))
    b = int(m.group(2))
    # We don't trust ordering in the string; treat the larger as winner's score.
    winner_pts = max(a, b)
    loser_pts = min(a, b)
    return winner_pts, loser_pts


@dataclass
class PowerStats:
    wrestler_id: str
    name: str
    team: str
    weight_class: str
    rank: int
    power_score: float = 0.0
    quality_wins: float = 0.0
    comp_losses: float = 0.0
    bonus_score: float = 0.0
    consistency_score: float = 0.0
    bad_loss_penalty: float = 0.0
    matches_counted: int = 0
    details: List[str] = field(default_factory=list)
    win_records: List[Tuple[int, str]] = field(default_factory=list)  # (opp_rank, result_type)
    loss_records: List[Tuple[int, Optional[int], str]] = field(default_factory=list)  # (opp_rank, margin, result_type)


def load_rankings(season: int, weight: str, data_dir: str) -> List[Dict]:
    base = Path(data_dir) / str(season)
    path = base / f"rankings_{weight}.json"
    if not path.exists():
        raise FileNotFoundError(f"Rankings file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("rankings", [])


def load_weight_class(season: int, weight: str, data_dir: str) -> Dict:
    base = Path(data_dir) / str(season)
    path = base / f"weight_class_{weight}.json"
    if not path.exists():
        raise FileNotFoundError(f"Weight-class file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def compute_power_for_weight(
    season: int, weight: str, data_dir: str
) -> Tuple[List[PowerStats], Dict[str, int]]:
    rankings = load_rankings(season, weight, data_dir)
    if not rankings:
        raise SystemExit(f"No rankings found for weight {weight} in season {season}.")

    wc_data = load_weight_class(season, weight, data_dir)
    wrestlers = wc_data.get("wrestlers", {})
    matches = wc_data.get("matches", [])

    # Build rank lookup for this weight.
    rank_by_id: Dict[str, int] = {}
    for entry in rankings:
        wid = entry.get("wrestler_id")
        r = entry.get("rank")
        if not wid or r is None:
            continue
        try:
            rank_by_id[wid] = int(r)
        except (TypeError, ValueError):
            continue

    # Initialize stats for all ranked wrestlers we have data for.
    stats: Dict[str, PowerStats] = {}
    for entry in rankings:
        wid = entry.get("wrestler_id")
        if not wid:
            continue
        w_info = wrestlers.get(wid)
        if not w_info:
            # No match data in this weight file; skip for now.
            continue
        name = w_info.get("name", f"ID:{wid}")
        team = w_info.get("team", "Unknown")
        r = rank_by_id.get(wid, 999)
        stats[wid] = PowerStats(
            wrestler_id=wid,
            name=name,
            team=team,
            weight_class=weight,
            rank=r,
        )

    if not stats:
        raise SystemExit(
            "No overlapping wrestlers between rankings and weight_class data; "
            "nothing to score."
        )

    # Process matches; only consider bouts where BOTH wrestlers are ranked
    # in this weight so we have opponent rank.
    for m in matches:
        w1 = m.get("wrestler1_id")
        w2 = m.get("wrestler2_id")
        winner = m.get("winner_id")
        result = m.get("result", "") or ""

        if not w1 or not w2 or not winner:
            continue

        # If neither side is one of our ranked wrestlers, skip.
        if w1 not in stats and w2 not in stats:
            continue

        # Require that both sides have ranking info so we can get OppRank.
        if w1 not in rank_by_id or w2 not in rank_by_id:
            continue

        result_type = classify_result_type(result)
        score_pair = parse_score_margin(result)
        winner_pts = loser_pts = None
        if score_pair:
            winner_pts, loser_pts = score_pair
            margin = winner_pts - loser_pts
        else:
            margin = None

        def update_for(wid: str, opp_id: str, is_winner: bool) -> None:
            """Record win/loss info; actual scoring is done after all matches."""
            s = stats.get(wid)
            if not s:
                return

            opp_rank = rank_by_id.get(opp_id)
            if opp_rank is None:
                return

            # Record wins and losses separately for later scoring.
            if is_winner:
                s.win_records.append((opp_rank, result_type))
            else:
                s.loss_records.append((opp_rank, margin, result_type))

            s.matches_counted += 1

        # Update for both perspectives
        if w1 in stats:
            update_for(w1, w2, is_winner=(winner == w1))
        if w2 in stats:
            update_for(w2, w1, is_winner=(winner == w2))

    # After collecting all wins/losses, compute scores using the refined rules.
    for s in stats.values():
        # ---- Quality Wins + Bonus (absolute rank with diminishing returns) ----
        if s.win_records:
            # Sort by opponent rank ascending (best opponents first)
            wins_sorted = sorted(s.win_records, key=lambda t: t[0])
            for idx, (opp_rank, rtype) in enumerate(wins_sorted):
                base = max(0, BASE_QW_MAX - opp_rank)
                if base <= 0:
                    continue
                decay = QW_DECAY ** idx
                core = MOD_QUALITY_WIN * base * decay
                s.quality_wins += core
                s.power_score += core

                # Bonus scaled relative to this core quality.
                bonus_mult = 0.0
                if rtype == "MD":
                    bonus_mult = BONUS_MD_MULT
                elif rtype == "TF":
                    bonus_mult = BONUS_TF_MULT
                elif rtype == "FALL":
                    bonus_mult = BONUS_FALL_MULT
                if bonus_mult > 0.0:
                    b = core * bonus_mult
                    s.bonus_score += b
                    s.power_score += b

        # ---- Loss-based components: Competitive Loss + Bad Loss ----
        if s.loss_records:
            # Worst losses first: highest (numerically) opponent rank
            losses_sorted = sorted(s.loss_records, key=lambda t: t[0], reverse=True)
            for idx, (opp_rank, margin, rtype) in enumerate(losses_sorted):
                # Competitive Loss: small credit for close losses vs much better guys
                if (
                    margin is not None
                    and margin <= COMP_LOSS_MAX_MARGIN
                    and rtype not in ("FALL", "TF")
                    and opp_rank <= COMP_LOSS_OPP_MAX_RANK
                    and s.rank > opp_rank
                ):
                    cl_base = max(0, s.rank - opp_rank)
                    cl = MOD_QUALITY_LOSS * cl_base
                    s.comp_losses += cl
                    s.power_score += cl

                # Bad loss penalty: losing to significantly lower-ranked opponents
                base_loss = max(0, opp_rank - BAD_LOSS_GOOD_THRESH)
                if base_loss > 0:
                    decay = BAD_LOSS_DECAY ** idx
                    pen = MOD_BAD_LOSS * base_loss * decay
                    s.bad_loss_penalty += pen
                    s.power_score -= pen

    # Return list sorted by power_score (desc)
    scored = sorted(stats.values(), key=lambda s: (-s.power_score, s.rank))
    return scored, rank_by_id


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Experimental power ranking for a single weight class."
    )
    parser.add_argument(
        "-season",
        type=int,
        required=True,
        help="Season year (e.g., 2026).",
    )
    parser.add_argument(
        "-weight-class",
        required=True,
        help="Weight class string (e.g., 125, 133, 141).",
    )
    parser.add_argument(
        "-data-dir",
        default="mt/rankings_data",
        help="Base data directory containing rankings_*.json and weight_class_*.json.",
    )

    args = parser.parse_args()
    season = args.season
    weight = str(args.weight_class)

    scored, rank_by_id = compute_power_for_weight(season, weight, args.data_dir)

    print(
        f"\nPower ranking experiment for {season} — {weight} lbs "
        f"(BASE_QW_MAX={BASE_QW_MAX}, QW_DECAY={QW_DECAY}, "
        f"BONUS_MD_MULT={BONUS_MD_MULT}, BONUS_TF_MULT={BONUS_TF_MULT}, BONUS_FALL_MULT={BONUS_FALL_MULT}, "
        f"BAD_LOSS_GOOD_THRESH={BAD_LOSS_GOOD_THRESH}, BAD_LOSS_DECAY={BAD_LOSS_DECAY})\n"
    )

    # Build mapping from wrestler_id to current rank for quick lookup
    current_order = sorted(rank_by_id.items(), key=lambda kv: kv[1])
    rank_pos: Dict[str, int] = {wid: r for wid, r in current_order}

    header = (
        f"{'PowRank':>7}  {'CurrRk':>6}  {'Δ':>3}  "
        f"{'Name':<25} {'Team':<20} {'PowerScore':>11}  "
        f"{'QW':>6} {'CL':>6} {'Bonus':>6} {'Cons':>6} {'BadL':>6}"
    )
    print(header)
    print("-" * len(header))

    for idx, s in enumerate(scored, start=1):
        curr = s.rank
        delta = curr - idx  # positive = current rank lower than power rank
        print(
            f"{idx:7d}  {curr:6d}  {delta:3d}  "
            f"{s.name:<25.25} {s.team:<20.20} {s.power_score:11.2f}  "
            f"{s.quality_wins:6.1f} {s.comp_losses:6.1f} {s.bonus_score:6.1f} "
            f"{s.consistency_score:6.1f} {s.bad_loss_penalty:6.1f}"
        )

    print(
        "\nNote: This is an experimental score based only on matches where both "
        "wrestlers are ranked in this weight class (so OppRank/WrestRank are known).\n"
    )


if __name__ == "__main__":
    main()


