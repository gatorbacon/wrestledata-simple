#!/usr/bin/env python3
"""
NCAA-tournament takedown-differential report: how often the wrestler with the
takedown edge / first takedown / nearfall points wins, and what decides bouts
when takedowns are tied. Writes one plain-text report for a window of seasons.

Data sources (see docs/matsavant.md, "NCAA Takedown-Differential Report"):
  - data/{year}/ncaa-tourney/bout_detail/{weight}.json   period-by-period events
  - data/{year}/ncaa-tourney/parsed/matches.json         official result type/score

Usage:
    .venv/bin/python scripts/analysis/td_differential_report.py --start 2024 --end 2026
    .venv/bin/python scripts/analysis/td_differential_report.py --start 2021 --end 2023 --out /tmp/r.txt

Years with no parsed/matches.json (e.g. 2020, cancelled) are skipped. Default output:
    data/analysis/td_differential_report_{start}-{end}_ncaa.txt

Conference tournaments (Big Ten, Big 12, ACC, MAC, Pac-12, SoCon pooled):
    .venv/bin/python scripts/analysis/td_differential_report.py --start 2017 --end 2019 --tourney conf
    -> data/analysis/td_differential_report_{start}-{end}_conf.txt
  Conference bout_detail has NO official result type, round or placement, so the
  conference report is ALL-BOUTS ONLY (no "decided by points" view, no All-American
  table; a most-no-takedown-wins table per single tournament replaces it) and pins
  can only be inferred: a winner trailing/tied on the scoreboard at the finish must
  have pinned (or won by default); a winner who was leading may have won either way.

Method notes
  * "Scored" events are read from each bout's `columns[].events[]`; `side` is
    already resolved against the headline at scrape time (winner/loser).
  * Takedown order uses elapsed time reconstructed from period offsets/lengths
    (P1/P2/P3 = 0/180/300s, lengths 180/120/120; OT1/2/3 = 420/480/510s,
    lengths 60/30/30; an event's clock is time REMAINING in its period).
  * "Decided by points" = official result type Dec, MD, TF, SV-*, TB-*, UTB.
    Excluded: Fall, Forfeit, Inj., DQ, and bouts whose result type can't be
    resolved (rematch pairs where the join is ambiguous).
  * KNOWN DATA ERROR HANDLED HERE: at least one bout (2026 174 Baumann-Carrigan)
    has winner/loser scores AND event sides swapped relative to the headline.
    Detected as: header winner score < loser score on a points result whose
    official score equals the reversed header score. Those bouts get their
    sides swapped and are listed in the report.
"""

import argparse
import glob
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

OFF = {"Period 1": 0, "Period 2": 180, "Period 3": 300,
       "Overtime 1": 420, "Overtime 2": 480, "Overtime 3": 510}
LEN = {"Period 1": 180, "Period 2": 120, "Period 3": 120,
       "Overtime 1": 60, "Overtime 2": 30, "Overtime 3": 30}
CLOCK = re.compile(r"\((\d+):(\d{2})\)")
SCORE = re.compile(r"^\d+-\d+$")
CATS = ["escape", "reversal", "nearfall", "penalty", "riding"]
ALLCATS = CATS + ["takedown", "adj"]
PLACE_ROUNDS = {"Final": (1, 2), "3rd": (3, 4), "5th": (5, 6), "7th": (7, 8)}
ROUND_ORDER = {"R32": 0, "C_R1": 0.5, "R16": 1, "C_R2": 1.5, "C_R3": 2.2, "QF": 2, "C_R4": 2.5, "C_QF": 2.7,
               "SF": 3, "C_SF": 3.5, "Final": 5, "3rd": 5, "5th": 5, "7th": 5}


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------
def classify(result_type):
    """points | fall | forfeit | unknown"""
    rt = result_type or ""
    if rt == "Fall":
        return "fall"
    if rt in ("Forfeit", "Inj.", "DQ"):
        return "forfeit"
    if rt in ("Dec", "MD", "TF", "UTB") or rt.startswith(("SV-", "TB-")):
        return "points"
    return "unknown"


def cat_points(text):
    t = re.sub(r"\(.*", "", text).strip()
    if t == "Escape":
        return "escape", 1
    if t == "Reversal":
        return "reversal", 2
    if t == "Riding Time":
        return "riding", 1
    m = re.match(r"^(\d+)\s*Nearfall$", t)
    if m:
        return "nearfall", int(m.group(1))
    m = re.match(r"^Penalty\s*(\d+)$", t)
    if m:
        return "penalty", int(m.group(1))
    m = re.match(r"^Takedown\s*(\d+)?$", t)
    if m:
        return "takedown", int(m.group(1)) if m.group(1) else 2  # bare "Takedown" = pre-2023-24 2-pointer
    if re.match(r"^[+-]\d+$", t):
        return "adj", int(t)
    return None, 0


def flip(side):
    return "loser" if side == "winner" else "winner"


def resolve_official(m, cands):
    """Pick the parsed/matches.json record for this bout (None if ambiguous)."""
    if len(cands) == 1:
        return cands[0]
    hdr = f"{m['winner']['score']}-{m['loser']['score']}"
    same = [c for c in cands if c["score"] == hdr]
    if len(same) == 1:
        return same[0]
    byround = [c for c in cands if c.get("round") == m.get("round")]
    if len(byround) == 1:
        return byround[0]
    if len({classify(c["result_type"]) for c in cands}) == 1:
        return cands[0]
    return None


def parse_bout(m, year, official, swapped):
    cols = m["columns"]
    fix = flip if swapped else (lambda s: s)
    td = Counter()
    nf = Counter()
    tds = []
    reg = {c: Counter() for c in ALLCATS}
    ot = {c: Counter() for c in ALLCATS}
    ot_cols = []
    last = 0
    for col in cols:
        label = col.get("label", "")
        if label not in OFF:
            continue
        is_ot = label.startswith("Overtime")
        if is_ot:
            ot_cols.append(label)
        for ev in col.get("events", []):
            side = ev.get("side")
            if side not in ("winner", "loser"):
                continue
            side = fix(side)
            text = ev.get("text", "")
            tm = CLOCK.search(text)
            elapsed = OFF[label] + LEN[label] - (int(tm.group(1)) * 60 + int(tm.group(2))) if tm else last
            last = elapsed
            cat, pts = cat_points(text)
            if cat is None:
                continue
            if cat == "takedown":
                td[side] += 1
                tds.append((elapsed, side, label))
                (ot if is_ot else reg)["takedown"][side] += pts
                continue
            if cat == "nearfall":
                nf[side] += pts
            (ot if is_ot else reg)[cat][side] += pts
    tds.sort(key=lambda x: x[0])
    rt = official["result_type"] if official else None
    return {
        "year": year, "weight": m["weight"], "round": m.get("round"),
        "winner": m["winner"]["name"], "loser": m["loser"]["name"],
        "wteam": m["winner"]["team"], "lteam": m["loser"]["team"],
        "ws": m["loser"]["score"] if swapped else m["winner"]["score"],
        "ls": m["winner"]["score"] if swapped else m["loser"]["score"],
        "rt": rt, "official_score": official["score"] if official else None,
        "round_official": official.get("round") if official else None,
        "wseed": official.get("winner_seed") if official else None,   # NCAA only (conference results carry no seeds)
        "lseed": official.get("loser_seed") if official else None,
        "cls": classify(rt) if official else "unknown",
        "td": td, "tds": tds, "nf": nf, "reg": reg, "ot": ot,
        "is_ot": bool(ot_cols), "cols": cols, "swapped": swapped,
    }


