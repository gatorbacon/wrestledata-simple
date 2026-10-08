# MatSavant — Search (SEO) Build Plan

Written 2026-10-07. Status: **Steps 1–5 done (2026-10-07, local, not pushed); Step 6 (preview, then one production deploy) next — needs TJ's OK to push.** Goal: get MatSavant wrestler and team pages found on Google (and citable by ChatGPT/Perplexity) before the 2026-27 season starts (~Nov 1). One production deploy for the whole project (deploys are ~83% of Netlify credit use — see "Why one deploy").

TJ's decisions (2026-10-07):
- Wrestler title: `Levi Haines Wrestling Record & Stats | Penn State 174 | MatSavant`
- Name-based URLs: `/wrestler/levi-haines`, `/team/penn-state` (no team in wrestler URLs — transfers)
- ChatGPT/Perplexity answer bots allowed, but only from their published IP addresses and only to pages, not data; training bots stay blocked
- Per-IP rate limit on data files
- Netlify cost checked: fine (below)

---

## Why (the numbers this plan is based on)

**Search Console, 2026-10-07** (property data since 2026-09-09):
- 4.1K pages indexed, 36.5K not: 35,803 "Discovered – currently not indexed" (Google found the URLs and didn't bother fetching them), 658 "Duplicate without user-selected canonical" (all wrestler pages: another season's ID of the same wrestler), 43 "Soft 404" (team links with no data, e.g. `team=ok_state`, and a few wrestler pages that looked blank to Google), 16 crawled-not-indexed.
- 82 clicks / 1.96K impressions, average position 11.1. 49 of the 82 clicks were the homepage (brand searches). Name searches already find us at positions 6–9 ("eren sement", "faraz hakim", "evan gleason") with 0 clicks — the result reads "Wrestler Profile" with no description.

**Site, 2026-10-07:**
- Every wrestler page's title is the static `Wrestler Profile`, every team page `Team Profile`; nothing sets `document.title`. No page has a meta description, canonical or `og:` tags.
- `sitemap.xml` lists 40,429 wrestler URLs: 38,093 season profiles (one per season ID) for 14,819 careers + 24 season profiles that belong to no career, **plus 2,336 stray stale copies** named like `10430251132 (1).json` (see Step 1 notes). All lastmods are 2026-09-14.
- The page content (name, record) only exists after JavaScript runs. ChatGPT/Perplexity fetchers don't run JavaScript, so today they'd see an empty page even if allowed.
- `robots.txt` and `block-bots.ts` block OAI-SearchBot, ChatGPT-User and PerplexityBot along with the training bots.

**Keyword research** (Google autocomplete, 2026-10-07): the highest-value searches are `[wrestler name] record` / `college record` / `career record` / `wrestling` (and `[name] wrestlestat`), and `[team] wrestling roster / lineup / schedule / results [2026-27]`. Details in the 2026-10-07 session; head terms worth targeting with static pages: "ncaa wrestling rankings by weight", "ncaa wrestling rankings 2026-27", "ncaa wrestling predictions [weight]", "college wrestling results this weekend", "ncaa wrestling brackets [year]", "ncaa wrestling champions by year".

