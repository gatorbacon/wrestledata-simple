# Open items and half-finished projects

One list for both sites and the side projects, so nothing gets lost between sessions. Started 2026-10-01.

**How this list works**
- One line per item: what it is, why it's open, and where the details live. Long write-ups stay in `docs/matsavant.md`, `CLAUDE.md` or the project's own docs; this file only points to them.
- Each item says when it was added (or last checked).
- When an item is finished, tick it and move it to **Done** at the bottom with the date. Done items older than about a month can be deleted; the git history keeps them.
- Claude: read this at the start of work, and update it whenever something is finished, parked, or newly found. Don't let open items live only in a chat.

---

## Waiting on TJ (decisions)

- [ ] **2026 NCAA rankings page files (`data/public_rankings/2026/`)**: these still hold the ranks and records as built on 2026-09-03, before the ranking-method change of 2026-09-09; only their DPG was refreshed. Regenerating them (`generate_public_rankings.py --season 2026 -league ncaa`) would change last season's displayed ranks, e.g. 125: Spratley #6 → #2. Regenerate or leave as a snapshot? *(added 2026-10-01; docs/matsavant.md gotcha 18)*
- [ ] **2026 NCAA xTP files**: built with the old (stale) 2026 profile DPG as an input. Rerun xTP for 2026, or leave as is? *(added 2026-10-01; gotcha 18)*
- [ ] **Cloudflare in front of matsavant.com**: optional bot protection; only needed if another scraper burst gets past Netlify's bot blocking. Needs DNS and email forwarding moved from Namecheap. *(since 2026-09-27; memory: MatSavant bot mitigation)*
- [ ] **KentuckyMat split careers**: 73 boys 2023 season IDs are linked to two same-name careers (e.g. Wade Mettling). TJ chose to leave them for now. *(since 2026-09-21; CLAUDE.md gotcha 14)*
- [ ] **KentuckyMat career-linking review list**: about 10 REVIEW cases plus 166 wrestlers with no career (mostly first-year wrestlers who need new careers). *(since 2026-09-21; CLAUDE.md gotcha 13)*
- [ ] **Move both sites to AWS** (S3 + CloudFront on a flat-rate plan so there's no surprise bill; billing alert first). Discussed 2026-10-02: KentuckyMat first because of the forum (Discourse on Lightsail, ~$12-15/mo; maybe start on Discourse's free hosted plan to test interest), then MatSavant, whose live tracker would move off Railway to a scheduled Lambda writing `live_data.json` to S3 (CloudFront compression must be on: the 2026 replay file is 1.28 MB raw / 83 KB gzipped). Check Netlify's usage page for real monthly bandwidth/requests before choosing the Free vs $15 Pro plan. Not started. *(added 2026-10-02)*

## Ready to ship (committed locally, not pushed)

- [ ] **KentuckyMat: search index loads in the background** (uncommitted; same change MatSavant shipped 2026-10-02). `header.js` + the `search_index.js`/Fuse.js tags removed from 21 pages; `compare.html` keeps both, `dual_predictor.html` keeps Fuse. Not measured yet: a Lighthouse before/after (desktop, phone on good LTE, phone on slow 4G) — the 2026-10-02 mobile baseline on a wrestler page was score 42-51, first paint 8-11 s, ~5.5 s of it the search index. *(added 2026-10-02)*

## Uncommitted local work

- [ ] **Takedown custom report edits**: `data/analysis/td_custom_report.html`, `scripts/analysis/td_custom_report/build_data.py`, `template.html`, plus untracked `data/analysis/nf_by_year.html`. TJ's own work in progress; never included in a push. *(seen 2026-10-01)*

## MatSavant (matsavant.com)

