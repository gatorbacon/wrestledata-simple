import os
import re
import sys

def fix_cli_db_path():
    """Fix the database path in the CLI module."""
    # Get the current directory
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
        
        # Check if we need to fix the path
        if all('os.path.dirname(os.path.abspath(__file__))' in match for match in matches):
            print("All database paths are already using the correct relative path")
            return
        
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

if __name__ == "__main__":
    fix_cli_db_path() 