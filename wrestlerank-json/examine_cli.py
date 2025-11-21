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

def examine_cli_code():
    """Examine the CLI code."""
    # Try to find the CLI module
    cli_file = find_module_file('wrestlerank.cli')
    
    if not cli_file:
        # Try to find it directly in the wrestlerank directory
        wrestlerank_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wrestlerank')
        cli_file = os.path.join(wrestlerank_dir, 'cli.py')
        
        if not os.path.exists(cli_file):
            print(f"Error: Could not find the CLI module")
            return
    
    print(f"CLI module found at: {cli_file}")
    
    # Read the file
    with open(cli_file, 'r') as f:
        code = f.read()
    
    print("\nSearching for matrix command handling in the CLI code...")
    
    # Look for matrix command handling
    lines = code.split('\n')
    for i, line in enumerate(lines):
        if 'matrix' in line.lower() and ('def' in line.lower() or 'command' in line.lower() or 'parser' in line.lower()):
            start = max(0, i - 10)
            end = min(len(lines), i + 10)
            
            print(f"\nFound matrix command handling around line {i+1}:")
            for j in range(start, end):
                if j == i:
                    print(f"> {lines[j]}")
                else:
                    print(f"  {lines[j]}")

if __name__ == "__main__":
    examine_cli_code() 