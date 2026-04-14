// ========================================
// Dual Rankings Leaderboard
// ========================================

function safe(v, fn) {
  if (v === null || v === undefined || v === "") return "—";
  return fn ? fn(v) : v;
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

function teamNameToSlug(teamName) {
  if (!teamName) return "";
  let slug = teamName.toLowerCase();
  slug = slug.replace(/\s+/g, "_");
  slug = slug.replace(/[^\w_]/g, "");
  slug = slug.replace(/_+/g, "_");
  slug = slug.replace(/^_+|_+$/g, "");
  return slug;
}

let standingsData = [];
let currentGender = 'boys';
let currentDrop = null;

function getQueryParam(key) {
  return new URLSearchParams(window.location.search).get(key);
}

function formatPublishedDate(publishedAt) {
  if (!publishedAt) return "";
  try {
    const date = new Date(publishedAt);
    return date.toLocaleDateString('en-US', { 
      year: 'numeric', 
      month: 'long', 
      day: 'numeric' 
    });
  } catch (e) {
    return publishedAt;
  }
}

// Format Date from ID (YYYY-MM-DD format) to avoid timezone issues
function formatDateFromId(dateId) {
  if (!dateId) return "";
  try {
    // Parse YYYY-MM-DD format directly as local date to avoid timezone issues
    const parts = dateId.split('-');
    if (parts.length === 3) {
      const year = parseInt(parts[0], 10);
      const month = parseInt(parts[1], 10) - 1; // JS months are 0-indexed
      const day = parseInt(parts[2], 10);
      const date = new Date(year, month, day);
      return date.toLocaleDateString('en-US', { 
        year: 'numeric', 
        month: 'long', 
        day: 'numeric' 
      });
    }
    return dateId;
  } catch (e) {
    return dateId;
  }
}

async function loadTeamRankingsArchiveIndex(gender, season) {
  const url = `/data/rankings/${gender}/${season}/index.json`;
  try {
    const response = await fetch(`${url}?t=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) return null;
    return await response.json();
  } catch (error) {
    console.error(`Error loading team rankings archive index:`, error);
    return null;
  }
}

async function loadDualRankings(gender, season, dropId) {
  // Try archive first
  const archiveUrl = `/data/rankings/${gender}/${season}/team/dual/drops/${dropId}.json`;
  try {
    const response = await fetch(`${archiveUrl}?t=${Date.now()}`, { cache: 'no-store' });
    if (response.ok) {
      const data = await response.json();
      return data;
    }
  } catch (error) {
    console.error(`Error loading archived dual rankings:`, error);
  }
  
  // Fallback to latest.json
  const latestUrl = `/data/rankings/${gender}/${season}/team/dual/latest.json`;
  try {
    const response = await fetch(`${latestUrl}?t=${Date.now()}`, { cache: 'no-store' });
    if (response.ok) {
      return await response.json();
    }
  } catch (error) {
    console.error(`Error loading latest dual rankings:`, error);
  }
  
  return null;
}

function renderDropSelector(drops, currentDrop, gender, season) {
  const selectorContainer = document.getElementById('drop-selector-container');
  if (!selectorContainer) return;
  
  if (!drops || drops.length <= 1) {
    selectorContainer.style.display = 'none';
    return;
  }
  
  selectorContainer.style.display = 'block';
  const select = document.getElementById('drop-selector');
  if (!select) return;
  
  select.innerHTML = '';
  
  drops.forEach(drop => {
    const option = document.createElement('option');
    option.value = drop.id;
    // Use id field for display to avoid timezone conversion issues
    option.textContent = formatDateFromId(drop.id);
    if (drop.id === currentDrop) {
      option.selected = true;
    }
    select.appendChild(option);
  });
  
  select.addEventListener('change', (e) => {
    const newDrop = e.target.value;
    const url = new URL(window.location);
    url.searchParams.set('drop', newDrop);
    window.location.href = url.toString();
  });
}

function formatDelta(delta) {
  if (delta === null || delta === undefined) return null;
  if (delta === 0) return "—";
  if (delta > 0) return `▲${delta}`;
  return `▼${Math.abs(delta)}`;
}

async function loadStandings() {
  // Get context from URL
  currentGender = getGenderFromURL();
  const season = getSeasonFromURL();
  const dropIdParam = getQueryParam('drop');
  
  // Load archive index to determine which drop to use
  const index = await loadTeamRankingsArchiveIndex(currentGender, season);
  const dropId = dropIdParam || (index?.latest) || null;
  currentDrop = dropId;
  
  // Try to load from archive
  let rankingsData = null;
  if (dropId) {
    rankingsData = await loadDualRankings(currentGender, season, dropId);
  }
  
  // Fallback to legacy dual_standings.json if no archive data
  if (!rankingsData) {
    const url = `/data/dual_standings/${currentGender}/${season}/dual_standings.json`;
    console.log(`[Dual Rankings] Loading data from: ${url}`);
    
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status} - ${res.statusText}`);
      const data = await res.json();
      
      console.log(`[Dual Rankings] Loaded ${data?.length || 0} teams for ${currentGender}`);
      
      // Convert legacy format to rankings format
      standingsData = (data || []).map(entry => ({
        rank: entry.rank,
        team: entry.team,
        team_slug: entry.team_slug,
        wins: entry.wins,
        losses: entry.losses,
        ties: entry.ties,
        point_diff: entry.point_diff,
        win_pct: entry.win_pct,
        prev_rank: null,
        delta: null
      }));
    } catch (err) {
      console.error("Error loading dual standings:", err);
      const seasonEl = document.getElementById("season-info");
      if (seasonEl) {
        seasonEl.textContent = "Error loading data";
      }
      const tbody = document.querySelector("#standings-table tbody");
      if (tbody) tbody.innerHTML = "";
      return;
    }
  } else {
    // Use archive data
    standingsData = rankingsData.rankings || [];
    
    // Update season info with published date
    const seasonEl = document.getElementById("season-info");
    if (seasonEl) {
      // Use dropId for display to avoid timezone conversion issues
      const publishedDate = formatDateFromId(dropId);
      seasonEl.textContent = `Published ${publishedDate} — ${currentGender.charAt(0).toUpperCase() + currentGender.slice(1)}`;
    }
    
    // Render drop selector
    if (index) {
      renderDropSelector(index.drops, dropId, currentGender, season);
    }
  }
  
  renderStandings();
}

