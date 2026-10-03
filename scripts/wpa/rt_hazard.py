#!/usr/bin/env python3
"""
The riding-time point model, simple version (TJ, 2026-09-29): P(A gets the point), P(nobody), P(B gets it) from a
handful of per-second rates and an exact dynamic program over the rest of regulation. Replaces the step-8 boosted-tree
classifier, which didn't know the physics and needed patch after patch (and still said 69% on the knife edge
"A up 1, 0:05 left, on top, needs all 5 seconds" where the data says ~90%).

Rates, per rules era (E12 = 2015-23, E3 = 2024-26), estimated from the play-by-play of the training bouts (event
counts / seconds spent in the position; bouts whose rebuilt riding time matches the official point only):
  * on the mat, per second: the bottom man escapes (+1), reverses (+2); the top man scores near-fall points (share of
    2 / 3 / 4 from the data)
  * in neutral, per second and per wrestler: a takedown (+2, or +3 from 2024)
  * the bout ends by fall, injury or DQ -- per second, by position (neutral / on the mat) and the size of the lead
    (0-3, 4-7, 8+). A tech fall needs no rate: it happens when the margin reaches 15. The label r is "nobody" when a
    bout ends early, so ending early is part of the model.
  * period picks: share of top / bottom / neutral by period (2, 3); the toss winner's defer share.
  Variants (`how`) -- what else a rate or pick share depends on, from the side of the wrestler concerned, at that
  moment: None = era only; "sign" / "size" / "size3" = his margin (leading / tied / trailing; "size" splits at 4
  points, "size3" at 4 and 8 -- a big lead means a mismatch); "rt" = his riding-time lead (even, 0:15-0:59, 1:00+;
  a wrestler who has already ridden a lot is a good rider and keeps riding: skill persists, and without this the
  model treats every top man as average); "<margin>+rt" = both. Thin pick / defer cells lean on the pooled shares.

The program runs backward from the end of regulation, second by second, over (position, margin, riding-time
differential). At 0:00: A's point = 1 if the differential is >= 60 s (wpa_common.RT_THRESHOLD). In each second the
bout ends early (value 0) with the end rate; otherwise a move happens with the rates above (moving position and
margin; a margin of 15 = tech fall = value 0), then the second's riding time goes to whoever is on top. Period breaks
(2:00 and 4:00 left) replace position with the pick distribution of whoever holds the choice -- recorded in the state
when it's known (period 2: the period-3 chooser; break states: the toss winner / the chooser), 50/50 before the toss.
B's point is the same program on the mirrored state. Locked states come out exact by construction (0 when the clock
rules the point out; P(no early end) when it can't be lost -- fit_state_model.rt_probs then sets that to 1, since the
table counts a locked point as scored), and the result is monotone in the differential and in A
being on top without any constraint. Penalty / stalling points are left out of the margin moves (rare).

Parameters are a small JSON (data/wpa/model/rt_params.json). Interface (used by fit_state_model.fit_rt / rt_probs):
fit(training bout keys, how) -> params dict; probs(params, df) -> (pA, pN, pB).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts/wpa"))
import wpa_common as C  # noqa: E402

STATES = ROOT / "data/wpa/states"
ERAS = ["E12", "E3"]
MARGIN_EDGES = {"size": [4], "size3": [4, 8]}   # "size": leading / trailing by 1-3 or 4+; "size3": 1-3, 4-7, 8+
RT_EDGES = [15, 60]                 # "rt": the wrestler's riding-time lead: even (under 0:15), 0:15-0:59, 1:00+
TF = 15                             # tech-fall margin
LEAD_BUCKETS = [0, 4, 8]            # size of the lead for the fall / injury / DQ rate: 0-3, 4-7, 8+
TD_POINTS = {"E12": 2, "E3": 3}
NF_POINTS = [2, 3, 4]
OFF = 490                           # riding-time grid: -OFF .. +OFF seconds
PICKS = ["top", "bottom", "neutral"]

_DATA = None


# ---------------------------------------------------------------------------------------------------------------
# data: time segments between events, the moves, the picks and the tosses (winner-oriented w / l)
# ---------------------------------------------------------------------------------------------------------------
def _load():
    global _DATA
    if _DATA is not None:
        return _DATA
    parts = []
    for kind in ("ncaa", "conf"):
        b = pd.read_csv(STATES / f"{kind}_bouts.csv", usecols=["bout_key", "era", "end_t_rem", "result_class"])
        e = pd.read_csv(STATES / f"{kind}_events.csv",
                        usecols=["bout_key", "seq", "section", "event", "actor", "points", "b_t_rem", "a_t_rem",
                                 "a_period", "b_margin", "a_margin", "b_pos", "a_pos", "b_rt_diff",
                                 "a_rt_diff"])
        parts.append(e[e["section"] == "reg"].merge(b, on="bout_key"))
    e = pd.concat(parts, ignore_index=True).sort_values(["bout_key", "seq"], kind="stable")
    e["a_period"] = pd.to_numeric(e["a_period"], errors="coerce")   # mixed with OT labels in the raw file
    e["eg"] = np.where(e["era"] == "E3", "E3", "E12")
    g = e.groupby("bout_key", sort=False)
    seg = pd.DataFrame({"bout_key": e["bout_key"], "eg": e["eg"],
                        "dur": g["a_t_rem"].shift(1).fillna(C.T_TOTAL) - e["b_t_rem"],
                        "pos": g["a_pos"].shift(1).fillna("neutral"), "m": g["a_margin"].shift(1).fillna(0),
                        "rt": g["a_rt_diff"].shift(1).fillna(0)})
    # the segment in which a bout stopped by fall / injury / DQ: the one ending at the first event at the end time
    early = (e["result_class"].isin(["fall", "injury", "dq"]) & (e["end_t_rem"] > 0)
             & (e["b_t_rem"] == e["end_t_rem"]))
    seg["end"] = (early & (early.groupby(e["bout_key"]).cumsum() == 1)).to_numpy()
    seg = seg[((seg["dur"] > 0) | seg["end"]) & (seg["pos"] != "pending")]
    ev = e["event"]
    moves = e[((ev == "takedown") & (e["b_pos"] == "neutral") & (e["a_pos"] != "neutral"))
              | (ev.isin(["escape", "reversal"]) & e["b_pos"].isin(["w_top", "l_top"]) & (e["b_pos"] != e["a_pos"]))
              | ((ev == "near_fall") & e["b_pos"].isin(["w_top", "l_top"]))]
    picks = e[(ev == "choose") & e["a_period"].isin([2, 3])]
    toss = e[ev == "toss"][["bout_key", "seq", "actor", "b_margin", "b_rt_diff", "eg"]]
    nxt = e[["bout_key", "seq", "event", "actor"]].assign(seq=lambda d: d["seq"] - 1)
    toss = toss.merge(nxt, on=["bout_key", "seq"], how="left", suffixes=("", "_next"))
    toss["deferred"] = (toss["event"] == "defer") & (toss["actor_next"] == toss["actor"])
    _DATA = {"seg": seg, "moves": moves, "picks": picks, "toss": toss}
    return _DATA


def _own(m, who):
    """Margin from the named wrestler's side (who = 'w' / 'l' per row)."""
    return np.where(np.asarray(who) == "w", np.asarray(m), -np.asarray(m))


