// ========================================
// Team Race page
// ========================================
// Data source: /data/team_odds/{season}/index.json -> {season}/{date}.json
// -- the same Monte Carlo team simulation (10,000 trials/drop) that already
// powers the homepage "Title Contenders"/"Trophy Chances" widgets
// (championship_widgets.js) and the full /team_odds.html table
// (team_odds.js). This page used to read the older xtp_teams_{season}.json
// (placement/advancement/bonus decomposition, real completed-season stats
// only) -- switched on request, since that file only exists through the
// 2026 season and can't be computed pre-season, while the Monte Carlo feed
// already has real current-season (2027) numbers.
//
// team.expected     -> this page's "xTP" hero number
// team.p_1st         -> "Title %"  (already 0-100 scale, no *100 needed)
// team.p_place 1-4   -> "Trophy %" (P(finish top 4), same definition used
//                        sitewide -- see championship_widgets.js's cwTop4Prob)
// team.lineup_detail -> expanded per-weight lineup. About 59% of slots
//                        sitewide have no real identified wrestler (rank:
//                        null, name: null) -- the simulation falls back to
//                        a generic ranks-25-33 pool for those (see
//                        docs/matsavant.md's Monte Carlo "Known
//                        simplification"). Those slots still carry a real,
//                        nonzero `expected` value; only the name/rank are
//                        missing, so they render as "Unranked" with a UNR
//                        badge, not as an empty/no-qualifier row.
//
// No wrestler_id exists in this data source, so (matching the site's own
// precedent in team_odds.js's own expanded view) wrestler names here are
// plain text, not profile links, and there are no headshots.

const TR_SEASON = "2027"; // independent of any other season constant on the site
const TR_SCALE_MAX = 200; // fixed domain for the per-team range bar, matches team_odds.js's SCALE_MAX
const TR_NAVY_FALLBACK = "#2c5c8f"; // solid navy fallback when a team has no entry in team_colors.json
const WEIGHTS = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285];

// team_odds' own team names use short scrape-convention abbreviations for a
// handful of teams that don't match the frontend's fuller team-page slugs
// -- same alias table already used by team_odds.js/championship_widgets.js.
const TR_SLUG_ALIASES = {
  "ok state": "oklahoma_state",
  "nd state": "north_dakota_state",
  "sd state": "south_dakota_state",
  "app state": "appalachian_state",
  "uni": "northern_iowa",
  "army": "army_west_point",
  "siue": "siu_edwardsville",
  "n. colorado": "northern_colorado",
};

let teamData = [];
let teamColors = {}; // slug -> { hex, stroke }
let expandedTeam = null; // single team name, or null -- only one open at a time, none by default

function fmtXTP(v) {
  return v === null || v === undefined ? "—" : v.toFixed(1);
}

function fmtPct(pct) {
  if (pct === null || pct === undefined) return "—";
  if (pct === 0) return "0%";
  if (pct < 1) return "<1%";
  return `${Math.round(pct)}%`;
}

function top4Prob(team) {
  const p = team.p_place || {};
  return (p["1"] || 0) + (p["2"] || 0) + (p["3"] || 0) + (p["4"] || 0);
}

function teamNameToSlug(teamName) {
  if (!teamName) return "";
  const alias = TR_SLUG_ALIASES[teamName.trim().toLowerCase()];
  if (alias) return alias;
  let slug = teamName.toLowerCase();
  slug = slug.replace(/\s+/g, "_");
  slug = slug.replace(/[^\w_]/g, "");
  slug = slug.replace(/_+/g, "_");
  slug = slug.replace(/^_+|_+$/g, "");
  return slug;
}

function teamAbbr(teamName) {
  if (!teamName) return "";
  const words = teamName.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "";
  if (words.length === 1) return words[0].slice(0, 3).toUpperCase();
  return words.map(w => w[0]).join("").toUpperCase().slice(0, 3);
}

