// ========================================
// Rankings (Traditional) Page
// ========================================
// Note: hs_config.js must be loaded before this file

function safe(v, fn) {
  if (v === null || v === undefined || v === "") return "—";
  return fn ? fn(v) : v;
}

function getQueryParam(key) {
  return new URLSearchParams(window.location.search).get(key);
}

// ========================================
// MV Rank Badge
// ========================================
function createMVRankBadge(rank) {
  if (rank === null || rank === undefined || rank === "") {
    return document.createTextNode("—");
  }
  
  const badge = document.createElement("span");
  badge.className = "rank-badge";
  
  // Medal badge styling: #1 gold, #2 silver, #3 bronze, others neutral
  if (rank === 1) {
    badge.classList.add("medal-gold");
  } else if (rank === 2) {
    badge.classList.add("medal-silver");
  } else if (rank === 3) {
    badge.classList.add("medal-bronze");
  } else {
    badge.classList.add("standard");
  }
  
  badge.textContent = `#${rank}`;
  return badge;
}

// ========================================
// Zero-Center MV Bar
// ========================================
function createZeroCenterMVBar(mvValue) {
  if (mvValue === null || mvValue === undefined) {
    return document.createTextNode("—");
  }
  
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
  
  return wrapper;
}

// ========================================
// Format Win-Loss Record
// ========================================
function formatWinLoss(record) {
  if (!record || record.wins === null || record.wins === undefined || record.losses === null || record.losses === undefined) {
    return "—";
  }
  
  // Use record_str if available, otherwise format from record object
  if (record.record_str) {
    return record.record_str;
  }
  
  const wins = record.wins;
  const losses = record.losses;
  const total = wins + losses;
  
  if (total === 0) {
    return "0–0 (—)";
  }
  
  const winPct = ((wins / total) * 100).toFixed(1);
  return `${wins}–${losses} (${winPct}%)`;
}

// ========================================
// Format Bonus Rate
// ========================================
function formatBonusRate(bonusPct) {
  if (bonusPct === null || bonusPct === undefined) {
    return "—";
  }
  
  // bonus_pct is already 0..1 format
  const pct = bonusPct * 100;
  return `${pct.toFixed(1)}%`;
}

// ========================================
// Team Name to Slug
// ========================================
function teamNameToSlug(teamName) {
  if (!teamName) return "";
  return teamName.toLowerCase()
    .replace(/\s+/g, '_')
    .replace(/[^a-z0-9_]/g, '');
}

// ========================================
// Load Rankings Data
// ========================================
async function loadRankingsData(gender, season, weight) {
  const url = buildRankingsURL(gender, season, weight);
  console.log(`[HS Rankings] Loading data from: ${url}`);
  
  try {
    const response = await fetch(`${url}?t=${Date.now()}`, { cache: 'no-store' });
    
    if (!response.ok) {
      throw new Error(`Failed to load rankings: ${response.status} - ${response.statusText}`);
    }
    
    const data = await response.json();
    console.log(`[HS Rankings] Loaded ${data?.wrestlers?.length || 0} wrestlers for ${gender} ${weight} lbs`);
    return data;
  } catch (error) {
    console.error(`[HS Rankings] Error loading data from ${url}:`, error);
    return null;
  }
}

// ========================================
// Compute MV Rank
// ========================================
function computeMVRank(wrestlers) {
  // Sort by MV descending
  const sorted = [...wrestlers].sort((a, b) => {
    const mvA = a.mv || 0;
    const mvB = b.mv || 0;
    if (mvB !== mvA) return mvB - mvA;
    // Tie-break by rank if available
    const rankA = a.rank || 9999;
    const rankB = b.rank || 9999;
    return rankA - rankB;
  });
  
  // Assign MV ranks
  sorted.forEach((wrestler, index) => {
    wrestler.mv_rank = index + 1;
  });
  
  return wrestlers;
}

