#!/usr/bin/env python3
"""
Link a season (e.g., 2024) into existing careers created from anchor season (e.g., 2025).

This script performs conservative, reversible linking of season accomplishments
to existing career records. It prioritizes accuracy over completeness.

Output:
- Updated career JSON files
- Review log for ambiguous cases
- Results log for all actions taken
"""

import json
import argparse
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict
from difflib import SequenceMatcher

_CAREERS_DIR = None  # overridden in main() based on --gender


def normalize_name(name: str) -> str:
    """
    Normalize a wrestler's name for matching.
    
    Normalization:
    1. Convert to lowercase
    2. Remove extra whitespace
    3. Collapse multiple spaces
    """
    if not name:
        return ""
    
    normalized = name.lower().strip()
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized


def normalize_team_name(team: str) -> str:
    """Normalize team name for matching."""
    if not team:
        return ""
    # Remove parentheticals like "(Louisville)"
    team = re.sub(r'\s*\([^)]+\)', '', team)
    # Remove "High School" suffix
    team = re.sub(r'\s+High School$', '', team, flags=re.IGNORECASE)
    # Normalize hyphens and spaces
    team = re.sub(r'[-–—]', ' ', team)
    team = re.sub(r'\s+', ' ', team)
    return team.lower().strip()


def load_name_aliases() -> Dict[str, str]:
    """
    Load name aliases and create a lookup dictionary.
    
    Returns:
        Dictionary mapping variant_name -> canonical_name
    """
    alias_file = Path("mt/name_alias.json")
    if not alias_file.exists():
        return {}
    
    with open(alias_file, 'r') as f:
        alias_data = json.load(f)
    
    # Build lookup: variant -> canonical
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


def load_careers(careers_dir: Path) -> Dict[str, Dict]:
    """
    Load all existing career files.
    
    Returns:
        Dictionary mapping career_id -> career_data
    """
    careers = {}
    career_files = list(careers_dir.glob("career_*.json"))
    
    print(f"Loading {len(career_files)} existing careers...")
    
    for career_file in career_files:
        try:
            with open(career_file, 'r') as f:
                career = json.load(f)
                career_id = career.get('career_id')
                if career_id:
                    careers[career_id] = career
        except Exception as e:
            print(f"⚠️  Warning: Could not load {career_file}: {e}")
    
    return careers


