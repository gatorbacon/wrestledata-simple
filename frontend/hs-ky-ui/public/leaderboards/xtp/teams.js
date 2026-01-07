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
  
  // Create wrapper container with two parts: value + bar (value on left, bar on right)
  const wrapper = document.createElement("div");
  wrapper.className = "xtp-bar-wrapper";
  wrapper.style.cssText = "display: flex; align-items: center; gap: 8px; width: 100%;";
  
  // Numeric value (outside bar, right-aligned for consistency)
  const valueSpan = document.createElement("span");
  valueSpan.className = "xtp-value-text";
  valueSpan.style.cssText = "color: #111; font-weight: 600; min-width: 45px; text-align: right; font-variant-numeric: tabular-nums;";
  valueSpan.textContent = value.toFixed(1);
  wrapper.appendChild(valueSpan);
  
  // Bar container (visual only, no text)
  const bar = document.createElement("div");
  bar.className = "metric-bar";
  bar.style.cssText = "flex: 1; position: relative; height: 12px; background: #e9e9e9; border-radius: 0;";
  
  // Cap width at 96%
  const width = Math.min((value / maxValue) * 100, 96);
  
  const fill = document.createElement("div");
  fill.className = "metric-bar-fill";
  fill.style.cssText = `position: absolute; left: 0; top: 0; bottom: 0; width: ${width}%; background: var(--accent-primary); opacity: 0.75; border-radius: 0;`;
  
  bar.appendChild(fill);
  wrapper.appendChild(bar);
  
  return wrapper;
}

// Note: hs_config.js must be loaded before this file

function teamNameToSlug(teamName) {
  if (!teamName) return "";
  let slug = teamName.toLowerCase();
  slug = slug.replace(/\s+/g, "_");
  slug = slug.replace(/[^\w_]/g, "");
  slug = slug.replace(/_+/g, "_");
  slug = slug.replace(/^_+|_+$/g, "");
  return slug;
}

let teamData = [];
let expandedTeam = null;
let currentGender = 'boys';
let currentWeights = [];

