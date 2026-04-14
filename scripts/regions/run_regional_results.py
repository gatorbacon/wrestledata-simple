#!/usr/bin/env python3
"""
Generate regional results graphics from text files.

Reads Region*-Results.txt from data/hs_ky_{gender}/Regionals/, parses 1st place
matches (winner/loser per weight) and team results (top 3), looks up wrestler
ranks in rankings_starters_{weight}.json, and fills the Results template SVG.
Output: mt/graphics/Region-Results/

Usage:
  python scripts/regions/run_regional_results.py --season 2026
  python scripts/regions/run_regional_results.py --season 2026 -gender girls
"""

import argparse
import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Scoring table for regional team predictions (same as run_regional_xtp)
REGIONAL_PLACEMENT_POINTS = {
    1: 25, 2: 22, 3: 19, 4: 16, 5: 12, 6: 9, 7: 2, 8: 1, 9: 0.5, 10: 0.5,
}

HS_BOYS_WEIGHTS = [106, 113, 120, 126, 132, 138, 144, 150, 157, 165, 175, 190, 215, 285]
HS_GIRLS_WEIGHTS = [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235]


def _normalize(s: str) -> str:
    """Lowercase, strip, collapse spaces."""
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _normalize_name_for_match(name: str) -> str:
    """Remove parenthetical nicknames for matching, e.g. 'Masoka (Ashley) Kilozo' -> 'Masoka Kilozo'."""
    return re.sub(r"\s*\([^)]*\)\s*", " ", (name or "").strip()).strip()


def load_teams(gender: str) -> List[dict]:
    """Load team list from data/team_lists/hs_ky_{gender}/teams.json."""
    path = PROJECT_ROOT / "data" / "team_lists" / f"hs_ky_{gender}" / "teams.json"
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def team_name_to_abbreviation(teams: List[dict]) -> Dict[str, str]:
    """Build map team name -> abbreviation."""
    out: Dict[str, str] = {}
    for t in teams:
        name = (t.get("name") or "").strip()
        abbr = (t.get("abbreviation") or name).strip()
        if name:
            out[name] = abbr
    return out


def build_region_teams(teams: List[dict]) -> Dict[str, Set[str]]:
    """Build region -> set(team names). Only teams with a region."""
    region_teams: Dict[str, Set[str]] = {}
    for t in teams:
        name = (t.get("name") or "").strip()
        region = t.get("region")
        if not name or region is None or (isinstance(region, str) and not region.strip()):
            continue
        region_str = str(region).strip()
        region_teams.setdefault(region_str, set()).add(name)
    return region_teams


def load_starter_rankings_for_weight(rankings_dir: Path, weight: int) -> List[dict]:
    """Load rankings_starters_{weight}.json; starters only (for predictions)."""
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


def _wrestlers_match(
    pred_name: str, pred_team: str, actual_name: str, actual_team: str
) -> bool:
    """Return True if predicted and actual refer to the same wrestler."""
    if _normalize(pred_team) != _normalize(actual_team):
        return False
    n1 = _normalize(pred_name)
    n2 = _normalize(actual_name)
    n1np = _normalize(_normalize_name_for_match(pred_name))
    n2np = _normalize(_normalize_name_for_match(actual_name))
    if n1 == n2 or n1np == n2np:
        return True
    # First name abbreviation match
    p1, p2 = n1np.split(), n2np.split()
    if len(p1) >= 2 and len(p2) >= 2 and p1[-1] == p2[-1]:
        if p1[0] == p2[0] or p1[0].startswith(p2[0]) or p2[0].startswith(p1[0]):
            return True
    return False


def shorten_wrestler_name(name: str, max_length: int = 20) -> str:
    """If name longer than max_length, use first initial + last name."""
    name = (name or "").strip()
    if len(name) <= max_length:
        return name
    parts = name.split()
    if not parts:
        return name[:max_length]
    if len(parts) == 1:
        return name[:max_length]
    return f"{parts[0][0]}. {parts[-1]}"


