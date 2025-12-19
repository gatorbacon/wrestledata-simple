// ========================================
// All-American & Title Odds Leaderboard (Stacked View)
// ========================================

function getQueryParam(key) {
  return new URLSearchParams(window.location.search).get(key);
}

function resolveSeason() {
  return "2026"; // Or make dynamic later
}

// ========================================
// Weight tabs component
// ========================================
function createWeightTabs(containerId, selectedWeight, onWeightChange) {
  const container = document.getElementById(containerId);
  if (!container) {
    console.warn(`Weight tabs container not found: ${containerId}`);
    return;
  }
  
  const weights = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285];
  
  container.innerHTML = '';
  container.setAttribute('role', 'tablist');
  container.setAttribute('aria-label', 'Weight class filter');
  
  weights.forEach((weight, index) => {
    const tab = document.createElement('button');
    tab.setAttribute('role', 'tab');
    
    const isSelected = weight === selectedWeight;
    tab.setAttribute('aria-selected', isSelected ? 'true' : 'false');
    tab.setAttribute('tabindex', isSelected ? '0' : '-1');
    tab.className = 'weight-tab';
    if (isSelected) {
      tab.classList.add('active');
    }
    tab.textContent = weight.toString();
    tab.dataset.weight = weight.toString();
    
    tab.addEventListener('click', () => {
      onWeightChange(weight);
    });
    
    // Keyboard navigation
    tab.addEventListener('keydown', (e) => {
      let targetIndex = index;
      if (e.key === 'ArrowLeft') {
        targetIndex = index > 0 ? index - 1 : weights.length - 1;
      } else if (e.key === 'ArrowRight') {
        targetIndex = index < weights.length - 1 ? index + 1 : 0;
      } else if (e.key === 'Home') {
        targetIndex = 0;
      } else if (e.key === 'End') {
        targetIndex = weights.length - 1;
      } else {
        return;
      }
      
      e.preventDefault();
      const targetWeight = weights[targetIndex];
      onWeightChange(targetWeight);
    });
    
    container.appendChild(tab);
  });
}

// ========================================
// Rank badge creation
// ========================================
function createRankBadge(rank) {
  if (rank === null || rank === undefined || rank === "") {
    return document.createTextNode("—");
  }
  
  const badge = document.createElement("span");
  badge.className = "rank-badge";
  
  // Medal badge styling: #1 gold, #2 silver, #3-5 bronze, others neutral
  if (rank === 1) {
    badge.classList.add("medal-gold");
  } else if (rank === 2) {
    badge.classList.add("medal-silver");
  } else if (rank >= 3 && rank <= 5) {
    badge.classList.add("medal-bronze");
  } else {
    badge.classList.add("standard");
  }
  
  badge.textContent = `#${rank}`;
  return badge;
}

// ========================================
// Stacked probability bar creation
// ========================================
function createStackedProbabilityBar(champProb, finalProb, aaProb) {
  // Clamp probabilities to [0, 1]
  const champ = Math.max(0, Math.min(1, champProb || 0));
  const final = Math.max(0, Math.min(1, finalProb || 0));
  const aa = Math.max(0, Math.min(1, aaProb || 0));
  
  // Calculate segments
  const champSegment = champ;
  const finalOnlySegment = Math.max(0, final - champ);
  const aaOnlySegment = Math.max(0, aa - final);
  const remainderSegment = Math.max(0, 1 - aa);
  
  // Format champion percentage for display (using tabular numerals)
  const champPercent = champ < 0.005 ? "<0.5%" : (champ * 100).toFixed(1) + "%";
  
  // Create container
  const container = document.createElement("div");
  container.className = "stacked-bar-container";
  
  // Create bar wrapper
  const barWrapper = document.createElement("div");
  barWrapper.className = "stacked-bar-wrapper";
  barWrapper.setAttribute('data-champ', champ);
  barWrapper.setAttribute('data-final', final);
  barWrapper.setAttribute('data-aa', aa);
  
  // Create segments (only if > 0) with data attributes for tooltips
  if (champSegment > 0) {
    const champSeg = document.createElement("div");
    champSeg.className = "stacked-bar-segment stacked-bar-champion";
    champSeg.style.width = `${champSegment * 100}%`;
    champSeg.setAttribute('data-segment-type', 'champion');
    champSeg.setAttribute('data-champ', champ);
    champSeg.setAttribute('data-final', final);
    champSeg.setAttribute('data-aa', aa);
    barWrapper.appendChild(champSeg);
  }
  
  if (finalOnlySegment > 0) {
    const finalSeg = document.createElement("div");
    finalSeg.className = "stacked-bar-segment stacked-bar-finalist";
    finalSeg.style.width = `${finalOnlySegment * 100}%`;
    finalSeg.setAttribute('data-segment-type', 'finalist');
    finalSeg.setAttribute('data-champ', champ);
    finalSeg.setAttribute('data-final', final);
    finalSeg.setAttribute('data-aa', aa);
    barWrapper.appendChild(finalSeg);
  }
  
  if (aaOnlySegment > 0) {
    const aaSeg = document.createElement("div");
    aaSeg.className = "stacked-bar-segment stacked-bar-aa";
    aaSeg.style.width = `${aaOnlySegment * 100}%`;
    aaSeg.setAttribute('data-segment-type', 'aa');
    aaSeg.setAttribute('data-champ', champ);
    aaSeg.setAttribute('data-final', final);
    aaSeg.setAttribute('data-aa', aa);
    barWrapper.appendChild(aaSeg);
  }
  
  if (remainderSegment > 0) {
    const remSeg = document.createElement("div");
    remSeg.className = "stacked-bar-segment stacked-bar-remainder";
    remSeg.style.width = `${remainderSegment * 100}%`;
    remSeg.setAttribute('data-segment-type', 'remainder');
    barWrapper.appendChild(remSeg);
  }
  
  // Create value label (Champion %)
  const valueLabel = document.createElement("span");
  valueLabel.className = "stacked-bar-value";
  valueLabel.textContent = champPercent;
  
  container.appendChild(barWrapper);
  container.appendChild(valueLabel);
  
  return container;
}

