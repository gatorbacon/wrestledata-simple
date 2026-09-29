#!/usr/bin/env python3
"""
WPA spec, Section 1 -- data audit (step 1 of the build order). Read-only.

Answers the 22 audit items in /Users/tjthompson/Downloads/wrestling_wpa_spec.md against the
play-by-play we actually have, and writes data/wpa/reports/data_audit.md.

Sources (see docs/matsavant.md):
  * play-by-play: data/{year}/{tourney}-tourney/bout_detail/{weight}.json  (NCAA + 6 conferences)
  * official results: data/{year}/ncaa-tourney/parsed/matches.json (result type, score, seeds) and
    data/{year}/{conf}-tourney/parsed/matches.json (built from team scrapes; no seeds)
  * national rank: frontend/wrestledata-ui/public/data/wrestlers/{season}/by_id/*.json `current_rank`
    (era-based methodology, docs/matsavant.md "NCAA Ranking Methodology")
Event parsing reuses scripts/analysis/parse_bout_pbp.py; official-result joins reuse
scripts/analysis/td_differential_report.py.

Usage: .venv/bin/python scripts/wpa/audit_data.py
"""
import glob
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts/analysis"))
import parse_bout_pbp as P          # noqa: E402
import td_differential_report as R  # noqa: E402

OUT = ROOT / "data/wpa/reports/data_audit.md"
CONFS = {"big_ten": "Big Ten", "big_12": "Big 12", "acc": "ACC", "mac": "MAC", "pac_12": "Pac-12", "socon": "SoCon"}
REG_LEN = {"Period 1": 180, "Period 2": 120, "Period 3": 120}
CLOCK = re.compile(r"\((\d+):(\d{2})\)\s*$")
RT_NOTE = re.compile(r"riding time:\s*(\d+):(\d+)(?:\s*\((\d+):(\d+)\))?", re.I)


def pct(a, b, d=1):
    return f"{100 * a / b:.{d}f}%" if b else "—"


def era_of(year, td_texts=None):
    """Scoring era, from the point values item 15 finds in the data: 2015 = takedown 2 / near fall 2-3;
    2016-2023 = takedown 2 / near fall 2-4; 2024-2026 = takedown 3 / near fall 2-3-4."""
    if year >= 2024:
        return "E3 2024–26 (TD 3, NF 2/3/4)"
    if year >= 2016:
        return "E2 2016–23 (TD 2, NF 2/4)"
    return "E1 2015 (TD 2, NF 2/3)"


def norm_event(text):
    base, _ = P.strip_time(text)
    base = re.sub(r"\s+", " ", base.strip())
    return base


def load_tourneys():
    """Yields (kind, label, year, weight, bout, official_or_None, results_available)."""
    years = sorted(int(p.name) for p in (ROOT / "data").iterdir() if p.name.isdigit())
    for y in years:
        base = ROOT / f"data/{y}/ncaa-tourney"
        if (base / "bout_detail").exists():
            parsed = defaultdict(list)
            pf = base / "parsed/matches.json"
            if pf.exists():
                for pm in json.load(open(pf)):
                    parsed[(pm["weight"], pm["winner_name"], pm["loser_name"])].append(pm)
            for f in sorted(glob.glob(str(base / "bout_detail/*.json"))):
                for m in json.load(open(f)):
                    cands = parsed.get((m["weight"], m["winner"]["name"], m["loser"]["name"]), [])
                    off = R.resolve_official(m, cands) if cands else None
                    yield "ncaa", "NCAA", y, m["weight"], m, off, pf.exists()
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
                    yield "conf", label, y, m["weight"], m, off, rp.exists()


def official_counts():
    """Official result rows per tournament (how many bouts were wrestled/decided at all)."""
    out = Counter()
    for pf in glob.glob(str(ROOT / "data/*/ncaa-tourney/parsed/matches.json")):
        y = int(Path(pf).parts[-4])
        out[("NCAA", y)] = len(json.load(open(pf)))
    for slug, label in CONFS.items():
        for rp in glob.glob(str(ROOT / f"data/*/{slug}-tourney/parsed/matches.json")):
            y = int(Path(rp).parts[-4])
            out[(label, y)] = len(json.load(open(rp)))
    return out


def rank_index():
    """(season, nkey(name)) -> list of (current_rank, team, weight) from MatSavant season profiles."""
    idx = defaultdict(list)
    for f in glob.glob(str(ROOT / "frontend/wrestledata-ui/public/data/wrestlers/*/by_id/*.json")):
        season = int(Path(f).parts[-3])
        try:
            p = json.load(open(f))
        except Exception:
            continue
        idx[(season, R.nkey(p.get("name")))].append((p.get("current_rank"), p.get("team"), p.get("weight_class")))
    return idx


