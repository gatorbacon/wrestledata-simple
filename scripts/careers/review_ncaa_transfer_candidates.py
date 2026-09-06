#!/usr/bin/env python3
"""
Cross-reference the possible-transfer candidates flagged by
link_ncaa_season.py against the official roster's own data on both sides.
Two signals, strongest first:

  1. previous_school (from the NEW team's official roster) is the site
     directly self-reporting where the wrestler transferred from -- if it
     names the candidate's prior team, that's near-certain confirmation,
     not an inference.
  2. hometown/high_school (from the enrichment join) should match between
     the old-team and new-team appearances of the same real person; a
     same-name coincidence usually won't share either.

Classifies each candidate:
  CONFIRMED    - previous_school names the candidate's prior team, OR
                 hometown/high_school matches on both sides
  CONTRADICTED - hometown AND high_school both present on both sides and
                 both differ, and previous_school doesn't name the
                 candidate's team (very likely NOT the same person)
  UNKNOWN      - not enough data on either side to judge

Never merges anything itself -- prints a merge_careers.py command for each
CONFIRMED case and leaves UNKNOWN/CONTRADICTED for manual judgment.

Usage:
  python scripts/careers/review_ncaa_transfer_candidates.py --season 2026
"""

import argparse
import json
import re
from difflib import SequenceMatcher
from pathlib import Path

TW_DIR = Path("mt/data/ncaa_men")
CAREERS_DIR = Path("data/careers/ncaa_men")
REPORT_DIR = Path("data/career_linking_logs")

# Common state-name variants seen across different athletics sites --
# collapsed to one canonical token so "Corona, Calif." and "Corona,
# California" compare equal instead of falsely contradicting.
STATE_VARIANTS = {
    "ala.": "al", "alabama": "al", "alaska": "ak",
    "ariz.": "az", "arizona": "az", "ark.": "ar", "arkansas": "ar",
    "calif.": "ca", "california": "ca",
    "colo.": "co", "colorado": "co", "conn.": "ct", "connecticut": "ct",
    "del.": "de", "delaware": "de", "d.c.": "dc",
    "fla.": "fl", "florida": "fl", "ga.": "ga", "georgia": "ga",
    "hawaii": "hi", "idaho": "id",
    "ill.": "il", "illinois": "il", "ind.": "in", "indiana": "in",
    "kan.": "ks", "kansas": "ks", "ky.": "ky", "kentucky": "ky",
    "la.": "la", "louisiana": "la", "maine": "me",
    "mass.": "ma", "massachusetts": "ma", "mich.": "mi", "michigan": "mi",
    "minn.": "mn", "minnesota": "mn", "miss.": "ms", "mississippi": "ms",
    "mo.": "mo", "missouri": "mo", "mont.": "mt", "montana": "mt",
    "n.c.": "nc", "north carolina": "nc", "n.d.": "nd", "north dakota": "nd",
    "n.h.": "nh", "new hampshire": "nh", "n.j.": "nj", "new jersey": "nj",
    "n.m.": "nm", "new mexico": "nm", "n.y.": "ny", "new york": "ny",
    "neb.": "ne", "nebraska": "ne", "nev.": "nv", "nevada": "nv",
    "okla.": "ok", "oklahoma": "ok", "ore.": "or", "oregon": "or",
    "pa.": "pa", "pennsylvania": "pa", "r.i.": "ri", "rhode island": "ri",
    "s.c.": "sc", "south carolina": "sc", "s.d.": "sd", "south dakota": "sd",
    "tenn.": "tn", "tennessee": "tn", "tex.": "tx", "texas": "tx",
    "utah": "ut", "vt.": "vt", "vermont": "vt",
    "va.": "va", "virginia": "va", "wash.": "wa", "washington": "wa",
    "w.va.": "wv", "west virginia": "wv",
    "wis.": "wi", "wisconsin": "wi", "wyo.": "wy", "wyoming": "wy",
    "ohio": "oh", "iowa": "ia", "md.": "md", "maryland": "md",
}


