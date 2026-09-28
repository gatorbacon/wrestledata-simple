#!/usr/bin/env python3
"""Build data/analysis/td_report_comparison.html from the 8 text reports (4 windows x NCAA/conference).

Run the 8 reports first (scripts/analysis/td_differential_report.py, --tourney ncaa|conf), then:
    .venv/bin/python scripts/analysis/td_comparison_viz/build_comparison.py
Steps: parse_reports.py parses the text reports -> reports.json (git-ignored intermediate);
this script adds the section-4 ladder counts and embeds the JSON into template.html.
The page is self-contained (inline SVG/JS, no libraries); open it in a browser.
"""
import json, re, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
subprocess.run([sys.executable, str(HERE / "parse_reports.py")], check=True)
R = json.load(open(HERE / "reports.json"))
for k, d in R.items():
    top = d["nd_top"]
    lad = {str(top): len(d["nd_rows"]) + d["nd_more"]}
    for n, lv in re.findall(r"(\d+) [A-Za-z\-]+ had (\d) such wins?", d["nd_compare"] or ""):
        lad[lv] = int(n)
    for lv in "1234":
        lad.setdefault(lv, 0)
    d["ladder"] = lad
html = (HERE / "template.html").read_text().replace("/*DATA*/", json.dumps(R, separators=(",", ":")))
out = ROOT / "data/analysis/td_report_comparison.html"
out.write_text(html)
print("wrote", out, f"{len(html):,} bytes")
