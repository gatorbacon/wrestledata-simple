# KentuckyMat — Edge Function + AdSense Readiness Plan

**Status:** Phase 0, 1, and 3 complete and live; AdSense approved kentuckymat.com and ads are placed on production. Phase 3 detail lives in `kentuckymat_ads_phase3.md` (which replaces this doc's short Phase 3 section — see that doc's "Implementation Record" section for what actually shipped and why). Written 2026-09-23 in a claude.ai planning session with author.
**Supersedes:** the Proposals and Recommendation sections of `kentuckymat_adsense_content_fix.md`. That doc's problem statement is still accurate history, but its root-cause diagnosis turned out to be wrong (see "Revised diagnosis").

**Claude Code:** read this whole doc before starting. Anything under "Open items for TJ" that blocks a phase, ask TJ rather than guessing. Update the status table as phases complete.

| Phase | What | Production deploys | Status |
|---|---|---|---|
| 0 | Free test deploys via a `dev` branch | 0 | ✅ 2026-09-23 |
| 1 | Static fixes: share tags, trust pages, ads.txt → TJ requests AdSense review | 1 | ✅ 2026-09-23 — AdSense approved |
| 2 | Edge function on wrestler profile pages | 1 | ☐ not started |
| 3 | Ad placement (after AdSense approval) | 1 | ✅ 2026-09-23 — see `kentuckymat_ads_phase3.md` |
| 4 | Port the same changes to matsavant.com | — | later |

---

## TL;DR

- The "AdSense crawler can't see our JS-rendered content" diagnosis is almost certainly wrong. Google already renders our JavaScript (proof below), and the AdSense crawler renders through the same Google rendering service. None of the old static-generation options (B/C/D) or bot-only prerendering (E) are needed for AdSense.
- The more likely cause of "Low value content" is that the site doesn't explain itself: an 18k-page stats database with no About, methodology, contact, or privacy page. Phase 1 fixes that for $0.
- Separately, everything that is *not* Google (Facebook/iMessage/Discord/X link previews, AI crawlers) does not run our JS and sees only the static HTML shell — and the static tags are broken. Matsavant's xTP description is leaking into every shared KentuckyMat profile. Phase 1 fixes the static tags; Phase 2 adds one small edge function that writes per-wrestler tags, a header summary, and the wrestler's JSON directly into the HTML.
- The site stays static except for that one function. It is cached at the CDN, fails open to today's exact page, and costs pennies of credits.

---

## Revised diagnosis

### Finding 1 — Google renders our JavaScript
Searching `micah thompson josh tuttle` on Google returns KentuckyMat profile pages whose snippets contain match-history rows: opponent name, rank, "TF 16-0", school, weight class, date. That text exists only in the career JSON that `wrestler.html` loads via `fetch()` after page load, so Googlebot executed the JS and indexed the rendered table. The result titles are per-wrestler too (`joshua Tuttle | Kentucky High School Wrestling | Fairdale`), so the JS-set title and description are being picked up.

### Finding 2 — The AdSense crawler uses the same renderer
- MERJ's 2024 server-log analysis: AdSense page fetches arrive as `Mediapartners-Google`, then Google's Web Rendering Service renders the page and requests the subresources (JS, JSON) under the `Googlebot` user-agent.
- Google's AdSense help: the AdSense crawler and Googlebot are separate crawlers but share a cache.

Conclusion: the thin raw HTML (~25–90 words) is very unlikely to be what triggered "Low value content." That flag is a site-level judgment and is sometimes made by a human reviewer. A reviewer landing on 18k templated stat pages with no About/Methodology/Contact/Privacy has no way to tell this is a real, original publication with real users.

One robots.txt check still matters, from MERJ's findings: if anything blocks `Googlebot` from our JS or `/data/` paths, the AdSense render comes out partial or blank. Confirm nothing in `robots.txt` or `_headers` does (Phase 1.6).

### Finding 3 — Everything that isn't Google sees only the static shell
Facebook Sharing Debugger on `https://kentuckymat.com/wrestler.html?career_id=career_000279&gender=boys` shows:
- `og:title`: `Wrestler Profile | KentuckyMat` (generic)
- `og:description`: `Expected Team Points (xTP) estimate how many NCAA tournament points a wrestler is likely to contribute…` — **Matsavant copy leaked into the KentuckyMat template.** Every shared profile currently describes KentuckyMat as an NCAA points model.
- no `og:image` (Facebook flags this as a warning)

