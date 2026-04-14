#!/usr/bin/env python3
"""
Regional tournament projected TEAM SCORES using REGIONAL rankings only.

- One wrestler per team per weight (starters only).
- Placement determined strictly by regional rank (state rank order within region).
- Deterministic scoring table (no xTP, no probabilities).
- Output: TOP 3 teams per region with per-weight breakdown (console only).
- With --export-graphics: fill Boys- or Girls-Regions-Predictions-Template.svg per region
  (8 regions; 14 weights boys, 12 weights girls), write SVG + JPG to mt/graphics/Region-Predictions/.

Usage:
  python scripts/xtp/run_regional_xtp.py --season 2026
  python scripts/xtp/run_regional_xtp.py --season 2026 -gender boys
  python scripts/xtp/run_regional_xtp.py --season 2026 --export-graphics
  python scripts/xtp/run_regional_xtp.py --season 2026 -gender girls --export-graphics
"""

import argparse
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Exact scoring table: placement -> points
REGIONAL_PLACEMENT_POINTS = {
    1: 25,
    2: 22,
    3: 19,
    4: 16,
    5: 12,
    6: 9,
    7: 2,
    8: 1,
    9: 0.5,
    10: 0.5,
}
# 11+ = 0

HS_BOYS_WEIGHTS = [106, 113, 120, 126, 132, 138, 144, 150, 157, 165, 175, 190, 215, 285]
HS_GIRLS_WEIGHTS = [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235]


