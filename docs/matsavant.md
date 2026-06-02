# MatSavant — Comprehensive Reference

MatSavant (matsavant.com) is a **100% static analytics platform** for NCAA Division I men's wrestling. Every number shown on the site is pre-computed by local Python scripts and written to JSON files that the frontend fetches directly. There is no backend API, no database queries at runtime, and no server-side rendering.

---

## Repository Location

MatSavant lives on the **`main`** branch. All frontend files are in:

```
frontend/wrestledata-ui/public/
```

All data pipeline scripts are in `scripts/` (non-hs_ky), `xtp/`, and `scripts/mat_value/`.

---

## Architecture Overview

```
TrackWrestling (scrape)
        ↓
  scripts/ncaa/parse_ncaa_results.py          ← tournament bracket + results
  scripts/scraping/scrape_ncaa_tournament.py  ← live tournament data
        ↓
  mt/rankings_data/{season}/                  ← intermediate: rankings, match data
  mt/data/{season}/                           ← intermediate: processed match data
        ↓
  scripts/mat_value/compute_all_mat_values.py ← TPAR + per-match impact
  scripts/bonus/compute_all_top33_bonus.py    ← bonus EV for xTP
  xtp/engine/engine.py                        ← expected team points
  scripts/ncaa/generate_replay.py             ← tournament replay JSON
        ↓
  frontend/wrestledata-ui/public/data/        ← static JSON served to site
```

Everything the frontend reads lives under `frontend/wrestledata-ui/public/data/`.

---

## Pages

| Page | File | Description |
|---|---|---|
| Homepage | `index.html` | Weight selector, TPAR leaders, xTP team rankings, stat leaders (pins/techs/majors/wins), Hodge watch |
| Wrestler Profile | `wrestler.html` | Per-wrestler TPAR, skill indices, match impact timeline, full match history |
| NCAA Live Tracker | `ncaa_live.html` | Tournament bracket replay — team leaderboard, projection history chart, big moments feed, by-weight cards, Lazarus Award |
| Seed Analysis | `ncaa_report.html` | Historical seeding vs. performance report |
| Scoring Trends | `ncaa_scoring_trends.html` | Bonus and scoring pattern analysis across rounds/years |
| Team Leaderboard | `ncaa_team_leaderboard.html` | xTP-ranked team table |
| Team Analysis | `ncaa_team_report.html` | Per-team deep-dive with dual meet stats |
| Conference Analysis | `ncaa_conf_analysis.html` | Conference-level aggregated stats |
| TPAR Leaderboard | `leaderboards/mat_value.html` | Full TPAR rankings by weight |

### Core JS Files

| File | Purpose |
|---|---|
| `app.js` | Wrestler profile rendering — TPAR display, skill chart, match impact SVG, match history table |
| `header.js` | Site nav, Fuse.js search integration |
| `tooltips.js` | Metric definitions (displayed on hover) |

---

## Data Directory Structure

```
frontend/wrestledata-ui/public/data/
├── {year}/
│   └── simulation_replay.json        ← full NCAA tournament replay (2014–2026)
├── wrestlers/
│   └── {year}/
│       ├── by_id/{wrestler_id}.json  ← individual wrestler profiles
│       └── index_wrestlers.json      ← search index
├── mat_value/
│   └── {year}/
│       ├── mat_value_{year}.json     ← TPAR leaderboard
│       └── match_mv_impact_{year}.json ← per-match TPAR impacts
├── xtp/
│   └── teams/
│       ├── teams.json                ← xTP team leaderboard
│       └── {team_slug}.json          ← per-team xTP detail
├── rankings/
│   └── {year}/
│       └── {date}/                   ← weekly ranked wrestler lists
└── bonus/
    └── {year}/                       ← Top-33 bonus EV per wrestler
```

---

## Stat Calculations

### 1. TPAR — Team Points Above Replacement

**What it is:** The primary individual performance metric. Displayed as "TPAR" everywhere in the UI. The underlying computation is called **Mat Value (MV)** in the scripts.

TPAR measures how much better (or worse) a wrestler performs compared to what a replacement-level D1 starter would produce against the same opponent. It is calculated per match and then averaged across the season.

**Script:** `scripts/mat_value/compute_mat_value.py`

#### Step 1 — Encode match result as a signed value

Every match result maps to a team point value and then gets a sign based on win/loss:

