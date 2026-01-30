// ========================================
// Site-wide Footer Component
// ========================================

(function() {
  'use strict';

  // Create footer HTML structure
  function createFooterHTML() {
    return `
      <footer class="site-footer" style="margin-top: 3em; padding-top: 2em; border-top: 1px solid var(--border-light); text-align: center;">
        <div class="footer-content" style="max-width: 800px; margin: 0 auto; padding: 0 1em;">
          <p class="footer-text" style="font-size: 0.8125rem; color: var(--text-secondary); margin: 0;">
            <a href="/report.html" style="color: var(--text-secondary); text-decoration: none;">Report a missing match or ask about a ranking</a>
          </p>
        </div>
      </footer>
    `;
  }

  // Initialize footer
  function initFooter() {
    // Insert footer at the end of body (before closing body tag)
    const body = document.body;
    if (body && !document.querySelector('.site-footer')) {
      const footerHTML = createFooterHTML();
      body.insertAdjacentHTML('beforeend', footerHTML);
    }
  }

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initFooter);
  } else {
    initFooter();
  }
})();

