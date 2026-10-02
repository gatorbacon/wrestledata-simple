#!/usr/bin/env python3
"""
Compute the "Freshman of the Year Watch" report for a season (read by freshman.html / freshman.js).

Same sources and stat code as hodge_candidates.py (this script imports them):
  - Candidate pool: `mt/elo_ratings/ncaa_men/{season}/elo_ratings.json` `hybrid_rank_by_weight` <= --top-n
    (default 10) at a weight -- the site's rank of record (docs/matsavant.md "NCAA Ranking Methodology
    (Source of Truth)"), NOT the banned matrix rank in `mt/rankings_data/`.
  - Per-wrestler stats: the published profile `frontend/wrestledata-ui/public/data/wrestlers/{season}/by_id/{id}.json`
    `match_list` (W/L, method, opponent_rank): win %, bonus % (F/TF/MD/INJ/MFF wins), pin %, ranked wins
    (opponent rank <= 33), top-10 wins, ranked bonus %.
  - Grade: the profile's `grade` (official-roster text, many spellings -- see is_freshman()), then grade overrides
    from `mt/rankings_data/grade_overrides.json` (legacy location, where the existing overrides live) and
    `mt/rankings_data/ncaa_men/grade_overrides.json` (where manage_grade_overrides.py writes now); the second wins.
    True and redshirt freshmen count (incl. Ivy "first-year").
  - DPG: the profile's `metrics.mat_value.mv_avg` -- the same season DPG the rankings page and profile show.
    Shown on the page for reference only; it is not part of FreshScore.

FreshScore (unchanged): 20% each win %, bonus %, pin %, ranked bonus % (0-100), plus 10% each ranked wins and
top-10 wins scaled to the best freshman's count.

Rebuilt 2026-10-02: this used to read `mt/rankings_data/{season}/rankings_{weight}.json` + `weight_class_*.json`
-- the same banned matrix-rank source the Hodge Watch was moved off on 2026-09-11, and that folder stopped
updating on 12/22/2025, so the page showed December records (Blaze 10-0 instead of 25-3). Its grade check
also only knew 'Fr.'/'RS Fr.', missing 'Freshman', 'R-Fr.', 'Redshirt Freshman', etc.

Run after calculate_elo_ratings.py + build_wrestler_profiles.py for the season (same place as hodge_candidates.py):
  .venv/bin/python scripts/rankings/freshman_of_year.py -season 2026
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hodge_candidates import (  # noqa: E402
    NCAA_WEIGHTS,
    build_candidate_pool,
    compute_stats_for_candidate,
    load_elo_ratings,
    load_profile,
)

FRESHMAN_KEYS = {"fr", "freshman", "fy", "firstyear", "rfr", "rsfr", "redshirtfreshman", "redshirtfirstyear"}
OVERRIDE_FILES = ["mt/rankings_data/grade_overrides.json", "mt/rankings_data/ncaa_men/grade_overrides.json"]


def is_freshman(grade: str) -> bool:
    """'Fr.', 'Freshman', 'FRESHMAN', 'R-Fr.', 'RS Fr.', 'RFr.', 'Redshirt Freshman', 'Fy.', 'First-Year', ..."""
    return re.sub(r"[^a-z]", "", (grade or "").lower()) in FRESHMAN_KEYS


def load_grade_overrides() -> Dict[str, str]:
    out: Dict[str, str] = {}
    for p in OVERRIDE_FILES:
        path = Path(p)
        if path.exists():
            for o in json.loads(path.read_text(encoding="utf-8")).get("overrides", []):
                if o.get("wrestler_id") and o.get("grade"):
                    out[o["wrestler_id"]] = o["grade"]
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Freshman of the Year Watch for top-ranked freshmen per weight.")
    parser.add_argument("-season", type=int, required=True, help="Season year (e.g., 2026)")
    parser.add_argument("-data-dir", default="frontend/wrestledata-ui/public/data/wrestlers",
                        help="Directory containing {season}/by_id/{wrestler_id}.json wrestler profiles")
    parser.add_argument("-elo-path", default=None,
                        help="Path to elo_ratings.json (default: mt/elo_ratings/ncaa_men/{season}/elo_ratings.json)")
    parser.add_argument("-output-dir", default="frontend/wrestledata-ui/public/data/awards/freshman",
                        help="Directory to save the JSON report (subdir per season will be created)")
    parser.add_argument("-top-n", type=int, default=10,
                        help="Number of ranked wrestlers per weight class to consider (default: 10)")
    args = parser.parse_args()
    season = args.season

    pool = build_candidate_pool(load_elo_ratings(season, args.elo_path), args.top_n)
    overrides = load_grade_overrides()

    cands: List[dict] = []
    missing: List[str] = []
    for weight in NCAA_WEIGHTS:
        for entry in pool.get(weight, []):
            profile = load_profile(season, entry["wrestler_id"], args.data_dir)
            if profile is None:
                missing.append(f"{entry['name']} ({weight}, id {entry['wrestler_id']})")
                continue
            grade = overrides.get(entry["wrestler_id"], profile.get("grade") or "")
            if not is_freshman(grade):
                continue
            s = compute_stats_for_candidate(entry, weight, profile)
            if s.total_matches == 0:
                continue
            mv = (profile.get("metrics") or {}).get("mat_value") or {}
            cands.append({"s": s, "grade": grade, "dpg": mv.get("mv_avg"),
                          "team_slug": profile.get("team_slug"), "photo_url": profile.get("photo_url") or None})
    if missing:
        print(f"Warning: {len(missing)} candidate(s) had no profile file, skipped: " + "; ".join(missing))

    max_rw = max((c["s"].ranked_wins for c in cands), default=0)
    max_t10 = max((c["s"].top10_wins for c in cands), default=0)
    for c in cands:
        s = c["s"]
        c["score"] = (
            s.win_pct * 100 * 0.20 + s.bonus_pct * 100 * 0.20 + s.fall_pct * 100 * 0.20
            + s.ranked_bonus_pct * 100 * 0.20
            + (s.ranked_wins / max_rw * 100 if max_rw else 0) * 0.10
            + (s.top10_wins / max_t10 * 100 if max_t10 else 0) * 0.10
        )
    cands.sort(key=lambda c: -c["score"])

    print(f"\nFreshman of the Year Watch {season} (top {args.top_n} per weight, sorted by FreshScore):\n")
    print(f"{'#':>3}  {'Name':<24} {'Team':<18} {'Wt':>4} {'Rk':>3} {'W-L':>6} {'DPG':>6} {'Fresh':>6}")
    rows = []
    for i, c in enumerate(cands, start=1):
        s = c["s"]
        dpg = round(c["dpg"], 2) if c["dpg"] is not None else None
        print(f"{i:>3}  {s.name:<24.24} {s.team:<18.18} {s.weight_class:>4} {s.weight_rank:>3} "
              f"{s.wins}-{s.losses:<3} {dpg if dpg is not None else '-':>6} {c['score']:6.2f}")
        rows.append({
            "rank": i,
            "wrestler_id": s.wrestler_id,
            "name": s.name,
            "team": s.team,
            "team_slug": c["team_slug"],
            "photo_url": c["photo_url"],
            "weight": int(s.weight_class),
            "weight_rank": s.weight_rank,
            "grade": c["grade"],
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
                "dpg": dpg,
            },
            "fresh_score": round(c["score"], 2),
        })

    out_dir = Path(args.output_dir) / str(season)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"freshman_{season}.json"
    json_path.write_text(json.dumps({
        "season": season,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "description": (
            f"True and redshirt freshmen ranked in the top {args.top_n} at their weight. "
            "Ranked wins are wins over top-33 opponents."
        ),
        "rows": rows,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nJSON report written to {json_path}\n")


if __name__ == "__main__":
    main()
