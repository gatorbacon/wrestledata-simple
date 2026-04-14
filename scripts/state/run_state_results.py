#!/usr/bin/env python3
"""
Generate state results graphics from placement.txt.

Reads placement.txt from data/hs_ky_{gender}/{season}/, parses 1st/3rd/5th/7th
place matches to get all 8 placers per weight, and fills the State Results
template SVG for each weight class. Output: mt/graphics/State-Results/{boys|girls}/

Only saves SVG files (no JPG export) so you can customize embedded images.

Usage:
  python scripts/state/run_state_results.py --season 2026
  python scripts/state/run_state_results.py --season 2026 -gender boys
  python scripts/state/run_state_results.py --season 2026 --weight 106
"""

import argparse
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

HS_BOYS_WEIGHTS = [106, 113, 120, 126, 132, 138, 144, 150, 157, 165, 175, 190, 215, 285]
HS_GIRLS_WEIGHTS = [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235]

PLACEMENT_LABELS = [
    "1st-place",
    "2nd-place",
    "3rd-place",
    "4th-place",
    "5th-place",
    "6th-place",
    "7th-place",
    "8th-place",
]


def parse_placement_file(placement_file_path: Path) -> Dict[str, List[Dict]]:
    """
    Parse placement file to extract state tournament placements.
    Returns dict: weight_class (str) -> list of {weight, place, name, team}.
    """
    placements_by_weight: Dict[str, List[Dict]] = {}
    if not placement_file_path.exists():
        return placements_by_weight

    current_weight: Optional[str] = None

    with placement_file_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.isdigit():
                current_weight = line
                placements_by_weight[current_weight] = []
                continue
            if not current_weight:
                continue

            placement_match = re.match(r"(\d+)(st|nd|rd|th)\s+Place\s+Match", line)
            if not placement_match:
                continue

            placement_num = int(placement_match.group(1))
            winner_pattern = r"Place\s+Match\s+-\s+(.+?)\s+\(([^)]+(?:\([^)]+\))*[^)]*)\)\s+\d+-\d+\s+won\s+(?:by|in)"
            winner_match = re.search(winner_pattern, line)
            loser_pattern = r"over\s+(.+?)\s+\(([^)]+(?:\([^)]+\))*[^)]*)\)\s+\d+-\d+\s*\("
            loser_match = re.search(loser_pattern, line)
            if not loser_match:
                loser_pattern = r"over\s+(.+?)\s+\(([^)]+(?:\([^)]+\))*[^)]*)\)\s+\d+-\d+$"
                loser_match = re.search(loser_pattern, line)

            if winner_match and loser_match:
                winner_name = winner_match.group(1).strip()
                winner_team = winner_match.group(2).strip()
                loser_name = loser_match.group(1).strip()
                loser_team = loser_match.group(2).strip()

                if placement_num == 1:
                    placements_by_weight[current_weight].append(
                        {"weight": current_weight, "place": 1, "name": winner_name, "team": winner_team}
                    )
                    placements_by_weight[current_weight].append(
                        {"weight": current_weight, "place": 2, "name": loser_name, "team": loser_team}
                    )
                elif placement_num == 3:
                    placements_by_weight[current_weight].append(
                        {"weight": current_weight, "place": 3, "name": winner_name, "team": winner_team}
                    )
                    placements_by_weight[current_weight].append(
                        {"weight": current_weight, "place": 4, "name": loser_name, "team": loser_team}
                    )
                elif placement_num == 5:
                    placements_by_weight[current_weight].append(
                        {"weight": current_weight, "place": 5, "name": winner_name, "team": winner_team}
                    )
                    placements_by_weight[current_weight].append(
                        {"weight": current_weight, "place": 6, "name": loser_name, "team": loser_team}
                    )
                elif placement_num == 7:
                    placements_by_weight[current_weight].append(
                        {"weight": current_weight, "place": 7, "name": winner_name, "team": winner_team}
                    )
                    placements_by_weight[current_weight].append(
                        {"weight": current_weight, "place": 8, "name": loser_name, "team": loser_team}
                    )

    return placements_by_weight


def format_wrestler_name(name: str, max_length: int = 24) -> str:
    """Format name for display. Truncate if needed."""
    if not name or not name.strip():
        return ""
    s = " ".join(word.title() for word in (name or "").strip().split())
    if len(s) <= max_length:
        return s
    words = s.split()
    if len(words) >= 2:
        return f"{words[0][0].upper()}. {words[-1]}"
    return s[:max_length]


def normalize_school_name(name: str) -> str:
    """School name in ALL CAPS."""
    if not name or not name.strip():
        return ""
    return name.strip().upper()


def _set_label_text(root: ET.Element, ns: dict, label: str, value: str) -> None:
    """Find element by inkscape label and set its text content."""
    el = root.find(f".//*[@inkscape:label='{label}']", namespaces=ns)
    if el is None:
        return
    tspan = el.find("svg:tspan", ns) if "svg" in str(el.tag) else el.find(".//{http://www.w3.org/2000/svg}tspan", ns)
    target = tspan if tspan is not None else el
    if target is not None:
        inner = target.find("svg:tspan", ns) if "svg" in str(target.tag) else target.find(".//{http://www.w3.org/2000/svg}tspan", ns)
        final = inner if inner is not None else target
        final.text = value or ""


