#!/usr/bin/env python3
"""
Build the NCAA seed matchup probability model from historical tournament data.

Loads all_matches.json, filters to truly-seeded championship bracket matches,
fits logistic regression for win probability and OLS for bonus EV, outputs
seed_model.json.

Usage:
  python scripts/ncaa/build_ncaa_seed_model.py
  python scripts/ncaa/build_ncaa_seed_model.py --verbose
"""

import argparse
import json
import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
COMBINED_DIR = DATA_DIR / "ncaa-tourney-parsed"
OUTPUT_PATH = COMBINED_DIR / "seed_model.json"

# Bonus points by result type (matches parse_ncaa_results.py)
BONUS_PTS = {
    "Dec": 0.0, "SV-1": 0.0, "SV-2": 0.0, "SV-3": 0.0,
    "TB-1": 0.0, "TB-2": 0.0, "TB-3": 0.0, "UTB": 0.0,
    "MD": 1.0, "TF": 1.5,
    "Fall": 2.0, "Forfeit": 2.0, "DQ": 2.0, "Inj.": 2.0,
}

# Years where only top-N seeds were official merit seeds
SEEDING_CUTOFF = {
    2013: 12,
    2014: 16, 2015: 16, 2016: 16, 2017: 16, 2018: 16,
    # 2019+: all 33 seeds are merit-based
}

ALL_SEEDS = list(range(1, 34))


def is_truly_seeded(seed: int, year: int) -> bool:
    return seed <= SEEDING_CUTOFF.get(year, 33)


def load_champ_matches():
    """Load championship-bracket, truly-seeded matches."""
    path = COMBINED_DIR / "all_matches.json"
    if not path.exists():
        print(f"ERROR: {path} not found. Run parse_ncaa_results.py first.", file=sys.stderr)
        sys.exit(1)

    all_matches = json.loads(path.read_text())
    filtered = []
    for m in all_matches:
        if m.get("bracket") != "champ":
            continue
        ws = m.get("winner_seed")
        ls = m.get("loser_seed")
        year = m.get("year")
        if ws is None or ls is None:
            continue
        if not is_truly_seeded(ws, year) or not is_truly_seeded(ls, year):
            continue
        filtered.append(m)
    return filtered


# ---------------------------------------------------------------------------
# Logistic regression (pure Python, no scipy dependency required)
# Uses gradient descent to fit: logit(P(lower_seed wins)) = b0 + b1*diff + b2*diff^2
# The quadratic term allows the curve to steepen at large seed differences,
# matching historical data (e.g., seed 1 beats seed 16 ~100% of the time).
# ---------------------------------------------------------------------------

def sigmoid(z):
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    else:
        e = math.exp(z)
        return e / (1.0 + e)


def fit_logistic(X, y, lr=0.008, epochs=10000):
    """Fit two-predictor logistic regression for win probability.

    Model: logit(P(seed_a wins)) = b0 + b1*seed_a + b2*seed_b
    where seed_a < seed_b (seed_a is the better/lower-numbered wrestler).

    Using separate coefficients for seed_a and seed_b (rather than just
    seed_diff) allows the model to distinguish, e.g., seed 1 vs seed 2
    (where seed 1 is historically ~67% favourite) from seed 8 vs seed 9
    (roughly a coin flip), even though both have diff=1.  This is the
    formulation described in the plan:
        logit(P) = β₀ + β₁·seed_a + β₂·seed_b

    X: list of (seed_a, seed_b) tuples (seed_a < seed_b)
    y: list of 1.0 (seed_a won) or 0.0 (seed_b won)
    Returns (b0, b1, b2).

    Expected signs after convergence: b1 < 0 (lower seed number = stronger
    wrestler → wins more), b2 > 0 (higher-numbered opponent → easier to beat).
    """
    b0, b1, b2 = 0.0, -0.05, 0.10
    n = len(X)
    for _ in range(epochs):
        grad_b0 = grad_b1 = grad_b2 = 0.0
        for (xa, xb), yi in zip(X, y):
            p = sigmoid(b0 + b1 * xa + b2 * xb)
            err = p - yi
            grad_b0 += err
            grad_b1 += err * xa
            grad_b2 += err * xb
        b0 -= lr * grad_b0 / n
        b1 -= lr * grad_b1 / n
        b2 -= lr * grad_b2 / n
    return b0, b1, b2


