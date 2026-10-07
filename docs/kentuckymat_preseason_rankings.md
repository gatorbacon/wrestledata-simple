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

**RESUME HERE (updated 2026-10-07): both genders are ranked and imported — no ranking work left. We are in the page-by-page "preseason state" walkthrough (bullet "Site 'preseason state'" below): Rankings and Home are decided; Wrestler profiles is proposed and waiting on TJ's two answers (Q1/Q2 below). Ask those, then continue with Team and the rest, then do the Build item. Nothing is built, committed or pushed yet.**

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
  - **Wrestler profiles** (proposed 2026-10-06; **WAITING ON TJ's two answers** — when resuming, ask these first):
    - Proposal:
      - Header pill = the 2027 preseason rank, labeled `#3 · 2027 Preseason`, then `120 lbs · Boyle County`. The page reads it from the published preseason drop, matched on the wrestler's 2026 ID (the drop entries carry those IDs). That's one small extra fetch, only in the preseason phase. No rebuild of the ~20k career files; it switches off by itself when the phase changes.
      - Returners outside the preseason top 40/24: **no pill** (not their 2026 number).
      - Graduated seniors / non-returners: keep their last rank, **labeled with its season** (`#5 · 2026`). Today that number has no label all summer and reads like a current rank.
      - Career table (one row per season): unchanged; no placeholder 2027 row until 2027 matches exist.
      - Season detail ("Season Rank #9" inside the 2026 season): unchanged (already scoped to 2026).
    - Q1: OK with the above (labeled preseason pill; no pill for unranked returners; season-labeled pills for graduates)?
    - Q2: once the phase is "season", keep a small season label on the pill (`#3 · 2027`) or go back to plain `#3`?
  - Still to walk through, in order: Team, Leaderboards (stats + career wins), Dual rankings, xTP teams (option to raise: a preseason team-tournament ranking from xTP), Dual predictor, Recruiting (whose "class of" year is current?), Compare, Methodology/About. The unlinked pages (matrix, matchups, report, mat_value, odds-stacked) are out of scope. For each page: say what it shows today in the preseason state, recommend, ask TJ (plain-text questions, not the multiple-choice prompt), record the decision here.
- [ ] **Build (after ALL page decisions are in; one batch, not per page):**
  - `hs_config.js`: `siteSeason: {season: 2027, phase: 'preseason'}` + `getSiteSeason()` / `getStatsSeason()` / `isPreseason()`; replace the eight hardcoded `return "2026"` getters (app.js, team.js, index.js, recruiting.js, leaderboards/*.js). Check `HS_CONFIG.defaultSeason` / `getSeasonFromURL()` callers.
  - Rankings: 2027 preseason drop for both genders from `mt/preseason_2027/rankings_data/` (top 40 boys / 24 girls; grade +1, 2026 record labeled 2026, no arrows, state-result pill kept) + PDF/JPG via the release script; "Preseason" dropdown label; "Past seasons" link + `data/rankings/{gender}/seasons.json` written by the release script; past-season banner/back link; past season opens on its last drop labeled "Final".
  - "2026 Final" girls drop from the final girls order (boys not needed).
  - Home: "2027 Preseason" tag under the rankings buttons (banner removal already done locally).
  - Profiles + other pages per the decisions above.
  - Add any new page/URL to `scripts/site_checks/pages.json`; smoke test `--target local` before, `--target live --wait-deploy` after. **Push only with TJ's approval.** Commit the uncommitted work listed below with it.
- [ ] Publish: a 2027 drop under `frontend/hs-ky-ui/public/data/rankings/{gender}/2027/` (`index.json` + drop folder, same format as the 2026 drops), wrestler links while entries still carry 2026 IDs, `pages.json` / smoke test before and after pushing (CLAUDE.md Hard Rules). Pushing needs TJ's approval.

**Uncommitted repo changes from this work** (none committed yet): `scripts/rankings/build_preseason_matrix_inputs.py` (new), `scripts/rankings/generate_matrix.py` (double-click fix; new Save filename with gender/season/timestamp), `scripts/rankings/import_matrix_saves.py` (new), this doc (new), pointer lines in `CLAUDE.md` and `docs/TODO.md`, and the `mt/preseason_*/` line in `.gitignore`. Everything under `mt/preseason_2027/` is gitignored local data. Don't lose it, and don't rerun `build_preseason_matrix_inputs.py` (it would overwrite TJ's saved rankings).

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
