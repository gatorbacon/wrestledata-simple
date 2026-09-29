#!/usr/bin/env python3
"""
WPA step 2 -- event parsing and match-state reconstruction (spec Section 2; build order step 2).

Turns every bout's play-by-play into a timeline of match states, stored from the WINNER's side ("w"/"l"; step 3
builds both perspectives with wpa_common.perspective / mirror):

  data/wpa/states/{kind}_bouts.csv    one row per bout: ids, era, seeds, result, flags, reconstruction checks
  data/wpa/states/{kind}_events.csv   one row per event, with the full state BEFORE and AFTER it (b_* / a_*)
  data/wpa/states/{kind}_samples.csv  the state every 10 s of regulation time (t_rem 420, 410, ... 10) -- the
                                      fixed-cadence samples spec 3.1 asks for, so quiet stretches are represented
  data/wpa/reports/state_reconstruction.md   what was done and how well it checks out

State (spec Section 2): score (margin excludes the pending riding-time point), t_rem = seconds left in the whole
regulation match, period, position, choice, riding-time differential and the riding-time lock (wpa_common.rt_status).

Decisions applied (TJ, 2026-09-29, after the data audit):
  A  running riding time is rebuilt from position (who is on top, and for how long)
  B  an event with no clock (or a clock that contradicts its neighbours) is placed between its clocked neighbours
     using a placement fraction fitted per event type on clocked events (validated on held-out years in the
     report); the bout keeps a flag and the size of the gap so validation can check those bouts separately
  C  pre-2019 NCAA seeds 17-33 are stored as unseeded (strength_seed); the raw seed is kept too
  D  rules_era stored per bout (E1 2015, E2 2016-23, E3 2024-26); pooling is a step-3 decision
  F  a fall ends at its official time (NCAA results carry it in `score`, conference results in `time` -- the data
     audit wrongly said NCAA had none); injury defaults / DQs / a fall whose time is missing end at the last logged
     event

Choice timing: the NCAA disk toss happens at the START of period 2, so during period 1 nobody holds a choice yet
(choice = 'none'); the toss, the defer and the pick are their own events at the P1/P2 break. During period 2
choice = whoever picks for period 3; during period 3, none. This differs from the spec's wording ("during period 1,
choice = whoever will choose at the start of period 2"), which would put a coin flip that hasn't happened yet into
period-1 states. Flagged in the report.

Usage: .venv/bin/python scripts/wpa/build_states.py [--kind ncaa|conf|both]
"""
import argparse
import csv
import random
import re
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts/analysis"))
sys.path.insert(0, str(ROOT / "scripts/wpa"))
import parse_bout_pbp as P  # noqa: E402
import wpa_common as C      # noqa: E402

OUT_DIR = ROOT / "data/wpa/states"
REPORT = ROOT / "data/wpa/reports/state_reconstruction.md"
SAMPLE_TIMES = list(range(C.T_TOTAL, 0, -10))  # 420, 410, ... 10


def other(s):
    return "l" if s == "w" else "w"


def top_of(side):
    return "w_top" if side == "w" else "l_top"


def declared_pos(side, word):
    """'X: Bottom' = X on bottom; 'X: Top' = X on top; 'Neutral' = neutral."""
    if word == "neutral":
        return "neutral"
    return top_of(side) if word == "top" else top_of(other(side))


# ---------------------------------------------------------------------------------------------------------------
# Parsing a column
# ---------------------------------------------------------------------------------------------------------------
def parse_col(col, swapped):
    out = []
    for e in col.get("events", []):
        side = e.get("side")
        if side not in ("winner", "loser"):
            continue
        side = "w" if side == "winner" else "l"
        if swapped:
            side = other(side)
        base, clock = P.strip_time(e["text"])
        p = P.parse_event_text(base)
        out.append({"side": side, "text": e["text"], "action": p["action"], "points": p["points"] or 0,
                    "word": p.get("position"), "clock": clock})
    return out


def prev_class(evs, i):
    if i == 0:
        return "START"
    a = evs[i - 1]["action"]
    return "takedown" if a == "takedown" else "stall" if a in ("stalling", "caution") else "other"


def clean_clocks(evs, length):
    """Marks each event's time source: 'clock' (kept), 'rejected' (clock contradicts the others: outside the
    period, or not on the longest non-increasing run of clocks), 'missing'."""
    idx = [i for i, e in enumerate(evs) if e["clock"] is not None and e["clock"] <= length]
    n = len(idx)
    best, prv = [1] * n, [-1] * n
    for a in range(n):
        for b in range(a):
            if evs[idx[b]]["clock"] >= evs[idx[a]]["clock"] and best[b] + 1 > best[a]:
                best[a], prv[a] = best[b] + 1, b
    keep = set()
    if n:
        a = max(range(n), key=lambda k: best[k])
        while a != -1:
            keep.add(idx[a])
            a = prv[a]
    for i, e in enumerate(evs):
        e["src"] = "clock" if i in keep else ("rejected" if e["clock"] is not None else "missing")


def next_clock(evs, i):
    """(clock of the next kept clock after event i, or 0 = period end; 'CLK' / 'END')."""
    for j in range(i + 1, len(evs)):
        if evs[j]["src"] == "clock":
            return evs[j]["clock"], "CLK"
    return 0, "END"


def loo_rows(evs, length):
    """Leave-one-out rows for fitting the placement fractions: every kept clock, with its clocked neighbours."""
    rows = []
    for i, e in enumerate(evs):
        if e["src"] != "clock":
            continue
        prev = next((evs[j]["clock"] for j in range(i - 1, -1, -1) if evs[j]["src"] == "clock"), length)
        nxt, end = next_clock(evs, i)
        if prev > nxt:
            rows.append((e["action"], prev_class(evs, i), end, prev, nxt, e["clock"]))
    return rows


def fit_alpha(rows, min_n=40):
    """Placement fraction per (event type, previous-event class, next anchor = real clock or period end): the
    median of (prev - t) / (prev - next) over clocked events (the median minimises absolute error). Falls back to
    (type, previous), then type alone, then 0.5 (midpoint)."""
    g = defaultdict(list)
    for a, pc, end, p, n, t in rows:
        f = (p - t) / (p - n)
        g[(a, pc, end)].append(f)
        g[(a, pc)].append(f)
        g[(a, "*")].append(f)
    return {k: st.median(v) for k, v in g.items() if len(v) >= min_n}


def alpha_for(alpha, action, pc, end):
    return alpha.get((action, pc, end), alpha.get((action, pc), alpha.get((action, "*"), 0.5)))


def estimate_times(evs, length, alpha):
    """Sets e['t'] (clock, seconds left in the period) for every event. Unclocked / rejected events go between the
    previous placed time and the next kept clock, at the fitted fraction; a run of several unclocked events is
    placed one after another so order is kept. e['gap'] = width of the window it was placed in (0 = real clock)."""
    last = length
    for i, e in enumerate(evs):
        if e["src"] == "clock":
            e["t"], e["gap"] = e["clock"], 0
            last = e["t"]
            continue
        nxt, end = next_clock(evs, i)
        lo = min(nxt, last)
        a = alpha_for(alpha, e["action"], prev_class(evs, i), end)
        e["t"] = round(last - a * (last - lo))
        e["gap"] = last - lo
        last = e["t"]


