#!/usr/bin/env python3
"""
Phase 5/6: compute a live win-probability trace for one specific bout, in the
style of an ESPN win-probability chart.

The model reacts to three things that all keep moving even when nobody
scores: the CLOCK (match_time_fraction_remaining -- see fit_baseline_model.py
for why this is match-relative, not period-relative), RIDING TIME (accrues
for whoever's on top), and DPG/score/position which are genuinely constant
between events. So between every pair of consecutive events this script
resamples the model every RESAMPLE_SEC seconds, re-deriving
match_time_fraction_remaining from the elapsed clock and riding_time_net_sec
from who was in control -- producing a smooth drift between events with
vertical jumps exactly at real scoring plays.

Every NCAA overtime period is sudden-victory (see wrestling_clock.py): the
match ends the INSTANT a deciding event happens there, not at that period's
nominal length. Two things follow, both fixed 2026-09-14 (found on the
149lb final, Valencia/Van Ness): (1) match_length_sec must reflect the
bout's own actual last event when it ends in OT, not a phantom continuation
through the rest of that period (or even into a tiebreaker that never
happened -- see win_probability.js for the matching period-label fix), and
(2) the win probability at that final OT event is forced to exactly 100%
-- this is a RULE fact (the match is definitionally over), not something
the model should be asked to predict from features, however well-calibrated.

Uses the logistic-regression model (baseline_logreg.joblib), with cubic
score_diff x match_time_fraction terms (see fit_baseline_model.py) -- a
gradient-boosted version was tried and rejected: it let extreme subject_dpg
values swamp the score-state features (a big DPG favorite predicted ~93%+
regardless of who was actually leading), an overfitting failure mode in the
sparse DPG tail that the polynomial terms don't have.

This is deliberately NOT a general "run this for any bout" pipeline yet --
it's built to answer the concrete question asked (can we chart a real NCAA
final), reading training_rows.csv (which already has subject_dpg/opponent_dpg
resolved) rather than re-deriving DPG lookups.

Usage:
    python scripts/win_prob/compute_match_win_prob.py \
        --tournament ncaa --year 2026 --weight 125 --bout-number 59 \
        --subject "Luke Lilledahl"
"""

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd

