#!/usr/bin/env python3
"""
Correlate an InterMat rankings snapshot to tracked wrestler_ids, using the
same matching pipeline apply_flo_rankings.py uses for FloWrestling (exact
normalized name at the same weight -> last-name+first-initial fallback at
the same weight -> a previously-persisted alias -> the same two checks at
ADJACENT weight classes -> an interactive prompt), with its own alias file
(mt/intermat_name_aliases.json) since InterMat's name spellings don't
always match Flo's the same way (kept separate so a resolved/skipped Flo
alias never silently reused for InterMat or vice versa).

Unlike apply_flo_rankings.py, this does NOT overwrite
mt/rankings_data/ncaa_men/{season}/rankings_{weight}.json -- Flo stays the
pipeline's live-rankings source of truth (generate_matrix.py renders its
order; calculate_elo_ratings.py reads its flo_ranked tags). InterMat is
tracked purely so the two sources can be compared against each other and
against our own current_rank throughout the season. This script writes a
companion file next to the raw snapshot:
  data/<season>/intermat-preseason-rankings/<date>_matched.json
one entry per InterMat-ranked wrestler (rank/name/school + resolved
wrestler_id, or null if skipped) -- same "_matched" suffix pattern already
used for the Flo pipeline's "_individual_modifiers" companion files.

Only correlates a snapshot that doesn't already have a "_matched.json"
companion -- since scrape_intermat_rankings.py only ever writes a NEW dated
file when InterMat's data actually changed, "no companion yet" is exactly
"this is new data since we last correlated." Safe/cheap to re-run after
every scrape (e.g. chained right after it): if nothing new was scraped,
this does nothing and doesn't re-prompt for already-resolved aliases.
Never touches a prior snapshot's companion file.

Usage:
    .venv/bin/python scripts/rankings/correlate_intermat_rankings.py -season 2027
"""
import argparse
import json
import re
import unicodedata
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RANKINGS_DIR = PROJECT_ROOT / "mt" / "rankings_data" / "ncaa_men"
ALIAS_FILE = PROJECT_ROOT / "mt" / "intermat_name_aliases.json"

WEIGHT_ORDER = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]


def normalize_name(name: str) -> str:
    """Same normalization apply_flo_rankings.py uses -- strips accents,
    canonicalizes apostrophe variants, collapses whitespace."""
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


def latest_intermat_snapshot(season: str) -> tuple[dict, str]:
    """Returns (payload, date_str) for the newest raw (non-"_matched")
    snapshot -- YYYY-MM-DD filenames sort chronologically."""
    tourney_dir = DATA_DIR / season / "intermat-preseason-rankings"
    files = sorted(f for f in tourney_dir.glob("*.json") if not f.stem.endswith("_matched"))
    if not files:
        raise FileNotFoundError(f"No InterMat snapshots found in {tourney_dir}")
    latest = files[-1]
    print(f"Using InterMat snapshot: {latest.name}")
    return json.loads(latest.read_text()), latest.stem


def load_rankings(season: str, weight: int) -> dict:
    path = RANKINGS_DIR / season / f"rankings_{weight}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} does not exist -- run the weekly rankings pipeline (at least through "
            f"build_starter_rankings.py) before correlating InterMat, so there's a roster to match against."
        )
    return json.loads(path.read_text())


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


def save_alias(intermat_name, intermat_school, season, wrestler_id, canonical_name):
    aliases = load_aliases()
    aliases.append({
        "intermat_name": intermat_name,
        "intermat_school": intermat_school,
        "season": season,
        "wrestler_id": wrestler_id,  # null means "confirmed no match, don't ask again"
        "canonical_name": canonical_name,
        "notes": "",
    })
    ALIAS_FILE.write_text(json.dumps({"aliases": aliases}, indent=2))


def find_alias(intermat_name, intermat_school, season):
    for a in load_aliases():
        if (a.get("intermat_name") == intermat_name and a.get("intermat_school") == intermat_school
                and a.get("season") == season):
            return a
    return None