def load_season_accomplishments(season: int, gender: str) -> List[Dict]:
    """Load season accomplishments for a given season."""
    file_path = Path(f"data/season_accomplishments/{gender}/{season}/season_accomplishments.json")
    
    if not file_path.exists():
        raise FileNotFoundError(f"Season accomplishments file not found: {file_path}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    return data.get('wrestlers', [])


def get_career_seasons(career: Dict) -> Set[int]:
    """Extract set of seasons already linked in a career."""
    seasons = career.get('seasons', {})
    if isinstance(seasons, dict):
        return {int(s) for s in seasons.keys() if s.isdigit()}
    return set()


def get_career_teams(career: Dict, season_accomplishments: Dict[int, List[Dict]]) -> Set[str]:
    """
    Get all teams a career has wrestled for by looking up season_wrestler_ids.
    
    Args:
        career: Career dictionary
        season_accomplishments: Dict mapping season -> list of wrestler records
        
    Returns:
        Set of team names
    """
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


def check_grade_progression(grade_2024: Optional[int], grade_2025: Optional[int]) -> bool:
    """
    Check if grade progression is plausible (2024 grade + 1 == 2025 grade).
    
    Returns True if:
    - Both grades exist and grade_2024 + 1 == grade_2025
    - Either grade is missing (can't verify, so allow)
    """
    if grade_2024 is None or grade_2025 is None:
        return True  # Can't verify, so allow
    
    return grade_2024 + 1 == grade_2025


def name_similarity(name1: str, name2: str) -> float:
    """Calculate name similarity score (0-1)."""
    return SequenceMatcher(None, normalize_name(name1), normalize_name(name2)).ratio()


def calculate_confidence_score(
    wrestler_2024: Dict,
    career: Dict,
    season_accomplishments: Dict[int, List[Dict]]
) -> Tuple[int, List[str]]:
    """
    Calculate confidence score (0-100) for linking wrestler to career.
    
    Returns:
        (score, reasons) tuple
    """
    score = 0
    reasons = []
    
    # Get career's 2025 wrestler data
    seasons = career.get('seasons', {})
    wrestler_2025_id = seasons.get('2025')
    
    wrestler_2025 = None
    if wrestler_2025_id and 2025 in season_accomplishments:
        for w in season_accomplishments[2025]:
            if w.get('season_wrestler_id') == wrestler_2025_id:
                wrestler_2025 = w
                break
    
    # Same team: +40
    team_2024 = normalize_team_name(wrestler_2024.get('team', ''))
    if wrestler_2025:
        team_2025 = normalize_team_name(wrestler_2025.get('team', ''))
        if team_2024 == team_2025:
            score += 40
            reasons.append("same_team")
        else:
            # Check if career has wrestled for this team before
            career_teams = get_career_teams(career, season_accomplishments)
            if any(normalize_team_name(t) == team_2024 for t in career_teams):
                score += 20
                reasons.append("team_in_history")
    else:
        # Can't verify team match
        reasons.append("no_2025_data")
    
    # Exact last-name match: +25
    name_2024 = wrestler_2024.get('name', '')
    name_2025 = career.get('canonical_name', '')
    
    name_2024_parts = normalize_name(name_2024).split()
    name_2025_parts = normalize_name(name_2025).split()
    
    if name_2024_parts and name_2025_parts:
        if name_2024_parts[-1] == name_2025_parts[-1]:  # Last names match
            score += 25
            reasons.append("exact_last_name")
    
    # Fuzzy full-name match: +20
    name_sim = name_similarity(name_2024, name_2025)
    if name_sim >= 0.95:
        score += 20
        reasons.append("exact_name_match")
    elif name_sim >= 0.85:
        score += 10
        reasons.append("fuzzy_name_match")
    
    # Plausible grade progression: +10
    if wrestler_2025:
        grade_2024 = wrestler_2024.get('grade')
        grade_2025 = wrestler_2025.get('grade')
        if check_grade_progression(grade_2024, grade_2025):
            score += 10
            reasons.append("plausible_grade")
    
    # Weight within ±2 classes: +5
    if wrestler_2025:
        weight_2024 = wrestler_2024.get('final_weight')
        weight_2025 = wrestler_2025.get('final_weight')
        if weight_2024 and weight_2025:
            weight_diff = abs(weight_2024 - weight_2025)
            if weight_diff <= 2:
                score += 5
                reasons.append("similar_weight")
    
    return (score, reasons)


def check_wrestler_already_linked(
    wrestler_2024_id: str,
    careers: Dict[str, Dict]
) -> Optional[str]:
    """
    Check if a 2024 wrestler is already linked to any career.
    
    Returns:
        career_id if already linked, None otherwise
    """
    for career_id, career in careers.items():
        seasons = career.get('seasons', {})
        if seasons.get('2024') == wrestler_2024_id:
            return career_id
    return None


def find_candidate_careers_optimized(
    wrestler_2024: Dict,
    careers: Dict[str, Dict],
    name_to_careers: Dict[str, List[str]],
    wrestler_lookup_2025: Dict[str, Dict],
    career_teams_cache: Dict[str, Set[str]],
    aliases: Dict[str, str]
) -> List[Tuple[str, Dict, int, List[str]]]:
    """
    Optimized version: Find candidate careers using pre-built lookups.
    
    Returns:
        List of (career_id, career, confidence_score, reasons) tuples, sorted by score descending
    """
    name_2024_norm = apply_name_alias(wrestler_2024.get('name', ''), aliases)
    team_2024_norm = normalize_team_name(wrestler_2024.get('team', ''))
    
    candidates = []
    
    # First, try exact name matches (most likely candidates)
    candidate_career_ids = set()
    if name_2024_norm in name_to_careers:
        candidate_career_ids.update(name_to_careers[name_2024_norm])
    
    # Also check fuzzy matches for similar names (last name match)
    name_parts = name_2024_norm.split()
    if len(name_parts) > 0:
        last_name = name_parts[-1]
        for name_norm, career_ids in name_to_careers.items():
            if name_norm.split()[-1] == last_name if name_norm.split() else False:
                candidate_career_ids.update(career_ids)
    
    # Limit to reasonable number of candidates (if too many, prioritize exact matches)
    if len(candidate_career_ids) > 50:
        # Too many candidates, only use exact name matches
        candidate_career_ids = set(name_to_careers.get(name_2024_norm, []))
    
    # Process candidate careers
    for career_id in candidate_career_ids:
        career = careers.get(career_id)
        if not career:
            continue
        
        # Skip if career already has this season linked
        career_seasons = get_career_seasons(career)
        if 2024 in career_seasons:
            continue
        
        # Only consider careers active within ±3 years of 2024
        if career_seasons:
            min_season = min(career_seasons)
            max_season = max(career_seasons)
            if min_season > 2027 or max_season < 2021:
                continue
        
        # Get 2025 wrestler data for comparison (using lookup)
        seasons = career.get('seasons', {})
        wrestler_2025_id = seasons.get('2025')
        wrestler_2025 = wrestler_lookup_2025.get(wrestler_2025_id) if wrestler_2025_id else None
        
        # Calculate confidence score (optimized version)
        score, reasons = calculate_confidence_score_optimized(
            wrestler_2024,
            career,
            wrestler_2025,
            career_teams_cache.get(career_id, set())
        )
        
        candidates.append((career_id, career, score, reasons))
    
    # Sort by score descending
    candidates.sort(key=lambda x: x[2], reverse=True)
    
    return candidates


def calculate_confidence_score_optimized(
    wrestler_2024: Dict,
    career: Dict,
    wrestler_2025: Optional[Dict],
    career_teams: Set[str]
) -> Tuple[int, List[str]]:
    """
    Optimized confidence score calculation using pre-loaded data.
    """
    score = 0
    reasons = []
    
    # Same team: +40
    team_2024_norm = normalize_team_name(wrestler_2024.get('team', ''))
    if wrestler_2025:
        team_2025_norm = normalize_team_name(wrestler_2025.get('team', ''))
        if team_2024_norm == team_2025_norm:
            score += 40
            reasons.append("same_team")
        elif any(normalize_team_name(t) == team_2024_norm for t in career_teams):
            score += 20
            reasons.append("team_in_history")
    else:
        if any(normalize_team_name(t) == team_2024_norm for t in career_teams):
            score += 20
            reasons.append("team_in_history")
        else:
            reasons.append("no_2025_data")
    
    # Exact last-name match: +25
    name_2024 = wrestler_2024.get('name', '')
    name_2025 = career.get('canonical_name', '')
    
    name_2024_parts = normalize_name(name_2024).split()
    name_2025_parts = normalize_name(name_2025).split()
    
    if name_2024_parts and name_2025_parts:
        if name_2024_parts[-1] == name_2025_parts[-1]:  # Last names match
            score += 25
            reasons.append("exact_last_name")
    
    # Fuzzy full-name match: +20
    name_sim = name_similarity(name_2024, name_2025)
    if name_sim >= 0.95:
        score += 20
        reasons.append("exact_name_match")
    elif name_sim >= 0.85:
        score += 10
        reasons.append("fuzzy_name_match")
    
    # Plausible grade progression: +10
    if wrestler_2025:
        grade_2024 = wrestler_2024.get('grade')
        grade_2025 = wrestler_2025.get('grade')
        if check_grade_progression(grade_2024, grade_2025):
            score += 10
            reasons.append("plausible_grade")
    
    # Weight within ±2 classes: +5
    if wrestler_2025:
        weight_2024 = wrestler_2024.get('final_weight')
        weight_2025 = wrestler_2025.get('final_weight')
        if weight_2024 and weight_2025:
            weight_diff = abs(weight_2024 - weight_2025)
            if weight_diff <= 2:
                score += 5
                reasons.append("similar_weight")
    
    return (score, reasons)


def find_candidate_careers(
    wrestler_2024: Dict,
    careers: Dict[str, Dict],
    season_accomplishments: Dict[int, List[Dict]],
    aliases: Dict[str, str]
) -> List[Tuple[str, Dict, int, List[str]]]:
    """
    Legacy version - kept for compatibility but not used.
    Use find_candidate_careers_optimized instead.
    """
    # This function is kept for reference but should not be called
    raise NotImplementedError("Use find_candidate_careers_optimized instead")


def auto_link_rule_a_optimized(
    wrestler_2024: Dict,
    career: Dict,
    wrestler_2025: Optional[Dict],
    career_teams: Set[str],
    aliases: Dict[str, str]
) -> bool:
    """
    Optimized version of Rule A using pre-loaded data.
    
    AUTO-LINK RULE A (Gold Standard)
    
    Link automatically if ALL are true:
    - name_norm matches exactly
    - team matches exactly
    - grade_2024 + 1 == grade_2025 OR grade missing on either side
    - career does not already have a 2024 season
    """
    # Check if already linked
    if 2024 in get_career_seasons(career):
        return False
    
    # Check name match
    name_2024_norm = apply_name_alias(wrestler_2024.get('name', ''), aliases)
    name_career_norm = career.get('name_norm', '')
    
    if name_2024_norm != name_career_norm:
        return False
    
    # Check team match - check 2025 team OR any team in career history
    team_2024_norm = normalize_team_name(wrestler_2024.get('team', ''))
    
    team_match = False
    
    # Check 2025 team
    if wrestler_2025:
        team_2025_norm = normalize_team_name(wrestler_2025.get('team', ''))
        if team_2024_norm == team_2025_norm:
            team_match = True
    
    # If not matched on 2025 team, check career history
    if not team_match:
        if any(normalize_team_name(t) == team_2024_norm for t in career_teams):
            team_match = True
    
    if not team_match:
        return False
    
    # Check grade progression
    grade_2024 = wrestler_2024.get('grade')
    
    if wrestler_2025:
        grade_2025 = wrestler_2025.get('grade')
        if not check_grade_progression(grade_2024, grade_2025):
            return False
    
    return True


def auto_link_rule_a(
    wrestler_2024: Dict,
    career: Dict,
    season_accomplishments: Dict[int, List[Dict]],
    aliases: Dict[str, str]
) -> bool:
    """
    AUTO-LINK RULE A (Gold Standard)
    
    Link automatically if ALL are true:
    - name_norm matches exactly
    - team matches exactly
    - grade_2024 + 1 == grade_2025 OR grade missing on either side
    - career does not already have a 2024 season
    """
    # Check if already linked
    if 2024 in get_career_seasons(career):
        return False
    
    # Check name match
    name_2024_norm = apply_name_alias(wrestler_2024.get('name', ''), aliases)
    name_career_norm = career.get('name_norm', '')
    
    if name_2024_norm != name_career_norm:
        return False
    
    # Check team match - check 2025 team OR any team in career history
    team_2024_norm = normalize_team_name(wrestler_2024.get('team', ''))
    
    # Get 2025 wrestler to check team
    seasons = career.get('seasons', {})
    wrestler_2025_id = seasons.get('2025')
    
    team_match = False
    
    # Check 2025 team
    if wrestler_2025_id and 2025 in season_accomplishments:
        for w in season_accomplishments[2025]:
            if w.get('season_wrestler_id') == wrestler_2025_id:
                team_2025_norm = normalize_team_name(w.get('team', ''))
                if team_2024_norm == team_2025_norm:
                    team_match = True
                break
    
    # If not matched on 2025 team, check career history
    if not team_match:
        career_teams = get_career_teams(career, season_accomplishments)
        if any(normalize_team_name(t) == team_2024_norm for t in career_teams):
            team_match = True
    
    if not team_match:
        return False
    
    # Check grade progression
    grade_2024 = wrestler_2024.get('grade')
    
    if wrestler_2025_id and 2025 in season_accomplishments:
        for w in season_accomplishments[2025]:
            if w.get('season_wrestler_id') == wrestler_2025_id:
                grade_2025 = w.get('grade')
                if not check_grade_progression(grade_2024, grade_2025):
                    return False
                break
    
    return True


def auto_link_rule_b_optimized(
    wrestler_2024: Dict,
    career: Dict,
    wrestler_2025: Optional[Dict],
    career_teams: Set[str],
    aliases: Dict[str, str]
) -> bool:
    """
    Optimized version of Rule B using pre-loaded data.
    """
    # Check if already linked
    if 2024 in get_career_seasons(career):
        return False
    
    # Check name match
    name_2024_norm = apply_name_alias(wrestler_2024.get('name', ''), aliases)
    name_career_norm = career.get('name_norm', '')
    
    if name_2024_norm != name_career_norm:
        return False
    
    # Check team match - check 2025 team OR any team in career history
    team_2024_norm = normalize_team_name(wrestler_2024.get('team', ''))
    
    team_match = False
    
    # Check 2025 team
    if wrestler_2025:
        team_2025_norm = normalize_team_name(wrestler_2025.get('team', ''))
        if team_2024_norm == team_2025_norm:
            team_match = True
    
    # If not matched on 2025 team, check career history
    if not team_match:
        if any(normalize_team_name(t) == team_2024_norm for t in career_teams):
            team_match = True
    
    if not team_match:
        return False
    
    # Check seasons are within ±3 years
    career_seasons = get_career_seasons(career)
    if career_seasons:
        min_season = min(career_seasons)
        max_season = max(career_seasons)
        if min_season > 2027 or max_season < 2021:
            return False
    
    return True


def auto_link_rule_b(
    wrestler_2024: Dict,
    career: Dict,
    season_accomplishments: Dict[int, List[Dict]],
    aliases: Dict[str, str]
) -> bool:
    """
    AUTO-LINK RULE B (Grade is unreliable)
    
    Link automatically if:
    - name_norm matches exactly
    - team matches exactly (2025 team OR any team in career history)
    - seasons are within ±3 years
    - no conflicting season already linked
    """
    # Check if already linked
    if 2024 in get_career_seasons(career):
        return False
    
    # Check name match
    name_2024_norm = apply_name_alias(wrestler_2024.get('name', ''), aliases)
    name_career_norm = career.get('name_norm', '')
    
    if name_2024_norm != name_career_norm:
        return False
    
    # Check team match - check 2025 team OR any team in career history
    team_2024_norm = normalize_team_name(wrestler_2024.get('team', ''))
    
    # Get 2025 wrestler to check team
    seasons = career.get('seasons', {})
    wrestler_2025_id = seasons.get('2025')
    
    team_match = False
    
    # Check 2025 team
    if wrestler_2025_id and 2025 in season_accomplishments:
        for w in season_accomplishments[2025]:
            if w.get('season_wrestler_id') == wrestler_2025_id:
                team_2025_norm = normalize_team_name(w.get('team', ''))
                if team_2024_norm == team_2025_norm:
                    team_match = True
                break
    
    # If not matched on 2025 team, check career history
    if not team_match:
        career_teams = get_career_teams(career, season_accomplishments)
        if any(normalize_team_name(t) == team_2024_norm for t in career_teams):
            team_match = True
    
    if not team_match:
        return False
    
    # Check seasons are within ±3 years
    career_seasons = get_career_seasons(career)
    if career_seasons:
        min_season = min(career_seasons)
        max_season = max(career_seasons)
        if min_season > 2027 or max_season < 2021:
            return False
    
    return True


def should_auto_create_career(
    wrestler_2024: Dict,
    candidates: List[Tuple[str, Dict, int, List[str]]],
    aliases: Dict[str, str]
) -> bool:
    """
    AUTO-CREATE CAREER RULE
    
    Create a NEW career automatically if:
    - grade == 7
    - no strong name match exists on the same team
    - no existing career already linked
    """
    grade_2024 = wrestler_2024.get('grade')
    if grade_2024 != 7:
        return False
    
    # Check if there's a strong match (score >= 80) on the same team
    team_2024_norm = normalize_team_name(wrestler_2024.get('team', ''))
    
    for career_id, career, score, reasons in candidates:
        if score >= 80:
            # Check if same team
            # We'd need to check the career's teams, but for auto-create,
            # if there's a strong match, don't auto-create
            return False
    
    return True


def link_season_to_careers(
    season: int,
    anchor_season: int,
    gender: str
) -> Dict:
    """
    Main linking logic.
    
    Returns:
        Dictionary with results: auto_linked, auto_created, review_queue, errors
    """
    print(f"\n{'='*60}")
    print(f"LINKING SEASON {season} TO CAREERS")
    print(f"{'='*60}")
    print(f"Anchor season: {anchor_season}")
    print(f"Gender: {gender}")
    print(f"{'='*60}\n")
    
    global _CAREERS_DIR
    _CAREERS_DIR = Path("data/careers") if gender == "boys" else Path("data/careers/girls")

    # Load data
    print("Loading data...")
    careers_dir = _CAREERS_DIR
    careers = load_careers(careers_dir)
    print(f"Loaded {len(careers)} careers")
    
    # Load season accomplishments for both seasons
    season_accomplishments = {
        2024: load_season_accomplishments(2024, gender),
        2025: load_season_accomplishments(2025, gender)
    }
    print(f"Loaded {len(season_accomplishments[2024])} wrestlers from 2024")
    print(f"Loaded {len(season_accomplishments[2025])} wrestlers from 2025")
    
    # Load name aliases
    aliases = load_name_aliases()
    print(f"Loaded {len(aliases)} name aliases")
    
    # Process each 2024 wrestler
    results = {
        'auto_linked': [],
        'auto_created': [],
        'review_queue': [],
        'errors': [],
        'already_linked': []
    }
    
    # Pre-build lookup structures for performance
    print("\nBuilding lookup structures...")
    
    # Build name_norm -> careers lookup
    name_to_careers = defaultdict(list)
    for career_id, career in careers.items():
        name_norm = career.get('name_norm', '')
        if name_norm:
            name_to_careers[name_norm].append(career_id)
    
    # Build season_wrestler_id -> wrestler lookup
    wrestler_lookup_2024 = {w.get('season_wrestler_id'): w for w in season_accomplishments[2024]}
    wrestler_lookup_2025 = {w.get('season_wrestler_id'): w for w in season_accomplishments[2025]}
    
    # Pre-build career teams cache
    print("Caching career team data...")
    career_teams_cache = {}
    for career_id, career in careers.items():
        career_teams_cache[career_id] = get_career_teams(career, {
            2024: season_accomplishments[2024],
            2025: season_accomplishments[2025]
        })
    
    # Pre-build already linked lookup
    already_linked_lookup = {}
    for career_id, career in careers.items():
        seasons = career.get('seasons', {})
        if '2024' in seasons:
            already_linked_lookup[seasons['2024']] = career_id
    
    print(f"Built lookups: {len(name_to_careers)} name mappings, {len(career_teams_cache)} career caches")
    
    print(f"\nProcessing {len(season_accomplishments[2024])} wrestlers from 2024...")
    
    processed = 0
    for wrestler_2024 in season_accomplishments[2024]:
        processed += 1
        if processed % 100 == 0:
            print(f"  Processed {processed}/{len(season_accomplishments[2024])} wrestlers...")
        wrestler_id_2024 = wrestler_2024.get('season_wrestler_id')
        
        # Check if already linked (using pre-built lookup)
        if wrestler_id_2024 in already_linked_lookup:
            existing_career_id = already_linked_lookup[wrestler_id_2024]
            results['already_linked'].append({
                'wrestler_2024': {
                    'name': wrestler_2024.get('name'),
                    'season_wrestler_id': wrestler_id_2024
                },
                'career_id': existing_career_id
            })
            continue
        wrestler_id_2024 = wrestler_2024.get('season_wrestler_id')
        name_2024 = wrestler_2024.get('name', '')
        
        if not wrestler_id_2024 or not name_2024:
            results['errors'].append({
                'wrestler': name_2024,
                'reason': 'missing_id_or_name'
            })
            continue
        
        # Find candidate careers (optimized with pre-built lookups)
        candidates = find_candidate_careers_optimized(
            wrestler_2024,
            careers,
            name_to_careers,
            wrestler_lookup_2025,
            career_teams_cache,
            aliases
        )
        
        # Try auto-link Rule A (Gold Standard)
        auto_linked = False
        for career_id, career, score, reasons in candidates:
            wrestler_2025 = wrestler_lookup_2025.get(career.get('seasons', {}).get('2025', ''))
            if auto_link_rule_a_optimized(wrestler_2024, career, wrestler_2025, career_teams_cache.get(career_id, set()), aliases):
                results['auto_linked'].append({
                    'wrestler_2024': {
                        'name': name_2024,
                        'season_wrestler_id': wrestler_id_2024,
                        'team': wrestler_2024.get('team'),
                        'grade': wrestler_2024.get('grade')
                    },
                    'career_id': career_id,
                    'rule': 'A',
                    'confidence': 100
                })
                auto_linked = True
                break
        
        if auto_linked:
            continue
        
        # Try auto-link Rule B
        for career_id, career, score, reasons in candidates:
            wrestler_2025 = wrestler_lookup_2025.get(career.get('seasons', {}).get('2025', ''))
            if auto_link_rule_b_optimized(wrestler_2024, career, wrestler_2025, career_teams_cache.get(career_id, set()), aliases):
                results['auto_linked'].append({
                    'wrestler_2024': {
                        'name': name_2024,
                        'season_wrestler_id': wrestler_id_2024,
                        'team': wrestler_2024.get('team'),
                        'grade': wrestler_2024.get('grade')
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
                # Auto-link with high confidence
                results['auto_linked'].append({
                    'wrestler_2024': {
                        'name': name_2024,
                        'season_wrestler_id': wrestler_id_2024,
                        'team': wrestler_2024.get('team'),
                        'grade': wrestler_2024.get('grade')
                    },
                    'career_id': career_id,
                    'rule': 'confidence_score',
                    'confidence': score,
                    'reasons': reasons
                })
                continue
            
            elif score >= 50:
                # Queue for review
                # Get top 3 candidates
                top_candidates = []
                for cid, c, s, r in candidates[:3]:
                    # Get career teams from cache
                    career_teams = career_teams_cache.get(cid, set())
                    top_candidates.append({
                        'career_id': cid,
                        'canonical_name': c.get('canonical_name'),
                        'teams': list(career_teams),
                        'seasons': list(get_career_seasons(c)),
                        'confidence': s,
                        'reasons': r
                    })
                
                results['review_queue'].append({
                    'wrestler_2024': {
                        'name': name_2024,
                        'season_wrestler_id': wrestler_id_2024,
                        'team': wrestler_2024.get('team'),
                        'grade': wrestler_2024.get('grade'),
                        'final_weight': wrestler_2024.get('final_weight')
                    },
                    'candidates': top_candidates,
                    'confidence': score,
                    'reasons': reasons
                })
                continue
        
        # Check if should auto-create new career
        grade_2024 = wrestler_2024.get('grade')
        
        # Check if there are ANY decent matches (score >= 50)
        has_decent_match = candidates and candidates[0][2] >= 50
        
        if grade_2024 == 12 and not has_decent_match:
            # Grade 12 with no good matches - auto-create (senior year, last season)
            results['auto_created'].append({
                'wrestler_2024': {
                    'name': name_2024,
                    'season_wrestler_id': wrestler_id_2024,
                    'team': wrestler_2024.get('team'),
                    'grade': wrestler_2024.get('grade')
                },
                'reason': 'grade_12_no_match',
                'best_match_score': candidates[0][2] if candidates else 0
            })
        elif should_auto_create_career(wrestler_2024, candidates, aliases):
            # Grade 7 with no strong match
            results['auto_created'].append({
                'wrestler_2024': {
                    'name': name_2024,
                    'season_wrestler_id': wrestler_id_2024,
                    'team': wrestler_2024.get('team'),
                    'grade': wrestler_2024.get('grade')
                },
                'reason': 'grade_7_no_match'
            })
        elif not has_decent_match:
            # No good matches - needs review (not auto-created)
            results['auto_created'].append({
                'wrestler_2024': {
                    'name': name_2024,
                    'season_wrestler_id': wrestler_id_2024,
                    'team': wrestler_2024.get('team'),
                    'grade': wrestler_2024.get('grade')
                },
                'reason': 'no_match_found',
                'best_match_score': candidates[0][2] if candidates else 0
            })
    
    return results


def apply_links_phase(
    links: List[Dict],
    careers: Dict[str, Dict],
    phase_name: str
) -> int:
    """
    Apply links for a specific phase.
    
    Returns:
        Number of links applied
    """
    links_applied = 0
    
    print(f"\nApplying {len(links)} links from {phase_name}...")
    for link in links:
        career_id = link['career_id']
        wrestler_2024_id = link['wrestler_2024']['season_wrestler_id']
        
        if career_id in careers:
            career = careers[career_id]
            seasons = career.get('seasons', {})
            
            # Check if already linked (idempotency)
            if '2024' in seasons:
                continue
            
            # Add 2024 season
            seasons['2024'] = wrestler_2024_id
            career['seasons'] = seasons
            
            # Save career file
            career_file = _CAREERS_DIR / f"{career_id}.json"
            with open(career_file, 'w', encoding='utf-8') as f:
                json.dump(career, f, indent=2, ensure_ascii=False)
            
            links_applied += 1
    
    return links_applied


def create_careers_phase(
    new_careers: List[Dict],
    careers: Dict[str, Dict],
    anchor_season: int
) -> int:
    """
    Create new careers for a specific phase.
    
    Returns:
        Number of careers created
    """
    careers_created = 0
    
    # Find max career ID to generate new ones
    careers_dir = _CAREERS_DIR
    max_career_num = 0
    for career_file in careers_dir.glob("career_*.json"):
        career_id = career_file.stem
        if career_id.startswith('career_'):
            try:
                num = int(career_id.replace('career_', ''))
                max_career_num = max(max_career_num, num)
            except ValueError:
                pass
    
    print(f"\nCreating {len(new_careers)} new careers...")
    for new_career_info in new_careers:
        wrestler_2024 = new_career_info['wrestler_2024']
        name_2024 = wrestler_2024['name']
        wrestler_id_2024 = wrestler_2024['season_wrestler_id']
        
        # Generate new career ID
        max_career_num += 1
        career_id = f"career_{max_career_num:06d}"
        
        # Create career
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
        
        # Save career file
        career_file = _CAREERS_DIR / f"{career_id}.json"
        with open(career_file, 'w', encoding='utf-8') as f:
            json.dump(career, f, indent=2, ensure_ascii=False)
        
        careers[career_id] = career
        careers_created += 1
    
    return careers_created


def apply_links(
    results: Dict,
    careers: Dict[str, Dict],
    season_accomplishments: Dict[int, List[Dict]],
    anchor_season: int
) -> Tuple[int, int]:
    """
    Legacy function - kept for compatibility.
    Use apply_links_phase and create_careers_phase instead.
    """
    # Separate by phase
    rule_a_links = [l for l in results['auto_linked'] if l.get('rule') == 'A']
    rule_b_links = [l for l in results['auto_linked'] if l.get('rule') == 'B']
    confidence_links = [l for l in results['auto_linked'] if l.get('rule') == 'confidence_score']
    
    links_applied = 0
    links_applied += apply_links_phase(rule_a_links, careers, "Rule A")
    links_applied += apply_links_phase(rule_b_links, careers, "Rule B")
    links_applied += apply_links_phase(confidence_links, careers, "High Confidence")
    
    careers_created = create_careers_phase(results['auto_created'], careers, anchor_season)
    
    return (links_applied, careers_created)


def print_detailed_summary(results: Dict, season: int, anchor_season: int, gender: str):
    """Print a detailed breakdown of linking results."""
    print(f"\n{'='*70}")
    print("DETAILED LINKING SUMMARY")
    print(f"{'='*70}")
    
    # Already linked
    print(f"\n📋 ALREADY LINKED: {len(results['already_linked'])}")
    if results['already_linked']:
        print("   (These wrestlers were already linked in a previous run)")
    
    # Separate auto-linked by phase
    auto_linked = results['auto_linked']
    rule_a_links = [l for l in auto_linked if l.get('rule') == 'A']
    rule_b_links = [l for l in auto_linked if l.get('rule') == 'B']
    confidence_links = [l for l in auto_linked if l.get('rule') == 'confidence_score']
    
    # Separate auto_created by reason
    grade_12_auto = [nc for nc in results['auto_created'] if nc.get('reason') == 'grade_12_no_match']
    other_new_careers = [nc for nc in results['auto_created'] if nc.get('reason') != 'grade_12_no_match']
    
    print(f"\n✅ AUTO-LINKED: {len(auto_linked)}")
    
    if auto_linked:
        print("\n   Breakdown by Phase:")
        print(f"     • Phase 1 - Rule A (Gold Standard): {len(rule_a_links)}")
        print(f"       - Exact name + exact team + grade progression")
        print(f"     • Phase 2 - Rule B: {len(rule_b_links)}")
        print(f"       - Exact name + exact team (grade unreliable)")
        print(f"     • Phase 3 - High Confidence (≥80): {len(confidence_links)}")
        print(f"       - High confidence score matches")
        print(f"     • Phase 4 - Grade 12 Auto-Create: {len(grade_12_auto)}")
        print(f"       - Grade 12 with no good matches (senior year)")
        print(f"     • Phase 5 - New Careers (Review): {len(other_new_careers)}")
        print(f"       - Other cases needing review")
        
        if confidence_links:
            confidence_ranges = defaultdict(int)
            for link in confidence_links:
                confidence = link.get('confidence', 0)
                if confidence >= 95:
                    confidence_ranges['95-100'] += 1
                elif confidence >= 80:
                    confidence_ranges['80-94'] += 1
            
            print("\n   Phase 3 Confidence Breakdown:")
            for range_name, count in sorted(confidence_ranges.items(), reverse=True):
                print(f"     • {range_name}: {count}")
    
    # Auto-created breakdown
    auto_created = results['auto_created']
    print(f"\n🆕 AUTO-CREATED (New Careers): {len(auto_created)}")
    
    if auto_created:
        reason_counts = defaultdict(int)
        grade_counts = defaultdict(int)
        
        for created in auto_created:
            reason = created.get('reason', 'unknown')
            reason_counts[reason] += 1
            
            grade = created['wrestler_2024'].get('grade')
            if grade:
                grade_counts[grade] += 1
        
        print("\n   Breakdown by Reason:")
        for reason, count in sorted(reason_counts.items()):
            reason_name = {
                'grade_7_no_match': 'Grade 7 with no strong match',
                'no_match_found': 'No match found (<50 confidence)'
            }.get(reason, reason)
            print(f"     • {reason_name}: {count}")
        
        if grade_counts:
            print("\n   Breakdown by Grade:")
            for grade, count in sorted(grade_counts.items()):
                print(f"     • Grade {grade}: {count}")
    
    # Review queue breakdown
    review_queue = results['review_queue']
    print(f"\n⚠️  REVIEW QUEUE (Manual Review Needed): {len(review_queue)}")
    
    if review_queue:
        confidence_ranges = defaultdict(int)
        
        for review in review_queue:
            confidence = review.get('confidence', 0)
            if confidence >= 70:
                confidence_ranges['70-79'] += 1
            elif confidence >= 60:
                confidence_ranges['60-69'] += 1
            else:
                confidence_ranges['50-59'] += 1
        
        print("\n   Breakdown by Confidence Score:")
        for range_name, count in sorted(confidence_ranges.items(), reverse=True):
            print(f"     • {range_name}: {count}")
        
        # Show sample of review cases
        print("\n   Sample Review Cases (first 5):")
        for i, review in enumerate(review_queue[:5], 1):
            wrestler = review['wrestler_2024']
            best_candidate = review['candidates'][0] if review['candidates'] else None
            print(f"\n     {i}. {wrestler['name']} ({wrestler['team']}, Grade {wrestler.get('grade', '?')})")
            print(f"        Confidence: {review['confidence']}")
            print(f"        Reasons: {', '.join(review.get('reasons', []))}")
            if best_candidate:
                print(f"        Best Match: {best_candidate['canonical_name']} ({best_candidate['career_id']})")
                print(f"        Match Confidence: {best_candidate['confidence']}")
    
    # Errors
    errors = results['errors']
    if errors:
        print(f"\n❌ ERRORS: {len(errors)}")
        for error in errors[:5]:
            print(f"     • {error.get('wrestler', 'Unknown')}: {error.get('reason', 'Unknown error')}")
    
    # Totals
    total_processed = (
        len(results['already_linked']) +
        len(results['auto_linked']) +
        len(results['auto_created']) +
        len(results['review_queue']) +
        len(results['errors'])
    )
    
    print(f"\n{'='*70}")
    print("TOTALS")
    print(f"{'='*70}")
    print(f"Total 2024 wrestlers processed: {total_processed}")
    print(f"  • Already linked: {len(results['already_linked'])}")
    print(f"  • Auto-linked: {len(results['auto_linked'])}")
    print(f"  • Auto-created: {len(results['auto_created'])}")
    print(f"  • Needs review: {len(results['review_queue'])}")
    print(f"  • Errors: {len(results['errors'])}")
    print(f"{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(
        description='Link a season into existing careers'
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
        help='Anchor season used to create careers (default: 2025)'
    )
    parser.add_argument(
        '--gender',
        type=str,
        required=True,
        choices=['boys', 'girls'],
        help='Gender (boys or girls)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run without applying changes (for testing)'
    )
    parser.add_argument(
        '--interactive',
        action='store_true',
        help='Show detailed summary and ask for confirmation before applying'
    )
    parser.add_argument(
        '--phase',
        type=str,
        choices=['1', '2', '3', '4', '5', 'all'],
        default='all',
        help='Which phase to apply: 1=Rule A, 2=Rule B, 3=High Confidence, 4=Grade 12 Auto, 5=New Careers, all=all phases'
    )
    parser.add_argument(
        '--apply-only',
        action='store_true',
        help='Skip analysis, only apply previously saved results'
    )
    
    args = parser.parse_args()
    
    # Run linking logic
    results = link_season_to_careers(
        args.season,
        args.anchor_season,
        args.gender
    )
    
    # Print detailed summary
    print_detailed_summary(results, args.season, args.anchor_season, args.gender)
    
    # Save logs
    log_dir = Path("data/career_linking_logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Separate results by phase
    rule_a_links = [l for l in results['auto_linked'] if l.get('rule') == 'A']
    rule_b_links = [l for l in results['auto_linked'] if l.get('rule') == 'B']
    confidence_links = [l for l in results['auto_linked'] if l.get('rule') == 'confidence_score']
    
    # Save phase-specific files
    phase1_file = log_dir / f"{args.season}_phase1_rule_a.json"
    with open(phase1_file, 'w', encoding='utf-8') as f:
        json.dump({
            'season': args.season,
            'anchor_season': args.anchor_season,
            'gender': args.gender,
            'phase': 'Rule A (Gold Standard)',
            'links': rule_a_links
        }, f, indent=2, ensure_ascii=False)
    print(f"✅ Saved Phase 1 (Rule A): {phase1_file}")
    
    phase2_file = log_dir / f"{args.season}_phase2_rule_b.json"
    with open(phase2_file, 'w', encoding='utf-8') as f:
        json.dump({
            'season': args.season,
            'anchor_season': args.anchor_season,
            'gender': args.gender,
            'phase': 'Rule B',
            'links': rule_b_links
        }, f, indent=2, ensure_ascii=False)
    print(f"✅ Saved Phase 2 (Rule B): {phase2_file}")
    
    phase3_file = log_dir / f"{args.season}_phase3_high_confidence.json"
    with open(phase3_file, 'w', encoding='utf-8') as f:
        json.dump({
            'season': args.season,
            'anchor_season': args.anchor_season,
            'gender': args.gender,
            'phase': 'High Confidence (≥80)',
            'links': confidence_links
        }, f, indent=2, ensure_ascii=False)
    print(f"✅ Saved Phase 3 (High Confidence): {phase3_file}")
    
    phase4_file = log_dir / f"{args.season}_phase4_new_careers.json"
    with open(phase4_file, 'w', encoding='utf-8') as f:
        json.dump({
            'season': args.season,
            'anchor_season': args.anchor_season,
            'gender': args.gender,
            'phase': 'New Careers (Review Before Creating)',
            'new_careers': results['auto_created']
        }, f, indent=2, ensure_ascii=False)
    print(f"✅ Saved Phase 4 (New Careers): {phase4_file}")
    
    # Save review log
    review_file = log_dir / f"{args.season}_link_review.json"
    with open(review_file, 'w', encoding='utf-8') as f:
        json.dump({
            'season': args.season,
            'anchor_season': args.anchor_season,
            'gender': args.gender,
            'review_queue': results['review_queue']
        }, f, indent=2, ensure_ascii=False)
    print(f"✅ Saved review log: {review_file}")
    
    # Save complete results log
    results_file = log_dir / f"{args.season}_link_results.json"
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump({
            'season': args.season,
            'anchor_season': args.anchor_season,
            'gender': args.gender,
            'auto_linked': results['auto_linked'],
            'auto_created': results['auto_created'],
            'review_queue_count': len(results['review_queue']),
            'errors': results['errors']
        }, f, indent=2, ensure_ascii=False)
    print(f"✅ Saved complete results log: {results_file}")
    
    # Apply changes by phase
    if args.apply_only:
        # Load from saved phase files
        log_dir = Path("data/career_linking_logs")
        
        if args.phase in ['1', 'all']:
            phase1_file = log_dir / f"{args.season}_phase1_rule_a.json"
            if phase1_file.exists():
                with open(phase1_file, 'r') as f:
                    phase1_data = json.load(f)
                rule_a_links = phase1_data.get('links', [])
            else:
                rule_a_links = []
        
        if args.phase in ['2', 'all']:
            phase2_file = log_dir / f"{args.season}_phase2_rule_b.json"
            if phase2_file.exists():
                with open(phase2_file, 'r') as f:
                    phase2_data = json.load(f)
                rule_b_links = phase2_data.get('links', [])
            else:
                rule_b_links = []
        
        if args.phase in ['3', 'all']:
            phase3_file = log_dir / f"{args.season}_phase3_high_confidence.json"
            if phase3_file.exists():
                with open(phase3_file, 'r') as f:
                    phase3_data = json.load(f)
                confidence_links = phase3_data.get('links', [])
            else:
                confidence_links = []
        
        if args.phase in ['4', 'all']:
            phase4_file = log_dir / f"{args.season}_phase4_grade_12_auto.json"
            if phase4_file.exists():
                with open(phase4_file, 'r') as f:
                    phase4_data = json.load(f)
                grade_12_auto = phase4_data.get('new_careers', [])
            else:
                grade_12_auto = []
        
        if args.phase in ['5', 'all']:
            phase5_file = log_dir / f"{args.season}_phase5_new_careers.json"
            if phase5_file.exists():
                with open(phase5_file, 'r') as f:
                    phase5_data = json.load(f)
                other_new_careers = phase5_data.get('new_careers', [])
            else:
                other_new_careers = []
    else:
        # Use current results
        rule_a_links = [l for l in results['auto_linked'] if l.get('rule') == 'A']
        rule_b_links = [l for l in results['auto_linked'] if l.get('rule') == 'B']
        confidence_links = [l for l in results['auto_linked'] if l.get('rule') == 'confidence_score']
        new_careers = results['auto_created']
    
    # Interactive mode: ask for confirmation by phase
    if args.interactive and not args.dry_run:
        print("\n" + "="*70)
        print("PHASED APPLICATION")
        print("="*70)
        
        total_applied = 0
        
        # Phase 1: Rule A (Gold Standard)
        if args.phase in ['1', 'all'] and rule_a_links:
            print(f"\n📋 Phase 1 - Rule A (Gold Standard): {len(rule_a_links)} links")
            print("   These are the highest confidence matches.")
            response = input("   Apply Phase 1? (yes/no): ").strip().lower()
            if response == 'yes':
                careers = load_careers(_CAREERS_DIR)
                applied = apply_links_phase(rule_a_links, careers, "Phase 1 (Rule A)")
                total_applied += applied
                print(f"   ✅ Applied {applied} links")
            else:
                print("   ⏭️  Skipped Phase 1")
        
        # Phase 2: Rule B
        if args.phase in ['2', 'all'] and rule_b_links:
            print(f"\n📋 Phase 2 - Rule B: {len(rule_b_links)} links")
            print("   Exact name + exact team (grade unreliable).")
            response = input("   Apply Phase 2? (yes/no): ").strip().lower()
            if response == 'yes':
                careers = load_careers(_CAREERS_DIR)
                applied = apply_links_phase(rule_b_links, careers, "Phase 2 (Rule B)")
                total_applied += applied
                print(f"   ✅ Applied {applied} links")
            else:
                print("   ⏭️  Skipped Phase 2")
        
        # Phase 3: High Confidence
        if args.phase in ['3', 'all'] and confidence_links:
            print(f"\n📋 Phase 3 - High Confidence (≥80): {len(confidence_links)} links")
            print("   High confidence score matches.")
            response = input("   Apply Phase 3? (yes/no): ").strip().lower()
            if response == 'yes':
                careers = load_careers(_CAREERS_DIR)
                applied = apply_links_phase(confidence_links, careers, "Phase 3 (High Confidence)")
                total_applied += applied
                print(f"   ✅ Applied {applied} links")
            else:
                print("   ⏭️  Skipped Phase 3")
        
        # Phase 4: Grade 12 Auto-Create
        if args.phase in ['4', 'all'] and grade_12_auto:
            print(f"\n📋 Phase 4 - Grade 12 Auto-Create: {len(grade_12_auto)} candidates")
            print("   These are Grade 12 wrestlers with no good matches (senior year).")
            print("   They will be automatically created as new careers.")
            response = input("   Create these careers? (yes/no): ").strip().lower()
            if response == 'yes':
                careers = load_careers(_CAREERS_DIR)
                created = create_careers_phase(grade_12_auto, careers, args.anchor_season)
                total_applied += created
                print(f"   ✅ Created {created} new careers")
            else:
                print("   ⏭️  Skipped Phase 4 (no careers created)")
        
        # Phase 5: New Careers (requires explicit review)
        if args.phase in ['5', 'all'] and other_new_careers:
            print(f"\n📋 Phase 5 - New Careers: {len(other_new_careers)} candidates")
            print("   ⚠️  WARNING: These will create NEW career files.")
            print("   Review the saved file before creating:")
            print(f"   {log_dir / f'{args.season}_phase5_new_careers.json'}")
            response = input("   Create new careers? (yes/no): ").strip().lower()
            if response == 'yes':
                careers = load_careers(_CAREERS_DIR)
                created = create_careers_phase(other_new_careers, careers, args.anchor_season)
                total_applied += created
                print(f"   ✅ Created {created} new careers")
            else:
                print("   ⏭️  Skipped Phase 5 (no careers created)")
        
        print(f"\n✅ Total applied/created: {total_applied}")
        
    elif not args.dry_run:
        # Non-interactive: apply based on phase flag
        careers = load_careers(_CAREERS_DIR)
        total_applied = 0
        
        if args.phase in ['1', 'all']:
            total_applied += apply_links_phase(rule_a_links, careers, "Phase 1 (Rule A)")
        if args.phase in ['2', 'all']:
            total_applied += apply_links_phase(rule_b_links, careers, "Phase 2 (Rule B)")
        if args.phase in ['3', 'all']:
            total_applied += apply_links_phase(confidence_links, careers, "Phase 3 (High Confidence)")
        if args.phase in ['4', 'all']:
            total_applied += create_careers_phase(new_careers, careers, args.anchor_season)
        
        print(f"\n✅ Total applied/created: {total_applied}")
    else:
        print("\n⚠️  DRY RUN: No changes applied")
    
    return 0


if __name__ == '__main__':
    exit(main())

