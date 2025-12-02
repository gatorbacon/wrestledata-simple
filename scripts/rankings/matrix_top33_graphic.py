#!/usr/bin/env python3
"""
Generate a square JPG graphic of the ranking matrix (top 33 only).

The graphic is intended to visually match the interactive HTML matrix,
but as a static image suitable for sharing. It:
  - Uses the existing relationships_{weight}.json and rankings_{weight}.json
    files from mt/rankings_data/{season}.
  - Renders the top 33 wrestlers in both rows and columns.
  - Shows names and team names on a single line (no up/down arrows or "Go" box).
  - Uses similar coloring for direct wins/losses and common opponents.
  - Outputs a square JPG (default 2000x2000).

Usage example:

  .venv/bin/python scripts/rankings/matrix_top33_graphic.py \\
      -season 2026 \\
      -weight-class 157 \\
      -output mt/graphics/2026/matrix_157_top33.jpg
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from generate_matrix import build_matrix_data


def abbreviate_name(full_name: str) -> str:
    """
    Short version of the name for column headers:
    First initial + last name (e.g., 'Levi Haines' -> 'L. Haines').
    """
    if not full_name:
        return ""
    parts = full_name.split()
    if len(parts) == 1:
        return parts[0]
    first_initial = parts[0][0]
    last = parts[-1]
    return f"{first_initial}. {last}"


def try_load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """
    Try to load a reasonably nice TrueType font; fall back to default.
    """
    preferred_fonts = [
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "Arial Bold.ttf" if bold else "Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
        if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for path in preferred_fonts:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _load_rankings_from_file(path: Path) -> List[Dict]:
    """Load a rankings_*.json file and return list sorted by numeric rank."""
    if not path.exists():
        raise FileNotFoundError(f"Rankings file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
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
            # Skip UNR / non-numeric
            continue
        cleaned.append(
            {
                "rank": rank_int,
                "wrestler_id": wid,
                "name": e.get("name", "Unknown"),
                "team": e.get("team", "Unknown"),
                # Preserve official starter flag if present; default to True.
                "is_starter": bool(e.get("is_starter", True)),
            }
        )

    cleaned.sort(key=lambda x: x["rank"])
    return cleaned


def load_current_rankings(
    season: int, weight_class: str, data_dir: str
) -> List[Dict]:
    base = Path(data_dir) / str(season)
    path = base / f"rankings_{weight_class}.json"
    return _load_rankings_from_file(path)


def _parse_archive_timestamp(name: str) -> Optional[datetime]:
    """Parse rankings_archive directory names (YYYYMMDD-HHMMSS) into datetimes."""
    try:
        return datetime.strptime(name, "%Y%m%d-%H%M%S")
    except ValueError:
        return None


def load_historical_rankings(
    season: int,
    weight_class: str,
    data_dir: str,
    days_ago: int,
) -> List[Dict]:
    """
    Load rankings from the archive as of N days ago.

    Use the snapshot whose timestamp is the latest one at or before
    11:59pm on the target day. If none exist, returns an empty list.
    """
    archive_root = Path(data_dir) / str(season) / "rankings_archive"
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

    path = best_dir / f"rankings_{weight_class}.json"
    if not path.exists():
        return []

    return _load_rankings_from_file(path)


def starters_from_rankings(rankings: List[Dict]) -> List[Dict]:
    """
    Filter a rankings list down to official starters only, based on the
    is_starter flag from the rankings JSON.
    """
    return [e for e in rankings if e.get("is_starter", True)]


def build_delta_map_by_position(
    current_rankings: List[Dict], historical_rankings: List[Dict]
) -> Dict[str, object]:
    """
    Compute change in position for each wrestler_id present in both lists.

    Positions are 1-based indices within the provided lists (after any
    starter/all filtering). Positive deltas mean movement UP
    (e.g., from position 8 to 3 yields +5).
    """
    if not historical_rankings:
        return {}

    prev_pos_by_id: Dict[str, int] = {
        e["wrestler_id"]: idx + 1 for idx, e in enumerate(historical_rankings)
    }

    deltas: Dict[str, object] = {}
    for idx, e in enumerate(current_rankings):
        wid = e["wrestler_id"]
        prev_pos = prev_pos_by_id.get(wid)
        curr_pos = idx + 1
        if prev_pos is None:
            # New to the rankings at this weight: mark as "N".
            deltas[wid] = "N"
            continue
        delta = prev_pos - curr_pos
        if delta != 0:
            deltas[wid] = delta

    return deltas


def load_relationships_and_rankings(
    season: int,
    weight_class: str,
    data_dir: str = "mt/rankings_data",
) -> Dict:
    """
    Load relationships_{weight}.json and attach ranking_order from
    rankings_{weight}.json if present, mirroring generate_matrix.py.
    """
    base_dir = Path(data_dir) / str(season)
    rel_file = base_dir / f"relationships_{weight_class}.json"
    if not rel_file.exists():
        raise FileNotFoundError(f"Relationship file not found: {rel_file}")

    with rel_file.open("r", encoding="utf-8") as f:
        relationships_data = json.load(f)

    rankings_file = base_dir / f"rankings_{weight_class}.json"
    if rankings_file.exists():
        try:
            with rankings_file.open("r", encoding="utf-8") as rf:
                rankings_data = json.load(rf)
            ranking_entries = rankings_data.get("rankings", [])
            ranking_ids = [r["wrestler_id"] for r in ranking_entries if r.get("wrestler_id")]
            relationships_data["ranking_order"] = ranking_ids

            # Also attach official starter map so build_matrix_data can mark
            # is_starter correctly for each wrestler.
            starter_map = {
                r["wrestler_id"]: bool(r.get("is_starter", True))
                for r in ranking_entries
                if r.get("wrestler_id")
            }
            relationships_data["starter_map"] = starter_map
        except Exception as e:
            print(f"Warning: Failed to load rankings file {rankings_file}: {e}")

    return relationships_data


def color_for_cell(cell_type: str, severity: str | None) -> Tuple[int, int, int]:
    """
    Map matrix cell type + severity to an RGB color.
    Based loosely on the HTML/CSS colors used in generate_matrix.py.
    """
    # Defaults
    if cell_type == "same-wrestler":
        return (224, 224, 224)

    # Split-even head-to-head series (e.g., 1-1, 2-2)
    if cell_type == "split_even":
        return (255, 250, 205)  # light yellow, to match HTML matrix

    # Common opponent cells (very light)
    if cell_type in ("common_win", "common_loss"):
        # severity 'co' is the only one used here
        return (242, 255, 242) if cell_type == "common_win" else (255, 242, 242)

    if cell_type in ("direct_win", "direct_loss"):
        if severity == "strong":
            return (51, 204, 51) if cell_type == "direct_win" else (255, 51, 51)
        if severity == "medium":
            return (102, 224, 102) if cell_type == "direct_win" else (255, 102, 102)
        if severity == "light":
            return (179, 255, 179) if cell_type == "direct_win" else (255, 179, 179)
        if severity == "co":
            # INJ-type light like common opp
            return (242, 255, 242) if cell_type == "direct_win" else (255, 242, 242)
        if severity == "nc":
            # Neutral grey for NC / MFF
            return (230, 230, 230)

    # No relationship
    return (255, 255, 255)


def draw_matrix_top33(
    matrix_data: Dict,
    weight_class: str,
    season: int,
    width: int = 2000,
    starters_only: bool = True,
    rank_deltas: Optional[Dict[str, int]] = None,
    recent_days: Optional[int] = None,
) -> Image.Image:
    """
    Render the top-33-by-top-33 sub-matrix as an image.
    The width is fixed; the height is computed from the content so we
    avoid large unused white margins.
    """
    wrestlers: List[Dict] = matrix_data["wrestlers"]
    matrix: Dict[str, Dict] = matrix_data["matrix"]

    if starters_only:
        # Filter to official starters only, based on is_starter flag that
        # build_matrix_data computed using the starter_map from rankings.
        wrestlers = [w for w in wrestlers if w.get("is_starter", True)]
    n = min(33, len(wrestlers))
    wrestlers = wrestlers[:n]

    # Layout constants
    W = width
    left_width = int(0.26 * W)  # slightly narrower than before (~20% less)
    top_height = 220            # fixed title/header height
    bottom_margin = 40

    # Cell size: fit n columns in remaining width
    cell_size = int((W - left_width) / n)
    grid_width = cell_size * n
    grid_height = cell_size * n
    H = top_height + grid_height + bottom_margin

    # Canvas
    img = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Fonts
    title_font = try_load_font(52, bold=True)
    name_font = try_load_font(24, bold=True)
    team_font = try_load_font(18, bold=False)
    rank_font = try_load_font(24, bold=True)
    delta_font = try_load_font(20, bold=True)
    col_font = try_load_font(18, bold=True)

    # Title: just the weight (e.g. "141 lbs.")
    title = f"{weight_class} lbs."
    draw.text((20, 20), title, font=title_font, fill=(0, 0, 0))

    # Row strip background
    for idx in range(n):
        y0 = top_height + idx * cell_size
        y1 = y0 + cell_size
        bg = (248, 248, 248) if idx % 2 == 0 else (240, 240, 240)
        draw.rectangle([0, y0, left_width, y1], fill=bg)

    # Header grid background
    draw.rectangle(
        [left_width, 0, left_width + grid_width, top_height], fill=(248, 248, 248)
    )

    # Draw row labels: rank + name (team)
    for idx, w in enumerate(wrestlers):
        y_center = top_height + idx * cell_size + cell_size / 2

        rank_text = f"{idx + 1:02d}"
        rank_x = 10
        draw.text(
            (rank_x, y_center - 12),
            rank_text,
            font=rank_font,
            fill=(100, 100, 100),
        )

        # Optional rank delta column between rank and name
        delta_text = None
        delta_fill = (0, 0, 0)
        if rank_deltas is not None:
            wid = w.get("id")
            d = rank_deltas.get(wid)
            if isinstance(d, int) and d != 0:
                delta_text = f"+{d}" if d > 0 else str(d)
                delta_fill = (23, 197, 23) if d > 0 else (212, 0, 0)  # #17c517 / #d40000
            elif isinstance(d, str) and d == "N":
                delta_text = "N"
                delta_fill = (23, 197, 23)  # #17c517
        delta_x = 70
        if delta_text is not None:
            draw.text(
                (delta_x, y_center - 12),
                delta_text,
                font=delta_font,
                fill=delta_fill,
            )

        text_x = 120
        name = w["name"]
        team = w.get("team", "")
        # Single-line: Name (Team)
        label = f"{name} ({team})" if team else name
        draw.text(
            (text_x, y_center - 16),
            label,
            font=name_font,
            fill=(0, 0, 0),
        )

    # Draw column headers (short names) above grid
    for j, w in enumerate(wrestlers):
        # Slight right nudge so headers visually sit over their columns
        x_center = left_width + j * cell_size + cell_size / 2 + 6
        short = abbreviate_name(w["name"])
        # Draw rotated text for compactness.
        # Use a tightly sized temporary image so the rotated text height
        # comfortably fits within the header band.
        try:
            bbox = draw.textbbox((0, 0), short, font=col_font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
        except AttributeError:
            tw, th = col_font.getsize(short)

        # Add generous padding so strokes aren't clipped after rotation
        pad = 6
        temp_img = Image.new("RGBA", (tw + 2 * pad, th + 2 * pad), (0, 0, 0, 0))
        temp_draw = ImageDraw.Draw(temp_img)
        temp_draw.text((pad, pad), short, font=col_font, fill=(0, 0, 0))
        rotated = temp_img.rotate(90, expand=1)
        rw, rh = rotated.size

        px = int(x_center - rw / 2)
        # Center the rotated label vertically within the header area so it
        # sits fully above the first matrix row.
        py = int((top_height - rh) / 2)
        if py < 0:
            py = 0

        img.paste(rotated, (px, py), rotated)

    # Draw matrix cells
    today = datetime.now().date()
    for i, w_row in enumerate(wrestlers):
        for j, w_col in enumerate(wrestlers):
            x0 = left_width + j * cell_size
            y0 = top_height + i * cell_size
            x1 = x0 + cell_size
            y1 = y0 + cell_size

            if i == j:
                color = color_for_cell("same-wrestler", None)
                draw.rectangle([x0, y0, x1, y1], fill=color, outline=(220, 220, 220))
                continue

            cell_key = f"{w_row['id']}_{w_col['id']}"
            cell = matrix.get(cell_key, {"type": "none"})
            ctype = cell.get("type", "none")
            severity = cell.get("severity")
            color = color_for_cell(ctype, severity)

            # Base cell rectangle
            draw.rectangle([x0, y0, x1, y1], fill=color, outline=(230, 230, 230))

            # Optional recent-match highlight: if any underlying match is recent
            # within the configured window (recent_days), draw a thicker border.
            # We use a solid black border so it stands out clearly even on
            # strong red/green cells (falls/tech falls).
            if recent_days is not None and cell.get("matches"):
                # Reuse the is_recent_date logic implicitly by checking days delta here.
                recent = False
                for m in cell["matches"]:
                    d_str = m.get("date", "")
                    try:
                        d = datetime.strptime(d_str, "%m/%d/%Y").date()
                    except Exception:
                        continue
                    delta = today - d
                    if timedelta(0) <= delta <= timedelta(days=recent_days):
                        recent = True
                        break
                if recent:
                    border_color = (0, 0, 0)
                    draw.rectangle(
                        [x0 + 1, y0 + 1, x1 - 1, y1 - 1],
                        outline=border_color,
                        width=4,
                    )

            val = cell.get("value", "")
            if val:
                # Draw cell text centered; use textbbox when available for sizing.
                try:
                    bbox = draw.textbbox((0, 0), val, font=team_font)
                    tw = bbox[2] - bbox[0]
                    th = bbox[3] - bbox[1]
                except AttributeError:
                    tw, th = team_font.getsize(val)
                tx = x0 + (cell_size - tw) / 2
                ty = y0 + (cell_size - th) / 2
                draw.text((tx, ty), val, font=team_font, fill=(0, 0, 0))

    # Border around grid
    draw.rectangle(
        [left_width, top_height, left_width + grid_width, top_height + grid_height],
        outline=(180, 180, 180),
        width=2,
    )

    return img


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a square JPG graphic of the ranking matrix (top 33)."
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
        "-data-dir",
        default="mt/rankings_data",
        help="Directory containing relationships_*.json and rankings_*.json",
    )
    parser.add_argument(
        "-output",
        default=None,
        help=(
            "Output JPG path. Defaults to "
            "mt/graphics/{season}/matrix_{weight}_top33.jpg"
        ),
    )
    parser.add_argument(
        "-size",
        type=int,
        default=2000,
        help="Size in pixels for the square image (default: 2000).",
    )
    parser.add_argument(
        "-delta-days",
        type=int,
        required=True,
        help=(
            "Number of days back to compare rankings for the delta column "
            "(compare vs rankings active at 11:59pm N days ago)."
        ),
    )

    args = parser.parse_args()

    season = args.season
    weight_class = str(args.weight_class)
    data_dir = args.data_dir
    delta_days = int(args.delta_days)

    relationships_data = load_relationships_and_rankings(
        season, weight_class, data_dir=data_dir
    )

    # Build matrix data (we don't need placement notes here)
    matrix_data = build_matrix_data(relationships_data)

    # Load current and historical rankings for delta calculations
    current_rankings_all = load_current_rankings(season, weight_class, data_dir)
    historical_rankings_all = load_historical_rankings(
        season, weight_class, data_dir, delta_days
    )

    # Build starters-only lists (one per team, first occurrence)
    current_rankings_starters = starters_from_rankings(current_rankings_all)
    historical_rankings_starters = starters_from_rankings(historical_rankings_all)

    # Restrict to top 33 for the displayed tables
    current_rankings_all_33 = current_rankings_all[:33]
    current_rankings_starters_33 = current_rankings_starters[:33]

    # Delta maps for starters-only and all-wrestlers views
    delta_map_starters = build_delta_map_by_position(
        current_rankings_starters_33, historical_rankings_starters
    )
    delta_map_all = build_delta_map_by_position(
        current_rankings_all_33, historical_rankings_all
    )

    # Determine base output path
    if args.output:
        base_path = Path(args.output)
    else:
        out_dir = Path("mt/graphics") / str(season)
        out_dir.mkdir(parents=True, exist_ok=True)
        base_path = out_dir / f"matrix_{weight_class}_top33.jpg"

    base_path.parent.mkdir(parents=True, exist_ok=True)

    # Starters-only version (current behavior) with delta column
    img_starters = draw_matrix_top33(
        matrix_data,
        weight_class,
        season,
        width=args.size,
        starters_only=True,
        rank_deltas=delta_map_starters,
        recent_days=delta_days,
    )
    img_starters.save(base_path, format="JPEG", quality=95)
    print(f"Matrix Top-33 graphic (starters only) written to {base_path}")

    # All-wrestlers version (no starter filter), saved with '_all' suffix
    suffix = "_all"
    all_name = f"{base_path.stem}{suffix}{base_path.suffix}"
    all_path = base_path.with_name(all_name)
    img_all = draw_matrix_top33(
        matrix_data,
        weight_class,
        season,
        width=args.size,
        starters_only=False,
        rank_deltas=delta_map_all,
        recent_days=delta_days,
    )
    img_all.save(all_path, format="JPEG", quality=95)
    print(f"Matrix Top-33 graphic (all wrestlers) written to {all_path}")


if __name__ == "__main__":
    main()



