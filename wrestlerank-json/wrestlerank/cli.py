"""
Command-line interface for the WrestleRank system.

This module provides the main entry point for the WrestleRank CLI.
"""

import click
import os
from datetime import datetime
import sqlite3
import csv
from tqdm import tqdm
import time

# Use the simplified SQLite module instead of SQLAlchemy
from wrestlerank.db import sqlite_db
from wrestlerank.migration import import_csv
from wrestlerank.migration import import_json

@click.group()
def main():
    """WrestleRank - Wrestling Rankings System."""
    pass

@main.command()
@click.option('--db-path', default='wrestlerank.db', help='Path to the database file')
@click.option('--update-only', is_flag=True, help='Only update schema, don\'t reset data')
def init(db_path, update_only):
    """Initialize or update the database."""
    if update_only:
        click.echo(f"Updating database schema at {db_path}")
        sqlite_db.init_db(db_path)
        sqlite_db.create_tables()
        click.echo("Database schema updated successfully!")
    else:
        click.echo(f"Initializing database at {db_path}")
        sqlite_db.init_db(db_path)
        sqlite_db.create_tables()
        click.echo("Database initialized successfully!")

@main.command()
def version():
    """Display the current version."""
    click.echo("WrestleRank v0.1.0")

@main.command()
@click.option('--weight-class', help='Weight class to list wrestlers for')
@click.option('--team', help='Team name to filter by')
@click.option('--active-only', is_flag=True, help='Show only wrestlers from active teams')
def list_wrestlers(weight_class, team, active_only):
    """List wrestlers in the database."""
    sqlite_db.init_db()
    
    # Build the query based on filters
    query = """
        SELECT w.*, t.name as team_db_name 
        FROM wrestlers w
        LEFT JOIN teams t ON w.team_id = t.id
        WHERE 1=1
    """
    params = []
    
    if weight_class:
        query += " AND w.weight_class = ?"
        params.append(weight_class)
    
    if team:
        query += " AND (w.team_name LIKE ? OR t.name LIKE ?)"
        params.extend([f"%{team}%", f"%{team}%"])
    
    if active_only:
        query += " AND w.active_team = 1"
    
    query += " ORDER BY w.weight_class, w.win_percentage DESC"
    
    cursor = sqlite_db.conn.cursor()
    cursor.execute(query, params)
    wrestlers = cursor.fetchall()
    
    if weight_class:
        click.echo(f"Wrestlers in {weight_class} weight class:")
    elif team:
        click.echo(f"Wrestlers from team containing '{team}':")
    elif active_only:
        click.echo("Wrestlers from active teams:")
    else:
        click.echo("All wrestlers:")
    
    # Group by weight class
    current_weight = None
    for w in wrestlers:
        if current_weight != w['weight_class']:
            current_weight = w['weight_class']
            click.echo(f"\n{current_weight}:")
        
        team_info = w['team_name']
        if w['team_id']:
            team_info += f" ({w['team_db_name']})"
        
        stats = f"{w['wins']}-{w['losses']} ({w['win_percentage']}%)"
        if w['rpi']:
            stats += f", RPI: {w['rpi']:.3f}"
        
        click.echo(f"  {w['id']}: {w['name']} - {team_info} - {stats}")
    
    click.echo(f"\nTotal: {len(wrestlers)} wrestlers")
    
    sqlite_db.close_db()

@main.command()
@click.argument('csv_dir', type=click.Path(exists=True))
def migrate(csv_dir):
    """Import data from CSV files into the database."""
    click.echo(f"Migrating data from {csv_dir}...")
    import_csv.run_migration(csv_dir)
    click.echo("Migration complete!")

@main.command()
@click.argument('csv_path', type=click.Path(exists=True))
@click.option('--team-csv', type=click.Path(exists=True), help='Path to team CSV for mapping')
def import_wrestlers(csv_path, team_csv):
    """Import only wrestlers from a CSV file."""
    click.echo(f"Importing wrestlers from {csv_path}...")
    
    # First import teams if team_csv is provided
    team_map = {}
    if team_csv:
        click.echo(f"First importing teams from {team_csv}...")
        team_map = import_csv.import_teams(team_csv)
    
    # Then import wrestlers
    wrestler_map = import_csv.import_wrestlers(csv_path, team_map)
    click.echo(f"Successfully imported {len(wrestler_map)} wrestlers.")

@main.command()
def list_teams():
    """List all teams in the database."""
    sqlite_db.init_db()
    
    cursor = sqlite_db.conn.cursor()
    cursor.execute("SELECT * FROM teams ORDER BY name")
    teams = cursor.fetchall()
    
    click.echo(f"Found {len(teams)} teams:")
    for team in teams:
        click.echo(f"{team['id']}: {team['name']} ({team['state']}) - External ID: {team['external_id']}")
    
    sqlite_db.close_db()

@main.command("import-teams-json")
@click.argument('json_path', type=click.Path(exists=True))
def import_teams_json(json_path):
    """Import teams from a JSON file."""
    click.echo(f"Importing teams from JSON: {json_path}...")
    try:
        team_map = import_json.import_teams_json(json_path)
        click.echo(f"Successfully imported or matched {len(team_map)} teams.")
    except Exception as e:
        click.echo(f"Error importing teams JSON: {e}")

