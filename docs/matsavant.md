# MatSavant — Comprehensive Reference

MatSavant (matsavant.com) is a **100% static analytics platform** for NCAA Division I men's wrestling. Every number shown on the site is pre-computed by local Python scripts and written to JSON files that the frontend fetches directly. There is no backend API, no database queries at runtime, and no server-side rendering.

---

## Repository Location

MatSavant lives on the **`main`** branch. All frontend files are in:

```
frontend/wrestledata-ui/public/
```

All data pipeline scripts are in `scripts/` (non-hs_ky), `xtp/`, and `scripts/mat_value/`.

---

## Architecture Overview

```
TrackWrestling (scrape)
        ↓
  scripts/ncaa/parse_ncaa_results.py          ← tournament bracket + results
  scripts/scraping/scrape_ncaa_tournament.py  ← live tournament data
        ↓
  mt/rankings_data/{season}/                  ← intermediate: rankings, match data
  mt/data/{season}/                           ← intermediate: processed match data
        ↓
  scripts/mat_value/compute_all_mat_values.py ← DPG + per-match impact
  scripts/bonus/compute_all_top33_bonus.py    ← bonus EV for xTP
  xtp/engine/engine.py                        ← expected team points
  scripts/ncaa/generate_replay.py             ← tournament replay JSON
        ↓
  frontend/wrestledata-ui/public/data/        ← static JSON served to site
```

Everything the frontend reads lives under `frontend/wrestledata-ui/public/data/`.

---

## Pages

| Page | File | Description |
|---|---|---|
| Homepage | `index.html` | Weight selector, DPG leaders, xTP team rankings, stat leaders (pins/techs/majors/wins), Hodge watch |
| Wrestler Profile | `wrestler.html` | Per-wrestler DPG, skill indices, match impact timeline, full match history |
| NCAA Live Tracker | `ncaa_live.html` | Tournament bracket replay — team leaderboard, projection history chart, big moments feed, by-weight cards, Lazarus Award |
| Seed Analysis | `ncaa_report.html` | Historical seeding vs. performance report |
| Scoring Trends | `ncaa_scoring_trends.html` | Bonus and scoring pattern analysis across rounds/years |
| Team Leaderboard | `ncaa_team_leaderboard.html` | xTP-ranked team table |
| Team Analysis | `ncaa_team_report.html` | Per-team deep-dive with dual meet stats |
| Conference Analysis | `ncaa_conf_analysis.html` | Conference-level aggregated stats |
| DPG Leaderboard | `leaderboards/mat_value.html` | Full DPG rankings by weight |

### Core JS Files

| File | Purpose |
|---|---|
| `app.js` | Wrestler profile rendering — DPG display, skill chart, match impact SVG, match history table |
| `header.js` | Site nav, Fuse.js search integration |
| `tooltips.js` | Metric definitions (displayed on hover) |

---

## Site Strategy & Information Architecture (Source of Truth)

Living rules for information architecture, naming, and UI. Follow this when adding pages or menu items. Do not invent a parallel nav or a second copy of an existing leaderboard.

Last aligned: September 2026. Originally drafted with Grok as `docs/MATSAVANT_SITE_STRATEGY.md`; merged here 2026-09-11 as the single official copy — do not recreate a separate strategy doc.

### Two products, one site

1. **Directory** — rankings, wrestler profiles, team pages, who-beat-whom, duals. This is the WrestleStat-shaped traffic. It compounds.
2. **Magazine** — Field Notes (threads), Tools (sims/generators), Lab (experiments), live Events. This is the X/Twitter voice. It does not compound unless it has a stable home.

Every new idea belongs in one bucket:

| Bucket | Question it answers |
|---|---|
| Rankings | Who is ahead? |
| Wrestlers / Teams | Who is this person / program? |
| Events | What happened at this tournament? |
| Field Notes | What is the argument? |
| Tools | What can I run? |
| Lab | What are we trying? |

If it does not sit on one of these, it does not get a top-nav link.

### Top navigation

Five items. No more.

```
MatSavant    RANKINGS ▾    WRESTLERS    TEAMS    EVENTS ▾    NOTES ▾     [search]    About
```

- Search is the real entry to profiles. Keep typeahead on every page.
- Do not add Tools, Lab, Matrix, DPG, Career DPG, or Transfers as top-level items.
- Group labels inside dropdowns (`WRESTLERS`, `RACES`) are not links.

#### Rankings ▾

```
WRESTLERS
  By weight          Top 33 by weight + P4P     ← default
  Matrix             Projected matchups (desktop only)

RACES
  Team race          NCAA title / xTP
  Hodge              Season P4P award
```

- Header **Rankings** click goes to **By weight**.
- Page title stays `Rankings` / `2027 Rankings` (season year). Do not call it Board.
- **Matrix** is hidden on mobile (menu row omitted or routed to By weight).
- Do not add a separate "DPG rankings" clone of By weight. DPG is a column + sort on By weight.
- If a real DPG *metric home* is built later (definition + all-weights list + field/beeswarm), it may return under Rankings as `DPG`. That page must not be another top-33 photo table.

#### Wrestlers

Landing page, not a dropdown.

- Search first.
- Weight pills: All · 125 · 133 · 141 · 149 · 157 · 165 · 174 · 184 · 197 · 285.
- **Spotlight · season DPG**: All = top 3 per weight; one weight = top 8. Names link to profiles.
- Link: `Full rankings →` (By weight). Do not dump the full 33-deep table here.

#### Teams

Landing page, not a dropdown.

- Search first.
- Conference pills, then every D1 team in a conference grid.
- Tile: name, logo if we have it, dual record + xTP (or title %), school color as a *subtle* accent.
- Click → team profile.
- Link: `Full team race →`.
- A short Top 15 xTP strip may sit above the grid. The grid is the page.

#### Events ▾

List **events**, not analysis page types.

```
  NCAA Championships
  Big Ten Championships
  Big 12 Championships
  National Duals
```

- One shell per event: **Live** when it is on, **Archive** when it is not.
- Seed analysis, scoring, team leaderboard, brackets = tabs *inside* the event.
- Offseason: all four still listed. Default Events click = NCAA archive.
- Live event may show a Live marker on that row.
- Do not put Midlands / duals / random invitationals in this menu. Those are schedule or Field Notes.

#### Field Notes ▾

```
  Field Notes    threads and write-ups     ← default
  Tools          sims and generators
  Lab            experiments
```

- Header **Field Notes** click goes to `/notes`.
- Tools and Lab are findable here, not only in a footer link.
- Career DPG and other experiments are cards *on* `/lab`, not extra menu rows.

### Homepage stack

1. Upcoming Duals
2. Rankings (P4P default, weight pills, `Full rankings →`)
3. Latest Note (one featured thread)
4. Team race strip (top programs, link to full page)

Do not pile Lab experiments, stat-leader tables, backtests, or archive charts onto first paint. Those are Field Notes, Lab, or footer.

### DPG public naming rule

Public definition (table caption):

> **DPG (dual points per match):** Measures how many extra dual points a wrestler adds or subtracts each time they wrestle, compared with what a typical wrestler gets against that same opponent.

Longer copy (ⓘ or DPG metric page only):

> Dual-point result (DEC 3, MD 4, TF 5, F 6 — or 0 for a loss) minus what a typical wrestler gets against that same opponent. Beat a #10 by major and you get a lot. Tech a #200 and you get a little. Season DPG is the **average** of those matches, not a total.

