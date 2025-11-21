import os
import sqlite3
import sys
import datetime

def view_rankings(weight_class=None, date=None):
    """View rankings in the database."""
    # Initialize the database connection
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wrestlerank.db')
    
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # Get available weight classes
        cursor.execute("SELECT DISTINCT weight_class FROM wrestler_rankings ORDER BY weight_class")
        weight_classes = [row['weight_class'] for row in cursor.fetchall()]
        
        if not weight_classes:
            print("No rankings found in the database")
            return
        
        print(f"Available weight classes: {', '.join(weight_classes)}")
        
        # Get available dates
        cursor.execute("SELECT DISTINCT date FROM wrestler_rankings ORDER BY date DESC")
        dates = [row['date'] for row in cursor.fetchall()]
        
        if not dates:
            print("No rankings found in the database")
            return
        
        print(f"Available dates: {', '.join(dates)}")
        
        # If weight class is not provided, ask for it
        if not weight_class or weight_class not in weight_classes:
            if weight_class and weight_class not in weight_classes:
                print(f"Weight class '{weight_class}' not found in database")
            
            print("\nEnter a weight class to view rankings for:")
            for i, wc in enumerate(weight_classes):
                print(f"{i+1}: {wc}")
            
            choice = input("Enter your choice (number or weight class): ")
            
            try:
                choice_idx = int(choice) - 1
                if 0 <= choice_idx < len(weight_classes):
                    weight_class = weight_classes[choice_idx]
                else:
                    weight_class = choice
            except ValueError:
                weight_class = choice
        
        # If date is not provided, ask for it
        if not date or date not in dates:
            if date and date not in dates:
                print(f"Date '{date}' not found in database")
            
            print("\nEnter a date to view rankings for:")
            for i, d in enumerate(dates):
                print(f"{i+1}: {d}")
            
            choice = input("Enter your choice (number or date): ")
            
            try:
                choice_idx = int(choice) - 1
                if 0 <= choice_idx < len(dates):
                    date = dates[choice_idx]
                else:
                    date = choice
            except ValueError:
                date = choice
        
        # Get rankings for the selected weight class and date
        cursor.execute(
            """
            SELECT wr.rank, wr.wrestler_id, w.name
            FROM wrestler_rankings wr
            LEFT JOIN wrestlers w ON wr.wrestler_id = w.id
            WHERE wr.weight_class = ? AND wr.date = ?
            ORDER BY wr.rank
            """,
            (weight_class, date)
        )
        
        rankings = cursor.fetchall()
        
        if not rankings:
            print(f"No rankings found for weight class {weight_class} on date {date}")
            return
        
        print(f"\nRankings for {weight_class} on {date}:")
        print("-" * 60)
        print(f"{'Rank':<5} {'Wrestler ID':<15} {'Name':<40}")
        print("-" * 60)
        
        for ranking in rankings:
            name = ranking['name'] if ranking['name'] else "Unknown"
            print(f"{ranking['rank']:<5} {ranking['wrestler_id']:<15} {name:<40}")
        
        print("-" * 60)
        print(f"Total: {len(rankings)} wrestlers")
        
    except Exception as e:
        print(f"Error viewing rankings: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

if __name__ == "__main__":
    weight_class = sys.argv[1] if len(sys.argv) > 1 else None
    date = sys.argv[2] if len(sys.argv) > 2 else None
    
    view_rankings(weight_class, date) 