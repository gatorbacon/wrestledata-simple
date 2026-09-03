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
# Load data
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

# Step 2: Wrestler profiles
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
| `scripts/season_accomplishments/generate_season_accomplishments.py` | Generates season accomplishment data |
| `scripts/careers/create_careers_from_season.py` | Creates initial career files from a season |
| `scripts/careers/link_season_interactive.py` | Interactively links seasons to careers |
| `scripts/careers/merge_careers.py` | Merges duplicate career records |
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

**SEO title templates:**
- Boys career: `{Name} | Kentucky High School Wrestling | {Team} | KentuckyMat`
- Girls career: `{Name} | Kentucky Girls High School Wrestling | {Team} | KentuckyMat`
- Team: `{Team} Wrestling {Season} | Kentucky [Girls] High School | KentuckyMat`
- Rankings: `{Season} Kentucky [Boys/Girls] High School Wrestling Rankings | KentuckyMat`

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
