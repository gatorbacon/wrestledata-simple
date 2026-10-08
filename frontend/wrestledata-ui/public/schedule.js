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
    `<a class="dual-ticker-team schedule-team schedule-team--${side}" data-stroke="${colorInfo.stroke ? "1" : "0"}" style="${style}" href="${teamHref(team.slug)}">` +
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

// Dense "Text only" row: "#3 Penn State  vs  Rutgers", team names link to
// their team pages, the filtered team (if any) in bold.
function renderScheduleTextTeam(team, ranks, side) {
  const rank = ranks[team.slug];
  const isSel = scheduleState.team === team.slug;
  return (
    `<a class="schedule-text-team schedule-text-team--${side}${isSel ? " is-selected" : ""}" href="${teamHref(team.slug)}">` +
    (rank ? `<span class="schedule-text-rank">#${rank}</span>` : "") +
    `${escapeScheduleHtml(team.name)}</a>`
  );
}

function renderScheduleTextRow(dual, ranks, dateLabel) {
  return (
    `<div class="schedule-text-row${dateLabel ? " is-first" : ""}">` +
    `<span class="schedule-text-date">${dateLabel || ""}</span>` +
    `<span class="schedule-text-match">` +
    renderScheduleTextTeam(dual.team_a, ranks, "a") +
    `<span class="schedule-text-vs">vs</span>` +
    renderScheduleTextTeam(dual.team_b, ranks, "b") +
    `</span></div>`
  );
}

function escapeScheduleHtml(text) {
  const div = document.createElement("div");
  div.textContent = text == null ? "" : String(text);
  return div.innerHTML;
}

// ---------- State: team filter + text-only view, mirrored in the URL ----------
// ?team=<slug> filters to that team's duals; ?view=text = text-only view.
// Text-only is off unless the URL asks for it.

const scheduleState = { team: null, text: false };
let SCHEDULE_DATA = { duals: [], ranks: {}, colors: {}, teams: {} };

function readScheduleURL() {
  const params = new URLSearchParams(location.search);
  scheduleState.team = params.get("team") || null;
  scheduleState.text = params.get("view") === "text";
}

function writeScheduleURL() {
  const params = new URLSearchParams();
  if (scheduleState.team) params.set("team", scheduleState.team);
  if (scheduleState.text) params.set("view", "text");
  const qs = params.toString();
  try { history.replaceState(null, "", location.pathname + (qs ? "?" + qs : "")); } catch (e) { /* ignore */ }
}

function renderSchedule() {
  const { duals: allDuals, ranks, colors, teams } = SCHEDULE_DATA;
  const list = document.getElementById("schedule-list");
  const countEl = document.getElementById("schedule-count");
  if (!list) return;

  const sel = scheduleState.team;
  // Filtered: only that team's duals, with the team always on the left so
  // the list reads as "Penn State vs <opponent>" down the page.
  const duals = sel
    ? allDuals
        .filter(d => d.team_a.slug === sel || d.team_b.slug === sel)
        .map(d => (d.team_b.slug === sel ? { ...d, team_a: d.team_b, team_b: d.team_a } : d))
    : allDuals;

  list.classList.toggle("schedule-page--text", scheduleState.text);

  if (!duals.length) {
    const who = sel ? (teams[sel] || sel) : "";
    list.innerHTML = sel
      ? `<p class="section-empty-state">No upcoming duals for ${escapeScheduleHtml(who)} yet. Their schedule may not be posted.</p>`
      : `<p class="section-empty-state">No upcoming duals scheduled.</p>`;
    if (countEl) countEl.textContent = sel ? `0 duals · ${who}` : "";
    return;
  }

  if (countEl) {
    countEl.textContent = `${duals.length} dual${duals.length === 1 ? "" : "s"}` + (sel ? ` · ${teams[sel] || sel}` : "");
  }

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

  if (scheduleState.text) {
    // Dense table: date in a left column, shown on the first dual of each day.
    list.innerHTML = `<div class="schedule-text-list">` + groups.map(g =>
      g.duals.map((d, i) => renderScheduleTextRow(d, ranks, i === 0 ? formatScheduleDate(g.date) : "")).join("")
    ).join("") + `</div>`;
    return;
  }

  list.innerHTML = groups.map(g => (
    `<div class="schedule-date-group">` +
    `<div class="schedule-date-heading">${formatScheduleDate(g.date)}</div>` +
    g.duals.map(d => renderScheduleRow(d, ranks, colors)).join("") +
    `</div>`
  )).join("");
}

// ---------- Team search (same Fuse setup as the Teams page search) ----------
// Teams page (teams_directory.js) searches the site search index's team
// entries with these exact Fuse options; here the candidate list is the
// teams that actually appear in the schedule (so a pick never filters to
// nothing), and picking one filters the list instead of navigating.

