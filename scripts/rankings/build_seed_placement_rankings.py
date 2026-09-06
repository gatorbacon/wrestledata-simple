#!/usr/bin/env python3
"""
Builds the Flo-preseason-rankings-schema substitute used for seasons where
real FloWrestling rankings are paywalled (2021-22 and earlier -- see
project_ncaa_2024_historical_backfill memory). Earlier backfills (2020,
2021, 2022) just took the NCAA tournament committee's SEED order directly as
the substitute rank. Per user direction (2026-09-04): seed order is the
committee's PRE-tournament guess, and a real placement upset should override
it for the wrestlers who actually earned a top-8 finish.

New rule:
  - Ranks 1-8: the ACTUAL top-8 tournament placers, in placement order (1st
    place match winner = rank 1, loser = rank 2, 3rd place match winner =
    rank 3, ... 7th place match loser = rank 8) -- regardless of seed. If the
    #16 seed placed 7th, they get rank 7, not rank 16.
  - Ranks 9+: every OTHER seeded wrestler (i.e. everyone not among the actual
    top-8 placers), sorted by their own seed number ascending, filling ranks
    9, 10, 11, ... in that order. A seed who would normally have landed in
    9-16 by seed order alone shifts back exactly as many spots as upset
    seeds displaced them from the top 8.

Data sources (both already exist for 2013-2019 from earlier scraping --
2012 is missing results.txt and needs its own investigation before this
script can run for that season):
  - data/{season}/ncaa-tourney/seeds/{weight}.txt (committee seed list)
  - data/{season}/ncaa-tourney/results.txt (full match-by-match results, one
    weight section per class, with "Nth Place Match - Winner (...) ... over
    Loser (...) ..." lines for the 4 placement matches per weight)

Usage:
  .venv/bin/python scripts/rankings/build_seed_placement_rankings.py --season 2019
  .venv/bin/python scripts/rankings/build_seed_placement_rankings.py --season 2019 --dry-run
"""
import argparse
import json
import re
from pathlib import Path

STANDARD_WEIGHTS = ["125", "133", "141", "149", "157", "165", "174", "184", "197", "285"]

PLACEMENT_RE = re.compile(
    r"^(\d+)(?:st|nd|rd|th) Place Match - (.+?) \([^)]*\)\s+[\d-]+\s+won\b.+?\bover\s+(.+?)\s*\([^)]*\)\s+[\d-]+",
)

SEED_LINE_RE = re.compile(r"^(\d+)\.\s+([^\t]+)\t([^\t]*)\t")


def normalize_name(name):
    n = name.lower().strip()
    n = re.sub(r"[.'`]", "", n)
    n = re.sub(r"\s+", " ", n)
    return n


def last_first_to_first_last(name):
    """Seed file format is 'Last, First' (occasionally 'Last, First Middle')."""
    if "," not in name:
        return name.strip()
    last, first = name.split(",", 1)
    return f"{first.strip()} {last.strip()}"


def parse_seeds(season):
    """Returns {weight: [{"seed": int, "name": "First Last", "school": str}, ...]}"""
    seeds_dir = Path(f"data/{season}/ncaa-tourney/seeds")
    out = {}
    for weight in STANDARD_WEIGHTS:
        path = seeds_dir / f"{weight}.txt"
        if not path.exists():
            continue
        entries = []
        for line in path.read_text().splitlines()[1:]:  # skip header row
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            seed_raw, name_raw, school = parts[0], parts[1], parts[2]
            m = re.match(r"^(\d+)\.?$", seed_raw.strip())
            if not m:
                continue
            entries.append({
                "seed": int(m.group(1)),
                "name": last_first_to_first_last(name_raw),
                "school": school.strip(),
            })
        if entries:
            out[weight] = sorted(entries, key=lambda e: e["seed"])
    return out


