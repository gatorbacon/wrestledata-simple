#!/usr/bin/env python3
"""
WPA overtime model -- CURRENT overtime rules only (TJ decision 2026-09-29: build it after step 10, separate rules for
sudden victory and the tiebreaker, data from the current-rules pool only).

Rules (NCAA; the 2-minute sudden victory and the 1-second tiebreaker riding-time rule were approved 2021-06-23 for
the 2021-22 season = data years 2022+, `wpa_common.ot_rules == "SV120"`; the 2025-26 rules changes list has no
overtime change):
  * SV-1: 2:00 from neutral, first score of any kind wins.
  * TB-1: two 30-second rides. The wrestler with the first offensive points in regulation (takedown / near fall;
    else a coin flip) chooses ride 1; the other wrestler chooses ride 2 (top, bottom or neutral). After both rides
    the leader on points wins; a points tie goes to the wrestler with more tiebreaker riding time (1 SECOND or more
    net), and only then to the next round. Riding time is a tiebreak, not a point on top of the score: in 2026 alone
    7 of 8 "escape in ride 1, neutral in ride 2, no score" bouts went to the escaper 1-0 although his opponent had
    banked riding time in ride 1 (TrackWrestling still logs a "Riding Time" point for the winner).
  * Next rounds (SV-2 1:00, TB-2, UTB) are one strength-weighted value here, expit(k_sv * rank signal): TrackWrestling
    writes every sudden-victory round in the "Overtime 1" column and every tiebreaker ride in "Overtime 2"/"3", so
    the later rounds' events are merged with the first round's and their deciding events are usually missing (e.g.
    2025 NCAA 165 Snipes-Gallagher TB-2 2-2 shows only TB-1's two escapes).

Data facts (SV120 pool, NCAA + conference, checked 2026-09-29):
  * 708 overtime bouts: SV-1 511, TB-1 130, TB-2 20, SV-2 15, TB-3 2, SV-3 1, UTB 1, falls 16 (+ 5 odd labels).
    2026 had more bouts reach the tiebreaker (32% vs ~23% in 2022-25, p ~ 0.03) -- no rule change, checked on the
    held-out 2026 fold.
  * SV-1 is decided by a takedown in 97% (495 / 510), else penalty points / an escape or reversal after a TD
    stalemate call. Its scoring rate rises through the period (~0.6%/s in the first 30 s, ~1.2-1.5%/s after): the
    hazard is piecewise constant over four 30-second windows.
  * "Choice 3" names the wrestler on BOTTOM in ride 1 ("X: Bottom" in 177 of 178; he escapes / reverses in 97.5% of
    rides that have one). The choice holder can DEFER (logged "X: Defer" before the pick; 17 of 50 tiebreakers in
    2026): the other wrestler then picks ride 1 -- always bottom -- and the holder picks ride 2. So the ride-2 chooser
    is the wrestler on top in ride 1 either way. Who holds the choice: in 150 of 178 nobody had a takedown / near
    fall in regulation (coin flip, not logged); in the other 28 the first offensive scorer started ride 1 on bottom
    18 times (64%, the rest deferred) -> q_holder_bottom.
  * A scoreless ride isn't logged. A TB-1 that ended tied was scoreless (ride-out, the chooser took bottom, ridden
    out: 30-30) in 38 of 39 later-round bouts, whose tiebreaker columns hold the later round's events only.
  * Ride 2 habit (the chooser = the wrestler on top in ride 1): behind on points -> bottom ~69%, neutral ~30%; tied
    with the riding-time lead (after a ride-out) -> bottom ~76%. Choosing by the model's best option would pick
    neutral far more often, so the observed habit sets the value before the pick in those two situations; the pick
    itself is an `ot_choice` link.
  * Riding time is only a points-tie breaker (checked in 2026: escape in ride 1 + neutral / no score in ride 2 went
    to the escaper 1-0). TrackWrestling logs a "Riding Time" point for the winner (29 logged, never for the loser).
  * In neutral the tiebreak leader takes the other down MORE than the trailer (13 vs 8 takedowns) and gets called
    for stalling more (8 vs 4 penalty points): neutral rates are split by leader / trailer.

Model
  WP(SV, t left) = pA * (1 - S) + S * TB_pre,   pA = expit(k_sv * rs),  S = exp(-integral of the hazard over t)
  TB_pre = the ride-1 position mix (holder on bottom with prob q; coin flip = 1/2) of the tiebreaker value
  Tiebreaker value = exact backward recursion per second over (position, tiebreaker margin, riding-time diff) with
  per-second rates from tiebreaker rides (escape, reversal, top's near fall / fall, penalty point to either wrestler;
  neutral takedown / penalty point by leader and trailer); A's actions x exp(s/2), B's x exp(-s/2), s = k_tb * rs;
  the ride-2 pick = the observed habit (above), elsewhere the chooser's best option; end = the points margin, or when
  tied the sign of the riding-time diff (1 s or more): won / lost / 0 = next rounds (one value, expit(k_sv * rs)).
  Tiebreaker values are then shrunk, logit x alpha_tb (~0.64, fitted on the training seasons): late in a ride the
  wrestler who needs a score gets it (stall point, scramble) ~3x as often as the average rates say (stall counts
  carry over from regulation). Before the shrink the model said 96% where the favourite won 88%.
  rs = the rank signal of the seed layer (wp_model.WPModel.parts: NCAA seed / national rank on the conference scale).
  Fitted: hazards and rates by counting (tiebreaker rides from bouts decided in TB-1 or by a fall, plus two
  ridden-out rides per scoreless-tie bout), k_sv by maximum likelihood on bouts decided in SV-1, k_tb (grid) on bouts
  that reached the tiebreaker, q / habit by counting, alpha_tb on training tiebreaker states. Validation: leave one
  season out (2022-2026), log loss at overtime states vs the step-9 flat value expit(beta_ot * rs).

Used by compute_wpa.py (OTModel.start_values / OTModel.chain). Earlier rules (SV60, before 2022) keep the flat value.

Usage: .venv/bin/python scripts/wpa/ot_model.py     (fit + held-out check + report, ~2.5 min; then compute_wpa.py)
Writes data/wpa/model/ot_params.json, data/wpa/states/ot_bouts.csv, data/wpa/reports/ot_model.md
"""
import json
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.special import expit

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts/wpa"))
sys.path.insert(0, str(ROOT / "scripts/analysis"))
import wpa_common as C  # noqa: E402

STATES = ROOT / "data/wpa/states"
MODEL = ROOT / "data/wpa/model"
REP = ROOT / "data/wpa/reports/ot_model.md"
PRM_FILE = MODEL / "ot_params.json"
SV_LEN, RIDE = 120, 30
SV_EDGES = [0, 30, 60, 90, 120]          # elapsed seconds; hazard constant inside each window
M, R = 9, 60                             # tiebreaker margin cap, riding-time cap (seconds)
NM, NR = 2 * M + 1, 2 * R + 1
NF_PTS = 3
FIT_YEARS = [2022, 2023, 2024, 2025, 2026]
CLEAN = {"SV-1", "TB-1", "Fall"}
POSI = {"A_top": 0, "A_bottom": 1, "neutral": 2}


