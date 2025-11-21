import os
import sqlite3
import sys
import re

def update_wrestler_weight_classes():
    """Update wrestler weight classes to use numeric values."""
    # Initialize the database connection
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wrestlerank.db')
    
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # Check if there's a weight_class column in the wrestlers table
        cursor.execute("PRAGMA table_info(wrestlers)")
        columns = [row['name'] for row in cursor.fetchall()]
        
        if 'weight_class' in columns:
            print("Found weight_class column in wrestlers table")
            
            # Get all weight classes from wrestlers table
            cursor.execute("SELECT DISTINCT weight_class FROM wrestlers WHERE weight_class IS NOT NULL")
            weight_classes = [row['weight_class'] for row in cursor.fetchall()]
            
            if not weight_classes:
                print("No weight classes found in wrestlers table")
            else:
                print(f"Current weight classes in wrestlers table: {', '.join(weight_classes)}")
                
                # Update each weight class to its numeric value
                updated_count = 0
                for wc in weight_classes:
                    # Extract the numeric part
                    match = re.search(r'(\d+)', wc)
                    if match:
                        numeric_value = match.group(1)
                        if wc != numeric_value:
                            print(f"Updating {wc} to {numeric_value}")
                            cursor.execute(
                                "UPDATE wrestlers SET weight_class = ? WHERE weight_class = ?",
                                (numeric_value, wc)
                            )
                            updated_count += cursor.rowcount
                
                conn.commit()
                print(f"Updated {updated_count} wrestlers")
        
        # Check the matches table for weight_class column
        cursor.execute("PRAGMA table_info(matches)")
        columns = [row['name'] for row in cursor.fetchall()]
        
        if 'weight_class' in columns:
            print("\nFound weight_class column in matches table")
            
            # Get all weight classes from matches table
            cursor.execute("SELECT DISTINCT weight_class FROM matches WHERE weight_class IS NOT NULL")
            weight_classes = [row['weight_class'] for row in cursor.fetchall()]
            
            if not weight_classes:
                print("No weight classes found in matches table")
            else:
                print(f"Current weight classes in matches table: {', '.join(weight_classes)}")
                
                # Update each weight class to its numeric value
                updated_count = 0
                for wc in weight_classes:
                    # Extract the numeric part
                    match = re.search(r'(\d+)', wc)
                    if match:
                        numeric_value = match.group(1)
                        if wc != numeric_value:
                            print(f"Updating {wc} to {numeric_value}")
                            cursor.execute(
                                "UPDATE matches SET weight_class = ? WHERE weight_class = ?",
                                (numeric_value, wc)
                            )
                            updated_count += cursor.rowcount
                
                conn.commit()
                print(f"Updated {updated_count} matches")
        
        # Now let's check the matrix generation query to see what tables it's using
        print("\nChecking matrix generation query...")
        
        # Get all tables in the database
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row['name'] for row in cursor.fetchall()]
        
        print(f"Tables in database: {', '.join(tables)}")
        
        # Check if there's a common_opponent_paths table
        if 'common_opponent_paths' in tables:
            print("\nFound common_opponent_paths table")
            
            # Check if it has a weight_class column
            cursor.execute("PRAGMA table_info(common_opponent_paths)")
            columns = [row['name'] for row in cursor.fetchall()]
            
            if 'weight_class' in columns:
                print("Found weight_class column in common_opponent_paths table")
                
                # Get all weight classes from common_opponent_paths table
                cursor.execute("SELECT DISTINCT weight_class FROM common_opponent_paths WHERE weight_class IS NOT NULL")
                weight_classes = [row['weight_class'] for row in cursor.fetchall()]
                
                if not weight_classes:
                    print("No weight classes found in common_opponent_paths table")
                else:
                    print(f"Current weight classes in common_opponent_paths table: {', '.join(weight_classes)}")
                    
                    # Update each weight class to its numeric value
                    updated_count = 0
                    for wc in weight_classes:
                        # Extract the numeric part
                        match = re.search(r'(\d+)', wc)
                        if match:
                            numeric_value = match.group(1)
                            if wc != numeric_value:
                                print(f"Updating {wc} to {numeric_value}")
                                cursor.execute(
                                    "UPDATE common_opponent_paths SET weight_class = ? WHERE weight_class = ?",
                                    (numeric_value, wc)
                                )
                                updated_count += cursor.rowcount
                    
                    conn.commit()
                    print(f"Updated {updated_count} common opponent paths")
        
        print("\nAll done! Weight classes have been standardized to numeric values.")
        
    except Exception as e:
        print(f"Error updating wrestler weight classes: {e}")
        import traceback
        traceback.print_exc()
        # Rollback the transaction if there was an error
        try:
            conn.rollback()
        except:
            pass
    finally:
        conn.close()

if __name__ == "__main__":
    update_wrestler_weight_classes() 