// ========================================
// Team name to slug conversion
// ========================================
function teamNameToSlug(teamName) {
  if (!teamName) return "";
  let slug = teamName.toLowerCase();
  slug = slug.replace(/\s+/g, "_");
  slug = slug.replace(/[^\w_]/g, "");
  slug = slug.replace(/_+/g, "_");
  slug = slug.replace(/^_+|_+$/g, "");
  return slug;
}

// ========================================
// Global state
// ========================================
let currentWeight = 125; // Default to lowest weight
let currentData = null;
let currentSort = "champ_prob"; // Default sort by Champion %
let sortDirection = "desc"; // Default descending

// ========================================
// Load data for a weight class
// ========================================
async function loadWeightData(weight) {
  const season = resolveSeason();
  const url = `/xtp/${season}/xtp_weight_${season}_${weight}.json`;
  
  try {
    const res = await fetch(url);
    if (!res.ok) {
      throw new Error(`Failed to load ${url}: ${res.status} ${res.statusText}`);
    }
    const data = await res.json();
    return data;
  } catch (err) {
    console.error(`Error loading weight ${weight} data:`, err);
    throw err;
  }
}

// ========================================
// Sort data
// ========================================
function sortData(data, sortKey, direction) {
  const sorted = [...data];
  
  sorted.sort((a, b) => {
    const aVal = a[sortKey] || 0;
    const bVal = b[sortKey] || 0;
    
    if (direction === "desc") {
      return bVal - aVal;
    } else {
      return aVal - bVal;
    }
  });
  
  return sorted;
}

// ========================================
// Render leaderboard table
// ========================================
function renderLeaderboard(data) {
  if (!data || data.length === 0) {
    const tbody = document.querySelector("#odds-stacked-table tbody");
    if (tbody) {
      tbody.innerHTML = "<tr><td colspan='4' style='text-align: center; padding: 2em;'>No data available</td></tr>";
    }
    return;
  }
  
  // Sort data
  const sorted = sortData(data, currentSort, sortDirection);
  
  const tbody = document.querySelector("#odds-stacked-table tbody");
  if (!tbody) return;
  
  tbody.innerHTML = "";
  
  sorted.forEach((entry) => {
    const tr = document.createElement("tr");
    
    // Store probability data on row for tooltip
    tr.setAttribute('data-champ', entry.champ_prob || 0);
    tr.setAttribute('data-final', entry.final_prob || 0);
    tr.setAttribute('data-aa', entry.aa_prob || 0);
    
    // Rank
    const rankTd = document.createElement("td");
    rankTd.appendChild(createRankBadge(entry.rank));
    tr.appendChild(rankTd);
    
    // Name (linked to wrestler profile)
    const nameTd = document.createElement("td");
    const nameLink = document.createElement("a");
    nameLink.href = `/wrestler.html?id=${entry.wrestler_id}`;
    nameLink.textContent = entry.name || "Unknown";
    nameLink.className = "wrestler-link";
    nameTd.appendChild(nameLink);
    tr.appendChild(nameTd);
    
    // Team (linked to team profile)
    const teamTd = document.createElement("td");
    const teamSlug = teamNameToSlug(entry.team);
    if (teamSlug) {
      const teamLink = document.createElement("a");
      teamLink.href = `/team.html?team=${teamSlug}`;
      teamLink.textContent = entry.team || "Unknown";
      teamLink.className = "team-link";
      teamTd.appendChild(teamLink);
    } else {
      teamTd.textContent = entry.team || "Unknown";
    }
    tr.appendChild(teamTd);
    
    // Stacked bar
    const barTd = document.createElement("td");
    barTd.className = "col-stacked-bar";
    barTd.appendChild(createStackedProbabilityBar(
      entry.champ_prob,
      entry.final_prob,
      entry.aa_prob
    ));
    tr.appendChild(barTd);
    
    tbody.appendChild(tr);
  });
  
  // Update sort indicators
  updateSortIndicators();
  
  // Attach row-level tooltips
  attachRowTooltips();
}

