# WPA model — handoff for a new session

Read this first. Written 2026-09-29 at the end of the session that built steps 1–9, so a fresh Claude Code session
(any account, **same Mac, same repo folder**) can finish the job without re-deriving anything.

**Where the rest lives:** the spec is `/Users/tjthompson/Downloads/wrestling_wpa_spec.md` (the 11-step build order is
its Section 9). The full design record is `docs/matsavant.md`, section "WPA model (TJ's spec)", which has the step table,
every TJ decision and the step-8 changes. Per-step reports are in `data/wpa/reports/`. Every script's docstring explains
its design. Claude Code memory: `~/.claude/projects/-Users-tjthompson-Documents-Cursor-wrestledata-simple/memory/project_wpa_spec_build.md`.

---

## 0. Standing rules (TJ)

- **Never push** to any branch without TJ's explicit OK. Commit locally only. All WPA commits so far are local and unpushed:
  `c83f75ae02` (steps 1–4), `367f01a53c` (5–7), `175f127d88` (8), `1c8c0497ba` (9), plus the commit that adds this file.
- **Keep WPA commits clean.** Unrelated uncommitted files sit in the tree: `data/analysis/td_custom_report.html`,
  `scripts/analysis/td_custom_report/{build_data.py,template.html}` and `data/analysis/nf_by_year.html`. Those belong to
  the takedown-report work, so don't `git add -A`; add WPA paths explicitly.
- Don't publish Artifacts unless TJ asks.
- **Effort reminders (TJ asked, to save credits):** high effort is right for the remaining steps. Tell TJ at step
  boundaries if a step needs more or less.
- TJ was at ~93% weekly usage when this was written. Keep turns lean: run long jobs in the background and don't re-read
  big files needlessly.
- Nothing here touches the live site. It's all under `scripts/wpa/` and `data/wpa/`, separate from the older Lab model
  in `scripts/win_prob/` and `data/pbp/`.

---

## 1. What exists (steps 1–9 done)

| Step | Script | Writes | Time |
|---|---|---|---|
| 1 audit | `scripts/wpa/audit_data.py` | `reports/data_audit.md` | — |
| 2 states | `scripts/wpa/build_states.py --kind both` (+ shared `wpa_common.py`) | `data/wpa/states/{ncaa,conf}_{bouts,events,samples}.csv` (gitignored) + `reports/state_reconstruction.md` | ~1 min |
| 3 table | `scripts/wpa/build_table.py` | `data/wpa/table/` (gitignored) | <1 min |
| 4 sparsity | `scripts/wpa/sparsity_audit.py` | `reports/sparsity_audit.md` | — |
| 5–6 state model | `scripts/wpa/fit_state_model.py` | `data/wpa/model/state_table.parquet`, `rt_model.joblib`, `backstop.joblib` (all gitignored), `model_params.json`, `reports/state_model.md` | ~9 min |
| 7 seed layer | `scripts/wpa/fit_strength.py [--refresh]` | `strength_params.json`, `tie_model.joblib`, `ncaa_oof_state.parquet` (auto-rebuilt when the state table changes, +6 min), `reports/strength_layer.md` | ~5–11 min |
| 8 validation | `scripts/wpa/validate.py [--reuse]` | `reports/validation.md` + `reports/img/validation_*.png` (cache `data/wpa/model/validation_cache.*`, gitignored) | ~6 min (`--reuse` 20 s) |
| 9 WPA | `scripts/wpa/compute_wpa.py` | `data/wpa/output/events_wpa.parquet` (gitignored), `data/wpa/output/wrestler_wpa.csv`, `reports/wpa.md` | ~10 s |

Shared predictor used by steps 8 and 9 and everything after: `scripts/wpa/wp_model.py`. `WPModel().wp(df)` or `.parts(df)`
takes A-relative regulation states: margin, t_rem, period, pos, choice, rt_diff, era_group, seed_a, seed_b.

