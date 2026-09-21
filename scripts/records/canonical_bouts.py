#!/usr/bin/env python3
"""
Canonical bout list for HS seasons: ONE place that decides which bouts exist and who won, so that every season
record on the site (header record, career summary, Season Stats box, match history, leaderboards) can be derived
from the same list instead of being counted separately by five different scripts (see CLAUDE.md Known Gotcha 15).

STATUS: read-only / not wired into the pipeline yet. `compare_season_records.py` uses it to show exactly how the
current numbers differ from it. Nothing here writes to frontend/ or to any existing data file.

Source: mt/processed_data/hs_{state}_{gender}/{season}/*.json (raw per-wrestler rows). A bout normally appears in BOTH
wrestlers' files ("views"); some appear in only one.

Rules (approved by TJ 2026-09-21):
  1. COUNTS: every decided bout, including forfeits, medical forfeits (MFF: `MFFL`, `M. For.`), injury defaults,
     defaults and DQs. NOT counted: byes, no-results (`NoResult`, override result `NC`), scraper-error rows.
  2. BOUT IDENTITY: same two wrestlers + same date + same result TYPE (fall/dec/MD/TF/...) is ONE bout, however many
     rows/views list it. Exact duplicate rows (e.g. Tuttle's Nathan Sargent win listed twice) therefore collapse.
     The bout is credited to BOTH wrestlers even if only one wrestler's file lists it.
  3. DIFFERENT RESULT = DIFFERENT BOUT (TJ 2026-09-21: never ignore a match whose result differs). Within a same-pair/date/type group,
     rows conflict when both carry a score and the scores differ, or both carry a real (non-0:00) time and the times differ (`0:00` is a
     placeholder, compatible with any time). Conflicting rows are separate bouts -- EXCEPT when no wrestler's own file lists both versions
     (A's file says 11-2, B's says 14-2): that is one bout the two sides recorded differently and counts once (flagged in the stats).
  3b. REMATCH BY LABEL only when very clear: rows with compatible results but different round labels ("Quarterfinals" vs "3rd Place Match")
     are separate bouts only if BOTH wrestlers' files each list BOTH labels; otherwise they are one bout (a duplicate). Unlabeled rows attach
     to a labeled bout. Bouts vs an unknown opponent (forfeits etc., no opponent id) are keyed by wrestler+event+date+type; distinct
     round labels there stay separate bouts (different unknown opponents), and two forfeits at different events on one day both count
     (the profile builder merges them).
  4. MFF counts as a win/loss (it is only excluded from bonus/pin rates by the consumers, like forfeits).
Also applied, exactly as the existing pipeline does: approved duplicate-event removals (data/duplicate_events/,
Known Gotcha 9) and mt/rankings_data/.../match_overrides.json (removals + result/winner overrides).
NOT applied: manual_matches.json (only build_relationships uses it, for head-to-head; never part of a displayed record).
Proposed but NOT decided (needs TJ): bouts labeled "Exhibition" are counted by default (as today); pass
exclude_exhibitions=True to drop them.

Public API:
    sb = build_season("boys", 2025)         -> SeasonBouts
    sb.record("29789127132")                -> {"W": 26, "L": 8, "ff_w": 2, "mff": 0, ...}
    sb.wrestler_bouts("29789127132")        -> list of bout dicts (date, event, round, opponent, result, ...)
"""
import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "rankings"))
from duplicate_events import match_ident, processed_drop_idents  # noqa: E402

DIVISION_WORDS = {"varsity", "junior varsity", "jv", "girls varsity", "girls junior varsity", "girls jv", "freshman",
                  "middle school", "boys varsity", "boys junior varsity", "boys jv", "novice", "open"}
ROUND_RE = re.compile(
    r"^(champ\.? round \d+|cons\.? round \d+|round \d+|quarterfinals|semifinals|cons\.? semis|cons\.? quarters|"
    r"cons\.? \d+(?:st|nd|rd|th)|\d+(?:st|nd|rd|th) place match|cross bracket|exhibition|pigtail|finals?|"
    r"championship)$")

COUNTED_TYPES = {"FALL", "TF", "MD", "DEC", "OT", "FF", "MFF", "INJ", "DFLT", "DQ", "OTHER"}
EXCLUDED_TYPES = {"BYE", "NORESULT", "ERROR", "NONE"}