// ========================================
// Render Rankings Table
// ========================================
function renderRankings(data, gender, weight) {
  if (!data || !data.wrestlers || data.wrestlers.length === 0) {
    const tbody = document.querySelector("#rankings-table tbody");
    tbody.innerHTML = `
      <tr>
        <td colspan="7" style="text-align: center; padding: 2em; color: var(--muted);">
          HS data not found for ${gender} ${weight} lbs.<br>
          <small style="color: var(--muted-2);">Check console for fetch details.</small>
        </td>
      </tr>
    `;
    console.warn(`[HS Rankings] No data returned for ${gender} ${weight} lbs`);
    return;
  }
  
  // Wrestlers are already in correct order from rankings file
  // No need to sort or recompute MV rank
  let wrestlers = data.wrestlers;
  
  const tbody = document.querySelector("#rankings-table tbody");
  tbody.innerHTML = "";
  
  wrestlers.forEach((wrestler) => {
    const tr = document.createElement("tr");
    
    // Rank
    const rankTd = document.createElement("td");
    rankTd.textContent = safe(wrestler.rank);
    tr.appendChild(rankTd);
    
    // Name (link to wrestler profile)
    const nameTd = document.createElement("td");
    nameTd.className = "name";
    if (wrestler.wrestler_id) {
      const nameLink = document.createElement("a");
      nameLink.href = `/wrestler.html?id=${wrestler.wrestler_id}`;
      nameLink.textContent = safe(wrestler.name);
      nameTd.appendChild(nameLink);
    } else {
      nameTd.textContent = safe(wrestler.name);
    }
    tr.appendChild(nameTd);
    
    // Team (link to team profile)
    const teamTd = document.createElement("td");
    teamTd.className = "name";
    if (wrestler.team) {
      const teamLink = document.createElement("a");
      const teamSlug = teamNameToSlug(wrestler.team);
      teamLink.href = `/team.html?team=${teamSlug}`;
      teamLink.textContent = wrestler.team;
      teamTd.appendChild(teamLink);
    } else {
      teamTd.textContent = "—";
    }
    tr.appendChild(teamTd);
    
    // W–L Record
    const recordTd = document.createElement("td");
    recordTd.textContent = formatWinLoss(wrestler.record);
    tr.appendChild(recordTd);
    
    // Bonus %
    const bonusTd = document.createElement("td");
    bonusTd.className = "num";
    bonusTd.textContent = formatBonusRate(wrestler.bonus_pct);
    tr.appendChild(bonusTd);
    
    // MV Score + Bar
    const mvTd = document.createElement("td");
    mvTd.className = "value-cell col-mv";
    if (wrestler.mv && wrestler.mv.value !== null && wrestler.mv.value !== undefined) {
      mvTd.appendChild(createZeroCenterMVBar(wrestler.mv.value));
    } else {
      mvTd.textContent = "—";
    }
    tr.appendChild(mvTd);
    
    // MV Rank Badge
    const mvRankTd = document.createElement("td");
    if (wrestler.mv && wrestler.mv.weight_rank !== null && wrestler.mv.weight_rank !== undefined) {
      mvRankTd.appendChild(createMVRankBadge(wrestler.mv.weight_rank));
    } else {
      mvRankTd.textContent = "—";
    }
    tr.appendChild(mvRankTd);
    
    tbody.appendChild(tr);
  });
}

// ========================================
// Generate Weight Tabs
// ========================================
function generateWeightTabs(gender, weights) {
  const container = document.getElementById('weight-tabs');
  if (!container) return;
  
  container.innerHTML = '';
  
  weights.forEach(weight => {
    const tab = document.createElement('a');
    tab.className = 'weight-tab';
    tab.href = buildPageURL('rankings.html', gender, { weight });
    tab.textContent = weight.toString();
    container.appendChild(tab);
  });
}

// ========================================
// Update Active Tab
// ========================================
function updateActiveTab(gender, weight) {
  const tabs = document.querySelectorAll('.weight-tab');
  tabs.forEach(tab => {
    const href = tab.getAttribute('href');
    const tabWeight = href.match(/weight=(\d+)/)?.[1];
    const tabGender = href.match(/gender=(\w+)/)?.[1];
    
    if (tabWeight === weight.toString() && tabGender === gender) {
      tab.classList.add('active');
    } else {
      tab.classList.remove('active');
    }
  });
}

// ========================================
// Initialize Rankings Page
// ========================================
async function initRankings() {
  // Get context from URL
  const gender = getGenderFromURL();
  const season = getSeasonFromURL();
  const weight = getWeightFromURL(gender);
  const weights = getWeightsForGender(gender);
  
  console.log(`[HS Rankings] Initializing: gender=${gender}, season=${season}, weight=${weight}`);
  
  // Generate weight tabs dynamically
  generateWeightTabs(gender, weights);
  
  // Update title
  const titleEl = document.getElementById("rankings-title");
  if (titleEl) {
    titleEl.textContent = `Rankings — ${gender.charAt(0).toUpperCase() + gender.slice(1)} ${weight} lbs`;
  }
  
  // Update season info
  const seasonEl = document.getElementById("season-info");
  if (seasonEl) {
    seasonEl.textContent = `Season ${season}`;
  }
  
  // Update active tab
  updateActiveTab(gender, weight);
  
  // Load and render data
  const data = await loadRankingsData(gender, season, weight);
  renderRankings(data, gender, weight);
}

// Initialize on DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initRankings);
} else {
  initRankings();
}