def _steps(x, edges):
    x = np.asarray(x, float)
    return (np.sign(x) * sum((np.abs(x) >= e).astype(int) for e in edges)).astype(int)


def _parts(how):
    """(margin part, riding-time part?) of a variant name: None | sign | size | size3 | rt | <margin>+rt"""
    if how is None:
        return None, False
    ps = how.split("+")
    return (None if ps[0] == "rt" else ps[0]), ps[-1] == "rt"


def level(m, rt, how):
    """The level a rate depends on, from the concerned wrestler's side (his margin m, his riding-time lead rt):
    code = 10 * margin level + riding-time level."""
    m, rt = np.broadcast_arrays(np.asarray(m, float), np.asarray(rt, float))
    mh, use_rt = _parts(how)
    ml = np.zeros(m.shape, int) if mh is None else np.sign(m).astype(int) if mh == "sign" else _steps(m, [1] + MARGIN_EDGES[mh])
    rl = _steps(rt, RT_EDGES) if use_rt else np.zeros(m.shape, int)
    return 10 * ml + rl


def _rt_levels(use_rt):
    return list(range(-len(RT_EDGES), len(RT_EDGES) + 1)) if use_rt else [0]


def levels(how):
    mh, use_rt = _parts(how)
    ml = [0] if mh is None else [-1, 0, 1] if mh == "sign" else list(range(-1 - len(MARGIN_EDGES[mh]), 2 + len(MARGIN_EDGES[mh])))
    return [10 * a + b for a in ml for b in _rt_levels(use_rt)]


