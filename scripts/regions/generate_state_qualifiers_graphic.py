#!/usr/bin/env python3
"""
Generate state qualifiers rankings graphic for girls.

Same layout as the top-24 rankings graphic (create_rankings_release), but shows only
the 16 state qualifiers at each weight—those who wrestled in the 1st and 3rd place
matches at regionals (4 regions × 4 qualifiers = 16).

If a wrestler from region results is not found in rankings, the script HALTS and
prompts for a test string to search. Resolved mappings are saved to:
  data/hs_ky_girls/Regionals/wrestler_lookup.json
so future runs use the override automatically.

Output: mt/graphics/state-qualifiers/ with filenames like hs_state_qualifiers_girls_20260203_100_107.jpg

Usage:
  python scripts/regions/generate_state_qualifiers_graphic.py --season 2026
"""

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

HS_GIRLS_WEIGHTS = [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235]


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _parse_wrestler_and_team(s: str) -> Optional[Tuple[str, str]]:
    """Parse 'Name (Team) RECORD' - extract name and team."""
    m = re.match(r"^(.*)\s+\(([^)]+)\)\s+\d+-\d+", s.strip())
    if not m:
        return None
    return m.group(1).strip(), m.group(2).strip()


def parse_region_results(path: Path, region_name: str) -> Dict[int, List[Tuple[str, str, str]]]:
    """
    Parse Region*-Results.txt for 1st and 3rd place matches.
    Returns: {weight: [(name, team, place), ...]} where place is "1","2","3","4"
    (1st winner, 1st loser, 3rd winner, 3rd loser).
    """
    result: Dict[int, List[Tuple[str, str, str]]] = {}
    text = path.read_text(encoding="utf-8")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    current_weight: Optional[int] = None
    for line in lines:
        if line == "Team Results":
            break
        if line.isdigit():
            current_weight = int(line)
            continue
        if current_weight is None:
            continue

        for prefix, place_winner, place_loser in [
            ("1st Place Match - ", "1", "2"),
            ("3rd Place Match - ", "3", "4"),
        ]:
            if line.startswith(prefix):
                rest = line[len(prefix) :].strip()
                if " won by " in rest and " over " in rest:
                    winner_part, _, after = rest.partition(" won by ")
                    _, _, loser_part = after.partition(" over ")
                    winner = _parse_wrestler_and_team(winner_part)
                    loser = _parse_wrestler_and_team(loser_part)
                    if winner and loser:
                        result.setdefault(current_weight, []).append(
                            (winner[0], winner[1], place_winner)
                        )
                        result.setdefault(current_weight, []).append(
                            (loser[0], loser[1], place_loser)
                        )
                break
    return result


def load_rankings_full(rankings_dir: Path, weight: int) -> List[dict]:
    """Load rankings_full/{weight}.json."""
    path = rankings_dir / f"{weight}.json"
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    return data.get("rankings") or []


def find_wrestler_in_rankings(
    entries: List[dict], name: str, team: str
) -> Optional[dict]:
    """Match wrestler by name and team. Returns full entry or None."""
    norm_team = _normalize(team)
    norm_name = _normalize(name)
    norm_name_no_paren = _normalize(re.sub(r"\s*\([^)]*\)\s*", " ", name).strip())

    for e in entries:
        r_name = (e.get("name") or "").strip()
        r_team = (e.get("team") or "").strip()
        r_norm_team = _normalize(r_team)
        if r_norm_team != norm_team:
            continue
        r_norm_name = _normalize(r_name)
        r_norm_name_no_paren = _normalize(re.sub(r"\s*\([^)]*\)\s*", " ", r_name).strip())
        if norm_name == r_norm_name or norm_name_no_paren == r_norm_name_no_paren:
            return e
        if norm_name_no_paren and r_norm_name_no_paren and norm_name_no_paren == r_norm_name_no_paren:
            return e
        n1, n2 = norm_name_no_paren.split(), r_norm_name_no_paren.split()
        if len(n1) >= 2 and len(n2) >= 2 and n1[-1] == n2[-1]:
            if n1[0] == n2[0] or n1[0].startswith(n2[0]) or n2[0].startswith(n1[0]):
                return e
    return None


