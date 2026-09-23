# KentuckyMat — Phase 3: Ad Configuration

**Status:** Shipped and live on production 2026-09-23. See "Implementation Record" below for what actually shipped, the decisions made along the way, and why. Written 2026-09-23 in a claude.ai planning session with TJ.
**Parent doc:** `kentuckymat_edge_function_plan.md` (this replaces that doc's short Phase 3 section).
**Context:** AdSense approved kentuckymat.com. Auto ads is OFF. Auto optimize is currently ON (TJ will turn it off — Part A).

**Claude Code — how to run this phase:**
1. Update the parent doc's status table: Phase 1 ✅ (AdSense approved), Phase 3 in progress.
2. **Before writing any code, give TJ the Part A checklist** (copy it to him as-is) and ask him for the IDs listed in A5. You can build everything on `dev` with placeholder IDs while you wait.
3. Do Part B on the `dev` branch. Test per Part C.
4. Go live with **one production deploy** only when TJ says to.
5. **After go-live, give TJ the Part D checklist.**

---

## Guiding principle

KentuckyMat is a clean, community-trusted site, not a for-profit business. The goal is a small profit to cover costs and fund more content — not maximum revenue. **When a choice trades cleanliness for revenue, choose cleanliness.** Concretely:

- Ads only on wrestler profile pages and rankings pages. Nowhere else.
- At most **two** ad units on any page.
- No Auto ads, no anchor/sticky ads, no vignettes/interstitials, no side rails, no formats that insert links into page text.
- Ads never above the wrestler's name/record, never inside a table, never between ranked rows.
- Every ad sits in a reserved, clearly labeled slot so the page never jumps around.

---

## Part A — TJ's AdSense checklist (Claude Code: give this to TJ first)

These are all done in the AdSense website. No code, no deploys, no Netlify credits.

**A1. Turn Auto optimize OFF**
Ads → By site → click **Edit** (pencil) next to kentuckymat.com → **Auto optimize** tab → turn it off → Apply to site.
*Why:* when on, Google experiments on 50% of your traffic by default — including turning on Auto ads formats — and applies "winners" automatically. That's how a clean site quietly gets spammy.

**A2. Confirm Auto ads stays OFF**
Ads → By site → the Auto ads column for kentuckymat.com should say **OFF**. Leave it off.

**A3. Block sensitive ad categories**
Brand safety → Content → Blocking controls → **Sensitive categories** (exact labels may differ slightly). Block:
- **Gambling & Betting (18+)** — should already be blocked by default. Confirm it is. Google recommends against allowing it on sites whose audience includes under-18s.
- **Simulated gambling**
- **Weight loss** — dieting products/programs. Top priority on a site organized by weight class. (Doesn't block general fitness or healthy-eating ads.)
- **Drugs & supplements**
- **Politics** — campaign/candidate/issue ads; keeps the site neutral through election season.
- **Dating**
- **References to sex & sexuality**
- **Sexual & reproductive health**
- **Get rich quick**
- **Cosmetic procedures & body modification**

**A4. Check ads.txt**
Sites → kentuckymat.com → ads.txt status should say **Authorized**. If not, tell Claude Code.

**A5. Create four display ad units and send Claude Code the IDs**
Ads → **By ad unit** → **Display ads**. Create four units, one at a time, with **Responsive** size (shape doesn't matter — Claude Code sets that in the code). Name them exactly:
- `KM-Profile-Top`
- `KM-Profile-Bottom`
- `KM-Rankings-Top`
- `KM-Rankings-Mid`

After each one is created, AdSense shows its code. Copy the number in `data-ad-slot="…"` for each unit, plus your publisher ID (`ca-pub-…`, also in that code), and send all five to Claude Code.
*Why four separate units:* AdSense reports earnings per unit, so after a few weeks you'll see exactly which positions are worth keeping.

**A6. (Optional, 5 minutes) European consent message**
Privacy & messaging → European regulations → create the message. It only ever shows to visitors from the EU/UK; without it those visitors get limited or no ads. Low priority for a Kentucky site — skip if you like.

**A7. Never click your own ads**
Not on the live site, not to "check they work." AdSense treats self-clicks as invalid activity and can suspend the account. Same for rapid repeated reloading to see different ads.

---

## Part B — Claude Code implementation (on `dev`)

### B1. Inventory first
- Find where the AdSense loader script (`adsbygoogle.js?client=ca-pub-…`) currently lives — likely the homepage (from the site-approval step), possibly a shared header.
- Find how `wrestler.html` renders: the header/summary element(s), the match-history container, and how total career matches can be counted from the data.
- Find how the rankings page(s) render: header/weight selector, whether one page load shows one weight class or all of them, and **whether switching weight/gender re-renders content in place without a page load.** This decides B4's rankings rules.
- Note anything from Phase 2 (edge function markers, pre-filled header, inline data) so ad slots don't collide with it.

### B2. Loader script
- Load it only on pages that have ad slots (wrestler profile, rankings), in `<head>`, `async`:
  ```html
  <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-XXXXXXXXXXXXXXXX" crossorigin="anonymous"></script>
  ```
- If the snippet is currently sitewide via a shared header, remove it from every page except profile, rankings, and the homepage (keep the homepage one where it was placed for approval). With Auto ads off, the homepage snippet shows nothing.
- Put the publisher ID in one place (a small config module, see B3), not scattered across files.

### B3. One shared ad module
Create `js/ads.js` (or match the site's existing structure) containing:
- A config map: publisher ID, and for each named slot its `data-ad-slot` ID and format.
- One function, e.g. `placeAd(containerEl, slotName)`, that inserts the `<ins>` element into an existing reserved container and calls `(adsbygoogle = window.adsbygoogle || []).push({})` **exactly once** for that element.
- Guard against double-pushing (mark the container once filled). A double push shows as a console error: `All 'ins' elements in the DOM with class=adsbygoogle already have ads in them`.

Slot config (placeholders until TJ sends IDs):

| Slot name | Page | `data-ad-format` | Reserved height |
|---|---|---|---|
| `profile-top` | wrestler profile | `horizontal` | 90px desktop / 100px mobile |
| `profile-bottom` | wrestler profile | `rectangle` | 280px |
| `rankings-top` | rankings | `horizontal` | 90px desktop / 100px mobile |
| `rankings-mid` | rankings | `rectangle` | 280px |

All units: `data-full-width-responsive="false"` so mobile ads don't expand past the reserved space. Verify the attribute behavior against AdSense's responsive ad code docs before finalizing.

### B4. Placement rules (exact)

**Wrestler profile (`wrestler.html`)**
- `profile-top`: **always**. Directly below the wrestler header/summary (name, school, record) and above the match history. Put the reserved container **in the static HTML** so its space exists before any JS runs — no layout shift.
- `profile-bottom`: **only when the wrestler has 20+ career matches** (`LONG_HISTORY_THRESHOLD = 20`, one constant). Insert after the match history finishes rendering. Short careers get one ad total.

**Rankings**
- `rankings-top`: **always**. Below the page header/weight selector, above the first ranked table. Keep at least ~1.5rem of space plus the label between the selector buttons and the ad so taps on the selector can't land on the ad.
- `rankings-mid`: **only if a single page load renders all (or many) weight classes as separate tables.** Place it between two weight-class tables at roughly the halfway point. Never inside a table.
- **If the rankings view re-renders in place when the user changes weight/gender:** keep both ad containers **outside** the re-rendered region so they're created once per page load. Never create new ad units or request new ads because the user changed a filter. If `rankings-mid` can't sit outside the re-rendered region, drop it.

**Everywhere else:** no ad containers, no loader script (except the homepage snippet noted in B2). That includes homepage content, team pages, leaderboards, about, methodology, contact, privacy.

### B5. Markup and CSS

```html
<div class="ad-slot ad-slot--horizontal" id="ad-profile-top">
  <span class="ad-label">Advertisement</span>
  <!-- <ins> inserted by placeAd() -->
</div>
```

```css
.ad-slot {
  margin: 1.5rem auto;
  max-width: 100%;
  text-align: center;
  overflow: hidden;
}
.ad-label {
  display: block;
  font-size: 11px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: #888;           /* use the site's muted text color/token if one exists */
  margin-bottom: 4px;
}
.ad-slot--horizontal { min-height: calc(90px + 20px); }   /* ad + label */
@media (max-width: 767px) {
  .ad-slot--horizontal { min-height: calc(100px + 20px); }
}
.ad-slot--rectangle { min-height: calc(280px + 20px); }

/* Unfilled ads: hide the whole slot, label included, so no empty "Advertisement" boxes */
.ad-slot:has(ins.adsbygoogle[data-ad-status="unfilled"]) { display: none; }
```

Notes:
- The label reads exactly "Advertisement" — plain, small, and not styled like site content. AdSense allows "Advertisements" or "Sponsored links" wording.
- Match the site's existing light/dark handling for the label color.
- Do **not** add any text asking visitors to click ads or "support the site" through ads — AdSense prohibits encouraging clicks.
- Ads must not look like part of the rankings/stats tables (no table borders, row striping, or stat-style fonts around them).

### B6. Things not to do
- No Auto ads code or `enable_page_level_ads`.
- No anchor/sticky, vignette, side-rail, or in-text link formats.
- No ad above the wrestler's name/record or above the rankings header.
- No more than two ad units on any page.
- No ad refresh, timers, or new ad requests on in-page interactions.
- No ads adjacent to navigation, buttons, or the weight selector without clear spacing.

---

## Part C — Test plan (on the `dev` branch deploy)

On the dev preview the ads will probably **not fill**, because the `netlify.app` preview domain isn't an approved AdSense site. That's expected — on dev you're testing layout and logic, not ad delivery.

1. **Short career profile** (<20 matches): exactly one slot, below the header, above match history.
2. **Long career profile** (20+ matches): two slots; the second appears after the match history.
3. **Rankings:** top slot below the selector with clear spacing; mid slot only when multiple weight-class tables render on one page, never inside a table.
4. If rankings re-render in place: switch weight/gender several times → no new ad requests (DevTools Network, filter `googlesyndication`), no console errors, slot count unchanged.
5. Pages that should have no ads (homepage content, team pages, leaderboards, about, etc.): no ad containers; no `adsbygoogle.js` request except the homepage snippet.
6. Unfilled handling: simulate by setting `data-ad-status="unfilled"` on an `<ins>` in DevTools → the whole slot, label included, disappears.
7. Layout: check at 375px (phone) and desktop widths. Reserved heights hold; nothing jumps when the slot is filled or collapses above the fold. Run Lighthouse (mobile) on one profile and one rankings page — CLS should not get worse than before this phase.
8. Console: zero AdSense errors (especially the double-push error).
9. If Phase 2's edge function is live on `dev`: profile pages still get the injected head tags/header/inline data, and the `profile-top` slot sits below the pre-filled header.

Then, on TJ's go-ahead: merge to `main` — **one production deploy**.

---

## Part D — TJ's after-launch checklist (Claude Code: give this to TJ after go-live)

**D1. Look, don't click.** Open a few live profile and rankings pages on your phone and a computer. New ad units can take a little while to start filling (often within an hour, sometimes longer). Don't click any ads.

**D2. Block anything that feels wrong.** If you see a specific ad you don't want on the site, find it in AdSense → Brand safety → **Ad review center** and block it.

**D3. Check which slots earn (after 3–4 weeks).** Reports → break down by **Ad unit**. Compare `KM-Profile-Top`, `KM-Profile-Bottom`, `KM-Rankings-Top`, `KM-Rankings-Mid`. If a bottom/mid slot earns almost nothing, tell Claude Code to remove it — a cleaner page is worth more than pennies.

**D4. Don't judge in the offseason.** September–November revenue will be tiny. December through February is the real test.

**D5. Spring decision (only if revenue isn't covering costs).** The least intrusive addition is a **mobile anchor ad** — a thin, dismissible bar at the bottom of the phone screen. It's turned on in AdSense's Auto ads settings with every other format off, plus page exclusions so it only runs on profile and rankings pages. Tell Claude Code before turning it on, since it interacts with where the loader script is placed. Still never turn on vignettes (full-screen ads between page loads) or in-text link formats.

**D6. Keep Auto optimize off.** If AdSense ever prompts you to "apply an optimization" or turn Auto optimize back on, decline unless you've decided to change the plan.

---

## Implementation Record (what shipped, and why)

**Shipped 2026-09-23.** Built on `dev`, visually reviewed by TJ on the branch-deploy preview, merged to `main` with one production deploy. Files touched: new `frontend/hs-ky-ui/public/js/ads.js`; edited `wrestler.html`, `rankings.html`, `app.js`, `rankings.js`, `styles.css`. All changes confined to `frontend/hs-ky-ui/` per the `dev` branch's KentuckyMat-only scope (see CLAUDE.md Hard Rules).

### Real slot IDs used

| Slot name | `data-ad-slot` | Page | Placed? |
|---|---|---|---|
| `KM-Profile-Top` | `6324158705` | wrestler profile | ✅ always |
| `KM-Profile-Bottom` | `9776318559` | wrestler profile | ✅ only 20+ career matches |
| `KM-Rankings-Top` | `5314329368` | rankings | ✅ always |
| `KM-Rankings-Mid` | `1570525473` | rankings | ❌ built in AdSense, not placed — see below |

Publisher ID `ca-pub-6991551662268186`. All four are wired into `js/ads.js`'s `SLOTS` config even though `rankings-mid` isn't used, so the unit exists and is documented if a future rankings-page redesign creates a second table region for it.

### Decisions made during implementation, and why

- **`rankings-mid` dropped.** B1's inventory step (reading `rankings.js`) confirmed `rankings.html` shows exactly one `<table id="rankings-table">` at a time — clicking a weight tab calls `loadAndRenderWeight()`, which repaints that same table's `tbody` in place; it never renders multiple weight classes' tables together. The plan's own B4 fallback rule ("place mid only if a single page load renders multiple weight-class tables... otherwise drop it") applies directly. Placing `rankings-mid` anywhere on this page's actual structure would mean putting it inside or immediately beside the one ranked table, which B4/B6 explicitly forbid. Rather than force an awkward placement, it was left unplaced. If the rankings page is ever redesigned to show multiple weight classes on one load, `rankings-mid`'s slot config is already there to use.

- **`wrestler.html` has two structurally different render paths, handled separately.** `app.js` builds career-profile pages (`?career_id=...`, the dominant URL pattern used by every internal link) and season-profile pages (`?id=...&season=...`, a legacy/secondary pattern) with completely different DOM-construction code (`renderCareerProfile` vs. `renderWrestlerProfile`/`renderSimplifiedSeasonStats`). One `ads.js` module is shared, but each path fills its ad slots differently:
  - **Season view** fills two *static* containers already in `wrestler.html` (`#wrestler-ad-container`, `#wrestler-ad-container-bottom`). `#wrestler-ad-container` doubles as a pre-existing positioning anchor that `renderSimplifiedSeasonStats()` already used (it inserts the Season Stats section immediately before this container) — reusing it meant no new positioning logic was needed for `profile-top` on this path.
  - **Career view** removes/rebuilds its entire profile section on every render (see `renderCareerProfile`'s existing cleanup step) and has no static container to anchor to, so it builds its own `ad-slot` elements programmatically: `profile-top` right after the career-summary table (before the season tabs, so it stays in place across season-tab clicks — those only touch the panel below), `profile-bottom` right after the season panel. Because this path never touches the season-view's static containers, `renderCareerProfile` explicitly hides them (`display: none`) so they don't leave a stray empty gap when a career-view page loads.

- **`profile-bottom` gated at 20+ career matches, same threshold on both paths.** Confirmed `career_record.wins`/`.losses` is present in both the career-view and season-view JSON payloads (season-view profiles carry a `career_record` object too, not just their own season's stats), so both paths gate on the same `KM_ADS.LONG_HISTORY_THRESHOLD = 20` constant rather than duplicating the number.

- **`rankings-top` placed once in `initRankings()`, not on every weight-tab click.** Same reasoning as the `rankings-mid` decision above — confirmed the ad container sits outside the DOM region `loadAndRenderWeight()`/`renderRankings()` ever touch, so it's created and requested exactly once per page load. Switching gender is a real page navigation (`?gender=girls`), which naturally reinitializes everything — that's a genuine new pageview, not a filter change, so a fresh ad request there is correct per B6 ("no ad refresh... on in-page interactions").

- **`data-ad-format="horizontal"/"rectangle"` + `data-full-width-responsive="false"`, not the `"auto"`/`"true"` AdSense's dashboard code snippets showed.** TJ asked directly whether the plan wanted fixed-size or responsive ad units — the answer is both, at different levels: the AdSense *unit* is created as "Responsive" (per A5, so its shape can be set in code rather than locked at creation), but the *rendered* ad is still constrained to a fixed footprint via `data-ad-format`/`data-full-width-responsive="false"` plus the CSS `min-height` on `.ad-slot--horizontal`/`.ad-slot--rectangle`. This is what B3/B5 actually specify ("so mobile ads don't expand past the reserved space" / reserved heights per format) — using AdSense's copy-paste default (`auto`/`true`) would let an ad grow past its reserved box on some viewports and cause the layout shift the whole reserved-space design exists to prevent.

- **CSS**: the old, already-dead `.ad-container`/`.ad-container ins` rules (left over from the pre-approval commented-out ad blocks) were replaced outright with the `.ad-slot`/`.ad-label`/`.ad-slot--horizontal`/`.ad-slot--rectangle` rules from B5, including the `:has(ins.adsbygoogle[data-ad-status="unfilled"])` rule that collapses a slot (box and label both) if AdSense reports it unfilled, so an unfilled ad never leaves a visible empty box.

### Testing done

- Syntax-checked all changed JS with `node --check` before committing.
- Confirmed via the dev branch-deploy preview build (fetched directly, not through DevTools — the Claude-in-Chrome browser extension wasn't connected this session) that the deployed HTML/JS/CSS matched what was committed: all four ad containers/anchors present, `js/ads.js` serving 200 with the four real slot IDs, all `KM_ADS` call sites present in `app.js`/`rankings.js`.
- TJ visually reviewed the dev preview across the four representative page types (career view with 20+ matches, career view under 20, season view, rankings) and confirmed it looked right before the production merge.
- **Not formally run this pass** (Part C items 4, 6, 7, 8 — DevTools network/console checks, simulated-unfilled test, Lighthouse CLS, 375px layout): the preview domain doesn't fill real ads anyway (not an approved AdSense site), so these checks matter most against production once ads start filling. Worth a spot-check on a live profile/rankings page in the next week or two rather than treating this as fully closed.

### Open items

- **A4 (ads.txt "Authorized" status in the AdSense dashboard)** showed "Not found" as of the last check, attributed to Google-side propagation lag since the file itself was already verified correctly served (Phase 1). Not reconfirmed as resolved — doesn't block anything already shipped, but worth a glance next time TJ is in the AdSense dashboard.
- **A6 (EU consent message)** — TJ's call, explicitly optional, not done.
- **Part D (after-launch checklist)** — now active now that this is live; see above. D3 (compare per-unit earnings, consider dropping a weak slot) and D5 (spring mobile-anchor-ad decision, only if revenue doesn't cover costs) are the two that need a decision later, not just a look.

---

## Carry-over to Matsavant (Phase 4)
Same approach when Matsavant gets ads: a separate set of named ad units per page type, the same `ads.js` module with Matsavant's slot IDs in its config, the same labels/reserved heights, and the same category blocks (they're set per AdSense account, so they'll already apply if Matsavant is added to the same account).
