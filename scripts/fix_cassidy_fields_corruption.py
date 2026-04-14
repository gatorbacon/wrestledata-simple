#!/usr/bin/env python3
"""
Fix 2022 match summary corruption where every letter 'n' was replaced
with 'Cassidy Fields' by a Selenium scraping artifact.

Only replaces 'Cassidy Fields' that appears mid-word (adjacent to a letter),
leaving legitimate 'Cassidy Fields' references (standalone name) untouched.
"""

import json
import re
from pathlib import Path

AFFECTED_FILES = [
    'Phelps', 'Madison_Southern', 'Belfry', 'Barbourville', 'Grant_County',
    'Madison_Central', 'Letcher_County_Central', 'Boyle_County', 'Mccreary_Central',
    'Knox_Central_High_School', 'Corbin', 'Wayne_County', 'Harlan_County',
    'Knott_County_Central', 'Bell_County', 'Perry_County_Central', 'Whitley_County'
]

DATA_DIR = Path('mt/data_alias/hs_ky_boys/2022')

# Match 'Cassidy Fields' only when adjacent to a letter on at least one side
CORRUPT_PATTERN = re.compile(r'(?<=[A-Za-z])Cassidy Fields|Cassidy Fields(?=[A-Za-z])')


def fix_string(s):
    return CORRUPT_PATTERN.sub('n', s)


def fix_value(v):
    """Recursively fix strings in any JSON value."""
    if isinstance(v, str):
        return fix_string(v)
    if isinstance(v, list):
        return [fix_value(x) for x in v]
    if isinstance(v, dict):
        return {k: fix_value(val) for k, val in v.items()}
    return v


def main():
    total_files = 0
    total_replacements = 0

    for fname in AFFECTED_FILES:
        file_path = DATA_DIR / f'{fname}.json'
        if not file_path.exists():
            print(f'  ⚠ Not found: {file_path}')
            continue

        with open(file_path, encoding='utf-8') as f:
            original_text = f.read()

        # Count how many mid-word replacements exist
        count = len(CORRUPT_PATTERN.findall(original_text))
        if count == 0:
            continue

        data = json.loads(original_text)
        fixed_data = fix_value(data)
        fixed_text = json.dumps(fixed_data, indent=2, ensure_ascii=False)

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(fixed_text)

        print(f'  ✅ {fname}: fixed {count} corrupted occurrences')
        total_files += 1
        total_replacements += count

    print(f'\nDone. Fixed {total_replacements} corruptions across {total_files} files.')
    print('Re-run process_raw_matches_by_season.py -season 2022 to regenerate processed data.')


if __name__ == '__main__':
    main()
