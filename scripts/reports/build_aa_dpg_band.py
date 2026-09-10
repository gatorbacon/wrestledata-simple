#!/usr/bin/env python3
"""
Builds the "All-American DPG range" band shown on every DPG report chart
(wrestler view, team roster, transfer window): a light-blue band spanning
the 25th-75th percentile of DPG among every NCAA All-American (top-8
finisher) over the 5 most recently completed seasons, plus the average DPG
of that same window's 10 NCAA champions (one per weight) for the dotted
reference line. Not weight-dependent -- one flat set of numbers, pooled
across all 10 weight classes.

Auto-detects the 5 most recent seasons that have BOTH real tournament
placement data (data/ncaa-tourney-parsed/all_wrestlers.json) AND finalized
DPG data (frontend/wrestledata-ui/public/data/mat_value/{season}/) --
never hardcoded to a fixed year range, so this keeps working correctly
every future season without editing.

Name -> wrestler_id join reuses the same normalize_name() + apostrophe
canonicalization + last-name/first-initial fallback pattern already proven
in scripts/analysis/flo_preseason_vs_score.py -- not reinvented here.

Usage:
    python scripts/reports/build_aa_dpg_band.py
    python scripts/reports/build_aa_dpg_band.py --seasons 5   # window size, default 5
"""

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ALL_WRESTLERS_PATH = PROJECT_ROOT / "data" / "ncaa-tourney-parsed" / "all_wrestlers.json"
WRESTLERS_INDEX_DIR = PROJECT_ROOT / "frontend/wrestledata-ui/public/data/wrestlers"
MAT_VALUE_DIR = PROJECT_ROOT / "frontend/wrestledata-ui/public/data/mat_value"
OUTPUT_PATH = PROJECT_ROOT / "frontend/wrestledata-ui/public/data/reports/aa_dpg_band.json"


def normalize_name(name: str) -> str:
    """Matches scripts/analysis/flo_preseason_vs_score.py's normalize_name()
    exactly -- strip accents, canonicalize apostrophe variants, collapse
    whitespace, lowercase."""
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = re.sub(r"[`´'‘’]", "'", name)
    return re.sub(r"\s+", " ", name.strip().lower())


def percentile(sorted_vals, p):
    """Linear-interpolation percentile, matches
    scripts/analysis/build_rank_score_distributions.py's percentile()."""
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p
    f, c = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def eligible_seasons(window: int):
    """Most recent `window` seasons with both real placement data and
    finalized DPG data -- auto-detected, never hardcoded."""
    all_wrestlers = json.loads(ALL_WRESTLERS_PATH.read_text())
    placement_years = sorted(set(w["year"] for w in all_wrestlers), reverse=True)
    out = []
    for year in placement_years:
        mv_path = MAT_VALUE_DIR / str(year) / f"mat_value_{year}.json"
        if mv_path.exists():
            out.append(year)
        if len(out) == window:
            break
    return sorted(out), all_wrestlers


def build_name_to_wid(season: int):
    """(normalized_name, weight) -> wrestler_id for one season, plus a
    (weight, last_name, first_initial) fallback index for nickname/spelling
    mismatches -- same two-tier lookup as flo_preseason_vs_score.py."""
    idx_path = WRESTLERS_INDEX_DIR / str(season) / "index_wrestlers.json"
    by_name = {}
    by_lastname = defaultdict(list)
    if not idx_path.exists():
        return by_name, by_lastname
    for w in json.loads(idx_path.read_text()):
        weight = w.get("weight_class")
        wid = w.get("wrestler_id")
        name = w.get("name")
        if not (weight and wid and name):
            continue
        norm = normalize_name(name)
        by_name[(weight, norm)] = wid
        parts = norm.split()
        if len(parts) >= 2:
            by_lastname[(weight, parts[-1], parts[0][0])].append(wid)
    return by_name, by_lastname


def lookup_wid(weight, name, by_name, by_lastname):
    wid = by_name.get((weight, normalize_name(name)))
    if wid:
        return wid
    parts = normalize_name(name).split()
    if len(parts) >= 2:
        candidates = by_lastname.get((weight, parts[-1], parts[0][0]))
        if candidates and len(candidates) == 1:
            return candidates[0]
    return None


def load_mv_avg_map(season: int):
    """wrestler_id -> mv_avg (DPG) for one season."""
    p = MAT_VALUE_DIR / str(season) / f"mat_value_{season}.json"
    if not p.exists():
        return {}
    return {str(e["wrestler_id"]): e.get("mv_avg") for e in json.loads(p.read_text())}


def main():
    parser = argparse.ArgumentParser(description="Build the AA DPG range band + champion-average line")
    parser.add_argument("--seasons", type=int, default=5, help="Rolling window size (default 5)")
    args = parser.parse_args()

    seasons, all_wrestlers = eligible_seasons(args.seasons)
    if len(seasons) < args.seasons:
        print(f"WARNING: only found {len(seasons)} eligible season(s) with both placement + DPG data "
              f"(wanted {args.seasons}): {seasons}")

    aa_dpg_values = []
    champ_dpg_values = []
    unmatched = []

    for season in seasons:
        by_name, by_lastname = build_name_to_wid(season)
        mv_avg_by_wid = load_mv_avg_map(season)

        season_rows = [w for w in all_wrestlers if w["year"] == season]
        aa_rows = [w for w in season_rows if w.get("placement_exact") and w.get("placement") is not None and w["placement"] <= 8]
        champ_rows = [w for w in season_rows if w.get("placement_exact") and w.get("placement") == 1]

        for row in aa_rows:
            wid = lookup_wid(row["weight"], row["name"], by_name, by_lastname)
            if not wid:
                unmatched.append((season, row["weight"], row["name"]))
                continue
            dpg = mv_avg_by_wid.get(str(wid))
            if dpg is not None:
                aa_dpg_values.append(dpg)

        for row in champ_rows:
            wid = lookup_wid(row["weight"], row["name"], by_name, by_lastname)
            if not wid:
                continue
            dpg = mv_avg_by_wid.get(str(wid))
            if dpg is not None:
                champ_dpg_values.append(dpg)

    aa_dpg_values.sort()
    aa_p25 = percentile(aa_dpg_values, 0.25)
    aa_p75 = percentile(aa_dpg_values, 0.75)
    champ_avg = sum(champ_dpg_values) / len(champ_dpg_values) if champ_dpg_values else None

    output = {
        "seasons_used": seasons,
        "aa_p25": round(aa_p25, 3) if aa_p25 is not None else None,
        "aa_p75": round(aa_p75, 3) if aa_p75 is not None else None,
        "champ_avg": round(champ_avg, 3) if champ_avg is not None else None,
        "n_aa": len(aa_dpg_values),
        "n_champ": len(champ_dpg_values),
        "generated": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    print(f"Seasons used: {seasons}")
    print(f"AA DPG: n={output['n_aa']}, p25={output['aa_p25']}, p75={output['aa_p75']}")
    print(f"Champion DPG: n={output['n_champ']}, avg={output['champ_avg']}")
    if unmatched:
        print(f"{len(unmatched)} AA row(s) had no wrestler_id match (skipped): "
              f"{unmatched[:10]}{' ...' if len(unmatched) > 10 else ''}")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