def load_rankings_for_weight(rankings_dir: Path, weight: int) -> List[dict]:
    """Load rankings_starters_{weight}.json; return list of entries with rank, name, team."""
    path = rankings_dir / f"rankings_starters_{weight}.json"
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    entries = data.get("rankings") or []
    return [e for e in entries if (e.get("team") or "").strip()]


def load_rankings_full_for_weight(rankings_dir: Path, weight: int) -> List[dict]:
    """
    Load rankings_full/{weight}.json (includes non-starters/roster wrestlers).
    Fallback when wrestler not in rankings_starters.
    """
    # rankings_dir is .../rankings/girls/2026; rankings_full is .../rankings_full/girls/2026
    rankings_full_dir = rankings_dir.parent.parent.parent / "rankings_full" / rankings_dir.parent.name / rankings_dir.name
    path = rankings_full_dir / f"{weight}.json"
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    entries = data.get("rankings") or []
    return [e for e in entries if (e.get("team") or "").strip()]


def _load_rankings_combined(rankings_dir: Path, weight: int) -> List[dict]:
    """
    Load entries from rankings_starters first, then add any from rankings_full not already present.
    Ensures we find both starters and roster wrestlers.
    """
    starters = load_rankings_for_weight(rankings_dir, weight)
    starter_ids = {e.get("wrestler_id") for e in starters if e.get("wrestler_id")}
    full = load_rankings_full_for_weight(rankings_dir, weight)
    extra = [e for e in full if e.get("wrestler_id") not in starter_ids]
    return starters + extra


def find_wrestler_rank(
    rankings_dir: Path,
    name: str,
    team: str,
    weights: List[int],
) -> Optional[Tuple[int, str, str]]:
    """
    Match wrestler by name and team in rankings. Searches ALL weight classes.
    Returns (rank, canonical_name, canonical_team) or None if not found.
    Handles: case, parenthetical nicknames, first-name abbreviations (e.g. Alex vs Alexandra).
    """
    norm_team = _normalize(team)
    norm_name = _normalize(name)
    norm_name_no_paren = _normalize(_normalize_name_for_match(name))

    for weight in weights:
        entries = _load_rankings_combined(rankings_dir, weight)
        if not entries:
            continue

        for e in entries:
            r_name = (e.get("name") or "").strip()
            r_team = (e.get("team") or "").strip()
            r_rank = e.get("rank")
            if r_rank is None:
                continue

            r_norm_team = _normalize(r_team)
            if r_norm_team != norm_team:
                continue

            r_norm_name = _normalize(r_name)
            r_norm_name_no_paren = _normalize(_normalize_name_for_match(r_name))

            # Exact match
            if norm_name == r_norm_name or norm_name_no_paren == r_norm_name_no_paren:
                return (r_rank, r_name, r_team)

            # Parenthetical-stripped match
            if norm_name_no_paren and r_norm_name_no_paren and norm_name_no_paren == r_norm_name_no_paren:
                return (r_rank, r_name, r_team)

            # First name abbreviation: "Alex" vs "Alexandra" - one first name is prefix of other
            name_parts = norm_name_no_paren.split()
            r_parts = r_norm_name_no_paren.split()
            if len(name_parts) >= 2 and len(r_parts) >= 2:
                if name_parts[-1] == r_parts[-1]:  # last name matches
                    fn1, fn2 = name_parts[0], r_parts[0]
                    if fn1 == fn2 or fn1.startswith(fn2) or fn2.startswith(fn1):
                        return (r_rank, r_name, r_team)

    return None


def search_rankings_by_string(
    rankings_dir: Path, weights: List[int], search_str: str
) -> List[Tuple[int, str, str, int]]:
    """
    Search rankings for entries where name or team contains search_str (case-insensitive).
    Searches ALL weight classes. Returns list of (rank, name, team, weight).
    """
    norm_search = _normalize(search_str)
    if not norm_search:
        return []
    results: List[Tuple[int, str, str, int]] = []
    for weight in weights:
        entries = _load_rankings_combined(rankings_dir, weight)
        for e in entries:
            r_rank = e.get("rank")
            if r_rank is None:
                continue
            r_name = (e.get("name") or "").strip()
            r_team = (e.get("team") or "").strip()
            if norm_search in _normalize(r_name) or norm_search in _normalize(r_team):
                results.append((r_rank, r_name, r_team, weight))
    return results