def other(s):
    return "l" if s == "w" else "w"


def td_points(year):
    return 3 if year >= 2024 else 2


# ---------------------------------------------------------------------------------------------------------------
# raw overtime columns (what the events file can't tell: ride-1 bottom, ride-2 start, merged rounds)
# ---------------------------------------------------------------------------------------------------------------
def raw_ot():
    import build_states as BS
    rows = []
    for kind in ("ncaa", "conf"):
        for r in C.load_bouts(kind):
            y = r["year"]
            if C.ot_rules(y) != "SV120":
                continue
            m = r["bout"]
            cols = {c["label"]: c for c in m.get("columns") or []}
            if not any(lab.startswith("Overtime") or lab == "Choice 3" for lab in cols):
                continue
            sw = r["swapped"]
            pc = lambda lab: BS.parse_col(cols[lab], sw) if lab in cols else []  # noqa: E731
            c3 = [e for e in pc("Choice 3") if e["action"] == "choice"]
            o2, o3 = pc("Overtime 2"), pc("Overtime 3")
            bot1, src1 = None, ""
            pick = [e for e in c3 if e["word"] in ("bottom", "top")]   # the first pick is TB-1's (after a defer)
            if pick:
                s = pick[0]["side"]
                bot1, src1 = (s if pick[0]["word"] == "bottom" else other(s)), "choice"
            else:
                for e in o2:
                    if e["action"] in ("escape", "reversal"):
                        bot1, src1 = e["side"], "first escape"
                        break
            start2, chooser2 = None, None
            for e in o3:
                if e["action"] == "choice" and e["word"] in ("neutral", "top", "bottom"):
                    chooser2 = e["side"]
                    start2 = "neutral" if e["word"] == "neutral" else (
                        ("A_top" if e["side"] == "w" else "A_bottom") if e["word"] == "top"
                        else ("A_bottom" if e["side"] == "w" else "A_top"))
                    break
                if e["action"] in ("escape", "reversal"):
                    start2 = "A_bottom" if e["side"] == "w" else "A_top"
                    break
                if e["action"] == "takedown":
                    start2 = "neutral"
                    break
            notes = [x for c in cols.values() if c["label"].startswith("Overtime") for x in c.get("notes", [])]
            rows.append({"bout_key": f"{kind}|{r['tournament']}|{y}|{r['weight']}|{m.get('bout_number')}",
                         "bot1": bot1 or "", "bot1_source": src1, "start2": start2 or "", "chooser2": chooser2 or "",
                         "next_round_note": any("next round" in x for x in notes),
                         "n_tb_scores": sum(1 for e in o2 + o3 if e["points"] and e["action"] != "riding_time")})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------------------------------------------
# the tiebreaker recursion
# ---------------------------------------------------------------------------------------------------------------
@lru_cache(maxsize=None)
def _idx(n, d):
    return np.clip(np.arange(n) + d, 0, n - 1)


def _sh(A, dm, dr):
    """out[..., m, r] = A[..., m + dm, r + dr] (clipped at the caps)."""
    return A[..., _idx(NM, dm), :][..., _idx(NR, dr)]


def _step(V, p, fa, fb, td):
    """One second earlier. V: [nS, 3, NM, NR] with t-1 seconds left; fa / fb: [nS, 1, 1]."""
    top, bot, neu = V[:, 0], V[:, 1], V[:, 2]
    out = np.empty_like(V)
    # A on top (B bottom): A's riding time +1
    e, rv, nf, fl = p["esc"] * fb, p["rev"] * fb, p["nf"] * fa, p["fall"] * fa
    out[:, 0] = ((1 - e - rv - nf - fl - p["pen_bot"] - p["pen_top"]) * _sh(top, 0, 1) + e * _sh(neu, -1, 1)
                 + rv * _sh(bot, -2, 1) + nf * _sh(top, NF_PTS, 1) + fl
                 + p["pen_bot"] * _sh(top, -1, 1) + p["pen_top"] * _sh(top, 1, 1))
    # A on bottom (B top): B's riding time +1
    e, rv, nf, fl = p["esc"] * fa, p["rev"] * fa, p["nf"] * fb, p["fall"] * fb
    out[:, 1] = ((1 - e - rv - nf - fl - p["pen_bot"] - p["pen_top"]) * _sh(bot, 0, -1) + e * _sh(neu, 1, -1)
                 + rv * _sh(top, 2, -1) + nf * _sh(bot, -NF_PTS, -1)
                 + p["pen_bot"] * _sh(bot, 1, -1) + p["pen_top"] * _sh(bot, -1, -1))
    # neutral: the wrestler losing the tiebreak right now (points, then riding time) attacks, the leader runs
    LA, LB, EV = _lead_masks()
    tdA = p["td_trail"] * LB + p["td_lead"] * LA + p["td_even"] * EV
    tdB = p["td_trail"] * LA + p["td_lead"] * LB + p["td_even"] * EV
    pnA = p["pen_trail"] * LB + p["pen_lead"] * LA + p["pen_even"] * EV       # penalty point awarded to A
    pnB = p["pen_trail"] * LA + p["pen_lead"] * LB + p["pen_even"] * EV
    ta, tb = tdA * fa, tdB * fb
    out[:, 2] = ((1 - ta - tb - pnA - pnB) * neu + ta * _sh(top, td, 0) + tb * _sh(bot, -td, 0)
                 + pnA * _sh(neu, 1, 0) + pnB * _sh(neu, -1, 0))
    return out


@lru_cache(maxsize=None)
def _lead_masks():
    mg, rg = np.arange(-M, M + 1)[:, None], np.arange(-R, R + 1)[None, :]
    LA = ((mg > 0) | ((mg == 0) & (rg > 0))).astype(float)
    LB = ((mg < 0) | ((mg == 0) & (rg < 0))).astype(float)
    return LA, LB, 1.0 - LA - LB


