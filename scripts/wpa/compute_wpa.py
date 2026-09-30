#!/usr/bin/env python3
"""
WPA step 9 -- win probability added per event, and its decomposition (spec Section 6).

Every NCAA bout that feeds the state table (bouts file `table_ok`) becomes one unbroken chain of win probabilities
from the opening whistle to the result, scored with the final model (`wp_model.WPModel`: state model + seed layer):

    opening whistle -> [clock] -> event -> [clock] -> event -> ... -> result (1 / 0)

Every link is a row of data/wpa/output/events_wpa.parquet, so each wrestler's WPA over a bout sums EXACTLY to
(result - WP at the opening whistle) -- asserted (spec 6.2).

Rows (event_type / category):
  * scoring events -- takedown, escape, reversal, near_fall (subtype nf2 / nf3 / nf4), penalty point: credited to
    the wrestler who caused them. A penalty point is credited to the wrestler who COMMITTED the infraction (the
    negative value) and `beneficiary` names the other one; subtype `stalling` when the offender's stalling call
    comes right before it (same second), else `penalty`.
  * choice -- toss (winning it), defer, choose (the period-2 / period-3 pick): WP after the step - WP before, from
    the chooser's side. `position` -- mid-period position calls ("Top (0:22)") without points.
  * riding_time -- `rt_lock`: the second the riding-time point stops being live (someone locks it in, or nobody can
    reach 1:00 any more); credited to the wrestler with the riding-time advantage at that moment. Plus the point
    itself at the end of regulation (`regulation_end`; ~0 WPA when the rebuilt riding time matches the official
    point, because the lock already priced it in).
  * terminal -- fall, tech_fall, injury, dq: whatever was left to reach 1. A tech fall is two rows: the score that
    reached 15 (valued as a state, like any score) and the tech_fall row (the remainder to 1).
  * overtime -- current rules (SV120, 2022+): the overtime model (ot_model.py). Tied at the end of regulation = its
    start value (sudden victory + tiebreaker, with the tiebreaker choice holder from regulation); every overtime
    event is valued (sudden victory by the clock, tiebreaker rides by position / points / tiebreaker riding time);
    `ot_choice` rows = the ride-1 / ride-2 position picks (credited to the chooser); a TB-1 that ended scoreless and
    tied is rebuilt (ride-out, bottom, ride-out) and the later rounds are one value until the winner's last overtime
    score. Earlier rules (SV60, before 2022): tied = the overtime win rate expit(beta_ot * rank signal), flat until
    the winner's LAST scoring event in overtime. If overtime has no winner's score, a synthetic `overtime` row takes
    the value to 1. Overtime rows: period = NaN, subtype = the phase (SV1 / TB1 / TB2 / later), margin = overtime
    points, rt = tiebreaker riding time.
  * clock -- time running between events (spec 6.1 "time decay"), credited to the leader at the start of the stretch
    (tied: the wrestler the model favours). Riding-time locks inside a stretch are split out as `rt_lock` rows.
  * other -- caution, stalling warnings, misconduct, score adjustments (no state change -> ~0 WPA).

Stored once per link, with the CREDITED wrestler's side: wp_before / wp_after / wpa and his state (margin, position,
choice, riding-time differential) before and after; wp_w_before / wp_w_after = the bout winner's side.

Outputs:
  data/wpa/output/events_wpa.parquet   one row per link (gitignored; rebuild in ~1 min)
  data/wpa/output/wrestler_wpa.csv     per wrestler per NCAA tournament: total WPA and splits by category, by own
                                       vs opponent's actions, and by position (top / bottom / neutral / break / OT)
  data/wpa/reports/wpa.md              sanity checks (sum rule, negative scoring WPA) + what the numbers say

Usage: .venv/bin/python scripts/wpa/compute_wpa.py [--kind ncaa|conf|both]   (default both; conference = step 10)
"""
import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import expit

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts/wpa"))
import fit_state_model as F  # noqa: E402
import ot_model as OM        # noqa: E402
import wp_model as W         # noqa: E402
import wpa_common as C       # noqa: E402

STATES = ROOT / "data/wpa/states"
OUT = ROOT / "data/wpa/output"
REP = ROOT / "data/wpa/reports/wpa.md"
TERMINAL = {"fall", "tech_fall", "injury", "dq"}
SCORING = {"takedown", "escape", "reversal", "near_fall", "penalty"}
CHOICE = {"toss", "defer", "choose"}
OTHER = {"caution", "stalling", "misconduct", "adjustment"}
TH = C.RT_THRESHOLD


# ---------------------------------------------------------------------------------------------------------------
# states (A = the bout winner)
# ---------------------------------------------------------------------------------------------------------------
def w_states(ev, p, nb):
    """Event states (p = 'b_' before / 'a_' after) from the winner's side, in wp_model's input format."""
    pos = ev[p + "pos"].astype(str).to_numpy()
    bs = ev[p + "break_step"].fillna("").astype(str).to_numpy()
    posA = np.select([pos == "neutral", pos == "w_top", pos == "l_top", pos == "pending"],
                     ["neutral", "A_top", "A_bottom", np.char.add("pending_", bs.astype(str))], "unknown")
    ch = ev[p + "choice"].fillna("none").astype(str).to_numpy()
    chA = np.select([ch == "w", ch == "l", ch == "none"], ["A", "B", "none"], "unknown")
    yr = ev["bout_key"].map(nb["year"]).to_numpy()
    per = pd.to_numeric(ev[p + "period"], errors="coerce").to_numpy()
    return pd.DataFrame({"margin": ev[p + "margin"].to_numpy(float), "t_rem": ev[p + "t_rem"].to_numpy(float),
                         "period": per, "pos": posA, "choice": chA, "rt_diff": ev[p + "rt_diff"].to_numpy(float),
                         "era_group": np.where(yr >= 2024, "E3", "E12"),
                         "seed_a": ev["bout_key"].map(nb["w_seed"]).astype(float).to_numpy(),
                         "seed_b": ev["bout_key"].map(nb["l_seed"]).astype(float).to_numpy(),
                         "kind": ev["bout_key"].map(nb["kind"]).to_numpy()}, index=ev.index)


