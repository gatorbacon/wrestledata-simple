import os
import shutil
import sys

def clean_parent_db():
    """Delete the database in the parent directory after backing it up."""
    # Get the current directory (should be wrestling-new)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Get the parent directory
    parent_dir = os.path.dirname(current_dir)
    
    # Path to the databases
    new_db = os.path.join(current_dir, 'wrestlerank.db')
    parent_db = os.path.join(parent_dir, 'wrestlerank.db')
    
    print(f"Checking database locations:")
    print(f"  Wrestling-new database: {new_db}")
    print(f"  Parent directory database: {parent_db}")
    
    # Check if the databases exist
    new_db_exists = os.path.exists(new_db)
    parent_db_exists = os.path.exists(parent_db)
    
    print(f"  Wrestling-new database exists: {new_db_exists}")
    print(f"  Parent directory database exists: {parent_db_exists}")
    
    if not new_db_exists:
        print("Error: Database not found in wrestling-new directory!")
        print("Please make sure the database exists in the wrestling-new directory before deleting the parent one.")
        return
    
    if not parent_db_exists:
        print("No database found in parent directory. Nothing to delete.")
        return
    
    # Create a backup of the parent database
    backup_db = f"{parent_db}.bak"
    try:
        shutil.copy2(parent_db, backup_db)
        print(f"Created backup of parent database: {backup_db}")
    except Exception as e:
        print(f"Error creating backup: {e}")
        return
    
    # Delete the parent database
    try:
        os.remove(parent_db)
        print(f"Successfully deleted database in parent directory: {parent_db}")
    except Exception as e:
        print(f"Error deleting parent database: {e}")
    
    print("\nAll done! The database in the parent directory has been deleted.")
    print("A backup was created at:", backup_db)
    print("All code should now be using the database in the wrestling-new directory.")

if __name__ == "__main__":
    clean_parent_db() 