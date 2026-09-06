#!/usr/bin/env python3
"""
Parse a manually-captured roster PDF (from the user's bulk URL->PDF tool, for
schools scrape_official_roster.py can't reach -- JS-rendered sites like
gowyo.com, or robots.txt-blocked sites like lrtrojans.com) into the same
{"season", "team_roster_url", "players": [...]} schema scrape_official_roster.py
produces, so it drops into the existing pipeline (match_official_rosters_to_trackwrestling.py,
enrich_ncaa_rosters.py) unchanged.

Sidearm Sports (the site template both Wyoming and Little Rock use) offers
three different "Roster View" layouts, and which one gets captured varies not
just school-to-school but season-to-season on the SAME school's site:

  - "Cards": a 3-column grid of player cards (name / weight / class-hometown-hs).
    Requires word-level bbox parsing -- the name row can be vertically offset
    from its weight/detail rows in ways plain -layout text can't disambiguate.
  - "Grid": an HTML table (Image/Full Name/Hometown/High School/Previous
    School/Pos./Academic Year/Major columns). The tricky part: a single-line
    "Full Name" cell renders vertically CENTERED against its taller, wrapped
    neighboring cells, so a name row's y-position can sit strictly BETWEEN a
    hometown cell's two wrapped lines -- assign every row to whichever name
    anchor is physically nearest in Y, not "everything after this name until
    the next one".
  - "List": one card per row, Name+Weight/Class on the left, Hometown+HighSchool
    on the right (Wyoming's version -- single column). Little Rock's own
    "List" view is laid out differently: 2 columns of cards, each a clean
    3-line block (name / class-height-weight / hometown-hs[-previous_school]),
    parseable directly from `pdftotext -layout` text via wide-whitespace column
    splitting, no bbox needed.

Usage as a library:
    from parse_manual_roster_pdf import parse_and_normalize
    players = parse_and_normalize(pdf_path, team_slug="wyoming")
    # -> list of dicts matching scrape_official_roster.py's player schema

Run directly to preview one PDF without writing anything:
    .venv/bin/python scripts/scraping/parse_manual_roster_pdf.py <pdf_path>
"""
import hashlib
import re
import subprocess
import sys
import xml.etree.ElementTree as ET


# ── Shared bbox helpers ───────────────────────────────────────────────────────

def get_words(pdf_path):
    out = subprocess.run(["pdftotext", "-bbox", pdf_path, "-"], capture_output=True, text=True)
    html = out.stdout
    start = html.index("<doc>")
    end = html.index("</doc>") + len("</doc>")
    root = ET.fromstring(html[start:end])
    words = []
    for page in root.findall("page"):
        for w in page.findall("word"):
            text = (w.text or "").strip()
            if not text:
                continue
            words.append({
                "x0": float(w.get("xMin")), "x1": float(w.get("xMax")),
                "y0": float(w.get("yMin")), "y1": float(w.get("yMax")),
                "text": text,
            })
    return words


def cluster_rows(words, y_tol=6):
    """Group words into physical text rows by Y-overlap."""
    words = sorted(words, key=lambda w: (w["y0"], w["x0"]))
    rows = []
    for w in words:
        placed = False
        for row in rows:
            if abs(row["y0"] - w["y0"]) <= y_tol:
                row["words"].append(w)
                row["y0"] = min(row["y0"], w["y0"])
                placed = True
                break
        if not placed:
            rows.append({"y0": w["y0"], "words": [w]})
    rows.sort(key=lambda r: r["y0"])
    for row in rows:
        row["words"].sort(key=lambda w: w["x0"])
    return rows


NAME_RE = re.compile(r"^[A-Z][a-zA-Z'.\-]*(\s[A-Z][a-zA-Z'.\-]*){1,3}$")


def looks_like_a_name(name):
    """Filters out sidebar/news-section text that sometimes leaks into the
    roster area on a page capture (e.g. 'Austin Collins Earns Two All-',
    '2 months ago') -- real names are 2-4 capitalized tokens, never sentence
    fragments."""
    return bool(NAME_RE.match(name))


