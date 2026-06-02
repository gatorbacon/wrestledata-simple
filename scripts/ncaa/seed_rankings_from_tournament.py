#!/usr/bin/env python3
"""
Seed NCAA rankings from tournament results.

Reads tournament results from simulation_replay.json (33 qualifiers per weight
class) and matches each tournament wrestler to a TrackWrestling wrestler ID via
auto-matching (difflib) + interactive fallback. Saves the match map to
tournament_id_map.json so reruns skip already-resolved wrestlers.

Top 33 are sorted by tournament points (actual) descending, ties broken by seed
(lower seed = higher rank). Non-qualifiers are appended sorted by win%.

Output: mt/rankings_data/ncaa_{gender}/{season}/rankings_{weight}.json
Map:    mt/rankings_data/ncaa_{gender}/{season}/tournament_id_map.json

Usage:
  python scripts/ncaa/seed_rankings_from_tournament.py -season 2026 -gender men
"""

import argparse
import difflib
import json
import sys
from pathlib import Path

NCAA_WEIGHTS = ['125', '133', '141', '149', '157', '165', '174', '184', '197', '285']
NCAA_WEIGHTS_157_UP = ['157', '165', '174', '184', '197', '285']


def normalize(s: str) -> str:
    return s.lower().strip()


def norm_team(team: str) -> str:
    """Normalize team name for fuzzy comparison."""
    return normalize(team).replace('state', 'st').replace('university', 'u').replace('  ', ' ')


def match_score(tourney_name: str, tourney_team: str, tw_name: str, tw_team: str) -> float:
    name_score = difflib.SequenceMatcher(None, normalize(tourney_name), normalize(tw_name)).ratio()
    team_score = difflib.SequenceMatcher(None, norm_team(tourney_team), norm_team(tw_team)).ratio()
    return 0.7 * name_score + 0.3 * team_score


def find_best_match(tourney_name: str, tourney_team: str, wrestlers: dict, threshold: float = 0.80):
    """Return (wrestler_id, score) or (None, 0) if no match above threshold."""
    best_id = None
    best_score = 0.0
    for wid, w in wrestlers.items():
        score = match_score(tourney_name, tourney_team, w['name'], w['team'])
        if score > best_score:
            best_score = score
            best_id = wid
    if best_score >= threshold:
        return best_id, best_score
    return None, best_score


def search_wrestlers(wrestlers: dict, query: str):
    query_lower = query.lower()
    return [
        w for w in wrestlers.values()
        if query_lower in w['name'].lower() or query_lower in w['team'].lower()
    ]


def interactive_lookup(tourney_name: str, tourney_team: str, wrestlers: dict):
    """Interactively search for a wrestler by name fragment. Returns wrestler_id or None."""
    print(f"\n  Could not auto-match: '{tourney_name}' ({tourney_team})")
    print("  Enter a name fragment to search (blank to skip this wrestler):")

    while True:
        try:
            fragment = input("    Search: ").strip()
        except EOFError:
            return None
        if not fragment:
            return None

        results = search_wrestlers(wrestlers, fragment)
        if not results:
            print("    No matches found. Try again.")
            continue

        for i, w in enumerate(results, 1):
            rec = f"{w['wins']}-{w['losses']}"
            print(f"    {i:>2}) {w['name']} ({w['team']}) [{w['weight_class']}] {rec}")

        while True:
            try:
                sel = input("    Select number (blank to search again): ").strip()
            except EOFError:
                return None
            if not sel:
                break
            try:
                idx = int(sel)
                if 1 <= idx <= len(results):
                    return results[idx - 1]['id']
            except ValueError:
                pass
            print("    Invalid selection.")


def load_tournament_data(season: int) -> dict:
    path = Path(f"frontend/wrestledata-ui/public/data/{season}/simulation_replay.json")
    if not path.exists():
        raise FileNotFoundError(f"Tournament data not found: {path}")
    with open(path) as f:
        data = json.load(f)
    return data['wrestlers']


