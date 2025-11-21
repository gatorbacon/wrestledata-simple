## WrestleRank (2025–2026)

A SQLite-backed pipeline to import high school wrestling data (teams, wrestlers, matches), compute head-to-head relationships (direct and common opponents), visualize them in an interactive matrix, and save rankings (manual from the UI or optimized automatically).

### What you’ll do
- Initialize a fresh DB for the new season
- Import your 2025–2026 CSVs
- Build relationships
- Generate and review the matrix
- Save or auto-generate rankings
- Diagnose and fix issues as the source site format evolves

---

### Prerequisites
- Python 3.10+ (3.11 recommended) on macOS (Darwin 24.x)
- pip and venv
- Basic CSVs exported from the new website

Install dependencies (no `requirements.txt` yet):

python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install click flask tqdm numpyIf you plan to use the optimizer: `numpy` is required. If you see dependency errors, install missing packages as they arise.

---

### Project layout (key dirs)
- `wrestlerank/cli.py`: main CLI entry point
- `wrestlerank/db/sqlite_db.py`: SQLite schema and helpers
- `wrestlerank/migration/import_csv.py`: CSV importers
- `wrestlerank/matrix/relationship_manager.py`: relationship computation
- `wrestlerank/matrix/matrix_generator.py`: matrix builder + HTML
- `wrestlerank/ranking/optimal_ranker.py`: optimization-based rankings
- `wrestlerank/web/server.py`: minimal endpoint to save rankings via CLI (optional)

---

### Fresh season setup
Start from a clean database to avoid cross-season mixing.

# From repo root
python -m wrestlerank.cli reset --force
python -m wrestlerank.cli initBy default this uses `wrestlerank.db` in the working directory. You can pass `--db-path /absolute/path/to.db` to most commands if you prefer a custom location.

---

### Prepare CSVs (source website may have changed)
Place CSVs in a directory like `/path/to/data/2025-2026/`. The code expects these columns (names are case-insensitive where noted):

- Teams (`team-list.csv`)
  - Required: `name`
  - Optional: `team_id`, `abbr`, `state`

- Wrestlers (the importer is tolerant; recommended file name `wrestler-list.csv` or `wrestler-list-CLEAN.csv`)
  - Required: `wrestlerID`, `name`, `weight`, `team`
  - Optional: `activeTeam` (true/false), `win_percentage` (0-100), `bonus_percentage`, `rpi`, `matches`, `days_since_last_match`

- Matches (recommended `match-results.csv` or `match-results-all.csv`)
  - Required: `uid`, `weight`, `winnerID`, `winner`, `winningTeam`, `loserID`, `loser`, `losingTeam`
  - Optional: `result` (e.g., Fall, Dec, TF, MD, FF, etc.)
  - Note: `uid` should encode date as `mmddyyyy-...`; importer extracts the date from this segment

If the site changed column names, you can:
- Pre-transform your CSV headers, or
- Update the import mapping in `wrestlerank/migration/import_csv.py` (functions: `import_teams`, `import_wrestlers`, `import_matches`).

---

### Import data (two options)

1) One-shot migration (expects specific filenames):
python -m wrestlerank.cli migrate /path/to/data/2025-20262) Step-by-step (recommended when formats changed):
# Teams
python -m wrestlerank.cli import-teams /path/to/data/2025-2026/team-list.csv

# Wrestlers
python -m wrestlerank.cli import-wrestlers /path/to/data/2025-2026/wrestler-list.csv \
  --team-csv /path/to/data/2025-2026/team-list.csv

# Matches (limit first run to verify)
python -m wrestlerank.cli import-matches /path/to/data/2025-2026/match-results.csv --limit 1000
# Remove --limit after verifyingQuick test flow (teams + wrestlers + limited matches + build direct relationships only):
python -m wrestlerank.cli quick-test /path/to/data/2025-2026 --match-limit 3000---

### Build relationships (global or per weight class)
Global, incremental-safe (tracks a `processed` flag; includes batched transactions):
python -m wrestlerank.cli build-relationships
# Or force reprocessing all matches:
python -m wrestlerank.cli build-relationships --all
# To reset relationship tables first:
python -m wrestlerank.cli build-relationships --resetPer weight class (rebuilds direct + common-opponent; optionally includes adjacent classes):
python -m wrestlerank.cli build-weight-class-relationships 132
python -m wrestlerank.cli build-weight-class-relationships W132 --include-adjacentNotes:
- Weight classes in DB are strings like `W106, W113, ..., W285`. If you pass `132`, the code will use it as-is; standardize to `W132` if needed for consistency in your data.

---

