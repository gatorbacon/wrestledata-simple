#!/usr/bin/env python3
"""
Link a new NCAA season onto existing careers (data/careers/ncaa_men/).

Unlike the HS linker (link_season_interactive.py), most of this problem is
solved for free: mt/data/roster_links/{team}/{season}.json (built by
scripts/analysis/match_official_rosters_to_trackwrestling.py) already maps
each TrackWrestling season_wrestler_id to a stable official-roster
player_id per team+season, and that player_id is confirmed stable across a
wrestler's seasons AT THE SAME SCHOOL. So the only real judgment call left
is transfers -- a wrestler who continues at a DIFFERENT school -- which this
script never auto-links; it only reports them for manual review via
scripts/careers/merge_careers.py (same "flag, don't guess" pattern already
established for HS name-change gotchas).

IMPORTANT -- lookback window, not just the immediate anchor season: matching
is NOT limited to careers whose most recent season is exactly --anchor-season
(usually new_season - 1). A wrestler who is fully absent from TrackWrestling
for one or more seasons -- redshirt, injury, personal leave, an Olympic-cycle
gap, not just the 2020/2021 COVID disruption -- has no entry in that one
specific anchor year, so anchor-only matching can never find them again: they
silently fall to Tier 3b ("no match anywhere") and get a permanently
disconnected duplicate career, with no flag left for a human to ever review.
This was confirmed and manually fixed for ~300 real wrestlers (2026-09-06
session) before this lookback logic was added -- see
data/career_linking_logs/ and memory for the investigation. Every not-yet-
linked-to-new_season career is instead matched against its OWN most recent
season, whatever year that is, as long as the gap is <= MAX_LOOKBACK_SEASONS.
Beyond that window a name+team coincidence becomes more plausible than a
real multi-year gap, so it's left for Tier 3b same as before.

Four tiers, most confident first:
  1. AUTO-LINK (same school, deterministic): new season's (team, player_id)
     matches (team, player_id) in ANY lookback-window season via
     roster_links -- most recent match wins.
  2. AUTO-LINK (same school, name fallback): wrestler has no roster_links
     match (official-roster coverage isn't 100%), but the same team + exact
     normalized name appears in a not-yet-linked career whose most recent
     season falls within the lookback window. A severe weight-class jump
     (>=3 classes, or crossing the heavyweight boundary) across a gap of
     MORE than one season downgrades this from auto-link to a flagged
     review candidate instead -- same real mistake this session caught by
     hand (an unconditional gap>1 same-team+name match is not automatically
     as safe as the adjacent-season case).
  3. NOT auto-linked -- reported only:
     a. Possible transfer: exact name match to a not-yet-linked career at a
        DIFFERENT school, within the lookback window. Printed for manual
        review/merge, never applied.
     b. Same-team match rejected only for a severe weight-class jump (see
        Tier 2 above) -- also printed for manual review, never applied.
  4. No match anywhere: assumed a new addition (freshman, JUCO transfer with
     no prior D1 record, etc.) -- a new career is created for them,
     mirroring the HS "no match -> auto-create" rule.

Usage:
  python scripts/careers/link_ncaa_season.py --season 2026 --anchor-season 2025
  python scripts/careers/link_ncaa_season.py --season 2026 --anchor-season 2025 --dry-run
"""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, Optional, Set, Tuple

TW_DIR = Path("mt/data/ncaa_men")
LINKS_DIR = Path("mt/data/roster_links")
CAREERS_DIR = Path("data/careers/ncaa_men")

# How many seasons back a not-yet-linked career's own last appearance may be
# and still be matched automatically. Beyond this, a name+team coincidence
# starts to become as plausible as a real gap (see Jake Smith / West
# Virginia, a confirmed same-team name collision found 2026-09-06), so it's
# left to fall through to a brand-new standalone career instead.
MAX_LOOKBACK_SEASONS = 5

# NCAA weight classes in order, for the Tier 2 weight-continuity safety check.
WEIGHT_CLASSES = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]
WEIGHT_INDEX = {w: i for i, w in enumerate(WEIGHT_CLASSES)}


