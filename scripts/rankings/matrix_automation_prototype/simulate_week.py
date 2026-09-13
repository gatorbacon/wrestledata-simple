#!/usr/bin/env python3
"""
Chained week-by-week ranking simulator. Unlike run_week.py (which always
re-loads the REAL published archive as the "before" state), this carries our
OWN simulated order forward from week to week - because match dates are
backdated in the data, comparing our output to what TJ actually published a
given week is meaningless (he often hadn't seen a match yet that's dated
earlier). Only the very first week bootstraps from a real archive (the
season-start baseline TJ already set by hand); every week after that starts
from the state file this script itself wrote last time.

Usage (first week of a chain):
    .venv/bin/python simulate_week.py --weight 157 --after 2026-01-15 \
        --bootstrap-from 2026-01-06

Usage (continuing chain):
    .venv/bin/python simulate_week.py --weight 157 --after 2026-01-22
"""
import argparse
import importlib.util
import json
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path("/Users/tjthompson/Documents/Cursor/wrestledata-simple")
SCRATCH = Path(__file__).parent
RANKINGS_SCRIPTS = REPO_ROOT / "scripts" / "rankings"

import sys
sys.path.insert(0, str(SCRATCH))
import ranking_engine as re
import temporal_load_data


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


br = load_module("build_relationships", RANKINGS_SCRIPTS / "build_relationships.py")
gm = load_module("generate_matrix", RANKINGS_SCRIPTS / "generate_matrix.py")


def parse_match_date(s):
    return datetime.strptime(s, "%m/%d/%Y").date()


