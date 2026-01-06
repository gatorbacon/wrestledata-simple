// ========================================
// Dual Matchup Predictor
// ========================================

let currentGender = 'boys';
let currentSeason = getSeasonFromURL();
let teamList = [];
let rankingsByWeight = {};
let teamRosters = {}; // team_name -> { weights: { weight: [wrestlers] } }
let teamA = null;
let teamB = null;
let fuse = null;

// ========================================
// Initialize
// ========================================

async function init() {
  currentGender = getGenderFromURL();
  
  // Setup gender toggle
  setupGenderToggle();
  
  // Load team list
  await loadTeamList();
  
  // Setup team autocomplete
  setupTeamAutocomplete();
  
  // Load rankings data
  await loadRankingsData();
  
  // Load team rosters
  await loadTeamRosters();
}

function setupGenderToggle() {
  const boysBtn = document.getElementById('gender-toggle-boys');
  const girlsBtn = document.getElementById('gender-toggle-girls');
  
  boysBtn.addEventListener('click', () => {
    currentGender = 'boys';
    boysBtn.classList.add('active');
    girlsBtn.classList.remove('active');
    resetTeams();
    loadTeamList();
    loadRankingsData();
    loadTeamRosters();
  });
  
  girlsBtn.addEventListener('click', () => {
    currentGender = 'girls';
    girlsBtn.classList.add('active');
    boysBtn.classList.remove('active');
    resetTeams();
    loadTeamList();
    loadRankingsData();
    loadTeamRosters();
  });
  
  // Set initial state
  if (currentGender === 'girls') {
    girlsBtn.classList.add('active');
    boysBtn.classList.remove('active');
  }
}

function resetTeams() {
  teamA = null;
  teamB = null;
  document.getElementById('team-a-input').value = '';
  document.getElementById('team-b-input').value = '';
  document.getElementById('scoreboard-container').style.display = 'none';
  document.getElementById('matchup-table-container').style.display = 'none';
}

async function loadTeamList() {
  try {
    // Load from search index (contains all teams)
    if (typeof searchIndex !== 'undefined' && searchIndex) {
      const teams = searchIndex.filter(item => item.type === 'team');
      teamList = teams.map(item => item.name);
      teamList.sort();
      console.log(`[Dual Predictor] Loaded ${teamList.length} teams from search index`);
    } else {
      // Fallback: try to load from team metrics or xTP data
      try {
        const xtpUrl = buildXTPURL(currentGender, currentSeason);
        const xtpData = await fetchJSON(xtpUrl);
        const teamsArray = Array.isArray(xtpData) ? xtpData : (xtpData.teams || []);
        teamList = teamsArray.map(t => t.team || t.name).filter(Boolean);
        teamList.sort();
        console.log(`[Dual Predictor] Loaded ${teamList.length} teams from xTP data`);
      } catch (err) {
        console.error('[Dual Predictor] Failed to load team list:', err);
        teamList = [];
      }
    }
  } catch (err) {
    console.error('[Dual Predictor] Error loading team list:', err);
    teamList = [];
  }
}

function setupTeamAutocomplete() {
  const teamAInput = document.getElementById('team-a-input');
  const teamBInput = document.getElementById('team-b-input');
  const teamADropdown = document.getElementById('team-a-dropdown');
  const teamBDropdown = document.getElementById('team-b-dropdown');
  
  // Initialize Fuse.js for fuzzy search
  if (typeof Fuse !== 'undefined') {
    fuse = new Fuse(teamList, {
      threshold: 0.3,
      includeScore: true
    });
  }
  
  setupAutocompleteInput(teamAInput, teamADropdown, (team) => {
    teamA = team;
    updateMatchups();
  });
  
  setupAutocompleteInput(teamBInput, teamBDropdown, (team) => {
    teamB = team;
    updateMatchups();
  });
}

function setupAutocompleteInput(input, dropdown, onSelect) {
  let timeout = null;
  
  input.addEventListener('input', (e) => {
    const query = e.target.value.trim();
    
    clearTimeout(timeout);
    
    if (!query) {
      dropdown.style.display = 'none';
      return;
    }
    
    timeout = setTimeout(() => {
      const results = searchTeams(query);
      renderDropdown(dropdown, results, (team) => {
        input.value = team;
        dropdown.style.display = 'none';
        onSelect(team);
      });
    }, 150);
  });
  
  input.addEventListener('focus', () => {
    const query = input.value.trim();
    if (query) {
      const results = searchTeams(query);
      renderDropdown(dropdown, results, (team) => {
        input.value = team;
        dropdown.style.display = 'none';
        onSelect(team);
      });
    }
  });
  
  // Close dropdown when clicking outside
  document.addEventListener('click', (e) => {
    if (!input.contains(e.target) && !dropdown.contains(e.target)) {
      dropdown.style.display = 'none';
    }
  });
}

function searchTeams(query) {
  if (!query) return [];
  
  if (fuse) {
    const results = fuse.search(query);
    return results.slice(0, 10).map(r => r.item);
  }
  
  // Fallback: simple filter
  const queryLower = query.toLowerCase();
  return teamList.filter(team => 
    team.toLowerCase().includes(queryLower)
  ).slice(0, 10);
}

