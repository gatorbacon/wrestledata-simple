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
| Wrestler Profile | `wrestler.html` | Per-wrestler DPG, skill indices, match impact timeline, full match history. **Career view** (2026-10-01): a Career row under the season table / Career chip on phones (2+ seasons only) switches everything below to career numbers, computed in the browser by `buildCareerProfile()` in `app.js` from the per-season profiles the season table already fetches (no extra file). Record / vs Top 10 / pins / techs / majors = sums; bonus % = (pins+techs+majors)/wins; DPG = Σ(season DPG × `mat_value.matches`)/Σ matches (same counts as the season rows); SI+/DF+/APR+ = match-weighted season values (labelled); no national percentile for a career; trajectory chart joins the seasons with a divider + year label; match list = newest season first with a divider per season. **Default view** (`pickInitialView()`): `?view=career` / `?view=season` win; otherwise a retired wrestler (latest season before the site's current season) opened at his latest season → Career, everyone else → the linked season. Season-scoped lists link with `&view=season` (match-history opponents, team rosters, DPG / simple leaderboards, Hodge, freshman, AA odds). Desktop header shows a one-line career summary under the season line (`renderCareerHeaderLine()`) |
| NCAA Live Tracker | `ncaa_live.html` | Tournament bracket replay — team leaderboard, projection history chart, big moments feed, by-weight cards, Lazarus Award |
| Seed Analysis | `ncaa_report.html` | Historical seeding vs. performance report |
| Scoring Trends | `ncaa_scoring_trends.html` | Bonus and scoring pattern analysis across rounds/years |
| Team Leaderboard | `ncaa_team_leaderboard.html` | xTP-ranked team table |
| Team Analysis | `ncaa_team_report.html` | Per-team deep-dive with dual meet stats |
| Conference Analysis | `ncaa_conf_analysis.html` | Conference-level aggregated stats |
| Takedowns & Team Points | `ncaa_takedowns.html` | Scatter of every NCAA entrant since 2015: takedown share vs. team points. Rebuild steps: "NCAA Takedowns & Team Points page" below |
| Career Takedowns | `ncaa_career_takedowns.html` | Scatter of every wrestler with 5+ NCAA + conference-tournament matches: career takedown share vs. career win %. Rebuild steps: "NCAA Career Takedowns page" below |
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

- Clicking **Rankings** in the header only opens the menu (dropdown headers are buttons, and there is no hover menu, by design). Every dropdown therefore costs one extra click, so don't turn a plain link (Wrestlers, Teams) into a dropdown for a single new page (TJ, 2026-10-01).
- Page title stays `Rankings` / `2027 Rankings` (season year). Do not call it Board.
- **Matrix** is hidden on mobile (menu row omitted or routed to By weight).
- Do not add a separate "DPG rankings" clone of By weight. DPG is a column + sort on By weight.
- If a real DPG *metric home* is built later (definition + all-weights list + field/beeswarm), it may return under Rankings as `DPG`. That page must not be another top-33 photo table.

#### Wrestlers

Landing page, not a dropdown.

- Search first.
- Weight pills: All · 125 · 133 · 141 · 149 · 157 · 165 · 174 · 184 · 197 · 285.
- **Spotlight · season DPG**: All = top 3 per weight; one weight = top 8. Names link to profiles.
- **Compare two wrestlers** link under the search (to `/tools/compare.html`). This is the menu-reachable way into Compare; it is not in the header menu (see the click-cost rule under Rankings).
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

- Clicking **Field Notes** in the header opens the menu; Field Notes (`/notes`) is its first row.
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
| InterMat rank snapshots — **comparison only, NOT wired into `current_rank`** | `data/{season}/intermat-preseason-rankings/*.json`, one file per scrape date (`YYYY-MM-DD.json`); a `{date}_matched.json` companion adds resolved `wrestler_id`s | Started 2026-09-18 (2026-27 season / tourney_year 2027 only) to track InterMat's editorial rankings alongside Flo's for comparison over the season — it does **not** feed `apply_flo_rankings.py` or any ranking-methodology tier above; Flo remains the sole live-rankings source of truth. Unlike Flo, InterMat publishes no dated archive — one URL always shows the *current* live rankings for a season (all 10 weights server-rendered in one static page load, no JS needed), so there's no site-side signal for "what's new since last time." `scrape_intermat_rankings.py` (season → URL slug lookup in its `SEASONS` dict — InterMat's slug, e.g. `ncaa-di-r78`, is an opaque id with no formula, so add a new entry by hand each fall) handles this itself: every run re-scrapes the live page but diffs it against the most recently archived snapshot's `weights` dict and only writes a new file (stamped with today's date) when something actually changed (a rank moved, a record updated, a wrestler entered/dropped) — safe to run as often as you like (e.g. daily), never rewrites a prior date's file, `--force` bypasses the diff. Each ranked entry carries `rank`/`name`/`school` (same shape as Flo's) plus free bonus columns InterMat exposes (`class`, `conference`, `record`). Matched to tracked `wrestler_id`s by `scripts/rankings/correlate_intermat_rankings.py`, reusing Flo's matching approach (exact name → last-name+initial → adjacent-weight → interactive prompt) but with its own alias file (`mt/intermat_name_aliases.json`) since InterMat's spellings don't always match Flo's the same way; it only acts on a snapshot that doesn't have a `_matched.json` companion yet, so it's cheap/safe to chain right after every scrape. **Two independent consumers as of 2026-09-18** (see "Multiple ranking sources" below for the first, "InterMat rank on the P4P/Rankings page" further below for the second) — each does its own name→wrestler_id resolution rather than sharing one, since one needs the CURRENT season's own roster/rankings pipeline (not available preseason) and the other reuses LAST season's completed index (already available preseason); don't assume they produce identical wrestler_id coverage. |
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

**Pages:** `index.html` (homepage preview, top 10 + expandable rows — FloWrestling only, no source toggle), `team_odds.html` (full table, all teams, date picker + a FloWrestling/InterMat source tab added 2026-09-18), `leaderboards/xtp/teams.html` ("Team Race" — reads the exact same `/data/team_odds/...` feed as `team_odds.html`, see its own module comment; also got the FloWrestling/InterMat source tab, added same day). "Team Race" is reachable from the top nav (Rankings dropdown); `team_odds.html` is not in the nav at all, only linked from the homepage's "NCAA Team Championship Odds" section — worth knowing since it means most traffic to this data lands on "Team Race" first.
**Data:** `frontend/wrestledata-ui/public/data/team_odds/{season}/{date}.json` + `index.json` (FloWrestling); `frontend/wrestledata-ui/public/data/team_odds/{season}/{source_slug}/{date}.json` + `{source_slug}/index.json` for any other source (currently just `intermat/`)

### Multiple ranking sources (added 2026-09-18)

This pipeline can simulate from either FloWrestling's or InterMat's rankings (see [InterMat rank snapshots](#where-each-raw-source-lives) — both scrape to the same `{rank, name, school}`-per-weight shape). `simulate_team_scores.py` derives a `source_slug` from the rankings file's own `"source"` field (`SOURCE_SLUGS` dict: `"FloWrestling" -> "flo"`, `"InterMat" -> "intermat"`) and bakes it into the output filename (`team_score_simulation{_adjusted}_{slug}_{date}.json`) so two sources landing on the same calendar date never collide/overwrite each other. `publish_team_odds_to_site.py` reads that slug back out of the filename (`SOURCE_SUBDIR` dict) and publishes Flo at the season root (unchanged, for backward compatibility — it was the only source before InterMat) and every other source into its own `{season}/{slug}/` subfolder with its own `index.json`. Both consuming pages use the identical pattern (`team_odds.js`'s `TO_SOURCES` array; `leaderboards/xtp/teams.js`'s `TR_SOURCES` array) to fetch whichever source's index/date the user has selected via their own source tab; `homepage_team_odds.js` was deliberately left Flo-only/unchanged (no source toggle on the homepage preview). Adding a third source later means: add it to `SOURCE_SLUGS` (simulate) + `SOURCE_SUBDIR` (publish) + `TO_SOURCES`/`TR_SOURCES` (both frontend pages) — small dict/array edits in four places, no structural changes.

### Why this exists

FloWrestling's own team projection allocates points by rank. That's accurate late in the season but not in September, for two structural reasons: (1) injuries — a #1 seed has to survive a full season before scoring anything (example: Caleb Henson, #1 preseason 2025-26, vanished from the rankings by October, scored 0), and (2) freshmen — most start the season unranked even when they're about to be good (PJ Duke, Jax Forrest). This system quantifies exactly how much error that produces and corrects for it with three layers, applied in order: an empirical rank-to-score distribution that sharpens every month, a program-strength offset, and a per-wrestler track-record modifier for the top of each weight class.

### Pipeline (run in order for a new rankings drop — repeat steps 1/4/5 per source)

1. `scripts/scraping/scrape_flo_preseason_rankings.py` (or `scripts/scraping/scrape_intermat_rankings.py`) — scrapes rankings for a season/date, writes `data/{season}/flo-preseason-rankings/{date}.json` (or `intermat-preseason-rankings/{date}.json`)
2. `scripts/analysis/build_rank_score_distributions.py` — builds `rank_score_distributions.json` (rerun only when a new tournament year's results are added, not every ranking drop; source-agnostic)
3. `scripts/analysis/compute_team_seed_offsets.py` — builds `team_seed_offsets.json` (rerun only when a new tournament year's results are added; source-agnostic)
4. `scripts/analysis/compute_individual_modifiers.py --rankings-file <flo or intermat file>` — builds `{rankings_file}_individual_modifiers.json` for this specific rankings drop (rerun every time — ranks change monthly)
5. `scripts/analysis/simulate_team_scores.py --rankings-file <same file> --team-offsets ... --individual-modifiers ...` — runs the Monte Carlo simulation, tags its own output with that file's source slug (see above)
6. `scripts/analysis/publish_team_odds_to_site.py` — copies every simulation output found (any source) into the frontend's public data dir, sorted into the right source's subfolder

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
**Output:** `data/ncaa-tourney-parsed/team_score_simulation{_adjusted}_{source_slug}_{date}.json`

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

Copies every `team_score_simulation_adjusted_{slug}_*.json` found in `data/ncaa-tourney-parsed/` into `frontend/wrestledata-ui/public/data/team_odds/{season}/{date}.json` (Flo) or `.../{season}/{slug}/{date}.json` (any other source), and writes each source's own `index.json` listing its available dates (newest first). The static site can't glob a directory, so the frontend fetches the relevant source's index first to know what dates exist, then fetches each date's file on demand.

---

## Compare Wrestlers Tool (added 2026-09-28)

`/tools/compare.html`. **Entry points (2026-10-01):** a **Compare ⇄** pill on every wrestler profile (desktop chip row; on mobile, the right side of the identity row) opens it with that wrestler filled in as `a=` and the cursor already in the second box; a "Compare two wrestlers" link under the search on the Wrestlers page; the Tools page card. Deliberately not in the header menu. A future team compare / dual preview should follow the same pattern (team profile + Teams page), not a menu row.

What it does: pick any two wrestlers, see every head-to-head bout and each wrestler's results against the opponents they share, across whole careers, with a season filter. Ported from KentuckyMat's compare page; the comparison logic is the same `compare_core.js` (copied unchanged to `frontend/wrestledata-ui/public/compare_core.js`; opponent-matching rules are in root `CLAUDE.md` → "Compare page"). `tools/compare.js` is the MatSavant UI and data loading. URL: `/tools/compare.html?a={wrestler_id}&b={wrestler_id}[&season=YYYY]` (any season's id of a wrestler works).

**Data source:** NCAA has no frontend career files, and profile `match_list` rows carry `opponent_career_id = null`. So the page loads **`data/careers/career_seasons.json`** (`{"careers": {"<career number>": {"<season>": "<wrestler_id>"}}}`, ~890 KB raw / ~180 KB gzipped, only fetched on this page), built by `scripts/reports/build_career_seasons.py` from the backend career links in `data/careers/ncaa_men/`. The page inverts it to wrestler_id → (career, season) and uses it to (1) find every season of a picked wrestler and fetch those `data/wrestlers/{season}/by_id/{id}.json` profiles, and (2) set each match's `opponent_career_id`, so an opponent faced in two seasons (even on two teams, e.g. Cameron Amine Michigan 2024 → Oklahoma State 2025) is one common opponent. Opponents not in any career fall back to name+team matching. A wrestler not in the file falls back to its own profile's `season_summary`. Career W-L is the sum of each season profile's `record.overall`.

**Keep it fresh:** the script only writes season ids whose profile is **committed** (`git ls-files`), so it never points at an undeployed file. Re-run it after career linking or after a new season's profiles are committed: `.venv/bin/python scripts/reports/build_career_seasons.py`. The picker uses the header search's ranking (match tier → champion/AA/active `priority` → rank).

## InterMat Rank on the P4P / Rankings Page (added 2026-09-18)

**Pages:** `index.html` (homepage P4P widget, "Sort:" dropdown), `rankings.html` (full P4P + per-weight table, "Sort by:" pills) — both share `p4p_rankings.js` and `data/p4p/{season}.json`.

A third sort option, "InterMat Rank," sits alongside the existing "Flo Rank" (`rank`, the row's real position/order in this file — unchanged, still what every other page treats as `current_rank`) and "DPG" (`dpg`). Selecting it re-sorts by each wrestler's `intermat_rank` field (nulls last) and swaps the rank-badge column to show that number instead of Flo's, so the badge always matches what the list is actually ordered by — see `displayRankFor()`/`renderRankBadge()` in `p4p_rankings.js`.

**`intermat_rank` is baked into `data/p4p/{season}.json` by `build_p4p_rankings.py`** (`load_intermat_ranks()`), additively — every existing field/consumer that only reads `rank` is unaffected. Deliberately does **NOT** reuse `correlate_intermat_rankings.py`'s `{date}_matched.json` output (unlike the Team Championship Odds integration above) — that matcher needs the CURRENT season's `mt/rankings_data/ncaa_men/{season}/rankings_{weight}.json` to already exist, which it doesn't preseason (chicken-and-egg: the weekly pipeline hasn't bootstrapped current-season rankings yet). Instead it reuses `build_p4p_rankings.py`'s own existing machinery for joining Flo's entries against **last season's completed wrestler index** (`resolve_wrestler_id()`, extracted from `enrich_entries()` into a shared helper 2026-09-18) — the same 3-tier (name+school → name-only → last-name+initial) resolution already proven for Flo, just applied to InterMat's raw snapshot too. Falls back to `{}` (every row's `intermat_rank` null) if InterMat hasn't been scraped for the season yet — optional overlay, never a hard dependency.

**Known limitation, handled explicitly:** InterMat publishes no pound-for-pound (cross-weight) list, only per-weight rankings (confirmed when `scrape_intermat_rankings.py` was built — no P4P tab exists on their page). So on the P4P tab, `intermat_rank` is really just each wrestler's own single-weight rank, not a genuine cross-weight order — sorting by it there would show many duplicate "#1"s. First pass disabled the InterMat sort option whenever P4P was active, but P4P is the default landing view, so that greyed out InterMat far too often — changed 2026-09-18 (same day) to the opposite direction instead: `applySortChange()` in `p4p_rankings.js` jumps the weight tab to 125 automatically when InterMat Rank is selected while on P4P, and `updateP4PTabAvailability()` disables the **P4P weight tab** (not the sort option) only while InterMat sort is actually active, re-enabling it the moment you switch back to Flo Rank or DPG.

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

**Structural facts found by the WPA build (2026-09-29, `scripts/wpa/`):**
- **A period with no events and no notes has no column at all.** `['Choice 1', 'Period 2', ...]` = a scoreless period 1; `[..., 'Choice 2']` as the last column = period 3 was reached but nothing was scored in it. Which periods a bout reached comes from the `Choice N` columns and the result type, not from which `Period N` columns exist. Same for overtime: a scoreless sudden victory has no `Overtime 1` column before `Choice 3`/`Overtime 2`.
- **Fall time is in the official results, not the play-by-play:** NCAA `parsed/matches.json` puts it in `score` as elapsed match time (`"6:37"`; `"7:37"` = a fall in sudden victory), conference results in `time`. Every fall in both has one.
- **The end-of-regulation riding-time point** is an unclocked `Riding Time` event in the `Period 3` column (occasionally in another column, incl. `Overtime 1` — sudden victory has no riding time, so it's the regulation point). In ~80 conference bouts the scorekeeper didn't log it at all: the official score is exactly one point higher for one side. Some conference tournaments don't have riding time recorded reliably (ACC 2024/2025, Pac-12 2020/2026, MAC 2017, Big 12 2020 — see `data/wpa/reports/state_reconstruction.md`).
- **`Choice 3`** (before tiebreaker periods) can hold one pick or both (`Bottom`, `Bottom`); **position declarations also appear inside period columns** (`Bottom (1:50)`) — restarts after a stoppage, or a period's choice logged in the wrong column.
- **Round labels can be wrong for rematch pairs** (2019 125 bout 61 is labelled `QF` but is the 5th-place fall) — see the rematch gotcha below.

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

## NCAA Takedown-Differential Report (Analysis)

**Script:** `scripts/analysis/td_differential_report.py --start YYYY --end YYYY` → one plain-text report at `data/analysis/td_differential_report_{start}-{end}_ncaa.txt` (override with `--out`). Built 2026-09-19 for 3-year windows (first run: 2024-2026, the 3-point-takedown era; the rule changed for the 2023-24 season, so 2021-2023 and earlier windows use 2-point takedowns — bare `"Takedown"` events, handled automatically). NCAA tournament only (needs `parsed/matches.json`); years without one (2020, cancelled) are skipped.

**What it reports:** win % by takedown differential; first-takedown win % by period; nearfall, exactly-2/3-takedowns, and "gave up the first takedown" scenarios; upsets (winner behind on takedowns) by how the bout ended; what decides bouts that are tied on takedowns (regulation scoring categories, and overtime breakdown), and (section 4) the All-Americans (top-8 finishers, from the Final/3rd/5th/7th bouts) with the most wins in which they scored zero takedowns — everyone tied at the window's maximum is listed, so the table's length varies by window (2024-26: 5 wrestlers at 3 wins; 2021-23 max is 2 wins with many tied). Forfeit/injury/DQ wins are excluded from that count. The other tables are shown for ALL BOUTS and for DECIDED BY POINTS ONLY.

**"Decided by points" definition:** official result type (from `parsed/matches.json`) is `Dec`, `MD`, `TF`, `UTB`, or starts with `SV-`/`TB-`. Excludes `Fall`, `Forfeit`, `Inj.`, `DQ`, and any bout whose official result can't be matched.

**Conference-tournament mode (`--tourney conf`, added 2026-09-19):** pools Big Ten, Big 12, ACC, MAC, Pac-12 and SoCon `bout_detail` (only complete brackets, i.e. ≥9 weight files) into `data/analysis/td_differential_report_{start}-{end}_conf.txt`. Conference `bout_detail` has **no result type, round or placement**, so this mode joins **official results extracted from the team scrapes** — see "Conference-tournament official results" below. Same tables as NCAA (ALL BOUTS + DECIDED BY POINTS ONLY); differences: no All-American table (no placements → replaced by "most no-takedown wins at a single conference tournament", first 15 rows shown), and a conference × year coverage table. Bouts with no official match (2-8% depending on window; worst are ACC 2017, MAC 2017, Big Ten 2015-18 where a team/event is missing from the team scrapes) count in ALL BOUTS but not points-only. If no results files exist at all, the mode falls back to scoreboard-at-finish proxies (winner trailing/tied at the finish = pin/default, a floor: scoreboard alone finds only 14% of NCAA pins; ~9% of "winner leading" bouts are pins) with the caveats printed in the report.

### Custom takedown report (2026-09-19)

`scripts/analysis/td_custom_report/build_report.py` → `data/analysis/td_custom_report.html`. A separate, TJ-specified report (not the comparison page above): (1) bars of % of matches with a non-zero takedown differential, NCAA + conference combined, 4 windows (split in the table view); (2)/(3) infographic "in N matches with a TD edge, the TD winner won X%" for all matches and for points-only; (3b) how often the wrestler BEHIND on takedowns won by official Fall (125 of 12,188 edge matches = 1.0%; 23% of all trailing-wrestler wins; by window and by edge size); (3c) among matches that ended in an official Fall with a TD edge, how often the pinner was the wrestler behind on takedowns (125 of 1,350 = 9.3%; 185 unmatched conference edge matches can't be classified, sensitivity 8.1-10.3%); (3d) NCAA only: share of pins won by the takedown leader by signed seed gap (behind's seed minus ahead's seed, -32..+32). Equal-count buckets (8, with the sparse far-left tail split in two: gaps -32..-11 = 71% of 35 pins, -10..-5 = 78% of 36) plus a logistic fit over all 564 pins (leader gets 84.7% of pins at equal seeds, odds x2.1 per 10 seeds of advantage); (4) win % at +1/+2/+3/+4+ edge by window (NCAA + conference combined, toggle all/points-only); (5) All-Americans with the most no-takedown wins in one NCAA tournament (max is 3, 13 wrestlers); (6) top-10 career no-takedown wins across NCAA + 6 conference tournaments 2015-2026. Unlike `parse_reports.py` this computes straight from bouts (`build_data.py` imports the loaders in `td_differential_report.py`), so numbers can differ slightly from the text reports: never-wrestled 0-0 forfeit/default bouts are dropped from the universe here. Career list matches wrestlers across years by (surname, first initial) because conference files spell first names differently; ties at the top-10 cutoff are ordered by share of wins with no takedown, and the page lists the wrestlers tied at the cutoff.

**Seed-control test (2026-09-20):** `scripts/analysis/td_custom_report/seed_control_test.py` → `data/analysis/seed_control_test.txt`. Asks whether the takedown leader's share of pins is just "the better wrestler gets both" by restricting to NCAA matches between close seeds. Seeds come from `data/{year}/ncaa-tourney/parsed/matches.json` (`winner_seed`/`loser_seed`, exposed on each bout by `td_differential_report.parse_bout` as `wseed`/`lseed`; NCAA only, conference results carry none). Result: among pins in matches with a takedown edge, the wrestler BEHIND on takedowns was the pinner 11.5% overall (NCAA), 6.0% at seed gaps of 16+, and 21.4% (95% CI 15-29) at gaps of 3 or less — skill explains part of the tilt, but the takedown leader still gets ~79% of pins between near-equal seeds. Limits: seeds are a rough skill proxy, and this cannot separate "the takedown causes the pin" from "the pin comes straight off the takedown".

### Takedown-report comparison page (2026-09-19)

`scripts/analysis/td_comparison_viz/build_comparison.py` → `data/analysis/td_report_comparison.html`: one self-contained page comparing the four report sections across the four windows and NCAA vs conference (line panels, range/strip plot, NCAA-vs-conf gap chart, stacked/heat charts, no-takedown-wins ladder; every chart has a table twin). It parses the 8 text reports (`parse_reports.py`, so the reports are the single source of numbers — rerun them first) into `reports.json` (git-ignored) and embeds that into `template.html`. Consistency labels (= steady, ▲/▼ step in 2024-26, ~ varies) use fixed rules in the template's `consist()`. Headline findings at build time: +2/+3/+4 TD edges win ≥95% everywhere; the +1 edge jumped from 88-92% to ~96% in 2024-26 in both tournament types together; conference wrestlers who score first win 1.8-4.4 pts more than NCAA ones in all four windows; nobody has ever had 4 no-takedown wins in one tournament.

### NCAA Takedowns & Team Points page (`ncaa_takedowns.html`, added 2026-09-29)

**What it is:** a live MatSavant page under Events → NCAA Championships → Archive → "Takedowns" (also a card on `events/ncaa.html`). One dot per wrestler per NCAA tournament, every entrant (not just All-Americans), 2015 onward. **x = takedown share** = takedowns he scored ÷ (scored + allowed) over his NCAA matches. **y = NCAA team points** he scored (advancement + bonus + placement). Dots are colored Champion / 2nd–4th / 5th–8th / Did not place (chips toggle each group). The black line with diamonds is the **average team points per 10%-wide band of takedown share** (bands with <5 wrestlers skipped). It sits below most visible dots because the 0–3-point non-placers stack on top of each other. There is also a band table (wrestlers, average points, number and % who placed), a sortable per-wrestler table (first 500 rows), and hover tooltips with the points breakdown. Light theme only (uses the site's `styles.css` variables). The chart redraws at the container's real width, so it stays readable on phones. First build: 3,540 wrestlers plotted, r = 0.65, 90–100% band averages 18.0 pts with 87% placing, and Seth Gross 2018 (11-12 takedowns, 24 pts) is the only champion under 50% takedown share. He's called out on the chart via `CALLOUTS` in the page script.

**Files:**
| File | Role |
|---|---|
| `scripts/analysis/td_share_team_points/build_data.py` | Builds the data; the only thing to run |
| `frontend/wrestledata-ui/public/data/reports/ncaa_td_share_team_points.json` | Output: `{meta: {years, entrants, plotted, no_td, no_pbp, built}, rows: [...]}`. Each row: `y` year, `wt`, `name`, `team`, `p` place 1-8 or null, `pts`, `adv`, `bonus`, `r` = [wins, losses, TDs for, TDs against] |
| `frontend/wrestledata-ui/public/ncaa_takedowns.html` | The page. Self-contained script, no chart library; all text (year range, notes, band table, stats) is computed from the JSON |
| `frontend/wrestledata-ui/public/event-tabs.js` | `NCAA_ARCHIVE_TABS` entry "Takedowns" |
| `frontend/wrestledata-ui/public/events/ncaa.html` | Landing-page card |

**Inputs:**
- **Official results:** `data/{year}/ncaa-tourney/parsed/matches.json`, built by `scripts/ncaa/parse_ncaa_results.py`. Used for team points and placements.
- **Play-by-play:** `data/{year}/ncaa-tourney/bout_detail/{weight}.json`. Used for takedowns, read through the loaders in `scripts/analysis/td_differential_report.py` (`R.load`), with never-wrestled 0-0 forfeits/defaults dropped (`build_data.wrestled` from the takedown report).

**How the numbers are computed:**
- **Team points** use the point tables imported from `parse_ncaa_results.py`:
  - Advancement: 1 per championship-bracket win, ½ per consolation win, 0 for Final/3rd/5th/7th matches.
  - Bonus: MD 1, TF 1½, Fall/Forfeit/Inj./DQ 2.
  - Placement: 16-12-10-9-7-6-4-3.
  - Byes are not credited, so a few totals may be ½–1 low.
  - Points are recomputed from `matches.json` rather than read from `parsed/wrestlers.json`. That file is keyed by seed and silently drops entrants whose name doesn't match the seeds file (e.g. 2018 197 Kyle Conel, 3rd). The script prints a cross-check against it; first build: 0 differences for every wrestler it contains.
- **Wrestler identity** across the two sources is (year, weight, surname + first initial). If two entrants in one bracket share that key (2017 125 Jose/Joshua Rodriguez), the script switches to full name for them and prints them as "ambiguous".
- **Left off the chart:** wrestlers with no takedowns either way (share undefined; 7 at first build) and wrestlers with no play-by-play for any wrestled match (81, nearly all 0-point entrants). The page no longer shows these counts (note removed 2026-09-29); the build script prints them.
- **Falls:** the play-by-play doesn't log falls, but the official result does, and points use the official result. Seth Gross's 2018 semifinal was a real fall in overtime after his sudden-victory takedown, so he gets 2 bonus points for it.

**Rebuilding after a new season (e.g. 2027):**
1. Make sure the new year's NCAA data exists, the same inputs every NCAA analysis uses: `data/2027/ncaa-tourney/parsed/matches.json` (run `scripts/ncaa/parse_ncaa_results.py` after the results are scraped) and `data/2027/ncaa-tourney/bout_detail/*.json` (the play-by-play scrape).
2. Run `.venv/bin/python scripts/analysis/td_share_team_points/build_data.py`. Years are detected automatically: every year ≥ 2015 with both inputs is included, with no code change. Check the printout: the year range should end in 2027, "differences vs parsed/wrestlers.json" should be 0 or only explainable name issues, and the not-plotted counts should be small.
3. Preview locally: `cd frontend/wrestledata-ui/public && python3 -m http.server 8792`, then open `http://127.0.0.1:8792/ncaa_takedowns.html`.
4. Deploy like any MatSavant change: the `matsavant-dev` branch gives a free preview, and merging to `main` is a paid production deploy. Only the JSON changes on a normal rebuild.
5. Optional: add a call-out for a notable new dot in `CALLOUTS` in `ncaa_takedowns.html`, and update the "first build" numbers in this section.

### NCAA Career Takedowns page (`ncaa_career_takedowns.html`, added 2026-09-29)

**What it is:** a live MatSavant page under Events → NCAA Championships → Archive → "Career Takedowns" (also a card on `events/ncaa.html`). It sits under NCAA but deliberately includes conference tournaments too (TJ, 2026-09-29).
- **What's plotted:** one dot per wrestler, pooling every NCAA-tournament AND conference-tournament match we have play-by-play for, 2015 onward. Only wrestlers with at least 5 such matches (`MIN_MATCHES`) are shown.
- **Axes:** x = career takedown share (takedowns scored ÷ scored + allowed). y = career win % in the same matches.
- **Colors:** best NCAA finish in those years: champion / All-American (2nd–8th) / NCAA qualifier / conference only. Chips toggle each group.
- **Band line:** the line with diamonds is the average win % per 10% band of takedown share. The band table also shows the pooled win % (all the band's matches added together).
- **Other features:** sortable per-wrestler table (first 500 rows), hover tooltips.
- **Styling:** light theme only; redraws at the real container width. No call-outs and no footnote (removed at TJ's request).
- **First build:** 1,879 wrestlers, r = 0.79, 90–100% band averages 85.1% wins. Of the 991 wrestlers under 50% share, 146 have a winning record. Seth Gross is the only one of 72 champions under 50% (25-27 takedowns, 12-3).

**Files:**
| File | Role |
|---|---|
| `scripts/analysis/career_td_share/build_data.py` | Builds the data; the only thing to run |
| `frontend/wrestledata-ui/public/data/reports/ncaa_career_td_share.json` | Output: `{meta: {years, min, plotted, few, no_td, linked_pct, built}, rows: [...]}`. Each row: `name`, `team` (up to two teams, e.g. transfers), `yrs` [first, last], `best` NCAA place 1-8 or null, `ncaa` number of NCAA tournaments, `linked` (matched to a career file), `r` = [wins, losses, TDs for, TDs against] |
| `frontend/wrestledata-ui/public/ncaa_career_takedowns.html` | The page. Self-contained script; all text and tables are computed from the JSON |
| `event-tabs.js`, `events/ncaa.html`, `sitemap.xml`, `scripts/generate_matsavant_sitemap.py` | Tab, landing card, sitemap entry |

**Inputs:**
- **NCAA play-by-play:** `data/{year}/ncaa-tourney/bout_detail/`.
- **Conference play-by-play:** `data/{year}/{conf}-tourney/bout_detail/` (ACC, Big Ten, Big 12, MAC, Pac-12, SoCon where they exist; complete brackets only; no EIWA). Both are loaded through `scripts/analysis/td_differential_report.py` (`R.load`, `R.load_conf`), and never-wrestled forfeits are dropped.
- **NCAA placements:** from `data/{year}/ncaa-tourney/parsed/matches.json` (Final/3rd/5th/7th matches).

**Linking matches to one wrestler (career identity):** a play-by-play bout names a wrestler only as (year, name, team).
1. **Name to season ID:** each (year, name, team) is matched to a `season_wrestler_id` through the season rosters in `mt/processed_data/ncaa_men/{year}/{Team}.json`. Same surname + first initial first; then team (normalized, with "University/State/St./of" etc. ignored); then weight; then exact full name to break ties.
2. **Season ID to career:** that ID is mapped to a career through `data/careers/ncaa_men/career_*.json` (`seasons` dict).
3. **Fallback:** anything that can't be linked is grouped by (surname + first initial, normalized team) instead.

First build linked 99.5% of match sides. About 10 names appear as two dots: real different people, or careers the career files already split (e.g. Zeke Moisey has two career files). Fixing those is a career-merge job, not a change to this script.

**Rebuilding after a new season (e.g. 2027):**
1. The new year's NCAA play-by-play (`data/2027/ncaa-tourney/bout_detail/`) and NCAA results (`parsed/matches.json`, for placements) must exist. Conference `bout_detail` for 2027 is picked up wherever it exists.
2. **Link the new season into the NCAA career files first** (`data/careers/ncaa_men/`, the normal NCAA career-linking pipeline). The new season's rosters must also be in `mt/processed_data/ncaa_men/2027/`. Otherwise 2027 wrestlers fall back to name+team grouping. Returning wrestlers still get split into two dots, and the printed "mapped to a career" rate drops below ~99%.
3. Run `.venv/bin/python scripts/analysis/career_td_share/build_data.py`. Years are detected automatically, with no code change. Check the printout: linked rate ~99%+, and the number of "unlinked plotted" wrestlers stays small.
4. Preview: `cd frontend/wrestledata-ui/public && python3 -m http.server 8795`, then open `http://127.0.0.1:8795/ncaa_career_takedowns.html`.
5. Deploy like any MatSavant change (`matsavant-dev` preview, or `main` = paid production deploy). Only the JSON changes on a normal rebuild.

It's natural to rebuild this together with "NCAA Takedowns & Team Points" above; they share the takedown loaders.

### Conference-tournament official results (built from team scrapes, 2026-09-19)

**Script:** `scripts/analysis/build_conference_results.py [--start Y --end Y]` → `data/{year}/{conf}-tourney/parsed/matches.json` (conf ∈ `big_ten big_12 acc mac pac_12 socon`; 2015-2026; 70 files, ~11,400 matches). **Source:** `mt/processed_data/ncaa_men/{year}/{Team}.json` — every wrestler's match list already carries `event` (e.g. "2019 Big Ten Wrestling Championships"), the round label inside `summary` ("Champ. Round 1 - A (X) over B (Y) (TF 17-0 4:39)"), and `result` ("Dec 7-3", "Fall 1:06", "TF 17-0 4:39", "SV-1 4-1", "TB-1 2-1", "M. For.", "MFFL", "Inj. 5:12", "DQ", "Def.", "BYE", "NoResult"). No new scraping was needed (an initial plan to re-scrape TrackWrestling's `RoundResults.jsp` per tournament was dropped once the team scrapes were pointed out; the TrackWrestling results page does carry the same info and matched our bouts 100% in a 3-tournament probe, so it remains a fallback for tournaments the team scrapes miss).

**Record:** `year, conference, weight, round (None for the older "Varsity - ..." summary format), winner_name/team, loser_name/team, result_type (Dec|MD|TF|Fall|SV-n|TB-n|UTB|Forfeit|Inj.|DQ|Default|Unknown), result_raw, score ("winner-loser", point results only), time (Fall/TF/Inj.), date, event`. `SV-n (Fall)` is stored as Fall; `M. For.`/`For.`/`MFFL` → Forfeit; BYE/NoResult rows are dropped.

**Gotchas:** (1) both wrestlers' team files list the same match, and one file may carry the round label while the other has none (`Varsity - ...`), so de-duplicate on (weight, winner, loser, result) — NOT on the round — or every match doubles; a pair that meets twice with the same result is kept twice via the max per-team-file count. (2) Event names vary wildly by year (`Pac 12`s`, `SoCon Tournament`, `Mid American Conference`, `2020 MAC Wrestling Championships03`, `Big Ten Championships`); recognised by conference pattern, excluding `vs. ...` duals, NCAA, EIWA and "duals". (3) **Names differ from `bout_detail`** (Timmy vs Timothy McCall, Jeff vs Jeffrey Koepke): join on (weight, surname, first initial), not exact name — this took the match rate from 89% to 97.7%. (4) `bout_detail` header scores differ from the official score by 1 point in ~1% of bouts (usually the riding-time point) — still the same bout. (5) A header with winner score < loser score whose reversed score equals the official score is the swapped-sides error; in conference data it occurs in ~0.1-0.15% of bouts (12 found across 2015-2026, all listed in each report's Data Notes; the impossible 15+ case is caught even without an official match). (6) The team scrapes also hold EIWA and other conference results (EIWA has no `bout_detail`; not extracted).

**Data gotchas learned building it (all handled in the script):**
- **Swapped-sides bout (2026 174, Baumann-Carrigan):** the bout_detail file has the winner/loser scores AND every event's `side` reversed relative to the headline (file says 8-15, official 15-8). Undetected, it shows up as a bogus "upset" and flips a takedown edge. Detected as header winner score < loser score where the reversed score equals an official points-result score for that pair; sides are flipped for that bout and the bout is listed in the report's Data Notes. Only 1 such bout in 1,488 checkable 2023-2026 decisions — but the class of error can't be ruled out for falls, which have no official score to check against.
- **Round labels can disagree between `bout_detail` and `parsed/matches.json` for rematch pairs** (same two wrestlers meeting twice, e.g. QF then 3rd-place match): the same pair's two bouts can carry each other's round label. Don't join those two files on `(weight, winner, loser, round)`; the script joins on `(weight, winner, loser)` and disambiguates by score, then round, and leaves a bout "unmatched" (excluded from points-only, kept in all-bouts) if it still can't tell.
- **Falls are not logged as events.** Play-by-play for a pin ends at the last scoring event; the header score is the score at the moment of the pin, so the pinned wrestler is often ahead on the scoreboard. "Nearfall points" therefore only counts nearfall that was actually awarded points.
- **Overtime labels:** `Overtime 1` = sudden victory (first score wins); `Overtime 2`/`Overtime 3` = the two 30-second tiebreaker periods (each wrestler gets a turn on bottom). A takedown scored in overtime still counts toward the bout's takedown differential, so a "tied on takedowns" bout can end on an overtime takedown. When both wrestlers escape in the tiebreakers, the **faster escape won 8 of 8** in the first run (escape time = 30s minus the event's clock).
- **A takedown event's clock is time REMAINING in the period**, same convention as every other event in this data.

## NCAA Regular-Season Dual Poller (Prototype — Shelved 2026-09-14)

**Undocumented data source found 2026-09-13** while scoping a lower-traffic alternative to the team-by-team roster scraper (`wrestle_scraper_raw_mt_locked.py`, which is still the source of truth and runs weekly). This does not replace it — it's a cheap supplemental *detector* for newly-completed regular-season duals, meant to poll far more often (nightly) without re-crawling every D1 team's roster and every wrestler's match page.

**The discovery:** Browse > Seasons > `<season>` College Men > NCAA lands on `seasons/Results.jsp`, which embeds the season's **entire event list** (tournaments + duals, ~250 rows/season) in one client-side JS array, `dataGrid` — already fully loaded regardless of the visible "Show N" page size (confirmed: `Teams.jsp`'s own `dataGrid` had 289 rows while only 50 were displayed). Each row is fixed-position:

| idx | meaning | tournament row | dual row |
|---|---|---|---|
| 0 | event id (`dualId` for duals) | set | set |
| 3/4 | start/end date (YYYYMMDD) | set | set |
| 5 | tournament name | **set** | **empty** |
| 8–11 | team1 `teamId`/name/state/score | empty | set |
| 12–15 | team2 `teamId`/name/state/score | empty | set |

**A row is a dual iff idx 9 and idx 13 (team names) are both non-empty** — a cleaner discriminator than event-name pattern matching, and the final score is right there with no further fetch needed.

**Bout-level detail** (weight-by-weight, method, score) lives at a separate plain authenticated page: `seasons/DualMatches.jsp?dualId=<idx0>&teamId=<idx8 or idx12>&twSessionId=<session>`. It renders one `.dataGridRow` per weight class with columns `[_, weight, summary, team1_points, team2_points]`, e.g. `"Troy Spratley (Oklahoma State) over Dean Peterson (Iowa) (Dec 5-2)"`. Forfeits use a shorter form with no opposing-team group: `"Tucker Owens (Air Force) over Unknown (For.)"` — needs its own regex fallback, see the script.

**Known site gotcha — do not trigger this by simulating a click:** the site normally opens this URL via `openEvent(idx)` in a popup. A *synthetic* (non-trusted) click on that link hangs the page indefinitely — when Chrome's popup blocker silently blocks the resulting `window.open()`, TrackWrestling's JS does not handle the null return and hangs. A real navigation straight to the URL (which is all the poller does) has no such problem.

**D1 filtering:** cross-references team1/team2 `teamId` against `data/team_lists/ncaa_men/<season>/teams.json` (from `scripts/scrape_ncaa_d1_teams.py`) rather than name-matching — team-ID formats vary a lot between teams (not a uniform ID range), so always compare by ID, never assume a numeric-range pattern.

**Reliability gotcha:** fetching ~100 `DualMatches.jsp` pages back-to-back with no delay caused TrackWrestling to silently return empty pages (0 rows, no error) across the board — looks like throttling, not a real data gap. Fixed with a courtesy delay between fetches plus retry-with-backoff on a 0-row result; held up cleanly afterward.

**Script:** `scripts/ncaa/poll_ncaa_d1_duals.py`. State (seen `dualId`s, so a dual is only fetched once): `mt/tracking/ncaa_dual_poll_state_<season>_men.json`. Output: `mt/data/ncaa_men/<season>/duals/<dualId>.json`.

**Status: prototype, shelved.** Validated end-to-end against the completed 2024-25 season (real historical data) — navigation, D1 filtering, bout parsing, retry/backoff, and dedup all confirmed working. **Not yet run against a live/in-progress season** — the one thing unconfirmed is whether a dual's results land in the feed same-day. D1 duals for 2026-27 don't start until 2026-11-01; test this live before folding it into the standard process, and resolve first: D1-mode (currently "either team D1", could require both), run cadence/cron, and whether output should stay under `mt/data/ncaa_men/.../duals/` or feed into an existing MatSavant data path instead.

---

## NCAA Bracket Archive (Lab, built 2026-10-01)

Every NCAA championship 1928-2026 at `/lab/brackets/` (directory) and `/lab/brackets/year.html?y=1979&w=150`
(`w=team` = Team Scores tab). Linked from the Lab page only.

- **Build:** `.venv/bin/python scripts/brackets/build_ncaa_bracket_archive.py [--year N]` writes
  `frontend/wrestledata-ui/public/lab/brackets/data/{year}.json` + `index.json` (~11 MB total). The script's docstring
  documents the output format and layout rules. Re-run after a new NCAA tournament is parsed into `all_matches.json`.
- **Sources (TJ's rule):** 1928-2012 = `data/ncaa_historical_brackets/` (wrestlingstats.com sheets; read its `SPEC.md`).
  2013 on = `data/ncaa-tourney-parsed/all_matches.json` (TrackWrestling); 2013-2016 hosts/dates/awards still come
  from the sheet files. No tournament 1943-45 or 2020. 1934 and 1938 are placewinners only (no bouts exist in the source).
- **Formats shown as they were:** Bergman wrestle-backs (1928-40: "for 2nd" / "for 3rd" sections), bad-point
  rounds as tables (1936, 1948), drawn consolation brackets (1941 on). Bouts whose winner the sheet doesn't show
  appear with no winner ("result not recorded").
- **Viewer:** `lab/brackets/bracket_engine.js` is a copy of `labs/bracket_viewer/bracket_engine.js`, extended (wrestler key
  `k`, no-winner bouts). Keep the two in step if the engine changes.
- **Team names:** shown as printed at the time, with spelling fixes only (`TEAM_FIXES` in the build script:
  PDF-truncated names, TrackWrestling's mixed "Penn St."/"Penn State", "UNI"/"Northern Iowa"). Linking old names
  to today's programs (team history) is **not built yet**.
- **Team scores:**
  - The printed top ten is used wherever it exists (1929-2016 except 1933).
  - 2013 on is calculated from the bouts with NCAA D1 scoring: advancement 1 per championship win (pigtail to
    semifinal) and 0.5 per consolation win before the place bouts; placement 16-12-10-9-7-6-4-3; bonus 2 fall /
    forfeit / default / DQ, 1.5 tech fall, 1 major. Deductions come from `data/{year}/ncaa-tourney/team_penalties.json`
    (only 2024 and 2026 exist).
  - Check against the printed 2013/2014/2016 top tens: 25 of 30 teams are exact. The rest are off by 1, except
    2013 Minnesota (printed 110.5, bouts 103). The likely causes are unrecorded team deductions and 2016 tech falls
    (back then a tech fall without near-fall points may have been worth 1, not 1.5).
  - For 2013, 2014 and 2016 the page shows the printed top ten and the calculated rest of the field. A ⚑ flag marks
    rows where the print and the bouts disagree.
  - The 2014 summary prints "Northern Iowa" in 9th. The bouts give Northwestern exactly 46 and Northern Iowa 40, so
    `PRINTED_TEAM_CORRECTIONS` shows Northwestern, with a flag.
- **Not done:** scoring rules for the eras before 2013 (needed for 1933, the missing 10th rows in 1931 and 1972,
  and full standings in old years). The 1930s fit about half the printed rows with 5-3-1 for places plus 1 per fall.
  It isn't exact, partly because many 1930s bouts are time-advantage results or have no result on the sheet. Also
  not done: team history pages, and WPA charts on 2013+ bouts.

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

## Win Probability + WPA Model (spec build, started 2026-09-29)

A rebuild of the win-probability idea above, done properly to TJ's spec (`wrestling_wpa_spec.md`: empirical state table with shrinkage, seed/rank strength layer that fades with the clock, WPA per event). **Separate from the Lab model above** — nothing here touches `data/pbp/`, `scripts/win_prob/` or the site. Code in `scripts/wpa/`, everything it writes under `data/wpa/`; each step writes a report to `data/wpa/reports/`.

| Step | Script | Output |
|---|---|---|
| 1. Data audit | `scripts/wpa/audit_data.py` | `data/wpa/reports/data_audit.md` |
| 2. State reconstruction | `scripts/wpa/build_states.py --kind ncaa\|conf\|both` (shared definitions: `scripts/wpa/wpa_common.py`) | `data/wpa/states/{ncaa,conf}_{bouts,events,samples}.csv`, `data/wpa/reports/state_reconstruction.md` |
| 3. Empirical state table | `scripts/wpa/build_table.py` | `data/wpa/table/{ncaa,conf}_obs.csv.gz` (winner-side observations), `{ncaa,conf}_table.csv` (cells: n_obs, n_matches, wins, p_emp, p_emp_match) |
| 4. Sparsity audit | `scripts/wpa/sparsity_audit.py` | `data/wpa/reports/sparsity_audit.md` + `img/` heatmaps — finding: the spec key is too fine (56% of E3 NCAA moments in cells with < 50 bouts, mostly from riding-time bins); backstop needed; conference E3 matches NCAA E3 and is the best way to thicken E3 |
| 5–6. State model (smoothing, backstop, riding-time split, monotonicity) | `scripts/wpa/fit_state_model.py` (~9 min) | `data/wpa/model/state_table.parquet`, `rt_model.joblib` (the riding-time blend), `rt_params.json` (its rate model), `backstop.joblib`, `model_params.json`, `data/wpa/reports/state_model.md` — riding-time point model = step-8 trees handing off to a rate model (`scripts/wpa/rt_hazard.py`) between 1:30 and 0:30 left (see "Changes after step 9"); table keyed on current margin AND the eventual riding-time point (pooling them as margin + point was tried and failed, and is no longer eligible even when its log loss wins — see below); E3 cells from NCAA + conference; built from the 10-s samples + the state just after each event + break states (step 8); projected monotone in margin, in the riding-time point and in the release option; held-out log loss 0.466 vs 0.468 (table ignoring riding time) and 0.472 (margin + time), with the gains concentrated late in close bouts (last 30 s within 2: 0.372 vs 0.416 and 0.431) |
| 7. Strength layer (NCAA seeds) | `scripts/wpa/fit_strength.py [--refresh]` (~5 min; the out-of-fold state probabilities are rebuilt automatically when the state table changes, +6 min; `--refresh` forces it) | `data/wpa/model/strength_params.json`, `tie_model.joblib`, `ncaa_oof_state.parquet`, `data/wpa/reports/strength_layer.md` — logit(WP) = α(t)·logit(WP_state) + β0·(t/420)^γ·rs + β_ot·P(tied at the buzzer)·rs; normal-quantile seeds (N = 50), 2015–18 unseeded valued like seed 22, α = 0.64 + 0.32 × share of the match elapsed, β0 1.56, γ 0.61, β_ot 0.51, 2024–26 seed effect × 0.87 (small, data-chosen); leave-one-tournament-out log loss 0.446 → 0.393 |
| 8. Validation | `scripts/wpa/validate.py [--reuse]` (~6 min; `--reuse` re-renders from the cached held-out predictions) | `data/wpa/reports/validation.md` + `img/validation_{calibration,slices}.png` — leave one tournament out + forward in time, bout-bootstrap intervals: log loss 0.456 margin + time → 0.446 state model → 0.393 full (2024–26: 0.472 → 0.466 → 0.414; forward 2024 cold start 0.415); calibration slope 1.00 (2024–26 0.97); 7 of 7 hand checks (the riding-time knife edge passes since the blend); 0 monotonicity drops in riding time and seed (4 grid steps in margin); 0.51% of scoring events lower the scorer's WP, all by ≤ 0.001 |
| 9. WPA per event | `scripts/wpa/compute_wpa.py [--kind ncaa|conf|both]` (~20 s; default both since step 10) | `data/wpa/output/events_wpa.parquet` (gitignored; one row per link of each bout's chain — events, clock stretches, riding-time locks), `data/wpa/output/wrestler_wpa.csv` (per wrestler per tournament: total = wins − expected wins, split by category, own vs opponent's scoring, and top / bottom / neutral / break / OT), `data/wpa/reports/wpa.md` — every bout's WPA sums exactly to result − opening WP (asserted); penalty/stalling points credited to the offender; overtime from the overtime model for 2022+ (see "Overtime model"), before that the overtime win rate until the winner's last OT score; 104 of 36,700 regulation scoring events negative, all ≤ 0.0006 |
| Choices (2026-09-30, TJ) | `scripts/wpa/fit_choice_shares.py` (seconds), then `compute_wpa.py` → `build_outputs.py` | `data/wpa/model/choice_shares.json` — break states (before the toss / toss won / about to pick) are no longer their own table cells: `wp_model.WPModel` values them from the regulation states they lead to, weighted by observed pick and defer shares. See "Break states" below |
| OT. Overtime model (after step 10, TJ) | `scripts/wpa/ot_model.py` (~2.5 min), then `compute_wpa.py` | `data/wpa/model/ot_params.json`, `data/wpa/states/ot_bouts.csv` (gitignored), `data/wpa/reports/ot_model.md` — current overtime rules only (2022+, 676 bouts); held out by season: log loss 0.662 flat overtime rate → **0.646** (tiebreaker states 0.666 → 0.561; every season better, 2026 by 0.022); calibrated 55–94%. See "Overtime model" below |
| 11. Final outputs (spec Section 8) | `scripts/wpa/build_outputs.py` (~1 min, after `compute_wpa.py`); `scripts/wpa/plot_examples.py` | `data/wpa/output/{state_table,match_wp_curves}.parquet` (gitignored), `data/wpa/output/model_params.json` (all fitted parameters merged), example step-plot charts in `data/wpa/reports/img/examples/`, `data/wpa/reports/final_summary.md` (spec Section 11 answers) |
| 10. Conference tournaments | `scripts/wpa/conf_ranks.py` (national rank per conference bout; see "Conference rank source"), then `fit_strength.py` → `validate.py` → `compute_wpa.py` | `data/wpa/states/conf_ranks.csv` (gitignored), `data/wpa/reports/conf_ranks.md`; `strength_params.json` → `conf`; `data/wpa/model/conf_oof_state.parquet`, `conf_heldout.parquet` (gitignored); `validation.md` section 9; `wpa.md` conference section — conference bouts use NATIONAL RANK on their own scale (N 200, unranked ≈ rank 60) × 1.45, and the state part's α × 1.14 (without it held-out conference predictions were underconfident, slope 1.08); fitted and validated leave-one-season-out on the leak-free seasons 2023–26 only (3,197 bouts): log loss 0.4355 state model → **0.3792**, slope 0.997; NCAA results unchanged. 7,917 conference bouts in the WPA chain (pre-2023 ones use the leaky end-of-season rank, caveated). The sparsity audit already covered conference E3 (table D) and its inputs didn't change, so it wasn't rerun |

**Decisions (TJ, 2026-09-29):** riding time rebuilt from position; unclocked events placed between clocked neighbours (fraction fitted per event type, validated on held-out years); pre-2019 NCAA seeds 17–33 = unseeded; rules eras E1 2015 / E2 2016–23 / E3 2024–26 with **E3 as the anchor** (older eras fill gaps, validation judged on E3); conference rank leakage accepted with a caveat; falls end at their official time. **Choice encoding:** the disk toss is at the start of period 2, so nobody holds a choice during period 1 (the spec's wording would put a future coin flip into period-1 states); the toss, defer and pick are separate events at the break.

**Decisions after the sparsity audit (TJ, 2026-09-29):** (1) **riding time is factored out of the state table** — WP = Σ P(riding-time point: A / none / B) × WP_table(margin + that point, time, period, position, choice); the point probability is its own model (riding-time differential, time left, position, margin), fitted on all eras since the riding-time rule hasn't changed; this replaces the spec's riding-time bins as a table dimension (the spec key left 56% of E3 moments in cells with < 50 bouts; factored out, E3 NCAA + conference: 12%); (2) conference 2024–26 states go into the table now (conference rank still waits for step 10); (3) validation rotates within E3 — train on two of 2024/2025/2026, test on the third NCAA year, all three rotations; (4) the 214 NCAA bouts set aside for riding-time reconstruction errors go back into the table, but not into the riding-time model; (5) the seed effect is fit on all NCAA years (2015–18 seeds 17–33 unseeded), then checked for E3; (6) a tie at the end of regulation is worth the overtime win rate, with the seed effect in overtime fit on all overtime bouts; (7) injury defaults / DQs stay in; (8) outputs as parquet (pyarrow installed in `.venv`); (9) `data/wpa/states/` and `data/wpa/table/` are gitignored (rebuild in about a minute with steps 2–3), as are the model binaries in `data/wpa/model/` (`*.parquet`, `*.joblib`; rebuild with steps 5–7); the `*_params.json` files are tracked.

**Changes made in step 8 (validation, 2026-09-29)** — each found by `validate.py`, each re-validated on held-out years:
1. **"Just before an event" moments are dropped** from the table and models (except break states): they're a biased sample, because the event about to happen is usually the trailing wrestler scoring. In the same cells, leaders won 6–7 points less often at those moments than at the 10-second samples in the last minute. This deviates from spec 3.1 on purpose.
2. **10-second samples sit at bin centres** (the opening whistle, then 415, 405 … 5 s left; `build_states.SAMPLE_TIMES`). The old grid (420 … 10) never sampled the last 10 seconds.
3. **Riding-time model:** added the share of the remaining time each wrestler must still ride to reach 1:00, the choice holder and a break flag. It's monotone in both wrestlers' remaining need and exact per wrestler whenever the clock decides the point. Monotone in margin too, chosen on held-out WP (0.4659 vs 0.4669 free). Free in margin fits the point itself better, because a big lead often ends in a tech fall with no point awarded, but it lets WP fall as the margin grows. The old version said 58% for "on top, 5 s left, must ride all of it"; the data says 89–96%. The new one gets partway (69% for that hand-checked state, the one failed hand check in `validation.md`). There are only 1–5 such moments per year, and refits move it between 53% and 78%, so it's left as a known soft spot, not tuned by hand.
4. **Tie model** (overtime seed term): now uses the state model's split, P(tie) = Σ_r P(r | S) · P(tie | S, r).
5. **Table monotone in the eventual riding-time point** as well as in margin.
6. **Seed layer shrinks the state part**, logit(WP) = α·logit(WP_state) + β(t)·rs + β_ot·P(tie)·rs. The state table already builds in "the leader is usually the better wrestler", so the spec's additive form (α = 1) double-counted strength and was overconfident in evenly matched bouts (calibration slope 0.80). The form of α (constant, or changing with the clock) is chosen on held-out log loss. α never depends on the seed gap: a gap-dependent α fitted marginally better but let a better seed lower WP in a losing position, and WP must rise with the seed advantage.
7. **Table respects the release option.** The top wrestler can always let his man go, so A on top at margin m is worth at least neutral at m − 1. Mirrored, an escape can't lower the escaper's WP. Before this, 2.7% of escapes had negative WPA. With margin monotonicity this also covers takedowns and reversals.

**Changes after step 9 (2026-09-29, TJ)** — the riding-time point model:
1. **A simple rate model was built** (`scripts/wpa/rt_hazard.py`, parameters `data/wpa/model/rt_params.json`): per-second rates from the play-by-play (bottom man escapes / reverses, top man near falls, takedowns in neutral, fall / injury / DQ; a margin of 15 = tech fall), period-pick and defer shares, then an exact dynamic program over position × margin × riding-time differential to the end of regulation. Monotone and exact at the locks by construction. It predicts the point itself better than the trees (held-out log loss 0.345 vs 0.367) and fixes the knife edge ("on top, 5 s left, must ride all of it": 89%).
2. **But it predicts the WINNER worse** early in bouts: held-out WP log loss 0.4666 (era only) vs 0.4659 for the trees; variants by margin (0.4690) or by riding-time lead (0.4684) — tried as a "skill persists" fix — were worse still. In the last minute the two are equally accurate (0.2250 vs 0.2242), and the rate model gets the late, fan-checkable states right (tied 2-2, 0:43 left, +1:01 riding time: trees 58% for the point, rate model 89%).
3. **TJ's choice: a blend** — trees until 1:30 left, linear handoff, rate model alone from 0:30 (`fit_state_model.RT_BLEND`, `BLEND_T`). Result: held-out WP equal to the trees (0.4659), 7 of 7 hand checks, no drift or jump at the handoff (WP change per second on clock stretches in 1:30–0:30 is the same as on either side). Rationale: fewest numbers that look wrong to users.
4. **The pooled table key (margin + point) is no longer eligible.** With the rate model alone it won held-out log loss by 0.001 and broke structurally ("tied, 0:30, A on bottom" → 41%; 4.2% of scoring events lowered the scorer's WP, up to 12 points). It's still scored in `state_model.md` for the record.
5. Example charts: `scripts/wpa/plot_wp_cards.py` (ESPN-style cards; `--year Y` = that year's finals, `--wrestler NAME` = one wrestler's run) → `data/wpa/reports/img/`.

**Conference rank source (step 10, 2026-09-29)** — conference-tournament bouts use NATIONAL RANK as the strength input (spec), built by `scripts/wpa/conf_ranks.py` → `data/wpa/states/conf_ranks.csv` (`w_rank`, `l_rank`, `rank_source`, `leak_free`; report `data/wpa/reports/conf_ranks.md`):
- **2023–2026, leak-free:** the latest FloWrestling snapshot dated before Feb 15 of the season (`data/{season}/flo-preseason-rankings/`: 2023-01-30, 2024-02-02, 2025-02-03, 2026-02-02), i.e. before the conference tournaments — what a live model would have had. Depth 24 per weight in 2023, 33 from 2024.
- **2015–2022, leaks:** no dated pre-tournament ranking exists, so the end-of-season `current_rank` from the MatSavant season profiles is used (see "NCAA Ranking Methodology" above). Before 2023 its top 8 are NCAA placements — results from after the conference tournament — so these ranks leak (TJ decision E: accepted, caveated). Used for WPA only; the conference strength layer is fitted and validated on 2023–26 alone.
- Ranks deeper than 33 count as unranked. Matching: surname + first initial at the bout's weight with the school agreeing through an explicit alias table (`SCHOOL_ALIASES` — exact matches only; "Penn" must never match "Penn State"), else the same name at another weight with the school agreeing. Check in the report: of the Flo-ranked wrestlers from the schools in each season's conference tournaments, 2–4% were never matched, and the spot-checked ones really didn't wrestle there.
- Do NOT use `current_rank` as a pre-tournament rank for anything new — it's end-of-season by construction.

**Break states (2026-09-30, TJ)** — TJ spotted a coin toss worth −1.5 and a standard P3 bottom pick at −0.4 in the bracket viewer. Cause: the three break states (`pending_pre_toss`, `pending_defer_option`, `pending_pick`) were independent state-table cells (~100–200 bouts per margin) with nothing tying them together, so toss values ran from −2.1 (down 2) to +1.6 (down 1) in 2024–26. Now `WPModel` composes them: about to pick = share-weighted average of bottom / top / neutral (shares by era × period × chooser's margin, `fit_choice_shares.py`, shrunk K=20); toss won = defer share × (opponent picks P2) + (1 − defer share) × (holder picks P2); before the toss = ½ / ½. Toss WPA is now 0 to +0.75 at every margin; the usual pick reads ≈0 (the viewer prints "≈0" under 0.5 pts). Held-out-style check on break moments: log loss 0.3634 vs 0.3630 for the old cells, which were fitted on those same outcomes. Real strategy shows in the shares, e.g. 2024–26 down 2 in P3: 37% pick neutral (one 3-point takedown leads) vs 12–16% down 1 or 3. **Deferring stays negative** (mean −2.3 in 2024–26), and it's real, not selection: deferrers won 1.4 pts less than the model's value at the toss, immediate choosers 1.6 more (gap ≈ 3 pts in both eras vs the model's 3.5–4.3; after the decision both groups are calibrated, +0.6 / −0.2). Caveat: `validate.py`'s held-out folds use their own per-fold models, not `WPModel`, so they don't see this change (break moments are a tiny share of samples).

**Overtime model (2026-09-29, TJ: separate sudden-victory and tiebreaker rules, current-rules data only)** — `scripts/wpa/ot_model.py`; its docstring has the rules, every data fact below with counts, and the model.
- **Rules / pool:** 2-minute sudden victory and the 1-second tiebreaker riding-time rule since 2021-22 (data year 2022, ncaa.com 2021-06-23); the 2025-26 rules changes (NCAA PDF) have no overtime change. 2026 did have more bouts reach the tiebreaker (32% vs ~23%) — no rule behind it, and the model held out on 2026 still beats the flat rate by the most of any season.
- **Sudden victory:** first score wins; the scoring rate climbs through the 2:00 (0.6%/s in the first 30 s, 1.2–1.35%/s after); P(scoreless) 27%. Strength: P(A scores first) = expit(0.77 · rank signal).
- **Tiebreaker (TB-1)**, facts that change how it must be modelled: (a) **riding time is only a points-tie breaker** (1 s or more of tiebreaker riding time, reset to 0 at the start of TB-1), not a point added to the score — TrackWrestling still logs a "Riding Time" point for the winner; (b) `Choice 3` logs the ride-1 BOTTOM wrestler (every pick is bottom); the holder (first takedown / near fall in regulation, else an unlogged coin flip — 150 of 178) can **defer** ("X: Defer", 17 of 50 in 2026), so the ride-2 chooser is always the wrestler on top in ride 1; (c) the ride-2 chooser takes **bottom 69–76%** of the time (behind on points / tied with the riding-time lead), far more than the model's best option (neutral), so that habit sets the value before the pick and the pick itself is an `ot_choice` link; (d) **a scoreless ride isn't logged**, and every later round is written into the same `Overtime 1/2/3` columns — a TB-1 that ended tied was scoreless (ride-out, bottom, ridden out = 30-30) in 38 of 39 later-round bouts, so their logged tiebreaker events are TB-2's; (e) in neutral the tiebreak LEADER scores takedowns (13 vs 8) and draws stall points (8 vs 4) more than the trailer.
- **Model:** exact per-second recursion over (position, tiebreaker margin, tiebreaker riding time) through the two 30-s rides, rates from TB-1 rides (plus two ridden-out rides per scoreless-tie bout), strength k_tb 0.80; then shrunk, logit × 0.64 — without it the model said 96% where the favourite won 88% (late stall points / scrambles come ~3× as often as the average rates). Later rounds (SV-2, TB-2, UTB) = one value, expit(0.77 · rs).
- **Known limits:** predicted TB-1 ties 14% vs 23% observed; one overtime score of 1,597 has negative WPA (Spratley's escape up 2 in ride 2, −0.006); five 2026 TB-1 finishes carry a wrong result label (Dec / Unknown / blank). Flow chart of every overtime bout in a season (NCAA + conference): `scripts/wpa/plot_ot_flow.py --year Y` → `data/wpa/reports/img/ot_flow_{Y}.png` (2025, 2026 committed).

One predictor for everything downstream: `scripts/wpa/wp_model.py` (`WPModel().wp(df)` / `.parts(df)`).

**Storage:** each bout once, from the winner's side (`w`/`l`); `wpa_common.perspective()` / `mirror()` produce the two A-relative views. `rt_status()` is the spec's riding-time lock (threshold `>= 60` s). Step 3 filters on the bouts file's `state_table_ok` (NCAA 96.8% of bouts, conference 89.3%; reasons in `state_table_reason`).

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

**The Dual Schedule page** (`schedule.html` + `schedule.js`) reads only `data/schedule/duals_2026-27.json` (written by step 5), plus 2026 xTP for the top-25 rank badges and `team_colors.json` for the cards. Since 2026-10-01 it has a team filter, built on the Teams page's search (same Fuse options over the search index's team entries, limited to teams that appear in the schedule; picking one filters the list instead of opening the team page, with the picked team always shown on the left), and a **Text only** toggle (off by default) for a dense date-column list. Both are kept in the URL: `?team=<slug>`, `?view=text`.

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

**Status as of 2026-09-13 (first run of the new current-season batch script):** 60 of 79 teams have a 2026-27 roster on file (7 newly added this run: Buffalo, Cal Poly, Campbell, CSU Bakersfield, Harvard, Lock Haven, Navy). Chattanooga and Wisconsin picked up newly-added players on a `--mode all` recheck. Illinois is flagged for review (26 → 25 players, one dropped) — the new pull is parked, not yet accepted. 13 teams haven't posted 2026-27 yet; 5 (California Baptist, Central Michigan, The Citadel, Gardner-Webb, Maryland) were labelled `no_players_found` and originally read as "a new template variant" — **that diagnosis was wrong (corrected 2026-09-21, see below)**.

**Status as of 2026-09-21 (full `--mode all` rescan + schedule rescan, Little Rock excluded):** rosters: American and Rider newly on file, Ohio 18 → 30, Binghamton +1, and the four parked flags (Brown, Drexel, Navy, Sacred Heart) were reviewed and accepted (TJ). Schedules: 27 → 36 of 79 teams posted; Wisconsin's parked Nov 1 opponent change (Bucknell → Bloomsburg) accepted. Little Rock's schedule was re-verified from a user-saved webarchive (`data/_tmp/2026-27 Wrestling Schedule - Little Rock Trojans.webarchive`, 18 events, identical to what's on file).

**Status as of 2026-10-01 (full `--mode all` roster rescan + schedule rescan):** rosters 65 → 69 of 79 (new: Gardner-Webb, Maryland, Mercyhurst, Northern Illinois; added players at Rider +12, Oregon State +9, Campbell +4, Arizona State, Cornell). Seven one/two-player drops (Columbia, Duke, Harvard, Iowa, Michigan, NC State, Rutgers) were reviewed and accepted (TJ). Penn State, Northwestern, Virginia Tech and Little Rock returned `not_found` (2025-26 kept). Schedules 38 → 60 of 79 (23 newly posted incl. Penn State, Oklahoma State, Minnesota; Rider fetched on a retry after a timeout); all 9 parked changes accepted (TJ) — date moves of a day, renamed events, and Purdue/Wisconsin filling in Big Ten dates. **The Schedule page does not update by itself**: after accepting schedule changes, run `dedupe_events.py` (step 5), which rewrites `frontend/wrestledata-ui/public/data/schedule/duals_2026-27.json` (236 → 490 duals this run). There is no roster review CLI; parked rosters were accepted by copying `{season}.pending.json` over `{season}.json`, updating `_status.json`, removing the flag, then `batch_scrape_current_rosters.py --render-only`.

**`no_players_found` on the modern Sidearm sites usually means "2026-27 not posted yet", NOT a parser failure (found 2026-09-21).** On these sites (all five above) any season URL that hasn't been posted (`/roster/2026-27`, `/roster/2026-2027`) returns HTTP 200 with an empty, unrendered template — `<title>@season Wrestling Roster - …</title>`, zero real player cards — and `scrape_season()` can't tell that apart from a broken parser, so it reports `no_players_found`. The bare `/sports/wrestling/roster` page parses fine with the existing `parse_html_roster()` (`s-person-card`; 26/24/30/40/31 players) but still shows 2025-26 (season selector `selected-option__text`), with names identical to the 2025-26 files on file — so nothing new to ingest until each school posts 2026-27. Quick check for any `no_players_found` team: fetch the season URL and look for `@season` in `<title>`. (Possible scraper improvement, not done: return `not_posted_yet` when the title contains `@season`.)

**Open issue — robots.txt vs. the schedule scraper (found 2026-09-21):** every scrape here identifies as `ClaudeBot`, and the roster pages are allowed for that agent, but (a) **Little Rock** (`lrtrojans.com`) serves `User-agent: *` / `Disallow: /` — its roster/schedule URLs are hardcoded in both batch scripts' `MANUAL_SCHOOL_BASE_URLS` and the schedule was fetched automatically on 2026-09-13 and 2026-09-16; policy is user-saved webarchive/PDF only (see roster section above), and (b) the 13 teams parsed via **Template D-text** (App State, Bellarmine, Bloomsburg, Clarion, Cornell, Edinboro, Franklin & Marshall, Lock Haven, Morgan State, Navy, SIUE, Utah Valley, Wyoming) are read through `/services/schedule_txt.ashx`, which those sites' robots.txt `Disallow: /services/` for our agent. The 2026-09-21 rescan skipped Little Rock but still fetched the D-text feeds. **Decision (TJ, 2026-09-21): leave the scripts exactly as they are** — the D-text schedule feeds stay in use, and no script was changed. The only carve-out is operational: when Claude runs the batch roster/schedule scans it excludes Little Rock (by removing `little_rock` from `MANUAL_SCHOOL_BASE_URLS` at runtime in a throwaway wrapper). The committed scripts themselves still contain Little Rock's URLs, so running them bare will fetch lrtrojans.com; use the webarchive/PDF route for that school instead.

---

## Starting a New NCAA Season (e.g. 2027) — checklist

Written 2026-10-01. The profile page decides **retired vs. active** from data, not from a list. Several steps have to happen for that to work, and the weekly NCAA pipeline (`scripts/pipeline.py ncaa 2027`) now runs most of them. Do these once, at the start of the season:

1. **Bump `DEFAULT_SEASON` in `scripts/pipeline.py`** to `"2027"`. Career linking, the search index, team profiles and leaderboards only run for `DEFAULT_SEASON`; on any other season they show as `[off]` (backfill protection).
2. **Make sure the 2027 rosters exist.** The pipeline's Get Teams → Season Scraper → Rebuild Official Roster Links steps write `mt/data/ncaa_men/2027/` and `mt/data/roster_links/`. Official rosters (see "Official Team Roster Scraping") make linking deterministic. Without them, linking falls back to same team + exact name.
3. **Run the pipeline.** These steps are in the NCAA run, in this order:
   - **Link Season into Careers** — `link_ncaa_season.py --season 2027 --anchor-season 2026`.
     - Returning wrestlers are added to their careers (same school by roster `player_id`, else by same-team exact name). The lookback is 5 seasons, so redshirt and injury gaps are covered.
     - Everyone else gets a new career.
     - **Transfers are never auto-linked.** They are printed and written to `data/career_linking_logs/ncaa_men_transfer_candidates_2027.json`.
     - Safe to re-run weekly: already-linked wrestlers are skipped, and wrestlers added to a roster mid-season get linked the next week.
   - **Build Wrestler Profiles** — 2027's profiles are built with the full `season_summary`. It also rewrites `data/wrestlers/available_seasons.json` from the season folders on disk, so 2027 becomes its top entry automatically.
   - **Refresh season_summary + Career Seasons Map** — `refresh_season_summary.py` patches `season_summary` on the 2015–2026 profiles of every career that just gained a 2027 season (only that key changes). Then `build_career_seasons.py` runs for the Compare tool. Note that it only writes profiles already committed to git, so the first week's 2027 ids appear after the next run following a commit.
   - **Build Search Index** — all seasons by default.
4. **Review the flagged transfers** whenever the link step lists any:
   - run `.venv/bin/python scripts/careers/review_ncaa_transfer_candidates.py --season 2027`; it classifies them as CONFIRMED / CONTRADICTED / UNKNOWN and prints a merge command for each CONFIRMED;
   - merge each real transfer with the steps in Known Gotcha 17 (merge, rebuild the affected profiles, refresh, search, reports).
5. **Smoke test, then push** (CLAUDE.md hard rule).

**How the profile picks its default view** (`pickInitialView` in `app.js`; full rules in the Wrestler Profile row under Pages):
- The "current season" is the top entry of `available_seasons.json`.
- A wrestler whose latest season in `season_summary` is older than that, opened on that latest season, is **retired** and opens on Career.
- A wrestler with a 2027 season in their career is **active** and opens on 2027. That includes a wrestler on a 2027 roster with 0 matches: a 0-match roster wrestler still gets a profile, and once linked, 2027 is in their `season_summary`.
- `view=career` / `view=season` in the URL override this. One-season wrestlers always show the season.

**What goes wrong if a step is skipped:**
- **Not linked:** a returning wrestler's 2027 profile stands alone, and their older profiles open on Career as if they had retired.
- **Linked but not refreshed:** opening an older season shows a season table without 2027, and the profile still treats them as retired. This is the stale-`season_summary` problem fixed for 3,884 profiles on 2026-10-01.
- **`DEFAULT_SEASON` not bumped:** the link step is `[off]` for 2027, so nothing links.

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
| `scripts/scraping/scrape_intermat_rankings.py` | Scrapes InterMat's current live rank snapshot to `data/{season}/intermat-preseason-rankings/{date}.json` (comparison only — see the source table above, does not touch `apply_flo_rankings.py`'s pipeline) |
| `scripts/rankings/correlate_intermat_rankings.py` | Matches the latest InterMat snapshot to tracked `wrestler_id`s, writes `{date}_matched.json` alongside it. Does NOT overwrite `rankings_{weight}.json` |
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
| `scripts/generate_search_index.py` | Builds `search_index.js` (Fuse.js data, ~4-5MB) — run: `-league ncaa -season 2026`. **Every season is the default since 2026-10-01** (`--all-seasons` is still accepted as a no-op; `--single-season` restricts to `-season` for testing only — its output must never be deployed). Before that change, forgetting `--all-seasons` silently dropped every graduated/historical wrestler (every past champion and All-American) from search; it happened once on 2026-10-01 and was caught before commit. NCAA wrestler entries carry a `priority` tier used by header.js's search ranking as a tiebreak over Fuse's fuzzy score: 0 = ever an NCAA D1 champion, 1 = ever an AA (top 8), 2 = active in the current season, 3 = everyone else (`rank` breaks ties within tier 2). Tiers 0/1 come from `data/ncaa-tourney-parsed/all_wrestlers.json` (built by `scripts/ncaa/parse_ncaa_results.py`, tournament results 2013-2026), matched by name only (added 2026-09-13 after search was surfacing obscure wrestlers ahead of Hodge winners/all-time greats). |
| `scripts/build_simple_leaderboards.py` | Builds stat leaderboard JSON (wins, pins, techs, majors) |
| `scripts/wrestlestat_ingest.py` | **Retired 2026-09-13, do not run.** Supplemental ingestion from WrestleStat — used once (2025-12-24) to fill gaps in TrackWrestling data. See Known Gotchas #6 for why it was retired. |
| `scripts/ncaa/lazarus_award.py` | Identifies and tracks Lazarus Award candidates |
| `scripts/scraping/scrape_flo_preseason_rankings.py` | Scrapes FloWrestling preseason/in-season rank snapshots |
| `scripts/analysis/build_rank_score_distributions.py` | Builds rank→score empirical distributions for team projections |
| `scripts/analysis/compute_team_seed_offsets.py` | Builds program-strength offsets (shrunk seed-relative over/underperformance) |
| `scripts/analysis/compute_individual_modifiers.py` | Builds upside-only track-record modifiers for top-3-ranked wrestlers |
| `scripts/analysis/simulate_team_scores.py` | Monte Carlo team championship odds simulation |
| `scripts/analysis/publish_team_odds_to_site.py` | Publishes team odds simulation output to the frontend data dir |
| `scripts/reports/build_transfer_dpg_report.py` | Builds one team's transfer-window report JSON; shared base module the other `scripts/reports/` scripts import |
| `scripts/reports/build_wrestler_view.py` | Builds one chart-ready JSON per career-linked wrestler (backfill or `--season`-scoped); also rebuilds `wrestler_index.json`, the reports hub's name-search index |
| `scripts/reports/build_career_seasons.py` | Builds `data/careers/career_seasons.json` (career → season wrestler_ids) for the Compare Wrestlers tool. Re-run after career linking or a new season's profiles are committed — see "Compare Wrestlers Tool" |
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
| `scripts/ncaa/poll_ncaa_d1_duals.py` | **Prototype, shelved** — lightweight nightly-poll supplement to `wrestle_scraper_raw_mt_locked.py` for detecting newly-completed D1 duals. Not yet part of the standard pipeline. See [NCAA Regular-Season Dual Poller](#ncaa-regular-season-dual-poller-prototype--shelved-2026-09-14) |

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

6. **WrestleStat ingestion is retired (2026-09-13) — do not re-run `wrestlestat_ingest.py`**: it was used once, on 2025-12-24, to speed-scrape recent duals from wrestlestat.com as a supplement to TrackWrestling. The merge step lived in `process_raw_matches_by_season.py` (`load_wrestlestat_matches()` + a `(date, weight, winner_id, loser_id)` dedup key against TrackWrestling), and normally skipped a WrestleStat match if TrackWrestling already had it. Of the 17 duals pulled that day, 8 got double-counted anyway — WrestleStat's site recorded those duals' dates **one calendar day later** than TrackWrestling did for the same bout, so the exact-date dedup key missed the match and both copies got written in under `event: "Dual Meet (WS-#####)"`, inflating win/loss records, DPG, and `relationships_*.json` H2H for every wrestler in those 8 duals (~50 raw entries / 46 true duplicates across Ohio State, Iowa State, Little Rock, Bucknell, Morgan State, Navy, American, CSU Bakersfield, Central Michigan, Penn, and Virginia — all from the 2025-12-20–12-22 weekend). Fixed 2026-09-13: the 46 duplicate entries were removed from `mt/processed_data/ncaa_men/2026/`, the 2 bouts WrestleStat had genuinely caught that TrackWrestling's own scrape missed (Navy's Danny Wask over Morgan State's Kyle Grey, 12/20; Penn's CJ Composto over Virginia's Gable Porter, 12/22) were hand-added directly into `mt/data_alias/ncaa_men/2026/` in normal TrackWrestling format so they survive independently of WrestleStat, `data/raw/wrestlestat_duals/` and `data/processed/wrestlestat/` were deleted, and the WrestleStat merge code was stripped out of `process_raw_matches_by_season.py` entirely (TrackWrestling is once again the sole NCAA match source). If WrestleStat speed-scraping is ever revived, any re-implementation needs a date-tolerant (not exact-match) dedup key.

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

18. **Profile DPG goes stale when Mat Value is recomputed without rebuilding profiles (found + fixed 2026-10-01)**: each season profile stores its own copy of DPG (`metrics.mat_value.mv_avg`, the DPG ranks, and every match's `mv_impact`), and so do `data/p4p/{season}.json` (via `build_p4p_rankings.py`, which reads the profiles) and `data/public_rankings/{season}/*.json` (`mv.value` / `mv.weight_rank`). `mat_value_2026.json` was recomputed on 2026-09-13 after the 2026 profiles were built, so 2,127 of 2,288 profiles showed an older DPG on the profile card than the leaderboard, percentile bar and reports (which read `mat_value_{season}.json` directly) — 415 off by more than 0.1. Fixed by `build_wrestler_profiles.py -season 2026` (verified: only DPG fields and `profile_generated_at` changed, 0 mismatches after) and `build_p4p_rankings.py` (only `dpg` changed). The 2026 `public_rankings` files were patched in place (only `mv.value`/`mv.weight_rank`) rather than regenerated, because `generate_public_rankings.py` now produces the post-2026-09-09 ranking methodology's ranks and records, which would have changed the page's rankings too — decide separately whether to regenerate them. Not refreshed: 2026 xTP files (the bracket engine takes DPG as an input). **Rule: after any Mat Value recompute, rebuild that season's profiles, then the P4P feed.** Check: compare each profile's `metrics.mat_value.mv_avg` with `mat_value_{season}.json` (2024 and 2025 match exactly).
17. **Merging two NCAA careers for one wrestler (checklist, first done 2026-10-01 for Mike/Michael Caliendo III, NDSU → Iowa)**: a name change plus a transfer can leave one wrestler as two careers (two search results). Confirm it's one person (the new roster's `previous_school`, same hometown / high school / weight), then: (1) `scripts/careers/merge_careers.py --keep <current career> --merge <old> --gender ncaa_men --yes`; (2) `scripts/rankings/refresh_season_summary.py --dry-run`, then without `--dry-run` — after the 2026-10-01 full refresh it should touch only that wrestler's profiles (if the dry run reports thousands, other profiles have gone stale again: check why before writing); (3) `scripts/reports/build_career_seasons.py` (compare tool; check only his career changed); (4) search index: `generate_search_index.py -league ncaa -season 2026` (all seasons by default since 2026-10-01; check the old career's entry is gone and the entry count is unchanged); (5) reports: delete `data/reports/wrestler_view/<old career>.json`, rebuild his view with `build_wrestler_view.build_wrestler_view()` + `write_search_index()`, and `build_team_roster_view.py --team <slug> --season <year>` for each team-season he's on. NCAA match rows carry no `opponent_career_id`, so opponents' files don't change. **Fixed 2026-10-01:** 3,884 NCAA profiles (2020–2025) carried stale copies of later seasons' `current_rank` (74 also a stale record) in `season_summary` — e.g. a 2025 page showed that wrestler's 2026 row at #122 while the 2026 page said #95. `refresh_season_summary.py` rewrote them (only `season_summary` changed, verified file by file), and the search index was rebuilt, refreshing 2,438 stale tiebreak ranks. Cause: the summary is a build-time snapshot; rerun `refresh_season_summary.py` after any season's ranks or records change.
16. **Team renames create duplicate team identities, with no equivalent of `apply_name_aliases.py` for teams (discovered 2026-09-13)**: University of Pennsylvania was scraped as team name/slug "Pennsylvania" through the 2025 season and "Penn" starting 2026 — both slugs have their own `data/teams/{slug}.json`, `team_metrics` entries, etc., as if they were different programs. `generate_search_index.py`'s NCAA team loader accumulates team slugs across every season (so old programs stay searchable), which surfaced "Pennsylvania" in search pointing at a team.html page with no current-season `team_metrics` entry — `team.js`'s `loadTeam()` did `metricsFile.teams.find(...)` with no null-check, so visiting it crashed with a raw JS property-access error shown as "Team Not Found." Fixed two ways: (1) `team.js` now throws a clean `No {SEASON} season data for this team.` message instead of crashing when a team has no current-season metrics entry (covers any future unnoticed rename, not just this one); (2) `generate_search_index.py` has a small `RETIRED_NCAA_TEAM_SLUGS` set (currently just `{"pennsylvania"}`) that's skipped when building the team search index, so the confirmed-duplicate old slug no longer shows up at all. This does NOT merge the two teams' historical data (2023-2025 rosters/stats still live under the "pennsylvania" slug and aren't reachable from the "penn" page) — that would need a team-level equivalent of `merge_careers.py`, not yet built. If another team rename shows up, add its old slug to `RETIRED_NCAA_TEAM_SLUGS`.

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