def fit_ols(X, y):
    """OLS with quadratic term: E[y] = a + b*x + c*x^2.
    Returns (intercept, b, c).
    The quadratic term allows bonus EV to curve upward for extreme seed
    mismatches (e.g., seed 1 vs seed 32 historically ~1.23 bonus pts,
    but the linear model capped at ~0.95).
    """
    n = len(X)
    if n == 0:
        return 0.0, 0.0, 0.0
    xs  = [x for (x,) in X]
    xs2 = [x * x for x in xs]

    # Build normal equations for [a, b, c] = inv(X'X) * X'y
    # X matrix columns: [1, x, x^2]
    s0  = float(n)
    s1  = sum(xs)
    s2  = sum(xs2)
    s3  = sum(x ** 3 for x in xs)
    s4  = sum(x ** 4 for x in xs)
    sy0 = sum(y)
    sy1 = sum(xs[i] * y[i] for i in range(n))
    sy2 = sum(xs2[i] * y[i] for i in range(n))

    # Solve 3x3 system via Gaussian elimination
    mat = [
        [s0,  s1,  s2,  sy0],
        [s1,  s2,  s3,  sy1],
        [s2,  s3,  s4,  sy2],
    ]
    for col in range(3):
        pivot = mat[col][col]
        if abs(pivot) < 1e-12:
            # Fall back to linear OLS if matrix is near-singular
            mean_x = s1 / n
            mean_y = sy0 / n
            num = sum((xs[i] - mean_x) * (y[i] - mean_y) for i in range(n))
            den = sum((xs[i] - mean_x) ** 2 for i in range(n))
            b1_lin = num / den if den > 1e-12 else 0.0
            b0_lin = mean_y - b1_lin * mean_x
            return b0_lin, b1_lin, 0.0
        for row in range(3):
            if row != col:
                factor = mat[row][col] / pivot
                for k in range(4):
                    mat[row][k] -= factor * mat[col][k]
    a_coef = mat[0][3] / mat[0][0]
    b_coef = mat[1][3] / mat[1][1]
    c_coef = mat[2][3] / mat[2][2]
    return a_coef, b_coef, c_coef


# ---------------------------------------------------------------------------
# Main model building
# ---------------------------------------------------------------------------

