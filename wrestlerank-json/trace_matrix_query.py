import sqlite3
import os
import sys
import datetime

def trace_matrix_query(weight_class):
    """Trace the database query used by the matrix code."""
    print(f"Tracing matrix query for weight class: {weight_class}")
    
    # Initialize the database connection
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wrestlerank.db')), 'wrestlerank.db')
    conn = sqlite3.connect(db_path)
    
    # Enable tracing of SQL statements
    def trace_callback(statement):
        if 'wrestler_rankings' in statement:
            print(f"SQL: {statement}")
    
    conn.set_trace_callback(trace_callback)
    
    try:
        # Try to import and run the matrix code
        try:
            from wrestlerank.matrix import matrix_generator
            print("Successfully imported matrix_generator")
            
            # Try to call the build_matrix function
            try:
                print("Calling build_matrix...")
                matrix_data = matrix_generator.build_matrix(
                    weight_class,
                    include_adjacent=True,
                    limit=10  # Limit to 10 wrestlers for testing
                )
                print("Successfully called build_matrix")
            except Exception as e:
                print(f"Error calling build_matrix: {e}")
        except ImportError as e:
            print(f"Error importing matrix_generator: {e}")
            
            # Try to find the matrix module
            wrestlerank_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wrestlerank')
            print(f"Looking for matrix module in: {wrestlerank_dir}")
            
            for root, dirs, files in os.walk(wrestlerank_dir):
                for file in files:
                    if 'matrix' in file.lower() and file.endswith('.py'):
                        print(f"Found potential matrix module: {os.path.join(root, file)}")
    
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        weight_class = sys.argv[1].lower()
        trace_matrix_query(weight_class)
    else:
        print("Usage: python trace_matrix_query.py <weight_class>")
        sys.exit(1) 