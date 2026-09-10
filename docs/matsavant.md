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
```
`calculate_elo_ratings.py` must run after `apply_flo_rankings.py` in the *same* pass — it reads `rankings_<weight>.json`'s `flo_ranked` tags to build `hybrid_rank`, and a stale/missing tag silently falls the wrestler to the Elo tier instead of trusting Flo. Do this for every season whose underlying rank data changed before moving to Step 2 — don't interleave.

**Step 2 — after EVERY affected season has been through Step 1, re-run `build_wrestler_profiles.py -season {year}` again for EVERY NCAA season (not just the ones that changed), in any order.** This is the step that was missed the first time. Reason: `season_summary` (the per-season table on a wrestler's profile page, e.g. `wrestler.html`'s "SEASON / TEAM / CLASS / RANK / RECORD / DPG" rows) is built by `build_ncaa_season_summary_lookup()`, which re-reads *every other season's own already-published profile file* off disk at the moment it runs — it is not computed from a shared live source, it's a snapshot taken at build time. A wrestler with a 2023-2026 career gets a `season_summary` row for each of those years baked into *every one* of their season profile files; if season A is rebuilt before season B is fixed, season A's copy of season B's row is stale until season A is rebuilt again. Since careers span many seasons, in practice this means: **any time more than one season's rank data changes in the same pass, plan on a full second `build_wrestler_profiles.py` sweep across every season at the end**, not just the ones that changed.

`compute_all_mat_values.py` and `apply_flo_rankings.py`/`calculate_elo_ratings.py` do **not** have this cross-season snapshot problem — each season's own file is self-contained — so Step 2 only needs to re-run `build_wrestler_profiles.py`.

**Not required for a rank-only fix, but part of the same family of "what needs to be re-run" questions:** `scripts/generate_search_index.py -league ncaa -season {year}` (search index doesn't display rank, so it wasn't stale from this specific fix, but it's another per-season snapshot artifact worth knowing about), and the weekly pipeline's later steps (bonus EV, xTP, team profiles/metrics — see the main weekly pipeline order in root `CLAUDE.md`) if DPG/mat_value numbers themselves changed, not just rank.

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
| `scripts/rankings/calculate_elo_ratings.py` | Builds `mt/elo_ratings/ncaa_men/{season}/elo_ratings.json` (`elo_rank`, `matrix_rank`, `hybrid_rank`) |
| `scripts/rankings/build_wrestler_profiles.py` | Writes each wrestler profile's `current_rank` — NCAA branch currently sources this incorrectly, see Known Compliance Gaps |
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