def tb_tables(prm, s_tb, s_sv, td, keep=True, dv=0.0):
    """Backward recursion for a vector of strengths. Returns (V1, V2): V2 [t, nS, pos, m, r] = ride 2 with t seconds
    left; V1[c] the same for ride 1 when c (0 = A, 1 = B) chooses ride 2. keep=False keeps only t = 30. dv shifts the
    next-round value (P(tie) = dV/dv)."""
    s_tb, s_sv = np.atleast_1d(np.asarray(s_tb, float)), np.atleast_1d(np.asarray(s_sv, float))
    p = prm["tb_rates"]
    fa, fb = np.exp(s_tb / 2)[:, None, None], np.exp(-s_tb / 2)[:, None, None]
    mm = np.arange(-M, M + 1)[:, None]
    tot = np.where(mm != 0, mm, np.sign(np.arange(-R, R + 1))[None, :])
    vnext = expit(s_sv)[:, None, None] + dv
    end = np.where(tot > 0, 1.0, np.where(tot < 0, 0.0, vnext))           # [nS, NM, NR]
    V = np.repeat(end[:, None], 3, axis=1)
    V2 = [V]
    for _ in range(RIDE):
        V = _step(V, p, fa, fb, td)
        V2.append(V)
    brk = {0: V.max(axis=1), 1: V.min(axis=1)}                             # ride-2 chooser's best option ...
    pol = prm.get("ride2_policy")
    if pol:                                                                # ... except where we observe his habit
        mg, rg = np.arange(-M, M + 1)[:, None], np.arange(-R, R + 1)[None, :]
        for c, sg, own_bot, own_top in ((0, 1, 1, 0), (1, -1, 0, 1)):
            for sit, mask in (("behind", sg * mg < 0), ("tied, riding-time lead", (mg == 0) & (sg * rg > 0))):
                pi = pol[sit]
                mix = pi["bottom"] * V[:, own_bot] + pi["neutral"] * V[:, 2] + pi["top"] * V[:, own_top]
                brk[c] = np.where(np.broadcast_to(mask, brk[c].shape[1:])[None], mix, brk[c])
    V1 = {}
    for c in (0, 1):
        V = np.repeat(brk[c][:, None], 3, axis=1)
        L = [V]
        for _ in range(RIDE):
            V = _step(V, p, fa, fb, td)
            L.append(V)
        V1[c] = np.stack(L) if keep else L[-1]
    return V1, (np.stack(V2) if keep else V2[-1])


def shrink(V, a):
    """Tiebreaker confidence shrink: logit(WP) x alpha_tb (0 / 1 stay exact). The per-second rates are averages;
    late in a ride the wrestler who needs a score gets it (a stall point, a scramble) about 3x as often as they say."""
    if a == 1.0:
        return V
    Vc = np.clip(V, 1e-9, 1 - 1e-9)
    out = expit(a * np.log(Vc / (1 - Vc)))
    return np.where((V <= 0) | (V >= 1), V, out)


def sv_survival(prm, t_rem):
    """P(no score in the rest of SV-1 from t_rem seconds left)."""
    el = SV_LEN - np.asarray(t_rem, float)
    h = 0.0
    for (a, b), hz in zip(zip(SV_EDGES[:-1], SV_EDGES[1:]), prm["sv_hazard"]):
        h = h + hz * np.clip(b - np.maximum(el, a), 0, None) * (el < b)
    return np.exp(-h)


def p_a_bottom(prm, holder):
    q = prm["q_holder_bottom"]
    return np.where(holder == "w", q, np.where(holder == "l", 1 - q, 0.5))


def tb_pre(prm, V1_start, holder):
    """Tiebreaker value before the ride-1 position is known. V1_start[c]: [nS, 3, NM, NR] at t = 30."""
    pb = p_a_bottom(prm, holder)
    return pb * V1_start[1][:, 1, M, R] + (1 - pb) * V1_start[0][:, 0, M, R]