def load(years):
    bouts, notes = [], {"years": [], "skipped_years": [], "no_pbp": 0, "swapped": [], "unresolved": 0,
                        "placers": {}}
    for y in years:
        base = ROOT / f"data/{y}/ncaa-tourney"
        pf = base / "parsed/matches.json"
        if not pf.exists() or not (base / "bout_detail").exists():
            notes["skipped_years"].append(y)
            continue
        notes["years"].append(y)
        parsed = defaultdict(list)
        for pm in json.load(open(pf)):
            parsed[(pm["weight"], pm["winner_name"], pm["loser_name"])].append(pm)
            pl = PLACE_ROUNDS.get(pm["round"])  # All-Americans = top 8 = Final/3rd/5th/7th bout participants
            if pl:
                notes["placers"][(y, pm["weight"], pm["winner_name"])] = (pl[0], pm["winner_team"])
                notes["placers"][(y, pm["weight"], pm["loser_name"])] = (pl[1], pm["loser_team"])
        for f in sorted(glob.glob(str(base / "bout_detail/*.json"))):
            for m in json.load(open(f)):
                if not m.get("columns"):
                    notes["no_pbp"] += 1
                    continue
                cands = parsed.get((m["weight"], m["winner"]["name"], m["loser"]["name"]), [])
                official = resolve_official(m, cands) if cands else None
                if cands and official is None:
                    notes["unresolved"] += 1
                # swapped-side detection (header score inverted vs official points score)
                swapped = False
                ws, ls = m["winner"]["score"], m["loser"]["score"]
                if ws < ls:
                    scores = {c["score"] for c in cands if SCORE.match(c["score"] or "")}
                    if f"{ls}-{ws}" in scores and f"{ws}-{ls}" not in scores:
                        swapped = True
                b = parse_bout(m, y, official, swapped)
                if swapped:
                    notes["swapped"].append(f"{y} {m['weight']} {m.get('round')}: {m['headline']} "
                                            f"(file says {ws}-{ls}, official {ls}-{ws})")
                bouts.append(b)
    return bouts, notes


CONFS = {"big_ten": "Big Ten", "big_12": "Big 12", "acc": "ACC", "mac": "MAC", "pac_12": "Pac-12",
         "socon": "SoCon"}


SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}


def nkey(name):
    """(surname, first initial): 'Timmy McCall' and 'Timothy McCall' agree, punctuation ignored."""
    t = [x for x in re.sub(r"[`'.]", "", (name or "").lower()).split() if x not in SUFFIXES]
    if len(t) < 2:
        return re.sub(r"[^a-z]", "", (name or "").lower()), ""
    return re.sub(r"[^a-z]", "", "".join(t[1:])), t[0][0]


def resolve_conf_official(m, cands):
    """Pick the official record (built by build_conference_results.py) for a conference bout, or None."""
    if not cands:
        return None
    ws, ls = m["winner"]["score"], m["loser"]["score"]
    hdr = f"{ws}-{ls}"
    pick = None
    if len(cands) == 1:
        pick = cands[0]
    else:
        same = [c for c in cands if c["score"] == hdr]
        if len(same) == 1:
            pick = same[0]
        elif len({classify(c["result_type"]) for c in cands}) == 1:
            pick = cands[0]
    if pick is None:
        return None
    # a points result whose score is nowhere near the header score (neither equal, reversed, nor within the
    # riding-time-point-sized differences seen in the data) is a different bout of the same pair (rematch)
    if classify(pick["result_type"]) == "points" and SCORE.match(pick["score"] or ""):
        a, b = map(int, pick["score"].split("-"))
        if not ((abs(a - ws) <= 2 and abs(b - ls) <= 2) or (a, b) == (ls, ws)):
            return None
    return pick


def load_conf(years):
    """Conference-tournament bouts. Official results (result type/score/round) are joined from
    data/{year}/{conf}-tourney/parsed/matches.json (build_conference_results.py); bouts with no
    match keep cls 'unknown'."""
    bouts = []
    notes = {"mode": "conf", "has_official": True, "years": [], "skipped_years": [], "no_pbp": 0, "swapped": [],
             "unresolved": 0, "placers": {}, "coverage": Counter(), "matched": Counter(), "no_results_file": []}
    for y in years:
        found = False
        for slug, label in CONFS.items():
            files = sorted(glob.glob(str(ROOT / f"data/{y}/{slug}-tourney/bout_detail/*.json")))
            if len(files) < 9:  # missing or partial scrape (a complete bracket has 10 weights; SoCon 2016 has 9)
                continue
            found = True
            idx = defaultdict(list)
            rp = ROOT / f"data/{y}/{slug}-tourney/parsed/matches.json"
            if rp.exists():
                for r in json.load(open(rp)):
                    idx[(str(r["weight"]), nkey(r["winner_name"]), nkey(r["loser_name"]))].append(r)
            else:
                notes["no_results_file"].append(f"{y} {label}")
            for f in files:
                for m in json.load(open(f)):
                    if not m.get("columns"):
                        notes["no_pbp"] += 1
                        continue
                    ws, ls = m["winner"]["score"], m["loser"]["score"]
                    cands = idx.get((str(m["weight"]), nkey(m["winner"]["name"]), nkey(m["loser"]["name"])), [])
                    official = resolve_conf_official(m, cands)
                    is_ot = any(c.get("label", "").startswith("Overtime") for c in m["columns"])
                    swapped = False
                    if official is not None:
                        notes["matched"][(label, y)] += 1
                        if ws < ls and SCORE.match(official["score"] or ""):
                            a, b = map(int, official["score"].split("-"))
                            swapped = (a, b) == (ls, ws)
                        why = f"file says {ws}-{ls}, official {official['score']}"
                    else:
                        # No official record: a winner trailing by 15+ at the finish is impossible (a 15-point lead
                        # ends the bout as a tech fall), so it is a swapped-sides error like NCAA 2026 174
                        # Baumann-Carrigan. Smaller swaps can't be detected without an official score.
                        swapped = (not is_ot) and ls - ws >= 15
                        why = f"file says {ws}-{ls}; winner trailing by {ls - ws} is impossible"
                    if swapped:
                        notes["swapped"].append(f"{y} {label} {m['weight']}: {m['headline']} ({why})")
                    b = parse_bout(m, y, official, swapped)
                    b["conf"] = label
                    bouts.append(b)
                    notes["coverage"][(label, y)] += 1
        (notes["years"] if found else notes["skipped_years"]).append(y)
    if not any(notes["matched"].values()):
        notes["has_official"] = False  # no results files at all -> fall back to scoreboard-at-finish proxies
    return bouts, notes


