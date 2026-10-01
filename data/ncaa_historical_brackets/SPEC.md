# NCAA Wrestling Championship bracket files — schema 2.0

One JSON file per tournament year (`NCAAyyyy.json`). Each file holds everything needed to redraw
every weight class of that year bout by bout. No other file is needed. `render_bracket.py`
(shipped next to this document) is a reference implementation; where this text and that program
disagree, the program shows what was meant.

The bracket format changed several times between 1928 and today. **Always start with
`model.bracket_model`** — it tells you which rebuild procedure (section 5) applies.

---

## 1. Top-level layout

```
{
  "schema":      {"name": "ncaa-wrestling-bracket", "version": "2.0", "spec": "SPEC.md"},
  "tournament":  {...},        // year, host, dates, team champion, outstanding wrestler, source
  "model":       {...},        // which bracket format this year used  (section 3)
  "codes":       {...},        // meaning of every code used in THIS file (rounds, results, slot kinds)
  "team_scores": {...},        // top-ten team table as printed
  "weights":     [...],        // one object per weight class (section 2.1)
  "matches":     [...]         // every bout of every weight, one row each (section 2.2)
}
```

`codes` is generated from the file's own content: it lists only codes that actually occur in it.

### 1.1 tournament
| field | meaning |
|---|---|
| year, edition, event, host | as printed |
| dates | `[first_day, last_day]`, ISO dates |
| team_champion, team_champion_label | label is printed text such as "Team Champion" or "Unofficial Co-Team Champion" |
| outstanding_wrestler, gorriaran_award | "Name - Team" strings as printed (missing if not awarded) |
| source.url / compiled_by | where the data comes from (wrestlingstats.com bracket sheets) |
| source.incomplete_consolations | true when the source itself says its consolation results are incomplete |

### 1.2 team_scores
`scores`: `[{rank, tied, team, points, champions}]` — the "Top Ten Team Scores" table as printed
(more than ten rows when teams tie; `champions` = individual champions from that team).
`official`: true, false (labelled unofficial), or null when there is no table. Empty `scores` = no
table in the source (1928 had no team scoring; 1933 names unofficial co-champions only).
`scope` describes the table; `notes` lists any disagreement with the brackets.

### 1.3 model
`bracket_model` (section 3) plus: `championship` (`single_elimination` / `bad_point_rounds` /
`not_available`), `consolation` (`bergman_list` / `drawn_bracket` / `none` / `not_available`),
`model_years`, `placements_awarded` (highest place awarded), `bout_order_known` (always false),
`description` (plain-language summary).

---

## 2. Weights and matches

### 2.1 weights[]
| field | meaning |
|---|---|
| weight | 115, 118 … or `"UNL"` (unlimited / heavyweight in early years) |
| draw_lines | number of lines in the championship draw (16 or 32); null when there is no bracket |
| entrants | `[{id, line, seed, name, team, entered_via}]` — every wrestler at this weight |
| consolation_sheet | the drawn consolation bracket (section 2.3); null when the model has none |
| placements | `[{place, wrestler_id, name, team, match_id, as, method}]` |
| bad_points_final | bad_points model only: total bad points per wrestler |
| notes | observations (e.g. a wrestler who was eligible to wrestle back but did not) |
| source_discrepancies | problems in the source sheet and how they were resolved |

`entrants[].id` is unique within the weight (e.g. `"118-07"`). **Always identify wrestlers by id** —
two different wrestlers can share a name at the same weight (1976, 158: two "Brad Smith"s).

`entrants[].line` = draw line (1 = top). Lines with no entrant are byes. `entered_via`:
`draw` (was placed on a line), `pigtail` (won a pigtail bout to take his line — he also has a
line), `pigtail_only` (lost a pigtail; never on a line), `consolation_only` (the sheet leaves him
out of the championship draw, but he wrestles in the consolations — see source_discrepancies),
`bad_point_rounds`, `summary` (known only from the summary page — no bouts).
`entrant_count` = number of entrants listed.

`placements[].method`: `bout` (decided by `match_id`; `as` = `winner` or `loser` of that bout),
`automatic` (awarded with no bout — Bergman era), `listed`/`bout_not_recorded`/`summary_only`
(the source names the place winner but has no bout for it), `tie` (several wrestlers share the
same `place`, e.g. 1936 158: two wrestlers tied for 4th). Placements always use `wrestler_id`,
even when the summary page spells the name differently (the difference is in `source_discrepancies`).

`bad_points_final` maps wrestler_id → total bad points.