# ---------------------------------------------------------------------------------------------------------------
class OTModel:
    def __init__(self, prm=None):
        self.prm = prm or json.loads(PRM_FILE.read_text())
        self._cache = {}

    def strengths(self, rs):
        return self.prm["k_sv"] * rs, self.prm["k_tb"] * rs

    def tables(self, rs, td):
        key = (round(float(rs), 2), td)
        if key not in self._cache:
            s_sv, s_tb = self.strengths(key[0])
            V1, V2 = tb_tables(self.prm, [s_tb], [s_sv], td)
            a = self.prm.get("alpha_tb", 1.0)
            self._cache[key] = ({c: shrink(V1[c][:, 0], a) for c in V1}, shrink(V2[:, 0], a), float(expit(s_sv)))
        return self._cache[key]

    def start_values(self, rs, holder, td):
        """WP of A at the start of overtime (batch; rs rounded to 0.02 so tables are shared)."""
        rs = np.round(np.asarray(rs, float) / 0.02) * 0.02
        holder = np.asarray(holder, object)
        td = np.asarray(td)
        out = np.empty(len(rs))
        for t in np.unique(td):
            m_ = td == t
            u, inv = np.unique(rs[m_], return_inverse=True)
            s_sv, s_tb = self.strengths(u)
            V1, _ = tb_tables(self.prm, s_tb, s_sv, int(t), keep=False)
            a = self.prm.get("alpha_tb", 1.0)
            pre = tb_pre(self.prm, {c: shrink(V1[c][inv], a) for c in V1}, holder[m_])
            S = sv_survival(self.prm, SV_LEN)
            out[m_] = expit(s_sv[inv]) * (1 - S) + S * pre
        return out

    # -----------------------------------------------------------------------------------------------------------
    def chain(self, evs, info, rs, td, holder, v0):
        """See _chain. Synthetic links (clock stretches, choices, the final step) get seq numbers strictly between the
        real events around them, in chain order (event rows keep their own integer seq)."""
        links = self._chain(evs, info, rs, td, holder, v0)
        real = {e["seq"] for e in evs}
        last = (min(real) if real else 0) - 1
        k = 0
        for lk in links:
            if lk["seq"] in real and float(lk["seq"]).is_integer():
                last, k = lk["seq"], 0
            else:
                k += 1
                lk["seq"] = last + 0.02 * k
        return links

    def _chain(self, evs, info, rs, td, holder, v0):
        """The overtime part of one bout's WP chain (A = the bout winner). evs: its overtime event rows (dicts with
        seq, event, actor, points, ot_period, ot_clock, raw_text) in order; info: its ot_bouts row (bot1, start2,
        chooser2, clean). Returns links: dicts seq, etype, actor, sub, vb, va, sb, sa (state dicts)."""
        rs = round(float(rs), 2)
        V1, V2, vnext = self.tables(rs, td)
        s_sv = self.prm["k_sv"] * rs
        pA = float(expit(s_sv))
        pb = float(p_a_bottom(self.prm, np.array([holder], object))[0])
        pre = pb * V1[1][RIDE, 1, M, R] + (1 - pb) * V1[0][RIDE, 0, M, R]
        sv = lambda t: pA * (1 - sv_survival(self.prm, t)) + sv_survival(self.prm, t) * pre  # noqa: E731
        links = []
        st = {"margin": 0.0, "t_rem": float(SV_LEN), "period": "SV1", "pos": "neutral", "choice": "none",
              "rt_diff": 0.0}
        cur = {"v": float(v0), "s": st}
        seq0 = evs[0]["seq"] if evs else 0

        def go(seq, etype, actor, v, s, sub=""):
            nonlocal cur
            links.append({"seq": seq, "etype": etype, "actor": actor, "sub": sub, "vb": cur["v"], "va": float(v),
                          "sb": cur["s"], "sa": s})
            cur = {"v": float(v), "s": s}

        def clock(seq, v, s):
            if abs(v - cur["v"]) > 1e-12:
                go(seq, "clock", "", v, s)
            else:
                cur["s"] = s

        done = lambda: cur["v"] >= 1.0 - 1e-12  # noqa: E731
        if info.get("tie_tb1") and info.get("bot1") in ("w", "l"):
            # TB-1 was scoreless (ride-out, chooser bottom, ride-out) -> tied -> later rounds, whose events are
            # logged in the same columns: flat at the next-round value, the winner's last overtime score takes it to 1
            b1 = info["bot1"]
            p1 = "A_bottom" if b1 == "w" else "A_top"
            ci = 0 if other(b1) == "w" else 1
            r1 = 30.0 if p1 == "A_top" else -30.0
            tst = lambda per, t_, p_, r__: {"margin": 0.0, "t_rem": t_, "period": per, "pos": p_,  # noqa: E731
                                            "choice": "none", "rt_diff": r__}
            clock(seq0 - 0.9, pre, dict(st, t_rem=0.0))
            go(seq0 - 0.8, "ot_choice", b1, V1[ci][RIDE, POSI[p1], M, R], tst("TB1", 30.0, p1, 0.0), sub="ride 1")
            clock(seq0 - 0.7, V1[ci][0, POSI[p1], M, R + int(r1)], tst("TB1", 0.0, p1, r1))
            p2 = "A_bottom" if other(b1) == "w" else "A_top"
            go(seq0 - 0.6, "ot_choice", other(b1), V2[RIDE, POSI[p2], M, R + int(r1)], tst("TB2", 30.0, p2, r1),
               sub="ride 2")
            clock(seq0 - 0.5, vnext, tst("TB2", 0.0, p2, 0.0))
            win = max((i for i, e in enumerate(evs) if e["actor"] == "w" and (e["points"] > 0 or e["event"] == "fall")),
                      default=None)
            for i, e in enumerate(evs):
                go(e["seq"], e["event"], e["actor"], 1.0 if (i == win or done()) else cur["v"],
                   dict(st, t_rem=0.0, period="later"))
            if not done():
                go((evs[-1]["seq"] if evs else seq0) + 0.5, "overtime", "w", 1.0, cur["s"], sub="later rounds")
            return links
        if not info.get("clean"):
            # later rounds: SV-1 ran out scoreless, then one step to the result at the winner's last overtime score
            win = max((i for i, e in enumerate(evs) if e["actor"] == "w" and (e["points"] > 0 or e["event"] == "fall")),
                      default=None)
            clock(seq0 - 0.5, pre, dict(st, t_rem=0.0))
            for i, e in enumerate(evs):
                s = dict(st, t_rem=0.0, period=f"OT{int(e['ot_period'] or 1)}")
                go(e["seq"], e["event"], e["actor"], 1.0 if (i == win or done()) else cur["v"], s)
            if not done():
                go((evs[-1]["seq"] if evs else seq0) + 0.5, "overtime", "w", 1.0, cur["s"], sub="later rounds")
            return links

        # ---- sudden victory
        sv_ev = [e for e in evs if (e["ot_period"] or 1) == 1 and e["event"] not in ("ot_riding_time",)]
        tb_ev = [e for e in evs if e not in sv_ev]
        t = float(SV_LEN)
        for e in sv_ev:
            if done():
                go(e["seq"], e["event"], e["actor"], 1.0, cur["s"])
                continue
            te = e["ot_clock"] if e["ot_clock"] == e["ot_clock"] and e["ot_clock"] is not None else t
            te = min(float(te), t)
            clock(e["seq"] - 0.5, sv(te), dict(st, t_rem=te))
            t = te
            v = 1.0 if (e["actor"] == "w" and (e["points"] > 0 or e["event"] == "fall")) else cur["v"]
            go(e["seq"], e["event"], e["actor"], v, dict(st, t_rem=te))
        if done():
            for e in tb_ev:
                go(e["seq"], e["event"], e["actor"], 1.0, cur["s"])
            return links
        seq_tb = tb_ev[0]["seq"] if tb_ev else (evs[-1]["seq"] + 0.5 if evs else seq0)
        clock(seq_tb - 0.9, pre, dict(st, t_rem=0.0))

        # ---- tiebreaker
        bot1 = info.get("bot1") or ""
        if bot1 not in ("w", "l"):
            go(seq_tb - 0.8, "overtime", "w", 1.0, cur["s"], sub="tiebreaker (position unknown)")
            for e in tb_ev:
                go(e["seq"], e["event"], e["actor"], 1.0, cur["s"])
            return links
        c2 = info.get("chooser2") or other(bot1)
        ci = 0 if c2 == "w" else 1
        pos = "A_bottom" if bot1 == "w" else "A_top"
        m_, r_ = 0, 0.0

        def val(ride, t_, pos_, m__, r__):
            mi = int(np.clip(m__, -M, M)) + M
            ri = int(np.clip(round(r__), -R, R)) + R
            tt = int(np.clip(round(t_), 0, RIDE))
            tab = V1[ci] if ride == 1 else V2
            return float(tab[tt, POSI[pos_], mi, ri])

        def tstate(ride, t_, pos_):
            return {"margin": float(m_), "t_rem": float(t_), "period": f"TB{ride}", "pos": pos_, "choice": "none",
                    "rt_diff": float(r_)}

        go(seq_tb - 0.7, "ot_choice", bot1, val(1, RIDE, pos, 0, 0.0), tstate(1, RIDE, pos), sub="ride 1")
        acc = lambda p_: 1 if p_ == "A_top" else -1 if p_ == "A_bottom" else 0  # noqa: E731
        rows = {1: [e for e in tb_ev if e["ot_period"] == 2], 2: [e for e in tb_ev if e["ot_period"] == 3]}
        rest = [e for e in tb_ev if e["ot_period"] not in (2, 3)]
        for ride in (1, 2):
            t = float(RIDE)
            if ride == 2:
                p2 = info.get("start2") or ("A_bottom" if c2 == "w" else "A_top")
                seq2 = rows[2][0]["seq"] - 0.5 if rows[2] else (rest[0]["seq"] - 0.6 if rest else cur_seq + 0.3)
                go(seq2, "ot_choice", c2, val(2, RIDE, p2, m_, r_), tstate(2, RIDE, p2), sub="ride 2")
                pos = p2
            evr = rows[ride]
            clocks = [e["ot_clock"] if (e["ot_clock"] is not None and e["ot_clock"] == e["ot_clock"]) else None
                      for e in evr]
            for j, e in enumerate(evr):
                te = clocks[j]
                if te is None:   # no clock: halfway to the next clocked event (or the end of the ride)
                    nxt = next((c for c in clocks[j + 1:] if c is not None), 0.0)
                    te = (t + min(nxt, t)) / 2
                te = min(float(te), t)
                r_ += acc(pos) * (t - te)
                t = te
                if done():
                    go(e["seq"], e["event"], e["actor"], 1.0, tstate(ride, t, pos))
                    continue
                clock(e["seq"] - 0.5, val(ride, t, pos, m_, r_), tstate(ride, t, pos))
                sb_pos = pos
                sg = 1 if e["actor"] == "w" else -1
                ev_, pts = e["event"], int(e["points"] or 0)
                if ev_ == "fall":
                    go(e["seq"], ev_, e["actor"], 1.0, tstate(ride, t, pos))
                    continue
                if ev_ in ("escape", "reversal", "takedown", "near_fall", "penalty"):
                    m_ += sg * pts
                if ev_ == "escape":
                    pos = "neutral"
                elif ev_ in ("reversal", "takedown"):
                    pos = "A_top" if e["actor"] == "w" else "A_bottom"
                elif ev_ == "choice":
                    txt = str(e.get("raw_text") or "").lower()
                    if "neutral" in txt:
                        pos = "neutral"
                    elif "top" in txt:
                        pos = "A_top" if e["actor"] == "w" else "A_bottom"
                    elif "bottom" in txt:
                        pos = "A_bottom" if e["actor"] == "w" else "A_top"
                v = val(ride, t, pos, m_, r_) if abs(m_) <= M else (1.0 if m_ > 0 else 0.0)
                go(e["seq"], ev_, e["actor"], v, tstate(ride, t, pos), sub=f"from {sb_pos}")
            r_ += acc(pos) * t
            cur_seq = (evr[-1]["seq"] if evr else seq_tb) + 0.2
            if not done():
                clock(cur_seq, val(ride, 0, pos, m_, r_), tstate(ride, 0, pos))
        for e in rest:          # the tiebreaker riding-time point (and a fall / injury after the rides)
            v = 1.0 if (e["actor"] == "w" and (e["points"] > 0 or e["event"] in ("fall", "injury", "dq"))) else cur["v"]
            go(e["seq"], e["event"], e["actor"], max(v, cur["v"]) if done() else v, cur["s"])
        if not done():
            go((evs[-1]["seq"] if evs else seq0) + 0.5, "overtime", "w", 1.0, cur["s"],
               sub="later rounds" if abs(cur["v"] - vnext) < 1e-9 else "tiebreaker")
        return links