# --------------------------------------------------------------------------
# stats helpers
# --------------------------------------------------------------------------
def wilson(w, n, z=1.96):
    if not n:
        return None
    p = w / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    a = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - a) / d * 100, (c + a) / d * 100


def cell(n, w):
    """-> (bouts, won, win%, CI) strings"""
    if not n:
        return f"{0:>5}", f"{'-':>5}", f"{'-':>6}", f"{'-':>11}"
    lo, hi = wilson(w, n)
    return f"{n:>5,}", f"{w:>5,}", f"{100 * w / n:>5.1f}%", f"{lo:>4.1f}-{hi:<5.1f}".rjust(11)


def pct(w, n):
    return f"{100 * w / n:.1f}%" if n else "-"


def net(d, c):
    return d[c]["winner"] - d[c]["loser"]


def labeled(label, text, width=100):
    """'Scope        text...' with a hanging indent (label column is 13 wide)"""
    lines = wrap(text, width - 13)
    return [f"{label:<13}{lines[0]}"] + [" " * 13 + x for x in lines[1:]]


def bullet(text, width=98, lead="  - "):
    lines = wrap(text, width - len(lead))
    return [lead + lines[0]] + [" " * len(lead) + x for x in lines[1:]]


def wrap(text, width=98, indent=""):
    words, lines, cur = text.split(), [], indent
    for w in words:
        if len(cur) + len(w) + 1 > width and cur.strip():
            lines.append(cur.rstrip())
            cur = indent
        cur += w + " "
    if cur.strip():
        lines.append(cur.rstrip())
    return lines


# --------------------------------------------------------------------------
# scenario tables (wrestler perspective)
# --------------------------------------------------------------------------
SCEN = [
    ("any", "Scored the first takedown (any time)"),
    ("p1", "1. First takedown in period 1"),
    ("p2", "2. First takedown in period 2 (none in period 1)"),
    ("p3", "3. First takedown in period 3 (none earlier)"),
    ("nf", "4. Scored nearfall points (any time)"),
    ("r5", "5. Gave up 1st takedown, then scored the 2nd takedown"),
    ("r6", "6. Gave up 1st takedown, then scored any later takedown"),
    ("r7", "7. Gave up 1st takedown, never scored a takedown"),
    ("td2", "8. Scored exactly 2 takedowns in the match"),
    ("td3", "9. Scored exactly 3 takedowns in the match"),
]
MEMO = [("ot", "   (memo) first takedown came in overtime"),
        ("td1", "   (memo) scored exactly 1 takedown"),
        ("td4", "   (memo) scored 4 or more takedowns")]


def scenarios(bs):
    R = defaultdict(lambda: [0, 0])
    for b in bs:
        for side in ("winner", "loser"):
            won = side == "winner"
            k = b["td"][side]
            for key, cond in (("td1", k == 1), ("td2", k == 2), ("td3", k == 3), ("td4", k >= 4)):
                if cond:
                    R[key][0] += 1
                    R[key][1] += won
            if b["nf"][side] > 0:
                R["nf"][0] += 1
                R["nf"][1] += won
        if not b["tds"]:
            continue
        _, first, label = b["tds"][0]
        won = first == "winner"
        key = "p1" if label == "Period 1" else "p2" if label == "Period 2" else "p3" if label == "Period 3" else "ot"
        for kk in ("any", key):
            R[kk][0] += 1
            R[kk][1] += won
        con = flip(first)
        cw = con == "winner"
        if len(b["tds"]) >= 2 and b["tds"][1][1] == con:
            R["r5"][0] += 1
            R["r5"][1] += cw
        if any(s == con for _, s, _ in b["tds"][1:]):
            R["r6"][0] += 1
            R["r6"][1] += cw
        else:
            R["r7"][0] += 1
            R["r7"][1] += cw
    return R


def diff_table(bs):
    """winner-relative TD differential -> {k: [n, won]} for k in 1,2,3,4(=4+) ; zero -> n"""
    D = Counter(b["td"]["winner"] - b["td"]["loser"] for b in bs)
    out = {0: [D[0], None]}
    for k in (1, 2, 3):
        won, lost = D[k], D[-k]
        out[k] = [won + lost, won]
    won = sum(v for d, v in D.items() if d >= 4)
    lost = sum(v for d, v in D.items() if d <= -4)
    out[4] = [won + lost, won]
    return out


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------
def fmt_win(b):
    """'by fall' / '3-2 in the final (tiebreaker)' / '11-3 (major decision)'"""
    if b.get("conf") and b["cls"] == "unknown":  # no official result: describe by the scoreboard at the finish
        if not b["is_ot"] and b["ws"] <= b["ls"]:
            return "by pin/default"
        return f"{b['ws']}-{b['ls']}" + (" (overtime)" if b["is_ot"] else "")
    if b["cls"] == "fall":
        return "by fall"
    res = b["official_score"] or f"{b['ws']}-{b['ls']}"
    if b["round"] == "Final":
        res += " in the final"
    rt = b["rt"] or ""
    tag = ("tiebreaker" if rt.startswith("TB-") or rt == "UTB" else
           "sudden victory" if rt.startswith("SV-") else
           "major decision" if rt == "MD" else "tech fall" if rt == "TF" else "")
    return res + (f" ({tag})" if tag else "")


