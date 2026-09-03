#!/usr/bin/env python3
"""
Parse NCAA D1 wrestling tournament match-by-match results into structured JSON.

Years covered: 2013-2026 (excluding 2020, cancelled)

Inputs per year:
  data/{year}/ncaa-tourney/results.txt
  data/{year}/ncaa-tourney/seeds/{weight}.txt

Outputs per year:
  data/{year}/ncaa-tourney/parsed/matches.json
  data/{year}/ncaa-tourney/parsed/wrestlers.json

Combined outputs:
  data/ncaa-tourney-parsed/all_matches.json
  data/ncaa-tourney-parsed/all_wrestlers.json

Usage:
  python scripts/ncaa/parse_ncaa_results.py
  python scripts/ncaa/parse_ncaa_results.py --year 2024
  python scripts/ncaa/parse_ncaa_results.py --dry-run
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
COMBINED_DIR = DATA_DIR / "ncaa-tourney-parsed"

YEARS = [2013, 2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026]
WEIGHTS = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]

# ---------------------------------------------------------------------------
# Bracket constants
# ---------------------------------------------------------------------------

BRACKET_FOR_ROUND = {
    "PIG":   "champ", "R32":   "champ", "R16":  "champ",
    "QF":    "champ", "SF":    "champ", "Final": "champ",
    "C_PIG": "consol", "C_R1": "consol", "C_R2": "consol",
    "C_R3":  "consol", "C_R4": "consol", "C_QF": "consol",
    "C_SF":  "consol", "3rd":  "consol", "5th":  "consol", "7th": "consol",
}

# Advancement points earned by the WINNER of each round.
# Placement matches (3rd/5th/7th/Final) give 0 — only placement points apply.
# PIG (champ pigtail) gives 0 — it's a qualifier into R32, not an advancement.
ADVANCEMENT_PTS = {
    "PIG":   1.0,
    "R32":   1.0, "R16": 1.0, "QF": 1.0, "SF": 1.0,
    "Final": 0.0,
    "C_PIG": 0.5,
    "C_R1":  0.5, "C_R2": 0.5, "C_R3": 0.5,
    "C_R4":  0.5, "C_QF": 0.5, "C_SF": 0.5,
    "3rd":   0.0, "5th":  0.0, "7th":  0.0,
}

PLACEMENT_PTS = {
    1: 16.0, 2: 12.0, 3: 10.0, 4: 9.0,
    5:  7.0, 6:  6.0, 7:  4.0, 8: 3.0,
}

# Placement range for wrestlers eliminated in consolation before top-8 matches.
# Losers of C_QF and C_SF continue to placement matches, so they're not in here.
ELIM_RANGE = {
    "C_PIG": (33, 33),
    "C_R1":  (25, 32),
    "C_R2":  (17, 24),
    "C_R3":  (13, 16),
    "C_R4":  ( 9, 12),
}

# Exact placements from named placement matches
PLACEMENT_MATCH_RESULTS = {
    "Final": (1, 2),
    "3rd":   (3, 4),
    "5th":   (5, 6),
    "7th":   (7, 8),
}

# ---------------------------------------------------------------------------
# Round name parsing
# ---------------------------------------------------------------------------

# Match-line prefix → canonical round.
# "Prelim" is ambiguous (PIG vs C_PIG) and resolved via section context.
MATCH_PREFIX_MAP = {
    "Champ. Round 1":  "R32",
    "Champ. Round 2":  "R16",
    "Quarterfinal":    "QF",
    "Semifinal":       "SF",
    "1st Place Match": "Final",
    "Cons. Round 1":   "C_R1",
    "Cons. Round 2":   "C_R2",
    "Cons. Round 3":   "C_R3",
    "Cons. Round 4":   "C_R4",
    "Cons. Round 5":   "C_QF",
    "Cons. Semi":      "C_SF",
    "3rd Place Match": "3rd",
    "5th Place Match": "5th",
    "7th Place Match": "7th",
}

# Section headers that mean the NEXT Prelim match is a consolation pigtail.
CONSOL_PIG_HEADERS = {
    "Consolation Pig Tails",  # 2014-2024
    "Prelim Round 2",         # 2013: C_PIG happens after R32 (later = higher in file)
}

# Section headers that mean the NEXT Prelim match is the championship pigtail.
CHAMP_PIG_HEADERS = {
    "Pig Tails",      # 2014-2024
    "Prelim Round 1", # 2013: PIG happens before R32 (earlier = lower in file)
}

# ---------------------------------------------------------------------------
# Result type / score extraction
# ---------------------------------------------------------------------------

RESULT_PATTERNS = [
    # Order matters: check more specific first.
    # Fall-during-overtime (abbreviated or full form) must come before plain SV/TB patterns.
    ("Fall",    r"won in (?:sudden victory|tie breaker|SV-\d|TB-\d)[^(]*by fall"),
    ("TF",      r"won by tech\.? fall"),
    ("MD",      r"won by major decision"),
    ("Dec",     r"won by decision"),
    ("Fall",    r"won by fall"),
    ("SV-1",    r"won in sudden victory - 1"),
    ("SV-2",    r"won in sudden victory - 2"),
    ("SV-3",    r"won in sudden victory - 3"),
    ("TB-1",    r"won in tie breaker - 1"),
    ("TB-2",    r"won in tie breaker - 2"),
    ("TB-3",    r"won in tie breaker - 3"),
    ("TB-2",    r"won in TB-2 by riding time"),
    ("TB-3",    r"won in TB-3 by riding time"),
    ("UTB",     r"won in the ultimate tie breaker"),
    ("Forfeit", r"won by (?:medical )?forfeit"),
    ("DQ",      r"won by disqualification"),
    ("Inj.",    r"won by injury"),
]

# Bonus points awarded to the winner based on result type.
BONUS_PTS: dict[str, float] = {
    "Dec":     0.0,
    "SV-1":    0.0, "SV-2":    0.0, "SV-3":    0.0,
    "TB-1":    0.0, "TB-2":    0.0, "TB-3":    0.0,
    "UTB":     0.0,
    "MD":      1.0,
    "TF":      1.5,
    "Fall":    2.0,
    "Forfeit": 2.0,
    "DQ":      2.0,
    "Inj.":    2.0,
}


def extract_result_type(text: str) -> str:
    for rt, pat in RESULT_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return rt
    return "Unknown"


def extract_score(text: str, result_type: str) -> Optional[str]:
    """Extract score/time from the trailing parenthetical."""
    m = re.search(r'\(([^()]*(?:\([^()]*\))?[^()]*)\)\s*$', text)
    if not m:
        return None
    paren = m.group(1).strip()

    if result_type == "TF":
        inner = re.search(r'\((\d+-\d+)\)', paren)
        return inner.group(1) if inner else None
    elif result_type == "Fall":
        t = re.search(r'(\d+:\d+)', paren)
        return t.group(1) if t else None
    elif result_type in ("Dec", "MD", "SV-1", "SV-2", "TB-1", "TB-2"):
        s = re.search(r'(\d+-\d+)\s*$', paren)
        return s.group(1) if s else None
    return None

# ---------------------------------------------------------------------------
# Name normalization and seed lookup
# ---------------------------------------------------------------------------

MATCH_RE = re.compile(
    r"^(.+?)\s+\(([^)]+)\)\s+\d+-\d+\s+won\b.+?\bover\s+(.+?)\s+\(([^)]+)\)\s+\d+-\d+"
)


def _norm(s: str) -> str:
    return " ".join(s.lower().split()).replace("`", "'").replace("'", "'")


def _seed_name_to_first_last(seed_name: str) -> str:
    """Convert 'Last, First' seed format to 'first last' normalized."""
    s = seed_name.strip()
    if "," in s:
        last, first = s.split(",", 1)
        return _norm(f"{first.strip()} {last.strip()}")
    return _norm(s)


def build_lookup(seeds: list[dict]) -> dict[str, dict]:
    """Map normalized first-last name → seed entry."""
    return {_seed_name_to_first_last(e["name"]): e for e in seeds}


def lookup_seed(result_name: str, lookup: dict[str, dict]) -> Optional[dict]:
    """Find seed entry for a wrestler by their result-format name (First Last)."""
    norm = _norm(result_name)
    entry = lookup.get(norm)
    if entry:
        return entry
    # Fallback: match on last name + first initial
    parts = norm.split()
    if len(parts) >= 2:
        last = parts[-1]
        first_init = parts[0][0]
        for key, e in lookup.items():
            kparts = key.split()
            if len(kparts) >= 2 and kparts[-1] == last and kparts[0][0] == first_init:
                return e
    return None


def load_seeds(year: int, weight: int) -> list[dict]:
    path = DATA_DIR / str(year) / "ncaa-tourney" / "seeds" / f"{weight}.txt"
    if not path.exists():
        return []
    entries = []
    with path.open(encoding="utf-8") as f:
        lines = f.readlines()
    for line in lines[1:]:  # skip header
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        seed_str = parts[0].strip().rstrip(".")
        try:
            seed_num = int(seed_str)
        except ValueError:
            continue
        entries.append({
            "seed": seed_num,
            "name": parts[1].strip(),
            "team": parts[2].strip(),
        })
    return entries

# ---------------------------------------------------------------------------
# Placement estimation for wrestlers eliminated before top-8
# ---------------------------------------------------------------------------

def estimate_placement(last_round: str, seed: int) -> tuple[int, int, int]:
    """Return (est_placement, pmin, pmax) for consolation-eliminated wrestlers."""
    lo, hi = ELIM_RANGE[last_round]
    if lo == hi:
        return lo, lo, hi
    est = max(lo, min(hi, seed))
    return est, lo, hi

# ---------------------------------------------------------------------------
# Core parser
# ---------------------------------------------------------------------------

def parse_year(year: int, verbose: bool = False) -> tuple[list[dict], list[dict]]:
    """
    Parse one year's results.txt.
    Returns (matches, wrestlers).
    """
    results_path = DATA_DIR / str(year) / "ncaa-tourney" / "results.txt"
    if not results_path.exists():
        print(f"  SKIP {year}: results.txt not found")
        return [], []

    # Load seeds for all weights
    lookups: dict[int, dict] = {}
    seed_entries: dict[int, list[dict]] = {}
    for w in WEIGHTS:
        seeds = load_seeds(year, w)
        seed_entries[w] = seeds
        lookups[w] = build_lookup(seeds)

    all_matches: list[dict] = []

    # Per-wrestler tracking: weight → seed → stats dict
    wrestler_stats: dict[int, dict[int, dict]] = {}
    # Placement tracking: weight → seed → (placement, last_round, exact, pmin, pmax)
    # Set on first encounter (file is latest→earliest, so first = final result)
    placements: dict[int, dict[int, tuple]] = {}

    unmatched: list[str] = []

    current_weight: Optional[int] = None
    in_consol_pig = False  # True when next Prelim = C_PIG, False when = PIG

    with results_path.open(encoding="utf-8") as f:
        lines = f.readlines()

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        # Weight header — exactly 3 digits
        if re.match(r'^\d{3}$', line):
            current_weight = int(line)
            in_consol_pig = False
            wrestler_stats.setdefault(current_weight, {})
            placements.setdefault(current_weight, {})
            continue

        if current_weight is None:
            continue

        # Section header — no "won" or "over"
        if "won" not in line and "over" not in line:
            if line in CONSOL_PIG_HEADERS:
                in_consol_pig = True
            elif line in CHAMP_PIG_HEADERS:
                in_consol_pig = False
            continue

        # Must be a match line — needs " - " separator
        if " - " not in line:
            continue

        prefix, _, match_part = line.partition(" - ")
        prefix = prefix.strip()

        # Resolve canonical round
        if prefix == "Prelim":
            canonical_round = "C_PIG" if in_consol_pig else "PIG"
        else:
            canonical_round = MATCH_PREFIX_MAP.get(prefix)
            if canonical_round is None:
                if verbose:
                    print(f"  WARN [{year} {current_weight}lb]: unknown prefix '{prefix}'")
                continue

        bracket = BRACKET_FOR_ROUND[canonical_round]
        adv_pts = ADVANCEMENT_PTS[canonical_round]

        # Parse winner / loser
        m = MATCH_RE.match(match_part)
        if not m:
            if verbose:
                print(f"  WARN [{year} {current_weight}lb]: can't parse: {line[:80]}")
            continue

        winner_name = m.group(1).strip()
        winner_team = m.group(2).strip()
        loser_name  = m.group(3).strip()
        loser_team  = m.group(4).strip()

        # Seed lookup
        lookup = lookups.get(current_weight, {})
        winner_entry = lookup_seed(winner_name, lookup)
        loser_entry  = lookup_seed(loser_name,  lookup)

        winner_seed = winner_entry["seed"] if winner_entry else None
        loser_seed  = loser_entry["seed"]  if loser_entry  else None

        if winner_entry is None:
            unmatched.append(f"{year} {current_weight}lb W: '{winner_name}' ({winner_team})")
        if loser_entry is None:
            unmatched.append(f"{year} {current_weight}lb L: '{loser_name}' ({loser_team})")

        # Result type and score
        result_type = extract_result_type(match_part)
        score = extract_score(match_part, result_type) if result_type != "Unknown" else None

        all_matches.append({
            "year":        year,
            "weight":      current_weight,
            "round":       canonical_round,
            "bracket":     bracket,
            "winner_seed": winner_seed,
            "winner_name": winner_name,
            "winner_team": winner_team,
            "loser_seed":  loser_seed,
            "loser_name":  loser_name,
            "loser_team":  loser_team,
            "result_type": result_type,
            "score":       score,
        })

        # Track wrestler stats (wins, advancement points)
        for seed, name, team, is_winner in [
            (winner_seed, winner_name, winner_team, True),
            (loser_seed,  loser_name,  loser_team,  False),
        ]:
            if seed is None:
                continue
            if seed not in wrestler_stats[current_weight]:
                wrestler_stats[current_weight][seed] = {
                    "name": name, "team": team,
                    "champ_wins": 0, "consol_wins": 0,
                    "advancement_points": 0.0,
                    "bonus_points": 0.0,
                }
            wd = wrestler_stats[current_weight][seed]
            if is_winner:
                if bracket == "champ":
                    wd["champ_wins"] += 1
                else:
                    wd["consol_wins"] += 1
                wd["advancement_points"] += adv_pts
                wd["bonus_points"] += BONUS_PTS.get(result_type, 0.0)

        # Placement tracking — first encounter wins (file is latest→earliest)
        pl = placements[current_weight]

        if canonical_round in PLACEMENT_MATCH_RESULTS:
            winner_place, loser_place = PLACEMENT_MATCH_RESULTS[canonical_round]
            if winner_seed is not None and winner_seed not in pl:
                pl[winner_seed] = (winner_place, canonical_round, True, winner_place, winner_place)
            if loser_seed is not None and loser_seed not in pl:
                pl[loser_seed] = (loser_place, canonical_round, True, loser_place, loser_place)

        elif canonical_round in ELIM_RANGE:
            # Consolation elimination — loser is done
            if loser_seed is not None and loser_seed not in pl:
                est, pmin, pmax = estimate_placement(canonical_round, loser_seed)
                pl[loser_seed] = (est, canonical_round, False, pmin, pmax)

    # Build wrestler records
    wrestler_records: list[dict] = []
    for weight in WEIGHTS:
        stats = wrestler_stats.get(weight, {})
        pl = placements.get(weight, {})
        for seed in sorted(stats.keys()):
            wd = stats[seed]
            placement_info = pl.get(seed)

            if placement_info:
                placement, last_round, exact, pmin, pmax = placement_info
                placement_pts = PLACEMENT_PTS.get(placement, 0.0) if exact else 0.0
            else:
                # Appeared in results but no placement recorded — flag it
                placement, last_round, exact, pmin, pmax = 0, "Unknown", False, 0, 0
                placement_pts = 0.0
                if verbose:
                    print(f"  WARN [{year} {weight}lb seed {seed}]: no placement found")

            adv = round(wd["advancement_points"], 1)
            bonus = round(wd["bonus_points"], 1)
            total = round(adv + bonus + placement_pts, 1)

            wrestler_records.append({
                "year":               year,
                "weight":             weight,
                "seed":               seed,
                "name":               wd["name"],
                "team":               wd["team"],
                "placement":          placement,
                "placement_exact":    exact,
                "placement_min":      pmin,
                "placement_max":      pmax,
                "last_round":         last_round,
                "champ_wins":         wd["champ_wins"],
                "consol_wins":        wd["consol_wins"],
                "advancement_points": adv,
                "bonus_points":       bonus,
                "placement_points":   placement_pts,
                "total_points":       total,
            })

    if unmatched:
        unique = sorted(set(unmatched))
        print(f"  {year}: {len(unique)} unmatched name(s):")
        for u in unique[:8]:
            print(f"    {u}")
        if len(unique) > 8:
            print(f"    ... and {len(unique) - 8} more")

    return all_matches, wrestler_records

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Parse NCAA tournament results")
    parser.add_argument("--year", type=int, help="Parse a single year")
    parser.add_argument("--dry-run", action="store_true", help="Parse but don't write files")
    parser.add_argument("--verbose", action="store_true", help="Print warnings")
    args = parser.parse_args()

    years = [args.year] if args.year else YEARS

    all_matches: list[dict] = []
    all_wrestlers: list[dict] = []

    for year in years:
        print(f"Parsing {year}...")
        matches, wrestlers = parse_year(year, verbose=args.verbose)
        print(f"  {len(matches)} matches, {len(wrestlers)} wrestler records")
        all_matches.extend(matches)
        all_wrestlers.extend(wrestlers)

        if not args.dry_run and matches:
            out_dir = DATA_DIR / str(year) / "ncaa-tourney" / "parsed"
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "matches.json").write_text(
                json.dumps(matches, indent=2), encoding="utf-8"
            )
            (out_dir / "wrestlers.json").write_text(
                json.dumps(wrestlers, indent=2), encoding="utf-8"
            )

    print(f"\nTotal: {len(all_matches)} matches, {len(all_wrestlers)} wrestler records")

    if not args.dry_run and all_matches:
        COMBINED_DIR.mkdir(parents=True, exist_ok=True)
        (COMBINED_DIR / "all_matches.json").write_text(
            json.dumps(all_matches, indent=2), encoding="utf-8"
        )
        (COMBINED_DIR / "all_wrestlers.json").write_text(
            json.dumps(all_wrestlers, indent=2), encoding="utf-8"
        )
        print(f"Wrote combined files to {COMBINED_DIR}")


if __name__ == "__main__":
    main()