# ---------------------------------------------------------------------------------------------------------------
# fitting
# ---------------------------------------------------------------------------------------------------------------
def load_data():
    """OT bouts (SV120, table_ok) with rank signal, holder, and their overtime events."""
    import compute_wpa as CW
    import wp_model as W
    raw = raw_ot().set_index("bout_key")
    parts = [CW.load_bouts(k) for k in ("ncaa", "conf")]
    nb = pd.concat([p[0] for p in parts])
    ev = pd.concat([p[1] for p in parts], ignore_index=True)
    nb = nb[(nb["table_ok"] == True) & (nb["ot_rules"] == "SV120")]  # noqa: E712
    start = pd.DataFrame({"margin": 0, "t_rem": float(C.T_TOTAL), "period": 1, "pos": "neutral", "choice": "none",
                          "rt_diff": 0.0, "era_group": np.where(nb["year"] >= 2024, "E3", "E12"),
                          "seed_a": nb["w_seed"].astype(float), "seed_b": nb["l_seed"].astype(float),
                          "kind": nb["kind"]}, index=nb.index)
    m = W.WPModel()
    nb["rs"] = m.parts(start)["rs"].to_numpy()
    nb["wp_flat"] = expit(m.sp["beta_ot"] * nb["rs"])
    reg = ev[(ev["section"] == "reg") & ev["event"].isin(["takedown", "near_fall"]) & (ev["points"] > 0)]
    nb["holder"] = reg.sort_values(["bout_key", "seq"]).groupby("bout_key")["actor"].first().reindex(nb.index) \
        .fillna("")
    ot = nb[nb.index.isin(raw.index) | (nb["went_to_ot"].astype(str) == "True")].copy()
    ot = ot.join(raw, how="left")
    for c in ("bot1", "start2", "chooser2"):
        ot[c] = ot[c].fillna("")
    ot["next_round_note"] = ot["next_round_note"].fillna(False)
    ot["n_tb_scores"] = ot["n_tb_scores"].fillna(0)
    ot["clean"] = ot["result_type"].isin(CLEAN) & ~ot["next_round_note"]
    # TB-1 ended tied with no score (ride-out, chooser bottom, ride-out: 30-30): TrackWrestling logs nothing for a
    # scoreless ride, so the tiebreaker events these bouts show are the later round's (38 of 39 later-round bouts
    # show at most one escape per wrestler)
    ot["tie_tb1"] = (ot["result_type"].isin(["TB-2", "TB-3", "UTB"])
                     | (ot["result_type"].isin(["SV-2", "SV-3"]) & (ot["n_tb_scores"] == 0))) & ot["bot1"].isin(["w", "l"])
    ot["td"] = [td_points(y) for y in ot["year"]]
    oe = ev[(ev["section"] == "ot") & ev["bout_key"].isin(ot.index)].sort_values(["bout_key", "seq"])
    evs = {bk: g[["seq", "event", "actor", "points", "ot_period", "ot_clock", "raw_text"]].to_dict("records")
           for bk, g in oe.groupby("bout_key")}
    for L in evs.values():
        for e in L:
            e["ot_period"] = None if e["ot_period"] != e["ot_period"] else int(e["ot_period"])
            e["ot_clock"] = None if e["ot_clock"] != e["ot_clock"] else float(e["ot_clock"])
            e["actor"] = e["actor"] if isinstance(e["actor"], str) else ""
    return ot, evs, nb


def sv_times(ot, evs):
    """(elapsed second of the deciding SV-1 score or NaN, reached the tiebreaker?) per bout."""
    el, reach = {}, {}
    for bk, r in ot.iterrows():
        L = evs.get(bk, [])
        sc = [e for e in L if (e["ot_period"] or 1) == 1 and e["actor"] == "w" and e["points"] > 0
              and e["ot_clock"] is not None]
        tb = any((e["ot_period"] or 0) >= 2 for e in L) or r["result_type"] not in ("SV-1",)
        if r["result_type"] == "SV-1" and sc:
            el[bk], reach[bk] = SV_LEN - sc[0]["ot_clock"], False
        elif r["result_type"] != "SV-1" and tb and r["result_type"] not in ("Dec", "Unknown"):
            el[bk], reach[bk] = np.nan, True
    return pd.Series(el), pd.Series(reach)