**Netlify cost** (TJ's usage screen, 2026-09-27 → 10-07, Personal plan, 1,000 credits/month): 254.4 credits = production deploys 210 (14 × 15), bandwidth 26.6, web requests 17.8 (88,877 requests). Web requests (edge functions included, per Netlify docs) are 2 credits per 10,000, so the new edge function is negligible. Deploys dominate → **one production deploy**, built on the free `matsavant-dev` preview first.

---

## Step 1 — URL slugs (data, no site change yet) — DONE 2026-10-07

New script `scripts/seo/build_url_slugs.py`. Source of truth: `data/url_slugs/ncaa_men.json` (committed; **append-only — a slug, once assigned, never changes or gets reused**).

**Wrestler slug rules:**
- From the career's `canonical_name` (`data/careers/ncaa_men/`); for the 24 season profiles with no career, the profile's `name` (keyed by season `wrestler_id`).
- Lowercase, accents stripped (`Piña` → `pina`), apostrophes dropped (`O'Connor` → `oconnor`; the data also uses `` ` `` and `?` as apostrophes: `O`Dell`, `D?Ambrosio`), anything else non-alphanumeric → `-`, collapse/trim hyphens. Nicknames in parentheses stay in (`chandler-chance-marstellar`; ~20 names).
- Name already taken → add the school of the wrestler's first season, by its **current** program name (`TEAM_SLUG_RENAMES` in the script: `army` → `army-west-point`, `north_carolina_state` → `nc-state`, etc.; e.g. `tyler-johnson-nc-state`); still taken → `-2`, `-3`. 14,314 of 14,819 career names are unique today; 471 names cover the other 976 careers (Tyler Johnson ×5, Jake Smith ×4). Whoever has the bare slug keeps it forever; only newcomers get suffixes.
- Reserved words that can't be slugs: none needed now (paths are under `/wrestler/`), but reject empty slugs.
- **Career merges** (`merge_careers`-style): the kept career keeps its slug; the merged career's slug becomes an **alias** (`"aliases": {"old-slug": "kept-slug"}`) that 301s. An unlinked season profile later linked into a career: its slug becomes an alias of the career's.

**Team slugs:** `team_slug` with `_` → `-` (`penn_state` → `penn-state`). No lookup needed. Old team slugs Google remembers (no longer anywhere in the data) alias to today's: `ok_state` → `oklahoma_state`, `north_carolina_state` → `nc_state`, `franklin__marshall` → `franklin_marshall`, `utah_valley_university` → `utah_valley`, `north_dakota_state_university` → `north_dakota_state`, `southern_illinois_edwardsville` → `siu_edwardsville`. `grand_canyon` has no team file → real 404. Pull the full 43-URL soft-404 list from Search Console during the build and check each one.

**Published lookup files** (written by the same script into `frontend/wrestledata-ui/public/seo/` — deliberately NOT under `/data/`, so the edge function's own lookups don't count against the Step 5 rate limit on `/data/*`; small, so the edge function never parses a big file):
- `wrestlers/{slug}.json` — `{name, slug, latest_season, latest_id, seasons: {"2026": "349…", …}, team, team_slug, weight, rank, career_record: "W-L", season_record}` (alias files: `{slug, alias_of}`). `career_record` = sum of `season_summary[].record`. Everything the title/description needs, so the edge function makes **one** small fetch for the head tags.
- `by_id/{Number(wrestler_id) % 97}.json` — `{wrestler_id: [slug, season, is_latest]}` (97 shards of 360–433 ids) for redirecting old `wrestler.html?id=` links. Not the last digits: TrackWrestling ids end in fixed suffixes (`…132`, `…009`).
- `teams.json` — `{team_id: {name, season}}` for the 79 team pages that actually have data (team file whose id matches a team in the latest `team_metrics`, ignoring punctuation). The edge function 404s every other `/team/<x>` (e.g. `abbreviations`, `ncaa_testings_school`, the stale duplicates `pennsylvania`, `mercyherst`, `presbyterian_college`, and `cleveland_state`/`lindenwood`/`queens`, which have no 2026 stats).
- Old team ids → current: `TEAM_SLUG_ALIASES` in `seo_text.js` (used by the pages and the edge function).

**Also add `url_slug`** to each wrestler profile JSON and `opponent_url_slug` to each `match_list` entry (post-step in the same script, after profiles are built) so pages can build clean links without a lookup. Expect a one-time diff on every profile; after that only new/changed ones.

Pipeline: add "Build URL Slugs" to `scripts/pipeline.py` for NCAA right after wrestler profiles and career seasons (`build_career_seasons.py`), before the search index. Add "MatSavant sitemap" (`generate_matsavant_sitemap.py`) at the end of the NCAA run — today it isn't in the pipeline at all.

**Result (2026-10-07):** `scripts/seo/build_url_slugs.py` written and run. 14,843 slugs (14,819 careers + 24 unlinked season profiles), 1,003 with a school/number suffix, 0 aliases yet; published 14,843 slug files + 97 id shards (5.4 MB); `url_slug` / `opponent_url_slug` added to all 38,093 profiles (only those fields change; re-run = 0 changes). Merge / relink / new-career-from-unlinked behaviour checked by simulation on a copy of the career files. Pipeline step "Build URL Slugs" added to `scripts/pipeline.py` (NCAA, after the Career Seasons Map). Found while doing it:
- **2,336 stale duplicate profiles** `data/wrestlers/2020/by_id/<id> (1).json` (+2,199 `by_team/… (1).json`), committed 2026-09-10 in `8ee6c9a209`, all older copies (generated 2026-09-05) of real files (2026-10-03). They are live and in the sitemap; Google lists one as a duplicate. The slug script ignores them. Deleting them is TJ's call (TODO).
- **139 same-name, same-school pairs** got a `-2` slug. Some are different people (two Michael Murphys at Virginia years apart), some look like one wrestler split over two career files. List: `mt/audits/url_slugs/same_name_same_school.csv`. If two careers are merged later, the extra slug becomes a redirect automatically.

## Step 2 — New page addresses — DONE 2026-10-07

`_redirects` (MatSavant):
```
/wrestler/*   /wrestler.html   200
/team/*       /team.html       200
```
(Verify on the preview that the edge function on `/wrestler/*` sees the original path before this rewrite; if not, have the edge function fetch `/wrestler.html` itself.)

Client fallback, so pages work even when the edge function is bypassed:
- `wrestler.html` inline script: if `location.pathname` starts with `/wrestler/`, fetch `/seo/wrestlers/{slug}.json` → `latest_id` (or `seasons[?season]`) → `loadWrestlerProfile(id)`. If the edge function already injected the data (`<script id="wrestler-slug-data">`), use that and skip the fetches. Keep `?id=` working as today.
- `team.html`: `/team/penn-state` → `penn_state` → `loadTeam()`.
- A specific season: `/wrestler/levi-haines?season=2024` (and `&view=season`, which `team.js` uses today). The **canonical is always the bare `/wrestler/levi-haines`**.
- `app.js` sets `document.title` and the meta description too (same template as Step 3), as a backup.

## Step 3 — Edge functions: titles, descriptions, text, redirects — DONE 2026-10-07 (local)

New `frontend/wrestledata-ui/public/netlify/edge-functions/wrestler-page.ts` (and `team-page.ts`, or one file with both). Must live under the base dir (2026-09-27 build gotcha). Reuse the design in `docs/kentuckymat_edge_function_plan.md` §2.3–2.4 (markers not DOM parsing, `onError: "bypass"`, strip `content-length`/`etag`/`last-modified`, HTML-escape everything, CDN cache headers, 50 ms CPU budget).

**`/wrestler.html?id=X`** → look up `by_id/{last2}.json` → **301** to `/wrestler/{slug}` (add `?season=YYYY` when X isn't the latest season; keep `view=`). Unknown id → **404** status with the page's "Not found" + `noindex`.

**`/wrestler/{slug}`** → fetch `/seo/wrestlers/{slug}.json`. `alias_of` → 301. Missing → 404 + `noindex`. Otherwise inject:
- `<title>{Name} Wrestling Record & Stats | {Team} {weight} | MatSavant</title>` (team/weight = latest season; name through the same display rule the page uses)
- `<meta name="description">`: `{Name} college wrestling record and stats: {career W-L} career, {season label} {season W-L} at {weight} for {Team}. Every match result, rankings and head-to-head on MatSavant.` Add NCAA placements only if the data has them reliably (check what's available during the build; don't guess).
- `<link rel="canonical" href="https://www.matsavant.com/wrestler/{slug}">` — production host even on the preview.
- `og:title`, `og:description`, `og:url`, `og:type=profile`, `og:image` (a site image for now; per-wrestler share images later), `twitter:card=summary`.
- Header pre-fill: name, team · weight, career record in the existing header elements (match what the JS renders → no flicker).
- Optionally inline the latest season profile JSON (`<script id="wrestler-data" type="application/json">`) if size allows (§2.3 size guard).

**`/team.html?team=x`** → 301 to `/team/{x with -}`; old slugs → 301 to the current team; no data → 404 + `noindex`.
**`/team/{slug}`** → title `{Team} Wrestling {2025-26}: Roster, Lineup, Results & Rankings | MatSavant` (season label from the team data, not hardcoded — it flips when 2027 data lands), description, canonical, og tags, team name pre-filled.

Caching: `Netlify-CDN-Cache-Control: public, s-maxage=604800`; `Cache-Control: public, max-age=0, must-revalidate`; `Netlify-Vary: query=season|view` for wrestler, none for team. Cached responses are dropped on each deploy.

**Built (2026-10-07):**
- `frontend/wrestledata-ui/public/seo_text.js` — the one copy of the title/description/address rules (`MatSavantSEO`), loaded by `wrestler.html`/`team.html` and imported by the edge function. Plain script, no import/export, so it works both ways.
- `wrestler.html` / `app.js`: `/wrestler/<slug>[?season=YYYY]` → `loadWrestlerFromSlug()` (uses the edge function's inline `#wrestler-slug-data` if present, else fetches `/seo/wrestlers/<slug>.json`; season hint so it doesn't 404 through newer seasons' folders); `setWrestlerHead()` sets title/description/canonical (latest-season summary, whichever season is on screen); unknown → "Not Found" + noindex. Old `?id=` links still work.
- `team.html` / `team.js`: `/team/<slug>`; old ids `location.replace` to the current team; title/description/canonical; not found → noindex. **Also fixed a live bug**: Franklin & Marshall and Gardner-Webb team pages showed "Team Not Found" because `team_metrics` ids (`franklin_&_marshall`, `gardner-webb`) didn't match the team file names — `loadTeam()` now falls back to matching ignoring punctuation.
- `_redirects`: `/wrestler/* /wrestler.html 200`, `/team/* /team.html 200`. `scripts/site_checks/smoke_test.py`'s local server now applies `_redirects` 200 rewrites; `pages.json` has `wrestler-slug`, `wrestler-slug-season`, `team-slug` (all pass locally).
- `netlify/edge-functions/seo-pages.ts` (inline config: paths `/wrestler`, `/wrestler.html`, `/wrestler/*`, `/team`, `/team.html`, `/team/*`; `onError: bypass`; `cache: manual`). Markers `<!--EDGE:HEAD-->…<!--/EDGE:HEAD-->` around the static `<title>` in both pages. Fills `#wrestler-name`, `#wp2m-name`, `#wrestler-resume` (exact `app.js` format, latest season only) and `#team-name`. Its own lookups send `user-agent: MatSavant-Edge/1.0` (block-bots 403s an empty UA). No `og:image` yet (no PNG site image exists; later item).
- Tested locally in Deno with `context.next()` and site fetches simulated from disk: 19 cases (name pages, `?season`, uppercase/trailing slash → 301, old `?id=` → 301 keeping season/view, unknown → 404 noindex, team aliases, `abbreviations` → 404); and the edge output loaded in headless Chrome: page JS works on top of it, reuses the inline data (0 extra lookups), no duplicate tags, no errors.

**Verify on the `matsavant-dev` preview (can't be tested locally):** (1) `context.next()` on `/wrestler/<slug>` returns `wrestler.html` via the `_redirects` rewrite (if not, fetch `/wrestler.html` in the function instead); (2) block-bots still runs for these paths (inline-config vs `netlify.toml` function order) and its UA check lets the function's own `/seo/` fetches through; (3) `cache: manual` + `Netlify-CDN-Cache-Control` actually caches (response header `Cache-Status`) and `Netlify-Vary: query=season|view` collapses `fbclid` variants; (4) the function's same-site `fetch()` works on the preview host.

## Step 4 — Links across the site point at the new addresses — DONE 2026-10-07

~40 places in 24 files build `wrestler.html?id=` / `team.html?team=` links (`app.js` 6, `homepage.js` 4, `aa_odds.js` 4, `schedule.js`, `rankings.js`, `p4p_rankings.js`, `leaderboards/simple_leaderboard.js`, `hodge.js`, `freshman.js`, `championship_widgets.js` 2 each; `wrestlers.js`, `tools/compare.js`, `teams_directory.js`, `team.js`, `team_odds.js`, `reports/transfers/index.html`, `reports/team/index.html`, `ncaa_outlook_mobile.js`, `mobile_rank_row.js`, `leaderboards/xtp/teams.js`, `leaderboards/dpg.js`, `lab/hodge/index.html`, `homepage_team_odds.js`, `dual_ticker.js` 1 each), plus `scripts/generate_search_index.py` (the search index's `url`).
- One helper in `header.js` (loaded first on every page): `wrestlerHref(slug, id, opts)` → `/wrestler/{slug}` when the slug is known, else `/wrestler.html?id={id}` (which 301s); `teamHref(team_slug)` → `/team/{hyphenated}`.
- **Must convert:** search index, match history opponents (`opponent_url_slug`), team roster, rankings/P4P, wrestlers directory, compare, homepage. These are Google's main crawl paths. Add `url_slug` to whatever data those pages read (profiles already get it in Step 1; check the P4P/rankings files).
- **May stay** on the old form for now (they 301): minor Lab/report pages. List what's left in TODO.

**Built (2026-10-07):**
- `header.js` (top, global): `wrestlerHref(urlPath, id, {view})` and `teamHref(teamId)`. Wrestler links use the ready-made `url_path` from the data (`/wrestler/<slug>`, plus `?season=YYYY` only when that id isn't the wrestler's latest season, so a link from a 2024 match history still opens 2024); no `url_path` → old `?id=` form (301s).
- `build_url_slugs.py` now also writes `url_path` (profiles: `url_slug` + `url_path`; matches: `opponent_url_path`, replacing step 1's `opponent_url_slug`) and patches every object with a `wrestler_id` in `DATA_PATCH_GLOBS` (p4p, public_rankings, rankings, leaderboards, awards, xtp weight files, mat_value summaries — 332 files, each rewritten in its own exact JSON style, verified byte-identical apart from the new field). `search_index.js`: wrestler urls → name address with `wrestler_id` kept as a field, team urls → `/team/<id>` with `team_id` kept (`tools/compare.js` and `schedule.js` now read those fields; they used to parse `?id=` / `?team=` out of the url). **Pipeline: the step moved to the very END of the NCAA run**, because those files (and the 2nd profile pass) are rebuilt by earlier steps without the new fields.
- 40 link spots in 22 files converted. Left on old links on purpose (they 301): `lab/hodge/index.html` (its data has `id`, not `wrestler_id`), `reports/transfers`, `reports/team` (15k data files).
- Also fixed: the Wrestlers directory linked profile-less incoming wrestlers (P4P `wrestler_id: null`, e.g. Bo Bassett) to `?id=null`; they're plain tiles now.
- Link audit (headless Chrome, 17 main pages): 4,797 wrestler + 2,488 team links, all on the new addresses, every slug/season/team resolving; 0 JS errors. Full local smoke test 52/52.

## Step 5 — Static pages, sitemap, robots, bots, rate limit — DONE 2026-10-07 (local)

**Static page titles/descriptions** (hand-written in each HTML file, aimed at the keyword list). Examples: home `MatSavant — College Wrestling Stats, Rankings & Results`; rankings `NCAA Wrestling Rankings by Weight 2026-27 | MatSavant`; schedule `College Wrestling Schedule & Dual Results 2026-27 | MatSavant`; teams `College Wrestling Teams: Rosters, Lineups & Results | MatSavant`; NCAA event/live pages "NCAA Wrestling Championships … Team Scores"; Hodge, Scoring Trends, leaderboards each their own. Each gets a canonical (the URL form in the sitemap, `.html` included — Google currently indexes both `/ncaa_scoring_trends` and `/ncaa_scoring_trends.html`).

**Sitemap** (`scripts/generate_matsavant_sitemap.py`): one `/wrestler/{slug}` per slug (~14.8K) instead of 40.4K season IDs; `/team/{slug}` for the 87 teams; static pages; real lastmods (latest profile's `profile_generated_at`, team `generated_at_utc`, static page file date) instead of today's date for everything. Update the SEO Setup section of `docs/matsavant.md`.

**robots.txt:** move OAI-SearchBot, ChatGPT-User, PerplexityBot (+ add Perplexity-User) out of the blocked group into their own group: `Allow: /`, `Disallow: /data/`, `Disallow: /search_index.js`. GPTBot, CCBot, Google-Extended, Applebot-Extended and the rest stay `Disallow: /`.

**block-bots.ts:** for those four user agents, allow only if the request IP (`context.ip`) is inside the company's published ranges — `https://openai.com/searchbot.json`, `https://openai.com/chatgpt-user.json`, `https://www.perplexity.ai/perplexitybot.json`, `https://www.perplexity.ai/perplexity-user.json` (all confirmed live 2026-10-07). Fetch the lists once per edge instance and cache in module scope (~1 h); if a list can't be fetched, block (fail closed). Also 403 them on `/data/*` and `/search_index.js` even from valid IPs. A spoofed "ChatGPT" user agent from any other IP stays blocked as today.

**Rate limit on data:** new tiny edge function (body: `return context.next()`) with
```ts
export const config = { path: "/data/*", rateLimit: { windowLimit: 400, windowSize: 180, aggregateBy: ["ip", "domain"] } };
```
Personal plan allows 2 code-based rules per project. Before settling the number, measure the heaviest real page on the preview: **the team page fetches every roster wrestler's profile** (~40–50 data requests per view), so the cap must clear several team pages in 3 minutes. Over-limit → 429 within ~10 s (enforcement delay). Honest limit: it caps *speed* per IP; a patient scraper from one IP under the cap, or one spread over many IPs, still gets through — Cloudflare (TODO) remains the backstop. Confirm the rule appears in the deploy log.

**Built (2026-10-07):**
- Titles, descriptions and canonicals hand-written into 24 regular pages (canonical only on 4 that already had descriptions). Home is now `MatSavant — College Wrestling Stats, Rankings & Results` (was "…Analytics", a word nobody searches). `rankings.html`, `schedule.html`, `team_odds.html` carry "2026-27" — bump each season (added to the "Starting a New NCAA Season" checklist in docs/matsavant.md).
- `generate_matsavant_sitemap.py`: 14,959 URLs (36 static + 1 note + 14,843 `/wrestler/<slug>` + 79 `/team/<id>`), was 40,552; real lastmods.
- `robots.txt` + `block-bots.ts`: OAI-SearchBot, ChatGPT-User, PerplexityBot, Perplexity-User may read pages, only from the IP ranges in openai.com/searchbot.json, /chatgpt-user.json, perplexity.ai/perplexitybot.json, /perplexity-user.json (fetched per edge instance, cached 1 h, fail closed), never `/data/` or `search_index.js`. Training crawlers unchanged (blocked). Tested in Deno against the live lists: 14/14 cases.
- `rate-limit-data.ts`: `/data/*`, 600 requests / 180 s per IP. Measured /data/ requests per page load: big team roster 67 (Sacred Heart), Penn State 35, home 25, DPG leaderboard 11, wrestler 8, most others 1–5. Stops fast bursts, not a patient single-IP scraper under ~3 req/s (Cloudflare is the backstop).

## Step 6 — Test on `matsavant-dev`, then one production deploy

**Preview results (2026-10-07, matsavant-dev 266ce42dc1 + fix):**
- (1) `/wrestler/<slug>` and `/team/<slug>`: the `_redirects` rewrite works behind the edge function — 200 with the function's title, canonical, pre-filled name/season line; unknown → 404 + noindex. (2) block-bots still runs on these paths: fake `OAI-SearchBot` from a non-OpenAI IP, GPTBot, python-requests → 403 on pages and `/data/`; Googlebot UA → 200; the function's own `/seo/` lookups go through. (3) Caching: responses `stored`, repeat requests `hit`. (4) Same-site `fetch()` from the function works.
- Rate limit: 700 quick `/data/` requests from one IP → all 200, then 429 within ~12 s (Netlify's documented enforcement lag); pages unaffected.
- **Netlify re-appends the request's query string to any redirect whose target has none** (known CDN behavior; happens after the edge function, can't be stripped there): `wrestler.html?id=X` → `/wrestler/levi-haines?id=X`. Fix: old-id redirects always carry `?season=YYYY` (Netlify leaves targets with a query alone; it's also the season the old link meant). Old `team.html?team=x` links land on `/team/<name>?team=x` — accepted (works, canonical is clean, ~90 such URLs).

On the preview (free branch deploy; see memory "MatSavant preview branch" for the temp-index build-commit method):
1. `curl -s {preview}/wrestler/levi-haines | grep -E "<title>|description|canonical|og:"` → per-wrestler values in raw HTML. Same for a team and a no-career profile.
2. `{preview}/wrestler.html?id={old season id}` → 301 to `/wrestler/{slug}?season=YYYY`; latest id → bare slug; garbage id → 404.
3. `/team.html?team=ok_state` → 301 `/team/oklahoma-state`; `/team/grand-canyon` → 404.
4. A same-name wrestler (`tyler-johnson…`) and names with apostrophes/hyphens/accents render and escape correctly.
5. Force an error in the edge function → page still works through the client fallback (`onError: bypass`). Remove.
6. Click through: search box, rankings, team roster, match-history opponent, compare → all land on `/wrestler/…` directly (no redirect hop).
7. Rate limit: hammer `/data/…` from one machine → 429s after the cap; normal browsing (several team pages) never sees one.
8. Bots: `curl -A "OAI-SearchBot"` from a normal IP → 403; page fetch is otherwise unchanged for browsers.
9. Smoke test: add `/wrestler/{slug}`, `/team/penn-state` and one old-URL redirect to `scripts/site_checks/pages.json`; teach `smoke_test.py`'s local server (`translate_path`) the two `_redirects` rewrites so `--target local` passes. Run local before the push, live after (Hard Rules).
10. Edge function logs: no errors, CPU well under 50 ms.

After the production deploy:
- Search Console → Sitemaps: resubmit `sitemap.xml`. Pages → "Validate fix" on Duplicate and Soft 404. URL Inspection → "Request indexing" on ~10 important pages (top wrestlers, Penn State, rankings).
- Check at 2, 4 and 8 weeks: indexed count (baseline 4.1K of 40.6K URLs → target most of ~14.9K), clicks on name searches (baseline 0), total clicks (baseline 82 in 4 weeks). Expect 4–8 weeks for Google to recrawl.

## Later (not in this project)
- Structured data (schema.org `ProfilePage`/`Person`, `SportsTeam`).
- Per-wrestler share images (`og:image` card with name/record).
- Team pages for past seasons (`/team/penn-state?season=2024`).
- Publish the Lab NCAA Bracket Archive (people search "ncaa wrestling brackets 1993").
- Promotion push (InterMat forum, r/wrestling, team boards, podcasts/Substacks) — after the fix, so new visitors land on pages Google can show.

## Size
Biggest pieces: Step 3 (edge functions) and Step 4 (link conversion). Steps 1, 2, 5 are each modest. Realistically 2–3 working sessions, then the preview check with TJ, then one deploy.