That same static shell is all iMessage, Discord, X, Slack, and AI crawlers (GPTBot, ClaudeBot, PerplexityBot) see. Per Vercel/MERJ crawl data, those AI crawlers download JS files but never execute them.

### Finding 4 — Data quality
`joshua Tuttle` (lowercase first name) is in the source data and shows up that way in Google's result title.

### Verdicts on the old options
| Old option | Verdict |
|---|---|
| A. Re-request AdSense review | Yes — at the end of Phase 1, after the trust pages are live |
| B. Pre-render hub pages | Not needed |
| C/D. Static page generation | Not needed for AdSense. Don't do. |
| E. Bot-only prerendering | Rejected. Serving different HTML by user-agent is what Google calls "dynamic rendering," and Google's docs now label it a workaround, not a recommended long-term solution (they recommend server-side rendering, static rendering, or hydration instead). |
| Full server rendering of match tables at the edge | Deferred. It would mean a second copy of the table-rendering code to keep in sync with the client JS. Revisit only if AI-search visibility of full match histories becomes a priority. |

---

## Goals and constraints

- Get AdSense approved. Ads go only on rankings pages and wrestler profile pages.
- Make profile pages load faster.
- **No new monthly cost** beyond what trivial ad revenue covers. No database, no server, no third-party service. Neither KentuckyMat nor Matsavant has income yet.
- The site stays static except for one edge function. If the function errors, visitors get exactly today's page (`onError: "bypass"`).
- **Minimize production deploys** — each costs 15 credits and deploys are currently the biggest credit cost. Do all work and testing on branch deploys (0 credits), batch changes, go live once per phase.
- About/Contact content must not identify TJ personally. Use a site email address, not a personal one.
- Build it portable: TJ plans to apply the same changes to matsavant.com later.

---

## Cost model (Netlify credit-based plans, Sept 2026)

| Item | Credits |
|---|---|
| Production deploy | 15 each |
| Branch deploy / Deploy Preview | 0 |
| Web requests (page views, assets, redirects, **edge function invocations**) | 2 per 10,000 |
| Bandwidth | 20 per GB |
| Edge function compute | Not billed as compute — counted as web requests |

Estimate: 50,000 profile views/month ≈ 10 credits of edge invocations, plus the function's own JSON fetch on cache misses. With CDN caching (Phase 2.4) most requests are cache hits. Net: pennies per month. Ad scripts and creatives are served by Google, not Netlify, so ads add no Netlify bandwidth.

Plan caveats: Free = 300 credits, hard cap, the site pauses when they run out. Personal (~$9) = 1,000 credits and also pauses when they run out unless auto-recharge is enabled (off by default). TJ has one site on Free and one on Personal and isn't sure which is which — see Open items.

---

## Phase 0 — Free test deploys (do first)

**TJ (Netlify UI, one time):** Project configuration → Build & deploy → Continuous deployment → Branches and deploy contexts → Configure → "Let me add individual branches" → add `dev`.

**Claude Code:**
1. `git checkout -b dev && git push -u origin dev`. The preview lives at `https://dev--<netlify-site-name>.netlify.app` (site name as shown in the Netlify dashboard).
2. Add to `CLAUDE.md`:
   > Code and content work happens on the `dev` branch. Never commit or push to `main` unless TJ explicitly says to go live. (Exception: the weekly data pipeline, if it commits to `main` by design.)
3. Check how the weekly data pipeline commits. If it pushes to `main`, then at the start of each work session run `git checkout dev && git merge main` so the preview has current data and the eventual merge back is clean.
4. Grep for hard-coded `https://kentuckymat.com` in `fetch()` calls, links, and script/style `src`/`href`. Convert to root-relative paths (`/data/...`) so the preview uses its own files. **Exception:** canonical, `og:url`, and `og:image` must stay absolute production URLs.
5. `curl -I` the preview URL and check whether Netlify sends `X-Robots-Tag: noindex` on branch deploys, so Google doesn't index the dev copy. If it doesn't, note it here and flag it to TJ.

Going live = `git checkout main && git merge dev && git push && git checkout dev` (one 15-credit deploy), or a GitHub PR from `dev` → `main`.

---

## Phase 1 — Static fixes, then request review (1 production deploy)

