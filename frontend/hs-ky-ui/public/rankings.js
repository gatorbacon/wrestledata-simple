// ========================================
// Rankings (Traditional) Page
// Note: hs_config.js must be loaded before this file
// ========================================

function safe(v, fn) {
  if (v === null || v === undefined || v === "") return "—";
  return fn ? fn(v) : v;
}

function getQueryParam(key) {
  return new URLSearchParams(window.location.search).get(key);
}

// ========================================
// Archive State
// ========================================
let archiveState = {
  index: null,
  meta: null,
  notes: null,
  currentDrop: null
};

// ========================================
// MV Rank Badge
// ========================================
function createMVRankBadge(rank) {
  if (rank === null || rank === undefined || rank === "") {
    return document.createTextNode("—");
  }
  
  const badge = document.createElement("span");
  badge.className = "rank-badge";
  
  // Medal badge styling: #1 gold, #2 silver, #3 bronze, others neutral
  if (rank === 1) {
    badge.classList.add("medal-gold");
  } else if (rank === 2) {
    badge.classList.add("medal-silver");
  } else if (rank === 3) {
    badge.classList.add("medal-bronze");
  } else {
    badge.classList.add("standard");
  }
  
  badge.textContent = `#${rank}`;
  return badge;
}

// ========================================
// Zero-Center MV Bar
// ========================================
function createZeroCenterMVBar(mvValue) {
  if (mvValue === null || mvValue === undefined) {
    return document.createTextNode("—");
  }
  
  const isPositive = mvValue >= 0;
  
  // Create wrapper with data-value and data-sign attributes
  const wrapper = document.createElement("div");
  wrapper.className = "value-bar-wrapper";
  wrapper.setAttribute("data-value", mvValue.toString());
  wrapper.setAttribute("data-sign", isPositive ? "positive" : "negative");
  
  // Zero line (first in DOM) - color based on value sign
  const zeroLine = document.createElement("div");
  zeroLine.className = `zero-line ${isPositive ? 'positive' : 'negative'}`;
  wrapper.appendChild(zeroLine);
  
  // Value bar
  const bar = document.createElement("div");
  bar.className = "value-bar";
  wrapper.appendChild(bar);
  
  // Value label
  const label = document.createElement("div");
  label.className = "value-label";
  wrapper.appendChild(label);
  
  // Calculate bar width and apply styles
  const MAX_ABS_VALUE = 6.0;
  const pct = Math.min(Math.abs(mvValue) / MAX_ABS_VALUE, 1);
  const widthPct = pct * 45; // 45% max each direction
  
  wrapper.style.setProperty('--bar-width', `${widthPct}%`);
  bar.style.width = `${widthPct}%`;
  
  if (isPositive) {
    bar.classList.add('positive');
    label.classList.add('positive');
    label.textContent = `+${mvValue.toFixed(1)}`;
  } else {
    bar.classList.add('negative');
    label.classList.add('negative');
    label.textContent = mvValue.toFixed(1);
  }
  
  return wrapper;
}

// ========================================
// Format Win-Loss Record
// ========================================
function formatWinLoss(record) {
  if (!record || record.wins === null || record.wins === undefined || record.losses === null || record.losses === undefined) {
    return "—";
  }
  
  // Use record_str if available, otherwise format from record object
  if (record.record_str) {
    return record.record_str;
  }
  
  const wins = record.wins;
  const losses = record.losses;
  const total = wins + losses;
  
  if (total === 0) {
    return "0–0 (—)";
  }
  
  const winPct = ((wins / total) * 100).toFixed(1);
  return `${wins}–${losses} (${winPct}%)`;
}

// ========================================
// Format Bonus Rate
// ========================================
function formatBonusRate(bonusPct) {
  if (bonusPct === null || bonusPct === undefined) {
    return "—";
  }
  
  // bonus_pct is already 0..1 format
  const pct = bonusPct * 100;
  return `${pct.toFixed(1)}%`;
}

