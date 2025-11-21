import os
import sqlite3
import sys
import re

def check_matrix_date():
    """Check which date format the matrix code is using."""
    # Path to the wrestlerank directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
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
    
    # Check each file for date references
    date_patterns = [
        r'date\s*=\s*[\'"]([^\'"]*)[\'"]',
        r'ORDER BY date',
        r'date DESC',
        r'date ASC',
        r'WHERE.*date',
        r'-optimal',
        r'-manual'
    ]
    
    for file_path in matrix_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            print(f"\nChecking {file_path} for date references:")
            
            for pattern in date_patterns:
                matches = re.findall(pattern, content)
                if matches:
                    print(f"  Found pattern '{pattern}':")
                    for match in matches:
                        print(f"    {match}")
            
            # Look for SQL queries that might select the most recent date
            if 'ORDER BY date DESC' in content:
                print("  This file appears to select the most recent date")
            
            # Look for specific date format references
            if '-optimal' in content:
                print("  This file appears to reference the '-optimal' date format")
            
            if '-manual' in content:
                print("  This file appears to reference the '-manual' date format")
            
        except Exception as e:
            print(f"Error checking {file_path}: {e}")

if __name__ == "__main__":
    check_matrix_date() 