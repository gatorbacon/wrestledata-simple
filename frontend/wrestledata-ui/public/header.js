// ========================================
// Site-wide Header Component
// ========================================

(function() {
  'use strict';

  // Create header HTML structure
  function createHeaderHTML() {
    return `
      <nav class="site-header" id="site-header">
        <div class="header-container">
          <!-- Logo (Leftmost) -->
          <div class="header-logo">
            <a href="/" class="logo-link" title="WrestleData — Wrestling analytics inspired by DataGolf">
              <span class="logo-text">WrestleData</span>
            </a>
          </div>

          <!-- Primary Nav Items (Center-Left) -->
          <div class="header-nav">
            <!-- Rankings Dropdown -->
            <div class="nav-item nav-item--dropdown" id="nav-rankings">
              <button class="nav-link nav-link--dropdown" aria-expanded="false" aria-haspopup="true">
                Rankings <span class="dropdown-arrow">▾</span>
              </button>
              <div class="dropdown-menu dropdown-menu--multi-level" id="rankings-menu">
                <!-- Individual Submenu -->
                <div class="dropdown-submenu">
                  <button class="dropdown-submenu-trigger">
                    Individual <span class="submenu-arrow">▸</span>
                  </button>
                  <div class="dropdown-submenu-content">
                    <a href="/rankings.html" class="dropdown-item">
                      <span class="dropdown-item-label">Rankings (Traditional)</span>
                    </a>
                    <a href="/matrix.html" class="dropdown-item">
                      <span class="dropdown-item-label">Rankings Matrix</span>
                    </a>
                    <a href="/leaderboards/mat_value.html" class="dropdown-item">
                      <span class="dropdown-item-label">TPAR</span>
                      <span class="dropdown-item-subtext">Team Points Above Replacement</span>
                    </a>
                  </div>
                </div>
                <!-- Team Submenu -->
                <div class="dropdown-submenu">
                  <button class="dropdown-submenu-trigger">
                    Team <span class="submenu-arrow">▸</span>
                  </button>
                  <div class="dropdown-submenu-content">
                    <a href="/leaderboards/xtp/teams.html" class="dropdown-item">
                      <span class="dropdown-item-label">Expected Team Points (xTP)</span>
                      <span class="dropdown-item-subtext">Projected NCAA tournament scoring</span>
                    </a>
                  </div>
                </div>
              </div>
            </div>

            <!-- Profiles Dropdown -->
            <div class="nav-item nav-item--dropdown" id="nav-profiles">
              <button class="nav-link nav-link--dropdown" aria-expanded="false" aria-haspopup="true">
                Profiles <span class="dropdown-arrow">▾</span>
              </button>
              <div class="dropdown-menu" id="profiles-menu">
                <a href="/leaderboards/mat_value.html" class="dropdown-item">
                  <span class="dropdown-item-label">Wrestlers</span>
                </a>
                <a href="/leaderboards/xtp/teams.html" class="dropdown-item">
                  <span class="dropdown-item-label">Teams</span>
                </a>
              </div>
            </div>

            <!-- Tournaments (Disabled/Placeholder) -->
            <div class="nav-item nav-item--disabled">
              <span class="nav-link nav-link--disabled">Tournaments</span>
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
          </div>
        </div>
      </nav>
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
      
      // Initialize search
      initSearch();
    }
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
  function initSearch() {
    const searchInput = document.getElementById('header-search-input');
    const searchDropdown = document.getElementById('search-dropdown');
    
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

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initHeader);
  } else {
    initHeader();
  }
})();

