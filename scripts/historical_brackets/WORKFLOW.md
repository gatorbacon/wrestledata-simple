# Historical bracket transcription workflow

Covers the **whole season pipeline** — season setup, all 14 weight classes,
and all post-processing (season accomplishments, team standings, wrestler
stubs, career profiles) — for turning one year's scanned KHSAA state
bracket PDF into fully-linked site data. Written after 2012 (first pass,
slow) and 2011 (second pass, much faster — this doc is why). Read this
start to finish before starting 2010 or any other season; it's the whole
playbook, not just the per-weight-class part.

## The big lesson

**Never hand-simulate `enter_bracket.py`'s interactive stdin prompts.**
Building a line-by-line "answer file" (one line per prompt) and piping it
in requires correctly predicting how many lines each entrant needs (a
senior gets 4 lines; a non-senior with candidate matches gets 5 — the
extra "link to one of these?" line), and gets every match's winner/method/
score in exact stdin order. Almost every transcription bug this project
hit (reversed winners, off-by-one entrant shifts, corrupted brackets) came
from miscounting these lines, not from misreading the bracket itself.

Instead, use **`enter_bracket.py --batch-json spec.json`**. It builds the
whole instance in one shot from a flat spec — no stdin, no line counting,
no guessing:

```json
{
  "entrants": {
    "ENTRANT_1": {"name": "Mason Franck", "first_name": "Mason", "last_name": "Franck",
                  "team": "Campbell County", "grade": 12, "link": "new"},
    "ENTRANT_2": {"name": "Justin Bevins", "first_name": "Justin", "last_name": "Bevins",
                  "team": "East Ridge", "grade": 11, "link": "new"}
  },
  "results": {
    "C_CHAMP_R1_0": {"winner": "ENTRANT_1", "method": "fall", "score_text": "1:23"}
  }
}
```

- `link`: `"career_XXXXXX"` to link into an existing career, or `"new"`/omitted
  to always mint a new one. Do the candidate research up front (see below) and
  put the decision straight in the spec — batch mode does no interactive
  candidate search.
- `results`: keyed by **slot ID** (from the template, e.g. `C_CHAMP_R1_0`,
  `CONS_M1_3`), not by bout number. Only `winner`/`method`/`score_text` are
  needed — `loser` is derived automatically from the slot's `inputs`.
- Byes are handled automatically (skip them in `results`).
- The dict of `slots[sid]["inputs"]` in the template file tells you exactly
  which two entrants meet in each slot — dump it once per template
  (`python -c "..."` reading `data/bracket_templates/{template_id}.json`) so
  you're not re-deriving crossover wiring by hand every weight class.

## Reading the PDF: render to image, don't trust `pdftotext -layout`

`pdftotext -layout` mangles this bracket format — winner/loser text and
scores get shifted onto adjacent rows because of how the columns overlap
vertically. It's fine for locating which page a weight class is on, but
**do not transcribe match results from it**. Instead:

```bash
pdftoppm -png -r 300 -f <page> -l <page> "data/2012/bracket-pdf/2012 KHSAA State Wrestling Tournament.pdf" out/page
```

Use `-r 300`, not `-r 200` — 2012 was transcribed at 200dpi and needed
several bugs fixed after the fact from misreads; 2011 at 300dpi needed
almost no rework. Then `Read` the PNG directly — the rendered bracket
lines/boxes make the winner/method/score unambiguous. Each weight class is
normally 2 pages: odd page = championship side, even page = consolation
side (the page also prints the "Place Winners" list at the bottom of the
consolation page — this is ground truth, use it to verify your
transcription before saving).

**If a specific region is still ambiguous even at 300dpi** (dense
multi-stage merge areas in the middle of the consolation bracket are the
usual culprit — text from 3-4 stacked bout boxes can visually run
together), don't guess: crop that region and upscale it further before
reading. This caught a real reversed-winner bug in 2011 that would have
otherwise slipped through:
```python
from PIL import Image
im = Image.open("page-06.png")
crop = im.crop((x0, y0, x1, y1))          # pick a generous box around the ambiguous rows
crop = crop.resize((crop.width*2, crop.height*2))
crop.save("crop.png")
```
Then `Read` the crop. Cheaper than re-deriving a wrong answer later.

To find which pages a weight belongs to:
```bash
for p in $(seq 1 N); do
  pdftotext -layout -f $p -l $p FILE.pdf - | sed -n 3p
done
```
(the weight class number is printed as the 3rd line of every page header).

