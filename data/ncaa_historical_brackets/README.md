# NCAA Wrestling Championships 1928–2016 — bracket data (schema 2.0)

**Start here:** `SPEC.md` explains every field and the exact procedure to rebuild any bracket.
`render_bracket.py` is the reference implementation:
`python render_bracket.py data/NCAA1979.json 118` draws a weight; add `--view` for a structured summary.

| folder / file | what it is |
|---|---|
| `SPEC.md` | file layout, codes, bracket models by era, rebuild procedures |
| `data/NCAAyyyy.json` | one self-contained file per tournament year (86 files, 33,412 bouts) |
| `render_bracket.py` | reference program: text drawing or canonical view of any weight |
| `team_scores/` | team-score table per year + `team_scores_all.csv` |
| `AUDIT.md` | every problem found in the source PDFs, year by year, and how it was handled |
| `validation/` | cold-start AI test results; comparison with independent 2013/2014/2016 data |
| `scripts/` | PDF → JSON pipeline (`run_all.sh`) to regenerate everything from the source PDFs |

Bracket models (SPEC.md §3): `bergman` 1928–40 · `bad_points` 1936, 1948 · `summary_only` 1934, 1938, 2015 ·
`wrestleback_finalists` 1941–71 · `wrestleback_semifinalists` 1972–85 · `wrestleback_quarterfinalists` 1986–95 ·
`wrestleback_all` 1996–2016. No tournament 1943–45. 2017 onward not included (the source PDFs are scans or
NCAA-format sheets; 2022–23 PDFs not available).

Each row in `matches` keeps the original 2013–2026 house fields (year, weight, round, bracket, winner_/loser_
seed/name/team, result_type, score) plus ids and from/to links, so existing tools that read the house
format keep working.

Source: wrestlingstats.com bracket sheets. They were compiled by hand; where they contradict themselves the
files keep what is printed and say so in `source_discrepancies`.
