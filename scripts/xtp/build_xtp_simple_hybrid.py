#!/usr/bin/env python3
"""
Builds a candidate replacement for the XTP_SIMPLE_POINTS_{BOYS,GIRLS} tables in
run_weight_xtp.py, and the two charts used to sanity-check it.

STATUS 2026-09-22: built and reviewed for the 2026 season (boys + girls). NOT wired into
run_weight_xtp.py / the team-page headline yet - TJ wants to implement and test that
separately. This script only writes its output under mt/audits/xtp_tuning/; it does not
touch any file the live site reads.

--------------------------------------------------------------------------------------
WHY THIS EXISTS
--------------------------------------------------------------------------------------
XTP_SIMPLE_POINTS_{BOYS,GIRLS} in run_weight_xtp.py is a flat rank -> points lookup table,
hand-built around the assumption that seeds hold (rank 1 = 1st place points, rank 2 = 2nd,
etc). It's what the team-page headline ("Projected State Tournament Points") and the xTP
team leaderboard sort actually display - not the full bracket-engine `xTP` (see the CLAUDE.md
"xTP and Bonus on KentuckyMat" note for that distinction).

Comparing it against 2026's real results (TJ + Claude, 2026-09-22) found it's wrong in two
different ways at once:
  - It's too generous at rank 1 (assumes the #1 seed wins; in reality even a true #1 seed
    only wins ~2/3 of the time at this level - three of fourteen 2026 boys #1 seeds scored
    under 5 points, including one to injury).
  - It's too stingy in the mid-to-late ranks: boys ranks 9-24 score real, gradually-declining
    points in reality, but the table gives them a flat 3.0/2.5/0.5 and then a hard cliff to 0.0
    at rank 25. Girls has the opposite mid-range problem: ranks 9-12 are UNDERpriced (flat 2.0
    vs an actual average of 3-6).

--------------------------------------------------------------------------------------
THE THREE SERIES (see the two "boys/girls 2026 predicted vs actual" charts)
--------------------------------------------------------------------------------------
  1. BLUE  - actual points scored, averaged at each pre-state rank (noisy: n=12-14/rank for
     a single season, so it's smoothed with a 3-point moving average for the line; the exact
     per-rank dots are also plotted).
  2. ORANGE - the CURRENT XTP_SIMPLE_POINTS_{BOYS,GIRLS} table, for reference.
  3. GREEN - actual points, plotted per FINISHING SPOT rather than per rank (Placed 1..8,
     then the non-placing "exit tiers": how far a wrestler got in the consolation bracket
     before their tournament ended). This is a completely different chart-building exercise
     from the by-rank series - see FINISH-SPOT X-POSITIONS below, and the "found + fixed"
     bugs list, because getting this series right took several real corrections.

--------------------------------------------------------------------------------------
FINISH-SPOT X-POSITIONS (TJ's correction, 2026-09-22 - do not regress this)
--------------------------------------------------------------------------------------
Placed 1-8 are individual bracket "spots" (1 wrestler per weight each) - x = 1..8 directly.
The non-placing exit tiers each cover MULTIPLE spots per weight (e.g. boys Cons. Round 4
exit = 4 wrestlers/weight), so their x-position is the MIDPOINT of the spot-range they
represent, not a sequential integer:
  Boys (32-man bracket, 4 exit tiers, verified against the real bracket topology):
    Cons. Round 4 exit -> spots  9-12 (4/weight) -> x = 10.5
    Cons. Round 3 exit -> spots 13-16 (4/weight) -> x = 14.5
    Cons. Round 2 exit -> spots 17-24 (8/weight) -> x = 20.5
    Cons. Round 1 exit -> spots 25-32 (8/weight) -> x = 28.5
  Girls (16-man bracket, only 2 exit tiers - smaller bracket, no Cons Round 3/4):
    Cons. Round 2 exit -> spots  9-12 (4/weight) -> x = 10.5
    Cons. Round 1 exit -> spots 13-16 (4/weight) -> x = 14.5
This is computed dynamically below (`spot_midpoints`) from each tier's real n/weight-count,
not hardcoded, so it stays correct if a future season's tier populations shift.

TJ's reasoning check that this reconciles (2026-09-22): boys - 336 of 448 entrants (24/weight)
have >=1 win, 112 (8/weight) have zero; every one of the 12 categories accounted for, nothing
past spot 32 because a 32-man bracket has no 33rd entrant. Girls - 192 total = 12 weights x
16-man bracket, same idea with 2 exit tiers instead of 4.

--------------------------------------------------------------------------------------
BUGS FOUND + FIXED BUILDING THIS (all fixed in this script; the underlying scripts these
were adapted from were NOT patched - see "left alone on purpose" below)
--------------------------------------------------------------------------------------
1. Girls round-priority order is NOT the boys order. A first pass copied the boys 32-man
   round sequence, which ranks Quarterfinals above Cons. Round 2 - backwards for the 16-man
   bracket, where ALL 48 girls QF losers land in Cons. Round 2 (verified empirically: every
   QF-loser wid has a real Cons. Round 2 match on record; zero data gaps). Using the boys
   order manufactured 12 fake "eliminated in the Quarterfinals" girls entries. Fixed by
   giving girls its own GIRLS_ROUND_ORDER (see round_priority()).
2. NoResult / "Unknown" ghost records must be filtered before computing a wrestler's final
   bracket round. TrackWrestling sometimes leaves the ORIGINAL seed pairing as an unresolved
   "X vs. Y" record (result == "NoResult", winner_name == loser_name == "Unknown") even after
   the real opponent changed (scratch, bye-fill) and the real result was recorded separately.
   Treating these as real matches fabricated 2 fake "eliminated in Champ. Round 1, no further
   match" girls entries. Fixed in iter_state_matches() below.
3. The shared placement lookup in scripts/state/evaluate_state_predictions.py
   (_collect_actual_placements) requires a non-null opponent_id, which forfeits don't have -
   that silently dropped girls 152 lbs' real 7th/8th pair (a forfeit finish, "Devon Banks over
   jacelyn smith (For.)"). This script uses its own collect_placements() below, which resolves
   place directly from each wrestler's own roster entry and never needs opponent_id.
4. evaluate_state_predictions.py's default --processed-dir points at
   frontend/wrestledata-ui/public/data/processed_data, which is STALE for girls 2026 (only has
   unresolved "vs." placeholder rows for some Champ. Round 1 matches, missing the real
   completed results). This script always reads mt/processed_data directly.

LEFT ALONE ON PURPOSE (real bugs, not fixed here - out of scope for a table-building script,
and TJ said hold off on wiring anything into production until tomorrow):
  - The opponent_id gap in evaluate_state_predictions.py's _collect_actual_placements (bug 3
    above) is still present in that file. This script doesn't call that function for
    placements (it has its own collect_placements()), so it isn't affected, but anyone running
    evaluate_state_predictions.py directly still hits it.
  - The stale frontend/wrestledata-ui processed_data copy (bug 4) is still stale.

--------------------------------------------------------------------------------------
THE HYBRID FORMULA
--------------------------------------------------------------------------------------
For every rank r in the pre-state rankings:
    green(r) = PchipInterpolator fit through the finish-spot series (monotonic cubic - no
               overshoot, preserves the real decreasing shape), evaluated at r. Held flat at
               its last real value (0.0) beyond the bracket's max spot (32 boys / 16 girls),
               since there's no data past the worst exit tier.
    blue(r)  = actual points by rank, 3-point moving average.
    hybrid(r) = 0.8 * green(r) + 0.2 * blue(r)
Then: enforce monotonic non-increasing (np.minimum.accumulate) - a worse rank should never
score more than a better rank in expectation, and this also cleanly absorbs a small amount of
real per-rank noise in blue's deep tail (ranks 30+) that otherwise produced a nonsensical
upward blip. Finally round to the nearest 0.5, matching the current table's convention.

Why 0.8/0.2 and not something else: TJ's call (2026-09-22), after looking at both raw
per-rank averages (too noisy/pulled down by outliers like an injured #1 seed) and pure
seed-holds assumptions (proven wrong - see WHY THIS EXISTS). Green is outcome-conditioned so
it's not a neutral "expected value for this rank" on its own; blending in a little of blue
pulls it back toward a true per-rank expectation without losing the placement-tier shape.
This weighting is a judgment call, not a derived optimum - revisit if a second season's data
becomes available to check against.

Usage:
    .venv/bin/python scripts/xtp/build_xtp_simple_hybrid.py --season 2026 -gender boys
    .venv/bin/python scripts/xtp/build_xtp_simple_hybrid.py --season 2026 -gender girls
    .venv/bin/python scripts/xtp/build_xtp_simple_hybrid.py --season 2026 -gender both

Output (per gender), all under mt/audits/xtp_tuning/:
    {gender}_{season}_rank_vs_points.csv       - per-wrestler reconciliation (rank, points,
                                                  place, exit round - every real state entrant)
    {gender}_{season}_xtp_rank_chart.png        - the 3-line chart (blue/orange/green)
    {gender}_{season}_hybrid_chart.png          - the hybrid vs. its two inputs
    {gender}_{season}_hybrid_table.json         - {rank: points} candidate table, rounded
"""
import argparse
import csv
import importlib.util
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator
from scipy.ndimage import uniform_filter1d
from scipy.interpolate import PchipInterpolator

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
import sys
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "state"))
import evaluate_state_predictions as esp  # noqa: E402

