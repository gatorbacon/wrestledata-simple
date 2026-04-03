#!/usr/bin/env python3
"""
Scan all career files and add name aliases to mt/name_alias.json for any season
where the wrestler's actual name differs from the career's canonical_name.

Run once to backfill existing data; safe to re-run (skips duplicates).
"""

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CAREERS_DIR = REPO_ROOT / "data" / "careers"
ALIAS_FILE = REPO_ROOT / "mt" / "name_alias.json"
ACC_ROOT = REPO_ROOT / "data" / "season_accomplishments"

# Genders to check (careers don't store gender; try both)
GENDERS = ["boys", "girls"]


def normalize_name(name: str) -> str:
    if not name:
        return ""
    return re.sub(r"\s+", " ", name.lower().strip())


def load_alias_file() -> dict:
    if ALIAS_FILE.exists():
        with ALIAS_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {"aliases": []}


def save_alias_file(data: dict) -> None:
    with ALIAS_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def build_acc_lookup(gender: str, season: int) -> dict:
    """Return wrestler_id -> name for a given gender/season."""
    path = ACC_ROOT / gender / str(season) / "season_accomplishments.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return {
        str(w["season_wrestler_id"]): w.get("name", "")
        for w in data.get("wrestlers", [])
        if w.get("season_wrestler_id")
    }


def main() -> None:
    # Pre-load all season accomplishment lookups
    acc_cache: dict[tuple, dict] = {}
    for gender in GENDERS:
        gender_dir = ACC_ROOT / gender
        if not gender_dir.exists():
            continue
        for season_dir in gender_dir.iterdir():
            if season_dir.is_dir() and season_dir.name.isdigit():
                season = int(season_dir.name)
                acc_cache[(gender, season)] = build_acc_lookup(gender, season)

    alias_data = load_alias_file()
    aliases = alias_data.setdefault("aliases", [])

    # Build fast lookup: canonical_norm -> alias entry index
    canonical_index: dict[str, int] = {
        normalize_name(e.get("canonical_name", "")): i
        for i, e in enumerate(aliases)
    }

    added = 0
    careers_checked = 0

    for career_file in sorted(CAREERS_DIR.glob("career_*.json")):
        with career_file.open("r", encoding="utf-8") as f:
            career = json.load(f)

        canonical_name = career.get("canonical_name") or ""
        if not canonical_name:
            continue
        canonical_norm = normalize_name(canonical_name)

        seasons: dict = career.get("seasons") or {}
        careers_checked += 1

        for season_str, wrestler_id in seasons.items():
            if not str(season_str).isdigit():
                continue
            season = int(season_str)
            wrestler_id = str(wrestler_id)

            # Try both genders (career files don't store gender)
            actual_name = ""
            for gender in GENDERS:
                lookup = acc_cache.get((gender, season), {})
                if wrestler_id in lookup:
                    actual_name = lookup[wrestler_id]
                    break

            if not actual_name:
                continue
            name_norm = normalize_name(actual_name)
            if name_norm == canonical_norm:
                continue  # Same name — no alias needed

            # Find or create alias entry
            if canonical_norm in canonical_index:
                entry = aliases[canonical_index[canonical_norm]]
                existing_variants = [normalize_name(v) for v in entry.get("name_variants", [])]
                if name_norm not in existing_variants:
                    entry.setdefault("name_variants", []).append(actual_name)
                    added += 1
            else:
                new_entry = {
                    "canonical_name": canonical_name,
                    "name_variants": [actual_name],
                    "notes": "Auto-added by backfill_career_aliases.py",
                }
                aliases.append(new_entry)
                canonical_index[canonical_norm] = len(aliases) - 1
                added += 1

    if added:
        save_alias_file(alias_data)
        print(f"✅ Added {added} new alias variant(s) across {careers_checked} careers → {ALIAS_FILE}")
    else:
        print(f"✅ No new aliases needed ({careers_checked} careers checked — all up to date)")


if __name__ == "__main__":
    main()
