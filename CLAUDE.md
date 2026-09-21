# KentuckyMat — Claude Code Reference

## Overview

This repo contains **two separate websites** that share a codebase and now both live on a single branch:

| Site | URL | Branch | Frontend Dir |
|---|---|---|---|
| KentuckyMat | kentuckymat.com | `main` | `frontend/hs-ky-ui/` |
| MatSavant | matsavant.com | `main` | `frontend/wrestledata-ui/` |

**All active development is on `main`.** The `hsky-dev` branch is retired/no longer used — do not check it out or treat it as a deploy target. The two sites still share this one branch/codebase; don't mix unrelated changes between their frontend dirs in a single commit.

**MatSavant full reference:** See [`docs/matsavant.md`](docs/matsavant.md) for the complete MatSavant/NCAA pipeline, page inventory, and stat calculation formulas (TPAR, SI+, DF+, PE+, DI+, xTP, bonus EV).

**Architecture: 100% static.** No backend, no API, no DynamoDB. Everything is pre-computed JSON files served to plain HTML/JS pages. The DynamoDB/Heroku/`api/` infrastructure is legacy and unused — do not reference it as active.

---

## Hard Rules

- **NEVER push to any git branch** without explicit user approval.
- Everything else is recoverable (user backs up regularly).

---

## Documentation Standard

When a script's data source, storage location, or a piece of methodology isn't already documented here or in [`docs/matsavant.md`](docs/matsavant.md), **document it as part of that work** — don't let it live only inside the script. This repo has multiple pipeline stages that compute similar-looking values (e.g. three different NCAA "rank" sources existed before this rule was written), and undocumented sources are exactly how a new script ends up quietly reading the wrong one. If you're about to write a new script and can't find its data source's origin/location already written down, that's a signal to go find and document it, not just re-derive it from code and move on.

Example: `docs/matsavant.md`'s "NCAA Ranking Methodology (Source of Truth)" section — written 2026-09-09 after discovering `build_wrestler_profiles.py`, `compute_all_mat_values.py`, and the transfer/roster report pipeline had each independently ended up reading a different, undocumented rank source, with real user-facing wrong-rank bugs as a result.

---

## Repository Structure

```
wrestledata-simple/
├── data/                          # Raw + source-of-truth data (NOT public)
│   ├── careers/                   # Master career records
│   │   ├── career_000001.json     # Boys (flat, no subdir)
│   │   └── girls/                 # Girls (in subdir)
│   │       └── career_000001.json
│   ├── season_accomplishments/    # Authoritative wrestler data per season
│   │   ├── boys/{season}/season_accomplishments.json
│   │   └── girls/{season}/season_accomplishments.json
│   ├── hs_ky_boys/                # Boys raw scraped data (2013–2026)
│   ├── hs_ky_girls/               # Girls raw scraped data (2024–2026)
│   ├── career_linking_logs/       # Audit logs from career linking
│   ├── recruiting/                # Recruiting commitments + colleges
│   │   ├── boys/commitments.json
│   │   └── girls/commitments.json
│   └── team_lists/                # Team lists by season
├── mt/                            # Intermediate processed data (NOT public)
│   ├── data/hs_ky_{gender}/{season}/     # Scraped + processed match data
│   ├── rankings_data/hs_ky_{gender}/{season}/  # Rankings outputs
│   ├── processed_data/hs_ky_{gender}/{season}/ # Normalized match data
│   ├── elo_ratings/{gender}/{season}/    # ELO ratings
│   ├── graphics/{season}/               # PDF/SVG/JPG ranking releases
│   └── locks/                           # Scraper concurrency locks
├── frontend/hs-ky-ui/public/      # PUBLIC site files (kentuckymat.com)
│   ├── *.html                     # All page shells
│   ├── *.js                       # Page logic
│   ├── hs_config.js               # Shared config + utilities (incl. setMetaDescription)
│   ├── app.js                     # Core wrestler/career profile logic
│   ├── team.js                    # Team profile logic
│   ├── sitemap.xml                # Regenerate with scripts/generate_sitemap.py
│   ├── robots.txt
│   └── data/                      # JSON data consumed by the frontend
│       ├── careers/boys/          # Built by build_career_profiles.py
│       ├── careers/girls/
│       ├── wrestlers/{gender}/{season}/by_id/
│       ├── rankings/{gender}/{season}/    # Archive drops by date
│       ├── teams/{gender}/{season}/
│       ├── leaderboards/{gender}/{season}/
│       ├── recruiting/{gender}/
│       ├── mat_value/{gender}/{season}/
│       ├── xtp/{gender}/{season}/
│       └── ...
├── scripts/                       # All pipeline scripts (see below)
├── xtp/                           # XTP calculation engine
└── .venv/                         # Python virtualenv (use .venv/bin/python)
```

---

## Data Flow Philosophy

```
TrackWrestling (scrape)
       ↓
mt/data/hs_ky_{gender}/{season}/        ← raw scraped data
       ↓
mt/processed_data/ + mt/rankings_data/  ← processed, ranked
       ↓
frontend/hs-ky-ui/public/data/          ← final JSON for the website
```

Scripts do all processing locally in `mt/` and only write final, website-ready JSON to `frontend/hs-ky-ui/public/data/`. The frontend never hits an API — it fetches these static JSON files directly.

---

## Gender & Season Conventions

| | Boys | Girls |
|---|---|---|
| Data history | 2013–present | 2024–present (sanctioned in KY in 2024) |
| Career files | `data/careers/career_*.json` (flat) | `data/careers/girls/career_*.json` (subdir) |
| Weight classes | 106,113,120,126,132,138,144,150,157,165,175,190,215,285 | 100,107,114,120,126,132,138,145,152,165,185,235 |
| Rankings schedule | Thursdays (weekly during season) | Wednesdays (weekly during season) |