def _exposure(m, r0, dur, moving, how):
    """Seconds at each level for segments with the concerned wrestler's margin m (constant) and riding-time lead
    starting at r0 -- rising 1 s per second when `moving` (he's on top), constant otherwise."""
    mh, use_rt = _parts(how)
    base = level(m, 0, mh)            # margin part of the code
    r0, dur = np.asarray(r0, float), np.asarray(dur, float)
    out = {}
    if not use_rt:
        for c in np.unique(base):
            out[int(c)] = float(dur[base == c].sum())
        return out
    b = [-np.inf] + [-e + 0.5 for e in RT_EDGES[::-1]] + [e - 0.5 for e in RT_EDGES] + [np.inf]
    r1 = r0 + np.where(moving, dur, 0)
    for i, lv in enumerate(_rt_levels(True)):
        sec = np.where(moving, np.clip(np.minimum(r1, b[i + 1]) - np.maximum(r0, b[i]), 0, None),
                       np.where((r0 >= b[i]) & (r0 < b[i + 1]), dur, 0))
        for c in np.unique(base):
            out[int(c) + lv] = out.get(int(c) + lv, 0.0) + float(sec[base == c].sum())
    return out


def fit(bout_keys, how="rt"):
    """Rates from the given (training, riding-time-consistent) bouts."""
    D = _load()
    keys = set(bout_keys)
    seg, mv, pk, ts = (D[k][D[k]["bout_key"].isin(keys)] for k in ("seg", "moves", "picks", "toss"))
    grp = levels(how)
    out = {"levels": how, "margin_edges": MARGIN_EDGES, "rt_edges": RT_EDGES, "rt_threshold": C.RT_THRESHOLD,
           "tech_fall": TF, "lead_buckets": LEAD_BUCKETS, "nf_points": NF_POINTS, "eras": {}}
    for eg in ERAS:
        s_, m_, p_, t_ = (x[x["eg"] == eg] for x in (seg, mv, pk, ts))
        top = s_[s_["pos"] != "neutral"]
        tw = np.where(top["pos"] == "w_top", "w", "l")
        exp_top = _exposure(_own(top["m"], tw), _own(top["rt"], tw), top["dur"], True, how)
        mt = m_[m_["b_pos"] != "neutral"]
        mw = np.where(mt["b_pos"] == "w_top", "w", "l")
        mt_s = level(_own(mt["b_margin"], mw), _own(mt["b_rt_diff"], mw), how)      # the TOP man's side
        rate = {x: {s: float(((mt["event"] == x).to_numpy() & (mt_s == s)).sum() / max(exp_top.get(s, 0), 1))
                    for s in grp} for x in ("escape", "reversal", "near_fall")}
        nfp = mt.loc[mt["event"] == "near_fall", "points"]
        neu = s_[s_["pos"] == "neutral"]
        ew = _exposure(neu["m"], neu["rt"], neu["dur"], False, how)
        el = _exposure(-neu["m"], -neu["rt"], neu["dur"], False, how)
        mn = m_[m_["event"] == "takedown"]
        mn_s = level(_own(mn["b_margin"], mn["actor"]), _own(mn["b_rt_diff"], mn["actor"]), how)
        td = {s: float((mn_s == s).sum() / max(ew.get(s, 0) + el.get(s, 0), 1)) for s in grp}
        lead = np.digitize(s_["m"].abs(), LEAD_BUCKETS) - 1
        end = {}
        for pc, msk in (("neutral", (s_["pos"] == "neutral").to_numpy()), ("mat", (s_["pos"] != "neutral").to_numpy())):
            end[pc] = [float(s_["end"].to_numpy()[msk & (lead == i)].sum()
                             / max(s_["dur"].to_numpy()[msk & (lead == i)].sum(), 1)) for i in range(len(LEAD_BUCKETS))]
        who_top = np.where(p_["a_pos"] == "w_top", "w", np.where(p_["a_pos"] == "l_top", "l", "n"))
        pick = np.where(who_top == "n", "neutral", np.where(who_top == p_["actor"].to_numpy(), "top", "bottom"))
        pk_s = level(_own(p_["b_margin"], p_["actor"]), _own(p_["b_rt_diff"], p_["actor"]), how)
        picks = {}
        for per in (2, 3):
            allp = (p_["a_period"] == per).to_numpy()
            pooled = [float((pick[allp] == x).sum() / max(allp.sum(), 1)) for x in PICKS]
            for s in grp:
                msk = allp & (pk_s == s)
                n = msk.sum()   # thin levels lean on the period's pooled shares (20 pseudo-picks)
                picks[f"{per}{int(s):+d}"] = [float(((pick[msk] == x).sum() + 20 * q) / (n + 20)) for x, q in zip(PICKS, pooled)]
        t_s = level(_own(t_["b_margin"], t_["actor"]), _own(t_["b_rt_diff"], t_["actor"]), how)
        d0 = float(t_["deferred"].mean()) if len(t_) else 0.5
        dfr = {s: float((t_["deferred"].to_numpy()[t_s == s].sum() + 20 * d0) / ((t_s == s).sum() + 20)) for s in grp}
        out["eras"][eg] = {
            "td_points": TD_POINTS[eg], "takedown": {str(k): v for k, v in td.items()},
            **{x: {str(k): v for k, v in rate[x].items()} for x in ("escape", "reversal", "near_fall")},
            "nf_share": [float((nfp == k).mean()) if len(nfp) else 1 / 3 for k in NF_POINTS],
            "end": end, "picks": picks, "defer": {str(k): v for k, v in dfr.items()},
            "exposure_min": {"top": float(top["dur"].sum() / 60), "neutral": float(neu["dur"].sum() / 60)}}
    return out


