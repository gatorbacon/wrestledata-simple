import os
import sys
import inspect

def find_module_file(module_name):
    """Find the file path for a module."""
    try:
        module = __import__(module_name, fromlist=[''])
        return module.__file__
    except ImportError:
        return None

def examine_matrix_code():
    """Examine the matrix generation code."""
    # Try to find the matrix module
    matrix_file = find_module_file('wrestlerank.matrix')
    
    if not matrix_file:
        # Try to find it directly in the wrestlerank directory
        wrestlerank_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wrestlerank')
        matrix_file = os.path.join(wrestlerank_dir, 'matrix.py')
        
        if not os.path.exists(matrix_file):
            print(f"Error: Could not find the matrix module")
            return
    
    print(f"Matrix module found at: {matrix_file}")
    
    # Read the file
    with open(matrix_file, 'r') as f:
        code = f.read()
    
    print("\nSearching for database queries in the matrix code...")
    
    # Look for SQL queries related to rankings
    lines = code.split('\n')
    for i, line in enumerate(lines):
        if 'wrestler_rankings' in line.lower() and ('select' in line.lower() or 'from' in line.lower()):
            start = max(0, i - 5)
            end = min(len(lines), i + 5)
            
            print(f"\nFound database query around line {i+1}:")
            for j in range(start, end):
                if j == i:
                    print(f"> {lines[j]}")
                else:
                    print(f"  {lines[j]}")

if __name__ == "__main__":
    examine_matrix_code() 