### 1.1 Fix static share/meta tags on every template
- Grep all HTML templates for leaked Matsavant text: `xTP`, `Expected Team Points`, `NCAA`, `Matsavant`, `TPAR`. Remove or replace.
- Give every page type (homepage, rankings, leaderboards, team pages, wrestler profile, any others) correct static defaults: `<title>`, meta description, `<link rel="canonical">`, `og:title`, `og:description`, `og:url`, `og:site_name` = KentuckyMat, `og:type`, `og:image` (+ `og:image:width`/`height`), `twitter:card` = `summary_large_image`.
- On `wrestler.html` these static values become the fallback that the edge function overwrites. Wrap them in markers so Phase 2 can swap the whole block:
  ```html
  <!--EDGE:HEAD:START-->
  <title>Wrestler Profile | KentuckyMat</title>
  <meta name="description" content="...">
  ...
  <!--EDGE:HEAD:END-->
  ```
- If any templates or includes are shared with the Matsavant codebase, note which ones here so Phase 4 can check for a reverse leak.

### 1.2 Default share image
`/images/og-kentuckymat.png`, 1200×630, under ~300 KB. TJ supplies artwork; if it isn't ready, generate a simple wordmark-on-brand-color placeholder. Reference it by absolute URL.

### 1.3 Trust pages (the actual AdSense fix)
Short, plain, factual. Link all four from a sitewide footer.
- `/about.html` — what KentuckyMat covers (Kentucky high school wrestling, boys and girls), what's on the site (rankings, leaderboards, team pages, 18k+ career profiles), where the data comes from, how often it updates. No owner name or personal details.
- `/methodology.html` — how rankings are built (e.g. top 40 boys / top 24 girls per weight class), how leaderboard stats like win % and bonus rate are defined, how season vs. career records work. Derive from the pipeline code. **TJ must review for accuracy before it goes live.**
- `/contact.html` — a site email address or a Netlify Form (forms are free on Netlify's credit-based plans). Framing it around corrections (wrestlers, parents, coaches reporting data errors) fits the site.
- `/privacy.html` — must cover: Google and third-party vendors use cookies to serve ads based on prior visits to this and other sites; Google's use of advertising cookies; how users can opt out (Google Ads Settings, aboutads.info); Google Analytics, if GA4 is installed (check); a contact for privacy questions.

### 1.4 ads.txt
`/ads.txt` at the site root, served as text/plain, containing the line from TJ's AdSense account (AdSense → Sites → ads.txt shows it exactly):
```
google.com, pub-XXXXXXXXXXXXXXXX, DIRECT, f08c47fec0942fa0
```
Also confirm the AdSense verification code or meta tag from the original application is still on the homepage.

### 1.5 Name capitalization (optional, cheap)
In the pipeline output, capitalize name tokens that are **entirely lowercase** (`joshua` → `Joshua`). Leave mixed-case tokens alone so `McDaniel`, `DeJesus`, `O'Neal` are untouched; treat each part of a hyphenated name separately. Log how many names changed. Can ride along with the next data run.

### 1.6 Verify on dev, then go live
- FB Sharing Debugger on a dev profile URL → correct KentuckyMat description and image. (Title stays generic until Phase 2 — expected.)
- Footer links work on every page type; `/ads.txt` is served as plain text.
- `robots.txt` and `_headers` don't block `Googlebot` from JS or `/data/`.
- Merge to `main` (**1 production deploy**).
- **TJ:** AdSense → Sites → kentuckymat.com → request review. Record the result in this doc. Phase 2 continues on `dev` while the review runs.

---

## Phase 2 — Edge function for wrestler profiles (1 production deploy)

### 2.1 What it does
For each request to the profile page:
1. Parse and validate `career_id` and `gender`. Confirm the real ID format from the data (looks like `career_\d{6}`) and the allowed genders (`boys`, `girls`). Invalid or missing → `return context.next()` untouched.
2. In parallel: `context.next()` (the static `wrestler.html`) and `fetch()` the career JSON from the same origin (`new URL(path, request.url)`, so dev previews read dev data). If the page response isn't 200 or the JSON isn't 200 → return the page response unchanged.
3. Parse the JSON for only the fields needed: name, school, career W-L and percentage, current-season record and rank.
4. String-replace into the HTML:
   - **Head block** (between the `EDGE:HEAD` markers): per-wrestler title, meta description, canonical, `og:*`, `twitter:*`.
   - **Profile header:** pre-fill name, school, career record, current-season record and rank.
   - **Inline data:** `<script id="career-data" type="application/json">…</script>` containing the JSON the page would otherwise fetch.
5. Return with the caching headers in 2.4.

### 2.2 Why each piece
| Piece | Benefit |
|---|---|
| Head tags | Correct link previews on Facebook, iMessage, Discord, X; correct title/description for every crawler that doesn't run JS |
| Header pre-fill | Name, school, and record present in raw HTML → readable by AI crawlers, and visible at first paint |
| Inline JSON | Removes the sequential HTML → JS → `fetch(JSON)` round trip, so tables render as soon as the JS runs. The client JS stays the only table renderer — nothing to keep in sync. |

### 2.3 Implementation notes
- **File:** `netlify/edge-functions/wrestler-page.ts` (Deno/TypeScript).
  ```ts
  import type { Config, Context } from "@netlify/edge-functions";

  export const config: Config = {
    path: ["/wrestler.html", "/wrestler"], // confirm which paths actually serve the page
    onError: "bypass",   // any error → today's static page is served
    cache: "manual",     // required for CDN caching; cache headers alone do nothing
  };
  ```
- **Paths:** Google displays these URLs as `kentuckymat.com › wrestler`. Check whether `/wrestler?...` also serves the page (Netlify can serve `x.html` at `/x`) and include every path that does.
- **Markers, not DOM parsing:** string replacement on comment markers placed in `wrestler.html`. Fast, no dependencies. If a marker is missing, skip that injection — never throw.
- **Response headers:** build the new Response from the original's status and headers, but **remove `content-length`, `etag`, and `last-modified`**. The static file's validators no longer describe the modified body; leaving them in lets a browser get a 304 after a data deploy and keep showing last week's injected data.
- **Title/description formats:** reuse exactly what the client JS already sets. Google has indexed `{Name} | Kentucky High School Wrestling | {School}` and `{Name} career record W-L (.pct), Kentucky high school wrestling, {School}.` Put the format functions in one small module that both the edge function and client JS import if practical; otherwise copy them with a comment pointing to the source of truth.
- **og:description** can be a little richer for shares, e.g. `Boyle County · Career 260-46 (.850) · #1 at 165 (2025-26)`. Keep it factual.
- **Canonical / og:url:** always `https://kentuckymat.com/wrestler.html?career_id=X&gender=Y` — only those two params, fixed order, absolute production domain even on dev. This collapses `fbclid`/`utm_*` duplicates.
- **Escaping:**
  - HTML-escape every value inserted into text or attributes (`& < > " '`).
  - Inline JSON: insert the raw fetched text (don't re-stringify) with `<` replaced by `\u003c` and U+2028/U+2029 escaped, so data can never close the `<script>` tag.
- **Size guard:** measure the largest career JSON. If a file exceeds a threshold (start around 150 KB), don't inline it; inject `<link rel="preload" href="/data/…json" as="fetch" crossorigin>` instead so the fetch starts in parallel with the JS. Verify in DevTools that the preload is actually consumed (no duplicate request).
- **Inventory first:** list every `fetch()` the profile page makes on load. Inline the ones needed for first render (the career file, possibly a season file); leave the rest.
- **Client JS change (small):**
  ```js
  const el = document.getElementById("career-data");
  const data = el ? JSON.parse(el.textContent) : await fetch(url).then(r => r.json());
  ```
  Keep the fetch fallback — the page must still work whenever the function bypasses.
- **Header pre-fill must match** the markup the JS renders into the same elements, so nothing visibly changes when the JS runs (no flicker, no layout shift). Prefer filling the existing header elements over adding a new block.
- **CPU:** the limit is 50 ms of CPU per request; time spent waiting on `fetch` doesn't count. String replacement plus parsing one career file should be far below that — confirm with the largest file in the function logs.

### 2.4 Caching
Set on the returned response:
```
Netlify-CDN-Cache-Control: public, s-maxage=604800
Cache-Control: public, max-age=0, must-revalidate
Netlify-Vary: query=career_id|gender
```
- Cached edge responses are discarded automatically on every new deploy (atomic deploys), so the weekly data deploy refreshes everything with no manual purging.
- Without `Netlify-Vary: query=…`, the entire query string is the cache key and every `fbclid`/`utm` variant becomes its own cache entry. Limiting it to the two real params raises the hit rate. Confirm the exact `Netlify-Vary` syntax against Netlify's caching docs.
- Browsers still revalidate on each visit (`max-age=0`), same as today.

### 2.5 Rankings pages (only if needed)
Inventory the rankings/leaderboard URLs. If each view is its own static file, the Phase 1 static tags are enough. If views are query-param driven (e.g. `rankings.html?weight=165&gender=boys`), add that path to the same function with per-view titles (e.g. `165 lbs Boys Rankings | Kentucky High School Wrestling | KentuckyMat`) and inline the rankings JSON if the size guard allows.

### 2.6 Test plan (all on the `dev` branch deploy)
1. `curl -s "https://dev--SITE.netlify.app/wrestler.html?career_id=career_000279&gender=boys" | grep -E "<title>|og:title|og:description|career-data"` → per-wrestler values in the raw HTML.
2. Two different wrestlers back-to-back → different tags. Same wrestler with `&fbclid=test` → same content, and the `Cache-Status` response header shows a cache hit.
3. Bad inputs return the static page unchanged, never a 500: missing `career_id`, `career_id=../../x`, a nonexistent ID, `gender=xyz`.
4. Temporarily throw inside the function → page still loads (bypass works). Remove the throw.
5. FB Sharing Debugger on the dev URL → wrestler name, record, image.
6. Browser DevTools: no separate career-JSON request when inlined; header doesn't flicker or shift; a request the function doesn't handle still renders via the fallback fetch.
7. Names with apostrophes and hyphens render and escape correctly.
8. Redeploy `dev` with changed data, then reload a profile in the same browser → new data shows (validates the header stripping in 2.3).
9. Lighthouse (mobile) before/after on three profiles — small, typical, and largest career. Record LCP in this doc.
10. Netlify edge function logs: no errors; CPU comfortably under 50 ms on the largest file.

Then merge to `main` (**1 production deploy**). After go-live: FB Sharing Debugger → "Scrape Again" on a few profile URLs that have already been shared (Facebook caches old previews), and Search Console URL Inspection on one profile.

---

## Phase 3 — Ad placement (after approval, 1 production deploy)
- Manual ad units on rankings and profile pages only (or Auto ads with every other page type excluded).
- Every ad slot gets a container with a fixed `min-height` matching its unit size (e.g. 250px for a 300×250) so content never jumps when an ad loads — prevents layout shift and accidental taps.
- Keep the profile header/summary above the first ad so the main content is the first thing that paints.
- Load `adsbygoogle.js` with `async`.

---

## Phase 4 — Port to matsavant.com (later)
Same sequence: fix static tags (including wherever the xTP text is shared between the two codebases), trust pages, ads.txt, then an edge function for its per-wrestler pages. Write the Phase 2 function with the site-specific values (domain, paths, title formats, data paths) in one config object at the top so it can be copied over with minimal edits.

---

## Open items for TJ
- [ ] Enable branch deploys for `dev` in Netlify (Phase 0).
- [ ] Confirm which Netlify plan KentuckyMat is on. If Free, it pauses when the 300 credits run out — decide before the season. If Personal, decide whether to turn on auto-recharge.
- [ ] Share-image artwork, or approve a placeholder.
- [ ] Review the About and Methodology text for accuracy.
- [ ] AdSense publisher ID / ads.txt line.
- [ ] Site contact email address to publish.

---

## References
- MERJ, "Discovering and Diagnosing a Google AdSense Rendering Bug" (2024): https://merj.com/blog/discovering-and-diagnosing-a-google-adsense-rendering-bug
- Google AdSense Help, "About the AdSense ads crawler": https://support.google.com/adsense/answer/99376
- Google Search Central, "Dynamic rendering as a workaround": https://developers.google.com/search/docs/guides/dynamic-rendering
- Vercel, "The rise of the AI crawler": https://vercel.com/blog/the-rise-of-the-ai-crawler
- Netlify Docs, "How credits work": https://docs.netlify.com/manage/accounts-and-billing/billing/billing-for-credit-based-plans/how-credits-work/
- Netlify Docs, "Branch deploys": https://docs.netlify.com/deploy/deploy-types/branch-deploys/
- Netlify Docs, "Optional configuration for edge functions" (`onError`, `cache`): https://docs.netlify.com/build/edge-functions/optional-configuration/
- Netlify Docs, "Caching overview" (`Netlify-Vary`): https://docs.netlify.com/platform/caching/
- Netlify KB, "How to run code at the edge with Netlify Edge Functions" (50 ms CPU limit): https://www.netlify.com/knowledge-base/how-to-run-code-at-the-edge-with-netlify-edge-functions/
- Netlify KB, "How to control CDN caching on Netlify": https://www.netlify.com/knowledge-base/how-to-control-cdn-caching-on-netlify/
