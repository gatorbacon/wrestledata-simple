#!/usr/bin/env python3
"""
anppm_by_rank.py

Normalized Average Points Per Match (ANPPM) for ranked wrestlers.

Based on the attached spec:

  - Consider wrestlers ranked 1..R (overall rank across all weights).
  - Use only "valid" matches:
      * Have a real final numeric score (e.g., '10-3').
      * Exclude falls, DQ, MFF, INJ, forfeits, etc.
  - For each valid match where Wrestler A faces Opponent B:
      1) Compute A's PD7_for (points scored per 7 minutes).
      2) Compute Opponent B's adjusted PA7:
           - Remove this A-vs-B match from B's stats.
           - If B meets sample-size requirement, use B's own PA7 from
             remaining matches.
           - Otherwise, use the weight-class-average PA7.
      3) Match NormScore = PD7_for - Opp_PA7.
      4) ANPPM for A = average(NormScore over A's valid matches).

Sample-size requirement (stat-eligible wrestler/opponent):

    threshold = max(8, floor(0.50 × average_valid_match_count_for_top_R_wrestlers))

For opponents with fewer than this requirement, we fall back to the
weight-class-average PA7.

Outputs:
  1) Top 10 wrestlers by ANPPM (descending).
  2) Detailed debug breakdown for the #1 wrestler:
       - Each match
       - Opponent name + rank
       - A's PD7_for
       - Opponent's PA7 used
       - Normalized match score
       - Running cumulative average
  3) Summary totals:
       - Total matches included
       - Matches excluded due to invalid match type
       - Matches where opponent PA7 came from weight-class averages
"""

from __future__ import annotations

import argparse
import math
import re
from collections import defaultdict
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import plotly.express as px
from plotly.subplots import make_subplots
import plotly.graph_objects as go

from load_data import load_team_data
from scoringbyrank import _parse_score_from_result, _load_rank_map
from wrestler_stats import build_wrestler_index, prompt_for_wrestler

# Weights for Dominance Index (DI_raw) combination of SI+, DF+, PE+.
# These should sum to 1.0 and can be tuned without touching the logic.
DI_WEIGHT_SI = 0.40
DI_WEIGHT_DF = 0.45
DI_WEIGHT_PE = 0.15


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute ANPPM (opponent-adjusted PD7) for ranked wrestlers."
    )
    parser.add_argument(
        "-season",
        type=int,
        required=True,
        help="Season year (e.g., 2026).",
    )
    parser.add_argument(
        "-maxrank",
        type=int,
        required=True,
        help="Include wrestlers ranked from 1 through this rank (across all weights).",
    )
    parser.add_argument(
        "-team",
        type=str,
        help=(
            "Optional team filter (e.g. 'Iowa'). When provided, console and HTML "
            "tables show only that team's starters, and plots highlight that team."
        ),
    )
    parser.add_argument(
        "-wrestler",
        action="store_true",
        help=(
            "Enter interactive single-wrestler stats mode. "
            "Prints detailed stats for one wrestler and skips the normalized "
            "NPF7/NPA7/NPD7 report and graphics."
        ),
    )
    parser.add_argument(
        "-weight",
        type=str,
        help=(
            "Optional weight class filter (e.g., '125'). When provided without "
            "-wrestler, prints a DI+ top-10 table for that weight class "
            "instead of the global NPF7/NPA7/NPD7 report."
        ),
    )
    parser.add_argument(
        "-quintiles",
        action="store_true",
        help=(
            "Print league APS7/APG7/APD7/APR mean/std for each weight/quintile "
            "bucket (starters only, by weight-class rankings)."
        ),
    )
    return parser.parse_args()


def estimate_match_duration_seconds(result_str: str) -> int:
    """
    Estimate match duration in seconds from a result string.

    Rules (per PD7 logic used elsewhere):
      - Default for a standard match: 7:00 (420 seconds).
      - Sudden Victory (SV-1, SV-2, SV-3): assume 8:15 total (495 seconds).
      - Tie Breakers (TB-1, TB-2): assume 10:00 total (600 seconds).
      - Tech fall (TF ... MM:SS): if a time like '5:21' is present, use that;
        otherwise fall back to 7:00.
    """
    base = 7 * 60  # 7 minutes
    if not result_str:
        return base

    s = result_str.lower()

    # Tie breakers first (10:00 total)
    if "tb-1" in s or "tb-2" in s:
        return 10 * 60

    # Sudden victory (8:15 total)
    if "sv-1" in s or "sv-2" in s or "sv-3" in s or "sudden victory" in s:
        return 8 * 60 + 15

    # Tech fall with an explicit time (e.g. 'TF 21-3 5:21')
    if "tf" in s:
        times = list(re.finditer(r"(\d+):(\d{2})", result_str))
        if times:
            m = times[-1]
            minutes = int(m.group(1))
            seconds = int(m.group(2))
            duration = minutes * 60 + seconds
            # Guard against malformed times like "0:00".
            if duration > 0:
                return duration

    # Fallback: standard 7-minute bout.
    return base