// ========================================
// Attach row-level tooltips
// ========================================
function attachRowTooltips() {
  const rows = document.querySelectorAll('#odds-stacked-table tbody tr');
  
  rows.forEach((row) => {
    const champ = parseFloat(row.getAttribute('data-champ')) || 0;
    const final = parseFloat(row.getAttribute('data-final')) || 0;
    const aa = parseFloat(row.getAttribute('data-aa')) || 0;
    
    // Format percentages
    const champPct = champ < 0.005 ? "<0.5%" : (champ * 100).toFixed(1) + "%";
    const finalPct = final < 0.005 ? "<0.5%" : (final * 100).toFixed(1) + "%";
    const aaPct = aa < 0.005 ? "<0.5%" : (aa * 100).toFixed(1) + "%";
    
    // Create tooltip text (3 lines)
    const tooltipText = `Champion: ${champPct}\nFinalist (incl. champ): ${finalPct}\nAll-American (incl. finals): ${aaPct}`;
    
    // Create custom tooltip element
    const tooltip = document.createElement('div');
    tooltip.className = 'odds-row-tooltip';
    tooltip.innerHTML = tooltipText.split('\n').map(line => `<div>${line}</div>`).join('');
    document.body.appendChild(tooltip);
    
    // Show/hide tooltip on row hover (positioned above row center)
    const updateTooltipPosition = () => {
      const rect = row.getBoundingClientRect();
      tooltip.style.left = (rect.left + rect.width / 2) + 'px';
      tooltip.style.top = (rect.top - 8) + 'px';
    };
    
    row.addEventListener('mouseenter', () => {
      updateTooltipPosition();
      tooltip.style.display = 'block';
    });
    
    row.addEventListener('mouseleave', () => {
      tooltip.style.display = 'none';
    });
  });
}

// ========================================
// Update sort indicators in header
// ========================================
function updateSortIndicators() {
  const headers = document.querySelectorAll("#odds-stacked-table thead th.sortable");
  headers.forEach((th) => {
    const sortKey = th.dataset.sort;
    th.classList.remove("sort-asc", "sort-desc");
    
    if (sortKey === currentSort) {
      th.classList.add(sortDirection === "asc" ? "sort-asc" : "sort-desc");
    }
  });
}

// ========================================
// Initialize sorting
// ========================================
function initSorting() {
  const header = document.getElementById("odds-breakdown-header");
  if (!header) return;
  
  header.style.cursor = "pointer";
  
  // Cycle through sort options: champ_prob -> final_prob -> aa_prob -> champ_prob
  header.addEventListener("click", () => {
    if (currentSort === "champ_prob") {
      currentSort = "final_prob";
    } else if (currentSort === "final_prob") {
      currentSort = "aa_prob";
    } else {
      currentSort = "champ_prob";
    }
    
    // Always use descending for these sorts
    sortDirection = "desc";
    
    // Update header dataset
    header.dataset.sort = currentSort;
    
    // Update header text to show active sort
    updateSortHeaderText();
    
    // Re-render with new sort
    if (currentData) {
      renderLeaderboard(currentData);
    }
  });
}

