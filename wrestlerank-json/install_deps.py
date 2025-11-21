"""
Helper script to install dependencies required by the optimal ranking algorithm.
"""

import sys
import subprocess
import importlib.util

def check_and_install(package_name, version=None):
    """Check if a package is installed and install it if not."""
    spec_name = package_name.lower()
    package_spec = f"{package_name}=={version}" if version else package_name
    
    if importlib.util.find_spec(spec_name) is None:
        print(f"{package_name} not found. Installing...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package_spec])
            print(f"{package_name} installed successfully!")
        except subprocess.CalledProcessError as e:
            print(f"Error installing {package_name}: {e}")
            return False
    else:
        print(f"{package_name} is already installed.")
    
    return True

if __name__ == "__main__":
    print("Installing dependencies for optimal ranker...")
    
    # List of required packages
    packages = [
        ("numpy", "2.2.1"),
        ("scipy", "1.15.0"),
        ("tqdm", "4.67.1"),
        ("networkx", "3.4.2")
    ]
    
    all_succeeded = True
    for package, version in packages:
        if not check_and_install(package, version):
            all_succeeded = False
    
    if all_succeeded:
        print("\nAll dependencies installed successfully!")
        print("You can now run the optimize-ranking command.")
    else:
        print("\nSome packages could not be installed automatically.")
        print("Please check the error messages above.") 