_spec = importlib.util.spec_from_file_location("run_weight_xtp", PROJECT_ROOT / "scripts" / "xtp" / "run_weight_xtp.py")
rwx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rwx)

HS_BOYS_WEIGHTS = [106, 113, 120, 126, 132, 138, 144, 150, 157, 165, 175, 190, 215, 285]
HS_GIRLS_WEIGHTS = [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235]

PROCESSED_BASE = PROJECT_ROOT / "mt" / "processed_data"  # NOT frontend/wrestledata-ui - see bug 4 above
RANKINGS_BASE = PROJECT_ROOT / "frontend" / "hs-ky-ui" / "public" / "data" / "rankings"
OUT_DIR = PROJECT_ROOT / "mt" / "audits" / "xtp_tuning"

BOYS_ROUND_ORDER = [
    "Champ. Round 1", "Cons. Round 1", "Champ. Round 2", "Cons. Round 2",
    "Quarterfinals", "Cons. Round 3", "Cons. Round 4", "Semifinals",
    "Cons. Round 5", "Cons. Semis",
    "7th Place Match", "5th Place Match", "3rd Place Match", "1st Place Match",
]
GIRLS_ROUND_ORDER = [
    "Champ. Round 1", "Cons. Round 1", "Quarterfinals", "Cons. Round 2",
    "Cons. Round 3", "Semifinals", "Cons. Semis",
    "7th Place Match", "5th Place Match", "3rd Place Match", "1st Place Match",
]
PLACEMENT_LABELS = {"1st Place Match": (1, 2), "3rd Place Match": (3, 4),
                     "5th Place Match": (5, 6), "7th Place Match": (7, 8)}

