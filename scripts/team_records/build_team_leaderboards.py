#!/usr/bin/env python3
"""
Team record-book leaderboards, built from the team's season-stats Google Sheet.

Independent of KentuckyMat / MatSavant: nothing here touches the website data.

Reads every season tab ("2010-2011" ... "2025-2026") of the spreadsheet and writes ONE
self-contained HTML page with 12 leaderboards:

    {Boys, Girls} x {Pins, Wins, Takedowns} x {Career, Best Seasons}

Career rows expand (click) to show the season-by-season breakdown.

Usage (from the repo root):
    .venv/bin/python scripts/team_records/build_team_leaderboards.py
    .venv/bin/python scripts/team_records/build_team_leaderboards.py --file my_copy.xlsx
    .venv/bin/python scripts/team_records/build_team_leaderboards.py --top 15
    .venv/bin/python scripts/team_records/build_team_leaderboards.py --girls-include-boys-section

Standard library only (includes a small .xlsx reader), so no extra installs.
Full documentation: scripts/team_records/README.md
"""
import argparse
import difflib
import html
import itertools
import json
import re
import sys
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_SHEET_ID = "1DESABLd4B5x8zQ1jsGlwNLuJyiy8OyLd"
ALIAS_FILE = HERE / "name_aliases.json"
DEFAULT_OUT = HERE / "output" / "leaderboards.html"
SNAPSHOT = HERE / "output" / "last_download.xlsx"

SEASON_TAB = re.compile(r"^\s*(\d{4})\s*-\s*(\d{4})\s*$")
TAKEDOWN_HDR = re.compile(r"^t\d\s*\(f\)$", re.I)  # 'T2 (F)' most years, 'T3 (F)' in 2025-26

METRICS = [  # key, plural label, singular label
    ("pins", "Pins", "pin"),
    ("wins", "Wins", "win"),
    ("takedowns", "Takedowns", "takedown"),
]


# --------------------------------------------------------------------------- xlsx reader
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
       "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def _col_index(ref):
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_xlsx(path):
    """Return [(sheet_name, rows)] where rows is a list of lists (None for empty cells)."""
    z = zipfile.ZipFile(path)
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root.findall("m:si", _NS):
            shared.append("".join(t.text or "" for t in si.iter("{%s}t" % _NS["m"])))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = {r.get("Id"): r.get("Target")
            for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    sheets = []
    for s in wb.find("m:sheets", _NS):
        target = rels[s.get("{%s}id" % _NS["r"])].lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        root = ET.fromstring(z.read(target))
        rows = []
        for row in root.iter("{%s}row" % _NS["m"]):
            cells = {}
            for c in row.findall("m:c", _NS):
                t, v = c.get("t"), c.find("m:v", _NS)
                if t == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter("{%s}t" % _NS["m"]))
                elif v is None:
                    continue
                elif t == "s":
                    val = shared[int(v.text)]
                elif t in ("str", "e"):
                    val = v.text
                else:
                    try:
                        f = float(v.text)
                        val = int(f) if f == int(f) else f
                    except ValueError:
                        val = v.text
                cells[_col_index(c.get("r"))] = val
            rows.append([cells.get(i) for i in range(max(cells) + 1)] if cells else [])
        sheets.append((s.get("name"), rows))
    return sheets


def fetch_sheet(sheet_id):
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    print(f"Downloading spreadsheet {sheet_id} ...")
    with urllib.request.urlopen(url, timeout=60) as resp:
        data = resp.read()
    if not data.startswith(b"PK"):
        sys.exit("Download did not return an .xlsx file. The sheet must be shared as 'anyone with the "
                 "link can view' -- or download it yourself and pass it with --file.")
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_bytes(data)
    return SNAPSHOT


# --------------------------------------------------------------------------- names
def name_key(raw):
    """Normalized identity key: 'Thompson, Micah' / 'micah  thompson' -> 'micah thompson'."""
    n = re.sub(r"\s+", " ", str(raw)).strip()
    if "," in n:
        last, _, first = n.partition(",")
        n = f"{first.strip()} {last.strip()}"
    return re.sub(r"\s+", " ", n.replace(".", "")).strip().lower()