def detect_roster_view(pdf_path):
    out = subprocess.run(["pdftotext", "-layout", pdf_path, "-"], capture_output=True, text=True)
    m = re.search(r"Roster View - (\w+)", out.stdout)
    return m.group(1) if m else None


# ── "Cards" grid parser (3-column card grid) ─────────────────────────────────

WEIGHT_RE = re.compile(r"^(HWT|\d{2,3}(/\d{2,3})?)$")


def _split_columns(row_words, gap=60):
    cols = []
    cur = [row_words[0]]
    for w in row_words[1:]:
        if w["x0"] - cur[-1]["x1"] > gap:
            cols.append(cur)
            cur = [w]
        else:
            cur.append(w)
    cols.append(cur)
    return [{"x0": c[0]["x0"], "text": " ".join(x["text"] for x in c)} for c in cols]


def _assign_to_bands(cols, bands, tol=250):
    out = {}
    for c in cols:
        best = min(range(len(bands)), key=lambda i: abs(bands[i] - c["x0"]))
        if abs(bands[best] - c["x0"]) <= tol:
            out[best] = c["text"]
    return out


def parse_cards(pdf_path, min_y=650, max_x=1230):
    """Wyoming-style 3-column card grid ('Roster View - Cards')."""
    all_words = get_words(pdf_path)
    coach_ys = [w["y0"] for w in all_words if w["text"] == "Coaches" and w["x0"] < 300]
    max_y = min(coach_ys) if coach_ys else float("inf")
    words = [w for w in all_words if min_y <= w["y0"] < max_y and w["x0"] <= max_x]
    rows = cluster_rows(words)
    row_cols = [_split_columns(row["words"]) for row in rows]

    weight_row_idxs = [i for i, cols in enumerate(row_cols)
                        if cols and all(WEIGHT_RE.match(c["text"]) for c in cols)]
    if not weight_row_idxs:
        return []

    anchor = max(weight_row_idxs, key=lambda i: len(row_cols[i]))
    bands = [c["x0"] for c in row_cols[anchor]]

    players = []
    i, n = 0, len(row_cols)
    while i < n:
        if i in weight_row_idxs:
            weight_map = _assign_to_bands(row_cols[i], bands)
            name_map = _assign_to_bands(row_cols[i - 1], bands) if i - 1 >= 0 else {}
            details_maps = []
            j = i + 1
            while j < n and j not in weight_row_idxs:
                if j + 1 < n and (j + 1) in weight_row_idxs:
                    break
                details_maps.append(_assign_to_bands(row_cols[j], bands))
                j += 1
            for slot, wt in weight_map.items():
                name = name_map.get(slot, "").strip()
                if not name:
                    continue
                detail_parts = [dm.get(slot, "") for dm in details_maps if dm.get(slot)]
                detail = re.sub(r"\s*\$\s*", " ", " ".join(detail_parts)).strip()
                players.append({"name": name, "weight": wt, "detail": detail})
            i = j
        else:
            i += 1
    return players


def _split_cards_detail(detail):
    """'Jr. / Beaver, Utah / Western Wyoming College' -> (grade, hometown, high_school)"""
    parts = [p.strip() for p in detail.split("/")]
    grade = parts[0] if len(parts) > 0 else ""
    hometown = parts[1] if len(parts) > 1 else ""
    high_school = parts[2] if len(parts) > 2 else ""
    return grade, hometown, high_school


# ── "Grid" table parser (Image/Full Name/Hometown/High School/... columns) ──

GRID_COLUMNS = ["name", "hometown", "high_school", "previous_school", "weight", "class_level", "major"]
GRID_HEADER_LABELS = {
    "Full": "name", "Hometown": "hometown", "High": "high_school",
    "Previous": "previous_school", "Pos.": "weight", "Weight": "weight",
    "Academic": "class_level", "Year": "class_level", "Major": "major",
}