def ints(d):
    return d.astype({"margin": int, "period": int})


def modelable(s, section):
    return ((section == "reg") & (s["t_rem"] > 0) & s["period"].isin([1, 2, 3]) & s["pos"].isin(F.POS)
            & s["choice"].isin(F.CH + ["unknown"])).to_numpy()


def wp_of(m, X):
    """m.wp, except a state whose choice holder wasn't recorded (choice 'unknown': some conference bouts lack the
    period-2 choice entry) is valued as the average of 'A holds it' and 'B holds it'."""
    X = ints(X)
    unk = (X["choice"] == "unknown").to_numpy()
    out = np.empty(len(X))
    if (~unk).any():
        out[~unk] = m.wp(X[~unk])
    if unk.any():
        out[unk] = 0.5 * (m.wp(X[unk].assign(choice="A")) + m.wp(X[unk].assign(choice="B")))
    return out


def end_value(margin, rt_diff, wp_ot):
    """Value at 0:00 of regulation: the result after the riding-time point; tied = the overtime win rate."""
    m = margin + (rt_diff >= TH) - (rt_diff <= -TH)
    return 1.0 if m > 0 else 0.0 if m < 0 else wp_ot


def accrual(pos):
    return 1 if pos == "A_top" else -1 if pos == "A_bottom" else 0


