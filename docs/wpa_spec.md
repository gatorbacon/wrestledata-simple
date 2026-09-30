# Matsavant — Wrestling Win Probability & WPA
## Implementation Spec for Claude Code

---

## 0. Objective

Build a win probability (WP) model for NCAA D1 folkstyle wrestling, and from it compute **Win Probability Added (WPA)** for every scoring action and state change in a match.

- **WP:** probability that a given wrestler wins the match, given the current match state and the pre-match strength difference.
- **WPA:** `WP(after event) − WP(before event)`, credited to the wrestler who caused the event.

This is a Matsavant project. **Do not use TPAR anywhere in this model.** Strength enters only through NCAA seed or national rank (Section 5).

### Data available

- ~11 NCAA D1 Championship tournaments with match-level play-by-play
- ~50 conference tournaments with match-level play-by-play
- NCAA matches carry tournament **seed**
- Conference matches carry end-of-season **national rank** (top 33 only; many wrestlers unranked)

### Scope of version 1

- Retrospective model only, built on seeds/ranks as they stood at tournament time.
- A live in-season predictor is **out of scope**. Do not build it.
- Build and validate on **NCAA data first**. Fold in conference data as a second pass (Section 9).

---

## 1. Data audit — do this first, report before modeling

Produce `reports/data_audit.md` answering every item below. Several later steps are conditional on the answers. Stop and report after this step.

### Coverage
1. Number of NCAA and conference tournaments; seasons spanned; list each tournament with its season.
2. Total matches and total scoring events, split NCAA vs conference.
3. Matches with complete play-by-play vs final score only. Exclude final-score-only matches from the state table.

### Timestamps — highest-risk item
4. Fraction of events with a match-clock timestamp.
5. Timestamp granularity (exact seconds vs rounded).
6. Whether period boundaries are explicit or must be inferred.
7. Count of matches with non-monotonic times, times exceeding period length, or other clock errors. List examples.
8. Period lengths observed (expect 3:00 / 2:00 / 2:00 regulation). Flag any deviation.

### State variables
9. Is position (neutral / top / bottom) recorded directly, or must it be inferred from event types? If inferred, document the inference rules.
10. Is riding time recorded as a running value, final value only, or absent?
11. Is period choice recorded — who won the toss, whether they deferred, and what each wrestler chose (top / bottom / neutral / defer) in periods 2 and 3?
12. Overtime: are sudden victory and tiebreaker periods present and distinguishable?

### Match results
13. Distribution of result types: decision, major decision, tech fall, fall, injury default, medical forfeit, DQ, forfeit.
14. Confirm how falls and tech falls terminate the event stream.

### Rules drift across seasons
15. Point values by event type **by season**. NCAA changed scoring during this window (takedown value increased from 2 to 3 starting 2023–24, and near fall values changed). Verify exact changes from the data itself, list them, and tag each match with a `rules_era`.
16. Tech fall threshold by era.
17. Any other rule changes visible in the data (riding time rules, stalling, etc.).

### Seed and rank
18. NCAA: is seed present for both wrestlers in every match? What is the seeding depth per season (how many seeds; how many unseeded wrestlers)?
19. Conference: fraction of wrestlers with a national rank; confirm ranking depth is 33 every season.
20. **Fraction of conference matches where both wrestlers are ranked**, where exactly one is ranked, and where neither is.

### Event taxonomy
21. Full list of distinct event types with counts.
22. Whether point values are stored or derived from event type.

---

## 2. Match state definition

All states are expressed from the perspective of one wrestler, called **A**.

| Variable | Encoding |
|---|---|
| `margin` | Integer score A − B, **excluding** the pending riding time point. Clamp to ±15. |
| `t_rem` | Seconds remaining in regulation (whole match, not period), **binned at 10 seconds**. |
| `period` | 1, 2, 3, or OT (keep OT separate — see 2.4). |
| `position` | `neutral`, `A_top`, `A_bottom`. |
| `choice` | Who holds the next unused period choice: `A`, `B`, or `none`. See 2.2. |
| `rt_status` | `locked_in`, `locked_out`, or `live`. See 2.3. |
| `rt_bin` | Riding time differential in 10-second bins, clamped to ±60. Only meaningful when `rt_status = live`. |
| `rules_era` | From audit item 15. |

### 2.1 Perspective and symmetry

Add **every match twice**, once from each wrestler's perspective, with the state mirrored (margin negated, position flipped, choice flipped, riding time negated, rank signal negated) and the outcome flipped.

This enforces `WP_A(S) = 1 − WP_B(mirror(S))` by construction and removes any dependence on an arbitrary assignment of A.

### 2.2 Choice