@main.command()
@click.argument('csv_path', type=click.Path(exists=True))
def import_teams(csv_path):
    """Import only teams from a CSV file."""
    click.echo(f"Importing teams from {csv_path}...")
    team_map = import_csv.import_teams(csv_path)
    click.echo(f"Successfully imported {len(team_map)} teams.")

@main.command("import-matches-json")
@click.argument('path', type=click.Path(exists=True))
@click.option('--no-relationships', is_flag=True, help='Do not update relationships during import')
def import_matches_json(path, no_relationships):
    """Import matches (and rostered wrestlers) from a JSON file or directory."""
    update_relationships = not no_relationships
    click.echo(f"Importing matches from JSON path: {path} (update_relationships={update_relationships})...")
    try:
        total = import_json.import_matches_json(path, update_relationships=update_relationships)
        if total > 0:
            click.echo(f"Imported {total} matches.")
        else:
            click.echo("No matches were imported.")
    except Exception as e:
        click.echo(f"Error importing matches JSON: {e}")

@main.command()
@click.option('--db-path', default='wrestlerank.db', help='Path to the database file')
@click.option('--force', is_flag=True, help='Force reset without confirmation')
def reset(db_path, force):
    """Reset the database by deleting it and recreating it."""
    if not force:
        if not click.confirm(f"This will delete all data in {db_path}. Are you sure?"):
            click.echo("Operation cancelled.")
            return
    
    # Close any existing connections
    sqlite_db.close_db()
    
    # Delete the database file
    if os.path.exists(db_path):
        os.remove(db_path)
        click.echo(f"Deleted existing database: {db_path}")
    
    # Initialize a fresh database
    sqlite_db.init_db(db_path)
    sqlite_db.create_tables()
    
    click.echo("Database reset successfully!")

@main.command()
@click.argument('csv_path', type=click.Path(exists=True))
@click.option('--update-stats/--no-update-stats', default=True, 
              help='Update wrestler stats after import')
@click.option('--limit', type=int, default=0, help='Limit number of matches to import (0 for all)')
def import_matches(csv_path, update_stats, limit):
    """Import matches from a CSV file."""
    click.echo(f"Importing matches from {csv_path}...")
    
    count = import_csv.import_matches(csv_path, update_stats, limit=limit)
    
    if limit > 0:
        click.echo(f"Imported {count} matches (limited to {limit})")
    else:
        click.echo(f"Imported {count} matches")

@main.command()
@click.option('--wrestler', help='Filter by wrestler name')
@click.option('--weight-class', help='Filter by weight class')
@click.option('--date-from', help='Filter by date (YYYY-MM-DD)')
@click.option('--date-to', help='Filter by date (YYYY-MM-DD)')
@click.option('--limit', type=int, default=50, help='Limit number of results')
def list_matches(wrestler, weight_class, date_from, date_to, limit):
    """List matches in the database."""
    sqlite_db.init_db()
    
    # Build query
    query = """
        SELECT m.*, 
               w1.name as wrestler1_name, w1.team_name as wrestler1_team,
               w2.name as wrestler2_name, w2.team_name as wrestler2_team
        FROM matches m
        JOIN wrestlers w1 ON m.wrestler1_id = w1.external_id
        JOIN wrestlers w2 ON m.wrestler2_id = w2.external_id
        WHERE 1=1
    """
    params = []
    
    if wrestler:
        query += " AND (w1.name LIKE ? OR w2.name LIKE ?)"
        params.extend([f"%{wrestler}%", f"%{wrestler}%"])
    
    if weight_class:
        query += " AND m.weight_class = ?"
        params.append(weight_class)
    
    if date_from:
        query += " AND m.date >= ?"
        params.append(date_from)
    
    if date_to:
        query += " AND m.date <= ?"
        params.append(date_to)
    
    query += " ORDER BY m.date DESC LIMIT ?"
    params.append(limit)
    
    cursor = sqlite_db.conn.cursor()
    cursor.execute(query, params)
    matches = cursor.fetchall()
    
    click.echo(f"Found {len(matches)} matches:")
    for m in matches:
        winner_name = m['wrestler1_name'] if m['winner_id'] == m['wrestler1_id'] else m['wrestler2_name']
        loser_name = m['wrestler2_name'] if m['winner_id'] == m['wrestler1_id'] else m['wrestler1_name']
        
        click.echo(f"{m['date']} - {m['weight_class']}: {winner_name} def. {loser_name} ({m['result']})")
    
    sqlite_db.close_db()

@main.command()
def update_schema():
    """Update the database schema without losing data."""
    click.echo("Updating database schema...")
    
    # Initialize the database connection
    sqlite_db.init_db()
    
    try:
        # Create any missing tables and indexes
        sqlite_db.create_tables()
        
        click.echo("Schema update completed successfully!")
    except Exception as e:
        click.echo(f"Error during schema update: {e}")
    finally:
        sqlite_db.close_db()

