#!/usr/bin/env python3
"""
Import ranking-matrix saves from ~/Downloads into the rankings data folder.

The matrix's Save button (generate_matrix.py) downloads one file per save, named
    rankings_{gender}_{season}_{weight}_{YYYY-MM-DD_HHMMSS}.json
with `gender`, `season`, `weight_class` and `saved_at` inside. This script:

  1. finds the saves for one gender + season (any weight, including Chrome's
     "... (1).json" copies) and takes the NEWEST save per weight (by saved_at);
  2. checks each one: gender/season/weight inside the file match the name, no
     duplicate wrestlers, every wrestler is in that weight's relationships file
     (i.e. the matrix would show them), and nobody in the current
     rankings_{weight}.json is missing from the save;
  3. prints what moved in the published range (boys top 40, girls top 24) versus
     the current rankings_{weight}.json;
  4. unless --dry-run: backs up the current rankings_{weight}.json to
     rankings_archive/import_{timestamp}/, writes the save as rankings_{weight}.json,
     and moves every save file it looked at for that weight (the newest and any
     older ones) to ~/Downloads/kentuckymat_matrix_saves/{gender}_{season}/.

Older saves named just rankings_{weight}.json (before 2026-10-06) are not
imported -- their gender can't be told from the name -- and are listed as a warning.

Usage:
  # In season (writes mt/rankings_data/hs_ky_{gender}/{season}/)
  .venv/bin/python scripts/rankings/import_matrix_saves.py -season 2027 -gender girls --dry-run
  .venv/bin/python scripts/rankings/import_matrix_saves.py -season 2027 -gender girls

  # Preseason staging tree (docs/kentuckymat_preseason_rankings.md)
  .venv/bin/python scripts/rankings/import_matrix_saves.py -season 2027 -gender girls \\
      -data-dir mt/preseason_2027/rankings_data
"""

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_matrix import league_dir_key  # noqa: E402

PUBLISHED_SIZE = {'boys': 40, 'girls': 24}
SAVE_ARCHIVE_DIRNAME = 'kentuckymat_matrix_saves'


def find_saves(downloads: Path, gender: str, season: int):
    """Return {weight: [(path, data), ...]} for every matching save, plus problems."""
    pattern = re.compile(
        rf'^rankings_{re.escape(gender)}_{season}_(?P<w>[^_]+)_'
        r'\d{4}-\d{2}-\d{2}_\d{6}(?: \(\d+\))?\.json$'
    )
    by_weight, problems = {}, []
    for path in sorted(downloads.glob(f'rankings_{gender}_{season}_*.json')):
        m = pattern.match(path.name)
        if not m:
            continue
        weight = m.group('w')
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as e:
            problems.append(f'{path.name}: unreadable ({e})')
            continue
        mismatches = [
            f'{key}={data.get(key)!r}' for key, want in
            (('gender', gender), ('season', season), ('weight_class', weight))
            if str(data.get(key)) != str(want)
        ]
        if mismatches:
            problems.append(f'{path.name}: contents say {", ".join(mismatches)}; skipped')
            continue
        by_weight.setdefault(weight, []).append((path, data))
    return by_weight, problems


def legacy_saves(downloads: Path):
    return sorted(p.name for p in downloads.glob('rankings_*.json')
                  if re.match(r'^rankings_\d+(-\d+| \(\d+\))?\.json$', p.name))


def newest(saves):
    return max(saves, key=lambda s: (s[1].get('saved_at') or '', s[0].stat().st_mtime))


def describe(entry):
    return f"{entry.get('name')} ({entry.get('team')})"


