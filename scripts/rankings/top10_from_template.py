#!/usr/bin/env python3
"""
Fill the Top-10 SVG template with rankings data and a feature photo.

Template:
  - Path: mt/graphics/templates/top10-template.svg
  - Text elements are tagged with inkscape:label attributes:
      * name1..name10   – wrestler names (will be converted to ALL CAPS)
      * school1..school10 – school names (ALL CAPS)
      * weightclass     – weight class label text
  - The background image node has:
      * id="bgimage" and inkscape:label="bgimage"
      * xlink:href="data:image/jpeg;base64,..."

This script:
  - Reads rankings_{weight}.json for the given season/weight.
  - Writes the top 10 names / schools into the labeled text nodes.
  - Updates the weightclass text.
  - Replaces the bgimage's xlink:href with a square feature photo for the #1 wrestler.
    * Photo path is resolved as:
         {images_dir}/{season}/{wrestler_id}.jpg/.jpeg/.png
    * If the source image is not square, the script exits with a clear error.
    * If it is square but not 1500x1500, it is resized to 1500x1500 before embedding.
  - Saves an output SVG.
  - If cairosvg is installed, also renders a JPG version.

Usage example:

  .venv/bin/python scripts/rankings/top10_from_template.py \\
      -season 2026 \\
      -weight-class 125 \\
      -images-dir assets/wrestler_photos \\
      -out-base mt/graphics/2026/top10_125
"""

from __future__ import annotations

import argparse
import base64
import json
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional
import xml.etree.ElementTree as ET

from PIL import Image


RANKINGS_DIR = Path("mt/rankings_data")
TEMPLATE_PATH = Path("mt/graphics/templates/top10-template.svg")


def _load_rankings_from_file(rankings_path: Path) -> List[Dict]:
    """Load a rankings_*.json file and return list sorted by numeric rank."""
    with rankings_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    entries = data.get("rankings", [])

    cleaned: List[Dict] = []
    for e in entries:
        r = e.get("rank")
        wid = e.get("wrestler_id")
        if wid is None or r is None:
            continue
        try:
            rank_int = int(r)
        except (TypeError, ValueError):
            # Skip UNR / non-numeric entries
            continue
        cleaned.append(
            {
                "rank": rank_int,
                "wrestler_id": wid,
                "name": e.get("name", "Unknown"),
                "team": e.get("team", "Unknown"),
                "record": e.get("record", ""),
                "is_starter": bool(e.get("is_starter", True)),
            }
        )

    cleaned.sort(key=lambda x: x["rank"])
    return cleaned


def load_rankings(season: int, weight_class: str) -> List[Dict]:
    """
    Load current rankings_{weight}.json for the given season/weight,
    filtered to starters only.
    """
    rankings_path = RANKINGS_DIR / str(season) / f"rankings_{weight_class}.json"
    if not rankings_path.exists():
        raise FileNotFoundError(f"Rankings file not found: {rankings_path}")
    all_entries = _load_rankings_from_file(rankings_path)
    return [e for e in all_entries if e.get("is_starter", True)]