- [ ] **Tablet width scrolls sideways**: at about 820 px wide, every page scrolls sideways because the top menu bar plus search box is wider than the screen. Phones and desktops are fine. *(found 2026-10-01)*
- [ ] **Compare page labels misaligned**: once Wrestler A is picked, the "Wrestler A" and "Wrestler B" labels sit at different heights. *(found 2026-10-01)*
- [ ] **Compare ideas not built** (TJ picked only the button restyle): suggested opponents on the Compare page when one wrestler is filled in (rivals, neighbours in the rankings), a head-to-head link on repeat opponents in match history, and a Google Analytics click event on the Compare button to measure use. *(discussed 2026-10-01)*
- [ ] **One unresolvable opponent wipes a wrestler's whole-season DPG.** *(since 2026-09-12; docs/matsavant.md gotcha 14)*
- [ ] **Conference membership not scraped**: `team_conferences.json` is a 2025-26 stopgap. Capture conference in the team-list scrape when the 2027 team list is scraped. *(since 2026-09-10; gotcha 12)*
- [ ] **Team renames create duplicate teams** (Pennsylvania → Penn): there's no team-level merge tool; old seasons sit under the old slug. *(since 2026-09-13; gotcha 16)*
- [ ] **Team simulation: unranked wrestlers all use one generic pool** regardless of program. *(gotcha 11)*
- [ ] **Win-probability model**: a 1-point lead in the last seconds is underpredicted (about 81% model vs 99% actual). *(docs/matsavant.md "Live Win-Probability Model")*
- [ ] **WPA model is built but not on the site**; the 149 lb bracket viewer is a local report only (`data/wpa/reports/bracket_2026_149.html`). Small data issue to fix at the source: the Gaj–Lamer rematch is labelled R16 instead of consolation semifinal. *(docs/wpa_handoff.md)*
- [ ] **TPAR research**: next step is an EIWA flat-penalty sweep on top of v3b + the MAC −0.9 fix, then a tournament CSV. Best so far 69.4% vs seeds 71.8%. *(memory: TPAR research 2026)*
- [ ] **Lazarus Award page** (awards/trivia tab): the script `scripts/ncaa/lazarus_award.py` exists; check whether a page ever shipped (it's referenced in `ncaa_live.html`). *(memory: pending UI changes)*

## MatSavant data (NCAA pipeline)

- [ ] **4,535 junk "(1).json" duplicate profiles are committed in `frontend/wrestledata-ui/public/data/wrestlers/2020/`** (e.g. `10430251132 (1).json`; nothing links to them). Any rebuild of 2020 profiles deletes them (the builder clears the folder); they were restored during the 2026-10-03 rematch fix to keep that commit focused. Delete them in their own commit. *(found 2026-10-03)*
- [ ] **iCloud seems to sync this repo (it lives in ~/Documents)**: during the 2026-10-03 bulk profile rebuild, 40 "(1).json" conflict copies appeared in `2026/by_team/` (moved out, not committed). Probably the source of the 2020 junk above too. Consider moving the repo out of iCloud-synced Documents; after any bulk rebuild, check `git status` for new " (1)" files before committing. *(found 2026-10-03)*
- [ ] **Hodge Watch 2026 is stale**: rerunning `hodge_candidates.py -season 2026` on the committed profiles gives 91 rows instead of the committed 100 (file from 2026-09-13; eligibility/weight-rank changes). Left as committed during the 2026-10-03 rematch fix; decide whether to regenerate. *(found 2026-10-03)*
- [ ] **NCAA `elo_ratings.json` has drifted from what the code makes today**: rerunning `calculate_elo_ratings.py -season 2026` (data unchanged) changes `hybrid_rank` for ~2,075 of 2,582 wrestlers and `matrix_rank` for ~2,174 (wins/losses identical). Profiles read `current_rank` from it, so the next NCAA pipeline run would move hundreds of displayed ranks. Find why (rankings_<weight>.json / Flo tags changed since the 2026-09-28 commit?) before rerunning Elo for any season. *(found 2026-10-03; docs/matsavant.md gotcha 19)*
- [ ] **Per-match DPG files have exact duplicate rows**: `match_mv_impact_{year}.json` repeats about 11% of bouts (same opponent, date and result; 2026: 4,152 of 37,767 rows, 1,433 of 2,288 wrestlers; 2024 and 2025 similar), where the profile lists the bout once (e.g. Marcus Blaze 11/23 TF 17-1 vs the same opponent twice; profile 28 bouts, `mat_value.matches` 29). Likely inflates or deflates season DPG slightly and counts. Find where `compute_all_mat_values.py` picks up the second copy, fix, rebuild DPG. The "DPG going in" analyses (`dpg_vs_ncaa_points.py`, `dpg_vs_seed_bracket_sim.py`) read the same file. *(found 2026-10-02)*

- [ ] **Rosters not posted yet for 2026-27**: 10 of 79 teams. Penn State, Northwestern, Virginia Tech and Little Rock returned "not found". Re-run `batch_scrape_current_rosters.py --mode all` every couple of weeks through the fall. *(checked 2026-10-01)*
- [ ] **Schedules not posted yet for 2026-27**: 19 of 79 teams; Chattanooga and Virginia Tech showed no events. Re-run `batch_scrape_schedules.py --season 2026-27`, accept parked changes, then run `dedupe_events.py` so the Schedule page updates. *(checked 2026-10-01)*
- [ ] **Leftover parked Clarion schedule file** `mt/data/official_schedules/clarion/2026-27.pending.json` has no flag (left from an older run; a fresh scrape matched the live file). Safe to delete. *(found 2026-10-01)*
- [ ] **No review tool for parked rosters**: the schedule side has `review_schedule_coherency.py`, rosters are accepted by hand. *(noted 2026-10-01)*
- [ ] **Scraper reports `no_players_found` for "not posted yet"** on modern Sidearm sites; could detect `@season` in the page title and say `not_posted_yet`. *(since 2026-09-21; docs/matsavant.md roster section)*
- [ ] **robots.txt question for the schedule scraper.** *(since 2026-09-21; docs/matsavant.md "Open issue — robots.txt")*
- [ ] **NCAA D1 dual poller**: shelved prototype. After D1 duals start (2026-11-01), test it live: does a new result show up the same day? Then decide cadence and output path. *(due after 2026-11-01; memory: NCAA D1 dual poller)*

## KentuckyMat (kentuckymat.com)

- [ ] **AdSense check-in, about 2026-10-23**: per-ad-unit earnings (Part D of `docs/kentuckymat_ads_phase3.md`); drop a bottom/mid slot that earns almost nothing. First look is informational; Dec–Feb is the real test. *(due 2026-10-23)*
- [ ] **AdSense project, phases still open**: Phase 2 (edge function) not started; Phase 4 (port to MatSavant) later. *(docs/kentuckymat_edge_function_plan.md)*
- [ ] **Before the 2027 HS season: smoke-test the HS pipeline steps** that regressed during the NCAA rework (CLAUDE.md gotcha 11). *(due before the 2027 season)*
- [ ] **2026 HS profiles have no `bonus` block.** Doesn't affect the site; if `compute_all_top33_bonus.py` is rerun for 2026, rerun xTP right after. *(CLAUDE.md gotchas 13/15)*
- [ ] **Re-tune the xTP_simple table after the 2027 season** with `build_xtp_simple_hybrid.py --season 2027`, before 2028. *(CLAUDE.md gotcha 17)*
- [ ] **`evaluate_state_predictions.py` bugs not fixed**: drops forfeit placements (needs an opponent ID) and its default processed-data folder is stale for girls 2026. *(CLAUDE.md gotcha 17)*
- [ ] **HS Mat Value is broken**, deliberately not fixed because KentuckyMat doesn't use it. *(CLAUDE.md gotcha 11)*
- [ ] **Matrix ranking assistant**: paused. Restart as a helper for TJ's weekly walk-through (surface conflicts and evidence), not a replacement. Read TJ's resume notes first. *(paused 2026-09-13; memory: matrix ranking automation)*
- [ ] **Historical state brackets**: 2012, 2011, 2010 boys done; next is 2009, working backward. *(memory: historical bracket transcription)*
- [ ] **Forum**: idea only, architecture not decided. *(CLAUDE.md "Future Plans")*

## New season (2027) — when it starts

- [ ] **MatSavant**: follow the checklist in docs/matsavant.md "Starting a New NCAA Season": bump `DEFAULT_SEASON` in `scripts/pipeline.py`, scrape rosters, run the pipeline (career linking is built in), review flagged transfers.
- [ ] **KentuckyMat**: update `defaultSeason` in `hs_config.js` (CLAUDE.md gotcha 6).
- [ ] **KentuckyMat 2027 preseason ranking**: boys and girls rankings DONE 2026-10-06 (all weights re-ranked by TJ, in `mt/preseason_2027/`; Herron 113 #40; Naiya Delos Santos removed, she moved away). NOW: page-by-page "preseason state" decisions (Rankings + Home decided; Wrestler profiles waiting on TJ's 2 answers; then Team, Leaderboards, Dual rankings, xTP, Dual predictor, Recruiting, Compare, Methodology/About), then build it all in one batch and publish (push needs approval). Home's All Star Classic banner removed locally, unpushed. *(docs/kentuckymat_preseason_rankings.md Part 1, "RESUME HERE")*
- [ ] **KentuckyMat: build the prior-season head-to-head layer in the matrix BEFORE the first in-season 2027 ranking** (light-blue, winner's cell only, head-to-head only, replaced by any current head-to-head or common-opponent result, display only). Needs 2027 career links done early in the season. *(approved 2026-10-05; docs/kentuckymat_preseason_rankings.md Part 2)*
- [ ] **KentuckyMat `data/hs_ky_{boys,girls}/bloodround.txt` are stale** (not 2026 state bouts despite an April 2026 save date); replace before using `manage_placement_notes.py -import-bloodround`. *(found 2026-10-05)*
- [ ] **Every year, once the NCAA season is over and the Hodge Trophy is announced** (next: spring 2027): add the season to `data/awards/hodge_trophy_history.json` and run `.venv/bin/python scripts/awards/build_hodge_dpg_history.py` to update the Lab page `/lab/hodge/`. *(docs/matsavant.md "DPG and the Hodge Trophy")*
- [ ] **Every year after the NCAAs**, once the bracket archive has the new year (`scripts/brackets/build_ncaa_bracket_archive.py`): rerun `.venv/bin/python scripts/rankings/freshman_of_year.py -season {year}` so the Freshman Watch's NCAAs column fills in. *(docs/matsavant.md "Freshman of the Year Watch")*

## Side projects

- [ ] **Wrestling program directory** (`~/Documents/Cursor/wrestling-recruit`): 345 programs onboarded; site build (M7) unfinished; commits are local only, nothing pushed. Read that repo's CLAUDE.md "RESUME HERE". *(memory: wrestling directory site)*
- [ ] **NCAA Bracket Archive (Lab)** — built 2026-10-01, local only (`/lab/brackets/`, docs/matsavant.md "NCAA Bracket Archive"). Open: (1) TJ review; (2) scoring rules for the years before 2013 so 1933 and the old years' full standings can be calculated (the 1930s fit about half the rows); (3) team-name map from old names to today's programs, then team history pages; (4) WPA charts on 2013+ bouts. *(updated 2026-10-01)*
- [ ] **Repo separation** (KentuckyMat and MatSavant in one repo): open question, no plan yet. *(CLAUDE.md "Future Plans")*

---

## Done

- [x] 2026-10-05 — KentuckyMat ranking matrix: double-click-to-move now uses the cell's current column (it used the column from when the page was built, so it went wrong after any reorder); a pending first click is cleared by any move. Tested in headless Chrome. (`generate_matrix.py`, uncommitted)
- [x] 2026-10-03 — MatSavant: same-day NCAA rematches no longer dropped (Kennedy–Kharchla 2026: QF + 3rd place); 1,512 bouts restored 2012–2026, 0 dropped; weight-class files, DPG, profiles and feeds rebuilt; WPA rematch round labels fixed. *(docs/matsavant.md gotcha 19; mt/audits/ncaa_rematch_fix/report.md; pushed 4ccf167889, live smoke test 70/70)*
- [x] 2026-10-03 — WPA: a locked riding-time point now counts as scored in the table (pin comebacks were missing from those cells), plus a pin-from-behind comeback floor by time left (`fit_pin_floor.py`) and a long-odds tail check in `validation.md`; full refit run. *(docs/wpa_handoff.md section 2; pushed 9659d7dbfe)*
- [x] 2026-10-03 — WPA: riding time now corrected to the official point in step 2 (no more false 0% at the buzzer), tiebreaker chain stops after a fall, `compute_wpa` stops the run if a winner's chart hits 0% or drops after 100%; full refit run. *(docs/wpa_handoff.md gotcha 2; committed)*
- [x] 2026-10-02 — Analysis: recency-weighted "DPG going in" (date decay, conference-tournament blend, last-k blend) does NOT beat plain DPG at predicting the NCAAs: tuned on 2015-23, the more recent matches are weighted the worse it gets; tested on 2024-26 every variant is slightly worse, alone and with the seed. `scripts/analysis/dpg_recency_test.py` -> `data/analysis/dpg_recency_test.json` (uncommitted).
- [x] 2026-10-02 — MatSavant: search index loads in the background after the page loads (no longer blocks first paint); match history shows the weight each bout was wrestled at (desktop Wt column, under the date on phones) (pushed).
- [x] 2026-10-02 — Pushed the held MatSavant/analysis commits: Dual Schedule team filter + Text only view, historical brackets data + Lab NCAA Bracket Archive, About page DPG formula, DPG-vs-NCAA analyses, Lab "DPG and the Hodge Trophy", Freshman of the Year Watch rework, this TODO list.
- [x] 2026-10-01 — Compare button next to the wrestler's name, Compare link on the Wrestlers page (pushed).
- [x] 2026-10-01 — Info icons work on phones and DPG Trajectory has one; "Dual Points Gained" wording (pushed).
- [x] 2026-10-01 — 2026 profile DPG matches the DPG file again; P4P feed and rankings DPG refreshed (pushed).
- [x] 2026-10-01 — Roster and schedule rescan; all 16 parked changes accepted; Schedule page 236 → 490 duals (pushed).
- [x] 2026-10-01 — Merged LJ / Leandro Araujo and Mike / Michael Caliendo careers (pushed).
- [x] 2026-10-01 — NCAA pipeline links each new season into careers and refreshes season tables; new-season checklist written.
- [x] 2026-10-01 — Career view on MatSavant profiles; retired wrestlers open on Career (pushed).
- [x] 2026-09-30 — Site smoke test before and after every push.
- [x] 2026-09-30 — WPA model, all 11 spec steps + overtime model.
