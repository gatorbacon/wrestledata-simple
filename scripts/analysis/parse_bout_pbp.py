#!/usr/bin/env python3
"""
Parse raw NCAA/conference bout-detail play-by-play (data/{year}/{tournament}
-tourney/bout_detail/{weight}.json, see docs/matsavant.md's "NCAA Bout-Level
Play-by-Play" section) into clean per-event rows suitable for modeling: a
live win-probability / in-match value-added model, analogous to NFL EPA or
DataGolf's Strokes Gained.

Point values and side semantics below were calibrated empirically against
the bouts' own `period_points` totals (2026-09-11), not assumed from rules
knowledge alone -- see the isolated-period cross-check this was built from.
Key findings:
  - `side` uniformly means "who receives these points" for every action
    type, including Penalty (confirmed against 10 isolated cases) -- there
    is no action where `side` means "who committed the act" and the
    opponent scores.
  - Stalling and Caution are always 0 points by themselves (confirmed
    against 341 isolated periods) -- procedural notifications, not scores.
  - Point values are embedded in the text itself where they vary by scoring
    era: "Takedown 3" (post-2023-24 3-point-takedown rule) vs bare
    "Takedown" (defaults to 2, pre-2023-24) -- no need to look up the
    season's rule era separately. Same for "N Nearfall" (leading number =
    points; a bare "Nearfall" with no number never appears in the data).

Two rare event types were resolved empirically the same way (2026-09-11),
by checking whether including them makes every previously-mismatched
period's total reconcile exactly, rather than guessing:
  - "+2"/"+4"/"-1"/"+1" scorekeeper-style adjustments (6 occurrences total
    across 3,720 NCAA bouts): these ARE real signed point deltas -- every
    one of the 5 bouts that mismatched period_points before this was
    accounted for reconciled exactly once its adjustment event's signed
    value was added to that side's score. Applied directly to the running
    score now; still flagged via needs_review=True so they're easy to spot
    and audit later if the model behaves oddly around one.
  - "Misconduct" (1 occurrence total): 0 points -- the one bout containing
    it only reconciles against period_points with Misconduct contributing
    nothing (unsportsmanlike-conduct cards don't carry individual-bout
    score in this data; they may affect team scoring elsewhere, out of
    scope here).

Output: one row per event across every bout, with running score and
position state computed as of that event -- data/pbp/events.jsonl (one
JSON object per line). Position state is tracked as which side (winner/
loser) currently holds top/bottom, or "neutral"; it's the same wrestler
identity throughout since the schema is winner/loser-relative, not
left/right-relative (already resolved at scrape time -- see the
winner/loser column-order gotcha in docs/matsavant.md).

Usage:
    python scripts/analysis/parse_bout_pbp.py
    python scripts/analysis/parse_bout_pbp.py --tournament ncaa --years 2021-2026
    python scripts/analysis/parse_bout_pbp.py --tournament big_ten --years 2024-2026
"""

import argparse
import glob
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = DATA_DIR / "pbp"

TIME_RE = re.compile(r"\((\d+):(\d+)\)\s*$")

# Bare action name -> default points (used only when the text has no
# embedded number, e.g. "Takedown" pre-2023-24, or never varies, e.g. "Escape").
DEFAULT_POINTS = {
    "escape": 1,
    "reversal": 2,
    "takedown": 2,  # bare "Takedown" (no trailing number) = pre-2023-24 era
    "riding time": 1,
}

# Position choice/declaration text (Choice N columns) -> normalized state.
POSITION_CHOICES = {"bottom": "bottom", "top": "top", "neutral": "neutral"}
# "Defer" is a choice action (deferring the choice to the next period), not
# a position itself -- it doesn't set anyone's position.

NON_SCORING = {"stalling", "caution"}

