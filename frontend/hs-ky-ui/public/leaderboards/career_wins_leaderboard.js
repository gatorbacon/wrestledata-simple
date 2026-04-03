// ========================================
// Career Wins Leaderboard
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

function resolveGender() {
  const genderParam = getQueryParam("gender");
  return genderParam || "boys"; // Default to boys
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

function formatWinPercentage(winPct) {
  if (winPct === null || winPct === undefined) {
    return "—";
  }
  // Format: 0.885 -> .885 (remove leading zero)
  return winPct.toFixed(3).replace(/^0\./, '.');
}

// Global state
let leaderboardData = null;

async function loadLeaderboard() {
  const season = resolveSeason();
  const gender = resolveGender();
  const url = `/data/leaderboards/${gender}/${season}/career_wins.json`;
  
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Failed to load ${url}`);
    const data = await res.json();
    leaderboardData = data;
    
    document.getElementById("season-info").textContent = `Season ${season} · ${gender.charAt(0).toUpperCase() + gender.slice(1)}`;
    
    renderLeaderboard(data);
  } catch (err) {
    console.error("Error loading leaderboard:", err);
    document.getElementById("season-info").textContent = "Error loading data";
    const tbody = document.querySelector("#leaderboard-table tbody");
    if (tbody) tbody.innerHTML = "";
  }
}

function renderLeaderboard(data) {
  if (!data || !Array.isArray(data)) return;
  
  // Data is already sorted by career wins (descending)
  // Render table
  const tbody = document.querySelector("#leaderboard-table tbody");
  tbody.innerHTML = "";
  
  data.forEach((entry, index) => {
    const tr = document.createElement("tr");
    
    // Rank: 1, 2, 3... (index + 1)
    const rank = index + 1;
    const rankTd = document.createElement("td");
    rankTd.appendChild(createRankBadge(rank));
    tr.appendChild(rankTd);
    
    // Name with link + state medal emoji
    const nameTd = document.createElement("td");
    nameTd.className = "name";
    const a = document.createElement("a");
    a.href = `/wrestler.html?id=${entry.wrestler_id}`;
    a.textContent = entry.name;
    nameTd.appendChild(a);
    if (entry.state_medals && entry.state_medals.length > 0) {
      const medalMap = { 1: "🥇", 2: "🥈", 3: "🥉" };
      const medalSpan = document.createElement("span");
      medalSpan.className = "state-medals";
      medalSpan.textContent = entry.state_medals.map(p => medalMap[p] || "").join("");
      nameTd.appendChild(medalSpan);
    }
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
    
    // Career Record
    const recordTd = document.createElement("td");
    recordTd.className = "num";
    recordTd.textContent = safe(entry.career_record);
    tr.appendChild(recordTd);
    
    // Winning Percentage
    const winPctTd = document.createElement("td");
    winPctTd.className = "num";
    winPctTd.textContent = formatWinPercentage(entry.win_pct);
    tr.appendChild(winPctTd);
    
    tbody.appendChild(tr);
  });
}

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
  loadLeaderboard();
});

// If DOM already loaded, run immediately
if (document.readyState !== 'loading') {
  loadLeaderboard();
}

