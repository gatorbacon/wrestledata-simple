// ========================================
// Dashboard Homepage
// ========================================

function safe(v, fn) {
  if (v === null || v === undefined || v === "") return "—";
  return fn ? fn(v) : v;
}

function resolveSeason() {
  return "2026";
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

function createMVRankBadge(rank) {
  if (rank === null || rank === undefined || rank === "") {
    return document.createTextNode("—");
  }
  
  const badge = document.createElement("span");
  badge.className = "rank-badge";
  
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

// Load MV leaderboard data
async function loadMVData() {
  const season = resolveSeason();
  const url = `/mat_value/${season}/mat_value_${season}.json`;
  
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Failed to load ${url}`);
    const data = await res.json();
    return data;
  } catch (err) {
    console.error("Error loading MV data:", err);
    return [];
  }
}

// Load xTP team data
async function loadXTPData() {
  const season = resolveSeason();
  const url = `/xtp/${season}/xtp_teams_${season}.json`;
  
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Failed to load ${url}`);
    const data = await res.json();
    return data.teams || [];
  } catch (err) {
    console.error("Error loading xTP data:", err);
    return [];
  }
}

// Render MV Preview (top 5)
function renderMVPreview(data) {
  const tbody = document.querySelector("#mv-preview-table tbody");
  if (!tbody) return;
  
  tbody.innerHTML = "";
  
  // Filter and sort
  const filtered = data.filter(entry => entry.matches >= 3);
  filtered.sort((a, b) => {
    if (b.mv_avg !== a.mv_avg) return b.mv_avg - a.mv_avg;
    if (b.matches !== a.matches) return b.matches - a.matches;
    return (a.current_rank || 9999) - (b.current_rank || 9999);
  });
  
  const top5 = filtered.slice(0, 5);
  
  top5.forEach((entry, index) => {
    const tr = document.createElement("tr");
    
    // Rank
    const rankTd = document.createElement("td");
    rankTd.appendChild(createMVRankBadge(index + 1));
    tr.appendChild(rankTd);
    
    // Wrestler name (link)
    const nameTd = document.createElement("td");
    nameTd.className = "name";
    const a = document.createElement("a");
    a.href = `/wrestler.html?id=${entry.wrestler_id}`;
    a.textContent = entry.name;
    nameTd.appendChild(a);
    tr.appendChild(nameTd);
    
    // Team
    const teamTd = document.createElement("td");
    teamTd.textContent = entry.team || "—";
    tr.appendChild(teamTd);
    
    // MV (numeric only, no bar)
    const mvTd = document.createElement("td");
    mvTd.className = "num";
    if (entry.mv_avg !== null && entry.mv_avg !== undefined) {
      const sign = entry.mv_avg >= 0 ? "+" : "";
      mvTd.textContent = `${sign}${entry.mv_avg.toFixed(1)}`;
    } else {
      mvTd.textContent = "—";
    }
    tr.appendChild(mvTd);
    
    tbody.appendChild(tr);
  });
}

// Render xTP Preview (top 5)
function renderXTPPreview(data) {
  const tbody = document.querySelector("#xtp-preview-table tbody");
  if (!tbody) return;
  
  tbody.innerHTML = "";
  
  // Sort teams
  const sorted = [...data].sort((a, b) => {
    if (b.team_xTP !== a.team_xTP) return b.team_xTP - a.team_xTP;
    if (b.team_xTP_P !== a.team_xTP_P) return b.team_xTP_P - a.team_xTP_P;
    return a.team.localeCompare(b.team);
  });
  
  const top5 = sorted.slice(0, 5);
  
  top5.forEach((team, index) => {
    const tr = document.createElement("tr");
    
    // Rank
    const rankTd = document.createElement("td");
    rankTd.appendChild(createMVRankBadge(index + 1));
    tr.appendChild(rankTd);
    
    // Team name (link)
    const teamTd = document.createElement("td");
    teamTd.className = "name";
    const a = document.createElement("a");
    const teamSlug = teamNameToSlug(team.team);
    a.href = `/team.html?team=${teamSlug}`;
    a.textContent = team.team;
    teamTd.appendChild(a);
    tr.appendChild(teamTd);
    
    // xTP (numeric only)
    const xtpTd = document.createElement("td");
    xtpTd.className = "num";
    if (team.team_xTP !== null && team.team_xTP !== undefined) {
      xtpTd.textContent = team.team_xTP.toFixed(1);
    } else {
      xtpTd.textContent = "—";
    }
    tr.appendChild(xtpTd);
    
    tbody.appendChild(tr);
  });
}

