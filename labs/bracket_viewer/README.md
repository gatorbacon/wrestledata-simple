# Bracket Viewer (side project)

Standalone, format-agnostic bracket viewer. Not wired into either site (kept out of both
`frontend/` dirs on purpose). To ship on MatSavant later: copy this folder to
`frontend/wrestledata-ui/public/lab/brackets/` on `main`.

- **Data source (NCAA):** `data/ncaa-tourney-parsed/all_matches.json` (from `scripts/ncaa/parse_ncaa_results.py`).
  Years 2013-2026 (no 2020). `build_ncaa_bracket_data.py` writes `data/ncaa/{year}.json` + `data/index.json`.
- **Schema + layout rules:** documented in the header of `build_ncaa_bracket_data.py`. New bracket types = a new adapter that emits the same schema; the engine is untouched.
- **Engine:** `bracket_engine.js` (render + round navigator), `viewer.js` (weight tabs, tournament picker, URL state `?event=&w=&from=&n=`).
- **Run locally:** `python3 -m http.server 8765 -d labs/bracket_viewer` then open http://localhost:8765/
- **Known heuristic:** in a Round-of-32 match the odd seed is drawn on top (matches the published 2026 125 bracket); slot order only.

## Status (2026-09-24)

**Viewer v1: built, NOT yet visually verified.** The Chrome extension was disconnected, so only a JS syntax check was run. Open it locally and check drag/resize/hover behavior before building on it. Not committed; not deployed. Not linked from `/lab`.

Design (TJ's spec): weight tabs on top, bracket below, first weight default. The centerpiece is the round navigator: a draggable/resizable window over shared time columns that shows 2+ rounds at once and re-renders instantly (visible rounds stretch to fill width; vertical spacing tightens when only late rounds are shown). Hover a wrestler = highlight their path across both brackets; tap pins. Finished tournaments only for now (live tracker possibly later). Bracket viewer only, nothing more.

Limits: connectors are drawn only between adjacent visible columns; consolation drop-ins from the championship bracket and the 7th-place match have no line (drop-ins get a left-edge marker).

## Next project: historical brackets (pre-2013) from wrestlingstats.com

**Source:** `https://www.wrestlingstats.com/ncaa/brackets.htm` links one PDF per year, 1928-2026, at `/ncaa/pdf/brackets/NCAA{year}.pdf` (some older ones `NCAA%20{year}.pdf`, with a space). No robots.txt (404). Missing: 1943-45, 2020 (the 2020 link is broken); 1934/1938 are 1-page stubs; 2022/2023 link to NCAA session PDFs. Nothing is archived in the repo yet (downloaded to scratch only).

**Text layer:** present 1928-2014, 2016, 2021, 2024-26. Missing/poor: 2015 (almost no text), 2017-18 (scans, need OCR), 2019 (mostly images). We already have 2013+ from our own pipeline, so this source matters for 2012 and earlier; 2013-2016 are a test set (parse, then compare with `data/ncaa-tourney-parsed/all_matches.json`).

**PDF layout:** page 1 = summary (team scores, place winners with seeds `[n]`, `[US]` = unseeded). Then per weight: championship bracket, consolation bracket, pigtail page (only when there are pigtails). Every advancing line carries the winner + result, so each match is recoverable with its real slot position. Crop-based counting of the left column (`pdftotext -x 0 -W 190` champ / `-W 135` cons) works for names; see `research/survey_wrestlingstats_pdfs.py` (approximate: page-kind detection breaks on weights with no pigtail page).

**Structure eras found (script survey + a handful of pages checked by eye; older eras unconfirmed):**

| Era | Weights | Consolation | Places |
|---|---|---|---|
| 2009-2016 | 125-285 | 16 in round 1; exactly 1 champ + 1 cons pigtail per weight | 8 |
| 1999-2008 | 125-285 | 16; pigtails vary 0-5 per weight | 8 |
| 1987-1998 | 118-275 | 16 | 8 |
| 1986 | 118-190, unlimited | 16 (starts here) | 8 |
| 1979-1985 | 118-190, unlimited | 8 in round 1 | 8 |
| 1963-1978 | 118-190, unlimited | 8 | 6 |
| 1966-69 | 11 weights 115-191 | small (2-4) | 6 |
| 1952-65 | 115-191, unlimited | small (2-4) | 4, 6 from 1963 |
| 1949-51 | 7 weights + unlimited | small | 4 |
| 1928-48 | 6-7 weights, vary by year | none/incomplete | none listed |

Champ bracket is 8-16 slots with byes pre-1949, then 32 slots (byes pad small fields). Pigtails appear from 1967 (1-10 per weight; counts above ~5 in the 1980s need verifying); none in 1983, 1992-93, 1999-2000. Weight lists before 1952 need per-year confirmation.

**Plan:** (1) parser validated on 2013 vs `all_matches.json` (PDF adds bracket position; the viewer's odd-seed R32 heuristic only fit 2026); (2) walk back year by year, new bracket template whenever structure changes (like `data/bracket_templates/`); (3) store wrestlers/matches/slot/round/source page as a raw-to-clean layer; (4) career linking last.
