# Cold-start test: can an AI that has never seen this project rebuild the brackets?

Method: a fresh AI instance was given **only SPEC.md and a few JSON files** (no scripts, no other
documentation, no access to anything else) and asked to write its own program to rebuild every
weight: championship bracket column by column, consolation sheet (or Bergman wrestle-backs, or
bad-point rounds), pigtails, place bouts and placements. Its output was compared, weight by
weight, with the reference program `render_bracket.py`.

| | files given | weights | identical to reference |
|---|---|---|---|
| Test 1 | 1928, 1936, 1938, 1942, 1979, 1990, 2011 (every model) | 60 | 60 / 60 |
| Test 2 (updated spec) | 1933, 1948, 1955, 1976, 1983, 2005, 2009, 2015 | 76 | 76 / 76 |
| Both test programs run on **all 86 years** (final data) | 1928–2016 | 819 | 819 / 819 each |

Each test also produced written feedback. It found real problems, all fixed before the final run:
* data: tech falls typed "Unknown"; "MT" (match termination) and "MED FFT" not recognised; overtime
  (TB/SV/criteria) not marked; two same-surname wrestlers swapped (1979 158 Olivers); sheet errors
  where a "Bye" was printed in place of the real entrant (2009 174 Raymond Jordan) or a wrestler was
  left out of the draw entirely (2009 133 James Kennedy - now added as consolation-only); a summary-page
  spelling ("Walter Jacob") not linked to the bout wrestler ("Walter Jacobs").
* spec: consolation columns vs round codes, slot ordering, layout rule, label for unknown slots,
  unknown-winner bouts, optional fields, bad-point round order — all clarified in SPEC.md.
