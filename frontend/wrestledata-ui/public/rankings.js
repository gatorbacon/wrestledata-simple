// ========================================
// Rankings (Traditional) Page
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
async function loadRankingsData(season, weight) {
  try {
    // Load from public_rankings directory
    const url = `/data/public_rankings/${season}/${weight}.json`;
    const response = await fetch(url);
    
    if (!response.ok) {
      throw new Error(`Failed to load rankings: ${response.status}`);
    }
    
    const data = await response.json();
    return data;
  } catch (error) {
    console.error("Error loading rankings data:", error);
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
function renderRankings(data) {
  if (!data || !data.wrestlers || data.wrestlers.length === 0) {
    const tbody = document.querySelector("#rankings-table tbody");
    tbody.innerHTML = `
      <tr>
        <td colspan="7" style="text-align: center; padding: 2em; color: var(--muted);">
          No rankings data available for this weight class.
        </td>
      </tr>
    `;
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
// Update Active Tab
// ========================================
function updateActiveTab(weight) {
  const tabs = document.querySelectorAll('.weight-tab');
  tabs.forEach(tab => {
    const href = tab.getAttribute('href');
    const tabWeight = href.match(/weight=(\d+)/)?.[1];
    if (tabWeight === weight.toString()) {
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
  const season = resolveSeason();
  const weightParam = getQueryParam("weight");
  const validWeights = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285];
  const weight = validWeights.includes(parseInt(weightParam)) ? parseInt(weightParam) : 125;
  
  // Update title
  document.getElementById("rankings-title").textContent = `Rankings — ${weight} lbs`;
  
  // Update active tab
  updateActiveTab(weight);
  
  // Load and render data
  const data = await loadRankingsData(season, weight);
  renderRankings(data);
}

// Initialize on DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initRankings);
} else {
  initRankings();
}