def _find_grid_header_bands(rows):
    for row in rows:
        texts = [w["text"] for w in row["words"]]
        if "Full" in texts and "Hometown" in texts:
            bands = {}
            for w in row["words"]:
                if w["text"] in GRID_HEADER_LABELS:
                    bands.setdefault(GRID_HEADER_LABELS[w["text"]], w["x0"])  # first word wins
            return bands, row["y0"]
    return None, None


def _assign_grid_band(x0, bands, tol=90):
    best = min(bands.items(), key=lambda kv: abs(kv[1] - x0))
    if abs(best[1] - x0) <= tol:
        return best[0]
    return None


def parse_grid(pdf_path, max_x=1010):
    """Wyoming-style table view ('Roster View - Grid')."""
    all_words = get_words(pdf_path)
    rows = cluster_rows(all_words)
    bands, header_y = _find_grid_header_bands(rows)
    if not bands:
        return []

    footer_ys = [w["y0"] for w in all_words if w["text"] == "Coaches" and w["x0"] < 100 and w["y0"] > header_y]
    max_y = min(footer_ys) if footer_ys else float("inf")

    body_rows = [r for r in rows if header_y < r["y0"] < max_y]
    for r in body_rows:
        r["words"] = [w for w in r["words"] if w["x0"] <= max_x]

    row_col_texts = []
    for r in body_rows:
        col_words = {}
        for w in r["words"]:
            col = _assign_grid_band(w["x0"], bands)
            if col:
                col_words.setdefault(col, []).append(w["text"])
        row_col_texts.append({"y0": r["y0"], "cols": {c: " ".join(t) for c, t in col_words.items()}})

    # A "Full Name" cell renders vertically CENTERED against its taller,
    # wrapped neighbors -- assign every row to whichever name-anchor Y is
    # physically closest, not "everything after this name until the next".
    anchors = [rc["y0"] for rc in row_col_texts if rc["cols"].get("name")]
    if not anchors:
        return []

    def nearest_anchor(y):
        return min(anchors, key=lambda a: abs(a - y))

    blocks = {a: {c: [] for c in GRID_COLUMNS} for a in anchors}
    for rc in row_col_texts:
        a = nearest_anchor(rc["y0"])
        for c in GRID_COLUMNS:
            if rc["cols"].get(c):
                blocks[a][c].append(rc["cols"][c])

    out = []
    for a in anchors:
        p = blocks[a]
        out.append({c: " ".join(p[c]).strip() for c in GRID_COLUMNS})
    return [p for p in out if looks_like_a_name(p["name"])]


# ── Wyoming-style "List" parser (1 card per row, 2 side-by-side fields) ─────

def parse_wystyle_list(pdf_path, left_max=550, right_min=550, right_max=1000):
    """Wyoming-style single-column list ('Roster View - List'): Name+Weight/Class
    on the left, Hometown+HighSchool on the right, spread across 2-3 physical
    lines with vertical-centering offsets."""
    all_words = get_words(pdf_path)
    rows = cluster_rows(all_words)

    footer_ys = [w["y0"] for w in all_words if w["text"] == "Coaches" and w["x0"] < 300]
    min_y = 650  # below the nav/header/hero area on every capture seen so far
    max_y = min([y for y in footer_ys if y > min_y], default=float("inf"))

    left_rows, right_rows = [], []
    for r in rows:
        if not (min_y < r["y0"] < max_y):
            continue
        left_text = " ".join(w["text"] for w in r["words"] if w["x0"] < left_max)
        right_text = " ".join(w["text"] for w in r["words"] if right_min <= w["x0"] < right_max)
        if left_text.strip():
            left_rows.append({"y0": r["y0"], "text": left_text.strip()})
        if right_text.strip():
            right_rows.append({"y0": r["y0"], "text": right_text.strip()})

    anchors = [r["y0"] for r in left_rows if NAME_RE.match(r["text"])]
    if not anchors:
        return []

    def nearest(y):
        return min(anchors, key=lambda a: abs(a - y))

    left_by_anchor = {a: [] for a in anchors}
    right_by_anchor = {a: [] for a in anchors}
    for r in left_rows:
        left_by_anchor[nearest(r["y0"])].append(r["text"])
    for r in right_rows:
        right_by_anchor[nearest(r["y0"])].append(r["text"])

    players = []
    for a in anchors:
        left_parts = left_by_anchor[a]
        name = next((t for t in left_parts if NAME_RE.match(t)), "")
        weight_class = " ".join(t for t in left_parts if t != name)
        right_parts = right_by_anchor[a]
        players.append({"name": name, "weight_class_raw": weight_class, "home_raw": " | ".join(right_parts)})
    return players


