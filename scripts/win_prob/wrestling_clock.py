#!/usr/bin/env python3
"""
Shared wrestling-clock constants/helpers for the win-probability pipeline.
Pulled out of fit_baseline_model.py and compute_match_win_prob.py (2026-09-14)
after the same period-boundary bug (see elapsed_seconds below) had to be
fixed in both places independently -- one shared module means it can't
silently diverge between training and chart-time code again.

Regulation periods (1/2/3) run their full clock and are decided at the
buzzer if not decided sooner. EVERY NCAA overtime period (OT1 "SV-1", OT2
"TB-1", OT3 "TB-2"/UTB) is a sudden-victory/first-to-decide format: the
match ends the INSTANT a deciding event happens, not at that period's
nominal length. Treating overtime like a fixed-length period was a second,
separate bug (found 2026-09-14 on the 149lb final: Valencia's OT1 takedown
was followed by ~90 more seconds of a phantom continuation, timed as if OT1
ran its full 2 minutes and could even reach a fictional TB period) --
`bout_match_length_sec` below is what actually decides how long a bout's
own trace/features run, per period type.
"""

PERIOD_LENGTH_SEC = {"1": 180, "2": 120, "3": 120, "OT1": 120, "OT2": 30, "OT3": 30}
PERIOD_ORDER = ["1", "2", "3", "OT1", "OT2", "OT3"]
OVERTIME_PERIODS = {"OT1", "OT2", "OT3"}

PERIOD_START_ELAPSED = {}
_running = 0
for _p in PERIOD_ORDER:
    PERIOD_START_ELAPSED[_p] = _running
    _running += PERIOD_LENGTH_SEC[_p]

# "choice_N" is the coin-flip/position-choice boundary made at the END of
# period N, i.e. the instant that STARTS period N+1 -- not a moment inside
# period N itself.
NEXT_PERIOD = dict(zip(PERIOD_ORDER, PERIOD_ORDER[1:]))


def period_base(period_label: str) -> str:
    """choice_1/choice_2/choice_3 are boundary markers tied to periods 1/2/3."""
    if period_label.startswith("choice_"):
        return period_label.split("_")[1]
    return period_label


def real_period(period_label: str) -> str:
    """The actual regulation/OT period active going FORWARD from this row --
    for a boundary row (choice_N/defer), that's period N+1, not N."""
    if period_label.startswith("choice_"):
        return NEXT_PERIOD.get(period_base(period_label), period_base(period_label))
    return period_label


def elapsed_seconds(period_label: str, time_remaining) -> float:
    """Elapsed seconds from the opening whistle. NaN time_remaining is only
    meaningful here for a TRUE boundary row (period label starts with
    "choice_") -- callers must handle a missing timestamp on a real action
    (a scrape gap, not a boundary) themselves; see compute_match_win_prob.py
    for the interpolation this needs."""
    if period_label.startswith("choice_"):
        return PERIOD_START_ELAPSED.get(real_period(period_label), 0)
    start = PERIOD_START_ELAPSED.get(period_label, 0)
    length = PERIOD_LENGTH_SEC.get(period_label, 0)
    if time_remaining is None:
        return start
    try:
        if time_remaining != time_remaining:  # NaN check without importing pandas/numpy
            return start
    except TypeError:
        pass
    return start + (length - float(time_remaining))


def bout_match_length_sec(last_real_period: str, last_event_elapsed_sec: float) -> float:
    """How long this bout's own clock actually runs, given the last (real)
    period it reached and the elapsed time of its final recorded event.
    Regulation (1/2/3): the match runs the full period -- decided at the
    buzzer if not sooner. Overtime (OT1/OT2/OT3): sudden-victory format --
    the match ends the instant the final event happens, not at that
    period's nominal length."""
    if last_real_period in OVERTIME_PERIODS:
        return last_event_elapsed_sec
    return PERIOD_START_ELAPSED[last_real_period] + PERIOD_LENGTH_SEC[last_real_period]