# ordered non-placing exit tiers, furthest-to-earliest, per gender - drives both the
# reconciliation bucketing and the finish-spot x-position midpoints
BOYS_EXIT_TIERS = ["Cons. Round 4", "Cons. Round 3", "Cons. Round 2", "Cons. Round 1"]
GIRLS_EXIT_TIERS = ["Cons. Round 2", "Cons. Round 1"]

BRACKET_SIZE = {"boys": 32, "girls": 16}


def clean_round(summary):
    s = (summary or "").strip()
    if s.startswith("Varsity - "):
        s = s[len("Varsity - "):]
    for r in BOYS_ROUND_ORDER:  # superset of girls' label vocabulary; just for string ID
        if s.startswith(r):
            return r
    return s.split(" - ")[0] if " - " in s else s


def round_priority(rlabel, gender):
    order = BOYS_ROUND_ORDER if gender == "boys" else GIRLS_ROUND_ORDER
    return order.index(rlabel) if rlabel in order else -1


def iter_state_matches(gender, season, state_dates, state_event):
    """Yields (wid, roster_name, round_label, won) for every REAL state match - excludes
    NoResult/"Unknown" ghost records (bug 2 above)."""
    data_dir = PROCESSED_BASE / f"hs_ky_{gender}" / str(season)
    for team_file in sorted(data_dir.glob("*.json")):
        try:
            data = json.loads(team_file.read_text())
        except Exception:
            continue
        for wrestler in data.get("roster") or []:
            wid = str(wrestler.get("season_wrestler_id", ""))
            if not wid:
                continue
            roster_name = (wrestler.get("name") or "").strip()
            for m in wrestler.get("matches") or []:
                if state_event not in (m.get("event") or ""):
                    continue
                if (m.get("date") or "").strip() not in state_dates:
                    continue
                summary = m.get("summary") or ""
                if "Junior Varsity" in summary:
                    continue
                if (m.get("result") or "") == "NoResult":
                    continue
                winner_name = (m.get("winner_name") or "").strip()
                loser_name = (m.get("loser_name") or "").strip()
                if "Unknown" in (winner_name, loser_name) or not winner_name or not loser_name:
                    continue
                yield wid, roster_name, clean_round(summary), winner_name == roster_name


