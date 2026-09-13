# Matrix ranking automation — prototype (PAUSED 2026-09-13)

This is exploratory code, not part of the production pipeline. Nothing here
is imported by, or overwrites, any real pipeline script or data. See the
`project_matrix_ranking_automation` memory for full context, decisions, and
the plan for resuming this work — this README is just an orientation to the
files.

## What this is

An attempt at a deterministic, explainable engine to automate (or assist)
TJ's manual weekly "matrix walk-through" — the hours-long process of
resolving head-to-head and common-opponent conflicts to produce the
KentuckyMat ranking order for a weight class. Paused because the resolver
architecture (greedy, one-conflict-pair-at-a-time) hit a real limitation:
some conflicts interact in a cluster and can't be solved independently. See
the memory doc for the decision on how to resume.

## Files

- `ranking_engine.py` — the core reusable engine: conflict scoring
  (`score_order`), gap resolution (`resolve_gap`, `solve_window`), the
  zero-loss floor rule, placement-note ranking (`placement_rank`), and
  window-filtering for performance (`filter_lookup_to_window`).
- `simulate_week.py` — the week-by-week simulation driver. Bootstraps from a
  real archived rankings JSON, then for each subsequent week: pulls
  temporally-truncated data, detects weight-class reclassifications, runs
  the full-board H2H/CO audit-and-resolve loop, and writes an HTML matrix
  (via the real `generate_matrix.py`/`build_relationships.py`) plus a
  `sim_state_{gender}_{season}_{weight}.json` state file for the next week.
- `temporal_load_data.py` — wraps the REAL production `load_data.py` to
  build a temporally-truncated `weight_class_{weight}.json` (matches
  filtered to `date <= cutoff`), reading real `mt/processed_data` files
  read-only and writing only to a scratch dir. This is what keeps
  weight-class assignment in sync with TJ's actual pipeline algorithm
  instead of a separate ad hoc reconstruction.

## Known state as of pause

Weight 165 was reviewed and confirmed correct. Weight 157 surfaced a real
architectural gap: a cluster of mutually-interacting CO conflicts (Parker
Smith/Leland Garcia, James McDaniels/Caden Wren, Grayson Scott/Isac Perez,
sharing bystander Jonathan Troxell) oscillates for ~245 moves and hits the
20-round reconciliation cap without a clean resolution or complete exception
list. Do not treat 157 output produced by this code as trustworthy without
addressing that first — see the memory doc.

Running this requires a `sim_state_*.json` and `temporal_rankings_data/`
scratch dir (not included — regenerate via `simulate_week.py
--bootstrap-from <date> --weight <wt> --after <date>`).
