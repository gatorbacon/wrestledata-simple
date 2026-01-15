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
            <a href="/" class="logo-link" title="Kentucky High School Wrestling Rankings">
              <span class="logo-text">kentuckymat</span>
            </a>
          </div>

          <!-- Primary Nav Items (Center-Left) -->
          <div class="header-nav">
            <!-- Boys Dropdown -->
            <div class="nav-item nav-item--dropdown" id="nav-boys">
              <button class="nav-link nav-link--dropdown" aria-expanded="false" aria-haspopup="true">
                Boys Rankings <span class="dropdown-arrow">▾</span>
              </button>
              <div class="dropdown-menu" id="boys-menu">
                <a href="/rankings.html?gender=boys" class="dropdown-item">
                  <span class="dropdown-item-label">Individual Rankings</span>
                </a>
                <a href="/leaderboards/xtp/teams.html?gender=boys" class="dropdown-item">
                  <span class="dropdown-item-label">Team Tournament</span>
                </a>
              </div>
            </div>

            <!-- Girls Dropdown -->
            <div class="nav-item nav-item--dropdown" id="nav-girls">
              <button class="nav-link nav-link--dropdown" aria-expanded="false" aria-haspopup="true">
                Girls Rankings <span class="dropdown-arrow">▾</span>
              </button>
              <div class="dropdown-menu" id="girls-menu">
                <a href="/rankings.html?gender=girls" class="dropdown-item">
                  <span class="dropdown-item-label">Individual Rankings</span>
                </a>
                <a href="/leaderboards/xtp/teams.html?gender=girls" class="dropdown-item">
                  <span class="dropdown-item-label">Team Tournament</span>
                </a>
              </div>
            </div>

            <!-- Dual Predictor -->
            <div class="nav-item">
              <a href="/dual_predictor.html" class="nav-link">Dual Predictor</a>
            </div>

            <!-- Stat Leaders -->
            <div class="nav-item">
              <a href="/leaderboards.html" class="nav-link">Stat Leaders</a>
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
            <!-- No About link for HS site -->
          </div>

          <!-- Mobile Icons (hidden on desktop) -->
          <div class="header-mobile-icons">
            <button class="mobile-icon-btn mobile-search-btn" id="mobile-search-btn" aria-label="Search">
              <span class="mobile-icon">🔍</span>
            </button>
            <button class="mobile-icon-btn mobile-menu-btn" id="mobile-menu-btn" aria-label="Menu">
              <span class="mobile-icon">☰</span>
            </button>
          </div>
        </div>
      </nav>

      <!-- Mobile Search Overlay -->
      <div class="mobile-search-overlay" id="mobile-search-overlay" style="display: none;">
        <div class="mobile-search-content">
          <div class="mobile-search-header">
            <input 
              type="text" 
              class="mobile-search-input" 
              id="mobile-search-input"
              placeholder="Search wrestlers, teams…"
              autocomplete="off"
              aria-label="Search wrestlers or teams"
            />
            <button class="mobile-search-close" id="mobile-search-close" aria-label="Close search">✕</button>
          </div>
          <div class="mobile-search-dropdown" id="mobile-search-dropdown" style="display: none;"></div>
        </div>
      </div>

      <!-- Mobile Menu Overlay -->
      <div class="mobile-menu-overlay" id="mobile-menu-overlay" style="display: none;">
        <div class="mobile-menu-content">
          <div class="mobile-menu-header">
            <span class="mobile-menu-title">Menu</span>
            <button class="mobile-menu-close" id="mobile-menu-close" aria-label="Close menu">✕</button>
          </div>
          <nav class="mobile-menu-nav">
            <!-- Boys Section (Expandable) -->
            <div class="mobile-menu-section">
              <button class="mobile-menu-section-header" aria-expanded="false" data-section="boys">
                <span>Boys Rankings</span>
                <span class="mobile-menu-chevron">▸</span>
              </button>
              <div class="mobile-menu-section-content" data-content="boys">
                <a href="/rankings.html?gender=boys" class="mobile-menu-item mobile-menu-item--child">Individual Rankings</a>
                <a href="/leaderboards/xtp/teams.html?gender=boys" class="mobile-menu-item mobile-menu-item--child">Team Tournament</a>
              </div>
            </div>

            <!-- Girls Section (Expandable) -->
            <div class="mobile-menu-section">
              <button class="mobile-menu-section-header" aria-expanded="false" data-section="girls">
                <span>Girls Rankings</span>
                <span class="mobile-menu-chevron">▸</span>
              </button>
              <div class="mobile-menu-section-content" data-content="girls">
                <a href="/rankings.html?gender=girls" class="mobile-menu-item mobile-menu-item--child">Individual Rankings</a>
                <a href="/leaderboards/xtp/teams.html?gender=girls" class="mobile-menu-item mobile-menu-item--child">Team Tournament</a>
              </div>
            </div>

            <!-- Dual Predictor (Non-expandable link) -->
            <a href="/dual_predictor.html" class="mobile-menu-item">Dual Predictor</a>

            <!-- Stat Leaders (Non-expandable link) -->
            <a href="/leaderboards.html" class="mobile-menu-item">Stat Leaders</a>
          </nav>
        </div>
      </div>
    `;
  }

  // Initialize header
  function initHeader() {
    // Insert header at the beginning of body
    const body = document.body;
    if (body && !document.getElementById('site-header')) {
      body.insertAdjacentHTML('afterbegin', createHeaderHTML());
      
      // Check if we're on a girls page and apply pink background
      applyGenderStyling();
      
      // Initialize dropdowns
      initDropdowns();
      
      // Initialize search
      initSearch();
      
      // Initialize mobile menu
      initMobileMenu();
      
      // Initialize mobile search
      initMobileSearch();
    }
  }

  // Apply gender-specific styling to header
  function applyGenderStyling() {
    const header = document.getElementById('site-header');
    if (!header) return;
    
    // Check URL parameters for gender=girls
    const urlParams = new URLSearchParams(window.location.search);
    const gender = urlParams.get('gender');
    
    if (gender === 'girls') {
      header.classList.add('header--girls');
    }
  }

  // Initialize mobile menu
  function initMobileMenu() {
    const menuBtn = document.getElementById('mobile-menu-btn');
    const menuOverlay = document.getElementById('mobile-menu-overlay');
    const menuClose = document.getElementById('mobile-menu-close');
    
    if (!menuBtn || !menuOverlay || !menuClose) return;
    
    function openMenu() {
      menuOverlay.style.display = 'block';
      document.body.style.overflow = 'hidden';
      // Close all expanded sections when opening menu
      closeAllSections();
    }
    
    function closeMenu() {
      menuOverlay.style.display = 'none';
      document.body.style.overflow = '';
      // Close all expanded sections when closing menu
      closeAllSections();
    }
    
    function closeAllSections() {
      const sectionHeaders = menuOverlay.querySelectorAll('.mobile-menu-section-header');
      sectionHeaders.forEach(header => {
        header.setAttribute('aria-expanded', 'false');
        const section = header.getAttribute('data-section');
        const content = menuOverlay.querySelector(`[data-content="${section}"]`);
        if (content) {
          content.style.display = 'none';
        }
        const chevron = header.querySelector('.mobile-menu-chevron');
        if (chevron) {
          chevron.textContent = '▸';
        }
      });
    }
    
    menuBtn.addEventListener('click', openMenu);
    menuClose.addEventListener('click', closeMenu);
    
    // Close when clicking outside menu content
    menuOverlay.addEventListener('click', (e) => {
      // Don't close if clicking on section headers or their children
      if (e.target.closest('.mobile-menu-section-header')) {
        return;
      }
      // Don't close if clicking on menu items
      if (e.target.closest('.mobile-menu-item')) {
        return;
      }
      // Close if clicking on overlay background
      if (e.target === menuOverlay) {
        closeMenu();
      }
    });
    
    // Handle accordion toggle for expandable sections
    const sectionHeaders = menuOverlay.querySelectorAll('.mobile-menu-section-header');
    sectionHeaders.forEach(header => {
      header.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        
        const isExpanded = header.getAttribute('aria-expanded') === 'true';
        const section = header.getAttribute('data-section');
        const content = menuOverlay.querySelector(`[data-content="${section}"]`);
        const chevron = header.querySelector('.mobile-menu-chevron');
        
        // Close all other sections (accordion behavior)
        sectionHeaders.forEach(otherHeader => {
          if (otherHeader !== header) {
            otherHeader.setAttribute('aria-expanded', 'false');
            const otherSection = otherHeader.getAttribute('data-section');
            const otherContent = menuOverlay.querySelector(`[data-content="${otherSection}"]`);
            if (otherContent) {
              otherContent.style.display = 'none';
            }
            const otherChevron = otherHeader.querySelector('.mobile-menu-chevron');
            if (otherChevron) {
              otherChevron.textContent = '▸';
            }
          }
        });
        
        // Toggle current section
        if (isExpanded) {
          header.setAttribute('aria-expanded', 'false');
          if (content) {
            content.style.display = 'none';
          }
          if (chevron) {
            chevron.textContent = '▸';
          }
        } else {
          header.setAttribute('aria-expanded', 'true');
          if (content) {
            content.style.display = 'block';
          }
          if (chevron) {
            chevron.textContent = '▾';
          }
        }
      });
    });
  }

  // Initialize mobile search
  function initMobileSearch() {
    const searchBtn = document.getElementById('mobile-search-btn');
    const searchOverlay = document.getElementById('mobile-search-overlay');
    const searchClose = document.getElementById('mobile-search-close');
    const searchInput = document.getElementById('mobile-search-input');
    const searchDropdown = document.getElementById('mobile-search-dropdown');
    
    if (!searchBtn || !searchOverlay || !searchClose || !searchInput || !searchDropdown) return;
    
    // Reuse existing search logic
    const desktopSearchInput = document.getElementById('header-search-input');
    const desktopSearchDropdown = document.getElementById('search-dropdown');
    
    function openSearch() {
      searchOverlay.style.display = 'block';
      document.body.style.overflow = 'hidden';
      // Focus input after a brief delay to ensure overlay is visible
      setTimeout(() => {
        searchInput.focus();
      }, 100);
    }
    
    function closeSearch() {
      searchOverlay.style.display = 'none';
      document.body.style.overflow = '';
      searchInput.value = '';
      searchDropdown.style.display = 'none';
    }
    
    searchBtn.addEventListener('click', openSearch);
    searchClose.addEventListener('click', closeSearch);
    
    // Close when clicking outside search content
    searchOverlay.addEventListener('click', (e) => {
      if (e.target === searchOverlay) {
        closeSearch();
      }
    });
    
    // Initialize search functionality for mobile input
    if (typeof Fuse !== 'undefined' && window.SEARCH_INDEX && Array.isArray(window.SEARCH_INDEX)) {
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
      
      function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
      }
      
      function renderResults(query) {
        if (query.length < 2) {
          searchDropdown.style.display = 'none';
          activeIndex = -1;
          return;
        }
        
        const results = fuse.search(query);
        
        if (results.length === 0) {
          searchDropdown.innerHTML = `
            <div class="search-result-item search-result-empty">No results found</div>
          `;
          searchDropdown.style.display = 'block';
          activeIndex = -1;
          return;
        }
        
        // Group by type, preserving Fuse.js relevance scores
        const wrestlerResults = results.filter(r => r.item.type === 'wrestler');
        const teamResults = results.filter(r => r.item.type === 'team');
        
        // Sort wrestlers: prioritize exact name matches, then Fuse.js relevance, then rank
        const queryLower = query.toLowerCase();
        wrestlerResults.sort((a, b) => {
          const nameA = (a.item.name || '').toLowerCase();
          const nameB = (b.item.name || '').toLowerCase();
          
          // Primary: Exact name matches (name starts with query or equals query)
          const exactMatchA = nameA === queryLower || nameA.startsWith(queryLower);
          const exactMatchB = nameB === queryLower || nameB.startsWith(queryLower);
          
          if (exactMatchA && !exactMatchB) return -1; // A is exact match, B is not
          if (!exactMatchA && exactMatchB) return 1;  // B is exact match, A is not
          
          // Secondary: If both or neither are exact matches, use Fuse.js relevance score
          if (exactMatchA === exactMatchB) {
            const scoreA = a.score || 1;
            const scoreB = b.score || 1;
            if (Math.abs(scoreA - scoreB) > 0.01) {
              return scoreA - scoreB; // Lower score = better match
            }
          }
          
          // Tertiary: Rank (only when relevance is similar or both are exact matches)
          const rankA = a.item.rank !== null && a.item.rank !== undefined ? a.item.rank : 9999;
          const rankB = b.item.rank !== null && b.item.rank !== undefined ? b.item.rank : 9999;
          return rankA - rankB;
        });
        
        // Limit to top 10 wrestlers after sorting
        const topWrestlers = wrestlerResults.slice(0, 10);
        let currentResults = topWrestlers.map(r => r.item).concat(teamResults.map(r => r.item));
        
        const wrestlers = topWrestlers.map(r => r.item);
        const teams = teamResults.map(r => r.item);
        
        let html = '';
        
        if (wrestlers.length > 0) {
          html += '<div class="search-section">';
          html += '<div class="search-section-label">Wrestlers</div>';
          html += '<div class="search-results">';
          wrestlers.forEach((item) => {
            const globalIdx = currentResults.indexOf(item);
            // Add female symbol if gender is 'girls'
            const nameDisplay = item.gender === 'girls' 
              ? `${escapeHtml(item.name)} <span style="color: #ff69b4;">♀</span>`
              : escapeHtml(item.name);
            html += `
              <div class="search-result" data-url="${item.url}" data-index="${globalIdx}">
                <div class="search-name">${nameDisplay}</div>
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
          teams.forEach((item) => {
            const globalIdx = currentResults.indexOf(item);
            // Add gender symbol: blue ♂ for boys, pink ♀ for girls
            let nameDisplay = escapeHtml(item.name);
            if (item.gender === 'boys') {
              nameDisplay += ' <span style="color: #0066cc;">♂</span>';
            } else if (item.gender === 'girls') {
              nameDisplay += ' <span style="color: #ff69b4;">♀</span>';
            }
            html += `
              <div class="search-result" data-url="${item.url}" data-index="${globalIdx}">
                <div class="search-name">${nameDisplay}</div>
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
      
      searchInput.addEventListener('input', (e) => {
        const query = e.target.value.trim();
        renderResults(query);
      });
      
      searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
          closeSearch();
        }
      });
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
      
      if (results.length === 0) {
        searchDropdown.innerHTML = `
          <div class="search-result-item search-result-empty">No results found</div>
        `;
        searchDropdown.style.display = 'block';
        activeIndex = -1;
        return;
      }
      
      // Group by type, preserving Fuse.js relevance scores
      const wrestlerResults = results.filter(r => r.item.type === 'wrestler');
      const teamResults = results.filter(r => r.item.type === 'team');
      
      // Sort wrestlers: prioritize exact name matches, then Fuse.js relevance, then rank
      const queryLower = query.toLowerCase();
      wrestlerResults.sort((a, b) => {
        const nameA = (a.item.name || '').toLowerCase();
        const nameB = (b.item.name || '').toLowerCase();
        
        // Primary: Exact name matches (name starts with query or equals query)
        const exactMatchA = nameA === queryLower || nameA.startsWith(queryLower);
        const exactMatchB = nameB === queryLower || nameB.startsWith(queryLower);
        
        if (exactMatchA && !exactMatchB) return -1; // A is exact match, B is not
        if (!exactMatchA && exactMatchB) return 1;  // B is exact match, A is not
        
        // Secondary: If both or neither are exact matches, use Fuse.js relevance score
        if (exactMatchA === exactMatchB) {
          const scoreA = a.score || 1;
          const scoreB = b.score || 1;
          if (Math.abs(scoreA - scoreB) > 0.01) {
            return scoreA - scoreB; // Lower score = better match
          }
        }
        
        // Tertiary: Rank (only when relevance is similar or both are exact matches)
        const rankA = a.item.rank !== null && a.item.rank !== undefined ? a.item.rank : 9999;
        const rankB = b.item.rank !== null && b.item.rank !== undefined ? b.item.rank : 9999;
        return rankA - rankB;
      });
      
      // Limit to top 10 wrestlers after sorting
      const topWrestlers = wrestlerResults.slice(0, 10);
      currentResults = topWrestlers.map(r => r.item).concat(teamResults.map(r => r.item));
      
      const wrestlers = topWrestlers.map(r => r.item);
      const teams = teamResults.map(r => r.item);
      
      let html = '';
      
      if (wrestlers.length > 0) {
        html += '<div class="search-section">';
        html += '<div class="search-section-label">Wrestlers</div>';
        html += '<div class="search-results">';
        wrestlers.forEach((item, idx) => {
          const globalIdx = currentResults.indexOf(item);
          // Add female symbol if gender is 'girls'
          const nameDisplay = item.gender === 'girls' 
            ? `${escapeHtml(item.name)} <span style="color: #ff69b4;">♀</span>`
            : escapeHtml(item.name);
          html += `
            <div class="search-result" data-url="${item.url}" data-index="${globalIdx}">
              <div class="search-name">${nameDisplay}</div>
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
          // Add gender symbol: blue ♂ for boys, pink ♀ for girls
          let nameDisplay = escapeHtml(item.name);
          if (item.gender === 'boys') {
            nameDisplay += ' <span style="color: #0066cc;">♂</span>';
          } else if (item.gender === 'girls') {
            nameDisplay += ' <span style="color: #ff69b4;">♀</span>';
          }
          html += `
            <div class="search-result" data-url="${item.url}" data-index="${globalIdx}">
              <div class="search-name">${nameDisplay}</div>
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