Both genders use identical scripts — gender is always a `--gender boys/girls` parameter.

**Path pattern used throughout:**
```
mt/rankings_data/hs_ky_{gender}/{season}/
mt/processed_data/hs_ky_{gender}/{season}/
data/season_accomplishments/{gender}/{season}/
frontend/hs-ky-ui/public/data/careers/{gender}/
```

---

## Career System

### Two-tier structure

**Backend career file** (`data/careers/[girls/]career_XXXXXX.json`):
```json
{
  "career_id": "career_000042",
  "canonical_name": "Micah Thompson",
  "name_norm": "micah thompson",
  "created_from_season": 2025,
  "seasons": {
    "2025": "30029272132",
    "2024": "24694064132",
    "2026": "35233660132"
  },
  "notes": null
}
```
Seasons is a **dict** keyed by year string → TrackWrestling wrestler ID.

**Frontend career file** (`frontend/hs-ky-ui/public/data/careers/{gender}/career_XXXXXX.json`):
Enriched version with `career_record` object and `seasons` as an **array** of objects, each containing full match history. Built by `build_career_profiles.py`.

### Career workflow
1. `create_careers_from_season.py` — creates initial career files from a season
2. `link_season_interactive.py` — links prior/new seasons to existing careers
3. `merge_careers.py` — merges duplicate careers (e.g. name changed between seasons)
4. `build_career_profiles.py --gender {gender}` — builds enriched frontend profiles

### Common career gotcha
If a wrestler's name changed between seasons (e.g. "Camila Velasco Pillacios" → "Camila Velasco"), the linker may create two separate career files instead of linking them. Use `merge_careers.py` to fix. Always keep the career ID that the wrestler's current season profile links to.

---

## Frontend URL Patterns

| Page | URL Pattern |
|---|---|
| Career profile | `wrestler.html?gender={gender}&career_id=career_XXXXXX` |
| Season profile | `wrestler.html?gender={gender}&id={wrestler_id}&season={year}` |
| Team profile | `team.html?gender={gender}&team={team_slug}&season={year}` |
| Rankings | `rankings.html?gender={gender}` |
| Leaderboards | `leaderboards.html?gender={gender}` |
| Recruiting | `recruiting.html?gender={gender}` |
| Compare wrestlers | `compare.html?gender={gender}&a=career_XXXXXX&b=career_XXXXXX[&season={year}]` |

Team slugs are lowercase, underscored (e.g. `boyle_county`, `anderson_county`). Built by `teamNameToSlug()` in `app.js`.

---

## Weekly Pipeline (Full Order)

Run from repo root with `.venv/bin/python`. Both genders run for most steps.

### Data Scraping

```bash
# Get teams
.venv/bin/python scripts/scrape_ncaa_d1_teams.py -league=hs -gender=boys -state=KY -season 2026
.venv/bin/python scripts/scrape_ncaa_d1_teams.py -league=hs -gender=girls -state=KY -season 2026

# Scrape match data from TrackWrestling
.venv/bin/python wrestle_scraper_raw_mt_locked.py -league hs -gender boys -state KY -season 2026 -headless
.venv/bin/python wrestle_scraper_raw_mt_locked.py -league hs -gender girls -state KY -season 2026 -headless

# Apply name aliases
.venv/bin/python scripts/apply_name_aliases.py 2026 -league hs -state KY -gender boys
.venv/bin/python scripts/apply_name_aliases.py 2026 -league hs -state KY -gender girls

# Parse and verify data
.venv/bin/python scripts/process_raw_matches_by_season.py -season 2026 -league hs -state KY -gender boys
.venv/bin/python scripts/process_raw_matches_by_season.py -season 2026 -league hs -state KY -gender girls
```

### Rankings Processing

```bash
# Load data (also removes APPROVED duplicate events by default and prints a NOTICE if new unapproved ones exist —
# if it does: run scripts/rankings/audit_duplicate_events.py, approve, then re-run this step. See Known Gotcha 9.)
.venv/bin/python scripts/rankings/load_data.py -season 2026 -save -league hs -state KY -gender boys
.venv/bin/python scripts/rankings/load_data.py -season 2026 -save -league hs -state KY -gender girls

# Build relationships (H2H)
.venv/bin/python scripts/rankings/build_relationships.py -season 2026 -save -league hs -state KY -gender boys
.venv/bin/python scripts/rankings/build_relationships.py -season 2026 -save -league hs -state KY -gender girls

# Ranking bands
.venv/bin/python scripts/rankings/ranking_bands.py -season 2026 -league hs -state KY -gender boys
.venv/bin/python scripts/rankings/ranking_bands.py -season 2026 -league hs -state KY -gender girls

# Rankings matrix — save new ranking order as output after running
.venv/bin/python scripts/rankings/generate_matrix.py -season 2026 -league hs -state KY -gender boys
.venv/bin/python scripts/rankings/generate_matrix.py -season 2026 -league hs -state KY -gender girls
```

### Overrides (only when needed)

```bash
.venv/bin/python scripts/rankings/manage_weight_overrides.py -season 2026 -league hs -state KY -gender boys
.venv/bin/python scripts/rankings/manage_weight_overrides.py -season 2026 -league hs -state KY -gender girls
.venv/bin/python scripts/rankings/manage_match_overrides_hs.py -season 2026 -state KY -gender boys
.venv/bin/python scripts/rankings/manage_placement_notes.py -season 2026 -league hs -state KY -gender boys
.venv/bin/python scripts/rankings/manage_placement_notes.py -season 2026 -league hs -state KY -gender girls
```

### Building the Website

