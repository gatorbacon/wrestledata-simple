# APS/APG/DI v2 Specification

## 0. Purpose

Define **v2** of the scoring/defense/pinning metrics:

- Raw per-7 stats: `PF7`, `PA7`, `PD7`
- Adjusted per-7 stats: `APS7`, `APG7`, `APD7`, `APR`
- Standardized indexes: `SI+`, `DF+`, `PE+`
- Dominance index: `DI+`

Goals:

1. Fix inflation from quick techs vs weak opponents.
2. Make strength of schedule (by **opponent rank**) explicitly baked in.
3. Keep the system tunable via a small set of constants.

## 1. Inputs & Scope

Per **non-fall match** we assume:

- `points_for`
- `points_against`
- `seconds_wrestled`
- `opponent_id`
- `opponent_rank`
- `weight_class`
- `season`

We assume you can fetch:

- ranked list & total_ranked
- per **Weight–Q** quintile stats: PF7_mean, PA7_mean, APS7_mean, APG7_mean, APD7_mean, APR_mean, stds

## 2. Global Constants

PF7_CAP = 25  
PA7_CAP = 25  
PD7_CAP = 20  

SHRINK_K = 8  
MIN_MATCHES_FOR_RAW = 3  

ANCHOR_W_Q = {1:1.00, 2:0.75, 3:0.50, 4:0.30, 5:0.15}  
MIN_WEIGHT_TINY_N = 0.05  

DI_WEIGHT_SI = 0.40  
DI_WEIGHT_DF = 0.45  
DI_WEIGHT_PE = 0.15  

## 3. Per-match PF7 / PA7 / PD7 with Caps

PF7_raw = points_for * 420 / seconds  
PA7_raw = points_against * 420 / seconds  

PF7 = min(PF7_raw, 25)  
PA7 = min(PA7_raw, 25)  
PD7 = clamp(PF7 - PA7, -20, 20)

## 4. Quintiles by Rank

p = (rank - 1) / (total_ranked - 1)

Q1: p <= .20  
Q2: p <= .40  
Q3: p <= .60  
Q4: p <= .80  
Q5: else  

Use PF7_mean_Q(weight,Q) and PA7_mean_Q(weight,Q) from your existing table.

## 5. Shrinkage of Opponent PF7 / PA7

If n_O < 3:
- PF7_adj = PF7_baseline
- PA7_adj = PA7_baseline

Else:
PF7_adj = (n/(n+k))*PF7_raw + (k/(n+k))*PF7_baseline  
PA7_adj = (n/(n+k))*PA7_raw + (k/(n+k))*PA7_baseline  

## 6. Smooth Match Weighting (Option C)

Use rank percentile + quintile anchor interpolation:

Q1→Q2: 1.00→0.75  
Q2→Q3: 0.75→0.50  
Q3→Q4: 0.50→0.30  
Q4→Q5: 0.30→0.15  
Q5 flat at 0.15  

If opponent n < 3: weight = 0.05

## 7. APS7 / APG7 / APR Contributions

APS7_contrib = PF7_match - PA7_adj(opponent)  
APG7_contrib = PF7_adj(opponent) - PA7_match  

Weighted:

APS7_weighted = weight * APS7_contrib  
APG7_weighted = weight * APG7_contrib  
APR_weighted  = weight * APR_contrib  

## 8. Wrestler-level APS7 / APG7 / APR

APS7 = sum(weighted) / sum(weights)  
APG7 = sum(weighted) / sum(weights)  
APR  = sum(weighted) / sum(weights)

APD7 = APS7 + APG7  

## 9. League Means

Compute league means/stds for APS7/APG7/APR per weight/season over population (e.g. all ranked).

## 10. Plus Metrics

SI+ = 100 + 10 * ((APS7 - APS7_mean) / APS7_std)  
DF+ = 100 + 10 * ((APG7 - APG7_mean) / APG7_std)  
PE+ = 100 + 10 * ((APR  - APR_mean)  / APR_std)

## 11. Dominance Index

DI+ = 0.40*SI+ + 0.45*DF+ + 0.15*PE+

## 12. Implementation Checklist

1. Apply caps first  
2. Shrink correctly using PF7_mean_Q, PA7_mean_Q  
3. Use analog weights for APS7/APG7/APR  
4. Weighted means, not simple averages  
5. Plus metrics from league stats  
6. DI+ from configurable params  