function renderDropdown(dropdown, results, onSelect) {
  if (results.length === 0) {
    dropdown.style.display = 'none';
    return;
  }
  
  dropdown.innerHTML = '';
  results.forEach(team => {
    const item = document.createElement('div');
    item.className = 'autocomplete-item';
    item.textContent = team;
    item.addEventListener('click', () => onSelect(team));
    dropdown.appendChild(item);
  });
  
  dropdown.style.display = 'block';
}

async function loadRankingsData() {
  const weights = getWeightsForGender(currentGender);
  rankingsByWeight = {};
  
  // Load FULL rankings by aggregating from wrestler profiles
  // Each wrestler profile contains their current_rank, so we can build complete rankings
  console.log(`[Dual Predictor] Loading full rankings from wrestler profiles...`);
  
  // Load FULL rankings from public location (copied by generate_public_rankings.py)
  for (const weight of weights) {
    try {
      const url = `${HS_CONFIG.dataPaths.rankingsFull}/${currentGender}/${currentSeason}/${weight}.json`;
      const data = await fetchJSON(url);
      
      if (data && data.rankings) {
        // Convert rankings array to wrestlers format
        rankingsByWeight[weight] = data.rankings.map(r => ({
          wrestler_id: r.wrestler_id,
          name: r.name,
          team: r.team,
          rank: r.rank,
          is_highest_ranked: r.is_highest_ranked !== false
        }));
        
        console.log(`[Dual Predictor] Loaded ${data.rankings.length} ranked wrestlers for ${weight} lbs from full rankings`);
      }
    } catch (err) {
      console.warn(`[Dual Predictor] Could not load full rankings for ${weight}, trying fallback...`, err);
      
      // Fallback: Try archive system (limited to top 40/24)
      try {
        let dropId = null;
        try {
          const indexUrl = `${HS_CONFIG.dataPaths.rankingsArchive}/${currentGender}/${currentSeason}/index.json`;
          const indexData = await fetchJSON(indexUrl);
          dropId = indexData?.latest || null;
        } catch (err) {
          // Archive not available
        }
        
        if (dropId) {
          try {
            const url = `${HS_CONFIG.dataPaths.rankingsArchive}/${currentGender}/${currentSeason}/${dropId}/${weight}.json`;
            const data = await fetchJSON(url);
            if (data && data.wrestlers) {
              rankingsByWeight[weight] = data.wrestlers;
              console.warn(`[Dual Predictor] Using archive data for ${weight} (limited to top ${currentGender === 'boys' ? '40' : '24'})`);
            }
          } catch (err) {
            // Skip this weight
          }
        }
      } catch (err) {
        console.warn(`[Dual Predictor] Could not load rankings for ${weight}:`, err);
      }
    }
  }
  
  console.log(`[Dual Predictor] Loaded rankings for ${Object.keys(rankingsByWeight).length} weight classes`);
  
  // Log total wrestlers loaded
  const totalWrestlers = Object.values(rankingsByWeight).reduce((sum, wrestlers) => sum + wrestlers.length, 0);
  console.log(`[Dual Predictor] Total wrestlers loaded: ${totalWrestlers}`);
}

