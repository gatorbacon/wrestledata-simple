function safe(v, fn) {
  if (v === null || v === undefined || v === "") return "—";
  return fn ? fn(v) : v;
}

function resolveSeason() {
  return "2026"; // Or make dynamic later
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

const WEIGHTS = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285];

let teamData = [];
let expandedTeam = null;

async function loadLeaderboard() {
  const season = resolveSeason();
  const url = `/xtp/${season}/xtp_teams_${season}.json`;
  
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Failed to load ${url}`);
    const data = await res.json();
    
    document.getElementById("season-info").textContent = `Season ${season}`;
    teamData = data.teams || [];
    renderLeaderboard();
  } catch (err) {
    console.error("Error loading leaderboard:", err);
    document.getElementById("season-info").textContent = "Error loading data";
    const tbody = document.querySelector("#leaderboard-table tbody");
    if (tbody) tbody.innerHTML = "";
  }
}

function renderLeaderboard() {
  // Sort teams: xTP desc, xTP_P desc, team name asc
  const sorted = [...teamData].sort((a, b) => {
    if (b.team_xTP !== a.team_xTP) return b.team_xTP - a.team_xTP;
    if (b.team_xTP_P !== a.team_xTP_P) return b.team_xTP_P - a.team_xTP_P;
    return a.team.localeCompare(b.team);
  });
  
  const tbody = document.querySelector("#leaderboard-table tbody");
  tbody.innerHTML = "";
  
  sorted.forEach((team, index) => {
    const rank = index + 1;
    const isExpanded = expandedTeam === team.team;
    
    // Main team row
    const tr = document.createElement("tr");
    tr.className = `expandable-row ${isExpanded ? "expanded" : "collapsed"}`;
    tr.dataset.team = team.team;
    
    // Expand icon
    const expandTd = document.createElement("td");
    const expandIcon = document.createElement("span");
    expandIcon.className = "expand-icon";
    expandTd.appendChild(expandIcon);
    tr.appendChild(expandTd);
    
    // Rank
    const rankTd = document.createElement("td");
    rankTd.textContent = rank;
    tr.appendChild(rankTd);
    
    // Team name (clickable)
    const teamTd = document.createElement("td");
    const teamLink = document.createElement("a");
    const teamSlug = teamNameToSlug(team.team);
    teamLink.href = `/team.html?team=${teamSlug}`;
    teamLink.textContent = team.team;
    teamTd.appendChild(teamLink);
    tr.appendChild(teamTd);
    
    // xTP (total, bold)
    const xtpTd = document.createElement("td");
    xtpTd.className = "xtp-total";
    xtpTd.textContent = safe(team.team_xTP, v => v.toFixed(1));
    tr.appendChild(xtpTd);
    
    // xTP_P
    const xtpPTd = document.createElement("td");
    xtpPTd.className = "xtp-component";
    xtpPTd.textContent = safe(team.team_xTP_P, v => v.toFixed(1));
    tr.appendChild(xtpPTd);
    
    // xTP_A
    const xtpATd = document.createElement("td");
    xtpATd.className = "xtp-component";
    xtpATd.textContent = safe(team.team_xTP_A, v => v.toFixed(1));
    tr.appendChild(xtpATd);
    
    // xTP_B
    const xtpBTd = document.createElement("td");
    xtpBTd.className = "xtp-component";
    xtpBTd.textContent = safe(team.team_xTP_B, v => v.toFixed(1));
    tr.appendChild(xtpBTd);
    
    tbody.appendChild(tr);
    
    // Click handler for expansion
    tr.addEventListener("click", (e) => {
      // Don't expand if clicking on team link
      if (e.target.tagName === "A") {
        return;
      }
      
      // Toggle expansion
      if (expandedTeam === team.team) {
        expandedTeam = null;
      } else {
        expandedTeam = team.team;
      }
      renderLeaderboard();
    });
    
    // Also make expand icon clickable
    expandIcon.addEventListener("click", (e) => {
      e.stopPropagation();
      if (expandedTeam === team.team) {
        expandedTeam = null;
      } else {
        expandedTeam = team.team;
      }
      renderLeaderboard();
    });
    
    // Weight breakdown row (expanded)
    if (isExpanded) {
      const breakdownTr = document.createElement("tr");
      breakdownTr.className = "weight-breakdown expanded";
      
      const breakdownTd = document.createElement("td");
      breakdownTd.colSpan = 7;
      
      // Create nested table
      const breakdownTable = document.createElement("table");
      
      // Header
      const thead = document.createElement("thead");
      const headerRow = document.createElement("tr");
      ["Weight", "Wrestler", "Rank", "xTP", "xTP_P", "xTP_A", "xTP_B"].forEach(header => {
        const th = document.createElement("th");
        th.textContent = header;
        headerRow.appendChild(th);
      });
      thead.appendChild(headerRow);
      breakdownTable.appendChild(thead);
      
      // Body
      const tbody2 = document.createElement("tbody");
      
      // Sort weights ascending
      const sortedWeights = WEIGHTS.map(w => String(w));
      
      sortedWeights.forEach(weight => {
        const weightData = team.weights?.[weight];
        const row = document.createElement("tr");
        
        // Weight
        const weightTd = document.createElement("td");
        weightTd.textContent = weight;
        row.appendChild(weightTd);
        
        if (weightData && weightData.wrestler_id) {
          // Wrestler name (clickable)
          const wrestlerTd = document.createElement("td");
          const wrestlerLink = document.createElement("a");
          wrestlerLink.href = `/wrestler.html?id=${weightData.wrestler_id}`;
          wrestlerLink.textContent = weightData.name || "Unknown";
          wrestlerTd.appendChild(wrestlerLink);
          row.appendChild(wrestlerTd);
          
          // Rank
          const rankTd = document.createElement("td");
          rankTd.textContent = safe(weightData.rank, v => `#${v}`);
          row.appendChild(rankTd);
          
          // xTP (total)
          const xtpTd = document.createElement("td");
          xtpTd.textContent = safe(weightData.xTP, v => v.toFixed(1));
          row.appendChild(xtpTd);
          
          // xTP_P
          const xtpPTd = document.createElement("td");
          xtpPTd.textContent = safe(weightData.xTP_P, v => v.toFixed(1));
          row.appendChild(xtpPTd);
          
          // xTP_A
          const xtpATd = document.createElement("td");
          xtpATd.textContent = safe(weightData.xTP_A, v => v.toFixed(1));
          row.appendChild(xtpATd);
          
          // xTP_B
          const xtpBTd = document.createElement("td");
          xtpBTd.textContent = safe(weightData.xTP_B, v => v.toFixed(1));
          row.appendChild(xtpBTd);
        } else {
          // No qualifier
          const noQualTd = document.createElement("td");
          noQualTd.className = "no-qualifier";
          noQualTd.colSpan = 6;
          noQualTd.textContent = "—";
          row.appendChild(noQualTd);
        }
        
        tbody2.appendChild(row);
      });
      
      breakdownTable.appendChild(tbody2);
      breakdownTd.appendChild(breakdownTable);
      breakdownTr.appendChild(breakdownTd);
      tbody.appendChild(breakdownTr);
    }
  });
}

// Initialize
document.addEventListener("DOMContentLoaded", () => {
  loadLeaderboard();
});