def build_model(matches: list, verbose: bool = False) -> dict:
    """
    Build win probability and bonus EV tables for all seed pairs.

    Win prob model:  logit(P(lower_seed wins)) = b0 + b1*seed_diff + b2*seed_diff^2
    Bonus EV model:  E[winner_bonus] = a + b*seed_diff + c*seed_diff^2

    Both models use a quadratic term so that the curve steepens at large seed
    differences, matching historical NCAA outcomes (e.g., seed 1 is ~100% vs
    seed 16 over 65 matches; seed 1 averages ~1.23 bonus pts vs seed 32).
    """
    # Collect training data
    win_X, win_y = [], []   # (seed_a, seed_b) → lower_seed_wins (0/1)
    # Per-seed bonus stats for winner-based bonus EV
    seed_bonus_stats: dict = {s: [0.0, 0] for s in ALL_SEEDS}

    raw_counts = {}  # (lo, hi) → [wins_by_lo, total]

    for m in matches:
        ws = m["winner_seed"]
        ls = m["loser_seed"]
        lo = min(ws, ls)
        hi = max(ws, ls)
        lower_won = 1 if ws == lo else 0
        bonus = BONUS_PTS.get(m.get("result_type", ""), 0.0)

        win_X.append((float(lo), float(hi)))   # (seed_a, seed_b) both passed
        win_y.append(float(lower_won))

        key = (lo, hi)
        if key not in raw_counts:
            raw_counts[key] = [0, 0]
        raw_counts[key][0] += lower_won
        raw_counts[key][1] += 1

        # Accumulate bonus earned when each seed wins (for bonus EV model)
        seed_bonus_stats[ws][0] += bonus
        seed_bonus_stats[ws][1] += 1

    if not win_X:
        print("ERROR: No matches found after filtering.", file=sys.stderr)
        sys.exit(1)

    if verbose:
        print(f"Training on {len(win_X)} championship-bracket matches")

    # Per-seed average bonus per win (championship bracket)
    # This is a better bonus predictor than seed_diff: the WINNER'S seed determines
    # their bonus-scoring tendencies regardless of the opponent's seed.
    # Default for seeds with no wins: interpolate from adjacent seeds.
    avg_bonus_per_win: dict = {}
    for s in ALL_SEEDS:
        total_b, wins = seed_bonus_stats[s]
        avg_bonus_per_win[s] = (total_b / wins) if wins > 0 else 0.25

    # Fit win probability model
    b0_win, b1_win, b2_win = fit_logistic(win_X, win_y)

    if verbose:
        print(f"Win model: logit(P(seed_a wins)) = {b0_win:.4f} + {b1_win:.4f}*seed_a + {b2_win:.4f}*seed_b")
        print("Per-seed avg bonus/win (championship bracket):")
        for s in [1, 2, 3, 4, 5, 8, 12, 16, 33]:
            print(f"  seed {s:2d}: {avg_bonus_per_win[s]:.3f}")

    # Sanity check spot-checks (seed_a < seed_b)
    checks = [(1, 2), (1, 8), (1, 16), (4, 5), (8, 9), (16, 17)]
    for a, b in checks:
        p = sigmoid(b0_win + b1_win * a + b2_win * b)
        if verbose:
            print(f"  P(seed {a:2d} beats seed {b:2d}) = {p:.3f}")

    # Build output tables for all pairs using Bayesian smoothing:
    # p_final = (n_obs * p_observed + N_PRIOR * p_model) / (n_obs + N_PRIOR)
    # For pairs with many observations the empirical rate dominates;
    # for rare pairs the smooth model prior dominates.
    N_PRIOR = 5

    win_prob = {}
    bonus_ev = {str(s): {} for s in ALL_SEEDS}
    n_obs = {str(s): {} for s in ALL_SEEDS}

    for a in ALL_SEEDS:
        win_prob[str(a)] = {}

        for b in ALL_SEEDS:
            if b <= a:
                continue
            diff = float(b - a)

            # Model (prior) win probability for seed a
            p_model = max(0.01, min(0.99, sigmoid(b0_win + b1_win * a + b2_win * b)))

            # Bayesian blend with observed rate
            rc = raw_counts.get((a, b), [0, 0])
            n, wins_by_lo = rc[1], rc[0]
            if n > 0:
                p_obs = wins_by_lo / n
                p_a_wins = (n * p_obs + N_PRIOR * p_model) / (n + N_PRIOR)
            else:
                p_a_wins = p_model
            p_a_wins = max(0.01, min(0.99, p_a_wins))
            win_prob[str(a)][str(b)] = round(p_a_wins, 6)

            # Bonus EV for match(a, b): weighted average of each seed's avg bonus/win,
            # weighted by their win probability.  This correctly captures that seed 1
            # earns high bonus (~0.62/win) regardless of opponent, while seed 5 earns
            # ~0.42/win.  Using seed_diff as predictor was wrong: it inflated EV for
            # large mismatches (e.g., 5 vs 29 → diff=24 → model EV=0.8) even though
            # seed 5 historically earns only 0.42/win.
            ev = (p_a_wins * avg_bonus_per_win[a]
                  + (1.0 - p_a_wins) * avg_bonus_per_win[b])
            ev = max(0.0, min(2.0, ev))
            bonus_ev[str(a)][str(b)] = round(ev, 6)
            bonus_ev[str(b)][str(a)] = round(ev, 6)

            # Observation count
            obs = n
            n_obs[str(a)][str(b)] = obs
            n_obs[str(b)][str(a)] = obs

    # Enforce monotonicity: for fixed a, P(a wins) must be non-decreasing as b increases.
    # Bayesian blending can create violations when rare pairs have noisy observed rates.
    # Fix by forward-pass maximum (isotonic-style): each probability must be at least
    # as large as the previous one for the same seed_a.
    pre_violations = 0
    for a in ALL_SEEDS:
        bs = [b for b in ALL_SEEDS if b > a]
        running_max = 0.0
        for b in bs:
            p = win_prob[str(a)][str(b)]
            if p < running_max - 1e-6:
                pre_violations += 1
            running_max = max(running_max, p)
            win_prob[str(a)][str(b)] = round(running_max, 6)

    # Validate monotonicity post-fix
    violations = []
    for a in ALL_SEEDS:
        probs = [(b, win_prob[str(a)][str(b)]) for b in ALL_SEEDS if b > a]
        for i in range(len(probs) - 1):
            if probs[i][1] > probs[i + 1][1] + 1e-6:
                violations.append((a, probs[i][0], probs[i][1], probs[i + 1][0], probs[i + 1][1]))

    if pre_violations > 0:
        print(f"INFO: Corrected {pre_violations} monotonicity violations via forward-max pass")
    if violations:
        print(f"WARNING: {len(violations)} monotonicity violations remain after correction")
        if verbose:
            for v in violations[:5]:
                print(f"  seed {v[0]} vs {v[1]}: {v[2]:.4f} > vs {v[3]}: {v[4]:.4f}")

    model = {
        "win_prob": win_prob,
        "bonus_ev_for_winner": bonus_ev,
        "n_obs": n_obs,
        "avg_bonus_per_win": {str(s): round(avg_bonus_per_win[s], 6) for s in ALL_SEEDS},
        "model_params": {
            "win_b0": round(b0_win, 6),
            "win_b1_seed_a": round(b1_win, 6),
            "win_b2_seed_b": round(b2_win, 6),
            "n_training_matches": len(win_X),
            "note": "win_prob: logit(P)=b0+b1*seed_a+b2*seed_b + Bayesian blend (n_prior=5) + monotonicity fix; bonus_ev: P(a)*avg_bonus[a]+P(b)*avg_bonus[b]"
        }
    }
    return model