async function loadLeaderboard() {
  // Get context from URL
  currentGender = getGenderFromURL();
  const season = getSeasonFromURL();
  currentWeights = getWeightsForGender(currentGender);
  
  const url = buildXTPURL(currentGender, season);
  console.log(`[HS xTP] Loading data from: ${url}`);
  
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status} - ${res.statusText}`);
    const data = await res.json();
    
    console.log(`[HS xTP] Loaded ${data?.teams?.length || 0} teams for ${currentGender}`);
    
    const seasonEl = document.getElementById("season-info");
    if (seasonEl) {
      seasonEl.textContent = `Season ${season} — ${currentGender.charAt(0).toUpperCase() + currentGender.slice(1)}`;
    }
    
    teamData = data.teams || [];
    renderLeaderboard();
  } catch (err) {
    console.error(`[HS xTP] Error loading data from ${url}:`, err);
    const seasonEl = document.getElementById("season-info");
    if (seasonEl) {
      seasonEl.textContent = `Error loading ${currentGender} data`;
    }
    const tbody = document.querySelector("#xtp-team-leaderboard-table tbody");
    if (tbody) {
      tbody.innerHTML = `
        <tr>
          <td colspan="7" style="text-align: center; padding: 2em; color: var(--muted);">
            HS data not found for ${currentGender}.<br>
            <small style="color: var(--muted-2);">Check console for fetch details.</small>
          </td>
        </tr>
      `;
    }
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
    const teamURL = buildPageURL('team.html', currentGender, { team: teamSlug });
    teamLink.href = teamURL.startsWith('/') ? teamURL : `/${teamURL}`;
    teamLink.textContent = team.team;
    teamTd.appendChild(teamLink);
    tr.appendChild(teamTd);
    
    // xTP (total) - primary metric with bar (value outside bar)
    const xtpTd = document.createElement("td");
    xtpTd.className = "value-cell col-xtp";
    
    if (team.team_xTP !== null && team.team_xTP !== undefined) {
      const xtpValue = team.team_xTP;
      
      // Create wrapper with value + bar layout (value outside bar)
      const wrapper = document.createElement("div");
      wrapper.className = "xtp-bar-wrapper";
      wrapper.style.cssText = "display: flex; align-items: center; gap: 8px; width: 100%;";
      
      // Numeric value (outside bar, right-aligned)
      const valueSpan = document.createElement("span");
      valueSpan.className = "xtp-value-text";
      valueSpan.style.cssText = "color: #111; font-weight: 600; min-width: 50px; text-align: right; font-variant-numeric: tabular-nums; font-size: 0.875rem;";
      valueSpan.textContent = `+${xtpValue.toFixed(1)}`;
      wrapper.appendChild(valueSpan);
      
      // Bar container (visual only, no text)
      const barContainer = document.createElement("div");
      barContainer.style.cssText = "flex: 1; position: relative; height: 14px; background: #e9e9e9; border-radius: 0;";
      
      // Calculate bar width (scale relative to table max)
      const MAX_ABS_VALUE = maxXTP > 0 ? maxXTP : 100.0;
      const pct = Math.min(Math.abs(xtpValue) / MAX_ABS_VALUE, 1);
      const widthPct = Math.min(pct * 100, 96); // Cap at 96%
      
      const barFill = document.createElement("div");
      barFill.style.cssText = `position: absolute; left: 0; top: 0; bottom: 0; width: ${widthPct}%; background: var(--accent-primary); opacity: 0.75; border-radius: 0;`;
      barContainer.appendChild(barFill);
      
      wrapper.appendChild(barContainer);
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
      ["Weight", "Wrestler", "Rank", "Expected Team Points", "xTP_P", "xTP_A", "xTP_B"].forEach(header => {
        const th = document.createElement("th");
        th.textContent = header;
        headerRow.appendChild(th);
      });
      thead.appendChild(headerRow);
      breakdownTable.appendChild(thead);
      
      // Body
      const tbody2 = document.createElement("tbody");
      
      // Sort weights ascending (use current gender's weights)
      const sortedWeights = currentWeights.map(w => String(w));
      
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
        
        // Weight column (wide enough for "Weight")
        const weightTd = document.createElement("td");
        weightTd.className = "weight-col-expanded";
        weightTd.style.cssText = "width: 70px; min-width: 70px; max-width: 70px;";
        weightTd.textContent = weight;
        row.appendChild(weightTd);
        
        if (weightData && weightData.wrestler_id) {
          // Wrestler name (clickable, 50% wider than before: 140px -> 210px)
          const wrestlerTd = document.createElement("td");
          wrestlerTd.className = "wrestler-col-expanded";
          wrestlerTd.style.cssText = "width: 210px; min-width: 210px; max-width: 210px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;";
          const wrestlerLink = document.createElement("a");
          const wrestlerURL = buildPageURL('wrestler.html', currentGender, { id: weightData.wrestler_id });
          wrestlerLink.href = wrestlerURL.startsWith('/') ? wrestlerURL : `/${wrestlerURL}`;
          wrestlerLink.textContent = weightData.name || "Unknown";
          wrestlerTd.appendChild(wrestlerLink);
          row.appendChild(wrestlerTd);
          
          // Rank - medal badge (just wide enough for "RANK" and badges)
          const rankTd = document.createElement("td");
          rankTd.className = "rank-col-expanded";
          rankTd.style.cssText = "width: 65px; min-width: 65px; max-width: 65px;";
          if (weightData.rank !== null && weightData.rank !== undefined) {
            rankTd.appendChild(createMVRankBadge(weightData.rank));
          } else {
            rankTd.textContent = "—";
          }
          row.appendChild(rankTd);
          
          // xTP (total) - primary metric with bar (expanded rows, value left of bar)
          // Uses remaining space (flexible width)
          const xtpTd = document.createElement("td");
          xtpTd.className = "num metric-primary expanded-xtp-cell";
          xtpTd.style.cssText = "padding: 6px 12px;";
          
          if (weightData.xTP !== null && weightData.xTP !== undefined) {
            // Scale bars relative to max xTP in THIS team's expanded rows
            xtpTd.appendChild(createMetricBar(weightData.xTP, expandedMaxXTP));
          } else {
            // No qualifier - show "—" with same layout
            const zeroWrapper = document.createElement("div");
            zeroWrapper.className = "xtp-bar-wrapper";
            zeroWrapper.style.cssText = "display: flex; align-items: center; gap: 8px; width: 100%;";
            const zeroValue = document.createElement("span");
            zeroValue.className = "xtp-value-text";
            zeroValue.style.cssText = "color: #111; font-weight: 600; min-width: 45px; text-align: right; font-variant-numeric: tabular-nums;";
            zeroValue.textContent = "—";
            zeroWrapper.appendChild(zeroValue);
            xtpTd.appendChild(zeroWrapper);
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

