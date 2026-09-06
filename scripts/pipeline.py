#!/usr/bin/env python3
"""
Interactive menu wrapper for the weekly data pipeline (scrape -> process ->
rank). Pick a track (NCAA / HS Boys / HS Girls) and a season, then step
through the process in order -- or jump around freely.

No persistence: progress is tracked only in memory for the current session.
Run it again tomorrow and every step starts unchecked again.

Each step runs as a real subprocess with stdin/stdout/stderr wired straight
through to your terminal, so the interactive prompts inside the underlying
scripts (alias y/n, data-integrity y/n, etc.) work exactly as if you'd run
them directly.

Usage:
    .venv/bin/python scripts/pipeline.py
    .venv/bin/python scripts/pipeline.py ncaa 2026       # skip the track/season prompts
    .venv/bin/python scripts/pipeline.py boys            # track given, still asks for season
"""
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

TRACKS = {
    "1": {"label": "NCAA (Men)", "league": "ncaa", "gender": "men", "state": None,
          "aliases": ["ncaa"]},
    "2": {"label": "HS Boys (KY)", "league": "hs", "gender": "boys", "state": "KY",
          "aliases": ["boys", "hs-boys", "hsboys"]},
    "3": {"label": "HS Girls (KY)", "league": "hs", "gender": "girls", "state": "KY",
          "aliases": ["girls", "hs-girls", "hsgirls"]},
}

DEFAULT_SEASON = "2026"


def resolve_track(arg: str):
    """Match a CLI arg against a track's menu number (1/2/3) or alias
    (ncaa, boys, girls, ...), case-insensitive. Returns None if no match."""
    key = arg.strip().lower()
    if key in TRACKS:
        return TRACKS[key]
    for t in TRACKS.values():
        if key in t["aliases"]:
            return t
    return None


def common_flags(track):
    """-league/-gender[/-state] flags shared by every step, in the order
    used throughout this repo's scripts."""
    flags = ["-league", track["league"], "-gender", track["gender"]]
    if track["state"]:
        flags += ["-state", track["state"]]
    return flags


def flo_season_label(season: str) -> str:
    """scrape_flo_preseason_rankings.py wants '2025-26', not the plain '2026'
    season string used everywhere else in this pipeline."""
    y = int(season)
    return f"{y - 1}-{str(y)[2:]}"


