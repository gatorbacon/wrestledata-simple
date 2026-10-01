/**
 * Standard tooltip system for metric definitions
 * Tooltips explain. Links navigate. Nothing should look interactive unless it actually is.
 */

function createTooltip(text) {
  const tooltip = document.createElement('span');
  tooltip.className = 'tooltip';
  tooltip.textContent = text;
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

  // Info icons are handled by the tap/click popover below (works on touch
  // screens and for icons rendered after page load). Just remember the text.
  if (element.classList.contains('tooltip-icon')) {
    element.dataset.tooltipText = text;
    return;
  }
  
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
  'xtp': 'Expected NCAA tournament points from a 10,000-trial Monte Carlo simulation of the bracket.',
  'mv': 'DPG (Dual Points Gained): the extra dual points per match vs. what a typical wrestler gets against that same opponent.',
  'xtp-p': 'Expected placement points.',
  'xtp-a': 'Expected advancement points.',
  'xtp-b': 'Expected bonus points.',
  'threshold': 'Minimum match threshold increases as the season progresses to ensure ranking stability.',
  'dpg-trajectory': 'Dual Points Gained, match by match. Each bar is one match: the extra dual points scored vs. what a typical wrestler gets against that same opponent. Green = won and beat that benchmark, red = lost and fell short of it, grey = won but fell short, or lost but beat it. The solid line is the average of the last 5 matches; the dashed line is the season (or career) average.',
  'hodge': 'Blends win record, quality of competition, dominance (avg team points per match), and pin rate into one score. Eligibility requires a top-3 weight-class rank and a strong win percentage.'
};

// Info-icon popover (2026-10-01). Every `.tooltip-icon[data-tooltip]` on
// the page -- including ones a page script renders later (the profile's DPG
// icons) -- opens one shared popover: tap/click toggles it (phones have no
// hover), hover previews it on mouse devices, Escape / tapping elsewhere /
// scrolling closes it. Text: the icon's data-tooltip-text (set by
// addTooltip, e.g. page-specific keys) or TOOLTIPS[data-tooltip].
(function () {
  let pop = null;
  let current = null;
  let pinned = false;
  const canHover = window.matchMedia && window.matchMedia('(hover: hover) and (pointer: fine)').matches;

  function iconFrom(target) {
    const icon = target && target.closest ? target.closest('.tooltip-icon[data-tooltip]') : null;
    return icon && textFor(icon) ? icon : null;
  }
  function textFor(icon) {
    return icon.dataset.tooltipText || TOOLTIPS[icon.getAttribute('data-tooltip')] || '';
  }
  function prepare(icon) {
    if (icon.dataset.tooltipReady) return;
    icon.dataset.tooltipReady = '1';
    icon.setAttribute('role', 'button');
    icon.setAttribute('tabindex', '0');
    icon.setAttribute('aria-label', 'What is this?');
    icon.setAttribute('aria-expanded', 'false');
  }
  function open(icon, pin) {
    if (!pop) {
      pop = document.createElement('div');
      pop.className = 'tooltip-popover';
      pop.id = 'tooltip-popover';
      pop.setAttribute('role', 'tooltip');
      document.body.appendChild(pop);
    }
    if (current && current !== icon) current.setAttribute('aria-expanded', 'false');
    current = icon;
    pinned = pin;
    pop.textContent = textFor(icon);
    pop.style.display = 'block';
    icon.setAttribute('aria-expanded', 'true');
    icon.setAttribute('aria-describedby', 'tooltip-popover');
    place(icon);
  }
  function place(icon) {
    const r = icon.getBoundingClientRect();
    const vw = document.documentElement.clientWidth;
    const vh = window.innerHeight;
    pop.style.left = '0px';
    pop.style.top = '0px';
    const w = pop.offsetWidth;
    const h = pop.offsetHeight;
    const left = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), vw - w - 8);
    const below = r.bottom + 8;
    const top = (below + h > vh - 8 && r.top - 8 - h > 8) ? r.top - 8 - h : below;
    pop.style.left = left + 'px';
    pop.style.top = top + 'px';
  }
  function close() {
    if (pop) pop.style.display = 'none';
    if (current) {
      current.setAttribute('aria-expanded', 'false');
      current.removeAttribute('aria-describedby');
    }
    current = null;
    pinned = false;
  }

  document.addEventListener('click', e => {
    const icon = iconFrom(e.target);
    if (!icon) {
      if (current && !(pop && pop.contains(e.target))) close();
      return;
    }
    // Icons sit inside sortable headers and clickable rows: don't trigger those.
    e.preventDefault();
    e.stopPropagation();
    prepare(icon);
    if (current === icon && pinned) close();
    else open(icon, true);
  }, true);

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') { close(); return; }
    const icon = iconFrom(e.target);
    if (icon && (e.key === 'Enter' || e.key === ' ')) {
      e.preventDefault();
      if (current === icon && pinned) close();
      else open(icon, true);
    }
  });

  if (canHover) {
    document.addEventListener('mouseover', e => {
      const icon = iconFrom(e.target);
      if (!icon) return;
      prepare(icon);
      if (!pinned) open(icon, false);
    });
    document.addEventListener('mouseout', e => {
      const icon = iconFrom(e.target);
      if (icon && icon === current && !pinned && !icon.contains(e.relatedTarget)) close();
    });
  }

  window.addEventListener('scroll', () => { if (current) close(); }, { passive: true, capture: true });
  window.addEventListener('resize', () => { if (current) close(); });

  // Make icons focusable/announced up front (keyboard users can't hover).
  function prepareAll(root) {
    (root || document).querySelectorAll('.tooltip-icon[data-tooltip]').forEach(icon => { if (textFor(icon)) prepare(icon); });
  }
  document.addEventListener('DOMContentLoaded', () => {
    prepareAll();
    // Legacy: non-icon elements with data-tooltip keep the inline hover tooltip.
    document.querySelectorAll('[data-tooltip]:not(.tooltip-icon)').forEach(el => {
      const key = el.getAttribute('data-tooltip');
      if (TOOLTIPS[key] && !el.closest('.tooltip-icon')) addTooltip(el, TOOLTIPS[key]);
    });
  });
})();
