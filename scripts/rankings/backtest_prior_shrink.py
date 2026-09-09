#!/usr/bin/env python3
"""
Backtest: which PRIOR_SEASON_SHRINK weights best calibrate a returning
wrestler's seeded Elo, measured against their ACTUAL early-season results.

For each candidate config, rebuilds a fully self-consistent Elo chain from
2012 through 2026 (each season's prior-year seed reads the *same config's*
own previously-computed season, entirely in-memory -- no disk writes, no
production files touched). Along the way, for every wrestler who was seeded
from a real prior season, it records the pre-match predicted win probability
(from the seeded Elo, before it's contaminated by any of this season's own
results) against the actual outcome, for that wrestler's first N matches of
the season. Log-loss/Brier/accuracy on exactly that slice isolates the
seed's own quality -- once a wrestler has wrestled enough this season, their
own results dominate and the initial seed stops mattering.

Result of the 2026-09 run (kept here for reference/future re-validation):
counterintuitively, weights ABOVE 1.0 beat every shrink-toward-1500 config
tested, consistently across all three gap tiers and both cutoffs, with
log-loss bottoming out in a flat 1.15-1.30 band for the gap=1 tier and
degrading sharply past ~1.4. Production now uses PRIOR_SEASON_SHRINK =
{1: 1.20, 2: 1.05}, default 0.80 (see calculate_elo_ratings.py for the full
writeup). Re-run this after any season's data materially changes (a data
fix, a new season added) to confirm the config still holds -- the CONFIGS
dict below is left at a validation checkpoint (current production value
plus a no-op and neighbors) rather than the full original sweep.
"""
import sys
import math
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calculate_elo_ratings as elo_mod  # noqa: E402

SEASONS = list(range(2012, 2027))
EVAL_SEASONS = list(range(2016, 2027))  # give the chain a few years to build depth first
EARLY_MATCH_CUTOFFS = (3, 5)  # report both -- "very early" and "settling in"

CONFIGS = {
    "no_seed":     ({1: 0.0, 2: 0.0}, 0.0),      # sanity floor -- confirms seeding helps at all
    "old_shrink":  ({1: 0.75, 2: 0.50}, 0.25),   # pre-backtest default, kept for comparison
    "production":  ({1: 1.20, 2: 1.05}, 0.80),   # current PRIOR_SEASON_SHRINK
    "boost_1.30":  ({1: 1.30, 2: 1.15}, 0.90),   # neighbor -- should track production closely
}


def run_season_instrumented(season, in_memory_elo, max_early):
    league, gender = "ncaa", "men"
    all_matches, wrestler_info = elo_mod.load_ncaa_matches_and_info(season)
    flo_rank_map = elo_mod.load_flo_rank_map(season, league)
    flo_cutoff = elo_mod.get_manual_rank_cutoff(league, gender)
    career_index = elo_mod.build_wid_to_career_seasons()

    seed_gap = {}  # wrestler_id -> gap, only for prior-season-seeded wrestlers

    def find_prior(wid):
        seasons_map = career_index.get(str(wid))
        if not seasons_map:
            return None
        for gap in range(1, elo_mod.PRIOR_SEASON_LOOKBACK_LIMIT + 1):
            prior_season = season - gap
            prior_wid = seasons_map.get(str(prior_season))
            if not prior_wid:
                continue
            entry = in_memory_elo.get(prior_season, {}).get(str(prior_wid))
            if entry and entry.get("has_matches"):
                return entry["elo_score"], gap
        return None

    def initial_elo_for(wid):
        prior = find_prior(wid)
        if prior is not None:
            prior_elo, gap = prior
            seed_gap[wid] = gap
            return elo_mod.seed_from_prior_elo(prior_elo, gap)
        flo_rank = flo_rank_map.get(wid)
        if flo_rank is not None:
            return elo_mod.flo_seed_elo(flo_rank, flo_cutoff)
        return elo_mod.INITIAL_ELO

    wrestlers = {}
    for wid in wrestler_info:
        wrestlers[wid] = {"elo": initial_elo_for(wid), "match_count": 0, "wins": 0, "losses": 0}

    match_list = []
    for m in all_matches:
        d = elo_mod.parse_match_date(m["date"])
        if d:
            match_list.append((d, m))
    match_list.sort(key=lambda x: x[0])

    # log[gap][cutoff] -> list of (pred, actual)
    log = defaultdict(lambda: defaultdict(list))

    for date_obj, match in match_list:
        wid = match["wrestler_id"]
        oid = match.get("opponent_id")
        is_winner = match["is_winner"]

        if wid not in wrestlers:
            wrestlers[wid] = {"elo": initial_elo_for(wid), "match_count": 0, "wins": 0, "losses": 0}
        if oid and oid not in wrestlers:
            wrestlers[oid] = {"elo": initial_elo_for(oid), "match_count": 0, "wins": 0, "losses": 0}

        w_elo, w_mc = wrestlers[wid]["elo"], wrestlers[wid]["match_count"]
        if oid:
            o_elo, o_mc = wrestlers[oid]["elo"], wrestlers[oid]["match_count"]
        else:
            o_elo, o_mc = elo_mod.INITIAL_ELO, 0

        pred_w = elo_mod.calculate_expected_score(w_elo, o_elo)
        actual_w = 1.0 if is_winner else 0.0

        gap = seed_gap.get(wid)
        if gap is not None:
            for cutoff in max_early:
                if w_mc < cutoff:
                    log[gap][cutoff].append((pred_w, actual_w))

        new_w = elo_mod.update_elo(w_elo, o_elo, actual_w, w_mc)
        wrestlers[wid]["elo"] = new_w
        wrestlers[wid]["match_count"] += 1
        wrestlers[wid]["wins" if is_winner else "losses"] += 1

        if oid:
            actual_o = 1.0 - actual_w
            pred_o = elo_mod.calculate_expected_score(o_elo, w_elo)
            gap_o = seed_gap.get(oid)
            if gap_o is not None:
                for cutoff in max_early:
                    if o_mc < cutoff:
                        log[gap_o][cutoff].append((pred_o, actual_o))
            new_o = elo_mod.update_elo(o_elo, w_elo, actual_o, o_mc)
            wrestlers[oid]["elo"] = new_o
            wrestlers[oid]["match_count"] += 1
            wrestlers[oid]["wins" if actual_o == 1.0 else "losses"] += 1

    return wrestlers, log


