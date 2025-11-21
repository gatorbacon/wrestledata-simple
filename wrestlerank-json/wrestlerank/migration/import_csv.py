"""
CSV data migration utility for WrestleRank.

This module provides functions to import data from the legacy CSV-based system
into the new database structure.
"""

import csv
import os
import datetime
from tqdm import tqdm
from wrestlerank.db import sqlite_db

def parse_date(date_string):
    """Parse date from various formats."""
    formats = ['%m/%d/%Y', '%Y-%m-%d', '%m-%d-%Y']
    for fmt in formats:
        try:
            return datetime.datetime.strptime(date_string, fmt).date()
        except ValueError:
            continue
    # Return current date if parsing fails
    print(f"Warning: Could not parse date '{date_string}', using today's date")
    return datetime.date.today()

def import_teams(csv_path):
    """
    Import teams from CSV file.
    
    Args:
        csv_path: Path to the teams CSV file
        
    Returns:
        dict: Mapping of team names to team IDs
    """
    print(f"Importing teams from {csv_path}...")
    team_map = {}
    
    # Connect to database
    sqlite_db.init_db()
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in tqdm(list(reader)):
                name = row.get('name')
                external_id = row.get('team_id')
                short_name = row.get('abbr')
                state = row.get('state')
                
                if not name:
                    continue
                
                # Check if team already exists by external_id
                existing_team = None
                if external_id:
                    existing_team = sqlite_db.get_team_by_external_id(external_id)
                
                # If not found by external_id, try by name
                if not existing_team:
                    existing_team = sqlite_db.get_team_by_name(name)
                
                if existing_team:
                    team_map[name] = existing_team['id']
                else:
                    # Create new team
                    team_id = sqlite_db.add_team(
                        name=name,
                        external_id=external_id,
                        short_name=short_name,
                        state=state
                    )
                    team_map[name] = team_id
    finally:
        sqlite_db.close_db()
    
    print(f"Imported {len(team_map)} teams")
    return team_map

def import_wrestlers(csv_path, team_map=None):
    """
    Import wrestlers from CSV file.
    
    Args:
        csv_path: Path to the wrestlers CSV file
        team_map: Mapping of team names to team IDs (optional)
        
    Returns:
        dict: Mapping of wrestler external IDs to wrestler IDs
    """
    print(f"Importing wrestlers from {csv_path}...")
    wrestler_map = {}
    
    # If no team_map provided, create an empty one
    if team_map is None:
        team_map = {}
    
    # Connect to database
    sqlite_db.init_db()
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in tqdm(list(reader)):
                external_id = row.get('wrestlerID')
                name = row.get('name')
                weight_class = row.get('weight')
                team_name = row.get('team')
                active_team = row.get('activeTeam', 'False').lower() == 'true'
                
                # Parse numeric values
                win_percentage = float(row.get('win_percentage', 0)) if row.get('win_percentage') else 0
                bonus_percentage = float(row.get('bonus_percentage', 0)) if row.get('bonus_percentage') else 0
                rpi = float(row.get('rpi', 0)) if row.get('rpi') else None
                matches = int(row.get('matches', 0)) if row.get('matches') else 0
                days_since_last_match = int(row.get('days_since_last_match', 0)) if row.get('days_since_last_match') else None
                
                # Calculate wins and losses from win_percentage and matches
                wins = int(round(win_percentage * matches / 100)) if win_percentage and matches else 0
                losses = matches - wins
                
                if not external_id or not name or not weight_class or not team_name:
                    print(f"Warning: Skipping row with missing required data: {row}")
                    continue
                
                # Standardize weight class format
                weight_class = f"W{weight_class}" if not weight_class.startswith('W') else weight_class
                
                # Look up team_id if team exists in team_map
                team_id = None
                
                # Try exact match first
                if team_name in team_map:
                    team_id = team_map[team_name]
                else:
                    # Try to find a team that contains this team name
                    for t_name, t_id in team_map.items():
                        if team_name in t_name:
                            team_id = t_id
                            print(f"Matched team '{team_name}' to '{t_name}'")
                            break
                
                # Check if wrestler already exists
                existing_wrestler = sqlite_db.get_wrestler_by_external_id(external_id)
                
                if existing_wrestler:
                    # Update existing wrestler
                    sqlite_db.update_wrestler_stats(
                        existing_wrestler['id'],
                        wins=wins,
                        losses=losses,
                        matches=matches,
                        win_percentage=win_percentage,
                        bonus_percentage=bonus_percentage,
                        rpi=rpi,
                        days_since_last_match=days_since_last_match
                    )
                    wrestler_map[external_id] = existing_wrestler['id']
                else:
                    # Create new wrestler
                    wrestler_id = sqlite_db.add_wrestler(
                        name=name,
                        external_id=external_id,
                        team_id=team_id,
                        team_name=team_name,
                        weight_class=weight_class,
                        active_team=active_team,
                        wins=wins,
                        losses=losses,
                        matches=matches,
                        win_percentage=win_percentage,
                        bonus_percentage=bonus_percentage,
                        rpi=rpi,
                        days_since_last_match=days_since_last_match
                    )
                    wrestler_map[external_id] = wrestler_id
    finally:
        sqlite_db.close_db()
    
    print(f"Imported {len(wrestler_map)} wrestlers")
    return wrestler_map

