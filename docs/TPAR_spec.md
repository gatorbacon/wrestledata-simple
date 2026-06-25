# TPAR — Massey/BT Fusion: Official Implementation Spec

**Version:** 1.0  **Status:** canonical  **Companion file:** `tpar_reference.py` (authoritative — your implementation must reproduce its output exactly)

TPAR rates every wrestler in a weight class on a single margin-based scale where the number means *expected scoring margin above a replacement-level wrestler*, with strength of schedule handled structurally rather than by any post-hoc correction. It is built from two ratings — a margin model (Massey) and a win/loss model (Bradley-Terry) — fused together.

This document specifies the system precisely enough to re-implement from scratch. Where prose and `tpar_reference.py` could ever disagree, **the code wins**. A reproduction checklist is at the end so you can confirm a match.

---

## 1. Inputs

The only required inputs are the per-weight match files: `weight_class_<W>.json` for `W ∈ {125,133,141,149,157,165,174,184,197,285}`. Each file:

```
{ "wrestlers": { "<id>": {"name","team","weight_class",...}, ... },
  "matches":   [ {"date","weight_class","wrestler1_id","wrestler2_id","winner_id","result","event"}, ... ] }
```

No bracket/seed file is needed in production. (A tournament bracket CSV was used during development only, to validate against seeds; it is not part of the rating.) NCAA tournament matches live inside these JSONs with `date == "03/21/2026"`.

