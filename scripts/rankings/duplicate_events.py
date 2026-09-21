"""
duplicate_events.py — detect and remove duplicated tournaments/duals ("clone events") from HS match data.

TrackWrestling sometimes lists one event twice (different names and/or dates), so every bout appears twice. The
pipeline's own de-dupe keys include the exact date, so a 1+ day mismatch slips through. This module:

  * DETECTS clone event pairs (find_duplicate_event_pairs) — used by scripts/rankings/audit_duplicate_events.py,
    which classifies each pair as confirmed / review / rejected and writes CSVs for a human to review.
  * APPLIES only human-approved decisions (apply_approved_duplicate_events) — used by load_data.py behind the
    --dedupe-events flag. Approved pairs live in data/duplicate_events/approved_duplicate_events.json; the rules are
    never re-run blindly on new data.

Detection rules are documented in audit_duplicate_events.py and CLAUDE.md (Known Gotcha 9).
"""

import collections
import glob
import itertools
import json
import os
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = ROOT / "mt" / "rankings_data"
DEFAULT_OUT_DIR = ROOT / "mt" / "audits" / "duplicate_events"
DEFAULT_APPROVED_FILE = ROOT / "data" / "duplicate_events" / "approved_duplicate_events.json"

NEAR_GAP_DAYS = 3                # events this close are compared regardless of name
FAR_GAP_DAYS = 14                # events up to this far apart are compared only when names are similar
MIN_SHARED_BOUTS = 2
CONFIRM_MIN_SPECIFIC = 3         # proof bouts needed to confirm when names differ (or events are near)
CONFIRM_MIN_SPECIFIC_SIMILAR = 2 # ... when event names are similar
BACK_TO_BACK_DAYS = 1            # "same event, entered on consecutive days" (one team dated it a day off)
DUAL_VS_TOURNEY_REVIEW_MIN_SHARED = 4 # a dual-vs-tournament pair is rejected unless back-to-back with this many shared, non-conflicting bouts
CONFIRM_LARGE_MIN_SHARED = 5          # back-to-back (or same-day) clone with this many shared bouts incl. >=1 identical non-fall result
CONFIRM_MIN_SHARED_BACK_TO_BACK = 3   # shared bouts (placeholders allowed, zero conflicts) that confirm a back-to-back clone

PLACEHOLDER_TIME = "0:00"        # the only placeholder time (scraper default)
_TIME_TAIL = re.compile(r"\s+\d{1,2}:\d{2}\s*$")
_TIME_ANY = re.compile(r"(\d{1,2}:\d{2})")
_SCORE = re.compile(r"\d+-\d+")

# Words ignored when comparing event names.
_STOP = {
    "boys", "girls", "coed", "the", "of", "and", "a", "tournament", "invitational", "individual",
    "varsity", "jv", "high", "school", "hs", "vs", "tourney", "championship", "championships",
}


# ---------------------------------------------------------------------------
# Result / event helpers
# ---------------------------------------------------------------------------

def result_type_key(result):
    """Normalize a result to a bout-identity key. Fall -> 'fall'; score results keep the score, drop the time.
    Returns None for forfeits/defaults/byes (not compared)."""
    r = (result or "").strip()
    rl = r.lower()
    if not rl or rl.startswith(("for", "m. for", "m.for", "dflt", "inj", "dq", "nc", "bye", "ff")):
        return None
    if rl.startswith("fall"):
        return "fall"
    return _TIME_TAIL.sub("", rl)


def result_time(result):
    m = _TIME_ANY.search(result or "")
    return m.group(1) if m else None


def _real_time(result):
    """The result's time if it is a real one (present and not the 0:00 placeholder), else None."""
    t = result_time(result)
    return t if t and t != PLACEHOLDER_TIME else None


def result_quality(result):
    """Higher = more informative copy. Real time beats no time beats the placeholder."""
    t = result_time(result)
    if t is None:
        return 1            # e.g. "Dec 3-2": nothing to be a placeholder about
    return 0 if t == PLACEHOLDER_TIME else 2