def _run_wrestler_mode(season: int, max_rank: int) -> None:
    """
    Interactive single-wrestler stats mode (triggered by -wrestler).

    This does NOT generate any HTML report or graphics. It:
      - Lets the user search for and select a wrestler.
      - Prints basic and advanced stats for that wrestler.
    """
    wrestlers = build_wrestler_index(season)
    print(f"Loaded {len(wrestlers)} wrestlers for season {season}.\n")

    ref = prompt_for_wrestler(wrestlers)
    if ref is None:
        print("No wrestler selected; exiting wrestler mode.")
        return

    team_name = ref.team
    wname = ref.name
    wid = ref.wrestler_id
    weight_class = ref.weight_class or "?"

    # Ranking (best overall rank across all weights for this season).
    rank_by_id = _load_rank_map(season)
    overall_rank = rank_by_id.get(wid)

    wins = 0
    losses = 0

    # Classification of wins
    fall_wins = 0
    md_wins = 0
    tf_wins = 0

    # Ranked-win counter
    ranked_wins = 0

    # PF/PA and PD7-related accumulators (non-fall, numeric-score matches)
    pf7_points_total = 0.0
    pa7_points_total = 0.0
    pd7_total_diff = 0.0
    total_seconds = 0
    pd7_matches = 0

    matches = ref.raw.get("matches", []) or []

    for m in matches:
        # Skip byes / no-result
        result = m.get("result", "") or ""
        if result in ("BYE", "NoResult"):
            continue
        summary = m.get("summary", "") or ""
        if "received a bye" in summary.lower():
            continue

        winner_name = m.get("winner_name", "") or ""
        loser_name = m.get("loser_name", "") or ""
        winner_team = m.get("winner_team", "") or ""
        loser_team = m.get("loser_team", "") or ""

        is_winner = (
            wid == str(m.get("winner_id") or "")
            or (wname == winner_name and team_name == winner_team)
        )
        is_loser = (
            wid == str(m.get("loser_id") or "")
            or (wname == loser_name and team_name == loser_team)
        )

        if not (is_winner or is_loser):
            continue

        # Record result
        if is_winner:
            wins += 1
        else:
            losses += 1

        res_lower = result.lower()
        is_fall = (
            "fall" in res_lower or "pin" in res_lower or "pinned" in res_lower
        )
        is_tf = "tf" in res_lower
        is_md = (
            ("md" in res_lower or "major" in res_lower)
            and not is_tf
            and not is_fall
        )

        if is_winner:
            if is_fall:
                fall_wins += 1
            elif is_tf:
                tf_wins += 1
            elif is_md:
                md_wins += 1

            # Ranked wins: opponent is ranked in the season rankings.
            opp_id = str(m.get("loser_id") or "")
            if opp_id and opp_id in rank_by_id:
                ranked_wins += 1

        # PF7/PA7 and PD7 use only matches with numeric scores and that are not falls.
        score_pair = _parse_score_from_result(result)
        if not score_pair:
            continue
        winner_pts, loser_pts = score_pair

        # Skip pins/falls for PF7/PA7/PD7 calculations.
        if is_fall:
            continue

        if is_winner:
            pf = float(winner_pts)
            pa = float(loser_pts)
        else:
            pf = float(loser_pts)
            pa = float(winner_pts)

        pf7_points_total += pf
        pa7_points_total += pa

        diff = pf - pa
        pd7_total_diff += diff

        duration_seconds = estimate_match_duration_seconds(result)
        total_seconds += duration_seconds
        pd7_matches += 1

    total_matches = wins + losses
    win_pct = (wins / total_matches * 100.0) if total_matches > 0 else 0.0
    pin_rate = (fall_wins / wins * 100.0) if wins > 0 else 0.0
    bonus_wins = fall_wins + md_wins + tf_wins
    bonus_rate = (bonus_wins / wins * 100.0) if wins > 0 else 0.0
    tech_rate = (tf_wins / wins * 100.0) if wins > 0 else 0.0

    if total_seconds > 0:
        scale = (7 * 60) / float(total_seconds)
        raw_pf7 = pf7_points_total * scale
        raw_pa7 = pa7_points_total * scale
        raw_pd7 = pd7_total_diff * scale
    else:
        raw_pf7 = raw_pa7 = raw_pd7 = 0.0

    # Pretty-print total mat time (for matches used in PF7/PA7/PD7).
    total_minutes = total_seconds // 60
    total_rem_secs = total_seconds % 60

    print("=" * 60)
    print(f"Wrestler Stats — Season {season}")
    print("=" * 60)
    print(f"Name:        {wname}")
    print(f"Team:        {team_name}")
    print(f"Weight:      {weight_class}")
    if overall_rank is not None:
        print(f"Rank:        #{overall_rank}")
    else:
        print("Rank:        Unranked")
    print()

    print(f"Record:      {wins}-{losses}  (Win %: {win_pct:5.1f}%)")
    print(f"Pin rate:    {fall_wins} pins  ({pin_rate:5.1f}% of wins)")
    print(
        f"Bonus rate:  {bonus_wins} bonus wins (MD/TF/Fall) "
        f"({bonus_rate:5.1f}% of wins)"
    )
    print(
        f"Tech rate:   {tf_wins} techs  ({tech_rate:5.1f}% of wins)"
    )
    print(f"Ranked wins: {ranked_wins}")
    print()

    print("Raw per-7-minute scoring (non-fall, scored matches only):")
    print(f"  PF7 (for):          {raw_pf7:6.2f}")
    print(f"  PA7 (against):      {raw_pa7:6.2f}")
    print(f"  Point differential: {raw_pd7:6.2f}")
    print(
        f"  Matches counted:    {pd7_matches} "
        f"({'no time information' if total_seconds == 0 else 'with time data'})"
    )
    print(
        f"  Total mat time (excluding falls): "
        f"{total_minutes:02d}:{total_rem_secs:02d} ({total_seconds} seconds)"
    )
    print()

    # ------------------------------------------------------------
    # Normalized stats for this wrestler (APS7 / APG7)
    # ------------------------------------------------------------
    print("Normalized per-7-minute scoring (APS7/APG7):")

    # Rebuild match context so we can show per-match math and opponent baselines.
    wrestlers_ctx, matches_by_wrestler, _pa7_sum_by_w, _pa7_cnt_by_w, pa7_sum_by_wt, pa7_cnt_by_wt, _exc = build_all_matches(
        season, {}
    )

    # Weight-class and league-wide baselines (LSR = league scoring rate)
    pa7_avg_by_weight: Dict[str, float] = {}
    pf7_sum_by_weight: Dict[str, float] = defaultdict(float)
    pf7_count_by_weight: Dict[str, int] = defaultdict(int)
    league_pa7_sum = 0.0
    league_pa7_count = 0
    league_pf7_sum = 0.0
    league_pf7_count = 0
    league_pd7_sum = 0.0
    league_pd7_count = 0
    league_pd7_sum = 0.0
    league_pd7_count = 0
    for wid_ctx, mlist in matches_by_wrestler.items():
        for e in mlist:
            wc = e.get("weight_class", "")
            if not wc:
                continue
            pa7_sum_by_wt[wc] += e.get("pa7", 0.0)
            pa7_cnt_by_wt[wc] += 1
            pf7_sum_by_weight[wc] += e.get("pd7_for", 0.0)
            pf7_count_by_weight[wc] += 1
            league_pa7_sum += e.get("pa7", 0.0)
            league_pa7_count += 1
            league_pf7_sum += e.get("pd7_for", 0.0)
            league_pf7_count += 1

            pd7_side = float(e.get("pd7_for", 0.0)) - float(e.get("pa7", 0.0))
            league_pd7_sum += pd7_side
            league_pd7_count += 1

            pd7_side = float(e.get("pd7_for", 0.0)) - float(e.get("pa7", 0.0))
            league_pd7_sum += pd7_side
            league_pd7_count += 1
    for wc, s in pa7_sum_by_wt.items():
        c = pa7_cnt_by_wt.get(wc, 0)
        if c > 0:
            pa7_avg_by_weight[wc] = s / float(c)
    pf7_avg_by_weight: Dict[str, float] = {}
    for wc, s in pf7_sum_by_weight.items():
        c = pf7_count_by_weight.get(wc, 0)
        if c > 0:
            pf7_avg_by_weight[wc] = s / float(c)

    league_pa7 = (
        league_pa7_sum / float(league_pa7_count) if league_pa7_count > 0 else 0.0
    )
    league_pf7 = (
        league_pf7_sum / float(league_pf7_count) if league_pf7_count > 0 else 0.0
    )
    league_pd7 = (
        league_pd7_sum / float(league_pd7_count) if league_pd7_count > 0 else 0.0
    )
    league_pd7 = (
        league_pd7_sum / float(league_pd7_count) if league_pd7_count > 0 else 0.0
    )

    # Shrinkage constant for opponent baselines.
    K = 8.0

    # Helper to pretty-print baseline components.
    def _print_baseline_components(
        opp_matches: List[Dict],
        match_key,
        use_pa7: bool,
    ) -> None:
        other = [e for e in opp_matches if e["key"] != match_key]
        if not other:
            print("      (no other valid matches for baseline)\n")
            return
        print("      Baseline components (opponent's other matches):")
        for idx, e in enumerate(other, start=1):
            opp_opp_name = e.get("opponent_name", f"ID:{e.get('opponent_id')}")
            res = e.get("result", "")
            pa7_val = e.get("pa7", 0.0)
            pf7_val = e.get("pd7_for", 0.0)
            wl = "W" if e.get("is_win") else "L"
            if use_pa7:
                print(
                    f"        {idx}. vs {opp_opp_name} — {wl} {res} "
                    f"(PA7={pa7_val:5.2f})"
                )
            else:
                print(
                    f"        {idx}. vs {opp_opp_name} — {wl} {res} "
                    f"(PF7={pf7_val:5.2f})"
                )
        print()

    # Debug toggles for per-match breakdowns.
    DEBUG_APS = True
    DEBUG_APG = True
    DEBUG_APR = False

    # Offensive side: APS7 breakdown for this wrestler (no threshold; shrinkage).
    aps_contribs: List[float] = []
    w_matches = matches_by_wrestler.get(wid, [])
    for idx, m in enumerate(w_matches, start=1):
        key = m["key"]
        opp_id = m["opponent_id"]
        opp_info = wrestlers_ctx.get(
            opp_id, {"name": f"ID:{opp_id}", "team": "Unknown", "weight_class": ""}
        )
        opp_name = opp_info.get("name", f"ID:{opp_id}")
        opp_team = opp_info.get("team", "Unknown")
        opp_rank = rank_by_id.get(opp_id)
        weight = m.get("weight_class", "")
        pd7_for = m["pd7_for"]

        opp_matches = matches_by_wrestler.get(opp_id, [])
        other_sides = [e for e in opp_matches if e["key"] != key]

        if other_sides:
            pa_raw = sum(e["pa7"] for e in other_sides) / float(len(other_sides))
            n = len(other_sides)
        else:
            pa_raw = league_pa7
            n = 0

        # Shrink opponent PA7 toward league average.
        pa_adj = (
            (pa_raw * n + league_pa7 * K) / float(n + K)
            if (n + K) > 0
            else league_pa7
        )

        contrib = pd7_for - pa_adj
        aps_contribs.append(contrib)
        running = sum(aps_contribs) / float(len(aps_contribs))

        if DEBUG_APS:
            rank_str = f"#{opp_rank}" if opp_rank is not None else "Unranked"
            print(
                f"  Match {idx}: vs {opp_name} ({opp_team}, {rank_str}, {weight})"
            )
            print(f"    PF7 this match:           {pd7_for:6.2f}")
            print(
                f"    Opponent raw PA7 (other matches): {pa_raw:6.2f} "
                f"(n={n})"
            )
            print(
                f"    LSR (league Scoring rate):    {league_pa7:6.2f}  (k={K:.0f})"
            )
            print(
                f"    Shrunk opponent PA7_adj:  {pa_adj:6.2f} "
                "(APS7 baseline)"
            )
            print(
                f"    APS7 contribution:        {contrib:+6.2f} "
                f"(PF7 - PA7_adj)"
            )
            print(f"    Running APS7 average:     {running:+6.2f}")
            _print_baseline_components(opp_matches, key, use_pa7=True)

    if DEBUG_APS:
        print()

    # Defensive side: APG7 breakdown for this wrestler (no threshold; shrinkage).
    apg_contribs: List[float] = []
    w_matches = matches_by_wrestler.get(wid, [])
    for idx, m in enumerate(w_matches, start=1):
        key = m["key"]
        opp_id = m["opponent_id"]
        opp_info = wrestlers_ctx.get(
            opp_id, {"name": f"ID:{opp_id}", "team": "Unknown", "weight_class": ""}
        )
        opp_name = opp_info.get("name", f"ID:{opp_id}")
        opp_team = opp_info.get("team", "Unknown")
        opp_rank = rank_by_id.get(opp_id)
        weight = m.get("weight_class", "")

        # Opponent PF7 this match vs this wrestler.
        opp_matches = matches_by_wrestler.get(opp_id, [])
        opp_this = next(
            (
                e
                for e in opp_matches
                if e["key"] == key and e.get("opponent_id") == wid
            ),
            None,
        )
        if not opp_this:
            continue
        pf7_this = opp_this["pd7_for"]

        other_off = [e for e in opp_matches if e["key"] != key]
        if other_off:
            pf_raw = sum(e["pd7_for"] for e in other_off) / float(len(other_off))
            n = len(other_off)
        else:
            pf_raw = league_pf7
            n = 0

        # Shrink opponent PF7 toward league average.
        pf_adj = (
            (pf_raw * n + league_pf7 * K) / float(n + K)
            if (n + K) > 0
            else league_pf7
        )

        contrib = pf_adj - pf7_this
        apg_contribs.append(contrib)
        running = sum(apg_contribs) / float(len(apg_contribs))

        if DEBUG_APG:
            rank_str = f"#{opp_rank}" if opp_rank is not None else "Unranked"
            print(
                f"  Match {idx}: vs {opp_name} ({opp_team}, {rank_str}, {weight})"
            )
            print(
                f"    PA7 this match:           {pf7_this:6.2f} "
                "(points allowed by this wrestler)"
            )
            print(
                f"    Opponent raw PF7 (other matches): {pf_raw:6.2f} "
                f"(n={n})"
            )
            print(
                f"    LSR (league Scoring rate):    {league_pf7:6.2f}  (k={K:.0f})"
            )
            print(
                f"    Shrunk opponent PF7_adj:  {pf_adj:6.2f} "
                "(opponent PF7 baseline)"
            )
            print(
                f"    APG7 contribution:        {contrib:+6.2f} "
                f"(opponent PF7_adj - PA7_this)"
            )
            print(f"    Running APG7 average:     {running:+6.2f}")
            _print_baseline_components(opp_matches, key, use_pa7=False)

    if DEBUG_APG:
        print()

    # Summary APS7/APG7 values for this wrestler (average of contributions).
    aps7_final = sum(aps_contribs) / float(len(aps_contribs)) if aps_contribs else 0.0
    apg7_final = sum(apg_contribs) / float(len(apg_contribs)) if apg_contribs else 0.0
    print("APS7/APG7 summary:")
    print(f"  APS7 (avg over matches): {aps7_final:+6.2f}")
    print(f"  APG7 (avg over matches): {apg7_final:+6.2f}")
    print()

    # ------------------------------------------------------------
    # APR (Adjusted Pin Rate) with detailed debug
    # ------------------------------------------------------------
    from collections import defaultdict as _dd
    import re as _re

    def _build_pin_history(
        season_: int,
    ) -> tuple[dict[str, list[dict]], float]:
        """
        Build per-wrestler pin histories and league pin rate (LPR).

        Uses raw team data (load_team_data), dedups bouts across team files,
        infers winner/loser and fall status from the summary string.
        """
        teams = load_team_data(season_)
        pin_matches: dict[str, list[dict]] = _dd(list)
        seen_keys = set()
        total_bouts = 0
        total_pin_losses = 0

        for team in teams:
            for w in team.get("roster", []) or []:
                wid_local = str(w.get("season_wrestler_id") or "")
                if not wid_local or wid_local == "null":
                    continue
                wname = w.get("name", "") or ""
                for m in w.get("matches", []) or []:
                    summary = m.get("summary", "") or ""
                    s_sum = summary.lower()
                    # Skip byes / no-result.
                    if "received a bye" in s_sum:
                        continue

                    opp_id_local = str(m.get("opponent_id") or "")
                    if not opp_id_local or opp_id_local == "null":
                        continue

                    date = m.get("date", "") or ""
                    w1, w2 = sorted([wid_local, opp_id_local])
                    match_key = (w1, w2, date, summary)
                    if match_key in seen_keys:
                        continue
                    seen_keys.add(match_key)

                    # Determine if this bout should be excluded (forfeit/DQ/INJ).
                    if any(
                        kw in s_sum
                        for kw in ["forfeit", "mff", " ff", "dq", "inj", "injury"]
                    ):
                        continue

                    # Infer winner/loser from "X over Y" pattern in summary.
                    over_idx = s_sum.find(" over ")
                    name_idx = s_sum.find(wname.lower())
                    if over_idx == -1 or name_idx == -1:
                        continue
                    if name_idx < over_idx:
                        # This wrestler appears before "over" → winner.
                        winner_id = wid_local
                        loser_id = opp_id_local
                    else:
                        winner_id = opp_id_local
                        loser_id = wid_local

                    w1_is_winner = winner_id == w1

                    is_fall = ("fall" in s_sum) and not any(
                        kw in s_sum for kw in ["tech fall", "tf "]
                    )

                    total_bouts += 1
                    if is_fall and loser_id:
                        total_pin_losses += 1

                    def add_side(side_wid: str, is_winner_side: bool) -> None:
                        opp_side = w2 if side_wid == w1 else w1
                        pin_matches[side_wid].append(
                            {
                                "key": match_key,
                                "opponent_id": opp_side,
                                "result": summary,
                                "is_win": is_winner_side,
                                "is_fall_win": is_winner_side and is_fall,
                                "is_fall_loss": (not is_winner_side) and is_fall,
                            }
                        )

                    add_side(w1, w1_is_winner)
                    add_side(w2, not w1_is_winner)

        lpr = (total_pin_losses / float(total_bouts)) if total_bouts > 0 else 0.0
        return pin_matches, lpr

    pin_matches_by_wrestler, LPR = _build_pin_history(season)

    if DEBUG_APR:
        print("APR breakdown (per match):")
    k_pin = 12.0
    apr_contribs: List[float] = []

    def _print_apr_baseline(opp_hist: List[Dict], match_key) -> None:
        other = [e for e in opp_hist if e["key"] != match_key]
        if not other:
            print("      (no other valid matches for baseline)\n")
            return
        print("      Baseline components (opponent's other matches):")
        for idx, e in enumerate(other, start=1):
            wl = "W" if e.get("is_win") else "L"
            pinned_flag = 1 if e.get("is_fall_loss") else 0
            res = e.get("result", "")
            print(
                f"        {idx}. {wl} {res} "
                f"(pinned_flag={pinned_flag})"
            )
        print()

    w_pin_matches = pin_matches_by_wrestler.get(wid, [])
    for idx, m in enumerate(w_pin_matches, start=1):
        key = m["key"]
        opp_id = m["opponent_id"]
        opp_info = wrestlers_ctx.get(
            opp_id, {"name": f"ID:{opp_id}", "team": "Unknown", "weight_class": ""}
        )
        opp_name = opp_info.get("name", f"ID:{opp_id}")
        opp_team = opp_info.get("team", "Unknown")
        opp_rank = rank_by_id.get(opp_id)
        pin_outcome = 1.0 if m.get("is_fall_win") else 0.0

        opp_hist = pin_matches_by_wrestler.get(opp_id, [])
        other = [e for e in opp_hist if e["key"] != key]
        if other:
            n = len(other)
            pin_allow_raw = sum(1.0 for e in other if e.get("is_fall_loss")) / float(n)
        else:
            n = 0
            pin_allow_raw = LPR

        pin_allow_adj = (
            (pin_allow_raw * n + LPR * k_pin) / float(n + k_pin)
            if (n + k_pin) > 0
            else LPR
        )

        contrib = pin_outcome - pin_allow_adj
        apr_contribs.append(contrib)
        running = sum(apr_contribs) / float(len(apr_contribs))

        rank_str = f"#{opp_rank}" if opp_rank is not None else "Unranked"
        if DEBUG_APR:
            print(f"  Match {idx}: vs {opp_name} ({opp_team}, {rank_str})")
            print(
                f"    Pin outcome:             {pin_outcome:.0f} "
                "(1 = win by fall, 0 = otherwise)"
            )
            print(
                f"    Opponent raw pin-allow:  {pin_allow_raw:6.3f} "
                f"(n={n})"
            )
            print(
                f"    LPR (league pin rate):   {LPR:6.3f}  (k_pin={k_pin:.0f})"
            )
            print(
                f"    Shrunk PinAllow_adj:     {pin_allow_adj:6.3f}"
            )
            print(
                f"    APR contribution:        {contrib:+6.3f} "
                f"(pin_outcome - PinAllow_adj)"
            )
            print(f"    Running APR average:     {running:+6.3f}")
            _print_apr_baseline(opp_hist, key)

    if DEBUG_APR:
        print()
    apr_final = sum(apr_contribs) / float(len(apr_contribs)) if apr_contribs else 0.0
    print("APR summary:")
    print(f"  APR (avg over matches): {apr_final:+6.3f}")
    print()

    # ------------------------------------------------------------
    # APD7 (Adjusted Point Differential per 7 minutes)
    # ------------------------------------------------------------
    # Reuse the all-wrestler metrics helper to obtain APD7 for this wrestler.
    all_metrics = _compute_plus_metrics_for_all(season, max_rank)
    apd7_for_wrestler = all_metrics.get(wid, {}).get("APD7", 0.0)
    print("APD7 summary:")
    print(f"  APD7 (avg over matches): {apd7_for_wrestler:+6.2f}")
    print()

    # ------------------------------------------------------------
    # SI+, DF+, PE+ — standardized indexes based on APS7/APG7/APR
    # ------------------------------------------------------------

    from statistics import mean as _mean, pstdev as _pstdev

    def _mean_std(values: List[float]) -> tuple[float, float]:
        vals = [float(v) for v in values if v is not None]
        if not vals:
            return 0.0, 1.0
        mu = _mean(vals)
        sigma = _pstdev(vals)
        if sigma <= 0.0:
            sigma = 1.0
        return mu, sigma

    # APS7 / APG7 population moments across ALL wrestlers (not just starters).
    aps_vals_pop: List[float] = []
    apg_vals_pop: List[float] = []

    for wid_pop, mlist_pop in matches_by_wrestler.items():
        contribs_off: List[float] = []
        contribs_def: List[float] = []
        for m_pop in mlist_pop:
            key_pop = m_pop["key"]
            opp_id_pop = m_pop["opponent_id"]
            weight_pop = m_pop.get("weight_class", "")
            pd7_for_pop = m_pop["pd7_for"]

            opp_matches_pop = matches_by_wrestler.get(opp_id_pop, [])
            other_sides_pop = [e for e in opp_matches_pop if e["key"] != key_pop]

            # APS7 side (offense).
            if other_sides_pop:
                pa_raw_pop = sum(e["pa7"] for e in other_sides_pop) / float(
                    len(other_sides_pop)
                )
                n_pop = len(other_sides_pop)
            else:
                pa_raw_pop = league_pa7
                n_pop = 0

            pa_adj_pop = (
                (pa_raw_pop * n_pop + league_pa7 * K) / float(n_pop + K)
                if (n_pop + K) > 0
                else league_pa7
            )
            contribs_off.append(pd7_for_pop - pa_adj_pop)

            # APG7 side (defense) — need opponent PF7 this match.
            # Use match key only; opponent_id orientation is not reliable.
            opp_this_pop = next(
                (e for e in opp_matches_pop if e["key"] == key_pop),
                None,
            )
            if opp_this_pop is None:
                raise RuntimeError(f"Missing reverse match entry for key: {key_pop}")
            pf7_this_pop = opp_this_pop["pd7_for"]
            other_off_pop = [e for e in opp_matches_pop if e["key"] != key_pop]
            if other_off_pop:
                pf_raw_pop = sum(e["pd7_for"] for e in other_off_pop) / float(
                    len(other_off_pop)
                )
                n_off_pop = len(other_off_pop)
            else:
                pf_raw_pop = league_pf7
                n_off_pop = 0

            pf_adj_pop = (
                (pf_raw_pop * n_off_pop + league_pf7 * K) / float(n_off_pop + K)
                if (n_off_pop + K) > 0
                else league_pf7
            )
            contribs_def.append(pf_adj_pop - pf7_this_pop)

        if contribs_off:
            aps_vals_pop.append(sum(contribs_off) / float(len(contribs_off)))
        if contribs_def:
            apg_vals_pop.append(sum(contribs_def) / float(len(contribs_def)))

    mean_APS7, std_APS7 = _mean_std(aps_vals_pop)
    mean_APG7, std_APG7 = _mean_std(apg_vals_pop)

    # APR population moments from pin histories for all wrestlers.
    apr_by_id: Dict[str, float] = {}
    for wid_pop, plist in pin_matches_by_wrestler.items():
        contribs_pop: List[float] = []
        for m_pop in plist:
            key_pop = m_pop["key"]
            opp_id_pop = m_pop["opponent_id"]
            pin_outcome_pop = 1.0 if m_pop.get("is_fall_win") else 0.0

            opp_hist_pop = pin_matches_by_wrestler.get(opp_id_pop, [])
            other_pop = [e for e in opp_hist_pop if e["key"] != key_pop]
            if other_pop:
                n_pop = len(other_pop)
                pin_allow_raw_pop = sum(
                    1.0 for e in other_pop if e.get("is_fall_loss")
                ) / float(n_pop)
            else:
                n_pop = 0
                pin_allow_raw_pop = LPR

            pin_allow_adj_pop = (
                (pin_allow_raw_pop * n_pop + LPR * k_pin) / float(n_pop + k_pin)
                if (n_pop + k_pin) > 0
                else LPR
            )
            contribs_pop.append(pin_outcome_pop - pin_allow_adj_pop)

        if contribs_pop:
            apr_by_id[wid_pop] = sum(contribs_pop) / float(len(contribs_pop))

    apr_vals_pop = list(apr_by_id.values())
    mean_APR, std_APR = _mean_std(apr_vals_pop)

    # Guard: if wrestler not in population sets, treat their metrics as 0.
    aps7_for_plus = aps7_final
    apg7_for_plus = apg7_final
    apr_for_plus = apr_final

    # Z-scores
    # Scoring: higher APS7 is better.
    z_SI = (aps7_for_plus - mean_APS7) / std_APS7 if std_APS7 > 0 else 0.0
    # Defense: higher APG7 (more positive normalized points prevented) is better.
    # Use wrestler - league so positive z_DF means better-than-average defense.
    z_DF = (apg7_for_plus - mean_APG7) / std_APG7 if std_APG7 > 0 else 0.0
    # Pins: higher APR is better.
    z_PE = (apr_for_plus - mean_APR) / std_APR if std_APR > 0 else 0.0

    # + metrics
    SI_plus = 100.0 + 10.0 * z_SI
    DF_plus = 100.0 + 10.0 * z_DF
    PE_plus = 100.0 + 10.0 * z_PE

    print("SI+/DF+/PE+ (standardized indexes):")
    print()
    print("  Scoring (SI+):")
    print(f"    APS7_wrestler = {aps7_for_plus:+6.2f}")
    print(
        f"    APS7_league   = {mean_APS7:+6.2f}, std = {std_APS7:5.2f}"
    )
    print(
        f"    z_SI = (APS7_wrestler - APS7_league) / std"
        f" = ({aps7_for_plus:+6.2f} - {mean_APS7:+6.2f}) / {std_APS7:5.2f}"
        f" = {z_SI:+5.2f}"
    )
    print(f"    SI+  = 100 + 10 * z_SI = {SI_plus:6.1f}")
    print()

    print("  Defense (DF+):")
    print(f"    APG7_wrestler = {apg7_for_plus:+6.2f}")
    print(
        f"    APG7_league   = {mean_APG7:+6.2f}, std = {std_APG7:5.2f}"
    )
    print(
        f"    z_DF = (APG7_wrestler - APG7_league) / std"
        f" = ({apg7_for_plus:+6.2f} - {mean_APG7:+6.2f}) / {std_APG7:5.2f}"
        f" = {z_DF:+5.2f}"
    )
    print(f"    DF+  = 100 + 10 * z_DF = {DF_plus:6.1f}")
    print()

    print("  Pin Efficiency (PE+):")
    print(f"    APR_wrestler  = {apr_for_plus:+6.3f}")
    print(
        f"    APR_league    = {mean_APR:+6.3f}, std = {std_APR:5.3f}"
    )
    print(
        f"    z_PE = (APR_wrestler - APR_league) / std"
        f" = ({apr_for_plus:+6.3f} - {mean_APR:+6.3f}) / {std_APR:5.3f}"
        f" = {z_PE:+5.2f}"
    )
    print(f"    PE+  = 100 + 10 * z_PE = {PE_plus:6.1f}")
    print()

    # ------------------------------------------------------------
    # DI_raw (Dominance Index, raw weighted combination of + metrics)
    # ------------------------------------------------------------
    DI_raw = (
        DI_WEIGHT_SI * SI_plus
        + DI_WEIGHT_DF * DF_plus
        + DI_WEIGHT_PE * PE_plus
    )

    print("  Dominance Index (DI_raw):")
    print(
        f"    Weights: w1(SI+)={DI_WEIGHT_SI:.2f}, "
        f"w2(DF+)={DI_WEIGHT_DF:.2f}, w3(PE+)={DI_WEIGHT_PE:.2f}"
    )
    print(
        "    DI_raw = w1*SI+ + w2*DF+ + w3*PE+"
    )
    print(
        f"           = {DI_WEIGHT_SI:.2f}*{SI_plus:6.1f}"
        f" + {DI_WEIGHT_DF:.2f}*{DF_plus:6.1f}"
        f" + {DI_WEIGHT_PE:.2f}*{PE_plus:6.1f}"
        f" = {DI_raw:6.1f}"
    )
    print()


