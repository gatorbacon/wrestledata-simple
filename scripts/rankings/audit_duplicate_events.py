#!/usr/bin/env python3
"""
audit_duplicate_events.py — DRY-RUN audit for duplicated tournaments/duals ("clone events").

Problem: TrackWrestling sometimes lists the same event twice (different names and/or dates — e.g.
"HATFIELD-MCCOY 32" 12/29 and "Boys Hatfield McCoy 32 2025" 12/30), or two teams' files date the same
dual a day apart. Every bout then appears twice on the wrestlers' pages, and the existing de-dupe in
load_data.py / build_wrestler_profiles.py misses it because its key includes the exact date.

This script DETECTS and REPORTS; it never changes match data. The detection code lives in duplicate_events.py,
which load_data.py uses (behind --dedupe-events) to remove duplicates for ONLY the event pairs a human has approved
(data/duplicate_events/approved_duplicate_events.json). Workflow:
    1. run this audit, skim event_pairs_review.csv / bouts_review.csv (and confirmed, if you like)
    2. approve:  --approve-confirmed          (every pair currently classed "confirmed")
                 --approve-ids 12,40,41       (specific pair_ids from this run — also lets you approve review pairs)
    3. run load_data.py ... --dedupe-events   (removes the extra copies; writes applied_{gender}_{season}.csv)
    Once applied, the duplicates are gone from the saved data, so a re-run of this audit no longer lists them.

Input : mt/rankings_data/hs_ky_{gender}/{season}/weight_class_*.json  (merged output of load_data.py --save;
        run load_data.py first if it's stale)
Output (mt/audits/duplicate_events/):
        event_pairs_review.csv / bouts_review.csv        <- the only files that need a human look
        event_pairs_confirmed.csv / bouts_confirmed.csv  <- judged duplicates (kept for audit/merge; no review needed)
        event_pairs_rejected.csv                         <- judged NOT duplicates (audit trail only)
        plus a console summary.

Two copies of a bout are the SAME bout when they involve the same wrestler pair and the same result type
(score kept) and their times are compatible:
    - identical results (incl. identical real times like "Fall 3:52")        -> same bout, real evidence
    - one side is the "0:00" placeholder (e.g. Fall 0:00 vs Fall 0:48)        -> compatible, but weak evidence
    - both times real and DIFFERENT (Fall 3:05 vs Fall 1:17, TF times differ) -> different results = a CONFLICT,
      treated as two separate bouts (never a duplicate)
"0:00" is the only placeholder time. A "specific" (proof) bout = a score, or a fall with the same real time on both copies.

Two events (event name + date) in the same season are compared when they share bouts and either are <= 3 days apart
(names may differ entirely) or are 4-14 days apart with similar names. Outcome, in order:
    rejected : fewer than 2 compatible shared bouts, or conflicts >= compatible bouts (different results = not duplicates)
    confirmed: (a) >= 3 proof bouts (>= 2 if the event names are similar) with few conflicts — e.g. the 2014 KHSAA
                   Region listings: 94 identical scores/times, a week apart;
               (b) MIRRORED DUAL: "vs. Team A" + "vs. Team B", back-to-back days, >= 3 shared bouts, none conflicting,
                   and every shared bout is a Team A wrestler vs a Team B wrestler (one team entered the dual a day off);
               (d) LARGE BACK-TO-BACK: same day or consecutive days, >= 5 shared bouts including >= 1 identical non-fall
                   result (Dec/MD/TF), none conflicting (0:00 placeholders allowed) — names may differ, dual/tournament
                   labels included: that much identical, non-fall overlap can't be coincidence;
               (c) SIMILAR NAMES, back-to-back days, >= 3 shared bouts, none conflicting (0:00 placeholders allowed) —
                   never when one event is a dual ("vs. X") and the other a tournament.
    rejected : (weak-evidence only, i.e. no proof bouts) one event is a dual and the other a tournament, or the events
               are different and >= 2 days apart. Exception -> review: dual vs tournament on back-to-back days with
               >= 4 shared, non-conflicting bouts (could be a dual-format tournament listed both ways).
    review   : everything else that shares compatible bouts (mostly 0:00-only overlap, 1 proof bout between differently
               named events, or proof bouts alongside conflicts).
Forfeits/defaults/byes are ignored.

Usage:
  .venv/bin/python scripts/rankings/audit_duplicate_events.py                 # both genders, all seasons
  .venv/bin/python scripts/rankings/audit_duplicate_events.py -gender boys -season 2026
  .venv/bin/python scripts/rankings/audit_duplicate_events.py --find hatfield   # also print pairs whose event names contain text
  .venv/bin/python scripts/rankings/audit_duplicate_events.py --approve-confirmed   # record confirmed pairs as approved
  .venv/bin/python scripts/rankings/audit_duplicate_events.py --approve-ids 4,7     # approve chosen pair_ids (any status but rejected)
"""