function createRankBadge(rank) {
  if (rank === null || rank === undefined || rank === "") {
    return document.createTextNode("—");
  }
  const badge = document.createElement("span");
  badge.className = "rank-badge";
  if (rank === 1) badge.classList.add("medal-gold");
  else if (rank === 2) badge.classList.add("medal-silver");
  else if (rank === 3) badge.classList.add("medal-bronze");
  else badge.classList.add("standard");
  badge.textContent = `#${rank}`;
  return badge;
}

function createUnrankedBadge() {
  const badge = document.createElement("span");
  badge.className = "rank-badge unr-badge";
  badge.textContent = "UNR";
  return badge;
}

function teamBarColor(slug) {
  const entry = teamColors[slug];
  return entry && entry.hex ? entry.hex : TR_NAVY_FALLBACK;
}

// Team crest with a required fallback: svg -> png -> abbreviation circle.
function createTeamMark(teamName, slug) {
  const wrap = document.createElement("span");
  wrap.className = "tr-team-mark";
  const img = document.createElement("img");
  img.alt = "";
  img.loading = "lazy";
  img.src = `/assets/team_logos/${slug}.svg`;
  img.addEventListener("error", () => {
    if (!img.dataset.fb) {
      img.dataset.fb = "1";
      img.src = `/assets/team_logos/${slug}.png`;
    } else {
      wrap.innerHTML = "";
      wrap.classList.add("tr-team-mark--abbr");
      wrap.textContent = teamAbbr(teamName);
    }
  });
  wrap.appendChild(img);
  return wrap;
}

async function loadTeamColors() {
  try {
    const res = await fetch("/data/team_colors.json");
    if (!res.ok) return {};
    const data = await res.json();
    return data.teams || {};
  } catch {
    return {};
  }
}

function formatDateLabel(iso) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function sortedTeams() {
  return [...teamData].sort((a, b) => {
    if (b.expected !== a.expected) return b.expected - a.expected;
    return a.team.localeCompare(b.team);
  });
}

async function loadLeaderboard() {
  try {
    const [idxRes, colors] = await Promise.all([
      fetch(`/data/team_odds/${TR_SEASON}/index.json`),
      loadTeamColors(),
    ]);
    if (!idxRes.ok) throw new Error("Failed to load team_odds index");
    const idx = await idxRes.json();
    const date = (idx.dates || [])[0]; // index.json is newest-first
    if (!date) throw new Error("No team_odds dates available");

    const res = await fetch(`/data/team_odds/${TR_SEASON}/${date}.json`);
    if (!res.ok) throw new Error(`Failed to load ${date}`);
    const data = await res.json();

    teamColors = colors;
    teamData = data.teams || [];

    document.getElementById("season-info").textContent = `${formatDateLabel(date)} rankings`;

    renderLeaderboard();
  } catch (err) {
    console.error("Error loading leaderboard:", err);
    document.getElementById("season-info").textContent = "Error loading data";
    const tbody = document.querySelector("#team-race-table tbody");
    if (tbody) tbody.innerHTML = "";
  }
}

// ---- Rendering ----