def parse_placements(season):
    """Returns {weight: [(placement_int, "First Last", "School"), ...]} (up to 8 entries/weight)."""
    path = Path(f"data/{season}/ncaa-tourney/results.txt")
    text = path.read_text()
    lines = text.splitlines()

    out = {}
    current_weight = None
    for line in lines:
        stripped = line.strip()
        if stripped in STANDARD_WEIGHTS:
            current_weight = stripped
            out.setdefault(current_weight, [])
            continue
        if current_weight is None:
            continue
        m = PLACEMENT_RE.match(stripped)
        if not m:
            continue
        place, winner, loser = int(m.group(1)), m.group(2).strip(), m.group(3).strip()
        # winner takes the odd placement named in the match ("1st Place
        # Match" -> winner=1st, loser=2nd; "3rd Place Match" -> winner=3rd,
        # loser=4th), consistent across every season checked (2013-2019).
        out[current_weight].append((place, winner))
        out[current_weight].append((place + 1, loser))
    return out


def build_season(season, dry_run=False):
    seeds_by_weight = parse_seeds(season)
    placements_by_weight = parse_placements(season)

    if not seeds_by_weight:
        raise SystemExit(f"No seed data found for season {season} (data/{season}/ncaa-tourney/seeds/) -- "
                          f"scrape it first (scripts/scraping/scrape_ncaa_tournament.py).")
    if not placements_by_weight:
        raise SystemExit(f"No results.txt found for season {season} (data/{season}/ncaa-tourney/results.txt) -- "
                          f"needed for real placement order, not just seeds.")

    weights_out = {}
    for weight in STANDARD_WEIGHTS:
        seeds = seeds_by_weight.get(weight)
        if not seeds:
            continue
        placements = placements_by_weight.get(weight) or []

        # A tournament that was cancelled before it played out (confirmed:
        # 2020, COVID) has a results.txt with round-header labels but zero
        # actual placement-match lines -- fall back to pure seed order for
        # that weight rather than silently dropping it. This is a no-op
        # relative to the pre-existing seed-only substitute for a genuinely
        # cancelled tournament (no real placements exist to override seed
        # order with), not a bug -- it's the correct degenerate case.
        if not placements:
            weights_out[weight] = [{"rank": s["seed"], "name": s["name"], "school": s["school"]} for s in seeds]
            continue

        seed_by_norm_name = {normalize_name(s["name"]): s for s in seeds}

        top8 = []
        matched_norm_names = set()
        unmatched_placements = []
        for place, name in sorted(placements, key=lambda x: x[0])[:8]:
            norm = normalize_name(name)
            seed_entry = seed_by_norm_name.get(norm)
            if seed_entry:
                top8.append({"rank": place, "name": seed_entry["name"], "school": seed_entry["school"]})
                matched_norm_names.add(norm)
            else:
                unmatched_placements.append((place, name))
                top8.append({"rank": place, "name": name, "school": None})

        if unmatched_placements:
            print(f"  [{weight}] WARNING: {len(unmatched_placements)} placer(s) not found in seed list "
                  f"(name mismatch?) -- used results.txt name/no school: {unmatched_placements}")

        remaining = [s for s in seeds if normalize_name(s["name"]) not in matched_norm_names]
        remaining.sort(key=lambda s: s["seed"])

        ranked = list(top8)
        next_rank = len(top8) + 1
        for s in remaining:
            ranked.append({"rank": next_rank, "name": s["name"], "school": s["school"]})
            next_rank += 1

        ranked.sort(key=lambda e: e["rank"])
        weights_out[weight] = ranked

    data = {
        "source": "ncaa_tournament_seeds_and_placement",
        "rankings_url": None,
        "ranking_date": f"{season}-03-20",
        "season": season,
        "note": ("Substitute for paywalled FloWrestling rankings: top 8 = actual tournament "
                 "placement order (not seed), 9+ = remaining wrestlers by committee seed."),
        "weights": weights_out,
    }

    if dry_run:
        for weight, ranked in weights_out.items():
            print(f"=== {weight} ===")
            for e in ranked[:10]:
                print(f"  {e['rank']:2d}  {e['name']:25s} {e['school']}")
        return data

    out_dir = Path(f"data/{season}/flo-preseason-rankings")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{season}-03-20.json"
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"Wrote {out_path} ({sum(len(v) for v in weights_out.values())} total entries across {len(weights_out)} weights)")
    return data


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    build_season(args.season, dry_run=args.dry_run)
