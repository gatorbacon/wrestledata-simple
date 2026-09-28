// ========================================
// Dual Schedule page: every upcoming dual, grouped by date. Same data
// source and rank lookup as the homepage ticker (dual_ticker.js) -- kept
// as its own self-contained page script rather than sharing that file, so
// this page doesn't also fire (and silently no-op) the ticker's own
// homepage-only render pass.
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

async function loadTeamColors() {
  try {
    // no-cache: this file changes occasionally (e.g. nicknames added
    // 2026-09-13) and has no cache-busting query param -- without this a
    // browser that already cached an old response never sees the update.
    const res = await fetch("/data/team_colors.json", { cache: "no-cache" });
    if (!res.ok) return { teams: {}, default: { hex: "#6b6153", stroke: false } };
    return await res.json();
  } catch {
    return { teams: {}, default: { hex: "#6b6153", stroke: false } };
  }
}

function formatScheduleDate(dateStr) {
  const [y, m, d] = dateStr.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  return date.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

// Darkens/lightens a #rrggbb hex by `percent` (-1..1, negative = darker) --
// used to build the two-tone gradient behind each mobile matchup-card half
// from a single team hex.
function shadeHex(hex, percent) {
  const n = parseInt(hex.replace("#", ""), 16);
  const clamp = v => Math.round(Math.max(0, Math.min(255, v)));
  const r = clamp(((n >> 16) & 0xff) + 255 * percent);
  const g = clamp(((n >> 8) & 0xff) + 255 * percent);
  const b = clamp((n & 0xff) + 255 * percent);
  return `#${((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1)}`;
}

// Same crest+rank+name markup as the homepage ticker (.dual-ticker-team/
// -crest/-rank/-name-full). Also carries team-color CSS vars and the
// school's nickname (from data/team_colors.json) so the <768px CSS can
// turn this same element into the diagonal gradient "matchup card" half
// -- full school name + nickname stacked -- without any separate
// mobile-only markup.
function renderScheduleTeam(team, ranks, colors, side) {
  const rank = ranks[team.slug];
  const colorInfo = (colors.teams && colors.teams[team.slug]) || colors.default || { hex: "#6b6153", stroke: false };
  const hex = colorInfo.hex || "#6b6153";
  const dark = shadeHex(hex, -0.45);
  const style = `--team-color:${hex};--team-color-dark:${dark};`;
  const fallback =
    `if(!this.dataset.fallback){this.dataset.fallback=1;this.src='/assets/team_logos/${team.slug}.png';}` +
    `else{this.remove();}`;
  return (
    `<a class="dual-ticker-team schedule-team schedule-team--${side}" data-stroke="${colorInfo.stroke ? "1" : "0"}" style="${style}" href="/team.html?team=${team.slug}">` +
    `<img class="dual-ticker-crest" src="/assets/team_logos/${team.slug}.svg" alt="" onerror="${fallback}">` +
    (rank ? `<span class="dual-ticker-rank">#${rank}</span>` : "") +
    `<span class="dual-ticker-name-full">${team.name}</span>` +
    (colorInfo.nickname ? `<span class="schedule-team-nickname">${colorInfo.nickname}</span>` : "") +
    `</a>`
  );
}

function renderScheduleRow(dual, ranks, colors) {
  return (
    `<div class="schedule-dual-row">` +
    renderScheduleTeam(dual.team_a, ranks, colors, "a") +
    `<span class="schedule-vs">vs</span>` +
    renderScheduleTeam(dual.team_b, ranks, colors, "b") +
    `</div>`
  );
}

function renderSchedule(duals, ranks, colors) {
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
    g.duals.map(d => renderScheduleRow(d, ranks, colors)).join("") +
    `</div>`
  )).join("");
}

document.addEventListener("DOMContentLoaded", async () => {
  const [duals, ranks, colors] = await Promise.all([
    loadSchedule(), loadScheduleRanks(), loadTeamColors()
  ]);
  renderSchedule(duals, ranks, colors);
});