async function loadTeamRosters() {
  teamRosters = {};
  const weights = getWeightsForGender(currentGender);
  
  // Build roster from rankings data (ranked wrestlers only)
  for (const [weight, wrestlers] of Object.entries(rankingsByWeight)) {
    for (const wrestler of wrestlers) {
      const teamName = wrestler.team;
      if (!teamName) continue;
      
      if (!teamRosters[teamName]) {
        teamRosters[teamName] = { weights: {} };
      }
      
      if (!teamRosters[teamName].weights[weight]) {
        teamRosters[teamName].weights[weight] = [];
      }
      
      teamRosters[teamName].weights[weight].push({
        wrestler_id: wrestler.wrestler_id,
        name: wrestler.name,
        rank: wrestler.rank,
        is_highest_ranked: wrestler.is_highest_ranked !== false
      });
    }
  }
  
  // Load ALL wrestlers from index_teams.json (includes unranked wrestlers)
  try {
    const indexUrl = `/data/wrestlers/${currentGender}/${currentSeason}/index_teams.json`;
    const indexData = await fetchJSON(indexUrl);
    
    // Helper function to normalize team names for matching
    function normalizeTeamName(name) {
      if (!name) return '';
      return name.toLowerCase()
        .replace(/\s+/g, '_')
        .replace(/[^a-z0-9_]/g, '');
    }
    
    // Process each team in the index
    for (const teamEntry of indexData) {
      if (!teamEntry.roster || !teamEntry.team_slug) continue;
      
      const teamSlug = teamEntry.team_slug;
      const normalizedSlug = normalizeTeamName(teamSlug);
      
      // Find team name by matching slug with existing teams in roster
      let teamName = null;
      for (const existingTeamName of Object.keys(teamRosters)) {
        if (normalizeTeamName(existingTeamName) === normalizedSlug) {
          teamName = existingTeamName;
          break;
        }
      }
      
      // If not found, try loading team profile to get name
      if (!teamName) {
        try {
          const teamUrl = `/data/teams/${currentGender}/${currentSeason}/${teamSlug}.json`;
          const teamData = await fetchJSON(teamUrl);
          teamName = teamData.team_name || teamData.name;
        } catch (err) {
          // Skip if team profile doesn't exist
          continue;
        }
      }
      
      if (!teamName) continue;
      
      if (!teamRosters[teamName]) {
        teamRosters[teamName] = { weights: {} };
      }
      
      // Load wrestler profiles to get their weight classes
      for (const wrestlerId of teamEntry.roster) {
        if (!wrestlerId || wrestlerId.startsWith('OUTSTATE_')) continue;
        
        try {
          const profileUrl = `/data/wrestlers/${currentGender}/${currentSeason}/by_id/${wrestlerId}.json`;
          const profile = await fetchJSON(profileUrl);
          const weight = profile.weight_class;
          
          if (!weight) continue;
          
          if (!teamRosters[teamName].weights[weight]) {
            teamRosters[teamName].weights[weight] = [];
          }
          
          // Check if already added (from rankings)
          const exists = teamRosters[teamName].weights[weight].some(
            w => w.wrestler_id === String(wrestlerId)
          );
          
          if (!exists) {
            teamRosters[teamName].weights[weight].push({
              wrestler_id: String(wrestlerId),
              name: profile.name || 'Unknown',
              rank: null, // Will be filled from rankings
              is_highest_ranked: false
            });
          }
        } catch (err) {
          // Skip if profile doesn't exist
          continue;
        }
      }
    }
  } catch (err) {
    console.warn('[Dual Predictor] Could not load team rosters from index_teams.json:', err);
  }
  
  // Update ranks from rankings data
  for (const [teamName, roster] of Object.entries(teamRosters)) {
    for (const [weight, wrestlers] of Object.entries(roster.weights)) {
      const weightRankings = rankingsByWeight[weight] || [];
      for (const wrestler of wrestlers) {
        const ranked = weightRankings.find(w => w.wrestler_id === wrestler.wrestler_id);
        if (ranked) {
          wrestler.rank = ranked.rank;
          wrestler.is_highest_ranked = ranked.is_highest_ranked !== false;
        }
      }
      
      // Sort by rank (best first), with unranked at the end
      wrestlers.sort((a, b) => {
        if (a.rank === null && b.rank === null) return 0;
        if (a.rank === null) return 1;
        if (b.rank === null) return -1;
        return a.rank - b.rank;
      });
    }
  }
  
  console.log(`[Dual Predictor] Loaded rosters for ${Object.keys(teamRosters).length} teams`);
}

// Store result overrides: row -> { winner: 'A'|'B', resultType: 'Decision'|'Major Decision'|'Fall' }
const resultOverrides = new Map();

function updateMatchups() {
  if (!teamA || !teamB) {
    document.getElementById('scoreboard-container').style.display = 'none';
    document.getElementById('matchup-table-container').style.display = 'none';
    return;
  }
  
  // Show scoreboard
  document.getElementById('scoreboard-container').style.display = 'block';
  document.getElementById('scoreboard-team-a-name').textContent = teamA.toUpperCase();
  document.getElementById('scoreboard-team-b-name').textContent = teamB.toUpperCase();
  
  // Update table headers with team names
  document.getElementById('team-a-header').textContent = teamA;
  document.getElementById('team-b-header').textContent = teamB;
  
  // Clear result overrides when teams change
  resultOverrides.clear();
  
  // Render matchup table
  renderMatchupTable();
  
  // Update scores
  updateScores();
}

