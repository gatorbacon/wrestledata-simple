# Comeback floor (pin from behind)

Built 2026-10-03 by `scripts/wpa/fit_pin_floor.py`. Trailing by 6+ (a locked riding-time point counted as scored), NCAA + conference tournaments, 10-s samples with 4:00 or less left: 60,535 samples from 5,492 bouts, 25 different pin comebacks.

**floor(t) = 0.00135 × (min(seconds left, 180) / 60) ^ 1.549** (max 0.74%, from 3:00 left on) — applied to the final WP in regulation: floor ≤ WP ≤ 1 − floor.

| Time left | Bouts down 6+ then | Trailer won by pin | Raw rate | Floor |
|---|---|---|---|---|
| 5:00 | 642 | 13 | 2.02% | 0.74% |
| 4:00 | 1,222 | 16 | 1.31% | 0.74% |
| 3:00 | 1,960 | 12 | 0.61% | 0.74% |
| 2:30 | 2,252 | 12 | 0.53% | 0.56% |
| 2:00 | 2,553 | 9 | 0.35% | 0.39% |
| 1:30 | 2,815 | 6 | 0.21% | 0.25% |
| 1:00 | 3,207 | 5 | 0.16% | 0.13% |
| 0:30 | 3,603 | 1 | 0.03% | 0.05% |
| 0:10 | 3,920 | 0 | 0.00% | 0.01% |

Each row counts the wrestlers down 6+ at that moment (the same wrestler appears in every row where he was down 6+), so the rows overlap; the curve is fitted on all the samples at once.