def _compute_plus_metrics_for_all(
    season: int, max_rank: int
) -> Dict[str, Dict[str, float]]:
    """
    Compute APS7/APG7/APR and corresponding SI+/DF+/PE+/DI_raw for ALL wrestlers.

    This mirrors the per-wrestler logic used in _run_wrestler_mode, but returns
    a dictionary keyed by wrestler_id for use in reports (e.g., weight-class
    top-10 tables).
    """
    # Build match structures for all wrestlers (no rank filter).
    (
        wrestlers_ctx,
        matches_by_wrestler,
        _pa7_sum_by_wrestler,
        _pa7_count_by_wrestler,
        pa7_sum_by_wt,
        pa7_cnt_by_wt,
        _excluded_invalid_matches,
    ) = build_all_matches(season, {})

    # League-wide PA7/PF7/PD7 (LSR) from all valid match sides.
    pa7_avg_by_weight: Dict[str, float] = {}
    pf7_sum_by_weight: Dict[str, float] = defaultdict(float)
    pf7_count_by_weight: Dict[str, int] = defaultdict(int)
    league_pa7_sum = 0.0
    league_pa7_count = 0
    league_pf7_sum = 0.0
    league_pf7_count = 0
    league_pd7_sum = 0.0
    league_pd7_count = 0
    for wid_ctx, mlist in matches_by_wrestler.items():
        for e in mlist:
            wc = e.get("weight_class", "")
            if not wc:
                continue
            pa7_sum_by_wt[wc] += e.get("pa7", 0.0)
            pa7_cnt_by_wt[wc] += 1
            pf7_sum_by_weight[wc] += e.get("pd7_for", 0.0)
            pf7_count_by_weight[wc] += 1
            league_pa7_sum += e.get("pa7", 0.0)
            league_pa7_count += 1
            league_pf7_sum += e.get("pd7_for", 0.0)
            league_pf7_count += 1

            pd7_side = float(e.get("pd7_for", 0.0)) - float(e.get("pa7", 0.0))
            league_pd7_sum += pd7_side
            league_pd7_count += 1
    for wc, s in pa7_sum_by_wt.items():
        c = pa7_cnt_by_wt.get(wc, 0)
        if c > 0:
            pa7_avg_by_weight[wc] = s / float(c)
    pf7_avg_by_weight: Dict[str, float] = {}
    for wc, s in pf7_sum_by_weight.items():
        c = pf7_count_by_weight.get(wc, 0)
        if c > 0:
            pf7_avg_by_weight[wc] = s / float(c)

    league_pa7 = (
        league_pa7_sum / float(league_pa7_count) if league_pa7_count > 0 else 0.0
    )
    league_pf7 = (
        league_pf7_sum / float(league_pf7_count) if league_pf7_count > 0 else 0.0
    )
    league_pd7 = (
        league_pd7_sum / float(league_pd7_count) if league_pd7_count > 0 else 0.0
    )

    K = 8.0  # shrinkage constant for APS7/APG7 baselines

    aps_vals_pop: List[float] = []
    apg_vals_pop: List[float] = []
    apd_vals_pop: List[float] = []
    aps_by_id: Dict[str, float] = {}
    apg_by_id: Dict[str, float] = {}
    apd_by_id: Dict[str, float] = {}
    pf7_by_id: Dict[str, float] = {}
    pa7_by_id: Dict[str, float] = {}

    # Compute APS7/APG7 for every wrestler.
    for wid_pop, mlist_pop in matches_by_wrestler.items():
        contribs_off: List[float] = []
        contribs_def: List[float] = []
        contribs_apd: List[float] = []
        pf7_sum = 0.0
        pa7_sum = 0.0
        pfpa_count = 0
        for m_pop in mlist_pop:
            key_pop = m_pop["key"]
            opp_id_pop = m_pop["opponent_id"]
            weight_pop = m_pop.get("weight_class", "")
            pd7_for_pop = m_pop["pd7_for"]
            pa7_this_pop = m_pop["pa7"]

            # Raw PF7/PA7 accumulation for this wrestler.
            pf7_sum += float(pd7_for_pop)
            pa7_sum += float(pa7_this_pop)
            pfpa_count += 1

            opp_matches_pop = matches_by_wrestler.get(opp_id_pop, [])
            other_sides_pop = [e for e in opp_matches_pop if e["key"] != key_pop]

            # Offensive side (APS7): PD7_for vs opponent PA7 baseline.
            if other_sides_pop:
                pa_raw_pop = sum(e["pa7"] for e in other_sides_pop) / float(
                    len(other_sides_pop)
                )
                n_pop = len(other_sides_pop)
            else:
                pa_raw_pop = league_pa7
                n_pop = 0

            pa_adj_pop = (
                (pa_raw_pop * n_pop + league_pa7 * K) / float(n_pop + K)
                if (n_pop + K) > 0
                else league_pa7
            )
            contribs_off.append(pd7_for_pop - pa_adj_pop)

            # Defensive side (APG7): opponent PF7 vs opponent PF7 baseline.
            opp_this_pop = next(
                (e for e in opp_matches_pop if e["key"] == key_pop),
                None,
            )
            if opp_this_pop is None:
                raise RuntimeError(f"Missing reverse match entry for key: {key_pop}")
            pf7_this_pop = opp_this_pop["pd7_for"]
            other_off_pop = [e for e in opp_matches_pop if e["key"] != key_pop]
            if other_off_pop:
                pf_raw_pop = sum(e["pd7_for"] for e in other_off_pop) / float(
                    len(other_off_pop)
                )
                n_off_pop = len(other_off_pop)
            else:
                pf_raw_pop = league_pf7
                n_off_pop = 0

            pf_adj_pop = (
                (pf_raw_pop * n_off_pop + league_pf7 * K) / float(n_off_pop + K)
                if (n_off_pop + K) > 0
                else league_pf7
            )
            contribs_def.append(pf_adj_pop - pf7_this_pop)

            # APD7 side (adjusted point differential).
            # PD7 for this wrestler in this bout:
            pd7_self = pd7_for_pop - pa7_this_pop
            # Opponent PD7 baseline from their other matches (their perspective).
            if other_sides_pop:
                pd7_raw_opp = sum(
                    float(e["pd7_for"]) - float(e["pa7"]) for e in other_sides_pop
                ) / float(len(other_sides_pop))
                n_pd = len(other_sides_pop)
            else:
                pd7_raw_opp = league_pd7
                n_pd = 0
            pd7_adj_opp = (
                (pd7_raw_opp * n_pd + league_pd7 * K) / float(n_pd + K)
                if (n_pd + K) > 0
                else league_pd7
            )
            # Expected margin for this wrestler vs this opponent is -PD7_opp.
            apd_contrib = pd7_self + pd7_adj_opp
            contribs_apd.append(apd_contrib)

        if contribs_off:
            aps_val = sum(contribs_off) / float(len(contribs_off))
            aps_by_id[wid_pop] = aps_val
            aps_vals_pop.append(aps_val)
        if contribs_def:
            apg_val = sum(contribs_def) / float(len(contribs_def))
            apg_by_id[wid_pop] = apg_val
            apg_vals_pop.append(apg_val)
        if contribs_apd:
            apd_val = sum(contribs_apd) / float(len(contribs_apd))
            apd_by_id[wid_pop] = apd_val
            apd_vals_pop.append(apd_val)

        if pfpa_count > 0:
            pf7_by_id[wid_pop] = pf7_sum / float(pfpa_count)
            pa7_by_id[wid_pop] = pa7_sum / float(pfpa_count)

    # Build pin histories and APR for all wrestlers (mirrors APR logic above).
    from collections import defaultdict as _dd

    def _build_pin_history_all(
        season_: int,
    ) -> tuple[dict[str, list[dict]], float]:
        teams = load_team_data(season_)
        pin_matches: dict[str, list[dict]] = _dd(list)
        seen_keys = set()
        total_bouts = 0
        total_pin_losses = 0

        for team in teams:
            for w in team.get("roster", []) or []:
                wid_local = str(w.get("season_wrestler_id") or "")
                if not wid_local or wid_local == "null":
                    continue
                wname = w.get("name", "") or ""
                for m in w.get("matches", []) or []:
                    summary = m.get("summary", "") or ""
                    s_sum = summary.lower()
                    if "received a bye" in s_sum:
                        continue
                    opp_id_local = str(m.get("opponent_id") or "")
                    if not opp_id_local or opp_id_local == "null":
                        continue
                    date = m.get("date", "") or ""
                    w1, w2 = sorted([wid_local, opp_id_local])
                    match_key = (w1, w2, date, summary)
                    if match_key in seen_keys:
                        continue
                    seen_keys.add(match_key)

                    if any(
                        kw in s_sum
                        for kw in ["forfeit", "mff", " ff", "dq", "inj", "injury"]
                    ):
                        continue

                    over_idx = s_sum.find(" over ")
                    name_idx = s_sum.find(wname.lower())
                    if over_idx == -1 or name_idx == -1:
                        continue
                    if name_idx < over_idx:
                        winner_id = wid_local
                        loser_id = opp_id_local
                    else:
                        winner_id = opp_id_local
                        loser_id = wid_local

                    w1_is_winner = winner_id == w1
                    is_fall = ("fall" in s_sum) and not any(
                        kw in s_sum for kw in ["tech fall", "tf "]
                    )

                    total_bouts += 1
                    if is_fall and loser_id:
                        total_pin_losses += 1

                    def add_side(side_wid: str, is_winner_side: bool) -> None:
                        opp_side = w2 if side_wid == w1 else w1
                        pin_matches[side_wid].append(
                            {
                                "key": match_key,
                                "opponent_id": opp_side,
                                "result": summary,
                                "is_win": is_winner_side,
                                "is_fall_win": is_winner_side and is_fall,
                                "is_fall_loss": (not is_winner_side) and is_fall,
                            }
                        )

                    add_side(w1, w1_is_winner)
                    add_side(w2, not w1_is_winner)

        lpr = (total_pin_losses / float(total_bouts)) if total_bouts > 0 else 0.0
        return pin_matches, lpr

    pin_matches_all, LPR_all = _build_pin_history_all(season)
    apr_by_id: Dict[str, float] = {}
    apr_vals_pop: List[float] = []
    k_pin = 12.0
    for wid_pop, plist in pin_matches_all.items():
        contribs_pop: List[float] = []
        for m_pop in plist:
            key_pop = m_pop["key"]
            opp_id_pop = m_pop["opponent_id"]
            pin_outcome_pop = 1.0 if m_pop.get("is_fall_win") else 0.0

            opp_hist_pop = pin_matches_all.get(opp_id_pop, [])
            other_pop = [e for e in opp_hist_pop if e["key"] != key_pop]
            if other_pop:
                n_pop = len(other_pop)
                pin_allow_raw_pop = sum(
                    1.0 for e in other_pop if e.get("is_fall_loss")
                ) / float(n_pop)
            else:
                n_pop = 0
                pin_allow_raw_pop = LPR_all

            pin_allow_adj_pop = (
                (pin_allow_raw_pop * n_pop + LPR_all * k_pin) / float(n_pop + k_pin)
                if (n_pop + k_pin) > 0
                else LPR_all
            )
            contribs_pop.append(pin_outcome_pop - pin_allow_adj_pop)

        if contribs_pop:
            apr_val = sum(contribs_pop) / float(len(contribs_pop))
            apr_by_id[wid_pop] = apr_val
            apr_vals_pop.append(apr_val)

    from statistics import mean as _mean, pstdev as _pstdev

    def _mean_std(values: List[float]) -> tuple[float, float]:
        vals = [float(v) for v in values if v is not None]
        if not vals:
            return 0.0, 1.0
        mu = _mean(vals)
        sigma = _pstdev(vals)
        if sigma <= 0.0:
            sigma = 1.0
        return mu, sigma

    mean_APS7, std_APS7 = _mean_std(aps_vals_pop)
    mean_APG7, std_APG7 = _mean_std(apg_vals_pop)
    mean_APR, std_APR = _mean_std(apr_vals_pop)
    # APD7 league moments are available if needed in future:
    mean_APD7, std_APD7 = _mean_std(apd_vals_pop)

    metrics_by_id: Dict[str, Dict[str, float]] = {}
    for wid in set(
        list(aps_by_id.keys())
        + list(apg_by_id.keys())
        + list(apr_by_id.keys())
        + list(apd_by_id.keys())
        + list(pf7_by_id.keys())
        + list(pa7_by_id.keys())
    ):
        aps = aps_by_id.get(wid, 0.0)
        apg = apg_by_id.get(wid, 0.0)
        apr = apr_by_id.get(wid, 0.0)
        apd = apd_by_id.get(wid, 0.0)
        pf7_raw = pf7_by_id.get(wid, 0.0)
        pa7_raw = pa7_by_id.get(wid, 0.0)

        z_SI = (aps - mean_APS7) / std_APS7 if std_APS7 > 0 else 0.0
        z_DF = (apg - mean_APG7) / std_APG7 if std_APG7 > 0 else 0.0
        z_PE = (apr - mean_APR) / std_APR if std_APR > 0 else 0.0

        SI_plus = 100.0 + 10.0 * z_SI
        DF_plus = 100.0 + 10.0 * z_DF
        PE_plus = 100.0 + 10.0 * z_PE
        DI_raw = (
            DI_WEIGHT_SI * SI_plus
            + DI_WEIGHT_DF * DF_plus
            + DI_WEIGHT_PE * PE_plus
        )

        metrics_by_id[wid] = {
            "APS7": aps,
            "APG7": apg,
            "APR": apr,
            "APD7": apd,
            "PF7_raw": pf7_raw,
            "PA7_raw": pa7_raw,
            "SI_plus": SI_plus,
            "DF_plus": DF_plus,
            "PE_plus": PE_plus,
            "DI_raw": DI_raw,
        }

    return metrics_by_id


