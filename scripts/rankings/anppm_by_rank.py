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
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np

from load_data import load_team_data
from scoringbyrank import _parse_score_from_result


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
        return [], [], [], {}, 0, 0, 0.0, 0

    starter_rank_by_id: Dict[str, int] = {}
    for path in sorted(rankings_dir.glob("rankings_*.json")):
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
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
        for new_rank, (_, r) in enumerate(starters, start=1):
            wid = str(r.get("wrestler_id") or "")
            if not wid:
                continue
            # Keep the best (lowest) starter-only rank across any appearances.
            if wid not in starter_rank_by_id or new_rank < starter_rank_by_id[wid]:
                starter_rank_by_id[wid] = new_rank

    if not starter_rank_by_id:
        return [], [], [], {}, 0, 0, 0.0, 0

    # Keep only starters within the requested rank cutoff.
    rank_by_id = {wid: r for wid, r in starter_rank_by_id.items() if r <= max_rank}
    if not rank_by_id:
        return [], [], [], {}, 0, 0, 0.0, 0

    (
        wrestlers,
        matches_by_wrestler,
        pa7_sum_by_wrestler,
        pa7_count_by_wrestler,
        pa7_sum_by_weight,
        pa7_count_by_weight,
        excluded_invalid_matches,
    ) = build_all_matches(season, rank_by_id)

    if not matches_by_wrestler:
        return [], {}, 0, excluded_invalid_matches, 0

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

    # Average valid match count for top-R ranked wrestlers.
    top_counts = [valid_match_counts.get(wid, 0) for wid in rank_by_id.keys()]
    if not top_counts:
        return [], [], {}, 0, excluded_invalid_matches, 0, 0.0, 0

    avg_valid_matches = sum(top_counts) / float(len(top_counts))

    # Threshold used for:
    #   - Including wrestlers in ANPF7 / ANPA7 lists.
    #   - Deciding when to trust a wrestler's own PA7 baseline.
    # Spec: floor(50% of avg valid matches) with a floor of 2.
    threshold = max(2, int(math.floor(0.5 * avg_valid_matches)))

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
) -> None:
    """
    Create a joint distribution plot:
      - Center: scatter of (NPF7, NPA7), colored by global rank quartile.
      - Top:   histogram of NPF7.
      - Right: histogram of NPA7.
    """
    if not npd_results:
        return

    xs = []
    ys = []
    ranks = []
    for row in npd_results:
        wid = row["wrestler_id"]
        if wid not in npf7_by_id or wid not in npa7_by_id:
            continue
        xs.append(float(npf7_by_id[wid]))
        ys.append(float(npa7_by_id[wid]))
        ranks.append(int(row.get("rank", max_rank)))

    if not xs:
        return

    xs = np.array(xs)
    ys = np.array(ys)
    ranks = np.array(ranks)

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
    labels = ["Top 25%", "25–50%", "50–75%", "Bottom 25%"]

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Layout: 2x2 grid (top histogram, right histogram, center scatter)
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

    # Main scatter
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
            label=labels[q],
        )

    ax_main.set_xlabel("NPF7 (normalized points for per 7)")
    ax_main.set_ylabel("NPA7 (normalized points against per 7)")
    ax_main.legend(loc="best", fontsize=8)

    # Top histogram (NPF7)
    ax_top.hist(xs, bins=20, color="#4c72b0", edgecolor="black")
    ax_top.set_ylabel("Count")
    ax_top.tick_params(labelbottom=False)  # hide x labels

    # Right histogram (NPA7)
    ax_right.hist(ys, bins=20, orientation="horizontal", color="#4c72b0", edgecolor="black")
    ax_right.set_xlabel("Count")
    ax_right.tick_params(labelleft=False)  # hide y labels

    # Align limits
    ax_top.set_xlim(ax_main.get_xlim())
    ax_right.set_ylim(ax_main.get_ylim())

    fig.suptitle("NPF7 vs NPA7 Joint Distribution", y=0.96)
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
) -> None:
    """
    Write an HTML report containing tables for NPF7, NPA7, NPD7
    and histograms for each (bucketed by nearest integer).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build histograms (quartiles based on GLOBAL rank up to max_rank)
    buckets_npf7, qcounts_npf7 = _build_histogram_quartiles(
        ranked_results, "anppm", max_rank
    )
    buckets_npa7, qcounts_npa7 = _build_histogram_quartiles(
        def_results, "npa7", max_rank
    )
    buckets_npd7, qcounts_npd7 = _build_histogram_quartiles(
        npd_results, "npd7", max_rank
    )

    graphics_dir = Path("mt/graphics") / str(season)
    hist_npf7_path = graphics_dir / f"npf7_hist_rank1-{max_rank}.png"
    hist_npa7_path = graphics_dir / f"npa7_hist_rank1-{max_rank}.png"
    hist_npd7_path = graphics_dir / f"npd7_hist_rank1-{max_rank}.png"
    joint_path = graphics_dir / f"npf7_vs_npa7_joint_rank1-{max_rank}.png"

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
    )

    def _rows_for_top_bottom(
        results: List[Dict], metric_key: str
    ) -> Tuple[List[Dict], List[Dict]]:
        top = results[:10]
        bottom = list(reversed(results))[:10]
        bottom.reverse()
        return top, bottom

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
    html.append(f"<title>NPF7/NPA7/NPD7 Report — Season {season}</title>")
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
    html.append(f"<h1>NPF7 / NPA7 / NPD7 — Season {season}, ranks 1–{max_rank}</h1>")

    # Histograms
    html.append("<div class='hist'>")
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
            f"<h2>NPF7 vs NPA7 Joint Distribution</h2>"
            f"<img src='{joint_path.name}' alt='NPF7 vs NPA7 joint plot' />"
        )
    html.append("</div>")

    # Tables
    html.append("<h2>NPF7 Leaders</h2>")
    html.append("<h3>Top 10 NPF7</h3>")
    html.append(_html_table(top_npf7, "NPF7", "anppm"))
    html.append("<h3>Bottom 10 NPF7</h3>")
    html.append(_html_table(bottom_npf7, "NPF7", "anppm"))

    html.append("<h2>NPA7 Leaders</h2>")
    html.append("<h3>Top 10 NPA7</h3>")
    html.append(_html_table(top_npa7, "NPA7", "npa7"))
    html.append("<h3>Bottom 10 NPA7</h3>")
    html.append(_html_table(bottom_npa7, "NPA7", "npa7"))

    html.append("<h2>NPD7 Leaders</h2>")
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
) -> None:
    print(f"\nNPF7 — Season {season}, ranks 1–{max_rank}\n")

    if not ranked_results:
        print("No ranked wrestlers with valid ANPPM data.")
        return

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
    print("\nBottom 10 wrestlers by NPF7 (normalized points for per 7 minutes):\n")
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
        npf7 = next((o["anppm"] for o in ranked_results if o["wrestler_id"] == r["wrestler_id"]), None)
        npa7 = next((d["npa7"] for d in def_results if d["wrestler_id"] == r["wrestler_id"]), None)
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
        npf7 = next((o["anppm"] for o in ranked_results if o["wrestler_id"] == r["wrestler_id"]), None)
        npa7 = next((d["npa7"] for d in def_results if d["wrestler_id"] == r["wrestler_id"]), None)
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
    )

    # Also write HTML report with tables and histograms.
    html_output = Path("mt/graphics") / str(season) / f"npf7_npa7_npd7_rank1-{max_rank}.html"
    write_html_report(
        season,
        max_rank,
        ranked_results,
        def_results,
        npd_results,
        html_output,
    )
    print(f"HTML report written to: {html_output}")


if __name__ == "__main__":
    main()