# Official period lengths in seconds -- needed to reconstruct riding time
# (see extract_choices/parse_bout below): a control segment that runs to
# the end of a period without an interrupting escape/reversal earns
# (this period's full length - 0), not "however many seconds we happened
# to see a timestamp for." Regulation lengths (180/120/120) are certain;
# OT lengths reflect the CURRENT rule set only and may not be accurate for
# older seasons whose overtime format differed (see docs/matsavant.md
# Known Gotcha #15) -- riding time reconstruction in OT should be treated
# as lower-confidence than in regulation until that's resolved.
PERIOD_LENGTH_SEC = {"1": 180, "2": 120, "3": 120, "OT1": 120, "OT2": 30, "OT3": 30}


def strip_time(text: str) -> tuple[str, int | None]:
    """Splits 'Takedown 3 (0:47)' into ('Takedown 3', 47) or
    ('Escape', None) if there's no embedded clock time."""
    m = TIME_RE.search(text)
    if not m:
        return text.strip(), None
    minutes, seconds = int(m.group(1)), int(m.group(2))
    base = text[: m.start()].strip()
    return base, minutes * 60 + seconds


def parse_event_text(base: str) -> dict:
    """
    Returns {"action": str, "points": int|None, "is_position_choice": bool,
    "position": str|None, "needs_review": bool}.
    `points` is None for position choices and for the rare unhandled types
    (Misconduct, +N/-N adjustments) that are deliberately not guessed at.
    """
    lower = base.lower().strip()

    if lower in POSITION_CHOICES:
        return {"action": "choice", "points": None, "position": POSITION_CHOICES[lower], "needs_review": False}
    if lower == "defer":
        return {"action": "defer", "points": None, "position": None, "needs_review": False}
    if lower in NON_SCORING:
        return {"action": lower, "points": 0, "position": None, "needs_review": False}

    # "Takedown 3" / "Takedown" (bare = 2, pre-2023-24)
    m = re.match(r"^takedown\s*(\d+)?$", lower)
    if m:
        pts = int(m.group(1)) if m.group(1) else DEFAULT_POINTS["takedown"]
        return {"action": "takedown", "points": pts, "position": None, "needs_review": False}

    # "N Nearfall" -- leading number always present in the data
    m = re.match(r"^(\d+)\s*nearfall$", lower)
    if m:
        return {"action": "near_fall", "points": int(m.group(1)), "position": None, "needs_review": False}

    # "Penalty N" -- awarded TO `side`, confirmed empirically (see module docstring)
    m = re.match(r"^penalty\s*(\d+)$", lower)
    if m:
        return {"action": "penalty", "points": int(m.group(1)), "position": None, "needs_review": False}

    if lower == "escape":
        return {"action": "escape", "points": DEFAULT_POINTS["escape"], "position": None, "needs_review": False}
    if lower == "reversal":
        return {"action": "reversal", "points": DEFAULT_POINTS["reversal"], "position": None, "needs_review": False}
    if lower == "riding time":
        return {"action": "riding_time", "points": DEFAULT_POINTS["riding time"], "position": None, "needs_review": False}

    if lower == "misconduct":
        return {"action": "misconduct", "points": 0, "position": None, "needs_review": True}

    # Scorekeeper-style adjustment (e.g. a review overturn) -- real signed
    # point delta, confirmed empirically (see module docstring). Flagged
    # for visibility since it's rare, but applied to the score like any
    # other scoring event.
    m = re.match(r"^([+-])(\d+)$", base.strip())
    if m:
        signed = int(m.group(2)) * (1 if m.group(1) == "+" else -1)
        return {"action": "adjustment", "points": signed, "position": None, "needs_review": True}

    return {"action": "unknown", "points": None, "position": None, "needs_review": True}


