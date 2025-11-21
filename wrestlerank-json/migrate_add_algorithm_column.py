import sqlite3

def add_algorithm_column(db_path='wrestlerank.db'):
    """Add the algorithm column to the wrestler_rankings table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Add the algorithm column if it doesn't exist
        cursor.execute("ALTER TABLE wrestler_rankings ADD COLUMN algorithm TEXT")
        conn.commit()
        print("Successfully added 'algorithm' column to 'wrestler_rankings' table.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("'algorithm' column already exists.")
        else:
            print(f"Error adding 'algorithm' column: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    add_algorithm_column() 