# ---------------------------------------------------------------------------------------------------------------
# the dynamic program -- value arrays are (pos, c, d): pos 0 neutral / 1 A_top / 2 A_bottom;
# c = A's margin + (TF - 1) (margins -14 .. 14; 15 either way = tech fall); d = rt_diff + OFF
# ---------------------------------------------------------------------------------------------------------------
CS = np.arange(-(TF - 1), TF)


G = np.arange(-OFF, OFF + 1)
LV_A = (CS[:, None], G[None, :])      # A's own margin and riding-time lead on the (c, d) grid
LV_B = (-CS[:, None], -G[None, :])    # B's


def _by_level(tab, lv):
    """tab: {code: value} -> array over lv (any shape)"""
    keys = np.array(sorted(int(k) for k in tab))
    vals = np.array([tab[str(k)] for k in keys])
    return vals[np.searchsorted(keys, lv)]


def _rates(p, how):
    sA, sB = level(*LV_A, how), level(*LV_B, how)
    lead = np.digitize(np.abs(CS), LEAD_BUCKETS) - 1
    r = {"tdA": _by_level(p["takedown"], sA), "tdB": _by_level(p["takedown"], sB),
         # A on top: the top man is A; A on bottom: the top man is B
         "escB": _by_level(p["escape"], sA), "revB": _by_level(p["reversal"], sA), "nfA": _by_level(p["near_fall"], sA),
         "escA": _by_level(p["escape"], sB), "revA": _by_level(p["reversal"], sB), "nfB": _by_level(p["near_fall"], sB)}
    # per-second probabilities of competing moves: p_i = rate_i * (1 - exp(-R)) / R
    for grp in (("tdA", "tdB"), ("escB", "revB", "nfA"), ("escA", "revA", "nfB")):
        R = sum(r[k] for k in grp)
        f = np.where(R > 0, -np.expm1(-R) / np.where(R > 0, R, 1), 1.0)
        for k in grp:
            r[k] = r[k] * f
    r["endN"] = (-np.expm1(-np.array(p["end"]["neutral"])[lead]))[:, None]
    r["endM"] = (-np.expm1(-np.array(p["end"]["mat"])[lead]))[:, None]
    r["td_pts"], r["nf"] = p["td_points"], list(zip(p.get("nf_share", [1 / 3] * 3), NF_POINTS))
    return r