def normalize_period_label(label: str) -> tuple[str, int]:
    """'Period 2' -> ('2', 2); 'Overtime 1' -> ('OT1', 4); 'Choice 1' -> ('choice_1', 0)
    (choice columns are position-setting only, ordered before the period they precede)."""
    m = re.match(r"^Period (\d+)$", label)
    if m:
        n = int(m.group(1))
        return str(n), n
    m = re.match(r"^Overtime (\d+)$", label)
    if m:
        n = int(m.group(1))
        return f"OT{n}", 3 + n
    m = re.match(r"^Choice (\d+)$", label)
    if m:
        n = int(m.group(1))
        return f"choice_{n}", n - 1  # sorts just before period n
    return label, 99


def extract_choices(bout: dict) -> dict:
    """
    Derives who won the pre-match disk flip and what each subsequent choice
    point resolved to, from the "Choice N" columns -- e.g. flip_winner
    deferring in Choice 1 so the opponent has to pick a position for period
    2, with flip_winner then getting first pick again for period 3 (Choice
    2). This is a genuinely separate state signal from position_after: the
    right to choose is committed once (at the flip) and its consequences
    unfold over the rest of the bout, so it's worth its own field rather
    than relying on the model to infer it purely from position sequences.

    Confirmed from real data (2026-09-12): the flip winner's action always
    appears FIRST within "Choice 1" -- either their own direct position
    pick, or a "Defer", immediately followed in the same column by the
    opponent's resulting (forced) pick. Same first-mover pattern holds for
    later Choice columns (Choice 2 = period 3's decision, Choice 3 = rare
    OT-related). Do not assume which choice is "better" here (e.g. bottom
    vs neutral) -- that's for the model to learn, not to encode.
    """
    result = {"flip_winner": None}
    for col in bout.get("columns", []):
        m = re.match(r"^Choice (\d+)$", col["label"])
        if not m:
            continue
        idx = int(m.group(1))
        events = col.get("events", [])
        if not events:
            continue
        first = events[0]
        if first["text"].strip().lower() == "defer":
            deferred = True
            # Rare scorekeeper quirk (2026-09-12): an occasional double
            # "Defer" gets logged before the real choice (0 occurrences
            # affect scoring -- always 0-0 periods). Skip any number of
            # leading defers and take the first actual position choice.
            resolved = next((e for e in events[1:] if e["text"].strip().lower() != "defer"), None)
            chooser = resolved["side"] if resolved else None
            choice = strip_time(resolved["text"])[0].lower() if resolved else None
        else:
            chooser = first["side"]
            choice = strip_time(first["text"])[0].lower()
            deferred = False
        if idx == 1:
            result["flip_winner"] = first["side"]
        result[f"choice_{idx}_chooser"] = chooser
        result[f"choice_{idx}_choice"] = choice
        result[f"choice_{idx}_deferred"] = deferred
    return result


RIDING_NOTE_RE = re.compile(r"riding time:\s*(\d+):(\d+)(?:\s*\((\d+):(\d+)\))?", re.IGNORECASE)