def times_conflict(res_a, res_b):
    """True when both copies carry a REAL time and the times differ (=> two different results)."""
    ta, tb = _real_time(res_a), _real_time(res_b)
    return bool(ta and tb and ta != tb)


def is_specific_pair(key, res_a, res_b):
    """True when two compatible copies agree on real evidence: a score, or an identical real fall time."""
    if key != "fall":
        return bool(_SCORE.search(res_a or ""))
    ta, tb = _real_time(res_a), _real_time(res_b)
    return bool(ta) and ta == tb


def _event_tokens(name):
    toks = set(re.findall(r"[a-z0-9]+", (name or "").lower()))
    return {t for t in toks if t not in _STOP and not re.fullmatch(r"(19|20)\d\d", t)}


def event_names_similar(a, b):
    ta, tb = _event_tokens(a), _event_tokens(b)
    if not ta or not tb:
        return (a or "").strip().lower() == (b or "").strip().lower()
    return ta <= tb or tb <= ta or len(ta & tb) / len(ta | tb) >= 0.5


_DUAL_RE = re.compile(r"^\s*vs\.?\s+(.+?)\s*$", re.IGNORECASE)
_TEAM_STOP = {"high", "school", "hs", "the"}


def dual_opponent(event_name):
    """'vs. Boyle County' -> 'Boyle County' (the opposing team named by a dual-style event); None if not a dual."""
    m = _DUAL_RE.match(event_name or "")
    return m.group(1) if m else None


def _team_tokens(s):
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if t not in _TEAM_STOP}


def team_matches(label, team):
    ta, tb = _team_tokens(label), _team_tokens(team)
    return bool(ta and tb and (ta <= tb or tb <= ta))


def is_mirrored_dual(event_a, event_b, matches, names):
    """'vs. Team A' and 'vs. Team B' are the SAME dual seen from each team's side when every shared bout is
    a Team A wrestler against a Team B wrestler (one team's coach entered it on a different day)."""
    ta, tb = dual_opponent(event_a), dual_opponent(event_b)
    if not ta or not tb or team_matches(ta, tb) or not names:
        return False
    for x, y, _ in matches:
        t1 = names.get(x["w1"], ("", ""))[1]
        t2 = names.get(x["w2"], ("", ""))[1]
        if not ((team_matches(ta, t1) and team_matches(tb, t2)) or (team_matches(ta, t2) and team_matches(tb, t1))):
            return False
    return True


def _parse_date(s):
    try:
        return datetime.strptime(s, "%m/%d/%Y")
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Loading merged bouts
# ---------------------------------------------------------------------------

def bouts_from_weight_class_data(data, gender, season):
    """Unique bouts (a bout listed in several weight-class lists counts once) from the weight-class structure
    {weight_class: {"wrestlers": {...}, "matches": [...]}} — the shape load_data.py holds in memory AND saves to
    weight_class_*.json. Returns (bouts, names) where names maps wrestler_id -> (name, team)."""
    bouts, names, seen = [], {}, set()
    for wc in sorted(data, key=str):
        d = data[wc]
        for wid, w in (d.get("wrestlers") or {}).items():
            names[str(wid)] = (w.get("name") or str(wid), w.get("team") or "")
        for m in d.get("matches", []):
            key = result_type_key(m.get("result"))
            dt = _parse_date(m.get("date", ""))
            w1, w2 = m.get("wrestler1_id"), m.get("wrestler2_id")
            if not key or not dt or not w1 or not w2:
                continue
            pair = tuple(sorted([str(w1), str(w2)]))
            event = m.get("event") or ""
            ident = (pair, m.get("date"), m.get("result"), event.lower())
            if ident in seen:          # same bout listed in several weight-class files
                continue
            seen.add(ident)
            bouts.append({
                "id": len(bouts), "gender": gender, "season": str(season), "pair": pair, "key": key,
                "result": m.get("result") or "", "date": dt, "date_str": m.get("date"), "event": event,
                "weight": str(m.get("weight_class") or ""), "w1": str(w1), "w2": str(w2),
            })
    return bouts, names