CLASS_RE = re.compile(r"^(R-)?(Fr|So|Jr|Sr)\.?$", re.IGNORECASE)


def _split_wystyle_weight_class(raw):
    """'165 / R-Jr.' -> ('165', 'R-Jr.'); '125 133' (slash dropped by a line
    break) -> ('125/133', ''); a stray '$' NIL-icon marker is discarded."""
    tokens = [t.strip() for t in re.split(r"[/\s]+", raw) if t.strip() and t.strip() != "$"]
    weights = [t for t in tokens if t == "HWT" or t.isdigit()]
    classes = [t for t in tokens if CLASS_RE.match(t)]
    return "/".join(weights), " ".join(classes)


def _split_wystyle_home(raw):
    """'Casper, Wyo. | Kelly Walsh' -> (hometown, high_school)"""
    parts = [p.strip() for p in raw.split("|") if p.strip()]
    hometown = parts[0] if len(parts) > 0 else ""
    high_school = parts[1] if len(parts) > 1 else ""
    return hometown, high_school


# ── Little Rock-style "List" parser (2-column cards, 3 clean lines each) ────

COL_SPLIT = re.compile(r"\s{8,}")


def parse_two_col_list(pdf_path, start_marker="Wrestling Roster", end_marker="Coaching Staff"):
    """Little Rock-style 2-column list: each card is exactly 3 lines
    (name / class-height-weight / hometown-hs[-previous_school]), reliably
    split from plain `pdftotext -layout` text via wide-whitespace column gaps."""
    out = subprocess.run(["pdftotext", "-layout", pdf_path, "-"], capture_output=True, text=True)
    lines = out.stdout.split("\n")
    start = next((i for i, l in enumerate(lines) if l.strip() == start_marker), 0) + 1
    end = next((i for i in range(start, len(lines)) if end_marker in lines[i]), len(lines))
    body = lines[start:end]

    rows = []
    for line in body:
        if not line.strip():
            continue
        rows.append(COL_SPLIT.split(line.strip()))

    players = []
    for i in range(0, len(rows) - len(rows) % 3, 3):
        name_row, stat_row, home_row = rows[i], rows[i + 1], rows[i + 2]
        for col in range(2):
            if col >= len(name_row):
                continue
            name = name_row[col].strip()
            if not name:
                continue
            stat = stat_row[col].strip() if col < len(stat_row) else ""
            home = home_row[col].strip() if col < len(home_row) else ""
            players.append({"name": name, "stat": stat, "home": home})
    return players


def _split_two_col_stat(stat):
    """'REDSHIRT FRESHMAN - 5'10" - 133 lbs' -> (class_level, weight)"""
    parts = [p.strip() for p in stat.split(" - ")]
    class_level = parts[0] if len(parts) > 0 else ""
    weight = parts[-1] if len(parts) > 0 else ""
    return class_level, weight


def _split_two_col_home(home):
    """'Bentonville, Ark. - Bentonville H.S.' -> (hometown, high_school, previous_school)
    A third segment (e.g. 'Derby, Kan. - Derby H.S. - Oklahoma State') is a transfer note."""
    parts = [p.strip() for p in home.split(" - ")]
    hometown = parts[0] if len(parts) > 0 else ""
    high_school = parts[1] if len(parts) > 1 else ""
    previous_school = parts[2] if len(parts) > 2 else None
    return hometown, high_school, previous_school