function renderLeaderboard() {
  const sorted = sortedTeams();
  const leaderXTP = sorted.length ? sorted[0].expected || 0 : 0;

  const tbody = document.querySelector("#team-race-table tbody");
  tbody.innerHTML = "";

  sorted.forEach((team, index) => {
    const rank = index + 1;
    const isExpanded = expandedTeam === team.team;
    const slug = teamNameToSlug(team.team);
    const color = teamBarColor(slug);

    const tr = document.createElement("tr");
    tr.className = `tr-row expandable-row ${isExpanded ? "expanded" : "collapsed"}`;
    tr.dataset.team = team.team;

    // 1. Expand chevron
    const expandTd = document.createElement("td");
    expandTd.className = "tr-chevron-cell";
    const expandIcon = document.createElement("span");
    expandIcon.className = "expand-icon";
    expandTd.appendChild(expandIcon);
    tr.appendChild(expandTd);

    // 2. Rank pill -- same medal convention as individual rankings (top 3 only)
    const rankTd = document.createElement("td");
    rankTd.className = "tr-rank-cell";
    rankTd.appendChild(createRankBadge(rank));
    tr.appendChild(rankTd);

    // 3-4. Team logo + name (bold, links to team profile)
    const teamTd = document.createElement("td");
    teamTd.className = "tr-team-cell-td";
    const teamWrap = document.createElement("div");
    teamWrap.className = "tr-team-cell";
    teamWrap.appendChild(createTeamMark(team.team, slug));
    const teamLink = document.createElement("a");
    teamLink.className = "tr-team-name";
    teamLink.href = `/team.html?team=${slug}`;
    teamLink.textContent = team.team;
    teamWrap.appendChild(teamLink);
    teamTd.appendChild(teamWrap);
    tr.appendChild(teamTd);

    // 5. Projected Team Points: bold number + bar (+ gap) together on the
    // top row, Title %/Trophy % smaller underneath.
    const xtpTd = document.createElement("td");
    xtpTd.className = "tr-xtp-cell";

    const heroRow = document.createElement("div");
    heroRow.className = "tr-hero-row";

    const xtpValue = document.createElement("span");
    xtpValue.className = "tr-xtp-value";
    xtpValue.textContent = fmtXTP(team.expected);
    heroRow.appendChild(xtpValue);

    const track = document.createElement("div");
    track.className = "tr-bar-track";
    const fill = document.createElement("div");
    fill.className = "tr-bar-fill";
    const barPct = leaderXTP > 0 ? Math.min((team.expected || 0) / leaderXTP, 1) * 100 : 0;
    fill.style.width = `${barPct}%`;
    fill.style.background = color;
    track.appendChild(fill);
    heroRow.appendChild(track);

    const gap = document.createElement("span");
    gap.className = "tr-gap";
    const isLeader = (team.expected || 0) >= leaderXTP;
    gap.textContent = isLeader ? "—" : `−${(leaderXTP - (team.expected || 0)).toFixed(1)}`;
    heroRow.appendChild(gap);

    xtpTd.appendChild(heroRow);

    const heroSub = document.createElement("div");
    heroSub.className = "tr-hero-sub";
    const titleChip = document.createElement("span");
    titleChip.className = "tr-hero-chip";
    titleChip.innerHTML = `Title <strong>${fmtPct(team.p_1st)}</strong>`;
    heroSub.appendChild(titleChip);
    const trophyChip = document.createElement("span");
    trophyChip.className = "tr-hero-chip";
    trophyChip.innerHTML = `Trophy <strong>${fmtPct(top4Prob(team))}</strong>`;
    heroSub.appendChild(trophyChip);
    xtpTd.appendChild(heroSub);
    tr.appendChild(xtpTd);

    tbody.appendChild(tr);

    // Only one team expanded at a time, none by default; opening a second
    // team closes whichever one was open.
    const toggle = () => {
      expandedTeam = expandedTeam === team.team ? null : team.team;
      renderLeaderboard();
    };

    tr.addEventListener("click", e => {
      if (e.target.tagName === "A") return; // don't hijack the team-name link
      toggle();
    });
    expandIcon.addEventListener("click", e => {
      e.stopPropagation();
      toggle();
    });

    if (isExpanded) {
      tbody.appendChild(renderExpandedRow(team, color));
    }
  });
}

