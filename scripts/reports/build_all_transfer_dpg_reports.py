#!/usr/bin/env python3
"""
Batch-precompute every team x season Transfer DPG report so the frontend
page (frontend/wrestledata-ui/public/reports/transfers/index.html) never
has to tell a visitor to go run a script themselves.

Single-season only (--start-year == --end-year) -- a multi-year range was
tried and dropped: "all transfers touching this team across N years" isn't
a useful stat, and the combinatorial year-range space (~120 pairs/team)
made full precompute impractical. One season per team is small enough to
precompute in full: 79 teams x 15 seasons (2012-2026) = 1,185 files.

Re-run this after each season's data lands (new season added, or any
season's underlying data changes).

Usage:
    python scripts/reports/build_all_transfer_dpg_reports.py
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from team_colors import TEAM_COLORS  # noqa: E402

MIN_YEAR = 2012
MAX_YEAR = 2026
SCRIPT = Path(__file__).resolve().parent / "build_transfer_dpg_report.py"


def main():
    teams = sorted(TEAM_COLORS.keys())
    years = range(MIN_YEAR, MAX_YEAR + 1)
    total = len(teams) * len(years)
    done = 0
    failed = []

    for team in teams:
        for year in years:
            done += 1
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--team", team, "--start-year", str(year), "--end-year", str(year)],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                failed.append((team, year, result.stderr.strip().splitlines()[-1] if result.stderr else "unknown error"))
            if done % 50 == 0 or done == total:
                print(f"[{done}/{total}] {team} {year}")

    print(f"\nDone: {total - len(failed)}/{total} succeeded")
    if failed:
        print(f"{len(failed)} failed:")
        for team, year, err in failed:
            print(f"  {team} {year}: {err}")


if __name__ == "__main__":
    main()
