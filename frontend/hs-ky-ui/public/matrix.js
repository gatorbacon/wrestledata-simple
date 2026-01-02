// ========================================
// Rankings Matrix Renderer
// ========================================
// Note: hs_config.js must be loaded before this file

function safe(v, fn) {
  if (v === null || v === undefined || v === "") return "—";
  return fn ? fn(v) : v;
}

function getQueryParam(key) {
  return new URLSearchParams(window.location.search).get(key);
}

// Load matrix data
async function loadMatrixData(gender, season, weight) {
  const url = buildMatrixURL(gender, season, weight);
  console.log(`[HS Matrix] Loading data from: ${url}`);
  
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status} - ${res.statusText}`);
    const data = await res.json();
    console.log(`[HS Matrix] Loaded matrix data for ${gender} ${weight} lbs (${data?.wrestlers?.length || 0} wrestlers)`);
    return data;
  } catch (err) {
    console.error(`[HS Matrix] Error loading data from ${url}:`, err);
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


// Persistent hover controller (single instance, lives outside renderMatrix)
const matrixHoverController = (function() {
  const tooltip = document.getElementById('matrix-tooltip');
  let tooltipRAF = null;
  let currentGrid = null;
  let lastHoveredCell = null;
  
  function showTooltip(content, x, y) {
    if (!tooltip) return;
    tooltip.innerHTML = content;
    tooltip.classList.remove('hidden');
    tooltip.style.left = `${x}px`;
    tooltip.style.top = `${y - 12}px`;
    tooltip.style.transform = 'translate(-50%, -100%)';
  }
  
  function hideTooltip() {
    if (!tooltip) return;
    if (tooltipRAF) {
      cancelAnimationFrame(tooltipRAF);
      tooltipRAF = null;
    }
    tooltip.classList.add('hidden');
    lastHoveredCell = null;
  }
  
  function findCellFromCoordinates(clientX, clientY) {
    // DEBUG: Log entry
    const debugEnabled = window.location.search.includes('debug=true');
    
    if (debugEnabled) {
      console.log('[findCellFromCoordinates] Called with:', { clientX, clientY, hasGrid: !!currentGrid });
    }
    
    // Try elementFromPoint first (fast path)
    let el = document.elementFromPoint(clientX, clientY);
    
    if (debugEnabled) {
      console.log('[findCellFromCoordinates] elementFromPoint returned:', {
        element: el,
        tagName: el?.tagName,
        className: el?.className,
        id: el?.id,
        inGrid: currentGrid ? currentGrid.contains(el) : 'no grid',
        activeElement: document.activeElement?.tagName + '#' + (document.activeElement?.id || '')
      });
    }
    
    // If elementFromPoint fails or returns wrong element, try elementsFromPoint as fallback
    if (!el || (currentGrid && !currentGrid.contains(el))) {
      if (debugEnabled) {
        console.log('[findCellFromCoordinates] Falling back to elementsFromPoint');
      }
      const elements = document.elementsFromPoint(clientX, clientY);
      if (debugEnabled) {
        console.log('[findCellFromCoordinates] elementsFromPoint returned', elements.length, 'elements:', 
          elements.slice(0, 5).map(e => ({ tag: e.tagName, class: e.className, inGrid: currentGrid ? currentGrid.contains(e) : 'no grid' }))
        );
      }
      // Find first element that's within the grid
      el = elements.find(elem => 
        currentGrid && currentGrid.contains(elem)
      ) || null;
      
      if (debugEnabled) {
        console.log('[findCellFromCoordinates] Found element in grid:', {
          element: el,
          tagName: el?.tagName,
          className: el?.className
        });
      }
    }
    
    // Explicitly ignore non-matrix elements
    if (!el) {
      if (debugEnabled) {
        console.log('[findCellFromCoordinates] No element found, returning null');
      }
      return null;
    }
    
    // Ignore if element is part of tooltip
    if (tooltip && (tooltip.contains(el) || el === tooltip)) {
      if (debugEnabled) {
        console.log('[findCellFromCoordinates] Element is tooltip, returning null');
      }
      return null;
    }
    
    // Ignore if element is part of header
    const header = document.getElementById('site-header');
    if (header && header.contains(el)) {
      if (debugEnabled) {
        console.log('[findCellFromCoordinates] Element is header, returning null');
      }
      return null;
    }
    
    // Ignore if element is outside the matrix grid
    if (currentGrid && !currentGrid.contains(el)) {
      if (debugEnabled) {
        console.log('[findCellFromCoordinates] Element outside grid, returning null');
      }
      return null;
    }
    
    // Resolve matrix cell strictly from the element at coordinates
    const cell = el.closest('.matrix-cell');
    
    if (debugEnabled) {
      console.log('[findCellFromCoordinates] closest .matrix-cell:', {
        cell: cell,
        hasTooltip: cell?.dataset.tooltip ? 'yes' : 'no',
        isSelf: cell?.classList.contains('self'),
        inGrid: cell && currentGrid ? currentGrid.contains(cell) : 'no grid'
      });
    }
    
    // Validate cell is within current grid
    if (cell && currentGrid && currentGrid.contains(cell)) {
      if (debugEnabled) {
        console.log('[findCellFromCoordinates] Returning cell:', cell);
      }
      return cell;
    }
    
    if (debugEnabled) {
      console.log('[findCellFromCoordinates] Final check failed, returning null');
    }
    return null;
  }
  
  function handleMouseMove(e) {
    const debugEnabled = window.location.search.includes('debug=true');
    
    // DEBUG: Log every mousemove (throttled to avoid spam)
    if (debugEnabled) {
      if (!handleMouseMove._lastLog || Date.now() - handleMouseMove._lastLog > 1000) {
        console.log('[handleMouseMove] Event fired:', {
          hasGrid: !!currentGrid,
          gridId: currentGrid?.id,
          clientX: e.clientX,
          clientY: e.clientY,
          target: e.target?.tagName + '#' + (e.target?.id || ''),
          activeElement: document.activeElement?.tagName + '#' + (document.activeElement?.id || '')
        });
        handleMouseMove._lastLog = Date.now();
      }
    }
    
    // Only process if we have an active grid
    if (!currentGrid) {
      if (debugEnabled && (!handleMouseMove._lastNoGridLog || Date.now() - handleMouseMove._lastNoGridLog > 2000)) {
        console.log('[handleMouseMove] No currentGrid, hiding tooltip');
        handleMouseMove._lastNoGridLog = Date.now();
      }
      hideTooltip();
      return;
    }
    
    // Coordinate-based hover detection (ignore e.target)
    const cell = findCellFromCoordinates(e.clientX, e.clientY);
    
    if (debugEnabled) {
      console.log('[handleMouseMove] Cell found:', {
        cell: cell,
        hasTooltip: cell?.dataset.tooltip ? 'yes' : 'no',
        isSelf: cell?.classList.contains('self'),
        lastHoveredCell: lastHoveredCell,
        isSameCell: cell === lastHoveredCell
      });
    }
    
    // If no valid cell or cell has no tooltip or is self cell, hide tooltip
    if (!cell || !cell.dataset.tooltip || cell.classList.contains('self')) {
      if (lastHoveredCell !== null) {
        if (debugEnabled) {
          console.log('[handleMouseMove] Hiding tooltip - no valid cell or no tooltip data');
        }
        hideTooltip();
      }
      return;
    }
    
    // If same cell as last hover, skip update (performance optimization)
    if (cell === lastHoveredCell) {
      if (debugEnabled && Math.random() < 0.01) { // Log 1% of the time to avoid spam
        console.log('[handleMouseMove] Same cell, skipping update');
      }
      return;
    }
    
    // Update tooltip for new cell
    if (debugEnabled) {
      console.log('[handleMouseMove] Updating tooltip for new cell');
    }
    lastHoveredCell = cell;
    
    // Cancel any pending RAF
    if (tooltipRAF) {
      cancelAnimationFrame(tooltipRAF);
    }
    
    // Schedule tooltip update
    tooltipRAF = requestAnimationFrame(() => {
      showTooltip(cell.dataset.tooltip, e.clientX, e.clientY);
      tooltipRAF = null;
    });
  }
  
  function handleMouseLeave(e) {
    // Hide tooltip when leaving the grid or document
    if (!currentGrid || !currentGrid.contains(e.relatedTarget)) {
      hideTooltip();
    }
  }
  
  function handleDocumentMouseLeave(e) {
    // Hide tooltip when mouse leaves document entirely
    if (!e.relatedTarget) {
      hideTooltip();
    }
  }
  
  // DEBUG: Check debug mode (check it here so it's available)
  let debugEnabled = window.location.search.includes('debug=true');
  
  // Always attach test handler if debug is enabled (even before main handlers)
  if (debugEnabled) {
    console.log('[hoverController] Debug mode enabled, attaching test handlers');
    
    // Check if document/body can receive events
    console.log('[hoverController] Document state:', {
      hasFocus: document.hasFocus(),
      activeElement: document.activeElement?.tagName + '#' + (document.activeElement?.id || ''),
      bodyPointerEvents: window.getComputedStyle(document.body).pointerEvents,
      documentReadyState: document.readyState
    });
    
    // Test ALL mouse events to see if ANY are firing
    const mouseEvents = ['mousedown', 'mouseup', 'mousemove', 'mouseenter', 'mouseleave', 'mouseover', 'mouseout', 'click'];
    mouseEvents.forEach(eventType => {
      document.addEventListener(eventType, (e) => {
        if (!window._mouseEventCount) window._mouseEventCount = {};
        if (!window._mouseEventCount[eventType]) {
          window._mouseEventCount[eventType] = 0;
        }
        window._mouseEventCount[eventType]++;
        if (window._mouseEventCount[eventType] === 1) {
          console.log(`[hoverController] ${eventType} event FIRED!`, {
            target: e.target?.tagName + '#' + (e.target?.id || ''),
            clientX: e.clientX,
            clientY: e.clientY
          });
        }
      }, true);
    });
    console.log('[hoverController] Test handlers attached for all mouse events');
    
    // Test handler - attach FIRST in capture phase to catch everything
    let testMoveCount = 0;
    const testHandler = (e) => {
      testMoveCount++;
      if (testMoveCount <= 3) { // Log first 3 to confirm it's working
        console.log('[hoverController] TEST: mousemove event FIRED!', {
          count: testMoveCount,
          clientX: e.clientX,
          clientY: e.clientY,
          target: e.target?.tagName + '#' + (e.target?.id || ''),
          currentTarget: e.currentTarget?.tagName,
          bubbles: e.bubbles,
          cancelable: e.cancelable
        });
      }
    };
    document.addEventListener('mousemove', testHandler, true);
    window.addEventListener('mousemove', testHandler, true);
    document.body.addEventListener('mousemove', testHandler, true);
    console.log('[hoverController] Test handler attached in capture phase (document, window, body)');
  }
  
  // Wrap handleMouseMove to track calls
  const originalHandleMouseMove = handleMouseMove;
  handleMouseMove = function(e) {
    if (debugEnabled) {
      if (!handleMouseMove._callCount) {
        handleMouseMove._callCount = 0;
      }
      handleMouseMove._callCount++;
      if (handleMouseMove._callCount <= 3) {
        console.log('[hoverController] handleMouseMove CALLED!', {
          count: handleMouseMove._callCount,
          hasGrid: !!currentGrid,
          gridId: currentGrid?.id,
          clientX: e.clientX,
          clientY: e.clientY
        });
      }
    }
    return originalHandleMouseMove.call(this, e);
  };
  
  // CRITICAL FIX: Use mouseover as PRIMARY mechanism since mousemove doesn't fire reliably
  // mouseover fires when entering elements, which works even when mousemove is blocked
  function handleMouseOver(e) {
    // Use coordinate-based detection just like mousemove (don't rely on e.target)
    if (!currentGrid) return;
    
    // Use the same coordinate-based detection as mousemove
    handleMouseMove(e);
  }
  
  // Attach listeners once (document-level for robustness)
  document.addEventListener('mousemove', handleMouseMove); // Keep for when it does fire
  document.addEventListener('mouseover', handleMouseOver, true); // PRIMARY: Use capture phase to catch early
  document.addEventListener('mouseleave', handleDocumentMouseLeave);
  
  // DEBUG: Log listener attachment
  if (debugEnabled) {
    console.log('[hoverController] Event listeners attached:', {
      mousemove: 'attached',
      mouseleave: 'attached',
      hasTooltip: !!tooltip,
      tooltipId: tooltip?.id,
      handlerFunction: typeof handleMouseMove,
      testHandlerAttached: 'yes'
    });
    
    // Also check if events are being stopped somewhere
    window.addEventListener('mousemove', (e) => {
      if (!window._windowMouseMoveCount) {
        window._windowMouseMoveCount = 0;
      }
      window._windowMouseMoveCount++;
      if (window._windowMouseMoveCount === 1) {
        console.log('[hoverController] Window-level mousemove fired!');
      }
    }, true);
  }
  
  // Add click handler to reset hover state after clicks outside grid
  document.addEventListener('click', function(e) {
    const debugEnabled = window.location.search.includes('debug=true');
    
    if (debugEnabled) {
      console.log('[click] Click detected:', {
        target: e.target.tagName + '#' + (e.target.id || ''),
        inGrid: currentGrid ? currentGrid.contains(e.target) : 'no grid',
        activeElement: document.activeElement?.tagName + '#' + (document.activeElement?.id || '')
      });
    }
    
    // CRITICAL FIX: After any click, trigger a mouseover event to reactivate hover tracking
    // mouseover events fire reliably, unlike mousemove which may be blocked
    setTimeout(() => {
      // Get element at click position
      const el = document.elementFromPoint(e.clientX, e.clientY);
      if (el) {
        // Dispatch mouseover on the element to trigger hover detection
        const syntheticEvent = new MouseEvent('mouseover', {
          bubbles: true,
          cancelable: true,
          view: window,
          clientX: e.clientX,
          clientY: e.clientY,
          relatedTarget: null
        });
        el.dispatchEvent(syntheticEvent);
        if (debugEnabled) {
          console.log('[click] Dispatched synthetic mouseover after click to reactivate tracking');
        }
      }
    }, 10);
    
    // If clicking outside the grid, reset hover state
    if (currentGrid && !currentGrid.contains(e.target)) {
      if (debugEnabled) {
        console.log('[click] Click outside grid, resetting hover state');
      }
      // Small delay to let focus settle, then reset
      setTimeout(() => {
        if (document.activeElement && document.activeElement !== document.body) {
          if (debugEnabled) {
            console.log('[click] Blurring active element after click:', document.activeElement.tagName + '#' + (document.activeElement.id || ''));
          }
          document.activeElement.blur();
        }
        lastHoveredCell = null;
      }, 0);
    }
  }, true); // Use capture phase to run early
  
  return {
    setGrid: function(grid) {
      const debugEnabled = window.location.search.includes('debug=true');
      
      if (debugEnabled) {
        console.log('[setGrid] Called with:', {
          hasGrid: !!grid,
          gridId: grid?.id,
          currentGrid: currentGrid?.id,
          activeElement: document.activeElement?.tagName + '#' + (document.activeElement?.id || '')
        });
      }
      
      // Remove old grid mouseleave listener if it exists
      if (currentGrid) {
        currentGrid.removeEventListener('mouseleave', handleMouseLeave);
      }
      
      // Hide tooltip and clear state on grid change
      hideTooltip();
      
      // Set new grid reference
      currentGrid = grid;
      
      // Attach mouseleave to new grid
      if (currentGrid) {
        currentGrid.addEventListener('mouseleave', handleMouseLeave);
      }
      
      // Reset focus state to prevent elementFromPoint issues
      if (document.activeElement && document.activeElement !== document.body) {
        if (debugEnabled) {
          console.log('[setGrid] Blurring active element:', document.activeElement.tagName + '#' + (document.activeElement.id || ''));
        }
        document.activeElement.blur();
      }
      
      // Clear any stale hover state
      lastHoveredCell = null;
      
      if (debugEnabled) {
        console.log('[setGrid] Grid set, state reset');
      }
    },
    cleanup: function() {
      hideTooltip();
      currentGrid = null;
    },
    // DEBUG: Expose current grid for debugging
    _getCurrentGrid: function() {
      return currentGrid;
    }
  };
})();

// Generate weight tabs
function generateWeightTabs(gender, weights) {
  const container = document.getElementById('weight-tabs');
  if (!container) return;
  
  container.innerHTML = '';
  
  weights.forEach(weight => {
    const tab = document.createElement('a');
    tab.className = 'weight-tab';
    tab.href = buildPageURL('matrix.html', gender, { weight });
    tab.textContent = weight.toString();
    container.appendChild(tab);
  });
}

// Update active tab
function updateActiveTab(gender, weight) {
  const tabs = document.querySelectorAll('.weight-tab');
  tabs.forEach(tab => {
    const href = tab.getAttribute('href');
    const tabWeight = href.match(/weight=(\d+)/)?.[1];
    const tabGender = href.match(/gender=(\w+)/)?.[1];
    
    if (tabWeight === weight.toString() && tabGender === gender) {
      tab.classList.add('active');
    } else {
      tab.classList.remove('active');
    }
  });
}

// Render matrix
function renderMatrix(matrixData, gender, weight) {
  const gridEl = document.getElementById("matrix-grid");
  if (!gridEl) {
    console.error('[HS Matrix] Matrix grid element not found');
    return;
  }
  
  if (!matrixData) {
    gridEl.innerHTML = `
      <div style="grid-column: 1 / -1; padding: 2em; text-align: center; color: var(--muted);">
        HS data not found for ${gender} ${weight} lbs.<br>
        <small style="color: var(--muted-2);">Check console for fetch details.</small>
      </div>
    `;
    matrixHoverController.setGrid(null);
    console.warn(`[HS Matrix] No data returned for ${gender} ${weight} lbs`);
    return;
  }
  
  const wrestlers = matrixData.wrestlers || [];
  const matrix = matrixData.matrix || {};
  const season = matrixData.season || "—";
  // Use weight parameter (already declared in function signature)
  
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
  // Set CSS variable for mobile media query
  grid.style.setProperty('--col-count', wrestlers.length.toString());
  
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
    // Store abbreviated version for mobile CSS
    nameSpan.setAttribute("data-name-abbreviated", formatWrestlerNameAbbreviated(rowWrestler.name));
    
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
      
      grid.appendChild(cell);
    });
  });
  
  // Update hover controller with new grid reference (no listener attachment here)
  matrixHoverController.setGrid(grid);
}

// Initialize matrix page
async function initMatrix() {
  const debugEnabled = window.location.search.includes('debug=true');
  
  if (debugEnabled) {
    console.log('[initMatrix] Starting initialization');
  }
  
  // Get context from URL
  const gender = getGenderFromURL();
  const season = getSeasonFromURL();
  const weight = getWeightFromURL(gender);
  const weights = getWeightsForGender(gender);
  
  console.log(`[HS Matrix] Initializing: gender=${gender}, season=${season}, weight=${weight}`);
  
  // Generate weight tabs dynamically
  generateWeightTabs(gender, weights);
  
  // Update active tab
  updateActiveTab(gender, weight);
  
  const matrixData = await loadMatrixData(gender, season, weight);
  renderMatrix(matrixData, gender, weight);
  
  // Reset focus after initial render to ensure hover works
  requestAnimationFrame(() => {
    if (document.activeElement && document.activeElement !== document.body) {
      if (debugEnabled) {
        console.log('[initMatrix] Blurring active element after render:', document.activeElement.tagName + '#' + (document.activeElement.id || ''));
      }
      document.activeElement.blur();
    }
    
    // CRITICAL FIX: Manually trigger a mouseover event to activate hover tracking
    // mouseover events fire reliably, unlike mousemove which may be blocked
    // We'll trigger it on the grid itself to ensure hover is ready
    const grid = document.getElementById('matrix-grid');
    if (grid) {
      const syntheticEvent = new MouseEvent('mouseover', {
        bubbles: true,
        cancelable: true,
        view: window,
        clientX: 0,
        clientY: 0,
        relatedTarget: null
      });
      grid.dispatchEvent(syntheticEvent);
      if (debugEnabled) {
        console.log('[initMatrix] Dispatched synthetic mouseover event on grid to activate tracking');
      }
    }
    
    if (debugEnabled) {
      console.log('[initMatrix] Initialization complete', {
        activeElement: document.activeElement?.tagName + '#' + (document.activeElement?.id || ''),
        hasGrid: !!document.getElementById('matrix-grid'),
        hasFocus: document.hasFocus()
      });
    }
  });
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initMatrix);
} else {
  initMatrix();
}

