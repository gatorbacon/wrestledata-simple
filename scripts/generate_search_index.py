#!/usr/bin/env python3
"""
Generate search_index.js for global site search.

This script reads wrestler and team index files and creates a JavaScript
file with searchable data for Fuse.js autocomplete.

Supports both NCAA and HS modes.

For HS, wrestlers are indexed from career profiles (one entry per career),
prioritized as:
  0 = ranked in current season (sorted by rank ascending)
  1 = unranked but active in current season
  2 = historical / graduated (sorted by career wins descending)
Teams are filtered to KY-only schools (those with a team profile page).
"""

import argparse
import json
import re
from pathlib import Path


def slug_to_name(slug):
    """Convert team slug to display name."""
    return slug.replace('_', ' ').title()


def generate_search_tokens(name, for_wrestler=False):
    """Generate search tokens from a name."""
    tokens = set()
    name_lower = name.lower()
    tokens.update(name_lower.split())
    if for_wrestler:
        return sorted(list(tokens))
    return sorted(list(tokens))


def team_slug_to_url(team_slug, gender=None):
    if gender:
        return f"/team.html?team={team_slug}&gender={gender}"
    return f"/team.html?team={team_slug}"


def wrestler_id_to_url(wrestler_id, gender=None):
    if gender:
        return f"/wrestler.html?id={wrestler_id}&gender={gender}"
    return f"/wrestler.html?id={wrestler_id}"


def career_id_to_url(career_id, gender=None):
    if gender:
        return f"/wrestler.html?career_id={career_id}&gender={gender}"
    return f"/wrestler.html?career_id={career_id}"


def load_boys_inactive_mask(script_dir, season):
    mask_file = script_dir / f"mt/rankings_data/hs_ky_boys/{season}/boys_inactive_wrestlers.json"
    if not mask_file.exists():
        return set()
    try:
        with open(mask_file, 'r', encoding='utf-8') as f:
            mask_data = json.load(f)
        return {str(w.get("boys_wrestler_id")) for w in mask_data.get("masked_wrestlers", []) if w.get("boys_wrestler_id")}
    except Exception as e:
        print(f"Warning: Could not load boys inactive mask: {e}")
        return set()


def load_ky_team_slugs(script_dir, gender, season):
    """Return set of slugs for teams with actual KY team profile pages."""
    team_profiles_dir = script_dir / f"frontend/hs-ky-ui/public/data/teams/{gender}/{season}"
    if not team_profiles_dir.exists():
        return set()
    return {p.stem for p in team_profiles_dir.glob("*.json")}