**Match inclusion:** include *all* matches by default. Provide an `exclude_dates` set (default empty). Setting it to `{"03/21/2026"}` reproduces predictive-test mode (rating the field as if the tournament hadn't happened); this is for evaluation only, not the published rating.

---

## 2. Result → signed margin

Classify each match by the first whitespace-delimited token of its `result` string. The winner receives the positive value, the loser its negation.

| Tokens | Margin |
|---|---|
| `Dec`, `SV-1`, `SV-2`, `SV-3`, `TB-1`, `TB-2`, `TB-3` | 3 |
| `MD` | 4 |
| `TF` | 5 |
| `Fall`, `Inj.`, `DQ` | 6 |
| `MFFL`, `M.` (M. For.), `Def.`, `Forfeit`, anything else | **skip the match** |

Overtime wins (sudden victory, tiebreaker) are decisions (3). Injury default and DQ count as falls (6). Forfeits and medical/defaults carry no information and are dropped entirely (they are not 0-margin matches; they are absent).

---

## 3. Per-weight match graph

Process each weight **independently** (separate networks; no cross-weight edges). For a weight, build the edge list `(winner_id, loser_id, margin)` over included, non-skipped matches. `loser_id` is whichever of `wrestler1_id`/`wrestler2_id` is not `winner_id`. The wrestler set `ids` is every id appearing in any edge, sorted. `matches[i]` (degree) is how many edges a wrestler appears in.

---

## 4. Massey rating (margin model)

Solve the ridge-regularized least-squares system in which, for every match, `margin ≈ rating_winner − rating_loser`.

Build `A` (n×n) and `b` (n) over edges: for each `(w, l, v)` with indices `i, j`: `A[i,i]+=1; A[j,j]+=1; A[i,j]-=1; A[j,i]-=1; b[i]+=v; b[j]-=v`. Then add ridge: `A += LAMBDA * I` with **`LAMBDA = 2.0`**, and solve `A r = b`. The ridge both guarantees invertibility and shrinks thinly-connected wrestlers toward 0 (≈ giving everyone ~2 phantom matches vs an average opponent). Output: `massey[id] = r[idx]`.

---

## 5. Bradley-Terry rating (win/loss model)

Estimate each wrestler's win-power from wins/losses only (margins ignored), via the MM (minorization-maximization) algorithm with regularization.

Accumulate `wins[i]` (count of edges i won) and `games[i][j]` (count of all edges between i and j, both directions). Initialize `p[i] = 1.0`. Repeat for **`BT_ITERS = 500`** iterations:

```
for each i:  num = wins[i] + BT_REG
             den = Σ_j games[i][j] / (p[i] + p[j])  +  2*BT_REG / (p[i] + 1.0)
             new[i] = num/den   (or p[i] if den == 0)
normalize:   p = new / mean(new)        # mean(p) = 1 after each pass
```

with **`BT_REG = 1.0`** (a virtual win+loss vs an average opponent, keeping undefeated wrestlers finite). Output log-strength: `bt[id] = log(max(p[id], 1e-9))`. Fixed init, fixed iteration count, and per-pass mean-normalization make this fully deterministic.

---

## 6. Global BT → Massey alignment

BT and Massey are different units, so before fusing, map BT into Massey units with **one global linear fit** (not per-weight — per-weight standardization is forbidden; it caused a real distortion where champions of lower-variance weights were over-rewarded).

Pool `(bt[i], massey[i])` for **every rated wrestler across all weights**, fit degree-1 `massey ≈ b1·bt + b0` (`numpy.polyfit(all_bt, all_massey, 1)` → `[b1, b0]`). Then `bt_aligned[i] = b0 + b1·bt[i]`. (Reference value: slope ≈ 1.63, intercept ≈ 1.50 on the 2026 data.)

---

## 7. Fusion splits

For Massey weight `wm`, `fused[i] = wm · massey[i] + (1 − wm) · bt_aligned[i]`. Compute and output **all three** splits:

| Split key | wm (Massey) | 1−wm (BT) | Role |
|---|---|---|---|
| `100_0` | 1.00 | 0.00 | pure dominance |
| `75_25` | 0.75 | 0.25 | dominance-led |
| `50_50` | 0.50 | 0.50 | **headline / default** |

The headline TPAR is the **50/50** split. Margin (dominance) and win/loss (results) each carry half: this is the configuration that best matched expert judgment — it correctly ranks champions like Robideau, places Trumble above Bastida, and keeps the top 3 clean while crediting strong undefeated records.

---

## 8. Offset (replacement anchoring)

The offset only sets where "0" sits; **it is a single constant subtracted from everyone in a split, so it never changes ranking or gaps** — only the displayed numbers. Computed independently per split, bracket-free, works any week of any season:

1. Within each weight, rank wrestlers (with `matches ≥ MIN_MATCHES`) by that split's `fused` value, descending; tie-break by ascending `id`.
2. **Weight floor** = mean of the wrestlers in ranks **29–33** (inclusive, 1-based) — i.e. the bottom 5 of the top 33, the "marginal qualifier" tier.
   - *Fallback* (early season, weight has <33 ranked): use the lowest 5 available, or all if fewer than 5.
3. **Global offset** = mean of the 10 weight floors.
4. `tpar[i] = fused[i] − global_offset`.

This makes 0 ≈ a replacement-level qualifier ("Tournament Performance Above **Replacement**" — the name is literally true). Because it's bracket-free, it runs identically in December or March.

**Cosmetic display-shift (optional):** under this anchor the most dominant wrestler lands near +4.8, not +6. The floor-at-0 default makes "above replacement" exact. If you prefer the top to read ~6, add a fixed constant `DISPLAY_SHIFT` to every score (default 0). It changes nothing but the printed numbers. You cannot have floor-at-0 *and* top-at-6 at once without rescaling, which is prohibited (rescaling distorts cross-weight comparison).

---

## 9. Output

For each split, list wrestlers with `matches ≥ MIN_MATCHES = 3` (display threshold only — ratings are computed for everyone), sorted by `tpar` descending, tie-break ascending `name` (deterministic). Each row: `rank, name, team, weight, matches, tpar`. Recommended emit: one table per split (CSV/JSON), plus per-split metadata (`global_offset`, alignment `b0/b1`, whether the tournament was included).

---

## 10. Early-season / cold-start behavior

This system has **no separate low-sample module** and does not need one — unlike TPAR v1, which shrank toward a human rank prior via K_SHRINK because its raw averages were unstable at low n. Here, stability is structural:

- **It will not break.** Massey's ridge (`LAMBDA`) makes the matrix invertible for any sparsity; BT's `BT_REG` keeps undefeated/winless wrestlers finite. No NaNs, no blow-ups on Week 2 data.
- **Shrinkage is built in, toward the field average (0)**, not toward an external rank. A wrestler with few/weakly-connected matches is automatically pulled toward 0.
- **Two honest early-season limits:** (a) ratings are *compressed* early (narrow spread) until match volume grows; (b) Massey/BT can only compare wrestlers through a *connected* match graph, and early-season graphs are fragmented across teams — a wrestler in a still-isolated cluster has a less trustworthy rating until inter-team matches link things up (usually mid-season). The system is simply honest about this rather than masking it with a prior.
- **Practical mitigation:** raise the display threshold early (e.g., `MIN_MATCHES = 5`) to keep one-weekend samples off the public board. The offset's fallback (Section 8) handles weights with <33 ranked wrestlers.

### Optional module: warm-start prior (off by default)
To recover v1-style early-season sharpness without subjective rankings: shrink each wrestler toward **last season's final TPAR** instead of toward 0 (freshmen → 0 or a recruiting-class default), with the prior's weight fading as matches accumulate. Concretely, add `K_WARM` phantom matches per wrestler pinning them to their prior, with `K_WARM` decaying as degree rises (e.g., effective prior weight `K_WARM/(K_WARM + matches)`). This uses the system's own prior-season output as the prior — no human polls — and is the modern successor to v1's K-value idea. Implement as a toggle; keep the core dependency-free.

---

## 11. Determinism & constants

All constants, locked: `LAMBDA = 2.0`, `BT_REG = 1.0`, `BT_ITERS = 500`, `MIN_MATCHES = 3`, `FLOOR_RANKS = (29, 33)`, `DISPLAY_SHIFT = 0`, splits `{100_0:1.0, 75_25:0.75, 50_50:0.5}`, `TOURNAMENT_DATE = "03/21/2026"`. Every step is deterministic given these: linear solve, fixed-iteration MM from a fixed init, a polyfit, and stable tie-broken sorts (value desc, then id or name asc). No randomness, no seeds.

---

## 12. Reproduction checklist (2026 data, tournament included)

A correct implementation produces, at minimum:
- Global alignment slope ≈ **1.63**, intercept ≈ **1.50**.
- **All three splits**: top 3 = Mesenbrink (165), Forrest (133), Barr (197), in that order.
- **50/50**: Sergio Vega (141) at #4; PJ Duke (157) around #8 (not top 3).
- 50/50 global offset ≈ **2.58** (top score ≈ +4.76 for Mesenbrink at `DISPLAY_SHIFT = 0`).
- Small samples suppressed: no 6–7 match wrestler in the top 25.

If those hold, the pipeline matches the reference.