def weight_jump_is_severe(wt_a, wt_b) -> bool:
    """True if two weight-class readings are implausible for one real career
    across a gap: a 3+ class jump, or a heavyweight/non-heavyweight boundary
    cross. Missing data on either side is NOT treated as severe -- there's
    nothing to contradict, so it doesn't block an otherwise-solid match."""
    try:
        wa, wb = int(wt_a), int(wt_b)
    except (TypeError, ValueError):
        return False
    if wa not in WEIGHT_INDEX or wb not in WEIGHT_INDEX:
        return False
    if (wa == 285) != (wb == 285):
        return True
    return abs(WEIGHT_INDEX[wa] - WEIGHT_INDEX[wb]) >= 3


def normalize_name(name: str) -> str:
    if not name:
        return ""
    return re.sub(r"\s+", " ", name.lower().strip())


# TW's own team_name field isn't always consistent year-to-year for the same
# program (confirmed: "Pennsylvania" in 2025 data, "Penn" in 2026 data) --
# without this, every Penn wrestler gets falsely flagged as a transfer.
TEAM_NAME_ALIASES = {
    "pennsylvania": "penn",
    "presbyterian college": "presbyterian",
    "siu edwardsville": "southern illinois edwardsville",
    "army west point": "army",
    "north dakota state": "north dakota state university",
    "nc state": "north carolina state",
    "binghamton": "binghamton university",
    "utah valley": "utah valley university",
}


def normalize_team_name(team_name: str) -> str:
    norm = normalize_name(team_name)
    return TEAM_NAME_ALIASES.get(norm, norm)


def generate_career_id(counter: int) -> str:
    return f"career_{counter:06d}"


def load_roster_links_for_year(year: int) -> Dict[Tuple[str, int], str]:
    """(team_slug, official_player_id) -> season_wrestler_id, for one TW year."""
    out = {}
    for team_dir in LINKS_DIR.iterdir():
        if not team_dir.is_dir():
            continue
        for season_file in team_dir.glob("*.json"):
            data = json.loads(season_file.read_text())
            if data.get("year") != year:
                continue
            for link in data.get("links", []):
                pid = link.get("player_id")
                wid = link.get("season_wrestler_id")
                if pid is not None and wid:
                    out[(data["team"], pid)] = wid
    return out


def load_tw_season(year: int) -> Dict[str, Dict]:
    """season_wrestler_id -> {name, team_name, weight_class}, for one TW year."""
    out = {}
    season_dir = TW_DIR / str(year)
    if not season_dir.exists():
        return out
    for team_file in season_dir.glob("*.json"):
        team_data = json.loads(team_file.read_text())
        team_name = team_data.get("team_name", "")
        for w in team_data.get("roster", []):
            wid = w.get("season_wrestler_id")
            if wid:
                out[wid] = {
                    "name": w.get("name", ""),
                    "team_name": team_name,
                    "weight_class": w.get("weight_class"),
                }
    return out


def load_careers() -> Dict[str, Dict]:
    careers = {}
    if CAREERS_DIR.exists():
        for f in CAREERS_DIR.glob("career_*.json"):
            career = json.loads(f.read_text())
            cid = career.get("career_id")
            if cid:
                careers[cid] = career
    return careers


