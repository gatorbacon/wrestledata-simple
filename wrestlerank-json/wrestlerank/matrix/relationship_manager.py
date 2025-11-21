"""
Relationship manager for wrestling head-to-head matrix.

This module handles the calculation and maintenance of wrestler relationships,
including direct matches and common opponent comparisons.
"""

from datetime import datetime
from wrestlerank.db import sqlite_db
from tqdm import tqdm

def update_direct_relationship(winner_id, loser_id, weight_class, match_id=None, existing_connection=False):
    """
    Update the direct relationship when a match occurs.
    
    Args:
        winner_id: External ID of winner
        loser_id: External ID of loser
        weight_class: Weight class of the match
        match_id: External ID of the match (optional)
        existing_connection: Whether to use an existing connection (True) or create a new one (False)
    """
    # Keep track of whether we created a new connection
    connection_created = False
    
    try:
        if not existing_connection:
            sqlite_db.init_db()
            connection_created = True
        
        # Update winner's record against loser
        _update_or_create_relationship(
            wrestler1_id=winner_id,
            wrestler2_id=loser_id,
            weight_class=weight_class,
            direct_wins=1,
            direct_losses=0
        )
        
        # Update loser's record against winner
        _update_or_create_relationship(
            wrestler1_id=loser_id,
            wrestler2_id=winner_id,
            weight_class=weight_class,
            direct_wins=0,
            direct_losses=1
        )
        
        # Now the important part: propagate common opponent relationships
        propagate_common_opponent_relationships(winner_id, loser_id, weight_class, match_id)
    except Exception as e:
        # If we created a connection and an error occurs, ensure we close it
        if connection_created:
            sqlite_db.close_db()
        # Re-raise the exception
        raise e
    finally:
        # Only close the connection if we created it and haven't already closed it
        if connection_created:
            sqlite_db.close_db()

