// ========================================
// Homepage Renderer (Read-Only, Lightweight)
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

function formatColumnHeader(name) {
  if (!name) return "—";
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  return name.substring(0, 3).toUpperCase();
}

function formatWrestlerName(name) {
  if (!name) return "—";
  return name.trim();
}

// Format name as "F. Lastname" for mobile display
function formatWrestlerNameAbbreviated(name) {
  if (!name) return "—";
  const trimmed = name.trim();
  const parts = trimmed.split(/\s+/);
  if (parts.length < 2) return trimmed; // Single name, return as-is
  const firstInitial = parts[0][0] + ".";
  const lastName = parts[parts.length - 1];
  return `${firstInitial} ${lastName}`;
}

// ========================================
// REUSABLE: Date-aware minimum match threshold (same as leaderboard)
// ========================================
function getMinMatchThreshold() {
  const now = new Date();
  const month = now.getMonth() + 1; // 1-12
  const day = now.getDate();
  
  // Before Dec 1
  if (month < 12) {
    return 3;
  }
  
  // Dec 1 through Dec 14
  if (month === 12 && day < 15) {
    return 4;
  }
  
  // Dec 15 or later
  return 5;
}

// Get cell styling info (reused from matrix.js logic)
function getCellStyleInfo(cellData, rowWrestlerId, colWrestlerId) {
  if (!cellData) {
    return { direction: "neutral", resultType: null, alpha: 1.0, isCO: false };
  }
  
  const cellType = cellData.type || "";
  const results = cellData.results || [];
  
  if (cellType === "SPLIT") {
    return { direction: "split", resultType: "SPLIT", alpha: 0.4, isCO: false };
  } else if (cellType === "COMMON_OPPONENT") {
    const coResult = cellData.co_result || "tie";
    let direction = "neutral";
    if (coResult === "win") direction = "win";
    else if (coResult === "loss") direction = "loss";
    return { direction: direction, resultType: "CO", alpha: 0.09, isCO: true };
  } else if (results.length > 0) {
    const firstResult = results[0];
    const winnerId = firstResult.winner_id;
    const method = firstResult.method || "D";
    
    let direction;
    if (winnerId === rowWrestlerId) direction = "win";
    else if (winnerId === colWrestlerId) direction = "loss";
    else return { direction: "neutral", resultType: null, alpha: 1.0, isCO: false };
    
    let alpha = 0.45;
    if (method === "F" || method === "TF") alpha = 0.85;
    else if (method === "MD") alpha = 0.65;
    
    return { direction: direction, resultType: method, alpha: alpha, isCO: false };
  }
  
  return { direction: "neutral", resultType: null, alpha: 1.0, isCO: false };
}

