# PowerShell script to run WrestleRank commands

# Activate the virtual environment
if (Test-Path "venv\Scripts\Activate.ps1") {
    . .\venv\Scripts\Activate.ps1
} elseif (Test-Path "venv\bin\Activate.ps1") {
    . .\venv\bin\Activate.ps1
} else {
    Write-Host "Virtual environment not found. Please run setup.bat first."
    exit
}

# Get the command and arguments
$command = $args[0]
$restArgs = $args[1..$args.Length]

# Special handling for import-rankings command
if ($command -eq "import-rankings") {
    # Check if we have at least one argument (the file)
    if ($restArgs.Length -lt 1) {
        Write-Host "Usage: .\run.ps1 import-rankings <json_file> [--weight-class <weight_class>]"
        exit
    }
    
    $jsonFile = $restArgs[0]
    
    # Check if the file exists
    if (-not (Test-Path $jsonFile)) {
        Write-Host "Error: File not found: $jsonFile"
        exit
    }
    
    # Extract weight class from arguments if provided
    $weightClass = $null
    for ($i = 1; $i -lt $restArgs.Length; $i++) {
        if ($restArgs[$i] -eq "--weight-class" -and $i+1 -lt $restArgs.Length) {
            $weightClass = $restArgs[$i+1]
            Write-Host "Using provided weight class: $weightClass"
            break
        }
    }
    
    # Get the full path to the script
    $scriptPath = Join-Path $PSScriptRoot "import_rankings.py"
    
    # Check if the script exists
    if (-not (Test-Path $scriptPath)) {
        Write-Host "Error: Import script not found at: $scriptPath"
        Write-Host "Creating the script now..."
        
        # Create the import_rankings.py script
        $scriptContent = @'
import json
import sqlite3
import datetime
import os
import sys

def import_rankings(json_file, weight_class=None):
    """Import rankings from a JSON file."""
    try:
        # Read the JSON file
        with open(json_file, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Could not parse JSON file: {e}")
        return
    
    # Use the weight class from the command line if provided, otherwise from the JSON
    if not weight_class:
        weight_class = data.get('weight_class')
    
    rankings = data.get('rankings', [])
    
    if not weight_class or not rankings:
        print("Invalid rankings file: missing weight_class or rankings data")
        return
    
    # Normalize weight class to lowercase
    weight_class = weight_class.lower()
    
    print(f"Importing rankings for {weight_class}")
    
    # Initialize the database connection
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wrestlerank.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    try:
        # Format the date as seen in the sample record: "030425-optimal"
        today = datetime.datetime.now().strftime('%m%d%y-manual')
        today_formatted = datetime.datetime.now().strftime('%Y-%m-%d')
        # Format last_updated as seen in the sample: "2025-03-12T13:04:18.622295"
        now = datetime.datetime.now().isoformat()
        
        print(f"Using date: {today_formatted}")
        print(f"Date format for DB: {today}")
        print(f"Last updated format: {now}")
        
        # Insert the rankings
        cursor = conn.cursor()
        
        # Check the schema of the wrestler_rankings table
        cursor.execute("PRAGMA table_info(wrestler_rankings)")
        columns = cursor.fetchall()
        column_names = [col['name'] for col in columns]
        print(f"Table columns: {column_names}")
        
        # Begin a transaction
        cursor.execute("BEGIN TRANSACTION")
        
        # Delete any existing rankings for this weight class and date
        cursor.execute(
            "DELETE FROM wrestler_rankings WHERE weight_class = ? AND date = ?",
            (weight_class, today)
        )
        
        # Insert the new rankings
        inserted_count = 0
        for ranking in rankings:
            try:
                wrestler_id = ranking.get('wrestler_id')
                rank = ranking.get('rank')
                
                if wrestler_id and rank:
                    # Create a complete record with all required fields
                    record = {
                        'wrestler_id': wrestler_id,
                        'weight_class': weight_class,
                        'rank': rank,
                        'date': today,
                        'last_updated': now,
                    }
                    
                    # Build the SQL dynamically based on the actual columns
                    columns_to_insert = []
                    values_to_insert = []
                    placeholders = []
                    
                    for col in column_names:
                        if col in record:
                            columns_to_insert.append(col)
                            values_to_insert.append(record[col])
                            placeholders.append('?')
                    
                    sql = f"INSERT INTO wrestler_rankings ({', '.join(columns_to_insert)}) VALUES ({', '.join(placeholders)})"
                    cursor.execute(sql, values_to_insert)
                    
                    inserted_count += 1
                else:
                    print(f"Warning: Skipping invalid ranking entry: {ranking}")
            except Exception as e:
                print(f"Error inserting ranking: {e}")
                print(f"Ranking data: {ranking}")
                print(f"SQL: {sql}")
                print(f"Values: {values_to_insert}")
        
        # Commit the transaction
        conn.commit()
        
        print(f"Successfully imported {inserted_count} rankings for {weight_class} with date {today}")
    
    except Exception as e:
        print(f"Error importing rankings: {e}")
        # Rollback the transaction if there was an error
        try:
            conn.rollback()
        except:
            pass
    finally:
        # Close the database connection
        conn.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python import_rankings.py <json_file> [weight_class]")
        sys.exit(1)
    
    json_file = sys.argv[1]
    weight_class = sys.argv[2] if len(sys.argv) > 2 else None
    
    import_rankings(json_file, weight_class)
'@
       
       # Write the script to the file
       $scriptContent | Out-File -FilePath $scriptPath -Encoding utf8
       
       Write-Host "Script created successfully at: $scriptPath"
   }
   
   # Try the direct import script first
   $directImportPath = Join-Path $PSScriptRoot "direct_import.py"
   
   if (Test-Path $directImportPath) {
       Write-Host "Using direct import script..."
       python $directImportPath $jsonFile $weightClass
   } else {
       Write-Host "Direct import script not found, using regular import script..."
       python $scriptPath $jsonFile $weightClass
   }
    exit
}

# For all other commands, pass to the Python module
# Check if we need to use the CLI module
if (Test-Path "wrestlerank\cli.py") {
    python -m wrestlerank.cli $command $restArgs
} elseif (Test-Path "wrestlerank\__main__.py") {
    python -m wrestlerank $command $restArgs
} else {
    Write-Host "Error: Could not find the CLI module. Please check your installation."
    exit 1
} 