def load_weight_class_data(base_dir: Path, weight: str) -> dict:
    # Prefer relationships file — it contains all wrestlers who actually competed
    # at this weight (including those whose primary weight class is different).
    rel_path = base_dir / f"relationships_{weight}.json"
    if rel_path.exists():
        with open(rel_path) as f:
            rel = json.load(f)
        wrestlers = rel.get('wrestlers', {})
        if wrestlers:
            return {wid: w for wid, w in wrestlers.items()}

    # Fallback: weight_class file filtered by weight
    path = base_dir / f"weight_class_{weight}.json"
    if not path.exists():
        raise FileNotFoundError(f"Weight class data not found: {path}")
    with open(path) as f:
        data = json.load(f)
    wrestlers = data.get('wrestlers', data)
    return {
        wid: w for wid, w in wrestlers.items()
        if w.get('weight_class') == weight
    }


def load_id_map(map_path: Path) -> dict:
    if map_path.exists():
        with open(map_path) as f:
            return json.load(f)
    return {}


def save_id_map(map_path: Path, id_map: dict) -> None:
    map_path.parent.mkdir(parents=True, exist_ok=True)
    with open(map_path, 'w') as f:
        json.dump(id_map, f, indent=2)


def load_elo_by_id(base_dir: Path) -> dict:
    """Load ELO ratings into a dict keyed by wrestler_id. Returns {} if file missing."""
    elo_path = base_dir.parent.parent.parent / "elo_ratings" / base_dir.parent.name / base_dir.name / "elo_ratings.json"
    # Canonical path: mt/elo_ratings/ncaa_men/2026/elo_ratings.json
    # base_dir is:     mt/rankings_data/ncaa_men/2026
    alt_path = Path(str(base_dir).replace("rankings_data", "elo_ratings").rstrip("/"))
    elo_path = alt_path / "elo_ratings.json"
    if not elo_path.exists():
        return {}
    with open(elo_path) as f:
        entries = json.load(f)
    return {e['wrestler_id']: e for e in entries}


def build_rankings_for_weight(
    weight: str,
    tourney_wrestlers: dict,
    tw_wrestlers: dict,
    id_map: dict,
    map_path: Path,
    season: int,
    elo_by_id: dict = None,
    dry_run: bool = False,
) -> list:
    """
    Returns a list of ranking dicts sorted: qualifiers first (by points/seed),
    then non-qualifiers (by win%).
    """
    qualifiers = []  # (seed_int, actual_pts, wrestler_id, name, team)

    # Map key for this weight
    weight_key = f"weight_{weight}"
    if weight_key not in id_map:
        id_map[weight_key] = {}
    weight_map = id_map[weight_key]

    any_interactive = False

    for seed_str, tw_data in tourney_wrestlers.items():
        seed = int(seed_str)
        t_name = tw_data['name']
        t_team = tw_data['team']
        actual = tw_data['actual']

        map_key = f"{t_name}|{t_team}"

        if map_key in weight_map:
            wid = weight_map[map_key]
        else:
            wid, score = find_best_match(t_name, t_team, tw_wrestlers)
            if wid is not None:
                print(f"  Auto-matched [{weight}] seed {seed:>2}: {t_name} ({t_team}) "
                      f"→ {tw_wrestlers[wid]['name']} ({tw_wrestlers[wid]['team']}) score={score:.2f}")
            else:
                if not dry_run:
                    wid = interactive_lookup(t_name, t_team, tw_wrestlers)
                    any_interactive = True
                if wid is None:
                    print(f"  SKIPPED (no match): [{weight}] seed {seed}: {t_name} ({t_team})")
                    continue
            weight_map[map_key] = wid
            if not dry_run:
                save_id_map(map_path, id_map)

        w = tw_wrestlers.get(wid, {})
        qualifiers.append({
            'seed': seed,
            'actual': actual,
            'wrestler_id': wid,
            'name': w.get('name', t_name),
            'team': w.get('team', t_team),
            'wins': w.get('wins', 0),
            'losses': w.get('losses', 0),
        })

    # Sort qualifiers: pts desc, then seed asc (lower seed = better tie-break)
    qualifiers.sort(key=lambda x: (-x['actual'], x['seed']))

    qualifier_ids = {q['wrestler_id'] for q in qualifiers}

    # Non-qualifiers split into tiers so 0-0 wrestlers always land at the bottom.
    # Tier B: at least 1 win   → sorted by ELO (or win%) desc
    # Tier C: 0 wins, >0 losses → sorted by ELO (or win%) desc, below Tier B
    # Tier D: 0-0 (no matches)  → absolute bottom
    tier_b, tier_c, tier_d = [], [], []
    for wid, w in tw_wrestlers.items():
        if wid in qualifier_ids:
            continue
        wins = w.get('wins', 0)
        losses = w.get('losses', 0)
        matches = w.get('matches_count', wins + losses)
        if matches == 0:
            tier_d.append(w)
        elif wins == 0:
            tier_c.append(w)
        else:
            tier_b.append(w)

    def sort_key(w):
        if elo_by_id:
            return -(elo_by_id.get(w['id'], {}).get('elo_score', 1500))
        wins = w.get('wins', 0)
        losses = w.get('losses', 0)
        return -(wins / max(wins + losses, 1))

    tier_b.sort(key=sort_key)
    tier_c.sort(key=sort_key)
    tier_d.sort(key=sort_key)
    non_qualifiers = tier_b + tier_c + tier_d

    rankings = []
    rank = 1
    for q in qualifiers:
        rankings.append({
            'rank': rank,
            'wrestler_id': q['wrestler_id'],
            'name': q['name'],
            'team': q['team'],
            'record': f"{q['wins']}-{q['losses']}",
            'tournament_points': q['actual'],
            'seed': q['seed'],
            'is_starter': True,
        })
        rank += 1

    for w in non_qualifiers:
        rankings.append({
            'rank': rank,
            'wrestler_id': w['id'],
            'name': w['name'],
            'team': w['team'],
            'record': f"{w['wins']}-{w['losses']}",
            'tournament_points': None,
            'seed': None,
            'is_starter': False,
        })
        rank += 1

    return rankings