function initScheduleSearch() {
  const input = document.getElementById("schedule-search-input");
  const dropdown = document.getElementById("schedule-search-dropdown");
  const wrap = document.getElementById("schedule-search");
  if (!input || !dropdown) return;

  const tokensBySlug = {};
  (window.SEARCH_INDEX || []).forEach(r => {
    if (r.type !== "team") return;
    // team_id since 2026-10-07 (urls became /team/<name>); older index: parse ?team=
    const m = r.team_id ? [null, r.team_id] : (r.url || "").match(/[?&]team=([^&]+)/);
    if (m) tokensBySlug[decodeURIComponent(m[1])] = r.searchTokens || "";
  });
  const items = Object.entries(SCHEDULE_DATA.teams)
    .map(([slug, name]) => ({ slug, name, searchTokens: tokensBySlug[slug] || "" }))
    .sort((a, b) => a.name.localeCompare(b.name));

  const fuse = typeof Fuse !== "undefined"
    ? new Fuse(items, {
        keys: [
          { name: "name", weight: 0.6 },
          { name: "searchTokens", weight: 0.4 },
        ],
        threshold: 0.4,
        ignoreLocation: true,
        minMatchCharLength: 2,
      })
    : null;

  let current = [];
  let active = -1;

  function hide() { dropdown.style.display = "none"; active = -1; }

  function setActive(i) {
    active = i;
    dropdown.querySelectorAll(".search-result").forEach((el, idx) => el.classList.toggle("is-active", idx === i));
  }

  function render() {
    const q = input.value.trim();
    if (q.length < 2) { hide(); return; }
    current = fuse
      ? fuse.search(q).slice(0, 10).map(r => r.item)
      : items.filter(t => t.name.toLowerCase().includes(q.toLowerCase())).slice(0, 10);
    if (!current.length) {
      dropdown.innerHTML = '<div class="search-result-item search-result-empty">No teams found</div>';
      dropdown.style.display = "block";
      return;
    }
    dropdown.innerHTML = current.map(t => {
      const n = SCHEDULE_DATA.duals.filter(d => d.team_a.slug === t.slug || d.team_b.slug === t.slug).length;
      return `<div class="search-result" data-slug="${t.slug}">` +
        `<div class="search-name">${escapeScheduleHtml(t.name)}</div>` +
        `<div class="search-secondary">${n} dual${n === 1 ? "" : "s"}</div></div>`;
    }).join("");
    dropdown.style.display = "block";
    active = -1;
    dropdown.querySelectorAll(".search-result").forEach((el, idx) => {
      // mousedown so the pick lands before the input loses focus
      el.addEventListener("mousedown", e => { e.preventDefault(); selectScheduleTeam(el.dataset.slug); });
      el.addEventListener("mouseenter", () => setActive(idx));
    });
  }

  input.addEventListener("input", render);
  input.addEventListener("keydown", e => {
    if (dropdown.style.display === "none") return;
    if (e.key === "ArrowDown") { e.preventDefault(); if (current.length) setActive((active + 1) % current.length); }
    else if (e.key === "ArrowUp") { e.preventDefault(); if (current.length) setActive((active - 1 + current.length) % current.length); }
    else if (e.key === "Enter") { e.preventDefault(); const t = current[active >= 0 ? active : 0]; if (t) selectScheduleTeam(t.slug); }
    else if (e.key === "Escape") { hide(); }
  });
  document.addEventListener("click", e => { if (wrap && !wrap.contains(e.target)) hide(); });
  window.__hideScheduleSearch = hide;
}

function renderSelectedTeam() {
  const input = document.getElementById("schedule-search-input");
  const chip = document.getElementById("schedule-selected");
  if (!input || !chip) return;
  const sel = scheduleState.team;
  if (!sel) {
    chip.hidden = true;
    chip.innerHTML = "";
    input.hidden = false;
    return;
  }
  const name = SCHEDULE_DATA.teams[sel] || sel;
  chip.innerHTML =
    `<img class="schedule-selected-crest" src="/assets/team_logos/${sel}.svg" alt="" ` +
    `onerror="if(!this.dataset.fb){this.dataset.fb=1;this.src='/assets/team_logos/${sel}.png';}else{this.remove();}">` +
    `<span class="schedule-selected-name">${escapeScheduleHtml(name)}</span>` +
    `<button type="button" class="schedule-selected-clear" aria-label="Show all teams">&times;</button>`;
  chip.querySelector(".schedule-selected-clear").addEventListener("click", () => {
    selectScheduleTeam(null);
    input.focus();
  });
  chip.hidden = false;
  input.hidden = true;
}

function selectScheduleTeam(slug) {
  scheduleState.team = slug || null;
  const input = document.getElementById("schedule-search-input");
  if (input) input.value = "";
  if (window.__hideScheduleSearch) window.__hideScheduleSearch();
  writeScheduleURL();
  renderSelectedTeam();
  renderSchedule();
}

function initTextToggle() {
  const btn = document.getElementById("schedule-text-toggle");
  if (!btn) return;
  const sync = () => {
    btn.setAttribute("aria-pressed", scheduleState.text ? "true" : "false");
    btn.classList.toggle("is-active", scheduleState.text);
  };
  sync();
  btn.addEventListener("click", () => {
    scheduleState.text = !scheduleState.text;
    sync();
    writeScheduleURL();
    renderSchedule();
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  readScheduleURL();
  const [duals, ranks, colors] = await Promise.all([
    loadSchedule(), loadScheduleRanks(), loadTeamColors()
  ]);
  const teams = {};
  duals.forEach(d => { [d.team_a, d.team_b].forEach(t => { if (t && t.slug) teams[t.slug] = t.name; }); });
  SCHEDULE_DATA = { duals, ranks, colors, teams };
  if (scheduleState.team && !teams[scheduleState.team]) scheduleState.team = null;
  initScheduleSearch();
  initTextToggle();
  renderSelectedTeam();
  renderSchedule();
});
