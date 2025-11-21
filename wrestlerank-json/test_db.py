"""
Test script to verify the database functionality.
"""

from wrestlerank.db import sqlite_db

print("Testing database functionality...")

# Initialize database
sqlite_db.init_db("test.db")
sqlite_db.create_tables()

# Add a team
team_id = sqlite_db.add_team("Test Team", "TEST", "FL")
print(f"Added team with ID: {team_id}")

# Add a wrestler
wrestler_id = sqlite_db.add_wrestler("John Doe", team_id, "W150")
print(f"Added wrestler with ID: {wrestler_id}")

# Get wrestlers
wrestlers = sqlite_db.get_wrestlers_by_weight_class("W150")
print(f"Found {len(wrestlers)} wrestlers in weight class W150")

# Close database
sqlite_db.close_db()

print("Database test completed successfully!") 