def build_steps(track, season):
    py = sys.executable  # the venv interpreter running this wrapper
    flags = common_flags(track)

    steps = [
        {
            "name": "Get Teams",
            "cmds": [[py, "scripts/scrape_ncaa_d1_teams.py", *flags, "-season", season]],
        },
        {
            "name": "Season Scraper",
            "cmds": [[py, "wrestle_scraper_raw_mt_locked.py", *flags, "-season", season, "-headless"]],
        },
    ]

    # NCAA only -- the Season Scraper step above does a full open(path, "w")
    # overwrite of mt/data/ncaa_men/{season}/{team}.json every run (confirmed
    # in wrestle_scraper_raw_mt_locked.py's save_team_data(), no merge), which
    # wipes the grade/hometown/photo_url/previous_school fields the official-
    # roster enrichment writes onto that same file. Must re-run both scripts
    # after every scrape, not just once, or the very next weekly scrape wipes
    # them again. Neither takes a -season flag -- both scan whatever's on
    # disk under mt/data/official_rosters/ and mt/data/roster_links/ across
    # every team+season, and are safe/cheap to run every time (pure local
    # JSON reads/writes, no network) even when this run's season isn't the
    # one that changed.
    if track["league"] == "ncaa":
        steps.append({
            "name": "Rebuild Official Roster Links",
            "cmds": [[py, "scripts/analysis/match_official_rosters_to_trackwrestling.py"]],
        })
        steps.append({
            "name": "Re-apply Roster Enrichment (grade/hometown/photo)",
            "cmds": [[py, "scripts/enrichment/enrich_ncaa_rosters.py"]],
        })

    steps += [
        {
            "name": "Post Process #1 - Applying Aliases",
            # season is a positional arg for this one, not -season
            "cmds": [[py, "scripts/apply_name_aliases.py", season, *flags]],
        },
        {
            "name": "Post Process #2 - Data Verification and Parsing",
            "cmds": [[py, "scripts/process_raw_matches_by_season.py", "-season", season, *flags]],
        },
        {
            "name": "Load Data for Ranking",
            "cmds": [[py, "scripts/rankings/load_data.py", "-season", season, "-save", *flags]],
        },
        {
            "name": "Build Relationships",
            "cmds": [[py, "scripts/rankings/build_relationships.py", "-season", season, "-save", *flags]],
        },
        {
            "name": "Ranking Bands",
            "cmds": [[py, "scripts/rankings/ranking_bands.py", "-season", season, *flags]],
        },
    ]

    if track["league"] == "ncaa":
        steps.append({
            "name": "Import Flo Rankings",
            "cmds": [
                [py, "scripts/scraping/scrape_flo_preseason_rankings.py",
                 "--season", flo_season_label(season), "--latest"],
                [py, "scripts/rankings/apply_flo_rankings.py", "-season", season],
            ],
        })

    steps.append({
        "name": "Create Ranking Matrix",
        "cmds": [[py, "scripts/rankings/generate_matrix.py", "-season", season, *flags]],
    })

    is_hs = track["league"] == "hs"
    is_ncaa = not is_hs
    gender = track["gender"]
    state = track["state"]

    # ---- Phase 2 ----

    # xTP hard-crashes (FileNotFoundError) without rankings_starters_<weight>.json,
    # even though TPAR and wrestler profiles don't really need it -- confirmed
    # by reading both scripts directly. Keep it for both tracks.
    if is_ncaa:
        starter_cmd = [py, "scripts/rankings/build_starter_rankings.py", "-season", season, "-league", "ncaa"]
    else:
        starter_cmd = [py, "scripts/rankings/build_starter_rankings.py", "-season", season, "-league", "hs", "-state", state]
    steps.append({"name": "Build Starter-Only Rankings", "cmds": [starter_cmd]})

    # calculate_elo_ratings.py uses -- (double-dash) flags, unlike almost
    # everything else in this pipeline -- confirmed from its argparse, not
    # a typo. NCAA invocation is new this session (previously HS-only, since
    # NCAA was fully hand-curated before the Flo/ELO hybrid plan).
    if is_ncaa:
        elo_cmd = [py, "scripts/rankings/calculate_elo_ratings.py", "-season", season, "--league", "ncaa", "--gender", "men"]
    else:
        elo_cmd = [py, "scripts/rankings/calculate_elo_ratings.py", "-season", season, "--league", "hs", "--gender", gender, "--state", state]
    steps.append({"name": "Hybrid Ranks (ELO)", "cmds": [elo_cmd]})

    # MV = TPAR (docs/matsavant.md gotcha #1). -gender only accepts
    # men/women here and is documented "Not used for HS" -- one combined
    # call covers both HS genders, matching the script's own design.
    if is_ncaa:
        mv_cmd = [py, "scripts/mat_value/compute_all_mat_values.py", "--season", season, "-league", "ncaa", "-gender", "men"]
    else:
        mv_cmd = [py, "scripts/mat_value/compute_all_mat_values.py", "--season", season, "-league", "hs", "-state", state]
    steps.append({"name": "Compute Mat Value (TPAR)", "cmds": [mv_cmd]})

    # Rolling per-date TPAR trajectory for the profile page's chart trendline
    # + hover. Reads only weight_class_<weight>.json (already produced by
    # Load Data above), independent of Mat Value / Hybrid Ranks -- safe to
    # rerun any time, and self-contained (doesn't touch mat_value_<season>.json
    # or any wrestler profile). NCAA-only; no HS equivalent.
    if is_ncaa:
        steps.append({
            "name": "Compute Rolling TPAR Trajectory",
            "cmds": [[py, "scripts/mat_value/compute_rolling_mbt.py", "--season", season]],
        })

    # Wrestler profiles also compute SI+/DF+/PE+/DI+. HS needs a separate
    # call per gender (profiles live in gender-specific dirs); NCAA is one
    # call. Runs twice in the full flow -- see the second pass below, which
    # picks up bonus/xTP/season-accomplishments data that doesn't exist yet
    # on this first pass.
    def wrestler_profiles_cmds():
        if is_ncaa:
            return [[py, "scripts/rankings/build_wrestler_profiles.py", "-season", season]]
        return [
            [py, "scripts/rankings/build_wrestler_profiles.py", "-season", season, "-league", "hs", "-state", state, "-gender", "boys"],
            [py, "scripts/rankings/build_wrestler_profiles.py", "-season", season, "-league", "hs", "-state", state, "-gender", "girls"],
        ]
    steps.append({"name": "Build Wrestler Profiles", "cmds": wrestler_profiles_cmds()})

    # NCAA's search index is a single shared, non-season-scoped file
    # (frontend/wrestledata-ui/public/search_index.js) -- it always represents
    # whichever season last built it, unlike HS's career-aware version. Running
    # this for a backfill season overwrites the LIVE site's search with stale
    # data; only ever run it for the current season (DEFAULT_SEASON).
    if is_ncaa and season != DEFAULT_SEASON:
        steps.append({
            "name": "Build Search Index",
            "cmds": [],
            "disabled": True,
            "note": f"Skipped for backfill season {season} -- NCAA search index is a single shared file "
                    f"representing whatever season last built it (no per-season path). Running this for a "
                    f"non-current season would overwrite the live site's search with stale data. Only run "
                    f"for season {DEFAULT_SEASON}.",
        })
    else:
        if is_ncaa:
            search_cmd = [py, "scripts/generate_search_index.py", "-league", "ncaa", "-season", season]
        else:
            search_cmd = [py, "scripts/generate_search_index.py", "-league", "hs", "-gender", "both", "-season", season]
        steps.append({"name": "Build Search Index", "cmds": [search_cmd]})

    # Same "-gender not used for HS" shape as Mat Value above.
    if is_ncaa:
        bonus_cmd = [py, "scripts/bonus/compute_all_top33_bonus.py", "--season", season, "-league", "ncaa", "-gender", "men"]
    else:
        bonus_cmd = [py, "scripts/bonus/compute_all_top33_bonus.py", "--season", season, "-league", "hs", "-state", state]
    steps.append({"name": "Compute Bonus Data", "cmds": [bonus_cmd]})

    if is_ncaa:
        xtp_cmd = [py, "scripts/xtp/run_team_xtp.py", "--season", season, "--rebuild-weights", "--limit", "25"]
    else:
        xtp_cmd = [py, "scripts/xtp/run_team_xtp.py", "--season", season, "--rebuild-weights", "--limit", "25", "-league", "hs", "-state", state]
    steps.append({"name": "Run Team xTP", "cmds": [xtp_cmd]})

    # Backtests the live Team Championship Odds model against every
    # completed season's real top-3 finishers. Seasons are discovered from
    # what's on disk (needs that season's NCAAs already scraped+parsed), so
    # this is safe/idempotent to run every time -- it only picks up a new
    # season once one becomes eligible. NCAA-only; no HS equivalent.
    if is_ncaa:
        backtest_cmd = [py, "scripts/analysis/build_top3_backtest.py"]
        steps.append({"name": "Build Top-3 Season Backtest", "cmds": [backtest_cmd]})

    # team_profiles/team_metrics/public_matrix/public_rankings/simple_leaderboards
    # all process BOTH HS genders in one call when -gender is omitted
    # (confirmed in each script's own argparse help text) -- matching your
    # literal commands, not a per-track split like wrestler profiles above.
    # Same shared-non-season-scoped-path issue as the search index above --
    # build_team_profiles.py's NCAA output (frontend/wrestledata-ui/public/data/teams/{team}.json)
    # has no season subdirectory at all, so building it for a backfill season
    # silently overwrites the LIVE site's team pages (confirmed: this happened
    # while backfilling 2023, caught via git status, restored via a rerun at
    # DEFAULT_SEASON). Skip entirely for NCAA backfills -- team.html itself
    # also hardcodes the current season, so a historical team profile has no
    # frontend consumer anyway.
    ncaa_team_profiles_unsafe = is_ncaa and season != DEFAULT_SEASON

    def team_profiles_cmds():
        if is_ncaa:
            return [[py, "scripts/teams/build_team_profiles.py", "--season", season, "-league", "ncaa"]]
        return [[py, "scripts/teams/build_team_profiles.py", "--season", season, "-league", "hs", "-state", state]]

    def team_profiles_step(name):
        if ncaa_team_profiles_unsafe:
            return {
                "name": name, "cmds": [], "disabled": True,
                "note": f"Skipped for backfill season {season} -- NCAA team profiles share one "
                        f"non-season-scoped path per team (no per-season path), and team.html always "
                        f"shows the current season regardless, so a historical build has no frontend "
                        f"consumer and would only overwrite the live {DEFAULT_SEASON} team pages.",
            }
        return {"name": name, "cmds": team_profiles_cmds()}

    steps.append(team_profiles_step("Build Team Profiles"))

    if is_ncaa:
        metrics_cmd = [py, "scripts/team_metrics/build_team_metrics.py", "--season", season, "-league", "ncaa"]
    else:
        metrics_cmd = [py, "scripts/team_metrics/build_team_metrics.py", "--season", season, "-league", "hs", "-state", state]
    steps.append({"name": "Build Team Metrics", "cmds": [metrics_cmd]})

    # NCAA: --flo-only caps the public matrix at FloWrestling's own ranked
    # count per weight (the "flo_ranked" tag apply_flo_rankings.py writes),
    # not --starters-only's unrelated roster/lineup concept.
    #
    # -rankings-dir/-relationships-dir must be explicit for NCAA: the
    # script's own default (frontend/wrestledata-ui/public/data/rankings)
    # only ever receives the *starters* subset from a different step, never
    # the base rankings_<weight>.json -- the real live data (matching your
    # manual matrix download-and-copy workflow, and where apply_flo_rankings.py
    # writes) is mt/rankings_data/ncaa_men/<season>/. Confirmed by reading
    # generate_matrix.py's own path resolution directly. HS's default
    # already resolves correctly on its own (script has HS-specific
    # substitution logic), so it's left alone here.
    if is_ncaa:
        matrix_json_cmd = [py, "scripts/generate_public_matrix.py", "-season", season, "-league", "ncaa",
                            "-rankings-dir", "mt/rankings_data/ncaa_men",
                            "-relationships-dir", "mt/rankings_data/ncaa_men", "--flo-only"]
    else:
        matrix_json_cmd = [py, "scripts/generate_public_matrix.py", "-season", season, "-league", "hs", "-state", state]
    steps.append({"name": "Generate Public Matrix JSON", "cmds": [matrix_json_cmd]})

    # NCAA now shows exactly FloWrestling's own ranked wrestlers (per
    # entry.flo_ranked, whatever count that is per weight), not is_starter
    # and not the hybrid-ELO tail -- that stays internal-only for now. The
    # script hardcodes the right source dir (mt/rankings_data/ncaa_men)
    # for this itself, no -rankings-dir override needed here.
    if is_ncaa:
        pub_rank_cmd = [py, "scripts/generate_public_rankings.py", "--season", season, "-league", "ncaa"]
    else:
        pub_rank_cmd = [py, "scripts/generate_public_rankings.py", "--season", season, "-league", "hs", "-state", state]
    steps.append({"name": "Generate Public Rankings", "cmds": [pub_rank_cmd]})

    if is_ncaa:
        # Not built yet: generate_dual_predictor_data.py is HS-specific
        # (hardcoded hs_ky_boys/hs_ky_girls paths, boys/girls branching
        # throughout, no -league flag at all) -- adding NCAA support is a
        # real refactor, not a flag. Listed here (disabled) as a marker so
        # it doesn't get forgotten, not as something to run today.
        steps.append({
            "name": "Dual Prediction Files",
            "cmds": [],
            "disabled": True,
            "note": "Not built for NCAA yet -- generate_dual_predictor_data.py is HS-only today.",
        })
    else:
        steps.append({
            "name": "Dual Prediction Files",
            "cmds": [[py, "scripts/rankings/generate_dual_predictor_data.py", "-season", season, "-gender", gender]],
        })

    if is_hs:
        # Structurally HS-only: pattern-matches literal KHSAA tournament
        # names ("KHSAA Region 1-8", "KHSAA Final Round State Championship")
        # with no NCAA equivalent shape (conference tourneys -> NCAAs).
        steps.append({
            "name": "Season Accomplishments",
            "cmds": [[py, "scripts/season_accomplishments/generate_season_accomplishments.py",
                      "--season", season, "--gender", gender, "--state", state.lower()]],
        })

        # HS only -- NCAA support exists as a --league flag but isn't
        # actually wired up (still hardcodes hs_ky_{gender} team-abbreviation
        # paths regardless of --league), so it wouldn't work today.
        def match_highlights_cmds():
            from datetime import date, timedelta
            default_end = date.today()
            default_start = default_end - timedelta(days=6)
            print(f"\nBiggest Upsets / Match Highlights needs a date range (which week to feature).")
            start = input(f"Start date [{default_start.isoformat()}]: ").strip() or default_start.isoformat()
            end = input(f"End date [{default_end.isoformat()}]: ").strip() or default_end.isoformat()
            return [[py, "scripts/rankings/generate_match_highlights.py",
                     "--start-date", start, "--end-date", end, "--season", season,
                     "--gender", gender, "--state", state]]
        steps.append({"name": "Biggest Upsets / Match Highlights", "build_cmds": match_highlights_cmds})

    # Second pass: bonus data, xTP, and (for HS) season accomplishments were
    # all computed AFTER the first profile build above, so profiles need
    # rebuilding once more to actually pick them up. build_wrestler_profiles.py
    # has explicit "preserve existing bonus data" logic specifically so this
    # second pass doesn't wipe out what compute_all_top33_bonus.py wrote.
    # Team profiles then need this second, now-complete wrestler data for
    # their own rollups (bonus_rate, etc.) -- confirmed via the actual
    # read/write dependencies in both scripts, not assumed.
    steps.append({"name": "Build Wrestler Profiles (2nd pass)", "cmds": wrestler_profiles_cmds()})
    steps.append(team_profiles_step("Build Team Profiles (2nd pass)"))

    if is_hs:
        from datetime import date
        today = date.today().isoformat()
        steps.append({
            "name": "Official Rankings Drop",
            "cmds": [
                [py, "scripts/rankings/create_rankings_release.py", "-season", season, "-gender", "boys",
                 "-drop-id", today, "--archive", "--pdf", "--jpg"],
                [py, "scripts/rankings/create_rankings_release.py", "-season", season, "-gender", "girls",
                 "-drop-id", today, "--archive", "--pdf", "--jpg"],
            ],
        })

        # HS only -- no NCAA "career" concept exists anywhere in this repo yet.
        steps.append({
            "name": "Career Profiles",
            "cmds": [
                [py, "scripts/rankings/build_career_profiles.py", "--gender", "boys"],
                [py, "scripts/rankings/build_career_profiles.py", "--gender", "girls"],
            ],
        })

    # build_simple_leaderboards.py is dual-league (per-season stat leaderboards,
    # both sites' JS consume it). build_leaderboards.py is HS-only by its own
    # docstring/argparse (choices=["hs"]) and its --all-time-career-wins flag
    # depends on the HS-only career-profile system built just above -- these
    # are two separate, non-overlapping scripts, not two ways to do one thing.
    if is_ncaa and season != DEFAULT_SEASON:
        # Same shared-path issue again: NCAA leaderboards write to
        # frontend/wrestledata-ui/public/data/leaderboards/*.json with no
        # season subdirectory -- confirmed this overwrote the live 2026
        # leaderboards while backfilling both 2023 and 2024. Only safe for
        # the current season.
        steps.append({
            "name": "Generate Leaderboards", "cmds": [], "disabled": True,
            "note": f"Skipped for backfill season {season} -- NCAA leaderboards share one "
                    f"non-season-scoped path (no per-season path). Running this for a non-current "
                    f"season overwrites the live site's leaderboards with stale data. Only run for "
                    f"season {DEFAULT_SEASON}.",
        })
    else:
        if is_ncaa:
            leaderboard_cmds = [[py, "scripts/build_simple_leaderboards.py", "--season", season, "-league", "ncaa"]]
        else:
            leaderboard_cmds = [
                [py, "scripts/build_simple_leaderboards.py", "--season", season, "-league", "hs", "-state", state],
                [py, "scripts/build_leaderboards.py", "-season", season, "--all-time-career-wins"],
            ]
        steps.append({"name": "Generate Leaderboards", "cmds": leaderboard_cmds})

    if is_hs:
        # KentuckyMat-only (hardcodes frontend/hs-ky-ui/ and kentuckymat.com),
        # covers the whole site in one pass -- no gender split needed, and no
        # NCAA equivalent since matsavant.com content isn't included at all.
        steps.append({"name": "Generate Sitemap", "cmds": [[py, "scripts/generate_sitemap.py"]]})

    return steps


