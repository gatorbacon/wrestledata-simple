#!/usr/bin/env python3
"""
Deterministic conflict-minimizing ranking engine (v1 prototype).

Priority for resolving a "clump" (a window of ranks whose internal order
can't be fully justified by direct results alone):
  1. Minimize H2H conflict count.
  2. Among ties, minimize CO conflict count (with echoes of an already-
     counted H2H match de-duplicated out).
  3. Among ties, minimize the severity of whichever results we're forced
     to override (prefer overriding a Decision over a Fall).
  4. Among ties, prefer overriding the OLDER result (recency).

v1 scope/limits (intentional, called out rather than hidden):
  - Windows are solved as closed systems: only relationships AMONG window
    members are scored. Boundary effects with wrestlers just outside the
    window are not yet checked - a real gap, noted for follow-up.
  - Windows larger than MAX_BRUTE_FORCE are flagged as an exception rather
    than solved with a heuristic - no guessing on sizes we haven't validated.
  - New wrestlers appearing in matches who aren't already on the board are
    flagged as a separate "should this person be added" exception, not
    silently ordered in.
"""
import itertools
import importlib.util
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path("/Users/tjthompson/Documents/Cursor/wrestledata-simple")
MAX_BRUTE_FORCE = 8


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


br = _load_module("build_relationships", REPO_ROOT / "scripts/rankings/build_relationships.py")

SEVERITY_ORDER = {"F": 0, "TF": 1, "INJ": 2, "MFF": 3, "MD": 4, "TB": 5, "D": 6, "NC": 7, "O": 8}


def classify_result_type(result: str) -> str:
    if not result:
        return "O"
    r = result.lower()
    if "mffl" in r or "m. for." in r or "medical forfeit" in r:
        return "MFF"
    if r.strip() == "nc" or "no contest" in r:
        return "NC"
    if "inj" in r or "injury" in r:
        return "INJ"
    if "fall" in r or " pin" in r or r.startswith("fall"):
        return "F"
    if "tf" in r or "technical fall" in r:
        return "TF"
    if "md" in r or "major" in r:
        return "MD"
    if "tb-" in r or "tiebreak" in r:
        return "TB"
    if "dec" in r or "sv-" in r:
        return "D"
    return "O"


def is_mff(result: str) -> bool:
    r = str(result).lower()
    return "mffl" in r or "m. for." in r or "medical forfeit" in r


def parse_date(s: str):
    return datetime.strptime(s, "%m/%d/%Y").date()


def compute_relationships(wrestlers, matches, season, gender, state="KY", league="hs"):
    """Thin wrapper around the production relationship builder."""
    return br.build_relationships_for_weight_class(
        {"wrestlers": wrestlers, "matches": matches},
        season=season, data_dir=str(REPO_ROOT / "mt/rankings_data"),
        league=league, state=state, gender=gender,
    )


def net_direct(rel_entry):
    """Return (winner_id, loser_id, best_severity_code, best_date) or None if
    split/no real (non-MFF) matches."""
    matches = [m for m in rel_entry.get("matches", []) if not is_mff(m.get("result", ""))]
    if not matches:
        return None
    w1, w2 = rel_entry["wrestler1_id"], rel_entry["wrestler2_id"]
    wins1 = sum(1 for m in matches if m["winner_id"] == w1)
    wins2 = sum(1 for m in matches if m["winner_id"] == w2)
    if wins1 == wins2:
        return None
    winner = w1 if wins1 > wins2 else w2
    loser = w2 if winner == w1 else w1
    win_matches = [m for m in matches if m["winner_id"] == winner]
    # Most severe first; among equally-severe wins, the most recent one represents
    # current form best (an old decision shouldn't out-rank a fresh one of the same type).
    best = min(
        win_matches,
        key=lambda m: (SEVERITY_ORDER.get(classify_result_type(m["result"]), 9), -parse_date(m["date"]).toordinal()),
    )
    return {
        "winner": winner, "loser": loser,
        "severity": classify_result_type(best["result"]),
        "date": parse_date(best["date"]), "event": best.get("event", ""), "result": best["result"],
    }


