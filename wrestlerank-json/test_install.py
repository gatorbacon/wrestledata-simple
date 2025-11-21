"""
Simple test script to verify the WrestleRank installation.
"""

print("Testing WrestleRank installation...")

try:
    import click
    print("✓ click is installed")
except ImportError:
    print("✗ click is not installed")

try:
    import sqlalchemy
    print("✓ sqlalchemy is installed")
except ImportError:
    print("✗ sqlalchemy is not installed")

try:
    import tqdm
    print("✓ tqdm is installed")
except ImportError:
    print("✗ tqdm is not installed")

try:
    import wrestlerank
    print("✓ wrestlerank is installed")
except ImportError:
    print("✗ wrestlerank is not installed")

print("\nTest complete!") 