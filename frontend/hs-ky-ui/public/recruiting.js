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

  document.addEventListener('DOMContentLoaded', () => {
    const label = GENDER === 'girls' ? 'Girls' : 'Boys';
    const subline = document.getElementById('recruiting-subline');
    if (subline) subline.textContent = `Kentucky ${label} Wrestling · Class Profiles & Commitments`;
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
    const visible = showAll ? allEntries.slice(0, MAX_SHOW) : allEntries.slice(0, DEFAULT_SHOW);
    const remaining = allEntries.length - visible.length;

    const tbody = document.getElementById('recruiting-tbody');
    tbody.innerHTML = '';

    visible.forEach((entry, i) => {
      const tr = document.createElement('tr');
      tr.innerHTML = buildRow(entry, i + 1);
      tbody.appendChild(tr);
    });

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
    const nameHref = `/wrestler.html?career_id=${encodeURIComponent(entry.career_id)}&gender=boys`;
    const teamHref = `/team.html?team=${encodeURIComponent(entry.team_slug)}&gender=boys`;

    const rankCell = entry.rank
      ? `#${entry.rank}`
      : `<span style="color:var(--muted)">—</span>`;

    const gradesCells = GRADE_LABELS.map(label => {
      const place = entry.placements ? entry.placements[label] : null;
      return `<td class="grade-col">${formatPlace(place)}</td>`;
    }).join('');

    const commitCell = entry.committed_to
      ? `<span class="committed-college">${escapeHtml(entry.committed_to)}</span>`
      : `<span class="uncommitted">Uncommitted</span>`;

    return `
      <td class="row-num">${num}</td>
      <td><a href="${nameHref}">${escapeHtml(entry.name)}</a></td>
      <td>${entry.weight || '—'}</td>
      <td class="rank-col">${rankCell}</td>
      <td><a href="${teamHref}">${escapeHtml(entry.team || '—')}</a></td>
      ${gradesCells}
      <td>${commitCell}</td>
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