def collect_final_rounds(gender, season, state_dates, state_event):
    best = {}
    for wid, name, rlabel, won in iter_state_matches(gender, season, state_dates, state_event):
        prio = round_priority(rlabel, gender)
        cur = best.get(wid)
        if cur is None or prio > cur[2]:
            best[wid] = (rlabel, won, prio)
    return best


def collect_placements(gender, season, state_dates, state_event):
    """Own placement collector (bug 3 above) - does NOT require opponent_id."""
    place_by_id = {}
    data_dir = PROCESSED_BASE / f"hs_ky_{gender}" / str(season)
    for team_file in sorted(data_dir.glob("*.json")):
        try:
            data = json.loads(team_file.read_text())
        except Exception:
            continue
        for wrestler in data.get("roster") or []:
            wid = str(wrestler.get("season_wrestler_id", ""))
            if not wid:
                continue
            roster_name = (wrestler.get("name") or "").strip()
            for m in wrestler.get("matches") or []:
                if state_event not in (m.get("event") or ""):
                    continue
                if (m.get("date") or "").strip() not in state_dates:
                    continue
                summary = m.get("summary") or ""
                for label, (wp, lp) in PLACEMENT_LABELS.items():
                    if label not in summary:
                        continue
                    winner_name = (m.get("winner_name") or "").strip()
                    loser_name = (m.get("loser_name") or "").strip()
                    if roster_name == winner_name:
                        place_by_id[wid] = wp
                    elif roster_name == loser_name:
                        place_by_id[wid] = lp
                    break
    return place_by_id


def build_reconciliation(gender, season):
    """Returns (rows, drop_id) - one row per real state entrant, with rank/points/place/
    final_round - and writes the per-wrestler CSV."""
    state_event = esp.STATE_EVENT_BOYS if gender == "boys" else esp.STATE_EVENT_GIRLS
    weights = HS_BOYS_WEIGHTS if gender == "boys" else HS_GIRLS_WEIGHTS
    state_dates = esp._state_dates_for_season(season)

    drop_id, rank_by = esp._load_rankings_before_tournament(RANKINGS_BASE, season, weights, gender)
    placements_shared = esp._collect_actual_placements(PROCESSED_BASE, gender, season, state_dates, state_event)
    points = esp._compute_wrestler_state_points(PROCESSED_BASE, gender, season, state_dates, state_event, placements_shared)
    points_by_id = {wid: (name, team, weight, pts) for wid, name, team, weight, pts in points}
    final_rounds = collect_final_rounds(gender, season, state_dates, state_event)
    place_by_id = collect_placements(gender, season, state_dates, state_event)

    all_entrants = set(final_rounds) | set(place_by_id)
    rank_lookup = {wid: rank for (weight, wid), rank in rank_by.items()}
    weight_lookup = {}
    for (weight, wid) in rank_by:
        weight_lookup.setdefault(wid, weight)

    rows = []
    for wid in all_entrants:
        rank = rank_lookup.get(wid)
        name, team, wgt, pts = points_by_id.get(wid, (None, None, None, 0.0))
        rlabel, won, prio = final_rounds.get(wid, (None, None, -1))
        rows.append({
            "gender": gender, "season": season, "weight": wgt or weight_lookup.get(wid),
            "rank": rank, "wrestler_id": wid, "name": name, "team": team,
            "points_scored": round(pts, 2), "place": place_by_id.get(wid),
            "final_round": rlabel, "won_final_match": won,
        })
    rows.sort(key=lambda r: ((r["weight"] or 0), r["rank"] or 999))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / f"{gender}_{season}_rank_vs_points.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    return rows, drop_id, len(weights)


