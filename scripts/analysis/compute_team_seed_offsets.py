#!/usr/bin/env python3
"""
Computes each team's historical seed-relative over/underperformance: on
average, how many more or fewer NCAA points did this program's wrestlers
score than the league-wide average wrestler holding the SAME seed, across
2023-2026?

Motivating example: Penn State wrestlers outscored the league-wide average
at their seed by roughly +1.5 points/wrestler on a recency-weighted,
shrunk basis (39 wrestler-seasons) -- a real, consistent program-strength
effect that a generic rank-based distribution (same for every team) doesn't
capture. Compounded across a 10-man lineup, that's still a meaningful edge.

One correction on top of the raw seed-relative average:

Empirical-Bayes shrinkage -- a single wrestler's tournament score is very
noisy (sigma ~= 3.75 pts, from bracket luck, bonus points, upsets, etc.)
relative to how large real team-level effects actually are (tau ~= 0.7
pts, estimated from the well-sampled teams). A raw average, even from
n=39, is not fully trustworthy on its own: standard error at n=39 is
sigma/sqrt(39) ~= 0.60, almost as large as tau itself. Each team's
average is shrunk toward 0 (the league mean) in proportion to how much
real signal-to-noise it has -- teams with more history keep more of their
raw number; thin/noisy samples get pulled most of the way back to
neutral. This replaces the old hard n>=5 trusted/untrusted cutoff, which
gave a team with n=5 (e.g. American, +1.50 raw) the exact same "full
credit" as a team with n=39 (Penn State) -- despite the n=5 estimate
carrying roughly 2.5x the noise.

We deliberately do NOT recency-weight (e.g. weighting 2026 more than
2023). A split-half test (2023-24 vs 2025-26 offset per team) found the
two halves barely correlate (r ~= 0.10) even for programs with fully
stable coaching across the whole window (Penn State/Cael Sanderson,
Oklahoma State/John Smith) -- team-level performance swings substantially
year to year in a way that doesn't look like smooth, recency-driven
drift. Since there's no clean recency signal to exploit, weighting recent
seasons more would just discard real data (raising noise) without
reducing bias. Using the full flat 4-year window and letting shrinkage
handle uncertainty is the better-supported choice.

Usage:
  python scripts/analysis/compute_team_seed_offsets.py
"""

import json
import statistics
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
COMBINED_DIR = PROJECT_ROOT / "data" / "ncaa-tourney-parsed"

YEARS = [2023, 2024, 2025, 2026]
MIN_N_FOR_TAU_ESTIMATE = 20  # only use well-sampled teams to estimate the true between-team spread

# FloWrestling scrape "school" -> all_wrestlers.json "team" name, where they diverge.
TEAM_ALIASES = {
    "App State": "Appalachian State",
    "Army": "Army West Point",
    "N. Colorado": "Northern Colorado",
    "ND State": "North Dakota State",
    "OK State": "Oklahoma State",
    "SD State": "South Dakota State",
    "SIUE": "SIU Edwardsville",
    "UNI": "Northern Iowa",
    "West Virgnia": "West Virginia",  # apparent site typo
}


def canonical_team(name: str) -> str:
    return TEAM_ALIASES.get(name, name)


def main():
    all_wrestlers = json.loads((COMBINED_DIR / "all_wrestlers.json").read_text())

    by_seed_league = defaultdict(list)
    by_team = defaultdict(list)  # team -> [(seed, points), ...]
    for w in all_wrestlers:
        if w["year"] not in YEARS:
            continue
        by_seed_league[w["seed"]].append(w["total_points"])
        by_team[w["team"]].append((w["seed"], w["total_points"]))

    league_avg_at_seed = {
        seed: statistics.mean(pts) for seed, pts in by_seed_league.items()
    }

    team_diffs = {}   # team -> [diff, ...]
    for team, rows in by_team.items():
        diffs = [pts - league_avg_at_seed[seed] for seed, pts in rows if seed in league_avg_at_seed]
        if diffs:
            team_diffs[team] = diffs

    # sigma^2: pooled within-team variance of individual diffs around each
    # team's own mean -- per-wrestler noise.
    ss, dof = 0.0, 0
    for team, diffs in team_diffs.items():
        n = len(diffs)
        if n >= 2:
            m = statistics.mean(diffs)
            ss += sum((d - m) ** 2 for d in diffs)
            dof += (n - 1)
    sigma2 = ss / dof

    raw_mean = {team: statistics.mean(diffs) for team, diffs in team_diffs.items()}
    n_of = {team: len(diffs) for team, diffs in team_diffs.items()}

    # tau^2: true between-team variance, estimated only from well-sampled
    # teams so noisy small-n teams don't inflate the estimate.
    big_teams = [t for t in raw_mean if n_of[t] >= MIN_N_FOR_TAU_ESTIMATE]
    var_big = statistics.pvariance([raw_mean[t] for t in big_teams])
    avg_noise_big = statistics.mean(sigma2 / n_of[t] for t in big_teams)
    tau2 = max(0.0, var_big - avg_noise_big)

    offsets = {}
    for team in team_diffs:
        n = n_of[team]
        raw = raw_mean[team]
        shrink_weight = tau2 / (tau2 + sigma2 / n) if n > 0 else 0.0
        offsets[team] = {
            "n": n,
            "raw_offset": round(raw, 2),
            "shrinkage_weight": round(shrink_weight, 2),
            "offset": round(shrink_weight * raw, 2),
            "trusted": n >= 5,  # kept for display/UX purposes only; shrinkage now does the real work
        }

    out_path = COMBINED_DIR / "team_seed_offsets.json"
    out_path.write_text(json.dumps({
        "years_included": YEARS,
        "sigma2_per_wrestler_noise": round(sigma2, 3),
        "tau2_between_team_variance": round(tau2, 3),
        "tau2_estimated_from_teams_with_n_at_least": MIN_N_FOR_TAU_ESTIMATE,
        "team_aliases": TEAM_ALIASES,
        "offsets": offsets,
    }, indent=2))

    ranked = sorted(offsets.items(), key=lambda x: -x[1]["offset"])
    print(f"sigma^2 (per-wrestler noise): {sigma2:.3f}   tau^2 (between-team): {tau2:.3f}")
    print()
    print(f"{'Team':<24}{'n':>4}{'raw':>8}{'B':>6}{'shrunk':>8}")
    print("-" * 52)
    for team, o in ranked[:15]:
        print(f"{team:<24}{o['n']:>4}{o['raw_offset']:>8.2f}{o['shrinkage_weight']:>6.2f}{o['offset']:>8.2f}")
    print("...")
    for team, o in ranked[-10:]:
        print(f"{team:<24}{o['n']:>4}{o['raw_offset']:>8.2f}{o['shrinkage_weight']:>6.2f}{o['offset']:>8.2f}")
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
