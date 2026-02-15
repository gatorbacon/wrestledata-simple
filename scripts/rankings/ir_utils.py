#!/usr/bin/env python3
"""
Injured Reserve (IR) utilities.

Load and resolve IR status for wrestlers. IR status is "active" until
a wrestler wrestles a match on a date after the IR date, at which point
status becomes "cleared" for logging.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Set, Optional

IR_JSON_PATH = Path("mt/ir_injured_reserve.json")


def load_ir_data(ir_path: Optional[Path] = None) -> Dict:
    """Load IR JSON. Returns empty dict if file does not exist."""
    path = ir_path or IR_JSON_PATH
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_ir_data(data: Dict, ir_path: Optional[Path] = None) -> None:
    """Save IR JSON."""
    path = ir_path or IR_JSON_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def resolve_active_ir(
    season: int,
    gender: str,
    wrestlers_by_id: Dict[str, Dict],
    ir_path: Optional[Path] = None,
) -> tuple[Set[str], bool]:
    """
    Resolve which wrestlers are currently active IR for the given season/gender.
    Updates status to "cleared" in the JSON when a wrestler has wrestled after IR date.

    Args:
        season: Season year (e.g., 2026)
        gender: "boys" or "girls"
        wrestlers_by_id: Dict of wrestler_id -> { last_match_date: "YYYY-MM-DD", ... }

    Returns:
        Set of wrestler IDs with active IR. Persists status updates to IR JSON
        when a wrestler is detected as returned (cleared).
    """
    data = load_ir_data(ir_path)
    season_key = str(season)
    gender_key = gender
    dirty = False

    if season_key not in data:
        return set()
    season_data = data[season_key]
    if gender_key not in season_data:
        return set()
    gender_data = season_data[gender_key]

    active_ids = set()
    for wrestler_id, entry in list(gender_data.items()):
        if not isinstance(entry, dict):
            continue
        status = entry.get("status", "active")
        ir_date_str = entry.get("ir_date", "")
        if not ir_date_str:
            continue

        try:
            ir_date = datetime.strptime(ir_date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue

        # Check if wrestler has wrestled after IR date
        wrestler_info = wrestlers_by_id.get(str(wrestler_id), {})
        last_match_str = wrestler_info.get("last_match_date")
        if last_match_str:
            try:
                last_match = datetime.strptime(last_match_str, "%Y-%m-%d").date()
                if last_match > ir_date:
                    # Wrestler returned - update status for logging
                    if status != "cleared":
                        entry["status"] = "cleared"
                        entry["cleared_date"] = last_match_str
                        dirty = True
                    continue  # Not active IR
            except (ValueError, TypeError):
                pass

        if status == "active":
            active_ids.add(str(wrestler_id))

    if dirty:
        save_ir_data(data, ir_path)

    return active_ids