def build_finish_spot_series(rows, gender, n_weights):
    """Returns (labels, x_positions, avg_points, n_per_bucket) for the green series -
    Placed 1-8 at x=1..8, then each exit tier at the midpoint of the bracket spots it covers
    (computed from its real n/weight, not hardcoded - see module docstring)."""
    exit_tiers = BOYS_EXIT_TIERS if gender == "boys" else GIRLS_EXIT_TIERS
    by_bucket = defaultdict(list)
    for r in rows:
        key = f"Placed {r['place']}" if r["place"] else r["final_round"]
        by_bucket[key].append(r["points_scored"])

    labels, xpos, ypts, ns = [], [], [], []
    for i in range(1, 9):
        key = f"Placed {i}"
        vals = by_bucket.get(key, [])
        labels.append(key)
        xpos.append(float(i))
        ypts.append(sum(vals) / len(vals) if vals else 0.0)
        ns.append(len(vals))

    spot_cursor = 8  # placers occupy spots 1-8
    for tier in exit_tiers:
        vals = by_bucket.get(tier, [])
        n = len(vals)
        n_per_weight = round(n / n_weights) if n_weights else 0
        lo, hi = spot_cursor + 1, spot_cursor + n_per_weight
        spot_cursor = hi
        labels.append(tier.replace("Cons. Round", "Cons R"))
        xpos.append((lo + hi) / 2)
        ypts.append(sum(vals) / n if vals else 0.0)
        ns.append(n)

    return labels, xpos, ypts, ns


def build_by_rank_series(gender, season, maxrank=50):
    rows_path = OUT_DIR / f"{gender}_{season}_rank_vs_points.csv"
    rows = list(csv.DictReader(rows_path.open()))
    by_rank = defaultdict(list)
    for r in rows:
        if r["rank"]:
            by_rank[int(r["rank"])].append(float(r["points_scored"]))
    ranks = [r for r in range(1, maxrank + 1) if r in by_rank]
    avg = [sum(by_rank[r]) / len(by_rank[r]) for r in ranks]
    return ranks, avg


PALETTE = {
    "blue": "#2a78d6", "orange": "#eb6834", "aqua": "#1baf7a", "yellow": "#eda100",
    "text_primary": "#0b0b0b", "text_secondary": "#52514e", "grid": "#e3e2dc", "surface": "#fcfcfb",
}


