import sqlite3
import os

# Initialize the database connection
db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wrestlerank.db')), 'wrestlerank.db')
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

try:
    # Get a sample record
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM wrestler_rankings LIMIT 1")
    sample = cursor.fetchone()
    
    if sample:
        print("Sample record details:")
        for key in sample.keys():
            value = sample[key]
            print(f"  {key}: {value} (type: {type(value).__name__}, length: {len(str(value)) if value is not None else 'N/A'})")
    else:
        print("No records found in wrestler_rankings table")
    
    # Get the table schema
    cursor.execute("PRAGMA table_info(wrestler_rankings)")
    columns = cursor.fetchall()
    
    print("\nTable schema:")
    for col in columns:
        print(f"  {col['name']} ({col['type']}) {'NOT NULL' if col['notnull'] else 'NULL'} {'DEFAULT: ' + col['dflt_value'] if col['dflt_value'] else ''}")
    
except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close() 