import os
import sqlite3
import sys
import re

def standardize_weight_classes():
    """Standardize all weight classes to just numbers (no prefix letters)."""
    # Initialize the database connection
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wrestlerank.db')
    
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # Get all weight classes
        cursor.execute("SELECT DISTINCT weight_class FROM wrestler_rankings ORDER BY weight_class")
        weight_classes = [row['weight_class'] for row in cursor.fetchall()]
        
        if not weight_classes:
            print("No rankings found in the database")
            return
        
        print(f"Current weight classes: {', '.join(weight_classes)}")
        
        # Group weight classes by their numeric value
        weight_class_groups = {}
        for wc in weight_classes:
            # Extract the numeric part
            match = re.search(r'(\d+)', wc)
            if match:
                numeric_value = match.group(1)
                if numeric_value not in weight_class_groups:
                    weight_class_groups[numeric_value] = []
                weight_class_groups[numeric_value].append(wc)
        
        print("\nWeight class groups:")
        for numeric, variants in weight_class_groups.items():
            print(f"  {numeric}: {', '.join(variants)}")
        
        # Begin a transaction
        cursor.execute("BEGIN TRANSACTION")
        
        # Update each weight class to its numeric value
        updated_count = 0
        for numeric, variants in weight_class_groups.items():
            for variant in variants:
                if variant != numeric:
                    # Get all dates for this variant
                    cursor.execute(
                        "SELECT DISTINCT date FROM wrestler_rankings WHERE weight_class = ?",
                        (variant,)
                    )
                    dates = [row['date'] for row in cursor.fetchall()]
                    
                    for date in dates:
                        # Check if there are already rankings for the numeric weight class on this date
                        cursor.execute(
                            "SELECT COUNT(*) as count FROM wrestler_rankings WHERE weight_class = ? AND date = ?",
                            (numeric, date)
                        )
                        existing_count = cursor.fetchone()['count']
                        
                        if existing_count > 0:
                            print(f"Warning: {numeric} already has {existing_count} rankings for date {date}")
                            print(f"  Deleting {variant} rankings for date {date}")
                            
                            # Delete the variant rankings for this date
                            cursor.execute(
                                "DELETE FROM wrestler_rankings WHERE weight_class = ? AND date = ?",
                                (variant, date)
                            )
                        else:
                            # Update the variant to the numeric value
                            print(f"Updating {variant} to {numeric} for date {date}")
                            cursor.execute(
                                "UPDATE wrestler_rankings SET weight_class = ? WHERE weight_class = ? AND date = ?",
                                (numeric, variant, date)
                            )
                            updated_count += 1
        
        # Commit the transaction
        conn.commit()
        
        print(f"\nUpdated {updated_count} weight classes to numeric values")
        
        # Verify the changes
        cursor.execute("SELECT DISTINCT weight_class FROM wrestler_rankings ORDER BY weight_class")
        new_weight_classes = [row['weight_class'] for row in cursor.fetchall()]
        
        print(f"New weight classes: {', '.join(new_weight_classes)}")
        
    except Exception as e:
        print(f"Error standardizing weight classes: {e}")
        # Rollback the transaction if there was an error
        try:
            conn.rollback()
        except:
            pass
    finally:
        conn.close()

def update_code_for_numeric_weight_classes():
    """Update code to use numeric weight classes."""
    # Path to the wrestlerank directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    wrestlerank_dir = os.path.join(current_dir, '..', 'wrestlerank')
    
    if not os.path.exists(wrestlerank_dir):
        print(f"Error: Wrestlerank directory not found at {wrestlerank_dir}")
        return
    
    # Find all Python files in the wrestlerank directory
    python_files = []
    for root, dirs, files in os.walk(wrestlerank_dir):
        for file in files:
            if file.endswith('.py'):
                python_files.append(os.path.join(root, file))
    
    # Also check files in the current directory
    for file in os.listdir(current_dir):
        if file.endswith('.py'):
            python_files.append(os.path.join(current_dir, file))
    
    if not python_files:
        print("No Python files found")
        return
    
    print(f"\nFound {len(python_files)} Python files")
    
    # Patterns to look for
    patterns = [
        r'[wW](\d+)',
        r'weight_class\.lower\(\)',
        r'weight_class\.startswith\([\'"]w[\'"]\)'
    ]
    
    # Check each file for weight class references
    for file_path in python_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            needs_update = False
            for pattern in patterns:
                if re.search(pattern, content):
                    needs_update = True
                    break
            
            if needs_update:
                print(f"\nFile needs update: {file_path}")
                
                # Update the content
                new_content = content
                
                # Replace weight_class with just weight_class
                new_content = re.sub(
                    r'weight_class\.lower\(\)',
                    'weight_class',
                    new_content
                )
                
                # Replace False checks
                new_content = re.sub(
                    r'weight_class\.startswith\([\'"]w[\'"]\)',
                    'False',  # Since we're removing all 'w' prefixes
                    new_content
                )
                
                # Replace code that extracts weight class from filename
                if 'direct_import.py' in file_path:
                    # Update the weight class extraction code
                    new_content = re.sub(
                        r'match = re\.search\(r\'\[wW\]\?\\d\+\', filename\)[\s\S]*?weight_class = f"w{match\.group\(1\)}"',
                        'match = re.search(r\'(\\d+)\', filename)\n            if match:\n                weight_class = match.group(1)',
                        new_content
                    )
                
                # Write the updated content back to the file
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                
                print(f"  Updated {file_path}")
            
        except Exception as e:
            print(f"Error checking {file_path}: {e}")

def update_direct_import():
    """Update direct_import.py to use numeric weight classes."""
    file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'direct_import.py')
    
    if not os.path.exists(file_path):
        print(f"Error: direct_import.py not found at {file_path}")
        return
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Update the weight class extraction code
        new_content = content.replace(
            """# If not in JSON, try to extract from filename
        if not weight_class:
            filename = os.path.basename(json_file)
            match = re.search(r'[wW]?(\\d+)', filename)
            if match:
                weight_class = f"w{match.group(1)}" """,
            
            """# If not in JSON, try to extract from filename
        if not weight_class:
            filename = os.path.basename(json_file)
            match = re.search(r'(\\d+)', filename)
            if match:
                weight_class = match.group(1)"""
        )
        
        # Remove any code that converts weight class to lowercase
        new_content = new_content.replace(
            "# Normalize weight class to lowercase\n    weight_class = weight_class",
            "# Ensure weight class is a string\n    weight_class = str(weight_class)"
        )
        
        # Write the updated content back to the file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print(f"Updated {file_path}")
        
    except Exception as e:
        print(f"Error updating direct_import.py: {e}")

if __name__ == "__main__":
    print("=== Standardizing Weight Classes ===")
    standardize_weight_classes()
    
    print("\n=== Updating Code for Numeric Weight Classes ===")
    update_code_for_numeric_weight_classes()
    
    print("\n=== Updating direct_import.py ===")
    update_direct_import()
    
    print("\n=== All Done! ===")
    print("Weight classes have been standardized to numeric values.")
    print("Try importing rankings and generating the matrix again:")
    print("  .\\run.ps1 import-rankings .\\_rankings-downloads\\106_rankings.json")
    print("  .\\run.ps1 matrix 106") 