def import_matches(csv_path, update_stats=True, update_relationships=True, limit=0):
    """
    Import matches from CSV file.
    
    Args:
        csv_path: Path to the matches CSV file
        update_stats: Whether to update wrestler stats after import
        update_relationships: Whether to update wrestler relationships after import
        limit: Number of matches to import (0 for all)
        
    Returns:
        int: Number of matches imported
    """
    print(f"Importing matches from {csv_path}...")
    count = 0
    
    # Connect to database
    sqlite_db.init_db()
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
            # Apply limit if specified
            if limit > 0:
                rows = rows[:limit]
                
            for row in tqdm(rows):
                uid = row.get('uid')
                weight_class = row.get('weight')
                
                # Get winner information
                winner_id = row.get('winnerID')
                winner_name = row.get('winner')
                winning_team = row.get('winningTeam')
                
                # Get loser information
                loser_id = row.get('loserID')
                loser_name = row.get('loser')
                losing_team = row.get('losingTeam')
                
                result = row.get('result')
                
                if not uid or not weight_class or not winner_id or not loser_id:
                    print(f"Warning: Skipping row with missing required data: {row}")
                    continue
                
                # Extract date from UID (format: mmddyyyy-winnerID-loserID)
                date_part = uid.split('-')[0]
                if len(date_part) == 8:
                    # Convert from mmddyyyy to yyyy-mm-dd
                    try:
                        month = int(date_part[0:2])
                        day = int(date_part[2:4])
                        year = int(date_part[4:8])
                        date_iso = f"{year:04d}-{month:02d}-{day:02d}"
                    except ValueError:
                        print(f"Warning: Invalid date format in UID: {uid}")
                        date_iso = datetime.date.today().isoformat()
                else:
                    print(f"Warning: Could not extract date from UID: {uid}")
                    date_iso = datetime.date.today().isoformat()
                
                # Standardize weight class format
                weight_class = f"W{weight_class}" if not weight_class.startswith('W') else weight_class
                
                # Check if match already exists
                existing_match = sqlite_db.get_match_by_external_id(uid)
                if existing_match:
                    print(f"Match with UID {uid} already exists, skipping")
                    continue
                
                # Ensure both wrestlers exist in the database
                get_or_create_wrestler_from_match(winner_id, winner_name, winning_team, weight_class)
                get_or_create_wrestler_from_match(loser_id, loser_name, losing_team, weight_class)
                
                # Add match to database
                sqlite_db.add_match(
                    external_id=uid,
                    date=date_iso,
                    weight_class=weight_class,
                    wrestler1_id=winner_id,
                    wrestler2_id=loser_id,
                    winner_id=winner_id,
                    result=result
                )
                count += 1
                
                # Update wrestler stats if requested
                if update_stats:
                    update_wrestler_stats_from_match(winner_id, loser_id, result)
                
                # Update relationships if requested
                if update_relationships:
                    from wrestlerank.matrix import relationship_manager
                    relationship_manager.update_direct_relationship(
                        winner_id, loser_id, weight_class
                    )
    finally:
        sqlite_db.close_db()
    
    print(f"Imported {count} matches")
    return count

