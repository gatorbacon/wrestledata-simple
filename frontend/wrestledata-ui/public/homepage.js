// ========================================
// MatSavant Homepage
// ========================================

function getSeasonMode() {
  const month = new Date().getMonth() + 1;
  return (month >= 11 || month <= 3) ? 'in-season' : 'post-season';
}

function resolveSeason() {
  return "2026";
}

function teamNameToSlug(name) {
  if (!name) return "";
  return name.toLowerCase()
    .replace(/\s+/g, "_")
    .replace(/[^\w_]/g, "")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function getMinMatchThreshold() {
  const now = new Date();
  const month = now.getMonth() + 1;
  const day = now.getDate();
  if (month < 12) return 3;
  if (month === 12 && day < 15) return 4;
  return 5;
}

// ========================================
// DATA LOADING
// ========================================

async function loadTournamentData() {
  const season = resolveSeason();
  try {
    const res = await fetch(`/data/${season}/simulation_replay.json`);
    if (!res.ok) return null;
    return await res.json();
  } catch { return null; }
}

async function loadMIData(weightFilter = 'all') {
  const season = resolveSeason();
  try {
    const res = await fetch(`/data/mat_value/${season}/mat_value_${season}.json`);
    if (!res.ok) return [];
    const all = await res.json();
    const minMatches = getMinMatchThreshold();
    let filtered = all.filter(e => e.matches >= minMatches);
    if (weightFilter !== 'all') {
      const wt = parseInt(weightFilter);
      filtered = filtered.filter(e => e.weight === wt);
    }
    filtered.sort((a, b) => {
      if (b.mv_avg !== a.mv_avg) return b.mv_avg - a.mv_avg;
      if (b.matches !== a.matches) return b.matches - a.matches;
      return (a.current_rank || 9999) - (b.current_rank || 9999);
    });
    return filtered.slice(0, 10);
  } catch { return []; }
}

async function loadRankingsData(weight) {
  const season = resolveSeason();
  if (weight === 'all') {
    const weights = ['125','133','141','149','157','165','174','184','197','285'];
    const results = [];
    await Promise.all(weights.map(async wt => {
      try {
        const res = await fetch(`/data/rankings/${season}/rankings_starters_${wt}.json`);
        if (!res.ok) return;
        const data = await res.json();
        const top = (data.rankings || []).find(r => r.rank === 1);
        if (top) results.push({ ...top, displayWeight: wt });
      } catch {}
    }));
    return results.sort((a, b) => parseInt(a.displayWeight) - parseInt(b.displayWeight));
  }
  try {
    const res = await fetch(`/data/rankings/${season}/rankings_starters_${weight}.json`);
    if (!res.ok) return [];
    const data = await res.json();
    return (data.rankings || []).slice(0, 10);
  } catch { return []; }
}

async function loadStatLeaderboard(stat) {
  try {
    const res = await fetch(`/data/leaderboards/${stat}.json`);
    if (!res.ok) return [];
    return await res.json();
  } catch { return []; }
}

// ========================================
// RENDERING
// ========================================

function renderXTPTeams(data) {
  const container = document.getElementById('xtp-teams-list');
  if (!container || !data) return;

  const cp = data.current_projection || {};
  const teams = Object.entries(cp)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([team, score], i) => ({ rank: i + 1, team, score }));

  if (teams.length === 0) {
    container.innerHTML = '<div class="analytics-empty">No data available</div>';
    return;
  }

  const rankCls = r => r === 1 ? 'gold' : r === 2 ? 'silver' : r === 3 ? 'bronze' : '';

  container.innerHTML = '';
  teams.forEach(t => {
    const row = document.createElement('div');
    row.className = 'analytics-row xtp-team-row';
    row.innerHTML =
      `<div class="row-rank ${rankCls(t.rank)}">${t.rank}</div>` +
      `<div class="row-name"><a href="/team.html?team=${teamNameToSlug(t.team)}">${t.team}</a></div>` +
      `<div class="row-value">${t.score.toFixed(1)}</div>`;
    container.appendChild(row);
  });
}

function renderTparList(data) {
  const container = document.getElementById('tpar-list');
  if (!container) return;
  container.innerHTML = '';

  if (!data || data.length === 0) {
    container.innerHTML = '<div class="analytics-empty">No data available</div>';
    return;
  }

  data.forEach((entry, i) => {
    const row = document.createElement('div');
    row.className = 'analytics-row tpar-row';
    const sign = entry.mv_avg >= 0 ? '+' : '';
    const valClass = entry.mv_avg >= 0 ? 'tpar-value-pos' : 'tpar-value-neg';
    row.innerHTML =
      `<div class="row-rank">${i + 1}</div>` +
      `<div class="row-name"><a href="/wrestler.html?id=${entry.wrestler_id}">${entry.name}</a></div>` +
      `<div class="row-team">${entry.team || '—'}</div>` +
      `<div class="row-value ${valClass}">${sign}${entry.mv_avg.toFixed(2)}</div>`;
    container.appendChild(row);
  });
}