# ---------------------------------------------------------------------------------------------------------------
def build(m, nb, ev):
    """The chain of every bout, winner's side. Each link runs between two points (a state + its WP); points inside
    clock stretches (riding-time locks) are valued in one batch model call at the end."""
    ev = ev.sort_values(["bout_key", "seq"]).reset_index(drop=True)
    bf, af = w_states(ev, "b_", nb), w_states(ev, "a_", nb)
    sec = ev["section"].to_numpy()
    mb, ma = modelable(bf, sec), modelable(af, sec)
    wp_b, wp_a = np.full(len(ev), np.nan), np.full(len(ev), np.nan)
    wp_b[mb], wp_a[ma] = wp_of(m, bf[mb]), wp_of(m, af[ma])

    start = pd.DataFrame({"margin": 0, "t_rem": float(C.T_TOTAL), "period": 1, "pos": "neutral", "choice": "none",
                          "rt_diff": 0.0, "era_group": np.where(nb["year"] >= 2024, "E3", "E12"),
                          "seed_a": nb["w_seed"].astype(float), "seed_b": nb["l_seed"].astype(float),
                          "kind": nb["kind"]}, index=nb.index)
    sp = m.parts(start)
    wp_start = sp["wp"]
    wp_ot = pd.Series(expit(m.sp["beta_ot"] * sp["rs"].to_numpy()), index=nb.index)
    # current overtime rules: the overtime model's start value (tiebreaker holder = first takedown / near fall)
    otm = OM.OTModel() if OM.PRM_FILE.exists() else None
    sv120 = (nb["ot_rules"] == "SV120").to_numpy() & (otm is not None)
    reg_off = ev[(ev["section"] == "reg") & ev["event"].isin(["takedown", "near_fall"]) & (ev["points"] > 0)]
    holder = reg_off.groupby("bout_key")["actor"].first().reindex(nb.index).fillna("")
    tdp = np.where(nb["year"] >= 2024, 3, 2)
    if sv120.any():
        wp_ot[sv120] = otm.start_values(sp["rs"].to_numpy()[sv120], holder.to_numpy()[sv120], tdp[sv120])
    oti = pd.read_csv(STATES / "ot_bouts.csv", keep_default_na=False).set_index("bout_key") if otm is not None else None
    if oti is not None:
        for c in ("clean", "tie_tb1"):
            oti[c] = oti[c].astype(str) == "True"
    rs_ = pd.Series(sp["rs"].to_numpy(), index=nb.index)

    rows, pending = [], []      # pending: points whose WP needs the model (inside clock stretches)
    E = ev[["bout_key", "event", "actor", "points", "section", "seq", "time_src", "b_t_rem"]]
    OTP = [None if x != x else int(x) for x in ev["ot_period"]]
    OTC = [None if x != x else float(x) for x in ev["ot_clock"]]
    RAW = ev["raw_text"].tolist()
    BF, AF = bf.to_dict("records"), af.to_dict("records")
    bouts = ev["bout_key"].to_numpy()
    starts = np.flatnonzero(np.r_[True, bouts[1:] != bouts[:-1]])
    ends = np.r_[starts[1:], len(ev)]
    n_noflip = 0

    def pt(state, v=None, bk=None):
        p_ = {"s": state, "v": v, "bk": bk}
        if v is None:
            pending.append(p_)
        return p_

    def link(bk, seq, etype, cat, actor, pa_, pb_, sub="", bene="", tsrc=""):
        rows.append({"bout_key": bk, "seq": seq, "event_type": etype, "subtype": sub, "category": cat,
                     "actor": actor, "beneficiary": bene, "_pa": pa_, "_pb": pb_, "time_src": tsrc})

    for s0, e0 in zip(starts, ends):
        bk = bouts[s0]
        wot = float(wp_ot[bk])
        cur = pt({"margin": 0.0, "t_rem": float(C.T_TOTAL), "period": 1, "pos": "neutral", "choice": "none",
                  "rt_diff": 0.0}, float(wp_start[bk]))
        prev_sec, done = "reg", False
        use_otm = bool(sv120[nb.index.get_loc(bk)]) and bk in oti.index if otm is not None else False
        ot_rows = []
        ot_win = None           # the winner's last scoring event in overtime = the winning score
        for i in range(s0, e0):
            if E.at[i, "section"] == "ot" and E.at[i, "actor"] == "w" and (E.at[i, "points"] > 0
                                                                           or E.at[i, "event"] == "fall"):
                ot_win = i
        for i in range(s0, e0):
            et, secn, seq = E.at[i, "event"], E.at[i, "section"], E.at[i, "seq"]
            actor = E.at[i, "actor"] if isinstance(E.at[i, "actor"], str) else ""
            sb, sa = BF[i], AF[i]
            if use_otm and secn == "ot":
                ot_rows.append(i)
                continue
            # ---- WP before / after (winner's side)
            if done:
                wb = wa = 1.0
            elif secn == "ot":
                wb, wa = wot, (1.0 if i == ot_win else wot)
            elif et == "regulation_end":
                wb, wa = end_value(sb["margin"], sb["rt_diff"], wot), end_value(sa["margin"], 0.0, wot)
            else:
                wb = wp_b[i] if mb[i] else (end_value(sb["margin"], sb["rt_diff"], wot) if sb["t_rem"] <= 0
                                            else np.nan)
                wa = 1.0 if et in TERMINAL else (wp_a[i] if ma[i] else (
                    end_value(sa["margin"], sa["rt_diff"], wot) if sa["t_rem"] <= 0 else np.nan))
            if np.isnan(wb) or np.isnan(wa):
                raise ValueError(f"{bk} seq {seq}: no WP for {et} ({sb['pos']} -> {sa['pos']})")
            pb_ = pt(sb, wb)

            # ---- the clock stretch up to this event, riding-time locks split out
            if not done:
                cs = cur["s"]
                if prev_sec == "reg" and secn == "reg":
                    t0, t1, rt0, rt1 = cs["t_rem"], sb["t_rem"], cs["rt_diff"], sb["rt_diff"]
                    st0 = W.rt_status_vec([rt0], [t0])[0]
                    st1 = W.rt_status_vec([rt1], [max(t1, 0)])[0]
                    if t1 < t0 and st0 != st1:
                        ok_ = cs["pos"] in ("neutral", "A_top", "A_bottom") and (
                            cs["period"] == sb["period"] or str(sb["pos"]).startswith("pending") or t1 <= 0)
                        if not ok_:
                            n_noflip += 1
                        else:
                            secs = np.arange(t0 - 1, t1 - 1, -1, dtype=float)
                            rts = rt0 + (rt1 - rt0) * (t0 - secs) / (t0 - t1)
                            stat = W.rt_status_vec(rts, np.maximum(secs, 0))
                            last_st, hi_t, hi_rt = st0, t0, rt0
                            for s_, r_, k_ in zip(secs, rts, stat):
                                if k_ != last_st:
                                    hi = cur if hi_t == t0 else pt(dict(cs, t_rem=hi_t, rt_diff=hi_rt), bk=bk)
                                    if hi is not cur:
                                        link(bk, seq - 0.8, "clock", "clock", "", cur, hi)
                                    if s_ == t1:
                                        lo = pb_
                                    elif s_ <= 0:
                                        lo = pt(dict(cs, t_rem=0.0, rt_diff=r_), end_value(cs["margin"], r_, wot))
                                    else:
                                        lo = pt(dict(cs, t_rem=s_, rt_diff=r_), bk=bk)
                                    who = "w" if hi_rt > 0 or (hi_rt == 0 and r_ > 0) else "l"
                                    link(bk, seq - 0.6, "rt_lock", "riding_time", who, hi, lo)
                                    cur, last_st = lo, k_
                                hi_t, hi_rt = s_, r_
                    if cur is not pb_:
                        link(bk, seq - 0.4, "clock", "clock", "", cur, pb_)
                elif abs(cur["v"] - wb) > 1e-12:   # (regulation -> overtime, overtime -> overtime: no change)
                    link(bk, seq - 0.4, "clock", "overtime" if secn == "ot" else "clock", "", cur, pb_)

            # ---- the event
            if secn == "ot":
                cat = "overtime"
            elif et in SCORING:
                cat = "scoring"
            elif et in CHOICE:
                cat = "choice"
            elif et == "choice":
                cat = "position"
            elif et in TERMINAL:
                cat = "terminal"
            elif et == "regulation_end":
                cat = "riding_time" if E.at[i, "points"] > 0 else "end_of_regulation"
            else:
                cat = "other"
            sub, bene, cred = "", "", actor or "w"
            if et == "near_fall":
                sub = f"nf{int(E.at[i, 'points'])}"
            if et == "penalty":
                bene, cred = actor, ("l" if actor == "w" else "w")
                sub = ("stalling" if i > s0 and E.at[i - 1, "event"] == "stalling" and E.at[i - 1, "actor"] == cred
                       and E.at[i - 1, "b_t_rem"] == E.at[i, "b_t_rem"] else "penalty")
            pa_ = pt(sa, wa)
            link(bk, seq, et, cat, cred, pb_, pa_, sub=sub, bene=bene, tsrc=E.at[i, "time_src"])
            cur, prev_sec = pa_, secn
            if wa == 1.0 and (et in TERMINAL or et == "regulation_end" or secn == "ot"):
                done = True
        if use_otm and ot_rows and not done:
            evs = [{"seq": E.at[i, "seq"], "event": E.at[i, "event"],
                    "actor": E.at[i, "actor"] if isinstance(E.at[i, "actor"], str) else "",
                    "points": E.at[i, "points"], "ot_period": OTP[i], "ot_clock": OTC[i], "raw_text": RAW[i]}
                   for i in ot_rows]
            if abs(cur["v"] - wot) > 1e-9:
                raise ValueError(f"{bk}: regulation ends at {cur['v']:.4f}, overtime starts at {wot:.4f}")
            for lk in otm.chain(evs, oti.loc[bk].to_dict(), float(rs_[bk]), int(tdp[nb.index.get_loc(bk)]),
                                holder[bk], wot):
                st2 = dict(lk["sa"], period=np.nan)
                nxt = pt(st2, lk["va"])
                et, act = lk["etype"], lk["actor"]
                bene, cred = "", act
                if et == "penalty":
                    bene, cred = act, ("l" if act == "w" else "w")
                link(bk, lk["seq"], et, "overtime", cred, cur, nxt, sub=lk["sa"]["period"], bene=bene)
                cur = nxt
            done = cur["v"] >= 1 - 1e-12
        if not done:
            if abs(cur["v"] - wot) < 1e-12:
                link(bk, E.at[e0 - 1, "seq"] + 0.5, "overtime", "overtime", "w", cur, pt(cur["s"], 1.0))
            else:
                raise ValueError(f"{bk}: chain ends at WP {cur['v']:.3f}, not decided")

    # value the points inside clock stretches (one batch)
    if pending:
        X = pd.DataFrame([p_["s"] for p_ in pending])
        bk_ = [p_["bk"] for p_ in pending]
        X["era_group"] = np.where(nb.loc[bk_, "year"].to_numpy() >= 2024, "E3", "E12")
        X["seed_a"] = nb.loc[bk_, "w_seed"].astype(float).to_numpy()
        X["seed_b"] = nb.loc[bk_, "l_seed"].astype(float).to_numpy()
        X["kind"] = nb.loc[bk_, "kind"].to_numpy()
        for p_, v in zip(pending, wp_of(m, X)):
            p_["v"] = float(v)
    for r in rows:
        pa_, pb_ = r.pop("_pa"), r.pop("_pb")
        sa, sb = pa_["s"], pb_["s"]
        r.update({"wp_w_before": pa_["v"], "wp_w_after": pb_["v"], "t_before": sa["t_rem"], "t_after": sb["t_rem"],
                  "period": sa["period"], "pos_w_before": sa["pos"], "pos_w_after": sb["pos"],
                  "choice_w_before": sa["choice"], "margin_w_before": sa["margin"], "margin_w_after": sb["margin"],
                  "rt_w_before": sa["rt_diff"], "rt_w_after": sb["rt_diff"]})
    out = pd.DataFrame(rows)
    out["wpa_w"] = out["wp_w_after"] - out["wp_w_before"]
    return out, wp_start, wp_ot, n_noflip


