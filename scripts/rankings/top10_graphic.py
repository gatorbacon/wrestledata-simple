#!/usr/bin/env python3
"""
Generate a square 2000x2000px "Top 10" graphic for a given weight class.

Layout:
  - Left side: vertical list of ranks 1–10 with wrestler name + school,
    similar to the Flow-style graphic you shared.
  - Right side: photo associated with the #1 wrestler.

Conventions:
  - Rankings source:
      mt/rankings_data/{season}/rankings_{weight}.json
    (same file you edit via the HTML matrix).
  - Wrestler photos (for #1 only):
      {images_dir}/{season}/{wrestler_id}.jpg
      or
      {images_dir}/{season}/{wrestler_id}.png

    where wrestler_id is the season_wrestler_id used in rankings.

Photo requirements:
  - Must exist for the #1-ranked wrestler.
  - Must be exactly 1000x2000 pixels (1000 wide x 2000 tall).
  - If missing or wrong-sized, the script prints a clear error message
    and exits without generating an image.

Usage example:

  .venv/bin/python scripts/rankings/top10_graphic.py \\
      -season 2026 \\
      -weight-class 125 \\
      -images-dir assets/wrestler_photos \\
      -output mt/graphics/2026/top10_125.png
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont


RANKINGS_DIR = Path("mt/rankings_data")
DEFAULT_OUTPUT_ROOT = Path("mt/graphics")


def load_rankings(season: int, weight_class: str) -> List[Dict]:
    """
    Load rankings_{weight}.json and return list sorted by 'rank'.

    For purposes of the Top-10 graphic we only want one starter per team
    at this weight. If multiple wrestlers from the same team are ranked,
    we keep the best-ranked one and drop the backups before taking the
    top 10.
    """
    rankings_path = RANKINGS_DIR / str(season) / f"rankings_{weight_class}.json"
    if not rankings_path.exists():
        raise FileNotFoundError(f"Rankings file not found: {rankings_path}")

    with rankings_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    entries = data.get("rankings", [])

    # Filter to those that have a numeric rank and are actually ranked
    preliminary: List[Dict] = []
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
        preliminary.append(
            {
                "rank": rank_int,
                "wrestler_id": wid,
                "name": e.get("name", "Unknown"),
                "team": e.get("team", "Unknown"),
            }
        )

    # Sort by rank so the first occurrence per team is the starter.
    preliminary.sort(key=lambda x: x["rank"])

    # Keep only the best-ranked wrestler per team (drop backups).
    cleaned: List[Dict] = []
    seen_teams = set()
    for e in preliminary:
        team = e.get("team")
        if team in seen_teams:
            continue
        seen_teams.add(team)
        cleaned.append(e)

    return cleaned


def resolve_photo_path(
    images_dir: Path, season: int, wrestler_id: str
) -> Optional[Path]:
    """Try to find a photo for a wrestler in common formats."""
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


def load_and_validate_photo(photo_path: Path) -> Image.Image:
    """
    Load the photo and ensure it is exactly 1000x2000.
    Raises ValueError with a clear message if not.
    """
    img = Image.open(photo_path).convert("RGB")
    w, h = img.size
    if (w, h) != (1000, 2000):
        raise ValueError(
            f"Photo at {photo_path} has size {w}x{h}; expected exactly 1000x2000."
        )
    return img


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


def draw_top10_graphic(
    rankings: List[Dict],
    photo_img: Image.Image,
    season: int,
    weight_class: str,
) -> Image.Image:
    """
    Compose the 2000x2000 graphic from rankings + photo.
    """
    # Canvas
    W, H = 2000, 2000
    img = Image.new("RGB", (W, H), (245, 245, 245))
    draw = ImageDraw.Draw(img)

    # Layout constants
    left_width = 1000  # left panel width for list
    right_width = W - left_width  # expected to be 1000

    # Backgrounds
    draw.rectangle([0, 0, left_width, H], fill=(250, 250, 250))
    draw.rectangle([left_width, 0, W, H], fill=(0, 0, 0))

    # Paste photo on right, using its native size (validated 1000x2000)
    img.paste(photo_img, (left_width, 0))

    # Fonts
    rank_font = try_load_font(80, bold=True)
    name_font = try_load_font(56, bold=True)
    team_font = try_load_font(40, bold=False)
    header_font = try_load_font(48, bold=True)
    small_font = try_load_font(32, bold=False)

    # Header text (top left)
    header_y = 40
    header_x = 40
    title = f"{season} Top 10"
    subtitle = f"{weight_class} lbs"
    draw.text((header_x, header_y), title, font=header_font, fill=(60, 60, 60))
    draw.text(
        (header_x, header_y + 56),
        subtitle,
        font=small_font,
        fill=(120, 120, 120),
    )

    # Row layout under header
    top_margin = 160
    num_rows = 10
    row_height = (H - top_margin) // num_rows

    # Colors
    row_bg_light = (240, 240, 240)
    row_bg_dark = (230, 230, 230)
    rank_color = (200, 200, 200)
    name_color = (10, 10, 10)
    team_color = (90, 90, 90)

    # Ensure we have up to 10 ranked entries
    rows = rankings[:num_rows]

    for idx in range(num_rows):
        y0 = top_margin + idx * row_height
        y1 = y0 + row_height

        # Alternating row background
        bg = row_bg_light if idx % 2 == 0 else row_bg_dark
        draw.rectangle([0, y0, left_width, y1], fill=bg)

        if idx >= len(rows):
            continue

        entry = rows[idx]
        rank = entry["rank"]
        name = entry["name"]
        team = entry["team"]

        # Rank column
        rank_x = 40
        rank_y = y0 + row_height / 2 - 40
        draw.text(
            (rank_x, rank_y),
            str(rank),
            font=rank_font,
            fill=rank_color,
        )

        # Name + team
        text_x = 160
        name_y = y0 + row_height / 2 - 36
        team_y = name_y + 52

        draw.text((text_x, name_y), name.upper(), font=name_font, fill=name_color)
        draw.text((text_x, team_y), team, font=team_font, fill=team_color)

    # Optional faint watermark text in bottom-left
    footer = "wrestledata"
    try:
        # Pillow >= 8: preferred, more accurate API
        bbox = draw.textbbox((0, 0), footer, font=small_font)
        fw = bbox[2] - bbox[0]
        fh = bbox[3] - bbox[1]
    except AttributeError:
        # Older Pillow fallback
        fw, fh = small_font.getsize(footer)
    draw.text((40, H - fh - 40), footer, font=small_font, fill=(180, 180, 180))

    return img


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a 2000x2000px Top-10 graphic for a weight class."
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
        "-output",
        default=None,
        help=(
            "Output image path. Defaults to "
            "mt/graphics/{season}/top10_{weight}.png"
        ),
    )

    args = parser.parse_args()

    season = args.season
    weight_class = str(args.weight_class)
    images_dir = Path(args.images_dir)

    rankings = load_rankings(season, weight_class)
    if not rankings:
        raise SystemExit(
            f"No ranked wrestlers found in rankings_{weight_class}.json for season {season}."
        )

    top1 = rankings[0]
    wid = top1["wrestler_id"]

    photo_path = resolve_photo_path(images_dir, season, wid)
    if not photo_path:
        raise SystemExit(
            f"No photo found for #1 wrestler {top1['name']} ({top1['team']}).\n"
            f"Expected a 1000x2000 image at one of:\n"
            f"  {images_dir}/{season}/{wid}.jpg\n"
            f"  {images_dir}/{season}/{wid}.jpeg\n"
            f"  {images_dir}/{season}/{wid}.png"
        )

    try:
        photo_img = load_and_validate_photo(photo_path)
    except ValueError as e:
        raise SystemExit(
            f"Photo for #1 wrestler {top1['name']} ({top1['team']}) has wrong size.\n"
            f"{e}\n"
            f"Please provide a source image that is exactly 1000x2000 pixels."
        )

    composed = draw_top10_graphic(rankings, photo_img, season, weight_class)

    # Determine output path
    if args.output:
        out_path = Path(args.output)
    else:
        out_dir = DEFAULT_OUTPUT_ROOT / str(season)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"top10_{weight_class}.png"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    composed.save(out_path, format="PNG")
    print(f"Top-10 graphic written to {out_path}")


if __name__ == "__main__":
    main()