// ========================================
// Create legend
// ========================================
function createLegend() {
  const legendContainer = document.getElementById("stacked-odds-legend");
  if (!legendContainer) return;
  
  legendContainer.innerHTML = "";
  legendContainer.className = "stacked-odds-legend";
  
  const items = [
    { label: "Champion", class: "stacked-bar-champion" },
    { label: "Finalist", class: "stacked-bar-finalist" },
    { label: "All-American", class: "stacked-bar-aa" },
    { label: "Outside Top 8", class: "stacked-bar-remainder" }
  ];
  
  items.forEach((item, index) => {
    const itemEl = document.createElement("span");
    itemEl.className = "legend-item";
    
    const swatch = document.createElement("span");
    swatch.className = `legend-swatch ${item.class}`;
    
    const label = document.createElement("span");
    label.className = "legend-label";
    label.textContent = item.label;
    
    itemEl.appendChild(swatch);
    itemEl.appendChild(label);
    legendContainer.appendChild(itemEl);
    
    // Add separator except for last item
    if (index < items.length - 1) {
      const separator = document.createElement("span");
      separator.className = "legend-separator";
      separator.textContent = "·";
      legendContainer.appendChild(separator);
    }
  });
}

// ========================================
// Update sort header text
// ========================================
function updateSortHeaderText() {
  const header = document.getElementById("odds-breakdown-header");
  if (!header) return;
  
  // Header text is now fixed: "Odds Breakdown (Cumulative Path to AA)"
  // Just update the sort indicator tooltip
  const sortIndicator = header.querySelector(".sort-indicator");
  if (sortIndicator) {
    let tooltipText = "";
    if (currentSort === "champ_prob") {
      tooltipText = "Sorted by Championship probability";
    } else if (currentSort === "final_prob") {
      tooltipText = "Sorted by Finalist probability";
    } else if (currentSort === "aa_prob") {
      tooltipText = "Sorted by All-American probability";
    }
    
    if (tooltipText && typeof addTooltip === 'function') {
      addTooltip(sortIndicator, tooltipText);
    }
  }
}

// ========================================
// Initialize tooltips
// ========================================
function initTooltips() {
  // Wait for tooltips.js to be available
  if (typeof TOOLTIPS !== 'undefined') {
    const tooltips = {
      'cumulative-path': 'This bar shows cumulative probabilities.\nEach segment includes all outcomes to its right:\nChampion ⊂ Finalist ⊂ All-American.'
    };
    
    // Add tooltips to global TOOLTIPS if it exists
    if (typeof TOOLTIPS !== 'undefined') {
      Object.assign(TOOLTIPS, tooltips);
    }
    
    // Initialize tooltips for icons
    document.querySelectorAll('.tooltip-icon').forEach(icon => {
      const tooltipKey = icon.dataset.tooltip;
      if (tooltipKey && tooltips[tooltipKey] && typeof addTooltip === 'function') {
        addTooltip(icon, tooltips[tooltipKey]);
      }
    });
  } else {
    // Retry after a short delay
    setTimeout(initTooltips, 100);
  }
}

// ========================================
// Main initialization
// ========================================
async function init() {
  // Check for weight parameter in URL
  const weightParam = getQueryParam("weight");
  if (weightParam) {
    const parsedWeight = parseInt(weightParam);
    if (!isNaN(parsedWeight)) {
      currentWeight = parsedWeight;
    }
  }
  
  // Set season info
  const season = resolveSeason();
  document.getElementById("season-info").textContent = `Season ${season}`;
  
  // Create weight tabs handler
  const handleWeightChange = async (weight) => {
    currentWeight = weight;
    
    // Update URL without reload
    const url = new URL(window.location);
    url.searchParams.set('weight', weight);
    window.history.pushState({}, '', url);
    
    // Update tabs
    createWeightTabs('weight-tabs-container', currentWeight, handleWeightChange);
    
    // Load and render data
    try {
      currentData = await loadWeightData(weight);
      renderLeaderboard(currentData);
    } catch (err) {
      console.error("Error loading data:", err);
      const tbody = document.querySelector("#odds-stacked-table tbody");
      if (tbody) {
        tbody.innerHTML = "<tr><td colspan='4' style='text-align: center; padding: 2em;'>Error loading data</td></tr>";
      }
    }
  };
  
  // Create weight tabs
  createWeightTabs('weight-tabs-container', currentWeight, handleWeightChange);
  
  // Initialize sorting
  initSorting();
  
  // Create legend
  createLegend();
  
  // Initialize tooltips
  initTooltips();
  
  // Update sort header text initially
  updateSortHeaderText();
  
  // Load initial data
  try {
    currentData = await loadWeightData(currentWeight);
    renderLeaderboard(currentData);
  } catch (err) {
    console.error("Error loading initial data:", err);
    const tbody = document.querySelector("#odds-stacked-table tbody");
    if (tbody) {
      tbody.innerHTML = "<tr><td colspan='4' style='text-align: center; padding: 2em;'>Error loading data</td></tr>";
    }
  }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

