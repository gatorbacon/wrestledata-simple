/**
 * Standard tooltip system for metric definitions
 * Tooltips explain. Links navigate. Nothing should look interactive unless it actually is.
 */

function createTooltip(text) {
  const tooltip = document.createElement('span');
  tooltip.className = 'tooltip';
  
  // Handle multi-line text (replace \n with <br>)
  if (text.includes('\n')) {
    const lines = text.split('\n');
    lines.forEach((line, index) => {
      if (index > 0) {
        tooltip.appendChild(document.createElement('br'));
      }
      tooltip.appendChild(document.createTextNode(line));
    });
  } else {
    tooltip.textContent = text;
  }
  
  tooltip.setAttribute('role', 'tooltip');
  return tooltip;
}

function showTooltip(element, tooltipEl) {
  if (!tooltipEl) return;
  
  // For table headers or tooltip icons inside table headers, use fixed positioning
  const isInTableHeader = element.tagName === 'TH' || element.closest('th');
  if (isInTableHeader) {
    const targetRect = element.tagName === 'TH' ? element.getBoundingClientRect() : element.closest('th').getBoundingClientRect();
    tooltipEl.style.position = 'fixed';
    tooltipEl.style.left = (targetRect.left + targetRect.width / 2) + 'px';
    tooltipEl.style.top = (targetRect.top - 8) + 'px';
    tooltipEl.style.transform = 'translate(-50%, -100%)';
    tooltipEl.style.bottom = 'auto';
  } else {
    // For bar segments, position above the segment
    const rect = element.getBoundingClientRect();
    tooltipEl.style.position = 'fixed';
    tooltipEl.style.left = (rect.left + rect.width / 2) + 'px';
    tooltipEl.style.top = (rect.top - 8) + 'px';
    tooltipEl.style.transform = 'translate(-50%, -100%)';
    tooltipEl.style.zIndex = '10000';
  }
  
  tooltipEl.style.opacity = '1';
  tooltipEl.style.visibility = 'visible';
}

function hideTooltip(tooltipEl) {
  if (!tooltipEl) return;
  tooltipEl.style.opacity = '0';
  tooltipEl.style.visibility = 'hidden';
}

function addTooltip(element, text) {
  if (!element || !text) return;
  
  // Don't add if already has tooltip
  if (element.querySelector('.tooltip')) return;
  
  element.classList.add('tooltip-trigger');
  const tooltip = createTooltip(text);
  element.appendChild(tooltip);
  
  // Make keyboard accessible
  element.setAttribute('tabindex', '0');
  element.setAttribute('aria-label', text);
  
  // Show/hide on hover and focus
  const showHandler = () => showTooltip(element, tooltip);
  const hideHandler = () => hideTooltip(tooltip);
  
  element.addEventListener('mouseenter', showHandler);
  element.addEventListener('mouseleave', hideHandler);
  element.addEventListener('focus', showHandler);
  element.addEventListener('blur', hideHandler);
}

// Tooltip definitions
const TOOLTIPS = {
  'xtp': 'Expected NCAA team points based on advancement, placement, and bonus probabilities.',
  'mv': 'Match Index (MI) shows per-match performance above replacement, normalized for opponent quality and match outcome. It is a rate metric, not a ranking.',
  'xtp-p': 'Expected placement points.',
  'xtp-a': 'Expected advancement points.',
  'xtp-b': 'Expected bonus points.',
  'threshold': 'Minimum match threshold increases as the season progresses to ensure ranking stability.'
};

// Initialize tooltips on page load
document.addEventListener('DOMContentLoaded', () => {
  // Handle tooltip icons - these are the primary trigger pattern
  document.querySelectorAll('.tooltip-icon[data-tooltip]').forEach(icon => {
    const key = icon.getAttribute('data-tooltip');
    if (TOOLTIPS[key]) {
      addTooltip(icon, TOOLTIPS[key]);
    }
  });
  
  // Handle elements with data-tooltip attribute (legacy support, should be converted to icons)
  document.querySelectorAll('[data-tooltip]:not(.tooltip-icon)').forEach(el => {
    const key = el.getAttribute('data-tooltip');
    if (TOOLTIPS[key] && !el.closest('.tooltip-icon')) {
      addTooltip(el, TOOLTIPS[key]);
    }
  });
});