def print_spot_check(model: dict):
    """Print spot-checks of model probabilities."""
    checks = [
        (1, 2), (1, 8), (1, 16), (1, 33),
        (2, 3), (4, 5), (8, 9), (16, 17),
        (3, 14), (5, 12),
    ]
    print("\nSpot-check win probabilities (lower seed wins):")
    print(f"  {'Pair':12s}  {'P(lo wins)':>12s}  {'P(hi wins)':>12s}  {'n_obs':>6s}")
    for a, b in checks:
        p = model["win_prob"].get(str(a), {}).get(str(b), 0.5)
        obs = model["n_obs"].get(str(a), {}).get(str(b), 0)
        print(f"  {a:2d} vs {b:2d}      {p:12.4f}  {1-p:12.4f}  {obs:6d}")

    print("\nSpot-check bonus EV by seed diff:")
    print(f"  {'Pair':12s}  {'Bonus EV':>10s}")
    for a, b in [(1, 33), (1, 16), (4, 5), (8, 9)]:
        ev = model["bonus_ev_for_winner"].get(str(a), {}).get(str(b), 0.0)
        print(f"  {a:2d} vs {b:2d}      {ev:10.4f}")


def main():
    parser = argparse.ArgumentParser(description="Build NCAA seed matchup model")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    print("Loading championship bracket matches...")
    matches = load_champ_matches()
    print(f"  {len(matches)} matches loaded after filtering")

    print("Fitting models...")
    model = build_model(matches, verbose=args.verbose)

    print_spot_check(model)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(model, indent=2))
    print(f"\nModel saved to {OUTPUT_PATH}")

    params = model["model_params"]
    print(f"Model parameters:")
    print(f"  Win:   b0={params['win_b0']:.4f}  b1(seed_a)={params['win_b1_seed_a']:.4f}  b2(seed_b)={params['win_b2_seed_b']:.4f}")
    print(f"  Bonus: per-seed avg bonus/win (see avg_bonus_per_win in output)")
    print(f"  Trained on {params['n_training_matches']} matches")


if __name__ == "__main__":
    main()