def interactive_resolve_wrestler(
    rankings_dir: Path,
    weight: int,
    name: str,
    team: str,
    role: str,
    weights: List[int],
) -> Optional[Tuple[int, str, str]]:
    """
    When a wrestler isn't found, pause and prompt user for a search string.
    Search rankings, display matches, let user pick one or skip.
    Returns (rank, canonical_name, canonical_team) or None (use "?" in graphic).
    """
    print(f"\n  ⚠ Wrestler not found: {name} ({team}) — {role} at {weight} lbs")
    print("  Enter a partial search string (name or school), or 'skip' to use ?")
    search_str = ""
    while True:
        if not search_str:
            try:
                search_str = input("  Search: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n  (skipped)")
                return None
            if not search_str:
                continue
            if search_str.lower() == "skip":
                return None
        matches = search_rankings_by_string(rankings_dir, weights, search_str)
        if not matches:
            print(f"  No matches for '{search_str}'. Try again or 'skip'.")
            search_str = ""
            continue
        print(f"  Found {len(matches)} match(es):")
        for i, (rank, r_name, r_team, r_weight) in enumerate(matches[:20], 1):
            print(f"    {i}. #{rank} {r_name} ({r_team}) — {r_weight} lbs")
        if len(matches) > 20:
            print(f"    ... and {len(matches) - 20} more")
        print("  Enter number to select, or new search string, or 'skip':")
        try:
            choice = input("  Choice: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  (skipped)")
            return None
        if not choice:
            continue
        if choice.lower() == "skip":
            return None
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= min(len(matches), 20):
                rank, r_name, r_team, _ = matches[idx - 1]
                return (rank, r_name, r_team)
            print(f"  Invalid. Enter 1-{min(len(matches), 20)}.")
        else:
            search_str = choice