### 2.2 matches[] — one row per bout that was actually wrestled
| field | meaning |
|---|---|
| year, weight | |
| match_id | unique within the file, e.g. `118-C_R1-03`. Treat it as an opaque key — do not split it (round codes such as `R6-7` contain hyphens); use the `round` and `weight` fields. |
| round | round code (section 4, and `codes.rounds`) |
| bracket | `champ`, `consol`, or `badpoints` |
| winner_id / loser_id | entrant ids |
| winner_name/team/seed, loser_name/team/seed | as printed on the bracket sheet |
| result_type | `Dec`, `TF` (technical fall), `Fall`, `TA` (time advantage), `MFF`, `Default`, `Forfeit`, `DQ`, `Unknown` (no result printed). Suffix `-OT` = overtime of any kind (OT, sudden victory SV, tiebreaker TB, criteria Cr). The sheets do not distinguish major decisions from decisions. |
| score | `Dec`/`TF`: points (`"7-5"`, `"4-4, 2-1"` = regulation then overtime); `Fall`/`TA`: time (`"5:32"`); null if not printed. `result_raw` has everything as printed. |
| result_raw | the result exactly as printed on the sheet |
| winner_from / loser_from | where each wrestler came from — see below |
| winner_to / loser_to | match_id of the next bout that wrestler wrestled, or null |
| seq | a valid replay order within the weight (true bout order is not known) |
| participants | only on a bout whose winner is unknown (winner/loser null): `[{id,name,team,from}]` |

`from` values: `line:N` — came from draw line N (including advancing on byes, which are **not**
rows); `W:<match_id>` — won that bout; `L:<match_id>` — lost that bout; `entry` — first bout for
this wrestler (pigtail or bad-point round).

Byes are never rows. A bout whose winner the sheet does not show has `winner_id`/`loser_id` null
and `participants` instead (its slot on the consolation sheet has kind `unrecorded`). The next bout
then has that unknown wrestler as one side: e.g. `loser_id: null`, `loser_from: "W:<unknown bout>"`
— someone (one of the two participants) lost it, but the sheet does not say who.

**Replaying:** process rows in `seq` order. Every `from` points at a line or at an earlier row, and
every `to` points at a later row that contains the same wrestler.

### 2.3 consolation_sheet (drawn-consolation models only)
The consolation bracket exactly as drawn on the sheet, as a tree of slots:
```
{"columns": 6,
 "slots": [{"slot": "S2.1", "column": 2, "kind": "bout", "wrestler_id": "118-05", "name": "...",
            "match_id": "118-C_R1-01", "top": "S1.1", "bottom": "S1.2", "feeds": "S3.1",
            "printed": "Hoffman 3-0"}, ...]}
```
* `slot` = `S<column>.<row>`; column 1 is the left edge (it holds only entries and byes); row counts
  top to bottom within the column. "Slot order" always means numeric: column, then row (S1.2 < S1.10).
  The sheet's columns are NOT round codes: column 1 holds only entries; the first column of results
  (column 2) is round `C_R1`, and so on, with the last two result columns `C_QF` and `C_SF`. For any
  bout slot, take the round from its `match_id` row (on a short sheet — e.g. three result columns —
  the columns are simply C_R1, C_QF, C_SF). `C_PIG` bouts are not on the sheet (their winners
  appear as entries).
* `top` / `bottom` = the two slots that feed this one (only on result slots); `feeds` = the slot
  this one feeds (null for the right-most slots, whose winners go to the 3rd-place bout).
* `kind` (also in `codes.slot_kinds`):
  `entry` a wrestler enters here · `bye` sheet prints "Bye" · `empty` blank line ·
  `bout` a consolation bout (`wrestler_id` = winner, `match_id` = the row) ·
  `advance` one feeder empty/bye, the other moves on with no bout · `empty_result` both feeders empty ·
  `unrecorded` a bout happened, winner not shown · `unidentified` printed name could not be matched.
* Entries appear in any column: first-round losers enter in column 1, later losers enter further right.

---

## 3. model

| bracket_model | years | championship | consolation |
|---|---|---|---|
| `bergman` | 1928–1940 (not 1934/1936/1938) | single elimination | Bergman wrestle-backs, no drawn sheet |
| `bad_points` | 1936, 1948 | rounds of pairings, no bracket | none |
| `summary_only` | 1934, 1938, 2015 | not available | not available |
| `wrestleback_finalists` | 1941–1971 | single elimination | drawn sheet; losers to the 2 finalists |
| `wrestleback_semifinalists` | 1972–1985 | single elimination | drawn sheet; losers to the 4 semifinalists |
| `wrestleback_quarterfinalists` | 1986–1995 | single elimination | drawn sheet; losers to the 8 quarterfinalists |
| `wrestleback_all` | 1996– | single elimination | drawn sheet; every championship loser |

No tournament was held 1943–1945. `model.placements_awarded` = number of places (3, 4, 6 or 8).

---

## 4. Round codes
Championship: `PIG` (pigtail/play-in), `R32`, `R16` (named by the number of lines in play),
`QF`, `SF`, `Final`.
Bergman: `WB2_R16`, `WB2_QF`, `WB2_SF` (wrestle-backs for 2nd), `2nd`; `WB3_*`, `3rd`.
Drawn consolation: `C_PIG`, `C_R1`, `C_R2` …, `C_QF`, `C_SF` (columns of the sheet, left to right;
the last two are always C_QF, C_SF), then place bouts `3rd`, `5th`, `7th` (winner takes that place,
loser the next).
Bad points: `R1`, `R2` … (`R6-7` = rounds 6 and 7 combined).

