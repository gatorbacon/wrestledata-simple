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

async function loadStandings() {
  // Get context from URL
  currentGender = getGenderFromURL();
  const season = getSeasonFromURL();
  
  const url = `/data/dual_standings/${currentGender}/${season}/dual_standings.json`;
  console.log(`[Dual Rankings] Loading data from: ${url}`);
  
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status} - ${res.statusText}`);
    const data = await res.json();
    
    console.log(`[Dual Rankings] Loaded ${data?.length || 0} teams for ${currentGender}`);
    
    standingsData = data || [];
    
    const seasonEl = document.getElementById("season-info");
    if (seasonEl) {
      seasonEl.textContent = `Season ${season} — ${currentGender.charAt(0).toUpperCase() + currentGender.slice(1)}`;
    }
    
    renderStandings();
  } catch (err) {
    console.error("Error loading dual standings:", err);
    const seasonEl = document.getElementById("season-info");
    if (seasonEl) {
      seasonEl.textContent = "Error loading data";
    }
    const tbody = document.querySelector("#standings-table tbody");
    if (tbody) tbody.innerHTML = "";
  }
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
    
    // Rank
    const rankTd = document.createElement("td");
    rankTd.appendChild(createRankBadge(entry.rank));
    tr.appendChild(rankTd);
    
    // Team (with link)
    const teamTd = document.createElement("td");
    teamTd.className = "name";
    const teamLink = document.createElement("a");
    teamLink.href = `/team.html?team=${entry.team_slug}`;
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

