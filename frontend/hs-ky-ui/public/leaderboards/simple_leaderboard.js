// ========================================
// Simple Leaderboard (Pins, Techs, Majors, Wins)
// ========================================

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
// REUSABLE: Weight tabs component (from mat_value.js)
// ========================================
function createWeightTabs(containerId, selectedWeight, onWeightChange) {
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

// Global state
let currentWeight = 'all';
let leaderboardData = null;
let config = null;

async function loadLeaderboard(config) {
  const season = resolveSeason();
  const url = `/data/leaderboards/${config.statType}.json`;
  
  // Check for weight filter in URL
  const weightParam = getQueryParam("weight");
  if (weightParam) {
    currentWeight = weightParam === 'all' ? 'all' : parseInt(weightParam);
  }
  
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Failed to load ${url}`);
    const data = await res.json();
    leaderboardData = data;
    
    document.getElementById(config.seasonInfoId).textContent = `Season ${season} · All Divisions`;
    
    // Update tabs
    const updateTabs = () => {
      createWeightTabs(config.containerId, currentWeight, (weight) => {
        currentWeight = weight;
        updateTabs();
        renderLeaderboard(leaderboardData, config);
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
    
    renderLeaderboard(data, config);
  } catch (err) {
    console.error("Error loading leaderboard:", err);
    document.getElementById(config.seasonInfoId).textContent = "Error loading data";
    const tbody = document.querySelector(`#${config.tableId} tbody`);
    if (tbody) tbody.innerHTML = "";
  }
}

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

function renderLeaderboard(data, config) {
  if (!data) return;
  
  // Filter data by weight
  let filtered = data.filter(entry => {
    if (currentWeight !== 'all' && entry.weight !== currentWeight) {
      return false;
    }
    return true;
  });
  
  // Sort by count descending, then by name ascending
  filtered.sort((a, b) => {
    if (b.count !== a.count) return b.count - a.count;
    return a.name.localeCompare(b.name);
  });
  
  // Render table
  const tbody = document.querySelector(`#${config.tableId} tbody`);
  tbody.innerHTML = "";
  
  filtered.forEach((entry, index) => {
    const tr = document.createElement("tr");
    
    const td = (v) => {
      const c = document.createElement("td");
      c.textContent = safe(v);
      tr.appendChild(c);
    };
    
    // Rank: recompute after filters (1, 2, 3... for filtered results)
    const rank = index + 1;
    const rankTd = document.createElement("td");
    rankTd.appendChild(createRankBadge(rank));
    tr.appendChild(rankTd);
    
    // Name with link
    const nameTd = document.createElement("td");
    nameTd.className = "name";
    const a = document.createElement("a");
    a.href = `/wrestler.html?id=${entry.wrestler_id}`;
    a.textContent = entry.name;
    nameTd.appendChild(a);
    tr.appendChild(nameTd);
    
    // Team with link
    const teamTd = document.createElement("td");
    const teamLink = document.createElement("a");
    // Generate team slug: lowercase, replace spaces with underscores, remove punctuation
    let teamSlug = entry.team.toLowerCase();
    teamSlug = teamSlug.replace(/\s+/g, '_');
    teamSlug = teamSlug.replace(/[^\w_]/g, '');
    teamSlug = teamSlug.replace(/_+/g, '_');
    teamSlug = teamSlug.replace(/^_+|_+$/g, '');
    teamLink.href = `/team.html?team=${teamSlug}`;
    teamLink.textContent = entry.team;
    teamTd.appendChild(teamLink);
    tr.appendChild(teamTd);
    
    td(entry.weight);
    
    // Count
    const countTd = document.createElement("td");
    countTd.className = "num";
    countTd.textContent = entry.count;
    tr.appendChild(countTd);
    
    tbody.appendChild(tr);
  });
}

// Initialize function
function initSimpleLeaderboard(cfg) {
  config = cfg;
  
  // Set page title
  document.title = cfg.title;
  
  // Load leaderboard data
  document.addEventListener("DOMContentLoaded", () => {
    loadLeaderboard(config);
  });
  
  // If DOM already loaded, run immediately
  if (document.readyState !== 'loading') {
    loadLeaderboard(config);
  }
}