def ride_counts(ot, evs):
    """Exposure seconds and events by position over the TB-1 rides (A = winner; pooled by role), plus the ride-2
    choices by the chooser's situation at the break. Bouts decided in TB-1 / by a fall use their logged rides; bouts
    whose TB-1 ended tied with no score (tie_tb1) add two ridden-out rides and a 'bottom' pick while tied with the
    riding-time lead. A ride 2 with nothing logged counts as the chooser on bottom (a neutral pick is logged as
    "Neutral (0:30)")."""
    expo = {"bottom": 0.0, "neutral": 0.0}
    cnt = {k: 0 for k in ("esc", "rev", "nf", "fall", "pen_bot", "pen_top", "td_trail", "td_lead", "td_even",
                          "pen_trail", "pen_lead", "pen_even")}
    expo.update({"neutral_uneven": 0.0, "neutral_even": 0.0})
    picks = []                                                   # (situation, pick) from the chooser's side
    for bk, r in ot[(ot["clean"] | ot["tie_tb1"]) & ot["bot1"].isin(["w", "l"])].iterrows():
        c2 = r["chooser2"] or other(r["bot1"])
        if r["tie_tb1"]:
            expo["bottom"] += 2 * RIDE
            picks.append(("tied, riding-time lead", "bottom"))
            continue
        L = [e for e in evs.get(bk, []) if e["ot_period"] in (2, 3)]
        if not L and r["result_type"] != "TB-1":
            continue
        m_, r_ = 0, 0.0
        for ride, per in ((1, 2), (2, 3)):
            if ride == 1:
                pos = "A_bottom" if r["bot1"] == "w" else "A_top"
            else:
                pos = r["start2"] or ("A_bottom" if c2 == "w" else "A_top")
                sg = 1 if c2 == "w" else -1
                sit = "behind" if sg * m_ < 0 else "tied, riding-time lead" if (m_ == 0 and sg * r_ > 0) else "other"
                pk = "neutral" if pos == "neutral" else ("bottom" if (pos == "A_bottom") == (c2 == "w") else "top")
                picks.append((sit, pk))
            evr = [e for e in L if e["ot_period"] == per]
            clocks = [e["ot_clock"] for e in evr]
            t = float(RIDE)
            for j, e in enumerate(evr):
                te = clocks[j]
                if te is None:
                    nxt = next((c for c in clocks[j + 1:] if c is not None), 0.0)
                    te = (t + min(nxt, t)) / 2
                te = min(te, t)
                expo["neutral" if pos == "neutral" else "bottom"] += t - te
                if pos == "neutral":
                    lead = "w" if (m_ > 0 or (m_ == 0 and r_ > 0)) else "l" if (m_ < 0 or (m_ == 0 and r_ < 0)) else ""
                    expo["neutral_uneven" if lead else "neutral_even"] += t - te
                r_ += (1 if pos == "A_top" else -1 if pos == "A_bottom" else 0) * (t - te)
                t = te
                a, ev_ = e["actor"], e["event"]
                bottom = "w" if pos == "A_bottom" else "l" if pos == "A_top" else None
                if pos == "neutral":
                    role = "even" if not lead else ("lead" if a == lead else "trail")
                    if ev_ == "takedown":
                        cnt[f"td_{role}"] += 1
                    elif ev_ == "penalty":
                        cnt[f"pen_{role}"] += int(e["points"] or 1)
                else:
                    if ev_ == "escape" and a == bottom:
                        cnt["esc"] += 1
                    elif ev_ == "reversal" and a == bottom:
                        cnt["rev"] += 1
                    elif ev_ == "near_fall" and a != bottom:
                        cnt["nf"] += 1
                    elif ev_ == "fall" and a != bottom:
                        cnt["fall"] += 1
                    elif ev_ == "penalty":
                        cnt["pen_bot" if a == bottom else "pen_top"] += int(e["points"] or 1)
                if ev_ in ("escape", "reversal", "takedown", "near_fall", "penalty"):
                    m_ += (1 if a == "w" else -1) * int(e["points"] or 0)
                if ev_ == "escape":
                    pos = "neutral"
                elif ev_ in ("reversal", "takedown"):
                    pos = "A_top" if a == "w" else "A_bottom"
                elif ev_ == "choice" and "neutral" in str(e.get("raw_text") or "").lower():
                    pos = "neutral"
                if ev_ == "fall":
                    t = 0.0
                    break
            expo["neutral" if pos == "neutral" else "bottom"] += t
            if pos == "neutral":
                lead = "w" if (m_ > 0 or (m_ == 0 and r_ > 0)) else "l" if (m_ < 0 or (m_ == 0 and r_ < 0)) else ""
                expo["neutral_uneven" if lead else "neutral_even"] += t
            r_ += (1 if pos == "A_top" else -1 if pos == "A_bottom" else 0) * t
    return expo, cnt, picks


def policy(picks):
    """Observed ride-2 pick shares by situation (add-0.5 smoothing)."""
    out = {}
    for sit in ("behind", "tied, riding-time lead"):
        c = {k: 0.5 for k in ("bottom", "neutral", "top")}
        for s_, p_ in picks:
            if s_ == sit:
                c[p_] += 1
        n = sum(c.values())
        out[sit] = {k: v / n for k, v in c.items()} | {"n": int(round(n - 1.5))}
    return out


def fit(ot, evs, years):
    d = ot[ot["year"].isin(years)]
    el, reach = sv_times(d, evs)
    h = []
    for a, b in zip(SV_EDGES[:-1], SV_EDGES[1:]):
        e_ = el.dropna()
        n = ((e_ >= a) & (e_ < b)).sum()
        x = (np.clip(e_, a, b) - a).sum() + reach.sum() * (b - a)
        h.append(float(n / x))
    expo, cnt, picks = ride_counts(d, evs)
    rates = {k: cnt[k] / expo["bottom"] for k in ("esc", "rev", "nf", "fall", "pen_bot", "pen_top")}
    for k in ("td", "pen"):
        rates[f"{k}_trail"] = cnt[f"{k}_trail"] / expo["neutral_uneven"]
        rates[f"{k}_lead"] = cnt[f"{k}_lead"] / expo["neutral_uneven"]
        # level (0-0, no riding time either way: rare) -> the average of the two roles
        rates[f"{k}_even"] = (cnt[f"{k}_even"] + cnt[f"{k}_trail"] + cnt[f"{k}_lead"]) / (
            2 * (expo["neutral_even"] + expo["neutral_uneven"]))
    kh = d[d["holder"].isin(["w", "l"]) & d["bot1"].isin(["w", "l"])]
    q = float(((kh["holder"] == kh["bot1"]).sum() + 1) / (len(kh) + 2))
    prm = {"sv_edges": SV_EDGES, "sv_hazard": h, "tb_rates": rates, "q_holder_bottom": q, "nf_points": NF_PTS,
           "ride2_policy": policy(picks),
           "fit_years": list(map(int, years)), "counts": {"exposure_seconds": expo, "events": cnt,
                                                          "holder_known": int(len(kh))}}
    # k_sv: bouts decided in SV-1 (the winner scored first)
    rs_sv = d.loc[el.index[el.notna()], "rs"].to_numpy()
    prm["k_sv"] = float(minimize_scalar(lambda k: -np.log(expit(k * rs_sv)).sum(), bounds=(0, 3),
                                        method="bounded").x)
    # k_tb: bouts that reached the tiebreaker with a known ride-1 position
    t = d[d.index.isin(reach.index[reach]) & d["bot1"].isin(["w", "l"])]
    rs_t, pos1, c2 = t["rs"].to_numpy(), t["bot1"].to_numpy(), t["chooser2"].where(t["chooser2"] != "", None)
    c2 = np.array([c if c else other(b) for c, b in zip(c2, pos1)])
    tdv = t["td"].to_numpy()

    def nll(k):
        tot = 0.0
        for tdx in np.unique(tdv):
            mm = tdv == tdx
            V1, _ = tb_tables(prm, k * rs_t[mm], prm["k_sv"] * rs_t[mm], int(tdx), keep=False)
            ci = (c2[mm] == "l").astype(int)
            pi = np.where(pos1[mm] == "w", 1, 0)
            v = np.where(ci == 0, V1[0][np.arange(mm.sum()), pi, M, R], V1[1][np.arange(mm.sum()), pi, M, R])
            tot -= np.log(np.clip(v, 1e-6, 1)).sum()
        return tot
    grid = np.round(np.arange(0, 1.61, 0.1), 2)
    ll = [nll(k) for k in grid]
    prm["k_tb"] = float(grid[int(np.argmin(ll))])
    prm["k_tb_grid_nll"] = dict(zip(map(float, grid), map(float, ll)))
    # alpha_tb: the shrink that best fits the training seasons' tiebreaker states
    T = eval_states(d, evs, dict(prm, alpha_tb=1.0))
    lt = np.log(np.clip(T.loc[T["phase"] == "tiebreaker", "wp"], 1e-6, 1 - 1e-6)
                / (1 - np.clip(T.loc[T["phase"] == "tiebreaker", "wp"], 1e-6, 1 - 1e-6)))
    prm["alpha_tb"] = float(minimize_scalar(lambda a: -np.log(expit(a * lt)).mean(), bounds=(0.3, 1.5),
                                            method="bounded").x)
    return prm


