import os
import re
import sys

def check_db_paths():
    """Check database paths in all scripts."""
    # Get the current directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Pattern to match database path code
    pattern = r'db_path\s*=\s*os\.path\.join\(.*?\)'
    
    # Find all Python files
    python_files = []
    for root, dirs, files in os.walk(current_dir):
        for file in files:
            if file.endswith('.py'):
                python_files.append(os.path.join(root, file))
    
    print(f"Found {len(python_files)} Python files")
    
    # Check each file
    for file_path in python_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
                # Find all database path definitions
                matches = re.findall(pattern, content)
                
                if matches:
                    print(f"\nFile: {file_path}")
                    for match in matches:
                        print(f"  {match}")
                        
                        # Check if the path is correct
                        if 'os.path.dirname(os.path.abspath(__file__))' in match:
                            print("  ✓ Using correct relative path")
                        else:
                            print("  ✗ Not using correct relative path")
        except Exception as e:
            print(f"Error reading {file_path}: {e}")

if __name__ == "__main__":
    check_db_paths() 