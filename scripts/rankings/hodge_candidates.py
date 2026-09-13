#!/usr/bin/env python3
"""
Compute Hodge Trophy front-runner metrics for a season.

Data sources (season 2026+ / current-methodology seasons):
  - `mt/elo_ratings/ncaa_men/{season}/elo_ratings.json` -- built by
    `calculate_elo_ratings.py`. Used only to build the candidate pool: for
    each weight class, whichever wrestlers have a `hybrid_rank_by_weight`
    entry <= --top-n for that weight. This is the same `hybrid_rank` value
    that's the site's documented rank source of truth (see docs/matsavant.md
    "NCAA Ranking Methodology (Source of Truth)") -- NOT the internal
    "matrix rank" (`mt/rankings_data/{season}/rankings_{weight}.json`),
    which that doc explicitly bans from ever feeding a public JSON file.
  - `frontend/wrestledata-ui/public/data/wrestlers/{season}/by_id/{id}.json`
    -- one already-published wrestler profile per candidate. `match_list`
    gives per-match result ("W"/"L"), method (FALL/TF/MD/DEC/...), and the
    opponent's already-resolved rank at that weight -- everything needed
    for win/bonus/fall rates and quality-of-competition scoring, straight
    from the same file wrestler.html itself reads (i.e. always as current
    as the last `build_wrestler_profiles.py` run for that season).

This script previously read `mt/rankings_data/{season}/rankings_{weight}.json`
+ `weight_class_{weight}.json`. That data stopped being regenerated
mid-season (an earlier, now-abandoned rankings pipeline run) and was also
the banned matrix-rank source -- so `hodge_{season}.json` was both stale
and, independent of staleness, reading from the wrong place. Fixed
2026-09-11; see docs/matsavant.md's Hodge section for the incident and the
"why the old source was wrong" detail. Also added to the documented weekly
pipeline at that point (root CLAUDE.md) -- it previously wasn't part of it.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


NCAA_WEIGHTS = ["125", "133", "141", "149", "157", "165", "174", "184", "197", "285"]

BONUS_CODES = {"F", "TF", "MD", "INJ", "MFF"}
FALL_CODES = {"F"}
TEAM_POINTS = {"D": 3, "MD": 4, "TF": 5, "F": 6}

# `match_list[].method` is already a clean structured code (unlike the old
# free-text `result` string this script used to regex-parse) -- just a
# lookup, no text classification needed.
METHOD_TO_CODE = {
    "FALL": "F",
    "TF": "TF",
    "MD": "MD",
    "INJ": "INJ",
    "MFF": "MFF",
    "DEC": "D",
    "SV-1": "D",
    "SV-2": "D",
    "SV-3": "D",
    "TB-1": "D",
    "TB-2": "D",
    "DFLT": "O",
    "DQ": "O",
}


def classify_method(method: Optional[str]) -> str:
    if not method:
        return "O"
    return METHOD_TO_CODE.get(method.upper(), "O")


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


def load_elo_ratings(season: int, elo_path: Optional[str]) -> List[Dict]:
    path = Path(elo_path) if elo_path else Path(f"mt/elo_ratings/ncaa_men/{season}/elo_ratings.json")
    if not path.exists():
        raise FileNotFoundError(
            f"elo_ratings.json not found at {path} -- run calculate_elo_ratings.py "
            f"-season {season} --league ncaa --gender men first."
        )
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_candidate_pool(elo_entries: List[Dict], top_n: int) -> Dict[str, List[Dict]]:
    """
    weight -> candidates with a hybrid_rank_by_weight entry <= top_n for
    that weight, sorted by rank ascending. A wrestler who moved weights
    mid-season can be a candidate at more than one weight.
    """
    pool: Dict[str, List[Dict]] = {w: [] for w in NCAA_WEIGHTS}
    for e in elo_entries:
        hrbw = e.get("hybrid_rank_by_weight") or {}
        for weight, rank in hrbw.items():
            if weight not in pool or rank is None:
                continue
            try:
                r = int(rank)
            except (TypeError, ValueError):
                continue
            if r > top_n:
                continue
            pool[weight].append(
                {
                    "wrestler_id": e.get("wrestler_id"),
                    "rank": r,
                    "name": e.get("name") or f"ID:{e.get('wrestler_id')}",
                    "team": e.get("team") or "Unknown",
                }
            )
    for w in pool:
        pool[w].sort(key=lambda c: c["rank"])
    return pool


def load_profile(season: int, wrestler_id: str, profiles_dir: str) -> Optional[Dict]:
    path = Path(profiles_dir) / str(season) / "by_id" / f"{wrestler_id}.json"
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def compute_stats_for_candidate(entry: Dict, weight: str, profile: Dict) -> HodgeStats:
    s = HodgeStats(
        wrestler_id=entry["wrestler_id"],
        name=entry["name"],
        team=entry["team"],
        weight_class=weight,
        weight_rank=entry["rank"],
    )

    for m in profile.get("match_list") or []:
        result = m.get("result")
        if result not in ("W", "L"):
            continue
        if result == "L":
            s.losses += 1
            continue

        s.wins += 1
        code = classify_method(m.get("method"))
        opp_rank = m.get("opponent_rank")

        if code in BONUS_CODES:
            s.bonus_wins += 1
        if code in FALL_CODES:
            s.fall_wins += 1
        if code == "F":
            s.pins += 1
        elif code == "TF":
            s.techs += 1
        elif code == "MD":
            s.majors += 1
        elif code == "D":
            s.decisions += 1

        tp = TEAM_POINTS.get(code, 0)
        if tp > 0:
            if opp_rank is not None and 1 <= opp_rank <= 50:
                w = 1.0 + (50.0 - float(opp_rank)) / 49.0
            else:
                w = 0.50
            s.dom_weighted_tp_num += tp * w
            s.dom_weighted_tp_den += w
            if opp_rank is None or opp_rank > 50:
                s.dom_unranked_tp_sum += tp
                s.dom_unranked_matches += 1

        if opp_rank is not None:
            if opp_rank <= 33:
                s.ranked_wins += 1
                if code in BONUS_CODES:
                    s.ranked_bonus_wins += 1
                if opp_rank <= 10:
                    s.top10_wins += 1
                if opp_rank <= 25:
                    s.ranked_win_ranks.append(opp_rank)

    return s


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compute Hodge Trophy front-runner metrics for top-ranked wrestlers "
            "in each weight class."
        )
    )
    parser.add_argument("-season", type=int, required=True, help="Season year (e.g., 2026)")
    parser.add_argument(
        "-data-dir",
        default="frontend/wrestledata-ui/public/data/wrestlers",
        help="Directory containing {season}/by_id/{wrestler_id}.json wrestler profiles",
    )
    parser.add_argument(
        "-elo-path",
        default=None,
        help="Path to elo_ratings.json (default: mt/elo_ratings/ncaa_men/{season}/elo_ratings.json)",
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
        help="Unused by the current eligibility gate (kept for CLI compatibility).",
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
    profiles_dir = args.data_dir
    output_root = Path(args.output_dir)

    elo_entries = load_elo_ratings(season, args.elo_path)
    pool = build_candidate_pool(elo_entries, args.top_n)

    all_candidates: List[HodgeStats] = []
    missing_profiles: List[str] = []

    for weight in NCAA_WEIGHTS:
        for entry in pool.get(weight, []):
            profile = load_profile(season, entry["wrestler_id"], profiles_dir)
            if profile is None:
                missing_profiles.append(f"{entry['name']} ({weight}, id {entry['wrestler_id']})")
                continue
            all_candidates.append(compute_stats_for_candidate(entry, weight, profile))

    if missing_profiles:
        print(f"Warning: {len(missing_profiles)} candidate(s) had no profile file, skipped:")
        for m in missing_profiles:
            print(f"  - {m}")

    filtered_candidates: List[HodgeStats] = [
        s for s in all_candidates if s.total_matches >= args.minmatch
    ]

    # --- Compute numeric Hodge scores (unchanged formula) ---

    def compute_s_rec(wins: int, losses: int) -> tuple[float, dict]:
        total = wins + losses
        raw = {"wins": wins, "losses": losses, "win_pct": wins / total if total > 0 else 0.0}
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
        raw = {"ranked_wins": ranked_wins, "top10_wins": top10_wins, "raw_quality": 0.0}
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
        raw = {"avg_team_points": 0.0}
        if weighted_tp_den <= 0.0:
            return (0.0, raw)
        avg_tp_weighted = weighted_tp_num / weighted_tp_den
        raw["avg_team_points"] = avg_tp_weighted
        if avg_tp_weighted <= 3.0:
            return (0.0, raw)
        s_dom = min(100.0, (avg_tp_weighted - 3.0) / 3.0 * 100.0)
        if unranked_matches > 0:
            avg_tp_unranked = unranked_tp_sum / float(unranked_matches)
            if avg_tp_unranked < 3.2:
                penalty = min(10.0, (3.2 - avg_tp_unranked) * 10.0)
                s_dom = max(0.0, s_dom - penalty)
        return (s_dom, raw)

    def compute_s_pins(pins: int, wins: int) -> tuple[float, dict]:
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
        if s.weight_rank > 3:
            return (False, f"Weight class rank {s.weight_rank} > 3")
        if s.total_matches < 5:
            return (False, f"Matches {s.total_matches} < 5")
        win_pct = s.win_pct if s.total_matches > 0 else 0.0
        if s.losses > 1 and win_pct < 0.90:
            return (False, f"Has {s.losses} loss(es) and win% {win_pct:.1%} < 90%")
        if s.ranked_wins < 1 and s_qual < 20.0:
            return (False, f"Ranked wins {s.ranked_wins} < 1 and quality score {s_qual:.1f} < 20")
        return (True, None)

    W_REC = 0.30
    W_QUAL = 0.30
    W_DOM = 0.25
    W_PINS = 0.15

    for s in filtered_candidates:
        s_rec_score, rec_raw = compute_s_rec(s.wins, s.losses)
        s_qual_score, qual_raw = compute_s_qual(s.ranked_win_ranks, s.ranked_wins, s.top10_wins)
        s_dom_score, dom_raw = compute_s_dom(
            s.dom_weighted_tp_num, s.dom_weighted_tp_den, s.dom_unranked_tp_sum, s.dom_unranked_matches
        )
        s_pins_score, pins_raw = compute_s_pins(s.pins, s.wins)

        s.component_data = {
            "record": {"raw": rec_raw, "score": s_rec_score, "weight": W_REC, "contribution": W_REC * s_rec_score},
            "quality": {"raw": qual_raw, "score": s_qual_score, "weight": W_QUAL, "contribution": W_QUAL * s_qual_score},
            "dominance": {"raw": dom_raw, "score": s_dom_score, "weight": W_DOM, "contribution": W_DOM * s_dom_score},
            "pins": {"raw": pins_raw, "score": s_pins_score, "weight": W_PINS, "contribution": W_PINS * s_pins_score},
        }

        s.hodge_score = (
            W_REC * s_rec_score + W_QUAL * s_qual_score + W_DOM * s_dom_score + W_PINS * s_pins_score
        )
        s.eligible, s.eligibility_reason = check_eligibility(s, s_qual_score)

    scored_candidates = sorted(filtered_candidates, key=lambda s: (-s.eligible, -s.hodge_score))

    print(
        f"\nHodge Trophy candidate metrics for season {season} "
        f"(top {args.top_n} per weight, min matches={args.minmatch}, sorted by HodgeScore):\n"
    )
    header = (
        f"{'#':>3}  {'Name':<25} {'Team':<20} {'Wt':>4}  "
        f"{'W-L':>7}  {'Score':>7}  {'Elig':>5}  {'Win%':>6}  {'Bonus%':>7}  {'Fall%':>6}"
    )
    print(header)
    print("-" * len(header))
    for idx, s in enumerate(scored_candidates, start=1):
        wl = f"{s.wins}-{s.losses}"
        print(
            f"{idx:>3}  {s.name:<25.25} {s.team:<20.20} {s.weight_class:>4}  "
            f"{wl:>7}  {s.hodge_score:7.2f}  {str(s.eligible):>5}  "
            f"{s.win_pct:6.3f}  {s.bonus_pct:7.3f}  {s.fall_pct:6.3f}"
        )

    # --- Generate JSON report ---
    season_dir = output_root / str(season)
    season_dir.mkdir(parents=True, exist_ok=True)
    json_path = season_dir / f"hodge_{season}.json"

    generated_at = datetime.now(timezone.utc).isoformat()

    rows = []
    for idx, s in enumerate(scored_candidates, start=1):
        rows.append(
            {
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
                        "raw": {"avg_team_points": round(s.component_data["dominance"]["raw"]["avg_team_points"], 2)},
                        "score": round(s.component_data["dominance"]["score"], 1),
                        "weight": s.component_data["dominance"]["weight"],
                        "contribution": round(s.component_data["dominance"]["contribution"], 2),
                    },
                    "pins": {
                        "raw": {"pin_pct": round(s.component_data["pins"]["raw"]["pin_pct"], 3)},
                        "score": round(s.component_data["pins"]["score"], 1),
                        "weight": s.component_data["pins"]["weight"],
                        "contribution": round(s.component_data["pins"]["contribution"], 2),
                    },
                },
            }
        )

    json_data = {
        "season": season,
        "generated_at": generated_at,
        "description": (
            "Hodge Score evaluates performance only. "
            "Eligibility determines who appears on the Hodge Watch. "
            "Weight-class rank influences eligibility — not scoring."
        ),
        "rows": rows,
    }

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)

    print(f"\nJSON report written to {json_path}\n")


if __name__ == "__main__":
    main()
