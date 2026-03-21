#!/usr/bin/env python3
"""
Tiny Flask server that:
  1. Runs live_monitor's scrape loop in a background thread
  2. Serves live_data.json at GET /live_data.json with CORS headers
"""
import gzip
import io
import json
import os
import sys
import threading
from pathlib import Path
from flask import Flask, make_response, jsonify
from flask_cors import CORS

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

app = Flask(__name__)
CORS(app)  # Allow matsavant.com to fetch from this domain

LIVE_DATA_PATH = PROJECT_ROOT / "live_data.json"

# Cache the gzipped payload so repeated requests don't re-compress each time
_cache = {"etag": None, "body": None}


@app.route("/live_data.json")
def live_data():
    if not LIVE_DATA_PATH.exists():
        return jsonify({"error": "not ready"}), 503

    stat = LIVE_DATA_PATH.stat()
    etag = f"{stat.st_mtime:.3f}-{stat.st_size}"

    if _cache["etag"] != etag:
        data = json.loads(LIVE_DATA_PATH.read_text())
        # Drop sorted_matches — redundant since h.match is embedded in history
        data.pop("sorted_matches", None)
        compact = json.dumps(data, separators=(",", ":")).encode()
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=6) as f:
            f.write(compact)
        _cache["etag"] = etag
        _cache["body"] = buf.getvalue()

    response = make_response(_cache["body"])
    response.headers["Content-Type"] = "application/json"
    response.headers["Content-Encoding"] = "gzip"
    response.headers["Cache-Control"] = "public, max-age=60"
    response.headers["ETag"] = _cache["etag"]
    return response


@app.route("/health")
def health():
    return "ok"


def start_monitor():
    import importlib.util
    monitor_path = PROJECT_ROOT / "scripts" / "ncaa" / "live_monitor.py"
    spec = importlib.util.spec_from_file_location("live_monitor", monitor_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    year = int(os.environ.get("TOURNAMENT_YEAR", 2026))
    module.run_live(year=year, interval_seconds=120, once=False, skip_scrape=False)


if __name__ == "__main__":
    # Start monitor loop in background thread
    t = threading.Thread(target=start_monitor, daemon=True)
    t.start()

    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