// Render static matrix (10x10 desktop, 6x6 mobile, no hover, clickable)
function renderStaticMatrix(matrixData, containerId, topN = 10) {
  const container = document.getElementById(containerId);
  if (!container || !matrixData) return;
  
  // Check if mobile to determine how many columns to show
  const isMobile = window.innerWidth <= 500;
  const displayCount = isMobile ? 7 : topN; // 7 rows/columns on mobile, 10 on desktop
  
  const allWrestlers = matrixData.wrestlers || [];
  const wrestlers = allWrestlers.slice(0, displayCount);
  const matrix = matrixData.matrix || {};
  
  container.innerHTML = "";
  
  // Set grid template columns
  // Grid structure: column 0 = corner + row headers, columns 1-N = column headers + matrix cells
  if (isMobile) {
    // Mobile: column 0 (corner 0px + row headers 130px) + 7 matrix columns
    // Note: corner and row headers share column 0, so we need enough width for row headers
    container.style.gridTemplateColumns = `130px repeat(7, minmax(0, 1fr))`;
  } else {
    // Desktop: column 0 (corner 240px + row headers 240px) + 10 matrix columns
    container.style.gridTemplateColumns = `240px repeat(${wrestlers.length}, 40px)`;
  }
  // Set CSS variable for mobile media query
  container.style.setProperty('--col-count', displayCount.toString());
  
  // Mobile-only: Calculate dynamic column widths to fit viewport
  function updateMobileMatrixLayout() {
    if (window.innerWidth > 500) {
      // Desktop: restore default grid
      const container = document.getElementById(containerId);
      if (container && allWrestlers.length >= topN) {
        container.style.gridTemplateColumns = `240px repeat(${topN}, 40px)`;
      }
      return;
    }
    
    const container = document.getElementById(containerId);
    if (!container) return;
    
    // Measure available width (viewport width)
    const viewportWidth = window.innerWidth;
    
    // Name column: 130px max
    const nameColWidth = 130;
    
    // Calculate matrix cell width (remaining space divided by 7)
    const matrixColWidth = Math.max(30, Math.floor((viewportWidth - nameColWidth) / 7));
    
    // Set dynamic grid template (column 0 contains both corner and row headers)
    container.style.gridTemplateColumns = `${nameColWidth}px repeat(7, ${matrixColWidth}px)`;
  }
  
  // Update on initial render and window resize (orientation change)
  if (isMobile) {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        updateMobileMatrixLayout();
      });
    });
    
    // Handle orientation change
    let resizeTimeout;
    window.addEventListener('resize', () => {
      clearTimeout(resizeTimeout);
      resizeTimeout = setTimeout(updateMobileMatrixLayout, 100);
    });
  }
  
  // Always create corner cell for proper grid structure
  // On mobile it will be invisible but still occupies grid position (0,0)
  const corner = document.createElement("div");
  corner.className = "matrix-corner";
  if (isMobile) {
    // On mobile, make it invisible but keep it in grid flow
    corner.style.width = "0";
    corner.style.height = "0";
    corner.style.padding = "0";
    corner.style.margin = "0";
    corner.style.visibility = "hidden";
    corner.style.overflow = "hidden";
  }
  container.appendChild(corner);
  
  // Create column headers (only for displayed wrestlers)
  wrestlers.forEach((wrestler) => {
    const colHeader = document.createElement("div");
    colHeader.className = "matrix-col-header";
    colHeader.textContent = formatColumnHeader(wrestler.name);
    container.appendChild(colHeader);
  });
  
  // Create rows
  wrestlers.forEach((rowWrestler) => {
    // Row header
    const rowHeader = document.createElement("div");
    rowHeader.className = "matrix-row-header";
    
    const rankSpan = document.createElement("span");
    rankSpan.className = "rank";
    rankSpan.textContent = rowWrestler.rank || "—";
    
    const nameSpan = document.createElement("span");
    nameSpan.className = "name";
    nameSpan.textContent = formatWrestlerName(rowWrestler.name);
    // Store abbreviated version for mobile CSS
    nameSpan.setAttribute("data-name-abbreviated", formatWrestlerNameAbbreviated(rowWrestler.name));
    
    rowHeader.appendChild(rankSpan);
    rowHeader.appendChild(nameSpan);
    container.appendChild(rowHeader);
    
    // Create cells for this row
    wrestlers.forEach((colWrestler) => {
      const cell = document.createElement("div");
      cell.className = "matrix-cell";
      
      // Self cell
      if (rowWrestler.id === colWrestler.id) {
        cell.classList.add("self", "cell-self");
        container.appendChild(cell);
        return;
      }
      
      // Get cell data
      const cellData = matrix[rowWrestler.id]?.[colWrestler.id];
      const styleInfo = getCellStyleInfo(cellData, rowWrestler.id, colWrestler.id);
      
      // Set text content (F, TF, DEC, MD, CO, etc.)
      cell.textContent = cellData?.display || "";
      
      // Apply styling
      if (styleInfo.direction === "win") {
        cell.classList.add("cell-win");
        cell.style.setProperty("--alpha", styleInfo.alpha);
      } else if (styleInfo.direction === "loss") {
        cell.classList.add("cell-loss");
        cell.style.setProperty("--alpha", styleInfo.alpha);
      } else if (styleInfo.isCO) {
        cell.classList.add("cell-co");
      } else if (styleInfo.direction === "split") {
        cell.classList.add("cell-split");
      } else {
        cell.classList.add("empty");
      }
      
      container.appendChild(cell);
    });
  });
}