NCAA folkstyle: the coin toss winner picks period 2 or defers; the other wrestler gets the remaining choice period.

- During period 1, `choice` = whoever will choose at the start of period 2.
- During period 2, `choice` = whoever will choose at the start of period 3.
- During period 3 and OT, `choice = none` (except as OT rules specify; model OT separately).

Choice matters most late: being down 2 with third-period choice in hand is a real asset. The period-start choice itself (picking bottom, top, neutral, or defer) is an event with its own WPA (Section 6).

If the audit shows choice is not recorded, infer it from the starting position of periods 2 and 3 where possible and document the method.

### 2.3 Riding time — explicit lock logic

Riding time is **not** a plain continuous variable. What matters late is whether the 1-point riding time bonus (earned by a 1:00+ advantage) is still reachable.

Example: A has 55 seconds of riding time advantage. With 6 seconds left and A on top, it is live — A can reach 1:00. With 4 seconds left, it is decided — A cannot. These must be different states.

Implement `rt_status` as an explicit function:

```
def rt_status(rt_diff, t_rem, position):
    # rt_diff: A's current riding time advantage in seconds (can be negative)
    # Riding time accrues only for the wrestler in top position.
    # Maximum possible A advantage at end   = rt_diff + t_rem   (A rides out the rest)
    # Minimum possible A advantage at end   = rt_diff - t_rem   (B rides out the rest)

    max_final = rt_diff + t_rem
    min_final = rt_diff - t_rem

    if min_final >= 60:  return "locked_in"    # A gets the point no matter what
    if max_final < 60 and min_final > -60:
        return "locked_none"                    # nobody can reach 60
    if max_final <= -60: return "locked_out"   # B gets the point no matter what
    return "live"
```

Notes:
- There are really four outcomes: A locked in, B locked in, nobody can reach it, still live. Collapse or keep as data supports, but **never merge "locked" with "live."**
- Verify the exact threshold rule from NCAA rules (1:00 or more, and whether it is ≥ 60 or > 59). Handle the boundary exactly.
- `position` matters for tightening the bound: a wrestler in neutral or bottom cannot accrue until they reach top. Start with the simple bound above; refine only if validation shows the edge cases matter.
- Riding time is typically only relevant in the third period and late second. Keep it in the state everywhere anyway; the table will show it's inert early.

**Conditional:** if the audit shows running riding time is unavailable, drop `rt_status` and `rt_bin` from the state, and add final riding time point to the outcome only. Document this as a known limitation. Do not reconstruct running riding time from final values.

### 2.4 Overtime

Overtime has different rules (sudden victory, tiebreakers, ultimate tiebreaker). Do not mix OT states into the regulation table.

- For regulation, treat "tied at 0:00 of period 3 with no riding time point decided" as a terminal state whose value is the empirical OT win rate for that situation (optionally conditioned on rank signal).
- Build a separate small OT model only if volume allows. Otherwise use the empirical rate.

### 2.5 Terminal states

- Fall, tech fall, injury default, DQ, forfeit: WP jumps to 1 or 0 immediately.
- End of regulation with a margin: WP = 1 or 0 after applying the riding time point.

---

## 3. Base model — empirical table with shrinkage

The design principle: **use real-world data wherever there is enough of it; estimate only where there isn't.** There is no hard switch between methods — the blend is continuous per cell to avoid seams.

### Step 3.1 — Build the empirical table

Extract the state at every event, the state after every event, and the final outcome.

Also sample states at a fixed clock cadence (every 10 seconds of match time) between events, so quiet stretches of a match are represented. Weight these so a long scoreless match isn't overcounted relative to active ones — record `n_matches` (distinct matches touching a cell) as well as `n_obs`.

Output a table keyed by the full state tuple:

- `n_obs` — observations
- `n_matches` — distinct matches contributing
- `wins` — A wins
- `p_emp = wins / n_obs`

### Step 3.2 — Sparsity audit

Produce `reports/sparsity_audit.md` with:

- Histogram of `n_matches` per cell.
- Fraction of **cells** with `n_matches < 50`.
- Fraction of **observed match-moments** landing in cells with `n_matches < 50`. This is the number that matters.
- A map (margin × t_rem heatmap, faceted by position and rt_status) of cell counts.
- The 30 thinnest cells that are actually visited in real matches.

These results decide how much of 3.3 and 3.4 is needed. If thin cells cover a trivial share of real match-moments, keep 3.3 minimal and skip 3.4.

### Step 3.3 — Local smoothing for thin cells

For each cell, compute a neighbor-borrowed estimate:

```
p_smooth(S) = weighted average of p_emp over neighboring cells:
    margin ± 1
    t_rem  ± 1 bin (10 s)
    same position, same choice, same rt_status, same period
weights = neighbor n_matches × kernel distance weight
```