def net_co(rel_entry):
    """Return (advantaged_id, disadvantaged_id, via_opponent_ids) or None if tied/no edge."""
    w1, w2 = rel_entry["wrestler1_id"], rel_entry["wrestler2_id"]
    co_w1, co_l1 = rel_entry.get("common_opp_wins_1", 0), rel_entry.get("common_opp_losses_1", 0)
    co_w2, co_l2 = rel_entry.get("common_opp_wins_2", 0), rel_entry.get("common_opp_losses_2", 0)
    if co_w1 == co_w2:
        return None
    if co_w1 > co_w2:
        advantaged, disadvantaged, details = w1, w2, rel_entry.get("co_details_1", [])
    else:
        advantaged, disadvantaged, details = w2, w1, rel_entry.get("co_details_2", [])
    return {"advantaged": advantaged, "disadvantaged": disadvantaged,
            "via": [d.get("opponent_id") for d in details]}


def build_lookup(direct_rel, co_rel):
    """pair (frozenset) -> net_direct/net_co result, for O(1) access during scoring."""
    direct = {}
    for r in direct_rel.values():
        nd = net_direct(r)
        if nd:
            direct[frozenset((r["wrestler1_id"], r["wrestler2_id"]))] = nd
    co = {}
    for r in co_rel.values():
        pair = frozenset((r["wrestler1_id"], r["wrestler2_id"]))
        if pair in direct:
            continue  # H2H takes full precedence - a pair that has actually wrestled
            # is never also treated as a CO conflict, even if their common-opponent
            # record disagrees with their own head-to-head result.
        nc = net_co(r)
        if nc:
            co[pair] = nc
    return direct, co


def placement_rank(note):
    """Lower is better. Numbered state placements (1-8) sort first, then BR
    (blood round), then Q (qualified for state, didn't reach blood round), then
    no credential at all (unplaced/unknown) sorts last."""
    if not note:
        return 1000
    note = str(note).strip().upper()
    if note.isdigit():
        return int(note)
    if note == "BR":
        return 8.5
    if note == "Q":
        return 8.75
    return 999  # unrecognized code - treat as "some credential" but below numbered/BR


def score_order(order, direct_lookup, co_lookup, placement_of=None):
    """order: list of wrestler_ids in proposed rank order (best first).
    placement_of: optional {wrestler_id: placement_note} for the prior-season-
    placement tiebreak (last resort - a returning state placer defaults to
    sitting at their prior finish until a result says otherwise).
    Returns (h2h_count, co_count, severity_cost, date_cost, accepted_conflicts)."""
    pos = {wid: i for i, wid in enumerate(order)}
    h2h_conflicts = []
    for pair, nd in direct_lookup.items():
        a, b = tuple(pair)
        if a not in pos or b not in pos:
            continue
        winner, loser = nd["winner"], nd["loser"]
        if pos[winner] > pos[loser]:  # worse-ranked (higher index) won -> conflict
            h2h_conflicts.append(nd)

    contaminated_pairs = set()
    for nd in h2h_conflicts:
        contaminated_pairs.add(frozenset((nd["winner"], nd["loser"])))

    co_conflicts = []
    for pair, nc in co_lookup.items():
        a, b = tuple(pair)
        if a not in pos or b not in pos:
            continue
        # skip if this pair also has a direct relationship (H2H takes precedence)
        if pair in direct_lookup:
            continue
        adv, disadv = nc["advantaged"], nc["disadvantaged"]
        if pos[adv] <= pos[disadv]:
            continue  # already consistent
        # de-dup: does the advantaged wrestler's path through any common opponent
        # reuse a match that's already an accepted H2H conflict for them?
        contaminated = any(frozenset((adv, opp)) in contaminated_pairs for opp in nc["via"])
        if contaminated:
            continue
        co_conflicts.append(nc)

    severity_cost = sum(-SEVERITY_ORDER.get(c["severity"], 9) for c in h2h_conflicts)
    date_cost = sum(c["date"].toordinal() for c in h2h_conflicts)

    # Tiebreak beyond count/severity/date: a wrestler with NO accepted conflict
    # anywhere in this window should rank above one who has one, whenever nothing
    # else (an actual result between them) dictates otherwise. Any pair with a real
    # edge is already forced into the right order by the terms above, so it's safe
    # to score this across every pair - only genuinely unconstrained pairs move.
    conflicted_ids = set()
    for c in h2h_conflicts:
        conflicted_ids.add(c["winner"]); conflicted_ids.add(c["loser"])
    for c in co_conflicts:
        conflicted_ids.add(c["advantaged"]); conflicted_ids.add(c["disadvantaged"])
    clean_ids = [w for w in order if w not in conflicted_ids]
    clean_below_conflicted = sum(
        1 for c in clean_ids for x in conflicted_ids if x in pos and pos[c] > pos[x]
    )

    # Last resort: prior-season placement. Only ever breaks a tie once every
    # actual result-based signal above is exhausted - e.g. two wrestlers with
    # no data connecting them at all, most common very early in a season.
    placement_violations = 0
    if placement_of:
        for a in order:
            for b in order:
                if a == b:
                    continue
                if pos[a] < pos[b] and placement_rank(placement_of.get(a)) > placement_rank(placement_of.get(b)):
                    placement_violations += 1

    return (len(h2h_conflicts), len(co_conflicts), severity_cost, date_cost, clean_below_conflicted,
            placement_violations), h2h_conflicts, co_conflicts


