import sqlite3
import os
import sys
import datetime

def check_rankings(weight_class=None, date=None):
    """Check the current rankings in the database."""
    # Initialize the database connection
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wrestlerank.db')), 'wrestlerank.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    try:
        cursor = conn.cursor()
        
        # Get all available weight classes if none specified
        if not weight_class:
            cursor.execute("SELECT DISTINCT weight_class FROM wrestler_rankings ORDER BY weight_class")
            weight_classes = [row['weight_class'] for row in cursor.fetchall()]
            print(f"Available weight classes: {', '.join(weight_classes)}")
            return
        
        # Get all available dates for the weight class if none specified
        if not date:
            cursor.execute(
                "SELECT DISTINCT date FROM wrestler_rankings WHERE weight_class = ? ORDER BY date DESC",
                (weight_class,)
            )
            dates = [row['date'] for row in cursor.fetchall()]
            print(f"Available dates for weight class {weight_class}: {', '.join(dates)}")
            
            if dates:
                # Use the most recent date
                date = dates[0]
                print(f"Using most recent date: {date}")
            else:
                print(f"No rankings found for weight class {weight_class}")
                return
        
        # Get the rankings for the specified weight class and date
        cursor.execute(
            """
            SELECT r.wrestler_id, r.rank, r.date, r.last_updated, w.name
            FROM wrestler_rankings r
            LEFT JOIN wrestlers w ON r.wrestler_id = w.id
            WHERE r.weight_class = ? AND r.date = ?
            ORDER BY r.rank
            """,
            (weight_class, date)
        )
        
        rankings = cursor.fetchall()
        
        if not rankings:
            print(f"No rankings found for weight class {weight_class} on date {date}")
            return
        
        print(f"\nRankings for weight class {weight_class} on date {date}:")
        print(f"{'Rank':<5} {'Wrestler ID':<15} {'Name':<30} {'Last Updated':<30}")
        print("-" * 80)
        
        for ranking in rankings:
            name = ranking['name'] if ranking['name'] else 'Unknown'
            print(f"{ranking['rank']:<5} {ranking['wrestler_id']:<15} {name:<30} {ranking['last_updated']}")
        
        print(f"\nTotal rankings: {len(rankings)}")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        weight_class = sys.argv[1]
        date = sys.argv[2] if len(sys.argv) > 2 else None
        check_rankings(weight_class, date)
    else:
        check_rankings() 