def parse_bout(bout: dict, meta: dict) -> tuple[list[dict], list[dict]]:
    """Returns a list of event rows for one bout, in chronological order,
    with running score/position state computed as of each event.

    Riding time is reconstructed from position transitions (takedown/
    reversal start a control segment, escape ends it, a period running out
    while still in control credits the rest of that period) rather than
    read from the scorekeeper's own "green/red riding time: M:SS" notes,
    because those notes identify wrestlers by raw display color (green/
    red), and color isn't resolved to winner/loser anywhere in this data
    (only left/right *columns* are, via the headline match at scrape time
    -- see the winner/loser column-order gotcha in docs/matsavant.md) --
    resolving color would require re-scraping. This turns out not to
    matter for validation: those notes report the NET riding-time
    advantage (whichever side is currently ahead, cumulative-minus-
    cumulative), not either side's raw individual total (confirmed
    empirically, 2026-09-12 -- see check_riding_time's docstring), so
    checking abs(computed_winner - computed_loser) against the note's
    value validates the reconstruction without ever needing to know which
    color said it. Returns (rows, riding_checks) -- see check_riding_time,
    which aggregates riding_checks across bouts, for the match rate
    (95.6% within 5 seconds across all 3,688 NCAA bouts 2021-2026).

    riding_checks entries are computed INLINE, interleaved into the same
    chronological event processing as everything else (not a separate
    nearest-timestamp lookup after the fact) -- an earlier version matched
    each note to whichever event row happened to be nearest in time, which
    silently produced nonsense when a period's first real scored event
    didn't occur until much later than a note's checkpoint (e.g. a note at
    "period start" matched against a row from an event 90 seconds later,
    comparing against a value that already had 90 more seconds of riding
    baked in). Notes are flushed against the exact live state at their own
    checkpoint time, in the same descending-time order they're logged in."""
    rows = []
    riding_checks = []
    score = {"winner": 0, "loser": 0}
    position = {"winner": None, "loser": None}  # "top" | "bottom" | "neutral" | None (not yet established)
    riding_time = {"winner": 0.0, "loser": 0.0}  # cumulative seconds controlling top, whole match
    current_rider = None  # "winner" | "loser" | None (neutral / not yet established)
    control_start_remaining = None  # time_remaining_in_period_sec when the current control segment began
    control_start_estimated = False  # True if control_start_remaining came from the last_known_remaining
    # fallback (missing timestamp) rather than a real one -- see close_control's period-end handling below.
    # Cumulative stalling calls AGAINST each side (the side on a "stalling"
    # event is who was called, not a beneficiary -- unlike every scoring
    # action). Progressive penalty per NCAA rules: 1st = warning (0 pts,
    # already correctly scored that way), 2nd = 1pt to opponent, 3rd =
    # another 1pt, 4th = 2pts, 5th = automatic DQ loss. The resulting point
    # award (if any) already appears as a separate same-timestamp "Penalty
    # N" event on the opponent's side and is scored correctly by that path
    # -- this counter exists purely so a leading indicator ("this wrestler
    # is 1 stalling call from a penalty / 2 from DQ") is available as a
    # state feature, independent of points on the board.
    stalling_count = {"winner": 0, "loser": 0}
    event_index = 0
    prev_was_timed_period = False
    # Best known clock reading in the CURRENT period, for the ~2.6% of
    # takedowns/reversals with no embedded timestamp (2026-09-12 bug fix):
    # falling back to None here used to permanently sever control_start_
    # remaining, silently losing every subsequent ride's credit for the
    # rest of the bout. Falling back to the last known reading instead
    # treats the untimed event as instantaneous (0-duration) rather than
    # losing tracking entirely -- a small approximation, not a data loss.
    last_known_remaining = None

    def close_control(end_remaining, is_period_end=False):
        """Credits the current rider (if any) for the segment ending now,
        then clears control state. end_remaining=0 means "ran to the end
        of the period without being interrupted".

        is_period_end=True (2026-09-12 bug fix) additionally skips crediting
        when the segment's START was itself estimated (see
        control_start_estimated/last_known_remaining) -- crediting "start
        estimate to 0" assumes the untimed event happened at the EARLIEST
        possible moment, which is the worst-case-largest guess for exactly
        the span we're least sure about (up to the rest of a 120s period).
        A normal close (a later event with its OWN real timestamp actually
        ends the ride) doesn't have this problem -- the end boundary is
        real even if the start was approximated by a few seconds -- so only
        the period-end path needs this guard."""
        nonlocal current_rider, control_start_remaining, control_start_estimated
        if (current_rider is not None and control_start_remaining is not None and end_remaining is not None
                and not (is_period_end and control_start_estimated)):
            riding_time[current_rider] += max(control_start_remaining - end_remaining, 0)
        current_rider = None
        control_start_remaining = None
        control_start_estimated = False

    def live_at(as_of_remaining):
        """Riding time projected to a specific moment in the CURRENT
        period, without mutating persistent state -- used both for each
        row's live snapshot and for validating notes against the exact
        state at their own checkpoint."""
        snap = dict(riding_time)
        if current_rider is not None and control_start_remaining is not None and as_of_remaining is not None:
            snap[current_rider] += max(control_start_remaining - as_of_remaining, 0)
        return snap

    def flush_notes(note_queue, threshold_remaining, period_label):
        """Pops and validates every pending note whose checkpoint occurred
        at or before threshold_remaining (higher remaining = earlier,
        since the clock counts down) -- called before an event with a
        known time, and once more at period end. threshold_remaining=None
        (an event with no timestamp) flushes nothing; those notes wait for
        the next safe checkpoint instead of being matched to a guess."""
        if threshold_remaining is None:
            return
        while note_queue and note_queue[0][0] >= threshold_remaining:
            checkpoint, reported = note_queue.pop(0)
            snap = live_at(checkpoint)
            riding_checks.append({
                "period": period_label, "checkpoint_sec": checkpoint, "reported_sec": reported,
                "computed_winner": round(snap["winner"], 1), "computed_loser": round(snap["loser"], 1),
            })

    for col in bout.get("columns", []):
        period_label, period_order = normalize_period_label(col["label"])
        is_timed_period = period_label in PERIOD_LENGTH_SEC

        if prev_was_timed_period and not is_timed_period:
            # Leaving a timed period for a Choice column: whoever was still
            # riding when it ended (no interrupting escape) gets credited
            # for the rest of it. Position itself is NOT reset here --
            # riding control specifically ends because the next period's
            # position is always freshly declared by the upcoming choice,
            # not carried over automatically.
            close_control(0, is_period_end=True)
        note_queue = []
        if is_timed_period:
            # A fresh choice (or period 1's/OT1's neutral default) carries
            # into this period's control_start_remaining at full length --
            # always exact, never an estimate.
            control_start_remaining = PERIOD_LENGTH_SEC[period_label] if current_rider else None
            control_start_estimated = False
            last_known_remaining = PERIOD_LENGTH_SEC[period_label]

            for note in col.get("notes", []):
                m = RIDING_NOTE_RE.search(note)
                if m and m.group(3) is not None:
                    checkpoint = int(m.group(3)) * 60 + int(m.group(4))
                    reported = int(m.group(1)) * 60 + int(m.group(2))
                    note_queue.append((checkpoint, reported))
            note_queue.sort(key=lambda x: -x[0])
            flush_notes(note_queue, PERIOD_LENGTH_SEC[period_label], period_label)

        for ev in col.get("events", []):
            side = ev["side"]
            other = "loser" if side == "winner" else "winner"
            base, time_remaining = strip_time(ev["text"])
            parsed = parse_event_text(base)
            event_index += 1
            # Fallback clock reading for this event if it has no embedded
            # timestamp -- see last_known_remaining note above.
            effective_remaining = time_remaining if time_remaining is not None else last_known_remaining
            if is_timed_period:
                flush_notes(note_queue, effective_remaining, period_label)

            if parsed["action"] == "choice":
                position[side] = parsed["position"]
                if parsed["position"] == "bottom":
                    position[other] = "top"
                    current_rider = other
                elif parsed["position"] == "top":
                    position[other] = "bottom"
                    current_rider = side
                elif parsed["position"] == "neutral":
                    position[other] = "neutral"
                    current_rider = None
            elif parsed["action"] == "takedown":
                position[side], position[other] = "top", "bottom"
                close_control(effective_remaining)
                current_rider, control_start_remaining = side, effective_remaining
                control_start_estimated = time_remaining is None
            elif parsed["action"] == "reversal":
                position[side], position[other] = "top", "bottom"
                close_control(effective_remaining)
                current_rider, control_start_remaining = side, effective_remaining
                control_start_estimated = time_remaining is None
            elif parsed["action"] == "escape":
                position[side], position[other] = "neutral", "neutral"
                close_control(effective_remaining)

            if time_remaining is not None:
                last_known_remaining = time_remaining

            if parsed["points"]:
                score[side] += parsed["points"]
            if parsed["action"] == "stalling":
                stalling_count[side] += 1

            # Live riding-time snapshot as of THIS event: riding_time[] only
            # updates when a control segment actually closes (see
            # close_control above), so an in-progress ride (e.g. a Stalling
            # call while someone's still riding) needs its partial elapsed
            # time added here too -- computed, not persisted, so the still-
            # open segment keeps accruing correctly for later events. Uses
            # this event's own (possibly missing) timestamp, not the
            # fallback-adjusted one, so a row with no timestamp honestly
            # doesn't claim more precision than it has.
            live_riding = live_at(time_remaining)

            rows.append({
                **meta,
                "bout_number": bout["bout_number"],
                "winner_name": bout["winner"]["name"], "winner_team": bout["winner"]["team"],
                "loser_name": bout["loser"]["name"], "loser_team": bout["loser"]["team"],
                "final_score": f"{bout['winner']['score']}-{bout['loser']['score']}",
                "event_index": event_index,
                "period": period_label, "period_order": period_order,
                "time_remaining_in_period_sec": time_remaining,
                "side": side,
                "raw_text": ev["text"],
                "action": parsed["action"],
                "points": parsed["points"],
                "needs_review": parsed["needs_review"],
                "score_winner_after": score["winner"], "score_loser_after": score["loser"],
                "position_winner_after": position["winner"], "position_loser_after": position["loser"],
                "stalling_count_winner_after": stalling_count["winner"],
                "stalling_count_loser_after": stalling_count["loser"],
                # Primary state feature for modeling: has this wrestler been
                # called at all yet (not the exact count). A first stalling
                # call forces a real strategic shift -- they can't risk a
                # second -- independent of how many further calls follow.
                # Penalty points can't be tied 1:1 to call number anyway
                # (penalties have other causes too, e.g. locked hands), and
                # a stalling DQ (5th call) is rare enough not to be worth
                # modeling as a likely outcome -- so the count itself is
                # kept above for audit, but this bool is what the model uses.
                "stalling_warned_winner_after": stalling_count["winner"] > 0,
                "stalling_warned_loser_after": stalling_count["loser"] > 0,
                "riding_time_winner_after": round(live_riding["winner"], 1),
                "riding_time_loser_after": round(live_riding["loser"], 1),
            })

        if is_timed_period:
            # Any notes left over occurred after the last event but before
            # the period ended (or the period had no events at all) --
            # flush against whatever state currently stands.
            flush_notes(note_queue, 0, period_label)

        prev_was_timed_period = is_timed_period

    return rows, riding_checks


