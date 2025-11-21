def fix_wrestler_rankings_ids():
    """Fix wrestler_rankings table to use external_id instead of database id."""
    conn = sqlite_db.conn
    cursor = conn.cursor()
    
    print("Checking for rankings with incorrect ID format...")
    
    # First, check if there are any rankings that use database IDs instead of external IDs
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM wrestler_rankings wr
        JOIN wrestlers w ON wr.wrestler_id = w.id
    """)
    
    count = cursor.fetchone()['count']
    
    if count > 0:
        print(f"Found {count} rankings using database IDs instead of external IDs")
        
        # Begin transaction
        cursor.execute("BEGIN TRANSACTION")
        
        try:
            # Create a temporary table to store the mappings
            cursor.execute("""
                CREATE TEMPORARY TABLE id_mappings AS
                SELECT wr.id as ranking_id, w.external_id as external_id
                FROM wrestler_rankings wr
                JOIN wrestlers w ON wr.wrestler_id = w.id
            """)
            
            # Update the wrestler_rankings table
            cursor.execute("""
                UPDATE wrestler_rankings
                SET wrestler_id = (
                    SELECT external_id
                    FROM id_mappings
                    WHERE id_mappings.ranking_id = wrestler_rankings.id
                )
                WHERE id IN (SELECT ranking_id FROM id_mappings)
            """)
            
            # Drop the temporary table
            cursor.execute("DROP TABLE id_mappings")
            
            # Commit the changes
            conn.commit()
            print(f"Successfully updated {count} rankings to use external IDs")
            
        except Exception as e:
            conn.rollback()
            print(f"Error fixing wrestler rankings IDs: {e}")
    else:
        print("No rankings found using incorrect ID format")

def run_migrations():
    """Run all necessary database migrations."""
    print("Running database migrations...")
    
    # Initialize database connection
    sqlite_db.init_db()
    
    try:
        # Run migrations in order
        add_algorithm_column()
        fix_wrestler_rankings_ids()
        
        print("Database migrations completed successfully.")
    finally:
        sqlite_db.close_db() 