// Load matrix data
async function loadMatrixData(season, weight) {
  const url = `/data/matrix/${season}/${weight}.json`;
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Failed to load ${url}`);
    return await res.json();
  } catch (err) {
    console.error("Error loading matrix data:", err);
    return null;
  }
}

// Load MI data (HOMEPAGE ONLY: weight filter BEFORE cap to 10 wrestlers)
async function loadMIData(weightFilter = 'all') {
  const season = resolveSeason();
  const url = `/data/mat_value/${season}/mat_value_${season}.json`;
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Failed to load ${url}`);
    const allData = await res.json();
    
    // STEP 1: Apply eligibility filter FIRST (same as leaderboard)
    const minMatches = getMinMatchThreshold();
    let filtered = allData.filter(entry => {
      return entry.matches >= minMatches;
    });
    
    // STEP 2: Apply weight filter (if not 'all')
    if (weightFilter !== 'all') {
      const weightNum = parseInt(weightFilter);
      filtered = filtered.filter(entry => entry.weight === weightNum);
    }
    
    // STEP 3: Sort by MV (descending), then matches (descending), then current_rank (ascending)
    filtered.sort((a, b) => {
      if (b.mv_avg !== a.mv_avg) return b.mv_avg - a.mv_avg;
      if (b.matches !== a.matches) return b.matches - a.matches;
      const rankA = a.current_rank || 9999;
      const rankB = b.current_rank || 9999;
      return rankA - rankB;
    });
    
    // STEP 4: Hard limit to 10 wrestlers AFTER filtering (homepage only)
    return filtered.slice(0, 10);
  } catch (err) {
    console.error("Error loading MI data:", err);
    return [];
  }
}

// Load xTP data
async function loadXTPData() {
  const season = resolveSeason();
  const url = `/data/xtp/${season}/xtp_teams_${season}.json`;
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

// Load stat leaderboard
async function loadStatLeaderboard(stat) {
  const url = `/data/leaderboards/${stat}.json`;
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Failed to load ${url}`);
    return await res.json();
  } catch (err) {
    console.error(`Error loading ${stat} data:`, err);
    return [];
  }
}

// Load Hodge Trophy data
async function loadHodgeData() {
  const season = resolveSeason();
  const url = `/data/awards/hodge/${season}/hodge_${season}.json`;
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Failed to load ${url}`);
    return await res.json();
  } catch (err) {
    console.error("Error loading Hodge data:", err);
    return null;
  }
}

// Calculate how many MI rows should be visible based on matrix height
function calculateMIVisibility() {
  const matrixWrapper = document.querySelector(".hero-matrix-wrapper");
  const miWrapper = document.querySelector(".hero-mi-wrapper");
  const miListContainer = document.getElementById("hero-mi-list");
  const miRows = miListContainer?.querySelectorAll(".mi-row");
  
  if (!matrixWrapper || !miWrapper || !miListContainer || !miRows || miRows.length === 0) {
    return;
  }
  
  // Measure matrix wrapper height
  const matrixHeight = matrixWrapper.getBoundingClientRect().height;
  
  // Measure MI wrapper height
  const miWrapperHeight = miWrapper.getBoundingClientRect().height;
  
  // Use matrix height as target
  const targetHeight = Math.min(matrixHeight, miWrapperHeight);
  
  // Measure first MI row height
  const firstRow = miRows[0];
  const miRowHeight = firstRow.getBoundingClientRect().height;
  
  if (targetHeight <= 0 || miRowHeight <= 0) {
    // Fallback: show all rows if measurement fails
    miRows.forEach(row => {
      row.style.display = "";
    });
    return;
  }
  
  // Calculate visible row count based on target height
  // Account for container padding
  const containerPadding = 8; // 4px top + 4px bottom
  const availableHeight = targetHeight - containerPadding;
  const visibleRowCount = Math.floor(availableHeight / miRowHeight);
  
  // Clamp to fetched row count, ensure at least 1 row is visible
  const fetchedRowCount = miRows.length;
  const finalVisibleCount = Math.max(1, Math.min(visibleRowCount, fetchedRowCount));
  
  // Apply visibility (display: none for rows beyond visible count)
  miRows.forEach((row, index) => {
    if (index < finalVisibleCount) {
      row.style.display = "";
    } else {
      row.style.display = "none";
    }
  });
}

