# KentuckyMat: preseason rankings and prior-season head-to-head

Started 2026-10-05 for the 2027 season. Two parts:

1. **Preseason ranking** (2027 is the first one): how the starting order is built from last season, and what is left before publishing it.
2. **Prior-season head-to-head in the matrix**: a design TJ approved on 2026-10-05. **It must be built before the first in-season 2027 ranking.** Not built yet.

---

## Part 1 — Preseason ranking

### How last season was ranked (source of truth)

- `mt/rankings_data/hs_ky_{gender}/{season}/rankings_{w}.json` is TJ's matrix order. Only the top **60 boys / 36 girls** are ranked by hand (`get_manual_rank_cutoff()` in `scripts/rankings/calculate_elo_ratings.py`). Below that, the order that matters is the **hybrid rank**: ELO order in three tiers (has a win, then winless with losses, then 0-0). It's stored per weight in `mt/elo_ratings/{gender}/{season}/elo_ratings.json` → `hybrid_rank_by_weight`. The matrix file's own order below the cutoff is not the hybrid order.
- Published: top **40 boys / 24 girls** (`create_rankings_release.py`).
- The final 2026 order is the current `rankings_*.json`, not the last published drop. Boys are identical to the 2026-03-04 drop. Girls were re-ranked after their last drop (2026-02-23).

### The preseason rule (TJ, 2026-10-05)

Same team and same weight for everyone. Remove the seniors and move everyone up. The manual block keeps its order, and the ELO block follows it.

**The ELO-cutoff problem:** removing seniors shrinks the hand-ranked block. If it drops below the published size, ELO-ordered wrestlers end up in the published rankings, and TJ isn't as careful with those. For 2027:

