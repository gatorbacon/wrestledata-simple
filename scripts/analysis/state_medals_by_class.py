#!/usr/bin/env python3
"""
State placements by graduating class, broken down by grade.

Grades are inferred for seasons missing grade data using known grades
from other seasons in the same career.

Usage:
    python scripts/analysis/state_medals_by_class.py --gender boys
    python scripts/analysis/state_medals_by_class.py --gender girls
    python scripts/analysis/state_medals_by_class.py --gender boys --min-class 2018
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

GRADE_NAMES = {
    7: "7th", 8: "8th", 9: "9th",
    10: "10th", 11: "11th", 12: "12th",
}

# Colors per grade — light to dark as grade increases
GRADE_COLORS = {
    7:  "#c6dbef",
    8:  "#9ecae1",
    9:  "#6baed6",
    10: "#3182bd",
    11: "#08519c",
    12: "#08306b",
}


def infer_grades(seasons: list[dict]) -> dict[int, int]:
    """
    Return {season: grade} for all seasons in a career.
    Uses known grades to infer missing ones (grade shifts by 1 per season year).
    """
    known = {}
    for s in seasons:
        season = s.get("season")
        grade = s.get("grade")
        if season is not None and grade is not None:
            known[int(season)] = int(grade)

    if not known:
        return {}

    # Use the first known anchor to infer all others
    anchor_season, anchor_grade = next(iter(known.items()))
    result = {}
    for s in seasons:
        season = s.get("season")
        if season is None:
            continue
        season = int(season)
        inferred = anchor_grade + (season - anchor_season)
        if 7 <= inferred <= 13:  # allow 13 as edge case (redshirt etc), filter later
            result[season] = inferred
    return result


def main():
    parser = argparse.ArgumentParser(description="State placements by graduating class")
    parser.add_argument("--gender", required=True, choices=["boys", "girls"])
    parser.add_argument("--min-class", type=int, default=None)
    parser.add_argument("--max-class", type=int, default=None)
    parser.add_argument("--no-chart", action="store_true", help="Print text output only")
    parser.add_argument("--show-skipped", action="store_true", help="List placements that could not be assigned a grade")
    args = parser.parse_args()
    gender = args.gender

    careers_dir = REPO_ROOT / "frontend/hs-ky-ui/public/data/careers" / gender
    if not careers_dir.exists():
        print(f"Career profiles not found: {careers_dir}")
        return

    # grad_class -> grade -> count
    data: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    skipped = 0
    skipped_list = []

    for cf in careers_dir.glob("career_*.json"):
        try:
            with cf.open(encoding="utf-8") as f:
                career = json.load(f)
        except Exception:
            continue

        seasons = career.get("seasons", [])
        grade_map = infer_grades(seasons)  # {season: grade}

        for s in seasons:
            state_place = s.get("state_place")
            if not state_place:
                continue

            season = s.get("season")
            if season is None:
                skipped += 1
                skipped_list.append({"name": career.get("canonical_name"), "season": "?", "place": state_place})
                continue

            grade = grade_map.get(int(season))
            if grade is None:
                skipped += 1
                skipped_list.append({"name": career.get("canonical_name"), "season": season, "place": state_place})
                continue

            if not (7 <= grade <= 12):
                skipped += 1
                skipped_list.append({"name": career.get("canonical_name"), "season": season, "place": state_place, "inferred_grade": grade})
                continue

            grad_class = int(season) + (12 - grade)
            data[grad_class][grade] += 1

    if not data:
        print("No state placement data found.")
        return

    all_classes = sorted(data.keys())
    if args.min_class:
        all_classes = [c for c in all_classes if c >= args.min_class]
    if args.max_class:
        all_classes = [c for c in all_classes if c <= args.max_class]

    # --- Text output ---
    print(f"\nState Placements by Graduating Class — {gender.capitalize()}")
    print("=" * 60)
    for grad_class in reversed(all_classes):
        grade_data = data[grad_class]
        total = sum(grade_data.values())
        print(f"\nClass of {grad_class}  ({total} total)")
        for grade in sorted(grade_data):
            bar = "#" * grade_data[grade]
            print(f"  Grade {GRADE_NAMES[grade]:5s}: {grade_data[grade]:3d}  {bar}")
    if skipped:
        print(f"\n  ({skipped} placements skipped — could not determine grade)")
        if args.show_skipped:
            print(f"\n{'─' * 60}")
            print(f"Skipped placements:")
            for row in sorted(skipped_list, key=lambda r: (r["season"], r["name"])):
                note = f"  [inferred grade {row['inferred_grade']} — out of range]" if "inferred_grade" in row else ""
                print(f"  {row['season']}  {row['place']}th place  {row['name']}{note}")
            print(f"{'─' * 60}")

    if args.no_chart:
        return

    # --- Bar chart ---
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import numpy as np

    grades = list(range(7, 13))
    x = np.arange(len(all_classes))
    bar_width = 0.65

    fig, ax = plt.subplots(figsize=(max(10, len(all_classes) * 0.55), 6))

    bottoms = np.zeros(len(all_classes))
    for grade in grades:
        counts = np.array([data[c].get(grade, 0) for c in all_classes], dtype=float)
        bars = ax.bar(x, counts, bar_width, bottom=bottoms,
                      color=GRADE_COLORS[grade], label=GRADE_NAMES[grade],
                      edgecolor="white", linewidth=0.4)
        # Label segments that are large enough to read
        for i, (count, bottom) in enumerate(zip(counts, bottoms)):
            if count >= 4:
                ax.text(x[i], bottom + count / 2, str(int(count)),
                        ha="center", va="center", fontsize=7,
                        color="white", fontweight="bold")
        bottoms += counts

    # Total labels on top of each bar
    for i, grad_class in enumerate(all_classes):
        total = sum(data[grad_class].values())
        ax.text(x[i], bottoms[i] + 0.5, str(total),
                ha="center", va="bottom", fontsize=8, color="#333333", fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels([str(c) for c in all_classes], rotation=45, ha="right", fontsize=9)
    ax.set_ylabel("State Placements", fontsize=11)
    ax.set_title(f"State Placements by Graduating Class — {gender.capitalize()}",
                 fontsize=13, fontweight="bold", pad=14)
    ax.set_xlim(-0.6, len(all_classes) - 0.4)
    ax.yaxis.grid(True, linestyle="--", alpha=0.5)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    legend_patches = [
        mpatches.Patch(color=GRADE_COLORS[g], label=f"Grade {GRADE_NAMES[g]}")
        for g in grades
    ]
    ax.legend(handles=legend_patches, title="Grade", loc="upper left",
              fontsize=9, title_fontsize=9, framealpha=0.8)

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