def load_merged_bouts(gender, season, data_dir=DEFAULT_DATA_DIR):
    """Read one gender/season from the saved weight_class_*.json files (output of load_data.py --save)."""
    folder = Path(data_dir) / f"hs_ky_{gender}" / str(season)
    data = {}
    for path in sorted(glob.glob(str(folder / "weight_class_*.json"))):
        with open(path) as f:
            data[os.path.basename(path)] = json.load(f)
    return bouts_from_weight_class_data(data, gender, season)


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

class _UnionFind:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


def _match_rows(rows_a, rows_b):
    """Pair up copies of the same (wrestler pair, result type) bout across two events.
    Returns (matches, conflicts): matches = [(x, y, specific)], conflicts = [(x, y)] leftover rows that could not be
    paired because both carried different REAL times (i.e. genuinely different results)."""
    left_a, left_b, matches = list(rows_a), list(rows_b), []
    same = lambda p, q: (p["result"] or "").strip().lower() == (q["result"] or "").strip().lower()
    # pass 1: identical results; pass 2: compatible (a 0:00 placeholder on one side)
    for compatible in (same, lambda p, q: not times_conflict(p["result"], q["result"])):
        for x in list(left_a):
            for y in left_b:
                if compatible(x, y):
                    matches.append((x, y, is_specific_pair(x["key"], x["result"], y["result"])))
                    left_a.remove(x)
                    left_b.remove(y)
                    break
    return matches, list(zip(left_a, left_b))


