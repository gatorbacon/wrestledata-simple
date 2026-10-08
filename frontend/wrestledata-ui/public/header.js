// ========================================
// Site-wide Header Component
// ========================================

// ---------- Links to wrestler and team pages (docs/matsavant_seo_plan.md) ----------
// Defined here because every page loads header.js first. urlPath is the
// ready-made name address that scripts/seo/build_url_slugs.py writes into the
// data ("url_path" / "opponent_url_path": /wrestler/levi-haines, plus
// ?season=2024 when that id isn't the wrestler's latest season). Without it,
// the old ?id= form, which the edge function 301s to the same page.
// params: {view} ("season" / "career").
function wrestlerHref(urlPath, id, params) {
  const view = params && params.view;
  if (urlPath) {
    if (!view) return urlPath;
    return urlPath + (urlPath.includes("?") ? "&" : "?") + "view=" + encodeURIComponent(view);
  }
  return `/wrestler.html?id=${encodeURIComponent(id)}` + (view ? `&view=${encodeURIComponent(view)}` : "");
}

// team id (penn_state) -> /team/penn-state. Old ids (army, north_carolina_state)
// go straight to today's team when seo_text.js is loaded; otherwise the edge
// function 301s them.
function teamHref(teamId) {
  const id = String(teamId || "").toLowerCase();
  const seo = window.MatSavantSEO;
  if (seo) return seo.teamPath(id);
  return `/team/${id.replace(/_/g, "-")}`;
}