# ---------------------------------------------------------------------------------------------------------------
def credit(out, nb):
    """Adds the credited wrestler's side (wrestler / opponent, wp_before / wp_after / wpa, his state)."""
    o = out.copy()
    # clock rows: the leader at the start of the stretch (tied: the model's favourite)
    clk = o["event_type"].isin(["clock", "overtime"]) & (o["actor"] == "")
    lead = np.where(o["margin_w_before"] > 0, "w", np.where(o["margin_w_before"] < 0, "l",
                    np.where(o["wp_w_before"] >= 0.5, "w", "l")))
    o.loc[clk, "actor"] = lead[clk.to_numpy()]
    aw = (o["actor"] == "w").to_numpy()
    sg = np.where(aw, 1.0, -1.0)
    flip_pos = {"A_top": "A_bottom", "A_bottom": "A_top"}
    flip_ch = {"A": "B", "B": "A"}
    b = nb.loc[o["bout_key"]]
    o["wrestler"] = np.where(aw, b["w_name"], b["l_name"])
    o["team"] = np.where(aw, b["w_team"], b["l_team"])
    o["opponent"] = np.where(aw, b["l_name"], b["w_name"])
    o["opponent_team"] = np.where(aw, b["l_team"], b["w_team"])
    o["seed"] = np.where(aw, b["w_seed_raw"], b["l_seed_raw"])
    o["opponent_seed"] = np.where(aw, b["l_seed_raw"], b["w_seed_raw"])
    o["won"] = aw
    o["wp_before"] = np.where(aw, o["wp_w_before"], 1 - o["wp_w_before"])
    o["wp_after"] = np.where(aw, o["wp_w_after"], 1 - o["wp_w_after"])
    o["wpa"] = sg * o["wpa_w"]
    for s in ("before", "after"):
        o[f"margin_{s}"] = sg * o[f"margin_w_{s}"]
        o[f"rt_{s}"] = sg * o[f"rt_w_{s}"]
    o["pos_before"] = [p if w else flip_pos.get(p, p) for p, w in zip(o["pos_w_before"], aw)]
    o["pos_after"] = [p if w else flip_pos.get(p, p) for p, w in zip(o["pos_w_after"], aw)]
    o["choice_before"] = [c if w else flip_ch.get(c, c) for c, w in zip(o["choice_w_before"], aw)]
    o["beneficiary"] = np.where(o["beneficiary"] == "w", b["w_name"], np.where(o["beneficiary"] == "l",
                                                                                b["l_name"], ""))
    for c in ("kind", "tournament", "year", "weight", "round", "bracket", "match_id", "result_class", "rt_consistent"):
        o[c] = b[c].to_numpy()
    o["side"] = np.where(aw, "w", "l")
    keep = ["bout_key", "kind", "tournament", "year", "weight", "round", "bracket", "match_id", "seq", "event_type",
            "subtype", "category", "wrestler", "team", "seed", "opponent", "opponent_team", "opponent_seed", "side",
            "won", "beneficiary", "period", "t_before", "t_after", "margin_before", "margin_after", "pos_before",
            "pos_after", "choice_before", "rt_before", "rt_after", "wp_before", "wp_after", "wpa", "wp_w_before",
            "wp_w_after", "wpa_w", "time_src", "result_class", "rt_consistent"]
    return o[keep].sort_values(["bout_key", "seq"]).reset_index(drop=True)