## Bout numbers vs. slot IDs

Bout numbers printed on the sheet (e.g. `Bout: 209`) are globally
sequential across the whole tournament print job and differ per weight
class — don't try to reuse them across weight classes. What's constant
*within one template* is the round structure: for the `ky_state_32e_8p_std_v1`
template, reading top to bottom on the championship page gives you
`C_CHAMP_R1_0..15` (16 bouts) → `C_CHAMP_R2_0..7` (8) → `C_CHAMP_QF_0..3` (4)
→ `C_CHAMP_SF_0..1` (2) → `C_CHAMP_FINAL_0` (1), in the same top-to-bottom
seed order every time. The consolation page maps to `CONS_R1_0..7` →
`CONS_M1_0..7` → `CONS_P1_0..3` → `CONS_M2_0..3` → `CONS_P2_0..1` →
`CONS_M3_0..1` → `CONS_P3_0` (3rd place) / `CONS_5TH` / `CONS_7TH`, in
that same top-to-bottom order on the page. Once you've read the champ page
top-to-bottom and the cons page top-to-bottom, you already have the slot
IDs — no bout-number bookkeeping needed.

## 0. Season setup (do once, before any weight class)

1. **Confirm the bracket structure is unchanged.** Render page 5 (first
   weight class, championship side) and page 6 (consolation side) at
   `-r 300` and eyeball entrant count / consolation style / round
   progression. If it matches `ky_state_32e_8p_std_v1` (32 entrants,
   8 places, single-backside consolation — true for both 2012 and 2011),
   just extend that template's `first_season`/`last_season` range in
   `data/bracket_templates/index.json` rather than making a new template.
   If it's genuinely different, use `template_builder.py` to build a new
   one and register it separately.
2. **Confirm the weight-class list.** Read the 3rd line of each page
   header across the whole PDF (see the loop below) and add a new era row
   to `data/weight_class_eras/hs_ky_boys.json` if the list differs from
   the last confirmed era. 2011 and 2012 use *different* lists (2011 is
   the older `103/112/119/125/130/135/140/145/152/160/171/189/215/285`
   scale; 2012+ uses `106/113/120/.../195/220/285`) — don't assume the
   list carries over from the year you just finished.
3. **Note the `--link-season`.** `enter_bracket.py` defaults to
   `season + 1`. When working backward this means each new season links
   against the season you *just finished this session* — e.g. 2011 linked
   against the 2012 data built earlier in the same project. This is
   exactly right and is why cross-year continuity (same wrestler, same
   career, different year) shows up immediately in the link precheck —
   treat it as a good sign, not a coincidence to double-check.

## Per-weight-class process (repeat 14x per season)

1. Find the 2 pages (see above), render both to PNG at `-r 300`, `Read` both.
2. Transcribe the championship page top-to-bottom into seed order
   (`ENTRANT_1..32`: name, team abbreviation → resolve to full team name,
   grade) and all `C_CHAMP_*` results.
3. Transcribe the consolation page the same way for all `CONS_*` results.
   Cross-check the 8 placements against the "Place Winners" list printed
   on the page — if anything doesn't match, trust the placement list and
   re-read the specific match in question before moving on.
4. Run the career-link precheck **once for all 32 entrants** (batched, not
   one at a time) against the next scraped season's index:
   ```python
   idx = build_link_index('boys', 2013)  # or whatever the next scraped season is
   for first, last, team, grade in entrants:
       if grade == 12:
           continue  # seniors can't appear in a later season, skip
       print(first, last, find_link_candidates(first, last, team, idx))
   ```
   Review each candidate list for a plausible team+name match (watch for
   spelling variants like Zack/Zach, Matt/Matthew, Meilke/Mielke — these
   are still real links) and decide link vs. new career for every non-senior
   before writing the spec.
5. Write the batch JSON spec directly from what you read in steps 2-4 (no
   intermediate "answer file" — go straight from bracket image to spec).
6. Run `enter_bracket.py --season S --weight W --gender boys --batch-json spec.json`.
7. Confirm the printed placements match the page's "Place Winners" list
   exactly before moving to the next weight class.