@main.command()
@click.argument('csv_path', type=click.Path(exists=True))
@click.option('--add-missing/--no-add-missing', default=True, 
              help='Add missing wrestlers to the database')
def discover_wrestlers(csv_path, add_missing):
    """Discover wrestlers from match data without importing matches."""
    click.echo(f"Discovering wrestlers from {csv_path}...")
    
    sqlite_db.init_db()
    discovered = 0
    added = 0
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
            click.echo(f"Processing {len(rows)} matches...")
            
            for row in tqdm(rows):
                # Process winner
                winner_id = row.get('winnerID')
                if winner_id:
                    wrestler = sqlite_db.get_wrestler_by_external_id(winner_id)
                    if not wrestler:
                        discovered += 1
                        if add_missing:
                            import_csv.get_or_create_wrestler_from_match(
                                winner_id, 
                                row.get('winner'), 
                                row.get('winningTeam'),
                                row.get('weight')
                            )
                            added += 1
                
                # Process loser
                loser_id = row.get('loserID')
                if loser_id:
                    wrestler = sqlite_db.get_wrestler_by_external_id(loser_id)
                    if not wrestler:
                        discovered += 1
                        if add_missing:
                            import_csv.get_or_create_wrestler_from_match(
                                loser_id, 
                                row.get('loser'), 
                                row.get('losingTeam'),
                                row.get('weight')
                            )
                            added += 1
    finally:
        sqlite_db.close_db()
    
    click.echo(f"Discovered {discovered} new wrestlers")
    if add_missing:
        click.echo(f"Added {added} new wrestlers to the database")
    else:
        click.echo("No wrestlers were added (--no-add-missing flag was set)")

@main.command()
@click.argument('weight_class')
@click.option('--limit', type=int, default=0, help='Maximum number of wrestlers to include (0 for all)')
@click.option('--use-rankings/--no-use-rankings', default=True, 
              help='Sort by official rankings instead of win percentage')
@click.option('--output', type=click.Path(), 
              default='matrix.html', help='Output file path')
def matrix(weight_class, limit, use_rankings, output):
    """Generate a head-to-head matrix for a weight class."""
    click.echo(f"Generating matrix for {weight_class}...")
    
    from wrestlerank.matrix import matrix_generator
    
    matrix_data = matrix_generator.build_matrix(
        weight_class, 
        include_adjacent=True, 
        limit=limit,
        use_rankings=use_rankings
    )
    
    html = matrix_generator.generate_html(matrix_data, weight_class)
    
    # Write to file with explicit UTF-8 encoding
    with open(output, 'w', encoding='utf-8') as f:
        f.write(html)
        
    click.echo(f"Matrix saved to {output}")
    
    # Open in browser if possible
    try:
        import webbrowser
        webbrowser.open(output)
    except:
        pass

@main.command()
@click.option('--reset', is_flag=True, help='Reset existing relationships before rebuilding')
@click.option('--all', is_flag=True, help='Process all matches, not just new ones')
@click.option('--timeout', type=int, default=30, help='SQLite timeout in seconds')
def build_relationships(reset, all, timeout):
    """Build wrestler relationships from match data."""
    from wrestlerank.matrix import relationship_manager
    
    click.echo("Building wrestler relationships from match data...")
    
    # Initialize the database with a timeout
    sqlite_db.init_db(timeout=timeout)
    
    try:
        # Reset relationships if requested
        if reset:
            if click.confirm("This will delete all existing relationship data. Continue?"):
                cursor = sqlite_db.conn.cursor()
                cursor.execute("DELETE FROM wrestler_relationships")
                cursor.execute("DELETE FROM common_opponent_paths")
                
                # Also reset the processed flag on all matches
                cursor.execute("UPDATE matches SET processed = 0 WHERE processed IS NOT NULL")
                
                sqlite_db.conn.commit()
                click.echo("Existing relationships deleted.")
            else:
                click.echo("Operation cancelled.")
                return
        
        # First, check if we need to add a 'processed' column to the matches table
        cursor = sqlite_db.conn.cursor()
        cursor.execute("PRAGMA table_info(matches)")
        columns = cursor.fetchall()
        has_processed = any(col['name'] == 'processed' for col in columns)
        
        if not has_processed:
            click.echo("Adding 'processed' column to matches table...")
            cursor.execute("ALTER TABLE matches ADD COLUMN processed INTEGER DEFAULT 0")
            sqlite_db.conn.commit()
        
        # Get matches that haven't been processed yet (or all if --all flag is set)
        if all:
            cursor.execute("SELECT * FROM matches ORDER BY date")
        else:
            cursor.execute("SELECT * FROM matches WHERE processed = 0 OR processed IS NULL ORDER BY date")
        
        matches = cursor.fetchall()
        
        click.echo(f"Processing {len(matches)} matches...")
        
        # Process each match in smaller batches to avoid long-running transactions
        batch_size = 100
        total_batches = (len(matches) + batch_size - 1) // batch_size
        
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min((batch_num + 1) * batch_size, len(matches))
            batch = matches[start_idx:end_idx]
            
            click.echo(f"Processing batch {batch_num + 1}/{total_batches} ({len(batch)} matches)...")
            
            # Begin a transaction for this batch
            cursor.execute("BEGIN TRANSACTION")
            
            try:
                # Process each match in the batch
                for match in tqdm(batch):
                    loser_id = match['wrestler1_id'] if match['winner_id'] != match['wrestler1_id'] else match['wrestler2_id']
                    
                    relationship_manager.update_direct_relationship(
                        match['winner_id'],
                        loser_id,
                        match['weight_class'],
                        match['external_id'],
                        existing_connection=True  # Use the existing connection
                    )
                    
                    # Mark this match as processed
                    cursor.execute("UPDATE matches SET processed = 1 WHERE external_id = ?", (match['external_id'],))
                
                # Commit the batch transaction
                sqlite_db.conn.commit()
                click.echo(f"Batch {batch_num + 1} processed successfully")
                
            except Exception as e:
                # If an error occurs, roll back this batch
                sqlite_db.conn.rollback()
                click.echo(f"Error processing batch {batch_num + 1}: {e}")
                click.echo("Rolling back batch and continuing with next batch...")
        
        sqlite_db.conn.commit()
        click.echo("Relationships built successfully!")
        
    except Exception as e:
        click.echo(f"Error building relationships: {e}")
    finally:
        sqlite_db.close_db()

