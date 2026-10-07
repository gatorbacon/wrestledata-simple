#!/usr/bin/env python3
"""
build_preseason_team_rosters.py

KentuckyMat preseason team pages (docs/kentuckymat_preseason_rankings.md,
"Team", decided 2026-10-07): in the preseason a team page shows its RETURNING
wrestlers, not a projected lineup or projected state points (lineups aren't set
until wrestlers certify weights and replace graduated seniors).

Source of truth for who returns: the preseason rankings staging files
(mt/preseason_{season}/rankings_data/hs_ky_{gender}/{season}/rankings_{w}.json).
They are last season's full ranked order with seniors removed (and TJ's manual
removals, e.g. Naiya Delos Santos), so they list every returning wrestler who
had matches last season, at last season's weight.

Per returner:
  - grade: next year's (create_rankings_release.load_grade_lookup in preseason mode)
  - wins / losses / bonus_rate: last season (2026 team files, else the profile)
  - preseason_rank: only if inside the published drop (top 40 boys / 24 girls)
  Wrestlers who were 0-0 last season are left out (roster listings, not competitors).
  - state_note: last season's state result (1-8 / BR / Q) from placement_notes.json

Writes frontend/hs-ky-ui/public/data/teams/{gender}/{season}/{team_slug}.json for
every team that has a {season-1} team file (teams with no returners get an empty
list). team.js reads these only while hs_config.js says phase 'preseason'.

Usage:
    .venv/bin/python scripts/teams/build_preseason_team_rosters.py --season 2027 --gender both
"""
import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "rankings"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "teams"))

import create_rankings_release as crr  # noqa: E402
from build_team_profiles import slugify_team_name  # noqa: E402

PUBLIC = REPO_ROOT / "frontend" / "hs-ky-ui" / "public"
WEIGHTS = {"boys": crr.KY_HS_BOYS_WEIGHTS, "girls": crr.KY_HS_GIRLS_WEIGHTS}


def load_published_ranks(gender: str, season: int):
    """wrestler_id -> rank from the latest published drop of `season` (top 40/24 only)."""
    base = PUBLIC / "data" / "rankings" / gender / str(season)
    index = json.loads((base / "index.json").read_text())
    drop_id = index["latest"]
    ranks = {}
    for w in WEIGHTS[gender]:
        f = base / drop_id / f"{w}.json"
        if f.exists():
            for e in json.loads(f.read_text()).get("wrestlers", []):
                ranks[str(e["wrestler_id"])] = e["rank"]
    return drop_id, ranks


def build(gender: str, season: int) -> None:
    prev = season - 1
    src = REPO_ROOT / "mt" / f"preseason_{season}" / "rankings_data" / f"hs_ky_{gender}" / str(season)
    if not src.exists():
        raise SystemExit(f"Preseason staging not found: {src}")

    # Next year's grades (preseason mode reads last season and moves everyone up a year)
    crr.PRESEASON = True
    grades = crr.load_grade_lookup(season, gender)
    crr.PRESEASON = False

    notes = {}
    notes_file = src / "placement_notes.json"
    if notes_file.exists():
        for n in json.loads(notes_file.read_text()).get("notes", []):
            notes[str(n["wrestler_id"])] = str(n.get("note", "")).upper()

    drop_id, published = load_published_ranks(gender, season)

    # Last season's team files: slug + team name + per-wrestler record/bonus
    prev_dir = PUBLIC / "data" / "teams" / gender / str(prev)
    teams = {}          # team_name -> slug
    stats = {}          # wrestler_id -> (wins, losses, bonus_rate)
    for f in sorted(prev_dir.glob("*.json")):
        d = json.loads(f.read_text())
        if "starters" not in d:
            continue
        teams[d["team_name"]] = d.get("team_id") or f.stem
        for s in list((d.get("starters") or {}).values()) + (d.get("remaining") or []):
            if s:
                stats[str(s["wrestler_id"])] = (s.get("wins"), s.get("losses"), s.get("bonus_rate"))

    returning = {}      # slug -> list
    seen = set()
    missing_team = set()
    skipped_zero = 0
    for w in WEIGHTS[gender]:
        f = src / f"rankings_{w}.json"
        if not f.exists():
            continue
        for e in json.loads(f.read_text()).get("rankings", []):
            wid = str(e["wrestler_id"])
            if wid in seen:
                continue
            seen.add(wid)
            team = e.get("team") or ""
            slug = teams.get(team)
            if slug is None:
                slug = slugify_team_name(team)
                missing_team.add(team)
            wins, losses, bonus = stats.get(wid, (None, None, None))
            if wins is None:
                prof = crr.load_wrestler_profile(wid, prev, gender) or {}
                rec = crr.parse_record((prof.get("record") or {}).get("overall"))
                if rec:
                    wins, losses = rec["wins"], rec["losses"]
                bonus = (prof.get("metrics") or {}).get("bonus_rate")
            if not (wins or losses):
                # 0-0 last season: a roster listing, not a wrestler who competed
                # (TrackWrestling lists many who never wrestled; CLAUDE.md gotcha 13)
                skipped_zero += 1
                continue
            returning.setdefault(slug, []).append({
                "wrestler_id": wid,
                "name": e.get("name"),
                "weight": w,
                "grade": grades.get(wid) or None,
                "wins": wins,
                "losses": losses,
                "bonus_rate": bonus,
                "preseason_rank": published.get(wid),
                "state_note": notes.get(wid),
            })

    out_dir = PUBLIC / "data" / "teams" / gender / str(season)
    out_dir.mkdir(parents=True, exist_ok=True)
    names = {slug: name for name, slug in teams.items()}
    written = 0
    for slug in sorted(set(names) | set(returning)):
        rows = returning.get(slug, [])
        rows.sort(key=lambda r: (r["weight"], r["preseason_rank"] is None, r["preseason_rank"] or 0,
                                 -(r["wins"] or 0)))
        out = {
            "schema_version": "preseason-1",
            "season": season,
            "phase": "preseason",
            "record_season": prev,
            "gender": gender,
            "drop_id": drop_id,
            "team_id": slug,
            "team_name": names.get(slug) or slug,
            "returning": rows,
        }
        (out_dir / f"{slug}.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
        written += 1

    ranked = sum(1 for r in sum(returning.values(), []) if r["preseason_rank"] is not None)
    print(f"{gender} {season} preseason: {len(seen) - skipped_zero} returners on {len(returning)} teams "
          f"({ranked} in the published drop {drop_id}; {skipped_zero} 0-0 entries left out); "
          f"wrote {written} files to {out_dir}")
    if missing_team:
        print(f"  WARNING: {len(missing_team)} team(s) not in the {prev} team files "
              f"(slug guessed): {sorted(missing_team)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--season", type=int, required=True, help="The preseason's season (e.g. 2027)")
    ap.add_argument("--gender", choices=["boys", "girls", "both"], default="both")
    args = ap.parse_args()
    for g in (["boys", "girls"] if args.gender == "both" else [args.gender]):
        build(g, args.season)


if __name__ == "__main__":
    main()