function renderRankingsPanel(data, weight) {
  const container = document.getElementById('rankings-list');
  const allLink = document.getElementById('rankings-all-link');
  if (!container) return;

  if (allLink) {
    allLink.href = weight === 'all' ? '/rankings.html' : `/rankings.html?weight=${weight}`;
  }

  container.innerHTML = '';

  if (!data || data.length === 0) {
    container.innerHTML = '<div class="analytics-empty">No data available</div>';
    return;
  }

  data.forEach((entry, i) => {
    const row = document.createElement('div');
    row.className = 'analytics-row rankings-row';
    const displayRank = weight === 'all' ? '1' : entry.rank;
    const rightCol = weight === 'all'
      ? `<div class="row-value row-weight-chip">${entry.displayWeight}</div>`
      : `<div class="row-value row-record">${entry.record || '—'}</div>`;
    row.innerHTML =
      `<div class="row-rank">${displayRank}</div>` +
      `<div class="row-name"><a href="/wrestler.html?id=${entry.wrestler_id}">${entry.name}</a></div>` +
      `<div class="row-team">${entry.team || '—'}</div>` +
      rightCol;
    container.appendChild(row);
  });
}

function renderStatLeaders(data, stat) {
  const tbody = document.querySelector('#stats-table tbody');
  const titleLink = document.getElementById('stat-leaders-title-link');
  if (!tbody) return;

  if (titleLink) titleLink.href = `/leaderboards/leaderboard_${stat}.html`;

  tbody.innerHTML = '';
  const top10 = (data || []).slice(0, 10);

  if (top10.length === 0) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = 4;
    td.style.cssText = 'text-align:center;padding:1.5em;color:var(--muted);font-size:0.8rem;';
    td.textContent = 'No data available';
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  top10.forEach((entry, i) => {
    const tr = document.createElement('tr');
    tr.innerHTML =
      `<td>${i + 1}</td>` +
      `<td class="name"><a href="/wrestler.html?id=${entry.wrestler_id}">${entry.name}</a></td>` +
      `<td>${entry.team || '—'}</td>` +
      `<td class="num">${entry.count || '—'}</td>`;
    tbody.appendChild(tr);
  });
}

// ========================================
// INIT
// ========================================

let selectedTparWeight = 'all';
let selectedRankingsWeight = 'all';
const miCache = {};
const rankingsCache = {};

async function initHomepage() {
  const season = resolveSeason();
  const mode = getSeasonMode();

  // Update season badge (inside xTP panel)
  const badge = document.getElementById('season-badge');
  if (badge) {
    badge.textContent = mode === 'post-season' ? `${season} Archive` : `${season} Season`;
  }

  // Load all initial data in parallel
  const [replayData, miData, rankingsData, pinsData] = await Promise.all([
    loadTournamentData(),
    loadMIData('all'),
    loadRankingsData('all'),
    loadStatLeaderboard('pins'),
  ]);

  miCache['all'] = miData;
  rankingsCache['all'] = rankingsData;

  renderXTPTeams(replayData);
  renderTparList(miData);
  renderRankingsPanel(rankingsData, 'all');
  renderStatLeaders(pinsData, 'pins');

  // TPAR weight tabs
  document.querySelectorAll('#tpar-weight-tabs .hp-tab').forEach(tab => {
    tab.addEventListener('click', async () => {
      const weight = tab.dataset.weight;
      if (weight === selectedTparWeight) return;
      selectedTparWeight = weight;
      document.querySelectorAll('#tpar-weight-tabs .hp-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      if (!miCache[weight]) miCache[weight] = await loadMIData(weight);
      renderTparList(miCache[weight]);
    });
  });

  // Rankings weight tabs (independent from TPAR)
  document.querySelectorAll('#rankings-weight-tabs .hp-tab').forEach(tab => {
    tab.addEventListener('click', async () => {
      const weight = tab.dataset.weight;
      if (weight === selectedRankingsWeight) return;
      selectedRankingsWeight = weight;
      document.querySelectorAll('#rankings-weight-tabs .hp-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      if (!rankingsCache[weight]) rankingsCache[weight] = await loadRankingsData(weight);
      renderRankingsPanel(rankingsCache[weight], weight);
    });
  });

  // Stat tabs
  document.querySelectorAll('#stats-tabs .hp-tab').forEach(tab => {
    tab.addEventListener('click', async () => {
      const stat = tab.dataset.stat;
      document.querySelectorAll('#stats-tabs .hp-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      const data = await loadStatLeaderboard(stat);
      renderStatLeaders(data, stat);
    });
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initHomepage);
} else {
  initHomepage();
}
