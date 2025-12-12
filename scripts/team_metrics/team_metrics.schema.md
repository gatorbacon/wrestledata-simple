# FILE: mt/team_metrics/<SEASON>/team_metrics.schema.md
# PURPOSE: LOCKED JSON CONTRACT for team metrics + UI display (values + league ranks)

## Overview
This schema defines the output of the team-metrics aggregation step.
It MUST be run AFTER `build_wrestler_profiles.py` because it depends on the wrestler profile JSONs being fresh.

Output path (per season):
- mt/team_metrics/<season>/team_metrics.json

Notes:
- League scope: NCAA D1 only
- No minimum team match threshold
- Exclude wrestlers with 0 matches
- “Ranked Win %” is removed and replaced with:
  - Top10 Win %
  - Top33 Win %
- All metric fields include both:
  - value
  - league rank (within D1 teams in this file)
- Ranking direction:
  - Higher is better for all metrics EXCEPT Avg PA7 (lower is better)
- Tie-breakers (stable rankings):
  1) value (primary, respecting direction)
  2) matches_included (desc)
  3) team_id (asc)

## Top-level JSON shape (team_metrics.json)
{
  "schema_version": "1.0",
  "season": 2026,
  "generated_at_utc": "YYYY-MM-DDTHH:MM:SSZ",
  "depends_on": {
    "wrestler_profiles_dir": "mt/wrestlers/2026/by_id",
    "wrestler_profiles_built_at_utc": "YYYY-MM-DDTHH:MM:SSZ or null"
  },
  "source": {
    "teams_list_file": "data/team_lists/2026/ncaa_d1_teams.json",
    "rankings_dir": "mt/rankings_data/2026",
    "starter_overrides_file": "mt/rankings_data/2026/starter_overrides.json",
    "wrestler_profiles_dir": "mt/wrestlers/2026/by_id"
  },
  "league": {
    "governing_body": "NCAA",
    "division": "D1",
    "team_count": 0
  },
  "metric_definitions": {
    "avg_pf7": "Match-weighted mean of wrestler PF7 across included wrestlers.",
    "avg_pa7": "Match-weighted mean of wrestler PA7 across included wrestlers.",
    "avg_pd7": "avg_pf7 - avg_pa7 (derived).",
    "bonus_rate": "Team bonus_wins / team_wins (wins denom).",
    "pin_rate":   "Team pin_wins / team_wins (wins denom).",
    "tech_rate":  "Team tech_wins / team_wins (wins denom).",
    "top10_win_pct": "Wins vs Top-10 opponents / matches vs Top-10 opponents.",
    "top33_win_pct": "Wins vs Top-33 opponents / matches vs Top-33 opponents.",
    "si_plus":  "Match-weighted mean SI+ across included wrestlers.",
    "df_plus":  "Match-weighted mean DF+ across included wrestlers.",
    "apr_plus": "Match-weighted mean APR+ across included wrestlers."
  },
  "teams": [
    {
      "team_id": "virginia_tech",
      "team_name": "Virginia Tech",
      "conference": "ACC",
      "division": "D1",

      "team_rank": { "value": null, "rank": null, "rank_scope": "league" },

      "metrics": {
        "avg_pf7": { "value": 5.81, "rank": 12, "rank_scope": "league" },
        "avg_pa7": { "value": 2.94, "rank": 18, "rank_scope": "league" },
        "avg_pd7": { "value": 2.87, "rank": 9,  "rank_scope": "league" },
        "bonus_rate": { "value": 0.44, "rank": 7,  "rank_scope": "league" },
        "pin_rate":   { "value": 0.19, "rank": 11, "rank_scope": "league" },
        "tech_rate":  { "value": 0.11, "rank": 23, "rank_scope": "league" },
        "top10_win_pct": { "value": 0.50, "rank": 16, "rank_scope": "league" },
        "top33_win_pct": { "value": 0.61, "rank": 15, "rank_scope": "league" }
      },

      "advanced_metrics": {
        "si_plus":  { "value": 108.2, "rank": 14, "rank_scope": "league" },
        "df_plus":  { "value": 112.6, "rank": 8,  "rank_scope": "league" },
        "apr_plus": { "value": 105.9, "rank": 19, "rank_scope": "league" }
      },

      "counts": {
        "matches_included": 215,
        "wins_included": 131,
        "wrestlers_included": 10,
        "starters_mode": "ranking_files_with_overrides"
      },

      "roster": {
        "starters": [
          {
            "weight": 125,
            "wrestler_id": "34933357132",
            "name": "Eddie Ventresca",
            "rank": 6,
            "is_starter": true
          }
        ],
        "remaining": [
          {
            "weight": 125,
            "wrestler_id": "34999999999",
            "name": "Backup Guy",
            "rank": null,
            "is_starter": false
          }
        ]
      },

      "highlights": {
        "best_team_win": { "opponent_team": null, "opponent_rank": null },
        "best_upset": {
          "wrestler_id": null,
          "wrestler_name": null,
          "result": null,
          "opponent_wrestler_name": null,
          "opponent_rank": null
        },
        "most_dominant_weight": { "weight": null, "reason": null },
        "weakest_weight": { "weight": null, "reason": null }
      }
    }
  ]
}

## Required behavior for missing data
- If a metric cannot be computed:
  - set {"value": null, "rank": null, "rank_scope":"league"}
- If team has 0 included matches:
  - omit the team entirely from `teams[]`

## Separate Team Rankings file (future; join in UI, not injected here)
Path suggestion:
- mt/team_rankings/<season>/team_rankings.json

Schema suggestion:
{
  "schema_version":"1.0",
  "season":2026,
  "generated_at_utc":"...",
  "teams":[
    {
      "team_id":"virginia_tech",
      "team_name":"Virginia Tech",
      "team_rank":6,
      "dual_rank":null,
      "projected_ncaa_points":null,
      "projected_aa_count":null,
      "projected_qualifiers":null
    }
  ]
}