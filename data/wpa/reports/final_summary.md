# WPA build — final summary (step 11)

Built 2026-09-29/30 from `wrestling_wpa_spec.md`. How to re-run and the details of each step are in `docs/wpa_handoff.md` and the WPA section of `docs/matsavant.md`. The step reports are in this folder.

## Outputs (`data/wpa/output/`, spec Section 8)

| File | What | Built by |
|---|---|---|
| `state_table.parquet` | every state cell: raw counts, empirical / smoothed / backstop / final WP (421,848 cells, two rules eras) | `fit_state_model.py`, copied by `build_outputs.py` |
| `model_params.json` | all fitted parameters in one file: state model, riding-time rate model, strength layer (incl. the conference scale), overtime model | `build_outputs.py` (merges `data/wpa/model/*_params.json`) |
| `events_wpa.parquet` | one row per link of every bout's WP chain (events, clock stretches, riding-time locks, overtime choices); each bout's links add up exactly to result − opening WP | `compute_wpa.py` |
| `wrestler_wpa.csv` | WPA per wrestler per tournament | `compute_wpa.py` |
| `match_wp_curves.parquet` | WP over time for 14,656 bouts (1.14M points: chain points plus the model at 10-second samples), overtime on the same clock | `build_outputs.py` |

The parquet files are gitignored (rebuild: `compute_wpa.py` then `build_outputs.py`, about 1 minute). `model_params.json` and `wrestler_wpa.csv` are tracked.

Example charts (`reports/img/examples/`, `plot_examples.py`): a big upset (2021 197 R32: #31 Pentz pins #2 Schultz from 3% at the opening whistle), a comeback (2023 125 SF: Ramos over Lee from 0.3%), a late riding-time decision (2024 157 QF: Cardenas over Shapiro 5-4 on the riding-time point) and a tiebreaker (2023 133: Mendez over Byrd, TB-1). Also: ESPN-style cards (`plot_wp_cards.py`), overtime flow charts (`plot_ot_flow.py`).

## Headline results

- **Held out (leave one NCAA year out, all 11 years):** log loss 0.456 for margin + time only → 0.446 for the state model → **0.393** for the full model (2024–26: 0.472 → 0.466 → **0.414**). Calibration slope 0.997 (1 = calibrated); the largest decile gap is 1.9 points.
- **Conference tournaments (with national rank, leak-free seasons 2023–26):** 0.435 → **0.379**, slope 0.997.
- **Overtime model (2022+ rules):** held out 0.662 → 0.646 (tiebreakers 0.666 → 0.561).
- **Structure:** 0 monotonicity drops. Only 0.22% of scoring events lower the scorer's WP, all by ≤ 0.1 point; these are riding-time edge cases at very high WP. 7 of 7 hand checks pass.
- **What events are worth:** a takedown averages +13.3 WP points in 2015–23 and +15.8 in 2024–26 (the 3-point takedown). Deferring averages −1.9.

## Spec Section 11 — open questions answered

**1. Timestamp quality, and what fraction of matches are usable.**
91% of events inside a period carry a clock: 47,328 of 51,922 NCAA and 58,821 of 64,279 conference. The clock reads exact seconds, with no rounding to 5 or 10. It counts down time remaining in the period. Clock errors (the clock going up within a period) are rare: 51 NCAA and 87 conference.

84.7% of NCAA bouts (5,729 / 6,766) and 84.2% of conference bouts have a clock on every regulation scoring event. With TJ's decision B, an unclocked event is placed between its clocked neighbours and the bout is flagged. After that, 96.8% of NCAA bouts and 89.3% of conference bouts are usable for the state table. The conference share is lower because 6 tournaments have unreliable riding time.

**2. Is running riding time recorded? Is period choice?**
- **Riding time:** not as a field. 54% of NCAA bouts have scorekeeper notes on it, and 48% show the end-of-match riding-time point as an event. It is rebuilt from position (decision A): the rebuilt value matches the actual in 98.6% of fully clocked NCAA bouts.
- **Period choice:** recorded in more than 99% of bouts, in the `Choice N` columns.
- **Position:** never recorded. It is inferred from the scoring and the choices.

**3. Conference matches with both wrestlers ranked.**
With the leak-free Flo snapshots before the tournament (2023–26), 23–30% of conference bouts have both wrestlers ranked, 38–40% have one, and 30–38% have neither. Before 2023 the only rank source is the end-of-season rank, which leaks NCAA results. Those seasons are used for WPA but not for fitting or testing (decision E).

**4. Share of match-moments in thin cells (< 50 bouts).**
- **With the spec's key:** 41.6% of NCAA moments and 56.0% of 2024–26 moments. In period 3 within 3 points, where bouts are decided, it is 75.6% for 2024–26. Riding-time bins are the main cause: dropping them takes that 75.6% to 23.0% (`sparsity_audit.md`).
- **With the final key:** riding time is factored out; the table is keyed on the eventual riding-time point, and conference 2024–26 data is added. Now 9.7% of 2015–23 moments and 20.9% of 2024–26 moments sit in thin cells.
- **How thin cells are handled:** those cells lean almost entirely on smoothing and the parametric backstop (mean own-data weight ≈ 0). The backstop was needed: without it, 21% of 2024–26 moments had fewer than 50 bouts even counting the neighbouring cells.

**5. Do rules eras need separate tables?**
Yes, for regulation. A 2-point lead with 1:00 left held 93% of the time in 2015–23 but 84% in 2024–26, because one 3-point takedown now erases it. The table is keyed on the era: 2015 is pooled with 2016–23 (decision D), and 2024–26 stands alone and drives the estimates. Older data enters only through the backstop and the smoothing.

Overtime also needs its own rules. Sudden victory was 1:00 through 2021 and 2:00 from 2022, and the tiebreaker riding time has only broken a points tie (1 second) since 2022. The overtime model is fitted only on 2022+ bouts (674). Earlier overtimes keep the simple strength-based value.

## Change after the build (2026-09-30)

Break states (before the toss, toss won, about to pick) are now composed from the regulation states they lead to, weighted by observed choice shares, instead of their own noisy table cells (TJ spotted a −1.5 coin toss). Toss WPA is now 0 to +0.75 at every margin, the usual pick ≈0; deferring stays about −2 and a check against real results says that is real (docs/matsavant.md, "Break states").

## Known soft spots

- **Riding-time knife edge** ("up 1, 0:05 left, on top, needs the last 5 s for 1:00"): the model is now right on the hand check. The data there is 1–5 held-out moments a year, so it stays uncertain.
- **Conference strength:** rank covers about 70% of conference bouts at most. Before 2023 the rank leaks results.
- **Overtime:** the pool is small (674 bouts). Ride-2 choices follow observed habit, not optimal play.
- **Source data:** some bouts can't be used. Examples are duplicate or mislabelled bouts (2018 197 Conel 'Fall 2-0' ×2) and 14 of 15 "comebacks from 0%" that were riding-time rebuild mismatches. The rebuild flags these (`rt_consistent`), and they are left out of examples and checks.