@main.command()
@click.argument('csv_dir', type=click.Path(exists=True))
@click.option('--match-limit', type=int, default=5000, help='Limit number of matches to import')
def quick_test(csv_dir, match_limit):
    """Run a quick test with limited data import."""
    click.echo(f"Running quick test with data from {csv_dir}...")
    
    # Find CSV files
    team_csv = os.path.join(csv_dir, 'team-list.csv')
    wrestler_csv = os.path.join(csv_dir, 'wrestler-list.csv')
    match_csv = os.path.join(csv_dir, 'match-results.csv')
    
    # Check if files exist
    for file_path in [team_csv, wrestler_csv, match_csv]:
        if not os.path.exists(file_path):
            click.echo(f"Error: File not found at {file_path}")
            return
    
    # Import data
    click.echo("Importing teams...")
    team_map = import_csv.import_teams(team_csv)
    
    click.echo("Importing wrestlers...")
    wrestler_map = import_csv.import_wrestlers(wrestler_csv, team_map)
    
    click.echo(f"Importing matches (limited to {match_limit})...")
    import_csv.import_matches(match_csv, limit=match_limit)
    
    # Build relationships
    click.echo("Building relationships...")
    from wrestlerank.matrix import relationship_manager
    
    sqlite_db.init_db()
    cursor = sqlite_db.conn.cursor()
    cursor.execute("SELECT * FROM matches ORDER BY date")
    matches = cursor.fetchall()
    
    for match in tqdm(matches):
        relationship_manager.update_direct_relationship(
            match['winner_id'],
            match['wrestler1_id'] if match['winner_id'] != match['wrestler1_id'] else match['wrestler2_id'],
            match['weight_class'],
            match['external_id']
        )
    
    sqlite_db.close_db()
    
    click.echo("Quick test completed successfully!")

@main.command()
@click.argument('weight_class')
@click.option('--include-adjacent/--no-include-adjacent', default=True, 
              help='Include adjacent weight classes for relationship calculations')
@click.option('--limit', type=int, default=0, 
              help='Limit number of matches to process (0 for all)')
def build_weight_class_relationships(weight_class, include_adjacent, limit):
    """Build relationships for a specific weight class."""
    from wrestlerank.matrix import relationship_manager
    
    click.echo(f"Building relationships for weight class {weight_class}...")
    
    # Get adjacent weight classes if needed
    adjacent_classes = []
    if include_adjacent:
        # Define the actual weight class sequences
        mens_weight_classes = ['106', '113', '120', '126', '132', '138', '144', '150', '157', '165', '175', '190', '215', '285']
        womens_weight_classes = ['W100', 'W107', 'W114', 'W120', 'W126', 'W132', 'W138', 'W145', 'W152', 'W165', 'W185', 'W235']
        
        if weight_class.startswith('W'):
            # Women's weight classes
            if weight_class in womens_weight_classes:
                idx = womens_weight_classes.index(weight_class)
                if idx > 0:
                    adjacent_classes.append(womens_weight_classes[idx - 1])
                if idx < len(womens_weight_classes) - 1:
                    adjacent_classes.append(womens_weight_classes[idx + 1])
        else:
            # Men's weight classes
            if weight_class in mens_weight_classes:
                idx = mens_weight_classes.index(weight_class)
                if idx > 0:
                    adjacent_classes.append(mens_weight_classes[idx - 1])
                if idx < len(mens_weight_classes) - 1:
                    adjacent_classes.append(mens_weight_classes[idx + 1])
    
    click.echo(f"Including adjacent weight classes: {', '.join(adjacent_classes)}")
    
    # Build the relationships
    relationship_manager.build_weight_class_relationships(
        weight_class, 
        adjacent_classes=adjacent_classes,
        limit=limit
    )
    
    click.echo(f"Relationships for {weight_class} built successfully!")