def get_quintile_metric_summary(
    season: int,
    max_rank: int,
    weight_class: str,
    quintile: int,
    metrics_by_id: Optional[Dict[str, Dict[str, float]]] = None,
) -> Optional[Dict[str, float]]:
    """
    Compute APS7/APG7/APD7/APR mean/std for a given weight class and quintile.

    Quintiles are defined within the weight's full rankings file
    (rankings_{weight}.json), split into 5 equal-sized groups (top 20%, next 20%, ...),
    using *all* ranked wrestlers at that weight (starters and backups).

    Returns a dict with:
        {
          "count": n,
          "APS7_mean": ...,
          "APS7_std": ...,
          "APG7_mean": ...,
          "APG7_std": ...,
          "APD7_mean": ...,
          "APD7_std": ...,
          "APR_mean": ...,
          "APR_std": ...,
        }
    or None if there are no wrestlers in that bucket.
    """
    from statistics import mean as _mean, pstdev as _pstdev

    def _mean_std(vals: List[float]) -> tuple[float, float]:
        if not vals:
            return 0.0, 0.0
        mu = _mean(vals)
        sigma = _pstdev(vals)
        return mu, sigma

    if quintile < 1 or quintile > 5:
        raise ValueError("quintile must be in 1..5")

    if metrics_by_id is None:
        metrics_by_id = _compute_plus_metrics_for_all(season, max_rank)

    rankings_path = Path("mt/rankings_data") / str(season) / f"rankings_{weight_class}.json"
    if not rankings_path.exists():
        print(f"Quintile summary: no rankings file for weight {weight_class} at {rankings_path}")
        return None

    try:
        with rankings_path.open("r", encoding="utf-8") as rf:
            rankings_data = json.load(rf)
    except Exception as e:
        print(f"Quintile summary: failed to read {rankings_path}: {e}")
        return None

    rankings = rankings_data.get("rankings", [])
    # Use all ranked wrestlers at this weight (not just starters), but only
    # those for whom we actually have APS7/APG7/APD7/APR metrics. This keeps
    # quintile bucket sizes balanced relative to the population we're
    # summarizing, instead of being skewed by low-ranked wrestlers who have
    # no valid-match stats yet.
    ranked_rows_all = [r for r in rankings if r.get("wrestler_id")]
    ranked_rows = [
        r
        for r in ranked_rows_all
        if str(r.get("wrestler_id") or "") in metrics_by_id
    ]
    if not ranked_rows:
        print(
            f"Quintile summary: no ranked wrestlers with metrics for weight {weight_class}"
        )
        return None

    # Sort by rank within the weight.
    ranked_rows.sort(key=lambda r: int(r.get("rank", 10**9)))
    n = len(ranked_rows)
    # Quintile boundaries (0-based indices)
    start_idx = (quintile - 1) * n // 5
    end_idx = quintile * n // 5 - 1
    end_idx = max(end_idx, start_idx)

    subset = ranked_rows[start_idx : end_idx + 1]
    if not subset:
        return None

    aps_vals: List[float] = []
    apg_vals: List[float] = []
    apd_vals: List[float] = []
    apr_vals: List[float] = []
    pf7_vals: List[float] = []
    pa7_vals: List[float] = []

    for r in subset:
        wid = str(r.get("wrestler_id") or "")
        m = metrics_by_id.get(wid)
        if not m:
            continue
        aps_vals.append(float(m.get("APS7", 0.0)))
        apg_vals.append(float(m.get("APG7", 0.0)))
        apd_vals.append(float(m.get("APD7", 0.0)))
        apr_vals.append(float(m.get("APR", 0.0)))
        pf7_vals.append(float(m.get("PF7_raw", 0.0)))
        pa7_vals.append(float(m.get("PA7_raw", 0.0)))

    if not (aps_vals or apg_vals or apd_vals or apr_vals or pf7_vals or pa7_vals):
        return None

    aps_mean, aps_std = _mean_std(aps_vals)
    apg_mean, apg_std = _mean_std(apg_vals)
    apd_mean, apd_std = _mean_std(apd_vals)
    apr_mean, apr_std = _mean_std(apr_vals)
    pf7_mean, pf7_std = _mean_std(pf7_vals)
    pa7_mean, pa7_std = _mean_std(pa7_vals)

    return {
        "count": float(len(aps_vals) or len(apg_vals) or len(apd_vals) or len(apr_vals)),
        "APS7_mean": aps_mean,
        "APS7_std": aps_std,
        "APG7_mean": apg_mean,
        "APG7_std": apg_std,
        "APD7_mean": apd_mean,
        "APD7_std": apd_std,
        "APR_mean": apr_mean,
        "APR_std": apr_std,
        "PF7_mean": pf7_mean,
        "PF7_std": pf7_std,
        "PA7_mean": pa7_mean,
        "PA7_std": pa7_std,
    }


def is_invalid_result_for_anppm(result: str, summary: str) -> bool:
    """
    Determine if a match result should be excluded from ANPPM.

    Excludes:
      - Falls/pins
      - MFF / Forfeit / FF
      - DQ
      - INJ / injury defaults
      - Explicit BYE / NoResult (handled earlier, but double-check)
    """
    s = (result or "").lower()
    t = (summary or "").lower()

    # Already-excluded types
    if "bye" in s or "noresult" in s:
        return True

    # Falls/pins
    if "fall" in s or "pin" in s or "pinned" in s:
        return True

    # Forfeits / medical forfeits
    if "mff" in s or "forfeit" in s or "ff" in s:
        return True

    # DQ
    if "dq" in s:
        return True

    # Injuries
    if "inj" in s or "injury" in s:
        return True

    # Also look in summary for these cues (belt-and-suspenders).
    if any(
        kw in t
        for kw in [
            "forfeit",
            "mff",
            "injury",
            "inj.",
            "inj default",
            "disqualified",
        ]
    ):
        return True

    return False


def build_all_matches(
    season: int,
    rank_by_id: Dict[str, int],
) -> Tuple[
    Dict[str, Dict],
    Dict[str, List[Dict]],
    Dict[str, float],
    Dict[str, int],
    Dict[str, float],
    Dict[str, int],
    int,
]:
    """
    Build per-wrestler valid-match data structures for ANPPM.

    Returns:
      - wrestlers: wid -> {name, team, weight_class, rank_or_None}
      - matches_by_wrestler: wid -> list of match dicts:
            {
              'key': match_key,
              'opponent_id': opp_id,
              'weight_class': weight_str,
              'pd7_for': float,
              'pa7': float,           # points allowed per 7
            }
      - pa7_sum_by_wrestler: wid -> sum(pa7 over valid matches)
      - pa7_count_by_wrestler: wid -> number of valid matches
      - pa7_sum_by_weight: weight -> sum(pa7 over all sides)
      - pa7_count_by_weight: weight -> number of pa7 entries
      - excluded_invalid_count: number of matches skipped as invalid
    """
    teams = load_team_data(season)

    # Basic roster info by wrestler_id
    wrestlers: Dict[str, Dict] = {}

    for team in teams:
        team_name = team.get("team_name", "Unknown")
        for w in team.get("roster", []):
            wid = str(w.get("season_wrestler_id") or "")
            if not wid or wid == "null":
                continue
            if wid not in wrestlers:
                wrestlers[wid] = {
                    "wrestler_id": wid,
                    "name": w.get("name", "Unknown"),
                    "team": team_name,
                    "weight_class": str(w.get("weight_class", "") or ""),
                }

    matches_by_wrestler: Dict[str, List[Dict]] = defaultdict(list)
    pa7_sum_by_wrestler: Dict[str, float] = defaultdict(float)
    pa7_count_by_wrestler: Dict[str, int] = defaultdict(int)

    pa7_sum_by_weight: Dict[str, float] = defaultdict(float)
    pa7_count_by_weight: Dict[str, int] = defaultdict(int)

    seen_matches = set()
    excluded_invalid_count = 0

    for team in teams:
        team_name = team.get("team_name", "Unknown")
        for w in team.get("roster", []):
            wid = str(w.get("season_wrestler_id") or "")
            if not wid or wid == "null":
                continue

            wname = w.get("name", "Unknown")
            primary_wc = str(w.get("weight_class", "") or "")

            for m in w.get("matches", []) or []:
                result = m.get("result", "") or ""
                summary = m.get("summary", "") or ""

                # Skip BYEs / NoResult early.
                if result in ("BYE", "NoResult") or "received a bye" in summary.lower():
                    continue

                opp_id = str(m.get("opponent_id") or "")
                if not opp_id or opp_id == "null":
                    continue

                # We only handle matches where we know both wrestlers as D1 IDs.
                if wid not in wrestlers or opp_id not in wrestlers:
                    continue

                # De-duplicate match via a normalized key.
                date = m.get("date", "") or ""
                # Use a normalized match key that does NOT depend on the event
                # label so that the same bout recorded in both teams' files
                # (with slightly different event strings) is only counted once.
                w1, w2 = sorted([wid, opp_id])
                match_key = (w1, w2, date, result)
                if match_key in seen_matches:
                    continue
                seen_matches.add(match_key)

                # Valid score?
                score_pair = _parse_score_from_result(result)
                if not score_pair:
                    # No numeric score -> invalid for ANPPM
                    excluded_invalid_count += 1
                    continue

                if is_invalid_result_for_anppm(result, summary):
                    excluded_invalid_count += 1
                    continue

                winner_pts, loser_pts = score_pair

                winner_name = m.get("winner_name", "") or ""
                loser_name = m.get("loser_name", "") or ""
                winner_team = m.get("winner_team", "") or ""
                loser_team = m.get("loser_team", "") or ""

                # Determine which side is winner/loser by ID or name+team.
                winner_id = str(m.get("winner_id") or "")
                loser_id = str(m.get("loser_id") or "")

                # For robustness, match by ID first, then by name+team.
                if winner_id == w1 and loser_id == w2:
                    w1_is_winner = True
                elif winner_id == w2 and loser_id == w1:
                    w1_is_winner = False
                else:
                    # Fallback name/team matching.
                    w1_info = wrestlers[w1]
                    w2_info = wrestlers[w2]
                    if (
                        w1_info["name"] == winner_name
                        and w1_info["team"] == winner_team
                    ):
                        w1_is_winner = True
                    elif (
                        w2_info["name"] == winner_name
                        and w2_info["team"] == winner_team
                    ):
                        w1_is_winner = False
                    else:
                        # Can't reliably tell; skip match.
                        excluded_invalid_count += 1
                        continue

                # Determine weight class for this match.
                match_weight = str(m.get("weight", "") or "") or primary_wc
                if not match_weight:
                    match_weight = wrestlers[w1].get("weight_class") or wrestlers[w2].get(
                        "weight_class"
                    )
                match_weight = str(match_weight or "")

                duration_seconds = estimate_match_duration_seconds(result)

                # For each side, compute PD7_for and PA7.
                def add_side(side_wid: str, is_winner_side: bool) -> None:
                    if is_winner_side:
                        pts_for = float(winner_pts)
                        pts_against = float(loser_pts)
                    else:
                        pts_for = float(loser_pts)
                        pts_against = float(winner_pts)

                    pd7_for = pts_for * (7 * 60.0) / float(duration_seconds)
                    pa7 = pts_against * (7 * 60.0) / float(duration_seconds)

                    opp_id_side = w2 if side_wid == w1 else w1
                    opp_info = wrestlers.get(
                        opp_id_side, {"name": f"ID:{opp_id_side}", "team": "Unknown"}
                    )

                    entry = {
                        "key": match_key,
                        "opponent_id": opp_id_side,
                        "opponent_name": opp_info.get("name", f"ID:{opp_id_side}"),
                        "weight_class": match_weight,
                        "result": result,
                        "is_win": is_winner_side,
                        "pd7_for": pd7_for,
                        "pa7": pa7,
                    }
                    matches_by_wrestler[side_wid].append(entry)
                    pa7_sum_by_wrestler[side_wid] += pa7
                    pa7_count_by_wrestler[side_wid] += 1

                    pa7_sum_by_weight[match_weight] += pa7
                    pa7_count_by_weight[match_weight] += 1

                add_side(w1, w1_is_winner)
                add_side(w2, not w1_is_winner)

    return (
        wrestlers,
        matches_by_wrestler,
        pa7_sum_by_wrestler,
        pa7_count_by_wrestler,
        pa7_sum_by_weight,
        pa7_count_by_weight,
        excluded_invalid_count,
    )


