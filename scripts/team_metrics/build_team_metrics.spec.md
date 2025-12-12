# FILE: scripts/team_metrics/build_team_metrics.spec.md
# PURPOSE: STEP-BY-STEP IMPLEMENTATION SPEC for Cursor
# IMPORTANT: This script MUST run AFTER build_wrestler_profiles.py

## Script
Create: scripts/team_metrics/build_team_metrics.py

## CLI
python scripts/team_metrics/build_team_metrics.py \
  --season 2026 \
  --teams-list data/team_lists/2026/ncaa_d1_teams.json \
  --rankings-dir mt/rankings_data/2026 \
  --starter-overrides mt/rankings_data/2026/starter_overrides.json \
  --wrestler-profiles-dir mt/wrestlers/2026/by_id \
  --out-file mt/team_metrics/2026/team_metrics.json \
  --debug-team "Virginia Tech"

### Args
--season (int, required)
--teams-list (path, required)
--rankings-dir (path, required)
--starter-overrides (path, optional; if missing treat as empty overrides)
--wrestler-profiles-dir (path, required)
--out-file (path, required)
--debug-team (string, optional; matches by team name OR team_id)
--no-roster (optional bool) if you want to skip embedding roster lists in output (default: embed rosters)

## Inputs (source of truth)
1) Team list (D1)
- data/team_lists/<season>/ncaa_d1_teams.json
- Each entry has: name, abbreviation, governing_body, division, url, etc.
- Use this list as the authoritative set of teams to output (D1 only).

2) Starter selection + ranks
- mt/rankings_data/<season>/ranking_<weight>.json
  - Contains rankings[] entries with: rank, wrestler_id, name, team, record, is_starter
- mt/rankings_data/<season>/starter_overrides.json
  - force_backup_ids: [wrestler_id,...]
  - Any wrestler_id in force_backup_ids must be treated as is_starter=false even if ranking file says true.
  - If forced false removes the starter, choose the next-highest ranked wrestler at that weight for that team as starter.

3) Wrestler profiles (fresh; produced by build_wrestler_profiles.py)
- mt/wrestlers/<season>/by_id/<wrestler_id>.json
- The script MUST NOT recompute matches from mt/processed_data (too slow).
- Instead, use wrestler profile fields (including match_count and matches list if present).
- Wrestlers with 0 matches must be excluded.

## Normalization / identity rules
### Team ID creation
- Define a deterministic function: team_id = slugify(team_name)
  - lowercase
  - spaces -> underscore
  - remove periods/apostrophes
  - collapse multiple underscores
Examples:
"Virginia Tech" -> "virginia_tech"
"Ohio State" -> "ohio_state"

### Mapping ranking entry team name to team_id
- ranking_<weight>.json entries have `team` as a string (e.g., "Virginia Tech").
- Convert that to team_id via the same slugify.

### Matching wrestler profile to team
- Wrestler profile includes a `team` string (or similar). Convert to team_id with slugify.
- If mismatch occurs between ranking team and profile team:
  - log a warning (include wrestler_id, ranking team, profile team)
  - still allow the wrestler to contribute under the ranking team_id (because starters come from rankings),
    but only if you can load the wrestler profile JSON by id.

## Step-by-step algorithm

### Step 0: Read and validate inputs
- Load teams_list JSON into teams_master[]
- Load starter_overrides (if exists) into a set force_backup_ids
- Read all ranking_<weight>.json files in rankings-dir:
  - weights = ["125","133","141","149","157","165","174","184","197","285"] (or detect from filenames)
  - For each weight file:
    - parse rankings[]
    - apply overrides:
      - if wrestler_id in force_backup_ids => treat as is_starter=false
    - store per weight: list of ranking entries
- Assert wrestler-profiles-dir exists.

### Step 1: Build “starters by team” from rankings files
For each team_id in teams_master:
- For each weight:
  - Filter that weight’s rankings list down to entries whose team_id == this team_id
  - From those, pick the lowest rank entry with is_starter==true
  - If none marked starter (after overrides), pick the lowest rank entry (rank smallest) as starter fallback
  - Result: starters_map[team_id][weight] = wrestler_id (or null if no one ranked at that weight)

Important: This starter list only covers ranked wrestlers. Some teams may have no ranked wrestler at a weight. That is allowed (starter null).

### Step 2: Determine “remaining roster”
Because you want “Remaining Roster” sections too, but your authoritative roster comes from processed team files, and we are NOT scanning those:
- For now, remaining roster should be derived from wrestler profiles directory:
  - Iterate over ALL wrestler profile JSON files (by_id) once.
  - For each profile:
    - if wrestler has 0 matches => skip
    - team_id = slugify(profile.team)
    - append to team_roster_all[team_id] list (store wrestler_id, name, weight, current_rank)
This gives you “everyone with matches” on the team.
Then:
- starters = from Step 1 (by weight)
- remaining = roster_all minus starters (by wrestler_id)