@main.command()
@click.argument('weight_class')
def debug_matrix(weight_class):
    """Debug matrix generation for a weight class."""
    click.echo(f"Debugging matrix for {weight_class}...")
    
    sqlite_db.init_db()
    
    try:
        cursor = sqlite_db.conn.cursor()
        
        # 1. Check wrestlers in this weight class
        cursor.execute(
            "SELECT COUNT(*) as count FROM wrestlers WHERE weight_class = ?",
            (weight_class,)
        )
        wrestler_count = cursor.fetchone()['count']
        click.echo(f"Found {wrestler_count} wrestlers in weight class {weight_class}")
        
        # 2. Get sample wrestlers
        cursor.execute(
            "SELECT external_id, name FROM wrestlers WHERE weight_class = ? ORDER BY win_percentage DESC LIMIT 5",
            (weight_class,)
        )
        sample_wrestlers = cursor.fetchall()
        click.echo("Sample wrestlers:")
        for w in sample_wrestlers:
            click.echo(f"  {w['name']} (ID: {w['external_id']})")
        
        if not sample_wrestlers:
            click.echo("No wrestlers found in this weight class!")
            return
            
        # 3. Check relationships
        wrestler_ids = [w['external_id'] for w in sample_wrestlers]
        placeholders = ','.join(['?'] * len(wrestler_ids))
        
        cursor.execute(
            f"""
            SELECT COUNT(*) as count FROM wrestler_relationships 
            WHERE wrestler1_id IN ({placeholders}) 
            AND wrestler2_id IN ({placeholders})
            """,
            wrestler_ids + wrestler_ids
        )
        relationship_count = cursor.fetchone()['count']
        click.echo(f"Found {relationship_count} relationships between sample wrestlers")
        
        # 4. Check for specific relationships
        if len(wrestler_ids) >= 2:
            cursor.execute(
                """
                SELECT * FROM wrestler_relationships 
                WHERE wrestler1_id = ? AND wrestler2_id = ?
                """,
                (wrestler_ids[0], wrestler_ids[1])
            )
            rel = cursor.fetchone()
            if rel:
                click.echo(f"Sample relationship: {rel['wrestler1_id']} vs {rel['wrestler2_id']}")
                click.echo(f"  Direct wins: {rel['direct_wins']}, Direct losses: {rel['direct_losses']}")
                click.echo(f"  Common opp wins: {rel['common_opp_wins']}, Common opp losses: {rel['common_opp_losses']}")
                click.echo(f"  Weight class: {rel['weight_class']}")
            else:
                click.echo(f"No relationship found between {wrestler_ids[0]} and {wrestler_ids[1]}")
        
        # 5. Check matches
        cursor.execute(
            f"""
            SELECT COUNT(*) as count FROM matches 
            WHERE wrestler1_id IN ({placeholders}) 
            OR wrestler2_id IN ({placeholders})
            """,
            wrestler_ids + wrestler_ids
        )
        match_count = cursor.fetchone()['count']
        click.echo(f"Found {match_count} matches involving sample wrestlers")
        
    finally:
        sqlite_db.close_db()

@main.command()
def check_relationship_weight_classes():
    """Check the weight classes in the relationships table."""
    sqlite_db.init_db()
    
    try:
        cursor = sqlite_db.conn.cursor()
        cursor.execute("SELECT DISTINCT weight_class FROM wrestler_relationships")
        weight_classes = cursor.fetchall()
        
        click.echo("Weight classes in relationships table:")
        for wc in weight_classes:
            click.echo(f"  '{wc['weight_class']}'")
            
        # Count relationships per weight class
        cursor.execute("SELECT weight_class, COUNT(*) as count FROM wrestler_relationships GROUP BY weight_class")
        counts = cursor.fetchall()
        
        click.echo("\nRelationship counts by weight class:")
        for row in counts:
            click.echo(f"  {row['weight_class']}: {row['count']} relationships")
    finally:
        sqlite_db.close_db()

@main.command()
@click.argument('weight_class')
def fix_relationship_weight_classes(weight_class):
    """Fix weight classes in the relationships table."""
    sqlite_db.init_db()
    
    try:
        cursor = sqlite_db.conn.cursor()
        
        # Update all relationships for wrestlers in this weight class
        cursor.execute(
            """
            UPDATE wrestler_relationships
            SET weight_class = ?
            WHERE wrestler1_id IN (
                SELECT external_id FROM wrestlers WHERE weight_class = ?
            )
            AND wrestler2_id IN (
                SELECT external_id FROM wrestlers WHERE weight_class = ?
            )
            """,
            (weight_class, weight_class, weight_class)
        )
        
        count = cursor.rowcount
        sqlite_db.conn.commit()
        
        click.echo(f"Updated {count} relationships to weight class '{weight_class}'")
    finally:
        sqlite_db.close_db()