8. **Run the read-only orphan check for this one weight class before moving
   on** — not just once at the end of the season. This is the cheap
   insurance against the "duplicate-entrant" failure mode described below:
   if the session ends right after this weight class for any reason
   (context limit, you stop for the day), the last thing that happened was
   a clean verification, not an unverified batch call.
   ```python
   import json
   d = json.load(open('data/bracket_instances/hs_ky_boys/{season}/{weight}.json'))
   valid_hw = set(e['historical_wrestler_id'] for e in d['entrants'].values() if e != 'BYE' and e)
   ledger = json.load(open('data/historical_wrestlers/hs_ky_boys/ledger.json'))
   orphaned = [hw for hw, v in ledger.items()
               if v.get('season') == {season} and v.get('weight_class') == {weight} and hw not in valid_hw]
   print(len(orphaned), 'orphaned —', 'clean' if not orphaned else 'NEEDS CLEANUP (see below)')
   ```
   If it reports orphans (only happens after a batch run that errored and
   was retried), run the full cleanup in "Duplicate-entrant / stale-link
   bugs" below immediately, scoped to just that weight's orphaned HW ids,
   before starting the next weight class.

## Known team-abbreviation drift

KHSAA/TrackWrestling abbreviations aren't stable across years — seen so
far: `MCCR`→`MCCE`, `JOHN`→`JOCE`, `HOLO`→`LHC`, `NUBL`→`NBUL`,
`UHA`→`UNHE`, `ERID`→`EARI` (East Ridge). If a raw abbreviation doesn't
resolve, search `data/team_lists/hs_ky_boys/teams.json` by substring on
the plausible full name rather than assuming the abbreviation is wrong.

**`HOLO` = Holy Cross (Louisville), not Holmes** — both are plausible
substring guesses from the letters alone; only the career-link precheck
(an exact name match landing on a *specific* 2012 team) confirmed it. If
an abbreviation has more than one plausible full-name match, don't just
pick one — resolve it the same way: put a placeholder team name in the
batch spec's entrant, run the precheck, and let an exact-name-match
candidate confirm or correct the guess before finalizing the spec.

## Verifying a transcription beyond the placement list

The "Place Winners" list only proves the *final 8* are right — it can't
catch a reversed winner in an early round if that wrestler didn't end up
placing. Two extra checks that caught real bugs in 2011:
- If two entrants' names are visually similar or numerically adjacent
  (`ENTRANT_16` vs `ENTRANT_18`), double check every slot that references
  either one after typing the spec — this exact mix-up happened once and
  `enter_bracket.py` only caught it because the wrong winner didn't match
  either of that slot's two valid inputs. A mix-up between two entrants
  who *do* both feed into the same later slot won't be caught by that
  validation at all.
- If a person's name matches an *existing* career exactly, but that
  career already has a link for a season very close to the one you're
  entering, stop and check whether they're really the same person (see
  "Duplicate-entrant / stale-link bugs" below) — don't assume the linker
  got it right just because the tool didn't complain.

## Post-processing pipeline (run once, after all 14 weight classes)

Same order as the plan's original design, all already built and reused
as-is between 2012 and 2011 — no code changes needed per season, only
new data:

```bash
# 1. Derive placements/records from the bracket instances (no hand-typing)
.venv/bin/python scripts/historical_brackets/build_season_accomplishments.py --season 2011 --gender boys

# 2. Team standings — transcribe the official score table (pages 2-N of the
#    PDF, right after the cover page) into a {team: score} JSON by hand,
#    the same way as the per-weight "Place Winners" list. Do NOT try to
#    reverse-engineer the historical point formula (see below) — just copy
#    the printed score. Then:
.venv/bin/python scripts/historical_brackets/compute_team_standings.py --season 2011 --gender boys \
  --official-json /path/to/2011_boys_official_scores.json --save
# Sanity check before trusting the merge: grep the printed table for "?"
# rows (official score missing = a team-name mismatch between your JSON
# and what's in the bracket instances) and re-run with `python -c` checking
# for rows where official_score is None in the saved file.

# 3. Wrestler stub profiles (needs a STATE_TOURNAMENT_DATE entry — add the
#    new season's last tournament day to the dict at the top of the script
#    before running, e.g. {2011: "2011-02-19"})
.venv/bin/python scripts/historical_brackets/build_wrestler_stubs.py --season 2011 --gender boys

# 4. Rebuild ALL career profiles (not season-scoped — this walks every
#    career file, so it picks up every season ever entered)
.venv/bin/python scripts/rankings/build_career_profiles.py --gender boys

# 5. Regenerate the sitemap (career/team URLs changed)
python scripts/generate_sitemap.py

# 6. Regenerate the search index — EASY TO FORGET, and newly-added
#    historical wrestlers will not be searchable on the site until this
#    runs. Always pass the site's actual current defaultSeason (check
#    frontend/hs-ky-ui/public/hs_config.js's `defaultSeason`, e.g. 2026),
#    NOT the historical season you just transcribed — historical
#    wrestlers show up in the "historical" bucket regardless of which
#    season is passed, but passing the wrong (old) season here corrupts
#    the "active" bucket for every currently-competing wrestler.
.venv/bin/python scripts/generate_search_index.py -league hs -gender both -season 2026
```

