#!/usr/bin/env python3
"""
Builds the Flo-preseason-rankings-schema substitute used for seasons where
real FloWrestling rankings are paywalled -- see docs/matsavant.md's "NCAA
Ranking Methodology (Source of Truth)" section for the full policy and why
each era is ranked the way it is. Two modes, chosen automatically by season:

2019, 2021, 2022 (full committee seeding covers the whole field):
  - Ranks 1-8: the ACTUAL top-8 tournament placers, in placement order (1st
    place match winner = rank 1, loser = rank 2, 3rd place match winner =
    rank 3, ... 7th place match loser = rank 8) -- regardless of seed. If the
    #16 seed placed 7th, they get rank 7, not rank 16.
  - Ranks 9-33: every OTHER seeded wrestler, sorted by their own seed number
    ascending.
  - A tournament with a results.txt that has zero placement-match lines
    (confirmed: 2020, COVID-cancelled) falls back to pure seed order 1-33
    for the whole field -- there's no real placement to override seed with.

2012-2018 (only the top 16 were REALLY committee-seeded -- seed numbers
17-33 in the scraped seed files are a blind random draw slot, not real
signal, so they can't be trusted as a sort key):
  - Ranks 1-8: same as above, actual placement.
  - Ranks 9-12: the 4 "blood round" losers -- the match where winning locks
    a minimum of 8th place and losing means no placement at all. Identified
    STRUCTURALLY from the full match-by-match bracket (not a hardcoded
    round-name string, since label text isn't guaranteed identical every
    year) -- see find_blood_round_losers(). Real-seeded (<=16) losers sort
    first by seed ascending; unseeded ones sort after by Elo descending.
  - Ranks 13-33: the remaining qualifiers, same seeded-then-Elo split.
  - Requires Elo scores to already exist for the season (mt/elo_ratings/
    ncaa_men/{season}/elo_ratings.json) -- for a fully-completed historical
    season this is a one-time chicken-and-egg exception to the normal
    apply_flo_rankings.py-before-calculate_elo_ratings.py order: run
    calculate_elo_ratings.py once first (no snapshot exists yet, so no
    Flo-seed boost -- fine, since that boost only affects early-season
    predictions, not a season's final ratings), use those final scores to
    build this snapshot, then run the normal chain afterward same as any
    other season.

Data sources:
  - data/{season}/ncaa-tourney/seeds/{weight}.txt (committee seed list)
  - data/{season}/ncaa-tourney/results.txt (full match-by-match results, one
    weight section per class -- every match line, not just the 4 placement
    ones, is parsed for the 2012-2018 mode)
  - mt/elo_ratings/ncaa_men/{season}/elo_ratings.json (2012-2018 mode only)

Usage:
  .venv/bin/python scripts/rankings/build_seed_placement_rankings.py --season 2019
  .venv/bin/python scripts/rankings/build_seed_placement_rankings.py --season 2015 --dry-run
"""
import argparse
import json
import re
from pathlib import Path

STANDARD_WEIGHTS = ["125", "133", "141", "149", "157", "165", "174", "184", "197", "285"]
REAL_SEED_CUTOFF = 16  # pre-2019: only seeds 1-16 are a genuine committee judgment

PLACEMENT_RE = re.compile(
    r"^(\d+)(?:st|nd|rd|th) Place Match - (.+?) \([^)]*\)\s+[\d-]+\s+won\b.+?\bover\s+(.+?)\s*\([^)]*\)\s+[\d-]+",
)