@main.command()
@click.argument('weight_class')
@click.argument('wrestler1_id')
@click.argument('wrestler2_id')
def debug_relationship(weight_class, wrestler1_id, wrestler2_id):
    """Debug relationship between two wrestlers."""
    from wrestlerank.matrix import relationship_manager
    
    click.echo(f"Debugging relationship for {wrestler1_id} vs {wrestler2_id} in {weight_class}...")
    
    # Create a test relationship
    relationship_manager.update_direct_relationship(
        wrestler1_id, wrestler2_id, weight_class
    )
    
    # Check if it was created
    sqlite_db.init_db()
    cursor = sqlite_db.conn.cursor()
    cursor.execute(
        """
        SELECT * FROM wrestler_relationships
        WHERE wrestler1_id = ? AND wrestler2_id = ?
        """,
        (wrestler1_id, wrestler2_id)
    )
    rel = cursor.fetchone()
    
    if rel:
        click.echo(f"Relationship found: {rel['wrestler1_id']} vs {rel['wrestler2_id']}")
        click.echo(f"  Direct wins: {rel['direct_wins']}, Direct losses: {rel['direct_losses']}")
        click.echo(f"  Weight class: {rel['weight_class']}")
    else:
        click.echo(f"No relationship found between {wrestler1_id} and {wrestler2_id}")
    
    sqlite_db.close_db()

@main.command()
@click.argument('csv_file', type=click.Path(exists=True))
@click.option('--weight-class', help='Override weight class from filename')
def import_rankings(csv_file, weight_class):
    """Import wrestler rankings from a CSV file."""
    # Parse filename to get weight class and date
    import os
    import re
    import csv
    from datetime import datetime
    
    filename = os.path.basename(csv_file)
    match = re.match(r'rankings-([^-]+)-(.+)\.csv', filename)
    
    if not match and not weight_class:
        click.echo(f"Error: File name format should be 'rankings-<weight>-<date>.csv', got '{filename}'")
        click.echo("Or provide --weight-class option to override")
        return
        
    if weight_class:
        click.echo(f"Using provided weight class: {weight_class}")
    else:
        weight_class = match.group(1)
        
    if match:
        date_str = match.group(2)
    else:
        date_str = datetime.now().strftime('%Y%m%d')
    
    # Convert date format if needed
    try:
        date = datetime.strptime(date_str, '%Y%m%d').strftime('%Y-%m-%d')
    except ValueError:
        date = date_str  # Use as-is if not in expected format
    
    click.echo(f"Importing rankings for {weight_class} from {date}")
    
    # Read CSV file and determine column names
    with open(csv_file, 'r', newline='') as f:
        # Try to detect the delimiter
        sample = f.read(1024)
        f.seek(0)
        
        if '\t' in sample:
            delimiter = '\t'
        elif ',' in sample:
            delimiter = ','
        else:
            delimiter = None  # Let csv.Sniffer figure it out
            
        # Read the header to determine column names
        reader = csv.reader(f, delimiter=delimiter)
        header = next(reader)
        
        # Map expected column names to actual column names
        wrestler_id_col = None
        name_col = None
        rank_col = None
        
        for i, col in enumerate(header):
            col_lower = col.lower()
            if col_lower in ('wrestlerid', 'wrestler_id', 'id'):
                wrestler_id_col = i
            elif col_lower in ('name', 'wrestler', 'wrestler_name'):
                name_col = i
            elif col_lower in ('rank', 'ranking'):
                rank_col = i
        
        if wrestler_id_col is None or name_col is None or rank_col is None:
            click.echo(f"Error: Could not identify required columns in CSV. Header: {header}")
            return
            
        # Read the rankings
        rankings = []
        for row in reader:
            if len(row) > max(wrestler_id_col, name_col, rank_col):
                rankings.append({
                    'wrestler_id': row[wrestler_id_col],
                    'name': row[name_col],
                    'rank': int(row[rank_col])
                })
    
    click.echo(f"Found {len(rankings)} rankings in CSV file")
    
    # Insert into database
    sqlite_db.init_db()
    try:
        cursor = sqlite_db.conn.cursor()
        now = datetime.now().isoformat()
        
        # Clear existing rankings for this weight class and date
        cursor.execute(
            "DELETE FROM wrestler_rankings WHERE weight_class = ? AND date = ?",
            (weight_class, date)
        )
        
        # Insert new rankings
        for ranking in rankings:
            cursor.execute(
                """
                INSERT INTO wrestler_rankings 
                (wrestler_id, weight_class, rank, date, last_updated)
                VALUES (?, ?, ?, ?, ?)
                """,
                (ranking['wrestler_id'], weight_class, ranking['rank'], date, now)
            )
        
        sqlite_db.conn.commit()
        click.echo(f"Imported {len(rankings)} rankings for {weight_class}")
    finally:
        sqlite_db.close_db()