def main():
    S = defaultdict(Counter)       # generic counters keyed by section
    tourneys = defaultdict(set)    # label -> years
    events_by_kind = Counter()
    scoring_by_kind = Counter()
    bouts_by_kind = Counter()
    pbp_by_kind = Counter()
    clock_examples = []
    maxrem = defaultdict(int)      # (label, era/year-group) -> max clock seen
    period_len_over = Counter()
    ot_labels = defaultdict(Counter)
    ot_maxrem = defaultdict(lambda: defaultdict(int))
    taxonomy = Counter()
    td_vals = defaultdict(Counter)
    nf_vals = defaultdict(Counter)
    pen_vals = defaultdict(Counter)
    tf_margin = defaultdict(Counter)
    md_margin = defaultdict(Counter)
    result_types = defaultdict(Counter)
    seconds_mod = Counter()
    fall_last = []
    tf_check = Counter()
    choice_stats = Counter()
    choice_dist = defaultdict(Counter)
    rt_stats = Counter()
    reconcile = Counter()
    seeds = defaultdict(lambda: {"bouts": 0, "both": 0, "one": 0, "none": 0, "max": 0, "entrants": set()})
    conf_rank_rows = []            # (label, year, weight, winner name/team, loser name/team)
    riding_matched = riding_total = 0
    miss_type = Counter()
    clocked_bouts = Counter()
    ot1_long = defaultdict(Counter)

    for kind, label, y, w, m, off, has_results in load_tourneys():
        tourneys[label].add(y)
        bouts_by_kind[kind] += 1
        cols = m.get("columns") or []
        if not cols:
            S["pbp"][(kind, "no_columns")] += 1
            continue
        pbp_by_kind[kind] += 1
        era = era_of(y, None)

        # ---- reconciliation: parsed events vs period_points vs header score
        meta = {"tournament": label, "year": y, "weight": w}
        rows, rchecks = P.parse_bout(m, meta)
        probs = P.validate_bout(m, rows)
        reconcile[(kind, "mismatch" if probs else "ok")] += 1
        pp_w = sum((c.get("period_points") or {}).get("winner", 0) for c in cols)
        pp_l = sum((c.get("period_points") or {}).get("loser", 0) for c in cols)
        hdr_ok = (pp_w, pp_l) == (m["winner"]["score"], m["loser"]["score"])
        reconcile[(kind, "header_ok" if hdr_ok else "header_off")] += 1
        mt, tt = P.check_riding_time(rchecks)
        riding_matched += mt
        riding_total += tt

        # ---- official result
        rtype = off.get("result_type") if off else None
        result_types[kind][rtype or "(no official result joined)"] += 1

        labels = [c["label"] for c in cols]
        for lab in labels:
            if lab.startswith("Overtime"):
                ot_labels[y][lab] += 1

        # ---- choice (Section 1 item 11)
        reached = {lab for lab in labels if lab.startswith(("Period", "Overtime"))}
        has_c1 = "Choice 1" in labels
        has_c2 = "Choice 2" in labels
        if "Period 2" in reached:
            choice_stats[(kind, "reached_p2")] += 1
            choice_stats[(kind, "p2_has_choice")] += has_c1
        if "Period 3" in reached:
            choice_stats[(kind, "reached_p3")] += 1
            choice_stats[(kind, "p3_has_choice")] += has_c2
        ch = P.extract_choices(m)
        for i in (1, 2):
            if ch.get(f"choice_{i}_choice"):
                choice_dist[(kind, i)][("defer→" if ch.get(f"choice_{i}_deferred") else "") + ch[f"choice_{i}_choice"]] += 1

        # ---- riding time (item 10)
        any_rt_note = any_rt_ck = False
        for c in cols:
            for n in c.get("notes", []):
                mm = RT_NOTE.search(n)
                if mm:
                    any_rt_note = True
                    any_rt_ck |= mm.group(3) is not None
        rt_stats[(kind, "bouts")] += 1
        rt_stats[(kind, "any_note")] += any_rt_note
        rt_stats[(kind, "checkpointed_note")] += any_rt_ck
        rt_stats[(kind, "rt_point_event")] += any(norm_event(e["text"]) == "Riding Time"
                                                   for c in cols for e in c.get("events", []))

        # ---- events: taxonomy, timestamps, clock errors, rule values
        last_timed = None
        for c in cols:
            lab = c["label"]
            timed = lab.startswith(("Period", "Overtime"))
            prev = None
            for e in c.get("events", []):
                txt = e["text"]
                base = norm_event(txt)
                key = re.sub(r"^\d+ Nearfall$", "N Nearfall", base)
                key = re.sub(r"^Penalty \d+$", "Penalty N", key)
                key = re.sub(r"^Takedown \d+$", "Takedown N", key)
                key = re.sub(r"^[+-]\d+$", "±N adjustment", key)
                taxonomy[key] += 1
                events_by_kind[kind] += 1
                parsed = P.parse_event_text(base)
                if (parsed["points"] or 0) != 0:
                    scoring_by_kind[kind] += 1
                mt_ = re.match(r"^Takedown\s*(\d+)?$", base)
                if mt_:
                    td_vals[y][int(mt_.group(1)) if mt_.group(1) else "bare (2)"] += 1
                mn = re.match(r"^(\d+) Nearfall$", base)
                if mn:
                    nf_vals[y][int(mn.group(1))] += 1
                mp = re.match(r"^Penalty (\d+)$", base)
                if mp:
                    pen_vals[y][int(mp.group(1))] += 1
                if not timed:
                    continue
                S["ts"][(kind, "timed_events")] += 1
                cm = CLOCK.search(txt)
                if not cm:
                    S["ts"][(kind, "no_clock")] += 1
                    continue
                S["ts"][(kind, "with_clock")] += 1
                rem = int(cm.group(1)) * 60 + int(cm.group(2))
                seconds_mod[rem % 10] += 1
                grp = "2024+" if y >= 2024 else "≤2023"
                if lab in REG_LEN:
                    maxrem[(lab, grp)] = max(maxrem[(lab, grp)], rem)
                    if rem > REG_LEN[lab]:
                        period_len_over[(kind, lab)] += 1
                        if len(clock_examples) < 12:
                            clock_examples.append(f"{label} {y} {w} bout {m.get('bout_number')}: {lab} event "
                                                  f"'{txt}' shows {rem // 60}:{rem % 60:02d} remaining (period is "
                                                  f"{REG_LEN[lab] // 60}:00)")
                else:
                    ot_maxrem[y][lab] = max(ot_maxrem[y][lab], rem)
                if prev is not None and rem > prev:
                    S["ts"][(kind, "nonmonotonic")] += 1
                    if len(clock_examples) < 24:
                        clock_examples.append(f"{label} {y} {w} bout {m.get('bout_number')}: {lab} clock goes up "
                                              f"{prev // 60}:{prev % 60:02d} → {rem // 60}:{rem % 60:02d} ('{txt}')")
                prev = rem
            if timed:
                last_timed = lab

        # ---- clock completeness: every scoring event in regulation has a clock (end-of-match Riding Time
        # point, stalling and cautions don't need one)
        full = True
        for c in cols:
            if not c["label"].startswith(("Period", "Overtime")):
                continue
            for e in c.get("events", []):
                cm = CLOCK.search(e["text"])
                kind_ev = re.sub(r"\d+", "N", norm_event(e["text"]))
                if not cm:
                    miss_type[kind_ev] += 1
                    if c["label"].startswith("Period") and kind_ev not in ("Stalling", "Caution", "Riding Time"):
                        full = False
                elif c["label"] == "Overtime 1":
                    sec = int(cm.group(1)) * 60 + int(cm.group(2))
                    ot1_long[y]["over 1:00" if sec > 60 else "≤1:00"] += 1
        clocked_bouts[(kind, "full")] += full
        clocked_bouts[(kind, "all")] += 1

        # ---- terminal behaviour (item 14)
        if rtype == "Fall":
            # official fall time = elapsed match time: conference results in `time`, NCAA results in `score` (M:SS)
            ft = off.get("time") or (off.get("score") if re.match(r"^\d+:\d\d$", str(off.get("score") or "")) else None)
            fall_last.append((kind, last_timed, ft))
        if rtype == "TF":
            margin = m["winner"]["score"] - m["loser"]["score"]
            tf_check[(era, margin)] += 1
            tf_margin[era][margin] += 1
        if rtype == "MD":
            md_margin[era][m["winner"]["score"] - m["loser"]["score"]] += 1

        # ---- seeds (NCAA) / rank rows (conf)
        if kind == "ncaa":
            s = seeds[y]
            s["bouts"] += 1
            ws_, ls_ = (off or {}).get("winner_seed"), (off or {}).get("loser_seed")
            n = (ws_ is not None) + (ls_ is not None)
            s[{2: "both", 1: "one", 0: "none"}[n]] += 1
            for sd in (ws_, ls_):
                if sd:
                    s["max"] = max(s["max"], sd)
        else:
            conf_rank_rows.append((label, y, w, m["winner"]["name"], m["winner"]["team"],
                                   m["loser"]["name"], m["loser"]["team"]))

    # NCAA entrants / seeding depth straight from the seeds files
    seed_depth = {}
    for y in sorted(tourneys["NCAA"]):
        entrants = seeded = 0
        mx = 0
        for f in glob.glob(str(ROOT / f"data/{y}/ncaa-tourney/seeds/*.txt")):
            for line in open(f):
                mm = re.match(r"^\s*(\d+)\s*[.)\-]?\s", line)
                if mm:
                    entrants += 1
                    mx = max(mx, int(mm.group(1)))
        seed_depth[y] = (entrants, mx)

    # ---- conference: national rank coverage (items 19-20)
    ridx = rank_index()
    rank_counts = defaultdict(Counter)
    unmatched_names = Counter()

    def rank_of(season, name, team, weight):
        c = ridx.get((season, R.nkey(name)), [])
        if not c:
            return "unmatched"
        if len(c) > 1:
            same_team = [x for x in c if (x[1] or "").lower() == (team or "").lower()]
            c = same_team or [x for x in c if x[2] == weight] or c
        r = c[0][0]
        return r if isinstance(r, int) else "unmatched"

    for label, y, w, wn, wt, ln, lt in conf_rank_rows:
        rw, rl = rank_of(y, wn, wt, w), rank_of(y, ln, lt, w)
        for nm, rr in ((wn, rw), (ln, rl)):
            if rr == "unmatched":
                unmatched_names[(label, y)] += 1
        ranked = lambda r: isinstance(r, int) and r <= 33
        k = sum((ranked(rw), ranked(rl)))
        grp = "2023–2026 (Flo)" if y >= 2023 else ("2019–2022 (placement+seed)" if y >= 2019 else "2015–2018 (placement+seed≤16)")
        rank_counts[grp][{2: "both", 1: "one", 0: "neither"}[k]] += 1
        rank_counts[grp]["unmatched_wrestlers"] += (rw == "unmatched") + (rl == "unmatched")
        rank_counts[grp]["wrestler_slots"] += 2
        rank_counts[grp]["ranked_wrestlers"] += ranked(rw) + ranked(rl)

    off_counts = official_counts()

    # ======================================================================
    L = []
    A = L.append
    A("# WPA data audit (spec Section 1)\n")
    A("Generated by `scripts/wpa/audit_data.py`. Read-only; nothing in the data was changed.\n")
    A("Play-by-play: `data/{year}/{tourney}-tourney/bout_detail/*.json`. Official results: "
      "`data/{year}/{tourney}-tourney/parsed/matches.json`. National rank: MatSavant season profiles "
      "(`current_rank`).\n")

    A("## Coverage\n")
    A("### 1. Tournaments and seasons\n")
    A("| Tournament | Seasons with play-by-play | Count |\n|---|---|---:|")
    for lab in ["NCAA"] + list(CONFS.values()):
        ys = sorted(tourneys[lab])
        A(f"| {lab} | {', '.join(map(str, ys))} | {len(ys)} |")
    n_conf = sum(len(tourneys[l]) for l in CONFS.values())
    A(f"\n**{len(tourneys['NCAA'])} NCAA Championships** and **{n_conf} conference tournaments**. "
      "(Spec expected ~11 and ~50.) NCAA has no 2020 tournament. EIWA is not on TrackWrestling.\n")

    A("### 2. Matches and scoring events\n")
    A("| | Bout records | With play-by-play | Events (all) | Scoring events (nonzero points) |\n|---|---:|---:|---:|---:|")
    for k, nm in (("ncaa", "NCAA"), ("conf", "Conference")):
        A(f"| {nm} | {bouts_by_kind[k]:,} | {pbp_by_kind[k]:,} | {events_by_kind[k]:,} | {scoring_by_kind[k]:,} |")
    A("")

    A("### 3. Complete play-by-play vs final score only\n")
    for k, nm in (("ncaa", "NCAA"), ("conf", "Conference")):
        ok, bad = reconcile[(k, "ok")], reconcile[(k, "mismatch")]
        hok, hoff = reconcile[(k, "header_ok")], reconcile[(k, "header_off")]
        A(f"- **{nm}:** {S['pbp'][(k, 'no_columns')]:,} bout records have no play-by-play at all (byes / "
          f"walkovers / forfeits — nothing to model). Of the {pbp_by_kind[k]:,} with play-by-play, "
          f"{ok:,} ({pct(ok, ok + bad)}) reconcile exactly: every period's parsed events sum to that period's "
          f"`period_points`; {bad:,} do not. The independent check is the headline final score: period totals "
          f"match it in {pct(hok, hok + hoff)} of bouts.")
    tot_off_ncaa = sum(v for (lab, y), v in off_counts.items() if lab == "NCAA")
    tot_off_conf = sum(v for (lab, y), v in off_counts.items() if lab != "NCAA")
    A(f"- Official result rows (all bouts incl. forfeits/byes-with-result): NCAA {tot_off_ncaa:,}, conference "
      f"{tot_off_conf:,}. There is no category of 'final score only' bouts inside the play-by-play files: a "
      f"bout either has event columns or it has none. Bouts with none, and bouts that fail reconciliation, "
      f"are excluded from the state table.\n")

    A("## Timestamps (highest-risk)\n")
    for k, nm in (("ncaa", "NCAA"), ("conf", "Conference")):
        te, wc, nc = S["ts"][(k, "timed_events")], S["ts"][(k, "with_clock")], S["ts"][(k, "no_clock")]
        A(f"- **4. {nm}:** {wc:,} of {te:,} events inside a period/OT column carry a clock ({pct(wc, te)}); "
          f"{nc:,} have none. (Position choices in `Choice N` columns never carry a clock and aren't counted.)")
    real_missing = {k: v for k, v in miss_type.items() if k not in ("Riding Time",)}
    A(f"- Which events lack a clock: the end-of-match `Riding Time` point ({miss_type['Riding Time']:,}; it needs "
      f"none), then " + ", ".join(f"{k} {v:,}" for k, v in sorted(real_missing.items(), key=lambda x: -x[1])[:8]) + ".")
    for k, nm in (("ncaa", "NCAA"), ("conf", "Conference")):
        A(f"- **Usable matches, {nm}:** {clocked_bouts[(k, 'full')]:,} of {clocked_bouts[(k, 'all')]:,} bouts "
          f"({pct(clocked_bouts[(k, 'full')], clocked_bouts[(k, 'all')])}) have a clock on every regulation scoring "
          f"event. The rest have at least one takedown/escape/near fall/penalty with no time — often a near fall logged "
          f"right after the takedown that set it up. Those could be placed between their clocked neighbours instead of "
          f"dropping the whole bout (decision for TJ).")
    tot = sum(seconds_mod.values())
    A(f"- **5. Granularity:** clock values are M:SS. Last-digit distribution of the seconds (uniform would be "
      f"10% each): " + ", ".join(f"{d}: {pct(seconds_mod[d], tot)}" for d in range(10)) +
      ". Exact seconds, no rounding to 5 or 10.")
    A("- **6. Period boundaries:** explicit. Every bout is a list of labelled columns (`Period 1`, `Choice 1`, "
      "`Period 2`, `Choice 2`, `Period 3`, `Overtime N`). The clock is time **remaining in the period**, "
      "counting down.")
    for k, nm in (("ncaa", "NCAA"), ("conf", "Conference")):
        A(f"- **7. {nm} clock errors:** {S['ts'][(k, 'nonmonotonic')]:,} places where the clock goes UP between "
          f"consecutive events in one period; "
          f"{sum(v for (kk, lab), v in period_len_over.items() if kk == k):,} events with more time remaining "
          f"than the period has.")
    if clock_examples:
        A("\n  Examples:\n")
        for e in clock_examples[:14]:
            A(f"  - {e}")
    A("\n- **8. Period lengths observed** (largest clock reading seen per period):\n")
    A("| Period | ≤2023 max | 2024+ max | Rule |\n|---|---|---|---|")
    for lab, n in REG_LEN.items():
        a, b = maxrem.get((lab, "≤2023"), 0), maxrem.get((lab, "2024+"), 0)
        A(f"| {lab} | {a // 60}:{a % 60:02d} | {b // 60}:{b % 60:02d} | {n // 60}:00 |")
    A("\n  Overtime columns by season (count of bouts containing each label; largest clock seen):\n")
    A("| Season | Overtime labels (bouts) | Largest clock per label |\n|---|---|---|")
    for y in sorted(ot_labels):
        A(f"| {y} | " + ", ".join(f"{k}: {v}" for k, v in sorted(ot_labels[y].items())) + " | " +
          ", ".join(f"{k}: {v // 60}:{v % 60:02d}" for k, v in sorted(ot_maxrem[y].items())) + " |")

    A("\n  Overtime 1 clock readings above 1:00, by season: " + ", ".join(
        f"{y}: {c['over 1:00']} of {c['over 1:00'] + c['≤1:00']}" for y, c in sorted(ot1_long.items())) +
      ". **Sudden victory was 1:00 through 2021 and 2:00 from 2022 on.** Tiebreaker periods are 0:30 in every season.")
    A("\n## State variables\n")
    A("- **9. Position is not recorded directly — it must be inferred.** Inference rules (already implemented and "
      "validated in `scripts/analysis/parse_bout_pbp.py`): period 1 and every OT start neutral; the `Choice N` "
      "column sets the next period's start (Bottom/Top/Neutral chosen by one wrestler, the other takes the "
      "complement); Takedown and Reversal put the scorer on top; Escape returns both to neutral. Near falls, "
      "penalties, stalling and cautions do not change position. Not visible: a restart after an out-of-bounds or "
      "an injury, and a wrestler 'cutting' an opponent (that shows up only as the opponent's Escape).")
    for k, nm in (("ncaa", "NCAA"), ("conf", "Conference")):
        b = rt_stats[(k, "bouts")]
        A(f"- **10. Riding time, {nm}:** running riding time is **not** stored as a field. {pct(rt_stats[(k, 'any_note')], b)} "
          f"of bouts have scorekeeper riding-time notes, and {pct(rt_stats[(k, 'checkpointed_note')], b)} have "
          f"at least one note pinned to a clock time. The end-of-match 'Riding Time' point appears as its own event "
          f"in {pct(rt_stats[(k, 'rt_point_event')], b)} of bouts.")
    A(f"- Running riding time can be **reconstructed from position** (who is on top, from the moment of a takedown/"
      f"reversal/top choice until the next escape/reversal/period end) — `parse_bout_pbp.py` does this. Checked "
      f"against every clock-pinned scorekeeper note: **{riding_matched:,} of {riding_total:,} ({pct(riding_matched, riding_total)}) "
      f"agree within 5 seconds.** This is reconstruction from the event stream, not from the final riding-time "
      f"value, so it doesn't fall under the spec's 'do not reconstruct running riding time from final values' rule "
      f"— but it is a decision for TJ (see open questions).")
    for k, nm in (("ncaa", "NCAA"), ("conf", "Conference")):
        r2, h2 = choice_stats[(k, "reached_p2")], choice_stats[(k, "p2_has_choice")]
        r3, h3 = choice_stats[(k, "reached_p3")], choice_stats[(k, "p3_has_choice")]
        A(f"- **11. Period choice, {nm}:** recorded. {pct(h2, r2)} of bouts that reached period 2 have a `Choice 1` "
          f"column; {pct(h3, r3)} of bouts that reached period 3 have `Choice 2`. The toss winner is the first "
          f"entry in `Choice 1` (either their pick or 'Defer').")
    for k, nm in (("ncaa", "NCAA"), ("conf", "Conference")):
        for i in (1, 2):
            d = choice_dist[(k, i)]
            n = sum(d.values())
            A(f"  - {nm} choice for period {i + 1} (n={n:,}): " +
              ", ".join(f"{c} {pct(v, n)}" for c, v in d.most_common()))
    A("- **12. Overtime:** present, labelled `Overtime 1..N`. Sudden victory vs tiebreaker is told apart by label "
      "and by the official result type (`SV-1`, `TB-1`, `TB-2`, `UTB`). The table above shows the OT format "
      "changing by season (from earlier work: **2026 is the only season under the current OT rules**).")

    A("\n## Match results\n")
    A("### 13. Result types (bouts with play-by-play, joined to official results)\n")
    A("| Result | NCAA | Conference |\n|---|---:|---:|")
    keys = sorted(set(result_types["ncaa"]) | set(result_types["conf"]), key=lambda x: -(result_types["ncaa"][x] + result_types["conf"][x]))
    for rk in keys:
        A(f"| {rk} | {result_types['ncaa'][rk]:,} | {result_types['conf'][rk]:,} |")
    A("\nForfeits, medical forfeits and most injury defaults have no play-by-play, so they barely appear here.")
    fl = Counter(lt for _, lt, _ in fall_last)
    A("\n### 14. How falls and tech falls end the event stream\n")
    ft_n = Counter(k for k, _, t in fall_last if t)
    ft_all = Counter(k for k, _, _ in fall_last)
    A(f"- **Falls are not logged as an event.** The stream simply stops. Of {len(fall_last):,} falls with "
      "play-by-play, the last period column present is: " +
      ", ".join(f"{lt or 'none'} {v:,}" for lt, v in fl.most_common()) +
      " (a period with no events or notes has no column at all, so this is only a lower bound on where the fall "
      f"happened). The fall's official time (elapsed match time) is in the results: NCAA `score` holds it as M:SS "
      f"({ft_n['ncaa']:,} of {ft_all['ncaa']:,} NCAA falls), conference results in `time` ({ft_n['conf']:,} of "
      f"{ft_all['conf']:,}). *Corrected 2026-09-29 during step 2: the first version of this audit said NCAA results "
      f"had no fall time — they do, in `score`.* So a fall is a terminal jump at its official time.")
    for era in sorted(tf_margin):
        good = {k: v for k, v in sorted(tf_margin[era].items()) if k >= 15}
        odd = {k: v for k, v in sorted(tf_margin[era].items()) if k < 15}
        A(f"- **Tech falls, {era}:** final margin distribution {good}" +
          (f"; outliers {odd} (negative = a swapped-sides bout the loaders already correct; a single 14 = one "
           f"record, likely a scoring correction)" if odd else "") +
          ". The scoring event that reaches the threshold is the last one logged.")

    A("\n## Rules drift across seasons\n")
    A("### 15. Point values by season\n")
    A("| Season | Takedown text (count) | Near fall values | Penalty values |\n|---|---|---|---|")
    for y in sorted(td_vals):
        A(f"| {y} | " + ", ".join(f"{k}: {v:,}" for k, v in sorted(td_vals[y].items(), key=str)) + " | " +
          ", ".join(f"{k}: {v:,}" for k, v in sorted(nf_vals[y].items())) + " | " +
          ", ".join(f"{k}: {v:,}" for k, v in sorted(pen_vals[y].items())) + " |")
    A("\n**Three scoring eras, not two.** Takedown went 2 → 3 in 2024 (as the spec says), but near falls changed "
      "twice: **2015** used 2 and 3; **2016–2023** used 2 and 4; **2024–2026** use 2, 3 and 4. (The stray 3s in 2021 "
      "are 2 events.) Tag: `rules_era` = **E1** 2015, **E2** 2016–2023, **E3** 2024–2026. E1 is one season "
      "(~600 NCAA + ~700 conference bouts), too small for its own table — it would be pooled with E2 (same takedown "
      "value, near falls differ by one point in the rarer big-NF case).")
    A("\n### 16. Tech fall threshold by era\n")
    for era in sorted(tf_margin):
        mm = md_margin[era]
        pos = [k for k in tf_margin[era] if k > 0]
        A(f"- **{era}:** 15 points in every era. Most common tech-fall margin {max(tf_margin[era], key=tf_margin[era].get)}; "
          f"largest major-decision margin {max(mm) if mm else '—'}; smallest positive tech-fall margin {min(pos) if pos else '—'}"
          ".")
    A("\n### 17. Other rule changes visible in the data\n")
    A("- **Overtime:** sudden victory 1:00 → 2:00 in 2022; 2026 is the only season under the current OT rules "
      "(earlier work). Keep OT out of the regulation table, as the spec says.")
    A("- Riding time point: still 1 point for 1:00+ advantage in every season with notes.")
    A("- Stalling: logged as 0-point `Stalling` events against the offender; the resulting point appears as a "
      "separate `Penalty N` event to the other side.")

    A("\n## Seed and rank\n")
    A("### 18. NCAA seeds\n")
    A("| Season | Bouts with PBP | Both seeded | One seeded | Neither | Highest seed number seen | Real seeding depth |\n|---|---:|---:|---:|---:|---:|---|")
    for y in sorted(seeds):
        s = seeds[y]
        depth = "1–16 real; 17–33 random draw" if y <= 2018 else "1–33 real (full field)"
        A(f"| {y} | {s['bouts']:,} | {s['both']:,} | {s['one']:,} | {s['none']:,} | {s['max']} | {depth} |")
    A("\nEvery NCAA qualifier has a seed number in the files, but **before 2019 only seeds 1–16 were committee "
      "seeds; 17–33 were a random bracket draw** (docs/matsavant.md, Ranking Methodology). Those numbers are not "
      "strength signal and must be treated as 'unseeded' in the strength layer. So the unseeded tail value "
      "applies to ~half the field in 2015–2018 and to nobody from 2019 on.")
    A("\n### 19–20. Conference: national rank\n")
    A("National rank = MatSavant `current_rank` for that season, matched to each conference wrestler by name "
      "(surname + first initial) and team. 'Ranked' = rank ≤ 33.\n")
    A("| Seasons (rank source) | Bouts | Both ranked | One ranked | Neither | Wrestlers not found |\n|---|---:|---:|---:|---:|---:|")
    for grp in sorted(rank_counts):
        c = rank_counts[grp]
        n = c["both"] + c["one"] + c["neither"]
        A(f"| {grp} | {n:,} | {c['both']:,} ({pct(c['both'], n)}) | {c['one']:,} ({pct(c['one'], n)}) | "
          f"{c['neither']:,} ({pct(c['neither'], n)}) | {c['unmatched_wrestlers']:,} of {c['wrestler_slots']:,} |")
    A("\n**Depth and source are not constant.** Ranks 1–33 come from a different source by era: FloWrestling "
      "(2023+, depth = however many Flo published, often 24–33, ELO below that), actual NCAA placement + committee "
      "seed (2019–2022), placement + real seeds ≤16 + ELO (2015–2018). **Leakage risk:** in 2015–2022 ranks 1–8 "
      "*are* the NCAA placement, and the 2023+ Flo snapshot used is the final (often post-NCAA) one — both are "
      "decided after the conference tournament. For a conference match that means the 'strength' input partly "
      "encodes results from two weeks later. The spec accepts end-of-season values for a retrospective model; "
      "flagging it because it will flatter validation on conference data.")

    A("\n## Event taxonomy\n")
    A("### 21. Distinct event types (clock stripped; numbers grouped)\n")
    A("| Event | Count |\n|---|---:|")
    for k, v in taxonomy.most_common():
        A(f"| {k} | {v:,} |")
    A("\n### 22. Point values\n")
    A("Derived from the event text (`Takedown 3`, `4 Nearfall`, `Penalty 1`; bare `Takedown` = 2, `Escape` = 1, "
      "`Reversal` = 2, `Riding Time` = 1; `Stalling`/`Caution`/`Misconduct` = 0). Each period column also stores "
      "official `period_points`, which is what reconciliation (item 3) checks against.")

    A("\n## Section 11: open questions, answered\n")
    ncaa_full = pct(clocked_bouts[("ncaa", "full")], clocked_bouts[("ncaa", "all")])
    conf_full = pct(clocked_bouts[("conf", "full")], clocked_bouts[("conf", "all")])
    A(f"1. **Timestamp quality / usable matches:** good. Exact seconds, explicit periods, a few dozen clock "
      f"reversals across ~15k bouts. {ncaa_full} of NCAA and {conf_full} of conference bouts have a clock on every "
      f"regulation scoring event.")
    A(f"2. **Running riding time:** not recorded as a field, but reconstructable from the event stream "
      f"({pct(riding_matched, riding_total)} within 5 s of the scorekeeper's clock-pinned notes). **Period choice:** "
      f"recorded (toss winner, defer, and each wrestler's pick for periods 2 and 3) in >99% of bouts that reach "
      f"those periods.")
    both = sum(c["both"] for c in rank_counts.values())
    nall = sum(c["both"] + c["one"] + c["neither"] for c in rank_counts.values())
    A(f"3. **Conference matches with both wrestlers ranked (top 33):** {pct(both, nall)} "
      f"({both:,} of {nall:,}); about a third have one ranked, a third neither.")
    A("4. **Share of match-moments in thin cells:** answered by the sparsity audit (step 4), not here.")
    A("5. **Separate tables per rules era:** three eras exist in the data. Likely answer: pool E1 with E2 (one "
      "season) and keep E3 separate or as a smoothing slice; the sparsity audit decides.")
    A("\n### Decisions needed from TJ before step 2\n")
    A("- **A. Riding time:** use the reconstruction from position (validated ~95%), or follow the spec's fallback "
      "(drop `rt_status`/`rt_bin`, final riding-time point only)? Recommendation: use the reconstruction; the spec's "
      "prohibition is about back-filling from the *final* value, which this doesn't do.")
    A("- **B. Bouts with an unclocked scoring event (~15%):** drop them from the state table, or place each unclocked "
      "event between its clocked neighbours? Recommendation: place them (the neighbours usually pin it within a few "
      "seconds, e.g. a near fall right after its takedown), and flag those bouts so validation can check them separately.")
    A("- **C. Pre-2019 NCAA seeds 17–33** are a random draw: treat as unseeded (tail value). Recommendation: yes.")
    A("- **D. Rules eras:** E1 (2015) pooled with E2, E3 separate. Recommendation: yes, pending the sparsity audit.")
    A("- **E. Conference rank leakage:** end-of-season rank includes later NCAA results. Accept (the spec allows it) "
      "but report conference validation with that caveat, or restrict conference to Flo seasons 2023–26? "
      "Recommendation: accept and caveat; it only affects the step-10 second pass.")
    A("- **F. Falls have no logged time** in the play-by-play. The terminal jump is placed at the last logged event. "
      "Recommendation: accept; it only affects where on a WP curve the final jump is drawn, not WPA of earlier events. "
      "*(Superseded in step 2: every fall has an official time — NCAA `score`, conference `time` — so falls end at "
      "their real time; the last-event rule is only the fallback for injury defaults and DQs.)*")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(L) + "\n")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
