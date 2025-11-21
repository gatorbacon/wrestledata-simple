import os
import shutil
import re
import sys

def ensure_script_in_wrestling_new():
    """Make sure this script is running from the wrestling-new directory."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    dir_name = os.path.basename(current_dir)
    
    if dir_name != 'wrestling-new':
        print(f"Error: This script should be run from the wrestling-new directory")
        print(f"Current directory: {current_dir}")
        
        # Check if we're in the parent directory
        wrestling_new_dir = os.path.join(current_dir, 'wrestling-new')
        if os.path.isdir(wrestling_new_dir):
            print(f"Found wrestling-new directory at {wrestling_new_dir}")
            print(f"Please cd to that directory and run this script again")
        
        return False
    
    return True

def move_scripts_to_wrestling_new():
    """Move all scripts from the parent directory to wrestling-new."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    
    # List of scripts to check
    script_names = [
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
        'test_db_write.py',
        'fix_cli_db_path.py',
        'fix_matrix_db_path.py',
        'fix_db_paths.py',
        'check_db_paths.py',
        'move_scripts.py'
    ]
    
    moved_count = 0
    for script_name in script_names:
        source_path = os.path.join(parent_dir, script_name)
        target_path = os.path.join(current_dir, script_name)
        
        if os.path.exists(source_path):
            # Check if the file already exists in wrestling-new
            if os.path.exists(target_path):
                print(f"Script already exists in wrestling-new: {script_name}")
                
                # Compare the files
                with open(source_path, 'r') as f1, open(target_path, 'r') as f2:
                    content1 = f1.read()
                    content2 = f2.read()
                
                if content1 == content2:
                    print(f"  Files are identical, deleting the source file")
                    os.remove(source_path)
                else:
                    print(f"  Files are different, renaming the source file to {script_name}.parent")
                    os.rename(source_path, f"{source_path}.parent")
            else:
                # Move the file
                try:
                    shutil.move(source_path, target_path)
                    print(f"Moved {script_name} to wrestling-new")
                    moved_count += 1
                except Exception as e:
                    print(f"Error moving {script_name}: {e}")
    
    print(f"Moved {moved_count} scripts to wrestling-new")