| Result | Team Pts | Win | Loss |
|---|---|---|---|
| Decision (DEC) | 3 | +3 | −3 |
| Major Decision (MD) | 4 | +4 | −4 |
| Technical Fall (TF) | 5 | +5 | −5 |
| Fall / Pin / INJ / DQ | 6 | +6 | −6 |

TB (tiebreaker) and SV (sudden victory) are treated as decisions.

#### Step 2 — Build the opponent's baseline expectation

The system estimates how much value the opponent *typically* produces, using a shrinkage model that pulls toward a tier average.

Rank tiers and their anchor points:

```
Tier anchors: ranks 1, 10, 30, 50, 100, 150, 200
```

For an opponent at rank `r`, the tier baseline `μ(r)` is computed by linear interpolation between the two nearest anchor means.

**Shrinkage formula (k = 20):**

```
opp_shrunk = (n × opp_raw_avg + 20 × μ(r)) / (n + 20)
```

where `n` = number of matches the opponent has wrestled, and `opp_raw_avg` = the opponent's observed mean signed value across all their matches.

This shrinkage pulls low-n opponents toward their tier average, preventing a wrestler from getting a huge TPAR boost just for beating a highly-ranked opponent who has only wrestled once.

#### Step 3 — Compute per-match TPAR impact

```
expected_signed = −opp_shrunk
tpar_match = result_signed − expected_signed
```

The negative sign on `opp_shrunk` is because the opponent's observed average is measured from *their* perspective, so it gets flipped to represent what *our* wrestler should expect.

**Example:** Wrestler beats a #10-ranked opponent by MD (+4). That opponent has a shrunk average of +0.8 (usually wins by a small margin). Expected = −(+0.8) = −0.8. TPAR impact = 4 − (−0.8) = **+4.8** (well above expectation).

#### Step 4 — Season TPAR

```
TPAR = mean(all tpar_match values across the season)
```

Forfeits and medical forfeits are excluded from all calculations.

**Output:** `mat_value/{year}/mat_value_{year}.json` — leaderboard of all wrestlers sorted by TPAR. Per-match impacts stored in `match_mv_impact_{year}.json`.

---

### 2. SI+, DF+, PE+, DI+ — Skill Indices

These metrics measure *how* a wrestler scores and defends, adjusted for opponent quality. They are standardized to a mean of 100 / std of 10 so a score of 110 means one standard deviation above average.

**Spec doc:** `docs/aps_apg_di_v2_spec.md`