// Render MI list (loads up to 10, then dynamically shows only what fits)
function renderMIGlance(data) {
  const container = document.getElementById("hero-mi-list");
  if (!container) return;
  
  container.innerHTML = "";
  
  // Remove any existing divider wrapper
  const existingDividers = container.querySelector('.mi-dividers');
  if (existingDividers) {
    existingDividers.remove();
  }
  
  // Data is already filtered by weight and capped to 10 in loadMIData()
  if (data.length === 0) {
    const emptyRow = document.createElement("div");
    emptyRow.className = "mi-row";
    const emptyCell = document.createElement("div");
    emptyCell.className = "mi-row-name";
    emptyCell.style.gridColumn = "1 / -1";
    emptyCell.style.justifyContent = "center";
    emptyCell.style.color = "var(--muted)";
    emptyCell.textContent = "No eligible wrestlers";
    emptyRow.appendChild(emptyCell);
    container.appendChild(emptyRow);
    return;
  }
  
  // Render all rows (max 10, already filtered)
  data.forEach((entry, index) => {
    const row = document.createElement("div");
    row.className = "mi-row";
    
    // Rank
    const rankDiv = document.createElement("div");
    rankDiv.className = "mi-row-rank";
    rankDiv.textContent = index + 1;
    row.appendChild(rankDiv);
    
    // Name (link)
    const nameDiv = document.createElement("div");
    nameDiv.className = "mi-row-name";
    const a = document.createElement("a");
    a.href = `/wrestler.html?id=${entry.wrestler_id}`;
    a.textContent = entry.name;
    nameDiv.appendChild(a);
    row.appendChild(nameDiv);
    
    // Team
    const teamDiv = document.createElement("div");
    teamDiv.className = "mi-row-team";
    teamDiv.textContent = entry.team || "—";
    row.appendChild(teamDiv);
    
    // MI value
    const valueDiv = document.createElement("div");
    valueDiv.className = "mi-row-value";
    if (entry.mv_avg !== null && entry.mv_avg !== undefined) {
      const sign = entry.mv_avg >= 0 ? "+" : "";
      valueDiv.textContent = `${sign}${entry.mv_avg.toFixed(1)}`;
    } else {
      valueDiv.textContent = "—";
    }
    row.appendChild(valueDiv);
    
    container.appendChild(row);
  });
  
  // Calculate visibility and create dividers after rendering
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      // Measure grid column boundaries
      const firstRank = container.querySelector('.mi-row-rank');
      const firstName = container.querySelector('.mi-row-name');
      const firstTeam = container.querySelector('.mi-row-team');
      
      if (firstRank && firstName && firstTeam) {
        const rankRect = firstRank.getBoundingClientRect();
        const nameRect = firstName.getBoundingClientRect();
        const teamRect = firstTeam.getBoundingClientRect();
        const containerRect = container.getBoundingClientRect();
        
        // Calculate divider positions relative to container
        const divider1 = rankRect.right - containerRect.left; // After rank
        const divider2 = nameRect.right - containerRect.left; // After name
        const divider3 = teamRect.right - containerRect.left; // After team
        
        // Create divider wrapper with three dividers
        const dividersWrapper = document.createElement("div");
        dividersWrapper.className = "mi-dividers";
        dividersWrapper.style.setProperty('--divider-1', `${divider1}px`);
        dividersWrapper.style.setProperty('--divider-2', `${divider2}px`);
        dividersWrapper.style.setProperty('--divider-3', `${divider3}px`);
        
        // Third divider as child element
        const divider3El = document.createElement("div");
        divider3El.className = "mi-divider-3";
        divider3El.style.left = `${divider3}px`;
        dividersWrapper.appendChild(divider3El);
        
        container.appendChild(dividersWrapper);
      }
      
      calculateMIVisibility();
    });
  });
}