function renderMatchupTable() {
  const tbody = document.getElementById('matchup-table-body');
  tbody.innerHTML = '';
  
  const weights = getWeightsForGender(currentGender);
  const rosterA = teamRosters[teamA] || { weights: {} };
  const rosterB = teamRosters[teamB] || { weights: {} };
  
  weights.forEach((weight, index) => {
    const row = document.createElement('tr');
    row.dataset.weight = weight;
    
    // Weight column
    const weightCell = document.createElement('td');
    weightCell.textContent = weight;
    weightCell.style.fontWeight = '600';
    row.appendChild(weightCell);
    
    // Get wrestlers for Team A (current weight + adjacent weights)
    const teamAWrestlers = getWrestlersForWeight(rosterA, weight, weights, index);
    const starterA = getStarter(rosterA.weights[weight] || []); // Default to starter at THIS weight
    
    // Team A wrestler dropdown
    const teamACell = document.createElement('td');
    const teamASelect = createWrestlerSelect(weight, teamAWrestlers, 'A', (wrestlerId) => {
      handleWrestlerSelection(wrestlerId, weight, 'A', row);
      updateMatchupRow(row, weight, wrestlerId, 'A');
      updateScores();
    });
    teamACell.appendChild(teamASelect);
    row.appendChild(teamACell);
    
    // Result column (clickable for override)
    const resultCell = document.createElement('td');
    resultCell.className = 'result-cell';
    resultCell.style.cursor = 'pointer';
    resultCell.style.userSelect = 'none';
    resultCell.title = 'Click to override result';
    resultCell.textContent = '—';
    resultCell.onclick = () => {
      showResultOverrideModal(row, weight, null, 3);
    };
    row.appendChild(resultCell);
    
    // Get wrestlers for Team B (current weight + adjacent weights)
    const teamBWrestlers = getWrestlersForWeight(rosterB, weight, weights, index);
    const starterB = getStarter(rosterB.weights[weight] || []); // Default to starter at THIS weight
    
    // Team B wrestler dropdown
    const teamBCell = document.createElement('td');
    const teamBSelect = createWrestlerSelect(weight, teamBWrestlers, 'B', (wrestlerId) => {
      handleWrestlerSelection(wrestlerId, weight, 'B', row);
      updateMatchupRow(row, weight, wrestlerId, 'B');
      updateScores();
    });
    teamBCell.appendChild(teamBSelect);
    row.appendChild(teamBCell);
    
    // Points column (will show cumulative totals)
    const pointsCell = document.createElement('td');
    pointsCell.className = 'points-cell';
    pointsCell.textContent = '0–0'; // Initial value, will be updated by updateScores
    row.appendChild(pointsCell);
    
    tbody.appendChild(row);
    
    // Set default selections with fallback logic
    // Priority: 1) Starter at current weight, 2) Highest-ranked non-starter from weight below, 3) Forfeit
    let defaultA = 'FORFEIT';
    if (starterA) {
      defaultA = starterA.wrestler_id;
    } else {
      const nonStarterBelow = getHighestRankedNonStarterFromWeightBelow(rosterA, weight, weights, index);
      if (nonStarterBelow) {
        defaultA = nonStarterBelow.wrestler_id;
      }
    }
    teamASelect.value = defaultA;
    
    let defaultB = 'FORFEIT';
    if (starterB) {
      defaultB = starterB.wrestler_id;
    } else {
      const nonStarterBelow = getHighestRankedNonStarterFromWeightBelow(rosterB, weight, weights, index);
      if (nonStarterBelow) {
        defaultB = nonStarterBelow.wrestler_id;
      }
    }
    teamBSelect.value = defaultB;
    
    // Initial matchup calculation
    updateMatchupRow(row, weight, teamASelect.value, 'A');
    updateMatchupRow(row, weight, teamBSelect.value, 'B');
  });
  
  document.getElementById('matchup-table-container').style.display = 'block';
  updateScores();
}

function getWrestlersForWeight(roster, weight, allWeights, weightIndex) {
  // Start with wrestlers at the current weight
  const wrestlers = [...(roster.weights[weight] || [])];
  const seenIds = new Set(wrestlers.map(w => w.wrestler_id));
  
  // Add wrestlers from one weight class up (if exists)
  if (weightIndex > 0) {
    const weightUp = allWeights[weightIndex - 1];
    const wrestlersUp = roster.weights[weightUp] || [];
    wrestlersUp.forEach(w => {
      if (!seenIds.has(w.wrestler_id)) {
        wrestlers.push({ ...w, sourceWeight: weightUp });
        seenIds.add(w.wrestler_id);
      }
    });
  }
  
  // Add wrestlers from one weight class down (if exists)
  if (weightIndex < allWeights.length - 1) {
    const weightDown = allWeights[weightIndex + 1];
    const wrestlersDown = roster.weights[weightDown] || [];
    wrestlersDown.forEach(w => {
      if (!seenIds.has(w.wrestler_id)) {
        wrestlers.push({ ...w, sourceWeight: weightDown });
        seenIds.add(w.wrestler_id);
      }
    });
  }
  
  // Sort by rank (best first), with current weight wrestlers first
  wrestlers.sort((a, b) => {
    // Current weight wrestlers come first
    const aIsCurrent = !a.sourceWeight || a.sourceWeight === weight;
    const bIsCurrent = !b.sourceWeight || b.sourceWeight === weight;
    if (aIsCurrent && !bIsCurrent) return -1;
    if (!aIsCurrent && bIsCurrent) return 1;
    
    // Then sort by rank
    if (a.rank === null && b.rank === null) return 0;
    if (a.rank === null) return 1;
    if (b.rank === null) return -1;
    return a.rank - b.rank;
  });
  
  return wrestlers;
}

function getStarter(wrestlers) {
  if (!wrestlers || wrestlers.length === 0) return null;
  
  // Find highest-ranked wrestler (lowest rank number)
  return wrestlers.find(w => w.is_highest_ranked) || wrestlers[0];
}

