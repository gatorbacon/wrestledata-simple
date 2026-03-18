#!/usr/bin/env python3
"""Add missing seed 33 entries to seeds files for years 2014-2018."""

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

YEARS = [2014, 2015, 2016, 2017, 2018]
WEIGHTS = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]


def norm(s: str) -> str:
    return " ".join(s.lower().split())


def load_existing_names(year: int, weight: int) -> set:
    path = DATA_DIR / str(year) / "ncaa-tourney" / "seeds" / f"{weight}.txt"
    names = set()
    with path.open() as f:
        for line in f.readlines()[1:]:  # skip header
            parts = line.strip().split("\t")
            if len(parts) < 2:
                continue
            name_str = parts[1].strip()
            if "," in name_str:
                last, first = name_str.split(",", 1)
                names.add(norm(f"{first.strip()} {last.strip()}"))
            else:
                names.add(norm(name_str))
    return names


def parse_pigtail_line(line: str):
    """Extract both wrestlers from a pigtail match line."""
    m = re.match(
        r"Prelim - (.+?) \(([^)]+)\) (\d+-\d+) won.+? over (.+?) \(([^)]+)\) (\d+-\d+)",
        line,
    )
    if m:
        return [
            {"name": m.group(1).strip(), "team": m.group(2).strip(), "record": m.group(3).strip()},
            {"name": m.group(4).strip(), "team": m.group(5).strip(), "record": m.group(6).strip()},
        ]
    return None


def to_last_first(name: str) -> str:
    """Convert 'First Middle? Last' to 'Last, First Middle?'."""
    parts = name.strip().split()
    if len(parts) == 1:
        return name
    last = parts[-1]
    first_parts = " ".join(parts[:-1])
    return f"{last}, {first_parts}"


def find_pigtail_matches(year: int) -> dict:
    """Return dict of weight -> [winner_info, loser_info] for champ pigtail."""
    results_path = DATA_DIR / str(year) / "ncaa-tourney" / "results.txt"
    with results_path.open() as f:
        lines = f.readlines()

    pigtails = {}
    current_weight = None
    in_pig = False

    for raw in lines:
        line = raw.strip()
        if re.match(r"^\d{3}$", line):
            current_weight = int(line)
            in_pig = False
        elif line == "Pig Tails":
            in_pig = True
        elif in_pig and line.startswith("Prelim - ") and current_weight is not None:
            parsed = parse_pigtail_line(line)
            if parsed:
                pigtails[current_weight] = parsed
            in_pig = False  # only one champ pigtail per weight

    return pigtails


def main():
    for year in YEARS:
        print(f"\n=== {year} ===")
        pigtails = find_pigtail_matches(year)

        for weight in WEIGHTS:
            if weight not in pigtails:
                print(f"  {weight}lb: no pigtail found!")
                continue

            wrestlers = pigtails[weight]
            existing = load_existing_names(year, weight)

            seed33 = None
            for w in wrestlers:
                if norm(w["name"]) not in existing:
                    seed33 = w
                    break

            if seed33 is None:
                print(f"  {weight}lb: both wrestlers already in seeds file")
                continue

            last_first = to_last_first(seed33["name"])
            line = f"33.\t{last_first}\t{seed33['team']}\t\t{seed33['record']}\tYes\n"

            seeds_path = DATA_DIR / str(year) / "ncaa-tourney" / "seeds" / f"{weight}.txt"
            with seeds_path.open("a") as f:
                f.write(line)

            print(f"  {weight}lb: added {last_first} ({seed33['team']}) {seed33['record']}")


if __name__ == "__main__":
    main()