def write_rankings(output_path: Path, weight: str, season: int, rankings: list) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        'weight_class': weight,
        'season': season,
        'rankings': rankings,
    }
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"  Wrote {len(rankings)} wrestlers → {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Seed NCAA rankings from tournament results."
    )
    parser.add_argument('-season', type=int, required=True, help='Season year (e.g., 2026)')
    parser.add_argument('-gender', type=str, default='men', choices=['men', 'women'],
                        help='Gender: men or women (default: men)')
    parser.add_argument('-weights', type=str, nargs='+', default=None,
                        help='Only process specific weight classes (e.g., -weights 125 133). '
                             'Defaults to 157+ to avoid overwriting manually-ranked lighter weights.')
    parser.add_argument('--all-weights', action='store_true',
                        help='Process all weight classes (overrides default 157+ restriction)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Auto-match only, no interactive prompts, no file writes')
    args = parser.parse_args()

    league_key = f"ncaa_{args.gender}"
    base_dir = Path(f"mt/rankings_data/{league_key}/{args.season}")
    map_path = base_dir / "tournament_id_map.json"

    if args.weights:
        weights_to_process = args.weights
    elif args.all_weights:
        weights_to_process = NCAA_WEIGHTS
    else:
        weights_to_process = NCAA_WEIGHTS_157_UP

    try:
        tourney_data = load_tournament_data(args.season)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    id_map = load_id_map(map_path)

    # Load ELO ratings once for non-qualifier sorting
    elo_by_id = load_elo_by_id(base_dir)
    if elo_by_id:
        print(f"Loaded ELO ratings for {len(elo_by_id)} wrestlers (non-qualifiers will be sorted by ELO).")
    else:
        print("No ELO file found — non-qualifiers will be sorted by win%.")

    for weight in weights_to_process:
        if weight not in tourney_data:
            print(f"[{weight}] No tournament data — skipping.")
            continue

        try:
            tw_wrestlers = load_weight_class_data(base_dir, weight)
        except FileNotFoundError as e:
            print(f"[{weight}] {e} — skipping.")
            continue

        print(f"\n=== Weight {weight} ({len(tw_wrestlers)} TW wrestlers) ===")

        rankings = build_rankings_for_weight(
            weight=weight,
            tourney_wrestlers=tourney_data[weight],
            tw_wrestlers=tw_wrestlers,
            id_map=id_map,
            map_path=map_path,
            season=args.season,
            elo_by_id=elo_by_id,
            dry_run=args.dry_run,
        )

        if not args.dry_run:
            output_path = base_dir / f"rankings_{weight}.json"
            write_rankings(output_path, weight, args.season, rankings)

        qualifier_count = sum(1 for r in rankings if r['is_starter'])
        print(f"  {qualifier_count} qualifiers matched, {len(rankings) - qualifier_count} non-qualifiers")

    print("\nDone.")


if __name__ == '__main__':
    main()