def fix_db_paths_in_scripts():
    """Fix database paths in all scripts in wrestling-new."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Pattern to match database path code
    pattern = r'db_path\s*=\s*os\.path\.join\((.*?)\)'
    
    # Correct path code
    correct_path = "os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wrestlerank.db')"
    
    # Find all Python files in wrestling-new
    python_files = []
    for root, dirs, files in os.walk(current_dir):
        for file in files:
            if file.endswith('.py'):
                python_files.append(os.path.join(root, file))
    
    print(f"Found {len(python_files)} Python files in wrestling-new")
    
    # Check and fix each file
    fixed_count = 0
    for file_path in python_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Find all database path definitions
            matches = re.findall(pattern, content)
            
            if matches:
                print(f"\nFile: {file_path}")
                
                # Check if any path needs to be fixed
                needs_fix = False
                for match in matches:
                    if 'os.path.dirname(os.path.abspath(__file__))' not in match:
                        print(f"  Found incorrect path: {match}")
                        needs_fix = True
                
                if needs_fix:
                    # Fix the paths
                    new_content = re.sub(
                        r'db_path\s*=\s*os\.path\.join\(.*?\)',
                        f"db_path = {correct_path}",
                        content
                    )
                    
                    # Write the fixed content back to the file
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    
                    print(f"  Fixed database path in {file_path}")
                    fixed_count += 1
                else:
                    print(f"  Path is already correct")
        
        except Exception as e:
            print(f"Error processing {file_path}: {e}")
    
    print(f"Fixed database paths in {fixed_count} files")

def fix_cli_db_path():
    """Fix the database path in the CLI module."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Path to the CLI module
    cli_path = os.path.join(current_dir, '..', 'wrestlerank', 'cli.py')
    
    if not os.path.exists(cli_path):
        print(f"Error: CLI module not found at {cli_path}")
        return
    
    print(f"Fixing database path in {cli_path}")
    
    try:
        # Read the CLI module
        with open(cli_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Look for database path definitions
        db_path_pattern = r'(.*?[\'"]wrestlerank\.db[\'"])'
        matches = re.findall(db_path_pattern, content)
        
        if not matches:
            print("No database path references found")
            return
        
        print(f"Found {len(matches)} database path references:")
        for match in matches:
            print(f"  {match}")
        
        # Fix the paths
        new_content = content
        
        # Replace direct references to 'wrestlerank.db'
        new_content = re.sub(
            r'[\'"]wrestlerank\.db[\'"]',
            "os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'wrestling-new', 'wrestlerank.db')",
            new_content
        )
        
        # Make sure os.path is imported
        if 'import os' not in new_content and 'from os import' not in new_content:
            new_content = "import os\n" + new_content
        
        # Write the fixed content back to the file
        with open(cli_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print(f"Fixed database path in {cli_path}")
        
    except Exception as e:
        print(f"Error fixing CLI database path: {e}")

def fix_matrix_db_path():
    """Fix the database path in the matrix module."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Path to the wrestlerank directory
    wrestlerank_dir = os.path.join(current_dir, '..', 'wrestlerank')
    
    if not os.path.exists(wrestlerank_dir):
        print(f"Error: Wrestlerank directory not found at {wrestlerank_dir}")
        return
    
    # Find all Python files in the wrestlerank directory
    matrix_files = []
    for root, dirs, files in os.walk(wrestlerank_dir):
        for file in files:
            if file.endswith('.py') and ('matrix' in file.lower() or 'rank' in file.lower()):
                matrix_files.append(os.path.join(root, file))
    
    if not matrix_files:
        print("No matrix-related files found")
        return
    
    print(f"Found {len(matrix_files)} matrix-related files:")
    for file in matrix_files:
        print(f"  {file}")
    
    # Fix each file
    fixed_count = 0
    for file_path in matrix_files:
        try:
            # Read the file
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Look for database path definitions
            db_path_pattern = r'(.*?[\'"]wrestlerank\.db[\'"])'
            matches = re.findall(db_path_pattern, content)
            
            if not matches:
                print(f"\nNo database path references found in {file_path}")
                continue
            
            print(f"\nFound {len(matches)} database path references in {file_path}:")
            for match in matches:
                print(f"  {match}")
            
            # Fix the paths
            new_content = content
            
            # Replace direct references to 'wrestlerank.db'
            new_content = re.sub(
                r'[\'"]wrestlerank\.db[\'"]',
                "os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'wrestling-new', 'wrestlerank.db')",
                new_content
            )
            
            # Make sure os.path is imported
            if 'import os' not in new_content and 'from os import' not in new_content:
                new_content = "import os\n" + new_content
            
            # Write the fixed content back to the file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            print(f"Fixed database path in {file_path}")
            fixed_count += 1
            
        except Exception as e:
            print(f"Error fixing database path in {file_path}: {e}")
    
    print(f"\nFixed database paths in {fixed_count} files")

def fix_db_location():
    """Fix the database location by ensuring the wrestling-new database is used."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
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
    
    if new_db_exists and parent_db_exists:
        # Both databases exist, check their sizes
        new_db_size = os.path.getsize(new_db)
        parent_db_size = os.path.getsize(parent_db)
        
        print(f"  Wrestling-new database size: {new_db_size} bytes")
        print(f"  Parent directory database size: {parent_db_size} bytes")
        
        if new_db_size > parent_db_size:
            print(f"  Wrestling-new database is larger, using it")
            
            # Backup the parent database
            if parent_db_size > 0:
                backup_db = f"{parent_db}.bak"
                try:
                    shutil.copy2(parent_db, backup_db)
                    print(f"  Created backup of parent database: {backup_db}")
                except Exception as e:
                    print(f"  Error creating backup: {e}")
            
            # Copy the wrestling-new database to the parent directory
            try:
                shutil.copy2(new_db, parent_db)
                print(f"  Copied wrestling-new database to parent directory")
            except Exception as e:
                print(f"  Error copying database: {e}")
        elif parent_db_size > new_db_size:
            print(f"  Parent directory database is larger, using it")
            
            # Backup the wrestling-new database
            if new_db_size > 0:
                backup_db = f"{new_db}.bak"
                try:
                    shutil.copy2(new_db, backup_db)
                    print(f"  Created backup of wrestling-new database: {backup_db}")
                except Exception as e:
                    print(f"  Error creating backup: {e}")
            
            # Copy the parent database to the wrestling-new directory
            try:
                shutil.copy2(parent_db, new_db)
                print(f"  Copied parent database to wrestling-new directory")
            except Exception as e:
                print(f"  Error copying database: {e}")
        else:
            print(f"  Both databases are the same size, no action needed")
    elif new_db_exists:
        print(f"  Only wrestling-new database exists, copying it to parent directory")
        
        try:
            shutil.copy2(new_db, parent_db)
            print(f"  Copied wrestling-new database to parent directory")
        except Exception as e:
            print(f"  Error copying database: {e}")
    elif parent_db_exists:
        print(f"  Only parent directory database exists, copying it to wrestling-new directory")
        
        try:
            shutil.copy2(parent_db, new_db)
            print(f"  Copied parent database to wrestling-new directory")
        except Exception as e:
            print(f"  Error copying database: {e}")
    else:
        print(f"  No database found in either location")

def main():
    """Fix everything."""
    if not ensure_script_in_wrestling_new():
        return
    
    print("=== Moving Scripts to Wrestling-New ===")
    move_scripts_to_wrestling_new()
    
    print("\n=== Fixing Database Paths in Scripts ===")
    fix_db_paths_in_scripts()
    
    print("\n=== Fixing CLI Database Path ===")
    fix_cli_db_path()
    
    print("\n=== Fixing Matrix Database Path ===")
    fix_matrix_db_path()
    
    print("\n=== Fixing Database Location ===")
    fix_db_location()
    
    print("\n=== All Done! ===")
    print("Everything should now be in the correct location and using the correct database path.")
    print("Try running the matrix command again:")
    print("  cd ..")
    print("  .\\run.ps1 matrix W106")

if __name__ == "__main__":
    main() 