function getHighestRankedNonStarterFromWeightBelow(roster, weight, allWeights, weightIndex) {
  // Only look at the weight class directly below (one index higher)
  if (weightIndex >= allWeights.length - 1) return null;
  
  const weightBelow = allWeights[weightIndex + 1];
  const wrestlersBelow = roster.weights[weightBelow] || [];
  
  if (wrestlersBelow.length === 0) return null;
  
  // Filter out starters (highest-ranked per team)
  const nonStarters = wrestlersBelow.filter(w => !w.is_highest_ranked);
  
  if (nonStarters.length === 0) return null;
  
  // Find highest-ranked non-starter (lowest rank number)
  const sorted = nonStarters.sort((a, b) => {
    if (a.rank === null && b.rank === null) return 0;
    if (a.rank === null) return 1;
    if (b.rank === null) return -1;
    return a.rank - b.rank;
  });
  
  // Mark with sourceWeight so display shows correctly
  return { ...sorted[0], sourceWeight: weightBelow };
}

function createWrestlerSelect(weight, wrestlers, team, onChange) {
  const select = document.createElement('select');
  select.className = 'wrestler-select';
  select.dataset.weight = weight;
  select.dataset.team = team;
  
  // Forfeit option (only non-wrestler option)
  const forfeitOption = document.createElement('option');
  forfeitOption.value = 'FORFEIT';
  forfeitOption.textContent = 'Forfeit';
  select.appendChild(forfeitOption);
  
  // Group wrestlers by source weight
  const currentWeightWrestlers = wrestlers.filter(w => !w.sourceWeight || w.sourceWeight === weight);
  const adjacentWeightWrestlers = wrestlers.filter(w => w.sourceWeight && w.sourceWeight !== weight);
  
  // Add current weight wrestlers
  if (currentWeightWrestlers.length > 0) {
    currentWeightWrestlers.forEach(wrestler => {
      const option = document.createElement('option');
      option.value = wrestler.wrestler_id;
      // At normal weight: just show rank
      const rankText = wrestler.rank ? `#${wrestler.rank}` : 'Unranked';
      option.textContent = `${wrestler.name} (${rankText})`;
      option.dataset.rank = wrestler.rank || '';
      option.dataset.actualWeight = weight; // Store actual weight for this matchup
      select.appendChild(option);
    });
  }
  
  // Add adjacent weight wrestlers with label
  if (adjacentWeightWrestlers.length > 0) {
    // Add separator if we have current weight wrestlers
    if (currentWeightWrestlers.length > 0) {
      const separator = document.createElement('option');
      separator.disabled = true;
      separator.textContent = '──────────';
      select.appendChild(separator);
    }
    
    // Group adjacent wrestlers by weight
    const byWeight = {};
    adjacentWeightWrestlers.forEach(w => {
      const wWeight = w.sourceWeight;
      if (!byWeight[wWeight]) byWeight[wWeight] = [];
      byWeight[wWeight].push(w);
    });
    
    Object.keys(byWeight).sort().forEach(wWeight => {
      const weightLabel = document.createElement('option');
      weightLabel.disabled = true;
      weightLabel.textContent = `From ${wWeight} lbs:`;
      select.appendChild(weightLabel);
      
      byWeight[wWeight].forEach(wrestler => {
        const option = document.createElement('option');
        option.value = wrestler.wrestler_id;
        // At different weight: show rank @ actual weight
        const rankText = wrestler.rank ? `#${wrestler.rank} @ ${wWeight}` : `Unranked @ ${wWeight}`;
        option.textContent = `${wrestler.name} (${rankText})`;
        option.dataset.rank = wrestler.rank || '';
        option.dataset.actualWeight = wWeight; // Store actual weight class
        select.appendChild(option);
      });
    });
  }
  
  select.addEventListener('change', () => {
    onChange(select.value);
  });
  
  return select;
}

function handleWrestlerSelection(wrestlerId, weight, team, currentRow) {
  // If selecting a real wrestler (not empty, not FORFEIT), check for duplicates
  if (wrestlerId && wrestlerId !== 'FORFEIT') {
    // Find all other rows with this wrestler selected
    const allRows = document.querySelectorAll('#matchup-table-body tr');
    allRows.forEach(row => {
      if (row === currentRow) return; // Skip current row
      
      const selectA = row.querySelector('select[data-team="A"]');
      const selectB = row.querySelector('select[data-team="B"]');
      
      // Check Team A select
      if (selectA && selectA.value === wrestlerId) {
        selectA.value = 'FORFEIT';
        const rowWeight = row.dataset.weight;
        updateMatchupRow(row, rowWeight, 'FORFEIT', 'A');
      }
      
      // Check Team B select
      if (selectB && selectB.value === wrestlerId) {
        selectB.value = 'FORFEIT';
        const rowWeight = row.dataset.weight;
        updateMatchupRow(row, rowWeight, 'FORFEIT', 'B');
      }
    });
  }
}

function getResultTypeFromPoints(points) {
  if (points === 3) return 'Decision';
  if (points === 4) return 'Major Decision';
  if (points === 6) return 'Fall';
  return 'Decision'; // Default
}

function getPointsFromResultType(resultType) {
  if (resultType === 'Decision') return 3;
  if (resultType === 'Major Decision') return 4;
  if (resultType === 'Fall') return 6;
  return 3; // Default
}

