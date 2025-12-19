// ========================================
// All-American & Title Odds Leaderboard (Unified)
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
// Probability bar creation (Table View)
// ========================================
function createProbabilityBar(prob) {
  if (prob === null || prob === undefined || isNaN(prob)) {
    return document.createTextNode("—");
  }
  
  // Clamp probability to [0, 1]
  const clampedProb = Math.max(0, Math.min(1, prob));
  const percentage = clampedProb * 100;
  
  // Format percentage display
  let displayText;
  if (percentage < 0.5) {
    displayText = "<0.5%";
  } else {
    displayText = percentage.toFixed(1) + "%";
  }
  
  // Determine color class based on percentage
  let colorClass = "prob-bar-gray";
  if (percentage >= 60) {
    colorClass = "prob-bar-strong-green";
  } else if (percentage >= 30) {
    colorClass = "prob-bar-green";
  } else if (percentage >= 10) {
    colorClass = "prob-bar-light-green";
  }
  
  // Create bar container
  const container = document.createElement("div");
  container.className = "prob-bar-container";
  
  // Create bar wrapper
  const barWrapper = document.createElement("div");
  barWrapper.className = "prob-bar-wrapper";
  
  // Create fill bar
  const fill = document.createElement("div");
  fill.className = `prob-bar-fill ${colorClass}`;
  fill.style.width = `${percentage}%`;
  
  // Create value label
  const valueLabel = document.createElement("span");
  valueLabel.className = "prob-bar-value";
  valueLabel.textContent = displayText;
  
  barWrapper.appendChild(fill);
  container.appendChild(barWrapper);
  container.appendChild(valueLabel);
  
  return container;
}

// ========================================
// Stacked probability bar creation (Stacked View)
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
  
  // Create segments (only if > 0)
  if (champSegment > 0) {
    const champSeg = document.createElement("div");
    champSeg.className = "stacked-bar-segment stacked-bar-champion";
    champSeg.style.width = `${champSegment * 100}%`;
    barWrapper.appendChild(champSeg);
  }
  
  if (finalOnlySegment > 0) {
    const finalSeg = document.createElement("div");
    finalSeg.className = "stacked-bar-segment stacked-bar-finalist";
    finalSeg.style.width = `${finalOnlySegment * 100}%`;
    barWrapper.appendChild(finalSeg);
  }
  
  if (aaOnlySegment > 0) {
    const aaSeg = document.createElement("div");
    aaSeg.className = "stacked-bar-segment stacked-bar-aa";
    aaSeg.style.width = `${aaOnlySegment * 100}%`;
    barWrapper.appendChild(aaSeg);
  }
  
  if (remainderSegment > 0) {
    const remSeg = document.createElement("div");
    remSeg.className = "stacked-bar-segment stacked-bar-remainder";
    remSeg.style.width = `${remainderSegment * 100}%`;
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
let currentSort = "aa_prob"; // Default sort by AA %
let sortDirection = "desc"; // Default descending
let viewMode = "table"; // "table" or "stacked"

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
// Render table view
// ========================================
function renderTableView(data) {
  if (!data || data.length === 0) {
    const tbody = document.querySelector("#aa-odds-table tbody");
    if (tbody) {
      tbody.innerHTML = "<tr><td colspan='6' style='text-align: center; padding: 2em;'>No data available</td></tr>";
    }
    return;
  }
  
  // Sort data
  const sorted = sortData(data, currentSort, sortDirection);
  
  const tbody = document.querySelector("#aa-odds-table tbody");
  if (!tbody) return;
  
  tbody.innerHTML = "";
  
  sorted.forEach((entry) => {
    const tr = document.createElement("tr");
    
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
    
    // Champion %
    const champTd = document.createElement("td");
    champTd.className = "col-prob";
    champTd.appendChild(createProbabilityBar(entry.champ_prob));
    tr.appendChild(champTd);
    
    // Finalist %
    const finalTd = document.createElement("td");
    finalTd.className = "col-prob";
    finalTd.appendChild(createProbabilityBar(entry.final_prob));
    tr.appendChild(finalTd);
    
    // AA %
    const aaTd = document.createElement("td");
    aaTd.className = "col-prob col-prob-primary";
    aaTd.appendChild(createProbabilityBar(entry.aa_prob));
    tr.appendChild(aaTd);
    
    tbody.appendChild(tr);
  });
  
  // Update sort indicators
  updateSortIndicators();
}

// ========================================
// Render stacked view
// ========================================
function renderStackedView(data) {
  if (!data || data.length === 0) {
    const tbody = document.querySelector("#aa-odds-stacked-table tbody");
    if (tbody) {
      tbody.innerHTML = "<tr><td colspan='5' style='text-align: center; padding: 2em;'>No data available</td></tr>";
    }
    return;
  }
  
  // Sort data (stacked view uses same sorting)
  const sorted = sortData(data, currentSort, sortDirection);
  
  const tbody = document.querySelector("#aa-odds-stacked-table tbody");
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
    
    // Champion % (numeric, right-aligned)
    const champTd = document.createElement("td");
    champTd.className = "col-champ-numeric";
    champTd.style.textAlign = "right";
    const champPercent = (entry.champ_prob || 0) < 0.005 ? "<0.5%" : ((entry.champ_prob || 0) * 100).toFixed(1) + "%";
    champTd.textContent = champPercent;
    tr.appendChild(champTd);
    
    tbody.appendChild(tr);
  });
  
  // Update sort indicators
  updateStackedSortIndicators();
  
  // Attach row-level tooltips
  attachRowTooltips();
}

// ========================================
// Render leaderboard (dispatches to correct view)
// ========================================
function renderLeaderboard(data) {
  if (viewMode === "table") {
    renderTableView(data);
  } else {
    renderStackedView(data);
  }
}