def find_duplicate_event_pairs(bouts, names=None):
    """Compare events within one season's bouts (`names`: wrestler_id -> (name, team), used to recognise mirrored
    duals). Returns dicts with status 'confirmed' | 'review' | 'rejected',
    a human-readable `reason`, event/date/size info, shared/specific/conflict counts, and `matches`
    (list of (bout_a, bout_b, specific)) for every compatible shared bout."""
    events = collections.defaultdict(list)                    # (event_lower, date) -> bouts
    for b in bouts:
        events[(b["event"].strip().lower(), b["date"])].append(b)

    key_rows = collections.defaultdict(lambda: collections.defaultdict(list))   # (pair,key) -> event -> rows
    for ek, bs in events.items():
        for b in bs:
            key_rows[(b["pair"], b["key"])][ek].append(b)

    acc = collections.defaultdict(lambda: {"matches": [], "conflict_rows": []})
    for _, by_ev in key_rows.items():
        if len(by_ev) < 2:
            continue
        for e1, e2 in itertools.combinations(sorted(by_ev), 2):
            if abs((e1[1] - e2[1]).days) > FAR_GAP_DAYS:
                continue
            ms, conf_rows = _match_rows(by_ev[e1], by_ev[e2])
            a = acc[(e1, e2)]
            a["matches"].extend(ms)
            a["conflict_rows"].extend(conf_rows)

    out = []
    for (e1, e2), a in acc.items():
        matches, conflict_rows = a["matches"], a["conflict_rows"]
        conflicts = len(conflict_rows)
        if len(matches) + conflicts < MIN_SHARED_BOUTS:
            continue
        gap = abs((e1[1] - e2[1]).days)
        name_sim = event_names_similar(e1[0], e2[0])
        if gap > NEAR_GAP_DAYS and not name_sim:
            continue                                   # far apart AND differently named: not a candidate
        n_shared = len(matches)
        n_specific = sum(1 for _, _, sp in matches if sp)

        n_nonfall_proof = sum(1 for x, _, sp in matches if sp and x["key"] != "fall")   # score results (Dec/MD/TF/SV)
        mirrored = is_mirrored_dual(events[e1][0]["event"], events[e2][0]["event"], matches, names)
        need = CONFIRM_MIN_SPECIFIC_SIMILAR if name_sim else CONFIRM_MIN_SPECIFIC
        both_dual = dual_opponent(e1[0]) is not None and dual_opponent(e2[0]) is not None
        one_dual = (dual_opponent(e1[0]) is not None) != (dual_opponent(e2[0]) is not None)

        if n_shared < MIN_SHARED_BOUTS:
            status, reason = "rejected", "shared bouts have different real results (times/scores differ)"
        elif conflicts >= n_shared:
            status, reason = "rejected", "as many conflicting results as matching ones"
        elif gap > NEAR_GAP_DAYS and n_specific < CONFIRM_MIN_SPECIFIC_SIMILAR:
            continue                                   # far apart, placeholder-only overlap: not flagged
        elif n_specific >= need and conflicts <= n_specific // 5:
            status = "confirmed"
            reason = f"{n_specific} identical-proof bouts" + ("" if name_sim else " (names differ)")
        elif (gap <= BACK_TO_BACK_DAYS and conflicts == 0 and n_shared >= CONFIRM_LARGE_MIN_SHARED
              and n_nonfall_proof >= 1):
            status = "confirmed"
            reason = (f"back-to-back/same day, {n_shared} shared bouts incl. {n_nonfall_proof} identical non-fall "
                      f"result(s), none conflicting")
        elif gap <= BACK_TO_BACK_DAYS and conflicts == 0 and n_shared >= CONFIRM_MIN_SHARED_BACK_TO_BACK and mirrored:
            status = "confirmed"
            reason = (f"mirrored dual ({events[e1][0]['event']} / {events[e2][0]['event']}): every shared bout is one team vs the other, "
                      f"back-to-back days, {n_shared} shared bouts, none conflicting")
        elif (gap <= BACK_TO_BACK_DAYS and conflicts == 0 and n_shared >= CONFIRM_MIN_SHARED_BACK_TO_BACK
              and name_sim and not one_dual):
            status = "confirmed"
            reason = f"similar event names, back-to-back days, {n_shared} shared bouts, none conflicting"
        elif n_specific == 0 and one_dual and gap <= BACK_TO_BACK_DAYS and conflicts == 0 and n_shared >= DUAL_VS_TOURNEY_REVIEW_MIN_SHARED:
            status = "review"
            reason = (f"dual vs tournament, back-to-back, {n_shared} shared bouts, none conflicting "
                      f"(could be a dual-format tournament listed both ways)")
        elif n_specific == 0 and one_dual:
            status, reason = "rejected", "one is a dual, the other a tournament, and no identical-proof bouts"
        elif n_specific == 0 and not name_sim and gap > BACK_TO_BACK_DAYS and not (both_dual and mirrored):
            status, reason = "rejected", f"different events {gap} days apart with no identical-proof bouts"
        elif n_specific >= need:
            status, reason = "review", f"{conflicts} conflicting results alongside {n_specific} matching"
        elif n_specific == 0:
            status, reason = "review", "only 0:00-placeholder overlap (no identical scores/times)"
        else:
            status, reason = "review", f"only {n_specific} identical-proof bout(s); names differ"

        by1, by2 = set(), set()
        for x, y, _ in matches:
            by1.add((x["pair"], x["key"]))
        out.append({
            "status": status, "reason": reason, "gap_days": gap, "name_similar": name_sim,
            "event_a": events[e1][0]["event"], "date_a": e1[1], "n_bouts_a": len(events[e1]),
            "event_b": events[e2][0]["event"], "date_b": e2[1], "n_bouts_b": len(events[e2]),
            "shared_bouts": n_shared, "shared_specific": n_specific, "conflicts": conflicts,
            "overlap_pct": round(100.0 * len(by1) / max(1, min(len(events[e1]), len(events[e2]))), 1),
            "matches": matches, "conflict_rows": conflict_rows,
        })
    return out