Then blend:

```
w       = n_matches / (n_matches + k)
p_state = w · p_emp + (1 − w) · p_smooth
```

- Tune `k` on held-out log loss. Start the search around 25–200.
- Data-rich cells end up essentially pure empirical. Thin cells lean on their neighbors.

### Step 3.4 — Parametric backstop (conditional)

Only if the sparsity audit shows meaningful real-world traffic through cells where even the neighbors are empty.

Fit a logistic model or monotone-constrained gradient boosting on all data, with features including:

- `margin / sqrt(t_rem + 1)`
- `log(t_rem + 1)`
- `position × t_rem` interaction
- `choice × margin` interaction
- `rt_status`, `rt_bin`, `period`, `rules_era`

Use it as the shrinkage target in place of `p_smooth` when neighbor volume is below a threshold. **Fit it on the full dataset first**, then use it only in the sparse region.

### Step 3.5 — Monotonicity

After blending, enforce that `p_state` is non-decreasing in `margin` holding everything else fixed (isotonic regression along the margin axis per slice is fine). Also verify WP is monotone in riding time advantage within `live`.

A table that says "up 6" is worse than "up 5" in the same situation is a bug. Report how many cells were adjusted and by how much.

---

## 4. Rules eras

Because takedown and near fall values changed mid-window, the same `margin` means different things across eras (a 3-point lead is one takedown after the change and more than one before).

Default approach:
- Build the table with `rules_era` as a state dimension if volume allows.
- If that makes cells too thin, pool eras but add `rules_era` to the smoothing slice so neighbors are borrowed within era first.

Report WP for a few common states side-by-side across eras so the effect is visible.

---

## 5. Strength layer — seed and rank

### 5.1 Inputs

- **NCAA matches:** use tournament **seed**.
- **Conference matches:** use end-of-season **national rank** (top 33). **Do not use conference seed.**
- These are end-of-season / tournament-time values. That is correct for this retrospective model.

### 5.2 Convert to a strength scale

Seeds and ranks are ordinal; raw differences misstate the gaps (1 vs 5 is a much bigger gap than 21 vs 25).

Convert each wrestler's seed or rank to a strength score. Implement both and compare on validation:

**(a) Log-rank:**
```
strength = −log(rank)
```

**(b) Normal quantile (preferred):**
```
N        = assumed pool size for the weight (tune; start ~60–80 for D1)
pct      = (rank − 0.5) / N
strength = −Φ⁻¹(pct)        # Φ⁻¹ = standard normal inverse CDF
```

`rank_signal = strength_A − strength_B`

### 5.3 Unseeded / unranked wrestlers

- Assign a single tail value, **not** "one past the last rank." Unranked wrestlers are a long tail, not the 34th-best.
- Starting value: equivalent rank ~45–60. Treat it as a tunable parameter and fit it on held-out log loss.
- Use separate tail values for NCAA unseeded and conference unranked if the audit shows NCAA seeding depth differs from 33 in some seasons.
- Unranked vs unranked → `rank_signal = 0`. Those matches contribute to the state table but not to fitting the strength layer.

### 5.4 Combining with state

Apply rank as a log-odds shift that fades as the match clock runs out:

```
logit(p_final) = logit(p_state) + β(t_rem) · rank_signal

β(t_rem) = β0 · (t_rem / T_total) ^ γ
```

- `T_total` = regulation match length (420 s).
- Fit `β0` and `γ` on held-out data by minimizing log loss. Expect `γ` near 1, but let the data decide.
- At the start of a tied match, rank carries almost all the information. At 0:05 up by 3, it carries almost none. The decay is essential — without it the model will keep favoring the top seed while he's getting turned.

### 5.5 Fitting data

- Fit `β0`, `γ`, `N`, and the unranked tail value on **NCAA matches first**.
- Then check whether conference matches (both-ranked subset) are consistent with the same parameters. If not, fit a separate `β0` for conference matches.

---

## 6. WPA computation

For every event transitioning `S → S'`:

```
WPA = WP(S') − WP(S)
```

Credit it to the wrestler who caused the event (signed from their perspective). For a reversal, the reverser gets positive WPA. For a penalty or stalling point, credit the wrestler who **committed** the infraction with the negative value, and record the beneficiary.

### 6.1 Event categories — decompose WPA by type

Tag every event so WPA can be broken down:

- **Scoring:** takedown, escape, reversal, near fall (by value), penalty point, stalling point.
- **Position change without points:** e.g. choice selection at period start.
- **Choice:** winning the toss and deferring; the choice made at period 2 and 3 (top / bottom / neutral). Compute choice WPA as `WP(state after choice) − WP(state before choice)`.
- **Riding time:** the moment `rt_status` flips from `live` to `locked_in`/`locked_out`; and the point applied at the end of regulation.
- **Terminal:** fall, tech fall — WPA is whatever remained to reach 1.0.
- **Clock:** time running with no event. Optional — compute "time decay WPA" across quiet stretches for the leading wrestler if useful.

### 6.2 Sanity rules

- A scoring event should almost never produce negative WPA for the scorer. Log any case where it does, with the full before/after state. These are bugs until proven otherwise.
- WPA across a match should sum to `outcome − WP(start)` for each wrestler. Assert this.

---

## 7. Validation

Produce `reports/validation.md` with:

1. **Holdout by tournament year**, not random split. Train on earlier years, test on the most recent 2–3. Also run leave-one-tournament-out cross-validation.
2. **Calibration plot:** predicted WP in deciles vs actual win rate. Must hug the diagonal.
3. **Log loss and Brier score** vs two baselines:
   - margin-only baseline
   - state model without the rank layer
4. **Calibration by rank-gap bucket:** big gap, small gap, both unranked. If big-gap matches are overconfident, `β0` is too high. If the miscalibration is concentrated late in matches, `γ` is off.
5. **Calibration by period** and by `rt_status`.
6. **Hand-checked sanity states** (report model value for each):
   - Tied, 7:00 remaining, neutral, equal seeds → ~0.50
   - Tied, 0:30 left, A on bottom → modestly above 0.50 for A
   - A down 1, start of period 3, A holds choice → close to a coin flip
   - A up 1, 0:05 left, A on top, riding time `live` at 55 s → reflects A likely securing the point
   - Same as above with 0:04 left (point now unreachable) → noticeably different
   - 1 seed vs 16 seed, tied, start of match → heavily favors the 1 seed
   - Same seeds, 1 seed down 3 with 0:10 left in neutral → rank should barely matter
7. **Monotonicity report** from 3.5.
8. **Negative-scoring-WPA report** from 6.2.

---

## 8. Outputs

Write to `outputs/`:

- `state_table.parquet` — every cell with `n_obs`, `n_matches`, `p_emp`, `p_smooth`, `w`, `p_state`
- `model_params.json` — `k`, `β0`, `γ`, `N`, unranked tail values, era handling, bin widths
- `events_wpa.parquet` — one row per event: match id, tournament, season, weight, wrestler, opponent, event type, state before, state after, WP before, WP after, WPA, category
- `wrestler_wpa.csv` — per wrestler per tournament: total WPA, and WPA split by category (scoring, position/choice, riding time, bottom-position WPA, top-position WPA, neutral WPA)
- `match_wp_curves.parquet` — WP over time for every match (for charting)
- `reports/data_audit.md`, `reports/sparsity_audit.md`, `reports/validation.md`

Also produce a simple chart per match of WP over time (step plot, events annotated) for a handful of example matches, including at least one big upset and one late riding-time decision.

---

## 9. Build order

1. **Data audit** (Section 1). Stop and report.
2. Event parsing and state reconstruction for NCAA matches, including the riding time lock function.
3. Empirical state table (3.1), with mirrored perspectives (2.1).
4. **Sparsity audit** (3.2). Stop and report.
5. Local smoothing and shrinkage (3.3). Parametric backstop (3.4) only if the sparsity audit calls for it.
6. Monotonicity enforcement (3.5).
7. Strength layer on NCAA seeds (Section 5); fit `β0`, `γ`, `N`, tail value.
8. Validation (Section 7).
9. WPA computation and decomposition (Section 6).
10. **Second pass:** add conference tournaments. Use national rank, not seed. Add their states to the table, re-run sparsity audit and validation, and check whether conference matches need their own `β0`.
11. Final outputs (Section 8).

---

## 10. Settled design decisions — do not revisit without flagging

- No TPAR.
- Empirical-first. Estimation only fills thin cells, blended continuously by `w = n/(n + k)`. No hard margin cutoff.
- Time bins: 10 seconds.
- Riding time: 10-second bins plus explicit locked/live status.
- Choice is part of the state for both period 2 and period 3.
- NCAA → seed. Conference → national rank (top 33), unranked get a tunable tail value.
- End-of-season / tournament-time seeds and ranks are correct for this retrospective model.
- Strength effect decays with time remaining.
- Live in-season prediction is out of scope.

## 11. Open questions to report back on

- Timestamp quality and fraction of usable matches.
- Whether running riding time and period choice are actually recorded.
- Fraction of conference matches with both wrestlers ranked.
- Share of real match-moments falling in thin cells.
- Whether rules eras need separate tables.
