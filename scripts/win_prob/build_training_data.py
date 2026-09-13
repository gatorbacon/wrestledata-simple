#!/usr/bin/env python3
"""
Turns parsed bout play-by-play (data/pbp/events_{tournament}.jsonl, built by
scripts/analysis/parse_bout_pbp.py) into a labeled training table for a live
win-probability model.

Why two rows per event, not one: parse_bout_pbp.py's rows are winner/loser-
labeled by construction (we already know who won), so the outcome is baked
into that framing and there's nothing to predict. The standard fix (same
approach as NFL/NBA win-probability models): emit the event TWICE, once from
each wrestler's own perspective, with every feature computed relative to
that wrestler (their own score minus opponent's, their own position, etc.)
and a label of 1 if that wrestler ultimately won, 0 if not. The model then
learns by pooling across thousands of bouts with different trajectories --
e.g. "of everyone who was down 0-3 early with 5:40 left, X% eventually
won" -- not from any single bout's outcome being ambiguous.

Deliberately NOT done here: no assumption about which state values help or
hurt (e.g. top vs. bottom position, or being flip_winner) is encoded --
these are passed through as plain categorical/boolean features for the
model in Phase 3 to learn the direction and size of, not asserted here.

DPG join: bout data only has wrestler name + team (no wrestler_id -- it
comes from TrackWrestling, a separate system from ours), so each wrestler's
season DPG is joined by (weight, normalized name) against that season's
mat_value_{year}.json, using the same normalize_name() + apostrophe-
canonicalization + last-name/first-initial fallback already proven in
scripts/analysis/flo_preseason_vs_score.py for this exact kind of join.
Unmatched wrestlers (should be rare) get dpg=None -- not silently dropped,
not silently zeroed -- so Phase 3 can decide how to handle missing DPG
(e.g. true freshmen with no prior-season number) explicitly.

Output: data/pbp/training_rows.csv -- one row per (event, perspective),
suitable for pandas / scikit-learn directly.

Usage:
    python scripts/win_prob/build_training_data.py
    python scripts/win_prob/build_training_data.py --tournaments ncaa,big_ten
"""

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
PBP_DIR = DATA_DIR / "pbp"
MAT_VALUE_DIR = PROJECT_ROOT / "frontend/wrestledata-ui/public/data/mat_value"


def normalize_name(name: str) -> str:
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = re.sub(r"[`´'‘’]", "'", name)
    return re.sub(r"\s+", " ", name.strip().lower())


class DpgIndex:
    """(weight, year) -> {normalized_name: mv_avg}, with a last-name +
    first-initial fallback index for the inevitable nickname/spelling
    mismatches between TrackWrestling and our own mat_value data."""

    def __init__(self):
        self._by_name = {}
        self._by_lastname = defaultdict(list)
        self._loaded_years = set()
        self.unmatched = []

    def _load_year(self, year: int):
        if year in self._loaded_years:
            return
        self._loaded_years.add(year)
        path = MAT_VALUE_DIR / str(year) / f"mat_value_{year}.json"
        if not path.exists():
            return
        for w in json.loads(path.read_text()):
            norm = normalize_name(w["name"])
            self._by_name[(year, w["weight"], norm)] = w["mv_avg"]
            parts = norm.split()
            if len(parts) >= 2:
                self._by_lastname[(year, w["weight"], parts[-1], parts[0][0])].append(w["mv_avg"])

    def lookup(self, year: int, weight: int, name: str):
        self._load_year(year)
        norm = normalize_name(name)
        val = self._by_name.get((year, weight, norm))
        if val is not None:
            return val
        parts = norm.split()
        if len(parts) >= 2:
            candidates = self._by_lastname.get((year, weight, parts[-1], parts[0][0]))
            if candidates and len(candidates) == 1:
                return candidates[0]
        self.unmatched.append((year, weight, name))
        return None


FIELDS = [
    "tournament", "year", "weight", "round", "bracket", "match_id", "bout_number",
    "event_index", "period", "period_order", "time_remaining_in_period_sec",
    "subject_side", "subject_name", "subject_team", "opponent_name", "opponent_team",
    "action", "points", "actor_is_subject", "raw_text",
    "subject_score", "opponent_score", "score_diff",
    "subject_position", "opponent_position",
    "subject_stalling_warned", "opponent_stalling_warned",
    "subject_is_flip_winner",
    "subject_riding_time_sec", "opponent_riding_time_sec", "riding_time_net_sec",
    "subject_riding_time_criterion_met",
    "subject_dpg", "opponent_dpg",
    "label",
]