def build_report(bouts, notes, start, end):
    L = []
    add = L.append
    W = 100
    rule = "=" * W
    sub = "-" * W

    pts = [b for b in bouts if b["cls"] == "points"]
    fall = [b for b in bouts if b["cls"] == "fall"]
    forf = [b for b in bouts if b["cls"] == "forfeit"]
    unk = [b for b in bouts if b["cls"] == "unknown"]
    with_td = [b for b in bouts if b["td"]["winner"] != b["td"]["loser"]]
    tied = [b for b in bouts if b["td"]["winner"] == b["td"]["loser"]]
    more_won = sum(1 for b in with_td if b["td"]["winner"] > b["td"]["loser"])

    conf = notes.get("mode") == "conf"
    has_off = notes.get("has_official", True)
    proxy = conf and not has_off  # no results files: fall back to scoreboard-at-finish proxies
    dual = has_off
    trail = [b for b in bouts if not b["is_ot"] and b["ws"] <= b["ls"]]

    add(rule)
    add(f"{'CONFERENCE' if conf else 'NCAA'} TOURNAMENT TAKEDOWN-DIFFERENTIAL REPORT  |  {start}-{end}")
    add(rule)
    add("")
    yrs = ", ".join(str(y) for y in notes["years"])
    if conf:
        L.extend(labeled("Scope", "Conference championships pooled: Big Ten, Big 12, ACC, MAC, Pac-12 and SoCon "
                         "(only the tournaments that are on file for each year - see coverage below). "
                         f"Seasons included: {yrs}."))
    else:
        add(f"Scope        NCAA Division I Championships only. Seasons included: {yrs}.")
    if notes["skipped_years"]:
        add(f"             Skipped (no play-by-play data on file): {', '.join(str(y) for y in notes['skipped_years'])}.")
    if conf:
        L.extend(labeled("Bouts", f"{len(bouts):,} bouts with play-by-play data ({notes['no_pbp']:,} more had none - "
                         "byes, forfeits and injury defaults - and are left out)."))
        if has_off:
            nm = sum(notes["matched"].values())
            L.extend(labeled("Source", "data/{year}/{conference}-tourney/bout_detail (events) + parsed/matches.json "
                             "(official results, built from the team scrapes by build_conference_results.py). "
                             f"Matched to an official result: {nm:,} of {len(bouts):,} bouts ({pct(nm, len(bouts))})."))
        else:
            add("Source       data/{year}/{conference}-tourney/bout_detail (events only; no results files found).")
        add("")
        add("Coverage    bouts with play-by-play, by conference and year ('-' = no tournament on file)")
        add("")
        cov = notes["coverage"]
        ylist = notes["years"]
        add("  " + f"{'Conference':<12}" + "".join(f"{y:>7}" for y in ylist) + f"{'Total':>9}")
        for label in CONFS.values():
            tot = sum(cov[(label, y)] for y in ylist)
            if not tot:
                continue
            add("  " + f"{label:<12}" + "".join(f"{(cov[(label, y)] or '-'):>7}" for y in ylist) + f"{tot:>9,}")
        add("  " + f"{'All':<12}" + "".join(f"{sum(cov[(l, y)] for l in CONFS.values()):>7}" for y in ylist)
            + f"{len(bouts):>9,}")
    else:
        add(f"Bouts        {len(bouts):,} bouts with play-by-play data "
            f"({notes['no_pbp']} more had none - all forfeits/injury defaults - and are left out).")
        add("Source       data/{year}/ncaa-tourney/bout_detail (events) + parsed/matches.json (official result).")
    add("")
    add("HOW TO READ THIS REPORT")
    bullets = [
        "'Bouts' = wrestler-bouts. Most scenarios count BOTH wrestlers in a bout, each from their own "
        "point of view, so a scenario like 'scored nearfall points' can include the winner and the loser "
        "of the same bout. 'Won' = how many of those wrestlers won the bout.",
    ]
    if proxy:
        bullets.append(
            "IMPORTANT: conference data has no official result type, so there is NO 'decided by points' "
            "view here - every table is ALL BOUTS and includes pins. (In the NCAA tournament about 10% of "
            "bouts were pins.) Where a table needs to separate pins, it uses the scoreboard at the finish: "
            "a winner who is TRAILING or TIED at the finish must have won by pin or default; a winner who "
            "was LEADING may have won on points or by pin, and can't be told apart.")
    else:
        bullets.append(
            "Every table has two blocks: ALL BOUTS, and DECIDED BY POINTS ONLY. 'Decided by points' means "
            "the official result was a decision, major decision, tech fall, or a sudden-victory / tiebreaker "
            "overtime. It EXCLUDES pins (falls), forfeits, injury defaults, disqualifications, and "
            f"{len(unk)} bout{'s' if len(unk) != 1 else ''} whose official result could not be matched.")
    bullets += [
        "Takedown differential = takedowns scored minus takedowns allowed in the bout (overtime "
        "included). Reversals, escapes and nearfall are NOT takedowns.",
        "95% CI = Wilson 95% confidence interval on the win %. Small samples have wide intervals; "
        "don't read much into gaps that fit inside each other's intervals.",
        "A pin is not logged as a scoring event, so 'nearfall points' only counts nearfall that was "
        "actually awarded points before the match ended.",
    ]
    for t in bullets:
        L.extend(bullet(t, W))
    add("")

    # ---------------- at a glance ----------------
    add(rule)
    add("AT A GLANCE")
    add(rule)
    def star(t):
        L.extend(bullet(t, W, "  * "))

    star(f"{pct(len(with_td), len(bouts))} of bouts ({len(with_td):,} of {len(bouts):,}) had a takedown "
         f"differential; {pct(len(tied), len(bouts))} ({len(tied):,}) were tied on takedowns "
         f"(0-0 counts as tied).")
    star(f"When there was a differential, the wrestler with MORE takedowns won "
         f"{more_won:,} of {len(with_td):,} bouts ({pct(more_won, len(with_td))}).")
    if dual:
        dpts = [b for b in pts if b["td"]["winner"] != b["td"]["loser"]]
        mp = sum(1 for b in dpts if b["td"]["winner"] > b["td"]["loser"])
        star(f"Counting only bouts decided by points, that figure is {mp:,} of {len(dpts):,} "
             f"({pct(mp, len(dpts))}).")
        star(f"How the {len(bouts):,} bouts ended: {len(pts):,} by points ({pct(len(pts), len(bouts))}), "
             f"{len(fall):,} by fall ({pct(len(fall), len(bouts))}), {len(forf):,} forfeit/injury/DQ, "
             f"{len(unk):,} unmatched.")
    else:
        star(f"{len(trail):,} bouts ({pct(len(trail), len(bouts))}) ended with the winner trailing or tied on the "
             f"scoreboard (so a pin or default). That is a floor for the pin rate: pins by a wrestler who was "
             f"ahead can't be identified in conference data.")
    add("")

    # ---------------- section 1: TD differential ----------------
    add(rule)
    add("1. TAKEDOWN DIFFERENTIAL -> WIN %")
    add(rule)
    add("For each differential, the wrestler on the + side is shown. The wrestler on the - side has the")
    add("mirror result (100% minus the win % shown), since it is the same bouts from the other side.")
    add("At 0 the win % is 50% by construction (both wrestlers are at 0 in the same bout) so only the")
    add("bout count is meaningful there.")
    add("")
    dt_all, dt_pts = diff_table(bouts), diff_table(pts)
    hdr1 = f"{'TD differential':<18}| {'ALL BOUTS':^33}" + (f" | {'DECIDED BY POINTS ONLY':^33}" if dual else "")
    hdr2 = (f"{'':<18}| {'Bouts':>5} {'Won':>5} {'Win %':>6} {'95% CI':>11}"
            + (f" | {'Bouts':>5} {'Won':>5} {'Win %':>6} {'95% CI':>11}" if dual else ""))
    add(hdr1)
    add(hdr2)
    add(sub)
    labels = {0: "0 (tied)", 1: "+1", 2: "+2", 3: "+3", 4: "+4 or more"}
    for k in (0, 1, 2, 3, 4):
        if k == 0:
            add(f"{labels[k]:<18}| {dt_all[0][0]:>5,} {'-':>5} {'50.0%':>6} {'(by constr.)':>11}"
                + (f" | {dt_pts[0][0]:>5,} {'-':>5} {'50.0%':>6} {'(by constr.)':>11}" if dual else ""))
        else:
            a, p = cell(*dt_all[k]), cell(*dt_pts[k])
            add(f"{labels[k]:<18}| {' '.join(a)}" + (f" | {' '.join(p)}" if dual else ""))
    add(sub)
    add("")

    # upsets by differential and how they ended
    add("Upsets: bouts where the wrestler with FEWER takedowns won" + ("" if proxy else ", by how the bout ended"))
    add("")
    if proxy:
        add(f"{'Winner was behind by':<22}{'Trailing/tied at finish':>25}{'Led at finish':>16}{'Total':>7}"
            f"{'Bouts w/ that edge':>20}")
        add(f"{'':<22}{'(pin or default)':>25}{'(points or pin)':>16}")
    else:
        add(f"{'Winner was behind by':<22}{'Dec/MD/TF':>10}{'OT dec.':>9}{'Fall':>6}{'For/Inj/DQ':>12}"
            f"{'Unmatched':>11}{'Total':>7}{'Bouts w/ that edge':>20}")
    add(sub)
    ups = defaultdict(Counter)
    tot_at = Counter()
    for b in bouts:
        d = b["td"]["winner"] - b["td"]["loser"]
        k = min(abs(d), 4)
        if d != 0:
            tot_at[k] += 1
        if d < 0:
            if proxy:
                col = "trail" if (not b["is_ot"] and b["ws"] <= b["ls"]) else "led"
            else:
                col = ("ot" if b["is_ot"] and b["cls"] == "points"
                       else "points" if b["cls"] == "points"
                       else b["cls"])
            ups[k][col] += 1
    for k in (1, 2, 3, 4):
        u = ups[k]
        t = sum(u.values())
        lab = f"{k} takedown{'s' if k > 1 else ''}" if k < 4 else "4+ takedowns"
        if proxy:
            add(f"{lab:<22}{u['trail']:>25}{u['led']:>16}{t:>7}{tot_at[k]:>20,}")
        else:
            add(f"{lab:<22}{u['points']:>10}{u['ot']:>9}{u['fall']:>6}{u['forfeit']:>12}{u['unknown']:>11}{t:>7}"
                f"{tot_at[k]:>20,}")
    add(sub)
    add("")

    big = [b for b in bouts if b["td"]["winner"] - b["td"]["loser"] <= -2]
    add(f"Every upset where the winner was behind by 2 or more takedowns ({len(big)} bouts):")
    add("")
    for b in sorted(big, key=lambda b: (b["year"], b.get("conf", ""), b["weight"], str(b["round"]))):
        d = b["td"]["loser"] - b["td"]["winner"]
        if proxy:
            where = f"{b['year']} {b['conf']} {b['weight']}"
            fin = f"{b['ws']}-{b['ls']}"
            how = (f"finish {fin}: winner trailing/tied = pin or default" if (not b["is_ot"] and b["ws"] <= b["ls"])
                   else f"finish {fin}" + (" (overtime)" if b["is_ot"] else ""))
            add(f"  {where:<22} {b['winner']} ({b['wteam']}) def. {b['loser']} ({b['lteam']})")
            add(f"        {how}  |  takedowns {b['td']['winner']}-{b['td']['loser']} (behind by {d})")
            continue
        how = b["rt"] or "?"
        if b["cls"] == "fall":
            how = "Fall"
            score = f"(score at pin {b['ws']}-{b['ls']})"
        else:
            score = b["official_score"] or f"{b['ws']}-{b['ls']}"
        where = f"{b['year']} {b['conf']} {b['weight']}" if conf else f"{b['year']} {b['weight']} {str(b['round']):<5}"
        rnd = f" [{b['round_official']}]" if conf and b.get("round_official") else ""
        add(f"  {where} {b['winner']} ({b['wteam']}) def. {b['loser']} ({b['lteam']}){rnd}")
        add(f"        {how} {score}  |  takedowns {b['td']['winner']}-{b['td']['loser']} "
            f"(behind by {d})")
    if not big:
        add("  (none)")
    add("")

    # ---------------- section 2: scenarios ----------------
    add(rule)
    add("2. WIN % BY SCENARIO (each wrestler counted from their own point of view)")
    add(rule)
    add("Scenarios 1-3 split the first takedown by the period it happened in. Scenarios 5-7 look at")
    add("the wrestler who gave up the first takedown. Scenarios overlap (e.g. a wrestler with nearfall")
    add("points usually also has the first takedown), so rows do not add up to the bout total.")
    add("")
    sa, sp = scenarios(bouts), scenarios(pts)
    add(f"{'Scenario':<56}| {'ALL BOUTS':^33}" + (f" | {'DECIDED BY POINTS ONLY':^33}" if dual else ""))
    add(f"{'':<56}| {'Bouts':>5} {'Won':>5} {'Win %':>6} {'95% CI':>11}"
        + (f" | {'Bouts':>5} {'Won':>5} {'Win %':>6} {'95% CI':>11}" if dual else ""))
    tw = 132 if dual else 98
    add("-" * tw)

    def srow(lab, key):
        a, p = cell(*sa[key]), cell(*sp[key])
        add(f"{lab:<56}| {' '.join(a)}" + (f" | {' '.join(p)}" if dual else ""))

    for key, lab in SCEN:
        srow(lab, key)
        if key == "p3":
            srow(MEMO[0][1], "ot")
    for key, lab in MEMO[1:]:
        srow(lab, key)
    add("-" * tw)
    add("A first takedown in overtime ends a sudden-victory bout, so that memo row is 100% by rule.")
    add("")

    # ---------------- section 3: tied on takedowns ----------------
    Z = tied
    zot = [b for b in Z if b["is_ot"]]
    if proxy:  # no official result type: split regulation bouts by the scoreboard at the finish
        zreg = [b for b in Z if not b["is_ot"] and b["ws"] > b["ls"]]
        zfall = [b for b in Z if not b["is_ot"] and b["ws"] <= b["ls"]]
        zoth = []
    else:
        zreg = [b for b in Z if not b["is_ot"] and b["cls"] == "points"]
        zfall = [b for b in Z if not b["is_ot"] and b["cls"] == "fall"]
        zoth = [b for b in Z if not b["is_ot"] and b["cls"] in ("forfeit", "unknown")]
    add(rule)
    add("3. WHEN TAKEDOWNS ARE TIED: WHAT DECIDES THE BOUT")
    add(rule)
    add(f"{len(Z):,} bouts ({pct(len(Z), len(bouts))}) were tied on takedowns (including 0-0).")
    add("")
    if proxy:
        add(f"  Regulation, winner LED at the finish        {len(zreg):>5,}  ({pct(len(zreg), len(Z))})")
        add(f"  Went to overtime                            {len(zot):>5,}  ({pct(len(zot), len(Z))})")
        add(f"  Regulation, winner trailing/tied (pin/dflt) {len(zfall):>5,}  ({pct(len(zfall), len(Z))})")
    else:
        add(f"  Decided by points in regulation   {len(zreg):>5,}  ({pct(len(zreg), len(Z))})")
        add(f"  Went to overtime                  {len(zot):>5,}  ({pct(len(zot), len(Z))})")
        add(f"  Ended in a fall (regulation)      {len(zfall):>5,}  ({pct(len(zfall), len(Z))})")
        add(f"  Forfeit / injury / DQ / unmatched {len(zoth):>5,}  ({pct(len(zoth), len(Z))})")
    add("")

    # 3a regulation category table
    add("3a. REGULATION, " + ("winner led at the finish" if proxy else "decided by points")
        + " -- win % by scoring-category edge")
    add("-" * W)
    if proxy:
        L.extend(wrap("CAVEAT: without official results this group also includes pins where the winner was ahead "
                      "when the pin happened (about 5% of the equivalent NCAA group, 2015-2026). Those bouts were "
                      "not decided by the points shown.", W))
    add(f"{len(zreg):,} bouts. Since takedowns cancel out, the winner is whoever is ahead in the other")
    add("categories combined. Edges are measured in POINTS (escape 1, reversal 2, nearfall 2-4,")
    add("penalty as awarded, riding time 1). The + wrestler's win % is shown; the - wrestler's is the")
    add("mirror.")
    rec = sum(1 for b in zreg
              if sum(b["reg"][c]["winner"] for c in ALLCATS) == b["ws"]
              and sum(b["reg"][c]["loser"] for c in ALLCATS) == b["ls"])
    add(f"Check: in {rec:,} of these {len(zreg):,} bouts the scoring events add up exactly to the final score.")
    add("")
    add(f"{'Category edge':<24}{'+1 pt':>16}{'+2 pts':>16}{'+3 or more':>16}")
    add("-" * 72)
    names = {"escape": "Escape", "reversal": "Reversal", "nearfall": "Nearfall", "penalty": "Penalty",
             "riding": "Riding time"}
    for c in CATS:
        cells = []
        for k in (1, 2, 3):
            w = sum(1 for b in zreg if net(b["reg"], c) > 0 and min(net(b["reg"], c), 3) == k)
            l = sum(1 for b in zreg if net(b["reg"], c) < 0 and min(-net(b["reg"], c), 3) == k)
            n = w + l
            cells.append(f"{w}/{n} = {100 * w / n:.0f}%" if n else "-")
        add(f"{names[c]:<24}" + "".join(f"{x:>16}" for x in cells))
    add("-" * 72)
    add("(cell = bouts won / bouts with that edge = win %; '-' = never happened or not possible)")
    add("")
    ahead = Counter()
    for b in zreg:
        for c in CATS:
            if net(b["reg"], c) > 0:
                ahead[c] += 1
    add("How often the eventual winner was AHEAD in each category:")
    for c in sorted(CATS, key=lambda c: -ahead[c]):
        add(f"  {names[c]:<12}{ahead[c]:>5}  ({pct(ahead[c], len(zreg))} of {len(zreg):,} bouts)")
    add("")
    combos = Counter(tuple(c for c in CATS if net(b["reg"], c) > 0) for b in zreg)
    add("Most common combinations of categories in which the winner was ahead:")
    for k, v in combos.most_common(8):
        add(f"  {v:>4}  {pct(v, len(zreg)):>6}  {' + '.join(names[c].lower() for c in k) or '(none)'}")
    margins = Counter(b["ws"] - b["ls"] for b in zreg)
    add("")
    add(f"Margin of victory: {margins[1]:,} of {len(zreg):,} ({pct(margins[1], len(zreg))}) were decided by 1 point; "
        f"{margins[2]:,} ({pct(margins[2], len(zreg))}) by 2.")
    add("")

    # 3b overtime
    add("3b. OVERTIME -- how tied-on-takedowns bouts that went to overtime were decided")
    add("-" * W)
    add(f"{len(zot):,} bouts. Regulation was tied on points in "
        f"{sum(1 for b in zot if sum(b['reg'][c]['winner'] for c in ALLCATS) == sum(b['reg'][c]['loser'] for c in ALLCATS)):,}"
        f" of them.")
    add("Sudden victory (Overtime 1) is first-score-wins; the tiebreakers (Overtime 2/3) give each wrestler a")
    add("turn on bottom for 30 seconds.")
    add("")
    kinds = Counter()
    esc_check = Counter()
    for b in zot:
        ot = b["ot"]
        tb = [c for c in b["cols"] if c["label"] in ("Overtime 2", "Overtime 3")]
        sv = [c for c in b["cols"] if c["label"] == "Overtime 1"]
        if net(ot, "takedown") > 0:
            kinds["Sudden victory: takedown (winner's total only reached even because the opponent had scored earlier)"] += 1
            continue
        sv_score = [e for c in sv for e in c["events"]
                    if e.get("side") in ("winner", "loser") and re.match(r"^(\d+ Nearfall|Penalty|Escape|Reversal)", e["text"])]
        if sv_score and not tb:
            kinds["Sudden victory: non-takedown score (" + ", ".join(sorted({re.sub(r'\s*\(.*', '', e['text']) for e in sv_score})) + ")"] += 1
            continue
        tot = sum(net(ot, c) for c in ALLCATS)
        if tot > 0:
            parts = "+".join(c for c in CATS if net(ot, c) > 0) or "other"
            kinds[f"Tiebreaker: scored more tiebreak points ({parts})"] += 1
            continue
        esc = {"winner": [], "loser": []}
        for c in tb:
            for e in c["events"]:
                if e["text"].startswith("Escape") and e.get("side") in esc:
                    t = CLOCK.search(e["text"])
                    esc[e["side"]].append(30 - (int(t.group(1)) * 60 + int(t.group(2))) if t else None)
        if esc["winner"] and esc["loser"] and None not in esc["winner"] + esc["loser"]:
            faster = min(esc["winner"]) < min(esc["loser"])
            kinds["Tiebreaker: both escaped, tied on points -> the FASTER escape won" if faster
                  else "Tiebreaker: both escaped, but the slower escape won (unexplained)"] += 1
        else:
            kinds["Tiebreaker: tied on tiebreak points, other (ride-out / riding time / criteria not in data)"] += 1
    for k, v in sorted(kinds.items(), key=lambda x: -x[1]):
        add(f"  {v:>4}  {k}")
    ahead_ot = sum(1 for b in zot if sum(net(b["ot"], c) for c in ALLCATS) > 0)
    behind_ot = sum(1 for b in zot if sum(net(b["ot"], c) for c in ALLCATS) < 0)
    add("")
    add(f"  Overtime winner had MORE overtime points in {ahead_ot} bouts, FEWER in {behind_ot}, "
        f"equal in {len(zot) - ahead_ot - behind_ot} (decided by escape time / ride-out).")
    add("")
    add("3c. OTHER ENDINGS WHEN TAKEDOWNS WERE TIED")
    add("-" * W)
    if proxy:
        add(f"  Winner trailing or tied on the scoreboard at the finish (pin or default): {len(zfall)}")
        add("  (Pins by a wrestler who was ahead can't be identified, so this is a floor.)")
    else:
        add(f"  Falls in regulation: {len(zfall)}   Forfeit/injury/DQ: "
            f"{sum(1 for b in zoth if b['cls'] == 'forfeit')}   Unmatched: {sum(1 for b in zoth if b['cls'] == 'unknown')}")
    add("")

    # ---------------- section 4: All-Americans, wins without a takedown ----------------
    if conf:
        wins_by, notd = Counter(), defaultdict(list)
        for b in bouts:
            if b["cls"] == "forfeit" or (b["ws"] == 0 and b["ls"] == 0):  # forfeit/default: not a wrestled win
                continue
            k = (b["year"], b["conf"], b["weight"], b["winner"])
            wins_by[k] += 1
            if b["td"]["winner"] == 0:
                notd[k].append(b)
        counts = Counter(len(v) for v in notd.values())
        add(rule)
        add("4. WRESTLERS WITH THE MOST WINS WITHOUT A TAKEDOWN AT A SINGLE CONFERENCE TOURNAMENT")
        add(rule)
        if not notd:
            add("(no wrestler won a bout without scoring a takedown in this window)")
            add("")
        else:
            top = max(counts)
            L.extend(wrap(f"Conference data has no placements, so instead of All-Americans this lists every wrestler "
                          f"who, at one conference tournament in {start}-{end}, had the most wins in which they "
                          f"scored NOT ONE takedown: {top} such win{'s' if top != 1 else ''}. Everyone tied at that "
                          f"number is listed (first 15 shown if more).", W))
            if proxy:
                L.extend(wrap("'X of Y' = wins with no takedown out of all of that wrestler's wins at that "
                              "tournament. Pins count. Scores shown are the scoreboard at the finish; 'by "
                              "pin/default' means the winner was trailing or tied when it ended. Forfeits with no "
                              "scoring are not counted; injury defaults that came after scoring can't be told apart "
                              "and are counted.", W))
            else:
                L.extend(wrap("'X of Y' = wins with no takedown out of all of that wrestler's wins at that "
                              "tournament. Pins count. Wins by forfeit, injury default or DQ are not counted "
                              "(results are the official ones; a bout with no official match shows its finish "
                              "score).", W))
            add("")
            rows = sorted((k for k, v in notd.items() if len(v) == top), key=lambda k: (k[0], k[1], k[2], k[3]))
            cw = (27, 20, 10, 42)
            sep = "+" + "+".join("-" * (w + 2) for w in cw) + "+"

            def line(cells):
                return "| " + " | ".join(f"{c:<{w}}" for c, w in zip(cells, cw)) + " |"

            add(sep)
            add(line(["Wrestler (school)", "Tournament, wt", "No-TD wins", "Who they beat"]))
            add(sep)
            for k in rows[:15]:
                y, cf, w, name = k
                beat = [f"{b['loser']} ({b['lteam']}) {fmt_win(b)}" for b in notd[k]]
                wrapped = wrap("; ".join(beat), cw[3]) or [""]
                name_lines = wrap(f"{name} ({notd[k][0]['wteam']})", cw[0])
                where = wrap(f"{y} {cf}, {w}", cw[1])
                for i in range(max(len(wrapped), len(name_lines), len(where))):
                    add(line([name_lines[i] if i < len(name_lines) else "",
                              where[i] if i < len(where) else "",
                              f"{len(notd[k])} of {wins_by[k]}" if i == 0 else "",
                              wrapped[i] if i < len(wrapped) else ""]))
                add(sep)
            if len(rows) > 15:
                add(f"... and {len(rows) - 15} more wrestlers tied at {top}.")
            add("")
            lower = [f"{counts[c]} wrestler{'s' if counts[c] != 1 else ''} had {c} such win{'s' if c != 1 else ''}"
                     for c in sorted(counts, reverse=True) if c < top]
            if lower:
                add("For comparison: " + "; ".join(lower) + ".")
            add("")
    else:
        placers = notes["placers"]
        wins_by, notd = Counter(), defaultdict(list)
        for b in bouts:
            k = (b["year"], b["weight"], b["winner"])
            if k not in placers or b["cls"] == "forfeit":  # forfeit/injury/DQ wins aren't wrestled wins
                continue
            wins_by[k] += 1
            if b["td"]["winner"] == 0:
                notd[k].append(b)
        counts = Counter(len(v) for v in notd.values())
        add(rule)
        add("4. ALL-AMERICANS WITH THE MOST WINS WITHOUT A TAKEDOWN")
        add(rule)
        if not notd:
            add("(no All-American won a bout without scoring a takedown in this window)")
            add("")
        else:
            top = max(counts)
            L.extend(wrap(f"All-Americans (top 8 finishers) in {start}-{end} with the most wins in which they scored "
                          f"NOT ONE takedown: {top} such win{'s' if top != 1 else ''}. Everyone tied at that "
                          f"number is listed.", W))
            L.extend(wrap("'X of Y' = wins with no takedown out of all of that wrestler's wins at that tournament. "
                          "Pins count. Wins by forfeit, injury default or DQ are not counted.", W))
            add("")
            ordn = {1: "1st", 2: "2nd", 3: "3rd"}
            rows = sorted((k for k, v in notd.items() if len(v) == top), key=lambda k: (k[0], k[1], k[2]))
            cw = (27, 11, 6, 10, 42)
            sep = "+" + "+".join("-" * (w + 2) for w in cw) + "+"

            def line(cells):
                return "| " + " | ".join(f"{c:<{w}}" for c, w in zip(cells, cw)) + " |"

            add(sep)
            add(line(["Wrestler (school)", "Year, wt", "Place", "No-TD wins", "Who they beat"]))
            add(sep)
            for k in rows:
                y, w, name = k
                place, team = placers[k]
                beat = []
                for b in sorted(notd[k], key=lambda b: ROUND_ORDER.get(b["round"], 9)):
                    res = fmt_win(b)
                    beat.append(f"{b['loser']} ({b['lteam']}) {res}")
                wrapped = wrap("; ".join(beat), cw[4]) or [""]
                first = [f"{name} ({team})", f"{y}, {w}", ordn.get(place, f"{place}th"),
                         f"{len(notd[k])} of {wins_by[k]}", wrapped[0]]
                name_lines = wrap(first[0], cw[0])
                n_lines = max(len(wrapped), len(name_lines))
                for i in range(n_lines):
                    add(line([name_lines[i] if i < len(name_lines) else "",
                              first[1] if i == 0 else "", first[2] if i == 0 else "",
                              first[3] if i == 0 else "", wrapped[i] if i < len(wrapped) else ""]))
                add(sep)
            add("")
            lower = [f"{counts[c]} All-American{'s' if counts[c] != 1 else ''} had {c} such win{'s' if c != 1 else ''}"
                     for c in sorted(counts, reverse=True) if c < top]
            if lower:
                add("For comparison: " + "; ".join(lower) + ".")
            add(f"(All-Americans in the window: {len(placers)} wrestler-seasons.)")
            add("")

    # ---------------- notes ----------------
    add(rule)
    add("DATA NOTES")
    add(rule)
    if conf and has_off:
        nm = sum(notes["matched"].values())
        note_items = [
            f"Bouts with no play-by-play ({notes['no_pbp']:,}) are byes (opponent 'Unknown'), forfeits and injury "
            "defaults, and are left out.",
            f"Official results come from the team scrapes (mt/processed_data/ncaa_men), extracted by "
            f"build_conference_results.py and matched to each bout by last name + first initial + weight "
            f"(Timmy/Timothy McCall are the same wrestler): {nm:,} of {len(bouts):,} bouts matched "
            f"({pct(nm, len(bouts))}). Unmatched bouts ({len(unk):,}) count in ALL BOUTS but not in DECIDED BY "
            "POINTS. The usual reasons are a wrestler or event missing from a team scrape, or a rematch that "
            "can't be paired.",
            "A swapped-sides bout is detected against the official score (winner's score lower than the loser's "
            "and equal to the official score reversed). For unmatched bouts only the impossible case, a winner "
            "trailing by 15+, is caught.",
            "Header scores in the play-by-play file sometimes differ from the official score by 1 point "
            "(usually the riding-time point); those bouts are still matched.",
            "Only tournaments that TrackWrestling has, and that were scraped complete, are included - see the coverage "
            "table. Known real gaps: Big Ten 2020, Big 12 2016-18, MAC 2019/2021/2023, Pac-12 2015-17 and 2024-25, "
            "SoCon 2026. (Official results for some of those tournaments exist in the team scrapes and are saved "
            "in parsed/matches.json, but there is no play-by-play to analyze.)",
        ]
    elif conf:
        note_items = [
            f"Bouts with no play-by-play ({notes['no_pbp']:,}) are byes, forfeits and injury defaults; they can't be "
            "told apart here (no official results exist for conference tournaments) and are left out.",
            "No official result type or round: pins can't be separated from decisions, so nothing here is "
            "'points only', and rematches within a tournament can't be identified.",
            "The swapped-sides error found in NCAA data (about one bout in 1,500) can only be caught here when it is "
            "impossible: a winner trailing by 15+ at the finish (a 15-point lead ends a bout as a tech fall). "
            "Those are flipped and listed below; smaller swaps can't be detected. A bout where the winner's "
            "score is LOWER than the loser's (by less than 15) is treated as a pin/default.",
            "Only tournaments that TrackWrestling has, and that were scraped complete, are included - see the coverage "
            "table. Known real gaps: Big Ten 2020, Big 12 2016-18, MAC 2019/2021/2023, Pac-12 2015-17 and 2024-25, "
            "SoCon 2026; 2020 conferences ran, NCAA 2020 was cancelled.",
        ]
    else:
        note_items = [
            f"Bouts with no play-by-play ({notes['no_pbp']}) are forfeits/injury defaults (checked against the official results) and are left out.",
            "Rematch pairs (same two wrestlers meeting twice in one tournament) can't always be matched to "
            "an official result. Where they can't, the bout counts in ALL BOUTS but not in DECIDED BY POINTS. "
            f"Currently unmatched: {len(unk)}.",
        ]
    for t in note_items:
        L.extend(bullet(t, W))
    if notes["swapped"]:
        add("  - Play-by-play sides/scores that were swapped in the source file and corrected here:")
        for sw in notes["swapped"]:
            add("      * " + sw)
    else:
        add("  - No swapped-side bouts were detected in this window.")
    add("  - Falls are not logged as events, so scoring context (e.g. nearfall) before a pin may be incomplete.")
    add("")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", type=int, required=True)
    ap.add_argument("--end", type=int, required=True)
    ap.add_argument("--out", type=str, default=None)
    ap.add_argument("--tourney", choices=("ncaa", "conf"), default="ncaa",
                    help="ncaa = NCAA championships (default); conf = six conference tournaments pooled")
    a = ap.parse_args()
    bouts, notes = (load_conf if a.tourney == "conf" else load)(range(a.start, a.end + 1))
    if not bouts:
        raise SystemExit("No bouts found for that window.")
    text = build_report(bouts, notes, a.start, a.end)
    out = Path(a.out) if a.out else ROOT / f"data/analysis/td_differential_report_{a.start}-{a.end}_{a.tourney}.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    print(f"Wrote {out}  ({len(bouts):,} bouts, years {notes['years']})")


if __name__ == "__main__":
    main()