function renderExpandedRow(team, color) {
  const tr = document.createElement("tr");
  tr.className = "weight-breakdown expanded";

  const td = document.createElement("td");
  td.colSpan = 4;
  td.className = "tr-expanded-td";

  // Team-level simulated scoring range: p5-p95 band, tick at expected.
  const range = document.createElement("div");
  range.className = "tr-range";
  const lo = team.p5 || 0;
  const hi = team.p95 || 0;
  const exp = team.expected || 0;
  const loPct = Math.min((lo / TR_SCALE_MAX) * 100, 100);
  const hiPct = Math.min((hi / TR_SCALE_MAX) * 100, 100);
  const band = document.createElement("div");
  band.className = "tr-range-band";
  band.style.left = `${loPct}%`;
  band.style.width = `${Math.max(hiPct - loPct, 0)}%`;
  range.appendChild(band);
  const tick = document.createElement("div");
  tick.className = "tr-range-tick";
  tick.style.left = `${Math.min((exp / TR_SCALE_MAX) * 100, 100)}%`;
  range.appendChild(tick);
  td.appendChild(range);

  const rangeLabel = document.createElement("div");
  rangeLabel.className = "tr-range-label";
  rangeLabel.textContent = `Simulated range: ${lo.toFixed(0)}–${hi.toFixed(0)} pts (90% of trials) · expected ${exp.toFixed(1)}`;
  td.appendChild(rangeLabel);

  // Per-weight lineup, 125 -> 285.
  const table = document.createElement("table");
  table.className = "tr-lineup-table";

  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  ["Weight", "Wrestler", "Rank", "xTP"].forEach(h => {
    const th = document.createElement("th");
    th.textContent = h;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  const lineup = [...(team.lineup_detail || [])].sort((a, b) => a.weight - b.weight);
  const teamMaxExpected = Math.max(0, ...lineup.map(w => w.expected || 0));

  lineup.forEach(wd => {
    const row = document.createElement("tr");
    row.className = "tr-lineup-row";

    const weightTd = document.createElement("td");
    weightTd.textContent = wd.weight;
    row.appendChild(weightTd);

    const wrestlerTd = document.createElement("td");
    wrestlerTd.className = "tr-wrestler-td";
    const cell = document.createElement("div");
    cell.className = "tr-wrestler-cell";
    if (wd.name) {
      cell.textContent = wd.name;
    } else {
      const unranked = document.createElement("span");
      unranked.className = "tr-wrestler-unranked";
      unranked.textContent = "Unranked";
      cell.appendChild(unranked);
    }
    wrestlerTd.appendChild(cell);
    row.appendChild(wrestlerTd);

    // Weight-class rank pill -- current hybrid rank, or UNR for the
    // generic unranked-pool fallback.
    const rankTd = document.createElement("td");
    rankTd.appendChild(wd.rank !== null && wd.rank !== undefined ? createRankBadge(wd.rank) : createUnrankedBadge());
    row.appendChild(rankTd);

    // xTP: bold value + bar scaled to this team's own max wrestler xTP.
    // Always real (even the generic-pool fallback carries a nonzero
    // expected value), so always rendered -- no "no qualifier" dash here.
    const xtpTd = document.createElement("td");
    xtpTd.className = "num tr-lineup-xtp-cell";
    const val = document.createElement("div");
    val.className = "tr-lineup-xtp-value";
    val.textContent = fmtXTP(wd.expected);
    xtpTd.appendChild(val);

    const barTrack = document.createElement("div");
    barTrack.className = "tr-lineup-bar-track";
    const barFill = document.createElement("div");
    barFill.className = "tr-lineup-bar-fill";
    const pct = teamMaxExpected > 0 ? Math.min((wd.expected || 0) / teamMaxExpected, 1) * 100 : 0;
    barFill.style.width = `${pct}%`;
    barFill.style.background = color;
    barTrack.appendChild(barFill);
    xtpTd.appendChild(barTrack);
    row.appendChild(xtpTd);

    tbody.appendChild(row);
  });
  table.appendChild(tbody);
  td.appendChild(table);

  tr.appendChild(td);
  return tr;
}

// Initialize
document.addEventListener("DOMContentLoaded", () => {
  loadLeaderboard();
});
