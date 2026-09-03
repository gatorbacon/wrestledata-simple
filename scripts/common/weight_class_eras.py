#!/usr/bin/env python3
"""
Shared, era-aware weight class lookup.

Generalizes the single 2019-cutoff table that used to live inline in
scripts/scraping/scrape_khsaa_regionals.py (KY_WEIGHT_CLASSES_BY_ERA) into
a multi-era table read from data/weight_class_eras/hs_ky_{gender}.json, so
historical (pre-2013) eras can be added without touching Python code.
"""

import json
from functools import lru_cache
from pathlib import Path

ERAS_DIR = Path("data/weight_class_eras")


@lru_cache(maxsize=None)
def _load_eras(gender: str) -> list[dict]:
    path = ERAS_DIR / f"hs_ky_{gender}.json"
    if not path.exists():
        raise FileNotFoundError(f"no weight-class era table for gender={gender!r} at {path}")
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return data["eras"]


def get_weight_classes_for_season(gender: str, season: int) -> list[int]:
    """Return the ordered weight class list in effect for `season` (e.g. 2019 -> [...]))."""
    for era in _load_eras(gender):
        first, last = era["first_season"], era["last_season"]
        if season >= first and (last is None or season <= last):
            return list(era["weight_classes"])
    raise ValueError(f"no weight-class era covers gender={gender!r} season={season}")


def get_era_for_season(gender: str, season: int) -> dict:
    """Return the full era row (era_id, first_season, last_season, weight_classes, ...)."""
    for era in _load_eras(gender):
        first, last = era["first_season"], era["last_season"]
        if season >= first and (last is None or season <= last):
            return era
    raise ValueError(f"no weight-class era covers gender={gender!r} season={season}")
