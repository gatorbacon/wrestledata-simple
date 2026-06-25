#!/usr/bin/env python3
"""
make_mbt_official.py — Promote MBT 50/50 to the official TPAR system.

What this does
--------------
1. Backs up mat_value_2026.json  →  mat_value_v1_2026.json  (safe to rerun)
2. Writes a new mat_value_2026.json with MBT scores (same schema, drop-in replacement)
3. Updates every wrestler profile in data/wrestlers/{season}/by_id/:
   - Renames match_list[].mv_impact → mv_impact_v1  (preserved, never deleted)
   - Computes MBT per-match impact and stores as mv_impact
   - Renames metrics.mat_value.mv_avg → mv_avg_v1
   - Writes new metrics.mat_value.mv_avg = MBT 50/50 TPAR
   - Updates rank_weight / rank_overall / version

Rollback
--------
Run make_v1_official.py (or just swap the files back). The _v1 fields and
mv_avg_v1 / mat_value_v1_2026.json are never touched again by this script.

Run
---
  .venv/bin/python scripts/mat_value/make_mbt_official.py
  .venv/bin/python scripts/mat_value/make_mbt_official.py --season 2026 --dry-run
"""

import argparse, json, os, pathlib, sys
from collections import defaultdict

def parse_date_iso(s):
    """MM/DD/YYYY → YYYY-MM-DD (for matching match_list dates)."""
    if not s:
        return s
    if '-' in s:
        return s  # already ISO
    parts = s.split('/')
    if len(parts) == 3:
        m, d, y = parts
        return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
    return s


