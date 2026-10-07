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
  // Classes, phase and seasons come from recruiting.json (build_recruiting_data.py
  // follows hs_config.js siteSeason); the first current class opens by default.
  let currentClass = null;
  let showAll = false;
  let currentLabels = GRADE_LABELS;

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
    setupShowMore();
    loadData();
  });

  function buildTabs() {
    const tabs = document.getElementById('class-tabs');
    tabs.innerHTML = '';
    const order = recruitingData.class_order || Object.keys(recruitingData.classes).sort();
    const graduated = recruitingData.graduated_class;
    const all = graduated && recruitingData.classes[graduated] ? order.concat([graduated]) : order;
    const requested = params.get('class');
    currentClass = all.includes(requested) ? requested : order[0];
    all.forEach(cls => {
      const btn = document.createElement('button');
      btn.className = 'class-tab' + (cls === currentClass ? ' active' : '');
      btn.dataset.class = cls;
      const isGrad = cls === graduated;
      btn.innerHTML = `<span class="tab-label-full">Class of ${cls}${isGrad ? ' · Graduated' : ''}</span>` +
        `<span class="tab-label-short">${cls}${isGrad ? ' Grad' : ''}</span>`;
      tabs.appendChild(btn);
    });
    applyLayout();
    document.querySelectorAll('.class-tab').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.class-tab').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentClass = btn.dataset.class;
        showAll = false;
        if (recruitingData) renderTable();
      });
    });
  }

  function setupShowMore() {
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
      buildTabs();
      renderTable();
    } catch (e) {
      document.getElementById('recruiting-tbody').innerHTML =
        `<tr><td colspan="10" style="color:var(--muted);padding:2em;text-align:center;">${GENDER === 'girls' ? 'Girls recruiting data coming soon.' : 'Failed to load recruiting data.'}</td></tr>`;
      console.error('Failed to load recruiting data:', e);
    }
  }

  // ---- Render ----

  // Grade columns for the current class: "8th" only when someone in it placed as an 8th grader
  function gradeLabelsFor(entries) {
    const has8th = entries.some(e => e.placements && e.placements['8th']);
    return has8th ? ['8th'].concat(GRADE_LABELS) : GRADE_LABELS;
  }

  // Rank column: preseason rank for current classes, last season's rank for the graduated class
  function rankLabel() {
    if (currentClass === recruitingData.graduated_class) return `${recruitingData.stats_season} Rank`;
    if (recruitingData.phase === 'preseason') return `${recruitingData.site_season} Pre. Rank`;
    return 'Rank';
  }

  function renderHead(labels) {
    const row = document.getElementById('recruiting-head-row');
    if (!row) return;
    row.innerHTML = `<th class="row-num" style="text-align:right;">#</th>
      <th>Name</th><th>Weight</th><th class="rank-col">${rankLabel()}</th><th>School</th>
      ${labels.map(l => `<th class="grade-col">${l}</th>`).join('')}
      <th>Committed To</th>`;
  }

  function renderTable() {
    const allEntries = (recruitingData.classes[currentClass] || []);
    currentLabels = gradeLabelsFor(allEntries);
    renderHead(currentLabels);
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

    const gradesCells = currentLabels.map(label => {
      const place = entry.placements ? entry.placements[label] : null;
      return `<td class="grade-col">${formatPlace(place)}</td>`;
    }).join('');

    const commitCell = entry.committed_to
      ? `<span class="committed-college" style="color:#166534;font-weight:500;">${escapeHtml(entry.committed_to)}</span>`
      : `<span class="uncommitted">Uncommitted</span>`;

    return `
      <td class="row-num">${num !== null ? num : ''}</td>
      <td><a href="${nameHref}">${escapeHtml(displayName(entry.name))}</a></td>
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
    const rankStr = !entry.rank ? '—'
      : currentClass === recruitingData.graduated_class ? `#${entry.rank} · ${recruitingData.stats_season}`
      : recruitingData.phase === 'preseason' ? `#${entry.rank} Pre.`
      : `#${entry.rank}`;

    const medalCells = currentLabels.map(label => {
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
          <a href="${nameHref}" class="recruit-card-name">${escapeHtml(displayName(entry.name))}</a>
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
