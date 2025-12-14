#!/usr/bin/env bash
set -euo pipefail

# ======================================
# WrestleData full site rebuild pipeline
# ======================================

SEASON=2026
VENV=".venv/bin/python"

echo "======================================"
echo "Rebuilding WrestleData for season $SEASON"
echo "======================================"

# Step 1
$VENV scripts/rankings/build_starter_rankings.py \
  -season $SEASON

# Step 2
$VENV scripts/rankings/build_wrestler_profiles.py \
  -season $SEASON

# Step 3
$VENV scripts/teams/build_team_profiles.py \
  --season $SEASON \
  --teams-list data/team_lists/$SEASON/ncaa_d1_teams.json \
  --rankings-dir mt/rankings_data/$SEASON \
  --starter-overrides mt/rankings_data/$SEASON/starter_overrides.json \
  --out-dir mt/teams

# Step 4
$VENV scripts/team_metrics/build_team_metrics.py \
  --season $SEASON \
  --teams-list data/team_lists/$SEASON/ncaa_d1_teams.json \
  --rankings-dir mt/rankings_data/$SEASON \
  --starter-overrides mt/rankings_data/$SEASON/starter_overrides.json \
  --wrestler-profiles-dir mt/wrestlers/$SEASON/by_id \
  --out-file mt/team_metrics/$SEASON/team_metrics.json

echo "======================================"
echo "Rebuild complete for season $SEASON"
echo "======================================"