def compute_per_match_impacts(match_list, rolling_timeline, final_tpar):
    """
    Compute MBT per-match impact for each entry in match_list.

    Strategy:
    - Sort the rolling MBT timeline chronologically.
    - For each timeline date, delta = tpar[i] - tpar[i-1]  (first: tpar[0] - 0).
    - Count matches on that date from match_list, spread delta equally.
    - For dates not in timeline (e.g. NCAA tournament), use
      (final_tpar - last_timeline_tpar) spread across remaining matches.
    - Matches with no date or unknown date get impact 0.
    """
    if not rolling_timeline:
        return {i: 0.0 for i in range(len(match_list))}

    # Sort timeline chronologically (dates are MM/DD/YYYY)
    def sort_key(pt):
        s = pt['date']
        m, d, y = s.split('/')
        return (int(y), int(m), int(d))

    tl = sorted(rolling_timeline, key=sort_key)

    # Build delta per ISO date
    delta_by_date = {}
    prev_tpar = 0.0
    for pt in tl:
        iso = parse_date_iso(pt['date'])
        delta_by_date[iso] = pt['tpar'] - prev_tpar
        prev_tpar = pt['tpar']

    last_rolling_tpar = tl[-1]['tpar'] if tl else 0.0
    last_rolling_iso  = parse_date_iso(tl[-1]['date']) if tl else None

    # Count matches per date
    date_counts = defaultdict(int)
    for m in match_list:
        d = m.get('date', '')
        if d:
            date_counts[d] += 1

    # Assign per-match impact
    impacts = {}
    for idx, m in enumerate(match_list):
        d = m.get('date', '')
        if not d:
            impacts[idx] = 0.0
            continue
        if d in delta_by_date:
            count = date_counts[d]
            impacts[idx] = round(delta_by_date[d] / count, 4) if count else 0.0
        else:
            # Date not in rolling timeline → probably tournament or post-season
            # Spread (final_tpar - last_rolling_tpar) across all such matches
            tournament_dates = {dd for dd in date_counts if dd not in delta_by_date and dd}
            tournament_match_count = sum(date_counts[dd] for dd in tournament_dates)
            tournament_delta = final_tpar - last_rolling_tpar if final_tpar is not None else 0.0
            count = date_counts[d]
            per_match = (tournament_delta / tournament_match_count
                         if tournament_match_count else 0.0)
            impacts[idx] = round(per_match, 4)

    return impacts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--season',   type=int, default=2026)
    ap.add_argument('--dry-run',  action='store_true',
                    help='Print what would happen without writing any files')
    a = ap.parse_args()

    FRONTEND = pathlib.Path('frontend/wrestledata-ui/public/data')
    MV_DIR   = FRONTEND / 'mat_value' / str(a.season)
    WR_DIR   = FRONTEND / 'wrestlers' / str(a.season) / 'by_id'

    mv_file      = MV_DIR / f'mat_value_{a.season}.json'
    mv_v1_file   = MV_DIR / f'mat_value_v1_{a.season}.json'
    mbt_file     = MV_DIR / f'tpar_mbt_{a.season}.json'
    rolling_file = MV_DIR / f'rolling_mbt_{a.season}.json'

    for f in (mv_file, mbt_file, rolling_file):
        if not f.exists():
            sys.exit(f"Missing required file: {f}")

    print(f"Loading data for season {a.season}...")
    with mv_file.open()      as f: old_mv   = json.load(f)
    with mbt_file.open()     as f: mbt_data = json.load(f)
    with rolling_file.open() as f: rolling  = json.load(f)

    # ── Step 1: Build new mat_value_2026.json ─────────────────────────────────

    # Index old mat_value by wrestler_id for field carryover
    old_by_id = {str(e['wrestler_id']): e for e in old_mv}

    # Compute per-weight MBT ranks
    by_weight = defaultdict(list)
    for wid, info in mbt_data.items():
        by_weight[info['weight']].append((wid, info['tpar_50_50']))

    weight_rank = {}   # wid → rank within weight
    for w, entries in by_weight.items():
        entries.sort(key=lambda x: -x[1])
        for rank, (wid, _) in enumerate(entries, 1):
            weight_rank[wid] = rank

    # Sort all MBT wrestlers by 50/50 for overall rank
    all_sorted = sorted(mbt_data.items(), key=lambda x: -x[1]['tpar_50_50'])
    overall_rank = {wid: r for r, (wid, _) in enumerate(all_sorted, 1)}

    new_mv = []
    for wid, info in mbt_data.items():
        old = old_by_id.get(str(wid), {})
        entry = {
            'wrestler_id':    wid,
            'name':           info.get('name',  old.get('name',  '')),
            'team':           info.get('team',  old.get('team',  '')),
            'weight':         info['weight'],
            'current_rank':   old.get('current_rank'),
            'mv_avg':         round(info['tpar_50_50'], 4),
            'mv_avg_v1':      old.get('mv_avg'),        # backup
            'matches':        old.get('matches', 0),
            'mv_rank_overall': overall_rank.get(wid),
            'mv_rank_weight':  weight_rank.get(wid),
        }
        new_mv.append(entry)

    # Sort by mv_avg desc (leaderboard default)
    new_mv.sort(key=lambda e: -(e['mv_avg'] or 0))

    if a.dry_run:
        print(f"[dry-run] Would write {mv_v1_file} (backup of v1)")
        print(f"[dry-run] Would write {mv_file} ({len(new_mv)} entries, MBT scores)")
        top5 = new_mv[:5]
        for e in top5:
            print(f"  {e['mv_avg']:+.3f}  {e['name']} ({e['weight']}, {e['team']})")
    else:
        # Back up v1 (only if backup doesn't already exist — don't overwrite a clean backup)
        if not mv_v1_file.exists():
            import shutil
            shutil.copy2(mv_file, mv_v1_file)
            print(f"Backed up → {mv_v1_file}")
        else:
            print(f"Backup already exists, skipping: {mv_v1_file}")

        with mv_file.open('w') as f:
            json.dump(new_mv, f)
        print(f"Wrote {mv_file}  ({len(new_mv)} entries)")

    # ── Step 2: Update wrestler profiles ──────────────────────────────────────

    profile_files = list(WR_DIR.glob('*.json'))
    print(f"\nUpdating {len(profile_files)} wrestler profiles...")

    updated = skipped = already_done = 0

    for pf in profile_files:
        wid = pf.stem
        mbt_info = mbt_data.get(wid)
        if mbt_info is None:
            skipped += 1
            continue

        with pf.open() as f:
            profile = json.load(f)

        # ── match_list: rename mv_impact → mv_impact_v1, add MBT mv_impact ──
        match_list = profile.get('match_list', [])
        if match_list and 'mv_impact_v1' not in match_list[0]:
            # First run: back up v1 values
            for m in match_list:
                if 'mv_impact' in m:
                    m['mv_impact_v1'] = m['mv_impact']
        elif match_list and 'mv_impact_v1' in match_list[0]:
            already_done += 1  # Already migrated on a previous run

        # Compute MBT per-match impacts
        wid_timeline = rolling.get(wid, [])
        final_tpar   = mbt_info['tpar_50_50']
        impacts = compute_per_match_impacts(match_list, wid_timeline, final_tpar)
        for idx, m in enumerate(match_list):
            m['mv_impact'] = impacts.get(idx, 0.0)

        # ── metrics.mat_value ─────────────────────────────────────────────────
        mv_metrics = profile.setdefault('metrics', {}).setdefault('mat_value', {})
        if 'mv_avg_v1' not in mv_metrics:
            mv_metrics['mv_avg_v1']       = mv_metrics.get('mv_avg')
            mv_metrics['rank_weight_v1']  = mv_metrics.get('rank_weight')
            mv_metrics['rank_overall_v1'] = mv_metrics.get('rank_overall')

        mv_metrics['mv_avg']       = round(mbt_info['tpar_50_50'], 4)
        mv_metrics['rank_weight']  = weight_rank.get(wid)
        mv_metrics['rank_overall'] = overall_rank.get(wid)
        mv_metrics['version']      = 'mbt_50_50'

        if not a.dry_run:
            with pf.open('w') as f:
                json.dump(profile, f)
        updated += 1

    if a.dry_run:
        print(f"[dry-run] Would update {updated} profiles, skip {skipped} (no MBT data)")
    else:
        print(f"Updated {updated} profiles  |  skipped {skipped} (no MBT data)  |  already migrated {already_done}")

    print("\nDone.")
    print("  To roll back: run make_v1_official.py  (or restore mat_value_v1_2026.json)")


if __name__ == '__main__':
    main()
