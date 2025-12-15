function safe(v, fn) {
  if (v === null || v === undefined || v === "") return "—";
  return fn ? fn(v) : v;
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
    const tbody = document.querySelector("#xtp-team-leaderboard-table tbody");
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
  
  // Calculate max xTP for bar scaling (per-table, like MV)
  const maxXTP = sorted.length > 0 
    ? Math.max(...sorted.map(t => t.team_xTP || 0))
    : 0;
  
  const tbody = document.querySelector("#xtp-team-leaderboard-table tbody");
  tbody.innerHTML = "";
  
  sorted.forEach((team, index) => {
    const rank = index + 1;
    const isExpanded = expandedTeam === team.team;
    
    // Main team row (matching MV leaderboard row structure)
    const tr = document.createElement("tr");
    tr.className = `expandable-row ${isExpanded ? "expanded" : "collapsed"}`;
    tr.dataset.team = team.team;
    // Row background matches page (no boxed panel look)
    
    // Expand icon
    const expandTd = document.createElement("td");
    const expandIcon = document.createElement("span");
    expandIcon.className = "expand-icon";
    expandTd.appendChild(expandIcon);
    tr.appendChild(expandTd);
    
    // Rank with medal badge (matching MV leaderboard)
    const rankTd = document.createElement("td");
    rankTd.appendChild(createMVRankBadge(rank));
    tr.appendChild(rankTd);
    
    // Team name (clickable)
    const teamTd = document.createElement("td");
    teamTd.className = "name";
    const teamLink = document.createElement("a");
    const teamSlug = teamNameToSlug(team.team);
    teamLink.href = `/team.html?team=${teamSlug}`;
    teamLink.textContent = team.team;
    teamTd.appendChild(teamLink);
    tr.appendChild(teamTd);
    
    // xTP (total) - primary metric with DataGolf-style centered bar (always positive)
    const xtpTd = document.createElement("td");
    xtpTd.className = "value-cell col-xtp";
    
    if (team.team_xTP !== null && team.team_xTP !== undefined) {
      const xtpValue = team.team_xTP;
      
      // Create wrapper with data-value and data-sign attributes (always positive for xTP)
      const wrapper = document.createElement("div");
      wrapper.className = "value-bar-wrapper";
      wrapper.setAttribute("data-value", xtpValue.toString());
      wrapper.setAttribute("data-sign", "positive");
      
      // Zero line (first in DOM) - always green for xTP (positive)
      const zeroLine = document.createElement("div");
      zeroLine.className = "zero-line positive";
      wrapper.appendChild(zeroLine);
      
      // Value bar
      const bar = document.createElement("div");
      bar.className = "value-bar";
      wrapper.appendChild(bar);
      
      // Value label
      const label = document.createElement("div");
      label.className = "value-label";
      wrapper.appendChild(label);
      
      // Calculate bar width and apply styles (scale relative to table max)
      // For xTP, we scale relative to the maximum value in the current table
      const MAX_ABS_VALUE = maxXTP > 0 ? maxXTP : 100.0;
      const pct = Math.min(Math.abs(xtpValue) / MAX_ABS_VALUE, 1);
      const widthPct = pct * 45; // 45% max each direction (same as MV)
      
      wrapper.style.setProperty('--bar-width', `${widthPct}%`);
      bar.style.width = `${widthPct}%`;
      
      // xTP is always positive
      bar.classList.add('positive');
      label.classList.add('positive');
      label.textContent = `+${xtpValue.toFixed(1)}`;
      
      xtpTd.appendChild(wrapper);
    } else {
      xtpTd.textContent = "—";
    }
    tr.appendChild(xtpTd);
    
    // xTP_P - subcomponent
    const xtpPTd = document.createElement("td");
    xtpPTd.className = "num metric-sub xtp-component-col";
    xtpPTd.textContent = safe(team.team_xTP_P, v => v.toFixed(1));
    tr.appendChild(xtpPTd);
    
    // xTP_A - subcomponent
    const xtpATd = document.createElement("td");
    xtpATd.className = "num metric-sub xtp-component-col";
    xtpATd.textContent = safe(team.team_xTP_A, v => v.toFixed(1));
    tr.appendChild(xtpATd);
    
    // xTP_B - subcomponent
    const xtpBTd = document.createElement("td");
    xtpBTd.className = "num metric-sub xtp-component-col";
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
      breakdownTd.style.paddingLeft = "0"; // Remove extra padding from nested table
      
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
      
      // Calculate max xTP for expanded rows in THIS team (for bar scaling)
      const teamXTPValues = sortedWeights
        .map(w => team.weights?.[w]?.xTP)
        .filter(v => v !== null && v !== undefined);
      const expandedMaxXTP = teamXTPValues.length > 0
        ? Math.max(...teamXTPValues)
        : (maxXTP > 0 ? maxXTP : 100.0);
      
      sortedWeights.forEach(weight => {
        const weightData = team.weights?.[weight];
        const row = document.createElement("tr");
        row.className = "xtp-expanded-row";
        
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
          
          // Rank - medal badge (expanded rows only)
          const rankTd = document.createElement("td");
          if (weightData.rank !== null && weightData.rank !== undefined) {
            rankTd.appendChild(createMVRankBadge(weightData.rank));
          } else {
            rankTd.textContent = "—";
          }
          row.appendChild(rankTd);
          
          // xTP (total) - primary metric with bar (expanded rows, same as collapsed)
          const xtpTd = document.createElement("td");
          xtpTd.className = "num metric-primary expanded-xtp-cell";
          
          if (weightData.xTP !== null && weightData.xTP !== undefined) {
            // Scale bars relative to max xTP in THIS team's expanded rows
            xtpTd.appendChild(createMetricBar(weightData.xTP, expandedMaxXTP));
          } else {
            xtpTd.textContent = "—";
          }
          row.appendChild(xtpTd);
          
          // xTP_P - subcomponent (shrunk, muted in expanded rows)
          const xtpPTd = document.createElement("td");
          xtpPTd.className = "num metric-sub expanded-component-col xtp-sub";
          xtpPTd.textContent = safe(weightData.xTP_P, v => v.toFixed(1));
          row.appendChild(xtpPTd);
          
          // xTP_A - subcomponent (shrunk, muted in expanded rows)
          const xtpATd = document.createElement("td");
          xtpATd.className = "num metric-sub expanded-component-col xtp-sub";
          xtpATd.textContent = safe(weightData.xTP_A, v => v.toFixed(1));
          row.appendChild(xtpATd);
          
          // xTP_B - subcomponent (shrunk, muted in expanded rows)
          const xtpBTd = document.createElement("td");
          xtpBTd.className = "num metric-sub expanded-component-col xtp-sub";
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