def _update_or_create_relationship(wrestler1_id, wrestler2_id, weight_class, direct_wins=0, direct_losses=0, common_opp_wins=0, common_opp_losses=0):
    """
    Update or create a relationship between two wrestlers.
    
    Args:
        wrestler1_id: External ID of first wrestler
        wrestler2_id: External ID of second wrestler
        weight_class: Weight class of the match
        direct_wins: Number of direct wins to add
        direct_losses: Number of direct losses to add
        common_opp_wins: Number of common opponent wins to add
        common_opp_losses: Number of common opponent losses to add
    """
    cursor = sqlite_db.conn.cursor()
    now = datetime.now().isoformat()
    
    # Check if relationship exists
    cursor.execute(
        """
        SELECT * FROM wrestler_relationships
        WHERE wrestler1_id = ? AND wrestler2_id = ? AND weight_class = ?
        """,
        (wrestler1_id, wrestler2_id, weight_class)
    )
    
    relationship = cursor.fetchone()
    
    if relationship:
        # Update existing relationship
        cursor.execute(
            """
            UPDATE wrestler_relationships
            SET direct_wins = direct_wins + ?,
                direct_losses = direct_losses + ?,
                common_opp_wins = common_opp_wins + ?,
                common_opp_losses = common_opp_losses + ?,
                last_updated = ?
            WHERE wrestler1_id = ? AND wrestler2_id = ? AND weight_class = ?
            """,
            (direct_wins, direct_losses, common_opp_wins, common_opp_losses, now, wrestler1_id, wrestler2_id, weight_class)
        )
    else:
        # Create new relationship
        cursor.execute(
            """
            INSERT INTO wrestler_relationships
            (wrestler1_id, wrestler2_id, direct_wins, direct_losses, common_opp_wins, common_opp_losses, weight_class, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (wrestler1_id, wrestler2_id, direct_wins, direct_losses, common_opp_wins, common_opp_losses, weight_class, now)
        )
    
    sqlite_db.conn.commit()

def propagate_common_opponent_relationships(winner_id, loser_id, weight_class, match_id):
    """
    Propagate common opponent relationships when a new match occurs.
    
    Args:
        winner_id: External ID of the winner
        loser_id: External ID of the loser
        weight_class: Weight class of the match
        match_id: External ID of the match
    """
    cursor = sqlite_db.conn.cursor()
    
    # 1. Everyone who beat the winner gets a common opponent win over the loser
    # First, find all previous matches where someone beat the winner
    cursor.execute(
        """
        SELECT external_id, wrestler1_id, date
        FROM matches
        WHERE wrestler2_id = ? AND winner_id = wrestler1_id
        """,
        (winner_id,)
    )
    
    for row in cursor.fetchall():
        who_beat_winner = row['wrestler1_id']
        previous_match_id = row['external_id']
        
        # Skip if direct relationship exists
        if _has_direct_relationship(who_beat_winner, loser_id, weight_class):
            continue
            
        # Update the common opponent wins directly in the database
        cursor.execute(
            """
            UPDATE wrestler_relationships
            SET common_opp_wins = common_opp_wins + 1
            WHERE wrestler1_id = ? AND wrestler2_id = ? AND weight_class = ?
            """,
            (who_beat_winner, loser_id, weight_class)
        )
        
        # If no rows were updated, create a new relationship
        if cursor.rowcount == 0:
            cursor.execute(
                """
                INSERT INTO wrestler_relationships
                (wrestler1_id, wrestler2_id, direct_wins, direct_losses, common_opp_wins, common_opp_losses, weight_class, last_updated)
                VALUES (?, ?, 0, 0, 1, 0, ?, ?)
                """,
                (who_beat_winner, loser_id, weight_class, datetime.now().isoformat())
            )
        
        # Record the common opponent path
        add_common_opponent_path(
            wrestler1_id=who_beat_winner,
            wrestler2_id=loser_id,
            common_opponent_id=winner_id,
            match1_id=previous_match_id,
            match2_id=match_id,
            weight_class=weight_class
        )
    
    # 2. The winner gets a common opponent win over everyone who lost to the loser
    cursor.execute(
        """
        SELECT wrestler1_id FROM wrestler_relationships 
        WHERE wrestler2_id = ? AND weight_class = ? AND direct_losses > direct_wins
        """, 
        (loser_id, weight_class)
    )
    
    for row in cursor.fetchall():
        who_lost_to_loser = row['wrestler1_id']
        # Skip if direct relationship exists
        if _has_direct_relationship(winner_id, who_lost_to_loser, weight_class):
            continue
        _update_or_create_relationship(
            wrestler1_id=winner_id,
            wrestler2_id=who_lost_to_loser,
            weight_class=weight_class,
            common_opp_wins=1
        )
    
    # 3. Everyone who lost to the winner gets a common opponent loss to the loser
    cursor.execute(
        """
        SELECT wrestler1_id FROM wrestler_relationships 
        WHERE wrestler2_id = ? AND weight_class = ? AND direct_losses > direct_wins
        """, 
        (winner_id, weight_class)
    )
    
    for row in cursor.fetchall():
        who_lost_to_winner = row['wrestler1_id']
        # Skip if direct relationship exists
        if _has_direct_relationship(who_lost_to_winner, loser_id, weight_class):
            continue
        _update_or_create_relationship(
            wrestler1_id=who_lost_to_winner,
            wrestler2_id=loser_id,
            weight_class=weight_class,
            common_opp_losses=1
        )
    
    # 4. The loser gets a common opponent loss to everyone who beat the winner
    cursor.execute(
        """
        SELECT wrestler2_id FROM wrestler_relationships 
        WHERE wrestler1_id = ? AND weight_class = ? AND direct_wins > direct_losses
        """, 
        (winner_id, weight_class)
    )
    
    for row in cursor.fetchall():
        who_was_beaten_by_winner = row['wrestler2_id']
        # Skip if direct relationship exists
        if _has_direct_relationship(loser_id, who_was_beaten_by_winner, weight_class):
            continue
        _update_or_create_relationship(
            wrestler1_id=loser_id,
            wrestler2_id=who_was_beaten_by_winner,
            weight_class=weight_class,
            common_opp_losses=1
        )
    
    sqlite_db.conn.commit()

def _has_direct_relationship(wrestler1_id, wrestler2_id, weight_class):
    """Check if a direct relationship exists between wrestlers."""
    cursor = sqlite_db.conn.cursor()
    cursor.execute(
        """
        SELECT COUNT(*) as count FROM wrestler_relationships 
        WHERE wrestler1_id = ? AND wrestler2_id = ? AND weight_class = ? 
        AND (direct_wins > 0 OR direct_losses > 0)
        """,
        (wrestler1_id, wrestler2_id, weight_class)
    )
    return cursor.fetchone()['count'] > 0

def get_matrix_for_weight_class(weight_class):
    """
    Get the head-to-head matrix for a weight class.
    
    Returns:
        dict: A dictionary mapping (wrestler1_id, wrestler2_id) to relationship
    """
    # This function would efficiently build the matrix from the relationship table
    # Implementation details depend on how you want to render the matrix
    pass 

def add_common_opponent_path(wrestler1_id, wrestler2_id, common_opponent_id, match1_id, match2_id, weight_class):
    """
    Record a common opponent path between two wrestlers.
    
    Args:
        wrestler1_id: External ID of first wrestler (who has the advantage)
        wrestler2_id: External ID of second wrestler
        common_opponent_id: External ID of the common opponent
        match1_id: External ID of first match (wrestler1 vs common opponent)
        match2_id: External ID of second match (common opponent vs wrestler2)
        weight_class: Weight class of the matches
    """
    cursor = sqlite_db.conn.cursor()
    now = datetime.now().isoformat()
    
    # Check if path already exists
    cursor.execute(
        """
        SELECT COUNT(*) as count FROM common_opponent_paths
        WHERE wrestler1_id = ? AND wrestler2_id = ? AND common_opponent_id = ?
        AND match1_id = ? AND match2_id = ?
        """,
        (wrestler1_id, wrestler2_id, common_opponent_id, match1_id, match2_id)
    )
    
    if cursor.fetchone()['count'] == 0:
        # Insert new path
        cursor.execute(
            """
            INSERT INTO common_opponent_paths
            (wrestler1_id, wrestler2_id, common_opponent_id, match1_id, match2_id, weight_class)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (wrestler1_id, wrestler2_id, common_opponent_id, match1_id, match2_id, weight_class)
        )
        sqlite_db.conn.commit() 