def load_hs_search_items(script_dir, gender, season):
    """Build search items from career profiles + team profiles."""
    careers_dir = script_dir / f"frontend/hs-ky-ui/public/data/careers/{gender}"
    wrestlers_index_path = script_dir / f"frontend/hs-ky-ui/public/data/wrestlers/{gender}/{season}/index_wrestlers.json"

    search_items = []

    # --- Build rank/weight lookup from current season index ---
    rank_map = {}   # wrestler_id -> current_rank
    weight_map = {} # wrestler_id -> weight_class
    team_map = {}   # wrestler_id -> team name
    masked_ids = set()
    if gender == 'boys':
        masked_ids = load_boys_inactive_mask(script_dir, season)

    if wrestlers_index_path.exists():
        with open(wrestlers_index_path, 'r', encoding='utf-8') as f:
            wrestlers_index = json.load(f)
        for w in wrestlers_index:
            wid = str(w.get('wrestler_id', ''))
            if wid:
                rank_map[wid] = w.get('current_rank')
                weight_map[wid] = w.get('weight_class')
                team_map[wid] = w.get('team', '')
    print(f"  Loaded {len(rank_map)} wrestlers from {season} index")

    # --- Load KY team slugs for team search ---
    ky_team_slugs = load_ky_team_slugs(script_dir, gender, season)
    print(f"  Found {len(ky_team_slugs)} KY team profiles")

    # --- Build wrestler entries from career profiles (or index fallback) ---
    career_files = sorted(careers_dir.glob("career_*.json")) if careers_dir.exists() else []

    if not career_files:
        print(f"  No career profiles found — falling back to {season} index")
        if wrestlers_index_path.exists():
            with open(wrestlers_index_path, 'r', encoding='utf-8') as f:
                wrestlers_index = json.load(f)
            for w in wrestlers_index:
                wid = str(w.get('wrestler_id', ''))
                name = w.get('name', '')
                if not wid or not name:
                    continue
                team = w.get('team', '')
                weight = w.get('weight_class')
                rank = w.get('current_rank')
                secondary_parts = []
                if team:
                    secondary_parts.append(team)
                if weight:
                    secondary_parts.append(str(weight))
                name_parts = name.split()
                search_items.append({
                    "type": "wrestler",
                    "name": name,
                    "first_name": name_parts[0] if name_parts else '',
                    "last_name": ' '.join(name_parts[1:]) if len(name_parts) > 1 else '',
                    "secondary": " · ".join(secondary_parts),
                    "url": wrestler_id_to_url(wid, gender),
                    "searchTokens": generate_search_tokens(name, for_wrestler=True),
                    "rank": rank,
                    "gender": gender,
                    "priority": 0 if rank else 1,
                    "sort_key": rank if rank else 0,
                })
            search_items.sort(key=lambda e: (e['priority'], e['sort_key']))
            for item in search_items:
                item.pop('sort_key', None)
            print(f"  Wrestlers: {len(search_items)} from index")
    else:
        print(f"  Processing {len(career_files)} career profiles...")

    for cf in career_files:
        try:
            with cf.open(encoding='utf-8') as f:
                career = json.load(f)
        except Exception:
            continue

        career_id = career.get('career_id')
        name = career.get('canonical_name', '')
        if not career_id or not name:
            continue

        seasons = career.get('seasons', [])
        if not seasons:
            continue

        cr = career.get('career_record', {})
        career_wins = cr.get('wins', 0)
        career_losses = cr.get('losses', 0)
        win_pct = cr.get('win_pct', 0.0)

        # Find the 2026 season entry (active wrestler)
        active_season = next((s for s in seasons if s['season'] == season), None)

        if active_season:
            wrestler_id = str(active_season.get('wrestler_id', ''))
            # Skip masked (inactive) wrestlers
            if masked_ids and wrestler_id in masked_ids:
                continue

            team = active_season.get('team', '') or team_map.get(wrestler_id, '')
            weight = active_season.get('weight_class') or weight_map.get(wrestler_id)
            rank = rank_map.get(wrestler_id)

            secondary_parts = []
            if team:
                secondary_parts.append(team)
            if weight:
                secondary_parts.append(f"{weight}")
            secondary = " · ".join(secondary_parts)

            if rank:
                priority = 0
                sort_key = rank
            else:
                priority = 1
                sort_key = 0
        else:
            # Historical / graduated wrestler
            wrestler_id = ''
            most_recent = seasons[0]  # already sorted newest first
            team = most_recent.get('team', '')
            priority = 2
            sort_key = -(career_wins)  # higher wins = lower sort_key value = earlier

            secondary_parts = []
            if team:
                secondary_parts.append(team)
            if career_wins or career_losses:
                secondary_parts.append(f"{career_wins}-{career_losses}")
            secondary = " · ".join(secondary_parts)

        name_parts = name.split()
        first_name = name_parts[0] if name_parts else ''
        last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''

        search_items.append({
            "type": "wrestler",
            "name": name,
            "first_name": first_name,
            "last_name": last_name,
            "secondary": secondary,
            "url": career_id_to_url(career_id, gender),
            "searchTokens": generate_search_tokens(name, for_wrestler=True),
            "rank": rank_map.get(wrestler_id) if active_season else None,
            "gender": gender,
            "priority": priority,
            "sort_key": sort_key,
        })

    if career_files:
        # Sort: ranked active first (by rank asc), then unranked active, then historical (by career wins desc)
        search_items.sort(key=lambda e: (e['priority'], e['sort_key']))
        for item in search_items:
            del item['sort_key']
        active_count = sum(1 for e in search_items if e['priority'] <= 1)
        historical_count = sum(1 for e in search_items if e['priority'] == 2)
        print(f"  Wrestlers: {active_count} active ({season}), {historical_count} historical")

    # --- Build team entries (KY only) ---
    teams_index_path = script_dir / f"frontend/hs-ky-ui/public/data/wrestlers/{gender}/{season}/index_teams.json"
    if teams_index_path.exists():
        with open(teams_index_path, 'r', encoding='utf-8') as f:
            all_teams = json.load(f)

        team_count = 0
        for team_data in all_teams:
            team_name = team_data.get('team', '')
            team_slug = team_data.get('team_slug', '')
            if not team_slug or team_slug not in ky_team_slugs:
                continue

            search_items.append({
                "type": "team",
                "name": team_name,
                "secondary": "KY HS",
                "url": team_slug_to_url(team_slug, gender),
                "searchTokens": generate_search_tokens(team_name),
                "gender": gender,
                "priority": 3,
            })
            team_count += 1
        print(f"  Teams: {team_count} KY schools")

    return search_items


