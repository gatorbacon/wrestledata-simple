// ========================================
// Leaderboards Page
// Loads pre-built leaderboard JSON and displays with gender/tab switching
// ========================================

let currentGender = 'boys';
let currentStat = 'wins';
let leaderboardData = {
  boys: null,
  girls: null
};

/**
 * Load leaderboard data for a gender
 */
async function loadLeaderboardData(gender) {
  const season = getSeasonFromURL();
  const url = `/data/leaderboards/${gender}/${season}/leaderboards.json`;
  
  try {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Failed to load leaderboard data: ${response.status}`);
    }
    const data = await response.json();
    leaderboardData[gender] = data;
    console.log(`Loaded leaderboard data for ${gender}:`, data);
    return data;
  } catch (error) {
    console.error(`Error loading leaderboard data for ${gender}:`, error);
    return null;
  }
}

/**
 * Render the leaderboard table
 */
function renderLeaderboard() {
  const data = leaderboardData[currentGender];
  if (!data) {
    document.getElementById('leaderboard-tbody').innerHTML = 
      '<tr><td colspan="6" style="text-align: center; padding: 2em; color: var(--text-secondary);">Loading...</td></tr>';
    return;
  }

  const entries = data[currentStat] || [];
  const tbody = document.getElementById('leaderboard-tbody');
  
  if (entries.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 2em; color: var(--text-secondary);">No data available</td></tr>';
    return;
  }

  // Update stat header
  const statHeader = document.getElementById('stat-header');
  const statLabels = {
    wins: 'Wins',
    pins: 'Pins',
    techs: 'Techs'
  };
  statHeader.textContent = statLabels[currentStat] || 'Stat';

  // Clear table
  tbody.innerHTML = '';

  // Render rows
  entries.forEach((entry, index) => {
    const tr = document.createElement('tr');
    
    // Rank (leaderboard position)
    const rankTd = document.createElement('td');
    rankTd.textContent = index + 1;
    rankTd.style.fontWeight = '600';
    tr.appendChild(rankTd);

    // Name (linked to wrestler profile)
    const nameTd = document.createElement('td');
    nameTd.className = 'name';
    const nameLink = document.createElement('a');
    nameLink.href = buildPageURL('wrestler.html', currentGender, { id: entry.wrestler_id });
    nameLink.textContent = entry.name;
    nameTd.appendChild(nameLink);
    tr.appendChild(nameTd);

    // Team
    const teamTd = document.createElement('td');
    teamTd.textContent = entry.team || '—';
    tr.appendChild(teamTd);

    // Rank (wrestler rank)
    const wrestlerRankTd = document.createElement('td');
    wrestlerRankTd.textContent = entry.rank === 999 ? '—' : entry.rank;
    wrestlerRankTd.style.textAlign = 'center';
    tr.appendChild(wrestlerRankTd);

    // W-L Record
    const recordTd = document.createElement('td');
    recordTd.textContent = `${entry.wins}–${entry.losses}`;
    recordTd.style.textAlign = 'center';
    tr.appendChild(recordTd);

    // Stat column (Wins/Pins/Techs)
    const statTd = document.createElement('td');
    statTd.textContent = entry[currentStat] || 0;
    statTd.style.textAlign = 'center';
    statTd.style.fontWeight = '600';
    tr.appendChild(statTd);

    tbody.appendChild(tr);
  });
}

/**
 * Setup gender toggle
 */
function setupGenderToggle() {
  const boysBtn = document.getElementById('gender-toggle-boys');
  const girlsBtn = document.getElementById('gender-toggle-girls');

  boysBtn.addEventListener('click', async () => {
    currentGender = 'boys';
    boysBtn.classList.add('active');
    girlsBtn.classList.remove('active');
    
    // Load data if not already loaded
    if (!leaderboardData.boys) {
      await loadLeaderboardData('boys');
    }
    
    renderLeaderboard();
  });

  girlsBtn.addEventListener('click', async () => {
    currentGender = 'girls';
    girlsBtn.classList.add('active');
    boysBtn.classList.remove('active');
    
    // Load data if not already loaded
    if (!leaderboardData.girls) {
      await loadLeaderboardData('girls');
    }
    
    renderLeaderboard();
  });
}

/**
 * Setup stat tabs
 */
function setupStatTabs() {
  const tabs = document.querySelectorAll('.stat-tab');
  
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      // Update active tab
      tabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      
      // Update current stat
      currentStat = tab.dataset.stat;
      
      // Re-render table (data already loaded)
      renderLeaderboard();
    });
  });
}

/**
 * Initialize page
 */
async function init() {
  // Set season info
  const season = getSeasonFromURL();
  document.getElementById('season-info').textContent = `Season ${season}`;

  // Setup UI controls
  setupGenderToggle();
  setupStatTabs();

  // Load initial data (boys, wins)
  currentGender = 'boys';
  currentStat = 'wins';
  
  await loadLeaderboardData('boys');
  renderLeaderboard();
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