def _sd(v, k):
    """along d: value at d uses the entry at d + k (edges clamped; the grid is wider than any reachable differential)"""
    if k == 1:
        return np.concatenate([v[..., 1:], v[..., -1:]], axis=-1)
    return np.concatenate([v[..., :1], v[..., :-1]], axis=-1)


def _sc(v, k):
    """along the margin: value at c uses the entry at c + k; past +/-15 is a tech fall = 0 (nobody gets the point)"""
    out = np.zeros_like(v)
    if k > 0:
        out[:-k] = v[k:]
    else:
        out[-k:] = v[:k]
    return out


def _step(V, r):
    U0, U1, U2 = V[0], _sd(V[1], 1), _sd(V[2], -1)   # the second's riding time goes to the (new) top man
    td = r["td_pts"]
    n = (1 - r["endN"]) * ((1 - r["tdA"] - r["tdB"]) * U0 + r["tdA"] * _sc(U1, td) + r["tdB"] * _sc(U2, -td))
    nfa = sum(w * _sc(U1, k) for w, k in r["nf"])
    nfb = sum(w * _sc(U2, -k) for w, k in r["nf"])
    t = (1 - r["endM"]) * ((1 - r["escB"] - r["revB"] - r["nfA"]) * U1 + r["escB"] * _sc(U0, -1)
                           + r["revB"] * _sc(U2, -2) + r["nfA"] * nfa)
    b = (1 - r["endM"]) * ((1 - r["escA"] - r["revA"] - r["nfB"]) * U2 + r["escA"] * _sc(U0, 1)
                           + r["revA"] * _sc(U1, 2) + r["nfB"] * nfb)
    return np.stack([n, t, b])


def _pick_value(V, p, per, chooser, how):
    """Value of a break where `chooser` ('A' / 'B') picks the position, over (c, d)."""
    lv = level(*(LV_A if chooser == "A" else LV_B), how)
    sh = [_by_level({str(int(k[1:])): v[i] for k, v in p["picks"].items() if int(k[0]) == per}, lv) for i in range(3)]
    top, bot = (1, 2) if chooser == "A" else (2, 1)
    return sh[0] * V[top] + sh[1] * V[bot] + sh[2] * V[0]


def _query(df):
    """Integer query arrays for A's point."""
    pos = df["pos"].to_numpy()
    per = df["period"].to_numpy(int) if "period" in df else df["pi"].to_numpy(int) + 1
    chc = df["chc"].to_numpy(int) if "chc" in df else np.select(
        [df["choice"] == "A", df["choice"] == "B"], [1, -1], 0)
    return {"s": np.clip(df["t_rem"].to_numpy(float).round().astype(int), 0, C.T_TOTAL),
            "c": np.clip(df["margin"].to_numpy(float).round().astype(int), -(TF - 1), TF - 1),
            "d": np.clip(df["rt_diff"].to_numpy(float).round().astype(int), -OFF + 1, OFF - 1),
            "pos": np.select([pos == "A_top", pos == "A_bottom"], [1, 2], 0), "chc": chc, "per": per,
            "kind": np.select([pos == "pending_pre_toss", pos == "pending_defer_option", pos == "pending_pick"],
                              ["pt", "do", "pk"], "in")}


def _mirror(q):
    return {**q, "c": -q["c"], "d": -q["d"], "pos": np.array([0, 2, 1])[q["pos"]], "chc": -q["chc"]}


