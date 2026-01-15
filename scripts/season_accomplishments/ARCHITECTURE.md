# Season Accomplishments JSON - Architecture

## Purpose
Generate a clean, authoritative summary of what each wrestler accomplished in a given season. This is the foundation for historical seasons and future career linking.

## Build Pipeline Position

This script should run **AFTER**:
1. ✅ Scraping (`wrestle_scraper_raw_mt_locked.py`)
2. ✅ Name alias application (`scripts/apply_name_aliases.py`)
3. ✅ Match processing (`scripts/process_raw_matches_by_season.py`)
4. ✅ Data loading (`scripts/rankings/load_data.py`)

This script should run **BEFORE**:
- Frontend JSON generation (`build_wrestler_profiles.py`, `build_team_profiles.py`, etc.)
- Any scripts that depend on historical season data

## Data Sources

### Primary Source: Processed Team JSON Files (Single Source of Truth)
**Location**: `mt/processed_data/hs_ky_{gender}/{season}/*.json`

**Note**: Processed data contains all necessary information including correct grade fields and parsed match data (winner/loser info).

**Structure**:
```json
{
  "team_name": "Boyle County",
  "season": 2025,
  "roster": [
    {
      "season_wrestler_id": "29939531132",
      "name": "Hayley Cappelli",
      "weight_class": "106",
      "grade": "7th",
      "matches": [
        {
          "date": "11/30/2024",
          "event": "The Tommy Castle Classic",
          "weight": "113",
          "summary": "...",
          "opponent_id": "...",
          "winner_name": "...",
          "loser_name": "...",
          "result": "TF"
        }
      ]
    }
  ]
}
```

### Data Extraction Logic

1. **Identity Fields** (from roster entry):
   - `season_wrestler_id`: Direct from `roster[].season_wrestler_id`
   - `name`: Direct from `roster[].name`
   - `team`: Direct from `team_name`
   - `gender`: From directory path (`hs_ky_boys` → `"boys"`)
   - `season`: Direct from `season` field
   - `grade`: Direct from `roster[].grade` (needs parsing: "7th" → 7, "So." → 10, etc.)

2. **Competition Summary** (from matches):
   - `final_weight`: Weight class of the LAST match by date (parse `matches[].date`, sort, take last `matches[].weight`)
   - `record.wins`: Count matches where `winner_name` == wrestler name AND `winner_team` == team name
   - `record.losses`: Count matches where `loser_name` == wrestler name AND `loser_team` == team name
   - **Filter out**: BYE matches (`result == "BYE"` or summary contains "received a bye")
   - **Filter out**: NoResult matches (`result == "NoResult"`)

3. **Postseason Fields** (future implementation):
   - `regional_qualifier`: Check if any match `event` contains "Regional" or "Region"
   - `regional_place`: Parse from event name or match summary (future)
   - `state_qualifier`: Check if any match `event` contains "State" or "KHSAA"
   - `state_place`: Parse from event name or match summary (future)
   - `state_champion`: Derived as `state_place === 1`

## Output Location

**Path**: `data/season_accomplishments/{gender}/{season}/season_accomplishments.json`

**Structure**:
```json
{
  "season": 2026,
  "gender": "boys",
  "wrestlers": [
    {
      "season_wrestler_id": "29939531132",
      "name": "Hayley Cappelli",
      "team": "Boyle County",
      "gender": "boys",
      "season": 2026,
      "grade": 7,
      "final_weight": 106,
      "record": {
        "wins": 15,
        "losses": 8
      },
      "regional_qualifier": false,
      "regional_place": null,
      "state_qualifier": false,
      "state_place": null,
      "state_champion": false
    }
  ]
}
```

## Filtering Rules

1. **Only include wrestlers with ≥1 match**: Skip wrestlers with empty `matches` array or all matches filtered out (BYE/NoResult)
2. **One record per wrestler per season**: If a wrestler appears on multiple teams (shouldn't happen, but handle gracefully), use the team with most matches
3. **Grade parsing**: Convert string grades to integers based on actual data from 2025 season:
   - "6th" → 6 (12 wrestlers)
   - "7th" → 7 (214 wrestlers)
   - "8th" → 8 (382 wrestlers)
   - "Fr." → 9 (950 wrestlers)
   - "So." → 10 (945 wrestlers)
   - "Jr." → 11 (787 wrestlers)
   - "Sr." → 12 (630 wrestlers)
   - Empty string or null → null (3 wrestlers in 2025, include with null grade)

## Implementation Notes

- Script should be idempotent (safe to re-run)
- Should handle missing/invalid data gracefully
- Should log warnings for data quality issues (e.g., wrestlers with 0 matches but in roster)
- Can be run for any historical season if processed data exists

## Future Enhancements

- Regional/state placement parsing from event names
- Tournament bracket position tracking
- Conference/region identification
- Injury/eligibility flags (if needed)

