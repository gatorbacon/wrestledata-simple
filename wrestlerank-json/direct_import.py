import json
import sqlite3
import datetime
import os
import sys
import re

def import_rankings(json_file, weight_class=None):
    """Import rankings from a JSON file."""
    try:
        # Read the JSON file
        with open(json_file, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Could not parse JSON file: {e}")
        return
    
    # Extract weight class from filename if not provided
    if not weight_class:
        # Try to extract from JSON data
        weight_class = data.get('weight_class')
        
        # If not in JSON, try to extract from filename
        if not weight_class:
            filename = os.path.basename(json_file)
            match = re.search(r'(\d+)', filename)
            if match:
                weight_class = match.group(1)
    
    rankings = data.get('rankings', [])
    
    if not weight_class or not rankings:
        print("Invalid rankings file: missing weight_class or rankings data")
        return
    
    # Ensure weight class is a string
    weight_class = str(weight_class)
    
    print(f"Importing rankings for {weight_class}")
    
    # Initialize the database connection
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wrestlerank.db')    
    conn = sqlite3.connect(db_path)
    
    try:
        # Format the date exactly like the sample: "030425-optimal"
        date_str = datetime.datetime.now().strftime('%m%d%y-optimal')
        
        # Format last_updated exactly like the sample: "2025-03-12T13:04:18.622295"
        last_updated = datetime.datetime.now().isoformat()
        
        print(f"Using date: {date_str}")
        print(f"Last updated: {last_updated}")
        
        # Insert the rankings
        cursor = conn.cursor()
        
        # Begin a transaction
        cursor.execute("BEGIN TRANSACTION")
        
        # Delete any existing rankings for this weight class and date
        cursor.execute(
            "DELETE FROM wrestler_rankings WHERE weight_class = ? AND date = ?",
            (weight_class, date_str)
        )
        
        # Insert the new rankings using a direct SQL approach
        inserted_count = 0
        for ranking in rankings:
            try:
                wrestler_id = ranking.get('wrestler_id')
                rank = ranking.get('rank')
                
                if wrestler_id and rank:
                    # Use a direct SQL statement with all required fields
                    cursor.execute(
                        """
                        INSERT INTO wrestler_rankings 
                        (wrestler_id, weight_class, rank, date, last_updated) 
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (wrestler_id, weight_class, rank, date_str, last_updated)
                    )
                    inserted_count += 1
                else:
                    print(f"Warning: Skipping invalid ranking entry: {ranking}")
            except Exception as e:
                print(f"Error inserting ranking: {e}")
                print(f"Ranking data: {ranking}")
        
        # Commit the transaction
        conn.commit()
        
        print(f"Successfully imported {inserted_count} rankings for {weight_class} with date {date_str}")
    
    except Exception as e:
        print(f"Error importing rankings: {e}")
        # Rollback the transaction if there was an error
        try:
            conn.rollback()
        except:
            pass
    finally:
        # Close the database connection
        conn.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python direct_import.py <json_file> [weight_class]")
        sys.exit(1)
    
    json_file = sys.argv[1]
    weight_class = sys.argv[2] if len(sys.argv) > 2 else None
    
    import_rankings(json_file, weight_class) 