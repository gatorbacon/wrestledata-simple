# Team Record Book Leaderboards

Standalone tool — **not part of KentuckyMat or MatSavant**; it touches no website data. It turns the team's
season-stats Google Sheet into one HTML page with 12 leaderboards:

`{Boys, Girls} × {Pins, Wins, Takedowns} × {Career, Best Seasons}`

Career rows expand on click to show the season-by-season breakdown (season, that stat, W–L record).

## Run it

From the repo root:

```bash
.venv/bin/python scripts/team_records/build_team_leaderboards.py
open scripts/team_records/output/leaderboards.html
```

| Option | Meaning |
|---|---|
| *(none)* | Downloads the sheet (must be shared "anyone with the link can view") and rebuilds |
| `--file my_copy.xlsx` | Use a downloaded .xlsx instead (e.g. if sharing is turned off) |
| `--top N` | Rows per board (default 25; ties at the cutoff are kept) |
| `--girls-include-boys-section` | Count girls' 2022-23 matches vs boys toward the girls boards (see below) |
| `--sheet-id ID` | Use a different Google Sheet |

Standard library only — no packages to install (it includes its own small .xlsx reader).

Files: `build_team_leaderboards.py` (script) · `name_aliases.json` (name fixes — **you edit this**) ·
`output/leaderboards.html` (result) · `output/last_download.xlsx` (copy of the sheet used for the last run).

Sheet: `https://docs.google.com/spreadsheets/d/1DESABLd4B5x8zQ1jsGlwNLuJyiy8OyLd`

## How the sheet is read

- Only tabs named like `2024-2025` are read; everything else (hand-built leaderboards, `COMBINED Boys`, awards) is ignored.
- **Season** = the row's `Year` column, so `2025` → shown as `2024-25`. (This also makes the mislabeled
  `2023-2022` tab come out correctly as 2022-23.)
- **Boys / Girls** come from the `Boys Varsity` / `Girls Varsity` marker rows. Rows before any marker are boys.
  Header rows repeated inside a Girls block are handled. An unknown marker (e.g. `JV`) is skipped with a warning.
- **Pins** = `Fall (F)`. **Wins** = `Wins`. **Takedowns** = `T2 (F)` — the 2025-26 tab calls that column `T3 (F)`; it
  is the same stat (the sheet's own Season Takedown board confirms it). Columns are found by header name, so
  differing column orders/extra columns (`MD (F)`, the `(A)` columns) are fine.
- Blank stat cells count as 0 and are shown as `–` in the breakdown; a warning is printed.
- Two rows for the same person + season + gender are **added together** (warning printed).
- Wrestlers with 0 of a stat don't appear on that board.

## Names and aliases

Names are matched after normalizing case, spacing and `Last, First` ↔ `First Last` (automatic — no alias needed).
For real spelling differences, `name_aliases.json`:

```json
{ "aliases":  { "Nate Rush": "Nathaniel Rush" },   // variant -> the one name to show
  "exclude":  [ "Our Wrestler" ],                    // placeholder rows, not people
  "not_same": [ ["Ben Rush", "Ben Rusk"] ] }         // suggested pair you confirmed are different people
```

Every run ends by listing **possible name variants not yet handled**: pairs with similar spelling (or one a
nickname prefix of the other) that never appear in the same season. Two names in the same season can't be one
person, which removes most false alarms. Add each suggestion to `aliases` (same person) or `not_same` (different).
Alias values must be final names — chains (A→B, B→C) are rejected.

Currently aliased: Balylee→Baylee Reynolds, Nate→Nathaniel Rush, Phebe→Phoebe Smith, Arubrey→Aubrey White.

## Judgment calls (change here if you disagree)

- **Girls in the boys section (2022-23 only).** Before girls' wrestling was sanctioned, some girls appear in *both*
  sections of the 2022-23 tab (their matches vs boys, and vs girls). By default only the girls-section rows count
  for the girls boards, and their boys-section rows are left out of both boards. This matches the sheet's own
  hand-built girls totals (e.g. Lyla Smith 34 career pins). `--girls-include-boys-section` adds those rows in.
- **"Wrestler, Our"** in 2022-23 is a team placeholder (unattributed matches) and is excluded.

## Known data disagreements in the sheet (as of 2026-09-19)

The season tabs are the source of truth here, but the hand-built `COMBINED Boys` / `Combined Girls` tabs (which the
sheet's hand-typed career boards were built from) disagree with them, so those hand boards differ from ours.
Audit run 2026-09-19 (seasons written as the tab's season, e.g. 2020-21):

- **COMBINED Boys, 9 rows differ:** Ethan Montgomery 2018-19 (wins 9 vs 10) and 2019-20 (15 vs 16); Evan Browning 2020-21
  (whole row: pins 7 vs 12, W-L 27-7 vs 24-10, takedowns 37 vs 19, escapes, reversals); Jaimen Carey 2020-21 (wins 16 vs 23);
  Micah Thompson 2020-21 (takedowns 14 vs 22); Jackson Burger 2021-22 (pins 21 vs 20); Cruz Reynolds 2022-23 (wins 14 vs 17);
  Kaygen Roberts 2022-23 (losses 5 vs 3) and 2025-26 (COMBINED pins cell holds 136, his career total; season tab 25).
- **COMBINED Boys, 12 season-tab rows missing:** 2022-23 girls' boys-section rows (Cineus, Damis, Hundley, Aubrey White,
  Lyla Smith, Phoebe Smith), Jayce Crowe 2022-23, and 2024-25 Aiden Thompson, Anthony Delfino, Gage Feltner, Jayden Talley
  (plus Cameron Thews 2014-15, all zeros).
- **Combined Girls, 14 rows differ:** 2022-23 wins/losses are higher than any combination of the season tab's
  sections (Aubrey White 18-14 vs 2-2, Makyla Fowler 11-6 vs 2-2, Lyla Smith 13-8 vs 3-0, Teagan Hundley 4-4 vs 0-2,
  Demi Damis wins 5 vs 3); 2023-24 `TF (F)` holds unrelated values (7-31) for every girl except Aubrey White; 2023-24
  Aubrey White is all zeros on the season tab but 5 pins / 5-4 / 9 takedowns in Combined Girls; 2023-24 Teagan Hundley wins 4 vs 9.
- Also: Paul McClure's tabs total 102 wins vs 121 on the hand board (a season may be missing), Brandon Devins
  2013-14 has a blank pins cell, and Dakota Phillips has two rows in 2018-19 (merged).
