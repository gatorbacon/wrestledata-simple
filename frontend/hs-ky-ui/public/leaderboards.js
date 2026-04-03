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
    
    // Also load career_wins from separate file if it exists
    if (data.career_wins && data.career_wins.length > 0) {
      // Already included in leaderboards.json
      leaderboardData[gender] = data;
    } else {
      // Try loading from separate file
      try {
        const careerWinsUrl = `/data/leaderboards/${gender}/${season}/career_wins.json`;
        const careerWinsResponse = await fetch(careerWinsUrl);
        if (careerWinsResponse.ok) {
          const careerWinsData = await careerWinsResponse.json();
          data.career_wins = careerWinsData;
        }
      } catch (e) {
        console.warn('Could not load career_wins.json:', e);
      }
      leaderboardData[gender] = data;
    }
    
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

  // Update table headers based on stat type (must be done before checking entries)
  updateTableHeaders();

  // Career Wins only: show/hide note and legend; set note year from data
  const noteEl = document.getElementById('career-wins-note');
  const legendEl = document.getElementById('career-wins-legend');
  if (noteEl && legendEl) {
    if (currentStat === 'career_wins') {
      const year = data.career_earliest_season;
      noteEl.textContent = year != null
        ? `Note: Career records include match data starting with the ${year} season.`
        : '';
      noteEl.style.display = noteEl.textContent ? 'block' : 'none';
      legendEl.textContent = 'Graduation year colors indicate class • Outlined pills indicate graduated wrestlers';
      legendEl.style.display = 'block';
    } else {
      noteEl.style.display = 'none';
      legendEl.style.display = 'none';
    }
  }

  const entries = data[currentStat] || [];
  const tbody = document.getElementById('leaderboard-tbody');
  
  const colCount = currentStat === 'career_wins' ? 6 : 6;
  if (entries.length === 0) {
    tbody.innerHTML = `<tr><td colspan="${colCount}" style="text-align: center; padding: 2em; color: var(--text-secondary);">No data available</td></tr>`;
    return;
  }

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

    // Name (linked to wrestler profile only when profile exists; Career Wins inactive = no link)
    const nameTd = document.createElement('td');
    nameTd.className = 'name';
    const seasonYear = parseInt(getSeasonFromURL(), 10) || 2026;
    const gradYear = entry.graduation_year != null ? parseInt(entry.graduation_year, 10) : null;
    const isActive = currentStat !== 'career_wins' || gradYear == null || gradYear >= seasonYear;
    if (isActive) {
      const nameLink = document.createElement('a');
      nameLink.href = buildPageURL('wrestler.html', currentGender, { id: entry.wrestler_id });
      nameLink.textContent = entry.name;
      nameTd.appendChild(nameLink);
    } else {
      nameTd.textContent = entry.name;
    }
    if (currentStat === 'career_wins' && entry.state_medals && entry.state_medals.length > 0) {
      const medalMap = { 1: '🥇', 2: '🥈', 3: '🥉' };
      const medalSpan = document.createElement('span');
      medalSpan.className = 'state-medals';
      medalSpan.textContent = entry.state_medals.map(p => medalMap[p] || '').join('');
      nameTd.appendChild(medalSpan);
    }
    tr.appendChild(nameTd);

    // Team
    const teamTd = document.createElement('td');
    teamTd.textContent = entry.team || '—';
    tr.appendChild(teamTd);

    if (currentStat === 'career_wins') {
      // Career Wins: Career Record, Winning %
      // Career Record
      const recordTd = document.createElement('td');
      recordTd.textContent = entry.career_record || '—';
      recordTd.style.textAlign = 'center';
      tr.appendChild(recordTd);

      // Winning Percentage
      const winPctTd = document.createElement('td');
      if (entry.win_pct !== null && entry.win_pct !== undefined) {
        const winPctFormatted = entry.win_pct.toFixed(3).replace(/^0\./, '.');
        winPctTd.textContent = winPctFormatted;
      } else {
        winPctTd.textContent = '—';
      }
      winPctTd.style.textAlign = 'center';
      winPctTd.style.fontWeight = '600';
      tr.appendChild(winPctTd);

      // Graduation year pill (active = filled by class; inactive = outlined)
      const gradTd = document.createElement('td');
      gradTd.style.textAlign = 'center';
      const seasonYear = parseInt(getSeasonFromURL(), 10) || 2026;
      const gradYear = entry.graduation_year != null ? parseInt(entry.graduation_year, 10) : null;
      if (gradYear == null) {
        gradTd.textContent = '—';
      } else {
        const span = document.createElement('span');
        span.className = getGraduationPillClass(gradYear, seasonYear);
        span.textContent = String(gradYear);
        gradTd.appendChild(span);
      }
      tr.appendChild(gradTd);
    } else {
      // Regular stats: Rank, W-L, Stat
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
    }

    tbody.appendChild(tr);
  });
}

/**
 * Graduation pill CSS class: active = filled by class (senior/junior/soph/freshman), inactive = outlined
 * currentSeasonYear = e.g. 2026; graduation_year from entry
 */
function getGraduationPillClass(graduationYear, currentSeasonYear) {
  const base = 'graduation-pill';
  if (graduationYear < currentSeasonYear) {
    return base + ' graduation-pill--outlined';
  }
  if (graduationYear === currentSeasonYear) return base + ' graduation-pill--senior';
  if (graduationYear === currentSeasonYear + 1) return base + ' graduation-pill--junior';
  if (graduationYear === currentSeasonYear + 2) return base + ' graduation-pill--sophomore';
  return base + ' graduation-pill--freshman';
}

/**
 * Update table headers based on current stat type
 */
function updateTableHeaders() {
  const thead = document.querySelector('#leaderboard-table thead tr');
  if (!thead) return;
  
  if (currentStat === 'career_wins') {
    // Career Wins headers: #, Name, Team, Career Record, Winning %, Graduation
    const headers = ['#', 'Name', 'Team', 'Career Record', 'Winning %', 'Graduation'];
    thead.innerHTML = '';
    headers.forEach((headerText, index) => {
      const th = document.createElement('th');
      th.textContent = headerText;
      if (index === headers.length - 1) {
        th.id = 'stat-header';
      }
      thead.appendChild(th);
    });
  } else {
    // Regular stats headers: #, Name, Team, Rank, W–L, Stat
    const headers = ['#', 'Name', 'Team', 'Rank', 'W–L', 'Wins'];
    thead.innerHTML = '';
    headers.forEach((headerText, index) => {
      const th = document.createElement('th');
      th.textContent = headerText;
      if (index === headers.length - 1) {
        th.id = 'stat-header';
      }
      thead.appendChild(th);
    });
    // Update stat header text
    const statHeader = document.getElementById('stat-header');
    const statLabels = {
      wins: 'Wins',
      pins: 'Pins',
      techs: 'Techs'
    };
    if (statHeader) {
      statHeader.textContent = statLabels[currentStat] || 'Stat';
    }
  }
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