def wrestler_table(o, nb, wp_start):
    """Per wrestler per tournament, both sides of every link (zero-sum within a bout). `seed` is the NCAA seed, or
    the national rank for a conference tournament (kind = conf)."""
    base = o[["bout_key", "kind", "tournament", "year", "weight", "category", "event_type", "side", "wpa_w", "pos_before",
              "wrestler"]].copy()
    parts = []
    for side, sg in (("w", 1.0), ("l", -1.0)):
        d = base.copy()
        b = nb.loc[d["bout_key"]]
        d["name"] = (b["w_name"] if side == "w" else b["l_name"]).to_numpy()
        d["team_"] = (b["w_team"] if side == "w" else b["l_team"]).to_numpy()
        d["seed_"] = (b["w_seed_raw"] if side == "w" else b["l_seed_raw"]).to_numpy()
        d["v"] = sg * d["wpa_w"]
        d["own"] = d["side"] == side
        pos = d["pos_before"].astype(str)
        if side == "l":
            pos = pos.map(lambda p: {"A_top": "A_bottom", "A_bottom": "A_top"}.get(p, p))
        d["posg"] = np.select([d["category"] == "overtime", pos == "A_top", pos == "A_bottom", pos == "neutral"],
                              ["ot", "top", "bottom", "neutral"], "break")
        parts.append(d)
    d = pd.concat(parts, ignore_index=True)
    g = ["kind", "tournament", "year", "weight", "name", "team_"]
    res = d.groupby(g).agg(seed=("seed_", "first"), wpa_total=("v", "sum")).reset_index()
    by = lambda col, pre: d.pivot_table(index=g, columns=col, values="v", aggfunc="sum", fill_value=0.0)\
        .add_prefix(pre).reset_index()
    res = res.merge(by("category", "wpa_"), on=g).merge(by("posg", "wpa_pos_"), on=g)
    sc = d[d["category"] == "scoring"]
    own = sc[sc["own"]].groupby(g)["v"].sum().rename("wpa_scoring_own")
    opp = sc[~sc["own"]].groupby(g)["v"].sum().rename("wpa_scoring_opponent")
    res = res.merge(own, on=g, how="left").merge(opp, on=g, how="left").fillna({"wpa_scoring_own": 0.0,
                                                                                 "wpa_scoring_opponent": 0.0})
    # bouts, wins, expected wins at the opening whistle
    bw = nb[nb.index.isin(o["bout_key"].unique())]
    kt = {"kind": bw["kind"], "tournament": bw["tournament"], "year": bw["year"], "weight": bw["weight"]}
    rec = pd.concat([pd.DataFrame(kt | {"name": bw["w_name"], "team_": bw["w_team"], "win": 1,
                                        "wp0": wp_start.loc[bw.index]}),
                     pd.DataFrame(kt | {"name": bw["l_name"], "team_": bw["l_team"], "win": 0,
                                        "wp0": 1 - wp_start.loc[bw.index]})])
    rec = rec.groupby(g).agg(bouts=("win", "size"), wins=("win", "sum"), expected_wins=("wp0", "sum")).reset_index()
    res = rec.merge(res, on=g).rename(columns={"team_": "team"})
    res["wins_minus_expected"] = res["wins"] - res["expected_wins"]
    return res


# ---------------------------------------------------------------------------------------------------------------
def load_bouts(kind):
    """Bouts + events of one kind. Conference bouts carry NATIONAL RANK in the seed columns (step 10, conf_ranks.py;
    NaN = unranked); wp_model reads them on the conference scale because kind == 'conf'."""
    nb = pd.read_csv(STATES / f"{kind}_bouts.csv", low_memory=False).set_index("bout_key")
    nb["kind"] = kind
    if kind == "conf":
        cr = pd.read_csv(STATES / "conf_ranks.csv").set_index("bout_key")
        for side in ("w", "l"):
            nb[f"{side}_seed"] = cr[f"{side}_rank"].reindex(nb.index)
            nb[f"{side}_seed_raw"] = nb[f"{side}_seed"]
        nb["rank_leak_free"] = cr["leak_free"].reindex(nb.index)
    # NCAA: w_seed / l_seed in the bouts file are already strength seeds (wpa_common.strength_seed: pre-2019 17-33 = NaN)
    ev = pd.read_csv(STATES / f"{kind}_events.csv", low_memory=False)
    return nb, ev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", default="both", choices=["ncaa", "conf", "both"])
    args = ap.parse_args()
    t0 = time.time()
    kinds = ["ncaa", "conf"] if args.kind == "both" else [args.kind]
    parts = [load_bouts(k) for k in kinds]
    nb = pd.concat([p_[0] for p_ in parts])
    ev = pd.concat([p_[1] for p_ in parts], ignore_index=True)
    ok = nb.index[nb["table_ok"] == True]  # noqa: E712
    ev = ev[ev["bout_key"].isin(ok)]
    m = W.WPModel()
    out, wp_start, wp_ot, n_noflip = build(m, nb.loc[ok], ev)
    print(f"chain built: {len(out):,} links, {out['bout_key'].nunique():,} bouts ({time.time() - t0:.0f}s)",
          flush=True)
    o = credit(out, nb)
    OUT.mkdir(parents=True, exist_ok=True)
    o.to_parquet(OUT / "events_wpa.parquet", index=False)
    wt = wrestler_table(o, nb, wp_start)
    wt.to_csv(OUT / "wrestler_wpa.csv", index=False, float_format="%.4f")
    nk = nb.loc[ok, "kind"]
    if "ncaa" in kinds:
        n_ok = nk.index[nk == "ncaa"]
        report(o[o["kind"] == "ncaa"], wt[wt["kind"] == "ncaa"], nb.loc[n_ok], wp_start.loc[n_ok], wp_ot.loc[n_ok],
               n_noflip)
    if "conf" in kinds:
        c_ok = nk.index[nk == "conf"]
        L = conf_report(o[o["kind"] == "conf"], wt[wt["kind"] == "conf"], nb.loc[c_ok])
        with open(REP, "a") as f:
            f.write("\n".join(L) + "\n")
    print(f"wrote {OUT}/events_wpa.parquet, wrestler_wpa.csv, {REP} ({time.time() - t0:.0f}s)")


