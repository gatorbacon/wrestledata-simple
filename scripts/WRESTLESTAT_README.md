# WrestleStat Ingestion Pipeline

Supplemental dual results ingestion system that fills missing matches from WrestleStat with maximum accuracy, human pacing, and permanent ID mappings.

## Overview

This pipeline supplements the primary TrackWrestling data source by:
- Scraping recent dual results from WrestleStat
- Resolving team and wrestler IDs with permanent mappings
- Checking for existing data to avoid duplicates
- Normalizing match data to MatSavant format
- **Never** modifying existing TrackWrestling ingestion logic

## Safety Rules

⚠️ **CRITICAL**: This pipeline follows strict safety rules:

- **NO automatic page clicking** - Every page navigation requires user confirmation
- **NO continuous scraping** - Human pacing controls the workflow
- **Permanent mappings** - Once confirmed, team/wrestler mappings are stored forever
- **TrackWrestling is primary** - WrestleStat only fills gaps
- **No silent overwrites** - All decisions are explicit and auditable

## Files Structure

```
data/
├── mappings/
│   ├── wrestlestat_teams.json      # Permanent team ID mappings
│   └── wrestlestat_wrestlers.json   # Permanent wrestler ID mappings
├── raw/
│   └── wrestlestat_duals/            # Raw scraped dual data
│       └── {dual_id}.json
└── processed/
    └── wrestlestat/                  # Normalized match data
        └── {dual_id}.json

scripts/
├── wrestlestat_ingest.py             # Main ingestion script
└── wrestlestat_ui.py                 # CLI helpers for resolution
```

## Usage

### Basic Workflow

1. **Run the ingestion script**:
   ```bash
   python scripts/wrestlestat_ingest.py
   ```

2. **Follow the prompts**:
   - Press ENTER to fetch the Recent Duals index page
   - Review the list of duals found
   - Press ENTER to begin processing

3. **For each dual**:
   - System checks if already ingested (skips if found)
   - Resolves WrestleStat teams → MatSavant teams
   - Prompts for confirmation before opening dual page
   - Extracts match data
   - Resolves wrestlers (with fuzzy matching)
   - Normalizes and saves data

### Team Resolution

When a WrestleStat team is encountered for the first time:

1. **Exact match**: System finds MatSavant team with same name → auto-confirms
2. **Fuzzy match**: System shows similar teams (≥70% similarity) → user selects
3. **Manual search**: User enters search term → system filters candidates

Mapping is stored permanently in `wrestlestat_teams.json`:

```json
{
  "wrestlestat_team_id": 61,
  "wrestlestat_name": "Pennsylvania",
  "matsavant_team_id": "penn_state",
  "confirmed_at": "2025-12-24T10:30:00"
}
```

### Wrestler Resolution

Three-tier matching system:

**Tier A - Exact Name Match**:
- Normalized names match exactly
- Ranking weight matches or ±1
- Auto-confirms if weight matches

**Tier B - Fuzzy Match**:
- Similarity ≥ 90%
- Ranking weight matches or ±1
- Shows recommendations, requires user confirmation

**Tier C - Manual Search**:
- User enters search term
- System filters MatSavant wrestlers
- User selects from filtered list
- Weight mismatch warnings shown

Mapping is stored permanently in `wrestlestat_wrestlers.json`:

```json
{
  "wrestlestat_wrestler_id": 98765,
  "wrestlestat_name": "Charles Smith-Jones",
  "matsavant_wrestler_id": "34952199812",
  "team_id": "illinois",
  "ranking_weight": 141,
  "match_type": "exact",
  "override": false,
  "confirmed_at": "2025-12-24T10:30:00"
}
```

## Data Format

### Raw Dual Data (`data/raw/wrestlestat_duals/{dual_id}.json`)

```json
{
  "wrestlestat_url": "https://www.wrestlestat.com/d1/event/dual/12345",
  "date": "12/21/2025",
  "scraped_at": "2025-12-24T10:30:00",
  "matches": [
    {
      "weight": 141,
      "wrestler_a_id": 12345,
      "wrestler_a_name": "John Doe",
      "wrestler_b_id": 67890,
      "wrestler_b_name": "Jane Smith",
      "winner_id": 12345,
      "win_type": "DEC",
      "score": "5-3",
      "result_text": "John Doe over Jane Smith (Dec 5-3)"
    }
  ]
}
```

### Processed Match Data (`data/processed/wrestlestat/{dual_id}.json`)

```json
{
  "dual_id": "12345",
  "wrestlestat_url": "https://www.wrestlestat.com/d1/event/dual/12345",
  "team_a": "illinois",
  "team_b": "iowa",
  "matches": [
    {
      "date": "12/21/2025",
      "event": "Dual Meet",
      "weight": "141",
      "summary": "34952199812 over 34952200123 (Dec 5-3)",
      "opponent_id": "34952200123",
      "source": "wrestlestat",
      "wrestlestat_url": "https://www.wrestlestat.com/d1/event/dual/12345"
    }
  ],
  "processed_at": "2025-12-24T10:30:00"
}
```

## Duplicate Detection

The pipeline checks for existing data in two ways:

1. **WrestleStat supplemental data**: Checks if raw dual file exists
2. **TrackWrestling data**: Looks for ≥5 matches between teams in last 7 days

If either condition is true, the dual is skipped.

## Merge Strategy

WrestleStat matches are **NOT** merged immediately. They remain separate until a later merge script runs:

- **TrackWrestling wins** on conflict
- **WrestleStat fills gaps** only
- Merge happens in separate process (not part of this pipeline)

## Configuration

Edit constants in `wrestlestat_ingest.py`:

```python
MIN_MATCH_THRESHOLD = 5  # Minimum matches to consider dual already ingested
SEASON = 2026            # Current season
```

## Troubleshooting

### "No duals found"
- Check WrestleStat website structure hasn't changed
- Verify network connection
- Check if WrestleStat requires authentication

### "Team resolution failed"
- Check `data/team_lists/{season}/ncaa_d1_teams.json` exists
- Verify team name normalization
- Use manual search option

### "Wrestler resolution failed"
- Verify team data file exists in `mt/data/{season}/`
- Check wrestler name spelling variations
- Use manual search with partial name

### HTML parsing errors
- WrestleStat page structure may have changed
- Check `scrape_dual_page()` function
- May need to update BeautifulSoup selectors

## Future Enhancements

- [ ] Batch processing mode (process multiple duals without prompts)
- [ ] Web UI for mapping management
- [ ] Automatic merge script
- [ ] Conflict resolution UI
- [ ] Statistics dashboard

## Notes

- All mappings are **append-only** - never overwritten
- All decisions are **auditable** - timestamps on every mapping
- Human pacing ensures **no rate limiting** issues
- Permanent mappings ensure **consistency** across runs