def choose_track():
    print("\nWhich track are you running?")
    for key, t in TRACKS.items():
        print(f"  {key}. {t['label']}")
    while True:
        choice = input("> ").strip()
        if choice in TRACKS:
            return TRACKS[choice]
        print("Invalid choice, try again.")


def choose_season():
    season = input(f"\nSeason [{DEFAULT_SEASON}]: ").strip()
    return season or DEFAULT_SEASON


def print_menu(steps, done, last_run_idx):
    print("\n" + "=" * 60)
    print("PIPELINE STEPS")
    print("=" * 60)
    for i, step in enumerate(steps):
        if step.get("disabled"):
            mark = "🚫"
        elif i in done:
            mark = "✅"
        else:
            mark = "⬜"
        print(f"  {mark} {i + 1}. {step['name']}")

    # "Next" is positional -- whatever comes right after the step you most
    # recently ran, not the first one you haven't done yet. Running step 7
    # straight out of the gate recommends 8 next, not 1, even though 1-6
    # were skipped and never marked done. Skips over any disabled step in
    # between. First run of the session (nothing run yet) starts at step 1.
    start = 0 if last_run_idx is None else last_run_idx + 1
    next_idx = None
    for i in range(start, len(steps)):
        if not steps[i].get("disabled"):
            next_idx = i
            break
    print("=" * 60)
    if next_idx is not None:
        print(f"Recommended next: {next_idx + 1}. {steps[next_idx]['name']}")
        print("Press Enter to run it, type a step number to jump, or 'q' to quit.")
    else:
        print("All steps complete for this session!")
        print("Type a step number to re-run one, or 'q' to quit.")
    return next_idx


