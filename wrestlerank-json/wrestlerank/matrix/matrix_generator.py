"""
Matrix generator for head-to-head wrestler comparisons.
"""

from wrestlerank.db import sqlite_db

def build_matrix(weight_class, include_adjacent=True, limit=0, use_rankings=True):
    """
    Build the matrix data structure for a weight class.
    
    Args:
        weight_class: The weight class to build the matrix for
        include_adjacent: Whether to include adjacent weight classes for relationship calculations
        limit: Maximum number of wrestlers to include (0 for all)
        use_rankings: Whether to sort by official rankings instead of win percentage
    """
    sqlite_db.init_db()
    
    try:
        # Get all ACTIVE wrestlers in THIS weight class only
        cursor = sqlite_db.conn.cursor()
        
        # Get the most recent rankings date for this weight class
        if use_rankings:
            cursor.execute(
                """
                SELECT MAX(date) as latest_date
                FROM wrestler_rankings
                WHERE weight_class = ?
                """,
                (weight_class,)
            )
            latest_date = cursor.fetchone()['latest_date']
            
            if not latest_date:
                # No rankings found, fall back to win percentage
                print(f"No rankings found for {weight_class}, falling back to win percentage")
                use_rankings = False
            else:
                print(f"Using rankings from {latest_date} for {weight_class}")
                
                # Count how many wrestlers have rankings
                cursor.execute(
                    """
                    SELECT COUNT(*) as count
                    FROM wrestler_rankings
                    WHERE weight_class = ? AND date = ?
                    """,
                    (weight_class, latest_date)
                )
                rank_count = cursor.fetchone()['count']
                print(f"Found {rank_count} wrestlers with rankings")
        
        # Build query based on whether to use rankings
        if use_rankings:
            # Join with wrestler_rankings using external_id
            query = """
                SELECT w.*, r.rank
                FROM wrestlers w
                LEFT JOIN wrestler_rankings r ON w.external_id = r.wrestler_id 
                   AND r.weight_class = ? AND r.date = ?
                WHERE w.weight_class = ?
                AND w.active_team = 1
                ORDER BY r.rank IS NULL, r.rank ASC, w.win_percentage DESC
            """
            params = (weight_class, latest_date, weight_class)
        else:
            query = """
                SELECT w.*, NULL as rank
                FROM wrestlers w
                WHERE w.weight_class = ?
                AND w.active_team = 1
                ORDER BY w.win_percentage DESC
            """
            params = (weight_class,)
        
        # Add limit if specified
        if limit > 0:
            query += f" LIMIT {limit}"
            
        cursor.execute(query, params)
        wrestlers = cursor.fetchall()
        
        # Get wrestler IDs for relationship lookup
        wrestler_ids = [w['external_id'] for w in wrestlers]
        
        # If no wrestlers found, return empty matrix
        if not wrestler_ids:
            return {
                'weight_class': weight_class,
                'wrestlers': [],
                'matrix': {},
                'common_opponent_paths': {}
            }
        
        placeholders = ','.join(['?'] * len(wrestler_ids))
        
        # Get all relationships between these wrestlers
        # Note: We don't filter by weight_class here because relationships
        # might have been built considering matches at adjacent weight classes
        cursor.execute(
            f"""
            SELECT * FROM wrestler_relationships 
            WHERE wrestler1_id IN ({placeholders}) 
            AND wrestler2_id IN ({placeholders})
            """,
            wrestler_ids + wrestler_ids
        )
        relationships = cursor.fetchall()
        
        # Build the matrix data structure
        matrix = {}
        for relationship in relationships:
            w1 = relationship['wrestler1_id']
            w2 = relationship['wrestler2_id']
            
            if relationship['direct_wins'] > relationship['direct_losses']:
                result = 'win'
            elif relationship['direct_losses'] > relationship['direct_wins']:
                result = 'loss'
            elif relationship['direct_wins'] > 0:
                result = 'split'
            elif relationship['common_opp_wins'] > relationship['common_opp_losses']:
                result = 'common_win'
            elif relationship['common_opp_losses'] > relationship['common_opp_wins']:
                result = 'common_loss'
            else:
                result = None
                
            matrix[(w1, w2)] = result
            
        # Get common opponent paths
        cursor.execute(
            f"""
            SELECT c.*, 
                   w.name as opponent_name,
                   m1.date as match1_date, m1.result as match1_result,
                   m2.date as match2_date, m2.result as match2_result,
                   c.wrestler1_id, c.wrestler2_id
            FROM common_opponent_paths c
            JOIN wrestlers w ON c.common_opponent_id = w.external_id
            JOIN matches m1 ON c.match1_id = m1.external_id
            JOIN matches m2 ON c.match2_id = m2.external_id
            WHERE c.wrestler1_id IN ({placeholders}) 
            AND c.wrestler2_id IN ({placeholders})
            """,
            wrestler_ids + wrestler_ids
        )
        
        # Build a dictionary of paths
        common_opponent_paths = {}
        for row in cursor.fetchall():
            key = (row['wrestler1_id'], row['wrestler2_id'])
            if key not in common_opponent_paths:
                common_opponent_paths[key] = []
                
            common_opponent_paths[key].append({
                'opponent_id': row['common_opponent_id'],
                'opponent_name': row['opponent_name'],
                'date': row['match1_date'],
                'wrestler1_name': next(w['name'] for w in wrestlers if w['external_id'] == row['wrestler1_id']),
                'wrestler2_name': next(w['name'] for w in wrestlers if w['external_id'] == row['wrestler2_id']),
                'result1': row['match1_result'],
                'result2': row['match2_result']
            })
        
        # Create the final data structure
        print(f"Found {len(wrestlers)} active wrestlers in {weight_class}")
        print(f"Found {len(relationships)} relationships")
        print(f"Built matrix with {len(matrix)} entries")
        return {
            'weight_class': weight_class,
            'wrestlers': wrestlers,
            'matrix': matrix,
            'common_opponent_paths': common_opponent_paths
        }
    finally:
        sqlite_db.close_db()