# Event names the site's placement logic recognises (generate_season_accomplishments.py). When two copies of a bout
# differ, the copy carrying one of these names must survive or regional/state placement would silently change.
KEEP_PREFERRED_EVENT_PATTERNS = (
    re.compile(r"KHSAA Region\s+[1-8]", re.IGNORECASE),
    re.compile(r"KHSAA Final Round State Championship", re.IGNORECASE),
)


def recognized_event_name(name):
    return any(p.search(name or "") for p in KEEP_PREFERRED_EVENT_PATTERNS)


def keep_rank(row, event_size):
    """Higher rank = the copy to keep: (1) event name the site recognises, (2) more specific result (real time over
    0:00), (3) larger event listing, (4) earlier date."""
    return (1 if recognized_event_name(row["event"]) else 0, result_quality(row["result"]),
            event_size, -row["date"].toordinal())


def suggest_keep(x, y, size_x, size_y):
    """Which of two copies of a bout to keep. Returns ('A'|'B', reason)."""
    rx, ry = keep_rank(x, size_x), keep_rank(y, size_y)
    if rx == ry:
        return "A", "identical"
    winner = "A" if rx > ry else "B"
    for i, why in enumerate(("recognized event name (KHSAA Region/State)", "more specific result",
                             "larger event listing", "earlier date")):
        if rx[i] != ry[i]:
            return winner, why
    return winner, "tie"


def rows_removed(pairs):
    """Number of bout rows a merge would drop (clusters of duplicate copies -> keep one each)."""
    uf = _UnionFind()
    for p in pairs:
        for x, y, _ in p["matches"]:
            uf.union(x["id"], y["id"])
    clusters = collections.Counter(uf.find(i) for i in list(uf.p))
    return sum(n - 1 for n in clusters.values())


# ---------------------------------------------------------------------------
# Approved decisions + applying them
# ---------------------------------------------------------------------------

def _iso(d):
    return d if isinstance(d, str) else d.strftime("%Y-%m-%d")


def approval_key(event_a, date_a, event_b, date_b):
    """Order-insensitive identity of an event pair: event names (case-insensitive) + ISO dates."""
    return frozenset({((event_a or "").strip().lower(), _iso(date_a)), ((event_b or "").strip().lower(), _iso(date_b))})


def pair_approval_key(p):
    return approval_key(p["event_a"], p["date_a"], p["event_b"], p["date_b"])


def load_approved(path=None):
    p = Path(path or DEFAULT_APPROVED_FILE)
    if not p.exists():
        return []
    with open(p) as f:
        return json.load(f).get("approved", [])


def save_approved(entries, path=None):
    p = Path(path or DEFAULT_APPROVED_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "version": 1,
        "description": ("Human-approved duplicate-event decisions (see scripts/rankings/duplicate_events.py, CLAUDE.md "
                        "Known Gotcha 9). load_data.py --dedupe-events removes the extra copy of every bout shared by "
                        "an approved event pair. Add entries with audit_duplicate_events.py --approve-confirmed / "
                        "--approve-ids; delete an entry to stop deduplicating that pair."),
        "approved": sorted(entries, key=lambda e: (e["gender"], str(e["season"]), e["date_a"], e["event_a"])),
    }
    with open(p, "w") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")


def entry_from_pair(p, approved_on, source):
    return {
        "gender": p["gender"], "season": str(p["season"]),
        "event_a": p["event_a"], "date_a": _iso(p["date_a"]), "event_b": p["event_b"], "date_b": _iso(p["date_b"]),
        "shared_bouts": p["shared_bouts"], "status_when_approved": p["status"], "reason": p["reason"],
        "approved_on": approved_on, "source": source, "note": "",
    }


def merge_approved(existing, new_entries):
    """Add new_entries to existing, skipping pairs already approved. Returns (merged, n_added)."""
    have = {(e["gender"], str(e["season"]), approval_key(e["event_a"], e["date_a"], e["event_b"], e["date_b"]))
            for e in existing}
    merged, added = list(existing), 0
    for e in new_entries:
        k = (e["gender"], str(e["season"]), approval_key(e["event_a"], e["date_a"], e["event_b"], e["date_b"]))
        if k not in have:
            have.add(k)
            merged.append(e)
            added += 1
    return merged, added