def compute_anppm(
    season: int,
    max_rank: int,
) -> Tuple[
    List[Dict],
    List[Dict],
    List[Dict],
    Dict[str, List[Dict]],
    int,
    int,
    int,
    float,
    int,
]:
    """
    Compute NPF7/NPA7/NPD7 for **starter-only** ranked wrestlers 1..max_rank.
    
    Only starters (is_starter == True in rankings_*.json) are considered as
    ranked wrestlers. Non-starters remain in the dataset as opponents.
    """
    # Build starter-only rank map: wrestler_id -> starter-only rank (best across weights)
    rankings_dir = Path("mt/rankings_data") / str(season)
    if not rankings_dir.exists():
        print(f"[DEBUG] Rankings dir missing: {rankings_dir}")
        return [], [], [], {}, 0, 0, 0, 0.0, 0

    starter_rank_by_id: Dict[str, int] = {}
    for path in sorted(rankings_dir.glob("rankings_*.json")):
        print(f"[DEBUG] Inspecting rankings file: {path}")
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            print(f"[DEBUG] Failed to read rankings file: {path}")
            continue

        rankings = data.get("rankings", [])
        # Filter to starters only, then re-number by original rank.
        starters = []
        for r in rankings:
            if not r.get("is_starter", False):
                continue
            try:
                orig_rank = int(r.get("rank"))
            except (TypeError, ValueError):
                continue
            starters.append((orig_rank, r))

        starters.sort(key=lambda x: x[0])
        print(f"[DEBUG]  Starters in {path.name}: {len(starters)}")
        for new_rank, (_, r) in enumerate(starters, start=1):
            wid = str(r.get("wrestler_id") or "")
            if not wid:
                continue
            # Keep the best (lowest) starter-only rank across any appearances.
            if wid not in starter_rank_by_id or new_rank < starter_rank_by_id[wid]:
                starter_rank_by_id[wid] = new_rank

    print(f"[DEBUG] Total starters found across all weights: {len(starter_rank_by_id)}")
    if not starter_rank_by_id:
        print("[DEBUG] No starters found in rankings_* files.")
        return [], [], [], {}, 0, 0, 0, 0.0, 0

    # Keep only starters within the requested rank cutoff.
    rank_by_id = {wid: r for wid, r in starter_rank_by_id.items() if r <= max_rank}
    print(
        f"[DEBUG] Starters within rank <= {max_rank}: {len(rank_by_id)} "
        f"(season={season})"
    )
    if not rank_by_id:
        print("[DEBUG] No starters within requested rank cutoff.")
        return [], [], [], {}, 0, 0, 0, 0.0, 0

    (
        wrestlers,
        matches_by_wrestler,
        pa7_sum_by_wrestler,
        pa7_count_by_wrestler,
        pa7_sum_by_weight,
        pa7_count_by_weight,
        excluded_invalid_matches,
    ) = build_all_matches(season, rank_by_id)

    print(
        f"[DEBUG] build_all_matches: wrestlers={len(wrestlers)}, "
        f"with_matches={len(matches_by_wrestler)}, "
        f"excluded_invalid_matches={excluded_invalid_matches}"
    )

    if not matches_by_wrestler:
        print("[DEBUG] No matches found for starter-ranked wrestlers after filtering.")
        return [], [], [], {}, 0, excluded_invalid_matches, 0, 0.0, 0

    # Compute per-weight-class PA7 averages (defensive baseline for ANPF7)
    # and PF7 averages (offensive baseline for ANPA7).
    pa7_avg_by_weight: Dict[str, float] = {}
    pf7_sum_by_weight: Dict[str, float] = defaultdict(float)
    pf7_count_by_weight: Dict[str, int] = defaultdict(int)

    for wid, matches in matches_by_wrestler.items():
        for e in matches:
            wc = e.get("weight_class", "")
            if not wc:
                continue
            # Defensive: PA7 pooled by weight class
            pa7_sum_by_weight[wc] += e.get("pa7", 0.0)
            pa7_count_by_weight[wc] += 1
            # Offensive: PF7 pooled by weight class
            pf7_sum_by_weight[wc] += e.get("pd7_for", 0.0)
            pf7_count_by_weight[wc] += 1

    for wc in set(list(pa7_sum_by_weight.keys()) + list(pf7_sum_by_weight.keys())):
        pa7_c = pa7_count_by_weight.get(wc, 0)
        if pa7_c > 0:
            pa7_avg_by_weight[wc] = pa7_sum_by_weight[wc] / float(pa7_c)

    pf7_avg_by_weight: Dict[str, float] = {}
    for wc, s in pf7_sum_by_weight.items():
        c = pf7_count_by_weight.get(wc, 0)
        if c > 0:
            pf7_avg_by_weight[wc] = s / float(c)

    # Compute valid-match counts for each wrestler.
    valid_match_counts: Dict[str, int] = {
        wid: len(matches) for wid, matches in matches_by_wrestler.items()
    }

    # Average valid match count for starter-ranked wrestlers.
    top_counts = [valid_match_counts.get(wid, 0) for wid in rank_by_id.keys()]
    if not top_counts:
        print("[DEBUG] No valid matches for any starter-ranked wrestlers.")
        return [], [], [], {}, 0, excluded_invalid_matches, 0, 0.0, 0

    avg_valid_matches = sum(top_counts) / float(len(top_counts))

    # Threshold used for:
    #   - Including wrestlers in NPF7 / NPA7 lists.
    #   - Deciding when to trust opponent/wrestler baselines.
    # Spec: floor(50% of avg valid matches) with a floor of 2.
    threshold = max(2, int(math.floor(0.5 * avg_valid_matches)))

    # DEBUG: Starter + match-count summary
    print(
        f"[DEBUG] Starters within rank cutoff: {len(rank_by_id)} | "
        f"avg_valid_matches={avg_valid_matches:.2f}, threshold={threshold}"
    )
    debug_ids = list(rank_by_id.keys())[:20]
    for wid in debug_ids:
        print(
            f"[DEBUG] starter wid={wid} rank={rank_by_id[wid]} "
            f"valid_matches={valid_match_counts.get(wid, 0)}"
        )

    # For quick lookup of per-wrestler per-match pa7 contributions by key.
    pa7_by_wrestler_and_key: Dict[Tuple[str, Tuple], float] = {}
    for wid, matches in matches_by_wrestler.items():
        for m in matches:
            pa7_by_wrestler_and_key[(wid, m["key"])] = m["pa7"]

    # Precompute per-wrestler PA7 totals.
    # (We already have sums and counts in pa7_sum_by_wrestler / pa7_count_by_wrestler.)

    total_matches_used = 0
    matches_using_weight_avg = 0

    # Offensive NPF7 results (normalized points FOR per 7 minutes)
    ranked_results: List[Dict] = []
    # Defensive NPA7 results (normalized points AGAINST per 7 minutes)
    def_results: List[Dict] = []
    def_debug_by_wrestler: Dict[str, List[Dict]] = {}

    for wid, rank in rank_by_id.items():
        matches = matches_by_wrestler.get(wid, [])
        if not matches:
            continue

        w_info = wrestlers.get(wid, {"name": f"ID:{wid}", "team": "Unknown", "weight_class": ""})
        name = w_info["name"]
        team = w_info["team"]

        # For this wrestler, accumulate:
        #   - Offensive ANPPM scores (norm_scores)
        #   - Defensive normalized PA7 scores (def_norm_scores)
        # Guard against any accidental duplicate side-entries for the same
        # bout by de-duplicating on (match_key, opponent_id).
        match_entries: List[Dict] = []
        norm_scores: List[float] = []
        def_norm_scores: List[float] = []
        def_match_entries: List[Dict] = []
        seen_local_keys = set()

        for m in matches:
            key = m["key"]
            opp_id = m["opponent_id"]
            local_key = (key, opp_id)
            if local_key in seen_local_keys:
                continue
            seen_local_keys.add(local_key)

            weight_class = m["weight_class"]
            pd7_for = m["pd7_for"]
            pd7_against = m["pa7"]

            # Opponent PA7 for this match.
            opp_pa7_used: Optional[float] = None
            used_weight_avg = False

            opp_valid_count = valid_match_counts.get(opp_id, 0)
            opp_pa7_total = pa7_sum_by_wrestler.get(opp_id, 0.0)

            # Opponent contributes their own PA7 baseline only if they have
            # at least (threshold + 1) valid matches total, so that after
            # removing this bout there are still >= threshold matches.
            if opp_valid_count - 1 >= threshold:
                # Use opponent's own PA7 excluding this match.
                pa7_current = pa7_by_wrestler_and_key.get((opp_id, key), 0.0)
                opp_pa7_used = (opp_pa7_total - pa7_current) / float(
                    opp_valid_count - 1
                )
            # If we couldn't compute opp_pa7_used from own stats, fall back to weight avg.
            if opp_pa7_used is None:
                opp_wc = weight_class or wrestlers.get(opp_id, {}).get(
                    "weight_class", ""
                )
                opp_wc = str(opp_wc or "")
                if opp_wc in pa7_avg_by_weight:
                    opp_pa7_used = pa7_avg_by_weight[opp_wc]
                    used_weight_avg = True
                else:
                    # No weight-class average available; skip this match.
                    continue

            norm = pd7_for - opp_pa7_used
            norm_scores.append(norm)

            match_entry = {
                "match_key": key,
                "opponent_id": opp_id,
                "weight_class": weight_class,
                "pd7_for": pd7_for,
                "opp_pa7": opp_pa7_used,
                "norm": norm,
                "used_weight_avg": used_weight_avg,
            }
            match_entries.append(match_entry)

            total_matches_used += 1
            if used_weight_avg:
                matches_using_weight_avg += 1

            # --- Defensive side: normalized points against per 7 minutes (NPA7) ---
            # PA7 against this wrestler in this bout is the PA7 value we
            # already computed for this side (points scored by opponent).
            # Baseline is the opponent's typical PF7 (points scored per 7)
            # vs OTHER wrestlers.
            #
            #  - If opponent has at least `threshold` other valid matches,
            #    we use their own PF7 average (excluding this bout).
            #  - Otherwise, we fall back to the weight-class-average PF7.
            #
            # NPA7 contribution = baseline_PF7 - PF7_this_match, so a
            # positive value means the defender held the opponent below
            # their usual scoring rate.

            # Gather opponent's other offensive matches (from their perspective).
            opp_matches = matches_by_wrestler.get(opp_id, [])
            other_offensive = [e for e in opp_matches if e["key"] != key]

            def_baseline: Optional[float] = None
            used_weight_avg = False

            if len(other_offensive) >= threshold:
                # Use opponent's own PF7 average (excluding this bout).
                total_pf7 = sum(e.get("pd7_for", 0.0) for e in other_offensive)
                def_baseline = total_pf7 / float(len(other_offensive))
            else:
                # Fall back to weight-class-average PF7.
                own_wc = weight_class or wrestlers.get(wid, {}).get(
                    "weight_class", ""
                )
                own_wc = str(own_wc or "")
                if own_wc in pf7_avg_by_weight:
                    def_baseline = pf7_avg_by_weight[own_wc]
                    used_weight_avg = True
                else:
                    # No baseline available; skip defensive normalization for this bout.
                    continue

            # NPA7 contribution for this bout (baseline - actual).
            def_norm = def_baseline - pd7_against
            def_norm_scores.append(def_norm)

            # Collect the matches that contributed to the opponent's offensive baseline
            # (excluding this specific bout). This is what we show in debug.
            baseline_components: List[Dict] = []
            for e in other_offensive:
                baseline_components.append(
                    {
                        "opponent_id": e.get("opponent_id", ""),
                        "opponent_name": e.get("opponent_name", ""),
                        "result": e.get("result", ""),
                        "pf7": e.get("pd7_for", 0.0),
                    }
                )

            def_match_entries.append(
                {
                    "match_key": key,
                    "opponent_id": opp_id,
                    "opponent_name": m.get("opponent_name", ""),
                    "weight_class": weight_class,
                    "pd7_against": pd7_against,
                    "baseline_pa7": def_baseline,
                    "norm_against": def_norm,
                    "used_weight_avg": used_weight_avg,
                    "baseline_components": baseline_components,
                }
            )

        # Require at least `threshold` valid (non-fall, non-DQ, non-MFF, etc.)
        # matches for a wrestler to have meaningful normalized stats.
        if len(norm_scores) >= threshold:
            anppm = sum(norm_scores) / float(len(norm_scores))
            ranked_results.append(
                {
                    "wrestler_id": wid,
                    "name": name,
                    "team": team,
                    "rank": rank,
                    "anppm": anppm,
                    "matches": len(norm_scores),
                }
            )

        if len(def_norm_scores) >= threshold:
            avg_def = sum(def_norm_scores) / float(len(def_norm_scores))
            def_results.append(
                {
                    "wrestler_id": wid,
                    "name": name,
                    "team": team,
                    "rank": rank,
                    "npa7": avg_def,
                    "matches": len(def_norm_scores),
                }
            )
            def_debug_by_wrestler[wid] = def_match_entries

    # Sort offensive NPF7 (descending: higher is better offense).
    ranked_results.sort(key=lambda r: (r["anppm"], r["matches"]), reverse=True)

    # Sort defensive NPA7 (descending: higher = better defense vs baseline).
    def_results.sort(key=lambda r: (r["npa7"], r["matches"]), reverse=True)

    # Combined NPD7 (normalized point differential per 7 minutes) = NPF7 + NPA7.
    def_by_id = {r["wrestler_id"]: r for r in def_results}
    npd_results: List[Dict] = []
    for off in ranked_results:
        wid = off["wrestler_id"]
        if wid not in def_by_id:
            continue
        d = def_by_id[wid]
        npd = off["anppm"] + d["npa7"]
        npd_results.append(
            {
                "wrestler_id": wid,
                "name": off["name"],
                "team": off["team"],
                "rank": off["rank"],
                "npd7": npd,
                "matches_off": off["matches"],
                "matches_def": d["matches"],
            }
        )

    # Sort NPD7 descending (higher total normalized differential is better).
    npd_results.sort(key=lambda r: (r["npd7"], r["matches_off"] + r["matches_def"]), reverse=True)

    return (
        ranked_results,
        def_results,
        npd_results,
        def_debug_by_wrestler,
        total_matches_used,
        excluded_invalid_matches,
        matches_using_weight_avg,
        avg_valid_matches,
        threshold,
    )