---

## 5. Rebuilding a bracket

### 5.1 Championship bracket (every model except bad_points / summary_only)
1. Make column 0 with `draw_lines` cells. Put each entrant with a `line` in cell `line-1`. Empty cells
   are byes. Round codes follow the column, not who is in it: in a 32-line draw columns 1–5 are
   R32, R16, QF, SF, Final; in a 16-line draw R16, QF, SF, Final — even when a whole column is byes
   (e.g. 1928, where every R16 pairing is a bye and there are no R16 rows).
2. Build column k+1 from column k by taking cells two at a time (1–2, 3–4, …):
   * both occupied → find the `bracket: champ` row whose winner_id/loser_id are these two; its winner
     fills the cell (the row's `round` is the column's round code, e.g. R32);
   * one occupied → that wrestler advances (bye, no row);
   * none → empty.
3. Repeat until one cell is left: the champion. The last pairing is the `Final`. (Every pairing of two
   wrestlers has exactly one row in these files; if one were ever missing, leave that cell null.)
4. Pigtails: a `PIG` row is a play-in; its winner is the entrant holding the line
   (`entered_via: pigtail`), its loser (`pigtail_only`) never appears on a line.

### 5.2 Bergman wrestle-backs (bracket_model `bergman`)
There is no consolation drawing. The consolation rows (`bracket: consol`) are, in `seq` order:
`WB2_*` bouts among wrestlers who lost to the champion (earliest loser first), the `2nd` bout
(wrestle-back survivor vs finals loser; winner = 2nd), then `WB3_*` / `3rd` for third.
Follow `winner_from`/`loser_from` to see who met whom. Places with `method: automatic` had no bout.

### 5.3 Drawn consolation bracket (all `wrestleback_*` models)
1. Take `consolation_sheet.slots`. Roots are slots with `feeds: null` (right-most column).
2. Order: for each root (in slot-id order), walk the tree **top feeder first, then the slot, then the
   bottom feeder** — this gives every column's slots from top to bottom.
3. Draw each slot in its `column`. Leaves (entry/bye/empty — slots with no `top`/`bottom`) take
   rows 0, 2, 4 … in walk order, counted across the whole sheet; a result slot sits midway between
   its `top` and `bottom` feeders (half-rows are fine — any layout that keeps this vertical order is
   correct). The walk order and the slot numbering agree in every file.
4. The label of a slot: entry/bout/advance → the wrestler (`wrestler_id`), plus the bout result from
   the row `match_id` for bouts; bye → "Bye"; empty/empty_result → blank; unrecorded → "(not
   recorded)"; unidentified → its `printed` text.
5. `C_PIG` rows are consolation play-ins; the winner appears on the sheet as an `entry`.
6. Place bouts are rows with round `3rd`, `5th`, `7th` (winner takes that place, loser the next); the
   `Final` loser is 2nd. **The rows are authoritative.** Usual pattern: `3rd` = the two root winners,
   `5th` = the losers of the two `C_SF` bouts, `7th` = the losers of the two `C_QF` bouts. When a
   consolation half is empty the semifinal loser goes straight to the 3rd-place bout (`from` = `L:…-SF-…`).

### 5.4 Bad points (bracket_model `bad_points`)
No bracket. Group rows by `round`, keeping each label as printed (a weight can have `R6`, or a
combined `R6-7`; order rounds by their first number, then the shorter label first). Wrestlers who
sat out a round (odd numbers) are simply absent from that round's rows. Each row is a bout; `winner_bad_points` /
`loser_bad_points` are the bad points charged in that bout (as printed) and `*_total` the running
total. Placements (1–4, ties possible) come from `placements`.

### 5.5 Summary only
No bouts. Report `placements` and `team_scores`.

---

## 6. Known limitations
* True bout order is not known before the modern era; `seq` is a valid logical order only.
* Byes and blank consolation lines are not match rows (they are implicit in `line`s and explicit
  in `consolation_sheet`).
* The source sheets were compiled by hand. Where they are internally inconsistent the file keeps
  what is printed and says so in `source_discrepancies` (e.g. summary page vs bracket).
* Bouts that were wrestled but not printed on the sheet are not in the file.
* A wrestler's name may be spelled differently in other sources; teams are as printed.

## 7. Minimal checks a rebuild should pass
* Every `winner_from`/`loser_from` resolves (line holder, or winner/loser of an earlier row; a null
  side resolves to the unknown winner of the row it names).
* No championship bout in these files has an unknown winner (only a few consolation bouts do).
* The championship rebuild (5.1) ends with the 1st-place wrestler in `placements`.
* Every consolation `bout` slot's `wrestler_id` equals the winner of its `match_id` row.
