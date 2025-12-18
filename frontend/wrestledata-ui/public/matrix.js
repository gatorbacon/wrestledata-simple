// ========================================
// Rankings Matrix Renderer
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

// Load matrix data
async function loadMatrixData(season, weight) {
  const url = `/matrix/${season}/public_matrix_${season}_${weight}.json`;
  
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Failed to load ${url}`);
    const data = await res.json();
    return data;
  } catch (err) {
    console.error("Error loading matrix data:", err);
    return null;
  }
}

// Get cell styling info (row-relative, authoritative)
function getCellStyleInfo(cellData, rowWrestlerId, colWrestlerId) {
  if (!cellData) {
    return {
      direction: "neutral",
      resultType: null,
      alpha: 1.0,
      isCO: false
    };
  }
  
  const cellType = cellData.type || "";
  const results = cellData.results || [];
  
  if (cellType === "SPLIT") {
    return {
      direction: "split",
      resultType: "SPLIT",
      alpha: 0.4,
      isCO: false
    };
  } else if (cellType === "COMMON_OPPONENT") {
    // CO: determine direction from co_result
    const coResult = cellData.co_result || "tie";
    let direction = "neutral";
    
    if (coResult === "win") {
      direction = "win";
    } else if (coResult === "loss") {
      direction = "loss";
    }
    
    return {
      direction: direction,
      resultType: "CO",
      alpha: 0.09,
      isCO: true
    };
  } else if (results.length > 0) {
    // Direct matchup: check winner_id at render time
    const firstResult = results[0];
    const winnerId = firstResult.winner_id;
    const method = firstResult.method || "D";
    
    // Determine direction from row wrestler's perspective
    let direction;
    if (winnerId === rowWrestlerId) {
      direction = "win";
    } else if (winnerId === colWrestlerId) {
      direction = "loss";
    } else {
      return {
        direction: "neutral",
        resultType: null,
        alpha: 1.0,
        isCO: false
      };
    }
    
    // Determine alpha based on method (opacity-based strategy)
    let alpha = 0.45; // Default for D/TB/SV
    if (method === "F" || method === "TF") {
      alpha = 0.85;
    } else if (method === "MD") {
      alpha = 0.65;
    }
    
    return {
      direction: direction,
      resultType: method,
      alpha: alpha,
      isCO: false
    };
  }
  
  // Default
  return {
    direction: "neutral",
    resultType: null,
    alpha: 1.0,
    isCO: false
  };
}

// Create tooltip content for a cell
function createTooltipContent(cellData, rowWrestler, colWrestler) {
  if (!cellData) {
    return null;
  }
  
  const cellType = cellData.type || "";
  const results = cellData.results || [];
  
  if (cellType === "COMMON_OPPONENT") {
    const coResult = cellData.co_result || "tie";
    if (coResult === "win") {
      return `Common Opponent Advantage<br/>${rowWrestler.name} has better common opponent results than ${colWrestler.name}`;
    } else if (coResult === "loss") {
      return `Common Opponent Disadvantage<br/>${colWrestler.name} has better common opponent results than ${rowWrestler.name}`;
    } else {
      return `Common Opponent<br/>No clear advantage between ${rowWrestler.name} and ${colWrestler.name}`;
    }
  }
  
  if (cellType === "SPLIT") {
    let html = `<strong>${rowWrestler.name} vs ${colWrestler.name}</strong><br/>`;
    html += `<div style="margin-top: 4px;">`;
    
    results.forEach((result, idx) => {
      const date = result.date || "—";
      const method = result.method || "—";
      const score = result.score || "";
      const rowWon = result.winner_id === rowWrestler.id;
      
      if (rowWon) {
        html += `<div style="margin-top: ${idx > 0 ? '4px' : '0'};">
          Defeated ${colWrestler.name}<br/>
          ${method}${score ? ` ${score}` : ""}<br/>
          <span style="opacity: 0.7; font-size: 0.85em;">${date}</span>
        </div>`;
      } else {
        html += `<div style="margin-top: ${idx > 0 ? '4px' : '0'};">
          Lost to ${colWrestler.name}<br/>
          ${method}${score ? ` ${score}` : ""}<br/>
          <span style="opacity: 0.7; font-size: 0.85em;">${date}</span>
        </div>`;
      }
    });
    
    html += `</div>`;
    return html;
  }
  
  // Single result
  if (results.length > 0) {
    const result = results[0];
    const date = result.date || "—";
    const method = result.method || "—";
    const score = result.score || "";
    const rowWon = result.winner_id === rowWrestler.id;
    
    if (rowWon) {
      return `Defeated ${colWrestler.name}<br/>
        ${method}${score ? ` ${score}` : ""}<br/>
        <span style="opacity: 0.7; font-size: 0.85em;">${date}</span>`;
    } else {
      return `Lost to ${colWrestler.name}<br/>
        ${method}${score ? ` ${score}` : ""}<br/>
        <span style="opacity: 0.7; font-size: 0.85em;">${date}</span>`;
    }
  }
  
  return null;
}

// Format wrestler name for display (full name)
function formatWrestlerName(name) {
  if (!name) return "—";
  // Return full name as-is
  return name.trim();
}

// Format wrestler name for column header (initials or short)
function formatColumnHeader(name) {
  if (!name) return "—";
  
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) {
    // Use first initial + last name initial
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  // Fallback: first 3 chars
  return name.substring(0, 3).toUpperCase();
}


// Render matrix
function renderMatrix(matrixData) {
  if (!matrixData) {
    document.getElementById("matrix-grid").innerHTML = `
      <div style="grid-column: 1 / -1; padding: 2em; text-align: center; color: var(--muted);">
        Error loading matrix data.
      </div>
    `;
    return;
  }
  
  const wrestlers = matrixData.wrestlers || [];
  const matrix = matrixData.matrix || {};
  const season = matrixData.season || "—";
  const weight = matrixData.weight || "125";
  
  // Update active tab based on current weight
  const tabs = document.querySelectorAll('.weight-tab');
  tabs.forEach(tab => {
    const href = tab.getAttribute('href');
    const tabWeight = href.match(/weight=(\d+)/)?.[1];
    if (tabWeight === weight.toString()) {
      tab.classList.add('active');
    } else {
      tab.classList.remove('active');
    }
  });
  
  const grid = document.getElementById("matrix-grid");
  grid.innerHTML = "";
  
  // Set grid template columns
  const colCount = wrestlers.length + 1; // +1 for row headers column
  grid.style.gridTemplateColumns = `240px repeat(${wrestlers.length}, 40px)`;
  
  // Create corner cell
  const corner = document.createElement("div");
  corner.className = "matrix-corner";
  grid.appendChild(corner);
  
  // Create column headers
  wrestlers.forEach((wrestler, colIndex) => {
    const colHeader = document.createElement("div");
    colHeader.className = "matrix-col-header";
    colHeader.textContent = formatColumnHeader(wrestler.name);
    colHeader.setAttribute("data-wrestler-id", wrestler.id);
    colHeader.setAttribute("data-col-index", colIndex);
    colHeader.setAttribute("data-col", colIndex.toString());
    grid.appendChild(colHeader);
  });
  
  // Create rows
  wrestlers.forEach((rowWrestler, rowIndex) => {
    // Row header
    const rowHeader = document.createElement("div");
    rowHeader.className = "matrix-row-header";
    rowHeader.setAttribute("data-wrestler-id", rowWrestler.id);
    rowHeader.setAttribute("data-row-index", rowIndex);
    rowHeader.setAttribute("data-row", rowIndex.toString());
    
    const rankSpan = document.createElement("span");
    rankSpan.className = "rank";
    rankSpan.textContent = rowWrestler.rank || "—";
    
    const nameSpan = document.createElement("span");
    nameSpan.className = "name";
    nameSpan.textContent = formatWrestlerName(rowWrestler.name);
    
    rowHeader.appendChild(rankSpan);
    rowHeader.appendChild(nameSpan);
    
    // Add click handler for future pinning (hook for Level 3)
    rowHeader.addEventListener("click", () => {
      // Future: pin wrestler, scroll to center, highlight row
      console.log("Row header clicked:", rowWrestler.id);
    });
    
    rowHeader.setAttribute("data-row", rowIndex.toString());
    
    grid.appendChild(rowHeader);
    
    // Create cells for this row
    wrestlers.forEach((colWrestler, colIndex) => {
      // Handle diagonal (wrestler vs self)
      if (rowWrestler.id === colWrestler.id) {
        const selfCell = document.createElement("div");
        selfCell.className = "matrix-cell self";
        selfCell.textContent = ""; // No letter
        selfCell.setAttribute("data-row-index", rowIndex);
        selfCell.setAttribute("data-col-index", colIndex);
        // No hover, no tooltip for diagonal cells
        grid.appendChild(selfCell);
        return;
      }
      
      const cellData = matrix[rowWrestler.id]?.[colWrestler.id];
      const styleInfo = getCellStyleInfo(cellData, rowWrestler.id, colWrestler.id);
      
      const cell = document.createElement("div");
      cell.className = "matrix-cell";
      cell.textContent = cellData?.display || "";
      
      // Set data attributes
      cell.setAttribute("data-row-index", rowIndex);
      cell.setAttribute("data-col-index", colIndex);
      cell.setAttribute("data-row-id", rowWrestler.id);
      cell.setAttribute("data-col-id", colWrestler.id);
      
      // Apply color and opacity via CSS class and inline alpha
      if (styleInfo.direction === "win") {
        cell.classList.add("cell-win");
        cell.style.setProperty("--alpha", styleInfo.alpha.toString());
      } else if (styleInfo.direction === "loss") {
        cell.classList.add("cell-loss");
        cell.style.setProperty("--alpha", styleInfo.alpha.toString());
      } else if (styleInfo.direction === "split") {
        cell.classList.add("cell-split");
      } else if (styleInfo.isCO) {
        cell.classList.add("cell-co");
      } else {
        // Neutral/empty
        cell.style.backgroundColor = "transparent";
      }
      
      // Store tooltip content in data attribute (string only, no DOM nodes)
      const tooltipContent = createTooltipContent(cellData, rowWrestler, colWrestler);
      if (tooltipContent) {
        cell.dataset.tooltip = tooltipContent;
      }
      
      // NO per-cell listeners - handled by delegation
      grid.appendChild(cell);
    });
  });
  
  // Delegated tooltip handler (single listener on grid)
  const tooltip = document.getElementById('matrix-tooltip');
  let tooltipRAF = null;
  
  function showTooltip(content, x, y) {
    tooltip.innerHTML = content;
    tooltip.classList.remove('hidden');
    
    // Position above cursor, centered
    tooltip.style.left = `${x}px`;
    tooltip.style.top = `${y - 12}px`;
    tooltip.style.transform = 'translate(-50%, -100%)';
  }
  
  function hideTooltip() {
    tooltip.classList.add('hidden');
  }
  
  grid.addEventListener('mousemove', (e) => {
    const cell = e.target.closest('.matrix-cell');
    if (!cell || !cell.dataset.tooltip || cell.classList.contains('self')) {
      hideTooltip();
      return;
    }
    
    if (tooltipRAF) cancelAnimationFrame(tooltipRAF);
    
    tooltipRAF = requestAnimationFrame(() => {
      showTooltip(cell.dataset.tooltip, e.clientX, e.clientY);
    });
  });
  
  grid.addEventListener('mouseleave', () => {
    hideTooltip();
  });
}

// Initialize matrix page
async function initMatrix() {
  const season = resolveSeason();
  const weight = getQueryParam("weight") || "125";
  
  const matrixData = await loadMatrixData(season, weight);
  renderMatrix(matrixData);
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initMatrix);
} else {
  initMatrix();
}