function renderStandings() {
  const tbody = document.querySelector("#standings-table tbody");
  if (!tbody) return;
  
  tbody.innerHTML = "";
  
  if (!standingsData || standingsData.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 5;
    td.textContent = "No standings data available";
    td.style.textAlign = "center";
    td.style.padding = "2em";
    td.style.color = "var(--muted)";
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }
  
  standingsData.forEach((entry) => {
    const tr = document.createElement("tr");
    
    // Rank with delta
    const rankTd = document.createElement("td");
    rankTd.style.cssText = "display: flex; align-items: center; gap: 8px;";
    rankTd.appendChild(createRankBadge(entry.rank));
    
    // Add delta indicator if available
    if (entry.delta !== null && entry.delta !== undefined) {
      const deltaSpan = document.createElement("span");
      deltaSpan.style.cssText = "font-size: 0.85em; font-weight: 600;";
      const deltaText = formatDelta(entry.delta);
      if (deltaText && deltaText !== "—") {
        if (entry.delta > 0) {
          deltaSpan.style.color = "#22c55e";
        } else if (entry.delta < 0) {
          deltaSpan.style.color = "#ef4444";
        }
        deltaSpan.textContent = deltaText;
        rankTd.appendChild(deltaSpan);
      } else if (entry.prev_rank === null) {
        const newSpan = document.createElement("span");
        newSpan.style.cssText = "font-size: 0.75rem; color: #0066CC;";
        newSpan.textContent = "NEW";
        rankTd.appendChild(newSpan);
      }
    }
    tr.appendChild(rankTd);
    
    // Team (with link) — archive JSON has "team" but may not have "team_slug"; derive slug if missing
    const teamTd = document.createElement("td");
    teamTd.className = "name";
    const teamLink = document.createElement("a");
    const teamSlug = entry.team_slug || teamNameToSlug(entry.team);
    teamLink.href = `/team.html?team=${teamSlug}`;
    teamLink.textContent = entry.team;
    teamTd.appendChild(teamLink);
    tr.appendChild(teamTd);
    
    // Record
    const recordTd = document.createElement("td");
    recordTd.style.textAlign = "center";
    recordTd.style.fontVariantNumeric = "tabular-nums";
    const recordText = entry.ties > 0 
      ? `${entry.wins}–${entry.losses}–${entry.ties}`
      : `${entry.wins}–${entry.losses}`;
    recordTd.textContent = recordText;
    tr.appendChild(recordTd);
    
    // Point Differential
    const pdTd = document.createElement("td");
    pdTd.style.textAlign = "center";
    pdTd.style.fontVariantNumeric = "tabular-nums";
    pdTd.textContent = entry.point_diff >= 0 ? `+${entry.point_diff}` : `${entry.point_diff}`;
    if (entry.point_diff > 0) {
      pdTd.style.color = "var(--success)";
    } else if (entry.point_diff < 0) {
      pdTd.style.color = "var(--error)";
    }
    tr.appendChild(pdTd);
    
    // Win Percentage
    const winPctTd = document.createElement("td");
    winPctTd.style.textAlign = "center";
    winPctTd.style.fontVariantNumeric = "tabular-nums";
    winPctTd.textContent = entry.win_pct ? entry.win_pct.toFixed(3) : "0.000";
    tr.appendChild(winPctTd);
    
    tbody.appendChild(tr);
  });
}

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
  loadStandings();
  
  // Update dual predictor link with gender parameter
  const dualPredictorLink = document.getElementById("dual-predictor-link");
  if (dualPredictorLink) {
    const gender = getGenderFromURL();
    dualPredictorLink.href = `/dual_predictor.html?gender=${gender}`;
  }
});

// If DOM already loaded, run immediately
if (document.readyState !== 'loading') {
  loadStandings();
  
  // Update dual predictor link with gender parameter
  const dualPredictorLink = document.getElementById("dual-predictor-link");
  if (dualPredictorLink) {
    const gender = getGenderFromURL();
    dualPredictorLink.href = `/dual_predictor.html?gender=${gender}`;
  }
}