def state_path(weight, gender, season):
    return SCRATCH / f"sim_state_{gender}_{season}_{weight}.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weight", required=True)
    ap.add_argument("--after", required=True, help="YYYY-MM-DD: as-of date for this week's run")
    ap.add_argument("--bootstrap-from", default=None, help="YYYY-MM-DD real archive to seed week 1 from")
    ap.add_argument("--gender", default="boys")
    ap.add_argument("--season", type=int, default=2026)
    args = ap.parse_args()

    after_date = datetime.strptime(args.after, "%Y-%m-%d").date()
    sp = state_path(args.weight, args.gender, args.season)

    if args.bootstrap_from:
        boot_date = datetime.strptime(args.bootstrap_from, "%Y-%m-%d").date()
        archive_path = (REPO_ROOT / "frontend/hs-ky-ui/public/data/rankings" / args.gender /
                         str(args.season) / args.bootstrap_from / f"{args.weight}.json")
        archive = json.loads(archive_path.read_text())
        wsorted = sorted(archive["wrestlers"], key=lambda w: w["rank"])
        state = {
            "as_of_date": args.bootstrap_from,
            "order": [w["wrestler_id"] for w in wsorted],
            "placement_of": {w["wrestler_id"]: w.get("placement_note") for w in wsorted},
            "starter_map": {w["wrestler_id"]: bool(w.get("is_starter", True)) for w in wsorted},
            "name_of": {w["wrestler_id"]: w["name"] for w in wsorted},
        }
        print(f"Bootstrapped week-1 state from real {args.bootstrap_from} archive ({len(state['order'])} wrestlers).")
    elif sp.exists():
        state = json.loads(sp.read_text())
        print(f"Loaded prior sim state as of {state['as_of_date']} ({len(state['order'])} wrestlers).")
    else:
        raise SystemExit(f"No prior state at {sp} and no --bootstrap-from given.")

    before_date = datetime.strptime(state["as_of_date"], "%Y-%m-%d").date()
    if after_date <= before_date:
        raise SystemExit(f"--after ({after_date}) must be later than prior state ({before_date}).")

    order = list(state["order"])
    placement_of = dict(state["placement_of"])
    starter_map = dict(state["starter_map"])
    name_of = dict(state["name_of"])

    # Run the REAL production load_data.py weight-assignment algorithm against match
    # data truncated to <= after_date (never the "final season" weight_class file, which
    # reflects each wrestler's LAST classification and silently drops anyone who moved
    # weight later - see 2026-09-12 discussion). Writes only to a scratch data dir, never
    # to production mt/rankings_data. Weight changes auto-apply (no interactive prompt) -
    # per TJ, getting weight-change approval right isn't in scope for this exercise; that
    # stays a manual, separate step in his real pipeline.
    all_weight_data = temporal_load_data.build_weight_classes_as_of(args.gender, args.season, after_date)
    weight_class_data = all_weight_data.get(args.weight, {"wrestlers": {}, "matches": []})

    # Keep name_of current (a wrestler's display name in the raw pool is authoritative).
    for wid, info in weight_class_data["wrestlers"].items():
        name_of[wid] = info.get("name", name_of.get(wid, wid))

    # A wrestler tracked on THIS board who the real weight-assignment algorithm has since
    # moved to a DIFFERENT weight needs to come OFF this board entirely - not be kept via a
    # stale placeholder. Confirmed real case (2026-09-12): Miles Smith and Jaimerion Young
    # were correctly classified at 157 on 2026-01-06 (TJ's real archive), but the real
    # threshold algorithm has them at 150 by 2026-01-15 - they shouldn't appear in this
    # file's board at all past that point, and their odd-looking rank movement before this
    # fix was just noise from carrying two wrestlers who don't belong here anymore.
    exceptions = []
    moved_away = {}
    for wid in order:
        if wid in weight_class_data["wrestlers"]:
            continue
        for other_wc, other_data in all_weight_data.items():
            if other_wc != args.weight and wid in other_data["wrestlers"]:
                moved_away[wid] = other_wc
                break
    for wid, new_wc in moved_away.items():
        exceptions.append(f"MOVED: {name_of.get(wid, wid)} reclassified to weight {new_wc} - removed from this board.")
    order = [wid for wid in order if wid not in moved_away]
    placement_of = {wid: v for wid, v in placement_of.items() if wid not in moved_away}
    starter_map = {wid: v for wid, v in starter_map.items() if wid not in moved_away}

    # weight_class_*.json's "wrestlers" pool reflects only each wrestler's CURRENT/final weight
    # classification (as of whenever this raw file was last built) - a wrestler tracked on our
    # board who is missing from it (but NOT confirmed moved to another weight above - could be
    # a genuine data gap) shouldn't silently vanish either. Union in anyone from the (now
    # weight-change-filtered) `order` who isn't in the raw pool, so relationship-building and
    # matrix rendering both see the full board.
    full_wrestlers_pool = {wid: dict(info) for wid, info in weight_class_data["wrestlers"].items()}
    for wid in order:
        if wid not in full_wrestlers_pool:
            full_wrestlers_pool[wid] = {"id": wid, "name": name_of.get(wid, wid), "team": "", "weight_class": args.weight, "grade": ""}

    all_matches_through_after = [m for m in weight_class_data["matches"] if parse_match_date(m["date"]) <= after_date]
    rel = br.build_relationships_for_weight_class(
        {"wrestlers": full_wrestlers_pool, "matches": all_matches_through_after},
        season=args.season, data_dir=str(REPO_ROOT / "mt/rankings_data"),
        league="hs", state="KY", gender=args.gender,
    )
    direct_lookup, co_lookup = re.build_lookup(rel["direct_relationships"], rel["common_opponent_relationships"])
    zero_loss_ids = re.zero_loss_ids_from_direct(rel["direct_relationships"])

    # The raw weight-class match pool includes everyone who ever wrestled at this weight this
    # season (JV, one-off, never-ranked) - not just the ~40-ish wrestlers TJ has deliberately
    # chosen to track. Untracked wrestlers must NOT be added to `order`: TJ only puts someone on
    # the board when he's decided they're worth ranking, and giving every match participant a
    # slot would balloon a 40-wrestler board toward 595 overnight. So: skip any new match unless
    # BOTH participants are already tracked (same rule run_week.py used) - untracked wrestlers
    # only get reported as an FYI list, never auto-added to the board.
    ranked_ids = set(order)
    new_matches = [m for m in weight_class_data["matches"] if before_date < parse_match_date(m["date"]) <= after_date]
    untracked_seen = set()
    for m in new_matches:
        for wid in (m["wrestler1_id"], m["wrestler2_id"]):
            if wid not in ranked_ids:
                untracked_seen.add(wid)
    # Out-of-state opponents (tournament fields) and "-1" bye/data placeholders were never
    # trackable KY wrestlers to begin with - don't even list those, just count them.
    noise_ids = {w for w in untracked_seen if w.startswith("OUTSTATE_") or w == "-1"}
    real_untracked = sorted(untracked_seen - noise_ids, key=lambda w: name_of.get(w, w))
    exceptions += [f"Untracked: {name_of.get(wid, wid)} wrestled this week, not on the board."
                   for wid in real_untracked]
    if noise_ids:
        exceptions.append(f"(+{len(noise_ids)} out-of-state/placeholder opponents, not shown)")
    new_match_dates = {}  # frozenset(pair) -> most recent new-match date this week, for move attribution
    for m in new_matches:
        w1, w2 = m["wrestler1_id"], m["wrestler2_id"]
        if w1 in ranked_ids and w2 in ranked_ids:
            new_match_dates[frozenset((w1, w2))] = m["date"]

    def audit_and_resolve(order, lookup, kind, log, exceptions, still_conflicted):
        """Full-board pass: find every conflict of `kind` ('h2h' or 'co') among tracked
        wrestlers - not just ones tied to a match dated this week - and keep resolving
        the highest-priority one (best-ranked victim first) until a full pass makes no
        further progress. This catches standing conflicts baked into the starting state
        (e.g. a backdated match TJ's real archive never reflected), not just new ones.

        Deliberately does NOT permanently blacklist a conflict the first time it can't
        be fixed: a pair that's unresolvable against the CURRENT board can become
        resolvable once an unrelated move elsewhere changes the neighborhood (this was
        a real bug - Walz/Willis looked "anchored" only because it was checked before a
        different fix cleared the way). A "fix" that doesn't actually flip the targeted
        pair is never applied (avoids oscillating between two equally-bad states).

        Performance note: every pass re-attempts every remaining conflict from scratch,
        but a fix elsewhere in the board usually leaves most OTHER gaps byte-for-byte
        identical - re-running an expensive brute force on an unchanged gap is pure
        waste (this was a real perf bug: dozens of real CO conflicts each re-solved on
        every single pass turned seconds into minutes). Cache resolve_gap's result by
        the pair plus the exact current contents of its gap, so an unchanged gap is a
        cheap lookup instead of a repeat brute force."""
        resolve_cache = {}
        # Fixing conflict A can, as a side effect on a shared bystander, incidentally
        # re-break conflict B - and fixing B can re-break A right back. Each individual
        # move genuinely "progresses" (a real fix, not a no-op), so nothing here notices
        # it's happening - only the SEQUENCE of board states reveals the cycle. Track
        # every board state seen in this call; if one repeats, we're oscillating, not
        # converging - stop and leave whatever's left as a genuine exception rather than
        # spin forever (this was a real bug, not just a slow case).
        seen_states = {tuple(order)}
        while True:
            pos = {w: i for i, w in enumerate(order)}
            conflicts = []
            for pair, rel in lookup.items():
                if kind in ("h2h", "placement"):
                    winner, loser = rel["winner"], rel["loser"]
                else:
                    winner, loser = rel["advantaged"], rel["disadvantaged"]
                if winner not in pos or loser not in pos:
                    continue
                if pos[winner] > pos[loser]:
                    conflicts.append((pos[loser], winner, loser))
            if not conflicts:
                return order
            conflicts.sort(key=lambda c: c[0])
            progressed = False
            pass_unresolved = {}
            for _, winner, loser in conflicts:
                pos = {w: i for i, w in enumerate(order)}
                if pos[winner] < pos[loser]:
                    continue  # already fixed earlier this pass
                pair_key = frozenset((winner, loser))
                lo_, hi_ = pos[loser], pos[winner]
                # Cache key is the pair plus the exact gap contents - NOT the whole board, since
                # what's outside the gap can't affect resolve_gap's decision for it. Cache stores
                # just the resulting GAP + note (not a full new_order), which gets stitched onto
                # the CURRENT prefix/suffix below - reusing a stale full new_order verbatim would
                # be wrong if something outside the gap changed since the cache was populated.
                cache_key = (pair_key, tuple(order[lo_:hi_ + 1]))
                if cache_key in resolve_cache:
                    cached_gap, note = resolve_cache[cache_key]
                    new_order = None if cached_gap is None else order[:lo_] + cached_gap + order[hi_ + 1:]
                else:
                    new_order, note = re.resolve_gap(order, winner, loser, direct_lookup, co_lookup, placement_of, zero_loss_ids)
                    resolve_cache[cache_key] = (None if new_order is None else new_order[lo_:hi_ + 1], note)
                if new_order is None:
                    pass_unresolved[pair_key] = (winner, loser, kind, note)
                    continue
                new_pos = {w: i for i, w in enumerate(new_order)}
                if new_pos[winner] > new_pos[loser]:
                    # Best achievable arrangement still leaves this pair conflicted - don't
                    # apply a non-fixing churn move, just note it and keep looking for a
                    # conflict we CAN actually resolve this pass.
                    pass_unresolved[pair_key] = (winner, loser, kind, "anchored - best achievable arrangement still leaves this conflict")
                    continue
                if tuple(new_order) in seen_states:
                    # This fix would take us back to a board state we've already been in this
                    # call - it's genuinely fixing THIS pair, but only by re-breaking whatever
                    # we fixed last time to get away from that exact state. Don't apply it;
                    # leave this pair as a real, explainable exception instead of oscillating.
                    pass_unresolved[pair_key] = (winner, loser, kind, "anchored - fixing this re-breaks another conflict this move already fixed (cycle)")
                    continue
                protected = [name_of.get(w) for w in note.get("anchors_untouched", []) if w in zero_loss_ids]
                date_label = f"({placement_of.get(winner)} vs {placement_of.get(loser) or 'unplaced'})" if kind == "placement" else new_match_dates.get(pair_key, "(pre-existing)")
                log.append({
                    "winner": name_of.get(winner), "loser": name_of.get(loser),
                    "date": date_label,
                    "before_rank_winner": pos.get(winner, "?") + 1, "before_rank_loser": pos.get(loser, "?") + 1,
                    "mode": note["mode"], "protected": protected, "kind": kind,
                })
                order = new_order
                seen_states.add(tuple(order))
                progressed = True
                any_move[0] = True
                break  # positions shifted - restart the scan
            if not progressed:
                still_conflicted.update(pass_unresolved)
                return order

    log = []
    still_conflicted = {}
    any_move = [False]
    # A CO fix can perturb wrestlers who are only bystanders/anchors within its own gap,
    # incidentally flipping an H2H pair that was already resolved (this was a real bug -
    # Walz/Willis kept coming back "anchored" because it was only ever re-checked within
    # the h2h pass, not after a later co move disturbed it). So loop h2h<->co together
    # until one full round-trip makes zero moves in either.
    outer_rounds = 0
    while True:
        outer_rounds += 1
        if outer_rounds > 20:
            exceptions.append(f"WARNING: h2h/co reconciliation didn't settle after {outer_rounds} rounds - stopped early, results may be incomplete.")
            break
        any_move[0] = False
        still_conflicted.clear()
        order = audit_and_resolve(order, direct_lookup, "h2h", log, exceptions, still_conflicted)

        # CO conflicts that just "echo" a LOSS we're intentionally forgiving (anchored H2H,
        # winner side) aren't separate issues - one bad loss can fan out into a dozen CO
        # losses, so don't chase the same underlying loss twice under a different name.
        # Directional: only suppress when the CO-advantaged wrestler was the one who LOST
        # the bridging match (we're forgiving that loss, so don't also penalize it via CO).
        # If instead they WON the bridging match (an accepted win that's just stuck, not a
        # forgiven loss), the CO edge is separate, real evidence and must NOT be suppressed -
        # this was a real bug (Habimana's CO win over Cornell, via his win over Sanford, was
        # being wrongly treated as an echo of the unrelated Habimana/Sanford tangle).
        still_h2h_forgiven_losses = {(loser, winner) for winner, loser, kind, note in still_conflicted.values() if kind == "h2h"}
        co_lookup_filtered = {}
        for pair, nc in co_lookup.items():
            adv = nc["advantaged"]
            if any((adv, opp) in still_h2h_forgiven_losses for opp in nc.get("via", [])):
                continue
            co_lookup_filtered[pair] = nc

        order = audit_and_resolve(order, co_lookup_filtered, "co", log, exceptions, still_conflicted)

        # NOTE (2026-09-12): an active placement-magnet audit pass was prototyped here and
        # pulled back out - see conversation. It correctly diagnosed Miles Smith (Q) sitting
        # above Judah Carey (returning 4th) with zero connecting evidence, but comparing
        # every placed wrestler against every OTHER wrestler on the whole board (not just
        # nearby/adjacent ones) generated thousands of spurious "violations" against
        # unrelated people far down the board and made runs take minutes instead of seconds.
        # More importantly, it's not clear this should be a continuous per-week mechanism at
        # all - TJ described placement as SEEDING behavior ("the only people that move ahead
        # of you are people who beat you or beat someone who beat you"), which reads more
        # like a one-time correction to how a starting archive gets seeded than an ongoing
        # weekly re-litigation against the whole board. Needs scope confirmation before
        # rebuilding - see [[project ranking algorithm]] discussion.

        if not any_move[0]:
            break

    def gap_evidence(winner, loser):
        """Every pairwise direct result among the wrestlers currently between winner and
        loser (inclusive) - shows exactly why an 'anchored' conflict can't be resolved,
        e.g. a genuine 3-way cycle, instead of leaving TJ with just a label."""
        pos = {w: i for i, w in enumerate(order)}
        if winner not in pos or loser not in pos:
            return []
        lo, hi = min(pos[winner], pos[loser]), max(pos[winner], pos[loser])
        gap = order[lo:hi + 1]
        lines = []
        if len(gap) <= 8:
            pairs = [(gap[i], gap[j]) for i in range(len(gap)) for j in range(i + 1, len(gap))]
        else:
            # Too many to dump every pairwise combination - focus on results that directly
            # touch the winner or loser, which is what actually explains THIS conflict.
            pairs = [(w, o) for o in gap if o not in (winner, loser) for w in (winner, loser)]
            lines.append(f"(gap spans {len(gap)} wrestlers - showing only results touching {name_of.get(winner)}/{name_of.get(loser)})")
        for a, b in pairs:
            nd = direct_lookup.get(frozenset((a, b)))
            if nd:
                lines.append(f"{name_of.get(nd['winner'])} beat {name_of.get(nd['loser'])} "
                             f"({nd['severity']}, {nd['date']})")
        return lines

    for winner, loser, kind, note in still_conflicted.values():
        exceptions.append(f"UNRESOLVED {kind.upper()}: {name_of.get(winner)} over {name_of.get(loser)} - {note}")
        for line in gap_evidence(winner, loser):
            exceptions.append(f"    evidence: {line}")

    # Save state for next week.
    new_state = {
        "as_of_date": args.after,
        "order": order,
        "placement_of": placement_of,
        "starter_map": starter_map,
        "name_of": name_of,
    }
    sp.write_text(json.dumps(new_state, indent=2))

    print(f"\n=== Weight {args.weight}: {before_date} -> {after_date} ===")
    print(f"{len(log)} resolving move(s) applied:")
    for entry in log:
        prot = f" [protected: {', '.join(entry['protected'])}]" if entry["protected"] else ""
        print(f"  [{entry['kind'].upper()}] {entry['winner']} (was #{entry['before_rank_winner']}) beat {entry['loser']} (was #{entry['before_rank_loser']}) "
              f"on {entry['date']} -> {entry['mode']}{prot}")
    if exceptions:
        print(f"\n{len(exceptions)} exception(s)/note(s):")
        for e in exceptions:
            print(f"  {e}")

    # --- Build the matrix HTML for review ---
    # Only wrestlers on OUR tracked board (`order`) get a row - not the full raw weight-class
    # pool, which includes hundreds of untracked/JV wrestlers (see untracked_seen above).
    wrestlers_asof = {}
    for wid in order:
        info = full_wrestlers_pool.get(wid, {})
        wrestlers_asof[wid] = dict(info) if info else {
            "id": wid, "name": name_of.get(wid, wid), "team": "", "weight_class": args.weight, "grade": "",
        }
        wrestlers_asof[wid]["name"] = name_of.get(wid, wrestlers_asof[wid].get("name", wid))

    wins_count, losses_count, last_date = {}, {}, {}
    for m in all_matches_through_after:
        w1, w2, winner = m["wrestler1_id"], m["wrestler2_id"], m["winner_id"]
        for wid in (w1, w2):
            if wid not in wrestlers_asof:
                continue
            if winner == wid:
                wins_count[wid] = wins_count.get(wid, 0) + 1
            else:
                losses_count[wid] = losses_count.get(wid, 0) + 1
            dd = parse_match_date(m["date"])
            if wid not in last_date or dd > last_date[wid]:
                last_date[wid] = dd
    for wid, info in wrestlers_asof.items():
        info["wins"] = wins_count.get(wid, 0)
        info["losses"] = losses_count.get(wid, 0)
        info["matches_count"] = wins_count.get(wid, 0) + losses_count.get(wid, 0)
        info["last_match_date"] = last_date[wid].isoformat() if wid in last_date else None

    direct_str = {f"{k[0]}_{k[1]}": v for k, v in rel["direct_relationships"].items()}
    co_str = {f"{k[0]}_{k[1]}": v for k, v in rel["common_opponent_relationships"].items()}
    relationships_data = {
        # Only our tracked board, not the full raw weight-class pool (build_matrix_data
        # appends every wrestler not in ranking_order as an extra "unranked" row - with
        # the full ~590-wrestler pool that balloons the matrix to a multi-MB file).
        "wrestlers": wrestlers_asof,
        "direct_relationships": direct_str,
        "common_opponent_relationships": co_str,
        "ranking_order": order,
        "starter_map": starter_map,
    }

    placement_notes_map = {wid: str(note).strip().upper() for wid, note in placement_of.items() if note}

    frozen_after = after_date

    class FrozenDateTime(datetime):
        @classmethod
        def today(cls):
            return datetime(frozen_after.year, frozen_after.month, frozen_after.day)

    gm.datetime = FrozenDateTime

    matrix_data = gm.build_matrix_data(
        relationships_data,
        placement_notes=placement_notes_map,
        cutoff_date=before_date,
        ir_active_ids=set(),
    )
    html = gm.generate_html_matrix(matrix_data, args.weight, args.season, force_backup_ids=[], ranking_bands_map={})

    out_path = SCRATCH / f"sim_matrix_{args.gender}_{args.season}_{args.weight}_{args.after}.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