def _bucket_nearest_int(value: float) -> int:
    """
    Bucket a float into the nearest integer with 0 bucket as:
      - [-0.49, 0.49] -> 0
      - [0.5, 1.49]  -> 1
      - [-1.49, -0.5] -> -1
    """
    if value >= 0:
        return int(math.floor(value + 0.5))
    else:
        return int(math.ceil(value - 0.5))


def _build_histogram_quartiles(
    metric_rows: List[Dict], value_key: str, max_rank: int
) -> Tuple[List[int], List[List[int]]]:
    """
    Build histogram buckets (nearest integer) with quartile coloring.

    Quartiles are defined over GLOBAL RANK, not the metric itself:
      - Q1 (Top 25%): ranks 1..qsize
      - Q2: ranks (qsize+1)..2*qsize
      - Q3: ranks (2*qsize+1)..3*qsize
      - Q4 (Bottom 25%): ranks > 3*qsize

    Returns:
      - buckets: sorted list of bucket centers (ints)
      - counts_per_quartile: list of 4 lists, each of length len(buckets),
        where counts_per_quartile[q][i] is the count in bucket i for quartile q.
    """
    if not metric_rows:
        return [], [[], [], [], []]

    qsize = max(1, max_rank // 4)

    bucket_qcounts: Dict[int, List[int]] = {}
    for row in metric_rows:
        v = float(row.get(value_key, 0.0))
        rank = int(row.get("rank", max_rank))
        b = _bucket_nearest_int(v)
        if b not in bucket_qcounts:
            bucket_qcounts[b] = [0, 0, 0, 0]

        # Determine quartile index based on GLOBAL rank
        if rank <= qsize:
            q = 0  # top 25%
        elif rank <= 2 * qsize:
            q = 1
        elif rank <= 3 * qsize:
            q = 2
        else:
            q = 3
        bucket_qcounts[b][q] += 1

    buckets = sorted(bucket_qcounts.keys())
    counts_per_quartile: List[List[int]] = [[], [], [], []]
    for b in buckets:
        for q in range(4):
            counts_per_quartile[q].append(bucket_qcounts[b][q])

    return buckets, counts_per_quartile


def _plot_histogram_quartiles(
    buckets: List[int],
    counts_per_quartile: List[List[int]],
    title: str,
    xlabel: str,
    output_path: Path,
) -> None:
    """
    Save a simple bar histogram to the given path.
    """
    if not buckets:
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(8, 4))

    x = np.arange(len(buckets))
    bottom = np.zeros(len(buckets))

    colors = ["#1f77b4", "#2ca02c", "#ff7f0e", "#d62728"]
    labels = ["Top 25%", "25–50%", "50–75%", "Bottom 25%"]

    for q in range(4):
        counts = np.array(counts_per_quartile[q])
        if counts.sum() == 0:
            continue
        plt.bar(
            x,
            counts,
            width=0.8,
            align="center",
            bottom=bottom,
            color=colors[q],
            edgecolor="black",
            label=labels[q],
        )
        bottom += counts

    plt.xticks(x, [str(b) for b in buckets])
    plt.xlabel(xlabel)
    plt.ylabel("Count")
    plt.title(title)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()