def normalize_hometown(s):
    """'St. Paris, Ohio' / 'Saint Paris, OH' -> 'st paris|oh' (comparable)."""
    s = normalize(s)
    if not s:
        return ""
    s = re.sub(r"^saint\b", "st", s)
    parts = [p.strip() for p in s.split(",")]
    if len(parts) >= 2:
        city, state = parts[0], parts[-1]
        state = STATE_VARIANTS.get(state, state)
        return f"{city}|{state}"
    return s


def fuzzy_match(a, b, threshold=0.85):
    if not a or not b:
        return False
    if a == b:
        return True
    return SequenceMatcher(None, a, b).ratio() >= threshold


HS_SUFFIX_RE = re.compile(
    r"\b(high school|senior high school|senior high|secondary school|preparatory school|"
    r"prep school|hs)\b\.?"
)


def normalize_high_school(s):
    """'Benedictine' / 'Benedictine High School' -> 'benedictine' (comparable).
    Confirmed (Nick Abounader, Gavin Ricketts): the same school gets one site's
    plain name and another's "X High School"/"X HS" -- SequenceMatcher ratio
    alone falls well short of the match threshold on that length difference,
    so strip the generic suffix and any trailing state parenthetical first."""
    s = normalize(s)
    if not s:
        return ""
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s)
    s = HS_SUFFIX_RE.sub("", s).strip()
    return re.sub(r"\s+", " ", s)


def hs_match(a, b, threshold=0.85):
    if fuzzy_match(a, b, threshold):
        return True
    if a and b and len(a) >= 4 and len(b) >= 4:
        return a in b or b in a
    return False


def load_wrestler_lookup(year):
    """season_wrestler_id -> {name, hometown, high_school, previous_school, team_name}"""
    out = {}
    season_dir = TW_DIR / str(year)
    for team_file in season_dir.glob("*.json"):
        team_data = json.loads(team_file.read_text())
        team_name = team_data.get("team_name", "")
        for w in team_data.get("roster", []):
            wid = w.get("season_wrestler_id")
            if wid:
                out[wid] = {
                    "name": w.get("name", ""),
                    "hometown": w.get("hometown"),
                    "high_school": w.get("high_school"),
                    "previous_school": w.get("previous_school"),
                    "team_name": team_name,
                }
    return out


def normalize(s):
    return (s or "").strip().lower()