def search_roster_by_last_name(query: str, roster_by_weight: dict):
    q = normalize_name(query)
    hits = []
    for entries in roster_by_weight.values():
        for e in entries:
            if q and q in e["norm_name"]:
                hits.append(e)
    return hits


def interactive_resolve(intermat_name, intermat_school, weight, adjacent_hint, roster_by_weight):
    print(f"\n❌ INTERMAT RANKING MISMATCH")
    print(f"   InterMat lists: '{intermat_name}' ({intermat_school}) at {weight} lbs -- no match in your tracked roster.")

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
        print(f"   {len(options)}. Skip this wrestler (exclude, don't ask again)")

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


def resolve_intermat_entry(entry, weight, roster_by_weight, season):
    """Returns a matched roster entry dict, or None if there's no match
    (confirmed skip, or a still-unresolved case the user chose to skip)."""
    intermat_name = entry["name"]
    intermat_school = entry.get("school", "")
    norm = normalize_name(intermat_name)
    last_first = last_first_key(norm)

    match = find_match_at_weight(norm, last_first, weight, roster_by_weight)
    if match:
        return match

    alias = find_alias(intermat_name, intermat_school, season)
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

    resolved = interactive_resolve(intermat_name, intermat_school, weight, adjacent_hint, roster_by_weight)
    save_alias(intermat_name, intermat_school, season,
               resolved["wrestler_id"] if resolved else None,
               resolved["name"] if resolved else "")
    return resolved


def main():
    parser = argparse.ArgumentParser(description="Correlate the latest InterMat snapshot to tracked wrestler_ids (comparison only -- does not touch the live rankings pipeline)")
    parser.add_argument("-season", required=True, help="Season, e.g. 2027 (tourney year -- matches data/<season>/ and mt/rankings_data/ncaa_men/<season>/)")
    parser.add_argument("--force", action="store_true",
                         help="Re-correlate even if the latest snapshot already has a _matched.json companion")
    args = parser.parse_args()
    season = args.season

    intermat_data, snapshot_stem = latest_intermat_snapshot(season)

    # One _matched.json per raw snapshot -- if this snapshot (identified by
    # its own date-stamped filename) has already been correlated, there's
    # nothing new to do. This is what lets the script be re-run freely
    # (e.g. right after every scrape_intermat_rankings.py pull) without
    # redoing work or re-prompting for already-resolved names each time --
    # it only does anything the first time a given dated snapshot shows up.
    out_path = DATA_DIR / season / "intermat-preseason-rankings" / f"{snapshot_stem}_matched.json"
    if out_path.exists() and not args.force:
        print(f"{out_path.name} already exists for snapshot {snapshot_stem}.json -- nothing new to correlate, skipping")
        return

    roster_by_weight, entries_by_id = build_roster_index(season)

    matched_out = {}
    total, matched = 0, 0
    for weight in WEIGHT_ORDER:
        entries = intermat_data["weights"].get(str(weight), [])
        out_entries = []
        for entry in entries:
            total += 1
            match = resolve_intermat_entry(entry, weight, roster_by_weight, season)
            out_entry = dict(entry)
            out_entry["wrestler_id"] = match["wrestler_id"] if match else None
            out_entry["matched_team"] = match["team"] if match else None
            out_entry["matched_weight"] = match["weight"] if match else None
            if match:
                matched += 1
            out_entries.append(out_entry)
        matched_out[str(weight)] = out_entries
        print(f"  {weight} lbs: {sum(1 for e in out_entries if e['wrestler_id'])}/{len(entries)} InterMat-ranked wrestlers matched")

    payload = {
        "source": "InterMat",
        "matched_against": "mt/rankings_data/ncaa_men roster (tracked wrestler_ids)",
        "ranking_date": intermat_data["ranking_date"],
        "season": intermat_data["season"],
        "weights": matched_out,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"\n{matched}/{total} total matched. Saved {out_path}")


if __name__ == "__main__":
    main()
