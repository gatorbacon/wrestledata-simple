#!/usr/bin/env python3
"""
Shared definitions for the WPA / win-probability build (spec: TJ's wrestling_wpa_spec.md; step notes in
data/wpa/reports/). Everything that more than one WPA step needs lives here so the steps can't drift apart:

  * rules eras, period lengths, the regulation clock (t_rem = seconds left in the WHOLE regulation match)
  * the riding-time lock function (spec 2.3) and the state bins (spec 2 table)
  * mirroring a state to the other wrestler's perspective (spec 2.1)
  * loading NCAA / conference bouts with their official result joined and swapped-sides bouts corrected

Storage convention for the step-2 files (data/wpa/states/): every bout is stored once, from the WINNER's side
("w" = the wrestler the headline says won, "l" = the loser). Nothing in a stored state is derived from the result;
step 3 turns each bout into two perspectives with mirror().
"""
import glob
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts/analysis"))
import td_differential_report as R  # noqa: E402  (official-result joins, name keys)

CONFS = {"big_ten": "Big Ten", "big_12": "Big 12", "acc": "ACC", "mac": "MAC", "pac_12": "Pac-12", "socon": "SoCon"}
SCORE_RE = re.compile(r"^\d+-\d+$")

# ---------------------------------------------------------------------------------------------------------------
# Clock
# ---------------------------------------------------------------------------------------------------------------
T_TOTAL = 420  # regulation length in seconds (3:00 + 2:00 + 2:00)
# regulation period -> (length, t_rem at the END of the period)
REG = {1: (180, 240), 2: (120, 120), 3: (120, 0)}
REG_LABEL = {"Period 1": 1, "Period 2": 2, "Period 3": 3}


def t_rem_of(period, clock):
    """Seconds left in regulation, given the period (1-3) and the clock (seconds left in that period)."""
    return REG[period][1] + clock


def ot_length(n, year):
    """Length of `Overtime n`. Sudden victory (OT1) was 1:00 through 2021 and 2:00 from 2022 (data audit item 8);
    tiebreakers are 0:30. OT4+ (a second sudden victory / ultimate tiebreaker) is rare; SV length for even-numbered
    SV periods is an assumption that only affects the separate OT model."""
    sv = 60 if year <= 2021 else 120
    if n == 1 or n == 4:
        return sv
    return 30


def rules_era(year):
    """Scoring eras found in the data (audit item 15): E1 2015 = takedown 2, near fall 2/3; E2 2016-2023 = takedown 2,
    near fall 2/4; E3 2024-2026 = takedown 3, near fall 2/3/4. TJ 2026-09-29: E1 is pooled with E2 (decision D) and E3
    drives the estimates."""
    if year >= 2024:
        return "E3"
    if year >= 2016:
        return "E2"
    return "E1"


def ot_rules(year):
    return "SV60" if year <= 2021 else "SV120"


# ---------------------------------------------------------------------------------------------------------------
# Riding time lock (spec 2.3)
# ---------------------------------------------------------------------------------------------------------------
# NCAA rule: a wrestler with 1:00 or more of net riding time advantage at the end of regulation gets 1 point.
# "1:00 or more" = rt_diff >= 60 (checked against the logged riding-time points in the step-2 report).
RT_THRESHOLD = 60


def rt_status(rt_diff, t_rem):
    """rt_diff: A's net riding-time advantage in seconds (negative = B ahead). t_rem: seconds left in regulation.
    Simple bound from the spec (position not used to tighten it): A can gain at most t_rem more seconds, lose at
    most t_rem. Four outcomes, never merging locked with live."""
    max_final = rt_diff + t_rem
    min_final = rt_diff - t_rem
    if min_final >= RT_THRESHOLD:
        return "locked_in"      # A gets the point whatever happens
    if max_final <= -RT_THRESHOLD:
        return "locked_out"     # B gets the point whatever happens
    if max_final < RT_THRESHOLD and min_final > -RT_THRESHOLD:
        return "locked_none"    # nobody can reach 1:00
    return "live"


