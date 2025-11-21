import os
import shutil
import sys

def move_scripts_to_subdirectory():
    """Move scripts from the parent directory to the wrestling-new subdirectory."""
    # Get the current directory (parent directory)
    parent_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Get the wrestling-new subdirectory
    new_dir = os.path.join(parent_dir, 'wrestling-new')
    
    # Check if the wrestling-new directory exists
    if not os.path.isdir(new_dir):
        print(f"Error: Wrestling-new directory not found: {new_dir}")
        return
    
    # List of scripts to move
    scripts = [
        'check_db_locations.py',
        'fix_db_location.py',
        'find_matrix_code.py',
        'trace_matrix_query.py',
        'update_rankings_format.py',
        'check_rankings.py',
        'check_schema.py',
        'direct_import.py',
        'examine_cli.py',
        'examine_matrix.py',
        'examine_record.py',
        'import_rankings.py',
        'test_db_write.py'
    ]
    
    # Move each script
    moved_count = 0
    for script in scripts:
        source_path = os.path.join(parent_dir, script)
        target_path = os.path.join(new_dir, script)
        
        if os.path.exists(source_path):
            # Check if the file already exists in the target directory
            if os.path.exists(target_path):
                print(f"Warning: {script} already exists in {new_dir}")
                
                # Compare the files
                with open(source_path, 'r') as f1, open(target_path, 'r') as f2:
                    content1 = f1.read()
                    content2 = f2.read()
                
                if content1 == content2:
                    print(f"  Files are identical, deleting the source file")
                    os.remove(source_path)
                else:
                    print(f"  Files are different, renaming the source file to {script}.parent")
                    os.rename(source_path, f"{source_path}.parent")
            else:
                # Move the file
                try:
                    shutil.move(source_path, target_path)
                    print(f"Moved {script} to {new_dir}")
                    moved_count += 1
                except Exception as e:
                    print(f"Error moving {script}: {e}")
    
    print(f"\nMoved {moved_count} scripts to {new_dir}")

if __name__ == "__main__":
    move_scripts_to_subdirectory() 