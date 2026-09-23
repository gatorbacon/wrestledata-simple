# KentuckyMat — AdSense "Low Value Content" Fix

**Status:** Decision pending (TJ). Written 2026-09-23.

## The Problem

kentuckymat.com applied to Google AdSense before/during last season and was flagged under
**Sites → "You need to fix some things" → Low value content**. TJ hasn't re-submitted since, so
that specific message may be stale — but the underlying technical issue it points at is real and
still present today.

**Root cause (diagnosed, not confirmed by Google directly):** Every page on the site — homepage,
rankings, leaderboards, team pages, and all 18,305+ wrestler career profiles — is a thin HTML
shell that loads its real content (rankings tables, win-loss records, match-by-match history)
via client-side JavaScript `fetch()` calls to JSON files, after the page loads. Measured raw HTML
word counts (before any JS runs): homepage 91 words, rankings/leaderboards ~25 words, wrestler
profile ~70 words. A real visitor with JS enabled sees all the real content (confirmed by real
weekly traffic in the thousands) — but AdSense's ad-review crawler is a **separate crawler from
Google's search indexer (Googlebot)**, and is understood to not reliably execute JavaScript the
way Googlebot does. It likely evaluates the site based on the near-empty raw HTML, which reads as
"low value" even though the site has substantial real value and real usage.

**Explicitly ruled out:** writing prose/articles/blog content as the fix. The real value is the
rankings and match data itself, already proven by real traffic — adding written commentary would
not be read and would not address the actual (technical) cause.

**Constraint:** ads are planned only on rankings pages and wrestler profile pages — any fix should
prioritize those two page types.

**Architecture constraint:** site is currently 100% static (no backend, no API — see main
`CLAUDE.md`), which some options below would preserve and some would step outside of.

---

## Proposals

### A. Re-request AdSense review now, before any code changes
Free and instant — tells us whether the stale flag still applies today, given the site has grown
substantially since the last (unknown-date) review attempt.

- ✅ Zero cost, zero engineering, immediate real signal
- ✅ Can be done in parallel with any of the options below, doesn't block them
- ❌ If the JS-rendering issue is the real cause, very likely to fail again for the same reason
- ❌ Burns a review cycle without new information if the underlying issue is unchanged

### B. Pre-render a handful of "hub" pages only (homepage, rankings, leaderboards)
Bake the current rankings/leaderboard tables directly into the static HTML at build time, reusing
data the weekly pipeline already computes. ~3-6 physical files total.

- ✅ Minimal effort — a handful of files, already regenerated weekly
- ✅ Covers what a reviewer/crawler would sample first
- ❌ Does **not** cover wrestler profile pages — the page type ads are actually planned on
- ❌ Likely insufficient alone, given the ad-placement plan

### C. Pre-render static pages for "ever ranked" wrestlers only
Generate real static HTML for the top 40 boys / top 24 girls per weight class each week
(~848 wrestlers/season snapshot), keyed off data the pipeline already produces. A page, once
created, is never deleted (even after the wrestler drops out of rankings), to avoid broken links.
Site links (team rosters, rankings tables, search, opponent links in match history) point to the
static page when the wrestler has one, and to the existing `wrestler.html?...` page otherwise —
decided once at link-generation time, not checked live in the browser.

- ✅ Directly targets exactly the pages both real traffic and the ad plan care about
- ✅ Bounded, contained growth (~1,000–1,500 new wrestlers/season, not the full 18,305+ archive)
- ✅ Reuses data the pipeline already computes weekly — not new data infrastructure
- ✅ Zero risk to the ~17,500 historical/unranked wrestler pages — untouched, unchanged
- ✅ Stays 100% static — no new architecture, no backend
- ❌ Real engineering work: needs a shared "who has a static page" lookup referenced by both the
  page generator and the existing client-side match-history JS (for correct opponent links)
- ❌ Any future shared-template change (header/footer/CSS) requires regenerating this whole
  (slowly growing) set, and that cost compounds every season
- ❌ Doesn't help crawler visibility outside the ranked set (acceptable — matches the ad plan and
  real traffic patterns)

### D. Full static generation — every wrestler, all 18,305+ career pages (and/or all 96,650+ season profiles)
Same idea as C but with no rank cutoff — every wrestler who's ever had a match gets a static page.

- ✅ Maximum coverage — nothing left dynamic-only, no lookup/manifest complexity
- ❌ **Measured cost**: current `data/careers` is 18,305 files / 409MB of JSON; full rendered HTML
  (markup + repeated nav/footer on every file, no server-side includes on static hosting) would
  likely add **700MB–1GB+**, nearly doubling the current 1.9GB site
- ❌ **Git history bloat compounds forever**: any shared template edit (nav link, footer, sitewide
  CSS) touches all 18,305+ generated files in one commit; repeated over years this could grow the
  already-1.6GB `.git` history to 10GB+, slowing every clone/pull/push indefinitely
- ❌ Weekly pipeline + deploy time grows substantially; any shared-template change forces a full
  (non-incremental) regeneration of the whole set
- ❌ Nearly all the added coverage goes to pages with ~zero real traffic (deep historical tail —
  nobody looks up an unranked 2014 wrestler), so cost/benefit is clearly worse than Option C

### E. Dynamic bot-specific prerendering (serve real content only to crawlers)
Put a small layer in front of the site (Netlify Edge Functions, or a hosted prerendering service)
that detects known bot user-agents (Googlebot, Mediapartners-Google, etc.) and serves them a
fully-rendered snapshot of the page. Real human visitors are completely unaffected — same JS-driven
site as today.

- ✅ Covers literally every page/URL at once — no bounded subset, no rank cutoff, no long tail left behind
- ✅ No growing file count, no git bloat, no "who has a static page" manifest, no opponent-link logic
- ✅ Doesn't touch any existing URLs, redirects, or client-side JS
- ✅ Industry-standard solution for exactly this class of problem (JS-heavy site + crawler visibility)
- ❌ Steps outside "100% static, no backend" — introduces one small dynamic layer or a third-party
  service dependency
- ❌ One more moving part to monitor (is it up, is it serving fresh snapshots)
- ❌ Pricing/limits for a hosted prerendering service not yet verified against this site's traffic/page count

---

## Open Questions Before Deciding
- Does re-requesting review now (Option A) still show "Low value content," or something else / nothing?
- Is TJ open to a small non-static component (Option E), or is staying 100% static a hard requirement?
- If Option E: what are current Netlify Edge Functions capabilities/limits, and/or pricing for a
  hosted prerendering service, at this site's traffic and page-count scale? (Not yet researched.)

## Recommendation (not yet acted on)
Do Option A immediately regardless of path (free, fast, real signal). Of the code paths, **C** is
the safer contained fix if staying fully static matters; **E** is the architecturally cleaner and
more complete fix if TJ is open to one small dynamic layer. **B alone and D are not recommended** —
B doesn't cover the pages that matter, D's cost is disproportionate to its benefit.
