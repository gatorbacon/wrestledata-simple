#!/usr/bin/env python3
"""
Tiny Flask server that:
  1. Runs live_monitor's scrape loop in a background thread
  2. Serves live_data.json at GET /live_data.json with CORS headers
"""
import os
import sys
import threading
from pathlib import Path
from flask import Flask, send_file, jsonify
from flask_cors import CORS

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

app = Flask(__name__)
CORS(app)  # Allow matsavant.com to fetch from this domain

LIVE_DATA_PATH = PROJECT_ROOT / "live_data.json"


@app.route("/live_data.json")
def live_data():
    if not LIVE_DATA_PATH.exists():
        return jsonify({"error": "not ready"}), 503
    response = send_file(LIVE_DATA_PATH, mimetype="application/json")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@app.route("/health")
def health():
    return "ok"


def start_monitor():
    from scripts.ncaa.live_monitor import run_live
    year = int(os.environ.get("TOURNAMENT_YEAR", 2026))
    run_live(year=year, interval_seconds=120, once=False, skip_scrape=False, push=False)


if __name__ == "__main__":
    # Start monitor loop in background thread
    t = threading.Thread(target=start_monitor, daemon=True)
    t.start()

    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