def validate_bout(bout: dict, rows: list[dict]) -> list[str]:
    """Cross-checks parsed period point totals against the bout's own
    period_points -- the only ground truth available. Returns a list of
    mismatch descriptions (empty if everything reconciles)."""
    problems = []
    by_period = {}
    for r in rows:
        by_period.setdefault((r["period"], r["period_order"]), []).append(r)

    for col in bout.get("columns", []):
        period_label, period_order = normalize_period_label(col["label"])
        pp = col.get("period_points")
        if pp is None:
            continue
        period_rows = by_period.get((period_label, period_order), [])
        computed_w = sum(r["points"] or 0 for r in period_rows if r["side"] == "winner")
        computed_l = sum(r["points"] or 0 for r in period_rows if r["side"] == "loser")
        if computed_w != pp["winner"] or computed_l != pp["loser"]:
            problems.append(
                f"{period_label}: computed w={computed_w} l={computed_l} vs actual w={pp['winner']} l={pp['loser']}"
            )
    return problems


def check_riding_time(riding_checks: list[dict], tolerance: int = 5) -> tuple[int, int]:
    """Aggregates the riding_checks parse_bout already computed inline
    (see its docstring) into a match rate against the scorekeeper's own
    '{color} riding time: M:SS (M:SS)' notes.

    These notes report the NET riding-time advantage (whichever side is
    currently ahead, cumulative-minus-cumulative), not either side's raw
    individual total -- confirmed empirically (2026-09-12): comparing
    reported values against set membership on either raw side matched only
    ~52% with a heavy error tail, but comparing against
    abs(computed_winner - computed_loser) instead brought the median error
    to 1 second and 96% within 5 seconds across a full season's bouts. This
    also sidesteps ever needing to resolve which color is which side --
    the net is the same regardless of who's "ahead." Notes with no
    checkpoint time (~41% of riding-time notes) can't be pinned to a
    moment and are never included in riding_checks to begin with. A default
    5s tolerance (not 2s) reflects real measurement jitter between the
    scored-events stream and the separately-logged riding notes, both
    entered by a human scorekeeper in real time."""
    matched = sum(
        1 for c in riding_checks
        if abs(abs(c["computed_winner"] - c["computed_loser"]) - c["reported_sec"]) <= tolerance
    )
    return matched, len(riding_checks)