def run_step(step):
    """Run every command in this step in sequence, stopping at the first
    failure. A step with multiple commands (e.g. scrape-then-apply) only
    counts as done if all of them succeed. A step with "build_cmds" instead
    of a static "cmds" list gets it called here (at run time, not menu-build
    time) so it can prompt for extra input first, e.g. a date range."""
    cmds = step["build_cmds"]() if "build_cmds" in step else step["cmds"]
    for cmd in cmds:
        print("\n" + "=" * 60)
        print(f"Running: {step['name']}")
        print(f"$ {' '.join(str(c) for c in cmd)}")
        print("=" * 60 + "\n")
        result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
        if result.returncode != 0:
            return False
    return True


def main():
    argv = sys.argv[1:]
    track = None
    season = None

    if len(argv) >= 1:
        track = resolve_track(argv[0])
        if track is None:
            valid = ", ".join(sorted({a for t in TRACKS.values() for a in t["aliases"]}))
            print(f"Unknown track '{argv[0]}'. Valid: {valid} (or 1/2/3).")
            sys.exit(1)
    if len(argv) >= 2:
        season = argv[1].strip()

    if track is None:
        track = choose_track()
    if season is None:
        season = choose_season()

    steps = build_steps(track, season)
    done = set()
    last_run_idx = None  # drives "recommended next" -- see print_menu()

    print(f"\nTrack: {track['label']}   Season: {season}")

    while True:
        next_idx = print_menu(steps, done, last_run_idx)
        choice = input("> ").strip().lower()

        if choice in ("q", "quit", "exit"):
            print("Bye.")
            break

        if choice == "" and next_idx is not None:
            idx = next_idx
        else:
            try:
                idx = int(choice) - 1
                if not (0 <= idx < len(steps)):
                    raise ValueError
            except ValueError:
                print("Invalid input.")
                continue

        if steps[idx].get("disabled"):
            note = steps[idx].get("note", "This step isn't available yet.")
            print(f"\n🚫 '{steps[idx]['name']}' is not runnable yet: {note}")
            continue

        success = run_step(steps[idx])
        last_run_idx = idx
        if success:
            done.add(idx)
        else:
            print(f"\n⚠️  '{steps[idx]['name']}' exited with a non-zero status. Not marked complete.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nBye.")
        sys.exit(0)
