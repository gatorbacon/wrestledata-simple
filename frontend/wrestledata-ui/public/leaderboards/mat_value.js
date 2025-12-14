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

async function loadLeaderboard() {
  const season = resolveSeason();
  const url = `/mat_value/${season}/mat_value_${season}.json`;
  
  // Check for weight filter in URL
  const weightParam = getQueryParam("weight");
  if (weightParam) {
    document.getElementById("weight-filter").value = weightParam;
  }
  
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Failed to load ${url}`);
    const data = await res.json();
    
    document.getElementById("season-info").textContent = `Season ${season}`;
    renderLeaderboard(data);
  } catch (err) {
    console.error("Error loading leaderboard:", err);
    document.getElementById("season-info").textContent = "Error loading data";
    const tbody = document.querySelector("#leaderboard-table tbody");
    if (tbody) tbody.innerHTML = "";
  }
}

function renderLeaderboard(data) {
  const weightFilter = document.getElementById("weight-filter").value;
  const minMatches = parseInt(document.getElementById("min-matches-filter").value) || 1;
  
  // Filter data
  let filtered = data.filter(entry => {
    if (weightFilter !== "all" && entry.weight !== parseInt(weightFilter)) {
      return false;
    }
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
  
  // Render table
  const tbody = document.querySelector("#leaderboard-table tbody");
  tbody.innerHTML = "";
  
  filtered.forEach((entry, index) => {
    const tr = document.createElement("tr");
    
    const td = (v) => {
      const c = document.createElement("td");
      c.textContent = safe(v);
      tr.appendChild(c);
    };
    
    // Rank: use weight rank if weight filter is set, otherwise overall rank
    const rank = weightFilter !== "all" 
      ? entry.mv_rank_weight 
      : entry.mv_rank_overall;
    td(rank !== null && rank !== undefined ? `#${rank}` : "—");
    
    // Name with link
    const nameTd = document.createElement("td");
    const a = document.createElement("a");
    a.href = `/wrestler.html?id=${entry.wrestler_id}`;
    a.textContent = entry.name;
    nameTd.appendChild(a);
    tr.appendChild(nameTd);
    
    td(entry.team);
    td(entry.weight);
    td(entry.mv_avg !== null && entry.mv_avg !== undefined ? entry.mv_avg.toFixed(1) : "—");
    td(entry.matches);
    
    tbody.appendChild(tr);
  });
}

// Initialize
document.addEventListener("DOMContentLoaded", () => {
  loadLeaderboard();
  
  // Add event listeners for filters
  document.getElementById("weight-filter").addEventListener("change", () => {
    loadLeaderboard();
  });
  
  document.getElementById("min-matches-filter").addEventListener("change", () => {
    loadLeaderboard();
  });
});

