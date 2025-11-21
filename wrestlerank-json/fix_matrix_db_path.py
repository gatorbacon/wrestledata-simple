import os
import re
import sys

def fix_matrix_db_path():
    """Fix the database path in the matrix module."""
    # Get the current directory (should be wrestling-new)
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
            
            # Check if we need to fix the path
            if all('os.path.dirname(os.path.abspath(__file__))' in match for match in matches):
                print("All database paths are already using the correct relative path")
                continue
            
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

if __name__ == "__main__":
    fix_matrix_db_path() 