```bash
# Step 1: Starter rankings
.venv/bin/python scripts/rankings/build_starter_rankings.py -season 2026 -league hs -state KY

# Step 1.2: ELO ratings (hybrid ranks for duals)
.venv/bin/python scripts/rankings/calculate_elo_ratings.py -season 2026 --gender boys
.venv/bin/python scripts/rankings/calculate_elo_ratings.py -season 2026 --gender girls

# Step 2: Wrestler profiles (HS: bouts come from the canonical bout list — Known Gotcha 15; check with scripts/records/verify_consistency.py)
.venv/bin/python scripts/rankings/build_wrestler_profiles.py -season 2026 -league hs -state KY -gender boys
.venv/bin/python scripts/rankings/build_wrestler_profiles.py -season 2026 -league hs -state KY -gender girls

# Step 2.1: Search index
.venv/bin/python scripts/generate_search_index.py -league hs -gender both -season 2026

# Step 2.5: Bonus data
.venv/bin/python scripts/bonus/compute_all_top33_bonus.py --season 2026 -league hs -state KY

# Step 2.6: XTP
.venv/bin/python scripts/xtp/run_team_xtp.py --season 2026 --rebuild-weights --limit 25 -league hs -state KY

# Step 3: Team profiles
.venv/bin/python scripts/teams/build_team_profiles.py --season 2026 -league hs -state KY

# Step 4: Team metrics
.venv/bin/python scripts/team_metrics/build_team_metrics.py --season 2026 -league hs -state KY

# Step 5: Dual predictor data
.venv/bin/python scripts/rankings/generate_dual_predictor_data.py -season 2026 -gender boys
.venv/bin/python scripts/rankings/generate_dual_predictor_data.py -season 2026 -gender girls

# Step 6: Season accomplishments
python3 scripts/season_accomplishments/generate_season_accomplishments.py --season 2026 --gender boys
python3 scripts/season_accomplishments/generate_season_accomplishments.py --season 2026 --gender girls

# Step 7: Leaderboards (wins/pins/techs only — career wins built in step 9.2)
.venv/bin/python scripts/build_leaderboards.py -season 2026

# Step 8: Official rankings drop (update date each week)
.venv/bin/python scripts/rankings/create_rankings_release.py -season 2026 -gender boys -drop-id 2026-mm-dd --archive --pdf --jpg
.venv/bin/python scripts/rankings/create_rankings_release.py -season 2026 -gender girls -drop-id 2026-mm-dd --archive --pdf --jpg

# Step 8.2: Open release notes
python scripts/rankings/open_notes_in_macdown.py -gender boys -season 2026 -drop-id 2026-mm-dd
python scripts/rankings/open_notes_in_macdown.py -gender girls -season 2026 -drop-id 2026-mm-dd

# Step 9.1: Career profiles
.venv/bin/python scripts/rankings/build_career_profiles.py --gender boys
.venv/bin/python scripts/rankings/build_career_profiles.py --gender girls

# Step 9.2: Leaderboards with career wins (reads career profiles built in 9.1)
.venv/bin/python scripts/build_leaderboards.py -season 2026 --all-time-career-wins

# Step 9.3: Sitemap
python scripts/generate_sitemap.py

# Step 9.4: Recruiting data
python scripts/recruiting/build_recruiting_data.py --gender boys
python scripts/recruiting/build_recruiting_data.py --gender girls
```

### Post-Season / Event-Driven (run only when needed)

```bash
# Match highlights graphic (update dates)
.venv/bin/python scripts/rankings/generate_match_highlights.py --start-date 2026-01-06 --end-date 2026-01-14 --season 2026 --gender boys
.venv/bin/python scripts/rankings/generate_match_highlights.py --start-date 2026-01-06 --end-date 2026-01-14 --season 2026 --gender girls

# Add/list/delete manual matches
python scripts/rankings/manage_manual_matches.py -season 2026 -action add -league hs -state ky -gender boys

# Merge duplicate careers
python3 scripts/careers/merge_careers.py --keep career_000025 --merge career_003042 --name "Name" --gender boys

# Link season careers (interactive)
python scripts/careers/link_season_interactive.py --season 2026 --gender boys
python scripts/careers/link_season_interactive.py --season 2026 --gender girls

# Manage recruiting commitments
python scripts/recruiting/manage_commitments.py --gender boys
python scripts/recruiting/manage_commitments.py --gender girls

# Region/state graphics
.venv/bin/python scripts/rankings/calculate_region_points.py --season 2026 --gender boys --generate-graphic
.venv/bin/python scripts/xtp/run_regional_xtp.py --season 2026 -gender boys --export-graphics
.venv/bin/python scripts/regions/run_regional_results.py --season 2026
.venv/bin/python scripts/state/run_state_predictions.py --season 2026 -gender boys
```

---

## Key Scripts Reference