**Index names:**
- **SI+** — Scoring Index (how well you score relative to who you're facing)
- **DF+** — Defense Index (how well you prevent scoring relative to who you're facing)
- **PE+** — Pin/Escape Index (bonus point propensity, called APR+ in some older UI labels)
- **DI+** — Dominance Index (weighted composite)

#### Constants

```python
PF7_CAP = 25       # Points-for per 7 min cap
PA7_CAP = 25       # Points-against per 7 min cap
PD7_CAP = 20       # Point differential per 7 min cap
SHRINK_K = 8       # Opponent shrinkage constant
MIN_MATCHES_FOR_RAW = 3
DI_WEIGHT_SI = 0.40
DI_WEIGHT_DF = 0.45
DI_WEIGHT_PE = 0.15
```

#### Step 1 — Per-match raw scoring rates (non-fall matches only)

```
PF7_raw = points_for  × 420 / seconds_wrestled
PA7_raw = points_against × 420 / seconds_wrestled

PF7 = min(PF7_raw, 25)
PA7 = min(PA7_raw, 25)
PD7 = clamp(PF7 − PA7, −20, 20)
```

The caps prevent a quick 15-0 tech fall against a weak opponent from inflating a wrestler's stats.

#### Step 2 — Assign opponent rank quintile

Divide all ranked wrestlers at the weight class into five quintiles:

```
p = (rank − 1) / (total_ranked − 1)

Q1: p ≤ 0.20  (top 20%)
Q2: p ≤ 0.40
Q3: p ≤ 0.60
Q4: p ≤ 0.80
Q5: remainder
```

#### Step 3 — Shrink opponent's PF7/PA7

```
If opponent has < 3 matches:
    PF7_adj = quintile baseline mean
    PA7_adj = quintile baseline mean

Otherwise:
    PF7_adj = (n/(n+8)) × PF7_raw + (8/(n+8)) × PF7_baseline_Q
    PA7_adj = (n/(n+8)) × PA7_raw + (8/(n+8)) × PA7_baseline_Q
```

#### Step 4 — Per-match contributions

```
APS7_contrib = PF7_match − PA7_adj(opponent)
APG7_contrib = PF7_adj(opponent) − PA7_match
APR_contrib  = PA7_adj(opponent)   ← pin/escape rate signal
```

#### Step 5 — Opponent weighting

Matches are weighted by the opponent's quintile rank. Opponents with fewer than 3 matches get a near-zero weight (0.05):

```
Q1 weight: 1.00    Q2 weight: 0.75    Q3 weight: 0.50
Q4 weight: 0.30    Q5 weight: 0.15    n<3:  weight: 0.05
```

Intermediate quintiles use linear interpolation.

#### Step 6 — Wrestler-level adjusted stats

```
APS7 = Σ(APS7_contrib × weight) / Σ(weights)
APG7 = Σ(APG7_contrib × weight) / Σ(weights)
APR  = Σ(APR_contrib  × weight) / Σ(weights)
APD7 = APS7 + APG7
```

#### Step 7 — Standardized indices

League means and standard deviations are computed across all ranked wrestlers at each weight class for the season.

```
SI+ = 100 + 10 × ((APS7 − APS7_mean) / APS7_std)
DF+ = 100 + 10 × ((APG7 − APG7_mean) / APG7_std)
PE+ = 100 + 10 × ((APR  − APR_mean)  / APR_std)
```

#### Step 8 — Dominance Index

```
DI+ = 0.40 × SI+ + 0.45 × DF+ + 0.15 × PE+
```

Defense is weighted slightly more than scoring (0.45 vs 0.40) because defensive consistency is a stronger predictor of performance at high levels.

---

### 3. Top-33 Bonus EV

This metric estimates how many bonus points (MD=1, TF=1.5, Fall=2) a wrestler expects to score *against top-33 opponents*. It feeds directly into the xTP engine.

**Script:** `scripts/bonus/compute_top33_bonus.py`

#### Bonus severity scale

```python
DEC:  0.0    MD: 1.0    TF: 1.5    FALL/INJ/DQ: 2.0
```

#### Peer tiers for shrinkage baseline

```
P1: ranks  1–8     P2: ranks  9–16
P3: ranks 17–33    P4: ranks 34+ (or unranked)
```

#### Calculation

For each wrestler, collect all wins vs. top-33 opponents and compute:

```
raw_ev = Σ(bonus_severity for each top-33 win) / n_wins
```

Then shrink toward the peer tier baseline (k = 8):

```
If n_wins == 0:
    shrunk_ev = peer_tier_baseline

Otherwise:
    shrunk_ev = (n_wins × raw_ev + 8 × peer_tier_baseline) / (n_wins + 8)

shrunk_ev = clamp(shrunk_ev, 0.0, 2.0)
```

The shrunk value is what the xTP engine uses as `bonus_ev_shrunk`.

---

### 4. xTP — Expected Team Points

xTP projects how many NCAA tournament team points a wrestler (and by extension their team) will likely score, before and during the tournament.

**Engine:** `xtp/engine/` (bracket_schema, probability, scoring, engine)

#### Win probability model

For any potential matchup between wrestlers i and j:

```
z = 1.0 × log(rank_j / rank_i) + 0.25 × (TPAR_i − TPAR_j)
P(i wins) = sigmoid(z) = 1 / (1 + e^−z)
```

Unranked wrestlers are assigned rank 200. Constants `α = 1.0` (rank influence) and `β = 0.25` (TPAR influence) are tunable.

#### Advancement points

```
Championship bracket  (R32, R16, QF, SF wins): +1.0 per win
Consolation bracket   (PIG, R1, R2, R3, R4, QF, SF wins): +0.5 per win
Placement matches     (3rd, 5th, 7th): +0.0 (only placement points)
Finals:               +0.0 (only placement points)
```

#### Placement points

```
1st: 16    2nd: 12    3rd: 10    4th: 9
5th: 7     6th: 6     7th: 4     8th: 3
```

#### Expected bonus points per slot

```
opponent_multiplier:
    Ranks  1– 8: 0.50x    Ranks  9–16: 0.75x
    Ranks 17–24: 1.00x    Ranks 25+:   1.15x

expected_bonus = P(win) × min(bonus_ev_shrunk × opponent_mult, 2.0)
```

Bonus is capped at 2.0 points (pin/forfeit max).

#### xTP per wrestler

```
xTP = Σ over all possible bracket outcomes:
    P(advance to slot) × (advancement_pts + expected_bonus + placement_pts)
```

#### xTP per team

```
xTP_team = Σ(xTP_wrestler) for all team members entered in tournament
```

The engine runs both pre-tournament (full bracket simulation) and live (locking in completed match results and re-computing from current bracket state).

---

## NCAA Tournament Tracker

**Page:** `ncaa_live.html`
**Data:** `data/{year}/simulation_replay.json`

### simulation_replay.json structure

```json
{
  "year": 2026,
  "last_updated": "2026-04-12T22:00:43",
  "matches_completed": 640,
  "matches_total": 640,
  "current_projection": { "Penn State": 181.5, ... },
  "pre_tourney_predictions": { "Penn State": 175.0, ... },
  "team_penalties": { "Team Name": -5.0 },
  "wrestlers": {
    "125": {
      "1": {
        "name": "...", "team": "...",
        "actual": 21.0,
        "projected_total": 21.0,
        "initial_projected": 19.44,
        "aa_prob": 1.0,
        "alive": false,
        "seed": 1
      }
    }
  },
  "history": [
    {
      "match_n": 1,
      "round": "PIG",
      "match": {
        "weight": 125, "winner_seed": 1, "loser_seed": 33,
        "winner_name": "...", "loser_name": "...",
        "winner_team": "...", "loser_team": "...",
        "result_type": "MD", "score": "9-2",
        "winner_school_update": 2.5,
        "loser_school_update": -0.5,
        "upsets": false, "bonuses": true
      },
      "projections": { "Team Name": 125.3, ... },
      "moments": [ { "type": "bonus|upset|rank_change", "team": "...", "message": "..." } ]
    }
  ],
  "sorted_matches": [ ... ],
  "moments": [ ... ]
}
```

### Round processing order

```
PIG → R32 → C_PIG → C_R1 → R16 → C_R2 → C_R3 → QF →
C_R4 → C_QF → SF → C_SF → Final → 3rd → 5th → 7th
```

### Bonus points used for tracker display

```python
{ "Dec": 0.0, "MD": 1.0, "TF": 1.5, "Fall": 2.0, "Forfeit": 2.0, "DQ": 2.0, "Inj.": 2.0 }
```

### Live Tracker features

| Tab | Content |
|---|---|
| Team Leaderboard | Rank, team, pre-tourney projection, current projection, Δ, actual points. Expandable per wrestler. |
| Projection History | Plotly.js line chart — top 10 teams, x=match number (0–640), y=projected points. Session markers. |
| Big Moments | Feed: upsets, bonus wins, leaderboard rank changes, USC penalties |
| Wrestler Movers | Top gainers / top losers in projection delta |
| By Weight | Collapsible cards per weight — seed, wrestler, projection, AA% |
| Lazarus Award | Tracks highest-seeded R32 loser who placed 3rd through consolation bracket |

### Generating the replay

```bash
python scripts/ncaa/generate_replay.py --season 2026
```

The replay is also used to build the seed analysis report (`generate_report.py`) and the scoring trends page.

---

## Key Scripts (NCAA / MatSavant Pipeline)

| Script | Purpose |
|---|---|
| `scripts/scraping/scrape_ncaa_tournament.py` | Live scrape of NCAA tournament brackets from TrackWrestling |
| `scripts/ncaa/parse_ncaa_results.py` | Parse TrackWrestling tournament HTML → matches JSON |
| `scripts/ncaa/generate_replay.py` | Build `simulation_replay.json` round-by-round |
| `scripts/ncaa/simulate_tournament.py` | Pre-tournament projection simulation |
| `scripts/ncaa/generate_report.py` | Build seed analysis report data |
| `scripts/ncaa/live_monitor.py` | Watch for new match results and trigger replay rebuild |
| `scripts/ncaa/build_ncaa_seed_model.py` | Historical seed performance model |
| `scripts/mat_value/compute_mat_value.py` | TPAR for a single wrestler (CLI) |
| `scripts/mat_value/compute_all_mat_values.py` | Batch TPAR for all wrestlers, builds leaderboards |
| `scripts/bonus/compute_top33_bonus.py` | Top-33 bonus EV for a single wrestler |
| `scripts/bonus/compute_all_top33_bonus.py` | Batch bonus EV, writes to wrestler profiles |
| `xtp/engine/engine.py` | Main xTP engine (pre-tournament + live) |
| `scripts/xtp/run_team_xtp.py` | Run team xTP projections |
| `scripts/xtp/run_weight_xtp.py` | Run weight-class-level xTP projections |
| `scripts/xtp/run_regional_xtp.py` | Regional xTP projections |
| `scripts/generate_search_index.py` | Builds `search_index.js` (Fuse.js data, ~6MB) — run: `-league ncaa -season 2026` |
| `scripts/build_simple_leaderboards.py` | Builds stat leaderboard JSON (wins, pins, techs, majors) |
| `scripts/wrestlestat_ingest.py` | Supplemental ingestion from WrestleStat (fills gaps in TrackWrestling data) |
| `scripts/ncaa/lazarus_award.py` | Identifies and tracks Lazarus Award candidates |

---

## Metric Summary Table

| Metric | What it measures | Scale | Location in UI |
|---|---|---|---|
| **TPAR** | Per-match value vs opponent expectation; season average | ±0 to ±5 typically | Wrestler profile hero, leaderboard, team page |
| **SI+** | Adjusted scoring rate vs opponent quality | 100 = avg; 110 = 1 SD above | Wrestler profile skill section |
| **DF+** | Adjusted defensive rate vs opponent quality | 100 = avg; 110 = 1 SD above | Wrestler profile skill section |
| **PE+** | Bonus point propensity vs opponent quality | 100 = avg; 110 = 1 SD above | Wrestler profile skill section |
| **DI+** | Composite dominance: 40% SI+ / 45% DF+ / 15% PE+ | 100 = avg | Wrestler profile skill section |
| **Bonus EV** | Expected bonus pts per win vs top-33 opponents | 0.0–2.0 | Internal; feeds xTP |
| **xTP** | Expected NCAA tournament team points | 0–50+ per wrestler | Team leaderboard, homepage |
| **AA Prob** | Probability of placing top 8 at NCAAs | 0%–100% | Live tracker per-wrestler |

---

## Known Gotchas

1. **TPAR display name vs script name**: The UI everywhere calls this "TPAR." The scripts and JSON field names call it `mv` or `mat_value`. They are the same thing.

2. **PE+ vs APR+**: Older UI labels and code comments may say `APR+`. The canonical spec (`docs/aps_apg_di_v2_spec.md`) defines this as `PE+`. The meaning is the same: pin/escape rate index.

3. **Forfeits excluded**: All forfeit and medical forfeit matches are stripped before any calculation (TPAR, SI+, xTP, etc.). They do count toward official win/loss records.

4. **Skill indices are non-fall only**: SI+, DF+, PE+ are computed only on non-fall matches (decisions, MDs, TFs). Falls end early and skew per-minute rates.

5. **simulation_replay.json covers all years**: The same file structure is used for historical replays (2014–2025) and the live current year (2026). The `history` array is the full match-by-match log; the `current_projection` and `wrestlers` objects reflect the final state.

6. **WrestleStat is supplemental only**: `wrestlestat_ingest.py` adds matches that TrackWrestling missed, but TrackWrestling is always the authoritative source on conflicts.

7. **Team penalties**: Some teams receive USC (unsportsmanlike conduct) point deductions. These are tracked in `team_penalties` in the replay JSON and shown in the Big Moments feed.

8. **xTP engine constants are tunable**: `WIN_PROB_ALPHA`, `WIN_PROB_BETA`, bonus multipliers, and `BONUS_CAP` are all defined at the top of their respective scripts and can be adjusted between seasons.

---

## Technology Stack

| Layer | Technology |
|---|---|
| Frontend | Vanilla HTML/CSS/JavaScript (no framework) |
| Interactive charts | Plotly.js (tournament projection history) |
| Static charts | Custom SVG (TPAR match impact timeline) |
| Search | Fuse.js (fuzzy matching on pre-built index) |
| Data format | Static JSON, served from `/data/` |
| Data pipeline | Python 3, local — no cloud dependencies at build time |
| Hosting | Netlify (static site) |

---

## What Is Legacy / Inactive (MatSavant Side)

- `docs/db_schema.md` — DynamoDB schema from the old backend era; fully replaced by static JSON
- `README.md` in project root — references old DynamoDB + Vite dev setup; stale
- `scripts/link_and_upload_season*.py` (multiple variants) — legacy upload scripts for DynamoDB; not used
- `scripts/clear_dynamodb_tables.py`, `scripts/upload_teams_to_dynamodb.py` — legacy
- `wrestlerank-json/` — standalone ranking experiment; not integrated