// Render Featured MV (top 8-10)
function renderFeaturedMV(data) {
  const tbody = document.querySelector("#featured-mv-table tbody");
  if (!tbody) return;
  
  tbody.innerHTML = "";
  
  // Filter and sort
  const filtered = data.filter(entry => entry.matches >= 3);
  filtered.sort((a, b) => {
    if (b.mv_avg !== a.mv_avg) return b.mv_avg - a.mv_avg;
    if (b.matches !== a.matches) return b.matches - a.matches;
    return (a.current_rank || 9999) - (b.current_rank || 9999);
  });
  
  const top10 = filtered.slice(0, 10);
  
  top10.forEach((entry, index) => {
    const tr = document.createElement("tr");
    
    // Rank
    const rankTd = document.createElement("td");
    rankTd.appendChild(createMVRankBadge(index + 1));
    tr.appendChild(rankTd);
    
    // Wrestler name (link)
    const nameTd = document.createElement("td");
    nameTd.className = "name";
    const a = document.createElement("a");
    a.href = `/wrestler.html?id=${entry.wrestler_id}`;
    a.textContent = entry.name;
    nameTd.appendChild(a);
    tr.appendChild(nameTd);
    
    // Team
    const teamTd = document.createElement("td");
    teamTd.textContent = entry.team || "—";
    tr.appendChild(teamTd);
    
    // MV (numeric only)
    const mvTd = document.createElement("td");
    mvTd.className = "num";
    if (entry.mv_avg !== null && entry.mv_avg !== undefined) {
      const sign = entry.mv_avg >= 0 ? "+" : "";
      mvTd.textContent = `${sign}${entry.mv_avg.toFixed(1)}`;
    } else {
      mvTd.textContent = "—";
    }
    tr.appendChild(mvTd);
    
    tbody.appendChild(tr);
  });
}

// Render Trending Wrestlers (top 5 by MV)
function renderTrending(data) {
  const tbody = document.querySelector("#trending-table tbody");
  if (!tbody) return;
  
  tbody.innerHTML = "";
  
  // Filter and sort
  const filtered = data.filter(entry => entry.matches >= 3);
  filtered.sort((a, b) => {
    if (b.mv_avg !== a.mv_avg) return b.mv_avg - a.mv_avg;
    if (b.matches !== a.matches) return b.matches - a.matches;
    return (a.current_rank || 9999) - (b.current_rank || 9999);
  });
  
  const top5 = filtered.slice(0, 5);
  
  top5.forEach((entry) => {
    const tr = document.createElement("tr");
    
    // Wrestler name (link)
    const nameTd = document.createElement("td");
    nameTd.className = "name";
    const a = document.createElement("a");
    a.href = `/wrestler.html?id=${entry.wrestler_id}`;
    a.textContent = entry.name;
    nameTd.appendChild(a);
    tr.appendChild(nameTd);
    
    // Team
    const teamTd = document.createElement("td");
    teamTd.textContent = entry.team || "—";
    tr.appendChild(teamTd);
    
    // MV (numeric only)
    const mvTd = document.createElement("td");
    mvTd.className = "num";
    if (entry.mv_avg !== null && entry.mv_avg !== undefined) {
      const sign = entry.mv_avg >= 0 ? "+" : "";
      mvTd.textContent = `${sign}${entry.mv_avg.toFixed(1)}`;
    } else {
      mvTd.textContent = "—";
    }
    tr.appendChild(mvTd);
    
    tbody.appendChild(tr);
  });
}

// Render Ranking Matrix Preview (149 lbs, top 8)
function renderMatrixPreview(data) {
  const tbody = document.querySelector("#matrix-preview-table tbody");
  if (!tbody) return;
  
  tbody.innerHTML = "";
  
  // Filter to 149 lbs only
  const filtered = data.filter(entry => entry.weight === 149 && entry.matches >= 3);
  filtered.sort((a, b) => {
    if (b.mv_avg !== a.mv_avg) return b.mv_avg - a.mv_avg;
    if (b.matches !== a.matches) return b.matches - a.matches;
    return (a.current_rank || 9999) - (b.current_rank || 9999);
  });
  
  const top8 = filtered.slice(0, 8);
  
  top8.forEach((entry, index) => {
    const tr = document.createElement("tr");
    
    // Rank
    const rankTd = document.createElement("td");
    rankTd.appendChild(createMVRankBadge(index + 1));
    tr.appendChild(rankTd);
    
    // Wrestler name (link)
    const nameTd = document.createElement("td");
    nameTd.className = "name";
    const a = document.createElement("a");
    a.href = `/wrestler.html?id=${entry.wrestler_id}`;
    a.textContent = entry.name;
    nameTd.appendChild(a);
    tr.appendChild(nameTd);
    
    // MV (numeric only)
    const mvTd = document.createElement("td");
    mvTd.className = "num";
    if (entry.mv_avg !== null && entry.mv_avg !== undefined) {
      const sign = entry.mv_avg >= 0 ? "+" : "";
      mvTd.textContent = `${sign}${entry.mv_avg.toFixed(1)}`;
    } else {
      mvTd.textContent = "—";
    }
    tr.appendChild(mvTd);
    
    tbody.appendChild(tr);
  });
}

// Initialize dashboard
async function initDashboard() {
  // Load data
  const [mvData, xtpData] = await Promise.all([
    loadMVData(),
    loadXTPData()
  ]);
  
  // Render all sections
  renderMVPreview(mvData);
  renderXTPPreview(xtpData);
  renderFeaturedMV(mvData);
  renderTrending(mvData);
  renderMatrixPreview(mvData);
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initDashboard);
} else {
  initDashboard();
}

