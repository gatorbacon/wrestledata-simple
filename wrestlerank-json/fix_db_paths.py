import os
import re
import sys

def fix_db_paths():
    """Fix database paths in all scripts."""
    # Get the current directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Pattern to match database path code
    pattern = r'db_path\s*=\s*os\.path\.join\((.*?)\)'
    
    # Correct path code
    correct_path = "os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wrestlerank.db')"
    
    # Find all Python files
    python_files = []
    for root, dirs, files in os.walk(current_dir):
        for file in files:
            if file.endswith('.py'):
                python_files.append(os.path.join(root, file))
    
    print(f"Found {len(python_files)} Python files")
    
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
    
    print(f"\nFixed database paths in {fixed_count} files")

if __name__ == "__main__":
    fix_db_paths() 