def has_edge(a, b, direct_lookup, co_lookup):
    pair = frozenset((a, b))
    return pair in direct_lookup or pair in co_lookup


def zero_loss_ids_from_direct(direct_rel):
    """Wrestler ids with zero accepted (non-MFF) losses among the given raw
    direct_relationships (rel['direct_relationships'], NOT the net_direct
    lookup - a wrestler could split 1-1 with someone and still show no net
    winner/loser via net_direct, which would wrongly hide a real loss here).
    Only covers wrestlers who appear in at least one relationship; a wrestler
    with literally zero matches so far isn't included (nothing to check them
    against yet) - callers should treat "not in this set" as "unknown", not
    "has a loss"."""
    seen, lost = set(), set()
    for r in direct_rel.values():
        w1, w2 = r["wrestler1_id"], r["wrestler2_id"]
        seen.add(w1); seen.add(w2)
        for m in r.get("matches", []):
            if is_mff(m.get("result", "")):
                continue
            loser = w2 if m["winner_id"] == w1 else w1
            lost.add(loser)
    return seen - lost


def rotate(order, winner, loser):
    """Pull winner out and reinsert directly above loser. Pure rotation - everyone
    else's relative order is untouched, they just shift by one slot to close the
    gap winner left and open the one loser now needs."""
    order = list(order)
    order.remove(winner)
    order.insert(order.index(loser), winner)
    return order


def rotation_violates_zero_loss_floor(gap_ids, winner, loser, direct_lookup, co_lookup, zero_loss_ids):
    """A zero-loss wrestler's rank should never get worse for a reason that has
    nothing to do with him. Plain rotation shifts EVERYONE strictly between
    loser's old slot and winner's old slot down by one, with no regard for who
    they are - fine for genuine bystanders, wrong for someone undefeated who
    has no result (direct or CO) connecting them to the winner at all. Note:
    an edge to LOSER only (not winner) doesn't trip this guard - that wrestler
    already gets routed to the movable/brute-force path below, which is where
    a CO-based exception to this floor would eventually need to be judged; not
    implemented yet, deliberately - see module docstring."""
    if not zero_loss_ids:
        return False
    for w in gap_ids[1:-1]:  # gap_ids[0]=loser, gap_ids[-1]=winner
        if w in zero_loss_ids and not has_edge(w, winner, direct_lookup, co_lookup):
            return True
    return False


def filter_lookup_to_window(window_ids, direct_lookup, co_lookup):
    """score_order is called once per rotation check and once per PERMUTATION during
    brute force (up to 8! = 40320 times) - scanning the full global lookup (hundreds
    of relationships across the whole board) inside that loop is the difference
    between milliseconds and minutes once there are more than a handful of conflicts
    to resolve in a run (this was a real perf bug - adding the placement-magnet audit
    multiplied the number of resolve_gap calls and made it actually hurt). Filter once
    per resolve_gap call to just the relationships among this specific window, then
    reuse that tiny dict for every permutation instead of the global one."""
    window_set = set(window_ids)
    small_direct = {pair: v for pair, v in direct_lookup.items() if pair <= window_set}
    small_co = {pair: v for pair, v in co_lookup.items() if pair <= window_set}
    return small_direct, small_co


