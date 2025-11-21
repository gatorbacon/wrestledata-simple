import sqlite3
import os
import sys
import datetime

def debug_matrix_command(weight_class):
    """Debug the matrix command execution."""
    print(f"Debugging matrix command for weight class: {weight_class}")
    
    # Initialize the database connection
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wrestlerank.db')), 'wrestlerank.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    try:
        cursor = conn.cursor()
        
        # Get all available dates for the weight class
        cursor.execute(
            "SELECT DISTINCT date FROM wrestler_rankings WHERE weight_class = ? ORDER BY date DESC",
            (weight_class,)
        )
        dates = [row['date'] for row in cursor.fetchall()]
        
        if not dates:
            print(f"No rankings found for weight class {weight_class}")
            return
        
        print(f"Available dates for weight class {weight_class}: {', '.join(dates)}")
        
        # Check if there's a date parameter in the matrix command
        # This is a guess based on common patterns - we'll need to adjust based on actual code
        matrix_date_param = None
        
        # Try to find the matrix module to see if it has a date parameter
        try:
            from wrestlerank.matrix import generate_matrix
            # Check if the function has a date parameter
            import inspect
            sig = inspect.signature(generate_matrix)
            if 'date' in sig.parameters:
                print("Matrix function has a date parameter")
            else:
                print("Matrix function does not have a date parameter")
                # Print the parameters it does have
                print(f"Parameters: {list(sig.parameters.keys())}")
        except ImportError:
            print("Could not import the matrix module")
        
        # If there's no date parameter, the code might be using a hardcoded date or the most recent date
        print("\nChecking for hardcoded dates in the database queries...")
        
        # Get all unique dates in the database
        cursor.execute("SELECT DISTINCT date FROM wrestler_rankings ORDER BY date")
        all_dates = [row['date'] for row in cursor.fetchall()]
        print(f"All dates in the database: {', '.join(all_dates)}")
        
        # Check if there are any rankings with a specific format (e.g., ending with "-optimal")
        optimal_dates = [d for d in all_dates if d.endswith("-optimal")]
        if optimal_dates:
            print(f"Found dates with '-optimal' suffix: {', '.join(optimal_dates)}")
            print("The matrix code might be specifically looking for these dates")
        
        # Check the most recent date for each format
        date_formats = {}
        for date in all_dates:
            if "-" in date:
                format_type = date.split("-")[1]
                if format_type not in date_formats or date > date_formats[format_type]:
                    date_formats[format_type] = date
        
        print("\nMost recent date for each format:")
        for format_type, date in date_formats.items():
            print(f"  {format_type}: {date}")
        
        # Check if there's a specific date format that the matrix code might be using
        if "optimal" in date_formats:
            print(f"\nThe matrix code might be using the most recent 'optimal' date: {date_formats['optimal']}")
            
            # Get the rankings for this date
            cursor.execute(
                """
                SELECT r.wrestler_id, r.rank, w.name
                FROM wrestler_rankings r
                LEFT JOIN wrestlers w ON r.wrestler_id = w.id
                WHERE r.weight_class = ? AND r.date = ?
                ORDER BY r.rank
                LIMIT 10
                """,
                (weight_class, date_formats['optimal'])
            )
            
            rankings = cursor.fetchall()
            
            print(f"\nTop 10 rankings for weight class {weight_class} on date {date_formats['optimal']}:")
            for ranking in rankings:
                name = ranking['name'] if ranking['name'] else 'Unknown'
                print(f"{ranking['rank']}: {name} ({ranking['wrestler_id']})")
        
        # Compare with the most recent manual date
        if "manual" in date_formats:
            print(f"\nMost recent 'manual' date: {date_formats['manual']}")
            
            # Get the rankings for this date
            cursor.execute(
                """
                SELECT r.wrestler_id, r.rank, w.name
                FROM wrestler_rankings r
                LEFT JOIN wrestlers w ON r.wrestler_id = w.id
                WHERE r.weight_class = ? AND r.date = ?
                ORDER BY r.rank
                LIMIT 10
                """,
                (weight_class, date_formats['manual'])
            )
            
            rankings = cursor.fetchall()
            
            print(f"\nTop 10 rankings for weight class {weight_class} on date {date_formats['manual']}:")
            for ranking in rankings:
                name = ranking['name'] if ranking['name'] else 'Unknown'
                print(f"{ranking['rank']}: {name} ({ranking['wrestler_id']})")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        weight_class = sys.argv[1].lower()
        debug_matrix_command(weight_class)
    else:
        print("Usage: python debug_matrix.py <weight_class>")
        sys.exit(1) 