def generate_html(matrix_data, weight_class):
    """Generate HTML for the head-to-head matrix."""
    wrestlers = matrix_data['wrestlers']
    matrix = matrix_data['matrix']
    common_opponent_paths = matrix_data.get('common_opponent_paths', {})
    
    # Initialize database connection for match details
    sqlite_db.init_db()
    
    try:
        # Start building the HTML
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Head-to-Head Matrix: {weight_class}</title>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 20px;
                }}
                table {{
                    border-collapse: collapse;
                    font-size: 14px;
                }}
                th, td {{
                    border: 1px solid #ddd;
                    padding: 8px;
                    text-align: center;
                }}
                th {{
                    background-color: #f2f2f2;
                    position: sticky;
                    top: 0;
                    font-weight: normal;
                    z-index: 5;
                }}
                th.rotate {{
                    height: 140px;
                    white-space: nowrap;
                    padding: 0 !important;
                }}
                th.rotate > div {{
                    transform: 
                        /* Magic Numbers */
                        translate(0px, 51px)
                        /* 45 is really 360 - 45 */
                        rotate(270deg);
                    width: 30px;
                }}
                th.rotate > div > span {{
                    padding: 5px 10px;
                    display: inline-block;
                    border-bottom: 1px solid #ccc;
                }}
                .same-wrestler {{
                    background-color: #e0e0e0;  /* Grey background for same wrestler cells */
                }}
                .sticky-col {{
                    position: sticky;
                    left: 0;
                    background-color: #f2f2f2;
                    z-index: 20;
                }}
                .rank-col {{
                    position: sticky;
                    left: 0;
                    background-color: #f2f2f2;
                    z-index: 20;
                }}
                .wrestler-col {{
                    position: sticky;
                    left: 40px;  /* Width of the rank column */
                    background-color: #f2f2f2;
                    z-index: 20;
                }}
                .wrestler-name {{
                    color: #0066cc;
                    text-decoration: underline;
                    cursor: pointer;
                    display: inline-block;
                    vertical-align: middle;
                }}
                .rank-arrows {{
                    display: inline-block;
                    margin-left: 5px;
                    vertical-align: middle;
                }}
                .rank-arrow {{
                    cursor: pointer;
                    padding: 2px 5px;
                    margin: 0 2px;
                    border: 1px solid #ddd;
                    border-radius: 3px;
                    background: #f8f8f8;
                }}
                .rank-arrow:hover {{
                    background: #e8e8e8;
                }}
                .matrix-cell {{
                    width: 40px !important;
                    height: 40px !important;
                    text-align: center;
                    font-weight: bold;
                }}
                .direct_win {{
                    background-color: #b3ffb3;  /* Light green */
                }}
                .direct_loss {{
                    background-color: #ffb3b3;  /* Light red */
                }}
                .common_win {{
                    background-color: #ccffcc;  /* Lighter green */
                }}
                .common_loss {{
                    background-color: #ffcccc;  /* Lighter red */
                }}
                .tooltip {{
                    display: none;
                    position: absolute;
                    background-color: #333;
                    color: white;
                    padding: 10px;
                    border-radius: 5px;
                    z-index: 100;
                    max-width: 300px;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.2);
                }}
                .info-cell:hover .tooltip {{
                    display: block;
                }}
                #save-button {{
                    position: fixed;
                    bottom: 20px;
                    right: 20px;
                    padding: 10px 20px;
                    background-color: #4CAF50;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    cursor: pointer;
                    font-size: 16px;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.2);
                }}
                #save-button:hover {{
                    background-color: #45a049;
                }}
                #rank-modal {{
                    display: none;
                    position: fixed;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 100%;
                    background-color: rgba(0,0,0,0.5);
                    z-index: 1000;
                }}
                .modal-content {{
                    background-color: white;
                    margin: 15% auto;
                    padding: 20px;
                    border-radius: 5px;
                    width: 300px;
                    text-align: center;
                }}
                .close-button {{
                    color: #aaa;
                    float: right;
                    font-size: 28px;
                    font-weight: bold;
                    cursor: pointer;
                }}
                .close-button:hover {{
                    color: black;
                }}
            

        /* Make relationship cells square */
        .matrix-table td.relationship-cell {{
            width: 40px;
            height: 40px;
            min-width: 40px;
            min-height: 40px;
            max-width: 40px;
            max-height: 40px;
            text-align: center;
            vertical-align: middle;
        }}
        
        /* Fix header row to stay on top when scrolling */
        .matrix-table {{
            position: relative;
        }}
        
        .matrix-table thead {{
            position: sticky;
            top: 0;
            z-index: 10;
            background-color: white;
        }}
        
        .matrix-table th.wrestler-header, 
        .matrix-table th.rank-header {{
            position: sticky;
            top: 0;
            z-index: 20;
            background-color: white;
        }}
        
        /* Add some spacing and borders for better readability */
        .matrix-table {{
            border-collapse: separate;
            border-spacing: 0;
            border: 1px solid #ddd;
        }}
        
        .matrix-table th, 
        .matrix-table td {{
            border: 1px solid #ddd;
            padding: 8px;
        }}
        
        /* Highlight diagonal cells */
            .matrix-table td.diagonal-cell {{
            background-color: #f2f2f2;
        }}
        </style>
            <script>
                // Define the save rankings function in the global scope
                function saveRankings() {{
                    console.log("Save button clicked");
                    
                    try {{
                        // Get all wrestler rows
                        const table = document.getElementById('matrix-table');
                        const rows = table.querySelectorAll('tr');
                        
                        // Collect ranking data
                        const rankingData = [];
                        for (let i = 1; i < rows.length; i++) {{
                            const nameCell = rows[i].querySelector('.wrestler-name');
                            if (nameCell) {{
                                rankingData.push({{
                                    wrestler_id: nameCell.dataset.id,
                                    rank: i
                                }});
                            }}
                        }}
                        
                        console.log("Rankings data:", rankingData);
                        
                        // Create JSON data
                        const jsonData = JSON.stringify({{
                            weight_class: '{weight_class}',
                            rankings: rankingData
                        }}, null, 2);
                        
                        // Create download
                        const blob = new Blob([jsonData], {{type: 'application/json'}});
                        const url = URL.createObjectURL(blob);
                        
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = '{weight_class}_rankings.json';
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);
                        
                        alert("Rankings saved to {weight_class}_rankings.json");
                    }} catch (error) {{
                        console.error("Error saving rankings:", error);
                        alert("Error saving rankings: " + error.message);
                    }}
                    
                    return false; // Prevent default button behavior
                }}
            </script>
        </head>
        <body>
            <h1>Head-to-Head Matrix: {weight_class}</h1>
            <table id="matrix-table">
        """
        
        # Add the header row with wrestler names
        html += "<tr><th class='rank-col'></th><th class='wrestler-col'>Wrestler</th><th>Win%</th><th>RPI</th>"
        
        # Rotated wrestler names in the header
        for wrestler in wrestlers:
            wrestler_id = wrestler['external_id']
            # Extract last name for header
            last_name = wrestler['name'].split()[-1] if ' ' in wrestler['name'] else wrestler['name']
            html += f"""
            <th class="rotate wrestler-header" data-id="{wrestler_id}">
                <div><span>{last_name}</span></div>
            </th>
            """
        
        html += "</tr>\n"
        
        # Add the data rows
        for i, wrestler1 in enumerate(wrestlers):
            w1_id = wrestler1['external_id']
            
            # Start a new row
            html += f"<tr><td class='rank-col'>{i+1}</td><td class='wrestler-col'>"
            
            # Add wrestler cell with name and rank arrows
            html += f"""
                <div style="display: flex; align-items: center;">
                    <span class="wrestler-name" data-id="{w1_id}" data-rank="{i+1}">
                        {wrestler1['name']}
                    </span>
                    <span class="rank-arrows">
                        <span class="rank-arrow up-arrow" data-id="{w1_id}" data-current-rank="{i+1}">&uarr;</span>
                        <span class="rank-arrow down-arrow" data-id="{w1_id}" data-current-rank="{i+1}">&darr;</span>
                    </span>
                </div>
            </td>
            """
            
            # Add win percentage and RPI
            win_pct = wrestler1['win_percentage'] if wrestler1['win_percentage'] is not None else 0
            rpi_val = wrestler1['rpi']
            rpi_str = f"{rpi_val:.3f}" if rpi_val is not None else ""
            html += f"<td>{win_pct}%</td><td>{rpi_str}</td>"
            
            # For each column (wrestler2)
            for j, wrestler2 in enumerate(wrestlers):
                w2_id = wrestler2['external_id']
                
                # If same wrestler, show X
                if w1_id == w2_id:
                    html += "<td class='same-wrestler'>X</td>"
                    continue
                    
                # Get the relationship between these wrestlers
                relationship = matrix.get((w1_id, w2_id))
                result = determine_relationship_display(relationship)
                
                if result == 'direct_win':
                    # Direct win - show the match result
                    match_details = get_match_details(w1_id, w2_id)
                    html += f'<td class="matrix-cell direct_win">{map_result_to_code(match_details["result"])}</td>'
                    
                elif result == 'direct_loss':
                    # Direct loss - show the match result
                    match_details = get_match_details(w2_id, w1_id)
                    html += f'<td class="matrix-cell direct_loss">{map_result_to_code(match_details["result"])}</td>'
                    
                elif result == 'common_win':
                    # Common opponent win - show tooltip with details
                    paths = common_opponent_paths.get((w1_id, w2_id), [])
                    tooltip = generate_tooltip(paths)
                    
                    html += f"""
                    <td class="matrix-cell common_win info-cell">
                        CO
                        <span class="tooltip">{tooltip}</span>
                    </td>
                    """
                    
                elif result == 'common_loss':
                    # For common losses, we need to look up the paths in the reverse direction
                    # because the common opponent paths are stored from the perspective of the winner
                    paths = common_opponent_paths.get((w2_id, w1_id), [])
                    
                    # We need to reverse the perspective in the tooltip
                    tooltip = generate_tooltip_reversed(paths, wrestler1['name'], wrestler2['name'])
                    
                    html += f"""
                    <td class="matrix-cell common_loss info-cell">
                        CO
                        <span class="tooltip">{tooltip}</span>
                    </td>
                    """
                    
                else:
                    # No relationship
                    html += '<td class="matrix-cell"></td>'
            
            html += "</tr>\n"
        
        html += """
            </table>
            
            <!-- Check if save button exists -->
            <div id="save-button-container" style="position: fixed; bottom: 20px; right: 20px;">
                <button id="save-button" onclick="saveRankings()" style="padding: 10px 20px; background-color: #4CAF50; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; box-shadow: 0 2px 5px rgba(0,0,0,0.2);">
                    Save Rankings
                </button>
            </div>
            
            <!-- Modal for setting specific rank -->
            <div id="rank-modal" class="modal">
                <div class="modal-content">
                    <span class="close-button">&times;</span>
                    <h2>Set Rank for <span id="selected-wrestler-name"></span></h2>
                    <input type="number" id="new-rank" min="1" step="1">
                    <button id="apply-rank">Apply</button>
                </div>
            </div>
            
            <script>
            let rows; // Define rows at the global scope

            document.addEventListener('DOMContentLoaded', function() {
                // Define rows here
                rows = document.querySelectorAll('#matrix-table tr');
                
                // Get the matrix table
                const table = document.getElementById('matrix-table');
                const saveButton = document.getElementById('save-button');
                const modal = document.getElementById('rank-modal');
                const closeButton = document.querySelector('.close-button');
                const newRankInput = document.getElementById('new-rank');
                const applyRankButton = document.getElementById('apply-rank');
                const selectedWrestlerNameElement = document.getElementById('selected-wrestler-name');
                
                // Store original rankings and current rankings
                const wrestlers = [];
                
                // Keep track of the original order when the page loaded
                let initialOrder = [];
                
                // Start from index 1 to skip header row
                for (let i = 1; i < rows.length; i++) {
                    const nameCell = rows[i].querySelector('.wrestler-name');
                    if (nameCell) {
                        wrestlers.push({
                            id: nameCell.dataset.id,
                            name: nameCell.textContent,
                            originalRank: parseInt(nameCell.dataset.rank),
                            currentRank: parseInt(nameCell.dataset.rank)
                        });
                        initialOrder.push(nameCell.dataset.id);
                    }
                }
                
                // Sort wrestlers by current rank
                wrestlers.sort((a, b) => a.currentRank - b.currentRank);
                
                // Handle up arrow click
                table.addEventListener('click', function(e) {
                    if (e.target.classList.contains('up-arrow')) {
                        const wrestlerId = e.target.dataset.id;
                        const currentRank = parseInt(e.target.dataset.currentRank);
                        
                        if (currentRank > 1) {
                            moveWrestler(wrestlerId, currentRank, currentRank - 1);
                        }
                    }
                });
                
                // Handle down arrow click
                table.addEventListener('click', function(e) {
                    if (e.target.classList.contains('down-arrow')) {
                        const wrestlerId = e.target.dataset.id;
                        const currentRank = parseInt(e.target.dataset.currentRank);
                        
                        if (currentRank < wrestlers.length) {
                            moveWrestler(wrestlerId, currentRank, currentRank + 1);
                        }
                    }
                });
                
                // Handle wrestler name click to open modal
                table.addEventListener('click', function(e) {
                    if (e.target.classList.contains('wrestler-name')) {
                        const wrestlerId = e.target.dataset.id;
                        const wrestler = wrestlers.find(w => w.id === wrestlerId);
                        
                        // Set up the modal
                        selectedWrestlerNameElement.textContent = wrestler.name;
                        newRankInput.value = wrestler.currentRank;
                        newRankInput.max = wrestlers.length;
                        
                        // Store the wrestler ID for later use
                        applyRankButton.dataset.wrestlerId = wrestlerId;
                        
                        // Show the modal
                        modal.style.display = 'block';
                    }
                });
                
                // Close modal when close button is clicked
                closeButton.addEventListener('click', function() {
                    modal.style.display = 'none';
                });
                
                // Close modal when clicking outside of it
                window.addEventListener('click', function(e) {
                    if (e.target === modal) {
                        modal.style.display = 'none';
                    }
                });
                
                // Apply new rank when button is clicked
                applyRankButton.addEventListener('click', function() {
                    const wrestlerId = this.dataset.wrestlerId;
                    const newRank = parseInt(newRankInput.value);
                    const wrestler = wrestlers.find(w => w.id === wrestlerId);
                    
                    if (newRank >= 1 && newRank <= wrestlers.length) {
                        moveWrestler(wrestlerId, wrestler.currentRank, newRank);
                        modal.style.display = 'none';
                    } else {
                        alert('Please enter a valid rank between 1 and ' + wrestlers.length);
                    }
                });
                
                // Function to move a wrestler to a new rank
                function moveWrestler(wrestlerId, fromRank, toRank) {
                    // Store the current order before making changes
                    const currentOrder = wrestlers.map(w => w.id);
                    
                    // Update the data structure
                    wrestlers.forEach(w => {
                        if (w.id === wrestlerId) {
                            w.currentRank = toRank;
                        } else if (fromRank < toRank && w.currentRank > fromRank && w.currentRank <= toRank) {
                            // Moving down, shift others up
                            w.currentRank--;
                        } else if (fromRank > toRank && w.currentRank < fromRank && w.currentRank >= toRank) {
                            // Moving up, shift others down
                            w.currentRank++;
                        }
                    });
                    
                    // Re-sort the wrestlers by current rank
                    wrestlers.sort((a, b) => a.currentRank - b.currentRank);
                    
                    // Reorder the table
                    reorderTable(currentOrder);
                }
                
                // Function to reorder the table based on current rankings
                function reorderTable(previousOrder) {
                    // If no previous order provided, use the current order
                    previousOrder = previousOrder || wrestlers.map(w => w.id);
                    
                    // Reorder the rows
                    const tbody = table.querySelector('tbody') || table;
                    
                    // Create an array from the rows (skip header)
                    const rowsArray = Array.from(rows).slice(1);
                    
                    // Sort rows based on wrestler ranks
                    rowsArray.sort((rowA, rowB) => {
                        const idA = rowA.querySelector('.wrestler-name').dataset.id;
                        const idB = rowB.querySelector('.wrestler-name').dataset.id;
                        
                        const rankA = wrestlers.find(w => w.id === idA).currentRank;
                        const rankB = wrestlers.find(w => w.id === idB).currentRank;
                        
                        return rankA - rankB;
                    });
                    
                    // Get the new order after sorting
                    const newOrder = rowsArray.map(row => {
                        return row.querySelector('.wrestler-name').dataset.id;
                    });
                    
                    // Update the rows with new ranks and reappend in correct order
                    rowsArray.forEach((row, index) => {
                        // Update rank number
                        row.querySelector('.rank-col').textContent = index + 1;
                        
                        // Update rank in arrows
                        const upArrow = row.querySelector('.up-arrow');
                        const downArrow = row.querySelector('.down-arrow');
                        const wrestlerName = row.querySelector('.wrestler-name');
                        
                        upArrow.dataset.currentRank = index + 1;
                        downArrow.dataset.currentRank = index + 1;
                        wrestlerName.dataset.rank = index + 1;
                        
                        // Re-append the row to maintain correct order
                        tbody.appendChild(row);
                    });
                    
                    // Reorder the header columns too
                    const headerRow = rows[0];
                    const headerCells = headerRow.querySelectorAll('.wrestler-header');
                    const headerCellsArray = Array.from(headerCells);
                    
                    // Create a map of id to header cell
                    const headerMap = {};
                    headerCellsArray.forEach(cell => {
                        headerMap[cell.dataset.id] = cell;
                    });
                    
                    // Remove existing header cells
                    headerCellsArray.forEach(cell => {
                        headerRow.removeChild(cell);
                    });
                    
                    // Append header cells in new order
                    newOrder.forEach(id => {
                        if (headerMap[id]) {
                            headerRow.appendChild(headerMap[id]);
                        }
                    });
                    
                    // Now we need to rearrange the matrix cells
                    if (previousOrder.toString() !== newOrder.toString()) {
                        rearrangeMatrixCells(previousOrder, newOrder, rows);
                    }
                }
                
                // Function to rearrange matrix cells when order changes
                function rearrangeMatrixCells(originalOrder, newOrder, rows) {
                    console.log("Rearranging cells from", originalOrder, "to", newOrder);
                    
                    // Create a copy of all cells in the matrix
                    const allCells = [];
                    for (let rowIdx = 1; rowIdx < rows.length; rowIdx++) {
                        const row = rows[rowIdx];
                        const rowWrestlerId = row.querySelector('.wrestler-name').dataset.id;
                        const cells = Array.from(row.cells).slice(4); // Skip rank, name, win%, RPI columns
                        
                        allCells.push({
                            rowId: rowWrestlerId,
                            cells: cells.map((cell, idx) => ({
                                html: cell.innerHTML,
                                className: cell.className,
                                colId: originalOrder[idx] || null
                            }))
                        });
                    }
                    
                    // Now rearrange the cells based on the new order
                    for (let rowIdx = 1; rowIdx < rows.length; rowIdx++) {
                        const row = rows[rowIdx];
                        const rowWrestlerId = row.querySelector('.wrestler-name').dataset.id;
                        const rowNewIdx = newOrder.indexOf(rowWrestlerId);
                        const rowOldIdx = originalOrder.indexOf(rowWrestlerId);
                        const cells = Array.from(row.cells).slice(4); // Skip rank, name, win%, RPI columns
                        
                        // For each cell in this row
                        for (let colIdx = 0; colIdx < cells.length; colIdx++) {
                            const colWrestlerId = newOrder[colIdx];
                            const colOldIdx = originalOrder.indexOf(colWrestlerId);
                            
                            // If this is a diagonal cell (same wrestler)
                            if (rowWrestlerId === colWrestlerId) {
                                cells[colIdx].className = 'same-wrestler';
                                cells[colIdx].innerHTML = 'X';
                            } 
                            // Otherwise, find the correct cell from the original matrix
                            else if (rowOldIdx >= 0 && colOldIdx >= 0) {
                                // Find the cell from the original matrix
                                const originalRowData = allCells.find(r => r.rowId === rowWrestlerId);
                                if (originalRowData) {
                                    cells[colIdx].innerHTML = originalRowData.cells[colOldIdx].html;
                                    cells[colIdx].className = originalRowData.cells[colOldIdx].className;
                                }
                            }
                        }
                    }
                }
            });
            </script>
        </body>
        </html>
        """
        
        return html
    finally:
        # Close the database connection when done
        sqlite_db.close_db()

def generate_tooltip(paths):
    """Generate tooltip HTML for common opponent paths."""
    if not paths:
        return "No common opponent details available"
    
    html = "<strong>Common Opponents:</strong><br>"
    
    for path in paths:
        html += f"""
        {path['opponent_name']} ({path['date']})<br>
        {path['wrestler1_name']} def. {path['opponent_name']} ({path['result1']})<br>
        {path['opponent_name']} def. {path['wrestler2_name']} ({path['result2']})<br>
        <hr>
        """
    
    return html.strip()

def generate_tooltip_reversed(paths, loser_name, winner_name):
    """Generate tooltip HTML for common opponent paths, with perspective reversed."""
    if not paths:
        return "No common opponent details available"
    
    html = "<strong>Common Opponents:</strong><br>"
    
    for path in paths:
        html += f"""
        {path['opponent_name']} ({path['date']})<br>
        {winner_name} def. {path['opponent_name']} ({path['result1']})<br>
        {path['opponent_name']} def. {loser_name} ({path['result2']})<br>
        <hr>
        """
    
    return html.strip()

def map_result_to_code(result):
    """Map result string to display code."""
    result_map = {
        'Fall': 'F',
        'Technical Fall': 'TF',
        'Major Decision': 'MD',
        'Decision': 'D',
        'Dec': 'D',
        'Default': 'DEF',
        'Forfeit': 'FF',
        'For.': 'FF',
        'MFFL': 'FF',
        'M. For.': 'FF',
        'SV-1': 'D',
        'Injury Default': 'INJ',
        'Disqualification': 'DQ'
    }
    
    # Handle abbreviated formats
    if result in ['F', 'TF', 'MD', 'D', 'DEF', 'FF', 'INJ', 'DQ']:
        return result
        
    return result_map.get(result, result)

def get_match_details(wrestler1_id, wrestler2_id):
    """Get details of matches between two wrestlers."""
    cursor = sqlite_db.conn.cursor()
    
    # Find direct matches between these wrestlers
    cursor.execute(
        """
        SELECT * FROM matches 
        WHERE ((wrestler1_id = ? AND wrestler2_id = ?) OR (wrestler1_id = ? AND wrestler2_id = ?))
        ORDER BY date DESC
        LIMIT 1
        """,
        (wrestler1_id, wrestler2_id, wrestler2_id, wrestler1_id)
    )
    
    match = cursor.fetchone()
    if match:
        # Convert to a regular dictionary
        return dict(match)
    
    return {'result': ''}  # Default empty result if no match found 

def determine_relationship_display(relationship):
    """
    Determine how to display a relationship in the matrix.
    
    Args:
        relationship: The relationship object or string from the matrix data
        
    Returns:
        A string indicating how to display the relationship: 
        'direct_win', 'direct_loss', 'split', 'common_win', 'common_loss', or None
    """
    # Handle when relationship is already a string result
    if isinstance(relationship, str):
        if relationship == 'win':
            return 'direct_win'
        elif relationship == 'loss':
            return 'direct_loss'
        elif relationship == 'split':
            return 'split'
        elif relationship == 'common_win':
            return 'common_win'
        elif relationship == 'common_loss':
            return 'common_loss'
        return None
    
    # Handle when relationship is None
    if not relationship:
        return None
        
    # Handle when relationship is a dictionary with direct_wins/losses and common_opp_wins/losses
    if isinstance(relationship, dict):
        direct_wins = relationship.get('direct_wins', 0)
        direct_losses = relationship.get('direct_losses', 0)
        common_opp_wins = relationship.get('common_opp_wins', 0)
        common_opp_losses = relationship.get('common_opp_losses', 0)
        
        if direct_wins > direct_losses:
            return 'direct_win'
        elif direct_losses > direct_wins:
            return 'direct_loss'
        elif direct_wins > 0:  # Both have the same number of wins/losses but not zero
            return 'split'
        elif common_opp_wins > common_opp_losses:
            return 'common_win'
        elif common_opp_losses > common_opp_wins:
            return 'common_loss'
    
    return None 