# ---------------------------------------------------------------------------------------------------------------
# held-out check
# ---------------------------------------------------------------------------------------------------------------
def eval_states(ot, evs, prm):
    """(bout_key, phase, WP_model, WP_flat) at overtime states: the start, every 10 s of sudden victory still
    live, and every tiebreaker state before an event / after a choice."""
    om = OTModel(prm)
    d = ot[ot["result_type"] != "Unknown"]
    v0 = om.start_values(d["rs"].to_numpy(), d["holder"].to_numpy(), d["td"].to_numpy())
    el, reach = sv_times(d, evs)
    out = []
    for (bk, r), v in zip(d.iterrows(), v0):
        out.append((bk, "start", v, r["wp_flat"]))
        if bk not in el.index:
            continue
        rs = round(float(r["rs"]), 2)
        V1, V2, _ = om.tables(rs, r["td"])
        pA = float(expit(prm["k_sv"] * rs))
        pb = float(p_a_bottom(prm, np.array([r["holder"]], object))[0])
        pre = pb * V1[1][RIDE, 1, M, R] + (1 - pb) * V1[0][RIDE, 0, M, R]
        for e_ in range(10, SV_LEN, 10):
            if np.isnan(el[bk]) or e_ < el[bk]:
                S = sv_survival(prm, SV_LEN - e_)
                out.append((bk, "sudden victory", pA * (1 - S) + S * pre, r["wp_flat"]))
        if reach[bk] and (r["clean"] or r["tie_tb1"]) and r["bot1"] in ("w", "l"):
            for lk in om.chain(evs.get(bk, []), r.to_dict(), rs, r["td"], r["holder"], v):
                if lk["sb"]["period"] in ("TB1", "TB2") and lk["etype"] != "clock" and lk["vb"] < 1 - 1e-12 \
                        and lk["vb"] > 1e-12:
                    out.append((bk, "tiebreaker", lk["vb"], r["wp_flat"]))
                if lk["etype"] == "ot_choice":
                    out.append((bk, "tiebreaker", lk["va"], r["wp_flat"]))
    return pd.DataFrame(out, columns=["bout_key", "phase", "wp", "flat"])


def ll(p):
    return float(-np.log(np.clip(p, 1e-6, 1)).mean())


def main():
    ot, evs, nb = load_data()
    print(f"{len(ot)} overtime bouts (SV120, table_ok); clean {ot['clean'].sum()}", flush=True)
    folds = []
    for y in FIT_YEARS:
        prm = fit(ot, evs, [x for x in FIT_YEARS if x != y])
        e = eval_states(ot[ot["year"] == y], evs, prm)
        e["year"] = y
        folds.append(e)
        print(f"  held out {y}: {len(e)} states, model {ll(e['wp']):.4f} vs flat {ll(e['flat']):.4f}", flush=True)
    H = pd.concat(folds, ignore_index=True)
    prm = fit(ot, evs, FIT_YEARS)
    MODEL.mkdir(parents=True, exist_ok=True)
    PRM_FILE.write_text(json.dumps(prm, indent=1))
    ot[["bot1", "bot1_source", "start2", "chooser2", "next_round_note", "clean", "tie_tb1", "holder"]].reset_index() \
        .to_csv(STATES / "ot_bouts.csv", index=False)
    report(ot, evs, prm, H)