def main():
    parser = argparse.ArgumentParser(description="Cross-reference NCAA transfer candidates with hometown/high_school data")
    parser.add_argument("--season", type=int, required=True, help="New season year (e.g. 2026)")
    parser.add_argument("--anchor-season", type=int, default=None, help="Anchor season year (default: season - 1)")
    args = parser.parse_args()

    anchor_season = args.anchor_season or (args.season - 1)
    report_path = REPORT_DIR / f"ncaa_men_transfer_candidates_{args.season}.json"
    candidates = json.loads(report_path.read_text())

    new_lookup = load_wrestler_lookup(args.season)
    anchor_lookup = load_wrestler_lookup(anchor_season)
    careers = {}
    for f in CAREERS_DIR.glob("career_*.json"):
        career = json.loads(f.read_text())
        careers[career["career_id"]] = career

    confirmed, contradicted, unknown = [], [], []

    for cand in candidates:
        new_info = new_lookup.get(cand["new_season_wrestler_id"], {})
        career = careers.get(cand["candidate_career_id"])
        if not career:
            unknown.append((cand, "career not found"))
            continue
        anchor_wid = career.get("seasons", {}).get(str(anchor_season))
        old_info = anchor_lookup.get(anchor_wid, {}) if anchor_wid else {}

        new_home_raw, old_home_raw = new_info.get("hometown"), old_info.get("hometown")
        new_hs_raw, old_hs_raw = new_info.get("high_school"), old_info.get("high_school")
        new_home, old_home = normalize_hometown(new_home_raw), normalize_hometown(old_home_raw)
        new_hs, old_hs = normalize_high_school(new_hs_raw), normalize_high_school(old_hs_raw)

        home_is_match = fuzzy_match(new_home, old_home)
        hs_is_match = hs_match(new_hs, old_hs)
        home_contradict = bool(new_home) and bool(old_home) and not home_is_match
        hs_contradict = bool(new_hs) and bool(old_hs) and not hs_is_match

        candidate_prior_team = normalize(cand["candidate_prior_team"])

        # previous_school: the new team's own roster naming the candidate's
        # prior team is a direct self-report, not an inference -- check it
        # against every "/"-separated prior school in case of multi-transfers
        # (e.g. "Oklahoma State / CSU Bakersfield").
        prev_school_raw = new_info.get("previous_school") or ""
        prev_schools = [normalize(s) for s in prev_school_raw.split("/")]
        prev_school_match = any(
            candidate_prior_team and (candidate_prior_team in s or s in candidate_prior_team)
            for s in prev_schools if s
        )

        # Confirmed (Cooper Shore et al.): some athletics sites reuse the
        # generic "Last School" label for transfer athletes, so it holds
        # the prior COLLEGE instead of an actual high school. Treat a
        # high_school value that names the candidate's prior team the same
        # way as previous_school.
        hs_names_prior_team = bool(new_hs) and candidate_prior_team and (
            candidate_prior_team in new_hs or new_hs in candidate_prior_team
        )

        entry = {
            **cand,
            "old_hometown": old_home_raw, "new_hometown": new_home_raw,
            "old_high_school": old_hs_raw, "new_high_school": new_hs_raw,
            "previous_school": prev_school_raw or None,
        }
        if prev_school_match:
            entry["confirm_reason"] = "previous_school"
            confirmed.append(entry)
        elif hs_names_prior_team:
            entry["confirm_reason"] = "high_school_names_prior_team"
            confirmed.append(entry)
        elif home_is_match or hs_is_match:
            entry["confirm_reason"] = "hometown" if home_is_match else "high_school"
            confirmed.append(entry)
        elif home_contradict and hs_contradict:
            contradicted.append(entry)
        else:
            unknown.append((entry, "insufficient hometown/high_school/previous_school data"))

    print(f"{'='*70}")
    print(f"CONFIRMED ({len(confirmed)})")
    print(f"{'='*70}")
    for c in confirmed:
        reason = c.get("confirm_reason", "?")
        detail = c.get("previous_school") if reason == "previous_school" else (
            c.get("new_high_school") if reason == "high_school_names_prior_team" else
            (c.get("new_hometown") if reason == "hometown" else c.get("new_high_school"))
        )
        print(f"  {c['name']:<25} {c['candidate_prior_team']:<20} -> {c['new_team']:<20} [{reason}: {detail}]")
        print(f"    python scripts/careers/merge_careers.py --keep {c['candidate_career_id']} "
              f"--merge {c['new_career_id']} --gender ncaa_men")

    print(f"\n{'='*70}")
    print(f"CONTRADICTED ({len(contradicted)}) -- hometown/high_school differ, likely NOT the same person")
    print(f"{'='*70}")
    for c in contradicted:
        print(f"  {c['name']:<25} {c['candidate_prior_team']:<20} -> {c['new_team']:<20}")
        print(f"    OLD: {c['old_hometown']!r} / {c['old_high_school']!r}")
        print(f"    NEW: {c['new_hometown']!r} / {c['new_high_school']!r}")

    print(f"\n{'='*70}")
    print(f"UNKNOWN ({len(unknown)}) -- not enough data, needs manual judgment")
    print(f"{'='*70}")
    for c, reason in unknown:
        print(f"  {c['name']:<25} {c['candidate_prior_team']:<20} -> {c['new_team']:<20} ({reason})")

    out_path = REPORT_DIR / f"ncaa_men_transfer_candidates_{args.season}_classified.json"
    out_path.write_text(json.dumps({
        "confirmed": confirmed,
        "contradicted": contradicted,
        "unknown": [c for c, _ in unknown],
    }, indent=2, ensure_ascii=False))
    print(f"\nFull classification written to {out_path}")


if __name__ == "__main__":
    main()
