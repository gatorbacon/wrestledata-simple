#!/usr/bin/env python3
"""
Apply the latest FloWrestling snapshot to rankings_<weight>.json (NCAA D1
men only). This is "step 7b" in the pipeline -- it runs after Ranking Bands
and before Create Ranking Matrix, so the matrix renders Flo's order at the
top instead of a manually hand-tuned one.

For each weight class, in order:
  1. Load the most recently archived FloWrestling snapshot
     (data/<year>/flo-preseason-rankings/*.json -- newest date wins).
  2. For every Flo-ranked wrestler, try to match them to a tracked
     wrestler_id: exact normalized name at the same weight, then
     last-name + first-initial fallback at the same weight, then a
     previously-persisted alias (mt/flo_name_aliases.json), then the same
     two checks at ADJACENT weight classes (catches wrestlers who moved up
     or down a class since Flo's rank was set), then an interactive prompt
     (look up by last name across the whole roster, confirm an
     adjacent-weight suggestion, or skip -- any of which gets persisted so
     you're never asked about the same Flo entry twice).
  3. Overwrite ranks 1..N in rankings_<weight>.json with Flo's order
     (N = however many Flo actually ranks at that weight, not a fixed
     cutoff). Everyone else gets renumbered N+1.. in their existing
     relative order. A wrestler matched at an adjacent weight is moved
     into their new weight's file and removed from their old one.

Usage:
    .venv/bin/python scripts/rankings/apply_flo_rankings.py -season 2026
"""
import argparse
import json
import re
import unicodedata
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RANKINGS_DIR = PROJECT_ROOT / "mt" / "rankings_data" / "ncaa_men"
ALIAS_FILE = PROJECT_ROOT / "mt" / "flo_name_aliases.json"

WEIGHT_ORDER = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]


def normalize_name(name: str) -> str:
    """Same normalization as scripts/analysis/flo_preseason_vs_score.py --
    strips accents, canonicalizes apostrophe variants, collapses whitespace."""
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = re.sub(r"[`´'‘’]", "'", name)
    return re.sub(r"\s+", " ", name.strip().lower())


def last_first_key(norm_name: str):
    parts = norm_name.split()
    return (parts[-1], parts[0][0]) if len(parts) >= 2 else None


def adjacent_weights(weight: int) -> list:
    idx = WEIGHT_ORDER.index(weight)
    out = []
    if idx > 0:
        out.append(WEIGHT_ORDER[idx - 1])
    if idx < len(WEIGHT_ORDER) - 1:
        out.append(WEIGHT_ORDER[idx + 1])
    return out


def latest_flo_snapshot(season: str) -> dict:
    tourney_dir = DATA_DIR / season / "flo-preseason-rankings"
    files = sorted(tourney_dir.glob("*.json"))  # YYYY-MM-DD names sort chronologically
    if not files:
        raise FileNotFoundError(f"No FloWrestling snapshots found in {tourney_dir}")
    latest = files[-1]
    print(f"Using FloWrestling snapshot: {latest.name}")
    return json.loads(latest.read_text())


def load_rankings(season: str, weight: int) -> dict:
    path = RANKINGS_DIR / season / f"rankings_{weight}.json"
    return json.loads(path.read_text())


def save_rankings(season: str, weight: int, data: dict):
    path = RANKINGS_DIR / season / f"rankings_{weight}.json"
    path.write_text(json.dumps(data, indent=2))


def build_roster_index(season: str):
    """Returns (roster_by_weight, entries_by_id):
    roster_by_weight: weight -> [{...rankings_<weight>.json fields..., norm_name, last_first}]
    entries_by_id: wrestler_id -> that same enriched entry (weight-agnostic lookup)
    """
    roster_by_weight = {}
    entries_by_id = {}
    for w in WEIGHT_ORDER:
        data = load_rankings(season, w)
        entries = []
        for r in data["rankings"]:
            norm = normalize_name(r["name"])
            enriched = {**r, "weight": w, "norm_name": norm, "last_first": last_first_key(norm)}
            entries.append(enriched)
            entries_by_id[r["wrestler_id"]] = enriched
        roster_by_weight[w] = entries
    return roster_by_weight, entries_by_id


def find_match_at_weight(norm_name, last_first, weight, roster_by_weight):
    entries = roster_by_weight.get(weight, [])
    for e in entries:
        if e["norm_name"] == norm_name:
            return e
    candidates = [e for e in entries if last_first and e["last_first"] == last_first]
    if len(candidates) == 1:
        return candidates[0]
    return None


def load_aliases() -> list:
    if ALIAS_FILE.exists():
        return json.loads(ALIAS_FILE.read_text()).get("aliases", [])
    return []


def save_alias(flo_name, flo_school, season, wrestler_id, canonical_name):
    aliases = load_aliases()
    aliases.append({
        "flo_name": flo_name,
        "flo_school": flo_school,
        "season": season,
        "wrestler_id": wrestler_id,  # null means "confirmed no match, don't ask again"
        "canonical_name": canonical_name,
        "notes": "",
    })
    ALIAS_FILE.write_text(json.dumps({"aliases": aliases}, indent=2))


def find_alias(flo_name, flo_school, season):
    for a in load_aliases():
        if (a.get("flo_name") == flo_name and a.get("flo_school") == flo_school
                and a.get("season") == season):
            return a
    return None


def search_roster_by_last_name(query: str, roster_by_weight: dict):
    q = normalize_name(query)
    hits = []
    for w, entries in roster_by_weight.items():
        for e in entries:
            if q and q in e["norm_name"]:
                hits.append(e)
    return hits


