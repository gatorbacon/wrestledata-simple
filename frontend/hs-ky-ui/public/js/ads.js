/* ========================================
   KentuckyMat ad slots (AdSense)
   Plan: docs/kentuckymat_ads_phase3.md
   Guiding rule from that doc: KentuckyMat is a clean, community-trusted site,
   not a for-profit business. When a choice trades cleanliness for revenue,
   choose cleanliness. Concretely that means: ads only on wrestler profile and
   rankings pages, max 2 per page, no auto/anchor/sticky/vignette/interstitial/
   side-rail/in-text-link formats, never above the wrestler's name/record or
   inside/between ranked table rows, and every slot reserves its own space so
   the page never jumps.
   ======================================== */
(function () {
  "use strict";

  const PUBLISHER_ID = "ca-pub-6991551662268186";

  // Real slot IDs from TJ's AdSense dashboard (2026-09-23).
  const SLOTS = {
    "profile-top": { adSlotId: "6324158705", format: "horizontal" }, // KM-Profile-Top
    "profile-bottom": { adSlotId: "9776318559", format: "rectangle" }, // KM-Profile-Bottom
    "rankings-top": { adSlotId: "5314329368", format: "horizontal" }, // KM-Rankings-Top
    // KM-Rankings-Mid (1570525473) was built in the AdSense dashboard but is
    // deliberately not placed: rankings.html renders one weight class's table
    // at a time (weight-tab clicks re-render the same #rankings-table in
    // place, confirmed in rankings.js), so there's no second table region for
    // a "mid" slot to sit in without landing inside/between ranked rows,
    // which the plan explicitly forbids. Drop it per the plan's own fallback
    // rule rather than force a placement.
    "rankings-mid": { adSlotId: "1570525473", format: "rectangle" },
  };

  // Career profiles with fewer than this many total matches don't get the
  // profile-bottom ad — a short/new profile shouldn't feel ad-heavy relative
  // to its content (per the phase 3 plan).
  const LONG_HISTORY_THRESHOLD = 20;

  /**
   * Build a reserved ad-slot <div> (label only) ready to insert into the page.
   * Call placeAd() on it afterward to actually request the ad.
   */
  function createAdSlotElement(slotName) {
    const cfg = SLOTS[slotName];
    if (!cfg) {
      console.warn("[ads] unknown slot:", slotName);
      return null;
    }
    const wrap = document.createElement("div");
    wrap.className = `ad-slot ad-slot--${cfg.format}`;
    wrap.id = `ad-${slotName}`;
    const label = document.createElement("span");
    label.className = "ad-label";
    label.textContent = "Advertisement";
    wrap.appendChild(label);
    return wrap;
  }

  /**
   * Insert the <ins class="adsbygoogle"> into an existing container and
   * request the ad exactly once. Safe to call more than once on the same
   * container — later calls are a no-op (guards against AdSense's
   * "already have ads in them" console error from a double push).
   */
  function placeAd(containerEl, slotName) {
    if (!containerEl) return;
    if (containerEl.dataset.adPlaced === "true") return;
    const cfg = SLOTS[slotName];
    if (!cfg) {
      console.warn("[ads] unknown slot:", slotName);
      return;
    }

    const ins = document.createElement("ins");
    ins.className = "adsbygoogle";
    ins.style.display = "block";
    ins.setAttribute("data-ad-client", PUBLISHER_ID);
    ins.setAttribute("data-ad-slot", cfg.adSlotId);
    ins.setAttribute("data-ad-format", cfg.format);
    ins.setAttribute("data-full-width-responsive", "false");
    containerEl.appendChild(ins);
    containerEl.dataset.adPlaced = "true";

    try {
      (window.adsbygoogle = window.adsbygoogle || []).push({});
    } catch (e) {
      console.warn("[ads] adsbygoogle push failed:", e);
    }
  }

  window.KM_ADS = {
    PUBLISHER_ID,
    SLOTS,
    LONG_HISTORY_THRESHOLD,
    createAdSlotElement,
    placeAd,
  };
})();
