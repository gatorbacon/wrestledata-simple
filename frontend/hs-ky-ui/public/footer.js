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
          <p class="footer-text" style="font-size: 0.9375rem; color: var(--text); margin: 0;">
            <a href="/report.html" class="footer-report-link" style="color: var(--accent-primary, #2563eb); font-weight: 600; text-decoration: none; border-bottom: 1px solid currentColor;">Contact Us / Ask about a ranking</a>
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

