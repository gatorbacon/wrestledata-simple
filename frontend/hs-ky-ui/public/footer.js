// ========================================
// Site-wide Footer Component
// ========================================

(function() {
  'use strict';

  // Create footer HTML structure
  function createFooterHTML() {
    return `
      <footer class="site-footer">
        <div class="footer-content">
          <p class="footer-text">
            <a href="/report.html" class="footer-report-link footer-report-link--muted">Contact Us</a>
            &nbsp;·&nbsp;
            <a href="/privacy.html" class="footer-report-link footer-report-link--muted">Privacy Policy</a>
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