function showResultOverrideModal(row, weight, currentWinner, currentPoints) {
  const currentResultType = getResultTypeFromPoints(currentPoints);
  const existingOverride = resultOverrides.get(row);
  
  // Use override values if they exist, otherwise use calculated values
  const displayWinner = existingOverride?.winner || currentWinner || 'A';
  const displayResultType = existingOverride?.resultType || currentResultType;
  
  // Create modal overlay
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 1000; display: flex; align-items: center; justify-content: center;';
  
  const modal = document.createElement('div');
  modal.style.cssText = 'background: white; padding: 2em; border-radius: 8px; min-width: 300px;';
  
  modal.innerHTML = `
    <h3 style="margin-top: 0;">Override Result - ${weight} lbs</h3>
    <div style="margin-bottom: 1em;">
      <label style="display: block; margin-bottom: 0.5em; font-weight: 600;">Winner:</label>
      <select id="override-winner" style="width: 100%; padding: 0.5em;">
        <option value="A" ${displayWinner === 'A' ? 'selected' : ''}>${teamA}</option>
        <option value="B" ${displayWinner === 'B' ? 'selected' : ''}>${teamB}</option>
      </select>
    </div>
    <div style="margin-bottom: 1.5em;">
      <label style="display: block; margin-bottom: 0.5em; font-weight: 600;">Result Type:</label>
      <select id="override-result-type" style="width: 100%; padding: 0.5em;">
        <option value="Decision" ${displayResultType === 'Decision' ? 'selected' : ''}>Decision (3 pts)</option>
        <option value="Major Decision" ${displayResultType === 'Major Decision' ? 'selected' : ''}>Major Decision (4 pts)</option>
        <option value="Fall" ${displayResultType === 'Fall' ? 'selected' : ''}>Fall (6 pts)</option>
      </select>
    </div>
    <div style="display: flex; gap: 1em; justify-content: flex-end;">
      <button id="override-cancel" style="padding: 0.5em 1em; background: #ccc; border: none; border-radius: 4px; cursor: pointer;">Cancel</button>
      <button id="override-clear" style="padding: 0.5em 1em; background: #ff6b6b; border: none; border-radius: 4px; cursor: pointer; color: white; ${existingOverride ? '' : 'display: none;'}">Clear Override</button>
      <button id="override-save" style="padding: 0.5em 1em; background: var(--accent-primary); border: none; border-radius: 4px; cursor: pointer; color: white;">Save</button>
    </div>
  `;
  
  overlay.appendChild(modal);
  document.body.appendChild(overlay);
  
  // Handle cancel
  document.getElementById('override-cancel').addEventListener('click', () => {
    document.body.removeChild(overlay);
  });
  
  // Handle clear override
  document.getElementById('override-clear').addEventListener('click', () => {
    resultOverrides.delete(row);
    document.body.removeChild(overlay);
    updateMatchupRow(row, weight, null, null);
    updateScores();
  });
  
  // Handle save
  document.getElementById('override-save').addEventListener('click', () => {
    const winner = document.getElementById('override-winner').value;
    const resultType = document.getElementById('override-result-type').value;
    
    resultOverrides.set(row, { winner, resultType });
    document.body.removeChild(overlay);
    updateMatchupRow(row, weight, null, null);
    updateScores();
  });
  
  // Close on overlay click
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) {
      document.body.removeChild(overlay);
    }
  });
}