def main():
    parser = argparse.ArgumentParser(description="Generate search_index.js for site search")
    parser.add_argument("-league", choices=["ncaa", "hs"], default="ncaa")
    parser.add_argument("-gender", choices=["boys", "girls", "both"],
                        help="Gender for HS (required if league=hs)")
    parser.add_argument("-season", type=int, default=2026)
    args = parser.parse_args()

    if args.league == 'hs' and not args.gender:
        parser.error("-gender is required when -league=hs")

    script_dir = Path(__file__).parent.parent
    search_index = []

    if args.league == 'hs':
        if args.gender == 'both':
            for g in ['boys', 'girls']:
                print(f"\nLoading {g} data...")
                search_index.extend(load_hs_search_items(script_dir, g, args.season))
        else:
            print(f"Loading {args.gender} data...")
            search_index.extend(load_hs_search_items(script_dir, args.gender, args.season))

        output_file = script_dir / "frontend/hs-ky-ui/public/search_index.js"

    else:  # ncaa — unchanged logic
        wrestlers_index = script_dir / f"frontend/wrestledata-ui/public/wrestlers/{args.season}/index_wrestlers.json"
        teams_index = script_dir / f"frontend/wrestledata-ui/public/wrestlers/{args.season}/index_teams.json"
        output_file = script_dir / "frontend/wrestledata-ui/public/search_index.js"

        print(f"Loading wrestlers from {wrestlers_index}...")
        if not wrestlers_index.exists():
            print(f"Error: {wrestlers_index} not found")
            return

        with open(wrestlers_index, 'r', encoding='utf-8') as f:
            wrestlers = json.load(f)
        for wrestler in wrestlers:
            name = wrestler.get('name', 'Unknown')
            team = wrestler.get('team', 'Unknown')
            weight = wrestler.get('weight_class')
            wrestler_id = wrestler.get('wrestler_id')
            if not wrestler_id:
                continue
            secondary_parts = []
            if team:
                secondary_parts.append(team)
            if weight:
                secondary_parts.append(str(weight))
            name_parts = name.split()
            search_index.append({
                "type": "wrestler",
                "name": name,
                "first_name": name_parts[0] if name_parts else "",
                "last_name": " ".join(name_parts[1:]) if len(name_parts) > 1 else "",
                "secondary": " · ".join(secondary_parts),
                "url": wrestler_id_to_url(wrestler_id),
                "searchTokens": generate_search_tokens(name, for_wrestler=True),
            })

        if teams_index.exists():
            with open(teams_index, 'r', encoding='utf-8') as f:
                teams = json.load(f)
            for team_data in teams:
                team_name = team_data.get('team', 'Unknown')
                team_slug = team_data.get('team_slug', '')
                if not team_slug:
                    continue
                search_index.append({
                    "type": "team",
                    "name": team_name,
                    "secondary": "D1",
                    "url": team_slug_to_url(team_slug),
                    "searchTokens": generate_search_tokens(team_name, team_slug=team_slug),
                })

    print(f"\nTotal items: {len(search_index)}")
    print(f"Writing to {output_file}...")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("// Search index for WrestleData global search\n")
        f.write("// Generated automatically - do not edit manually\n\n")
        f.write("window.SEARCH_INDEX = ")
        json.dump(search_index, f, indent=2, ensure_ascii=False)
        f.write(";\n")

    print("✓ Search index generated successfully!")


if __name__ == "__main__":
    main()