def plan_removals(bouts, names, approved_keys):
    """Decide which bout copies to drop for the approved event pairs (one gender/season).
    Copies of the same bout form clusters (a bout listed in 3 events is one cluster); exactly one survivor per cluster
    is chosen by keep_rank. Returns (drops, missing_keys) where drops = [{"drop": row, "keep": row}] and
    missing_keys = approved pairs that no longer resolve to a detected pair (data changed)."""
    pairs = find_duplicate_event_pairs(bouts, names)
    by_key = {pair_approval_key(p): p for p in pairs}
    selected = [by_key[k] for k in approved_keys if k in by_key]
    missing = [k for k in approved_keys if k not in by_key]
    size = collections.Counter((b["event"].strip().lower(), b["date"]) for b in bouts)
    uf, rows = _UnionFind(), {}
    for p in selected:
        for x, y, _ in p["matches"]:
            rows[x["id"]], rows[y["id"]] = x, y
            uf.union(x["id"], y["id"])
    clusters = collections.defaultdict(list)
    for i, r in rows.items():
        clusters[uf.find(i)].append(r)
    drops = []
    for members in clusters.values():
        best = max(members, key=lambda r: keep_rank(r, size[(r["event"].strip().lower(), r["date"])]))
        drops.extend({"drop": r, "keep": best} for r in members if r is not best)
    return drops, missing


def apply_approved_duplicate_events(data, season, league, state, gender, approved_file=None, log_dir=None):
    """Remove approved duplicated events from `data` (HS only; silent no-op for other leagues), then print a notice if
    NEW likely duplicates remain that nobody has approved yet. Returns the number of unique bouts removed."""
    if league != "hs":
        return 0
    removed = _apply_approved(data, season, league, state, gender, approved_file, log_dir)
    _notice_new_duplicates(data, gender, season)
    return removed


def _notice_new_duplicates(data, gender, season):
    """After removal, whatever is still detected as duplicated is NEW (not approved). Tell the user."""
    bouts, names = bouts_from_weight_class_data(data, gender, season)
    pairs = find_duplicate_event_pairs(bouts, names)
    n_conf = sum(1 for p in pairs if p["status"] == "confirmed")
    n_rev = sum(1 for p in pairs if p["status"] == "review")
    if n_conf or n_rev:
        print(f"  NOTICE ({gender} {season}): {n_conf} likely duplicate event pair(s) (+{n_rev} to review) are NOT approved yet. "
              f"Review/approve with: .venv/bin/python scripts/rankings/audit_duplicate_events.py -gender {gender} -season {season}")
        print("         (then re-run Load Data for Ranking so the approved ones are removed)")
    else:
        print(f"  Duplicate events ({gender} {season}): none pending.")


def approved_drop_idents(data, gender, season, approved_file=None):
    """Read-only twin of `_apply_approved` for consumers that read RAW processed matches instead of the saved
    weight_class files (e.g. calculate_elo_ratings.py). `data` has the weight-class shape
    {key: {"wrestlers": {id: {"name", "team"}}, "matches": [{wrestler1_id, wrestler2_id, date, event, result, ...}]}}.
    Returns the set of bout identities (sorted wrestler-id pair, date string, result string, lower-cased event) that the
    approved event pairs say to drop -- the same identity `_apply_approved` matches on. Nothing is mutated or written."""
    approved = [e for e in load_approved(approved_file)
                if e["gender"] == gender and str(e["season"]) == str(season)]
    if not approved:
        return set()
    bouts, names = bouts_from_weight_class_data(data, gender, season)
    keys = {approval_key(e["event_a"], e["date_a"], e["event_b"], e["date_b"]) for e in approved}
    drops, _missing = plan_removals(bouts, names, keys)
    return {(d["drop"]["pair"], d["drop"]["date_str"], d["drop"]["result"], d["drop"]["event"].lower())
            for d in drops}