function updateMatchupRow(row, weight, wrestlerId, team) {
  const selectA = row.querySelector('select[data-team="A"]');
  const selectB = row.querySelector('select[data-team="B"]');
  const resultCell = row.querySelector('.result-cell');
  const pointsCell = row.querySelector('.points-cell');
  
  if (!selectA || !selectB || !resultCell || !pointsCell) return;
  
  const wrestlerAId = selectA.value;
  const wrestlerBId = selectB.value;
  
  // Treat FORFEIT as empty for logic purposes
  const effectiveAId = (wrestlerAId === 'FORFEIT' || !wrestlerAId) ? null : wrestlerAId;
  const effectiveBId = (wrestlerBId === 'FORFEIT' || !wrestlerBId) ? null : wrestlerBId;
  
  // Check for override first
  const override = resultOverrides.get(row);
  
  if (override) {
    // Use override values
    const winner = override.winner;
    const resultType = override.resultType;
    const points = getPointsFromResultType(resultType);
    
    resultCell.innerHTML = '';
    
    if (winner === 'A') {
      const triangle = document.createElement('span');
      triangle.className = 'winner-triangle winner-triangle-left';
      triangle.innerHTML = '◀';
      resultCell.appendChild(triangle);
      resultCell.appendChild(document.createTextNode(resultType));
      // Don't set points here - updateScores will set cumulative totals
    } else {
      resultCell.appendChild(document.createTextNode(resultType));
      const triangle = document.createElement('span');
      triangle.className = 'winner-triangle winner-triangle-right';
      triangle.innerHTML = '▶';
      resultCell.appendChild(triangle);
      // Don't set points here - updateScores will set cumulative totals
    }
    
    // Make result cell clickable (with override values)
    resultCell.onclick = () => {
      showResultOverrideModal(row, weight, winner, points);
    };
    
    // Update scores to recalculate cumulative totals
    updateScores();
    return;
  }
  
  // If no wrestler selected for either team, clear result
  if (!effectiveAId && !effectiveBId) {
    resultCell.innerHTML = '—';
    // Don't set points here - updateScores will set cumulative totals
    resultCell.onclick = () => {
      showResultOverrideModal(row, weight, null, 3);
    };
    updateScores();
    return;
  }
  
  // If only one team has a wrestler, they win by forfeit (6 points)
  if (!effectiveAId && effectiveBId) {
    resultCell.innerHTML = '';
    const triangle = document.createElement('span');
    triangle.className = 'winner-triangle winner-triangle-right';
    triangle.innerHTML = '▶';
    resultCell.appendChild(triangle);
    resultCell.appendChild(document.createTextNode('Forfeit'));
    // Don't set points here - updateScores will set cumulative totals
    resultCell.onclick = () => {
      showResultOverrideModal(row, weight, 'B', 6);
    };
    updateScores();
    return;
  }
  
  if (effectiveAId && !effectiveBId) {
    resultCell.innerHTML = '';
    const triangle = document.createElement('span');
    triangle.className = 'winner-triangle winner-triangle-left';
    triangle.innerHTML = '◀';
    resultCell.appendChild(triangle);
    resultCell.appendChild(document.createTextNode('Forfeit'));
    // Don't set points here - updateScores will set cumulative totals
    resultCell.onclick = () => {
      showResultOverrideModal(row, weight, 'A', 6);
    };
    updateScores();
    return;
  }
  
  // Both wrestlers selected - get their actual weights and ranks
  const wrestlerAInfo = getWrestlerInfo(effectiveAId, selectA, weight);
  const wrestlerBInfo = getWrestlerInfo(effectiveBId, selectB, weight);
  
  // Adjust ranks based on weight class differences
  const adjustedRankA = adjustRankForWeightClass(wrestlerAInfo.rank, wrestlerAInfo.actualWeight, weight);
  const adjustedRankB = adjustRankForWeightClass(wrestlerBInfo.rank, wrestlerBInfo.actualWeight, weight);
  
  let winner = null;
  let points = 3; // Default to regular decision
  
  if (adjustedRankA === null && adjustedRankB === null) {
    // Both unranked - default to Team A, regular decision
    winner = 'A';
    points = 3;
  } else if (adjustedRankA === null) {
    winner = 'B';
    points = 3;
  } else if (adjustedRankB === null) {
    winner = 'A';
    points = 3;
  } else {
    // Determine winner and calculate points based on rank difference
    const rankDiff = Math.abs(adjustedRankA - adjustedRankB);
    
    if (adjustedRankA < adjustedRankB) {
      winner = 'A';
      points = calculatePointsForRankDifference(rankDiff, currentGender);
    } else if (adjustedRankB < adjustedRankA) {
      winner = 'B';
      points = calculatePointsForRankDifference(rankDiff, currentGender);
    } else {
      // Tie - default to Team A, regular decision
      winner = 'A';
      points = 3;
    }
  }
  
  // Get result type from points
  const resultType = getResultTypeFromPoints(points);
  
  // Clear previous content
  resultCell.innerHTML = '';
  
  if (winner === 'A') {
    // Team A wins - triangle pointing left
    const triangle = document.createElement('span');
    triangle.className = 'winner-triangle winner-triangle-left';
    triangle.innerHTML = '◀';
    resultCell.appendChild(triangle);
    resultCell.appendChild(document.createTextNode(resultType));
    // Don't set points here - updateScores will set cumulative totals
  } else {
    // Team B wins - triangle pointing right
    resultCell.appendChild(document.createTextNode(resultType));
    const triangle = document.createElement('span');
    triangle.className = 'winner-triangle winner-triangle-right';
    triangle.innerHTML = '▶';
    resultCell.appendChild(triangle);
    // Don't set points here - updateScores will set cumulative totals
  }
  
  // Make result cell clickable (always set, even if override exists)
  resultCell.onclick = () => {
    showResultOverrideModal(row, weight, winner, points);
  };
  
  // Store current calculated values for override modal
  resultCell.dataset.calculatedWinner = winner;
  resultCell.dataset.calculatedPoints = points;
  
  // Update scores to recalculate cumulative totals
  updateScores();
}

function getWrestlerInfo(wrestlerId, selectElement, matchupWeight) {
  // Handle FORFEIT or empty/null cases
  if (!wrestlerId || wrestlerId === 'FORFEIT') {
    return { rank: null, actualWeight: matchupWeight };
  }
  
  const roster = selectElement.dataset.team === 'A' ? teamRosters[teamA] : teamRosters[teamB];
  if (!roster) return { rank: null, actualWeight: matchupWeight };
  
  // Find wrestler in roster to get their actual weight class
  let actualWeight = matchupWeight;
  let rank = null;
  
  // Check all weight classes
  for (const [w, wrestlers] of Object.entries(roster.weights)) {
    const wrestler = wrestlers.find(wr => wr.wrestler_id === wrestlerId);
    if (wrestler) {
      actualWeight = parseInt(w);
      rank = wrestler.rank;
      break;
    }
  }
  
  // If not found in roster, try rankings
  if (rank === null) {
    for (const [w, rankings] of Object.entries(rankingsByWeight)) {
      const ranked = rankings.find(wr => wr.wrestler_id === wrestlerId);
      if (ranked) {
        actualWeight = parseInt(w);
        rank = ranked.rank;
        break;
      }
    }
  }
  
  return { rank, actualWeight };
}

