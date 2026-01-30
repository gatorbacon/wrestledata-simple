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

async function loadTeamTournamentRankings(gender, season, dropId) {
  // Try archive first
  const archiveUrl = `/data/rankings/${gender}/${season}/team/tournament/drops/${dropId}.json`;
  try {
    const response = await fetch(`${archiveUrl}?t=${Date.now()}`, { cache: 'no-store' });
    if (response.ok) {
      const data = await response.json();
      return data;
    }
  } catch (error) {
    console.error(`Error loading archived team tournament rankings:`, error);
  }
  
  // Fallback to latest.json
  const latestUrl = `/data/rankings/${gender}/${season}/team/tournament/latest.json`;
  try {
    const response = await fetch(`${latestUrl}?t=${Date.now()}`, { cache: 'no-store' });
    if (response.ok) {
      return await response.json();
    }
  } catch (error) {
    console.error(`Error loading latest team tournament rankings:`, error);
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
  if (delta > 0) return `▲ +${delta}`;
  return `▼ ${delta}`;
}

async function loadLeaderboard() {
  // Get context from URL
  currentGender = getGenderFromURL();
  const season = getSeasonFromURL();
  currentWeights = getWeightsForGender(currentGender);
  const dropIdParam = getQueryParam('drop');
  
  // Load archive index to determine which drop to use
  const index = await loadTeamRankingsArchiveIndex(currentGender, season);
  const dropId = dropIdParam || (index?.latest) || null;
  currentDrop = dropId;
  
  // Try to load from archive
  let rankingsData = null;
  if (dropId) {
    rankingsData = await loadTeamTournamentRankings(currentGender, season, dropId);
  }
  
  // Fallback to legacy xTP file if no archive data
  if (!rankingsData) {
    const url = buildXTPURL(currentGender, season);
    console.log(`[HS xTP] Loading data from: ${url}`);
    
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status} - ${res.statusText}`);
      const data = await res.json();
      
      console.log(`[HS xTP] Loaded ${data?.teams?.length || 0} teams for ${currentGender}`);
      
      // Convert legacy format to rankings format
      teamData = (data.teams || []).map((team, idx) => ({
        rank: idx + 1,
        team: team.team,
        points: team.team_xTP_simple || team.team_xTP || 0.0,
        prev_rank: null,
        delta: null
      }));
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
      return;
    }
  } else {
    // Use archive data
    teamData = rankingsData.rankings || [];
    
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
  
  renderLeaderboard();
}

function renderLeaderboard() {
  // Sort teams by rank (already sorted from archive, or sort by points)
  const sorted = [...teamData].sort((a, b) => {
    if (a.rank !== undefined && b.rank !== undefined) {
      return a.rank - b.rank;
    }
    // Fallback: sort by points
    const aPoints = a.points || 0;
    const bPoints = b.points || 0;
    if (bPoints !== aPoints) return bPoints - aPoints;
    return a.team.localeCompare(b.team);
  });
  
  // Calculate max xTP_simple for bar scaling (per-table, like MV)
  const maxXTP = sorted.length > 0 
    ? Math.max(...sorted.map(t => t.points || t.team_xTP_simple || t.team_xTP || 0))
    : 0;
  
  const tbody = document.querySelector("#xtp-team-leaderboard-table tbody");
  tbody.innerHTML = "";
  
  sorted.forEach((team, index) => {
    const rank = team.rank || (index + 1);
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
    
    // Rank with medal badge and delta
    const rankTd = document.createElement("td");
    rankTd.style.cssText = "display: flex; align-items: center; gap: 8px;";
    rankTd.appendChild(createMVRankBadge(rank));
    
    // Add delta indicator if available
    if (team.delta !== null && team.delta !== undefined) {
      const deltaSpan = document.createElement("span");
      deltaSpan.style.cssText = "font-size: 0.75rem; color: var(--muted);";
      const deltaText = formatDelta(team.delta);
      if (deltaText && deltaText !== "—") {
        if (team.delta > 0) {
          deltaSpan.style.color = "var(--success)";
        } else if (team.delta < 0) {
          deltaSpan.style.color = "var(--error)";
        }
        deltaSpan.textContent = deltaText;
        rankTd.appendChild(deltaSpan);
      } else if (team.prev_rank === null) {
        const newSpan = document.createElement("span");
        newSpan.style.cssText = "font-size: 0.75rem; color: #0066CC;";
        newSpan.textContent = "NEW";
        rankTd.appendChild(newSpan);
      }
    }
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
    
    // Points (primary) - simplified rank-based scoring with bar
    const xtpTd = document.createElement("td");
    xtpTd.className = "value-cell col-xtp";
    
    // Use points from archive, or fall back to legacy fields
    const primaryScore = team.points !== null && team.points !== undefined
      ? team.points
      : (team.team_xTP_simple !== null && team.team_xTP_simple !== undefined 
        ? team.team_xTP_simple 
        : team.team_xTP);
    
    if (primaryScore !== null && primaryScore !== undefined) {
      const xtpValue = primaryScore;
      
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
      breakdownTd.colSpan = 4;
      breakdownTd.style.paddingLeft = "0"; // Remove extra padding from nested table
      
      // Create nested table
      const breakdownTable = document.createElement("table");
      
      // Header
      const thead = document.createElement("thead");
      const headerRow = document.createElement("tr");
      ["Weight", "Wrestler", "Rank", "Projected Pts"].forEach(header => {
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
      
      // Calculate max xTP_simple for expanded rows in THIS team (for bar scaling)
      const teamXTPValues = sortedWeights
        .map(w => team.weights?.[w]?.xTP_simple || team.weights?.[w]?.xTP)
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
          
          // xTP_simple (primary) - simplified rank-based scoring with bar (expanded rows)
          // Uses remaining space (flexible width)
          const xtpTd = document.createElement("td");
          xtpTd.className = "num metric-primary expanded-xtp-cell";
          xtpTd.style.cssText = "padding: 6px 12px;";
          
          // Use xTP_simple as primary, fall back to xTP for backward compatibility
          const weightScore = weightData.xTP_simple !== null && weightData.xTP_simple !== undefined 
            ? weightData.xTP_simple 
            : weightData.xTP;
          
          if (weightScore !== null && weightScore !== undefined) {
            // Scale bars relative to max xTP_simple in THIS team's expanded rows
            xtpTd.appendChild(createMetricBar(weightScore, expandedMaxXTP));
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
        } else {
          // No qualifier
          const noQualTd = document.createElement("td");
          noQualTd.className = "no-qualifier";
          noQualTd.colSpan = 3;
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