# ---------------------------------------------------------------------------------------------------------------
# One bout
# ---------------------------------------------------------------------------------------------------------------
STATE_KEYS = ["t_rem", "period", "score_w", "score_l", "margin", "pos", "choice", "break_step", "rt_diff",
              "rt_status"]


def build_bout(rec, alpha, S):
    """Returns (bout_row, event_rows, sample_rows) or (bout_row, [], []) for an excluded bout."""
    m, y, sw_flag = rec["bout"], rec["year"], rec["swapped"]
    off = rec["official"]
    rtype = off.get("result_type") if off else None
    key = f"{rec['kind']}|{rec['tournament']}|{y}|{rec['weight']}|{m.get('bout_number')}"
    ws, ls = (m["loser"]["score"], m["winner"]["score"]) if sw_flag else (m["winner"]["score"], m["loser"]["score"])
    wseed = off.get("winner_seed") if off else None
    lseed = off.get("loser_seed") if off else None
    bout = {"bout_key": key, "kind": rec["kind"], "tournament": rec["tournament"], "year": y,
            "era": C.rules_era(y), "ot_rules": C.ot_rules(y), "weight": rec["weight"],
            "bout_number": m.get("bout_number"), "round": m.get("round"), "bracket": m.get("bracket"),
            "match_id": m.get("match_id"),
            "w_name": m["winner"]["name"], "w_team": m["winner"]["team"],
            "l_name": m["loser"]["name"], "l_team": m["loser"]["team"],
            "w_seed_raw": wseed, "l_seed_raw": lseed,
            "w_seed": C.strength_seed(y, wseed), "l_seed": C.strength_seed(y, lseed),
            "result_type": rtype, "final_w": ws, "final_l": ls, "swapped": sw_flag}
    cols = m.get("columns") or []
    rclass = C.result_class(rtype)
    if not cols:
        bout.update(included=False, exclude_reason="no play-by-play")
        return bout, [], []
    if rclass == "forfeit":
        bout.update(included=False, exclude_reason="forfeit")
        return bout, [], []

    reg, reg_notes, choice_cols, ot = {}, {}, {}, {}
    rt_logged, rt_logged_ot = [], []
    for c in cols:
        lab = c["label"]
        evs = parse_col(c, sw_flag)
        if lab.startswith("Period"):
            p = int(lab.split()[1])
            rt_logged += [e["side"] for e in evs if e["action"] == "riding_time"]
            reg[p] = [e for e in evs if e["action"] != "riding_time"]
            reg_notes[p] = c.get("notes", [])
        elif lab.startswith("Choice"):
            choice_cols[int(lab.split()[1])] = evs
        elif lab.startswith("Overtime"):
            n = int(lab.split()[1])
            rts = [e["side"] for e in evs if e["action"] == "riding_time"]
            # sudden victory has no riding time: a riding-time point logged under Overtime 1 is the regulation
            # point in the wrong column (e.g. 2023 141 bout 29, a 2-1 decision); tiebreaker riding time is real
            if n == 1:
                rt_logged += rts
            else:
                rt_logged_ot += rts
            evs = [e for e in evs if e["action"] != "riding_time"]
            if evs:  # an overtime column with nothing in it (notes only) is not evidence of overtime
                ot[n] = evs

    has_ot = bool(ot) or 3 in choice_cols or rclass == "overtime"
    result_inferred = rclass is None
    if rclass is None:
        rclass = "overtime" if has_ot else ("tech_fall" if abs(ws - ls) >= 15 else "decision")
    elif rclass == "decision" and has_ot:
        # official type says Dec but the bout went to overtime (e.g. 2026 197 bout 12, 2-2 after two tiebreakers)
        S["flag"]["official Dec/MD but play-by-play shows overtime (treated as overtime)"] += 1
        rclass = "overtime"
    # a tech fall reached only with the end-of-regulation riding-time point (margin 14 + 1) went the full 7:00
    reg_pts = {"w": 0, "l": 0}
    for p in reg:
        for e in reg[p]:
            reg_pts[e["side"]] += e["points"]
    tf_by_rt = rclass == "tech_fall" and bool(rt_logged) and abs(reg_pts["w"] - reg_pts["l"]) < 15
    # official end time (elapsed match time, M:SS) for falls; conference results also carry one for some injury
    # defaults / DQs
    end_elapsed = None
    if off and rclass in ("fall", "injury", "dq"):
        mm = re.match(r"^(\d+):(\d\d)$", str(off.get("time") or off.get("score") or ""))
        if mm:
            end_elapsed = int(mm.group(1)) * 60 + int(mm.group(2))
    # overtime columns (or an end time past 7:00) mean regulation was completed, whatever the result type -- a fall
    # in sudden victory is a real thing (e.g. 2016 125 SF, Gilman over Tomasello, fall 7:37 after an SV takedown)
    full_reg = rclass in ("decision", "overtime") or tf_by_rt or has_ot or (end_elapsed is not None and end_elapsed > C.T_TOTAL)
    reached = {1}
    if end_elapsed is not None and end_elapsed <= C.T_TOTAL:
        reached |= set(range(1, (1 if end_elapsed <= 180 else 2 if end_elapsed <= 300 else 3) + 1))
    if full_reg or has_ot or any(k in choice_cols for k in (1, 2)) or 2 in reg or 3 in reg:
        reached.add(2)
    if full_reg or has_ot or 2 in choice_cols or 3 in reg:
        reached.add(3)
    bout.update(included=True, exclude_reason="", result_class=rclass, result_inferred=result_inferred,
                full_regulation=full_reg, went_to_ot=has_ot)

    # a scoreboard clock that wasn't running: two or more scoring events stamped with the period's starting clock
    stuck = sum(1 for p in reg for e in reg[p] if e["points"] and e["clock"] == C.REG[p][0]) >= 2
    bout["stuck_clock"] = stuck
    # clocks: clean + estimate, per regulation period
    n_est = n_est_scoring = 0
    max_gap = 0
    for p in (1, 2, 3):
        if p in reg:
            L = C.REG[p][0]
            clean_clocks(reg[p], L)
            estimate_times(reg[p], L, alpha)
            for e in reg[p]:
                if e["src"] != "clock":
                    S["time_src"][(e["src"], e["action"])] += 1
                    n_est += 1
                    if e["points"]:
                        n_est_scoring += 1
                        max_gap = max(max_gap, e["gap"])
                        S["est_gap"][e["gap"]] += 1
                else:
                    S["time_src"][("clock", "all")] += 1
    for n, evs in ot.items():
        L = C.ot_length(n, y)
        clean_clocks(evs, L)
        estimate_times(evs, L, alpha)

    # ------------------------------------------------------------- walk
    st_ = {"sw": 0, "sl": 0, "pos": "neutral", "rt": 0.0, "t": C.T_TOTAL, "period": 1, "choice": "none",
           "break_step": None, "section": "reg", "unknown_secs": 0, "conflicts": 0}
    stalls = {"w": 0, "l": 0}
    events, samples = [], []
    probes = [(s, "sample") for s in SAMPLE_TIMES]
    notes = []
    for p in (1, 2, 3):
        for note in reg_notes.get(p, []):
            mm = P.RIDING_NOTE_RE.search(note)
            if mm and mm.group(3) is not None:
                ck = int(mm.group(3)) * 60 + int(mm.group(4))
                if ck <= C.REG[p][0]:
                    notes.append((C.t_rem_of(p, ck), int(mm.group(1)) * 60 + int(mm.group(2)), p))
    notes.sort(key=lambda x: -x[0])
    si = [0, 0]  # next sample index, next note index
    seq = [0]

    def snap():
        t = st_["t"]
        reg_ = st_["section"] == "reg"
        return {"t_rem": t if reg_ else 0, "period": st_["period"], "score_w": st_["sw"], "score_l": st_["sl"],
                "margin": st_["sw"] - st_["sl"], "pos": st_["pos"], "choice": st_["choice"],
                "break_step": st_["break_step"] or "", "rt_diff": round(st_["rt"], 1) if reg_ else None,
                "rt_status": C.rt_status(st_["rt"], t) if reg_ else None}

    def advance(t_new):
        t_new = min(t_new, st_["t"])
        d = st_["t"] - t_new
        if st_["pos"] == "w_top":
            st_["rt"] += d
        elif st_["pos"] == "l_top":
            st_["rt"] -= d
        elif st_["pos"] == "unknown":
            st_["unknown_secs"] += d
        st_["t"] = t_new

    def flush(t_ev):
        """Emit riding-time note checks at or before t_ev (compared to the state before events at t_ev) and
        10-second samples strictly before t_ev (a sample at exactly t_ev comes after that event)."""
        while si[1] < len(notes) and notes[si[1]][0] >= t_ev:
            tt, reported, p = notes[si[1]]
            if tt <= st_["t"]:
                save = (st_["rt"], st_["t"], st_["unknown_secs"])
                advance(tt)
                S["rt_note"]["n"] += 1
                err = abs(abs(st_["rt"]) - reported)
                S["rt_note"]["within5"] += err <= 5
                S["rt_note_err"][min(int(err), 30)] += 1
                st_["rt"], st_["t"], st_["unknown_secs"] = save
            si[1] += 1
        # (the opening-whistle sample, t_rem 420, always comes before any event: nothing can have happened yet,
        # even when a scorekeeper's clock reads 3:00 on an early takedown)
        while si[0] < len(SAMPLE_TIMES) and (SAMPLE_TIMES[si[0]] > t_ev or SAMPLE_TIMES[si[0]] == C.T_TOTAL):
            advance(SAMPLE_TIMES[si[0]])
            row = snap()
            row["bout_key"] = key
            samples.append(row)
            si[0] += 1

    def emit(event, actor, points, e=None, before=None):
        seq[0] += 1
        after = snap()
        row = {"bout_key": key, "seq": seq[0], "section": st_["section"], "event": event, "actor": actor or "",
               "points": points,
               "raw_text": e["text"] if e else "", "time_src": e["src"] if e else "break",
               "gap": e["gap"] if e else 0,
               "ot_period": st_.get("ot_n", ""), "ot_clock": e["t"] if (e and st_["section"] == "ot") else "",
               "stalls_w": stalls["w"], "stalls_l": stalls["l"]}
        for k in STATE_KEYS:
            row["b_" + k] = before[k]
            row["a_" + k] = after[k]
        events.append(row)

    def apply(e):
        a, s = e["action"], e["side"]
        o, pos = other(s), st_["pos"]
        known = pos not in ("unknown",)
        if a == "takedown":
            if known and pos != "neutral":
                S["conflict"]["takedown while not neutral"] += 1
                st_["conflicts"] += 1
            st_["pos"] = top_of(s)
        elif a == "reversal":
            if known and pos != top_of(o):
                S["conflict"]["reversal by a wrestler not on bottom"] += 1
                st_["conflicts"] += 1
            st_["pos"] = top_of(s)
        elif a == "escape":
            if known and pos != top_of(o):
                S["conflict"]["escape by a wrestler not on bottom"] += 1
                st_["conflicts"] += 1
            st_["pos"] = "neutral"
        elif a == "near_fall":
            if known and pos != top_of(s):
                S["conflict"]["near fall by a wrestler not on top"] += 1
                st_["conflicts"] += 1
        elif a == "choice":
            S["declaration"][st_["section"]] += 1
            st_["pos"] = declared_pos(s, e["word"])
        if e["points"]:
            if s == "w":
                st_["sw"] += e["points"]
            else:
                st_["sl"] += e["points"]
        if a == "stalling":
            stalls[s] += 1
        S["events_by_action"][a] += 1

    def infer_start(evs):
        """Starting position of a period with no usable choice entry, from its first position-revealing event.
        Returns (pos, how, consumed_first) -- consumed_first = the first event WAS the choice (an in-period
        declaration at the start) and should not also be applied as a restart."""
        for i, e in enumerate(evs):
            a, s = e["action"], e["side"]
            if a == "choice":
                return declared_pos(s, e["word"]), "declaration in period column", i == 0
            if a in ("escape", "reversal"):
                return top_of(other(s)), f"first {a}", False
            if a == "takedown":
                return "neutral", "first takedown", False
            if a == "near_fall":
                return top_of(s), "first near fall", False
        return "unknown", "unknown", False

    def run_period(p, evs, skip_first=False):
        st_["period"], st_["section"], st_["break_step"] = p, "reg", None
        for i, e in enumerate(evs):
            if skip_first and i == 0:
                continue
            t_ev = C.t_rem_of(p, e["t"])
            flush(t_ev)
            advance(t_ev)
            before = snap()
            apply(e)
            emit(e["action"], e["side"], e["points"], e, before)

    # period 1
    run_period(1, reg.get(1, []))
    p3_holder = None
    ended_at = None
    for p in (2, 3):
        if p not in reached:
            break
        boundary = C.REG[p - 1][1]
        flush(boundary)
        advance(boundary)
        st_["period"], st_["pos"] = p, "pending"
        evs_next = reg.get(p, [])
        ch = [e for e in choice_cols.get(p - 1, []) if e["action"] in ("choice", "defer")]
        skip_first = False
        if p == 2:
            st_["choice"], st_["break_step"] = "none", "pre_toss"
            picks = [e for e in ch if e["action"] == "choice"]
            if ch:
                tw = ch[0]["side"]
                S["choice"]["toss found"] += 1
                before = snap()
                st_["choice"], st_["break_step"] = tw, "defer_option"
                emit("toss", tw, 0, None, before)
                if ch[0]["action"] == "defer":
                    S["choice"]["deferred"] += 1
                    before = snap()
                    st_["choice"], st_["break_step"] = other(tw), "pick"
                    emit("defer", tw, 0, None, before)
                    p3_holder = tw
                else:
                    p3_holder = other(tw)  # toss winner picks now (from defer_option), opponent gets period 3
                bout["toss_winner"] = tw
                bout["deferred"] = ch[0]["action"] == "defer"
            else:
                S["choice"]["no Choice 1 entry"] += 1
                c2 = [e for e in choice_cols.get(2, []) if e["action"] == "choice"]
                p3_holder = c2[0]["side"] if c2 else "unknown"
            if picks:
                pk = picks[0]
                before = snap()
                st_["pos"] = declared_pos(pk["side"], pk["word"])
                st_["choice"], st_["break_step"] = p3_holder, None
                emit("choose", pk["side"], 0, {"text": pk["text"], "src": "break", "gap": 0, "t": None}, before)
                S["start_how"][(2, "choice column")] += 1
            else:
                pos, how, skip_first = infer_start(evs_next)
                st_["pos"], st_["choice"], st_["break_step"] = pos, p3_holder, None
                S["start_how"][(2, how)] += 1
        else:
            st_["choice"], st_["break_step"] = p3_holder or "unknown", "pick"
            picks = [e for e in ch if e["action"] == "choice"]
            if picks:
                pk = picks[0]
                if p3_holder in ("w", "l"):
                    S["choice"]["P3 chooser = derived holder" if pk["side"] == p3_holder
                               else "P3 chooser != derived holder"] += 1
                before = snap()
                before["choice"] = pk["side"]  # whoever actually picked
                st_["pos"] = declared_pos(pk["side"], pk["word"])
                st_["choice"], st_["break_step"] = "none", None
                emit("choose", pk["side"], 0, {"text": pk["text"], "src": "break", "gap": 0, "t": None}, before)
                S["start_how"][(3, "choice column")] += 1
            else:
                pos, how, skip_first = infer_start(evs_next)
                st_["pos"], st_["choice"], st_["break_step"] = pos, "none", None
                S["start_how"][(3, how)] += 1
        run_period(p, evs_next, skip_first)

    # official score vs the play-by-play header: an official score exactly one point higher for one side, in a
    # bout decided in regulation, is a riding-time point the scorekeeper didn't log (76 conference bouts; checked
    # against the rebuilt riding time in the report)
    off_diff = None
    if off and C.SCORE_RE.match(str(off.get("score") or "")):
        oa, ob = map(int, off["score"].split("-"))
        off_diff = (oa - ws, ob - ls)
    bout["official_score_diff"] = "" if off_diff is None else f"{off_diff[0]:+d},{off_diff[1]:+d}"
    reg_end = {}
    if full_reg:
        flush(0)
        advance(0)
        before = snap()
        rt_final = st_["rt"]
        recon = "w" if rt_final >= C.RT_THRESHOLD else "l" if rt_final <= -C.RT_THRESHOLD else "none"
        pts = {"w": rt_logged.count("w"), "l": rt_logged.count("l")}
        src = "play-by-play" if rt_logged else "none"
        if not has_ot and off_diff in ((1, 0), (0, 1)) and not rt_logged:
            pts["w" if off_diff == (1, 0) else "l"] += 1
            src = "official score"
            S["flag"]["riding-time point missing from the play-by-play, taken from the official score"] += 1
        net = pts["w"] - pts["l"]
        actual = "w" if net > 0 else "l" if net < 0 else "none"
        st_["sw"] += pts["w"]
        st_["sl"] += pts["l"]
        st_["break_step"] = "regulation_end"
        emit("regulation_end", actual if actual != "none" else "", abs(net), None, before)
        reg_end = {"rt_final_recon": round(rt_final, 1), "rt_point_recon": recon, "rt_point_logged": actual,
                   "rt_point_source": src, "rt_consistent": recon == actual,
                   "reg_margin_before_rt": before["margin"], "reg_margin": st_["sw"] - st_["sl"]}
        ended_at = 0
    else:
        last_t = st_["t"]
        ended_at = last_t
        end_src = "last event"
        if end_elapsed is not None:
            S["end_time"]["official end time"] += 1
            if C.T_TOTAL - end_elapsed > last_t:
                S["end_time"]["official time earlier than the last logged event (used the event)"] += 1
            else:
                ended_at, end_src = C.T_TOTAL - end_elapsed, "official time"
                S["end_gap"][min(last_t - ended_at, 400) // 10 * 10] += 1
        else:
            S["end_time"][f"no official end time ({rclass})"] += 1
        flush(ended_at)
        advance(ended_at)
        if rt_logged:
            S["flag"]["riding-time point logged in a bout that ended early"] += 1
            st_["sw"] += rt_logged.count("w")
            st_["sl"] += rt_logged.count("l")
        before = snap()
        st_["break_step"] = "match_end"
        emit(rclass, "w", 0, None, before)
        bout["end_source"] = end_src
    bout.update(end_t_rem=ended_at, **reg_end)

    # ------------------------------------------------------------- overtime (separate section, not in samples)
    if has_ot and full_reg:
        st_["section"] = "ot"
        c3 = [e for e in choice_cols.get(3, []) if e["action"] == "choice"]
        ot2_start = None
        for n in sorted(ot):
            st_["ot_n"], st_["period"], st_["break_step"] = n, f"OT{n}", None
            evs = ot[n]
            skip_first = False
            if n in (1, 4):
                st_["pos"] = "neutral"
            elif n == 2 and c3:
                st_["pos"] = declared_pos(c3[0]["side"], c3[0]["word"])
            elif n == 3 and len(c3) >= 2:
                st_["pos"] = declared_pos(c3[1]["side"], c3[1]["word"])
            elif n == 3 and ot2_start in ("w_top", "l_top"):
                st_["pos"] = "l_top" if ot2_start == "w_top" else "w_top"
            else:
                st_["pos"], _, skip_first = infer_start(evs)
            if n == 2:
                ot2_start = st_["pos"]
            for i, e in enumerate(evs):
                if skip_first and i == 0:
                    continue
                before = snap()
                apply(e)
                emit(e["action"], e["side"], e["points"], e, before)
        if rt_logged_ot:
            before = snap()
            st_["sw"] += rt_logged_ot.count("w")
            st_["sl"] += rt_logged_ot.count("l")
            emit("ot_riding_time", rt_logged_ot[0], len(rt_logged_ot), None, before)
        if rclass in ("fall", "injury", "dq"):
            before = snap()
            st_["break_step"] = "match_end"
            emit(rclass, "w", 0, None, before)
            bout["end_source"] = "official time (overtime)" if end_elapsed else "last event (overtime)"

    bout.update(n_events=len(events), n_samples=len(samples), n_time_estimated=n_est,
                n_scoring_time_estimated=n_est_scoring, max_scoring_gap=max_gap,
                position_conflicts=st_["conflicts"], unknown_position_secs=st_["unknown_secs"],
                p3_choice_holder=p3_holder or "",
                score_check=(st_["sw"], st_["sl"]) == (ws, ls) or (st_["sw"], st_["sl"]) == (ws + (off_diff or (0, 0))[0], ls + (off_diff or (0, 0))[1]))
    return bout, events, samples


# ---------------------------------------------------------------------------------------------------------------
# Self-checks of the lock function and mirroring
# ---------------------------------------------------------------------------------------------------------------
def self_checks():
    out = []
    cases = [  # (rt_diff, t_rem, expected, why)
        (55, 6, "live", "spec example: 55 s up, 6 s left -- A can still reach 1:00"),
        (55, 4, "locked_none", "spec example: 55 s up, 4 s left -- A can't reach 1:00, B can't either"),
        (60, 0, "locked_in", "exactly 1:00 at the end earns the point (>= 60)"),
        (59, 0, "locked_none", "0:59 at the end does not"),
        (-60, 0, "locked_out", "mirror of the 1:00 case"),
        (75, 10, "locked_in", "75 s up, 10 s left: worst case 65"),
        (75, 16, "live", "75 s up, 16 s left: B could ride it back to 59"),
        (0, 420, "live", "opening whistle: everything reachable"),
        (-30, 25, "locked_none", "30 s down, 25 s left: neither side can reach 1:00"),
    ]
    for rt, t, exp, why in cases:
        got = C.rt_status(rt, t)
        out.append((rt, t, exp, got, why))
    rnd = random.Random(7)
    bad = 0
    for _ in range(20000):
        s = {"margin": rnd.randint(-15, 15), "pos": rnd.choice(["neutral", "w_top", "l_top"]),
             "choice": rnd.choice(["w", "l", "none"]), "rt_diff": rnd.randint(-200, 200)}
        t = rnd.randint(0, 420)
        s["rt_status"] = C.rt_status(s["rt_diff"], t)
        a, b = C.perspective(s, "w"), C.perspective(s, "l")
        if C.mirror(a) != b or C.rt_status(b["rt_diff"], t) != b["rt_status"] or C.rt_bin(b["rt_diff"]) != -C.rt_bin(a["rt_diff"]):
            bad += 1
    return out, bad


# ---------------------------------------------------------------------------------------------------------------
def run(kind):
    recs = list(C.load_bouts(kind))
    # pass 1: fit placement fractions on clocked events; validate on held-out years
    loo = []
    for r in recs:
        for c in r["bout"].get("columns") or []:
            lab = c["label"]
            if lab in C.REG_LABEL:
                evs = [e for e in parse_col(c, False) if e["action"] != "riding_time"]
                L = C.REG[C.REG_LABEL[lab]][0]
                clean_clocks(evs, L)
                loo += [(r["year"],) + x for x in loo_rows(evs, L)]
    alpha = fit_alpha([x[1:] for x in loo])
    a_even = fit_alpha([x[1:] for x in loo if x[0] % 2 == 0])
    e_mid, e_fit = [], []
    for yr, a, pc, end, p, n, t in loo:
        if yr % 2 == 1:
            e_mid.append(abs((p + n) / 2 - t))
            e_fit.append(abs(p - alpha_for(a_even, a, pc, end) * (p - n) - t))

    S = defaultdict(Counter)
    bouts, events, samples = [], [], []
    for r in recs:
        b, ev, sm = build_bout(r, alpha, S)
        bouts.append(b)
        events += ev
        samples += sm

    # Tournaments where riding time wasn't reliably recorded: among bouts whose rebuilt advantage was 80 s or more
    # (a point in ~98% of fully clocked NCAA bouts), the share with no riding-time point anywhere (play-by-play or
    # official score). Flagged when that share is 20%+ over at least 10 such bouts.
    g = defaultdict(lambda: [0, 0])
    for b in bouts:
        if b.get("full_regulation") and not b.get("went_to_ot") and abs(b.get("rt_final_recon", 0)) >= 80:
            g[(b["tournament"], b["year"])][0] += 1
            g[(b["tournament"], b["year"])][1] += b["rt_point_logged"] == "none"
    bad_t = {k: v for k, v in g.items() if v[0] >= 10 and v[1] / v[0] >= 0.2}
    for b in bouts:
        if not b["included"]:
            b["state_table_ok"], b["state_table_reason"] = False, "excluded"
            continue
        b["rt_tournament_ok"] = (b["tournament"], b["year"]) not in bad_t
        rc = b["result_class"]
        b["reg_end_consistent"] = (not b["full_regulation"]) or (
            b["reg_margin"] == 0 if b["went_to_ot"] else (b["reg_margin"] > 0 if rc == "decision" else True))
        why = []
        if not b["score_check"]:
            why.append("score doesn't rebuild")
        if not b["reg_end_consistent"]:
            why.append("regulation end inconsistent with result")
        if b["unknown_position_secs"]:
            why.append("period start position unknown")
        if b["stuck_clock"]:
            why.append("clock stuck at period start")
        if not b["rt_tournament_ok"]:
            why.append("tournament without reliable riding time")
        elif b["full_regulation"] and not b["rt_consistent"]:
            why.append("rebuilt riding-time point != actual")
        b["state_table_ok"] = not why
        b["state_table_reason"] = "; ".join(why)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, rows in (("bouts", bouts), ("events", events), ("samples", samples)):
        cols = []
        for row in rows:
            for k in row:
                if k not in cols:
                    cols.append(k)
        with open(OUT_DIR / f"{kind}_{name}.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
    return {"kind": kind, "alpha": alpha, "holdout": (e_mid, e_fit), "S": S, "bouts": bouts, "events": events,
            "samples": samples, "n_loo": len(loo), "bad_t": bad_t}


def pct(a, b, d=1):
    return f"{100 * a / b:.{d}f}%" if b else "—"


def fmt_clock(t):
    return f"{int(t) // 60}:{int(t) % 60:02d}"


def report(results):
    checks, mirror_bad = self_checks()
    L = []
    A = L.append
    A("# WPA step 2 — state reconstruction\n")
    A("Generated by `scripts/wpa/build_states.py` (shared definitions in `scripts/wpa/wpa_common.py`). Inputs are the "
      "same play-by-play and official results as the data audit. Nothing in `data/` outside `data/wpa/` is changed.\n")
    A("**Outputs** (`data/wpa/states/`), every bout stored once from the winner's side (`w` = winner, `l` = loser); "
      "step 3 builds both perspectives:\n")
    A("- `{kind}_bouts.csv` — one row per bout: ids, `era`, raw and usable seeds (`w_seed`/`l_seed`, decision C), "
      "result, how regulation ended, riding-time checks, flags (`n_scoring_time_estimated`, `max_scoring_gap`, "
      "`position_conflicts`, `unknown_position_secs`, `score_check`).")
    A("- `{kind}_events.csv` — one row per event with the state before (`b_*`) and after (`a_*`): `t_rem`, `period`, "
      "score, `margin`, `pos` (`neutral`/`w_top`/`l_top`/`pending`), `choice`, `rt_diff` (winner minus loser, "
      "seconds), `rt_status`. Includes the break events (`toss`, `defer`, `choose`), `regulation_end` (where the "
      "riding-time point is applied) and overtime events (`section = ot`).")
    A("- `{kind}_samples.csv` — the state every 10 s of regulation (`t_rem` 420 … 10), for spec 3.1's fixed-cadence "
      "samples. A bout that ended early (fall, tech fall, injury, DQ) has samples only before its last logged event.\n")

    for res in results:
        kind = res["kind"]
        nm = "NCAA" if kind == "ncaa" else "Conference"
        S, bouts, events, samples = res["S"], res["bouts"], res["events"], res["samples"]
        inc = [b for b in bouts if b["included"]]
        A(f"## {nm}\n")
        A("### Bouts\n")
        ex = Counter(b["exclude_reason"] for b in bouts if not b["included"])
        A(f"- {len(bouts):,} bout records → **{len(inc):,} included**; excluded: " +
          ", ".join(f"{k} {v:,}" for k, v in ex.most_common()) + ".")
        rc = Counter(b["result_class"] for b in inc)
        A("- Included by result: " + ", ".join(f"{k} {v:,}" for k, v in rc.most_common()) +
          f" ({sum(b['result_inferred'] for b in inc)} with no official result type — class taken from the "
          f"play-by-play).")
        er = Counter(b["era"] for b in inc)
        A("- By rules era: " + ", ".join(f"{k} {er[k]:,}" for k in sorted(er)) +
          f" (E3 = 2024–26, the anchor per TJ).")
        sw = [b for b in inc if b["swapped"]]
        A(f"- Swapped-sides bouts corrected (header and event sides reversed relative to the official result): "
          f"{len(sw)}" + (": " + "; ".join(f"{b['year']} {b['weight']} {b['w_name']} over {b['l_name']}"
                                           for b in sw[:6]) if sw else "") + ".")
        ok = sum(b["score_check"] for b in inc)
        od = Counter(b["official_score_diff"] for b in inc if b["official_score_diff"])
        nod = sum(od.values())
        A(f"- **Score check:** rebuilding each bout event by event (riding-time point applied at the end of "
          f"regulation, overtime added after) reproduces the bout's final score in **{ok:,} of {len(inc):,} "
          f"({pct(ok, len(inc), 2)})**. Independent check against the official result (bouts whose official "
          f"result carries a points score, n = {nod:,}): header score = official in {pct(od['+0,+0'], nod, 2)}; "
          f"official one point higher for one side {od['+1,+0'] + od['+0,+1']:,} (a riding-time point the "
          f"scorekeeper didn't log — added at the end of regulation, `rt_point_source = official score`); other "
          f"differences {nod - od['+0,+0'] - od['+1,+0'] - od['+0,+1']:,} (left as the play-by-play has them)." +
          ("" if ok == len(inc) else " Mismatches: " + "; ".join(
              f"{b['bout_key']} (file {b['final_w']}-{b['final_l']})" for b in inc if not b["score_check"])[:600]))
        A("")

        A("### Clock (decision B)\n")
        ts = S["time_src"]
        n_clock = ts[("clock", "all")]
        n_miss = sum(v for (src, a), v in ts.items() if src == "missing")
        n_rej = sum(v for (src, a), v in ts.items() if src == "rejected")
        A(f"- Regulation events: {n_clock:,} with a usable clock, {n_miss:,} with none, {n_rej:,} whose clock was "
          f"rejected (outside the period, or off the longest non-increasing run of clocks in that period — a clock "
          f"that jumps back up is treated as a typo, not as time running backwards).")
        by_a = Counter()
        for (src, a), v in ts.items():
            if src != "clock":
                by_a[a] += v
        A("- Estimated events by type: " + ", ".join(f"{a} {v:,}" for a, v in by_a.most_common()) + ".")
        e_mid, e_fit = res["holdout"]
        A(f"- **Placement rule:** an estimated event goes between the previous placed time and the next real clock, "
          f"at a fraction fitted per (event type, previous event, whether the next anchor is a real clock or the "
          f"end of the period) on {res['n_loo']:,} clocked events — hide a real "
          f"clock, see where it sat between its neighbours. Tested on held-out years (fit on even seasons, scored on "
          f"odd): **mean error {st.mean(e_fit):.1f} s, median {st.median(e_fit):.0f} s**, vs the plain midpoint "
          f"{st.mean(e_mid):.1f} s / {st.median(e_mid):.0f} s.")
        al = res["alpha"]
        show = [("near_fall", "takedown"), ("takedown", "other"), ("takedown", "START"), ("escape", "takedown"),
                ("escape", "START"), ("penalty", "stall"), ("reversal", "START")]
        A("  Fractions used (0 = same second as the previous event, 1 = same second as the next clock): " +
          ", ".join(f"{a} after {pc}: {al[(a, pc)]:.2f}" for a, pc in show if (a, pc) in al) + ".")
        gaps = S["est_gap"]
        ng = sum(gaps.values())
        g10 = sum(v for g, v in gaps.items() if g <= 10)
        g30 = sum(v for g, v in gaps.items() if g <= 30)
        g60 = sum(v for g, v in gaps.items() if g <= 60)
        A(f"- Window each estimated scoring event was placed in: ≤10 s {pct(g10, ng)}, ≤30 s {pct(g30, ng)}, "
          f"≤60 s {pct(g60, ng)}, wider {pct(ng - g60, ng)} (n = {ng:,}).")
        fb = sum(1 for b in inc if b["n_scoring_time_estimated"])
        fb60 = sum(1 for b in inc if b["max_scoring_gap"] > 60)
        A(f"- Bouts with at least one estimated scoring event: {fb:,} ({pct(fb, len(inc))}); with one placed in a "
          f"window wider than 60 s: {fb60:,} ({pct(fb60, len(inc))}). Both flags are on the bout row.\n")

        A("### Position\n")
        sh = S["start_how"]
        for p in (2, 3):
            tot = sum(v for (pp, h), v in sh.items() if pp == p)
            A(f"- Period {p} starting position (n = {tot:,}): " +
              ", ".join(f"{h} {pct(v, tot)}" for (pp, h), v in sorted(sh.items(), key=lambda x: -x[1]) if pp == p) + ".")
        cf = S["conflict"]
        nsc = sum(v for a, v in S["events_by_action"].items() if a in ("takedown", "escape", "reversal", "near_fall"))
        A(f"- **Consistency:** of {nsc:,} takedowns, escapes, reversals and near falls, {sum(cf.values()):,} "
          f"({pct(sum(cf.values()), nsc, 2)}) don't fit the position reconstructed so far: " +
          ", ".join(f"{k} {v:,}" for k, v in cf.most_common()) +
          ". The event is applied anyway (a takedown still puts the scorer on top), so one missed restart or "
          "scoring event doesn't carry forward. Bouts with any: "
          f"{sum(1 for b in inc if b['position_conflicts']):,} ({pct(sum(1 for b in inc if b['position_conflicts']), len(inc))}).")
        dec = S["declaration"]
        A(f"- Position declared inside a period (a restart after a stoppage, logged like `Bottom (1:50)`): "
          f"{dec['reg']:,} in regulation — treated as a position reset.")
        uk = [b for b in inc if b["unknown_position_secs"]]
        A(f"- Bouts where a period's starting position could not be determined at all (no choice logged and no "
          f"position-revealing event): {len(uk):,}; {sum(b['unknown_position_secs'] for b in uk):,} seconds of "
          f"regulation in unknown position (no riding time credited there).\n")

        A("### Choice\n")
        chs = S["choice"]
        reached2 = sum(v for (p, h), v in S["start_how"].items() if p == 2)
        A(f"- Toss winner identified in {chs['toss found']:,} of {reached2:,} bouts that reached period 2 "
          f"({pct(chs['toss found'], reached2)}); the toss winner deferred in {pct(chs['deferred'], chs['toss found'])}.")
        agree, disagree = chs["P3 chooser = derived holder"], chs["P3 chooser != derived holder"]
        A(f"- Check of the rule (toss winner who picks → opponent picks period 3; toss winner who defers → toss winner "
          f"picks period 3): the logged period-3 chooser matches in **{agree:,} of {agree + disagree:,} "
          f"({pct(agree, agree + disagree, 2)})**.")
        A("- Encoding (flagged — differs from the spec's wording): the NCAA disk toss is at the start of period 2, so "
          "`choice = none` throughout period 1; the toss, a defer and the pick are events at the break "
          "(`break_step` pre_toss → defer_option → pick). During period 2 `choice` = the period-3 chooser; "
          "period 3: none.\n")

        A("### Riding time (decision A)\n")
        rn = S["rt_note"]
        A(f"- Against the scorekeeper's clock-pinned riding-time notes (net advantage, as in the audit): "
          f"**{rn['within5']:,} of {rn['n']:,} ({pct(rn['within5'], rn['n'])}) within 5 s** with the new timing "
          f"(audit, old parser: 94.8%).")
        fr = [b for b in inc if b["full_regulation"]]
        conf = Counter((b["rt_point_recon"], b["rt_point_logged"]) for b in fr)
        agree = sum(v for (a, b), v in conf.items() if a == b)
        fsrc = Counter(b["rt_point_source"] for b in fr)
        A(f"- **End-of-regulation riding-time point, rebuilt vs actual** ({len(fr):,} bouts that went the full seven "
          f"minutes; actual = the point in the play-by-play ({fsrc['play-by-play']:,}), or the official score's extra "
          f"point where the scorekeeper didn't log one ({fsrc['official score']:,})): agree in **{agree:,} "
          f"({pct(agree, len(fr))})**.\n")
        A("| Rebuilt ↓ / Actual → | winner | loser | none |\n|---|---:|---:|---:|")
        for a in ("w", "l", "none"):
            A(f"| {'winner' if a == 'w' else 'loser' if a == 'l' else 'none'} | " +
              " | ".join(f"{conf[(a, b)]:,}" for b in ("w", "l", "none")) + " |")
        A("\n  Near the 1:00 line — share of bouts where the rebuilt leader actually got the point:\n")
        A("| Rebuilt advantage at the end | Bouts | Leader got the point |\n|---|---:|---:|")
        for lo, hi in ((0, 40), (40, 50), (50, 55), (55, 58), (58, 60), (60, 62), (62, 65), (65, 70), (70, 80),
                       (80, 1000)):
            sel = [b for b in fr if lo <= abs(b["rt_final_recon"]) < hi]
            got = sum(1 for b in sel if b["rt_point_logged"] == ("w" if b["rt_final_recon"] > 0 else "l"))
            lab = f"{lo}–{hi - 1} s" if hi < 1000 else f"{lo}+ s"
            A(f"| {lab} | {len(sel):,} | {pct(got, len(sel))} |")
        def agree_(bs):
            return sum(b["rt_point_recon"] == b["rt_point_logged"] for b in bs), len(bs)
        a1, n1 = agree_([b for b in fr if not b["n_scoring_time_estimated"]])
        a2, n2 = agree_([b for b in fr if b["n_scoring_time_estimated"]])
        a3, n3 = agree_([b for b in fr if b["max_scoring_gap"] > 60])
        A(f"\n  **Where the misses come from:** bouts where every scoring event has a real clock agree "
          f"**{pct(a1, n1)}** ({a1:,} of {n1:,}); bouts with an estimated scoring event {pct(a2, n2)} ({a2:,} of "
          f"{n2:,}); bouts with one placed in a window wider than 60 s {pct(a3, n3)}. So the reconstruction itself is "
          f"sound; the misses are the unclocked events whose time had to be guessed (typically an unclocked takedown "
          f"late in a period, where the guess decides how long the ride lasted). Each full-regulation bout carries "
          f"`rt_consistent` (rebuilt point == actual point); the {n1 + n2 - a1 - a2:,} inconsistent bouts are left "
          f"out of the state table (`state_table_ok`, below) — the riding-time lock states are where their errors "
          f"would land — and kept for WPA reporting.")
        by_y = defaultdict(lambda: [0, 0])
        for b in fr:
            by_y[b["year"]][0] += b["rt_point_recon"] == b["rt_point_logged"]
            by_y[b["year"]][1] += 1
        A("  By season: " + ", ".join(f"{y} {pct(a, n)}" for y, (a, n) in sorted(by_y.items())) + ".")
        wrong_side = conf[("w", "l")] + conf[("l", "w")]
        A(f"\n  Opposite-side disagreements (rebuilt says one wrestler, the other got it): {wrong_side}. The rest "
          f"sit near the line — a few seconds of reconstruction error either way.")
        smp = samples
        stat_p = Counter((s["period"], s["rt_status"]) for s in smp)
        A("- `rt_status` in the 10-second samples, by period: " + "; ".join(
            f"P{p}: " + ", ".join(f"{k} {pct(stat_p[(p, k)], sum(v for (pp, kk), v in stat_p.items() if pp == p))}"
                                  for k in ("live", "locked_none", "locked_in", "locked_out"))
            for p in (1, 2, 3)) + ". Locked states only appear late, as expected.\n")

        A("### Regulation end and overtime\n")
        ot_b = [b for b in fr if b["went_to_ot"]]
        tied = sum(1 for b in ot_b if b["reg_margin"] == 0)
        A(f"- Every bout that went to overtime must be tied after the riding-time point is added: "
          f"**{tied:,} of {len(ot_b):,}** are.")
        dec_b = [b for b in fr if b["result_class"] == "decision"]
        nz = sum(1 for b in dec_b if b["reg_margin"] > 0)
        A(f"- Decisions: winner ahead at the end of regulation in {nz:,} of {len(dec_b):,}.")
        tf = [b for b in inc if b["result_class"] == "tech_fall"]
        tf_rt = sum(1 for b in tf if b["full_regulation"])
        A(f"- Tech falls: {len(tf):,}, of which {tf_rt:,} reached 15 only with the riding-time point at the end of "
          f"regulation (margin 14 + 1).")
        early = [b for b in inc if not b["full_regulation"]]
        et = S["end_time"]
        eg = S["end_gap"]
        neg = sum(eg.values())
        A(f"- Bouts that ended before the end of regulation: {len(early):,}. Tech falls end at the scoring event "
          f"that reached 15. **Falls end at their official time** — NCAA results carry it in `score` (elapsed match "
          f"time, e.g. `6:37`), conference results in `time`; the data audit wrongly said NCAA had none, so decision F "
          f"(end at the last logged event) is only the fallback now: " +
          ", ".join(f"{k} {v:,}" for k, v in et.most_common()) + ".")
        if neg:
            A(f"  How long after the last logged event the fall came: same 10-s window {pct(eg[0], neg)}, "
              f"≤30 s {pct(sum(v for g, v in eg.items() if g < 30), neg)}, ≤60 s "
              f"{pct(sum(v for g, v in eg.items() if g < 60), neg)}, longer {pct(sum(v for g, v in eg.items() if g >= 60), neg)}"
              f" — the samples in that stretch are real live states that the last-event rule would have dropped.")
        ot_end = [b for b in inc if str(b.get("end_source", "")).endswith("(overtime)")]
        A(f"- Falls / injury defaults in overtime: {len(ot_end)} (regulation completed, so they count as full "
          f"regulation bouts).\n")

        if kind == "ncaa":
            A("### Two bouts, reconstructed (spot check)\n")
        byk = defaultdict(list)
        for e in events:
            byk[e["bout_key"]].append(e)
        picks = []
        for b in (inc if kind == "ncaa" else []):  # an E3 decision with a riding-time point; an E3 fall
            if b["era"] == "E3" and b.get("rt_point_logged") == "w" and b["result_class"] == "decision" \
                    and b["round"] in ("Final", "SF") and not picks:
                picks.append(b)
        for b in (inc if kind == "ncaa" else []):
            if b["era"] == "E3" and b["result_class"] == "fall" and b.get("end_source") == "official time" \
                    and b["round"] in ("Final", "SF", "QF") and len(picks) < 2:
                picks.append(b)
        for b in picks:
            A(f"**{b['year']} {b['weight']} {b['round']}: {b['w_name']} ({b['w_team']}) over {b['l_name']} "
              f"({b['l_team']}), {b['result_type']} {b['final_w']}-{b['final_l']}** — winner = `w`.\n")
            A("| Event | By | Time left (reg.) | Score after | Position after | Choice after | RT diff after | "
              "RT status after |\n|---|---|---|---|---|---|---:|---|")
            for e in byk[b["bout_key"]]:
                if e["section"] != "reg":
                    continue
                ev = e["event"] + (" *(time est.)*" if e["time_src"] not in ("clock", "break") else "")
                A(f"| {ev} | {e['actor']} | {fmt_clock(e['a_t_rem'])} | {e['a_score_w']}-{e['a_score_l']} | "
                  f"{e['a_pos']} | {e['a_choice']} | {e['a_rt_diff']} | {e['a_rt_status']} |")
            A("")

        A("### Which bouts go into the state table (`state_table_ok`)\n")
        if res["bad_t"]:
            A("Tournaments flagged for unreliable riding time (of bouts with a rebuilt advantage of 80 s or more, the "
              "share with no riding-time point anywhere — about 2% in fully clocked NCAA bouts):\n")
            A("| Tournament | Bouts rebuilt 80 s+ | No point |\n|---|---:|---:|")
            for (t, y), (n, miss) in sorted(res["bad_t"].items(), key=lambda x: -x[1][1] / x[1][0]):
                A(f"| {t} {y} | {n} | {miss} ({pct(miss, n, 0)}) |")
            A("")
        else:
            A("No tournament is flagged for unreliable riding time.\n")
        ok_b = [b for b in inc if b["state_table_ok"]]
        reasons = Counter(r for b in inc for r in b["state_table_reason"].split("; ") if r)
        A(f"- **{len(ok_b):,} of {len(inc):,} included bouts ({pct(len(ok_b), len(inc))}) are clean for the state "
          f"table.** Left out (a bout can have several reasons): " +
          ", ".join(f"{k} {v:,}" for k, v in reasons.most_common()) + ".")
        era_ok = Counter(b["era"] for b in ok_b)
        era_all = Counter(b["era"] for b in inc)
        A("- Clean bouts by era: " + ", ".join(f"{e} {era_ok[e]:,} of {era_all[e]:,}" for e in sorted(era_all)) +
          ". Left-out bouts stay in the files for WPA reporting; step 3 filters on `state_table_ok`.\n")

        A("### Size\n")
        A(f"- {len(events):,} event rows, {len(smp):,} ten-second samples.")
        by_era = Counter()
        bmap = {b["bout_key"]: b["era"] for b in inc}
        for s in smp:
            by_era[bmap[s["bout_key"]]] += 1
        A("- Samples by era: " + ", ".join(f"{k} {by_era[k]:,}" for k in sorted(by_era)) +
          " (×2 once mirrored in step 3).\n")

    A("## Riding-time lock function (spec 2.3)\n")
    A("`wpa_common.rt_status(rt_diff, t_rem)` — exactly the spec's simple bound; threshold `rt_diff >= 60` "
      "(1:00 or more, confirmed by the near-the-line table above: the point goes to the leader from 60 s up, not "
      "below). Position is not used to tighten the bound yet (spec: refine only if validation shows it matters).\n")
    A("| A's advantage | Time left | Expected | Got | Case |\n|---:|---:|---|---|---|")
    for rt, t, exp, got, why in checks:
        A(f"| {rt} s | {t} s | {exp} | {got}{'' if got == exp else ' ✗'} | {why} |")
    A(f"\nMirror check: 20,000 random states viewed from both wrestlers — `mirror(A's view) == B's view` (margin, "
      f"position, choice, riding time, lock status, riding-time bin) failed **{mirror_bad}** times.\n")

    A("## Bins (for step 3)\n")
    A("`margin_bin` clamps to ±15; `t_bin` = 10-second bins of regulation time left (0–41); `rt_bin` = 10-second "
      "riding-time bins truncated toward zero, clamped to ±6 (±60 s), so a mirrored state always lands in the "
      "mirrored bin.\n")
    OUT = REPORT
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(L) + "\n")
    print("wrote", OUT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", default="ncaa", choices=["ncaa", "conf", "both"])
    args = ap.parse_args()
    kinds = ["ncaa", "conf"] if args.kind == "both" else [args.kind]
    results = [run(k) for k in kinds]
    for r in results:
        print(f"{r['kind']}: {sum(b['included'] for b in r['bouts']):,} bouts, {len(r['events']):,} events, "
              f"{len(r['samples']):,} samples")
    report(results)


if __name__ == "__main__":
    main()