def load_team_region_mapping(gender: str) -> Dict[str, str]:
    """Load team -> region from teams.json."""
    path = PROJECT_ROOT / "data" / "team_lists" / f"hs_ky_{gender}" / "teams.json"
    if not path.exists():
        return {}
    mapping = {}
    with path.open("r", encoding="utf-8") as f:
        for t in json.load(f):
            name = (t.get("name") or "").strip()
            region = t.get("region")
            if name and region is not None:
                mapping[name] = str(region)
    return mapping


WRESTLER_LOOKUP_FILE = PROJECT_ROOT / "data" / "hs_ky_girls" / "Regionals" / "wrestler_lookup.json"


def _override_key(name: str, team: str) -> str:
    return f"{name}|{team}"


def load_wrestler_overrides(season: int) -> Dict[int, Dict[str, dict]]:
    """Load wrestler lookup overrides: {weight: {override_key: entry}}."""
    if not WRESTLER_LOOKUP_FILE.exists():
        return {}
    try:
        with WRESTLER_LOOKUP_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    season_data = data.get("overrides", {}).get(str(season), data.get(str(season), {}))
    result: Dict[int, Dict[str, dict]] = {}
    for w_str, entries in season_data.items():
        if isinstance(entries, dict):
            result[int(w_str)] = entries
    return result


def save_wrestler_override(season: int, weight: int, name: str, team: str, entry: dict) -> None:
    """Save a wrestler override to the lookup file."""
    WRESTLER_LOOKUP_FILE.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if WRESTLER_LOOKUP_FILE.exists():
        try:
            with WRESTLER_LOOKUP_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
    if "overrides" not in data:
        data["overrides"] = {}
    if str(season) not in data["overrides"]:
        data["overrides"][str(season)] = {}
    if str(weight) not in data["overrides"][str(season)]:
        data["overrides"][str(season)][str(weight)] = {}
    data["overrides"][str(season)][str(weight)][_override_key(name, team)] = entry
    with WRESTLER_LOOKUP_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"  Saved to {WRESTLER_LOOKUP_FILE}")


def find_wrestler_in_any_weight(
    rankings_dir: Path, name: str, team: str, weights: List[int]
) -> Optional[dict]:
    """Search for wrestler by name+team across all weight rankings. Returns first match."""
    for w in weights:
        entries = load_rankings_full(rankings_dir, w)
        match = find_wrestler_in_rankings(entries, name, team)
        if match:
            return match
    return None


def search_rankings_by_string(entries: List[dict], test_str: str) -> List[dict]:
    """Search rankings by substring in name or team. Case-insensitive."""
    norm = _normalize(test_str)
    if not norm:
        return []
    return [
        e for e in entries
        if norm in _normalize(e.get("name", "")) or norm in _normalize(e.get("team", ""))
    ]


