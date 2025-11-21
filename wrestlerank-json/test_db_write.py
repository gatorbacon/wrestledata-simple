import sqlite3
import os
import datetime

# Initialize the database connection
db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wrestlerank.db')), 'wrestlerank.db')
print(f"Database path: {db_path}")
print(f"Database exists: {os.path.exists(db_path)}")

if os.path.exists(db_path):
    print(f"Database size: {os.path.getsize(db_path)} bytes")
    print(f"Database permissions: {oct(os.stat(db_path).st_mode)[-3:]}")

conn = sqlite3.connect(db_path)

try:
    # Create a test table
    cursor = conn.cursor()
    
    # Begin a transaction
    cursor.execute("BEGIN TRANSACTION")
    
    # Create a test table if it doesn't exist
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS test_table (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)
    
    # Insert a test record
    now = datetime.datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO test_table (name, created_at) VALUES (?, ?)",
        (f"Test record {now}", now)
    )
    
    # Commit the transaction
    conn.commit()
    
    print("Successfully wrote to the database")
    
    # Read back the test records
    cursor.execute("SELECT * FROM test_table ORDER BY id DESC LIMIT 5")
    rows = cursor.fetchall()
    
    print("\nRecent test records:")
    for row in rows:
        print(f"  {row}")
    
except Exception as e:
    print(f"Error: {e}")
    # Rollback the transaction if there was an error
    try:
        conn.rollback()
    except:
        pass
finally:
    # Close the database connection
    conn.close() 