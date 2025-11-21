# DynamoDB Schema and Technical Specification - Match Finder Project

---

### Overview
This document defines the data schema and technical specification for the local and eventual AWS-hosted DynamoDB instance used by the Match Finder project. The database stores match, wrestler, and team data across multiple years and supports cross-season career linking for NCAA wrestlers.

---

## Table: `career_wrestler`
- **Purpose**: Persistent identity for a wrestler across all seasons
- **Primary Key**: `career_id` (string)

#### Example Fields:
- `career_id`: `"career_03112"`
- `name_variants`: `[{"S":"Josh Willaert"},{"S":"Joshua Willaert"}]`

---

## Table: `season_wrestler`
- **Purpose**: Snapshot of a wrestler's info for a specific season
- **Primary Key**: `season_wrestler_id` (string)

#### Global Secondary Indexes (GSIs):
- `career_id-index` (HASH: `career_id`)
- `season_team-index` (HASH: `season`, RANGE: `team_id`)

#### Example Fields:
- `season_wrestler_id`: `"2015-ELIZ-Quinn_Ruble"`
- `career_id`: `"career_07627"`
- `team_id`: `"ELIZ"`
- `team_name`: `"Elizabethtown"`
- `status`: `"roster_verified"`
- `season`: `2015`
- `weight_class`: `"165"`
- `class_year`: `"Fr."`
- `name`: `"Quinn Ruble"`

---

## Table: `teams`
- **Purpose**: Master record of teams
- **Primary Key**: `team_id` (string)

#### Example Fields:
- `team_id`: `"Appalacian-State"`
- `name`: `"Appalacian State"`
- `aliases`: `["App State","ASU"]`
- `state`: `"NC"`

---

## Table: `team_seasons`
- **Purpose**: Track team-specific metadata by year
- **Primary Key**: Composite (`team_id`, `season`)

#### Example Fields:
- `team_id`: `"Appalacian-State"`
- `season`: `2025`
- `name`: `"Appalacian State"`
- `abbreviation`: `"APP"`
- `governing_body`: `"NCAA"`
- `division`: `"DI - SoCon, Division I"`

---

## Table: `matches`
- **Purpose**: Record of individual matches between wrestlers
- **Primary Key**: `match_id` (string)

#### Global Secondary Indexes (GSIs):
- `match_wrestler-index` (HASH: `wrestler1_id`)

#### Example Fields:
- `match_id`: `"2014-PSU-Zain_Rethorford-2014-AUGS-Drew_Randall-12/07/2013-MD-12-3"`

- `wrestler1_id`: `"2014-PSU-Zain_Rethorford"`
- `wrestler1_name`: `"Zain Rethorford"`
- `wrestler1_team_id`: `"Penn-State"`
- `wrestler1_team_name`: `"Penn State"`
- `wrestler1_team_abbr`: `"PSU"`

- `wrestler2_id`: `"2014-AUGS-Drew_Randall"`
- `wrestler2_name`: `"Drew Randall"`
- `wrestler2_team_id`: `"Augsburg"`
- `wrestler2_team_name`: `"Augsburg"`
- `wrestler2_team_abbr`: `"AUGS"`

- `winner_id`: `"2014-PSU-Zain_Rethorford"`
- `result`: `"MD-12-3"`
- `event_name`: `"Indiana Little State"`
- `date`: `"12/07/2013"`
- `weight_class`: `"141"`

---

## Table: `career_link`
- **Purpose**: (Optional) Tracking fuzzy match linking history for transparency
- **Primary Key**: `season_wrestler_id` (string)

#### Example Fields:
- `season_wrestler_id`: `"2015-ASHL-Joseph_Brandt"`
- `linked_career_id`: `"career_03166"`
- `match_type`: `"exact"`
- `confidence_score`: `0.92`
- `manual_override`: `false`

---

### Notes for Future Developers
- All data is ingested from raw JSON scraped from Trackwrestling, processed through a local post-processing step, and uploaded to DynamoDB.
- Post-processing resolves fuzzy name matches, team transfers, and weight class tracking across seasons.
- `career_id` is the glue across seasons; all queries for career stats or histories depend on this mapping.
- Local DynamoDB can be run with:
  ```bash
  java -Djava.library.path=./DynamoDBLocal_lib -jar DynamoDBLocal.jar -sharedDb -port 8001
  ```
- The Python client should use:
  ```python
  boto3.resource('dynamodb', endpoint_url='http://localhost:8001')
  ```