def build_rows(event: dict, dpg_index: DpgIndex) -> list[dict]:
    """Returns [] (dropping the whole bout, not just one side) if either
    wrestler's DPG doesn't resolve -- a bout with an unresolvable wrestler
    has no valid opponent-quality signal for either perspective, so there's
    no consistent way to keep half of it. See docs/matsavant.md Known
    Gotcha #14 for why this happens (not a career-linking issue -- a single
    unresolvable opponent elsewhere in that wrestler's season silently
    drops their whole-season DPG upstream)."""
    year, weight = event["year"], event["weight"]
    dpg = {
        "winner": dpg_index.lookup(year, weight, event["winner_name"]),
        "loser": dpg_index.lookup(year, weight, event["loser_name"]),
    }
    if dpg["winner"] is None or dpg["loser"] is None:
        return []

    rows = []
    for subject_side in ("winner", "loser"):
        opponent_side = "loser" if subject_side == "winner" else "winner"
        subject_name = event[f"{subject_side}_name"]
        opponent_name = event[f"{opponent_side}_name"]
        subject_score = event[f"score_{subject_side}_after"]
        opponent_score = event[f"score_{opponent_side}_after"]
        flip_winner = event.get("flip_winner")
        rows.append({
            "tournament": event["tournament"], "year": year, "weight": weight,
            "round": event.get("round"), "bracket": event.get("bracket"), "match_id": event.get("match_id"),
            "bout_number": event["bout_number"],
            "event_index": event["event_index"], "period": event["period"], "period_order": event["period_order"],
            "time_remaining_in_period_sec": event["time_remaining_in_period_sec"],
            "subject_side": subject_side,
            "subject_name": subject_name, "subject_team": event[f"{subject_side}_team"],
            "opponent_name": opponent_name, "opponent_team": event[f"{opponent_side}_team"],
            "action": event["action"], "points": event["points"],
            # who actually DID this event (scored, chose, deferred) --
            # needed to phrase e.g. "Valencia takes bottom" for a choice/
            # defer event, which subject_position alone can't say (it's the
            # RESULT of the choice, not who made it).
            "actor_is_subject": event.get("side") == subject_side,
            "raw_text": event.get("raw_text"),
            "subject_score": subject_score, "opponent_score": opponent_score,
            "score_diff": subject_score - opponent_score,
            "subject_position": event[f"position_{subject_side}_after"],
            "opponent_position": event[f"position_{opponent_side}_after"],
            "subject_stalling_warned": event[f"stalling_warned_{subject_side}_after"],
            "opponent_stalling_warned": event[f"stalling_warned_{opponent_side}_after"],
            "subject_is_flip_winner": (flip_winner == subject_side) if flip_winner else None,
            "subject_riding_time_sec": event.get(f"riding_time_{subject_side}_after"),
            "opponent_riding_time_sec": event.get(f"riding_time_{opponent_side}_after"),
            "riding_time_net_sec": (
                event[f"riding_time_{subject_side}_after"] - event[f"riding_time_{opponent_side}_after"]
                if event.get(f"riding_time_{subject_side}_after") is not None else None
            ),
            "subject_riding_time_criterion_met": (
                (event[f"riding_time_{subject_side}_after"] - event[f"riding_time_{opponent_side}_after"]) >= 60
                if event.get(f"riding_time_{subject_side}_after") is not None else None
            ),
            "subject_dpg": dpg[subject_side],
            "opponent_dpg": dpg[opponent_side],
            "label": 1 if subject_side == "winner" else 0,
        })
    return rows


def main():
    parser = argparse.ArgumentParser(description="Build the labeled win-probability training table from parsed PBP")
    parser.add_argument("--tournaments", type=str, default=None,
                         help="Comma-separated tournament keys (default: every events_*.jsonl found in data/pbp/)")
    args = parser.parse_args()

    if args.tournaments:
        tournaments = args.tournaments.split(",")
    else:
        tournaments = [p.stem.replace("events_", "") for p in PBP_DIR.glob("events_*.jsonl")]

    dpg_index = DpgIndex()
    out_path = PBP_DIR / "training_rows.csv"
    total_events = 0
    total_rows = 0
    dropped_bouts = set()
    kept_bouts = set()

    with open(out_path, "w", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=FIELDS)
        writer.writeheader()
        for tournament in tournaments:
            events_path = PBP_DIR / f"events_{tournament}.jsonl"
            if not events_path.exists():
                print(f"[SKIP] {events_path} not found")
                continue
            with open(events_path) as f:
                for line in f:
                    event = json.loads(line)
                    bout_key = (event["tournament"], event["year"], event["weight"], event["bout_number"])
                    rows = build_rows(event, dpg_index)
                    for r in rows:
                        writer.writerow(r)
                    total_events += 1
                    total_rows += len(rows)
                    (kept_bouts if rows else dropped_bouts).add(bout_key)

    # A bout only ever fully succeeds or fully fails (every event in it
    # shares the same two wrestler names), so this set difference is exact,
    # not an approximation.
    dropped_bouts -= kept_bouts
    print(f"\n[DONE] {total_events} events -> {total_rows} training rows -> {out_path}")
    print(f"  {len(dropped_bouts)} bout(s) dropped entirely (unresolvable wrestler DPG on one side) -- "
          f"see docs/matsavant.md Known Gotcha #14")
    if dropped_bouts:
        print("  Dropped bouts (tournament, year, weight, bout_number):")
        for b in sorted(dropped_bouts)[:15]:
            print(f"    {b}")
    if dpg_index.unmatched:
        distinct_unmatched = sorted(set(dpg_index.unmatched))
        print(f"  {len(distinct_unmatched)} distinct (year, weight, name) lookups never resolved:")
        for u in distinct_unmatched[:15]:
            print(f"    {u}")


if __name__ == "__main__":
    main()