def conf_report(o, wt, nb):
    """Conference section of wpa.md (step 10)."""
    L = ["\n## Conference tournaments (step 10)\n",
         f"{nb.shape[0]:,} conference bouts ({', '.join(f'{k} {v}' for k, v in nb['tournament'].value_counts().items())}), "
         "same chain and crediting as NCAA. Strength input = national rank (`conf_ranks.py`): leak-free Flo snapshots "
         "from 2023; **before 2023 the end-of-season rank, which leaks NCAA results (TJ decision E) — opening WPs and "
         "expected wins for those seasons are sharper than a live model could have been.** Riding time is unreliable "
         "in six conference tournaments (ACC 2024/25, Pac-12 2020/26, MAC 2017, Big 12 2020); their bouts are left out "
         "of the state table (`table_ok`) and so of this chain.\n"]
    sc = o[o["category"] == "scoring"]
    neg = sc[(sc["wpa"] < -1e-9) & (sc["event_type"] != "penalty")]
    L.append(f"- Negative scoring WPA: {len(neg):,} of {len(sc):,} scoring events; largest {(-neg['wpa']).max() if len(neg) else 0:.4f}.")
    td = sc[sc["event_type"] == "takedown"]
    L.append("- Mean WPA of a takedown: " + ", ".join(
        f"{lab} {100 * td.loc[m_, 'wpa'].mean():+.1f} pts" for lab, m_ in
        (("2015–23", td["year"] < 2024), ("2024–26", td["year"] >= 2024))) + " (NCAA figures above).\n")
    lf = wt[wt["year"] >= 2023].sort_values("wins_minus_expected", ascending=False)
    L.append("**Most wins above expectation in one conference tournament, leak-free seasons (2023+):**\n")
    L.append("| Year | Tournament | Weight | Wrestler | Team | Rank | Bouts | Wins | Expected | WPA |\n"
             "|---:|---|---:|---|---|---:|---:|---:|---:|---:|")
    for r in lf.head(10).itertuples():
        rk = "—" if pd.isna(r.seed) else int(r.seed)
        L.append(f"| {r.year} | {r.tournament} | {r.weight} | {r.name} | {r.team} | {rk} | {r.bouts} | {r.wins} | "
                 f"{r.expected_wins:.2f} | {r.wpa_total:+.2f} |")
    return L


def pct(x, d=1):
    return f"{100 * x:.{d}f}%"


def pts(x, d=1):
    return f"{100 * x:+.{d}f}"


def md(df):
    cols = list(df.columns)
    num = [pd.api.types.is_numeric_dtype(df[c]) or df[c].astype(str).str.match(r"^[+\-−]?[\d.,]+%?( \(|$)").all()
           for c in cols]
    out = ["| " + " | ".join(map(str, cols)) + " |", "|" + "|".join("---:" if n else "---" for n in num) + "|"]
    out += ["| " + " | ".join(map(str, r)) + " |" for r in df.itertuples(index=False)]
    return "\n".join(out)