def _plot_joint_npf7_npa7(
    npd_results: List[Dict],
    npf7_by_id: Dict[str, float],
    npa7_by_id: Dict[str, float],
    max_rank: int,
    output_path: Path,
    highlight_team: Optional[str] = None,
) -> None:
    """
    Create a static joint distribution plot for local inspection.
    (Interactive HTML version is created separately in write_html_report.)
    """
    if not npd_results:
        return

    xs = []
    ys = []
    ranks = []
    teams = []
    for row in npd_results:
        wid = row["wrestler_id"]
        if wid not in npf7_by_id or wid not in npa7_by_id:
            continue
        xs.append(float(npf7_by_id[wid]))
        ys.append(float(npa7_by_id[wid]))
        ranks.append(int(row.get("rank", max_rank)))
        teams.append(row.get("team", ""))

    if not xs:
        return

    xs = np.array(xs)
    ys = np.array(ys)
    ranks = np.array(ranks)
    teams = np.array(teams)

    highlight_team_lower = highlight_team.lower() if highlight_team else None
    highlight_mask = (
        np.array([t.lower() == highlight_team_lower for t in teams])
        if highlight_team_lower
        else np.zeros_like(xs, dtype=bool)
    )

    if not highlight_team_lower:
        # Default coloring by rank quartile.
        qsize = max(1, max_rank // 4)

        def quartile_for_rank(r: int) -> int:
            if r <= qsize:
                return 0
            elif r <= 2 * qsize:
                return 1
            elif r <= 3 * qsize:
                return 2
            else:
                return 3

        q_indices = np.array([quartile_for_rank(int(r)) for r in ranks])
        colors = ["#1f77b4", "#2ca02c", "#ff7f0e", "#d62728"]

    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig = plt.figure(figsize=(8, 8))
    gs = fig.add_gridspec(
        2,
        2,
        width_ratios=[4, 1],
        height_ratios=[1, 4],
        wspace=0.05,
        hspace=0.05,
    )

    ax_top = fig.add_subplot(gs[0, 0])
    ax_right = fig.add_subplot(gs[1, 1])
    ax_main = fig.add_subplot(gs[1, 0])

    if highlight_team_lower:
        # Grey points for all wrestlers, blue highlight for the chosen team.
        ax_main.scatter(
            xs,
            ys,
            s=20,
            color="#bbbbbb",
            alpha=0.6,
            edgecolors="none",
        )
        if highlight_mask.any():
            ax_main.scatter(
                xs[highlight_mask],
                ys[highlight_mask],
                s=35,
                color="#1f77b4",
                alpha=0.95,
                edgecolors="black",
                linewidths=0.5,
            )
    else:
        for q in range(4):
            mask = q_indices == q
            if not mask.any():
                continue
            ax_main.scatter(
                xs[mask],
                ys[mask],
                s=25,
                color=colors[q],
                alpha=0.8,
                edgecolors="none",
            )

    ax_main.set_xlabel("NPF7 (normalized points for per 7)")
    ax_main.set_ylabel("NPA7 (normalized points against per 7)")

    ax_top.hist(xs, bins=20, color="#4c72b0", edgecolor="black")
    ax_top.set_ylabel("Count")
    ax_top.tick_params(labelbottom=False)

    ax_right.hist(ys, bins=20, orientation="horizontal", color="#4c72b0", edgecolor="black")
    ax_right.set_xlabel("Count")
    ax_right.tick_params(labelleft=False)

    ax_top.set_xlim(ax_main.get_xlim())
    ax_right.set_ylim(ax_main.get_ylim())

    fig.suptitle("NPF7 vs NPA7 Joint Distribution (static)", y=0.96)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()


def write_html_report(
    season: int,
    max_rank: int,
    ranked_results: List[Dict],
    def_results: List[Dict],
    npd_results: List[Dict],
    output_path: Path,
     team_filter: Optional[str] = None,
) -> None:
    """
    Write an HTML report containing tables for NPF7, NPA7, NPD7
    and histograms for each (bucketed by nearest integer).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    team_filter_normalized = team_filter.strip().lower() if team_filter else None

    # Build histograms using ALL wrestlers (not just starters).
    # We reuse the all-wrestler metrics helper and, when available, use
    # global rankings to assign quartiles for coloring. Unranked wrestlers
    # fall into the bottom quartile by default.
    all_metrics = _compute_plus_metrics_for_all(season, max_rank)
    try:
        rank_by_id_all = _load_rank_map(season)
    except Exception:
        rank_by_id_all = {}

    metric_rows_npf7: List[Dict] = []
    metric_rows_npa7: List[Dict] = []
    metric_rows_npd7: List[Dict] = []
    for wid, m in all_metrics.items():
        # Only include wrestlers whose global rank is within the max_rank cutoff.
        # Unranked wrestlers (or rank > max_rank) are excluded from these
        # "ranks 1–max_rank" histograms.
        rank_val = int(rank_by_id_all.get(wid, max_rank + 1))
        if rank_val > max_rank:
            continue
        aps7_val = float(m.get("APS7", 0.0))
        apg7_val = float(m.get("APG7", 0.0))
        npd7_val = aps7_val + apg7_val
        metric_rows_npf7.append({"wrestler_id": wid, "rank": rank_val, "anppm": aps7_val})
        metric_rows_npa7.append({"wrestler_id": wid, "rank": rank_val, "npa7": apg7_val})
        metric_rows_npd7.append({"wrestler_id": wid, "rank": rank_val, "npd7": npd7_val})

    buckets_npf7, qcounts_npf7 = _build_histogram_quartiles(
        metric_rows_npf7, "anppm", max_rank
    )
    buckets_npa7, qcounts_npa7 = _build_histogram_quartiles(
        metric_rows_npa7, "npa7", max_rank
    )
    buckets_npd7, qcounts_npd7 = _build_histogram_quartiles(
        metric_rows_npd7, "npd7", max_rank
    )

    graphics_dir = Path("mt/graphics") / str(season)
    hist_npf7_path = graphics_dir / f"npf7_hist_rank1-{max_rank}.png"
    hist_npa7_path = graphics_dir / f"npa7_hist_rank1-{max_rank}.png"
    hist_npd7_path = graphics_dir / f"npd7_hist_rank1-{max_rank}.png"

    # For joint plots, keep the default filenames for the global (no-team) report.
    # When a team filter is applied, write team-specific joint plots so the
    # original report remains unchanged.
    if team_filter_normalized:
        safe_team = re.sub(r"[^a-z0-9]+", "_", team_filter_normalized).strip("_")
        joint_path = graphics_dir / f"npf7_vs_npa7_joint_rank1-{max_rank}_team-{safe_team}.png"
        joint_interactive_path = (
            graphics_dir
            / f"npf7_vs_npa7_joint_interactive_rank1-{max_rank}_team-{safe_team}.html"
        )
    else:
        joint_path = graphics_dir / f"npf7_vs_npa7_joint_rank1-{max_rank}.png"
        joint_interactive_path = (
            graphics_dir
            / f"npf7_vs_npa7_joint_interactive_rank1-{max_rank}.html"
        )

    _plot_histogram_quartiles(
        buckets_npf7,
        qcounts_npf7,
        f"NPF7 Distribution (ranks 1–{max_rank})",
        "NPF7 bucket",
        hist_npf7_path,
    )
    _plot_histogram_quartiles(
        buckets_npa7,
        qcounts_npa7,
        f"NPA7 Distribution (ranks 1–{max_rank})",
        "NPA7 bucket",
        hist_npa7_path,
    )
    _plot_histogram_quartiles(
        buckets_npd7,
        qcounts_npd7,
        f"NPD7 Distribution (ranks 1–{max_rank})",
        "NPD7 bucket",
        hist_npd7_path,
    )

    # Joint distribution plot (NPF7 vs NPA7)
    npf7_by_id = {r["wrestler_id"]: r["anppm"] for r in ranked_results}
    npa7_by_id = {r["wrestler_id"]: r["npa7"] for r in def_results}
    _plot_joint_npf7_npa7(
        npd_results,
        npf7_by_id,
        npa7_by_id,
        max_rank,
        joint_path,
        team_filter if team_filter_normalized else None,
    )

    # Interactive joint plot with hover tooltips (Plotly)
    if npd_results:
        xs = []
        ys = []
        ranks = []
        names = []
        teams = []
        npd_vals = []
        wrestler_ids = []
        for row in npd_results:
            wid = row["wrestler_id"]
            if wid not in npf7_by_id or wid not in npa7_by_id:
                continue
            xs.append(float(npf7_by_id[wid]))
            ys.append(float(npa7_by_id[wid]))
            ranks.append(int(row.get("rank", max_rank)))
            names.append(row["name"])
            teams.append(row["team"])
            npd_vals.append(float(row["npd7"]))
            wrestler_ids.append(wid)

        if xs:
            # Build joint plot with scatter + solid-color histograms using Plotly subplots
            fig = make_subplots(
                rows=2,
                cols=2,
                column_widths=[0.8, 0.2],
                row_heights=[0.2, 0.8],
                specs=[[{"type": "xy"}, {"type": "histogram"}],
                       [{"type": "xy"}, {"type": "histogram"}]],
                horizontal_spacing=0.04,
                vertical_spacing=0.04,
            )

            customdata = np.column_stack([teams, ranks, npd_vals, wrestler_ids])

            if team_filter_normalized:
                # Grey for all wrestlers, blue for the selected team.
                is_team = np.array(
                    [t.lower() == team_filter_normalized for t in teams]
                )
                # Others
                if (~is_team).any():
                    fig.add_trace(
                        go.Scatter(
                            x=np.array(xs)[~is_team],
                            y=np.array(ys)[~is_team],
                            mode="markers",
                            name="Others",
                            marker=dict(color="#bbbbbb", size=6, opacity=0.7),
                            text=np.array(names)[~is_team],
                            customdata=customdata[~is_team],
                            hovertemplate=(
                                "Name=%{text}<br>"
                                "Team=%{customdata[0]}<br>"
                                "Rank=%{customdata[1]}<br>"
                                "NPF7=%{x:.2f}<br>"
                                "NPA7=%{y:.2f}<br>"
                                "NPD7=%{customdata[2]:.2f}<br>"
                                "ID=%{customdata[3]}<extra></extra>"
                            ),
                        ),
                        row=2,
                        col=1,
                    )
                # Highlight team
                if is_team.any():
                    fig.add_trace(
                        go.Scatter(
                            x=np.array(xs)[is_team],
                            y=np.array(ys)[is_team],
                            mode="markers",
                            name=f"{team_filter} starters",
                            marker=dict(color="#1f77b4", size=8, opacity=0.95),
                            text=np.array(names)[is_team],
                            customdata=customdata[is_team],
                            hovertemplate=(
                                "Name=%{text}<br>"
                                "Team=%{customdata[0]}<br>"
                                "Rank=%{customdata[1]}<br>"
                                "NPF7=%{x:.2f}<br>"
                                "NPA7=%{y:.2f}<br>"
                                "NPD7=%{customdata[2]:.2f}<br>"
                                "ID=%{customdata[3]}<extra></extra>"
                            ),
                        ),
                        row=2,
                        col=1,
                    )
            else:
                # Default color by rank quartile.
                qsize = max(1, max_rank // 4)

                def quartile_label(r: int) -> str:
                    if r <= qsize:
                        return "Top 25%"
                    elif r <= 2 * qsize:
                        return "25–50%"
                    elif r <= 3 * qsize:
                        return "50–75%"
                    else:
                        return "Bottom 25%"

                quartiles = [quartile_label(r) for r in ranks]
                colors = {
                    "Top 25%": "#1f77b4",
                    "25–50%": "#2ca02c",
                    "50–75%": "#ff7f0e",
                    "Bottom 25%": "#d62728",
                }

                for q_label, color in colors.items():
                    mask = np.array(quartiles) == q_label
                    if not mask.any():
                        continue
                    fig.add_trace(
                        go.Scatter(
                            x=np.array(xs)[mask],
                            y=np.array(ys)[mask],
                            mode="markers",
                            name=q_label,
                            marker=dict(color=color, size=6, opacity=0.9),
                            text=np.array(names)[mask],
                            customdata=customdata[mask],
                            hovertemplate=(
                                "Name=%{text}<br>"
                                "Team=%{customdata[0]}<br>"
                                "Rank=%{customdata[1]}<br>"
                                "NPF7=%{x:.2f}<br>"
                                "NPA7=%{y:.2f}<br>"
                                "NPD7=%{customdata[2]:.2f}<br>"
                                "ID=%{customdata[3]}<extra></extra>"
                            ),
                        ),
                        row=2,
                        col=1,
                    )

            # Top histogram: NPF7 (solid color)
            fig.add_trace(
                go.Histogram(
                    x=xs,
                    nbinsx=20,
                    marker_color="#4c72b0",
                    showlegend=False,
                    opacity=0.8,
                ),
                row=1,
                col=1,
            )

            # Right histogram: NPA7 (solid color)
            fig.add_trace(
                go.Histogram(
                    y=ys,
                    nbinsy=20,
                    marker_color="#4c72b0",
                    showlegend=False,
                    opacity=0.8,
                ),
                row=2,
                col=2,
            )

            fig.update_xaxes(showticklabels=False, row=1, col=1)
            fig.update_yaxes(showticklabels=False, row=2, col=2)

            fig.update_xaxes(title_text="NPF7 (normalized points for per 7)", row=2, col=1)
            fig.update_yaxes(title_text="NPA7 (normalized points against per 7)", row=2, col=1)

            title_suffix = (
                f" — {team_filter} highlighted"
                if team_filter_normalized
                else ""
            )
            fig.update_layout(
                title=(
                    f"NPF7 vs NPA7 Joint Distribution — Season {season}, "
                    f"ranks 1–{max_rank}{title_suffix}"
                ),
                legend_title_text="Rank Quartile"
                if not team_filter_normalized
                else "Legend",
            )
            joint_interactive_path.parent.mkdir(parents=True, exist_ok=True)
            fig.write_html(joint_interactive_path, include_plotlyjs="cdn", full_html=True)

    def _rows_for_top_bottom(
        results: List[Dict], metric_key: str
    ) -> Tuple[List[Dict], List[Dict]]:
        top = results[:10]
        bottom = list(reversed(results))[:10]
        bottom.reverse()
        return top, bottom

    if team_filter_normalized:
        def _filter_team(rows: List[Dict]) -> List[Dict]:
            return [
                r for r in rows if r.get("team", "").lower() == team_filter_normalized
            ]

        team_npf7 = _filter_team(ranked_results)
        team_npa7 = _filter_team(def_results)
        team_npd7 = _filter_team(npd_results)
        top_npf7, bottom_npf7 = team_npf7, []
        top_npa7, bottom_npa7 = team_npa7, []
        top_npd7, bottom_npd7 = team_npd7, []
    else:
        top_npf7, bottom_npf7 = _rows_for_top_bottom(ranked_results, "anppm")
        top_npa7, bottom_npa7 = _rows_for_top_bottom(def_results, "npa7")
        top_npd7, bottom_npd7 = _rows_for_top_bottom(npd_results, "npd7")

    def _html_table(rows: List[Dict], metric_label: str, metric_key: str) -> str:
        if not rows:
            return "<p>(no wrestlers)</p>"
        header = (
            "<table><thead><tr>"
            "<th>#</th><th>Rank</th><th>Name</th><th>Team</th>"
            f"<th>{metric_label}</th><th>Matches</th>"
            "</tr></thead><tbody>"
        )
        body_lines = []
        for idx, r in enumerate(rows, start=1):
            rank = r["rank"]
            name = r["name"]
            team = r["team"]
            val = r[metric_key]
            matches = r.get("matches", r.get("matches_off", 0) + r.get("matches_def", 0))
            body_lines.append(
                f"<tr><td>{idx}</td><td>{rank}</td><td>{name}</td><td>{team}</td>"
                f"<td>{val:+.2f}</td><td>{matches}</td></tr>"
            )
        return header + "\n".join(body_lines) + "</tbody></table>"

    def _html_table_npd(rows: List[Dict]) -> str:
        if not rows:
            return "<p>(no wrestlers)</p>"
        header = (
            "<table><thead><tr>"
            "<th>#</th><th>Rank</th><th>Name</th><th>Team</th>"
            "<th>NPD7</th><th>NPF7</th><th>NPA7</th>"
            "<th>Off Matches</th><th>Def Matches</th>"
            "</tr></thead><tbody>"
        )
        body_lines = []
        # Build lookup for NPF7/NPA7
        npf7_by_id = {r["wrestler_id"]: r["anppm"] for r in ranked_results}
        npa7_by_id = {r["wrestler_id"]: r["npa7"] for r in def_results}
        for idx, r in enumerate(rows, start=1):
            wid = r["wrestler_id"]
            rank = r["rank"]
            name = r["name"]
            team = r["team"]
            npd7 = r["npd7"]
            npf7 = npf7_by_id.get(wid, 0.0)
            npa7 = npa7_by_id.get(wid, 0.0)
            m_off = r["matches_off"]
            m_def = r["matches_def"]
            body_lines.append(
                f"<tr><td>{idx}</td><td>{rank}</td><td>{name}</td><td>{team}</td>"
                f"<td>{npd7:+.2f}</td><td>{npf7:+.2f}</td><td>{npa7:+.2f}</td>"
                f"<td>{m_off}</td><td>{m_def}</td></tr>"
            )
        return header + "\n".join(body_lines) + "</tbody></table>"

    html = []
    html.append("<!DOCTYPE html>")
    html.append("<html><head><meta charset='utf-8'>")
    title_suffix = (
        f" — {team_filter} starters" if team_filter_normalized else ""
    )
    html.append(f"<title>NPF7/NPA7/NPD7 Report — Season {season}{title_suffix}</title>")
    html.append(
        "<style>"
        "body { font-family: system-ui, -apple-system, BlinkMacSystemFont, sans-serif; margin: 20px; }"
        "h1, h2, h3 { margin-top: 1em; }"
        "table { border-collapse: collapse; width: 100%; margin-bottom: 1em; }"
        "th, td { border: 1px solid #ddd; padding: 4px 6px; text-align: left; }"
        "th { background-color: #f0f0f0; }"
        "tbody tr:nth-child(even) { background-color: #fafafa; }"
        ".hist img { max-width: 100%; height: auto; }"
        "</style>"
    )
    html.append("</head><body>")
    heading_suffix = (
        f" (team: {team_filter})" if team_filter_normalized else ""
    )
    html.append(
        f"<h1>NPF7 / NPA7 / NPD7 — Season {season}, ranks 1–{max_rank}{heading_suffix}</h1>"
    )

    # Histograms / joint plots
    html.append("<div class='hist'>")
    # For team-specific reports, omit the three global histograms but keep the
    # joint distribution plots. For the global report, include all histograms.
    if not team_filter_normalized:
        if hist_npf7_path.exists():
            html.append(
                f"<h2>NPF7 Histogram</h2>"
                f"<img src='{hist_npf7_path.name}' alt='NPF7 histogram' />"
            )
        if hist_npa7_path.exists():
            html.append(
                f"<h2>NPA7 Histogram</h2>"
                f"<img src='{hist_npa7_path.name}' alt='NPA7 histogram' />"
            )
        if hist_npd7_path.exists():
            html.append(
                f"<h2>NPD7 Histogram</h2>"
                f"<img src='{hist_npd7_path.name}' alt='NPD7 histogram' />"
            )
    if joint_path.exists():
        html.append(
            f"<h2>NPF7 vs NPA7 Joint Distribution (static)</h2>"
            f"<img src='{joint_path.name}' alt='NPF7 vs NPA7 joint plot' />"
        )
    if joint_interactive_path.exists():
        html.append(
            "<h2>NPF7 vs NPA7 Joint Distribution (interactive)</h2>"
            f"<iframe src='{joint_interactive_path.name}' "
            "width='100%' height='600' style='border:1px solid #ccc;'></iframe>"
        )
    html.append("</div>")

    # Tables
    html.append("<h2>NPF7 Leaders</h2>")
    if team_filter_normalized:
        html.append(f"<h3>{team_filter} starters (NPF7)</h3>")
        html.append(_html_table(top_npf7, "NPF7", "anppm"))
    else:
        html.append("<h3>Top 10 NPF7</h3>")
        html.append(_html_table(top_npf7, "NPF7", "anppm"))
        html.append("<h3>Bottom 10 NPF7</h3>")
        html.append(_html_table(bottom_npf7, "NPF7", "anppm"))

    html.append("<h2>NPA7 Leaders</h2>")
    if team_filter_normalized:
        html.append(f"<h3>{team_filter} starters (NPA7)</h3>")
        html.append(_html_table(top_npa7, "NPA7", "npa7"))
    else:
        html.append("<h3>Top 10 NPA7</h3>")
        html.append(_html_table(top_npa7, "NPA7", "npa7"))
        html.append("<h3>Bottom 10 NPA7</h3>")
        html.append(_html_table(bottom_npa7, "NPA7", "npa7"))

    html.append("<h2>NPD7 Leaders</h2>")
    if team_filter_normalized:
        html.append(f"<h3>{team_filter} starters (NPD7)</h3>")
        html.append(_html_table_npd(top_npd7))
    else:
        html.append("<h3>Top 10 NPD7</h3>")
        html.append(_html_table_npd(top_npd7))
        html.append("<h3>Bottom 10 NPD7</h3>")
        html.append(_html_table_npd(bottom_npd7))

    html.append("</body></html>")

    output_path.write_text("\n".join(html), encoding="utf-8")


def print_results(
    season: int,
    max_rank: int,
    ranked_results: List[Dict],
    def_results: List[Dict],
    npd_results: List[Dict],
    def_debug_by_wrestler: Dict[str, List[Dict]],
    total_matches_used: int,
    excluded_invalid_matches: int,
    matches_using_weight_avg: int,
    avg_valid_matches: float,
    threshold: int,
    team_filter: Optional[str] = None,
) -> None:
    print(f"\nNPF7 — Season {season}, ranks 1–{max_rank}\n")

    if not ranked_results:
        print("No ranked wrestlers with valid ANPPM data.")
        return

    team_filter_normalized = team_filter.strip().lower() if team_filter else None

    def _filter_team(rows: List[Dict]) -> List[Dict]:
        if not team_filter_normalized:
            return rows
        return [r for r in rows if r.get("team", "").lower() == team_filter_normalized]

    ranked_view = _filter_team(ranked_results)
    def_view = _filter_team(def_results)
    npd_view = _filter_team(npd_results)

    if team_filter_normalized:
        label = team_filter
        # NPF7 for this team's starters
        print(f"{len(ranked_view)} starter(s) for {label} with NPF7 data:\n")
        if not ranked_view:
            print(f"(no starters for {label} in ranks 1–{max_rank} with valid NPF7)\n")
        else:
            for idx, r in enumerate(ranked_view, start=1):
                name = r["name"]
                team = r["team"]
                rank = r["rank"]
                anppm = r["anppm"]
                matches = r["matches"]
                print(
                    f"{idx}. #{rank:2d} {name} ({team}) - NPF7 {anppm:+.2f} "
                    f"({matches} valid matches)"
                )

        # NPA7 for this team's starters
        print(
            f"\n{len(def_view)} starter(s) for {label} with NPA7 data "
            "(higher = better defense vs opponent scoring baseline):\n"
        )
        if not def_view:
            print(f"(no starters for {label} in ranks 1–{max_rank} with valid NPA7)\n")
        else:
            for idx, r in enumerate(def_view, start=1):
                name = r["name"]
                team = r["team"]
                rank = r["rank"]
                npa7 = r["npa7"]
                matches = r["matches"]
                print(
                    f"{idx}. #{rank:2d} {name} ({team}) - NPA7 {npa7:+.2f} "
                    f"({matches} valid matches)"
                )

        # NPD7 for this team's starters
        print(
            f"\n{len(npd_view)} starter(s) for {label} with NPD7 data "
            "(NPF7 + NPA7 per 7 minutes):\n"
        )
        if not npd_view:
            print(f"(no starters for {label} in ranks 1–{max_rank} with valid NPD7)\n")
        else:
            for idx, r in enumerate(npd_view, start=1):
                name = r["name"]
                team = r["team"]
                rank = r["rank"]
                npd7 = r["npd7"]
                m_off = r["matches_off"]
                m_def = r["matches_def"]
                npf7 = next(
                    (
                        o["anppm"]
                        for o in ranked_results
                        if o["wrestler_id"] == r["wrestler_id"]
                    ),
                    None,
                )
                npa7 = next(
                    (
                        d["npa7"]
                        for d in def_results
                        if d["wrestler_id"] == r["wrestler_id"]
                    ),
                    None,
                )
                print(
                    f"{idx}. #{rank:2d} {name} ({team}) - NPD7 {npd7:+.2f} "
                    f"(NPF7={npf7:+.2f}, NPA7={npa7:+.2f}, off {m_off}, def {m_def} matches)"
                )

    else:
        # Top 10 by NPF7 (normalized points FOR per 7 minutes)
        print("Top 10 wrestlers by NPF7 (normalized points for per 7 minutes):\n")
        top10 = ranked_results[:10]
        for idx, r in enumerate(top10, start=1):
            name = r["name"]
            team = r["team"]
            rank = r["rank"]
            anppm = r["anppm"]  # still stored internally as 'anppm'
            matches = r["matches"]
            print(
                f"{idx}. #{rank:2d} {name} ({team}) - NPF7 {anppm:+.2f} "
                f"({matches} valid matches)"
            )

        # Bottom 10 by NPF7
        print(
            "\nBottom 10 wrestlers by NPF7 (normalized points for per 7 minutes):\n"
        )
        bottom10 = list(reversed(ranked_results))[:10]
        bottom10.reverse()  # show worst (most negative) first
        for idx, r in enumerate(bottom10, start=1):
            name = r["name"]
            team = r["team"]
            rank = r["rank"]
            anppm = r["anppm"]
            matches = r["matches"]
            print(
                f"{idx}. #{rank:2d} {name} ({team}) - NPF7 {anppm:+.2f} "
                f"({matches} valid matches)"
            )

        # Top 10 by normalized points against per 7 minutes (defensive side)
        print(
            "\nTop 10 wrestlers by normalized points against per 7 minutes "
            "(higher = better defense vs opponent scoring baseline):\n"
        )
        top_def = def_results[:10]
        for idx, r in enumerate(top_def, start=1):
            name = r["name"]
            team = r["team"]
            rank = r["rank"]
            npa7 = r["npa7"]
            matches = r["matches"]
            print(
                f"{idx}. #{rank:2d} {name} ({team}) - NPA7 {npa7:+.2f} "
                f"({matches} valid matches)"
            )

        # Bottom 10 by normalized points against (NPA7) — worst defenses.
        print(
            "\nBottom 10 wrestlers by normalized points against per 7 minutes "
            "(lower = weaker defense vs opponent scoring baseline):\n"
        )
        bottom_def = list(reversed(def_results))[:10]
        bottom_def.reverse()  # show worst (most negative NPA7) first
        for idx, r in enumerate(bottom_def, start=1):
            name = r["name"]
            team = r["team"]
            rank = r["rank"]
            npa7 = r["npa7"]
            matches = r["matches"]
            print(
                f"{idx}. #{rank:2d} {name} ({team}) - NPA7 {npa7:+.2f} "
                f"({matches} valid matches)"
            )

        # Top 10 by normalized point differential per 7 minutes (NPD7 = NPF7 + NPA7)
        print(
            "\nTop 10 wrestlers by NPD7 (normalized point differential per 7 minutes):\n"
        )
        top_npd = npd_results[:10]
        for idx, r in enumerate(top_npd, start=1):
            name = r["name"]
            team = r["team"]
            rank = r["rank"]
            npd7 = r["npd7"]
            m_off = r["matches_off"]
            m_def = r["matches_def"]
            npf7 = next(
                (
                    o["anppm"]
                    for o in ranked_results
                    if o["wrestler_id"] == r["wrestler_id"]
                ),
                None,
            )
            npa7 = next(
                (
                    d["npa7"]
                    for d in def_results
                    if d["wrestler_id"] == r["wrestler_id"]
                ),
                None,
            )
            print(
                f"{idx}. #{rank:2d} {name} ({team}) - NPD7 {npd7:+.2f} "
                f"(NPF7={npf7:+.2f}, NPA7={npa7:+.2f}, off {m_off}, def {m_def} matches)"
            )

        # Bottom 10 by NPD7
        print(
            "\nBottom 10 wrestlers by NPD7 (normalized point differential per 7 minutes):\n"
        )
        bottom_npd = list(reversed(npd_results))[:10]
        bottom_npd.reverse()  # show worst (most negative NPD7) first
        for idx, r in enumerate(bottom_npd, start=1):
            name = r["name"]
            team = r["team"]
            rank = r["rank"]
            npd7 = r["npd7"]
            m_off = r["matches_off"]
            m_def = r["matches_def"]
            npf7 = next(
                (
                    o["anppm"]
                    for o in ranked_results
                    if o["wrestler_id"] == r["wrestler_id"]
                ),
                None,
            )
            npa7 = next(
                (
                    d["npa7"]
                    for d in def_results
                    if d["wrestler_id"] == r["wrestler_id"]
                ),
                None,
            )
            print(
                f"{idx}. #{rank:2d} {name} ({team}) - NPD7 {npd7:+.2f} "
                f"(NPF7={npf7:+.2f}, NPA7={npa7:+.2f}, off {m_off}, def {m_def} matches)"
            )

    # NOTE: Detailed NPA7 defensive debug output has been disabled for now.
    # The implementation is preserved below for potential future use.
    #
    # DEBUG_DEF = False
    # if DEBUG_DEF and def_results:
    #     print(
    #         "\nDetailed normalized points-against breakdown for top 3 "
    #         "defensive leaders (worst NPA7):\n"
    #     )
    #     rank_by_id = _load_rank_map(season)
    #     for pos in range(min(3, len(def_results))):
    #         ...

    # Summary totals
    print("Summary:")
    print(f"  Avg valid matches per ranked wrestler: {avg_valid_matches:.2f}")
    print(f"  Stat-eligibility threshold (wrestlers/opponents): {threshold} matches")
    print(f"  Total matches included:             {total_matches_used}")
    print(f"  Matches excluded (invalid type):    {excluded_invalid_matches}")
    print(
        f"  Matches using weight-class PA7:     {matches_using_weight_avg}"
    )
    print()


def main() -> None:
    args = parse_args()
    season = args.season
    max_rank = args.maxrank
    team_filter_raw = args.team
    weight_filter = args.weight
    if args.wrestler:
        # In wrestler mode we skip the normalized scoring report entirely.
        _run_wrestler_mode(season, max_rank)
        return

    if args.quintiles:
        # Precompute metrics once for all wrestlers.
        metrics_by_id = _compute_plus_metrics_for_all(season, max_rank)
        weight_classes = ["125", "133", "141", "149", "157", "165", "174", "184", "197", "285"]
        print(
            f"{'Weight-Q':<10} {'Count':>6} "
            f"{'APS7_mean':>10} {'APS7_std':>9} "
            f"{'APG7_mean':>10} {'APG7_std':>9} "
            f"{'APD7_mean':>10} {'APD7_std':>9} "
            f"{'APR_mean':>10} {'APR_std':>9} "
            f"{'PF7_mean':>10} {'PA7_mean':>10}"
        )
        print("-" * 122)
        for wc in weight_classes:
            for q in range(1, 6):
                stats = get_quintile_metric_summary(
                    season, max_rank, wc, q, metrics_by_id=metrics_by_id
                )
                label = f"{wc}-Q{q}"
                if not stats:
                    print(f"{label:<10} {'0':>6}")
                    continue
                print(
                    f"{label:<10} {int(stats['count']):6d} "
                    f"{stats['APS7_mean']:10.3f} {stats['APS7_std']:9.3f} "
                    f"{stats['APG7_mean']:10.3f} {stats['APG7_std']:9.3f} "
                    f"{stats['APD7_mean']:10.3f} {stats['APD7_std']:9.3f} "
                    f"{stats['APR_mean']:10.3f} {stats['APR_std']:9.3f} "
                    f"{stats['PF7_mean']:10.3f} {stats['PA7_mean']:10.3f}"
                )
        print()
        return

    # If a weight filter is provided without -wrestler, print a DI+ top-10
    # table for that weight class instead of the global NPF7/NPA7/NPD7 report.
    if weight_filter:
        metrics_by_id = _compute_plus_metrics_for_all(season, max_rank)
        rankings_dir = Path("mt/rankings_data") / str(season)
        weight_str = str(weight_filter)
        rankings_path = rankings_dir / f"rankings_{weight_str}.json"
        if not rankings_path.exists():
            print(f"No rankings file found for weight {weight_str} at {rankings_path}")
            return
        try:
            with rankings_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Failed to read rankings file {rankings_path}: {e}")
            return

        rankings = data.get("rankings", [])
        # Filter to starters only and sort by weight-specific rank.
        starters = [
            r for r in rankings if r.get("is_starter", False) and r.get("rank") is not None
        ]
        starters.sort(key=lambda r: int(r["rank"]))
        top10 = starters[:200]
        if not top10:
            print(f"No starter rankings found for weight {weight_str}.")
            return

        print(f"DI+ Top 10 — Season {season}, weight {weight_str}")
        print()
        header = (
            f"{'Wrestler':<30} {'SI+':>7} {'DF+':>7} {'PE+':>7} "
            f"{'DI+':>7} {'APS7':>7} {'APG7':>7} {'APD7':>7} "
            f"{'Record':>10} {'Rank':>6}"
        )
        print(header)
        print("-" * len(header))

        for r in top10:
            wid = str(r.get("wrestler_id") or "")
            name = r.get("name", "Unknown")
            team = r.get("team", "Unknown")
            record = r.get("record", "")
            rank = int(r.get("rank", 0))
            label = f"{name} ({team})"
            m = metrics_by_id.get(wid)
            if not m:
                si = df = pe = apd = di = aps = apg = 0.0
            else:
                si = m["SI_plus"]
                df = m["DF_plus"]
                pe = m["PE_plus"]
                aps = m.get("APS7", 0.0)
                apg = m.get("APG7", 0.0)
                apd = m.get("APD7", 0.0)
                di = m["DI_raw"]
            print(
                f"{label:<30} {si:7.1f} {df:7.1f} {pe:7.1f} "
                f"{di:7.1f} {aps:7.2f} {apg:7.2f} {apd:7.2f} "
                f"{record:>10} {rank:6d}"
            )
        print()
        return

    (
        ranked_results,
        def_results,
        npd_results,
        def_debug_by_wrestler,
        total_used,
        excluded_invalid,
        used_weight_avg,
        avg_valid_matches,
        threshold,
    ) = compute_anppm(season, max_rank)

    # If a team filter was provided, attempt to resolve it to a canonical team
    # string present in the results. If there is no exact match, fall back to
    # substring search and let the user choose.
    def _resolve_team_filter(
        team_name: Optional[str],
        ranked: List[Dict],
        defensive: List[Dict],
        npd: List[Dict],
    ) -> Optional[str]:
        if not team_name:
            return None
        candidate = team_name.strip()
        if not candidate:
            return None
        candidate_lower = candidate.lower()

        teams_set = set()
        for rows in (ranked, defensive, npd):
            for r in rows:
                t = r.get("team")
                if t:
                    teams_set.add(t)

        if not teams_set:
            print("No team data available in results; ignoring -team filter.")
            return None

        # Exact (case-insensitive) match
        lower_to_team = {t.lower(): t for t in teams_set}
        if candidate_lower in lower_to_team:
            chosen = lower_to_team[candidate_lower]
            print(f"Using team '{chosen}' (exact match).")
            return chosen

        # Substring search (case-insensitive)
        partial_matches = sorted(
            [t for t in teams_set if candidate_lower in t.lower()]
        )
        if not partial_matches:
            print(
                f"No teams matched '{team_name}'. "
                "Run without -team or try a different name."
            )
            return None
        if len(partial_matches) == 1:
            chosen = partial_matches[0]
            print(f"Using team '{chosen}' (partial match).")
            return chosen

        # Multiple candidates: let the user choose.
        print(f"Multiple teams matched '{team_name}':")
        for idx, t in enumerate(partial_matches, start=1):
            print(f"  {idx}. {t}")
        while True:
            choice = input(
                f"Enter a number from 1 to {len(partial_matches)} "
                "to select a team (or press Enter to cancel team filter): "
            ).strip()
            if choice == "":
                print("No team selected; running global report.")
                return None
            if not choice.isdigit():
                print("Please enter a valid number or press Enter to cancel.")
                continue
            num = int(choice)
            if 1 <= num <= len(partial_matches):
                chosen = partial_matches[num - 1]
                print(f"Using team '{chosen}'.")
                return chosen
            print("Number out of range; try again.")

    team_filter = _resolve_team_filter(
        team_filter_raw, ranked_results, def_results, npd_results
    )

    print_results(
        season,
        max_rank,
        ranked_results,
        def_results,
        npd_results,
        def_debug_by_wrestler,
        total_used,
        excluded_invalid,
        used_weight_avg,
        avg_valid_matches,
        threshold,
        team_filter,
    )

    # Also write HTML report with tables and histograms.
    if team_filter:
        safe_team = re.sub(r"[^a-z0-9]+", "_", team_filter.strip().lower()).strip("_")
        html_output = (
            Path("mt/graphics")
            / str(season)
            / f"npf7_npa7_npd7_rank1-{max_rank}_team-{safe_team}.html"
        )
    else:
        html_output = (
            Path("mt/graphics")
            / str(season)
            / f"npf7_npa7_npd7_rank1-{max_rank}.html"
        )
    write_html_report(
        season,
        max_rank,
        ranked_results,
        def_results,
        npd_results,
        html_output,
        team_filter,
    )
    print(f"HTML report written to: {html_output}")


if __name__ == "__main__":
    main()