| | Manual ranks left after seniors | ELO wrestlers in published range |
|---|---|---|
| Boys | 34–54 per weight | **27**, in 138, 150, 157, 165, 175, 190, 215, 285 (144 has 42 left, so it's fine) |
| Girls | 28–31 per weight | none (all weights cover the top 24) |

TJ chose to rank those boys weights deeper in the preseason matrix before publishing.

### Building it

```bash
.venv/bin/python scripts/rankings/build_preseason_matrix_inputs.py --from-season 2026 --gender boys
.venv/bin/python scripts/rankings/generate_matrix.py -season 2027 -league hs -state KY -gender boys \
    -data-dir mt/preseason_2027/rankings_data -output-dir mt/preseason_2027/rankings_html
```

- Output goes to a **separate staging tree**, `mt/preseason_2027/` (gitignored by the `mt/preseason_*/` entry added 2026-10-06), never to `mt/rankings_data/`. That keeps it from being mistaken for real 2027 season data.
- **Wrestler IDs are still the 2026 TrackWrestling IDs.** IDs change every season, so they have to be mapped to 2027 IDs through career links once 2027 rosters are scraped (see Part 2, "Career links").
- **Relationships:** the 2026 relationship files, minus seniors' own rows. Common-opponent comparisons whose common opponent was a senior are kept. For boys that's 16,014 of the 60,193 common-opponent pairs, and in 8,455 of them seniors are the only common opponent.
- **Placement notes** (1–8 / BR / Q next to each name) are rebuilt from the 2026 state tournament and replace the old ones (the old file had TJ's 2025 results). Source: `mt/processed_data` via `build_xtp_simple_hybrid.py`'s bracket collectors. 1–8 = place. BR = lost in the round that decides placing (boys Cons. Round 4, girls Cons. Round 2). Q = every other state entrant. Checked: full brackets (boys 448 = 14×32, girls 192 = 12×16), places match `season_accomplishments` for all placers, and there are exactly 4 BR per weight.
- **Don't use `data/hs_ky_{gender}/bloodround.txt` for 2026.** Despite an April 2026 save date, its bouts are not 2026 state bouts; they look like 2025. Replace it before ever running `manage_placement_notes.py -import-bloodround` again.
- The matrix still shows 2026 grades (a "Jr." is a rising senior).
- **Saving (new 2026-10-06):** the matrix's Save button downloads `rankings_{gender}_{season}_{w}_{YYYY-MM-DD_HHMMSS}.json` (gender, season and `saved_at` are also inside the file), so boys and girls saves can't overwrite each other and every save is kept. Import with `.venv/bin/python scripts/rankings/import_matrix_saves.py -season 2027 -gender girls -data-dir mt/preseason_2027/rankings_data [--dry-run]`: it takes the newest save per weight, blocks a save that is missing a wrestler or lists one the matrix doesn't have, reports what moved in the published range, backs up the replaced file to `rankings_archive/import_{timestamp}/`, and moves the used saves to `~/Downloads/kentuckymat_matrix_saves/{gender}_{season}/`. Then rerun only `generate_matrix.py`. Never import into `mt/rankings_data/` for preseason work. **Don't rerun `build_preseason_matrix_inputs.py`**, because it rewrites every `rankings_{w}.json` from the 2026 start point. Saves made before 2026-10-06 were named just `rankings_{w}.json` and were copied by hand (the boys, plus girls 107/114/120).
- **Double-click-to-move** (click a cell twice to move that row to the column's rank) was broken until 2026-10-05: it used each cell's column number from when the page was built, so after any reorder it sent the row to the column's original rank. Matrices built after the fix in `generate_matrix.py` read the live column instead. The fix only reaches a matrix when it's rebuilt, so older HTML files (e.g. `mt/rankings_html/.../2026/`) still have the bug.

### Status / still to do (2027)

**RESUME HERE (updated 2026-10-07): PUBLISHED — the 2027 preseason site went live 2026-10-07 (commit 4cfd4ca3d7; live smoke test 88/88). Next KentuckyMat preseason work: before the first in-season drop (early December) flip `siteSeason.phase` to 'season' per "Switching to the in-season phase", run 2027 career linking early, and build the Part 2 prior-season H2H matrix layer.**

- [x] Boys and girls inputs staged; boys matrices built (2026-10-05).
- [x] **Boys DONE.** TJ re-ranked all 14 boys weights. His saves were copied from `~/Downloads` into `mt/preseason_2027/rankings_data/hs_ky_boys/2027/rankings_{w}.json`; the starting orders are kept as `rankings_{w}.start.json`. For 126 the later save `rankings_126-2.json` (3:28 pm) was used; it ranks the whole weight and has the same top 40 as the first save.
  - **Trey Herron (Caldwell County)**: the 2026 data listed him at two weights (hand-ranked #41 at 113, plus a leftover tail entry at 106). The 113 relationships file, rebuilt in the 2026-09-20 duplicate-events cleanup, no longer has him, so the 113 matrix silently dropped him. TJ had ranked him #40 at 106. **TJ's decision: Herron is 113 #40.** He was inserted there and removed from 106 (everyone below him at 106 moved up; new 106 #40 Elnar Kamalov was hand-ranked in 2026). Lesson: the input builder should drop a wrestler's duplicate tail entry at a second weight, and check every ranked wrestler is in that weight's relationships file (girls were checked: clean).
  - ELO-origin wrestlers in the boys top 40 were all placed by TJ, except Graydon Gant (215 #39, the same spot as his ELO start). **TJ: keep Gant there.**
- [x] Girls matrices built 2026-10-06 (`mt/preseason_2027/rankings_html/hs_ky_girls/2027/`), with the double-click fix. Starting orders kept as `rankings_{w}.start.json`.
- [x] 2026-10-06: the boys saves were moved out of `~/Downloads` into `~/Downloads/kentuckymat_preseason_2027_boys/` (all checked against staging first). Otherwise girls saves at the same weights (120/126/132/138/165) would have downloaded as `rankings_120 (1).json` etc.
- [x] 2026-10-06: girls **107, 114, 120** reviewed by TJ (saved with the old button) and imported: same wrestlers, 33/41/44 positions changed; 107 and 114 changed only below the top 24. At 120 the top-24 changes include Zeliah Cooper 12→7, Asmin Saidi 5→13, Briella Levy 10→17, Lizzie Ward 9→14.
- [x] 2026-10-06: **Naiya Delos Santos (Taylor County) removed** (TJ: she moved away; she'd have been girls 100 #1). Removed from girls 100 (rankings, `.start.json`, her own relationship pairs, placement note) and from boys 106 (same girl, different ID: 0-0, #232). Common-opponent comparisons where she was the shared opponent are kept, as for seniors. Backups are in `rankings_archive/remove_delos_santos_*`. Girls 100 #1 is now Kenleigh Estep.
- [x] 2026-10-06: **Herron's matrix entry moved from `relationships_106.json` to `relationships_113.json`** (backup `rankings_archive/move_herron_*`). Before this, the 106 matrix showed him as an extra last row and the 113 matrix didn't show him at all, so re-saving either weight would have put him back at 106 or dropped him from 113. His 2026 comparisons were all with 106 wrestlers, so his 113 row has no cells. Checked afterwards: every preseason matrix (26) has exactly the wrestlers and order of its `rankings_{w}.json`.
- [x] All matrices (boys and girls) rebuilt 2026-10-06 with the new Save button.
- [x] **Girls DONE (2026-10-06).** TJ saved all 12 weights with the new Save button; imported with `import_matrix_saves.py` (backup of the previous files: `rankings_archive/import_20261006-095738/`; saves in `~/Downloads/kentuckymat_matrix_saves/girls_2027/`). For 185 there were two saves a minute apart with different orders; the newer one (09:50:00) was used. 100, 107 and 114 have the same top 24 as the starting order (100 after removing Delos Santos). Biggest top-24 changes: 120 (Kaitlyn Baker 24→15, Zeliah Cooper 12→7, Asmin Saidi 5→13), 145 (Jenny White #1 over Amy Velasco; Kylee Hargan 17→29), 165 (Saydee Johnson 31→21), 185 (Addison Rowland 27→20). Girls matrices rebuilt; every matrix matches its rankings file.
- [x] **Site "preseason state" (TJ, 2026-10-06).** The site has a season AND a phase: `{season: 2027, phase: 'preseason'}` until the first in-season ranking (after the first week of matches), then `{season: 2027, phase: 'season'}`, which stays through state and the summer until `{season: 2028, phase: 'preseason'}`. Set in one place (`hs_config.js`), with helpers `getSiteSeason()` (2027 in both phases), `getStatsSeason()` (2026 in preseason, 2027 in season: pages that need real match data) and `isPreseason()`. The eight hardcoded `return "2026"` getters (app.js, team.js, index.js, recruiting.js, leaderboards/*.js) are replaced by the helpers, so the yearly switch is one line. Page decisions are collected one page at a time, then built together:
  - **Rankings** (decided 2026-10-06):
    - Opens on the 2027 preseason drop. Title "2027 Preseason Kentucky {Boys/Girls} High School Wrestling Rankings"; the dropdown labels it "Preseason" instead of a date. The drop ID is the publish date.
    - Rows: grade moved up a year (Jr. → Sr., 8th → Fr.), the **2026 record clearly labeled as 2026**, **no movement arrows**, and the 2026 state-result pill (↩︎ #1 / BR / Q) is kept. The **first in-season drop is a fresh baseline with no arrows either.**
    - **PDF and JPG graphics: yes** (same as a weekly drop).
    - **Past seasons:** the dropdown lists only the current season's drops. A "Past seasons: 2026" link at the top opens `rankings.html?season=2026` on the same page, with a "2026 rankings (past season)" banner and a "← Back to current rankings" link; that season's dropdown opens on its last drop, labeled "Final". The list of past seasons comes from a generated `data/rankings/{gender}/seasons.json` that the release script updates (not hardcoded). Today only 2026 has drops; `data/rankings/boys/2020/` is an empty leftover folder.
    - **Publish a "2026 Final" girls drop** from the final girls order (they were re-ranked after their last drop, 2026-02-23), so both archives end on the true final ranking. Boys don't need one (the 2026-03-04 drop equals the final order).
  - **Home** (decided 2026-10-06): a small "2027 Preseason" tag under the Boys/Girls Rankings buttons, shown only in the preseason phase. Nothing else changes (the other cards don't name a season). The temporary "2027 All Star Classic" banner was removed from Home on 2026-10-06 (local, unpushed); `matchups.html` + `matchups_data.js` stay, just unlinked.
  - **Wrestler profiles** (decided 2026-10-07):
    - Header pill = the 2027 preseason rank, labeled `#3 · 2027 Preseason`, then `120 lbs · Boyle County`. The page reads it from the published preseason drop, matched on the wrestler's 2026 ID (the drop entries carry those IDs). One small extra fetch, only in the preseason phase. No rebuild of the ~20k career files; it switches off by itself when the phase changes.
    - Returners outside the preseason top 40/24: **no pill** (not their 2026 number).
    - Graduated seniors / non-returners: keep their last rank, **labeled with its season** (`#5 · 2026`).
    - **In-season too (new norm): the pill always carries its season**, `#3 · 2027`, never a bare `#3`.
    - Career table and the per-season "Season Rank" detail: unchanged; no placeholder 2027 row until 2027 matches exist.
  - **Team** (decided 2026-10-07): **no preseason team projection.** A preseason team total stacks errors that all lean one way (only one wrestler per weight counts, so deep teams with stacked teammates come out low; weight moves filling empty weights are invisible), and the headline number + rank badge is what people screenshot. Tested 2026-10-07 with the 2027 hybrid table (boys: Paducah Tilghman 159, Ryle 141.5, Martin County 112.5, Union County 105.5 vs 248 in 2026; girls: Boyle County 108.5) — TJ judged it not accurate enough. Instead, in the preseason phase:
    - Header "{Team} Wrestling · 2027 Preseason".
    - **Returning wrestlers** (2026 roster minus seniors): next year's grade, 2026 record labeled "2026", and the individual preseason rank pill if in the published top 40/24. No team math.
    - In place of the "Projected State Tournament Points" box: a short note, e.g. "2027 projected state points arrive with the first in-season rankings in early December. Lineups aren't set until wrestlers certify weights and replace graduated seniors, so a team projection before then would mostly be guesswork." (TJ: "early December" is the ETA.)
    - 2026 team results (record, top-33/top-10, rates) labeled "2026 Season", or reachable through a "2026 season" link like past rankings.
    - Links into team pages without `season=` must not 404 on `data/teams/{gender}/2027/` (only 2026 files exist) — build preseason team files or fall back to the stats season.
  - **xTP teams** (follows from Team, agreed 2026-10-07; revised the same day — see the Build notes): only the "2027 projected team standings arrive with the first in-season rankings in early December" message plus a link to the 2026 final standings.
  - **Stat Leaders** (`leaderboards.html`; decided 2026-10-07; the separate `leaderboards/leaderboard_*.html` pages are unlinked orphans, out of scope):
    - Wins / Pins / Techs: keep showing 2026, labeled "2026 Season · Final", rank column labeled "2026 Rank". They switch to 2027 when the phase switches to "season" (same moment as every other page), even though early-season lists are thin.
    - Career Wins: class-year pills follow the site season (2027), so the Class of 2026 shows outlined as graduated and the Class of 2027 as seniors.
    - **New: "Active only" toggle on Career Wins, default OFF (show all)** — useful year-round.
  - **Dual rankings** (decided 2026-10-07, revised the same day): only a "2027 dual rankings arrive with the first in-season rankings in early December" note plus a link to the 2026 final dual rankings. Older 2026 drops through a "Past seasons: 2026" link, same as individual rankings (dropdown lists only current-season drops).
  - **Dual predictor** (decided 2026-10-07): **turned off in the preseason** — no simulation, just a note that the Dual Predictor comes back with 2027 lineups in early December. (TJ chose this over running it on labeled 2026 lineups.) Nav/Home links can stay; the page itself shows the note.
  - **Recruiting** (decided 2026-10-07): tabs Class of 2027–2030, opening on **2027**; Class of 2026 kept as a last tab labeled "2026 · Graduated". Rank column = the 2027 preseason rank, labeled, blank outside the published top 40/24 (same rule as the profile pill). **Add Class of 2030** (2026 8th graders: 40 boys / 25 girls are in the preseason published rankings, e.g. girls 100 #2 Brielle Richardson, 107 #2 Peyton Brinkman), with a small "8th" placement column shown only when someone in the class placed at state as an 8th grader. Class years come from the site season, not hardcoded (`build_recruiting_data.py` has `CURRENT_SEASON = 2026`, `GRAD_CLASSES = [2026..2029]`; `recruiting.js`/`.html` hardcode `'2026'` and the four tabs).
    - Commitments updated 2026-10-07 (TJ): Corban Nance (`career_000008`) → Georgetown College (new); Benjamin Woosley (`career_002471`) → Georgetown College (was Lindsey Wilson). Boys `recruiting.json` rebuilt; the rebuild also swapped two borderline entries at the 100 cutoff (2028 Hunter Fields → Gavin Jordan, 2029 Jaxson Wallace → Heath May) from data changes since the June build. Uncommitted.
  - **Compare, About, Methodology** (decided 2026-10-07): **no changes.** Compare's cards already label the rank with its season (`#2 · 2026`). About already says each season starts from previous years' context. TJ declined a Methodology "Preseason Rankings" section ("I'll address it if people complain").
  - **All page decisions are in (2026-10-07).** The unlinked pages (matrix, matchups, report, mat_value, odds-stacked, leaderboards/leaderboard_*.html) are out of scope.
- [x] **Build — DONE locally 2026-10-07** (not committed or pushed). Local smoke test: 84 of 84 checks pass (6 warnings = MatSavant's pre-existing missing team logos).
  - **`hs_config.js`**: `siteSeason: {season: 2027, phase: 'preseason'}` + `isPreseason()`, `getSiteSeason()`, `getStatsSeason()` (`HS_CONFIG.defaultSeason` is now set from it), `preseasonComingNote(what)` and `renderSeasonContext()` (shared "Past seasons" / past-season banner). The orphan pages' hardcoded `"2026"` getters (index.js, leaderboards/simple_leaderboard.js, career_wins_leaderboard.js, mat_value.js, odds-stacked.js) were left alone: none of those files are loaded by a linked page.
  - **Rankings**: `create_rankings_release.py --preseason` (order from `mt/preseason_{season}/rankings_data/`, records/profiles/grades from the season before with grades moved up a year, no ELO hybrid, no movement, no team/dual archives, meta `phase: 'preseason'`, index label "Preseason", graphic date box "PRE. 2027", internal PDF `hs_rankings_{gender}_{season}_preseason.pdf` without the team page). Every `--archive` run now writes `data/rankings/{gender}/seasons.json`. SVG graphics now fall back to the archive entry's grade (the old `load_grade_info` path doesn't exist, so the grade source was empty). Drops built with **drop ID 2026-10-07**: `data/rankings/{boys,girls}/2027/2026-10-07/` (+ `rankings.pdf`), graphics in `mt/graphics/2027/`. **If publishing on a later date, rebuild with that date as the drop ID** (delete the 2027 folders first): `create_rankings_release.py -season 2027 -gender {g} -drop-id YYYY-MM-DD --preseason --archive --pdf --jpg`, then `build_preseason_team_rosters.py` and `build_recruiting_data.py --rebuild` (they read the drop).
  - **Girls "2026 Final" drop**: `data/rankings/girls/2026/2026-10-07/` (normal release from the final girls order, with team tournament + dual archives and the PDF). Team and dual top 5 unchanged from 2026-02-23; 212 of 288 wrestlers moved (the post-state re-rank).
  - **rankings.js**: opens on the site season; `?season=2026` = past season with banner + back link; dropdown shows "Preseason" / "Final (date)"; record columns labeled "2026 W–L"/"2026 Bonus %" when the drop's `record_season` differs; wrestler links carry `&season=` (so old drops keep working once 2027 profiles exist); weight tabs keep `season=` on past seasons.
  - **Home**: "2027 PRESEASON" tag under the rankings buttons (index.html now loads hs_config.js — note this also makes Home send a GA page view, which it never did before: `analytics.js` has `send_page_view: false` and nothing on Home called `sendPageView()`).
  - **Profiles (app.js)**: header pill `#2 · 2027 Preseason` from the published drop (one fetch: index + that weight's file), none for unranked returners, `#5 · 2026` for graduates / anything else; the single-season view's badge also carries its year.
  - **Team**: `scripts/teams/build_preseason_team_rosters.py --season 2027 --gender both` writes `data/teams/{gender}/2027/{slug}.json` (`schema_version: preseason-1`): returners = the preseason rankings files (seniors and Delos Santos already removed), minus 0-0 roster listings (boys 2,403 returners / 713 0-0 left out; girls 733 / 114). team.js (preseason, no `?season=`) shows the note box instead of projected points, "2026 Season" stats, and a Returning Wrestlers table (Wt, Wrestler, Gr, preseason Rank, 2026 W–L, 2026 State); `?season=2026` = the normal 2026 page (linked as "2026 season →"). Phones: the two summary boxes now stack (they were clipped on the normal page too).
  - **Team Tournament / Team Duals** (revised by TJ 2026-10-07 after seeing the preview, which showed the 2026 table under the note and still read as a current projection): in the preseason the page shows **only** the note and a "See the 2026 final standings →" link (`renderPreseasonStandingsNote()` in hs_config.js; table, explainer and dropdown hidden) — "the whole site is in 2027 mode; 2026 only if they click for it". `?season=2026` = full 2026 drop list with the past-season banner; its latest drop is labeled "Final"; the Preseason drop is filtered out of their drop lists.
  - **Wording** (TJ 2026-10-07, "too many words"): every preseason placeholder (Team Tournament, Team Duals, the team page's projected-points box, Dual Predictor) is just a big **"Coming Soon"** + "Expected in early December, after the season begins." (`createComingSoonBlock()` in hs_config.js), plus the 2026 link on the two standings pages. No explanations.
  - **Names** (TJ 2026-10-07): ALL CAPS / all lowercase names shown with capitalized words, mixed case untouched — `displayName()` in header.js at every name render site, `display_name()` for the graphics (CLAUDE.md, "Wrestler name display"). Graphics rebuilt.
  - **Dual Predictor**: replaced by a "Coming back in early December" note in the preseason.
  - **Stat Leaders**: "2026 Season · Final", "2026 Rank" column (cards: "2026 #8"); Career Wins pills measured against the site season (Class of 2026 outlined); "Active only" toggle (default off).
  - **Recruiting**: `build_recruiting_data.py` reads `siteSeason` from hs_config.js (override `--site-season/--phase`): classes 2027–2030 + "2026 · Graduated"; rank = published preseason rank (graduated class: its 2026 rank); new `8th` placement (counts toward ordering only for a class with no HS seasons yet); the "this year" swap rule uses the stats-season placement instead of always `Sr`. recruiting.js builds tabs/columns from the JSON. `manage_commitments.py` also reads the stats season from hs_config.js.
  - `scripts/site_checks/pages.json`: added rankings 2026 (boys/girls), a returner's profile, preseason team pages (boys/girls), dual rankings, girls recruiting.
- [x] **Published 2026-10-07** (commit 4cfd4ca3d7, pushed with TJ's MatSavant schedule commit 36e3bb5a1f; live smoke test 88/88). Was: TJ reviews locally, then commit + push to `main` (approval needed; smoke test `--target live --wait-deploy` after). The push will also carry the other uncommitted KentuckyMat work already in the tree (background search index — `docs/TODO.md`, and the All Star banner removal).

### Switching to the in-season phase (first in-season 2027 ranking, early December)

One line in `hs_config.js`: `siteSeason: { season: 2027, phase: 'season' }`. In the same push:
- Build the 2027 team profiles (`build_team_profiles.py --season 2027`), which **overwrites** the preseason roster files in `data/teams/{gender}/2027/` — that's intended, but don't build them while the phase is still 'preseason' (the preseason team view would read a normal profile as a roster).
- Rerun `build_recruiting_data.py --rebuild` (classes stay 2027–2030; ranks switch to current ranks; the graduated 2026 class is then read from its 2026 season).
- The first in-season drop is a fresh baseline with no arrows: `create_rankings_release.py` skips drops labeled "Preseason" when it looks for the previous drop (both for the archive and the graphics), so this happens by itself.
- Profile pills switch to `#3 · 2027` automatically.
- Next summer: `{season: 2028, phase: 'preseason'}` and repeat Part 1.

### Next summer: the 2028 preseason, step by step

What 2027 took, in order (details in the sections above):

1. **Stage the matrix inputs** (once; never rerun after TJ starts saving): `.venv/bin/python scripts/rankings/build_preseason_matrix_inputs.py --from-season 2027 --gender {boys,girls}`. Check the "ELO wrestlers in published range" table and that every ranked wrestler is in that weight's relationships file (the Herron lesson).
2. **Build the matrices**: `generate_matrix.py -season 2028 -league hs -state KY -gender {g} -data-dir mt/preseason_2028/rankings_data -output-dir mt/preseason_2028/rankings_html`. TJ re-ranks and saves each weight.
3. **Import the saves**: `import_matrix_saves.py -season 2028 -gender {g} -data-dir mt/preseason_2028/rankings_data`, then rebuild only the matrices.
4. **Last season's final drop**: if a gender was re-ranked after its last weekly drop, publish a normal drop of the final order (2026 girls needed one; boys didn't).
5. **Preseason drops**: `create_rankings_release.py -season 2028 -gender {g} -drop-id <publish date> --preseason --archive --pdf --jpg`.
6. **Team rosters**: `scripts/teams/build_preseason_team_rosters.py --season 2028 --gender both`.
7. **Flip the site**: `hs_config.js` `siteSeason: { season: 2028, phase: 'preseason' }`, then `build_recruiting_data.py --rebuild` (it reads the phase from hs_config.js).
8. **Check**: `smoke_test.py --target local`, preview on `dev` (reset `dev` to `main` first — see CLAUDE.md), then push with TJ's approval and run the live smoke test.

The page behavior for the preseason is already built and driven by the phase, so no page code should need changing; only the decisions in "Site 'preseason state'" if TJ wants something different.

**Where the work lives:** all code, site data and docs are committed and live (commits `11846b7d80` tooling, `4cfd4ca3d7` site). Only `mt/preseason_2027/` stays local (gitignored staging data: TJ's saved rankings, `.start.json` starting orders, relationships, placement notes, backups in `rankings_archive/`). Don't lose it, and don't rerun `build_preseason_matrix_inputs.py` (it would overwrite TJ's saved rankings). Graphics are in `mt/graphics/2027/`; the used matrix saves are in `~/Downloads/kentuckymat_matrix_saves/` and `~/Downloads/kentuckymat_preseason_2027_boys/`.

---

## Part 2 — Prior-season head-to-head in the matrix (approved design, to build)

### The problem

Once 2027 matches start, the matrix is rebuilt from 2027 data only, so last season's results disappear. Only the 1–8/BR/Q note remains. If a Q beat a BR last year, TJ ranks the Q higher in the preseason, but later he can no longer see why, and the note pulls them back into "BR above Q."

### The design (TJ's decisions, 2026-10-05)

1. **Head-to-head only.** Last season's direct bouts between the two wrestlers; no prior-season common opponents.
2. **New cell type, light blue, win side only.** Only the cell of the wrestler who won last year's series is colored, and the mirror cell stays empty. Light blue below the diagonal therefore reads like green below the diagonal: "a lower-ranked wrestler beat him last year."
3. **Which series show (TJ, revised 2026-10-06):** a one-sided series (1-0, 2-0, 3-0 …) always shows, colored for the winner. A **split** (both wrestlers won at least once) shows only if the winner leads by **2 or more**: 3-1, 4-2, 4-1 show; 1-1, 2-2 and **2-1, 3-2** don't. The tooltip lists every prior-season bout: date, result, event, and the weight if it was different. (2026 pairs for reference: boys 18,104, of which 1-0 = 89.6%, 2-0 = 7.1%, 1-1 = 308, 2-1 = 62, 3-1 = 11, 2-2 = 6; girls 4,781, with 1-1 = 93, 2-1 = 37, 3-1 = 11, 2-2 = 6. The rule hides about 2% of pairs.)
4. **Lowest priority. Any current-season data replaces it.** If the pair has a current-season head-to-head **or** a common-opponent result, show that and drop the blue. It only fills cells that would otherwise be empty.
5. **Display only.** It must not feed automatic sorting (`auto_seed_rankings.py`), conflict counts, ranking bands, "recent" highlighting, or anything else that scores the matrix. It's a hint for TJ's eye.

### How to build it (sketch)

- **Data:** last season's `mt/rankings_data/hs_ky_{gender}/{prev}/relationships_{w}.json` → `direct_relationships`. The prior bout may have been at a different weight, so collect pairs from all weight files (or from the canonical bout list, `scripts/records/canonical_bouts.py`). De-duplicate by pair.
- **Career links:** convert prior IDs to career IDs, then to current-season IDs, using the backend career files (`data/careers/[girls/]career_*.json`, `seasons` dict). A pair is shown only if **both** wrestlers' current seasons are linked. Freshmen have no history, so they're unaffected.
- **Matrix code:** in `generate_matrix.py`'s `build_matrix_data()`, after the direct and common-opponent branches, add a third branch for cells still `type: 'none'`: `type: 'prior_win'` with a light-blue CSS class, on the winner's side only. Exclude this type wherever cells are counted or scored.
- **Self-check:** for a known pair from last season with no 2027 meeting yet, the blue cell appears on the right side; after a 2027 common opponent is added, it's replaced.

### Career links (TJ, 2026-10-05)

This feature is only as good as the 2027 career links, so run `link_season_interactive.py` for 2027 (and `scripts/careers/audit_unlinked_seasons.py`, CLAUDE.md gotcha 13) **early in the season**, before the first in-season ranking. Unlinked returning wrestlers silently lose their blue cells.