def report(o, wt, nb, wp_start, wp_ot, n_noflip):
    L = []
    A = L.append
    o = o.copy()
    o["era"] = np.where(o["year"] >= 2024, "2024–26", "2015–23")
    first = o.groupby("bout_key")["wp_w_before"].first()
    err = (o.groupby("bout_key")["wpa_w"].sum() - (1 - first)).abs().max()
    nxt = o.groupby("bout_key")["wp_w_before"].shift(-1)
    gap = (nxt - o["wp_w_after"]).abs().max()
    wterr = (wt["wpa_total"] - wt["wins_minus_expected"]).abs().max()
    sc = o[(o["category"] == "scoring") & (o["event_type"] != "penalty")]
    neg = sc[sc["wpa"] < -1e-9]
    re_ = o[(o["event_type"] == "regulation_end") & (o["wpa_w"].abs() > 1e-9)]
    n_b = o["bout_key"].nunique()

    A("# WPA step 9 — win probability added\n")
    A("Generated by `scripts/wpa/compute_wpa.py` (spec Section 6) with the final model (`wp_model.py`: state model + "
      "seed layer, validated in `validation.md`). Every NCAA bout that feeds the state table "
      f"({n_b:,} bouts, 2015–2026) is one chain of win probabilities from the opening whistle to the result: "
      "every event, every quiet stretch of clock between events, and the second the riding-time point stops being "
      "live. Each link's WPA = WP after − WP before, from the side of the wrestler credited with it. Rows: "
      "`data/wpa/output/events_wpa.parquet`; per wrestler per tournament: `data/wpa/output/wrestler_wpa.csv`.\n")
    A("Crediting (spec 6): scores go to the scorer; a penalty or stalling point goes to the wrestler who committed "
      "it (negative), with the beneficiary recorded; choices to the chooser; clock stretches to the leader at the "
      "start of the stretch; a riding-time lock to the wrestler with the riding-time advantage. A tech fall is two "
      "rows (the score that reached 15, valued like any score, then the remainder to 1). **Overtime** (spec 2.4): "
      "current rules (2022+) use the overtime model (`ot_model.py`, report `ot_model.md`): sudden victory by the "
      "clock, tiebreaker rides by position / points / tiebreaker riding time, `ot_choice` rows for the ride picks, "
      "later rounds one value. Before 2022, tied = the overtime win rate (with the seed term), flat until the "
      "winner's last score in overtime.\n")

    A("## Sanity checks (spec 6.2)\n")
    A(f"- **Sum rule:** each bout's WPA sums to result − WP at the opening whistle for both wrestlers: largest "
      f"error {err:.1e} over {n_b:,} bouts; consecutive links meet exactly (largest gap {gap:.1e}); per wrestler "
      f"per tournament, total WPA = wins − expected wins (largest error {wterr:.1e}).")
    A(f"- **Negative scoring WPA:** {len(neg)} of {len(sc):,} scoring events (penalty points excluded — those are "
      "credited to the offender) lower the scorer's WP" + (f"; largest {-neg['wpa'].min():.4f}." if len(neg)
                                                             else "."))
    if len(neg):
        dec = ((neg["wp_before"] < 0.01) | (neg["wp_before"] > 0.99)).sum()
        A(f"  All are {-100 * neg['wpa'].min():.2f} WP points or less, and {dec} of the {len(neg)} are in bouts already "
          "decided (the scorer below 1% or above 99%): rounding-level moves where the seed layer and the table's "
          "projections meet, not wrong-way values. Worst five:")
    for r in neg.sort_values("wpa").head(5).itertuples():
        A(f"  - {r.bout_key} {r.event_type} at {int(r.t_before)} s left, margin {r.margin_before:+.0f}, "
          f"{r.pos_before} → {r.pos_after}, riding time {r.rt_before:+.0f}: {pct(r.wp_before, 2)} → "
          f"{pct(r.wp_after, 2)}.")
    A(f"- **Riding-time point at the end of regulation:** the lock logic prices the point in before the buzzer, so "
      f"applying it adds nothing — except in {re_['bout_key'].nunique()} bouts whose rebuilt riding time disagrees "
      "with the official point (all flagged `rt_consistent = False`); there the official point is applied at "
      "the buzzer and carries the correction.")
    A(f"- Riding-time locks found inside clock stretches: {(o['event_type'] == 'rt_lock').sum():,}; "
      f"{n_noflip} stretches where the status changed across a period break without a break event were left whole "
      "(their lock stays in the clock row).\n")

    A("## What each event is worth\n")
    A("Mean WPA to the credited wrestler, by rules era (the 3-point takedown arrived in 2024). Penalty and stalling "
      "points are from the offender's side.\n")
    ev = o[o["category"].isin(["scoring", "terminal"])].copy()
    ev["label"] = np.select([ev["event_type"] == "near_fall", ev["event_type"] == "penalty"],
                            ["near fall " + ev["subtype"].str[2:], ev["subtype"] + " point (offender)"],
                            ev["event_type"])
    g = ev.groupby(["label", "era"])["wpa"].agg(["size", "mean"]).unstack("era")
    tab = pd.DataFrame({"Event": g.index,
                        "Count 2015–23": g[("size", "2015–23")].fillna(0).astype(int).map("{:,}".format),
                        "Mean WPA 2015–23": g[("mean", "2015–23")].map(lambda x: pts(x) if pd.notna(x) else "—"),
                        "Count 2024–26": g[("size", "2024–26")].fillna(0).astype(int).map("{:,}".format),
                        "Mean WPA 2024–26": g[("mean", "2024–26")].map(lambda x: pts(x) if pd.notna(x) else "—")})
    order = ["takedown", "escape", "reversal", "near fall 2", "near fall 3", "near fall 4",
             "stalling point (offender)", "penalty point (offender)", "fall", "tech_fall", "injury", "dq"]
    tab = tab.set_index("Event").reindex([x for x in order if x in tab["Event"].values]).reset_index()
    A(md(tab))
    A("\nWPA points = percentage points of win probability. A fall's WPA is whatever was left to reach 100%; a "
      "tech fall row is only the remainder after the score that reached 15.\n")

    A("**Takedowns by situation** (mean WPA, 2024–26; margin = the scorer's margin before the takedown):\n")
    td = o[(o["event_type"] == "takedown") & (o["year"] >= 2024)].copy()
    td["when"] = np.select([td["period"] == 1, td["period"] == 2, td["t_before"] > 60],
                           ["period 1", "period 2", "period 3, before the last minute"], "last minute")
    td["mb"] = td["margin_before"].clip(-4, 4).astype(int)
    pv = td.pivot_table(index="when", columns="mb", values="wpa", aggfunc="mean")
    pv = pv.reindex(["period 1", "period 2", "period 3, before the last minute", "last minute"])
    t2 = pd.DataFrame({"When": pv.index})
    for c in pv.columns:
        lab = f"{'≤ ' if c == -4 else '≥ ' if c == 4 else ''}{c:+d}" if c else "tied"
        t2[lab] = [pts(x, 0) if pd.notna(x) else "—" for x in pv[c]]
    A(md(t2) + "\n")

    A("## Choices (spec 6.1)\n")
    ch = o[o["category"] == "choice"].copy()
    toss = ch[ch["event_type"] == "toss"]
    dfr = ch[ch["event_type"] == "defer"]
    A(f"- **Winning the coin toss** (at the start of period 2): mean {pts(toss['wpa'].mean(), 2)} WPA points "
      f"({len(toss):,} tosses).")
    A(f"- **Deferring** (toss winner takes the period-3 choice instead): mean {pts(dfr['wpa'].mean(), 2)}; by era "
      + ", ".join(f"{e} {pts(v, 2)}" for e, v in dfr.groupby("era")["wpa"].mean().items())
      + f" ({len(dfr):,} defers of {len(toss):,} tosses). Negative = on average the state after deferring was worth "
      "less than the toss winner's state before deciding (which averages over the wrestlers who picked right away).\n")
    pk = ch[ch["event_type"] == "choose"].copy()
    pk["pick"] = pk["pos_after"].map({"A_top": "top", "A_bottom": "bottom", "neutral": "neutral"})
    pk["mb"] = np.select([pk["margin_before"] <= -2, pk["margin_before"] == -1, pk["margin_before"] == 0,
                          pk["margin_before"] == 1], ["down 2+", "down 1", "tied", "up 1"], "up 2+")
    for per in (2, 3):
        d = pk[pk["period"] == per]
        pv = d.pivot_table(index="mb", columns="pick", values="wpa", aggfunc=["mean", "size"])
        pv = pv.reindex(["down 2+", "down 1", "tied", "up 1", "up 2+"])
        t3 = pd.DataFrame({"Chooser's margin": pv.index})
        for c in ("bottom", "top", "neutral"):
            t3[f"Picks {c}"] = [f"{pts(mn)} ({int(n):,})" if pd.notna(mn) and n >= 10 else "—" for mn, n in
                                zip(pv[("mean", c)], pv[("size", c)])]
        A(f"**Period-{per} choice** (mean WPA of the pick, count in brackets; all years):\n")
        A(md(t3) + "\n")
    A("The WPA of a pick compares it with the average of what choosers in that state actually did, so a strongly "
      "negative cell means that pick is usually the wrong one there.\n")

    A("## Riding time\n")
    lk = o[o["event_type"] == "rt_lock"]
    A(f"{len(lk):,} riding-time locks (the second the point stops being live). Mean |WPA| {pts(lk['wpa'].abs().mean(), 2)}, "
      f"largest {pts(lk['wpa'].abs().max())} points. Riding out a period shows up mostly as top-position clock "
      "WPA (below), not in the lock itself: the point's chance is priced continuously as time passes.\n")

    A("## Where a wrestler's WPA comes from\n")
    A("Per wrestler per tournament, total WPA = wins − expected wins at the opening whistle (the seed layer's "
      "pre-match odds). Mean over all wrestler-tournaments of each part (they sum to ~0 overall, since every bout "
      "is zero-sum):\n")
    parts = [c for c in wt.columns if c.startswith("wpa_pos_")]
    A(md(pd.DataFrame({"Position": [c[8:] for c in parts],
                       "Mean |WPA| per wrestler-tournament": [f"{wt[c].abs().mean():.3f}" for c in parts]})))
    A("\n(top / bottom / neutral = WPA from events and clock that START in that position, from the wrestler's side; "
      "break = coin toss and period choices; ot = overtime.)\n")

    A("## Leaders\n")
    show = ["year", "weight", "name", "team", "seed", "bouts", "wins", "expected_wins", "wpa_total",
            "wpa_scoring_own", "wpa_pos_top", "wpa_pos_bottom", "wpa_pos_neutral"]
    fmt = wt[show].copy()
    for c in show[7:]:
        fmt[c] = fmt[c].map(lambda x: f"{x:+.2f}" if c != "expected_wins" else f"{x:.2f}")
    fmt["seed"] = wt["seed"].map(lambda x: "—" if pd.isna(x) else f"{int(x)}")
    top = fmt.loc[wt["wpa_total"].sort_values(ascending=False).index].head(15)
    A("**Most WPA in one NCAA tournament** (= wins above what the seeds expected):\n")
    A(md(top.rename(columns={"expected_wins": "expected", "wpa_total": "WPA", "wpa_scoring_own": "own scoring",
                             "wpa_pos_top": "top", "wpa_pos_bottom": "bottom", "wpa_pos_neutral": "neutral"})))
    A("\n**2026**:\n")
    t26 = fmt.loc[wt[wt["year"] == 2026]["wpa_total"].sort_values(ascending=False).index].head(10)
    A(md(t26.rename(columns={"expected_wins": "expected", "wpa_total": "WPA", "wpa_scoring_own": "own scoring",
                             "wpa_pos_top": "top", "wpa_pos_bottom": "bottom", "wpa_pos_neutral": "neutral"})))

    A("\n**Biggest single plays** (all years):\n")
    bp = o[o["category"].isin(["scoring", "terminal", "riding_time", "overtime"])].sort_values("wpa", ascending=False)
    bp = bp.drop_duplicates("bout_key").head(12)
    A(md(pd.DataFrame({"Bout": bp["year"].astype(str) + " " + bp["weight"].astype(str) + " " + bp["round"].fillna(""),
                       "Wrestler": bp["wrestler"] + " (" + bp["team"] + ")",
                       "Event": bp["event_type"] + np.where(bp["subtype"] != "", " " + bp["subtype"], ""),
                       "Situation": [f"{'P' + str(int(pp)) if pd.notna(pp) else 'OT'} {int(t) // 60}:{int(t) % 60:02d}, "
                                     f"margin {mg:+.0f}" for pp, t, mg in zip(bp["period"], bp["t_before"],
                                                                              bp["margin_before"])],
                       "WP": [f"{pct(a, 0)} → {pct(b, 0)}" for a, b in zip(bp["wp_before"], bp["wp_after"])]})))
    wmin = o.groupby("bout_key").agg(start=("wp_w_before", "first"), low=("wp_w_before", "min"))
    rtok = nb["rt_consistent"].reindex(wmin.index).fillna(True).astype(bool)
    up = wmin.sort_values("start").head(8)
    b = nb.loc[up.index]
    A("\n**Biggest upsets** (lowest winner's WP at the opening whistle):\n")
    A(md(pd.DataFrame({"Bout": b["year"].astype(str) + " " + b["weight"].astype(str) + " " + b["round"].fillna(""),
                       "Winner": b["w_name"] + " (" + b["w_seed_raw"].map(lambda x: "unseeded" if pd.isna(x)
                                                                          else f"#{int(x)}") + ")",
                       "Loser": b["l_name"] + " (" + b["l_seed_raw"].map(lambda x: "unseeded" if pd.isna(x)
                                                                         else f"#{int(x)}") + ")",
                       "Result": b["result_type"] + " " + b["final_w"].astype(str) + "-" + b["final_l"].astype(str),
                       "Winner's WP at the whistle": up["start"].map(pct).to_numpy()})))
    cb = wmin[rtok].sort_values("low").head(8)
    b = nb.loc[cb.index]
    A("\n**Biggest comebacks** (lowest WP the eventual winner fell to; bouts whose rebuilt riding time disagrees "
      "with the official point left out — there the chain can show the winner beaten at the buzzer before the "
      "official point is applied):\n")
    A(md(pd.DataFrame({"Bout": b["year"].astype(str) + " " + b["weight"].astype(str) + " " + b["round"].fillna(""),
                       "Winner": b["w_name"] + " (" + b["w_team"] + ")", "Loser": b["l_name"] + " (" + b["l_team"] + ")",
                       "Result": b["result_type"] + " " + b["final_w"].astype(str) + "-" + b["final_l"].astype(str),
                       "Lowest WP": cb["low"].map(lambda x: pct(x, 2)).to_numpy()})))
    A("\n## Known data issue\n")
    A("NCAA 2018 197 lbs has two bouts listed as \"QF, Kyle Conel over Kollin Moore\": the real one (Dec 5-3) and a "
      "two-event \"Fall 2-0\" (match 8962577104); a similar two-event \"Fall 2-0\" is listed for Conel over Jacob "
      "Holschlag (C_SF). They come from the scraped bracket, not this step — worth checking against the official "
      "bracket before anything here is published.\n")
    REP.write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
