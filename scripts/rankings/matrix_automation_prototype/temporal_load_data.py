#!/usr/bin/env python3
"""
Build a temporally-truncated weight_class_{weight}.json using the REAL
production load_data.py algorithm (team roster loading, weight-class
threshold assignment, etc.) restricted to matches on or before a cutoff
date - instead of the ad hoc reconstruction this replaced.

Reads real per-team files from mt/processed_data/ (read-only, never
modified). Writes its output to a scratchpad data dir, NEVER to production
mt/rankings_data - so nothing here can ever clobber TJ's real pipeline
output.

Per TJ (2026-09-12): for this ranking/matrix-focused exercise, weight-class
changes are auto-approved rather than interactively confirmed - that
approval step stays a manual, separate part of his real weekly pipeline
("I have to manually approve all weight changes at run time... this
allows me to make sure it makes sense"). We're only trying to perfect the
ranking logic here, not automate the whole pipeline, so getting weight
changes perfectly right isn't the goal right now.

Mechanically, auto-approval falls out for free: load_data.py's
is_wrestler_ranked() treats a missing rankings_{weight}.json as "not
ranked," which takes the unconditional auto-apply branch and never calls
the interactive input() prompt at all. So as long as we never write a
rankings_{weight}.json into our scratch data dir, every proposed weight
change auto-applies, no monkeypatching needed.
"""
import importlib.util
import json
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path("/Users/tjthompson/Documents/Cursor/wrestledata-simple")
SCRATCH = Path(__file__).parent
SCRATCH_DATA_DIR = SCRATCH / "temporal_rankings_data"


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


load_data = _load_module("load_data", REPO_ROOT / "scripts/rankings/load_data.py")


def parse_date(s):
    return datetime.strptime(s, "%m/%d/%Y").date()


def load_truncated_teams(gender, season, cutoff_date):
    """Read the REAL processed_data team files (read-only) and return deep
    copies with each wrestler's matches filtered to date <= cutoff_date."""
    data_dir = REPO_ROOT / "mt/processed_data" / f"hs_ky_{gender}" / str(season)
    teams = []
    for f in sorted(data_dir.glob("*.json")):
        team = json.loads(f.read_text())
        for wrestler in team.get("roster", []):
            wrestler["matches"] = [
                m for m in wrestler.get("matches", [])
                if m.get("date") and parse_date(m["date"]) <= cutoff_date
            ]
        teams.append(team)
    return teams


def build_weight_classes_as_of(gender, season, cutoff_date):
    """Run the real load_data weight-assignment algorithm against truncated
    match data. Writes weight_class_{weight}.json + weight_confirmation.json
    to SCRATCH_DATA_DIR (never mt/rankings_data) and returns the resulting
    {weight_str: {wrestlers, matches}} dict (same shape as a real
    weight_class_{weight}.json's contents)."""
    scratch_dir = SCRATCH_DATA_DIR
    scratch_dir.mkdir(parents=True, exist_ok=True)
    teams = load_truncated_teams(gender, season, cutoff_date)
    data = load_data.extract_wrestlers_and_matches(
        teams, season=season, data_dir=str(scratch_dir),
        league="hs", state="KY", gender=gender,
    )
    load_data.save_loaded_data(
        data, season, output_dir=str(scratch_dir),
        league="hs", state="KY", gender=gender,
    )
    return data


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--gender", default="boys")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--as-of", required=True, help="YYYY-MM-DD cutoff date")
    args = ap.parse_args()
    cutoff = datetime.strptime(args.as_of, "%Y-%m-%d").date()
    data = build_weight_classes_as_of(args.gender, args.season, cutoff)
    for wc in sorted(data.keys(), key=lambda w: int(w) if w.isdigit() else 999):
        rankable = [w for w in data[wc]["wrestlers"].values() if not w.get("is_synthetic")]
        print(f"  {wc}: {len(rankable)} wrestlers, {len(data[wc]['matches'])} matches")