def interactive_resolve(flo_name, flo_school, weight, adjacent_hint, roster_by_weight):
    print(f"\n❌ FLO RANKING MISMATCH")
    print(f"   Flo lists: '{flo_name}' ({flo_school}) at {weight} lbs -- no match in your tracked roster.")

    while True:
        options = []
        if adjacent_hint:
            aw, entry = adjacent_hint
            options.append(("adjacent", entry))
            print(f"\n   {len(options)}. Use match: {entry['name']} ({entry['team']}, {aw} lbs) -- possible weight change")
        else:
            print()
        options.append(("search", None))
        print(f"   {len(options)}. Search roster by last name")
        options.append(("skip", None))
        print(f"   {len(options)}. Skip this wrestler (exclude from Flo-ranked tier, don't ask again)")

        choice = input("   Choice: ").strip()
        try:
            idx = int(choice) - 1
            kind, payload = options[idx]
        except (ValueError, IndexError):
            print("   Invalid choice.")
            continue

        if kind == "adjacent":
            return payload
        if kind == "skip":
            return None
        if kind == "search":
            query = input("   Enter last name to search: ").strip()
            hits = search_roster_by_last_name(query, roster_by_weight)
            if not hits:
                print("   No matches found.")
                continue
            for i, e in enumerate(hits, 1):
                print(f"     {i}. {e['name']} ({e['team']}, {e['weight']} lbs)")
            print(f"     0. Search again")
            sub = input("   Pick a number: ").strip()
            if sub == "0":
                continue
            try:
                sub_idx = int(sub) - 1
                if 0 <= sub_idx < len(hits):
                    return hits[sub_idx]
            except ValueError:
                pass
            print("   Invalid choice.")


def resolve_flo_entry(flo_entry, weight, roster_by_weight, season):
    """Returns a matched roster entry dict, or None if there's no match
    (confirmed skip, or a still-unresolved case the user chose to skip)."""
    flo_name = flo_entry["name"]
    flo_school = flo_entry.get("school", "")
    norm = normalize_name(flo_name)
    last_first = last_first_key(norm)

    match = find_match_at_weight(norm, last_first, weight, roster_by_weight)
    if match:
        return match

    alias = find_alias(flo_name, flo_school, season)
    if alias:
        if alias["wrestler_id"] is None:
            return None
        for entries in roster_by_weight.values():
            for e in entries:
                if e["wrestler_id"] == alias["wrestler_id"]:
                    return e
        # Alias points at a wrestler_id we can no longer find -- fall through
        # to a fresh interactive resolution rather than silently dropping it.

    adjacent_hint = None
    for aw in adjacent_weights(weight):
        m = find_match_at_weight(norm, last_first, aw, roster_by_weight)
        if m:
            adjacent_hint = (aw, m)
            break

    resolved = interactive_resolve(flo_name, flo_school, weight, adjacent_hint, roster_by_weight)
    save_alias(flo_name, flo_school, season,
               resolved["wrestler_id"] if resolved else None,
               resolved["name"] if resolved else "")
    return resolved


def main():
    parser = argparse.ArgumentParser(description="Apply the latest FloWrestling snapshot to rankings_<weight>.json (NCAA D1 men)")
    parser.add_argument("-season", required=True, help="Season, e.g. 2026")
    args = parser.parse_args()
    season = args.season

    flo_data = latest_flo_snapshot(season)
    roster_by_weight, entries_by_id = build_roster_index(season)

    # Phase 1: resolve every Flo entry to a wrestler_id, regardless of which
    # weight that wrestler is CURRENTLY tracked at. Global claimed_ids so a
    # wrestler can't get assigned twice if Flo (or a bad match) lists them
    # at two weights.
    flo_assignments = {}  # weight -> [wrestler_id, ...] in Flo rank order
    claimed_ids = set()
    for weight in WEIGHT_ORDER:
        flo_entries = flo_data["weights"].get(str(weight), [])
        assigned = []
        for flo_entry in flo_entries:
            match = resolve_flo_entry(flo_entry, weight, roster_by_weight, season)
            if match is None:
                continue
            wid = match["wrestler_id"]
            if wid in claimed_ids:
                continue
            claimed_ids.add(wid)
            assigned.append(wid)
        flo_assignments[weight] = assigned
        print(f"  {weight} lbs: {len(assigned)}/{len(flo_entries)} Flo-ranked wrestlers matched")

    # Phase 2: build & save each weight's final rankings. A wrestler matched
    # at an adjacent weight moves into that weight's file here and is
    # excluded from their old one (claimed_ids covers both cases).
    for weight in WEIGHT_ORDER:
        data = load_rankings(season, weight)
        assigned_ids = flo_assignments[weight]
        current_by_id = {r["wrestler_id"]: r for r in data["rankings"]}

        new_top = []
        for wid in assigned_ids:
            source = current_by_id.get(wid) or entries_by_id[wid]
            entry = {k: v for k, v in source.items() if k not in ("weight", "norm_name", "last_first")}
            # Marks exactly the wrestlers Flo itself ranked (not is_starter,
            # which is an unrelated lineup concept) -- generate_public_matrix.py
            # --flo-only filters on this to cap NCAA's public matrix at Flo's
            # own cutoff instead of the full depth chart.
            entry["flo_ranked"] = True
            new_top.append(entry)

        remaining = [dict(r) for r in data["rankings"] if r["wrestler_id"] not in claimed_ids]
        for r in remaining:
            r["flo_ranked"] = False
        remaining.sort(key=lambda r: r["rank"])

        rank = 1
        for r in new_top + remaining:
            r["rank"] = rank
            rank += 1

        data["rankings"] = new_top + remaining
        save_rankings(season, weight, data)

    print("\nDone.")


if __name__ == "__main__":
    main()