import argparse
import collections
import csv
import os
from pathlib import Path

from duplicate_events import *  # noqa: F401,F403  (detection, keep rule, approved-decision helpers)
from datetime import date as _date   # after the star import, which exports the datetime *class*


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

EVENT_PAIR_COLS = [
    "pair_id", "status", "approved", "reason", "gender", "season", "gap_days", "name_similar", "shared_bouts",
    "shared_specific", "conflicts", "overlap_pct", "event_a", "date_a", "n_bouts_a", "event_b", "date_b", "n_bouts_b",
]
BOUT_COLS = [
    "pair_id", "status", "gender", "season", "weight", "wrestler_1", "team_1", "wrestler_2", "team_2",
    "evidence", "date_a", "event_a", "result_a", "date_b", "event_b", "result_b", "suggested_keep", "keep_reason",
]


def _fmt(d):
    return d.strftime("%Y-%m-%d")


def _write_csv(path, cols, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def discover_seasons(gender, data_dir):
    base = Path(data_dir) / f"hs_ky_{gender}"
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir() and p.name.isdigit())


def _line(p):
    return (f"  [{p['status']}] {p['gender'][0]}{p['season']}  {p['shared_bouts']:>3} shared "
            f"({p['shared_specific']} proof, {p['conflicts']} conflicts)  "
            f"{_fmt(p['date_a'])} {p['event_a']!r} ({p['n_bouts_a']}) <-> {_fmt(p['date_b'])} {p['event_b']!r} ({p['n_bouts_b']})")


