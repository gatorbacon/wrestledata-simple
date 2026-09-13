// ========================================
// Site-wide Header Component
// ========================================

(function() {
  'use strict';

  const SEARCH_ICON_SVG = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>`;
  const MENU_ICON_SVG = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="3" y1="6" x2="21" y2="6"></line><line x1="3" y1="12" x2="21" y2="12"></line><line x1="3" y1="18" x2="21" y2="18"></line></svg>`;

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

    initSearch('mobile-search-input', 'mobile-search-dropdown');

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

  // Initialize search functionality with Fuse.js
  function initSearch(inputId, dropdownId) {
    const searchInput = document.getElementById(inputId);
    const searchDropdown = document.getElementById(dropdownId);
    
    if (!searchInput || !searchDropdown) return;
    
    // Check if Fuse.js and search index are available
    if (typeof Fuse === 'undefined') {
      console.warn('Fuse.js not loaded');
      return;
    }
    
    if (!window.SEARCH_INDEX || !Array.isArray(window.SEARCH_INDEX)) {
      console.warn('SEARCH_INDEX not available');
      return;
    }
    
    // Initialize Fuse.js
    const fuse = new Fuse(window.SEARCH_INDEX, {
      keys: [
        { name: 'name', weight: 0.6 },
        { name: 'searchTokens', weight: 0.4 }
      ],
      threshold: 0.4,
      ignoreLocation: true,
      minMatchCharLength: 2
    });
    
    let activeIndex = -1;
    let currentResults = [];
    
    // Render search results
    function renderResults(query) {
      if (query.length < 2) {
        searchDropdown.style.display = 'none';
        activeIndex = -1;
        return;
      }
      
      // Perform search
      const results = fuse.search(query);
      currentResults = results.slice(0, 10).map(r => r.item);
      
      if (currentResults.length === 0) {
        searchDropdown.innerHTML = `
          <div class="search-result-item search-result-empty">No results found</div>
        `;
        searchDropdown.style.display = 'block';
        activeIndex = -1;
        return;
      }
      
      // Group by type
      const wrestlers = currentResults.filter(r => r.type === 'wrestler');
      const teams = currentResults.filter(r => r.type === 'team');
      
      let html = '';
      
      if (wrestlers.length > 0) {
        html += '<div class="search-section">';
        html += '<div class="search-section-label">Wrestlers</div>';
        html += '<div class="search-results">';
        wrestlers.forEach((item, idx) => {
          const globalIdx = currentResults.indexOf(item);
          html += `
            <div class="search-result" data-url="${item.url}" data-index="${globalIdx}">
              <div class="search-name">${escapeHtml(item.name)}</div>
              <div class="search-secondary">${escapeHtml(item.secondary)}</div>
            </div>
          `;
        });
        html += '</div></div>';
      }
      
      if (teams.length > 0) {
        html += '<div class="search-section">';
        html += '<div class="search-section-label">Teams</div>';
        html += '<div class="search-results">';
        teams.forEach((item, idx) => {
          const globalIdx = currentResults.indexOf(item);
          html += `
            <div class="search-result" data-url="${item.url}" data-index="${globalIdx}">
              <div class="search-name">${escapeHtml(item.name)}</div>
              <div class="search-secondary">${escapeHtml(item.secondary)}</div>
            </div>
          `;
        });
        html += '</div></div>';
      }
      
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