**Full rebuild chain** (run from the repo root, in the background, with a log to the scratchpad):
`.venv/bin/python scripts/wpa/fit_state_model.py && .venv/bin/python scripts/wpa/fit_strength.py && .venv/bin/python scripts/wpa/validate.py && .venv/bin/python scripts/wpa/compute_wpa.py`
(~30 min). Steps 2–3 only need rerunning if the state reconstruction changes. Everything is deterministic (`random_state=0`),
so a rerun with no code change gives identical params.

---

## 2. The model as it stands

**State** (spec 2): margin (excluding the pending riding-time point), t_rem (10-s bins), period, position (neutral / A_top /
A_bottom, plus break states `pending_pre_toss`, `pending_defer_option`, `pending_pick`), choice holder (A / B / none),
riding-time differential, rules era.

**Rules eras** (TJ decision): E1 2015, E2 2016–23, E3 2024–26. The model uses E12 (2015–23) vs E3, and **E3 is the anchor**:
older eras fill gaps, and validation is judged on E3.

**Riding time is factored out of the table** (TJ's idea, after the sparsity audit):
`WP_state = Σ_r P(r | S) · T(S, r)`, where r ∈ {A gets the point, nobody, B gets it}.
- `T` = empirical table keyed on current margin **and** the eventual point r, kept apart. Pooling them as margin + r was
  tried and failed. It is smoothed with neighbours plus a GBM backstop via `w = n/(n+k)`, k = 80, k2 = 80, and uses
  NCAA + conference E3 data.
- `P(r | S)` = the riding-time point model (see section 5: **this is the piece to simplify next**). It is exact whenever
  the clock decides the point (per wrestler: 0 if he can't reach 1:00 even riding every remaining second, 1 if he keeps it
  even if ridden out).
- Lock logic per spec 2.3: `wpa_common.rt_status` / `wp_model.rt_status_vec`, threshold `>= 60` s, with 4 states:
  locked_in / locked_out / locked_none / live.

**Step-6 projections on T** (alternated 6 rounds, then symmetrised): monotone in margin; monotone in r (B pt ≤ none ≤ A pt);
and the **release option** (the top man can let his man go, so A_top at m ≥ neutral at m−1, and mirrored, an escape can't
lower the escaper's WP).

**Rows that feed the model:** 10-s samples at bin centres (420, then 415, 405 … 5), the state just AFTER each event, and
break states. The spec's "state just before each event" rows are **dropped on purpose**: they are biased because the
event about to happen is usually the trailing wrestler scoring, which cost leaders 6–7 points late. This deviates from
spec 3.1, and TJ was told.

**Seed layer** (spec 5): `logit(WP) = α(t)·logit(WP_state) + β0·(t/420)^γ·rs·(E3 mult) + β_ot·P(tie at buzzer)·rs`.
- Fitted values: α(t) = 0.64 + 0.32 × share of the match elapsed, β0 1.56, γ 0.61, β_ot 0.51, E3 multiplier 0.87.
- rs = strength(A) − strength(B) on a normal-quantile seed scale (N = 50; unseeded ≈ seed 22; both unseeded → 0).
  Pre-2019 seeds 17–33 are treated as unseeded (TJ decision C: those were a random draw).
- **α must never depend on the seed gap.** A gap-dependent α fitted slightly better but made WP fall as the seed
  advantage grew. α exists because the state table already builds in "leaders are usually better"; the spec's α = 1
  double-counted strength (calibration slope 0.88).
- Tie model: `P(tie | S) = Σ_r P(r|S)·P(tie | S, r)`, a GBM symmetrised by mirroring.

**Validation results (step 8), held out:**
- Log loss: margin + time 0.456, state model 0.446, **full 0.393**. For 2024–26: 0.472 / 0.466 / **0.414**. Forward in time,
  2024 as a cold start: 0.415.
- Calibration slope 1.00 (2024–26: 0.97).
- 0 monotonicity drops (margin, riding time, seed).
- 6 of 7 hand checks pass. The fail is the riding-time knife edge: "A up 1, 0:05, on top, +0:55" gives P(A pt) = 69%
  against the >75% rule, where the data says ~90%+. That's part of why the simplification is next.

**WPA (step 9)**, from `compute_wpa.py`:
- Each bout is one chain: opening whistle → clock → event → clock → … → result. Clock stretches are credited to the leader
  at the start of the stretch; riding-time locks get their own `rt_lock` row at the exact second.
- The sum rule is asserted: WPA sums to result − opening WP, exactly. Per wrestler per tournament, total = wins − expected wins.
- Penalty and stalling points are credited to the **offender** (negative), with the beneficiary recorded. In the raw
  events the `penalty` actor is the beneficiary, and a `stalling` event with 0 points is the call on the offender.
- A tech fall is two rows: the scoring event, then the remainder to 1.
- Overtime: tied at the end of regulation = `expit(β_ot·rs)`. The value stays there until the winner's last OT score,
  which takes the jump to 1. **No separate OT model was built** (spec 2.4 allows skipping it; ~600 NCAA OT bouts). Ask
  TJ if he wants one.
- 38 of 36,700 scoring events have negative WPA, all ≤ 0.06 WP points and in bouts already decided.
- Findings so far: 2024–26 takedown +15.7 WP points (2015–23: +13.7); deferring −1.9 on average.

---

## 3. Gotchas learned the hard way

1. **`ncaa_bouts.csv` `w_seed` / `l_seed` are ALREADY strength seeds** (NaN = unseeded, pre-2019 17–33 already NaN).
   Don't pass them through `wpa_common.strength_seed` again: it expects ints, returns None for floats, and silently wipes
   every seed. That happened once in step 9 and every opening WP came out 50%.
2. Bouts file filters: `table_ok` = what the table and WPA use (NCAA 6,739 bouts; includes 213 riding-time-mismatch bouts).
   `rt_model_ok` = rows the riding-time model trains on. `rt_consistent = False` = rebuilt riding time disagrees with the
   official point. In WPA those bouts carry the correction at the buzzer, and 22 show a jump there.
3. The model needs **int** margin and period (`compute_wpa.ints()`), or `F.lookup` fails with "arrays used as indices must
   be of integer type".
4. Changing anything in `fit_state_model.py` changes the state table's mtime, so `fit_strength` rebuilds the out-of-fold
   cache (+6 min). That's expected.
5. The HGB riding-time model with monotone constraints: making it monotone in margin keeps WP monotone but fits the point
   worse (a big lead often ends in a tech fall with no point awarded). Leaving margin free fits the point but lets WP fall
   as the lead grows. Currently chosen by held-out WP: monotone in margin (0.4659 vs 0.4669). A physics-based model removes
   this dilemma (section 5).
6. Choosing between table variants before the step-6 projections gave the wrong answer. `fit_state_model` now re-scores
   the variants within 0.001 **after** the projections.
7. Background jobs: run the ~30-min chain with `run_in_background` and a log in the session scratchpad. The Bash safety
   classifier sometimes returns "no verdict (error)"; just retry once.

---

## 4. Open items to raise with TJ

- **Source-data issue:** NCAA 2018 at 197 lbs has two "QF Kyle Conel over Kollin Moore" bouts. The real one is Dec 5-3
  (match 8962976104). The other is a two-event "Fall 2-0" (match 8962577104). There's also a two-event "Fall 2-0" Conel over
  Jacob Holschlag in the C_SF. These come from the scraped bracket and should be checked against the official bracket
  before anything is published. They are noted in `reports/wpa.md`.
- **Overtime model — TJ decided 2026-09-29: build it AFTER step 10, BEFORE step 11.** Rules-based, reusing the rate
  model (`rt_hazard.py`) and its exact second-by-second machinery, not an empirical table. TJ's requirements:
  (1) **SV-1 and the tiebreakers get separate rules** — sudden victory = first score wins (takedown race, drifting
  toward the tiebreaker as the clock runs); tiebreakers = 30-s rides each (escapes / reversals / riding time, who
  chooses). (2) **Only data from the current OT rules** (sudden victory 2:00 since 2022; `ot_rules == "SV120"` in the
  bouts files): 307 NCAA OT bouts (2022–26) + 367 conference = 674. Per-second escape / takedown rates may still come
  from regulation wrestling (plentiful); the small pool is for the OT structure, the OT seed effect, and a check of
  whether OT rates differ from regulation (if they do, use OT rates). Confirm the tiebreaker riding-time rule from the
  recorded OT events (`ot_period` 1 = SV, 2–3 = the two 30-s rides; `ot_riding_time` events), not from memory.
  Why it matters: 620 of 6,739 NCAA bouts went to OT (13 finals; 3 of 10 in 2025); 175 ended in tiebreakers, where
  the current flat line is visibly wrong (e.g. 2025 125 final: 100% after Robinson's TB escape though Spratley still
  had his ride); in 98 OT bouts the eventual loser scored in OT and gets no WPA credit.
- **Takedown report section 3e** (published artifact TtL2sMVbLwUazwBoNfeyZG, `scripts/analysis/td_custom_report/`) used
  2015–18 seeds 17–32 as real seeds. It needs a fix: restrict to 2019+ or treat 17+ as unseeded. It's queued, separate from
  WPA, and its files are the uncommitted ones mentioned above.

---

## 5. DONE (2026-09-29): riding-time point model = trees + rate-model blend

Built `scripts/wpa/rt_hazard.py` (rate model + exact dynamic program). It predicts the point better but the WINNER
worse than the trees early in bouts, so TJ chose a blend: trees until 1:30 left, linear handoff, rate model alone from
0:30. Held-out WP equal to the trees, 7 of 7 hand checks, no seam. The pooled table key is no longer eligible (it broke
structurally when it briefly won). Full record: `docs/matsavant.md`, "Changes after step 9". `rt_model.joblib` now
holds the blend (a dict: tree + rate params + handoff seconds); `rt_params.json` is the rate model alone. Chain time is
~35 min now (the trees are refit in every seed-layer fold). Example charts: `scripts/wpa/plot_wp_cards.py`.

## 6. DONE (2026-09-29): step 10 — conference tournaments

`scripts/wpa/conf_ranks.py` gives each conference bout a national rank: leak-free Flo snapshots before Feb 15 for
2023–26; the leaky end-of-season `current_rank` before that (decision E, caveated). `fit_strength.py` fits the
conference rank scale (N 200, unranked ≈ rank 60), a rank multiplier (1.45 — the spec's "own β0") and an α multiplier
(1.14) leave-one-season-out on 2023–26 only; NCAA parameters unchanged. Held out: 0.4355 → 0.3792, slope 0.997.
`wp_model` reads conference rows via `kind == "conf"` (ranks go in the seed columns). `compute_wpa.py --kind both`
(default) covers 14,656 bouts; `wrestler_wpa.csv` is now per wrestler per TOURNAMENT (columns `kind`, `tournament`).
A few conference bouts lack the period-2 choice entry (`choice == "unknown"`); `compute_wpa.wp_of` values those states
as the average of A / B holding it. Full record: `docs/matsavant.md` step table row 10 and "Conference rank source".

**Next: the overtime model (section 4), then step 11.**

## 7. Then step 11 — final outputs (spec Section 8)

(Example charts started: `scripts/wpa/plot_wp_cards.py`, ESPN-style cards — finals by year or one wrestler's run.)

The spec wants, in "outputs/" (we use `data/wpa/output/`):
- `state_table.parquet` — exists in `data/wpa/model/`; copy or link it.
- `model_params.json` — exists (plus `strength_params.json`).
- `events_wpa.parquet` — exists.
- `wrestler_wpa.csv` — exists.
- **Still to do:** `match_wp_curves.parquet` (WP over time for every match, for charting: the chain points plus 10-s samples)
  and **example charts** — a step plot per match with events annotated for a handful of matches. Include at least one big
  upset (e.g. 2018 197 QF Conel over #1 Moore, or 2021 197 R32 Pentz #31 over Schultz #2) and one late riding-time decision
  (search `events_wpa` for large `rt_lock` rows).
- Reports: `data_audit.md`, `sparsity_audit.md`, `validation.md` (all exist; re-run after step 10).
- Finish with an answer to the spec's Section 11 open questions (most were answered in the audit and the sparsity report),
  and a final summary for TJ.