function adjustRankForWeightClass(rank, actualWeight, matchupWeight) {
  if (rank === null) return null;
  
  const actualWeightNum = parseInt(actualWeight);
  const matchupWeightNum = parseInt(matchupWeight);
  
  // If wrestler is from weight class below, add 2.5 to rank
  if (actualWeightNum < matchupWeightNum) {
    return rank + 2.5;
  }
  
  // If wrestler is from weight class above, use rank as-is (move down)
  // If same weight, use rank as-is
  return rank;
}

function calculatePointsForRankDifference(rankDiff, gender) {
  if (gender === 'boys') {
    if (rankDiff >= 1 && rankDiff <= 7) {
      return 3; // Regular decision
    } else if (rankDiff >= 8 && rankDiff <= 14) {
      return 4; // Major decision
    } else if (rankDiff >= 15) {
      return 6; // Fall
    }
  } else if (gender === 'girls') {
    if (rankDiff >= 1 && rankDiff <= 4) {
      return 3; // Regular decision
    } else if (rankDiff >= 5 && rankDiff <= 8) {
      return 4; // Major decision
    } else if (rankDiff >= 9) {
      return 6; // Fall
    }
  }
  
  // Default to regular decision
  return 3;
}


function updateScores() {
  let scoreA = 0;
  let scoreB = 0;
  
  const rows = Array.from(document.querySelectorAll('#matchup-table-body tr'));
  
  // Calculate cumulative totals row by row
  rows.forEach((row, index) => {
    const resultCell = row.querySelector('.result-cell');
    const pointsCell = row.querySelector('.points-cell');
    const selectA = row.querySelector('select[data-team="A"]');
    const selectB = row.querySelector('select[data-team="B"]');
    
    if (!resultCell || !pointsCell) return;
    
    // Get points for this match
    let matchPointsA = 0;
    let matchPointsB = 0;
    
    // Check for override first
    const override = resultOverrides.get(row);
    
    if (override) {
      const points = getPointsFromResultType(override.resultType);
      if (override.winner === 'A') {
        matchPointsA = points;
      } else {
        matchPointsB = points;
      }
    } else {
      // Calculate from wrestlers
      const wrestlerAId = selectA?.value;
      const wrestlerBId = selectB?.value;
      
      const effectiveAId = (wrestlerAId === 'FORFEIT' || !wrestlerAId) ? null : wrestlerAId;
      const effectiveBId = (wrestlerBId === 'FORFEIT' || !wrestlerBId) ? null : wrestlerBId;
      
      if (!effectiveAId && effectiveBId) {
        matchPointsB = 6; // Forfeit
      } else if (effectiveAId && !effectiveBId) {
        matchPointsA = 6; // Forfeit
      } else if (effectiveAId && effectiveBId) {
        const weight = parseInt(row.dataset.weight);
        const wrestlerAInfo = getWrestlerInfo(effectiveAId, selectA, weight);
        const wrestlerBInfo = getWrestlerInfo(effectiveBId, selectB, weight);
        
        const adjustedRankA = adjustRankForWeightClass(wrestlerAInfo.rank, wrestlerAInfo.actualWeight, weight);
        const adjustedRankB = adjustRankForWeightClass(wrestlerBInfo.rank, wrestlerBInfo.actualWeight, weight);
        
        let winner = null;
        let points = 3;
        
        if (adjustedRankA === null && adjustedRankB === null) {
          winner = 'A';
          points = 3;
        } else if (adjustedRankA === null) {
          winner = 'B';
          points = 3;
        } else if (adjustedRankB === null) {
          winner = 'A';
          points = 3;
        } else {
          const rankDiff = Math.abs(adjustedRankA - adjustedRankB);
          if (adjustedRankA < adjustedRankB) {
            winner = 'A';
            points = calculatePointsForRankDifference(rankDiff, currentGender);
          } else if (adjustedRankB < adjustedRankA) {
            winner = 'B';
            points = calculatePointsForRankDifference(rankDiff, currentGender);
          } else {
            winner = 'A';
            points = 3;
          }
        }
        
        if (winner === 'A') {
          matchPointsA = points;
        } else {
          matchPointsB = points;
        }
      }
    }
    
    // Add to running totals
    scoreA += matchPointsA;
    scoreB += matchPointsB;
    
    // Update points cell to show cumulative total
    pointsCell.textContent = `${scoreA}–${scoreB}`;
  });
  
  document.getElementById('scoreboard-team-a-score').textContent = scoreA;
  document.getElementById('scoreboard-team-b-score').textContent = scoreB;
}

// Helper function for JSON fetching
async function fetchJSON(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  return response.json();
}

// Initialize on page load
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