// ========================================
// Team Name to Slug
// ========================================
function teamNameToSlug(teamName) {
  if (!teamName) return "";
  return teamName.toLowerCase()
    .replace(/\s+/g, '_')
    .replace(/[^a-z0-9_]/g, '');
}

// ========================================
// Format Published Date
// ========================================
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

// ========================================
// Format Date from ID (YYYY-MM-DD format)
// ========================================
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

// ========================================
// Load Archive Index
// ========================================
async function loadArchiveIndex(gender, season) {
  const url = `${HS_CONFIG.dataPaths.rankingsArchive}/${gender}/${season}/index.json`;
  console.log(`[HS Rankings] Loading archive index from: ${url}`);
  
  try {
    const response = await fetch(`${url}?t=${Date.now()}`, { cache: 'no-store' });
    
    if (!response.ok) {
      throw new Error(`Failed to load archive index: ${response.status}`);
    }
    
    const data = await response.json();
    archiveState.index = data;
    console.log(`[HS Rankings] Loaded archive index, latest: ${data.latest}, drops: ${data.drops.length}`);
    return data;
  } catch (error) {
    console.error(`[HS Rankings] Error loading archive index from ${url}:`, error);
    return null;
  }
}

// ========================================
// Load Drop Meta
// ========================================
async function loadDropMeta(gender, season, dropId) {
  const url = `${HS_CONFIG.dataPaths.rankingsArchive}/${gender}/${season}/${dropId}/meta.json`;
  console.log(`[HS Rankings] Loading drop meta from: ${url}`);
  
  try {
    const response = await fetch(`${url}?t=${Date.now()}`, { cache: 'no-store' });
    
    if (!response.ok) {
      throw new Error(`Failed to load drop meta: ${response.status}`);
    }
    
    const data = await response.json();
    archiveState.meta = data;
    console.log(`[HS Rankings] Loaded drop meta: ${dropId}, baseline: ${data.baseline}`);
    return data;
  } catch (error) {
    console.error(`[HS Rankings] Error loading drop meta from ${url}:`, error);
    return null;
  }
}

// ========================================
// Load Per-Weight Notes
// ========================================
async function loadWeightNotes(gender, season, dropId, weight) {
  const url = `${HS_CONFIG.dataPaths.rankingsArchive}/${gender}/${season}/${dropId}/notes/${weight}.md`;
  
  try {
    const response = await fetch(`${url}?t=${Date.now()}`, { cache: 'no-store' });
    
    if (!response.ok) {
      // Notes are optional, fail silently
      return null;
    }
    
    const text = await response.text();
    return text;
  } catch (error) {
    // Fail silently for missing notes
    return null;
  }
}

// ========================================
// Load Rankings Data from Archive
// ========================================
async function loadRankingsData(gender, season, weight, dropId) {
  const url = `${HS_CONFIG.dataPaths.rankingsArchive}/${gender}/${season}/${dropId}/${weight}.json`;
  console.log(`[HS Rankings] Loading rankings from: ${url}`);
  
  try {
    const response = await fetch(`${url}?t=${Date.now()}`, { cache: 'no-store' });
    
    if (!response.ok) {
      throw new Error(`Failed to load rankings: ${response.status} - ${response.statusText}`);
    }
    
    const data = await response.json();
    console.log(`[HS Rankings] Loaded ${data?.wrestlers?.length || 0} wrestlers for ${gender} ${weight} lbs (drop: ${dropId})`);
    return data;
  } catch (error) {
    console.error(`[HS Rankings] Error loading data from ${url}:`, error);
    return null;
  }
}