def interactive_resolve_wrestler(
    name: str,
    team: str,
    weight: int,
    place: str,
    region: str,
    rankings_dir: Path,
    weights: List[int],
    season: int,
) -> dict:
    """
    Halt and prompt user to identify wrestler. Search by test string across ALL weights, save override, return entry.
    """
    # Build combined entries from all weights for search (wrestlers may be ranked at different weight)
    entries: List[dict] = []
    for w in weights:
        entries.extend(load_rankings_full(rankings_dir, w))
    print()
    print("=" * 60)
    print("WRESTLER NOT FOUND IN RANKINGS")
    print("=" * 60)
    print(f"  Weight: {weight} lbs")
    print(f"  From region results: {name} ({team})")
    print(f"  Regional place: {place} | Region: {region}")
    print()
    print("Enter a test string to search rankings (name or team substring):")
    print("  (or enter wrestler_id:XXXX to use a specific ID)")
    print()

    while True:
        try:
            test_str = input("> ").strip()
        except EOFError:
            print("Aborted.")
            raise SystemExit(1)
        if not test_str:
            print("Please enter a non-empty string.")
            continue

        if test_str.lower().startswith("wrestler_id:"):
            wid = test_str[12:].strip()
            if wid:
                entry = {
                    "wrestler_id": wid,
                    "name": name,
                    "team": team,
                    "rank": 999,
                }
                save_wrestler_override(season, weight, name, team, entry)
                return entry
            continue

        matches = search_rankings_by_string(entries, test_str)
        if not matches:
            print(f"  No matches for '{test_str}'. Try another string.")
            continue

        while True:
            print(f"  Found {len(matches)} match(es):")
            for i, m in enumerate(matches[:20], 1):
                r = m.get("rank", "?")
                wid = m.get("wrestler_id", "")
                n = m.get("name", "")
                t = m.get("team", "")
                print(f"    {i}. #{r} {n} ({t}) [id={wid}]")
            if len(matches) > 20:
                print(f"    ... and {len(matches) - 20} more")
            print()
            print("Enter number to select, or another search string:")
            try:
                choice = input("> ").strip()
            except EOFError:
                print("Aborted.")
                raise SystemExit(1)
            if not choice:
                continue
            if choice.isdigit():
                idx = int(choice)
                if 1 <= idx <= len(matches):
                    entry = matches[idx - 1]
                    save_entry = {
                        "wrestler_id": entry.get("wrestler_id", ""),
                        "name": (entry.get("name") or "").strip(),
                        "team": (entry.get("team") or "").strip(),
                        "rank": entry.get("rank", 999),
                    }
                    save_wrestler_override(season, weight, name, team, save_entry)
                    return entry
            # Treat as new search string
            test_str = choice
            matches = search_rankings_by_string(entries, test_str)
            if not matches:
                print(f"  No matches for '{test_str}'. Try another string.")
                break


