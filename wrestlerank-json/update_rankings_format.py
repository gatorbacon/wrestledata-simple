import sqlite3
import os
import sys
import datetime

def update_rankings_format(weight_class, from_suffix='manual', to_suffix='optimal'):
    """Update the format of rankings from one suffix to another."""
    print(f"Updating rankings format for weight class {weight_class} from '{from_suffix}' to '{to_suffix}'")
    
    # Initialize the database connection
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wrestlerank.db')), 'wrestlerank.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    try:
        cursor = conn.cursor()
        
        # Get all dates with the from_suffix
        cursor.execute(
            "SELECT DISTINCT date FROM wrestler_rankings WHERE weight_class = ? AND date LIKE ?",
            (weight_class, f'%-{from_suffix}')
        )
        dates = [row['date'] for row in cursor.fetchall()]
        
        if not dates:
            print(f"No rankings found for weight class {weight_class} with suffix '{from_suffix}'")
            return
        
        print(f"Found {len(dates)} dates with suffix '{from_suffix}': {', '.join(dates)}")
        
        # Begin a transaction
        cursor.execute("BEGIN TRANSACTION")
        
        total_updated = 0
        
        for date in dates:
            # Extract the date part and create the new date string
            date_part = date.split('-')[0]
            new_date = f"{date_part}-{to_suffix}"
            
            # Check if there are already rankings with the new date
            cursor.execute(
                "SELECT COUNT(*) as count FROM wrestler_rankings WHERE weight_class = ? AND date = ?",
                (weight_class, new_date)
            )
            existing_count = cursor.fetchone()['count']
            
            if existing_count > 0:
                print(f"Warning: {existing_count} rankings already exist for {weight_class} with date {new_date}")
                print(f"Deleting existing rankings for {weight_class} with date {new_date}")
                
                # Delete the existing rankings
                cursor.execute(
                    "DELETE FROM wrestler_rankings WHERE weight_class = ? AND date = ?",
                    (weight_class, new_date)
                )
            
            # Update the date format
            cursor.execute(
                "UPDATE wrestler_rankings SET date = ? WHERE weight_class = ? AND date = ?",
                (new_date, weight_class, date)
            )
            
            updated = cursor.rowcount
            total_updated += updated
            
            print(f"Updated {updated} rankings from {date} to {new_date}")
        
        # Commit the transaction
        conn.commit()
        
        print(f"Successfully updated {total_updated} rankings for weight class {weight_class}")
        
    except Exception as e:
        print(f"Error: {e}")
        # Rollback the transaction if there was an error
        try:
            conn.rollback()
        except:
            pass
    finally:
        conn.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python update_rankings_format.py <weight_class> [from_suffix] [to_suffix]")
        sys.exit(1)
    
    weight_class = sys.argv[1].lower()
    from_suffix = sys.argv[2] if len(sys.argv) > 2 else 'manual'
    to_suffix = sys.argv[3] if len(sys.argv) > 3 else 'optimal'
    
    update_rankings_format(weight_class, from_suffix, to_suffix) 