def norm_name(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def result_type(res):
    r = (res or "").strip().upper()
    if not r:
        return "NONE"
    if r == "BYE":
        return "BYE"
    if r.startswith("NORESULT") or r in ("NC", "NO CONTEST"):
        return "NORESULT"
    if r.startswith("SCRAPER"):
        return "ERROR"
    if "MFF" in r or r.startswith("M.") or "MEDICAL" in r:
        return "MFF"
    if r.startswith("FOR") or r == "FF":
        return "FF"
    if r.startswith("FALL"):
        return "FALL"
    if r.startswith("TF"):
        return "TF"
    if r.startswith("MD"):
        return "MD"
    if r.startswith("DEC"):
        return "DEC"
    if r.startswith(("SV", "TB", "UTB")):
        return "OT"
    if r.startswith("INJ"):
        return "INJ"
    if r.startswith(("DEF", "DFLT")):
        return "DFLT"
    if r.startswith("DQ"):
        return "DQ"
    return "OTHER"


def parse_round(summary):
    """Bracket round label from a summary like 'Varsity - Champ. Round 2 - A (X) over B (Y) (Fall 0:13)'; None if unrecognised."""
    parts = (summary or "").split(" - ")
    for p in parts[:-1]:
        t = re.sub(r"\s+", " ", p.strip().lower())
        if t in DIVISION_WORDS:
            continue
        if ROUND_RE.match(t):
            return t
    return None


def iso(d):
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", d or "")
    return f"{m.group(3)}-{m.group(1)}-{m.group(2)}" if m else (d or "")


_SCORE_RE = re.compile(r"\b(\d{1,2}-\d{1,2})\b")
_TIME_RE = re.compile(r"\b(\d{1,2}:\d{2})\b")


def _score_time(res):
    """(score like '7-2' or None, real time like '3:52' or None; the 0:00 placeholder counts as no time)"""
    res = res or ""
    m, t = _SCORE_RE.search(res), _TIME_RE.search(res)
    tm = t.group(1) if t and t.group(1) != "0:00" else None
    return (m.group(1) if m else None), tm


def _placeholder_only(res):
    sc, tm = _score_time(res)
    return sc is None and tm is None


def _conflict(sc1, tm1, sc2, tm2):
    return bool((sc1 and sc2 and sc1 != sc2) or (tm1 and tm2 and tm1 != tm2))


class Row:
    __slots__ = ("owner", "entry", "idx", "date", "event", "rnd", "rtype", "owner_won", "opp", "summary", "result",
                 "acc_counted", "drop_reason", "bout", "opp_name", "opp_team", "weight")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))


class SeasonBouts:
    def __init__(self, gender, season):
        self.gender = gender
        self.season = season
        self.roster = {}                 # id -> {name, team, grade, weight, entry}
        self.bouts = []                  # canonical bouts
        self.by_wrestler = collections.defaultdict(list)   # id -> [bout index]
        self.rows = []                   # every parsed raw row (with .bout / .drop_reason)
        self.stats = collections.Counter()
        self.rematch_round_pairs = collections.Counter()

    def wrestler_bouts(self, wid):
        return [self.bouts[i] for i in self.by_wrestler.get(str(wid), [])]

    def outcome(self, bout, wid):
        return "W" if bout["winner"] == str(wid) else "L"

    def record(self, wid):
        out = collections.Counter()
        for b in self.wrestler_bouts(wid):
            if b["rtype"] not in COUNTED_TYPES:
                continue
            o = self.outcome(b, wid)
            out[o] += 1
            if b["rtype"] == "FF":
                out["ff_" + o.lower()] += 1
            if b["rtype"] == "MFF":
                out["mff_" + o.lower()] += 1
        return {"W": out["W"], "L": out["L"], "ff_w": out["ff_w"], "mff_w": out["mff_w"], "mff_l": out["mff_l"],
                "ff_l": out["ff_l"]}