from wrestling_clock import (
    PERIOD_LENGTH_SEC, PERIOD_START_ELAPSED, OVERTIME_PERIODS,
    real_period, elapsed_seconds, bout_match_length_sec,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PBP_DIR = PROJECT_ROOT / "data/pbp"
MODEL_DIR = PBP_DIR / "models"

NUMERIC_FEATURES = [
    "score_diff", "match_time_fraction_remaining",
    "score_diff_x_match_time_fraction", "score_diff_x_match_time_fraction_sq", "score_diff_x_match_time_fraction_cube",
    "subject_dpg", "opponent_dpg", "riding_time_net_sec",
]
CATEGORICAL_FEATURES = ["period", "subject_position"]
BOOLEAN_FEATURES = [
    "subject_stalling_warned", "opponent_stalling_warned", "subject_is_flip_winner_filled",
    "subject_riding_time_criterion_met_filled",
]
FEATURE_COLS = NUMERIC_FEATURES + CATEGORICAL_FEATURES + BOOLEAN_FEATURES

RESAMPLE_SEC = 3
RIDING_ACCRUAL = {"top": 1.0, "bottom": -1.0}  # sec of net riding time per elapsed second


def predict_row(model, score_diff, match_frac, subject_dpg, opponent_dpg, riding_net,
                 period, position, stall_s, stall_o, flip_win, riding_met):
    row = pd.DataFrame([{
        "score_diff": score_diff, "match_time_fraction_remaining": match_frac,
        "score_diff_x_match_time_fraction": score_diff * match_frac,
        "score_diff_x_match_time_fraction_sq": score_diff * match_frac ** 2,
        "score_diff_x_match_time_fraction_cube": score_diff * match_frac ** 3,
        "subject_dpg": subject_dpg, "opponent_dpg": opponent_dpg, "riding_time_net_sec": riding_net,
        "period": period, "subject_position": position,
        "subject_stalling_warned": stall_s, "opponent_stalling_warned": stall_o,
        "subject_is_flip_winner_filled": flip_win, "subject_riding_time_criterion_met_filled": riding_met,
    }])[FEATURE_COLS]
    return float(model.predict_proba(row)[:, 1][0])


def compute_trace(df: pd.DataFrame, model, tournament: str, year: int, weight: int,
                   bout_number: int, subject: str) -> dict:
    """Core Phase 5/6 computation, importable so callers (e.g. a lookup-by-
    wrestler-name script, or a batch plotter) don't have to shell out to the
    CLI. `df` is training_rows.csv already loaded (load once, reuse across
    many bouts); `model` is the loaded baseline_logreg.joblib pipeline."""
    bout = df[
        (df.tournament == tournament) & (df.year == year)
        & (df.weight == weight) & (df.bout_number == bout_number)
        & (df.subject_name == subject)
    ].sort_values("event_index").reset_index(drop=True)
    if bout.empty:
        raise ValueError(f"No rows found for {tournament} {year} {weight} bout {bout_number} subject={subject}")

    opponent_name = bout["opponent_name"].iloc[0]
    bout["subject_is_flip_winner_filled"] = bout["subject_is_flip_winner"].fillna(False)
    bout["riding_time_net_sec"] = bout["riding_time_net_sec"].fillna(0)
    bout["subject_position"] = bout["subject_position"].fillna("unknown")

    dpg_s, dpg_o = bout["subject_dpg"].iloc[0], bout["opponent_dpg"].iloc[0]

    real_periods_seen = [real_period(p) for p in bout["period"]]
    last_real_period = max(real_periods_seen, key=lambda p: PERIOD_START_ELAPSED[p])
    ends_in_overtime = last_real_period in OVERTIME_PERIODS
    # provisional length (nominal end of the last period reached) -- only
    # used as the interpolation anchor below; an OT-ending bout's TRUE
    # length is finalized afterward from its own actual last event.
    provisional_length = PERIOD_START_ELAPSED[last_real_period] + PERIOD_LENGTH_SEC[last_real_period]

    # elapsed_sec: a boundary event (choice/defer, or period label "choice_N")
    # has a genuinely-known timestamp of 0 remaining -- but a missing
    # timestamp on a real action (stalling, penalty, riding_time, etc, ~2-4%
    # of rows) is NOT actually "period just started"; treating it that way
    # snaps the clock backward mid-bout and makes the trace double back on
    # itself (found 2026-09-13 on the 184lb final). Instead, leave those
    # unresolved and interpolate between the nearest KNOWN elapsed times in
    # this bout (anchored at 0 and the provisional length at the edges),
    # which keeps the clock monotonic and each event roughly where it
    # actually falls.
    is_boundary = bout["period"].astype(str).str.startswith("choice_") | bout["action"].isin(["choice", "defer"])
    raw_elapsed = [
        elapsed_seconds(p, t) if (b or not pd.isna(t)) else float("nan")
        for p, t, b in zip(bout["period"], bout["time_remaining_in_period_sec"], is_boundary)
    ]
    anchored = pd.concat([pd.Series([0.0]), pd.Series(raw_elapsed, dtype="float64"), pd.Series([float(provisional_length)])], ignore_index=True)
    bout["elapsed_sec"] = anchored.interpolate(method="linear", limit_direction="both").iloc[1:-1].reset_index(drop=True)

    # Now that every row has a real elapsed_sec, finalize match_length_sec:
    # regulation bouts keep the provisional (nominal period end) value, but
    # an OT bout is sudden-victory -- the match ends at its own last event,
    # not at that period's nominal length (see wrestling_clock.py).
    match_length_sec = bout_match_length_sec(last_real_period, float(bout["elapsed_sec"].iloc[-1]))

    def match_frac(t):
        return max(0.0, min(1.0, 1 - t / match_length_sec))

    # events_out: the DISCRETE scoring/position events only (for dots + tooltips).
    # trace_out: the DENSE resampled curve (events + interpolated points) that
    # accounts for the clock and riding time moving between events (for the line).
    events_out = [{
        "event_index": 0, "period": "1", "elapsed_sec": 0, "action": "match_start",
        "subject_score": 0, "opponent_score": 0, "subject_position": "neutral",
        "win_prob": predict_row(model, 0, match_frac(0), dpg_s, dpg_o, 0.0, "1", "neutral", False, False, False, False),
    }]
    for _, row in bout.iterrows():
        e = {
            "event_index": int(row["event_index"]), "period": row["period"], "elapsed_sec": row["elapsed_sec"],
            "action": row["action"], "subject_score": int(row["subject_score"]), "opponent_score": int(row["opponent_score"]),
            "subject_position": row["subject_position"],
            "actor_is_subject": bool(row["actor_is_subject"]) if pd.notna(row["actor_is_subject"]) else None,
            "raw_text": row["raw_text"] if pd.notna(row["raw_text"]) else None,
            "score_diff": float(row["score_diff"]), "stall_s": bool(row["subject_stalling_warned"]),
            "stall_o": bool(row["opponent_stalling_warned"]), "flip_win": bool(row["subject_is_flip_winner_filled"]),
            "riding_net_at_event": float(row["riding_time_net_sec"]),
        }
        seg_period = real_period(row["period"])
        e["win_prob"] = predict_row(
            model, e["score_diff"], match_frac(e["elapsed_sec"]), dpg_s, dpg_o, e["riding_net_at_event"],
            seg_period, e["subject_position"] or "unknown", e["stall_s"], e["stall_o"], e["flip_win"],
            e["riding_net_at_event"] >= 60,
        )
        events_out.append(e)

    # Sudden-victory rule override: the match is DEFINITIONALLY over the
    # instant the bout's final event happens in overtime -- not a model
    # prediction, however well-calibrated the model is for every other state.
    if ends_in_overtime:
        events_out[-1]["win_prob"] = 1.0

    # who actually scored each event, for display (e.g. "score went 1-1 to
    # 2-1" on its own doesn't say what happened) -- derived from which side's
    # score changed, not from the row's own `points` field, since sign there
    # is easy to get backwards across the winner/loser-perspective flip.
    for i in range(1, len(events_out)):
        prev, cur = events_out[i - 1], events_out[i]
        d_subject = cur["subject_score"] - prev["subject_score"]
        d_opponent = cur["opponent_score"] - prev["opponent_score"]
        if d_subject > 0:
            cur["scorer"], cur["score_points"] = subject, d_subject
        elif d_opponent > 0:
            cur["scorer"], cur["score_points"] = opponent_name, d_opponent
        else:
            cur["scorer"], cur["score_points"] = None, 0
    events_out[0]["scorer"], events_out[0]["score_points"] = None, 0

    trace_out = []
    for i in range(len(events_out) - 1):
        a, b = events_out[i], events_out[i + 1]
        t0, t1 = a["elapsed_sec"], b["elapsed_sec"]
        seg_period = real_period(a["period"])
        position = a["subject_position"] or "unknown"
        accrual = RIDING_ACCRUAL.get(position, 0.0)
        score_diff = a.get("score_diff", 0.0)
        riding_base = a.get("riding_net_at_event", 0.0)
        stall_s, stall_o, flip_win = a.get("stall_s", False), a.get("stall_o", False), a.get("flip_win", False)

        trace_out.append({"elapsed_sec": t0, "win_prob": a["win_prob"]})
        t = t0 + RESAMPLE_SEC
        while t < t1:
            riding_net = riding_base + accrual * (t - t0)
            p = predict_row(model, score_diff, match_frac(t), dpg_s, dpg_o, riding_net, seg_period, position,
                             stall_s, stall_o, flip_win, riding_net >= 60)
            trace_out.append({"elapsed_sec": t, "win_prob": p})
            t += RESAMPLE_SEC
    trace_out.append({"elapsed_sec": events_out[-1]["elapsed_sec"], "win_prob": events_out[-1]["win_prob"]})

    # extend the trace to the buzzer -- a no-op for an OT-decided bout, since
    # match_length_sec now equals its own last event's elapsed_sec exactly.
    last = events_out[-1]
    if match_length_sec > last["elapsed_sec"]:
        seg_period = real_period(last["period"])
        position = last["subject_position"] or "unknown"
        accrual = RIDING_ACCRUAL.get(position, 0.0)
        score_diff = last.get("score_diff", 0.0)
        riding_base = last.get("riding_net_at_event", 0.0)
        stall_s, stall_o, flip_win = last.get("stall_s", False), last.get("stall_o", False), last.get("flip_win", False)
        t0 = last["elapsed_sec"]
        t = t0 + RESAMPLE_SEC
        while t <= match_length_sec:
            riding_net = riding_base + accrual * (t - t0)
            p = predict_row(model, score_diff, match_frac(t), dpg_s, dpg_o, riding_net, seg_period, position,
                             stall_s, stall_o, flip_win, riding_net >= 60)
            trace_out.append({"elapsed_sec": t, "win_prob": p})
            t += RESAMPLE_SEC

    # Regulation buzzer-certainty override, same rule-based logic as the OT
    # override above: if the clock has fully expired with a nonzero lead,
    # the outcome is decided by definition -- not a matter of the model's
    # confidence. NOTE this only guarantees the exact final instant; the
    # model's approach to that point in the closing seconds still has a
    # real, separate calibration gap for narrow (1-point) leads specifically
    # that this does NOT fix (found 2026-09-14 on the 184lb final: the
    # empirical win rate for a 1-point lead with <3% of the match left is
    # ~99%, same as a 2- or 3-point lead at that point, but the model
    # predicts only ~80% for 1 point vs ~98% for 2-3 points there --
    # flagged as a follow-up modeling task, not patched here).
    if not ends_in_overtime and events_out[-1]["score_diff"] != 0:
        trace_out[-1]["win_prob"] = 1.0

    for e in events_out:
        for k in ("score_diff", "stall_s", "stall_o", "flip_win", "riding_net_at_event"):
            e.pop(k, None)

    return {
        "tournament": tournament, "year": year, "weight": weight,
        "subject_name": subject, "opponent_name": opponent_name,
        "final_subject_score": events_out[-1]["subject_score"],
        "final_opponent_score": events_out[-1]["opponent_score"],
        "match_length_sec": match_length_sec,
        "period_starts": PERIOD_START_ELAPSED,
        "events": events_out,
        "trace": trace_out,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tournament", default="ncaa")
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--weight", type=int, required=True)
    ap.add_argument("--bout-number", type=int, required=True)
    ap.add_argument("--subject", required=True, help="Wrestler name to chart probability FOR")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    df = pd.read_csv(PBP_DIR / "training_rows.csv", low_memory=False)
    model = joblib.load(MODEL_DIR / "baseline_logreg.joblib")
    out = compute_trace(df, model, args.tournament, args.year, args.weight, args.bout_number, args.subject)

    out_path = Path(args.out) if args.out else PBP_DIR / f"match_win_prob_{args.tournament}_{args.year}_{args.weight}.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"[DONE] wrote {out_path} ({len(out['events'])} events, {len(out['trace'])} trace points)")
    for e in out["events"]:
        print(f"  {e['period']:>8} t={e['elapsed_sec']:5.0f}s  {e['action']:12s} {e['subject_score']}-{e['opponent_score']}  P(win)={e['win_prob']*100:5.1f}%")


if __name__ == "__main__":
    main()