def _set_text_in_element(el: ET.Element, ns: dict, value: str) -> None:
    """Set text in element, handling nested tspan."""
    if el is None:
        return
    tspan = el.find("svg:tspan", ns)
    if tspan is None:
        tspan = el.find(".//{http://www.w3.org/2000/svg}tspan", ns)
    if tspan is None:
        el.text = value or ""
        return
    inner = tspan.find("svg:tspan", ns)
    if inner is None:
        inner = tspan.find(".//{http://www.w3.org/2000/svg}tspan", ns)
    target = inner if inner is not None else tspan
    target.text = value or ""


def generate_state_results_graphic(
    weight: int,
    placements: List[Dict],
    template_path: Path,
    out_dir: Path,
    output_basename: str,
) -> bool:
    """
    Fill State Results template for one weight class.
    placements: list of {place, name, team} sorted by place 1-8.
    """
    if not template_path.exists():
        print(f"  Template not found: {template_path}")
        return False

    ns = {
        "svg": "http://www.w3.org/2000/svg",
        "inkscape": "http://www.inkscape.org/namespaces/inkscape",
    }
    tree = ET.parse(template_path)
    root = tree.getroot()

    _set_label_text(root, ns, "Weight-Class", f"{weight} lbs")

    placements_by_place = {p["place"]: p for p in placements}

    for i, label in enumerate(PLACEMENT_LABELS, start=1):
        group = root.find(f".//*[@inkscape:label='{label}']", namespaces=ns)
        if group is None:
            continue
        p = placements_by_place.get(i)
        if p:
            name = format_wrestler_name(p.get("name") or "")
            team = normalize_school_name(p.get("team") or "")
        else:
            name = ""
            team = ""
        wrestler_el = group.find(f".//*[@inkscape:label='wrestler-name']", namespaces=ns)
        school_el = group.find(f".//*[@inkscape:label='school-name']", namespaces=ns)
        if wrestler_el is not None:
            _set_text_in_element(wrestler_el, ns, name)
        if school_el is not None:
            _set_text_in_element(school_el, ns, team)

    out_dir.mkdir(parents=True, exist_ok=True)
    svg_path = out_dir / f"{output_basename}_{weight}.svg"
    tree.write(svg_path, encoding="utf-8", xml_declaration=True)
    print(f"  ✓ {weight} lbs: {svg_path}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate state results graphics from placement.txt"
    )
    parser.add_argument("--season", type=int, default=2026, help="Season year")
    parser.add_argument(
        "-gender",
        "--gender",
        type=str,
        choices=["boys", "girls"],
        default="boys",
        help="Gender",
    )
    parser.add_argument(
        "--weight",
        type=int,
        default=None,
        help="Single weight class (e.g. 106); default all for gender",
    )
    parser.add_argument(
        "--placement-file",
        type=str,
        default=None,
        help="Override placement file path",
    )
    args = parser.parse_args()

    if args.gender == "boys":
        weights = HS_BOYS_WEIGHTS
        template_path = (
            PROJECT_ROOT
            / "mt"
            / "graphics"
            / "templates"
            / "State-Results"
            / "Boys-States-Results-Template.svg"
        )
        out_dir = PROJECT_ROOT / "mt" / "graphics" / "State-Results" / "boys"
        output_prefix = "boys"
    else:
        weights = HS_GIRLS_WEIGHTS
        template_path = (
            PROJECT_ROOT
            / "mt"
            / "graphics"
            / "templates"
            / "State-Results"
            / "Girls-States-Results-Template.svg"
        )
        out_dir = PROJECT_ROOT / "mt" / "graphics" / "State-Results" / "girls"
        output_prefix = "girls"

    if args.placement_file:
        placement_path = Path(args.placement_file)
    else:
        placement_path = (
            PROJECT_ROOT / "data" / f"hs_ky_{args.gender}" / str(args.season) / "placement.txt"
        )
        if not placement_path.exists():
            placement_path = placement_path.with_suffix(".md")

    if not placement_path.exists():
        print(f"Placement file not found: {placement_path}")
        print("Create data/hs_ky_{gender}/{season}/placement.txt with format:")
        print("  106")
        print("  1st Place Match - Winner Name (Team) X-Y won by ... over Loser Name (Team) X-Y")
        print("  3rd Place Match - ...")
        print("  5th Place Match - ...")
        print("  7th Place Match - ...")
        return

    placements_by_weight = parse_placement_file(placement_path)

    if args.weight is not None:
        if args.weight not in weights:
            print(f"Invalid weight {args.weight} for {args.gender}. Valid: {weights}")
            return
        weights = [args.weight]

    print("=" * 60)
    print("STATE RESULTS GRAPHICS")
    print("=" * 60)
    print(f"Gender: {args.gender}, Season: {args.season}")
    print(f"Placement file: {placement_path}")
    print(f"Weights: {weights}")
    print()

    for weight in weights:
        weight_str = str(weight)
        placements = placements_by_weight.get(weight_str, [])
        placements_sorted = sorted(placements, key=lambda p: p["place"])

        if len(placements_sorted) != 8:
            print(f"  ⚠ {weight} lbs: expected 8 placers, got {len(placements_sorted)}")
            if not placements_sorted:
                continue

        generate_state_results_graphic(
            weight,
            placements_sorted,
            template_path,
            out_dir,
            output_prefix,
        )

    print()
    print("=" * 60)
    print(f"Output: {out_dir}")
    print("(SVG only - customize embedded images, then export to JPG as needed)")
    print("=" * 60)


if __name__ == "__main__":
    main()