def collect_state_qualifiers(
    regionals_dir: Path,
    rankings_dir: Path,
    weights: List[int],
    season: int,
) -> Dict[int, List[dict]]:
    """
    Collect 16 state qualifiers per weight from all region results.
    Halts and prompts if a wrestler cannot be found (no override).
    Returns {weight: [wrestler_entries sorted by state rank]}.
    """
    qualifiers_by_weight: Dict[int, Set[Tuple[str, str, str, str]]] = {}  # (name, team, place, region)

    for results_file in sorted(regionals_dir.glob("Region*-Results.txt")):
        m = re.match(r"Region(\d+)-Results\.txt", results_file.name, re.I)
        if not m:
            continue
        region_name = m.group(1)
        per_weight = parse_region_results(results_file, region_name)
        for weight, wrestlers in per_weight.items():
            for name, team, place in wrestlers:
                qualifiers_by_weight.setdefault(weight, set()).add((name, team, place, region_name))

    overrides = load_wrestler_overrides(season)

    # Build wrestler entries with rank from rankings_full, sort by state rank
    result: Dict[int, List[dict]] = {}
    for weight in weights:
        qualifiers = qualifiers_by_weight.get(weight, set())
        entries = load_rankings_full(rankings_dir, weight)
        weight_overrides = overrides.get(weight, {})
        wrestler_list: List[dict] = []
        for name, team, place, region in qualifiers:
            match = find_wrestler_in_rankings(entries, name, team)
            if not match:
                # Wrestler may be ranked at a different weight (e.g. qualified at 120, ranked at 114)
                match = find_wrestler_in_any_weight(rankings_dir, name, team, weights)
            if match:
                rank = match.get("rank", 999)
                wid = match.get("wrestler_id", "")
                r_name = (match.get("name") or "").strip()
                r_team = (match.get("team") or "").strip()
                wrestler_list.append({
                    "wrestler_id": wid,
                    "name": r_name,
                    "team": r_team,
                    "rank": rank,
                    "movement": None,
                    "is_new": False,
                    "_place": place,
                    "_region": region,
                })
            else:
                # Check override file
                override_entry = weight_overrides.get(_override_key(name, team))
                if override_entry:
                    wrestler_list.append({
                        "wrestler_id": override_entry.get("wrestler_id", ""),
                        "name": (override_entry.get("name") or name).strip(),
                        "team": (override_entry.get("team") or team).strip(),
                        "rank": override_entry.get("rank", 999),
                        "movement": None,
                        "is_new": False,
                        "_place": place,
                        "_region": region,
                    })
                else:
                    # Halt and prompt user
                    resolved = interactive_resolve_wrestler(
                        name, team, weight, place, region, rankings_dir, weights, season
                    )
                    wrestler_list.append({
                        "wrestler_id": resolved.get("wrestler_id", ""),
                        "name": (resolved.get("name") or name).strip(),
                        "team": (resolved.get("team") or team).strip(),
                        "rank": resolved.get("rank", 999),
                        "movement": None,
                        "is_new": False,
                        "_place": place,
                        "_region": region,
                    })
                    # Update in-memory overrides so we don't prompt again this run
                    weight_overrides[_override_key(name, team)] = resolved
                    overrides[weight] = weight_overrides
        wrestler_list.sort(key=lambda x: (x["rank"], x["name"]))
        # Strip internal metadata for output
        result[weight] = []
        for w in wrestler_list:
            entry = {k: v for k, v in w.items() if not k.startswith("_")}
            entry["_region_place"] = w["_place"]  # "1","2","3","4" for fill_svg_template
            result[weight].append(entry)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate state qualifiers graphic for girls")
    parser.add_argument("--season", type=int, default=2026)
    args = parser.parse_args()

    regionals_dir = PROJECT_ROOT / "data" / "hs_ky_girls" / "Regionals"
    rankings_full_dir = PROJECT_ROOT / "frontend" / "hs-ky-ui" / "public" / "data" / "rankings_full" / "girls" / str(args.season)

    if not regionals_dir.exists():
        print(f"Regionals dir not found: {regionals_dir}")
        return
    if not rankings_full_dir.exists():
        print(f"Rankings full dir not found: {rankings_full_dir}")
        return

    print("Collecting state qualifiers from region results...")
    qualifiers = collect_state_qualifiers(
        regionals_dir, rankings_full_dir, HS_GIRLS_WEIGHTS, args.season
    )

    # Build all_weight_data in format expected by create_rankings_release
    region_mapping = load_team_region_mapping("girls")
    all_weight_data: Dict[str, Tuple[List[dict], Dict[str, str], Dict[str, str]]] = {}

    for weight in HS_GIRLS_WEIGHTS:
        w_str = str(weight)
        wrestlers = qualifiers.get(weight, [])
        region_places = {}
        team_best = {}
        for w in wrestlers:
            wid = w.get("wrestler_id", "")
            team = w.get("team", "")
            rp = w.get("_region_place", "N/A")
            if wid:
                region_places[wid] = rp
            # team_best: highest ranked wrestler per team
            if team:
                existing_wid = team_best.get(team)
                existing_rank = next((x.get("rank", 999) for x in wrestlers if x.get("wrestler_id") == existing_wid), 999) if existing_wid else 999
                if existing_wid is None or (w.get("rank", 999) < existing_rank):
                    team_best[team] = wid
        # Remove _region_place from wrestlers before passing to fill_svg_template
        clean_wrestlers = [{k: v for k, v in w.items() if k != "_region_place"} for w in wrestlers]
        all_weight_data[w_str] = (clean_wrestlers, region_places, team_best)

    import shutil
    import subprocess
    try:
        from PIL import Image
        _pil_ok = True
    except ImportError:
        _pil_ok = False
        Image = None
    _inkscape = shutil.which("inkscape")
    if not _inkscape:
        _inkscape_path = Path("/Applications/Inkscape.app/Contents/MacOS/inkscape")
        if _inkscape_path.exists():
            _inkscape = str(_inkscape_path)
    try:
        import cairosvg
        from io import BytesIO
        _cairosvg_ok = True
    except ImportError:
        _cairosvg_ok = False
        cairosvg = BytesIO = None

    # Import from create_rankings_release (same template fill logic)
    import sys
    sys.path.insert(0, str(PROJECT_ROOT))
    try:
        from scripts.rankings.create_rankings_release import (
            fill_svg_template,
            load_grade_info as load_grade_from_release,
        )
    except ImportError as e:
        print(f"Could not import create_rankings_release: {e}")
        return

    def render_svg_to_jpg(svg_path: Path, jpg_path: Path, width: int = 1500, height: int = 1500) -> bool:
        """Return True if JPG was generated."""
        if not _pil_ok:
            return False
        jpg_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if _cairosvg_ok:
                png_bytes = cairosvg.svg2png(url=str(svg_path), output_width=width, output_height=height)
                img = Image.open(BytesIO(png_bytes)).convert("RGB")
                img.save(jpg_path, format="JPEG", quality=95)
            elif _inkscape:
                png_path = jpg_path.with_suffix(".png")
                subprocess.run([_inkscape, str(svg_path), "--export-type=png", f"--export-filename={png_path}",
                               f"--export-width={width}", f"--export-height={height}"], check=True, capture_output=True)
                img = Image.open(png_path).convert("RGB")
                img.save(jpg_path, format="JPEG", quality=95)
                png_path.unlink(missing_ok=True)
            else:
                return False
            print(f"  ✓ JPG: {jpg_path}")
            return True
        except Exception as e:
            print(f"  JPG failed: {e}")
            return False

    template_path = PROJECT_ROOT / "mt" / "graphics" / "templates" / "top40v1-girls.svg"
    if not template_path.exists():
        print(f"Template not found: {template_path}")
        return

    output_dir = PROJECT_ROOT / "mt" / "graphics" / "state-qualifiers"
    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")

    weight_classes = [str(w) for w in HS_GIRLS_WEIGHTS]
    max_rows = 16

    for i in range(0, len(weight_classes), 2):
        weight1 = weight_classes[i]
        if weight1 not in all_weight_data:
            continue
        wrestlers1, region_places1, team_best1 = all_weight_data[weight1]
        grade_info1 = load_grade_from_release(weight1, "girls")

        if i + 1 < len(weight_classes):
            weight2 = weight_classes[i + 1]
            if weight2 not in all_weight_data:
                continue
            wrestlers2, region_places2, team_best2 = all_weight_data[weight2]
            grade_info2 = load_grade_from_release(weight2, "girls")

            root = fill_svg_template(
                template_path,
                weight1,
                weight2,
                wrestlers1,
                wrestlers2,
                region_mapping,
                region_places1,
                region_places2,
                grade_info1,
                grade_info2,
                team_best1,
                team_best2,
                gender="girls",
                max_rows=max_rows,
            )

            # Clear rows 17-24 (template has 24, we only use 16)
            import xml.etree.ElementTree as ET
            ns = {"svg": "http://www.w3.org/2000/svg", "inkscape": "http://www.inkscape.org/namespaces/inkscape"}
            for row in range(17, 25):
                for label in ["rank_1_", "name_1_", "school_1_", "grade_1_", "region_1_", "rank_2_", "name_2_", "school_2_", "grade_2_", "region_2_"]:
                    el = root.find(f".//svg:text[@inkscape:label='{label}{row}']", namespaces=ns)
                    if el is not None:
                        tspan = el.find("svg:tspan", ns)
                        target = tspan if tspan is not None else el
                        target.text = ""

            svg_filename = f"hs_state_qualifiers_girls_{date_str}_{weight1}_{weight2}.svg"
            svg_path = output_dir / svg_filename
            tree = ET.ElementTree(root)
            tree.write(svg_path, encoding="utf-8", xml_declaration=True)
            print(f"  ✓ SVG: {svg_path}")

            jpg_filename = f"hs_state_qualifiers_girls_{date_str}_{weight1}_{weight2}.jpg"
            jpg_path = output_dir / jpg_filename
            if not render_svg_to_jpg(svg_path, jpg_path, width=1500, height=1500):
                if not _pil_ok:
                    print(f"  (JPG skipped: pip install pillow)")
                elif not _cairosvg_ok and not _inkscape:
                    print(f"  (JPG skipped: pip install cairosvg or install Inkscape)")
        else:
            print(f"  Skipping {weight1} (no pair)")

    print(f"\n✓ State qualifiers graphics: {output_dir}")


if __name__ == "__main__":
    main()
