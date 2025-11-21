"""
Database migration utilities for WrestleRank.

This module provides functions for migrating data from the legacy CSV-based
system to the new database-driven architecture.
"""

import os
import csv
import pandas as pd
from datetime import datetime
from tqdm import tqdm
from sqlalchemy.exc import IntegrityError

from . import init_db, create_tables, get_session
from .models import Team, Wrestler, Match, WeightClass, MatchType
from .operations import add_team, add_wrestler, add_match

def parse_date(date_str):
    """Parse date string in various formats."""
    formats = ['%m/%d/%Y', '%Y-%m-%d', '%m-%d-%Y']
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Could not parse date: {date_str}")

def import_teams(csv_path):
    """
    Import teams from a CSV file.
    
    Args:
        csv_path (str): Path to the CSV file containing team data
        
    Returns:
        dict: Mapping of team names to team IDs
    """
    print(f"Importing teams from {csv_path}...")
    team_map = {}
    session = get_session()
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in tqdm(list(reader)):
            name = row.get('team_name') or row.get('name')
            if not name:
                continue
                
            # Check if team already exists
            team = session.query(Team).filter(Team.name == name).first()
            if not team:
                # Create new team
                team = Team(
                    name=name,
                    short_name=row.get('short_name'),
                    location=row.get('location'),
                    state=row.get('state')
                )
                session.add(team)
                session.flush()  # Get ID without committing
                
            team_map[name] = team.id
    
    session.commit()
    session.close()
    print(f"Imported {len(team_map)} teams.")
    return team_map

def migrate_legacy_data(legacy_dir):
    """
    Migrate all legacy data from CSV files to the database.
    
    Args:
        legacy_dir (str): Directory containing legacy CSV files
        
    Returns:
        bool: True if migration was successful
    """
    # Initialize database
    init_db()
    create_tables()
    
    # Find CSV files
    team_csv = os.path.join(legacy_dir, 'team-list.csv')
    wrestler_csv = os.path.join(legacy_dir, 'wrestler-list-CLEAN.csv')
    match_csv = os.path.join(legacy_dir, 'match-results-all.csv')
    
    # Check if files exist
    if not os.path.exists(team_csv):
        print(f"Error: Team list file not found at {team_csv}")
        return False
        
    # Import teams
    team_map = import_teams(team_csv)
    
    # More import functions would be implemented here
    
    return True 