def logloss(pairs):
    eps = 1e-9
    total = 0.0
    for p, a in pairs:
        p = min(max(p, eps), 1 - eps)
        total += -(a * math.log(p) + (1 - a) * math.log(1 - p))
    return total / len(pairs) if pairs else None


def brier(pairs):
    if not pairs:
        return None
    return sum((p - a) ** 2 for p, a in pairs) / len(pairs)


def accuracy(pairs):
    if not pairs:
        return None
    correct = sum(1 for p, a in pairs if (p >= 0.5) == (a == 1.0))
    return correct / len(pairs)


def run_config(name, shrink_tiers, shrink_default):
    elo_mod.PRIOR_SEASON_SHRINK = shrink_tiers
    elo_mod.PRIOR_SEASON_SHRINK_DEFAULT = shrink_default
    elo_mod._career_seasons_cache = None

    in_memory_elo = {}
    # combined log across all eval seasons: gap -> cutoff -> pairs
    combined = defaultdict(lambda: defaultdict(list))

    for season in SEASONS:
        wrestlers, log = run_season_instrumented(season, in_memory_elo, EARLY_MATCH_CUTOFFS)
        in_memory_elo[season] = {
            wid: {"elo_score": d["elo"], "has_matches": d["match_count"] > 0}
            for wid, d in wrestlers.items()
        }
        if season in EVAL_SEASONS:
            for gap, by_cutoff in log.items():
                for cutoff, pairs in by_cutoff.items():
                    combined[gap][cutoff].extend(pairs)

    return combined


def main():
    results = {}
    for name, (tiers, default) in CONFIGS.items():
        print(f"Running config: {name} = {tiers}, default={default} ...", flush=True)
        results[name] = run_config(name, tiers, default)

    for cutoff in EARLY_MATCH_CUTOFFS:
        print(f"\n{'='*90}")
        print(f"EARLY MATCH CUTOFF: first {cutoff} matches of the season, gap=1 (returning next year)")
        print(f"{'='*90}")
        print(f"{'config':<14}{'n':>8}{'log_loss':>12}{'brier':>10}{'accuracy':>10}")
        for name in CONFIGS:
            pairs = results[name].get(1, {}).get(cutoff, [])
            ll, br, acc = logloss(pairs), brier(pairs), accuracy(pairs)
            print(f"{name:<14}{len(pairs):>8}{ll:>12.4f}{br:>10.4f}{acc:>10.3f}" if pairs else f"{name:<14} no data")

        print(f"\ngap=2 (one-year layoff), first {cutoff} matches:")
        print(f"{'config':<14}{'n':>8}{'log_loss':>12}{'brier':>10}{'accuracy':>10}")
        for name in CONFIGS:
            pairs = results[name].get(2, {}).get(cutoff, [])
            ll, br, acc = logloss(pairs), brier(pairs), accuracy(pairs)
            print(f"{name:<14}{len(pairs):>8}{ll:>12.4f}{br:>10.4f}{acc:>10.3f}" if pairs else f"{name:<14} no data")

        print(f"\ngap>=3 (multi-year layoff), first {cutoff} matches:")
        print(f"{'config':<14}{'n':>8}{'log_loss':>12}{'brier':>10}{'accuracy':>10}")
        for name in CONFIGS:
            pairs = []
            for g, by_cutoff in results[name].items():
                if g >= 3:
                    pairs.extend(by_cutoff.get(cutoff, []))
            ll, br, acc = logloss(pairs), brier(pairs), accuracy(pairs)
            print(f"{name:<14}{len(pairs):>8}{ll:>12.4f}{br:>10.4f}{acc:>10.3f}" if pairs else f"{name:<14} no data")


if __name__ == "__main__":
    main()
