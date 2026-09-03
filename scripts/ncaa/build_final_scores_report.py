#!/usr/bin/env python3
"""
Build the data behind the "Every Final Score" page (final_scores.html) --
a heatmap of every winner/loser final-score combination per NCAA D1 men's
season, plus a "how many points does it take to win" breakdown.

Parses the free-text match "summary" strings in mt/data/ncaa_men/{season}/*.json
(e.g. "Varsity - Winner Name (Winner Team) over Loser Name (Loser Team) (Dec 7-3)").

This logic was hand-validated against real data during development, reconciling
almost exactly against known-correct totals (unique combos, top score combos,
averages) for multiple seasons. It intentionally does NOT reuse
scripts/process_raw_matches_by_season.py's parse_name_team()/process_match() --
those solve a different problem (opponent-identity resolution) and don't need
touching here. A handful of non-obvious rules below look like they could be
"simplified" or "fixed" -- they can't; each one was found by reconciling
against a known-correct total and getting the wrong answer without it:

  - Nested parens in team names (e.g. "Pacific (OR)") break a naive
    \\(([^)]+)\\) regex split -- split_trailing_paren() scans for the
    matching '(' by paren depth instead.
  - TB-2/TB-3 sometimes carry a "(RT)" (riding time) annotation between the
    code and the score, e.g. "TB-2 (RT) 3-2" -- CODE_SCORE_RE skips an
    optional parenthetical there.
  - "X received a bye" and unresolved "X vs. Y" (no result recorded) are
    excluded from total_decided_matches entirely -- they are not decided
    matches with an unparsed result, they are not decided matches at all.
  - "... over Unknown (CODE)" -- opponent identity lost in the source data --
    always buckets as "other", regardless of what CODE follows, since the
    result can't be attributed to a real opponent. This reconciled the
    "other" bucket to a known-correct value exactly.
  - The two numbers in a score are already listed in winner-then-loser
    order. Do NOT reorder them by magnitude (no max()/min()). An
    overtime/tiebreak score can legitimately show the winner with the LOWER
    number (decided by riding time/criteria) -- forcing max/min silently
    corrupts ~1% of the grid.
  - unique_combos counts distinct EXACT (uncapped) scores seen, not distinct
    populated cells in the capped 25/15 grid (capping merges some distinct
    raw scores into the same cell).

Usage:
  python scripts/ncaa/build_final_scores_report.py                  # rebuild every season
  python scripts/ncaa/build_final_scores_report.py -season 2026     # rebuild just one
"""
import argparse
import collections
import glob
import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "mt" / "data" / "ncaa_men"
DEFAULT_OUT_DIR = PROJECT_ROOT / "frontend" / "wrestledata-ui" / "public" / "data" / "final_scores"

WIN_CAP = 25
LOSE_CAP = 15
PTS_CAP = 17

# Longest/most-specific first so alternation doesn't stop early (e.g. "M."
# must not swallow inside "MD"; "SV-1"/"TB-1" must be tried before a bare
# letter class would eat only "SV-"/"TB-" and strand the digit).
KNOWN_CODES = [
    "Min-TF", "SV-1", "SV-2", "SV-3", "TB-1", "TB-2", "TB-3",
    "MD", "TF", "Dec", "Fall", "Inj.", "M.", "NC", "For.", "Def.", "DQ",
]
CODE_SCORE_RE = re.compile(
    r'^(' + "|".join(re.escape(c) for c in KNOWN_CODES) + r')(?:\s*\([^)]*\))?(?:\s+(\d+)\s*-\s*(\d+))?'
)

GRID_CODES = {"Dec", "MD", "TF", "SV-1", "SV-2", "SV-3", "TB-1", "TB-2", "TB-3", "Min-TF"}
NO_SCORE_LABELS = {"Fall", "M.", "Inj.", "NC", "For.", "Def.", "DQ"}