Do not use residual, expected value, mat_value, or TPAR in UI copy. TPAR was the old internal name; DPG is the public name. Backend may still say mv/mat_value — see [Stat Calculations → DPG](#1-dpg--dual-points-gained) for the actual formula.

**Adoption rule:** DPG lives on the main ranking table as a first-class column and sort. People copy the number next to the #1 wrestler. A duplicate leaderboard labeled DPG trains people that it is a side mode.

### Career DPG chart (profiles + Lab)

Season lollipops / bubbles:

- **y** = season DPG
- **x** = calendar year, even spacing
- **size** = matches (cap radius so two-season cards cannot swallow the plot)
- **fill** = school color, ~75–80% opacity, overlap allowed
- DNP years = tick, not an empty DPG
- Stem from 0 to the *edge* of the disc, not through the fill
- Labels: year + school under the axis; value by the disc
- Small-n seasons may use a hollow/dashed disc; do not use the same dash for the champion reference line
- Match-weighted averages; n < 6 shown on the chart, excluded from Δ
- If all seasons ≥ 0, yMin = 0 (do not reserve −1 empty space)

#### AA / champion reference marks

Compute **once** per report (not per wrestler):

- Pool all 10 weights
- Last 5 completed NCAA tournaments (exclude 2020 if no tournament)
- AA band = 25th–75th percentile of **that season's** DPG for wrestlers who were All-American **that season** (8 placewinners × 10 weights)
- Champion mark = **median** DPG of NCAA champions in the same window
- No match-count filter on those honor seasons unless data quality requires it

Draw only if the mark intersects the card's existing y-scale:

- AA band: clipped full-width rect, ~8–12% opacity, behind discs, no school color, no chip on the data
- Champ: thin dashed or 1px line; do not raise yMax just to reach it
- Exception: if `dataMax >= aaLow - 0.4`, nudge `yMax` to `aaLow + 0.3` so the floor of the AA band is visible
- Page caption once: shaded = typical AA season · dashed = typical champion

#### Lab home for the roster view

- Name: **Career DPG**
- URL: `/lab/career-dpg`
- Subtitle: `Season bubbles · size = matches · color = school`
- Individual or team (roster of cards)
- Stamp: `Lab · not a ranking`
- Stays in Lab until the same chart is embedded on wrestler profiles; then Lab can keep the team/roster browser only

### Field Notes / Tools / Lab

| | Field Notes | Tools | Lab |
|---|---|---|---|
| What | Longform threads + images | Interactive: input → output | Experimental views |
| Examples | X write-ups | Dual sim, team DPG graphic | Career DPG, field beeswarm drafts |
| URL | `/notes`, `/notes/:slug` | `/tools`, `/tools/:slug` | `/lab`, `/lab/:slug` |

Graduation:

- Lab view that becomes canonical (e.g. beeswarm on a future DPG metric page) leaves Lab.
- Tool people return to every dual weekend stays in Tools.
- Do not list tools inside the Field Notes article feed. A sim is not a thread.

#### Publishing a Field Note (source of truth: `scripts/notes/`)

There is no CMS/backend — Field Notes are authored as markdown in Obsidian and converted to the site's static JSON by a script. Two scripts, added 2026-09-13:

- `scripts/notes/new_note.py "Title"` — scaffolds `frontend/wrestledata-ui/notes_drafts/<slug>/note.md` (frontmatter: `title`, `hook`, `tags`) and opens it in Obsidian via the `obsidian://` URI. `frontend/wrestledata-ui/notes_drafts/` must be opened as its own Obsidian vault (not nested in a subfolder) with "New attachment location" = *Same folder as current file* and Wikilinks off, so a pasted screenshot auto-saves next to `note.md` and inserts a standard `![alt](file.png)` reference — no manual screenshot/drag/link steps. `OBSIDIAN_VAULT` in the script must match the vault's name exactly.
- `scripts/notes/publish_note.py <slug>` — converts the draft into the live format:
  - Body markdown → `frontend/wrestledata-ui/public/data/notes/body/<slug>.json` (`blocks`: `{"type":"p","html":...}` / `{"type":"img","src","alt","caption"}`). Paragraph markdown supports `**bold**`, `*italic*`, `` `code` ``, and `[text](https://...)` links, converted to pre-escaped HTML at publish time (safe because Field Notes are self-authored, not user-submitted).
  - `![alt](file.png)` on its own line = an image block; a lone `*caption*` line immediately after it becomes the caption. This is detected line-by-line (not by blank-line paragraph chunking), because Obsidian's paste and typical X-thread-style writing put an image directly under its caption text with no blank line in between. Referenced image files are copied from the draft folder into `frontend/wrestledata-ui/public/data/notes/images/<slug>/`. `http(s)://` and `/`-prefixed image refs are left as-is (external or already-published), and still count toward the note's thumbnail even though nothing is copied.
  - Obsidian names pasted screenshots with spaces (`Pasted image ....png`) but URL-encodes the space as `%20` in the markdown link it inserts — the script unquotes the reference before looking the file up on disk, then re-quotes it for the published `src`.
  - Adds/updates the entry in `frontend/wrestledata-ui/public/data/notes/notes.json` (matched by slug, so re-running after edits is safe).
  - Reruns `scripts/generate_matsavant_sitemap.py` (skip with `--no-sitemap`).

`frontend/wrestledata-ui/notes_drafts/` is the draft workspace — it sits outside `public/` so nothing in it is deployed until `publish_note.py` runs. `note.js`'s paragraph renderer reads `block.html` when present (falls back to escaping `block.text` for any older hand-written body files).

### Naming

| Avoid | Use |
|---|---|
| Board | By weight / Rankings |
| Rankings (Traditional) | By weight |
| TPAR | DPG |
| Expected Team Points as a menu name | Team race (xTP is a column) |
| Tournaments | Events |
| Profiles | Wrestlers / Teams |
| Sandbox / Experiments as menu labels | Lab |
| Trajectory / Bubbles as page titles | Career DPG |
| Heisman (unless that is the official name we chose) | Hodge for the season P4P award |

### URL map (target)

```
/                       homepage
/rankings               By weight + P4P
/rankings/matrix        desktop
/rankings/teams         Team race / xTP
/rankings/hodge         season P4P award
/wrestlers              index
/wrestlers/:slug        profile
/teams                  index
/teams/:slug            profile
/events/ncaa
/events/big-ten
/events/big-12
/events/national-duals
/notes
/notes/:slug
/tools
/lab
/lab/career-dpg
```

This is a **target**, not necessarily the current live routing — check actual files under `frontend/wrestledata-ui/public/` before assuming a route exists.

### Build order (when adding work)

1. Keep Rankings dropdown + By weight as the default board. DPG column/sort stays here.
2. Wrestler profiles: match list → opponent profile (the click loop).
3. `/notes` index + homepage featured Note.
4. Event shells (four events); old tournament analysis pages become tabs or Field Notes.
5. `/tools` and `/lab` indexes. Career DPG is a Lab card.

### Do not

- Add a seventh top-nav item for a new idea. It starts in Lab or Field Notes.
- Ship two leaderboards that are the same wrestlers in a different sort.
- Put school colors on a league-wide honor chart (field / qualifier / AA / champ uses gray / blue / gold / ring).
- Autoscale a Career DPG card to include −1 when every season is positive.
- Leave Matrix as a mobile layout.
- Treat group headers in dropdowns as pages.

---

## Data Directory Structure

```
frontend/wrestledata-ui/public/data/
├── {year}/
│   └── simulation_replay.json        ← full NCAA tournament replay (2014–2026)
├── wrestlers/
│   └── {year}/
│       ├── by_id/{wrestler_id}.json  ← individual wrestler profiles
│       └── index_wrestlers.json      ← search index
├── mat_value/
│   └── {year}/
│       ├── mat_value_{year}.json     ← DPG leaderboard
│       └── match_mv_impact_{year}.json ← per-match DPG impacts
├── xtp/
│   └── teams/
│       ├── teams.json                ← xTP team leaderboard
│       └── {team_slug}.json          ← per-team xTP detail
├── rankings/
│   └── {year}/
│       └── {date}/                   ← weekly ranked wrestler lists
└── bonus/
    └── {year}/                       ← Top-33 bonus EV per wrestler
```

---

## NCAA Ranking Methodology (Source of Truth)

`current_rank` — the number shown everywhere on the frontend (wrestler profile hero, `mat_value_{season}.json`'s own `current_rank` field, team rosters, the transfer/roster report pipeline) — must always be derived using the rules below. **The internally-generated "matrix rank" (`generate_matrix.py` / `mt/rankings_data/`) must never be read by anything that writes a user-facing JSON file.** We still generate the matrix (kept for possible future internal use), but as of this doc it is explicitly retired from being anyone's source of truth for a published rank. If you ever find code computing or displaying a rank from the matrix, or from any source other than what's below, stop and flag it — either fix it or get an explicit, documented exception approved.

### The rule, by era

| Era | Ranks 1–8 | Ranks 9–12 | Ranks 13–33 | 34+ |
|---|---|---|---|---|
| Current season (live) + 2023–2026 (settled) | Latest/final FloWrestling snapshot, as many spots as Flo actually publishes that week/season (not a fixed cutoff — commonly 24 or 33) | *(same Flo snapshot, continued)* | *(same Flo snapshot, continued)* | ELO for everyone Flo doesn't rank |
| 2019, 2021, 2022 *(2020 excluded — no tournament)* | Actual tournament placement (1st–8th) | Full field is really committee-seeded from 2019 on — sort the rest by seed | Same — seed order | ELO for anyone outside the 33-man qualifying field |
| 2020 (COVID — tournament cancelled) | committee seed order, 1–33 (no results exist to place against) | " | " | ELO |
| 2012–2018 *(only the top 16 were really seeded — 17–33 was a blind random draw, not a committee judgment)* | Actual tournament placement (1st–8th) | The 4 "blood round" (`C_QF`) losers: any with a **real** seed (≤16) sort first, by that seed ascending; any without a real seed (seed >16, i.e. random draw) sort after, by ELO | Remaining qualifiers, same split: real-seed (≤16) ones first by seed, then unseeded ones by ELO | ELO for anyone not in the tournament |

### Why it's tiered this way

- **Flo era (2023+, and current season)**: FloWrestling's editorial ranking is real, human-judged signal and the best available source whenever it exists. ELO fills in anyone below however far Flo ranked that week.
- **2019, 2021, 2022**: no real Flo data exists for these seasons (confirmed directly from the scraped files — see below), but the NCAA committee had already expanded to seeding the *entire* qualifying field by 2019, so seed order is a legitimate signal for the whole 33, not just the top of it. Tournament results still override the committee's pre-tournament guess for anyone who actually earned a top-8 finish.
- **2020**: the tournament was cancelled (COVID) before a single match was wrestled, so there is no placement signal at all that year — it degrades to pure seed order for the full field.
- **2012–2018**: seeding only covered 1–16 in these years. TrackWrestling's scraped seed files still show a number for every entrant (17–33), but that number is a random blind-draw bracket slot, not a real committee judgment — it must never be treated as signal. So for the 9–12 and 13–33 tiers, only wrestlers with a real seed (≤16) get sorted by that seed; everyone else in those tiers falls back to ELO.

### Where each raw source lives

| Source | Path | Notes |
|---|---|---|
| FloWrestling rank snapshots | `data/{season}/flo-preseason-rankings/*.json`, one file per scrape date (`YYYY-MM-DD.json`) | Folder name is a legacy misnomer — it holds every snapshot scraped through the season (preseason, in-season touch points, and a postseason one when Flo publishes it), not just preseason. `ranking_date` + `source` fields in each file tell you which: real data has `"source": "FloWrestling"`; the no-Flo-available seasons instead have a single file with `"source": "ncaa_tournament_seeds_and_placement"`. `apply_flo_rankings.py` always takes whichever file sorts last by filename (the latest date) as authoritative for that pipeline run. Scraped by `scripts/scraping/scrape_flo_preseason_rankings.py`. **Confirmed real-Flo coverage: 2023–2026 (and current season) only** — checked the files directly rather than assuming; 2022 does *not* have real Flo data despite being a recent season. |
| NCAA committee seeds | `data/{season}/ncaa-tourney/seeds/{weight}.txt`, tab-separated (`Seed / Name / Team / Grade / Record / Scoring`) | Present 2012–2026, 33 rows/weight. Only ranks 1–16 are a real committee judgment before 2019 — see above. |
| NCAA tournament match-by-match results | `data/{season}/ncaa-tourney/results.txt`, plain text, one match per line under round-label headers (e.g. `Cons. Round 4 (32 Man)`, `Cons. Semis (32 Man)`, `1st/3rd/5th/7th Place Match`) | Present 2012–2026. 2020 exists as a file but has zero placement-match lines (tournament cancelled). Round-label → guaranteed-placement mapping used to find the "blood round": |

  | Round (canonical label) | Locked min. placement |
  |---|---|
  | Championship Finals | 2nd |
  | 3rd place match | 4th |
  | Championship SF / Consolation SF (`C_SF`) | 6th |
  | 5th place match | 6th |
  | **Consolation QF (`C_QF`) — the "blood round"** | **8th if you win it; unplaced (9th–12th) if you lose it** |
  | 7th place match | 8th |

  `results.txt`'s raw scraped text labels (e.g. `Cons. Round 4 (32 Man)`) still need mapping to this canonical scheme per year — bracket sizes/labeling can shift slightly year to year, so this is real parsing work, not a lookup table.

| ELO ratings | `mt/elo_ratings/ncaa_men/{season}/elo_ratings.json` | Built by `scripts/rankings/calculate_elo_ratings.py`. Per wrestler: `elo_score`, `elo_rank`, `matrix_rank` (**do not use** — see matrix-rank ban above), `hybrid_rank`. |
| Matrix rankings — **internal/dev use only, never wire to a public JSON** | `mt/rankings_data/ncaa_men/{season}/rankings_{weight}.json` | Built by `scripts/rankings/generate_matrix.py`. Kept for possible future internal use only. |

### Compliance status (fixed 2026-09-09 for 2019–2026; 2012–2018 still open)

**Fixed and reprocessed, 2019–2026:**
- `scripts/rankings/calculate_elo_ratings.py`: added `calculate_ncaa_hybrid_ranks_by_weight()` / `load_flo_ranked_by_weight()`, used only for `league == 'ncaa'`. Trusts ONLY entries tagged `flo_ranked: True` in `rankings_<weight>.json` (real Flo, or the seed+placement substitute — both legitimate) for the top tier, using their existing rank number as-is; ELO-sorts everyone else. The old generic `calculate_hybrid_ranks_by_weight()` (HS) is untouched. Writes the correct value into `hybrid_rank`/`hybrid_rank_by_weight` in `mt/elo_ratings/ncaa_men/{season}/elo_ratings.json`.
- `scripts/rankings/build_wrestler_profiles.py`: NCAA branch now loads and passes `hybrid_rank_by_id` (previously never called for NCAA). `current_rank` for NCAA now never falls back to matrix rank — if no hybrid rank exists it's left unset rather than silently matrix-derived.
- `scripts/mat_value/compute_all_mat_values.py`: `write_season_dataset()` now reads `current_rank` from `elo_ratings.json`'s hybrid rank instead of `rankings_<weight>.json`'s raw `rank` field.
- `scripts/rankings/apply_flo_rankings.py`: fixed a pre-existing crash (`remaining.sort()` on a `None` rank — happens whenever a prior `write_rankings_from_elo()` run had already nulled out 0-match wrestlers) that was blocking re-runs.
- Verified against the real bug report: Antrell Taylor (Nebraska, 157) — 2025 now correctly shows `current_rank: 1` (matches his NCAA title), 2026 now shows `current_rank: 3` (matches FloWrestling's actual final ranking) — both were wrong before this fix (2025 showed 2, 2026 showed 1).
- Confirmed 2019/2021/2022's existing `build_seed_placement_rankings.py` output ("top 8 = actual placement, 9+ = remaining seed order") and 2020's existing COVID fallback (pure seed 1–33 when `results.txt` has no placement lines) **already matched the new rule exactly** — no rework needed there, just re-running the now-fixed downstream steps. Re-ran the full chain (`apply_flo_rankings.py` → `calculate_elo_ratings.py` → `build_wrestler_profiles.py` → `compute_all_mat_values.py`) for every season 2019–2026; spot-checked plausible top-of-weight results after each.

**2012–2018: fixed 2026-09-09.** `scripts/rankings/build_seed_placement_rankings.py` now has a `season < 2019` mode alongside the original (2019/2021/2022 unchanged) — both share the same seed/placement parsing and output schema by design, so they can't drift apart the way separate scripts could. The pre-2019 mode:
- Parses the *entire* match-by-match bracket (`parse_full_bracket()`), not just the 4 placement-match lines.
- Identifies the "blood round" (`find_blood_round_losers()`) **structurally** rather than by a hardcoded round-name string (label text like `Cons. Round 4 (32 Man)` isn't guaranteed identical every year): it's whichever round's losers are permanently eliminated (never appear again) and unplaced, while 100% of that same round's winners eventually do place — the *first* such round found scanning from the placement matches backward, since a bracket round further back also eliminates exactly 4 unplaced wrestlers each (a lower tier, not the blood round) and would otherwise be ambiguous with a simple "count of 4" check. Verified by hand-tracing two different season/weight combinations (2019 125, 2015 133) before trusting it, then dry-run-checked clean (no fallback warnings) across all of 2012–2018.
- Splits both the 4 blood-round losers (ranks 9–12) and the remaining qualifiers (ranks 13–33) into real-seeded (≤16, sorted by seed) then unseeded (sorted by Elo) via `sort_seeded_then_elo()`.
- Needs `mt/elo_ratings/ncaa_men/{season}/elo_ratings.json` to already exist for that season (a one-time exception to the normal apply-Flo-before-calculate-Elo order — see the script's module docstring for why that's safe for a completed historical season).
- A handful of blood-round losers per season had a results.txt/seed-file name-spelling mismatch (e.g. "Mario Gonzalez" in 2014) — kept rather than silently dropped, treated as unseeded (Elo-sorted) since their real seed couldn't be confirmed.

Ran the full chain for all of 2012–2018 (`apply_flo_rankings.py` → `calculate_elo_ratings.py` → `build_wrestler_profiles.py` → `compute_all_mat_values.py`), then the required full `build_wrestler_profiles.py` sweep across every season 2012–2026 (see "Rebuild order" below) so every `season_summary` snapshot reflects the newly-correct pre-2019 data too. **All eras (2012–2026) are now on the documented methodology — no known remaining compliance gaps.**

**Known, deliberately out of scope for this fix:** `write_rankings_from_elo()` (in `calculate_elo_ratings.py`) still re-sorts `rankings_<weight>.json` by raw Elo score after `current_rank`'s correct value has already been computed and saved — this doesn't affect `current_rank` anymore (that's read from `elo_ratings.json` now, not this file), but it does mean `rankings_<weight>.json`'s `rank` field — still used for the *opponent* rank shown in a wrestler's match history — can show Elo-order rather than true Flo/placement order. Not fixed here since it wasn't the reported problem; flag if it comes up.

### Rebuild order after any ranking-affecting change

Getting `current_rank` right for one season isn't enough by itself — the site can still show stale numbers afterward if the rebuild order below isn't followed. This bit us for real during the 2026-09-09 fix: fixing 2025 *after* 2026 had already been built left 2026's own profile pages still showing Antrell Taylor's old (wrong) 2025 rank, even though 2025's own profile file was already correct.

**Step 1 — per affected season, in this exact order:**
```
scripts/rankings/apply_flo_rankings.py -season {year}          # refresh flo_ranked tags from the latest snapshot
scripts/rankings/calculate_elo_ratings.py -season {year} --league ncaa --gender men   # writes hybrid_rank to elo_ratings.json
scripts/rankings/build_wrestler_profiles.py -season {year}     # writes current_rank into that season's own profiles
scripts/mat_value/compute_all_mat_values.py --season {year}    # writes current_rank into mat_value_{year}.json
scripts/rankings/hodge_candidates.py -season {year}             # rebuilds Hodge Watch off the now-current rank/profile data
```
`calculate_elo_ratings.py` must run after `apply_flo_rankings.py` in the *same* pass — it reads `rankings_<weight>.json`'s `flo_ranked` tags to build `hybrid_rank`, and a stale/missing tag silently falls the wrestler to the Elo tier instead of trusting Flo. Do this for every season whose underlying rank data changed before moving to Step 2 — don't interleave.

**Step 2 — after EVERY affected season has been through Step 1, re-run `build_wrestler_profiles.py -season {year}` again for EVERY NCAA season (not just the ones that changed), in any order.** This is the step that was missed the first time. Reason: `season_summary` (the per-season table on a wrestler's profile page, e.g. `wrestler.html`'s "SEASON / TEAM / CLASS / RANK / RECORD / DPG" rows) is built by `build_ncaa_season_summary_lookup()`, which re-reads *every other season's own already-published profile file* off disk at the moment it runs — it is not computed from a shared live source, it's a snapshot taken at build time. A wrestler with a 2023-2026 career gets a `season_summary` row for each of those years baked into *every one* of their season profile files; if season A is rebuilt before season B is fixed, season A's copy of season B's row is stale until season A is rebuilt again. Since careers span many seasons, in practice this means: **any time more than one season's rank data changes in the same pass, plan on a full second `build_wrestler_profiles.py` sweep across every season at the end**, not just the ones that changed.

`compute_all_mat_values.py` and `apply_flo_rankings.py`/`calculate_elo_ratings.py` do **not** have this cross-season snapshot problem — each season's own file is self-contained — so Step 2 only needs to re-run `build_wrestler_profiles.py`.

**Not required for a rank-only fix, but part of the same family of "what needs to be re-run" questions:** `scripts/generate_search_index.py -league ncaa -season {year}` (search index doesn't display rank, so it wasn't stale from this specific fix, but it's another per-season snapshot artifact worth knowing about), `scripts/rankings/hodge_candidates.py -season {year}` (see below — depends on the exact same `elo_ratings.json` + wrestler-profile data this chain produces, so it goes stale right along with them), and the weekly pipeline's later steps (bonus EV, xTP, team profiles/metrics — see the main weekly pipeline order in root `CLAUDE.md`) if DPG/mat_value numbers themselves changed, not just rank.

### Hodge Trophy Candidates

**Script:** `scripts/rankings/hodge_candidates.py -season {year}` — writes `frontend/wrestledata-ui/public/data/awards/hodge/{season}/hodge_{season}.json`, read directly by `hodge.html`/`hodge.js`.

**Data sources:** candidate pool (top-N by weight) comes from `mt/elo_ratings/ncaa_men/{season}/elo_ratings.json`'s `hybrid_rank_by_weight` — the same rank-of-record described above, not the banned matrix rank. Per-candidate stats (win/loss, bonus/fall rate, quality-of-competition, dominance) are computed by reading that candidate's own already-published `frontend/wrestledata-ui/public/data/wrestlers/{season}/by_id/{wrestler_id}.json` and iterating its `match_list` (`result`, `method`, `opponent_rank` are all already resolved there — no separate opponent lookup needed).

**Incident (found + fixed 2026-09-11):** this script previously read `mt/rankings_data/{season}/rankings_{weight}.json` + `weight_class_{weight}.json` for both rank *and* match data. Two independent problems: (1) that's the internal matrix-rank source this doc bans from ever feeding a public JSON, predating the 2026-09-09 rank fix and never brought into compliance with it; (2) separately from the rank-source issue, that specific data directory had simply stopped being regenerated mid-season (last touched Dec 2025, an abandoned earlier rankings pipeline run) — so even the win/loss counts themselves were frozen mid-season (e.g. the reigning #1 candidate showing 10-0 instead of his real final 26-0). Rewritten to read the current-methodology sources above; also wasn't listed anywhere as a step to re-run after a ranking change (this section) or in the Key Scripts table (below) — both fixed at the same time. Was not previously part of any documented weekly/rebuild procedure; **now it is** — see Step 1 above, chain order matters (it needs `calculate_elo_ratings.py` and `build_wrestler_profiles.py` to have already run for that season).

---

## Stat Calculations

### 1. DPG — Dual Points Gained

**What it is:** The primary individual performance metric. Displayed as "DPG" everywhere in the UI (formerly displayed as "TPAR" — the old name is retired site-wide, but you may still see it in old screenshots, commit history, or the private research scripts under `scripts/analysis/`). The underlying computation is called **Mat Value (MV)** in the scripts, and `mv`/`mat_value` remain the internal field names, script names (`compute_mat_value.py`, `compute_all_mat_values.py`), and JSON filenames (`mat_value_{year}.json`, `match_mv_impact_{year}.json`) — only the public-facing display name changed.

DPG measures how much better (or worse) a wrestler performs compared to what a typical wrestler gets against that same opponent. Concretely: your dual-point result (DEC 3, MD 4, TF 5, F 6) minus what a typical wrestler gets against that same opponent — beat a #10 by major and you get a lot, tech a #200 and you get a little. It is calculated per match and then averaged across the season (a rate, not a total). Note this is *not* a "replacement level" baseline in the WAR sense — see the note on `μ(r)` below for what the baseline actually is.

**Script:** `scripts/mat_value/compute_mat_value.py`

#### Step 1 — Encode match result as a signed value

Every match result maps to a team point value and then gets a sign based on win/loss:

| Result | Team Pts | Win | Loss |
|---|---|---|---|
| Decision (DEC) | 3 | +3 | −3 |
| Major Decision (MD) | 4 | +4 | −4 |
| Technical Fall (TF) | 5 | +5 | −5 |
| Fall / Pin / INJ / DQ | 6 | +6 | −6 |

TB (tiebreaker) and SV (sudden victory) are treated as decisions.

#### Step 2 — Build the opponent's baseline expectation

The system estimates how much value the opponent *typically* produces, using a shrinkage model that pulls toward a tier average.

Rank tiers and their anchor points:

```
Tier anchors: ranks 1, 10, 30, 50, 100, 150, 200
```

For an opponent at rank `r`, the tier baseline `μ(r)` is computed by linear interpolation between the two nearest anchor means.

**Where `μ(r)` (the anchor means) come from — not arbitrary, not fixed:** Only the anchor *rank positions* (1, 10, 30, 50, 100, 150, 200) are hardcoded. The mean *value* at each anchor is recomputed empirically every run, scoped to that specific season + weight class (`compute_tier_averages()` in `compute_mat_value.py`): for a tier like ranks 10–30, it pulls every match played that season, at that weight, by every wrestler ranked in that band, and averages their signed match-point outcome. So "replacement level" for a given opponent rank is literally "what wrestlers of that rank tier actually averaged, at that weight, that season" — it floats with the data rather than pinning to a universal constant. This means DPG's zero point is relative and self-calibrating per season/weight: a bonus-heavy or unusually close weight class that year shifts what counts as "0 DPG," and a "+0.0" wrestler one year isn't guaranteed to be the same real skill level as a "+0.0" wrestler the same weight the year before.

**Shrinkage formula (k = 20):**

```
opp_shrunk = (n × opp_raw_avg + 20 × μ(r)) / (n + 20)
```

where `n` = number of matches the opponent has wrestled, and `opp_raw_avg` = the opponent's observed mean signed value across all their matches.

This shrinkage pulls low-n opponents toward their tier average, preventing a wrestler from getting a huge DPG boost just for beating a highly-ranked opponent who has only wrestled once.

#### Step 3 — Compute per-match DPG impact

```
expected_signed = −opp_shrunk
dpg_match = result_signed − expected_signed
```

The negative sign on `opp_shrunk` is because the opponent's observed average is measured from *their* perspective, so it gets flipped to represent what *our* wrestler should expect.

**Example:** Wrestler beats a #10-ranked opponent by MD (+4). That opponent has a shrunk average of +0.8 (usually wins by a small margin). Expected = −(+0.8) = −0.8. DPG impact = 4 − (−0.8) = **+4.8** (well above expectation).

#### Step 4 — Season DPG

```
DPG = mean(all dpg_match values across the season)
```

Forfeits and medical forfeits are excluded from all calculations.

**Output:** `mat_value/{year}/mat_value_{year}.json` — leaderboard of all wrestlers sorted by DPG. Per-match impacts stored in `match_mv_impact_{year}.json`. Both files, and the `mv_avg`/`mv_rank_overall`/`mv_rank_weight` fields inside them, keep the legacy `mv`/`mat_value` naming — untouched by the TPAR→DPG display rename.

**Other places this same number appears, with a `dpg`-keyed field (not `mv`):**
- `mat_value/{year}/rolling_mbt_{year}.json` — per-date rolling trajectory for the wrestler-profile chart (`compute_rolling_mbt.py`), each point shaped `{"date", "dpg", "matches"}`.
- `mat_value/2026/dpg_mbt_2026.json` — in-season MBT blend intermediate (`make_mbt_official.py`), keys `dpg_50_50`/`dpg_75_25`/`dpg_100_0` (only exists for the season still being officialized).
- `data/reports/transfers/*.json`, `data/reports/team_roster/*.json`, `data/reports/wrestler_view/*.json` — the transfer/roster/wrestler report pipeline (`scripts/reports/build_transfer_dpg_report.py` and friends), each season entry shaped `{..., "dpg", "matches"}`.
- `data/p4p/{season}.json` — homepage pound-for-pound widget (`scripts/rankings/build_p4p_rankings.py`), per-wrestler `"dpg"` field.

All of the above were renamed from a literal `"tpar"` key to `"dpg"` on 2026-09-09 as a pure key rename (existing files were rekeyed in place with a small migration script, not recomputed) — same day as the TPAR→DPG display rename. If you're adding a new script that reads or writes any of these files, use `dpg`, not `tpar` or `mv`.

---

### 2. SI+, DF+, PE+, DI+ — Skill Indices

These metrics measure *how* a wrestler scores and defends, adjusted for opponent quality. They are standardized to a mean of 100 / std of 10 so a score of 110 means one standard deviation above average.

**Spec doc:** `docs/aps_apg_di_v2_spec.md`

**Index names:**
- **SI+** — Scoring Index (how well you score relative to who you're facing)
- **DF+** — Defense Index (how well you prevent scoring relative to who you're facing)
- **PE+** — Pin/Escape Index (bonus point propensity, called APR+ in some older UI labels)
- **DI+** — Dominance Index (weighted composite)

#### Constants

```python
PF7_CAP = 25       # Points-for per 7 min cap
PA7_CAP = 25       # Points-against per 7 min cap
PD7_CAP = 20       # Point differential per 7 min cap
SHRINK_K = 8       # Opponent shrinkage constant
MIN_MATCHES_FOR_RAW = 3
DI_WEIGHT_SI = 0.40
DI_WEIGHT_DF = 0.45
DI_WEIGHT_PE = 0.15
```

#### Step 1 — Per-match raw scoring rates (non-fall matches only)

```
PF7_raw = points_for  × 420 / seconds_wrestled
PA7_raw = points_against × 420 / seconds_wrestled

PF7 = min(PF7_raw, 25)
PA7 = min(PA7_raw, 25)
PD7 = clamp(PF7 − PA7, −20, 20)
```

The caps prevent a quick 15-0 tech fall against a weak opponent from inflating a wrestler's stats.

#### Step 2 — Assign opponent rank quintile

Divide all ranked wrestlers at the weight class into five quintiles:

```
p = (rank − 1) / (total_ranked − 1)

Q1: p ≤ 0.20  (top 20%)
Q2: p ≤ 0.40
Q3: p ≤ 0.60
Q4: p ≤ 0.80
Q5: remainder
```

#### Step 3 — Shrink opponent's PF7/PA7

```
If opponent has < 3 matches:
    PF7_adj = quintile baseline mean
    PA7_adj = quintile baseline mean

Otherwise:
    PF7_adj = (n/(n+8)) × PF7_raw + (8/(n+8)) × PF7_baseline_Q
    PA7_adj = (n/(n+8)) × PA7_raw + (8/(n+8)) × PA7_baseline_Q
```

#### Step 4 — Per-match contributions

```
APS7_contrib = PF7_match − PA7_adj(opponent)
APG7_contrib = PF7_adj(opponent) − PA7_match
APR_contrib  = PA7_adj(opponent)   ← pin/escape rate signal
```

#### Step 5 — Opponent weighting

Matches are weighted by the opponent's quintile rank. Opponents with fewer than 3 matches get a near-zero weight (0.05):

```
Q1 weight: 1.00    Q2 weight: 0.75    Q3 weight: 0.50
Q4 weight: 0.30    Q5 weight: 0.15    n<3:  weight: 0.05
```

Intermediate quintiles use linear interpolation.

#### Step 6 — Wrestler-level adjusted stats

```
APS7 = Σ(APS7_contrib × weight) / Σ(weights)
APG7 = Σ(APG7_contrib × weight) / Σ(weights)
APR  = Σ(APR_contrib  × weight) / Σ(weights)
APD7 = APS7 + APG7
```

#### Step 7 — Standardized indices

League means and standard deviations are computed across all ranked wrestlers at each weight class for the season.

```
SI+ = 100 + 10 × ((APS7 − APS7_mean) / APS7_std)
DF+ = 100 + 10 × ((APG7 − APG7_mean) / APG7_std)
PE+ = 100 + 10 × ((APR  − APR_mean)  / APR_std)
```

#### Step 8 — Dominance Index

```
DI+ = 0.40 × SI+ + 0.45 × DF+ + 0.15 × PE+
```

Defense is weighted slightly more than scoring (0.45 vs 0.40) because defensive consistency is a stronger predictor of performance at high levels.

---

### 3. Top-33 Bonus EV

This metric estimates how many bonus points (MD=1, TF=1.5, Fall=2) a wrestler expects to score *against top-33 opponents*. It feeds directly into the xTP engine.

**Script:** `scripts/bonus/compute_top33_bonus.py`

#### Bonus severity scale

```python
DEC:  0.0    MD: 1.0    TF: 1.5    FALL/INJ/DQ: 2.0
```

#### Peer tiers for shrinkage baseline

```
P1: ranks  1–8     P2: ranks  9–16
P3: ranks 17–33    P4: ranks 34+ (or unranked)
```

#### Calculation

For each wrestler, collect all wins vs. top-33 opponents and compute:

```
raw_ev = Σ(bonus_severity for each top-33 win) / n_wins
```

Then shrink toward the peer tier baseline (k = 8):

```
If n_wins == 0:
    shrunk_ev = peer_tier_baseline

Otherwise:
    shrunk_ev = (n_wins × raw_ev + 8 × peer_tier_baseline) / (n_wins + 8)

shrunk_ev = clamp(shrunk_ev, 0.0, 2.0)
```

The shrunk value is what the xTP engine uses as `bonus_ev_shrunk`.

---

### 4. xTP — Expected Team Points

xTP projects how many NCAA tournament team points a wrestler (and by extension their team) will likely score, before and during the tournament.

**Engine:** `xtp/engine/` (bracket_schema, probability, scoring, engine)

#### Win probability model

**Not to be confused with the live, in-match win-probability model** (see [Live Win-Probability Model](#live-win-probability-model-lab) below) — this one is xTP-internal, pre-match only, and has no notion of score/clock/position. It answers "who wins this hypothetical matchup" from rank+DPG alone; the other answers "given the match state right now, who wins" from an actual bout's play-by-play.

For any potential matchup between wrestlers i and j:

```
z = 1.0 × log(rank_j / rank_i) + 0.25 × (DPG_i − DPG_j)
P(i wins) = sigmoid(z) = 1 / (1 + e^−z)
```

Unranked wrestlers are assigned rank 200. Constants `α = 1.0` (rank influence) and `β = 0.25` (DPG influence) are tunable.

#### Advancement points

```
Championship bracket  (R32, R16, QF, SF wins): +1.0 per win
Consolation bracket   (PIG, R1, R2, R3, R4, QF, SF wins): +0.5 per win
Placement matches     (3rd, 5th, 7th): +0.0 (only placement points)
Finals:               +0.0 (only placement points)
```

#### Placement points

```
1st: 16    2nd: 12    3rd: 10    4th: 9
5th: 7     6th: 6     7th: 4     8th: 3
```

#### Expected bonus points per slot

```
opponent_multiplier:
    Ranks  1– 8: 0.50x    Ranks  9–16: 0.75x
    Ranks 17–24: 1.00x    Ranks 25+:   1.15x

expected_bonus = P(win) × min(bonus_ev_shrunk × opponent_mult, 2.0)
```

Bonus is capped at 2.0 points (pin/forfeit max).

#### xTP per wrestler

```
xTP = Σ over all possible bracket outcomes:
    P(advance to slot) × (advancement_pts + expected_bonus + placement_pts)
```

#### xTP per team

```
xTP_team = Σ(xTP_wrestler) for all team members entered in tournament
```

The engine runs both pre-tournament (full bracket simulation) and live (locking in completed match results and re-computing from current bracket state).

---

### 5. AA DPG Range (reports pages only)

**What it is:** A benchmark overlay drawn on every DPG chart in the report suite (`frontend/wrestledata-ui/public/reports/`) — a light-blue shaded band showing the 25th-75th percentile of DPG among NCAA All-Americans (top-8 finishers), plus a dotted line for the average DPG of NCAA champions, both pooled over the 5 most recently completed seasons and **not weight-dependent** (one flat set of numbers reused on every chart, regardless of weight class).

**Script:** `scripts/reports/build_aa_dpg_band.py`
**Output:** `frontend/wrestledata-ui/public/data/reports/aa_dpg_band.json` — `{"seasons_used": [...], "aa_p25": x, "aa_p75": y, "champ_avg": z, "n_aa": 400, "n_champ": 50, "generated": "..."}`

**Method:**
1. Auto-detects the 5 most recent seasons with both real tournament placement data (`data/ncaa-tourney-parsed/all_wrestlers.json`) and finalized DPG data (`mat_value_{year}.json`) — never hardcoded to a fixed year range, so it stays correct every future season without editing.
2. Per season: `placement_exact and placement <= 8` = All-Americans (8/weight x 10 weights = 80/season); `placement == 1` = champions (10/season). 400 AAs and 50 champions pooled across the 5-season window.
3. Joins each placed wrestler's name+weight to a real `wrestler_id` via that season's `index_wrestlers.json`, reusing the same `normalize_name()` + apostrophe-canonicalization + last-name/first-initial fallback already proven in `scripts/analysis/flo_preseason_vs_score.py` — then looks up that `wrestler_id`'s `mv_avg` in `mat_value_{year}.json`.
4. p25/p75 via linear-interpolation percentile (same formula as `scripts/analysis/build_rank_score_distributions.py`'s `percentile()`); champion average is a flat mean.

**Rendering (`reports/shared/chart.js`):** the band only ever *extends* a chart's y-axis upward (never downward, never for the champion line) — and only when a wrestler's best qualifying season came within 0.3 DPG of the band's bottom edge (`aa_p25`) but the chart wouldn't otherwise reach that high. If nothing came within 0.3, the axis is left exactly as it would be without the band, and the band simply doesn't render (no forced stretching for wrestlers nowhere close). The champion line is never used to extend the axis at all — it only appears if a chart already reaches it naturally.

**When to re-run:** once per season, after that season's NCAA tournament results (`data/{season}/ncaa-tourney/`) and DPG (`mat_value_{season}.json`) are both finalized — the rolling 5-season window then shifts forward on its own next time the script runs, dropping the oldest season automatically.

---

## NCAA Team Championship Odds (Preseason/In-Season Team Projections)

**Pages:** `index.html` (homepage preview, top 10 + expandable rows), `team_odds.html` (full table, all teams, date picker)
**Data:** `frontend/wrestledata-ui/public/data/team_odds/{season}/{date}.json` + `index.json`

### Why this exists

FloWrestling's own team projection allocates points by rank. That's accurate late in the season but not in September, for two structural reasons: (1) injuries — a #1 seed has to survive a full season before scoring anything (example: Caleb Henson, #1 preseason 2025-26, vanished from the rankings by October, scored 0), and (2) freshmen — most start the season unranked even when they're about to be good (PJ Duke, Jax Forrest). This system quantifies exactly how much error that produces and corrects for it with three layers, applied in order: an empirical rank-to-score distribution that sharpens every month, a program-strength offset, and a per-wrestler track-record modifier for the top of each weight class.

### Pipeline (run in order for a new rankings drop)

1. `scripts/scraping/scrape_flo_preseason_rankings.py` — scrapes FloWrestling's rankings for a season/date, writes `data/{season}/flo-preseason-rankings/{date}.json`
2. `scripts/analysis/build_rank_score_distributions.py` — builds `rank_score_distributions.json` (rerun only when a new tournament year's results are added, not every ranking drop)
3. `scripts/analysis/compute_team_seed_offsets.py` — builds `team_seed_offsets.json` (rerun only when a new tournament year's results are added)
4. `scripts/analysis/compute_individual_modifiers.py` — builds `{rankings_file}_individual_modifiers.json` for this specific rankings drop (rerun every time — ranks change monthly)
5. `scripts/analysis/simulate_team_scores.py --team-offsets ... --individual-modifiers ...` — runs the Monte Carlo simulation
6. `scripts/analysis/publish_team_odds_to_site.py` — copies the latest simulation output into the frontend's public data dir

### 1. Rank-based score distributions

**Script:** `scripts/analysis/build_rank_score_distributions.py`
**Output:** `data/ncaa-tourney-parsed/rank_score_distributions.json`

For each FloWrestling rank (1–33) and each touch-point month (Sep–Feb), pools that rank's own historical NCAA `total_points` across 2023–2026, then blends in the immediate neighbor ranks (rank ± 1), recentered to the target rank's own mean:

```
adjusted_neighbor_points = neighbor_points - mean(neighbor_points) + own_mean
```

This borrows a neighbor's spread (more data → a more stable variance estimate) without importing their different central tendency. All points clipped to [0, 30] — the real NCAA scoring ceiling (4.0 max advancement + 10.0 max bonus + 16.0 max placement).

September only has ~1 year of real touch-point data (n_own=10 vs 40+ every other month) — too thin to trust independently, so it's aliased directly to October's distribution rather than pooled on its own.

### 2. Program-strength offsets

**Script:** `scripts/analysis/compute_team_seed_offsets.py`
**Output:** `data/ncaa-tourney-parsed/team_seed_offsets.json`

Computes each program's historical seed-relative over/underperformance: on average, how many more or fewer points did this program's wrestlers score than the league-wide average wrestler holding the *same seed*, 2023–2026?

```
diff = wrestler_points - league_avg_at_that_seed
raw_offset = mean(diff) across the program's wrestler-seasons
```

Raw averages are shrunk toward 0 via empirical-Bayes weighting, since a single wrestler's tournament result is noisy (σ² ≈ 14) relative to how large real program-level effects actually are (τ² ≈ 0.51, estimated from the well-sampled programs):

```
shrinkage_weight = τ² / (τ² + σ²/n)
offset = shrinkage_weight × raw_offset
```

Even a program with n=39 (the most any program has) only earns ~59% credit for its raw average; a program with n=5 earns as little as 15%. This replaced an earlier hard n≥5 trusted/untrusted cutoff that gave every program above that line full credit regardless of how thin its sample actually was.

**Deliberately not recency-weighted.** A split-half test (2023-24 vs. 2025-26 offset per program) found the two halves barely correlate (r≈0.10) even for programs with fully stable coaching across the whole window — program performance swings substantially year to year in a way that doesn't look like smooth, recency-driven drift. Weighting recent seasons more would discard real data without reducing bias, so the full flat 4-year window is used instead.

### 3. Individual wrestler track-record modifiers

**Script:** `scripts/analysis/compute_individual_modifiers.py`
**Output:** `{rankings_file}_individual_modifiers.json` (one per rankings drop)

Applies to the top 3 ranked wrestlers at each weight only — the only tier this has been validated for. Two wrestlers can share the same current rank but have very different track records (one won it all last year, one took 3rd); this adds real, proven history on top of the generic rank-based projection.

```
resid = wrestler_points - league_avg_at_current_seed        (predicted quantity)
predictor_1yr = prior year's absolute points
predictor_2yr = average of the last 2 years' absolute points (when both exist)
```

Two linear fits (`resid ~ predictor`), one per current-seed tier (1, 2, 3), estimated separately for the 1-year and 2-year predictors from every historical wrestler-to-wrestler year transition (2013–2026):

```
beta = cov(predictor, resid) / var(predictor)
modifier = beta × (this_wrestler's_predictor - mean_predictor_in_that_tier)
```

**Upside-only, by design.** Both `mod_1yr` and `mod_2yr` are floored at 0 before combining:

```
final_modifier = max(mod_1yr, mod_2yr, 0)
```

History is never allowed to *subtract* from the current rank's baseline. A weak prior result is much harder to interpret than a strong one — injury, a graduating senior blocking the lineup, a tough bracket, a weight-class move — and a backtest showed a naive symmetric (both-directions) version actively hurt team-level prediction accuracy for some teams versus the upside-only version, which never underperforms the no-modifier baseline. A simple 2-year *average* can also dilute a strong recent year with a weaker older one; taking the max of two independently-floored modifiers instead means more history can only ever help, never hurt.

**Sequential cap within each weight class.** Rank 1 is never capped (nothing ranks above it). Rank 2's final adjusted value (base + modifier) can never exceed rank 1's; rank 3's can never exceed rank 2's. This approximates isotonic regression — it stops the modifier from ever implying a lower-ranked wrestler is secretly better than the wrestler ranked above them:

```
ceiling = None
for wrestler in [rank1, rank2, rank3]:   # in rank order
    adjusted = base + modifier
    if ceiling is not None:
        adjusted = min(adjusted, ceiling)
    ceiling = adjusted
```

**Validated via backtest** (out-of-sample fit excluding the transition being tested, applied to the 2025-26 season's actual top-10 finishers): team-level mean absolute error dropped from 23.6 (no modifier) → 22.4 (symmetric, both directions) → 22.1 (upside-only). Upside-only matched or beat the no-modifier baseline for 9 of 10 teams; the symmetric version made 2 teams' predictions worse. At the individual level, prior *absolute* points within the same current-seed tier correlates with next season's residual at r≈0.37–0.48 (seeds 1–3 pooled) — much stronger than prior *seed-relative* residual alone (r≈0.10), meaning raw dominance (bonus points, falls, how far they placed) carries real information beyond what the seed number alone captures.

**Explicitly not built:** a team-level version of this same idea (does a *team's* prior-year total predict this year's error?) tested at r≈0.56, but nearly all of that signal came from two programs (Penn State, Oklahoma State) across only 3 usable historical transitions — selecting "top teams" and then finding they beat expectations is close to circular, since they're at the top partly *because* they beat expectations. Shelved as unproven rather than built into the pipeline.

### 4. Monte Carlo team simulation

**Script:** `scripts/analysis/simulate_team_scores.py`
**Output:** `data/ncaa-tourney-parsed/team_score_simulation{_adjusted}_{date}.json`

For each team's 10-man lineup (best-ranked wrestler per weight, or a fallback pool of ranks 25–33 if unranked), runs 10,000 trials: each trial draws one random sample per weight slot from that wrestler's (rank-distribution + team-offset + individual-modifier) points list, sums to a team total, then ranks all teams that trial to record placement.

```
for each trial:
    team_total = Σ random_choice(wrestler_points_list) for each of 10 weight slots
    rank all teams this trial, tally each team's placement
```

Output per team: `min`, `max`, `p5`, `p95`, `expected` (mean), `p_1st`/`p_top3`/`p_top5`/`p_top10`, exact `p_place` odds for 1st–10th, and full `lineup_detail` (each wrestler's rank, individual modifier if any, expected/p5/p95).

**Known simplification:** unranked roster slots all draw from the same generic ranks-25–33 fallback pool regardless of program. A Penn State backup replacing an injured starter likely outscores this generic stand-in — not yet modeled (open item, see Known Gotchas).

### 5. Publishing

**Script:** `scripts/analysis/publish_team_odds_to_site.py`

Copies every `team_score_simulation_adjusted_*.json` found in `data/ncaa-tourney-parsed/` into `frontend/wrestledata-ui/public/data/team_odds/{season}/{date}.json`, and writes an `index.json` listing all available dates (newest first). The static site can't glob a directory, so the frontend fetches this index first to know what dates exist, then fetches each date's file on demand.

---

## NCAA Tournament Tracker

**Page:** `ncaa_live.html`
**Data:** `data/{year}/simulation_replay.json`

### simulation_replay.json structure

```json
{
  "year": 2026,
  "last_updated": "2026-04-12T22:00:43",
  "matches_completed": 640,
  "matches_total": 640,
  "current_projection": { "Penn State": 181.5, ... },
  "pre_tourney_predictions": { "Penn State": 175.0, ... },
  "team_penalties": { "Team Name": -5.0 },
  "wrestlers": {
    "125": {
      "1": {
        "name": "...", "team": "...",
        "actual": 21.0,
        "projected_total": 21.0,
        "initial_projected": 19.44,
        "aa_prob": 1.0,
        "alive": false,
        "seed": 1
      }
    }
  },
  "history": [
    {
      "match_n": 1,
      "round": "PIG",
      "match": {
        "weight": 125, "winner_seed": 1, "loser_seed": 33,
        "winner_name": "...", "loser_name": "...",
        "winner_team": "...", "loser_team": "...",
        "result_type": "MD", "score": "9-2",
        "winner_school_update": 2.5,
        "loser_school_update": -0.5,
        "upsets": false, "bonuses": true
      },
      "projections": { "Team Name": 125.3, ... },
      "moments": [ { "type": "bonus|upset|rank_change", "team": "...", "message": "..." } ]
    }
  ],
  "sorted_matches": [ ... ],
  "moments": [ ... ]
}
```

### Round processing order

```
PIG → R32 → C_PIG → C_R1 → R16 → C_R2 → C_R3 → QF →
C_R4 → C_QF → SF → C_SF → Final → 3rd → 5th → 7th
```

### Bonus points used for tracker display

```python
{ "Dec": 0.0, "MD": 1.0, "TF": 1.5, "Fall": 2.0, "Forfeit": 2.0, "DQ": 2.0, "Inj.": 2.0 }
```

### Live Tracker features

| Tab | Content |
|---|---|
| Team Leaderboard | Rank, team, pre-tourney projection, current projection, Δ, actual points. Expandable per wrestler. |
| Projection History | Plotly.js line chart — top 10 teams, x=match number (0–640), y=projected points. Session markers. |
| Big Moments | Feed: upsets, bonus wins, leaderboard rank changes, USC penalties |
| Wrestler Movers | Top gainers / top losers in projection delta |
| By Weight | Collapsible cards per weight — seed, wrestler, projection, AA% |
| Lazarus Award | Tracks highest-seeded R32 loser who placed 3rd through consolation bracket |

### Generating the replay

```bash
python scripts/ncaa/generate_replay.py --season 2026
```

The replay is also used to build the seed analysis report (`generate_report.py`) and the scoring trends page.

---

## NCAA Bout-Level Play-by-Play (Event Data)

**This was undocumented until 2026-09-11** — found while scoping a possible live win-probability / in-match DPG-added model (analogous to DataGolf's Strokes Gained or nfelo/NFL EPA). Do not confuse this with `simulation_replay.json` above, which only has match-level final results (winner, score, result type) — this is the one source with in-match, timestamped scoring events.

**Location:** `data/{year}/ncaa-tourney/bout_detail/{weight}.json` — one JSON list per weight class per year.

**Coverage: 2021–2026 only, NCAA Championship bouts only.** Not 2012/2013 onward, and not the full match corpus:
- 2020 has no file because there was no NCAA tournament that year (COVID cancellation).
- 2012–2019 have no bout-detail files at all — nobody has run the scraper for those years, and it's unconfirmed whether TrackWrestling's classic bracket viewer even still serves play-by-play that far back. Open question, not a known dead end.
- **3,720 bouts total** across 2021–2026 (10 weights x ~62 bouts/year x 6 years) — this is the NCAA Championship bracket only, not the 10,000+-match corpus that powers DPG generally. That larger corpus has final scores only, no in-match event timeline, and is not useful for a play-by-play model.
- Pigtail rounds (PIG / C_PIG) are permanently absent — TrackWrestling's play-by-play viewer has no page for them at all (not a scraper bug).

**Scraper:** `scripts/scraping/scrape_ncaa_bout_detail.py` (pulls raw play-by-play) → `scripts/ncaa/reconcile_bout_detail.py` (joins against `data/{year}/ncaa-tourney/parsed/matches.json` by weight + wrestler names to attach `round`/`bracket`, writing back onto the same records in place). Both must run in that order; the reconciler requires `matches.json` to already exist for the year.

**Schema** (one object per bout):
```json
{
  "headline": "Luke Lilledahl (Penn State) defeated Mack Mauger (Missouri)",
  "winner": { "name": "...", "team": "...", "score": 11 },
  "loser": { "name": "...", "team": "...", "score": 2 },
  "weight": 125, "bout_number": 1, "match_id": "...",
  "round": "R32", "bracket": "champ",
  "columns": [
    {
      "label": "Period 1 | Choice 1 | Period 2 | Choice 2 | Period 3 | OT...",
      "notes": ["green riding time: 1:42", "3, 36 (3:00)"],
      "events": [
        { "side": "winner|loser", "text": "Escape (1:53)" },
        { "side": "winner|loser", "text": "Takedown 3 (0:47)" },
        { "side": "loser", "text": "Defer" },
        { "side": "winner", "text": "Bottom" }
      ],
      "period_points": { "winner": 4, "loser": 0 }
    }
  ]
}
```

**This is raw, not parsed** at the source — each event is free text with an embedded clock time (e.g. `"Takedown 3 (0:47)"`). It IS parsed downstream now: `scripts/analysis/parse_bout_pbp.py` turns this into clean per-event rows (running score, position, time-remaining, stalling state) — see [Live Win-Probability Model](#live-win-probability-model-lab) below for the full pipeline built on top of it.

**Known gotcha (winner/loser column order):** the two wrestler columns in the underlying play-by-play tables are NOT consistently ordered winner-then-loser — position (left/right) reflects TrackWrestling's own display assignment, not who won. `scrape_ncaa_bout_detail.py` resolves this by matching the "X defeated Y" headline against each column's name, which is already handled in the `winner`/`loser` split above — but any new code parsing `columns[].events[].side` must trust the `side` field, not column position, since `side` was already resolved correctly against the headline at scrape time (it's not raw column order).

### Conference championships (2026-09-11): same source, more data, lower-DPG wrestlers too

The NCAA Championship bracket above is national-qualifier-level talent only. Conference championships run on the identical TrackWrestling Classic viewer and use the same current (post-2023-24, 3-point-takedown) scoring rules, so they extend the same dataset with more bouts and a wider DPG range (unranked/lower-seed wrestlers the NCAA bracket never reaches) — no new scoring-era complication.

**Scraper:** `scripts/scraping/scrape_conference_bout_detail.py` — reuses `scrape_ncaa_bout_detail.py`'s `scrape_tournament()` core unchanged, just a different `tournamentId` and output path (`data/{year}/{conference}-tourney/bout_detail/{weight}.json`). **No round/bracket reconciliation** for these (unlike NCAA) — there's no parsed `matches.json`-equivalent source to join against yet, so bouts save without a `round`/`bracket` field.

**Finding a new conference's tournament ID** (no public listing exists): get a fresh session by GETing `/Login.jsp`, then hit the Events Classic search directly —
```
https://www.trackwrestling.com/Login.jsp?TIM=<ms>&twSessionId=<sid>&tName=<query>&sDate=<mm/dd/yyyy>&eDate=<mm/dd/yyyy>&state=&lastName=&firstName=&teamName=&sfvString=&city=&gbId=&camps=false
```
then read the numeric ID out of the matching result's `eventSelected(ID, 'name', ...)` link. **Confirm the bracket actually has play-by-play before trusting the ID** — a tournament can exist on TrackWrestling with only final scores and no period-by-period detail (worth checking every time, not just once): resolve a couple of real (non-bye) bout numbers via `resolve_match_id()` + `parse_bout_html()` and check `columns` is non-empty, the way `scrape_conference_bout_detail.py`'s module docstring describes.

**Confirmed working, real period-by-period data verified (updated 2026-09-13):**
| Conference | Registered as | 2026 ID | 2025 ID | 2024 ID |
|---|---|---|---|---|
| Big Ten | `big_ten` | 964607132 | 911000132 | 825871132 |
| Big 12 | `big_12` | 974060132 | 900890132 | 848140132 |
| ACC | `acc` | 948555132 | 882841132 | 815457132 |
| MAC | `mac` | 964861132 | 911012132 | 830507132 |
| Pac-12 | `pac_12` | 974263132 | — (doesn't exist) | — (doesn't exist) |
| SoCon | `socon` | — (doesn't exist) | 896232132 | 794933132 |

**Pac-12 and SoCon have real coverage gaps, not missed search terms** — confirmed via a full-year date-range search, not just an untried query:
- Pac-12: only 2026, 2023, and 2018 editions exist on TrackWrestling at all — no 2024 or 2025. Consistent with the conference's 2024 realignment turmoil (most Pac-12 schools left; wrestling-specific membership was in flux). 2026 is the only edition inside our current-scoring-era window.
- SoCon: 2024 and 2025 exist, but a full calendar-year 2026 search turns up nothing under this name — genuinely missing this year, not a naming variant.

**Confirmed absent from TrackWrestling entirely (2026-09-13) — not just an untried search term:** EIWA and Ivy League. These are the same missing tournament, not two — Ivy League schools wrestle their postseason through EIWA in real life, not a separate Ivy-only championship. Skipped; not recoverable from this data source.

---

## Live Win-Probability Model (Lab)

Answers "given the match state right now (score, clock, position, DPG, riding time, stalling), what's the win probability?" for a specific real bout — analogous to an ESPN win-probability chart, or NFL EPA/DataGolf Strokes Gained. **Not the same thing as the xTP engine's "win probability model"** above — that one is pre-match rank+DPG only, this one runs on real in-match play-by-play. Live on the site at `/win_probability.html` (linked from `/lab/index.html`), currently showing the 10 2026 NCAA finals.

### Pipeline, in order

1. **`scripts/analysis/parse_bout_pbp.py`** — parses the raw play-by-play (see "NCAA Bout-Level Play-by-Play" above) into one row per scoring/position event, with running score/position/riding-time/stalling state computed as of that event. Point values and side semantics were calibrated empirically against each bout's own `period_points` totals, not assumed from rules knowledge (100% exact reconciliation across 3,720+ NCAA bouts, then extended to every conference). Writes `data/pbp/events_{tournament}.jsonl`.
   ```
   python scripts/analysis/parse_bout_pbp.py --tournament ncaa
   python scripts/analysis/parse_bout_pbp.py --tournament big_ten
   ```
   (one `events_*.jsonl` per tournament key — `ncaa`, `big_ten`, `big_12`, `acc`, `mac`, `pac_12`, `socon`; `--years` optional, auto-detects otherwise)

2. **`scripts/win_prob/build_training_data.py`** — reads every `events_*.jsonl` found in `data/pbp/` (or `--tournaments` to restrict) and builds `data/pbp/training_rows.csv`: one row per event PER PERSPECTIVE (a mirrored winner-view and loser-view row for every event, so the label isn't trivially "the subject always wins"). Resolves each wrestler's season DPG via `DpgIndex`; **drops the whole bout** (both perspectives) if either wrestler's DPG doesn't resolve — see Known Gotcha #14. As of 2026-09-14: 121,356 rows / 6,292 bouts across all 7 tournaments, 62 bouts dropped for unresolvable DPG.

3. **`scripts/win_prob/fit_baseline_model.py`** — fits `data/pbp/models/baseline_logreg.joblib`, a logistic regression. This is the model actually used everywhere downstream (a gradient-boosted alternative was tried and rejected — see `compute_match_win_prob.py`'s docstring). Prints test-set ROC-AUC/log-loss/Brier and a full calibration table; as of the 2026-09-14 refit (all 7 tournaments, overtime-length bug fixed): test ROC-AUC 0.9547. **Always re-run this after re-running step 2** (new data, a feature change, or a bugfix in how a feature is computed all require a refit — the coefficients are baked into the `.joblib` file, not recomputed live).

4. **`scripts/win_prob/wrestling_clock.py`** — shared period-length/elapsed-time/match-length constants and helpers, imported by both step 3 and step 5. Centralized 2026-09-14 after the same period-boundary bug had to be fixed independently in both files once already — this is the one place period lengths, period order, and the regulation-vs-overtime match-length distinction should ever be defined. If you're touching period/OT logic anywhere in this pipeline, it should import from here, not redefine its own copy.

5. **`scripts/win_prob/compute_match_win_prob.py`** — the core per-bout computation, `compute_trace(df, model, tournament, year, weight, bout_number, subject)`, importable (not just a CLI) so callers don't have to shell out. For one bout: builds the discrete event list (each event's own win probability) AND a densely-resampled trace (every `RESAMPLE_SEC=3` seconds) that reacts continuously to the clock and riding time even between scoring events, not just at them. Applies two rule-based overrides that are NOT model predictions: a bout that ends in overtime gets its final event forced to 100% (sudden victory = match over, not a matter of confidence), and a bout decided by regulation's buzzer with a nonzero lead gets its trace's final point forced to 100% the same way. CLI usage:
   ```
   python scripts/win_prob/compute_match_win_prob.py --tournament ncaa --year 2026 --weight 125 --bout-number 59 --subject "Luke Lilledahl"
   ```

6. **`scripts/win_prob/plot_matches.py`** — local-only lookup + matplotlib batch plotting, for eyeballing a whole slate at once (`--tournament ncaa --year 2026 --round Final`) or one wrestler's matches (`--winner "Name"`). Not part of the site — saves a PNG locally. This is the tool to use for a quick sanity check before trusting a model change; it's what caught the elapsed-time and OT bugs in Known Gotcha #16.

7. **`scripts/win_prob/export_matches_for_site.py`** — the only step that writes into `frontend/`. Reads `MATCH_SETS` (currently just the 2026 NCAA finals) and writes one static JSON per set to `frontend/wrestledata-ui/public/data/win_prob/{key}.json` — per the site's static-architecture rule, the browser never runs the model, it just fetches this. **Re-run this (after re-running steps 2-3 if the model changed) any time you want the site's numbers to reflect a fix** — it's not wired into any automatic rebuild.

### Frontend

`frontend/wrestledata-ui/public/win_probability.html` + `win_probability.js`, styled like the site's other Lab charts (`final_scores.html` is the closest sibling — same `--panel`/`--border`/card conventions). Renders one small-multiple SVG chart per match: a stepped/interpolated probability curve (blue = subject favored, red = trailing), real scoring-event dots, and a **fixed readout row under each chart** (not a floating tooltip — a floating box clips against the card edge near a chart's top/right corner, found 2026-09-13). Hovering or dragging anywhere over a chart's plot area scrubs the whole timeline (not just the tiny dots) and updates the readout: period + clock (time REMAINING in that period, converted from the match-elapsed clock the data ships in), score, a plain-language description of the last event (`"Valencia takes bottom"`, `"Takedown +3 — Vega"`, not the raw action name), and win probability. Adding a new match set to the page means adding it to `export_matches_for_site.py`'s `MATCH_SETS` and re-running that script — the frontend just renders whatever's in the JSON, no code change needed for a new match, only for a new page-level match SET/data file.

### Known limitations (see Known Gotcha #16 for the full history)

- **Riding time inside overtime periods is lower-confidence** than in regulation (Known Gotcha #15) — the reconstruction's 95%+ validated match rate is dominated by regulation-period checkpoints.
- **A 1-point lead in the game's closing seconds is underpredicted relative to the data** (~81% model vs. ~99% empirical) even after the overtime fixes — open, not yet fixed. Don't trust the model's exact number in that specific situation; the buzzer-certainty override only fixes the literal final instant, not the approach to it.
- **DPG resolution failures silently drop whole bouts** from training (Known Gotcha #14) — a real pipeline fragility upstream of this model, not something fixed here.

---

## Official Team Schedule Scraping (Source of Truth)

Scrapes each D1 team's own official athletics schedule page (e.g. `gopsusports.com/sports/wrestling/schedule`) — dual meets and tournaments, with date, home/away/neutral, location, result, TV/streaming info, and a recap link. This is separate from the TrackWrestling match-data pipeline: it's schedule/fixture data (who's meeting whom and when, including unplayed future events), not match results.

Schedule pages split into a handful of known template families by site vendor, confirmed empirically school-by-school (not assumed from one example):
- **Template A** (Penn State-style, `gopsusports.com`): server-rendered plain HTML under `.schedule-event`, no JSON payload or XHR involved at all.
- **Template B** (Nebraska/Iowa-style): server-rendered plain HTML under a different wrapper, `.schedule-event-item` — Nebraska and Iowa aren't even identical to each other under that same wrapper, so field selectors try several known sub-selectors rather than assuming one exact shape.
- **Template C** (Oklahoma State/Ohio State): genuinely embedded structured JSON in a Nuxt/Pinia payload (`pinia.schedule.schedules["schedules-wrestling,"].games`) — the richest source when present (real opponent id/logo, W/L score, TV network name as clean typed fields).
- **Template D** (legacy Sidearm — Cornell, Clarion, Edinboro, Morgan State, Navy, Lock Haven, etc.): prefers each school's plain-text accessibility feed (`/services/schedule_txt.ashx?schedule={id}`, a "Text Format For Braille" link) over parsing the HTML directly — some of these schools render the schedule as a client-side web component with no data in the raw HTML at all, and even schools whose HTML *does* work reliably have this same clean fixed-width-column feed available, so it's used as the primary path for the whole family.

None of these vendor pages print a year on the event card, only "Mon DD" — the year is inferred from the requested season slug (e.g. "2026-27": Aug–Dec → 2026, Jan–Jul → 2027). A season-suffixed URL can also silently 200 with the *wrong* season's already-posted schedule before the requested season goes up (confirmed on Penn State) — guarded by checking the season string embedded in the page's own `<title>` before accepting a page as a match for the requested season.

### Pipeline, in order

1. **`scripts/scraping/scrape_official_schedule.py`** — scrapes one team's schedule page, trying all templates in order against the same fetched HTML and reporting which matched. Output: `mt/data/official_schedules/{team}/{season}.json`.
   ```
   python scripts/scraping/scrape_official_schedule.py --team penn_state \
     --base-url https://gopsusports.com/sports/wrestling/schedule --season 2025-26
   ```

2. **`scripts/scraping/batch_scrape_schedules.py`** — runs step 1 across every current D1 team. Team → schedule base URL is resolved by reusing whatever official-roster URL that team's own roster scrape already recorded (swap trailing `/roster` for `/schedule`); a small number of manual-only schools (Wyoming, Little Rock, George Mason — webarchive/PDF-captured, no scrapeable roster URL on file) have their real domains hardcoded in `MANUAL_SCHOOL_BASE_URLS`. Maintains `mt/data/official_schedules/_status.json` (per-team last success date/season/event count/template, and the most recent check's result) and renders `mt/data/official_schedules/SCHEDULE_STATUS.md` for a human-readable view. Designed to be re-run periodically through the fall as more schools post their schedule — a team that hasn't posted yet just gets its "not yet posted" status refreshed, never loses previously-saved good data.
   ```
   .venv/bin/python scripts/scraping/batch_scrape_schedules.py --season 2026-27
   ```

3. **Coherency gate (built into step 2):** a new scrape is never allowed to silently overwrite a team's saved schedule if it has *fewer* events than the last good pull. A couple of legitimately-cancelled duals is a normal, real change — but it's indistinguishable from inside the scraper alone from a site redesign quietly breaking the parser and losing real events. When events would be dropped, the new scrape is parked as `{season}.pending.json`, the old (last-known-good) file is left as the live one, and the team/diff is recorded in `mt/data/official_schedules/_coherency_flags.json`.

4. **`scripts/scraping/review_schedule_coherency.py`** — walks through each flagged team interactively, showing exactly what was dropped/added, and lets you choose: keep old, accept new, merge both (deduped), or skip for now.
   ```
   .venv/bin/python scripts/scraping/review_schedule_coherency.py
   ```

5. **`scripts/scraping/dedupe_events.py`** — first-pass cross-team event deduplication/reconciliation. Duals are matched pairwise: once each side's raw opponent string resolves to a canonical team slug, a real dual should appear in both teams' own schedules (one says home, the other away) and gets merged into one record, filling gaps from whichever side has richer data. Tournaments are matched N-way by (normalized event name, date) into one record with a participant list. Team-name resolution is deliberately conservative (exact/substring match against the current D1 team list, plus a small explicit alias list) — a genuinely ambiguous abbreviation (e.g. "OSU") isn't resolved automatically and isn't yet handled.
   ```
   .venv/bin/python scripts/scraping/dedupe_events.py
   ```

**Status as of 2026-09-13:** 24 of 79 D1 teams successfully pulled for 2026-27 (added Buffalo, Duke, Little Rock, North Dakota State, SIU Edwardsville, Wisconsin this run); the rest still show `wrong_season_not_posted_yet`. Re-running `batch_scrape_schedules.py` periodically through the fall is expected and safe.

---

## Official Team Roster Scraping (Source of Truth)

Scrapes each D1 team's own official athletics roster page for the current season — class/eligibility year, hometown, high school, and a current-season photo per wrestler, none of which TrackWrestling's match data carries. Explicitly **not** sourced from wrestlestat.com or similar aggregators — every field here is public information the school itself publishes about its own athletes.

Most D1 sites checked so far are Nuxt.js apps embedding roster data as a `<script type="application/json">` payload using Nuxt's devalue-style serialization (a flat array where objects/arrays reference other elements by index) — `scrape_official_roster.py` implements a minimal resolver for that (`resolve_nuxt_payload`) and finds the roster's player list structurally rather than by a fixed container key, since different schools nest it differently. Several more site variants exist beneath that, tried in order as fallbacks: a server-rendered Vue "s-person-card" component (Oklahoma State), and three distinct legacy-Sidearm HTML templates (`.sidearm-roster-list-item`, `.sidearm-roster-player-container`, `.roster-list-item`) each confirmed on different schools with their own field-selector quirks (documented inline in each parser — e.g. `extract_legacy_sidearm_weight()`'s multi-school weight-vs-height disambiguation).

A season-suffixed roster URL can silently redirect back to the bare (current) URL instead of 404ing when that season hasn't been posted yet — `scrape_season()` treats a same-season request that lands back on the bare base URL as `redirected_to_current` (not a real pull) specifically to avoid mislabeling last season's still-live roster as this season's. Confirmed via this pipeline (2026-09-13): several schools' bare roster URL was still serving 2025-26 data when their 2026-27 page wasn't up yet.

Three schools (Wyoming, Little Rock, George Mason) have no live-scrapable roster page at all — none of the fallback parsers ever matched — and their data was captured manually via `.webarchive`/PDF instead (see `ingest_manual_roster_webarchive.py` / `ingest_manual_roster_pdfs.py`). Their saved JSON's `team_roster_url` field is annotated `"... (manual webarchive capture)"` specifically so downstream tooling (both batch scripts below) knows not to treat it as a live-fetchable URL.

### Pipeline

1. **`scripts/scraping/scrape_official_roster.py`** — scrapes one team, one or more seasons. Output: `mt/data/official_rosters/{team}/{season}.json`.
   ```
   python scripts/scraping/scrape_official_roster.py --team penn_state \
     --base-url https://gopsusports.com/sports/wrestling/roster --seasons 2025-26,2024-25,2026-27
   ```

2. **`scripts/scraping/batch_scrape_historical_rosters.py`** — batch driver scoped to the **2012–2019 historical backfill**, one season at a time, resolving each team against that season's own team list (not the current 79-team list — teams come and go over 14 years).
   ```
   .venv/bin/python scripts/scraping/batch_scrape_historical_rosters.py --season 2019
   ```

3. **`scripts/scraping/batch_scrape_current_rosters.py`** — the current-season counterpart, added 2026-09-13. Runs against the current 79-team list (`data/team_lists/ncaa_men/2026/teams.json`), resolving each team's base URL by reusing whatever real (non-manual) `team_roster_url` its own most-recently-scraped season already recorded. Two modes:
   - `--mode missing` (default): only scrapes teams with no file yet for the requested season — cheapest way to fill gaps as more schools post through the fall.
   - `--mode all`: re-checks every team, including ones already on file, to catch roster changes (transfers, corrections, new signees). Never silently overwrites a roster whose player count *dropped* — parks the new pull as `{season}.pending.json` and records the diff in `mt/data/official_rosters/_coherency_flags.json` for manual review (same reasoning as the schedule scraper's coherency gate: a real departure and a broken parser look identical from inside the scraper alone).
   ```
   .venv/bin/python scripts/scraping/batch_scrape_current_rosters.py --mode missing
   .venv/bin/python scripts/scraping/batch_scrape_current_rosters.py --mode all
   ```
   Maintains `mt/data/official_rosters/_status.json` and renders `mt/data/official_rosters/ROSTER_STATUS.md`.

**Status as of 2026-09-13 (first run of the new current-season batch script):** 60 of 79 teams have a 2026-27 roster on file (7 newly added this run: Buffalo, Cal Poly, Campbell, CSU Bakersfield, Harvard, Lock Haven, Navy). Chattanooga and Wisconsin picked up newly-added players on a `--mode all` recheck. Illinois is flagged for review (26 → 25 players, one dropped) — the new pull is parked, not yet accepted. 13 teams haven't posted 2026-27 yet; 5 (California Baptist, Central Michigan, The Citadel, Gardner-Webb, Maryland) have a live page none of the current parsers match — a new template variant, needs manual investigation.

---

## Key Scripts (NCAA / MatSavant Pipeline)

| Script | Purpose |
|---|---|
| `scripts/scraping/scrape_ncaa_tournament.py` | Live scrape of NCAA tournament brackets from TrackWrestling |
| `scripts/ncaa/parse_ncaa_results.py` | Parse TrackWrestling tournament HTML → matches JSON |
| `scripts/ncaa/generate_replay.py` | Build `simulation_replay.json` round-by-round |
| `scripts/ncaa/simulate_tournament.py` | Pre-tournament projection simulation |
| `scripts/ncaa/generate_report.py` | Build seed analysis report data |
| `scripts/ncaa/live_monitor.py` | Watch for new match results and trigger replay rebuild |
| `scripts/ncaa/build_ncaa_seed_model.py` | Historical seed performance model |
| `scripts/scraping/scrape_flo_preseason_rankings.py` | Scrapes a dated FloWrestling rank snapshot to `data/{season}/flo-preseason-rankings/{date}.json` |
| `scripts/rankings/apply_flo_rankings.py` | Overwrites `mt/rankings_data/ncaa_men/{season}/rankings_{weight}.json`'s top ranks with the latest Flo snapshot (see [NCAA Ranking Methodology](#ncaa-ranking-methodology-source-of-truth)) |
| `scripts/rankings/build_seed_placement_rankings.py` | Flo-unavailable-season substitute: top-8 by actual tournament placement, 9+ by committee seed. Currently the *old*, coarser version of the rule — see Known Compliance Gaps below |
| `scripts/rankings/generate_matrix.py` | Builds the internal matrix ranking. Kept for possible future use; **not a valid source for any user-facing rank** |
| `scripts/scraping/scrape_official_schedule.py` | Scrapes one team's official athletics schedule page → `mt/data/official_schedules/{team}/{season}.json`. See [Official Team Schedule Scraping](#official-team-schedule-scraping-source-of-truth) |
| `scripts/scraping/batch_scrape_schedules.py` | Runs the above across every D1 team; maintains status log + coherency flags |
| `scripts/scraping/review_schedule_coherency.py` | Interactively resolves flagged schedule scrapes that dropped events |
| `scripts/scraping/dedupe_events.py` | Cross-team dual/tournament event reconciliation across scraped schedules |
| `scripts/scraping/scrape_official_roster.py` | Scrapes one team's official roster page → `mt/data/official_rosters/{team}/{season}.json`. See [Official Team Roster Scraping](#official-team-roster-scraping-source-of-truth) |
| `scripts/scraping/batch_scrape_historical_rosters.py` | Batch roster scrape for the 2012-2019 historical backfill |
| `scripts/scraping/batch_scrape_current_rosters.py` | Batch roster scrape for the current season (`--mode missing`\|`all`) |
| `scripts/rankings/calculate_elo_ratings.py` | Builds `mt/elo_ratings/ncaa_men/{season}/elo_ratings.json` (`elo_rank`, `matrix_rank`, `hybrid_rank`) |
| `scripts/rankings/build_wrestler_profiles.py` | Writes each wrestler profile's `current_rank` — NCAA branch currently sources this incorrectly, see Known Compliance Gaps |
| `scripts/rankings/hodge_candidates.py` | Builds the Hodge Watch (`data/awards/hodge/{season}/hodge_{season}.json`) from `elo_ratings.json`'s `hybrid_rank_by_weight` + each candidate's wrestler-profile `match_list`. Run after `calculate_elo_ratings.py` + `build_wrestler_profiles.py` — see [Rebuild order](#rebuild-order-after-any-ranking-affecting-change) |
| `scripts/mat_value/compute_mat_value.py` | DPG for a single wrestler (CLI) |
| `scripts/mat_value/compute_all_mat_values.py` | Batch DPG for all wrestlers, builds leaderboards |
| `scripts/bonus/compute_top33_bonus.py` | Top-33 bonus EV for a single wrestler |
| `scripts/bonus/compute_all_top33_bonus.py` | Batch bonus EV, writes to wrestler profiles |
| `xtp/engine/engine.py` | Main xTP engine (pre-tournament + live) |
| `scripts/xtp/run_team_xtp.py` | Run team xTP projections |
| `scripts/xtp/run_weight_xtp.py` | Run weight-class-level xTP projections |
| `scripts/xtp/run_regional_xtp.py` | Regional xTP projections |
| `scripts/generate_search_index.py` | Builds `search_index.js` (Fuse.js data, ~6MB) — run: `-league ncaa -season 2026` |
| `scripts/build_simple_leaderboards.py` | Builds stat leaderboard JSON (wins, pins, techs, majors) |
| `scripts/wrestlestat_ingest.py` | Supplemental ingestion from WrestleStat (fills gaps in TrackWrestling data) |
| `scripts/ncaa/lazarus_award.py` | Identifies and tracks Lazarus Award candidates |
| `scripts/scraping/scrape_flo_preseason_rankings.py` | Scrapes FloWrestling preseason/in-season rank snapshots |
| `scripts/analysis/build_rank_score_distributions.py` | Builds rank→score empirical distributions for team projections |
| `scripts/analysis/compute_team_seed_offsets.py` | Builds program-strength offsets (shrunk seed-relative over/underperformance) |
| `scripts/analysis/compute_individual_modifiers.py` | Builds upside-only track-record modifiers for top-3-ranked wrestlers |
| `scripts/analysis/simulate_team_scores.py` | Monte Carlo team championship odds simulation |
| `scripts/analysis/publish_team_odds_to_site.py` | Publishes team odds simulation output to the frontend data dir |
| `scripts/reports/build_transfer_dpg_report.py` | Builds one team's transfer-window report JSON; shared base module the other `scripts/reports/` scripts import |
| `scripts/reports/build_wrestler_view.py` | Builds one chart-ready JSON per career-linked wrestler (backfill or `--season`-scoped); also rebuilds `wrestler_index.json`, the reports hub's name-search index |
| `scripts/reports/build_team_roster_view.py` | Builds one team+season roster JSON by reading already-built `build_wrestler_view.py` output |
| `scripts/reports/build_aa_dpg_band.py` | Builds the AA DPG range band + champion line shown on every report chart — see [AA DPG Range](#5-aa-dpg-range-reports-pages-only) |
| `scripts/generate_matsavant_sitemap.py` | Regenerates `frontend/wrestledata-ui/public/sitemap.xml` — see SEO Setup below. Re-run after any wrestler/team profile rebuild or new Note |
| `scripts/reports/build_all_transfer_dpg_reports.py` | Batch-precomputes every team x season Transfer DPG report (79 teams x 15 seasons = 1,185 files) so the report page never needs a visitor to run a script manually. Re-run once a new season's data lands |
| `scripts/analysis/parse_bout_pbp.py` | Parses raw NCAA/conference bout play-by-play into per-event rows — step 1 of the [Live Win-Probability Model](#live-win-probability-model-lab) |
| `scripts/win_prob/build_training_data.py` | Builds `data/pbp/training_rows.csv` from every parsed `events_*.jsonl` — step 2 |
| `scripts/win_prob/fit_baseline_model.py` | Fits the win-probability logistic regression, `data/pbp/models/baseline_logreg.joblib` — step 3, re-run after any change to steps 1-2 |
| `scripts/win_prob/wrestling_clock.py` | Shared period-length/elapsed-time constants for the win-probability pipeline — no CLI, imported by steps 3 and 5 |
| `scripts/win_prob/compute_match_win_prob.py` | Computes one bout's win-probability trace (CLI + importable `compute_trace()`) — step 5 |
| `scripts/win_prob/plot_matches.py` | Local matplotlib lookup/batch-plot for eyeballing a slate of matches before trusting a model change — step 6, not part of the site |
| `scripts/win_prob/export_matches_for_site.py` | Writes the win-probability Lab page's static JSON data — step 7, the only step that touches `frontend/` |

---

## SEO Setup (MatSavant)

- **Canonical host is `www.matsavant.com`, not the apex**: `https://matsavant.com` is a 301 redirect to `https://www.matsavant.com` (Netlify domain config, outside this repo). Every URL in `sitemap.xml`, and the `Sitemap:` line in `robots.txt`, must use `www.matsavant.com` — pointing them at the apex caused Search Console's first sitemap fetch to fail ("Couldn't fetch"), since the registered property and the sitemap's URLs were on different hosts. `scripts/generate_matsavant_sitemap.py`'s `BASE_URL` is set to the `www` host for this reason; don't change it back without also fixing the Search Console property.
- **Google Search Console**: set up 2026-09 as a URL-prefix property for `https://www.matsavant.com` (the canonical host, not the apex), verified via HTML file — same method as KentuckyMat. Verification file: `frontend/wrestledata-ui/public/googled965ce574f260313.html`. Don't delete it; Google re-checks it periodically.
- **`robots.txt`**: `frontend/wrestledata-ui/public/robots.txt`, points at the `www` sitemap URL.
- **`sitemap.xml`**: generated by `scripts/generate_matsavant_sitemap.py`. Covers every static page, every Note (from `data/notes/notes.json`), every wrestler profile across every backfilled season 2012–2026 (~40,400 URLs — each season's `wrestler_id` is its own crawlable entry point into that person's career page via the `season_summary` switcher, not a duplicate), and all 86 current team profiles. ~40,550 URLs total, safely under the single-sitemap 50,000-URL cap — no sitemap index needed. Re-run the script (and redeploy) whenever wrestler/team profiles are rebuilt or a Note is published; it isn't wired into the weekly pipeline automatically.
- **Analytics**: separate from Search Console — see `analytics.js` (GA4, measurement ID `G-DRHRDZF2DV`) and the pageview-firing logic in `header.js`.

---

## Metric Summary Table

| Metric | What it measures | Scale | Location in UI |
|---|---|---|---|
| **DPG** | Per-match value vs opponent expectation; season average | ±0 to ±5 typically | Wrestler profile hero, leaderboard, team page |
| **SI+** | Adjusted scoring rate vs opponent quality | 100 = avg; 110 = 1 SD above | Wrestler profile skill section |
| **DF+** | Adjusted defensive rate vs opponent quality | 100 = avg; 110 = 1 SD above | Wrestler profile skill section |
| **PE+** | Bonus point propensity vs opponent quality | 100 = avg; 110 = 1 SD above | Wrestler profile skill section |
| **DI+** | Composite dominance: 40% SI+ / 45% DF+ / 15% PE+ | 100 = avg | Wrestler profile skill section |
| **Bonus EV** | Expected bonus pts per win vs top-33 opponents | 0.0–2.0 | Internal; feeds xTP |
| **xTP** | Expected NCAA tournament team points | 0–50+ per wrestler | Team leaderboard, homepage |
| **AA Prob** | Probability of placing top 8 at NCAAs | 0%–100% | Live tracker per-wrestler |

---

## Known Gotchas

1. **DPG display name vs script name**: The UI everywhere calls this "DPG." The scripts and JSON field names call it `mv` or `mat_value`. They are the same thing.

2. **PE+ vs APR+**: Older UI labels and code comments may say `APR+`. The canonical spec (`docs/aps_apg_di_v2_spec.md`) defines this as `PE+`. The meaning is the same: pin/escape rate index.

3. **Forfeits excluded**: All forfeit and medical forfeit matches are stripped before any calculation (DPG, SI+, xTP, etc.). They do count toward official win/loss records.

4. **Skill indices are non-fall only**: SI+, DF+, PE+ are computed only on non-fall matches (decisions, MDs, TFs). Falls end early and skew per-minute rates.

5. **simulation_replay.json covers all years**: The same file structure is used for historical replays (2014–2025) and the live current year (2026). The `history` array is the full match-by-match log; the `current_projection` and `wrestlers` objects reflect the final state.

6. **WrestleStat is supplemental only**: `wrestlestat_ingest.py` adds matches that TrackWrestling missed, but TrackWrestling is always the authoritative source on conflicts.

7. **Team penalties**: Some teams receive USC (unsportsmanlike conduct) point deductions. These are tracked in `team_penalties` in the replay JSON and shown in the Big Moments feed.

8. **xTP engine constants are tunable**: `WIN_PROB_ALPHA`, `WIN_PROB_BETA`, bonus multipliers, and `BONUS_CAP` are all defined at the top of their respective scripts and can be adjusted between seasons.

9. **Individual track-record modifiers only cover ranks 1-3**: this is the only tier the backtest has validated (r≈0.37-0.48). Applying the same regression to lower ranks (or generalizing to a team-level version) has *not* been validated — a team-level attempt tested well in aggregate (r≈0.56) but nearly all of it traced back to just two programs (Penn State, Oklahoma State) over 3 usable years, and was shelved rather than shipped. See "NCAA Team Championship Odds" section above.

10. **`compute_individual_modifiers.py` output is per-rankings-file, not persistent**: unlike `team_seed_offsets.json` (rebuilt only when new tournament results land), the individual modifiers file must be regenerated every time a new FloWrestling rankings snapshot is scraped, since it depends on that snapshot's current ranks. It's written alongside the rankings file it was computed from (`{rankings_file}_individual_modifiers.json`), not to a fixed path.

11. **Unranked-wrestler fallback is still generic (open item)**: team simulation slots with no ranked wrestler all draw from the same pooled ranks-25-33 distribution regardless of program. Stratifying this by program strength (a blue-blood program's unranked backup likely outscores a mid-major's) is a known gap, not yet built.

12. **Conference membership is not captured by the current team-list scrape (open item, discovered 2026-09-10)**: `data/team_lists/ncaa_men/{season}/teams.json` (built by `scrape_ncaa_d1_teams.py`) and every downstream team file (`frontend/wrestledata-ui/public/data/teams/*.json`, `team_metrics.json`) carry a `conference` field, but it's `null` for 78 of 79 D1 teams — the live scraper never populates it. The last scrape that *did* capture it is the obsolete `mt/data/_obsolete/2026/*.json` roster dump, where each wrestler entry's `division` field is a comma-joined list like `"DI - Big Ten, DI - Big Ten, ..."`; taking the most common `DI - {conference}` token per team recovers all 79 teams across 9 conferences (Big Ten, Big 12, ACC, EIWA, MAC, SoCon, Ivy League, Pac-12, Independent). That backfill is saved at `frontend/wrestledata-ui/public/data/team_conferences.json` (`{team_slug: conference}`, plus a `source`/`note` explaining it's an interim backfill). **This is a stopgap, not a pipeline fix** — it reflects the 2025-26 season's rosters, so any transfer/realignment since won't show. Fix properly: have `scrape_ncaa_d1_teams.py` capture conference directly when it scrapes the 2027 team list (early 2027 season), and stop reading from `team_conferences.json`.

13. **Transfer DPG report is single-season only, by design (2026-09-11)**: `build_transfer_dpg_report.py` still accepts `--start-year`/`--end-year` as separate flags, but the frontend (`reports/transfers/index.html`, and the Transfer Window tab in `reports/index.html`) only ever calls it with the same year for both — a multi-year range ("all transfers touching this team across 2023-2026") was tried and dropped as not a useful stat, and the full team x year-range combinatorial space (~120 pairs/team) was impractical to precompute. Every team x season (79 x 15 = 1,185 files) IS fully precomputed via `build_all_transfer_dpg_reports.py`, so the page never shows "no report generated, go run this script" the way it used to. Output files are still named `{team}_{start}_{end}.json` (e.g. `oklahoma_state_2025_2025.json`) — the frontend constructs that filename from a single "Season" dropdown value used for both halves.

14. **A single unresolvable opponent silently kills a wrestler's whole-season DPG (open item, discovered 2026-09-12)**: `compute_all_mat_values.py` → `compute_mv_for_wrestler()` requires *every* opponent across *all* of a wrestler's matches that season (via `get_opponent_info()`) to be resolvable in that season's rankings files — if even one opponent isn't found in any weight class's rankings, it raises and the entire wrestler is dropped from `mat_value_{season}.json` (and never gets a `mat_value` field written to their profile), not just that one match excluded. Confirmed case: Ethen Miller (Virginia Tech, 2026, wrestler_id `34941289132`) is missing 2026 DPG entirely — not a career-linking bug (his `season_summary` correctly threads all 5 seasons across his Maryland→Virginia Tech transfer) and not missing match data (34 real matches load fine) — the actual cause is one Midlands Championships opponent, Jaden Pepe (Harvard, wrestler_id `34937336132`), who isn't in any 2026 weight-class rankings file at all (likely just unranked at the time of that snapshot). This is a general pipeline fragility, not specific to transfers — any wrestler whose matches include an unranked/unresolvable opponent (common at out-of-conference opens like Midlands) can silently lose their entire season's DPG with no error surfaced downstream. Not fixed yet — the fix would be to skip the single unresolvable match/opponent rather than aborting the whole wrestler, in `compute_mv_for_wrestler`'s per-match opponent-resolution loop (`scripts/mat_value/compute_all_mat_values.py`).

15. **Riding time is reconstructed, not read directly, in the win-probability PBP pipeline (2026-09-12)** — `scripts/analysis/parse_bout_pbp.py`'s `parse_bout()` computes cumulative riding time per side (`riding_time_winner_after`/`riding_time_loser_after`) from position transitions: a takedown/reversal starts a control segment, an escape ends it, and a period running out while still in control credits the rest of that period. This is NOT read from the scorekeeper's own `"{color} riding time: M:SS"` notes in the raw bout-detail data, because those notes identify wrestlers by raw display color (green/red) and color is never resolved to winner/loser anywhere in this data (only left/right *columns* are, via the headline match at scrape time — see the winner/loser column-order gotcha above) — resolving it would require re-scraping every already-scraped tournament.
    - **The notes report the NET riding-time advantage** (whichever side is currently ahead, cumulative-minus-cumulative), **not either side's raw individual total** — this was not obvious and cost real debugging time: checking a note's value for set-membership against either side's raw computed total matched only ~52% with a heavy error tail; comparing against `abs(computed_winner - computed_loser)` instead gets 95.6-95.9% matching within 5 seconds (validated independently against both the full NCAA 2021-2026 corpus and Big Ten 2024-2026). This also means the notes can validate the reconstruction without ever needing to resolve which color is which side — the net is the same regardless of who's ahead. See `check_riding_time()`'s docstring.
    - **Two real bugs were found and fixed along the way**, both in `parse_bout()`: (1) a takedown/reversal missing its embedded timestamp (~2.6% of them) used to permanently null out `control_start_remaining`, silently losing every subsequent ride's credit for the rest of the bout — fixed by falling back to the last known clock reading (`last_known_remaining`) and treating the untimed event as instantaneous. (2) Crediting a "ran to the end of the period" bonus to a control segment whose *start* was itself one of those estimated timestamps could overcount by up to the entire remaining period, since the true start could be anywhere in that window — fixed by skipping the period-end credit specifically when the segment's start was estimated (`control_start_estimated` flag), while still crediting normally when a later real event ends the same segment.
    - **OT period lengths in `PERIOD_LENGTH_SEC` reflect the CURRENT rule set only** (SV-1=120s, tiebreakers=30s/30s) and may be wrong for older seasons whose overtime format differed — see the "conference championships" section above for what's confirmed vs. still open about exactly when that changed. Riding time reconstruction inside OT periods should be treated as lower-confidence than in regulation until that's resolved; the 95%+ match rate above is dominated by regulation-period checkpoints, which are the overwhelming majority of the notes.
    - Also tracked per side: `stalling_warned_{winner,loser}_after` (boolean — has this wrestler been called for stalling at all yet, not the exact count; a first call forces a real strategic shift independent of whether it ever becomes a penalty) and `flip_winner`/`choice_N_chooser`/`choice_N_choice`/`choice_N_deferred` (who won the pre-match disk flip and what each choice point resolved to — see `extract_choices()`). Neither of these encodes any assumption about which value helps or hurts; they're passed through as plain state for a model to learn from.

16. **Every NCAA overtime period is sudden-victory — treating it as a fixed-length period broke the win-probability model twice over (fixed 2026-09-14)**: `scripts/win_prob/wrestling_clock.py` now centralizes the wrestling-clock constants that used to be duplicated (and once already diverged) between `fit_baseline_model.py` and `compute_match_win_prob.py`. Two bugs, both from the same wrong assumption ("OT1/OT2/OT3 run their nominal length like a regulation period"):
    - **`match_length_sec` for an OT-decided bout was computed as the END of that overtime period's nominal length** (even reaching into a next tiebreaker period that never happened), instead of the elapsed time of the bout's own actual final event. Since `match_time_fraction_remaining` (the crunch-time feature) is defined relative to `match_length_sec`, this meant a tied score entering sudden-victory OT looked like it had ~20% of the "match" still ahead of it, when in reality the match was seconds from certainly ending — silencing the crunch-time effect exactly where it should have been strongest. Found on the 149lb 2026 final (Valencia/Van Ness): the model held Valencia at ~80% favorite basically flat through a genuinely back-and-forth match into OT, roughly its pre-match DPG-based read, when it should have been pulled toward a toss-up by the tied, dwindling-time state. Fixed via `bout_match_length_sec()`: regulation periods keep the nominal period-end length (decided at the buzzer if not sooner); an OT-decided bout's length is its own last event's elapsed time. Refit after the fix — metrics didn't move (test ROC-AUC 0.9547 vs 0.9548), confirming this was a correctness fix, not a modeling change, and empirically **DPG still matters even once a match has proven itself close**: querying the fixed training data directly, a DPG favorite wins a tied sudden-victory OT 64.5% of the time (n=434 tied-OT rows) — nowhere near a 50/50 coin flip, so "the match is close, it must be converging to a toss-up" is not what the data actually shows; the old ~80% READING was still too high, but the corrected model's ~64% for this case is a real, checked finding, not an artifact.
    - **The win probability AT the deciding OT event was still a model prediction (usually 70-95%), not 100%**, even though the match is definitionally over the instant that event happens (sudden victory = first score wins, no more clock exists after it). `compute_match_win_prob.py` now force-sets `win_prob = 1.0` on a bout's final event when it ends in overtime — a rule-based override, not something asked of the statistical model. The equivalent regulation-buzzer case (clock hits zero with a nonzero lead) gets the same override on the trace's final point.
    - **A related, DIFFERENT calibration gap was found and left OPEN**: even after both fixes above, a lead of exactly 1 point in the last few seconds of regulation is still underpredicted relative to the data — checking `fit_baseline_model.load_data()`'s output directly, period 3 with <3% of match time left shows a **98.9% empirical win rate for a 1-point lead**, statistically indistinguishable from a 2-point lead (98.8%) or 3-point lead (99.7%) at that same point — but the fitted model (with DPG held equal) predicts only ~81-82% for 1 point there vs. ~94-99% for 2-3 points, a real, reproducible gap specific to narrow leads that the cubic `score_diff x match_time_fraction_remaining` polynomial terms don't close. Found on the 184lb 2026 final (McEnelly, up 4-3 with 3 seconds left): the model dropped to ~72% right as the clock was about to run out. The buzzer-certainty override above fixes the trace's literal final point but not the model's approach to it in the closing seconds. Suspected cause: the four polynomial terms (`score_diff`, and its product with `match_time_fraction_remaining`/`_sq`/`_cube`) are highly collinear by construction, which can produce large, partially-cancelling coefficients that don't generalize smoothly to every discrete score_diff value — not yet fixed; likely needs either score_diff-bucketed interaction terms or a revisit of the earlier gradient-boosted attempt (rejected for a different failure mode — see `compute_match_win_prob.py`'s docstring) with the DPG-tail overfitting specifically addressed rather than abandoning nonlinearity altogether.
    - The x-axis period-label rendering (`win_probability.js`) had a matching bug: filtering periods by `start <= matchEnd` rendered a zero-width "OT" label on every non-OT match (since OT1's nominal start exactly equals a regulation-decided match's length) and a phantom "TB" on an OT-decided match. Fixed to strict `<`.

---

## Technology Stack

| Layer | Technology |
|---|---|
| Frontend | Vanilla HTML/CSS/JavaScript (no framework) |
| Interactive charts | Plotly.js (tournament projection history) |
| Static charts | Custom SVG (DPG match impact timeline) |
| Search | Fuse.js (fuzzy matching on pre-built index) |
| Data format | Static JSON, served from `/data/` |
| Data pipeline | Python 3, local — no cloud dependencies at build time |
| Hosting | Netlify (static site) |

---

## What Is Legacy / Inactive (MatSavant Side)

- `docs/db_schema.md` — DynamoDB schema from the old backend era; fully replaced by static JSON
- `README.md` in project root — references old DynamoDB + Vite dev setup; stale
- `scripts/link_and_upload_season*.py` (multiple variants) — legacy upload scripts for DynamoDB; not used
- `scripts/clear_dynamodb_tables.py`, `scripts/upload_teams_to_dynamodb.py` — legacy
- `wrestlerank-json/` — standalone ranking experiment; not integrated
- `scripts/win_prob/fit_gbm_model.py` — gradient-boosted alternative to the win-probability logistic regression, tried and rejected 2026-09-13 (let extreme DPG values swamp the score-state features — see `compute_match_win_prob.py`'s docstring). Not used by anything; kept only as a record of what was tried.
- `scripts/win_prob/generate_viz_data.py` — one-off data prep for an early single-match Artifact exploration, superseded by `export_matches_for_site.py` + the real Lab page. Not part of the pipeline.