def display_name(raw):
    """'Thompson , Micah' -> 'Micah Thompson' (keeps the sheet's capitalization)."""
    n = re.sub(r"\s+", " ", str(raw)).strip()
    if "," in n:
        last, _, first = n.partition(",")
        n = f"{first.strip()} {last.strip()}"
    return re.sub(r"\s+", " ", n).strip()


def load_aliases():
    cfg = json.loads(ALIAS_FILE.read_text()) if ALIAS_FILE.exists() else {}
    aliases = {name_key(k): v.strip() for k, v in cfg.get("aliases", {}).items()}
    exclude = {name_key(n) for n in cfg.get("exclude", [])}
    not_same = {frozenset((name_key(a), name_key(b))) for a, b in cfg.get("not_same", [])}
    for variant, canon in aliases.items():
        if name_key(canon) in aliases and name_key(canon) != variant:
            sys.exit(f"Alias chain in {ALIAS_FILE.name}: '{variant}' -> '{canon}' is itself an alias. "
                     f"Point every variant straight at the final name.")
    return aliases, exclude, not_same


# --------------------------------------------------------------------------- parsing
def to_int(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    try:
        return int(float(str(v).strip()))
    except ValueError:
        return None


def parse_season_tabs(sheets, warnings):
    """Flatten every season tab into row dicts, tracking the Boys/Girls section markers."""
    rows_out, tabs_read = [], []
    for tab, rows in sheets:
        m = SEASON_TAB.match(tab)
        if not m or not rows:
            continue
        tabs_read.append(tab)
        tab_years = {int(m.group(1)), int(m.group(2))}
        cols, section = None, "boys"  # the boys block usually has no marker row

        def read_header(r):
            hdr = {}
            for i, h in enumerate(r):
                h = re.sub(r"\s+", " ", str(h or "")).strip().lower()
                if h == "name": hdr["name"] = i
                elif h == "year": hdr["year"] = i
                elif h == "fall (f)": hdr["pins"] = i
                elif h == "wins": hdr["wins"] = i
                elif h == "losses": hdr["losses"] = i
                elif TAKEDOWN_HDR.match(h) and "takedowns" not in hdr: hdr["takedowns"] = i
            return hdr

        for sheet_row, r in enumerate(rows, start=1):
            vals = [v for v in r if v is not None and str(v).strip() != ""]
            if not vals:
                continue
            first = str(r[0]).strip().lower() if r and r[0] is not None else ""
            if first == "name":  # header row (row 1, and repeated inside some Girls blocks)
                cols = read_header(r)
                missing = [k for k in ("name", "year", "pins", "wins", "losses", "takedowns") if k not in cols]
                if missing:
                    warnings.append(f"Tab '{tab}' row {sheet_row}: header is missing column(s) {missing}.")
                continue
            if len(vals) == 1 and isinstance(r[0], str):  # section marker, e.g. 'Girls Varsity'
                label = r[0].strip().lower()
                if "girl" in label: section = "girls"
                elif "boy" in label: section = "boys"
                else:
                    section = None
                    warnings.append(f"Tab '{tab}' row {sheet_row}: unknown section '{r[0].strip()}' -- "
                                    f"its rows are skipped until the next Boys/Girls marker.")
                continue
            if section is None or cols is None:
                continue
            cell = lambda k: r[cols[k]] if k in cols and cols[k] < len(r) else None
            year = to_int(cell("year"))
            if year is None:
                warnings.append(f"Tab '{tab}' row {sheet_row}: '{cell('name')}' has no numeric Year -- skipped.")
                continue
            if year not in tab_years:
                warnings.append(f"Tab '{tab}' row {sheet_row}: '{cell('name')}' has Year {year}, "
                                f"which doesn't match the tab name.")
            rec = {"raw": str(cell("name")).strip(), "season": year, "tab": tab, "row": sheet_row,
                   "section": section, "blank": []}
            for k in ("pins", "wins", "losses", "takedowns"):
                v = to_int(cell(k))
                if v is None:
                    rec["blank"].append(k)
                    v = 0
                rec[k] = v
            rows_out.append(rec)
    return rows_out, tabs_read


# --------------------------------------------------------------------------- build data
def season_label(end_year):
    return f"{end_year - 1}-{str(end_year)[-2:]}"


def resolve_names(rows, aliases, exclude, girls_include_boys, warnings):
    """Apply aliases/exclusions, assign gender, merge same-season duplicates."""
    variants_used = Counter()
    kept = []
    for r in rows:
        k = name_key(r["raw"])
        if k in exclude:
            variants_used[("exclude", r["raw"])] += 1
            continue
        if k in aliases:
            canon = aliases[k]
            variants_used[(r["raw"], canon)] += 1
        else:
            canon = display_name(r["raw"])
        r["canon"] = canon
        r["ckey"] = name_key(canon)
        kept.append(r)

    # Most common written form wins the display name for anyone without an explicit alias.
    forms = defaultdict(Counter)
    for r in kept:
        if name_key(r["raw"]) not in aliases:
            forms[r["ckey"]][display_name(r["raw"])] += 1
    alias_targets = {name_key(v) for v in aliases.values()}  # an explicit alias spelling always wins
    display = {k: c.most_common(1)[0][0] for k, c in forms.items() if k not in alias_targets}
    for r in kept:
        r["canon"] = display.get(r["ckey"], r["canon"])

    # A girl who also wrestled on the boys' side (2022-23) shows up in both sections.
    girls = {r["ckey"] for r in kept if r["section"] == "girls"}
    final, girl_rows_on_boys = [], 0
    for r in kept:
        if r["section"] == "boys" and r["ckey"] in girls:
            if girls_include_boys:
                r["gender"] = "girls"
            else:
                girl_rows_on_boys += 1
                continue
        else:
            r["gender"] = r["section"]
        final.append(r)
    if girl_rows_on_boys:
        warnings.append(f"{girl_rows_on_boys} boys-section row(s) belong to girls who also have girls-section rows "
                        f"(matches against boys, 2022-23). Left OUT of both boards; add "
                        f"--girls-include-boys-section to count them for the girls.")

    merged = {}
    for r in final:
        key = (r["gender"], r["ckey"], r["season"])
        if key in merged:
            m = merged[key]
            for k in ("pins", "wins", "losses", "takedowns"):
                m[k] += r[k]
            m["blank"] = [b for b in m["blank"] if b in r["blank"]]
            warnings.append(f"'{r['canon']}' has more than one {r['gender']} row for {season_label(r['season'])} "
                            f"(tab '{r['tab']}', rows {m['row']} & {r['row']}) -- numbers were added together.")
            m["row"] = f"{m['row']}&{r['row']}"
        else:
            merged[key] = dict(r)
    for m in merged.values():
        for k in m["blank"]:
            warnings.append(f"'{m['canon']}' {season_label(m['season'])}: blank {k} cell counted as 0 "
                            f"(tab '{m['tab']}', row {m['row']}).")
    return list(merged.values()), variants_used


def suggest_variants(rows, not_same):
    """Names that look like the same person but aren't merged (and never share a season)."""
    seasons = defaultdict(set)
    for r in rows:
        seasons[r["canon"]].add(r["season"])
    out = []
    for a, b in itertools.combinations(sorted(seasons), 2):
        if seasons[a] & seasons[b] or frozenset((name_key(a), name_key(b))) in not_same:
            continue
        ka, kb = name_key(a), name_key(b)
        fa, _, la = ka.partition(" ")
        fb, _, lb = kb.partition(" ")
        ratio = difflib.SequenceMatcher(None, ka, kb).ratio()
        first_sim = difflib.SequenceMatcher(None, fa, fb).ratio()
        last_sim = difflib.SequenceMatcher(None, la, lb).ratio()
        if (ratio >= 0.8 or (la == lb and first_sim >= 0.5) or (fa == fb and last_sim >= 0.6)
                or (first_sim >= 0.8 and last_sim >= 0.8)
                or (la == lb and (fa.startswith(fb) or fb.startswith(fa)))):
            out.append((a, sorted(seasons[a]), b, sorted(seasons[b])))
    return out


def rank_entries(entries, top):
    """Attach competition ranks (1,2,2,4) with tie flags; keep rank <= top (ties included)."""
    entries = [e for e in entries if e["value"] > 0]
    entries.sort(key=lambda e: (-e["value"], e["name"], e.get("season", 0)))
    counts = Counter(e["value"] for e in entries)
    for i, e in enumerate(entries):
        e["rank"] = 1 + sum(1 for x in entries if x["value"] > e["value"])
        e["tie"] = counts[e["value"]] > 1
    return [e for e in entries if e["rank"] <= top]


def build_boards(rows, top):
    boards = {}
    by_person = defaultdict(list)
    for r in rows:
        by_person[(r["gender"], r["ckey"])].append(r)
    for gender in ("boys", "girls"):
        for metric, _, _ in METRICS:
            career = []
            for (g, _k), seasons in by_person.items():
                if g != gender:
                    continue
                seasons = sorted(seasons, key=lambda s: s["season"])
                career.append({
                    "name": seasons[0]["canon"],
                    "value": sum(s[metric] for s in seasons),
                    "seasons": [{"season": s["season"], "value": s[metric], "wins": s["wins"],
                                 "losses": s["losses"], "blank": metric in s["blank"]} for s in seasons],
                })
            best = [{"name": r["canon"], "season": r["season"], "value": r[metric]}
                    for r in rows if r["gender"] == gender]
            boards[(gender, metric, "career")] = rank_entries(career, top)
            boards[(gender, metric, "season")] = rank_entries(best, top)
    return boards


# --------------------------------------------------------------------------- html
CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#16202c;--muted:#66727f;--line:#e3e7ec;--accent:#1f4e8c;--accent-ink:#fff;--row:#f0f4f9;--gold:#b7791f}
@media (prefers-color-scheme:dark){:root{--bg:#10151b;--card:#18202a;--ink:#e8edf2;--muted:#93a0ad;--line:#27313d;--accent:#5b9bf0;--accent-ink:#0b1117;--row:#1f2a36;--gold:#e0b04a}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:1.6rem;margin:0 0 4px}
.sub{color:var(--muted);margin:0 0 18px;font-size:.9rem}
.bar{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin-bottom:20px}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:var(--card)}
.seg button{border:0;background:none;color:var(--ink);padding:9px 22px;font:inherit;font-weight:600;cursor:pointer}
.seg button[aria-pressed=true]{background:var(--accent);color:var(--accent-ink)}
.ghost{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:10px;padding:9px 14px;font:inherit;cursor:pointer}
.panel[hidden]{display:none}
h2{font-size:1.15rem;margin:26px 0 10px;letter-spacing:.01em}
.pair{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:16px}
.board{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:6px 6px 8px}
.board h3{margin:8px 10px 6px;font-size:.78rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
.row,.entry>summary{display:grid;align-items:baseline;gap:8px;padding:8px 10px;border-radius:8px}
.career .entry>summary{grid-template-columns:3rem 1fr auto}
.season .row{grid-template-columns:3rem 1fr auto auto}
.row .rk,.entry>summary .rk{color:var(--muted);font-variant-numeric:tabular-nums}
.top .rk{color:var(--gold);font-weight:700}
.val{font-weight:700;font-variant-numeric:tabular-nums;text-align:right;min-width:2.5rem}
.yr{color:var(--muted);font-size:.85rem;white-space:nowrap;font-variant-numeric:tabular-nums}
small{color:var(--muted);font-size:.78rem;margin-left:6px}
.board>:nth-child(even of .row,.entry)>summary,.board>.row:nth-child(even of .row,.entry){background:var(--row)}
.entry>summary{cursor:pointer;list-style:none}
.entry>summary::-webkit-details-marker{display:none}
.chev{display:inline-block;width:.9em;color:var(--muted);transition:transform .12s}
.entry[open] .chev{transform:rotate(90deg)}
.brk{width:calc(100% - 20px);margin:2px 10px 10px 10px;border-collapse:collapse;font-size:.88rem;font-variant-numeric:tabular-nums}
.brk th{color:var(--muted);font-weight:600;text-align:right;padding:4px 8px;border-bottom:1px solid var(--line)}
.brk td{text-align:right;padding:4px 8px;border-bottom:1px solid var(--line)}
.brk th:first-child,.brk td:first-child{text-align:left}
.brk tr.total td{font-weight:700;border-bottom:0}
.brk .gap{color:var(--muted)}
.empty{color:var(--muted);padding:10px}
.notes{margin-top:34px;border:1px solid var(--line);border-radius:12px;background:var(--card);padding:4px 14px}
.notes summary{display:block;padding:10px 0;font-weight:600}
.notes ul{margin:4px 0 12px 18px;padding:0;color:var(--muted);font-size:.86rem}
.notes h4{margin:12px 0 4px;font-size:.85rem}
@media (max-width:520px){.career .entry>summary{grid-template-columns:2.4rem 1fr auto}.season .row{grid-template-columns:2.4rem 1fr auto auto}}
"""

JS = """
(function(){
  var panels=document.querySelectorAll('.panel'), btns=document.querySelectorAll('[data-g]');
  function show(g){
    if(!document.getElementById('panel-'+g)) g='boys';
    panels.forEach(function(p){p.hidden=(p.id!=='panel-'+g)});
    btns.forEach(function(b){b.setAttribute('aria-pressed',b.dataset.g===g)});
  }
  btns.forEach(function(b){b.addEventListener('click',function(){show(b.dataset.g)})});
  var open=false;
  document.getElementById('toggle-all').addEventListener('click',function(){
    open=!open;
    document.querySelectorAll('.panel:not([hidden]) details.entry').forEach(function(d){d.open=open});
    this.textContent=open?'Collapse all':'Expand all';
  });
  show((location.hash||'#boys').slice(1));
})();
"""


def _esc(s):
    return html.escape(str(s))


def render_board(entries, kind, metric_label, singular):
    if not entries:
        return '<div class="empty">No data yet.</div>'
    out = []
    for e in entries:
        rank = f"T-{e['rank']}" if e["tie"] else str(e["rank"])
        cls = " top" if e["rank"] <= 3 else ""
        if kind == "season":
            out.append(f'<div class="row{cls}"><span class="rk">{rank}</span><span>{_esc(e["name"])}</span>'
                       f'<span class="yr">{season_label(e["season"])}</span><span class="val">{e["value"]}</span></div>')
            continue
        first, last = e["seasons"][0]["season"], e["seasons"][-1]["season"]
        span = season_label(first) if first == last else f"{season_label(first)} – {season_label(last)[-2:]}"
        body = "".join(
            f'<tr><td>{season_label(s["season"])}</td>'
            f'<td>{"<span class=gap>–</span>" if s["blank"] else s["value"]}</td>'
            f'<td>{s["wins"]}–{s["losses"]}</td></tr>' for s in e["seasons"])
        out.append(
            f'<details class="entry{cls}"><summary><span class="rk">{rank}</span>'
            f'<span><span class="chev">▸</span> {_esc(e["name"])}<small>{span}</small></span>'
            f'<span class="val">{e["value"]}</span></summary>'
            f'<table class="brk"><thead><tr><th>Season</th><th>{metric_label}</th><th>Record</th></tr></thead>'
            f'<tbody>{body}<tr class="total"><td>Career</td><td>{e["value"]}</td><td></td></tr></tbody></table>'
            f'</details>')
    return "".join(out)


def render_html(boards, meta):
    panels = []
    for gender, glabel in (("boys", "Boys"), ("girls", "Girls")):
        secs = []
        for metric, label, singular in METRICS:
            career = render_board(boards[(gender, metric, "career")], "career", label, singular)
            season = render_board(boards[(gender, metric, "season")], "season", label, singular)
            secs.append(
                f'<h2>Most {label}</h2><div class="pair">'
                f'<article class="board career"><h3>Career</h3>{career}</article>'
                f'<article class="board season"><h3>Best Seasons</h3>{season}</article></div>')
        panels.append(f'<section class="panel" id="panel-{gender}">{"".join(secs)}</section>')

    def ul(items):
        return "<ul>" + "".join(f"<li>{_esc(i)}</li>" for i in items) + "</ul>" if items else "<ul><li>None</li></ul>"

    notes = (
        '<details class="notes"><summary>Data notes</summary>'
        f'<h4>Source</h4>{ul(meta["source"])}'
        f'<h4>Name aliases applied</h4>{ul(meta["aliases"])}'
        f'<h4>Rows excluded</h4>{ul(meta["excluded"])}'
        f'<h4>Warnings</h4>{ul(meta["warnings"])}</details>')
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Team Record Book Leaderboards</title>'
        f'<style>{CSS}</style></head><body><div class="wrap">'
        '<h1>Team Record Book — Leaderboards</h1>'
        f'<p class="sub">Varsity seasons {season_label(meta["first"])} through {season_label(meta["last"])} '
        f'· top {meta["top"]} per board · generated {meta["generated"]}. '
        'Click a career row to see season by season.</p>'
        '<div class="bar"><div class="seg">'
        '<button data-g="boys" aria-pressed="true">Boys</button>'
        '<button data-g="girls" aria-pressed="false">Girls</button></div>'
        '<button class="ghost" id="toggle-all" type="button">Expand all</button></div>'
        f'{"".join(panels)}{notes}</div><script>{JS}</script></body></html>')


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sheet-id", default=DEFAULT_SHEET_ID, help="Google Sheet ID to download")
    ap.add_argument("--file", help="use a local .xlsx instead of downloading")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output HTML path")
    ap.add_argument("--top", type=int, default=25, help="rows per board; ties at the cutoff are kept (default 25)")
    ap.add_argument("--girls-include-boys-section", action="store_true",
                    help="count girls' boys-section rows (2022-23 matches vs boys) toward the girls boards")
    args = ap.parse_args()

    path = Path(args.file) if args.file else fetch_sheet(args.sheet_id)
    warnings = []
    rows, tabs = parse_season_tabs(read_xlsx(path), warnings)
    if not rows:
        sys.exit("No season rows found -- expected tabs named like '2024-2025'.")
    aliases, exclude, not_same = load_aliases()
    rows, used = resolve_names(rows, aliases, exclude, args.girls_include_boys_section, warnings)
    boards = build_boards(rows, args.top)

    meta = {
        "top": args.top,
        "first": min(r["season"] for r in rows), "last": max(r["season"] for r in rows),
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": [f"{'Local file ' + str(path) if args.file else 'Google Sheet ' + args.sheet_id}",
                   f"{len(tabs)} season tabs read: {', '.join(tabs)}",
                   "Pins = 'Fall (F)'; Takedowns = 'T2 (F)' (called 'T3 (F)' in the 2025-26 tab); Wins = 'Wins'.",
                   "Season is the tab's 'Year' column (graduation-year style, 2025 = the 2024-25 season)."],
        "aliases": [f"{a} → {b} ({n} row{'s' if n != 1 else ''})"
                    for (a, b), n in sorted(used.items()) if a != "exclude"],
        "excluded": [f"{b} ({n} row{'s' if n != 1 else ''})" for (a, b), n in sorted(used.items()) if a == "exclude"],
        "warnings": warnings,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(boards, meta), encoding="utf-8")

    counts = Counter(r["gender"] for r in rows)
    print(f"Read {len(tabs)} season tabs -> {counts['boys']} boys and {counts['girls']} girls wrestler-seasons.")
    for w in warnings:
        print(f"  warning: {w}")
    sugg = suggest_variants(rows, not_same)
    if sugg:
        print("\nPossible name variants NOT yet in name_aliases.json (never share a season, so could be one person):")
        for a, ya, b, yb in sugg:
            print(f"  '{a}' {ya}   vs   '{b}' {yb}")
        print("  -> add to 'aliases' if same person, or to 'not_same' if different.")
    else:
        print("No unresolved name variants.")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