# ── Normalization to scrape_official_roster.py's schema ─────────────────────

def player_id_for(team_slug, name):
    """Deterministic hash of (team, normalized name) -- NOT the real site's
    player_id (we have no way to know that from a PDF), but stable across
    every season parsed with this same function, which is what actually
    matters: link_ncaa_season.py's tier-1 auto-link relies on (team,
    player_id) continuity across seasons at the same school."""
    norm = re.sub(r"\s+", " ", name.strip().lower())
    h = hashlib.md5(f"{team_slug}:{norm}".encode()).hexdigest()
    return int(h[:9], 16)


def make_player(team_slug, name, class_level, weight, hometown, high_school, previous_school=None):
    first, *rest = name.split(" ", 1)
    last = rest[0] if rest else ""
    weight = weight.strip()
    if weight and not weight.endswith("lbs") and weight != "HWT":
        weight = f"{weight} lbs"
    return {
        "player_id": player_id_for(team_slug, name),
        "name": name,
        "first_name": first,
        "last_name": last,
        "class_level": class_level,
        "weight": weight,
        "hometown": hometown,
        "high_school": high_school,
        "previous_school": previous_school,
        "photo_url": None,
        "bio_url": None,
        "slug": None,
        "source": "manual_pdf_transcription",
    }


def parse_and_normalize(pdf_path, team_slug, list_style="wyoming"):
    """Auto-detects Cards/Grid/List and returns players in
    scrape_official_roster.py's schema. `list_style` disambiguates the two
    different "List" layouts Sidearm sites use ('wyoming' = single-column
    2-field cards, 'two_col' = Little Rock's 2-column 3-line cards) --
    detect_roster_view() can't tell these apart from the PDF's own label
    alone, so pass whichever this team's site actually renders."""
    # Little Rock's own site doesn't label a "Roster View - X" toggle at all
    # (that's a Wyoming/gowyo.com-specific header string) -- when the caller
    # already knows it's the 2-column layout, skip detection entirely.
    if list_style == "two_col":
        players = []
        for p in parse_two_col_list(pdf_path):
            class_level, weight = _split_two_col_stat(p["stat"])
            hometown, hs, prev = _split_two_col_home(p["home"])
            players.append(make_player(team_slug, p["name"], class_level, weight, hometown, hs, prev))
        return players, "List (2-column)"

    view = detect_roster_view(pdf_path)
    players = []

    if view == "Cards":
        for p in parse_cards(pdf_path):
            grade, hometown, hs = _split_cards_detail(p["detail"])
            players.append(make_player(team_slug, p["name"], grade, p["weight"], hometown, hs))

    elif view == "Grid":
        for p in parse_grid(pdf_path):
            if not p["name"]:
                continue
            players.append(make_player(team_slug, p["name"], p["class_level"], p["weight"],
                                        p["hometown"], p["high_school"], p["previous_school"] or None))

    elif view == "List":
        for p in parse_wystyle_list(pdf_path):
            weight, cls = _split_wystyle_weight_class(p["weight_class_raw"])
            hometown, hs = _split_wystyle_home(p["home_raw"])
            if not p["name"] or not weight:
                continue
            players.append(make_player(team_slug, p["name"], cls, weight, hometown, hs))

    else:
        raise ValueError(f"Unknown or undetected roster view '{view}' in {pdf_path}")

    return players, view


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: parse_manual_roster_pdf.py <pdf_path> [team_slug] [list_style]")
        sys.exit(1)
    pdf_path = sys.argv[1]
    team_slug = sys.argv[2] if len(sys.argv) > 2 else "preview"
    list_style = sys.argv[3] if len(sys.argv) > 3 else "wyoming"
    players, view = parse_and_normalize(pdf_path, team_slug, list_style)
    print(f"[{view}] {len(players)} players\n")
    for p in players:
        print(f"{p['name']:<25} {p['weight']:<10} {p['class_level']:<20} {p['hometown']:<28} {p['high_school']}")