// Render xTP glance table
function renderXTPGlance(data) {
  const tbody = document.querySelector("#xtp-glance-table tbody");
  if (!tbody) return;
  
  tbody.innerHTML = "";
  
  const sorted = [...data].sort((a, b) => {
    if (b.team_xTP !== a.team_xTP) return b.team_xTP - a.team_xTP;
    if (b.team_xTP_P !== a.team_xTP_P) return b.team_xTP_P - a.team_xTP_P;
    return a.team.localeCompare(b.team);
  });
  
  const top10 = sorted.slice(0, 10);
  
  top10.forEach((team, index) => {
    const tr = document.createElement("tr");
    
    const rankTd = document.createElement("td");
    rankTd.textContent = index + 1;
    tr.appendChild(rankTd);
    
    const teamTd = document.createElement("td");
    teamTd.className = "name";
    const a = document.createElement("a");
    const teamSlug = teamNameToSlug(team.team);
    a.href = `/team.html?team=${teamSlug}`;
    a.textContent = team.team;
    teamTd.appendChild(a);
    tr.appendChild(teamTd);
    
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

// Render stat leaders table
function renderStatLeaders(data, stat) {
  const tbody = document.querySelector("#stats-table tbody");
  const link = document.getElementById("stat-leaders-link");
  if (!tbody) return;
  
  tbody.innerHTML = "";
  
  // Update link based on selected stat
  if (link) {
    link.href = `/leaderboards/leaderboard_${stat}.html`;
  }
  
  const top10 = data.slice(0, 10);
  
  if (top10.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 4;
    td.style.textAlign = "center";
    td.style.padding = "1em";
    td.style.color = "var(--muted)";
    td.textContent = "No data available";
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }
  
  top10.forEach((entry, index) => {
    const tr = document.createElement("tr");
    
    const rankTd = document.createElement("td");
    rankTd.textContent = index + 1;
    tr.appendChild(rankTd);
    
    const nameTd = document.createElement("td");
    nameTd.className = "name";
    const a = document.createElement("a");
    a.href = `/wrestler.html?id=${entry.wrestler_id}`;
    a.textContent = entry.name;
    nameTd.appendChild(a);
    tr.appendChild(nameTd);
    
    const teamTd = document.createElement("td");
    teamTd.textContent = entry.team || "—";
    tr.appendChild(teamTd);
    
    const statTd = document.createElement("td");
    statTd.className = "num";
    statTd.textContent = entry.count || "—";
    tr.appendChild(statTd);
    
    tbody.appendChild(tr);
  });
}

// Render Hodge Trophy Watch
function renderHodgeGlance(data) {
  const tbody = document.querySelector("#hodge-glance-table tbody");
  if (!tbody || !data || !data.rows) return;
  
  tbody.innerHTML = "";
  
  // Filter to eligible wrestlers only (eligibility already enforced upstream)
  const eligibleRows = data.rows.filter(r => r.eligible);
  
  // Sort by hodge_score descending (already sorted in JSON, but ensure)
  const sorted = [...eligibleRows].sort((a, b) => {
    return (b.hodge_score || 0) - (a.hodge_score || 0);
  });
  
  const top10 = sorted.slice(0, 10);
  
  if (top10.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 4;
    td.style.textAlign = "center";
    td.style.padding = "1em";
    td.style.color = "var(--muted)";
    td.textContent = "No eligible wrestlers";
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }
  
  top10.forEach((row, index) => {
    const tr = document.createElement("tr");
    
    const rankTd = document.createElement("td");
    rankTd.textContent = index + 1;
    tr.appendChild(rankTd);
    
    const nameTd = document.createElement("td");
    nameTd.className = "name";
    const a = document.createElement("a");
    a.href = `/wrestler.html?id=${row.wrestler_id}`;
    a.textContent = row.name;
    nameTd.appendChild(a);
    tr.appendChild(nameTd);
    
    const teamTd = document.createElement("td");
    teamTd.textContent = row.team || "—";
    tr.appendChild(teamTd);
    
    const scoreTd = document.createElement("td");
    scoreTd.className = "num";
    if (row.hodge_score !== null && row.hodge_score !== undefined) {
      scoreTd.textContent = row.hodge_score.toFixed(1);
    } else {
      scoreTd.textContent = "—";
    }
    tr.appendChild(scoreTd);
    
    tbody.appendChild(tr);
  });
}

// Initialize homepage
// Shared state: selectedWeight drives both panels
// Matrix always uses a numeric weight (default 157), never "ALL"
// MI uses selectedWeight directly (can be "ALL" or numeric)
let selectedWeight = "157"; // Shared selector state
let matrixWeight = 157; // Matrix always uses numeric weight
let matrixCache = {};
let miDataCache = {}; // Cache by weight filter

// Update selector visual state (both Matrix and MI use same weight)
function updateSelectorState() {
  const tabs = document.querySelectorAll("#shared-weight-tabs .weight-tab");
  tabs.forEach(tab => {
    const weight = tab.dataset.weight;
    tab.classList.remove("active");
    
    // Both Matrix and MI use the same weight, so just check selectedWeight
    if (weight === selectedWeight) {
      tab.classList.add("active");
    }
  });
}

async function initHomepage() {
  const season = resolveSeason();
  
  // Initialize: Both Matrix and MI default to 157 (no "ALL" on front page)
  selectedWeight = "157"; // MI starts at 157 (same as matrix)
  matrixWeight = 157; // Matrix starts at 157
  
  // Load initial data
  const [miData, xtpData, initialMatrix, hodgeData] = await Promise.all([
    loadMIData("157"), // Load with 157 filter for MI (same as matrix)
    loadXTPData(),
    loadMatrixData(season, 157), // Load 157 for matrix
    loadHodgeData()
  ]);
  
  // Cache MI data and matrix
  miDataCache["157"] = miData;
  matrixCache[157] = initialMatrix;
  
  // Render sections
  renderMIGlance(miData);
  renderXTPGlance(xtpData);
  renderHodgeGlance(hodgeData);
  renderStaticMatrix(initialMatrix, "hero-matrix-grid", 10);
  
  // Update hero matrix link
  const heroLink = document.getElementById("hero-matrix-link");
  if (heroLink) {
    heroLink.href = `/matrix.html?weight=157`;
  }
  
  // Update selector visual state (both Matrix and MI use 157)
  updateSelectorState();
  
  // Initial MI visibility calculation after everything renders
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      calculateMIVisibility();
    });
  });
  
  // Load default stat (pins)
  const pinsData = await loadStatLeaderboard("pins");
  renderStatLeaders(pinsData, "pins");
  
  // Shared weight selector handlers
  const sharedTabs = document.querySelectorAll("#shared-weight-tabs .weight-tab");
  sharedTabs.forEach(tab => {
    tab.addEventListener("click", async () => {
      const weight = tab.dataset.weight;
      
      // Skip if already selected
      if (weight === selectedWeight) return;
      
      // Update both selectedWeight and matrixWeight (no "ALL" option)
      const weightNum = parseInt(weight);
      selectedWeight = weight;
      matrixWeight = weightNum;
      
      // Load matrix if not cached
      if (!matrixCache[weightNum]) {
        const matrixData = await loadMatrixData(season, weightNum);
        if (matrixData) {
          matrixCache[weightNum] = matrixData;
        }
      }
      
      // Render matrix
      if (matrixCache[weightNum]) {
        renderStaticMatrix(matrixCache[weightNum], "hero-matrix-grid", 10);
        
        // Update link
        if (heroLink) {
          heroLink.href = `/matrix.html?weight=${weightNum}`;
        }
      }
      
      // CRITICAL FIX: Always re-query MI data for the selected weight
      // Don't rely on cache - fetch fresh data to avoid showing wrestlers from wrong weight
      const miData = await loadMIData(weight);
      miDataCache[weight] = miData; // Cache for future use
      
      // Re-render MI with fresh data
      renderMIGlance(miData);
      
      // Recalculate MI visibility after both render
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          calculateMIVisibility();
        });
      });
      
      // Update selector visual state
      updateSelectorState();
    });
  });
  
  // Stat tab handlers
  const statTabs = document.querySelectorAll("#stats-tabs .stats-tab");
  statTabs.forEach(tab => {
    tab.addEventListener("click", async () => {
      const stat = tab.dataset.stat;
      
      // Update active tab
      statTabs.forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      
      // Load and render stat
      const statData = await loadStatLeaderboard(stat);
      renderStatLeaders(statData, stat);
    });
  });
  
  // Handle window resize to recalculate MI visibility
  let resizeTimeout = null;
  window.addEventListener('resize', () => {
    if (resizeTimeout) {
      clearTimeout(resizeTimeout);
    }
    resizeTimeout = setTimeout(() => {
      calculateMIVisibility();
    }, 150);
  });
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initHomepage);
} else {
  initHomepage();
}
