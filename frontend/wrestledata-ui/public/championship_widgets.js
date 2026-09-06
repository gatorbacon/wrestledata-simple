// ========================================
// Homepage championship-odds widgets
// ========================================
// Two widgets, both driven by the same /data/team_odds/{season}/ feed that
// already powers the full "NCAA Team Championship Odds" table below them:
//   1. Title Contenders -- top 3 teams by title (1st place) probability
//   2. Trophy Chances -- top 7 teams by probability of finishing top 4

const CW_SEASON = "2027";

// team_odds' own team names are short scrape-convention names (matching
// mt/data/official_schedules/{slug}/ style, e.g. "OK State", "N. Colorado")
// for a handful of teams whose real name doesn't match that abbreviation --
// the frontend's own team pages/logos use fuller slugs (oklahoma_state,
// northern_colorado). Naively slugifying the short name 404s both the logo
// and the team-page link. Same underlying mismatch as the one fixed for
// the dual ticker/P4P builder, just surfacing in this data source instead.
const CW_SLUG_ALIASES = {
  "ok state": "oklahoma_state",
  "nd state": "north_dakota_state",
  "sd state": "south_dakota_state",
  "app state": "appalachian_state",
  "uni": "northern_iowa",
  "army": "army_west_point",
  "siue": "siu_edwardsville",
  "n. colorado": "northern_colorado",
};

function cwSlug(name) {
  if (!name) return "";
  const alias = CW_SLUG_ALIASES[name.trim().toLowerCase()];
  if (alias) return alias;
  return name.toLowerCase()
    .replace(/\s+/g, "_")
    .replace(/[^\w_]/g, "")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function cwFormatPct(pct) {
  if (pct === undefined || pct === null) return "—";
  if (pct === 0) return "0%";
  if (pct < 1) return "<1%";
  return `${Math.round(pct)}%`;
}

function cwCrestImg(slug, cls) {
  return (
    `<img class="${cls}" src="/assets/team_logos/${slug}.svg" alt="" ` +
    `onerror="if(!this.dataset.fb){this.dataset.fb=1;this.src='/assets/team_logos/${slug}.png';}else{this.remove();}">`
  );
}

async function loadTeamOddsForWidgets() {
  try {
    const idxRes = await fetch(`/data/team_odds/${CW_SEASON}/index.json`);
    if (!idxRes.ok) return [];
    const idx = await idxRes.json();
    const newestDate = (idx.dates || [])[0];
    if (!newestDate) return [];
    const res = await fetch(`/data/team_odds/${CW_SEASON}/${newestDate}.json`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.teams || [];
  } catch {
    return [];
  }
}

function cwTop4Prob(team) {
  const p = team.p_place || {};
  return (p["1"] || 0) + (p["2"] || 0) + (p["3"] || 0) + (p["4"] || 0);
}

// ---------- Widget 1: Title Contenders (top 3) ----------

function renderTitleContenders(teams) {
  const wrap = document.getElementById("title-contenders-section");
  if (!wrap) return;
  if (!teams.length) { wrap.innerHTML = ""; return; }

  const top3 = teams.slice().sort((a, b) => b.p_1st - a.p_1st).slice(0, 3);
  const medals = ["gold", "silver", "bronze"];

  const cards = top3.map((t, i) => {
    const slug = cwSlug(t.team);
    return (
      `<a class="contender-card contender-${medals[i]}" href="/team.html?team=${slug}">` +
      `<div class="contender-rank">#${i + 1}</div>` +
      cwCrestImg(slug, "contender-crest") +
      `<div class="contender-name">${t.team}</div>` +
      `<div class="contender-pct">${cwFormatPct(t.p_1st)}</div>` +
      `<div class="contender-label">Title Chance</div>` +
      `</a>`
    );
  }).join("");

  wrap.innerHTML =
    `<div class="section-header">` +
    `<h2>2027 National Championship Favorites</h2>` +
    `<a href="/team_odds.html" class="section-header-link">Full Table →</a>` +
    `</div>` +
    `<div class="contenders-row">${cards}</div>`;
}

// ---------- Widget 2: Trophy Chances (top 7, top-4 finish) ----------

function renderTrophyChances(teams) {
  const wrap = document.getElementById("trophy-chances-section");
  if (!wrap) return;
  if (!teams.length) { wrap.innerHTML = ""; return; }

  const top7 = teams
    .map(t => ({ ...t, _top4: cwTop4Prob(t) }))
    .sort((a, b) => b._top4 - a._top4)
    .slice(0, 7);

  const cols = top7.map((t, i) => {
    const slug = cwSlug(t.team);
    const pct = Math.max(0, Math.min(100, t._top4));
    return (
      `<a class="trophy-col" href="/team.html?team=${slug}">` +
      `<div class="trophy-rank">#${i + 1}</div>` +
      cwCrestImg(slug, "trophy-crest") +
      `<div class="trophy-name">${t.team}</div>` +
      `<div class="trophy-pct">${cwFormatPct(t._top4)}</div>` +
      `<div class="trophy-bar-track"><div class="trophy-bar-fill" style="width:${pct}%"></div></div>` +
      `</a>`
    );
  }).join("");

  wrap.innerHTML =
    `<div class="section-header">` +
    `<h2>Trophy Odds</h2>` +
    `<span class="header-subline">Probability of a top-4 finish</span>` +
    `</div>` +
    `<div class="trophy-row">${cols}</div>`;
}

document.addEventListener("DOMContentLoaded", async () => {
  const teams = await loadTeamOddsForWidgets();
  renderTitleContenders(teams);
  renderTrophyChances(teams);
});