def update_wrestler_stats_from_match(winner_id, loser_id, result):
    """Update wrestler statistics based on a match result."""
    # Get wrestlers
    winner = sqlite_db.get_wrestler_by_external_id(winner_id)
    loser = sqlite_db.get_wrestler_by_external_id(loser_id)
    
    if not winner or not loser:
        return
    
    # Update winner stats
    wins = winner['wins'] + 1
    matches = winner['matches'] + 1
    win_percentage = (wins / matches) * 100 if matches > 0 else 0
    
    sqlite_db.update_wrestler_stats(
        winner['id'],
        wins=wins,
        matches=matches,
        win_percentage=win_percentage
    )
    
    # Update loser stats
    losses = loser['losses'] + 1
    matches = loser['matches'] + 1
    win_percentage = (loser['wins'] / matches) * 100 if matches > 0 else 0
    
    sqlite_db.update_wrestler_stats(
        loser['id'],
        losses=losses,
        matches=matches,
        win_percentage=win_percentage
    )

def get_or_create_wrestler_from_match(wrestler_id, name, team_name, weight_class):
    """
    Get an existing wrestler or create a new one from match data.
    
    Args:
        wrestler_id: External ID of the wrestler
        name: Name of the wrestler
        team_name: Name of the wrestler's team
        weight_class: Weight class of the wrestler
        
    Returns:
        dict: Wrestler record
    """
    # Check if wrestler already exists
    wrestler = sqlite_db.get_wrestler_by_external_id(wrestler_id)
    
    if wrestler:
        return wrestler
    
    # Wrestler doesn't exist, create a new one
    print(f"Creating new wrestler from match data: {name} ({wrestler_id})")
    
    # Look up team_id if possible
    team_id = None
    cursor = sqlite_db.conn.cursor()
    cursor.execute("SELECT id FROM teams WHERE name LIKE ?", (f"%{team_name}%",))
    team = cursor.fetchone()
    if team:
        team_id = team['id']
    
    # Create the wrestler
    wrestler_db_id = sqlite_db.add_wrestler(
        name=name,
        external_id=wrestler_id,
        team_id=team_id,
        team_name=team_name,
        weight_class=weight_class,
        active_team=False,  # Default to inactive since we don't know
        wins=0,
        losses=0,
        matches=0
    )
    
    # Return the newly created wrestler
    cursor.execute("SELECT * FROM wrestlers WHERE id = ?", (wrestler_db_id,))
    return cursor.fetchone()

def run_migration(csv_dir):
    """
    Run the full migration process.
    
    Args:
        csv_dir: Directory containing CSV files
        
    Returns:
        bool: True if migration was successful
    """
    # Find CSV files
    team_csv = os.path.join(csv_dir, 'team-list.csv')
    wrestler_csv = os.path.join(csv_dir, 'wrestler-list-CLEAN.csv')
    match_csv = os.path.join(csv_dir, 'match-results-all.csv')
    
    # Check if files exist
    if not os.path.exists(team_csv):
        print(f"Error: Team file not found at {team_csv}")
        return False
    
    if not os.path.exists(wrestler_csv):
        print(f"Error: Wrestler file not found at {wrestler_csv}")
        return False
    
    if not os.path.exists(match_csv):
        print(f"Error: Match file not found at {match_csv}")
        return False
    
    # Run migration
    team_map = import_teams(team_csv)
    wrestler_map = import_wrestlers(wrestler_csv, team_map)
    import_matches(match_csv)
    
    print("Migration completed successfully!")
    return True 