def update_common_opponent_relationships(wrestler1_id, wrestler2_id, weight_class, existing_connection=False):
    """Update common opponent relationships between two wrestlers."""
    if not existing_connection:
        sqlite_db.init_db()
    
    try:
        cursor = sqlite_db.conn.cursor()
        
        # Get matches for both wrestlers
        cursor.execute(
            """
            SELECT * FROM matches 
            WHERE (wrestler1_id = ? OR wrestler2_id = ?) 
            AND weight_class = ?
            """,
            (wrestler1_id, wrestler1_id, weight_class)
        )
        wrestler1_matches = cursor.fetchall()
        
        cursor.execute(
            """
            SELECT * FROM matches 
            WHERE (wrestler1_id = ? OR wrestler2_id = ?) 
            AND weight_class = ?
            """,
            (wrestler2_id, wrestler2_id, weight_class)
        )
        wrestler2_matches = cursor.fetchall()
        
        # Find common opponents
        wrestler1_opponents = set()
        for match in wrestler1_matches:
            if match['wrestler1_id'] == wrestler1_id:
                wrestler1_opponents.add(match['wrestler2_id'])
            else:
                wrestler1_opponents.add(match['wrestler1_id'])
                
        wrestler2_opponents = set()
        for match in wrestler2_matches:
            if match['wrestler1_id'] == wrestler2_id:
                wrestler2_opponents.add(match['wrestler2_id'])
            else:
                wrestler2_opponents.add(match['wrestler1_id'])
                
        common_opponents = wrestler1_opponents.intersection(wrestler2_opponents)
        
        # Count wins and losses against common opponents
        common_opp_wins = 0
        common_opp_losses = 0
        
        # Track paths for each common opponent
        paths = []
        
        for opponent_id in common_opponents:
            # Skip if the opponent is one of the wrestlers we're comparing
            if opponent_id in (wrestler1_id, wrestler2_id):
                continue
                
            # Find wrestler1's best result against this opponent
            wrestler1_won = False
            wrestler1_match_id = None
            
            for match in wrestler1_matches:
                if (match['wrestler1_id'] == wrestler1_id and match['wrestler2_id'] == opponent_id) or \
                   (match['wrestler1_id'] == opponent_id and match['wrestler2_id'] == wrestler1_id):
                    if match['winner_id'] == wrestler1_id:
                        wrestler1_won = True
                        wrestler1_match_id = match['external_id']
                        break
            
            # Find wrestler2's best result against this opponent
            wrestler2_won = False
            wrestler2_match_id = None
            
            for match in wrestler2_matches:
                if (match['wrestler1_id'] == wrestler2_id and match['wrestler2_id'] == opponent_id) or \
                   (match['wrestler1_id'] == opponent_id and match['wrestler2_id'] == wrestler2_id):
                    if match['winner_id'] == wrestler2_id:
                        wrestler2_won = True
                        wrestler2_match_id = match['external_id']
                        break
            
            # Only count if the results are different (one won, one lost)
            # This ensures logical consistency
            if wrestler1_won and not wrestler2_won:
                common_opp_wins += 1
                
                # Store the path if we have both match IDs
                if wrestler1_match_id and wrestler2_match_id:
                    paths.append({
                        'common_opponent_id': opponent_id,
                        'match1_id': wrestler1_match_id,
                        'match2_id': wrestler2_match_id
                    })
                    
            elif not wrestler1_won and wrestler2_won:
                common_opp_losses += 1
        
        # Update the relationship in the database
        now = datetime.now().isoformat()
        
        cursor.execute(
            """
            INSERT INTO wrestler_relationships 
            (wrestler1_id, wrestler2_id, direct_wins, direct_losses, 
             common_opp_wins, common_opp_losses, weight_class, last_updated)
            VALUES (?, ?, 0, 0, ?, ?, ?, ?)
            ON CONFLICT(wrestler1_id, wrestler2_id, weight_class) 
            DO UPDATE SET
                common_opp_wins = ?,
                common_opp_losses = ?,
                last_updated = ?
            """,
            (wrestler1_id, wrestler2_id, common_opp_wins, common_opp_losses, 
             weight_class, now, common_opp_wins, common_opp_losses, now)
        )
        
        # Also update the reverse relationship to ensure consistency
        cursor.execute(
            """
            INSERT INTO wrestler_relationships 
            (wrestler1_id, wrestler2_id, direct_wins, direct_losses, 
             common_opp_wins, common_opp_losses, weight_class, last_updated)
            VALUES (?, ?, 0, 0, ?, ?, ?, ?)
            ON CONFLICT(wrestler1_id, wrestler2_id, weight_class) 
            DO UPDATE SET
                common_opp_wins = ?,
                common_opp_losses = ?,
                last_updated = ?
            """,
            (wrestler2_id, wrestler1_id, common_opp_losses, common_opp_wins, 
             weight_class, now, common_opp_losses, common_opp_wins, now)
        )
        
        # Store the common opponent paths
        for path in paths:
            cursor.execute(
                """
                INSERT OR IGNORE INTO common_opponent_paths
                (wrestler1_id, wrestler2_id, common_opponent_id, match1_id, match2_id, weight_class)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (wrestler1_id, wrestler2_id, path['common_opponent_id'], 
                 path['match1_id'], path['match2_id'], weight_class)
            )
        
        sqlite_db.conn.commit()
        
    finally:
        if not existing_connection:
            sqlite_db.close_db()

def build_weight_class_relationships(weight_class, adjacent_classes=None, limit=0):
    """
    Build all relationships for a weight class.
    
    Args:
        weight_class: The weight class to build relationships for
        adjacent_classes: List of adjacent weight classes to include
        limit: Maximum number of matches to process (0 for all)
    """
    sqlite_db.init_db()
    
    try:
        cursor = sqlite_db.conn.cursor()
        
        # Clear existing relationships for this weight class
        print(f"Clearing existing relationships for {weight_class}...")
        cursor.execute(
            """
            DELETE FROM wrestler_relationships
            WHERE weight_class = ? AND wrestler1_id IN (
                SELECT external_id FROM wrestlers WHERE weight_class = ?
            )
            """,
            (weight_class, weight_class)
        )
        
        cursor.execute(
            """
            DELETE FROM common_opponent_paths
            WHERE weight_class = ? AND wrestler1_id IN (
                SELECT external_id FROM wrestlers WHERE weight_class = ?
            )
            """,
            (weight_class, weight_class)
        )
        
        # Get matches for this weight class and adjacent classes
        weight_classes = [weight_class]
        if adjacent_classes:
            weight_classes.extend(adjacent_classes)
            
        weight_class_str = ", ".join([f"'{wc}'" for wc in weight_classes])
        print(f"Processing {limit if limit > 0 else 'all'} matches from weight classes: {', '.join(weight_classes)}...")
        
        cursor.execute(
            f"""
            SELECT * FROM matches 
            WHERE weight_class IN ({weight_class_str})
            ORDER BY date DESC
            {f"LIMIT {limit}" if limit > 0 else ""}
            """
        )
        
        matches = cursor.fetchall()
        print(f"Found {len(matches)} matches to process")
        
        # Process each match to build direct relationships
        print("Building direct relationships...")
        for match in tqdm(matches):
            # Skip matches with no winner
            if not match['winner_id']:
                continue
                
            # Determine loser
            loser_id = match['wrestler1_id'] if match['winner_id'] == match['wrestler2_id'] else match['wrestler2_id']
            
            # Update direct relationship directly
            now = datetime.now().isoformat()
            
            # Update winner's record against loser
            cursor.execute(
                """
                INSERT INTO wrestler_relationships
                (wrestler1_id, wrestler2_id, direct_wins, direct_losses, common_opp_wins, common_opp_losses, weight_class, last_updated)
                VALUES (?, ?, 1, 0, 0, 0, ?, ?)
                ON CONFLICT(wrestler1_id, wrestler2_id, weight_class) 
                DO UPDATE SET
                    direct_wins = direct_wins + 1,
                    last_updated = ?
                """,
                (match['winner_id'], loser_id, weight_class, now, now)
            )
            
            # Update loser's record against winner
            cursor.execute(
                """
                INSERT INTO wrestler_relationships
                (wrestler1_id, wrestler2_id, direct_wins, direct_losses, common_opp_wins, common_opp_losses, weight_class, last_updated)
                VALUES (?, ?, 0, 1, 0, 0, ?, ?)
                ON CONFLICT(wrestler1_id, wrestler2_id, weight_class) 
                DO UPDATE SET
                    direct_losses = direct_losses + 1,
                    last_updated = ?
                """,
                (loser_id, match['winner_id'], weight_class, now, now)
            )
        
        # Commit after processing all matches
        sqlite_db.conn.commit()
        print("Direct relationships built successfully")
        
        # Now build common opponent relationships for all wrestlers in this weight class
        cursor.execute(
            """
            SELECT external_id FROM wrestlers
            WHERE weight_class = ? AND active_team = 1
            """,
            (weight_class,)
        )
        
        wrestlers = [row['external_id'] for row in cursor.fetchall()]
        
        # Build all pairwise relationships
        total_pairs = len(wrestlers) * (len(wrestlers) - 1) // 2
        print(f"Building common opponent relationships for {len(wrestlers)} wrestlers ({total_pairs} potential pairs)...")
        
        # Use tqdm for progress bar
        progress_bar = tqdm(total=total_pairs, desc="Processing wrestler pairs")
        
        pair_count = 0
        co_relationships_found = 0
        
        for i, w1 in enumerate(wrestlers):
            for w2 in wrestlers[i+1:]:  # Only process each pair once
                pair_count += 1
                
                # Update progress every 100 pairs
                if pair_count % 100 == 0:
                    progress_bar.update(100)
                    
                # Skip if direct relationship exists
                cursor.execute(
                    """
                    SELECT COUNT(*) as count FROM wrestler_relationships
                    WHERE wrestler1_id = ? AND wrestler2_id = ? AND weight_class = ?
                    AND (direct_wins > 0 OR direct_losses > 0)
                    """,
                    (w1, w2, weight_class)
                )
                
                if cursor.fetchone()['count'] == 0:
                    # No direct relationship, calculate common opponent relationship
                    update_common_opponent_relationships(w1, w2, weight_class, existing_connection=True)
                    co_relationships_found += 1
                    
                    # Print status update every 50 common opponent relationships found
                    if co_relationships_found % 50 == 0:
                        print(f"  Found {co_relationships_found} common opponent relationships so far...")
        
        # Update progress bar to completion
        progress_bar.update(total_pairs - progress_bar.n)
        progress_bar.close()
        
        print(f"Found a total of {co_relationships_found} common opponent relationships")
        sqlite_db.conn.commit()
        print("All relationships built successfully!")
        
    finally:
        sqlite_db.close_db() 