def resolve_gap(order, winner, loser, direct_lookup, co_lookup, placement_of=None, zero_loss_ids=None):
    """A new result creates winner-ranked-worse-than-loser. Resolve it with the
    smallest disruption that doesn't create a new conflict. Try a plain rotation
    first (winner moves directly above loser, everyone between shifts by exactly
    one - true anchors are naturally left in their relative order by this alone).
    Only fall back to a real solve when the rotation itself would create a new
    conflict with someone genuinely connected to winner or loser in between, OR
    when it would push a zero-loss wrestler down for a reason unconnected to them
    (see rotation_violates_zero_loss_floor) - in that fallback path, such a
    wrestler is classified an anchor (no edge to either side) and keeps their
    EXACT original slot, untouched, rather than being shifted at all.
    Returns (new_order, note)."""
    pos = {w: i for i, w in enumerate(order)}
    lo, hi = pos[loser], pos[winner]
    gap_ids = order[lo:hi + 1]

    gap_direct, gap_co = filter_lookup_to_window(gap_ids, direct_lookup, co_lookup)
    rotated_gap = rotate(gap_ids, winner, loser)
    score, h2h_c, co_c = score_order(rotated_gap, gap_direct, gap_co, placement_of)
    floor_blocked = rotation_violates_zero_loss_floor(gap_ids, winner, loser, direct_lookup, co_lookup, zero_loss_ids)
    if score[0] == 0 and not floor_blocked:  # plain rotation creates no H2H conflicts - done, minimal disruption
        new_order = order[:lo] + rotated_gap + order[hi + 1:]
        return new_order, {"mode": "rotation", "h2h_conflicts": h2h_c, "co_conflicts": co_c}

    # Rotation alone isn't safe - either someone in the gap has real evidence that
    # contradicts it, or a zero-loss wrestler would be shifted for no reason of
    # their own. Narrow to who's actually connected and solve just that subset;
    # everyone else (zero-loss bystanders included) keeps their exact slot.
    movable = [w for w in gap_ids if w in (winner, loser) or has_edge(w, winner, direct_lookup, co_lookup)
               or has_edge(w, loser, direct_lookup, co_lookup)]
    anchors = [w for w in gap_ids if w not in movable]
    if len(movable) > MAX_BRUTE_FORCE:
        return None, f"gap too tangled to solve automatically ({len(movable)} evidentially-connected wrestlers)"

    result = solve_window(movable, direct_lookup, co_lookup, placement_of)
    # Anchors keep their exact relative position; the movable group's new order
    # gets threaded into the slots the movable group originally occupied.
    movable_slots = sorted(i for i, w in enumerate(gap_ids) if w in movable)
    new_gap = list(gap_ids)
    for slot, wid in zip(movable_slots, result["order"]):
        new_gap[slot] = wid
    new_order = order[:lo] + new_gap + order[hi + 1:]
    return new_order, {"mode": "local_solve", "h2h_conflicts": result["h2h_conflicts"],
                        "co_conflicts": result["co_conflicts"], "anchors_untouched": anchors}


def solve_window(window_ids, direct_lookup, co_lookup, placement_of=None):
    """Brute-force the best ordering of window_ids. Returns None if too large."""
    if len(window_ids) > MAX_BRUTE_FORCE:
        return None
    # Filter once, outside the up-to-8!-permutation loop - see filter_lookup_to_window.
    small_direct, small_co = filter_lookup_to_window(window_ids, direct_lookup, co_lookup)
    best_order, best_score, best_conflicts = None, None, None
    for perm in itertools.permutations(window_ids):
        score, h2h_c, co_c = score_order(list(perm), small_direct, small_co, placement_of)
        if best_score is None or score < best_score:
            best_score, best_order, best_conflicts = score, perm, (h2h_c, co_c)
    return {"order": list(best_order), "score": best_score,
            "h2h_conflicts": best_conflicts[0], "co_conflicts": best_conflicts[1]}