def main():
    ap = argparse.ArgumentParser(description="Dry-run audit for duplicated events (no data is changed).")
    ap.add_argument("-gender", "--gender", choices=["boys", "girls", "both"], default="both")
    ap.add_argument("-season", "--season", type=int, nargs="*", help="Season(s); default = all found")
    ap.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    ap.add_argument("--find", help="Also print event pairs (any status) whose event names contain this text")
    ap.add_argument("--top", type=int, default=10, help="How many of the largest pairs per status to print")
    ap.add_argument("--approved-file", default=str(DEFAULT_APPROVED_FILE), help="Approved-decisions JSON")
    ap.add_argument("--approve-confirmed", action="store_true",
                    help="Record every currently 'confirmed' pair in the approved file (human sign-off)")
    ap.add_argument("--approve-ids", help="Comma-separated pair_ids from THIS run to approve (confirmed or review)")
    args = ap.parse_args()

    genders = ["boys", "girls"] if args.gender == "both" else [args.gender]
    os.makedirs(args.out_dir, exist_ok=True)
    approved_entries = load_approved(args.approved_file)
    approved_keys = {(e["gender"], str(e["season"]), approval_key(e["event_a"], e["date_a"], e["event_b"], e["date_b"]))
                     for e in approved_entries}

    all_pairs, all_bouts_n = [], 0
    rows_by_status = collections.Counter()      # bout rows a merge would drop, per status
    pair_rows = collections.defaultdict(list)
    bout_rows = collections.defaultdict(list)
    pair_id = 0

    for gender in genders:
        seasons = [str(s) for s in args.season] if args.season else discover_seasons(gender, args.data_dir)
        for season in seasons:
            bouts, names = load_merged_bouts(gender, season, args.data_dir)
            if not bouts:
                continue
            all_bouts_n += len(bouts)
            pairs = find_duplicate_event_pairs(bouts, names)
            for st in ("confirmed", "review"):
                rows_by_status[st] += rows_removed([p for p in pairs if p["status"] == st])
            pairs.sort(key=lambda p: (-p["shared_bouts"], p["date_a"]))
            for p in pairs:
                pair_id += 1
                p["pair_id"], p["gender"], p["season"] = pair_id, gender, season
                st = p["status"]
                pair_rows[st].append({
                    "pair_id": pair_id, "status": st, "reason": p["reason"],
                    "approved": "yes" if (gender, str(season), pair_approval_key(p)) in approved_keys else "no", "gender": gender, "season": season,
                    "gap_days": p["gap_days"], "name_similar": "yes" if p["name_similar"] else "no",
                    "shared_bouts": p["shared_bouts"], "shared_specific": p["shared_specific"], "conflicts": p["conflicts"],
                    "overlap_pct": p["overlap_pct"],
                    "event_a": p["event_a"], "date_a": _fmt(p["date_a"]), "n_bouts_a": p["n_bouts_a"],
                    "event_b": p["event_b"], "date_b": _fmt(p["date_b"]), "n_bouts_b": p["n_bouts_b"],
                })
                if st == "rejected":
                    continue                                     # no bout detail for non-duplicates
                for x, y in p["conflict_rows"]:                  # contradictions, shown so a reviewer can judge them
                    n1, t1 = names.get(x["w1"], (x["w1"], ""))
                    n2, t2 = names.get(x["w2"], (x["w2"], ""))
                    bout_rows[st].append({
                        "pair_id": pair_id, "status": st, "gender": gender, "season": season,
                        "weight": x["weight"] or y["weight"], "wrestler_1": n1, "team_1": t1, "wrestler_2": n2, "team_2": t2,
                        "evidence": "CONFLICT (different real results - NOT a duplicate)",
                        "date_a": _fmt(x["date"]), "event_a": x["event"], "result_a": x["result"],
                        "date_b": _fmt(y["date"]), "event_b": y["event"], "result_b": y["result"],
                        "suggested_keep": "", "keep_reason": "",
                    })
                for x, y, specific in p["matches"]:
                    keep, why = suggest_keep(x, y, p["n_bouts_a"], p["n_bouts_b"])
                    n1, t1 = names.get(x["w1"], (x["w1"], ""))
                    n2, t2 = names.get(x["w2"], (x["w2"], ""))
                    bout_rows[st].append({
                        "pair_id": pair_id, "status": st, "gender": gender, "season": season,
                        "weight": x["weight"] or y["weight"], "wrestler_1": n1, "team_1": t1, "wrestler_2": n2, "team_2": t2,
                        "evidence": "specific" if specific else "weak (0:00 placeholder on one copy)",
                        "date_a": _fmt(x["date"]), "event_a": x["event"], "result_a": x["result"],
                        "date_b": _fmt(y["date"]), "event_b": y["event"], "result_b": y["result"],
                        "suggested_keep": keep, "keep_reason": why,
                    })
            all_pairs.extend(pairs)

    out = args.out_dir
    for st in ("confirmed", "review"):
        _write_csv(os.path.join(out, f"event_pairs_{st}.csv"), EVENT_PAIR_COLS, pair_rows[st])
        _write_csv(os.path.join(out, f"bouts_{st}.csv"), BOUT_COLS, bout_rows[st])
    _write_csv(os.path.join(out, "event_pairs_rejected.csv"), EVENT_PAIR_COLS, pair_rows["rejected"])
    for stale in ("event_pairs.csv", "bouts.csv"):              # superseded first-draft filenames
        if os.path.exists(os.path.join(out, stale)):
            os.remove(os.path.join(out, stale))

    # ---- approvals (explicit human action only) ----
    to_approve = []
    if args.approve_confirmed:
        to_approve += [p for p in all_pairs if p["status"] == "confirmed"]
    if args.approve_ids:
        wanted = {int(i) for i in args.approve_ids.split(",") if i.strip()}
        chosen = [p for p in all_pairs if p["pair_id"] in wanted]
        bad = [p["pair_id"] for p in chosen if p["status"] == "rejected"]
        if bad:
            print(f"Refusing to approve rejected pair_id(s): {bad}")
        to_approve += [p for p in chosen if p["status"] != "rejected"]
        for i in sorted(wanted - {p["pair_id"] for p in all_pairs}):
            print(f"pair_id {i} not found in this run")
    if to_approve:
        today = _date.today().isoformat()
        source = "audit --approve-confirmed" if args.approve_confirmed and not args.approve_ids else "audit --approve-ids"
        merged, added = merge_approved(approved_entries, [entry_from_pair(p, today, source) for p in to_approve])
        save_approved(merged, args.approved_file)
        print(f"Approved {added} new event pair(s) ({len(to_approve) - added} already approved) -> {args.approved_file}")
        approved_keys = {(e["gender"], str(e["season"]), approval_key(e["event_a"], e["date_a"], e["event_b"], e["date_b"]))
                         for e in merged}

    # ---- console summary ----
    cnt = collections.Counter(p["status"] for p in all_pairs)
    print(f"Scanned {all_bouts_n:,} merged bouts ({', '.join(genders)}).\n")
    print(f"  confirmed duplicates : {cnt['confirmed']:>4} event pairs  ->  ~{rows_by_status['confirmed']:,} bout rows "
          f"({rows_by_status['confirmed'] / max(1, all_bouts_n):.2%} of bouts)")
    print(f"  rejected (not dupes) : {cnt['rejected']:>4} event pairs")
    print(f"  LEFT TO REVIEW       : {cnt['review']:>4} event pairs  ->  ~{rows_by_status['review']:,} bout rows")
    n_appr = sum(1 for p in all_pairs if p["status"] == "confirmed"
                 and (p["gender"], str(p["season"]), pair_approval_key(p)) in approved_keys)
    print(f"  approved so far      : {n_appr:>4} of the confirmed pairs are in the approved file "
          f"({cnt['confirmed'] - n_appr} confirmed but NOT yet approved)")
    def _review_kind(reason):
        if reason.startswith("only 0:00"):
            return "only 0:00-placeholder overlap"
        if reason.startswith("dual vs tournament"):
            return "dual vs tournament, back-to-back, many shared bouts"
        if reason.startswith("only"):
            return "only 1 identical-proof bout; names differ"
        return "proof bouts alongside conflicting results"
    rev = collections.Counter(_review_kind(p["reason"]) for p in all_pairs if p["status"] == "review")
    for k, v in rev.most_common():
        print(f"      review because: {k}: {v}")
    by_season = collections.Counter((p["gender"], p["season"]) for p in all_pairs if p["status"] == "review")
    print("\nReview pairs by season:", ", ".join(f"{g[0]}{s}:{n}" for (g, s), n in sorted(by_season.items(), key=lambda x: (x[0][1], x[0][0]))))

    for st in ("confirmed", "review"):
        sel = sorted((p for p in all_pairs if p["status"] == st), key=lambda p: -p["shared_bouts"])[: args.top]
        print(f"\nLargest {st} pairs:")
        for p in sel:
            print(_line(p))
    if args.find:
        needle = args.find.lower()
        hits = [p for p in all_pairs if needle in p["event_a"].lower() or needle in p["event_b"].lower()]
        print(f"\nPairs matching {args.find!r}: {len(hits)}")
        for p in hits:
            print(_line(p))
    print(f"\nWrote CSVs to {out}  (no data was modified)")


if __name__ == "__main__":
    main()
