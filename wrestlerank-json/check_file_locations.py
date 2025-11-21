import os
import sys

def check_file_locations():
    """Check where important files are located."""
    # Get the current directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Get the parent directory
    parent_dir = os.path.dirname(current_dir)
    
    print(f"Current directory: {current_dir}")
    print(f"Parent directory: {parent_dir}")
    
    # List of files to check
    files_to_check = [
        'fix_matrix_db_path.py',
        'fix_cli_db_path.py',
        'fix_db_paths.py',
        'check_db_paths.py',
        'fix_everything.py',
        'check_db_locations.py',
        'update_rankings_format.py',
        'direct_import.py'
    ]
    
    print("\nChecking file locations:")
    
    for file in files_to_check:
        # Check in current directory
        current_path = os.path.join(current_dir, file)
        parent_path = os.path.join(parent_dir, file)
        
        if os.path.exists(current_path):
            print(f"  {file}: Found in current directory")
        elif os.path.exists(parent_path):
            print(f"  {file}: Found in parent directory")
        else:
            print(f"  {file}: Not found")

if __name__ == "__main__":
    check_file_locations() 