def resolve_photo_path(images_dir: Path, season: int, wrestler_id: str) -> Optional[Path]:
    """Try to find a photo file for the wrestler under images_dir/season/."""
    season_dir = images_dir / str(season)
    candidates = [
        season_dir / f"{wrestler_id}.jpg",
        season_dir / f"{wrestler_id}.jpeg",
        season_dir / f"{wrestler_id}.png",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def load_and_prepare_square_photo(photo_path: Path) -> bytes:
    """
    Load photo, ensure it is square, resize to 1500x1500 if needed,
    and return JPEG-encoded bytes.
    """
    img = Image.open(photo_path).convert("RGB")
    w, h = img.size
    if w != h:
        raise SystemExit(
            f"Feature photo at {photo_path} is not square (size {w}x{h}).\n"
            f"Please provide a square image so it can be resized to 1500x1500."
        )

    if w != 1500:
        img = img.resize((1500, 1500), Image.LANCZOS)

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def embed_photo_data_url(root: ET.Element, jpeg_bytes: bytes) -> None:
    """Replace bgimage's xlink:href data URL with the provided JPEG bytes."""
    ns = {
        "svg": "http://www.w3.org/2000/svg",
        "inkscape": "http://www.inkscape.org/namespaces/inkscape",
        "xlink": "http://www.w3.org/1999/xlink",
    }

    bg = root.find(".//svg:image[@id='bgimage']", ns)
    if bg is None:
        raise SystemExit(
            "Could not find <image> element with id='bgimage' in the SVG template."
        )

    b64 = base64.b64encode(jpeg_bytes).decode("ascii")
    data_url = f"data:image/jpeg;base64,{b64}"
    bg.set("{http://www.w3.org/1999/xlink}href", data_url)


def fill_text_labels(
    root: ET.Element,
    rankings: List[Dict],
    weight_class_label: str,
    rank_deltas: Optional[List[Optional[int]]] = None,
) -> None:
    """
    Fill name/school/weightclass text nodes in the SVG and optionally
    per-rank delta labels (delta1..delta10).
    """
    ns = {
        "svg": "http://www.w3.org/2000/svg",
        "inkscape": "http://www.inkscape.org/namespaces/inkscape",
    }

    # Names and schools for top 10
    for idx in range(1, 11):
        entry = rankings[idx - 1] if idx - 1 < len(rankings) else None
        name_text = entry["name"].upper() if entry else ""
        if entry:
            team_raw = entry.get("team", "Unknown")
            record_raw = (entry.get("record") or "").strip()
            # Keep school in ALL CAPS for consistency with the template,
            # and append record in parentheses when available.
            if record_raw:
                school_text = f"{team_raw.upper()}   ({record_raw})"
            else:
                school_text = team_raw.upper()
        else:
            school_text = ""
        delta_val = (
            rank_deltas[idx - 1] if rank_deltas and idx - 1 < len(rank_deltas) else None
        )

        # name{idx}
        name_el = root.find(
            f".//svg:text[@inkscape:label='name{idx}']", namespaces=ns
        )
        if name_el is not None:
            tspan = name_el.find("svg:tspan", ns)
            target = tspan if tspan is not None else name_el
            target.text = name_text

        # school{idx}
        school_el = root.find(
            f".//svg:text[@inkscape:label='school{idx}']", namespaces=ns
        )
        if school_el is not None:
            tspan = school_el.find("svg:tspan", ns)
            target = tspan if tspan is not None else school_el
            target.text = school_text

        # delta{idx} – change in rank (e.g., "+3" or "-2")
        delta_el = root.find(
            f".//svg:text[@inkscape:label='delta{idx}']", namespaces=ns
        )
        if delta_el is not None:
            tspan = delta_el.find("svg:tspan", ns)
            target = tspan if tspan is not None else delta_el

            # Parse existing style from the actual rendered element (tspan if present)
            # into a dict so we can tweak fill/display.
            style_src = target
            style_str = style_src.get("style", "")
            style_parts = [
                part.strip() for part in style_str.split(";") if part.strip()
            ]
            style_dict: Dict[str, str] = {}
            for part in style_parts:
                if ":" not in part:
                    continue
                k, v = part.split(":", 1)
                style_dict[k.strip()] = v.strip()

            if delta_val is None or delta_val == 0:
                # No movement or no data: hide the label.
                target.text = ""
                style_dict["display"] = "none"
            elif isinstance(delta_val, str) and delta_val == "N":
                # New to the rankings at this weight: show green "N".
                target.text = "N"
                style_dict.pop("display", None)
                style_dict["fill"] = "#17c517"
            elif isinstance(delta_val, int):
                # Show movement with color-coded +/- value.
                text_val = f"+{delta_val}" if delta_val > 0 else str(delta_val)
                target.text = text_val
                style_dict.pop("display", None)
                style_dict["fill"] = "#17c517" if delta_val > 0 else "#d40000"
            else:
                # Fallback: hide anything unexpected.
                target.text = ""
                style_dict["display"] = "none"

            # Rebuild style string.
            new_style = ";".join(f"{k}:{v}" for k, v in style_dict.items())
            # Apply to both the container <text> and inner <tspan> so the
            # fill/display definitely take effect regardless of where the
            # template defined them.
            delta_el.set("style", new_style)
            if tspan is not None:
                tspan.set("style", new_style)

    # Weight class label
    wc_el = root.find(
        ".//svg:text[@inkscape:label='weightclass']",
        namespaces=ns,
    )
    if wc_el is not None:
        tspan = wc_el.find("svg:tspan", ns)
        target = tspan if tspan is not None else wc_el
        target.text = weight_class_label


def save_svg(root: ET.Element, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(root)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)


def render_jpg(svg_path: Path, jpg_path: Path) -> None:
    """
    Render SVG to JPG using cairosvg (if available).
    If cairosvg is not installed, print a message and skip JPG generation.
    """
    try:
        import cairosvg  # type: ignore
    except ImportError:
        print(
            "cairosvg is not installed; skipping JPG render.\n"
            "To enable JPG output, install it with:\n"
            "  .venv/bin/pip install cairosvg"
        )
        return

    jpg_path.parent.mkdir(parents=True, exist_ok=True)
    # Render to PNG in memory, then convert to JPG via Pillow to ensure RGB
    png_bytes = cairosvg.svg2png(url=str(svg_path))
    img = Image.open(BytesIO(png_bytes)).convert("RGB")
    img.save(jpg_path, format="JPEG", quality=95)
    print(f"JPG graphic written to {jpg_path}")


def _parse_archive_timestamp(name: str) -> Optional[datetime]:
    """Parse rankings_archive directory names (YYYYMMDD-HHMMSS) into datetimes."""
    try:
        return datetime.strptime(name, "%Y%m%d-%H%M%S")
    except ValueError:
        return None


def load_historical_rankings(
    season: int,
    weight_class: str,
    days_ago: int,
) -> List[Dict]:
    """
    Load rankings from the archive as of N days ago.

    We use the snapshot whose timestamp is the latest one at or before
    11:59pm on the target day. If none exist, returns an empty list.
    """
    archive_root = RANKINGS_DIR / str(season) / "rankings_archive"
    if not archive_root.exists():
        return []

    today = datetime.now().date()
    target_date = today - timedelta(days=days_ago)
    target_dt = datetime(
        target_date.year, target_date.month, target_date.day, 23, 59, 59
    )

    best_dir: Optional[Path] = None
    best_ts: Optional[datetime] = None

    for child in archive_root.iterdir():
        if not child.is_dir():
            continue
        ts = _parse_archive_timestamp(child.name)
        if ts is None or ts > target_dt:
            continue
        if best_ts is None or ts > best_ts:
            best_ts = ts
            best_dir = child

    if best_dir is None:
        return []

    rankings_path = best_dir / f"rankings_{weight_class}.json"
    if not rankings_path.exists():
        return []

    all_entries = _load_rankings_from_file(rankings_path)
    return [e for e in all_entries if e.get("is_starter", True)]


def compute_rank_deltas(
    current_rankings: List[Dict], historical_rankings: List[Dict]
) -> List[Optional[object]]:
    """
    Compute change in rank for the current top 10 vs historical snapshot.

    A positive delta means the wrestler moved UP (e.g., from 8 -> 3 yields +5).
    If a wrestler was not present in the historical rankings, the delta is None.
    """
    if not historical_rankings:
        return [None] * 10

    # Map wrestler_id -> position among starters in the historical snapshot
    # (1-based index in the starters-only list).
    prev_by_id: Dict[str, int] = {
        e["wrestler_id"]: idx + 1 for idx, e in enumerate(historical_rankings)
    }

    deltas: List[Optional[object]] = []
    for idx, entry in enumerate(current_rankings[:10]):
        wid = entry["wrestler_id"]
        # Position among current starters (1-based index in current list)
        curr_pos = idx + 1
        prev_rank = prev_by_id.get(wid)
        if prev_rank is None:
            # New to this weight/ranked set since the historical snapshot.
            deltas.append("N")
        else:
            deltas.append(prev_rank - curr_pos)

    # Pad to length 10 so fill_text_labels can index safely.
    while len(deltas) < 10:
        deltas.append(None)

    return deltas


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Fill the Top-10 SVG template with rankings and a feature photo, "
            "and optionally render a JPG."
        )
    )
    parser.add_argument(
        "-season",
        type=int,
        required=True,
        help="Season year (e.g., 2026)",
    )
    parser.add_argument(
        "-weight-class",
        required=True,
        help="Weight class string (e.g., 125, 133, 141)",
    )
    parser.add_argument(
        "-images-dir",
        default="assets/wrestler_photos",
        help=(
            "Base directory for wrestler photos. "
            "Photos are expected at {images-dir}/{season}/{wrestler_id}.jpg (or .png)."
        ),
    )
    parser.add_argument(
        "-out-base",
        default=None,
        help=(
            "Base path (without extension) for output files. "
            "Defaults to mt/graphics/{season}/top10_{weight}."
        ),
    )
    parser.add_argument(
        "-delta-days",
        type=int,
        required=True,
        help=(
            "Number of days back to compare rankings for the delta labels "
            "(compare vs rankings active at 11:59pm N days ago)."
        ),
    )

    args = parser.parse_args()

    season = args.season
    weight_class = str(args.weight_class)
    images_dir = Path(args.images_dir)
    delta_days = int(args.delta_days)

    rankings = load_rankings(season, weight_class)
    if not rankings:
        raise SystemExit(
            f"No ranked wrestlers found in rankings_{weight_class}.json "
            f"for season {season}."
        )

    top1 = rankings[0]
    wid = top1["wrestler_id"]

    photo_path = resolve_photo_path(images_dir, season, wid)
    if not photo_path:
        raise SystemExit(
            f"No photo found for #1 wrestler {top1['name']} ({top1['team']}).\n"
            f"Expected a square image at one of:\n"
            f"  {images_dir}/{season}/{wid}.jpg\n"
            f"  {images_dir}/{season}/{wid}.jpeg\n"
            f"  {images_dir}/{season}/{wid}.png"
        )

    jpeg_bytes = load_and_prepare_square_photo(photo_path)

    # Historical rankings for delta calculation
    historical = load_historical_rankings(season, weight_class, delta_days)
    rank_deltas = compute_rank_deltas(rankings, historical)

    if not TEMPLATE_PATH.exists():
        raise SystemExit(f"SVG template not found: {TEMPLATE_PATH}")

    tree = ET.parse(TEMPLATE_PATH)
    root = tree.getroot()

    # Fill texts and embed photo. Show weight as "<wt> lbs".
    fill_text_labels(
        root,
        rankings,
        weight_class_label=f"{weight_class} lbs",
        rank_deltas=rank_deltas,
    )
    embed_photo_data_url(root, jpeg_bytes)

    # Output paths
    if args.out_base:
        base = Path(args.out_base)
    else:
        base = Path("mt/graphics") / str(season) / f"top10_{weight_class}"

    svg_out = base.with_suffix(".svg")
    jpg_out = base.with_suffix(".jpg")

    save_svg(root, svg_out)
    print(f"SVG graphic written to {svg_out}")

    # Attempt JPG render (if cairosvg is available)
    render_jpg(svg_out, jpg_out)


if __name__ == "__main__":
    main()