def save_career(career: Dict):
    (CAREERS_DIR / f"{career['career_id']}.json").write_text(json.dumps(career, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="Link a new NCAA season onto existing careers")
    parser.add_argument("--season", type=int, required=True, help="New season year to link (e.g. 2026)")
    parser.add_argument("--anchor-season", type=int, required=True, help="Prior season already in careers (e.g. 2025)")
    parser.add_argument("--dry-run", action="store_true", help="Report only, don't write any career files")
    args = parser.parse_args()

    new_season, anchor_season = args.season, args.anchor_season

    careers = load_careers()
    print(f"Loaded {len(careers)} existing careers")

    print(f"Loading roster_links + TW roster data for {new_season}...")
    new_links = load_roster_links_for_year(new_season)
    new_tw = load_tw_season(new_season)
    wid_to_team_pid = {wid: (team, pid) for (team, pid), wid in new_links.items()}

    # Every not-yet-linked-to-new_season career, matched against its OWN most
    # recent season (not necessarily anchor_season) -- as long as the gap is
    # within MAX_LOOKBACK_SEASONS. See module docstring for why this can't be
    # narrowed to just anchor_season without silently missing real gaps.
    candidate_careers = []  # (career_id, last_season:int, wid)
    for cid, career in careers.items():
        seasons_dict = career.get("seasons", {})
        if not seasons_dict or str(new_season) in seasons_dict:
            continue
        last_season = max(int(s) for s in seasons_dict)
        gap = new_season - last_season
        if 1 <= gap <= MAX_LOOKBACK_SEASONS:
            candidate_careers.append((cid, last_season, seasons_dict[str(last_season)]))

    lookback_years = sorted({ls for _, ls, _ in candidate_careers}, reverse=True)
    print(f"Lookback years needed (gap 1-{MAX_LOOKBACK_SEASONS} from {new_season}): {lookback_years or '(none)'}")

    tw_by_year = {y: load_tw_season(y) for y in lookback_years}
    links_by_year = {y: load_roster_links_for_year(y) for y in lookback_years}
    teampid_to_wid_by_year = {
        y: {(team, pid): wid for (team, pid), wid in links_by_year[y].items()}
        for y in lookback_years
    }

    # (season_year, wid) -> career_id, and name_norm -> [(career_id, team_name, weight_class, season_year), ...]
    wid_year_to_career: Dict[Tuple[int, str], str] = {}
    name_index: Dict[str, list] = defaultdict(list)
    for cid, last_season, wid in candidate_careers:
        info = tw_by_year.get(last_season, {}).get(wid)
        if not info:
            continue  # candidate wid not found in that year's TW data -- shouldn't normally happen
        wid_year_to_career[(last_season, wid)] = cid
        name_index[careers[cid]["name_norm"]].append((cid, info["team_name"], info.get("weight_class"), last_season))

    max_career_num = max((int(cid.replace("career_", "")) for cid in careers), default=0)

    # wids already linked to new_season by a prior run of this script (any
    # tier, including a tier-3 standalone career) -- reprocessing them would
    # re-flag already-resolved transfer candidates or double-create careers.
    new_season_already_linked: Set[str] = {
        wid for career in careers.values()
        for season, wid in career.get("seasons", {}).items()
        if season == str(new_season)
    }

    tier1 = tier2 = tier3_transfer = tier3_weight_flag = tier3_new = 0
    transfer_report = []
    already_linked = 0

    for wid_new, info in new_tw.items():
        if wid_new in new_season_already_linked:
            already_linked += 1
            continue

        name_new = info["name"]
        team_new = info["team_name"]
        weight_new = info.get("weight_class")
        name_norm_new = normalize_name(name_new)

        # Find this wrestler's official player_id + team_slug in the new season, if any
        team_slug_new, pid_new = wid_to_team_pid.get(wid_new, (None, None))

        # Tier 1: deterministic (team, player_id) continuation, checked across
        # every lookback year, most recent first (a wrestler stays the same
        # official player_id at the same school across any gap).
        linked = False
        if team_slug_new is not None and pid_new is not None:
            for y in lookback_years:
                candidate_wid = teampid_to_wid_by_year[y].get((team_slug_new, pid_new))
                if candidate_wid is None:
                    continue
                cid = wid_year_to_career.get((y, candidate_wid))
                if cid and str(new_season) not in careers[cid].get("seasons", {}):
                    careers[cid]["seasons"][str(new_season)] = wid_new
                    tier1 += 1
                    linked = True
                    break
        if linked:
            continue

        # Tier 2: same-team exact-name fallback (covers official-roster
        # coverage gaps), across every lookback year.
        candidates = name_index.get(name_norm_new, [])
        same_team_candidates = [c for c in candidates if normalize_team_name(c[1]) == normalize_team_name(team_new)]
        if len(same_team_candidates) == 1:
            cid, old_team, old_weight, old_season = same_team_candidates[0]
            gap = new_season - old_season
            # An adjacent-season (gap=1) same-team+name match has always been
            # auto-linked unconditionally. A wider gap is new territory this
            # lookback window opens up, and a severe weight-class jump across
            # it is exactly the failure mode that produced a real bad merge
            # this session (Jake Smith / West Virginia) -- flag it for review
            # instead of guessing.
            if gap > 1 and weight_jump_is_severe(old_weight, weight_new):
                max_career_num += 1
                new_cid = generate_career_id(max_career_num)
                careers[new_cid] = {
                    "career_id": new_cid,
                    "canonical_name": name_new,
                    "name_norm": name_norm_new,
                    "created_from_season": new_season,
                    "seasons": {str(new_season): wid_new},
                    "notes": None,
                }
                transfer_report.append({
                    "reason": "same_team_weight_jump",
                    "name": name_new,
                    "new_team": team_new,
                    "new_weight": weight_new,
                    "new_season_wrestler_id": wid_new,
                    "new_career_id": new_cid,
                    "candidate_career_id": cid,
                    "candidate_prior_team": old_team,
                    "candidate_prior_weight": old_weight,
                    "candidate_prior_season": old_season,
                    "gap_years": gap,
                })
                tier3_weight_flag += 1
                continue
            careers[cid]["seasons"][str(new_season)] = wid_new
            tier2 += 1
            continue

        # Both tier 3 branches get a standalone new career -- a flagged
        # transfer candidate still needs SOME career record representing
        # their new-season appearance, so review_ncaa_transfer_candidates.py
        # (or a manual merge_careers.py call) has a real career_id to merge
        # into the candidate, rather than leaving them unrepresented until a
        # human decides.
        max_career_num += 1
        new_cid = generate_career_id(max_career_num)
        careers[new_cid] = {
            "career_id": new_cid,
            "canonical_name": name_new,
            "name_norm": name_norm_new,
            "created_from_season": new_season,
            "seasons": {str(new_season): wid_new},
            "notes": None,
        }

        # Tier 3a: possible transfer -- exact name match at a DIFFERENT team,
        # anywhere within the lookback window.
        diff_team_candidates = [c for c in candidates if normalize_team_name(c[1]) != normalize_team_name(team_new)]
        if diff_team_candidates:
            for cid, old_team, old_weight, old_season in diff_team_candidates:
                transfer_report.append({
                    "reason": "transfer",
                    "name": name_new,
                    "new_team": team_new,
                    "new_weight": weight_new,
                    "new_season_wrestler_id": wid_new,
                    "new_career_id": new_cid,
                    "candidate_career_id": cid,
                    "candidate_prior_team": old_team,
                    "candidate_prior_weight": old_weight,
                    "candidate_prior_season": old_season,
                    "gap_years": new_season - old_season,
                })
            tier3_transfer += 1
            continue

        # Tier 3b: no match anywhere -- new career stands on its own
        tier3_new += 1

    print(f"\n{'='*70}")
    print(f"LINK SUMMARY: {new_season} onto anchor {anchor_season} (lookback up to {MAX_LOOKBACK_SEASONS} seasons)")
    print(f"{'='*70}")
    print(f"Already linked (prior run):             {already_linked}")
    print(f"Tier 1 (same school, player_id match):  {tier1}")
    print(f"Tier 2 (same school, name fallback):    {tier2}")
    print(f"Tier 3a (possible transfer -- flagged, standalone career created): {tier3_transfer}")
    print(f"Tier 3  (same-team but severe weight jump -- flagged instead of auto-linked): {tier3_weight_flag}")
    print(f"Tier 3b (no match -- new career created): {tier3_new}")
    print(f"Total new-season wrestlers processed: {len(new_tw)}")

    if transfer_report:
        report_path = Path(f"data/career_linking_logs/ncaa_men_transfer_candidates_{new_season}.json")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        if not args.dry_run:
            report_path.write_text(json.dumps(transfer_report, indent=2, ensure_ascii=False))
        print(f"\n{len(transfer_report)} flagged candidates (transfers + weight-jump same-team) written to {report_path}")
        print("Review these manually and merge with scripts/careers/merge_careers.py --gender ncaa_men if confirmed:")
        for t in transfer_report[:20]:
            print(f"  [{t['reason']}] {t['name']:<25} {t['candidate_prior_team']:<20} -> {t['new_team']:<20} (candidate: {t['candidate_career_id']}, gap={t['gap_years']})")
        if len(transfer_report) > 20:
            print(f"  ... and {len(transfer_report) - 20} more (see report file)")

    if not args.dry_run:
        for career in careers.values():
            save_career(career)
        print(f"\nSaved {len(careers)} career files to {CAREERS_DIR}")
    else:
        print("\n[DRY RUN] No files written")


if __name__ == "__main__":
    main()
