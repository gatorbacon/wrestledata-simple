// =============================================
// College Recruiting Page
// =============================================

(function () {
  'use strict';

  const params = new URLSearchParams(window.location.search);
  const GENDER = params.get('gender') === 'girls' ? 'girls' : 'boys';
  const DATA_URL = `/data/recruiting/${GENDER}/recruiting.json`;
  const DEFAULT_SHOW = 50;
  const MAX_SHOW = 100;

  const GRADE_LABELS = ['Fr', 'So', 'Jr', 'Sr'];

  let recruitingData = null;
  let currentClass = '2026';
  let showAll = false;

  // ---- Init ----

  function applyLayout() {
    const mobile = window.innerWidth <= 680;
    document.querySelectorAll('.recruiting-desktop').forEach(el => el.style.display = mobile ? 'none' : '');
    document.querySelectorAll('.recruiting-mobile').forEach(el => el.style.display = mobile ? 'block' : 'none');

    // Tab labels: short year on mobile, full "Class of YYYY" on desktop
    document.querySelectorAll('.tab-label-full').forEach(el => el.style.display = mobile ? 'none' : 'inline');
    document.querySelectorAll('.tab-label-short').forEach(el => el.style.display = mobile ? 'inline' : 'none');

    // "Class of:" prefix label only on mobile
    const prefix = document.querySelector('.class-tabs-prefix');
    if (prefix) prefix.style.display = mobile ? 'inline' : 'none';

    // Summary line: hide on mobile
    const summary = document.getElementById('class-summary');
    if (summary) summary.style.display = mobile ? 'none' : '';

    // Tabs: no wrapping on mobile
    const tabs = document.getElementById('class-tabs');
    if (tabs) tabs.style.flexWrap = mobile ? 'nowrap' : 'wrap';
  }

  document.addEventListener('DOMContentLoaded', () => {
    applyLayout();
    window.addEventListener('resize', applyLayout);
    setupTabs();
    loadData();
  });

  function setupTabs() {
    document.querySelectorAll('.class-tab').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.class-tab').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentClass = btn.dataset.class;
        showAll = false;
        if (recruitingData) renderTable();
      });
    });

    document.getElementById('show-more-btn').addEventListener('click', () => {
      showAll = true;
      document.getElementById('show-more-btn').style.display = 'none';
      renderTable();
    });
  }

  async function loadData() {
    try {
      const res = await fetch(DATA_URL);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      recruitingData = await res.json();
      renderTable();
    } catch (e) {
      document.getElementById('recruiting-tbody').innerHTML =
        `<tr><td colspan="10" style="color:var(--muted);padding:2em;text-align:center;">${GENDER === 'girls' ? 'Girls recruiting data coming soon.' : 'Failed to load recruiting data.'}</td></tr>`;
      console.error('Failed to load recruiting data:', e);
    }
  }

  // ---- Render ----

  function renderTable() {
    const allEntries = (recruitingData.classes[currentClass] || []);
    const ranked = allEntries.slice(0, MAX_SHOW);
    const bonusCommitted = allEntries.slice(MAX_SHOW); // committed-only entries appended by build script
    const visible = showAll ? ranked : ranked.slice(0, DEFAULT_SHOW);
    const remaining = ranked.length - visible.length;

    const tbody = document.getElementById('recruiting-tbody');
    tbody.innerHTML = '';

    visible.forEach((entry, i) => {
      const tr = document.createElement('tr');
      if (entry.committed_to) tr.style.backgroundColor = '#f0fdf4';
      tr.innerHTML = buildRow(entry, i + 1);
      tbody.appendChild(tr);
    });

    // Bonus committed (beyond top 100) — only shown when expanded, no rank number
    if (showAll) {
      bonusCommitted.forEach(entry => {
        const tr = document.createElement('tr');
        tr.style.backgroundColor = '#f0fdf4';
        tr.innerHTML = buildRow(entry, null);
        tbody.appendChild(tr);
      });
    }

    // Mobile cards
    const cardsEl = document.getElementById('recruiting-cards');
    cardsEl.innerHTML = '';
    visible.forEach((entry, i) => {
      const card = document.createElement('div');
      card.className = 'recruit-card';
      if (entry.committed_to) card.style.backgroundColor = '#f0fdf4';
      card.innerHTML = buildCard(entry, i + 1);
      cardsEl.appendChild(card);
    });

    if (showAll) {
      bonusCommitted.forEach(entry => {
        const card = document.createElement('div');
        card.className = 'recruit-card';
        card.style.backgroundColor = '#f0fdf4';
        card.innerHTML = buildCard(entry, null);
        cardsEl.appendChild(card);
      });
    }

    // Summary line
    const placers = allEntries.filter(e => e.total_points > 0).length;
    const committed = allEntries.filter(e => e.committed_to).length;
    document.getElementById('class-summary').textContent =
      `${allEntries.length} wrestlers · ${placers} with state placements · ${committed} committed`;

    // Show more button
    const btn = document.getElementById('show-more-btn');
    if (!showAll && remaining > 0) {
      btn.style.display = 'block';
      btn.textContent = `Show more (${remaining} remaining)`;
    } else {
      btn.style.display = 'none';
    }
  }

  function buildRow(entry, num) {
    const nameHref = `/wrestler.html?career_id=${encodeURIComponent(entry.career_id)}&gender=${GENDER}`;
    const teamHref = `/team.html?team=${encodeURIComponent(entry.team_slug)}&gender=${GENDER}`;

    const rankCell = entry.rank
      ? `#${entry.rank}`
      : `<span style="color:var(--muted)">—</span>`;

    const gradesCells = GRADE_LABELS.map(label => {
      const place = entry.placements ? entry.placements[label] : null;
      return `<td class="grade-col">${formatPlace(place)}</td>`;
    }).join('');

    const commitCell = entry.committed_to
      ? `<span class="committed-college" style="color:#166534;font-weight:500;">${escapeHtml(entry.committed_to)}</span>`
      : `<span class="uncommitted">Uncommitted</span>`;

    return `
      <td class="row-num">${num !== null ? num : ''}</td>
      <td><a href="${nameHref}">${escapeHtml(entry.name)}</a></td>
      <td>${entry.weight || '—'}</td>
      <td class="rank-col">${rankCell}</td>
      <td><a href="${teamHref}">${escapeHtml(entry.team || '—')}</a></td>
      ${gradesCells}
      <td>${commitCell}</td>
    `;
  }

  function buildCard(entry, num) {
    const nameHref = `/wrestler.html?career_id=${encodeURIComponent(entry.career_id)}&gender=${GENDER}`;
    const teamHref = `/team.html?team=${encodeURIComponent(entry.team_slug)}&gender=${GENDER}`;
    const rankStr = entry.rank ? `#${entry.rank}` : '—';

    const medalCells = GRADE_LABELS.map(label => {
      const place = entry.placements ? entry.placements[label] : null;
      return `<div class="recruit-card-medal-cell">
        <span class="recruit-card-medal-label">${label}</span>
        ${formatPlace(place)}
      </div>`;
    }).join('');

    const commitStr = entry.committed_to
      ? `<span class="committed-college" style="color:#166534;font-weight:500;">${escapeHtml(entry.committed_to)}</span>`
      : `<span class="uncommitted">Uncommitted</span>`;

    return `
      <div class="recruit-card-left">
        <div class="recruit-card-top">
          <span class="recruit-card-num">${num !== null ? num : ''}</span>
          <a href="${nameHref}" class="recruit-card-name">${escapeHtml(entry.name)}</a>
          <span class="recruit-card-rank">${rankStr}</span>
        </div>
        <div class="recruit-card-meta">
          <a href="${teamHref}" style="color:var(--accent)">${escapeHtml(entry.team || '—')}</a>
          &nbsp;·&nbsp;${entry.weight || '—'} lbs
        </div>
        <div class="recruit-card-commit">
          <span class="recruit-card-commit-label">College:</span>${commitStr}
        </div>
      </div>
      <div class="recruit-card-medals">${medalCells}</div>
    `;
  }

  function formatPlace(place) {
    if (!place) return `<span style="color:var(--muted)">—</span>`;
    if (place >= 1 && place <= 8) {
      return `<img src="/img/medals/${place}.png" width="28" height="28" alt="${place}" style="display:block;margin:0 auto;">`;
    }
    return `<span style="color:var(--muted);font-size:0.8rem;">${place}</span>`;
  }

  function escapeHtml(str) {
    const d = document.createElement('div');
    d.textContent = str || '';
    return d.innerHTML;
  }
})();
