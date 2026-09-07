// ========================================
// Homepage upcoming-duals ticker
// ========================================
// Schedule-only for now (no scores) -- data comes from
// scripts/scraping/dedupe_events.py's export_duals_for_ticker(), which
// already filters to today-or-later and resolves each team to the
// frontend's own team-page slug (not the schedule scraper's internal one).

const DUAL_TICKER_XTP_SEASON = "2026"; // xtp/{season}/ folder -- season-start-year convention
const DUAL_TICKER_TOP_N = 25;

function dualTickerSlug(name) {
  if (!name) return "";
  return name.toLowerCase()
    .replace(/\s+/g, "_")
    .replace(/[^\w_]/g, "")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "");
}

async function loadDualTicker() {
  try {
    const res = await fetch("/data/schedule/duals_2026-27.json");
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

async function loadDualTickerRanks() {
  try {
    const res = await fetch(`/data/xtp/${DUAL_TICKER_XTP_SEASON}/xtp_teams_${DUAL_TICKER_XTP_SEASON}.json`);
    if (!res.ok) return {};
    const data = await res.json();
    const ranked = [...data.teams].sort((a, b) => b.team_xTP - a.team_xTP);
    const ranks = {};
    ranked.slice(0, DUAL_TICKER_TOP_N).forEach((t, i) => {
      ranks[dualTickerSlug(t.team)] = i + 1;
    });
    return ranks;
  } catch {
    return {};
  }
}

// Official slug -> abbreviation map (e.g. "penn_state": "PSU"), baked from
// each team's own profile file by scripts/generate_team_abbreviations.py --
// used on mobile so two duals fit per screen without wrapping full names.
async function loadTeamAbbreviations() {
  try {
    const res = await fetch("/data/teams/abbreviations.json");
    if (!res.ok) return {};
    return await res.json();
  } catch {
    return {};
  }
}

function formatDualTickerDate(dateStr) {
  const [y, m, d] = dateStr.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  return date.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

// extraClass: lets other pages (the dual schedule page) reuse this exact
// crest+rank+name markup/behavior inside their own row layout.
function renderDualTickerTeam(team, ranks, abbrevs, extraClass) {
  const rank = ranks[team.slug];
  const abbr = abbrevs[team.slug] || team.name;
  // Most crests are .svg, but some only exist as .png (see assets/
  // team_logos/manifest.json) -- try svg first, fall back to png once,
  // then give up silently (no icon) rather than erroring in a loop.
  const fallback =
    `if(!this.dataset.fallback){this.dataset.fallback=1;this.src='/assets/team_logos/${team.slug}.png';}` +
    `else{this.remove();}`;
  return (
    `<a class="dual-ticker-team${extraClass ? " " + extraClass : ""}" href="/team.html?team=${team.slug}">` +
    `<img class="dual-ticker-crest" src="/assets/team_logos/${team.slug}.svg" alt="" ` +
    `onerror="${fallback}">` +
    (rank ? `<span class="dual-ticker-rank">#${rank}</span>` : "") +
    `<span class="dual-ticker-name-full">${team.name}</span>` +
    `<span class="dual-ticker-name-abbr">${abbr}</span>` +
    `</a>`
  );
}

function renderDualTicker(duals, ranks, abbrevs) {
  const wrap = document.getElementById("dual-ticker-section");
  if (!wrap) return;

  if (!duals.length) {
    wrap.innerHTML = "";
    return;
  }

  const cards = duals.map(d => (
    `<div class="dual-ticker-card">` +
    `<div class="dual-ticker-date">${formatDualTickerDate(d.date)}</div>` +
    renderDualTickerTeam(d.team_a, ranks, abbrevs) +
    renderDualTickerTeam(d.team_b, ranks, abbrevs) +
    `</div>`
  )).join("");

  wrap.innerHTML =
    `<div class="section-header">` +
    `<h2>Upcoming Duals</h2>` +
    `<a href="/schedule.html" class="section-header-link">Schedule →</a>` +
    `</div>` +
    `<div class="dual-ticker-wrap">` +
    `<button class="dual-ticker-arrow" id="dual-ticker-prev" aria-label="Previous dual">&#8249;</button>` +
    `<div class="dual-ticker-track" id="dual-ticker-track">${cards}</div>` +
    `<button class="dual-ticker-arrow" id="dual-ticker-next" aria-label="Next dual">&#8250;</button>` +
    `</div>`;

  const track = document.getElementById("dual-ticker-track");
  const isMobile = () => window.matchMedia("(max-width: 767px)").matches;
  // Mobile shows two cards at a time (scroll-snap in CSS) -- scroll by the
  // track's own width so prev/next lands on the next pair exactly. Desktop
  // keeps the original fixed multi-card scroll amount.
  const scrollAmount = () => (isMobile() ? track.clientWidth : 336);
  document.getElementById("dual-ticker-prev").addEventListener("click", () => {
    track.scrollBy({ left: -scrollAmount(), behavior: "smooth" });
  });
  document.getElementById("dual-ticker-next").addEventListener("click", () => {
    track.scrollBy({ left: scrollAmount(), behavior: "smooth" });
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  const [duals, ranks, abbrevs] = await Promise.all([loadDualTicker(), loadDualTickerRanks(), loadTeamAbbreviations()]);
  renderDualTicker(duals, ranks, abbrevs);
});
