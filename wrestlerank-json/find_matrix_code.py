import os
import sys
import re

def search_files_for_code(directory, pattern, file_pattern=None):
    """Search for code matching a pattern in files."""
    matches = []
    
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file_pattern and not re.match(file_pattern, file):
                continue
                
            file_path = os.path.join(root, file)
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                    if re.search(pattern, content, re.IGNORECASE):
                        matches.append((file_path, content))
            except Exception as e:
                print(f"Error reading {file_path}: {e}")
    
    return matches

def find_matrix_code():
    """Find and examine the matrix code."""
    # Directory to search
    directory = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wrestlerank')
    
    # Look for Python files that might contain matrix code
    file_pattern = r'.*\.py$'
    
    # Patterns to search for
    patterns = [
        r'def\s+build_matrix',
        r'matrix_generator',
        r'wrestler_rankings.*date',
        r'SELECT.*FROM\s+wrestler_rankings',
        r'ORDER\s+BY\s+rank',
        r'-optimal'
    ]
    
    for pattern in patterns:
        print(f"\nSearching for pattern: {pattern}")
        matches = search_files_for_code(directory, pattern, file_pattern)
        
        if not matches:
            print(f"No matches found for pattern: {pattern}")
            continue
        
        print(f"Found {len(matches)} files matching pattern: {pattern}")
        
        for file_path, content in matches:
            print(f"\nFile: {file_path}")
            
            # Extract relevant sections
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if re.search(pattern, line, re.IGNORECASE):
                    start = max(0, i - 10)
                    end = min(len(lines), i + 10)
                    
                    print(f"\nMatch around line {i+1}:")
                    for j in range(start, end):
                        if j == i:
                            print(f"> {lines[j]}")
                        else:
                            print(f"  {lines[j]}")

if __name__ == "__main__":
    find_matrix_code() 