### Generate head-to-head matrix HTML
python -m wrestlerank.cli matrix W132 --use-rankings --output W132_matrix.html
# If you have no rankings yet, omit --use-rankings or it will fall back to win%
open W132_matrix.htmlThe matrix UI lets you reorder ranks visually. The “Save Rankings” button downloads a JSON (e.g., `W132_rankings.json`).

To persist those rankings to the DB:
python -m wrestlerank.cli save-rankings "$(cat W132_rankings.json)"---

### Import rankings from a CSV (optional)
If you have rankings from elsewhere:
- Filename format: `rankings-<weight>-<yyyymmdd>.csv` (or pass `--weight-class`)
- Required columns (flexible names): `wrestler_id`, `name`, `rank`

python -m wrestlerank.cli import-rankings /path/to/rankings-W132-20251110.csv
# or
python -m wrestlerank.cli import-rankings /path/to/your.csv --weight-class W132---

### Auto-generate “optimal” rankings (optional)
Uses PageRank + Greedy MFAS + Simulated Annealing + Local Search to minimize anomalies, then saves to `wrestler_rankings` with a date/algorithm tag:
python -m wrestlerank.cli optimize-ranking W132If you see dependency errors, ensure `numpy` is installed; optimization is CPU-intensive.

---

### Diagnostics and maintenance
Useful commands:
# Quick DB version check
python -m wrestlerank.cli version

# Inspect data
python -m wrestlerank.cli list-teams
python -m wrestlerank.cli list-wrestlers --weight-class W132 --active-only
python -m wrestlerank.cli list-matches --weight-class W132 --limit 50

# Schema updates (idempotent)
python -m wrestlerank.cli update-schema

# Match processing status
python -m wrestlerank.cli diagnose-matches
python -m wrestlerank.cli diagnose-matches "SELECT * FROM matches WHERE processed IS NULL LIMIT 20"

# Relationship tables overview
python -m wrestlerank.cli check-relationship-weight-classes
python -m wrestlerank.cli fix-relationship-weight-classes W132
python -m wrestlerank.cli fix-common-opponent-inconsistencies W132

# Reset only relationships (keep wrestlers/matches)
python -m wrestlerank.cli reset-relationships --force

# Ad-hoc SQL
python -m wrestlerank.cli run-sql "SELECT COUNT(*) AS c FROM matches"---

### When the source website changes
- If CSV header names/structures changed, update these functions:
  - `wrestlerank/migration/import_csv.py`:
    - `import_teams` (maps `name`, `team_id`, `abbr`, `state`)
    - `import_wrestlers` (maps `wrestlerID`, `name`, `weight`, `team`, etc.)
    - `import_matches` (maps `uid`, `winnerID`, `loserID`, `weight`, `result`, etc.)
- Alternatively, pre-clean CSVs to the expected column names before import.

---

### Optional: Minimal web endpoint to save rankings
`wrestlerank/web/server.py` contains a small Flask handler that proxies to the CLI. To use it, ensure you have a Flask app defined (if missing, add):
from flask import Flask, request, jsonify
import json, subprocess

app = Flask(__name__)

@app.route('/save-rankings', methods=['POST'])
def save_rankings():
    try:
        data_json = json.dumps(request.json)
        out = subprocess.check_output(['python', '-m', 'wrestlerank.cli', 'save-rankings', data_json])
        return out
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5001)Run it:
export FLASK_APP=wrestlerank/web/server.py
flask run -p 5001---

### Common pitfalls
- Mixed weight class formats (`132` vs `W132`): standardize your CSVs to `W###` and use that consistently.
- Rankings join uses `wrestlers.external_id = wrestler_rankings.wrestler_id`. Ensure your rankings csv/json uses external IDs.
- Duplicate matches: importer skips by `uid`. If your `uid` format changed, update the importer accordingly.
- `processed` match flag for global relationship build: added automatically if missing.

---

### Cheat sheet
# Fresh season
python -m wrestlerank.cli reset --force && python -m wrestlerank.cli init

# Import
python -m wrestlerank.cli import-teams /data/team-list.csv
python -m wrestlerank.cli import-wrestlers /data/wrestler-list.csv --team-csv /data/team-list.csv
python -m wrestlerank.cli import-matches /data/match-results.csv

# Relationships
python -m wrestlerank.cli build-relationships --all

# Matrix
python -m wrestlerank.cli matrix W132 --output W132_matrix.html && open W132_matrix.html

# Save rankings from UI JSON
python -m wrestlerank.cli save-rankings "$(cat W132_rankings.json)"

# Optimize rankings
python -m wrestlerank.cli optimize-ranking W132---

### Support
- Update mappings in `wrestlerank/migration/import_csv.py` if the website changes.
- For deeper issues, inspect `wrestlerank/matrix/relationship_manager.py` and `wrestlerank/matrix/matrix_generator.py`.