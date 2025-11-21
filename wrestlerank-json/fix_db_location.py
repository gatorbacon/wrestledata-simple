import os
import shutil
import sqlite3
import sys

def fix_db_location(source_db, target_db, backup=True):
    """Fix the database location by copying the source database to the target location."""
    print(f"Fixing database location:")
    print(f"  Source: {source_db}")
    print(f"  Target: {target_db}")
    
    # Check if source database exists
    if not os.path.exists(source_db):
        print(f"Error: Source database does not exist: {source_db}")
        return False
    
    # Create a backup of the target database if it exists
    if os.path.exists(target_db) and backup:
        backup_db = f"{target_db}.bak"
        print(f"  Creating backup of target database: {backup_db}")
        try:
            shutil.copy2(target_db, backup_db)
            print(f"  Backup created successfully")
        except Exception as e:
            print(f"  Error creating backup: {e}")
            return False
    
    # Copy the source database to the target location
    try:
        # Make sure the target directory exists
        target_dir = os.path.dirname(target_db)
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)
        
        # Copy the database
        shutil.copy2(source_db, target_db)
        print(f"  Database copied successfully")
        return True
    except Exception as e:
        print(f"  Error copying database: {e}")
        return False

def main():
    """Fix the database location issue."""
    # Parent directory database
    parent_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wrestlerank.db')
    
    # Wrestling-new directory database
    new_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wrestling-new')
    new_db = os.path.join(new_dir, 'wrestlerank.db')
    
    print("Database locations:")
    print(f"  Parent directory: {parent_db}")
    print(f"  Wrestling-new directory: {new_db}")
    
    # Check if both databases exist
    parent_exists = os.path.exists(parent_db)
    new_exists = os.path.exists(new_db)
    
    print(f"  Parent database exists: {parent_exists}")
    print(f"  Wrestling-new database exists: {new_exists}")
    
    if parent_exists and new_exists:
        # Both databases exist, ask which one to keep
        print("\nBoth databases exist. Which one do you want to keep?")
        print("1. Parent directory database")
        print("2. Wrestling-new directory database")
        
        choice = input("Enter your choice (1 or 2): ")
        
        if choice == "1":
            # Keep parent database, copy it to wrestling-new
            if fix_db_location(parent_db, new_db):
                print("\nDatabase location fixed successfully!")
                print("The parent directory database has been copied to the wrestling-new directory.")
        elif choice == "2":
            # Keep wrestling-new database, copy it to parent
            if fix_db_location(new_db, parent_db):
                print("\nDatabase location fixed successfully!")
                print("The wrestling-new directory database has been copied to the parent directory.")
        else:
            print("Invalid choice. No changes were made.")
    elif parent_exists:
        # Only parent database exists, copy it to wrestling-new
        if fix_db_location(parent_db, new_db):
            print("\nDatabase location fixed successfully!")
            print("The parent directory database has been copied to the wrestling-new directory.")
    elif new_exists:
        # Only wrestling-new database exists, copy it to parent
        if fix_db_location(new_db, parent_db):
            print("\nDatabase location fixed successfully!")
            print("The wrestling-new directory database has been copied to the parent directory.")
    else:
        print("\nError: No database found in either location.")

if __name__ == "__main__":
    main() 