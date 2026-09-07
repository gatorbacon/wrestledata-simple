// ========================================
// Dual Schedule page: every upcoming dual, grouped by date. Same data
// source, rank lookup, and team-abbreviation reuse as the homepage
// ticker (dual_ticker.js) -- kept as its own self-contained page script
// rather than sharing that file, so this page doesn't also fire (and
// silently no-op) the ticker's own homepage-only render pass.
// ========================================

const SCHEDULE_XTP_SEASON = "2026";
const SCHEDULE_TOP_N = 25;

function scheduleSlug(name) {
  if (!name) return "";
  return name.toLowerCase()
    .replace(/\s+/g, "_")
    .replace(/[^\w_]/g, "")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "");
}

async function loadSchedule() {
  try {
    const res = await fetch("/data/schedule/duals_2026-27.json");
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

async function loadScheduleRanks() {
  try {
    const res = await fetch(`/data/xtp/${SCHEDULE_XTP_SEASON}/xtp_teams_${SCHEDULE_XTP_SEASON}.json`);
    if (!res.ok) return {};
    const data = await res.json();
    const ranked = [...data.teams].sort((a, b) => b.team_xTP - a.team_xTP);
    const ranks = {};
    ranked.slice(0, SCHEDULE_TOP_N).forEach((t, i) => {
      ranks[scheduleSlug(t.team)] = i + 1;
    });
    return ranks;
  } catch {
    return {};
  }
}

async function loadTeamAbbreviations() {
  try {
    const res = await fetch("/data/teams/abbreviations.json");
    if (!res.ok) return {};
    return await res.json();
  } catch {
    return {};
  }
}

function formatScheduleDate(dateStr) {
  const [y, m, d] = dateStr.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  return date.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

// Same crest+rank+name markup/behavior as the homepage ticker (full name
// on desktop, official abbreviation on mobile -- same <768px swap rule).
function renderScheduleTeam(team, ranks, abbrevs, side) {
  const rank = ranks[team.slug];
  const abbr = abbrevs[team.slug] || team.name;
  const fallback =
    `if(!this.dataset.fallback){this.dataset.fallback=1;this.src='/assets/team_logos/${team.slug}.png';}` +
    `else{this.remove();}`;
  return (
    `<a class="dual-ticker-team schedule-team schedule-team--${side}" href="/team.html?team=${team.slug}">` +
    `<img class="dual-ticker-crest" src="/assets/team_logos/${team.slug}.svg" alt="" onerror="${fallback}">` +
    (rank ? `<span class="dual-ticker-rank">#${rank}</span>` : "") +
    `<span class="dual-ticker-name-full">${team.name}</span>` +
    `<span class="dual-ticker-name-abbr">${abbr}</span>` +
    `</a>`
  );
}

function renderScheduleRow(dual, ranks, abbrevs) {
  return (
    `<div class="schedule-dual-row">` +
    renderScheduleTeam(dual.team_a, ranks, abbrevs, "a") +
    `<span class="schedule-vs">vs</span>` +
    renderScheduleTeam(dual.team_b, ranks, abbrevs, "b") +
    `</div>`
  );
}

function renderSchedule(duals, ranks, abbrevs) {
  const list = document.getElementById("schedule-list");
  const countEl = document.getElementById("schedule-count");
  if (!list) return;

  if (!duals.length) {
    list.innerHTML = `<p class="section-empty-state">No upcoming duals scheduled.</p>`;
    if (countEl) countEl.textContent = "";
    return;
  }

  if (countEl) countEl.textContent = `${duals.length} duals`;

  // The feed is already date-ordered (same convention the ticker relies
  // on) -- just group consecutive same-date entries rather than re-sorting.
  const groups = [];
  let currentGroup = null;
  duals.forEach(d => {
    if (!currentGroup || d.date !== currentGroup.date) {
      currentGroup = { date: d.date, duals: [] };
      groups.push(currentGroup);
    }
    currentGroup.duals.push(d);
  });

  list.innerHTML = groups.map(g => (
    `<div class="schedule-date-group">` +
    `<div class="schedule-date-heading">${formatScheduleDate(g.date)}</div>` +
    g.duals.map(d => renderScheduleRow(d, ranks, abbrevs)).join("") +
    `</div>`
  )).join("");
}

document.addEventListener("DOMContentLoaded", async () => {
  const [duals, ranks, abbrevs] = await Promise.all([loadSchedule(), loadScheduleRanks(), loadTeamAbbreviations()]);
  renderSchedule(duals, ranks, abbrevs);
});
