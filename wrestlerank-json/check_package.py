import os
import sys

def check_package(package_name):
    """Check the structure of a Python package."""
    print(f"Checking package: {package_name}")
    
    # Check if the package directory exists
    if not os.path.isdir(package_name):
        print(f"Error: Package directory '{package_name}' not found")
        return
    
    # List all files in the package directory
    print(f"\nFiles in {package_name}/:")
    for file in sorted(os.listdir(package_name)):
        file_path = os.path.join(package_name, file)
        if os.path.isfile(file_path):
            print(f"  {file}")
    
    # Check for __init__.py
    init_path = os.path.join(package_name, "__init__.py")
    if os.path.isfile(init_path):
        print(f"\nFound __init__.py")
    else:
        print(f"\nWarning: __init__.py not found in {package_name}")
    
    # Check for __main__.py
    main_path = os.path.join(package_name, "__main__.py")
    if os.path.isfile(main_path):
        print(f"Found __main__.py")
    else:
        print(f"Warning: __main__.py not found in {package_name}")
    
    # Check for cli.py
    cli_path = os.path.join(package_name, "cli.py")
    if os.path.isfile(cli_path):
        print(f"Found cli.py")
    else:
        print(f"Warning: cli.py not found in {package_name}")
    
    # Check if the package is importable
    print(f"\nTrying to import {package_name}...")
    try:
        __import__(package_name)
        print(f"Successfully imported {package_name}")
    except ImportError as e:
        print(f"Error importing {package_name}: {e}")
    
    # Check Python path
    print(f"\nPython path:")
    for path in sys.path:
        print(f"  {path}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        package_name = sys.argv[1]
    else:
        package_name = "wrestlerank"
    
    check_package(package_name) 