def split_trailing_paren(s):
    """s ends with ')' -- return (prefix, inner) splitting on the matching
    '(' found by scanning backward with paren-depth counting, so a team name
    that itself contains parens (e.g. "Pacific (OR)") doesn't break the split
    of the outer "(Team)" or "(CODE)" group around it."""
    s = s.rstrip()
    if not s.endswith(")"):
        return None
    depth = 0
    for i in range(len(s) - 1, -1, -1):
        if s[i] == ")":
            depth += 1
        elif s[i] == "(":
            depth -= 1
            if depth == 0:
                return s[:i].rstrip(), s[i + 1:-1]
    return None


def get_code_score(summary):
    """A decided match's summary always ends in '(CODE [score])' as its
    outermost trailing paren group."""
    split = split_trailing_paren(summary)
    return split[1] if split else None


def season_label(season: str) -> str:
    y = int(season)
    return f"{y - 1}–{str(y)[2:]}"


def team_count(season: str) -> int:
    return len(glob.glob(str(DATA_DIR / season / "*.json")))


def available_seasons():
    return sorted((p.name for p in DATA_DIR.iterdir() if p.is_dir()), reverse=True)


def compute_season_stats(season: str) -> dict:
    seen = set()
    grid = [[0] * (WIN_CAP + 1) for _ in range(LOSE_CAP + 1)]
    stoppage = collections.Counter()
    total_decided = 0
    total_scored = 0
    top_combo_counter = collections.Counter()
    unique_raw_combos = set()
    points_wins = [0] * (PTS_CAP + 1)
    points_losses = [0] * (PTS_CAP + 1)

    winner_pts_sum = loser_pts_sum = scored_for_avg = 0
    tf_count = md_count = pin_count = 0

    for fpath in glob.glob(str(DATA_DIR / season / "*.json")):
        d = json.load(open(fpath))
        for w in d.get("roster", []):
            for m in w.get("matches", []):
                date = m.get("date")
                summary = m.get("summary", "")
                # Both wrestlers' logs record the identical summary text for
                # a shared match, so (date, summary) dedupes without
                # requiring the opponent to also be a tracked team.
                key = (date, summary)
                if key in seen:
                    continue
                seen.add(key)

                if " over " not in summary or summary.rstrip().endswith("bye"):
                    continue  # bye, or unresolved "vs." -- not a decided match at all

                total_decided += 1

                if " over Unknown" in summary or "Unknown over " in summary:
                    stoppage["other"] += 1
                    continue

                code_score = get_code_score(summary)
                cs = CODE_SCORE_RE.match(code_score.strip()) if code_score else None
                if not cs:
                    stoppage["other"] += 1
                    continue
                code = cs.group(1)
                s1, s2 = cs.group(2), cs.group(3)

                if code in GRID_CODES and s1 is not None and s2 is not None:
                    wscore, lscore = int(s1), int(s2)  # already winner-then-loser order
                    total_scored += 1
                    stoppage[code] += 1
                    unique_raw_combos.add((wscore, lscore))

                    winner_pts_sum += wscore
                    loser_pts_sum += lscore
                    scored_for_avg += 1
                    if code == "TF":
                        tf_count += 1
                    if code == "MD":
                        md_count += 1

                    wcap = min(wscore, WIN_CAP)
                    lcap = min(lscore, LOSE_CAP)
                    grid[lcap][wcap] += 1
                    top_combo_counter[(wcap, lcap)] += 1

                    points_wins[min(wscore, PTS_CAP)] += 1
                    points_losses[min(lscore, PTS_CAP)] += 1
                elif code in NO_SCORE_LABELS:
                    stoppage[code] += 1
                    if code == "Fall":
                        pin_count += 1
                else:
                    stoppage["other"] += 1

    top_combos = [
        {"winner": w, "loser": l, "count": c}
        for (w, l), c in sorted(top_combo_counter.items(), key=lambda kv: -kv[1])[:15]
    ]

    return {
        "season": season,
        "label": season_label(season),
        "team_count": team_count(season),
        "total_decided_matches": total_decided,
        "total_scored_matches": total_scored,
        "win_cap": WIN_CAP,
        "lose_cap": LOSE_CAP,
        "grid": grid,
        "top_combos": top_combos,
        "stoppage_breakdown": dict(stoppage),
        "unique_combos": len(unique_raw_combos),
        "points_wins": points_wins,
        "points_losses": points_losses,
        "winner_avg_pts": round(winner_pts_sum / scored_for_avg, 3) if scored_for_avg else 0,
        "loser_avg_pts": round(loser_pts_sum / scored_for_avg, 3) if scored_for_avg else 0,
        "tech_fall_rate": round(100 * tf_count / total_decided, 2) if total_decided else 0,
        "major_decision_rate": round(100 * md_count / total_decided, 2) if total_decided else 0,
        "pin_rate": round(100 * pin_count / total_decided, 2) if total_decided else 0,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-season", default="all", help='4-digit season to rebuild, or "all" (default) for every season under mt/data/ncaa_men/')
    p.add_argument("-out-dir", default=None, help="Output directory (default: frontend/wrestledata-ui/public/data/final_scores/)")
    args = p.parse_args()

    out_dir = Path(args.out_dir) if args.out_dir else DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    seasons = available_seasons() if args.season == "all" else [args.season]

    index_seasons = []
    trend_entries = {}
    for season in seasons:
        print(f"Building {season} ({season_label(season)})...")
        stats = compute_season_stats(season)
        (out_dir / f"{season}.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False))
        index_seasons.append({"season": season, "label": stats["label"], "team_count": stats["team_count"]})
        trend_entries[season] = {
            "label": stats["label"],
            "winner": stats["winner_avg_pts"],
            "loser": stats["loser_avg_pts"],
            "tech_fall_rate": stats["tech_fall_rate"],
            "major_decision_rate": stats["major_decision_rate"],
            "pin_rate": stats["pin_rate"],
        }
        print(f"  decided={stats['total_decided_matches']} scored={stats['total_scored_matches']} unique_combos={stats['unique_combos']}")

    index_path = out_dir / "index.json"
    trend_path = out_dir / "trend.json"

    if args.season == "all":
        index_seasons.sort(key=lambda s: s["season"], reverse=True)
        index_path.write_text(json.dumps({"seasons": index_seasons}, indent=2, ensure_ascii=False))
        print(f"Wrote index.json with {len(index_seasons)} seasons")
    else:
        # Keep index.json/trend.json in sync for a single-season refresh
        # too, without clobbering entries for seasons not rebuilt this run.
        existing = json.loads(index_path.read_text())["seasons"] if index_path.exists() else []
        existing = [s for s in existing if s["season"] != args.season] + index_seasons
        existing.sort(key=lambda s: s["season"], reverse=True)
        index_path.write_text(json.dumps({"seasons": existing}, indent=2, ensure_ascii=False))
        print(f"Updated index.json ({len(existing)} seasons)")

        if trend_path.exists():
            existing_trend = json.loads(trend_path.read_text())
            existing_trend.update(trend_entries)
            trend_entries = existing_trend

    # trend.json is a lightweight cross-season summary (5 numbers/season) so
    # the trend charts don't need to fetch all 15 full season files (each
    # carrying a 16x26 grid + top combos) just to plot 5 lines.
    ordered = sorted(trend_entries.items(), key=lambda kv: kv[0])  # oldest first
    trend_out = {
        "seasons": [e["label"] for _, e in ordered],
        "winner": [e["winner"] for _, e in ordered],
        "loser": [e["loser"] for _, e in ordered],
        "tech_fall_rate": [e["tech_fall_rate"] for _, e in ordered],
        "major_decision_rate": [e["major_decision_rate"] for _, e in ordered],
        "pin_rate": [e["pin_rate"] for _, e in ordered],
    }
    trend_path.write_text(json.dumps(trend_out, indent=2, ensure_ascii=False))
    print(f"Wrote trend.json with {len(ordered)} seasons")

    print(f"\nOutput: {out_dir}")


if __name__ == "__main__":
    main()