RT_STATUS_MIRROR = {"locked_in": "locked_out", "locked_out": "locked_in", "locked_none": "locked_none",
                    "live": "live", None: None}


# ---------------------------------------------------------------------------------------------------------------
# State bins (spec 2 table)
# ---------------------------------------------------------------------------------------------------------------
MARGIN_CLAMP = 15
RT_BIN_CLAMP = 6  # 10-second bins, clamped to +/-60 s


def margin_bin(margin):
    return max(-MARGIN_CLAMP, min(MARGIN_CLAMP, margin))


def t_bin(t_rem):
    """10-second bins of regulation time left: bin k = [10k, 10k+10). The single instant t_rem=420 (opening whistle)
    shares bin 41 with 410-419 so every bin is 10 s wide."""
    return min(41, int(t_rem // 10))


def rt_bin(rt_diff):
    """Riding-time differential in 10-second bins, truncated toward zero so mirror(rt_bin) == -rt_bin exactly
    (bin 0 = within 10 s either way), clamped to +/-6 (= 60 s or more)."""
    b = min(RT_BIN_CLAMP, int(abs(rt_diff) // 10))
    return b if rt_diff >= 0 else -b


# position values stored from the winner's side
POS_MIRROR = {"neutral": "neutral", "w_top": "l_top", "l_top": "w_top", "pending": "pending", "unknown": "unknown"}
SIDE_MIRROR = {"w": "l", "l": "w", "none": "none", "unknown": "unknown", None: None}


def perspective(state, side):
    """A stored (winner-oriented) state seen from `side` ('w' or 'l'), as A-relative fields:
    margin, position (neutral / A_top / A_bottom / pending / unknown), choice (A / B / none / unknown), rt_diff,
    rt_status. mirror() of the result is the other wrestler's view, which is how spec 2.1's symmetry holds."""
    sign = 1 if side == "w" else -1
    pos = state["pos"]
    if pos in ("w_top", "l_top"):
        a_top = (pos == "w_top") == (side == "w")
        pos = "A_top" if a_top else "A_bottom"
    ch = state["choice"]
    if ch in ("w", "l"):
        ch = "A" if ch == side else "B"
    rs = state["rt_status"]
    if side == "l":
        rs = RT_STATUS_MIRROR[rs]
    return {"margin": sign * state["margin"], "pos": pos, "choice": ch,
            "rt_diff": None if state["rt_diff"] is None else sign * state["rt_diff"], "rt_status": rs}


def mirror(a_state):
    """Mirror an A-relative state (output of perspective()) to B's view."""
    pos = {"A_top": "A_bottom", "A_bottom": "A_top"}.get(a_state["pos"], a_state["pos"])
    ch = {"A": "B", "B": "A"}.get(a_state["choice"], a_state["choice"])
    return {"margin": -a_state["margin"], "pos": pos, "choice": ch,
            "rt_diff": None if a_state["rt_diff"] is None else -a_state["rt_diff"],
            "rt_status": RT_STATUS_MIRROR[a_state["rt_status"]]}


# ---------------------------------------------------------------------------------------------------------------
# Seeds (decision C)
# ---------------------------------------------------------------------------------------------------------------
def strength_seed(year, seed):
    """Committee seed usable as strength signal, or None. Before 2019 only seeds 1-16 were committee seeds; 17-33
    were a random bracket draw (docs/matsavant.md, Ranking Methodology) -> unseeded (TJ decision C, 2026-09-29)."""
    if not isinstance(seed, int):
        return None
    if year <= 2018 and seed > 16:
        return None
    return seed


# ---------------------------------------------------------------------------------------------------------------
# Loading bouts
# ---------------------------------------------------------------------------------------------------------------
def result_class(rtype):
    if rtype in ("Dec", "MD"):
        return "decision"
    if rtype == "TF":
        return "tech_fall"
    if rtype == "Fall":
        return "fall"
    if rtype and (rtype.startswith("SV") or rtype.startswith("TB") or rtype == "UTB"):
        return "overtime"
    if rtype == "Inj.":
        return "injury"
    if rtype == "DQ":
        return "dq"
    if rtype in ("Forfeit", "MFF", "FF"):
        return "forfeit"
    return None


def load_bouts(kind="ncaa"):
    """Yields dicts: kind, tournament, year, weight, bout (raw), official (or None), swapped (bool).
    kind: 'ncaa' | 'conf'. Swapped-sides detection is the same as td_differential_report.py (header winner score
    below the loser's while the official score is the reverse; for conference bouts with no official record, a
    winner trailing by 15+ outside overtime)."""
    years = sorted(int(p.name) for p in (ROOT / "data").iterdir() if p.name.isdigit())
    for y in years:
        if kind == "ncaa":
            base = ROOT / f"data/{y}/ncaa-tourney"
            if not (base / "bout_detail").exists():
                continue
            parsed = defaultdict(list)
            pf = base / "parsed/matches.json"
            if pf.exists():
                for pm in json.load(open(pf)):
                    parsed[(pm["weight"], pm["winner_name"], pm["loser_name"])].append(pm)
            for f in sorted(glob.glob(str(base / "bout_detail/*.json"))):
                for m in json.load(open(f)):
                    cands = parsed.get((m["weight"], m["winner"]["name"], m["loser"]["name"]), [])
                    off = R.resolve_official(m, cands) if cands else None
                    ws, ls = m["winner"]["score"], m["loser"]["score"]
                    # A winner who is not ahead at the end of a bout with no overtime can only have won by fall /
                    # injury default / DQ. If the resolver picked a points result for such a bout (a rematch pair
                    # whose round label is wrong in the scrape -- e.g. 2019 125 bout 61 is labelled QF but is the
                    # 5th-place fall), take the pair's only non-points result instead.
                    no_ot = not any(c.get("label", "").startswith("Overtime") for c in m.get("columns") or [])
                    if (off and ws <= ls and no_ot and result_class(off.get("result_type")) in ("decision", "tech_fall")
                            and off.get("score") not in (f"{ws}-{ls}", f"{ls}-{ws}")):
                        alt = [c for c in cands if result_class(c.get("result_type")) in ("fall", "injury", "dq")]
                        if len(alt) == 1:
                            off = alt[0]
                    swapped = False
                    if ws < ls:
                        scores = {c["score"] for c in cands if SCORE_RE.match(c["score"] or "")}
                        swapped = f"{ls}-{ws}" in scores and f"{ws}-{ls}" not in scores
                    yield {"kind": "ncaa", "tournament": "NCAA", "year": y, "weight": m["weight"], "bout": m,
                           "official": off, "swapped": swapped}
        else:
            for slug, label in CONFS.items():
                files = sorted(glob.glob(str(ROOT / f"data/{y}/{slug}-tourney/bout_detail/*.json")))
                if not files:
                    continue
                idx = defaultdict(list)
                rp = ROOT / f"data/{y}/{slug}-tourney/parsed/matches.json"
                if rp.exists():
                    for r in json.load(open(rp)):
                        idx[(str(r["weight"]), R.nkey(r["winner_name"]), R.nkey(r["loser_name"]))].append(r)
                for f in files:
                    for m in json.load(open(f)):
                        cands = idx.get((str(m["weight"]), R.nkey(m["winner"]["name"]), R.nkey(m["loser"]["name"])), [])
                        off = R.resolve_conf_official(m, cands) if m.get("columns") else None
                        ws, ls = m["winner"]["score"], m["loser"]["score"]
                        is_ot = any(c.get("label", "").startswith("Overtime") for c in m.get("columns") or [])
                        if off is not None:
                            swapped = False
                            if ws < ls and SCORE_RE.match(off["score"] or ""):
                                a, b = map(int, off["score"].split("-"))
                                swapped = (a, b) == (ls, ws)
                        else:
                            swapped = (not is_ot) and ls - ws >= 15
                        yield {"kind": "conf", "tournament": label, "year": y, "weight": m["weight"], "bout": m,
                               "official": off, "swapped": swapped}