def report(ot, evs, prm, H):
    om = OTModel(prm)
    el, reach = sv_times(ot, evs)
    L = ["# WPA overtime model (current rules: SV120, 2022+)\n",
         "Generated by `scripts/wpa/ot_model.py` (rules, data facts and model in its docstring). Winner-oriented; "
         "log loss = −mean log WP of the eventual winner.\n",
         f"Pool: {len(ot)} overtime bouts ({', '.join(f'{k} {v}' for k, v in ot['result_type'].value_counts().items())}); "
         f"{int(ot['clean'].sum())} usable end to end (decided in SV-1, TB-1 or by a fall without merged later rounds).\n",
         "## Fitted parameters (all 5 seasons)\n",
         "| Sudden victory, elapsed | 0–30 s | 30–60 s | 60–90 s | 90–120 s |", "|---|---:|---:|---:|---:|",
         "| scoring rate per second | " + " | ".join(f"{h * 100:.2f}%" for h in prm["sv_hazard"]) + " |",
         f"\nP(SV-1 scoreless) implied: {float(sv_survival(prm, SV_LEN)) * 100:.0f}% "
         f"(observed {reach.mean() * 100:.0f}% of {len(reach)}).\n",
         "| Tiebreaker rate per second | value | events / exposure |", "|---|---:|---|"]
    ce, cn = prm["counts"]["exposure_seconds"], prm["counts"]["events"]
    lab = {"esc": "bottom escapes", "rev": "bottom reverses", "nf": "top near fall", "fall": "top pins",
           "pen_bot": "penalty point to bottom", "pen_top": "penalty point to top",
           "td_trail": "neutral: takedown by the wrestler losing the tiebreak", "td_lead": "neutral: takedown by the leader",
           "td_even": "neutral, level: takedown (each)", "pen_trail": "neutral: penalty point to the trailer (leader stalls)",
           "pen_lead": "neutral: penalty point to the leader", "pen_even": "neutral, level: penalty point (each)"}
    for k, v in prm["tb_rates"].items():
        ex = ce["neutral_uneven"] if k.endswith(("_trail", "_lead")) else (
            2 * (ce["neutral_even"] + ce["neutral_uneven"]) if k.endswith("_even") else ce["bottom"])
        n_ = cn[k] if k in cn else sum(cn[f"{k[:-5]}_{x}"] for x in ("trail", "lead", "even"))
        L.append(f"| {lab[k]} | {v * 100:.2f}% | {n_} / {ex:.0f} s |")
    L += [f"\nImplied: P(escape or reversal within a 30-second ride) = "
          f"{(1 - np.exp(-30 * (prm['tb_rates']['esc'] + prm['tb_rates']['rev']))) * 100:.0f}%.",
          f"\nStrength: k_sv = {prm['k_sv']:.2f} (P(A scores first in SV) = expit(k_sv·rs)); k_tb = {prm['k_tb']:.2f} "
          f"(rates × exp(±k_tb·rs/2)); tiebreaker values shrunk: logit × α_tb = {prm['alpha_tb']:.2f}; later rounds = "
          f"expit(k_sv·rs). Flat step-9 value for comparison: "
          f"expit({json.loads((MODEL / 'strength_params.json').read_text())['beta_ot']:.2f}·rs).",
          f"Ride-1 holder on bottom: q = {prm['q_holder_bottom']:.2f} ({prm['counts']['holder_known']} bouts with a "
          f"first takedown / near fall; no offensive points = coin flip, 1/2).\n"]
    pol = prm["ride2_policy"]
    L += ["Ride-2 pick (the chooser = the wrestler on top in ride 1), observed, used as the chooser's habit in these "
          "two situations (elsewhere he takes his best option):\n",
          "| Chooser at the break | Bouts | Bottom | Neutral | Top |", "|---|---:|---:|---:|---:|"]
    for sit, v in pol.items():
        L.append(f"| {sit} | {v['n']} | {v['bottom'] * 100:.0f}% | {v['neutral'] * 100:.0f}% | {v['top'] * 100:.0f}% |")
    L.append(f"\n{int(ot['tie_tb1'].sum())} bouts went past TB-1 with a scoreless TB-1 (ride-out, bottom, ride-out = "
             "30-30): their tiebreaker events are the later round's, so they enter the rates as two ridden-out rides.\n")
    # held-out
    L += ["## Held out by season (fit on the other four)\n",
          "| Phase | States | Bouts | Flat β_ot | OT model | Δ |", "|---|---:|---:|---:|---:|---:|"]
    for ph in ("start", "sudden victory", "tiebreaker", None):
        g = H if ph is None else H[H["phase"] == ph]
        L.append(f"| {ph or '**all**'} | {len(g):,} | {g['bout_key'].nunique()} | {ll(g['flat']):.4f} | "
                 f"{ll(g['wp']):.4f} | {ll(g['wp']) - ll(g['flat']):+.4f} |")
    L += ["\n| Season | States | Flat | OT model | Δ |", "|---|---:|---:|---:|---:|"]
    for y, g in H.groupby("year"):
        L.append(f"| {y} | {len(g):,} | {ll(g['flat']):.4f} | {ll(g['wp']):.4f} | {ll(g['wp']) - ll(g['flat']):+.4f} |")
    # calibration (folded: the favourite's side)
    f = H[(H["wp"] - 0.5).abs() >= 0.005]      # (a state valued at exactly 1/2 has no favourite)
    f = f.assign(p=np.maximum(f["wp"], 1 - f["wp"]), y=(f["wp"] >= 0.5).astype(float))
    f["bin"] = pd.cut(f["p"], [0.5, 0.6, 0.7, 0.8, 0.9, 1.0], include_lowest=True)
    L += ["\nCalibration, held out (favourite's side):\n", "| WP bin | States | Predicted | Actual |",
          "|---|---:|---:|---:|"]
    for b, g in f.groupby("bin", observed=True):
        L.append(f"| {b} | {len(g):,} | {g['p'].mean() * 100:.1f}% | {g['y'].mean() * 100:.1f}% |")
    # checks
    t = ot[ot.index.isin(reach.index[reach]) & ot["bot1"].isin(["w", "l"])]
    tie_obs = (~t["result_type"].isin(["TB-1", "Fall"])).mean()
    ties = []
    for bk, r in t.iterrows():
        s_sv, s_tb = prm["k_sv"] * r["rs"], prm["k_tb"] * r["rs"]
        V1, _ = tb_tables(prm, [s_tb], [s_sv], int(r["td"]), keep=False, dv=0.005)
        V1b, _ = tb_tables(prm, [s_tb], [s_sv], int(r["td"]), keep=False, dv=-0.005)
        c = 0 if (r["chooser2"] or other(r["bot1"])) == "w" else 1
        pi = 1 if r["bot1"] == "w" else 0
        ties.append((V1[c][0, pi, M, R] - V1b[c][0, pi, M, R]) / 0.01)   # P(tie) = dV / d(next-round value)
    ch = t[t["start2"] != ""]
    agree, n2 = 0, 0
    for bk, r in ch.iterrows():
        V1, V2, _ = om.tables(round(float(r["rs"]), 2), r["td"])
        lk = om.chain(evs.get(bk, []), r.to_dict(), round(float(r["rs"]), 2), r["td"], r["holder"], 0.5)
        pre2 = [x for x in lk if x["etype"] == "ot_choice" and x["sub"] == "ride 2"]
        if not pre2:
            continue
        sb = pre2[0]["sb"]
        opts = {p_: V2[RIDE, POSI[p_], int(np.clip(sb["margin"], -M, M)) + M,
                       int(np.clip(round(sb["rt_diff"]), -R, R)) + R] for p_ in POSI}
        c2 = r["chooser2"] or other(r["bot1"])
        best = max(opts, key=opts.get) if c2 == "w" else min(opts, key=opts.get)
        gap = abs(opts[best] - opts[r["start2"]])
        n2 += 1
        agree += (best == r["start2"]) or gap < 0.01
    L += ["\n## Checks\n",
          f"* P(TB-1 ends tied → later rounds): model {np.mean(ties) * 100:.0f}% vs observed {tie_obs * 100:.0f}% "
          f"({len(t)} bouts that reached the tiebreaker with a known ride-1 position).",
          f"* Ride-2 choice: the logged start matches the model's best option (or is within 1 point of WP) in "
          f"{agree}/{n2} bouts.",
          f"* Start of overtime, all SV120 bouts: mean OT-model value for the winner "
          f"{om.start_values(ot['rs'].to_numpy(), ot['holder'].to_numpy(), ot['td'].to_numpy()).mean() * 100:.1f}% vs "
          f"flat {ot['wp_flat'].mean() * 100:.1f}%.",
          "* Next rounds (SV-2, TB-2, UTB) are one value (expit(k_sv·rs)); their play-by-play is merged into the "
          "first round's columns."]
    REP.write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
