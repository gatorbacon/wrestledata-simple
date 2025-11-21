"""
Direct SQLite database implementation for WrestleRank.

This module provides a simpler alternative to SQLAlchemy that doesn't
require compilation of C extensions.
"""

import sqlite3
import os
from datetime import datetime

# Database connection
DB_PATH = 'wrestlerank.db'
conn = None

def init_db(db_path=DB_PATH, timeout=30):
    """Initialize the database connection."""
    global conn
    conn = sqlite3.connect(db_path, timeout=timeout)
    conn.row_factory = sqlite3.Row
    return conn

def create_tables():
    """Create all necessary tables."""
    cursor = conn.cursor()
    
    # Create teams table with external_id field
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS teams (
        id INTEGER PRIMARY KEY,
        external_id TEXT,  -- Store the team_id from CSV
        name TEXT NOT NULL,
        short_name TEXT,
        state TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create wrestlers table with additional fields
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS wrestlers (
        id INTEGER PRIMARY KEY,
        external_id TEXT,  -- Store the wrestlerID from CSV
        name TEXT NOT NULL,
        team_id INTEGER,
        team_name TEXT,    -- Store the original team name from CSV
        weight_class TEXT NOT NULL,
        active_team BOOLEAN DEFAULT 0,
        wins INTEGER DEFAULT 0,
        losses INTEGER DEFAULT 0,
        matches INTEGER DEFAULT 0,
        win_percentage REAL DEFAULT 0,
        bonus_percentage REAL DEFAULT 0,
        rpi REAL,
        days_since_last_match INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (team_id) REFERENCES teams (id)
    )
    ''')
    
    # Create matches table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY,
        external_id TEXT,  -- Store the original UID
        date TEXT NOT NULL,  -- Store as ISO format YYYY-MM-DD
        weight_class TEXT NOT NULL,
        wrestler1_id TEXT NOT NULL,  -- External ID of first wrestler
        wrestler2_id TEXT NOT NULL,  -- External ID of second wrestler
        winner_id TEXT NOT NULL,     -- External ID of winner
        result TEXT,                 -- Fall, Decision, etc.
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create rankings table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS rankings (
        id INTEGER PRIMARY KEY,
        wrestler_id INTEGER NOT NULL,
        weight_class TEXT NOT NULL,
        rank INTEGER NOT NULL,
        date TEXT NOT NULL,
        algorithm TEXT,
        win_percentage REAL,
        rpi REAL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (wrestler_id) REFERENCES wrestlers (id)
    )
    ''')
    
    # Create wrestler_relationships table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS wrestler_relationships (
        id INTEGER PRIMARY KEY,
        wrestler1_id TEXT NOT NULL,  -- External ID of first wrestler
        wrestler2_id TEXT NOT NULL,  -- External ID of second wrestler
        direct_wins INTEGER DEFAULT 0,  -- Direct wins by wrestler1 over wrestler2
        direct_losses INTEGER DEFAULT 0,  -- Direct losses by wrestler1 to wrestler2
        common_opp_wins INTEGER DEFAULT 0,  -- Common opponent wins
        common_opp_losses INTEGER DEFAULT 0,  -- Common opponent losses
        weight_class TEXT NOT NULL,  -- Weight class where this relationship applies
        last_updated TEXT NOT NULL,  -- When this relationship was last updated
        UNIQUE(wrestler1_id, wrestler2_id, weight_class)
    )
    ''')
    
    # Create common_opponent_paths table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS common_opponent_paths (
        id INTEGER PRIMARY KEY,
        wrestler1_id TEXT NOT NULL,  -- External ID of first wrestler
        wrestler2_id TEXT NOT NULL,  -- External ID of second wrestler
        common_opponent_id TEXT NOT NULL,  -- External ID of the common opponent
        match1_id TEXT NOT NULL,  -- External ID of the first match
        match2_id TEXT NOT NULL,  -- External ID of the second match
        weight_class TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(wrestler1_id, wrestler2_id, common_opponent_id, match1_id, match2_id)
    )
    ''')
    
    # Create wrestler rankings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS wrestler_rankings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wrestler_id TEXT NOT NULL,
            weight_class TEXT NOT NULL,
            rank INTEGER NOT NULL,
            date TEXT NOT NULL,
            last_updated TEXT NOT NULL,
            algorithm TEXT,
            UNIQUE(wrestler_id, weight_class, date)
        )
    ''')
    
    # Add indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_wrestler_relationships_w1 ON wrestler_relationships (wrestler1_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_wrestler_relationships_w2 ON wrestler_relationships (wrestler2_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_wrestler_relationships_weight ON wrestler_relationships (weight_class)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_common_opponent_paths_w1 ON common_opponent_paths (wrestler1_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_common_opponent_paths_w2 ON common_opponent_paths (wrestler2_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_matches_wrestlers ON matches (wrestler1_id, wrestler2_id)")
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_rankings_wrestler ON wrestler_rankings (wrestler_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_rankings_weight_date ON wrestler_rankings (weight_class, date)')
    
    conn.commit()

def close_db():
    """Close the database connection."""
    if conn:
        conn.close()

# Team operations
def add_team(name, external_id=None, short_name=None, state=None):
    """Add a new team to the database."""
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO teams (name, external_id, short_name, state) VALUES (?, ?, ?, ?)",
        (name, external_id, short_name, state)
    )
    conn.commit()
    return cursor.lastrowid

def get_team_by_name(name):
    """Get a team by name."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM teams WHERE name = ?", (name,))
    return cursor.fetchone()

def get_team_by_external_id(external_id):
    """Get a team by its external ID."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM teams WHERE external_id = ?", (external_id,))
    return cursor.fetchone()

# Wrestler operations
def add_wrestler(name, external_id=None, team_id=None, team_name=None, weight_class=None, 
                active_team=False, wins=0, losses=0, matches=0, win_percentage=0, 
                bonus_percentage=0, rpi=None, days_since_last_match=None):
    """Add a new wrestler to the database."""
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO wrestlers 
           (name, external_id, team_id, team_name, weight_class, active_team, 
            wins, losses, matches, win_percentage, bonus_percentage, rpi, days_since_last_match) 
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (name, external_id, team_id, team_name, weight_class, active_team, 
         wins, losses, matches, win_percentage, bonus_percentage, rpi, days_since_last_match)
    )
    conn.commit()
    return cursor.lastrowid

def get_wrestlers_by_weight_class(weight_class):
    """Get all wrestlers in a weight class."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT w.*, t.name as team_name 
        FROM wrestlers w
        JOIN teams t ON w.team_id = t.id
        WHERE w.weight_class = ?
    """, (weight_class,))
    return cursor.fetchall()

# Add a function to get wrestler by external_id
def get_wrestler_by_external_id(external_id):
    """Get a wrestler by external ID."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM wrestlers WHERE external_id = ?", (external_id,))
    return cursor.fetchone()

# Add a function to update wrestler stats
def update_wrestler_stats(wrestler_id, wins=None, losses=None, matches=None, 
                         win_percentage=None, bonus_percentage=None, rpi=None, 
                         days_since_last_match=None):
    """Update wrestler statistics."""
    cursor = conn.cursor()
    
    # Build the SET clause dynamically based on provided values
    set_clauses = []
    params = []
    
    if wins is not None:
        set_clauses.append("wins = ?")
        params.append(wins)
    if losses is not None:
        set_clauses.append("losses = ?")
        params.append(losses)
    if matches is not None:
        set_clauses.append("matches = ?")
        params.append(matches)
    if win_percentage is not None:
        set_clauses.append("win_percentage = ?")
        params.append(win_percentage)
    if bonus_percentage is not None:
        set_clauses.append("bonus_percentage = ?")
        params.append(bonus_percentage)
    if rpi is not None:
        set_clauses.append("rpi = ?")
        params.append(rpi)
    if days_since_last_match is not None:
        set_clauses.append("days_since_last_match = ?")
        params.append(days_since_last_match)
    
    if not set_clauses:
        return False  # Nothing to update
    
    # Add wrestler_id to params
    params.append(wrestler_id)
    
    # Execute the update
    cursor.execute(
        f"UPDATE wrestlers SET {', '.join(set_clauses)} WHERE id = ?",
        params
    )
    conn.commit()
    return True 

# Add functions for match operations
def add_match(external_id, date, weight_class, wrestler1_id, wrestler2_id, winner_id, result=None):
    """Add a new match to the database."""
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO matches 
           (external_id, date, weight_class, wrestler1_id, wrestler2_id, winner_id, result) 
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (external_id, date, weight_class, wrestler1_id, wrestler2_id, winner_id, result)
    )
    conn.commit()
    return cursor.lastrowid

def get_match_by_external_id(external_id):
    """Get a match by its external ID."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM matches WHERE external_id = ?", (external_id,))
    return cursor.fetchone()

def get_matches_by_wrestler_id(wrestler_id):
    """Get all matches involving a wrestler."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM matches 
        WHERE wrestler1_id = ? OR wrestler2_id = ?
        ORDER BY date DESC
    """, (wrestler_id, wrestler_id))
    return cursor.fetchall() 