def _style_axes(ax):
    ax.grid(True, color=PALETTE["grid"], linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    for spine in ["left", "bottom"]:
        ax.spines[spine].set_color(PALETTE["grid"])
    ax.tick_params(colors=PALETTE["text_secondary"], labelsize=9)


def plot_three_line_chart(gender, season, ranks, actual_avg, simple_table, flabels, fxpos, fypts, fn, out_path):
    ay_smooth = uniform_filter1d(np.array(actual_avg), size=3, mode="nearest")
    max_simple_rank = max(simple_table)
    sx = list(range(1, max_simple_rank + 1))
    sy = [simple_table.get(r, 0.0) for r in sx]

    fig, ax = plt.subplots(figsize=(11, 6.5), dpi=200)
    fig.patch.set_facecolor(PALETTE["surface"])
    ax.set_facecolor(PALETTE["surface"])

    ax.plot(ranks, ay_smooth, color=PALETTE["blue"], linewidth=2, zorder=3,
            label="Actual points, by pre-state rank")
    ax.scatter(ranks, actual_avg, color=PALETTE["blue"], s=10, alpha=0.35, zorder=2)
    ax.plot(sx, sy, color=PALETTE["orange"], linewidth=2, zorder=3, label="xTP_simple prediction, by rank")
    ax.plot(fxpos, fypts, color=PALETTE["aqua"], linewidth=2, zorder=3,
            label="Actual points, by finishing spot (midpoint of spot range)")
    ax.scatter(fxpos, fypts, color=PALETTE["aqua"], s=34, zorder=4,
               edgecolor=PALETTE["surface"], linewidth=1)

    up = True
    for x, y, lbl, n in zip(fxpos, fypts, flabels, fn):
        dy = (16 if up else -16)
        ax.annotate(f"{lbl}\n(n={n})", (x, y), textcoords="offset points", xytext=(0, dy),
                    ha="center", va=("bottom" if up else "top"), fontsize=7.5,
                    color=PALETTE["text_secondary"], linespacing=1.3)
        up = not up

    xmax = max(max(ranks), max(sx), max(fxpos)) + 2
    ax.set_xlim(0, xmax)
    ax.set_ylim(0, max(max(actual_avg), max(sy), max(fypts)) * 1.08)
    ax.xaxis.set_major_locator(MultipleLocator(2))
    ax.set_xlabel("Pre-state rank (blue/orange)  —  finishing spot, midpoint of range (green)",
                  color=PALETTE["text_primary"], fontsize=11)
    ax.set_ylabel("KHSAA team points scored at state", color=PALETTE["text_primary"], fontsize=11)
    ax.set_title(f"{gender.title()} {season}: predicted vs. actual state-tournament points by rank",
                 color=PALETTE["text_primary"], fontsize=13, fontweight="bold", loc="left", pad=14)
    _style_axes(ax)
    ax.legend(loc="upper right", frameon=False, fontsize=9.5, labelcolor=PALETTE["text_primary"])
    fig.text(0.01, 0.01,
             "Dots = exact per-rank averages; blue/orange lines = 3-point moving average; green connects exact category dots.",
             fontsize=8, color=PALETTE["text_secondary"])
    plt.tight_layout(rect=[0, 0.03, 1, 1])
    plt.savefig(out_path, facecolor=fig.get_facecolor())
    plt.close(fig)


def build_hybrid(ranks, actual_avg, fxpos, fypts, green_weight=0.8, blue_weight=0.2):
    ay_smooth = uniform_filter1d(np.array(actual_avg), size=3, mode="nearest")
    green_interp = PchipInterpolator(fxpos, fypts, extrapolate=False)
    green_at_rank = green_interp(np.array(ranks))
    green_at_rank = np.where(np.isnan(green_at_rank), 0.0, green_at_rank)
    hybrid_raw = green_weight * green_at_rank + blue_weight * ay_smooth
    hybrid = np.minimum.accumulate(hybrid_raw)  # monotonic non-increasing - see module docstring
    rounded = np.round(hybrid * 2) / 2
    return hybrid, rounded


def plot_hybrid_chart(gender, season, ranks, actual_avg, simple_table, fxpos, fypts, hybrid, out_path):
    ay_smooth = uniform_filter1d(np.array(actual_avg), size=3, mode="nearest")
    max_simple_rank = max(simple_table)
    sx = list(range(1, max_simple_rank + 1))
    sy = [simple_table.get(r, 0.0) for r in sx]

    fig, ax = plt.subplots(figsize=(11, 6.5), dpi=200)
    fig.patch.set_facecolor(PALETTE["surface"])
    ax.set_facecolor(PALETTE["surface"])

    ax.plot(ranks, ay_smooth, color=PALETTE["blue"], linewidth=1.5, alpha=0.55, zorder=2,
            label="Actual points, by rank (smoothed)")
    ax.plot(sx, sy, color=PALETTE["orange"], linewidth=1.5, alpha=0.55, zorder=2, label="xTP_simple (current)")
    ax.plot(fxpos, fypts, color=PALETTE["aqua"], linewidth=1.5, alpha=0.55, marker="o", markersize=4,
            zorder=2, label="Actual points, by finishing spot")
    ax.plot(ranks, hybrid, color=PALETTE["yellow"], linewidth=3, zorder=4,
            label="Hybrid candidate: 0.8×finish-spot + 0.2×rank")

    xmax = max(fxpos) + 4
    ax.set_xlim(0, xmax)
    ax.set_ylim(0, max(max(actual_avg), max(sy), max(fypts)) * 1.08)
    ax.xaxis.set_major_locator(MultipleLocator(2))
    ax.set_xlabel("Pre-state rank", color=PALETTE["text_primary"], fontsize=11)
    ax.set_ylabel("KHSAA team points scored at state", color=PALETTE["text_primary"], fontsize=11)
    ax.set_title(f"{gender.title()} {season}: xTP_simple hybrid candidate vs. its two inputs",
                 color=PALETTE["text_primary"], fontsize=13, fontweight="bold", loc="left", pad=14)
    _style_axes(ax)
    ax.legend(loc="upper right", frameon=False, fontsize=9.5, labelcolor=PALETTE["text_primary"])
    fig.text(0.01, 0.01,
             "Hybrid = 0.8×(green, Pchip-interpolated onto rank) + 0.2×(blue, 3-pt moving avg), "
             "then forced monotonic non-increasing and rounded to nearest 0.5.",
             fontsize=8, color=PALETTE["text_secondary"])
    plt.tight_layout(rect=[0, 0.03, 1, 1])
    plt.savefig(out_path, facecolor=fig.get_facecolor())
    plt.close(fig)


def run(gender, season):
    print(f"=== {gender.upper()} {season} ===")
    rows, drop_id, n_weights = build_reconciliation(gender, season)
    print(f"  {len(rows)} real state entrants (rankings drop {drop_id})")

    flabels, fxpos, fypts, fn = build_finish_spot_series(rows, gender, n_weights)
    ranks, actual_avg = build_by_rank_series(gender, season)
    simple_table = rwx.XTP_SIMPLE_POINTS_BOYS if gender == "boys" else rwx.XTP_SIMPLE_POINTS_GIRLS

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    chart_path = OUT_DIR / f"{gender}_{season}_xtp_rank_chart.png"
    plot_three_line_chart(gender, season, ranks, actual_avg, simple_table, flabels, fxpos, fypts, fn, chart_path)
    print(f"  wrote {chart_path}")

    hybrid, rounded = build_hybrid(ranks, actual_avg, fxpos, fypts)
    hybrid_chart_path = OUT_DIR / f"{gender}_{season}_hybrid_chart.png"
    plot_hybrid_chart(gender, season, ranks, actual_avg, simple_table, fxpos, fypts, hybrid, hybrid_chart_path)
    print(f"  wrote {hybrid_chart_path}")

    table = {int(r): float(v) for r, v in zip(ranks, rounded)}
    table_path = OUT_DIR / f"{gender}_{season}_hybrid_table.json"
    json.dump(table, table_path.open("w"), indent=2)
    print(f"  wrote {table_path}")

    print(f"\n  {'rank':>4} {'hybrid':>7} {'xtp_simple_now':>15}")
    for r in ranks:
        print(f"  {r:>4} {table[r]:>7.1f} {simple_table.get(r, 0.0):>15.1f}")
    print()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--season", type=int, default=2026)
    p.add_argument("-gender", choices=["boys", "girls", "both"], default="both")
    args = p.parse_args()
    genders = ["boys", "girls"] if args.gender == "both" else [args.gender]
    for g in genders:
        run(g, args.season)


if __name__ == "__main__":
    main()
