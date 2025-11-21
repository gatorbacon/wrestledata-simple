import os
import sqlite3
import sys

def check_db_file(db_path):
    """Check a database file and print information about it."""
    print(f"\nChecking database: {db_path}")
    
    if not os.path.exists(db_path):
        print(f"  Database file does not exist")
        return
    
    print(f"  File size: {os.path.getsize(db_path)} bytes")
    print(f"  Last modified: {os.path.getmtime(db_path)}")
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Check tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row['name'] for row in cursor.fetchall()]
        print(f"  Tables: {', '.join(tables)}")
        
        # Check wrestler_rankings table
        if 'wrestler_rankings' in tables:
            cursor.execute("SELECT COUNT(*) as count FROM wrestler_rankings")
            count = cursor.fetchone()['count']
            print(f"  Total rankings: {count}")
            
            # Check weight classes
            cursor.execute("SELECT DISTINCT weight_class FROM wrestler_rankings")
            weight_classes = [row['weight_class'] for row in cursor.fetchall()]
            print(f"  Weight classes: {', '.join(weight_classes)}")
            
            # Check dates
            cursor.execute("SELECT DISTINCT date FROM wrestler_rankings ORDER BY date DESC")
            dates = [row['date'] for row in cursor.fetchall()]
            print(f"  Dates: {', '.join(dates)}")
            
            # Check most recent rankings for w106
            if 'w106' in weight_classes:
                for date in dates:
                    cursor.execute(
                        """
                        SELECT wrestler_id, rank
                        FROM wrestler_rankings
                        WHERE weight_class = 'w106' AND date = ?
                        ORDER BY rank
                        LIMIT 5
                        """,
                        (date,)
                    )
                    rankings = cursor.fetchall()
                    
                    if rankings:
                        print(f"\n  Top 5 rankings for w106 on {date}:")
                        for ranking in rankings:
                            print(f"    Rank {ranking['rank']}: {ranking['wrestler_id']}")
        
        conn.close()
    except Exception as e:
        print(f"  Error accessing database: {e}")

def main():
    """Check both database locations."""
    # Parent directory database
    parent_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wrestlerank.db')
    
    # Wrestling-new directory database
    new_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wrestling-new')
    new_db = os.path.join(new_dir, 'wrestlerank.db')
    
    print("Checking database locations:")
    print(f"Parent directory: {os.path.dirname(os.path.abspath(__file__))}")
    print(f"Wrestling-new directory: {new_dir}")
    
    check_db_file(parent_db)
    check_db_file(new_db)
    
    # Check which database is being used by the code
    print("\nChecking which database is being used by the code:")
    
    # Check import_rankings.py
    import_rankings_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'import_rankings.py')
    if os.path.exists(import_rankings_path):
        print(f"\nChecking {import_rankings_path}:")
        with open(import_rankings_path, 'r') as f:
            content = f.read()
            print(f"  Database path code: {content.find('db_path = os.path.join')}")
    
    # Check direct_import.py
    direct_import_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'direct_import.py')
    if os.path.exists(direct_import_path):
        print(f"\nChecking {direct_import_path}:")
        with open(direct_import_path, 'r') as f:
            content = f.read()
            print(f"  Database path code: {content.find('db_path = os.path.join')}")
    
    # Check wrestlerank directory for Python files that might use the database
    wrestlerank_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wrestlerank')
    if os.path.exists(wrestlerank_dir):
        print(f"\nChecking Python files in {wrestlerank_dir}:")
        for root, dirs, files in os.walk(wrestlerank_dir):
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r') as f:
                            content = f.read()
                            if 'wrestlerank.db' in content:
                                print(f"  {file_path} references wrestlerank.db")
                    except Exception as e:
                        print(f"  Error reading {file_path}: {e}")

if __name__ == "__main__":
    main() 