def _load_overrides(gender, season, state):
    p = ROOT / "mt" / "rankings_data" / f"hs_{state}_{gender}" / str(season) / "match_overrides.json"
    removals, overrides = [], {}
    if p.exists():
        try:
            for ov in json.load(open(p, encoding="utf-8")).get("overrides", []):
                w1, w2, d = ov.get("wrestler1_id"), ov.get("wrestler2_id"), ov.get("date")
                if not (w1 and w2 and d):
                    continue
                k = (*sorted([str(w1), str(w2)]), iso(d))
                if ov.get("remove"):
                    removals.append((k, str(ov["result"]).strip() if ov.get("result") else None))
                else:
                    overrides[k] = ov
        except Exception as e:  # noqa: BLE001
            print(f"warning: could not read {p}: {e}", file=sys.stderr)
    return removals, overrides


def build_season(gender, season, state="ky", exclude_exhibitions=False, apply_overrides=True, same_round_is_one_bout=True):
    sb = SeasonBouts(gender, season)
    data_dir = ROOT / "mt" / "processed_data" / f"hs_{state}_{gender}" / str(season)
    drop = processed_drop_idents(gender, season, state=state)

    # ---- load every roster entry ("view") ----
    entries = []      # (team_name, wrestler dict, matches after dup-event drop)
    for f in sorted(data_dir.glob("*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        team = d.get("team_name", "Unknown")
        for w in d.get("roster", []):
            wid = w.get("season_wrestler_id")
            if not wid:
                continue
            ms = [m for m in w.get("matches", []) if match_ident(m, wid) not in drop]
            entries.append((team, w, ms))
    # roster: keep the entry with the most valid matches per id (first wins ties) - same choice the accomplishments script makes
    best = {}
    for ei, (team, w, ms) in enumerate(entries):
        wid = str(w["season_wrestler_id"])
        valid = sum(1 for m in ms if not (m.get("result") == "BYE" or "received a bye" in (m.get("summary") or "").lower()
                                          or m.get("result") == "NoResult"))
        if valid == 0:
            continue
        if wid not in best or valid > best[wid][0]:
            best[wid] = (valid, ei)
    for wid, (_, ei) in best.items():
        team, w, _ = entries[ei]
        sb.roster[wid] = dict(name=w.get("name", ""), team=team, grade=w.get("grade"), weight=w.get("weight_class"), entry=ei)
    id_name = {}
    for team, w, _ in entries:
        id_name.setdefault(str(w["season_wrestler_id"]), (w.get("name", ""), team))

    # ---- parse rows ----
    groups = collections.defaultdict(list)
    for ei, (team, w, ms) in enumerate(entries):
        owner = str(w["season_wrestler_id"])
        oname = norm_name(w.get("name"))
        for idx, m in enumerate(ms):
            res = m.get("result")
            rt = result_type(res)
            summ = m.get("summary") or ""
            opp = m.get("opponent_id")
            opp = str(opp) if opp not in (None, "", "None") else None
            wn, ln = norm_name(m.get("winner_name")), norm_name(m.get("loser_name"))
            won = None
            if wn == oname and ln != oname:
                won = True
            elif ln == oname and wn != oname:
                won = False
            elif wn == oname and ln == oname:
                won = (m.get("winner_team") == team)
            elif opp and opp in id_name:
                on = norm_name(id_name[opp][0])
                if wn == on:
                    won = False
                elif ln == on:
                    won = True
            acc_counted = (rt not in ("BYE", "NORESULT") and
                           ((m.get("winner_name") == w.get("name") and m.get("winner_team") == team) or
                            (m.get("loser_name") == w.get("name") and m.get("loser_team") == team)))
            acc_counted = acc_counted and (best.get(owner, (0, -1))[1] == ei)
            row = Row(owner=owner, entry=ei, idx=idx, date=iso(m.get("date")), event=m.get("event") or "",
                      rnd=parse_round(summ), rtype=rt, owner_won=won, opp=opp, summary=summ, result=res,
                      acc_counted=acc_counted, drop_reason=None, bout=None,
                      opp_name=((m.get("loser_name") if won else m.get("winner_name")) if won is not None else None),
                      opp_team=((m.get("loser_team") if won else m.get("winner_team")) if won is not None else None),
                      weight=m.get("weight"))
            sb.rows.append(row)
            sb.stats["rows"] += 1
            if rt in EXCLUDED_TYPES:
                row.drop_reason = "excluded type " + rt
                sb.stats["excluded rows: " + rt] += 1
                continue
            if exclude_exhibitions and row.rnd == "exhibition":
                row.drop_reason = "exhibition"
                sb.stats["excluded rows: exhibition"] += 1
                continue
            if won is None:
                row.drop_reason = "winner unresolved"
                sb.stats["rows where the owner's name matches neither side"] += 1
                continue
            pair = (owner, opp) if opp else ("UNK", owner, row.event.lower())
            key = (tuple(sorted(pair[:2])) if opp else pair, row.date, rt)
            groups[key].append(row)

    # ---- cluster each (pair, date, type) group into bouts ----
    # Step 1 (results): two rows are the same bout only if their results are COMPATIBLE. A conflict = both carry a score and the
    # scores differ, or both carry a real (non-0:00) time and the times differ -> different bouts, ALWAYS (TJ 2026-09-21: never
    # ignore a match whose result differs). A `0:00` placeholder is compatible with any time.
    # Step 2 (rematch by label): rows with compatible results but different round labels are ONE bout (a duplicate) unless the
    # rematch is very clear: BOTH wrestlers' files each list BOTH labels. (Known-opponent bouts only. Bouts vs an unknown opponent
    # have no second view, so distinct labels there stay separate bouts.)  Unlabeled rows attach to a labeled bout.
    for key, rows in groups.items():
        rows = sorted(rows, key=lambda r: (_placeholder_only(r.result), r.owner, r.idx))
        clusters = []          # each: {"rows": [...], "score": str|None, "time": str|None}
        for r in rows:
            sc, tm = _score_time(r.result)
            fits = [c for c in clusters if not _conflict(c["score"], c["time"], sc, tm)]
            if fits:
                same_label = [c for c in fits if any(x.rnd == r.rnd for x in c["rows"])]
                c = (same_label or fits)[0] if (same_label or len(fits) == 1) else max(fits, key=lambda c: len(c["rows"]))
            else:
                c = {"rows": [], "score": None, "time": None}
                clusters.append(c)
                if len(clusters) > 1:
                    sb.stats["result-conflict clusters (before merging one-sided versions)"] += 1
            c["rows"].append(r)
            c["score"] = c["score"] or sc
            c["time"] = c["time"] or tm
        clusters = [c["rows"] for c in clusters]
        if same_round_is_one_bout and len(clusters) > 1 and key[0][0] != "UNK":
            # OPTION (off by default): a wrestler can't wrestle the same round of one event twice, so two conflicting rows carrying the SAME
            # round label are one bout with a data variance (e.g. Fall 2:34 vs Fall 2:33, TF 21-6 vs TF 22-6), not two bouts.
            lab = [{r.rnd for r in c if r.rnd} for c in clusters]
            pr = list(range(len(clusters)))

            def f3(i):
                while pr[i] != i:
                    pr[i] = pr[pr[i]]
                    i = pr[i]
                return i
            for i in range(len(clusters)):
                for j in range(i + 1, len(clusters)):
                    if lab[i] & lab[j] and f3(i) != f3(j):
                        pr[f3(j)] = f3(i)
                        sb.stats["same round label, different result: merged into one bout (option)"] += 1
            mg3 = collections.OrderedDict()
            for i, c in enumerate(clusters):
                mg3.setdefault(f3(i), []).extend(c)
            clusters = list(mg3.values())
        if len(clusters) > 1 and key[0][0] != "UNK":
            # Conflicting versions that NO wrestler's own file lists together (A's file has one score, B's file another) are one bout the two
            # sides recorded differently, not two bouts: each wrestler only ever sees one of them. Counted once (flagged in the stats).
            own = [{r.owner for r in c} for c in clusters]
            par = list(range(len(clusters)))

            def f2(i):
                while par[i] != i:
                    par[i] = par[par[i]]
                    i = par[i]
                return i
            for i in range(len(clusters)):
                for j in range(i + 1, len(clusters)):
                    if not (own[i] & own[j]) and f2(i) != f2(j):
                        par[f2(j)] = f2(i)
                        sb.stats["bouts where the two wrestlers' files record different results (counted once)"] += 1
            mg = collections.OrderedDict()
            for i, c in enumerate(clusters):
                mg.setdefault(f2(i), []).extend(c)
            clusters = list(mg.values())

        out = []
        for cl in clusters:
            labeled, unl = collections.OrderedDict(), []
            for r in cl:
                (labeled.setdefault(r.rnd, []).append(r) if r.rnd else unl.append(r))
            subs = list(labeled.values()) if labeled else [unl]
            if labeled and unl:
                subs[0].extend(unl)
                sb.stats["unlabeled rows folded into a labeled bout"] += len(unl)
            if len(subs) > 1 and key[0][0] != "UNK":
                parent = list(range(len(subs)))

                def find(i):
                    while parent[i] != i:
                        parent[i] = parent[parent[i]]
                        i = parent[i]
                    return i
                owners = [{r.owner for r in c} for c in subs]
                for i in range(len(subs)):
                    for j in range(i + 1, len(subs)):
                        if not (len(owners[i]) == 2 and len(owners[j]) == 2):      # not clearly listed by both wrestlers
                            x, y = find(i), find(j)
                            if x != y:
                                parent[y] = x
                                sb.stats["different round labels folded into one bout (rematch not clear)"] += 1
                merged = collections.OrderedDict()
                for i, c in enumerate(subs):
                    merged.setdefault(find(i), []).extend(c)
                subs = list(merged.values())
            out.extend(subs)
        clusters = out
        rematch = len(clusters) > 1 and key[0][0] != "UNK"   # unknown-opponent bouts in different rounds are different opponents, not a rematch
        if rematch:
            sb.stats["same-day rematch groups (distinct round labels)"] += 1
            sb.rematch_round_pairs[" | ".join(sorted({r.rnd or "-" for c in clusters for r in c}))] += 1
        for cl in clusters:
            owners = {r.owner for r in cl}
            # winner: each row says who won
            winners = collections.Counter()
            for r in cl:
                winners[(r.owner if r.owner_won else r.opp) or "UNK"] += 1
            winner = winners.most_common(1)[0][0]
            if len([k for k in winners if k != "UNK"]) > 1:
                sb.stats["bouts whose rows disagree on the winner"] += 1
            real = [r for r in cl if " 0:00" not in (r.result or "")] or cl
            head = real[0]
            pair_ids = [x for x in (key[0] if key[0][0] != "UNK" else (key[0][1],)) if x]
            opp_of = {}
            for a in pair_ids:
                others = [b for b in pair_ids if b != a]
                opp_of[a] = others[0] if others else None
            bout = dict(idx=len(sb.bouts), date=head.date, event=head.event, round=head.rnd, rtype=key[2], result=head.result,
                        ids=pair_ids, winner=winner, rows=cl, rematch=rematch, override=None,
                        owners=sorted(owners), n_rows=len(cl), unknown_opp=key[0][0] == "UNK",
                        weight=head.weight, opp_name=head.opp_name, opp_team=head.opp_team,
                        summaries={r.summary for r in cl})
            sb.bouts.append(bout)
            for r in cl:
                r.bout = bout["idx"]

    # ---- match overrides (same keys/semantics as load_data.py) ----
    if apply_overrides:
        removals, overrides = _load_overrides(gender, season, state)
        for b in sb.bouts:
            if len(b["ids"]) != 2 or b["rtype"] in EXCLUDED_TYPES:
                continue
            k = (*sorted(b["ids"]), b["date"])
            for rk, rres in removals:
                if rk == k and (rres is None or any((r.result or "").strip() == rres for r in b["rows"])):
                    b["rtype"] = "NORESULT"
                    b["override"] = "removed"
                    sb.stats["bouts removed by match_overrides"] += 1
            ov = overrides.get(k)
            if ov and b["override"] is None:
                b["winner"] = str(ov.get("winner_id", b["winner"]))
                if ov.get("result"):
                    b["result"] = ov["result"]
                    b["rtype"] = result_type(ov["result"])
                if ov.get("event"):
                    b["event_override"] = ov["event"]       # load_data also lets an override rename the event
                b["override"] = "result/winner"
                sb.stats["bouts changed by match_overrides"] += 1
    for b in sb.bouts:
        if b["rtype"] in EXCLUDED_TYPES:
            for r in b["rows"]:
                r.drop_reason = r.drop_reason or ("override: " + (b["override"] or "excluded"))
            continue
        for wid in b["ids"]:
            sb.by_wrestler[wid].append(b["idx"])
    sb.stats["canonical bouts"] = sum(1 for b in sb.bouts if b["rtype"] in COUNTED_TYPES)
    return sb


# ---------------------------------------------------------------------------------------------------------------------------------------
# Adapter for the profile builder: canonical bouts -> the "match dict" shape that weight_class_*.json uses
# ({date MM/DD/YYYY, weight_class, wrestler1_id < wrestler2_id, winner_id, result, event}) so build_wrestler_profiles.py's existing
# record / bonus / best-win / match_list code runs unchanged on the canonical list.
# ---------------------------------------------------------------------------------------------------------------------------------------
import hashlib  # noqa: E402


def synthetic_opponent_id(name, team):
    """Same id load_data.create_synthetic_opponent_id() gives an out-of-state / unidentified opponent (md5 of 'name|team')."""
    key = f"{name}|{team}".lower().strip()
    return "OUTSTATE_" + hashlib.md5(key.encode("utf-8")).hexdigest()[:12]


def _team_from_event(event):
    m = re.search(r"vs\.?\s+([^(]+)", event or "", re.IGNORECASE)
    return m.group(1).strip() if m else None


def _event_for(sb, bout, wid):
    """Event label from `wid`'s own point of view. Dual-meet events read "vs. <the other team>" in EACH wrestler's own file, so a bout
    that only the opponent's file lists carries the opponent's label ("vs. <wid's team>") -- flip it to "vs. <opponent's team>"."""
    if bout.get("event_override"):
        return bout["event_override"]
    own = [r for r in bout["rows"] if r.owner == wid]
    if own:
        return (own[0]).event
    ev = bout["event"] or ""
    if re.match(r"^\s*vs\.?\s", ev, re.IGNORECASE):
        other = bout["rows"][0].owner if bout["rows"] else None
        team = sb.roster.get(other, {}).get("team") if other else None
        if team:
            return f"vs. {team}"
    return ev


def matches_by_wrestler(sb, weight_of=None):
    """({wrestler_id: [match dict, ...]}, {synthetic_id: {"name","team"}}) for every COUNTED canonical bout.
    weight_of(bout) -> weight-class string or None (the caller supplies the ranking files' weight for a known pair; the raw row weight is the fallback)."""
    out = collections.defaultdict(list)
    synth = {}
    for b in sb.bouts:
        if b["rtype"] not in COUNTED_TYPES:
            continue
        y, mo, d = (b["date"] or "").split("-") if re.match(r"^\d{4}-\d{2}-\d{2}$", b["date"] or "") else (None, None, None)
        date = f"{mo}/{d}/{y}" if y else b["date"]
        wc = (weight_of(b) if weight_of else None) or b.get("weight")
        if len(b["ids"]) == 2:
            a, c = sorted(b["ids"])
            for wid in (a, c):
                out[wid].append(dict(date=date, weight_class=wc, wrestler1_id=a, wrestler2_id=c, winner_id=b["winner"], result=b["result"],
                                     event=_event_for(sb, b, wid)))
        else:
            owner = b["ids"][0]
            name = b.get("opp_name") or "Unknown"
            team = b.get("opp_team")
            if b["rtype"] in ("FF", "MFF") and (not team or team == "Unknown"):
                team = _team_from_event(b["event"]) or team
            team = team or "Unknown"
            sid = synthetic_opponent_id(name, team)
            synth[sid] = {"name": name, "team": team}
            a, c = sorted([owner, sid])
            winner = owner if b["winner"] == owner else sid
            out[owner].append(dict(date=date, weight_class=wc, wrestler1_id=a, wrestler2_id=c, winner_id=winner, result=b["result"],
                                   event=_event_for(sb, b, owner)))
    return out, synth


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gender", choices=["boys", "girls"])
    ap.add_argument("season", type=int)
    ap.add_argument("wrestler_id", nargs="?")
    a = ap.parse_args()
    s = build_season(a.gender, a.season)
    print(dict(s.stats))
    if a.wrestler_id:
        print(a.wrestler_id, s.roster.get(a.wrestler_id, {}).get("name"), s.record(a.wrestler_id))
        for b in sorted(s.wrestler_bouts(a.wrestler_id), key=lambda b: b["date"]):
            print(" ", b["date"], (b["round"] or "-").ljust(18), b["rtype"].ljust(5), "W" if b["winner"] == a.wrestler_id else "L",
                  b["result"], "| rows", b["n_rows"], "| rematch" if b["rematch"] else "")