def iter_bout_files(tournament: str, years: list[int]):
    for year in years:
        pattern = DATA_DIR / str(year) / f"{tournament}-tourney" / "bout_detail" / "*.json"
        for f in sorted(glob.glob(str(pattern))):
            yield year, Path(f)


def main():
    parser = argparse.ArgumentParser(description="Parse raw bout-detail play-by-play into modeling-ready events")
    parser.add_argument("--tournament", type=str, default="ncaa",
                         help="Tournament key matching the {tournament}-tourney data dir (default: ncaa)")
    parser.add_argument("--years", type=str, default=None,
                         help="Year or range, e.g. '2026' or '2021-2026' (default: auto-detect all available)")
    args = parser.parse_args()

    if args.years:
        if "-" in args.years:
            start, end = args.years.split("-")
            years = list(range(int(start), int(end) + 1))
        else:
            years = [int(args.years)]
    else:
        years = sorted(
            int(p.name) for p in DATA_DIR.iterdir()
            if p.name.isdigit() and (p / f"{args.tournament}-tourney" / "bout_detail").exists()
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"events_{args.tournament}.jsonl"

    total_bouts = 0
    total_events = 0
    total_mismatches = 0
    review_events = 0
    riding_matched = 0
    riding_total = 0

    with open(out_path, "w") as out:
        for year, f in iter_bout_files(args.tournament, years):
            weight = int(f.stem)
            bouts = json.loads(f.read_text())
            for bout in bouts:
                if not bout.get("columns"):
                    continue  # bye or 0-0 walkover, no PBP to parse
                meta = {
                    "tournament": args.tournament, "year": year, "weight": weight,
                    "round": bout.get("round"), "bracket": bout.get("bracket"),
                    "match_id": bout.get("match_id"),
                    **extract_choices(bout),
                }
                rows, riding_checks = parse_bout(bout, meta)
                problems = validate_bout(bout, rows)
                if problems:
                    total_mismatches += 1
                    print(f"[MISMATCH] {year} {args.tournament} {weight} bout {bout['bout_number']} "
                          f"({bout['winner']['name']} def. {bout['loser']['name']}): {'; '.join(problems)}")
                m, t = check_riding_time(riding_checks)
                riding_matched += m
                riding_total += t
                for r in rows:
                    r["period_point_mismatch"] = bool(problems)
                    out.write(json.dumps(r) + "\n")
                    total_events += 1
                    if r["needs_review"]:
                        review_events += 1
                total_bouts += 1

    print(f"\n[DONE] {total_bouts} bouts, {total_events} events -> {out_path}")
    print(f"  {total_mismatches} bouts with a period-point mismatch (check above)")
    print(f"  {review_events} events flagged needs_review (Misconduct / +N-N adjustments / truly unrecognized text)")
    if riding_total:
        print(f"  Riding time reconstruction: {riding_matched}/{riding_total} ({riding_matched/riding_total:.1%}) "
              f"matched the scorekeeper's own checkpointed notes")


if __name__ == "__main__":
    main()