### Step 3: Per-wrestler extraction function (single source of metrics)
Implement a function load_wrestler(profile_json) that returns:
- match_count (int)
- win_count (int)
- pf7, pa7 (floats)
- si_plus, df_plus, apr_plus (floats)
- top10_wins, top10_matches (ints)
- top33_wins, top33_matches (ints)
- bonus_wins (int)  # denominator wins
- pin_wins (int)    # denominator wins
- tech_wins (int)   # denominator wins

How to compute the counts:
- Prefer using existing fields if present in the profile:
  - record vs top10 / vs top25 etc (if stored as "W-L", parse)
  - But you said you do NOT store vs-ranked baked in reliably, so do this instead:
- Use match history array in the profile IF present:
  - each match should include opponent_rank (int or null) and result (W/L) and method (DEC/MD/TF/FALL/etc)
  - For each match:
    - if result == "W": win_count++
    - if opponent_rank != null and opponent_rank <= 10: top10_matches++, and if win: top10_wins++
    - if opponent_rank != null and opponent_rank <= 33: top33_matches++, and if win: top33_wins++
    - if win and method in ["MD","TF","FALL"] (or however you encode): bonus_wins++
    - if win and method indicates pin/fall: pin_wins++
    - if win and method indicates tech fall: tech_wins++
If match history is NOT present or lacks opponent_rank/method:
- Set those counts to null and allow team-level fields to become null where needed (don’t fake it).

### Step 4: Decide which wrestlers contribute to team aggregation
Team aggregation should be for STARTING 10 only (your requirement).
So for each team:
- included_wrestler_ids = all non-null starters across weights (unique)
- For each included wrestler:
  - load profile
  - if match_count == 0 => exclude
- matches_included = sum(match_count)
- wins_included = sum(win_count)

### Step 5: Compute team metrics (match-weighted means + win-based rates)
Let total_matches = sum(w.match_count) across included wrestlers
Let total_wins = sum(w.win_count) across included wrestlers

Compute:
- avg_pf7 = sum(w.pf7 * w.match_count) / total_matches
- avg_pa7 = sum(w.pa7 * w.match_count) / total_matches
- avg_pd7 = avg_pf7 - avg_pa7

Advanced metrics:
- si_plus  = sum(w.si_plus  * w.match_count) / total_matches
- df_plus  = sum(w.df_plus  * w.match_count) / total_matches
- apr_plus = sum(w.apr_plus * w.match_count) / total_matches

Rates (wins denominator):
- bonus_rate = total_bonus_wins / total_wins   (if total_wins==0 => null)
- pin_rate   = total_pin_wins / total_wins     (if total_wins==0 => null)
- tech_rate  = total_tech_wins / total_wins    (if total_wins==0 => null)

Top win %:
- top10_win_pct = total_top10_wins / total_top10_matches (if matches==0 => null)
- top33_win_pct = total_top33_wins / total_top33_matches (if matches==0 => null)

### Step 6: Compute league ranks per metric
Across all teams that have that metric non-null:
- avg_pa7: ascending (lower is better)
- all others: descending (higher is better)
Tie-breakers:
1) metric value
2) counts.matches_included (desc)
3) team_id (asc)
Assign rank starting at 1.

Store ranks in the output alongside values.

### Step 7: Build rosters section in output
For each team:
- roster.starters: list of 10 (or fewer) entries containing:
  - weight, wrestler_id, name, rank, is_starter=true
- roster.remaining: list of other wrestlers with matches on that team:
  - weight, wrestler_id, name, rank, is_starter=false
Sort roster:
- starters sorted by weight asc (125..285)
- remaining sorted by weight asc then by rank asc (nulls last) then name

### Step 8: Write output JSON
Write mt/team_metrics/<season>/team_metrics.json following the locked schema in team_metrics.schema.md:
- schema_version, season, generated_at_utc
- depends_on.wrestler_profiles_dir, and (if available) include the built_at timestamp from the wrestler build step; else null
- league.team_count = len(teams[])
- teams[] entries include metrics + ranks + counts + roster + highlights (highlights may be null placeholders for now)

### Step 9: Debug output (required)
If --debug-team provided:
- print:
  - resolved team_id
  - starter wrestler_ids by weight
  - each included wrestler: match_count, win_count, pf7, pa7, si/df/apr, top10/33 counts, bonus/pin/tech wins
  - final computed team metrics before ranking
  - final ranks after ranking

## Error handling (hard rules)
- Missing wrestler profile JSON for a starter id:
  - log warning and skip that wrestler
- Team ends with total_matches==0:
  - omit the team entirely
- Rankings file missing for a weight:
  - log warning and proceed (that weight contributes no starters)
- starter_overrides missing:
  - treat as no overrides

## Performance constraints
- The script must NOT scan mt/processed_data for matches.
- It may scan mt/wrestlers/<season>/by_id once to build roster_all (remaining roster).
- It may load starter wrestler profiles as needed.

## Future join with Team Rankings (NOT in this script)
- Team rank / dual rank / projected points will come later from a different script and JSON file:
  - mt/team_rankings/<season>/team_rankings.json
- UI should join that by team_id at runtime (don’t inject here).