| Script | Purpose |
|---|---|
| `wrestle_scraper_raw_mt_locked.py` | Scrapes TrackWrestling match data (primary data source) |
| `scripts/apply_name_aliases.py` | Normalizes wrestler name variants before processing |
| `scripts/process_raw_matches_by_season.py` | Parses + validates raw scraped data |
| `scripts/rankings/load_data.py` | Loads processed data into rankings system |
| `scripts/rankings/build_relationships.py` | Builds head-to-head relationship data |
| `scripts/rankings/generate_matrix.py` | Generates rankings matrix (save output as new rank order) |
| `scripts/rankings/build_starter_rankings.py` | Creates starter-only rankings (must run before profiles) |
| `scripts/rankings/calculate_elo_ratings.py` | ELO hybrid ranks for dual predictions |
| `scripts/rankings/build_wrestler_profiles.py` | Builds wrestler JSON profiles for frontend |
| `scripts/rankings/build_career_profiles.py` | Builds enriched career profiles for frontend |
| `scripts/rankings/create_rankings_release.py` | Official weekly drop (archive + PDF + JPG) |
| `scripts/teams/build_team_profiles.py` | Builds team JSON profiles for frontend |
| `scripts/team_metrics/build_team_metrics.py` | Computes team strength metrics |
| `scripts/bonus/compute_all_top33_bonus.py` | Adds bonus data to wrestler profiles |
| `scripts/xtp/run_team_xtp.py` | XTP (extra tournament points) calculations |
| `scripts/build_leaderboards.py` | Generates stat leaderboards + career wins |
| `scripts/generate_search_index.py` | Builds search_index.js (~6MB Fuse.js data) |
| `scripts/generate_sitemap.py` | Regenerates sitemap.xml (run after career/team changes) |
| `scripts/rankings/audit_duplicate_events.py` | **Read-only** audit for duplicated events (see Known Gotcha 9); writes confirmed/review/rejected CSVs to `mt/audits/duplicate_events/` |
| `scripts/rankings/duplicate_events.py` | Library behind the audit and `load_data.py`'s duplicate-event removal (default-on for HS): clone-event detection, keep rule, approved-decisions file, removal (see Known Gotcha 9) |
| `scripts/rankings/apply_duplicate_events_inplace.py` | Applies the approved removals directly to already-saved `weight_class_*.json` (use for OLD seasons instead of re-running `load_data.py`; see Known Gotcha 9) |
| `scripts/season_accomplishments/generate_season_accomplishments.py` | Generates season accomplishment data |
| `scripts/careers/create_careers_from_season.py` | Creates initial career files from a season |
| `scripts/careers/link_season_interactive.py` | Interactively links seasons to careers |
| `scripts/careers/merge_careers.py` | Merges duplicate career records |
| `scripts/careers/audit_unlinked_seasons.py` | **Read-only** audit: wrestler-seasons WITH matches that no career file links to (AUTO / REVIEW / NONE); can write an AUTO plan (see Known Gotcha 13) |
| `scripts/records/canonical_bouts.py` | **The one place season W-L is decided** (canonical bout list per season; rules in its header; used by accomplishments + profile builder — Known Gotcha 15). Helpers: `verify_consistency.py`, `compare_season_records.py`, `show_wrestler.py`, `career_wins_preview.py` |
| `scripts/careers/link_seasons_batch.py` | Applies an explicit list of `season -> season_wrestler_id` links to existing careers (non-interactive); validates, logs to `data/career_linking_logs/batch_links_log.json` |
| `scripts/recruiting/build_recruiting_data.py` | Builds recruiting page data |
| `scripts/recruiting/manage_commitments.py` | Interactive CLI to manage college commitments |

---

## Frontend JS Architecture

All pages share `hs_config.js` which is loaded first and provides:
- `HS_CONFIG` — weight classes, default season/gender, data paths
- `getGenderFromURL()`, `getSeasonFromURL()`, `getQueryParam()`
- `buildPageURL()` — builds `page.html?gender=X&...` links
- `setMetaDescription()` — sets/updates meta description tag for SEO

**Key JS files per page:**

| Page | JS File | Notes |
|---|---|---|
| Wrestler/Career profile | `app.js` | Sets `document.title` and meta description dynamically |
| Team profile | `team.js` | Sets `document.title` and meta description dynamically |
| Rankings | `rankings.js` | Sets `document.title` and meta description in `initRankings()` |
| Leaderboards | `leaderboards.js` | Sets `document.title` and meta description in `init()` |
| Recruiting | `recruiting.js` | Uses `GENDER` const — always pass `&gender=` in links |
| Compare wrestlers | `compare.js` + `compare_core.js` | Two-wrestler picker → head-to-head + common opponents, computed client-side from the two career files (no extra data build). See "Compare page" below |