@main.command()
@click.argument('weight_class')
def fix_common_opponent_inconsistencies(weight_class):
    """Fix inconsistent common opponent relationships in a weight class."""
    click.echo(f"Fixing inconsistent common opponent relationships for {weight_class}...")
    
    sqlite_db.init_db()
    
    try:
        cursor = sqlite_db.conn.cursor()
        
        # Find all wrestlers in this weight class
        cursor.execute(
            """
            SELECT external_id, name FROM wrestlers
            WHERE weight_class = ? AND active_team = 1
            """,
            (weight_class,)
        )
        wrestlers = cursor.fetchall()
        wrestler_ids = [w['external_id'] for w in wrestlers]
        
        click.echo(f"Found {len(wrestlers)} wrestlers in {weight_class}")
        
        # Find inconsistent relationships where both wrestlers have common opponent losses to each other
        inconsistencies = []
        
        for i, w1 in enumerate(wrestler_ids):
            for w2 in wrestler_ids[i+1:]:  # Only check each pair once
                # Check relationship from w1 to w2
                cursor.execute(
                    """
                    SELECT common_opp_wins, common_opp_losses FROM wrestler_relationships
                    WHERE wrestler1_id = ? AND wrestler2_id = ? AND weight_class = ?
                    """,
                    (w1, w2, weight_class)
                )
                rel_1_to_2 = cursor.fetchone()
                
                # Check relationship from w2 to w1
                cursor.execute(
                    """
                    SELECT common_opp_wins, common_opp_losses FROM wrestler_relationships
                    WHERE wrestler1_id = ? AND wrestler2_id = ? AND weight_class = ?
                    """,
                    (w2, w1, weight_class)
                )
                rel_2_to_1 = cursor.fetchone()
                
                # Skip if either relationship doesn't exist
                if not rel_1_to_2 or not rel_2_to_1:
                    continue
                
                # Check for inconsistency: both have common opponent losses to each other
                if rel_1_to_2['common_opp_losses'] > rel_1_to_2['common_opp_wins'] and \
                   rel_2_to_1['common_opp_losses'] > rel_2_to_1['common_opp_wins']:
                    # Get wrestler names for better reporting
                    w1_name = next(w['name'] for w in wrestlers if w['external_id'] == w1)
                    w2_name = next(w['name'] for w in wrestlers if w['external_id'] == w2)
                    
                    inconsistencies.append({
                        'w1_id': w1,
                        'w2_id': w2,
                        'w1_name': w1_name,
                        'w2_name': w2_name
                    })
        
        click.echo(f"Found {len(inconsistencies)} inconsistent relationships")
        
        # Fix the inconsistencies
        for inc in inconsistencies:
            click.echo(f"Fixing relationship between {inc['w1_name']} and {inc['w2_name']}")
            
            # Clear both relationships
            cursor.execute(
                """
                UPDATE wrestler_relationships
                SET common_opp_wins = 0, common_opp_losses = 0
                WHERE (wrestler1_id = ? AND wrestler2_id = ?) OR (wrestler1_id = ? AND wrestler2_id = ?)
                """,
                (inc['w1_id'], inc['w2_id'], inc['w2_id'], inc['w1_id'])
            )
            
            # Also clear any common opponent paths
            cursor.execute(
                """
                DELETE FROM common_opponent_paths
                WHERE (wrestler1_id = ? AND wrestler2_id = ?) OR (wrestler1_id = ? AND wrestler2_id = ?)
                """,
                (inc['w1_id'], inc['w2_id'], inc['w2_id'], inc['w1_id'])
            )
        
        sqlite_db.conn.commit()
        click.echo("Fixed all inconsistent relationships")
        
    finally:
        sqlite_db.close_db()

@main.command()
@click.option('--force', is_flag=True, help='Force reset without confirmation')
def reset_relationships(force):
    """Reset all wrestler relationships in the database."""
    if not force:
        if not click.confirm("This will delete ALL relationship data. Are you sure?"):
            click.echo("Operation cancelled.")
            return
    
    sqlite_db.init_db()
    
    try:
        cursor = sqlite_db.conn.cursor()
        
        # Delete all relationships
        cursor.execute("DELETE FROM wrestler_relationships")
        rel_count = cursor.rowcount
        
        # Delete all common opponent paths
        cursor.execute("DELETE FROM common_opponent_paths")
        path_count = cursor.rowcount
        
        sqlite_db.conn.commit()
        
        click.echo(f"Deleted {rel_count} relationships and {path_count} common opponent paths")
        click.echo("All relationships have been reset. Run 'build-relationships' to rebuild them.")
        
    finally:
        sqlite_db.close_db()

@main.command()
@click.argument('query')
def run_sql(query):
    """Run a SQL query directly on the database."""
    sqlite_db.init_db()
    
    try:
        cursor = sqlite_db.conn.cursor()
        cursor.execute(query)
        results = cursor.fetchall()
        
        # Print results
        if results:
            # Print column headers
            headers = list(results[0].keys())
            print(" | ".join(headers))
            print("-" * (sum(len(h) for h in headers) + 3 * (len(headers) - 1)))
            
            # Print rows
            for row in results:
                print(" | ".join(str(row[h]) for h in headers))
            
            print(f"\n{len(results)} rows returned")
        else:
            print("No results returned")
            
    except Exception as e:
        print(f"Error executing query: {e}")
    finally:
        sqlite_db.close_db()


