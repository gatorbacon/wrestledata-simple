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

## Ready to ship (committed locally, not pushed)

- [ ] **Dual Schedule: team filter + Text only view** (commit `0ebfa76024`). TJ is holding it to group with the next push. *(added 2026-10-01)*

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

## Side projects

- [ ] **Wrestling program directory** (`~/Documents/Cursor/wrestling-recruit`): 345 programs onboarded; site build (M7) unfinished; commits are local only, nothing pushed. Read that repo's CLAUDE.md "RESUME HERE". *(memory: wrestling directory site)*
- [ ] **NCAA Bracket Archive (Lab)** — built 2026-10-01, local only (`/lab/brackets/`, docs/matsavant.md "NCAA Bracket Archive"). Open: (1) TJ review; (2) scoring rules for the years before 2013 so 1933 and the old years' full standings can be calculated (the 1930s fit about half the rows); (3) team-name map from old names to today's programs, then team history pages; (4) WPA charts on 2013+ bouts. *(updated 2026-10-01)*
- [ ] **Repo separation** (KentuckyMat and MatSavant in one repo): open question, no plan yet. *(CLAUDE.md "Future Plans")*

---

## Done

- [x] 2026-10-01 — Compare button next to the wrestler's name, Compare link on the Wrestlers page (pushed).
- [x] 2026-10-01 — Info icons work on phones and DPG Trajectory has one; "Dual Points Gained" wording (pushed).
- [x] 2026-10-01 — 2026 profile DPG matches the DPG file again; P4P feed and rankings DPG refreshed (pushed).
- [x] 2026-10-01 — Roster and schedule rescan; all 16 parked changes accepted; Schedule page 236 → 490 duals (pushed).
- [x] 2026-10-01 — Merged LJ / Leandro Araujo and Mike / Michael Caliendo careers (pushed).
- [x] 2026-10-01 — NCAA pipeline links each new season into careers and refreshes season tables; new-season checklist written.
- [x] 2026-10-01 — Career view on MatSavant profiles; retired wrestlers open on Career (pushed).
- [x] 2026-09-30 — Site smoke test before and after every push.
- [x] 2026-09-30 — WPA model, all 11 spec steps + overtime model.