// ========================================
// Render Notes
// ========================================
function renderNotes(notesText) {
  const notesContainer = document.getElementById('rankings-notes');
  if (!notesContainer) return;
  
  if (!notesText || notesText.trim() === '') {
    notesContainer.style.display = 'none';
    return;
  }
  
  // Simple markdown rendering (basic support)
  // For full markdown, consider using a library like marked.js
  let html = notesText
    .replace(/^# (.+)$/gm, '<h2>$1</h2>')
    .replace(/^## (.+)$/gm, '<h3>$1</h3>')
    .replace(/^### (.+)$/gm, '<h4>$1</h4>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^\- (.+)$/gm, '<li>$1</li>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/^(.+)$/gm, '<p>$1</p>');
  
  // Wrap list items
  html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
  
  notesContainer.innerHTML = html;
  notesContainer.style.display = 'block';
}

// ========================================
// Render Drop Selector
// ========================================
function renderDropSelector(drops, currentDrop, gender, season, weight) {
  const selectorContainer = document.getElementById('drop-selector-container');
  if (!selectorContainer) return;
  
  if (drops.length <= 1) {
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
  
  // Handle change
  select.addEventListener('change', (e) => {
    const newDrop = e.target.value;
    // Update PDF link for new drop before navigation
    renderPdfDownloadLink(gender, season, newDrop);
    const url = new URL(window.location);
    url.searchParams.set('drop', newDrop);
    window.location.href = url.toString();
  });
}

// ========================================
// Render PDF Download Link
// ========================================
function renderPdfDownloadLink(gender, season, dropId) {
  const container = document.getElementById('pdf-download-container');
  const link = document.getElementById('pdf-download-link');
  
  if (!container || !link) return;
  
  // Construct PDF path
  const pdfPath = `/data/rankings/${gender}/${season}/${dropId}/rankings.pdf`;
  
  // Check if PDF exists by trying to fetch it
  fetch(pdfPath, { method: 'HEAD' })
    .then(response => {
      if (response.ok) {
        // PDF exists - show download link
        link.href = pdfPath;
        link.download = `rankings_${gender}_${season}_${dropId}.pdf`;
        container.style.display = 'block';
      } else {
        // PDF doesn't exist - hide container
        container.style.display = 'none';
      }
    })
    .catch(() => {
      // Error fetching - assume PDF doesn't exist
      container.style.display = 'none';
    });
}

// ========================================
// Check if previous placement should be shown
// ========================================
function shouldShowPreviousPlacement(season) {
  if (!season) return false;
  
  const currentDate = new Date();
  const seasonYear = parseInt(season, 10);
  const cutoffDate = new Date(seasonYear, 0, 20); // January 20 of season year
  
  // Only show if before January 20 of the current season year
  return currentDate < cutoffDate;
}

// ========================================
// Create Previous Season Placement Micro-Pill
// ========================================
function createPreviousPlacementPill(placementNote, season) {
  // Check seasonal expiration
  if (!shouldShowPreviousPlacement(season)) {
    return null;
  }
  
  if (!placementNote) return null;
  
  const note = placementNote.toUpperCase();
  let pillText = '';
  
  // Top 8 placements: "↩︎ #1", "↩︎ #2", etc.
  if (['1', '2', '3', '4', '5', '6', '7', '8'].includes(note)) {
    pillText = `↩︎ #${note}`;
  } 
  // Blood round: "↩︎ b"
  else if (note === 'BR') {
    pillText = '↩︎ b';
  } 
  // Qualifier: "↩︎ q"
  else if (note === 'Q') {
    pillText = '↩︎ q';
  } 
  // Unknown/invalid - don't render
  else {
    return null;
  }
  
  const pill = document.createElement('span');
  pill.className = 'previous-placement-pill';
  pill.textContent = pillText;
  return pill;
}

// ========================================
// Render Rankings Table
// ========================================
function renderRankings(data, gender, weight, isBaseline, season) {
  if (!data || !data.wrestlers || data.wrestlers.length === 0) {
    const tbody = document.querySelector("#rankings-table tbody");
    tbody.innerHTML = `
      <tr>
        <td colspan="8" style="text-align: center; padding: 2em; color: var(--muted);">
          HS data not found for ${gender} ${weight} lbs.<br>
          <small style="color: var(--muted-2);">Check console for fetch details.</small>
        </td>
      </tr>
    `;
    console.warn(`[HS Rankings] No data returned for ${gender} ${weight} lbs`);
    return;
  }
  
  // Wrestlers are already in correct order from rankings file
  let wrestlers = data.wrestlers;
  
  const tbody = document.querySelector("#rankings-table tbody");
  tbody.innerHTML = "";
  
  wrestlers.forEach((wrestler) => {
    const tr = document.createElement("tr");
    
    // Check if non-starter (not highest ranked for team)
    const isNonStarter = wrestler.is_highest_ranked === false;
    if (isNonStarter) {
      tr.classList.add("non-starter");
    }
    
    // Rank (just the number)
    const rankTd = document.createElement("td");
    rankTd.className = "rank";
    rankTd.style.width = "3em";
    rankTd.style.paddingRight = "0.25em";
    rankTd.style.textAlign = "center";
    rankTd.textContent = safe(wrestler.hybrid_rank ?? wrestler.rank);
    tr.appendChild(rankTd);
    
    // Movement indicator column (separate column for alignment)
    const movementTd = document.createElement("td");
    movementTd.className = "movement-col";
    movementTd.style.textAlign = "center";
    movementTd.style.width = "2em";
    movementTd.style.paddingLeft = "0";
    movementTd.style.paddingRight = "0.5em";
    
    if (!isBaseline) {
      // Check if wrestler is new (wasn't in previous rankings)
      if (wrestler.is_new === true) {
        const newSpan = document.createElement("span");
        newSpan.className = "rank-movement rank-new";
        newSpan.style.fontSize = "0.85em";
        newSpan.style.fontWeight = "700"; // Bold
        newSpan.style.color = "#1F4ED8"; // Blue (using accent-primary)
        newSpan.textContent = "N";
        movementTd.appendChild(newSpan);
      } 
      // Otherwise, show movement if available and non-zero
      else if (wrestler.movement !== undefined && wrestler.movement !== null) {
        const movement = wrestler.movement;
        
        if (movement !== 0) {
          const movementSpan = document.createElement("span");
          movementSpan.className = "rank-movement";
          movementSpan.style.fontSize = "0.85em";
          movementSpan.style.fontWeight = "600";
          
          if (movement > 0) {
            // Moved up (positive movement)
            movementSpan.style.color = "#22c55e"; // green
            movementSpan.textContent = `▲${Math.abs(movement)}`;
          } else {
            // Moved down (negative movement)
            movementSpan.style.color = "#ef4444"; // red
            movementSpan.textContent = `▼${Math.abs(movement)}`;
          }
          
          movementTd.appendChild(movementSpan);
        }
      }
    }
    
    tr.appendChild(movementTd);
    
    // Name (link to wrestler profile) with previous placement micro-pill
    const nameTd = document.createElement("td");
    nameTd.className = "name";
    if (wrestler.wrestler_id) {
      const nameLink = document.createElement("a");
      nameLink.href = `/wrestler.html?id=${wrestler.wrestler_id}&gender=${gender}`;
      nameLink.textContent = safe(wrestler.name);
      nameTd.appendChild(nameLink);
      
      // Add previous placement micro-pill if available (before Jan 20)
      const pill = createPreviousPlacementPill(wrestler.placement_note, season);
      if (pill) {
        nameTd.appendChild(pill);
      }
    } else {
      nameTd.textContent = safe(wrestler.name);
      
      // Add previous placement micro-pill if available (before Jan 20)
      const pill = createPreviousPlacementPill(wrestler.placement_note, season);
      if (pill) {
        nameTd.appendChild(pill);
      }
    }
    tr.appendChild(nameTd);
    
    // Team (link to team profile)
    const teamTd = document.createElement("td");
    teamTd.className = "name";
    if (wrestler.team) {
      const teamLink = document.createElement("a");
      const teamSlug = teamNameToSlug(wrestler.team);
      teamLink.href = buildPageURL('team.html', gender, { team: teamSlug });
      teamLink.textContent = wrestler.team;
      teamTd.appendChild(teamLink);
    } else {
      teamTd.textContent = "—";
    }
    tr.appendChild(teamTd);
    
    // Grade (Sr., Jr., So., Fr., 8th, 7th) - narrow column between Team and Region
    const gradeTd = document.createElement("td");
    gradeTd.className = "grade-col";
    gradeTd.textContent = wrestler.grade || "—";
    tr.appendChild(gradeTd);
    
    // Region (format: "7 (1)" or "7 (-)" or "-")
    const regionTd = document.createElement("td");
    regionTd.className = "region";
    const region = wrestler.region || "-";
    const regionPlace = wrestler.region_place || "N/A";
    
    if (region && region !== "-") {
      if (regionPlace && regionPlace !== "N/A") {
        regionTd.textContent = `${region} (${regionPlace})`;
      } else {
        regionTd.textContent = `${region} (-)`;
      }
    } else {
      regionTd.textContent = "-";
    }
    tr.appendChild(regionTd);
    
    // W–L Record
    const recordTd = document.createElement("td");
    recordTd.textContent = formatWinLoss(wrestler.record);
    // Short form for mobile two-line layout (no win%)
    if (wrestler.record && wrestler.record.wins != null) {
      recordTd.dataset.wlShort = `${wrestler.record.wins}–${wrestler.record.losses}`;
    }
    tr.appendChild(recordTd);
    
    // Bonus %
    const bonusTd = document.createElement("td");
    bonusTd.className = "num";
    bonusTd.textContent = formatBonusRate(wrestler.bonus_pct);
    tr.appendChild(bonusTd);
    
    tbody.appendChild(tr);
  });
}

// ========================================
// Generate Weight Tabs
// ========================================
function generateWeightTabs(gender, weights, dropId) {
  const container = document.getElementById('weight-tabs');
  if (!container) return;
  
  container.innerHTML = '';
  
  weights.forEach(weight => {
    const tab = document.createElement('a');
    tab.className = 'weight-tab';
    const params = new URLSearchParams();
    params.set('gender', gender);
    params.set('weight', weight);
    if (dropId) {
      params.set('drop', dropId);
    }
    tab.href = `rankings.html?${params.toString()}`;
    tab.textContent = weight.toString();
    container.appendChild(tab);
  });
}

// ========================================
// Update Active Tab
// ========================================
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

// ========================================
// Load and Render Weight-Specific Content
// ========================================
async function loadAndRenderWeight(gender, season, weight, dropId, isBaseline) {
  // Load notes for this weight
  const notes = await loadWeightNotes(gender, season, dropId, weight);
  renderNotes(notes);
  
  // Load and render rankings
  const data = await loadRankingsData(gender, season, weight, dropId);
  renderRankings(data, gender, weight, isBaseline, season);
}

// ========================================
// Initialize Rankings Page
// ========================================
async function initRankings() {
  // Get context from URL
  const gender = getGenderFromURL();
  const season = getSeasonFromURL();
  const weight = getWeightFromURL(gender);
  const weights = getWeightsForGender(gender);
  const dropIdParam = getQueryParam('drop');
  
  console.log(`[HS Rankings] Initializing: gender=${gender}, season=${season}, weight=${weight}, drop=${dropIdParam || 'latest'}`);
  const _rankGenderLabel = gender === "girls" ? "Kentucky Girls" : "Kentucky Boys";
  document.title = `${season} ${_rankGenderLabel} High School Wrestling Rankings | KentuckyMat`;
  sendPageView();
  setMetaDescription(`${season} ${_rankGenderLabel} high school wrestling rankings by weight class. Updated weekly with full stats, records, and match data on KentuckyMat.`);
  
  // Load archive index to determine which drop to use
  const index = await loadArchiveIndex(gender, season);
  if (!index) {
    console.error('[HS Rankings] Failed to load archive index, cannot proceed');
    return;
  }
  
  // Determine drop ID (use URL param, fallback to latest)
  const dropId = dropIdParam || index.latest;
  archiveState.currentDrop = dropId;
  
  // Load drop meta
  const meta = await loadDropMeta(gender, season, dropId);
  const isBaseline = meta?.baseline === true;
  
  // Generate weight tabs dynamically
  generateWeightTabs(gender, weights, dropId);
  
  // Update title
  const titleEl = document.getElementById("rankings-title");
  if (titleEl) {
    titleEl.textContent = `Rankings — ${gender.charAt(0).toUpperCase() + gender.slice(1)} ${weight} lbs`;
  }
  
  // Update season info with published date
  const seasonEl = document.getElementById("season-info");
  if (seasonEl && meta) {
    // Use dropId for display to avoid timezone conversion issues
    const publishedDate = formatDateFromId(dropId);
    seasonEl.textContent = `Published ${publishedDate}`;
  } else {
    seasonEl.textContent = `Season ${season}`;
  }
  
  // Render drop selector
  renderDropSelector(index.drops, dropId, gender, season, weight);
  
  // Check for PDF and render download link
  renderPdfDownloadLink(gender, season, dropId);
  
  // Update active tab
  updateActiveTab(gender, weight);
  
  // Load weight-specific content (notes + rankings)
  await loadAndRenderWeight(gender, season, weight, dropId, isBaseline);
  
  // Set up weight tab click handlers to reload notes and rankings
  const weightTabs = document.querySelectorAll('.weight-tab');
  weightTabs.forEach(tab => {
    tab.addEventListener('click', async (e) => {
      // Extract weight from href
      const href = tab.getAttribute('href');
      const urlParams = new URLSearchParams(href.split('?')[1]);
      const newWeight = parseInt(urlParams.get('weight'));
      const newDrop = urlParams.get('drop') || dropId;
      
      if (newWeight && newWeight !== weight) {
        e.preventDefault();
        
        // Update URL without reload
        const currentUrl = new URL(window.location);
        currentUrl.searchParams.set('weight', newWeight);
        if (newDrop !== dropId) {
          currentUrl.searchParams.set('drop', newDrop);
        }
        window.history.pushState({}, '', currentUrl);
        
        // Update active tab
        updateActiveTab(gender, newWeight);
        
        // Update title
        if (titleEl) {
          titleEl.textContent = `Rankings — ${gender.charAt(0).toUpperCase() + gender.slice(1)} ${newWeight} lbs`;
        }
        
        // Load new weight's notes and rankings
        await loadAndRenderWeight(gender, season, newWeight, newDrop, isBaseline);
      }
    });
  });
}

// Handle browser back/forward navigation
window.addEventListener('popstate', async () => {
  const gender = getGenderFromURL();
  const season = getSeasonFromURL();
  const weight = getWeightFromURL(gender);
  const dropIdParam = getQueryParam('drop');
  
  // Load archive index to get drop ID
  const index = await loadArchiveIndex(gender, season);
  if (!index) return;
  
  const dropId = dropIdParam || index.latest;
  const meta = await loadDropMeta(gender, season, dropId);
  const isBaseline = meta?.baseline === true;
  
  // Update title
  const titleEl = document.getElementById("rankings-title");
  if (titleEl) {
    titleEl.textContent = `Rankings — ${gender.charAt(0).toUpperCase() + gender.slice(1)} ${weight} lbs`;
  }
  
  // Update active tab
  updateActiveTab(gender, weight);
  
  // Reload weight-specific content
  await loadAndRenderWeight(gender, season, weight, dropId, isBaseline);
});

// Initialize on DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initRankings);
} else {
  initRankings();
}