**Compare page (`compare.html`, KentuckyMat only so far):**
- `compare_core.js` is pure/DOM-free (`window.CompareCore`) so it can be reused for MatSavant; `compare.js` is UI, URL state and fetching. The picker is page-local (the header search in `header.js` is a closure and isn't reusable); it reads `career_id` out of each `search_index.js` record's `url`. A "Compare ⇄" pill on career profiles (`app.js`) links here with `a=` prefilled.
- **Opponent identity** (how two wrestlers' opponents are matched across seasons): `opponent_career_id` when present; otherwise normalized `name|team` (a name|team that resolves to a career_id anywhere in either file uses that career key). `opponent_id` is season-specific and can't match across seasons. Skipped: `opponent_name == "Unknown"` (many opponents share one `OUTSTATE_*` id), forfeits (`FF`/`MFF`/`FOR*`), injury defaults/`NC` for common opponents. Head-to-head is the union of A's matches vs B and B's matches vs A (flipped), de-duplicated, also matching B's season `wrestler_id`s. About 22–27% of matches have no `opponent_career_id`, so the name+team fallback matters.
- Boys and girls are compared separately (career IDs overlap between the two dirs — always key on `gender + career_id`). A wrestler can have both a boys and a girls career (e.g. a girl wrestling on the boys team).
- **MatSavant follow-up (not done):** NCAA `opponent_career_id` is always null today (`build_wrestler_profiles.py` passes `career_lookup=None`; career links exist only in backend `data/careers/ncaa_men/`). It needs that populated from a `season_wrestler_id → career_id` lookup before cross-season matching will work there.

**SEO title templates:**
- Boys career: `{Name} | Kentucky High School Wrestling | {Team} | KentuckyMat`
- Girls career: `{Name} | Kentucky Girls High School Wrestling | {Team} | KentuckyMat`
- Team: `{Team} Wrestling {Season} | Kentucky [Girls] High School | KentuckyMat`
- Rankings: `{Season} Kentucky [Boys/Girls] High School Wrestling Rankings | KentuckyMat`

---

## Standalone Tools (not part of either website)

- **Team record-book leaderboards** — `scripts/team_records/`. Reads the team's season-stats Google Sheet
  (season tabs like `2024-2025`) and writes `scripts/team_records/output/leaderboards.html` (Boys/Girls × Pins/Wins/Takedowns ×
  Career/Best Seasons). Run: `.venv/bin/python scripts/team_records/build_team_leaderboards.py`. Name spelling fixes live in
  `scripts/team_records/name_aliases.json`. Touches no website data. Details, judgment calls and known sheet
  discrepancies: [`scripts/team_records/README.md`](scripts/team_records/README.md).

---

## Known Gotchas

1. **Career files path inconsistency**: Boys careers are flat in `data/careers/career_*.json`; girls are in `data/careers/girls/career_*.json`. Scripts that handle both must check for the gender subdir. See `build_leaderboards.py` for the pattern.

2. **Career seasons format**: Backend career files use a **dict** (`{"2026": "id"}`). Frontend career files use an **array** of season objects. Don't confuse them.

3. **`gender=boys` hardcoding**: Several JS files were historically hardcoded to `gender=boys` in links. Always use the `GENDER` or `gender` variable instead. Check `recruiting.js` as a reference.

4. **`setMetaDescription` availability**: This helper lives in `hs_config.js`. It's available on all pages. Do NOT redefine it in other JS files.

5. **`build_starter_rankings.py` must run before `build_wrestler_profiles.py`**: Profiles use starter rankings for opponent rank determination.

6. **`defaultSeason` in `hs_config.js`**: Must be updated to the current season each year.

7. **Name changes break career linking**: If a wrestler's name changed between seasons, two separate career files will be created. Use `merge_careers.py` to fix — always keep the career ID the current season profile already points to.

8. **Sitemap uses `TODAY` as `lastmod`**: This is correct behavior for a statically-generated site. Regenerate sitemap whenever career or team files change.

9. **Duplicated events (same bout listed twice under different dates)**: TrackWrestling sometimes lists one tournament/dual twice — different names and/or dates (e.g. `HATFIELD-MCCOY 32` 12/29 and `Boys Hatfield McCoy 32 2025` 12/30, or two teams dating a dual a day apart). The scraper records both faithfully, and every de-dupe key in `load_data.py` (`match_identity_key`, `dedupe_matches_across_weights`) and `build_wrestler_profiles.py` (`_match_identity_key`, `build_match_list`) includes the exact date, so a 1+ day mismatch slips through: the bout shows twice on both wrestlers' pages and inflates records/stats. Same-date duplicates are already collapsed. Raw scraped files stay untouched. Two scripts: `scripts/rankings/audit_duplicate_events.py` (**read-only** audit → confirmed/review/rejected CSVs) and `scripts/rankings/duplicate_events.py` (library: detection + applying). **Removal only ever applies human-approved event pairs**, listed in `data/duplicate_events/approved_duplicate_events.json` (source-of-truth data; the rules are never re-run blindly on new data). Workflow: run the audit → skim `event_pairs_review.csv`/`bouts_review.csv` → approve with `audit_duplicate_events.py --approve-confirmed` (all confirmed) and/or `--approve-ids 12,40` (specific pair_ids from that run, review pairs allowed, rejected refused) → re-run Load Data. **Removal is ON by default for HS**: `load_data.py ... -save` applies the approved list automatically (opt out with `--no-dedupe-events`; `--approved-events-file` overrides the file for testing), and then prints a `NOTICE` if any *new*, not-yet-approved likely duplicates are still in that season. `scripts/pipeline.py` (HS only) has an **"Audit Duplicate Events"** step right after "Load Data for Ranking" that runs the audit for the season, so the weekly flow surfaces new duplicates without anyone having to remember: if the audit lists confirmed/review pairs, approve them and re-run Load Data. Nothing is removed unless a pair is in the approved file, so an un-reviewed week is simply unchanged (never silently deleted). The removal runs inside `save_loaded_data` after `dedupe_matches_across_weights` and before match overrides, drops the extra copy of each approved bout from every weight-class list, decrements the affected wrestlers' `wins`/`losses`/`matches_count`, fixes `last_match_date` only if a dropped copy was the latest, and writes `mt/audits/duplicate_events/applied_{gender}_{season}.csv`. After it runs, the duplicates no longer exist in the saved data, so the audit stops listing them. **Old seasons — do NOT regenerate with `load_data.py`**: historical seasons have no `rankings_*.json`, so `load_data` treats every wrestler as unranked and auto-applies weight changes, which silently overwrote two hand-settled weight decisions in 2014 during testing (and `weight_confirmation.json` is rewritten). For a past season use `scripts/rankings/apply_duplicate_events_inplace.py -gender boys -season N` (or `--all-seasons`; `--dry-run` first) — it edits only the approved bouts in the saved `weight_class_*.json`/`summary.json` and is idempotent (re-runs warn "no longer detected", which is expected). **Applied 2026-09-20**: 85 approved boys pairs (2013–2026) → 1,194 duplicate bouts removed in place (2014 largest: 579; 2026: 74); girls had none. Girls are audited by the same tools when pairs appear. Rebuilt afterwards for boys 2013–2026: relationships (`mt/`), ELO (2020, 2026), `data/season_accomplishments` records, wrestler profiles, career profiles, leaderboards (2013/14/17/18/26 + all-time career wins), public matrix 2026, search index. 2026 team profiles, team metrics and xTP were rebuilt after the team-builder fix (Gotcha 11). NOT rebuilt: public rankings/rankings_full snapshots and rosters/dual standings (older snapshots — refresh via the weekly pipeline). **Two more consumers read RAW `mt/processed_data` (not the weight-class files) and apply the same approved removals themselves** via `duplicate_events.processed_drop_idents()`/`match_ident()`: `calculate_elo_ratings.py` (prints "Dropped N match rows … from approved duplicate events") and `season_accomplishments/generate_season_accomplishments.py` (its per-wrestler `record` W-L is what profiles show as the season record and what career records sum — so without this the site would still show inflated records). Each wrestler's own raw file may hold one or both copies of a duplicated bout (Matney's file had both, his opponent's only the survivor), so record fixes are per-file, not per-bout. For PAST seasons don't regenerate accomplishments (it re-runs hand-matched state/regional placements); use `generate_season_accomplishments.py --season N --gender boys --records-only [--dry-run]`, which keeps the existing file and rewrites only each wrestler's `record` (`--no-dedupe-events` should report 0 changes = no drift). Downstream steps (`build_relationships`/matrix, ELO, profiles, careers, leaderboards, bonus/xTP) read the saved files and must be rebuilt for affected seasons before the website reflects the removal.
   - Unit of comparison: a *bout* = unordered wrestler pair + result type (score kept, time dropped). Two copies are the **same bout** if their times are compatible: identical (incl. identical real times like `Fall 3:52`) = real "proof"; one side the **`0:00` placeholder** (the only placeholder) = compatible but weak; **both real and different** (`Fall 3:05` vs `Fall 1:17`) = a *conflict* = two different results = **never a duplicate** (TJ's rule). Forfeits/byes ignored. Reads the merged `mt/rankings_data/hs_ky_{gender}/{season}/weight_class_*.json` (run `load_data.py --save` first if stale).
   - Two events (name + date) are compared when they share bouts and are ≤3 days apart (names may differ entirely), or 4–14 days apart with similar names. Outcome, in order: **rejected** (<2 compatible shared bouts, or conflicts ≥ matches); **confirmed** — (a) ≥3 proof bouts (≥2 if event names are similar) with few conflicts, e.g. 2014 `KHSAA Region 6` listed 2/8 and 2/15 with 94 identical scores/times, (b) **mirrored dual**: `vs. Team A` + `vs. Team B`, back-to-back days, ≥3 shared bouts, none conflicting, and every shared bout is a Team A wrestler vs a Team B wrestler (one team entered the dual a day off — TJ's 2-day-event theory), (c) **similar names, back-to-back days, ≥3 shared bouts, none conflicting** (0:00 placeholders allowed; never when one event is a dual and the other a tournament); (d) **large back-to-back**: same day or consecutive days, ≥5 shared bouts including ≥1 identical non-fall result (Dec/MD/TF), none conflicting — names may differ and a dual-vs-tournament label mismatch is overridden (that much identical non-fall overlap can't be coincidence; e.g. `Fern Creek Invitational` vs `vs. Bullitt Central`); **rejected** (weak evidence only) — one event is a dual and the other a tournament, or the events are different and ≥2 days apart (e.g. `Lady Bruin Invitational` vs `vs. North Hardin` 3 days apart); **review** — everything else (mostly `0:00`-only overlap, 1 proof bout between differently-named events, proof bouts alongside conflicts, plus dual-vs-tournament pairs on back-to-back days with ≥4 shared non-conflicting bouts, which could be a dual-format tournament like Fern Creek Gladiator listed both ways). Only the review files need a human look.
   - Why event-level and not per-match: `Fall 0:00` placeholders repeat constantly, so single matches can't be safely compared; a clone event is proven by many identical bouts. Name similarity alone misses many (`WCI`/`Woodford Co Invitational`, `vs. Cooper`/`vs. Boone County` = one dual seen from each team's side).
   - First run 2026-09-20 on all HS data (≈325k merged bouts): 85 confirmed pairs (~1,190 rows, 0.37%), 417 rejected, 73 left to review (~340 rows). Copy to keep, in order: (1) the event name the site's placement logic recognises (`KHSAA Region 1-8`, `KHSAA Final Round State Championship` — `generate_season_accomplishments.py` matches those exact patterns, so the wrong survivor would silently change regional/state placement), (2) the more specific result (real time over `0:00`), (3) the larger event listing, (4) the earlier date. The survivor's date can differ from the dropped copy's by 1–14 days. Pair IDs are regenerated each run.


10. **ELO output location (HS)**: `calculate_elo_ratings.py` writes HS output to `mt/elo_ratings/{boys|girls}/{season}/elo_ratings.json` (fixed 2026-09-20 — since 2026-06 it wrote to `hs_ky_{gender}/`, a directory nothing reads, so the pipeline's "Hybrid Ranks (ELO)" step never reached profiles). Readers: `build_wrestler_profiles.py` (`current_rank` hybrid), `generate_dual_predictor_data.py`, `create_rankings_release.py`, `generate_elo_report.py`. NCAA stays in `mt/elo_ratings/ncaa_men/{season}/`. `mt/elo_ratings/` is tracked in git.

11. **Several HS pipeline steps regressed when the NCAA side was reworked (found 2026-09-20, while rebuilding after the duplicate-event cleanup) — status:**
    - **Team profiles** (`teams/build_team_profiles.py -league hs`) — FIXED. `resolve_starters_for_team` had been rewritten for NCAA (needs `flo_ranked`/`match_count`/`last_match_date`, which HS rankings entries don't have) so nearly every HS team came out with "0 starters". HS now uses `resolve_starters_for_team_hs` (original rank + `is_starter` logic); NCAA logic untouched. Both team builders also collapse team-list entries that slugify to the same id (the scraped list has `"Waggener "` / `"Frederick Douglass "` trailing-space duplicates).
    - **Team list scraper** (`scrape_ncaa_d1_teams.py`) — FIXED: (a) HS now writes the flat `data/team_lists/hs_ky_{gender}/teams.json` that every HS reader uses (it had switched to `{season}/teams.json`, which nothing reads); (b) a re-scrape that returns no `region` no longer wipes known regions (TrackWrestling only lists "Region N" in-season; the April scrape had wiped 139 boys / 107 girls regions, so team pages fell back to "Kentucky High School" and `calculate_region_points.py` lost its mapping). Regions were restored from the 2026-02-02 list (`a8a9451566`).
    - **xTP** (`xtp/run_team_xtp.py -league hs`) — FIXED: crashed on the documented weekly command (`--rankings-dir` default is `None`; HS branch compared it to a stale string). NOTE xTP takes `top33_bonus_ev_shrunk` from each wrestler PROFILE's `bonus` block (`compute_all_top33_bonus.py` writes it), so the pipeline order bonus → xTP → team profiles matters; the committed xtp files had been built without bonus (`bonus_ev = 0.0`) while the committed team pages had it.
    - **ELO output path** — FIXED (see 10). **`build_simple_leaderboards.py -league hs`** — FIXED: its `--output-dir` default was the MatSavant NCAA folder and overrode the HS path, so every HS run overwrote `frontend/wrestledata-ui/public/data/leaderboards/*.json` with Kentucky data. Default is now `None` (NCAA → wrestledata-ui, HS → `frontend/hs-ky-ui/public/data/leaderboards/{gender}/{season}/`).
    - **Mat Value — NOT used by KentuckyMat, so deliberately not fixed** (checked 2026-09-20): the MV profile section in `app.js` is NCAA-only, `leaderboards/mat_value.html` is an unlinked orphan (not in nav or sitemap, and fetches a non-gendered path), the homepage MV loader lives in `index.js` which `index.html` never loads, and every committed HS `mv` value is `null`. `compute_all_mat_values.py -league hs` fails with hundreds of `Failed to find opponent` errors, so the pipeline's "Compute Mat Value" step is now disabled for HS. Fix it only if HS Mat Value comes back.
    - **Left as-is (snapshots older than the data, not re-run after the cleanup):** 2026 `rosters`, `dual_standings` (the dual simulation is not deterministic), `public_rankings`, `rankings_full`. They regenerate with end-of-season differences unrelated to duplicates; refresh them with the normal weekly pipeline.

12. **Rebuilding old-season profiles produces harmless churn**: the current `build_wrestler_profiles.py` adds empty `grade/hometown/high_school/photo_url/previous_school` keys and a new `profile_generated_at` to every file, so a rebuild rewrites every file in a season even when nothing real changed (2014 = ~12k files, ~1.4k with real changes). After any bulk rebuild run `scripts/revert_rebuild_noise.py <path>` (`--dry-run` first; `--ignore-added grade,bonus` also treats those newly-added non-empty keys as noise): it compares each modified JSON to `git show HEAD:<path>` and `git checkout`s the files whose only differences are timestamp keys / newly-added empty keys, so the commit/deploy contains only real changes. Only use it on paths that were clean before the rebuild.

13. **Unlinked wrestler-seasons (found 2026-09-21 via Josh Tuttle's missing 2024 season)**: `link_season_interactive.py` is a manual pass and skipped some wrestlers, so a season can have matches, a season profile and an accomplishments entry yet not be in any career file's `seasons` dict — the career page then skips that year and the career record is short. Nothing errors. `scripts/careers/audit_unlinked_seasons.py` finds them (roster entries with 0 matches are ignored — TrackWrestling lists many wrestlers who never wrestled). Categories: **AUTO** (exact name, exactly one career lacking the season, same team as one of its seasons within ±3 years, grade progression within ±1), **REVIEW** (name variants like Josh/Joshua or Brayden/Braydon, transfers, several same-name careers, exact name with no team/grade support = usually a different person), **NONE** (no existing career; mostly first-year wrestlers, needs a NEW career). `audit_unlinked_seasons.py --write-plan plan.json` then `link_seasons_batch.py --plan plan.json [--dry-run]` applies links (adds a season key only; never creates/merges/changes careers; skips anything whose id isn't in the processed roster or is already linked elsewhere) and logs them. **Applied 2026-09-21**: 65 AUTO links (Tuttle 2024 + 64: boys 2015/2017/2020/2022/2024/2026 and one girls 2026) — the 2026 gaps were the bulk (64 of 65 are exact-name same-team wrestlers, mostly 2026 seasons for 2025 careers). **Then (TJ approved) 7 name-variant typos**: Braydon Donato→Brayden Donato, Elexis Herrington→alexis Herrington, Isaac Meyer (2020)→Issac Meyer, Jakobi Linton→Jakobri Linton, cam caudill→Cameron Caudill, lathen meade→lathan meade, salde hyden→Slade Hyden (72 backend career files changed in total, all logged in `batch_links_log.json`). **Deliberately NOT linked (TJ: leave alone)**: the transfers (George Mintch, Michael Hacker, Elijah Clark), Wade Mettling's split careers, and the same-name-different-person cases (Gavin Adams, Gavin Ratliff, Jackson Reed, Jake Williamson, Mason Hamilton, Thomas Evans). **Still open**: ~10 of those REVIEW cases, 166 NONE (150 are names that appear nowhere else in the data = first-year wrestlers who need new careers), and the split careers in Gotcha 14. **After linking, rebuild**: `build_wrestler_profiles.py` for each affected season (profiles carry `career_id`, `career`, `season_summary` and every opponent's `opponent_career_id`, so opponents' files change too), then `generate_search_index.py`, `build_career_profiles.py` (both genders), `build_leaderboards.py -season 2026 --all-time-career-wins`. Snapshot the folders first and restore noise-only files afterwards (Gotcha 12 — the tree may already be dirty from earlier rebuilds, so compare against your own snapshot, not HEAD). Linking a girl who also wrestles in the girls division into the CURRENT season makes `generate_search_index.py` apply `boys_inactive_wrestlers.json` to her boys career, so her duplicate boys search entry disappears (girls entry stays) — expected. **Rebuilding a season's profiles used to drop the `bonus` block** (2020 lost it on 168 profiles) — fixed 2026-09-21: `build_wrestler_profiles.py` now reads each profile's existing `bonus` before clearing the folder and writes it back (values are NOT recomputed; re-run `compute_all_top33_bonus.py` for that). Note 2026 profiles currently have no `bonus` block at all (it was lost in earlier rebuilds and never re-run).


15. **Season records: ONE canonical bout list (found 2026-09-21 via Josh Tuttle 2024; fixed the same day)**: a wrestler's season W-L used to be counted separately by `season_accomplishments` (header / career summary — every raw row whose name+team text matched), `build_wrestler_profiles.py` (`match_list` from the merged `mt/rankings_data` weight_class files — Season Stats box and match history) and `app.js` (recount), and they disagreed on 30–55% of wrestlers per season (2013/14 worse). Causes: rows listed twice were counted twice; bouts listed only in the OPPONENT's file were missed; name/team spelling mismatches (Brayden/Braydan) dropped rows; the match list merged same-day bouts vs unknown/out-of-state opponents (two forfeits), dropped the 2nd same-day bout vs one opponent, and dropped medical forfeits (MFF); and `load_data` dropped a few bouts entirely. **Now**: `scripts/records/canonical_bouts.py` (`build_season(gender, season)`) builds one bout list per season from `mt/processed_data` (both wrestlers' files), applies the approved duplicate events (Gotcha 9) and `match_overrides.json`, and everything reads it: `generate_season_accomplishments.py` (`record`; `--legacy-records` = old count), `build_wrestler_profiles.py` (HS default `-match_source canonical`: `record`, `match_list`, bonus stats, best win/worst loss all come from it; `-match_source weight_classes` = legacy) → `build_career_profiles.py` → leaderboards / search index. `app.js` Season Stats still recounts from `match_list`, which now equals `record`. Rules (TJ 2026-09-21; full text in the `canonical_bouts.py` header): count every decided bout incl. forfeits/MFF/injury defaults/DQ (MFF counts as W/L but is excluded from pin/bonus rates like forfeit wins); exclude byes, no-results (`NoResult`, override `NC`) and scraper-error rows; exhibitions still count; a bout credits BOTH wrestlers even if only one file lists it; same pair+date+result TYPE with compatible results = one bout (exact duplicate rows collapse); **a different result (score, or real non-0:00 time) is a different bout — never ignore a match whose result differs** — except when no wrestler's own file lists both versions (A's file says 11-2, B's 14-2: one bout recorded differently, counted once); the SAME round label in one event is one bout (you can't wrestle a round twice; e.g. Fall 2:34 vs 2:33); different round labels are a real same-day rematch only when BOTH wrestlers' files list BOTH (otherwise one duplicate bout). Bouts with no opponent id (forfeits vs "Unknown", unrostered opponents) are keyed by wrestler+event+date+type(+label) and get the same synthetic `OUTSTATE_<md5(name|team)>` id `load_data` uses; each wrestler sees the bout's event from HIS side ("vs. <other team>"). The weight class of a bout comes from the ranking files when the pair is there, else the raw row (normalised). Ranking/ELO/H2H/matrix steps still read the weight_class files and are unchanged. **Checks**: `scripts/records/verify_consistency.py` (canonical == accomplishments == profile `record` == `match_list` W-L for every wrestler-season; run after any rebuild), `compare_season_records.py` (how the OLD numbers differed, with causes, writes `mt/audits/season_records/`), `show_wrestler.py --career career_X` (one career before/after), `career_wins_preview.py` (top career wins live vs working tree vs canonical). `build_wrestler_profiles.py` prints a warning if `data/season_accomplishments` is stale relative to canonical. **Applied 2026-09-21**: accomplishments `--records-only` for all boys 2013–2026 + girls 2024–2026, profiles rebuilt for all of them, then career profiles, leaderboards (per-season + all-time career wins), search index; 2026 bonus/xTP/team profiles/team metrics refreshed. Known small limits: opponent-only bouts rely on the opponent's file being scraped; two forfeits at the SAME event/date/round vs unknowns collapse into one; a rebuild no longer drops `bonus` (profile builder now keeps it) but old-season bonus values were not recomputed.

14. **Split careers (not fixed)**: 73 boys season IDs — all 2023 — are linked to TWO careers with the same name (146 career files, all `created_from_season: 2025`), e.g. Wade Mettling `career_006124` [2021, 2023] + `career_006552` [2022, 2023] share 2023 id `20163829132`. Each is half of one wrestler's career, so both career pages show a short record. Fix with `scripts/careers/merge_careers.py` (keep the id the current season profile points to), one pair at a time or scripted; do it BEFORE linking any orphan season for those names (an exact-name match to two careers is ambiguous and is left for review). Girls have none.

---

## SEO Setup

- **Google Search Console**: Verified. Sitemap submitted at `https://www.kentuckymat.com/sitemap.xml`.
- **`robots.txt`**: Present at `frontend/hs-ky-ui/public/robots.txt`.
- **`sitemap.xml`**: Generated by `scripts/generate_sitemap.py`. Add to rebuild pipeline when careers/teams change.
- **Dynamic titles + meta descriptions**: Set in JS at render time for wrestler, team, rankings, and leaderboard pages. Static meta descriptions in `index.html` and `recruiting.html`.

---

## Future Plans (Known)

- **Repo separation**: kentuckymat and matsavant now share the single `main` branch (the old `hsky-dev` split was retired). Whether to eventually split them into fully independent repositories is still an open question — the current shared-codebase state is a known tradeoff.
- **Forum**: Add a community forum to kentuckymat.com. Architecture approach TBD.
- **Automated documentation**: Keep `CLAUDE.md` updated regularly as the codebase evolves.

---

## What Is Legacy / Inactive

- `api/` directory and `server.py` — legacy, not used
- `frontend/wrestledata-ui/` — MatSavant site frontend (shares `main` with the KentuckyMat frontend)
- DynamoDB tables and `link_and_upload_season.py` upload steps — fully replaced by static files
- `scripts/generate_public_rankings.py` — uncertain if still needed
- `scripts/generate_public_matrix.py` — not currently needed
- `data/rankings-TOBEDELETED/` — legacy, safe to remove
