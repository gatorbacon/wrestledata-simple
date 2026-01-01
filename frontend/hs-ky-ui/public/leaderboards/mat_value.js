function safe(v, fn) {
  if (v === null || v === undefined || v === "") return "—";
  return fn ? fn(v) : v;
}

function getQueryParam(key) {
  return new URLSearchParams(window.location.search).get(key);
}

function resolveSeason() {
  return "2026"; // Or make dynamic later
}

// ========================================
// REUSABLE: Date-aware minimum match threshold
// ========================================
function getMinMatchThreshold() {
  const now = new Date();
  const month = now.getMonth() + 1; // 1-12
  const day = now.getDate();
  
  // Before Dec 1
  if (month < 12) {
    return 3;
  }
  
  // Dec 1 through Dec 14
  if (month === 12 && day < 15) {
    return 4;
  }
  
  // Dec 15 or later
  return 5;
}

// ========================================
// REUSABLE: Weight tabs component
// ========================================
function createWeightTabs(containerId, selectedWeight, onWeightChange) {
  // Support both ID and class selector
  const container = document.getElementById(containerId) || 
                    document.querySelector(`#${containerId}`) || 
                    document.querySelector(`.${containerId}`);
  if (!container) {
    console.warn(`Weight tabs container not found: ${containerId}`);
    return;
  }
  
  const weights = ['all', 125, 133, 141, 149, 157, 165, 174, 184, 197, 285];
  
  container.innerHTML = '';
  container.setAttribute('role', 'tablist');
  container.setAttribute('aria-label', 'Weight class filter');
  
  weights.forEach((weight, index) => {
    const tab = document.createElement('button');
    tab.setAttribute('role', 'tab');
    
    // Normalize weight for comparison (handle both 'all' and numeric)
    const normalizedWeight = weight === 'all' ? 'all' : (typeof weight === 'number' ? weight : parseInt(weight));
    const normalizedSelected = selectedWeight === 'all' ? 'all' : (typeof selectedWeight === 'number' ? selectedWeight : parseInt(selectedWeight));
    const isSelected = normalizedWeight === normalizedSelected;
    
    tab.setAttribute('aria-selected', isSelected ? 'true' : 'false');
    tab.setAttribute('tabindex', isSelected ? '0' : '-1');
    tab.className = 'weight-tab';
    if (isSelected) {
      tab.classList.add('active');
    }
    tab.textContent = weight === 'all' ? 'All' : weight.toString();
    tab.dataset.weight = weight.toString();
    
    tab.addEventListener('click', () => {
      onWeightChange(weight === 'all' ? 'all' : parseInt(weight));
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
      onWeightChange(targetWeight === 'all' ? 'all' : parseInt(targetWeight));
    });
    
    container.appendChild(tab);
  });
}

// ========================================
// REUSABLE: Update threshold explainer
// ========================================
function updateThresholdExplainer(explainerId) {
  const explainer = document.getElementById(explainerId) || document.querySelector(explainerId);
  if (!explainer) return;
  
  const threshold = getMinMatchThreshold();
  explainer.innerHTML = `Includes wrestlers with ≥${threshold} matches this season. <span class="tooltip-icon" data-tooltip="threshold">→</span>`;
  
  // Initialize tooltip (tooltips.js will handle it via DOMContentLoaded listener)
  // If tooltips.js hasn't loaded yet, trigger initialization manually
  const icon = explainer.querySelector('.tooltip-icon');
  if (icon && typeof addTooltip === 'function' && typeof TOOLTIPS !== 'undefined' && TOOLTIPS.threshold) {
    addTooltip(icon, TOOLTIPS.threshold);
  } else if (icon) {
    // Fallback: wait for tooltips.js to initialize
    setTimeout(() => {
      if (typeof addTooltip === 'function' && typeof TOOLTIPS !== 'undefined' && TOOLTIPS.threshold) {
        addTooltip(icon, TOOLTIPS.threshold);
      }
    }, 100);
  }
}

// Map: wrestler_id -> { weight -> starter_rank }
let starterRankMap = {};