def check_and_report(weight, save, current, relationships, top_n):
    """Print checks and movement for one weight. Returns list of blocking errors."""
    errors = []
    ranks = save.get('rankings') or []
    ids = [e.get('wrestler_id') for e in ranks]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        errors.append(f'duplicate wrestler ids in save: {dupes}')
    if relationships is not None:
        not_in_matrix = [e for e in ranks if e.get('wrestler_id') not in relationships]
        if not_in_matrix:
            errors.append('not in relationships file (matrix would not show them): '
                          + ', '.join(describe(e) for e in not_in_matrix))
    if sorted(e.get('rank') for e in ranks) != list(range(1, len(ranks) + 1)):
        errors.append('ranks are not 1..N')

    if current is None:
        print(f'    (no current rankings_{weight}.json; will be created, {len(ranks)} wrestlers)')
        return errors

    cur = current.get('rankings') or []
    cur_rank = {e['wrestler_id']: e['rank'] for e in cur}
    new_ids = set(ids)
    missing = [e for e in cur if e['wrestler_id'] not in new_ids]
    added = [e for e in ranks if e.get('wrestler_id') not in cur_rank]
    if missing:
        errors.append(f'{len(missing)} wrestler(s) in current file missing from save: '
                      + ', '.join(describe(e) for e in missing[:10]))
    if added:
        print(f'    {len(added)} wrestler(s) new vs current file: '
              + ', '.join(f"#{e['rank']} {describe(e)}" for e in added[:10]))

    moved = [e for e in ranks if e.get('wrestler_id') in cur_rank and cur_rank[e['wrestler_id']] != e['rank']]
    moved_top = [e for e in moved
                 if e['rank'] <= top_n or cur_rank[e['wrestler_id']] <= top_n]
    if not moved:
        print('    no changes vs current file')
    else:
        print(f'    {len(moved)} rank change(s) total; '
              + (f'in or out of the top {top_n}:' if moved_top else f'none in the top {top_n}'))
        for e in sorted(moved_top, key=lambda e: e['rank']):
            old = cur_rank[e['wrestler_id']]
            arrow = 'up' if e['rank'] < old else 'down'
            print(f"      #{e['rank']:<3} {describe(e)}  was #{old} ({arrow} {abs(old - e['rank'])})")
    return errors


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('-season', type=int, required=True)
    ap.add_argument('-gender', required=True, choices=['boys', 'girls', 'men', 'women'])
    ap.add_argument('-league', default='hs', choices=['hs', 'ncaa'])
    ap.add_argument('-state', default='KY')
    ap.add_argument('-data-dir', default='mt/rankings_data',
                    help='rankings data root (preseason: mt/preseason_{season}/rankings_data)')
    ap.add_argument('-downloads', default=str(Path.home() / 'Downloads'))
    ap.add_argument('-weights', help='comma-separated weights to import (default: all found)')
    ap.add_argument('--dry-run', action='store_true', help='check and report only; change nothing')
    ap.add_argument('--allow-missing', action='store_true',
                    help='import even if wrestlers in the current file are missing from the save')
    args = ap.parse_args()

    downloads = Path(args.downloads).expanduser()
    data_path = Path(args.data_dir) / league_dir_key(args.league, args.gender, args.state) / str(args.season)
    if not data_path.is_dir():
        sys.exit(f'Data folder not found: {data_path}')
    top_n = PUBLISHED_SIZE.get(args.gender, 40)

    by_weight, problems = find_saves(downloads, args.gender, args.season)
    if args.weights:
        wanted = {w.strip() for w in args.weights.split(',')}
        by_weight = {w: s for w, s in by_weight.items() if w in wanted}

    print(f'{args.gender} {args.season}: saves in {downloads} -> {data_path}'
          + ('  [DRY RUN]' if args.dry_run else ''))
    for p in problems:
        print(f'  WARNING {p}')
    legacy = legacy_saves(downloads)
    if legacy:
        print(f'  WARNING old-style saves without gender/season in the name (not imported): {", ".join(legacy)}')
    if not by_weight:
        print('  No saves found.')
        return

    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup_dir = data_path / 'rankings_archive' / f'import_{stamp}'
    save_archive = downloads / SAVE_ARCHIVE_DIRNAME / f'{args.gender}_{args.season}'
    imported, blocked = [], []

    for weight in sorted(by_weight, key=lambda w: (len(w), w)):
        saves = by_weight[weight]
        path, save = newest(saves)
        older = [p.name for p, _ in saves if p != path]
        print(f'\n  {weight}: {path.name}' + (f'  (newest of {len(saves)}; older: {", ".join(older)})' if older else ''))

        target = data_path / f'rankings_{weight}.json'
        current = json.loads(target.read_text(encoding='utf-8')) if target.exists() else None
        rel_file = data_path / f'relationships_{weight}.json'
        relationships = (json.loads(rel_file.read_text(encoding='utf-8')).get('wrestlers') or {}
                         if rel_file.exists() else None)
        if relationships is None:
            print(f'    WARNING no relationships_{weight}.json; skipped the in-matrix check')

        errors = check_and_report(weight, save, current, relationships, top_n)
        if args.allow_missing:
            errors = [e for e in errors if 'missing from save' not in e]
        if errors:
            for e in errors:
                print(f'    BLOCKED: {e}')
            blocked.append(weight)
            continue
        if args.dry_run:
            continue

        if target.exists():
            backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup_dir / target.name)
        shutil.copy2(path, target)
        save_archive.mkdir(parents=True, exist_ok=True)
        for p, _ in saves:
            shutil.move(str(p), str(save_archive / p.name))
        imported.append(weight)

    print()
    if args.dry_run:
        ok = [w for w in by_weight if w not in blocked]
        print(f'DRY RUN: would import {len(ok)} weight(s): {", ".join(sorted(ok, key=lambda w: (len(w), w))) or "none"}')
    else:
        print(f'Imported {len(imported)} weight(s): {", ".join(imported) or "none"}')
        if backup_dir.exists():
            print(f'  previous files backed up to {backup_dir}')
        if imported:
            print(f'  save files moved to {save_archive}')
    if blocked:
        print(f'Blocked (not imported): {", ".join(blocked)}')
        sys.exit(1)


if __name__ == '__main__':
    main()