# Same shape as PLACEMENT_RE but captures ANY round's label/winner/loser, not
# just the 4 placement-match lines -- e.g. "Cons. Round 4 - X won ... over Y",
# "Quarterfinal - X won ... over Y". Used to reconstruct the full bracket for
# the pre-2019 blood-round split.
GENERAL_MATCH_RE = re.compile(
    r"^(.+?) - (.+?) \([^)]*\)\s+[\d-]+\s+won\b.+?\bover\s+(.+?)\s*\([^)]*\)\s+[\d-]+",
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


def parse_full_bracket(season):
    """Returns {weight: [(round_label, winner_name, loser_name), ...]} in
    FILE order -- which is reverse-chronological (the championship/
    placement matches are listed first, the very first bracket round last).
    Every match line carries its own round label as a prefix (e.g. "Cons.
    Round 4 - ...", "Quarterfinal - ...", "1st Place Match - ..."), so this
    doesn't need to track separate round-header lines at all -- one regex
    over every line gets the whole bracket in one pass."""
    path = Path(f"data/{season}/ncaa-tourney/results.txt")
    text = path.read_text()

    out = {}
    current_weight = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped in STANDARD_WEIGHTS:
            current_weight = stripped
            out.setdefault(current_weight, [])
            continue
        if current_weight is None:
            continue
        m = GENERAL_MATCH_RE.match(stripped)
        if not m:
            continue
        round_label, winner, loser = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        out[current_weight].append((round_label, winner, loser))
    return out


def find_blood_round_losers(matches, placed_norm_names):
    """matches: this weight's (round_label, winner, loser) tuples in FILE
    order (reverse-chronological -- see parse_full_bracket). Returns
    (blood_round_label, [loser_name, ...]) for the 4 wrestlers who lost the
    "blood round" (the consolation match where winning locks a minimum of
    8th and losing means no placement at all -- canonical `C_QF` in
    docs/matsavant.md's round-label reference), or (None, []) if no clean
    round of exactly 4 was found.

    This is deliberately STRUCTURAL, not a hardcoded round-name lookup --
    label text (e.g. "Cons. Round 4 (32 Man)") isn't guaranteed identical
    every year, but its defining property is: every one of ITS winners goes
    on to place top-8, and every one of its losers never wrestles again and
    never places. Concretely: walk the bracket top-to-bottom (== latest
    round first), and for every wrestler NOT among the 8 placers, their
    FIRST appearance in this scan is necessarily their actual final match
    (since later rounds are listed first). Group these true-eliminations by
    round label. Multiple rounds can each eliminate exactly 4 unplaced
    wrestlers in a standard bracket (a round further back, e.g. Cons. Round
    3, eliminates its own 4 -- just a lower tier, not blood-round losers) --
    the correct one is the FIRST such group encountered in the scan (i.e.
    closest to the placement matches), not just any group of 4."""
    seen = set()
    round_first_index = {}
    eliminations_by_round = {}

    for idx, (round_label, winner, loser) in enumerate(matches):
        round_first_index.setdefault(round_label, idx)
        for name, is_loser in ((winner, False), (loser, True)):
            norm = normalize_name(name)
            if norm in seen:
                continue
            seen.add(norm)
            if is_loser and norm not in placed_norm_names:
                eliminations_by_round.setdefault(round_label, []).append(loser)

    candidates = [
        (round_first_index[label], label, losers)
        for label, losers in eliminations_by_round.items()
        if len(losers) == 4
    ]
    if not candidates:
        return None, []
    candidates.sort(key=lambda c: c[0])
    return candidates[0][1], candidates[0][2]


def load_elo_by_name(season):
    """{normalize_name(name): elo_score} for a season, from
    mt/elo_ratings/ncaa_men/{season}/elo_ratings.json. Required for the
    2012-2018 mode's seeded-vs-unseeded sort -- must already exist (run
    calculate_elo_ratings.py once first for a season with no snapshot yet;
    see this file's module docstring for why that's safe for a completed
    historical season)."""
    path = Path(f"mt/elo_ratings/ncaa_men/{season}/elo_ratings.json")
    if not path.exists():
        raise SystemExit(
            f"No Elo ratings found for season {season} ({path}) -- the pre-2019 blood-round "
            f"mode needs Elo scores to sort unseeded wrestlers. Run first (no snapshot exists "
            f"yet for this season, which is fine -- see this script's module docstring):\n"
            f"  .venv/bin/python scripts/rankings/calculate_elo_ratings.py -season {season} "
            f"--league ncaa --gender men"
        )
    out = {}
    for e in json.loads(path.read_text()):
        name = e.get("name")
        if name:
            out[normalize_name(name)] = e.get("elo_score", 0)
    return out


def sort_seeded_then_elo(entries, elo_by_norm_name):
    """entries: [{"seed": int, "name": ..., "school": ...}, ...]. Splits into
    real-seeded (<=16, a genuine committee judgment pre-2019) sorted by seed
    ascending, then everyone else (seed 17-33, a blind random draw slot --
    not real signal) sorted by Elo descending. Missing Elo sorts last within
    the unseeded group rather than erroring."""
    seeded = sorted(
        (e for e in entries if e["seed"] <= REAL_SEED_CUTOFF),
        key=lambda e: e["seed"],
    )
    unseeded = sorted(
        (e for e in entries if e["seed"] > REAL_SEED_CUTOFF),
        key=lambda e: elo_by_norm_name.get(normalize_name(e["name"]), float("-inf")),
        reverse=True,
    )
    return seeded + unseeded


def build_season(season, dry_run=False):
    pre_2019 = season < 2019  # only seeds 1-16 are real committee judgment before this

    seeds_by_weight = parse_seeds(season)
    placements_by_weight = parse_placements(season)
    full_bracket_by_weight = parse_full_bracket(season) if pre_2019 else {}
    elo_by_norm_name = load_elo_by_name(season) if pre_2019 else {}

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

        if not pre_2019:
            # 2019/2021/2022: full field is really committee-seeded -- pure
            # seed order for everyone not among the top 8.
            remaining.sort(key=lambda s: s["seed"])
        else:
            # 2012-2018: split ranks 9-12 (blood-round losers) and 13-33
            # (remaining qualifiers) each into real-seeded (<=16, sorted by
            # seed) then unseeded (sorted by Elo) -- see module docstring.
            matches = full_bracket_by_weight.get(weight, [])
            blood_round_label, blood_losers = find_blood_round_losers(matches, matched_norm_names)
            blood_norm_names = {normalize_name(n) for n in blood_losers}

            if len(blood_losers) != 4:
                print(f"  [{weight}] WARNING: couldn't cleanly identify 4 blood-round losers "
                      f"(found {len(blood_losers)}) -- falling back to pure seed order for "
                      f"ranks 9+ at this weight only")
                remaining.sort(key=lambda s: s["seed"])
            else:
                blood_round_entries = [s for s in remaining if normalize_name(s["name"]) in blood_norm_names]
                qualifier_entries = [s for s in remaining if normalize_name(s["name"]) not in blood_norm_names]

                # A results.txt name that doesn't match anyone in the seed
                # list (spelling variant, etc.) would otherwise just vanish
                # from the output -- add them back with no real seed (999,
                # so sort_seeded_then_elo treats them as unseeded/Elo-sorted)
                # rather than silently dropping a real blood-round loser.
                matched_blood_norms = {normalize_name(s["name"]) for s in blood_round_entries}
                unmatched_blood = [n for n in blood_losers if normalize_name(n) not in matched_blood_norms]
                if unmatched_blood:
                    print(f"  [{weight}] WARNING: {len(unmatched_blood)} blood-round loser(s) not "
                          f"found in seed list (name mismatch?) -- kept, treated as unseeded: {unmatched_blood}")
                    for name in unmatched_blood:
                        blood_round_entries.append({"seed": 999, "name": name, "school": None})

                blood_round_sorted = sort_seeded_then_elo(blood_round_entries, elo_by_norm_name)
                qualifiers_sorted = sort_seeded_then_elo(qualifier_entries, elo_by_norm_name)
                remaining = blood_round_sorted + qualifiers_sorted

        ranked = list(top8)
        next_rank = len(top8) + 1
        for s in remaining:
            ranked.append({"rank": next_rank, "name": s["name"], "school": s["school"]})
            next_rank += 1

        ranked.sort(key=lambda e: e["rank"])
        weights_out[weight] = ranked

    if not pre_2019:
        note = ("Substitute for paywalled FloWrestling rankings: top 8 = actual tournament "
                 "placement order (not seed), 9-33 = remaining wrestlers by committee seed "
                 "(full field genuinely seeded from 2019 on).")
    else:
        note = ("Substitute for paywalled FloWrestling rankings, pre-2019 mode (only seeds "
                 "1-16 are real committee judgment before 2019): top 8 = actual tournament "
                 "placement order, 9-12 = the 4 blood-round losers, 13-33 = remaining "
                 "qualifiers -- both of those tiers sorted real-seed-first (<=16, by seed) "
                 "then unseeded-by-Elo. See docs/matsavant.md's NCAA Ranking Methodology.")

    data = {
        "source": "ncaa_tournament_seeds_and_placement",
        "rankings_url": None,
        "ranking_date": f"{season}-03-20",
        "season": season,
        "note": note,
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