async function loadStarterRankings(season) {
  const weights = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285];
  const map = {};
  let totalLoaded = 0;
  
  // Load starter-only rankings for each weight
  for (const weight of weights) {
    try {
      const url = `/data/rankings/${season}/rankings_starters_${weight}.json`;
      const res = await fetch(url);
      if (!res.ok) {
        console.warn(`Failed to fetch ${url}: ${res.status} ${res.statusText}`);
        continue;
      }
      
      const data = await res.json();
      const rankings = data.rankings || [];
      
      for (const entry of rankings) {
        const wrestlerId = String(entry.wrestler_id || "");
        if (!wrestlerId) continue;
        
        if (!map[wrestlerId]) {
          map[wrestlerId] = {};
        }
        map[wrestlerId][weight] = entry.rank;
        totalLoaded++;
      }
    } catch (err) {
      console.error(`Failed to load starter rankings for ${weight}:`, err);
    }
  }
  
  console.log(`Loaded starter rankings: ${totalLoaded} entries for ${Object.keys(map).length} unique wrestlers`);
  return map;
}

// Global state
let currentWeight = 'all';
let leaderboardData = null;

async function loadLeaderboard() {
  const season = resolveSeason();
  const url = `/data/mat_value/${season}/mat_value_${season}.json`;
  
  // Check for weight filter in URL
  const weightParam = getQueryParam("weight");
  if (weightParam) {
    currentWeight = weightParam === 'all' ? 'all' : parseInt(weightParam);
  }
  
  try {
    // Load starter rankings first
    starterRankMap = await loadStarterRankings(season);
    
    // Then load MV data
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Failed to load ${url}`);
    const data = await res.json();
    leaderboardData = data;
    
    document.getElementById("season-info").textContent = `Season ${season}`;
    
    // Update tabs and explainer
    const updateTabs = () => {
      createWeightTabs('weight-tabs-container', currentWeight, (weight) => {
        currentWeight = weight;
        updateTabs(); // Recreate tabs with new selection to update highlighting
        renderLeaderboard(leaderboardData);
        // Update URL without reload
        const url = new URL(window.location);
        if (weight === 'all') {
          url.searchParams.delete('weight');
        } else {
          url.searchParams.set('weight', weight);
        }
        window.history.pushState({}, '', url);
      });
    };
    updateTabs();
    updateThresholdExplainer('threshold-explainer');
    
    renderLeaderboard(data);
  } catch (err) {
    console.error("Error loading leaderboard:", err);
    document.getElementById("season-info").textContent = "Error loading data";
    const tbody = document.querySelector("#mv-leaderboard-table tbody");
    if (tbody) tbody.innerHTML = "";
  }
}

function createRankBadge(rank) {
  if (rank === null || rank === undefined || rank === "") {
    return document.createTextNode("—");
  }
  
  const badge = document.createElement("span");
  badge.className = "rank-badge";
  
  // Top 5 get accent color, others get muted
  if (rank <= 5) {
    badge.classList.add("top");
  } else {
    badge.classList.add("standard");
  }
  
  badge.textContent = `#${rank}`;
  return badge;
}

function createUNRBadge() {
  const badge = document.createElement("span");
  badge.className = "rank-badge unr-badge";
  badge.textContent = "UNR";
  return badge;
}

function createWtClassRankBadge(rank, isStarter) {
  // If not a starter, show UNR
  if (!isStarter) {
    return createUNRBadge();
  }
  
  if (rank === null || rank === undefined || rank === "") {
    return document.createTextNode("—");
  }
  
  const badge = document.createElement("span");
  badge.className = "rank-badge";
  
  // Only #1 gets colored, all others neutral
  if (rank === 1) {
    badge.classList.add("top");
  } else {
    badge.classList.add("standard");
  }
  
  badge.textContent = `#${rank}`;
  return badge;
}

function createMVRankBadge(rank) {
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

function createMetricBar(value, maxValue) {
  if (value === null || value === undefined || maxValue === 0) {
    return document.createTextNode("—");
  }
  
  // Cap width at 96%
  const width = Math.min((value / maxValue) * 100, 96);
  
  const bar = document.createElement("div");
  bar.className = "metric-bar";
  
  const fill = document.createElement("div");
  fill.className = "metric-bar-fill";
  fill.style.width = `${width}%`;
  
  const valueSpan = document.createElement("span");
  valueSpan.className = "metric-bar-value";
  valueSpan.textContent = value.toFixed(1);
  
  bar.appendChild(fill);
  bar.appendChild(valueSpan);
  return bar;
}

function renderLeaderboard(data) {
  if (!data) return;
  
  const minMatches = getMinMatchThreshold();
  
  // Filter data
  let filtered = data.filter(entry => {
    // Weight filter
    if (currentWeight !== 'all' && entry.weight !== currentWeight) {
      return false;
    }
    // Date-aware minimum matches threshold
    if (entry.matches < minMatches) {
      return false;
    }
    return true;
  });
  
  // Sort by MV (descending), then matches (descending), then current_rank (ascending)
  filtered.sort((a, b) => {
    if (b.mv_avg !== a.mv_avg) return b.mv_avg - a.mv_avg;
    if (b.matches !== a.matches) return b.matches - a.matches;
    const rankA = a.current_rank || 9999;
    const rankB = b.current_rank || 9999;
    return rankA - rankB;
  });
  
  // Note: Bar scaling now uses fixed MAX_ABS_VALUE (6.0) in render logic
  // No need to pre-calculate percentages
  
  // Render table
  const tbody = document.querySelector("#mv-leaderboard-table tbody");
  tbody.innerHTML = "";
  
  filtered.forEach((entry, index) => {
    const tr = document.createElement("tr");
    
    const td = (v) => {
      const c = document.createElement("td");
      c.textContent = safe(v);
      tr.appendChild(c);
    };
    
    // MV Rank: CRITICAL - recompute after filters (1, 2, 3... for filtered results)
    // This is a filtered leaderboard, not a global rank dump
    const mvRank = index + 1;
    const mvRankTd = document.createElement("td");
    mvRankTd.appendChild(createMVRankBadge(mvRank));
    tr.appendChild(mvRankTd);
    
    // Name with link
    const nameTd = document.createElement("td");
    nameTd.className = "name";
    const a = document.createElement("a");
    a.href = `/wrestler.html?id=${entry.wrestler_id}`;
    a.textContent = entry.name;
    nameTd.appendChild(a);
    tr.appendChild(nameTd);
    
    td(entry.team);
    td(entry.weight);
    
    // Wt Class Rank: starter-only ranking with UNR for non-starters
    const wrestlerId = String(entry.wrestler_id || "");
    const weight = entry.weight;
    
    // Look up starter rank for this wrestler at this weight
    const starterRank = starterRankMap[wrestlerId]?.[weight];
    const isStarter = starterRank !== undefined;
    
    const wtClassRankTd = document.createElement("td");
    wtClassRankTd.appendChild(createWtClassRankBadge(starterRank, isStarter));
    tr.appendChild(wtClassRankTd);
    
    // MV with DataGolf-style centered bar
    const mvTd = document.createElement("td");
    mvTd.className = "value-cell col-mv";
    
    if (entry.mv_avg !== null && entry.mv_avg !== undefined) {
      const mvValue = entry.mv_avg;
      const isPositive = mvValue >= 0;
      
      // Create wrapper with data-value and data-sign attributes
      const wrapper = document.createElement("div");
      wrapper.className = "value-bar-wrapper";
      wrapper.setAttribute("data-value", mvValue.toString());
      wrapper.setAttribute("data-sign", isPositive ? "positive" : "negative");
      
      // Zero line (first in DOM) - color based on value sign
      const zeroLine = document.createElement("div");
      zeroLine.className = `zero-line ${isPositive ? 'positive' : 'negative'}`;
      wrapper.appendChild(zeroLine);
      
      // Value bar
      const bar = document.createElement("div");
      bar.className = "value-bar";
      wrapper.appendChild(bar);
      
      // Value label
      const label = document.createElement("div");
      label.className = "value-label";
      wrapper.appendChild(label);
      
      // Calculate bar width and apply styles
      const MAX_ABS_VALUE = 6.0;
      const pct = Math.min(Math.abs(mvValue) / MAX_ABS_VALUE, 1);
      const widthPct = pct * 45; // 45% max each direction
      
      wrapper.style.setProperty('--bar-width', `${widthPct}%`);
      bar.style.width = `${widthPct}%`;
      
      if (isPositive) {
        bar.classList.add('positive');
        label.classList.add('positive');
        label.textContent = `+${mvValue.toFixed(1)}`;
      } else {
        bar.classList.add('negative');
        label.classList.add('negative');
        label.textContent = mvValue.toFixed(1);
      }
      
      mvTd.appendChild(wrapper);
    } else {
      mvTd.textContent = "—";
    }
    tr.appendChild(mvTd);
    
    // Matches - de-emphasized (smaller, muted, right-aligned)
    const matchesTd = document.createElement("td");
    matchesTd.className = "num matches-column";
    matchesTd.textContent = safe(entry.matches);
    tr.appendChild(matchesTd);
    
    tbody.appendChild(tr);
  });
}

// Initialize
document.addEventListener("DOMContentLoaded", () => {
  loadLeaderboard();
});

