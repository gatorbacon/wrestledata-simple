#!/usr/bin/env python3
"""
Unified interactive script for linking a season to careers.

Tracks every season_wrestler_id and ensures it ends up linked to a career
(either existing or newly created).

This script embeds all linking logic - no need to run other scripts first.
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple
from collections import defaultdict
from difflib import SequenceMatcher
import sys
import importlib.util
import re


def normalize_name(name: str) -> str:
    """Normalize a wrestler's name for matching."""
    if not name:
        return ""
    normalized = name.lower().strip()
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized


def normalize_team_name(team: str) -> str:
    """Normalize team name for matching."""
    if not team:
        return ""
    team = re.sub(r'\s*\([^)]+\)', '', team)
    team = re.sub(r'\s+High School$', '', team, flags=re.IGNORECASE)
    team = re.sub(r'[-–—]', ' ', team)
    team = re.sub(r'\s+', ' ', team)
    return team.lower().strip()


def load_name_aliases() -> Dict[str, str]:
    """Load name aliases and create a lookup dictionary."""
    alias_file = Path("mt/name_alias.json")
    if not alias_file.exists():
        return {}
    
    with open(alias_file, 'r') as f:
        alias_data = json.load(f)
    
    lookup = {}
    for alias in alias_data.get('aliases', []):
        canonical = alias.get('canonical_name', '')
        for variant in alias.get('name_variants', []):
            lookup[normalize_name(variant)] = normalize_name(canonical)
    
    return lookup


def apply_name_alias(name: str, aliases: Dict[str, str]) -> str:
    """Apply name alias if available, otherwise return normalized name."""
    name_norm = normalize_name(name)
    return aliases.get(name_norm, name_norm)


