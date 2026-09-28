#!/usr/bin/env python3
"""Build data/analysis/td_custom_report.html: runs build_data.py (bout-level computation), embeds data.json in template.html."""
import json, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
subprocess.run([sys.executable, str(HERE / "build_data.py")], check=True, stdout=subprocess.DEVNULL)
data = json.load(open(HERE / "data.json"))
html = (HERE / "template.html").read_text().replace("/*DATA*/", json.dumps(data, separators=(",", ":")))
out = ROOT / "data/analysis/td_custom_report.html"
out.write_text(html)
print("wrote", out, f"{len(html):,} bytes")