def _apply_replacements_to_file(
    path: Path,
    replacements: Dict[int, Dict[str, Tuple[Tuple[str, str], Tuple[str, str]]]],
    weights: List[int],
) -> None:
    """
    Update the results file with canonical name/team from rankings.
    replacements: {weight: {"winner": ((old_name, old_team), (new_name, new_team)), "loser": ...}}
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    current_weight: Optional[int] = None
    first_place_prefix = "1st Place Match - "
    new_lines: List[str] = []

    for line in lines:
        if line.strip().isdigit():
            current_weight = int(line.strip())
            new_lines.append(line)
            continue
        if line == "Team Results":
            current_weight = None
            new_lines.append(line)
            continue

        if current_weight is not None and line.strip().startswith(first_place_prefix):
            repl = replacements.get(current_weight)
            if repl:
                rest = line[line.index(first_place_prefix) + len(first_place_prefix) :]
                if " won by " in rest and " over " in rest:
                    winner_part, _, after = rest.partition(" won by ")
                    _, _, loser_part = after.partition(" over ")
                    winner_parsed = _parse_wrestler_and_team(winner_part)
                    loser_parsed = _parse_wrestler_and_team(loser_part)
                    if winner_parsed and "winner" in repl:
                        old_n, old_t = repl["winner"][0]
                        new_n, new_t = repl["winner"][1]
                        if (winner_parsed[0], winner_parsed[1]) == (old_n, old_t):
                            old_str = f"{old_n} ({old_t})"
                            new_str = f"{new_n} ({new_t})"
                            line = line.replace(old_str, new_str, 1)
                    if loser_parsed and "loser" in repl:
                        old_n, old_t = repl["loser"][0]
                        new_n, new_t = repl["loser"][1]
                        if (loser_parsed[0], loser_parsed[1]) == (old_n, old_t):
                            old_str = f"{old_n} ({old_t})"
                            new_str = f"{new_n} ({new_t})"
                            line = line.replace(old_str, new_str, 1)
        new_lines.append(line)

    path.write_text("\n".join(new_lines) + ("\n" if text.endswith("\n") else ""), encoding="utf-8")
    print(f"  ✓ Updated results file: {path}")


def _parse_wrestler_and_team(s: str) -> Optional[Tuple[str, str]]:
    """
    Parse "Name (Team) RECORD" or "Name (Nickname) Last (Team) RECORD" - extract name and team.
    Uses last parenthetical before record (handles names like "Corey (Onna) Dalmida (Fort Campbell) 8-4").
    Handles team names with nested parens like "Trinity (Louisville)".
    """
    m = re.match(r"^(.*)\s+\(([^)]*(?:\([^)]*\)[^)]*)*)\)\s+\d+-\d+", s.strip())
    if not m:
        return None
    return m.group(1).strip(), m.group(2).strip()


def parse_results_file(path: Path) -> Tuple[Dict[int, Tuple[str, str, str, str]], List[Tuple[str, float]]]:
    """
    Parse Region*-Results.txt.
    Returns:
      - per_weight: {weight: (winner_name, winner_team, loser_name, loser_team)}
      - top_3_teams: [(team_name, score), ...]
    """
    per_weight: Dict[int, Tuple[str, str, str, str]] = {}
    top_3_teams: List[Tuple[str, float]] = []

    text = path.read_text(encoding="utf-8")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    current_weight: Optional[int] = None
    in_team_results = False

    # "1st Place Match - WinnerPart won by METHOD over LoserPart"
    first_place_prefix = "1st Place Match - "

    for line in lines:
        if line == "Team Results":
            in_team_results = True
            continue

        if in_team_results:
            parts = line.split("\t")
            if len(parts) >= 3:
                try:
                    rank = int(parts[0].strip())
                    team_name = parts[1].strip()
                    score = float(parts[2].strip())
                    if rank <= 3:
                        top_3_teams.append((team_name, score))
                except (ValueError, IndexError):
                    pass
            continue

        if line.isdigit():
            current_weight = int(line)
            continue

        if line.startswith(first_place_prefix) and current_weight is not None:
            rest = line[len(first_place_prefix) :].strip()
            if " over " in rest:
                winner_part, _, loser_part = rest.partition(" over ")
                # Strip " won by X" or " won in X" from winner (handles "won in sudden victory - 1", etc.)
                winner_part = re.sub(r"\s+won\s+(?:by|in)\s+.*$", "", winner_part.strip())
                winner = _parse_wrestler_and_team(winner_part)
                loser = _parse_wrestler_and_team(loser_part.strip())
                if winner and loser:
                    per_weight[current_weight] = (
                        winner[0],
                        winner[1],
                        loser[0],
                        loser[1],
                    )
            current_weight = None

    return per_weight, top_3_teams[:3]


def _set_label_text(root: ET.Element, ns: dict, label: str, value: str) -> None:
    """Find text by inkscape label, replace its text."""
    el = root.find(f".//svg:text[@inkscape:label='{label}']", namespaces=ns)
    if el is None:
        return
    tspan = el.find("svg:tspan", ns)
    target = tspan if tspan is not None else el
    target.text = value or ""


def _set_wrestler_text(el: ET.Element, ns: dict, value: str) -> None:
    """Replace text in wrestler element (handles nested tspan)."""
    tspan = el.find("svg:tspan", ns)
    if tspan is None:
        el.text = value or ""
        return
    inner = tspan.find("svg:tspan", ns)
    target = inner if inner is not None else tspan
    target.text = value or ""


def _find_inkscape() -> Optional[str]:
    """Path to Inkscape executable, or None."""
    exe = shutil.which("inkscape")
    if exe:
        return exe
    mac_path = Path("/Applications/Inkscape.app/Contents/MacOS/inkscape")
    if mac_path.is_file():
        return str(mac_path)
    return None


def _export_svg_to_jpg_inkscape(
    svg_path: Path, jpg_path: Path, width: int = 1500, height: int = 1500
) -> Tuple[bool, Optional[str]]:
    """Export SVG to JPG via Inkscape."""
    inkscape = _find_inkscape()
    if not inkscape:
        return False, "Inkscape not found"
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
    except Exception as e:
        if png_path.exists():
            png_path.unlink(missing_ok=True)
        return False, str(e)


def export_region_results_graphics(
    results_path: Path,
    rankings_dir: Path,
    gender: str,
    region_name: str,
    season: int,
    interactive: bool = True,
) -> bool:
    """
    Fill Results template for one region, write SVG and JPG to mt/graphics/Region-Results/.
    Returns True on success.
    """
    template_name = (
        "Boys-Regions-Results-Template.svg"
        if gender == "boys"
        else "Girls-Regions-Results-Template.svg"
    )
    template_path = PROJECT_ROOT / "mt" / "graphics" / "templates" / "regions" / template_name
    if not template_path.exists():
        print(f"  Template not found: {template_path}")
        return False

    per_weight, top_3_teams = parse_results_file(results_path)
    weights = HS_BOYS_WEIGHTS if gender == "boys" else HS_GIRLS_WEIGHTS
    title_prefix = "Boys" if gender == "boys" else "Girls"
    file_prefix = "Boys-Region" if gender == "boys" else "Girls-Region"

    teams_list = load_teams(gender)
    team_abbrev = team_name_to_abbreviation(teams_list)

    out_dir = PROJECT_ROOT / "mt" / "graphics" / "Region-Results"
    out_dir.mkdir(parents=True, exist_ok=True)

    ns = {
        "svg": "http://www.w3.org/2000/svg",
        "inkscape": "http://www.inkscape.org/namespaces/inkscape",
    }

    tree = ET.parse(template_path)
    root = tree.getroot()

    # Region title
    _set_label_text(root, ns, "Region-Text", f"{title_prefix} Region {region_name}")

    # Top 3 teams
    for i in range(1, 4):
        if i <= len(top_3_teams):
            team_name, score = top_3_teams[i - 1]
            display_name = team_name.replace(" High School", "").replace("High School ", "").strip() if "High School" in team_name else team_name
            _set_label_text(root, ns, f"team{i}-name", display_name)
            _set_label_text(root, ns, f"team{i}-score", f"{score:.1f} pts")
        else:
            _set_label_text(root, ns, f"team{i}-name", "")
            _set_label_text(root, ns, f"team{i}-score", "")

    # Per-weight: wrestler1 = winner (1st), wrestler2 = loser (2nd)
    # Track replacements to persist to file when canonical (name, team) differs from file
    replacements: Dict[int, Dict[str, Tuple[Tuple[str, str], Tuple[str, str]]]] = {}

    for idx, weight in enumerate(weights, start=1):
        group = root.find(f".//svg:g[@inkscape:label='weight{idx}']", namespaces=ns)
        if group is None:
            continue

        pair = per_weight.get(weight)
        if pair:
            winner_name, winner_team, loser_name, loser_team = pair
            r1 = find_wrestler_rank(rankings_dir, winner_name, winner_team, weights)
            if r1 is None and interactive:
                r1 = interactive_resolve_wrestler(
                    rankings_dir, weight, winner_name, winner_team, "1st place", weights
                )
            r2 = find_wrestler_rank(rankings_dir, loser_name, loser_team, weights)
            if r2 is None and interactive:
                r2 = interactive_resolve_wrestler(
                    rankings_dir, weight, loser_name, loser_team, "2nd place", weights
                )
            rank1 = str(r1[0]) if r1 is not None else "?"
            rank2 = str(r2[0]) if r2 is not None else "?"
            # Use canonical name/team when we have a match
            w_name, w_team = (r1[1], r1[2]) if r1 else (winner_name, winner_team)
            l_name, l_team = (r2[1], r2[2]) if r2 else (loser_name, loser_team)
            w1_line = f"#{rank1} {shorten_wrestler_name(w_name)} ({team_abbrev.get(w_team, w_team)})"
            w2_line = f"over #{rank2} {shorten_wrestler_name(l_name)} ({team_abbrev.get(l_team, l_team)})"
            # Record replacements when canonical differs from file (for persistence)
            if r1 and (r1[1], r1[2]) != (winner_name, winner_team):
                replacements.setdefault(weight, {})["winner"] = (
                    (winner_name, winner_team),
                    (r1[1], r1[2]),
                )
            if r2 and (r2[1], r2[2]) != (loser_name, loser_team):
                replacements.setdefault(weight, {})["loser"] = (
                    (loser_name, loser_team),
                    (r2[1], r2[2]),
                )
        else:
            w1_line = ""
            w2_line = ""

        for sub_label, text in [("wrestler1", w1_line), ("wrestler2", w2_line)]:
            el = group.find(f".//*[@inkscape:label='{sub_label}']", namespaces=ns)
            if el is not None:
                _set_wrestler_text(el, ns, text or "")

    # Persist replacements to the results file
    if replacements:
        _apply_replacements_to_file(results_path, replacements, weights)

    svg_path = out_dir / f"{file_prefix}-{region_name}.svg"
    jpg_path = out_dir / f"{file_prefix}-{region_name}.jpg"
    tree.write(svg_path, encoding="utf-8", xml_declaration=True)
    print(f"  ✓ SVG: {svg_path}")

    # JPG export
    try:
        import cairosvg
        from PIL import Image
        _cairosvg_ok = True
    except ImportError:
        _cairosvg_ok = False
        cairosvg = Image = None

    inkscape_ok, inkscape_err = _export_svg_to_jpg_inkscape(svg_path, jpg_path)
    if inkscape_ok:
        print(f"  ✓ JPG: {jpg_path} (via Inkscape)")
    elif _cairosvg_ok:
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
        if inkscape_err:
            print(f"  (JPG skipped: {inkscape_err})")

    return True


def compute_prediction_accuracy(
    results_path: Path,
    rankings_dir: Path,
    gender: str,
    region_name: str,
    weights: List[int],
    region_team_names: Set[str],
) -> Tuple[int, int, bool]:
    """
    Compare actual results vs predictions (highest ranked starter in region).
    Returns (champions_correct, total_weights, team_champion_correct).
    """
    per_weight, top_3_teams = parse_results_file(results_path)
    champions_correct = 0
    total_weights = 0

    for weight in weights:
        actual = per_weight.get(weight)
        if not actual:
            continue
        total_weights += 1
        actual_winner_name, actual_winner_team = actual[0], actual[1]

        # Predicted = highest ranked starter in region at this weight
        entries = load_starter_rankings_for_weight(rankings_dir, weight)
        in_region = [e for e in entries if (e.get("team") or "").strip() in region_team_names]
        in_region.sort(key=lambda e: (e.get("rank") or 9999, e.get("wrestler_id", "")))
        if in_region:
            pred_name = (in_region[0].get("name") or "").strip()
            pred_team = (in_region[0].get("team") or "").strip()
            if _wrestlers_match(pred_name, pred_team, actual_winner_name, actual_winner_team):
                champions_correct += 1

    # Predicted team champion = top team from starter-based scoring
    teams: Dict[str, float] = {}
    for weight in weights:
        entries = load_starter_rankings_for_weight(rankings_dir, weight)
        in_region = [e for e in entries if (e.get("team") or "").strip() in region_team_names]
        in_region.sort(key=lambda e: (e.get("rank") or 9999, e.get("wrestler_id", "")))
        for placement, entry in enumerate(in_region, start=1):
            pts = REGIONAL_PLACEMENT_POINTS.get(placement, 0.0)
            team = (entry.get("team") or "").strip()
            if team:
                teams[team] = teams.get(team, 0.0) + pts
    predicted_team = ""
    if teams:
        predicted_team = max(teams, key=lambda t: teams[t])

    actual_team = ""
    if top_3_teams:
        actual_team = top_3_teams[0][0]

    team_correct = bool(
        predicted_team and actual_team and _normalize(predicted_team) == _normalize(actual_team)
    )
    return champions_correct, total_weights, team_correct


def discover_results_files() -> List[Tuple[Path, str, str]]:
    """
    Find all Region*-Results.txt files.
    Returns [(path, gender, region_name), ...]
    """
    found: List[Tuple[Path, str, str]] = []
    for gender in ("girls", "boys"):
        regionals_dir = PROJECT_ROOT / "data" / f"hs_ky_{gender}" / "Regionals"
        if not regionals_dir.exists():
            continue
        for p in regionals_dir.glob("Region*-Results.txt"):
            m = re.match(r"Region(\d+)-Results\.txt", p.name, re.IGNORECASE)
            if m:
                found.append((p, gender, m.group(1)))
    return sorted(found, key=lambda x: (x[1], int(x[2])))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate regional results graphics from text files"
    )
    parser.add_argument("--season", type=int, default=2026, help="Season year (e.g. 2026)")
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
        help="Override rankings dir",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Use ? for unmatched wrestlers instead of prompting (for batch/CI)",
    )
    args = parser.parse_args()

    results_files = discover_results_files()
    if not results_files:
        print("No Region*-Results.txt files found in data/hs_ky_{girls,boys}/Regionals/")
        return

    if args.gender:
        results_files = [(p, g, r) for p, g, r in results_files if g == args.gender]

    rankings_base = (
        Path(args.rankings_dir)
        if args.rankings_dir
        else PROJECT_ROOT / "frontend" / "hs-ky-ui" / "public" / "data" / "rankings"
    )

    print("=" * 60)
    print("REGIONAL RESULTS GRAPHICS")
    print("=" * 60)

    # Accumulate prediction accuracy per gender
    accuracy_by_gender: Dict[str, List[Tuple[str, int, int, bool]]] = {"girls": [], "boys": []}

    for results_path, gender, region_name in results_files:
        rankings_dir = rankings_base / gender / str(args.season)
        if not rankings_dir.exists():
            print(f"[{gender} Region {region_name}] Rankings dir not found: {rankings_dir}")
            continue
        print(f"\n{gender.title()} Region {region_name}: {results_path.name}")
        export_region_results_graphics(
            results_path,
            rankings_dir,
            gender,
            region_name,
            args.season,
            interactive=not args.non_interactive,
        )

        # Prediction accuracy vs actual results
        teams_list = load_teams(gender)
        region_teams = build_region_teams(teams_list)
        region_team_names = region_teams.get(region_name, set())
        weights = HS_GIRLS_WEIGHTS if gender == "girls" else HS_BOYS_WEIGHTS
        champ_ok, total_w, team_ok = compute_prediction_accuracy(
            results_path, rankings_dir, gender, region_name, weights, region_team_names
        )
        accuracy_by_gender[gender].append((region_name, champ_ok, total_w, team_ok))
        print(f"  Predictions: {champ_ok}/{total_w} champions correct, team champion {'✓' if team_ok else '✗'}")

    print("\n" + "=" * 60)
    print("Output: mt/graphics/Region-Results/")
    print("=" * 60)

    # Summary: prediction accuracy
    for gender in ("girls", "boys"):
        entries = accuracy_by_gender[gender]
        if not entries:
            continue
        total_champ = sum(e[1] for e in entries)
        total_weights = sum(e[2] for e in entries)
        team_correct = sum(1 for e in entries if e[3])
        n_regions = len(entries)
        print(f"\n{gender.upper()} PREDICTION ACCURACY:")
        for region_name, champ_ok, total_w, team_ok in entries:
            print(f"  Region {region_name}: {champ_ok}/{total_w} champions, team {'✓' if team_ok else '✗'}")
        print(f"  Total: {total_champ}/{total_weights} champions correct, {team_correct}/{n_regions} team champions correct")


if __name__ == "__main__":
    main()
