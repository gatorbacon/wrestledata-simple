#!/usr/bin/env python3
"""
create_retroactive_team_drop.py

Creates a retroactive team rankings drop from current data files.
This allows the next archive run to calculate deltas properly.

Usage:
    python scripts/rankings/create_retroactive_team_drop.py -season 2026 -gender boys -drop-id 2026-01-21
    python scripts/rankings/create_retroactive_team_drop.py -season 2026 -gender girls -drop-id 2026-01-20
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


def load_team_tournament_data(gender: str, season: int) -> List[Dict]:
    """Load current team tournament rankings from xTP file."""
    xtp_path = Path(f"frontend/hs-ky-ui/public/data/xtp/{gender}/{season}/xtp_teams_{season}.json")
    
    if not xtp_path.exists():
        raise FileNotFoundError(f"Team xTP file not found: {xtp_path}")
    
    with xtp_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    
    teams_list = data.get("teams", [])
    if not teams_list:
        raise ValueError(f"No teams found in xTP data")
    
    # Sort by team_xTP_simple (descending)
    teams_list.sort(key=lambda t: -t.get("team_xTP_simple", 0.0))
    
    # Convert to archive format
    rankings = []
    for rank, team in enumerate(teams_list, start=1):
        rankings.append({
            "rank": rank,
            "team": team.get("team", ""),
            "points": team.get("team_xTP_simple", 0.0),
            "prev_rank": None,
            "delta": None
        })
    
    return rankings


def load_dual_rankings_data(gender: str, season: int) -> List[Dict]:
    """Load current dual rankings from dual_standings.json."""
    dual_path = Path(f"frontend/hs-ky-ui/public/data/dual_standings/{gender}/{season}/dual_standings.json")
    
    if not dual_path.exists():
        raise FileNotFoundError(f"Dual standings file not found: {dual_path}")
    
    with dual_path.open("r", encoding="utf-8") as f:
        standings = json.load(f)
    
    if not standings:
        raise ValueError(f"No dual standings found")
    
    # Convert to archive format
    rankings = []
    for entry in standings:
        rankings.append({
            "rank": entry.get("rank"),
            "team": entry.get("team", ""),
            "wins": entry.get("wins", 0),
            "losses": entry.get("losses", 0),
            "ties": entry.get("ties", 0),
            "point_diff": entry.get("point_diff", 0),
            "win_pct": entry.get("win_pct", 0.0),
            "prev_rank": None,
            "delta": None
        })
    
    return rankings


def create_team_tournament_drop(
    season: int,
    gender: str,
    drop_id: str,
    archive_base: Path
) -> None:
    """Create team tournament rankings drop file."""
    print(f"\nCreating Team Tournament Rankings drop: {drop_id}")
    
    # Load current data
    rankings = load_team_tournament_data(gender, season)
    
    # Create output structure
    output_data = {
        "season": season,
        "gender": gender,
        "ranking_type": "team_tournament",
        "drop_id": drop_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rankings": rankings
    }
    
    # Write to archive
    archive_dir = archive_base / gender / str(season) / "team" / "tournament" / "drops"
    archive_dir.mkdir(parents=True, exist_ok=True)
    
    drop_file = archive_dir / f"{drop_id}.json"
    with drop_file.open("w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"  ✓ Created: {drop_file}")
    print(f"  ✓ Teams: {len(rankings)}")
    
    # Update latest.json
    latest_file = archive_base / gender / str(season) / "team" / "tournament" / "latest.json"
    with latest_file.open("w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    print(f"  ✓ Updated latest.json")


def create_dual_rankings_drop(
    season: int,
    gender: str,
    drop_id: str,
    archive_base: Path
) -> None:
    """Create dual rankings drop file."""
    print(f"\nCreating Dual Rankings drop: {drop_id}")
    
    # Load current data
    rankings = load_dual_rankings_data(gender, season)
    
    # Create output structure
    output_data = {
        "season": season,
        "gender": gender,
        "ranking_type": "dual",
        "drop_id": drop_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rankings": rankings
    }
    
    # Write to archive
    archive_dir = archive_base / gender / str(season) / "team" / "dual" / "drops"
    archive_dir.mkdir(parents=True, exist_ok=True)
    
    drop_file = archive_dir / f"{drop_id}.json"
    with drop_file.open("w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"  ✓ Created: {drop_file}")
    print(f"  ✓ Teams: {len(rankings)}")
    
    # Update latest.json
    latest_file = archive_base / gender / str(season) / "team" / "dual" / "latest.json"
    with latest_file.open("w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    print(f"  ✓ Updated latest.json")


def update_index_json(
    season: int,
    gender: str,
    drop_id: str,
    archive_base: Path
) -> None:
    """Update index.json to include the new drop."""
    index_file = archive_base / gender / str(season) / "index.json"
    
    if index_file.exists():
        with index_file.open("r", encoding="utf-8") as f:
            index_data = json.load(f)
    else:
        index_data = {
            "latest": drop_id,
            "drops": []
        }
    
    # Check if drop already exists
    drop_exists = any(d.get("id") == drop_id for d in index_data.get("drops", []))
    
    if not drop_exists:
        index_data["drops"].append({
            "id": drop_id,
            "published_at": f"{drop_id}T00:00:00Z"
        })
        # Sort drops by published_at (newest first)
        index_data["drops"].sort(key=lambda x: x.get("published_at", ""), reverse=True)
        
        # IMPORTANT: Do NOT change "latest" field - it should point to the most recent
        # individual rankings drop, not team rankings drop. Only add the drop to the list.
        
        with index_file.open("w", encoding="utf-8") as f:
            json.dump(index_data, f, indent=2)
        print(f"  ✓ Updated index.json (added drop, preserved latest individual rankings drop)")
    else:
        print(f"  ⚠ Drop {drop_id} already exists in index.json, skipping update")


def main():
    parser = argparse.ArgumentParser(
        description="Create retroactive team rankings drop from current data"
    )
    parser.add_argument(
        "-season",
        type=int,
        required=True,
        help="Season year (e.g., 2026)"
    )
    parser.add_argument(
        "-gender",
        choices=["boys", "girls"],
        required=True,
        help="Gender"
    )
    parser.add_argument(
        "-drop-id",
        type=str,
        required=True,
        help="Drop identifier (e.g., '2026-01-21')"
    )
    parser.add_argument(
        "--archive-base",
        type=str,
        default="frontend/hs-ky-ui/public/data/rankings",
        help="Base directory for archive structure"
    )
    
    args = parser.parse_args()
    
    archive_base = Path(args.archive_base)
    
    print(f"{'='*60}")
    print(f"Creating Retroactive Team Rankings Drop")
    print(f"{'='*60}")
    print(f"Season: {args.season}")
    print(f"Gender: {args.gender}")
    print(f"Drop ID: {args.drop_id}")
    print(f"{'='*60}")
    
    try:
        # Create team tournament drop
        create_team_tournament_drop(
            season=args.season,
            gender=args.gender,
            drop_id=args.drop_id,
            archive_base=archive_base
        )
        
        # Create dual rankings drop
        create_dual_rankings_drop(
            season=args.season,
            gender=args.gender,
            drop_id=args.drop_id,
            archive_base=archive_base
        )
        
        # Update index.json
        update_index_json(
            season=args.season,
            gender=args.gender,
            drop_id=args.drop_id,
            archive_base=archive_base
        )
        
        print(f"\n{'='*60}")
        print(f"✓ Retroactive drop created successfully!")
        print(f"{'='*60}")
        
    except Exception as e:
        print(f"\n{'='*60}")
        print(f"❌ Error: {e}")
        print(f"{'='*60}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())