def load_teams(gender: str) -> List[dict]:
    """Load team list from data/team_lists/hs_ky_{gender}/teams.json."""
    path = PROJECT_ROOT / "data" / "team_lists" / f"hs_ky_{gender}" / "teams.json"
    if not path.exists():
        raise FileNotFoundError(f"Team list not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_region_teams(teams: List[dict]) -> Tuple[Dict[str, str], Dict[str, Set[str]]]:
    """Build team -> region and region -> set(team names). Only teams with a region."""
    team_region: Dict[str, str] = {}
    region_teams: Dict[str, Set[str]] = {}
    for t in teams:
        name = (t.get("name") or "").strip()
        region = t.get("region")
        if not name or region is None or (isinstance(region, str) and not region.strip()):
            continue
        region_str = str(region).strip()
        team_region[name] = region_str
        region_teams.setdefault(region_str, set()).add(name)
    return team_region, region_teams


def team_name_to_abbreviation(teams: List[dict]) -> Dict[str, str]:
    """Build map team name -> abbreviation from data/team_lists teams.json structure."""
    out: Dict[str, str] = {}
    for t in teams:
        name = (t.get("name") or "").strip()
        abbr = (t.get("abbreviation") or name).strip()
        if name:
            out[name] = abbr
    return out


def shorten_wrestler_name(name: str, max_length: int = 20) -> str:
    """If name longer than max_length, use first initial + last name (e.g. 'C. Thompson')."""
    name = (name or "").strip()
    if len(name) <= max_length:
        return name
    parts = name.split()
    if not parts:
        return name[:max_length]
    if len(parts) == 1:
        return name[:max_length]
    return f"{parts[0][0]}. {parts[-1]}"


def load_starter_rankings_for_weight(
    rankings_dir: Path,
    weight: int,
) -> List[dict]:
    """
    Load rankings_starters_<weight>.json.
    Returns list of entries with rank, wrestler_id, name, team, is_starter.
    """
    path = rankings_dir / f"rankings_starters_{weight}.json"
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    entries = data.get("rankings") or []
    return [e for e in entries if e.get("is_starter") and (e.get("team") or "").strip()]


def placement_to_points(placement: int) -> float:
    """Convert placement (1st=1, 2nd=2, ...) to points using the regional table."""
    return REGIONAL_PLACEMENT_POINTS.get(placement, 0.0)


def placement_label(placement: int) -> str:
    """Human-readable placement: 1st, 2nd, 3rd, 4th, ..., 10th, 11th+."""
    if placement >= 11:
        return "11th+"
    if placement == 1:
        return "1st"
    if placement == 2:
        return "2nd"
    if placement == 3:
        return "3rd"
    return f"{placement}th"


def aggregate_regional_team_scores(
    rankings_dir: Path,
    weights: List[int],
    region_team_names: Set[str],
) -> Dict[str, dict]:
    """
    For one region: for each weight, take starters in region, sort by state rank,
    assign placement 1,2,3,... then score via table. Aggregate by team.
    One wrestler per team per weight (starters only).
    """
    teams: Dict[str, dict] = {}

    for weight in weights:
        entries = load_starter_rankings_for_weight(rankings_dir, weight)
        in_region = [e for e in entries if (e.get("team") or "").strip() in region_team_names]
        if not in_region:
            continue
        in_region.sort(key=lambda e: (e.get("rank") or 9999, e.get("wrestler_id", "")))
        for placement, entry in enumerate(in_region, start=1):
            points = placement_to_points(placement)
            team = (entry.get("team") or "").strip()
            if not team:
                continue
            if team not in teams:
                teams[team] = {"team": team, "total_points": 0.0, "weights": {}}
            teams[team]["total_points"] += points
            teams[team]["weights"][weight] = {
                "name": (entry.get("name") or "?").strip(),
                "placement": placement,
                "points": points,
            }

    return teams


def get_region_display_data(
    rankings_dir: Path,
    weights: List[int],
    region_team_names: Set[str],
) -> Tuple[List[Tuple[str, float]], Dict[int, List[Tuple[str, str, str]]]]:
    """
    For one region: top 3 teams (name, score) and per-weight top 2 wrestlers
    (state_rank, name, team) for graphic fill.
    """
    teams = aggregate_regional_team_scores(rankings_dir, weights, region_team_names)
    sorted_teams = sorted(
        teams.values(),
        key=lambda t: (-t["total_points"], t["team"]),
    )[:3]
    top_3_list = [(t["team"], t["total_points"]) for t in sorted_teams]

    per_weight: Dict[int, List[Tuple[str, str, str]]] = {}
    for weight in weights:
        entries = load_starter_rankings_for_weight(rankings_dir, weight)
        in_region = [e for e in entries if (e.get("team") or "").strip() in region_team_names]
        in_region.sort(key=lambda e: (e.get("rank") or 9999, e.get("wrestler_id", "")))
        top2 = in_region[:2]
        per_weight[weight] = [
            (str(e.get("rank") or "?"), (e.get("name") or "?").strip(), (e.get("team") or "?").strip())
            for e in top2
        ]
    return top_3_list, per_weight


def _set_label_text(root: ET.Element, ns: dict, label: str, value: str) -> None:
    """Same as create_rankings_release: find text by label, get tspan, replace its text."""
    el = root.find(f".//svg:text[@inkscape:label='{label}']", namespaces=ns)
    if el is None:
        return
    tspan = el.find("svg:tspan", ns)
    target = tspan if tspan is not None else el
    target.text = value or ""


def _set_wrestler_text(el: ET.Element, ns: dict, value: str) -> None:
    """Same as rankings: find first tspan; if it has a child tspan use that (nested). Replace text only."""
    tspan = el.find("svg:tspan", ns)
    if tspan is None:
        el.text = value or ""
        return
    inner = tspan.find("svg:tspan", ns)
    target = inner if inner is not None else tspan
    target.text = value or ""


def _find_inkscape() -> Optional[str]:
    """
    Path to Inkscape executable, or None if not found.
    Checks PATH first; on macOS also checks /Applications/Inkscape.app.
    """
    exe = shutil.which("inkscape")
    if exe:
        return exe
    # macOS: GUI app often not on PATH
    mac_path = Path("/Applications/Inkscape.app/Contents/MacOS/inkscape")
    if mac_path.is_file():
        return str(mac_path)
    return None


def _export_svg_to_jpg_inkscape(
    svg_path: Path, jpg_path: Path, width: int = 1500, height: int = 1500
) -> Tuple[bool, Optional[str]]:
    """
    Export SVG to JPG via Inkscape so that filters (e.g. drop shadows) render.
    Returns (success, error_message). error_message is set when success is False
    so the caller can print why it failed.
    """
    inkscape = _find_inkscape()
    if not inkscape:
        return False, "Inkscape not found (not on PATH; on macOS also checked /Applications/Inkscape.app)"
    try:
        from PIL import Image
    except ImportError:
        return False, "PIL/Pillow not installed"
    png_path = jpg_path.with_suffix(".png")
    try:
        result = subprocess.run(
            [
                inkscape,
                str(svg_path),
                "--export-type=png",
                f"--export-filename={png_path}",
                f"--export-width={width}",
                f"--export-height={height}",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip() or f"exit code {result.returncode}"
            if png_path.exists():
                png_path.unlink(missing_ok=True)
            return False, f"Inkscape failed: {err}"
        img = Image.open(png_path).convert("RGB")
        img.save(jpg_path, format="JPEG", quality=95)
        png_path.unlink(missing_ok=True)
        return True, None
    except OSError as e:
        if png_path.exists():
            png_path.unlink(missing_ok=True)
        return False, f"Inkscape error: {e}"
    except Exception as e:
        if png_path.exists():
            png_path.unlink(missing_ok=True)
        return False, str(e)


def export_region_predictions_graphics(
    rankings_dir: Path,
    season: int,
    gender: str,
) -> None:
    """
    For each region 1..8: load template for gender, fill RegionText, team1-3 name/score,
    weight1..N wrestler1/wrestler2 (boys 14 weights, girls 12), write SVG and export JPG to
    mt/graphics/Region-Predictions/.
    """
    template_name = (
        "Boys-Regions-Predictions-Template.svg"
        if gender == "boys"
        else "Girls-Regions-Predictions-Template.svg"
    )
    template_path = (
        PROJECT_ROOT / "mt" / "graphics" / "templates" / "regions" / template_name
    )
    if not template_path.exists():
        print(f"Template not found: {template_path}")
        return
    out_dir = PROJECT_ROOT / "mt" / "graphics" / "Region-Predictions"
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        import cairosvg
        from PIL import Image
        _cairosvg_ok = True
    except ImportError:
        _cairosvg_ok = False
        cairosvg = Image = None
        print("  (JPG requires cairosvg and pillow: pip install cairosvg pillow)")
    _inkscape_path = _find_inkscape()
    _inkscape_available = _inkscape_path is not None

    weights = HS_BOYS_WEIGHTS if gender == "boys" else HS_GIRLS_WEIGHTS
    title_prefix = "Boys" if gender == "boys" else "Girls"
    file_prefix = "Boys-Region" if gender == "boys" else "Girls-Region"

    teams_list = load_teams(gender)
    _, region_teams = build_region_teams(teams_list)
    team_abbrev = team_name_to_abbreviation(teams_list)
    regions_sorted = sorted(region_teams.keys(), key=lambda r: (int(r) if r.isdigit() else 999, r))

    ns = {
        "svg": "http://www.w3.org/2000/svg",
        "inkscape": "http://www.inkscape.org/namespaces/inkscape",
    }

    for region_name in regions_sorted:
        region_team_names = region_teams[region_name]
        top_3_list, per_weight = get_region_display_data(rankings_dir, weights, region_team_names)

        tree = ET.parse(template_path)
        root = tree.getroot()

        # Region title
        _set_label_text(root, ns, "Region-Text", f"{title_prefix} Region {region_name}")
        # Top 3 teams (full name at top; abbreviation only in weight-class wrestler lines below)
        for i in range(1, 4):
            if i <= len(top_3_list):
                team_name, score = top_3_list[i - 1]
                _set_label_text(root, ns, f"team{i}-name", team_name)
                _set_label_text(root, ns, f"team{i}-score", f"{score:.1f} pts")
            else:
                _set_label_text(root, ns, f"team{i}-name", "")
                _set_label_text(root, ns, f"team{i}-score", "")
        # Per-weight wrestler1 / wrestler2 (weight1..weightN)
        for idx, weight in enumerate(weights, start=1):
            group = root.find(f".//svg:g[@inkscape:label='weight{idx}']", namespaces=ns)
            if group is None:
                continue
            pairs = per_weight.get(weight, [])
            if len(pairs) > 0:
                r1, n1, t1 = pairs[0]
                w1_line = f"#{r1} {shorten_wrestler_name(n1)} ({team_abbrev.get(t1, t1)})"
            else:
                w1_line = ""
            if len(pairs) > 1:
                r2, n2, t2 = pairs[1]
                w2_line = f"over #{r2} {shorten_wrestler_name(n2)} ({team_abbrev.get(t2, t2)})"
            else:
                w2_line = ""
            for sub_label, text in [("wrestler1", w1_line), ("wrestler2", w2_line)]:
                el = group.find(f".//*[@inkscape:label='{sub_label}']", namespaces=ns)
                if el is not None:
                    _set_wrestler_text(el, ns, text or "")

        svg_path = out_dir / f"{file_prefix}-{region_name}.svg"
        jpg_path = out_dir / f"{file_prefix}-{region_name}.jpg"
        tree.write(svg_path, encoding="utf-8", xml_declaration=True)
        print(f"  ✓ SVG: {svg_path}")

        # JPG: prefer Inkscape so SVG filters (drop shadows) render; fallback to cairosvg
        jpg_path.parent.mkdir(parents=True, exist_ok=True)
        inkscape_ok, inkscape_err = _export_svg_to_jpg_inkscape(svg_path, jpg_path)
        if inkscape_ok:
            print(f"  ✓ JPG: {jpg_path} (via Inkscape)")
        elif _cairosvg_ok:
            if inkscape_err and region_name == regions_sorted[0]:
                print(f"  (Inkscape: {inkscape_err})")
            try:
                png_bytes = cairosvg.svg2png(
                    url=str(svg_path), output_width=1500, output_height=1500
                )
                img = Image.open(BytesIO(png_bytes)).convert("RGB")
                img.save(jpg_path, format="JPEG", quality=95)
                print(f"  ✓ JPG: {jpg_path}")
            except Exception as e:
                print(f"  JPG failed: {e}")
        else:
            if inkscape_err and region_name == regions_sorted[0]:
                print(f"  (Inkscape: {inkscape_err})")
            print(f"  JPG skipped: need Inkscape (for drop shadows) or cairosvg+pillow")

    print(f"✓ Region predictions ({gender}): SVG (and JPG if deps installed) in {out_dir}")


def print_region_top3(
    region_name: str,
    gender: str,
    teams: Dict[str, dict],
    weights: List[int],
    top_n: int = 3,
) -> None:
    """Print top N teams with total points and per-weight breakdown."""
    sorted_teams = sorted(
        teams.values(),
        key=lambda t: (-t["total_points"], t["team"]),
    )[:top_n]

    if not sorted_teams:
        print("  (No teams with scored wrestlers in this region)\n")
        return

    for rank, team_data in enumerate(sorted_teams, 1):
        team_name = team_data["team"]
        total = team_data["total_points"]
        print(f"{rank}. {team_name} — {total:.1f} pts")
        print("   Weight Breakdown:")
        wmap = team_data.get("weights") or {}
        for w in weights:
            slot = wmap.get(w)
            if slot:
                label = placement_label(slot["placement"])
                print(f"     {w:3} lbs: {slot['name']} ({label}, {slot['points']:.1f} pts)")
            else:
                print(f"     {w:3} lbs: (empty)")
        print()
    return


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Regional projected team scores (starter rankings, deterministic table, top 3 per region)"
    )
    parser.add_argument("--season", type=int, required=True, help="Season year (e.g. 2026)")
    parser.add_argument(
        "-gender",
        type=str,
        choices=["boys", "girls"],
        default=None,
        help="Gender; default both",
    )
    parser.add_argument(
        "--rankings-dir",
        type=str,
        default=None,
        help="Override rankings dir (default: frontend/hs-ky-ui/public/data/rankings/<gender>/<season>)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=3,
        help="Number of top teams per region to show (default 3)",
    )
    parser.add_argument(
        "--export-graphics",
        action="store_true",
        help="Export region prediction graphics (boys only): fill template, write SVG + JPG to mt/graphics/Region-Predictions/",
    )
    args = parser.parse_args()

    genders = [args.gender] if args.gender else ["boys", "girls"]

    for gender in genders:
        weights = HS_BOYS_WEIGHTS if gender == "boys" else HS_GIRLS_WEIGHTS
        rankings_dir = Path(args.rankings_dir) if args.rankings_dir else (
            PROJECT_ROOT / "frontend" / "hs-ky-ui" / "public" / "data" / "rankings" / gender / str(args.season)
        )
        if not rankings_dir.exists():
            print(f"[{gender}] Rankings dir not found: {rankings_dir}")
            continue

        teams_list = load_teams(gender)
        _, region_teams = build_region_teams(teams_list)
        regions_sorted = sorted(region_teams.keys(), key=lambda r: (int(r) if r.isdigit() else 999, r))

        print("=" * 80)
        print(f"REGIONAL PROJECTED TEAM SCORES — {gender.upper()} — Season {args.season}")
        print("Source: Regional starter rankings. Scoring: 1st=25, 2nd=22, 3rd=19, 4th=16, 5th=12, 6th=9, 7th=2, 8th=1, 9th/10th=0.5, 11+=0.")
        print("=" * 80)

        for region_name in regions_sorted:
            region_team_names = region_teams[region_name]
            print(f"\nRegion {region_name} – {gender.title()}\n")
            teams = aggregate_regional_team_scores(
                rankings_dir,
                weights,
                region_team_names,
            )
            print_region_top3(region_name, gender, teams, weights, top_n=args.top)

        if args.export_graphics:
            print("\n" + "=" * 80)
            print(f"Region prediction graphics ({gender}): SVG + JPG to mt/graphics/Region-Predictions/")
            print("=" * 80)
            export_region_predictions_graphics(rankings_dir, args.season, gender)

        print("=" * 80)


if __name__ == "__main__":
    main()