// ========================================
// Attach row-level tooltips (Stacked View)
// ========================================
function attachRowTooltips() {
  const rows = document.querySelectorAll('#aa-odds-stacked-table tbody tr');
  
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
// Update sort indicators (Table View)
// ========================================
function updateSortIndicators() {
  const headers = document.querySelectorAll("#aa-odds-table thead th.sortable");
  headers.forEach((th) => {
    const sortKey = th.dataset.sort;
    th.classList.remove("sort-asc", "sort-desc");
    
    if (sortKey === currentSort) {
      th.classList.add(sortDirection === "asc" ? "sort-asc" : "sort-desc");
    }
  });
}

// ========================================
// Update sort indicators (Stacked View)
// ========================================
function updateStackedSortIndicators() {
  const header = document.getElementById("odds-breakdown-header");
  if (header) {
    header.classList.remove("sort-asc", "sort-desc");
    header.classList.add(sortDirection === "asc" ? "sort-asc" : "sort-desc");
  }
}

// ========================================
// Initialize sorting (Table View)
// ========================================
function initSorting() {
  // Table view sorting
  const tableHeaders = document.querySelectorAll("#aa-odds-table thead th.sortable");
  
  tableHeaders.forEach((th) => {
    th.style.cursor = "pointer";
    th.addEventListener("click", () => {
      const sortKey = th.dataset.sort;
      
      // Toggle direction if clicking the same column
      if (sortKey === currentSort) {
        sortDirection = sortDirection === "asc" ? "desc" : "asc";
      } else {
        currentSort = sortKey;
        sortDirection = "desc"; // Default to descending
      }
      
      // Re-render with new sort
      if (currentData) {
        renderLeaderboard(currentData);
      }
    });
  });
  
  // Stacked view sorting (cycles through sort options)
  const stackedHeader = document.getElementById("odds-breakdown-header");
  if (stackedHeader) {
    stackedHeader.style.cursor = "pointer";
    
    stackedHeader.addEventListener("click", () => {
      // Cycle through sort options: champ_prob -> final_prob -> aa_prob -> champ_prob
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
      stackedHeader.dataset.sort = currentSort;
      
      // Re-render with new sort
      if (currentData) {
        renderLeaderboard(currentData);
      }
    });
  }
}

// ========================================
// Create legend (Stacked View)
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
// Switch view mode
// ========================================
function switchViewMode(mode) {
  if (mode !== "table" && mode !== "stacked") {
    return;
  }
  
  viewMode = mode;
  
  // Update toggle buttons
  document.querySelectorAll('.view-toggle-btn').forEach(btn => {
    if (btn.dataset.view === mode) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });
  
  // Show/hide tables
  const tableView = document.getElementById("aa-odds-table");
  const stackedView = document.getElementById("aa-odds-stacked-table");
  const legend = document.getElementById("stacked-odds-legend");
  const helperText = document.getElementById("view-helper-text");
  
  if (mode === "table") {
    if (tableView) tableView.style.display = "";
    if (stackedView) stackedView.style.display = "none";
    if (legend) legend.style.display = "none";
    if (helperText) helperText.style.display = "none";
  } else {
    if (tableView) tableView.style.display = "none";
    if (stackedView) stackedView.style.display = "";
    if (legend) legend.style.display = "";
    if (helperText) helperText.style.display = "";
    
    // Create legend if not already created
    createLegend();
  }
  
  // Re-render with current data
  if (currentData) {
    renderLeaderboard(currentData);
  }
}

// ========================================
// Initialize tooltips
// ========================================
function initTooltips() {
  // Wait for tooltips.js to be available
  if (typeof TOOLTIPS !== 'undefined') {
    const tooltips = {
      'champion-prob': 'Probability of winning the NCAA title.',
      'finalist-prob': 'Probability of reaching the NCAA finals.',
      'aa-prob': 'Probability of finishing Top 8 (earning All-American honors).',
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
  
  // Check for view parameter in URL
  const viewParam = getQueryParam("view");
  if (viewParam === "stacked") {
    viewMode = "stacked";
  }
  
  // Set season info
  const season = resolveSeason();
  document.getElementById("season-info").textContent = `Season ${season}`;
  
  // Initialize view toggle
  document.querySelectorAll('.view-toggle-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const mode = btn.dataset.view;
      switchViewMode(mode);
      
      // Update URL
      const url = new URL(window.location);
      if (mode === "table") {
        url.searchParams.delete('view');
      } else {
        url.searchParams.set('view', mode);
      }
      window.history.pushState({}, '', url);
    });
  });
  
  // Set initial view mode
  switchViewMode(viewMode);
  
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
      const tbody = document.querySelector(`#aa-odds-${viewMode === "table" ? "table" : "stacked-table"} tbody`);
      if (tbody) {
        tbody.innerHTML = `<tr><td colspan='${viewMode === "table" ? "6" : "5"}' style='text-align: center; padding: 2em;'>Error loading data</td></tr>`;
      }
    }
  };
  
  // Create weight tabs
  createWeightTabs('weight-tabs-container', currentWeight, handleWeightChange);
  
  // Initialize sorting
  initSorting();
  
  // Initialize tooltips
  initTooltips();
  
  // Load initial data
  try {
    currentData = await loadWeightData(currentWeight);
    renderLeaderboard(currentData);
  } catch (err) {
    console.error("Error loading initial data:", err);
    const tbody = document.querySelector(`#aa-odds-${viewMode === "table" ? "table" : "stacked-table"} tbody`);
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan='${viewMode === "table" ? "6" : "5"}' style='text-align: center; padding: 2em;'>Error loading data</td></tr>`;
    }
  }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