**Why we stopped trying to reverse-engineer the old team-scoring formula**:
the printed placement points, advancement points, and bonus values almost
certainly differed by era (confirmed inconsistent even within a single
clean single-scorer example — see 2012 session). Rather than guess and
risk silently wrong numbers, `team_standings/*.json` stores **both** an
`official_score` (transcribed from the document, authoritative, what the
site should display) and a `modern_score` (computed with the current-era
formula, for cross-year comparison only, unchanged code).

## Duplicate-entrant / stale-link bugs — always run this check

Two distinct bug patterns hit the career-linking data this project, both
caused by the **same root issue**: `enter_bracket.py --batch-json` creates
every entrant (minting HW ids, linking or creating careers) *before* it
processes match results. If the run errors out partway through results
(a bad `ENTRANT_N` reference, JSON typo, etc.), all 32 entrants for that
weight class have *already* been created. Fixing the spec and re-running
creates a **second** full set of entrants — the first set becomes
orphaned, and any of them that were supposed to `link` into an existing
career leaves that career pointing at the orphaned (now-wrong) HW id
instead of the corrected one, because the collision-safety check in
`link_into_existing_career` silently refuses to overwrite.

Symptom when re-running after a fix: a wall of
`[WARN] career_XXXXXX already has a {season} season (...) — not overwriting`.

**Fix, every time this happens** (ran twice this project — 195 lb in 2012,
189 lb in 2011 — same script both times):
```python
import json, glob, os

season = 2011  # <- set this
d = json.load(open(f'data/bracket_instances/hs_ky_boys/{season}/WEIGHT.json'))  # <- set WEIGHT
valid_hw = set(e['historical_wrestler_id'] for e in d['entrants'].values() if e != 'BYE' and e)

ledger = json.load(open('data/historical_wrestlers/hs_ky_boys/ledger.json'))
orphaned = [hw for hw, v in ledger.items() if v.get('season') == season and hw not in valid_hw]

fixed, deleted = 0, 0
for hw in orphaned:
    cid = ledger[hw]['career_id']
    path = f'data/careers/career_{cid.split("_")[1]}.json'
    c = json.load(open(path))
    if len(c['seasons']) == 1 and str(season) in c['seasons']:
        os.remove(path); deleted += 1                 # pure ghost career -> delete
    elif c['seasons'].get(str(season)) == hw:
        del c['seasons'][str(season)]; json.dump(c, open(path, 'w'), indent=2)
        open(path, 'a').write('\n'); fixed += 1        # stale pointer on a real career -> clear it
    del ledger[hw]

json.dump(ledger, open('data/historical_wrestlers/hs_ky_boys/ledger.json', 'w'), indent=2)
open('data/historical_wrestlers/hs_ky_boys/ledger.json', 'a').write('\n')
print(f'fixed {fixed}, deleted {deleted}, removed {len(orphaned)} ledger entries')
```
Then for every career that was `fixed` (not `deleted`), re-add the correct
`{season: hw}` pointer using the CURRENT (valid) entrant's HW id — pull it
from `career_to_current_hw` the same way `run_bracket_batch` does.

**Run the read-only detection half of this** (just the `valid_hw`/`orphaned`
computation, no writes) **after finishing every season**, not just when a
run visibly errors — it's cheap, and it's the only way to be sure a
successful-looking run didn't leave stragglers:
```python
import json, glob
valid_hw = set()
for f in glob.glob('data/bracket_instances/hs_ky_boys/2011/*.json'):
    for e in json.load(open(f))['entrants'].values():
        if e != 'BYE' and e:
            valid_hw.add(e['historical_wrestler_id'])
ledger = json.load(open('data/historical_wrestlers/hs_ky_boys/ledger.json'))
orphaned = [hw for hw, v in ledger.items() if v.get('season') == 2011 and hw not in valid_hw]
print(len(orphaned), 'orphaned —', 'clean' if not orphaned else 'NEEDS CLEANUP')
```
