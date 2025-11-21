from flask import Flask, request, jsonify, render_template_string, redirect, url_for
import os, json, tempfile

from wrestlerank.migration import import_csv
from wrestlerank.matrix import matrix_generator, relationship_manager
from wrestlerank.db import sqlite_db
from wrestlerank.ranking.optimal_ranker import OptimalRanker

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 256 * 1024 * 1024  # 256MB uploads

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>WrestleRank Admin</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 20px; }
    h2 { margin-top: 28px; }
    form { margin: 12px 0; padding: 12px; border: 1px solid #ddd; }
    button { padding: 6px 12px; }
    input[type=file] { margin: 6px 0; }
    .row { display: flex; gap: 24px; flex-wrap: wrap; }
    .card { flex: 1 1 420px; border: 1px solid #eee; padding: 16px; border-radius: 6px; }
    label { display: inline-block; min-width: 140px; }
  </style>
</head>
<body>
  <h1>WrestleRank Admin</h1>

  <div class="row">
    <div class="card">
      <h2>Database</h2>
      <form method="post" action="/db/reset">
        <label>DB Path (optional):</label>
        <input name="db_path" placeholder="wrestlerank.db" />
        <button type="submit">Reset & Init</button>
      </form>
      <form method="post" action="/db/update-schema">
        <button type="submit">Update Schema</button>
      </form>
    </div>

    <div class="card">
      <h2>Import: Teams</h2>
      <form method="post" action="/import/teams" enctype="multipart/form-data">
        <input type="file" name="file" accept=".csv" required />
        <button type="submit">Import Teams CSV</button>
      </form>

      <h2>Import: Wrestlers</h2>
      <form method="post" action="/import/wrestlers" enctype="multipart/form-data">
        <input type="file" name="file" accept=".csv" required />
        <label>Team CSV (optional):</label>
        <input type="file" name="team_csv" accept=".csv" />
        <button type="submit">Import Wrestlers CSV</button>
      </form>

      <h2>Import: Matches</h2>
      <form method="post" action="/import/matches" enctype="multipart/form-data">
        <input type="file" name="file" accept=".csv" required />
        <label>Limit:</label>
        <input type="number" name="limit" min="0" value="0" />
        <label>Update stats:</label>
        <input type="checkbox" name="update_stats" checked />
        <button type="submit">Import Matches CSV</button>
      </form>
    </div>

    <div class="card">
      <h2>Relationships</h2>
      <form method="post" action="/relationships/build">
        <label>Weight Class (e.g. W132):</label>
        <input name="weight_class" required />
        <label>Include adjacent:</label>
        <input type="checkbox" name="include_adjacent" checked />
        <label>Limit (0=all):</label>
        <input type="number" name="limit" min="0" value="0" />
        <button type="submit">Build For Weight Class</button>
      </form>
      <form method="post" action="/relationships/reset">
        <button type="submit">Reset ALL Relationships</button>
      </form>
    </div>

    <div class="card">
      <h2>Matrix</h2>
      <form method="get" action="/matrix/view">
        <label>Weight Class:</label>
        <input name="weight_class" required />
        <label>Use Rankings:</label>
        <input type="checkbox" name="use_rankings" checked />
        <label>Limit (0=all):</label>
        <input type="number" name="limit" min="0" value="0" />
        <button type="submit">Open Matrix</button>
      </form>

      <h2>Rankings</h2>
      <form method="post" action="/rankings/optimize">
        <label>Weight Class:</label>
        <input name="weight_class" required />
        <button type="submit">Run Optimizer</button>
      </form>
    </div>
  </div>
</body>
</html>
"""

def _save_upload_to_tmp(file_storage):
    fd, tmp_path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    file_storage.save(tmp_path)
    return tmp_path

@app.route("/", methods=["GET"])
def home():
    return render_template_string(DASHBOARD_HTML)

# DB operations
@app.route("/db/reset", methods=["POST"])
def db_reset():
    db_path = request.form.get("db_path") or "wrestlerank.db"
    try:
        sqlite_db.close_db()
        if os.path.exists(db_path):
            os.remove(db_path)
        sqlite_db.init_db(db_path)
        sqlite_db.create_tables()
        sqlite_db.close_db()
        return redirect(url_for("home"))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/db/update-schema", methods=["POST"])
def db_update_schema():
    try:
        sqlite_db.init_db()
        sqlite_db.create_tables()
        return redirect(url_for("home"))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        sqlite_db.close_db()

# Imports
@app.route("/import/teams", methods=["POST"])
def import_teams():
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "Missing file"}), 400
    tmp_path = _save_upload_to_tmp(request.files["file"])
    try:
        team_map = import_csv.import_teams(tmp_path)
        return jsonify({"ok": True, "teams": len(team_map)})
    finally:
        os.remove(tmp_path)

@app.route("/import/wrestlers", methods=["POST"])
def import_wrestlers():
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "Missing file"}), 400
    tmp_path = _save_upload_to_tmp(request.files["file"])
    team_csv = request.files.get("team_csv")
    team_map = {}
    team_tmp = None
    try:
        if team_csv and team_csv.filename:
            team_tmp = _save_upload_to_tmp(team_csv)
            team_map = import_csv.import_teams(team_tmp)
        wrestler_map = import_csv.import_wrestlers(tmp_path, team_map)
        return jsonify({"ok": True, "wrestlers": len(wrestler_map)})
    finally:
        os.remove(tmp_path)
        if team_tmp and os.path.exists(team_tmp):
            os.remove(team_tmp)

@app.route("/import/matches", methods=["POST"])
def import_matches():
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "Missing file"}), 400
    tmp_path = _save_upload_to_tmp(request.files["file"])
    limit = int(request.form.get("limit", "0") or "0")
    update_stats = "update_stats" in request.form
    try:
        count = import_csv.import_matches(tmp_path, update_stats=update_stats, limit=limit)
        return jsonify({"ok": True, "matches": count})
    finally:
        os.remove(tmp_path)

# Relationships
@app.route("/relationships/build", methods=["POST"])
def relationships_build():
    wc = request.form.get("weight_class")
    if not wc:
        return jsonify({"ok": False, "error": "Missing weight_class"}), 400
    include_adjacent = "include_adjacent" in request.form
    limit = int(request.form.get("limit", "0") or "0")
    adjacent = []
    if include_adjacent:
        mens = ['106','113','120','126','132','138','144','150','157','165','175','190','215','285']
        womens = ['W100','W107','W114','W120','W126','W132','W138','W145','W152','W165','W185','W235']
        if wc.startswith('W') and wc in womens:
            i = womens.index(wc)
            if i>0: adjacent.append(womens[i-1])
            if i<len(womens)-1: adjacent.append(womens[i+1])
        else:
            # normalize if bare number
            base = wc[1:] if wc.startswith('W') else wc
            if base in mens:
                i = mens.index(base)
                if i>0: adjacent.append('W'+mens[i-1])
                if i<len(mens)-1: adjacent.append('W'+mens[i+1])
    try:
        relationship_manager.build_weight_class_relationships(wc, adjacent_classes=adjacent, limit=limit)
        return jsonify({"ok": True, "weight_class": wc, "adjacent": adjacent})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/relationships/reset", methods=["POST"])
def relationships_reset():
    try:
        sqlite_db.init_db()
        cur = sqlite_db.conn.cursor()
        cur.execute("DELETE FROM wrestler_relationships")
        cur.execute("DELETE FROM common_opponent_paths")
        sqlite_db.conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        sqlite_db.close_db()

# Matrix
@app.route("/matrix/view", methods=["GET"])
def matrix_view():
    wc = request.args.get("weight_class")
    if not wc:
        return jsonify({"ok": False, "error": "Missing weight_class"}), 400
    use_rankings = request.args.get("use_rankings", "on").lower() not in ("0","false","off")
    limit = int(request.args.get("limit", "0") or "0")
    try:
        data = matrix_generator.build_matrix(wc, include_adjacent=True, limit=limit, use_rankings=use_rankings)
        html = matrix_generator.generate_html(data, wc)
        return html
    except Exception as e:
        return f"<pre>Error generating matrix: {e}</pre>", 500

# Rankings (save from matrix UI)
@app.route("/save-rankings", methods=["POST"])
def save_rankings():
    try:
        data_json = json.dumps(request.json)
        # Reuse CLI handler logic directly here:
        payload = json.loads(data_json)
        weight_class = payload.get('weight_class')
        rankings = payload.get('rankings', [])
        if not weight_class or not rankings:
            return jsonify({'success': False, 'error': 'Missing weight class or rankings'}), 400

        sqlite_db.init_db()
        cur = sqlite_db.conn.cursor()
        now = __import__("datetime").datetime.now().isoformat()
        today = now.split('T')[0]
        cur.execute("DELETE FROM wrestler_rankings WHERE weight_class = ? AND date = ?", (weight_class, today))
        for r in rankings:
            cur.execute(
                "INSERT INTO wrestler_rankings (wrestler_id, weight_class, rank, date, last_updated) VALUES (?, ?, ?, ?, ?)",
                (r.get('wrestler_id'), weight_class, r.get('rank'), today, now)
            )
        sqlite_db.conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        sqlite_db.close_db()

# Optimizer (synchronous MVP)
@app.route("/rankings/optimize", methods=["POST"])
def rankings_optimize():
    wc = request.form.get("weight_class")
    if not wc:
        return jsonify({"ok": False, "error": "Missing weight_class"}), 400
    try:
        ranker = OptimalRanker(wc)
        if not ranker.load_data_from_db():
            return jsonify({"ok": False, "error": "No data loaded"}), 400
        ranker.run_optimization()
        saved = ranker.save_rankings_to_db("optimal")
        return jsonify({"ok": True, "saved": bool(saved), "best_score": ranker.best_score})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5001)