def _sweep(p, q, how):
    """P(A's point) for every query (one era's parameters)."""
    r = _rates(p, how)
    out = np.full(len(q["s"]), np.nan)
    ci, di = q["c"] + TF - 1, q["d"] + OFF
    grid = G
    inq = q["kind"] == "in"
    ph = np.where(q["per"] >= 3, 3, np.where(q["per"] == 2, 2, 1))

    def at(mask, V3d):
        """in-period queries in `mask` read V3d (pos, c, d)"""
        idx = np.nonzero(mask)[0]
        if len(idx):
            out[idx] = V3d[q["pos"][idx], ci[idx], di[idx]]

    def by_holder(mask, tab):
        """values that depend on who holds the choice (+1 A, -1 B, 0 unknown = 50/50); tab[X] is (c, d) or
        (pos, c, d)"""
        idx = np.nonzero(mask)[0]
        if len(idx):
            ix = (ci[idx], di[idx]) if tab["A"].ndim == 2 else (q["pos"][idx], ci[idx], di[idx])
            a, b = tab["A"][ix], tab["B"][ix]
            h = q["chc"][idx]
            out[idx] = np.where(h > 0, a, np.where(h < 0, b, 0.5 * (a + b)))

    # period 3: 2:00 .. 0:00
    V = np.broadcast_to((grid >= C.RT_THRESHOLD).astype(float), (3, len(CS), len(grid))).copy()
    s3 = np.minimum(q["s"], 120)
    for s in range(0, 121):
        if s:
            V = _step(V, r)
        at(inq & (ph == 3) & (s3 == s), V)
    W3 = {X: _pick_value(V, p, 3, X, how) for X in ("A", "B")}
    by_holder((q["kind"] == "pk") & (q["per"] >= 3), W3)
    # period 2: 4:00 .. 2:00, once per period-3 chooser
    V2 = {X: np.broadcast_to(W3[X], (3,) + W3[X].shape).copy() for X in ("A", "B")}
    s2 = np.clip(q["s"], 120, 240)
    for s in range(120, 241):
        if s > 120:
            V2 = {X: _step(V2[X], r) for X in V2}
        by_holder(inq & (ph == 2) & (s2 == s), V2)
    # the 4:00 break: X picks period 2 and the other picks period 3; the toss winner defers with the defer share
    W2 = {"A": _pick_value(V2["B"], p, 2, "A", how), "B": _pick_value(V2["A"], p, 2, "B", how)}
    qA = _by_level(p["defer"], level(*LV_A, how))
    qB = _by_level(p["defer"], level(*LV_B, how))
    DO = {"A": (1 - qA) * W2["A"] + qA * W2["B"], "B": (1 - qB) * W2["B"] + qB * W2["A"]}
    PT = 0.5 * (DO["A"] + DO["B"])
    by_holder((q["kind"] == "pk") & (q["per"] <= 2), W2)
    by_holder(q["kind"] == "do", DO)
    idx = np.nonzero(q["kind"] == "pt")[0]
    out[idx] = PT[ci[idx], di[idx]]
    # period 1: 7:00 .. 4:00
    V = np.broadcast_to(PT, (3,) + PT.shape).copy()
    s1 = np.clip(q["s"], 240, C.T_TOTAL)
    for s in range(240, C.T_TOTAL + 1):
        if s > 240:
            V = _step(V, r)
        at(inq & (ph == 1) & (s1 == s), V)
    return out


def probs(params, df):
    """(pA, pN, pB) for every row of df (A-relative states: t_rem, margin, rt_diff, pos, period or pi, chc or choice,
    ei or era_group)."""
    q = _query(df)
    qm = _mirror(q)
    e3 = (df["ei"].to_numpy(int) == 1) if "ei" in df else (df["era_group"] == "E3").to_numpy()
    pa, pb = np.zeros(len(df)), np.zeros(len(df))
    for eg, msk in (("E12", ~e3), ("E3", e3)):
        if not msk.any():
            continue
        both = {k: np.concatenate([q[k][msk], qm[k][msk]]) for k in q}
        v = _sweep(params["eras"][eg], both, params["levels"])
        n = int(msk.sum())
        pa[msk], pb[msk] = v[:n], v[n:]
    s = pa + pb
    scale = np.where(s > 1, 1 / np.maximum(s, 1e-12), 1.0)   # can't both happen; guards rounding only
    pa, pb = pa * scale, pb * scale
    return pa, 1 - pa - pb, pb
