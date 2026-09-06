# Team logos

Wordmarks/logos for NCAA D1 wrestling programs, used in MatSavant graphics
(`top3_backtest.js`'s end-of-line badges, and the homepage upcoming-duals
ticker's team crests).

**Filename convention:** `{team_slug}.svg` (or `.png` where no SVG source was
available), where the slug matches the same lowercase/underscore convention
as `teamNameToSlug()` in `frontend/wrestledata-ui/public/app.js` /
`homepage.js` (lowercase, spaces to underscores, punctuation stripped) — e.g.
"Oklahoma State" -> `oklahoma_state.svg`, "Penn State" -> `penn_state.svg`.

**Source:** Wikipedia/Wikimedia Commons, resolved per-team via each
program's athletics-team Wikipedia article. `manifest.json` in this
directory records, per team, the exact source URL and Wikipedia's own
reported license status (`source_url`, `license_note`).

**⚠️ Licensing not yet vetted — 36 of 79 are Wikipedia "fair use" images.**
The full 73-team set added 2026-09 was fetched in bulk deliberately deferring
the licensing check that used to gate additions one at a time (repo owner's
call, to unblock a ticker feature) — see `manifest.json` for the per-team
`license_note`. A "fair use" note means Wikipedia hosts that file only for
its own article under non-free-content policy, NOT freely reusable on a
third-party site — those need a real per-team check (find a
public-domain/CC alternative, or drop back to text-only for that team)
before this set is treated as production-ready. The original 6
(cornell/iowa/michigan/nebraska/oklahoma_state/penn_state) predate this
batch and were vetted individually as before.

**Currently have:** all 79 current D1 programs (see `manifest.json` for the
73 fetched 2026-09; the original 6 — cornell, iowa, michigan, nebraska,
oklahoma_state, penn_state — aren't in that manifest since they predate it).

**Adding a new team:** drop `{slug}.svg` (or `.png`) in this directory, and
add an entry to `manifest.json` recording where it came from and its
license status. Consuming code should treat a missing logo as expected (not
an error) and fall back gracefully.
