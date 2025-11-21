import sqlite3
import os

# Initialize the database connection
db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wrestlerank.db')), 'wrestlerank.db')
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

try:
    # Get the schema of the wrestler_rankings table
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(wrestler_rankings)")
    columns = cursor.fetchall()
    
    print("Columns in wrestler_rankings table:")
    for col in columns:
        print(f"  {col['name']} ({col['type']}) {'NOT NULL' if col['notnull'] else 'NULL'}")
    
    # Check if there are any existing records
    cursor.execute("SELECT COUNT(*) as count FROM wrestler_rankings")
    count = cursor.fetchone()['count']
    print(f"\nTotal records in wrestler_rankings: {count}")
    
    if count > 0:
        # Get a sample record
        cursor.execute("SELECT * FROM wrestler_rankings LIMIT 1")
        sample = cursor.fetchone()
        print("\nSample record:")
        for key in sample.keys():
            print(f"  {key}: {sample[key]}")
    
except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close() 