@main.command()
@click.argument('data_json', type=str)
def save_rankings(data_json):
    """Save rankings from the matrix UI."""
    import json
    data = json.loads(data_json)
    
    weight_class = data.get('weight_class')
    rankings = data.get('rankings', [])
    
    if not weight_class or not rankings:
        click.echo(json.dumps({'success': False, 'error': 'Missing weight class or rankings data'}))
        return
    
    sqlite_db.init_db()
    
    try:
        cursor = sqlite_db.conn.cursor()
        
        # Get the current date for the ranking
        now = datetime.now().isoformat()
        today = now.split('T')[0]  # Just the date part
        
        # First, check if rankings already exist for today
        cursor.execute(
            """
            SELECT COUNT(*) as count FROM wrestler_rankings
            WHERE weight_class = ? AND date = ?
            """,
            (weight_class, today)
        )
        
        # If rankings exist, delete them first
        if cursor.fetchone()['count'] > 0:
            cursor.execute(
                """
                DELETE FROM wrestler_rankings
                WHERE weight_class = ? AND date = ?
                """,
                (weight_class, today)
            )
        
        # Insert the new rankings
        for ranking in rankings:
            wrestler_id = ranking.get('wrestler_id')
            rank = ranking.get('rank')
            
            cursor.execute(
                """
                INSERT INTO wrestler_rankings
                (wrestler_id, weight_class, rank, date, last_updated)
                VALUES (?, ?, ?, ?, ?)
                """,
                (wrestler_id, weight_class, rank, today, now)
            )
        
        sqlite_db.conn.commit()
        click.echo(json.dumps({'success': True}))
        
    except Exception as e:
        click.echo(json.dumps({'success': False, 'error': str(e)}))
    finally:
        sqlite_db.close_db()

@main.command()
@click.argument('query', required=False)
def diagnose_matches(query=None):
    """Diagnose issues with match processing."""
    click.echo("Diagnosing match processing status...")
    
    sqlite_db.init_db()
    
    try:
        cursor = sqlite_db.conn.cursor()
        
        # Check if the processed column exists
        cursor.execute("PRAGMA table_info(matches)")
        columns = cursor.fetchall()
        has_processed = any(col['name'] == 'processed' for col in columns)
        
        if not has_processed:
            click.echo("The 'processed' column does not exist in the matches table!")
            return
        
        # Count total matches
        cursor.execute("SELECT COUNT(*) as count FROM matches")
        total_count = cursor.fetchone()['count']
        click.echo(f"Total matches in database: {total_count}")
        
        # Count processed matches
        cursor.execute("SELECT COUNT(*) as count FROM matches WHERE processed = 1")
        processed_count = cursor.fetchone()['count']
        click.echo(f"Matches marked as processed: {processed_count}")
        
        # Count unprocessed matches
        cursor.execute("SELECT COUNT(*) as count FROM matches WHERE processed = 0 OR processed IS NULL")
        unprocessed_count = cursor.fetchone()['count']
        click.echo(f"Matches marked as unprocessed or NULL: {unprocessed_count}")
        
        # Count NULL processed values
        cursor.execute("SELECT COUNT(*) as count FROM matches WHERE processed IS NULL")
        null_count = cursor.fetchone()['count']
        click.echo(f"Matches with NULL processed value: {null_count}")
        
        # Run a custom query if provided
        if query:
            click.echo(f"\nRunning custom query: {query}")
            cursor.execute(query)
            results = cursor.fetchall()
            
            if results:
                # Print column headers
                headers = list(results[0].keys())
                click.echo(" | ".join(headers))
                click.echo("-" * (sum(len(h) for h in headers) + 3 * (len(headers) - 1)))
                
                # Print rows (limit to first 20)
                for row in results[:20]:
                    click.echo(" | ".join(str(row[h]) for h in headers))
                
                if len(results) > 20:
                    click.echo(f"... and {len(results) - 20} more rows")
                
                click.echo(f"\n{len(results)} rows returned")
            else:
                click.echo("No results returned")
                
    except Exception as e:
        click.echo(f"Error diagnosing matches: {e}")
    finally:
        sqlite_db.close_db()

@main.command()
@click.argument('weight_class')
@click.option('--algorithm', default='optimal',
              help='Name of the optimization algorithm')
def optimize_ranking(weight_class, algorithm):
    """
    Generate optimal rankings for a weight class using advanced algorithms.
    
    This command uses the sophisticated optimization techniques from the legacy
    system to minimize ranking anomalies. It combines PageRank, MFAS, Simulated
    Annealing, and Local Search to find the best possible ranking.
    """
    click.echo(f"Generating optimal rankings for weight class {weight_class}...")
    
    from wrestlerank.ranking.optimal_ranker import OptimalRanker
    
    # Initialize the ranker
    ranker = OptimalRanker(weight_class)
    
    # Load data from database
    if not ranker.load_data_from_db():
        click.echo("Failed to load data. Aborting.")
        return
    
    # Run the optimization process
    start_time = time.time()
    ranker.run_optimization()
    end_time = time.time()
    
    click.echo(f"Optimization completed in {end_time - start_time:.2f} seconds")
    click.echo(f"Final anomaly score: {ranker.best_score}")
    
    # Save the rankings to the database
    if ranker.save_rankings_to_db(algorithm):
        click.echo("Rankings saved to database successfully!")
    else:
        click.echo("Failed to save rankings to database.")

if __name__ == '__main__':
    main()