def match_ident(match, wrestler_id):
    """Bout identity of one RAW processed_data match, seen from the rostered wrestler `wrestler_id`'s file:
    (sorted [wrestler_id, opponent_id], date string, result string, lower-cased event) -- the same tuple
    `_apply_approved` / `approved_drop_idents` use, and identical from either wrestler's side. Raw matches carry only
    `opponent_id` (no winner_id/loser_id). None when there is no opponent id (byes, unresolved)."""
    opp = match.get("opponent_id")
    if not wrestler_id or not opp:
        return None
    return (tuple(sorted([str(wrestler_id), str(opp)])), match.get("date"), match.get("result"),
            (match.get("event") or "").lower())


def processed_drop_idents(gender, season, state="ky", processed_root="mt/processed_data", approved_file=None):
    """Set of bout identities (see `match_ident`) to drop from RAW `mt/processed_data/hs_{state}_{gender}/{season}`
    matches, for consumers that read that layer instead of the saved weight_class files (calculate_elo_ratings.py,
    generate_season_accomplishments.py). Uses the approved event pairs; empty set if none are approved."""
    if not [e for e in load_approved(approved_file) if e["gender"] == gender and str(e["season"]) == str(season)]:
        return set()
    folder = Path(processed_root) / f"hs_{state.lower()}_{gender}" / str(season)
    names, matches = {}, []
    for path in sorted(folder.glob("*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                team = json.load(f)
        except Exception:
            continue
        team_name = team.get("team_name", "")
        for wr in team.get("roster", []):
            wid, wname = wr.get("season_wrestler_id"), wr.get("name") or ""
            for m in wr.get("matches", []):
                ident = match_ident(m, wid)
                if not ident or m.get("result") in ("BYE", "NoResult") or "received a bye" in (m.get("summary") or "").lower():
                    continue
                won = (m.get("winner_name") or "").lower() == wname.lower()
                opp_name, opp_team = (m.get("loser_name"), m.get("loser_team")) if won else (m.get("winner_name"), m.get("winner_team"))
                names[str(wid)] = {"name": wname, "team": team_name}
                names.setdefault(str(m["opponent_id"]), {"name": opp_name, "team": opp_team})
                w1, w2 = ident[0]
                matches.append({"wrestler1_id": w1, "wrestler2_id": w2, "date": m.get("date"),
                                "event": m.get("event", ""), "result": m.get("result", ""),
                                "weight_class": m.get("weight", "")})
    return approved_drop_idents({"_": {"wrestlers": names, "matches": matches}}, gender, season, approved_file)


def _apply_approved(data, season, league, state, gender, approved_file=None, log_dir=None):
    """Remove the extra copy of every bout shared by the human-approved clone event pairs for this gender/season.
    Mutates `data` ({weight_class: {"wrestlers", "matches"}}) in place: drops the matches from EVERY weight-class list
    they appear in and decrements the affected wrestlers' matches_count/wins/losses (load_data computed those at
    extraction time). Writes an audit log CSV. Returns the number of unique bouts removed."""
    approved = [e for e in load_approved(approved_file)
                if e["gender"] == gender and str(e["season"]) == str(season)]
    if not approved:
        print(f"Duplicate-event removal: no approved decisions for {gender} {season}.")
        return 0

    bouts, names = bouts_from_weight_class_data(data, gender, season)
    keys = {approval_key(e["event_a"], e["date_a"], e["event_b"], e["date_b"]) for e in approved}
    drops, missing = plan_removals(bouts, names, keys)
    for k in missing:
        print("  WARNING: approved event pair no longer detected (data changed?): " +
              " <-> ".join(f"{ev!r} {d}" for ev, d in sorted(k, key=lambda t: t[1])))
    if not drops:
        print(f"Duplicate-event removal: {len(approved)} approved pair(s) for {gender} {season}, nothing to remove.")
        return 0

    idents = {(d["drop"]["pair"], d["drop"]["date_str"], d["drop"]["result"], d["drop"]["event"].lower()): d
              for d in drops}
    seen, delta, dropped_dates = set(), collections.defaultdict(lambda: [0, 0, 0]), collections.defaultdict(set)
    for wc_data in data.values():
        wr = wc_data.get("wrestlers", {})
        kept = []
        for m in wc_data.get("matches", []):
            w1, w2 = m.get("wrestler1_id"), m.get("wrestler2_id")
            ident = (tuple(sorted([str(w1), str(w2)])), m.get("date"), m.get("result"), (m.get("event") or "").lower())
            if ident not in idents:
                kept.append(m)
                continue
            winner = str(m.get("winner_id") or "")
            for wid in (w1, w2):                                   # keep this weight class's stats consistent
                info = wr.get(wid) or wr.get(str(wid))
                if info:
                    info["matches_count"] = max(0, info.get("matches_count", 0) - 1)
                    if winner:
                        key = "wins" if str(wid) == winner else "losses"
                        info[key] = max(0, info.get(key, 0) - 1)
            if ident not in seen:                                  # per-bout (not per-weight-class) tallies for the log
                seen.add(ident)
                for wid in (w1, w2):
                    delta[str(wid)][2] += 1
                    if winner:
                        delta[str(wid)][0 if str(wid) == winner else 1] += 1
                    dropped_dates[str(wid)].add(_iso(_parse_date(m.get("date"))))
        wc_data["matches"] = kept

    # last_match_date: only touch it when a dropped copy WAS the wrestler's latest match
    latest = {}
    for wc_data in data.values():
        for m in wc_data.get("matches", []):
            dt = _parse_date(m.get("date"))
            for wid in (m.get("wrestler1_id"), m.get("wrestler2_id")):
                if dt and wid and (str(wid) not in latest or dt > latest[str(wid)]):
                    latest[str(wid)] = dt
    for wc_data in data.values():
        for wid, info in wc_data.get("wrestlers", {}).items():
            cur = info.get("last_match_date")
            if cur and cur in dropped_dates.get(str(wid), ()):
                new = latest.get(str(wid))
                if new is None or _iso(new) < cur:
                    info["last_match_date"] = _iso(new) if new else None

    _write_apply_log(drops, names, gender, season, log_dir)
    changed = {w: v for w, v in delta.items() if v[2]}
    print(f"Duplicate-event removal ({gender} {season}): removed {len(idents)} duplicate bout(s) from "
          f"{len(approved) - len(missing)} approved event pair(s); {len(changed)} wrestler record(s) changed.")
    for wid, (w, l, n) in sorted(changed.items(), key=lambda kv: -kv[1][2])[:10]:
        nm, tm = names.get(wid, (wid, ""))
        print(f"    {nm} ({tm}): -{n} match(es)  (-{w} W, -{l} L)")
    return len(idents)


def _write_apply_log(drops, names, gender, season, log_dir=None):
    import csv
    out = Path(log_dir or DEFAULT_OUT_DIR)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"applied_{gender}_{season}.csv"
    cols = ["gender", "season", "wrestler_1", "team_1", "wrestler_2", "team_2", "weight",
            "dropped_date", "dropped_event", "dropped_result", "kept_date", "kept_event", "kept_result"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for d in drops:
            x, k = d["drop"], d["keep"]
            n1, t1 = names.get(x["w1"], (x["w1"], ""))
            n2, t2 = names.get(x["w2"], (x["w2"], ""))
            w.writerow({"gender": gender, "season": season, "wrestler_1": n1, "team_1": t1, "wrestler_2": n2, "team_2": t2,
                        "weight": x["weight"], "dropped_date": _iso(x["date"]), "dropped_event": x["event"],
                        "dropped_result": x["result"], "kept_date": _iso(k["date"]), "kept_event": k["event"],
                        "kept_result": k["result"]})
    print(f"  wrote {path}")