(function() {
  'use strict';

  const SEARCH_ICON_SVG = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>`;
  const MENU_ICON_SVG = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="3" y1="6" x2="21" y2="6"></line><line x1="3" y1="12" x2="21" y2="12"></line><line x1="3" y1="18" x2="21" y2="18"></line></svg>`;

  // ---------- Shared search ranking ----------
  // Used by the header search below and exported as window.MatSavantSearch so
  // other wrestler pickers (wrestlers.html directory search, tools/compare.js)
  // rank results the same way instead of keeping their own copies.
  const fuseOptions = {
    keys: [
      { name: 'name', weight: 0.6 },
      { name: 'searchTokens', weight: 0.4 }
    ],
    threshold: 0.4,
    ignoreLocation: true,
    minMatchCharLength: 2,
    includeScore: true,
  };

  // Fuse's own fuzzy score alone doesn't reliably rank an exact/prefix
  // match above a merely-fuzzy one (e.g. "penn s" scored some unrelated
  // wrestlers as good as or better than "Penn State"). This computes a
  // coarse match-quality tier up front so real prefix matches always win,
  // then breaks ties using each item's `priority` (national champion > AA
  // > active this season > everyone else -- see generate_search_index.py)
  // and finally `rank` / Fuse's score.
  function tokenMatchTier(query, name) {
    const q = query.toLowerCase().trim();
    const nameLower = name.toLowerCase();
    if (nameLower === q) return 0;
    if (nameLower.startsWith(q)) return 1;
    // Every query word is a prefix of some distinct word in the name, in
    // any order/position -- catches "mitch mes" -> "Mitchell Mesenbrink"
    // and "penn s" -> "Penn State" even though neither is a literal
    // whole-string prefix.
    const qWords = q.split(/\s+/).filter(Boolean);
    const nameWords = nameLower.split(/\s+/).filter(Boolean);
    const used = new Array(nameWords.length).fill(false);
    const allMatched = qWords.length > 0 && qWords.every(qw => {
      const i = nameWords.findIndex((nw, idx) => !used[idx] && nw.startsWith(qw));
      if (i === -1) return false;
      used[i] = true;
      return true;
    });
    return allMatched ? 2 : 3;
  }

  // Fuse's `threshold` option doesn't bound the combined score it hands
  // back when multiple weighted keys are in play (name + searchTokens
  // here) -- e.g. "Penn state" returns "Carter Tate" et al at score ~0.68,
  // nowhere near the 0.4 threshold that was supposed to gate this. Since
  // tiers 0-2 are already validated by our own prefix/token logic above
  // (trustworthy regardless of Fuse's score), this quality floor only
  // needs to apply to tier 3 (pure fuzzy, no prefix signal at all) --
  // genuine typo matches like "mesenrbink" -> Mesenbrink score ~0.27, well
  // under this, so real fuzzy tolerance is untouched.
  const FUZZY_SCORE_FLOOR = 0.5;

  function rankResults(query, fuseResults) {
    return fuseResults
      .map(r => ({
        item: r.item,
        tier: tokenMatchTier(query, r.item.name),
        priority: r.item.priority ?? 0,
        rank: r.item.rank ?? Infinity,
        score: r.score ?? 1,
      }))
      .filter(r => r.tier < 3 || r.score < FUZZY_SCORE_FLOOR)
      .sort((a, b) => (
        a.tier - b.tier ||
        a.priority - b.priority ||
        a.rank - b.rank ||
        a.score - b.score
      ));
  }

  window.MatSavantSearch = { fuseOptions, tokenMatchTier, rankResults };

  // ---------- Search data, loaded in the background ----------
  // Fuse.js and search_index.js (~4.4 MB, ~320 KB compressed) used to be
  // <script> tags in every page's <head>, which held up the whole page on
  // phones (2026-10-02 Lighthouse on KentuckyMat's identical setup, slow 4G:
  // ~5.5 s of an 8-11 s first paint). They now load after the page has
  // finished loading, so the page shows up first and autocomplete is still
  // ready by the time most people search. Pages that use the index for their
  // own content (wrestlers.html, teams.html, tools/compare.html,
  // schedule.html) still load it up front, and loadSearchData() then finds it
  // already there.
  const FUSE_SRC = 'https://cdn.jsdelivr.net/npm/fuse.js@6.6.2';
  const SEARCH_INDEX_SRC = '/search_index.js?v=20260913';
  let searchDataPromise = null;

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = src;
      script.async = true;
      script.onload = resolve;
      script.onerror = () => {
        script.remove();
        reject(new Error('Failed to load ' + src));
      };
      document.head.appendChild(script);
    });
  }

  function loadSearchData() {
    if (!searchDataPromise) {
      searchDataPromise = Promise.all([
        typeof Fuse === 'undefined' ? loadScript(FUSE_SRC) : null,
        Array.isArray(window.SEARCH_INDEX) ? null : loadScript(SEARCH_INDEX_SRC)
      ]).catch((err) => {
        searchDataPromise = null; // let the next hover/tap retry
        throw err;
      });
    }
    return searchDataPromise;
  }

  // Calls fn once the page has finished loading and the browser is idle.
  function afterPageLoad(fn) {
    const whenIdle = () => ('requestIdleCallback' in window)
      ? requestIdleCallback(() => fn(), { timeout: 2000 })
      : setTimeout(fn, 200);
    if (document.readyState === 'complete') whenIdle();
    else window.addEventListener('load', whenIdle, { once: true });
  }

  // Runs `setup` (builds the Fuse instances, attaches the real handlers) once
  // the search data has loaded. Loading starts in the background after the
  // page has loaded, or sooner on the first hover, touch or focus of any
  // element in `triggers`; anything typed before it arrives shows
  // "Loading search…" and is searched as soon as the data is there.
  function initBackgroundSearch(searchInput, searchDropdown, triggers, setup) {
    let ready = false;
    let showingMessage = false;

    function showMessage(text) {
      searchDropdown.innerHTML = `<div class="search-result-item search-result-empty">${text}</div>`;
      searchDropdown.style.display = 'block';
      showingMessage = true;
    }

    function start() {
      loadSearchData().then(() => {
        if (ready) return;
        ready = true;
        setup();
        if (document.activeElement === searchInput && searchInput.value.trim().length >= 2) {
          searchInput.dispatchEvent(new Event('input'));
        } else if (showingMessage) {
          searchDropdown.style.display = 'none';
        }
      }).catch((err) => {
        console.warn('Search unavailable:', err.message);
        if (searchInput.value.trim().length >= 2) showMessage('Search is unavailable right now');
      });
    }

    triggers.forEach((el) => {
      ['pointerenter', 'touchstart', 'focus'].forEach((type) => {
        el.addEventListener(type, start, { passive: true });
      });
    });
    afterPageLoad(start);

    searchInput.addEventListener('input', () => {
      if (ready) return;
      if (searchInput.value.trim().length >= 2) {
        showMessage('Loading search…');
      } else {
        searchDropdown.style.display = 'none';
      }
      start();
    });
  }

  // Create header HTML structure
  function createHeaderHTML() {
    return `
      <nav class="site-header" id="site-header">
        <div class="header-container">
          <!-- Logo (Leftmost) -->
          <div class="header-logo">
            <a href="/" class="logo-link" title="MatSavant — Wrestling analytics inspired by DataGolf">
              <span class="logo-text">MatSavant</span>
            </a>
          </div>

          <!-- Primary Nav Items (Center-Left) -->
          <div class="header-nav">
            <!-- Rankings Dropdown -->
            <div class="nav-item nav-item--dropdown" id="nav-rankings">
              <button class="nav-link nav-link--dropdown" aria-expanded="false" aria-haspopup="true">
                Rankings <span class="dropdown-arrow">▾</span>
              </button>
              <div class="dropdown-menu" id="rankings-menu">
                <div class="dropdown-group-label">Wrestlers</div>
                <a href="/rankings.html" class="dropdown-item">
                  <span class="dropdown-item-label">By Weight</span>
                  <span class="dropdown-item-subtext">Top 33 by weight + P4P</span>
                </a>
                <a href="/matrix.html" class="dropdown-item">
                  <span class="dropdown-item-label">Matrix</span>
                  <span class="dropdown-item-subtext">Visual Map of Ranks</span>
                </a>
                <div class="dropdown-group-label">Races</div>
                <a href="/leaderboards/xtp/teams.html" class="dropdown-item">
                  <span class="dropdown-item-label">Team race</span>
                  <span class="dropdown-item-subtext">NCAA title / xTP</span>
                </a>
                <a href="/hodge.html" class="dropdown-item">
                  <span class="dropdown-item-label">Hodge</span>
                  <span class="dropdown-item-subtext">View Hodge Data</span>
                </a>
              </div>
            </div>

            <!-- Wrestlers / Teams: direct links, not a dropdown -->
            <a href="/wrestlers.html" class="nav-item nav-link">Wrestlers</a>
            <a href="/teams.html" class="nav-item nav-link">Teams</a>

            <!-- Events Dropdown -->
            <div class="nav-item nav-item--dropdown" id="nav-events">
              <button class="nav-link nav-link--dropdown" aria-expanded="false" aria-haspopup="true">
                Events <span class="dropdown-arrow">▾</span>
              </button>
              <div class="dropdown-menu" id="events-menu">
                <a href="/events/ncaa.html" class="dropdown-item">
                  <span class="dropdown-item-label">NCAA</span>
                </a>
                <span class="dropdown-item dropdown-item--disabled" aria-disabled="true">
                  <span class="dropdown-item-label">Big Ten</span>
                  <span class="dropdown-item-subtext">Coming soon</span>
                </span>
                <span class="dropdown-item dropdown-item--disabled" aria-disabled="true">
                  <span class="dropdown-item-label">Big 12</span>
                  <span class="dropdown-item-subtext">Coming soon</span>
                </span>
                <span class="dropdown-item dropdown-item--disabled" aria-disabled="true">
                  <span class="dropdown-item-label">National Duals</span>
                  <span class="dropdown-item-subtext">Coming soon</span>
                </span>
              </div>
            </div>

            <!-- Field Notes Dropdown -->
            <div class="nav-item nav-item--dropdown" id="nav-notes">
              <button class="nav-link nav-link--dropdown" aria-expanded="false" aria-haspopup="true">
                Field Notes <span class="dropdown-arrow">▾</span>
              </button>
              <div class="dropdown-menu" id="notes-menu">
                <a href="/notes/index.html" class="dropdown-item">
                  <span class="dropdown-item-label">Field Notes</span>
                  <span class="dropdown-item-subtext">Threads and write-ups</span>
                </a>
                <a href="/tools/index.html" class="dropdown-item">
                  <span class="dropdown-item-label">Tools</span>
                  <span class="dropdown-item-subtext">Sims and generators</span>
                </a>
                <a href="/lab/index.html" class="dropdown-item">
                  <span class="dropdown-item-label">Lab</span>
                  <span class="dropdown-item-subtext">Experiments</span>
                </a>
              </div>
            </div>
          </div>

          <!-- Search (Center-Right) -->
          <div class="header-search">
            <div class="search-container">
              <input 
                type="text" 
                class="search-input" 
                id="header-search-input"
                placeholder="Search wrestlers, teams…"
                autocomplete="off"
                aria-label="Search wrestlers or teams"
              />
              <div class="search-dropdown" id="search-dropdown" style="display: none;"></div>
            </div>
          </div>

          <!-- Right Side Items -->
          <div class="header-right">
            <a href="/about.html" class="header-link">About</a>
            <div class="header-mobile-actions">
              <button type="button" class="header-icon-btn" id="mobile-search-toggle" aria-label="Search" aria-expanded="false">
                ${SEARCH_ICON_SVG}
              </button>
              <button type="button" class="header-icon-btn" id="mobile-menu-toggle" aria-label="Menu" aria-expanded="false" aria-controls="mobile-drawer">
                ${MENU_ICON_SVG}
              </button>
            </div>
          </div>
        </div>

        <!-- Mobile search bar: expands full-width under the header row -->
        <div class="mobile-search-bar" id="mobile-search-bar" hidden>
          <div class="search-container">
            <input
              type="text"
              class="search-input"
              id="mobile-search-input"
              placeholder="Search wrestlers, teams…"
              autocomplete="off"
              aria-label="Search wrestlers or teams"
            />
            <div class="search-dropdown" id="mobile-search-dropdown" style="display: none;"></div>
          </div>
        </div>
      </nav>

      <!-- Mobile nav drawer: same links as the desktop dropdowns above, just
           moved into a slide-in panel instead of hover menus. -->
      <div class="mobile-drawer-overlay" id="mobile-drawer-overlay" hidden></div>
      <div class="mobile-drawer" id="mobile-drawer" hidden aria-hidden="true">
        <div class="mobile-drawer-header">
          <span class="mobile-drawer-title">Menu</span>
          <button type="button" class="mobile-drawer-close" id="mobile-drawer-close" aria-label="Close menu">&times;</button>
        </div>
        <nav class="mobile-drawer-nav">
          <div class="mobile-drawer-section">
            <div class="mobile-drawer-section-label">Rankings</div>
            <a href="/rankings.html" class="mobile-drawer-link">By Weight</a>
            <a href="/leaderboards/xtp/teams.html" class="mobile-drawer-link">Team race</a>
            <a href="/hodge.html" class="mobile-drawer-link">Hodge</a>
          </div>
          <div class="mobile-drawer-section">
            <a href="/wrestlers.html" class="mobile-drawer-link">Wrestlers</a>
            <a href="/teams.html" class="mobile-drawer-link">Teams</a>
          </div>
          <div class="mobile-drawer-section">
            <div class="mobile-drawer-section-label">Events</div>
            <a href="/events/ncaa.html" class="mobile-drawer-link">NCAA</a>
            <span class="mobile-drawer-link mobile-drawer-link--disabled" aria-disabled="true">Big Ten <em>— coming soon</em></span>
            <span class="mobile-drawer-link mobile-drawer-link--disabled" aria-disabled="true">Big 12 <em>— coming soon</em></span>
            <span class="mobile-drawer-link mobile-drawer-link--disabled" aria-disabled="true">National Duals <em>— coming soon</em></span>
          </div>
          <div class="mobile-drawer-section">
            <div class="mobile-drawer-section-label">Field Notes</div>
            <a href="/notes/index.html" class="mobile-drawer-link">Field Notes</a>
            <a href="/tools/index.html" class="mobile-drawer-link">Tools</a>
            <a href="/lab/index.html" class="mobile-drawer-link">Lab</a>
          </div>
          <div class="mobile-drawer-section mobile-drawer-section--last">
            <a href="/about.html" class="mobile-drawer-link">About</a>
          </div>
        </nav>
      </div>
    `;
  }

  // Initialize header
  function initHeader() {
    // Insert header at the beginning of body
    const body = document.body;
    if (body && !document.getElementById('site-header')) {
      body.insertAdjacentHTML('afterbegin', createHeaderHTML());

      // Initialize dropdowns
      initDropdowns();

      // Initialize search (desktop input)
      initSearch('header-search-input', 'search-dropdown');

      // Mobile-only: search toggle, hamburger drawer
      initMobileSearch();
      initMobileDrawer();
    }
  }

  // Mobile search icon: toggles the full-width search bar under the header
  function initMobileSearch() {
    const toggle = document.getElementById('mobile-search-toggle');
    const bar = document.getElementById('mobile-search-bar');
    const input = document.getElementById('mobile-search-input');
    if (!toggle || !bar || !input) return;

    initSearch('mobile-search-input', 'mobile-search-dropdown', [toggle]);

    toggle.addEventListener('click', () => {
      const isOpen = !bar.hidden;
      bar.hidden = isOpen;
      toggle.setAttribute('aria-expanded', String(!isOpen));
      if (!isOpen) {
        input.focus();
      } else {
        input.value = '';
        document.getElementById('mobile-search-dropdown').style.display = 'none';
      }
    });
  }

  // Mobile hamburger: slides in the nav drawer, traps focus, closes on
  // overlay click / close button / Escape.
  function initMobileDrawer() {
    const menuToggle = document.getElementById('mobile-menu-toggle');
    const drawer = document.getElementById('mobile-drawer');
    const overlay = document.getElementById('mobile-drawer-overlay');
    const closeBtn = document.getElementById('mobile-drawer-close');
    if (!menuToggle || !drawer || !overlay || !closeBtn) return;

    function focusableEls() {
      return Array.from(drawer.querySelectorAll('a[href], button:not([disabled])'));
    }

    function trapFocus(e) {
      if (e.key !== 'Tab') return;
      const els = focusableEls();
      if (els.length === 0) return;
      const first = els[0];
      const last = els[els.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }

    function openDrawer() {
      drawer.hidden = false;
      overlay.hidden = false;
      drawer.setAttribute('aria-hidden', 'false');
      menuToggle.setAttribute('aria-expanded', 'true');
      document.body.style.overflow = 'hidden';
      document.addEventListener('keydown', onKeydown);
      const els = focusableEls();
      if (els.length) els[0].focus();
    }

    function closeDrawer() {
      drawer.hidden = true;
      overlay.hidden = true;
      drawer.setAttribute('aria-hidden', 'true');
      menuToggle.setAttribute('aria-expanded', 'false');
      document.body.style.overflow = '';
      document.removeEventListener('keydown', onKeydown);
      menuToggle.focus();
    }

    function onKeydown(e) {
      if (e.key === 'Escape') {
        closeDrawer();
      } else {
        trapFocus(e);
      }
    }

    menuToggle.addEventListener('click', openDrawer);
    closeBtn.addEventListener('click', closeDrawer);
    overlay.addEventListener('click', closeDrawer);
  }

  // Initialize dropdown menus
  function initDropdowns() {
    const dropdownTriggers = document.querySelectorAll('.nav-link--dropdown');
    
    dropdownTriggers.forEach(trigger => {
      const navItem = trigger.closest('.nav-item--dropdown');
      const menu = navItem.querySelector('.dropdown-menu');
      const submenuTriggers = navItem.querySelectorAll('.dropdown-submenu-trigger');
      
      // Toggle main dropdown
      trigger.addEventListener('click', (e) => {
        e.stopPropagation();
        const isOpen = trigger.getAttribute('aria-expanded') === 'true';
        
        // Close all other dropdowns
        document.querySelectorAll('.nav-link--dropdown').forEach(other => {
          if (other !== trigger) {
            other.setAttribute('aria-expanded', 'false');
            other.closest('.nav-item--dropdown').classList.remove('is-open');
          }
        });
        
        // Toggle this dropdown
        trigger.setAttribute('aria-expanded', !isOpen);
        navItem.classList.toggle('is-open', !isOpen);
      });
      
      // Handle submenu triggers
      submenuTriggers.forEach(subTrigger => {
        subTrigger.addEventListener('click', (e) => {
          e.stopPropagation();
          const submenu = subTrigger.closest('.dropdown-submenu');
          submenu.classList.toggle('is-open');
        });
      });
    });
    
    // Close dropdowns when clicking outside
    document.addEventListener('click', (e) => {
      if (!e.target.closest('.nav-item--dropdown')) {
        document.querySelectorAll('.nav-link--dropdown').forEach(trigger => {
          trigger.setAttribute('aria-expanded', 'false');
          trigger.closest('.nav-item--dropdown').classList.remove('is-open');
        });
        document.querySelectorAll('.dropdown-submenu').forEach(submenu => {
          submenu.classList.remove('is-open');
        });
      }
    });
  }

  // Initialize search functionality with Fuse.js (once the data loads).
  // `extraTriggers`: other elements whose hover/tap should start the load
  // early, e.g. the mobile search toggle.
  function initSearch(inputId, dropdownId, extraTriggers = []) {
    const searchInput = document.getElementById(inputId);
    const searchDropdown = document.getElementById(dropdownId);

    if (!searchInput || !searchDropdown) return;

    initBackgroundSearch(searchInput, searchDropdown, [searchInput, ...extraTriggers],
      () => setupSearch(searchInput, searchDropdown));
  }

  function setupSearch(searchInput, searchDropdown) {
    // Two separate Fuse instances (wrestlers, teams) rather than one over the
    // whole index -- searching everything together and taking a single top-10
    // slice let a pile of loosely-matched wrestlers crowd out an exact team
    // match (e.g. "Penn State" wouldn't surface at all for "penn s"), since
    // there are ~30x more wrestler entries than team entries competing for
    // the same 10 slots. Each type now gets its own guaranteed slots.
    const fuseWrestlers = new Fuse(window.SEARCH_INDEX.filter(i => i.type === 'wrestler'), fuseOptions);
    const fuseTeams = new Fuse(window.SEARCH_INDEX.filter(i => i.type === 'team'), fuseOptions);

    let activeIndex = -1;
    let currentResults = [];

    // Render search results
    function renderResults(query) {
      if (query.length < 2) {
        searchDropdown.style.display = 'none';
        activeIndex = -1;
        return;
      }

      // Perform search -- 6 wrestler slots + 4 team slots, each ranked (and
      // capped) independently so neither type can crowd out the other.
      const wrestlerMatches = rankResults(query, fuseWrestlers.search(query)).slice(0, 6);
      const teamMatches = rankResults(query, fuseTeams.search(query)).slice(0, 4);
      const wrestlers = wrestlerMatches.map(r => r.item);
      const teams = teamMatches.map(r => r.item);
      currentResults = [...wrestlers, ...teams];

      if (currentResults.length === 0) {
        searchDropdown.innerHTML = `
          <div class="search-result-item search-result-empty">No results found</div>
        `;
        searchDropdown.style.display = 'block';
        activeIndex = -1;
        return;
      }

      function sectionHtml(label, items) {
        if (items.length === 0) return '';
        let html = '<div class="search-section">';
        html += `<div class="search-section-label">${label}</div>`;
        html += '<div class="search-results">';
        items.forEach(item => {
          const globalIdx = currentResults.indexOf(item);
          html += `
            <div class="search-result" data-url="${item.url}" data-index="${globalIdx}">
              <div class="search-name">${escapeHtml(item.name)}</div>
              <div class="search-secondary">${escapeHtml(item.secondary)}</div>
            </div>
          `;
        });
        html += '</div></div>';
        return html;
      }

      // An exact/near-exact team match (e.g. "Penn State") should lead the
      // whole dropdown, not just win within its own section -- otherwise a
      // pile of merely-decent wrestler matches still visually outrank the
      // one thing the query was clearly asking for. Sections are ordered by
      // whichever type's best result has the better (lower) match tier;
      // Wrestlers keeps its usual first position on a tie or when empty.
      const bestWrestlerTier = wrestlerMatches.length ? wrestlerMatches[0].tier : Infinity;
      const bestTeamTier = teamMatches.length ? teamMatches[0].tier : Infinity;
      const teamsFirst = bestTeamTier < bestWrestlerTier;

      const html = teamsFirst
        ? sectionHtml('Teams', teams) + sectionHtml('Wrestlers', wrestlers)
        : sectionHtml('Wrestlers', wrestlers) + sectionHtml('Teams', teams);

      searchDropdown.innerHTML = html;
      searchDropdown.style.display = 'block';
      activeIndex = -1;
      
      // Attach click handlers
      searchDropdown.querySelectorAll('.search-result').forEach(result => {
        result.addEventListener('click', () => {
          const url = result.getAttribute('data-url');
          if (url) {
            window.location.href = url;
          }
        });
      });
    }
    
    // Escape HTML to prevent XSS
    function escapeHtml(text) {
      const div = document.createElement('div');
      div.textContent = text;
      return div.innerHTML;
    }
    
    // Navigate to active result
    function navigateToActive() {
      if (activeIndex >= 0 && activeIndex < currentResults.length) {
        const url = currentResults[activeIndex].url;
        if (url) {
          window.location.href = url;
        }
      }
    }
    
    // Update active selection
    function updateActiveSelection() {
      const results = searchDropdown.querySelectorAll('.search-result');
      results.forEach((r, idx) => {
        if (idx === activeIndex) {
          r.classList.add('is-active');
        } else {
          r.classList.remove('is-active');
        }
      });
    }
    
    // Handle input
    searchInput.addEventListener('input', (e) => {
      const query = e.target.value.trim();
      renderResults(query);
    });
    
    // Handle focus
    searchInput.addEventListener('focus', () => {
      const query = searchInput.value.trim();
      if (query.length >= 2) {
        renderResults(query);
      }
    });
    
    // Handle keyboard navigation
    searchInput.addEventListener('keydown', (e) => {
      const results = searchDropdown.querySelectorAll('.search-result');
      
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (activeIndex < results.length - 1) {
          activeIndex++;
          updateActiveSelection();
        }
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (activeIndex > 0) {
          activeIndex--;
          updateActiveSelection();
        } else {
          activeIndex = -1;
          updateActiveSelection();
        }
      } else if (e.key === 'Enter') {
        e.preventDefault();
        navigateToActive();
      } else if (e.key === 'Escape') {
        searchDropdown.style.display = 'none';
        activeIndex = -1;
        searchInput.blur();
      }
    });
    
    // Hide dropdown when clicking outside
    document.addEventListener('click', (e) => {
      if (!e.target.closest('.search-container')) {
        searchDropdown.style.display = 'none';
        activeIndex = -1;
      }
    });
  }

  // Exposed so page-specific search inputs outside the header itself (e.g.
  // the mobile app-home search card, see mobile_app_home.js) can reuse the
  // exact same Fuse.js wiring instead of duplicating it.
  window.initHeaderSearch = initSearch;

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initHeader);
  } else {
    initHeader();
  }

  // ========================================
  // GA4 pageview firing (see analytics.js -- send_page_view is off there)
  // ========================================
  // Every page here has a static <title> except notes/note.html, which
  // sets its title from a fetch; that page calls window.sendPageView()
  // itself once the title is final instead of being auto-fired below.
  function sendPageView() {
    if (typeof gtag === 'function') {
      gtag('event', 'page_view', {
        page_title: document.title,
        page_location: window.location.href,
      });
    }
  }
  window.sendPageView = sendPageView;

  const _dynamicTitlePages = ['/notes/note.html'];
  const _isStaticTitlePage = !_dynamicTitlePages.some(p => window.location.pathname.endsWith(p));
  if (_isStaticTitlePage) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', sendPageView);
    } else {
      sendPageView();
    }
  }
})();

