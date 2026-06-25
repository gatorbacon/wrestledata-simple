#!/usr/bin/env python3
"""
make_v1_official.py — Roll back from MBT to v1 TPAR.

Reverses what make_mbt_official.py did:
  - Restores mat_value_2026.json from mat_value_v1_2026.json
  - Restores mv_impact from mv_impact_v1 in every wrestler profile
  - Restores metrics.mat_value.mv_avg from mv_avg_v1

Run:
  .venv/bin/python scripts/mat_value/make_v1_official.py
"""

import argparse, json, pathlib, shutil, sys

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--season', type=int, default=2026)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    FRONTEND = pathlib.Path('frontend/wrestledata-ui/public/data')
    MV_DIR   = FRONTEND / 'mat_value' / str(a.season)
    WR_DIR   = FRONTEND / 'wrestlers' / str(a.season) / 'by_id'

    mv_file    = MV_DIR / f'mat_value_{a.season}.json'
    mv_v1_file = MV_DIR / f'mat_value_v1_{a.season}.json'

    if not mv_v1_file.exists():
        sys.exit(f"No backup found at {mv_v1_file} — nothing to roll back.")

    if a.dry_run:
        print(f"[dry-run] Would restore {mv_file} from {mv_v1_file}")
    else:
        shutil.copy2(mv_v1_file, mv_file)
        print(f"Restored {mv_file} from v1 backup")

    profile_files = list(WR_DIR.glob('*.json'))
    print(f"Restoring {len(profile_files)} wrestler profiles...")
    restored = skipped = 0

    for pf in profile_files:
        with pf.open() as f:
            profile = json.load(f)

        match_list = profile.get('match_list', [])
        mv_metrics = profile.get('metrics', {}).get('mat_value', {})

        has_v1 = match_list and 'mv_impact_v1' in match_list[0]
        has_mv_v1 = 'mv_avg_v1' in mv_metrics

        if not has_v1 and not has_mv_v1:
            skipped += 1
            continue

        if has_v1:
            for m in match_list:
                if 'mv_impact_v1' in m:
                    m['mv_impact'] = m.pop('mv_impact_v1')

        if has_mv_v1:
            mv_metrics['mv_avg']       = mv_metrics.pop('mv_avg_v1')
            mv_metrics['rank_weight']  = mv_metrics.pop('rank_weight_v1', mv_metrics.get('rank_weight'))
            mv_metrics['rank_overall'] = mv_metrics.pop('rank_overall_v1', mv_metrics.get('rank_overall'))
            mv_metrics['version']      = 'v1'

        if not a.dry_run:
            with pf.open('w') as f:
                json.dump(profile, f)
        restored += 1

    if a.dry_run:
        print(f"[dry-run] Would restore {restored} profiles, skip {skipped}")
    else:
        print(f"Restored {restored} profiles  |  skipped {skipped} (no v1 backup found)")
    print("Done.")

if __name__ == '__main__':
    main()