def maybe_add_career_name_alias(wrestler_name: str, canonical_name: str) -> None:
    """
    If wrestler_name differs from canonical_name, add wrestler_name as a variant
    in mt/name_alias.json so future seasons can auto-match on either spelling.
    """
    if not wrestler_name or not canonical_name:
        return
    name_norm = normalize_name(wrestler_name)
    canonical_norm = normalize_name(canonical_name)
    if name_norm == canonical_norm:
        return

    alias_file = Path("mt/name_alias.json")
    if alias_file.exists():
        with alias_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"aliases": []}

    aliases = data.setdefault("aliases", [])

    # Find existing entry for this canonical name and add variant if missing
    for entry in aliases:
        if normalize_name(entry.get("canonical_name", "")) == canonical_norm:
            existing_variants = [normalize_name(v) for v in entry.get("name_variants", [])]
            if name_norm not in existing_variants:
                entry.setdefault("name_variants", []).append(wrestler_name)
                with alias_file.open("w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print(f"  📝 Added name alias: '{wrestler_name}' → '{canonical_name}'")
            return

    # No existing entry for this canonical — create one
    aliases.append({
        "canonical_name": canonical_name,
        "name_variants": [wrestler_name],
        "notes": "Auto-added from career link",
    })
    with alias_file.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  📝 Added name alias: '{wrestler_name}' → '{canonical_name}'")


def names_match_with_synonyms(name1: str, name2: str, synonyms: Dict[str, List[str]]) -> bool:
    """Check if two names match, considering synonyms."""
    norm1 = normalize_name(name1)
    norm2 = normalize_name(name2)
    
    # Exact match
    if norm1 == norm2:
        return True
    
    # Check if they're synonyms
    return are_names_synonyms(name1, name2, synonyms)


def check_grade_progression(grade_new: Optional[int], grade_existing: Optional[int], year_diff: int) -> bool:
    """
    Check if grade progression is plausible given the year difference.
    
    Args:
        grade_new: Grade in the new season being linked
        grade_existing: Grade in the existing season from career
        year_diff: Year difference (new_season - existing_season), e.g., 2026 - 2025 = 1, 2026 - 2024 = 2
    
    Returns:
        True if grade progression is plausible
    """
    if grade_new is None or grade_existing is None:
        return True
    # Grade should increase by year_diff (e.g., if linking 2026 to 2025, grade should increase by 1)
    return grade_existing + year_diff == grade_new


def name_similarity(name1: str, name2: str) -> float:
    """Calculate name similarity score (0-1)."""
    return SequenceMatcher(None, normalize_name(name1), normalize_name(name2)).ratio()


def load_name_synonyms() -> Dict[str, List[str]]:
    """Load name synonyms from file."""
    synonym_file = Path("data/career_linking_logs/name_synonyms.json")
    if not synonym_file.exists():
        return {}
    
    with open(synonym_file, 'r') as f:
        return json.load(f)


def save_name_synonyms(synonyms: Dict[str, List[str]]):
    """Save name synonyms to file."""
    log_dir = Path("data/career_linking_logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    synonym_file = log_dir / "name_synonyms.json"
    with open(synonym_file, 'w') as f:
        json.dump(synonyms, f, indent=2, ensure_ascii=False)


def get_seed_synonyms() -> Dict[str, List[str]]:
    """Get seed list of common name variants."""
    return {
        "daniel": ["dan", "danny", "dannie"],
        "nathaniel": ["nathan", "nate", "nathanial"],
        "nathanial": ["nathan", "nate", "nathaniel"],
        "michael": ["mike", "mikey", "mick"],
        "william": ["will", "bill", "billy", "willy"],
        "robert": ["bob", "rob", "bobby", "robbie"],
        "richard": ["rick", "rich", "dick", "ricky"],
        "james": ["jim", "jimmy", "jamie"],
        "joseph": ["joe", "joey"],
        "thomas": ["tom", "tommy"],
        "christopher": ["chris", "chrisopher"],
        "matthew": ["matt", "matty"],
        "andrew": ["andy", "drew"],
        "benjamin": ["ben", "benny"],
        "gabriel": ["gabe", "gabby", "gabrielle"],
        "alexander": ["alex", "alexander"],
        "nicholas": ["nick", "nickolas", "nico"],
        "jonathan": ["jon", "john", "johnny"],
        "samuel": ["sam", "sammy"],
        "david": ["dave", "davey"],
        "joshua": ["josh"],
        "anthony": ["tony", "antony"],
        "stephen": ["steve", "steven"],
        "kenneth": ["ken", "kenny"],
        "timothy": ["tim", "timmy"],
        "patrick": ["pat", "paddy"],
        "edward": ["ed", "eddie", "eddy"],
        "ronald": ["ron", "ronnie"],
        "kenneth": ["ken", "kenny"],
        "charles": ["chuck", "charlie"],
        "lawrence": ["larry", "lawrence"],
        "gregory": ["greg"],
        "raymond": ["ray"],
        "jeffrey": ["jeff"],
        "scott": ["scotty"],
        "brian": ["bryan"],
        "kevin": ["kev"],
        "mark": ["marc"],
        "paul": ["paulie"],
        "steven": ["steve"],
        "kenneth": ["ken", "kenny"],
        "george": ["georgie"],
        "kenneth": ["ken", "kenny"],
        "ricky": ["ricky", "rick", "rickey"],
        "elliot": ["elliot", "elliott", "eli"],
        "zachary": ["zach", "zack", "zachary"],
        "tristan": ["tristen", "tristian", "tristian"],
        "gavin": ["gavin", "gavyn", "gavynn"],
        "jacob": ["jacob", "jakob", "jake"]
    }


def are_names_synonyms(name1: str, name2: str, synonyms: Dict[str, List[str]]) -> bool:
    """Check if two names are synonyms by comparing first names."""
    norm1 = normalize_name(name1)
    norm2 = normalize_name(name2)
    
    if norm1 == norm2:
        return True
    
    # Extract first names (everything before the first space)
    first1 = norm1.split()[0] if norm1.split() else norm1
    first2 = norm2.split()[0] if norm2.split() else norm2
    
    # If first names match exactly, they're synonyms
    if first1 == first2:
        return True
    
    # Check if first1 is a key and first2 is in its variants
    if first1 in synonyms:
        if first2 in synonyms[first1]:
            return True
    
    # Check if first2 is a key and first1 is in its variants
    if first2 in synonyms:
        if first1 in synonyms[first2]:
            return True
    
    # Check if they're both variants of the same canonical name
    for canonical, variants in synonyms.items():
        if first1 in variants and first2 in variants:
            return True
        if first1 == canonical and first2 in variants:
            return True
        if first2 == canonical and first1 in variants:
            return True
    
    return False


def add_name_synonym(name1: str, name2: str, synonyms: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """Add a name synonym pair to the synonyms dictionary."""
    norm1 = normalize_name(name1)
    norm2 = normalize_name(name2)
    
    if norm1 == norm2:
        return synonyms
    
    # Find if either name is already a canonical
    canonical = None
    variant = None
    
    if norm1 in synonyms:
        canonical = norm1
        variant = norm2
    elif norm2 in synonyms:
        canonical = norm2
        variant = norm1
    else:
        # Neither is canonical, use the shorter one or first alphabetically
        canonical = min(norm1, norm2, key=len)
        variant = norm2 if canonical == norm1 else norm1
    
    # Check if variant is already in synonyms
    if canonical in synonyms:
        if variant not in synonyms[canonical]:
            synonyms[canonical].append(variant)
    else:
        synonyms[canonical] = [variant]
    
    return synonyms


def load_season_accomplishments(season: int, gender: str) -> Dict[str, Dict]:
    """Load season accomplishments and create lookup by season_wrestler_id."""
    file_path = Path(f"data/season_accomplishments/{gender}/{season}/season_accomplishments.json")
    
    if not file_path.exists():
        raise FileNotFoundError(f"Season accomplishments file not found: {file_path}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    lookup = {}
    for wrestler in data.get('wrestlers', []):
        wrestler_id = wrestler.get('season_wrestler_id')
        if wrestler_id:
            lookup[wrestler_id] = wrestler
    
    return lookup


def load_season_accomplishments_list(season: int, gender: str) -> List[Dict]:
    """Load season accomplishments as a list."""
    file_path = Path(f"data/season_accomplishments/{gender}/{season}/season_accomplishments.json")
    
    if not file_path.exists():
        raise FileNotFoundError(f"Season accomplishments file not found: {file_path}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    return data.get('wrestlers', [])


def load_careers(careers_dir: Path) -> Dict[str, Dict]:
    """Load all existing career files."""
    careers = {}
    career_files = list(careers_dir.glob("career_*.json"))
    
    for career_file in career_files:
        try:
            with open(career_file, 'r') as f:
                career = json.load(f)
                career_id = career.get('career_id')
                if career_id:
                    careers[career_id] = career
        except Exception:
            continue
    
    return careers


def load_career(career_id: str) -> Optional[Dict]:
    """Load a single career file."""
    career_file = Path("data/careers") / f"{career_id}.json"
    if not career_file.exists():
        return None
    
    with open(career_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_career_seasons(career: Dict) -> Set[int]:
    """Extract set of seasons already linked in a career."""
    seasons = career.get('seasons', {})
    if isinstance(seasons, dict):
        return {int(s) for s in seasons.keys() if str(s).isdigit()}
    return set()


def get_most_recent_season_in_career(career: Dict, new_season: Optional[int] = None) -> Optional[int]:
    """Get the season in a career nearest to new_season (or most recent if not provided)."""
    career_seasons = get_career_seasons(career)
    if not career_seasons:
        return None
    if new_season is not None:
        return min(career_seasons, key=lambda s: abs(s - new_season))
    return max(career_seasons)


def get_career_teams(career: Dict, season_accomplishments: Dict[int, List[Dict]]) -> Set[str]:
    """Get all teams a career has wrestled for."""
    teams = set()
    seasons = career.get('seasons', {})
    
    if isinstance(seasons, dict):
        for season_str, season_wrestler_id in seasons.items():
            try:
                season = int(season_str)
                if season in season_accomplishments:
                    for wrestler in season_accomplishments[season]:
                        if wrestler.get('season_wrestler_id') == season_wrestler_id:
                            team = wrestler.get('team')
                            if team:
                                teams.add(team)
            except (ValueError, TypeError):
                continue
    
    return teams


def calculate_confidence_score_optimized(
    wrestler_new: Dict,
    career: Dict,
    wrestler_existing: Optional[Dict],
    career_teams: Set[str],
    year_diff: int = 1
) -> Tuple[int, List[str]]:
    """
    Calculate confidence score (0-100) for linking wrestler to career.
    
    Args:
        wrestler_new: Wrestler from the new season being linked
        career: Career to potentially link to
        wrestler_existing: Wrestler data from the most recent season in the career
        career_teams: Set of teams the career has wrestled for
        year_diff: Year difference (new_season - existing_season), e.g., 2026 - 2025 = 1
    """
    score = 0
    reasons = []
    
    team_new_norm = normalize_team_name(wrestler_new.get('team', ''))
    if wrestler_existing:
        team_existing_norm = normalize_team_name(wrestler_existing.get('team', ''))
        if team_new_norm == team_existing_norm:
            score += 40
            reasons.append("same_team")
        elif any(normalize_team_name(t) == team_new_norm for t in career_teams):
            score += 20
            reasons.append("team_in_history")
    else:
        if any(normalize_team_name(t) == team_new_norm for t in career_teams):
            score += 20
            reasons.append("team_in_history")
        else:
            reasons.append("no_existing_season_data")
    
    name_new = wrestler_new.get('name', '')
    name_career = career.get('canonical_name', '')
    
    name_new_parts = normalize_name(name_new).split()
    name_career_parts = normalize_name(name_career).split()
    
    if name_new_parts and name_career_parts:
        if name_new_parts[-1] == name_career_parts[-1]:
            score += 25
            reasons.append("exact_last_name")
    
    name_sim = name_similarity(name_new, name_career)
    if name_sim >= 0.95:
        score += 20
        reasons.append("exact_name_match")
    elif name_sim >= 0.85:
        score += 10
        reasons.append("fuzzy_name_match")
    
    # Plausible grade progression: +10
    if wrestler_existing:
        grade_new = wrestler_new.get('grade')
        grade_existing = wrestler_existing.get('grade')
        if check_grade_progression(grade_new, grade_existing, year_diff):
            score += 10
            reasons.append("plausible_grade")
    
    # Weight within ±2 classes: +5
    if wrestler_existing:
        weight_new = wrestler_new.get('final_weight')
        weight_existing = wrestler_existing.get('final_weight')
        if weight_new and weight_existing:
            weight_diff = abs(weight_new - weight_existing)
            if weight_diff <= 2:
                score += 5
                reasons.append("similar_weight")
    
    return (score, reasons)


def find_candidate_careers_optimized(
    wrestler_new: Dict,
    careers: Dict[str, Dict],
    name_to_careers: Dict[str, List[str]],
    season_accomplishments_lookup: Dict[int, Dict[str, Dict]],
    career_teams_cache: Dict[str, Set[str]],
    aliases: Dict[str, str],
    new_season: int,
    synonyms: Dict[str, List[str]] = None
) -> List[Tuple[str, Dict, int, List[str]]]:
    """
    Find candidate careers using pre-built lookups.
    
    Args:
        wrestler_new: Wrestler from the new season being linked
        careers: All existing careers
        name_to_careers: Lookup from normalized name to career IDs
        season_accomplishments_lookup: Dict mapping season -> {wrestler_id -> wrestler_data}
        career_teams_cache: Cache of teams for each career
        aliases: Name aliases
        new_season: The season being linked (e.g., 2026)
        synonyms: Name synonyms
    """
    name_new_norm = apply_name_alias(wrestler_new.get('name', ''), aliases)
    
    candidates = []
    candidate_career_ids = set()
    
    if name_new_norm in name_to_careers:
        candidate_career_ids.update(name_to_careers[name_new_norm])
    
    # Also check synonyms for candidate finding
    if synonyms:
        for canonical, variants in synonyms.items():
            if name_new_norm == canonical or name_new_norm in variants:
                # Check all synonyms as potential matches
                for syn_name in [canonical] + variants:
                    if syn_name in name_to_careers:
                        candidate_career_ids.update(name_to_careers[syn_name])
    
    name_parts = name_new_norm.split()
    if len(name_parts) > 0:
        last_name = name_parts[-1]
        for name_norm, career_ids in name_to_careers.items():
            if name_norm.split()[-1] == last_name if name_norm.split() else False:
                candidate_career_ids.update(career_ids)
    
    if len(candidate_career_ids) > 50:
        candidate_career_ids = set(name_to_careers.get(name_new_norm, []))
    
    for career_id in candidate_career_ids:
        career = careers.get(career_id)
        if not career:
            continue
        
        career_seasons = get_career_seasons(career)
        # Skip if this season is already linked
        if new_season in career_seasons:
            continue
        
        if career_seasons:
            min_season = min(career_seasons)
            max_season = max(career_seasons)
            # Filter to careers within ±3 years of new_season
            if min_season > new_season + 3 or max_season < new_season - 3:
                continue
        
        # Find the nearest season in the career to new_season
        most_recent_season = get_most_recent_season_in_career(career, new_season)
        if not most_recent_season:
            continue

        # Get wrestler data from the nearest season
        seasons = career.get('seasons', {})
        wrestler_existing_id = seasons.get(str(most_recent_season))
        wrestler_existing = None
        if wrestler_existing_id and most_recent_season in season_accomplishments_lookup:
            wrestler_existing = season_accomplishments_lookup[most_recent_season].get(wrestler_existing_id)
        
        # Calculate year difference
        year_diff = new_season - most_recent_season
        
        score, reasons = calculate_confidence_score_optimized(
            wrestler_new,
            career,
            wrestler_existing,
            career_teams_cache.get(career_id, set()),
            year_diff
        )
        
        candidates.append((career_id, career, score, reasons))
    
    candidates.sort(key=lambda x: x[2], reverse=True)
    return candidates


def auto_link_rule_a_optimized(
    wrestler_new: Dict,
    career: Dict,
    wrestler_existing: Optional[Dict],
    career_teams: Set[str],
    aliases: Dict[str, str],
    year_diff: int,
    new_season: int,
    synonyms: Dict[str, List[str]] = None
) -> bool:
    """Rule A: Exact name + exact team + grade progression."""
    if new_season in get_career_seasons(career):
        return False
    
    name_new = wrestler_new.get('name', '')
    name_career = career.get('canonical_name', '')
    
    # Check name match (with aliases and synonyms)
    name_new_norm = apply_name_alias(name_new, aliases)
    name_career_norm = apply_name_alias(name_career, aliases)
    
    if name_new_norm != name_career_norm:
        # If not exact match, check synonyms
        if synonyms and are_names_synonyms(name_new, name_career, synonyms):
            pass  # Names match via synonyms
        else:
            return False
    
    team_new_norm = normalize_team_name(wrestler_new.get('team', ''))
    team_match = False
    
    if wrestler_existing:
        team_existing_norm = normalize_team_name(wrestler_existing.get('team', ''))
        if team_new_norm == team_existing_norm:
            team_match = True
    
    if not team_match:
        if any(normalize_team_name(t) == team_new_norm for t in career_teams):
            team_match = True
    
    if not team_match:
        return False
    
    grade_new = wrestler_new.get('grade')
    if wrestler_existing:
        grade_existing = wrestler_existing.get('grade')
        if not check_grade_progression(grade_new, grade_existing, year_diff):
            return False
    
    return True


def auto_link_rule_b_optimized(
    wrestler_new: Dict,
    career: Dict,
    wrestler_existing: Optional[Dict],
    career_teams: Set[str],
    aliases: Dict[str, str],
    new_season: int,
    synonyms: Dict[str, List[str]] = None
) -> bool:
    """Rule B: Exact name + exact team (grade unreliable)."""
    if new_season in get_career_seasons(career):
        return False
    
    name_new = wrestler_new.get('name', '')
    name_career = career.get('canonical_name', '')
    
    # Check name match (with aliases and synonyms)
    name_new_norm = apply_name_alias(name_new, aliases)
    name_career_norm = apply_name_alias(name_career, aliases)
    
    if name_new_norm != name_career_norm:
        # If not exact match, check synonyms
        if synonyms and are_names_synonyms(name_new, name_career, synonyms):
            pass  # Names match via synonyms
        else:
            return False
    
    team_new_norm = normalize_team_name(wrestler_new.get('team', ''))
    team_match = False
    
    if wrestler_existing:
        team_existing_norm = normalize_team_name(wrestler_existing.get('team', ''))
        if team_new_norm == team_existing_norm:
            team_match = True
    
    if not team_match:
        if any(normalize_team_name(t) == team_new_norm for t in career_teams):
            team_match = True
    
    if not team_match:
        return False
    
    career_seasons = get_career_seasons(career)
    if career_seasons:
        min_season = min(career_seasons)
        max_season = max(career_seasons)
        # Filter to careers within ±3 years of new_season
        if min_season > new_season + 3 or max_season < new_season - 3:
            return False
    
    return True


def get_wrestler_from_link(link: Dict) -> Optional[Dict]:
    """Get wrestler data from a link, handling both old format ('wrestler_2024') and new format ('wrestler_new')."""
    return link.get('wrestler_new') or link.get('wrestler_2024')


def check_if_already_linked(wrestler_id: str, career_id: str, season: int = None) -> bool:
    """
    Check if a wrestler is already linked to a career.
    
    Args:
        wrestler_id: Season wrestler ID to check
        career_id: Career ID to check
        season: Optional season to check (if None, checks all seasons)
    """
    career = load_career(career_id)
    if not career:
        return False
    
    seasons = career.get('seasons', {})
    if season is not None:
        return seasons.get(str(season)) == wrestler_id
    else:
        # Check all seasons
        return wrestler_id in seasons.values()


def get_all_linked_wrestler_ids(season: int = None) -> Set[str]:
    """
    Get set of all season_wrestler_ids that are already linked.
    
    Args:
        season: Optional season to filter by (if None, returns all linked wrestler IDs from all seasons)
    """
    linked = set()
    careers_dir = Path("data/careers")
    
    for career_file in careers_dir.glob("career_*.json"):
        try:
            with open(career_file, 'r') as f:
                career = json.load(f)
                seasons = career.get('seasons', {})
                if season is not None:
                    wrestler_id = seasons.get(str(season))
                    if wrestler_id:
                        linked.add(wrestler_id)
                else:
                    # Add all wrestler IDs from all seasons
                    for wrestler_id in seasons.values():
                        if wrestler_id:
                            linked.add(wrestler_id)
        except Exception:
            continue
    
    return linked


def print_comparison(wrestler_new: Dict, career: Dict, wrestler_existing: Optional[Dict], index: int, total: int, new_season: int = None, existing_season: int = None):
    """Print compact side-by-side comparison."""
    print("\n" + "="*80)
    print(f"COMPARISON {index}/{total}")
    print("="*80)
    
    name_new = wrestler_new.get('name', 'Unknown')
    team_new = wrestler_new.get('team', 'Unknown')
    weight_new = wrestler_new.get('final_weight', '?')
    grade_new = wrestler_new.get('grade', '?')
    record_new = wrestler_new.get('record', {})
    wins_new = record_new.get('wins', 0) if record_new else 0
    losses_new = record_new.get('losses', 0) if record_new else 0
    
    name_career = career.get('canonical_name', 'Unknown')
    team_existing = 'Unknown'
    weight_existing = '?'
    grade_existing = '?'
    wins_existing = 0
    losses_existing = 0
    
    if wrestler_existing:
        team_existing = wrestler_existing.get('team', 'Unknown')
        weight_existing = wrestler_existing.get('final_weight', '?')
        grade_existing = wrestler_existing.get('grade', '?')
        record_existing = wrestler_existing.get('record', {})
        wins_existing = record_existing.get('wins', 0) if record_existing else 0
        losses_existing = record_existing.get('losses', 0) if record_existing else 0
    
    existing_season_label = f" ({existing_season})" if existing_season else ""
    new_season_label = f" ({new_season})" if new_season else ""
    
    print(f"\nCareer{existing_season_label}: {name_career} / {team_existing} / Grade {grade_existing} / {weight_existing} lbs / {wins_existing}-{losses_existing}")
    print(f"New{new_season_label}:          {name_new} / {team_new} / Grade {grade_new} / {weight_new} lbs / {wins_new}-{losses_new}")
    
    name_match = name_new.lower().strip() == name_career.lower().strip()
    team_match = team_new.lower().strip() == team_existing.lower().strip()
    grade_progression = False
    if grade_new is not None and grade_existing is not None and grade_new != '?' and grade_existing != '?':
        try:
            year_diff = new_season - existing_season if (new_season and existing_season) else 1
            grade_progression = check_grade_progression(grade_new, grade_existing, year_diff)
        except (ValueError, TypeError):
            grade_progression = False
    
    print(f"\nMatch: Name={'✅' if name_match else '❌'}  Team={'✅' if team_match else '❌'}  Grade={'✅' if grade_progression else '❌'}")
    print(f"Career ID: {career.get('career_id', 'Unknown')}")
    print("="*80)


def review_category(
    category_name: str,
    links: List[Dict],
    wrestler_lookup_new: Dict[str, Dict],
    season_accomplishments_lookup: Dict[int, Dict[str, Dict]],
    already_linked: Set[str],
    new_season: int,
    anchor_season: int,
    synonyms: Dict[str, List[str]] = None,
    rejected_links: List[Dict] = None
) -> tuple[List[Dict], List[Dict], Dict[str, List[str]], List[Dict]]:
    """Review a category of links interactively."""
    # Build set of rejected wrestler IDs for this category
    rejected_wrestler_ids = set()
    if rejected_links:
        for rejected_link in rejected_links:
            wrestler_id = rejected_link.get('wrestler_2024', {}).get('season_wrestler_id')
            if wrestler_id:
                rejected_wrestler_ids.add(wrestler_id)
    
    # Filter out already-linked wrestlers, already-applied links, AND rejected links
    links_to_review = []
    for link in links:
        # Handle both old format ('wrestler_2024') and new format ('wrestler_new')
        wrestler_data = link.get('wrestler_new') or link.get('wrestler_2024')
        if not wrestler_data:
            continue
        wrestler_id = wrestler_data.get('season_wrestler_id')
        career_id = link.get('career_id')
        # Skip if already linked, already applied, or previously rejected
        if (wrestler_id and wrestler_id not in already_linked and 
            wrestler_id not in rejected_wrestler_ids and
            (not career_id or not check_if_already_linked(wrestler_id, career_id, new_season))):
            links_to_review.append(link)
    
    if synonyms is None:
        synonyms = load_name_synonyms()
        # Merge with seed synonyms
        seed_synonyms = get_seed_synonyms()
        for canonical, variants in seed_synonyms.items():
            if canonical not in synonyms:
                synonyms[canonical] = []
            for variant in variants:
                if variant not in synonyms[canonical]:
                    synonyms[canonical].append(variant)
    
    if not links_to_review:
        print(f"\n✅ All links in {category_name} are already applied!")
        return [], [], synonyms, []
    
    print(f"\n{'='*80}")
    print(f"REVIEWING: {category_name}")
    print(f"{'='*80}")
    print(f"Total links: {len(links)}")
    print(f"Already linked: {len(links) - len(links_to_review)}")
    print(f"Needs review: {len(links_to_review)}")
    
    approved = []
    rejected = []
    moved_to_category_5 = []  # Wrestlers rejected with no alternatives
    
    for i, link in enumerate(links_to_review, 1):
        # Handle both old format ('wrestler_2024') and new format ('wrestler_new')
        wrestler_new_id = link.get('wrestler_new', {}).get('season_wrestler_id') or link.get('wrestler_2024', {}).get('season_wrestler_id')
        career_id = link['career_id']
        
        wrestler_new = wrestler_lookup_new.get(wrestler_new_id)
        if not wrestler_new:
            rejected.append(link)
            continue
        
        career = load_career(career_id)
        if not career:
            rejected.append(link)
            continue
        
        # Find the nearest season in the career to new_season
        most_recent_season = get_most_recent_season_in_career(career, new_season)
        wrestler_existing = None
        if most_recent_season:
            wrestler_existing_id = career.get('seasons', {}).get(str(most_recent_season))
            if wrestler_existing_id and most_recent_season in season_accomplishments_lookup:
                wrestler_existing = season_accomplishments_lookup[most_recent_season].get(wrestler_existing_id)
        
        # For Category 3, skip the comparison and go straight to the match table
        if category_name == 'Category 3: High Confidence (≥80)':
            # Skip comparison display, go straight to table
            name_new = wrestler_new.get('name', '')
            team_new = wrestler_new.get('team', '')
            grade_new = wrestler_new.get('grade')
            weight_new = wrestler_new.get('final_weight')
            
            # Extract last name
            name_parts_new = name_new.split()
            last_name_new = name_parts_new[-1] if name_parts_new else ''
            first_name_new = name_parts_new[0] if len(name_parts_new) > 1 else ''
            
            # Find all careers with matching last name (including the proposed one)
            careers_dir = Path("data/careers")
            matching_careers = []
            proposed_career_id = link.get('career_id')
            
            # First, add the proposed career at the top
            proposed_career_name = career.get('canonical_name', '')
            proposed_career_name_parts = proposed_career_name.split()
            proposed_first_name = proposed_career_name_parts[0] if len(proposed_career_name_parts) > 1 else ''
            
            # Calculate match scores for proposed career
            proposed_team_match = normalize_team_name(team_new) == normalize_team_name(wrestler_existing.get('team', '')) if wrestler_existing else False
            proposed_first_name_sim = name_similarity(first_name_new, proposed_first_name) if first_name_new and proposed_first_name else 0.0
            proposed_first_name_fuzzy = proposed_first_name_sim >= 0.7
            year_diff = new_season - most_recent_season if most_recent_season else 1
            proposed_grade_match = (grade_new is not None and wrestler_existing and 
                                    wrestler_existing.get('grade') is not None and 
                                    check_grade_progression(grade_new, wrestler_existing.get('grade'), year_diff))
            proposed_weight_match = (weight_new is not None and wrestler_existing and 
                                    wrestler_existing.get('final_weight') is not None and 
                                    abs(weight_new - wrestler_existing.get('final_weight')) <= 2)
            
            # Calculate priority score for proposed career
            proposed_priority = 0
            if proposed_team_match and proposed_first_name_fuzzy:
                proposed_priority = 1000 + proposed_first_name_sim * 100
            elif proposed_team_match:
                proposed_priority = 500 + proposed_first_name_sim * 50
            elif proposed_first_name_fuzzy:
                proposed_priority = 300 + proposed_first_name_sim * 30
            else:
                proposed_priority = proposed_first_name_sim * 10
            
            if proposed_grade_match:
                proposed_priority += 20
            if proposed_weight_match:
                proposed_priority += 10
            
            matching_careers.append({
                'career_id': proposed_career_id,
                'career_name': proposed_career_name,
                'team': wrestler_existing.get('team', '') if wrestler_existing else '',
                'grade': wrestler_existing.get('grade') if wrestler_existing else None,
                'weight': wrestler_existing.get('final_weight') if wrestler_existing else None,
                'team_match': proposed_team_match,
                'first_name_fuzzy': proposed_first_name_fuzzy,
                'first_name_sim': proposed_first_name_sim,
                'grade_match': proposed_grade_match,
                'weight_match': proposed_weight_match,
                'priority_score': proposed_priority,
                'last_name_fuzzy': False,
                'is_proposed': True
            })
            
            # Now find all other careers with matching last name
            for career_file in careers_dir.glob("career_*.json"):
                with open(career_file, 'r') as f:
                    other_career = json.load(f)
                
                other_career_id = other_career.get('career_id')
                if other_career_id == proposed_career_id:
                    continue
                
                # Skip if already has new_season linked
                if str(new_season) in other_career.get('seasons', {}):
                    continue
                
                other_career_name = other_career.get('canonical_name', '')
                other_career_name_parts = other_career_name.split()
                other_career_last_name = other_career_name_parts[-1] if other_career_name_parts else ''
                
                # Check last name match (exact or fuzzy)
                last_name_match = False
                last_name_fuzzy = False
                if last_name_new.lower() == other_career_last_name.lower():
                    last_name_match = True
                elif last_name_new and other_career_last_name:
                    # Fuzzy match for last name (similarity > 0.8)
                    last_name_sim = name_similarity(last_name_new, other_career_last_name)
                    if last_name_sim >= 0.8:
                        last_name_fuzzy = True
                
                if not last_name_match and not last_name_fuzzy:
                    continue
                
                # Get nearest season wrestler data
                other_most_recent_season = get_most_recent_season_in_career(other_career, new_season)
                other_wrestler_existing = None
                if other_most_recent_season:
                    other_wrestler_existing_id = other_career.get('seasons', {}).get(str(other_most_recent_season))
                    if other_wrestler_existing_id and other_most_recent_season in season_accomplishments_lookup:
                        other_wrestler_existing = season_accomplishments_lookup[other_most_recent_season].get(other_wrestler_existing_id)
                
                other_career_first_name = other_career_name_parts[0] if len(other_career_name_parts) > 1 else ''
                other_team_existing = other_wrestler_existing.get('team', '') if other_wrestler_existing else ''
                other_grade_existing = other_wrestler_existing.get('grade') if other_wrestler_existing else None
                other_weight_existing = other_wrestler_existing.get('final_weight') if other_wrestler_existing else None
                
                # Calculate match scores
                other_team_match = normalize_team_name(team_new) == normalize_team_name(other_team_existing) if other_team_existing else False
                other_first_name_sim = name_similarity(first_name_new, other_career_first_name) if first_name_new and other_career_first_name else 0.0
                other_first_name_fuzzy = other_first_name_sim >= 0.7
                other_year_diff = new_season - other_most_recent_season if other_most_recent_season else 1
                other_grade_match = (grade_new is not None and other_grade_existing is not None and 
                                    check_grade_progression(grade_new, other_grade_existing, other_year_diff))
                other_weight_match = (weight_new is not None and other_weight_existing is not None and
                                    abs(weight_new - other_weight_existing) <= 2)
                
                # Calculate priority score
                other_priority_score = 0
                if other_team_match and other_first_name_fuzzy:
                    other_priority_score = 1000 + other_first_name_sim * 100
                elif other_team_match:
                    other_priority_score = 500 + other_first_name_sim * 50
                elif other_first_name_fuzzy:
                    other_priority_score = 300 + other_first_name_sim * 30
                else:
                    other_priority_score = other_first_name_sim * 10
                
                if other_grade_match:
                    other_priority_score += 20
                if other_weight_match:
                    other_priority_score += 10
                
                # Penalize fuzzy last name matches
                if last_name_fuzzy and not last_name_match:
                    other_priority_score -= 100
                
                matching_careers.append({
                    'career_id': other_career_id,
                    'career_name': other_career_name,
                    'team': other_team_existing,
                    'grade': other_grade_existing,
                    'weight': other_weight_existing,
                    'team_match': other_team_match,
                    'first_name_fuzzy': other_first_name_fuzzy,
                    'first_name_sim': other_first_name_sim,
                    'grade_match': other_grade_match,
                    'weight_match': other_weight_match,
                    'priority_score': other_priority_score,
                    'last_name_fuzzy': last_name_fuzzy,
                    'is_proposed': False
                })
            
            # Deduplicate careers by career_id (keep the one with highest priority score)
            seen_career_ids = {}
            deduplicated_careers = []
            for match in matching_careers:
                career_id = match['career_id']
                if career_id not in seen_career_ids:
                    seen_career_ids[career_id] = match
                    deduplicated_careers.append(match)
                else:
                    # If we've seen this career before, keep the one with higher priority score
                    existing_match = seen_career_ids[career_id]
                    if match['priority_score'] > existing_match['priority_score']:
                        # Replace the existing one
                        deduplicated_careers.remove(existing_match)
                        deduplicated_careers.append(match)
                        seen_career_ids[career_id] = match
            
            # Sort by priority score (descending) - proposed will be at top if it's the best match
            deduplicated_careers.sort(key=lambda x: x['priority_score'], reverse=True)
            
            # Display all matches in compact format
            print(f"\n{'='*120}")
            print(f"ALL MATCHES FOR: {name_new} ({team_new}, Grade {grade_new}, {weight_new} lbs)")
            print(f"{'='*120}")
            print(f"{'#':<4} {'Career ID':<12} {'Name':<25} {'Team':<25} {'Grade':<8} {'Weight':<10} {'Team':<6} {'Name':<6} {'Grade':<6} {'Weight':<6} {'Score':<8}")
            print(f"{'-'*120}")
            
            for idx, match in enumerate(deduplicated_careers, 1):
                # Color codes: ✅ = exact match, 🟡 = close match, ❌ = no match
                team_symbol = "✅" if match['team_match'] else "❌"
                name_symbol = "✅" if match['first_name_sim'] >= 0.9 else ("🟡" if match['first_name_fuzzy'] else "❌")
                grade_symbol = "✅" if match['grade_match'] else ("🟡" if (grade_new and match['grade'] and abs(grade_new - match['grade']) <= 2) else "❌")
                weight_symbol = "✅" if match['weight_match'] else ("🟡" if (weight_new and match['weight'] and abs(weight_new - match['weight']) <= 5) else "❌")
                
                grade_str = str(match['grade']) if match['grade'] is not None else '?'
                weight_str = f"{match['weight']} lbs" if match['weight'] is not None else '?'
                score_str = str(int(match['priority_score']))
                career_id_short = match['career_id'].replace('career_', '') if 'career_' in match['career_id'] else match['career_id']
                
                # Mark proposed match
                proposed_marker = " ⭐" if match['is_proposed'] else ""
                
                print(f"{idx:<4} {career_id_short:<12} {match['career_name']:<25}{proposed_marker:<2} {match['team']:<25} {grade_str:<8} {weight_str:<10} "
                      f"{team_symbol:<6} {name_symbol:<6} {grade_symbol:<6} {weight_symbol:<6} {score_str:<8}")
            
            print(f"{'='*120}")
            print(f"\nOptions:")
            if deduplicated_careers:
                print(f"  [1-{len(deduplicated_careers)}] - Link to match shown above")
            print(f"  [n]ew career - Create new career")
            print(f"  [s]kip - Skip for now (will move to Category 5)")
            
            while True:
                response = input("\n> ").strip().lower()
                
                if response.isdigit():
                    alt_idx = int(response) - 1
                    if 0 <= alt_idx < len(deduplicated_careers):
                        # Link to selected match
                        selected_match = deduplicated_careers[alt_idx]
                        alt_career_id = selected_match['career_id']
                        wrestler_data = get_wrestler_from_link(link)
                        alt_link = {
                            'wrestler_new': wrestler_data,
                            'career_id': alt_career_id,
                            'confidence': int(selected_match['priority_score']),
                            'reasons': ['last_name_match', 'rejected_alternative']
                        }
                        approved.append(alt_link)
                        # Auto-apply immediately
                        wrestler_new_id = wrestler_data.get('season_wrestler_id')
                        if wrestler_new_id and not check_if_already_linked(wrestler_new_id, alt_career_id, new_season):
                            alt_career_file = Path("data/careers") / f"{alt_career_id}.json"
                            with open(alt_career_file, 'r') as f:
                                alt_career_data = json.load(f)
                            alt_seasons = alt_career_data.get('seasons', {})
                            if str(new_season) not in alt_seasons:
                                alt_seasons[str(new_season)] = wrestler_new_id
                                alt_career_data['seasons'] = alt_seasons
                                with open(alt_career_file, 'w', encoding='utf-8') as f:
                                    json.dump(alt_career_data, f, indent=2, ensure_ascii=False)
                                maybe_add_career_name_alias(
                                    wrestler_data.get('name', ''),
                                    alt_career_data.get('canonical_name', ''),
                                )
                                print(f"✅ Linked to {selected_match['career_name']} and applied")
                        else:
                            print("✅ Linked to alternative career (already linked)")
                        rejected.append(link)  # Mark original as rejected
                        break
                    else:
                        print(f"Invalid number. Please enter 1-{len(matching_careers)}")
                elif response in ['n', 'new', 'new career']:
                    # Create new career immediately
                    new_career_id = create_single_career(wrestler_new, anchor_season, new_season)
                    
                    print(f"✅ Created new career {new_career_id} and linked wrestler")
                    wrestler_data = get_wrestler_from_link(link)
                    approved.append({
                        'wrestler_new': wrestler_data,
                        'career_id': new_career_id,
                        'action': 'new_career_created'
                    })
                    rejected.append(link)  # Mark original as rejected
                    break
                elif response in ['s', 'skip']:
                    # Skip - move to Category 5
                    wrestler_data = get_wrestler_from_link(link)
                    moved_to_category_5.append({
                        'wrestler_new': wrestler_data,
                        'reason': 'rejected_from_category_3_skipped',
                        'rejected_career_id': proposed_career_id
                    })
                    rejected.append(link)
                    print("⏭️  Skipped - will review in Category 5")
                    break
                else:
                    print(f"Invalid option. Please enter 1-{len(matching_careers)}, 'n', or 's'")
                    continue
            
            print(f"\nProgress: {i}/{len(links_to_review)} | Approved: {len(approved)} | Rejected: {len(rejected)}")
            continue  # Skip normal review flow for Category 3
        
        # Normal review flow for other categories
        print_comparison(wrestler_new, career, wrestler_existing, i, len(links_to_review), new_season, most_recent_season)
        
        # Check if names are similar but not exact
        name_new_normal = wrestler_new.get('name', '')
        name_career_normal = career.get('canonical_name', '')
        show_synonym_option = False
        if name_new_normal and name_career_normal:
            name_sim = name_similarity(name_new_normal, name_career_normal)
            if 0.7 <= name_sim < 0.95:  # Similar but not exact
                show_synonym_option = True
        
        while True:
            print("\nOptions:")
            print("  [a]pprove - Link this wrestler to this career")
            print("  [r]eject  - Reject this link (will find alternative or create new)")
            if show_synonym_option:
                print("  [y]ynonym - Mark these names as synonyms (e.g., Nathan/Nathaniel)")
            print("  [s]kip    - Skip for now")
            print("  [b] approve all remaining - Approve all remaining in this category")
            print("  [q]uit    - Save and return to main menu")
            
            response = input("\n> ").strip()
            response_lower = response.lower()
            
            if response_lower in ['b', 'approve all', 'approveall', 'all']:
                remaining = links_to_review[i-1:]
                approved.extend(remaining)
                # Auto-apply all remaining links immediately
                for remaining_link in remaining:
                    career_id = remaining_link.get('career_id')
                    wrestler_data = get_wrestler_from_link(remaining_link)
                    wrestler_new_id = wrestler_data.get('season_wrestler_id') if wrestler_data else None
                    if wrestler_new_id and career_id and not check_if_already_linked(wrestler_new_id, career_id, new_season):
                        career = load_career(career_id)
                        if career:
                            seasons = career.get('seasons', {})
                            if str(new_season) not in seasons:
                                seasons[str(new_season)] = wrestler_new_id
                                career['seasons'] = seasons
                                career_file = Path("data/careers") / f"{career_id}.json"
                                with open(career_file, 'w', encoding='utf-8') as f:
                                    json.dump(career, f, indent=2, ensure_ascii=False)
                                maybe_add_career_name_alias(
                                    wrestler_data.get('name', '') if wrestler_data else '',
                                    career.get('canonical_name', ''),
                                )
                print(f"✅ Approved and applied all {len(remaining)} remaining links")
                break
            elif response_lower in ['a', 'approve']:
                approved.append(link)
                # Auto-apply immediately
                career_id = link['career_id']
                wrestler_data = get_wrestler_from_link(link)
                wrestler_new_id = wrestler_data.get('season_wrestler_id')
                if wrestler_new_id and not check_if_already_linked(wrestler_new_id, career_id, new_season):
                    career = load_career(career_id)
                    if career:
                        seasons = career.get('seasons', {})
                        if str(new_season) not in seasons:
                            seasons[str(new_season)] = wrestler_new_id
                            career['seasons'] = seasons
                            career_file = Path("data/careers") / f"{career_id}.json"
                            with open(career_file, 'w', encoding='utf-8') as f:
                                json.dump(career, f, indent=2, ensure_ascii=False)
                            maybe_add_career_name_alias(
                                wrestler_data.get('name', '') if wrestler_data else '',
                                career.get('canonical_name', ''),
                            )
                            print("✅ Approved and applied")
                        else:
                            print("✅ Approved (already linked)")
                    else:
                        print("✅ Approved")
                else:
                    print("✅ Approved (already linked)")
                break
            elif response_lower in ['r', 'reject']:
                rejected.append(link)
                print("❌ Rejected")
                break
            elif response_lower in ['y', 'synonym']:
                if show_synonym_option:
                    synonyms = add_name_synonym(name_2024, name_2025, synonyms)
                    save_name_synonyms(synonyms)
                    print(f"✅ Added synonym: '{name_2024}' ↔ '{name_2025}'")
                    print("   (This will help with future matching)")
                    # After adding synonym, approve the link
                    approved.append(link)
                    print("✅ Also approved this link")
                    break
                else:
                    print("Synonym option not available for these names")
            elif response_lower in ['s', 'skip']:
                print("⏭️  Skipped")
                break
            elif response_lower in ['q', 'quit']:
                print("\n💾 Saving progress...")
                return approved, rejected, synonyms, moved_to_category_5
            else:
                print(f"Invalid option: '{response}'. Please try again.")
        
        print(f"\nProgress: {i}/{len(links_to_review)} | Approved: {len(approved)} | Rejected: {len(rejected)}")
        
        if response_lower in ['b', 'approve all', 'approveall', 'all']:
            break
    
    return approved, rejected, synonyms, moved_to_category_5


def apply_links(links: List[Dict], category_name: str, careers: Dict[str, Dict]) -> int:
    """Apply approved links to careers."""
    links_applied = 0
    
    # Filter out already-linked
    links_to_apply = []
    for link in links:
        wrestler_data = get_wrestler_from_link(link)
        if not wrestler_data:
            continue
        wrestler_id = wrestler_data.get('season_wrestler_id')
        career_id = link['career_id']
        if wrestler_id and not check_if_already_linked(wrestler_id, career_id, new_season):
            links_to_apply.append(link)
    
    if not links_to_apply:
        print(f"✅ All links in {category_name} are already applied!")
        return 0
    
    print(f"\nApplying {len(links_to_apply)} links from {category_name}...")
    for link in links_to_apply:
        career_id = link['career_id']
        wrestler_data = get_wrestler_from_link(link)
        wrestler_new_id = wrestler_data.get('season_wrestler_id') if wrestler_data else None
        
        if career_id in careers and wrestler_new_id:
            career = careers[career_id]
            seasons = career.get('seasons', {})
            
            if str(new_season) in seasons:
                continue
            
            seasons[str(new_season)] = wrestler_new_id
            career['seasons'] = seasons

            career_file = Path("data/careers") / f"{career_id}.json"
            with open(career_file, 'w', encoding='utf-8') as f:
                json.dump(career, f, indent=2, ensure_ascii=False)
            maybe_add_career_name_alias(
                wrestler_data.get('name', '') if wrestler_data else '',
                career.get('canonical_name', ''),
            )
            links_applied += 1
    
    print(f"✅ Applied {links_applied} links")
    return links_applied


def create_single_career(wrestler: Dict, anchor_season: int, season: int, careers: Dict[str, Dict] = None) -> str:
    """
    Create a single new career immediately and link the wrestler.
    
    Args:
        wrestler: Wrestler data dictionary
        anchor_season: Anchor season (for created_from_season field)
        season: Season being linked (for the seasons dict)
        careers: Optional careers dict to update
    
    Returns:
        The new career_id
    """
    wrestler_id = wrestler.get('season_wrestler_id')
    name = wrestler.get('name', '')
    
    careers_dir = Path("data/careers")
    
    # Find max career ID
    max_career_num = 0
    for career_file in careers_dir.glob("career_*.json"):
        career_id = career_file.stem
        if career_id.startswith('career_'):
            try:
                num = int(career_id.replace('career_', ''))
                max_career_num = max(max_career_num, num)
            except ValueError:
                pass
    
    max_career_num += 1
    new_career_id = f"career_{max_career_num:06d}"
    
    # Create career
    new_career = {
        'career_id': new_career_id,
        'canonical_name': name,
        'name_norm': normalize_name(name),
        'created_from_season': anchor_season,
        'seasons': {
            str(season): wrestler_id
        },
        'notes': None
    }
    
    # Save career file
    career_file = careers_dir / f"{new_career_id}.json"
    with open(career_file, 'w', encoding='utf-8') as f:
        json.dump(new_career, f, indent=2, ensure_ascii=False)
    
    # Update careers dict if provided
    if careers is not None:
        careers[new_career_id] = new_career
    
    return new_career_id


def create_new_careers(new_careers: List[Dict], anchor_season: int, careers: Dict[str, Dict]) -> int:
    """Create new careers for wrestlers."""
    careers_created = 0
    
    # Filter out already-linked
    careers_to_create = []
    already_linked = get_all_linked_wrestler_ids()
    
    for new_career in new_careers:
        wrestler_id = new_career['wrestler_2024']['season_wrestler_id']
        if wrestler_id not in already_linked:
            careers_to_create.append(new_career)
    
    if not careers_to_create:
        print("✅ All new careers are already created!")
        return 0
    
    # Find max career ID
    careers_dir = Path("data/careers")
    max_career_num = 0
    for career_file in careers_dir.glob("career_*.json"):
        career_id = career_file.stem
        if career_id.startswith('career_'):
            try:
                num = int(career_id.replace('career_', ''))
                max_career_num = max(max_career_num, num)
            except ValueError:
                pass
    
    print(f"\nCreating {len(careers_to_create)} new careers...")
    for new_career_info in careers_to_create:
        wrestler_2024 = new_career_info['wrestler_2024']
        name_2024 = wrestler_2024['name']
        wrestler_id_2024 = wrestler_2024['season_wrestler_id']
        
        max_career_num += 1
        career_id = f"career_{max_career_num:06d}"
        
        career = {
            'career_id': career_id,
            'canonical_name': name_2024,
            'name_norm': normalize_name(name_2024),
            'created_from_season': anchor_season,
            'seasons': {
                '2024': wrestler_id_2024
            },
            'notes': None
        }
        
        career_file = Path("data/careers") / f"{career_id}.json"
        with open(career_file, 'w', encoding='utf-8') as f:
            json.dump(career, f, indent=2, ensure_ascii=False)
        
        careers[career_id] = career
        careers_created += 1
    
    print(f"✅ Created {careers_created} new careers")
    return careers_created


def run_linking_analysis(
    wrestler_list_new: List[Dict],
    careers: Dict[str, Dict],
    name_to_careers: Dict[str, List[str]],
    season_accomplishments_lookup: Dict[int, Dict[str, Dict]],
    career_teams_cache: Dict[str, Set[str]],
    aliases: Dict[str, str],
    already_linked: Set[str],
    new_season: int,
    synonyms: Dict[str, List[str]] = None
) -> Dict[str, List[Dict]]:
    """
    Run the linking analysis and generate categories.
    
    Args:
        wrestler_list_new: List of wrestlers from the new season being linked
        careers: All existing careers
        name_to_careers: Lookup from normalized name to career IDs
        season_accomplishments_lookup: Dict mapping season -> {wrestler_id -> wrestler_data}
        career_teams_cache: Cache of teams for each career
        aliases: Name aliases
        already_linked: Set of wrestler IDs already linked
        new_season: The season being linked (e.g., 2026)
        synonyms: Name synonyms
    """
    results = {
        'Category 1: Rule A (Gold Standard)': [],
        'Category 2: Rule B': [],
        'Category 3: High Confidence (≥80)': [],
        'Category 4: Grade 12 Auto-Create': [],
        'Category 5: New Careers': []
    }
    
    processed = 0
    for wrestler_new in wrestler_list_new:
        processed += 1
        if processed % 500 == 0:
            print(f"  Processed {processed}/{len(wrestler_list_new)} wrestlers...")
        
        wrestler_id_new = wrestler_new.get('season_wrestler_id')
        if not wrestler_id_new:
            continue
        
        # Skip if already linked
        if wrestler_id_new in already_linked:
            continue
        
        name_new = wrestler_new.get('name', '')
        if not name_new:
            continue
        
        # Find candidate careers
        candidates = find_candidate_careers_optimized(
            wrestler_new,
            careers,
            name_to_careers,
            season_accomplishments_lookup,
            career_teams_cache,
            aliases,
            new_season,
            synonyms
        )
        
        # Try Rule A
        auto_linked = False
        for career_id, career, score, reasons in candidates:
            most_recent_season = get_most_recent_season_in_career(career, new_season)
            if not most_recent_season:
                continue
            
            wrestler_existing_id = career.get('seasons', {}).get(str(most_recent_season))
            wrestler_existing = None
            if wrestler_existing_id and most_recent_season in season_accomplishments_lookup:
                wrestler_existing = season_accomplishments_lookup[most_recent_season].get(wrestler_existing_id)
            
            year_diff = new_season - most_recent_season
            
            if auto_link_rule_a_optimized(wrestler_new, career, wrestler_existing, career_teams_cache.get(career_id, set()), aliases, year_diff, new_season, synonyms):
                results['Category 1: Rule A (Gold Standard)'].append({
                    'wrestler_new': {
                        'name': name_new,
                        'season_wrestler_id': wrestler_id_new,
                        'team': wrestler_new.get('team'),
                        'grade': wrestler_new.get('grade')
                    },
                    'career_id': career_id,
                    'rule': 'A',
                    'confidence': 100
                })
                auto_linked = True
                break
        
        if auto_linked:
            continue
        
        # Try Rule B
        for career_id, career, score, reasons in candidates:
            most_recent_season = get_most_recent_season_in_career(career, new_season)
            if not most_recent_season:
                continue
            
            wrestler_existing_id = career.get('seasons', {}).get(str(most_recent_season))
            wrestler_existing = None
            if wrestler_existing_id and most_recent_season in season_accomplishments_lookup:
                wrestler_existing = season_accomplishments_lookup[most_recent_season].get(wrestler_existing_id)
            
            if auto_link_rule_b_optimized(wrestler_new, career, wrestler_existing, career_teams_cache.get(career_id, set()), aliases, new_season, synonyms):
                results['Category 2: Rule B'].append({
                    'wrestler_new': {
                        'name': name_new,
                        'season_wrestler_id': wrestler_id_new,
                        'team': wrestler_new.get('team'),
                        'grade': wrestler_new.get('grade')
                    },
                    'career_id': career_id,
                    'rule': 'B',
                    'confidence': 95
                })
                auto_linked = True
                break
        
        if auto_linked:
            continue
        
        # Check confidence score
        if candidates:
            best_candidate = candidates[0]
            career_id, career, score, reasons = best_candidate
            
            if score >= 80:
                results['Category 3: High Confidence (≥80)'].append({
                    'wrestler_new': {
                        'name': name_new,
                        'season_wrestler_id': wrestler_id_new,
                        'team': wrestler_new.get('team'),
                        'grade': wrestler_new.get('grade')
                    },
                    'career_id': career_id,
                    'rule': 'confidence_score',
                    'confidence': score,
                    'reasons': reasons
                })
                continue
            
            elif score >= 50:
                # Queue for review (add to Category 3)
                results['Category 3: High Confidence (≥80)'].append({
                    'wrestler_new': {
                        'name': name_new,
                        'season_wrestler_id': wrestler_id_new,
                        'team': wrestler_new.get('team'),
                        'grade': wrestler_new.get('grade')
                    },
                    'career_id': career_id,
                    'rule': 'confidence_score',
                    'confidence': score,
                    'reasons': reasons
                })
                continue
        
        # No good match - check if Grade 12
        grade_new = wrestler_new.get('grade')
        has_decent_match = candidates and candidates[0][2] >= 50
        
        if grade_new == 12 and not has_decent_match:
            # Grade 12 with no good matches - auto-create
            results['Category 4: Grade 12 Auto-Create'].append({
                'wrestler_new': {
                    'name': name_new,
                    'season_wrestler_id': wrestler_id_new,
                    'team': wrestler_new.get('team'),
                    'grade': wrestler_new.get('grade')
                },
                'reason': 'grade_12_no_match',
                'best_match_score': candidates[0][2] if candidates else 0
            })
        else:
            # Other cases - needs review
            results['Category 5: New Careers'].append({
                'wrestler_new': {
                    'name': name_new,
                    'season_wrestler_id': wrestler_id_new,
                    'team': wrestler_new.get('team'),
                    'grade': wrestler_new.get('grade')
                },
                'reason': 'no_match_found',
                'best_match_score': candidates[0][2] if candidates else 0
            })
    
    return results


def show_status(
    all_wrestlers: List[Dict],
    linked_wrestler_ids: Set[str],
    category_stats: Dict[str, Dict],
    state: Dict = None,
    season: int = None
):
    """Show overall status."""
    total_wrestlers = len(all_wrestlers)
    linked_count = len(linked_wrestler_ids)
    unlinked_count = total_wrestlers - linked_count
    
    season_label = f"{season} " if season else ""
    print(f"\n{'='*80}")
    print("OVERALL STATUS")
    print(f"{'='*80}")
    print(f"Total {season_label}wrestlers: {total_wrestlers}")
    print(f"Linked to careers: {linked_count}")
    print(f"Not yet linked: {unlinked_count}")
    
    if category_stats:
        print(f"\nCategory Breakdown:")
        for cat_name, stats in category_stats.items():
            # Count only unapplied approved/rejected items
            approved_list = state.get('approved', {}).get(cat_name, []) if state else []
            rejected_list = state.get('rejected', {}).get(cat_name, []) if state else []
            
            # Filter out already-applied links
            unapplied_approved = []
            for link in approved_list:
                wrestler_id = link.get('wrestler_2024', {}).get('season_wrestler_id')
                career_id = link.get('career_id')
                if wrestler_id and career_id and not check_if_already_linked(wrestler_id, career_id):
                    unapplied_approved.append(link)
            
            print(f"  {cat_name}:")
            print(f"    Approved (unapplied): {len(unapplied_approved)}")
            print(f"    Rejected: {len(rejected_list)}")
            print(f"    Applied: {stats.get('applied', False)}")
    
    print(f"{'='*80}\n")


def main():
    parser = argparse.ArgumentParser(
        description='Unified interactive script for linking season to careers'
    )
    parser.add_argument(
        '--season',
        type=int,
        default=2024,
        help='Season to link (default: 2024)'
    )
    parser.add_argument(
        '--anchor-season',
        type=int,
        default=2025,
        help='Anchor season (default: 2025)'
    )
    parser.add_argument(
        '--gender',
        type=str,
        required=True,
        choices=['boys', 'girls'],
        help='Gender (boys or girls)'
    )
    
    args = parser.parse_args()
    
    log_dir = Path("data/career_linking_logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Load data
    print("\nLoading data...")
    careers_dir = Path("data/careers")
    careers = load_careers(careers_dir)
    print(f"Loaded {len(careers)} careers")
    
    # Find all seasons that exist in careers
    all_seasons_in_careers = set()
    for career in careers.values():
        all_seasons_in_careers.update(get_career_seasons(career))
    
    # Also include the new season being linked
    new_season = args.season
    all_seasons_in_careers.add(new_season)
    
    print(f"Found seasons in careers: {sorted(all_seasons_in_careers)}")
    
    # Load season accomplishments for all seasons
    season_accomplishments_lookup = {}  # season -> {wrestler_id -> wrestler_data}
    season_accomplishments_list_dict = {}  # season -> [wrestler_data]
    
    for season in all_seasons_in_careers:
        try:
            lookup = load_season_accomplishments(season, args.gender)
            wrestler_list = load_season_accomplishments_list(season, args.gender)
            season_accomplishments_lookup[season] = lookup
            season_accomplishments_list_dict[season] = wrestler_list
            print(f"Loaded {len(wrestler_list)} wrestlers from {season}")
        except FileNotFoundError:
            print(f"Warning: Season {season} accomplishments not found, skipping")
            continue
    
    # Load the new season being linked
    wrestler_lookup_new = season_accomplishments_lookup.get(new_season, {})
    wrestler_list_new = season_accomplishments_list_dict.get(new_season, [])
    
    if not wrestler_list_new:
        print(f"Error: No wrestlers found for season {new_season}")
        return
    
    already_linked = get_all_linked_wrestler_ids(new_season)
    
    # Build lookups for analysis
    print("Building lookup structures...")
    name_to_careers = defaultdict(list)
    for career_id, career in careers.items():
        name_norm = career.get('name_norm', '')
        if name_norm:
            name_to_careers[name_norm].append(career_id)
    
    career_teams_cache = {}
    for career_id, career in careers.items():
        career_teams_cache[career_id] = get_career_teams(career, season_accomplishments_list_dict)
    
    aliases = load_name_aliases()
    
    # Load name synonyms (initialize early)
    synonyms = load_name_synonyms()
    seed_synonyms = get_seed_synonyms()
    for canonical, variants in seed_synonyms.items():
        if canonical not in synonyms:
            synonyms[canonical] = []
        for variant in variants:
            if variant not in synonyms[canonical]:
                synonyms[canonical].append(variant)
    
    # Run analysis to generate categories
    print("\nAnalyzing wrestlers and generating categories...")
    categories = run_linking_analysis(
        wrestler_list_new,
        careers,
        name_to_careers,
        season_accomplishments_lookup,
        career_teams_cache,
        aliases,
        already_linked,
        new_season,
        synonyms
    )
    
    print(f"✅ Analysis complete:")
    print(f"   Category 1 (Rule A): {len(categories.get('Category 1: Rule A (Gold Standard)', []))}")
    print(f"   Category 2 (Rule B): {len(categories.get('Category 2: Rule B', []))}")
    print(f"   Category 3 (High Confidence): {len(categories.get('Category 3: High Confidence (≥80)', []))}")
    print(f"   Category 4 (Grade 12 Auto): {len(categories.get('Category 4: Grade 12 Auto-Create', []))}")
    print(f"   Category 5 (New Careers): {len(categories.get('Category 5: New Careers', []))}")
    
    # Track state
    state_file = log_dir / f"{args.season}_interactive_state.json"
    if state_file.exists():
        with open(state_file, 'r') as f:
            state = json.load(f)
        # Ensure all categories exist in state (for backward compatibility)
        all_categories = [
            'Category 1: Rule A (Gold Standard)',
            'Category 2: Rule B',
            'Category 3: High Confidence (≥80)',
            'Category 4: Grade 12 Auto-Create',
            'Category 5: New Careers'
        ]
        for cat in all_categories:
            if 'approved' not in state:
                state['approved'] = {}
            if 'rejected' not in state:
                state['rejected'] = {}
            if 'applied' not in state:
                state['applied'] = {}
            if cat not in state['approved']:
                state['approved'][cat] = []
            if cat not in state['rejected']:
                state['rejected'][cat] = []
            if cat not in state['applied']:
                state['applied'][cat] = False
    else:
        state = {
            'approved': {cat: [] for cat in categories.keys()},
            'rejected': {cat: [] for cat in categories.keys()},
            'applied': {cat: False for cat in categories.keys()}
        }
    
    # Main menu loop
    while True:
        # Refresh already_linked set
        already_linked = get_all_linked_wrestler_ids(new_season)
        
        show_status(wrestler_list_new, already_linked, {
            cat: {
                'approved': len(state['approved'].get(cat, [])),
                'rejected': len(state['rejected'].get(cat, [])),
                'applied': state['applied'].get(cat, False)
            }
            for cat in categories.keys()
        }, state, new_season)
        
        print("MAIN MENU")
        print("="*80)
        print("1. Review Category 1: Rule A (Gold Standard)")
        print("2. Review Category 2: Rule B")
        print("3. Review Category 3: High Confidence (≥80)")
        print("4. Review Category 4: Grade 12 Auto-Create")
        print("5. Review Category 5: New Careers")
        print("6. Apply all approved links")
        print("7. Create all approved new careers")
        print("8. Show unlinked wrestlers")
        print("9. Exit")
        print("="*80)
        
        choice = input("\nSelect option: ").strip()
        
        if choice == '1':
            if 'Category 1: Rule A (Gold Standard)' in categories:
                approved, rejected, synonyms, _ = review_category(
                    'Category 1: Rule A (Gold Standard)',
                    categories['Category 1: Rule A (Gold Standard)'],
                    wrestler_lookup_new,
                    season_accomplishments_lookup,
                    already_linked,
                    new_season,
                    synonyms
                )
                # Links are already auto-applied in review_category, just track for state
                state['approved']['Category 1: Rule A (Gold Standard)'].extend(approved)
                state['rejected']['Category 1: Rule A (Gold Standard)'].extend(rejected)
                # Mark as applied since auto-apply happened
                state['applied']['Category 1: Rule A (Gold Standard)'] = True
            else:
                print("Category 1 data not found. Run link_season_to_careers.py first.")
        
        elif choice == '2':
            if 'Category 2: Rule B' in categories:
                approved, rejected, synonyms, _ = review_category(
                    'Category 2: Rule B',
                    categories['Category 2: Rule B'],
                    wrestler_lookup_new,
                    season_accomplishments_lookup,
                    already_linked,
                    new_season,
                    args.anchor_season,
                    synonyms,
                    state.get('rejected', {}).get('Category 2: Rule B', [])
                )
                # Links are already auto-applied in review_category, just track for state
                state['approved']['Category 2: Rule B'].extend(approved)
                state['rejected']['Category 2: Rule B'].extend(rejected)
                # Mark as applied since auto-apply happened
                state['applied']['Category 2: Rule B'] = True
            else:
                print("Category 2 data not found. Run link_season_to_careers.py first.")
        
        elif choice == '3':
            if 'Category 3: High Confidence (≥80)' in categories:
                approved, rejected, synonyms, moved_to_cat5 = review_category(
                    'Category 3: High Confidence (≥80)',
                    categories['Category 3: High Confidence (≥80)'],
                    wrestler_lookup_new,
                    season_accomplishments_lookup,
                    already_linked,
                    new_season,
                    args.anchor_season,
                    synonyms,
                    state.get('rejected', {}).get('Category 3: High Confidence (≥80)', [])
                )
                # Links are already auto-applied in review_category, just track for state
                state['approved']['Category 3: High Confidence (≥80)'].extend(approved)
                state['rejected']['Category 3: High Confidence (≥80)'].extend(rejected)
                # Mark as applied since auto-apply happened
                state['applied']['Category 3: High Confidence (≥80)'] = True
                # Move rejected wrestlers with no alternatives to Category 5
                if moved_to_cat5:
                    if 'Category 5: New Careers' not in categories:
                        categories['Category 5: New Careers'] = []
                    categories['Category 5: New Careers'].extend(moved_to_cat5)
                    print(f"\n📝 Moved {len(moved_to_cat5)} rejected wrestlers to Category 5 (New Careers)")
            else:
                print("Category 3 data not found. Run link_season_to_careers.py first.")
        
        elif choice == '4':
            if 'Category 4: Grade 12 Auto-Create' in categories:
                # Grade 12 auto-create - show summary and allow bulk approve
                grade_12_careers = categories['Category 4: Grade 12 Auto-Create']
                print(f"\n{'='*80}")
                print("CATEGORY 4: GRADE 12 AUTO-CREATE")
                print(f"{'='*80}")
                print(f"Found {len(grade_12_careers)} Grade 12 wrestlers with no good matches")
                print("These are seniors (last year), so they should get new careers.")
                
                # Check if already reviewed
                already_reviewed_ids = set()
                for reviewed in state['approved'].get('Category 4: Grade 12 Auto-Create', []):
                    wrestler_data = get_wrestler_from_link(reviewed)
                    if wrestler_data:
                        already_reviewed_ids.add(wrestler_data.get('season_wrestler_id'))
                
                remaining = []
                for nc in grade_12_careers:
                    wrestler_data = get_wrestler_from_link(nc)
                    if wrestler_data and wrestler_data.get('season_wrestler_id') not in already_reviewed_ids:
                        remaining.append(nc)
                
                if not remaining:
                    print(f"\n✅ All {len(grade_12_careers)} Grade 12 careers have been approved!")
                    continue
                
                print(f"Remaining to approve: {len(remaining)}")
                print("\nOptions:")
                print("  [a]pprove all - Approve all remaining Grade 12 careers")
                print("  [r]eview - Review each one individually")
                print("  [s]kip - Skip for now")
                
                response = input("\n> ").strip().lower()
                
                if response == 'a' or 'approve all' in response:
                    # Create careers immediately for all remaining
                    print(f"\nCreating {len(remaining)} Grade 12 careers...")
                    for new_career in remaining:
                        wrestler_data_from_link = get_wrestler_from_link(new_career)
                        wrestler_id = wrestler_data_from_link.get('season_wrestler_id') if wrestler_data_from_link else None
                        wrestler_2024 = wrestler_lookup_new.get(wrestler_id) if wrestler_id else None
                        if wrestler_2024:
                            wrestler_data = get_wrestler_from_link({'wrestler_new': wrestler_2024}) if isinstance(wrestler_2024, dict) and 'season_wrestler_id' in wrestler_2024 else wrestler_2024
                            new_career_id = create_single_career(wrestler_data, args.anchor_season, new_season, careers)
                            print(f"  ✅ Created {new_career_id} for {wrestler_2024.get('name')}")
                    print(f"\n✅ Created all {len(remaining)} Grade 12 careers")
                    # Reload careers to include newly created ones
                    careers = load_careers(Path("data/careers"))
                elif response == 'r' or response == 'review':
                    # Review individually (similar to Category 5 but simpler)
                    approved_new = []
                    for i, new_career in enumerate(remaining, 1):
                        wrestler_data_from_link = get_wrestler_from_link(new_career)
                        if not wrestler_data_from_link:
                            continue
                        wrestler_id = wrestler_data_from_link.get('season_wrestler_id')
                        wrestler_new = wrestler_lookup_new.get(wrestler_id)
                        if not wrestler_new:
                            continue
                        print(f"\n{i}/{len(remaining)}: {wrestler_data_from_link.get('name')} ({wrestler_data_from_link.get('team')})")
                        print(f"  Best match score: {new_career.get('best_match_score', 0)}")
                        resp = input("  [a]pprove / [s]kip / [q]uit: ").strip().lower()
                        if resp == 'a':
                            # Create career immediately
                            wrestler_data = get_wrestler_from_link({'wrestler_new': wrestler_new}) if isinstance(wrestler_new, dict) and 'season_wrestler_id' in wrestler_new else wrestler_new
                            new_career_id = create_single_career(wrestler_data, args.anchor_season, new_season, careers)
                            approved_new.append({
                                'wrestler_new': wrestler_data_from_link,
                                'career_id': new_career_id,
                                'action': 'new_career_created'
                            })
                            print(f"  ✅ Created {new_career_id} and linked wrestler")
                        elif resp == 'q':
                            break
                    # Reload careers to include newly created ones
                    if approved_new:
                        careers = load_careers(Path("data/careers"))
                else:
                    print("⏭️  Skipped")
            else:
                print("Category 4 data not found. Run link_season_to_careers.py first.")
        
        elif choice == '5':
            if 'Category 5: New Careers' in categories:
                # For new careers, show them with alternative matches
                new_careers = categories['Category 5: New Careers']
                print(f"\nFound {len(new_careers)} candidates for new careers")
                print("Review each one - we'll show alternative matches if available:")
                
                approved_new = []
                rejected_new = []
                alternative_matches = []
                
                # Import linking functions to find alternatives
                import sys
                import importlib.util
                link_script_path = Path(__file__).parent / "link_season_to_careers.py"
                spec = importlib.util.spec_from_file_location("link_season_to_careers", link_script_path)
                link_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(link_module)
                
                # Build lookups for finding alternatives
                careers = link_module.load_careers(Path("data/careers"))
                name_to_careers = {}
                for career_id, career in careers.items():
                    name_norm = career.get('name_norm', '')
                    if name_norm:
                        if name_norm not in name_to_careers:
                            name_to_careers[name_norm] = []
                        name_to_careers[name_norm].append(career_id)
                
                career_teams_cache = {}
                for career_id, career in careers.items():
                    career_teams_cache[career_id] = get_career_teams(career, season_accomplishments_list_dict)
                
                # Filter out already-reviewed wrestlers
                already_reviewed_ids = set()
                for reviewed in state['approved'].get('Category 5: New Careers', []):
                    wrestler_data = get_wrestler_from_link(reviewed)
                    if wrestler_data:
                        already_reviewed_ids.add(wrestler_data.get('season_wrestler_id'))
                for reviewed in state['rejected'].get('Category 5: New Careers', []):
                    wrestler_data = get_wrestler_from_link(reviewed)
                    if wrestler_data:
                        already_reviewed_ids.add(wrestler_data.get('season_wrestler_id'))
                
                new_careers_to_review = []
                for nc in new_careers:
                    wrestler_data = get_wrestler_from_link(nc)
                    if wrestler_data and wrestler_data.get('season_wrestler_id') not in already_reviewed_ids:
                        new_careers_to_review.append(nc)
                
                # Sort by best_match_score (highest confidence first)
                new_careers_to_review.sort(key=lambda x: x.get('best_match_score', 0), reverse=True)
                
                if not new_careers_to_review:
                    print(f"\n✅ All {len(new_careers)} new career candidates have been reviewed!")
                    print(f"   Approved: {len(state['approved'].get('Category 5: New Careers', []))}")
                    print(f"   Rejected: {len(state['rejected'].get('Category 5: New Careers', []))}")
                    continue
                
                print(f"\nResuming review: {len(new_careers_to_review)} remaining (out of {len(new_careers)} total)")
                print(f"Sorted by confidence: highest ({new_careers_to_review[0].get('best_match_score', 0)}) to lowest ({new_careers_to_review[-1].get('best_match_score', 0)})")
                
                for i, new_career in enumerate(new_careers_to_review, 1):
                    wrestler_data_from_link = get_wrestler_from_link(new_career)
                    if not wrestler_data_from_link:
                        continue
                    wrestler_id = wrestler_data_from_link.get('season_wrestler_id')
                    wrestler_new = wrestler_lookup_new.get(wrestler_id)
                    
                    if not wrestler_new:
                        # Auto-create career if wrestler not found (shouldn't happen, but handle gracefully)
                        print(f"⚠️  Wrestler data not found for {wrestler_data_from_link.get('name', 'Unknown')}, skipping...")
                        continue
                    
                    name_new = wrestler_new.get('name', '')
                    team_new = wrestler_new.get('team', '')
                    grade_new = wrestler_new.get('grade')
                    weight_new = wrestler_new.get('final_weight')
                    
                    # Extract last name
                    name_parts_new = name_new.split()
                    last_name_new = name_parts_new[-1] if name_parts_new else ''
                    first_name_new = name_parts_new[0] if len(name_parts_new) > 1 else ''
                    
                    # Find alternative matches
                    aliases = load_name_aliases()
                    synonyms = load_name_synonyms()
                    candidates = find_candidate_careers_optimized(
                        wrestler_new,
                        careers,
                        name_to_careers,
                        season_accomplishments_lookup,
                        career_teams_cache,
                        aliases,
                        new_season,
                        synonyms
                    )
                    
                    # Filter out already-linked careers
                    candidates = [(cid, c, s, r) for cid, c, s, r in candidates 
                                 if wrestler_id not in already_linked and 
                                 not check_if_already_linked(wrestler_id, cid)]
                    
                    # Filter by exact last name match and confidence >= 50
                    matching_careers = []
                    for cid, c, score, reasons in candidates:
                        # Only include if confidence >= 50
                        if score < 50:
                            continue
                        
                        # Check for exact last name match
                        career_name = c.get('canonical_name', '')
                        career_name_parts = career_name.split()
                        career_last_name = career_name_parts[-1] if career_name_parts else ''
                        
                        if last_name_new.lower() != career_last_name.lower():
                            continue
                        
                        # Get wrestler data from most recent season in career
                        existing_seasons = sorted([int(s) for s in c.get('seasons', {}).keys() if s.isdigit()], reverse=True)
                        wrestler_existing = None
                        existing_season = None
                        if existing_seasons:
                            existing_season = existing_seasons[0]
                            wrestler_existing_id = c.get('seasons', {}).get(str(existing_season))
                            if wrestler_existing_id and existing_season in season_accomplishments_lookup:
                                wrestler_existing = season_accomplishments_lookup[existing_season].get(wrestler_existing_id)
                        
                        career_first_name = career_name_parts[0] if len(career_name_parts) > 1 else ''
                        team_existing = wrestler_existing.get('team', '') if wrestler_existing else ''
                        grade_existing = wrestler_existing.get('grade') if wrestler_existing else None
                        weight_existing = wrestler_existing.get('final_weight') if wrestler_existing else None
                        
                        # Calculate match scores
                        team_match = normalize_team_name(team_new) == normalize_team_name(team_existing) if wrestler_existing else False
                        first_name_sim = name_similarity(first_name_new, career_first_name) if first_name_new and career_first_name else 0.0
                        first_name_fuzzy = first_name_sim >= 0.7
                        # Calculate year difference for grade progression
                        year_diff = new_season - existing_season if existing_season else 0
                        grade_match = (grade_new is not None and grade_existing is not None and 
                                      grade_new + year_diff == grade_existing) if existing_season else False
                        weight_match = (weight_new is not None and weight_existing is not None and
                                      abs(weight_new - weight_existing) <= 2)
                        
                        # Calculate priority score (similar to Category 3)
                        priority_score = 0
                        if team_match and first_name_fuzzy:
                            priority_score = 1000 + first_name_sim * 100
                        elif team_match:
                            priority_score = 500 + first_name_sim * 50
                        elif first_name_fuzzy:
                            priority_score = 300 + first_name_sim * 30
                        else:
                            priority_score = first_name_sim * 10
                        
                        if grade_match:
                            priority_score += 20
                        if weight_match:
                            priority_score += 10
                        
                        # Use the confidence score from find_candidate_careers_optimized
                        # But ensure it's at least 50 (already filtered above)
                        matching_careers.append({
                            'career_id': cid,
                            'career_name': career_name,
                            'team': team_existing,
                            'grade': grade_existing,
                            'weight': weight_existing,
                            'team_match': team_match,
                            'first_name_fuzzy': first_name_fuzzy,
                            'first_name_sim': first_name_sim,
                            'grade_match': grade_match,
                            'weight_match': weight_match,
                            'priority_score': priority_score,
                            'confidence_score': score,
                            'is_proposed': False
                        })
                    
                    # Sort by priority score (descending)
                    matching_careers.sort(key=lambda x: x['priority_score'], reverse=True)
                    
                    # Check if best match is < 40 confidence
                    best_match_confidence = matching_careers[0]['confidence_score'] if matching_careers else 0
                    
                    if best_match_confidence < 40:
                        # No good match - recommend new career
                        print(f"\n{'='*110}")
                        print(f"NEW CAREER CANDIDATE {i}/{len(new_careers_to_review)}")
                        print(f"{'='*110}")
                        print(f"Wrestler: {name_new} ({team_new}, Grade {grade_new}, {weight_new} lbs)")
                        print(f"Reason: {new_career.get('reason', 'unknown')}")
                        print(f"\n⚠️  No good match found (best match confidence: {best_match_confidence:.0f}% < 40%)")
                        print(f"Recommendation: Create new career")
                        print(f"\nOptions:")
                        print("  [n]ew career - Create new career (recommended)")
                        print("  [s]kip - Skip for now")
                        print("  [q]uit - Save progress and return to main menu")
                        print("  [N]ew career all remaining - Create new careers for all remaining")
                        
                        response = input("\n> ").strip()
                        response_lower = response.lower()
                        
                        # Check for capital 'N' first (before lowercasing check)
                        if response == 'N' or 'new career all' in response_lower:
                            # Create careers for all remaining immediately
                            remaining = new_careers_to_review[i-1:]
                            print(f"\nCreating {len(remaining)} new careers...")
                            for remaining_career in remaining:
                                remaining_wrestler_data = get_wrestler_from_link(remaining_career)
                                if remaining_wrestler_data:
                                    remaining_wrestler_id = remaining_wrestler_data.get('season_wrestler_id')
                                    remaining_wrestler = wrestler_lookup_new.get(remaining_wrestler_id)
                                    if remaining_wrestler:
                                        wrestler_data = get_wrestler_from_link({'wrestler_new': remaining_wrestler}) if isinstance(remaining_wrestler, dict) and 'season_wrestler_id' in remaining_wrestler else remaining_wrestler
                                        new_career_id = create_single_career(wrestler_data, args.anchor_season, new_season, careers)
                                        approved_new.append({
                                            'wrestler_new': remaining_wrestler_data,
                                            'career_id': new_career_id,
                                            'action': 'new_career_created'
                                        })
                                        print(f"  ✅ Created {new_career_id} for {remaining_wrestler.get('name')}")
                            print(f"\n✅ Created all {len(remaining)} remaining new careers")
                            # Reload careers to include newly created ones
                            careers = load_careers(Path("data/careers"))
                            break
                        elif response_lower == 'n' or response_lower == 'new career':
                            # Create career immediately
                            wrestler_data = get_wrestler_from_link({'wrestler_new': wrestler_new}) if isinstance(wrestler_new, dict) and 'season_wrestler_id' in wrestler_new else wrestler_new
                            new_career_id = create_single_career(wrestler_data, args.anchor_season, new_season, careers)
                            approved_new.append({
                                'wrestler_new': wrestler_data_from_link,
                                'career_id': new_career_id,
                                'action': 'new_career_created'
                            })
                            print(f"✅ Created new career {new_career_id} and linked wrestler")
                        elif response_lower == 's' or response_lower == 'skip':
                            print("⏭️  Skipped")
                        elif response_lower == 'q' or response_lower == 'quit':
                            print("\n💾 Saving progress...")
                            break
                        else:
                            print("Invalid option, defaulting to new career")
                            # Create career immediately
                            wrestler_data = get_wrestler_from_link({'wrestler_new': wrestler_new}) if isinstance(wrestler_new, dict) and 'season_wrestler_id' in wrestler_new else wrestler_new
                            new_career_id = create_single_career(wrestler_data, args.anchor_season, new_season, careers)
                            approved_new.append({
                                'wrestler_new': wrestler_data_from_link,
                                'career_id': new_career_id,
                                'action': 'new_career_created'
                            })
                            print(f"✅ Created new career {new_career_id} and linked wrestler")
                    else:
                        # Show table like Category 3
                        print(f"\n{'='*110}")
                        print(f"ALL MATCHES FOR: {name_new} ({team_new}, Grade {grade_new}, {weight_new} lbs)")
                        print(f"{'='*110}")
                        print(f"{'#':<4} {'Name':<25} {'Team':<25} {'Grade':<8} {'Weight':<10} {'Team':<6} {'Name':<6} {'Grade':<6} {'Weight':<6} {'Score':<8}")
                        print(f"{'-'*110}")
                        
                        for idx, match in enumerate(matching_careers, 1):
                            # Color codes: ✅ = exact match, 🟡 = close match, ❌ = no match
                            team_symbol = "✅" if match['team_match'] else "❌"
                            name_symbol = "✅" if match['first_name_sim'] >= 0.9 else ("🟡" if match['first_name_fuzzy'] else "❌")
                            grade_symbol = "✅" if match['grade_match'] else ("🟡" if (grade_new and match['grade'] and abs(grade_new - match['grade']) <= 2) else "❌")
                            weight_symbol = "✅" if match['weight_match'] else ("🟡" if (weight_new and match['weight'] and abs(weight_new - match['weight']) <= 5) else "❌")
                            
                            grade_str = str(match['grade']) if match['grade'] is not None else '?'
                            weight_str = f"{match['weight']} lbs" if match['weight'] is not None else '?'
                            score_str = str(int(match['confidence_score']))
                            
                            print(f"{idx:<4} {match['career_name']:<25} {match['team']:<25} {grade_str:<8} {weight_str:<10} "
                                  f"{team_symbol:<6} {name_symbol:<6} {grade_symbol:<6} {weight_symbol:<6} {score_str:<8}")
                        
                        print(f"{'='*110}")
                        print(f"\nOptions:")
                        if matching_careers:
                            print(f"  [1-{len(matching_careers)}] - Link to match shown above")
                        print(f"  [n]ew career - Create new career")
                        print(f"  [s]kip - Skip for now")
                        print(f"  [q]uit - Save progress and return to main menu")
                        print(f"  [N]ew career all remaining - Create new careers for all remaining")
                        
                        response = input("\n> ").strip()
                        response_lower = response.lower()
                        
                        # Check for capital 'N' first (before lowercasing check)
                        if response == 'N' or 'new career all' in response_lower:
                            # Create careers for all remaining immediately
                            remaining = new_careers_to_review[i-1:]
                            print(f"\nCreating {len(remaining)} new careers...")
                            for remaining_career in remaining:
                                remaining_wrestler_data = get_wrestler_from_link(remaining_career)
                                if remaining_wrestler_data:
                                    remaining_wrestler_id = remaining_wrestler_data.get('season_wrestler_id')
                                    remaining_wrestler = wrestler_lookup_new.get(remaining_wrestler_id)
                                    if remaining_wrestler:
                                        wrestler_data = get_wrestler_from_link({'wrestler_new': remaining_wrestler}) if isinstance(remaining_wrestler, dict) and 'season_wrestler_id' in remaining_wrestler else remaining_wrestler
                                        new_career_id = create_single_career(wrestler_data, args.anchor_season, new_season, careers)
                                        approved_new.append({
                                            'wrestler_new': remaining_wrestler_data,
                                            'career_id': new_career_id,
                                            'action': 'new_career_created'
                                        })
                                        print(f"  ✅ Created {new_career_id} for {remaining_wrestler.get('name')}")
                            print(f"\n✅ Created all {len(remaining)} remaining new careers")
                            # Reload careers to include newly created ones
                            careers = load_careers(Path("data/careers"))
                            break
                        elif response.isdigit():
                            alt_idx = int(response) - 1
                            if 0 <= alt_idx < len(matching_careers):
                                # Link to selected match
                                selected_match = matching_careers[alt_idx]
                                alt_career_id = selected_match['career_id']
                                alternative_matches.append({
                                    'wrestler_new': wrestler_data_from_link,
                                    'career_id': alt_career_id,
                                    'rule': 'alternative_match',
                                    'confidence': int(selected_match['confidence_score']),
                                    'reasons': ['last_name_match', 'category_5_match']
                                })
                                # Auto-apply immediately
                                if not check_if_already_linked(wrestler_id, alt_career_id):
                                    alt_career_file = Path("data/careers") / f"{alt_career_id}.json"
                                    with open(alt_career_file, 'r') as f:
                                        alt_career_data = json.load(f)
                                    alt_seasons = alt_career_data.get('seasons', {})
                                    if str(new_season) not in alt_seasons:
                                        alt_seasons[str(new_season)] = wrestler_id
                                        alt_career_data['seasons'] = alt_seasons
                                        with open(alt_career_file, 'w', encoding='utf-8') as f:
                                            json.dump(alt_career_data, f, indent=2, ensure_ascii=False)
                                        print(f"✅ Linked to {selected_match['career_name']} and applied")
                                else:
                                    print("✅ Linked to alternative career (already linked)")
                                rejected_new.append(new_career)  # Mark original as rejected
                            else:
                                print(f"Invalid number. Please enter 1-{len(matching_careers)}")
                                continue
                        elif response_lower == 'n' or response_lower == 'new career':
                            # Create career immediately
                            wrestler_data = get_wrestler_from_link({'wrestler_new': wrestler_new}) if isinstance(wrestler_new, dict) and 'season_wrestler_id' in wrestler_new else wrestler_new
                            new_career_id = create_single_career(wrestler_data, args.anchor_season, new_season, careers)
                            approved_new.append({
                                'wrestler_new': wrestler_data_from_link,
                                'career_id': new_career_id,
                                'action': 'new_career_created'
                            })
                            print(f"✅ Created new career {new_career_id} and linked wrestler")
                        elif response_lower == 's' or response_lower == 'skip':
                            print("⏭️  Skipped")
                        elif response_lower == 'q' or response_lower == 'quit':
                            print("\n💾 Saving progress...")
                            break
                        else:
                            print("Invalid option, defaulting to new career")
                            # Create career immediately
                            wrestler_data = get_wrestler_from_link({'wrestler_new': wrestler_new}) if isinstance(wrestler_new, dict) and 'season_wrestler_id' in wrestler_new else wrestler_new
                            new_career_id = create_single_career(wrestler_data, args.anchor_season, new_season, careers)
                            approved_new.append({
                                'wrestler_new': wrestler_data_from_link,
                                'career_id': new_career_id,
                                'action': 'new_career_created'
                            })
                            print(f"✅ Created new career {new_career_id} and linked wrestler")
                    
                    # Save after each decision
                    state['approved']['Category 5: New Careers'] = approved_new
                    state['rejected']['Category 5: New Careers'] = rejected_new
                    with open(state_file, 'w') as f:
                        json.dump(state, f, indent=2)
                    
                    print(f"\nProgress: {i}/{len(new_careers_to_review)} | New Careers: {len(approved_new)} | Alternatives: {len(alternative_matches)}")
                    
                    if response_lower == 'q' or response_lower == 'quit':
                        break
                
                state['approved']['Category 5: New Careers'] = approved_new
                state['rejected']['Category 5: New Careers'] = rejected_new
                
                # Add alternative matches to appropriate category
                if alternative_matches:
                    print(f"\n✅ Found {len(alternative_matches)} alternative matches")
                    # Add to Category 3 for review
                    if 'Category 3: High Confidence (≥80)' not in state['approved']:
                        state['approved']['Category 3: High Confidence (≥80)'] = []
                    state['approved']['Category 3: High Confidence (≥80)'].extend(alternative_matches)
            else:
                print("Category 5 data not found. Run link_season_to_careers.py first.")
        
        elif choice == '6':
            # Apply all approved links
            total_applied = 0
            for cat_name, approved_links in state['approved'].items():
                if approved_links and not state['applied'].get(cat_name, False):
                    # Only apply links (not new careers)
                    if 'links' in str(cat_name) or any('career_id' in link for link in approved_links):
                        applied = apply_links(approved_links, cat_name, careers)
                        total_applied += applied
                        if applied > 0:
                            state['applied'][cat_name] = True
                            # Reload careers to get updated state
                            careers = load_careers(careers_dir)
            print(f"\n✅ Total applied: {total_applied}")
        
        elif choice == '7':
            # Create new careers (both Category 4 and 5)
            total_created = 0
            
            if 'Category 4: Grade 12 Auto-Create' in state['approved']:
                created = create_new_careers(
                    state['approved']['Category 4: Grade 12 Auto-Create'],
                    args.anchor_season,
                    careers
                )
                total_created += created
                print(f"✅ Created {created} Grade 12 careers")
                # Reload careers
                careers = load_careers(careers_dir)
            
            if 'Category 5: New Careers' in state['approved']:
                created = create_new_careers(
                    state['approved']['Category 5: New Careers'],
                    args.anchor_season,
                    careers
                )
                total_created += created
                print(f"✅ Created {created} other new careers")
                # Reload careers
                careers = load_careers(careers_dir)
            
            if total_created > 0:
                already_linked = get_all_linked_wrestler_ids()
            else:
                print("No new careers approved yet.")
        
        elif choice == '8':
            # Show unlinked wrestlers and allow creating careers for them
            linked = get_all_linked_wrestler_ids()
            unlinked = [w for w in wrestler_list_2024 if w.get('season_wrestler_id') not in linked]
            
            if not unlinked:
                print("\n✅ All wrestlers are linked!")
                continue
            
            print(f"\n{'='*80}")
            print(f"UNLINKED WRESTLERS: {len(unlinked)}")
            print(f"{'='*80}")
            
            # Show all unlinked wrestlers
            for i, w in enumerate(unlinked, 1):
                name = w.get('name', 'Unknown')
                team = w.get('team', 'Unknown')
                grade = w.get('grade', '?')
                weight = w.get('final_weight', '?')
                print(f"  {i:3d}. {name:<30} ({team}, Grade {grade}, {weight} lbs)")
            
            print(f"\n{'='*80}")
            print("Options:")
            print("  [c]reate all - Create new careers for all unlinked wrestlers")
            print("  [r]eturn - Return to main menu")
            
            response = input("\n> ").strip().lower()
            
            if response == 'c' or response == 'create all':
                # Convert unlinked wrestlers to new career format
                new_careers_list = []
                for w in unlinked:
                    new_careers_list.append({
                        'wrestler_2024': {
                            'name': w.get('name'),
                            'season_wrestler_id': w.get('season_wrestler_id'),
                            'team': w.get('team'),
                            'grade': w.get('grade')
                        },
                        'reason': 'unlinked_remaining'
                    })
                
                # Add to Category 5 approved list
                if 'Category 5: New Careers' not in state['approved']:
                    state['approved']['Category 5: New Careers'] = []
                state['approved']['Category 5: New Careers'].extend(new_careers_list)
                
                print(f"\n✅ Added {len(new_careers_list)} unlinked wrestlers to Category 5 approved list")
                print("   Run option 7 (Create all approved new careers) to create them.")
            else:
                print("Returning to main menu...")
        
        elif choice == '9':
            # Save state and exit
            with open(state_file, 'w') as f:
                json.dump(state, f, indent=2)
            print("\n💾 State saved. Goodbye!")
            break
        
        else:
            print("Invalid option. Please try again.")
        
        # Save state after each action
        with open(state_file, 'w') as f:
            json.dump(state, f, indent=2)
    
    return 0


if __name__ == '__main__':
    exit(main())

